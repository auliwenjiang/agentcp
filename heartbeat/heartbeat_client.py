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
import requests
import datetime
import socket
import threading
import time
from typing import Optional
from agentcp.base.log import log_debug, log_error, log_exception, log_info, log_warning
from agentcp.base.auth_client import AuthClient

from agentcp.msg.message_serialize import *
from ..context import ErrorContext, exceptions


class HeartbeatClient:
    # 重连相关常量
    MAX_SEND_FAILURES = 3           # 发送失败触发重连的阈值
    MAX_RECV_FAILURES = 3           # 接收失败触发重连的阈值
    MAX_MISSED_HEARTBEATS = 3       # 心跳响应超时阈值（错过次数）
    RECONNECT_BACKOFF_MAX = 30      # 重连退避上限（秒）
    SOCKET_TIMEOUT = 1.0            # socket 超时时间（秒）

    def __init__(self, agent_id: str, server_url: str, aid_path: str, seed_password: str):
        self.agent_id = agent_id
        self.server_url = server_url
        self.seed_password = seed_password
        self.port = 0  # server_port
        self.sign_cookie = 0
        self.udp_socket = None
        self.local_ip = "0.0.0.0"
        self.local_port = 0
        self.server_ip = "127.0.0.1"
        self.heartbeat_interval = 5000
        self.is_running = False
        self.is_sending_heartbeat = False
        self.send_thread: Optional[threading.Thread] = None
        self.receive_thread: Optional[threading.Thread] = None
        self.msg_seq = 0
        self.last_hb = 0
        self.message_listener = None
        self.auth_client = AuthClient(agent_id, server_url, aid_path, seed_password)
        self.on_recv_invite = None

        # 新增：用于自动恢复的状态
        self._socket_lock = threading.Lock()        # 保护 socket 操作
        self._reconnect_lock = threading.Lock()     # 防止并发重连
        self._last_reconnect_ts = 0                 # 上次重连时间戳
        self._last_hb_recv = 0                      # 上次收到心跳响应的时间戳
        self._send_failures = 0                     # 连续发送失败次数
        self._recv_failures = 0                     # 连续接收失败次数

    def initialize(self):
        self.sign_in()

    def sign_in(self) -> bool:
        data = self.auth_client.sign_in()
        if data is None:
            log_error("sign_in failed: data is None")
            return False
        self.server_ip = data.get("server_ip")
        self.port = int(data.get("port", 0))
        self.sign_cookie = data.get("sign_cookie")
        log_info(f'signin {self.server_ip} {self.port} {self.sign_cookie}')

        return self.server_ip is not None and self.port != 0 and self.sign_cookie is not None

    def sign_out(self):
        self.auth_client.sign_out()

    def set_on_recv_invite(self, listener):
        """设置消息监听器"""
        self.on_recv_invite = listener

    # ========== 新增：Socket 生命周期管理 ==========

    def _create_socket(self):
        """创建并绑定 UDP socket，设置超时"""
        with self._socket_lock:
            self._close_socket_internal()
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.settimeout(self.SOCKET_TIMEOUT)
            self.udp_socket.bind((self.local_ip, 0))  # 使用新端口
            self.local_ip, self.local_port = self.udp_socket.getsockname()
            log_info(f"UDP socket created and bound to {self.local_ip}:{self.local_port}")

    def _close_socket_internal(self):
        """内部方法：关闭 socket（不加锁，由调用方保证线程安全）"""
        if self.udp_socket is not None:
            try:
                self.udp_socket.close()
            except Exception as e:
                log_warning(f"Close socket error: {e}")
            self.udp_socket = None

    def _close_socket(self):
        """安全关闭 socket"""
        with self._socket_lock:
            self._close_socket_internal()

    def _reconnect(self, reason: str):
        """重连：限流/退避后执行 sign_in() + _create_socket()"""
        if not self.is_running:
            log_debug(f"Reconnect skipped (client offline): {reason}")
            return False
        if not self._reconnect_lock.acquire(blocking=False):
            log_debug(f"Reconnect already in progress, skip: {reason}")
            return False

        try:
            now = time.time()
            # 限流：距离上次重连至少间隔 5 秒
            elapsed = now - self._last_reconnect_ts
            if elapsed < 5:
                backoff = min(5 - elapsed, self.RECONNECT_BACKOFF_MAX)
                log_info(f"Reconnect backoff: waiting {backoff:.1f}s")
                time.sleep(backoff)

            log_info(f"Reconnecting due to: {reason}")
            self._last_reconnect_ts = time.time()

            # 重新登录
            if not self.sign_in():
                log_error("Reconnect failed: sign_in returned False")
                return False

            # 重建 socket
            self._create_socket()

            # 重置失败计数
            self._send_failures = 0
            self._recv_failures = 0
            self._last_hb_recv = int(time.time() * 1000)

            log_info("Reconnect successful")
            return True
        except Exception as e:
            log_error(f"Reconnect exception: {e}")
            return False
        finally:
            self._reconnect_lock.release()

    # ========== 发送心跳（带异常恢复和超时检测） ==========

    def __send_heartbeat(self):
        backoff = 1  # 初始退避时间（秒）

        while self.is_sending_heartbeat and self.is_running:
            try:
                current_time_ms = int(datetime.datetime.now().timestamp() * 1000)

                # 检查心跳响应超时
                if self._last_hb_recv > 0:
                    timeout_threshold = self.MAX_MISSED_HEARTBEATS * self.heartbeat_interval
                    if current_time_ms - self._last_hb_recv > timeout_threshold:
                        log_warning(f"Heartbeat response timeout: {current_time_ms - self._last_hb_recv}ms > {timeout_threshold}ms")
                        self._reconnect("heartbeat_response_timeout")
                        backoff = 1
                        continue

                # 发送心跳
                if current_time_ms > (self.last_hb + self.heartbeat_interval):
                    log_debug(f'send heartbeat message to {self.server_ip}:{self.port}')
                    self.last_hb = current_time_ms
                    self.msg_seq = self.msg_seq + 1
                    req = HeartbeatMessageReq()
                    req.header.MessageMask = 0
                    req.header.MessageSeq = self.msg_seq
                    req.header.MessageType = 513
                    req.header.PayloadSize = 100
                    req.AgentId = self.agent_id
                    req.SignCookie = self.sign_cookie
                    buf = io.BytesIO()
                    req.serialize(buf)
                    data = buf.getvalue()

                    with self._socket_lock:
                        if self.udp_socket is not None:
                            self.udp_socket.sendto(data, (self.server_ip, self.port))
                        else:
                            raise Exception("UDP socket is None")

                    # 发送成功，重置失败计数和退避
                    self._send_failures = 0
                    backoff = 1

                time.sleep(1)

            except Exception as e:
                self._send_failures += 1
                log_error(f"Heartbeat send error (failures={self._send_failures}): {e}")
                ErrorContext.publish(exceptions.SDKError(f"Heartbeat send error: {e}"))

                # 达到阈值，触发重连
                if self._send_failures >= self.MAX_SEND_FAILURES:
                    log_warning(f"Send failures reached threshold ({self.MAX_SEND_FAILURES}), triggering reconnect")
                    self._reconnect("send_failures_threshold")
                    backoff = 1
                else:
                    # 指数退避
                    time.sleep(backoff)
                    backoff = min(backoff * 2, self.RECONNECT_BACKOFF_MAX)

    # ========== 接收消息（可中断、可恢复） ==========

    def _receive_messages(self):
        while self.is_running:
            try:
                # 使用 socket 超时，确保能定期检查 is_running
                with self._socket_lock:
                    if self.udp_socket is None:
                        time.sleep(0.5)
                        continue
                    sock = self.udp_socket

                try:
                    data, addr = sock.recvfrom(1536)
                except socket.timeout:
                    # 超时是正常的，继续循环检查 is_running
                    continue

                # 接收成功，重置失败计数
                self._recv_failures = 0

                udp_header, offset = UdpMessageHeader.deserialize(data, 0)

                if udp_header.MessageType == 258:
                    hb_resp, offset = HeartbeatMessageResp.deserialize(data, 0)
                    self.heartbeat_interval = hb_resp.NextBeat

                    # 更新最后收到心跳响应的时间
                    self._last_hb_recv = int(datetime.datetime.now().timestamp() * 1000)

                    # 服务器端身份验证失败(比如服务器发生了异常重启)，需要重新登录
                    if hb_resp.NextBeat == 401:
                        log_warning(f"Heartbeat failed: {hb_resp.NextBeat}, triggering reconnect")
                        ErrorContext.publish(exceptions.SDKError(f"401,心跳", code=0))
                        self._reconnect("401_auth_failed")
                        continue

                    if self.heartbeat_interval <= 5000:
                        self.heartbeat_interval = 5000

                elif udp_header.MessageType == 259:
                    invite_req, offset = InviteMessageReq.deserialize(data, 0)
                    if self.on_recv_invite is not None:
                        ErrorContext.publish(exceptions.SDKError(f"收到邀请，加入session: {invite_req}", code=0))
                        self.on_recv_invite(invite_req)

                    resp = InviteMessageResp()
                    self.msg_seq = self.msg_seq + 1
                    resp.header.MessageMask = 0
                    resp.header.MessageSeq = self.msg_seq
                    resp.header.MessageType = 516
                    resp.AgentId = self.agent_id
                    resp.InviterAgentId = invite_req.InviterAgentId
                    resp.SignCookie = self.sign_cookie
                    buf = io.BytesIO()
                    resp.serialize(buf)
                    resp_data = buf.getvalue()

                    with self._socket_lock:
                        if self.udp_socket is not None:
                            self.udp_socket.sendto(resp_data, (self.server_ip, self.port))

            except socket.timeout:
                # 超时是正常的，继续循环
                continue
            except Exception as e:
                if not self.is_running:
                    break

                self._recv_failures += 1
                log_error(f"Receive message exception (failures={self._recv_failures}): {e}")
                ErrorContext.publish(exceptions.SDKError(f"Receive message exception: {e}"))

                # 达到阈值，触发重连
                if self._recv_failures >= self.MAX_RECV_FAILURES:
                    log_warning(f"Recv failures reached threshold ({self.MAX_RECV_FAILURES}), triggering reconnect")
                    self._reconnect("recv_failures_threshold")
                else:
                    time.sleep(1.5)

    def online(self):
        """开始心跳"""
        if self.is_running:
            return

        # 使用统一的 socket 创建方法
        self._create_socket()

        # 初始化心跳响应时间
        self._last_hb_recv = int(time.time() * 1000)

        self.is_running = True
        self.is_sending_heartbeat = True

        self.send_thread = threading.Thread(target=self.__send_heartbeat, daemon=True)
        self.receive_thread = threading.Thread(target=self._receive_messages, daemon=True)

        self.send_thread.start()
        self.receive_thread.start()
        log_info("Successfully went online")

    def offline(self):
        """停止心跳"""
        log_info("Going offline...")

        # 1. 先设置标志位，通知线程退出
        self.is_running = False
        self.is_sending_heartbeat = False

        # 2. 关闭 socket（会使阻塞的 recvfrom 抛出异常）
        self._close_socket()

        # 3. 等待线程退出
        if self.send_thread is not None and self.send_thread.is_alive():
            self.send_thread.join(timeout=3)
            if self.send_thread.is_alive():
                log_warning("Send thread did not exit in time")

        if self.receive_thread is not None and self.receive_thread.is_alive():
            self.receive_thread.join(timeout=3)
            if self.receive_thread.is_alive():
                log_warning("Receive thread did not exit in time")

        self.send_thread = None
        self.receive_thread = None
        log_info("Successfully went offline")
    
    def get_online_status(self, aids):
        try:
            ep_url = self.server_url + "/query_online_state"
            data = {
                "agent_id": f"{self.agent_id}",
                "signature": self.auth_client.signature,
                "agents": aids
            }
            response = requests.post(ep_url, json=data, verify=False, proxies={}, timeout=(3, 10))
            if response.status_code == 200:
                log_info(f"get_online_status ok:{response.json()}")
                return response.json()["data"]
            else:
                log_error(f"get_online_status failed:{response.json()}")
                return []
        except Exception as e:
            log_exception(f"get_online_status exception: {e}")
            return []
