# AgentCP Flutter 项目结构

## 完整目录结构

```
evol/
│
├── android/                                    # Android 原生代码
│   ├── app/
│   │   ├── src/
│   │   │   └── main/
│   │   │       ├── kotlin/com/example/evol/
│   │   │       │   ├── MainActivity.kt         # ✅ 主 Activity（已修改）
│   │   │       │   └── AgentCPPlugin.kt        # ✅ AgentCP 插件（新建）
│   │   │       └── AndroidManifest.xml
│   │   ├── build.gradle.kts                    # ⚠️ 需要添加 AAR 依赖
│   │   └── libs/                               # ⚠️ 放置 AAR 文件的目录
│   │       └── agentcp-android-release.aar     # ⏳ 待添加
│   ├── build.gradle.kts                        # ⚠️ 可选：添加 Maven 仓库
│   └── settings.gradle.kts
│
├── lib/                                        # Flutter Dart 代码
│   ├── main.dart                               # ✅ 应用入口（已修改）
│   ├── services/
│   │   └── agentcp_service.dart                # ✅ AgentCP 服务类（新建）
│   └── pages/
│       └── agentcp_page.dart                   # ✅ AgentCP 管理页面（新建）
│
├── test/                                       # 测试代码
│   └── widget_test.dart
│
├── pubspec.yaml                                # Flutter 依赖配置
│
├── README_AGENTCP.md                           # ✅ 完整文档（新建）
├── QUICK_START.md                              # ✅ 快速开始指南（新建）
├── BUILD_CONFIG.md                             # ✅ 构建配置说明（新建）
├── SUMMARY.md                                  # ✅ 项目总结（新建）
└── PROJECT_STRUCTURE.md                        # ✅ 本文档（新建）
```

## 文件说明

### ✅ 已完成的文件

#### Android 原生层

1. **MainActivity.kt**
   - 路径: `android/app/src/main/kotlin/com/example/evol/MainActivity.kt`
   - 状态: ✅ 已修改
   - 功能: 注册 MethodChannel，初始化 AgentCPPlugin
   - 代码行数: ~30 行

2. **AgentCPPlugin.kt**
   - 路径: `android/app/src/main/kotlin/com/example/evol/AgentCPPlugin.kt`
   - 状态: ✅ 新建完成
   - 功能: 封装 AgentCP SDK 的所有 API
   - 代码行数: ~500 行
   - 包含方法:
     - SDK 管理: initialize, setBaseUrls, setStoragePath, setLogLevel, shutdown, getVersion
     - AID 管理: createAID, loadAID, deleteAID, listAIDs, getCurrentAID
     - 状态管理: online, offline, isOnline, getState

#### Flutter 应用层

3. **main.dart**
   - 路径: `lib/main.dart`
   - 状态: ✅ 已修改
   - 功能: 应用入口，导航到 AgentCP 管理页面
   - 代码行数: ~60 行

4. **agentcp_service.dart**
   - 路径: `lib/services/agentcp_service.dart`
   - 状态: ✅ 新建完成
   - 功能: Flutter 侧的 AgentCP 服务封装
   - 代码行数: ~250 行
   - 提供方法:
     - 所有原生方法的 Dart 封装
     - 统一的错误处理
     - 类型安全的 API

5. **agentcp_page.dart**
   - 路径: `lib/pages/agentcp_page.dart`
   - 状态: ✅ 新建完成
   - 功能: AgentCP 管理界面
   - 代码行数: ~600 行
   - UI 组件:
     - SDK 信息卡片
     - 初始化配置表单
     - AID 创建表单
     - 在线状态控制
     - AID 列表管理

#### 文档

6. **README_AGENTCP.md**
   - 状态: ✅ 新建完成
   - 内容: 完整的项目文档、API 参考、使用说明

7. **QUICK_START.md**
   - 状态: ✅ 新建完成
   - 内容: 快速集成指南、分步骤操作说明

8. **BUILD_CONFIG.md**
   - 状态: ✅ 新建完成
   - 内容: Gradle 配置示例、三种集成方式

9. **SUMMARY.md**
   - 状态: ✅ 新建完成
   - 内容: 项目总结、技术架构、待办事项

10. **PROJECT_STRUCTURE.md**
    - 状态: ✅ 本文档
    - 内容: 项目结构说明

### ⚠️ 需要修改的文件

1. **android/app/build.gradle.kts**
   - 需要添加: AgentCP AAR 依赖
   - 参考: BUILD_CONFIG.md

2. **android/build.gradle.kts** (可选)
   - 需要添加: Maven 仓库配置
   - 参考: BUILD_CONFIG.md

### ⏳ 待添加的文件

1. **android/app/libs/agentcp-android-release.aar**
   - 来源: `H:\project\evol_main\evol_app\agentcp-so\android\build\outputs\aar\`
   - 操作: 复制到项目

## 代码流程图

### 1. 初始化流程

```
用户点击"初始化 SDK"
    ↓
AgentCPPage._initializeSDK()
    ↓
AgentCPService.setBaseUrls()
    ↓
MethodChannel.invokeMethod('setBaseUrls')
    ↓
AgentCPPlugin.setBaseUrls()
    ↓
AgentCP.getInstance().setBaseUrls()  ← 待集成
    ↓
返回结果到 Flutter
    ↓
更新 UI 状态
```

### 2. 创建 AID 流程

```
用户输入 AID 和密码
    ↓
AgentCPPage._createAID()
    ↓
AgentCPService.createAID()
    ↓
MethodChannel.invokeMethod('createAID')
    ↓
