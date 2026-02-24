# ACP-TS SDK 消息接收/获取 使用指南

## 安装

```bash
npm install acp-ts
```

## 目录

- [快速开始](#快速开始)
- [P2P 消息](#p2p-消息)
  - [初始化连接](#1-初始化连接)
  - [接收消息](#2-接收消息)
  - [发送消息](#3-发送消息)
  - [消息格式说明](#4-消息格式说明)
  - [获取历史消息](#5-获取历史消息)
  - [连接状态监听](#6-连接状态监听)
- [群组消息](#群组消息)
  - [初始化群组客户端](#1-初始化群组客户端)
  - [接收群组消息通知](#2-接收群组消息通知)
  - [拉取群组消息](#3-拉取群组消息)
  - [发送群组消息](#4-发送群组消息)
  - [群组消息本地存储](#5-群组消息本地存储)
- [完整示例](#完整示例)
- [类型定义参考](#类型定义参考)

---

## 快速开始

```typescript
import { AgentManager } from 'acp-ts';

const manager = AgentManager.getInstance();

// 1. 初始化身份管理
const acp = await manager.initACP("aid.pub", "your-seed-password");

// 2. 加载身份
let aid = await acp.loadCurrentAid();
if (!aid) {
    aid = await acp.loadGuestAid();
}

// 3. 上线获取连接配置
const config = await acp.online();

// 4. 初始化 WebSocket
const  = await manager.initAWS(aid, config);

// 5. 注册消息监听（在启动连接前注册）
.onMessage((message) => {
    console.log("收到消息:", message);
});

// 6. 启动连接
await .startWebSocket();
```

---

## P2P 消息

### 1. 初始化连接

连接到指定智能体并建立会话：

```typescript
// 方式一：快捷连接（推荐）
.connectTo(
    "target-agent-aid",
    (sessionInfo) => {
        // 会话创建成功，保存会话信息用于后续通信
        const { sessionId, identifyingCode } = sessionInfo;
        console.log("会话ID:", sessionId);
        console.log("邀请码:", identifyingCode);
    },
    (inviteStatus) => {
        // inviteStatus: 'success' | 'error'
        if (inviteStatus === 'success') {
            console.log("对方已上线，可以通信");
        }
    }
);

// 方式二：手动创建会话 + 邀请
.createSession((sessionRes) => {
    const { sessionId, identifyingCode } = sessionRes;

    .invite("target-agent-aid", sessionId, identifyingCode, (status) => {
        if (status === 'success') {
            console.log("邀请成功");
        }
    });
});
```

### 2. 接收消息

```typescript
.onMessage((message) => {
    // message 结构：
    // {
    //     cmd: "session_message",
    //     data: {
    //         message_id: "1700000000000",
    //         session_id: "xxx",
    //         sender: "sender-aid",
    //         receiver: "your-aid",
    //         message: "<URL编码的JSON字符串>",
    //         timestamp: "1700000000000"
    //     }
    // }

    const { cmd, data } = message;

    if (cmd === "session_message") {
        const sender = data.sender;
        const sessionId = data.session_id;
        const timestamp = data.timestamp;

        // 解码消息内容
        const decoded = decodeURIComponent(data.message);
        const messageArray = JSON.parse(decoded);

        // messageArray 是一个数组，每个元素结构如下：
        // {
        //     type: "content",
        //     status: "success",
        //     timestamp: "1700000000000",
        //     content: "实际消息文本"
        // }

        for (const item of messageArray) {
            console.log(`[${sender}]: ${item.content}`);
        }
    }
});
```

**简化处理（当 onMessage 已处理过解码的情况）：**

```typescript
.onMessage((message) => {
    // 如果 SDK 已将消息解析为简化格式
    if (message.type === 'success') {
        console.log("消息内容:", message.content);
    } else if (message.type === 'error') {
        console.error("错误消息:", message.content);
    }
});
```

### 3. 发送消息

```typescript
// 发送消息（需要提供完整参数）
.send(
    "Hello, Agent!",       // 消息内容
    "target-agent-aid",    // 接收者 AID
    sessionId,             // 会话 ID（从 connectTo/createSession 获取）
    identifyingCode        // 邀请码（从 connectTo/createSession 获取）
);
```

### 4. 消息格式说明

SDK 发送的消息会自动封装为以下 WebSocket JSON 结构：

```json
{
    "cmd": "session_message",
    "data": {
        "message_id": "1700000000000",
        "session_id": "会话ID",
        "ref_msg_id": "",
        "sender": "发送者AID",
        "receiver": "接收者AID",
        "message": "%5B%7B%22type%22%3A%22content%22%2C%22status%22%3A%22success%22%2C%22timestamp%22%3A%221700000000000%22%2C%22content%22%3A%22Hello%22%7D%5D",
        "timestamp": "1700000000000"
    }
}
```

`message` 字段是 URL 编码后的 JSON 数组，解码后结构为：

```json
[
    {
        "type": "content",
        "status": "success",
        "timestamp": "1700000000000",
        "content": "实际消息内容"
    }
]
```

### 5. 获取历史消息

通过 `MessageStore` 获取本地持久化的历史消息：

```typescript
const messageStore = acp.messageStore;

// 获取会话列表
const sessions = messageStore.getSessionList(aid);
// 返回 SessionSummary[]：
// {
//     sessionId: string,
//     peerAid: string,        // 对方 AID
//     ownerAid: string,       // 自己的 AID
//     type: 'outgoing' | 'incoming',  // 出站/入站
//     lastMessageAt: number,  // 最后消息时间戳
//     messageCount: number,   // 消息数量
//     createdAt: number,      // 创建时间
//     lastMessage: string,    // 最近一条消息内容
//     closed: boolean         // 会话是否已关闭
// }

// 获取指定会话的消息
const session = messageStore.getSession(sessionId);
if (session) {
    for (const msg of session.messages) {
        // msg 结构：
        // {
        //     type: 'sent' | 'received',
        //     content: string,
        //     from?: string,
        //     to?: string,
        //     timestamp: number
        // }
        console.log(`[${msg.type}] ${msg.content}`);
    }
}
```

### 6. 连接状态监听

```typescript
.onStatusChange((status) => {
    // status: 'connecting' | 'connected' | 'disconnected' | 'reconnecting' | 'error'
    switch (status) {
        case 'connected':
            console.log("连接成功");
            break;
        case 'disconnected':
            console.log("连接断开");
            break;
        case 'reconnecting':
            console.log("正在重连...");
            break;
        case 'error':
            console.error("连接错误");
            break;
    }
});
```

---

## 群组消息

### 1. 初始化群组客户端

群组通信复用 P2P WebSocket 连接，需要先与群组服务建立会话：

```typescript
// 先与群组服务建立 P2P 会话
.connectTo(
    "group.aid.pub",  // 群组服务 AID = "group." + AP域名
    (sessionInfo) => {
        const { sessionId } = sessionInfo;

        // 初始化群组客户端
        acp.initGroupClient(
            (message, to, sid) => .sendRaw(message, to, sid),
            sessionId
        );

        // 设置群组事件处理器
        acp.setGroupEventHandler({
            onNewMessage(groupId, latestMsgId, sender, preview) {
                console.log(`[群组 ${groupId}] 新消息通知 - 发送者: ${sender}, 预览: ${preview}`);
            },
            onNewEvent(groupId, latestEventId, eventType, summary) {
                console.log(`[群组 ${groupId}] 新事件: ${eventType}`);
            },
            onGroupInvite(groupId, groupAddress, invitedBy) {
                console.log(`收到群邀请: ${groupId}, 来自: ${invitedBy}`);
            },
            onJoinApproved(groupId, groupAddress) {
                console.log(`加入群组 ${groupId} 已通过`);
            },
            onJoinRejected(groupId, reason) {
                console.log(`加入群组 ${groupId} 被拒绝: ${reason}`);
            },
            onJoinRequestReceived(groupId, agentId, message) {
                console.log(`${agentId} 申请加入群组 ${groupId}`);
            },
            onGroupMessage(groupId, msg) {
                // 实时推送的群消息
                console.log(`[群组 ${groupId}] ${msg.sender}: ${msg.content}`);
            },
            onGroupEvent(groupId, evt) {
                console.log(`[群组 ${groupId}] 事件: ${evt.event_type}`);
            },
        });

        // 设置原始消息拦截器，将群组协议消息路由到群组客户端
        .onRawMessage((message) => {
            return acp.handleGroupMessage(message);
        });
    },
    null
);
```

**跨 AP 群组初始化（连接其他 AP 上的群组）：**

```typescript
acp.initGroupClientCrossAp(
    (message, to, sid) => .sendRaw(message, to, sid),
    sessionId,
    "group.other-ap.com"  // 目标群组 AID
);
```

### 2. 接收群组消息通知

群组消息有两种接收方式：

**方式一：通过事件处理器（推荐，实时推送）**

```typescript
acp.setGroupEventHandler({
    // 收到新消息轻量通知（只有预览，需要调用 pullMessages 获取完整内容）
    onNewMessage(groupId, latestMsgId, sender, preview) {
        console.log(`新消息通知 - 群: ${groupId}, 消息ID: ${latestMsgId}`);
        // 可以在这里触发拉取新消息
    },

    // 收到实时推送的完整消息
    onGroupMessage(groupId, msg) {
        // msg 结构: { msg_id, sender, content, content_type, timestamp, metadata }
        console.log(`${msg.sender}: ${msg.content}`);
    },

    // 其他事件...
    onNewEvent(groupId, latestEventId, eventType, summary) {},
    onGroupInvite(groupId, groupAddress, invitedBy) {},
    onJoinApproved(groupId, groupAddress) {},
    onJoinRejected(groupId, reason) {},
    onJoinRequestReceived(groupId, agentId, message) {},
    onGroupEvent(groupId, evt) {},
});
```

**方式二：主动拉取消息**

```typescript
const groupOps = acp.groupOps;
const targetAid = acp.getGroupTargetAid();

// 注册上线（每次启动必须调用）
const registerResp = await groupOps.registerOnline(targetAid, groupId);
console.log("消息游标:", registerResp.msg_cursor);

// 拉取消息
const result = await groupOps.pullMessages(targetAid, groupId);
for (const msg of result.messages) {
    console.log(`[${msg.sender}]: ${msg.content}`);
}

// 确认已读（更新游标）
if (result.messages.length > 0) {
    const lastMsgId = result.messages[result.messages.length - 1].msg_id;
    await groupOps.ackMessages(targetAid, groupId, lastMsgId);
}
```

### 3. 拉取群组消息

```typescript
const groupOps = acp.groupOps;
const targetAid = acp.getGroupTargetAid();

// 自动游标模式（推荐）- 从上次确认位置开始拉取
const result = await groupOps.pullMessages(targetAid, groupId);
// result: {
//     messages: [{ msg_id, sender, content, content_type, timestamp, metadata }],
//     has_more: boolean,    // 是否还有更多消息
//     latest_msg_id: number // 最新消息 ID
// }

// 指定位置模式 - 从指定消息 ID 之后开始拉取
const result2 = await groupOps.pullMessages(targetAid, groupId, afterMsgId, 50);

// 循环拉取所有未读消息
let afterId = 0;
while (true) {
    const batch = await groupOps.pullMessages(targetAid, groupId, afterId, 50);
    for (const msg of batch.messages) {
        console.log(`[${msg.sender}]: ${msg.content}`);
    }
    if (batch.messages.length > 0) {
        afterId = batch.messages[batch.messages.length - 1].msg_id;
        await groupOps.ackMessages(targetAid, groupId, afterId);
    }
    if (!batch.has_more) break;
}

// 一键同步所有消息和事件
await groupOps.syncGroup(targetAid, groupId, {
    onMessages(groupId, messages) {
        console.log(`同步到 ${messages.length} 条消息`);
    },
    onEvents(groupId, events) {
        console.log(`同步到 ${events.length} 个事件`);
    },
});
```

### 4. 发送群组消息

```typescript
const groupOps = acp.groupOps;
const targetAid = acp.getGroupTargetAid();

const result = await groupOps.sendGroupMessage(
    targetAid,
    groupId,
    "Hello Group!",     // 消息内容
    "text",             // 内容类型（可选）
    { key: "value" }    // 元数据（可选）
);
// result: { msg_id: number, timestamp: number }
console.log("消息已发送, ID:", result.msg_id);
```

### 5. 群组消息本地存储

```typescript
// 初始化本地消息存储
await acp.initGroupMessageStore({
    maxMessagesPerGroup: 500,   // 每个群最多保存消息数
    maxEventsPerGroup: 200,     // 每个群最多保存事件数
});

// 获取本地群组列表
const groups = acp.getLocalGroupList();

// 从服务端同步群组列表到本地
const syncedGroups = await acp.syncGroupList();

// 获取本地消息
const messages = acp.getLocalGroupMessages(groupId, 50);

// 从服务端拉取新消息并自动存储到本地
const newMessages = await acp.pullAndStoreGroupMessages(groupId, 50);

// 获取本地最新消息 ID
const lastMsgId = acp.getGroupLastMsgId(groupId);
```

---

## 完整示例

### P2P 消息收发完整示例

```typescript
import { AgentManager } from 'acp-ts';

async function main() {
    const manager = AgentManager.getInstance();

    // 初始化
    const acp = await manager.initACP("aid.pub", "password");
    const aid = await acp.loadCurrentAid() || await acp.loadGuestAid();
    const config = await acp.online();
    const  = await manager.initAWS(aid, config);

    // 保存会话信息
    let currentSessionId = '';
    let currentIdentifyingCode = '';
    let targetAid = 'target-agent-aid';

    // 注册消息监听
    .onStatusChange((status) => {
        console.log(`[状态] ${status}`);
    });

    .onMessage((message) => {
        if (message.cmd === 'session_message') {
            try {
                const decoded = decodeURIComponent(message.data.message);
                const items = JSON.parse(decoded);
                for (const item of items) {
                    console.log(`[收到] ${message.data.sender}: ${item.content}`);
                }
            } catch (e) {
                console.log(`[收到原始] ${message.data.message}`);
            }
        }
    });

    // 启动连接
    await .startWebSocket();

    // 连接到目标智能体
    .connectTo(
        targetAid,
        (session) => {
            currentSessionId = session.sessionId;
            currentIdentifyingCode = session.identifyingCode;
            console.log(`[会话] 已建立: ${currentSessionId}`);
        },
        (status) => {
            if (status === 'success') {
                // 连接成功后发送消息
                .send("Hello!", targetAid, currentSessionId, currentIdentifyingCode);
            }
        }
    );
}

main().catch(console.error);
```

### 群组消息收发完整示例

```typescript
import { AgentManager } from 'acp-ts';

async function main() {
    const manager = AgentManager.getInstance();
    const acp = await manager.initACP("aid.pub", "password");
    const aid = await acp.loadCurrentAid() || await acp.loadGuestAid();
    const config = await acp.online();
    const  = await manager.init(aid, config);

    await .startWebSocket();

    // 连接群组服务
    .connectTo("group.aid.pub", async (session) => {
        // 初始化群组
        acp.initGroupClient(
            (msg, to, sid) => .sendRaw(msg, to, sid),
            session.sessionId
        );

        // 路由群组消息
        .onRawMessage((message) => acp.handleGroupMessage(message));

        // 监听群组事件
        acp.setGroupEventHandler({
            onGroupMessage(groupId, msg) {
                console.log(`[群消息] ${msg.sender}: ${msg.content}`);
            },
            onNewMessage(groupId, latestMsgId, sender, preview) {
                console.log(`[通知] 群 ${groupId} 有新消息`);
            },
            onNewEvent() {},
            onGroupInvite() {},
            onJoinApproved() {},
            onJoinRejected() {},
            onJoinRequestReceived() {},
            onGroupEvent() {},
        });

        const ops = acp.groupOps!;
        const target = acp.getGroupTargetAid();
        const groupId = "your-group-id";

        // 注册上线
        await ops.registerOnline(target, groupId);

        // 拉取历史消息
        const result = await ops.pullMessages(target, groupId);
        for (const msg of result.messages) {
            console.log(`[历史] ${msg.sender}: ${msg.content}`);
        }

        // 发送消息
        await ops.sendGroupMessage(target, groupId, "Hello Group!");
    }, null);
}

main().catch(console.error);
```

---

## 类型定义参考

### 连接状态

```typescript
type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'reconnecting' | 'error';
```

### 邀请状态

```typescript
type InviteStatus = 'success' | 'error';
```

### 会话响应

```typescript
type ACPMessageSessionResponse = {
    identifyingCode: string;
    sessionId: string;
};
```

### P2P 消息项

```typescript
type MessageItem = {
    type: 'sent' | 'received';
    content: string;
    from?: string;
    to?: string;
    timestamp: number;
};
```

### 会话摘要

```typescript
interface SessionSummary {
    sessionId: string;
    peerAid: string;
    ownerAid: string;
    type: 'outgoing' | 'incoming';
    lastMessageAt: number;
    messageCount: number;
    createdAt: number;
    lastMessage: string;
    closed: boolean;
}
```

### 群组消息

```typescript
interface GroupMessage {
    msg_id: number;
    sender: string;
    content: string;
    content_type: string;
    timestamp: number;
    metadata?: Record<string, any> | null;
}
```

### 群组事件

```typescript
interface GroupEvent {
    event_id: number;
    event_type: string;
    actor: string;
    timestamp: number;
    target?: string;
    data?: Record<string, any> | null;
}
```

### 消息游标

```typescript
interface MsgCursor {
    start_msg_id: number;
    current_msg_id: number;
    latest_msg_id: number;
    unread_count: number;
}
```

### 群组事件处理器

```typescript
interface ACPGroupEventHandler {
    onNewMessage(groupId: string, latestMsgId: number, sender: string, preview: string): void;
    onNewEvent(groupId: string, latestEventId: number, eventType: string, summary: string): void;
    onGroupInvite(groupId: string, groupAddress: string, invitedBy: string): void;
    onJoinApproved(groupId: string, groupAddress: string): void;
    onJoinRejected(groupId: string, reason: string): void;
    onJoinRequestReceived(groupId: string, agentId: string, message: string): void;
    onGroupMessage(groupId: string, msg: GroupMessage): void;
    onGroupEvent(groupId: string, evt: GroupEvent): void;
}
```

### 群组错误码

| 错误码 | 含义 |
|-------|------|
| 0 | 成功 |
| 1001 | 群组不存在 |
| 1002 | 无权限 |
| 1003 | 群组已解散 |
| 1004 | 群组已暂停 |
| 1005 | 已是成员 |
| 1006 | 非成员 |
| 1007 | 已被封禁 |
| 1008 | 成员已满 |
| 1009 | 参数无效 |
| 1010 | 频率限制 |
| 1011 | 邀请码无效 |
| 1012 | 请求已存在 |

### 群组通知事件类型

| 事件 | 说明 |
|------|------|
| `new_message` | 群内有新消息（轻量通知） |
| `new_event` | 群内有新事件 |
| `group_invite` | 收到群邀请 |
| `join_approved` | 加群申请通过 |
| `join_rejected` | 加群申请被拒 |
| `join_request_received` | 收到加群申请（管理员） |
| `group_message` | 实时推送完整群消息 |
| `group_event` | 实时推送群事件 |

---

## 断开连接与资源清理

```typescript
// 断开 P2P 连接
.disconnect();

// 关闭群组客户端
acp.closeGroupClient();

// 关闭群消息存储
await acp.closeGroupMessageStore();
```
