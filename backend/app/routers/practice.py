"""练习会话 API — v3: 六边形能力 + 差距检测

新增：
1. 用户自评入口 GET /api/practice/hexagon-info
2. 开场时检测用户能力差距（I - input差集）
3. 结束时返回六维度评分
"""

import uuid, time
from fastapi import APIRouter, HTTPException, Request
from app.models.schemas import (
    PracticeStartRequest, PracticeStartResponse,
    PracticeMessageRequest, PracticeMessageResponse,
    PracticeEndRequest, FeedbackResponse, ProfileRequest,
    HexagonSelfAssessment, HexagonScore, HEXAGON_DIMENSIONS,
)
from app.data.scenes import get_scene_by_id
from app.data.coaches import get_coach_by_id
from app.services.llm import generate, build_interviewer_system_prompt, compact_for_continuation
from app.services.rag import retrieve
from app.services.evaluator import evaluate_session, evaluate_hexagon
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/practice", tags=["practice"])
_sessions: dict[str, dict] = {}

# 全局用户能力档案（MVP用内存，后续换DB）
_user_hexagon: dict[str, HexagonScore | None] = {"self": None, "latest_ai": None, "history": []}
_user_profile: dict = {}

# 简单速率限制（内存，MVP阶段）
_rate_limits: dict[str, list[float]] = {}  # {ip: [timestamps]}
RATE_LIMIT_WINDOW = 60   # 秒
RATE_LIMIT_MAX = 30       # 每窗口最多请求数
SESSION_TTL = 3600        # 会话超时 1小时


def _cleanup_expired_sessions():
    """清理过期会话"""
    now = time.time()
    expired = [sid for sid, s in _sessions.items() if now - s.get("created_at", 0) > SESSION_TTL]
    for sid in expired:
        del _sessions[sid]
    if expired:
        logger.info(f"清理 {len(expired)} 个过期会话")


def _check_rate_limit(client_ip: str) -> bool:
    """简单速率限制，返回 True 表示允许"""
    now = time.time()
    if client_ip not in _rate_limits:
        _rate_limits[client_ip] = []
    # 清理过期记录
    _rate_limits[client_ip] = [t for t in _rate_limits[client_ip] if now - t < RATE_LIMIT_WINDOW]
    if len(_rate_limits[client_ip]) >= RATE_LIMIT_MAX:
        return False
    _rate_limits[client_ip].append(now)
    return True


@router.get("/profile")
async def get_profile():
    """获取用户画像"""
    return {
        "profile": _user_profile,
        "hexagon": {
            "dimensions": HEXAGON_DIMENSIONS,
            "self_assessment": _user_hexagon.get("self"),
            "latest_ai": _user_hexagon.get("latest_ai"),
            "history": _user_hexagon.get("history", []),
        }
    }


@router.post("/profile")
async def save_profile(profile: ProfileRequest):
    """保存用户画像 {year, major, concerns: [...], hexagon_self: {...}}"""
    if profile.year: _user_profile["year"] = profile.year
    if profile.major: _user_profile["major"] = profile.major
    if profile.concerns: _user_profile["concerns"] = profile.concerns
    if profile.hexagon_self:
        try:
            _user_hexagon["self"] = HexagonSelfAssessment(**profile.hexagon_self)
        except Exception: pass
    return {"status": "ok", "profile": _user_profile}

# -- 保留 hexagon-info 兼容旧调用 --
@router.get("/hexagon-info")
async def hexagon_info():
    """获取六维能力信息（兼容）"""
    return {
        "dimensions": HEXAGON_DIMENSIONS,
        "self_assessment": _user_hexagon.get("self"),
        "latest_ai": _user_hexagon.get("latest_ai"),
        "history": _user_hexagon.get("history", []),
    }


@router.post("/hexagon-self")
async def save_self_assessment(scores: HexagonSelfAssessment):
    """保存用户自评"""
    _user_hexagon["self"] = scores
    return {"status": "ok", "scores": scores.model_dump()}


