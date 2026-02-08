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
import ssl
import threading
import time
import urllib.parse
from typing import Optional

import websocket

from agentcp.base.log import log_debug, log_error, log_exception, log_info
from agentcp.msg.wss_binary_message import *

from ..context import ErrorContext, exceptions

@dataclass
class FileChunk:
    offset: int
    chunk_size: int
    chunk: bytes

class StreamClient:
    def __init__(self, agent_id: str, session_id, server_url: str, signature: str):
        """消息客户端类
        Args:
            agent_id: 代理ID
            server_url: 服务器URL
        """
        self.session_id = session_id
        self.agent_id = agent_id
        self.server_url = server_url
        self.signature = signature
        self.connected_event = threading.Event()
        self.ws = None
        self.ws_url = ""
        self.ws_thread: Optional[threading.Thread] = None
        self.ws_is_running = False
        self.ws_chunks = ""
        self.file_stream_chunk_queue = queue.Queue()
        self.file_stream_push_cache_left_space = 65536

    def set_message_handler(self, message_handler):
        """设置消息处理器"""
        self.message_handler = message_handler

    def start_websocket_client(self):
        if self.connected_event.is_set():
            return

        # 确保URL格式正确
        ws_url = self.server_url.rstrip("/")  # 移除末尾斜杠
        ws_url = ws_url.replace("https://", "wss://").replace("http://", "ws://")
        ws_url = ws_url + f"&agent_id={self.agent_id}"

        log_debug(f"message Connecting to WebSocket URL: {ws_url}")  # 调试日志
        self.ws_url = ws_url
        self.ws_thread = threading.Thread(target=self.__ws_handler, daemon=True)
        self.ws_thread.start()
        wait = 0
        while not self.connected_event.is_set() and wait < 5:
            log_debug("WebSocket client is reconnect...")
            time.sleep(0.01)
            wait += 0.01
        return self.connected_event.is_set()

    def send_wss_message(self, msg):
        if self.ws.sock and self.ws.sock.connected:
            self.start_websocket_client()
        self.__send_wss_message_p(msg)

    def __send_wss_message_p(self, msg):
        if self.ws.sock and self.ws.sock.connected:
            bytes_msg = encode_wss_binary_message(msg)
            self.ws.send(bytes_msg, websocket.ABNF.OPCODE_BINARY)

    def stop_websocket_client(self):
        if self.ws:
            self.ws.close()
        self.ws_thread.join()
        self.ws = None
        self.ws_thread = None

    def send_msg(self, msg):
        try:
            self.ws.send(msg)
            return True
        except Exception as e:
            log_exception(f"send message: {msg}")
            trace_id = msg.get("trace_id", "") if isinstance(msg, dict) else ""
            ErrorContext.publish(exceptions.SendMsgError(f"发送消息时发生错误: {e}", trace_id=trace_id))

    def send_chunk_to_stream(self, chunk, type="text/event-stream"):

        if self.ws is None or self.ws.sock is None or not self.ws.sock.connected:
            log_error("WebSocket connection is not established @send_chunk_to_stream.")
            self.ws_chunks += chunk
            return False
        try:
            if type=="text/event-stream":
                chunk_quote = urllib.parse.quote_plus(chunk)
                data = {
                    "cmd": "push_text_stream_req",
                    "data": {
                        "chunk": f"{chunk_quote}",
                    },
                }
                msg = json.dumps(data)
                self.send_msg(msg)  # 发送消息到 WebSocket 服务器
                return True
            return False
        except Exception as e:
            import traceback
            log_error(f"发送消息时发生错误: {str(e)}\n{traceback.format_exc()}")
            ErrorContext.publish(exceptions.SendChunkToStreamError(f"发送消息时发生错误: {e}"))
            return False

    def send_chunk_to_file_stream(self, offset: int, chunk: bytes) -> bool:
        try:
            if self.ws is None or self.ws.sock is None or not self.ws.sock.connected:
                file_chunk = FileChunk()
                file_chunk.offset = offset
                file_chunk.size = len(chunk)
                file_chunk.chunk = chunk
                self.file_stream_chunk_queue.put(file_chunk)
                time.sleep(1)
                return False
            msg = WssBinaryMessage()
            msg.magic_byte1 = ord('M')
            msg.magic_byte2 = ord('U')
            msg.version = 0x101
            msg.flags = 0
            msg.msg_type = 0x5
            msg.msg_seq = 0
            msg.content_type = 0x5
            msg.compressed = 0
            msg.reserved = offset
            if self.ws and self.ws.sock and self.ws.sock.connected:  # 检查WebSocket连接状态是否正常
                bytes_msg = encode_wss_binary_buffer(chunk, msg)
                self.ws.send(bytes_msg, websocket.ABNF.OPCODE_BINARY)
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 发送文件数据: {offset} + {len(chunk)}")
            self.file_stream_push_cache_left_space -= len(chunk)
            return self.file_stream_push_cache_left_space >= 16384
        except Exception as e:
            print(f"发送文件数据时发生错误: {str(e)}")
            return False

    def __ws_handler(self):
        """
        WebSocket客户端定时发送消息函数
        :param url: WebSocket服务器URL（ws://或wss://开头）
        :param message: 要定时发送的消息内容
        :param interval: 发送间隔时间（秒），默认5秒
        """
        try:

            def on_message(ws, message):
                """接收到服务器消息时的处理函数"""
                if isinstance(message, bytes):
                    txt_msg = decode_wss_binary_message(message)
                    if txt_msg is not None and len(txt_msg) > 0:
                        log_info(f"Text_Stream收到消息收到二进制消息: {txt_msg}")
                        on_message(ws, txt_msg)
                elif isinstance(message, str):
                    log_info(f"Text_Stream收到消息: {self.agent_id}\t{message}")

            def on_error(ws, error):
                """连接发生错误时的处理函数"""
                log_error(f"Text_Stream连接错误: {error}")
                ErrorContext.publish(exceptions.SDKError(f"websocket on_error: {error}"))

            def on_close(ws, close_status_code, close_msg):
                """连接关闭时的处理函数"""
                log_info("Text_Stream WebSocket 连接已关闭")

            def on_open(ws):
                """连接建立后的处理函数，用于发送初始消息"""
                log_info("Text_Stream WebSocket 连接已建立")
                self.connected_event.set()  # 设置连接事件
                # if self.ws_chunks is not None and len(self.ws_chunks) > 0:
                #     self.send_chunk_to_stream(self.ws_chunks)
                #     self.ws_chunks = ""

            # 创建 WebSocket 客户端实例
            self.ws = websocket.WebSocketApp(
                self.ws_url,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
            )
            # 启动WebSocket连接（阻塞当前线程）
            self.ws.run_forever(
                sslopt={
                    "cert_reqs": ssl.CERT_NONE,  # 禁用证书验证
                    "check_hostname": False,  # 忽略主机名不匹配
                }
            )
        except Exception as e:
            log_exception(f"WebSocket连接失败: {e}")
            ErrorContext.publish(exceptions.SDKError(f"WebSocket连接失败: {e}"))

    def close_stream(self, stream_url: str):
        if self.ws and self.ws.sock and self.ws.sock.connected:  # 检查WebSocket连接状态是否正常
            data = {
                "cmd": "close_stream_req",
            }
            msg = json.dumps(data)
            self.ws.send(msg)
            # self.__send_wss_message(self.ws, msg)  # 发送消息到 WebSocket 服务器
            log_info(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 发送消息: {msg}")

        if self.ws_is_running:
            self.ws_is_running = False
            self.ws.close()
            self.ws = None

    def __send_wss_message(self, msg):
        if self.ws.sock and self.ws.sock.connected:
            bytes_msg = encode_wss_binary_message(msg)
            self.ws.send(bytes_msg, websocket.ABNF.OPCODE_BINARY)
