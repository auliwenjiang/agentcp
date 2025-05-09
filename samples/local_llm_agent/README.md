## 使用指南
### 1、环境要求
- Python 3.8+
- [AgentCP SDK](https://pypi.org/project/agentcp/)
- [Ollama](https://ollama.com/)

### 2、环境准备
安装Ollama并下载模型:
#### [Windows](https://ollama.com/download/OllamaSetup.exe)
#### [macOS](https://ollama.com/download/Ollama-darwin.zip)
#### Linux
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### 3、下载模型:
```bash
ollama pull qwen3:0.6b
```

### 4、安装依赖

安装必要的Python库:
```bash
pip install agentcp requests
```
### 5、创建身份ID
```bash
python create_profile.py
```
### 6、修改main.py文件
1. 将seed_password、agent_id修改为上一步创建的身份信息
2. 将model_name修改为你本地使用的model

### 7、执行main.py代码
```bash
python main.py
```
## 功能简介
该Agent基于`agentcp`库构建，实现与本地大模型交互，主要功能包括：

- 接收并处理用户的消息请求
- 转发消息到本地大模型
- 处理本地大模型的响应并返回给原始请求方

## 完整示例代码
```python
import json
import requests
import agentcp
model_name = 'your_local_model'
def chatWithLLM(prompt):
    try:
        response = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": model_name,
                "messages": [
                    {
                        "role": "user", 
                        "content": prompt
                    }],
                "stream": False
            })
        response.encoding = 'utf-8'
        response.raise_for_status()
        result = response.json()
        result = result.get('message')
        result = result.get('content')
        return result
    except requests.exceptions.RequestException as e:
        return "请求失败"
    except json.JSONDecodeError:
        return "响应解析失败"

if __name__ == '__main__':
    agent_id = 'your_agent_id'
    acp = agentcp.AgentCP('.', seed_password='')
    aid = acp.load_aid(agent_id)
    @aid.message_handler()
    async def sync_message_handler(msg):
        content = aid.get_content_from_message(msg)
        session_id = aid.get_session_id_from_message(msg)
        sender = aid.get_sender_from_message(msg)
        res = chatWithLLM(content)
        aid.send_message_content(session_id, [sender], res)
        return True
    aid.online()
    acp.serve_forever()
```