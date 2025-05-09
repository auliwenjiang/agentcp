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
2. 将 to_agent_id 修改为你想要调用的[agent_id](https://www.agentunion.cn/)

### 5、执行main.py代码
```bash
python main.py
```

## 功能简介
该Agent基于`agentcp`库构建，实现了一个天气查询的中转代理 Agent，可接收用户请求并将其转发给下游天气查询 Agent，最终将结果返回用户。

- 接收并处理用户的消息请求
- 转发查询请求到目标Agent
- 处理目标Agent的响应并返回给原始请求方

## 完整示例代码
```python
import agentcp
if __name__ == "__main__":
    to_agent_id = "your_llm_agent_id_from_mu"
    agent_id = 'your_agent_id_from_profile'
    acp = agentcp.AgentCP('.', seed_password='')
    aid = acp.load_aid(agent_id)

    #其它agent返回消息处理函数
    async def reply_message_handler(reply_msg, sender, session_id):
        reply_text = aid.get_content_from_message(reply_msg)
        aid.send_message_content(to_aid_list=[sender], session_id=session_id, llm_content=reply_text)

    @aid.message_handler()  #消息处理函数
    async def sync_message_handler(msg):
        receiver = aid.get_receiver_from_message(msg)  # 获取接收者 
        if aid.id not in receiver:
            return
        session_id = aid.get_session_id_from_message(msg)
        sender = aid.get_sender_from_message(msg)  # 获取发送者
        sender_content = aid.get_content_from_message(msg)
        aid.quick_send_messsage_content(to_agent_id, sender_content, lambda reply_msg: reply_message_handler(reply_msg, sender, session_id))
        return True
    aid.online()
    acp.serve_forever()
```