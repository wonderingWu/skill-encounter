"""LLM 服务层 —— 基于 Anthropic Context Engineering 最佳实践重构

核心改进（v2）:
1. XML 标签结构化 Prompt（Anthropic 推荐，防止长上下文中指令衰减）
2. 分场景 Temperature（面试对话 0.4 / 反馈评估 0.2 / 开场白 0.6）
3. Token 成本追踪（每次调用记录 input/output tokens）
4. 对话压缩 compaction（避免 token 成本线性增长）
5. Just-in-time RAG 注入（不从开始就带全部知识库）
"""

from __future__ import annotations

from openai import OpenAI
from app.config import LLM_API_KEY, LLM_API_BASE, LLM_MODEL
import json
import re
import logging

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_API_BASE)
    return _client


# ── 核心生成方法（带 token 追踪） ──────────

def generate(
    prompt: str,
    system_prompt: str = "",
    temperature: float = 0.4,
    max_tokens: int = 1024,
) -> tuple[str, dict]:
    """
    通用 LLM 生成，返回 (文本, token_usage)
    token_usage = {"input": int, "output": int}
    """
    client = _get_client()
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        text = response.choices[0].message.content or ""
        usage = {
            "input": response.usage.prompt_tokens if response.usage else 0,
            "output": response.usage.completion_tokens if response.usage else 0,
        }
        return text, usage
    except Exception as e:
        raise RuntimeError(f"LLM 调用失败: {e}")


def generate_json(
    prompt: str,
    system_prompt: str = "",
    temperature: float = 0.2,
    max_tokens: int = 1024,
) -> tuple[dict, dict]:
    """生成 JSON 格式输出，返回 (dict, token_usage)"""
    raw, usage = generate(prompt, system_prompt, temperature, max_tokens)
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw), usage
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group()), usage
            except json.JSONDecodeError:
                pass
        raise RuntimeError(f"LLM 未返回有效 JSON。原始输出: {raw[:300]}")


# ── XML 结构化 System Prompt（Anthropic 推荐格式） ───

def build_interviewer_system_prompt(
    interviewer_role: str,
    scene_description: str,
    difficulty_hint: str = "",
    rag_context: str = "",
) -> str:
    """
    使用 XML 标签分隔不同语义区域，防止长上下文中关键指令衰减。
    rag_context 只在需要时才注入（just-in-time），而非会话开始就固定。
    """
    prompt_parts = [
        "<role>",
        f"你是{interviewer_role}，正在对一位校招候选人进行真实的模拟面试。",
        f"场景：{scene_description}",
        "</role>",
        "",
        "<behavior_rules>",
        "1. 角色一致性：始终以面试官身份说话，绝不跳出角色说「作为AI助手」之类的话",
        "2. 单问原则：每轮只问一个问题，不要一次抛出多个问题",
        "3. 追问深度：对回答进行1-2层追问，考察思考深度",
        "4. 适度压力：可提出质疑或追问细节，但不要恶意刁难",
        "5. 自然收尾：5-8轮对话后自然结束，可以这样说：「好的，这一轮面试就到这里，请问你有什么想问我的吗？」",
        "6. 简洁回复：每次回复控制在50-150字，像真人面试官一样精炼",
        "</behavior_rules>",
    ]

    if difficulty_hint:
        prompt_parts.extend([
            "",
            "<difficulty_guidance>",
            f"当前练习难度：{difficulty_hint}",
            "</difficulty_guidance>",
        ])

    if rag_context:
        prompt_parts.extend([
            "",
            "<reference_knowledge>",
            "以下是本次面试可参考的背景知识，用来让你的提问更专业：",
            rag_context,
            "</reference_knowledge>",
        ])

    prompt_parts.extend([
        "",
        "<output_format>",
        "只输出面试内容本身，不要加任何前缀（如「面试官：」）或后缀说明。",
        "像真人说话一样自然、简洁。",
        "</output_format>",
    ])

    return "\n".join(prompt_parts)


