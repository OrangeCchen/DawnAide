"""分区记忆系统

支持多分区的上下文管理，每个分区有独立的 token 预算。
分区类型：
- user: 用户级别（跨会话持久化）
- session: 会话级别（单次会话内）
- task: 任务级别（单个任务内）
- agent: Agent 级别（Agent 私有记忆）
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from loguru import logger


@dataclass
class MemoryEntry:
    """记忆条目"""

    content: str
    role: str = "user"  # user | assistant | system
    source: str = ""  # 来源标识
    tokens: int = 0
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)


class MemoryPartition:
    """记忆分区"""

    def __init__(self, name: str, budget: int):
        self.name = name
        self.budget = budget
        self.entries: deque[MemoryEntry] = deque()
        self._current_tokens = 0

    @property
    def used_tokens(self) -> int:
        return self._current_tokens

    @property
    def remaining_tokens(self) -> int:
        return max(0, self.budget - self._current_tokens)

    def add(self, entry: MemoryEntry):
        """添加记忆条目（超出预算时淘汰最旧条目）"""
        # 估算 token 数
        if entry.tokens == 0:
            entry.tokens = len(entry.content) // 2  # 粗略估算

        # 淘汰旧条目直到有空间
        while self._current_tokens + entry.tokens > self.budget and self.entries:
            removed = self.entries.popleft()
            self._current_tokens -= removed.tokens

        self.entries.append(entry)
        self._current_tokens += entry.tokens

    def get_context(self, max_tokens: int | None = None) -> list[MemoryEntry]:
        """获取上下文（按时间顺序）"""
        if max_tokens is None:
            return list(self.entries)

        result = []
        total = 0
        for entry in reversed(list(self.entries)):
            if total + entry.tokens > max_tokens:
                break
            result.insert(0, entry)
            total += entry.tokens
        return result

    def clear(self):
        """清空分区"""
        self.entries.clear()
        self._current_tokens = 0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "budget": self.budget,
            "used_tokens": self.used_tokens,
            "entry_count": len(self.entries),
        }


class MemorySystem:
    """分区记忆系统"""

    def __init__(self, budgets: dict[str, int]):
        self.partitions: dict[str, MemoryPartition] = {}
        for name, budget in budgets.items():
            self.partitions[name] = MemoryPartition(name=name, budget=budget)

        logger.info(f"MemorySystem 已初始化，分区 budgets: {budgets}")

    def add_memory(
        self,
        partition: str,
        content: str,
        role: str = "user",
        source: str = "",
        metadata: dict | None = None,
    ):
        """向指定分区添加记忆"""
        if partition not in self.partitions:
            logger.warning(f"分区不存在: {partition}")
            return

        entry = MemoryEntry(
            content=content,
            role=role,
            source=source,
            metadata=metadata or {},
        )
        self.partitions[partition].add(entry)

    def get_context(
        self,
        partitions: list[str] | None = None,
        max_tokens: int | None = None,
    ) -> list[MemoryEntry]:
        """获取合并上下文"""
        if partitions is None:
            partitions = list(self.partitions.keys())

        all_entries = []
        for p_name in partitions:
            if p_name in self.partitions:
                all_entries.extend(self.partitions[p_name].get_context())

        # 按时间排序
        all_entries.sort(key=lambda e: e.timestamp)

        if max_tokens:
            result = []
            total = 0
            for entry in reversed(all_entries):
                if total + entry.tokens > max_tokens:
                    break
                result.insert(0, entry)
                total += entry.tokens
            return result

        return all_entries

    def clear_partition(self, partition: str):
        """清空指定分区"""
        if partition in self.partitions:
            self.partitions[partition].clear()

    def get_stats(self) -> dict:
        """获取记忆系统统计"""
        return {
            name: p.to_dict() for name, p in self.partitions.items()
        }


# 全局单例
_memory: MemorySystem | None = None


def get_memory_system() -> MemorySystem | None:
    return _memory


def create_memory_system(budgets: dict[str, int]) -> MemorySystem:
    global _memory
    _memory = MemorySystem(budgets=budgets)
    return _memory
