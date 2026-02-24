import { getPublicKeyPem, isPemValid, preloadCrypto } from "./cert";
import { CertAndKeyStore, DEFAULT_ACP_DIR } from "./datamanager";
import * as fs from "fs";
import * as path from "path";
import { getEntryPointConfig, getGuestAid, signIn } from "./api";
import { IAgentCP, IAgentIdentity } from "./interfaces";
import { createAid, getDecryptKey, logger } from "./utils";
import { MessageStore } from "./messagestore";
import { FileSync } from "./filesync";
import { AgentMdOptions, generateAgentMd } from "./agentmd";
import { ACPGroupClient, GroupOperations, ACPGroupEventHandler, CursorStore, GroupMessageStore, GroupMessage, GroupMessageBatch } from "./group";

class AgentCP implements IAgentCP {
    private seedPassword: string;
    private apUrl: string;
    private msgUrl: string;
    private activeAid: string = '';
    private _basePath: string;
    private _messageStore: MessageStore;
    private agentMdPath: string | null = null;
    private agentMdUploaded: boolean = false;
    private autoGenerateAgentMd: boolean = false;
    private agentMdOptions: Partial<AgentMdOptions> = {};

    // Group client properties
    groupClient: ACPGroupClient | null = null;
    groupOps: GroupOperations | null = null;
    groupMessageStore: GroupMessageStore | null = null;
    private _groupTargetAid: string = '';
    private _groupSessionId: string = '';
    private _persistGroupMessages: boolean = true;

    // Group lifecycle management
    private _onlineGroups: Set<string> = new Set();
    private _heartbeatTimer: ReturnType<typeof setInterval> | null = null;
    private _heartbeatIntervalMs: number = 180_000; // 3 minutes

    get messageStore(): MessageStore {
        return this._messageStore;
    }

    constructor(
        apiUrl: string,
        seedPassword: string = "",
        basePath?: string,
        options?: { persistMessages?: boolean; persistGroupMessages?: boolean }
    ) {
        if (!apiUrl) {
            this.handleError("参数缺失：apiUrl不应为空");
        }
        if (apiUrl.startsWith('http://')) {
            this.handleError("apiUrl不需要http://开头");
        }
        if (basePath) {
            CertAndKeyStore.setBasePath(basePath);
        }
        const baseUrl = `https://acp3.${apiUrl}`
        this.seedPassword = seedPassword;
        this._basePath = basePath || DEFAULT_ACP_DIR;
        this.apUrl = `${baseUrl}/api/accesspoint`;
        this.msgUrl = `${baseUrl}/api/message`;
        this._persistGroupMessages = options?.persistGroupMessages ?? true;

        this._messageStore = new MessageStore({
            persistMessages: options?.persistMessages ?? false,
            basePath: this._basePath,
        });

        // 预热加密模块
        this.initializeCrypto();
    }

    /**
     * 初始化并预热加密模块
     */
    private async initializeCrypto(): Promise<void> {
        try {
            await preloadCrypto();
        } catch (error) {
            logger.warn('AgentCP 加密模块预热失败:', error);
        }
    }

    /// 导入本地用户信息
    public async importAid(
        identity: IAgentIdentity,
        seedPassword: string = ""): Promise<boolean> {
        this.seedPassword = seedPassword;
        const { aid, privateKey, certPem } = identity;
        try {
            if (!aid || !privateKey || !certPem) {
                this.handleError("参数缺失：aid、privateKey 或 certPem 不应为空");
            }
            const isValid = isPemValid(certPem);
            if (!isValid) {
                this.handleError("证书已过期");
            }
            await CertAndKeyStore.saveAid(aid);
            await CertAndKeyStore.saveCertificate(aid, certPem);
            await CertAndKeyStore.savePrivateKey(aid, privateKey);
            this.activeAid = aid;
            return true;
        } catch (err) {
            this.handleError(`错误: ${err instanceof Error ? err.message : String(err)}`);
        }
    }

    public async loadAid(aid: string): Promise<string | null> {
        const aids = await CertAndKeyStore.getAids();
        if (aids && aids.length > 0) {
            if (aids.includes(aid)) {
                this.activeAid = aid;
                return aid;
            }
        }
        return null;
    }

