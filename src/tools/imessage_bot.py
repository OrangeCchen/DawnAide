"""iMessage 双向对话机器人

监听 macOS Messages.app 数据库中的新消息，
自动提交给 AgentTeams 执行任务，结果通过 iMessage 回复。

两种模式：
- 待命模式（standby）：只监听"开启"命令，收到后激活
- 活跃模式（active）：处理所有消息，收到"关闭"后回到待命

服务启动时自动进入待命模式，无需打开网页。
"""

from __future__ import annotations

import asyncio
import re
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger

# Messages.app 数据库路径
CHAT_DB_PATH = Path.home() / "Library" / "Messages" / "chat.db"

# 机器人回复的前缀标识（用于过滤自己发的消息）
BOT_PREFIXES = ("📋", "👩‍💻", "✅", "❌", "⏱")

# 激活命令
ACTIVATE_COMMANDS = ("开启", "启动", "start", "开机")
# 关闭命令
DEACTIVATE_COMMANDS = ("关闭", "停止", "stop", "quit", "关机")

# Apple 时间戳起点：2001-01-01 00:00:00 UTC
APPLE_EPOCH = datetime(2001, 1, 1)


class ImessageBot:
    """iMessage 双向对话机器人（支持待命/活跃两种模式）"""

    def __init__(self):
        self._listening = False      # 是否在监听（待命 or 活跃）
        self._active = False         # 是否活跃（处理任务）
        self._task: asyncio.Task | None = None
        self._last_rowid: int = 0
        self._phone: str = ""
        self._processing: set[int] = set()
        self._recent_texts: dict[str, float] = {}
        self._poll_interval: float = 3.0
        self._standby_poll_interval: float = 5.0  # 待命时轮询更慢

    @property
    def is_running(self) -> bool:
        """是否在活跃处理任务"""
        return self._active

    @property
    def is_listening(self) -> bool:
        """是否在监听（含待命）"""
        return self._listening

    @property
    def phone(self) -> str:
        return self._phone

    @property
    def status(self) -> str:
        if self._active:
            return "active"
        elif self._listening:
            return "standby"
        return "off"

    def _read_phone_from_env(self) -> str:
        """从 .env 文件读取手机号"""
        try:
            from src.config import ROOT_DIR
            env_path = ROOT_DIR / ".env"
            if env_path.exists():
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    if line.startswith("IMESSAGE_PUSH_TO="):
                        return line.split("=", 1)[1].strip()
        except Exception:
            pass
        return ""

    async def start_listening(self, phone: str = "") -> bool:
        """启动监听（进入待命模式）

        服务启动时自动调用，只监听开启/关闭命令。
        """
        if self._listening:
            return True

        if not phone:
            phone = self._read_phone_from_env()
        if not phone:
            logger.warning("[iMessage Bot] 未配置手机号，跳过启动")
            return False

        if not CHAT_DB_PATH.exists():
            logger.warning(f"[iMessage Bot] 数据库不存在: {CHAT_DB_PATH}")
            return False

        # 测试数据库权限
        try:
            conn = sqlite3.connect(f"file:{CHAT_DB_PATH}?mode=ro", uri=True)
            conn.execute("SELECT 1 FROM message LIMIT 1")
            conn.close()
        except Exception as e:
            logger.warning(f"[iMessage Bot] 无法读取数据库（需要全磁盘访问权限）: {e}")
            return False

        self._phone = phone
        self._listening = True
        self._last_rowid = self._get_latest_rowid()

        logger.info(
            f"[iMessage Bot] 待命模式启动，监听 {phone}，"
            f"发送「开启」激活，ROWID={self._last_rowid}"
        )

        self._task = asyncio.create_task(self._poll_loop())
        return True

    async def activate(self):
        """激活为活跃模式（开始处理任务）"""
        if self._active:
            return
        self._active = True
        logger.info("[iMessage Bot] 已激活，开始处理任务")
        from src.tools.imessage import send_imessage
        await send_imessage(
            self._phone,
            "👩‍💻 AgentTeams 已就绪\n"
            "直接发消息，自动处理。\n"
            "发送「关闭」可休眠。"
        )

    async def deactivate(self):
        """回到待命模式"""
        if not self._active:
            return
        self._active = False
        logger.info("[iMessage Bot] 已休眠，回到待命模式")
        from src.tools.imessage import send_imessage
        await send_imessage(
            self._phone,
            "👩‍💻 Bot 已休眠。发送「开启」重新激活。"
        )

    async def stop(self):
        """完全停止监听"""
        self._active = False
        self._listening = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("[iMessage Bot] 已完全停止")

    async def _poll_loop(self):
        """主轮询循环（待命+活跃共用）"""
        while self._listening:
            try:
                new_messages = self._check_new_messages()
                now = time.time()
                # 清理 30 秒前的去重记录
                self._recent_texts = {
                    k: v for k, v in self._recent_texts.items() if now - v < 30
                }

                for rowid, text, msg_time in new_messages:
                    if rowid in self._processing:
                        self._last_rowid = max(self._last_rowid, rowid)
                        continue
                    stripped = text.strip()
                    # 过滤机器人自己的回复
                    if any(stripped.startswith(p) for p in BOT_PREFIXES):
                        self._last_rowid = max(self._last_rowid, rowid)
                        continue
                    # 内容去重
                    if stripped in self._recent_texts:
                        self._last_rowid = max(self._last_rowid, rowid)
                        continue
                    self._recent_texts[stripped] = now
                    self._last_rowid = max(self._last_rowid, rowid)

                    # 检查命令
                    if stripped in ACTIVATE_COMMANDS:
                        await self.activate()
                        continue
                    if stripped in DEACTIVATE_COMMANDS:
                        await self.deactivate()
                        continue

                    # 活跃模式下才处理任务
                    if self._active:
                        self._processing.add(rowid)
                        asyncio.create_task(self._process_message(rowid, stripped))
                    # 待命模式下忽略非命令消息

            except Exception as e:
                logger.error(f"[iMessage Bot] 轮询异常: {e}")

            interval = self._poll_interval if self._active else self._standby_poll_interval
            await asyncio.sleep(interval)

    def _get_latest_rowid(self) -> int:
        """获取当前数据库中最新消息的 ROWID"""
        try:
            conn = sqlite3.connect(f"file:{CHAT_DB_PATH}?mode=ro", uri=True)
            cursor = conn.execute("SELECT MAX(ROWID) FROM message")
            row = cursor.fetchone()
            conn.close()
            return row[0] or 0
        except Exception as e:
            logger.error(f"[iMessage Bot] 读取数据库失败: {e}")
            return 0

    def _check_new_messages(self) -> list[tuple[int, str, datetime]]:
        """检查自己对话中的新消息"""
        results = []
        try:
            conn = sqlite3.connect(f"file:{CHAT_DB_PATH}?mode=ro", uri=True)
            query = """
                SELECT m.ROWID, m.text, m.date
                FROM message m
                JOIN chat_message_join cmj ON m.ROWID = cmj.message_id
                JOIN chat c ON cmj.chat_id = c.ROWID
                WHERE m.ROWID > ?
                  AND m.text IS NOT NULL
                  AND m.text != ''
                  AND c.chat_identifier = ?
                ORDER BY m.ROWID ASC
                LIMIT 10
            """
            cursor = conn.execute(query, (self._last_rowid, self._phone))
            for row in cursor.fetchall():
                rowid, text, date_val = row
                if date_val and date_val > 1e15:
                    msg_time = APPLE_EPOCH + timedelta(seconds=date_val / 1e9)
                elif date_val:
                    msg_time = APPLE_EPOCH + timedelta(seconds=date_val)
                else:
                    msg_time = datetime.now()
                results.append((rowid, text, msg_time))
            conn.close()
        except Exception as e:
            logger.error(f"[iMessage Bot] 查询新消息失败: {e}")
        return results

    async def _process_message(self, rowid: int, text: str):
        """处理一条用户消息：提交任务 → 等待结果 → 回复"""
        logger.info(f"[iMessage Bot] 收到消息: {text[:50]}...")

        try:
            from src.tools.imessage import send_imessage
            from src.core.engine import get_engine
            from src.core.task import Task, TaskStatus
            from src.core.team import TeamMember, get_team_manager

            engine = get_engine()
            if not engine:
                await send_imessage(self._phone, "❌ 引擎未就绪，请稍后再试")
                return

            # 创建临时团队
            tm = get_team_manager()
            team = tm.create_team(
                name=f"iMessage: {text[:20]}",
                description="iMessage Bot 自动创建",
            )
            lead = engine.get_agent("team-lead")
            if lead:
                tm.add_member(team.id, TeamMember(
                    agent_name=lead.name, role=lead.role, role_label=lead.role_label,
                ))
            await tm.save_team_to_db(team)

            task = Task(
                title=text[:50],
                description=text,
                assigned_to="team-lead",
                assigned_by="imessage-bot",
                team_id=team.id,
            )

            result = await engine.submit_task(task)

            if result and result.status == TaskStatus.COMPLETED:
                plain = self._strip_markdown(result.content)
                if len(plain) > 800:
                    plain = plain[:797] + "..."
                reply = f"📋 {text[:30]}\n\n{plain}"
            else:
                reply = f"❌ 任务处理失败\n\n原始消息: {text[:100]}"

            await send_imessage(self._phone, reply)
            logger.info(f"[iMessage Bot] 回复已发送，长度={len(reply)}")

        except Exception as e:
            logger.error(f"[iMessage Bot] 处理消息异常: {e}")
            try:
                from src.tools.imessage import send_imessage
                await send_imessage(self._phone, f"❌ 处理失败: {str(e)[:100]}")
            except Exception:
                pass
        finally:
            self._processing.discard(rowid)

    @staticmethod
    def _strip_markdown(text: str) -> str:
        """去除 Markdown 格式标记"""
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        text = re.sub(r'\*(.+?)\*', r'\1', text)
        text = re.sub(r'#{1,6}\s*', '', text)
        text = re.sub(r'`(.+?)`', r'\1', text)
        text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)
        text = re.sub(r'---+', '', text)
        return text.strip()


# 全局单例
_bot: ImessageBot | None = None


def get_imessage_bot() -> ImessageBot:
    """获取 iMessage Bot 全局单例"""
    global _bot
    if _bot is None:
        _bot = ImessageBot()
    return _bot
