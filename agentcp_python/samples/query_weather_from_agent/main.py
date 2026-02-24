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