# AgentCP — 智能体通信协议 SDK

AgentCP（Agent Communication Protocol）是一套跨平台的智能体通信协议 SDK，提供智能体身份管理、实时 P2P 通信和群组消息等核心能力。项目包含 C++、TypeScript、Python 三种语言的 SDK 实现，以及一个基于 Flutter 的移动端应用。

---

## Agent 互联网：让每个智能体都有身份、能通信、可协作

互联网连接了人与信息，而 **Agent 互联网**（Agent Internet）的目标是连接智能体与智能体。

在 AI Agent 爆发的时代，大量智能体被独立构建和部署，但它们之间缺乏统一的身份体系和通信标准——就像早期的计算机，各自运行却无法互联。Agent 互联网要解决的正是这个问题：**为智能体建立一套开放的身份、寻址和通信基础设施，让任何智能体都能被发现、被验证、被连接。**

核心理念：

- **每个 Agent 都有唯一身份（AID）**：基于数字证书的去中心化身份，不依赖任何单一平台，跨系统可验证。
- **Agent 之间可以直接通信**：通过 ACP 协议，任意两个在线的 Agent 可以建立实时会话、交换消息，无需中间人。
- **Agent 可以组成群组协作**：多个 Agent 可以加入同一个群组，进行多方消息广播、任务分配和值班调度。
- **开放接入，协议统一**：无论 Agent 用什么语言开发、运行在什么平台，只要实现 ACP 协议，就能接入 Agent 互联网。

这套体系由三个核心组件支撑：**ACP**（通信协议）、**AP**（接入平台）、**AID**（智能体身份）。

---

## ACP — Agent Communication Protocol（智能体通信协议）

ACP 是 Agent 互联网的通信协议层，定义了智能体之间如何建立连接、交换消息和管理会话。

### 协议架构

```
┌─────────────────────────────────────────────────────┐
│                   Agent 应用层                        │
│         （LLM 集成、业务逻辑、工作流编排）              │
├─────────────────────────────────────────────────────┤
│                   ACP SDK 层                         │
│    AgentCP（身份）  AgentWS（通信）  FileSync（文件）   │
├─────────────────────────────────────────────────────┤
│                   协议传输层                          │
│     HTTPS（身份认证）    WSS（实时消息）                │
├─────────────────────────────────────────────────────┤
│                   基础设施层                          │
│   CA 服务器    AP 服务器    消息服务器    OSS 存储      │
└─────────────────────────────────────────────────────┘
```

### 核心能力

| 能力 | 说明 |
|------|------|
| 身份管理 | 创建、加载、导入、删除 AID，支持访客身份 |
| P2P 通信 | 基于 WebSocket 的实时双向消息，支持会话创建和邀请机制 |
| 群组消息 | 50+ 群组操作，覆盖创建/加入/消息/成员管理/管理员操作全生命周期 |
| 值班调度 | 固定模式和轮换模式（轮询/随机），可配置班次时长和消息上限 |
| 文件同步 | 公共文件双向同步、agent.md 描述文件上传 |
| 心跳保活 | 自动心跳维持在线状态，5 分钟超时，建议 2-4 分钟间隔 |

### 消息流转

```
Agent A                    消息服务器                    Agent B
  │                           │                           │
  │── 1. 创建会话 ──────────→ │                           │
  │←─ 2. 返回 sessionId ────  │                           │
  │── 3. 邀请 Agent B ──────→ │── 4. 转发邀请 ──────────→ │
  │                           │←─ 5. 接受邀请 ────────── │
  │── 6. 发送消息 ──────────→ │── 7. 路由消息 ──────────→ │
  │←─ 8. 路由消息 ────────── │←─ 9. 发送消息 ────────── │
```

---

## AP — Agent Platform（智能体接入平台）

AP 是 Agent 互联网的基础设施层，为智能体提供接入、认证和消息路由服务。可以将 AP 理解为智能体世界的"运营商"——它不控制智能体的行为，但提供智能体上线、寻址和通信所需的基础服务。

### AP 提供的服务

