"""练习会话 API 路由"""

import uuid
from fastapi import APIRouter, HTTPException
from app.models.schemas import (
    PracticeStartRequest,
    PracticeStartResponse,
    PracticeMessageRequest,
    PracticeMessageResponse,
    PracticeEndRequest,
    FeedbackResponse,
    MessageRole,
)
from app.data.scenes import get_scene_by_id
from app.services.llm import generate, build_interviewer_system_prompt
from app.services.rag import retrieve
from app.services.evaluator import evaluate_session
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/practice", tags=["practice"])

# 简易内存存储（生产环境应改为 Redis/DB）
_sessions: dict[str, dict] = {}


@router.post("/start", response_model=PracticeStartResponse)
async def start_practice(req: PracticeStartRequest):
    """开始一个练习会话"""
    scene = get_scene_by_id(req.scene_id)
    if scene is None:
        raise HTTPException(status_code=404, detail=f"场景不存在: {req.scene_id}")

    session_id = str(uuid.uuid4())[:8]

    # RAG 检索相关知识
    rag_context = retrieve(
        scene_id=scene.id,
        query=f"{scene.title} {scene.description}",
        k=5,
    )

    # 构建面试官 prompt
    system_prompt = build_interviewer_system_prompt(
        interviewer_role=scene.interviewer_role,
        scene_description=scene.description,
        rag_context=rag_context,
    )

    # 生成开场白
    opening = generate(
        prompt="请开始面试，发出第一道题目或开场白。只需要发出面试内容，不要加任何额外说明。",
        system_prompt=system_prompt,
        temperature=0.8,
    )

    # 保存会话
    _sessions[session_id] = {
        "scene": scene,
        "system_prompt": system_prompt,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "assistant", "content": opening},
        ],
        "round": 1,
    }

    return PracticeStartResponse(
        session_id=session_id,
        scene=scene,
        opening_message=opening,
    )


@router.post("/message", response_model=PracticeMessageResponse)
async def send_message(req: PracticeMessageRequest):
    """发送消息，获取 AI 面试官回复"""
    session = _sessions.get(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    # 记录用户消息
    session["messages"].append({"role": "user", "content": req.message})

    # 调用 LLM 生成回复
    reply = generate(
        prompt=req.message,
        system_prompt=session["system_prompt"],
        temperature=0.8,
    )

    # 记录 AI 回复
    session["messages"].append({"role": "assistant", "content": reply})
    session["round"] += 1

    logger.info(
        f"会话 {req.session_id} 第 {session['round']} 轮, "
        f"累计消息 {len(session['messages'])} 条"
    )

    return PracticeMessageResponse(
        session_id=req.session_id,
        reply=reply,
        current_round=session["round"],
    )


@router.post("/end", response_model=FeedbackResponse)
async def end_practice(req: PracticeEndRequest):
    """结束练习，获取结构化反馈"""
    session = _sessions.get(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    scene = session["scene"]

    # 生成反馈
    feedback = evaluate_session(
        session_id=req.session_id,
        scene_title=scene.title,
        messages=session["messages"],
    )

    # 清理会话
    del _sessions[req.session_id]

    return FeedbackResponse(
        session_id=req.session_id,
        feedback=feedback,
    )
