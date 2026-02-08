# -*- coding: utf-8 -*-
# Copyright 2025 AgentUnion Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
ConnectionManager - WebSocket 连接管理器

提供 MessageClient 的生命周期管理，支持：
1. 连接状态查询
2. 主动销毁和重建连接
3. 断开/恢复回调
4. 连接健康监控

每个 AgentID 对应一个 ConnectionManager，管理该 Agent 的所有 MessageClient。
"""

import threading
import time
from typing import Dict, Optional, Callable, List
from dataclasses import dataclass, field
from enum import Enum

from agentcp.base.log import log_info, log_error, log_warning, log_debug
from agentcp.msg.message_client import MessageClient, MessageClientConfig, ConnectionState


class ConnectionEvent(Enum):
    """连接事件类型"""
    CONNECTED = "connected"           # 连接建立
    DISCONNECTED = "disconnected"     # 连接断开
    RECONNECTING = "reconnecting"     # 正在重连
    RECONNECTED = "reconnected"       # 重连成功
    DESTROYED = "destroyed"           # 连接销毁
    CREATED = "created"               # 连接创建


@dataclass
class ConnectionInfo:
    """连接信息"""
    server_url: str
    message_client: Optional[MessageClient] = None
    created_at: float = 0.0
    last_connected_at: float = 0.0
    last_disconnected_at: float = 0.0
    disconnect_count: int = 0
    reconnect_count: int = 0
    is_destroyed: bool = False


class ConnectionManager:
    """WebSocket 连接管理器

    管理一个 AgentID 下的所有 MessageClient 连接。

    主要功能：
    1. 连接生命周期管理（创建、销毁、重建）
    2. 连接状态查询
    3. 事件回调（断开、恢复）
    4. 健康监控

    使用示例：
        ```python
        # 创建连接管理器
        conn_mgr = ConnectionManager(agent_id, aid_path, seed_password)

        # 设置回调
        conn_mgr.set_event_callback(on_connection_event)

        # 获取或创建连接
        mc = conn_mgr.get_or_create_connection(server_url)

        # 查询连接状态
        if conn_mgr.is_healthy(server_url):
            mc.send_msg(...)

        # 销毁并重建连接
        conn_mgr.rebuild_connection(server_url)

        # 关闭所有连接
        conn_mgr.destroy_all()
        ```
    """

    def __init__(
        self,
        agent_id: str,
        aid_path: str,
        seed_password: str,
        config: Optional[MessageClientConfig] = None
    ):
        """初始化连接管理器

        Args:
            agent_id: Agent ID
            aid_path: AID 证书路径
            seed_password: 种子密码
            config: MessageClient 配置（可选，不传则使用默认配置）
        """
        self.agent_id = agent_id
        self.aid_path = aid_path
        self.seed_password = seed_password
        self.config = config or MessageClientConfig()

        # 连接映射：server_url -> ConnectionInfo
        self._connections: Dict[str, ConnectionInfo] = {}
        self._lock = threading.RLock()

        # 事件回调
        self._event_callback: Optional[Callable[[str, ConnectionEvent, dict], None]] = None

        # 是否已关闭
        self._shutdown = False

        log_info(f"[ConnectionManager] 初始化: agent_id={agent_id}")

    def set_event_callback(self, callback: Callable[[str, ConnectionEvent, dict], None]) -> None:
        """设置连接事件回调

        回调函数签名: callback(server_url: str, event: ConnectionEvent, info: dict)

        Args:
            callback: 事件回调函数
        """
        self._event_callback = callback
        log_info(f"[ConnectionManager] 已设置事件回调")

    def _fire_event(self, server_url: str, event: ConnectionEvent, extra_info: dict = None) -> None:
        """触发事件回调"""
        if self._event_callback:
            try:
                info = extra_info or {}
                info["agent_id"] = self.agent_id
                info["server_url"] = server_url
                info["timestamp"] = time.time()
                self._event_callback(server_url, event, info)
            except Exception as e:
                log_error(f"[ConnectionManager] 事件回调异常: {e}")

    def get_or_create_connection(
        self,
        server_url: str,
        cache_auth_client=None,
        message_handler=None
    ) -> Optional[MessageClient]:
        """获取或创建连接

        如果连接已存在且未销毁，返回现有连接。
        如果连接不存在或已销毁，创建新连接。

        Args:
            server_url: 消息服务器 URL
            cache_auth_client: 缓存的认证客户端（可选）
            message_handler: 消息处理器（可选）

        Returns:
            MessageClient 实例，失败返回 None
        """
        if self._shutdown:
            log_warning(f"[ConnectionManager] 已关闭，无法创建连接")
            return None

        server_url = server_url.rstrip("/")

        with self._lock:
            conn_info = self._connections.get(server_url)

            # 已存在且未销毁，复用
            if conn_info and not conn_info.is_destroyed and conn_info.message_client:
                log_debug(f"[ConnectionManager] 复用现有连接: {server_url}")
                return conn_info.message_client

            # 需要创建新连接
            log_info(f"[ConnectionManager] 创建新连接: {server_url}")

            try:
                mc = MessageClient(
                    agent_id=self.agent_id,
                    server_url=server_url,
                    aid_path=self.aid_path,
                    seed_password=self.seed_password,
                    cache_auth_client=cache_auth_client,
                    config=self.config
                )
                mc.initialize()

                if message_handler:
                    mc.set_message_handler(message_handler)

                # 设置回调
                mc.set_disconnect_callback(self._on_disconnect)
                mc.set_reconnect_callback(self._on_reconnect)

                # 记录连接信息
                conn_info = ConnectionInfo(
                    server_url=server_url,
                    message_client=mc,
                    created_at=time.time(),
                    is_destroyed=False
                )
                self._connections[server_url] = conn_info

                self._fire_event(server_url, ConnectionEvent.CREATED)
                return mc

            except Exception as e:
                log_error(f"[ConnectionManager] 创建连接失败: {server_url}, error={e}")
                return None

    def get_connection(self, server_url: str) -> Optional[MessageClient]:
        """获取现有连接（不创建）

        Args:
            server_url: 消息服务器 URL

        Returns:
            MessageClient 实例，不存在返回 None
        """
        server_url = server_url.rstrip("/")
        with self._lock:
            conn_info = self._connections.get(server_url)
            if conn_info and not conn_info.is_destroyed:
                return conn_info.message_client
            return None

    def is_healthy(self, server_url: str) -> bool:
        """检查连接是否健康

        Args:
            server_url: 消息服务器 URL

        Returns:
            True: 连接健康可用
            False: 连接不可用
        """
        mc = self.get_connection(server_url)
        if mc:
            return mc.is_healthy()
        return False

    def get_connection_info(self, server_url: str) -> Optional[dict]:
        """获取连接详细信息

        Args:
            server_url: 消息服务器 URL

        Returns:
            连接信息字典，不存在返回 None
        """
        server_url = server_url.rstrip("/")
        with self._lock:
            conn_info = self._connections.get(server_url)
            if not conn_info:
                return None

            mc = conn_info.message_client
            mc_info = mc.get_connection_info() if mc else {}

            return {
                "server_url": server_url,
                "created_at": conn_info.created_at,
                "last_connected_at": conn_info.last_connected_at,
                "last_disconnected_at": conn_info.last_disconnected_at,
                "disconnect_count": conn_info.disconnect_count,
                "reconnect_count": conn_info.reconnect_count,
                "is_destroyed": conn_info.is_destroyed,
                **mc_info
            }

    def get_all_connections_info(self) -> List[dict]:
        """获取所有连接的信息

        Returns:
            连接信息列表
        """
        with self._lock:
            result = []
            for server_url in self._connections:
                info = self.get_connection_info(server_url)
                if info:
                    result.append(info)
            return result

    def get_health_summary(self) -> dict:
        """获取健康状态摘要

        Returns:
            健康状态摘要字典
        """
        with self._lock:
            total = len(self._connections)
            healthy = sum(1 for url in self._connections if self.is_healthy(url))
            destroyed = sum(1 for info in self._connections.values() if info.is_destroyed)

            return {
                "agent_id": self.agent_id,
                "total_connections": total,
                "healthy_connections": healthy,
                "unhealthy_connections": total - healthy - destroyed,
                "destroyed_connections": destroyed,
                "is_all_healthy": healthy == total and total > 0
            }

    def destroy_connection(self, server_url: str, wait: bool = True) -> bool:
        """销毁指定连接

        Args:
            server_url: 消息服务器 URL
            wait: 是否等待连接完全关闭

        Returns:
            True: 销毁成功
            False: 连接不存在
        """
        server_url = server_url.rstrip("/")

        with self._lock:
            conn_info = self._connections.get(server_url)
            if not conn_info:
                log_warning(f"[ConnectionManager] 连接不存在: {server_url}")
                return False

            if conn_info.is_destroyed:
                log_debug(f"[ConnectionManager] 连接已销毁: {server_url}")
                return True

            log_info(f"[ConnectionManager] 销毁连接: {server_url}")

            mc = conn_info.message_client
            if mc:
                try:
                    mc.stop_websocket_client()
                except Exception as e:
                    log_error(f"[ConnectionManager] 停止 WebSocket 异常: {e}")

            conn_info.is_destroyed = True
            conn_info.message_client = None

            self._fire_event(server_url, ConnectionEvent.DESTROYED)
            return True

    def rebuild_connection(
        self,
        server_url: str,
        cache_auth_client=None,
        message_handler=None
    ) -> Optional[MessageClient]:
        """销毁并重建连接

        Args:
            server_url: 消息服务器 URL
            cache_auth_client: 缓存的认证客户端（可选）
            message_handler: 消息处理器（可选）

        Returns:
            新的 MessageClient 实例，失败返回 None
        """
        log_info(f"[ConnectionManager] 重建连接: {server_url}")

        # 先销毁
        self.destroy_connection(server_url, wait=True)

        # 短暂等待确保资源释放
        time.sleep(0.3)

        # 再创建
        return self.get_or_create_connection(server_url, cache_auth_client, message_handler)

    def destroy_all(self, wait: bool = True) -> None:
        """销毁所有连接

        Args:
            wait: 是否等待所有连接完全关闭
        """
        log_info(f"[ConnectionManager] 销毁所有连接...")
        self._shutdown = True

        with self._lock:
            for server_url in list(self._connections.keys()):
                self.destroy_connection(server_url, wait=wait)

        log_info(f"[ConnectionManager] 所有连接已销毁")

    def force_reconnect(self, server_url: str) -> bool:
        """强制触发重连

        不销毁连接，而是触发 MessageClient 的重连逻辑。

        Args:
            server_url: 消息服务器 URL

        Returns:
            True: 触发成功
            False: 连接不存在
        """
        mc = self.get_connection(server_url)
        if not mc:
            return False

        log_info(f"[ConnectionManager] 强制重连: {server_url}")

        # 停止当前连接
        mc.stop_websocket_client()

        # 短暂等待
        time.sleep(0.2)

        # 重新启动
        return mc.start_websocket_client()

    def _on_disconnect(self, agent_id: str, server_url: str, code: int, reason: str) -> None:
        """连接断开回调"""
        server_url = server_url.rstrip("/")
        log_warning(f"[ConnectionManager] 连接断开: {server_url}, code={code}, reason={reason}")

        with self._lock:
            conn_info = self._connections.get(server_url)
            if conn_info:
                conn_info.last_disconnected_at = time.time()
                conn_info.disconnect_count += 1

        self._fire_event(server_url, ConnectionEvent.DISCONNECTED, {
            "code": code,
            "reason": reason
        })

    def _on_reconnect(self, agent_id: str, server_url: str) -> None:
        """连接恢复回调"""
        server_url = server_url.rstrip("/")
        log_info(f"[ConnectionManager] 连接恢复: {server_url}")

        with self._lock:
            conn_info = self._connections.get(server_url)
            if conn_info:
                conn_info.last_connected_at = time.time()
                conn_info.reconnect_count += 1

        self._fire_event(server_url, ConnectionEvent.RECONNECTED)

    def __del__(self):
        """析构时清理"""
        try:
            if not self._shutdown:
                self.destroy_all(wait=False)
        except Exception:
            pass
