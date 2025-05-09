import json
import requests
import agentcp
model_name = 'your_model_name'
def chatWithLLM(prompt):
    try:
        response = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": model_name,
                "messages": [
                    {
                        "role": "system", 
                        "content": 'no_think'
                    },
                    {
                        "role": "system", 
                        "content": '使用中文输出内容'
                    },
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
        import traceback
        print(f"请求失败: {traceback.format_exc()}")
        return "请求失败"
    except json.JSONDecodeError:
        return "响应解析失败"

if __name__ == '__main__':
    agent_id = 'your_agent_id_from_profile'
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
        