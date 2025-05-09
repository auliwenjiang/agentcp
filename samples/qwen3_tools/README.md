# github
[https://github.com/auliwenjiang/agentcp/blob/master/samples/qwen3_tools](https://github.com/auliwenjiang/agentcp/blob/master/samples/qwen3_tools)

# README.md

## 1、使用指南
### 1)、创建agent身份
请参考[一、创建身份，读写公有私有数据](https://ccnz88r91l2y.feishu.cn/wiki/I5F4whGuFioqwNkfJ45c8ZQ3nGf)
- 运行create_profile.py,创建agent

### 2)、添加并配置.env文件
``` bash
BASE_URL=https://api.siliconflow.cn/v1 # 改成实际url
OPENAI_API_KEY=sk-*********** # 改成实际api key
MODEL_NAME=Qwen/Qwen3-8B  # 改成实际大模型
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
├── qwen3_tools.py  # 智能体实现
```
### 5)、执行代码
```bash
python qwen3_tools.py
```

## 2、功能简介
基于AgentCP SDK开发的qwen3大模型function calling智能体，实现大模型能力与智能体网络的无缝对接。使网络中的其他智能体可以通过调用该智能体的API来获取大模型的响应。

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
    print(f'收到消息数据: {msg}')
    # 大模型对话
    response = chat_tools(query=aid.get_content_from_message(msg))
    # 消息回复
    aid.send_message_content(aid.get_session_id_from_message(msg), [aid.get_sender_from_message(msg)], response)
    return True
```

### 3）、fuction calling实现
```python
# 工具清单
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "获取城市天气信息",
            "parameters": {"type": "object", "properties": {"location": {"type": "string"}, "dt": {"type": "string"}}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_news",
            "description": "搜索指定主题新闻",
            "parameters": {"type": "object", "properties": {"keyword": {"type": "string"}}}
        }
    }
]

# 定义本地函数（模拟天气API）
def get_weather(location: str, dt: str):
    """模拟天气查询功能"""
    return f'{location}{dt}天气：25℃,晴朗'

# 定义本地函数（模拟天气API）
def search_news(keyword: str):
    """模拟天气查询功能"""
    return f'{keyword}最新消息'


def chat_tools(query: str):
    print('-' * 60)
    # 发起请求并处理响应
    messages = [{'role': 'user', 'content': query},
                {'role': 'system', 'content': '你是一个工具调用助手，需要一次性返回所有工具'}]
    client = OpenAI(api_key=openai_api_key, base_url=base_url)
    response = client.chat.completions.create(model=model_name, messages=messages, tools=tools, tool_choice='auto',
                                              temperature=0.3)
    # 大模型返回解析
    try:
        message = response.choices[0].message
        # 工具不存在直接返回
        if not hasattr(message, 'tool_calls') or not message.tool_calls:
            return message.content

        # 处理工具
        results = []
        for tool_call in message.tool_calls:
            name, args0 = tool_call.function.name, tool_call.function.arguments
            # 兼容{'location': '上海'} 和 '{"location": "上海"}'格式
            args = json.loads(args0) if isinstance(args0, str) else args0
            result = get_weather(**args) if name == 'get_weather' else search_news(**args)
            info = f'函数={name}, args={args}, 调用结果:{result}'
            results.append(info)
        return ';'.join(results)
    except Exception as e:
        print(f'llm response parse err:{e}')
        return '大模型返回解析失败'
```

## 注意事项
1. 大模型环境变量正确配置
2. 智能体网络接入需要有效的seed_password
3. 生产环境建议关闭debug模式