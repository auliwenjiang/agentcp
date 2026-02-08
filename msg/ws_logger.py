# -*- coding: utf-8 -*-
"""
WebSocket 专用日志模块

独立记录 WebSocket 连接的断开、重连、错误等事件。
日志文件: logs/websocket.log

使用直接文件写入方式，避免与其他日志库冲突。
"""

import os
import json
import threading
import sys
import time
from datetime import datetime
from typing import Optional, Dict, Any

# 跨平台文件锁支持
if sys.platform == 'win32':
    import msvcrt
    # Windows: 使用 msvcrt.locking，锁定文件开头的一段区域
    _LOCK_BYTES = 1024 * 1024  # 锁定 1MB 区域（足够覆盖日志写入）

    def lock_file(f):
        """获取文件锁（Windows）"""
        try:
            # 移动到文件开头进行锁定
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, _LOCK_BYTES)
        except (IOError, OSError):
            # 锁定失败（可能被其他进程占用），忽略继续写入
            pass

    def unlock_file(f):
        """释放文件锁（Windows）"""
        try:
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, _LOCK_BYTES)
        except (IOError, OSError, ValueError):
            # 解锁失败，忽略
            pass
else:
    import fcntl

    def lock_file(f):
        """获取文件锁（Unix/Linux/Mac）"""
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (IOError, OSError):
            # 锁定失败，忽略继续写入
            pass

    def unlock_file(f):
        """释放文件锁（Unix/Linux/Mac）"""
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except (IOError, OSError):
            pass


