"""语音分析 API — 真声练习模式

接收录音文件 + 转写文本，分析语速、流畅度，返回语音能力评估。
"""

import time
import logging
from fastapi import APIRouter, HTTPException, File, UploadFile, Form
from app.models.schemas import VoiceAnalysisResponse
from app.services.llm import generate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/voice", tags=["voice"])


def _analyze_transcript(text: str, duration_sec: float) -> tuple[str, float, float]:
    """
    分析转写文本的基础指标：
    - 语速 (字/分钟)
    - 停顿估计 (基于文本中的断句)
    - LLM 分析流畅度
    """
    chars = len(text.replace(" ", ""))
    words = len(text)  # 中文字数 ≈ 字符数
    pace = round(words / max(duration_sec / 60, 0.1), 1)  # 字/分钟

    # 基础分析
    sentence_count = text.count("。") + text.count("？") + text.count("！") + 1
    avg_sentence_len = round(words / max(sentence_count, 1), 1)

    # 流畅度指标
    filler_count = text.count("嗯") + text.count("呃") + text.count("那个") + text.count("就是")
    repetition = text.count("……") + text.count("..")

    return f"语速 {pace} 字/分钟 | 共 {words} 字 {sentence_count} 句 | 平均句长 {avg_sentence_len} 字", pace, chars


@router.post("/analyze", response_model=VoiceAnalysisResponse)
async def analyze_voice(
    audio: UploadFile = File(...),
    transcript: str = Form(default=""),
    duration: float = Form(default=0),
    scene_type: str = Form(default="speech"),
):
    """
    接收录音文件和转写文本，返回语音分析结果。

    - audio: 录音文件 (webm/wav)
    - transcript: Web Speech API 转写的文本
    - duration: 录音时长 (秒)
    - scene_type: 场景类型 (speech/debate/interview)
    """
    if duration <= 0:
        raise HTTPException(status_code=400, detail="录音时长无效")

    # 保存录音文件
    timestamp = int(time.time())
    filename = f"voice_{timestamp}.webm"

    try:
        audio_bytes = await audio.read()
        if len(audio_bytes) == 0:
            raise HTTPException(status_code=400, detail="录音文件为空")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"读取录音失败: {e}")

    # 基础指标
    basic_metrics, pace, chars = _analyze_transcript(transcript, duration)

    # LLM 语音能力分析
    scene_label = {"speech": "即兴演讲", "debate": "辩论", "interview": "面试"}.get(scene_type, "表达练习")
    analysis_prompt = f"""分析以下{scene_label}录音转写文本的语音表现。录音时长 {duration:.0f} 秒，{chars} 字。

转写文本：
---
{transcript[:800]}
---

请从以下维度简短评估（每个维度一句话）：
1. 语速：{pace} 字/分钟是否合适？
2. 流畅度：有没有重复、停顿、填充词？
3. 结构：表达是否清晰有逻辑？
4. 改进建议：最重要的1个改进方向

用中文回复，200字以内，自然说话语气。"""

    analysis, usage = generate(
        prompt=analysis_prompt,
        temperature=0.3,
        max_tokens=256,
    )

    # 构建反馈
    pace_feedback = "语速适中" if 120 <= pace <= 250 else ("语速偏快" if pace > 250 else "语速偏慢")
    if pace < 80:
        pace_feedback += "——可能是因为思考时间较长，可以尝试减少停顿"
    elif pace > 300:
        pace_feedback += "——可以适当放慢，给听众消化时间"

    return VoiceAnalysisResponse(
        transcript=transcript,
        duration_sec=duration,
        word_count=chars,
        pace_wpm=pace,
        pace_feedback=pace_feedback,
        basic_metrics=basic_metrics,
        ai_analysis=analysis.strip(),
    )
