"""LLM 服务层 —— 封装 OpenAI 兼容 API 调用"""

from openai import OpenAI
from app.config import LLM_API_KEY, LLM_API_BASE, LLM_MODEL, LLM_TEMPERATURE
import json
import re

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_API_BASE)
    return _client


def generate(
    prompt: str,
    system_prompt: str = "",
    temperature: float = LLM_TEMPERATURE,
    max_tokens: int = 2048,
) -> str:
    """通用 LLM 生成方法"""
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
        return response.choices[0].message.content or ""
    except Exception as e:
        raise RuntimeError(f"LLM 调用失败: {e}")


def generate_json(
    prompt: str,
    system_prompt: str = "",
    temperature: float = 0.3,
    max_tokens: int = 2048,
) -> dict:
    """生成 JSON 格式输出"""
    raw = generate(prompt, system_prompt, temperature, max_tokens)
    # 尝试提取 JSON
    raw = raw.strip()
    # 去掉可能的 markdown 代码块标记
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # 尝试从文本中提取第一个 JSON 对象
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        raise RuntimeError(f"LLM 未返回有效 JSON。原始输出: {raw[:500]}")


# ── 场景 Prompt 构建 ──────────────────────


def build_interviewer_system_prompt(
    interviewer_role: str,
    scene_description: str,
    rag_context: str = "",
) -> str:
    """构建面试官 System Prompt"""
    prompt = f"""你是一个专业的{interviewer_role}，正在进行一场真实的面试/模拟练习。

## 你的角色
{scene_description}

## 行为准则
1. **保持角色一致性**：始终以{interviewer_role}的身份说话，不要跳出角色
2. **追问深挖**：对用户的回答进行 1-2 层追问，考察思考深度
3. **营造真实压力**：适当提出质疑或反例，但不要恶意刁难
4. **控制节奏**：每轮只问一个问题，不要一次性抛出多个问题
5. **适时收尾**：在 5-8 轮对话后，自然地结束面试

## 参考知识
{rag_context if rag_context else "（无额外参考资料，请基于你的通用知识进行面试）"}

## 开始
现在开始面试。请以{interviewer_role}的身份发出第一道题目或开场白。"""
    return prompt


def build_feedback_prompt(messages: list[dict]) -> str:
    """构建反馈评估 Prompt"""
    conversation = "\n".join(
        f"[{m['role']}]: {m['content']}" for m in messages
    )

    prompt = f"""你是一位资深的面试教练。请根据以下对话记录，对候选人的表现进行结构化评估。

## 对话记录
{conversation}

## 评估要求
请从以下 4 个维度评分（0-5 分，精确到 0.5），并给出具体点评：

1. **逻辑结构**：回答是否有清晰的结构（总分总/STAR/金字塔），是否逻辑自洽
2. **专业深度**：是否展现了足够的行业知识和思考深度，是否引用了方法论或数据
3. **表达清晰度**：语言是否流畅、简洁、准确，是否避免了模糊和啰嗦
4. **临场应变**：面对追问时是否能灵活应对，态度是否从容

还需输出：
- strengths: 2-3 个亮点
- improvements: 2-3 个具体改进建议
- summary: 一段 50 字左右的总结评语

请严格以 JSON 格式返回（不要包含 markdown 代码块标记）:
{{
  "overall_score": 3.5,
  "dimensions": [
    {{"name": "逻辑结构", "score": 4.0, "comment": "..."}},
    {{"name": "专业深度", "score": 3.0, "comment": "..."}},
    {{"name": "表达清晰度", "score": 3.5, "comment": "..."}},
    {{"name": "临场应变", "score": 3.5, "comment": "..."}}
  ],
  "strengths": ["...", "..."],
  "improvements": ["...", "..."],
  "summary": "..."
}}"""
    return prompt
