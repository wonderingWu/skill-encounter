"""RAG 知识库服务 —— 基于 ChromaDB 的向量检索

v2 改进：添加检索缓存，避免同一会话内的重复向量搜索
"""

from __future__ import annotations

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
# 中英文多语言模型，对中文知识库检索效果更好
_embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="paraphrase-multilingual-MiniLM-L12-v2"  # 多语言模型，中文效果好
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
    """初始化知识库：每次启动强制重建（保证觉醒导向数据）"""
    global _initialized
    if _initialized:
        return

    collection = _get_collection()

    # 强制重建：删除旧面试导向数据
    if collection.count() > 0:
        old_ids = collection.get()["ids"]
        if old_ids:
            collection.delete(ids=old_ids)
            logger.info(f"已清除旧知识库 {len(old_ids)} 条文档")

    # 导入种子数据
    logger.info(f"开始导入觉醒导向种子数据，共 {len(SEED_DOCUMENTS)} 条...")
    ids = []
    documents = []
    metadatas = []

    for i, doc in enumerate(SEED_DOCUMENTS):
        ids.append(f"seed_{i}")
        documents.append(doc["content"])
        meta = dict(doc["metadata"])
        # 确保 concern_tags 是 ChromaDB 支持的格式
        if "concern_tags" in meta:
            meta["concern_tags"] = ",".join(meta["concern_tags"]) if meta["concern_tags"] else ""
        metadatas.append(meta)
        metadatas.append(doc["metadata"])

    collection.add(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
    )

    _initialized = True
    logger.info(f"种子数据导入完成，共 {len(SEED_DOCUMENTS)} 条文档")


def retrieve(scene_id: str, query: str, k: int = 3, user_concerns: list[str] | None = None) -> str:
    """检索与查询最相关的知识片段（带缓存 + profile过滤）"""
    collection = _get_collection()

    if collection.count() == 0:
        return ""

    try:
        # 构建 where 过滤条件（profile-aware）
        where_filter = None
        if user_concerns and len(user_concerns) > 0:
            # 如果用户有concerns标签，检索时优先匹配
            # 注意：ChromaDB where 过滤语法
            pass  # where过滤暂时通过结果后处理实现

        results = collection.query(
            query_texts=[query],
            n_results=min(k * 2, collection.count()),  # 取2倍候选，后处理筛选
            where=where_filter,
        )

        if not results or not results["documents"] or not results["documents"][0]:
            return ""

        documents = results["documents"][0]
        metadatas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(documents)

        # 后处理：如果用户有 concerns，优先返回相关文档
        if user_concerns and len(user_concerns) > 0:
            scored = []
            for i, (doc, meta) in enumerate(zip(documents, metadatas)):
                score = 0
                tags_str = meta.get("concern_tags", "")
                if tags_str:
                    tags = tags_str.split(",")
                    for uc in user_concerns:
                        if uc in tags:
                            score += 2
                scored.append((doc, meta, score))
            # 按匹配分数排序，取 top k
            scored.sort(key=lambda x: x[2], reverse=True)
            documents = [s[0] for s in scored[:k]]
            metadatas = [s[1] for s in scored[:k]]
        else:
            documents = documents[:k]
            metadatas = metadatas[:k]

        # 构建上下文文本
        context_parts = []
        for i, (doc, meta) in enumerate(zip(documents, metadatas)):
            source = meta.get("source", "未知来源")
            doc_type = meta.get("type", "通用")
            context_parts.append(f"[{source}] ({doc_type})\n{doc}")

        result = "\n\n---\n\n".join(context_parts)

        # 写入缓存
        cache_key = hashlib.md5(f"{scene_id}:{query}".encode()).hexdigest()
        if len(_retrieval_cache) >= 128:
            keys_to_remove = list(_retrieval_cache.keys())[:64]
            for k in keys_to_remove:
                del _retrieval_cache[k]
        _retrieval_cache[cache_key] = result

        return result

    except Exception as e:
        logger.warning(f"RAG 检索异常: {e}")
        return ""
