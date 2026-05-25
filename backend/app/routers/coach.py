"""教练人格 API"""

from fastapi import APIRouter
from app.models.schemas import CoachListResponse, CoachRecommendRequest
from app.data.coaches import list_coaches, get_coach_by_id, recommend_coaches

router = APIRouter(prefix="/api/coaches", tags=["coaches"])


@router.get("", response_model=CoachListResponse)
async def list_coaches_api():
    """获取所有预设教练"""
    coaches = list_coaches()
    return CoachListResponse(coaches=coaches, total=len(coaches))


@router.get("/{coach_id}")
async def get_coach_api(coach_id: str):
    """获取教练详情"""
    coach = get_coach_by_id(coach_id)
    if coach is None:
        return {"error": "教练不存在", "coach_id": coach_id}
    return coach


@router.post("/recommend")
async def recommend_coaches_api(req: CoachRecommendRequest):
    """根据用户画像推荐教练（含推荐理由）"""
    result = recommend_coaches(
        concerns=req.concerns or [],
        hexagon_self=req.hexagon_self or None,
        scene_id=req.scene_id,
    )
    return {"recommendations": result, "total": len(result)}
