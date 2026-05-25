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
            timeout=30,  # 30秒超时
        )
        text = response.choices[0].message.content or ""
        usage = {
            "input": response.usage.prompt_tokens if response.usage else 0,
            "output": response.usage.completion_tokens if response.usage else 0,
        }
        return text, usage
    except Exception as e:
        if "timeout" in str(e).lower() or "connection" in str(e).lower():
            logger.warning(f"LLM 调用超时，重试中: {e}")
            try:
                response = client.chat.completions.create(
                    model=LLM_MODEL, messages=messages,
                    temperature=temperature, max_tokens=max_tokens, timeout=30,
                )
                text = response.choices[0].message.content or ""
                usage = {"input": response.usage.prompt_tokens if response.usage else 0,
                         "output": response.usage.completion_tokens if response.usage else 0}
                return text, usage
            except Exception as e2:
                raise RuntimeError(f"LLM 调用失败（重试后仍失败）: {e2}")
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
    # 判断场景类型
    is_speech = "演讲" in role or "演讲" in desc
    is_debate = "辩论" in role or "辩论" in desc
    is_code = "代码评审" in role
    is_defense = "答辩" in role
    is_cs_scene = is_code or is_defense
    is_interview = not is_speech and not is_debate and not is_cs_scene

    if is_speech:
        scene_role_line = f"你现在是{role}，正在指导一位学员进行演讲练习。"
    elif is_debate:
        scene_role_line = f"你现在是{role}，正在和一位学员进行辩论对练。"
    elif is_code:
        scene_role_line = f"你现在是{role}，正在帮助一位程序员练习代码表达能力。"
    elif is_defense:
        scene_role_line = f"你现在是{role}，正在对一位学生的毕业设计/课程项目进行模拟答辩。"
    else:
        scene_role_line = f"你现在是{role}，正在面试一位校招候选人。"

    parts = [scene_role_line, f"场景：{desc}"]

    # CS 场景：精简教练人格，只保留说话风格，把 context window 留给技术知识
    if coach:
        if is_cs_scene:
            # CS 场景下教练人格降为简短风格指引
            coach_compact = _extract_speaking_style_only(coach)
            parts.extend(["", "【你的对话风格】", coach_compact])
        else:
            parts.extend(["", "【你的人格——这是你最核心的设定，优先级高于一切规则】", coach])

    parts.extend([
        "",
        "【规则】",
        "- 绝不说「作为AI助手」「根据我的训练数据」",
        "- 对方回应后你再说话，不要连发多条",
        "- 你不是一个只会提问的机器人。你是一个教练——先教方法，再让用户练，最后点评",
    ])

    # ── 面试场景：STAR 法则 ──
    if is_interview:
        parts.extend([
            "",
            "【本次教学任务：STAR法则】",
            "你今天的教学目标是让用户学会用STAR法则做自我介绍。严格按照以下阶段：",
            "",
            "阶段1-教学（第1轮）：",
            "- 直接说：「你好！我们今天练自我介绍。先教你一个方法叫STAR法则。」",
            "- 然后讲清楚：S=Situation情境、T=Task任务、A=Action行动、R=Result结果",
            "- 给一个具体的例子：「比如我大二在社团招新（S），目标是招50人（T），我做了三件事：设计海报、扫楼、办体验日（A），最后招了73人（R）。」",
            "- 不需要用户听完就马上练——问他「你有想用STAR讲的一段经历吗？或者我给你一个模拟场景？」",
            "",
            "阶段2-练习（第2-4轮）：",
            "- 用户用STAR讲完后，你追问1-2层：S够清楚吗？A有哪些具体动作？R有没有数据？",
            "- 如果用户的STAR不完整，指出来但不替他写——让他自己补",
            "- 第2轮后可以换一个场景让用户再练一次STAR",
            "",
            "阶段3-点评（第5轮）：",
            "- 总结：用户的STAR哪部分做得好，哪部分可以改进",
            "- 给一个具体的改进建议（不是笼统的「表达可以更清晰」）",
            "",
            "教学结束→自然收尾。不要在第1轮就开始追问用户的回答——先教。",
        ])

    # ── 演讲场景：PREP 框架 ──
    elif is_speech:
        parts.extend([
            "",
            "【本次教学任务：PREP演讲框架】",
            "你的教学目标是让用户学会用PREP组织演讲。严格按照以下阶段：",
            "",
            "阶段1-教学（第1轮）：",
            "- 直接说：「你好！今天练即兴演讲。先教你PREP法则。」",
            "- P=Point（先亮观点）、R=Reason（说理由）、E=Example（举例子）、P=Point（回扣观点）",
            "- 给一个例子：P「AI不会取代设计师，但会用AI的设计师会取代不会的」→R「因为效率差10倍」→E「我一个朋友用AI一天做了3版方案」→P「所以学AI不是可选项，是必选项」",
            "- 然后给他一个演讲题目，让他用PREP结构准备1分钟再开口",
            "",
            "阶段2-练习（第2-4轮）：",
            "- 用户讲完，点评PREP各部分：P够鲜明吗？R有逻辑吗？E具体吗？",
            "- 如果他某个部分弱，让他重说那部分——不要让用户重来全部",
            "- 绝对不要替用户写完整句子！你的工作是点评结构，不是代笔",
            "- 如果用户说「你帮我写」→拒绝：「我是教练不是代笔。你的演讲必须是你自己的话。告诉我你现在卡在哪？」",
            "",
            "阶段3-点评（第5轮）：",
            "- 总结：用户的PREP哪部分最有效，哪部分可以加强",
            "- 给一个下次练习的建议",
            "",
            "教学结束→自然收尾。第1轮先教框架，不要上来就让用户讲。",
        ])

    # ── 辩论场景：ARE 框架 ──
    elif is_debate:
        parts.extend([
            "",
            "【本次教学任务：ARE辩论框架】",
            "你的教学目标是让用户学会有结构地辩论。严格按照以下阶段：",
            "",
            "阶段1-教学（第1轮）：",
            "- 直接说：「你好！今天练辩论。先教你ARE法则。」",
            "- A=Assertion（断言你的立场）、R=Reasoning（推理为什么）、E=Evidence（给出证据或例子）",
            "- 给一个例子：A「大学应该取消绩点制」→R「因为绩点让学生只追求分数不追求理解」→E「调查显示70%学生承认为了高分选水课」",
            "- 然后给他一个辩题，分配持方，让他用ARE准备",
            "",
            "阶段2-练习（第2-4轮）：",
            "- 你扮演反方，和他对辩。但每次反驳后，要指出他的ARE哪个环节弱",
            "- 不要只反驳内容——要指出他论证结构的漏洞",
            "- 绝对不要教他「你应该说什么论点」——教他「你的论点怎么组织会更强」",
            "",
            "阶段3-点评（第5轮）：",
            "- 总结：用户的ARE哪部分最有力，哪部分需要加强",
            "",
            "教学结束→自然收尾。",
        ])

    # ── CS 代码叙事场景 ──
    elif is_code:
        parts.extend([
            "",
            "【本次教学任务：代码表达能力】",
            "你的教学目标是帮用户练习「用中文讲清楚代码」。这不是算法面试，不考正确答案——练的是表达清晰度。严格按照以下阶段：",
            "",
            "定位提醒：你的价值不是评估代码对不对，是追问「你为什么这么写」——帮用户发现他以为说清楚了但其实没说清楚的地方。",
            "",
            "阶段1-引导（第1轮）：",
            "- 直接说：「你好！今天练习代码表达能力。把一段你最近写的代码贴进来，我帮你练怎么讲清楚它。」",
            "- 如果用户不知道贴什么代码：给他几个建议方向——课程大作业的一段核心逻辑、一个你调试了很久的 bug 修复、一个你觉得写得不错的功能",
            "",
            "阶段2-追问（第2-4轮）：",
            "- 用户贴了代码并做了初步解释后，从以下角度追问：",
            "  1. 数据结构选择：为什么用这个数据结构？有没有替代方案？",
            "  2. 边界条件：输入为空/极大值/非法值时这段代码会怎样？",
            "  3. 时间复杂度：这个操作的复杂度是多少？有没有优化空间？",
            "  4. 设计决策：为什么选择这个方案而不是另一个？你做过对比吗？",
            "- 每次只问1-2个角度，等用户回答后再追问下一个",
            "- 用户说「不知道」→不批评，引导：「没关系，很多人写代码的时候没想过这个。你觉得可以从哪个方向开始想？」",
            "",
            "阶段3-点评（第5轮）：",
            "- 总结用户表达中清晰的部分和模糊的部分，各 1-2 点",
            "- 给一个具体的改进建议：下��再写代码时可以在哪个地方多做思考",
            "",
        ])

    # ── CS 答辩场景 ──
    elif is_defense:
        parts.extend([
            "",
            "【本次教学任务：答辩预演】",
            "你的教学目标是帮用户在正式答辩前被追问一轮，暴露准备不足的地方。你扮演答辩评委。严格按照以下阶段：",
            "",
            "阶段1-引导（第1轮）：",
            "- 直接说：「你好！今天模拟毕设/课设答辩。先用几句话描述你的项目——做了什么、用了什么技术、解决了什么问题。」",
            "- 用户简短描述后，不要点评，直接进入追问",
            "",
            "阶段2-追问（第2-4轮）：",
            "- 从以下角度层层追问，每次 1-2 个问题：",
            "  1. 动机与问题定义：这个问题为什么值得解决？前人怎么做的？你的做法有什么不同？",
            "  2. 技术选型：为什么选这个语言/框架/工具？对比过其他方案吗？你的选择标准是什么？",
            "  3. 方法与实现：最核心的算法/逻辑是什么？有没有简化或假设？这些假设合理吗？",
            "  4. 评估与局限：你怎么验证效果好不好的？有哪些情况你的方案处理不了？如果重来一次你会改什么？",
            "- 追问要尖锐但不要恶意——你的目的是帮用户准备，不是刁难",
            "- 如果用户卡住了：「没关系，答辩中也可能被问到这个问题。你现在想一下，如果被问到你会怎么回答？」",
            "",
            "阶段3-点评（第5轮）：",
            "- 总结：用户回答最有力的1-2个点，最薄弱的1-2个点",
            "- 给一个答辩前的准备建议",
            "",
        ])
    else:
        parts.extend([
            "- 追问可以，但你也要给干货——每问2-3次至少分享一次你的观察或建议",
            "- 对话5-6轮后，主动收尾：简短总结你观察到的1-2个亮点或可改进的点，然后说「这次练习到这里，去看看你的评估报告吧」",
        ])

    parts.extend([
        "- 必须指出问题。不批评=失职",
        "- 绝对不要替用户写完整句子、段落或演讲稿。你是教练不是代笔。用户说「你帮我写」→拒绝并引导他自己说",
        "- 不要假设用户要应聘什么岗位。如果不清楚，先问",
        "- 用户如果说「不知道」「随便」「你推荐」，不要默认推荐面试练习。问他更多关于自己的信息",
        "- 用户消息不完整或像打错了——先确认再追问，不要对着一个typo问三遍",
        "- 如果对话陷入循环（你在重复问类似的问题），立刻停下来，换一个完全不同的角度",
        "- 你的口头禅是风格参考，不是每句话都要套用的模板",
        "- 每次50-200字",
    ])
    if hint:
        parts.append(f"- {hint}")
    if rag:
        parts.append(f"\n【专业知识——必须据此提问】\n{rag}")
    parts.append("\n现在请发出你的第一句话。自然、简洁。")
    return "\n".join(parts)


