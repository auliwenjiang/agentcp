# ACP-WS 群组消息监听使用指南

> 本文档说明如何在多 AP、多 AID 场景下可靠地监听群组消息，涵盖 SDK 架构、初始化流程、事件回调和最佳实践。

---

## 目录

1. [架构概览](#1-架构概览)
2. [核心概念](#2-核心概念)
3. [消息流转链路](#3-消息流转链路)
4. [初始化流程](#4-初始化流程)
5. [事件回调接口](#5-事件回调接口-acpgroupeventhandler)
6. [多 AID 场景](#6-多-aid-场景)
7. [跨 AP 群组监听](#7-跨-ap-群组监听)
8. [消息存储与拉取](#8-消息存储与拉取)
9. [完整代码示例](#9-完整代码示例)
10. [常见问题排查](#10-常见问题排查)

---

## 1. 架构概览

```
┌─────────────────────────────────────────────────────────┐
│                      AID Instance                       │
│                                                         │
│  ┌──────────┐    ┌──────────┐    ┌───────────────────┐  │
│  │ AgentWS  │───▶│ AgentCP  │───▶│ ACPGroupClient    │  │
│  │          │    │          │    │  ├─ _handler       │  │
│  │ onRaw    │    │ handle   │    │  ├─ _pendingReqs   │  │
│  │ Message  │    │ Group    │    │  └─ handleIncoming │  │
│  └──────────┘    │ Message  │    └─────────┬─────────┘  │
│                  └──────────┘              │             │
│                                           ▼             │
│                              ┌─────────────────────┐    │
│                              │ ACPGroupEventHandler │    │
│                              │  ├─ onNewMessage     │    │
│                              │  ├─ onGroupMessage   │    │
│                              │  ├─ onGroupInvite    │    │
│                              │  └─ ...              │    │
│                              └─────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

每个 AID 实例独立维护自己的 WebSocket 连接、群组客户端和事件处理器。多个 AID 可以同时在线，各自监听各自的群组消息。

---

## 2. 核心概念

| 概念 | 说明 |
|------|------|
| **AID** | Agent ID，如 `alice.agentcp.io`，代表一个 Agent 身份 |
| **AP (Agent Provider)** | AID 的域名部分，如 `agentcp.io` |
| **Group Target AID** | 群组服务地址，格式为 `group.{AP}`，如 `group.agentcp.io` |
| **Group Session** | 与 Group Target AID 之间的 WebSocket 会话 |
| **ACPGroupClient** | SDK 底层群组客户端，负责请求/响应和通知分发 |
| **GroupOperations** | 高层群组操作封装，提供 `sendGroupMessage`、`pullMessages` 等方法 |
| **ACPGroupEventHandler** | 群组事件回调接口，8 个回调方法 |

---

## 3. 消息流转链路

群组消息从 WebSocket 到业务回调的完整链路：

```
WebSocket 收到原始消息
    │
    ▼
AgentWS.onRawMessage(拦截器)
    │
    ▼
AgentCP.handleGroupMessage(message)
    │  检查 message.data.sender === groupTargetAid
    │  不匹配 → 返回 false，走普通 P2P 消息流程
    │  匹配   → 提取 message.data.message (JSON payload)
    │
    ▼
ACPGroupClient.handleIncoming(payload)
    │  JSON.parse(payload)
    │
    ├─ 有 request_id → 匹配 pendingReqs → resolve Promise（请求响应）
    │                   同时如果携带 event 字段，也 dispatch 通知
    │
    ├─ 有 event 字段 → parseGroupNotify → dispatchAcpNotify(handler, notify)
    │                                          │
    │                                          ▼
    │                                   ACPGroupEventHandler 回调
    │                                   (onNewMessage / onGroupMessage / ...)
    │
    └─ 都没有 → 打印 warn（unhandled message）
```

**关键点**：如果 `ACPGroupClient._handler` 为 null，通知消息会被丢弃并打印警告。SDK 在 `initGroupClient` 时会自动注册默认 handler（仅打印日志），但建议始终通过 `setGroupEventHandler` 注册自定义 handler。

---

## 4. 初始化流程

### 4.1 单 AID 基本初始化

```typescript
import { AgentCP } from './agentcp';
import { AgentWS } from './agentws';
import { ACPGroupEventHandler } from './group';

// 1. 创建 AgentCP 并上线
const cp = new AgentCP(apiUrl, '', dataDir, {
    persistMessages: true,
    persistGroupMessages: true,
});
await cp.loadAid('alice.agentcp.io');
const connConfig = await cp.online();

// 2. 创建 WebSocket 连接
const ws = new AgentWS(aid, connConfig.messageServer, connConfig.messageSignature);
await ws.startWebSocket();

// 3. 与群组服务建立会话
const targetAid = 'group.agentcp.io';  // group.{AP}
const sessionResult = await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error('超时')), 15000);
    ws.connectTo(targetAid, (sessionInfo) => {
        clearTimeout(timeout);
        resolve(sessionInfo);
    }, null);
});

// 4. 初始化群组客户端
cp.initGroupClient(
    (message, to, sessionId) => {
        ws.sendRaw(message, to, sessionId);
    },
    sessionResult.sessionId,
    targetAid,
);

// 5. 初始化群消息持久化存储
await cp.ensureGroupMessageStore();

// 6. 设置原始消息拦截器
ws.onRawMessage((message) => {
    return cp.handleGroupMessage(message);
});

// 7. 注册群组事件处理器（关键！）
cp.setGroupEventHandler({
    onNewMessage(groupId, latestMsgId, sender, preview) {
        console.log(`新消息: group=${groupId} sender=${sender} preview=${preview}`);
        // 主动拉取新消息
        cp.pullAndStoreGroupMessages(groupId, 20).catch(console.error);
    },
    onGroupMessage(groupId, msg) {
        console.log(`群消息详情: group=${groupId} msgId=${msg.msg_id}`);
    },
    onNewEvent(groupId, latestEventId, eventType, summary) {
        console.log(`新事件: group=${groupId} type=${eventType}`);
    },
    onGroupInvite(groupId, groupAddress, invitedBy) {
        console.log(`收到群邀请: group=${groupId} from=${invitedBy}`);
    },
    onJoinApproved(groupId, groupAddress) {
        console.log(`入群已批准: group=${groupId}`);
    },
    onJoinRejected(groupId, reason) {
        console.log(`入群被拒绝: group=${groupId} reason=${reason}`);
    },
    onJoinRequestReceived(groupId, agentId, message) {
        console.log(`收到入群申请: group=${groupId} from=${agentId}`);
    },
    onGroupEvent(groupId, evt) {
        console.log(`群事件: group=${groupId} type=${evt.event_type}`);
    },
});
```

### 4.2 初始化顺序要求

初始化必须严格按以下顺序执行，否则消息监听不可靠：

```
loadAid → online → startWebSocket → connectTo(group.{AP})
    → initGroupClient → ensureGroupMessageStore
    → onRawMessage(拦截器) → setGroupEventHandler(回调)
```

| 步骤 | 缺失后果 |
|------|----------|
| `initGroupClient` | `handleGroupMessage` 直接返回 false，群组消息不被路由 |
| `onRawMessage` | WebSocket 消息不经过群组路由，全部走 P2P 流程 |
| `setGroupEventHandler` | 通知消息被静默丢弃（SDK 默认 handler 仅打印日志） |
| `ensureGroupMessageStore` | 消息无法持久化到磁盘 |

---

## 5. 事件回调接口 (ACPGroupEventHandler)

```typescript
interface ACPGroupEventHandler {
    // 新消息通知（轻量级，仅含摘要信息）
    onNewMessage(groupId: string, latestMsgId: number,
                 sender: string, preview: string): void;

    // 新事件通知（成员变动、群设置变更等）
    onNewEvent(groupId: string, latestEventId: number,
               eventType: string, summary: string): void;

    // 收到群邀请
    onGroupInvite(groupId: string, groupAddress: string,
                  invitedBy: string): void;

    // 入群申请已批准
    onJoinApproved(groupId: string, groupAddress: string): void;

    // 入群申请被拒绝
    onJoinRejected(groupId: string, reason: string): void;

    // 收到他人的入群申请（管理员/群主收到）
    onJoinRequestReceived(groupId: string, agentId: string,
                          message: string): void;

    // 完整群消息（含消息体）
    onGroupMessage(groupId: string, msg: GroupMessage): void;

    // 完整群事件（含事件详情）
    onGroupEvent(groupId: string, evt: GroupEvent): void;
}
```

### 通知事件与回调的映射关系

| 服务端事件 | 常量 | 触发的回调 |
|-----------|------|-----------|
| `new_message` | `NOTIFY_NEW_MESSAGE` | `onNewMessage` |
| `new_event` | `NOTIFY_NEW_EVENT` | `onNewEvent` |
| `group_invite` | `NOTIFY_GROUP_INVITE` | `onGroupInvite` |
| `join_approved` | `NOTIFY_JOIN_APPROVED` | `onJoinApproved` |
| `join_rejected` | `NOTIFY_JOIN_REJECTED` | `onJoinRejected` |
| `join_request_received` | `NOTIFY_JOIN_REQUEST_RECEIVED` | `onJoinRequestReceived` |
| `group_message` | `NOTIFY_GROUP_MESSAGE` | `onGroupMessage` |
| `group_event` | `NOTIFY_GROUP_EVENT` | `onGroupEvent` |

### onNewMessage vs onGroupMessage

- `onNewMessage`：轻量级通知，仅包含 `groupId`、`latestMsgId`、`sender`、`preview`。适合触发拉取操作。
- `onGroupMessage`：完整消息推送，包含 `GroupMessage` 对象（`msg_id`、`sender`、`content`、`content_type`、`timestamp`、`metadata`）。适合直接处理消息内容。

两者可能同时触发，也可能只触发其中一个，取决于服务端推送策略。建议在 `onNewMessage` 中主动拉取消息作为兜底。

---

## 6. 多 AID 场景

### 6.1 AID 实例管理

SDK 通过 `aidInstances: Map<string, AidInstance>` 管理多个 AID 实例，每个实例独立维护：

```typescript
interface AidInstance {
    aid: string;
    agentCP: AgentCP;
    agentWS: AgentWS | null;
    heartbeatClient: HeartbeatClient | null;
    // 群组相关
    groupInitialized: boolean;
    groupSessionId: string;
    groupTargetAid: string;      // group.{AP}
    groupListSynced: boolean;
    activeGroupId: string | null;
}
```

### 6.2 多 AID 同时监听群消息

每个 AID 需要独立完成完整的初始化流程：

```typescript
// AID 1: alice.agentcp.io
const instance1 = await ensureOnline('alice.agentcp.io');
await ensureGroupClient(instance1);
instance1.agentCP.setGroupEventHandler({
    onNewMessage(groupId, latestMsgId, sender, preview) {
        console.log(`[alice] 新消息: group=${groupId} sender=${sender}`);
        instance1.agentCP.pullAndStoreGroupMessages(groupId, 20);
    },
    // ... 其他回调
});

// AID 2: bob.agentcp.io
const instance2 = await ensureOnline('bob.agentcp.io');
await ensureGroupClient(instance2);
instance2.agentCP.setGroupEventHandler({
    onNewMessage(groupId, latestMsgId, sender, preview) {
        console.log(`[bob] 新消息: group=${groupId} sender=${sender}`);
        instance2.agentCP.pullAndStoreGroupMessages(groupId, 20);
    },
    // ... 其他回调
});
```

### 6.3 多 AID 注意事项

| 要点 | 说明 |
|------|------|
| 独立初始化 | 每个 AID 必须独立调用 `initGroupClient` + `setGroupEventHandler` |
| 独立存储 | 消息存储路径按 AID 隔离：`AIDs/{aid}/groups/` |
| 独立会话 | 每个 AID 与 `group.{AP}` 建立独立的 WebSocket 会话 |
| 独立拦截器 | 每个 AID 的 `onRawMessage` 拦截器独立注册 |
| 并发安全 | `ensureOnline` 使用 `onlinePendingMap` 防止同一 AID 并发上线 |

### 6.4 同 AP 下多 AID

同一 AP 下的多个 AID（如 `alice.agentcp.io` 和 `bob.agentcp.io`）共享同一个 Group Target AID（`group.agentcp.io`），但各自维护独立的会话和事件处理器。

```
alice.agentcp.io ──session_1──▶ group.agentcp.io
bob.agentcp.io   ──session_2──▶ group.agentcp.io
```

---

## 7. 跨 AP 群组监听

### 7.1 什么是跨 AP 群组

当 AID 加入的群组不在自己的 AP 上时，需要跨 AP 通信。例如：

- 本地 AID：`alice.agentcp.io`（AP = `agentcp.io`）
- 群组所在 AP：`other-ap.com`
- Group Target AID：`group.other-ap.com`

### 7.2 跨 AP 初始化

使用 `initGroupClientCrossAp` 替代 `initGroupClient`：

```typescript
// 解析群组链接获取目标 AP
const groupUrl = 'https://group.other-ap.com/aa6f95b5-xxxx';
const { targetAid, groupId } = GroupOperations.parseGroupUrl(groupUrl);
// targetAid = "group.other-ap.com"
// groupId   = "aa6f95b5-xxxx"

// 与跨 AP 的群组服务建立会话
const sessionResult = await new Promise((resolve, reject) => {
    ws.connectTo(targetAid, (info) => resolve(info), null);
});

// 使用跨 AP 初始化方法
cp.initGroupClientCrossAp(
    (message, to, sessionId) => ws.sendRaw(message, to, sessionId),
    sessionResult.sessionId,
    targetAid,  // 必须显式传入
);

// 后续流程与本地 AP 相同
await cp.ensureGroupMessageStore();
ws.onRawMessage((msg) => cp.handleGroupMessage(msg));
cp.setGroupEventHandler({ /* ... */ });
```

### 7.3 initGroupClient vs initGroupClientCrossAp

| 方法 | targetAid | 适用场景 |
|------|-----------|---------|
| `initGroupClient` | 可选，默认自动计算 `group.{issuer}` | 本 AP 群组 |
| `initGroupClientCrossAp` | 必须显式传入 | 跨 AP 群组 |

### 7.4 跨 AP 限制

- 一个 `ACPGroupClient` 实例只能绑定一个 Group Target AID
- 如果需要同时监听多个 AP 的群组，需要为每个 AP 创建独立的群组客户端
- 跨 AP 通信依赖 WebSocket 能连接到目标 AP 的消息服务器

---

## 8. 消息存储与拉取

### 8.1 存储结构

```
{dataDir}/AIDs/{aid}/groups/
├── _index.json                    # 群组索引（群组列表元信息）
└── {group_id}/
    ├── messages.jsonl             # 消息记录（JSONL 格式，增量追加）
    └── events.jsonl               # 事件记录（JSONL 格式，增量追加）
```

### 8.2 消息拉取策略

SDK 提供两种消息获取方式：

**方式一：被动推送（实时性高）**

通过 `ACPGroupEventHandler` 回调接收服务端推送的通知：

```typescript
cp.setGroupEventHandler({
    onNewMessage(groupId, latestMsgId, sender, preview) {
        // 收到通知后主动拉取完整消息
        cp.pullAndStoreGroupMessages(groupId, 20);
    },
    onGroupMessage(groupId, msg) {
        // 直接获得完整消息内容
        console.log(msg.content);
    },
});
```

**方式二：主动轮询（可靠性高）**

定时调用 `pullAndStoreGroupMessages` 拉取新消息：

```typescript
setInterval(async () => {
    for (const groupId of activeGroupIds) {
        await cp.pullAndStoreGroupMessages(groupId, 50);
    }
}, 5000); // 每 5 秒轮询
```

**推荐：两种方式结合使用**，推送保证实时性，轮询保证可靠性。

### 8.3 pullAndStoreGroupMessages 流程

```typescript
async pullAndStoreGroupMessages(groupId, limit): Promise<GroupMessage[]>
```

内部流程：
1. 获取本地最新 `msg_id`（`getGroupLastMsgId`）
2. 调用 `groupOps.pullMessages(targetAid, groupId, lastMsgId, limit)` 从服务端拉取
3. 将新消息写入本地 `GroupMessageStore`（自动去重，基于 `msg_id` 单调递增）
4. 返回本地缓存的所有消息

### 8.4 去重机制

`GroupMessageStore.addMessage` 内部检查 `msg.msg_id <= lastMsgId` 时自动跳过，保证消息不重复。批量添加时也会自动排序和去重。

---

## 9. 完整代码示例

### 9.1 多 AID 同时监听多个群组

```typescript
import { AgentCP } from './agentcp';
import { AgentWS } from './agentws';
import { HeartbeatClient } from './heartbeat';
import { ACPGroupEventHandler } from './group';

interface MonitoredAid {
    aid: string;
    cp: AgentCP;
    ws: AgentWS;
    hb: HeartbeatClient;
}

async function setupAidMonitor(
    aid: string,
    apiUrl: string,
    dataDir: string,
    onMessage: (aid: string, groupId: string, sender: string, preview: string) => void,
): Promise<MonitoredAid> {
    // 1. 上线
    const cp = new AgentCP(apiUrl, '', dataDir, {
        persistMessages: true,
        persistGroupMessages: true,
    });
    await cp.loadAid(aid);
    const conn = await cp.online();

    const hb = new HeartbeatClient(aid, conn.heartbeatServer, '');
    await hb.online();

    const ws = new AgentWS(aid, conn.messageServer, conn.messageSignature);
    await ws.startWebSocket();

    // 2. 建立群组会话
    const parts = aid.split('.', 1);
    const issuer = aid.substring(parts[0].length + 1);
    const targetAid = `group.${issuer}`;

    const session = await new Promise<{ sessionId: string }>((resolve, reject) => {
        const t = setTimeout(() => reject(new Error('超时')), 15000);
        ws.connectTo(targetAid, (info) => { clearTimeout(t); resolve(info); }, null);
    });

    // 3. 初始化群组客户端
    cp.initGroupClient(
        (msg, to, sid) => ws.sendRaw(msg, to, sid),
        session.sessionId,
        targetAid,
    );
    await cp.ensureGroupMessageStore();

    // 4. 消息路由
    ws.onRawMessage((msg) => cp.handleGroupMessage(msg));

    // 5. 注册事件处理器
    cp.setGroupEventHandler({
        onNewMessage(groupId, latestMsgId, sender, preview) {
            onMessage(aid, groupId, sender, preview);
            cp.pullAndStoreGroupMessages(groupId, 20).catch(console.error);
        },
        onGroupMessage(groupId, msg) {
            console.log(`[${aid}] 群消息: group=${groupId} content=${msg.content}`);
        },
        onNewEvent() {},
        onGroupInvite(groupId, _, invitedBy) {
            console.log(`[${aid}] 收到群邀请: group=${groupId} from=${invitedBy}`);
        },
        onJoinApproved(groupId) {
            console.log(`[${aid}] 入群已批准: group=${groupId}`);
        },
        onJoinRejected(groupId, reason) {
            console.log(`[${aid}] 入群被拒: group=${groupId} reason=${reason}`);
        },
        onJoinRequestReceived(groupId, agentId) {
            console.log(`[${aid}] 入群申请: group=${groupId} from=${agentId}`);
        },
        onGroupEvent(groupId, evt) {
            console.log(`[${aid}] 群事件: group=${groupId} type=${evt.event_type}`);
        },
    });

    return { aid, cp, ws, hb };
}

// 使用示例：同时监听两个 AID
async function main() {
    const monitors = await Promise.all([
        setupAidMonitor('alice.agentcp.io', 'agentcp.io', './data',
            (aid, gid, sender, preview) => {
                console.log(`[${aid}] 新消息 from ${sender}: ${preview}`);
            }),
        setupAidMonitor('bob.agentcp.io', 'agentcp.io', './data',
            (aid, gid, sender, preview) => {
                console.log(`[${aid}] 新消息 from ${sender}: ${preview}`);
            }),
    ]);

    console.log(`正在监听 ${monitors.length} 个 AID 的群组消息...`);

    // 可选：定时轮询兜底
    setInterval(async () => {
        for (const m of monitors) {
            const groups = await m.cp.syncGroupList();
            for (const g of groups) {
                await m.cp.pullAndStoreGroupMessages(g.group_id, 50)
                    .catch(console.error);
            }
        }
    }, 10000);
}
```

### 9.2 跨 AP 群组监听

```typescript
async function monitorCrossApGroup(
    localAid: string,
    groupUrl: string,  // 如 "https://group.other-ap.com/xxxx"
    apiUrl: string,
    dataDir: string,
) {
    const cp = new AgentCP(apiUrl, '', dataDir, { persistGroupMessages: true });
    await cp.loadAid(localAid);
    const conn = await cp.online();

    const ws = new AgentWS(localAid, conn.messageServer, conn.messageSignature);
    await ws.startWebSocket();

    // 解析群组链接
    const { targetAid, groupId } = GroupOperations.parseGroupUrl(groupUrl);
    // targetAid = "group.other-ap.com"

    // 与跨 AP 群组服务建立会话
    const session = await new Promise<{ sessionId: string }>((resolve, reject) => {
        const t = setTimeout(() => reject(new Error('超时')), 15000);
        ws.connectTo(targetAid, (info) => { clearTimeout(t); resolve(info); }, null);
    });

    // 使用跨 AP 初始化
    cp.initGroupClientCrossAp(
        (msg, to, sid) => ws.sendRaw(msg, to, sid),
        session.sessionId,
        targetAid,
    );
    await cp.ensureGroupMessageStore();

    ws.onRawMessage((msg) => cp.handleGroupMessage(msg));
    cp.setGroupEventHandler({
        onNewMessage(gid, latestMsgId, sender, preview) {
            console.log(`[跨AP] 新消息: group=${gid} sender=${sender}`);
            cp.pullAndStoreGroupMessages(gid, 20).catch(console.error);
        },
        onGroupMessage() {},
        onNewEvent() {},
        onGroupInvite() {},
        onJoinApproved() {},
        onJoinRejected() {},
        onJoinRequestReceived() {},
        onGroupEvent() {},
    });

    console.log(`正在监听跨 AP 群组: ${groupUrl}`);
}
```

---

## 10. 常见问题排查

### Q1: onGroupMessage / onNewMessage 回调从未触发

**检查清单**：

1. 是否调用了 `setGroupEventHandler`？
   - SDK 默认 handler 仅打印日志，不执行业务逻辑
   - 必须注册自定义 handler

2. 是否注册了 `onRawMessage` 拦截器？
   - 没有拦截器，群组消息不会被路由到 `handleGroupMessage`

3. `handleGroupMessage` 是否返回 true？
   - 检查日志中是否有 `handleGroupMessage skipped` 字样
   - 确认 `groupClient` 和 `_groupTargetAid` 已初始化

4. 消息的 `sender` 是否匹配 `groupTargetAid`？
   - 打开 `handleGroupMessage` 中被注释的日志确认

5. `handleIncoming` 中 payload 是否能正确解析？
   - 检查是否有 `JSON.parse failed` 错误
   - 确认 payload 中包含 `event` 字段

### Q2: 多 AID 场景下只有一个 AID 能收到消息

- 确认每个 AID 都独立完成了完整初始化流程
- 检查 `onRawMessage` 拦截器是否绑定到了正确的 `agentCP` 实例
- 确认每个 AID 的 WebSocket 连接状态正常

### Q3: 跨 AP 群组消息收不到

- 确认使用了 `initGroupClientCrossAp` 而非 `initGroupClient`
- 确认 `targetAid` 与群组所在 AP 匹配
- 检查 WebSocket 是否能连接到目标 AP 的消息服务器

### Q4: 消息重复

- `GroupMessageStore` 基于 `msg_id` 自动去重，正常情况不会重复
- 如果在 `onNewMessage` 和轮询中都调用 `pullAndStoreGroupMessages`，存储层会自动去重

### Q5: 消息丢失

- 推送通知可能因网络问题丢失，建议结合定时轮询兜底
- 检查 `handleIncoming` 中是否有 `unhandled incoming message` 警告
- 确认服务端推送的 JSON 格式包含 `event` 字段

### 调试日志开关

在 `group/client.ts` 中取消以下注释可打印详细的消息收发日志：

```typescript
// client.ts:112 — 打印原始 payload
console.log(`[GroupClient] <<< handleIncoming raw payload: ${payload.substring(0, 500)}`);

// client.ts:121 — 打印解析后的字段
console.log(`[GroupClient] <<< parsed data: action=${data.action} request_id=${data.request_id} event=${data.event}`);
```
