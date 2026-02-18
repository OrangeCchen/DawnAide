"""SQLite 持久化层

存储 teams 和 messages，保证重启后数据不丢失。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import aiosqlite
from loguru import logger

from src.config import DATA_DIR

DB_PATH = DATA_DIR / "agent_teams.db"


class Database:
    """异步 SQLite 数据库"""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def connect(self):
        """连接数据库并创建表"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self.db_path))
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._create_tables()
        logger.info(f"数据库已连接: {self.db_path}")

    async def close(self):
        if self._db:
            await self._db.close()
            self._db = None

    async def _create_tables(self):
        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS teams (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                description TEXT DEFAULT '',
                created_at  TEXT NOT NULL,
                metadata    TEXT DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS team_members (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id     TEXT NOT NULL,
                agent_name  TEXT NOT NULL,
                role        TEXT NOT NULL,
                role_label  TEXT DEFAULT '',
                FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
                UNIQUE(team_id, agent_name)
            );

            CREATE TABLE IF NOT EXISTS messages (
                id          TEXT PRIMARY KEY,
                type        TEXT NOT NULL,
                sender      TEXT DEFAULT '',
                receiver    TEXT DEFAULT '',
                team_id     TEXT NOT NULL,
                content     TEXT DEFAULT '',
                metadata    TEXT DEFAULT '{}',
                timestamp   TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_messages_team_id ON messages(team_id);
            CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp);
        """)
        await self._db.commit()

    # ---- Team 操作 ----

    async def save_team(self, team_dict: dict):
        """保存或更新团队"""
        await self._db.execute(
            """INSERT OR REPLACE INTO teams (id, name, description, created_at, metadata)
               VALUES (?, ?, ?, ?, ?)""",
            (
                team_dict["id"],
                team_dict["name"],
                team_dict.get("description", ""),
                team_dict.get("created_at", datetime.now().isoformat()),
                json.dumps(team_dict.get("metadata", {}), ensure_ascii=False),
            ),
        )
        # 先清除该团队的旧成员记录，再插入当前成员
        await self._db.execute(
            "DELETE FROM team_members WHERE team_id = ?", (team_dict["id"],)
        )
        for member in team_dict.get("members", []):
            await self._db.execute(
                """INSERT INTO team_members (team_id, agent_name, role, role_label)
                   VALUES (?, ?, ?, ?)""",
                (
                    team_dict["id"],
                    member["agent_name"],
                    member["role"],
                    member.get("role_label", ""),
                ),
            )
        await self._db.commit()

    async def load_teams(self) -> list[dict]:
        """加载所有团队"""
        cursor = await self._db.execute(
            "SELECT * FROM teams ORDER BY created_at"
        )
        rows = await cursor.fetchall()
        teams = []
        for row in rows:
            team = {
                "id": row["id"],
                "name": row["name"],
                "description": row["description"],
                "created_at": row["created_at"],
                "metadata": json.loads(row["metadata"] or "{}"),
                "members": [],
            }
            # 加载成员
            mcursor = await self._db.execute(
                "SELECT * FROM team_members WHERE team_id = ?", (row["id"],)
            )
            mrows = await mcursor.fetchall()
            for m in mrows:
                team["members"].append({
                    "agent_name": m["agent_name"],
                    "role": m["role"],
                    "role_label": m["role_label"],
                })
            teams.append(team)
        return teams

    async def delete_team(self, team_id: str):
        """删除团队及其成员和消息"""
        await self._db.execute("DELETE FROM team_members WHERE team_id = ?", (team_id,))
        await self._db.execute("DELETE FROM messages WHERE team_id = ?", (team_id,))
        await self._db.execute("DELETE FROM teams WHERE id = ?", (team_id,))
        await self._db.commit()

    # ---- Message 操作 ----

    async def save_message(self, msg_dict: dict):
        """保存消息"""
        await self._db.execute(
            """INSERT OR REPLACE INTO messages (id, type, sender, receiver, team_id, content, metadata, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                msg_dict["id"],
                msg_dict["type"],
                msg_dict.get("sender", ""),
                msg_dict.get("receiver", ""),
                msg_dict.get("team_id", ""),
                msg_dict.get("content", ""),
                json.dumps(msg_dict.get("metadata", {}), ensure_ascii=False),
                msg_dict.get("timestamp", datetime.now().isoformat()),
            ),
        )
        await self._db.commit()

    async def load_messages(self, team_id: str) -> list[dict]:
        """加载团队消息历史"""
        cursor = await self._db.execute(
            "SELECT * FROM messages WHERE team_id = ? ORDER BY timestamp",
            (team_id,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": row["id"],
                "type": row["type"],
                "sender": row["sender"],
                "receiver": row["receiver"],
                "team_id": row["team_id"],
                "content": row["content"],
                "metadata": json.loads(row["metadata"] or "{}"),
                "timestamp": row["timestamp"],
            }
            for row in rows
        ]


# ---- 全局单例 ----

_db: Database | None = None


async def get_database() -> Database:
    """获取全局数据库实例"""
    global _db
    if _db is None:
        _db = Database()
        await _db.connect()
    return _db


async def close_database():
    """关闭数据库连接"""
    global _db
    if _db:
        await _db.close()
        _db = None
