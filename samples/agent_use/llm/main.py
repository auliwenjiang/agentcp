import json
import time

import agentcp
from openai import OpenAI


class QwenClient:
    def __init__(self):
        self.openai_api_key = None
        self.base_url = None
        self.model = None
        self.client = None
        self.acp = agentcp.AgentCP("../../../../data", seed_password="", debug=True)
        self.agentid: agentcp.AgentID = None

    def init_ai_client(self, json_data):
        # 从环境变量中获取 API Key 和 Base URL
        self.openai_api_key = json_data.get("API_KEY", "")
        self.base_url = json_data.get("BASE_URL", "")
        self.model = json_data.get("MODEL", "")
        self.client = OpenAI(api_key=self.openai_api_key, base_url=self.base_url)

    async def async_message_handler(self, message_data):
        try:
            receiver = message_data.get("receiver")
            sender = message_data.get("sender", "")  # 获取工具信息
            if self.agentid.id not in receiver:
                print("不是发给我的消息，不处理")
                return
            message_array = self.agentid.get_content_array_from_message(message_data)
            if len(message_array) == 0:
                print("消息内容为空，不处理")
                return
            llm_content = self.agentid.get_content_from_message(message_data)
            stream = message_array[0].get("stream", False)  # 获取stream信息
            tools = message_array[0].get("tools", [])  # 获取工具信息
            rolesetting = message_array[0].get("prompt", "")  # 获取工具信息
            if rolesetting != "" and rolesetting != None:
                messages = [{"role": "system", "content": rolesetting}, {"role": "user", "content": llm_content}]
            else:
                messages = [{"role": "user", "content": llm_content}]
            print(f"\n[处理消息: {sender} : {llm_content}]\n")
            await self.stream_process_query(message_data, messages, sender, stream, tools)  # 添加await关键字
        except Exception as e:
            import traceback
            print(f"处理消息时发生错误: {e}\n完整堆栈跟踪:\n{traceback.format_exc()}")

    def send_message_tools_call(self, session_id, sender, llm_content: str, funcallback):
        to_aid_list = [sender]
        msg_block = {
            "type": "tool_call",
            "status": "success",
            "timestamp": int(time.time() * 1000),
            "content": llm_content,
        }
        self.agentid.add_message_handler(funcallback, session_id)
        self.agentid.send_message(session_id, to_aid_list, msg_block)

    async def stream_process_query(self, message_data: dict, messages: list, sender: str, stream: bool,
                                   user_tools: list):
        if user_tools is None:
            user_tools = []  # 确保tools是一个列表，即使它为空
        if len(user_tools) > 0:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=stream,
                tools=user_tools
            )
        else:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=stream
            )
        session_id = message_data.get("session_id", "")  # 获取session_id
        content = response.choices[0]
        if content.finish_reason == "tool_calls":
            tool_call = content.message.tool_calls[0]
            tool_name = tool_call.function.name
            tool_args = json.loads(tool_call.function.arguments)
            print(f"\n[Calling tool {tool_name} with args {tool_args}]\n")

            async def funcallback(result_content):
                self.agentid.remove_message_handler(funcallback, session_id)
                messages.append(content.message.model_dump())
                messages.append({
                    "role": "tool",
                    "content": self.agentid.get_content_from_message(result_content),
                    "tool_call_id": tool_call.id,
                })
                await self.stream_process_query(message_data, messages, sender, stream, user_tools)

            tool_content = {
                'tool_name': tool_name,
                'tool_args': tool_args,
            }
            self.send_message_tools_call(session_id, sender, json.dumps(tool_content), funcallback)
            return
        if stream:
            await self.agentid.send_stream_message(message_data.get("session_id"), [sender], response)  # 确保正确调用
        else:
            return self.agentid.reply_message(message_data, content.message.content)


def main():
    client = QwenClient()
    print("欢迎使用 AGENT！")
    _my_aid = "llmdemo007.agentunion.cn"
    try:
        client.agentid = client.acp.load_aid(_my_aid)

        @client.agentid.message_handler()
        async def sync_message_handler(msg):
            await client.async_message_handler(msg)  # 添加await关键字
            return True

        print("开始在线...")
        env_path = "./env.json"
        # 新增文件读取逻辑
        try:
            with open(env_path, 'r', encoding='utf-8') as f:
                env_data = json.load(f)
                client.init_ai_client(env_data)
                print(f"成功加载配置文件: {env_path}")
        except FileNotFoundError:
            print(f"配置文件 {env_path} 未找到")
            exit(1)
        except json.JSONDecodeError:
            print(f"配置文件 {env_path} 格式错误")
            exit(1)
        except Exception as e:
            print(f"加载配置失败: {str(e)}")
            exit(1)
        client.agentid.online()  # 确保self.agentid不为None
        private_path = client.agentid.get_agent_private_path()  # 获取私钥路径
        print("开始监听消息...")
        client.acp.serve_forever()
    except Exception as e:
        import traceback
        print(f"\n⚠️ 发生错误: {traceback.format_exc()}")  # 添加堆栈信息打印


if __name__ == "__main__":
    main()