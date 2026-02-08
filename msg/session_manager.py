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
import asyncio
import json
import queue
import threading
import time
import uuid
from threading import Lock
from typing import Optional

from agentcp.base.log import log_debug, log_error, log_exception, log_info, log_warning
from agentcp.db.db_mananger import DBManager
from agentcp.message import AgentInstructionBlock
from agentcp.msg.message_client import MessageClient
from agentcp.msg.message_serialize import InviteMessageReq
from agentcp.msg.stream_client import StreamClient
from agentcp.msg.wss_binary_message import *

from ..context import ErrorContext, exceptions


class Session:
    def __init__(self, agent_id: str, message_client: MessageClient):
        """心跳客户端类
        Args:
            agent_id: 代理ID
            server_url: 服务器URL
        """
        self.agent_id = agent_id
        self.identifying_code = ""
        self.on_message_receive = None
        self.on_invite_ack = None
        self.on_session_message_ack = None
        self.on_system_message = None
        self.on_member_list_receive = None
        self.message_client: MessageClient = message_client
        self.stream_client_map = {}
        # self.StreamClient = None
        self.queue = queue.Queue()
        self.invite_message = None
        self.text_stream_pulling = False
        self.text_stream_pull_url = ""
        self.session_id = None
        self.text_stream_recv_thread: Optional[threading.Thread] = None
        # ✅ 移除锁：create_stream 使用 UUID 保证请求唯一性，无需串行化

    def can_invite_member(self):
        return not not self.identifying_code

    def set_session_id(self, session_id: str):
        self.session_id = session_id

    def close_session(self):
        try:
            if self.identifying_code is not None:
                self.__send_leave_session()
                return
            self.__send_close_session()
        except Exception as e:
            log_exception(f"send close chat session message exception: {e}")  # 记录异常
            ErrorContext.publish(exceptions.SDKError(f"close_session: {e}"))
        # try:
        #     self.message_client.stop_websocket_client()
        # except Exception as e:
        #     log_exception(f'stop websocket client exception: {e}')  # 记录异常
        self.message_client = None

    def __send_leave_session(self):
        try:
            data = {
                "cmd": "leave_session_req",
                "data": {"session_id": f"{self.session_id}", "request_id": f"{int(time.time() * 1000)}"},
            }
            msg = json.dumps(data)
            self.message_client.send_msg(msg)
            log_debug(f"send close chat session message: {msg}")  # 调试日志
        except Exception as e:
            log_exception(f"send close chat session message exception: {e}")  # 记录异常

    def __send_close_session(self):
        try:
            data = {
                "cmd": "close_session_req",
                "data": {
                    "session_id": f"{self.session_id}",
                    "request_id": f"{int(time.time() * 1000)}",
                    "identifying_code": self.identifying_code,
                },
            }
            msg = json.dumps(data)
            self.message_client.send_msg(msg)
            log_debug(f"send close chat session message: {msg}")  # 调试日志
        except Exception as e:
            log_exception(f"send close chat session message exception: {e}")  # 记录异常

    # accept invite request
    def accept_invite(self, invite_req: InviteMessageReq):
        try:
            data = {
                "cmd": "join_session_req",
                "data": {
                    "session_id": invite_req.SessionId,
                    "request_id": f"{int(time.time() * 1000)}",
                    "inviter_agent_id": invite_req.InviterAgentId,
                    "invite_code": invite_req.InviteCode,
                    "last_msg_id": "0",
                },
            }
            msg = json.dumps(data)
            self.message_client.send_msg(msg)
            log_debug(f"send join chat session message: {msg}")  # 调试日志
        except Exception as e:
            log_exception(f"send join chat session message exception: {e}")  # 记录异常
            ErrorContext.publish(exceptions.JoinSessionError(f"accept_invite: {e}"))

    def reject_invite(self, invite_req: InviteMessageReq):
        pass

    def leave_session(self, session_id: str):
        pass

    def invite_member(self, acceptor_aid: str):
        try:
            data = {
                "cmd": "invite_agent_req",
                "data": {
                    "session_id": self.session_id,
                    "request_id": f"{uuid.uuid4().hex}",
                    "inviter_id": self.agent_id,
                    "acceptor_id": acceptor_aid,
                    "invite_code": self.identifying_code,
                },
            }
            msg = json.dumps(data)
            ret = self.message_client.send_msg(msg)
            log_debug(f"send invite message: {msg} , ret:{ret}")  # 调试日志
            return ret
        except Exception as e:
            ErrorContext.publish(exceptions.SDKError(f"invite_member: {e}"))
            log_exception(f"send invite message exception: {e}")  # 记录异常
            return False

    def eject_member(self, eject_aid: str):
        try:
            data = {
                "cmd": "eject_agent_req",
                "data": {
                    "session_id": f"{self.session_id}",
                    "request_id": f"{int(time.time() * 1000)}",
                    "eject_agent_id": self.agent_id,
                    "identifying_code": self.identifying_code,
                },
            }
            msg = json.dumps(data)
            self.message_client.send_msg(msg)
            log_debug(f"send eject message: {msg}")  # 调试日志
            return True
        except Exception as e:
            ErrorContext.publish(exceptions.SDKError(f"eject_member: {e}"))
            log_exception(f"send eject message exception: {e}")
            return False

    def get_member_list(self):
        try:
            data = {
                "cmd": "get_member_list",
                "data": {
                    "session_id": f"{self.session_id}",
                    "request_id": f"{int(time.time() * 1000)}",
                },
            }
            msg = json.dumps(data)
            self.message_client.send_msg(msg)
            log_debug(f"send get member list message: {msg}")  # 调试日志
            return True
        except Exception as e:
            log_exception(f"send get member list message exception: {e}")
            return False

    def send_msg(
        self,
        msg: list,
        receiver: str,
        ref_msg_id: str = "",
        message_id: str = "",
        agent_cmd_block: AgentInstructionBlock = None,
    ):
        if len(msg) == 0:
            log_error("msg is empty")
            return
        import urllib.parse

        # ✅ 修复: 序列化 AgentInstructionBlock 对象
        instruction_data = None
        if agent_cmd_block is not None:
            from dataclasses import asdict
            instruction_data = asdict(agent_cmd_block)

        send_msg = urllib.parse.quote(json.dumps(msg))
        data = {
            "cmd": "session_message",
            "data": {
                "message_id": message_id,
                "session_id": self.session_id,
                "ref_msg_id": ref_msg_id,
                "sender": f"{self.agent_id}",
                "instruction": instruction_data,  # ✅ 使用序列化后的字典
                "receiver": receiver,
                "message": send_msg,
                "timestamp": f"{int(time.time() * 1000)}",
            },
        }
        msg = json.dumps(data)
        log_debug(f"send message: {msg}")
        return self.message_client.send_msg(msg)

    def on_open(self):
        """WebSocket连接建立时的处理函数"""
        try:
            #log_info("WebSocket connection opened.")
            # 成员断线加入
            if self.invite_message is not None:
                self.accept_invite(self.invite_message)
            # owner重新加入
            if self.identifying_code:
                self.owner_rejoin()
        except Exception as e:
            import traceback
            log_error(f"WebSocket连接建立时的处理函数: {e}\n{traceback.format_exc()}")

    def owner_rejoin(self):
        try:
            data = {
                "cmd": "join_session_req",
                "data": {
                    "session_id": self.session_id,
                    "request_id": f"{int(time.time() * 1000)}",
                    "inviter_agent_id": "",
                    "invite_code": self.identifying_code,
                    "last_msg_id": "0",
                },
            }
            msg = json.dumps(data)
            self.message_client.send_msg(msg)
            log_debug(f"send owner rejoin message: {msg}")  # 调试日志
        except Exception as e:
            ErrorContext.publish(exceptions.JoinSessionError(f"加入会话失败: {self.session_id}"))
            log_exception(f"send owner rejoin message exception: {e}")

    async def create_stream(self, to_aid_list: [], content_type: str = "text/event-stream", ref_msg_id: str = ""):
        """创建流式通道 - 带连接恢复自动重试

        当检测到连接断开时，会等待连接恢复后自动重试，对调用方透明。

        重试策略:
        - 最大重试次数: 2次（总共尝试3次）
        - 等待连接恢复超时: 10秒
        - 单次请求超时: 10秒
        - 最坏情况总超时: 约60秒
        """
        max_retries = 2  # 最多重试2次
        retry_wait_timeout = 10.0  # 等待连接恢复的超时时间

        for retry_count in range(max_retries + 1):
            try:
                result = await self._create_stream_once(to_aid_list, content_type, ref_msg_id)
                push_url, error_or_pull = result

                # 成功
                if push_url is not None:
                    return result

                # 检查是否是连接断开导致的失败
                if not self._is_connection_lost_error(error_or_pull):
                    # 非连接问题（如服务器拒绝、参数错误等），直接返回失败
                    return result

                # 连接断开，尝试等待恢复后重试
                if retry_count < max_retries:
                    log_warning(f"🔄 连接断开，等待恢复后重试 ({retry_count + 1}/{max_retries})...")

                    # 等待连接恢复
                    reconnected = await self._wait_for_reconnection(retry_wait_timeout)
                    if reconnected:
                        log_info(f"✅ 连接已恢复，重新发送 create_stream 请求...")
                        continue  # 重试
                    else:
                        log_error(f"❌ 等待连接恢复超时 ({retry_wait_timeout}s)")
                        # 继续尝试，可能在重试过程中恢复
                        continue
                else:
                    # 达到最大重试次数
                    return result

            except Exception as e:
                import traceback
                log_error(f"❌ create_stream 重试循环异常: {e}\n{traceback.format_exc()}")
                if retry_count >= max_retries:
                    return None, f"创建流异常: {str(e)}"

        return None, "重试次数已用完"

    def _is_connection_lost_error(self, error_msg: str) -> bool:
        """判断是否是连接断开导致的错误"""
        if error_msg is None:
            return False
        error_lower = str(error_msg).lower()
        connection_keywords = [
            "connection_lost",
            "连接断开",
            "websocket 连接不可用",
            "连接不可用",
            "发送创建流请求失败",
            "发送请求失败"
        ]
        return any(keyword in error_lower for keyword in connection_keywords)

    async def _wait_for_reconnection(self, timeout: float) -> bool:
        """等待 WebSocket 连接恢复

        Args:
            timeout: 最大等待时间（秒）

        Returns:
            True: 连接已恢复并验证通过
            False: 等待超时或连接不可用
        """
        if self.message_client is None:
            return False

        start_time = time.time()
        check_interval = 0.3  # 每 0.3 秒检查一次（更频繁）

        log_info(f"⏳ 等待连接恢复，超时时间: {timeout}s...")

        while time.time() - start_time < timeout:
            # 检查连接是否已恢复（多重条件）
            ws_open = self.message_client._is_ws_open()
            event_set = self.message_client.connected_event.is_set()

            # 需要两个条件都满足才认为连接真正恢复
            if ws_open and event_set:
                # 额外等待 0.2 秒让连接稳定
                await asyncio.sleep(0.2)
                # 再次验证
                if self.message_client._is_ws_open():
                    elapsed = time.time() - start_time
                    log_info(f"✅ 连接已恢复，耗时: {elapsed:.1f}s")
                    return True

            await asyncio.sleep(check_interval)

        # 超时，最后检查一次
        elapsed = time.time() - start_time
        ws_open = self.message_client._is_ws_open()
        log_warning(f"⏱️ 等待连接恢复超时: {elapsed:.1f}s, ws_open={ws_open}")
        return ws_open

    async def _create_stream_once(self, to_aid_list: [], content_type: str, ref_msg_id: str):
        """单次创建流（不含重试逻辑）

        Returns:
            (push_url, pull_url): 成功时返回两个 URL
            (None, error_msg): 失败时返回 None 和错误信息
        """
        try:
            start_time = time.time()
            receiver = ",".join(to_aid_list)
            request_id = f"{uuid.uuid4().hex}"

            # 检查 message_client
            if self.message_client is None:
                error_msg = "message_client 未初始化"
                log_error(f"❌ 创建流失败: {error_msg}")
                ErrorContext.publish(exceptions.CreateStreamError(error_msg))
                return None, error_msg

            # ✅ 增强：检查连接状态，同时检查 connected_event
            ws_open = self.message_client._is_ws_open()
            event_set = self.message_client.connected_event.is_set()

            if not ws_open or not event_set:
                error_msg = f"WebSocket 连接不可用 (ws_open={ws_open}, event_set={event_set})"
                log_warning(f"⚠️ 创建流: {error_msg}")
                return None, error_msg

            # 构建请求消息
            data = {
                "cmd": "session_create_stream_req",
                "data": {
                    "session_id": self.session_id,
                    "request_id": f"{request_id}",
                    "ref_msg_id": ref_msg_id,
                    "sender": f"{self.agent_id}",
                    "receiver": receiver,
                    "content_type": content_type,
                    "timestamp": f"{int(time.time() * 1000)}",
                },
            }
            msg = json.dumps(data)

            # 注册响应队列（使用线程安全方法）
            temp_queue = asyncio.Queue()
            try:
                loop = asyncio.get_running_loop()  # Python 3.10+ 推荐用法
            except RuntimeError:
                loop = asyncio.get_event_loop()  # 兼容旧版本
            self.message_client.register_stream_request(request_id, {
                "queue": temp_queue,
                "loop": loop,
                "timestamp": start_time,
                "receiver": receiver
            })

            # 发送请求
            send_success = self.message_client.send_msg(msg)
            if not send_success:
                self.message_client.unregister_stream_request(request_id)
                error_msg = "发送创建流请求失败"
                log_warning(f"⚠️ {error_msg}")
                return None, error_msg

            log_info(f"📤 发送创建流请求: request_id={request_id[:8]}... receiver={receiver}")

            # 等待服务器响应（单次超时10秒）
            try:
                ack = await asyncio.wait_for(temp_queue.get(), timeout=10.0)
                elapsed = time.time() - start_time
                log_info(f"✅ 收到流创建响应: request_id={request_id[:8]}... 耗时={elapsed:.2f}s")
            except asyncio.TimeoutError:
                elapsed = time.time() - start_time
                pending_count = self.message_client.get_pending_stream_count()
                log_error(f"⏱️ 创建流超时: request_id={request_id[:8]}... receiver={receiver} 耗时={elapsed:.2f}s")
                log_error(f"📊 当前等待响应的请求数: {pending_count}")
                ErrorContext.publish(exceptions.CreateStreamError(f"创建流超时(10秒): receiver={receiver}"))
                return None, f"创建流超时: 10秒内未收到服务器响应"
            finally:
                self.message_client.unregister_stream_request(request_id)

            # 检查错误标记（连接断开通知或清理线程放入的）
            if "error" in ack:
                error_type = ack.get("error", "unknown")
                error_msg = ack.get("message", "流创建失败")
                log_warning(f"⚠️ 收到错误标记 ({error_type}): {error_msg}")
                # 不发布 ErrorContext，让外层决定是否重试
                return None, error_msg

            # 验证响应完整性
            if "session_id" in ack and "push_url" in ack and "pull_url" in ack and "message_id" in ack:
                push_url = ack["push_url"]
                pull_url = ack["pull_url"]

                # 创建流客户端连接
                try:
                    success = await self.__create_stream_client(self.session_id, push_url)
                    if not success:
                        await asyncio.sleep(1)
                        success = await self.__create_stream_client(self.session_id, push_url)
                        if not success:
                            ErrorContext.publish(exceptions.CreateStreamError(f"创建流失败: {push_url}"))
                            log_error(f"❌ 创建流客户端失败: {push_url}")
                            return None, f"创建流客户端连接失败"
                except Exception as e:
                    log_error(f"❌ 创建流客户端异常: {str(e)}")
                    ErrorContext.publish(exceptions.CreateStreamError(f"创建流失败: {push_url}"))
                    return None, f"创建流客户端异常: {str(e)}"

                return push_url, pull_url
            else:
                log_error(f"❌ 服务器响应不完整: {ack}")
                ErrorContext.publish(exceptions.CreateStreamError("未获取到流连接"))
                return None, "服务器响应不完整"

        except Exception as e:
            import traceback
            error_msg = traceback.format_exc()
            log_error(f"❌ 单次创建流异常: {error_msg}")
            ErrorContext.publish(exceptions.CreateStreamError(f"创建流异常: {str(e)}"))
            return None, f"创建流异常: {str(e)}"

    async def __create_stream_client(self, session_id, push_url):
        stream_client = StreamClient(self.agent_id, session_id, push_url, self.message_client.auth_client.signature)
        ws_url = push_url
        ws_url = ws_url + f"&agent_id={self.agent_id}&signature={self.message_client.auth_client.signature}"
        log_info(f"ws_ts_url = {ws_url}")
        stream_client.ws_url = ws_url
        stream_client.ws_is_running = True
        success = await stream_client.start_websocket_client()
        if not success:
            log_error(f"创建流失败, 启动websocket失败: {stream_client.ws_url}")
            ErrorContext.publish(exceptions.CreateStreamError(f"创建流失败: {stream_client.ws_url}"))
            return None
        self.stream_client_map[push_url] = stream_client
        return stream_client

    def send_chunk_to_stream(self, stream_url: str, chunk,type="text/event-stream"):
        stream_client: StreamClient = self.stream_client_map.get(stream_url)
        if not stream_client:
            error_msg = f"send_chunk_to_stream, stream_client is none for url: {stream_url}"
            ErrorContext.publish(
                exceptions.SendChunkToStreamError(error_msg)
            )
            return False, error_msg
        return stream_client.send_chunk_to_stream(chunk)

    def send_file_chunk_to_stream(self, stream_url: str, offset: int, chunk: bytes):
        stream_client: StreamClient = self.stream_client_map.get(stream_url)
        if not stream_client:
            error_msg = f"send_file_chunk_to_stream, stream_client is none for url: {stream_url}"
            ErrorContext.publish(
                exceptions.SendChunkToStreamError(error_msg)
            )
            return False, error_msg
        return stream_client.send_chunk_to_file_stream(offset,chunk)

    def close_stream(self, stream_url: str):
        stream_client: StreamClient = self.stream_client_map.get(stream_url)
        if stream_client is not None:
            stream_client.close_stream(stream_url)
            stream_client = None
            self.stream_client_map.pop(stream_url)
            log_info(f"关闭流: {stream_url}")


