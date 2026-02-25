"""本地客户端能力适配器

负责与 AgentTeams Client Runtime 通信，提供：
- 健康检查（探测 Runtime 是否可用）
- 本地文件读取代理
- 本地知识库检索代理
- 统一降级策略（Runtime 不可用时返回可解释提示）

通信方式：localhost HTTP（后续可扩展 gRPC）
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import httpx
from loguru import logger


@dataclass
class ClientStatus:
    """客户端运行时状态"""
    online: bool = False
    version: str = ""
    last_check: float = 0.0
    capabilities: list[str] = field(default_factory=list)


class LocalClientAdapter:
    """本地客户端能力适配器（单例）

    所有对 Client Runtime 的调用统一经此适配器，
    提供超时、熔断、降级等保护机制。
    """

    DEFAULT_BASE_URL = "http://127.0.0.1:19800"
    HEALTH_CHECK_INTERVAL = 30.0  # 秒
    REQUEST_TIMEOUT = 10.0  # 秒

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self._status = ClientStatus()
        self._client: httpx.AsyncClient | None = None
        self._consecutive_failures = 0
        self._circuit_open = False
        self._circuit_open_until = 0.0
        self.CIRCUIT_THRESHOLD = 3
        self.CIRCUIT_COOLDOWN = 60.0  # 熔断冷却秒数

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.REQUEST_TIMEOUT,
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    # ------ 熔断器 ------

    def _check_circuit(self) -> bool:
        """检查熔断器是否开启，返回 True 表示可以请求"""
        if not self._circuit_open:
            return True
        import time
        if time.time() >= self._circuit_open_until:
            self._circuit_open = False
            self._consecutive_failures = 0
            logger.info("[客户端适配器] 熔断器半开，尝试恢复")
            return True
        return False

    def _on_success(self):
        self._consecutive_failures = 0
        self._circuit_open = False

    def _on_failure(self):
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.CIRCUIT_THRESHOLD:
            import time
            self._circuit_open = True
            self._circuit_open_until = time.time() + self.CIRCUIT_COOLDOWN
            logger.warning(
                f"[客户端适配器] 连续 {self._consecutive_failures} 次失败，"
                f"熔断 {self.CIRCUIT_COOLDOWN}s"
            )

    # ------ 核心请求方法 ------

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> dict[str, Any] | None:
        """统一请求方法，内置熔断与降级"""
        if not self._check_circuit():
            logger.debug("[客户端适配器] 熔断中，跳过请求")
            return None

        try:
            client = await self._get_client()
            resp = await client.request(method, path, **kwargs)
            resp.raise_for_status()
            self._on_success()
            return resp.json()
        except httpx.ConnectError:
            self._on_failure()
            logger.debug(f"[客户端适配器] 连接失败: {self.base_url}{path}")
            return None
        except httpx.TimeoutException:
            self._on_failure()
            logger.warning(f"[客户端适配器] 请求超时: {path}")
            return None
        except Exception as e:
            self._on_failure()
            logger.warning(f"[客户端适配器] 请求异常: {path} -> {e}")
            return None

    # ------ 公开 API ------

    async def check_health(self) -> ClientStatus:
        """检查客户端运行时健康状态"""
        import time
        now = time.time()
        if now - self._status.last_check < self.HEALTH_CHECK_INTERVAL and self._status.online:
            return self._status

        data = await self._request("GET", "/health")
        if data and data.get("status") == "ok":
            self._status = ClientStatus(
                online=True,
                version=data.get("version", "unknown"),
                last_check=now,
                capabilities=data.get("capabilities", []),
            )
            logger.info(
                f"[客户端适配器] Runtime 在线 v{self._status.version}, "
                f"能力: {self._status.capabilities}"
            )
        else:
            self._status = ClientStatus(online=False, last_check=now)

        return self._status

    @property
    def is_online(self) -> bool:
        return self._status.online

    async def read_file(
        self,
        path: str,
        start: int | None = None,
        end: int | None = None,
        mode: str = "text",
    ) -> dict[str, Any] | None:
        """通过 Runtime 读取本地文件"""
        payload: dict[str, Any] = {"path": path, "mode": mode}
        if start is not None:
            payload["start"] = start
        if end is not None:
            payload["end"] = end

        return await self._request("POST", "/file/read", json=payload)

    async def open_path(self, path: str) -> dict[str, Any] | None:
        """通过 Runtime 打开本地目录/文件"""
        return await self._request("POST", "/file/open", json={"path": path})

    async def search_kb(
        self,
        query: str,
        collection: str = "default",
        top_k: int = 5,
        filters: dict | None = None,
    ) -> dict[str, Any] | None:
        """通过 Runtime 检索本地知识库"""
        payload = {
            "query": query,
            "collection": collection,
            "top_k": top_k,
        }
        if filters:
            payload["filters"] = filters

        return await self._request("POST", "/kb/search", json=payload)

    async def index_kb(
        self,
        paths: list[str],
        collection: str = "default",
        reindex: bool = False,
        file_types: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """通过 Runtime 提交索引任务"""
        payload = {
            "paths": paths,
            "collection": collection,
            "reindex": reindex,
        }
        if file_types:
            payload["file_types"] = file_types

        return await self._request("POST", "/kb/index", json=payload)

    async def list_permissions(self) -> dict[str, Any] | None:
        """查询已授权目录"""
        return await self._request("GET", "/permissions/list")

    async def grant_permission(self, path: str) -> dict[str, Any] | None:
        """授权新目录"""
        return await self._request("POST", "/permissions/grant", json={"path": path})


# ------ 全局单例 ------

_adapter: LocalClientAdapter | None = None


def get_local_client_adapter() -> LocalClientAdapter:
    global _adapter
    if _adapter is None:
        _adapter = LocalClientAdapter()
    return _adapter
