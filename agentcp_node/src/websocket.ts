import { v4 as uuidv4 } from 'uuid';
import mitt from 'mitt';
import * as https from 'https';
import { logger } from './utils';

// 统一的环境检测函数
export const isNodeEnvironment = typeof process !== 'undefined' &&
    process.versions != null &&
    process.versions.node != null;

// 动态加载 WebSocket 实现
let WebSocketImpl: any;
if (isNodeEnvironment) {
    WebSocketImpl = require('ws');
} else {
    WebSocketImpl = WebSocket;
}

// WebSocket 配置选项
export interface WSClientOptions {
    /** 是否跳过 SSL 证书验证（仅 Node.js 环境有效，默认 true） */
    rejectUnauthorized?: boolean;
    /** 最大重试次数（默认 5） */
    maxRetries?: number;
    /** 连接超时时间（毫秒，默认 10000） */
    connectionTimeout?: number;
}

type ACPMessageSessionResponse = {
    identifyingCode: string;
    sessionId: string;
}

type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'reconnecting' | 'error';

type InviteStatus = 'success' | 'error';

type Events = {
    'status-change': ConnectionStatus;
    'message': any;
    'session': ACPMessageSessionResponse;
    'invite': InviteStatus;
};

interface WSMessage {
    cmd: string;
    data: {
        session_id?: string;
        identifying_code?: string;
        status_code?: string;
        message?: string;
    };
}

class WSClient {
    private emitter = mitt<Events>();
    private socket: WebSocket | null = null;
    private status: ConnectionStatus = 'disconnected';
    private aid: string = '';
    private isRunning: boolean = false;
    private isOnline: boolean = false;
    private wsUrl: string = '';
    private maxRetries: number = 5;
    private isNormalClose: boolean = false;
    private _isReconnecting: boolean = false;
    private options: WSClientOptions = {};
    private rawMessageCallback: ((message: any) => boolean) | null = null;
    private reconnectNeededCallback: (() => void) | null = null;
    private _isReconnectNeededRunning: boolean = false;

    constructor(options?: WSClientOptions) {
        this.options = options || {};
        this.maxRetries = this.options.maxRetries ?? 2;
    }

    /**
     * 检查 WebSocket 是否已连接
     */
    private isConnected(): boolean {
        return this.socket != null && this.socket.readyState === 1;
    }

    async connectToServer(wsServer: string, aid: string, sinature: string): Promise<void> {
        this.aid = aid;
        let url = wsServer.replace("https://", "wss://").replace("http://", "ws://")
        const encodedAid = encodeURIComponent(aid);
        const encodedSignature = encodeURIComponent(sinature);
        if (!this.isRunning) {
            url = `${url}/session?agent_id=${encodedAid}&signature=${encodedSignature}`;
            this.wsUrl = url;
            await this.connect();
        }
    }

    /**
     * 注册"快速重连全部失败"回调，通知上层需要重新鉴权
     */
    onReconnectNeeded(cb: () => void): void {
        this.reconnectNeededCallback = cb;
    }

    /**
     * 更新 WebSocket URL（上层重新获取 signature 后调用）
     */
    updateWsUrl(url: string): void {
        this.wsUrl = url;
    }

    /**
     * 重连 WebSocket（供外部调用，如心跳重连后触发）
     * 会关闭旧连接，重置状态，重新建立连接
     * @param newUrl 可选，传入新的 wsUrl（重新鉴权后使用）
     */
    async reconnect(newUrl?: string): Promise<void> {
        if (this._isReconnecting) {
            logger.log('[WS] 已在重连中，跳过');
            return;
        }
        if (!this.wsUrl && !newUrl) {
            logger.error('[WS] 重连失败: wsUrl 为空，尚未进行过初始连接');
            return;
        }
        this._isReconnecting = true;
        if (newUrl) {
            this.wsUrl = newUrl;
        }
        logger.log('[WS] 开始 WebSocket 重连...');

        try {
            // 关闭旧连接（标记为正常关闭，避免触发 onclose 重试）
            if (this.socket) {
                this.isNormalClose = true;
                try { this.socket.close(); } catch (_) {}
                this.socket = null;
            }
            this.isRunning = false;
            this.updateStatus('reconnecting');

            // 重新建立连接
            await this.connect();
            logger.log('[WS] WebSocket 重连成功');
        } catch (error) {
            logger.error('[WS] WebSocket 重连失败:', error);
            this.updateStatus('error');
        } finally {
            this._isReconnecting = false;
        }
    }

