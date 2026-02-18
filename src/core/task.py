"""任务定义与状态管理"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4


class TaskStatus(str, Enum):
    """任务状态"""

    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskPriority(str, Enum):
    """任务优先级"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class TaskResult:
    """任务执行结果"""

    task_id: str
    agent_name: str
    status: TaskStatus = TaskStatus.COMPLETED
    content: str = ""
    report_path: str = ""  # 报告文件路径
    findings: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    completed_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "agent_name": self.agent_name,
            "status": self.status.value,
            "content": self.content,
            "report_path": self.report_path,
            "findings": self.findings,
            "metadata": self.metadata,
            "completed_at": self.completed_at.isoformat(),
        }


@dataclass
class Task:
    """任务定义"""

    id: str = field(default_factory=lambda: uuid4().hex[:8])
    title: str = ""
    description: str = ""
    assigned_to: str = ""  # Agent name
    assigned_by: str = ""  # Agent name
    team_id: str = ""
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.MEDIUM
    parent_task_id: str | None = None  # 父任务ID（用于任务拆解）
    sub_tasks: list[Task] = field(default_factory=list)
    result: TaskResult | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "assigned_to": self.assigned_to,
            "assigned_by": self.assigned_by,
            "team_id": self.team_id,
            "status": self.status.value,
            "priority": self.priority.value,
            "parent_task_id": self.parent_task_id,
            "sub_tasks": [t.to_dict() for t in self.sub_tasks],
            "result": self.result.to_dict() if self.result else None,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