    public async createAid(aid: string): Promise<string> {
        const loaded = await this.loadAid(aid);
        if (loaded) {
            this.activeAid = loaded;
            return loaded;
        }
        const created = await createAid(aid, this.apUrl, this.seedPassword);
        if (!created) {
            this.handleError(`当前aid: ${aid}创建失败`);
        }
        this.activeAid = aid;
        return aid;
    }

    public async loadCurrentAid(): Promise<string | null> {
        const aids = await CertAndKeyStore.getAids();
        if (aids && aids.length > 0) {
            let currentAid = aids[0];
            const firstNonGuestAid = aids.find((aid: string) => !aid.startsWith('guest'));
            if (firstNonGuestAid) {
                currentAid = firstNonGuestAid;
            }
            return this.loadAid(currentAid);
        } else {
            return null
        }
    }

    public async loadGuestAid(): Promise<string> {
        const loaded = await getGuestAid(this.apUrl, this.seedPassword);
        if (!loaded) {
            this.handleError('加载aid失败');
        }
        this.activeAid = loaded;
        return loaded;
    }

    public async loadAidList(): Promise<string[] | null> {
        const aids = await CertAndKeyStore.getAids();
        if (aids) {
            return aids;
        } else {
            return null;
        }
    }

    public async online(): Promise<{
        messageSignature: string,
        messageServer: string,
        heartbeatServer: string,
    }> {
        let messageSignature = '';
        let messageServer = '';
        let heartbeatServer = '';
        const aid = this.activeAid;

        if (!aid) {
            this.handleError('请先加载或创建 AID');
        }

        const privateKey = await getDecryptKey(aid, this.seedPassword);
        if (!privateKey) {
            this.handleError('私钥不存在或无效，请检查 AID 是否正确创建');
        }
        const {publicKeyPem, certPem} = await getPublicKeyPem(aid);
        if (!certPem) {
            this.handleError('证书不存在，请重新创建 AID');
        }

        const apData = await signIn(aid, this.apUrl, privateKey, publicKeyPem, certPem);
        if (!apData) {
            this.handleError(`${this.apUrl}接口signIn失败`);
        }
        const epData = await getEntryPointConfig(aid, this.apUrl);
        if (!epData) {
            this.handleError("接入点服务器get_accesspoint_config获取数据失败");
        } else {
            if (epData) {
                messageServer = epData.messageServer;
                heartbeatServer = epData.heartbeatServer;
            }
        }
        const msgData = await signIn(aid, this.msgUrl, privateKey, publicKeyPem, certPem);
        if (!msgData) {
            this.handleError(`${this.msgUrl}接口signIn失败`);
        } else {
            messageSignature = msgData.signature ?? '';
        }

        // 登录成功后自动上传 agent.md（仅首次）
        if (this.agentMdPath && !this.agentMdUploaded) {
            try {
                const fileSync = new FileSync({
                    apiUrl: this.msgUrl,
                    aid: this.activeAid,
                    signature: messageSignature,
                });
                const result = await fileSync.uploadAgentMdFromFile(this.agentMdPath);
                if (result.success) {
                    this.agentMdUploaded = true;
                } else {
                    logger.warn('agent.md 上传失败:', result.error);
                }
            } catch (err) {
                logger.warn('agent.md 上传异常:', err);
            }
        }

        // 自动生成并上传 agent.md（仅当未设置自定义路径且启用了自动生成时）
        if (!this.agentMdPath && this.autoGenerateAgentMd && !this.checkAgentMdMarker(aid)) {
            try {
                const content = generateAgentMd({ aid, ...this.agentMdOptions });
                const fileSync = new FileSync({
                    apiUrl: this.msgUrl,
                    aid: this.activeAid,
                    signature: messageSignature,
                });
                const result = await fileSync.uploadAgentMd(content);
                if (result.success) {
                    this.saveAgentMdMarker(aid);
                    logger.log(`agent.md 自动生成并上传成功: ${aid}`);
                } else {
                    logger.warn('agent.md 自动上传失败:', result.error);
                }
            } catch (err) {
                logger.warn('agent.md 自动生成异常:', err);
            }
        }

        return {
            messageSignature,
            messageServer,
            heartbeatServer
        }
    }

    async getCertInfo(aid: string): Promise<{
        privateKey: string;
        publicKey: string;
        csr: string;
        cert: string;
    } | null> {
        const csr = await CertAndKeyStore.getCsr(aid);
        const privateKey = await CertAndKeyStore.getPrivateKey(aid);
        const {publicKeyPem, certPem} = await getPublicKeyPem(aid);
        if (!certPem || !csr || !privateKey || !publicKeyPem) {
            return null;
        }
        return {
            privateKey,
            publicKey: publicKeyPem,
            csr,
            cert: certPem
        }
    }

