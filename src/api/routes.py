"""REST API 路由"""

from __future__ import annotations

import asyncio
import re

from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel

from src.core.engine import get_engine
from src.core.message_bus import Message, MessageType, get_message_bus
from src.core.task import Task
from src.core.team import TeamMember, get_team_manager
from src.memory.memory_system import get_memory_system
from src.llm.base import ChatMessage
from src.stores.role_registry import get_role_registry

router = APIRouter(prefix="/api")


# ---- Request/Response Models ----


class CreateTeamRequest(BaseModel):
    name: str
    description: str = ""


class AddMemberRequest(BaseModel):
    agent_name: str
    role: str
    role_label: str = ""


class SubmitTaskRequest(BaseModel):
    title: str
    description: str
    team_id: str = ""
    file_paths: list[str] = []  # 本地文件/目录路径，后端自动读取内容
    enable_review: bool = False  # 是否启用审查专家核查
    scene_type: str = ""  # 场景子模板 ID（如 meeting_notice）
    scene_category: str = ""  # 场景分类（如 official_writing）
    scene_form_data: dict[str, str] = {}  # 场景表单已采集的结构化字段


class NoteSuggestRequest(BaseModel):
    title: str = ""
    content: str
    need_divergent: bool = False
    use_web_search: bool = True
    team_id: str = ""


class CreateRoleRequest(BaseModel):
    name: str
    display_name: str
    label: str = "Explorer"
    description: str = ""
    system_prompt: str = ""


# ---- Team Routes ----


@router.get("/teams")
async def list_teams():
    """获取所有团队"""
    tm = get_team_manager()
    return {"teams": [t.to_dict() for t in tm.list_teams()]}


@router.post("/teams")
async def create_team(req: CreateTeamRequest):
    """创建团队"""
    tm = get_team_manager()
    team = tm.create_team(name=req.name, description=req.description)

    # 自动添加 team-lead 作为成员
    engine = get_engine()
    if engine:
        lead = engine.get_agent("team-lead")
        if lead:
            tm.add_member(
                team.id,
                TeamMember(
                    agent_name=lead.name,
                    role=lead.role,
                    role_label=lead.role_label,
                ),
            )

    # 持久化
    await tm.save_team_to_db(team)

    return team.to_dict()


@router.get("/teams/{team_id}")
async def get_team(team_id: str):
    """获取团队详情"""
    tm = get_team_manager()
    team = tm.get_team(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="团队不存在")
    return team.to_dict()


@router.post("/teams/{team_id}/members")
async def add_member(team_id: str, req: AddMemberRequest):
    """添加团队成员"""
    tm = get_team_manager()
    member = TeamMember(
        agent_name=req.agent_name,
        role=req.role,
        role_label=req.role_label,
    )
    success = tm.add_member(team_id, member)
    if not success:
        raise HTTPException(status_code=404, detail="团队不存在")

    # 持久化到数据库
    team = tm.get_team(team_id)
    if team:
        await tm.save_team_to_db(team)

    return {"success": True}


@router.patch("/teams/{team_id}")
async def rename_team(team_id: str, req: dict):
    """重命名团队"""
    tm = get_team_manager()
    new_name = req.get("name", "").strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="名称不能为空")
    success = tm.rename_team(team_id, new_name)
    if not success:
        raise HTTPException(status_code=404, detail="团队不存在")
    team = tm.get_team(team_id)
    if team:
        await tm.save_team_to_db(team)
    return {"success": True, "name": new_name}


@router.delete("/teams/{team_id}")
async def delete_team(team_id: str):
    """删除团队"""
    tm = get_team_manager()
    success = tm.delete_team(team_id)
    if not success:
        raise HTTPException(status_code=404, detail="团队不存在")
    await tm.delete_team_from_db(team_id)
    return {"success": True}


@router.post("/teams/{team_id}/stop")
async def stop_task(team_id: str):
    """终止当前团队正在执行的任务"""
    bg_task = _running_tasks.get(team_id)
    if not bg_task or bg_task.done():
        raise HTTPException(status_code=404, detail="没有正在运行的任务")

    bg_task.cancel()
    # 等待取消完成（最多 3 秒）
    try:
        await asyncio.wait_for(asyncio.shield(bg_task), timeout=3.0)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        pass

    return {"success": True}


