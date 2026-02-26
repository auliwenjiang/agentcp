# AgentCP SDK 集成检查清单

## 📋 集成前检查

### 环境准备
- [ ] Flutter SDK 已安装（3.x 或更高版本）
- [ ] Android Studio 已安装
- [ ] Kotlin 插件已启用
- [ ] Android SDK 已配置
- [ ] 设备或模拟器已准备好

### 文件准备
- [ ] AgentCP AAR 文件已构建
  - 位置: `H:\project\evol_main\evol_app\agentcp-so\android\build\outputs\aar\agentcp-android-release.aar`
  - 或: `H:\project\evol_main\evol_app\agentcp-so\android\build\repo\com\agentcp\agentcp-sdk\0.1.0\`

---

## 📦 第一步：添加 AAR 依赖

### 方式 A：本地 AAR 文件（推荐用于开发）

- [ ] 创建 libs 目录
  ```bash
  mkdir "H:\project\evol_main\evol_app\evol\android\app\libs"
  ```

- [ ] 复制 AAR 文件
  ```bash
  copy "H:\project\evol_main\evol_app\agentcp-so\android\build\outputs\aar\agentcp-android-release.aar" ^
       "H:\project\evol_main\evol_app\evol\android\app\libs\"
  ```

- [ ] 修改 `android/app/build.gradle.kts`
  ```kotlin
  dependencies {
      implementation(files("libs/agentcp-android-release.aar"))
  }
  ```

### 方式 B：本地 Maven 仓库（推荐用于团队）

- [ ] 修改 `android/build.gradle.kts`
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

- [ ] 修改 `android/app/build.gradle.kts`
  ```kotlin
  dependencies {
      implementation("com.agentcp:agentcp-sdk:0.1.0")
  }
  ```

---

## 🔧 第二步：更新 Kotlin 代码

### 打开文件
- [ ] 打开 `android/app/src/main/kotlin/com/example/evol/AgentCPPlugin.kt`

### 添加导入（文件顶部）
- [ ] 添加以下导入语句：
  ```kotlin
  import com.agentcp.AgentCP
  import com.agentcp.AgentID
  import com.agentcp.Result as AgentResult
  import com.agentcp.AgentState
  import com.agentcp.LogLevel
  import com.agentcp.AgentCPException
  ```

### 添加成员变量
- [ ] 在类中添加：
  ```kotlin
  private var currentAgent: AgentID? = null
  ```

### 替换方法实现

#### SDK 管理方法

- [ ] **initialize()** - 约第 65 行
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

- [ ] **setBaseUrls()** - 约第 95 行
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

- [ ] **setStoragePath()** - 约第 130 行
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

- [ ] **setLogLevel()** - 约第 165 行
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

#### AID 管理方法

- [ ] **createAID()** - 约第 200 行
  ```kotlin
  val sdk = AgentCP.getInstance()
  currentAgent = sdk.createAID(aid, password)
  currentAid = currentAgent?.getAID()
  ```

- [ ] **loadAID()** - 约第 240 行
  ```kotlin
  val sdk = AgentCP.getInstance()
  currentAgent = sdk.loadAID(aid)
  currentAid = currentAgent?.getAID()
  ```

- [ ] **deleteAID()** - 约第 275 行
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

- [ ] **listAIDs()** - 约第 310 行
  ```kotlin
  val sdk = AgentCP.getInstance()
  val aids = sdk.listAIDs().toList()
  ```

#### 状态管理方法

- [ ] **online()** - 约第 345 行
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

- [ ] **offline()** - 约第 380 行
  ```kotlin
  currentAgent?.offline()
  ```

- [ ] **isOnline()** - 约第 410 行
  ```kotlin
  val online = currentAgent?.isOnline() ?: false
  ```
  并更新返回值：
  ```kotlin
  result.success(mapOf(
      "success" to true,
      "isOnline" to online
  ))
  ```

- [ ] **getState()** - 约第 425 行
  ```kotlin
  val state = currentAgent?.getState()?.toString() ?: "Offline"
  ```

- [ ] **getVersion()** - 约第 445 行
  ```kotlin
  val version = AgentCP.getInstance().getVersion()
  ```

- [ ] **shutdown()** - 约第 465 行
  ```kotlin
  currentAgent?.close()
  currentAgent = null
  AgentCP.getInstance().shutdown()
  ```

---

## 🔐 第三步：配置权限

### 修改 AndroidManifest.xml
- [ ] 打开 `android/app/src/main/AndroidManifest.xml`
- [ ] 添加网络权限：
  ```xml
  <uses-permission android:name="android.permission.INTERNET" />
  <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
  ```

---

## 🏗️ 第四步：构建和测试

### 清理和构建
- [ ] 清理项目
  ```bash
  cd H:\project\evol_main\evol_app\evol
  flutter clean
  ```

- [ ] 获取依赖
  ```bash
  flutter pub get
  ```

- [ ] 构建 APK（可选，用于验证）
  ```bash
  flutter build apk --debug
  ```

### 验证 AAR 集成
- [ ] 检查 APK 内容
  ```bash
  # 查看 APK 中是否包含 .so 文件
  unzip -l build/app/outputs/flutter-apk/app-debug.apk | findstr agentcp
  ```
  应该看到类似输出：
  ```
  lib/arm64-v8a/libagentcp_jni.so
  lib/armeabi-v7a/libagentcp_jni.so
  ```

---

## 🚀 第五步：运行应用

### 启动应用
- [ ] 连接设备或启动模拟器
- [ ] 运行应用
  ```bash
  flutter run
  ```

### 功能测试

#### 1. 初始化测试
- [ ] 点击"进入 AgentCP 管理"
- [ ] 输入 CA 服务器地址（如：`https://ca.example.com`）
- [ ] 输入 AP 服务器地址（如：`https://ap.example.com`）
- [ ] 点击"初始化 SDK"
- [ ] 验证：显示"SDK 初始化成功"

