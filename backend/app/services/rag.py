"""RAG 知识库服务 —— 基于 ChromaDB 的向量检索

v2 改进：添加检索缓存，避免同一会话内的重复向量搜索
"""

from chromadb import PersistentClient
from chromadb.utils import embedding_functions
from app.config import CHROMA_PERSIST_DIR, CHROMA_COLLECTION_NAME
from app.data.seed import SEED_DOCUMENTS
import hashlib
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

_client: PersistentClient | None = None
_collection = None
_initialized = False

# 检索缓存（按 query hash 缓存，最多 128 条）
_retrieval_cache: dict[str, str] = {}

# 使用 sentence-transformers 作为 embedding 函数
# 支持中文的轻量模型
_embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"  # 轻量通用模型，支持多语言
)


def _get_client() -> PersistentClient:
    global _client
    if _client is None:
        _client = PersistentClient(path=CHROMA_PERSIST_DIR)
    return _client


def _get_collection():
    global _collection
    if _collection is None:
        client = _get_client()
        try:
            _collection = client.get_collection(
                name=CHROMA_COLLECTION_NAME,
                embedding_function=_embedding_fn,
            )
            logger.info(f"已加载现有知识库: {_collection.count()} 条文档")
        except Exception:
            _collection = client.create_collection(
                name=CHROMA_COLLECTION_NAME,
                embedding_function=_embedding_fn,
            )
            logger.info("已创建新的知识库")
    return _collection


def init_knowledge_base():
    """初始化知识库：检查并导入种子数据"""
    global _initialized
    if _initialized:
        return

    collection = _get_collection()

    if collection.count() > 0:
        logger.info(f"知识库已有 {collection.count()} 条文档，跳过初始化")
        _initialized = True
        return

    # 导入种子数据
    logger.info(f"开始导入种子数据，共 {len(SEED_DOCUMENTS)} 条...")
    ids = []
    documents = []
    metadatas = []

    for i, doc in enumerate(SEED_DOCUMENTS):
        ids.append(f"seed_{i}")
        documents.append(doc["content"])
        metadatas.append(doc["metadata"])

    collection.add(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
    )

    _initialized = True
    logger.info(f"种子数据导入完成，共 {len(SEED_DOCUMENTS)} 条文档")


def retrieve(scene_id: str, query: str, k: int = 5) -> str:
    """检索与查询最相关的知识片段（带缓存）"""
    # 缓存 key = query 的 hash
    cache_key = hashlib.md5(f"{scene_id}:{query}".encode()).hexdigest()
    if cache_key in _retrieval_cache:
        logger.debug("RAG 缓存命中")
        return _retrieval_cache[cache_key]

    collection = _get_collection()

    if collection.count() == 0:
        return ""

    try:
        results = collection.query(
            query_texts=[query],
            n_results=min(k, collection.count()),
        )

        if not results or not results["documents"] or not results["documents"][0]:
            return ""

        documents = results["documents"][0]
        metadatas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(documents)

        # 构建上下文文本
        context_parts = []
        for i, (doc, meta) in enumerate(zip(documents, metadatas)):
            source = meta.get("source", "未知来源")
            doc_type = meta.get("type", "通用")
            context_parts.append(f"[{source}] ({doc_type})\n{doc}")

        result = "\n\n---\n\n".join(context_parts)

        # 写入缓存（LRU 简单策略：超过 128 条时清掉最早的一半）
        if len(_retrieval_cache) >= 128:
            keys_to_remove = list(_retrieval_cache.keys())[:64]
            for k in keys_to_remove:
                del _retrieval_cache[k]
        _retrieval_cache[cache_key] = result

        return result

    except Exception as e:
        logger.warning(f"RAG 检索异常: {e}")
        return ""
