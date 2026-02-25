import * as dgram from 'dgram';
import { signIn } from './api';
import { getPublicKeyPem } from './cert';
import { getDecryptKey , logger } from './utils';
import {
    HeartbeatMessageReq,
    HeartbeatMessageResp,
    InviteMessageReq,
    InviteMessageResp,
    UdpMessageHeader,
    MessageType
} from './message_serialize';

export type HeartbeatStatus = 'offline' | 'connecting' | 'online' | 'reconnecting' | 'error';

export interface InviteInfo {
    inviterAgentId: string;
    inviteCode: string;
    sessionId: string;
    messageServer: string;
}

export class HeartbeatClient {
    // 重连相关常量
    private static readonly MAX_SEND_FAILURES = 3;
    private static readonly MAX_RECV_FAILURES = 3;
    private static readonly MAX_MISSED_HEARTBEATS = 6;
    private static readonly RECONNECT_BACKOFF_MAX = 30000;
    private static readonly SOCKET_TIMEOUT = 1000;

    private agentId: string;
    private serverUrl: string;
    private seedPassword: string;

    private serverIp: string = '127.0.0.1';
    private port: number = 0;
    private signCookie: number = 0;
    private signature: string = '';

    private udpSocket: dgram.Socket | null = null;
    private heartbeatInterval: number = 5000;
    private isRunning: boolean = false;
    private isSendingHeartbeat: boolean = false;

    private msgSeq: number = 0;
    private lastHb: number = 0;
    private lastHbRecv: number = 0;

    private sendFailures: number = 0;
    private recvFailures: number = 0;
    private lastReconnectTs: number = 0;
    private isReconnecting: boolean = false;

    private sendTimer: NodeJS.Timeout | null = null;
    private status: HeartbeatStatus = 'offline';

    // 回调函数
    private onStatusChangeCallback: ((status: HeartbeatStatus) => void) | null = null;
    private onInviteCallback: ((invite: InviteInfo) => void) | null = null;
    private onReconnectCallback: (() => void) | null = null;

    constructor(agentId: string, serverUrl: string, seedPassword: string) {
        this.agentId = agentId;
        this.serverUrl = serverUrl;
        this.seedPassword = seedPassword;
    }

    /**
     * 设置状态变更回调
     */
    public onStatusChange(callback: (status: HeartbeatStatus) => void): void {
        this.onStatusChangeCallback = callback;
    }

    /**
     * 设置邀请回调
     */
    public onInvite(callback: (invite: InviteInfo) => void): void {
        this.onInviteCallback = callback;
    }

    /**
     * 设置重连成功回调
     * 当心跳重连成功后触发，用于通知外部组件（如 WebSocket）也进行重连
     */
    public onReconnect(callback: () => void): void {
        this.onReconnectCallback = callback;
    }

    /**
     * 获取当前状态
     */
    public getStatus(): HeartbeatStatus {
        return this.status;
    }

    private updateStatus(newStatus: HeartbeatStatus): void {
        if (this.status !== newStatus) {
            this.status = newStatus;
            if (this.onStatusChangeCallback) {
                this.onStatusChangeCallback(newStatus);
            }
        }
    }

    /**
     * 登录心跳服务器
     */
    public async signIn(): Promise<boolean> {
        try {
            const privateKey = await getDecryptKey(this.agentId, this.seedPassword);
            if (!privateKey) {
                logger.error('[Heartbeat] 获取私钥失败');
                return false;
            }

            const { publicKeyPem, certPem } = await getPublicKeyPem(this.agentId);
            if (!certPem) {
                logger.error('[Heartbeat] 获取证书失败');
                return false;
            }

            // 确保使用 HTTPS
            let serverUrl = this.serverUrl;
            if (serverUrl.startsWith('http://')) {
                serverUrl = serverUrl.replace('http://', 'https://');
            }
            const result = await signIn(this.agentId, serverUrl, privateKey, publicKeyPem, certPem);

            if (!result || !result.signData) {
                logger.error('[Heartbeat] signIn 失败');
                return false;
            }

            const { server_ip, port, sign_cookie, signature } = result.signData;

            if (!server_ip || !port || sign_cookie === undefined) {
                logger.error('[Heartbeat] signIn 返回数据不完整');
                return false;
            }

            this.serverIp = server_ip;
            this.port = parseInt(port, 10);
            this.signCookie = parseInt(sign_cookie, 10);
            this.signature = signature || '';

                logger.log(`[Heartbeat] signIn 成功: ${this.serverIp}:${this.port}`);
            return true;
        } catch (error) {
            logger.error('[Heartbeat] signIn 异常:', error);
            return false;
        }
    }

