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
import json
import queue
import threading
import time
import uuid
from threading import Lock
from typing import Optional

from agentcp.base.log import log_debug, log_error, log_exception, log_info
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
        self._create_stream_lock = Lock()  # 添加创建流的锁

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

        send_msg = urllib.parse.quote(json.dumps(msg))
        data = {
            "cmd": "session_message",
            "data": {
                "message_id": message_id,
                "session_id": self.session_id,
                "ref_msg_id": ref_msg_id,
                "sender": f"{self.agent_id}",
                "instruction": agent_cmd_block,
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
            log_info("WebSocket connection opened.")
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
        with self._create_stream_lock:  # 使用锁保护整个创建流的过程
            try:
                start_time = time.time()
                receiver = ",".join(to_aid_list)
                data = {
                    "cmd": "session_create_stream_req",
                    "data": {
                        "session_id": self.session_id,
                        "request_id": f"{int(time.time() * 1000)}",
                        "ref_msg_id": ref_msg_id,
                        "sender": f"{self.agent_id}",
                        "receiver": receiver,
                        "content_type": content_type,
                        "timestamp": f"{int(time.time() * 1000)}",
                    },
                }
                msg = json.dumps(data)
                # self.ws.send(msg)
                self.message_client.send_msg(msg)  # 发送消息到 WebSocket 服务器
                log_info(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 发送消息: {msg}")
                ack = self.message_client.queue.get(timeout=3)
                if "session_id" in ack and "push_url" in ack and "pull_url" in ack and "message_id" in ack:
                    push_url = ack["push_url"]
                    pull_url = ack["pull_url"]
                    try:
                        success = self.__create_stream_client(self.session_id, push_url)
                        if not success:
                            ErrorContext.publish(exceptions.CreateStreamError(f"创建流失败: {push_url}"))
                            log_error(f"创建流失败: {push_url}")
                            return None, f"创建流成功,连接失败: {push_url}"
                    except Exception as e:
                        log_error(f"创建流失败: {str(e)}")
                        ErrorContext.publish(exceptions.CreateStreamError(f"创建流失败: {push_url}"))
                        return None, f"创建流成功,连接异常: {str(e)}"
                    return push_url, pull_url
                ErrorContext.publish(exceptions.CreateStreamError("未获取到流连接"))
                return None, "未获取到流连接"
            except Exception as e:
                import traceback
                ErrorContext.publish(exceptions.CreateStreamError(f"创建流异常: {traceback.format_exc()}"))
                log_error(f"发送消息时发生错误: {str(e)}\n{traceback.format_exc()}")
                return None, f"创建流异常: {str(e)}"

    def __create_stream_client(self, session_id, push_url):
        stream_client = StreamClient(self.agent_id, session_id, push_url, self.message_client.auth_client.signature)
        ws_url = push_url
        ws_url = ws_url + f"&agent_id={self.agent_id}&signature={self.message_client.auth_client.signature}"
        log_info(f"ws_ts_url = {ws_url}")
        stream_client.ws_url = ws_url
        stream_client.ws_is_running = True
        success = stream_client.start_websocket_client()
        if not success:
            log_error(f"创建流失败, 启动websocket失败: {stream_client.ws_url}")
            ErrorContext.publish(exceptions.CreateStreamError(f"创建流失败: {stream_client.ws_url}"))
            return None
        self.stream_client_map[push_url] = stream_client
        return stream_client

    def send_chunk_to_stream(self, stream_url: str, chunk,type="text/event-stream"):
        stream_client: StreamClient = self.stream_client_map.get(stream_url)
        if not stream_client:
            ErrorContext.publish(
                exceptions.SendChunkToStreamError(f"send_chunk_to_stream, stream_client is none: {stream_client}")
            )
            return False,f"send_chunk_to_stream, stream_client is none: {stream_client.ws_url}"
        return stream_client.send_chunk_to_stream(chunk)

    def send_file_chunk_to_stream(self, stream_url: str, offset: int, chunk: bytes):
        stream_client: StreamClient = self.stream_client_map.get(stream_url)
        if not stream_client:
            ErrorContext.publish(
                exceptions.SendChunkToStreamError(
                    f"send_chunk_to_stream, stream_client is none: {stream_client.ws_url}"
                )
            )
            return False,f"send_chunk_to_stream, stream_client is none: {stream_client.ws_url}"
        return stream_client.send_chunk_to_file_stream(offset,chunk)

    def close_stream(self, stream_url: str):
        stream_client: StreamClient = self.stream_client_map.get(stream_url)
        if stream_client is not None:
            stream_client.close_stream(stream_url)
            stream_client = None
            self.stream_client_map.pop(stream_url)
            log_info(f"关闭流: {stream_url}")


class SessionManager:
    def __init__(self, agent_id: str, server_url: str, aid_path: str, seed_password: str, db_mananger: DBManager):
        self.lock = threading.Lock()
        self.sessions = {}
        self.agent_id = agent_id
        self.server_url = server_url
        self.aid_path = aid_path
        self.seed_password = seed_password
        # 连接多个消息服务器
        self.message_client_map = {}
        # 多条流式消息
        self.message_server_map = {}
        self.db_mananger = db_mananger
        self.queue = queue.Queue()
        self.create_session_event = threading.Event()
        self._create_session_lock = Lock()

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

            self.__create(message_client, name, subject, session_type)
            # 等待创建群组的响应
            self.create_session_event.wait()
            try:
                session_result = self.queue.get(timeout=1)
                self.queue.task_done()
            except Exception:
                ErrorContext.publish(exceptions.CreateSessionError("创建会话等待结果超时"))
                log_error("队列获取超时，当前队列内容:{list(self.queue.queue)}")
                return None, None
            return session_result["session_id"], session_result["identifying_code"]

    def on_open(self, ws):
        """WebSocket连接建立时的处理函数"""
        log_info("WebSocket connection opened.")
        try:
            for session in self.sessions.values():
                # 成员断线加入
                session.on_open()
        except Exception as e:
            import traceback
            log_error(f"WebSocket连接建立时的处理函数: {e}\n{traceback.format_exc()}")

    def on_message(self, ws, message):
        """接收到服务器消息时的处理函数"""
        try:
            log_info(f"received a message: {message}")
            js = json.loads(message)
            if "cmd" not in js or "data" not in js:
                log_error("收到的消息中不包括cmd字段，不符合预期格式")
                return
            cmd = js["cmd"]
            message_data = js["data"]
            session_id = message_data.get("session_id", "")
            if session_id:
                session = self.sessions.get(session_id)
            if cmd == "create_session_ack":
                self.__on_create_session_ack(js["data"])
            elif cmd == "session_message" and session is not None:
                import urllib.parse

                message_content = js["data"]["message"]
                js["data"]["message"] = urllib.parse.unquote(message_content)
                if self.on_message_receive is not None:
                    self.on_message_receive(js["data"])
                    # TODO after receive message, send ack
                else:
                    log_error("on_message_recive is None")
            elif cmd == "invite_agent_ack" and session is not None:
                log_info(f"收到邀请消息: {js}")
                if self.on_invite_ack is not None:
                    self.on_invite_ack(js["data"])
                else:
                    log_error("on_message_recive is None")
            elif cmd == "session_message_ack" and session is not None and self.on_session_message_ack is not None:
                return self.on_session_message_ack(js["data"])

            elif cmd == "session_create_stream_ack" and session is not None and session.message_client is not None:
                log_info("收到创建流成功的消息")
                session.message_client.queue.put(js["data"])

            elif cmd == "system_message" and session is not None and self.on_system_message is not None:
                self.on_system_message(js["data"])
        except Exception as e:
            import traceback

            log_error(f"处理消息时发生异常: {e}\n{traceback.format_exc()}")

    def __create(self, message_client: MessageClient, session_name: str, subject: str, session_type: str = "public"):
        log_info(f"create_session: {session_name}, {subject}, {session_type}")
        try:
            log_debug("check WebSocket connection status")  # 调试日志
            data = {
                "cmd": "create_session_req",
                "data": {
                    "request_id": f"{uuid.uuid4().hex}",
                    "type": f"{session_type}",
                    "group_name": f"{session_name}",
                    "subject": f"{subject}",
                    "timestamp": f"{int(time.time() * 1000)}",
                },
            }
            msg = json.dumps(data)
            message_client.send_msg(msg)
            log_debug(f"send message: {msg}")  # 调试日志
        except Exception as e:
            ErrorContext.publish(exceptions.CreateSessionError("创建会话等待结果超时"))
            log_exception(f"send create chat session message exception: {e}")  # 记录异常

    def get(self, session_id: str):
        with self.lock:
            session: Session = self.sessions.get(session_id)
            return session

    def check_stream_url_exists(self, stream_url: str):
        with self.lock:
            return stream_url in self.message_server_map
        return False

    def create_session(self, name: str, subject: str, session_type: str = "public"):
        with self.lock:
            if name in self.sessions:
                log_error(f"session {name} already exists.")
                return None
            cache_auth_client = None
            if self.server_url in self.message_server_map:
                cache_auth_client = self.message_server_map[self.server_url]

            if self.server_url in self.message_client_map:
                log_info("复用message_client")
                message_client = self.message_client_map[self.server_url]
            else:
                message_client = MessageClient(
                    self.agent_id, self.server_url, self.aid_path, self.seed_password, cache_auth_client
                )
                message_client.initialize()
                self.message_client_map[self.server_url] = message_client
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
            self.sessions[session_id] = session
            log_info(f"session {name} created: {session_id}.")
            self.message_server_map[self.server_url] = message_client.auth_client
            return session

    def __on_create_session_ack(self, js):
        if "session_id" in js and "status_code" in js and "message" in js and "identifying_code" in js:
            # session_id = js["session_id"]
            # self.identifying_code = js["identifying_code"]
            self.queue.put(js)
            self.create_session_event.set()
            if js["status_code"] == 200 or js["status_code"] == "200":
                log_info(f"create_session_ack: {js}")
            else:
                log_error(f"create_session_ack failed: {js}")
        else:
            log_error("收到的消息中不包括session_id字段，不符合预期格式")

    def close_all_session(self):
        with self.lock:
            try:
                for session_id in self.sessions:
                    session: Session = self.sessions[session_id]
                    session.close_session()
                    del self.sessions[session_id]
            except Exception as e:
                log_error(f"close_all_session exception: {e}")

    def close_session(self, session_id: str):
        with self.lock:
            if session_id not in self.sessions:
                log_error(f"Session {session_id} does not exist.")
                return False
            session: Session = self.sessions[session_id]
            session.close_session()
            del self.sessions[session_id]

    def join_session(self, req: InviteMessageReq):
        with self.lock:
            # if req.SessionId in self.sessions:
            #     return self.sessions[req.SessionId]
            cache_auth_client = None
            if req.MessageServer in self.message_server_map:
                cache_auth_client = self.message_server_map[req.MessageServer]

            if req.MessageServer in self.message_client_map:
                message_client = self.message_client_map[req.MessageServer]
            else:
                message_client = MessageClient(
                    self.agent_id, req.MessageServer, self.aid_path, self.seed_password, cache_auth_client
                )
                message_client.initialize()
                message_client.set_message_handler(self)
                self.message_client_map[req.MessageServer] = message_client

            session: Session = Session(self.agent_id, message_client)
            session.session_id = req.SessionId
            session.accept_invite(req)
            session.invite_message = req
            self.sessions[req.SessionId] = session
            self.message_server_map[req.MessageServer] = message_client.auth_client
            return session

    def leave_session(self, session_id: str):
        self.close_session(session_id)
        return

    def invite_member(self, session_id: str, acceptor_aid: str):
        with self.lock:
            if session_id not in self.sessions:
                log_error(f"Session {session_id} does not exist.")
                return False
            session: Session = self.sessions[session_id]
            return session.invite_member(acceptor_aid)

    async def create_stream(
        self, session_id: str, to_aid_list: [], content_type: str = "text/event-stream", ref_msg_id: str = ""
    ):
        with self.lock:
            if session_id not in self.sessions:
                log_error(f"Session {session_id} does not exist.")
                return None, f"Session {session_id} does not exist."
            session: Session = self.sessions[session_id]
            return await session.create_stream(to_aid_list, content_type, ref_msg_id)

    def close_stream(self, session_id: str, stream_url: str):
        with self.lock:
            if session_id not in self.sessions:
                log_error(f"Session {session_id} does not exist.")
                return False
            session: Session = self.sessions[session_id]
            session.close_stream(stream_url)

    def send_chunk_to_stream(self, session_id: str, stream_url: str, chunk,type="text/event-stream"):
        with self.lock:
            if session_id not in self.sessions:
                log_error(f"session {session_id} does not exist.")
                return False
            session: Session = self.sessions[session_id]
            return session.send_chunk_to_stream(stream_url, chunk,type = type)

    def send_chunk_to_file_stream(self,session_id: str, stream_url: str, offset: int, chunk: bytes):
        with self.lock:
            if session_id not in self.sessions:
                log_error(f"session {session_id} does not exist.")
                return False
            session: Session = self.sessions[session_id]
            return session.send_file_chunk_to_stream(stream_url, offset,chunk)

    def send_msg(
        self,
        session_id: str,
        msg: list,
        receiver: str,
        ref_msg_id: str = "",
        message_id: str = "",
        agent_cmd_block: AgentInstructionBlock = None,
    ):
        with self.lock:
            if session_id not in self.sessions:
                log_error(f"session {session_id} does not exist.")
                # 加载本地缓存的消息
                if self.server_url in self.message_client_map:
                    log_info("复用message_client")
                    message_client = self.message_client_map[self.server_url]
                else:
                    cache_auth_client = None
                    if self.server_url in self.message_server_map:
                        cache_auth_client = self.message_server_map[self.server_url]
                    message_client = MessageClient(
                        self.agent_id, self.server_url, self.aid_path, self.seed_password, cache_auth_client
                    )
                    message_client.initialize()
                    self.message_client_map[self.server_url] = message_client
                session = Session(self.agent_id, message_client)
                message_client.set_message_handler(self)
                self.init_his_session(session_id, session)
                self.sessions[session_id] = session
            session: Session = self.sessions[session_id]
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
