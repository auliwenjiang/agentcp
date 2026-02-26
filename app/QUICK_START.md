# AgentCP SDK 快速集成指南

## 当前状态

✅ **已完成**：
- Flutter MethodChannel 封装
- Android 原生插件实现
- 完整的 UI 管理界面
- 所有 API 方法封装

⚠️ **待完成**：
- 集成真实的 AgentCP AAR 文件
- 替换模拟代码为真实 SDK 调用

## 快速开始

### 第一步：添加 AgentCP AAR

选择以下任一方式：

**方式 A：本地 AAR 文件**

1. 复制 AAR 文件：
   ```bash
   copy "H:\project\evol_main\evol_app\agentcp-so\android\build\outputs\aar\agentcp-android-release.aar" "H:\project\evol_main\evol_app\evol\android\app\libs\"
   ```

2. 编辑 `android/app/build.gradle.kts`，在 `dependencies` 块末尾添加：
   ```kotlin
   dependencies {
       // ... 现有依赖 ...
       implementation(files("libs/agentcp-android-release.aar"))
   }
   ```

**方式 B：本地 Maven 仓库**

1. 编辑 `android/build.gradle.kts`，在 `allprojects.repositories` 块中添加：
   ```kotlin
   allprojects {
       repositories {
           google()
           mavenCentral()
           maven {
               url = uri("H:/project/evol_main/evol_app/agentcp-so/android/build/repo")
           }
       }
   }
   ```

2. 编辑 `android/app/build.gradle.kts`，在 `dependencies` 块末尾添加：
   ```kotlin
   dependencies {
       // ... 现有依赖 ...
       implementation("com.agentcp:agentcp-sdk:0.1.0")
   }
   ```

### 第二步：更新 AgentCPPlugin.kt

打开文件：`android/app/src/main/kotlin/com/example/evol/AgentCPPlugin.kt`

#### 1. 添加导入（文件顶部）

```kotlin
import com.agentcp.AgentCP
import com.agentcp.AgentID
import com.agentcp.Result as AgentResult
import com.agentcp.AgentState
import com.agentcp.LogLevel
import com.agentcp.AgentCPException
```

#### 2. 添加成员变量（类中）

在 `AgentCPPlugin` 类中，找到这一行：
```kotlin
private var currentAid: String? = null
```

在其下方添加：
```kotlin
private var currentAgent: AgentID? = null
```

#### 3. 替换关键方法

**initialize 方法**（约第 65 行）：

替换：
```kotlin
// TODO: 替换为真实的 AgentCP SDK 调用
isInitialized = true
```

为：
```kotlin
val sdk = AgentCP.getInstance()
val r = sdk.initialize()
if (!r.ok()) {
    android.os.Handler(context.mainLooper).post {
        result.error("INIT_FAILED", r.message, r.context)
    }
    return@execute
}
isInitialized = true
```

**setBaseUrls 方法**（约第 95 行）：

替换：
```kotlin
// TODO: 替换为真实的 AgentCP SDK 调用
```

为：
```kotlin
val sdk = AgentCP.getInstance()
val r = sdk.setBaseUrls(caBaseUrl, apBaseUrl)
if (!r.ok()) {
    android.os.Handler(context.mainLooper).post {
        result.error("SET_URLS_FAILED", r.message, r.context)
    }
    return@execute
}
```

**setStoragePath 方法**（约第 130 行）：

替换：
```kotlin
// TODO: 替换为真实的 AgentCP SDK 调用
```

为：
```kotlin
val sdk = AgentCP.getInstance()
val r = sdk.setStoragePath(path)
if (!r.ok()) {
    android.os.Handler(context.mainLooper).post {
        result.error("SET_PATH_FAILED", r.message, r.context)
    }
    return@execute
}
```

**setLogLevel 方法**（约第 165 行）：

替换：
```kotlin
// TODO: 替换为真实的 AgentCP SDK 调用
```

为：
```kotlin
val logLevel = when (level.lowercase()) {
    "error" -> LogLevel.Error
    "warn" -> LogLevel.Warn
    "info" -> LogLevel.Info
    "debug" -> LogLevel.Debug
    "trace" -> LogLevel.Trace
    else -> LogLevel.Info
}
AgentCP.getInstance().setLogLevel(logLevel)
```

**createAID 方法**（约第 200 行）：

替换：
```kotlin
// TODO: 替换为真实的 AgentCP SDK 调用
currentAid = aid
```

为：
```kotlin
val sdk = AgentCP.getInstance()
currentAgent = sdk.createAID(aid, password)
currentAid = currentAgent?.getAID()
```

**loadAID 方法**（约第 240 行）：

