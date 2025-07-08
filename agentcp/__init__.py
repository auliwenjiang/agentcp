# 移除或注释掉原来的导入
#: code: utf-8

from requests.packages import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from agentcp.agentcp import AgentCP, AgentID
from agentcp.mermaid import Mermaid
from agentcp.workflow import Workflow

__version__ = "0.1.90"

__all__ = ["__version__", "AgentCP", "AgentID","Mermaid","Workflow"]