    public setAgentMdPath(filePath: string): void {
        this.agentMdPath = filePath;
    }

    public async resetAgentMdUploadStatus(): Promise<void> {
        this.agentMdUploaded = false;
    }

    public setAutoGenerateAgentMd(enable: boolean): void {
        this.autoGenerateAgentMd = enable;
    }

    public setAgentMdOptions(options: Partial<AgentMdOptions>): void {
        this.agentMdOptions = options;
    }

    private getAgentMdMarkerPath(aid: string): string {
        const aidsDir = CertAndKeyStore.getAIDsDir();
        return path.join(aidsDir, aid, '.agentmd-uploaded');
    }

    private checkAgentMdMarker(aid: string): boolean {
        try {
            return fs.existsSync(this.getAgentMdMarkerPath(aid));
        } catch {
            return false;
        }
    }

    private saveAgentMdMarker(aid: string): void {
        try {
            fs.writeFileSync(this.getAgentMdMarkerPath(aid), new Date().toISOString(), 'utf-8');
        } catch (err) {
            logger.warn('保存 agent.md 标记文件失败:', err);
        }
    }

    // ============================================================
    // Group Client Integration
    // ============================================================

    /**
     * 获取群组目标AID
     */
    public getGroupTargetAid(): string {
        return this._groupTargetAid;
    }

    /**
     * 初始化群组客户端。
     * 需要外部提供 sendRaw 函数和 sessionId，因为 AgentCP 本身不管理 WebSocket 连接。
     *
     * @param sendRaw 发送原始消息的函数: (message, to, sessionId) => void
     * @param sessionId 与 group.{issuer} 的会话ID
     * @param targetAid 目标群组AID，默认 "group.{issuer}"
     */
    public initGroupClient(
        sendRaw: (message: string, to: string, sessionId: string) => void,
        sessionId: string,
        targetAid?: string,
    ): void {
        if (!targetAid) {
            const parts = this.activeAid.split(".", 1);
            const issuer = this.activeAid.substring(parts[0].length + 1) || this.activeAid;
            targetAid = `group.${issuer}`;
        }
        this._groupTargetAid = targetAid;
        this._groupSessionId = sessionId;

        const sendFunc = (target: string, payload: string): void => {
            sendRaw(payload, target, this._groupSessionId);
        };

        this.groupClient = new ACPGroupClient(this.activeAid, sendFunc);
        this.groupOps = new GroupOperations(this.groupClient);

        // 设置默认 event handler，防止通知被静默丢弃
        this.groupClient.setEventHandler(this._createDefaultGroupEventHandler());
    }

    /**
     * 初始化跨AP群组客户端。
     *
     * @param sendRaw 发送原始消息的函数
     * @param sessionId 与目标群组AID的会话ID
     * @param targetAid 目标群组AID (如 "group.aid.com")
     */
    public initGroupClientCrossAp(
        sendRaw: (message: string, to: string, sessionId: string) => void,
        sessionId: string,
        targetAid: string,
    ): void {
        this._groupTargetAid = targetAid;
        this._groupSessionId = sessionId;

        const sendFunc = (target: string, payload: string): void => {
            sendRaw(payload, target, this._groupSessionId);
        };

        this.groupClient = new ACPGroupClient(this.activeAid, sendFunc);
        this.groupOps = new GroupOperations(this.groupClient);

        // 设置默认 event handler，防止通知被静默丢弃
        this.groupClient.setEventHandler(this._createDefaultGroupEventHandler());
    }
    /**
     * 处理群组协议消息路由。
     * 当收到 session_message 时，检查 sender 是否为群组目标AID，
     * 如果是则路由到 groupClient.handleIncoming()。
     *
     * @returns true 如果消息被群组客户端处理
     */
    public handleGroupMessage(message: any): boolean {
        if (this.groupClient == null || !this._groupTargetAid) {
            logger.log(`[Group] handleGroupMessage skipped: groupClient=${this.groupClient != null}, targetAid=${this._groupTargetAid}`);
            return false;
        }
        const data = message.data || message;
        const sender = data.sender ?? "";
        if (sender === this._groupTargetAid) {
            try {
                const rawMsg = data.message ?? "";
                if (typeof rawMsg === 'string' && rawMsg) {
                    logger.log(`[Group] handleGroupMessage: routing to groupClient, sender=${sender} msgLen=${rawMsg.length}`);
                    this.groupClient.handleIncoming(rawMsg);
                } else {
                    logger.warn(`[Group] rawMsg is not a non-empty string, skipping handleIncoming. type=${typeof rawMsg}`);
                }
                return true;
            } catch (e) {
                logger.error("[Group] handleIncoming error:", e);
                return true;
            }
        }
        return false;
    }