#### 2. 创建 AID 测试
- [ ] 输入 Agent ID（如：`test@example.com`）
- [ ] 输入密码（如：`password123`）
- [ ] 点击"创建 AID"
- [ ] 验证：显示"AID 创建成功"
- [ ] 验证：AID 列表中出现新创建的 AID

#### 3. 上线测试
- [ ] 点击"上线"按钮
- [ ] 验证：按钮变为禁用状态
- [ ] 验证：状态显示为"Online"
- [ ] 验证：显示"上线成功"消息

#### 4. 下线测试
- [ ] 点击"下线"按钮
- [ ] 验证：状态显示为"Offline"
- [ ] 验证：显示"下线成功"消息

#### 5. AID 管理测试
- [ ] 创建第二个 AID
- [ ] 验证：列表中显示两个 AID
- [ ] 点击第二个 AID 的"加载"按钮
- [ ] 验证：当前 AID 切换成功
- [ ] 点击删除按钮
- [ ] 确认删除
- [ ] 验证：AID 从列表中移除

#### 6. 状态刷新测试
- [ ] 点击右上角刷新按钮
- [ ] 验证：状态信息更新

---

## 🐛 故障排除

### 编译错误

#### 错误：Unresolved reference: AgentCP
- [ ] 检查 AAR 文件是否存在
- [ ] 检查 build.gradle.kts 配置是否正确
- [ ] 运行 `flutter clean`
- [ ] 删除 `android/.gradle` 目录
- [ ] 重新同步：`flutter pub get`

#### 错误：Duplicate class found
- [ ] 检查是否同时使用了 AAR 文件和 Maven 依赖
- [ ] 只保留一种依赖方式

### 运行时错误

#### 错误：UnsatisfiedLinkError
- [ ] 检查 AAR 中是否包含 .so 文件
- [ ] 检查设备架构是否支持
- [ ] 查看 APK 中是否包含 .so 文件

#### 错误：初始化失败
- [ ] 检查服务器地址是否正确
- [ ] 检查网络连接
- [ ] 检查网络权限是否已添加
- [ ] 查看 Logcat 日志

#### 错误：创建 AID 失败
- [ ] 检查 AID 格式是否正确
- [ ] 检查密码是否符合要求
- [ ] 查看详细错误信息

---

## 📊 验证清单

### 代码完整性
- [ ] 所有 TODO 注释已替换
- [ ] 所有导入语句已添加
- [ ] 所有成员变量已添加
- [ ] 所有方法已更新

### 配置完整性
- [ ] AAR 依赖已添加
- [ ] 网络权限已配置
- [ ] Gradle 配置正确

### 功能完整性
- [ ] SDK 初始化正常
- [ ] AID 创建成功
- [ ] 上线功能正常
- [ ] 下线功能正常
- [ ] AID 列表显示正确
- [ ] 状态更新及时
- [ ] 错误提示正确

---

## 📝 日志检查

### 查看 Logcat 日志
```bash
# 过滤 AgentCP 相关日志
adb logcat | findstr AgentCP
```

### 关键日志
- [ ] `SDK initialized` - SDK 初始化成功
- [ ] `Agent created: xxx` - AID 创建成功
- [ ] `Agent loaded: xxx` - AID 加载成功
- [ ] `Agent is now online` - 上线成功
- [ ] `Agent is now offline` - 下线成功

---

## ✅ 完成标志

当以下所有项都完成时，集成即为成功：

- [x] ✅ 代码已完成（框架）
- [ ] ⏳ AAR 已集成
- [ ] ⏳ Kotlin 代码已更新
- [ ] ⏳ 应用可以正常运行
- [ ] ⏳ 所有功能测试通过
- [ ] ⏳ 无编译错误
- [ ] ⏳ 无运行时错误

---

## 📚 参考文档

完成集成后，参考以下文档了解更多：

- [ ] [README_AGENTCP.md](README_AGENTCP.md) - 完整文档
- [ ] [QUICK_START.md](QUICK_START.md) - 快速开始
- [ ] [BUILD_CONFIG.md](BUILD_CONFIG.md) - 构建配置
- [ ] [SUMMARY.md](SUMMARY.md) - 项目总结
- [ ] [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) - 项目结构

---

## 🎯 下一步

集成完成后，可以考虑：

- [ ] 添加消息收发功能
- [ ] 实现文件传输
- [ ] 添加会话管理
- [ ] 实现状态持久化
- [ ] 优化用户界面
- [ ] 添加单元测试
- [ ] 添加集成测试
- [ ] 编写用户文档

---

**预计完成时间**: 1-2 小时

**难度等级**: ⭐⭐☆☆☆ (中等)

**建议**: 按照清单逐项完成，遇到问题参考故障排除部分
