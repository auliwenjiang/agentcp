# AgentCP 群组 SDK 差异对比文档

> 对比对象：
> - **当前 SDK**（C++ / Android）：`H:\project\agentcp-so`
> - **Node SDK**（TypeScript）：`H:\project\evol_main\node-ws-acp\acp-ws`

---

## 1. 整体架构差异

| 维度 | 当前 SDK (C++/Android) | Node SDK (TypeScript) |
|------|----------------------|----------------------|
| 核心语言 | C++ (core) + Java (Android) + ObjC (iOS) | TypeScript |
| 并发模型 | 多线程 (mutex + condition_variable) | 单线程事件循环 (Promise + Deferred) |
| 异步模式 | 同步阻塞 (`SendRequest` 阻塞等待响应) | async/await (`sendRequest` 返回 Promise) |
| 文件结构 | `core/include/agentcp/group_*.h` + `core/src/group/group_*.cpp` | `src/group/*.ts` (types/client/operations/events/cursor_store/message_store) |
| 高层集成 | **无** — 仅提供底层 API，无 AgentCP 主类集成 | **有** — `agentcp.ts` 中集成了完整的群组会话生命周期管理 |
| 平台存储 | Android: SQLite; C++ core: 无 MessageStore | Node: JSONL 文件持久化 + 内存缓存 |

---

## 2. 错误码 (GroupErrorCode)

| 错误码 | 当前 SDK | Node SDK | 差异 |
|--------|---------|---------|------|
| SUCCESS (0) | ✅ | ✅ | — |
| GROUP_NOT_FOUND (1001) | ✅ | ✅ | — |
| NO_PERMISSION (1002) | ✅ | ✅ | — |
| GROUP_DISSOLVED (1003) | ✅ | ✅ | — |
| GROUP_SUSPENDED (1004) | ✅ | ✅ | — |
| ALREADY_MEMBER (1005) | ✅ | ✅ | — |
| NOT_MEMBER (1006) | ✅ | ✅ | — |
| BANNED (1007) | ✅ | ✅ | — |
| MEMBER_FULL (1008) | ✅ | ✅ | — |
| INVALID_PARAMS (1009) | ✅ | ✅ | — |
| RATE_LIMITED (1010) | ✅ | ✅ | — |
| INVITE_CODE_INVALID (1011) | ✅ | ✅ | — |
| REQUEST_EXISTS (1012) | ✅ | ✅ | — |
| BROADCAST_CONFLICT (1013) | ✅ | ✅ | — |
| **DUTY_NOT_ENABLED (1020)** | ❌ | ✅ | **Node 独有** |
| **NOT_DUTY_AGENT (1021)** | ❌ | ✅ | **Node 独有** |
| **AGENT_MD_NOT_FOUND (1024)** | ❌ | ✅ | **Node 独有** |
| **AGENT_MD_INVALID (1025)** | ❌ | ✅ | **Node 独有** |
| ACTION_NOT_IMPL (1099) | ✅ | ✅ | — |

**结论**：当前 SDK 缺少 4 个值班 (Duty) 相关错误码。

---

## 3. 通知事件常量 (Notify Events)

| 常量 | 当前 SDK | Node SDK | 差异 |
|------|---------|---------|------|
| NOTIFY_NEW_MESSAGE | ✅ | ✅ | — |
| NOTIFY_NEW_EVENT | ✅ | ✅ | — |
| NOTIFY_GROUP_INVITE | ✅ | ✅ | — |
| NOTIFY_JOIN_APPROVED | ✅ | ✅ | — |
| NOTIFY_JOIN_REJECTED | ✅ | ✅ | — |
| NOTIFY_JOIN_REQUEST_RECEIVED | ✅ | ✅ | — |
| NOTIFY_GROUP_EVENT | ✅ | ✅ | — |
| **NOTIFY_GROUP_MESSAGE** | ❌ | ✅ | **Node 独有** — 用于单条消息推送 (`message_push` → `group_message`) |
| ACTION_MESSAGE_BATCH_PUSH | ✅ | ✅ | — |

**结论**：当前 SDK 缺少 `NOTIFY_GROUP_MESSAGE` 常量。Node SDK 在 `handleIncoming` 中将 `message_push` action 转换为 `NOTIFY_GROUP_MESSAGE` 通知事件，当前 SDK 不支持此转换。