    /**
     * 设置群组事件处理器
     */
    public setGroupEventHandler(handler: ACPGroupEventHandler): void {
        if (this.groupClient) {
            this.groupClient.setEventHandler(handler);
        }
    }

    /**
     * 创建默认的群组事件处理器。
     * - onGroupMessageBatch: 自动存储消息 + watermark ACK
     * - onJoinApproved: 自动注册到 Home AP + 存储群组
     * 外部可通过 setGroupEventHandler 覆盖。
     */
    private _createDefaultGroupEventHandler(): ACPGroupEventHandler {
        return {
            onNewMessage(groupId, latestMsgId, sender, preview) {
                logger.log(`[Group][DefaultHandler] onNewMessage: group=${groupId} msgId=${latestMsgId} sender=${sender} preview=${preview}`);
            },
            onNewEvent(groupId, latestEventId, eventType, summary) {
                logger.log(`[Group][DefaultHandler] onNewEvent: group=${groupId} eventId=${latestEventId} type=${eventType}`);
            },
            onGroupInvite(groupId, groupAddress, invitedBy) {
                logger.log(`[Group][DefaultHandler] onGroupInvite: group=${groupId} address=${groupAddress} invitedBy=${invitedBy}`);
            },
            onJoinApproved: (groupId, groupAddress) => {
                logger.log(`[Group][DefaultHandler] onJoinApproved: group=${groupId} address=${groupAddress}`);
                (async () => {
                    try {
                        if (!this.groupOps || !this._groupTargetAid) {
                            logger.warn(`[Group][DefaultHandler] onJoinApproved skipped: groupOps or targetAid not available`);
                            return;
                        }
                        let groupName = groupId;
                        try {
                            const info = await this.groupOps.getGroupInfo(this._groupTargetAid, groupId);
                            groupName = info.name || groupId;
                        } catch (_) {}
                        this.addGroupToStore(groupId, groupName);
                    } catch (e: any) {
                        logger.error(`[Group][DefaultHandler] onJoinApproved processing failed: group=${groupId}`, e.message);
                    }
                })();
            },
            onJoinRejected(groupId, reason) {
                logger.log(`[Group][DefaultHandler] onJoinRejected: group=${groupId} reason=${reason}`);
            },
            onJoinRequestReceived(groupId, agentId, message) {
                logger.log(`[Group][DefaultHandler] onJoinRequestReceived: group=${groupId} agent=${agentId}`);
            },
            onGroupMessageBatch: (groupId, batch) => {
                logger.log(`[Group][DefaultHandler] onGroupMessageBatch: group=${groupId} count=${batch.count} range=[${batch.start_msg_id}, ${batch.latest_msg_id}]`);
                this.processAndAckBatch(groupId, batch).catch(e => {
                    logger.error(`[Group][DefaultHandler] processAndAckBatch failed: group=${groupId}`, e);
                });
            },
            onGroupEvent(groupId, evt) {
                logger.log(`[Group][DefaultHandler] onGroupEvent: group=${groupId} event=${evt.event_type}`);
            },
        };
    }

    /**
     * 处理批量推送消息：排序、存储、ACK 最后一条。
     * 返回排序后的消息列表，供上层使用（如推送给浏览器）。
     */
    public async processAndAckBatch(groupId: string, batch: GroupMessageBatch): Promise<GroupMessage[]> {
        const batchMessages = batch.messages || [];
        const sorted = [...batchMessages].sort((a, b) => a.msg_id - b.msg_id);
        logger.log(`[AgentCP] processAndAckBatch: group=${groupId} batchCount=${batchMessages.length} sortedCount=${sorted.length} msgIds=[${sorted.map(m => m.msg_id).join(',')}]`);

        const storeExists = !!this.groupMessageStore;
        const storeGroupExists = storeExists ? !!this.groupMessageStore!.getGroup(groupId) : false;
        logger.log(`[AgentCP] processAndAckBatch: storeExists=${storeExists} storeGroupExists=${storeGroupExists} lastMsgId=${this.getGroupLastMsgId(groupId)}`);

        await this.addGroupMessagesToStore(groupId, sorted);

        // ACK batch 中最后一条消息
        if (sorted.length > 0) {
            const lastMsgId = sorted[sorted.length - 1].msg_id;
            this._ackMessage(groupId, lastMsgId);
        }

        return sorted;
    }

