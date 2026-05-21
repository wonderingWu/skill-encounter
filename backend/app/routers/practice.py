"""练习会话 API — v3: 六边形能力 + 差距检测

新增：
1. 用户自评入口 GET /api/practice/hexagon-info
2. 开场时检测用户能力差距（I - input差集）
3. 结束时返回六维度评分
"""

import uuid, time
from fastapi import APIRouter, HTTPException
from app.models.schemas import (
    PracticeStartRequest, PracticeStartResponse,
    PracticeMessageRequest, PracticeMessageResponse,
    PracticeEndRequest, FeedbackResponse,
    HexagonSelfAssessment, HexagonScore, HEXAGON_DIMENSIONS,
)
from app.data.scenes import get_scene_by_id
from app.services.llm import generate, build_interviewer_system_prompt, compact_for_continuation
from app.services.rag import retrieve
from app.services.evaluator import evaluate_session, evaluate_hexagon, detect_gaps
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/practice", tags=["practice"])
_sessions: dict[str, dict] = {}

# 全局用户能力档案（MVP用内存，后续换DB）
_user_hexagon: dict[str, HexagonScore | None] = {"self": None, "latest_ai": None, "history": []}


@router.get("/hexagon-info")
async def hexagon_info():
    """获取六维能力信息和当前评分"""
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
    """开始练习 — v3: 加入差距检测"""
    scene = get_scene_by_id(req.scene_id)
    if scene is None:
        raise HTTPException(status_code=404, detail=f"场景不存在: {req.scene_id}")

    session_id = str(uuid.uuid4())[:8]
    system_prompt = build_interviewer_system_prompt(
        interviewer_role=scene.interviewer_role,
        scene_description=scene.description,
        difficulty_hint=f"难度 {scene.difficulty}",
        rag_context="",
    )
    opening, usage_start = generate(
        prompt="请以面试官身份发出第一道题目或开场白。简洁、自然。",
        system_prompt=system_prompt, temperature=0.6, max_tokens=256,
    )
    _sessions[session_id] = {
        "scene": scene, "system_prompt_base": system_prompt,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "assistant", "content": opening},
        ],
        "round": 1, "total_tokens": usage_start["input"] + usage_start["output"],
        "token_log": [{"action": "start", **usage_start}],
        "rag_used": False, "created_at": time.time(),
        "gap_detected": False,
    }
    return PracticeStartResponse(
        session_id=session_id, scene=scene, opening_message=opening,
    )


@router.post("/message", response_model=PracticeMessageResponse)
async def send_message(req: PracticeMessageRequest):
    """发送消息 — v3: 首次消息触发差距检测并注入提示"""
    session = _sessions.get(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    scene = session["scene"]
    session["messages"].append({"role": "user", "content": req.message})

    # ═══ 首轮差距检测 ═══
    gap_hint = ""
    if not session.get("gap_detected") and session["round"] == 1:
        session["gap_detected"] = True
        try:
            gaps = detect_gaps(req.message)
            if gaps.detected_gaps:
                dim_names = []
                for g in gaps.detected_gaps:
                    d = next((d for d in HEXAGON_DIMENSIONS if d['id'] == g), None)
                    dim_names.append(f"{d['emoji']} {d['name']}" if d else g)
                gap_hint = (
                    f"【注意】从用户的第一条消息中，我注意到TA可能在以下方面需要关注："
                    f"{', '.join(dim_names)}。"
                    f"请在适当的时候温和地引导TA思考这些方向。"
                )
                if gaps.hint_question:
                    gap_hint += f" 提示问题：{gaps.hint_question}"
                logger.info(f"会话 {req.session_id} 差距检测: {gaps.detected_gaps}")
        except Exception as e:
            logger.warning(f"差距检测失败: {e}")

    # compaction
    if len(session["messages"]) > 10:
        session["messages"] = compact_for_continuation(session["messages"], keep_recent=3)

    # JIT RAG
    rag_context = ""
    if session["round"] <= 3 or session["round"] % 3 == 1:
        rag_context = retrieve(scene_id=scene.id, query=req.message, k=2)
        if rag_context:
            session["rag_used"] = True

    # 构建本轮 system prompt（注入差距提示）
    current_sp = build_interviewer_system_prompt(
        interviewer_role=scene.interviewer_role,
        scene_description=scene.description,
        difficulty_hint=(
            f"第{session['round']}轮。{'请保持追问深度' if session['round'] <= 5 else '在2-3轮内自然收尾'}"
            + (f"\n{gap_hint}" if gap_hint else "")
        ),
        rag_context=rag_context,
    )

    reply, usage_msg = generate(
        prompt=req.message, system_prompt=current_sp,
        temperature=0.4, max_tokens=256,
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
    hex_scores, gaps = evaluate_hexagon(session["messages"])
    feedback, usage_eval = evaluate_session(
        session_id=req.session_id, scene_title=scene.title,
        messages=session["messages"], hexagon_scores=hex_scores,
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
