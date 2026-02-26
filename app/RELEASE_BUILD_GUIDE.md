# ACP Android Release 构建指南

## 1. 项目概述

- 项目名称：ACP (AgentCP)
- 包名：`com.agent.acp`
- 构建工具：Flutter + Gradle (Kotlin DSL)
- 原生依赖：agentcp-sdk（C++ via CMake）
- 输出产物：`app-release.apk`（约 34MB）

## 2. 环境要求

| 工具 | 版本要求 |
|------|---------|
| Flutter SDK | >= 3.8.1 |
| Java JDK | 11+ |
| Android SDK | compileSdk 由 Flutter 管理 |
| Android NDK | 27.0.12077973 |
| CMake | 3.22.1 |

## 3. 项目结构（关键文件）

```
acp_app/
├── android/
│   ├── app/
│   │   ├── build.gradle.kts      # 应用构建配置（含签名）
│   │   └── release-keystore.jks  # Release 签名证书
│   ├── key.properties             # 签名密钥配置（不入版本库）
│   ├── build.gradle.kts           # 根构建配置
│   └── settings.gradle.kts        # 包含 agentcp-sdk 引用
├── lib/                           # Flutter Dart 源码
├── pubspec.yaml                   # Flutter 依赖配置
└── build/app/outputs/flutter-apk/ # APK 输出目录
```

## 4. 签名配置

### 4.1 签名证书（Keystore）

证书文件位于 `android/app/release-keystore.jks`，当前配置：

| 属性 | 值 |
|------|---|
| 算法 | RSA 2048 位 |
| 有效期 | 10000 天（至 2053 年） |
| 别名 | release |
| 签名算法 | SHA256withRSA |
| DN | CN=ACP, OU=Development, O=AgentCP, L=Beijing, ST=Beijing, C=CN |

### 4.2 key.properties

位于 `android/key.properties`，内容格式：

```properties
storePassword=acp2026
keyPassword=acp2026
keyAlias=release
storeFile=release-keystore.jks
```

> 此文件已在 `.gitignore` 中排除，不会提交到版本库。

### 4.3 build.gradle.kts 签名引用

`android/app/build.gradle.kts` 中通过读取 `key.properties` 自动加载签名配置：

```kotlin
val keystorePropertiesFile = rootProject.file("key.properties")
val keystoreProperties = Properties()
if (keystorePropertiesFile.exists()) {
    keystoreProperties.load(FileInputStream(keystorePropertiesFile))
}

signingConfigs {
    create("release") {
        keyAlias = keystoreProperties["keyAlias"] as String?
        keyPassword = keystoreProperties["keyPassword"] as String?
        storeFile = keystoreProperties["storeFile"]?.let { file(it as String) }
        storePassword = keystoreProperties["storePassword"] as String?
    }
}

buildTypes {
    release {
        signingConfig = signingConfigs.getByName("release")
    }
}
```

## 5. 构建命令

### 5.1 构建 Release APK

```bash
cd acp_app
flutter build apk --release
```

构建产物路径：`build/app/outputs/flutter-apk/app-release.apk`

### 5.2 构建 App Bundle（用于 Google Play 发布）

```bash
flutter build appbundle --release
```

构建产物路径：`build/app/outputs/bundle/release/app-release.aab`

### 5.3 指定版本号构建

```bash
flutter build apk --release --build-name=1.0.1 --build-number=2
```

### 5.4 清理后重新构建

```bash
flutter clean && flutter pub get && flutter build apk --release
```

## 6. 验证 APK 签名

构建完成后，可验证 APK 是否使用了正确的 release 证书签名：

```bash
keytool -printcert -jarfile build/app/outputs/flutter-apk/app-release.apk
```

预期输出应包含：
```
所有者: CN=ACP, OU=Development, O=AgentCP, L=Beijing, ST=Beijing, C=CN
```

## 7. agentcp-sdk 依赖说明

项目通过源码方式引用 agentcp-sdk，配置在 `android/settings.gradle.kts`：

```kotlin
include(":agentcp-sdk")
project(":agentcp-sdk").projectDir = file("H:/project/evol_main/evol_app/agentcp-so/android")
```

SDK 使用 CMake 编译 C++ 原生代码，支持以下 ABI：
- `armeabi-v7a`
- `arm64-v8a`
- `x86_64`

如需在其他机器构建，需确保 agentcp-sdk 源码路径正确，或修改 `settings.gradle.kts` 中的路径。

## 8. 新环境部署检查清单

1. 安装 Flutter SDK >= 3.8.1，运行 `flutter doctor` 确认环境正常
2. 安装 JDK 11+
3. 确认 Android SDK、NDK 27.0.12077973、CMake 3.22.1 已安装
4. 将 `release-keystore.jks` 放入 `android/app/` 目录
5. 在 `android/` 目录下创建 `key.properties`，填入正确的密码和别名
6. 确认 agentcp-sdk 源码路径与 `settings.gradle.kts` 中一致
7. 执行 `flutter pub get` 拉取依赖
8. 执行 `flutter build apk --release` 构建

## 9. 常见问题

### Q: 构建报错 "Keystore was tampered with, or password was incorrect"
检查 `key.properties` 中的密码是否与生成 keystore 时一致。

### Q: 构建报错找不到 agentcp-sdk
确认 `settings.gradle.kts` 中 agentcp-sdk 的 `projectDir` 路径在当前机器上存在。

### Q: 如何重新生成签名证书
```bash
keytool -genkey -v \
  -keystore android/app/release-keystore.jks \
  -keyalg RSA -keysize 2048 -validity 10000 \
  -alias release \
  -storepass <你的密码> \
  -keypass <你的密码> \
  -dname "CN=ACP, OU=Development, O=AgentCP, L=Beijing, ST=Beijing, C=CN"
```

> 注意：更换证书后，已安装的旧版本 APK 无法直接覆盖升级，需先卸载。
