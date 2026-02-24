# acp-ts

基于 WebSocket 的智能体通信库，提供智能体身份管理和实时通信功能。

## 安装

```bash
npm install acp-ts
```

## 简介

acp-ts 是一个基于 WebSocket 的智能体通信库，提供了智能体身份管理（AgentCP）、WebSocket 通信（AgentWS）和文件同步（FileSync）功能。通过 AgentManager 统一管理这些功能，使用更加便捷。

## 快速开始

### 1. 初始化 AgentManager

```typescript
import { AgentManager } from 'acp-ts';

// 获取 AgentManager 单例
const manager = AgentManager.getInstance();

// 初始化 AgentCP（身份管理）
const apiUrl = "aid.pub";  // 只需要域名，不需要 https:// 前缀
const seedPassword = "your-seed-password"; // 可选
const acp = await manager.initACP(apiUrl, seedPassword);
```

### 2. 身份管理

```typescript
// 创建新的智能体身份
const aid = await acp.createAid("your-aid");

// 如果本地只有一个账户，可以直接加载当前账户
const currentAid = await acp.loadCurrentAid();
if (!currentAid) {
    throw new Error("没有可用的身份");
}

// 或者加载指定的身份
const loaded = await acp.loadAid(aid);
if (!loaded) {
    throw new Error("加载身份失败");
}

// 或者导入已有的身份
const identity = {
    aid: "your-aid",
    privateKey: "your-private-key",
    certPem: "your-cert-pem"
};
await acp.importAid(identity, seedPassword);

// 如果没有身份，可以加载访客身份
const guestAid = await acp.loadGuestAid();

// 获取当前可用的身份列表
const aidList = await acp.loadAidList();

// 获取当前身份的证书信息
const certInfo = await acp.getCertInfo(aid);
```

### 3. 上线并建立连接

```typescript
// 获取连接配置
const config = await acp.online();

// 初始化 WebSocket 连接
const aws = await manager.initAWS(aid, config);

// 启动 WebSocket 连接
await aws.startWebSocket();

// 快速连接到指定智能体（推荐方式）
aws.connectTo("target-aid",
    (sessionInfo) => {
        console.log("会话创建成功:", sessionInfo.sessionId);
        console.log("邀请码:", sessionInfo.identifyingCode);
    },
    (inviteStatus) => {
        console.log("邀请状态:", inviteStatus);
    }
);
```

### 4. 消息通信

```typescript
// 注册状态变更监听
aws.onStatusChange((status) => {
    console.log(`连接状态: ${status}`);
    // status: 'connecting' | 'connected' | 'disconnected' | 'reconnecting' | 'error'
});

// 注册消息接收监听
aws.onMessage((message) => {
    console.log(`收到消息类型: ${message.type}`); // 'success' | 'error'
    console.log(`消息内容: ${message.content}`);
});

// 发送消息到当前会话
aws.send("Hello, Agent!");

// 发送消息到指定智能体
aws.sendTo("specific-agent-id", "Hello, specific agent!");

// 断开连接
aws.disconnect();
```

## 高级用法

### 手动会话管理

如果需要更精细的控制，可以手动管理会话和邀请：

```typescript
// 手动创建会话
aws.createSession((sessionRes) => {
    console.log("会话ID:", sessionRes.sessionId);
    console.log("邀请码:", sessionRes.identifyingCode);

    // 手动邀请智能体
    aws.invite(
        "target-agent-id",
        sessionRes.sessionId,
        sessionRes.identifyingCode,
        (inviteStatus) => {
            if (inviteStatus === 'success') {
                console.log("邀请成功，可以开始通信");
            } else {
                console.log("邀请失败");
            }
        }
    );
});
```

### 文件同步

acp-ts 提供了公共文件同步功能，可以在本地目录和服务器之间同步文件（仅 Node.js 环境）：

```typescript
// 方式一：使用 AgentManager 快捷方法
const result = await manager.syncPublicFiles(aid, config.messageSignature, './public');

console.log("上传成功:", result.uploadedFiles);
console.log("下载成功:", result.downloadedFiles);
console.log("上传失败:", result.uploadFailedFiles);
console.log("下载失败:", result.downloadFailedFiles);

// 方式二：使用 FileSync 类进行更精细的控制
const fileSync = manager.initFileSync(aid, config.messageSignature, './public');

// 监听同步状态
fileSync.onStatusChange((status) => {
    console.log("同步状态:", status); // 'idle' | 'syncing' | 'completed' | 'error'
});

// 监听同步进度
fileSync.onProgress((progress) => {
    console.log(`${progress.phase}: ${progress.current}/${progress.total} - ${progress.fileName}`);
});

// 执行同步
const syncResult = await fileSync.syncPublicFiles();
```

