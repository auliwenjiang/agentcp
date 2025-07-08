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
from dataclasses import dataclass
from typing import Literal, Optional, Union

from agentcp.msg.open_ai_message import OpenAIMessage


@dataclass
class AgentSelectItemBlock:
    type: Literal["text", "image", "video", "audio"]
    id: str
    content: str


@dataclass
class AgentFormInputItemBlock:
    id: str
    name: str
    description: str


@dataclass
class AgentFormBlock:
    id: str
    description: str
    params: Optional[Union[list[AgentSelectItemBlock], AgentFormInputItemBlock]]
    form_type: Literal["single_select", "multiple_select", "time", "input"] = "single_select"
    result: Optional[str] = ""


@dataclass
class AgentFormItemResultBlock:
    id: str
    result: str


@dataclass
class AgentFormResultBlock:
    result: Optional[list[AgentFormItemResultBlock]] = None


@dataclass
class AgentAddFriendBlock:
    aid: str
    description: str


@dataclass
class AgentFileBlock:
    name: str
    url: str
    content: str
    description: str
    type: str
    encode: str


@dataclass
class AgentCreateOrderBlock:
    total_amount: int
    description: str
    # 发起者aid
    initiator_aid: str
    # 支付人aid，若为空则为发起者支付
    player_aid: str
    # 支付方式，如alipay,wxpay
    payment_method: str
    # 服务周期，单位为秒，如10分钟为600
    service_period: int


@dataclass
class AgentOrderBlock:
    total_amount: int
    description: str
    # 发起者aid
    initiator_aid: str
    # 支付人aid，若为空则为发起者支付
    player_aid: str
    # 支付方式，如alipay,wxpay
    payment_method: str
    # 服务周期，单位为秒，如10分钟为600
    service_period: int
    # 担保方aid
    guarantor_aid: str
    order_no: str
    status: Literal["success", "pending", "failed", "canceled"]
    order_query_url: str
    qr_code_url: str


@dataclass
class AssistantMessageBlock:
    type: Literal[
        "llm",
        "content",
        "search",
        "reasoning_content",
        "error",
        "file",
        "image",
        "tool_call",
        "text/event-stream",
        "video",
        "audio",
        "form",
        "form_result",
        "add_agent",
        "create_order",
        "order",
    ]
    status: Literal["success", "loading", "cancel", "error", "reading", "optimizing"]
    timestamp: int
    block_id: Optional[str] = None
    content: Optional[
        Union[
            str,
            AgentCreateOrderBlock,
            AgentOrderBlock,
            OpenAIMessage,
            AgentFormResultBlock,
            AgentAddFriendBlock,
            AgentFileBlock,
            list[AgentFormBlock],
        ]
    ] = None
    type_format: str = ""
    trace_id: Optional[str] = ""


@dataclass
class AgentInstructionBlock:
    cmd: str
    params: Optional[dict] = None
    description: Optional[str] = None
    model: str = ""