---

## 4. ACPGroupEventHandler 回调接口

| 回调方法 | 当前 SDK | Node SDK | 差异 |
|---------|---------|---------|------|
| OnNewMessage | ✅ | ✅ | — |
| OnNewEvent | ✅ | ✅ | — |
| OnGroupInvite | ✅ | ✅ | — |
| OnJoinApproved | ✅ | ✅ | — |
| OnJoinRejected | ✅ | ✅ | — |
| OnJoinRequestReceived | ✅ | ✅ | — |
| OnGroupMessageBatch | ✅ | ✅ | — |
| OnGroupEvent | ✅ | ✅ | — |
| **onGroupMessage** (单条消息推送) | ❌ | ✅ (optional) | **Node 独有** — 配合 `NOTIFY_GROUP_MESSAGE` 使用 |

**结论**：当前 SDK 缺少 `onGroupMessage` 可选回调（单条消息实时推送处理）。

---

## 5. GroupClient (请求/响应传输层)

### 5.1 并发模型差异

| 特性 | 当前 SDK | Node SDK |
|------|---------|---------|
| 请求等待机制 | `condition_variable` + `mutex` 阻塞等待 | `Promise` + `setTimeout` 异步等待 |
| 线程安全 | `std::atomic` + `std::mutex` 保护 | 无需锁（JS 单线程） |
| 超时处理 | `cv.wait_for()` 超时 | `setTimeout` 定时器 |
| 取消机制 | `cancelled` 标志 + `cv.notify_all()` | `clearTimeout` + `reject` |
| handler 存储 | `std::atomic<ACPGroupEventHandler*>` | 普通成员变量 |

### 5.2 HandleIncoming 消息路由差异

| 消息类型 | 当前 SDK | Node SDK |
|---------|---------|---------|
| 响应 (有 request_id) | ✅ 路由到 pending request | ✅ 路由到 pending request |
| 响应同时携带 event 字段 | ✅ 额外 dispatch 通知 | ✅ 额外 dispatch 通知 |
| 通知 (有 event 字段) | ✅ dispatch 到 handler | ✅ dispatch 到 handler |
| **`message_push` action** | ❌ **不支持** | ✅ 转换为 `NOTIFY_GROUP_MESSAGE` 通知 |
| `message_batch_push` action | ✅ 解析并调用 `OnGroupMessageBatch` | ✅ 解析并调用 `onGroupMessageBatch` |

**关键差异**：当前 SDK 的 `HandleIncoming` 不处理 `message_push` 类型的单条消息推送，只处理 `message_batch_push`。Node SDK 两者都处理。

### 5.3 Close 行为差异

| 行为 | 当前 SDK | Node SDK |
|------|---------|---------|
| 取消 pending requests | ✅ 设置 cancelled + notify_all | ✅ clearTimeout + reject |
| 关闭 cursor store | ❌ 不在 Close 中处理 | ✅ 调用 `cursorStore.close()` |

---

## 6. GroupOperations (操作层)

### 6.1 Phase 0-5 操作对比

所有 Phase 0-5 的操作在两个 SDK 中**完全一致**：

- Phase 0: `registerOnline`, `unregisterOnline`, `heartbeat`
- Phase 1: `createGroup`, `addMember`, `sendGroupMessage`, `pullMessages`, `ackMessages`, `pullEvents`, `ackEvents`, `getCursor`, `syncGroup`
- Phase 2: `removeMember`, `leaveGroup`, `dissolveGroup`, `banAgent`, `unbanAgent`, `getBanlist`, `requestJoin`, `reviewJoinRequest`, `batchReviewJoinRequests`, `getPendingRequests`
- Phase 3: `getGroupInfo`, `updateGroupMeta`, `getMembers`, `getAdmins`, `getRules`, `updateRules`, `getAnnouncement`, `updateAnnouncement`, `getJoinRequirements`, `updateJoinRequirements`, `suspendGroup`, `resumeGroup`, `transferMaster`, `getMaster`, `createInviteCode`, `useInviteCode`, `listInviteCodes`, `revokeInviteCode`, `acquireBroadcastLock`, `releaseBroadcastLock`, `checkBroadcastPermission`
- Phase 4: `getSyncStatus`, `getSyncLog`, `getChecksum`, `getMessageChecksum`, `getPublicInfo`, `searchGroups`, `generateDigest`, `getDigest`
- Phase 5: `listMyGroups`, `unregisterMembership`, `changeMemberRole`, `getFile`, `getSummary`, `getMetrics`

