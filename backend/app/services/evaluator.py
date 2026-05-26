"""反馈评估服务 — v4: 六维度能力评分 + 差距检测 + 框架发现

核心改进：
1. 六维能力评估：表达力/逻辑力/自我认知/协作力/AI素养/适应力
2. 对话中能力差距检测（I - input差集）
3. 用户自评 vs AI评估对比
4. v4 新增：对话后框架发现 — 识别用户自然使用的思维框架，不给对话增加压力
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
  "strengths": ["亮点1", "亮点2"],
  "improvements": ["改进1", "改进2"],
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


def evaluate_hexagon(messages: list[dict]) -> tuple[HexagonScore, list[str], list[str], list[str], dict]:
    """评估六维度能力，返回 (scores, gaps, strengths, improvements, token_usage)"""
    conversation = "\n".join(
        f"[{m['role']}]: {m['content'][:300]}" for m in messages if m['role'] != 'system'
    )
    try:
        data, usage = generate_json(
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
        strengths = data.get('strengths', [])
        improvements = data.get('improvements', [])
        return scores, gaps, strengths, improvements, usage
    except Exception as e:
        logger.error(f"六维评估失败: {e}")
        return HexagonScore(
            expression=2.5, logic=2.5, self_awareness=2.5,
            collaboration=2.5, ai_literacy=2.5, adaptability=2.5,
        ), [], [], [], {"input": 0, "output": 0}


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


# ── v4: 对话后框架发现 ──

KNOWN_FRAMEWORKS = {
    "STAR": "情境→任务→行动→结果：你讲述经历时自然地用了这个结构，先说背景再说你做了什么最后说结果。这是面试中最经典的行为面试框架。",
    "PREP": "观点→理由→例子→回扣：你在表达观点时先亮观点、再说理由、举例子、最后回扣主题。这是即兴演讲的高效结构。",
    "ARE": "断言→推理→证据：你在论证立场时先断言、再推理、给证据。这是结构化辩论的核心。",
    "金字塔原理": "结论先行→分层论证：你先说了核心结论，再逐层展开论据。这是麦肯锡顾问的标准表达方式。",
    "第一性原理": "回归基本事实：你没有接受表面的答案，而是追问最底层的原因。这是马斯克推崇的思维方法。",
    "MECE": "不重不漏的分类：你在分析问题时，拆解的方式做到了相互独立、完全穷尽。",
    "SCQA": "情境→冲突→问题→答案：你的讲述有故事感——先交代背景，再说矛盾，然后引出问题，最后给出方案。",
    "SBI": "情境→行为→影响：你在给反馈时先说了具体情境，再描述行为，最后说影响。这是组织心理学中最有效的反馈模型。",
    "对比论证": "正反对比：你通过比较两个方案的优劣来论证你的观点，这是有说服力的论证方式。",
    "因果链": "因果推理：你的思考有明显的因果链条——因为A所以B因此C。这是逻辑严谨的标志。",
}

PATTERN_DETECT_PROMPT = """<task>
你是思维模式分析专家。阅读以下对话记录，识别用户在表达中**自然使用**的思维框架。
注意：你是在描述用户已经展现的模式，不是在教用户。别说「你应该学XX」，说「你刚才用了XX」。
</task>

<conversation>
{conversation}
</conversation>

<known_frameworks>
{framework_list}
</known_frameworks>

<rules>
- 只列出用户**确实在对话中展现了**的框架，不要臆测
- 每个发现的框架，引用一句用户的**原话**作为证据
- 如果用户没有展现任何框架，返回空列表——不要编造
- frameworks_discovered 是框架名列表，patterns_used 是框架名→{explanation, evidence}的映射
- 最多列出3个框架，按展现清晰度排序
</rules>

