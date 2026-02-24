import asyncio 
from calendar import c
import time
import agentcp
from agentcp.agentcp import AgentID
from http import HTTPStatus
from dashscope import Application
from dotenv import load_dotenv, find_dotenv
from dashscope import Application

class AmapClient:
    def __init__(self):
        self.agentid_client = agentcp.AgentCP(".",seed_password="888777")  # 初始化 MCP 客户端，设置 debug=True 以启用调试模式
        self.agentid:AgentID = None
        load_dotenv(find_dotenv())
        self.api_key = "sk-yourappkey"
        self.app_id = "your_appid"
        
    async def chat_loop(self):
        if self.agentid is None:
            print("load error,please check your agentid")
            return None  # 确保返回None而不是继续执行
        
        @self.agentid.message_handler()
        async def sync_message_handler(msg):
            await self.async_message_handler(msg)  # 添加await关键字
            return True
            
        print("设置监听函数...")
        
        try:
            print("开始在线...")
            self.agentid.online()  # 确保self.agentid不为None
            print("开始监听消息...")
            while True:
                await asyncio.sleep(1)
        except AttributeError as e:
            print(f"AgentID未正确初始化: {e}")
            return None

    async def async_message_handler(self,message_data):
        #print(f"收到消息数据: {message_data}")
        try:
            receiver = message_data.get("receiver")
            if self.agentid.id not in receiver:
                print("不是发给我的消息，不处理")
                return                
            content = self.agentid.get_content_from_message(message_data)
            response = Application.call(
                api_key=self.api_key,
                app_id=self.app_id,
                prompt=content
            )

            if response.status_code != HTTPStatus.OK:
                result = f"调用失败，错误码：{response.status_code}, 错误信息：{response.message}"
                print(f'request_id={response.request_id}')
                print(f'code={response.status_code}')
                print(f'message={response.message}')
                print(f'请参考文档：https://help.aliyun.com/zh/model-studio/developer-reference/error-code')
            else:
                result = response.output.text
                print(response.output.text)
            to_aid_list = []
            to_aid_list.append(message_data.get("sender"))
            # 修改为直接传递字典而不是对象
            msg_block = {
                "type": "content",
                "status": "success", 
                "timestamp": int(time.time() * 1000),
                "content": result
            }
            self.agentid.reply_message(message_data, msg_block)
        except Exception as e:
            import traceback
            print(f"处理消息时发生错误: {e}\n完整堆栈跟踪:\n{traceback.format_exc()}")
            
async def main():
    client = AmapClient()
    print("欢迎使用高德聊天机器人 AGENT 客户端！")
    client.agentid = client.agentid_client.load_aid("your_agent_id")  # 替换为实际的AgentID
    try:
        await client.chat_loop()
    except Exception as e:
        print(f"聊天循环出错: {e}")
        
if __name__ == "__main__":
    asyncio.run(main())