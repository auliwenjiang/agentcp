# AgentCP Android SDK 接入指南

## 目录

1. [概述](#概述)
2. [环境要求](#环境要求)
3. [构建 AAR](#构建-aar)
4. [集成方式](#集成方式)
5. [快速开始](#快速开始)
6. [API 参考](#api-参考)
7. [错误处理](#错误处理)
8. [最佳实践](#最佳实践)
9. [常见问题](#常见问题)

---

## 概述

AgentCP SDK 是一个基于 C++ 的跨平台即时通讯客户端 SDK，提供完整的 IM 功能支持，包括：

- Agent ID (AID) 管理
- 在线/离线状态管理
- 消息收发
- 会话管理
- 文件传输
- 流式数据传输

### 架构

```
+---------------------------+
|     Your Android App      |
+---------------------------+
|   AgentCP Java API        |
+---------------------------+
|   JNI Bridge              |
+---------------------------+
|   AgentCP Core (C++)      |
+---------------------------+
```

---

## 环境要求

### 开发环境

| 组件 | 最低版本 | 推荐版本 |
|------|---------|---------|
| Android Studio | Arctic Fox | Hedgehog+ |
| Gradle | 8.0 | 8.4 |
| Android Gradle Plugin | 8.0.0 | 8.2.0 |
| NDK | r21 | r26 |
| CMake | 3.18 | 3.22.1 |

### 目标设备

| 配置项 | 值 |
|-------|-----|
| minSdk | 21 (Android 5.0) |
| targetSdk | 34 (Android 14) |
| 支持架构 | armeabi-v7a, arm64-v8a, x86_64 |

---

## 构建 AAR

### 方式一：使用构建脚本

**Windows:**
```batch
cd android
build_aar.bat
```

**Linux/macOS:**
```bash
cd android
chmod +x build_aar.sh
./build_aar.sh
```

### 方式二：使用 Gradle 命令

```bash
cd android

# 构建 Debug 版本
./gradlew assembleDebug

# 构建 Release 版本
./gradlew assembleRelease

# 发布到本地 Maven 仓库
./gradlew publishReleasePublicationToLocalRepository
```

### 构建产物

构建完成后，AAR 文件位于：

```
android/build/outputs/aar/
├── agentcp-android-debug.aar
└── agentcp-android-release.aar
```

本地 Maven 仓库位于：

```
android/build/repo/com/agentcp/agentcp-sdk/0.1.0/
├── agentcp-sdk-0.1.0.aar
├── agentcp-sdk-0.1.0.pom
└── agentcp-sdk-0.1.0-sources.jar
```

---

## 集成方式

### 方式一：本地 AAR 文件

1. 将 `agentcp-android-release.aar` 复制到项目的 `app/libs/` 目录

2. 在 `app/build.gradle` 中添加：

```groovy
android {
    // ...
}

dependencies {
    implementation files('libs/agentcp-android-release.aar')
}
```

### 方式二：本地 Maven 仓库

1. 在项目根目录的 `settings.gradle` 中添加本地仓库：

```groovy
dependencyResolutionManagement {
    repositories {
        google()
        mavenCentral()
        // 添加本地 Maven 仓库
        maven {
            url = uri("path/to/agentcp-so/android/build/repo")
        }
    }
}
```

2. 在 `app/build.gradle` 中添加依赖：

```groovy
dependencies {
    implementation 'com.agentcp:agentcp-sdk:0.1.0'
}
```

### 方式三：发布到私有 Maven 仓库

修改 `android/build.gradle` 中的 `repositories` 配置：

```groovy
publishing {
    repositories {
        maven {
            name = "private"
            url = uri("https://your-maven-repo.com/releases")
            credentials {
                username = findProperty("mavenUser") ?: ""
                password = findProperty("mavenPassword") ?: ""
            }
        }
    }
}
```

然后执行：

```bash
./gradlew publishReleasePublicationToPrivateRepository
```

---

## 快速开始

### 1. 初始化 SDK

```java
import com.agentcp.AgentCP;
import com.agentcp.Result;
import com.agentcp.LogLevel;

public class MyApplication extends Application {
    @Override
    public void onCreate() {
        super.onCreate();
        initAgentCP();
    }

    private void initAgentCP() {
        AgentCP sdk = AgentCP.getInstance();

        // 设置服务器地址
        Result r1 = sdk.setBaseUrls(
            "https://ca.example.com",  // CA 服务器
            "https://ap.example.com"   // AP 服务器
        );
        if (!r1.ok()) {
            Log.e("AgentCP", "setBaseUrls failed: " + r1);
            return;
        }

        // 设置存储路径
        String storagePath = getFilesDir().getAbsolutePath() + "/agentcp";
        Result r2 = sdk.setStoragePath(storagePath);
        if (!r2.ok()) {
            Log.e("AgentCP", "setStoragePath failed: " + r2);
            return;
        }

        // 设置日志级别
        sdk.setLogLevel(LogLevel.INFO);

        // 初始化
        Result r3 = sdk.initialize();
        if (!r3.ok()) {
            Log.e("AgentCP", "initialize failed: " + r3);
            return;
        }

        Log.i("AgentCP", "SDK initialized, version: " + sdk.getVersion());
    }
}
```

### 2. 创建/加载 Agent ID

```java
import com.agentcp.AgentCP;
import com.agentcp.AgentID;
import com.agentcp.AgentCPException;

public class AgentManager {
    private AgentID currentAgent;

    // 创建新的 Agent ID
    public void createAgent(String aid, String password) {
        try {
            currentAgent = AgentCP.getInstance().createAID(aid, password);
            Log.i("AgentCP", "Agent created: " + currentAgent.getAID());
        } catch (AgentCPException e) {
            Log.e("AgentCP", "Create agent failed: " + e.getResult());
        }
    }

    // 加载已有的 Agent ID
    public void loadAgent(String aid) {
        try {
            currentAgent = AgentCP.getInstance().loadAID(aid);
            Log.i("AgentCP", "Agent loaded: " + currentAgent.getAID());
        } catch (AgentCPException e) {
            Log.e("AgentCP", "Load agent failed: " + e.getResult());
        }
    }

    // 获取所有 Agent ID 列表
    public String[] listAgents() {
        return AgentCP.getInstance().listAIDs();
    }

    // 删除 Agent ID
    public void deleteAgent(String aid) {
        Result r = AgentCP.getInstance().deleteAID(aid);
        if (!r.ok()) {
            Log.e("AgentCP", "Delete agent failed: " + r);
        }
    }
}
```

### 3. 上线/下线管理

```java
import com.agentcp.AgentID;
import com.agentcp.AgentState;
import com.agentcp.Result;

public class ConnectionManager {
    private AgentID agent;

    public ConnectionManager(AgentID agent) {
        this.agent = agent;
    }

    // 上线
    public boolean goOnline() {
        Result r = agent.online();
        if (r.ok()) {
            Log.i("AgentCP", "Agent is now online");
            return true;
        } else {
            Log.e("AgentCP", "Go online failed: " + r);
            return false;
        }
    }

    // 下线
    public void goOffline() {
        agent.offline();
        Log.i("AgentCP", "Agent is now offline");
    }

    // 检查在线状态
    public boolean isOnline() {
        return agent.isOnline();
    }

    // 获取详细状态
    public AgentState getState() {
        return agent.getState();
    }

    // 状态监听示例
    public void monitorState() {
        new Thread(() -> {
            while (true) {
                AgentState state = agent.getState();
                Log.d("AgentCP", "Current state: " + state);

                switch (state) {
                    case Online:
                        // 在线，可以收发消息
                        break;
                    case Reconnecting:
                        // 正在重连
                        break;
                    case Error:
                        // 发生错误，可能需要重新登录
                        break;
                    default:
                        break;
                }

                try {
                    Thread.sleep(5000);
                } catch (InterruptedException e) {
                    break;
                }
            }
        }).start();
    }
}
```

### 4. 完整使用示例

```java
public class MainActivity extends AppCompatActivity {
    private AgentID agent;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        // SDK 应该在 Application 中初始化
        // 这里演示如何使用

        // 创建或加载 Agent
        String aid = "user@example.com";
        String password = "secure_password";

        String[] existingAids = AgentCP.getInstance().listAIDs();
        boolean exists = Arrays.asList(existingAids).contains(aid);

        try {
            if (exists) {
                agent = AgentCP.getInstance().loadAID(aid);
            } else {
                agent = AgentCP.getInstance().createAID(aid, password);
            }

            // 上线
            Result r = agent.online();
            if (r.ok()) {
                updateUI("Connected as: " + agent.getAID());
            } else {
                updateUI("Connection failed: " + r.message);
            }

        } catch (AgentCPException e) {
            updateUI("Error: " + e.getMessage());
        }
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        if (agent != null) {
            agent.offline();
            agent.close();
        }
    }

    private void updateUI(String message) {
        runOnUiThread(() -> {
            // 更新 UI
            Toast.makeText(this, message, Toast.LENGTH_SHORT).show();
        });
    }
}
```

---

## API 参考

### AgentCP 类

单例类，SDK 的主入口。

| 方法 | 返回值 | 说明 |
|------|--------|------|
| `getInstance()` | `AgentCP` | 获取单例实例 |
| `initialize()` | `Result` | 初始化 SDK |
| `shutdown()` | `void` | 关闭 SDK |
| `setBaseUrls(caBase, apBase)` | `Result` | 设置服务器地址 |
| `setStoragePath(path)` | `Result` | 设置本地存储路径 |
| `setLogLevel(level)` | `Result` | 设置日志级别 |
| `createAID(aid, password)` | `AgentID` | 创建新的 Agent ID |
| `loadAID(aid)` | `AgentID` | 加载已有的 Agent ID |
| `deleteAID(aid)` | `Result` | 删除 Agent ID |
| `listAIDs()` | `String[]` | 列出所有 Agent ID |
| `getVersion()` | `String` | 获取 SDK 版本 |
| `getBuildInfo()` | `String` | 获取构建信息 |

### AgentID 类

代表一个 Agent 身份，实现 `AutoCloseable` 接口。

| 方法 | 返回值 | 说明 |
|------|--------|------|
| `online()` | `Result` | 上线 |
| `offline()` | `void` | 下线 |
| `isOnline()` | `boolean` | 是否在线 |
| `getState()` | `AgentState` | 获取当前状态 |
| `getAID()` | `String` | 获取 Agent ID 字符串 |
| `close()` | `void` | 释放资源 |

### Result 类

操作结果封装。

| 字段/方法 | 类型 | 说明 |
|----------|------|------|
| `code` | `int` | 错误码，0 表示成功 |
| `message` | `String` | 错误消息 |
| `context` | `String` | 错误上下文 |
| `ok()` | `boolean` | 是否成功 |

### AgentState 枚举

Agent 状态枚举。

| 值 | 说明 |
|----|------|
| `Offline` | 离线 |
| `Connecting` | 正在连接 |
| `Authenticating` | 正在认证 |
| `Online` | 在线 |
| `Reconnecting` | 正在重连 |
| `Error` | 错误状态 |

### LogLevel 枚举

日志级别枚举。

| 值 | 说明 |
|----|------|
| `Error` | 仅错误 |
| `Warn` | 警告及以上 |
| `Info` | 信息及以上 |
| `Debug` | 调试及以上 |
| `Trace` | 全部日志 |

---

## 错误处理

### 错误码范围

| 范围 | 类别 |
|------|------|
| 0 | 成功 |
| 1-999 | 通用错误 |
| 1000-1999 | 认证错误 |
| 2000-2999 | 心跳错误 |
| 3000-3999 | WebSocket 错误 |
| 4000-4999 | AID/会话错误 |
| 5000-5999 | 流错误 |
| 6000-6999 | 文件错误 |
| 7000-7999 | 数据库错误 |
| 8000-8999 | 网络错误 |

### 异常处理示例

```java
try {
    AgentID agent = AgentCP.getInstance().createAID(aid, password);
} catch (AgentCPException e) {
    Result r = e.getResult();

    if (r.code >= 1000 && r.code < 2000) {
        // 认证错误
        showAuthError(r.message);
    } else if (r.code >= 8000 && r.code < 9000) {
        // 网络错误
        showNetworkError(r.message);
    } else {
        // 其他错误
        showGenericError(r.message);
    }
}
```

---

## 最佳实践

### 1. 生命周期管理

```java
public class MyApplication extends Application {
    @Override
    public void onCreate() {
        super.onCreate();
        // 在 Application 中初始化 SDK
        initAgentCP();
    }

    @Override
    public void onTerminate() {
        super.onTerminate();
        // 关闭 SDK
        AgentCP.getInstance().shutdown();
    }
}
```

### 2. 使用 try-with-resources

```java
try (AgentID agent = AgentCP.getInstance().loadAID(aid)) {
    agent.online();
    // 使用 agent...
} // 自动调用 close()
```

### 3. 在后台线程执行网络操作

```java
ExecutorService executor = Executors.newSingleThreadExecutor();

executor.execute(() -> {
    Result r = agent.online();
    runOnUiThread(() -> {
        if (r.ok()) {
            updateUI("Connected");
        } else {
            showError(r.message);
        }
    });
});
```

### 4. 存储路径建议

```java
// 推荐使用应用私有目录
String storagePath = context.getFilesDir().getAbsolutePath() + "/agentcp";

// 或者使用外部存储（需要权限）
// String storagePath = context.getExternalFilesDir(null).getAbsolutePath() + "/agentcp";
```

### 5. ProGuard 配置

如果启用了代码混淆，SDK 的 `consumer-rules.pro` 会自动应用。如需额外配置：

```proguard
# 保留 AgentCP 所有公共 API
-keep public class com.agentcp.** { public *; }
```

---

## 常见问题

### Q1: 找不到 native 库

**错误信息:** `java.lang.UnsatisfiedLinkError: couldn't find "libagentcp_jni.so"`

**解决方案:**
1. 确保 AAR 正确集成
2. 检查设备 CPU 架构是否在支持列表中
3. 检查 APK 中是否包含 so 文件

### Q2: SDK 初始化失败

**可能原因:**
1. 存储路径无写入权限
2. 服务器地址配置错误
3. 网络不可用

**解决方案:**
```java
// 检查存储路径
File dir = new File(storagePath);
if (!dir.exists()) {
    dir.mkdirs();
}

// 检查网络
ConnectivityManager cm = (ConnectivityManager)
    getSystemService(Context.CONNECTIVITY_SERVICE);
NetworkInfo info = cm.getActiveNetworkInfo();
if (info == null || !info.isConnected()) {
    // 无网络连接
}
```

### Q3: 上线失败

**可能原因:**
1. 认证信息错误
2. 服务器不可达
3. Agent ID 不存在

**解决方案:**
```java
Result r = agent.online();
if (!r.ok()) {
    Log.e("AgentCP", "Online failed: code=" + r.code
        + ", message=" + r.message
        + ", context=" + r.context);
}
```

### Q4: 如何调试

1. 设置日志级别为 Debug 或 Trace：
```java
AgentCP.getInstance().setLogLevel(LogLevel.Debug);
```

2. 查看 Logcat 输出，过滤 "AgentCP" 标签

### Q5: 支持哪些 CPU 架构？

当前支持：
- `armeabi-v7a` (32位 ARM)
- `arm64-v8a` (64位 ARM)
- `x86_64` (64位 x86，模拟器)

如需添加其他架构，修改 `build.gradle` 中的 `abiFilters`。

---

## 版本历史

| 版本 | 日期 | 说明 |
|------|------|------|
| 0.1.0 | 2024-01 | 初始版本 |

---

## 技术支持

如有问题，请联系技术支持或提交 Issue。
