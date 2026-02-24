# Evol - AgentCP Flutter App

基于 Flutter 的 AgentCP 客户端，通过 MethodChannel 桥接 C++ AgentCP SDK，提供 AID 管理和端到端聊天功能。

## 架构

```
Flutter (Dart UI)
  ↕ MethodChannel
Kotlin Plugin (AgentCPPlugin.kt)
  ↕ Java API
Java Wrapper (AgentID.java + Callback Interfaces)
  ↕ JNI
C++ AgentCP SDK (agentcp_core)
```

## 项目状态

### 已完成

**Page 1 — AID 管理页面** (`agentcp_page.dart`)
- SDK 初始化、服务器地址/存储路径/日志级别配置
- AID 创建（名称 + AP 域名）、加载、删除
- AID 列表展示，点击选择并上线
- 上线后注册原生回调（setHandlers），显示"进入聊天"按钮
- 下线操作

**Page 2 — 聊天页面** (`chat_page.dart`)
- 会话列表（横向 ChoiceChip，点击切换）
- 消息气泡区域（发送蓝色右对齐，接收白色左对齐，显示发送者 AID）
- 文本输入框 + 发送按钮
- "Connect to Peer" 对话框：输入对方 AID → createSession + inviteAgent
- 收到 invite 自动 joinSession 并添加会话
- 状态指示灯（绿色在线 / 灰色离线）

**4 层桥接实现**

| 层 | 文件 | 内容 |
|---|---|---|
| JNI/C++ | `agentcp-so/android/.../agentcp_jni.cpp` | JNI_OnLoad、9 个 JNI 函数、JSON 序列化 |
| Java | `agentcp-so/android/.../AgentID.java` | 9 个公开方法 + 9 个 native 声明 |
| Java | `agentcp-so/android/.../MessageCallback.java` | 消息回调接口 |
| Java | `agentcp-so/android/.../InviteCallback.java` | 邀请回调接口 |
| Java | `agentcp-so/android/.../StateChangeCallback.java` | 状态变更回调接口 |
| Kotlin | `acp_app/.../AgentCPPlugin.kt` | 7 个新 method handler + 回调转发到 Flutter |
| Kotlin | `acp_app/.../MainActivity.kt` | 传递 MethodChannel 给 plugin |
| Dart | `acp_app/lib/services/agentcp_service.dart` | 反向 MethodCallHandler + 7 个新方法 + 数据类 |
| Dart | `acp_app/lib/main.dart` | initCallbackHandler + /chat 路由 |
| Dart | `acp_app/lib/pages/agentcp_page.dart` | 上线后调 setHandlers + "进入聊天"按钮 |
| Dart | `acp_app/lib/pages/chat_page.dart` | 完整聊天 UI |

### 待验证

- 需要 `flutter clean && flutter build apk --debug` 全量重编译（原生层变更不支持热重载）
- 端到端消息收发（需两台设备或模拟器分别登录不同 AID）

## 项目结构

```
acp_app/
├── lib/
│   ├── main.dart                          # 入口，初始化回调，路由
│   ├── services/
│   │   └── agentcp_service.dart           # SDK 服务层 + 数据类
│   └── pages/
│       ├── agentcp_page.dart              # AID 管理页面
│       └── chat_page.dart                 # 聊天页面
├── android/app/src/main/kotlin/com/example/evol/
│   ├── MainActivity.kt                    # FlutterActivity
│   └── AgentCPPlugin.kt                   # MethodChannel 处理
└── pubspec.yaml

agentcp-so/                                # C++ SDK + Android 绑定
├── core/
│   ├── include/agentcp/                   # 公开头文件
│   │   ├── agentcp.h                      # AgentCP / AgentID / SessionManager
│   │   ├── types.h                        # Block / Message / SessionInfo / 回调类型
│   │   └── result.h                       # Result
│   └── src/                               # 实现 + third_party/json.hpp
├── android/
│   ├── CMakeLists.txt                     # JNI 构建配置
│   └── src/main/
│       ├── cpp/agentcp_jni.cpp            # JNI 实现
│       └── java/com/agentcp/
│           ├── AgentCP.java               # SDK 单例
│           ├── AgentID.java               # Agent 实例
│           ├── MessageCallback.java       # 消息回调接口
│           ├── InviteCallback.java        # 邀请回调接口
│           └── StateChangeCallback.java   # 状态变更回调接口
```

## 数据流

### 发送消息
```
用户输入 → ChatPage._sendMessage()
  → AgentCPService.sendMessage(sessionId, text)
    → MethodChannel "sendMessage"
      → AgentCPPlugin.sendMessage()
        → AgentID.sendMessage(sessionId, blocksJson)
          → JNI nativeSendMessage → JsonToBlocks → AgentID::SendMessage()
```

### 接收消息
```
C++ SDK 收到消息 → MessageHandler lambda
  → JNI AttachCurrentThread → Java MessageCallback.onMessage()
    → Kotlin: methodChannel.invokeMethod("onMessage", args) [主线程]
      → Dart: AgentCPService.initCallbackHandler 解析 → onMessageReceived
        → ChatPage setState → 消息气泡渲染
```

## 构建

```bash
# 全量重编译（修改原生代码后必须执行）
flutter clean && flutter build apk --debug

# 仅 Dart 变更可用热重载
flutter run
```

## API 参考

### AgentCPService 方法

| 方法 | 说明 |
|---|---|
| `initialize()` | 初始化 SDK |
| `setBaseUrls(ca, ap)` | 设置 CA/AP 服务器地址 |
| `setStoragePath(path?)` | 设置本地存储路径 |
| `setLogLevel(level)` | 设置日志级别 |
| `createAID(aid, password)` | 创建 AID |
| `loadAID(aid, password)` | 加载已有 AID |
| `deleteAID(aid)` | 删除 AID |
| `listAIDs()` | 列出所有本地 AID |
| `online()` | 上线 |
| `offline()` | 下线 |
| `isOnline()` | 查询在线状态 |
| `getState()` | 获取连接状态 |
| `getCurrentAID()` | 获取当前 AID |
| `setHandlers()` | 注册原生回调 |
| `createSession(members)` | 创建会话 |
| `inviteAgent(sessionId, agentId)` | 邀请 Agent 加入会话 |
| `joinSession(sessionId)` | 加入会话 |
| `getActiveSessions()` | 获取活跃会话列表 |
| `getSessionInfo(sessionId)` | 获取会话详情 (JSON) |
| `sendMessage(sessionId, text)` | 发送文本消息 |

### 回调

| 回调 | 触发时机 |
|---|---|
| `onMessageReceived(ChatMessage)` | 收到消息 |
| `onInviteReceived(sessionId, inviterId)` | 收到会话邀请 |
| `onStateChanged(oldState, newState)` | 连接状态变更 |

## 技术栈

- Flutter / Dart 3.8+
- Kotlin 2.1
- C++17 (AgentCP SDK)
- nlohmann/json 3.11.3
- IXWebSocket 11.4.5
