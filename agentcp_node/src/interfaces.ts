import { ACPMessageSessionResponse, ConnectionStatus, InviteStatus } from "./websocket";
import { MessageStore } from "./messagestore";
import { AgentMdOptions } from "./agentmd";
import { ACPGroupClient, GroupOperations, ACPGroupEventHandler, CursorStore, GroupMessageStore, GroupMessage } from "./group";

/**
 * 代理身份信息接口
 * @interface IAgentIdentity
 * @property {string} aid - 代理ID，用于唯一标识一个代理
 * @property {string} privateKey - 代理的私钥，用于签名和加密
 * @property {string} certPem - 代理的证书，PEM格式
 */
interface IAgentIdentity {
    aid: string;
    privateKey: string;
    certPem: string;
}

/**
 * 连接配置接口
 * @interface IConnectionConfig
 * @property {string} messageServer - 消息服务器地址
 * @property {string} heartbeatServer - 心跳服务器地址
 * @property {string} messageSignature - 消息签名
 */
interface IConnectionConfig {
    messageServer: string;
    heartbeatServer: string;
    messageSignature: string;
}

/**
 * 代理控制平面接口
 * @interface IAgentCP
 */
interface IAgentCP {
    /**
     * 消息存储模块
     */
    readonly messageStore: MessageStore;

    /**
     * 导入代理身份
     * @param {IAgentIdentity} identity - 代理身份信息
     * @param {string} [seedPassword] - 种子密码（可选）
     * @returns {Promise<boolean>} 导入是否成功
     */
    importAid(identity: IAgentIdentity, seedPassword?: string): Promise<boolean>;

    /**
     * 加载访客身份
     * @returns {Promise<string>} 访客身份的AID
     */
    loadGuestAid(): Promise<string>;
    /**
    * 加载当前的代理身份
    * @returns {Promise<string>} 成功返回AID，失败返回null
    */
    loadCurrentAid(): Promise<string | null>;
    /**
     * 加载指定的代理身份
     * @param {string} aid - 要加载的代理ID
     * @returns {Promise<string | null>} 成功返回AID，失败返回null
     */
    loadAid(aid: string): Promise<string | null>;

    /**
     * 创建新的代理身份
     * @param {string} aid - 新代理的ID
     * @returns {Promise<string>} 创建的代理ID
     */
    createAid(aid: string): Promise<string>;

    /**
     * 上线代理，获取连接配置
     * @returns {Promise<IConnectionConfig>} 连接配置信息
     */
    online(): Promise<IConnectionConfig>;

    /**
     * 加载指定代理的证书信息
     * @param {string} aid - 要加载证书信息的代理ID
     * @returns {Promise<{privateKey: string, publicKey: string, csr: string, cert: string}>} 证书相关信息
     * @throws {Error} 当证书信息不完整时抛出错误
     */
    getCertInfo(aid: string): Promise<{
        privateKey: string;
        publicKey: string;
        csr: string;
        cert: string;
    } | null>;

    /**
     * 设置 agent.md 文件路径，登录成功后会自动上传（仅首次）
     * @param {string} filePath - agent.md 文件的本地路径
     */
    setAgentMdPath(filePath: string): void;

    /**
     * 重置 agent.md 上传状态，下次登录时会重新上传
     */
    resetAgentMdUploadStatus(): Promise<void>;

    /**
     * 启用/禁用 agent.md 自动生成
     * @param {boolean} enable - 是否启用
     */
    setAutoGenerateAgentMd(enable: boolean): void;

    /**
     * 设置自动生成 agent.md 的选项
     * @param {Partial<AgentMdOptions>} options - 生成选项
     */
    setAgentMdOptions(options: Partial<AgentMdOptions>): void;

    // ============================================================
    // Group Client
    // ============================================================

    /** 群组传输层客户端实例 */
    readonly groupClient: ACPGroupClient | null;
    /** 群组操作接口实例 */
    readonly groupOps: GroupOperations | null;
    /** 群消息持久化存储实例 */
    readonly groupMessageStore: GroupMessageStore | null;

    /**
     * 初始化群组客户端（同 AP 通信）
     * @param sendRaw 发送原始消息的函数
     * @param sessionId 与 group.{issuer} 的会话 ID
     * @param targetAid 目标群组 AID，默认自动计算为 group.{issuer}
     */
    initGroupClient(
        sendRaw: (message: string, to: string, sessionId: string) => void,
        sessionId: string,
        targetAid?: string,
    ): void;

    /**
     * 初始化跨 AP 群组客户端
     * @param sendRaw 发送原始消息的函数
     * @param sessionId 与目标群组 AID 的会话 ID
     * @param targetAid 目标群组 AID
     */
    initGroupClientCrossAp(
        sendRaw: (message: string, to: string, sessionId: string) => void,
        sessionId: string,
        targetAid: string,
    ): void;

    /**
     * 处理群组协议消息路由
     * @returns true 如果消息被群组客户端处理
     */
    handleGroupMessage(message: any): boolean;

