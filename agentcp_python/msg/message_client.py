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

import asyncio
import json
import queue
import ssl
import threading
import time
from enum import Enum
from typing import Dict, Optional, Union

import websockets
from websockets.exceptions import ConnectionClosed, ConnectionClosedError, ConnectionClosedOK
from websockets.exceptions import InvalidMessage, PayloadTooBig, ProtocolError
from websockets.protocol import State as WsState
from websockets.frames import Frame, Opcode

from agentcp.utils.proxy_bypass import ensure_no_proxy_for_local_env, is_local_url, pop_proxy_env, restore_proxy_env
from agentcp.base.auth_client import AuthClient
from agentcp.base.client import IClient
from agentcp.base.log import log_debug, log_error, log_exception, log_info, log_warning

from ..context import ErrorContext, exceptions

ensure_no_proxy_for_local_env()
from .ws_logger import get_ws_logger  # ✅ 导入 WebSocket 专用日志


class ConnectionState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"


class MessageClientConfig:
    """Configuration class for MessageClient

    配置参数说明：
    - max_queue_size: 消息队列最大容量，断连期间消息暂存于此
    - connection_timeout: WebSocket 连接建立超时时间
    - ping_interval: 心跳间隔，用于检测连接是否存活
    - reconnect_base_interval: 首次重连等待时间
    - reconnect_max_interval: 最大重连等待时间（指数退避上限）
    - reconnect_backoff_factor: 指数退避因子
    - max_message_size: 单条消息最大大小，超过则丢弃
    """

    def __init__(self):
        # ✅ 消息队列：扩大容量，减少断连期间消息丢失
        self.max_queue_size: int = 5000  # 从 30 改为 5000

        # ✅ 连接超时：缩短，更快感知连接失败
        self.connection_timeout: float = 3.0  # 从 5.0 改为 3.0

        self.retry_interval: float = 4.0
        self.max_retry_attempts: int = 0  # 0 表示无限重连
        self.send_retry_attempts: int = 5
        self.send_retry_delay: float = 0.01

        # ✅ 心跳：更频繁，更快检测连接"假死"
        self.ping_interval: int = 3  # 从 5 改为 3

        # ✅ 自动重连配置：缩短间隔，更快恢复服务
        self.auto_reconnect: bool = True
        self.reconnect_base_interval: float = 0.5   # 从 2.0 改为 0.5（首次重连只等 0.5 秒）
        self.reconnect_max_interval: float = 10.0   # 从 60.0 改为 10.0（最多等 10 秒）
        self.reconnect_backoff_factor: float = 1.5  # 保持不变

        # ✅ 消息大小限制
        self.max_message_size: int = 10 * 1024 * 1024  # 从 64MB 改为 10MB