# ---- Task Routes ----


# 运行中的后台任务，按 team_id 索引
_running_tasks: dict[str, asyncio.Task] = {}


def _short_title_from_text(text: str, limit: int = 10) -> str:
    """从文本提取一个不超过 limit 的简短标题"""
    if not text:
        return ""
    cleaned = " ".join(text.strip().split())
    cleaned = re.sub(r"^[#>*\-\d\.\s]+", "", cleaned)
    if not cleaned:
        return ""
    return cleaned[:limit]


async def _fallback_rename_team_after_stop(task: Task):
    """终止场景下的兜底重命名（不依赖 LLM）"""
    from src.core.team import get_team_manager

    tm = get_team_manager()
    team = tm.get_team(task.team_id)
    if not team or not team.name.startswith("新对话"):
        return

    bus = get_message_bus()
    history = bus.get_history(task.team_id)

    user_text = ""
    for msg in history:
        if msg.sender == "user" and (msg.content or "").strip():
            user_text = msg.content
            break
    if not user_text:
        user_text = task.description

    new_name = _short_title_from_text(user_text, limit=10)
    if not new_name:
        return

    old_name = team.name
    tm.rename_team(task.team_id, new_name)
    await tm.save_team_to_db(team)
    logger.info(f"终止后兜底重命名: {old_name} -> {new_name}")

    await bus.publish(Message(
        type=MessageType.SYSTEM,
        sender="system",
        team_id=task.team_id,
        content="",
        metadata={
            "action": "team_renamed",
            "team_id": task.team_id,
            "new_name": new_name,
        },
    ))


async def _run_task_background(task: Task):
    """在后台执行任务，异常不会中断主流程"""
    engine = get_engine()
    if not engine:
        return
    try:
        await engine.submit_task(task)
    except asyncio.CancelledError:
        logger.info(f"任务已被用户终止: {task.title}")
        # 清理流式状态 + 发送终止消息
        bus = get_message_bus()
        history = bus.get_history(task.team_id)
        for msg in history:
            if msg.metadata.get("streaming"):
                await bus.update_message_content(
                    task.team_id, msg.id, msg.content or "（已终止）",
                    metadata_updates={"streaming": False},
                )
                await bus.publish(Message(
                    type=MessageType.STREAM_CHUNK,
                    sender="system", team_id=task.team_id, content="",
                    metadata={"target_id": msg.id, "stream_done": True},
                ))
        await bus.publish(Message(
            type=MessageType.STATUS_UPDATE,
            sender="system",
            team_id=task.team_id,
            content="对话已被用户终止",
            metadata={"status": "completed", "stopped": True},
        ))

        # 用户主动终止时也尝试自动重命名对话（首次对话场景）
        try:
            lead = engine.get_agent("team-lead")
            if lead and hasattr(lead, "_auto_rename_team"):
                await lead._auto_rename_team(task)  # type: ignore[attr-defined]
        except Exception as rename_err:
            logger.warning(f"终止后自动重命名失败（不影响主流程）: {rename_err}")

        # LLM 重命名失败或被取消时，使用本地规则兜底重命名
        try:
            await _fallback_rename_team_after_stop(task)
        except Exception as rename_err:
            logger.warning(f"终止后兜底重命名失败（不影响主流程）: {rename_err}")
    except Exception as e:
        logger.error(f"后台任务执行失败: {e}")
        bus = get_message_bus()
        await bus.publish(Message(
            type=MessageType.SYSTEM,
            sender="system",
            team_id=task.team_id,
            content=f"任务执行失败: {str(e)}",
            metadata={"error": True},
        ))
    finally:
        _running_tasks.pop(task.team_id, None)


