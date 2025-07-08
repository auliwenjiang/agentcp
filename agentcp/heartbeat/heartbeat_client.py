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
from agentcp.base.log import log_debug, log_error, log_exception, log_info
from agentcp.base.auth_client import AuthClient

from agentcp.msg.message_serialize import *

class HeartbeatClient:
    def __init__(self, agent_id: str, server_url: str,aid_path: str,seed_password: str):
        self.agent_id = agent_id
        self.server_url = server_url
        self.agent_id = agent_id
        self.server_url = server_url
        self.seed_password = seed_password
        self.port = 0 #server_port
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
        self.auth_client = AuthClient(agent_id, server_url,aid_path,seed_password)  # 使用AuthClient

    def initialize(self):
        self.sign_in()
        
    def sign_in(self)->bool:
        data = self.auth_client.sign_in()
        if data is None:
            log_error("sign_in failed: data is None")
            return False
        self.server_ip = data.get("server_ip")
        self.port = int(data.get("port", 0))
        self.sign_cookie = data.get("sign_cookie")
        log_info(f'singin {self.server_ip} {self.port} {self.sign_cookie}')
        
        return self.server_ip is not None and self.port != 0 and self.sign_cookie is not None
    
    def sign_out(self):
        self.auth_client.sign_out()
  
    def set_on_recv_invite(self, listener):
        """设置消息监听器"""
        self.on_recv_invite = listener

    def __send_heartbeat(self):
        while self.is_sending_heartbeat and self.is_running:
            try:
                current_time_ms = int(datetime.datetime.now().timestamp() * 1000)  # 获取当前时间戳(毫秒)
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
                    self.udp_socket.sendto(data, (self.server_ip, self.port))
                time.sleep(1)  # 休眠1毫秒
            except Exception as e:
                log_exception(f"Heartbeat send error: {e}")

    def _receive_messages(self):
        while self.is_running:
            try:
                data, addr = self.udp_socket.recvfrom(1536)
                udp_header, offset = UdpMessageHeader.deserialize(data, 0)
                if udp_header.MessageType == 258:
                    hb_resp, offset = HeartbeatMessageResp.deserialize(data, 0)
                    self.heartbeat_interval = hb_resp.NextBeat
                    #服务器端身份验证失败(比如服务器发生了异常重启)，需要重新登录
                    if hb_resp.NextBeat == 401:
                        log_error(f"Heartbeat failed: {hb_resp.NextBeat}, try sign in again")
                        self.sign_in()
                    if self.heartbeat_interval <= 5000:
                        self.heartbeat_interval = 5000
                elif udp_header.MessageType == 259:
                    invite_req, offset = InviteMessageReq.deserialize(data, 0)
                    if self.on_recv_invite is not None:
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
                    data = buf.getvalue()
                    self.udp_socket.sendto(data, (self.server_ip, self.port))
            except Exception as e:
                log_exception(f"Receive message exception: {e}")
                time.sleep(1.5)  # 等待1.5秒后重试

    def online(self):
        """开始心跳"""
        # 创建并启动心跳线程
        if self.is_running:
            return

        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.bind((self.local_ip, self.local_port))
        # 获取绑定成功的本地地址信息
        self.local_ip, self.local_port = self.udp_socket.getsockname()
        log_info(f"UDP socket bound to {self.local_ip}:{self.local_port}")

        self.is_running = True
        self.is_sending_heartbeat = True

        self.send_thread = threading.Thread(target=self.__send_heartbeat, daemon=True)
        self.receive_thread = threading.Thread(target=self._receive_messages, daemon=True)

        self.send_thread.start()
        self.receive_thread.start()
        log_info("Successfully went online")

    def offline(self):
        """停止心跳"""
        if self.udp_socket is not None:
            self.udp_socket.close()
        self.is_running = False
        pass
    
    def get_online_status(self,aids):
        try:
            ep_url = self.server_url + "/query_online_state"
            data = {
                "agent_id": f"{self.agent_id}",
                "signature": self.auth_client.signature,
                "agents":aids
            }
            response = requests.post(ep_url, json=data, verify=False)
            if response.status_code == 200:
                log_info(f"get_online_status ok:{response.json()}")
                return response.json()["data"]
            else:
                log_error(f"get_on_line_status failed:{response.json()}")
                return []
        except Exception as e:
            log_exception(f"get_on_line_status in exception: {e}")
            return []