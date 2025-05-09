from agentcp import AgentCP
import asyncio
import os
import re
import os
import json

class FileOperator:
    """文件操作类，负责安全地读取文本文件内容"""

    def __init__(self, sandbox_root: str = None):
        self.sandbox_root = sandbox_root or os.getcwd()  # 默认使用当前工作目录

    def is_text_file(self, file_path: str) -> bool:
        """
        通过检查文件内容判断是否为文本文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            bool: 是否为文本文件
        """
        try:
            # 尝试以文本模式打开文件
            with open(file_path, 'r', encoding='utf-8') as f:
                # 读取前1024个字符
                f.read(1024)
            return True
        except UnicodeDecodeError:
            # 如果解码失败，说明不是文本文件
            return False
        except Exception:
            # 处理其他异常，如文件不存在等，默认不是文本文件
            return False

    def extract_file_path(self, text: str) -> str:
        """从文本中提取文件名(不需要完整路径)"""
        match = re.search(r"(?:读取|打开|查看)文件\s*([^\s\/\\]+)", text)
        return match.group(1) if match else None

    def sanitize_path(self, filename: str) -> str:
        """遍历sandbox目录，找到这个文件"""
        def recursive_search(root_dir):
            try:
                for root, dirs, files in os.walk(root_dir):
                    if filename in files:
                        full_path = os.path.join(root, filename)
                        normalized_path = os.path.normpath(full_path)
                        return normalized_path
            except:
                return None
            return None

        return recursive_search(self.sandbox_root)

    def walk_directory(self):
        """
        遍历目录并打印所有文件和文件夹
        """
        filenamess = []
        for root, dirs, files in os.walk(self.sandbox_root):
            for file in files:
                filenamess.append(file)
        return filenamess

    def exist_file(self, filename):
        """
        检查文件是否存在
        """
        safe_path = self.sanitize_path(filename)
        return os.path.exists(safe_path)

    def read_file(self, file_path: str) -> str:
        """
        安全地读取文本文件内容
        
        Args:
            file_path: 文件路径
            
        Returns:
            文件内容字符串
            
        Raises:
            ValueError: 如果文件不是文本格式
        """

        safe_path = self.sanitize_path(file_path)
        if not safe_path:
            raise ValueError("文件不存在")
        if not self.is_text_file(safe_path):
            raise ValueError("只能读取文本文件")
        with open(safe_path, "r") as file:
            return file.read()

def parse_command(text):
    if not text:
        return False
    if text.find("查询") >=0 or text.find("列表") >=0:
        return 'list'
    if text.find("读取") >=0 or text.find("查看") >=0:
        return 'read'

class FileAgent:
    def __init__(self, endpoint: str, name: str):
        """
        初始化文件Agent
        """
        self.acp = AgentCP("./", seed_password="888777")
        self.endpoint = endpoint
        self.name = name
        self.aid = None
        self.last_command = ''

    async def message_handler(self, msg):
        """
        消息处理器 - 根据消息内容安全地读取文件
        {
            'session_id': '1831173476580327424', 
            'request_id': '', 'message_id': '9', 
            'ref_msg_id': '', 'sender': 'samplesdeveloper.agentunion.cn', 
            'receiver': 'guest_1831158907166261248.agentunion.cn', 
            'message': '[{"type": "text", "status": "success", "timestamp": 1746343146261, 
            "content": "{\\"text\\":\\"\\u8bfb\\u53d6\\u6587\\u4ef6agentprofile.json\\",\\"files\\":[],\\"links\\":[],\\"search\\":false,\\"think\\":false}",
            "stream": false, "prompt": null, "extra": null, "artifact": null}]',
            'timestamp': '1746343146265'
        }
        """
        try:
            ref_msg_id = msg.get("ref_msg_id")
            content = msg.get("message", "\"{}\"")
            content = json.loads(content)[0]["content"]
            content = json.loads(content)
            text = content.get("text", "")
            command = parse_command(text)
            print(f"收到消息: {content}")

            if self.last_command == 'read':
                self.last_command = ''
                return await self.read_file(msg, text)
            elif command == 'list':
                files = self.file_operator.walk_directory()
                if not files:
                    await self._send_reply(msg, "当前目录下没有文件")
                    return True
                to = "文件列表<br>" + "<br>".join(files)
                await self._send_reply(msg, to)
                return True
            elif command == 'read':
                self.last_command = 'read'
                files = self.file_operator.walk_directory()
                if not files:
                    await self._send_reply(msg, "当前目录下没有文件")
                    return True
                to = "读取哪一个文件？<br>" + "<br>".join(files)
                print(f'send message: {to}')
                await self._send_reply(msg, to)
                return True
            else:
                await self._send_reply(msg, "你可以对我说: <br>读取文件<br>查询文件")
        except Exception as e:
            print(f"处理消息出错: {str(e)}")
            await self._send_reply(msg, f"处理文件时出错: {str(e)}")
            return False

    async def read_file(self, msg, text):
        try:
            filename = self.file_operator.extract_file_path(text)  # 现在只获取文件名
            if not filename:
                try:
                    print(f'未提供文件名尝试读取: {text}')
                    file_content = self.file_operator.read_file(text)  # 直接传入文件名
                    await self._send_reply(msg, f"文件内容:<br>{file_content}")
                    return
                except Exception as e:
                    print(f"处理消息出错: {str(e)}")
            try:
                file_content = self.file_operator.read_file(filename)  # 直接传入文件名
                await self._send_reply(msg, f"文件内容:<br>{file_content}")
            except PermissionError:
                await self._send_reply(msg, "访问文件被拒绝")
            except FileNotFoundError:
                await self._send_reply(msg, f"文件不存在: {filename}")
            except ValueError as e:
                await self._send_reply(msg, f"{str(e)}")
            return True
        except Exception as e:
            print(f"处理消息出错: {str(e)}")
            await self._send_reply(msg, f"处理文件时出错: {str(e)}")
            return False

    async def _send_reply(self, original_msg, content: str):
        """
        发送回复消息
        """
        try:
            self.aid.send_message_content(
                to_aid_list=[original_msg.get("sender")],
                session_id=original_msg.get("session_id"),
                llm_content=content)
        except Exception as e:
            print(f"发送回复消息出错: {str(e)}")

    async def run(self):
        """
        运行Agent
        """
        try:
            print("正在启动Agent...", self.endpoint, self.name)
            self.aid = self.acp.create_aid(self.endpoint, self.name)
            self.aid.add_message_handler(self.message_handler)
            self.aid.online()
            self.file_operator = FileOperator(self.aid.get_agent_public_path())
            
            print("Agent已上线，等待文件读取指令...")

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
    ENDPOINT = "agentunion.cn"
    AGENT_NAME = "122asad"  # 请输入你的agent名称

    # 创建并运行Agent
    agent = FileAgent(
        ENDPOINT,
        AGENT_NAME,
    )
    # agent.test()
    asyncio.run(agent.run())
