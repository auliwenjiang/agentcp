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

import json
import queue
import ssl
import threading
import time
from enum import Enum
from typing import Dict, Optional, Union

import websocket

from agentcp.base.auth_client import AuthClient
from agentcp.base.client import IClient
from agentcp.base.log import log_debug, log_error, log_exception, log_info

from ..context import ErrorContext, exceptions


class ConnectionState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"


class MessageClientConfig:
    """Configuration class for MessageClient"""

    def __init__(self):
        self.max_queue_size: int = 30
        self.connection_timeout: float = 5.0
        self.retry_interval: float = 4.0
        self.max_retry_attempts: int = 3
        self.send_retry_attempts: int = 5
        self.send_retry_delay: float = 0.01
        self.ping_interval: int = 5


class MessageClient(IClient):
    """WebSocket-based message client with automatic reconnection and message queuing."""

    def __init__(
        self,
        agent_id: str,
        server_url: str,
        aid_path: str,
        seed_password: str,
        cache_auth_client: Optional[AuthClient] = None,
        config: Optional[MessageClientConfig] = None,
    ):
        self.agent_id = agent_id
        self.server_url = server_url.rstrip("/")  # Remove trailing slash
        self.config = config or MessageClientConfig()

        # Initialize auth client
        if cache_auth_client is None:
            self.auth_client = AuthClient(agent_id, server_url, aid_path, seed_password)
        else:
            self.auth_client = cache_auth_client

        # Thread synchronization
        self.lock = threading.Lock()
        self.connected_event = threading.Event()

        # WebSocket related
        self.ws: Optional[websocket.WebSocketApp] = None
        self.ws_thread: Optional[threading.Thread] = None
        self.ws_url: Optional[str] = None

        # Message handling
        self.queue = queue.Queue(maxsize=self.config.max_queue_size)
        self.message_handler: Optional[object] = None

        # Connection state
        self._connection_state = ConnectionState.DISCONNECTED
        self._is_retrying = False
        self._shutdown_requested = False

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

    def _build_websocket_url(self) -> str:
        """Build WebSocket URL with proper protocol and parameters."""
        ws_url = self.server_url.replace("https://", "wss://").replace("http://", "ws://")
        return f"{ws_url}/session?agent_id={self.agent_id}&signature={self.auth_client.signature}"

    def start_websocket_client(self) -> bool:
        """Start WebSocket client connection."""
        if self.connection_state == ConnectionState.CONNECTED:
            return True

        if self._shutdown_requested:
            return False

        try:
            with self.lock:
                if self._connection_state in [ConnectionState.CONNECTING, ConnectionState.RECONNECTING]:
                    return self._wait_for_connection()

            self._set_connection_state(ConnectionState.CONNECTING)

            self.ws_url = self._build_websocket_url()
            log_debug(f"Connecting to WebSocket URL: {self.ws_url}")

            # Start WebSocket thread
            self.ws_thread = threading.Thread(target=self._ws_handler, daemon=True)
            self.ws_thread.start()

            return self._wait_for_connection()

        except Exception as e:
            log_exception(f"Failed to start WebSocket client: {e}")
            self._set_connection_state(ConnectionState.DISCONNECTED)
            return False

    def _wait_for_connection(self) -> bool:
        """Wait for connection to be established."""
        return self.connected_event.wait(timeout=self.config.connection_timeout)

    def stop_websocket_client(self) -> None:
        """Stop WebSocket client connection."""
        self._shutdown_requested = True

        with self.lock:
            if self.ws:
                self.ws.close()
                self.ws = None

            if self.ws_thread and self.ws_thread.is_alive():
                self.ws_thread.join(timeout=2.0)
                self.ws_thread = None

        self._set_connection_state(ConnectionState.DISCONNECTED)

    def send_msg(self, msg: Union[str, Dict]) -> bool:
        """Send message through WebSocket with retry logic."""
        if not self._ensure_connection():
            return self._queue_message(msg)

        try:
            message_str = json.dumps(msg) if not isinstance(msg, str) else msg
            self.ws.send(message_str)
            log_info("Message sent successfully")
            return True

        except Exception as e:
            log_exception(f"Failed to send message: {e}")
            trace_id = msg.get("trace_id", "") if isinstance(msg, dict) else ""
            ErrorContext.publish(exceptions.SendMsgError(message=f"Error sending message: {e}", trace_id=trace_id))
            return self._queue_message(msg)

    def _ensure_connection(self) -> bool:
        """Ensure WebSocket connection is established."""
        retry_count = 0

        while retry_count < self.config.send_retry_attempts:
            if self.connection_state == ConnectionState.CONNECTED and self.ws:
                return True

            log_debug("WebSocket not connected, attempting to reconnect...")
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
            # Remove oldest message if queue is full
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
        if self._is_retrying or self._shutdown_requested:
            return

        self._is_retrying = True
        self._set_connection_state(ConnectionState.RECONNECTING)

        try:
            retry_count = 0
            while retry_count < self.config.max_retry_attempts and not self._shutdown_requested:
                log_info(f"Attempting reconnection, attempt {retry_count + 1}")

                if self.start_websocket_client():
                    log_info("Reconnection successful")
                    return

                retry_count += 1
                if retry_count < self.config.max_retry_attempts:
                    time.sleep(self.config.retry_interval)

            log_error(f"Reconnection failed after {self.config.max_retry_attempts} attempts")

        finally:
            self._is_retrying = False
            if self.connection_state != ConnectionState.CONNECTED:
                self._set_connection_state(ConnectionState.DISCONNECTED)

    def _process_queued_messages(self) -> None:
        """Process messages that were queued during disconnection."""
        try:
            while not self.queue.empty():
                try:
                    message = self.queue.get_nowait()
                    self.ws.send(message)
                    self.queue.task_done()
                except queue.Empty:
                    break
                except Exception as e:
                    log_error(f"Failed to send queued message: {e}")
                    break
        except Exception as e:
            log_error(f"Error processing queued messages: {e}")

    # WebSocket event handlers
    def on_error(self, ws: websocket.WebSocketApp, error: Exception) -> None:
        """Handle WebSocket errors."""
        log_error(f"WebSocket error: {error}")
        try:
            if "Connection to remote host was lost" in str(error):
                ErrorContext.publish(exceptions.SDKError(f"WebSocket connection to remote host was lost: {self.ws_url}"))
                threading.Thread(target=self._handle_reconnection, daemon=True).start()
        except Exception as e:
            pass

    def on_close(self, ws: websocket.WebSocketApp, close_status_code: int, close_msg: str) -> None:
        """Handle WebSocket connection close."""
        try:
            log_info(f"WebSocket connection closed: {close_status_code} - {close_msg}")
            self._set_connection_state(ConnectionState.DISCONNECTED)
        except Exception as e:
            log_exception(f"Error in message handler on_close: {str(e)}")

    def on_open(self, ws: websocket.WebSocketApp) -> None:
        """Handle WebSocket connection open."""
        log_info("WebSocket connection established")
        try:
            self._set_connection_state(ConnectionState.CONNECTED)
            self._is_retrying = False

            # Call custom message handler if available
            if self.message_handler and hasattr(self.message_handler, "on_open"):
                try:
                    self.message_handler.on_open(ws)
                except Exception as e:
                    log_exception(f"Error in message handler on_open1: {str(e)}")
            # Process queued messages
            self._process_queued_messages()
        except Exception as e:
            log_exception(f"Error in message handler on_open2: {str(e)}")

    def on_ping(self, ws: websocket.WebSocketApp, message: bytes) -> None:
        """Handle WebSocket ping."""
        log_debug(f"WebSocket received ping: {message}")
        self._set_connection_state(ConnectionState.CONNECTED)

    def on_pong(self, ws: websocket.WebSocketApp, message: bytes) -> None:
        """Handle WebSocket pong."""
        log_debug(f"WebSocket received pong: {message}")
        self._set_connection_state(ConnectionState.CONNECTED)

    def on_message(self, ws: websocket.WebSocketApp, message: str) -> None:
        """Handle incoming WebSocket messages."""
        try:
            log_info(f"WebSocket received message: {message}")
            self._set_connection_state(ConnectionState.CONNECTED)

            if self.message_handler and hasattr(self.message_handler, "on_message"):
                self.message_handler.on_message(ws, message)
            else:
                log_error("Message handler does not have an on_message method")

        except Exception as e:
            log_exception(f"Error processing message: {e}")
            trace_id = ""
            try:
                if isinstance(message, str):
                    msg_dict = json.loads(message)
                    trace_id = msg_dict.get("trace_id", "")
            except (json.JSONDecodeError, AttributeError):
                pass

            ErrorContext.publish(exceptions.SDKError(message=f"Error processing message: {e}", trace_id=trace_id))

    def _ws_handler(self) -> None:
        """WebSocket handler thread function."""
        try:
            self.ws = websocket.WebSocketApp(
                self.ws_url,
                on_open=self.on_open,
                on_message=self.on_message,
                on_error=self.on_error,
                on_close=self.on_close,
                on_ping=self.on_ping,
                on_pong=self.on_pong,
            )

            # Start WebSocket connection
            self.ws.run_forever(
                ping_interval=self.config.ping_interval,
                sslopt={
                    "cert_reqs": ssl.CERT_NONE,
                    "check_hostname": False,
                },
            )

        except Exception as e:
            log_exception(f"WebSocket handler error: {e}")
        finally:
            self._set_connection_state(ConnectionState.DISCONNECTED)
