"""WebSocket 实时消息推送"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from src.core.message_bus import Message, get_message_bus
from src.display.hooks import DisplayHooks

ws_router = APIRouter()


class ConnectionManager:
    """WebSocket 连接管理"""

    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self._bus_registered = False

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket 连接已建立，当前连接数: {len(self.active_connections)}")

        # 只注册一次全局消息总线回调
        if not self._bus_registered:
            bus = get_message_bus()
            bus.subscribe_global(self._on_bus_message)
            self._bus_registered = True
            logger.debug("WebSocket 全局消息回调已注册")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket 连接已断开，当前连接数: {len(self.active_connections)}")

    async def broadcast(self, data: dict):
        """广播消息给所有连接"""
        message_text = json.dumps(data, ensure_ascii=False)
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message_text)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)

    async def _on_bus_message(self, message: Message):
        """消息总线回调 -> 推送到所有 WebSocket 客户端"""
        msg_dict = message.to_dict()
        # 应用显示 Hook
        msg_dict = DisplayHooks.apply(msg_dict)
        await self.broadcast(msg_dict)


manager = ConnectionManager()


@ws_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 端点（带服务端 keepalive 心跳）"""
    await manager.connect(websocket)

    async def _server_heartbeat():
        """服务端定时发送心跳，防止长时间任务期间连接被中间件/代理断开"""
        try:
            while True:
                await asyncio.sleep(25)
                try:
                    await websocket.send_text(json.dumps({"action": "heartbeat"}))
                except Exception:
                    break
        except asyncio.CancelledError:
            pass

    heartbeat_task = asyncio.create_task(_server_heartbeat())

    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
                action = payload.get("action", "")

                if action == "ping":
                    await websocket.send_text(json.dumps({"action": "pong"}))

            except json.JSONDecodeError:
                await websocket.send_text(
                    json.dumps({"error": "Invalid JSON"}, ensure_ascii=False)
                )

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    finally:
        heartbeat_task.cancel()
