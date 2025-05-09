import json
import time
import traceback

import agentcp

"""
智能体搜索 使用大模型agent实现工具选择 多工具并行调用
"""
class Agent:
    def __init__(self):
        self.agentid = None
        self.acp = agentcp.AgentCP("../data")
        self.llm_agent_id = "lwj9999.agentunion.cn"
    async def async_message_handler(self, msg):
        try:
            receiver = self.agentid.get_receiver_from_message(msg)
            if self.agentid.id not in receiver:
                print("不是发给我的消息，不处理")
                return
            sender = self.agentid.get_sender_from_message(msg)
            session_id = self.agentid.get_session_id_from_message(msg)
            to_aid_list = [sender]

            # 获取输入
            llm_content = self.agentid.get_content_from_message(msg)
            print(f"llm_content={llm_content}\n")

            # 调用工具选择agent
            self.mult_tool_choose(llm_content,session_id,to_aid_list)
        except Exception as e:
            print(f"处理消息时发生错误: {e}\n完整堆栈跟踪:\n{traceback.format_exc()}")

    async def reply_message_handler(self,reply_msg,session_id,to_aid_list):
        content = []
        print(f"模型返回结果{reply_msg}")
        message_json = json.loads(reply_msg.get("message"))
        if isinstance(message_json, list) and len(message_json) > 0:
            content = message_json
            message_json = message_json[0]
        # 根据大模型返回结果 决定是否调用其他agent
        if message_json.get("type") == "tool_call":
            print(f"使用工具 {content}")
            await self.mult_tool_call(content,session_id, to_aid_list)
        else:
            self.agentid.send_message_content(session_id, to_aid_list, self.agentid.get_content_from_message(reply_msg))
        return

    def mult_tool_choose(self,llm_content,session_id,to_aid_list):
        tools = []
        agents = self.agentid.get_all_public_data()
        for ainfo in agents:
            aid =ainfo.get("agent_id",None)
            if aid is None or aid == "":
                continue
            public_data = ainfo.get("public_data",None)

            if public_data is None:
                continue
            # public_data_json = json.loads(public_data)
            name = public_data.get('name',None)
            if name is None or name == "":
                continue
            description = public_data.get('description',None)
            if description is None or description == "":
                continue
            description = f"我是{name}，我能提供[{description}[服务，我的aid是{aid}"
            tools.append({
                "type": "function",
                "function": {
                    "name": "agent_" + aid,
                    "description": description,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "aid": {
                                "type": "string",
                                "description": "",
                            },
                            "text": {
                                "type": "string",
                                "description": ""
                            }
                        },
                        "required": ["aid", "text"]
                    }
                }
            })
        msg_block = {
            "type": "content",
            "status": "success",
            "timestamp": int(time.time() * 1000),
            "content": llm_content,
            "tools":tools,
            "prompt":""
        }
        self.agentid.quick_send_messsage(self.llm_agent_id, msg_block, lambda reply_msg: self.reply_message_handler(reply_msg,session_id,to_aid_list))

    async def mult_tool_call(self,content,session_id, to_aid_list) :
        for tool_call in content:
            tool = json.loads(tool_call.get("content"))
            tool_name = tool.get("tool_name")
            tool_args = tool.get("tool_args")
            async def async_func_call_result(message):
                tool_result = self.agentid.get_content_from_message(message)
                self.agentid.quick_send_messsage_content(self.llm_agent_id, tool_result,
                    lambda reply_msg: self.reply_message_handler(reply_msg,session_id,to_aid_list))
                return
            self.agentid.quick_send_messsage_content(tool_args["aid"], tool_args["text"], async_func_call_result)

if __name__ == "__main__":
    _endpoint = "agentunion.cn"
    _name = "mc57001"

    agent = Agent()
    agent.agentid =agent.acp.create_aid(_endpoint, _name)
    async def sync_message_handler(msg):
        print(f"收到消息数据: {msg}")
        await agent.async_message_handler(msg)  # 添加await关键字
        return True
    try:
        agent.agentid.online()
        agent.agentid.add_message_handler(sync_message_handler)
        agent.acp.serve_forever()
    except Exception as e:
        print(f"AgentID未正确初始化: {e}")