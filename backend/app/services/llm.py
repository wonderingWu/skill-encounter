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
    history: list[dict] | None = None,
) -> tuple[str, dict]:
    """
    通用 LLM 生成，返回 (文本, token_usage)
    token_usage = {"input": int, "output": int}
    history: 可选，之前的对话历史 [{role, content}, ...]
    """
    client = _get_client()
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if history:
        messages.extend(history)
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


# ── 双格式 System Prompt（自动适配模型） ───

def build_interviewer_system_prompt(
    interviewer_role: str,
    scene_description: str,
    difficulty_hint: str = "",
    rag_context: str = "",
    coach_context: str = "",
) -> str:
    """
    自动检测模型类型，生成适配的 system prompt。
    - Claude/GPT 系列 → XML 结构化格式（Anthropic 最佳实践）
    - GLM/其他 → 精简直接格式（GLM 对长 prompt 注意力分散）
    """
    from app.config import LLM_MODEL as _m

    if any(x in _m.lower() for x in ("claude", "gpt", "o1", "o3", "o4")):
        return _build_xml_prompt(interviewer_role, scene_description, difficulty_hint, rag_context, coach_context)
    else:
        return _build_compact_prompt(interviewer_role, scene_description, difficulty_hint, rag_context, coach_context)


def _build_compact_prompt(role: str, desc: str, hint: str, rag: str, coach: str) -> str:
    """精简 prompt —— 适合 GLM 等对长上下文中指令容易丢失的模型"""
    # 判断场景类型来决定角色描述
    is_speech = "演讲" in role or "演讲" in desc
    is_debate = "辩论" in role or "辩论" in desc
    if is_speech:
        scene_role_line = f"你现在是{role}，正在指导一位学员进行演讲练习。"
    elif is_debate:
        scene_role_line = f"你现在是{role}，正在和一位学员进行辩论对练。"
    else:
        scene_role_line = f"你现在是{role}，正在面试一位校招候选人。"
    parts = [scene_role_line, f"场景：{desc}"]
    if coach:
        parts.extend(["", "【你的人格——这是你最核心的设定，优先级高于一切规则】", coach])
    parts.extend([
        "",
        "【规则】",
        "- 绝不说「作为AI助手」「根据我的训练数据」",
        "- 对方回应后你再说话，不要连发多条",
        "- 追问可以，但你也要给干货——每问2-3次至少分享一次你的观察或建议",
        "- 必须指出问题。不批评=失职",
        "- 不要假设用户要应聘什么岗位。如果不清楚，先问",
        "- 每次50-200字",
        "- 5-8轮后自然结束",
    ])
    if hint:
        parts.append(f"- {hint}")
    if rag:
        parts.append(f"\n【专业知识——必须据此提问】\n{rag}")
    parts.append("\n现在请发出你的第一句话。自然、简洁。")
    return "\n".join(parts)


def _build_xml_prompt(role: str, desc: str, hint: str, rag: str, coach: str) -> str:
    """XML 结构化 prompt —— Anthropic 最佳实践，适合 Claude/GPT"""
    parts = [
        "<role>",
        f"你是{role}，正在对一位校招候选人进行真实的模拟面试。",
        f"场景：{desc}",
        "</role>",
    ]
    if coach:
        parts.extend(["", "<persona>", coach, "</persona>"])
    parts.extend([
        "",
        "<behavior_rules>",
        "1. 角色一致性：以面试官身份说话，绝不跳出角色",
        "2. 单问原则：每轮只问一个问题",
        "3. 追问深度：对回答进行1-2层追问，回答敷衍时必须追问",
        "4. 必须质疑：用户回答有问题、矛盾或不充分时，必须指出。不批评就是失职",
        "5. 不哄人：用户说错了就说错了，不用「你说得也有道理」糊弄",
        "6. 自然收尾：5-8轮后自然结束",
        "7. 简洁回复：每次50-150字",
        "</behavior_rules>",
    ])
    if hint:
        parts.extend(["", f"<difficulty>{hint}</difficulty>"])
    if rag:
        parts.extend(["", f"<knowledge>{rag}</knowledge>"])
    parts.extend(["", "<format>只输出面试内容，不加前缀后缀。像真人说话。</format>"])
    return "\n".join(parts)




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
