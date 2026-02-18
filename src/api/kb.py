"""知识库 API 路由"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

import requests
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel
from qdrant_client.models import Filter, FieldCondition, MatchValue

from src.config import get_settings
from src.vector import (
    get_qdrant_client,
    ensure_collection_exists,
    get_embedding,
    get_embeddings,
    upsert_vectors,
    search_vectors,
    delete_vectors,
    get_collection_info,
)

router = APIRouter(prefix="/api/kb", tags=["knowledge-base"])

# 来源存储路径
KB_STORAGE_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "kb_files"
KB_STORAGE_PATH.mkdir(parents=True, exist_ok=True)


# ---- Request/Response Models ----


class SourceBase(BaseModel):
    """知识来源基础模型"""
    name: str
    type: str  # pdf, docx, txt, link, markdown
    size: int = 0
    chunk_count: int = 0


class SourceCreate(BaseModel):
    """创建来源请求"""
    name: str
    type: str
    content: str = ""  # 文本内容或链接
    file_path: str = ""  # 已上传文件的路径


class SearchRequest(BaseModel):
    """检索请求"""
    query: str
    limit: int = 5


class ChatRequest(BaseModel):
    """对话请求"""
    message: str
    history: list[dict[str, str]] = []


class SourceResponse(BaseModel):
    """来源响应"""
    id: str
    name: str
    type: str
    size: int
    chunk_count: int
    created_at: str


# ---- 内存存储（生产环境应使用数据库）----

# 来源元数据存储
_sources_db: dict[str, dict[str, Any]] = {}


# ---- 工具函数 ----


def parse_document(content: str, file_type: str) -> list[str]:
    """解析文档为文本块
    
    简单实现：按段落分割。
    生产环境可使用更复杂的分块策略。
    """
    # 按段落分割
    paragraphs = content.split("\n\n")
    
    # 过滤空段落并合并过短的段落
    chunks = []
    current_chunk = ""
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        
        # 如果当前段落加上新段落超过 500 字，分割
        if len(current_chunk) + len(para) > 500:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = para
        else:
            if current_chunk:
                current_chunk += "\n\n" + para
            else:
                current_chunk = para
    
    if current_chunk:
        chunks.append(current_chunk)
    
    # 如果分块太少，尝试更细粒度分割
    if len(chunks) < 3 and len(content) > 200:
        # 按句子分割
        sentences = content.replace("\n", " ").split("。")
        chunks = []
        current = ""
        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue
            if len(current) + len(sent) > 300:
                if current:
                    chunks.append(current + "。")
                current = sent
            else:
                current = (current + "。" + sent) if current else sent + "。"
        if current:
            chunks.append(current)
    
    return [c for c in chunks if c.strip()]


async def process_file_upload(file: UploadFile) -> tuple[str, str]:
    """处理文件上传
    
    Returns:
        (file_id, file_path)
    """
    file_id = str(uuid.uuid4())
    
    # 确定文件扩展名
    ext = Path(file.filename).suffix.lower()
    if ext == ".md":
        file_type = "markdown"
    elif ext == ".txt":
        file_type = "txt"
    elif ext == ".pdf":
        file_type = "pdf"
    elif ext in [".doc", ".docx"]:
        file_type = "docx"
    else:
        file_type = "unknown"
    
    # 保存文件
    file_path = KB_STORAGE_PATH / f"{file_id}{ext}"
    content = await file.read()
    file_path.write_bytes(content)
    
    # 提取文本内容
    text_content = ""
    if file_type in ["txt", "markdown"]:
        try:
            text_content = content.decode("utf-8")
        except:
            text_content = content.decode("gbk", errors="ignore")
    elif file_type == "pdf":
        # TODO: 实现 PDF 解析
        text_content = "[PDF 文件 - 需要解析]"
    elif file_type == "docx":
        # TODO: 实现 Word 解析
        text_content = "[Word 文件 - 需要解析]"
    
    return text_content, file_type


def process_link(url: str) -> str:
    """处理链接，提取网页内容
    
    简单实现：返回 URL。
    生产环境可使用 web_reader 工具提取内容。
    """
    # TODO: 使用 web_reader 提取网页内容
    return f"[网页内容 - {url}]"


# ---- API Routes ----


@router.get("/sources")
async def list_sources() -> JSONResponse:
    """获取知识库来源列表"""
    settings = get_settings()
    collection_name = settings.qdrant.collection_name
    
    # 获取 collection 信息
    try:
        info = get_collection_info(collection_name)
    except Exception as e:
        logger.warning(f"获取 collection 信息失败: {e}")
        info = {"points_count": 0}
    
    sources = list(_sources_db.values())
    
    return {
        "sources": sources,
        "total_chunks": info.get("points_count", 0),
    }


@router.post("/sources/upload")
async def upload_source(
    file: UploadFile = File(...),
) -> JSONResponse:
    """上传文件到知识库"""
    settings = get_settings()
    collection_name = settings.qdrant.collection_name
    
    # 确保 collection 存在
    ensure_collection_exists(collection_name)
    
    # 处理文件上传
    try:
        text_content, file_type = await process_file_upload(file)
    except Exception as e:
        logger.error(f"文件处理失败: {e}")
        raise HTTPException(status_code=500, detail=f"文件处理失败: {e}")
    
    if not text_content or text_content.startswith("["):
        raise HTTPException(status_code=400, detail="暂不支持此文件格式或文件为空")
    
    # 解析为文本块
    chunks = parse_document(text_content, file_type)
    
    if not chunks:
        raise HTTPException(status_code=400, detail="无法从文件中提取有效内容")
    
    # 获取 embedding
    try:
        embeddings = get_embeddings(chunks)
    except Exception as e:
        logger.error(f"Embedding 失败: {e}")
        raise HTTPException(status_code=500, detail=f"生成向量失败: {e}")
    
    # 插入向量
    source_id = str(uuid.uuid4())
    points = []
    
    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        # 使用纯 UUID 作为 point ID
        point_id = str(uuid.uuid4())
        points.append({
            "id": point_id,
            "vector": embedding,
            "payload": {
                "source_id": source_id,
                "source_name": file.filename,
                "chunk_index": i,
                "content": chunk,
                "file_type": file_type,
            },
        })
    
    try:
        upsert_vectors(collection_name, points)
    except Exception as e:
        logger.error(f"向量存储失败: {e}")
        raise HTTPException(status_code=500, detail=f"向量存储失败: {e}")
    
    # 保存来源元数据
    source_info = {
        "id": source_id,
        "name": file.filename,
        "type": file_type,
        "size": len(text_content),
        "chunk_count": len(chunks),
        "created_at": "now",
    }
    _sources_db[source_id] = source_info
    
    return {
        "success": True,
        "source": source_info,
    }


@router.post("/sources/link")
async def add_link(url: str = Form(...)) -> JSONResponse:
    """添加网页链接到知识库"""
    settings = get_settings()
    collection_name = settings.qdrant.collection_name

    ensure_collection_exists(collection_name)

    # 处理链接
    text_content = process_link(url)

    # 解析为文本块
    chunks = parse_document(text_content, "link")

    # 获取 embedding
    embeddings = get_embeddings(chunks)

    # 插入向量
    source_id = str(uuid.uuid4())
    points = []

    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        # 使用纯 UUID 作为 point ID
        point_id = str(uuid.uuid4())
        points.append({
            "id": point_id,
            "vector": embedding,
            "payload": {
                "source_id": source_id,
                "source_name": url,
                "chunk_index": i,
                "content": chunk,
                "file_type": "link",
            },
        })

    upsert_vectors(collection_name, points)

    # 保存来源元数据
    source_info = {
        "id": source_id,
        "name": url,
        "type": "link",
        "size": len(text_content),
        "chunk_count": len(chunks),
        "created_at": "now",
    }
    _sources_db[source_id] = source_info

    return {
        "success": True,
        "source": source_info,
    }


@router.post("/sources/text")
async def add_text_source(name: str = Form(...), content: str = Form(...)) -> JSONResponse:
    """添加纯文本到知识库"""
    settings = get_settings()
    collection_name = settings.qdrant.collection_name

    ensure_collection_exists(collection_name)

    if not content or not content.strip():
        raise HTTPException(status_code=400, detail="文本内容不能为空")

    # 解析为文本块
    chunks = parse_document(content, "text")

    if not chunks:
        raise HTTPException(status_code=400, detail="无法解析文本内容")

    # 获取 embedding
    try:
        embeddings = get_embeddings(chunks)
    except Exception as e:
        logger.error(f"Embedding 失败: {e}")
        raise HTTPException(status_code=500, detail=f"生成向量失败: {e}")

    # 插入向量
    source_id = str(uuid.uuid4())
    points = []

    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        # 使用纯 UUID 作为 point ID
        point_id = str(uuid.uuid4())
        points.append({
            "id": point_id,
            "vector": embedding,
            "payload": {
                "source_id": source_id,
                "source_name": name,
                "chunk_index": i,
                "content": chunk,
                "file_type": "text",
            },
        })

    try:
        upsert_vectors(collection_name, points)
    except Exception as e:
        logger.error(f"向量存储失败: {e}")
        raise HTTPException(status_code=500, detail=f"向量存储失败: {e}")

    # 保存来源元数据
    source_info = {
        "id": source_id,
        "name": name,
        "type": "text",
        "size": len(content),
        "chunk_count": len(chunks),
        "created_at": "now",
    }
    _sources_db[source_id] = source_info

    return {
        "success": True,
        "source": source_info,
    }


@router.delete("/sources/{source_id}")
async def delete_source(source_id: str) -> JSONResponse:
    """删除知识来源"""
    settings = get_settings()
    collection_name = settings.qdrant.collection_name
    
    if source_id not in _sources_db:
        raise HTTPException(status_code=404, detail="来源不存在")
    
    # 删除向量
    client = get_qdrant_client()
    
    # 构建过滤条件：删除该来源的所有向量
    filter_condition = Filter(
        must=[FieldCondition(key="source_id", match=MatchValue(value=source_id))]
    )
    
    try:
        client.delete(
            collection_name=collection_name,
            points_selector=filter_condition,
        )
    except Exception as e:
        logger.warning(f"删除向量失败: {e}")
    
    # 删除来源元数据
    del _sources_db[source_id]
    
    return {"success": True}


@router.post("/search")
async def search_knowledge(req: SearchRequest) -> JSONResponse:
    """语义检索知识库"""
    settings = get_settings()
    collection_name = settings.qdrant.collection_name
    
    # 获取查询的 embedding
    try:
        query_vector = get_embedding(req.query)
    except Exception as e:
        logger.error(f"查询 embedding 失败: {e}")
        raise HTTPException(status_code=500, detail=f"查询向量生成失败: {e}")
    
    # 检索
    try:
        results = search_vectors(
            collection_name,
            query_vector,
            limit=req.limit,
        )
    except Exception as e:
        logger.error(f"检索失败: {e}")
        raise HTTPException(status_code=500, detail=f"检索失败: {e}")
    
    # 格式化结果
    formatted_results = []
    for r in results:
        formatted_results.append({
            "id": r["id"],
            "score": r["score"],
            "content": r["payload"].get("content", ""),
            "source_name": r["payload"].get("source_name", ""),
            "source_id": r["payload"].get("source_id", ""),
        })
    
    return {
        "query": req.query,
        "results": formatted_results,
    }


@router.post("/chat")
async def chat_with_knowledge(req: ChatRequest) -> JSONResponse:
    """基于知识库进行对话"""
    settings = get_settings()
    collection_name = settings.qdrant.collection_name
    
    # 1. 检索相关上下文
    try:
        query_vector = get_embedding(req.message)
        results = search_vectors(
            collection_name,
            query_vector,
            limit=5,
        )
    except Exception as e:
        logger.error(f"检索失败: {e}")
        raise HTTPException(status_code=500, detail=f"知识检索失败: {e}")
    
    # 构建上下文
    context_parts = []
    citations = []
    
    for r in results:
        content = r["payload"].get("content", "")
        source_name = r["payload"].get("source_name", "")
        source_id = r["payload"].get("source_id", "")
        
        context_parts.append(f"【{source_name}】\n{content}")
        citations.append({
            "source_id": source_id,
            "source_name": source_name,
            "chunk": content[:100] + "...",
        })
    
    context = "\n\n".join(context_parts)
    
    # 2. 调用 LLM 生成回答
    try:
        from src.llm.base import ChatMessage
        from src.core.engine import get_engine
        
        engine = get_engine()
        if not engine:
            raise HTTPException(status_code=503, detail="引擎未就绪")
        
        lead = engine.get_agent("team-lead")
        if not lead:
            raise HTTPException(status_code=503, detail="team-lead 不可用")
        
        # 构建 prompt
        prompt = f"""你是一个专业的知识库问答助手。请根据以下参考资料回答用户的问题。