    /**
     * 创建 UDP socket
     */
    private createSocket(): void {
        this.closeSocket();

        this.udpSocket = dgram.createSocket('udp4');

        this.udpSocket.on('message', (msg, rinfo) => {
            this.handleMessage(msg);
        });

        this.udpSocket.on('error', (err) => {
            logger.error('[Heartbeat] Socket 错误:', err);
            this.recvFailures++;
            if (this.recvFailures >= HeartbeatClient.MAX_RECV_FAILURES) {
                this.reconnect('recv_failures_threshold');
            }
        });

        this.udpSocket.on('close', () => {
            // Socket 已关闭
        });

        // 绑定到随机端口
        this.udpSocket.bind(0, '0.0.0.0', () => {
            // Socket 绑定成功
        });
    }

    /**
     * 关闭 socket
     */
    private closeSocket(): void {
        if (this.udpSocket) {
            try {
                this.udpSocket.close();
            } catch (e) {
                // 忽略关闭错误
            }
            this.udpSocket = null;
        }
    }

    /**
     * 处理接收到的消息
     */
    private handleMessage(data: Buffer): void {
        try {
            const { header } = UdpMessageHeader.deserialize(data, 0);

            if (header.MessageType === MessageType.HEARTBEAT_RESP) {
                // 心跳响应
                const { resp } = HeartbeatMessageResp.deserialize(data, 0);
                this.lastHbRecv = Date.now();
                this.recvFailures = 0;

                // 检查是否需要重新认证
                if (resp.NextBeat === 401) {
                    logger.warn('[Heartbeat] 收到 401，需要重新认证');
                    this.reconnect('401_auth_failed');
                    return;
                }

                // 更新心跳间隔
                if (resp.NextBeat > 0 && resp.NextBeat !== 401) {
                    this.heartbeatInterval = Math.max(resp.NextBeat, 5000);
                }

            } else if (header.MessageType === MessageType.INVITE_REQ) {
                // 邀请请求
                const { req } = InviteMessageReq.deserialize(data, 0);
                logger.log(`[Heartbeat] 收到邀请请求: inviter=${req.InviterAgentId}, session=${req.SessionId}`);

                // 发送邀请响应
                this.sendInviteResponse(req);

                // 触发回调
                if (this.onInviteCallback) {
                    this.onInviteCallback({
                        inviterAgentId: req.InviterAgentId,
                        inviteCode: req.InviteCode,
                        sessionId: req.SessionId,
                        messageServer: req.MessageServer
                    });
                }
            }
        } catch (error) {
            logger.error('[Heartbeat] 处理消息异常:', error);
        }
    }

    /**
     * 发送邀请响应
     */
    private sendInviteResponse(inviteReq: InviteMessageReq): void {
        if (!this.udpSocket) return;

        try {
            this.msgSeq++;

            const resp = new InviteMessageResp();
            resp.header.MessageMask = 0;
            resp.header.MessageSeq = this.msgSeq;
            resp.header.MessageType = MessageType.INVITE_RESP;
            resp.header.PayloadSize = 0;
            resp.AgentId = this.agentId;
            resp.InviterAgentId = inviteReq.InviterAgentId;
            resp.SessionId = inviteReq.SessionId;
            resp.SignCookie = this.signCookie;

            const data = resp.serialize();
            this.udpSocket.send(data, this.port, this.serverIp, (err) => {
                if (err) {
                    logger.error('[Heartbeat] 发送邀请响应失败:', err);
                } else {
                    logger.log('[Heartbeat] 邀请响应已发送');
                }
            });
        } catch (error) {
            logger.error('[Heartbeat] 发送邀请响应异常:', error);
        }
    }