### 6.2 Node SDK 独有操作

| 操作 | 说明 | 当前 SDK |
|------|------|---------|
| **`updateDutyConfig`** | 更新值班配置 (mode/rotation_strategy/shift_duration 等) | ❌ 缺失 |
| **`setFixedAgents`** | 快捷设置固定值班 Agent 列表 | ❌ 缺失 |
| **`getDutyStatus`** | 获取值班状态 (config + state) | ❌ 缺失 |
| **`refreshMemberTypes`** | 重新获取所有成员 agent.md 并更新 AgentType | ❌ 缺失 |

### 6.3 工具方法差异

| 方法 | 当前 SDK | Node SDK | 差异 |
|------|---------|---------|------|
| `parseGroupUrl` | ✅ 静态方法 | ✅ 静态方法 | — |
| `joinByUrl` | ✅ 返回 `string` (request_id) | ✅ 返回 `RequestJoinResp` (status + request_id) | **返回类型不同** |

**`joinByUrl` 详细差异**：
- 当前 SDK：返回 `std::string`（request_id），无法区分"直接加入"和"等待审核"
- Node SDK：返回 `RequestJoinResp { status, request_id }`，`status="joined"` 表示直接加入，`status="pending"` 表示等待审核

### 6.4 RequestJoin 返回类型差异

| SDK | 返回类型 | 说明 |
|-----|---------|------|
| 当前 SDK | `std::string` (request_id) | 仅返回 request_id |
| Node SDK | `RequestJoinResp { status, request_id }` | 同时返回状态和 request_id |

**结论**：当前 SDK 缺少 `RequestJoinResp` 类型定义。

### 6.5 ackMessages/ackEvents 中的 CursorStore 联动

| 行为 | 当前 SDK | Node SDK |
|------|---------|---------|
| ack 后自动更新本地 cursor | ❌ 不在 operations 层处理 | ✅ `ackMessages`/`ackEvents` 内自动调用 `cursorStore.save*Cursor()` |

---

## 7. 类型定义差异

### 7.1 Node SDK 独有类型

| 类型 | 说明 |
|------|------|
| `RequestJoinResp` | `{ status: string; request_id: string }` — requestJoin 的返回类型 |
| `DutyConfig` | 值班配置：mode, rotation_strategy, shift_duration_ms 等 |
| `DutyState` | 值班状态：current_duty_agent, shift_start_time 等 |
| `DutyStatusResp` | `{ config: DutyConfig; state: DutyState }` |

### 7.2 Wire Protocol 参数传递差异

| 特性 | 当前 SDK | Node SDK |
|------|---------|---------|
| GroupRequest.params | `params_flat` (map) + `params_json` (raw JSON string) | `params?: Record<string, any>` (原生对象) |
| GroupResponse.data | `data_json` (raw JSON string) | `data?: any` (原生对象) |
| GroupNotify.data | `data_json` (raw JSON string) | `data?: any` (原生对象) |
| GroupMessage.metadata | `metadata_json` (string) | `metadata?: Record<string, any>` (原生对象) |
| GroupEvent.data | `data_json` (string) | `data?: Record<string, any>` (原生对象) |

**说明**：这是语言特性导致的合理差异。C++ 无法直接表示动态 JSON 对象，使用 raw JSON string 是标准做法。

### 7.3 PullMessagesResp 差异

| 字段 | 当前 SDK | Node SDK |
|------|---------|---------|
| messages | `std::vector<GroupMessage>` (强类型) | `Record<string, any>[]` (弱类型) |

Node SDK 的 `PullMessagesResp.messages` 使用 `Record<string, any>[]` 而非 `GroupMessage[]`，这是一个类型安全性的差异。

---

## 8. 高层集成 (AgentCP 主类)

这是**最大的架构差异**。Node SDK 在 `agentcp.ts` 中提供了完整的群组会话生命周期管理，当前 SDK 完全没有对应实现。

