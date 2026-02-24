/**
 * Group operations - all 5 phases.
 * Mirrors Python SDK: agentcp/group/operations.py
 */

import { ACPGroupClient } from './client';
import {
    GroupError, GroupErrorCode, GroupResponse,
    CreateGroupResp, SendMessageResp, PullMessagesResp, PullEventsResp,
    CursorState, MsgCursor, EventCursor,
    createMsgCursor, createEventCursor,
    GroupInfoResp, BanlistResp, BatchReviewResp, PendingRequestsResp,
    RequestJoinResp,
    MembersResp, AdminsResp, RulesResp, AnnouncementResp,
    JoinRequirementsResp, MasterResp,
    InviteCodeResp, InviteCodeListResp,
    BroadcastLockResp, BroadcastPermissionResp,
    SyncStatusResp, SyncLogResp, ChecksumResp,
    PublicGroupInfoResp, SearchGroupsResp, DigestResp,
    MembershipInfo, ListMyGroupsResp, GetFileResp, GetSummaryResp, GetMetricsResp,
    DutyConfig, DutyStatusResp,
} from './types';

/**
 * Callback interface for syncGroup.
 */
export interface SyncHandler {
    onMessages(groupId: string, messages: Record<string, any>[]): void;
    onEvents(groupId: string, events: Record<string, any>[]): void;
}

/**
 * All group operations, wrapping ACPGroupClient.sendRequest().
 */
export class GroupOperations {
    private _client: ACPGroupClient;

    constructor(client: ACPGroupClient) {
        this._client = client;
    }

    private _check(resp: GroupResponse, action: string): void {
        if (resp.code !== GroupErrorCode.SUCCESS) {
            throw new GroupError(action, resp.code, resp.error, resp.group_id);
        }
    }

