# ACP 多设备群组数据同步流程文档

## 场景说明

用户在 A 设备上使用 AID 加入了一个群组，随后在 B 设备上使用相同的 AID 登录，分析 B 设备能否获取到群消息及群信息。

## 结论

**可以获取到。** 服务端是数据的唯一真实来源（Source of Truth），B 设备使用相同 AID 登录后，通过 Pull-Based 增量同步机制，可以从服务端拉取到所有群信息和群消息。

---

## 一、前提条件：B 设备需要相同的 AID 身份

### 1.1 AID 身份组成

| 文件 | 说明 |
|------|------|
| `cert.pem` | X.509 证书 |
| `private_key.enc` | 加密私钥 |
| `csr` | 证书签名请求 |

### 1.2 B 设备获取身份的方式

| 方式 | 说明 |
|------|------|
| 共享存储 | 通过云同步/共享文件系统自动同步 `AIDs/{aid}/` 目录 |
| 手动导入 | 通过 `importAid(identity)` 手动导入身份信息 |
| 本地加载 | 通过 `loadAid(aid)` 从本地已有存储加载 |

> ⚠️ **关键点：** B 设备必须拥有与 A 设备完全相同的证书和私钥，否则无法通过服务端身份验证。

---

## 二、B 设备登录上线流程

### 步骤 1：加载 AID 身份

```
loadAid('alice.agentcp.io') → 加载 cert.pem + private_key.enc
```

### 步骤 2：获取连接配置

```
getDecryptKey(aid, seedPassword)                          → 解密私钥
getPublicKeyPem(aid)                                      → 获取公钥
signIn(aid, apUrl, privateKey, publicKeyPem, certPem)     → 获取 messageSignature
getEntryPointConfig(aid, apUrl)                           → 获取 messageServer + heartbeatServer
```

### 步骤 3：建立 WebSocket 连接

```
URL: wss://messageServer/session?agent_id={aid}&signature={sig}
```

- 服务端验证证书 + 签名
- 连接成功后状态变为 `connected`

### 步骤 4：启动 UDP 心跳

- 每 5 秒发送心跳包到 `heartbeatServer`
- 检测网络故障，触发 WebSocket 重连

---

## 三、B 设备获取群信息流程

### 步骤 1：初始化群组客户端

| 操作 | 说明 |
|------|------|
| `acp.initGroupClient()` | 初始化 ACPGroupClient |
| 计算 targetAid | 如 `group.{issuer}` |
| 创建 Session | 与群组服务建立会话 |
| 获取凭证 | 获取 `sessionId` + `identifyingCode` |
| 设置路由拦截 | 设置 Raw Message 路由拦截 |

### 步骤 2：同步群列表

```
acp.syncGroupList() → 调用 groupOps.listMyGroups(targetAid)
```

- 服务端返回该 AID 加入的所有群组列表
- 包含：`group_id`, `group_name`, `member_count` 等
- 存储到本地：`AIDs/{aid}/groups/_index.json`

> ✅ **此时 B 设备已获取到 A 设备加入的群信息**

### 步骤 3：获取群详情（可选）

- `groupOps.getGroupInfo(targetAid, groupId)` → 获取单个群详细信息
- `groupOps.getGroupMembers(targetAid, groupId)` → 获取群成员列表

---

## 四、B 设备获取群消息流程

### 步骤 1：初始化消息存储

- `acp.initGroupMessageStore()` → 初始化 GroupMessageStore
- 加载本地已有消息：`loadGroupsForAid(ownerAid)`
- 获取上次同步位置：`lastMsgId`（首次为 0）

### 步骤 2：增量拉取消息

```
acp.pullAndStoreGroupMessages(groupId)
  └─ 内部调用: groupOps.pullMessages(targetAid, groupId, lastMsgId, limit)
```

- 服务端返回 `lastMsgId` 之后的所有新消息
- 消息存储到本地：`AIDs/{aid}/groups/{groupId}/messages.jsonl`

### 步骤 3：确认已读

```
groupOps.ackMessages(targetAid, groupId, latest_msg_id)
```

