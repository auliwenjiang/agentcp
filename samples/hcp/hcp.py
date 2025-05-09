import json
from openai import OpenAI
from dotenv import load_dotenv
import agentcp
import os
from typing import Dict, List, Optional
import traceback
# 加载 .env 文件，确保 API Key 受到保护
load_dotenv()

class MCPClient:
    def __init__(self):
        """初始化 MCP 客户端"""
        self.openai_api_key = os.getenv("OPENAI_API_KEY")  # 读取 OpenAI API Key
        self.base_url = os.getenv("BASE_URL")  # 读取 BASE YRL
        self.model = os.getenv("MODEL")  # 读取 model
        if not self.openai_api_key:
            raise ValueError(" ×  未找到 OpenAI API Key，请在 .env 文件中设置 OPENAI_API_KEY")
        self.client = OpenAI(api_key=self.openai_api_key, base_url=self.base_url)
        # 创建OpenAI client
        self.acp = agentcp.AgentCP(".",seed_password="888777",debug=False)
        self.agentid:agentcp.AgentID = None
        self.message_store = dict()

    def record_message(self, session_id: str, role: str, content: str) -> None:
        """
        记录消息到对话历史
        参数:
            session_id: 对话会话ID，用于区分不同对话
            role: 消息角色 ('user', 'assistant', 'system')
            content: 消息内容
        """
        if session_id not in self.message_store:
            self.message_store[session_id] = []
        #'assistant','user','system'
        message = {"role": role, "content": content}
        self.message_store[session_id].append(message)

    def get_messages_for_llm(
            self,
            session_id: str,
            max_messages: Optional[int] = None,
            system_message: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """
        构造适合大模型调用的历史消息

        参数:
            session_id: 对话会话ID
            max_messages: 最大返回消息数量(从最新开始计数)
            system_message: 可选系统消息，会放在消息列表开头

        返回:
            格式化后的消息列表，可直接用于大模型API调用
        """
        if session_id not in self.message_store:
            return [{"role": "system", "content": system_message}] if system_message else []

        messages = self.message_store[session_id].copy()

        # 限制消息数量
        if max_messages is not None and max_messages > 0:
            messages = messages[-max_messages:]

        # 添加系统消息(如果提供)
        if system_message:
            # 确保系统消息在最前面
            if messages and messages[0]["role"] == "system":
                messages[0]["content"] = system_message  # 更新已有系统消息
            else:
                messages.insert(0, {"role": "system", "content": system_message})

        return messages

    def clear_messages(self, session_id: str) -> None:
        """清除指定会话的消息历史"""
        if session_id in self.message_store:
            del self.message_store[session_id]

    def get_last_message(self, session_id: str) -> Optional[Dict[str, str]]:
        """获取指定会话的最后一条消息"""
        if session_id in self.message_store and self.message_store[session_id]:
            return self.message_store[session_id][-1]
        return None

    async def process_query(self, query: str,session_id: str,send_aid: str,messages:list = []):
        print(f"\n[Processing query: {query}]\n")
        from datetime import datetime
        now = datetime.now()
        rolesetting = f"""
                您是一个专业的天气查询助手，能够根据用户提供的地理位置或城市名称，快速准确地查询当前天气状况、未来几天的天气预报以及相关的天气建议。请遵循以下规则：
                1. **意图判断**：
                    - 判断是否询问天气有关内容
                        --如果不是就简单回复用户的问题(20字以内),并引导用户问询天气有关的问题
                        --如果是天气有关的问题:                        
                            --- 如果用户未明确指定位置，请主动询问
                            --- 如果用户未明确指定时间，请主动询问,但是如果之前已经问过位置信息,那么时间默认为是今天
                2. **查询位置范围**：
                    - 支持地球上的所有城市,只要是个地方就行
                    - 如果用户未明确指定地点，先去会话历史中查看用户是否有提到过:
                        -- 如果没有,就请主动询问
                        -- 如果有,就以最后提到的位置来回答
                3. **查询时间范围**：
                    - 任何绝对时间,如3月15日,2024年5月18日
                    - 任何相对时间,如三年前,五天前,一周后,明天,后天,大后天,前天,昨天,今天上午
                    - 任何年号记年的时间,如万历十五年三月十八日
                    - 如果用户未明确指定时间，先去会话历史中查看用户是否有提到过时间:
                        -- 如果没有,就主动询问
                        -- 如果有提到,就已最后提到的时间来回答
                4. **查询内容**：
                    - 当前天气：温度、湿度、风速、天气状况（晴、雨、雪等）。
                    - 未来天气预报：未来 3 天的天气趋势。
                    - 过去的天气:猜测的天气情况
                    - 天气建议：根据天气状况提供穿衣、出行等建议。
                    你如果不清楚，可以随意编写

                    例如：
                    - 上海今天晴，气温 15°C，湿度 45%，风速 10 km/h。建议穿薄外套。
                    - 南京未来三天天气预报如下：
                        明天：多云，气温 18°C - 22°C。
                        后天：小雨，气温 16°C - 20°C。

                5. **交互方式**：
                    - 使用简洁明了的语言回复用户。
                    - 如果用户提供的地点不明确或无法查询，请友好提示并建议重新输入。

                6. **示例对话**：
                    - 用户：今天北京的天气怎么样？
                    Agent：北京今天晴，气温 15°C，湿度 45%，风速 10 km/h。建议穿薄外套。
                    - 用户：未来三天上海的天气预报？
                    Agent：上海未来三天天气预报如下：
                        明天：多云，气温 18°C - 22°C。
                        后天：小雨，气温 16°C - 20°C。
                        第三天：阴，气温 17°C - 21°C。

                7. **错误处理**：
                    - 如果查询失败，请提示用户检查输入或稍后重试。
                    - 如果遇到技术问题，请告知用户并建议联系技术支持。
                8. **当前的系统时间**:
                    - {now.strftime("%Y-%m-%d %H:%M:%S")}
                9. **如果用户的问题与天气无关,回答字数不要超过20字**
                请始终保持专业、友好和高效的服务态度！
        """
        if messages is None or len(messages) == 0:
            self.record_message(session_id,'user',query)
            messages = self.get_messages_for_llm(session_id,20,rolesetting)

        tools = [{
            "type": "function",
            "function": {
                "name": "user_answer",
                "description": "当用户问题缺少必要信息时，调用此方法，返回为用户补全的必要信息",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": "为询问用户缺少的必要信息的问题"
                        },
                        "位置": {
                            "type": "string",
                            "description": "上下文中已经知道的位置信息,还不知道就是空字符串"
                        },
                        "时间": {
                            "type": "string",
                            "description": "上下文中已经知道的时间信息,还不知道就是空字符串"
                        }
                    },
                    "required": ["question"]
                }
            }
        }]
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools = tools
        )
        # 处理返回的内容
        content = response.choices[0]
        if content.finish_reason == "tool_calls":
            # 如何是需要使用工具，就解析工具
            tool_call = content.message.tool_calls[0]
            tool_name = tool_call.function.name
            tool_args = json.loads(tool_call.function.arguments)
            # 执行工具
            print(f"\n[Calling tool {tool_name} with args {tool_args}]\n")
            #将模型返回的调用哪个工具数据和工具执行完成后的数据都存入messages中
            async def sync_wait_user_answer(answer_message):
                self.agentid.remove_message_handler(sync_wait_user_answer,session_id)
                llm_content = self.agentid.get_content_from_message(answer_message)
                #print(f"收到消息数据: {llm_content}")
                messages.append(content.message.model_dump())
                messages.append({
                    "role": "tool",
                    "content": llm_content,
                    "tool_call_id": tool_call.id,
                })
                await self.process_query("",session_id,send_aid,messages)
                return True
            to_aid_list = [send_aid]
            self.agentid.add_message_handler(sync_wait_user_answer,session_id)
            self.agentid.send_message_content(session_id,to_aid_list,f"[from FC]{tool_args['question']}")
            self.record_message(session_id, 'assistant', f"[from FC]{tool_args['question']}")
            print(f"[from FC]{tool_args['question']}")
            return
        to_aid_list = [send_aid]
        self.agentid.send_message_content(session_id,to_aid_list,f"[from LLM answer]{content.message.content}")
        self.record_message(session_id, 'assistant',f"[from LLM answer]{content.message.content}")
        print(f"[from LLM answer]{content.message.content}")
        return

def main():
    client = MCPClient()
    client.agentid = client.acp.load_aid("your_agent_id")  # 替换为实际的AgentID
    
    @client.agentid.message_handler()
    async def async_message_handler(message_data):
        try:
            session_id = client.agentid.get_session_id_from_message(message_data)
            llm_content_str = client.agentid.get_content_from_message(message_data)
            send_aid_str = client.agentid.get_sender_from_message(message_data)
            receive_aid_str = client.agentid.get_receiver_from_message(message_data)
            if client.agentid.id not in receive_aid_str:
                #不是发给我的消息，不处理
                return
            await client.process_query(llm_content_str, session_id, send_aid_str)
        except Exception as e:
            print(f"处理消息时发生错误: {e}\n完整堆栈跟踪:\n{traceback.format_exc()}")
    try:
        client.agentid.online()
        print("欢迎使用HCP聊天机器人 AGENT 客户端！")
        client.acp.serve_forever()
    except Exception as e:
        print(f"\n⚠️ 发生错误: {traceback.format_exc()}")  # 添加堆栈信息打印

if __name__ == "__main__":
    main()