@router.post("/tasks")
async def submit_task(req: SubmitTaskRequest):
    """提交任务（异步）

    立即返回 task_id，Agent 在后台执行，
    进度通过 WebSocket 实时推送。
    支持通过 file_paths 传入本地文件/目录路径，自动读取内容。
    """
    engine = get_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="引擎未就绪")

    # 如果有文件路径，读取文件内容并追加到任务描述
    full_description = req.description
    if req.file_paths:
        from src.tools.file_reader import read_paths

        file_content = read_paths(req.file_paths)
        full_description = (
            f"{req.description}\n\n"
            f"--- 以下是需要分析的文件内容 ---\n\n"
            f"{file_content}"
        )

    task_metadata: dict = {}
    if req.file_paths:
        task_metadata["file_paths"] = req.file_paths
    task_metadata["enable_review"] = req.enable_review
    if req.scene_type:
        task_metadata["scene_type"] = req.scene_type
    if req.scene_category:
        task_metadata["scene_category"] = req.scene_category
    if req.scene_form_data:
        task_metadata["scene_form_data"] = req.scene_form_data

    task = Task(
        title=req.title,
        description=full_description,
        assigned_to="team-lead",
        assigned_by="user",
        team_id=req.team_id,
        metadata=task_metadata,
    )

    # 先发一条用户消息到消息总线（显示原始描述，不含文件内容，太长了）
    bus = get_message_bus()
    user_msg = req.description
    if req.file_paths:
        paths_str = ", ".join(req.file_paths)
        user_msg += f"\n\n📎 附加文件: {paths_str}"

    await bus.publish(Message(
        type=MessageType.AGENT_MESSAGE,
        sender="user",
        team_id=req.team_id,
        content=user_msg,
        metadata={"source": "user", "task_id": task.id, "file_paths": req.file_paths},
    ))

    # 后台异步执行，不阻塞响应；跟踪 asyncio.Task 以支持取消
    bg_task = asyncio.create_task(_run_task_background(task))
    _running_tasks[req.team_id] = bg_task

    return {"task_id": task.id, "status": "submitted"}


@router.post("/notes/suggest")
async def suggest_note(req: NoteSuggestRequest):
    """根据笔记内容生成联想建议（仅大模型 + 联网搜索）。"""
    engine = get_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="引擎未就绪")

    lead = engine.get_agent("team-lead")
    if not lead:
        raise HTTPException(status_code=503, detail="team-lead 不可用")

    mode_hint = (
        "【发散模式】请跨场景、跨角色、跨时间尺度发散，优先提出具有启发性和探索价值的问题。"
        if req.need_divergent
        else "【聚焦模式】请围绕当前目标给出可执行、可落地、可验证的问题。"
    )
    search_context = ""
    search_refs: list[dict] = []
    if req.use_web_search:
        try:
            from src.tools.web_search import (
                web_search,
                web_search_news,
                build_references,
                format_search_results,
            )

            query_seed = f"{req.title} {req.content[:180]}".strip()
            query = " ".join(query_seed.split())
            if req.need_divergent:
                results = await web_search(f"{query} 趋势 案例 方法论", max_results=5)
            else:
                results = await web_search(f"{query} 实施 风险 清单", max_results=5)
            if not results:
                results = await web_search_news(query, max_results=5)
            search_refs = build_references(results, start_index=1)
            search_context = format_search_results(results, query, search_refs)
        except Exception as e:
            logger.warning(f"笔记联想联网搜索失败，降级为纯模型生成: {e}")

    user_prompt = (
        f"你是笔记助理。{mode_hint}\n\n"
        "你的目标是拓展用户笔记，请仅输出 3 个高质量推荐问题，帮助用户继续思考。\n"
        "输出格式要求（Markdown）：\n"
        "### 推荐问题\n"
        "1. ...\n"
        "2. ...\n"
        "3. ...\n\n"
        "问题必须满足：\n"
        "- 与用户笔记强相关\n"
        "- 具体、可执行，避免空泛\n"
        "- 彼此角度不同（目标、风险、落地等）\n\n"
        f"笔记标题：{req.title or '未命名笔记'}\n"
        f"笔记内容：\n{req.content.strip()}"
    )
    if search_context:
        user_prompt += (
            "\n\n---\n\n"
            "以下是联网搜索结果，请作为补充参考（可引用来源，避免杜撰）：\n"
            f"{search_context}"
        )

    response = await lead.llm.chat(
        messages=[
            ChatMessage(
                role="system",
                content="你是严谨且实用的中文笔记联想助手，擅长基于上下文提出高质量问题。",
            ),
            ChatMessage(role="user", content=user_prompt),
        ],
        # 不显式传 temperature / max_tokens，默认与对话链路一致
    )
    return {
        "suggestion": response.content,
        "model": lead.llm.model,
        "used_web_search": bool(search_context),
        "references": search_refs,
    }


