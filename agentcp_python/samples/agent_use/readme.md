# github
[https://github.com/auliwenjiang/agentcp/blob/master/samples/agent_use/main.py](https://github.com/auliwenjiang/agentcp/blob/master/samples/agent_use/main.py)

# README.md

## 1、使用指南
### 1)、创建4个agent身份
请参考[一、创建身份，读写公有私有数据](https://ccnz88r91l2y.feishu.cn/wiki/I5F4whGuFioqwNkfJ45c8ZQ3nGf)
- 运行create_profile.py,创建DEMO_AGENT_AID
- 运行llm/create_profile.py,创建大模型Agent LLM_AGENT_AID
- 运行search/create_profile.py,创建智能体发现Agent SEARCH_AGENT_AID
- 运行tool/create_profile.py,创建工具Agent TOOL_AGENT_AID

### 2)、修改main.py文件
- 将main.py llm/main.py search/main.py tool/main.py里的seed_password、_my_aid修改为步骤1）创建的身份信息
- 将main.py里的llm_agent_id修改为LLM_AGENT_AID，search_agent_id修改为SEARCH_AGENT_AID
- 将search/main.py里的agent_id修改为TOOL_AGENT_AID
- 注意同级目录里的main.py和create_profile.py里的 AgentCP()参数要保持一致
### 3）、 配置文件
在llm目录下创建env.json,添加大模型的配置
``` json
{
  "API_KEY":"大模型的api_key",
  "BASE_URL":"大模型Api接口URL",
  "MODEL":"模型名称"
}
```
### 4)、安装依赖项
```bash
pip install agentcp OpenAI
```
### 5)、执行代码
```bash
cd tool && python main.py
cd llm && python main.py
cd search && python main.py
python main.py
```

## 2、功能简介
该Agent基于agentcp库实现了一个串并行调用的智能体（Agent），支持消息处理、工具检索、多工具并行调用以及与外部Agent的通信。
- 创建一个Agent身份（_my_aid)
- 实现Agent接收用户输入的自然语言文本
- 根据用户输入调用智能体发现Agent(search_agent_id)，寻找相关的Agent
- 把相关的Agent按照function call方式组装，发给大模型Agent（llm_agent_id）进行工具选择
- 根据大模型Agent返回的工具集列(tool_agent_id)表进行回调,把结果返回给用户

## 3、完整示例代码
### 1）、main.py
```python
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
        self.acp = agentcp.AgentCP("../data",seed_password="")
        self.llm_agent_id = "llmdemo007.agentunion.cn"
        self.search_agent_id = "search007.agentunion.cn"
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
        def search_agent_handler(search_msg):
            result = self.agentid.get_content_from_message(search_msg)
            print(f"search result={result}")
            agents = json.loads(result)
            tools = []
            for ainfo in agents:
                description = f"我是{ainfo['agent_id']}，我能提供[{ainfo['description']}]服务，我的aid是{ainfo['agent_id']}"
                tools.append({
                    "type": "function",
                    "function": {
                        "name": "agent_" + ainfo['agent_id'],
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
                "tools": tools,
                "prompt": ""
            }
            self.agentid.quick_send_messsage(self.llm_agent_id, msg_block,
                                             lambda reply_msg: self.reply_message_handler(reply_msg, session_id,
                                                                                          to_aid_list))

        self.agentid.quick_send_messsage_content(self.search_agent_id, llm_content,search_agent_handler)

    async def mult_tool_call(self,content,session_id, to_aid_list) :
        for tool_call in content:
            tool = json.loads(tool_call.get("content"))
            tool_args = tool.get("tool_args")
            print(f"aiddddddd={tool_args['aid']} text={tool_args['text']}")
            async def async_func_call_result(message):
                tool_result = self.agentid.get_content_from_message(message)
                print(f"工具返回的结果={tool_result}")
                self.agentid.send_message_content(session_id,to_aid_list, tool_result)
                # self.agentid.quick_send_messsage_content(self.llm_agent_id, tool_result,
                #     lambda reply_msg: self.reply_message_handler(reply_msg,session_id,to_aid_list))
                return
            self.agentid.quick_send_messsage_content(tool_args["aid"], tool_args["text"], async_func_call_result)

if __name__ == "__main__":
    _my_aid = "mc58009.aid.pub"

    agent = Agent()
    agent.agentid =agent.acp.load_aid(_my_aid)
    async def sync_message_handler(msg):
        print(f"收到消息数据: {msg}")
        await agent.async_message_handler(msg)  # 添加await关键字
        return True
    try:
        agent.agentid.online()
        # agent.agentid.sync_public_files()
        agent.agentid.add_message_handler(sync_message_handler)
        agent.acp.serve_forever()
    except Exception as e:
        print(f"AgentID未正确初始化: {e}")
```

### 2）、tool/main.py
```
import agentcp

if __name__ == "__main__":
    acp = agentcp.AgentCP("../../data")
    _my_aid = "testdemo11.aid.pub"
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
```
### 3）、llm/main.py
```
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
        self.acp = agentcp.AgentCP("../../data", seed_password="", debug=True)
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
    _my_aid = "llmdemo007.aid.pub"
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
```
### 4）、search/main.py
```
import json

import agentcp

if __name__ == "__main__":
    acp = agentcp.AgentCP("../data")
    _my_aid = "search007.aid.pub"
    aid = acp.load_aid(_my_aid)
    @aid.message_handler()
    async def sync_message_handler(msg):
        receiver = aid.get_receiver_from_message(msg)
        if aid.id not in receiver:
            return None
        session_id = aid.get_session_id_from_message(msg)
        sender = aid.get_sender_from_message(msg)
        agents = [
            {
                "agent_id": "testdemo11.aid.pub",
                "name":"我是天气Agent，我提供天气信息",
                "description":"我是天气Agent，我提供天气信息",
            },
        ]
        aid.send_message_content(session_id, [sender], json.dumps(agents))
        return True
    aid.online()
    # aid.sync_public_files()
    print("已上线完成")
    acp.serve_forever()
```

