"""场景 API 路由"""

from fastapi import APIRouter, Query
from app.models.schemas import SceneListResponse
from app.data.scenes import list_scenes, get_scene_by_id

router = APIRouter(prefix="/api/scenes", tags=["scenes"])


@router.get("", response_model=SceneListResponse)
async def list_scenes_api(
    category: str | None = Query(None, description="按类别筛选: interview/speech/debate/negotiation"),
    difficulty: str | None = Query(None, description="按难度筛选: beginner/intermediate/advanced"),
):
    """获取可用场景列表"""
    scenes = list_scenes(category=category, difficulty=difficulty)
    return SceneListResponse(scenes=scenes, total=len(scenes))


@router.get("/{scene_id}")
async def get_scene_api(scene_id: str):
    """获取场景详情"""
    scene = get_scene_by_id(scene_id)
    if scene is None:
        return {"error": "场景不存在", "scene_id": scene_id}
    return scene