# ---- Messages Routes ----


@router.get("/teams/{team_id}/messages")
async def get_team_messages(team_id: str):
    """获取团队消息历史"""
    bus = get_message_bus()
    messages = bus.get_history(team_id)
    return {"messages": [m.to_dict() for m in messages]}


# ---- Roles Routes ----


@router.get("/roles")
async def list_roles():
    """列出所有角色"""
    registry = get_role_registry()
    return {"roles": [r.to_dict() for r in registry.list_roles()]}


@router.post("/roles")
async def create_role(req: CreateRoleRequest):
    """动态创建角色（写入 YAML + 创建 Agent）"""
    registry = get_role_registry()

    # 检查是否重复
    if registry.get(req.name):
        raise HTTPException(status_code=409, detail=f"角色 '{req.name}' 已存在")

    from src.stores.role_registry import RoleDefinition

    role_def = RoleDefinition(
        name=req.name,
        display_name=req.display_name,
        label=req.label,
        description=req.description,
        system_prompt=req.system_prompt or f"你是一名{req.display_name}。{req.description}",
    )

    # 注册到内存 + 持久化到 YAML
    registry.register(role_def)
    registry.save_role(role_def)

    # 动态创建 Agent 实例
    engine = get_engine()
    if engine:
        from src.agents.base import AgentBase
        from src.core.message_bus import get_message_bus
        from src.llm.factory import create_llm_adapter
        from src.config import get_settings
        from src.memory.memory_system import get_memory_system

        llm = create_llm_adapter(get_settings().llm)
        bus = get_message_bus()
        memory = get_memory_system()

        agent = AgentBase(
            name=role_def.name,
            role=role_def.name,
            role_label=role_def.label,
            system_prompt=role_def.system_prompt,
            llm=llm,
            message_bus=bus,
            memory=memory,
        )
        engine.register_agent(agent)

    return role_def.to_dict()


# ---- Model Routes ----


# 千问开源模型列表（DashScope 支持的模型）
QWEN_MODELS = [
    {"id": "qwen-plus", "name": "Qwen-Plus", "desc": "通用增强 · 均衡性价比"},
    {"id": "qwen-max", "name": "Qwen-Max", "desc": "旗舰模型 · 最强推理"},
    {"id": "qwen-turbo", "name": "Qwen-Turbo", "desc": "极速响应 · 低成本"},
    {"id": "qwen-long", "name": "Qwen-Long", "desc": "长文本 · 100 万 token"},
    {"id": "qwen3-235b-a22b", "name": "Qwen3-235B", "desc": "开源最大 · MoE 架构"},
    {"id": "qwen3-32b", "name": "Qwen3-32B", "desc": "开源 32B · 高性价比"},
    {"id": "qwen3-14b", "name": "Qwen3-14B", "desc": "开源 14B · 轻量高效"},
    {"id": "qwen3-8b", "name": "Qwen3-8B", "desc": "开源 8B · 快速推理"},
    {"id": "qwen2.5-72b-instruct", "name": "Qwen2.5-72B", "desc": "开源 72B · 强推理"},
    {"id": "qwen2.5-32b-instruct", "name": "Qwen2.5-32B", "desc": "开源 32B · 均衡"},
]


class SwitchModelRequest(BaseModel):
    model_id: str


@router.get("/models")
async def list_models():
    """获取可用模型列表和当前模型"""
    engine = get_engine()
    current = ""
    if engine:
        lead = engine.get_agent("team-lead")
        if lead:
            current = lead.llm.model
    return {"models": QWEN_MODELS, "current": current}


