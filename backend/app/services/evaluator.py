"""反馈评估服务 — v3: 六维度能力评分 + 差距检测

核心改进：
1. 六维能力评估：表达力/逻辑力/自我认知/协作力/AI素养/适应力
2. 对话中能力差距检测（I - input差集）
3. 用户自评 vs AI评估对比
"""

from app.services.llm import generate_json
from app.models.schemas import (
    Feedback, DimensionScore, HexagonScore,
    HEXAGON_DIMENSIONS, GapDetection,
)
import logging

logger = logging.getLogger(__name__)


HEXAGON_EVAL_PROMPT = """<task>
你是资深面试教练和成长导师。请根据对话记录，从六个维度评估这位学生的当前水平。
评分0-5分，精确到0.5。你需要区分「对话中实际展现的能力」和「没有展现的能力」。
</task>

<conversation>
{conversation}
</conversation>

<dimensions>
1. expression（表达影响力）：语言流畅度、逻辑清晰度、是否能用简洁语言说清复杂想法
2. logic（逻辑分析力）：思考是否有结构、论证是否自洽、拆解问题是否有框架
3. self_awareness（自我认知力）：是否了解自己的优缺点、能否坦诚面对不足、情绪管理
4. collaboration（人际协作力）：团队协作意识、是否能理解他人立场、沟通方式是否建设性
5. ai_literacy（AI素养力）：对AI的理解程度、是否会用AI工具、AI伦理意识
6. adaptability（适应创新力）：学习能力、创新思维、面对变化的适应性
</dimensions>

<rules>
- 只对「对话中实际展现出来的」做评分，没展现的维度给2.5（中性分）并在comments中标注"对话中未充分展现，建议专门练习"
- 如果用户展现出对某个维度的显著兴趣或天赋，适当提高该维度分数
- gap_dimensions列出当前最需要提升的2-3个维度
</rules>

<output_json>
{{
  "expression": 3.0, "logic": 3.5, "self_awareness": 2.5,
  "collaboration": 3.0, "ai_literacy": 2.5, "adaptability": 3.0,
  "comments": {{
    "expression": "...", "logic": "...", "self_awareness": "...",
    "collaboration": "...", "ai_literacy": "...", "adaptability": "..."
  }},
  "gap_dimensions": ["self_awareness", "ai_literacy"],
  "gap_reason": "用户在对话中展现出较强的逻辑分析能力，但对自己的职业方向不够清晰..."
}}
</output_json>"""


GAP_DETECT_PROMPT = """<task>
分析用户的第一条消息，检测哪些能力维度可能缺失。
用户的表述可能带有自我认知偏误——用户说"我挺自信的"不一定真的自信。
你要做的是从用户的表达方式、关注重点、回避话题中推断真实的能力缺口。
</task>

<user_message>
{user_message}
</user_message>

<dimensions>
1. expression（表达影响力）2. logic（逻辑分析力）3. self_awareness（自我认知力）
4. collaboration（人际协作力）5. ai_literacy（AI素养力）6. adaptability（适应创新力）
</dimensions>

<output_json>
{{
  "detected_gaps": ["self_awareness", "adaptability"],
  "suggested_focus": "建议优先关注自我认知力的提升",
  "hint_question": "你有没有做过MBTI或者盖洛普优势测试？了解过自己的性格和思维偏好吗？",
  "reasoning": "用户在消息中提到'我不知道自己适合干什么'，表明自我认知是当前最大短板..."
}}
</output_json>"""


