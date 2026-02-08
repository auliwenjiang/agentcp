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
from numbers import Number
import time
import requests
import datetime
import requests


from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives import hashes
import datetime
from cryptography.hazmat.primitives.asymmetric import ec

from agentcp.file.wss_binary_message import *
import websocket
from agentcp.base.auth_client import AuthClient
import ssl
from requests.packages.urllib3.exceptions import InsecureRequestWarning
import os

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

class FileClient:
    def __init__(self, aid_path:str,seed_password:str,agent_id: str, agent_network: str, cert: str = None, key: str = None):
        """消息客户端类

        Args:
            agent_id: 代理ID
            server_url: 服务器URL
        """
        self.agent_id = agent_id
        self.agent_network = agent_network
        self.server_url = "https://oss." + agent_network + "/api/oss"
        self.cert = cert
        self.key = key
        self.auth_client = AuthClient(agent_id, self.server_url, aid_path, seed_password)
        self.ws = None
        self.uploaded_url = ""
       
    def sign_in(self):
        """登录方法"""
        self.auth_client.sign_in()
    
    def sign_out(self):
        """登出方法""" 
        self.auth_client.sign_out()
    def get_signature(self):
        return self.auth_client.signature

    def close(self):
        if self.ws is not None:
            self.ws.close()


    #标准的post方式上传文件，同步阻塞的方式上传文件，需要修改为异步，并处理各种可能失败的情况
    def post_file(self, full_path):
        try:
            if self.auth_client.signature is None:
                self.sign_in()
            if self.auth_client.signature is None:
                print("sign_out failed: signature is None")
                return None
            params = {
                'agent_id': self.agent_id,
                'signature': self.auth_client.signature,
                'file_name': os.path.basename(full_path)
            }
            hb_url = self.server_url + f"/upload_file"
            with open(full_path, 'rb') as file:
                files = {'file': file}
                response = requests.post(hb_url, data = params, files=files,verify=False)
                if response.status_code == 200:
                    print('文件上传成功')
                    return response.json()["url"]
                else:
                    print(f'文件上传失败，状态码: {response.status_code}')
                    return None
        except FileNotFoundError:
            print('文件未找到')
            return None
        except Exception as e:
            print(f'发生错误: {e}')
            return None
        
    def get_uploaded_url(self):
        return self.uploaded_url

    #仅是测试代码，同步阻塞的方式下载文件，需要修改为异步，并处理各种可能失败的情况
    def download_file(self, url, save_path):
        try:
            if self.auth_client.signature is None:
                self.sign_in()
            if self.auth_client.signature is None:
                print("sign_out failed: signature is None")
                return None
            hb_url = url + f"?agent_id={self.agent_id}&signature={self.auth_client.signature}"
            try:
                # 发送 GET 请求下载文件
                response = requests.get(hb_url, verify=False, stream=True)
                response.raise_for_status()  # 检查请求是否成功

                # 打开本地文件以写入二进制数据
                with open(save_path, 'wb') as file:
                    # 逐块写入文件，避免一次性加载大文件到内存
                    for chunk in response.iter_content(chunk_size=16384):
                        if chunk:  # 过滤掉保持活动的新块
                            file.write(chunk)

                print(f"文件下载成功，保存路径: {save_path}")
                return hb_url,save_path
            except requests.RequestException as e:
                print(f"下载文件时发生请求错误: {e}")
                return hb_url,None
            except Exception as e:
                print(f"下载文件时发生未知错误: {e}")
                return hb_url,None
        except Exception as e:
            print(f"download_file in exception: {e}")
        
