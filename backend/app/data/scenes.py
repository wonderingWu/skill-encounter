"""场景数据定义"""

from app.models.schemas import Scene, SceneCategory, Difficulty

SCENES: list[Scene] = [
    Scene(
        id="pm-interview-beginner",
        title="你比自己想象的更有竞争力",
        emoji="😰",
        cat="job",
        category=SceneCategory.INTERVIEW,
        difficulty=Difficulty.BEGINNER,
        description="来发现你在对话中还没展现的力量。",
        tags=["面试模拟", "入门"],
        interviewer_role="腾讯产品总监",
        duration_minutes=15,
    ),
    Scene(
        id="pm-interview-intermediate",
        title="群面不是比谁声音大",
        emoji="🔥",
        cat="job",
        category=SceneCategory.INTERVIEW,
        difficulty=Difficulty.INTERMEDIATE,
        description="找到你独特的表达方式，安静也可以有力。",
        tags=["压力面试", "进阶"],
        interviewer_role="字节跳动高级产品经理",
        duration_minutes=20,
    ),
    Scene(
        id="pm-interview-advanced",
        title="你的经历里，藏着面试官想听的故事",
        emoji="💼",
        cat="job",
        category=SceneCategory.INTERVIEW,
        difficulty=Difficulty.ADVANCED,
        description="把社团、课程、甚至失败的尝试，翻译成你的独特筹码。",
        tags=["高阶面试", "经验转化"],
        interviewer_role="战略产品副总裁",
        duration_minutes=25,
    ),
    Scene(
        id="speech-improv-beginner",
        title="把你的想法，变成别人的共鸣",
        emoji="🎤",
        cat="express",
        category=SceneCategory.SPEECH,
        difficulty=Difficulty.BEGINNER,
        description="2分钟准备3分钟开讲。你不是不会说，你是还没找到自己的声音。",
        tags=["即兴演讲", "克服紧张"],
        interviewer_role="演讲教练",
        duration_minutes=10,
    ),
    Scene(
        id="speech-improv-intermediate",
        title="每一次开口，都在重新定义你是谁",
        emoji="🗣️",
        cat="express",
        category=SceneCategory.SPEECH,
        difficulty=Difficulty.INTERMEDIATE,
        description="AI教练从内容、结构、气场三个维度给你反馈。",
        tags=["进阶演讲", "社恐友好"],
        interviewer_role="TEDx 演讲教练",
        duration_minutes=12,
    ),
    Scene(
        id="debate-improv",
        title="好的反驳，始于真正听懂对方",
        emoji="⚔️",
        cat="express",
        category=SceneCategory.DEBATE,
        difficulty=Difficulty.INTERMEDIATE,
        description="AI扮反方，逼你走出自己的逻辑闭环。",
        tags=["即兴辩论", "逻辑思维"],
        interviewer_role="辩论赛对手",
        duration_minutes=15,
    ),
    # ── CS 专项场景 ──────────────────────────
    Scene(
        id="code-narrative",
        title="把你刚写的代码，用中文讲一遍",
        emoji="💻",
        cat="cs",
        category=SceneCategory.PRESENTATION,
        difficulty=Difficulty.BEGINNER,
        description="粘贴一段你写的代码，AI教练追问你为什么这么写、边界条件考虑了吗。练的是讲清楚技术决策，不是刷算法题。",
        tags=["代码表达", "技术沟通"],
        interviewer_role="资深代码评审",
        duration_minutes=15,
    ),
    Scene(
        id="project-defense",
        title="答辩前先被AI问一轮",
        emoji="🎓",
        cat="cs",
        category=SceneCategory.PRESENTATION,
        difficulty=Difficulty.INTERMEDIATE,
        description="描述你的课程项目或毕设，AI扮演答辩评委追问技术选型、方案局限、改进方向。练完再上，心里有底。",
        tags=["毕设答辩", "项目展示"],
        interviewer_role="毕业设计答辩评委",
        duration_minutes=20,
    ),
]


def get_scene_by_id(scene_id: str) -> Scene | None:
    for scene in SCENES:
        if scene.id == scene_id:
            return scene
    return None


def list_scenes(
    category: str | None = None,
    difficulty: str | None = None,
    cat: str | None = None,
) -> list[Scene]:
    result = SCENES
    if cat and cat != "all":
        result = [s for s in result if s.cat == cat]
    if category:
        result = [s for s in result if s.category == category]
    if difficulty:
        result = [s for s in result if s.difficulty == difficulty]
    return result
