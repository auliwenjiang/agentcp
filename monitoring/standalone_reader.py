# -*- coding: utf-8 -*-
"""
独立监控数据读取器

支持跨进程读取监控数据，无需依赖全局变量或进程内通信
"""

import os
import time
from typing import Dict, Any, Optional, List

from .metrics_store import MetricsStore
from .sliding_window import SlidingWindowMetrics


class StandaloneMonitoringReader:
    """独立监控数据读取器

    可以在任何进程中使用，通过直接读取 SQLite 数据库获取监控数据
    """

    def __init__(self, db_path: str = None):
        """初始化读取器

        Args:
            db_path: 数据库路径，如果为空则使用默认路径
        """
        if db_path is None:
            # 使用默认路径
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
            db_path = os.path.join(project_root, 'backup', 'metrics_timeseries.db')

        self.db_path = db_path
        self.metrics_store = MetricsStore(db_path)

    def get_realtime_metrics(self) -> Dict[str, Any]:
        """获取实时监控指标

        Returns:
            包含累计指标和时间窗口统计的字典
        """
        # 检查数据库文件是否存在
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"监控数据库不存在: {self.db_path}")

        # 获取最新的一条记录作为累计指标
        latest_records = self.metrics_store.query_latest(limit=1)
        if not latest_records:
            raise ValueError("数据库中没有监控数据")

        cumulative = latest_records[0]

        # 计算时间窗口统计
        windows = self._calculate_windows()

        return {
            'agent_id': cumulative.get('agent_id', 'unknown'),
            'timestamp': cumulative.get('timestamp', time.time()),
            'cumulative': self._format_cumulative(cumulative),
            'windows': windows
        }

    def _format_cumulative(self, record: dict) -> dict:
        """格式化累计指标"""
        # 计算成功率
        received_total = record.get('received_total', 0)
        dispatched_success = record.get('dispatched_success', 0)

        dispatch_success_rate = "0.00%"
        if received_total > 0:
            rate = (dispatched_success / received_total) * 100
            dispatch_success_rate = f"{rate:.2f}%"

        # 计算运行时长（使用最早的记录时间）
        store_stats = self.metrics_store.get_stats()
        min_ts = store_stats.get('min_timestamp', record['timestamp'])
        uptime_seconds = record['timestamp'] - min_ts if min_ts else 0

        return {
            'received_total': record.get('received_total', 0),
            'dispatched_success': record.get('dispatched_success', 0),
            'dispatched_failed': record.get('dispatched_failed', 0),
            'handler_success': record.get('handler_success', 0),
            'handler_failed': record.get('handler_failed', 0),
            'dispatch_queue_size': record.get('dispatch_queue_size', 0),
            'dispatch_success_rate': dispatch_success_rate,
            'uptime_seconds': str(int(uptime_seconds)),
            'dispatch_latency': {
                'avg_ms': f"{record.get('avg_dispatch_latency_ms', 0):.2f}",
                'p50_ms': f"{record.get('p50_dispatch_latency_ms', 0):.2f}",
                'p95_ms': f"{record.get('p95_dispatch_latency_ms', 0):.2f}",
                'p99_ms': f"{record.get('p99_dispatch_latency_ms', 0):.2f}",
            }
        }

    def _calculate_windows(self) -> Dict[str, Dict[str, Any]]:
        """计算时间窗口统计"""
        now = int(time.time())

        windows = {
            '1m': self._calculate_window(now, 60),
            '3m': self._calculate_window(now, 180),
            '5m': self._calculate_window(now, 300),
            '10m': self._calculate_window(now, 600),
            '15m': self._calculate_window(now, 900),
        }

        return windows

    def _calculate_window(self, now: int, duration: int) -> Dict[str, Any]:
        """计算单个时间窗口的统计数据"""
        from_ts = now - duration
        to_ts = now

        # 查询时间范围内的数据
        records = self.metrics_store.query_range(from_ts, to_ts)

        if len(records) < 2:
            # 数据不足，返回空统计
            return {
                'throughput_per_second': 0.0,
                'avg_latency_ms': 0.0,
                'success_rate': 0.0,
                'total_messages': 0,
                'failed_messages': 0,
                'avg_queue_size': 0.0,
                'window_duration': duration,
                'data_points_count': len(records)
            }

        # 计算增量
        first_record = records[0]
        last_record = records[-1]

        received_delta = last_record['received_total'] - first_record['received_total']
        success_delta = last_record['dispatched_success'] - first_record['dispatched_success']
        failed_delta = last_record['dispatched_failed'] - first_record['dispatched_failed']

        # 计算实际时间跨度
        actual_duration = last_record['timestamp'] - first_record['timestamp']
        if actual_duration < 1:
            actual_duration = 1

        # 计算吞吐量
        throughput = received_delta / actual_duration

        # 计算成功率
        success_rate = 0.0
        if received_delta > 0:
            success_rate = (success_delta / received_delta) * 100

        # 计算平均延迟
        latencies = [r['avg_dispatch_latency_ms'] for r in records if r['avg_dispatch_latency_ms'] > 0]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0.0

        # 计算平均队列大小
        queue_sizes = [r['dispatch_queue_size'] for r in records]
        avg_queue_size = sum(queue_sizes) / len(queue_sizes) if queue_sizes else 0.0

        return {
            'throughput_per_second': round(throughput, 2),
            'avg_latency_ms': round(avg_latency, 2),
            'success_rate': round(success_rate, 2),
            'total_messages': received_delta,
            'failed_messages': failed_delta,
            'avg_queue_size': round(avg_queue_size, 1),
            'window_duration': duration,
            'data_points_count': len(records)
        }

    def get_window_metrics(self, window_names: List[str]) -> Dict[str, Dict[str, Any]]:
        """获取指定时间窗口的指标"""
        now = int(time.time())

        window_durations = {
            '1m': 60,
            '3m': 180,
            '5m': 300,
            '10m': 600,
            '15m': 900,
        }

        result = {}
        for name in window_names:
            if name in window_durations:
                result[name] = self._calculate_window(now, window_durations[name])

        return result

    def get_history(self, from_ts: int, to_ts: int, limit: int = 1000) -> List[Dict[str, Any]]:
        """获取历史数据"""
        return self.metrics_store.query_range(from_ts, to_ts, limit=limit)

    def get_latest_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取最新的历史数据"""
        return self.metrics_store.query_latest(limit=limit)

    def get_service_info(self) -> Dict[str, Any]:
        """获取监控服务信息"""
        store_stats = self.metrics_store.get_stats()

        # 检查是否有最近的数据更新（最近30秒内）
        max_ts = store_stats.get('max_timestamp', 0)
        is_running = (time.time() - max_ts) < 30 if max_ts else False

        return {
            'agent_id': 'unknown',
            'running': is_running,
            'snapshot_interval': 10,
            'snapshot_count': store_stats.get('total_records', 0),
            'store_stats': store_stats
        }


def get_standalone_reader(db_path: str = None) -> StandaloneMonitoringReader:
    """获取独立监控读取器实例

    Args:
        db_path: 数据库路径，如果为空则使用默认路径

    Returns:
        StandaloneMonitoringReader 实例
    """
    return StandaloneMonitoringReader(db_path)