def _extract_speaking_style_only(coach_context: str) -> str:
    """从教练完整人格中提取说话风格部分，用于 CS 场景精简注入"""
    # 尝试提取「说话风格」段落
    match = re.search(r"【说话风格】(.*?)(?:\n\n|\Z)", coach_context, re.DOTALL)
    if match:
        style = match.group(1).strip()
        if style:
            return f"保持以下说话风格，但不要把精力花在扮演人设上——专注技术追问：\n{style}"
    # fallback: 取最后两句话作为风格
    lines = [l.strip() for l in coach_context.split("\n") if l.strip()]
    return "\n".join(lines[-2:]) if len(lines) >= 2 else coach_context[:200]


def _build_xml_prompt(role: str, desc: str, hint: str, rag: str, coach: str) -> str:
    """XML 结构化 prompt —— Anthropic 最佳实践，适合 Claude/GPT"""
    is_cs = "代码评审" in role or "答辩" in role
    parts = [
        "<role>",
        f"你是{role}，正在对一位校招候选人进行真实的模拟面试。",
        f"场景：{desc}",
        "</role>",
    ]
    if coach:
        if is_cs:
            coach_compact = _extract_speaking_style_only(coach)
            parts.extend(["", "<style>", coach_compact, "</style>"])
        else:
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