@router.post("/start", response_model=PracticeStartResponse)
async def start_practice(req: PracticeStartRequest):
    """开始练习 — v4: 加入教练人格"""
    _cleanup_expired_sessions()
    scene = get_scene_by_id(req.scene_id)
    if scene is None:
        raise HTTPException(status_code=404, detail=f"场景不存在: {req.scene_id}")

    # 加载教练人格（预设或自定义）
    coach = get_coach_by_id(req.coach_id)
    if coach is None and req.custom_coach:
        # 自定义教练
        cc = req.custom_coach
        coach = type('Coach', (), {
            'id': req.coach_id, 'name': cc.get('name', '自定义教练'),
            'emoji': cc.get('emoji', '🤖'), 'tagline': cc.get('tagline', ''),
            'personality': cc.get('personality', ''), 'speaking_style': '',
        })()
    coach_personality = ""
    coach_name = ""
    if coach:
        coach_name = getattr(coach, 'name', '')
        personality = getattr(coach, 'personality', '')
        speaking_style = getattr(coach, 'speaking_style', '')
        coach_personality = f"{personality}\n【说话风格】{speaking_style}" if personality else ""

    session_id = str(uuid.uuid4())[:8]
    system_prompt = build_interviewer_system_prompt(
        interviewer_role=scene.interviewer_role,
        scene_description=scene.description,
        difficulty_hint=f"难度 {scene.difficulty}",
        rag_context="",
        coach_context=coach_personality,
    )
    # 开场词：教练自报身份 + 确认场景 + 开始
    scene_context = f"场景「{scene.title}」：{scene.description}"
    opening_prompt = (
        f"你正在和一位学员对话。{'你的名字是' + coach_name + '，' if coach_name else ''}"
        f"做简短自我介绍（1-2句）。用户选择了{scene_context}。"
        "不要问「你想聊什么」——用户已经选了场景。直接进入场景开始练习。自然、简洁。"
    )
    opening, usage_start = generate(
        prompt=opening_prompt,
        system_prompt=system_prompt, temperature=0.6, max_tokens=256,
    )
    _sessions[session_id] = {
        "scene": scene, "coach": coach, "system_prompt_base": system_prompt,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "assistant", "content": opening},
        ],
        "round": 1, "total_tokens": usage_start["input"] + usage_start["output"],
        "token_log": [{"action": "start", **usage_start}],
        "rag_used": False, "created_at": time.time(),
    }
    return PracticeStartResponse(
        session_id=session_id, scene=scene, coach=coach, opening_message=opening,
    )


@router.post("/message", response_model=PracticeMessageResponse)
async def send_message(req: PracticeMessageRequest, request: Request):
    """发送消息 — v3: 首次消息触发差距检测并注入提示"""
    # 速率限制
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")

    # 定期清理过期会话
    _cleanup_expired_sessions()

    session = _sessions.get(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    scene = session["scene"]
    session["messages"].append({"role": "user", "content": req.message})

    # compaction
    if len(session["messages"]) > 10:
        session["messages"] = compact_for_continuation(session["messages"], keep_recent=3)

    # JIT RAG — 每轮检索，确保面试有行业知识支撑
    rag_context = ""
    rag_context = retrieve(scene_id=scene.id, query=req.message, k=3, user_concerns=_user_profile.get("concerns"))
    if rag_context:
        session["rag_used"] = True

    # 构建本轮 system prompt（注入教练人格）
    coach = session.get("coach")
    coach_context = ""
    if coach:
        # 教练人格以指令格式注入（而非散文），与 behavior_rules 同级
        personality = getattr(coach, 'personality', '')
        speaking_style = getattr(coach, 'speaking_style', '')
        coach_context = f"{personality}\n【说话风格】{speaking_style}" if personality else ""

    current_sp = build_interviewer_system_prompt(
        interviewer_role=scene.interviewer_role,
        scene_description=scene.description,
        difficulty_hint=(
            f"第{session['round']}轮。{'必须追问用户回答中的薄弱点' if session['round'] <= 5 else '在2-3轮内自然收尾'}"
        ),
        rag_context=rag_context,
        coach_context=coach_context,
    )

    # 传对话历史给 LLM（排除 system 消息，避免和当前 sp 重复）
    history = [m for m in session["messages"] if m["role"] != "system"]
    reply, usage_msg = generate(
        prompt=req.message, system_prompt=current_sp,
        temperature=0.4, max_tokens=512,
        history=history,
    )
    session["messages"].append({"role": "assistant", "content": reply})
    session["round"] += 1
    session["total_tokens"] += usage_msg["input"] + usage_msg["output"]
    session["token_log"].append({
        "action": f"message_r{session['round']}", "rag_used": bool(rag_context),
        "total_msgs": len(session["messages"]), **usage_msg,
    })
    return PracticeMessageResponse(
        session_id=req.session_id, reply=reply, current_round=session["round"],
    )


@router.post("/end", response_model=FeedbackResponse)
async def end_practice(req: PracticeEndRequest):
    """结束练习 — v3: 返回六维评分"""
    session = _sessions.get(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    scene = session["scene"]

    # 六维评估
    hex_scores, gaps, strengths, improvements, eval_usage = evaluate_hexagon(session["messages"])
    feedback, usage_eval = evaluate_session(
        session_id=req.session_id, scene_title=scene.title,
        messages=session["messages"], hexagon_scores=hex_scores,
        strengths=strengths, improvements=improvements,
    )

    # 更新用户能力档案
    _user_hexagon["latest_ai"] = hex_scores.model_dump()
    _user_hexagon["history"].append({
        "session_id": req.session_id,
        "scene": scene.title,
        "scores": hex_scores.model_dump(),
        "gaps": gaps,
        "timestamp": time.time(),
    })
    if len(_user_hexagon["history"]) > 20:
        _user_hexagon["history"] = _user_hexagon["history"][-20:]

    session["total_tokens"] += usage_eval.get("input", 0) + usage_eval.get("output", 0)
    del _sessions[req.session_id]

    return FeedbackResponse(session_id=req.session_id, feedback=feedback)
