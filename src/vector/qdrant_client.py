"""Qdrant 向量数据库客户端"""

from __future__ import annotations

import os
from typing import Any
from pathlib import Path

from loguru import logger
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue

from src.config import get_settings


# 全局客户端单例
_qdrant_client: QdrantClient | None = None

# 向量维度（千问 embedding 是 1024 维）
EMBEDDING_DIMENSION = 1024


def get_qdrant_client() -> QdrantClient:
    """获取 Qdrant 客户端单例"""
    global _qdrant_client
    
    if _qdrant_client is None:
        settings = get_settings()
        qdrant_cfg = settings.qdrant
        
        _qdrant_client = QdrantClient(
            host=qdrant_cfg.host,
            port=qdrant_cfg.port,
            api_key=qdrant_cfg.api_key if qdrant_cfg.api_key else None,
            https=qdrant_cfg.use_https,
            timeout=30,
        )
        logger.info(f"Qdrant 客户端已初始化: {qdrant_cfg.host}:{qdrant_cfg.port}")
    
    return _qdrant_client


def ensure_collection_exists(collection_name: str | None = None) -> None:
    """确保 Collection 存在，不存在则创建"""
    settings = get_settings()
    collection_name = collection_name or settings.qdrant.collection_name
    
    client = get_qdrant_client()
    
    # 检查 collection 是否存在
    collections = client.get_collections().collections
    exists = any(col.name == collection_name for col in collections)
    
    if not exists:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=EMBEDDING_DIMENSION,
                distance=Distance.COSINE,
            ),
        )
        logger.info(f"已创建 Collection: {collection_name}")


def get_collection_info(collection_name: str | None = None) -> dict[str, Any]:
    """获取 Collection 信息"""
    settings = get_settings()
    collection_name = collection_name or settings.qdrant.collection_name
    
    client = get_qdrant_client()
    info = client.get_collection(collection_name)
    return {
        "name": info.name,
        "vectors_count": info.vectors_count,
        "points_count": info.points_count,
        "status": info.status.name,
    }


def upsert_vectors(
    collection_name: str,
    points: list[dict[str, Any]],
) -> bool:
    """插入或更新向量数据
    
    Args:
        collection_name: Collection 名称
        points: 向量点列表，每项包含:
            - id: 唯一ID
            - vector: 向量数组
            - payload: 元数据字典
    
    Returns:
        是否成功
    """
    client = get_qdrant_client()
    
    # 转换为 Qdrant PointStruct 格式
    qdrant_points = [
        PointStruct(
            id=p["id"],
            vector=p["vector"],
            payload=p.get("payload", {}),
        )
        for p in points
    ]
    
    client.upsert(
        collection_name=collection_name,
        points=qdrant_points,
    )
    
    logger.info(f"已插入 {len(points)} 条向量到 {collection_name}")
    return True


def search_vectors(
    collection_name: str,
    query_vector: list[float],
    limit: int = 5,
    filter_conditions: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """向量相似度检索

    Args:
        collection_name: Collection 名称
        query_vector: 查询向量
        limit: 返回结果数量
        filter_conditions: 过滤条件

    Returns:
        检索结果列表
    """
    client = get_qdrant_client()

    # 构建过滤条件
    filter_obj = None
    if filter_conditions:
        must = []
        for key, value in filter_conditions.items():
            must.append(FieldCondition(key=key, match=MatchValue(value=value)))
        filter_obj = Filter(must=must)

    # 使用 query_points 方法（新版本 API）
    results = client.query_points(
        collection_name=collection_name,
        query=query_vector,
        limit=limit,
        query_filter=filter_obj,
        with_payload=True,
        with_vectors=False,
    )

    # query_points 返回 ResultPoints 对象，需要访问 .points
    return [
        {
            "id": r.id,
            "score": r.score,
            "payload": r.payload,
        }
        for r in results.points
    ]


def delete_vectors(
    collection_name: str,
    point_ids: list[str],
) -> bool:
    """删除向量"""
    client = get_qdrant_client()
    
    client.delete(
        collection_name=collection_name,
        points_selector=point_ids,
    )
    
    logger.info(f"已删除 {len(point_ids)} 条向量 from {collection_name}")
    return True


def delete_collection(collection_name: str) -> bool:
    """删除整个 Collection"""
    client = get_qdrant_client()
    
    client.delete_collection(collection_name=collection_name)
    logger.info(f"已删除 Collection: {collection_name}")
    return True
