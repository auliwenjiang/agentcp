# github
[https://github.com/auliwenjiang/agentcp/blob/master/samples/deepseek](https://github.com/auliwenjiang/agentcp/blob/master/samples/deepseek)

# README.md

## 1、使用指南
### 1)、创建agent身份
请参考[一、创建身份，读写公有私有数据](https://ccnz88r91l2y.feishu.cn/wiki/I5F4whGuFioqwNkfJ45c8ZQ3nGf)
- 运行create_profile.py,创建agent

### 2)、添加并配置.env文件
``` bash
BASE_URL=https://api.siliconflow.cn/v1 # 改成实际url
OPENAI_API_KEY=sk-*********** # 改成实际api key
MODEL_NAME=deepseek-ai/DeepSeek-R1-Distill-Qwen-7B  # 改成实际大模型
AID=deepseekdemo.agentunion.cn # 改成自己实际注册aid
```
### 3）、添加依赖
``` bash
pip install openai==1.77.0 -i https://pypi.tuna.tsinghua.edu.cn/simple/
```
### 4)、目录结构
```bash
.
├── create_profile.py  # agent注册脚本
├── .env   # 环境变量配置
├── deeepseek.py  # 智能体实现
```
### 5)、执行代码
```bash
python deepseek.py
```

## 2、功能简介
基于AgentCP SDK开发的deepseek大模型智能体，实现大模型能力与智能体网络的无缝对接。使网络中的其他智能体可以通过调用该智能体的API来获取大模型的响应。

## 3、环境要求
- Python 3.8+
- AgentCP SDK
- OpenAI兼容API服务

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
    response = llm_chat(query=aid.get_content_from_message(msg))
    # 消息回复
    aid.send_message_content(aid.get_session_id_from_message(msg), [aid.get_sender_from_message(msg)], response)
    return True
```
### 3）、大模型调用
```python
def llm_chat(query: str) -> str:
    """ 基于openai的大模型调用 """
    client = OpenAI(api_key=openai_api_key, base_url=base_url)
    response = client.chat.completions.create(model=model_name, messages=[{'role': 'user', 'content': query}])
    result = response.choices[0].message.content
    print(f'大模型[{model_name}]回复[query = {query}]：response = {result}')
    return result
```

## 注意事项
1. 大模型环境变量正确配置
2. 智能体网络接入需要有效的seed_password
3. 生产环境建议关闭debug模式