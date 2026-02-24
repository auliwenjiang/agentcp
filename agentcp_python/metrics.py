# -*- coding: utf-8 -*-
"""
✅ P1-3新增: 消息处理指标收集器

提供详细的消息处理统计和监控指标
"""

import threading
import time
from typing import Dict, Any, List


class MessageMetrics:
    """消息处理指标收集器

    收集以下指标：
    - 消息接收总数
    - 派发成功/失败数
    - Handler 成功/失败数
    - 派发队列大小
    - 平均延迟
    - 延迟直方图（p50, p95, p99）
    """

    def __init__(self):
        self.lock = threading.Lock()

        # 基础计数器
        self.received_total = 0
        self.dispatched_success = 0
        self.dispatched_failed = 0
        self.handler_success = 0
        self.handler_failed = 0
        self.dispatch_queue_size = 0  # ✅ 派发队列大小

        # 延迟统计
        self.dispatch_latencies: List[float] = []  # 毫秒
        self.handler_latencies: List[float] = []  # 毫秒
        self.max_latency_samples = 1000  # 保留最近 1000 个样本

        # 平均值缓存
        self._avg_dispatch_latency_ms = 0.0
        self._avg_handler_latency_ms = 0.0

        # 启动时间
        self.start_time = time.time()

    def record_received(self):
        """记录收到消息"""
        with self.lock:
            self.received_total += 1

    def record_dispatch_success(self, latency_ms: float):
        """记录派发成功

        Args:
            latency_ms: 派发延迟（毫秒）
        """
        with self.lock:
            self.dispatched_success += 1
            self.dispatch_latencies.append(latency_ms)

            # 保持样本数量在限制内
            if len(self.dispatch_latencies) > self.max_latency_samples:
                self.dispatch_latencies.pop(0)

            # 更新平均值
            self._avg_dispatch_latency_ms = sum(self.dispatch_latencies) / len(self.dispatch_latencies)

    def record_dispatch_failure(self):
        """记录派发失败"""
        with self.lock:
            self.dispatched_failed += 1

    def record_handler_success(self, latency_ms: float):
        """记录 Handler 成功

        Args:
            latency_ms: 处理延迟（毫秒）
        """
        with self.lock:
            self.handler_success += 1
            self.handler_latencies.append(latency_ms)

            # 保持样本数量在限制内
            if len(self.handler_latencies) > self.max_latency_samples:
                self.handler_latencies.pop(0)

            # 更新平均值
            self._avg_handler_latency_ms = sum(self.handler_latencies) / len(self.handler_latencies)

    def record_handler_failure(self):
        """记录 Handler 失败"""
        with self.lock:
            self.handler_failed += 1

    def update_dispatch_queue_size(self, count: int):
        """更新派发队列计数

        Args:
            count: 当前派发队列大小
        """
        with self.lock:
            self.dispatch_queue_size = count

    def get_summary(self) -> Dict[str, Any]:
        """获取指标摘要

        Returns:
            包含所有指标的字典
        """
        with self.lock:
            # 计算成功率
            dispatch_rate = 0.0
            if self.received_total > 0:
                dispatch_rate = (self.dispatched_success / self.received_total) * 100

            handler_rate = 0.0
            if self.dispatched_success > 0:
                handler_rate = (self.handler_success / self.dispatched_success) * 100

            # 计算百分位数
            dispatch_p50, dispatch_p95, dispatch_p99 = self._calculate_percentiles(
                self.dispatch_latencies
            )
            handler_p50, handler_p95, handler_p99 = self._calculate_percentiles(
                self.handler_latencies
            )

            # 运行时间
            uptime_seconds = time.time() - self.start_time

            return {
                # 基础计数
                "received_total": self.received_total,
                "dispatched_success": self.dispatched_success,
                "dispatched_failed": self.dispatched_failed,
                "handler_success": self.handler_success,
                "handler_failed": self.handler_failed,
                "dispatch_queue_size": self.dispatch_queue_size,

                # 成功率
                "dispatch_success_rate": f"{dispatch_rate:.2f}%",
                "handler_success_rate": f"{handler_rate:.2f}%",

                # 延迟统计（毫秒）
                "dispatch_latency": {
                    "avg_ms": f"{self._avg_dispatch_latency_ms:.2f}",
                    "p50_ms": f"{dispatch_p50:.2f}",
                    "p95_ms": f"{dispatch_p95:.2f}",
                    "p99_ms": f"{dispatch_p99:.2f}",
                },
                "handler_latency": {
                    "avg_ms": f"{self._avg_handler_latency_ms:.2f}",
                    "p50_ms": f"{handler_p50:.2f}",
                    "p95_ms": f"{handler_p95:.2f}",
                    "p99_ms": f"{handler_p99:.2f}",
                },

                # 吞吐量（每秒）
                "throughput": {
                    "messages_per_second": f"{self.received_total / max(1, uptime_seconds):.2f}",
                    "dispatched_per_second": f"{self.dispatched_success / max(1, uptime_seconds):.2f}",
                },

                # 运行时间
                "uptime_seconds": f"{uptime_seconds:.0f}",
            }

    def _calculate_percentiles(self, data: List[float]) -> tuple:
        """计算百分位数

        Args:
            data: 数据列表

        Returns:
            (p50, p95, p99) 元组
        """
        if not data:
            return (0.0, 0.0, 0.0)

        sorted_data = sorted(data)
        n = len(sorted_data)

        p50_idx = int(n * 0.50)
        p95_idx = int(n * 0.95)
        p99_idx = int(n * 0.99)

        return (
            sorted_data[min(p50_idx, n - 1)],
            sorted_data[min(p95_idx, n - 1)],
            sorted_data[min(p99_idx, n - 1)],
        )

    def reset(self):
        """重置所有指标"""
        with self.lock:
            self.received_total = 0
            self.dispatched_success = 0
            self.dispatched_failed = 0
            self.handler_success = 0
            self.handler_failed = 0
            self.dispatch_queue_size = 0  # ✅ 派发队列大小

            self.dispatch_latencies.clear()
            self.handler_latencies.clear()

            self._avg_dispatch_latency_ms = 0.0
            self._avg_handler_latency_ms = 0.0

            self.start_time = time.time()

    def print_summary(self):
        """打印指标摘要"""
        summary = self.get_summary()

        print("\n" + "=" * 60)
        print("📊 AgentCP 消息处理指标")
        print("=" * 60)

        # 基础计数
        print(f"\n📨 消息统计:")
        print(f"  接收总数: {summary['received_total']}")
        print(f"  派发成功: {summary['dispatched_success']}")
        print(f"  派发失败: {summary['dispatched_failed']}")
        print(f"  处理成功: {summary['handler_success']}")
        print(f"  处理失败: {summary['handler_failed']}")
        print(f"  派发队列: {summary['dispatch_queue_size']}")

        # 成功率
        print(f"\n✅ 成功率:")
        print(f"  派发成功率: {summary['dispatch_success_rate']}")
        print(f"  处理成功率: {summary['handler_success_rate']}")

        # 延迟
        print(f"\n⏱️  延迟统计:")
        print(f"  派发延迟 (ms):")
        print(f"    平均: {summary['dispatch_latency']['avg_ms']}")
        print(f"    P50:  {summary['dispatch_latency']['p50_ms']}")
        print(f"    P95:  {summary['dispatch_latency']['p95_ms']}")
        print(f"    P99:  {summary['dispatch_latency']['p99_ms']}")

        print(f"  处理延迟 (ms):")
        print(f"    平均: {summary['handler_latency']['avg_ms']}")
        print(f"    P50:  {summary['handler_latency']['p50_ms']}")
        print(f"    P95:  {summary['handler_latency']['p95_ms']}")
        print(f"    P99:  {summary['handler_latency']['p99_ms']}")

        # 吞吐量
        print(f"\n🚀 吞吐量:")
        print(f"  接收速率: {summary['throughput']['messages_per_second']} msg/s")
        print(f"  派发速率: {summary['throughput']['dispatched_per_second']} msg/s")

        # 运行时间
        print(f"\n⏰ 运行时间: {summary['uptime_seconds']} 秒")
        print("=" * 60 + "\n")
