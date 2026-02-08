# -*- coding:utf-8 -*-
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
import time
import traceback
import urllib.parse

import requests
from flask import Response

from agentcp.base.log import log_error, log_exception, log_info


class AttrDict(dict):
    """使用属性方式读取字典兼容 openai响应格式"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 递归转换所有字典类型子项
        for key, value in self.items():
            if isinstance(value, dict):
                self[key] = AttrDict(value)
            elif isinstance(value, list):
                self[key] = [AttrDict(v) if isinstance(v, dict) else v for v in value]

    def __getattr__(self, key):
        if key in self:
            return self[key]
        raise AttributeError(f"{self.__class__.__name__}对象无属性{key}")

    def model_dump(self, exclude_none: bool = True, **kwargs) -> dict:
        """兼容openai响应的 model_dump"""

        def _serialize(obj):
            if isinstance(obj, AttrDict):
                return {k: _serialize(v) for k, v in obj.items() if not (exclude_none and v is None)}
            elif isinstance(obj, list):
                return [_serialize(item) for item in obj]
            else:
                return obj

        return _serialize(self)


def format_date() -> str:
    """获取当前格式化时间"""
    ts = time.time()
    # 格式化输出（带毫秒）
    formatted_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
    millis = int(ts * 1000) % 1000
    return f"{formatted_time}.{millis:03d}"


def get_message_type(messages: list) -> str:
    """获取消息类型"""
    if len(messages) > 0:
        msg = messages[0]
        msg_type = msg.get("type")
        return msg_type
    return None


def parse_stream_url(url0: str) -> tuple:
    """
    解析消息中流地址
    如:
    https://ts.agentunion.cn/api/text_stream/pull_text_stream?session_id=1831992075507204096&message_id=6
    解析出独立的url和参数字典
    """
    args = {}
    array = url0.split("?")
    if len(array) != 2:
        return url0, args
    url, args_str = array
    for kv in args_str.split("&"):
        arr = kv.split("=")
        if len(arr) != 2:
            continue
        args[arr[0]] = arr[1]
    return url, args


def get_vaild_json(text):
    try:
        json_data = json.loads(text)
        return json_data
    except Exception:
        return None


def fail_response(content) -> AttrDict:
    # 构造失败默认结果(是否流式只是delta和message的区别)
    return AttrDict(
        {
            "status": "error",
            "code": 400,
            "message": content,
        }
    )


class LLMAgent:
    def __init__(self, llm_agent, aid):
        self.llm_agent_name = llm_agent  # 大模型agent名称
        self.aid = aid  # 当前agent主体
        self.msg = None  # 当前agent主体
        self.result = None
        self.session_id = None  # 当前会话id
        self.result_type = (
            None  # 结果类型，如text, image, audio, video, file, form, add_friend, create_order, error, empt
        )

    async def chat_create(self, open_ai_message_body, trace_id: str = ""):
        """大模型agent对话"""
        # 结果值为空
        self.result = AttrDict({})
        llm_message = {
            "type": "llm",
            "status": "success",
            "timestamp": int(time.time() * 1000),
            "content": open_ai_message_body,
            "trace_id": trace_id,
        }

        # 3、发送消息并异步接收结果
        async def reply_message_handler(reply_msg):
            try:
                # 解析大模型返回结果
                msg_type, response = self.parse_message(reply_msg=reply_msg)
                log_info(
                    f"[{format_date()}]: llm agent message parse result msg_type = {msg_type}, response = {response}"
                )
                self.result_type = msg_type
                if msg_type == "error":
                    self.result = fail_response(response)
                else:
                    self.result = response
            except Exception as e:
                self.result = fail_response(f"消息解析失败{str(e)}")
                self.result_type = "error"
            self.session_id = reply_msg.get("session_id", "")

        try:
            # 3-1、向大模型agent发送消息
            if self.session_id is None:
                self.aid.quick_send_message(
                    self.llm_agent_name, llm_message, lambda reply_msg: reply_message_handler(reply_msg)
                )
            else:
                self.aid.add_message_handler(reply_message_handler, session_id=self.session_id)
                self.aid.send_message(self.session_id, [self.llm_agent_name], llm_message)
            # 3-2、异步等待结果（带超时）
            # 4-2、轮询解析结果(最长等待12秒)
            timeout = 60
            start_time = time.time()
            while len(self.result) == 0:
                # log_info(f'reply_result = {self.result[1]}')
                await asyncio.sleep(0.1)  # 每0.1s检查一次
                if time.time() - start_time > timeout:
                    return fail_response(f"消息读取超时{self.session_id}")
            # 流式响应
            if self.result_type == "text/event-stream":
                return self.read_stream(self.result)
        except Exception as e:
            log_exception(f"{format_date()}消息处理异常: {str(e)}")
            traceback.format_exc()
            return fail_response(f"消息处理异常{str(e)}")
        return self.result

    def read_stream(self, content):
        url = ""
        try:
            # 增加URL参数验证
            url = content + "&agent_id=" + self.aid.id
            target_response = requests.get(url, stream=True, verify=False, timeout=(5, 30))  # 连接超时5秒，读取超时30秒

            def generate():
                try:
                    for line in target_response.iter_lines():
                        if line:
                            # 检查是否为合法 SSE 格式（避免污染数据流）
                            chunk = urllib.parse.unquote_plus(line.decode("utf-8"))
                            # chunk = get_vaild_json(decoded_url)
                            key, value = chunk.split(":", 1)
                            key = key.strip()
                            value = value.strip()
                            if key == "event" and value == "done":
                                break
                                # yield f"event: done\n\n".encode('utf-8')
                            else:
                                json_data = get_vaild_json(value)
                                if json_data is None:
                                    continue
                                # print(f"[llm agent message] {json_data}")
                                yield f"data: {json.dumps(json_data)}\n\n".encode("utf-8")
                except requests.exceptions.Timeout:
                    # 返回超时错误（SSE 格式）
                    error_msg = {"status": "error", "message": json.dumps({"error": "目标服务器响应超时"})}
                    yield f"data: {error_msg}\n\n".encode("utf-8")  # 编码为字节流
                except requests.exceptions.RequestException as e:
                    # 返回其他请求错误（SSE 格式）
                    error_msg = {"status": "error", "message": json.dumps({"error": f"目标服务器请求失败: {str(e)}"})}
                    yield f"data: {error_msg}\n\n".encode("utf-8")  # 编码为字节流
                except Exception as e:
                    # 捕获其他异常并返回错误（SSE 格式）
                    error_msg = {"status": "error", "message": json.dumps({"error": f"处理过程中发生错误: {str(e)}"})}
                    yield f"data: {error_msg}\n\n".encode("utf-8")

            # 返回流式响应
            return Response(generate(), content_type="text/event-stream", status=target_response.status_code)
        except requests.exceptions.Timeout:
            log_error(f"请求超时: {url}")
            return fail_response("流连接超时")
        except requests.exceptions.RequestException as e:
            log_error(f"{format_date()}连接异常: {str(e)}")
            traceback.format_exc()
            return fail_response("连接异常")

    def parse_message(self, reply_msg) -> tuple:
        """解析llm agent消息结果"""
        # 读取消息中的llm响应体
        msg_type = get_message_type(messages=self.aid.get_content_array_from_message(reply_msg))
        content = self.aid.get_content_from_message(reply_msg, message_type=msg_type)
        if msg_type == "error":
            return msg_type, content

        if msg_type == "text/event-stream":
            return msg_type, content

        # 解析大模型返回
        content_dict = json.loads(content)
        return msg_type, AttrDict(content_dict)
