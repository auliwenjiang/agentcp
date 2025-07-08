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
import websocket
import os
import ssl
from agentcp.msg.wss_binary_message import decode_wss_binary_buffer
def download_file_via_websocket(wss_url, save_path):
    """
    通过WebSocket下载文件并保存到指定路径
    :param wss_url: WebSocket连接地址
    :param file_extension: 文件扩展名
    :param save_path: 文件保存路径
    """

    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    file_stream_pulled_file = open(save_path, "wb")
    print(f"文件保存路径:{save_path}")
    def on_message(ws, message):
        try:
            if isinstance(message, bytes):
                bin_msg = decode_wss_binary_buffer(message)
                if bin_msg is None:
                    return
                if bin_msg.msg_type == 0x5 and bin_msg.content_type == 0x5:
                    print(f"收到文件流:offset={bin_msg.reserved}, size={bin_msg.payload_length}, crc32={bin_msg.crc32}")
                    if file_stream_pulled_file is not None:
                        file_stream_pulled_file.write(bin_msg.payload)
                else:
                    txt_msg = bin_msg.payload.decode()
                    if txt_msg is not None and len(txt_msg) > 0:
                        print(f"File_Stream pull handler 收到消息收到二进制消息: {txt_msg}")
                        on_message(ws, txt_msg)
            elif isinstance(message, str):
                import json
                js = json.loads(message)
                if "cmd" not in js or "data" not in js:
                    return
                cmd = js["cmd"]
                data = js["data"]
                if cmd == "close_file_stream_req":
                    if file_stream_pulled_file is not None:
                        file_stream_pulled_file.close()
                        file_stream_pulled_file = None
                        ws.close()

        except Exception as e:
            print(f"file_stream_pull_handler在处理收到的消息时发生异常 {str(e)}")

    def on_error(ws, error):
        print(f"发生错误: {error}")
        ws.close()  # 发生错误时主动关闭连接

    def on_close(ws, close_status_code, close_msg):
        print("连接已关闭")
        ws = None  # 确保引用被清除

    def on_open(ws):
        print("连接已建立，等待文件数据...")

    # 创建WebSocket连接，禁用SSL验证
    ws = websocket.WebSocketApp(wss_url,
                              on_open=on_open,
                              on_message=on_message,
                              on_error=on_error,
                              on_close=on_close)
    
    # 运行时不验证SSL证书
    ws.run_forever(
        sslopt={
            "cert_reqs": ssl.CERT_NONE,  # 禁用证书验证
            "check_hostname": False,  # 忽略主机名不匹配
        }
    )