class SessionManager:
    def __init__(self, agent_id: str, server_url: str, aid_path: str, seed_password: str, db_mananger: DBManager, agent_id_ref=None):
        # ✅ 优化: 使用细粒度锁,避免全局阻塞
        self.sessions_lock = threading.RLock()  # 保护 sessions 字典的读写
        self.sessions = {}
        self.agent_id = agent_id
        self.server_url = server_url
        self.aid_path = aid_path
        self.seed_password = seed_password
        self._agent_id_ref = agent_id_ref
        # 连接多个消息服务器
        self.message_client_map = {}
        # 多条流式消息
        self.message_server_map = {}
        self.db_mananger = db_mananger
        self.queue = queue.Queue()
        self.create_session_queue_map = {}
        self.create_session_event = threading.Event()
        self._create_session_lock = Lock()

    def _get_session_safely(self, session_id: str) -> Optional[Session]:
        """✅ 线程安全地获取session（不持锁返回）

        Args:
            session_id: 会话ID

        Returns:
            Session对象或None
        """
        with self.sessions_lock:
            return self.sessions.get(session_id)

    def _add_session_safely(self, session_id: str, session: Session) -> None:
        """✅ 线程安全地添加session"""
        with self.sessions_lock:
            self.sessions[session_id] = session

    def _remove_session_safely(self, session_id: str) -> Optional[Session]:
        """✅ 线程安全地移除session"""
        with self.sessions_lock:
            return self.sessions.pop(session_id, None)

    def create_session_id(
        self, name: str, message_client: MessageClient, subject: str, *, session_type: str = "public"
    ) -> str:
        with self._create_session_lock:
            log_info(f"sign in success: {self.agent_id}")
            message_client.set_message_handler(self)
            if not message_client.start_websocket_client():
                log_error("Failed to start WebSocket client.")
                ErrorContext.publish(exceptions.CreateSessionError("message_client start_websocket_client is none"))
                return None, None

            request_id, temp_queue = self.__create(message_client, name, subject, session_type)
            if not request_id or temp_queue is None:
                ErrorContext.publish(exceptions.CreateSessionError("create_session_req send failed"))
                return None, None
            try:
                session_result = temp_queue.get(timeout=10)
                temp_queue.task_done()
                temp_queue = None
            except Exception as e:
                self.create_session_queue_map.pop(request_id, None)
                import traceback
                ErrorContext.publish(exceptions.CreateSessionError(f"创建会话等待结果超时: {traceback.format_exc()}"))
                log_error("队列获取超时，当前队列内容:{list(self.queue.queue)}")
                return None, None
            return session_result["session_id"], session_result["identifying_code"]

    def on_open(self, ws):
        """✅ 优化: WebSocket连接建立时的处理函数，修复遍历sessions的竞态条件"""
        #log_info("WebSocket connection opened.")
        try:
            # ✅ 修复: 在锁内快速复制sessions列表，避免遍历时被修改
            with self.sessions_lock:
                sessions_to_reopen = list(self.sessions.values())

            # ✅ 释放锁后再调用每个session的on_open（避免持锁时间过长）
            for session in sessions_to_reopen:
                try:
                    session.on_open()
                except Exception as e:
                    log_error(f"session.on_open() failed: {e}")
        except Exception as e:
            import traceback
            log_error(f"WebSocket连接建立时的处理函数: {e}\n{traceback.format_exc()}")

    def get_content_array_from_message(self, message):
        # 消息数组
        message_content = message.get("message", "")
        message_array = []
        if isinstance(message_content, str):
            try:
                if message_content.strip():  # 检查内容是否非空
                    llm_content_json_array = json.loads(message_content)
                    if isinstance(llm_content_json_array, list) and len(llm_content_json_array) > 0:
                        return llm_content_json_array  # 返回整个数组而不是第一个元素的 conten
                    else:
                        message_array.append(llm_content_json_array)
                        return message_array
                else:
                    log_info("收到空消息内容")
                    return []
            except json.JSONDecodeError:
                log_error(f"无法解析的消息内容: {message_content}")
                return []
        elif isinstance(message_content, list) and len(message_content) > 0:
            return message_content
        else:
            log_error("无效的消息格式")
            return []

    def on_message(self, ws, message:str):
        """✅ P0-1修复: 移除线程创建，改为直接同步调用

        接收到服务器消息时的处理函数

        修改要点：
        1. 移除所有 threading.Thread 创建
        2. 改为直接同步调用回调函数
        3. 回调函数内部会将任务提交到 Scheduler，因此这里同步调用是安全的
        4. 异常处理确保单个消息失败不影响后续消息接收
        """
        try:
            #log_info(f"received a message session mananger: {len(message)}")

            js = json.loads(message)
            if "cmd" not in js or "data" not in js:
                log_error("收到的消息中不包括cmd字段，不符合预期格式")
                return

            cmd = js["cmd"]
            message_data = js["data"]
            #log_info(f"received a message session mananger: {cmd}")

            # ✅ P0-1修复: 所有消息处理改为直接同步调用
            if cmd == "create_session_ack":
                # 创建session的ack（同步处理）
                self.__on_create_session_ack(js["data"])

            elif cmd == "session_message":
                # ✅ 修复: 移除线程创建，直接同步调用
                import urllib.parse
                message_content = js["data"]["message"]
                js["data"]["message"] = urllib.parse.unquote(message_content)

                if self.on_message_receive is not None:
                    try:
                        # ✅ 直接同步调用（内部会提交到 Scheduler）
                        self.on_message_receive(js["data"])
                    except Exception as e:
                        log_error(f"消息处理回调异常: {e}")
                        import traceback
                        log_error(traceback.format_exc())
                else:
                    log_error("on_message_receive is None")

            elif cmd == "invite_agent_ack":
                log_info(f"收到邀请消息: {js}")
                if self.on_invite_ack is not None:
                    try:
                        # ✅ 修复: 移除线程创建，直接同步调用
                        self.on_invite_ack(js["data"])
                    except Exception as e:
                        log_error(f"邀请回调异常: {e}")
                else:
                    log_error("on_invite_ack is None")

            elif cmd == "session_message_ack":
                session_id = message_data.get("session_id", "")
                session = self._get_session_safely(session_id)
                if session is not None and self.on_session_message_ack is not None:
                    try:
                        # ✅ 修复: 移除线程创建，直接同步调用
                        self.on_session_message_ack(js["data"])
                    except Exception as e:
                        log_error(f"消息确认回调异常: {e}")

            elif cmd == "session_create_stream_ack":
                session_id = message_data.get("session_id", "")
                session = self._get_session_safely(session_id)
                if session is not None and session.message_client is not None:
                    request_id = js["data"]["request_id"]
                    # ✅ 使用线程安全方法获取队列条目
                    queue_entry = session.message_client.get_stream_request(request_id)
                    if queue_entry:
                        # ✅ 从字典中获取队列对象和事件循环
                        temp_queue = queue_entry["queue"]
                        loop = queue_entry["loop"]

                        # ✅ 使用 call_soon_threadsafe 确保线程安全
                        # 从 WebSocket 线程安全地向 asyncio.Queue 放入数据
                        loop.call_soon_threadsafe(temp_queue.put_nowait, js["data"])

            elif cmd == "system_message":
                session_id = message_data.get("session_id", "")
                session = self._get_session_safely(session_id)
                if session is not None and self.on_system_message is not None:
                    try:
                        # ✅ 修复: 移除线程创建，直接同步调用
                        self.on_system_message(js["data"])
                    except Exception as e:
                        log_error(f"系统消息回调异常: {e}")

        except Exception as e:
            import traceback
            log_error(f"处理消息时发生异常: {e}\n{traceback.format_exc()}")

    def __create(self, message_client: MessageClient, session_name: str, subject: str, session_type: str = "public"):
        log_info(f"create_session: {session_name}, {subject}, {session_type}")
        try:
            log_debug("check WebSocket connection status")  # 调试日志
            request_id = f"{uuid.uuid4().hex}"
            data = {
                "cmd": "create_session_req",
                "data": {
                    "request_id": f"{request_id}",
                    "type": f"{session_type}",
                    "group_name": f"{session_name}",
                    "subject": f"{subject}",
                    "timestamp": f"{int(time.time() * 1000)}",
                },
            }
            temp_queue = queue.Queue()
            self.create_session_queue_map[request_id] = temp_queue
            msg = json.dumps(data)
            message_client.send_msg(msg)
            log_debug(f"send message: {msg}")  # 调试日志
            return request_id, temp_queue
        except Exception as e:
            import traceback
            ErrorContext.publish(exceptions.CreateSessionError(f"创建会话等待结果超时: {traceback.format_exc()}"))
            log_exception(f"send create chat session message exception: {e}")  # 记录异常
            return None, None

    def get(self, session_id: str):
        """✅ 优化: 使用细粒度锁"""
        return self._get_session_safely(session_id)

    def check_stream_url_exists(self, stream_url: str):
        """✅ 优化: 简化锁使用"""
        with self.sessions_lock:
            return stream_url in self.message_server_map
        return False

    def create_session(self, name: str, subject: str, session_type: str = "public"):
        """✅ 优化: 只在必要时持锁，修复竞态条件"""
        # ✅ 第一次加锁：获取或创建 message_client
        with self.sessions_lock:
            cache_auth_client = self.message_server_map.get(self.server_url)

            if self.server_url in self.message_client_map:
                log_info("复用message_client")
                message_client = self.message_client_map[self.server_url]
            else:
                message_client = MessageClient(
                    self.agent_id, self.server_url, self.aid_path, self.seed_password, cache_auth_client, agent_id_ref=self._agent_id_ref
                )
                message_client.initialize()
                self.message_client_map[self.server_url] = message_client

        # ✅ 释放锁后再执行耗时操作
        session = Session(self.agent_id, message_client)
        session_id, identifying_code = self.create_session_id(
            name, message_client, subject, session_type=session_type
        )

        if session_id is None or identifying_code is None:
            log_error(f"Failed to create Session {name}.")
            return None

        session.session_id = session_id
        session.identifying_code = identifying_code

        if not session_id:
            log_error(f"Failed to create Session {name}.")
            return None

        # ✅ 第二次加锁：添加session，并检查是否已存在（避免重复创建）
        with self.sessions_lock:
            if session_id in self.sessions:
                # ✅ 修复: 如果已存在，返回已有的session
                #log_info(f"session {session_id} already exists, returning existing session.")
                return self.sessions[session_id]

            self.sessions[session_id] = session
            self.message_server_map[self.server_url] = message_client.auth_client

        log_info(f"session {name} created: {session_id}.")
        return session

    def __on_create_session_ack(self, js):
        if "session_id" in js and "status_code" in js and "message" in js and "identifying_code" in js:
            # session_id = js["session_id"]
            # self.identifying_code = js["identifying_code"]
            temp_queue = self.create_session_queue_map.get(js["request_id"])
            if temp_queue:
                temp_queue.put(js)
                self.create_session_queue_map.pop(js["request_id"],None)
            if js["status_code"] == 200 or js["status_code"] == "200":
                log_info(f"create_session_ack: {js}")
            else:
                log_error(f"create_session_ack failed: {js}")
        else:
            log_error("收到的消息中不包括session_id字段，不符合预期格式")

    def close_all_session(self):
        """✅ 优化: 先获取所有session，释放锁后再关闭

        修复：同时关闭所有 MessageClient 的 WebSocket 连接，
        避免旧连接变成"孤儿"继续运行。
        """
        with self.sessions_lock:
            sessions_to_close = list(self.sessions.items())
            self.sessions.clear()
            # ✅ 获取所有 MessageClient（在锁内复制引用）
            message_clients_to_close = list(self.message_client_map.values())
            self.message_client_map.clear()
            self.message_server_map.clear()

        # ✅ 释放锁后再执行耗时的关闭操作
        for session_id, session in sessions_to_close:
            try:
                session.close_session()
            except Exception as e:
                log_error(f"close session {session_id} exception: {e}")

        # ✅ 关闭所有 MessageClient 的 WebSocket 连接
        for mc in message_clients_to_close:
            try:
                if mc:
                    log_info(f"[SessionManager] 关闭 MessageClient: {mc.server_url}")
                    mc.stop_websocket_client()
            except Exception as e:
                log_error(f"[SessionManager] 关闭 MessageClient 异常: {e}")

    def close_session(self, session_id: str):
        """✅ 优化: 快速获取session后释放锁再关闭"""
        session = self._remove_session_safely(session_id)
        if session is None:
            log_error(f"Session {session_id} does not exist.")
            return False

        # ✅ 释放锁后再执行耗时的关闭操作
        try:
            session.close_session()
        except Exception as e:
            log_error(f"close session {session_id} exception: {e}")
        return True

    def join_session(self, req: InviteMessageReq):
        """✅ 优化: 只在必要时持锁，修复竞态条件"""
        # ✅ 第一次加锁：获取或创建 message_client
        with self.sessions_lock:
            # ✅ 双重检查：可能已经加入过了
            if req.SessionId in self.sessions:
                #log_info(f"session {req.SessionId} already exists, returning existing session.")
                return self.sessions[req.SessionId]

            cache_auth_client = self.message_server_map.get(req.MessageServer)

            if req.MessageServer in self.message_client_map:
                message_client = self.message_client_map[req.MessageServer]
            else:
                message_client = MessageClient(
                    self.agent_id, req.MessageServer, self.aid_path, self.seed_password, cache_auth_client, agent_id_ref=self._agent_id_ref
                )
                message_client.initialize()
                message_client.set_message_handler(self)
                self.message_client_map[req.MessageServer] = message_client

        # ✅ 释放锁后创建session
        session: Session = Session(self.agent_id, message_client)
        session.session_id = req.SessionId
        session.accept_invite(req)
        session.invite_message = req

        # ✅ 第二次加锁：添加时再次检查，防止重复
        with self.sessions_lock:
            if req.SessionId in self.sessions:
                log_info(f"session {req.SessionId} was created by another thread, returning existing.")
                return self.sessions[req.SessionId]

            self.sessions[req.SessionId] = session
            self.message_server_map[req.MessageServer] = message_client.auth_client

        return session

    def leave_session(self, session_id: str):
        self.close_session(session_id)
        return

    def invite_member(self, session_id: str, acceptor_aid: str):
        """✅ 优化: 快速获取session后释放锁"""
        session = self._get_session_safely(session_id)
        if session is None:
            log_error(f"Session {session_id} does not exist.")
            return False

        # ✅ 释放锁后再执行操作
        return session.invite_member(acceptor_aid)

    async def create_stream(
        self, session_id: str, to_aid_list: [], content_type: str = "text/event-stream", ref_msg_id: str = ""
    ):
        """✅ 优化: 不持锁等待异步响应 - 关键修复！

        这是阻塞问题的根源：之前在持锁状态下等待服务器响应(最多15秒)
        现在改为快速获取session后立即释放锁，再进行异步等待
        """
        session = self._get_session_safely(session_id)
        if session is None:
            log_error(f"Session {session_id} does not exist.")
            return None, f"Session {session_id} does not exist."

        # ✅ 关键: 不持有任何锁的情况下等待异步响应
        return await session.create_stream(to_aid_list, content_type, ref_msg_id)

    def close_stream(self, session_id: str, stream_url: str):
        """✅ 优化: 快速获取session后释放锁"""
        session = self._get_session_safely(session_id)
        if session is None:
            log_error(f"Session {session_id} does not exist.")
            return False

        # ✅ 释放锁后再执行操作
        session.close_stream(stream_url)
        return True

    def send_chunk_to_stream(self, session_id: str, stream_url: str, chunk,type="text/event-stream"):
        """✅ 优化: 快速获取session后释放锁"""
        session = self._get_session_safely(session_id)
        if session is None:
            log_error(f"session {session_id} does not exist.")
            return False

        # ✅ 释放锁后再执行操作
        return session.send_chunk_to_stream(stream_url, chunk, type = type)

    def send_chunk_to_file_stream(self,session_id: str, stream_url: str, offset: int, chunk: bytes):
        """✅ 优化: 快速获取session后释放锁"""
        session = self._get_session_safely(session_id)
        if session is None:
            log_error(f"session {session_id} does not exist.")
            return False

        # ✅ 释放锁后再执行操作
        return session.send_file_chunk_to_stream(stream_url, offset, chunk)

    def send_msg(
        self,
        session_id: str,
        msg: list,
        receiver: str,
        ref_msg_id: str = "",
        message_id: str = "",
        agent_cmd_block: AgentInstructionBlock = None,
    ):
        """✅ 优化: 快速获取或创建session后释放锁，修复竞态条件"""
        session = self._get_session_safely(session_id)

        # ✅ 如果session不存在，需要创建
        if session is None:
            log_error(f"session {session_id} does not exist.")

            # 第一次加锁：获取或创建 message_client 和 session
            with self.sessions_lock:
                # ✅ 双重检查：可能其他线程已经创建了
                if session_id in self.sessions:
                    session = self.sessions[session_id]
                else:
                    # 确实不存在，获取 message_client
                    if self.server_url in self.message_client_map:
                        log_info("复用message_client")
                        message_client = self.message_client_map[self.server_url]
                    else:
                        cache_auth_client = self.message_server_map.get(self.server_url)
                        message_client = MessageClient(
                            self.agent_id, self.server_url, self.aid_path, self.seed_password, cache_auth_client, agent_id_ref=self._agent_id_ref
                        )
                        message_client.initialize()
                        self.message_client_map[self.server_url] = message_client

                    # ✅ 在锁内创建并添加session（避免释放锁后的竞态）
                    session = Session(self.agent_id, message_client)
                    message_client.set_message_handler(self)
                    session.session_id = session_id

                    # 尝试加载历史（如果失败也继续）
                    try:
                        result = self.db_mananger.load_session_history(session_id)
                        if result:
                            session.identifying_code = result[0]["identifying_code"]
                    except Exception as e:
                        log_error(f"load session history failed: {e}")

                    # ✅ 在锁内添加，确保原子性
                    self.sessions[session_id] = session

        # ✅ 释放锁后再发送消息
        session.send_msg(msg, receiver, ref_msg_id, message_id, agent_cmd_block)
        return True

    def init_his_session(self, session_id: str, session: Session):
        session.session_id = session_id
        result = self.db_mananger.load_session_history(session_id)
        if not result:
            log_error(f"load session history failed: {session_id}")
            return False
        session.identifying_code = result[0]["identifying_code"]

    def set_on_message_receive(self, on_message_recive):
        self.on_message_receive = on_message_recive

    def set_on_invite_ack(self, on_invite_ack):
        self.on_invite_ack = on_invite_ack

    def set_on_session_message_ack(self, on_session_message_ack):
        self.on_session_message_ack = on_session_message_ack

    def set_on_system_message(self, on_system_message):
        self.on_system_message = on_system_message

    def set_on_member_list_receive(self, on_member_list_receive):
        self.on_member_list_receive = on_member_list_receive
