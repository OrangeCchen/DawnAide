"""Agent 间消息总线

消息总线是 Agent 之间通信的核心设施。
支持发布/订阅模式和直接消息。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Coroutine
from uuid import uuid4

from loguru import logger


class MessageType(str, Enum):
    """消息类型"""

    TASK_ASSIGNMENT = "task_assignment"  # 任务分配
    TASK_RESULT = "task_result"  # 任务结果
    AGENT_MESSAGE = "agent_message"  # Agent 普通消息
    STATUS_UPDATE = "status_update"  # 状态更新
    SYSTEM = "system"  # 系统消息
    STREAM_CHUNK = "stream_chunk"  # 流式输出片段（不持久化）


@dataclass
class Message:
    """消息体"""

    id: str = field(default_factory=lambda: uuid4().hex[:12])
    type: MessageType = MessageType.AGENT_MESSAGE
    sender: str = ""  # Agent name
    receiver: str = ""  # Agent name, 空表示广播
    team_id: str = ""
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type.value,
            "sender": self.sender,
            "receiver": self.receiver,
            "team_id": self.team_id,
            "content": self.content,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }


# 订阅回调类型
MessageHandler = Callable[[Message], Coroutine[Any, Any, None]]


class MessageBus:
    """消息总线

    支持:
    - 订阅特定团队的消息
    - 订阅特定消息类型
    - 直接发送消息给指定 Agent
    - 广播消息给团队所有成员
    """

    def __init__(self):
        # team_id -> list of handlers
        self._team_handlers: dict[str, list[MessageHandler]] = {}
        # agent_name -> handler
        self._agent_handlers: dict[str, MessageHandler] = {}
        # 全局处理器（用于 WebSocket 推送等）
        self._global_handlers: list[MessageHandler] = []
        # 消息历史 team_id -> list of messages
        self._history: dict[str, list[Message]] = {}
        self._lock = asyncio.Lock()

    def subscribe_team(self, team_id: str, handler: MessageHandler):
        """订阅团队消息"""
        if team_id not in self._team_handlers:
            self._team_handlers[team_id] = []
        self._team_handlers[team_id].append(handler)

    def subscribe_agent(self, agent_name: str, handler: MessageHandler):
        """注册 Agent 的消息处理器"""
        self._agent_handlers[agent_name] = handler

    def subscribe_global(self, handler: MessageHandler):
        """注册全局消息处理器（如 WebSocket 推送）"""
        self._global_handlers.append(handler)

    def unsubscribe_global(self, handler: MessageHandler):
        """取消全局处理器"""
        if handler in self._global_handlers:
            self._global_handlers.remove(handler)

    async def publish(self, message: Message):
        """发布消息"""
        is_stream_chunk = message.type == MessageType.STREAM_CHUNK
        team_id = message.team_id

        if not is_stream_chunk:
            async with self._lock:
                # 记录内存历史（流式片段不记录）
                if team_id not in self._history:
                    self._history[team_id] = []
                self._history[team_id].append(message)

                # 持久化到数据库（在锁内执行，保证与内存历史的一致性）
                try:
                    from src.storage.database import get_database
                    db = await get_database()
                    await db.save_message(message.to_dict())
                except Exception as e:
                    logger.warning(f"消息持久化失败（不影响运行）: {e}")

            logger.debug(
                f"消息发布: [{message.type.value}] {message.sender} -> "
                f"{message.receiver or '(broadcast)'}: {message.content[:80]}..."
            )

        # 通知全局处理器（stream_chunk 也需要广播到 WebSocket）
        for handler in self._global_handlers:
            try:
                await handler(message)
            except Exception as e:
                logger.error(f"全局处理器错误: {e}")

        # 流式片段只需要广播到 WebSocket，不需要分发给 Agent
        if is_stream_chunk:
            return

        # 如果有指定接收者，直接发送
        if message.receiver and message.receiver in self._agent_handlers:
            try:
                await self._agent_handlers[message.receiver](message)
            except Exception as e:
                logger.error(f"Agent 处理器错误 [{message.receiver}]: {e}")
            return

        # 否则广播给团队
        if team_id in self._team_handlers:
            for handler in self._team_handlers[team_id]:
                try:
                    await handler(message)
                except Exception as e:
                    logger.error(f"团队处理器错误: {e}")

    async def update_message_content(
        self,
        team_id: str,
        msg_id: str,
        content: str,
        metadata_updates: dict | None = None,
    ):
        """更新已有消息的内容和 metadata（流式结束后调用）"""
        import json as _json

        msgs = self._history.get(team_id, [])
        updated_meta_str = None
        for m in msgs:
            if m.id == msg_id:
                m.content = content
                if metadata_updates:
                    m.metadata.update(metadata_updates)
                updated_meta_str = _json.dumps(m.metadata, ensure_ascii=False)
                break

        # 同步更新数据库
        try:
            from src.storage.database import get_database
            db = await get_database()
            if updated_meta_str is not None:
                await db._db.execute(
                    "UPDATE messages SET content = ?, metadata = ? WHERE id = ?",
                    (content, updated_meta_str, msg_id),
                )
            else:
                await db._db.execute(
                    "UPDATE messages SET content = ? WHERE id = ?",
                    (content, msg_id),
                )
            await db._db.commit()
        except Exception as e:
            logger.warning(f"更新消息内容失败: {e}")

    def get_history(self, team_id: str) -> list[Message]:
        """获取团队消息历史"""
        return self._history.get(team_id, [])

    def get_all_teams_history(self) -> dict[str, list[Message]]:
        """获取所有团队的消息历史"""
        return dict(self._history)

    async def load_history_from_db(self):
        """从数据库恢复所有消息历史"""
        try:
            from src.storage.database import get_database
            db = await get_database()

            # 加载所有团队的消息
            import aiosqlite
            cursor = await db._db.execute(
                "SELECT DISTINCT team_id FROM messages"
            )
            team_ids = [row[0] for row in await cursor.fetchall()]

            total = 0
            for tid in team_ids:
                rows = await db.load_messages(tid)
                messages = []
                for r in rows:
                    msg = Message(
                        id=r["id"],
                        type=MessageType(r["type"]),
                        sender=r["sender"],
                        receiver=r["receiver"],
                        team_id=r["team_id"],
                        content=r["content"],
                        metadata=r["metadata"],
                        timestamp=datetime.fromisoformat(r["timestamp"]),
                    )
                    messages.append(msg)
                if messages:
                    self._history[tid] = messages
                    total += len(messages)

            if total > 0:
                logger.info(f"从数据库恢复了 {len(team_ids)} 个团队的 {total} 条消息")
        except Exception as e:
            logger.warning(f"从数据库恢复消息历史失败: {e}")


# 全局消息总线单例
_bus: MessageBus | None = None


def get_message_bus() -> MessageBus:
    """获取全局消息总线"""
    global _bus
    if _bus is None:
        _bus = MessageBus()
    return _bus
