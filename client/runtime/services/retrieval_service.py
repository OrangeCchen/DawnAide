"""本地知识库检索服务

支持向量检索（ChromaDB）与关键词检索的混合召回。
"""

from __future__ import annotations

from fastapi import APIRouter
from loguru import logger
from pydantic import BaseModel

router = APIRouter(prefix="/kb", tags=["kb"])


class SearchRequest(BaseModel):
    query: str
    collection: str = "default"
    top_k: int = 5
    filters: dict | None = None


class SearchHit(BaseModel):
    content: str
    source: str
    score: float
    chunk_index: int = 0


class SearchResponse(BaseModel):
    hits: list[SearchHit]
    total: int = 0


@router.post("/search", response_model=SearchResponse)
async def search_kb(req: SearchRequest):
    import asyncio
    from store.local_store import get_collection

    collection = await get_collection(req.collection)

    results = await asyncio.to_thread(
        collection.query,
        query_texts=[req.query],
        n_results=req.top_k,
    )

    hits = []
    if results and results.get("documents"):
        documents = results["documents"][0]
        metadatas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(documents)
        distances = results["distances"][0] if results.get("distances") else [0.0] * len(documents)

        for doc, meta, dist in zip(documents, metadatas, distances):
            score = max(0.0, 1.0 - dist)
            hits.append(SearchHit(
                content=doc,
                source=meta.get("source", "unknown"),
                score=round(score, 4),
                chunk_index=meta.get("chunk_index", 0),
            ))

    return SearchResponse(hits=hits, total=len(hits))