    createSession(cb: (status: ACPMessageSessionResponse) => void) {
        this.createSessionId();
        // 创建一个包装的回调函数，执行完后自动移除监听器
        const wrappedCallback = (status: ACPMessageSessionResponse) => {
            cb(status);
            this.emitter.off('session', wrappedCallback);
        };

        this.emitter.on('session', wrappedCallback);
    }

    invite(receiver: string, sessionId: string, identifyingCode: string, cb: (((status: InviteStatus) => void) | null) = null) {
        this.sendInviteMessage(receiver, sessionId, identifyingCode);

        if (cb) {
            // 创建一个包装的回调函数，执行完后自动移除监听器
            const wrappedCallback = (status: InviteStatus) => {
                cb(status);
                this.emitter.off('invite', wrappedCallback);
            };
            this.emitter.on('invite', wrappedCallback);
        }
    }

    onStatusChange(cb: (status: ConnectionStatus) => void) {
        this.emitter.on('status-change', cb);
    }

    onMessage(cb: (message: any) => void) {
        this.emitter.on('message', cb);
    }

    /**
     * 设置原始消息拦截器。回调函数返回 true 表示已处理（拦截），不再继续分发。
     */
    onRawMessage(cb: (message: any) => boolean) {
        this.rawMessageCallback = cb;
    }

    disconnect(): void {
        this.isRunning = false;
        this.isNormalClose = true;
        if (this.socket) {
            this.socket.close();
            this.socket = null;
        }
        this.emitter.all.clear();
    }


    /**
     * 发送原始消息（不做 URL 编码），用于群组协议等需要原始 JSON 的场景
     * @returns true 发送成功，false 连接未建立
     */
    sendRaw(message: string, to: string, sessionId: string): boolean {
        if (!this.isConnected()) {
            logger.error('[WS] sendRaw: WebSocket连接未建立或已断开');
            return false;
        }
        try {
            const msg = {
                cmd: "session_message",
                data: {
                    message_id: Date.now().toString(),
                    session_id: sessionId,
                    ref_msg_id: '',
                    sender: this.aid,
                    receiver: to,
                    message: message,  // 不做 encodeURIComponent
                    timestamp: Date.now().toString()
                }
            };
            // console.log(`[WS] sendRaw: sender=${this.aid} receiver=${to} sessionId=${sessionId} msgLen=${message.length}`);
            this.socket?.send(JSON.stringify(msg));
            return true;
        } catch (error) {
            logger.error('发送原始消息失败:', error);
            return false;
        }
    }

    send(message: string, to: string, sessionId: string, identifyingCode: string): void {
        if (!message || message.trim().length === 0) {
            logger.error('发送的消息不能为空');
            return;
        }

        if (!this.isConnected()) {
            const errorMessage = [{
                'content': 'WebSocket连接未建立或已断开'
            }];
            this.emitter.emit('message', {
                type: 'error',
                content: JSON.stringify(errorMessage)
            });
            return;
        }
        if (!this.isOnline) {
            const errorMessage = [{
                'content': `${to}不在线`
            }]
            this.emitter.emit('message', {
                type: 'error',
                content: JSON.stringify(errorMessage)
            });
            return;
        }
        try {
            const message_data = [{
                "type": "content",
                "status": "success",
                "timestamp": Date.now().toString(),
                "content": message
            }]
            const jsonMsg = JSON.stringify(message_data)
            const encodedMsg = encodeURIComponent(jsonMsg);
            const message_id = Date.now().toString();
            const msg = {
                cmd: "session_message",
                data: {
                    message_id: message_id,
                    session_id: sessionId,
                    ref_msg_id: '',
                    sender: this.aid,
                    receiver: to,
                    message: encodedMsg,
                    timestamp: Date.now().toString()
                }
            };
            this.socket?.send(JSON.stringify(msg));
        } catch (error) {
            logger.error('发送消息失败:', error);
            this.emitter.emit('message', {
                type: 'error',
                content: JSON.stringify([{ content: '发送消息失败' }])
            });
        }
    }