### 8.1 Node SDK 独有的高层功能

#### 8.1.1 群组客户端初始化

```typescript
// Node SDK 提供两种初始化方式
initGroupClient(sendRaw, sessionId, targetAid?)     // 默认 group.{issuer}
initGroupClientCrossAp(sendRaw, sessionId, targetAid) // 跨 AP 自定义 targetAid
```

当前 SDK：仅提供底层 `ACPGroupClient` 构造函数，无自动 targetAid 推导。

#### 8.1.2 群组会话生命周期

```typescript
// Node SDK 完整的会话管理
joinGroupSession(groupId)    // register_online + 冷启动拉取 + 启动心跳
leaveGroupSession(groupId)   // 从在线列表移除，无群在线时 unregister_online
leaveAllGroupSessions()      // 优雅退出所有群组
getOnlineGroups()            // 获取当前在线群组列表
```

当前 SDK：**完全缺失**。需要调用方自行管理 registerOnline/unregisterOnline/heartbeat 的调用时机。

#### 8.1.3 心跳管理

```typescript
// Node SDK 自动心跳
_heartbeatTimer              // setInterval 定时器
_heartbeatIntervalMs = 180_000  // 默认 3 分钟
_startHeartbeat()            // 自动启动
_stopHeartbeat()             // 自动停止
_sendHeartbeat()             // 发送心跳
```

当前 SDK：**完全缺失**。调用方需自行实现心跳定时器。

#### 8.1.4 消息存储集成

```typescript
// Node SDK 自动消息存储
initGroupMessageStore(options?)          // 初始化 JSONL 存储
syncGroupList()                          // 从服务端同步群组列表到本地
getLocalGroupList()                      // 获取本地群组列表
addGroupToStore(groupId, name)           // 添加群组到本地
removeGroupFromStore(groupId)            // 从本地移除群组
getLocalGroupMessages(groupId, limit?)   // 获取本地消息
addGroupMessageToStore(groupId, msg)     // 添加单条消息
addGroupMessagesToStore(groupId, msgs)   // 批量添加消息
getGroupLastMsgId(groupId)              // 获取最后消息 ID
pullAndStoreGroupMessages(groupId, ...)  // 拉取并存储消息
```

当前 SDK (C++ core)：**完全缺失**。仅 Android 端有独立的 SQLite `GroupMessageStore`。

#### 8.1.5 默认事件处理器

```typescript
// Node SDK 自动创建默认事件处理器
_createDefaultGroupEventHandler() {
    // 自动存储收到的消息
    // 自动处理 join_approved 事件（获取群信息 + 加入本地存储）
    // 自动处理 message_batch_push（processAndAckBatch）
}
```

当前 SDK：**完全缺失**。调用方需自行实现所有事件处理逻辑。

#### 8.1.6 批量消息处理与确认

```typescript
// Node SDK 提供 processAndAckBatch
async processAndAckBatch(groupId, batch): Promise<GroupMessage[]> {
    // 排序 → 存储 → ACK → 返回消息列表
}
```

当前 SDK：**完全缺失**。

---

## 9. 消息存储层差异

### 9.1 C++ Core

**无群组消息存储实现**。`core/` 目录下没有任何 MessageStore 相关代码。

### 9.2 Android (Java)

| 特性 | Android SDK | Node SDK |
|------|------------|---------|
| 存储引擎 | SQLite | JSONL 文件 |
| 数据模型 | `GroupChatMessage` + `GroupConversation` | `GroupMessage` + `GroupRecord` |
| 去重机制 | `PRIMARY KEY (group_id, msg_id)` + `CONFLICT_IGNORE` | `msg_id <= lastMsgId` 跳过 |
| 未读计数 | ✅ `unread_count` 字段 + `markGroupRead()` | ❌ 无未读计数 |
| 事件存储 | ❌ 不存储事件 | ✅ 存储 GroupEvent (events.jsonl) |
| 消息上限 | 无限制 (SQLite) | 可配置 `maxMessagesPerGroup=5000`, `maxEventsPerGroup=2000` |
| 删除群组 | ✅ 事务删除 (messages + conversations) | ✅ 删除目录 |
| 查询能力 | 丰富 (SQL: afterMsgId, limit, offset, 倒序) | 基础 (内存过滤: afterMsgId, beforeMsgId, limit) |
| 批量写入 | ✅ 事务批量插入 | ✅ 全量重写 JSONL |