    /**
     * 异步 ACK 消息（不阻塞调用方）
     */
    private _ackMessage(groupId: string, msgId: number): void {
        if (!this.groupOps || !this._groupTargetAid) return;
        this.groupOps.ackMessages(this._groupTargetAid, groupId, msgId).catch(e => {
            logger.warn(`[Group] ack failed: group=${groupId} msgId=${msgId}`, e.message || e);
        });
    }

    /**
     * 设置群组游标存储
     */
    public setGroupCursorStore(store: CursorStore): void {
        if (this.groupClient) {
            this.groupClient.setCursorStore(store);
        }
    }

    /**
     * 关闭群组客户端。
     * 自动停止心跳、清理在线群组状态。
     */
    public closeGroupClient(): void {
        this._stopHeartbeat();
        this._onlineGroups.clear();

        if (this.groupClient) {
            try {
                this.groupClient.close();
            } catch (e) {
                logger.error("[Group] group_client close error:", e);
            }
            this.groupClient = null;
            this.groupOps = null;
        }
    }

    /**
     * 初始化群消息持久化存储
     */
    public async initGroupMessageStore(options?: {
        maxMessagesPerGroup?: number;
        maxEventsPerGroup?: number;
    }): Promise<void> {
        this.groupMessageStore = new GroupMessageStore({
            persistMessages: this._persistGroupMessages,
            basePath: this._basePath,
            maxMessagesPerGroup: options?.maxMessagesPerGroup,
            maxEventsPerGroup: options?.maxEventsPerGroup,
        });
        if (this.activeAid) {
            try {
                await this.groupMessageStore.loadGroupsForAid(this.activeAid);
            } catch (e) {
                logger.warn('[AgentCP] 加载群消息存储失败:', e);
            }
        }
    }

    /**
     * 确保群消息持久化存储已初始化并加载完成。
     * 如果已初始化则直接返回，否则初始化并等待磁盘数据加载完成。
     */
    public async ensureGroupMessageStore(): Promise<void> {
        if (this.groupMessageStore) return;
        if (this._persistGroupMessages) {
            await this.initGroupMessageStore();
        }
    }

    // ============================================================
    // Group Storage Management (CRUD API)
    // ============================================================

    /**
     * 从服务端拉取群组列表并同步到本地存储。
     * 返回群组列表（含 group_id, name, member_count 等）。
     */
    public async syncGroupList(): Promise<Array<{ group_id: string; name: string; member_count?: number }>> {
        if (!this.groupOps || !this._groupTargetAid) {
            throw new Error('群组客户端未初始化，请先调用 initGroupClient');
        }

        const result = await this.groupOps.listMyGroups(this._groupTargetAid);
        const groups: Array<{ group_id: string; name: string; member_count?: number }> = [];

        for (const membership of result.groups) {
            // 尝试获取群组详细信息
            let name = membership.group_id;
            let memberCount: number | undefined;
            try {
                const info = await this.groupOps.getGroupInfo(this._groupTargetAid, membership.group_id);
                name = info.name || membership.group_id;
                memberCount = info.member_count;
            } catch (_) {}

            groups.push({ group_id: membership.group_id, name, member_count: memberCount });

            // 同步到本地存储
            if (this.groupMessageStore) {
                this.groupMessageStore.getOrCreateGroup(membership.group_id, this._groupTargetAid, name);
            }
        }

        // 清理本地有但服务端已不存在的群组
        if (this.groupMessageStore) {
            const serverGroupIds = new Set(result.groups.map(g => g.group_id));
            const localGroups = this.groupMessageStore.getGroupList();
            for (const local of localGroups) {
                if (!serverGroupIds.has(local.groupId)) {
                    await this.groupMessageStore.deleteGroup(local.groupId);
                    logger.log(`[Group] syncGroupList: 清理本地已退出群组 ${local.groupId}`);
                }
            }
        }

        return groups;
    }

