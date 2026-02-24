import asyncio 
import json
import time
import agentcp
from pathlib import Path  # 新增导入
class SearchClient:
    def __init__(self):
        agent_data_path = "."
        self.acp = agentcp.AgentCP(agent_data_path,seed_password="888777")
        self.agentid = None
        self.agent_public_data = []
        
    async def async_message_handler(self, message_data):
        try:
            receiver = message_data.get("receiver")
            session_id = message_data.get("session_id")  # 获取session_id
            message_id = message_data.get("message_id")  # 获取message_id
            print(f"收到消息数据: {session_id} {message_id} {receiver}")
            if self.agentid.id not in receiver:
                print("不是发给我的消息，不处理")
                return
            sender = message_data.get("sender")
            #解析内容
            llm_content = self.agentid.get_content_from_message(message_data)
            print("llm 内容:", llm_content)
            self.send_message(sender,session_id,message_id,"qwenlwj1.agentunion.cn","text",llm_content)            
        except json.JSONDecodeError as e:
            import traceback
            print(f"JSON解析错误: {e}\n原始数据: {message_data}\n完整堆栈跟踪:\n{traceback.format_exc()}")
        except Exception as e:
            import traceback
            print(f"处理消息时发生错误: {e}\n完整堆栈跟踪:\n{traceback.format_exc()}")
                
    def get_aid_list(self):
        """获取所有 aid 列表"""
        return self.acp.get_aid_list()
    
    async def fetch_and_write_public_data(self):
        """每 5 分钟获取公共数据并写入文件"""
        while True:
            try:
                agent_public_data = self.agentid.get_all_public_data()
                aids = ""
                for item in agent_public_data:
                    aids+=";"+item['agent_id']
                data=self.agentid.get_online_status(aids)
                # 将 online 为 true 的数据放在前面
                online_items = []
                for item in agent_public_data:
                    for item2 in data:
                        if item['agent_id'] == item2['agent_id']:
                            item['online'] = item2['online']
                            if item['online']:
                                online_items.append(item)
                self.agent_public_data = online_items
            except Exception as e:
                print(f"获取或写入公共数据时发生错误: {e}")
            await asyncio.sleep(300)  # 等待 5 分钟


    def send_message_reply(self, session_id,to_aid,type,llm_content: str):
        to_aid_list = []
            
        # 我本地的千问agent身份
        to_aid_list.append(to_aid)            
        # 修改为直接传递字典而不是对象
        msg_block = {
            "type": type,
            "status": "success", 
            "timestamp": int(time.time() * 1000),
            "content": llm_content
        }
        self.agentid.send_message(session_id,to_aid_list, msg_block)
    
    def __build_agent_des_prompt(self):
        prompt = """
        # 角色
            你是一个智能体发现的小助手，你能够根据用户的问题，找到最适合的的一个或多个agent_id，然后返回agent_id字典，key为agent_id,value为agent_id的描述。
        ## 技能
        """
        for item in self.agent_public_data:
            public_data = json.loads(item.get('public_data', "{}"))
            if item['online']:
                prompt += f"""
                ### 技能 {item['agent_id']}: 处理 {public_data['description']} 的查询
                - 当用户询问与 {public_data['description']} 相关的问题时，返回 {item['agent_id']}。
                """
        return prompt + """
        ## 限制
        - 如果找不到合适的技能，返回不知道。
        - 不要做无关agent_id的回复
        """
            
    def send_message(self, sender,session_id,message_id,to_aid,type,llm_content: str):
        to_aid_list = []
        async def async_func_session_handler(message):
                # 在这里编写你的异步函数逻辑
            print("异步函数执行中...")
            print("message:",message)
            self.agentid.remove_message_handler(async_func_session_handler,message["session_id"])
            self.send_message_reply(session_id,sender,"content",self.agentid.get_content_from_message(message)) 
        # 我本地的千问agent身份
        to_aid_list.append(to_aid)            
        new_session_id = self.agentid.create_session("临时问题","无")
        self.agentid.invite_member(new_session_id,to_aid)
        # 修改为直接传递字典而不是对象
        msg_block = {
            "type": type,
            "status": "success", 
            "timestamp": int(time.time() * 1000),
            "content": llm_content,
            "prompt": self.__build_agent_des_prompt()
        }
        self.agentid.add_message_handler(async_func_session_handler,new_session_id)
        print(f"发送消息: {session_id} {message_id} {new_session_id}")
        self.agentid.send_message(new_session_id,to_aid_list, msg_block)
        
async def main():
    client = SearchClient()
    print("欢迎使用搜索 AGENT！")
    agentid_list = client.acp.get_aid_list()
                    
    while client.agentid is None:
        print("请选择一个身份（aid）:")
        for i, agentid in enumerate(agentid_list):
            print(f"{i+1}. {agentid}")
        print(f"{len(agentid_list)+1}. 创建一个新的身份（aid）")
        choice = input("请输入数字选择一个身份（aid）: ")
        try:
            choice = int(choice) - 1
            if choice < 0 or choice > len(agentid_list):
                raise ValueError
            if choice == len(agentid_list):
                aid = input("请输入name: ")
                client.agentid = client.acp.create_aid("agentunion.cn",aid)
                agentid_list = client.acp.get_aid_list()
            else:
                client.agentid = client.acp.load_aid(agentid_list[choice])
        except ValueError:
            print("无效的选择，请重新输入。")
    
    try:
        if client.agentid is None:
            print("load error,please check your agentid")
            return None  # 确保返回None而不是继续执行
        
        # @client.agentid.message_handler
        async def sync_message_handler(msg):
            #print(f"收到消息数据: {msg}")
            await client.async_message_handler(msg)  # 添加await关键字
            return True
        
        try:
            print("开始在线...")
            client.agentid.online()  # 确保self.agentid不为None
            asyncio.create_task(client.fetch_and_write_public_data())  # 启动定时任务
            client.agentid.add_message_handler(sync_message_handler)
            print("开始监听消息...")
            while True:
                await asyncio.sleep(1)
        except AttributeError as e:
            print(f"AgentID未正确初始化: {e}")
            return None
    except Exception as e:
        import traceback
        print(f"\n⚠️ 发生错误: {traceback.format_exc()}")  # 添加堆栈信息打印

if __name__ == "__main__":
    import sys
    asyncio.run(main())