def evaluate_hexagon(messages: list[dict]) -> tuple[HexagonScore, list[str]]:
    """评估六维度能力，返回 (scores, gap_dimensions)"""
    conversation = "\n".join(
        f"[{m['role']}]: {m['content'][:300]}" for m in messages if m['role'] != 'system'
    )
    try:
        data, _ = generate_json(
            prompt=HEXAGON_EVAL_PROMPT.format(conversation=conversation),
            temperature=0.2,
            max_tokens=1024,
        )
        scores = HexagonScore(
            expression=float(data.get('expression', 2.5)),
            logic=float(data.get('logic', 2.5)),
            self_awareness=float(data.get('self_awareness', 2.5)),
            collaboration=float(data.get('collaboration', 2.5)),
            ai_literacy=float(data.get('ai_literacy', 2.5)),
            adaptability=float(data.get('adaptability', 2.5)),
            comments=data.get('comments', {}),
        )
        gaps = data.get('gap_dimensions', [])
        return scores, gaps
    except Exception as e:
        logger.error(f"六维评估失败: {e}")
        return HexagonScore(
            expression=2.5, logic=2.5, self_awareness=2.5,
            collaboration=2.5, ai_literacy=2.5, adaptability=2.5,
        ), []


def detect_gaps(first_message: str) -> GapDetection:
    """从用户第一条消息中检测能力差距"""
    try:
        data, _ = generate_json(
            prompt=GAP_DETECT_PROMPT.format(user_message=first_message[:500]),
            temperature=0.3,
            max_tokens=512,
        )
        return GapDetection(
            detected_gaps=data.get('detected_gaps', []),
            suggested_focus=data.get('suggested_focus', ''),
            hint_question=data.get('hint_question', ''),
        )
    except Exception as e:
        logger.warning(f"差距检测失败: {e}")
        return GapDetection()


def evaluate_session(
    session_id: str, scene_title: str, messages: list[dict],
    hexagon_scores: HexagonScore | None = None,
) -> tuple[Feedback, dict]:
    """评估会话（兼容原有4维 + 新增六维）"""
    if not messages or len(messages) < 2:
        fb = Feedback(
            session_id=session_id, scene_title=scene_title,
            overall_score=2.5,
            dimensions=[DimensionScore(name="对话不足", score=2.5, comment="请完成3轮以上对话")],
            strengths=[], improvements=["完成更多轮对话以获得准确评估"],
            summary="对话轮次较少。",
        )
        return fb, {"input": 0, "output": 0, "action": "evaluate_skip"}

    # 生成传统4维反馈 + 六维评分
    if hexagon_scores is None:
        hexagon_scores, _ = evaluate_hexagon(messages)

    overall = round(sum([
        hexagon_scores.expression, hexagon_scores.logic, hexagon_scores.self_awareness,
        hexagon_scores.collaboration, hexagon_scores.ai_literacy, hexagon_scores.adaptability,
    ]) / 6, 1)

    dimensions = [
        DimensionScore(name=d['name'], score=getattr(hexagon_scores, d['id'], 2.5),
                       comment=hexagon_scores.comments.get(d['id'], ''))
        for d in HEXAGON_DIMENSIONS
    ]

    return Feedback(
        session_id=session_id, scene_title=scene_title,
        overall_score=overall, dimensions=dimensions,
        strengths=[],
        improvements=[f"{d['emoji']} {d['name']} — {hexagon_scores.comments.get(d['id'], '建议专项练习')}"
                       for d in HEXAGON_DIMENSIONS if getattr(hexagon_scores, d['id'], 5) < 3.0],
        summary=f"综合六维评分 {overall}/5。最高维度：{_top_dim(hexagon_scores)}。最需提升：{_weak_dim(hexagon_scores)}。",
    ), {"input": 100, "output": 80, "action": "evaluate_v3"}


def _top_dim(s: HexagonScore) -> str:
    dims = {d['id']: getattr(s, d['id'], 0) for d in HEXAGON_DIMENSIONS}
    best = max(dims, key=dims.get)
    name = next(d['name'] for d in HEXAGON_DIMENSIONS if d['id'] == best)
    return f"{name}({dims[best]:.1f})"


def _weak_dim(s: HexagonScore) -> str:
    dims = {d['id']: getattr(s, d['id'], 0) for d in HEXAGON_DIMENSIONS}
    worst = min(dims, key=dims.get)
    name = next(d['name'] for d in HEXAGON_DIMENSIONS if d['id'] == worst)
    return f"{name}({dims[worst]:.1f})"