    /** 获取当前群组目标 AID */
    getGroupTargetAid(): string;

    /** 设置群组事件处理器 */
    setGroupEventHandler(handler: ACPGroupEventHandler): void;

    /** 设置群组游标存储 */
    setGroupCursorStore(store: CursorStore): void;

    /** 关闭群组客户端 */
    closeGroupClient(): void;

    /**
     * 初始化群消息持久化存储
     */
    initGroupMessageStore(options?: {
        maxMessagesPerGroup?: number;
        maxEventsPerGroup?: number;
    }): Promise<void>;

    /**
     * 确保群消息持久化存储已初始化并加载完成
     */
    ensureGroupMessageStore(): Promise<void>;

    // ============================================================
    // Group Storage Management (CRUD API)
    // ============================================================

    /**
     * 从服务端拉取群组列表并同步到本地存储
     */
    syncGroupList(): Promise<Array<{ group_id: string; name: string; member_count?: number }>>;

    /**
     * 获取本地存储的群组列表
     */
    getLocalGroupList(): Array<{ group_id: string; name: string; member_count?: number }>;

    /**
     * 添加群组到本地存储
     */
    addGroupToStore(groupId: string, name: string): void;

    /**
     * 从本地存储删除群组
     */
    removeGroupFromStore(groupId: string): Promise<void>;

    /**
     * 获取本地存储的群消息
     */
    getLocalGroupMessages(groupId: string, limit?: number): GroupMessage[];

    /**
     * 添加群消息到本地存储
     */
    addGroupMessageToStore(groupId: string, msg: GroupMessage): Promise<void>;

    /**
     * 批量添加群消息到本地存储
     */
    addGroupMessagesToStore(groupId: string, msgs: GroupMessage[]): Promise<void>;

    /**
     * 获取本地存储中群组的最新消息ID
     */
    getGroupLastMsgId(groupId: string): number;

    /**
     * 从服务端拉取新消息并同步到本地存储
     */
    pullAndStoreGroupMessages(groupId: string, limit?: number): Promise<GroupMessage[]>;

    /**
     * 关闭群消息存储
     */
    closeGroupMessageStore(): Promise<void>;
}

/**
 * WebSocket代理接口
 * @interface IAgentWS
 */
interface IAgentWS {
    /**
     * 启动WebSocket连接
     * @returns {Promise<void>}
     */
    startWebSocket(): Promise<void>;
    /**
     * 快捷连接到指定智能体，自动创建会话并发送邀请
     * @param receiver 要连接的智能体ID
     * @param onSessionCreated 会话创建成功回调（可选）
     * @param onInviteStatus 邀请状态回调（可选）
    */
    connectTo(
        receiver: string,
        onSessionCreated: ((sessionInfo: ACPMessageSessionResponse) => void) | null,
        onInviteStatus: ((status: InviteStatus) => void) | null
    ): void;

    /**
      * 创建会话
      * @param cb 会话创建回调函数
      */
    createSession(cb: (res: ACPMessageSessionResponse) => void): void;

    /**
     * 邀请智能体加入会话
     * @param receiver 接收者智能体ID
     * @param sessionId 会话ID
     * @param identifyingCode 邀请码
     * @param cb 邀请状态回调函数（可选）
     */
    invite(receiver: string, sessionId: string, identifyingCode: string, cb: (((status: InviteStatus) => void) | null)): void;

    /**
     * 发送消息
     * @param {string} msg - 要发送的消息内容
     * @param {string} to - 接收者智能体ID
     * @param {string} sessionId - 会话ID
     * @param {string} identifyingCode - 邀请码
     */
    send(msg: string, to: string, sessionId: string, identifyingCode: string): void;

    /**
     * 发送原始消息（不做 URL 编码），用于群组协议等需要原始 JSON 的场景
     * @param {string} message - 原始消息字符串
     * @param {string} to - 接收者智能体ID
     * @param {string} sessionId - 会话ID
     * @returns {boolean} true 发送成功，false 连接未建立
     */
    sendRaw(message: string, to: string, sessionId: string): boolean;

    /**
     * 设置原始消息拦截器。回调函数返回 true 表示已处理（拦截），不再继续分发。
     * @param {function} cb - 原始消息拦截回调函数
     */
    onRawMessage(cb: (message: any) => boolean): void;


    /**
     * 注册连接状态变更回调
     * @param {function} cb - 状态变更回调函数
     * @param {ConnectionStatus} cb.status - 连接状态
     */
    onStatusChange(cb: (status: ConnectionStatus) => void): void;

    /**
     * 注册消息接收回调
     * @param {function} cb - 消息接收回调函数
     * @param {any} cb.message - 接收到的消息
     */
    onMessage(cb: (message: any) => void): void;

    /**
     * 断开WebSocket连接
     */
    disconnect(): void;

    /**
     * 重连 WebSocket
     */
    reconnect(): Promise<void>;
}

export { IAgentCP, IAgentWS, IAgentIdentity, IConnectionConfig };