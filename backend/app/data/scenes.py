"""场景数据定义"""

from app.models.schemas import Scene, SceneCategory, Difficulty

SCENES: list[Scene] = [
    Scene(
        id="pm-interview-beginner",
        title="产品经理面试 - 初级",
        category=SceneCategory.INTERVIEW,
        difficulty=Difficulty.BEGINNER,
        description="模拟互联网公司产品经理校招一面。面试官将考察你的产品 sense、逻辑思维和沟通能力。适合零基础入门。",
        tags=["产品经理", "互联网", "校招", "入门"],
        interviewer_role="腾讯产品总监",
        duration_minutes=15,
    ),
    Scene(
        id="pm-interview-intermediate",
        title="产品经理面试 - 进阶",
        category=SceneCategory.INTERVIEW,
        difficulty=Difficulty.INTERMEDIATE,
        description="模拟大厂 PM 二面/三面。增加费米问题、数据分析、商业化等高频难题，面试官会深度追问。适合有基础的同学。",
        tags=["产品经理", "互联网", "进阶", "费米问题"],
        interviewer_role="字节跳动高级产品经理",
        duration_minutes=20,
    ),
    Scene(
        id="pm-interview-advanced",
        title="产品经理面试 - 挑战",
        category=SceneCategory.INTERVIEW,
        difficulty=Difficulty.ADVANCED,
        description="模拟总监面/HR 面。包含产品战略、团队协作、职业规划等高阶话题。面试官风格犀利，直击要害。",
        tags=["产品经理", "互联网", "高阶", "总监面"],
        interviewer_role="战略产品副总裁",
        duration_minutes=25,
    ),
    Scene(
        id="speech-improv-beginner",
        title="即兴演讲 - 入门",
        category=SceneCategory.SPEECH,
        difficulty=Difficulty.BEGINNER,
        description="随机抽取一个话题，你有 2 分钟准备时间，然后进行 3 分钟即兴演讲。适合克服演讲恐惧、锻炼表达能力。",
        tags=["演讲", "表达", "入门", "克服紧张"],
        interviewer_role="演讲教练",
        duration_minutes=10,
    ),
    Scene(
        id="speech-improv-intermediate",
        title="即兴演讲 - 进阶",
        category=SceneCategory.SPEECH,
        difficulty=Difficulty.INTERMEDIATE,
        description="挑战更高难度的话题，准备时间缩短到 1 分钟。演讲后 AI 教练会从内容结构、语言表达、台风三个维度进行评估。",
        tags=["演讲", "表达", "进阶", "限时挑战"],
        interviewer_role="TEDx 演讲教练",
        duration_minutes=12,
    ),
    Scene(
        id="debate-improv",
        title="即兴辩论 - 1v1",
        category=SceneCategory.DEBATE,
        difficulty=Difficulty.INTERMEDIATE,
        description="AI 给你一个辩题和持方，你需要用逻辑说服对方。AI 扮演反方与你交锋。锻炼批判性思维和即兴应变能力。",
        tags=["辩论", "逻辑", "批判性思维", "即兴"],
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
) -> list[Scene]:
    result = SCENES
    if category:
        result = [s for s in result if s.category == category]
    if difficulty:
        result = [s for s in result if s.difficulty == difficulty]
    return result
