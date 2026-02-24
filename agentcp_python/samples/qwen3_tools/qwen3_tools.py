# -*- coding:utf-8 -*-
"""
基础配置:
qwen3大模型function calling使用,输入字符串,输出字符串
https://img.alicdn.com/imgextra/i2/O1CN01kvilTK1hZKZPhDDvY_!!6000000004291-2-tps-269-282.png
"""
import agentcp
import os
import json
from openai import OpenAI
from dotenv import load_dotenv, find_dotenv

# 加载并读取环境变量
load_dotenv(find_dotenv())
base_url = os.getenv('BASE_URL')
openai_api_key = os.getenv('OPENAI_API_KEY')
model_name = os.getenv('MODEL_NAME')


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


if __name__ == "__main__":
    acp = agentcp.AgentCP(os.path.pardir, seed_password='123456', debug=True)
    print(f"当前acp访问路径:{acp.app_path}\n开始:agentcp版本:{agentcp.__version__},{__file__}")
    aid = acp.load_aid(os.getenv('AID'))

    @aid.message_handler()
    async def sync_message_handler(msg):
        print(f'收到消息数据: {msg}')
        # 大模型对话
        response = chat_tools(query=aid.get_content_from_message(msg))
        # 消息回复
        aid.send_message_content(aid.get_session_id_from_message(msg), [aid.get_sender_from_message(msg)], response)
        return True

    # agent上线
    aid.online()
    # 开启永久监听
    acp.serve_forever()