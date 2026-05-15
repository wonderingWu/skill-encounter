
import os
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent

# LLM 配置（兼容 OpenAI API 格式）
LLM_API_KEY = os.getenv("LLM_API_KEY", "sk-placeholder")
LLM_API_BASE = os.getenv("LLM_API_BASE", "https://api.openai.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-3.5-turbo")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.7"))

# GLM-4 推荐配置示例（在 .env 中设置）:
# LLM_API_BASE=https://open.bigmodel.cn/api/paas/v4
# LLM_MODEL=glm-4-flash

# DeepSeek 推荐配置示例:
# LLM_API_BASE=https://api.deepseek.com/v1
# LLM_MODEL=deepseek-chat

# ChromaDB 配置
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", str(PROJECT_ROOT / "chroma_data"))
CHROMA_COLLECTION_NAME = os.getenv("CHROMA_COLLECTION_NAME", "skill_encounter_knowledge")

# 服务配置
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
