# -*- coding: utf-8 -*-
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

"""
我们来详细实现Workflow:
1.Mermaid类是mermaid语法的解析器,类构造实例的时候传入mermaid语法的文本,得到流程图的节点和边.目前只支持graph
2.Workflow类是用来处理任意工作流,在构造实例的时候传入一个Mermaid的实例作为整个工作流参考的基础
3.各节点类通过装饰器output_port和input_port来定义节点的输入输出端口
4.节点通过Workflow的addnode方法加入工作流,工作流在调用start方法的时候,根据mermaid的节点和边的关系建立各节点实例输入输出端口之间的绑定关系
5.在定义Agent的时候, 不同的Agent需要有不同Agent的类
6.每个Agent类, 他有具体的输入输出端口, 这些输入输出端口是通过装饰器来定义
7.装饰器做两件事:
    1.完成参数的传递
    2.完成端口函数名字和端口注解的绑定(可以在函数定义里面的注释部分来描述这个端口是做什么用的,
                                 他应该与mermaid里面的流程里面的描述词一样)
8.通过workflow.start的时候, 首先将已经通过addmode加入的节点之间, 让输入输出端口之间根据描述词建立绑定关系.
这样, 当一个输出端口执行完毕后, 将自动开始调用其指向的下一个Agent的输入端口函数
"""

# 引入acp的库
# import time
import threading

from inspect import iscoroutinefunction
import asyncio

from .mermaid import Mermaid
from functools import wraps
from collections import defaultdict

from agentcp.base.log import log_error, log_info, log_warning


class Workflow:
    _workflow_lock = threading.Lock()
    _workflow_storage = dict()

    def output_port(description: str):
        """
            输出端口的函数参数定义无限制,只要他的调用者(通常就是当前节点自己的输入端口函数中)正确的传递参数即可
            输入端口的函数参数定义,是一个字符串,其实原则上也是没有限制的,只要调用者参数传递争取即可

        :return:
        """

        # 输出端口的函数定义是随便的,只要他的调用者正确的传递参数即可
        #
        def decorator(func):
            func.is_output_port = True
            func.output_port_desc = description

            @wraps(func)
            def wrapper(self, *args, **kwargs):
                try:
                    result = func(self, *args, **kwargs)

                    workflow = self._workflow

                    output_port_name = f"{self.__class__.__name__}:{func.__name__}"
                    target_port, target_port_name = workflow.port_mapping.get(output_port_name, (None, None))
                    if target_port:
                        # 判断是否为异步方法并处理
                        if iscoroutinefunction(target_port):
                            # 获取或创建事件循环
                            try:
                                loop = asyncio.get_running_loop()
                            except RuntimeError:
                                loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(loop)
                            # 异步调用（支持同步/异步上下文）
                            loop.run_until_complete(target_port(result))
                        else:
                            # 同步调用
                            target_port(result)
                    else:
                        log_error(f"{output_port_name}没有找到绑定的输入端口")

                    return result
                except Exception as e:
                    log_error(f"Error in output port {func.__name__}: {e}")
                    raise

            return wrapper

        return decorator

    def input_port(param: str):
        def decorator(func):
            func.is_input_port = True
            func.input_port_desc = param

            @wraps(func)
            def wrapper(self, *args, **kwargs):
                try:
                    return func(self, *args, **kwargs)
                except Exception as e:
                    log_error(f"输入端口异常 {func.__name__}: {e}")
                    raise

            return wrapper

        return decorator

    def __init__(self, mermaid: Mermaid):
        self.nodes = {}
        self.port_mapping = defaultdict()
        self.mermaid = mermaid  # 保存 Mermaid 实例

    def addnode(self, agent, node_name):
        agent._workflow = self
        self.nodes[node_name] = agent
        return self  # 返回 self 以支持链式调用

    @classmethod
    def getstorage(cls, key=None, default=None, caller: str = "") -> dict:
        # 不同的工作流调用者得到不同的存储对象,默认是一个线程一个对象
        if not caller or len(caller) == 0:
            threadid = threading.get_ident()
            caller = f"workflow_caller_{threadid}"
        with cls._workflow_lock:
            if caller not in cls._workflow_storage:
                cls._workflow_storage[caller] = dict()

            storage = cls._workflow_storage[caller]
            if key:
                return storage.setdefault(key, default)
            return storage

    @classmethod
    def clearstorage(cls, caller: str = "") -> None:
        """
        清除指定调用者的存储数据

        :param caller: 调用者标识，默认为当前线程生成的标识
        """
        if not caller or len(caller) == 0:
            threadid = threading.get_ident()
            caller = f"workflow_caller_{threadid}"
        with cls._workflow_lock:
            if caller in cls._workflow_storage:
                del cls._workflow_storage[caller]

    def start(self):
        self._build_port_mapping()

    def _build_port_mapping(self):
        mermaid_edges = self.mermaid.edges  # 从 Mermaid 实例获取边数据
        for edge in mermaid_edges:
            source_node, description, target_node = edge
            source_node_desc = self.mermaid.node_dict.get(source_node, "")
            target_node_desc = self.mermaid.node_dict.get(target_node, "")
            source_agent = self.nodes.get(source_node_desc, None)
            target_agent = self.nodes.get(target_node_desc, None)
            if not source_agent:
                log_warning(
                    f'"{source_node} -->|{description}|{target_node}"\t{source_node}[{source_node_desc}]没有找到'
                )
            if not target_agent:
                log_warning(
                    f'"{source_node} -->|{description}|{target_node}"\t{target_node}[{target_node_desc}]没有找到'
                )
            if source_agent and target_agent:
                output_port = self._find_output_port(source_agent, description)
                input_port = self._find_input_port(target_agent, description)
                if not output_port:
                    log_warning(f'"{source_node_desc}"没有发现输出端口:{description}')
                if not input_port:
                    log_warning(f'"{target_node_desc}"没有发现输入端口:{description}')
                if input_port and output_port:
                    self.port_mapping[f"{source_agent.__class__.__name__}:{output_port.__name__}"] = (
                        input_port,
                        f"{target_agent.__class__.__name__}:{input_port.__name__}",
                    )
                    log_info(
                        f"[{source_node_desc}  -> |{description}| {target_node_desc}]"
                        f"\n\t调用链: {source_agent.__class__.__name__}:{output_port.__name__} >> {target_agent.__class__.__name__}:{input_port.__name__}"
                    )

    def _find_output_port(self, agent, desc):
        for method_name in dir(agent):
            method = getattr(agent, method_name)
            if hasattr(method, "is_output_port") and method.output_port_desc == desc:
                return method
        return None

    def _find_input_port(self, agent, desc):
        for method_name in dir(agent):
            method = getattr(agent, method_name)
            if hasattr(method, "is_input_port") and method.input_port_desc == desc:
                return method
        return None
