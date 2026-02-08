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
import atexit
import queue
import threading
from typing import Callable

from .exceptions import SDKError


class AtomicErrorContext:
    """
    错误收集，只有在订阅后才运行，否则不会有任何错误信息加入到队列
    """

    def __init__(self, max_queue_size=1024):
        self.queue = queue.Queue[SDKError](maxsize=max_queue_size)
        self.stop_flag = threading.Event()
        self.start_flag = threading.Event()
        self.worker_thread = threading.Thread(target=self._worker, daemon=True)

    def publish(self, e: SDKError):
        if not self.start_flag.is_set():
            return

        try:
            if self.queue.full():
                self.queue.get_nowait()
            e.agent_id = self.aid

            self.queue.put(e, block=False)
        except queue.Full:
            pass

    def subscribe(self, aid: str, func: Callable[[SDKError], None]):
        """
        上层直接退出登录线程未完全退出，防止重复订阅（多账号来回切换会出现异常）
        """
        if self.start_flag.is_set():
            return

        self.aid = aid
        self.func = func
        self.start_flag.set()
        self.worker_thread.start()
        atexit.register(self.close)

    def _worker(self):
        """后台线程，定时或批量处理队列数据"""
        while not self.stop_flag.is_set():
            try:
                # 等待队列有数据
                data = self.queue.get(timeout=1)
                self.func(data)
            except queue.Empty:
                pass  # 到达interval时间也可能队列为空

    def close(self):
        """关闭采集线程，确保队列数据全部发送"""
        self.stop_flag.set()
        self.worker_thread.join()
