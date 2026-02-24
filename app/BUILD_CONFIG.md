# AgentCP SDK 集成 - build.gradle.kts 配置示例

## 方式一：使用本地 AAR 文件

### 修改 android/app/build.gradle.kts

在文件末尾的 `dependencies` 块中添加：

```kotlin
dependencies {
    // 添加 AgentCP SDK AAR
    implementation(files("libs/agentcp-android-release.aar"))
}
```

完整示例：

```kotlin
plugins {
    id("com.android.application")
    id("kotlin-android")
    id("dev.flutter.flutter-gradle-plugin")
}

android {
    namespace = "com.example.evol"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }

    kotlinOptions {
        jvmTarget = JavaVersion.VERSION_11.toString()
    }

    defaultConfig {
        applicationId = "com.example.evol"
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    buildTypes {
        release {
            signingConfig = signingConfigs.getByName("debug")
        }
    }
}

flutter {
    source = "../.."
}

dependencies {
    // 添加 AgentCP SDK AAR
    implementation(files("libs/agentcp-android-release.aar"))
}
```

---

## 方式二：使用本地 Maven 仓库

### 1. 修改 android/build.gradle.kts

```kotlin
allprojects {
    repositories {
        google()
        mavenCentral()
        // 添加 AgentCP SDK 本地 Maven 仓库
        maven {
            url = uri("H:/project/agentcp-so/android/build/repo")
        }
    }
}

val newBuildDir: Directory = rootProject.layout.buildDirectory.dir("../../build").get()
rootProject.layout.buildDirectory.value(newBuildDir)

subprojects {
    val newSubprojectBuildDir: Directory = newBuildDir.dir(project.name)
    project.layout.buildDirectory.value(newSubprojectBuildDir)
}

subprojects {
    project.evaluationDependsOn(":app")
}

tasks.register<Delete>("clean") {
    delete(rootProject.layout.buildDirectory)
}
```

### 2. 修改 android/app/build.gradle.kts

在 `dependencies` 块中添加：

```kotlin
dependencies {
    // 添加 AgentCP SDK Maven 依赖
    implementation("com.agentcp:agentcp-sdk:0.1.0")
}
```

---

## 方式三：使用远程 Maven 仓库（如果有）

### 修改 android/build.gradle.kts

```kotlin
allprojects {
    repositories {
        google()
        mavenCentral()
        // 添加私有 Maven 仓库
        maven {
            url = uri("https://your-maven-repo.com/releases")
            credentials {
                username = project.findProperty("mavenUser") as String? ?: ""
                password = project.findProperty("mavenPassword") as String? ?: ""
            }
        }
    }
}
```

### 修改 android/app/build.gradle.kts

```kotlin
dependencies {
    implementation("com.agentcp:agentcp-sdk:0.1.0")
}
```

---

## 添加必要的权限

### 修改 android/app/src/main/AndroidManifest.xml

在 `<manifest>` 标签内添加：

```xml
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <!-- 网络权限 -->
    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />

    <application
        android:label="evol"
        android:name="${applicationName}"
        android:icon="@mipmap/ic_launcher">
        <!-- ... -->
    </application>
</manifest>
```

---

## ProGuard 配置（如果启用混淆）

### 创建或修改 android/app/proguard-rules.pro

```proguard
# AgentCP SDK
-keep public class com.agentcp.** { public *; }
-keepclassmembers class com.agentcp.** { *; }

# 保留 JNI 方法
-keepclasseswithmembernames class * {
    native <methods>;
}
```

### 在 android/app/build.gradle.kts 中启用

```kotlin
android {
    buildTypes {
        release {
            isMinifyEnabled = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
            signingConfig = signingConfigs.getByName("debug")
        }
    }
}
```

---

## 验证配置

### 1. 同步 Gradle

```bash
cd android
./gradlew --refresh-dependencies
```

### 2. 检查依赖

```bash
./gradlew :app:dependencies
```

查找输出中是否包含 `agentcp-sdk` 或 `agentcp-android-release.aar`

### 3. 构建项目

```bash
cd ..
flutter clean
flutter pub get
flutter build apk --debug
```

### 4. 检查 APK 内容

```bash
# 解压 APK
unzip -l build/app/outputs/flutter-apk/app-debug.apk | grep agentcp

# 应该看到类似输出：
# lib/arm64-v8a/libagentcp_jni.so
# lib/armeabi-v7a/libagentcp_jni.so
```

---

## 故障排除

### 问题：Gradle 同步失败

**错误信息**：
```
Could not find com.agentcp:agentcp-sdk:0.1.0
```

**解决方案**：
1. 检查 Maven 仓库路径是否正确
2. 确认 AAR 文件已构建并存在
3. 尝试使用绝对路径

### 问题：编译错误

**错误信息**：
```
Unresolved reference: AgentCP
```

**解决方案**：
1. 确认 AAR 已正确添加到依赖
2. 运行 `flutter clean`
3. 删除 `android/.gradle` 目录
4. 重新同步：`flutter pub get`

### 问题：运行时崩溃

**错误信息**：
```
java.lang.UnsatisfiedLinkError: couldn't find "libagentcp_jni.so"
```

**解决方案**：
1. 检查 AAR 中是否包含 .so 文件
2. 确认设备架构支持（arm64-v8a, armeabi-v7a, x86_64）
3. 检查 APK 中是否包含 .so 文件

---

## 推荐配置

对于开发环境，推荐使用**方式一（本地 AAR）**：
- ✅ 简单直接
- ✅ 不需要额外配置
- ✅ 便于调试

对于团队协作，推荐使用**方式二（本地 Maven）**：
- ✅ 版本管理清晰
- ✅ 支持多模块项目
- ✅ 便于更新

对于生产环境，推荐使用**方式三（远程 Maven）**：
- ✅ 集中管理
- ✅ 自动更新
- ✅ 支持 CI/CD

---

## 相关文件

- `android/app/build.gradle.kts` - 应用级构建配置
- `android/build.gradle.kts` - 项目级构建配置
- `android/settings.gradle.kts` - 项目设置
- `android/app/src/main/AndroidManifest.xml` - 应用清单
- `android/app/proguard-rules.pro` - ProGuard 规则

---

## 下一步

配置完成后：
1. 参考 [QUICK_START.md](QUICK_START.md) 更新 Kotlin 代码
2. 运行 `flutter run` 测试集成
3. 查看 [README_AGENTCP.md](README_AGENTCP.md) 了解完整功能
