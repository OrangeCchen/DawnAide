"""向量数据库模块"""

from src.vector.qdrant_client import (
    get_qdrant_client,
    ensure_collection_exists,
    get_collection_info,
    upsert_vectors,
    search_vectors,
    delete_vectors,
    delete_collection,
    EMBEDDING_DIMENSION,
)

from src.vector.embeddings import (
    get_embedding,
    get_embeddings,
    truncate_text,
)
