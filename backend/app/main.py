"""技能奇遇 (Skill Encounter) - FastAPI 主入口"""

import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.config import HOST, PORT, PROJECT_ROOT
from app.routers import scene, practice
from app.services.rag import init_knowledge_base

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化知识库"""
    logger.info("正在初始化 RAG 知识库...")
    try:
        init_knowledge_base()
        logger.info("RAG 知识库初始化完成")
    except Exception as e:
        logger.error(f"知识库初始化失败（服务仍可运行，但 RAG 功能不可用）: {e}")
    yield
    logger.info("服务关闭")


app = FastAPI(
    title="技能奇遇 (Skill Encounter)",
    description="AI 驱动的轻社交 × 就业技能模拟平台",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(scene.router)
app.include_router(practice.router)

# 健康检查
@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "skill-encounter", "version": "0.1.0"}

# 静态文件（前端）—— 兼容本地和 Docker 环境
import os as _os
_frontend_from_env = _os.getenv("FRONTEND_DIR", "")
if _frontend_from_env:
    frontend_dir = Path(_frontend_from_env)
else:
    # 自动探测：尝试多个可能的路径
    candidates = [
        Path(__file__).parent.parent.parent / "frontend",  # 本地: skill-encounter/frontend
        Path(__file__).parent.parent / "frontend",          # Docker: /app/frontend
        Path("/app/frontend"),                              # Docker 硬编码后备
    ]
    frontend_dir = None
    for d in candidates:
        if d.exists():
            frontend_dir = d
            break

if frontend_dir and frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
    logger.info(f"前端静态文件已挂载: {frontend_dir}")
else:
    logger.warning(f"前端目录未找到，仅 API 可用。探测路径: {candidates}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True)
