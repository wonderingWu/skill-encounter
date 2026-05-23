"""场景数据定义"""

from app.models.schemas import Scene, SceneCategory, Difficulty

SCENES: list[Scene] = [
    Scene(
        id="pm-interview-beginner",
        title="投了简历没回音，是不是我不够好？",
        emoji="😰",
        cat="job",
        category=SceneCategory.INTERVIEW,
        difficulty=Difficulty.BEGINNER,
        description="练一次大厂面试你就知道。",
        tags=["面试模拟", "入门"],
        interviewer_role="腾讯产品总监",
        duration_minutes=15,
    ),
    Scene(
        id="pm-interview-intermediate",
        title="群面总是插不上话，我该怎么办？",
        emoji="🔥",
        cat="job",
        category=SceneCategory.INTERVIEW,
        difficulty=Difficulty.INTERMEDIATE,
        description="压力场景专项练习。",
        tags=["压力面试", "进阶"],
        interviewer_role="字节跳动高级产品经理",
        duration_minutes=20,
    ),
    Scene(
        id="pm-interview-advanced",
        title="学长说没实习经历面试绝对没戏…",
        emoji="💼",
        cat="job",
        category=SceneCategory.INTERVIEW,
        difficulty=Difficulty.ADVANCED,
        description="把社团经历翻译成面试官想听的故事。",
        tags=["高阶面试", "经验转化"],
        interviewer_role="战略产品副总裁",
        duration_minutes=25,
    ),
    Scene(
        id="speech-improv-beginner",
        title="课堂pre紧张到脑子一片空白…",
        emoji="🎤",
        cat="express",
        category=SceneCategory.SPEECH,
        difficulty=Difficulty.BEGINNER,
        description="2分钟准备3分钟开讲，再也不慌。",
        tags=["即兴演讲", "克服紧张"],
        interviewer_role="演讲教练",
        duration_minutes=10,
    ),
    Scene(
        id="speech-improv-intermediate",
        title="朋友圈发完又删，怕说错话…",
        emoji="🗣️",
        cat="express",
        category=SceneCategory.SPEECH,
        difficulty=Difficulty.INTERMEDIATE,
        description="AI教练三维反馈。",
        tags=["进阶演讲", "社恐友好"],
        interviewer_role="TEDx 演讲教练",
        duration_minutes=12,
    ),
    Scene(
        id="debate-improv",
        title="室友说我观点没逻辑，怎么反驳？",
        emoji="⚔️",
        cat="express",
        category=SceneCategory.DEBATE,
        difficulty=Difficulty.INTERMEDIATE,
        description="AI扮演反方与你交锋。",
        tags=["即兴辩论", "逻辑思维"],
        interviewer_role="辩论赛对手",
        duration_minutes=15,
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
