"""Agent 基类"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from loguru import logger

from src.core.message_bus import Message, MessageBus, MessageType
from src.core.task import Task, TaskResult, TaskStatus
from src.llm.base import ChatMessage, LLMAdapter


class AgentBase:
    """所有 Agent 的基类

    提供:
    - LLM 对话能力
    - 消息收发（自动在执行前后发送状态消息）
    - 任务处理
    """

    def __init__(
        self,
        name: str,
        role: str,
        role_label: str,
        system_prompt: str,
        llm: LLMAdapter,
        message_bus: MessageBus,
        memory: Any = None,
        skills: list[str] | None = None,
        register_bus: bool = True,
    ):
        self.name = name
        self.role = role
        self.role_label = role_label
        self.system_prompt = system_prompt
        self.llm = llm
        self.bus = message_bus
        self.memory = memory
        self.skills = skills or []
        self.status = "idle"
        self._conversation: list[ChatMessage] = []

        # 注册到消息总线（临时 Agent 可跳过）
        if register_bus:
            self.bus.subscribe_agent(self.name, self._on_message)
        logger.info(f"Agent 已创建: {name} (role={role})")

    def _get_system_prompt(self) -> str:
        """获取带当前时间的系统提示"""
        now = datetime.now()
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        time_info = (
            f"\n\n[系统信息] 当前时间: {now.strftime('%Y年%m月%d日 %H:%M')} "
            f"{weekdays[now.weekday()]}"
        )
        return self.system_prompt + time_info

    async def _on_message(self, message: Message):
        """消息回调（由消息总线调用）"""
        if message.type == MessageType.TASK_ASSIGNMENT:
            task_data = message.metadata.get("task")
            if task_data:
                task = Task(**task_data) if isinstance(task_data, dict) else task_data
                await self.receive_task(task)

    async def receive_task(self, task: Task) -> TaskResult:
        """接收并执行任务"""
        self.status = "working"
        logger.info(f"[{self.name}] 收到任务: {task.title}")

        try:
            result = await self.execute_task(task)
            self.status = "idle"

            # 自动发送完成消息
            status_label = "A_OK" if result.status == TaskStatus.COMPLETED else "FAILED"
            await self.send_message(
                content=result.content,
                team_id=task.team_id,
                msg_type=MessageType.TASK_RESULT,
                metadata={
                    "result": result.to_dict(),
                    "status_label": status_label,
                },
            )

            return result
        except Exception as e:
            logger.error(f"[{self.name}] 任务执行失败: {e}")
            self.status = "idle"
            await self.send_message(
                content=f"任务执行失败: {str(e)}",
                team_id=task.team_id,
                msg_type=MessageType.TASK_RESULT,
                metadata={"status_label": "FAILED"},
            )
            return TaskResult(
                task_id=task.id,
                agent_name=self.name,
                status=TaskStatus.FAILED,
                content=f"任务执行失败: {str(e)}",
            )

    async def execute_task(self, task: Task) -> TaskResult:
        """执行任务的核心逻辑（子类可覆写）

        默认实现：发送开始消息 -> 调用 LLM -> 返回结果
        """
        # 发送开始消息
        await self.send_message(
            content=f"{self.role_label} 开始执行: {task.title}...",
            team_id=task.team_id,
            msg_type=MessageType.STATUS_UPDATE,
            metadata={"status": "working"},
        )

        response = await self.think(
            f"请执行以下任务:\n\n标题: {task.title}\n描述: {task.description}"
        )
        return TaskResult(
            task_id=task.id,
            agent_name=self.name,
            status=TaskStatus.COMPLETED,
            content=response,
        )

    async def think(self, user_input: str, system_prompt: str | None = None) -> str:
        """调用 LLM 进行推理（非流式）

        Args:
            user_input: 用户输入
            system_prompt: 可选的 system prompt 覆盖，传入后替代默认的 self._get_system_prompt()
        """
        sys_prompt = system_prompt if system_prompt is not None else self._get_system_prompt()
        messages = [
            ChatMessage(role="system", content=sys_prompt),
            *self._conversation,
            ChatMessage(role="user", content=user_input),
        ]

        response = await self.llm.chat(messages)

        # 记录对话历史
        self._conversation.append(ChatMessage(role="user", content=user_input))
        self._conversation.append(ChatMessage(role="assistant", content=response.content))

        # 控制对话历史长度
        if len(self._conversation) > 20:
            self._conversation = self._conversation[-16:]

        return response.content

    async def think_stream(
        self,
        user_input: str,
        team_id: str = "",
        msg_type: MessageType = MessageType.TASK_RESULT,
        metadata: dict | None = None,
        system_prompt: str | None = None,
    ) -> str:
        """调用 LLM 流式推理，逐 token 推送到前端

        流程：
        1. 先发一条空内容消息（建立前端卡片）
        2. 逐 token 发 STREAM_CHUNK（前端追加显示）
        3. 结束后更新原消息内容 + metadata（持久化完整结果 + 统计数据）

        Args:
            system_prompt: 可选的 system prompt 覆盖，传入后替代默认的 self._get_system_prompt()
        """
        import time
        from uuid import uuid4

        sys_prompt = system_prompt if system_prompt is not None else self._get_system_prompt()
        messages = [
            ChatMessage(role="system", content=sys_prompt),
            *self._conversation,
            ChatMessage(role="user", content=user_input),
        ]

        msg_id = uuid4().hex[:12]
        meta = metadata or {}
        start_time = time.time()

        # 1. 发送初始空消息（会被持久化 + 前端创建卡片）
        init_msg = Message(
            id=msg_id,
            type=msg_type,
            sender=self.name,
            team_id=team_id,
            content="",
            metadata={**meta, "streaming": True},
        )
        await self.bus.publish(init_msg)

        # 2. 流式输出
        full_text = ""
        try:
            async for chunk in self.llm.stream_chat(messages):
                full_text += chunk
                # 发送流式片段（不持久化）
                chunk_msg = Message(
                    type=MessageType.STREAM_CHUNK,
                    sender=self.name,
                    team_id=team_id,
                    content=chunk,
                    metadata={"target_id": msg_id},
                )
                await self.bus.publish(chunk_msg)
        except Exception as e:
            logger.error(f"[{self.name}] 流式输出异常: {e}")
            if not full_text:
                # 降级到非流式
                response = await self.llm.chat(messages)
                full_text = response.content

        # 3. 计算统计数据
        elapsed = round(time.time() - start_time, 1)
        # 粗略估算 token：中文 ~1.5 token/字，英文 ~0.25 token/字，取折中
        est_tokens = max(len(full_text) * 2 // 3, 1)

        # 4. 流式结束：更新原消息内容 + metadata（持久化统计信息）
        await self.bus.update_message_content(
            team_id, msg_id, full_text,
            metadata_updates={
                "streaming": False,
                "elapsed": elapsed,
                "est_tokens": est_tokens,
                "char_count": len(full_text),
            },
        )

        # 5. 发送 stream_done 通知（前端实时更新）
        done_msg = Message(
            type=MessageType.STREAM_CHUNK,
            sender=self.name,
            team_id=team_id,
            content="",
            metadata={
                "target_id": msg_id,
                "stream_done": True,
                "elapsed": elapsed,
                "est_tokens": est_tokens,
                "char_count": len(full_text),
            },
        )
        await self.bus.publish(done_msg)

        # 记录对话历史
        self._conversation.append(ChatMessage(role="user", content=user_input))
        self._conversation.append(ChatMessage(role="assistant", content=full_text))
        if len(self._conversation) > 20:
            self._conversation = self._conversation[-16:]

        return full_text

    async def send_message(
        self,
        content: str,
        receiver: str = "",
        team_id: str = "",
        msg_type: MessageType = MessageType.AGENT_MESSAGE,
        metadata: dict | None = None,
    ):
        """发送消息"""
        message = Message(
            type=msg_type,
            sender=self.name,
            receiver=receiver,
            team_id=team_id,
            content=content,
            metadata=metadata or {},
        )
        await self.bus.publish(message)

    def reset_conversation(self):
        """重置对话历史"""
        self._conversation.clear()