AgentCPPlugin.createAID()
    ↓
AgentCP.getInstance().createAID()  ← 待集成
    ↓
返回 AgentID 对象
    ↓
更新 UI，显示成功消息
```

### 3. 上线流程

```
用户点击"上线"
    ↓
AgentCPPage._goOnline()
    ↓
AgentCPService.online()
    ↓
MethodChannel.invokeMethod('online')
    ↓
AgentCPPlugin.online()
    ↓
currentAgent.online()  ← 待集成
    ↓
返回结果
    ↓
刷新状态，显示"Online"
```

## 数据流向

```
┌─────────────────────────────────────────────────────────┐
│                    Flutter UI Layer                      │
│                                                           │
│  ┌──────────────┐         ┌──────────────┐              │
│  │ AgentCPPage  │────────▶│ User Actions │              │
│  │   (Widget)   │         │   (Buttons)  │              │
│  └──────┬───────┘         └──────────────┘              │
│         │                                                 │
│         │ setState()                                      │
│         ▼                                                 │
│  ┌──────────────┐                                        │
│  │  UI State    │                                        │
│  │  Variables   │                                        │
│  └──────────────┘                                        │
└────────────┬────────────────────────────────────────────┘
             │
             │ AgentCPService.method()
             ▼
┌─────────────────────────────────────────────────────────┐
│                  Flutter Service Layer                   │
│                                                           │
│  ┌──────────────────────────────────────────────────┐   │
│  │           AgentCPService (Static Class)          │   │
│  │                                                   │   │
│  │  • initialize()      • createAID()               │   │
│  │  • setBaseUrls()     • loadAID()                 │   │
│  │  • online()          • offline()                 │   │
│  │  • ...                                           │   │
│  └────────────────────┬─────────────────────────────┘   │
└───────────────────────┼─────────────────────────────────┘
                        │
                        │ MethodChannel.invokeMethod()
                        ▼
┌─────────────────────────────────────────────────────────┐
│                  Platform Channel                        │
│                                                           │
│  ┌──────────────────────────────────────────────────┐   │
│  │     MethodChannel('com.example.evol/agentcp')    │   │
│  └────────────────────┬─────────────────────────────┘   │
└───────────────────────┼─────────────────────────────────┘
                        │
                        │ onMethodCall()
                        ▼
┌─────────────────────────────────────────────────────────┐
│                Android Native Layer                      │
│                                                           │
│  ┌──────────────────────────────────────────────────┐   │
│  │              AgentCPPlugin (Kotlin)              │   │
│  │                                                   │   │
│  │  • MethodCallHandler                             │   │
│  │  • Background Thread Executor                    │   │
│  │  • Error Handling                                │   │
│  └────────────────────┬─────────────────────────────┘   │
│                       │                                   │
│                       │ SDK API Calls                     │
│                       ▼                                   │
│  ┌──────────────────────────────────────────────────┐   │
│  │           AgentCP SDK (C++ via JNI)              │   │
│  │                                                   │   │
│  │  • AgentCP.getInstance()                         │   │
│  │  • AgentID objects                               │   │
│  │  • Native operations                             │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

## 关键接口

### MethodChannel 方法列表

| 方法名 | 参数 | 返回值 | 说明 |
|--------|------|--------|------|
| `initialize` | - | `Map` | 初始化 SDK |
| `setBaseUrls` | `caBaseUrl`, `apBaseUrl` | `Map` | 设置服务器地址 |
| `setStoragePath` | `path` | `Map` | 设置存储路径 |
| `setLogLevel` | `level` | `Map` | 设置日志级别 |
| `createAID` | `aid`, `password` | `Map` | 创建 AID |
| `loadAID` | `aid` | `Map` | 加载 AID |
| `deleteAID` | `aid` | `Map` | 删除 AID |
| `listAIDs` | - | `Map` | 列出所有 AID |
| `online` | - | `Map` | 上线 |
| `offline` | - | `Map` | 下线 |
| `isOnline` | - | `Map` | 检查在线状态 |
| `getState` | - | `Map` | 获取当前状态 |
| `getCurrentAID` | - | `Map` | 获取当前 AID |
| `getVersion` | - | `Map` | 获取版本 |
| `shutdown` | - | `Map` | 关闭 SDK |

## 下一步操作

### 1. 集成 AAR（必需）

```bash
# 复制 AAR 文件
copy "H:\project\evol_main\evol_app\agentcp-so\android\build\outputs\aar\agentcp-android-release.aar" ^
     "H:\project\evol_main\evol_app\evol\android\app\libs\"
```

### 2. 修改 Gradle 配置（必需）

参考 `BUILD_CONFIG.md` 修改 `android/app/build.gradle.kts`

### 3. 更新 Kotlin 代码（必需）

参考 `QUICK_START.md` 替换 `AgentCPPlugin.kt` 中的所有 TODO 代码

### 4. 测试运行（必需）

```bash
flutter clean
flutter pub get
flutter run
```

## 文件依赖关系

```
main.dart
  └─> agentcp_page.dart
        └─> agentcp_service.dart
              └─> MethodChannel
                    └─> MainActivity.kt
                          └─> AgentCPPlugin.kt
                                └─> AgentCP SDK (AAR)
```

## 总结

- ✅ **已完成**: 所有 Flutter 和 Kotlin 代码
- ✅ **已完成**: 所有文档
- ⏳ **待完成**: 集成真实的 AgentCP AAR
- ⏳ **待完成**: 替换模拟代码为真实 SDK 调用

**预计完成时间**: 1-2 小时（仅需按照 QUICK_START.md 操作）