@router.post("/models/switch")
async def switch_model(req: SwitchModelRequest):
    """切换当前使用的模型"""
    valid_ids = {m["id"] for m in QWEN_MODELS}
    if req.model_id not in valid_ids:
        raise HTTPException(status_code=400, detail=f"不支持的模型: {req.model_id}")

    engine = get_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="引擎未就绪")

    # 1. 更新运行时内存中的模型
    lead = engine.get_agent("team-lead")
    if lead:
        lead.llm.model = req.model_id
        logger.info(f"模型已切换（运行时）: {req.model_id}")

    # 2. 持久化到 .env 文件
    try:
        from src.config import ROOT_DIR
        env_path = ROOT_DIR / ".env"
        if env_path.exists():
            lines = env_path.read_text(encoding="utf-8").splitlines()
            new_lines = []
            found = False
            for line in lines:
                if line.startswith("OPENAI_MODEL="):
                    new_lines.append(f"OPENAI_MODEL={req.model_id}")
                    found = True
                else:
                    new_lines.append(line)
            if not found:
                new_lines.append(f"OPENAI_MODEL={req.model_id}")
            env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
            logger.info(f"模型已持久化到 .env: {req.model_id}")
    except Exception as e:
        logger.warning(f"持久化模型到 .env 失败（运行时已生效）: {e}")

    return {"success": True, "model": req.model_id}


# ---- iMessage Bot Routes ----


class ImessageBotStartRequest(BaseModel):
    phone: str = ""  # 留空则从 .env 读取


@router.post("/imessage-bot/start")
async def start_imessage_bot(req: ImessageBotStartRequest):
    """激活 iMessage Bot（从待命变为活跃）"""
    from src.tools.imessage_bot import get_imessage_bot

    bot = get_imessage_bot()

    # 如果还没在监听，先启动监听
    if not bot.is_listening:
        phone = req.phone.strip() or ""
        success = await bot.start_listening(phone)
        if not success:
            raise HTTPException(status_code=500, detail="启动失败，请检查配置或权限")

    # 激活
    await bot.activate()
    return {"success": True, "status": bot.status, "phone": bot.phone}


@router.post("/imessage-bot/stop")
async def stop_imessage_bot():
    """让 Bot 回到待命模式"""
    from src.tools.imessage_bot import get_imessage_bot

    bot = get_imessage_bot()
    await bot.deactivate()
    return {"success": True, "status": bot.status}


@router.get("/imessage-bot/status")
async def imessage_bot_status():
    """查询 iMessage 机器人状态"""
    from src.tools.imessage_bot import get_imessage_bot

    bot = get_imessage_bot()
    return {
        "running": bot.is_running,
        "listening": bot.is_listening,
        "status": bot.status,
        "phone": bot.phone,
    }


# ---- Info Routes ----


@router.get("/agents")
async def list_agents():
    """列出所有 Agent"""
    engine = get_engine()
    if not engine:
        return {"agents": []}
    return {
        "agents": [
            {
                "name": a.name,
                "role": a.role,
                "role_label": a.role_label,
                "status": a.status,
            }
            for a in engine.list_agents()
        ]
    }


@router.get("/memory/stats")
async def memory_stats():
    """获取记忆系统统计"""
    mem = get_memory_system()
    if not mem:
        return {"stats": {}}
    return {"stats": mem.get_stats()}


# ---- Scene Routes ----


@router.get("/scenes")
async def list_scenes():
    """获取所有场景模板"""
    from src.stores.scene_registry import get_scene_registry

    registry = get_scene_registry()
    return {"scenes": registry.to_list()}


# ---- Export Routes ----


class ExportWordRequest(BaseModel):
    content: str
    title: str = ""
    doc_type: str = "general"  # general / notice / report / speech


@router.post("/export/word")
async def export_word(req: ExportWordRequest):
    """将 Markdown 内容导出为 Word 文档"""
    from src.tools.doc_exporter import export_markdown_to_word

    try:
        file_path = export_markdown_to_word(
            content=req.content,
            title=req.title,
            doc_type=req.doc_type,
        )
        from fastapi.responses import FileResponse

        return FileResponse(
            path=file_path,
            filename=file_path.name,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    except Exception as e:
        logger.error(f"Word 导出失败: {e}")
        raise HTTPException(status_code=500, detail=f"导出失败: {e}")