### 9.3 Android 独有功能

| 功能 | 说明 |
|------|------|
| `markGroupRead(groupId)` | 重置未读计数 |
| `unreadCount` 字段 | 自动维护未读消息数 |
| `getMessagesAfter(groupId, afterMsgId, limit)` | 增量拉取查询 |
| `StorageConfig` 多模式 | INTERNAL / EXTERNAL / CUSTOM 存储路径 |

### 9.4 Node SDK 独有功能

| 功能 | 说明 |
|------|------|
| 事件存储 (`events.jsonl`) | 持久化 GroupEvent |
| `addEvents()` / `getEvents()` | 事件 CRUD |
| `getLatestMessages(groupId, limit)` | 获取最新 N 条消息 |
| `loadGroupsForAid(ownerAid)` | 按 AID 加载所有群组 |
| 消息/事件上限截断 | 超过上限自动删除旧数据 |

---

## 10. CursorStore 差异

两个 SDK 的 CursorStore 实现**基本一致**，差异很小：

| 特性 | 当前 SDK | Node SDK |
|------|---------|---------|
| 接口 | 抽象类 (`virtual`) | TypeScript `interface` |
| 线程安全 | `std::mutex` 保护 | 无需（单线程） |
| 持久化 | JSON 文件 | JSON 文件 (Node) / 纯内存 (Browser) |
| 单调递增 | ✅ 只允许 cursor 前进 | ✅ 只允许 cursor 前进 |
| 脏标记优化 | ✅ `dirty_` flag | ✅ `_dirty` flag |
| 浏览器兼容 | N/A | ✅ `isNodeEnvironment` 检测 |

---

## 11. EventProcessor 差异

两个 SDK 的 `EventProcessor` 接口和 `dispatchEvent` 实现**完全一致**，支持相同的 15 种事件类型。无差异。

---

## 12. 总结：当前 SDK 需要补齐的功能

### 12.1 已完成对齐 ✅

| 功能 | 状态 |
|------|------|
| 值班 (Duty) 错误码 (1020/1021/1024/1025) | ✅ 已添加 |
| 值班类型 (DutyConfig/DutyState/DutyStatusResp) | ✅ 已添加 |
| 值班操作 (UpdateDutyConfig/SetFixedAgents/GetDutyStatus/RefreshMemberTypes) | ✅ 已添加 |
| `NOTIFY_GROUP_MESSAGE` 常量 | ✅ 已添加 |
| `OnGroupMessage` 可选回调 | ✅ 已添加 (默认空实现，不破坏现有代码) |
| `message_push` 处理 (HandleIncoming) | ✅ 已添加 |
| `RequestJoinResp` 类型 | ✅ 已添加 |
| `RequestJoin` 返回 RequestJoinResp | ✅ 已更新 |
| `JoinByUrl` 返回 RequestJoinResp | ✅ 已更新 |

### 12.2 建议后续补齐（架构增强，非协议对齐）

| 优先级 | 功能 | 说明 |
|--------|------|------|
| P1 | **C++ Core GroupMessageStore** | 参考 Node SDK 的 JSONL 存储或 Android 的 SQLite，为 C++ core 提供消息持久化 |
| P2 | **高层会话管理** | 参考 Node SDK 的 `joinGroupSession`/`leaveGroupSession`/心跳管理，封装生命周期 |
| P2 | **默认事件处理器** | 参考 Node SDK 的 `_createDefaultGroupEventHandler`，提供开箱即用的消息自动存储 |
| P2 | **`processAndAckBatch`** | 批量消息排序 → 存储 → ACK 的便捷方法 |
| P3 | **`Close` 时关闭 CursorStore** | 当前 SDK 的 `ACPGroupClient::Close()` 不关闭 CursorStore |

### 12.3 无需修改（合理差异）

- Wire Protocol 中使用 `string` vs 原生对象：语言特性差异，合理
- 并发模型 (mutex vs Promise)：语言特性差异，合理
- Android SQLite vs Node JSONL：平台特性差异，合理