class MessageClient(IClient):
    """WebSocket-based message client using websockets library.

    使用 websockets 库替代 websocket-client，更好地处理协议扩展和错误。
    """

    # 类级别的速率限制标志
    _last_rate_limit_log_time = 0
    _rate_limit_log_interval = 30

    def __init__(
        self,
        agent_id: str,
        server_url: str,
        aid_path: str,
        seed_password: str,
        cache_auth_client: Optional[AuthClient] = None,
        config: Optional[MessageClientConfig] = None,
        agent_id_ref=None,
    ):
        self.agent_id = agent_id
        self.server_url = server_url.rstrip("/")
        self.config = config or MessageClientConfig()
        self._agent_id_ref = agent_id_ref

        # Initialize auth client
        if cache_auth_client is None:
            self.auth_client = AuthClient(agent_id, server_url, aid_path, seed_password)
        else:
            self.auth_client = cache_auth_client

        # Thread synchronization
        self.lock = threading.Lock()
        self.connected_event = threading.Event()

        # WebSocket related
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.ws_thread: Optional[threading.Thread] = None
        self.ws_url: Optional[str] = None

        # Asyncio event loop for websockets
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        # Message handling
        self.queue = queue.Queue(maxsize=self.config.max_queue_size)
        self.message_handler: Optional[object] = None

        # Connection state
        self._connection_state = ConnectionState.DISCONNECTED
        self._is_retrying = False
        self._shutdown_requested = False
        self.stream_queue_map = {}
        self._stream_queue_lock = threading.Lock()  # 保护 stream_queue_map 的访问

        # Stream queue cleanup
        self._cleanup_thread: Optional[threading.Thread] = None
        self._cleanup_running = False

        # 重连状态管理
        self._current_reconnect_interval = self.config.reconnect_base_interval
        self._reconnect_attempt_count = 0

        # 连接健康检查
        self._health_check_thread: Optional[threading.Thread] = None
        self._health_check_running = False
        self._last_pong_time: float = 0

        # 连接唯一标识，用于追踪和防止重复连接
        self._connection_id: int = 0

        # CONNECTING tracking: avoid stuck connection attempts
        self._connecting_since: float = 0.0
        self._connecting_conn_id: int = 0

        # ✅ 断开回调：当 WebSocket 连接断开时通知外部
        self._on_disconnect_callback: Optional[callable] = None

        # ✅ 连接恢复回调：当 WebSocket 连接恢复时通知外部
        self._on_reconnect_callback: Optional[callable] = None

    @property
    def connection_state(self) -> ConnectionState:
        """Get current connection state."""
        with self.lock:
            return self._connection_state

    def _set_connection_state(self, state: ConnectionState) -> None:
        """Set connection state thread-safely."""
        with self.lock:
            self._connection_state = state
            if state == ConnectionState.CONNECTED:
                self.connected_event.set()
            else:
                self.connected_event.clear()
            if state != ConnectionState.CONNECTING:
                self._connecting_since = 0.0
                self._connecting_conn_id = 0

    def _get_use_system_proxy(self) -> bool:
        """获取是否使用系统代理"""
        if self._agent_id_ref and hasattr(self._agent_id_ref, 'get_use_system_proxy'):
            return self._agent_id_ref.get_use_system_proxy()
        return False

    def _is_ws_open(self) -> bool:
        """Check if WebSocket connection is open."""
        try:
            return self.ws is not None and self.ws.state == WsState.OPEN
        except Exception:
            return False

    # ==================== 连接状态查询 API ====================

    def is_healthy(self) -> bool:
        """✅ 检查连接是否健康可用

        健康条件：
        1. WebSocket 连接状态为 OPEN
        2. connected_event 已设置
        3. 连接状态为 CONNECTED
        4. 没有正在重连

        Returns:
            True: 连接健康，可以发送消息
            False: 连接不可用
        """
        return (
            self._is_ws_open() and
            self.connected_event.is_set() and
            self.connection_state == ConnectionState.CONNECTED and
            not self._is_retrying
        )

    def get_connection_info(self) -> dict:
        """✅ 获取连接状态详情

        Returns:
            包含连接状态信息的字典
        """
        return {
            "agent_id": self.agent_id,
            "server_url": self.server_url,
            "state": self.connection_state.value,
            "ws_open": self._is_ws_open(),
            "is_healthy": self.is_healthy(),
            "is_retrying": self._is_retrying,
            "reconnect_attempts": self._reconnect_attempt_count,
            "current_reconnect_interval": self._current_reconnect_interval,
            "connection_id": self._connection_id,
            "last_pong_time": self._last_pong_time,
            "queue_size": self.queue.qsize(),
            "queue_capacity": self.config.max_queue_size,
            "pending_streams": self.get_pending_stream_count(),
        }

    def get_health_summary(self) -> str:
        """✅ 获取连接健康状态摘要（用于日志/调试）

        Returns:
            健康状态摘要字符串
        """
        info = self.get_connection_info()
        status = "🟢 健康" if info["is_healthy"] else "🔴 不健康"
        return (
            f"{status} | state={info['state']} | "
            f"ws_open={info['ws_open']} | "
            f"retrying={info['is_retrying']} | "
            f"queue={info['queue_size']}/{info['queue_capacity']}"
        )

    def set_reconnect_callback(self, callback: callable) -> None:
        """✅ 设置连接恢复回调

        当 WebSocket 连接恢复时，会调用此回调函数。
        回调函数签名: callback(agent_id: str, server_url: str)

        Args:
            callback: 连接恢复时调用的回调函数
        """
        self._on_reconnect_callback = callback
        log_info(f"[MessageClient] 已设置连接恢复回调: {callback}")

    # ==================== 原有方法 ====================

    def initialize(self) -> None:
        """Initialize the client by signing in."""
        self.auth_client.sign_in()

    def sign_in(self) -> bool:
        """Sign in using auth client."""
        try:
            result = self.auth_client.sign_in()
            return result is not None
        except Exception as e:
            log_exception(f"Failed to sign in: {e}")
            return False

    def get_headers(self) -> Dict[str, str]:
        """Get headers for requests."""
        return {"User-Agent": f"AgentCP/{__import__('agentcp').__version__} (AuthClient; {self.agent_id})"}

    def sign_out(self) -> None:
        """Sign out using auth client."""
        self.auth_client.sign_out()

    def set_message_handler(self, message_handler: object) -> None:
        """Set message handler for incoming messages."""
        self.message_handler = message_handler

    def set_disconnect_callback(self, callback: callable) -> None:
        """设置断开回调函数

        当 WebSocket 连接断开时，会调用此回调函数通知外部。
        回调函数签名: callback(agent_id: str, server_url: str, code: int, reason: str)

        Args:
            callback: 断开时调用的回调函数
        """
        self._on_disconnect_callback = callback
        log_info(f"[MessageClient] 已设置断开回调: {callback}")

    def _build_websocket_url(self) -> str:
        """Build WebSocket URL with proper protocol and parameters."""
        ws_url = self.server_url.replace("https://", "wss://").replace("http://", "ws://")
        return f"{ws_url}/session?agent_id={self.agent_id}&signature={self.auth_client.signature}"

    def start_websocket_client(self) -> bool:
        """Start WebSocket client connection.

        修复：如果 WebSocket 连接实际上是正常的，不要创建新连接。
        只在连接真正断开时才创建新连接。
        """
        # ✅ 检查解释器是否正在关闭
        import sys
        if hasattr(sys, 'is_finalizing') and sys.is_finalizing():
            log_debug("Interpreter is shutting down, skipping connection")
            self._shutdown_requested = True
            return False

        if self._shutdown_requested:
            return False

        need_cleanup = False
        need_start = False
        conn_id = 0
        now = time.time()

        with self.lock:
            ws_open = self._is_ws_open()

            # ✅ 修复：如果 WebSocket 连接实际上是正常的，直接返回 true
            # 不管状态是什么，只要连接是 open 的就不需要重连
            if ws_open:
                # 修正状态（可能被错误地设置为 DISCONNECTED）
                if self._connection_state != ConnectionState.CONNECTED:
                    log_info(f"[conn:{self._connection_id}] WebSocket is open, fixing state from {self._connection_state.value} to connected")
                    self._connection_state = ConnectionState.CONNECTED
                    self.connected_event.set()
                return True

            # 如果正在连接中（另一个线程正在创建连接），等待结果
            if self._connection_state == ConnectionState.CONNECTING:
                conn_id = self._connection_id
                if (
                    self._connecting_conn_id == conn_id
                    and self._connecting_since > 0
                    and (now - self._connecting_since) > max(self.config.connection_timeout * 2, 10.0)
                ):
                    log_warning(
                        f"[conn:{conn_id}] Stale CONNECTING detected "
                        f"(elapsed={now - self._connecting_since:.1f}s), restarting connection"
                    )
                    need_cleanup = True
                    need_start = True
                    self._connection_id += 1
                    conn_id = self._connection_id
                    log_info(f"[conn:{conn_id}] Creating new connection: state=connecting(stale), ws_open={ws_open}")
                    self._connection_state = ConnectionState.CONNECTING
                    self._connecting_since = now
                    self._connecting_conn_id = conn_id
                    self.connected_event.clear()
                else:
                    log_debug(f"[conn:{conn_id}] Another thread is connecting, waiting...")
            else:
                # ✅ 只有在 ws 真正不可用时才创建新连接
                need_cleanup = True
                need_start = True
                self._connection_id += 1
                conn_id = self._connection_id
                # 记录为什么需要新连接
                log_info(f"[conn:{conn_id}] Creating new connection: state={self._connection_state.value}, ws_open={ws_open}")
                self._connection_state = ConnectionState.CONNECTING
                self._connecting_since = now
                self._connecting_conn_id = conn_id
                self.connected_event.clear()

        # 在锁外执行阻塞操作
        if need_cleanup:
            self._cleanup_old_connection_unlocked()

        if need_start:
            self.ws_url = self._build_websocket_url()
            log_debug(f"[conn:{conn_id}] Connecting to WebSocket URL: {self.ws_url}")

            # ✅ 记录连接尝试到专用日志
            ws_logger = get_ws_logger()
            ws_logger.log_connection_attempt(conn_id, self.ws_url, "new_connection")

            # Start WebSocket thread with asyncio loop
            self.ws_thread = threading.Thread(
                target=self._ws_handler,
                args=(conn_id,),
                daemon=True,
                name=f"WebSocketHandler-{conn_id}"
            )
            self.ws_thread.start()

        return self._wait_for_connection()

    def _cleanup_old_connection_unlocked(self) -> None:
        """Clean up old connection. Called WITHOUT lock held to avoid blocking."""
        log_info(f"[cleanup] 开始清理旧连接状态...")

        # 停止辅助线程标志
        self._cleanup_running = False
        self._health_check_running = False

        # ✅ 通知所有等待中的 stream 请求（创建新连接前清理旧状态）
        pending_count = self.get_pending_stream_count()  # ✅ 使用线程安全方法
        if pending_count > 0:
            log_warning(f"[cleanup] 通知 {pending_count} 个等待中的 stream 请求...")
        self._notify_pending_stream_requests("创建新连接，旧请求已取消")

        # 在锁内保存并清除旧的引用
        with self.lock:
            old_loop = self._loop
            old_ws = self.ws
            old_thread = self.ws_thread
            # 注意：不在这里清除引用，让新连接设置新值
            # 这样可以避免竞态条件

        # 关闭旧的 WebSocket
        if old_loop and old_ws:
            try:
                if old_loop.is_running():
                    future = asyncio.run_coroutine_threadsafe(
                        self._graceful_close_ws(old_ws),
                        old_loop
                    )
                    try:
                        future.result(timeout=2.0)
                    except Exception:
                        pass
            except Exception:
                pass

        # 停止旧的事件循环
        if old_loop:
            try:
                if old_loop.is_running():
                    old_loop.call_soon_threadsafe(old_loop.stop)
            except Exception:
                pass

        # 等待旧线程结束
        if old_thread and old_thread.is_alive():
            try:
                old_thread.join(timeout=2.0)
            except Exception:
                pass

    async def _graceful_close_ws(self, ws) -> None:
        """Gracefully close WebSocket connection."""
        if ws is None:
            return
        try:
            await asyncio.wait_for(ws.close(), timeout=1.0)
        except asyncio.TimeoutError:
            pass
        except Exception:
            pass

    def _cleanup_old_connection(self) -> None:
        """Clean up old connection (legacy method, calls unlocked version)."""
        self._cleanup_old_connection_unlocked()

    def _wait_for_connection(self) -> bool:
        """Wait for connection to be established."""
        result = self.connected_event.wait(timeout=self.config.connection_timeout)
        if not result:
            # 超时了，检查状态
            with self.lock:
                if self._connection_state == ConnectionState.CONNECTING:
                    # 连接超时，但线程可能还在运行，让它继续
                    # 下次调用会重新等待或创建新连接
                    log_debug("Connection wait timeout, connection still in progress")
                    if self._connecting_since > 0 and (time.time() - self._connecting_since) > self.config.connection_timeout:
                        log_warning("Connection appears stalled, marking DISCONNECTED to allow reconnect")
                        self._connection_state = ConnectionState.DISCONNECTED
                        self._connecting_since = 0.0
                        self._connecting_conn_id = 0
                        self.connected_event.clear()
        return result

    def stop_websocket_client(self) -> None:
        """Stop WebSocket client connection."""
        self._shutdown_requested = True

        # 停止清理线程
        self._stop_cleanup_thread()

        # 停止健康检查线程
        self._stop_health_check_thread()

        # 关闭 WebSocket
        if self._loop and self.ws:
            try:
                if self._loop.is_running():
                    future = asyncio.run_coroutine_threadsafe(
                        self._graceful_close_ws(self.ws),
                        self._loop
                    )
                    try:
                        future.result(timeout=2.0)
                    except Exception:
                        pass
            except Exception:
                pass

        # 停止事件循环
        if self._loop and self._loop.is_running():
            try:
                self._loop.call_soon_threadsafe(self._loop.stop)
            except Exception:
                pass

        if self.ws_thread and self.ws_thread.is_alive():
            self.ws_thread.join(timeout=2.0)
            self.ws_thread = None

        self._set_connection_state(ConnectionState.DISCONNECTED)

    def send_msg(self, msg: Union[str, Dict]) -> bool:
        """Send message through WebSocket with retry logic."""
        if not self._ensure_connection():
            return self._queue_message(msg)

        try:
            # 检查连接是否有效
            if not self._is_ws_open():
                log_debug("WebSocket connection invalid, queueing message")
                # 不设置 DISCONNECTED，让连接自然恢复或由健康检查处理
                return self._queue_message(msg)

            message_str = json.dumps(msg) if not isinstance(msg, str) else msg

            # ✅ 发送前检查消息大小，超过限制直接丢弃
            msg_size = len(message_str.encode('utf-8')) if isinstance(message_str, str) else len(message_str)
            if msg_size > self.config.max_message_size:
                log_error(f"[conn:{self._connection_id}] ❌ 发送消息过大，已丢弃: {msg_size/1024/1024:.2f}MB > {self.config.max_message_size/1024/1024:.0f}MB 限制")
                # 记录到专用日志
                ws_logger = get_ws_logger()
                ws_logger.log_abnormal_data(
                    conn_id=self._connection_id,
                    data=None,
                    error=f"发送消息大小 {msg_size/1024/1024:.2f}MB ({msg_size} bytes) 超过限制 {self.config.max_message_size/1024/1024:.0f}MB，已丢弃",
                    data_type="oversized_send_discarded"
                )
                return False  # 丢弃消息，返回失败

            # 使用事件循环发送消息
            if self._loop and self._loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    self._async_send(message_str),
                    self._loop
                )
                future.result(timeout=5.0)
                return True
            else:
                return self._queue_message(msg)

        except ConnectionClosed as e:
            log_debug(f"WebSocket connection closed during send: {e}")
            # 连接已关闭，设置状态（连接会自动重连）
            with self.lock:
                if self._connection_state == ConnectionState.CONNECTED:
                    self._connection_state = ConnectionState.DISCONNECTED
                    self.connected_event.clear()
            return self._queue_message(msg)
        except Exception as e:
            log_debug(f"Failed to send message: {e}")
            trace_id = msg.get("trace_id", "") if isinstance(msg, dict) else ""
            ErrorContext.publish(exceptions.SendMsgError(message=f"Error sending message: {e}", trace_id=trace_id))
            # 发送失败不一定意味着连接断开，不要设置 DISCONNECTED
            return self._queue_message(msg)

    async def _async_send(self, message: str) -> None:
        """Async send message."""
        if self._is_ws_open():
            await self.ws.send(message)

    def _ensure_connection(self) -> bool:
        """Ensure WebSocket connection is established."""
        # 快速路径：如果已连接且有效，直接返回
        if self._is_ws_open():
            # 只在状态是 DISCONNECTED 时修正为 CONNECTED
            # 不要修改 CONNECTING 状态，避免干扰正在进行的连接
            with self.lock:
                if self._connection_state == ConnectionState.DISCONNECTED:
                    self._connection_state = ConnectionState.CONNECTED
                    self.connected_event.set()
            return True

        # 需要建立连接
        retry_count = 0
        while retry_count < self.config.send_retry_attempts:
            if self.start_websocket_client():
                return True

            retry_count += 1
            if retry_count < self.config.send_retry_attempts:
                time.sleep(self.config.send_retry_delay)

        log_error(f"Failed to establish connection after {self.config.send_retry_attempts} attempts")
        return False

    def _queue_message(self, msg: Union[str, Dict]) -> bool:
        """Queue message for later sending."""
        try:
            if self.queue.full():
                try:
                    self.queue.get_nowait()
                    self.queue.task_done()
                except queue.Empty:
                    pass

            message_str = json.dumps(msg) if not isinstance(msg, str) else msg
            self.queue.put(message_str, timeout=1)
            log_debug("Message queued for later sending")
            return False

        except (queue.Full, queue.Empty) as e:
            log_error(f"Failed to queue message: {e}")
            return False

    def _handle_reconnection(self) -> None:
        """Handle reconnection logic with exponential backoff."""
        # ✅ 检查解释器是否正在关闭
        import sys
        if hasattr(sys, 'is_finalizing') and sys.is_finalizing():
            log_debug("Interpreter is shutting down, skipping reconnection")
            self._shutdown_requested = True
            return

        if self._shutdown_requested:
            return

        if not self.config.auto_reconnect:
            log_debug("Auto-reconnect is disabled, skipping reconnection")
            return

        # 使用锁保护 _is_retrying 标志
        with self.lock:
            if self._is_retrying:
                log_debug("Reconnection already in progress, skipping")
                return
            self._is_retrying = True
            # 不设置 RECONNECTING 状态，让 start_websocket_client 设置 CONNECTING

        reconnect_start_time = time.time()
        ws_logger = get_ws_logger()

        try:
            if self._reconnect_attempt_count == 0:
                self._current_reconnect_interval = self.config.reconnect_base_interval

            while not self._shutdown_requested:
                self._reconnect_attempt_count += 1

                if self.config.max_retry_attempts > 0 and self._reconnect_attempt_count > self.config.max_retry_attempts:
                    log_error(f"Reconnection failed after {self.config.max_retry_attempts} attempts, giving up")
                    # ✅ 记录重连失败
                    ws_logger.log_reconnect_fail(
                        conn_id=self._connection_id,
                        attempt=self._reconnect_attempt_count,
                        reason=f"达到最大重试次数 {self.config.max_retry_attempts}"
                    )
                    break

                # ✅ 记录重连开始
                ws_logger.log_reconnect_start(
                    conn_id=self._connection_id,
                    attempt=self._reconnect_attempt_count,
                    interval=self._current_reconnect_interval
                )

                if self._reconnect_attempt_count == 1 or self._reconnect_attempt_count % 10 == 0:
                    log_info(f"🔄 Reconnecting... attempt {self._reconnect_attempt_count} (interval: {self._current_reconnect_interval:.1f}s)")
                else:
                    log_debug(f"Reconnecting attempt {self._reconnect_attempt_count}")

                if self.start_websocket_client():
                    reconnect_duration = time.time() - reconnect_start_time
                    log_info("✅ Reconnection successful!")

                    # ✅ 记录重连成功
                    ws_logger.log_reconnect_success(
                        conn_id=self._connection_id,
                        attempt=self._reconnect_attempt_count,
                        duration=reconnect_duration,
                        pending_recovered=0  # 等待请求已在断开时通知，这里为0
                    )

                    # ✅ 增强：主动验证连接真正可用
                    if not self._verify_connection_after_reconnect():
                        log_warning("⚠️ 重连后连接验证失败，继续重试...")
                        time.sleep(self._current_reconnect_interval)
                        continue

                    # ✅ 执行系统恢复检查
                    self._perform_system_recovery_check()

                    # ✅ 触发连接恢复回调
                    if self._on_reconnect_callback:
                        try:
                            log_info(f"[conn:{self._connection_id}] 触发连接恢复回调...")
                            self._on_reconnect_callback(
                                agent_id=self.agent_id,
                                server_url=self.server_url
                            )
                        except Exception as e:
                            log_error(f"[conn:{self._connection_id}] 连接恢复回调执行异常: {e}")

                    self._reconnect_attempt_count = 0
                    self._current_reconnect_interval = self.config.reconnect_base_interval
                    return

                time.sleep(self._current_reconnect_interval)

                self._current_reconnect_interval = min(
                    self._current_reconnect_interval * self.config.reconnect_backoff_factor,
                    self.config.reconnect_max_interval
                )

            if self.config.max_retry_attempts > 0:
                log_error(f"Reconnection failed after {self.config.max_retry_attempts} attempts")

        finally:
            self._is_retrying = False
            if self.connection_state != ConnectionState.CONNECTED:
                self._set_connection_state(ConnectionState.DISCONNECTED)

    def _verify_connection_after_reconnect(self) -> bool:
        """✅ 重连后主动验证连接是否真正可用

        检查项：
        1. WebSocket 对象存在且状态为 OPEN
        2. 事件循环正在运行
        3. connected_event 已设置

        Returns:
            True: 连接验证通过
            False: 连接验证失败
        """
        try:
            # 等待一小段时间让连接稳定
            time.sleep(0.2)

            # 1. 检查 WebSocket 状态
            if not self._is_ws_open():
                log_warning(f"[验证] WebSocket 状态不是 OPEN")
                return False

            # 2. 检查事件循环
            if self._loop is None or not self._loop.is_running():
                log_warning(f"[验证] 事件循环未运行")
                return False

            # 3. 检查 connected_event
            if not self.connected_event.is_set():
                log_warning(f"[验证] connected_event 未设置")
                return False

            # 4. 检查连接状态
            if self.connection_state != ConnectionState.CONNECTED:
                log_warning(f"[验证] 连接状态不是 CONNECTED: {self.connection_state.value}")
                return False

            log_info(f"[验证] ✅ 连接验证通过")
            return True

        except Exception as e:
            log_error(f"[验证] 连接验证异常: {e}")
            return False

    def _perform_system_recovery_check(self) -> None:
        """✅ 执行系统恢复检查，确保重连后系统正常运行

        检查项目：
        1. WebSocket 连接状态
        2. 事件循环状态
        3. 队列状态
        4. 辅助线程状态
        """
        try:
            ws_logger = get_ws_logger()
            recovery_status = {}

            # 1. 检查连接状态
            ws_open = self._is_ws_open()
            recovery_status["ws_connection"] = "OK" if ws_open else "FAILED"

            # 2. 检查事件循环
            loop_running = self._loop is not None and self._loop.is_running()
            recovery_status["event_loop"] = "OK" if loop_running else "FAILED"

            # 3. 检查消息队列
            queue_size = self.queue.qsize() if self.queue else 0
            recovery_status["message_queue_size"] = queue_size
            recovery_status["message_queue"] = "OK"

            # 4. 检查 stream_queue_map（应该已被清空）
            pending_streams = self.get_pending_stream_count()  # ✅ 使用线程安全方法
            recovery_status["pending_stream_requests"] = pending_streams

            # 5. 检查辅助线程
            cleanup_running = self._cleanup_thread and self._cleanup_thread.is_alive()
            health_check_running = self._health_check_thread and self._health_check_thread.is_alive()
            recovery_status["cleanup_thread"] = "OK" if cleanup_running else "RESTARTING"
            recovery_status["health_check_thread"] = "OK" if health_check_running else "RESTARTING"

            # 6. 检查连接事件
            connected_event_set = self.connected_event.is_set()
            recovery_status["connected_event"] = "OK" if connected_event_set else "FAILED"

            # 判断整体状态
            all_ok = (
                ws_open and
                loop_running and
                connected_event_set
            )
            recovery_status["overall_status"] = "HEALTHY" if all_ok else "DEGRADED"

            # 记录恢复状态
            ws_logger.log_system_recovery(
                conn_id=self._connection_id,
                recovery_status=recovery_status
            )

            if all_ok:
                log_info(f"✅ [系统恢复] 所有检查通过，系统已完全恢复")
            else:
                log_warning(f"⚠️ [系统恢复] 部分检查未通过: {recovery_status}")

                # 尝试修复问题
                if not cleanup_running:
                    log_info("🔧 重启清理线程...")
                    self._start_cleanup_thread()

                if not health_check_running:
                    log_info("🔧 重启健康检查线程...")
                    self._start_health_check_thread()

        except Exception as e:
            log_error(f"❌ 系统恢复检查失败: {e}")

    async def _process_queued_messages(self) -> None:
        """Process messages that were queued during disconnection."""
        try:
            while not self.queue.empty():
                try:
                    message = self.queue.get_nowait()
                    if self._is_ws_open():
                        await self.ws.send(message)
                    self.queue.task_done()
                except queue.Empty:
                    break
                except Exception as e:
                    log_error(f"Failed to send queued message: {e}")
                    break
        except Exception as e:
            log_error(f"Error processing queued messages: {e}")

    def _cleanup_stale_stream_queues(self, owner_conn_id: int) -> None:
        """定期清理过期的流队列"""
        log_info(f"[conn:{owner_conn_id}] 🧹 流队列清理线程已启动")
        cleanup_interval = 30
        last_cleanup_time = time.time()

        while self._cleanup_running and not self._shutdown_requested:
            try:
                # 使用短间隔 sleep，快速响应停止信号
                time.sleep(1.0)

                # 检查连接 ID 是否仍然有效
                if self._connection_id != owner_conn_id:
                    log_debug(f"[conn:{owner_conn_id}] 清理线程: 连接已被取代，退出")
                    break

                if not self._cleanup_running or self._shutdown_requested:
                    break

                # 检查是否到达清理间隔
                now = time.time()
                if now - last_cleanup_time < cleanup_interval:
                    continue
                last_cleanup_time = now

                stale_requests = []

                # ✅ 使用锁保护遍历操作
                with self._stream_queue_lock:
                    for request_id, entry in list(self.stream_queue_map.items()):
                        timestamp = entry.get("timestamp", now)
                        age = now - timestamp

                        if age > 15.0:
                            stale_requests.append({
                                "request_id": request_id,
                                "age": age,
                                "receiver": entry.get("receiver", "unknown"),
                                "entry": entry  # 保存完整的 entry
                            })

                    # ✅ 在锁内移除过期请求
                    for req in stale_requests:
                        self.stream_queue_map.pop(req["request_id"], None)
                    remaining_count = len(self.stream_queue_map)

                # ✅ 释放锁后再处理通知
                if stale_requests:
                    log_info(f"🧹 发现 {len(stale_requests)} 个过期流请求，开始清理...")

                    for req in stale_requests:
                        request_id = req["request_id"]
                        queue_entry = req["entry"]

                        log_error(f"⚠️ 清理过期流请求: request_id={request_id[:8]}... "
                                f"receiver={req['receiver']} 等待时间={req['age']:.1f}s")

                        try:
                            temp_queue = queue_entry["queue"]
                            loop = queue_entry.get("loop")

                            if temp_queue.empty() and loop:
                                error_data = {"error": "timeout", "message": "流创建超时"}
                                loop.call_soon_threadsafe(temp_queue.put_nowait, error_data)
                        except Exception as e:
                            log_debug(f"清理队列时异常（可忽略）: {e}")

                    log_info(f"✅ 清理完成，剩余等待请求: {remaining_count}")

            except Exception as e:
                log_error(f"❌ 流队列清理异常: {e}")

        log_info(f"[conn:{owner_conn_id}] 🧹 流队列清理线程已停止")

    def _start_cleanup_thread(self) -> None:
        """启动清理线程"""
        # 如果旧线程还在运行，先等待它停止
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            if self._cleanup_running:
                return  # 线程正常运行中，不需要重启
            # 等待旧线程结束
            self._cleanup_thread.join(timeout=2.0)

        self._cleanup_running = True

        # 传递当前连接 ID
        current_conn_id = self._connection_id

        self._cleanup_thread = threading.Thread(
            target=self._cleanup_stale_stream_queues,
            args=(current_conn_id,),
            daemon=True,
            name=f"StreamQueueCleanup-{current_conn_id}"
        )
        self._cleanup_thread.start()
        log_debug(f"[conn:{current_conn_id}] 流队列清理线程已启动")

    def _stop_cleanup_thread(self) -> None:
        """停止清理线程"""
        if not self._cleanup_thread:
            return

        self._cleanup_running = False

        if self._cleanup_thread.is_alive():
            self._cleanup_thread.join(timeout=2.0)

        self._cleanup_thread = None
        log_debug("流队列清理线程已停止")

    def _start_health_check_thread(self) -> None:
        """启动连接健康检查线程"""
        # 如果旧线程还在运行，先等待它停止
        if self._health_check_thread and self._health_check_thread.is_alive():
            if self._health_check_running:
                return  # 线程正常运行中，不需要重启
            # 等待旧线程结束
            self._health_check_thread.join(timeout=2.0)

        self._health_check_running = True
        self._last_pong_time = time.time()

        # 传递当前连接 ID，让线程知道它属于哪个连接
        current_conn_id = self._connection_id

        self._health_check_thread = threading.Thread(
            target=self._health_check_loop,
            args=(current_conn_id,),
            daemon=True,
            name=f"WebSocketHealthCheck-{current_conn_id}"
        )
        self._health_check_thread.start()
        log_debug(f"[conn:{current_conn_id}] 连接健康检查线程已启动")

    def _stop_health_check_thread(self) -> None:
        """停止连接健康检查线程"""
        self._health_check_running = False

        if self._health_check_thread and self._health_check_thread.is_alive():
            self._health_check_thread.join(timeout=2.0)

        self._health_check_thread = None
        log_debug("连接健康检查线程已停止")

    def _health_check_loop(self, owner_conn_id: int) -> None:
        """连接健康检查循环

        注意：websockets 库内部已经处理了 ping/pong，会自动关闭不响应的连接。
        因此这里只需要检查 WebSocket 状态，不需要自己判断 pong 超时。
        """
        # ✅ 优化：缩短检查间隔，更快发现连接问题
        check_interval = self.config.ping_interval * 2  # 从 *3 改为 *2（6秒检查一次）
        ws_logger = get_ws_logger()

        log_debug(f"[conn:{owner_conn_id}] 健康检查线程启动: 检查间隔={check_interval}s")

        last_check_time = time.time()

        while self._health_check_running and not self._shutdown_requested:
            try:
                # 使用短间隔 sleep，快速响应停止信号
                time.sleep(1.0)

                # 检查连接 ID 是否仍然有效（防止旧线程继续运行）
                if self._connection_id != owner_conn_id:
                    log_debug(f"[conn:{owner_conn_id}] 健康检查线程: 连接已被取代 (当前: {self._connection_id})，退出")
                    break

                if not self._health_check_running or self._shutdown_requested:
                    break

                # 检查是否到达检查间隔
                now = time.time()
                if now - last_check_time < check_interval:
                    continue
                last_check_time = now

                # 再次检查连接 ID
                if self._connection_id != owner_conn_id:
                    log_debug(f"[conn:{owner_conn_id}] 健康检查线程: 连接已被取代，退出")
                    break

                # 获取当前状态
                ws_open = self._is_ws_open()
                conn_state = self.connection_state.value

                # 检查连接状态
                if self.connection_state == ConnectionState.DISCONNECTED:
                    log_debug(f"[conn:{owner_conn_id}] 健康检查: 检测到连接状态为 DISCONNECTED")
                    # 只在触发重连时记录日志
                    ws_logger.log_health_check(
                        conn_id=owner_conn_id,
                        ws_open=ws_open,
                        connection_state=conn_state,
                        action="trigger_reconnect_state_disconnected"
                    )
                    # ✅ 修复：触发重连前先通知所有等待中的请求
                    self._notify_pending_stream_requests("健康检查检测到连接断开")
                    if not self._is_retrying:
                        threading.Thread(target=self._handle_reconnection, daemon=True).start()
                    continue

                # 检查 WebSocket 对象是否有效
                if not ws_open:
                    log_debug(f"[conn:{owner_conn_id}] 健康检查: WebSocket 连接已关闭")
                    # 只在触发重连时记录日志
                    ws_logger.log_health_check(
                        conn_id=owner_conn_id,
                        ws_open=ws_open,
                        connection_state=conn_state,
                        action="trigger_reconnect_ws_closed"
                    )
                    # ✅ 修复：触发重连前先通知所有等待中的请求
                    self._notify_pending_stream_requests("健康检查检测到WebSocket关闭")
                    self._set_connection_state(ConnectionState.DISCONNECTED)
                    if not self._is_retrying:
                        threading.Thread(target=self._handle_reconnection, daemon=True).start()
                    continue

                # 连接正常，更新 pong 时间（用于统计，不用于判断断开）
                # 不记录日志，避免日志量过大
                self._last_pong_time = time.time()

            except Exception as e:
                log_error(f"[conn:{owner_conn_id}] 健康检查异常: {e}")

        log_debug(f"[conn:{owner_conn_id}] 健康检查线程已退出")

    def _ws_handler(self, conn_id: int) -> None:
        """WebSocket handler thread function with asyncio loop."""
        loop = None
        try:
            # ✅ 检查解释器是否正在关闭
            import sys
            if hasattr(sys, 'is_finalizing') and sys.is_finalizing():
                log_debug(f"[conn:{conn_id}] Interpreter is shutting down, skipping connection")
                self._shutdown_requested = True
                return

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop

            loop.run_until_complete(self._ws_connect_and_receive(conn_id))

        except RuntimeError as e:
            error_str = str(e).lower()
            # ✅ 检测解释器关闭相关的错误
            if "interpreter shutdown" in error_str or "cannot schedule" in error_str:
                log_warning(f"[conn:{conn_id}] Interpreter shutting down, stopping reconnection")
                self._shutdown_requested = True  # 阻止重连
            else:
                log_debug(f"[conn:{conn_id}] WebSocket handler RuntimeError: {e}")
        except Exception as e:
            error_str = str(e).lower()
            # ✅ 也检查通用异常中的解释器关闭错误
            if "interpreter shutdown" in error_str or "cannot schedule" in error_str:
                log_warning(f"[conn:{conn_id}] Interpreter shutting down, stopping reconnection")
                self._shutdown_requested = True
            else:
                log_debug(f"[conn:{conn_id}] WebSocket handler error: {e}")
        finally:
            # 只有当前连接才设置 DISCONNECTED 状态
            with self.lock:
                if self._connection_id == conn_id:
                    log_debug(f"[conn:{conn_id}] Handler exiting, setting DISCONNECTED")
                    self._connection_state = ConnectionState.DISCONNECTED
                    self._connecting_since = 0.0
                    self._connecting_conn_id = 0
                    self.connected_event.clear()
                    self.ws = None
                else:
                    log_debug(f"[conn:{conn_id}] Handler exiting, but superseded by conn:{self._connection_id}")

            # 安全关闭事件循环
            if loop and not loop.is_closed():
                try:
                    # 只有当 loop 没有运行时才能安全地取消任务
                    if not loop.is_running():
                        # 取消所有pending任务
                        pending = asyncio.all_tasks(loop)
                        for task in pending:
                            task.cancel()

                        # 等待任务取消完成
                        if pending:
                            loop.run_until_complete(
                                asyncio.gather(*pending, return_exceptions=True)
                            )

                    # 关闭loop
                    if not loop.is_closed():
                        loop.close()
                except Exception:
                    pass

    async def _ws_connect_and_receive(self, conn_id: int) -> None:
        """Async WebSocket connection and message receiving loop."""
        ssl_context = None
        if self.ws_url and self.ws_url.startswith("wss://"):
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

        # 准备代理配置（localhost 永远直连，避免全局代理/VPN 劫持）
        use_proxy = self._get_use_system_proxy() and (not is_local_url(self.ws_url))
        extra_headers = {}
        saved_proxy_env = None

        try:
            # websockets库通过环境变量支持代理，但我们可以通过extra_headers传递代理信息
            # 如果不使用代理，确保不会使用环境变量中的代理设置
            import os
            import platform
            if not use_proxy:
                # 临时清除代理环境变量（只影响本次握手），确保 localhost 不会走代理
                saved_proxy_env = pop_proxy_env()

            # 准备 websockets.connect 参数
            # 注意：websockets 14.2+ 在某些平台（macOS/Darwin）上不支持 proxy 参数
            # 会抛出 "BaseEventLoop.create_connection() got an unexpected keyword argument 'proxy'"
            ws_connect_kwargs = {
                "ssl": ssl_context,
                "open_timeout": self.config.connection_timeout,
                "ping_interval": self.config.ping_interval,
                "ping_timeout": self.config.ping_interval * 10,
                "close_timeout": 5,
                "max_size": None,  # ✅ 禁用协议层大小限制，在应用层处理超大消息
                "compression": "deflate",  # ✅ 启用压缩，与服务器协商压缩扩展
            }
            
            # macOS (Darwin) 上 websockets 14.2+ 不支持 proxy 参数
            # 其他平台显式禁用代理（配合环境变量清除）
            if platform.system() != "Darwin":
                ws_connect_kwargs["proxy"] = None

            async with websockets.connect(
                self.ws_url,
                **ws_connect_kwargs
            ) as ws:
                # 连接建立后立即恢复代理环境变量（避免影响进程内其他请求）
                if saved_proxy_env:
                    restore_proxy_env(saved_proxy_env)
                    saved_proxy_env = None
                # 检查连接ID是否仍然有效（防止旧连接继续处理）
                with self.lock:
                    if self._connection_id != conn_id:
                        log_debug(f"[conn:{conn_id}] Connection superseded by conn:{self._connection_id}, closing")
                        # ✅ 记录连接被取代到专用日志
                        ws_logger = get_ws_logger()
                        ws_logger.log_connection_superseded(conn_id, self._connection_id, "_ws_connect_and_receive:after_connect")
                        return

                self.ws = ws

                # 连接成功
                log_info(f"[conn:{conn_id}] WebSocket connection established")
                self._set_connection_state(ConnectionState.CONNECTED)
                with self.lock:
                    self._is_retrying = False
                self._reconnect_attempt_count = 0
                self._current_reconnect_interval = self.config.reconnect_base_interval
                self._last_pong_time = time.time()

                # ✅ 记录连接建立到专用日志
                ws_logger = get_ws_logger()
                ws_logger.log_connection_established(
                    conn_id=conn_id,
                    ws_url=self.ws_url,
                    extra_info={
                        "agent_id": self.agent_id,
                        "ping_interval": self.config.ping_interval,
                        "has_handler": self.message_handler is not None
                    }
                )

                # 启动辅助线程（异常不影响主流程）
                try:
                    self._start_cleanup_thread()
                    ws_logger.log_helper_thread(conn_id, "cleanup", "started")
                except Exception as e:
                    log_error(f"[conn:{conn_id}] 启动清理线程失败: {e}")
                    ws_logger.log_helper_thread(conn_id, "cleanup", "start_failed", success=False, error=str(e))

                try:
                    self._start_health_check_thread()
                    ws_logger.log_helper_thread(conn_id, "health_check", "started")
                except Exception as e:
                    log_error(f"[conn:{conn_id}] 启动健康检查线程失败: {e}")
                    ws_logger.log_helper_thread(conn_id, "health_check", "start_failed", success=False, error=str(e))

                # 调用消息处理器的 on_open
                if self.message_handler and hasattr(self.message_handler, "on_open"):
                    try:
                        self.message_handler.on_open(ws)
                        ws_logger.log_on_open_callback(
                            conn_id=conn_id,
                            success=True,
                            handler_type=type(self.message_handler).__name__
                        )
                    except Exception as e:
                        log_exception(f"[conn:{conn_id}] Error in message handler on_open: {e}")
                        ws_logger.log_on_open_callback(
                            conn_id=conn_id,
                            success=False,
                            error=str(e),
                            handler_type=type(self.message_handler).__name__
                        )

                # 处理队列中的消息
                await self._process_queued_messages()

                # 消息接收循环
                loop_start_time = time.time()
                messages_received = 0
                last_stats_time = time.time()
                stats_interval = 60.0  # 每60秒记录一次统计

                # ✅ 新增：记录最近的消息类型（用于诊断）
                recent_msg_types = []  # 保存最近20条消息的类型
                max_recent = 20

                # ✅ 新增：追踪消息大小
                max_msg_size = 0  # 最大消息大小
                total_bytes = 0   # 总字节数
                large_msg_count = 0  # 大消息计数（>100KB）

                # ✅ 修改：使用 while True + recv() 代替 async for，以便捕获单条消息的协议错误
                protocol_error_count = 0  # RSV 位错误计数（用于日志）

                while True:
                    # 检查连接是否仍然有效
                    if self._connection_id != conn_id:
                        log_debug(f"[conn:{conn_id}] Connection superseded, exiting message loop")
                        ws_logger.log_connection_superseded(conn_id, self._connection_id, "message_loop")
                        ws_logger.log_message_loop_exit(
                            conn_id=conn_id,
                            reason="connection_superseded",
                            messages_received=messages_received,
                            duration=time.time() - loop_start_time
                        )
                        return

                    # 检查连接状态（websockets 15.x 使用 state 而不是 closed）
                    if ws.state != WsState.OPEN:
                        log_debug(f"[conn:{conn_id}] WebSocket connection not open (state={ws.state}), exiting message loop")
                        break

                    try:
                        # ✅ 使用 recv() 接收消息，可以在这里捕获单条消息的错误
                        message = await ws.recv()
                        protocol_error_count = 0  # 成功接收，重置错误计数

                    except ProtocolError as e:
                        error_str = str(e).lower()
                        # ✅ 检查是否是 RSV 位错误
                        if "reserved bits" in error_str or "rsv" in error_str:
                            protocol_error_count += 1
                            log_warning(f"[conn:{conn_id}] ⚠️ RSV 位错误 (第 {protocol_error_count} 次): {e}")
                            ws_logger.log_abnormal_data(
                                conn_id=conn_id,
                                data=None,
                                error=f"RSV位错误: {e}",
                                data_type="rsv_bit_error"
                            )

                            # ✅ RSV 位错误时，websockets 库已经发送了关闭帧，连接无法继续
                            # 抛出 ConnectionClosedError 让外层统一处理（正确清理资源后重连）
                            log_info(f"[conn:{conn_id}] RSV 位错误导致连接关闭，触发快速重连")
                            from websockets.frames import Close
                            # 创建一个带有清晰原因的 ConnectionClosedError
                            raise ConnectionClosedError(
                                Close(1006, f"RSV位错误: {str(e)[:80]}"),
                                None
                            )
                        else:
                            # 其他协议错误，向上抛出
                            raise

                    except ConnectionClosed:
                        # 连接关闭，退出循环让外层处理
                        raise

                    try:
                        self._last_pong_time = time.time()
                        self._set_connection_state(ConnectionState.CONNECTED)
                        messages_received += 1

                        # ✅ 新增：追踪消息大小
                        msg_size = len(message) if message else 0
                        total_bytes += msg_size
                        if msg_size > max_msg_size:
                            max_msg_size = msg_size

                        # ✅ 应用层消息大小检查：超过阈值直接丢弃，不影响WebSocket连接
                        if msg_size > self.config.max_message_size:
                            large_msg_count += 1
                            log_error(f"[conn:{conn_id}] ❌ 收到超大消息，已丢弃: {msg_size/1024/1024:.1f}MB > {self.config.max_message_size/1024/1024:.0f}MB 限制")
                            # 记录到专用日志（只记录大小，不记录内容）
                            ws_logger.log_abnormal_data(
                                conn_id=conn_id,
                                data=None,
                                error=f"消息大小 {msg_size/1024/1024:.2f}MB ({msg_size} bytes) 超过限制 {self.config.max_message_size/1024/1024:.0f}MB，已丢弃",
                                data_type="oversized_message_discarded"
                            )
                            continue  # ✅ 丢弃消息，继续处理下一条，不断开连接

                        if msg_size > 1 * 1024 * 1024:  # >1MB
                            large_msg_count += 1
                            log_warning(f"[conn:{conn_id}] ⚠️ 收到大消息: {msg_size/1024/1024:.1f}MB")

                        # 定期记录消息统计（每60秒）
                        now = time.time()
                        if now - last_stats_time >= stats_interval:
                            interval_time = now - last_stats_time
                            avg_msg_size = total_bytes / messages_received if messages_received > 0 else 0
                            throughput_kb = (total_bytes / 1024) / interval_time  # KB/s

                            # ✅ 检测异常流量
                            if throughput_kb > 10000:  # >10MB/s
                                log_error(f"[conn:{conn_id}] ⚠️ 异常高流量: {throughput_kb:.0f}KB/s, 平均消息大小: {avg_msg_size/1024:.1f}KB")

                            ws_logger.log_message_received(
                                conn_id=conn_id,
                                message_type="stats",
                                message_size=0,
                                cmd=None,
                                extra_info={
                                    "total_messages": messages_received,
                                    "interval_seconds": int(interval_time),
                                    "loop_duration": int(now - loop_start_time),
                                    "avg_msg_size_kb": f"{avg_msg_size/1024:.1f}",
                                    "throughput_kb_s": f"{throughput_kb:.0f}",
                                    "total_bytes_mb": f"{total_bytes/1024/1024:.1f}",
                                    "large_msg_count": large_msg_count
                                }
                            )
                            last_stats_time = now

                        if isinstance(message, bytes):
                            # 二进制消息，尝试解码
                            try:
                                message = message.decode('utf-8')
                            except UnicodeDecodeError as e:
                                # ✅ 记录异常数据到专用日志
                                ws_logger.log_abnormal_data(
                                    conn_id=conn_id,
                                    data=message,
                                    error=f"二进制消息解码失败: {e}",
                                    data_type="binary"
                                )
                                log_warning(f"[conn:{conn_id}] Failed to decode binary message (discarded): {e}")
                                continue

                        # ✅ 新增：提取并记录消息类型
                        msg_cmd = "unknown"
                        try:
                            msg_json = json.loads(message) if isinstance(message, str) else {}
                            msg_cmd = msg_json.get("cmd", "no_cmd")
                        except Exception:
                            msg_cmd = "parse_error"

                        recent_msg_types.append(msg_cmd)
                        if len(recent_msg_types) > max_recent:
                            recent_msg_types.pop(0)

                        # 处理消息
                        if self.message_handler and hasattr(self.message_handler, "on_message"):
                            try:
                                self.message_handler.on_message(ws, message)
                            except Exception as e:
                                # ✅ 记录消息处理错误到专用日志
                                ws_logger.log_message_error(
                                    conn_id=conn_id,
                                    message=message,
                                    error=str(e)
                                )
                                log_exception(f"[conn:{conn_id}] Error in message handler: {e}")

                    except Exception as e:
                        # ✅ 记录异常数据到专用日志
                        ws_logger.log_abnormal_data(
                            conn_id=conn_id,
                            data=message if 'message' in locals() else None,
                            error=f"消息处理异常: {e}",
                            data_type="unknown"
                        )
                        log_warning(f"[conn:{conn_id}] Error processing message (discarded): {e}")
                        continue

                # while True 循环正常结束（ws.state != OPEN）
                log_debug(f"[conn:{conn_id}] WebSocket message loop ended normally")
                ws_logger.log_message_loop_exit(
                    conn_id=conn_id,
                    reason="loop_ended_normally",
                    messages_received=messages_received,
                    duration=time.time() - loop_start_time
                )
                self._handle_connection_close(conn_id, None, "connection ended")

        except ConnectionClosed as e:
            # ✅ 增强日志：记录更多诊断信息
            connection_duration = time.time() - loop_start_time if 'loop_start_time' in locals() else 0
            msgs_count = messages_received if 'messages_received' in locals() else 0
            recent_types = recent_msg_types if 'recent_msg_types' in locals() else []
            max_size = max_msg_size if 'max_msg_size' in locals() else 0
            total = total_bytes if 'total_bytes' in locals() else 0
            large_count = large_msg_count if 'large_msg_count' in locals() else 0

            log_warning(f"[conn:{conn_id}] WebSocket connection closed: code={e.code}, reason={e.reason}, "
                       f"duration={connection_duration:.1f}s, messages={msgs_count}, max_size={max_size/1024:.1f}KB")

            # ✅ 记录连接关闭异常到专用日志（包含诊断信息）
            ws_logger = get_ws_logger()
            ws_logger.log_connection_closed(
                conn_id=conn_id,
                code=e.code,
                reason=e.reason or "(empty)",
                connection_duration=connection_duration,
                messages_received=msgs_count,
                last_pong_time=self._last_pong_time,
                extra_info={
                    "ws_url": self.ws_url[:80] if self.ws_url else "N/A",
                    "agent_id": self.agent_id,
                    "code_meaning": self._get_close_code_meaning(e.code),
                    "recent_msg_types": recent_types[-10:] if recent_types else [],
                    "max_msg_size_kb": f"{max_size/1024:.1f}",
                    "total_bytes_kb": f"{total/1024:.1f}",
                    "large_msg_count": large_count,
                    "exception_type": type(e).__name__,
                    "exception_detail": str(e)[:200] if str(e) else "(none)"
                }
            )
            self._handle_connection_close(conn_id, e.code, e.reason)

        except asyncio.TimeoutError:
            log_warning(f"[conn:{conn_id}] WebSocket connection timeout")
            self._handle_connection_close(conn_id, None, "timeout")

        except PayloadTooBig as e:
            if saved_proxy_env:
                restore_proxy_env(saved_proxy_env)
                saved_proxy_env = None
            # ✅ 备用处理：max_size=None时此异常不应触发，保留作为防御性编程
            log_error(f"[conn:{conn_id}] ❌ 收到的消息太大，超过限制: {e}")
            ws_logger = get_ws_logger()
            ws_logger.log_abnormal_data(
                conn_id=conn_id,
                data=None,
                error=f"PayloadTooBig: {e}",
                data_type="payload_too_big"
            )
            self._handle_connection_close(conn_id, None, f"消息太大: {e}")

        except ProtocolError as e:
            if saved_proxy_env:
                restore_proxy_env(saved_proxy_env)
                saved_proxy_env = None
            # ✅ 协议错误（如无效的帧、RSV位错误等）
            log_error(f"[conn:{conn_id}] ❌ WebSocket 协议错误: {e}")
            ws_logger = get_ws_logger()
            ws_logger.log_abnormal_data(
                conn_id=conn_id,
                data=None,
                error=f"ProtocolError: {e}",
                data_type="protocol_error"
            )
            # 协议错误通常表示服务器行为异常，增加重连间隔
            self._current_reconnect_interval = min(
                self._current_reconnect_interval * 3,
                self.config.reconnect_max_interval
            )
            self._handle_connection_close(conn_id, None, f"协议错误: {e}")

        except InvalidMessage as e:
            if saved_proxy_env:
                restore_proxy_env(saved_proxy_env)
                saved_proxy_env = None
            # ✅ 无效的消息格式
            log_error(f"[conn:{conn_id}] ❌ 无效的 WebSocket 消息: {e}")
            ws_logger = get_ws_logger()
            ws_logger.log_abnormal_data(
                conn_id=conn_id,
                data=None,
                error=f"InvalidMessage: {e}",
                data_type="invalid_message"
            )
            self._handle_connection_close(conn_id, None, f"无效消息: {e}")

        except Exception as e:
            error_str = str(e)

            # 检查是否为连接数限制错误
            is_rate_limit = (
                "400" in error_str or
                "超过连接数限制" in error_str or
                "connection limit" in error_str.lower()
            )

            if is_rate_limit:
                current_time = time.time()
                if current_time - MessageClient._last_rate_limit_log_time > MessageClient._rate_limit_log_interval:
                    MessageClient._last_rate_limit_log_time = current_time
                    log_warning(f"[conn:{conn_id}] WebSocket rate limit: 超过连接数限制")
                self._current_reconnect_interval = min(
                    self._current_reconnect_interval * 2,
                    self.config.reconnect_max_interval
                )
            else:
                log_debug(f"[conn:{conn_id}] WebSocket connection error: {e}")
                # ✅ 记录异常到专用日志
                ws_logger = get_ws_logger()
                ws_logger.log_abnormal_data(
                    conn_id=conn_id,
                    data=None,
                    error=f"WebSocket异常: {error_str}",
                    data_type="exception"
                )

            self._handle_connection_close(conn_id, None, str(e))

    def _handle_connection_close(self, conn_id: int, code: Optional[int], reason: str, received_data: any = None) -> None:
        """Handle connection close event."""
        # 检查连接ID是否仍然有效
        is_current_connection = False
        current_conn_id = 0
        with self.lock:
            current_conn_id = self._connection_id
            if self._connection_id != conn_id:
                log_warning(f"[conn:{conn_id}] 连接已被取代 (当前: {self._connection_id})，仍执行清理")
                # ✅ 不直接 return，异常断开时仍需清理
            else:
                is_current_connection = True
                log_info(f"[conn:{conn_id}] 当前连接断开: code={code}, reason={reason}")
                self._connection_state = ConnectionState.DISCONNECTED
                self._connecting_since = 0.0
                self._connecting_conn_id = 0
                self.connected_event.clear()
                self.ws = None

        # ✅ 记录到专用 WebSocket 日志（无论是否是当前连接）
        with self._stream_queue_lock:
            pending_count = len(self.stream_queue_map)

        ws_logger = get_ws_logger()

        # ✅ 记录连接被取代事件
        if not is_current_connection:
            ws_logger.log_connection_superseded(conn_id, current_conn_id, "_handle_connection_close")

        try:
            ws_logger.log_disconnect(
                conn_id=conn_id,
                reason=reason,
                code=code,
                received_data=received_data,
                pending_requests=pending_count,
                extra_info={
                    "agent_id": self.agent_id,
                    "server_url": self.server_url,
                    "is_current_connection": is_current_connection,
                    "current_conn_id": current_conn_id
                }
            )
        except Exception as e:
            log_error(f"记录 WebSocket 断开日志失败: {e}")

        # ✅ 修复：连接断开时立即通知所有等待中的 stream 请求
        self._notify_pending_stream_requests(f"连接断开: {reason}")

        # ✅ 只有当前连接断开时才执行重置和重连（旧连接断开不处理，因为已有新连接）
        if not is_current_connection:
            log_debug(f"[conn:{conn_id}] 旧连接断开，跳过重置和重连（当前连接: {self._connection_id}）")
            return

        # ✅ 触发断开回调通知外部（仅当前连接的异常断开才通知）
        if code != 1000 and self._on_disconnect_callback:
            try:
                log_info(f"[conn:{conn_id}] 触发断开回调通知外部...")
                self._on_disconnect_callback(
                    agent_id=self.agent_id,
                    server_url=self.server_url,
                    code=code,
                    reason=reason
                )
            except Exception as e:
                log_error(f"[conn:{conn_id}] 断开回调执行异常: {e}")

        # ✅ 异常断开时执行完全重置（模拟重启应用的效果）
        # 注意：_full_reset 会清理状态，但不能在当前线程（WebSocket线程）中停止事件循环
        need_full_reset = code == 1006 or code == 1002 or code is None or "400" in str(reason) or "protocol" in str(reason).lower()
        if need_full_reset:
            log_warning(f"[conn:{conn_id}] 检测到异常断开(code={code})，执行部分重置...")
            # ✅ 修复：不调用 _full_reset（会尝试停止当前线程的事件循环导致问题）
            # 只清理必要的状态，让 _handle_reconnection 处理重连
            self._partial_reset_for_reconnect(conn_id)

        if not self._shutdown_requested and self.config.auto_reconnect:
            if code != 1000:  # 非正常关闭
                with self.lock:
                    if not self._is_retrying:
                        log_debug(f"[conn:{conn_id}] Triggering reconnection")
                        # ✅ 给重连一点时间让当前线程完成清理
                        def delayed_reconnect():
                            time.sleep(0.5)  # 等待当前 WebSocket 线程完全结束
                            self._handle_reconnection()
                        threading.Thread(target=delayed_reconnect, daemon=True, name=f"Reconnect-{conn_id}").start()

    def _full_reset(self, conn_id: int) -> None:
        """✅ 完全重置连接状态（模拟重启应用的效果）

        当检测到异常断开时，清理所有状态，确保重连后系统能正常运转。
        """
        ws_logger = get_ws_logger()
        log_warning(f"[conn:{conn_id}] ========== 开始完全重置 ==========")
        ws_logger.log_full_reset_detail(conn_id, "start", "开始完全重置流程")

        try:
            # ✅ 0. 首先重置连接状态（关键！阻止其他线程创建新连接）
            old_conn_id = 0
            with self.lock:
                old_conn_id = self._connection_id
                self._connection_id = 0
                self._is_retrying = False
                self._connection_state = ConnectionState.DISCONNECTED
                self._connecting_since = 0.0
                self._connecting_conn_id = 0
                self.connected_event.clear()
            log_info(f"[conn:{conn_id}] ✅ 连接ID重置: {old_conn_id} → 0")
            ws_logger.log_full_reset_detail(conn_id, "reset_conn_id", f"old={old_conn_id} -> new=0")

            # 1. 停止所有辅助线程（关键！防止它们继续干扰）
            log_info(f"[conn:{conn_id}] 🛑 停止辅助线程...")
            self._cleanup_running = False
            self._health_check_running = False
            ws_logger.log_full_reset_detail(conn_id, "stop_threads", "设置线程停止标志")

            # 2. 清空消息队列
            queue_size = self.queue.qsize()
            cleared_count = 0
            while not self.queue.empty():
                try:
                    self.queue.get_nowait()
                    self.queue.task_done()
                    cleared_count += 1
                except queue.Empty:
                    break

            log_info(f"[conn:{conn_id}] 🧹 清空消息队列: {cleared_count}/{queue_size} 条消息已丢弃")
            ws_logger.log_full_reset_detail(conn_id, "clear_queue", f"cleared={cleared_count}, total={queue_size}")

            # 3. 清空 stream_queue_map（已经在 _notify_pending_stream_requests 中通知过了）
            with self._stream_queue_lock:
                stream_count = len(self.stream_queue_map)
                self.stream_queue_map.clear()
            log_info(f"[conn:{conn_id}] 🧹 清空流请求映射: {stream_count} 个请求已清理")
            ws_logger.log_full_reset_detail(conn_id, "clear_streams", f"cleared={stream_count}")

            # 4. 关闭旧的 WebSocket 连接
            old_ws = self.ws
            old_loop = self._loop
            if old_loop and old_ws:
                try:
                    if old_loop.is_running():
                        future = asyncio.run_coroutine_threadsafe(
                            self._graceful_close_ws(old_ws),
                            old_loop
                        )
                        try:
                            future.result(timeout=1.0)
                        except Exception:
                            pass
                except Exception:
                    pass
                log_info(f"[conn:{conn_id}] 🔌 旧 WebSocket 连接已关闭")
                ws_logger.log_full_reset_detail(conn_id, "close_ws", "旧WebSocket已关闭")

            # 5. 停止旧的事件循环
            if old_loop and old_loop.is_running():
                try:
                    old_loop.call_soon_threadsafe(old_loop.stop)
                    log_info(f"[conn:{conn_id}] ⏹️ 旧事件循环已停止")
                    ws_logger.log_full_reset_detail(conn_id, "stop_loop", "事件循环已停止")
                except Exception:
                    pass

            # 6. 等待旧线程结束（注意：不能 join 当前线程，会死锁！）
            current_thread = threading.current_thread()
            if self._cleanup_thread and self._cleanup_thread.is_alive() and self._cleanup_thread != current_thread:
                self._cleanup_thread.join(timeout=1.0)
            if self._health_check_thread and self._health_check_thread.is_alive() and self._health_check_thread != current_thread:
                self._health_check_thread.join(timeout=1.0)
            # WebSocket 线程通常就是当前线程，不要 join 自己
            if self.ws_thread and self.ws_thread.is_alive() and self.ws_thread != current_thread:
                self.ws_thread.join(timeout=1.0)
            ws_logger.log_full_reset_detail(conn_id, "join_threads", "等待旧线程结束完成")

            # 7. 清空所有引用
            with self.lock:
                self.ws = None
                self._loop = None
                self.ws_thread = None
                self._cleanup_thread = None
                self._health_check_thread = None
            ws_logger.log_full_reset_detail(conn_id, "clear_refs", "清空所有引用")

            # 8. 重置重连状态
            self._reconnect_attempt_count = 0
            self._current_reconnect_interval = self.config.reconnect_base_interval
            self._last_pong_time = 0
            ws_logger.log_full_reset_detail(conn_id, "reset_reconnect", "重置重连状态")

            # 9. 记录重置日志
            ws_logger.log_full_reset(
                conn_id=conn_id,
                queue_cleared=cleared_count,
                streams_cleared=stream_count
            )

            log_info(f"[conn:{conn_id}] ✅ 完全重置完成，系统状态已清理，准备重新连接")
            ws_logger.log_full_reset_detail(conn_id, "complete", "完全重置流程完成")

        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            log_error(f"[conn:{conn_id}] ❌ 完全重置失败: {e}\n{error_detail}")
            ws_logger.log_full_reset_detail(conn_id, "error", f"重置失败: {str(e)}")

    def _partial_reset_for_reconnect(self, conn_id: int) -> None:
        """✅ 部分重置，用于异常断开后准备重连

        与 _full_reset 不同，此方法：
        1. 不尝试停止当前线程的事件循环（避免死锁）
        2. 不 join 当前线程（避免死锁）
        3. 只清理必要的状态，让重连线程创建新的连接

        这个方法在 WebSocket 处理线程中调用是安全的。
        """
        ws_logger = get_ws_logger()
        log_info(f"[conn:{conn_id}] 🔄 开始部分重置（为重连准备）...")

        try:
            # 1. 重置重连计数（让重连从头开始）
            self._reconnect_attempt_count = 0
            self._current_reconnect_interval = self.config.reconnect_base_interval

            # 2. 清空 stream_queue_map（已经在 _notify_pending_stream_requests 中通知过了）
            with self._stream_queue_lock:
                stream_count = len(self.stream_queue_map)
                self.stream_queue_map.clear()
            if stream_count > 0:
                log_info(f"[conn:{conn_id}] 🧹 清空流请求映射: {stream_count} 个请求已清理")

            # 3. 清空消息队列中的消息（可选，重连后会重新发送）
            # 注意：这里不清空队列，让队列中的消息在重连后自动发送
            queue_size = self.queue.qsize()
            if queue_size > 0:
                log_info(f"[conn:{conn_id}] 📦 消息队列有 {queue_size} 条待发送消息，重连后自动发送")

            # 4. 停止辅助线程标志（让它们自己退出）
            self._cleanup_running = False
            self._health_check_running = False

            # 5. 标记连接状态（关键：让 start_websocket_client 知道需要创建新连接）
            with self.lock:
                self._connection_state = ConnectionState.DISCONNECTED
                self._connecting_since = 0.0
                self._connecting_conn_id = 0
                self.connected_event.clear()
                self._is_retrying = False  # 重置重试标志，允许新的重连
                # 注意：不清空 ws 和 _loop，让它们自然被替换

            log_info(f"[conn:{conn_id}] ✅ 部分重置完成，准备重连")
            ws_logger.log_full_reset_detail(conn_id, "partial_reset_complete", "部分重置完成，准备重连")

        except Exception as e:
            log_error(f"[conn:{conn_id}] ❌ 部分重置异常: {e}")

    def _notify_pending_stream_requests(self, reason: str) -> None:
        """✅ 通知所有等待中的 stream 请求连接已断开

        当 WebSocket 连接断开时，立即通知所有等待响应的 create_stream 请求，
        避免它们继续等待到 15 秒超时。这样调用方可以更快地重试。
        """
        # ✅ 使用锁保护，复制后立即释放锁
        with self._stream_queue_lock:
            if not self.stream_queue_map:
                return
            pending_items = list(self.stream_queue_map.items())
            pending_count = len(pending_items)
            self.stream_queue_map.clear()  # 在锁内清空

        if pending_count == 0:
            return

        log_warning(f"🔔 通知 {pending_count} 个等待中的流请求: {reason}")

        # ✅ 释放锁后再处理通知（避免长时间持锁）
        notified_count = 0
        failed_count = 0
        for request_id, queue_entry in pending_items:
            try:
                temp_queue = queue_entry.get("queue")
                loop = queue_entry.get("loop")
                receiver = queue_entry.get("receiver", "unknown")

                if temp_queue and loop:
                    error_data = {
                        "error": "connection_lost",
                        "message": f"WebSocket 连接断开: {reason}，请重试"
                    }
                    try:
                        # 检查事件循环是否仍在运行
                        if loop.is_running():
                            # 使用线程安全的方式放入错误通知
                            loop.call_soon_threadsafe(temp_queue.put_nowait, error_data)
                            notified_count += 1
                            log_debug(f"📢 已通知: request_id={request_id[:8]}... receiver={receiver}")
                        else:
                            failed_count += 1
                            log_debug(f"事件循环已停止，跳过: request_id={request_id[:8]}...")
                    except RuntimeError as e:
                        failed_count += 1
                        log_debug(f"事件循环已关闭: {e}")
                    except Exception as e:
                        failed_count += 1
                        log_debug(f"通知失败: {e}")

            except Exception as e:
                log_error(f"❌ 通知等待请求时异常: {e}")

        # 汇总日志
        log_info(f"🔔 流请求通知完成: 成功={notified_count}, 失败={failed_count}, 总数={pending_count}")

    def _get_close_code_meaning(self, code: int) -> str:
        """获取 WebSocket 关闭代码的含义"""
        close_codes = {
            1000: "正常关闭 (Normal Closure)",
            1001: "端点离开 (Going Away) - 服务器关闭或浏览器导航离开",
            1002: "协议错误 (Protocol Error)",
            1003: "不支持的数据类型 (Unsupported Data)",
            1005: "未收到状态码 (No Status Received)",
            1006: "异常关闭 (Abnormal Closure) - 连接意外断开，未收到关闭帧。常见原因：网络中断、服务器崩溃、防火墙/代理断开、心跳超时",
            1007: "无效的帧数据 (Invalid Frame Payload Data)",
            1008: "策略违规 (Policy Violation)",
            1009: "消息太大 (Message Too Big)",
            1010: "必需的扩展 (Mandatory Extension)",
            1011: "内部服务器错误 (Internal Server Error)",
            1012: "服务重启 (Service Restart)",
            1013: "稍后重试 (Try Again Later)",
            1014: "错误的网关 (Bad Gateway)",
            1015: "TLS握手失败 (TLS Handshake Failure)",
        }
        return close_codes.get(code, f"未知代码 (Unknown Code: {code})")

    # 兼容性方法 - 保持与旧 API 的兼容
    def on_open(self, ws) -> None:
        """Handle WebSocket connection open (for compatibility)."""
        pass

    def on_message(self, ws, message: str) -> None:
        """Handle incoming WebSocket messages (for compatibility)."""
        pass

    def on_error(self, ws, error: Exception) -> None:
        """Handle WebSocket errors (for compatibility)."""
        pass

    def on_close(self, ws, close_status_code: int, close_msg: str) -> None:
        """Handle WebSocket connection close (for compatibility)."""
        pass

    def on_ping(self, ws, message: bytes) -> None:
        """Handle WebSocket ping (for compatibility)."""
        self._last_pong_time = time.time()

    def on_pong(self, ws, message: bytes) -> None:
        """Handle WebSocket pong (for compatibility)."""
        self._last_pong_time = time.time()

    # ✅ 线程安全的 stream_queue_map 访问方法
    def register_stream_request(self, request_id: str, queue_entry: dict) -> None:
        """线程安全地注册流请求"""
        with self._stream_queue_lock:
            self.stream_queue_map[request_id] = queue_entry

    def unregister_stream_request(self, request_id: str) -> Optional[dict]:
        """线程安全地注销流请求，返回被移除的条目"""
        with self._stream_queue_lock:
            return self.stream_queue_map.pop(request_id, None)

    def get_stream_request(self, request_id: str) -> Optional[dict]:
        """线程安全地获取流请求"""
        with self._stream_queue_lock:
            return self.stream_queue_map.get(request_id)

    def get_pending_stream_count(self) -> int:
        """线程安全地获取等待中的流请求数量"""
        with self._stream_queue_lock:
            return len(self.stream_queue_map)

    def full_reset(self) -> None:
        """
        完全重置 MessageClient，清理所有资源

        这个方法比 _full_reset 更彻底，用于外部显式调用
        重置后可以重新调用 start_websocket_client() 建立新连接
        """
        log_info(f"[MessageClient] 开始完全重置: agent_id={self.agent_id}")

        try:
            # 1. 设置关闭标志（阻止重连和新操作）
            self._shutdown_requested = True
            log_debug("[MessageClient] ✓ 已设置关闭标志")

            # 2. 停止辅助线程标志
            self._cleanup_running = False
            self._health_check_running = False
            log_debug("[MessageClient] ✓ 已设置线程停止标志")

            # 3. 通知所有等待中的请求
            pending_count = self.get_pending_stream_count()
            if pending_count > 0:
                log_info(f"[MessageClient] 通知 {pending_count} 个等待中的流请求...")
                self._notify_pending_stream_requests("MessageClient 正在完全重置")

            # 4. 停止 WebSocket 连接
            log_debug("[MessageClient] 正在停止 WebSocket...")
            try:
                self.stop_websocket_client()
            except Exception as e:
                log_warning(f"[MessageClient] 停止 WebSocket 失败: {e}")

            # 5. 清空 stream_queue_map
            with self._stream_queue_lock:
                self.stream_queue_map.clear()
            log_debug("[MessageClient] ✓ stream_queue_map 已清空")

            # 6. 清空消息队列
            cleared_count = 0
            while not self.queue.empty():
                try:
                    self.queue.get_nowait()
                    self.queue.task_done()
                    cleared_count += 1
                except queue.Empty:
                    break
            log_debug(f"[MessageClient] ✓ 已清空 {cleared_count} 条待发送消息")

            # 7. 等待辅助线程结束
            if self._cleanup_thread and self._cleanup_thread.is_alive():
                self._cleanup_thread.join(timeout=2.0)
            if self._health_check_thread and self._health_check_thread.is_alive():
                self._health_check_thread.join(timeout=2.0)
            log_debug("[MessageClient] ✓ 辅助线程已停止")

            # 8. 重置连接状态
            with self.lock:
                self._connection_state = ConnectionState.DISCONNECTED
                self._connecting_since = 0.0
                self._connecting_conn_id = 0
                self.connected_event.clear()
                self._is_retrying = False
                self._reconnect_attempt_count = 0
                self._current_reconnect_interval = self.config.reconnect_base_interval
                self._connection_id = 0
                self._last_pong_time = 0

            log_debug("[MessageClient] ✓ 连接状态已重置")

            # 9. 清空引用
            self.ws = None
            self._loop = None
            self.ws_thread = None
            self._cleanup_thread = None
            self._health_check_thread = None
            log_debug("[MessageClient] ✓ 对象引用已清空")

            # 10. 重置关闭标志（允许后续重新启动）
            self._shutdown_requested = False
            log_debug("[MessageClient] ✓ 关闭标志已重置")

            log_info(f"[MessageClient] ✅ 完全重置完成: agent_id={self.agent_id}")

        except Exception as e:
            log_error(f"[MessageClient] ❌ 完全重置失败: {e}")
            import traceback
            traceback.print_exc()
            # 确保关闭标志被重置，允许重试
            self._shutdown_requested = False