class WebSocketLogger:
    """WebSocket 专用日志记录器 - 直接文件写入版本"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        # 文件写入锁
        self._file_lock = threading.Lock()

        try:
            # 创建日志目录
            self.log_dir = os.path.join(os.getcwd(), "logs")
            os.makedirs(self.log_dir, exist_ok=True)

            # 日志文件路径
            self.log_file = os.path.join(self.log_dir, "websocket.log")

            # 最大文件大小 (10MB)
            self.max_file_size = 10 * 1024 * 1024
            # 保留备份数量
            self.backup_count = 5

            self._logger_ready = True

        except Exception as e:
            print(f"[WARNING] WebSocket 日志初始化失败: {e}")
            self._logger_ready = False
            self.log_file = None

        # 统计信息
        self._stats = {
            "disconnect_count": 0,
            "reconnect_count": 0,
            "reconnect_success_count": 0,
            "reconnect_fail_count": 0,
            "last_disconnect_time": None,
            "last_reconnect_time": None,
            "last_error": None
        }
        self._stats_lock = threading.Lock()

    def _rotate_if_needed(self):
        """检查并执行日志轮转"""
        if not self.log_file or not os.path.exists(self.log_file):
            return

        try:
            file_size = os.path.getsize(self.log_file)
            if file_size >= self.max_file_size:
                # 执行轮转
                for i in range(self.backup_count - 1, 0, -1):
                    old_file = f"{self.log_file}.{i}"
                    new_file = f"{self.log_file}.{i + 1}"
                    if os.path.exists(old_file):
                        if os.path.exists(new_file):
                            os.remove(new_file)
                        os.rename(old_file, new_file)

                # 将当前日志重命名为 .1
                backup_file = f"{self.log_file}.1"
                if os.path.exists(backup_file):
                    os.remove(backup_file)
                os.rename(self.log_file, backup_file)

        except Exception as e:
            # 轮转失败不影响日志写入
            print(f"[WARNING] 日志轮转失败: {e}")

    def _write_log(self, level: str, message: str):
        """直接写入日志文件（线程安全）"""
        if not self._logger_ready or not self.log_file:
            # 如果日志系统不可用，输出到标准输出
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{level}] {message}")
            return

        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_line = f"[{timestamp}] [{level}] {message}\n"

        with self._file_lock:
            try:
                # 检查是否需要轮转
                self._rotate_if_needed()

                # 直接写入文件
                with open(self.log_file, 'a', encoding='utf-8') as f:
                    # 尝试使用文件锁（跨进程安全）
                    locked = False
                    try:
                        lock_file(f)
                        locked = True
                        # 写入时移动到文件末尾（append模式已自动处理，但显式调用更安全）
                        f.seek(0, 2)  # SEEK_END
                        f.write(log_line)
                        f.flush()
                        os.fsync(f.fileno())  # 确保写入磁盘
                    except (IOError, OSError) as write_err:
                        # 写入失败，尝试不带 fsync 写入
                        try:
                            f.write(log_line)
                            f.flush()
                        except Exception:
                            raise write_err
                    finally:
                        # 确保始终尝试解锁
                        if locked:
                            unlock_file(f)

            except Exception as e:
                # 写入失败时输出到标准输出
                print(f"[WARNING] 写入日志文件失败: {e}")
                print(log_line.strip())

    def _format_data(self, data: Any, max_length: int = 500) -> str:
        """格式化数据用于日志记录，限制长度"""
        if data is None:
            return "None"
        try:
            if isinstance(data, bytes):
                try:
                    data_str = data.decode('utf-8')
                except UnicodeDecodeError:
                    data_str = f"<binary data, length={len(data)}>"
            elif isinstance(data, dict):
                data_str = json.dumps(data, ensure_ascii=False, indent=2)
            else:
                data_str = str(data)

            if len(data_str) > max_length:
                return data_str[:max_length] + f"... (truncated, total {len(data_str)} chars)"
            return data_str
        except Exception as e:
            return f"<format error: {e}>"

    def log_disconnect(
        self,
        conn_id: int,
        reason: str,
        code: Optional[int] = None,
        received_data: Any = None,
        pending_requests: int = 0,
        extra_info: Optional[Dict] = None
    ):
        """记录连接断开事件"""
        with self._stats_lock:
            self._stats["disconnect_count"] += 1
            self._stats["last_disconnect_time"] = datetime.now().isoformat()
            self._stats["last_error"] = reason

        log_lines = [
            "=" * 80,
            "CONNECTION DISCONNECTED",
            "=" * 80,
            f"  Connection ID    : {conn_id}",
            f"  Disconnect Time  : {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')}",
            f"  Close Code       : {code if code else 'N/A'}",
            f"  Reason           : {reason}",
            f"  Pending Requests : {pending_requests}",
        ]

        if received_data:
            log_lines.append(f"  Received Data    : {self._format_data(received_data)}")

        if extra_info:
            try:
                log_lines.append(f"  Extra Info       : {json.dumps(extra_info, ensure_ascii=False)}")
            except (TypeError, ValueError):
                log_lines.append(f"  Extra Info       : {str(extra_info)}")

        log_lines.append("=" * 80)

        self._write_log("WARNING", "\n".join(log_lines))

    def log_reconnect_start(self, conn_id: int, attempt: int, interval: float):
        """记录开始重连"""
        self._write_log(
            "INFO",
            f"[RECONNECT START] conn_id={conn_id}, attempt={attempt}, interval={interval:.1f}s"
        )

    def log_reconnect_success(
        self,
        conn_id: int,
        attempt: int,
        duration: float,
        pending_recovered: int = 0
    ):
        """记录重连成功"""
        with self._stats_lock:
            self._stats["reconnect_count"] += 1
            self._stats["reconnect_success_count"] += 1
            self._stats["last_reconnect_time"] = datetime.now().isoformat()

        log_lines = [
            "-" * 60,
            "RECONNECTION SUCCESSFUL",
            "-" * 60,
            f"  New Connection ID : {conn_id}",
            f"  Reconnect Time    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"  Attempts          : {attempt}",
            f"  Duration          : {duration:.2f}s",
            f"  Pending Recovered : {pending_recovered}",
            "-" * 60
        ]

        self._write_log("INFO", "\n".join(log_lines))

    def log_reconnect_fail(self, conn_id: int, attempt: int, reason: str):
        """记录重连失败"""
        with self._stats_lock:
            self._stats["reconnect_count"] += 1
            self._stats["reconnect_fail_count"] += 1

        self._write_log(
            "ERROR",
            f"[RECONNECT FAILED] conn_id={conn_id}, attempt={attempt}, reason={reason}"
        )

    def log_connection_closed(
        self,
        conn_id: int,
        code: int,
        reason: str,
        connection_duration: float = 0,
        messages_received: int = 0,
        last_pong_time: float = 0,
        extra_info: Optional[Dict] = None
    ):
        """记录连接关闭事件（增强版，包含诊断信息）"""
        from datetime import datetime as dt

        # 计算最后一次 pong 距离现在的时间
        time_since_last_pong = time.time() - last_pong_time if last_pong_time > 0 else -1

        log_lines = [
            "X" * 80,
            "CONNECTION CLOSED (DETAILED)",
            "X" * 80,
            f"  Connection ID      : {conn_id}",
            f"  Close Time         : {dt.now().strftime('%Y-%m-%d %H:%M:%S.%f')}",
            f"  Close Code         : {code}",
            f"  Close Reason       : {reason}",
            f"  Connection Duration: {connection_duration:.2f}s",
            f"  Messages Received  : {messages_received}",
            f"  Time Since Pong    : {time_since_last_pong:.2f}s" if time_since_last_pong >= 0 else f"  Time Since Pong    : N/A",
        ]

        if extra_info:
            log_lines.append("  --- Extra Info ---")
            for key, value in extra_info.items():
                # 特殊处理消息类型列表，使其更易读
                if key == "recent_msg_types" and isinstance(value, list):
                    if value:
                        log_lines.append(f"  {key:18}: {', '.join(value)}")
                    else:
                        log_lines.append(f"  {key:18}: (none)")
                else:
                    log_lines.append(f"  {key:18}: {value}")

        # 添加诊断提示
        if code == 1006:
            log_lines.append("  --- Diagnosis ---")
            log_lines.append("  Code 1006 表示异常关闭，可能的原因：")
            log_lines.append("    1. 网络中断或不稳定")
            log_lines.append("    2. 服务器主动断开但未发送关闭帧")
            log_lines.append("    3. 心跳超时（检查 ping_interval 和 ping_timeout 配置）")
            log_lines.append("    4. 防火墙/代理/负载均衡器超时断开")
            if connection_duration < 60:
                log_lines.append(f"    5. 连接仅存活 {connection_duration:.1f}s，可能是认证失败或服务器拒绝")
            if time_since_last_pong > 30:
                log_lines.append(f"    6. 距离上次心跳响应已 {time_since_last_pong:.1f}s，可能是心跳超时")

        log_lines.append("X" * 80)

        self._write_log("ERROR", "\n".join(log_lines))

    def log_full_reset(
        self,
        conn_id: int,
        queue_cleared: int,
        streams_cleared: int
    ):
        """记录完全重置事件"""
        log_lines = [
            "🔄" * 40,
            "FULL RESET EXECUTED",
            "🔄" * 40,
            f"  Connection ID      : {conn_id}",
            f"  Reset Time         : {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')}",
            f"  Queue Cleared      : {queue_cleared} messages discarded",
            f"  Streams Cleared    : {streams_cleared} pending requests cleared",
            f"  Connection ID Reset: Yes (will start from 1)",
            "🔄" * 40
        ]

        self._write_log("WARNING", "\n".join(log_lines))

    def log_abnormal_data(
        self,
        conn_id: int,
        data: Any,
        error: str,
        data_type: str = "unknown"
    ):
        """记录异常数据"""
        log_lines = [
            "!" * 60,
            "ABNORMAL DATA RECEIVED",
            "!" * 60,
            f"  Connection ID : {conn_id}",
            f"  Time          : {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')}",
            f"  Data Type     : {data_type}",
            f"  Error         : {error}",
            f"  Data Content  : {self._format_data(data, max_length=1000)}",
            "!" * 60
        ]

        self._write_log("ERROR", "\n".join(log_lines))

    def log_connection_established(
        self,
        conn_id: int,
        ws_url: str,
        extra_info: Optional[Dict] = None
    ):
        """记录连接建立成功"""
        log_lines = [
            "=" * 60,
            "CONNECTION ESTABLISHED",
            "=" * 60,
            f"  Connection ID : {conn_id}",
            f"  Time          : {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')}",
            f"  URL           : {ws_url[:100] if ws_url else 'N/A'}...",
        ]

        if extra_info:
            for key, value in extra_info.items():
                log_lines.append(f"  {key:14}: {value}")

        log_lines.append("=" * 60)
        self._write_log("INFO", "\n".join(log_lines))

    def log_message_received(
        self,
        conn_id: int,
        message_type: str,
        message_size: int,
        cmd: str = None,
        extra_info: Optional[Dict] = None
    ):
        """记录收到消息"""
        info_parts = [
            f"conn_id={conn_id}",
            f"type={message_type}",
            f"size={message_size}",
        ]
        if cmd:
            info_parts.append(f"cmd={cmd}")
        if extra_info:
            for key, value in extra_info.items():
                info_parts.append(f"{key}={value}")

        self._write_log("DEBUG", f"[MSG RECV] {', '.join(info_parts)}")

    def log_message_loop_exit(
        self,
        conn_id: int,
        reason: str,
        messages_received: int = 0,
        duration: float = 0
    ):
        """记录消息循环退出"""
        log_lines = [
            "~" * 60,
            "MESSAGE LOOP EXITED",
            "~" * 60,
            f"  Connection ID      : {conn_id}",
            f"  Exit Time          : {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')}",
            f"  Reason             : {reason}",
            f"  Messages Received  : {messages_received}",
            f"  Loop Duration      : {duration:.2f}s",
            "~" * 60
        ]
        self._write_log("WARNING", "\n".join(log_lines))

    def log_on_open_callback(
        self,
        conn_id: int,
        success: bool,
        error: str = None,
        handler_type: str = None
    ):
        """记录 on_open 回调状态"""
        if success:
            self._write_log(
                "INFO",
                f"[ON_OPEN] conn_id={conn_id}, status=SUCCESS, handler={handler_type or 'unknown'}"
            )
        else:
            self._write_log(
                "ERROR",
                f"[ON_OPEN] conn_id={conn_id}, status=FAILED, handler={handler_type or 'unknown'}, error={error}"
            )

    def log_health_check(
        self,
        conn_id: int,
        ws_open: bool,
        connection_state: str,
        action: str = None
    ):
        """记录健康检查结果"""
        self._write_log(
            "DEBUG",
            f"[HEALTH CHECK] conn_id={conn_id}, ws_open={ws_open}, state={connection_state}, action={action or 'none'}"
        )

    def log_system_recovery(
        self,
        conn_id: int,
        recovery_status: Dict[str, Any]
    ):
        """记录系统恢复状态"""
        log_lines = [
            "+" * 60,
            "SYSTEM RECOVERY STATUS",
            "+" * 60,
            f"  Connection ID      : {conn_id}",
            f"  Recovery Time      : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        ]

        for key, value in recovery_status.items():
            log_lines.append(f"  {key:20}: {value}")

        log_lines.append("+" * 60)

        self._write_log("INFO", "\n".join(log_lines))

    def log_message_error(
        self,
        conn_id: int,
        message: Any,
        error: str
    ):
        """记录消息处理错误"""
        self._write_log(
            "ERROR",
            f"[MESSAGE ERROR] conn_id={conn_id}, error={error}, "
            f"message={self._format_data(message, max_length=200)}"
        )

    def log_connection_superseded(
        self,
        old_conn_id: int,
        new_conn_id: int,
        location: str
    ):
        """记录连接被取代"""
        self._write_log(
            "WARNING",
            f"[CONN SUPERSEDED] old_conn={old_conn_id} superseded by new_conn={new_conn_id}, location={location}"
        )

    def log_connection_attempt(
        self,
        conn_id: int,
        ws_url: str,
        reason: str
    ):
        """记录连接尝试"""
        self._write_log(
            "INFO",
            f"[CONN ATTEMPT] conn_id={conn_id}, reason={reason}, url={ws_url[:80]}..."
        )

    def log_state_change(
        self,
        conn_id: int,
        old_state: str,
        new_state: str,
        reason: str = ""
    ):
        """记录连接状态变化"""
        self._write_log(
            "DEBUG",
            f"[STATE CHANGE] conn_id={conn_id}, {old_state} -> {new_state}, reason={reason}"
        )

    def log_helper_thread(
        self,
        conn_id: int,
        thread_name: str,
        action: str,
        success: bool = True,
        error: str = None
    ):
        """记录辅助线程操作"""
        if success:
            self._write_log(
                "DEBUG",
                f"[THREAD] conn_id={conn_id}, thread={thread_name}, action={action}"
            )
        else:
            self._write_log(
                "ERROR",
                f"[THREAD ERROR] conn_id={conn_id}, thread={thread_name}, action={action}, error={error}"
            )

    def log_stream_request(
        self,
        conn_id: int,
        request_id: str,
        action: str,
        receiver: str = "",
        extra_info: Optional[Dict] = None
    ):
        """记录流请求操作"""
        info_parts = [
            f"conn_id={conn_id}",
            f"request_id={request_id[:8]}...",
            f"action={action}",
        ]
        if receiver:
            info_parts.append(f"receiver={receiver}")
        if extra_info:
            for key, value in extra_info.items():
                info_parts.append(f"{key}={value}")

        self._write_log("DEBUG", f"[STREAM REQ] {', '.join(info_parts)}")

    def log_full_reset_detail(
        self,
        conn_id: int,
        step: str,
        detail: str
    ):
        """记录完全重置的详细步骤"""
        self._write_log(
            "INFO",
            f"[FULL RESET] conn_id={conn_id}, step={step}, detail={detail}"
        )

    def log_send_message(
        self,
        conn_id: int,
        msg_size: int,
        success: bool,
        error: str = None
    ):
        """记录消息发送"""
        if success:
            self._write_log(
                "DEBUG",
                f"[SEND] conn_id={conn_id}, size={msg_size}, status=OK"
            )
        else:
            self._write_log(
                "WARNING",
                f"[SEND FAILED] conn_id={conn_id}, size={msg_size}, error={error}"
            )

    def log_queue_operation(
        self,
        conn_id: int,
        operation: str,
        queue_size: int,
        detail: str = ""
    ):
        """记录队列操作"""
        self._write_log(
            "DEBUG",
            f"[QUEUE] conn_id={conn_id}, op={operation}, size={queue_size}, detail={detail}"
        )

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._stats_lock:
            return self._stats.copy()

    def log_stats(self):
        """记录当前统计信息"""
        stats = self.get_stats()
        log_lines = [
            "#" * 60,
            "WEBSOCKET STATISTICS",
            "#" * 60,
            f"  Total Disconnects      : {stats['disconnect_count']}",
            f"  Total Reconnect Tries  : {stats['reconnect_count']}",
            f"  Reconnect Successes    : {stats['reconnect_success_count']}",
            f"  Reconnect Failures     : {stats['reconnect_fail_count']}",
            f"  Last Disconnect Time   : {stats['last_disconnect_time'] or 'N/A'}",
            f"  Last Reconnect Time    : {stats['last_reconnect_time'] or 'N/A'}",
            f"  Last Error             : {stats['last_error'] or 'N/A'}",
            "#" * 60
        ]

        self._write_log("INFO", "\n".join(log_lines))


# 全局单例
_ws_logger: Optional[WebSocketLogger] = None
_ws_logger_lock = threading.Lock()


def get_ws_logger() -> WebSocketLogger:
    """获取 WebSocket 日志记录器单例（线程安全）"""
    global _ws_logger
    if _ws_logger is None:
        with _ws_logger_lock:
            if _ws_logger is None:
                _ws_logger = WebSocketLogger()
    return _ws_logger
