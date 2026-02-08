# AgentCP UDP 心跳自动恢复修复报告

**修复日期**: 2026-01-30
**修复版本**: agentcp (python_backend)
**修复人员**: Claude Opus 4.5

---

## 一、问题描述

### 1.1 现象
- 服务器端观察到客户端没有发送心跳
- 客户端重启后恢复正常
- 心跳发送线程在异常情况下停止，且没有自动恢复机制

### 1.2 影响范围
- UDP 心跳客户端 (`heartbeat_client.py`)
- 认证客户端 (`auth_client.py`)

---

## 二、问题根因分析

### 2.1 HeartbeatClient 问题

| 问题 | 严重程度 | 描述 |
|------|---------|------|
| Socket 异常后不重建 | 🔴 严重 | `sendto()` 异常后只打印错误，不尝试重建 socket，导致心跳永久失效 |
| 401 重登录后不更新 socket | 🔴 严重 | `sign_in()` 获取新服务器信息后，UDP socket 未重建，心跳发送到错误地址 |
| 接收线程阻塞无法中断 | 🔴 严重 | `recvfrom()` 阻塞调用，socket 损坏后陷入无限异常循环 |
| `offline()` 关闭顺序错误 | 🟡 中等 | 先关 socket 再置标志位，可能导致线程访问已关闭的 socket |
| 线程没有 join() | 🟡 中等 | 未等待线程退出，可能导致资源泄漏 |
| 无心跳超时检测 | 🟡 设计缺陷 | 只发送心跳不检测响应，无法主动发现断连 |

### 2.2 AuthClient 问题

| 问题 | 严重程度 | 描述 |
|------|---------|------|
| 重试逻辑缺陷 | 🟡 中等 | `is_retry` 标志位设置后永不重置，导致后续登录尝试直接返回 |
| 递归调用未返回结果 | 🟡 中等 | `sign_in()` 递归调用未 return，结果丢失 |
| 返回值不一致 | 🟡 中等 | 失败时返回空字符串 `""`，调用方当 dict 使用会崩溃 |
| HTTP 请求无超时 | 🟡 中等 | 可能导致线程被无限阻塞 |

---

## 三、修复方案

### 3.1 HeartbeatClient 修复

#### 3.1.1 新增常量配置

```python
class HeartbeatClient:
    MAX_SEND_FAILURES = 3           # 发送失败触发重连的阈值
    MAX_RECV_FAILURES = 3           # 接收失败触发重连的阈值
    MAX_MISSED_HEARTBEATS = 3       # 心跳响应超时阈值（错过次数）
    RECONNECT_BACKOFF_MAX = 30      # 重连退避上限（秒）
    SOCKET_TIMEOUT = 1.0            # socket 超时时间（秒）
```

#### 3.1.2 新增状态变量

```python
self._socket_lock = threading.Lock()        # 保护 socket 操作
self._reconnect_lock = threading.Lock()     # 防止并发重连
self._last_reconnect_ts = 0                 # 上次重连时间戳
self._last_hb_recv = 0                      # 上次收到心跳响应的时间戳
self._send_failures = 0                     # 连续发送失败次数
self._recv_failures = 0                     # 连续接收失败次数
```

#### 3.1.3 统一 Socket 生命周期管理

新增方法：
- `_create_socket()`: 创建并绑定 UDP socket，设置超时
- `_close_socket()`: 安全关闭 socket
- `_reconnect(reason)`: 限流/退避后执行 sign_in + 重建 socket

#### 3.1.4 发送线程异常恢复

```python
def __send_heartbeat(self):
    backoff = 1
    while self.is_sending_heartbeat and self.is_running:
        try:
            # 检查心跳响应超时
            if self._last_hb_recv > 0:
                timeout_threshold = self.MAX_MISSED_HEARTBEATS * self.heartbeat_interval
                if current_time_ms - self._last_hb_recv > timeout_threshold:
                    self._reconnect("heartbeat_response_timeout")
                    continue

            # 发送心跳（使用锁保护 socket）
            with self._socket_lock:
                if self.udp_socket is not None:
                    self.udp_socket.sendto(data, (self.server_ip, self.port))

            self._send_failures = 0
            backoff = 1

        except Exception as e:
            self._send_failures += 1
            if self._send_failures >= self.MAX_SEND_FAILURES:
                self._reconnect("send_failures_threshold")
            else:
                time.sleep(backoff)
                backoff = min(backoff * 2, self.RECONNECT_BACKOFF_MAX)
```

#### 3.1.5 接收线程可中断、可恢复

```python
def _receive_messages(self):
    while self.is_running:
        try:
            # socket 设置超时，确保能定期检查 is_running
            try:
                data, addr = sock.recvfrom(1536)
            except socket.timeout:
                continue  # 超时是正常的

            self._recv_failures = 0
            self._last_hb_recv = current_time_ms  # 更新响应时间

            if hb_resp.NextBeat == 401:
                self._reconnect("401_auth_failed")  # 401 触发重连

        except Exception as e:
            self._recv_failures += 1
            if self._recv_failures >= self.MAX_RECV_FAILURES:
                self._reconnect("recv_failures_threshold")
```