    /**
     * 从群聊链接解析出 targetAid 和 groupId。
     * 例如 "https://group.agentcp.io/aa6f95b5-2e2f-4485-b1f4-d35c4940406e"
     *   => { targetAid: "group.agentcp.io", groupId: "aa6f95b5-2e2f-4485-b1f4-d35c4940406e" }
     */
    static parseGroupUrl(groupUrl: string): { targetAid: string; groupId: string } {
        let url: URL;
        try {
            url = new URL(groupUrl);
        } catch {
            throw new Error(`无效的群聊链接: ${groupUrl}`);
        }
        const targetAid = url.hostname;
        const groupId = url.pathname.replace(/^\//, '');
        if (!targetAid || !groupId) {
            throw new Error(`群聊链接缺少 targetAid 或 groupId: ${groupUrl}`);
        }
        return { targetAid, groupId };
    }

    /**
     * 通过群聊链接加入群组。
     * - 提供 inviteCode 时：免审核，直接通过邀请码加入
     * - 不提供 inviteCode 时：
     *   - 公开群：直接加入，返回 status="joined"
     *   - 私密群：提交加入申请，返回 status="pending"
     *
     * @param groupUrl 群聊链接，如 "https://group.agentcp.io/<group_id>"
     * @param options 可选参数
     * @param options.inviteCode 邀请码（免审核加入）
     * @param options.message 申请消息（私密群审核模式下使用）
     * @returns RequestJoinResp，包含 status 和 request_id
     */
    async joinByUrl(groupUrl: string, options?: {
        inviteCode?: string;
        message?: string;
    }): Promise<RequestJoinResp> {
        const { targetAid, groupId } = GroupOperations.parseGroupUrl(groupUrl);
        if (options?.inviteCode) {
            await this.useInviteCode(targetAid, groupId, options.inviteCode);
            return { status: 'joined', request_id: '' };
        }
        return this.requestJoin(targetAid, groupId, options?.message ?? '');
    }

    // ============================================================
    // Phase 0: Lifecycle (register / heartbeat / unregister)
    // ============================================================

    /**
     * 注册上线，告知 group.ap 当前客户端在线，可以接收消息推送。
     * 客户端每次启动或重新连接时调用一次即可。
     */
    async registerOnline(targetAid: string): Promise<void> {
        const resp = await this._client.sendRequest(targetAid, "", "register_online", null);
        this._check(resp, "register_online");
    }

    /**
     * 主动下线（优雅退出）。
     * 客户端退出时调用，立即从在线列表移除。
     */
    async unregisterOnline(targetAid: string): Promise<void> {
        const resp = await this._client.sendRequest(targetAid, "", "unregister_online", null);
        this._check(resp, "unregister_online");
    }

    /**
     * 心跳保活。
     * 在线注册有 5 分钟超时，SDK 需定时发送（建议 2~4 分钟）。
     */
    async heartbeat(targetAid: string): Promise<void> {
        const resp = await this._client.sendRequest(targetAid, "", "heartbeat", null);
        this._check(resp, "heartbeat");
    }

    // ============================================================
    // Phase 1: Basic Operations
    // ============================================================

    async createGroup(targetAid: string, name: string, options?: {
        alias?: string; subject?: string; visibility?: string; description?: string; tags?: string[];
    }): Promise<CreateGroupResp> {
        const params: Record<string, any> = { name };
        if (options?.alias) params.alias = options.alias;
        if (options?.subject) params.subject = options.subject;
        if (options?.visibility) params.visibility = options.visibility;
        if (options?.description) params.description = options.description;
        if (options?.tags) params.tags = options.tags;
        const resp = await this._client.sendRequest(targetAid, "", "create_group", params);
        this._check(resp, "create_group");
        const d = resp.data || {};
        return { group_id: d.group_id ?? "", group_url: d.group_url ?? "" };
    }

    async addMember(targetAid: string, groupId: string, agentId: string, role: string = ""): Promise<void> {
        const params: Record<string, any> = { agent_id: agentId };
        if (role) params.role = role;
        const resp = await this._client.sendRequest(targetAid, groupId, "add_member", params);
        this._check(resp, "add_member");
    }

    async sendGroupMessage(targetAid: string, groupId: string, content: string,
                           contentType: string = "", metadata?: Record<string, any>): Promise<SendMessageResp> {
        const params: Record<string, any> = { content };
        if (contentType) params.content_type = contentType;
        if (metadata) params.metadata = metadata;
        const resp = await this._client.sendRequest(targetAid, groupId, "send_message", params);
        this._check(resp, "send_message");
        const d = resp.data || {};
        return { msg_id: d.msg_id ?? 0, timestamp: d.timestamp ?? 0 };
    }

    /**
     * 拉取消息。
     * - afterMsgId > 0: 指定位置模式，从该 ID 之后开始拉取
     * - afterMsgId = 0 或不传: 自动游标模式（推荐），服务端基于 current_msg_id 自动计算
     */
    async pullMessages(targetAid: string, groupId: string,
                       afterMsgId: number = 0, limit: number = 0): Promise<PullMessagesResp> {
        const params: Record<string, any> = {};
        if (afterMsgId > 0) params.after_msg_id = afterMsgId;
        if (limit > 0) params.limit = limit;
        const resp = await this._client.sendRequest(targetAid, groupId, "pull_messages",
            Object.keys(params).length > 0 ? params : null);
        this._check(resp, "pull_messages");
        const d = resp.data || {};
        return {
            messages: d.messages ?? [],
            has_more: d.has_more ?? false,
            latest_msg_id: d.latest_msg_id ?? 0,
        };
    }

    async ackMessages(targetAid: string, groupId: string, msgId: number): Promise<void> {
        const resp = await this._client.sendRequest(targetAid, groupId, "ack_messages", { msg_id: msgId });
        this._check(resp, "ack_messages");
        const store = this._client.getCursorStore();
        if (store) {
            store.saveMsgCursor(groupId, msgId);
        }
    }

    async pullEvents(targetAid: string, groupId: string,
                     afterEventId: number, limit: number = 0): Promise<PullEventsResp> {
        const params: Record<string, any> = { after_event_id: afterEventId };
        if (limit > 0) params.limit = limit;
        const resp = await this._client.sendRequest(targetAid, groupId, "pull_events", params);
        this._check(resp, "pull_events");
        const d = resp.data || {};
        return {
            events: d.events ?? [],
            has_more: d.has_more ?? false,
            latest_event_id: d.latest_event_id ?? 0,
        };
    }

    async ackEvents(targetAid: string, groupId: string, eventId: number): Promise<void> {
        const resp = await this._client.sendRequest(targetAid, groupId, "ack_events", { event_id: eventId });
        this._check(resp, "ack_events");
        const store = this._client.getCursorStore();
        if (store) {
            store.saveEventCursor(groupId, eventId);
        }
    }

    async getCursor(targetAid: string, groupId: string): Promise<CursorState> {
        const resp = await this._client.sendRequest(targetAid, groupId, "get_cursor", null);
        this._check(resp, "get_cursor");
        const d = resp.data || {};
        return {
            msg_cursor: createMsgCursor(d.msg_cursor),
            event_cursor: createEventCursor(d.event_cursor),
        };
    }

    async syncGroup(targetAid: string, groupId: string, handler: SyncHandler): Promise<void> {
        const cursor = await this.getCursor(targetAid, groupId);
        const store = this._client.getCursorStore();
        if (store) {
            const [localMsg, localEvent] = store.loadCursor(groupId);
            if (localMsg > cursor.msg_cursor.current_msg_id) {
                cursor.msg_cursor.current_msg_id = localMsg;
            }
            if (localEvent > cursor.event_cursor.current_event_id) {
                cursor.event_cursor.current_event_id = localEvent;
            }
        }
        await this._syncMessages(targetAid, groupId, cursor, handler);
        await this._syncEvents(targetAid, groupId, cursor, handler);
    }

    private async _syncMessages(targetAid: string, groupId: string,
                                cursor: CursorState, handler: SyncHandler): Promise<void> {
        let after = cursor.msg_cursor.current_msg_id;
        while (true) {
            const result = await this.pullMessages(targetAid, groupId, after, 50);
            const messages = result.messages || [];
            if (messages.length > 0) {
                handler.onMessages(groupId, messages);
                const lastId = messages[messages.length - 1].msg_id ?? after;
                await this.ackMessages(targetAid, groupId, lastId);
                after = lastId;
            }
            if (!result.has_more) {
                break;
            }
        }
    }

    private async _syncEvents(targetAid: string, groupId: string,
                              cursor: CursorState, handler: SyncHandler): Promise<void> {
        let after = cursor.event_cursor.current_event_id;
        while (true) {
            const result = await this.pullEvents(targetAid, groupId, after, 50);
            const events = result.events || [];
            if (events.length > 0) {
                handler.onEvents(groupId, events);
                const lastId = events[events.length - 1].event_id ?? after;
                await this.ackEvents(targetAid, groupId, lastId);
                after = lastId;
            }
            if (!result.has_more) {
                break;
            }
        }
    }

    // ============================================================
    // Phase 2: Management Operations
    // ============================================================

    async removeMember(targetAid: string, groupId: string, agentId: string): Promise<void> {
        const resp = await this._client.sendRequest(targetAid, groupId, "remove_member", { agent_id: agentId });
        this._check(resp, "remove_member");
    }

    async leaveGroup(targetAid: string, groupId: string): Promise<void> {
        const resp = await this._client.sendRequest(targetAid, groupId, "leave_group", null);
        this._check(resp, "leave_group");
    }

    async dissolveGroup(targetAid: string, groupId: string): Promise<void> {
        const resp = await this._client.sendRequest(targetAid, groupId, "dissolve_group", null);
        this._check(resp, "dissolve_group");
    }

    async banAgent(targetAid: string, groupId: string, agentId: string,
                   reason: string = "", expiresAt: number = 0): Promise<void> {
        const params: Record<string, any> = { agent_id: agentId };
        if (reason) params.reason = reason;
        if (expiresAt) params.expires_at = expiresAt;
        const resp = await this._client.sendRequest(targetAid, groupId, "ban_agent", params);
        this._check(resp, "ban_agent");
    }

    async unbanAgent(targetAid: string, groupId: string, agentId: string): Promise<void> {
        const resp = await this._client.sendRequest(targetAid, groupId, "unban_agent", { agent_id: agentId });
        this._check(resp, "unban_agent");
    }

    async getBanlist(targetAid: string, groupId: string): Promise<BanlistResp> {
        const resp = await this._client.sendRequest(targetAid, groupId, "get_banlist", null);
        this._check(resp, "get_banlist");
        const d = resp.data || {};
        return { banned: d.banned ?? [] };
    }

    async requestJoin(targetAid: string, groupId: string, message: string = ""): Promise<RequestJoinResp> {
        const params: Record<string, any> = {};
        if (message) params.message = message;
        const resp = await this._client.sendRequest(targetAid, groupId, "request_join",
            Object.keys(params).length > 0 ? params : null);
        this._check(resp, "request_join");
        const d = resp.data || {};
        return { status: d.status ?? "pending", request_id: d.request_id ?? "" };
    }

    async reviewJoinRequest(targetAid: string, groupId: string,
                            agentId: string, action: string, reason: string = ""): Promise<void> {
        const params: Record<string, any> = { agent_id: agentId, action };
        if (reason) params.reason = reason;
        const resp = await this._client.sendRequest(targetAid, groupId, "review_join_request", params);
        this._check(resp, "review_join_request");
    }

    async batchReviewJoinRequests(targetAid: string, groupId: string,
                                  agentIds: string[], action: string,
                                  reason: string = ""): Promise<BatchReviewResp> {
        const params: Record<string, any> = { agent_ids: agentIds, action };
        if (reason) params.reason = reason;
        const resp = await this._client.sendRequest(targetAid, groupId, "batch_review_join_requests", params);
        this._check(resp, "batch_review_join_requests");
        const d = resp.data || {};
        return { processed: d.processed ?? 0, total: d.total ?? 0 };
    }

    async getPendingRequests(targetAid: string, groupId: string): Promise<PendingRequestsResp> {
        const resp = await this._client.sendRequest(targetAid, groupId, "get_pending_requests", null);
        this._check(resp, "get_pending_requests");
        const d = resp.data || {};
        return { requests: d.requests ?? [] };
    }

    // ============================================================
    // Phase 3: Full Features
    // ============================================================

    async getGroupInfo(targetAid: string, groupId: string): Promise<GroupInfoResp> {
        const resp = await this._client.sendRequest(targetAid, groupId, "get_group_info", null);
        this._check(resp, "get_group_info");
        const d = resp.data || {};
        return {
            group_id: d.group_id ?? "", name: d.name ?? "",
            creator: d.creator ?? "", visibility: d.visibility ?? "",
            member_count: d.member_count ?? 0, created_at: d.created_at ?? 0,
            updated_at: d.updated_at ?? 0, alias: d.alias ?? "",
            subject: d.subject ?? "", status: d.status ?? "",
            tags: d.tags ?? [], master: d.master ?? "",
        };
    }

    async updateGroupMeta(targetAid: string, groupId: string, params: Record<string, any>): Promise<void> {
        const resp = await this._client.sendRequest(targetAid, groupId, "update_group_meta", params);
        this._check(resp, "update_group_meta");
    }

    async getMembers(targetAid: string, groupId: string): Promise<MembersResp> {
        const resp = await this._client.sendRequest(targetAid, groupId, "get_members", null);
        this._check(resp, "get_members");
        const d = resp.data || {};
        return { members: d.members ?? [] };
    }

    async getAdmins(targetAid: string, groupId: string): Promise<AdminsResp> {
        const resp = await this._client.sendRequest(targetAid, groupId, "get_admins", null);
        this._check(resp, "get_admins");
        const d = resp.data || {};
        return { admins: d.admins ?? [] };
    }

    async getRules(targetAid: string, groupId: string): Promise<RulesResp> {
        const resp = await this._client.sendRequest(targetAid, groupId, "get_rules", null);
        this._check(resp, "get_rules");
        const d = resp.data || {};
        return {
            max_members: d.max_members ?? 0,
            max_message_size: d.max_message_size ?? 0,
            broadcast_policy: d.broadcast_policy ?? null,
        };
    }

    async updateRules(targetAid: string, groupId: string, params: Record<string, any>): Promise<void> {
        const resp = await this._client.sendRequest(targetAid, groupId, "update_rules", params);
        this._check(resp, "update_rules");
    }

    async getAnnouncement(targetAid: string, groupId: string): Promise<AnnouncementResp> {
        const resp = await this._client.sendRequest(targetAid, groupId, "get_announcement", null);
        this._check(resp, "get_announcement");
        const d = resp.data || {};
        return {
            content: d.content ?? "",
            updated_by: d.updated_by ?? "",
            updated_at: d.updated_at ?? 0,
        };
    }

    async updateAnnouncement(targetAid: string, groupId: string, content: string): Promise<void> {
        const resp = await this._client.sendRequest(targetAid, groupId, "update_announcement", { content });
        this._check(resp, "update_announcement");
    }

    async getJoinRequirements(targetAid: string, groupId: string): Promise<JoinRequirementsResp> {
        const resp = await this._client.sendRequest(targetAid, groupId, "get_join_requirements", null);
        this._check(resp, "get_join_requirements");
        const d = resp.data || {};
        return { mode: d.mode ?? "", require_all: d.require_all ?? false };
    }

    async updateJoinRequirements(targetAid: string, groupId: string, params: Record<string, any>): Promise<void> {
        const resp = await this._client.sendRequest(targetAid, groupId, "update_join_requirements", params);
        this._check(resp, "update_join_requirements");
    }

    async suspendGroup(targetAid: string, groupId: string): Promise<void> {
        const resp = await this._client.sendRequest(targetAid, groupId, "suspend_group", null);
        this._check(resp, "suspend_group");
    }

    async resumeGroup(targetAid: string, groupId: string): Promise<void> {
        const resp = await this._client.sendRequest(targetAid, groupId, "resume_group", null);
        this._check(resp, "resume_group");
    }

    async transferMaster(targetAid: string, groupId: string,
                         newMasterAid: string, reason: string = ""): Promise<void> {
        const params: Record<string, any> = { new_master_aid: newMasterAid };
        if (reason) params.reason = reason;
        const resp = await this._client.sendRequest(targetAid, groupId, "transfer_master", params);
        this._check(resp, "transfer_master");
    }

    async getMaster(targetAid: string, groupId: string): Promise<MasterResp> {
        const resp = await this._client.sendRequest(targetAid, groupId, "get_master", null);
        this._check(resp, "get_master");
        const d = resp.data || {};
        return {
            master: d.master ?? "",
            master_transferred_at: d.master_transferred_at ?? 0,
            transfer_reason: d.transfer_reason ?? "",
        };
    }

    async createInviteCode(targetAid: string, groupId: string, options?: {
        label?: string; max_uses?: number; expires_at?: number;
    }): Promise<InviteCodeResp> {
        const params: Record<string, any> = {};
        if (options?.label) params.label = options.label;
        if (options?.max_uses) params.max_uses = options.max_uses;
        if (options?.expires_at) params.expires_at = options.expires_at;
        const resp = await this._client.sendRequest(targetAid, groupId, "create_invite_code",
            Object.keys(params).length > 0 ? params : null);
        this._check(resp, "create_invite_code");
        const d = resp.data || {};
        return {
            code: d.code ?? "", group_id: d.group_id ?? "",
            created_by: d.created_by ?? "", created_at: d.created_at ?? 0,
            label: d.label ?? "", max_uses: d.max_uses ?? 0,
            expires_at: d.expires_at ?? 0,
        };
    }

    async useInviteCode(targetAid: string, groupId: string, code: string): Promise<void> {
        const resp = await this._client.sendRequest(targetAid, groupId, "use_invite_code", { code });
        this._check(resp, "use_invite_code");
    }

    async listInviteCodes(targetAid: string, groupId: string): Promise<InviteCodeListResp> {
        const resp = await this._client.sendRequest(targetAid, groupId, "list_invite_codes", null);
        this._check(resp, "list_invite_codes");
        const d = resp.data || {};
        return { codes: d.codes ?? [] };
    }

    async revokeInviteCode(targetAid: string, groupId: string, code: string): Promise<void> {
        const resp = await this._client.sendRequest(targetAid, groupId, "revoke_invite_code", { code });
        this._check(resp, "revoke_invite_code");
    }

    async acquireBroadcastLock(targetAid: string, groupId: string): Promise<BroadcastLockResp> {
        const resp = await this._client.sendRequest(targetAid, groupId, "acquire_broadcast_lock", null);
        this._check(resp, "acquire_broadcast_lock");
        const d = resp.data || {};
        return {
            acquired: d.acquired ?? false,
            expires_at: d.expires_at ?? 0,
            holder: d.holder ?? "",
        };
    }

    async releaseBroadcastLock(targetAid: string, groupId: string): Promise<void> {
        const resp = await this._client.sendRequest(targetAid, groupId, "release_broadcast_lock", null);
        this._check(resp, "release_broadcast_lock");
    }

    async checkBroadcastPermission(targetAid: string, groupId: string): Promise<BroadcastPermissionResp> {
        const resp = await this._client.sendRequest(targetAid, groupId, "check_broadcast_permission", null);
        this._check(resp, "check_broadcast_permission");
        const d = resp.data || {};
        return { allowed: d.allowed ?? false, reason: d.reason ?? "" };
    }

    // ============================================================
    // Phase 4: SDK Convenience
    // ============================================================

    async getSyncStatus(targetAid: string, groupId: string): Promise<SyncStatusResp> {
        const resp = await this._client.sendRequest(targetAid, groupId, "get_sync_status", null);
        this._check(resp, "get_sync_status");
        const d = resp.data || {};
        return {
            msg_cursor: createMsgCursor(d.msg_cursor),
            event_cursor: createEventCursor(d.event_cursor),
            sync_percentage: d.sync_percentage ?? 0,
        };
    }

    async getSyncLog(targetAid: string, groupId: string, startDate: string): Promise<SyncLogResp> {
        const resp = await this._client.sendRequest(targetAid, groupId, "get_sync_log", { start_date: startDate });
        this._check(resp, "get_sync_log");
        const d = resp.data || {};
        return { entries: d.entries ?? [] };
    }

    async getChecksum(targetAid: string, groupId: string, file: string): Promise<ChecksumResp> {
        const resp = await this._client.sendRequest(targetAid, groupId, "get_checksum", { file });
        this._check(resp, "get_checksum");
        const d = resp.data || {};
        return { file: d.file ?? "", checksum: d.checksum ?? "" };
    }

    async getMessageChecksum(targetAid: string, groupId: string, date: string): Promise<ChecksumResp> {
        const resp = await this._client.sendRequest(targetAid, groupId, "get_message_checksum", { date });
        this._check(resp, "get_message_checksum");
        const d = resp.data || {};
        return { file: d.file ?? "", checksum: d.checksum ?? "" };
    }

    async getPublicInfo(targetAid: string, groupId: string): Promise<PublicGroupInfoResp> {
        const resp = await this._client.sendRequest(targetAid, groupId, "get_public_info", null);
        this._check(resp, "get_public_info");
        const d = resp.data || {};
        return {
            group_id: d.group_id ?? "", name: d.name ?? "",
            creator: d.creator ?? "", visibility: d.visibility ?? "",
            member_count: d.member_count ?? 0, created_at: d.created_at ?? 0,
            alias: d.alias ?? "", subject: d.subject ?? "",
            tags: d.tags ?? [], join_mode: d.join_mode ?? "",
        };
    }

    async searchGroups(targetAid: string, keyword: string, options?: {
        tags?: string[]; limit?: number; offset?: number;
    }): Promise<SearchGroupsResp> {
        const params: Record<string, any> = { keyword };
        if (options?.tags) params.tags = options.tags;
        if (options?.limit) params.limit = options.limit;
        if (options?.offset) params.offset = options.offset;
        const resp = await this._client.sendRequest(targetAid, "", "search_groups", params);
        this._check(resp, "search_groups");
        const d = resp.data || {};
        const groups: PublicGroupInfoResp[] = (d.groups ?? []).map((g: any) => ({
            group_id: g.group_id ?? "", name: g.name ?? "",
            creator: g.creator ?? "", visibility: g.visibility ?? "",
            member_count: g.member_count ?? 0, created_at: g.created_at ?? 0,
            alias: g.alias ?? "", subject: g.subject ?? "",
            tags: g.tags ?? [], join_mode: g.join_mode ?? "",
        }));
        return { groups, total: d.total ?? 0 };
    }

    async generateDigest(targetAid: string, groupId: string,
                         date: string, period: string): Promise<DigestResp> {
        const resp = await this._client.sendRequest(targetAid, groupId, "generate_digest",
            { date, period });
        this._check(resp, "generate_digest");
        const d = resp.data || {};
        return {
            date: d.date ?? "", period: d.period ?? "",
            message_count: d.message_count ?? 0, unique_senders: d.unique_senders ?? 0,
            data_size: d.data_size ?? 0, generated_at: d.generated_at ?? 0,
            top_contributors: d.top_contributors ?? [],
        };
    }

    async getDigest(targetAid: string, groupId: string,
                    date: string, period: string): Promise<DigestResp> {
        const resp = await this._client.sendRequest(targetAid, groupId, "get_digest",
            { date, period });
        this._check(resp, "get_digest");
        const d = resp.data || {};
        return {
            date: d.date ?? "", period: d.period ?? "",
            message_count: d.message_count ?? 0, unique_senders: d.unique_senders ?? 0,
            data_size: d.data_size ?? 0, generated_at: d.generated_at ?? 0,
            top_contributors: d.top_contributors ?? [],
        };
    }

    // ============================================================
    // Phase 5: Home AP Membership Index
    // ============================================================

    async listMyGroups(targetAid: string, status: number = 0): Promise<ListMyGroupsResp> {
        const params: Record<string, any> = {};
        if (status) params.status = status;
        const resp = await this._client.sendRequest(targetAid, "", "list_my_groups",
            Object.keys(params).length > 0 ? params : null);
        this._check(resp, "list_my_groups");
        const d = resp.data || {};
        const groups: MembershipInfo[] = (d.groups ?? []).map((g: any) => ({
            group_id: g.group_id ?? "", group_url: g.group_url ?? "",
            group_server: g.group_server ?? "", session_id: g.session_id ?? "",
            role: g.role ?? "", status: g.status ?? 0,
            created_at: g.created_at ?? 0, updated_at: g.updated_at ?? 0,
        }));
        return { groups, total: d.total ?? 0 };
    }

    async unregisterMembership(targetAid: string, groupId: string): Promise<void> {
        const resp = await this._client.sendRequest(targetAid, groupId, "unregister_membership", null);
        this._check(resp, "unregister_membership");
    }

    async changeMemberRole(targetAid: string, groupId: string,
                           agentId: string, newRole: string): Promise<void> {
        const params = { agent_id: agentId, new_role: newRole };
        const resp = await this._client.sendRequest(targetAid, groupId, "change_member_role", params);
        this._check(resp, "change_member_role");
    }

    async getFile(targetAid: string, groupId: string,
                  file: string, offset: number = 0): Promise<GetFileResp> {
        const params: Record<string, any> = { file };
        if (offset) params.offset = offset;
        const resp = await this._client.sendRequest(targetAid, groupId, "get_file", params);
        this._check(resp, "get_file");
        const d = resp.data || {};
        return { data: d.data ?? "", total_size: d.total_size ?? 0, offset: d.offset ?? 0 };
    }

    async getSummary(targetAid: string, groupId: string, date: string): Promise<GetSummaryResp> {
        const resp = await this._client.sendRequest(targetAid, groupId, "get_summary", { date });
        this._check(resp, "get_summary");
        const d = resp.data || {};
        return {
            date: d.date ?? "", message_count: d.message_count ?? 0,
            senders: d.senders ?? [], data_size: d.data_size ?? 0,
        };
    }

    async getMetrics(targetAid: string): Promise<GetMetricsResp> {
        const resp = await this._client.sendRequest(targetAid, "", "get_metrics", null);
        this._check(resp, "get_metrics");
        const d = resp.data || {};
        return {
            goroutines: d.goroutines ?? 0, alloc_mb: d.alloc_mb ?? 0,
            sys_mb: d.sys_mb ?? 0, gc_cycles: d.gc_cycles ?? 0,
        };
    }

    // ============================================================
    // Duty (值班) Operations
    // ============================================================

    /**
     * 更新值班配置。权限要求：creator 或 admin。
     */
    async updateDutyConfig(targetAid: string, groupId: string, config: Partial<DutyConfig>): Promise<void> {
        const params: Record<string, any> = {};
        if (config.mode != null) params.mode = config.mode;
        if (config.rotation_strategy != null) params.rotation_strategy = config.rotation_strategy;
        if (config.shift_duration_ms != null) params.shift_duration_ms = config.shift_duration_ms;
        if (config.max_messages_per_shift != null) params.max_messages_per_shift = config.max_messages_per_shift;
        if (config.duty_priority_window_ms != null) params.duty_priority_window_ms = config.duty_priority_window_ms;
        if (config.enable_rule_prelude != null) params.enable_rule_prelude = config.enable_rule_prelude;
        const resp = await this._client.sendRequest(targetAid, groupId, "update_duty_config", { duty_config: params });
        this._check(resp, "update_duty_config");
    }

    /**
     * 快捷设置固定值班 Agent 列表（自动切换为 fixed 模式）。
     */
    async setFixedAgents(targetAid: string, groupId: string, agents: string[]): Promise<void> {
        const resp = await this._client.sendRequest(targetAid, groupId, "set_fixed_agents", { agents });
        this._check(resp, "set_fixed_agents");
    }

    /**
     * 获取值班状态，包含 config 和 state。
     */
    async getDutyStatus(targetAid: string, groupId: string): Promise<DutyStatusResp> {
        const resp = await this._client.sendRequest(targetAid, groupId, "get_duty_status", null);
        this._check(resp, "get_duty_status");
        const d = resp.data || {};
        return { config: d.config ?? {}, state: d.state ?? {} };
    }

    /**
     * 重新获取所有成员的 agent.md 并更新 AgentType。
     */
    async refreshMemberTypes(targetAid: string, groupId: string): Promise<void> {
        const resp = await this._client.sendRequest(targetAid, groupId, "refresh_member_types", null);
        this._check(resp, "refresh_member_types");
    }
}