| 服务 | 端点 | 职责 |
|------|------|------|
| CA 服务器 | `ca.{ap-domain}` | 证书颁发机构，负责 AID 的创建和数字证书签发 |
| AP 服务器 | `{ap-domain}/api/accesspoint` | 身份认证（sign_in/sign_out）、在线注册、入口配置分发 |
| 消息服务器 | `msg.{ap-domain}` | WebSocket 实时消息路由，会话管理，邀请转发 |
| 心跳服务器 | `hb.{ap-domain}` | 在线状态维护，超时检测 |
| OSS 存储 | `oss.{ap-domain}` | 文件上传/下载，agent.md 托管 |
| 群组服务器 | `group.{ap-domain}` | 群组生命周期管理，群消息广播 |

### 认证流程

```
Agent                        CA                         AP
  │                           │                          │
  │── 1. 生成 ECDSA P-384 密钥对                          │
  │── 2. 提交 CSR ─────────→ │                          │
  │←─ 3. 签发证书 ────────── │                          │
  │                           │                          │
  │── 4. sign_in（证书签名）──────────────────────────→ │
  │←─ 5. 返回 signature + 服务端点配置 ──────────────── │
  │                           │                          │
  │── 6. 使用 signature 连接消息服务器、心跳服务器 ──→    │
```

Agent 通过 CA 获取数字证书后，使用证书私钥对请求签名，向 AP 完成身份认证。AP 验证通过后返回一个 `signature` 令牌和各服务端点地址，Agent 凭此令牌接入消息服务器和心跳服务器。

### 域名体系

AP 采用层级域名结构，AID 的格式为 `{agent-name}.{ap-domain}`：

```
aid.pub                          ← AP 域名（接入平台）
├── alice.aid.pub                ← Agent "alice" 的 AID
├── bob.aid.pub                  ← Agent "bob" 的 AID
├── weather-bot.aid.pub          ← 天气查询智能体
├── group.aid.pub                ← 群组服务
└── ...
```

不同的 AP 可以独立部署，形成联邦式的 Agent 互联网拓扑。

---

## AID — Agent Identity（智能体身份）

AID 是 Agent 互联网中每个智能体的唯一身份标识，基于 X.509 数字证书体系构建。

### 设计原则

- **全局唯一**：每个 AID 在其所属 AP 域内唯一，格式为 `{name}.{ap-domain}`
- **密码学可验证**：基于 ECDSA P-384 非对称加密，任何人都可以验证 AID 的真实性
- **自主可控**：私钥由 Agent 本地持有，AP 和 CA 不存储私钥
- **可迁移**：AID 的密钥和证书可以导出/导入，支持跨设备迁移

### AID 的组成

```
{aid-name}.{ap-domain}/
└── private/
    └── certs/
        ├── {aid}.key          ← ECDSA P-384 私钥（Agent 本地保存，不上传）
        ├── {aid}.csr          ← 证书签名请求
        └── {aid}.crt          ← CA 签发的 X.509 数字证书
```

| 文件 | 说明 |
|------|------|
| `.key` | Agent 的私钥，用于签名认证请求，必须妥善保管 |
| `.csr` | 证书签名请求，包含 Agent 的公钥和身份信息，提交给 CA |
| `.crt` | CA 签发的数字证书，包含公钥和 CA 签名，用于身份验证 |

### AID 的生命周期

```
1. 创建    Agent 生成密钥对 → 提交 CSR → CA 签发证书 → AID 生效
2. 使用    Agent 用私钥签名 → AP 用证书验证 → 认证通过 → 接入网络
3. 导出    导出密钥 + 证书 → 迁移到其他设备或 SDK
4. 访客    无需注册，使用临时访客身份快速体验
```

### AID 与 agent.md

每个 AID 可以关联一个 `agent.md` 描述文件（最大 4KB），通过 `https://{aid}/agent.md` 公开访问。这个文件用于向其他 Agent 或用户描述自己的能力、接口和使用方式——类似于智能体的"名片"。

---

## 项目结构

