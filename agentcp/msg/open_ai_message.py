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
from typing import Dict, List, Union, Iterable, Optional
from openai._types import NOT_GIVEN, Body, Query, Headers, NotGiven
from openai.types.shared.chat_model import ChatModel
from openai.types.chat.chat_completion import ChatCompletion
from openai.types.shared_params.metadata import Metadata
from openai.types.shared.reasoning_effort import ReasoningEffort
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from openai.types.chat.chat_completion_deleted import ChatCompletionDeleted
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from openai.types.chat.chat_completion_audio_param import ChatCompletionAudioParam
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam
from openai.types.chat.chat_completion_stream_options_param import ChatCompletionStreamOptionsParam
from openai.types.chat.chat_completion_prediction_content_param import ChatCompletionPredictionContentParam
from openai.types.chat.chat_completion_tool_choice_option_param import ChatCompletionToolChoiceOptionParam
from openai.types.chat import (
    ChatCompletionAudioParam,
    completion_list_params,
    completion_create_params,
    completion_update_params,
)
from typing_extensions import Literal, overload

class OpenAIMessage:    
    def __init__(self):
        self.messages :  Iterable[ChatCompletionMessageParam] = None
        self.model: Union[str, ChatModel] = None
        self.audio: Optional[ChatCompletionAudioParam] = None
        self.frequency_penalty: Optional[float] = None
        self.function_call: completion_create_params.FunctionCall = None
        self.functions: Iterable[completion_create_params.Function] = None
        self.logit_bias: Optional[Dict[str, int]] = None
        self.logprobs: Optional[bool] = None
        self.max_completion_tokens: Optional[int] = None
        self.max_tokens: Optional[int] = None
        self.metadata: Optional[Metadata] = None
        self.modalities: Optional[List[Literal["text", "audio"]]] = None
        self.n: Optional[int] = None
        self.parallel_tool_calls = None
        self.prediction: Optional[ChatCompletionPredictionContentParam] = None
        self.presence_penalty: Optional[float] = None
        self.reasoning_effort: Optional[ReasoningEffort] = None
        self.response_format: completion_create_params.ResponseFormat  = None
        self.seed: Optional[int]  = None
        self.service_tier: Optional[Literal["auto", "default"]]  = None
        self.stop: Union[Optional[str], List[str], None] = None
        self.store: Optional[bool] = None
        self.stream: Optional[Literal[False]] = None
        self.stream_options: Optional[ChatCompletionStreamOptionsParam]  = None
        self.temperature: Optional[float] = None
        self.tool_choice: ChatCompletionToolChoiceOptionParam = None
        self.tools: Iterable[ChatCompletionToolParam] = None
        self.top_logprobs: Optional[int]  = None
        self.top_p: Optional[float]  = None
        self.user: str  = None
        self.web_search_options: completion_create_params.WebSearchOptions = None
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        self.extra_headers: Headers  = None
        self.extra_query: Query  = None
        self.extra_body: Body  = None
        self.timeout: float  = 100
    
    def to_json(self) -> str:
        """将对象序列化为JSON字符串，自动跳过None值"""
        data = {
            key: value 
            for key, value in self.__dict__.items()
            if value is not None and not key.startswith('_')
        }
        return json.dumps(data, 
                         default=lambda o: o.__dict__, 
                         ensure_ascii=False, 
                         separators=(',', ':'))