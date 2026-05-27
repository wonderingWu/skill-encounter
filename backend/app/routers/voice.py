"""语音分析 API — 真声练习模式

接收录音文件 + 转写文本，分析语速、流畅度，返回语音能力评估。
"""

import time
import os
import logging
from fastapi import APIRouter, HTTPException, Request, File, UploadFile, Form
from app.models.schemas import VoiceAnalysisResponse
from app.services.llm import generate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/voice", tags=["voice"])

# 速率限制
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX = 10
_rate_limits: dict[str, list[float]] = {}


def _check_rate(client_ip: str) -> bool:
    now = time.time()
    if client_ip not in _rate_limits:
        _rate_limits[client_ip] = []
    _rate_limits[client_ip] = [t for t in _rate_limits[client_ip] if now - t < RATE_LIMIT_WINDOW]
    if len(_rate_limits[client_ip]) >= RATE_LIMIT_MAX:
        return False
    _rate_limits[client_ip].append(now)
    # 清理空条目防止内存泄漏
    if not _rate_limits[client_ip]:
        del _rate_limits[client_ip]
    return True


def _analyze_transcript(text: str, duration_sec: float, audio_size: int) -> dict:
    """分析转写文本的语音指标"""
    chars = len(text.replace(" ", ""))
    words = len(text)
    pace = round(words / max(duration_sec / 60, 0.5), 1)

    sentence_count = text.count("。") + text.count("？") + text.count("！") + 1
    avg_sentence_len = round(words / max(sentence_count, 1), 1)

    # 填充词统计
    fillers = {"嗯": text.count("嗯"), "呃": text.count("呃"), "那个": text.count("那个"),
               "就是": text.count("就是"), "然后": text.count("然后")}
    filler_total = sum(fillers.values())

    # 音频真实性检查
    expected_min_size = duration_sec * 1000  # ~1KB/sec for opus
    audio_quality = "正常" if audio_size > expected_min_size * 0.5 else "可能录音质量较低"

    return {
        "pace": pace, "chars": chars, "words": words,
        "sentence_count": sentence_count, "avg_sentence_len": avg_sentence_len,
        "filler_total": filler_total, "filler_detail": fillers,
        "audio_size_kb": round(audio_size / 1024, 1),
        "audio_quality": audio_quality,
    }


@router.post("/analyze", response_model=VoiceAnalysisResponse)
async def analyze_voice(
    request: Request,
    audio: UploadFile = File(...),
    transcript: str = Form(default=""),
    duration: float = Form(default=0),
    scene_type: str = Form(default="speech"),
):
    # 速率限制
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate(client_ip):
        raise HTTPException(status_code=429, detail="请求过于频繁")

    if duration <= 0:
        raise HTTPException(status_code=400, detail="录音时长无效")
    if duration > 300:
        raise HTTPException(status_code=400, detail="录音最长 5 分钟")

    # 空转写文本提前返回——不调用 LLM
    text = transcript.strip()
    if not text:
        return VoiceAnalysisResponse(
            transcript="", duration_sec=duration, word_count=0,
            pace_wpm=0, pace_feedback="未检测到语音内容，请确认麦克风正常并重试",
            basic_metrics="", ai_analysis="",
        )

    # 读取音频文件（限制大小）
    audio_bytes = await audio.read()
    if len(audio_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="录音文件过大（上限 10MB）")
    if len(audio_bytes) < 100:
        raise HTTPException(status_code=400, detail="录音文件过短或无内容")

    # 保存音频
    timestamp = int(time.time())
    os.makedirs("voice_recordings", exist_ok=True)
    filepath = f"voice_recordings/voice_{timestamp}.webm"
    try:
        with open(filepath, "wb") as f:
            f.write(audio_bytes)
    except Exception:
        logger.warning("保存录音文件失败，跳过存储")

    # 基础指标分析（使用音频数据）
    metrics = _analyze_transcript(text, duration, len(audio_bytes))
    filler_str = "、".join(f"{k}({v}次)" for k, v in metrics["filler_detail"].items() if v > 0)

    basic_metrics = (
        f"语速 {metrics['pace']} 字/分钟 | {metrics['words']} 字 {metrics['sentence_count']} 句"
        f" | 录音 {metrics['audio_size_kb']}KB({metrics['audio_quality']})"
    )
    if filler_str:
        basic_metrics += f" | 填充词: {filler_str}"

    # LLM 语音能力分析（按场景区分）
    scene_config = {
        "speech": {"label": "即兴演讲", "focus": "观点清晰度、节奏控制、开头和收尾是否有力"},
        "debate": {"label": "辩论", "focus": "论证结构、反驳力度、是否有停顿思考后的精彩回击"},
        "interview": {"label": "面试", "focus": "回答是否切题、STAR结构完整性、语气是否自信"},
    }
    sc = scene_config.get(scene_type, scene_config["speech"])

    # 填充词分析摘要
    filler_note = ""
    if metrics["filler_total"] > 5:
        top_filler = max(metrics["filler_detail"], key=metrics["filler_detail"].get)
        filler_note = f"转写文本中出现 {metrics['filler_total']} 次填充词（最多的是「{top_filler}」）。"

    analysis_prompt = f"""你是语音表达教练。分析以下{sc['label']}录音转写。

录音 {duration:.0f} 秒 · 语速 {metrics['pace']} 字/分钟 · {metrics['words']} 字。
{filler_note}

转写文本（完整）：
---
{text[:1200]}{'…(截断)' if len(text) > 1200 else ''}
---

请评估（重点看{sc['focus']}）：
1. 做得好：这{metrics['words']}字表达里最有效的 1 个点（引用原文佐证）
2. 需改进：最影响表达效果的 1 个问题（引用原文佐证）
3. 一句话建议

要求：只说具体的，不说泛泛的。每个评价必须引用原话。用中文，150字以内。"""

    try:
        analysis, usage = generate(
            prompt=analysis_prompt,
            temperature=0.3,
            max_tokens=256,
        )
        ai_analysis = analysis.strip()
    except Exception as e:
        logger.error(f"LLM 语音分析失败: {e}")
        ai_analysis = f"AI 分析暂不可用。基础数据：{basic_metrics}"

    # 语速反馈
    pace = metrics["pace"]
    if pace < 80:
        pace_feedback = "语速偏慢——思考停顿较多，可以尝试减少「然后」「就是」等填充词"
    elif pace < 120:
        pace_feedback = "语速从容，适合娓娓道来的表达风格"
    elif pace <= 250:
        pace_feedback = "语速适中，信息密度合适"
    elif pace <= 320:
        pace_feedback = "语速偏快——信息量大但听众可能跟不上，关键处适当停顿"
    else:
        pace_feedback = "语速很快——可能因为紧张，建议做深呼吸降速"

    return VoiceAnalysisResponse(
        transcript=text,
        duration_sec=duration,
        word_count=metrics["chars"],
        pace_wpm=pace,
        pace_feedback=pace_feedback,
        basic_metrics=basic_metrics,
        ai_analysis=ai_analysis,
    )
