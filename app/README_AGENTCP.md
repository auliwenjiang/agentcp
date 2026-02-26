# AgentCP SDK Flutter 集成

本项目已完成 AgentCP SDK 的 Flutter 封装，提供了完整的 AID 申请、注册和上线功能。

## 项目结构

```
evol/
├── android/
│   └── app/src/main/kotlin/com/example/evol/
│       ├── MainActivity.kt              # 主 Activity，注册 MethodChannel
│       └── AgentCPPlugin.kt            # AgentCP SDK 的 Flutter 插件封装
├── lib/
│   ├── main.dart                       # 应用入口
│   ├── services/
│   │   └── agentcp_service.dart       # AgentCP 服务类（Dart 侧）
│   └── pages/
│       └── agentcp_page.dart          # AgentCP 管理页面
└── README_AGENTCP.md                   # 本文档
```

## 功能特性

### 已实现功能

1. **SDK 初始化**
   - 设置 CA/AP 服务器地址
   - 设置本地存储路径
   - 设置日志级别
   - SDK 初始化

2. **AID 管理**
   - 创建新的 Agent ID
   - 加载已有的 Agent ID
   - 删除 Agent ID
   - 列出所有 Agent ID

3. **在线状态管理**
   - Agent 上线
   - Agent 下线
   - 查询在线状态
   - 获取当前状态

4. **UI 界面**
   - 直观的管理界面
   - 实时状态显示
   - AID 列表管理
   - 错误提示

## 集成真实的 AgentCP SDK

当前代码使用模拟实现，要集成真实的 AgentCP SDK，请按以下步骤操作：

### 1. 添加 AAR 依赖

#### 方式一：本地 AAR 文件

1. 将构建好的 `agentcp-android-release.aar` 复制到 `android/app/libs/` 目录

2. 修改 `android/app/build.gradle.kts`，在 `dependencies` 块中添加：

```kotlin
dependencies {
    implementation(files("libs/agentcp-android-release.aar"))
}
```

#### 方式二：本地 Maven 仓库

1. 修改 `android/settings.gradle.kts`，在 `repositories` 块中添加：

```kotlin
dependencyResolutionManagement {
    repositories {
        google()
        mavenCentral()
        // 添加本地 Maven 仓库
        maven {
            url = uri("H:/project/evol_main/evol_app/agentcp-so/android/build/repo")
        }
    }
}
```

2. 修改 `android/app/build.gradle.kts`，在 `dependencies` 块中添加：

```kotlin
dependencies {
    implementation("com.agentcp:agentcp-sdk:0.1.0")
}
```

### 2. 更新 AgentCPPlugin.kt

打开 `android/app/src/main/kotlin/com/example/evol/AgentCPPlugin.kt`，将所有标记为 `// TODO` 的模拟代码替换为真实的 SDK 调用。

#### 示例：初始化方法

**当前（模拟）：**
```kotlin
private fun initialize(call: MethodCall, result: Result) {
    executor.execute {
        try {
            // TODO: 替换为真实的 AgentCP SDK 调用
            isInitialized = true
            Log.i(TAG, "SDK initialized")
            // ...
        }
    }
}
```

**替换为（真实）：**
```kotlin
private fun initialize(call: MethodCall, result: Result) {
    executor.execute {
        try {
            val sdk = AgentCP.getInstance()
            val r = sdk.initialize()
            if (!r.ok()) {
                android.os.Handler(context.mainLooper).post {
                    result.error("INIT_FAILED", r.message, r.context)
                }
                return@execute
            }

            isInitialized = true
            Log.i(TAG, "SDK initialized")

            android.os.Handler(context.mainLooper).post {
                result.success(mapOf(
                    "success" to true,
                    "message" to "SDK initialized successfully"
                ))
            }
        } catch (e: Exception) {
            Log.e(TAG, "Initialize failed", e)
            android.os.Handler(context.mainLooper).post {
                result.error("INIT_FAILED", e.message, null)
            }
        }
    }
}
```

#### 需要替换的方法

在 `AgentCPPlugin.kt` 中，以下方法需要替换为真实的 SDK 调用：

1. `initialize()` - SDK 初始化
2. `setBaseUrls()` - 设置服务器地址
3. `setStoragePath()` - 设置存储路径
4. `setLogLevel()` - 设置日志级别
5. `createAID()` - 创建 AID
6. `loadAID()` - 加载 AID
7. `deleteAID()` - 删除 AID
8. `listAIDs()` - 列出 AID
9. `online()` - 上线
10. `offline()` - 下线
11. `isOnline()` - 检查在线状态
12. `getState()` - 获取状态
13. `getVersion()` - 获取版本
14. `shutdown()` - 关闭 SDK

