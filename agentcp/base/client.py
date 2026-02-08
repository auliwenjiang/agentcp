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
import abc
import requests

from agentcp.base.log import log_error, log_info


class IClient(abc.ABC):
    @abc.abstractmethod
    def sign_in(self) -> bool:
        pass
    
    @abc.abstractmethod
    def get_headers(self) -> dict:
        pass
    
    @abc.abstractmethod
    def sign_out(self):
        pass


    def get_request(self,url: str, params: dict = None, headers: dict = None,is_retry=True) -> requests.Response:
        """
        发送GET请求的通用方法   
        Args:
            url (str): 请求的URL
            params (dict, optional): 请求参数. Defaults to None.
            headers (dict, optional): 请求头. Defaults to None. 
        Returns:
            requests.Response: 响应对象
        """
        try:
            common_headers = self.get_headers()
            if headers:
                common_headers = {**common_headers, **headers}
            response = requests.get(url, params=params, headers=common_headers,verify=False)
            response.raise_for_status()
            if response.status_code == 200:
                return response
            else:
                error = response.json().get("error", "")
                log_error(f"请求失败，错误详情: {error}")
                if response.status_code == 401 and is_retry:
                    log_info("尝试重新登录...")
                    if self.sign_in():
                        return self.get_request(url, params=params, headers=common_headers, is_retry=False)
                return response
        except requests.exceptions.RequestException as e:
            log_error(f"请求失败: {e}")
            return None


    def post_request(self, url: str, data: dict = None, json: dict = None, headers: dict = None, is_retry=True) -> requests.Response:
        """
        发送POST请求的通用方法
    
        Args:
            url (str): 请求的URL
            data (dict, optional): 表单数据. Defaults to None.
            json (dict, optional): JSON数据. Defaults to None.
            headers (dict, optional): 请求头. Defaults to None.
            is_retry (bool, optional): 是否重试. Defaults to True.
        Returns:
            requests.Response: 响应对象
        """
        try:
            common_headers = self.get_headers()
            if headers:
                common_headers = {**common_headers, **headers}
            response = requests.post(url, data=data, json=json, headers=common_headers, verify=False)
            if response.status_code == 200:
                return response
            else:
                error = response.json().get("error", "")
                log_error(f"请求失败，错误详情: {error}")
                if response.status_code == 401 and is_retry:
                    log_info("尝试重新登录...")
                    if self.sign_in():
                        return self.post_request(url, data=data, json=json, headers=common_headers, is_retry=False)
            return response
        except requests.exceptions.RequestException as e:
            log_error(f"请求失败: {e}")
            raise
    
    
