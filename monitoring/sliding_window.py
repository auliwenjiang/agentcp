# -*- coding: utf-8 -*-
"""
滑动窗口指标统计

支持多时间窗口的实时统计分析
"""

import time
from typing import Dict, List, Tuple, Any


class TimeWindow:
    """单个时间窗口

    维护一个固定时长的滑动窗口，自动清理过期数据点
    """

    def __init__(self, duration_seconds: int):
        """初始化时间窗口

        Args:
            duration_seconds: 窗口时长（秒）
        """
        self.duration = duration_seconds
        self.data_points: List[Tuple[float, dict]] = []  # [(timestamp, metrics), ...]

    def add_snapshot(self, timestamp: float, metrics: dict):
        """添加一个时间点的指标快照

        Args:
            timestamp: 时间戳
            metrics: 指标字典，必须包含以下字段：
                - received_delta: 增量接收消息数
                - success_delta: 增量成功派发数
                - failed_delta: 增量失败数
                - avg_latency: 平均延迟（毫秒）
                - queue_size: 当前队列大小
        """
        self.data_points.append((timestamp, metrics))

        # 清理过期数据（保留窗口时长内的数据）
        cutoff = timestamp - self.duration
        self.data_points = [(t, m) for t, m in self.data_points if t >= cutoff]

    def get_stats(self) -> Dict[str, Any]:
        """计算窗口内的统计数据

        Returns:
            包含以下统计指标的字典：
            - throughput_per_second: 吞吐量（消息/秒）
            - avg_latency_ms: 平均延迟（毫秒）
            - success_rate: 成功率（%）
            - total_messages: 窗口内总消息数
            - failed_messages: 窗口内失败消息数
            - avg_queue_size: 平均队列大小
            - window_duration: 窗口时长（秒）
            - data_points_count: 数据点数量
        """
        if not self.data_points:
            return {
                'throughput_per_second': 0.0,
                'avg_latency_ms': 0.0,
                'success_rate': 0.0,
                'total_messages': 0,
                'failed_messages': 0,
                'avg_queue_size': 0,
                'window_duration': self.duration,
                'data_points_count': 0,
            }

        # 计算总量
        total_received = sum(m.get('received_delta', 0) for _, m in self.data_points)
        total_success = sum(m.get('success_delta', 0) for _, m in self.data_points)
        total_failed = sum(m.get('failed_delta', 0) for _, m in self.data_points)

        # 计算实际时间跨度（可能小于窗口时长）
        actual_duration = self.data_points[-1][0] - self.data_points[0][0]
        if actual_duration < 1:
            actual_duration = 1  # 避免除零

        # 计算吞吐量 (msg/s)
        throughput = total_received / actual_duration

        # 计算平均延迟（只考虑有延迟数据的点）
        latencies = [m.get('avg_latency', 0) for _, m in self.data_points if m.get('avg_latency', 0) > 0]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0.0

        # 计算成功率
        success_rate = (total_success / max(total_received, 1)) * 100

        # 计算平均队列大小
        queue_sizes = [m.get('queue_size', 0) for _, m in self.data_points]
        avg_queue_size = sum(queue_sizes) / len(queue_sizes) if queue_sizes else 0

        return {
            'throughput_per_second': round(throughput, 2),
            'avg_latency_ms': round(avg_latency, 2),
            'success_rate': round(success_rate, 2),
            'total_messages': total_received,
            'failed_messages': total_failed,
            'avg_queue_size': round(avg_queue_size, 1),
            'window_duration': self.duration,
            'data_points_count': len(self.data_points),
        }


class SlidingWindowMetrics:
    """多时间窗口管理器

    管理多个不同时长的滑动窗口，提供多粒度的统计视图
    支持的窗口：1分钟、3分钟、5分钟、10分钟、15分钟
    """

    def __init__(self):
        """初始化多时间窗口管理器"""
        # 创建多个时间窗口
        self.windows: Dict[str, TimeWindow] = {
            '1m': TimeWindow(60),      # 1分钟
            '3m': TimeWindow(180),     # 3分钟
            '5m': TimeWindow(300),     # 5分钟
            '10m': TimeWindow(600),    # 10分钟
            '15m': TimeWindow(900),    # 15分钟
        }

        # 记录上一次快照的状态
        self.last_snapshot_time = 0
        self.last_metrics_snapshot: Dict[str, Any] = {}

    def update(self, current_metrics: dict):
        """更新所有窗口（应该每10秒调用一次）

        Args:
            current_metrics: 当前累计指标，必须包含以下字段：
                - received_total: 累计接收消息总数
                - dispatched_success: 累计派发成功数
                - dispatched_failed: 累计派发失败数
                - dispatch_queue_size: 当前派发队列大小
                - avg_dispatch_latency_ms: 平均派发延迟（可选）
                - avg_handler_latency_ms: 平均处理延迟（可选）
        """
        now = time.time()

        # 计算增量指标 (delta)
        metrics_delta = self._calculate_delta(current_metrics)

        # 更新所有窗口
        for window in self.windows.values():
            window.add_snapshot(now, metrics_delta)

        # 保存当前快照状态
        self.last_snapshot_time = now
        self.last_metrics_snapshot = current_metrics.copy()

    def _calculate_delta(self, current: dict) -> dict:
        """计算两次快照之间的增量

        Args:
            current: 当前累计指标

        Returns:
            增量指标字典
        """
        if not self.last_metrics_snapshot:
            # 第一次快照，返回零增量
            return {
                'received_delta': 0,
                'success_delta': 0,
                'failed_delta': 0,
                'avg_latency': 0.0,
                'queue_size': current.get('dispatch_queue_size', 0),
            }

        # 计算增量
        received_delta = current.get('received_total', 0) - self.last_metrics_snapshot.get('received_total', 0)
        success_delta = current.get('dispatched_success', 0) - self.last_metrics_snapshot.get('dispatched_success', 0)
        failed_delta = current.get('dispatched_failed', 0) - self.last_metrics_snapshot.get('dispatched_failed', 0)

        # 获取平均延迟（优先使用 dispatch_latency，其次使用 handler_latency）
        avg_latency = 0.0
        if 'avg_dispatch_latency_ms' in current:
            avg_latency = current['avg_dispatch_latency_ms']
        elif 'avg_handler_latency_ms' in current:
            avg_latency = current['avg_handler_latency_ms']

        return {
            'received_delta': max(0, received_delta),  # 防止负数
            'success_delta': max(0, success_delta),
            'failed_delta': max(0, failed_delta),
            'avg_latency': avg_latency,
            'queue_size': current.get('dispatch_queue_size', 0),
        }

    def get_window_stats(self, window_name: str) -> Dict[str, Any]:
        """获取指定窗口的统计数据

        Args:
            window_name: 窗口名称（'1m', '3m', '5m', '10m', '15m'）

        Returns:
            窗口统计数据字典，如果窗口不存在则返回空字典
        """
        if window_name not in self.windows:
            return {}
        return self.windows[window_name].get_stats()

    def get_all_windows(self) -> Dict[str, Dict[str, Any]]:
        """获取所有窗口的统计数据

        Returns:
            字典，key为窗口名称，value为统计数据
        """
        return {
            name: window.get_stats()
            for name, window in self.windows.items()
        }

    def reset(self):
        """重置所有窗口数据"""
        for window in self.windows.values():
            window.data_points.clear()
        self.last_snapshot_time = 0
        self.last_metrics_snapshot.clear()
