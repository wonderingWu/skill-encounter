"""练习会话 API — v2 重构

基于 Anthropic Context Engineering 最佳实践的核心改进：
1. Just-in-time RAG：不在开始时一次性注入全部知识，而是每轮按需检索
2. 渐进压缩（compaction）：长对话自动压缩早期内容，控制 token 增长
3. Token 成本追踪：每会话/每次调用的 token 消耗记录
4. 分场景 Temperature：面试对话 0.4 / 开场白 0.6
"""

import uuid
import time
from fastapi import APIRouter, HTTPException
from app.models.schemas import (
    PracticeStartRequest,
    PracticeStartResponse,
    PracticeMessageRequest,
    PracticeMessageResponse,
    PracticeEndRequest,
    FeedbackResponse,
)
from app.data.scenes import get_scene_by_id
from app.services.llm import (
    generate,
    build_interviewer_system_prompt,
    compact_for_continuation,
)
from app.services.rag import retrieve
from app.services.evaluator import evaluate_session
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/practice", tags=["practice"])

_sessions: dict[str, dict] = {}


@router.post("/start", response_model=PracticeStartResponse)
async def start_practice(req: PracticeStartRequest):
    """开始练习会话 — v2：不在开始时做 RAG，保持 system prompt 精简"""
    scene = get_scene_by_id(req.scene_id)
    if scene is None:
        raise HTTPException(status_code=404, detail=f"场景不存在: {req.scene_id}")

    session_id = str(uuid.uuid4())[:8]

    # 构建精简的 system prompt（不含 RAG 知识）
    system_prompt = build_interviewer_system_prompt(
        interviewer_role=scene.interviewer_role,
        scene_description=scene.description,
        difficulty_hint=f"难度 {scene.difficulty}",
        rag_context="",  # 不在这里注入 RAG
    )

    # 生成开场白（稍高温度，让开场白多样化）
    opening, usage_start = generate(
        prompt="请以面试官身份发出第一道题目或开场白。简洁、自然。",
        system_prompt=system_prompt,
        temperature=0.6,
        max_tokens=256,
    )

    # 初始化会话
    _sessions[session_id] = {
        "scene": scene,
        "system_prompt_base": system_prompt,  # 基础 system prompt（不含 RAG）
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "assistant", "content": opening},
        ],
        "round": 1,
        "total_tokens": usage_start["input"] + usage_start["output"],
        "token_log": [{"action": "start", **usage_start}],
        "rag_used": False,
        "created_at": time.time(),
    }

    logger.info(
        f"会话 {session_id} 开始 | 场景: {scene.title} | "
        f"开场token: {usage_start['input']}+{usage_start['output']}"
    )

    return PracticeStartResponse(
        session_id=session_id,
        scene=scene,
        opening_message=opening,
    )


@router.post("/message", response_model=PracticeMessageResponse)
async def send_message(req: PracticeMessageRequest):
    """
    发送消息 — v2 核心改进：
    1. 每轮做轻量 RAG 检索（基于用户最新消息），按需注入知识
    2. 对话超过 6 条时自动 compaction，控制上下文长度
    3. 使用面试专用 temperature（0.4）
    """
    session = _sessions.get(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    scene = session["scene"]

    # 记录用户消息
    session["messages"].append({"role": "user", "content": req.message})

    # ═══ 渐进压缩（compaction） ═══
    # 当消息超过阈值时，压缩早期对话为摘要
    if len(session["messages"]) > 10:
        logger.info(f"会话 {req.session_id} 触发 compaction (消息数: {len(session['messages'])})")
        session["messages"] = compact_for_continuation(
            session["messages"], keep_recent=3
        )

    # ═══ Just-in-time RAG ═══
    # 基于用户最新回答检索相关知识，而非一开始就带全部知识库
    rag_context = ""
    if session["round"] <= 3 or session["round"] % 3 == 1:
        # 前3轮或每3轮做一次轻量检索
        rag_context = retrieve(
            scene_id=scene.id,
            query=req.message,  # 用用户的真实回答作为检索 query
            k=2,  # 只检索 2 条，保持精简
        )
        if rag_context:
            session["rag_used"] = True
            logger.debug(f"会话 {req.session_id} 第{session['round']}轮 RAG检索成功")

    # 构建本轮使用的 system prompt（动态注入 RAG）
    current_system_prompt = build_interviewer_system_prompt(
        interviewer_role=scene.interviewer_role,
        scene_description=scene.description,
        difficulty_hint=f"当前是第{session['round']}轮对话，{'请保持追问深度' if session['round'] <= 5 else '在2-3轮内自然收尾'}",
        rag_context=rag_context,
    )

    # ═══ 生成回复 ═══
    # 面试对话用 0.4 temperature（保持角色一致性，略有变化）
    reply, usage_msg = generate(
        prompt=req.message,
        system_prompt=current_system_prompt,
        temperature=0.4,
        max_tokens=256,
    )

    # 记录 AI 回复和 token
    session["messages"].append({"role": "assistant", "content": reply})
    session["round"] += 1
    session["total_tokens"] += usage_msg["input"] + usage_msg["output"]
    session["token_log"].append({
        "action": f"message_r{session['round']}",
        "rag_used": bool(rag_context),
        "compacted": len(session["messages"]) > 10,
        "total_msgs": len(session["messages"]),
        **usage_msg,
    })

    logger.info(
        f"会话 {req.session_id} 第{session['round']}轮 | "
        f"tokens: +{usage_msg['input']}/{usage_msg['output']} | "
        f"累计: {session['total_tokens']} | "
        f"RAG: {'✓' if rag_context else '✗'} | "
        f"压缩: {'✓' if len(session['messages']) > 10 else '✗'}"
    )

    return PracticeMessageResponse(
        session_id=req.session_id,
        reply=reply,
        current_round=session["round"],
    )


@router.post("/end", response_model=FeedbackResponse)
async def end_practice(req: PracticeEndRequest):
    """结束练习 — v2：压缩对话后评估 + 返回 token 统计"""
    session = _sessions.get(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    scene = session["scene"]

    # 生成反馈（evaluator 内部会先压缩对话）
    feedback, usage_eval = evaluate_session(
        session_id=req.session_id,
        scene_title=scene.title,
        messages=session["messages"],
    )
    session["total_tokens"] += usage_eval.get("input", 0) + usage_eval.get("output", 0)
    session["token_log"].append(usage_eval)

    # 输出完整的 token 统计
    logger.info(
        f"会话 {req.session_id} 结束 | "
        f"总轮数: {session['round']} | "
        f"总token: {session['total_tokens']} | "
        f"RAG使用: {session['rag_used']} | "
        f"用时: {time.time() - session['created_at']:.0f}秒\n"
        f"Token明细: {session['token_log']}"
    )

    # 清理会话
    del _sessions[req.session_id]

    return FeedbackResponse(
        session_id=req.session_id,
        feedback=feedback,
    )