    /**
     * 发送心跳
     */
    private sendHeartbeat(): void {
        if (!this.udpSocket || !this.isRunning || !this.isSendingHeartbeat || this.isReconnecting) {
            return;
        }

        const now = Date.now();

        // 检查心跳响应超时
        if (this.lastHbRecv > 0) {
            const timeoutThreshold = HeartbeatClient.MAX_MISSED_HEARTBEATS * this.heartbeatInterval;
            if (now - this.lastHbRecv > timeoutThreshold) {
                logger.warn(`[Heartbeat] 心跳响应超时: ${now - this.lastHbRecv}ms > ${timeoutThreshold}ms`);
                this.reconnect('heartbeat_response_timeout');
                return;
            }
        }

        // 检查是否需要发送心跳
        if (now < this.lastHb + this.heartbeatInterval) {
            return;
        }

        try {
            this.msgSeq++;
            this.lastHb = now;

            const req = new HeartbeatMessageReq();
            req.header.MessageMask = 0;
            req.header.MessageSeq = this.msgSeq;
            req.header.MessageType = MessageType.HEARTBEAT_REQ;
            req.header.PayloadSize = 100;
            req.AgentId = this.agentId;
            req.SignCookie = this.signCookie;

            const data = req.serialize();

            this.udpSocket.send(data, this.port, this.serverIp, (err) => {
                if (err) {
                    logger.error('[Heartbeat] 发送心跳失败:', err);
                    this.sendFailures++;
                    if (this.sendFailures >= HeartbeatClient.MAX_SEND_FAILURES) {
                        this.reconnect('send_failures_threshold');
                    }
                } else {
                    this.sendFailures = 0;
                }
            });
        } catch (error) {
            logger.error('[Heartbeat] 发送心跳异常:', error);
            this.sendFailures++;
        }
    }

    /**
     * 重连
     */
    private async reconnect(reason: string): Promise<boolean> {
        if (!this.isRunning || this.isReconnecting) {
            return false;
        }

        this.isReconnecting = true;
        this.updateStatus('reconnecting');

        try {
            const now = Date.now();
            const elapsed = now - this.lastReconnectTs;

            // 限流：至少间隔 5 秒
            if (elapsed < 5000) {
                const backoff = Math.min(5000 - elapsed, HeartbeatClient.RECONNECT_BACKOFF_MAX);
                logger.log(`[Heartbeat] 重连退避: ${backoff}ms`);
                await new Promise(resolve => setTimeout(resolve, backoff));
            }

            logger.log(`[Heartbeat] 开始重连，原因: ${reason}`);
            this.lastReconnectTs = Date.now();

            // 重新登录
            if (!await this.signIn()) {
                logger.error('[Heartbeat] 重连失败: signIn 返回 false');
                this.updateStatus('error');
                // 重置 lastHbRecv 避免下次 tick 立即再次触发重连
                this.lastHbRecv = Date.now();
                return false;
            }

            // 重建 socket
            this.createSocket();

            // 重置状态
            this.sendFailures = 0;
            this.recvFailures = 0;
            this.lastHbRecv = Date.now();

            logger.log('[Heartbeat] 重连成功');
            this.updateStatus('online');

            // 通知外部组件（如 WebSocket）进行重连
            if (this.onReconnectCallback) {
                try {
                    this.onReconnectCallback();
                } catch (e) {
                    logger.error('[Heartbeat] onReconnect 回调异常:', e);
                }
            }

            return true;
        } catch (error) {
            logger.error('[Heartbeat] 重连异常:', error);
            this.updateStatus('error');
            return false;
        } finally {
            this.isReconnecting = false;
        }
    }

    /**
     * 上线
     */
    public async online(): Promise<boolean> {
        if (this.isRunning) {
            logger.log('[Heartbeat] 已经在线');
            return true;
        }

        this.updateStatus('connecting');

        // 登录
        if (!await this.signIn()) {
            this.updateStatus('error');
            return false;
        }

        // 创建 socket
        this.createSocket();

        // 初始化状态
        this.lastHbRecv = Date.now();
        this.isRunning = true;
        this.isSendingHeartbeat = true;

        // 启动心跳定时器
        this.sendTimer = setInterval(() => {
            this.sendHeartbeat();
        }, 1000);

        // 立即发送一次心跳
        this.sendHeartbeat();

        this.updateStatus('online');
        return true;
    }

    /**
     * 离线
     */
    public offline(): void {
        this.isRunning = false;
        this.isSendingHeartbeat = false;

        // 停止定时器
        if (this.sendTimer) {
            clearInterval(this.sendTimer);
            this.sendTimer = null;
        }

        // 关闭 socket
        this.closeSocket();

        this.updateStatus('offline');
    }

    /**
     * 查询在线状态
     */
    public async getOnlineStatus(aids: string[]): Promise<any[]> {
        try {
            const axios = (await import('axios')).default;
            const epUrl = `${this.serverUrl}/query_online_state`;
            const data = {
                agent_id: this.agentId,
                signature: this.signature,
                agents: aids
            };

            const response = await axios.post(epUrl, data, { timeout: 10000 });
            if (response.status === 200) {
                return response.data.data || [];
            }
            return [];
        } catch (error) {
            logger.error('[Heartbeat] 查询在线状态异常:', error);
            return [];
        }
    }
}