    /**
     * 获取本地存储的群组列表。
     * 如果持久化存储已初始化，从存储中读取；否则返回空数组。
     */
    public getLocalGroupList(): Array<{ group_id: string; name: string; member_count?: number }> {
        if (!this.groupMessageStore) return [];
        return this.groupMessageStore.getGroupList().map(r => ({
            group_id: r.groupId,
            name: r.groupName,
        }));
    }

    /**
     * 添加群组到本地存储
     */
    public addGroupToStore(groupId: string, name: string): void {
        if (!this.groupMessageStore) return;
        this.groupMessageStore.getOrCreateGroup(groupId, this._groupTargetAid, name);
    }

    /**
     * 从本地存储删除群组
     */
    public async removeGroupFromStore(groupId: string): Promise<void> {
        if (!this.groupMessageStore) return;
        await this.groupMessageStore.deleteGroup(groupId);
    }

    /**
     * 获取本地存储的群消息
     */
    public getLocalGroupMessages(groupId: string, limit?: number): GroupMessage[] {
        if (!this.groupMessageStore) return [];
        if (limit) {
            return this.groupMessageStore.getLatestMessages(groupId, limit);
        }
        return this.groupMessageStore.getMessages(groupId);
    }

    /**
     * 添加群消息到本地存储
     */
    public async addGroupMessageToStore(groupId: string, msg: GroupMessage): Promise<void> {
        if (!this.groupMessageStore) return;
        await this.groupMessageStore.addMessage(groupId, msg);
    }

    /**
     * 批量添加群消息到本地存储
     */
    public async addGroupMessagesToStore(groupId: string, msgs: GroupMessage[]): Promise<void> {
        if (!this.groupMessageStore) {
            logger.warn(`[AgentCP] addGroupMessagesToStore: groupMessageStore is NULL! group=${groupId} msgs=${msgs.length} — 消息将丢失!`);
            return;
        }
        await this.groupMessageStore.addMessages(groupId, msgs);
    }

    /**
     * 获取本地存储中群组的最新消息ID（用于增量拉取）
     */
    public getGroupLastMsgId(groupId: string): number {
        if (!this.groupMessageStore) return 0;
        const record = this.groupMessageStore.getGroup(groupId);
        return record?.lastMsgId ?? 0;
    }

    /**
     * 从服务端拉取新消息并同步到本地存储。
     * 循环拉取直到 has_more=false，每批拉取后自动 ACK。
     * 返回所有本地缓存的消息（包括新拉取的）。
     *
     * @param groupId 群组 ID
     * @param afterMsgId 从哪条消息之后开始拉取，0 表示使用服务端自动游标模式
     * @param limit 每次拉取数量上限，0 表示使用服务端默认值
     */
    public async pullAndStoreGroupMessages(groupId: string, afterMsgId: number = 0, limit: number = 50): Promise<GroupMessage[]> {
        if (!this.groupOps || !this._groupTargetAid) {
            throw new Error('群组客户端未初始化');
        }

        let after = afterMsgId;

        try {
            while (true) {
                const pulled = await this.groupOps.pullMessages(
                    this._groupTargetAid, groupId, after, limit);

                if (!pulled.messages || pulled.messages.length === 0) {
                    break;
                }

                const msgs: GroupMessage[] = pulled.messages.map(m => ({
                    msg_id: m.msg_id ?? 0,
                    sender: m.sender ?? '',
                    content: m.content ?? '',
                    content_type: m.content_type ?? 'text',
                    timestamp: m.timestamp ?? 0,
                    metadata: m.metadata ?? null,
                }));
                await this.addGroupMessagesToStore(groupId, msgs);

                // ACK 这批消息中的最后一条
                if (msgs.length > 0) {
                    const lastMsgId = msgs[msgs.length - 1].msg_id;
                    await this.groupOps.ackMessages(this._groupTargetAid, groupId, lastMsgId);

                    // 更新 after 用于下一轮拉取
                    after = lastMsgId;
                }

                if (!pulled.has_more) {
                    break;
                }
            }
        } catch (e: any) {
            logger.warn('[AgentCP] pullAndStoreGroupMessages error:', e.message);
        }

        return this.getLocalGroupMessages(groupId);
    }

