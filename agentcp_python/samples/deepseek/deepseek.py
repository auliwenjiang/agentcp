# -*- coding:utf-8 -*-
"""
deepseek大模型对话:输入字符串,输出字符串
https://resouces.modelscope.cn/avatar/6c8d6d52-b760-4538-9b32-35dd5ebecc68.jpg
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

def llm_chat(query: str) -> str:
    """ 基于openai的大模型调用 """
    client = OpenAI(api_key=openai_api_key, base_url=base_url)
    response = client.chat.completions.create(model=model_name, messages=[{'role': 'user', 'content': query}])
    result = response.choices[0].message.content
    print(f'大模型[{model_name}]回复[query = {query}]：response = {result}')
    return result

if __name__ == "__main__":
    acp = agentcp.AgentCP(os.path.pardir, seed_password='123456', debug=True)
    print(f"当前acp访问路径:{acp.app_path}\n开始:agentcp版本:{agentcp.__version__},{__file__}")
    aid = acp.load_aid(os.getenv('AID'))

    @aid.message_handler()
    async def sync_message_handler(msg):
        # 大模型对话
        response = llm_chat(query=aid.get_content_from_message(msg))
        # 消息回复
        aid.send_message_content(aid.get_session_id_from_message(msg), [aid.get_sender_from_message(msg)], response)
        return True

    # agent上线
    aid.online()

    # 开启永久监听
    acp.serve_forever()