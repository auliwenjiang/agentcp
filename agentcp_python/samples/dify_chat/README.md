# github
[https://github.com/auliwenjiang/agentcp/blob/master/samples/dify_chat](https://github.com/auliwenjiang/agentcp/blob/master/samples/dify_chat)

# README.md

## 1、使用指南
### 1)、创建agent身份
请参考[一、创建身份，读写公有私有数据](https://ccnz88r91l2y.feishu.cn/wiki/I5F4whGuFioqwNkfJ45c8ZQ3nGf)
- 运行create_profile.py,创建agent

### 2)、添加并配置.env文件
``` bash
BASE_URL=http://your_host/v1/chat-messages # 改成实际url
API_KEY=app-1qMAqDifpRiOsnNR7mYOM3uv # 改成实际api key
AID=difychatdemo.agentunion.cn # 改成自己实际注册aid
```

### 3)、目录结构
```bash
.
├── create_profile.py  # agent注册脚本
├── .env   # 环境变量配置
├── dify_chat.py  # 智能体实现
```
### 4)、执行代码
```bash
python dify_chat.py
```

## 2、功能简介
基于AgentCP SDK开发的dify chat智能体，实现dify chat能力与智能体网络的无缝对接。使网络中的其他智能体可以通过调用该智能体的API来获取dify chat的响应。

## 3、环境要求
- Python 3.8+
- AgentCP SDK

## 4、核心类说明
### 1）、agent上线
```python
acp = agentcp.AgentCP(os.path.pardir, debug=True)
print(f"当前acp访问路径:{acp.app_path}\n开始:agentcp版本:{agentcp.__version__},{__file__}")
aid = acp.load_aid(os.getenv('AID'))

# agent上线
aid.online()

# 开启永久监听
acp.serve_forever()
```
### 2）、消息处理
```python
@aid.message_handler()
async def sync_message_handler(msg):
    # 大模型对话
    response = dify_chat_client(query=aid.get_content_from_message(msg))
    # 消息回复
    aid.send_message_content(aid.get_session_id_from_message(msg), [aid.get_sender_from_message(msg)], response)
    return True
```
### 3）、dify调用
```python
def dify_chat_client(query: str)-> str:
    """ dify chat 客户端"""
    headers = { 'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json; charset=utf-8'}
    data = json.dumps({'inputs': {} ,'query': query, 'conversation_id': '', 'user': os.getenv('AID')}, ensure_ascii=False).encode('utf-8')
    response = requests.post(base_url, headers=headers, data=data, stream=False)
    print(f'dify response = {response}')
    if response.status_code != 200:
        return f'请求失败：{response.text}'
    result = json.loads(response.text)['answer']
    print(f'difychat回复[query = {query}]：response = {result}')
    return result
```

## 注意事项
1. dify环境变量正确配置
2. 智能体网络接入需要有效的seed_password
3. 生产环境建议关闭debug模式