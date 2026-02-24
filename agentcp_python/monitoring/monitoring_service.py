# -*- coding: utf-8 -*-
"""
统一监控服务

集成滑动窗口统计和时间序列存储，提供完整的监控解决方案
"""

import threading
import time
from typing import Dict, Any, List, Optional

from .sliding_window import SlidingWindowMetrics
from .metrics_store import MetricsStore


class MonitoringService:
    """统一监控服务

    职责：
    - 定期采集指标快照（每10秒）
    - 更新滑动窗口统计
    - 持久化到时间序列存储
    - 提供实时和历史数据查询接口
    """

    def __init__(
        self,
        agent_id: str,
        metrics_collector,
        db_path: str,
        snapshot_interval: int = 10
    ):
        """初始化监控服务

        Args:
            agent_id: AgentID 标识
            metrics_collector: MessageMetrics 实例
            db_path: 时间序列数据库路径
            snapshot_interval: 快照间隔（秒），默认10秒
        """
        self.agent_id = agent_id
        self.metrics_collector = metrics_collector
        self.snapshot_interval = snapshot_interval

        # 初始化组件
        self.sliding_windows = SlidingWindowMetrics()
        self.metrics_store = MetricsStore(db_path)

        # 线程控制
        self._running = False
        self._snapshot_thread: Optional[threading.Thread] = None

        # 统计信息
        self._snapshot_count = 0
        self._last_cleanup_time = time.time()

    def start(self):
        """启动监控服务"""
        if self._running:
            print(f"⚠️ [MonitoringService] 监控服务已在运行")
            return

        self._running = True
        self._snapshot_thread = threading.Thread(
            target=self._snapshot_loop,
            daemon=True,
            name=f"MetricsSnapshot-{self.agent_id}"
        )
        self._snapshot_thread.start()
        print(f"📊 [MonitoringService] 已启动 (agent_id={self.agent_id}, interval={self.snapshot_interval}s)")

    def stop(self, wait: bool = True):
        """停止监控服务

        Args:
            wait: 是否等待线程完全停止（默认True）
                  设为False可避免阻塞主流程
        """
        if not self._running:
            return

        self._running = False

        # 如果需要等待线程停止
        if wait and self._snapshot_thread and self._snapshot_thread.is_alive():
            self._snapshot_thread.join(timeout=5.0)

        # 最后一次快照保存（仅在等待模式下执行）
        if wait:
            try:
                self._take_snapshot()
                print(f"📊 [MonitoringService] 已停止 (共采集 {self._snapshot_count} 次快照)")
            except Exception as e:
                print(f"⚠️ [MonitoringService] 最终快照失败: {e}")
        else:
            print(f"📊 [MonitoringService] 停止信号已发送（非阻塞模式）")

        if wait:
            self._snapshot_thread = None

    def _snapshot_loop(self):
        """快照循环 - 每N秒收集一次数据"""
        while self._running:
            try:
                self._take_snapshot()

                # 定期清理旧数据（每小时一次）
                now = time.time()
                if now - self._last_cleanup_time > 3600:
                    self._cleanup_old_data()
                    self._last_cleanup_time = now

            except Exception as e:
                print(f"❌ [MonitoringService] 快照失败: {e}")
                import traceback
                traceback.print_exc()

            # 等待下一次快照
            time.sleep(self.snapshot_interval)

    def _take_snapshot(self):
        """执行一次快照采集（非阻塞）"""
        try:
            # 1. 获取当前指标（使用 timeout 防止阻塞）
            current_metrics = self.metrics_collector.get_summary()
            current_metrics['agent_id'] = self.agent_id
            current_metrics['timestamp'] = time.time()
        except Exception as e:
            # 获取指标失败，跳过本次快照（不影响核心流程）
            print(f"⚠️ [MonitoringService] 获取指标失败，跳过本次快照: {e}")
            return

        # 解析字符串格式的指标（兼容现有 MessageMetrics）
        self._parse_metrics(current_metrics)

        # 2. 更新滑动窗口
        self.sliding_windows.update(current_metrics)

        # 3. 存储到时间序列数据库
        self.metrics_store.insert_snapshot(current_metrics)

        self._snapshot_count += 1

        # 调试日志（可选）
        if self._snapshot_count % 6 == 0:  # 每1分钟打印一次
            print(
                f"📊 [MonitoringService] 快照 #{self._snapshot_count}: "
                f"received={current_metrics.get('received_total', 0)}, "
                f"queue={current_metrics.get('dispatch_queue_size', 0)}"
            )

    def _parse_metrics(self, metrics: dict):
        """解析和标准化指标数据

        处理现有 MessageMetrics 返回的字符串格式指标
        """
        # 解析延迟数据（从嵌套字典中提取）
        if 'dispatch_latency' in metrics and isinstance(metrics['dispatch_latency'], dict):
            dispatch_latency = metrics['dispatch_latency']
            metrics['avg_dispatch_latency_ms'] = self._parse_float(dispatch_latency.get('avg_ms', '0'))
            metrics['p50_dispatch_latency_ms'] = self._parse_float(dispatch_latency.get('p50_ms', '0'))
            metrics['p95_dispatch_latency_ms'] = self._parse_float(dispatch_latency.get('p95_ms', '0'))
            metrics['p99_dispatch_latency_ms'] = self._parse_float(dispatch_latency.get('p99_ms', '0'))

        if 'handler_latency' in metrics and isinstance(metrics['handler_latency'], dict):
            handler_latency = metrics['handler_latency']
            metrics['avg_handler_latency_ms'] = self._parse_float(handler_latency.get('avg_ms', '0'))

        # 解析运行时间
        if 'uptime_seconds' in metrics:
            metrics['uptime_seconds'] = self._parse_float(metrics['uptime_seconds'])

    def _parse_float(self, value) -> float:
        """安全地解析浮点数"""
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return 0.0
        return 0.0

    def _cleanup_old_data(self):
        """清理旧数据"""
        try:
            self.metrics_store.cleanup_old_data(retention_days=7)
        except Exception as e:
            print(f"⚠️ [MonitoringService] 清理旧数据失败: {e}")

    def get_realtime_metrics(self) -> Dict[str, Any]:
        """获取实时指标（包括所有时间窗口）

        Returns:
            包含以下内容的字典：
            - agent_id: AgentID 标识
            - timestamp: 当前时间戳
            - cumulative: 累计指标（来自 MessageMetrics）
            - windows: 所有时间窗口的统计数据
        """
        base_metrics = self.metrics_collector.get_summary()
        window_stats = self.sliding_windows.get_all_windows()

        return {
            'agent_id': self.agent_id,
            'timestamp': time.time(),
            'cumulative': base_metrics,  # 累计指标
            'windows': window_stats,     # 时间窗口指标
        }

    def get_window_metrics(self, window_names: List[str]) -> Dict[str, Dict[str, Any]]:
        """获取指定时间窗口的指标

        Args:
            window_names: 窗口名称列表，如 ['1m', '3m', '5m']

        Returns:
            窗口统计数据字典
        """
        all_windows = self.sliding_windows.get_all_windows()
        return {
            name: all_windows.get(name, {})
            for name in window_names
            if name in all_windows
        }

    def get_history(self, from_ts: int, to_ts: int, limit: int = 1000) -> List[Dict[str, Any]]:
        """获取历史数据

        Args:
            from_ts: 起始时间戳
            to_ts: 结束时间戳
            limit: 最大返回记录数

        Returns:
            历史数据列表
        """
        return self.metrics_store.query_range(from_ts, to_ts, self.agent_id, limit)

    def get_latest_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取最新的历史数据

        Args:
            limit: 最大返回记录数

        Returns:
            最新的历史数据列表
        """
        return self.metrics_store.query_latest(self.agent_id, limit)

    def get_service_info(self) -> Dict[str, Any]:
        """获取监控服务信息

        Returns:
            包含服务状态和统计信息的字典
        """
        store_stats = self.metrics_store.get_stats()

        return {
            'agent_id': self.agent_id,
            'running': self._running,
            'snapshot_interval': self.snapshot_interval,
            'snapshot_count': self._snapshot_count,
            'store_stats': store_stats,
        }

    def reset_windows(self):
        """重置所有时间窗口（用于测试）"""
        self.sliding_windows.reset()
