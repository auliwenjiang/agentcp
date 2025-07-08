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
import datetime
import hashlib
import os

import requests

from agentcp.base.auth_client import AuthClient
from agentcp.base.client import IClient
from agentcp.base.log import log_debug, log_error, log_exception, log_info

from ..context import ErrorContext, exceptions


class ApClient(IClient):
    def __init__(self, agent_id: str, server_url: str, aid_path: str, seed_password: str):
        self.agent_id = agent_id
        self.heartbeat_server = ""
        self.message_server = ""
        self.server_url = f"{server_url}" + "/api/accesspoint"
        self.auth_client = AuthClient(agent_id, self.server_url, aid_path, seed_password)  # 使用AuthClient

    def initialize(self):
        self.auth_client.sign_in()
        self.get_entrypoint_config()

    def sign_in(self) -> bool:
        return self.auth_client.sign_in() is not None

    def get_headers(self) -> dict:
        return {"User-Agent": f"AgentCP/{__import__('agentcp').__version__} (AuthClient; {self.agent_id})"}

    def sign_out(self):
        """登出方法"""
        self.auth_client.sign_out()

    def post_private_data(self, data):
        try:
            ep_url = self.server_url + "/post_agent_private_data"
            data = {
                "agent_id": f"{self.agent_id}",
                "signature": self.auth_client.signature,
                "data": data,
            }
            response = self.post_request(ep_url, json=data)
            if response.status_code == 200:
                log_info(f"post_private_data ok:{response.json()}")
                return response.json()["data"]
            else:
                log_error(f"post_private_data failed:{response.json()}")
                return None
        except Exception as e:
            log_exception(f"Post private data exception occurred: {e}")
            ErrorContext.publish(exceptions.SDKError(f"Post private data exception occurred: {e}"))
            return None

    def get_all_public_data(self):
        try:
            ep_url = self.server_url + "/get_all_public_data"
            data = {
                "agent_id": f"{self.agent_id}",
                "signature": self.auth_client.signature,
            }
            response = self.post_request(ep_url, json=data)
            if response.status_code == 200:
                return response.json()["data"]
            else:
                log_error(f"get_all_public_data failed:{response.json()}")
                return []
        except Exception as e:
            log_error("get_all_public_data exception:")
            log_exception(e)
            ErrorContext.publish(exceptions.SDKError(f"get_all_public_data exception: {e}"))
            return []

    def get_agent_list(self):
        try:
            ep_url = self.server_url + "/get_agent_list"
            data = {
                "agent_id": f"{self.agent_id}",
                "signature": self.auth_client.signature,
            }
            response = self.post_request(ep_url, json=data)
            if response.status_code == 200:
                log_info(f"get_all_public_data ok:{response.json()}")
                return response.json()["data"]
            else:
                log_error(f"get_all_public_data failed:{response.json()}")
                return None
        except Exception as e:
            log_exception(f"Get all public data exception occurred: {e}")
            ErrorContext.publish(exceptions.SDKError(f"Get all public data exception occurred: {e}"))

    def get_entrypoint_config(self):
        try:
            ep_url = self.server_url + "/get_accesspoint_config"
            log_debug(f"Get server config: {ep_url}")
            data = {
                "agent_id": f"{self.agent_id}",
                "signature": self.auth_client.signature,
            }
            response = self.post_request(ep_url, json=data)
            if response.status_code == 200:
                try:
                    config = response.json()
                    if isinstance(config.get("config"), str):  # 处理config是字符串的情况
                        import json

                        config["config"] = json.loads(config["config"])
                    if "config" in config:
                        if "heartbeat_server" in config["config"]:
                            self.heartbeat_server = config["config"]["heartbeat_server"]
                            log_debug(f"Set heartbeat server to: {self.heartbeat_server}")
                        if "message_server" in config["config"]:
                            self.message_server = config["config"]["message_server"]
                            log_debug(f"Set message server to: {self.message_server}")
                except (ValueError, AttributeError) as e:
                    ErrorContext.publish(exceptions.SDKError(f"处理ap返回的数据出错: {response.text}"))
                    log_exception(f"Failed to parse JSON. Response content: {response.text[:500]}. Error: {e}")
            else:
                log_error(f"Get entrypoint config {ep_url} failed:{response.json()}")

        except Exception as e:
            log_exception(f"Get entrypoint config exception occurred: {e}")
            ErrorContext.publish(exceptions.SDKError(f"Get entrypoint config exception occurred: {e}"))

    def get_agent_profile(self, agentid):
        try:
            url = f"https://{agentid}/agentprofile.json"
            response = self.get_request(url)
            if response.status_code == 200:
                log_debug(f"get_agent_public_data ok:{response.json()}")
                return response.json()
            else:
                log_error(f"get_agent_public_data failed:{response.json()}")
                return None
        except Exception as e:
            log_exception(f"Get agent public data exception occurred: {e}")
            return None

    def get_agent_public_data(self, agentid):
        try:
            ep_url = self.server_url + "/get_agent_public_data"
            data = {
                "agent_id": f"{agentid}",
                "signature": self.auth_client.signature,
            }
            response = self.post_request(ep_url, json=data)
            if response.status_code == 200:
                log_debug(f"get_agent_public_data ok:{response.json()}")
                return response.json()[
                    "data"
                ]  # Return the data if it exists, else return None or handle it as you like
            else:
                log_error(f"get_agent_public_data failed:{response.json()}")
                return None
        except Exception as e:
            log_exception(f"Get agent public data exception occurred: {e}")
            return None

    def get_agent_private_data(self):
        try:
            ep_url = self.server_url + "/get_agent_private_data"
            data = {
                "agent_id": f"{self.agent_id}",
                "signature": self.auth_client.signature,
            }
            response = self.post_request(ep_url, json=data)
            if response.status_code == 200:
                log_debug(f"Get_agent_private_data ok:{response.json()}")
                return response.json()["data"]
            else:
                log_error(f"Get_agent_private_data failed:{response.json()}")
                return None
        except Exception as e:
            log_exception(f"Get agent private data exception occurred: {e}")
            return None

    def get_heartbeat_server(self):
        return self.heartbeat_server

    def get_message_server(self):
        return self.message_server

    def __get_sha256(self, input_str: str) -> str:
        sha256_hash = hashlib.sha256()
        sha256_hash.update(input_str.encode("utf-8"))
        return sha256_hash.hexdigest()

    def __scan_folder(self, folder_path):
        file_list = []
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                relative_file_path = os.path.relpath(os.path.join(root, file), folder_path)
                relative_file_path = relative_file_path.replace("\\", "/")
                file_path = os.path.join(root, file)

                try:
                    file_size = os.path.getsize(file_path)
                    last_modified_utc = datetime.datetime.fromtimestamp(
                        os.path.getmtime(file_path), tz=datetime.timezone.utc
                    )
                    last_modified_ms = int(last_modified_utc.timestamp() * 1000)
                    sha256 = self.__get_sha256(file_path)
                    file_info = {
                        "full_path": relative_file_path,
                        "size": file_size,
                        "last_modified": last_modified_ms,
                        "sha256": sha256,
                    }
                    file_list.append(file_info)
                except Exception as e:
                    import traceback

                    log_error(f"处理文件 {relative_file_path} 时出错，错误信息: {str(e)}")
                    log_error("详细堆栈信息如下：")
                    log_error(traceback.format_exc())
        return file_list

    def sync_public_files(self, file_path) -> bool:
        try:
            files_list = self.__scan_folder(file_path)
            ep_url = self.server_url + "/sync_public_files"
            data = {
                "agent_id": f"{self.agent_id}",
                "signature": self.auth_client.signature,
                "file_list": files_list,
            }
            response = requests.post(ep_url, json=data, verify=False)
            if response.status_code == 200:
                rj = response.json()
                log_info(f"sync_public_files ok:{rj}")
                if "need_upload_files" in rj:
                    need_upload_files = rj["need_upload_files"]
                    for file_name in need_upload_files:
                        params = {
                            "agent_id": self.agent_id,
                            "signature": self.auth_client.signature,
                            "file_name": file_name,
                        }
                        full_path = os.path.join(file_path, file_name)
                        hb_url = self.server_url + "/upload_file"
                        with open(full_path, "rb") as file:
                            files = {"file": file}
                            response = requests.post(hb_url, data=params, files=files, verify=False)
                            if response.status_code == 200:
                                log_info(f"文件{file_name}上传成功 => {response.json()['url']}")
                            else:
                                log_error(f"文件{file_name}上传失败，状态码: {response.status_code}")
                if "need_download_files" in rj:
                    need_download_files = rj["need_download_files"]
                    for file_name in need_download_files:
                        download_url = (
                            self.server_url
                            + "/download_file"
                            + f"?file_name={file_name}&agent_id={self.agent_id}&signature={self.auth_client.signature}"
                        )
                        log_info(f"download_url:{download_url}")
                        try:
                            # 发送 GET 请求下载文件
                            response = requests.get(download_url, verify=False, stream=True)
                            response.raise_for_status()  # 检查请求是否成功
                            # 打开本地文件以写入二进制数据
                            save_path = os.path.join(file_path, file_name)
                            os.makedirs(os.path.dirname(save_path), exist_ok=True)
                            with open(save_path, "wb") as file:
                                # 逐块写入文件，避免一次性加载大文件到内存
                                for chunk in response.iter_content(chunk_size=16384):
                                    if chunk:  # 过滤掉保持活动的新块
                                        file.write(chunk)
                            log_info(f"文件下载成功，保存路径: {save_path}")
                        except requests.RequestException as e:
                            log_error(f"下载文件时发生请求错误: {e}")
                        except Exception as e:
                            log_error(f"下载文件时发生未知错误: {e}")
                return True
            else:
                raise Exception(f"sync_public_files failed:{response.status_code}")
                return False
        except Exception:
            import traceback

            log_error("详细堆栈信息如下：")
            log_error(traceback.format_exc())
            return False

    def delete_public_file(self, file_name: str):
        try:
            ep_url = self.server_url + "/delete_public_file"
            data = {
                "agent_id": f"{self.agent_id}",
                "signature": self.auth_client.signature,
                "file_name": file_name,
            }
            response = requests.post(ep_url, json=data, verify=False)
            if response.status_code == 200:
                log_info(f"delete_public_file ok:{response.json()}")
            else:
                log_error(f"delete_public_file failed:{response.json()}")
        except Exception as e:
            log_exception(f"delete_public_file in exception: {e}")
        pass