替换：
```kotlin
// TODO: 替换为真实的 AgentCP SDK 调用
currentAid = aid
```

为：
```kotlin
val sdk = AgentCP.getInstance()
currentAgent = sdk.loadAID(aid)
currentAid = currentAgent?.getAID()
```

**deleteAID 方法**（约第 275 行）：

替换：
```kotlin
// TODO: 替换为真实的 AgentCP SDK 调用
```

为：
```kotlin
val sdk = AgentCP.getInstance()
val r = sdk.deleteAID(aid)
if (!r.ok()) {
    android.os.Handler(context.mainLooper).post {
        result.error("DELETE_AID_FAILED", r.message, r.context)
    }
    return@execute
}
```

**listAIDs 方法**（约第 310 行）：

替换：
```kotlin
// TODO: 替换为真实的 AgentCP SDK 调用
val aids = if (currentAid != null) listOf(currentAid) else emptyList<String>()
```

为：
```kotlin
val sdk = AgentCP.getInstance()
val aids = sdk.listAIDs().toList()
```

**online 方法**（约第 345 行）：

替换：
```kotlin
// TODO: 替换为真实的 AgentCP SDK 调用
isOnline = true
```

为：
```kotlin
val r = currentAgent!!.online()
if (!r.ok()) {
    android.os.Handler(context.mainLooper).post {
        result.error("ONLINE_FAILED", r.message, r.context)
    }
    return@execute
}
isOnline = true
```

**offline 方法**（约第 380 行）：

替换：
```kotlin
// TODO: 替换为真实的 AgentCP SDK 调用
```

为：
```kotlin
currentAgent?.offline()
```

**isOnline 方法**（约第 410 行）：

替换：
```kotlin
// TODO: 替换为真实的 AgentCP SDK 调用
```

为：
```kotlin
val online = currentAgent?.isOnline() ?: false
```

并将返回值改为：
```kotlin
result.success(mapOf(
    "success" to true,
    "isOnline" to online
))
```

**getState 方法**（约第 425 行）：

替换：
```kotlin
// TODO: 替换为真实的 AgentCP SDK 调用
val state = when {
    currentAid == null -> "Offline"
    isOnline -> "Online"
    else -> "Offline"
}
```

为：
```kotlin
val state = currentAgent?.getState()?.toString() ?: "Offline"
```

**getVersion 方法**（约第 445 行）：

替换：
```kotlin
// TODO: 替换为真实的 AgentCP SDK 调用
val version = "0.1.0"
```

为：
```kotlin
val version = AgentCP.getInstance().getVersion()
```

**shutdown 方法**（约第 465 行）：

替换：
```kotlin
// TODO: 替换为真实的 AgentCP SDK 调用
```

为：
```kotlin
currentAgent?.close()
currentAgent = null
AgentCP.getInstance().shutdown()
```

### 第三步：同步和构建

```bash
cd H:\project\evol_main\evol_app\evol
flutter clean
flutter pub get
flutter run
```

## 验证集成

运行应用后：

1. ✅ 点击"进入 AgentCP 管理"
2. ✅ 输入服务器地址并初始化
3. ✅ 创建一个 AID
4. ✅ 点击"上线"按钮
5. ✅ 查看状态是否变为"Online"

## 常见问题

### Q: 编译错误 "Unresolved reference: AgentCP"

**A**: AAR 未正确添加，检查：
- AAR 文件是否存在于 `android/app/libs/` 目录
- `build.gradle.kts` 是否正确添加依赖
- 运行 `flutter clean` 后重新构建

### Q: 运行时错误 "UnsatisfiedLinkError"

**A**: Native 库加载失败，检查：
- AAR 中是否包含 .so 文件
- 设备架构是否支持（查看 AAR 中的 jniLibs 目录）

### Q: 初始化失败

**A**: 检查：
- 服务器地址是否正确
- 网络权限是否已添加到 AndroidManifest.xml
- 查看 Logcat 日志获取详细错误

## 完整文件位置

- **Android 插件**: `android/app/src/main/kotlin/com/example/evol/AgentCPPlugin.kt`
- **Flutter 服务**: `lib/services/agentcp_service.dart`
- **UI 页面**: `lib/pages/agentcp_page.dart`
- **主入口**: `lib/main.dart`

## 下一步

集成完成后，你可以：

1. 添加更多 AgentCP 功能（消息收发、文件传输等）
2. 优化 UI 界面
3. 添加状态持久化
4. 实现自动重连机制

## 技术支持

如遇问题，请参考：
- [完整文档](README_AGENTCP.md)
- [AgentCP SDK 接入指南](H:\project\evol_main\evol_app\agentcp-so\android\INTEGRATION_GUIDE.md)