### agent.md 上传

登录成功后可以自动上传 agent.md 文件，该文件用于描述智能体信息：

```typescript
// 方式一：登录时自动上传（推荐）
acp.setAgentMdPath('./agent.md');  // 设置文件路径
const config = await acp.online();  // 登录时自动上传

// 如果需要重新上传，先重置状态
await acp.resetAgentMdUploadStatus();
await acp.online();  // 再次登录会重新上传

// 方式二：使用 FileSync 手动上传
const fileSync = manager.initFileSync(aid, config.messageSignature, './public');

// 从内容上传
const result = await fileSync.uploadAgentMd('# My Agent\n\nThis is my agent.');

// 或从文件上传
const result2 = await fileSync.uploadAgentMdFromFile('./agent.md');

if (result.success) {
    console.log("上传成功:", result.url);  // https://{aid}/agent.md
}
```

**注意事项：**
- agent.md 文件大小限制为 4KB
- 上传后可通过 `https://{aid}/agent.md` 访问

### React 组件中使用

```typescript
import React, { useEffect, useState } from 'react';
import { AgentManager } from 'acp-ts';

const ChatComponent: React.FC = () => {
    const [aws, setAws] = useState<any>(null);
    const [messages, setMessages] = useState<string[]>([]);
    const [connectionStatus, setConnectionStatus] = useState<string>('disconnected');

    useEffect(() => {
        const initAgent = async () => {
            try {
                const manager = AgentManager.getInstance();
                const acp = await manager.initACP("aid.pub");

                // 加载或创建身份
                let aid = await acp.loadCurrentAid();
                if (!aid) {
                    aid = await acp.loadGuestAid();
                }

                // 获取连接配置并初始化WebSocket
                const config = await acp.online();
                const agentWS = await manager.initAWS(aid, config);

                // 注册事件监听器
                agentWS.onStatusChange((status) => {
                    setConnectionStatus(status);
                });

                agentWS.onMessage((message) => {
                    setMessages(prev => [...prev, message.content]);
                });

                // 启动连接
                await agentWS.startWebSocket();
                setAws(agentWS);

            } catch (error) {
                console.error("初始化失败:", error);
            }
        };

        initAgent();

        // 清理函数
        return () => {
            if (aws) {
                aws.disconnect();
            }
        };
    }, []);

    const sendMessage = (text: string) => {
        if (aws && connectionStatus === 'connected') {
            aws.send(text);
        }
    };

    const connectToAgent = (targetAid: string) => {
        if (aws) {
            aws.connectTo(targetAid);
        }
    };

    return (
        <div>
            <div>状态: {connectionStatus}</div>
            <div>
                {messages.map((msg, index) => (
                    <div key={index}>{msg}</div>
                ))}
            </div>
        </div>
    );
};
```

## API 参考

### AgentManager

- `getInstance(): AgentManager` - 获取单例实例
- `initACP(apiUrl, seedPassword?): Promise<AgentCP>` - 初始化身份管理
- `initAWS(aid, config): Promise<AgentWS>` - 初始化 WebSocket 连接
- `initFileSync(aid, signature, localDir): FileSync` - 初始化文件同步模块
- `syncPublicFiles(aid, signature, localDir): Promise<SyncResult>` - 快捷同步公共文件
- `acp(): AgentCP` - 获取 AgentCP 实例
- `aws(): AgentWS` - 获取 AgentWS 实例
- `fs(): FileSync` - 获取 FileSync 实例

### AgentCP

