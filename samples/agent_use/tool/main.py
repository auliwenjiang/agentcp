import agentcp

if __name__ == "__main__":
    acp = agentcp.AgentCP("../../../../data")
    _my_aid = "testdemo11.agentunion.cn"
    aid = acp.load_aid(_my_aid)
    @aid.message_handler()
    async def sync_message_handler(msg):
        receiver = aid.get_receiver_from_message(msg)
        if aid.id not in receiver:
            return None
        session_id = aid.get_session_id_from_message(msg)
        sender = aid.get_sender_from_message(msg)
        content = "我是天气Agent，今天气温39摄氏度，晴天"
        aid.send_message_content(session_id, [sender], content)
        return True
    aid.online()
    # aid.sync_public_files()
    print("已上线完成")
    acp.serve_forever()