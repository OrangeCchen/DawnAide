"""核心引擎 - 任务调度与 Agent 管理"""

from __future__ import annotations

from loguru import logger

from src.agents.base import AgentBase
from src.core.message_bus import MessageBus, get_message_bus
from src.core.task import Task, TaskResult
from src.core.team import TeamManager, get_team_manager


class Engine:
    """核心引擎

    负责:
    - Agent 注册与管理
    - 任务提交与调度
    - 团队协调
    """

    def __init__(self, message_bus: MessageBus, team_manager: TeamManager):
        self.bus = message_bus
        self.team_manager = team_manager
        self._agents: dict[str, AgentBase] = {}
        logger.info("引擎模块已初始化")

    def register_agent(self, agent: AgentBase):
        """注册 Agent"""
        self._agents[agent.name] = agent
        logger.debug(f"Agent 已注册: {agent.name} ({agent.role})")

    def get_agent(self, name: str) -> AgentBase | None:
        """获取 Agent"""
        return self._agents.get(name)

    def list_agents(self) -> list[AgentBase]:
        """列出所有 Agent"""
        return list(self._agents.values())

    async def submit_task(self, task: Task) -> TaskResult | None:
        """提交任务到引擎"""
        logger.info(f"任务已提交: {task.title} -> {task.assigned_to}")

        agent = self.get_agent(task.assigned_to)
        if not agent:
            logger.error(f"Agent 不存在: {task.assigned_to}")
            return None

        result = await agent.receive_task(task)
        return result


# 全局单例
_engine: Engine | None = None


def get_engine() -> Engine | None:
    return _engine


def create_engine() -> Engine:
    global _engine
    bus = get_message_bus()
    tm = get_team_manager()
    _engine = Engine(message_bus=bus, team_manager=tm)
    return _engine
