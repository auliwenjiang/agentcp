# Copyright 2025 AgentUnion Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# 在Python文件开头明确指定编码声明
# -*- coding: utf-8 -*-
import abc
import asyncio
import hashlib
import json
import logging
from ntpath import exists
import os
import queue
import threading
import time
import typing
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from typing import Union

import requests
from cryptography.hazmat.primitives import serialization

from agentcp import utils
from agentcp.ap.ap_client import ApClient
from agentcp.base.html_util import parse_html
from agentcp.ca.ca_client import CAClient
from agentcp.ca.ca_root import CARoot
from agentcp.context import ErrorContext, exceptions
from agentcp.db.db_mananger import DBManager
from agentcp.heartbeat.heartbeat_client import HeartbeatClient
from agentcp.message import AgentInstructionBlock, AssistantMessageBlock
from agentcp.msg.session_manager import Session, SessionManager
from agentcp.file.file_client import FileClient
from .llm_server import add_llm_aid, add_llm_api_key, get_base_url, get_llm_api_key, llm_server_is_running, run_server
from agentcp.improved_scheduler import ImprovedMessageScheduler
from agentcp.metrics import MessageMetrics
from agentcp.base.log import log_info, log_error, log_exception, log_warning, log_debug,set_log_enabled

class _AgentCP(abc.ABC):
    """
    AgentCP类的抽象基类
    """

    def __init__(self):
        self.shutdown_flag = threading.Event()  # 初始化信号量
        self.exit_hook_func = None

    def register_signal_handler(self, exit_hook_func=None):
        """
        注册信号处理函数
        """
        try:
            import signal

            signal.signal(signal.SIGTERM, self.signal_handle)
            signal.signal(signal.SIGINT, self.signal_handle)
            self.exit_hook_func = exit_hook_func
        except Exception:
            return

    def serve_forever(self):
        """ """
        while not self.shutdown_flag.is_set():
            time.sleep(1)

    def signal_handle(self, signum, frame):
        """
        信号处理函数
        :param signum: 信号编号
        :param frame: 当前栈帧
        """
        self.shutdown_flag.set()  # 设置关闭标志
        if self.exit_hook_func:
            self.exit_hook_func(signum, frame)


