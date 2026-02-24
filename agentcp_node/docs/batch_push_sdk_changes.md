# SDK 批量推送（message_batch_push）改造指南

本文档总结 TypeScript SDK (acp-ts) 接入 `message_batch_push` 的完整改动，供其他语言 SDK 参考实施。

## 1. 背景

服务端不再按"每条消息 × 每个接收者"即时推送（`message_push`），改为按 `(receiver_agent_id, group_id)` 聚合后批量推送消息列表，新 action 为 `message_batch_push`。

旧的 `message_push`（单条推送）已废弃，SDK 侧需完全移除对应处理逻辑。

## 2. 服务端推送数据格式

```json
{
  "action": "message_batch_push",
  "group_id": "g-123",
  "code": 0,
  "data": {
    "messages": [
      {
        "msg_id": 1001,
        "sender": "agent-a.aid.pub",
        "content": "hello",
        "content_type": "text/plain",
        "timestamp": 1739700000000
      }
    ],
    "start_msg_id": 1001,
    "latest_msg_id": 1003,
    "count": 3
  }
}
```

## 3. 改动清单

### 3.1 类型定义

新增常量和类型：

```typescript
// 常量
const ACTION_MESSAGE_BATCH_PUSH = "message_batch_push"

// 批量消息结构体
interface GroupMessageBatch {
    messages: GroupMessage[]  // 消息列表
    start_msg_id: number      // 批内首条 msg_id
    latest_msg_id: number     // 批内末条 msg_id
    count: number             // 批内消息数
}
```

删除：
- `NOTIFY_GROUP_MESSAGE` 常量（不再使用）

### 3.2 事件接口（破坏性变更）

`ACPGroupEventHandler` 接口：

- **删除** `onGroupMessage(groupId, msg)` — 单条消息回调
- **新增** `onGroupMessageBatch(groupId, batch)` — 批量消息回调

```typescript
interface ACPGroupEventHandler {
    // ... 其他方法不变 ...
    onGroupMessageBatch(groupId: string, batch: GroupMessageBatch): void  // 新增
    // 删除: onGroupMessage(groupId: string, msg: GroupMessage): void
}
```

所有实现了 `ACPGroupEventHandler` 的地方都需要同步修改。

### 3.3 收包分发（handleIncoming）

在 `ACPGroupClient.handleIncoming()` 中：

**删除**旧的 `message_push` 处理分支。

**新增** `message_batch_push` 处理分支（放在 request/response 和 notification 判断之后）：

```
收到 payload → JSON.parse
  → 有 request_id？ → 走 response 配对逻辑
  → 有 event 字段？ → 走 notification 分发逻辑
  → action == "message_batch_push" 且有 data？
      → 解析 data 为 GroupMessageBatch
      → 将 data.messages 中每条消息解析为 GroupMessage 对象
      → 调用 handler.onGroupMessageBatch(group_id, batch)
      → 直接 return，不走其他逻辑
```

关键实现：

```typescript
const action = data.action ?? "";
if (action === ACTION_MESSAGE_BATCH_PUSH && data.data) {
    const batchData = data.data;
    const batch: GroupMessageBatch = {
        messages: (batchData.messages ?? []).map((m: any) => ({
            msg_id: m.msg_id ?? 0,
            sender: m.sender ?? "",
            content: m.content ?? "",
            content_type: m.content_type ?? "text/plain",
            timestamp: m.timestamp ?? 0,
            metadata: m.metadata ?? null,
        })),
        start_msg_id: batchData.start_msg_id ?? 0,
        latest_msg_id: batchData.latest_msg_id ?? 0,
        count: batchData.count ?? 0,
    };
    handler.onGroupMessageBatch(data.group_id ?? "", batch);
    return;
}
```

### 3.4 消息处理逻辑（processAndAckBatch）

收到 batch 后的标准处理流程：

```
1. 将 batch.messages 按 msg_id 升序排序
2. 批量存储到本地（存储层需以 msg_id 去重，防止与 pull 拉取的消息重复）
3. ACK batch 中排序后最后一条消息的 msg_id
```

参考实现：

```typescript
public processAndAckBatch(groupId: string, batch: GroupMessageBatch): GroupMessage[] {
    const sorted = [...batch.messages].sort((a, b) => a.msg_id - b.msg_id);
    store.addMessages(groupId, sorted);  // 批量存储（内部去重）

    if (sorted.length > 0) {
        const lastMsgId = sorted[sorted.length - 1].msg_id;
        groupOps.ackMessages(targetAid, groupId, lastMsgId);  // 异步 ACK
    }

    return sorted;
}
```

### 3.5 消息去重

存储层的 `addMessages` 必须做幂等去重。推荐策略：

- 维护 per-group 的 `lastMsgId`（已存储的最大 msg_id）
- 写入时跳过 `msg_id <= lastMsgId` 的消息

这样可以防止 batch push 和 `pullMessages` 拉取到重叠消息时重复存储。

### 3.6 冷启动同步

`joinGroupSession` 时，在 `register_online` 之后、进入批推送接收之前，先做一次 pull 对齐历史：

```
1. register_online(targetAid)
2. lastMsgId = 本地存储的最新 msg_id
3. pullAndStoreMessages(groupId, afterMsgId=lastMsgId)  // 拉取未读历史
4. 启动心跳定时器
```

### 3.7 在线状态前置条件

批量推送只发送给"在线注册"的 agent，SDK 必须：

1. 建立会话后调用 `register_online`
2. 周期调用 `heartbeat` 保活（建议 2~4 分钟）
3. 退出时调用 `unregister_online`

否则不会收到 `message_batch_push`，只能靠 `pull_messages` 拉取。

## 4. 通知外部（UI / 上层应用）

收到 batch 后，应将**完整的排序后消息列表**一次性通知给上层，而非逐条通知：

```typescript
// 推送给 UI
notify({
    type: 'group_message_batch',
    group_id: groupId,
    messages: sorted,        // 完整消息列表
    count: batch.count,
    start_msg_id: batch.start_msg_id,
    latest_msg_id: batch.latest_msg_id,
});
```

## 5. 删除项汇总

以下旧逻辑需要完全移除：

| 删除项 | 说明 |
|---|---|
| `NOTIFY_GROUP_MESSAGE` 常量 | 不再使用 |
| `onGroupMessage(groupId, msg)` | 接口方法，替换为 `onGroupMessageBatch` |
| `message_push` 处理分支 | handleIncoming 中的旧单条推送处理 |
| `dispatchAcpNotify` 中的 `NOTIFY_GROUP_MESSAGE` 分支 | 不再通过 notify 通道分发消息 |

## 6. 改动文件对照表（TypeScript SDK 实际改动）

| 文件 | 改动 |
|---|---|
| `group/types.ts` | +`ACTION_MESSAGE_BATCH_PUSH`, +`GroupMessageBatch`, -`NOTIFY_GROUP_MESSAGE` |
| `group/events.ts` | 接口 +`onGroupMessageBatch`, -`onGroupMessage`, dispatch 移除旧分支 |
| `group/client.ts` | handleIncoming: +`message_batch_push` 分支, -`message_push` 分支 |
| `group/index.ts` | 导出新增类型和常量 |
| `agentcp.ts` | +`processAndAckBatch`, 默认 handler 改为 batch, joinGroupSession 加冷启动同步 |
| `server.ts` | handler 改为 `onGroupMessageBatch`, 通知改为推送消息列表 |