def build_feedback_prompt(messages: list[dict]) -> str:
    """构建反馈评估 Prompt（v2：先压缩再评估）"""
    # 先压缩对话
    compacted = _compact_conversation(messages)

    prompt = f"""<task>
你是资深面试教练。请根据以下对话摘要，对候选人的表现进行结构化评估。
</task>

<conversation_summary>
{compacted}
</conversation_summary>

<evaluation_criteria>
从4个维度评分(0-5分，精确到0.5)，给出具体点评：
1. 逻辑结构：回答是否有清晰结构(总分总/STAR/金字塔)，是否逻辑自洽
2. 专业深度：是否展现足够行业知识和思考深度，是否引用方法论或数据
3. 表达清晰度：语言是否流畅、简洁、准确
4. 临场应变：面对追问时是否灵活应对，态度是否从容
</evaluation_criteria>

<output_requirements>
输出严格JSON(不要markdown代码块标记):
{{
  "overall_score": 3.5,
  "dimensions": [
    {{"name": "逻辑结构", "score": 4.0, "comment": "..."}},
    {{"name": "专业深度", "score": 3.0, "comment": "..."}},
    {{"name": "表达清晰度", "score": 3.5, "comment": "..."}},
    {{"name": "临场应变", "score": 3.5, "comment": "..."}}
  ],
  "strengths": ["亮点1", "亮点2"],
  "improvements": ["改进1", "改进2"],
  "summary": "50字左右总结评语"
}}
</output_requirements>"""
    return prompt


# ── 对话压缩（compaction，Anthropic 推荐） ───

def _compact_conversation(messages: list[dict]) -> str:
    """
    将完整对话压缩为结构化摘要。
    只保留：面试官问什么 + 候选人核心观点 + 追问内容。
    丢弃：冗余表达、开场白、过渡语句。
    """
    # 过滤掉 system 消息
    dialog = [m for m in messages if m["role"] != "system"]

    if len(dialog) <= 4:
        # 对话很短，不需要压缩
        return "\n".join(f"[{m['role']}]: {m['content'][:200]}" for m in dialog)

    # 构建压缩摘要
    lines = []
    qa_pairs = []
    current_q = None

    for m in dialog:
        if m["role"] == "assistant":
            current_q = m["content"][:150]
        elif m["role"] == "user" and current_q:
            qa_pairs.append({
                "q": current_q,
                "a": m["content"][:200],
            })
            current_q = None

    lines.append(f"对话共 {len(qa_pairs)} 轮问答，摘要如下：\n")
    for i, pair in enumerate(qa_pairs, 1):
        lines.append(f"第{i}轮 — 面试官问: {pair['q']}")
        lines.append(f"候选人答: {pair['a']}\n")

    return "\n".join(lines)


def compact_for_continuation(messages: list[dict], keep_recent: int = 3) -> list[dict]:
    """
    为长对话做 compaction，返回压缩后的消息列表。
    保留最近 keep_recent 轮的完整对话，更早的压缩为摘要。
    用于防止 token 成本随对话线性增长。
    """
    if len(messages) <= 6:
        return messages

    # 分离 system prompt 和对话
    system_msgs = [m for m in messages if m["role"] == "system"]
    dialog = [m for m in messages if m["role"] != "system"]

    # 最近 N 轮保留完整（N*2 条消息 = N个问答对）
    recent_count = keep_recent * 2
    recent = dialog[-recent_count:] if len(dialog) > recent_count else dialog
    older = dialog[:-recent_count] if len(dialog) > recent_count else []

    result = list(system_msgs)

    if older:
        summary = _compact_conversation(older)
        result.append({
            "role": "system",
            "content": f"<conversation_history_summary>\n前{len(older)//2}轮对话摘要：\n{summary}\n</conversation_history_summary>"
        })

    result.extend(recent)
    return result