class AgentID(abc.ABC):
    def __init__(self, id: str, app_path: str, seed_password: str, ca_client, ep_url, debug=False):
        super().__init__()
        self.shutdown_flag = threading.Event()  # 初始化信号量
        self.public_data_path = os.path.join(app_path, "AIDs", id, "public")
        self.private_data_path = os.path.join(app_path, "AIDs", id, "private")
        os.makedirs(self.public_data_path, exist_ok=True)
        os.makedirs(self.private_data_path, exist_ok=True)
        self.ca_root_path = os.path.join(app_path, "Certs", "root")
        os.makedirs(self.ca_root_path, exist_ok=True)
        ca_root = CARoot()
        ca_root.set_ca_root_crt(self.ca_root_path)
        self.id = id
        array = id.split(".")
        self.ap = array[-2] + "." + array[-1]
        self.name = ""
        self.avaUrl = ""
        self.description = ""
        self.ap_client = None
        self.session_manager = None
        self.ca_client: CAClient = ca_client
        self.ep_url = ep_url
        self.seed_password = seed_password
        self.message_from_acp = False
        self.message_handlers = []  # 添加消息监听器属性
        self.message_handlers_session_map = {}  # 添加消息监听器属性
        self.message_handlers_router_map = {}  # 添加消息监听器属性
        self.heartbeat_client = None
        self.db_manager = DBManager(self.private_data_path, id)
        self.debug = debug

        # ✅ 使用新的改进调度器替代原有线程池
        self.use_improved_scheduler = True  # 可以通过参数控制是否启用
        if self.use_improved_scheduler:
            self.message_scheduler = ImprovedMessageScheduler(
                core_workers=20,      # 核心线程数
                max_workers=50,       # 最大线程数
                max_tasks_per_worker=10  # 每线程最大异步任务数
            )
        else:
            # 保留原有实现作为备份
            self.thread_pool = ThreadPoolExecutor(max_workers=200)
            self.task_queue = queue.Queue()
            self.active_threads = 0
            self.thread_lock = threading.Lock()

        self.is_online_success = False
        self.file_client = None

        # ✅ 断开回调：当 WebSocket 连接断开时通知外部
        self._disconnect_callback = None

        # ✅ P1-3新增: 消息处理指标
        self.metrics = MessageMetrics()

        # ✅ 修复WebSocket阻塞: 消息派发队列（无阻塞，避免阻塞WebSocket线程）
        self.message_dispatch_queue = queue.Queue(maxsize=10000)  # 大容量队列
        self._message_dispatcher_thread = None
        self._message_dispatcher_running = False
        self._start_message_dispatcher()

        # ✅ Metrics定时同步到JSON文件
        # 使用项目根目录的backup文件夹（app_path是./agentcp，需要获取其父目录作为项目根目录）
        project_root = os.path.abspath(os.path.dirname(app_path))  # 从 "./agentcp" 获取项目根目录
        backup_dir = os.path.join(project_root, "backup")
        os.makedirs(backup_dir, exist_ok=True)
        self.metrics_file_path = os.path.join(backup_dir, "metrics.json")
        print(f"[DEBUG] AgentID初始化: app_path = {app_path}")
        print(f"[DEBUG] AgentID初始化: project_root = {project_root}")
        print(f"[DEBUG] AgentID初始化: metrics_file_path = {self.metrics_file_path}")
        self._metrics_sync_thread = None
        self._metrics_sync_running = False
        print(f"[DEBUG] 即将启动metrics同步线程...")
        self._start_metrics_sync()
        print(f"[DEBUG] _start_metrics_sync()调用完成")

        # ✅ 新增: 启动统一监控服务（集成滑动窗口和时间序列存储）
        # ⚠️ 监控服务启动失败不应影响核心流程
        self.monitoring_service = None
        try:
            from agentcp.monitoring.monitoring_service import MonitoringService
            from agentcp.monitoring.global_monitor import set_global_monitoring_service

            db_path = os.path.join(backup_dir, "metrics_timeseries.db")
            self.monitoring_service = MonitoringService(
                agent_id=id,
                metrics_collector=self.metrics,
                db_path=db_path,
                snapshot_interval=10  # 每10秒采集一次
            )
            self.monitoring_service.start()

            # ✅ 注册为全局监控服务（供Server访问）
            set_global_monitoring_service(self.monitoring_service)

            log_info(f"📊 [AgentID] 监控服务已启动: {id}")
        except Exception as e:
            log_error(f"⚠️ [AgentID] 监控服务启动失败（不影响核心功能）: {e}")
            self.monitoring_service = None

        # 代理配置
        self._use_system_proxy = False
        self._proxy_config_path = os.path.join(self.private_data_path, "proxy_config.json")
        self._load_proxy_config()


    def get_app_path(self):
        return self.public_data_path

    def get_agent_public_path(self):
        return self.public_data_path

    def get_agent_private_path(self):
        return self.private_data_path

    def _load_proxy_config(self):
        """从磁盘加载代理配置"""
        try:
            if os.path.exists(self._proxy_config_path):
                with open(self._proxy_config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self._use_system_proxy = config.get('use_system_proxy', False)
                    log_info(f"[AgentID] 加载代理配置: use_system_proxy={self._use_system_proxy}")
            else:
                # 首次初始化，创建默认配置文件
                self._save_proxy_config()
                log_info(f"[AgentID] 创建默认代理配置文件: {self._proxy_config_path}")
        except Exception as e:
            log_error(f"[AgentID] 加载代理配置失败: {e}")
            self._use_system_proxy = False

    def _save_proxy_config(self):
        """保存代理配置到磁盘"""
        try:
            config = {
                'use_system_proxy': self._use_system_proxy
            }
            with open(self._proxy_config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            log_info(f"[AgentID] 保存代理配置: use_system_proxy={self._use_system_proxy}")
        except Exception as e:
            log_error(f"[AgentID] 保存代理配置失败: {e}")

    def get_use_system_proxy(self) -> bool:
        """获取是否使用系统代理"""
        return self._use_system_proxy

    def set_use_system_proxy(self, use_proxy: bool):
        """设置是否使用系统代理

        Args:
            use_proxy: True表示使用系统代理，False表示不使用
        """
        # 先更新内存中的配置
        self._use_system_proxy = use_proxy
        # 再保存到磁盘
        self._save_proxy_config()
        log_info(f"[AgentID] 更新代理配置: use_system_proxy={use_proxy}")

    def init_ap_client(self):
        self.ap_client = ApClient(self.id, self.ep_url, self.ca_client.get_aid_certs_path(self.id), self.seed_password)
        self.ap_client.set_agent_id_ref(self)
        self.ap_client.initialize()

    def online(self):
        print(f"{self.id} online")
        try:
            if self.ap_client is None:
                self.ap_client = ApClient(
                    self.id, self.ep_url, self.ca_client.get_aid_certs_path(self.id), self.seed_password
                )
                self.ap_client.set_agent_id_ref(self)
                self.ap_client.initialize()
                if self.ap_client.get_heartbeat_server() is None or self.ap_client.get_heartbeat_server() == "":
                    raise Exception("获取心跳服务器地址失败")

            log_debug("initialzing heartbeat server")
            if self.heartbeat_client is not None:
                self.heartbeat_client.offline()
                self.heartbeat_client.sign_out()
                self.heartbeat_client = None

            self.heartbeat_client = HeartbeatClient(
                self.id,
                self.ap_client.get_heartbeat_server(),
                self.ca_client.get_aid_certs_path(self.id),
                self.seed_password,
            )
            self.heartbeat_client.initialize()

            if self.session_manager is not None:
                try:
                    self.session_manager.close_all_session()
                    self.session_manager = None
                except Exception as e:
                    log_exception(f"close session error: {e}")
                    
            self.session_manager = SessionManager(
                self.id,
                self.ap_client.get_message_server(),
                self.ca_client.get_aid_certs_path(self.id),
                self.seed_password,
                self.db_manager,
                agent_id_ref=self,
            )
            self.session_manager.set_on_message_receive(self.__agentid_message_listener)
            self.session_manager.set_on_invite_ack(self.__on_invite_ack)
            self.session_manager.set_on_session_message_ack(self.__on_session_message_ack)
            self.session_manager.set_on_system_message(self.__on_system_message)
            self.session_manager.set_on_member_list_receive(self.__on_member_list_receive)
            self.__connect()
            add_llm_aid(self)
            self.is_online_success = True
        except Exception as e:
            log_exception(f"agent online error: {e}")
            ErrorContext.publish(exceptions.SDKError(message=f"agent online error: {e}"))
            self.is_online_success = False

    def offline(self):
        """离线状态"""
        # ✅ 修复WebSocket阻塞: 先停止消息派发线程
        if hasattr(self, '_stop_message_dispatcher'):
            self._stop_message_dispatcher()

        # ✅ 停止metrics同步线程
        if hasattr(self, '_stop_metrics_sync'):
            self._stop_metrics_sync()

        # ✅ 停止监控服务（非阻塞，不影响主流程）
        if hasattr(self, 'monitoring_service') and self.monitoring_service:
            try:
                self.monitoring_service.stop(wait=False)  # 不等待线程结束
                log_info(f"📊 [AgentID] 监控服务停止信号已发送: {self.id}")
            except Exception as e:
                log_error(f"⚠️ [AgentID] 停止监控服务异常（不影响核心功能）: {e}")

        if self.heartbeat_client:
            self.heartbeat_client.offline()
            self.heartbeat_client.sign_out()
            self.heartbeat_client = None
        if self.ap_client:
            self.ap_client.sign_out()
            self.ap_client = None
        if self.session_manager:
            self.session_manager.close_all_session()
            self.session_manager = None

        # ✅ 关闭改进的调度器
        if self.use_improved_scheduler and hasattr(self, 'message_scheduler'):
            log_info("正在关闭消息调度器...")
            self.message_scheduler.print_stats()
            self.message_scheduler.shutdown(wait=True)

    def get_aid_info(self):
        return {
            "aid": self.id,
            "name": self.name,
            "description": self.description,
            "avaUrl": self.avaUrl,
            "ep_url": self.ep_url,
        }

    def get_metrics(self) -> dict:
        """✅ P1-3新增: 获取消息处理指标

        Returns:
            包含所有指标的字典
        """
        if hasattr(self, 'metrics'):
            return self.metrics.get_summary()
        return {}

    def print_metrics(self):
        """✅ P1-3新增: 打印消息处理指标"""
        if hasattr(self, 'metrics'):
            self.metrics.print_summary()
        else:
            print("⚠️ 指标收集未启用")

    def delete_friend_agent(self, aid):
        return self.db_manager.delete_friend_agent(aid)

    def delete_session(self, session_id):
        self.session_manager.close_session(session_id)
        return self.db_manager.delete_session(session_id)

    def get_message_list(self, session_id, page=1, page_size=10):
        return self.db_manager.get_message_list(self.id, session_id, page, page_size)

    def get_llm_message_list(self, session_id, page=1, page_size=10):
        message_list = self.get_message_list(self.id, session_id, page, page_size)
        if message_list is None or len(message_list) == 0:
            return []
        llm_message_list = []
        for message in message_list:
            sender = self.get_sender_from_message(message)
            content = self.get_content_from_message(message)
            reciver = self.get_receiver_from_message(message)
            if sender != self.id and self.id not in reciver:
                continue
            if sender == self.id:
                msg = {"role": "assistant", "content": content}
            else:
                msg = {"role": "user", "content": content}
            llm_message_list.append(msg)
        return llm_message_list

    def add_message_handler(
        self,
        handler: typing.Callable[[dict], typing.Awaitable[None]],
        session_id: str = "",
        router: str = "",
        from_acp: bool = False,
    ):
        """消息监听器装饰器"""
        log_debug("add message handler")
        if self.message_from_acp == False or (session_id == "" and router == ""):
            self.message_from_acp = from_acp

        if session_id == "" and router == "":
            self.message_handlers.append(handler)
        elif session_id != "":
            self.message_handlers_session_map[session_id] = handler
        else:
            self.message_handlers_router_map[router] = handler

    def remove_message_handler(self, handler: typing.Callable[[dict], typing.Awaitable[None]], session_id):
        """移除消息监听器"""
        if session_id == "":
            if handler in self.message_handlers:
                self.message_handlers.remove(handler)
        else:
            self.message_handlers_session_map.pop(session_id, None)

    def create_session(self, name, subject, *, type="public"):
        """创建与多个agent的会话
        :param name: 群组名称
        :param subject: 群组主题
        :param to_aid_list: 目标agent ID列表
        :return: 会话ID或None
        """
        log_debug(f"create session: {name}, subject: {subject}, type: {type}")
        session = self.session_manager.create_session(name, subject, type)
        if session is None:
            log_error("failed to create session")
            return None
        self.__insert_session(self.id, session.session_id, session.identifying_code, name)
        return session.session_id

    def invite_member(self, session_id, to_aid):
        if self.session_manager.invite_member(session_id, to_aid):
            self.db_manager.invite_member(self.id, session_id, to_aid)
        else:
            log_error(f"failed to invite: {to_aid} -> {session_id}")

    def get_online_status(self, aids):
        return self.heartbeat_client.get_online_status(aids)

    def get_conversation_list(self, page, page_size):
        return self.db_manager.get_conversation_list(self.id, page, page_size)

    # file/binary
    async def create_stream(
        self, session_id, to_aid_list, content_type: str = "text/event-stream", ref_msg_id: str = ""
    ):
        return await self.session_manager.create_stream(session_id, to_aid_list, content_type, ref_msg_id)

    def close_session(self, session_id):
        return self.session_manager.close_session(session_id)

    def close_stream(self, session_id, stream_url):
        return self.session_manager.close_stream(session_id, stream_url)

    def send_chunk_to_stream(self, session_id, stream_url, chunk,type="text/event-stream"):
        return self.session_manager.send_chunk_to_stream(session_id, stream_url, chunk, type = type)

    def send_chunk_to_file_stream(self, session_id,push_url,offset: int, chunk: bytes):
        return self.session_manager.send_chunk_to_file_stream(session_id,push_url,offset,chunk)


    def __quick_send_message_base(self, to_aid, asnyc_message_result):
        session_id = self.create_session("quick session", "")
        if session_id is None:
            raise Exception("failed to create session")

        async def __asnyc_message_result(data):
            self.remove_message_handler(__asnyc_message_result, session_id=session_id)
            if asnyc_message_result is not None:
                await asnyc_message_result(data)

        self.invite_member(session_id, to_aid)
        if asnyc_message_result is not None:
            self.add_message_handler(__asnyc_message_result, session_id=session_id)
        return session_id

    def quick_send_message_content(self, to_aid: str, message_content: str, asnyc_message_result):
        session_id = self.__quick_send_message_base(to_aid, asnyc_message_result)
        return self.send_message_content(session_id, [to_aid], message_content)

    def reply_message(self, msg: dict, message: Union[AssistantMessageBlock, list[AssistantMessageBlock], dict, str]):
        session_id = msg.get("session_id", "")
        if session_id == "":
            log_error("failed to get session id")
            return False
        to_aid_list = [msg.get("sender", "")]
        ref_msg_id = msg.get("message_id", "")
        return self.send_message(session_id, to_aid_list, message, ref_msg_id)

    def quick_send_message(
        self,
        to_aid: str,
        message: Union[AssistantMessageBlock, list[AssistantMessageBlock], dict],
        asnyc_message_result,
        insert_message: bool = True,
    ):
        session_id = self.__quick_send_message_base(to_aid, asnyc_message_result)
        self.send_message(session_id, [to_aid], message, insert_message=insert_message)
        return session_id

    def send_message_content(
        self, session_id: str, to_aid_list: list, llm_content: str, ref_msg_id: str = "", message_id: str = ""
    ):
        # 处理对象转换为字典
        if session_id == "" or session_id is None:
            return
        if llm_content == "" or llm_content is None:
            return
        msg_block = {
            "type": "content",
            "status": "success",
            "timestamp": int(time.time() * 1000),
            "content": llm_content,
        }
        return self.send_message(session_id, to_aid_list, msg_block, ref_msg_id, message_id)

    def insert_message(
        self,
        role,
        aid,
        session_id,
        to_aids,
        message: Union[AssistantMessageBlock, list[AssistantMessageBlock], dict, str],
        parent_message_id="",
        message_id: str = "",
    ):
        # 处理对象转换为字典
        if isinstance(message, (AssistantMessageBlock, dict)):
            message_data = [message.__dict__ if hasattr(message, "__dict__") else message]  # 将字典转换为列表
        elif isinstance(message, list):
            message_data = [msg.__dict__ if hasattr(msg, "__dict__") else msg for msg in message]  # 保持列表类型
        elif isinstance(message, str):
            message_data = [
                {"type": "content", "status": "success", "timestamp": int(time.time() * 1000), "content": message}
            ]  # 将字符串转换为包含单个字典的列表
        if message_id == "" or message_id is None:
            message_id = str(int(time.time() * 1000))
        self.db_manager.insert_message(
            role,
            aid,
            session_id,
            aid,
            parent_message_id,
            ",".join(to_aids),
            "",
            json.dumps(message_data),
            "sent",
            message_id,
        )

    # 发送自定义指令消息
    def send_instruction_message(
        self, session_id: str, to_aid: str, agent_cmd_block: AgentInstructionBlock = None, ref_msg_id: str = ""
    ):
        # 处理对象转换为字典
        if session_id == "" or session_id is None:
            return
        return self.send_message(session_id, [to_aid], None, agent_cmd_block=agent_cmd_block, ref_msg_id=ref_msg_id)

    def send_form_message(self, session_id: str, to_aid_list: [], result: [], ref_msg_id: str):
        try:
            # 处理对象转换为字典
            if session_id == "" or session_id is None:
                return
            save_message_list = self.db_manager.get_message_by_id(self.id, session_id, ref_msg_id)
            if save_message_list is None or len(save_message_list) == 0:
                return
            msg = save_message_list[0]

            msg_block = json.loads(msg["content"])[0]

            if msg_block["type"] != "form":
                return
            form_list = msg_block["content"]
            index = 0
            for form in form_list:
                form["result"] = json.dumps(result[index])
                index = index + 1
            msg["content"] = []
            msg["content"].append(msg_block)
            self.db_manager.update_message(msg)

            msg_array = []
            content = {"result": result}
            msg_block_result = {"type": "form_result", "content": content}
            msg_array.append(msg_block_result)
            return self.session_manager.send_msg(session_id, msg_array, ";".join(to_aid_list), ref_msg_id, "", None)
        except Exception as e:
            log_exception(f"send_form_message failed: {e}")
            return

    def upload_file(self,full_path):
        if self.file_client is None:
            self.file_client = FileClient(self.ca_client.get_aid_certs_path(self.id),self.seed_password,self.id,self.ap,agent_id_ref=self)
            self.file_client.sign_in()
        return self.file_client.post_file(full_path)

    def download_file(self,url,file_path):
        if self.file_client is None:
            domain = url.split("//")[1].split("/")[0]
            # domain = 'oss.modelgate.us'
            main_domain = '.'.join(domain.split('.')[1:])
            self.file_client = FileClient(self.ca_client.get_aid_certs_path(self.id),self.seed_password,self.id,main_domain,agent_id_ref=self)
            self.file_client.sign_in()
        return self.file_client.download_file(url,file_path)

    async def upload_file_async(self, full_path):
        """异步上传文件方法

        Args:
            full_path: 文件的完整路径

        Returns:
            str: 上传成功后的文件URL，失败返回None
        """
        import aiohttp
        import aiofiles
        import os
        from agentcp.file.file_client import FileClient

        try:
            # 初始化文件客户端
            if self.file_client is None:
                self.file_client = FileClient(self.ca_client.get_aid_certs_path(self.id),self.seed_password,self.id, self.ap,agent_id_ref=self)
                # 注意：这里的sign_in仍然是同步的，如果需要完全异步，需要修改FileClient
                self.file_client.sign_in()

            if self.file_client.signature is None:
                print("upload_file_async failed: signature is None")
                return None

            # 准备上传参数
            params = {
                'agent_id': self.file_client.agent_id,
                'signature': self.file_client.signature,
                'file_name': os.path.basename(full_path)
            }

            upload_url = self.file_client.server_url + "/upload_file"

            # 使用aiohttp进行异步文件上传
            async with aiohttp.ClientSession() as session:
                async with aiofiles.open(full_path, 'rb') as file:
                    file_content = await file.read()

                data = aiohttp.FormData()
                # 添加表单参数
                for key, value in params.items():
                    data.add_field(key, value)
                # 添加文件
                data.add_field('file', file_content, filename=os.path.basename(full_path))

                async with session.post(upload_url, data=data, ssl=False) as response:
                    if response.status == 200:
                        result = await response.json()
                        print('文件异步上传成功')
                        return result.get("url")
                    else:
                        print(f'文件异步上传失败，状态码: {response.status}')
                        return None

        except FileNotFoundError:
            print('文件未找到')
            return None
        except Exception as e:
            print(f'异步上传发生错误: {e}')
            return None


    def send_message(
        self,
        sessionId: str,
        to_aid_list: list,
        message: Union[AssistantMessageBlock, list[Union[AssistantMessageBlock]], dict, str],
        ref_msg_id: str = "",
        message_id: str = "",
        agent_cmd_block: AgentInstructionBlock = None,
        insert_message: bool = True
    ):
        # 处理对象转换为字典
        if self.is_online_success == False:
            self.online()
        if self.is_online_success == False:
            return False

        # 处理消息格式转换
        if message == None or message == "":
            message_data = []
        elif isinstance(message, (AssistantMessageBlock, dict)):
            message_data = [message.__dict__ if hasattr(message, "__dict__") else message]  # 将字典转换为列表
        elif isinstance(message, list):
            message_data = [msg.__dict__ if hasattr(msg, "__dict__") else msg for msg in message]  # 保持列表类型
        elif isinstance(message, str):
            message_data = [
                {"type": "content", "status": "success", "timestamp": int(time.time() * 1000), "content": message}
            ]  # 将字符串转换为包含单个字典的列表
        else:
            message_data = []
        if message_id == "" or message_id is None:
            message_id = str(int(time.time() * 1000))
        instruction = ""
        if agent_cmd_block is not None:
            instruction = json.dumps(agent_cmd_block)
        if insert_message:
            self.db_manager.insert_message(
                "user",
                self.id,
                sessionId,
                self.id,
                ref_msg_id,
                ",".join(to_aid_list),
                instruction,
                json.dumps(message_data),
                "text",
                "sent",
                message_id,
            )
        return self.session_manager.send_msg(
            sessionId, message_data, ";".join(to_aid_list), ref_msg_id, message_id, agent_cmd_block
        )

    def get_agent_profile(self, aid_str):
        return self.ap_client.get_agent_profile(aid_str)

    def get_agent_public_data(self):
        return self.ap_client.get_agent_public_data(self.id)

    def sync_public_files(self) -> bool:
        return self.ap_client.sync_public_files(self.public_data_path)
    # https://oss.aid.pub/api/oss/upload_file, post agent_id, signature, file
    # def upload_file():


    def get_my_profile_data(self):
        path = os.path.join(self.public_data_path, "agentprofile.json")
        try:
            with open(path, "r", encoding="utf-8") as file:
                return json.load(file)
        except FileNotFoundError:
            log_error(f"文件不存在: {path}")
            return None
        except json.JSONDecodeError:
            log_error(f"文件格式错误: {path}")
            return None
        except Exception as e:
            log_error(f"读取文件时出错: {path}, 错误: {e}")
            return None

    def get_publisher_info(self):
        return {"publisherAid": self.id, "organization": self.ap, "certificationSignature": self.ap}

    def create_agent_profile(self, json_data, supportDiscover=True):
        check_result = self.__check_agent_profile(json_data)
        if check_result == False:
            raise Exception("agent profile check failed, please check your agent profile")
        public_data_path = self.get_agent_public_path()
        agent_profile_path = os.path.join(public_data_path, "agentprofile.json")
        agent_html_path = os.path.join(public_data_path, "index.html")
        agent_config_path = os.path.join(public_data_path, "config.json")
        if not os.path.exists(agent_config_path):
            self.__create_config_file(agent_config_path, public_data_path, supportDiscover)
        # 如果文件存在，重命名为temp.json
        self.__create_new_file(json_data, agent_profile_path, public_data_path)
        self.__create_html_file(json_data, agent_html_path)
        log_debug("agent profile created successfully")

    def __create_config_file(self, agent_config_path, public_data_path, supportDiscover):
        data = {
            "homepage": "index.html",
            "supportDiscover": supportDiscover,
        }
        self.__create_new_file(data, agent_config_path, public_data_path)

    def __create_html_file(self, json_data, agent_html_path):
        if os.path.exists(agent_html_path):
            os.remove(agent_html_path)
        html_content = parse_html(json_data)
        # 将生成的 HTML 内容写入文件
        with open(agent_html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

    def __create_new_file(self, json_data, agent_profile_path, public_data_path):
        os.path.exists(public_data_path) or os.mkdir(public_data_path)
        # parse_html
        temp_path = os.path.join(public_data_path, "temp.json")
        if os.path.exists(agent_profile_path):
            os.rename(agent_profile_path, temp_path)

        str_data = json.dumps(json_data)
        self.__write_to_file(str_data, agent_profile_path)
        # 删除临时文件
        if os.path.exists(temp_path):
            os.remove(temp_path)

    def __write_to_file(self, data, filename):
        """将JSON数据写入文件，带错误处理"""
        try:
            # 将set类型转换为list
            with open(filename, "w", encoding="utf-8") as file:
                file.write(data)
            log_info(f"成功写入JSON文件: {filename}")
        except (IOError, TypeError) as e:
            log_error(f"写入文件时出错: {e}")
        except Exception as e:
            log_error(f"未知错误: {e}")

    def __check_agent_profile(self, json_data):
        """创建智能体配置文件
        :param json_data: 包含智能体配置信息的字典
        :return: 如果验证通过返回True，否则返回False
        """
        required_fields = {
            "publisherInfo": dict,
            "version": str,
            "lastUpdated": str,
            "name": str,
            "description": str,
            "capabilities": dict,
            "llm": dict,
            "references": dict,
            "authorization": dict,
            "input": dict,
            "output": dict,
            "avaUrl": str,
            "supportStream": bool,
            "supportAsync": bool,
            "permission": list,
        }

        if not isinstance(json_data, dict):
            log_error("json_data 必须是一个字典")
            return False

        ava_url = json_data.get("avaUrl", "")
        if ava_url == "" or (not ava_url.startswith("http://") and not ava_url.startswith("https://")):
            json_data["avaUrl"] = "https://stzbtool.oss-cn-hangzhou.aliyuncs.com/modelunion/acp.png"

        for field, field_type in required_fields.items():
            if field not in json_data:
                log_error(f"缺少必填字段: {field}")
                return False
            if not isinstance(json_data[field], field_type):
                log_error(f"字段 {field} 类型错误，应为 {field_type}")
                return False

        # 检查嵌套字段
        if not all(key in json_data["capabilities"] for key in ["core", "extended"]):
            log_error("capabilities 字段缺少 core 或 extended")
            return False

        if not all(key in json_data["references"] for key in ["knowledgeBases", "tools", "companyInfo", "productInfo"]):
            log_error("references 字段缺少必要子字段")
            return False

        if not all(key in json_data["authorization"] for key in ["modes", "fee", "description", "sla"]):
            log_error("authorization 字段缺少必要子字段")
            return False

        if not all(
            key in json_data["input"] for key in ["types", "formats", "examples", "semantics", "compatibleAids"]
        ):
            log_error("input 字段缺少必要子字段")
            return False

        if not all(
            key in json_data["output"] for key in ["types", "formats", "examples", "semantics", "compatibleAids"]
        ):
            log_error("output 字段缺少必要子字段")
            return False

        log_info("json_data 验证通过")
        return True

    def save_public_file(self, file_path: str, filename: str):
        self.ap_client.save_public_file(file_path, filename)

    def delete_public_file(self, file_path: str):
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                log_info(f"成功删除文件: {file_path}")
                self.ap_client.delete_public_file(file_path)
            else:
                log_error(f"文件不存在: {file_path}")
        except Exception as e:
            log_exception(f"删除文件时出错: {file_path}, 错误: {e}")

    def add_friend_agent(self, aid, name, description, avaUrl):
        self.db_manager.add_friend_agent(aid, name, description, avaUrl)

    def set_friend_name(self, aid, name):
        self.db_manager.set_friend_agent(aid, name)

    def get_friend_agent_list(self):
        return self.db_manager.get_friend_agent_list(self.id)

    def __on_heartbeat_invite_message(self, invite_req):
        session: Session = self.session_manager.join_session(invite_req)

    def __run_message_listeners(self, data):
        """
        运行消息监听器 (旧版本,兼容性保留)
        新版本使用 __async_run_message_listeners
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            session_id = data["session_id"]
            cmd = data.get("instruction", None)
            if session_id in self.message_handlers_session_map:
                tasks = [self.__safe_call(self.message_handlers_session_map[session_id], data)]
                loop.run_until_complete(asyncio.gather(*tasks))
            elif cmd != None and cmd["cmd"] in self.message_handlers_router_map:
                tasks = [self.__safe_call(self.message_handlers_router_map[cmd["cmd"]], data)]
                loop.run_until_complete(asyncio.gather(*tasks))
            else:
                tasks = [self.__safe_call(func, data) for func in self.message_handlers]
                loop.run_until_complete(asyncio.gather(*tasks))
        finally:
            loop.close()

    async def __async_run_message_listeners(self, data):
        """✅ P1-3增强: 异步运行消息监听器（带指标收集）

        这个函数会在工作线程的事件循环中运行
        """
        # ✅ P1-3: 记录 handler 开始时间
        handler_start_time = time.time()
        handler_success = False

        try:
            session_id = data["session_id"]
            cmd = data.get("instruction", None)

            if session_id in self.message_handlers_session_map:
                await self.__safe_call(
                    self.message_handlers_session_map[session_id],
                    data
                )
            elif cmd is not None and cmd.get("cmd") in self.message_handlers_router_map:
                await self.__safe_call(
                    self.message_handlers_router_map[cmd["cmd"]],
                    data
                )
            else:
                # 并发执行所有处理器
                tasks = [
                    self.__safe_call(func, data)
                    for func in self.message_handlers
                ]
                await asyncio.gather(*tasks, return_exceptions=True)

            # ✅ P1-3: Handler 成功执行
            handler_success = True

        except Exception as e:
            log_exception(f"消息处理失败: {e}")
            # ✅ P1-3: Handler 失败
            handler_success = False

        finally:
            # ✅ P1-3: 记录 handler 指标
            handler_latency_ms = (time.time() - handler_start_time) * 1000

            if handler_success:
                self.metrics.record_handler_success(handler_latency_ms)
            else:
                self.metrics.record_handler_failure()

    async def __safe_call(self, func, data):
        import inspect
        import time

        func_name = getattr(func, '__name__', str(func))
        start_time = time.time()
        task = None

        try:
            sig = inspect.signature(func)
            num_params = len(sig.parameters)

            # 检查函数是否为协程函数
            is_coro = asyncio.iscoroutinefunction(func)
            # 如果被装饰器包装，可能需要额外检查
            if hasattr(func, "__wrapped__") and not is_coro:
                is_coro = asyncio.iscoroutinefunction(func.__wrapped__)

            if not is_coro:
                try:
                    if num_params == 2:
                        func(self, data)
                    elif num_params == 1:
                        func(data)
                    else:
                        # Handle cases where parameter count doesn't match expected
                        # Or raise an error, log a warning, etc.
                        print(f"Warning: Function {func_name} has unexpected number of parameters: {num_params}")
                    return
                except Exception as e:
                    print(f"Error calling function: {e}")

            # 处理协程函数（带优雅的超时处理）
            try:
                # 创建协程任务
                if num_params == 2:
                    coro = func(self, data)
                elif num_params == 1:
                    coro = func(data)
                else:
                    # Handle cases where parameter count doesn't match expected
                    print(f"Warning: Async function {func_name} has unexpected number of parameters: {num_params}")
                    return

                # 使用 wait_for 设置超时，并保存任务引用
                task = asyncio.create_task(coro)
                await asyncio.wait_for(asyncio.shield(task), timeout=600.0)  # 10分钟超时

            except asyncio.TimeoutError:
                # 超时处理：尝试优雅取消任务
                elapsed = time.time() - start_time
                print(f"⚠️ [AgentCP] 函数 {func_name} 执行超时 (600s), 实际耗时: {elapsed:.2f}s")

                # 尝试取消任务
                if task and not task.done():
                    print(f"⚠️ [AgentCP] 正在取消超时任务: {func_name}")
                    task.cancel()
                    try:
                        # 等待任务取消完成（最多1秒）
                        await asyncio.wait_for(task, timeout=1.0)
                    except asyncio.CancelledError:
                        print(f"✅ [AgentCP] 任务已成功取消: {func_name}")
                    except asyncio.TimeoutError:
                        print(f"⚠️ [AgentCP] 任务取消超时，强制结束: {func_name}")
                    except Exception as cancel_error:
                        print(f"⚠️ [AgentCP] 取消任务时出错: {cancel_error}")

                # 记录超时信息（不记录完整堆栈，避免日志过长）
                session_id = data.get('session_id', 'unknown')
                message_id = data.get('message_id', 'unknown')
                print(f"⚠️ [AgentCP] 超时详情 - session: {session_id}, message: {message_id}")

            except asyncio.CancelledError:
                # 任务被外部取消
                elapsed = time.time() - start_time
                print(f"⚠️ [AgentCP] 函数 {func_name} 被取消, 耗时: {elapsed:.2f}s")
                # 不重新抛出，避免影响 worker 线程

            except Exception as e:
                # 其他异常
                elapsed = time.time() - start_time
                import traceback
                print(f"❌ [AgentCP] 函数 {func_name} 执行异常 (耗时: {elapsed:.2f}s)")
                print(f"   异常类型: {type(e).__name__}")
                print(f"   异常信息: {str(e)[:200]}")  # 限制错误信息长度
                # 只在调试模式打印完整堆栈
                if os.getenv('DEBUG') == '1':
                    print(f"   完整堆栈:\n{traceback.format_exc()}")

        except Exception as e:
            # 最外层异常保护
            elapsed = time.time() - start_time
            print(f"❌ [AgentCP] __safe_call 异常保护触发 (func: {func_name}, elapsed: {elapsed:.2f}s): {e}")
            # 确保不影响 worker 线程运行

    def __on_member_list_receive(self, data):
        log_info(f"__on_member_list_receive：{data}")

    def fetch_stream_message(self, message_data: dict) -> str:
        session_id = message_data["session_id"]
        message_id = message_data["message_id"]
        message = json.loads(message_data["message"])
        message_list = []  # 修改变量名避免与内置list冲突
        message_temp = None
        if isinstance(message, list):
            message_list = message
            message_temp = message_list[0] if isinstance(message_list[0], dict) else json.loads(message_list[0])
        else:
            message_list.append(message)
            message_temp = message
        save_message_list = self.db_manager.get_message_by_id(self.id, session_id, message_id)
        if "text/event-stream" == message_temp.get("type", ""):
            pull_url = message_temp.get("content", "")
            log_info("pull_url:" + pull_url)
            if pull_url == "":
                return ""
            return self.__fetch_stream_data(pull_url, save_message_list, message_data, message_list)
        return ""

    def __get_vaild_json(self, text):
        try:
            json_data = json.loads(text)
            return json_data
        except Exception:
            return None

    def __fetch_stream_data(self, pull_url, save_message_list, data, message_list):
        """通过 HTTPS 请求拉取流式数据"""
        try:
            session_id = data["session_id"]
            message_id = data["message_id"]
            ref_msg_id = data["ref_msg_id"]
            sender = data["sender"]
            receiver = data["receiver"]
            message = message_list[0]
            message["type"] = "content"
            message["extra"] = pull_url
            message["content"] = ""
            if save_message_list is None or len(save_message_list) == 0:
                self.db_manager.insert_message(
                    "assistant",
                    self.id,
                    session_id,
                    sender,
                    ref_msg_id,
                    receiver,
                    "",
                    json.dumps(message_list),
                    "text",
                    "success",
                    message_id,
                )
            save_message_list = self.db_manager.get_message_by_id(self.id, session_id, message_id)
            if save_message_list is None or len(save_message_list) == 0:
                log_error(f"插入消息失败: {pull_url}")
                return
            msg_block = json.loads(save_message_list[0]["content"])[0]
            pull_url = pull_url + "&agent_id=" + self.id
            # pull_url = pull_url.replace("https://agentunion.cn","https://ts.agentunion.cn")
            try:
                response = requests.get(
                    pull_url, stream=True, verify=False, timeout=(60, 600), proxies={}
                )  # 连接超时60秒，读取超时10分钟
                response.raise_for_status()  # 检查HTTP状态码
                content_text = ""
                is_end = False
                for line in response.iter_lines():
                    if line is None:
                        log_error("保持连接-等待1")
                        continue
                    decoded_line = line.decode("utf-8")
                    if not decoded_line.startswith("data:") and not decoded_line.startswith("event:"):
                        if decoded_line == ": keep-alive":
                            log_error("保持连接-等待2")
                            continue
                        decoded_url = urllib.parse.unquote_plus(decoded_line)
                        if decoded_url is None:
                            log_error("保持连接-等待3")
                            continue

                        chunk = self.__get_vaild_json(decoded_url)
                        # print(chunk)
                        if chunk is None:
                            content_text = content_text + decoded_url
                        else:
                            is_continue = False
                            try:
                                if len(chunk.get("choices", [])) == 0:
                                    continue
                                is_continue = True
                            except Exception:
                                content_text = content_text + decoded_url
                            try:
                                if is_continue:
                                    content_text = content_text + chunk.get("choices", [])[0].get("delta", {}).get(
                                        "content", ""
                                    )
                            except Exception:
                                log_error(f"content_text: {content_text}")

                        msg_block["content"] = content_text
                    else:
                        key, value = decoded_line.split(":", 1)
                        key = key.strip()
                        value = value.strip()
                        if key == "event" and value == "done":
                            log_info("接收到的消息仅为 'done'")
                            is_end = True
                            msg_block["status"] = "success"
                        else:
                            decoded_url = urllib.parse.unquote_plus(value)
                            if decoded_url is None:
                                log_error("保持连接-等待3")
                                continue
                            chunk = self.__get_vaild_json(decoded_url)
                            if chunk is None:
                                content_text = content_text + decoded_url
                            else:
                                is_continue = False
                                try:
                                    if len(chunk.get("choices", [])) == 0:
                                        continue
                                    is_continue = True
                                except Exception:
                                    content_text = content_text + decoded_url
                                try:
                                    if is_continue:
                                        content_text = content_text + chunk.get("choices", [{}])[0].get(
                                            "delta", {}
                                        ).get("content", "")
                                except Exception:
                                    log_error(f"content_text: {content_text}")
                            msg_block["content"] = content_text
                    message_list = []
                    message_list.append(msg_block)
                    save_message_list[0]["content"] = json.dumps(message_list)
                    if is_end:
                        log_info(f"结束拉取流,{msg_block}")
                    self.db_manager.update_message(save_message_list[0])
                return msg_block["content"]
            except requests.exceptions.Timeout:
                log_error(f"请求超时: {pull_url}")
                return ""
            except requests.exceptions.RequestException as e:
                log_error(f"请求失败: {pull_url}, 错误: {str(e)}")
                msg_block["status"] = "error"
                msg_block["type"] = "error"
                msg_block["content"] = "拉取流失败"
                message_list = []
                message_list.append(msg_block)
                save_message_list[0]["content"] = json.dumps(message_list)
                self.db_manager.update_message(save_message_list[0])
                return ""
        except Exception as e:
            import traceback

            log_error(f"拉取流式数据时发生错误: {str(e)}\n{traceback.format_exc()}")
            log_error(f"请求失败: {pull_url}, 错误: {str(e)}")
            msg_block["status"] = "error"
            msg_block["type"] = "error"
            msg_block["content"] = "拉取流失败"
            message_list = []
            message_list.append(msg_block)
            save_message_list[0]["content"] = json.dumps(message_list)
            self.db_manager.update_message(save_message_list[0])
            return ""

    def check_stream_url_exists(self, push_url):
        return self.session_manager.check_stream_url_exists(push_url)

    def __404_message_insert(self, data):
        session_id = data["session_id"]
        acceptor_id = data["acceptor_id"]
        message_list = []
        msg_block = {
            "type": "error",
            "status": "success",
            "timestamp": int(time.time() * 1000),  # 使用毫秒时间戳
            "content": f"该模型的服务商{acceptor_id}不在线 请您前往模型列表确认模型在线状态，或选择该模型的其它服务商重试",
            "extra": "",
        }
        message_list.append(msg_block)
        time.sleep(0.3)
        message_data = {
            "session_id": session_id,
            "ref_msg_id": "",
            "sender": acceptor_id,
            "receiver": self.id,
            "message": json.dumps(message_list),
        }
        self.__run_message_listeners(message_data)

    def __on_invite_ack(self, data):
        status = int(data["status_code"])
        log_info(f"__on_invite_ack:{data}")
        if status == 404:
            thread = threading.Thread(target=self.__404_message_insert, args=(data,))
            thread.start()

    def __on_session_message_ack(self, data):
        status = int(data["status_code"])
        if status == 404:
            offline_receivers: list = data["offline_receivers"]
            log_info(f"offline_receivers:{data}")
            if offline_receivers == None or len(offline_receivers) == 0:
                return
            for receiver in offline_receivers:
                data["acceptor_id"] = receiver
                thread = threading.Thread(target=self.__404_message_insert, args=(data,))
                thread.start()

    def __on_system_message(self, data):
        event_type = data["event_type"]
        session_id = data["session_id"]
        if "Session dismissed" == event_type:
            self.session_manager.leave_session(session_id)

    def __ping_message(self, data):
        msg_array = self.get_content_array_from_message(data)
        if len(msg_array) == 0:
            return False
        if msg_array[0].get("type") == "ping":
            msg_block = {
                "type": "content",
                "status": "success",
                "timestamp": int(time.time() * 1000),  # 使用毫秒时间戳
                "content": "ping_result",
            }
            self.reply_message(data, msg_block)
            return True
        return False

    def _start_message_dispatcher(self):
        """✅ 修复WebSocket阻塞: 启动消息派发线程

        派发线程负责：
        1. 从无阻塞队列中取消息
        2. 调用scheduler提交（可能阻塞）
        3. 执行数据库操作（可能阻塞）
        4. 失败消息记录日志并丢弃
        """
        if self._message_dispatcher_thread and self._message_dispatcher_thread.is_alive():
            return

        self._message_dispatcher_running = True
        self._message_dispatcher_thread = threading.Thread(
            target=self._message_dispatcher_main,
            daemon=True,
            name="MessageDispatcher"
        )
        self._message_dispatcher_thread.start()
        log_info("🚀 消息派发线程已启动")

    def _message_dispatcher_main(self):
        """✅ 修复WebSocket阻塞: 消息派发线程主循环

        工作流程：
        1. 从dispatch_queue取消息（阻塞等待）
        2. 提交到scheduler（允许阻塞，不影响WebSocket）
        3. 执行数据库操作（允许阻塞，不影响WebSocket）
        4. 失败消息记录日志并丢弃
        """
        log_info("🚀 消息派发线程开始运行")

        while self._message_dispatcher_running and not self.shutdown_flag.is_set():
            try:
                # 从队列取消息（阻塞等待，超时1秒）
                try:
                    message_task = self.message_dispatch_queue.get(timeout=1.0)
                except queue.Empty:
                    continue

                data = message_task['data']
                message_id = data.get('message_id', 'unknown')
                session_id = data.get('session_id', 'unknown')
                is_stream_message = message_task.get('is_stream_message', False)
                message_list = message_task.get('message_list', [])
                instruction = message_task.get('instruction')
                sender = data.get('sender', '')
                receiver = data.get('receiver', '')
                ref_msg_id = data.get('ref_msg_id', '')

                # ✅ 提交到scheduler（允许阻塞45秒，不影响WebSocket线程）
                max_retries = 3
                submit_success = False
                last_error = None
                dispatch_start_time = time.time()

                for attempt in range(max_retries):
                    try:
                        if self.use_improved_scheduler:
                            success = self.message_scheduler.submit_message(
                                self.__async_run_message_listeners,
                                data,
                                raise_on_reject=False
                            )

                            if success:
                                submit_success = True
                                dispatch_latency_ms = (time.time() - dispatch_start_time) * 1000
                                self.metrics.record_dispatch_success(dispatch_latency_ms)
                                log_info(f"✅ [Dispatcher] 消息已提交: message_id={message_id[:16]}...")
                                break
                            else:
                                last_error = "调度器拒绝任务"
                        else:
                            # 旧实现
                            def task():
                                with self.thread_lock:
                                    self.active_threads += 1
                                try:
                                    self.__run_message_listeners(data)
                                except Exception as e:
                                    log_exception(f"消息处理失败: {e}")
                                finally:
                                    with self.thread_lock:
                                        self.active_threads -= 1

                            self.thread_pool.submit(task)
                            submit_success = True
                            break

                    except Exception as e:
                        last_error = str(e)

                    # 重试前退避等待
                    if not submit_success and attempt < max_retries - 1:
                        wait_time = 0.05 * (2 ** attempt)
                        time.sleep(wait_time)

                # ✅ 提交失败，记录日志并丢弃消息
                if not submit_success:
                    self.metrics.record_dispatch_failure()
                    log_error(
                        f"❌ [Dispatcher] 消息提交最终失败，已丢弃: "
                        f"message_id={message_id[:16]}... "
                        f"session_id={session_id} "
                        f"error={last_error}"
                    )
                    continue

                # ✅ 提交成功，执行数据库操作（允许阻塞，不影响WebSocket线程）
                if not is_stream_message:
                    try:
                        save_message_list = self.db_manager.get_message_by_id(
                            self.id, session_id, message_id
                        )

                        instruction_str = ""
                        if instruction is not None:
                            instruction_str = json.dumps(instruction)

                        if save_message_list is None or len(save_message_list) == 0:
                            self.db_manager.insert_message(
                                "assistant",
                                self.id,
                                session_id,
                                sender,
                                ref_msg_id,
                                receiver,
                                instruction_str,
                                json.dumps(message_list),
                                "text",
                                "success",
                                message_id,
                            )
                        else:
                            save_message = save_message_list[0]
                            content = save_message["content"]
                            if isinstance(content, list):
                                content.append(message_list)
                            elif isinstance(content, str):
                                content_list = json.loads(content)
                                content_list.append(message_list)
                            save_message["content"] = json.dumps(content_list)
                            self.db_manager.update_message(save_message)

                    except Exception as e:
                        log_exception(f"⚠️ [Dispatcher] 数据库操作失败（消息已派发）: {e}")

            except Exception as e:
                log_exception(f"❌ [Dispatcher] 派发循环异常: {e}")
                time.sleep(0.1)

        log_info("🚀 消息派发线程已停止")

    def _stop_message_dispatcher(self):
        """✅ 修复WebSocket阻塞: 停止消息派发线程"""
        if not self._message_dispatcher_thread:
            return

        self._message_dispatcher_running = False

        if self._message_dispatcher_thread.is_alive():
            self._message_dispatcher_thread.join(timeout=5.0)

        self._message_dispatcher_thread = None
        log_info("✅ 消息派发线程已停止")

    def _start_metrics_sync(self):
        """✅ 启动Metrics定时同步线程

        每2分钟将metrics数据同步到JSON文件
        """
        print(f"[DEBUG] _start_metrics_sync() 被调用")
        if self._metrics_sync_thread and self._metrics_sync_thread.is_alive():
            print(f"[DEBUG] metrics同步线程已存在且运行中，跳过启动")
            return

        print(f"[DEBUG] 准备创建metrics同步线程...")
        self._metrics_sync_running = True
        self._metrics_sync_thread = threading.Thread(
            target=self._metrics_sync_main,
            daemon=True,
            name="MetricsSync"
        )
        print(f"[DEBUG] metrics同步线程已创建，即将启动...")
        self._metrics_sync_thread.start()
        print(f"[DEBUG] metrics同步线程start()调用完成")
        log_info("📊 Metrics同步线程已启动")

    def _metrics_sync_main(self):
        """✅ Metrics定时同步主循环

        启动时立即同步一次，然后每2分钟同步一次metrics数据到JSON文件
        """
        print(f"[DEBUG] _metrics_sync_main() 线程开始执行！")
        log_info("📊 Metrics同步线程开始运行")

        # ✅ 立即同步一次（启动时）
        first_sync = True
        print(f"[DEBUG] 准备进入同步循环...")

        while self._metrics_sync_running and not self.shutdown_flag.is_set():
            try:
                # 如果不是第一次同步，等待2分钟（120秒）
                if not first_sync:
                    for _ in range(120):
                        if not self._metrics_sync_running or self.shutdown_flag.is_set():
                            break
                        time.sleep(1)

                    if not self._metrics_sync_running:
                        break
                else:
                    first_sync = False

                print(f"[DEBUG] 开始同步metrics数据...")

                # 更新队列大小
                self.metrics.dispatch_queue_size = self.message_dispatch_queue.qsize()
                print(f"[DEBUG] 队列大小: {self.metrics.dispatch_queue_size}")

                # 获取metrics摘要
                summary = self.metrics.get_summary()
                print(f"[DEBUG] metrics摘要: received={summary['received_total']}, success={summary['dispatched_success']}")

                # 添加额外信息
                summary['agent_id'] = self.id
                summary['agent_name'] = self.name
                summary['timestamp'] = time.time()
                summary['timestamp_str'] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
                print(f"[DEBUG] 准备写入文件: {self.metrics_file_path}")

                # 写入JSON文件
                import json
                with open(self.metrics_file_path, 'w', encoding='utf-8') as f:
                    json.dump(summary, f, indent=2, ensure_ascii=False)
                print(f"[DEBUG] 文件写入成功！")

                log_info(
                    f"📊 Metrics已同步到文件: {self.metrics_file_path} "
                    f"(接收:{summary['received_total']}, "
                    f"成功:{summary['dispatched_success']}, "
                    f"失败:{summary['dispatched_failed']})"
                )

            except Exception as e:
                print(f"[DEBUG] ❌ Metrics同步发生异常: {e}")
                import traceback
                traceback.print_exc()
                log_exception(f"❌ Metrics同步失败: {e}")
                time.sleep(10)  # 失败后等待10秒再重试

        print(f"[DEBUG] Metrics同步线程退出循环")
        log_info("📊 Metrics同步线程已停止")

    def _stop_metrics_sync(self):
        """✅ 停止Metrics定时同步线程"""
        if not self._metrics_sync_thread:
            return

        self._metrics_sync_running = False

        if self._metrics_sync_thread.is_alive():
            self._metrics_sync_thread.join(timeout=5.0)

        self._metrics_sync_thread = None
        log_info("✅ Metrics同步线程已停止")


    def __agentid_message_listener(self, data):
        """✅ 修复WebSocket阻塞: 快速入队，不阻塞WebSocket线程

        修改要点：
        1. WebSocket线程只负责解析消息并快速入队
        2. 不执行任何阻塞操作（scheduler提交、数据库操作）
        3. 使用put_nowait避免阻塞，队列满时记录错误
        4. 所有重操作由独立的dispatcher线程处理
        """
        # ✅ P1-3: 记录收到消息
        #print(f"[DEBUG] __agentid_message_listener 收到消息，长度: {len(data)}")
        self.metrics.record_received()
        #print(f"[DEBUG] metrics.record_received()调用完成，当前received_total: {self.metrics.received_total}")

        log_info(f"received a message in agentcp: {len(data)}")
        if self.__ping_message(data):
            return

        session_id = data.get("session_id", "unknown")
        message_id = data.get("message_id", "unknown")

        # 快速解析消息内容
        try:
            message = json.loads(data["message"])

            # 解析消息内容
            message_list = []
            message_temp = None
            if isinstance(message, list):
                message_list = message
                message_temp = message_list[0] if isinstance(message_list[0], dict) else json.loads(message_list[0])
            else:
                message_list.append(message)
                message_temp = message

            # 判断是否为流消息
            is_stream_message = message_temp.get("type", "") == "text/event-stream"

            # 构造任务对象
            message_task = {
                'data': data,
                'is_stream_message': is_stream_message,
                'message_list': message_list,
                'instruction': data.get("instruction", None)
            }

            # ✅ 快速入队（无阻塞）
            try:
                self.message_dispatch_queue.put_nowait(message_task)
                log_debug(f"✅ [WebSocket] 消息已入队: message_id={message_id[:16]}... queue_size={self.message_dispatch_queue.qsize()}")
            except queue.Full:
                # 队列满，丢弃消息并记录错误
                self.metrics.record_dispatch_failure()
                log_error(
                    f"❌ [WebSocket] 派发队列已满 (10000)，消息丢弃: "
                    f"message_id={message_id[:16]}... session_id={session_id}"
                )
                # 队列满时直接丢弃，不重试

        except Exception as e:
            log_exception(f"❌ [WebSocket] 消息解析失败: {e}")

    def __insert_session(self, aid, session_id, identifying_code, name):
        conversation = self.db_manager.get_conversation_by_id(aid, session_id)
        if conversation is None:
            # identifying_code,name, type,to_aid_list
            self.db_manager.create_session(aid, session_id, identifying_code, name, "public")
        return

    def __connect(self):
        if not hasattr(self, "_heartbeat_thread") or not self._heartbeat_thread.is_alive():
            self._heartbeat_thread = threading.Thread(target=self.heartbeat_client.online)
            self._heartbeat_thread.start()
        self.heartbeat_client.set_on_recv_invite(self.__on_heartbeat_invite_message)
        log_info(f"agentid {self.id} is ready!")

    def get_agent_list(self):
        """获取所有agentid列表"""
        return self.ap_client.get_agent_list()

    def get_all_public_data(self):
        """获取所有agentid列表"""
        return self.ap_client.get_all_public_data()

    def get_session_member_list(self, session_id):
        return self.db_manager.get_session_member_list(session_id)

    def update_aid_info(self, aid, avaUrl, name, description):
        self.db_manager.update_aid_info(aid, avaUrl, name, description)
        return True

    def message_handler(self, router: str = ""):
        def decorator(func):
            self.add_message_handler(func, router=router)
            return func

        return decorator

    def get_llm_url(self, target_aid: str):
        base_url = get_base_url(self, target_aid)
        return base_url

    def get_llm_api_key(self):
        llm_app_key = get_llm_api_key(self.id)
        return llm_app_key

    def add_llm_api_key(self, aid_str: str, llm_api_key: str):
        if aid_str != self.id:
            return False
        return add_llm_api_key(self, llm_api_key)

    def reset(self, wait_timeout: float = 5.0) -> bool:
        """
        彻底重置 AgentID，清理所有资源，恢复到初始状态

        重置后可以重新调用 online() 走完整初始化流程

        清理内容:
        1. 停止所有内部线程（消息派发、metrics同步、监控服务）
        2. 清理 session_manager（包括所有 MessageClient 和 WebSocket 连接）
        3. 清理 heartbeat_client
        4. 清空消息队列和 handlers
        5. 重置在线状态

        Args:
            wait_timeout: 等待线程结束的超时时间（秒）

        Returns:
            bool: 重置是否成功完成（部分失败也返回 True，会记录警告）
        """
        log_info(f"🔄 [AgentID] 开始重置: {self.id}")
        print(f"[AgentID] ========== 开始重置 ==========")

        reset_success = True

        try:
            # 1. 标记为离线状态（立即生效，阻止新请求）
            self.is_online_success = False
            print(f"[AgentID] ✓ 已标记为离线状态")

            # 2. 停止消息派发线程
            print(f"[AgentID] 正在停止消息派发线程...")
            try:
                if hasattr(self, '_stop_message_dispatcher'):
                    self._stop_message_dispatcher()
                print(f"[AgentID] ✓ 消息派发线程已停止")
            except Exception as e:
                log_warning(f"[AgentID] 停止消息派发线程失败（继续重置）: {e}")
                reset_success = False

            # 3. 停止 metrics 同步线程
            print(f"[AgentID] 正在停止 metrics 同步线程...")
            try:
                if hasattr(self, '_stop_metrics_sync'):
                    self._stop_metrics_sync()
                print(f"[AgentID] ✓ Metrics 同步线程已停止")
            except Exception as e:
                log_warning(f"[AgentID] 停止 metrics 同步线程失败（继续重置）: {e}")

            # 4. 停止监控服务
            print(f"[AgentID] 正在停止监控服务...")
            try:
                if hasattr(self, 'monitoring_service') and self.monitoring_service is not None:
                    self.monitoring_service.stop(wait=False)
                    self.monitoring_service = None
                print(f"[AgentID] ✓ 监控服务已停止")
            except Exception as e:
                log_warning(f"[AgentID] 停止监控服务失败（继续重置）: {e}")

            # 5. 清理 session_manager（包括所有 WebSocket 连接）
            print(f"[AgentID] 正在清理 session_manager...")
            try:
                if self.session_manager is not None:
                    self._reset_session_manager(wait_timeout)
                    self.session_manager = None
                print(f"[AgentID] ✓ Session manager 已清理")
            except Exception as e:
                log_error(f"[AgentID] 清理 session_manager 失败: {e}")
                reset_success = False

            # 6. 清理 heartbeat_client
            print(f"[AgentID] 正在清理 heartbeat_client...")
            try:
                if self.heartbeat_client is not None:
                    try:
                        self.heartbeat_client.offline()
                    except Exception:
                        pass
                    try:
                        self.heartbeat_client.sign_out()
                    except Exception:
                        pass
                    self.heartbeat_client = None
                print(f"[AgentID] ✓ Heartbeat client 已清理")
            except Exception as e:
                log_warning(f"[AgentID] 清理 heartbeat_client 失败（继续重置）: {e}")

            # 7. 清空消息派发队列
            print(f"[AgentID] 正在清空消息队列...")
            try:
                cleared_count = 0
                if hasattr(self, 'message_dispatch_queue'):
                    while not self.message_dispatch_queue.empty():
                        try:
                            self.message_dispatch_queue.get_nowait()
                            cleared_count += 1
                        except queue.Empty:
                            break
                print(f"[AgentID] ✓ 已清空 {cleared_count} 条待处理消息")
            except Exception as e:
                log_warning(f"[AgentID] 清空消息队列失败（继续重置）: {e}")

            # 8. 清空 message handlers 的 session 级别映射（保留全局 handlers）
            print(f"[AgentID] 正在清理 handler 映射...")
            try:
                self.message_handlers_session_map.clear()
                self.message_handlers_router_map.clear()
                print(f"[AgentID] ✓ Handler 映射已清理")
            except Exception as e:
                log_warning(f"[AgentID] 清理 handler 映射失败（继续重置）: {e}")

            # 9. 重新启动消息派发线程（为下次 online 做准备）
            print(f"[AgentID] 正在重新启动消息派发线程...")
            try:
                if hasattr(self, '_start_message_dispatcher'):
                    self._start_message_dispatcher()
                print(f"[AgentID] ✓ 消息派发线程已重新启动")
            except Exception as e:
                log_error(f"[AgentID] 重新启动消息派发线程失败: {e}")
                reset_success = False

            # 10. 重新启动 metrics 同步线程
            print(f"[AgentID] 正在重新启动 metrics 同步线程...")
            try:
                if hasattr(self, '_start_metrics_sync'):
                    self._start_metrics_sync()
                print(f"[AgentID] ✓ Metrics 同步线程已重新启动")
            except Exception as e:
                log_warning(f"[AgentID] 重新启动 metrics 同步线程失败: {e}")

            print(f"[AgentID] ========== 重置完成 ==========")
            log_info(f"✅ [AgentID] 重置完成: {self.id}, 成功={reset_success}")

            return reset_success

        except Exception as e:
            log_error(f"❌ [AgentID] 重置过程发生异常: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _reset_session_manager(self, wait_timeout: float):
        """
        彻底重置 SessionManager，包括所有 MessageClient 和 WebSocket 连接

        Args:
            wait_timeout: 等待线程结束的超时时间（秒）
        """
        if self.session_manager is None:
            return

        sm = self.session_manager

        # 1. 关闭所有 session
        print(f"[AgentID] 正在关闭所有 sessions...")
        try:
            sm.close_all_session()
        except Exception as e:
            log_warning(f"[AgentID] close_all_session 失败: {e}")

        # 2. 停止所有 MessageClient 的 WebSocket 连接
        print(f"[AgentID] 正在停止所有 MessageClient...")
        if hasattr(sm, 'message_client_map'):
            for server_url, message_client in list(sm.message_client_map.items()):
                try:
                    if message_client is not None:
                        # 设置关闭标志
                        message_client._shutdown_requested = True
                        # 调用完全重置方法（如果存在）
                        if hasattr(message_client, 'full_reset'):
                            message_client.full_reset()
                        else:
                            message_client.stop_websocket_client()
                        print(f"[AgentID] ✓ MessageClient 已停止: {server_url[:50]}...")
                except Exception as e:
                    log_warning(f"[AgentID] 停止 MessageClient 失败: {e}")

        # 3. 清空所有映射
        if hasattr(sm, 'sessions'):
            sm.sessions.clear()
        if hasattr(sm, 'message_client_map'):
            sm.message_client_map.clear()
        if hasattr(sm, 'message_server_map'):
            sm.message_server_map.clear()
        if hasattr(sm, 'create_session_queue_map'):
            sm.create_session_queue_map.clear()

        print(f"[AgentID] ✓ SessionManager 所有映射已清空")

    def reset_and_reconnect(self) -> bool:
        """
        重置并重新连接的便捷方法

        等同于: reset() + online()

        Returns:
            bool: 是否成功重新连接
        """
        log_info(f"🔄 [AgentID] 开始重置并重连: {self.id}")

        # 1. 重置
        reset_ok = self.reset()
        if not reset_ok:
            log_warning("[AgentID] 重置部分失败，但继续尝试重连...")

        # 2. 等待一小段时间确保资源完全释放
        time.sleep(0.5)

        # 3. 重新上线
        try:
            self.online()

            if self.is_online_success:
                log_info(f"✅ [AgentID] 重置并重连成功: {self.id}")
                return True
            else:
                log_error(f"❌ [AgentID] 重连后仍未在线: {self.id}")
                return False

        except Exception as e:
            log_error(f"❌ [AgentID] 重连过程异常: {e}")
            import traceback
            traceback.print_exc()
            return False

    def set_disconnect_callback(self, callback: callable) -> None:
        """设置 WebSocket 断开回调

        当任意 MessageClient 的 WebSocket 连接断开时，会调用此回调函数。
        外部可以通过此回调实现自动重建逻辑。

        回调函数签名: callback(agent_id: str, server_url: str, code: int, reason: str)

        Args:
            callback: 断开时调用的回调函数

        示例:
            def on_disconnect(agent_id, server_url, code, reason):
                print(f"连接断开: {agent_id} -> {server_url}, code={code}, reason={reason}")
                # 触发重建逻辑...

            agentId.set_disconnect_callback(on_disconnect)
        """
        log_info(f"[AgentID] 设置断开回调: {callback}")

        # 保存回调引用，用于新创建的 MessageClient
        self._disconnect_callback = callback

        # 为所有现有的 MessageClient 设置回调
        if self.session_manager and hasattr(self.session_manager, 'message_client_map'):
            for server_url, mc in self.session_manager.message_client_map.items():
                if mc and hasattr(mc, 'set_disconnect_callback'):
                    mc.set_disconnect_callback(callback)
                    log_info(f"[AgentID] 已为 MessageClient({server_url}) 设置断开回调")

    # ==================== MessageClient 管理 API ====================

    def get_message_client(self, server_url: str = None):
        """✅ 获取 MessageClient 实例

        Args:
            server_url: 消息服务器 URL（可选，不传则返回第一个）

        Returns:
            MessageClient 实例，不存在返回 None
        """
        if not self.session_manager or not hasattr(self.session_manager, 'message_client_map'):
            return None

        if server_url:
            return self.session_manager.message_client_map.get(server_url.rstrip("/"))
        else:
            # 返回第一个
            for mc in self.session_manager.message_client_map.values():
                return mc
            return None

    def get_all_message_clients(self) -> dict:
        """✅ 获取所有 MessageClient 实例

        Returns:
            {server_url: MessageClient} 字典
        """
        if not self.session_manager or not hasattr(self.session_manager, 'message_client_map'):
            return {}
        return dict(self.session_manager.message_client_map)

    def is_connection_healthy(self, server_url: str = None) -> bool:
        """✅ 检查连接是否健康

        Args:
            server_url: 消息服务器 URL（可选，不传则检查所有连接）

        Returns:
            True: 连接健康
            False: 连接不健康或不存在
        """
        if server_url:
            mc = self.get_message_client(server_url)
            return mc.is_healthy() if mc else False
        else:
            # 检查所有连接
            for mc in self.get_all_message_clients().values():
                if not mc.is_healthy():
                    return False
            return len(self.get_all_message_clients()) > 0

    def get_connection_status(self, server_url: str = None) -> dict:
        """✅ 获取连接状态信息

        Args:
            server_url: 消息服务器 URL（可选）

        Returns:
            连接状态信息字典
        """
        if server_url:
            mc = self.get_message_client(server_url)
            if mc:
                return mc.get_connection_info()
            return {"error": "连接不存在", "server_url": server_url}
        else:
            result = {
                "agent_id": self.id,
                "is_online": self.is_online_success,
                "connections": []
            }
            for url, mc in self.get_all_message_clients().items():
                result["connections"].append(mc.get_connection_info())
            return result

    def get_connection_health_summary(self) -> str:
        """✅ 获取连接健康状态摘要（用于日志/调试）

        Returns:
            健康状态摘要字符串
        """
        clients = self.get_all_message_clients()
        if not clients:
            return f"🔴 {self.id}: 无连接"

        summaries = []
        for url, mc in clients.items():
            summaries.append(f"  [{url}] {mc.get_health_summary()}")

        return f"📊 {self.id} 连接状态:\n" + "\n".join(summaries)

    def rebuild_message_client(self, server_url: str = None) -> bool:
        """✅ 销毁并重建 MessageClient

        这会断开现有连接，创建新的 MessageClient 实例。
        用于连接出现严重问题时的恢复。

        Args:
            server_url: 消息服务器 URL（可选，不传则重建所有）

        Returns:
            True: 重建成功
            False: 重建失败
        """
        if not self.session_manager:
            log_error("[AgentID] SessionManager 不存在，无法重建")
            return False

        if server_url:
            return self._rebuild_single_message_client(server_url)
        else:
            # 重建所有
            success = True
            for url in list(self.get_all_message_clients().keys()):
                if not self._rebuild_single_message_client(url):
                    success = False
            return success

    def _rebuild_single_message_client(self, server_url: str) -> bool:
        """重建单个 MessageClient"""
        server_url = server_url.rstrip("/")
        log_info(f"[AgentID] 开始重建 MessageClient: {server_url}")

        try:
            sm = self.session_manager
            old_mc = sm.message_client_map.get(server_url)

            if old_mc:
                # 1. 停止旧连接
                log_info(f"[AgentID] 停止旧连接...")
                try:
                    old_mc.stop_websocket_client()
                except Exception as e:
                    log_warning(f"[AgentID] 停止旧连接异常: {e}")

                # 2. 等待资源释放
                time.sleep(0.5)

            # 3. 创建新连接
            log_info(f"[AgentID] 创建新连接...")
            from agentcp.msg.message_client import MessageClient
            cache_auth_client = sm.message_server_map.get(server_url)

            new_mc = MessageClient(
                self.id,
                server_url,
                self.ca_client.get_aid_certs_path(self.id),
                self.seed_password,
                cache_auth_client
            )
            new_mc.initialize()
            new_mc.set_message_handler(sm)

            # 4. 设置回调
            if self._disconnect_callback:
                new_mc.set_disconnect_callback(self._disconnect_callback)

            # 5. 启动连接
            if new_mc.start_websocket_client():
                sm.message_client_map[server_url] = new_mc
                sm.message_server_map[server_url] = new_mc.auth_client
                log_info(f"✅ [AgentID] MessageClient 重建成功: {server_url}")
                return True
            else:
                log_error(f"❌ [AgentID] MessageClient 启动失败: {server_url}")
                return False

        except Exception as e:
            log_error(f"❌ [AgentID] 重建 MessageClient 异常: {e}")
            import traceback
            traceback.print_exc()
            return False

    def force_reconnect(self, server_url: str = None) -> bool:
        """✅ 强制触发重连

        不销毁 MessageClient，只是触发其重连逻辑。
        比 rebuild_message_client 更轻量。

        Args:
            server_url: 消息服务器 URL（可选，不传则重连所有）

        Returns:
            True: 重连成功
            False: 重连失败
        """
        if server_url:
            mc = self.get_message_client(server_url)
            if not mc:
                return False
            log_info(f"[AgentID] 强制重连: {server_url}")
            mc.stop_websocket_client()
            time.sleep(0.2)
            return mc.start_websocket_client()
        else:
            success = True
            for url, mc in self.get_all_message_clients().items():
                log_info(f"[AgentID] 强制重连: {url}")
                mc.stop_websocket_client()
                time.sleep(0.2)
                if not mc.start_websocket_client():
                    success = False
            return success

    # ==================== 原有方法 ====================

    def __repr__(self):
        return f"AgentId(aid={self.id})"

    def get_sender_from_message(self, message):
        if isinstance(message, dict):
            return message.get("sender")
        return None  # 如果不是字典，返回None或抛出异常，取决于你的需求

    def get_session_id_from_message(self, message):
        if isinstance(message, dict):
            return message.get("session_id")
        return None  # 如果不是字典，返回None或抛出异常，取决于你的需求

    def get_receiver_from_message(self, message):
        if isinstance(message, dict):
            return message.get("receiver")
        return None  # 如果不是字典，返回None或抛出异常，取决于你的需求

    def get_content_from_message(self, message, message_type="content"):
        message_array = self.get_content_array_from_message(message)
        for item in message_array:
            if isinstance(item, dict) and item.get("type") == message_type:
                # 这里可以执行你需要的操作，例如打印 content 字段
                content = item.get("content", "")
                try:
                    content_json = json.loads(content)  # 尝试解析为 JSON
                    if isinstance(content_json, dict) and "text" in content_json:  # 检查是否为字典且包含 'text'
                        return content_json["text"]
                except Exception:
                    return content
                return content
        if message_type == "content":
            return self.get_content_from_message(message, message_type="text")
        return None  # 如果不是字典，返回None或抛出异常，取决于你的需求

    def __str__(self):
        return self.id

    # 尝试解析 content 为 JSON 格式
    def get_content_array_from_message(self, message):
        # 消息数组
        message_content = message.get("message", "")
        message_array = []
        if isinstance(message_content, str):
            try:
                if message_content.strip():  # 检查内容是否非空
                    llm_content_json_array = json.loads(message_content)
                    if isinstance(llm_content_json_array, list) and len(llm_content_json_array) > 0:
                        return llm_content_json_array  # 返回整个数组而不是第一个元素的 conten
                    else:
                        message_array.append(llm_content_json_array)
                        return message_array
                else:
                    log_info("收到空消息内容")
                    return []
            except json.JSONDecodeError:
                log_error(f"无法解析的消息内容: {message_content}")
                return []
        elif isinstance(message_content, list) and len(message_content) > 0:
            return message_content
        else:
            log_error("无效的消息格式")
            return []

    async def send_stream_message(
        self, session_id: str, to_aid_list: list, response, type="text/event-stream", file_path:str = "",ref_msg_id: str = ""
    ):
        # 处理对象转换为字典
        if type == "file/binary" and (file_path == "" or not os.path.exists(file_path)):
            return False,"文件不存在"
        stream_result = await self.create_stream(session_id, to_aid_list, type, ref_msg_id)
        push_url, pull_url = stream_result
        if push_url is None:
            log_error(f"{pull_url}")
            msg_block = {
                "type": "error",
                "status": "success",
                "timestamp": int(time.time() * 1000),
                "content": f"{pull_url}",
            }
            self.send_message(session_id, to_aid_list, msg_block)
            return None

        msg_block = {
            "type": type,
            "status": "loading",
            "timestamp": int(time.time() * 1000),
            "content": pull_url,
        }

        if type == "file/binary":
            from agentcp.utils.file_util import get_file_info
            msg_block["extra"] = get_file_info(file_path)

        self.send_message(session_id, to_aid_list, msg_block)
        if type=="text/event-stream":
            for chunk in response:
                chunk_str = json.dumps(chunk, default=lambda x: vars(x), ensure_ascii=False)
                log_info(f"chunk_str = {chunk_str}")
                self.send_chunk_to_stream(session_id, push_url, chunk_str,type = type)
        elif type=="file/binary":
            failed_counter = 0
            with open(file_path, "rb") as f:
                offset = 0
                for byte_block in iter(lambda: f.read(16384), b""):
                    result = self.send_chunk_to_file_stream(session_id, push_url,offset, byte_block)
                    offset += len(byte_block)
                    if not result:
                        failed_counter += 1
                        log_error(f"send_chunk_to_file_stream failed, session {session_id} failed_counter={failed_counter}")
                        time.sleep(failed_counter * 0.1)
                        if failed_counter >= 10:
                            break
                    else:
                        failed_counter = 0
        self.close_stream(session_id, push_url)
        return True

    def ping_aid(self, aid: str):
        start_time = time.time()
        msg_block = {"type": "ping", "status": "success", "timestamp": int(time.time() * 1000), "content": "ping"}
        ping_queue = queue.Queue()

        async def asnyc_message_result(message):
            end_time = time.time()
            cost_time = end_time - start_time
            ping_queue.put(cost_time)

        self.quick_send_message(aid, msg_block, asnyc_message_result, insert_message=False)
        try:
            ping = ping_queue.get(timeout=10)
        except queue.Empty:
            log_info(f"ping_aid {aid} timeout")
            ping = 10000
        return ping


class AgentCP(_AgentCP):
    def __init__(
        self,
        agent_data_path,
        certificate_path: str = "",
        seed_password: str = "",
        debug=False,
        log_level: int = logging.INFO,
        port: int = 0,
        run_proxy: bool = True,
    ) -> None:
        super().__init__()
        if agent_data_path == "" or agent_data_path is None:
            raise Exception("agent_data_path 不能为空")
        else:
            self.app_path = os.path.join(agent_data_path, "agentcp")
        self.seed_password = self.__get_sha256(seed_password)
        super().__init__()
        if agent_data_path == "" or agent_data_path is None:
            raise Exception("agent_data_path 不能为空")
        else:
            self.app_path = os.path.join(agent_data_path, "agentcp")
        self.seed_password = self.__get_sha256(seed_password)
        if certificate_path == "" or certificate_path is None:
            certificate_path = self.app_path
        self.aid_path = os.path.join(certificate_path, "AIDs")
        os.path.exists(self.aid_path) or os.makedirs(self.aid_path)
        set_log_enabled(debug, log_level)
        self.ca_client = None
        self.ep_url = None
        self.debug = debug
        self.aid_map = {}
        if run_proxy:
            self.run_llm_proxy(port)

    def run_llm_proxy(self, port):
        if llm_server_is_running():
            log_info("本地服务已启动")
            return
        run_server(self.debug, port=port)
        # 等待local server 在异步线程中启动
        time.sleep(0.4)

    def get_llm_url(self, target_aid: str):
        base_url = get_base_url(self, target_aid)
        return base_url

    def get_llm_api_key(self, aid_str: str):
        return get_llm_api_key(aid_str)

    def __enter__(self):
        """进入上下文时返回实例自身"""
        return self

    def set_seed_password(self, seed_password: str):
        self.seed_password = self.__get_sha256(seed_password)

    def modify_seed_password(self, seed_password: str):
        new_seed_password = self.__get_sha256(seed_password)
        aid_list = self.get_aid_list()
        for aid_str in aid_list:
            # 加载aid
            private_key = self.__load_aid_private_key(aid_str)
            if private_key is None:
                log_error(f"加载失败aid: {aid_str}")
                continue
            try:
                self.ca_client.modify_seed_password(aid_str, private_key, new_seed_password)
                log_error(f"修改密码种子成功aid: {aid_str}")
            except Exception as e:
                log_error(f"修改密码种子失败aid: {aid_str}, 错误: {str(e)}")

    def __load_aid_private_key(self, agent_id: str):
        self.__build_url(agent_id)
        try:
            private_key = self.ca_client.load_private_key(agent_id)
            return private_key
        except Exception as e:
            log_exception(f"加载和验证密钥对时出错: {e}")  # 调试用
            return None

    def get_agent_data_path(self):
        return self.app_path

    def __get_sha256(self, input_str: str) -> str:
        sha256_hash = hashlib.sha256()
        sha256_hash.update(input_str.encode("utf-8"))
        return sha256_hash.hexdigest()

    def save_aid_info(self, agent_id: str, seed_password: str, private_key: str, cert: str) -> AgentID:
        private_key_ = serialization.load_pem_private_key(
            private_key.encode("utf-8"), password=self.__get_sha256(seed_password).encode("utf-8")
        )
        self.ca_client.save_private_key_to_file(agent_id, private_key_)
        self.ca_client.save_cert_to_file(agent_id, cert)

    def __build_url(self, aid: str):
        aid_array = aid.split(".")
        if len(aid_array) < 3:
            raise RuntimeError("加载aid错误,请检查传入aid")
        end_str = f"{aid_array[-2]}.{aid_array[-1]}"
        self.ca_client = CAClient("https://acp3." + end_str, self.aid_path, self.seed_password)
        self.ep_url = "https://acp3." + end_str

    def load_aid(self, agent_id: str) -> AgentID:
        self.__build_url(agent_id)
        try:
            log_debug(f"load agentid: {agent_id}")
            if self.ca_client.aid_is_not_exist(agent_id):  # 检查返回结果是否有效
                log_error(f"未找到agent_id: {agent_id} 或数据不完整")
                return None
            aid = AgentID(agent_id, self.app_path, self.seed_password, self.ca_client, self.ep_url, debug=self.debug)
            ep_url = self.ca_client.resign_csr(agent_id)
            if ep_url:
                return aid
            return None
        except Exception as e:
            log_exception(f"加载和验证密钥对时出错: {e}")  # 调试用
            return None

    def read_private_key(self, agent_id: str):
        self.__build_url(agent_id)
        private_key = self.ca_client.load_private_key_str(agent_id, self.seed_password)
        return private_key

    def read_certificate_pem(self, agent_id: str):
        self.__build_url(agent_id)
        private_key = self.ca_client.load_certificate_pem(agent_id)
        return private_key

    def __build_id(self, id: str):
        ep = self.ep_url.split(".")
        end_str = f"{ep[-2]}.{ep[-1]}"
        if id.endswith(end_str):
            return id
        return f"{id}.{ep[-2]}.{ep[-1]}"

    def get_guest_aid(self, ep_url: str):
        self.ca_client = CAClient("https://acp3." + ep_url, self.aid_path, self.seed_password)
        self.ep_url = "https://acp3." + ep_url
        guest_aid = self.ca_client.get_guest_aid()
        if guest_aid:
            return self.load_aid(guest_aid)
        raise RuntimeError("获取guest aid失败")

    def create_aid(self, ap: str, agent_name: str) -> AgentID:
        if agent_name.startswith("guest"):
            return self.get_guest_aid(ap)

        self.ca_client = CAClient("https://acp3." + ap, self.aid_path, self.seed_password)
        self.ep_url = "https://acp3." + ap
        if not self.ca_client.aid_is_not_exist(agent_name + "." + ap):
            return self.load_aid(agent_name + "." + ap)

        agent_id = self.__build_id(agent_name)
        log_debug(f"create agentid: {agent_id}")
        result = self.ca_client.send_csr_to_server(agent_id)
        if result == True:
            return self.load_aid(agent_id)
        raise RuntimeError(result)


    def get_aid_list(self) -> list:
        path = os.path.join(self.aid_path)
        aid_list = []
        for entry in os.scandir(path):
            array = entry.name.split(".")
            if entry.is_dir() and len(array) == 3:
                aid_list.append(entry.name)
        return aid_list

    def add_message_handler(self, handler: typing.Callable[[dict], typing.Awaitable[None]], aid_str: str):
        """消息监听器装饰器"""
        log_debug("add message handler")
        if not aid_str:
            raise ValueError("aid_str 不能为空")
        aid_acp_array = aid_str.split(".")
        if len(aid_acp_array) < 3:
            raise ValueError("aid_str 格式错误")
        ap = ".".join(aid_acp_array[1:])
        name = aid_acp_array[0]
        aid: AgentID = self.create_aid(ap, name)
        if aid is None:
            raise RuntimeError("加载aid失败")
        aid.online()
        self.aid_map[aid_str] = aid
        aid.add_message_handler(handler, from_acp=True)

    def get_aid(self, aid_str: str) -> AgentID:
        return self.aid_map.get(aid_str)

    def message_handler(self, aid_str):
        def decorator(func):
            self.add_message_handler(func, aid_str=aid_str)
            return func

        return decorator

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文时执行资源清理"""
        # 触发关闭标志（继承自_AggentCP）
        self.shutdown_flag.set()

        # 清理所有AgentID的资源
        for aid in self.aid_map.values():
            if hasattr(aid, "offline"):
                aid.offline()
        # 其他需要清理的资源（如日志、连接等）
        log_info("AgentCP上下文退出，资源已清理")