#### 3.1.6 修复 offline() 关闭顺序

```python
def offline(self):
    # 1. 先设置标志位
    self.is_running = False
    self.is_sending_heartbeat = False

    # 2. 关闭 socket
    self._close_socket()

    # 3. 等待线程退出
    if self.send_thread is not None and self.send_thread.is_alive():
        self.send_thread.join(timeout=3)
    if self.receive_thread is not None and self.receive_thread.is_alive():
        self.receive_thread.join(timeout=3)
```

### 3.2 AuthClient 修复

#### 3.2.1 新增 HTTP 超时配置

```python
HTTP_TIMEOUT = (3, 10)  # (连接超时, 读取超时)
```

#### 3.2.2 重写 sign_in() 重试逻辑

```python
def sign_in(self, max_retry_num: int = 10) -> Union[dict, None]:
    """登录方法，使用循环重试，失败返回 None"""
    for retry_count in range(max_retry_num + 1):
        try:
            if retry_count > 0:
                backoff = min(2 * retry_count, 30)  # 指数退避
                time.sleep(backoff)

            response = requests.post(url, ..., timeout=self.HTTP_TIMEOUT)

            if response.status_code == 200:
                # ... 处理成功响应 ...
                return result

        except Exception as e:
            log_warning(f"Sign in exception (retry {retry_count}/{max_retry_num}): {e}")

    log_error(f"Sign in failed after {max_retry_num} retries")
    return None  # 统一返回 None，不再返回空字符串
```

#### 3.2.3 所有 HTTP 请求添加超时

- `sign_in()`: 添加 `timeout=self.HTTP_TIMEOUT`
- `sign_out()`: 添加 `timeout=self.HTTP_TIMEOUT`
- `__check_server_cert()`: 添加 `timeout=self.HTTP_TIMEOUT`

---

## 四、修改文件清单

| 文件路径 | 修改类型 | 说明 |
|---------|---------|------|
| `agentcp/heartbeat/heartbeat_client.py` | 重构 | 添加自动恢复机制 |
| `agentcp/base/auth_client.py` | 重构 | 修复重试逻辑 |

---

## 五、修复效果

### 5.1 解决的问题

| 场景 | 修复前 | 修复后 |
|------|-------|-------|
| 网络短暂中断 | ❌ 心跳永久失效 | ✅ 自动重连恢复 |
| 服务器重启(401) | ❌ 心跳发送到错误地址 | ✅ 重建 socket 恢复 |
| 长时间无响应 | ❌ 无法检测 | ✅ 超时检测触发重连 |
| 登录失败 | ❌ 一次失败后永久失败 | ✅ 循环重试直到成功 |
| 调用 offline() | ❌ 可能异常/资源泄漏 | ✅ 安全关闭 |

### 5.2 新增能力

1. **心跳响应超时检测**: 连续 3 次心跳周期无响应，自动触发重连
2. **发送/接收失败计数**: 连续 3 次失败触发重连
3. **指数退避重试**: 避免频繁重连对服务器造成压力
4. **重连限流**: 距离上次重连至少间隔 5 秒
5. **线程安全**: 使用锁保护 socket 操作

---

## 六、测试建议

### 6.1 功能测试

1. **正常心跳**: 启动后确认心跳持续发送并收到响应
2. **网络中断恢复**: 断网 30 秒后恢复，观察是否自动重连
3. **服务器重启**: 服务端重启返回 401，确认客户端自动重新登录
4. **offline/online 循环**: 重复调用，确认无资源泄漏

### 6.2 异常测试

1. **模拟 socket 异常**: 确认触发重连
2. **模拟登录失败**: 确认重试机制正常工作
3. **模拟长时间无响应**: 确认超时检测触发重连

---

## 七、回滚策略

如需回滚，可按以下步骤操作：

1. 使用 git 恢复修改前的版本：
   ```bash
   git checkout <commit-hash> -- python_backend/agentcp/heartbeat/heartbeat_client.py
   git checkout <commit-hash> -- python_backend/agentcp/base/auth_client.py
   ```

2. 或者仅回滚部分修改：
   - 保留 `AuthClient` 的 HTTP 超时修复
   - 回滚 `HeartbeatClient` 的重连逻辑

---

## 八、后续优化建议

1. **添加监控指标**: 记录重连次数、失败次数等，便于运维监控
2. **配置化参数**: 将重连阈值、超时时间等参数配置化
3. **健康检查接口**: 提供 API 查询心跳状态
4. **日志分级**: 区分 DEBUG/INFO/WARNING/ERROR 日志级别

---

*报告生成时间: 2026-01-30 08:07:15 UTC*
