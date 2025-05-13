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
import abc
import array
import json
import asyncio

from dataclasses import dataclass
from tabnanny import check
import time
from typing import  Union
import typing
import signal
import threading
from venv import logger
import requests

from agentcp.log import log_debug, log_info, log_error, set_log_enabled,log_exception
from agentcp.ap_client import ApClient
from agentcp.heartbeat_client import HeartbeatClient
from agentcp.db.db_mananger import DBManager
from agentcp.message import AssistantMessageBlock
from agentcp.session_manager import SessionManager, Session
from agentcp.ca_client import CAClient
import urllib.parse
import hashlib
import os
from agentcp.html_util import parse_html
from agentcp.ca_root import CARoot


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
        signal.signal(signal.SIGTERM, self.signal_handle)
        signal.signal(signal.SIGINT, self.signal_handle)
        self.exit_hook_func = exit_hook_func
        
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
    def __init__(self, id:str,app_path:str,seed_password:str,ca_client,ep_url):
        super().__init__()       
        self.public_data_path = os.path.join(app_path, "AIDs",id,"public")
        self.private_data_path = os.path.join(app_path, "AIDs",id,"private")
        os.path.exists(self.public_data_path) or os.makedirs(self.public_data_path)
        os.path.exists(self.private_data_path) or os.makedirs(self.private_data_path)
        self.ca_root_path = os.path.join(app_path,"Certs","root")
        os.path.exists(self.ca_root_path) or os.makedirs(self.ca_root_path)
        ca_root = CARoot()
        ca_root.set_ca_root_crt(self.ca_root_path)
        self.id = id
        array = id.split(".")
        self.ap = array[-2]+"."+array[-1]
        self.name = ""
        self.avaUrl = ""
        self.description = ""
        self.ap_client = None
        self.session_manager = None
        self.ca_client:CAClient = ca_client
        self.ep_url = ep_url
        self.seed_password = seed_password
        self.message_handlers = []  # 添加消息监听器属性
        self.message_handlers_map = {}  # 添加消息监听器属性
        self.heartbeat_client = None
        self.db_manager = DBManager(self.private_data_path,id)
        
    def get_app_path(self):
        return self.public_data_path
    
    def get_agent_public_path(self):
        return self.public_data_path

    def get_agent_private_path(self):
        return self.private_data_path
    
    def init_ap_client(self):
        self.ap_client = ApClient(self.id, self.ep_url,self.ca_client.get_aid_certs_path(self.id),self.seed_password)
        self.ap_client.initialize()

    def online(self):
        log_debug("initialzing entrypoint server")
        if self.ap_client is None:
            self.ap_client = ApClient(self.id, self.ep_url,self.ca_client.get_aid_certs_path(self.id),self.seed_password)
            self.ap_client.initialize()
            if self.ap_client.get_heartbeat_server() is None or self.ap_client.get_heartbeat_server() == "":
                raise Exception("获取心跳服务器地址失败")

        log_debug("initialzing heartbeat server")
        if self.heartbeat_client is not None:
            self.heartbeat_client.offline()
            self.heartbeat_client.sign_out()
            self.heartbeat_client = None
            
        self.heartbeat_client = HeartbeatClient(
            self.id, self.ap_client.get_heartbeat_server(),self.ca_client.get_aid_certs_path(self.id),self.seed_password
        )
        self.heartbeat_client.initialize()

        if self.session_manager is not None:
            self.session_manager.close_all_session()
            self.session_manager = None
        self.session_manager = SessionManager(
            self.id, self.ap_client.get_message_server(),self.ca_client.get_aid_certs_path(self.id),self.seed_password
        )
        self.__connect()
        
    def offline(self):
        """离线状态"""
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

    def get_aid_info(self):
        return {
            'aid':self.id,
            'name':self.name,
            'description':self.description,
            'avaUrl':self.avaUrl,
            'ep_url':self.ep_url,
        }
        
    def get_message_list(self,session_id,page=1, page_size=10):
        return self.db_manager.get_message_list(self.id,session_id,page,page_size)
    
    def get_llm_message_list(self,session_id,page=1, page_size=10):
        message_list = self.get_message_list(self.id,session_id,page,page_size)
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
                msg = {"role":"assistant", "content": content}
            else:
                msg = {"role": "user", "content": content}
            llm_message_list.append(msg)
        return llm_message_list

    def add_message_handler(
        self, handler: typing.Callable[[dict], typing.Awaitable[None]],session_id:str=""
    ):
        """消息监听器装饰器"""
        log_debug("add message handler")
        if not asyncio.iscoroutinefunction(handler):
            raise TypeError("监听器必须是异步函数(async def)")
        if session_id == "":
            self.message_handlers.append(handler)
        else:
            self.message_handlers_map[session_id] = handler
            
    def remove_message_handler(self, handler: typing.Callable[[dict], typing.Awaitable[None]],session_id:str=""):
        """移除消息监听器"""
        if session_id == "":
            if handler in self.message_handlers:
                self.message_handlers.remove(handler)
        else:
            self.message_handlers_map.pop(session_id, None)
        print(len(self.message_handlers_map))
    
    def create_session(self, name, subject, *, type='public'):
        """创建与多个agent的会话
        :param name: 群组名称
        :param subject: 群组主题
        :param to_aid_list: 目标agent ID列表
        :return: 会话ID或None
        """
        log_debug(f"create session: {name}, subject: {subject}, type: {type}")
        session = self.session_manager.create_session(name, subject, type)
        session.set_on_message_receive(self.__agentid_message_listener)
        session.set_on_invite_ack(self.__on_invite_ack)
        session.set_on_member_list_receive(self.__on_member_list_receive)
        self.__insert_session(self.id, session.session_id, session.identifying_code, name)
        return session.session_id

    def invite_member(self, session_id, to_aid):
        if self.session_manager.invite_member(session_id, to_aid):
            self.db_manager.invite_member(self.id, session_id, to_aid)
        else:
            log_error(f"failed to invite: {to_aid} -> {session_id}")

    def get_online_status(self,aids):
        return self.heartbeat_client.get_online_status(aids)

    def get_conversation_list(self,aid,main_aid,page,page_size):
        return self.db_manager.get_conversation_list(aid,main_aid,page,page_size)
    
    async def create_stream(self,session_id,to_aid_list, content_type: str = "text/event-stream", ref_msg_id : str = ""):
        return await self.session_manager.create_stream(session_id,to_aid_list, content_type, ref_msg_id)
        
    def close_session(self, session_id):
        self.session_manager.close_session(session_id)
        
    def close_stream(self,session_id, stream_url):
        self.session_manager.close_stream(session_id, stream_url)
    
    def send_chunk_to_stream(self,session_id, stream_url, chunk):
        self.session_manager.send_chunk_to_stream(session_id, stream_url, chunk)
        
    def __quick_send_message_base(self,to_aid,asnyc_message_result):
        session_id = self.create_session("quick session", "")
        if session_id is None:
            raise Exception("failed to create session")
        async def __asnyc_message_result(data):
            self.remove_message_handler(__asnyc_message_result,session_id=session_id)
            await asnyc_message_result(data)
        self.invite_member(session_id,to_aid)
        self.add_message_handler(__asnyc_message_result,session_id=session_id)
        return session_id
        
    def quick_send_message_content(self,to_aid:str, message_content:str,asnyc_message_result):
        session_id = self.__quick_send_messsage_base(to_aid,asnyc_message_result)
        self.send_message_content(session_id,[to_aid],message_content)
        
    def reply_message(self,msg:dict,message: Union[AssistantMessageBlock, list[AssistantMessageBlock], dict,str]):
        session_id = msg.get("session_id","")
        if session_id == "":
            log_error("failed to get session id")
            return False
        to_aid_list = [msg.get("sender","")]
        ref_msg_id = msg.get("message_id","")
        self.send_message(session_id,to_aid_list,message,ref_msg_id)
    
    def quick_send_message(self,to_aid:str, message: Union[AssistantMessageBlock, list[AssistantMessageBlock], dict],asnyc_message_result):
        session_id = self.__quick_send_message_base(to_aid,asnyc_message_result)
        self.send_message(session_id,[to_aid],message)
        
    def send_message_content(self,session_id: str,to_aid_list: list,llm_content: str,ref_msg_id: str="",message_id:str=""):
        # 处理对象转换为字典
        if session_id == "" or session_id is None:
            return
        if llm_content == "" or llm_content is None:
            return
        msg_block = {
            "type": "content",
            "status": "success", 
            "timestamp": int(time.time() * 1000),
            "content": llm_content
        }
        self.send_message(session_id,to_aid_list,msg_block,ref_msg_id,message_id)
        
    def send_message(self, sessionId: str,to_aid_list: list,  message: Union[AssistantMessageBlock, list[AssistantMessageBlock], dict,str],ref_msg_id: str="",message_id:str=""):
        # 处理对象转换为字典
        if isinstance(message, (AssistantMessageBlock, dict)):
            message_data = [message.__dict__ if hasattr(message, '__dict__') else message]  # 将字典转换为列表
        elif isinstance(message, list):
            message_data = [msg.__dict__ if hasattr(msg, '__dict__') else msg for msg in message]  # 保持列表类型
        elif isinstance(message, str):
            message_data = [{
                "type": "content",
                "status": "success",
                "timestamp": int(time.time() * 1000),
                "content": message
            }]  # 将字符串转换为包含单个字典的列表
        if message_id == "" or message_id is None:
            message_id = str(int(time.time() * 1000))

        self.db_manager.insert_message(
            "user",
            self.id,
            sessionId,
            self.id,
            "",
            ",".join(to_aid_list),
            json.dumps(message_data),
            "text",
            "sent",
            message_id
        )
        self.session_manager.send_msg(sessionId ,json.dumps(message_data), ";".join(to_aid_list), ref_msg_id,message_id)
        
    def get_agent_public_data(self,agentid:str):
        return self.ap_client.get_agent_public_data(agentid)
    
    def sync_public_files(self) ->bool:
        return self.ap_client.sync_public_files(self.public_data_path)
        
    def get_agent_profile_data(self):
        path = os.path.join(self.public_data_path,"agentprofile.json")
        try:
            with open(path, 'r', encoding='utf-8') as file:
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
        return {
            "publisherAid": self.id,
            "organization": self.ap,
            "certificationSignature": self.ap
        }
    
    def create_agent_profile(self,json_data):
        check_result = self.__check_agent_profile(json_data)
        if check_result == False:
            raise Exception("agent profile check failed, please check your agent profile")
        public_data_path = self.get_agent_public_path()
        agent_profile_path = os.path.join(public_data_path,"agentprofile.json")
        agent_html_path = os.path.join(public_data_path,"index.html")
        agent_config_path = os.path.join(public_data_path,"config.json")
        if not os.path.exists(agent_config_path):
            self.__create_config_file(agent_config_path,public_data_path)
        # 如果文件存在，重命名为temp.json
        self.__create_new_file(json_data,agent_profile_path,public_data_path)
        self.__create_html_file(json_data, agent_html_path)
        logger.info("agent profile created successfully")
        
        
    def __create_config_file(self, agent_config_path,public_data_path):
        data = {
            "homepage": "index.html",
            "supportDiscover": True,
        }
        self.__create_new_file(data,agent_config_path,public_data_path)
        
    def __create_html_file(self, json_data, agent_html_path):
        if os.path.exists(agent_html_path):
            os.remove(agent_html_path)
        html_content = parse_html(json_data)
        # 将生成的 HTML 内容写入文件
        with open(agent_html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
    
    def __create_new_file(self,json_data,agent_profile_path,public_data_path):
        os.path.exists(public_data_path) or os.mkdir(public_data_path)
        #parse_html
        temp_path = os.path.join(public_data_path,"temp.json")
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
            with open(filename, 'w', encoding='utf-8') as file:
                file.write(data)
            print(f"成功写入JSON文件: {filename}")
        except (IOError, TypeError) as e:
            print(f"写入文件时出错: {e}")
        except Exception as e:
            print(f"未知错误: {e}")

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
            "llm":dict,
            "references": dict,
            "authorization": dict,
            "input": dict,
            "output": dict,
            "avaUrl": str,
            "supportStream": bool,
            "supportAsync": bool,
            "permission": list
        }

        if not isinstance(json_data, dict):
            logger.error("json_data 必须是一个字典")
            return False
        
        ava_url = json_data.get("avaUrl","")
        if ava_url == "" or (not ava_url.startswith("http://") and not ava_url.startswith("https://")):
            logger.error("图片地址传递不正确")
            return False

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

        if not all(key in json_data["input"] for key in ["types", "formats", "examples", "semantics", "compatibleAids"]):
            log_error("input 字段缺少必要子字段")
            return False

        if not all(key in json_data["output"] for key in ["types", "formats", "examples", "semantics", "compatibleAids"]):
            log_error("output 字段缺少必要子字段")
            return False

        log_info("json_data 验证通过")
        return True
        
    
    def save_public_file(self,file_path:str,filename:str):
        self.ap_client.save_public_file(file_path,filename)
    
    
    def delete_public_file(self,file_path:str):
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                log_info(f"成功删除文件: {file_path}")
                self.ap_client.delete_public_file(file_path)
            else:
                log_error(f"文件不存在: {file_path}")
        except Exception as e:
            log_exception(f"删除文件时出错: {file_path}, 错误: {e}")

    def add_friend_agent(self,aid,name,description,avaUrl):
        self.db_manager.add_friend_agent(self.id,aid,name,description,avaUrl)

    def get_friend_agent_list(self):
        return self.db_manager.get_friend_agent_list(self.id)

    def __on_heartbeat_invite_message(self, invite_req):
        session: Session = self.session_manager.join_session(invite_req)
        session.set_on_message_receive(self.__agentid_message_listener)

    def __run_message_listeners(self, data):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            session_id = data["session_id"]
            if session_id in self.message_handlers_map:
                tasks = [self.__safe_call(self.message_handlers_map[session_id], data)]
                loop.run_until_complete(asyncio.gather(*tasks))
            else:
                tasks = [self.__safe_call(func, data) for func in self.message_handlers]
                loop.run_until_complete(asyncio.gather(*tasks))
        finally:
            loop.close()

    async def __safe_call(self, func, data):
        try:
            await func(data)
        except Exception as e:
            log_exception(f"message_listener_func: 异步消息处理异常: {e}")
    
    def __on_member_list_receive(self,data):
        print("__on_member_list_receive",data)

    def __fetch_stream_data(self, pull_url,save_message_list,data,message_list):
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
                self.db_manager.insert_message("assistant",self.id,session_id,sender, ref_msg_id, receiver, json.dumps(message_list), "text", "success",message_id)
            save_message_list = self.db_manager.get_message_by_id(self.id,session_id,message_id)
            if save_message_list is None or len(save_message_list) == 0:
                log_error(f"插入消息失败: {pull_url}")
                return
            print(save_message_list[0])
            msg_block = json.loads(save_message_list[0]["content"])[0]
            pull_url = pull_url+"&agent_id="+self.id
            log_info("开始拉取流式数据...1："+pull_url)
            #pull_url = pull_url.replace("https://agentunion.cn","https://ts.agentunion.cn")
            try:
                response = requests.get(pull_url, stream=True, verify=False, timeout=(5, 30))  # 连接超时5秒，读取超时30秒
                response.raise_for_status()  # 检查HTTP状态码
                content_text = ""
                for line in response.iter_lines():
                    if line is None:
                        continue
                    decoded_line = line.decode('utf-8')
                    if not decoded_line.startswith("data:") and not decoded_line.startswith("event:"):
                        if decoded_line == ": keep-alive":
                            log_error("接收到的消息不是有效的 SSE 格式")
                            continue
                        decoded_url = urllib.parse.unquote_plus(decoded_line)
                        content_text = content_text+decoded_url
                        msg_block["content"] = content_text
                    else:
                        key, value = decoded_line.split(':', 1)
                        key = key.strip()
                        value = value.strip()
                        if key == 'event' and value == "done":
                            print("接收到的消息仅为 'done'")
                            msg_block["status"] = "success"
                        else:
                            decoded_url = urllib.parse.unquote_plus(value)
                            content_text = content_text+decoded_url
                            msg_block["content"] = content_text
                            # save_message_list[0]["content"] = message
                    message_list = []
                    message_list.append(msg_block)
                    save_message_list[0]["content"] = json.dumps(message_list)
                    self.db_manager.update_message(self.id,save_message_list[0])
            except requests.exceptions.Timeout:
                log_error(f"请求超时: {pull_url}")
            except requests.exceptions.RequestException as e:
                log_error(f"请求失败: {pull_url}, 错误: {str(e)}")
                msg_block["status"] = "error"
                msg_block["type"] = "error"
                msg_block["content"] = "拉取流失败"
                message_list = []
                message_list.append(msg_block)
                save_message_list[0]["content"] = json.dumps(message_list)
                self.db_manager.update_message(self.id,save_message_list[0])
        except Exception as e:
            import traceback
            print(f"拉取流式数据时发生错误: {str(e)}\n{traceback.format_exc()}")
    
    def __404_message_insert(self,data):
        session_id = data["session_id"]
        acceptor_id = data["acceptor_id"]
        message_list = []
        msg_block = {
            "type":"error",
            "status":"success",
            "timestamp":int(time.time() * 1000),  # 使用毫秒时间戳
            "content":"该Agent不在线",
            "extra":""
        }
        message_list.append(msg_block)
        time.sleep(0.3)
        message_id = self.db_manager.insert_message("assistant",self.id,session_id,acceptor_id, "", self.id, json.dumps(message_list), "text", "success","")
        message_data = {
            "session_id":session_id,
            "message_id":message_id,
            "ref_msg_id":"",
            "sender":acceptor_id,
            "receiver":self.id,
            "message":json.dumps(message_list)
        }
        self.__run_message_listeners(message_data)
        
    def __on_invite_ack(self,data):
        status = int(data["status_code"])
        if status == 404:
            thread = threading.Thread(target=self.__404_message_insert, args=(data,))
            thread.start()

    def __agentid_message_listener(self, data):
        log_debug(f"received a message: {data}")
        session_id = data["session_id"]
        message_id = data["message_id"]
        ref_msg_id = data["ref_msg_id"]
        sender = data["sender"]
        receiver = data["receiver"]
        message = json.loads(data["message"])
        message_list = []  # 修改变量名避免与内置list冲突
        message_temp = None
        if isinstance(message, list):
            message_list = message
            message_temp = message_list[0] if isinstance(message_list[0], dict) else json.loads(message_list[0])
        else:
            message_list.append(message)
            message_temp = message
        save_message_list = self.db_manager.get_message_by_id(self.id,session_id,message_id)
        if "text/event-stream" == message_temp.get("type", ""):
            pull_url = message_temp.get("content","")
            print("pull_url:"+pull_url)
            if pull_url == "":
                return            
            threading.Thread(target=self.__fetch_stream_data, args=(pull_url,save_message_list,data,message_list,)).start()
            return
        
        if save_message_list is None or len(save_message_list) == 0:
            self.db_manager.insert_message("assistant",self.id,session_id,sender, ref_msg_id, receiver, json.dumps(message_list), "text", "success",message_id)
        else:
            save_message = save_message_list[0]
            content = save_message["content"]
            if isinstance(content, list):
                content.append(message_list)
            elif isinstance(content, str):
                content_list = json.loads(content)
                content_list.append(message_list)                
            save_message["content"] = json.dumps(content_list)
            self.db_manager.update_message(self.id,save_message)
            
        thread = threading.Thread(target=self.__run_message_listeners, args=(data,))
        thread.start()

    def __insert_session(self,aid,session_id,identifying_code,name):
        conversation =  self.db_manager.get_conversation_by_id(aid,session_id)
        if conversation is None:
            # identifying_code,name, type,to_aid_list
            self.db_manager.create_conversation(aid,session_id,identifying_code,name,"public",[])
        return

    def __connect(self):
        if not hasattr(self, '_heartbeat_thread') or not self._heartbeat_thread.is_alive():
            self._heartbeat_thread = threading.Thread(target=self.heartbeat_client.online)
            self._heartbeat_thread.start()
        self.heartbeat_client.set_on_recv_invite(self.__on_heartbeat_invite_message)
        log_info(f'agentid {self.id} is ready!')



    def get_agent_list(self):
        """获取所有agentid列表"""
        return self.ap_client.get_agent_list()

    def get_all_public_data(self):
        """获取所有agentid列表"""
        return self.ap_client.get_all_public_data()

    def get_session_member_list(self,session_id):
        return self.db_manager.get_session_member_list(self.id,session_id)

    def update_aid_info(self, aid, avaUrl, name, description):
        self.db_manager.update_aid_info(aid, avaUrl, name, description)
        return True

    def message_handler(self, name: str|None = None):
        def wrapper(fn):
            # 动态获取 client 属性名
            self.add_message_handler(fn)
            return fn
        return wrapper

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
    
    
    def get_content_from_message(self, message,message_type="content"):
        message_array = self.get_content_array_from_message(message)
        for item in message_array:
            if isinstance(item, dict) and item.get('type') == message_type:
                # 这里可以执行你需要的操作，例如打印 content 字段
                content = item.get(message_type,'')
                try:
                    content_json = json.loads(content)  # 尝试解析为 JSON
                    if isinstance(content_json, dict) and 'text' in content_json:  # 检查是否为字典且包含 'text'
                        return content_json['text']
                except json.JSONDecodeError:
                    pass 
                return content
        if message_type == "content":
            return self.get_content_from_message(message,message_type="text")
        return None  # 如果不是字典，返回None或抛出异常，取决于你的需求
    
    def __str__(self):
        return self.id
    
    # 尝试解析 content 为 JSON 格式 
    def get_content_array_from_message(self, message):
        #消息数组
        message_content = message.get("message","")
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
                    print("收到空消息内容")
                    return []
            except json.JSONDecodeError:
                print(f"无法解析的消息内容: {message_content}")
                return []
        elif isinstance(message_content, list) and len(message_content) > 0:
            return message_content
        else:
            print("无效的消息格式")
            return []
        
    async def send_stream_message(self,session_id: str, to_aid_list: list, response,type="text/event-stream",ref_msg_id:str=""):
        # 处理对象转换为字典
        stream_result = await self.create_stream(session_id,to_aid_list,type, ref_msg_id)
        if stream_result is None:
            print("创建流失败")        
            msg_block = {
                "type": "error",
                "status": "success", 
                "timestamp": int(time.time() * 1000),
                "content": "创建流失败"
            }
            self.send_message(session_id,to_aid_list, msg_block)
            return None
        push_url, pull_url = stream_result
        print(f"push_url: {push_url}")
        print(f"pull_url: {pull_url}")
        msg_block = {
            "type": "text/event-stream",
            "status": "loading", 
            "timestamp": int(time.time() * 1000),
            "content": pull_url
        }
        
        self.send_message(session_id,to_aid_list,msg_block)
        
        for chunk in response:
           # 打印每个chunk的内容，以便调试
            if chunk.choices[0].delta.content:
                # chunk.choices[0].delta.content)
                print(chunk.choices[0].delta.content)
                self.send_chunk_to_stream(session_id,push_url,chunk.choices[0].delta.content)
                #print(chunk.choices[0].delta.content, end="", flush=True)  # 实时打印流式响应               
        self.close_stream(session_id,push_url)