    connect(): Promise<void> {
        return new Promise((resolve, reject) => {
            let retryCount = 0;
            let resolved = false;
            const attemptConnect = () => {
                this.updateStatus('connecting');
                try {
                    // Node.js 环境下可配置 SSL 证书验证
                    if (isNodeEnvironment) {
                        const rejectUnauthorized = this.options.rejectUnauthorized ?? false;
                        const agent = new https.Agent({ rejectUnauthorized });
                        this.socket = new WebSocketImpl(this.wsUrl, { agent }) as unknown as WebSocket;
                    } else {
                        this.socket = new WebSocketImpl(this.wsUrl) as unknown as WebSocket;
                    }
                    this.socket.onopen = () => {
                        this.isRunning = true;
                        retryCount = 0;
                        this.updateStatus('connected');
                        if (!resolved) {
                            resolved = true;
                            resolve();
                        }
                    };
                    this.socket.onmessage = (event: MessageEvent) => {
                        try {
                            const data = JSON.parse(event.data);
                            this.handleMessage(data);
                        } catch (error) {
                            logger.error('解析消息失败:', error);
                        }
                    };

                    this.socket.onclose = (event: CloseEvent) => {
                        this.isRunning = false;
                        this.updateStatus('disconnected');

                        if (!this.isNormalClose && !event.wasClean && retryCount < this.maxRetries) {
                            retryCount++;
                            const retryDelay = retryCount * 1000;
                            logger.warn(`WebSocket连接断开，${retryDelay}ms后快速重试 (${retryCount}/${this.maxRetries})...`);
                            setTimeout(attemptConnect, retryDelay);
                        } else if (!this.isNormalClose && retryCount >= this.maxRetries) {
                            if (!resolved) {
                                // 首次连接就失败，直接 reject
                                resolved = true;
                                reject(new Error(`WebSocket连接失败，已达到最大重试次数 (${this.maxRetries})`));
                            } else if (
                                this.reconnectNeededCallback
                                && !this._isReconnectNeededRunning
                                && !this._isReconnecting  // 避免 reconnect() 内部的 connect() 失败再次触发，形成循环
                            ) {
                                // 曾经连接成功过、后来断开且快速重试耗尽 → 通知上层重新鉴权
                                logger.warn('[WS] 快速重试耗尽，触发 onReconnectNeeded 回调');
                                this._isReconnectNeededRunning = true;
                                // 回调可能是异步的，用 Promise 确保标志位在异步完成后才重置
                                Promise.resolve()
                                    .then(() => this.reconnectNeededCallback!())
                                    .catch((err) => logger.error('[WS] onReconnectNeeded 回调执行失败:', err))
                                    .finally(() => { this._isReconnectNeededRunning = false; });
                            }
                        }
                        this.isNormalClose = false;
                    };

                    this.socket.onerror = (error) => {
                        logger.error('WebSocket 错误:', {
                            error,
                            readyState: this.socket?.readyState,
                            url: this.wsUrl,
                        });
                        this.updateStatus('error');
                        // WebSocket.OPEN = 1
                        if (this.socket?.readyState === 1) {
                            this.socket.close(); // 主动触发 onclose
                        }
                    };
                } catch (err) {
                    logger.error('创建 WebSocket 实例失败:', err);
                    this.updateStatus('error');
                    if (retryCount < this.maxRetries) {
                        retryCount++;
                        const retryDelay = retryCount * 1000;
                        logger.warn(`创建失败，${retryCount}秒后重试...`);
                        setTimeout(attemptConnect, retryDelay);
                    } else {
                        if (!resolved) {
                            resolved = true;
                            reject(new Error(`创建 WebSocket 实例失败，已达到最大重试次数 (${this.maxRetries})`));
                        }
                    }
                }
            };

            attemptConnect();
        });
    }


