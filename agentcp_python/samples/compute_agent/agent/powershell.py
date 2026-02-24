import subprocess
import json
from typing import Optional, Union, List, Dict
import tempfile
import os
import logging


class PowerShellExecutor:
    """
    PowerShell 脚本执行模块

    功能：
    - 执行 PowerShell 命令或脚本文件
    - 支持参数传递
    - 捕获标准输出和错误输出
    - 支持 JSON 结果解析
    - 超时控制
    - 临时脚本文件管理
    """

    def __init__(self, execution_policy: str = "RemoteSigned"):
        """
        初始化 PowerShell 执行器

        :param execution_policy: PowerShell 执行策略 (默认: RemoteSigned)
        """
        self.execution_policy = execution_policy
        self.logger = logging.getLogger("PowerShellExecutor")

    def execute_command(
        self,
        command: str,
        arguments: Optional[Dict[str, Union[str, int, bool]]] = None,
        timeout: int = 60,
        convert_to_json: bool = False,
    ) -> Union[str, Dict]:
        """
        执行 PowerShell 命令

        :param command: PowerShell 命令或脚本代码
        :param arguments: 参数字典 {参数名: 值}
        :param timeout: 超时时间(秒)
        :param convert_to_json: 是否将输出解析为JSON
        :return: 命令输出或解析后的JSON
        """
        # 构建完整的 PowerShell 命令
        ps_command = self._build_ps_command(command, arguments)

        # 执行命令
        result = self._execute_ps(ps_command, timeout)

        # 如果需要转换为 JSON
        if convert_to_json:
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                self.logger.warning("Output is not valid JSON, returning raw output")
                return result.stdout
        return result.stdout

    def execute_script(
        self,
        script_path: str,
        arguments: Optional[Dict[str, Union[str, int, bool]]] = None,
        timeout: int = 60,
        convert_to_json: bool = False,
    ) -> Union[str, Dict]:
        """
        执行 PowerShell 脚本文件

        :param script_path: PowerShell 脚本路径
        :param arguments: 参数字典 {参数名: 值}
        :param timeout: 超时时间(秒)
        :param convert_to_json: 是否将输出解析为JSON
        :return: 脚本输出或解析后的JSON
        """
        if not os.path.exists(script_path):
            raise FileNotFoundError(f"PowerShell script not found: {script_path}")

        # 构建执行脚本的命令
        ps_command = f"& '{script_path}' {self._dict_to_ps_args(arguments)}"

        # 执行命令
        result = self._execute_ps(ps_command, timeout)

        # 如果需要转换为 JSON
        if convert_to_json:
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                self.logger.warning("Output is not valid JSON, returning raw output")
                return result.stdout
        return result.stdout

    def execute_temporary_script(
        self,
        script_content: str,
        arguments: Optional[Dict[str, Union[str, int, bool]]] = None,
        timeout: int = 60,
        convert_to_json: bool = False,
    ) -> Union[str, Dict]:
        """
        创建并执行临时 PowerShell 脚本

        :param script_content: PowerShell 脚本内容
        :param arguments: 参数字典 {参数名: 值}
        :param timeout: 超时时间(秒)
        :param convert_to_json: 是否将输出解析为JSON
        :return: 脚本输出或解析后的JSON
        """
        # 创建临时脚本文件
        with tempfile.NamedTemporaryFile(
            suffix=".ps1", delete=False, mode="w"
        ) as temp_script:
            temp_script.write(script_content)
            temp_path = temp_script.name

        try:
            result = self.execute_script(temp_path, arguments, timeout, convert_to_json)
        finally:
            # 清理临时文件
            os.unlink(temp_path)

        return result

    def _build_ps_command(
        self, command: str, arguments: Optional[Dict[str, Union[str, int, bool]]] = None
    ) -> str:
        """
        构建完整的 PowerShell 命令

        :param command: 基础命令
        :param arguments: 参数字典
        :return: 完整的 PowerShell 命令
        """
        # 如果命令是多行脚本，需要先保存到变量中
        if "\n" in command:
            script_block = f"{{{command}}}"
            return f"Invoke-Command -ScriptBlock {script_block} {self._dict_to_ps_args(arguments)}"
        else:
            return f"{command} {self._dict_to_ps_args(arguments)}"

    def _dict_to_ps_args(
        self, arguments: Optional[Dict[str, Union[str, int, bool]]]
    ) -> str:
        """
        将参数字典转换为 PowerShell 参数字符串

        :param arguments: 参数字典
        :return: PowerShell 参数字符串
        """
        if not arguments:
            return ""

        args = []
        for key, value in arguments.items():
            if isinstance(value, bool):
                # 布尔参数处理
                if value:
                    args.append(f"-{key}")
            else:
                # 其他类型参数
                args.append(f"-{key} {self._escape_ps_value(value)}")

        return " ".join(args)

    def _escape_ps_value(self, value: Union[str, int, float]) -> str:
        """
        转义 PowerShell 参数值

        :param value: 参数值
        :return: 转义后的字符串
        """
        if isinstance(value, str):
            # 字符串需要加引号并转义内部引号
            return f"\"{value.replace('\"', '`\"')}\""
        else:
            # 数字类型直接转换为字符串
            return str(value)

    def _execute_ps(self, ps_command: str, timeout: int) -> subprocess.CompletedProcess:
        """
        执行 PowerShell 命令

        :param ps_command: PowerShell 命令
        :param timeout: 超时时间(秒)
        :return: 完成的过程对象
        """
        # 构建完整的 PowerShell 命令
        full_command = [
            "powershell.exe",
            "-ExecutionPolicy",
            self.execution_policy,
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            ps_command,
        ]

        self.logger.debug(f"Executing PowerShell command: {' '.join(full_command)}")

        try:
            # 执行命令
            result = subprocess.run(
                full_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout,
                check=False,
            )

            # 记录错误
            if result.returncode != 0:
                self.logger.error(
                    f"PowerShell command failed with exit code {result.returncode}\n"
                    f"Error output: {result.stderr}"
                )

            return result

        except subprocess.TimeoutExpired:
            self.logger.error("PowerShell command timed out")
            raise
        except Exception as e:
            self.logger.error(f"Error executing PowerShell command: {str(e)}")
            raise
