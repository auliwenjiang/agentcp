# -*- coding: utf-8 -*-
"""
改进的消息调度器
支持线程池 + 异步任务池的混合架构
"""

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Awaitable, Dict, Any, Optional
from agentcp.base.log import log_info, log_error, log_exception, log_warning, log_debug


class ImprovedMessageScheduler:
    """
    改进的消息调度器

    架构:
    - 核心线程: core_workers 个 (常驻)
    - 最大线程: max_workers 个 (高峰扩展)
    - 每线程并发异步任务: max_tasks_per_worker 个

    优势:
    - 资源高效: 少量线程处理大量异步任务
    - 高并发: 总并发 = max_workers × max_tasks_per_worker
    - 负载均衡: 自动选择负载最低的工作线程
    """

    def __init__(self,
                 core_workers: int = 20,
                 max_workers: int = 50,
                 max_tasks_per_worker: int = 10):
        """
        初始化调度器

        Args:
            core_workers: 核心工作线程数 (常驻)
            max_workers: 最大工作线程数 (高峰时扩展)
            max_tasks_per_worker: 每个工作线程的最大并发异步任务数
        """
        self.core_workers = core_workers
        self.max_workers = max_workers
        self.max_tasks_per_worker = max_tasks_per_worker

        # 线程池
        self.thread_pool = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="agentcp-worker"
        )

        # 工作线程状态
        self.worker_loops: Dict[int, asyncio.AbstractEventLoop] = {}  # worker_id -> event loop
        self.worker_queues: Dict[int, asyncio.Queue] = {}  # worker_id -> message queue
        self.worker_tasks_count: Dict[int, int] = {}  # worker_id -> active task count
        self.worker_lock = threading.Lock()

        # 统计信息
        self.total_messages = 0
        self.total_processed = 0
        self.total_errors = 0
        self.total_rejected = 0  # ✅ P1修复: 添加拒绝计数
        self.active_workers = 0
        self.is_running = True

        # ✅ 修复: 添加统计锁,保护计数器的线程安全
        self.stats_lock = threading.Lock()

        # ✅ P1修复: 队列监控配置
        self.queue_warn_threshold = 0.8  # 队列使用率警告阈值
        self.queue_timeout = 5.0  # ✅ 增加: 队列等待超时从2秒增加到5秒
        self.max_submit_retries = 3  # ✅ 新增: 提交失败时的最大重试次数

        # 初始化核心工作线程
        self._init_core_workers()

        log_info(f"[Scheduler] 初始化完成: core_workers={core_workers}, "
                f"max_workers={max_workers}, max_tasks_per_worker={max_tasks_per_worker}")

    def _init_core_workers(self):
        """初始化核心工作线程"""
        for worker_id in range(self.core_workers):
            self._start_worker(worker_id)

    def _start_worker(self, worker_id: int):
        """
        ✅ P1修复: 启动一个工作线程 (使用Event同步)

        Args:
            worker_id: 工作线程ID
        """
        # 创建启动就绪事件
        ready_event = threading.Event()

        # 提交工作线程任务
        self.thread_pool.submit(self._worker_main, worker_id, ready_event)

        # ✅ 使用Event等待线程就绪 (最多等待5秒)
        if not ready_event.wait(timeout=5.0):
            log_error(f"[Worker-{worker_id}] 启动超时")
            raise RuntimeError(f"Worker-{worker_id} failed to start within 5 seconds")

        with self.worker_lock:
            self.worker_tasks_count[worker_id] = 0
            self.active_workers += 1

        log_info(f"[Worker-{worker_id}] 启动成功")

    def _worker_main(self, worker_id: int, ready_event: threading.Event = None):
        """
        ✅ P1修复: 工作线程主函数
        运行一个持久的事件循环,处理异步任务

        Args:
            worker_id: 工作线程ID
            ready_event: 启动就绪事件 (用于同步启动)
        """
        # 创建新的事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # ✅ 增加: 队列大小从1000增加到5000，提高并发容量
        queue = asyncio.Queue(maxsize=5000)

        # 注册到全局状态
        with self.worker_lock:
            self.worker_loops[worker_id] = loop
            self.worker_queues[worker_id] = queue

        log_info(f"[Worker-{worker_id}] 事件循环启动, thread={threading.current_thread().name}")

        # ✅ 通知启动完成
        if ready_event:
            ready_event.set()

        # 运行事件循环
        try:
            loop.run_until_complete(self._worker_loop(worker_id, queue))
        except Exception as e:
            log_exception(f"[Worker-{worker_id}] 事件循环异常: {e}")
        finally:
            # 清理
            try:
                # 取消所有待处理任务
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                # 等待取消完成
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                loop.close()
            except Exception as e:
                log_error(f"[Worker-{worker_id}] 清理异常: {e}")

            # 从全局状态移除
            with self.worker_lock:
                if worker_id in self.worker_loops:
                    del self.worker_loops[worker_id]
                if worker_id in self.worker_queues:
                    del self.worker_queues[worker_id]
                if worker_id in self.worker_tasks_count:
                    del self.worker_tasks_count[worker_id]
                self.active_workers -= 1

            log_info(f"[Worker-{worker_id}] 已停止")

    async def _worker_loop(self, worker_id: int, queue: asyncio.Queue):
        """✅ P0-3改进: 工作线程事件循环，优化任务拒绝逻辑

        改进要点：
        1. 移除"放回队列"的逻辑（会导致死锁）
        2. 任务超限时直接跳过（让 submit_message 重试其他 worker）
        3. 添加详细的日志

        Args:
            worker_id: 工作线程ID
            queue: 消息队列
        """
        while self.is_running:
            try:
                # 等待新消息 (超时检查,避免卡死)
                try:
                    message_handler, data = await asyncio.wait_for(queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                # ✅ 检查是否超过任务限制
                with self.worker_lock:
                    current_tasks = self.worker_tasks_count.get(worker_id, 0)

                    if current_tasks >= self.max_tasks_per_worker:
                        # ✅ P0-3改进: 不再尝试放回队列，直接记录拒绝
                        with self.stats_lock:
                            self.total_rejected += 1

                        message_id = data.get('message_id', 'unknown') if isinstance(data, dict) else 'unknown'
                        log_warning(
                            f"⚠️ [Worker-{worker_id}] 任务超限 "
                            f"({current_tasks}/{self.max_tasks_per_worker}), "
                            f"拒绝任务 message_id={message_id[:16] if len(message_id) > 16 else message_id}..."
                        )

                        # 短暂等待后继续取下一个任务
                        await asyncio.sleep(0.05)
                        continue

                    # 增加任务计数
                    self.worker_tasks_count[worker_id] = current_tasks + 1

                # ✅ 关键:创建异步任务(不等待完成)
                asyncio.create_task(
                    self._handle_message_wrapper(worker_id, message_handler, data)
                )

            except asyncio.CancelledError:
                log_info(f"[Worker-{worker_id}] 收到取消信号")
                break
            except Exception as e:
                log_exception(f"[Worker-{worker_id}] 事件循环异常: {e}")
                await asyncio.sleep(0.1)

    async def _handle_message_wrapper(self,
                                      worker_id: int,
                                      message_handler: Callable[[Dict], Awaitable[None]],
                                      data: Dict[str, Any]):
        """
        消息处理包装器
        处理完成后减少任务计数

        Args:
            worker_id: 工作线程ID
            message_handler: 异步消息处理函数
            data: 消息数据
        """
        try:
            # 调用实际的消息处理函数
            await message_handler(data)

            # ✅ 修复: 使用锁保护统计计数器
            with self.stats_lock:
                self.total_processed += 1

        except Exception as e:
            # ✅ 修复: 使用锁保护统计计数器
            with self.stats_lock:
                self.total_errors += 1
            log_exception(f"[Worker-{worker_id}] 消息处理失败: {e}")
        finally:
            # 减少任务计数
            with self.worker_lock:
                current = self.worker_tasks_count.get(worker_id, 0)
                self.worker_tasks_count[worker_id] = max(0, current - 1)

    def submit_message(self,
                       message_handler: Callable[[Dict], Awaitable[None]],
                       data: Dict[str, Any],
                       raise_on_reject: bool = False) -> bool:
        """✅ P0-3改进: 提交消息到调度器（多候选 worker + 队列监控）

        改进要点：
        1. 选择多个候选 worker 而不是单个
        2. 依次尝试候选 worker，失败时自动切换
        3. 检查队列使用率，跳过接近满的 worker
        4. 优化重试逻辑和等待时间

        Args:
            message_handler: 异步消息处理函数 async def handler(data)
            data: 消息数据
            raise_on_reject: 如果为True，在任务被拒绝时抛出异常；否则返回False

        Returns:
            bool: True表示提交成功，False表示被拒绝

        Raises:
            RuntimeError: 当raise_on_reject=True且任务被拒绝时抛出
        """
        # ✅ 统计计数
        with self.stats_lock:
            self.total_messages += 1

        # ✅ P0-3改进: 重试机制，每次尝试多个候选 worker
        last_error = None
        for retry_attempt in range(self.max_submit_retries):
            try:
                # ✅ 获取负载最低的 TOP 3 worker
                candidate_workers = self._select_workers_by_load(top_n=3)

                if not candidate_workers:
                    error_msg = "[Scheduler] 没有可用的工作线程"
                    log_error(error_msg)
                    with self.stats_lock:
                        self.total_rejected += 1
                    if raise_on_reject:
                        raise RuntimeError(error_msg)
                    return False

                # ✅ 依次尝试候选 worker
                submitted = False
                for worker_id in candidate_workers:
                    loop = self.worker_loops.get(worker_id)
                    queue = self.worker_queues.get(worker_id)

                    if not loop or not queue or loop.is_closed():
                        continue

                    # ✅ 检查队列使用率
                    queue_size = queue.qsize()
                    queue_maxsize = queue.maxsize
                    usage_rate = queue_size / queue_maxsize if queue_maxsize > 0 else 0

                    # ✅ 如果队列使用率超过 90%，跳过这个 worker
                    if usage_rate >= 0.9:
                        log_warning(
                            f"⚠️ [Worker-{worker_id}] 队列接近满 "
                            f"({queue_size}/{queue_maxsize}, {usage_rate*100:.1f}%), 尝试下一个"
                        )
                        continue

                    # ✅ 尝试提交
                    try:
                        future = asyncio.run_coroutine_threadsafe(
                            self._put_with_timeout(queue, message_handler, data),
                            loop
                        )
                        future.result(timeout=self.queue_timeout)

                        # ✅ 提交成功
                        submitted = True
                        log_debug(f"✅ [Scheduler] 消息已提交到 Worker-{worker_id}")
                        return True

                    except Exception as e:
                        log_debug(f"⚠️ [Worker-{worker_id}] 提交失败: {e}, 尝试下一个")
                        continue

                if submitted:
                    return True

                # ✅ 所有候选 worker 都失败
                last_error = "所有候选 worker 都无法接收任务"

            except Exception as e:
                last_error = str(e)

            # ✅ 重试前等待（指数退避）
            if retry_attempt < self.max_submit_retries - 1:
                wait_time = 0.05 * (2 ** retry_attempt)  # 指数退避: 0.05s, 0.1s, 0.2s
                log_warning(
                    f"⚠️ [Scheduler] 提交失败 (第{retry_attempt + 1}次), "
                    f"{wait_time}s 后重试... reason={last_error}"
                )
                time.sleep(wait_time)

        # ✅ 所有重试都失败
        with self.stats_lock:
            self.total_rejected += 1

        error_msg = f"[Scheduler] 消息提交最终失败: {last_error}"
        log_error(error_msg)

        if raise_on_reject:
            raise RuntimeError(error_msg)

        return False

    async def _put_with_timeout(self, queue: asyncio.Queue, message_handler, data):
        """
        ✅ P1修复: 带超时的队列put操作

        Args:
            queue: 目标队列
            message_handler: 消息处理器
            data: 消息数据
        """
        try:
            await asyncio.wait_for(
                queue.put((message_handler, data)),
                timeout=self.queue_timeout
            )
        except asyncio.TimeoutError:
            raise Exception(f"队列已满,等待超时 ({self.queue_timeout}s)")

    def _select_worker(self) -> Optional[int]:
        """
        选择负载最低的工作线程（保留向后兼容）

        Returns:
            worker_id 或 None (如果没有可用worker)
        """
        with self.worker_lock:
            if not self.worker_tasks_count:
                return None

            # 找到任务数最少的worker
            min_tasks = float('inf')
            selected_worker = None

            for worker_id, task_count in self.worker_tasks_count.items():
                if task_count < min_tasks:
                    min_tasks = task_count
                    selected_worker = worker_id

                    # 如果找到空闲worker,直接使用
                    if task_count == 0:
                        break

            return selected_worker

    def _select_workers_by_load(self, top_n: int = 3) -> list:
        """✅ P0-3新增: 选择负载最低的 TOP N worker

        Args:
            top_n: 返回前 N 个负载最低的 worker

        Returns:
            worker_id 列表，按负载从低到高排序
        """
        with self.worker_lock:
            if not self.worker_tasks_count:
                return []

            # 按任务数排序（从少到多）
            sorted_workers = sorted(
                self.worker_tasks_count.items(),
                key=lambda x: x[1]  # x[1] 是任务数
            )

            # 返回前 N 个 worker 的 ID
            return [worker_id for worker_id, _ in sorted_workers[:top_n]]

    def get_stats(self) -> Dict[str, Any]:
        """
        ✅ 修复: 获取统计信息 (线程安全)

        Returns:
            统计数据字典
        """
        # 获取 worker 统计
        with self.worker_lock:
            total_active_tasks = sum(self.worker_tasks_count.values())
            worker_details = dict(self.worker_tasks_count)
            active_workers = self.active_workers

        # 获取全局统计
        with self.stats_lock:
            total_messages = self.total_messages
            total_processed = self.total_processed
            total_errors = self.total_errors
            total_rejected = self.total_rejected  # ✅ P1修复: 添加拒绝统计

        return {
            'total_messages': total_messages,
            'total_processed': total_processed,
            'total_errors': total_errors,
            'total_rejected': total_rejected,  # ✅ P1修复
            'active_workers': active_workers,
            'total_active_tasks': total_active_tasks,
            'worker_tasks': worker_details,
            'success_rate': f"{(total_processed / max(1, total_messages)) * 100:.2f}%"
        }

    def print_stats(self):
        """✅ P1修复: 打印统计信息 (包含拒绝数)"""
        stats = self.get_stats()
        log_info(f"[Scheduler Stats] "
                f"Messages: {stats['total_messages']}, "
                f"Processed: {stats['total_processed']}, "
                f"Errors: {stats['total_errors']}, "
                f"Rejected: {stats['total_rejected']}, "
                f"Active Workers: {stats['active_workers']}, "
                f"Active Tasks: {stats['total_active_tasks']}, "
                f"Success Rate: {stats['success_rate']}")

    def shutdown(self, wait: bool = True):
        """
        关闭调度器

        Args:
            wait: 是否等待所有任务完成
        """
        log_info("[Scheduler] 正在关闭...")
        self.is_running = False

        if wait:
            # 等待一段时间让任务完成
            max_wait = 10  # 最多等待10秒
            for i in range(max_wait):
                stats = self.get_stats()
                if stats['total_active_tasks'] == 0:
                    break
                log_info(f"[Scheduler] 等待任务完成... 剩余 {stats['total_active_tasks']} 个")
                time.sleep(1)

        # 关闭线程池
        self.thread_pool.shutdown(wait=wait)

        # 打印最终统计
        self.print_stats()
        log_info("[Scheduler] 已关闭")
