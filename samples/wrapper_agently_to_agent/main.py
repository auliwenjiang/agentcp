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