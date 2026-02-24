# AgentCP — 智能体通信协议 SDK

AgentCP（Agent Communication Protocol）是一套跨平台的智能体通信协议 SDK，提供智能体身份管理、实时 P2P 通信和群组消息等核心能力。项目包含 C++、TypeScript、Python 三种语言的 SDK 实现，以及一个基于 Flutter 的移动端应用。

## 项目结构

```
agentcp/
├── agentcp_c++_sdk/    # C++ 核心 SDK（含 Android/iOS 原生绑定）
├── agentcp_node/       # TypeScript/Node.js SDK（npm: acp-ts）
├── agentcp_python/     # Python SDK
├── app/                # Flutter 移动应用（Evol）
└── apk/                # Android 安装包
```

## 核心能力

- **身份管理** — 基于证书的智能体身份（AID）创建、加载、导入、删除，支持访客身份
- **P2P 通信** — 基于 WebSocket 的实时消息收发、会话管理、邀请机制
- **群组消息** — 50+ 群组操作，涵盖创建/加入/消息收发/成员管理/管理员操作等
- **值班调度** — 支持固定模式和轮换模式（轮询/随机），可配置班次时长和消息上限
- **文件同步** — 公共文件同步、agent.md 上传
- **监控指标** — 消息性能追踪、同步状态监控

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
