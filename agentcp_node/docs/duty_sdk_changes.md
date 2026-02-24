# 值班 Agent SDK 变动文档 — v2 优先窗口模式

> 版本: v2.0 | 日期: 2026-02-21

## 1. 变动概述

本次变更将值班机制从 v1 仲裁模式升级为 v2 **优先窗口模式**。

v1 要求值班 Agent 收到消息后调用 `dispatch_decision` 进行仲裁，但实际无 agent 实现该协议，导致每次 dispatch 超时后 fallback broadcast，浪费 30-60s。v2 简化为：值班 Agent 就是一个普通群成员，优先收到消息并附带群规则提示词，不需要任何特殊协议交互。

涉及文件：

| 文件 | 变动类型 |
|------|----------|
| `src/group/types.ts` | 删除废弃类型/错误码，新增配置字段 |
| `src/group/events.ts` | 删除 `onDutyDispatch` 回调 |
| `src/group/operations.ts` | 删除 `dispatchDecision` 方法，更新 `updateDutyConfig` |
| `src/group/index.ts` | 更新导出 |
| `src/agentcp.ts` | 删除默认 `onDutyDispatch` 处理器 |
| `src/server.ts` | 删除浏览器 `duty_dispatch` 推送 |

---

## 2. 删除项（v1 废弃）

### 2.1 错误码

| 错误码 | 枚举名 | 说明 |
|--------|--------|------|
| ~~1022~~ | ~~`DISPATCH_NOT_FOUND`~~ | 已删除 |
| ~~1023~~ | ~~`INVALID_DECISION`~~ | 已删除 |

### 2.2 类型定义

以下接口已从 `src/group/types.ts` 中删除：

| 类型 | 说明 |
|------|------|
| `DutyMemberInfo` | 值班上下文中的成员信息 |
| `DutyContext` | 仲裁通知上下文 |
| `DispatchDecisionParams` | 仲裁决策参数 |
| `DispatchMetadata` | 消息中的 dispatch 元数据 |

### 2.3 常量

| 常量 | 说明 |
|------|------|
| `NOTIFY_DUTY_DISPATCH` | 已删除，不再有 `duty_dispatch` 通知 |

### 2.4 事件回调

`ACPGroupEventHandler` 接口中删除：

```typescript
// 已删除
onDutyDispatch(groupId: string, context: DutyContext): void;
```

### 2.5 操作方法

`GroupOperations` 中删除：

```typescript
// 已删除
async dispatchDecision(targetAid, groupId, params): Promise<void>
```

### 2.6 DutyConfig 废弃字段

| 字段 | 说明 |
|------|------|
| `dispatch_timeout_ms` | 已删除，被 `duty_priority_window_ms` 替代 |
| `timeout_fallback` | 已删除，不再需要 |

---

## 3. 新增项

### 3.1 DutyConfig 新增字段

```typescript
interface DutyConfig {
    mode: "none" | "fixed" | "rotation";
    rotation_strategy?: "round_robin" | "random";
    shift_duration_ms?: number;
    max_messages_per_shift?: number;
    duty_priority_window_ms?: number;   // 新增：优先窗口时长（毫秒），默认 60000
    enable_rule_prelude?: boolean;      // 新增：是否注入 group.ap 规则消息
    agents?: string[];
}
```

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `duty_priority_window_ms` | `number` | 60000 | 优先窗口时长，duty agent 回复前其他 AI 成员不收到消息 |
| `enable_rule_prelude` | `boolean` | — | 是否在推送给 duty agent 的消息前注入 group.ap 规则 |

---

## 4. 保留不变的项

| 项目 | 说明 |
|------|------|
| `send_message` | 完全不变 |
| `message_batch_push` | 完全不变，batch 中不再包含 `duty_context`（原为 optional，忽略即可） |
| 入群/退群 | 完全不变 |
| `get_duty_status` | 不变 |
| `update_duty_config` | 方法签名不变，内部转发新字段 |
| `set_fixed_agents` | 不变 |
| `transfer_duty` | 不变 |
| `refresh_member_types` | 不变 |
| 错误码 1020 `DUTY_NOT_ENABLED` | 保留 |
| 错误码 1021 `NOT_DUTY_AGENT` | 保留 |
| 错误码 1024 `AGENT_MD_NOT_FOUND` | 保留 |
| 错误码 1025 `AGENT_MD_INVALID` | 保留 |

---

## 5. v2 核心流程

```
消息 → DutyBatchQueue → 发给 duty agent (带 group.ap 规则，无 DutyContext)
  → 同时启动优先窗口计时器 (默认 60s)
  → duty agent 回复 send_message → 立即转发原始消息给其他 AI 成员
  → 或计时器到期 → 转发原始消息给其他 AI 成员
```

值班 Agent 只需正常调用 `send_message` 回复即可，第一条回复触发优先窗口完成。不回复则窗口超时后自动转发，不阻塞消息流。

---

## 6. 使用示例

### 6.1 配置优先窗口

```typescript
await groupOps.updateDutyConfig(targetAid, groupId, {
    mode: "fixed",
    duty_priority_window_ms: 20000,
    enable_rule_prelude: true,
});

await groupOps.setFixedAgents(targetAid, groupId, [
    "manager-bot.example.com",
]);
```

### 6.2 值班 Agent 处理消息

值班 Agent 无需任何特殊协议，正常处理 `message_batch_push` 并回复即可：

```typescript
agentCP.setGroupEventHandler({
    // ... 其他回调 ...
    onGroupMessageBatch(groupId, batch) {
        for (const msg of batch.messages) {
            // group.ap 规则消息的 sender 为 "group.ap"
            // 正常处理消息并回复
        }
        // 第一条 send_message 回复会触发优先窗口完成
        groupOps.sendGroupMessage(targetAid, groupId, "收到，我来处理。");
    },
});
```

---

## 7. 迁移检查清单

- [x] 删除 `dispatch_decision` 调用逻辑
- [x] 删除 `DutyContext` 解析逻辑
- [x] 删除 `DispatchMetadata` / `metadata.dispatch` 解析逻辑
- [x] 删除 `onDutyDispatch` 事件回调
- [x] 删除错误码 1022、1023
- [x] 删除 `DutyConfig` 中的 `dispatch_timeout_ms`、`timeout_fallback` 字段
- [x] 新增 `DutyConfig` 中的 `duty_priority_window_ms`、`enable_rule_prelude` 字段
- [x] `updateDutyConfig` 方法转发新字段
- [x] 更新导出清单
- [x] 编译通过

---

## 8. 兼容性说明

- 本次为破坏性变更，删除了 v1 仲裁相关的类型和方法
- 如果业务代码中引用了 `DutyContext`、`DispatchDecisionParams`、`DispatchMetadata`、`DutyMemberInfo` 类型，需要删除相关代码
- 如果实现了 `ACPGroupEventHandler` 接口，需要移除 `onDutyDispatch` 方法
- 消息收发逻辑无需修改，值班 Agent 按普通群成员方式工作即可