class AgentCP(_AgentCP):
    
    def __init__(self, agent_data_path, certificate_path:str = "", seed_password:str = "",debug = False):
        super().__init__()       
        if agent_data_path == "" or agent_data_path is None:
            raise Exception("agent_data_path 不能为空")
        else:
            self.app_path = os.path.join(agent_data_path, "agentcp")
        self.seed_password = self.__get_sha256(seed_password)        
        if certificate_path == "" or certificate_path is None:
            certificate_path = self.app_path
        self.aid_path = os.path.join(certificate_path, 'AIDs')
        os.path.exists(self.aid_path) or os.makedirs(self.aid_path)
        set_log_enabled(debug)
        self.ca_client = None
        self.ep_url = None
        
    def modify_seed_password(self, seed_password:str):
        new_seed_password = self.__get_sha256(seed_password)
        aid_list = self.get_aid_list()
        for aid_str in aid_list:
            #加载aid
            private_key = self.__load_aid_private_key(aid_str)
            if private_key is None:
                logger.error(f"加载失败aid: {aid_str}")
                continue
            try:
                self.ca_client.modify_seed_password(aid_str,private_key,new_seed_password)
                logger.error(f"修改密码种子成功aid: {aid_str}")
            except Exception as e:
                logger.error(f"修改密码种子失败aid: {aid_str}, 错误: {str(e)}")
            
            
    def __load_aid_private_key(self,agent_id: str):
        self.__build_url(agent_id)
        try:
            private_key = self.ca_client.load_private_key(agent_id)
            return private_key
        except Exception as e:
            log_exception(f"加载和验证密钥对时出错: {e}")  # 调试用
            return None
        
    def get_agent_data_path(self):
        return self.app_path

    def __get_sha256(self,input_str: str) -> str:
        sha256_hash = hashlib.sha256()
        sha256_hash.update(input_str.encode('utf-8'))
        return sha256_hash.hexdigest()
    
    def __build_url(self, aid: str):
        aid_array = aid.split('.')
        if len(aid_array) < 3:
            raise RuntimeError("加载aid错误,请检查传入aid")
        end_str = f'{aid_array[-2]}.{aid_array[-1]}'
        self.ca_client = CAClient("https://ap."+end_str,self.aid_path,self.seed_password)
        self.ep_url = "https://ap."+end_str

    def load_aid(self, agent_id: str) -> AgentID:
        self.__build_url(agent_id)
        try:
            log_debug(f"load agentid: {agent_id}")
            if self.ca_client.aid_is_not_exist(agent_id):  # 检查返回结果是否有效
                log_error(f"未找到agent_id: {agent_id} 或数据不完整")
                return None
            aid = AgentID(agent_id,self.app_path,self.seed_password,self.ca_client,self.ep_url)
            ep_url = self.ca_client.resign_csr(agent_id)
            if ep_url:
                return aid
            return None
        except Exception as e:
            log_exception(f"加载和验证密钥对时出错: {e}")  # 调试用
            return None

    def __build_id(self, id:str):
        ep = self.ep_url.split('.')
        end_str = f'{ep[-2]}.{ep[-1]}'
        if id.endswith(end_str):
            return id
        return f'{id}.{ep[-2]}.{ep[-1]}'
    
    def get_guest_aid(self,ep_url: str):
        self.ca_client = CAClient("https://ap."+ep_url,self.aid_path,self.seed_password)
        self.ep_url = "https://ap."+ep_url
        guest_aid = self.ca_client.get_guest_aid()
        if guest_aid:
            return self.load_aid(guest_aid)
        raise RuntimeError("获取guest aid失败")
        
    def create_aid(self, ap: str,agent_name: str) -> AgentID:
        import re
        if not re.match('^[a-z0-9]+$', agent_name):
            raise ValueError(f"agent_id {agent_name} 必须仅包含数字或小写字母")
        
        if agent_name.startswith("guest"):
            return self.get_guest_aid(ap)
                    
        self.ca_client = CAClient("https://ap."+ap,self.aid_path,self.seed_password)
        self.ep_url = "https://ap."+ap
        
        if not self.ca_client.aid_is_not_exist(agent_name+"."+ap):
            return self.load_aid(agent_name+"."+ap)
        
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
            array = entry.name.split('.')
            if entry.is_dir() and len(array) == 3:
                aid_list.append(entry.name)
        return aid_list