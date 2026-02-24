
## 使用指南
### 1、环境要求
- Python 3.8+
- [AgentCP SDK](https://pypi.org/project/agentcp/)
- [Agently SDK](https://pypi.org/project/Agently/) 

### 2、安装依赖
确保安装以下必要库, ✅ 建议使用 python-dotenv 来加载 .env 文件管理密钥和配置。
```bash
pip install agentcp agently python-dotenv
```
### 3、创建身份ID
```bash
python create_profile.py
```
### 4、修改main.py文件
将seed_password、agent_id修改为上一步创建的身份信息

### 5、配置.env文件
创建.env文件并添加以下信息，并替换为您的实际配置：
```json
{
    "OPENAI_API_KEY": "your_api_key",
    "BASE_URL": "https://api.example.com/v1",
    "MODEL": "model_name"
}
```

### 6、执行main.py代码
```bash
python main.py
```

## 功能简介
该 Agent 结合了 `agentcp` 和 `agently` 两个库，具备以下核心能力：

- 接收并处理外部消息请求
- 调用大语言模型生成自然语言响应
- 异步发送处理结果给消息发送者
- 适用于快速构建具备 智能问答能力 的服务型 Agent。

## 完整示例代码
```python
import agentcp
import Agently
import os
from dotenv import load_dotenv
load_dotenv()

if __name__ == "__main__":
    agent_id = 'your_agent_id_from_profile'
    acp = agentcp.AgentCP('.', seed_password='')
    aid = acp.load_aid(agent_id)
    openai_api_key = os.getenv("OPENAI_API_KEY")
    model_url = os.getenv("BASE_URL")
    model_name = os.getenv("MODEL")
    agent = (
        Agently.create_agent()
            .set_settings("current_model", "OAIClient")
            .set_settings("model.OAIClient.auth", {'api_key': openai_api_key})
            .set_settings("model.OAIClient.url", model_url)
            .set_settings("model.OAIClient.options", {'model': model_name})
    )
    
    @aid.message_handler()  #消息处理函数
    async def sync_message_handler(msg):
        receiver = aid.get_receiver_from_message(msg)  # 获取接收者 
        if aid.id not in receiver:
            return
        session_id = aid.get_session_id_from_message(msg)
        sender = aid.get_sender_from_message(msg)  # 获取发送者
        sender_content = aid.get_content_from_message(msg)
        result = (
            agent
                .general("输出规定", "必须使用中文进行输出")
                .role({
                    "姓名": "ACP小助手",
                    "任务": "使用自己的知识为用户解答常见问题",
                })
                .input(sender_content)
                .instruct(["你需要根据用户的问题提供相关的回答", "你可以适当的有点幽默"])
                .start()
        )
        aid.send_message_content(to_aid_list=[sender], session_id=session_id, llm_content=result)
        return True
    aid.online()
    acp.serve_forever()
```