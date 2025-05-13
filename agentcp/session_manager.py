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
import queue
import uuid
import threading
import time
import json
from typing import Optional
from agentcp.log import log_debug, log_error, log_info
from agentcp.message_client import MessageClient
from agentcp.message_serialize import InviteMessageReq
from agentcp.wss_binary_message import *
from agentcp.stream_client import StreamClient


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
        self.on_member_list_receive = None
        self.message_client: MessageClient = message_client
        self.stream_client: StreamClient = None
        self.queue = queue.Queue()
        self.invite_message = None
        self.text_stream_pulling = False
        self.text_stream_pull_url = ""
        self.text_stream_recv_thread: Optional[threading.Thread] = None
        
    def initialize(self, name: str, subject: str, *, session_type: str = "public", session_id=None)->str:
        log_info(f"sign in success: {self.agent_id}")
        self.message_client.set_message_handler(self)
        if not self.message_client.start_websocket_client():
            log_error("Failed to start WebSocket client.")
            return
        
        if not session_id:
            self._create(name, subject, session_type)
            # 等待创建群组的响应
            self.session_id = self.queue.get(timeout=5)
            self.queue.task_done()
        else:
            self.session_id = session_id
            log_info(f"join session: {self.session_id}")
        return self.session_id

    def can_invite_member(self):
        return not not self.identifying_code

    def set_session_id(self, session_id: str):
        self.session_id = session_id

    def set_on_message_receive(self, on_message_recive):
        self.on_message_receive = on_message_recive
    
    def set_on_invite_ack(self, on_invite_ack):
        self.on_invite_ack = on_invite_ack
    
    def set_on_member_list_receive(self, on_member_list_receive):
        self.on_member_list_receive = on_member_list_receive

    def __on_create_session_ack(self, js):
        if "session_id" in js and "status_code" in js and "message" in js and "identifying_code" in js:
            self.session_id = js["session_id"]
            self.identifying_code = js["identifying_code"]
            self.queue.put(self.session_id)

            if js["status_code"] == 200 or js["status_code"] == "200":
                log_info(f"create_session_ack: {js}")
            else:
                log_error(f"create_session_ack failed: {js}")
        else:
            log_error("收到的消息中不包括session_id字段，不符合预期格式")

    def _create(self, session_name: str, subject: str, session_type: str = "public"):
        log_info(f"create_session: {session_name}, {subject}, {session_type}")
        try:
            log_debug(f"check WebSocket connection status")  # 调试日志
            data = {
                    "cmd" : "create_session_req",
                    "data" : {
                        "request_id": f"{uuid.uuid4().hex}",
                        "type": f"{session_type}",
                        "group_name": f"{session_name}",
                        "subject": f"{subject}",
                        "timestamp": f"{int(time.time() * 1000)}"
                    },
                }
            msg = json.dumps(data)
            self.message_client.send_msg(msg)
            log_debug(f"send message: {msg}")  # 调试日志
        except Exception as e:
            log_exception(f'send create chat session message exception: {e}')  # 记录异常

    def close_session(self):
        self.message_client.stop_websocket_client()
        pass

    # accept invite request
    def accept_invite(self, invite_req: InviteMessageReq):
        try:
            data = {
                    "cmd" : "join_session_req",
                    "data" : {
                        "session_id": invite_req.SessionId,
                        "request_id": f"{int(time.time() * 1000)}",
                        "inviter_agent_id": invite_req.InviterAgentId,
                        "invite_code": invite_req.InviteCode,
                        "last_msg_id": "0"
                    },
                }
            msg = json.dumps(data)
            self.message_client.send_msg(msg)
            log_debug(f"send join chat session message: {msg}")  # 调试日志
        except Exception as e:
            log_exception(f'send join chat session message exception: {e}')  # 记录异常

    def reject_invite(self, invite_req: InviteMessageReq):
        pass

    def leave_session(self, session_id: str):
        pass

    def invite_member(self, acceptor_aid: str):
        try:
            data = {
                    "cmd" : "invite_agent_req",
                    "data" : {
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
            log_exception(f'send invite message exception: {e}')  # 记录异常
            return False

    def eject_member(self,  eject_aid: str):
        try:
            data = {
                    "cmd" : "eject_agent_req",
                    "data" : {
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
            log_exception(f'send eject message exception: {e}')
            return False

    def get_member_list(self):
        try:
            # SessionId       string `json:"session_id"`
            # RequestId       string `json:"request_id"`
            data = {
                    "cmd" : "get_member_list",
                    "data" : {
                        "session_id": f"{self.session_id}",
                        "request_id": f"{int(time.time() * 1000)}",
                    },
                }
            msg = json.dumps(data)
            self.message_client.send_msg(msg)
            log_debug(f"send get member list message: {msg}")  # 调试日志
            return True
        except Exception as e:
            log_exception(f'send get member list message exception: {e}')
            return False

    def send_msg(self, msg: str, receiver: str, ref_msg_id : str = "",message_id:str =""):
        import urllib.parse
        send_msg = urllib.parse.quote(msg)
        data = {
                    "cmd" : "session_message",
                    "data" : {
                        "message_id":message_id,
                        "session_id": self.session_id,
                        "ref_msg_id": ref_msg_id,
                        "sender": f"{self.agent_id}",
                        "receiver": receiver,
                        "message": send_msg,
                        "timestamp": f"{int(time.time() * 1000)}"
                    },
                }
        msg = json.dumps(data)
        log_debug(f"send message: {msg}")
        self.message_client.send_msg(msg)

    def on_message(self, ws, message):
        """接收到服务器消息时的处理函数"""
        try:
            # print(f"message_client收到消息: {message}")
            # 如果需要解析 JSON 数据，可以使用 json.loads(message)
            log_debug(f"received a message: {message}")
            js = json.loads(message)
            if "cmd" not in js or "data" not in js:
                log_error("收到的消息中不包括cmd字段，不符合预期格式")
                return
            cmd = js["cmd"]

            if cmd == "create_session_ack":
                self.__on_create_session_ack(js["data"])

            elif cmd == "session_message":
                import urllib.parse
                message_content = js["data"]["message"]
                js["data"]["message"] = urllib.parse.unquote(message_content)
                if self.on_message_receive is not None:
                    self.on_message_receive(js["data"])
                    # TODO after receive message, send ack
                else:
                    log_error("on_message_recive is None")
            elif cmd == "invite_agent_ack":
                log_info(f"收到邀请消息: {js}")
                if self.on_invite_ack is not None:
                    self.on_invite_ack(js["data"])
                    # TODO after receive message, send ack
                else:
                    log_error("on_message_recive is None")
            # elif cmd == "member_list":
            #     return self.on_member_list_receive(js["data"])
                    
            elif cmd == "session_create_stream_ack":
                log_info("收到创建流成功的消息")
                self.message_client.queue.put(js["data"])
        except Exception as e:
            import traceback
            log_error(f"处理消息时发生异常: {e}\n{traceback.format_exc()}")

    def on_open(self, ws):
        """WebSocket连接建立时的处理函数"""
        log_info("WebSocket connection opened.")
        # 成员断线加入
        if self.invite_message is not None:
            self.accept_invite(self.invite_message)

        # owner重新加入
        if self.identifying_code:
            self.owner_rejoin()

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
            log_exception(f'send owner rejoin message exception: {e}')
            
    async def create_stream(self, to_aid_list: [], content_type: str = "text/event-stream", ref_msg_id : str = ""):      
        try:
            receiver = ','.join(to_aid_list)
            data = {
                "cmd" : "session_create_stream_req",
                "data" : {
                    "session_id": self.session_id,
                    "request_id": f"{int(time.time() * 1000)}",
                    "ref_msg_id": ref_msg_id,
                    "sender": f"{self.agent_id}",
                    "receiver": receiver,
                    "content_type": content_type,
                    "timestamp": f"{int(time.time() * 1000)}"
                },
            }
            msg = json.dumps(data)
            #self.ws.send(msg)
            self.message_client.send_msg(msg)  # 发送消息到 WebSocket 服务器
            log_info(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 发送消息: {msg}")
            ack = self.message_client.queue.get(timeout=3)
            log_info("等待ack响应")
            if "session_id" in ack and "push_url" in ack and "pull_url" in ack and "message_id" in ack:
                push_url = ack["push_url"]
                pull_url = ack["pull_url"]
                if self.stream_client is not None:
                    log_error("session is already running.")
                    return push_url, pull_url
                signature = self.message_client.auth_client.signature
                if signature is None:
                    log_error("Signature is None.")
                    return None, None
                return push_url, pull_url
            return None, None
        except Exception as e:
            import traceback
            log_error(f"发送消息时发生错误: {str(e)}\n{traceback.format_exc()}")
            return None
    
    def __create_stream_client(self,session_id,push_url):
        self.stream_client = StreamClient(self.agent_id, session_id,push_url, self.message_client.auth_client.signature)
        ws_url = push_url
        ws_url = ws_url + f"&agent_id={self.agent_id}&signature={self.message_client.auth_client.signature}"
        log_info(f"ws_ts_url = {ws_url}")
        self.stream_client.ws_url = ws_url
        self.stream_client.ws_is_running = True
        self.stream_client.start_websocket_client()

    def send_chunk_to_stream(self,stream_url: str, chunk: str):
        if self.stream_client is None:
            self.__create_stream_client(self.session_id,stream_url)
        return self.stream_client.send_chunk_to_stream(chunk)
        
    def close_stream(self, stream_url: str):
        if self.stream_client is not None:
            self.stream_client.close_stream(stream_url)
            self.stream_client = None



class SessionManager:
    def __init__(self, agent_id: str, server_url: str,aid_path:str,seed_password: str):
        self.lock = threading.Lock()
        self.sessions = {}
        self.agent_id = agent_id
        self.server_url = server_url
        self.aid_path = aid_path
        self.seed_password = seed_password
        self.message_server_map = {}
    
    def get(self, session_id: str):
        with self.lock:
            session: Session = self.sessions.get(session_id)
            return session

    def create_session(self, name: str, subject: str, session_type: str = "public"):
        with self.lock:
            if name in self.sessions:
                log_error(f"session {name} already exists.")
                return None
            cache_auth_client = None
            if self.server_url in self.message_server_map:
                cache_auth_client = self.message_server_map[self.server_url]
            message_client = MessageClient(self.agent_id, self.server_url,self.aid_path,self.seed_password,cache_auth_client)
            message_client.initialize()
            session = Session(self.agent_id, message_client)
            session_id = session.initialize(name, subject, session_type=session_type)
            if not session_id:
                log_error(f"Failed to create Session {name}.")
                return None
            self.sessions[session_id] = session
            log_info(f"session {name} created: {session_id}.")
            self.message_server_map[self.server_url] = message_client.auth_client
            return session
        
    def close_all_session(self):
        with self.lock:
            for session_id in self.sessions:
                session: Session = self.sessions[session_id]
                session.close_session()
                del self.sessions[session_id]
    
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
            if req.SessionId in self.sessions:
                return self.sessions[req.SessionId]
            cache_auth_client = None
            if req.MessageServer in self.message_server_map:
                cache_auth_client = self.message_server_map[req.MessageServer]
            message_client = MessageClient(self.agent_id, req.MessageServer,self.aid_path,self.seed_password,cache_auth_client)
            message_client.initialize()           
            session: Session = Session(self.agent_id, message_client)
            if not session.initialize("", "", session_id=req.SessionId):
                log_error(f"Failed to join session {req.SessionId}.")
                return None
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
        
    async def create_stream(self, session_id: str,to_aid_list: [], content_type: str = "text/event-stream", ref_msg_id : str = ""):
        with self.lock:
            if session_id not in self.sessions:
                log_error(f"Session {session_id} does not exist.")
                return False
            session: Session = self.sessions[session_id]
            return await session.create_stream(to_aid_list, content_type, ref_msg_id)
        
    def close_stream(self, session_id: str,stream_url: str):
        with self.lock:
            if session_id not in self.sessions:
                log_error(f"Session {session_id} does not exist.")
                return False
            session: Session = self.sessions[session_id]
            session.close_stream(stream_url)
    
    def send_chunk_to_stream(self, session_id: str,stream_url: str, chunk: str):
        with self.lock:
            if session_id not in self.sessions:
                log_error(f"session {session_id} does not exist.")
                return False
            session: Session = self.sessions[session_id]
            return session.send_chunk_to_stream(stream_url, chunk)
        

    def send_msg(self, session_id: str, msg: str, receiver: str, ref_msg_id: str = "",message_id: str = ""):
        with self.lock:
            if session_id not in self.sessions:
                log_error(f"session {session_id} does not exist.")
                return False
            session: Session = self.sessions[session_id]
            session.send_msg(msg, receiver, ref_msg_id,message_id)
            return True