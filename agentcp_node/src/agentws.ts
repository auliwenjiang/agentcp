import { IAgentWS } from "./interfaces";
import { WSClient, ConnectionStatus, ACPMessageSessionResponse, InviteStatus } from "./websocket";
import { logger } from './utils';

/**
 * AgentWS类
 * 提供基于WebSocket的智能体通信功能，封装了WebSocket连接、会话创建和消息传递等操作
 */
class AgentWS implements IAgentWS {
    /** 智能体ID */
    private aid: string;
    /** WebSocket客户端实例 */
    private msgClient: WSClient;
    /** 心跳服务器地址（未使用） */
    private heartbeatServer: string = '';
    /** 消息服务器地址 */
    private messageServer: string;
    /** 消息签名 */
    private messageSignature: string;
    // 存储回调函数
    private statusChangeCallback: ((status: ConnectionStatus) => void) | null = null;
    private messageCallback: ((message: any) => void) | null = null;

    /**
     * 构造函数
     * @param aid 智能体ID
     * @param messageServer 消息服务器地址
     * @param messageSignature 消息签名
     */
    constructor(aid: string, messageServer: string, messageSignature: string) {
        this.aid = aid;
        this.messageServer = messageServer;
        this.messageSignature = messageSignature;
        this.msgClient = new WSClient();
        // 在构造函数中设置回调代理
        this.msgClient.onStatusChange((status: ConnectionStatus) => {
            if (this.statusChangeCallback) {
                this.statusChangeCallback(status);
            }
        });

        this.msgClient.onMessage((message: any) => {
            if (this.messageCallback) {
                this.messageCallback(message);
            }
        });
    }

    /**
     * 连接到WebSocket服务器
     * @throws Error 当连接失败时抛出错误
     */
    public async startWebSocket(): Promise<void> {
        if (this.aid.length == 0) {
            throw new Error("本地的aid不存在");
        }
        if (this.messageSignature.length === 0 || this.messageServer.length === 0) {
            throw new Error("消息服务器不存在");
        }
        await this.msgClient.connectToServer(this.messageServer, this.aid, this.messageSignature);
    }

    /**
     * 快捷连接到指定智能体，自动创建会话并发送邀请
     * @param receiver 要连接的智能体ID
     * @param onSessionCreated 会话创建成功回调（可选）
     * @param onInviteStatus 邀请状态回调（可选）
     */
    public connectTo(
        receiver: string, 
        onSessionCreated: ((sessionInfo: ACPMessageSessionResponse) => void) | null = null,
        onInviteStatus: ((status: InviteStatus) => void) | null = null
    ) {
        if (!receiver || receiver.length === 0) {
            throw new Error("receiver不能为空");
        }

        // 先创建会话
        this.createSession((sessionRes: ACPMessageSessionResponse) => {
            // 会话创建成功后的处理
            if (onSessionCreated) {
                onSessionCreated(sessionRes);
            }

            // 如果会话创建成功且返回了邀请码，发送邀请
            if (sessionRes.sessionId && sessionRes.identifyingCode) {
                this.invite(receiver, sessionRes.sessionId, sessionRes.identifyingCode, onInviteStatus);
            } else {
                logger.error("会话创建成功但未返回sessionId或identifyingCode");
            }
        });
    }

    /**
     * 创建会话
     * @param cb 会话创建回调函数
     */
    public createSession(cb: (res: ACPMessageSessionResponse) => void) {
        this.msgClient.createSession(cb);
    }

    /**
     * 邀请智能体加入会话
     * @param receiver 接收者智能体ID
     * @param sessionId 会话ID
     * @param identifyingCode 邀请码
     * @param cb 邀请状态回调函数（可选）
     */
    public invite(receiver: string, sessionId: string, identifyingCode: string, cb: (((status: InviteStatus) => void) | null) = null) {
        if (!receiver || receiver.length === 0) {
            throw new Error("receiver不能为空");
        }
        this.msgClient.invite(receiver, sessionId, identifyingCode, cb);
    }

    /**
     * 发送消息
     * @param msg 要发送的消息内容
     * @param to 接收者智能体ID
     * @param sessionId 会话ID
     * @param identifyingCode 邀请码
     */
    public send(msg: string, to: string, sessionId: string, identifyingCode: string) {
        this.msgClient.send(msg, to, sessionId, identifyingCode);
    }

    /**
     * 发送原始消息（不做 URL 编码），用于群组协议等需要原始 JSON 的场景
     * @param message 原始消息字符串
     * @param to 接收者智能体ID
     * @param sessionId 会话ID
     * @returns true 发送成功，false 连接未建立
     */
    public sendRaw(message: string, to: string, sessionId: string): boolean {
        return this.msgClient.sendRaw(message, to, sessionId);
    }

    /**
     * 设置原始消息拦截器。回调函数返回 true 表示已处理（拦截），不再继续分发。
     * 用于群组协议消息路由。
     */
    public onRawMessage(cb: (message: any) => boolean) {
        this.msgClient.onRawMessage(cb);
    }

    /**
     * 设置WebSocket连接状态变更的监听函数
     * @param cb 状态变更回调函数
     */
    public onStatusChange(cb: (status: ConnectionStatus) => void) {
        this.statusChangeCallback = cb;
        // 如果已经连接，立即触发当前状态
        if (this.msgClient.getCurrentStatus) {
            cb(this.msgClient.getCurrentStatus());
        }
    }

    /**
     * 设置消息接收的监听函数
     * @param cb 消息接收回调函数
     */
    public onMessage(cb: (message: any) => void) {
        this.messageCallback = cb;
    }

    /**
     * 断开WebSocket连接
     */
    public disconnect() {
        this.msgClient.disconnect();
    }

    /**
     * 注册"快速重连全部失败"回调，透传 WSClient 的回调
     */
    public onReconnectNeeded(cb: () => void): void {
        this.msgClient.onReconnectNeeded(cb);
    }

    /**
     * 重连 WebSocket
     * @param newServer 新的消息服务器地址（可选，重新鉴权后传入）
     * @param newSignature 新的签名（可选，重新鉴权后传入）
     */
    public async reconnect(newServer?: string, newSignature?: string): Promise<void> {
        let newUrl: string | undefined;
        if (newServer && newSignature) {
            this.messageServer = newServer;
            this.messageSignature = newSignature;
            let url = newServer.replace("https://", "wss://").replace("http://", "ws://");
            const encodedAid = encodeURIComponent(this.aid);
            const encodedSignature = encodeURIComponent(newSignature);
            newUrl = `${url}/session?agent_id=${encodedAid}&signature=${encodedSignature}`;
        }
        await this.msgClient.reconnect(newUrl);
    }

    /**
     * 接受来自心跳通道的邀请
     * 当心跳客户端收到邀请时，调用此方法通过 WebSocket 加入会话
     * @param sessionId 会话ID
     * @param inviterId 邀请者ID
     * @param inviteCode 邀请码
     */
    public acceptInviteFromHeartbeat(sessionId: string, inviterId: string, inviteCode: string) {
        this.msgClient.acceptInviteFromHeartbeat(sessionId, inviterId, inviteCode);
    }
}

export { AgentWS }