<output_json>
{{
  "frameworks_discovered": ["STAR"],
  "patterns_used": {{
    "STAR": {{
      "explanation": "你在讲社团招新经历时，先描述了当时只剩3个人的情境，然后说目标是招20人，接着具体讲了你做海报、扫楼、办体验日三步，最后给出招到73人的结果——这是典型的STAR结构。",
      "evidence": "用户原话：'上一届走了以后只剩3个人，秋季学期要招20个新人，时间只有两周。我带着剩下的3个人设计了招新方案……最后招了73人。'"
    }}
  }}
}}
</output_json>"""


def detect_patterns_used(messages: list[dict]) -> tuple[list[str], dict[str, dict], dict]:
    """
    对话后分析：识别用户自然使用的思维框架。
    返回 (frameworks_discovered, patterns_used, token_usage)
    - frameworks_discovered: ["STAR", "金字塔原理"]
    - patterns_used: {"STAR": {"explanation": "...", "evidence": "..."}, ...}
    """
    conversation = "\n".join(
        f"[{m['role']}]: {m['content'][:300]}" for m in messages if m['role'] != 'system'
    )
    framework_list = "\n".join(
        f"- {name}: {desc[:100]}" for name, desc in KNOWN_FRAMEWORKS.items()
    )
    try:
        data, usage = generate_json(
            prompt=PATTERN_DETECT_PROMPT.format(
                conversation=conversation,
                framework_list=framework_list,
            ),
            temperature=0.3,
            max_tokens=1024,
        )
        frameworks = data.get('frameworks_discovered', [])
        patterns = data.get('patterns_used', {})

        # 大小写不敏感匹配 + 过滤
        def _match_fw(name: str) -> str | None:
            for k in KNOWN_FRAMEWORKS:
                if k.lower() == name.lower():
                    return k
            return None

        frameworks = [fn for f in frameworks if (fn := _match_fw(f))]
        patterns = {fn: v for k, v in patterns.items() if (fn := _match_fw(k))}

        # 双向补全：frameworks 中有但 patterns 中缺失 → 补空
        for f in frameworks:
            if f not in patterns:
                patterns[f] = {"explanation": "", "evidence": ""}

        return frameworks, patterns, usage
    except Exception as e:
        logger.warning(f"框架发现失败: {e}")
        return [], [], {"input": 0, "output": 0}


# ── 会话评估（v4 整合框架发现）──

def evaluate_session(
    session_id: str, scene_title: str, messages: list[dict],
    hexagon_scores: HexagonScore | None = None,
    strengths: list[str] | None = None,
    improvements: list[str] | None = None,
) -> tuple[Feedback, dict]:
    """评估会话（v4: 六维评分 + 框架发现）"""
    eval_usage = {"input": 0, "output": 0}

    if not messages or len(messages) < 2:
        fb = Feedback(
            session_id=session_id, scene_title=scene_title,
            overall_score=2.5,
            dimensions=[DimensionScore(name="对话不足", score=2.5, comment="请完成3轮以上对话")],
            strengths=[], improvements=["完成更多轮对话以获得准确评估"],
            summary="对话轮次较少。",
        )
        return fb, {"input": 0, "output": 0, "action": "evaluate_skip"}

    # 六维评分
    if hexagon_scores is None:
        hexagon_scores, _, strengths, improvements, eval_usage = evaluate_hexagon(messages)

    # v4: 框架发现（对话后分析，不增加对话压力）
    # 至少 6 条消息（3 轮用户发言）才有足够的对话内容做框架判断
    if len(messages) >= 6:
        frameworks, patterns, pattern_usage = detect_patterns_used(messages)
        eval_usage["input"] += pattern_usage.get("input", 0)
        eval_usage["output"] += pattern_usage.get("output", 0)
    else:
        frameworks, patterns, pattern_usage = [], [], {"input": 0, "output": 0}

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
        strengths=strengths or [],
        improvements=improvements or [
            f"{d['emoji']} {d['name']} — {hexagon_scores.comments.get(d['id'], '建议专项练习')}"
            for d in HEXAGON_DIMENSIONS if getattr(hexagon_scores, d['id'], 5) < 3.0
        ],
        summary=f"综合六维评分 {overall}/5。最高维度：{_top_dim(hexagon_scores)}。最需提升：{_weak_dim(hexagon_scores)}。",
        frameworks_discovered=frameworks,
        patterns_used=patterns,
    ), {"input": eval_usage.get("input", 0), "output": eval_usage.get("output", 0), "action": "evaluate_v4"}


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
