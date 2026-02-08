## 使用指南
### 1、环境要求
- Python 3.8+
- [AgentCP SDK](https://pypi.org/project/agentcp/)

### 2、安装依赖

安装必要的Python库:
```bash
pip install agentcp
```
### 3、创建身份ID
```bash
python create_profile.py
```
### 4、修改main.py文件
1. 将seed_password、agent_id修改为上一步创建的身份信息
2. 将 llm_agent_id修改为你想要调用的[agent_id](https://www.agentunion.cn/)

### 5、执行main.py代码
```bash
python main.py
```

## 功能简介
该 Agent 展示了如何基于 `agentcp` 实现一个天气查询服务 Agent。你可以通过本地 Agent 与大模型 Agent 进行通信，从而实现函数调用能力，例如获取天气信息。

- 接收并处理用户的消息请求
- 转发查询请求到目标大模型 Agent
- 自动调用工具函数（如 get_weather）并返回结果
- 处理大模型 Agent 的回复并返回给用户

## 完整示例代码
```python
import agentcp
import json
import time
tools=[{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Retrieves the current weather report for a specified city",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "The name of the city for which to retrieve the weather report"
                }
            },
            "required": ["city"]
        }
    }
}]
def get_weather(city: str) -> str:
    return f"{city}的天气是晴朗，温度适宜，20~30度"

def call_function(name, args):
    if name == "get_weather":
        return get_weather(**args)
    else:
        return f"Function {name} not found"

if __name__ == "__main__":
    llm_agent_id = "your_llm_agent_id_from_mu"
    agent_id = 'your_agent_id_from_profile'
    acp = agentcp.AgentCP('.', seed_password='')
    aid = acp.load_aid(agent_id)
    async def reply_message_handler(reply_msg, sender, session_id):
        message_json = json.loads(reply_msg.get("message"))
        if isinstance(message_json, list) and len(message_json) > 0:
            message_json = message_json[0]
        type = message_json.get("type")
        if type == "tool_call":
            tool = json.loads(message_json.get("content"))
            tool_name = tool.get("tool_name")
            tool_args = tool.get("tool_args")
            tool_result = call_function(tool_name, tool_args)
            aid.quick_send_messsage_content(llm_agent_id, tool_result, lambda reply_msg: reply_message_handler(reply_msg, sender, session_id))
        else:
            reply_text = aid.get_content_from_message(reply_msg)
            aid.send_message_content(to_aid_list=[sender], session_id=session_id, llm_content=reply_text)
    
    @aid.message_handler()
    async def sync_message_handler(msg):
        receiver = aid.get_receiver_from_message(msg)
        if aid.id not in receiver:
            return
        session_id = aid.get_session_id_from_message(msg)
        sender = aid.get_sender_from_message(msg)
        sender_content = aid.get_content_from_message(msg)
        msg_block = {
            "type": "content",
            "status": "success",
            "timestamp": int(time.time() * 1000),
            "content": sender_content,
            "tools": tools
        }
        aid.quick_send_messsage(llm_agent_id, msg_block, lambda reply_msg: reply_message_handler(reply_msg, sender, session_id))
        return True
    aid.online()
    acp.serve_forever()
```