"""反馈评估服务 —— 基于 Anthropic Compaction 策略重构

v2 改进：
1. 先压缩对话再评估（节省 40-60% token）
2. 使用分场景 temperature（评估用 0.2 确保一致性）
3. 记录每次评估的 token 消耗
"""

from app.services.llm import generate_json, build_feedback_prompt
from app.models.schemas import Feedback, DimensionScore
import logging

logger = logging.getLogger(__name__)


def evaluate_session(
    session_id: str,
    scene_title: str,
    messages: list[dict],
) -> tuple[Feedback, dict]:
    """
    评估一个练习会话，返回 (Feedback, token_usage)
    token_usage = {"input": int, "output": int, "action": "evaluate"}
    """

    if not messages or len(messages) < 2:
        return Feedback(
            session_id=session_id,
            scene_title=scene_title,
            overall_score=2.5,
            dimensions=[
                DimensionScore(name="逻辑结构", score=2.5, comment="对话次数太少，建议至少完成3轮对话"),
                DimensionScore(name="专业深度", score=2.5, comment="对话次数太少，无法给出准确评估"),
                DimensionScore(name="表达清晰度", score=2.5, comment="对话次数太少，无法给出准确评估"),
                DimensionScore(name="临场应变", score=2.5, comment="对话次数太少，无法给出准确评估"),
            ],
            strengths=["（对话次数不足，建议重新练习）"],
            improvements=["至少完成5轮以上对话，以获得准确的反馈评估"],
            summary="对话轮次较少，建议重新进行一次完整的模拟练习。",
        ), {"input": 0, "output": 0, "action": "evaluate_skip"}

    prompt = build_feedback_prompt(messages)

    try:
        data, usage = generate_json(
            prompt=prompt,
            temperature=0.2,  # 评估需要一致性，低温度
            max_tokens=1024,
        )
        usage["action"] = "evaluate"
    except Exception as e:
        logger.error(f"反馈生成失败: {e}")
        return Feedback(
            session_id=session_id,
            scene_title=scene_title,
            overall_score=3.0,
            dimensions=[
                DimensionScore(name="逻辑结构", score=3.0, comment="（评估服务暂时异常）"),
                DimensionScore(name="专业深度", score=3.0, comment="（评估服务暂时异常）"),
                DimensionScore(name="表达清晰度", score=3.0, comment="（评估服务暂时异常）"),
                DimensionScore(name="临场应变", score=3.0, comment="（评估服务暂时异常）"),
            ],
            strengths=["完成了本次练习"],
            improvements=["评估服务暂时异常，建议稍后重试"],
            summary="评估服务暂时出现异常，但这不影响你的练习。建议稍后重新结束练习以获取完整反馈。",
        ), {"input": 0, "output": 0, "action": "evaluate_error"}

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
    ), usage
