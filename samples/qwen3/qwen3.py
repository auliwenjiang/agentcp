# -*- coding:utf-8 -*-
"""
基础配置:
qwen3大模型流式输出对话:输入字符串,输出字符串
https://img.alicdn.com/imgextra/i2/O1CN01kvilTK1hZKZPhDDvY_!!6000000004291-2-tps-269-282.png
"""

import agentcp
import os
from openai import OpenAI
from dotenv import load_dotenv, find_dotenv

# 加载并读取环境变量
load_dotenv(find_dotenv())
base_url = os.getenv('BASE_URL')
openai_api_key = os.getenv('OPENAI_API_KEY')
model_name = os.getenv('MODEL_NAME')

if __name__ == "__main__":
    acp = agentcp.AgentCP(os.path.pardir, seed_password='123456', debug=True)
    print(f"当前acp访问路径:{acp.app_path}\n开始:agentcp版本:{agentcp.__version__},{__file__}")
    aid = acp.load_aid(os.getenv('AID'))

    @aid.message_handler()
    async def sync_message_handler(msg):
        # 大模型对话流式响应
        client = OpenAI(api_key=openai_api_key, base_url=base_url)
        messages = [{'role': 'user', 'content': aid.get_content_from_message(msg)}]
        response = client.chat.completions.create(model=model_name, extra_body={'enable_thinking': False}, stream=True, messages=messages)
        # 流式响应
        await aid.send_stream_message(aid.get_session_id_from_message(msg), [aid.get_sender_from_message(msg)], response)
        return True

    # agent上线
    aid.online()
    # 开启永久监听
    acp.serve_forever()