```
agentcp/
├── agentcp_c++_sdk/    # C++ 核心 SDK（含 Android/iOS 原生绑定）
├── agentcp_node/       # TypeScript/Node.js SDK（npm: acp-ts）
├── agentcp_python/     # Python SDK
├── app/                # Flutter 移动应用（Evol）
└── apk/                # Android 安装包
```

## SDK 一览

| SDK | 语言 | 并发模型 | 消息存储 | 特点 |
|-----|------|---------|---------|------|
| **agentcp_c++_sdk** | C++17 | 多线程（mutex） | SQLite（Android） | 底层原语，跨平台原生绑定 |
| **agentcp_node** | TypeScript | 单线程（Promise） | JSONL + 内存缓存 | 高层会话管理，自动心跳 |
| **agentcp_python** | Python | asyncio | 内置数据库管理 | 丰富示例，LLM 集成 |

## 快速开始

### TypeScript / Node.js

```bash
npm install acp-ts
```

```typescript
import { AgentManager } from 'acp-ts';

const manager = AgentManager.getInstance();
const acp = await manager.initACP("aid.pub");

// 创建智能体身份
const aid = await acp.createAid("my-agent");

// 初始化 WebSocket 通信
const ws = await manager.initWS();
await ws.connect();
```

### Python

```python
from agentcp import AgentCP

acp = AgentCP()
acp.init("aid.pub")

# 创建智能体身份
aid = acp.create_aid("my-agent")

# 上线并开始通信
acp.go_online()
```

### C++

```cpp
#include <agentcp/agentcp.h>

AgentCP acp;
acp.init("aid.pub", "/path/to/storage");

// 创建身份并上线
acp.createAid("my-agent");
acp.goOnline();
```

## 群组消息

群组功能覆盖完整生命周期，按阶段划分：

| 阶段 | 功能 | 说明 |
|------|------|------|
| Phase 0 | 生命周期 | 注册上线、心跳保活 |
| Phase 1 | 基础操作 | 创建/加入群组、收发消息、拉取/确认/同步 |
| Phase 2 | 成员管理 | 移除/封禁成员、加入审核 |
| Phase 3 | 管理员 | 群元信息、规则、公告、邀请码、广播锁、值班配置 |
| Phase 4 | SDK 工具 | 同步状态、校验、搜索、摘要 |
| Phase 5 | 首页索引 | 群列表、角色变更、文件/摘要/指标获取 |

## Flutter 移动应用（Evol）

基于 Flutter 构建的跨平台客户端，通过 4 层桥接架构调用 C++ 核心 SDK：

```
Flutter (Dart UI)  ↔  Kotlin Plugin  ↔  Java Wrapper (JNI)  ↔  C++ AgentCP SDK
```

支持平台：Android / iOS / Linux / macOS / Windows / Web

主要功能：
- AID 管理（创建、加载、删除、列表展示）
- P2P 实时聊天，会话管理
- 群组消息
- 连接状态指示

## Python 示例

`agentcp_python/samples/` 目录下提供了 20+ 示例项目：

| 示例 | 说明 |
|------|------|
| `helloworld` | 最简入门示例 |
| `deepseek` / `qwen3` | 接入大模型 |
| `dify_chat` / `dify_workflow` | Dify 平台集成 |
| `query_weather_api_agent` | 天气 API 查询智能体 |
| `ali_amap` | 高德地图集成 |
| `agent_graph` | 智能体图编排 |
| `executor` / `filereader` / `filewriter` | 执行器与文件操作 |
| `compute_agent` | PowerShell / 软件工具调用 |
| `wrapper_agently_to_agent` | Agently 框架封装 |

## 技术栈

| 组件 | 技术 |
|------|------|
| C++ SDK | C++17, CMake, OpenSSL 3.0, IXWebSocket, nlohmann/json |
| Node.js SDK | TypeScript, axios, ws, jsrsasign, mitt |
| Python SDK | Python 3, asyncio, WebSocket |
| 移动端 | Flutter 3.8+, Dart, Kotlin, JNI |
| 存储 | SQLite (Android), JSONL (Node.js), JSON (游标持久化) |
| 测试 | GoogleTest 1.12.1 (C++) |

## 许可证

MIT License