### 3. 添加必要的导入

在 `AgentCPPlugin.kt` 文件顶部添加 AgentCP SDK 的导入：

```kotlin
import com.agentcp.AgentCP
import com.agentcp.AgentID
import com.agentcp.Result
import com.agentcp.AgentState
import com.agentcp.LogLevel
import com.agentcp.AgentCPException
```

### 4. 管理 AgentID 实例

在 `AgentCPPlugin` 类中添加成员变量来保存当前的 AgentID 实例：

```kotlin
class AgentCPPlugin(private val context: Context) : MethodCallHandler {
    // ...
    private var currentAgent: AgentID? = null

    // 在需要的地方使用 currentAgent
    private fun online(result: Result) {
        if (currentAgent == null) {
            result.error("NO_AGENT", "No agent loaded", null)
            return
        }

        executor.execute {
            try {
                val r = currentAgent!!.online()
                // ...
            }
        }
    }
}
```

## 使用说明

### 运行应用

```bash
cd H:\project\evol_main\evol_app\evol
flutter run
```

### 操作流程

1. **初始化 SDK**
   - 输入 CA 服务器地址（例如：`https://ca.example.com`）
   - 输入 AP 服务器地址（例如：`https://ap.example.com`）
   - 点击"初始化 SDK"按钮

2. **创建 AID**
   - 输入 Agent ID（例如：`user@example.com`）
   - 输入密码
   - 点击"创建 AID"按钮

3. **上线**
   - 创建或加载 AID 后
   - 点击"上线"按钮
   - 查看状态变为"Online"

4. **管理 AID**
   - 在 AID 列表中查看所有已创建的 AID
   - 点击"加载"按钮切换到其他 AID
   - 点击"删除"按钮删除不需要的 AID

## API 参考

### AgentCPService (Dart)

所有方法都是静态方法，返回 `Future<Map<String, dynamic>>` 或特定类型。

#### SDK 管理

- `initialize()` - 初始化 SDK
- `setBaseUrls({caBaseUrl, apBaseUrl})` - 设置服务器地址
- `setStoragePath({path})` - 设置存储路径
- `setLogLevel(level)` - 设置日志级别
- `shutdown()` - 关闭 SDK
- `getVersion()` - 获取版本

#### AID 管理

- `createAID({aid, password})` - 创建 AID
- `loadAID(aid)` - 加载 AID
- `deleteAID(aid)` - 删除 AID
- `listAIDs()` - 列出所有 AID
- `getCurrentAID()` - 获取当前 AID

#### 在线状态

- `online()` - 上线
- `offline()` - 下线
- `isOnline()` - 检查是否在线
- `getState()` - 获取当前状态

### 返回值格式

成功时：
```dart
{
  'success': true,
  'message': '操作成功',
  // 其他数据...
}
```

失败时：
```dart
{
  'success': false,
  'error': 'ERROR_CODE',
  'message': '错误信息'
}
```

## 注意事项

1. **线程安全**：所有原生 SDK 调用都在后台线程执行，结果通过主线程返回

2. **错误处理**：所有方法都包含完整的错误处理，失败时会返回详细的错误信息

3. **资源管理**：记得在应用退出时调用 `shutdown()` 释放资源

4. **权限配置**：如果需要网络访问，确保在 `AndroidManifest.xml` 中添加：
   ```xml
   <uses-permission android:name="android.permission.INTERNET" />
   <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
   ```

5. **最低 SDK 版本**：确保 `minSdk` 至少为 21（Android 5.0）

## 故障排除

### 问题：找不到 AgentCP 类

**解决方案**：
- 确认 AAR 文件已正确添加到项目
- 检查 Gradle 同步是否成功
- 清理并重新构建项目：`flutter clean && flutter pub get`

### 问题：JNI 错误

**解决方案**：
- 确认 AAR 中包含所需的 .so 文件
- 检查设备架构是否支持（armeabi-v7a, arm64-v8a, x86_64）

### 问题：初始化失败

**解决方案**：
- 检查服务器地址是否正确
- 确认网络连接正常
- 查看 Logcat 日志获取详细错误信息

## 参考文档

- [AgentCP Android SDK 接入指南](H:\project\evol_main\evol_app\agentcp-so\android\INTEGRATION_GUIDE.md)
- [Flutter Platform Channels](https://docs.flutter.dev/development/platform-integration/platform-channels)

## 版本信息

- Flutter SDK: 3.x
- Kotlin: 2.1.0
- Android Gradle Plugin: 8.7.3
- AgentCP SDK: 0.1.0

## 许可证

根据项目许可证使用。