要求：
1. 只根据提供的参考资料回答，不要编造信息
2. 如果参考资料中有相关信息，给出详细回答
3. 如果参考资料中没有足够信息，请明确告知用户

参考资料：
{context}

用户问题：{req.message}

请给出回答："""
        
        # 添加历史对话（可选）
        messages = [
            ChatMessage(role="system", content="你是一个专业的知识库问答助手，擅长根据提供的参考资料回答用户问题。"),
        ]
        
        # 添加历史消息
        for msg in req.history[-5:]:  # 只保留最近5条
            messages.append(ChatMessage(role=msg["role"], content=msg["content"]))
        
        messages.append(ChatMessage(role="user", content=prompt))
        
        response = await lead.llm.chat(messages)
        answer = response.content
        
    except Exception as e:
        logger.error(f"LLM 调用失败: {e}")
        answer = f"生成回答时发生错误: {e}"
    
    return {
        "answer": answer,
        "citations": citations,
    }


@router.get("/stats")
async def get_stats() -> JSONResponse:
    """获取知识库统计信息"""
    settings = get_settings()
    collection_name = settings.qdrant.collection_name
    
    try:
        info = get_collection_info(collection_name)
    except Exception as e:
        info = {"points_count": 0, "vectors_count": 0}
    
    return {
        "total_sources": len(_sources_db),
        "total_chunks": info.get("points_count", 0),
        "collection_name": collection_name,
    }