- 更新游标：`saveMsgCursor(groupId, latest_msg_id)`
- 游标单调递增，不会回退

### 步骤 4：监听实时消息

- 设置事件处理器：`acp.setGroupEventHandler(handler)`
- 服务端通过 WebSocket 推送 `GroupNotify` 通知
- 通知类型：`new_message`, `new_event`, `group_invite` 等
- 收到通知后触发增量拉取

---

## 五、完整时序流程

### 5.1 A 设备操作（先行）

```
1. createAid('alice.agentcp.io')        → 生成身份（证书 + 私钥）
2. online()                              → 连接服务端
3. joinByUrl(groupUrl, inviteCode)       → 加入群组
4. sendGroupMessage()                    → 发送消息
5. 消息存储在服务端
```

### 5.2 B 设备操作（后续）

```
1. loadAid('alice.agentcp.io')           → 加载相同身份
2. online()                              → 连接服务端（相同签名）
3. initGroupClient()                     → 初始化群组客户端
4. syncGroupList()                       → 从服务端拉取群列表     ✅ 获取群信息
5. pullAndStoreGroupMessages(groupId)    → 拉取群消息             ✅ 获取群消息
6. setGroupEventHandler()                → 监听后续实时消息       ✅ 接收新消息
```

### 5.3 时序图

```
    A 设备                    服务端                    B 设备
      │                        │                        │
      │── createAid() ────────>│                        │
      │── online() ───────────>│                        │
      │── joinByUrl() ────────>│                        │
      │── sendMessage() ──────>│  (消息存储在服务端)     │
      │                        │                        │
      │                        │            loadAid() ──│
      │                        │<──────── online() ─────│
      │                        │<──── initGroupClient() │
      │                        │                        │
      │                        │<──── syncGroupList() ──│
      │                        │── 返回群列表 ─────────>│  ✅ 群信息
      │                        │                        │
      │                        │<── pullMessages() ─────│
      │                        │── 返回历史消息 ───────>│  ✅ 群消息
      │                        │                        │
      │                        │── GroupNotify 推送 ───>│  ✅ 实时消息
      │                        │                        │
```

---

## 六、数据同步机制说明

### 6.1 同步模式

| 模式 | 机制 | 说明 |
|------|------|------|
| 拉取模式（Pull-Based） | 设备主动请求 | 设备主动从服务端拉取数据，按需获取 |
| 推送通知（Push） | 服务端推送 | 服务端推送事件通知，设备收到后按需拉取详情 |

### 6.2 游标追踪

- 每个设备独立维护游标（`msg_cursor`, `event_cursor`）
- 游标存储在本地：`AIDs/{aid}/groups/.cursors.json`
- 游标单调递增，防止数据回退

```json
{
  "group-id-1": { "msg_cursor": 150, "event_cursor": 50 },
  "group-id-2": { "msg_cursor": 200, "event_cursor": 75 }
}
```

### 6.3 设备间关系

- A 和 B 设备**不直接通信**
- 服务端是唯一数据源（Source of Truth）
- 各设备独立拉取，最终一致性（Eventual Consistency）
- 无冲突解决机制（不需要，因为只读拉取）

### 6.4 本地存储结构

```
AIDs/{aid}/groups/
├── _index.json              # 群组元数据索引
├── .cursors.json            # 游标数据
└── {group_id}/
    ├── messages.jsonl       # 群消息
    └── events.jsonl         # 群事件
```

---

## 七、注意事项

| 编号 | 事项 | 说明 |
|------|------|------|
| 1 | 身份一致性 | B 设备必须使用与 A 设备完全相同的 AID 证书和私钥 |
| 2 | 首次同步延迟 | B 设备首次登录需要全量拉取群列表和历史消息，可能有延迟 |
| 3 | 消息上限 | 每个群默认最多存储 5000 条消息、2000 条事件 |
| 4 | 网络依赖 | 同步依赖网络连接，离线时只能访问本地已缓存数据 |
| 5 | 游标独立 | 两台设备的已读进度互相独立，不会同步 |
| 6 | WebSocket 重连 | 断线后自动重连（最多 5 次，指数退避） |
