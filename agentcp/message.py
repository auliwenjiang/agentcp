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
from typing import Dict, List, Literal, Optional, Union


@dataclass
class Artifact:
    identifier: str
    title: str
    type: Literal[
        "application/vnd.ant.code",
        "text/markdown",
        "text/html",
        "image/svg+xml",
        "application/vnd.ant.mermaid",
        "application/vnd.ant.react",
    ]
    language: Optional[str] = None

@dataclass
class AssistantMessageBlock:
    type: Literal["content", "search", "reasoning_content", "error", 'file', 'image','tool_call']
    status: Literal["success", "loading", "cancel", "error", "reading", "optimizing"]
    timestamp: int    
    content: Optional[str] = None
    type_format: str = ""
    stream: bool = False
    tools: Optional[List[Dict]] = None
    prompt: Optional[str] = None