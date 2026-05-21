from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime
from enum import Enum


class SceneCategory(str, Enum):
    INTERVIEW = "interview"       # 面试模拟
    SPEECH = "speech"             # 即兴演讲
    DEBATE = "debate"             # 即兴辩论
    NEGOTIATION = "negotiation"   # 谈判模拟


class Difficulty(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


# ── 场景相关 ──────────────────────────────

class Scene(BaseModel):
    """场景卡片"""
    id: str = Field(..., description="场景唯一标识，如 pm-interview-beginner")
    title: str = Field(..., description="场景名称")
    category: SceneCategory = Field(..., description="场景类别")
    difficulty: Difficulty = Field(..., description="难度等级")
    description: str = Field(..., description="场景描述")
    tags: list[str] = Field(default_factory=list, description="标签")
    interviewer_role: str = Field(..., description="AI 扮演的角色名称")
    duration_minutes: int = Field(default=15, description="建议练习时长（分钟）")

    class Config:
        use_enum_values = True


class SceneListResponse(BaseModel):
    """场景列表返回"""
    scenes: list[Scene]
    total: int


# ── 消息相关 ──────────────────────────────

class Message(BaseModel):
    """单条对话消息"""
    role: MessageRole
    content: str
    timestamp: Optional[str] = None

    class Config:
        use_enum_values = True


# ── 练习会话相关 ──────────────────────────

class PracticeStartRequest(BaseModel):
    """开始练习请求"""
    scene_id: str = Field(..., description="选择的场景 ID")


class PracticeStartResponse(BaseModel):
    """开始练习返回"""
    session_id: str
    scene: Scene
    opening_message: str = Field(..., description="AI 面试官开场白")


class PracticeMessageRequest(BaseModel):
    """发送消息请求"""
    session_id: str
    message: str = Field(..., description="用户消息内容")


class PracticeMessageResponse(BaseModel):
    """发送消息返回"""
    session_id: str
    reply: str = Field(..., description="AI 面试官回复")
    current_round: int = Field(default=1, description="当前轮次")


class PracticeEndRequest(BaseModel):
    """结束练习请求"""
    session_id: str


# ── 反馈相关 ──────────────────────────────

class DimensionScore(BaseModel):
    """维度评分"""
    name: str = Field(..., description="维度名称")
    score: float = Field(..., ge=0, le=5, description="评分 (0-5)")
    comment: str = Field(..., description="维度点评")


class Feedback(BaseModel):
    """结构化反馈"""
    session_id: str
    scene_title: str
    overall_score: float = Field(..., ge=0, le=5, description="综合评分")
    dimensions: list[DimensionScore]
    strengths: list[str] = Field(default_factory=list, description="亮点")
    improvements: list[str] = Field(default_factory=list, description="改进建议")
    summary: str = Field(..., description="总结评语")


class FeedbackResponse(BaseModel):
    """反馈返回"""
    session_id: str
    feedback: Feedback


# ── 六边形能力维度 ──────────────────────────

# 六大维度的标准定义
HEXAGON_DIMENSIONS = [
    {"id": "expression",   "name": "表达影响力", "emoji": "💬",
     "desc": "能不能把想法说清楚、写明白、让人信服"},
    {"id": "logic",        "name": "逻辑分析力", "emoji": "🧩",
     "desc": "能不能结构化地思考、拆解复杂问题"},
    {"id": "self_awareness","name": "自我认知力", "emoji": "🪞",
     "desc": "了不了解自己的优势盲区、能不能管理情绪"},
    {"id": "collaboration","name": "人际协作力", "emoji": "🤝",
     "desc": "能不能和不同的人合作、处理冲突"},
    {"id": "ai_literacy",  "name": "AI素养力",   "emoji": "🤖",
     "desc": "懂不懂AI能做什么、会不会用AI工具"},
    {"id": "adaptability", "name": "适应创新力", "emoji": "🌱",
     "desc": "能不能快速学习新东西、在变化中找到方向"},
]


class HexagonSelfAssessment(BaseModel):
    """用户自评六维度分数"""
    expression: float = Field(default=0, ge=0, le=5)
    logic: float = Field(default=0, ge=0, le=5)
    self_awareness: float = Field(default=0, ge=0, le=5)
    collaboration: float = Field(default=0, ge=0, le=5)
    ai_literacy: float = Field(default=0, ge=0, le=5)
    adaptability: float = Field(default=0, ge=0, le=5)


class HexagonScore(BaseModel):
    """单次六维度评分（AI或自评）"""
    expression: float = Field(..., ge=0, le=5)
    logic: float = Field(..., ge=0, le=5)
    self_awareness: float = Field(..., ge=0, le=5)
    collaboration: float = Field(..., ge=0, le=5)
    ai_literacy: float = Field(..., ge=0, le=5)
    adaptability: float = Field(..., ge=0, le=5)
    comments: dict[str, str] = Field(default_factory=dict)  # {dim_id: "点评"}


class HexagonHistory(BaseModel):
    """六维度历史记录"""
    self_assessment: Optional[HexagonSelfAssessment] = None
    ai_assessments: list[dict] = Field(default_factory=list)  # [{session_id, scene, scores, timestamp}]
    latest_scores: HexagonScore = Field(...)
    gap_dimensions: list[str] = Field(default_factory=list)  # 当前差距最大的维度


class GapDetection(BaseModel):
    """能力差距检测结果"""
    detected_gaps: list[str] = Field(default_factory=list)  # 用户可能缺失的维度
    suggested_focus: str = ""  # 建议优先提升的维度
    hint_question: str = ""  # 探测性问题
