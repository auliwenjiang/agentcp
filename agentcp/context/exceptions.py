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


import platform as plt


class SDKError(Exception):
    code = 1000
    trace_id = ""
    agent_id = ""
    platform = plt.version()
    py_version = plt.python_version()  # type: ignore

    def __init__(self, message, trace_id=""):
        super().__init__(message)
        self.trace_id = trace_id
        import agentcp

        self.sdk_version = f"agentcp/{agentcp.__version__}"

    def to_dict(self):
        return {
            "code": self.code,
            "trace_id": self.trace_id,
            "message": str(self),
            "agent_id": self.agent_id,
            "platform": self.platform,
            "py_version": self.py_version,
            "sdk_version": self.sdk_version,
        }


class LLMFlowError(SDKError):
    """调用 LLM 出错"""

    code = 1001


class CallLLMError(LLMFlowError):
    """调用 LLM 出错"""

    code = 1002


class CreateSessionError(LLMFlowError):
    """创建会话请求或响应出错"""

    code = 1003


class InviteMemberError(LLMFlowError):
    """邀请成员请求或响应出错"""

    code = 1005


class JoinSessionError(LLMFlowError):
    """加入会话请求或响应出错"""

    code = 1007


class SendMsgError(LLMFlowError):
    """发送消息出错"""

    code = 1009


class CreateStreamError(LLMFlowError):
    """创建流式通道请求或响应出错"""

    code = 1010


class StreamUrlNotifyError(LLMFlowError):
    """通知流地址出错"""

    code = 1012


class PullStreamError(LLMFlowError):
    """拉取流内容出错"""

    code = 1013


class SendChunkToStreamError(LLMFlowError):
    """向流中发送内容块出错"""

    code = 1014


class ChunksBySSEError(LLMFlowError):
    """通过 SSE 发送内容块出错"""

    code = 1015


class CloseStreamError(LLMFlowError):
    """关闭流式通道出错"""

    code = 1016
