"""应用初始化模块

精简版：启动时只创建 team-lead，其他专家由 team-lead 根据任务动态生成。
"""

from __future__ import annotations

from loguru import logger

from src.config import DATA_DIR, WRITABLE_DATA_DIR, get_settings


async def initialize_app():
    """应用初始化流程"""
    settings = get_settings()

    logger.info("=== 数字员工协作平台 POC 启动 ===")

    # 1. 确保目录结构就绪
    _ensure_directories()
    logger.info("目录结构已就绪")

    # 2. 初始化显示 Hook
    from src.display.hooks import setup_hooks

    setup_hooks()

    # 3. 加载方法论库
    from src.stores.methodology_lib import get_methodology_lib

    method_lib = get_methodology_lib()
    method_lib.load_from_directory()
    logger.info(f"方法论库已加载，共 {method_lib.count} 个方法论")

    # 4. 加载角色注册表（保留用于参考，但不再驱动 Agent 创建）
    from src.stores.role_registry import get_role_registry

    role_registry = get_role_registry()
    role_registry.load_from_directory()
    logger.info(f"角色定义库已加载，共 {role_registry.count} 个定义")

    # 4.5 加载技能注册表
    from src.stores.skill_registry import get_skill_registry

    skill_registry = get_skill_registry()
    skill_registry.load_from_directory()
    logger.info(f"技能注册表已加载，共 {skill_registry.count} 个技能")

    # 4.6 加载场景注册表
    from src.stores.scene_registry import get_scene_registry

    scene_registry = get_scene_registry()
    scene_registry.load_from_directory()
    logger.info(f"场景注册表已加载，共 {scene_registry.count} 个场景分类")

    # 5. 初始化记忆系统
    from src.memory.memory_system import create_memory_system

    memory = create_memory_system(settings.memory.budgets)

    # 6. 初始化上下文管理器
    from src.memory.context_manager import ContextManager

    ContextManager(memory=memory)

    # 7. 创建 LLM 适配器
    from src.llm.factory import create_llm_adapter

    llm = create_llm_adapter(settings.llm)

    # 8. 初始化引擎
    from src.core.engine import create_engine

    engine = create_engine()

    # 9. 连接数据库
    from src.storage.database import get_database

    await get_database()
    logger.info("数据库已连接")

    # 10. 从数据库恢复历史团队
    from src.core.team import get_team_manager

    tm = get_team_manager()
    await tm.load_teams_from_db()

    # 11. 从数据库恢复消息历史
    from src.core.message_bus import get_message_bus

    bus = get_message_bus()
    await bus.load_history_from_db()

    # 12. 创建 team-lead（其他专家由 team-lead 按需动态生成）
    from src.agents.team_lead import TeamLeadAgent

    team_lead = TeamLeadAgent(
        name="team-lead",
        llm=llm,
        message_bus=bus,
        memory=memory,
    )
    engine.register_agent(team_lead)
    logger.info("team-lead 已创建（专家将按任务需求动态生成）")

    # 13. 启动 iMessage Bot 待命监听
    try:
        from src.tools.imessage_bot import get_imessage_bot
        bot = get_imessage_bot()
        started = await bot.start_listening()
        if started:
            logger.info("iMessage Bot 待命模式已启动（发送「开启」激活）")
        else:
            logger.info("iMessage Bot 未启动（未配置或无权限）")
    except Exception as e:
        logger.warning(f"iMessage Bot 启动失败: {e}")

    logger.info("=== 应用初始化完成 ===")

    return engine


def _ensure_directories():
    """确保必要目录存在"""
    dirs = [
        DATA_DIR / "roles",
        DATA_DIR / "methodologies",
        DATA_DIR / "skills",
        DATA_DIR / "scenes",
        WRITABLE_DATA_DIR / "exports",
        WRITABLE_DATA_DIR,
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
