"""反馈评估服务 —— 生成结构化面试反馈"""

from app.services.llm import generate_json, build_feedback_prompt
from app.models.schemas import Feedback, DimensionScore
import logging

logger = logging.getLogger(__name__)


def evaluate_session(
    session_id: str,
    scene_title: str,
    messages: list[dict],
) -> Feedback:
    """评估一个练习会话，返回结构化反馈"""

    if not messages or len(messages) < 2:
        # 对话太少，返回默认反馈
        return Feedback(
            session_id=session_id,
            scene_title=scene_title,
            overall_score=2.5,
            dimensions=[
                DimensionScore(name="逻辑结构", score=2.5, comment="对话次数太少，无法给出准确评估。建议至少完成 3 轮对话。"),
                DimensionScore(name="专业深度", score=2.5, comment="对话次数太少，无法给出准确评估。"),
                DimensionScore(name="表达清晰度", score=2.5, comment="对话次数太少，无法给出准确评估。"),
                DimensionScore(name="临场应变", score=2.5, comment="对话次数太少，无法给出准确评估。"),
            ],
            strengths=["（对话次数不足，建议重新练习）"],
            improvements=["至少完成 5 轮以上对话，以获得准确的反馈评估"],
            summary="这次练习的对话轮次较少，建议重新进行一次完整的模拟练习，以便 AI 教练能给出更有价值的反馈。",
        )

    prompt = build_feedback_prompt(messages)

    try:
        data = generate_json(prompt)
    except Exception as e:
        logger.error(f"反馈生成失败: {e}")
        # 降级：返回一个基础反馈
        return Feedback(
            session_id=session_id,
            scene_title=scene_title,
            overall_score=3.0,
            dimensions=[
                DimensionScore(name="逻辑结构", score=3.0, comment="（评估服务暂时异常，此为降级反馈）"),
                DimensionScore(name="专业深度", score=3.0, comment="（评估服务暂时异常，此为降级反馈）"),
                DimensionScore(name="表达清晰度", score=3.0, comment="（评估服务暂时异常，此为降级反馈）"),
                DimensionScore(name="临场应变", score=3.0, comment="（评估服务暂时异常，此为降级反馈）"),
            ],
            strengths=["完成了本次练习"],
            improvements=["评估服务暂时异常，建议稍后重试"],
            summary="评估服务暂时出现了异常，但这不影响你的练习。建议稍后重新结束练习以获取完整反馈。",
        )

    dimensions = [
        DimensionScore(
            name=d["name"],
            score=float(d["score"]),
            comment=d.get("comment", ""),
        )
        for d in data.get("dimensions", [])
    ]

    return Feedback(
        session_id=session_id,
        scene_title=scene_title,
        overall_score=float(data.get("overall_score", 3.0)),
        dimensions=dimensions,
        strengths=data.get("strengths", []),
        improvements=data.get("improvements", []),
        summary=data.get("summary", "练习完成。"),
    )
