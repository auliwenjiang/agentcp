# -*- coding: utf-8 -*-
"""
时间序列指标存储

使用 SQLite 存储时间序列监控数据，支持历史查询和趋势分析
"""

import sqlite3
import time
import threading
from typing import List, Dict, Any, Optional


class MetricsStore:
    """时间序列数据存储（基于SQLite）

    特性：
    - 轻量级，无需额外部署
    - 支持高效的时间范围查询
    - 自动清理过期数据
    - 线程安全
    """

    def __init__(self, db_path: str):
        """初始化时间序列存储

        Args:
            db_path: SQLite 数据库文件路径
        """
        self.db_path = db_path
        self.lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        """初始化数据库表结构"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # 创建时间序列表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS metrics_timeseries (
                    timestamp INTEGER PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    received_total INTEGER DEFAULT 0,
                    dispatched_success INTEGER DEFAULT 0,
                    dispatched_failed INTEGER DEFAULT 0,
                    handler_success INTEGER DEFAULT 0,
                    handler_failed INTEGER DEFAULT 0,
                    dispatch_queue_size INTEGER DEFAULT 0,
                    avg_dispatch_latency_ms REAL DEFAULT 0.0,
                    avg_handler_latency_ms REAL DEFAULT 0.0,
                    p50_dispatch_latency_ms REAL DEFAULT 0.0,
                    p95_dispatch_latency_ms REAL DEFAULT 0.0,
                    p99_dispatch_latency_ms REAL DEFAULT 0.0,
                    throughput_per_second REAL DEFAULT 0.0,
                    success_rate REAL DEFAULT 0.0
                )
            ''')

            # 创建索引（优化查询性能）
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_timestamp
                ON metrics_timeseries(timestamp)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_agent_id_timestamp
                ON metrics_timeseries(agent_id, timestamp)
            ''')

            conn.commit()
            conn.close()

    def insert_snapshot(self, metrics: dict):
        """插入一个时间点的指标快照（非阻塞）

        Args:
            metrics: 指标字典，必须包含以下字段：
                - agent_id: AgentID 标识
                - timestamp: 时间戳（可选，默认当前时间）
                - received_total: 累计接收消息总数
                - dispatched_success: 累计派发成功数
                - dispatched_failed: 累计派发失败数
                - handler_success: 累计处理成功数（可选）
                - handler_failed: 累计处理失败数（可选）
                - dispatch_queue_size: 当前派发队列大小
                - avg_dispatch_latency_ms: 平均派发延迟（可选）
                - avg_handler_latency_ms: 平均处理延迟（可选）
                - p50_dispatch_latency_ms: P50延迟（可选）
                - p95_dispatch_latency_ms: P95延迟（可选）
                - p99_dispatch_latency_ms: P99延迟（可选）
        """
        timestamp = metrics.get('timestamp', int(time.time()))
        if isinstance(timestamp, float):
            timestamp = int(timestamp)

        # ✅ 使用 trylock 模式：如果锁被占用，跳过本次写入（不阻塞）
        locked = self.lock.acquire(blocking=False)
        if not locked:
            # 锁被占用，跳过本次写入（避免阻塞主流程）
            return

        try:
            conn = sqlite3.connect(self.db_path, timeout=1.0)  # 1秒超时
            cursor = conn.cursor()

            try:
                # 计算吞吐量和成功率
                received_total = metrics.get('received_total', 0)
                dispatched_success = metrics.get('dispatched_success', 0)
                uptime = metrics.get('uptime_seconds', 1)

                throughput = received_total / max(uptime, 1)
                success_rate = (dispatched_success / max(received_total, 1)) * 100 if received_total > 0 else 0.0

                cursor.execute('''
                    INSERT OR REPLACE INTO metrics_timeseries (
                        timestamp, agent_id, received_total, dispatched_success,
                        dispatched_failed, handler_success, handler_failed,
                        dispatch_queue_size, avg_dispatch_latency_ms, avg_handler_latency_ms,
                        p50_dispatch_latency_ms, p95_dispatch_latency_ms, p99_dispatch_latency_ms,
                        throughput_per_second, success_rate
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    timestamp,
                    metrics.get('agent_id', 'unknown'),
                    received_total,
                    dispatched_success,
                    metrics.get('dispatched_failed', 0),
                    metrics.get('handler_success', 0),
                    metrics.get('handler_failed', 0),
                    metrics.get('dispatch_queue_size', 0),
                    self._safe_float(metrics.get('avg_dispatch_latency_ms')),
                    self._safe_float(metrics.get('avg_handler_latency_ms')),
                    self._safe_float(metrics.get('p50_dispatch_latency_ms')),
                    self._safe_float(metrics.get('p95_dispatch_latency_ms')),
                    self._safe_float(metrics.get('p99_dispatch_latency_ms')),
                    throughput,
                    success_rate,
                ))

                conn.commit()
            except Exception as e:
                print(f"❌ [MetricsStore] 插入数据失败: {e}")
                conn.rollback()
            finally:
                conn.close()
        finally:
            # ✅ 确保释放锁（无论是否成功）
            self.lock.release()

    def _safe_float(self, value) -> float:
        """安全地转换为浮点数

        Args:
            value: 待转换的值

        Returns:
            转换后的浮点数，失败返回0.0
        """
        if value is None:
            return 0.0
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return 0.0
        return float(value)

    def query_range(
        self,
        from_ts: int,
        to_ts: int,
        agent_id: Optional[str] = None,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """查询时间范围内的数据

        Args:
            from_ts: 起始时间戳
            to_ts: 结束时间戳
            agent_id: AgentID 过滤（可选）
            limit: 最大返回记录数

        Returns:
            时间序列数据列表
        """
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            try:
                if agent_id:
                    cursor.execute('''
                        SELECT * FROM metrics_timeseries
                        WHERE timestamp >= ? AND timestamp <= ? AND agent_id = ?
                        ORDER BY timestamp ASC
                        LIMIT ?
                    ''', (from_ts, to_ts, agent_id, limit))
                else:
                    cursor.execute('''
                        SELECT * FROM metrics_timeseries
                        WHERE timestamp >= ? AND timestamp <= ?
                        ORDER BY timestamp ASC
                        LIMIT ?
                    ''', (from_ts, to_ts, limit))

                rows = cursor.fetchall()
                return [self._row_to_dict(row) for row in rows]
            finally:
                conn.close()

    def query_latest(self, agent_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """查询最新的数据点

        Args:
            agent_id: AgentID 过滤（可选）
            limit: 最大返回记录数

        Returns:
            最新的时间序列数据列表
        """
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            try:
                if agent_id:
                    cursor.execute('''
                        SELECT * FROM metrics_timeseries
                        WHERE agent_id = ?
                        ORDER BY timestamp DESC
                        LIMIT ?
                    ''', (agent_id, limit))
                else:
                    cursor.execute('''
                        SELECT * FROM metrics_timeseries
                        ORDER BY timestamp DESC
                        LIMIT ?
                    ''', (limit,))

                rows = cursor.fetchall()
                return [self._row_to_dict(row) for row in rows]
            finally:
                conn.close()

    def _row_to_dict(self, row) -> Dict[str, Any]:
        """将数据库行转换为字典

        Args:
            row: 数据库查询结果行

        Returns:
            包含所有字段的字典
        """
        columns = [
            'timestamp', 'agent_id', 'received_total', 'dispatched_success',
            'dispatched_failed', 'handler_success', 'handler_failed',
            'dispatch_queue_size', 'avg_dispatch_latency_ms', 'avg_handler_latency_ms',
            'p50_dispatch_latency_ms', 'p95_dispatch_latency_ms', 'p99_dispatch_latency_ms',
            'throughput_per_second', 'success_rate'
        ]
        return dict(zip(columns, row))

    def cleanup_old_data(self, retention_days: int = 7):
        """清理过期数据

        Args:
            retention_days: 数据保留天数（默认7天）
        """
        cutoff = int(time.time()) - (retention_days * 86400)

        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            try:
                cursor.execute('DELETE FROM metrics_timeseries WHERE timestamp < ?', (cutoff,))
                deleted_count = cursor.rowcount
                conn.commit()

                if deleted_count > 0:
                    print(f"🧹 [MetricsStore] 清理了 {deleted_count} 条过期数据 (>{retention_days}天)")
            except Exception as e:
                print(f"❌ [MetricsStore] 清理数据失败: {e}")
                conn.rollback()
            finally:
                conn.close()

    def get_stats(self) -> Dict[str, Any]:
        """获取数据库统计信息

        Returns:
            包含数据库统计信息的字典
        """
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            try:
                # 查询总记录数
                cursor.execute('SELECT COUNT(*) FROM metrics_timeseries')
                total_records = cursor.fetchone()[0]

                # 查询时间范围
                cursor.execute('SELECT MIN(timestamp), MAX(timestamp) FROM metrics_timeseries')
                min_ts, max_ts = cursor.fetchone()

                # 查询不同 agent_id 数量
                cursor.execute('SELECT COUNT(DISTINCT agent_id) FROM metrics_timeseries')
                agent_count = cursor.fetchone()[0]

                return {
                    'total_records': total_records,
                    'min_timestamp': min_ts,
                    'max_timestamp': max_ts,
                    'agent_count': agent_count,
                    'db_path': self.db_path,
                }
            finally:
                conn.close()

    def close(self):
        """关闭存储（预留接口，SQLite 会自动管理连接）"""
        pass