    /**
     * 获取当前WebSocket连接状态
     * @returns 当前连接状态
     */
    public getCurrentStatus(): ConnectionStatus {
        return this.status;
    }

    private updateStatus(newStatus: ConnectionStatus) {
        if (this.status !== newStatus) {
            this.status = newStatus;
            this.emitter.emit('status-change', newStatus);
        }
    }

    private createSessionId() {
        if (!this.isConnected()) {
            logger.error('WebSocket连接未建立，无法创建会话');
            return;
        }
        try {
            const msg = {
                cmd: "create_session_req",
                data: {
                    request_id: uuidv4().replace(/-/g, ''),
                    type: "public",
                    group_name: "1",
                    subject: "",
                    timestamp: Date.now().toString()
                }
            };
            this.socket!.send(JSON.stringify(msg));
        } catch (error) {
            logger.error('发送创建会话请求失败:', error);
        }
    }

    private sendInviteMessage(receiver: string, sessionId: string, identifyingCode: string) {
        if (!receiver || !sessionId || !identifyingCode) {
            logger.error('邀请参数不完整');
            return;
        }

        if (!this.isConnected()) {
            logger.error('WebSocket连接未建立，无法发送邀请');
            return;
        }
        try {
            const msg = {
                cmd: "invite_agent_req",
                data: {
                    request_id: uuidv4().replace(/-/g, ''),
                    acceptor_id: receiver,
                    invite_code: identifyingCode,
                    session_id: sessionId,
                    inviter_id: this.aid
                }
            };
            this.socket?.send(JSON.stringify(msg));
        } catch (error) {
            logger.error('发送邀请失败:', error);
        }
    }

    private handleMessage(message: WSMessage): void {
        const { cmd, data } = message;

        // Raw message interception: allow group protocol routing etc.
        if (cmd === "session_message" && this.rawMessageCallback) {
            const intercepted = this.rawMessageCallback(message);
            if (intercepted) {
                return; // intercepted
            }
        }

        if (cmd === "create_session_ack") {
            const { session_id, identifying_code } = data;
            this.emitter.emit('session', {
                sessionId: session_id ?? '',
                identifyingCode: identifying_code ?? ''
            })
        }
        else if (cmd === "invite_agent_ack") {
            const { status_code } = data;
            if (Number(status_code) === 200) {
                this.isOnline = true;
            } else {
                this.isOnline = false;
            }
            this.emitter.emit('invite', this.isOnline ? 'success' : 'error');
        }
        else if (cmd === "invite_agent_req") {
            // 收到邀请请求，自动接受
            const { session_id, inviter_id, invite_code } = data as any;
            logger.log(`收到来自 ${inviter_id} 的会话邀请，会话ID: ${session_id}`);
            this.acceptInvite(session_id, inviter_id, invite_code);
        }
        else if (cmd === "session_message") {
            this.emitter.emit('message', message)
        }
    }

    private acceptInvite(sessionId: string, inviterId: string, inviteCode: string): void {
        if (!this.isConnected()) {
            logger.error('WebSocket连接未建立，无法接受邀请');
            return;
        }
        try {
            const msg = {
                cmd: "join_session_req",
                data: {
                    session_id: sessionId,
                    request_id: uuidv4().replace(/-/g, ''),
                    inviter_agent_id: inviterId,
                    invite_code: inviteCode,
                    last_msg_id: "0"
                }
            };
            this.socket!.send(JSON.stringify(msg));
            logger.log(`已接受会话邀请: ${sessionId}`);
            this.isOnline = true;
        } catch (error) {
            logger.error('接受邀请失败:', error);
        }
    }

    /**
     * 公开方法：接受来自心跳通道的邀请
     * 当心跳客户端收到邀请时，调用此方法通过 WebSocket 加入会话
     */
    public acceptInviteFromHeartbeat(sessionId: string, inviterId: string, inviteCode: string): void {
        logger.log(`[WebSocket] 通过心跳通道收到邀请，加入会话: ${sessionId}`);
        this.acceptInvite(sessionId, inviterId, inviteCode);
    }
}

export { WSClient };
export type { ACPMessageSessionResponse, ConnectionStatus, InviteStatus };