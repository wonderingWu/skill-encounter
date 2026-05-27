from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime
from enum import Enum


class SceneCategory(str, Enum):
    INTERVIEW = "interview"       # 面试模拟
    SPEECH = "speech"             # 即兴演讲
    DEBATE = "debate"             # 即兴辩论
    NEGOTIATION = "negotiation"   # 谈判模拟
    PRESENTATION = "presentation" # 答辩/代码展示


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
    title: str = Field(..., description="用户视角场景标题")
    emoji: str = Field(default="💬", description="场景图标 emoji")
    cat: str = Field(default="all", description="前端分类: job/express/self/ai/all")
    category: SceneCategory = Field(..., description="场景类别")
    difficulty: Difficulty = Field(..., description="难度等级")
    description: str = Field(..., description="一句话场景描述")
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
    coach_id: str = Field(default="", description="选择的教练 ID")
    custom_coach: Optional[dict] = Field(default=None, description="自定义教练数据 {name,emoji,personality}")


class PracticeStartResponse(BaseModel):
    """开始练习返回"""
    session_id: str
    scene: Scene
    coach: Optional["Coach"] = None
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
    # v4: 对话后框架发现
    frameworks_discovered: list[str] = Field(default_factory=list, description="发现的框架名列表")
    patterns_used: dict[str, dict] = Field(default_factory=dict, description="框架名→{explanation, evidence}")


class FeedbackResponse(BaseModel):
    """反馈返回"""
    session_id: str
    feedback: Feedback


# ── 语音分析 ──────────────────────────────

class VoiceAnalysisResponse(BaseModel):
    """真声练习分析结果"""
    transcript: str = Field(..., description="语音转写文本")
    duration_sec: float = Field(..., description="录音时长(秒)")
    word_count: int = Field(default=0, description="字数")
    pace_wpm: float = Field(default=0, description="语速(字/分钟)")
    pace_feedback: str = Field(default="", description="语速评价")
    basic_metrics: str = Field(default="", description="基础指标摘要")
    ai_analysis: str = Field(default="", description="LLM 语音能力分析")


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
    latest_scores: HexagonScore | None = None
    gap_dimensions: list[str] = Field(default_factory=list)  # 当前差距最大的维度


class ProfileRequest(BaseModel):
    """用户画像请求"""
    year: str = Field(default="", description="年级")
    major: str = Field(default="", description="专业")
    concerns: list[str] = Field(default_factory=list, description="担忧标签")
    hexagon_self: Optional[dict] = Field(default=None, description="六维自评 {expression:float,...}")


class GapDetection(BaseModel):
    """能力差距检测结果"""
    detected_gaps: list[str] = Field(default_factory=list)  # 用户可能缺失的维度
    suggested_focus: str = ""  # 建议优先提升的维度
    hint_question: str = ""  # 探测性问题


# ── 教练人格 ──────────────────────────────

class Coach(BaseModel):
    """AI 教练人格"""
    id: str = Field(..., description="教练唯一标识")
    name: str = Field(..., description="教练名称")
    emoji: str = Field(default="🤖", description="教练头像 emoji")
    tagline: str = Field(default="", description="一句话介绍")
    personality: str = Field(..., description="人格描述，注入 system prompt")
    strengths: list[str] = Field(default_factory=list, description="擅长的六维能力")
    speaking_style: str = Field(default="", description="说话风格")
    is_preset: bool = Field(default=True, description="是否预设教练")


class CoachRecommendRequest(BaseModel):
    """AI 推荐教练请求"""
    year: str = Field(default="")
    major: str = Field(default="")
    concerns: list[str] = Field(default_factory=list)
    hexagon_self: Optional[dict] = Field(default=None, description="六维自评 {expression:float,...}")
    scene_id: Optional[str] = Field(default=None, description="场景 ID，用于 CS 场景感知推荐")


class CoachListResponse(BaseModel):
    """教练列表返回"""
    coaches: list[Coach]
    total: int