- `createAid(aid): Promise<string>` - 创建新身份
- `loadAid(aid): Promise<boolean>` - 加载指定身份
- `loadCurrentAid(): Promise<string | null>` - 加载当前身份
- `loadGuestAid(): Promise<string>` - 加载访客身份
- `loadAidList(): Promise<string[]>` - 获取身份列表
- `importAid(identity, seedPassword?): Promise<void>` - 导入身份
- `getCertInfo(aid): Promise<CertInfo>` - 获取证书信息
- `online(): Promise<Config>` - 上线获取连接配置
- `setAgentMdPath(filePath): void` - 设置 agent.md 文件路径（登录时自动上传）
- `resetAgentMdUploadStatus(): Promise<void>` - 重置上传状态，下次登录时重新上传

### AgentWS

#### 方法

- `startWebSocket(): Promise<void>` - 启动 WebSocket 连接
- `connectTo(receiver, onSessionCreated?, onInviteStatus?): void` - 快捷连接到指定智能体
- `createSession(callback): void` - 创建会话
- `invite(receiver, sessionId, identifyingCode, callback?): void` - 邀请智能体加入会话
- `send(message): void` - 发送消息到当前会话
- `sendTo(receiver, message): void` - 发送消息到指定智能体
- `onStatusChange(callback): void` - 注册状态变更监听器
- `onMessage(callback): void` - 注册消息接收监听器
- `disconnect(): void` - 断开连接

#### 类型定义

```typescript
type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'reconnecting' | 'error';
type InviteStatus = 'success' | 'error';

type ACPMessageResponse = {
    type: 'success' | 'error';
    content: string;
}

type ACPMessageSessionResponse = {
    identifyingCode: string;
    sessionId: string;
}
```

### WSClient

底层 WebSocket 客户端，提供更精细的控制：

- `connectToServer(wsServer, aid, signature): Promise<void>` - 连接到 WebSocket 服务器
- `createSession(callback): void` - 创建会话（自动清理监听器）
- `invite(receiver, sessionId, identifyingCode, callback?): void` - 发送邀请
- `onStatusChange(callback): () => void` - 注册状态监听器，返回清理函数
- `onMessage(callback): () => void` - 注册消息监听器，返回清理函数
- `send(message): void` - 发送消息
- `sendTo(receiver, message): void` - 发送消息到指定接收者
- `disconnect(): void` - 断开连接并清理所有监听器

### FileSync

文件同步类，提供公共文件的上传、下载和同步功能（仅 Node.js 环境）：

- `syncPublicFiles(): Promise<SyncResult>` - 同步公共文件
- `uploadAgentMd(content): Promise<UploadResult>` - 上传 agent.md 内容
- `uploadAgentMdFromFile(filePath): Promise<UploadResult>` - 从文件上传 agent.md
- `getStatus(): FileSyncStatus` - 获取当前同步状态
- `onStatusChange(callback): void` - 设置状态变更回调
- `onProgress(callback): void` - 设置进度回调

#### 类型定义

```typescript
type FileSyncStatus = 'idle' | 'syncing' | 'completed' | 'error';

interface SyncResult {
    status: FileSyncStatus;
    uploadedFiles: string[];
    downloadedFiles: string[];
    uploadFailedFiles: string[];
    downloadFailedFiles: string[];
    error?: string;
}

interface UploadResult {
    success: boolean;
    url?: string;
    error?: string;
}
```

## 错误处理

```typescript
try {
    await aws.startWebSocket();
} catch (error) {
    console.error(`WebSocket 连接失败: ${error.message}`);
}

// 连接状态监听
aws.onStatusChange((status) => {
    switch (status) {
        case 'error':
            console.error("连接出错，尝试重连...");
            break;
        case 'disconnected':
            console.warn("连接断开");
            break;
        case 'connected':
            console.log("连接成功");
            break;
    }
});

// 消息错误处理
aws.onMessage((message) => {
    if (message.type === 'error') {
        console.error("收到错误消息:", message.content);
    } else {
        console.log("收到消息:", message.content);
    }
});
```

## 最佳实践

1. **资源管理**
   - 使用 AgentManager 管理实例
   - 退出时调用 `disconnect()` 清理资源
   - React 组件中使用 useEffect 清理函数

2. **事件处理**
   - 初始化连接后再注册监听器
   - 使用 WSClient 时调用返回的清理函数防止内存泄漏

3. **安全性**
   - 妥善保管 seedPassword 和私钥
   - 使用 HTTPS/WSS 协议通信

## 相关项目

- [acp-py](https://www.npmjs.com/package/acp-py) - Python 版本的智能体通信库

## License

MIT
