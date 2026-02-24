# -*- coding:utf-8 -*-
"""
基础配置:
SSE模式接入dify的chat:输入字符串,输出字符串
https://tse3-mm.cn.bing.net/th/id/OIP-C.Hux_MNYiHtMI5EnBzSIubAAAAA?rs=1&pid=ImgDetMain
"""
import agentcp
import os
import json
import requests
from dotenv import load_dotenv, find_dotenv

# 加载并读取环境变量
load_dotenv(find_dotenv())
base_url = os.getenv('BASE_URL')
api_key = os.getenv('API_KEY')


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

if __name__ == "__main__":
    acp = agentcp.AgentCP(os.path.pardir, seed_password='123456', debug=True)
    print(f"当前acp访问路径:{acp.app_path}\n开始:agentcp版本:{agentcp.__version__},{__file__}")
    aid = acp.load_aid(os.getenv('AID'))

    @aid.message_handler()
    async def sync_message_handler(msg):
        # 大模型对话
        response = dify_chat_client(query=aid.get_content_from_message(msg))
        # 消息回复
        aid.send_message_content(aid.get_session_id_from_message(msg), [aid.get_sender_from_message(msg)], response)
        return True

    # agent上线
    aid.online()
    # 开启永久监听
    acp.serve_forever()