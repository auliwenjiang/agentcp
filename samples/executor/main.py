from agentcp import AgentCP
import asyncio
import json
from RestrictedPython import compile_restricted
from RestrictedPython.Guards import safe_builtins, guarded_unpack_sequence

class PrintCollector:
    """Collect written text, and return it when called."""

    def __init__(self, _getattr_=None):
        self.txt = []
        self._getattr_ = _getattr_

    def write(self, text):
        self.txt.append(text)

    def __call__(self, *args, **kwargs):
        return self

    def _call_print(self, *objects, **kwargs):
        if kwargs.get("file", None) is None:
            kwargs["file"] = self
        else:
            self._getattr_(kwargs["file"], "write")

        print(*objects, **kwargs)


class PythonExecutorAgent:
    def __init__(self, endpoint: str, name: str):
        self.acp = AgentCP("./", seed_password="888777")
        self.endpoint = endpoint
        self.name = name
        self.aid = None

    async def message_handler(self, msg):
        """
        消息处理器 - 执行Python代码并返回结果
        """
        try:
            ref_msg_id = msg.get("ref_msg_id")
            content = msg.get("message", '"{}"')
            content = json.loads(content)[0]["content"]
            content = json.loads(content)
            text = content.get("text", "")
            if not text.strip():
                await self._send_reply(msg, "请输入要执行的Python代码")
                return True

            try:
                # 安全地执行代码
                result = await self.safe_exec(text)
                print(f"执行结果: {result}")
                await self._send_reply(msg, f"执行结果:<br>{result}")
            except Exception as e:
                print(f"执行代码出错: {str(e)}")
                await self._send_reply(msg, f"执行出错:<br> {str(e)}")

            return True

        except Exception as e:
            print(f"处理消息出错: {str(e)}")
            await self._send_reply(msg, f"处理代码时出错:<br> {str(e)}")
            return False

    async def _send_reply(self, original_msg, content: str):
        """
        发送回复消息
        """
        try:
            self.aid.send_message_content(
                to_aid_list=[original_msg.get("sender")],
                session_id=original_msg.get("session_id"),
                llm_content=content,
            )
        except Exception as e:
            print(f"发送回复消息出错: {str(e)}")
    async def safe_exec(self, code: str):
        """
        安全地执行Python代码

        调用说明：
        1. 传入参数 `code` 应为合法的Python代码字符串。
        2. 执行代码时，会使用 `RestrictedPython` 进行安全限制，防止执行危险操作。
        3. 代码中的 `print` 输出会被 `PrintCollector` 捕获，但当前方法未返回该输出。
        4. 最终结果需要存储在名为 `result` 的变量中，方法会尝试从执行环境中获取该变量的值并返回。
        5. 代码中可以使用 `import` 进行模块导入，但由于安全性考虑，建议谨慎使用。

        参数:
        code (str): 要安全执行的Python代码字符串。

        返回:
        Any: 执行代码中 `result` 变量的值，如果不存在则返回 `None`。
        """
        safe_builtins.update(
            {
                "__import__": __import__,
            }
        )

        policy_globals = {
            "__builtins__": safe_builtins,
            "_print_": PrintCollector(),  # 用于捕获print输出
            "_getattr_": getattr,
            "_getiter_": iter,
            "_getitem_": lambda obj, index: obj[index],
            "_iter_unpack_sequence_": guarded_unpack_sequence,  # 支持多变量赋值
        }

        byte_code = compile_restricted(code, filename="<inline>", mode="exec")
        exec(byte_code, policy_globals)
        # 查看print输出
        # output = policy_globals["_print_"]()
        # print(f"沙箱输出结果：\n{output.txt}")
        # 获取结果, 最终结果返回必须是变量result
        result = policy_globals.get("result")
        print("Captured result:", result)
        return result

    async def run(self):
        """运行Agent"""
        try:
            self.aid = self.acp.create_aid(self.endpoint, self.name)
            self.aid.add_message_handler(self.message_handler)
            self.aid.online()
            print("Python执行器Agent已上线，等待代码执行指令...")

            while True:
                await asyncio.sleep(1)

        except Exception as e:
            print(f"发生错误: {str(e)}")
        finally:
            if self.aid:
                self.aid.offline()
                print("Agent已下线")


if __name__ == "__main__":
    # 配置参数
    ENDPOINT = "aid.pub"
    AGENT_NAME = ""  # 请使用真实的aid

    # 创建并运行Agent
    agent = PythonExecutorAgent(ENDPOINT, AGENT_NAME)
    asyncio.run(agent.run())
