"""Team 管理模块"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from loguru import logger


@dataclass
class TeamMember:
    """团队成员"""

    agent_name: str
    role: str  # "team-lead" | "reviewer" | "architect" | "ux-reviewer" | ...
    role_label: str = ""  # 显示标签，如 "Lead", "Explorer", "Plan"
    status: str = "idle"  # idle | working | done

    def to_dict(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "role": self.role,
            "role_label": self.role_label,
            "status": self.status,
        }


@dataclass
class Team:
    """团队"""

    id: str = field(default_factory=lambda: uuid4().hex[:8])
    name: str = ""
    description: str = ""
    members: list[TeamMember] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def member_count(self) -> int:
        return len(self.members)

    def get_member(self, agent_name: str) -> TeamMember | None:
        for m in self.members:
            if m.agent_name == agent_name:
                return m
        return None

    def get_lead(self) -> TeamMember | None:
        for m in self.members:
            if m.role == "team-lead":
                return m
        return None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "members": [m.to_dict() for m in self.members],
            "member_count": self.member_count,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }


class TeamManager:
    """团队管理器（带持久化）"""

    def __init__(self):
        self._teams: dict[str, Team] = {}

    def create_team(self, name: str, description: str = "") -> Team:
        """创建团队"""
        team = Team(name=name, description=description)
        self._teams[team.id] = team
        logger.info(f"团队已创建: {name} (id={team.id})")
        return team

    def add_member(self, team_id: str, member: TeamMember) -> bool:
        """添加成员"""
        team = self._teams.get(team_id)
        if not team:
            logger.warning(f"团队不存在: {team_id}")
            return False
        team.members.append(member)
        logger.info(f"成员 {member.agent_name}({member.role}) 加入团队 {team.name}")
        return True

    def get_team(self, team_id: str) -> Team | None:
        return self._teams.get(team_id)

    def list_teams(self) -> list[Team]:
        return list(self._teams.values())

    def rename_team(self, team_id: str, new_name: str) -> bool:
        """重命名团队"""
        team = self._teams.get(team_id)
        if team:
            team.name = new_name
            return True
        return False

    def delete_team(self, team_id: str) -> bool:
        if team_id in self._teams:
            del self._teams[team_id]
            return True
        return False

    async def save_team_to_db(self, team: Team):
        """持久化团队到数据库"""
        try:
            from src.storage.database import get_database
            db = await get_database()
            await db.save_team(team.to_dict())
        except Exception as e:
            logger.warning(f"团队持久化失败: {e}")

    async def delete_team_from_db(self, team_id: str):
        """从数据库删除团队"""
        try:
            from src.storage.database import get_database
            db = await get_database()
            await db.delete_team(team_id)
        except Exception as e:
            logger.warning(f"团队删除持久化失败: {e}")

    async def load_teams_from_db(self):
        """从数据库恢复团队"""
        try:
            from src.storage.database import get_database
            db = await get_database()
            team_dicts = await db.load_teams()

            for td in team_dicts:
                members = [
                    TeamMember(
                        agent_name=m["agent_name"],
                        role=m["role"],
                        role_label=m.get("role_label", ""),
                    )
                    for m in td.get("members", [])
                ]
                team = Team(
                    id=td["id"],
                    name=td["name"],
                    description=td.get("description", ""),
                    members=members,
                    created_at=datetime.fromisoformat(td["created_at"]),
                    metadata=td.get("metadata", {}),
                )
                self._teams[team.id] = team

            if team_dicts:
                logger.info(f"从数据库恢复了 {len(team_dicts)} 个团队")
        except Exception as e:
            logger.warning(f"从数据库恢复团队失败: {e}")


# 全局单例
_manager: TeamManager | None = None


def get_team_manager() -> TeamManager:
    global _manager
    if _manager is None:
        _manager = TeamManager()
    return _manager
