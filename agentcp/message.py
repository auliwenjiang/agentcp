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