    // ============================================================
    // Group Session Lifecycle (register_online / pull / heartbeat / unregister)
    // ============================================================

    /**
     * 加入群组会话（完整生命周期）：
     * 1. register_online → 告知 group.ap 在线
     * 2. 将群组加入在线列表
     * 3. 启动心跳定时器（首次时启动）
     */
    public async joinGroupSession(groupId: string): Promise<void> {
        if (!this.groupOps || !this._groupTargetAid) {
            throw new Error('群组客户端未初始化，请先调用 initGroupClient');
        }

        // Step 1: register_online（仅通知 group.ap 在线，不再返回游标）
        await this.groupOps.registerOnline(this._groupTargetAid);
        this._onlineGroups.add(groupId);

        logger.log(`[Group] joinGroupSession: group=${groupId}`);

        // Step 2: 冷启动同步 — 拉取历史消息对齐，再进入批推送接收
        try {
            const lastMsgId = this.getGroupLastMsgId(groupId);
            await this.pullAndStoreGroupMessages(groupId, lastMsgId, 50);
        } catch (e: any) {
            logger.warn(`[Group] cold-start sync failed: group=${groupId}`, e.message || e);
        }

        // Step 3: 启动心跳定时器（首次加入群组时启动）
        this._ensureHeartbeat();
    }

    /**
     * 离开群组会话（优雅退出）：
     * 1. 从在线群组列表移除
     * 2. 如果没有在线群组了，unregister_online + 停止心跳定时器
     */
    public async leaveGroupSession(groupId: string): Promise<void> {
        if (!this.groupOps || !this._groupTargetAid) return;

        this._onlineGroups.delete(groupId);

        // 如果没有在线群组了，通知 group.ap 下线并停止心跳
        if (this._onlineGroups.size === 0) {
            try {
                await this.groupOps.unregisterOnline(this._groupTargetAid);
            } catch (e: any) {
                logger.warn(`[Group] unregisterOnline failed`, e.message || e);
            }
            this._stopHeartbeat();
        }
    }

    /**
     * 离开所有群组会话
     */
    public async leaveAllGroupSessions(): Promise<void> {
        const groups = Array.from(this._onlineGroups);
        for (const groupId of groups) {
            await this.leaveGroupSession(groupId);
        }
    }

    /**
     * 获取当前在线群组列表
     */
    public getOnlineGroups(): string[] {
        return Array.from(this._onlineGroups);
    }

    /**
     * 设置心跳间隔（毫秒），默认 180000（3 分钟）
     */
    public setHeartbeatInterval(intervalMs: number): void {
        this._heartbeatIntervalMs = intervalMs;
        // 如果心跳已在运行，重新启动以应用新间隔
        if (this._heartbeatTimer) {
            this._stopHeartbeat();
            this._ensureHeartbeat();
        }
    }

    /**
     * 确保心跳定时器已启动
     */
    private _ensureHeartbeat(): void {
        if (this._heartbeatTimer) return;
        if (this._onlineGroups.size === 0) return;

        this._heartbeatTimer = setInterval(() => {
            this._sendHeartbeats();
        }, this._heartbeatIntervalMs);

        logger.log(`[Group] heartbeat started: interval=${this._heartbeatIntervalMs}ms`);
    }

    /**
     * 停止心跳定时器
     */
    private _stopHeartbeat(): void {
        if (this._heartbeatTimer) {
            clearInterval(this._heartbeatTimer);
            this._heartbeatTimer = null;
            logger.log(`[Group] heartbeat stopped`);
        }
    }

    /**
     * 发送心跳保活
     */
    private _sendHeartbeats(): void {
        if (!this.groupOps || !this._groupTargetAid) return;

        this.groupOps.heartbeat(this._groupTargetAid).catch(e => {
            logger.warn(`[Group] heartbeat failed`, e.message || e);
        });
    }

    /**
     * 关闭群消息存储，刷新所有未写入的数据
     */
    public async closeGroupMessageStore(): Promise<void> {
        if (this.groupMessageStore) {
            await this.groupMessageStore.close();
            this.groupMessageStore = null;
        }
    }

    private handleError(error: unknown, customMessage?: string): never {
        const errorMessage = error instanceof Error ? error.message : String(error);
        throw new Error(`${customMessage || '操作失败'}: ${errorMessage}`);
    }
}

export { AgentCP };