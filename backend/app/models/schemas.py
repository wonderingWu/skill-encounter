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
