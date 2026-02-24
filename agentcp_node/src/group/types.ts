/**
 * ACP Group Protocol types and constants.
 * Mirrors Python SDK: agentcp/group/types.py
 */

// ============================================================
// Error Codes
// ============================================================

export enum GroupErrorCode {
    SUCCESS = 0,
    GROUP_NOT_FOUND = 1001,
    NO_PERMISSION = 1002,
    GROUP_DISSOLVED = 1003,
    GROUP_SUSPENDED = 1004,
    ALREADY_MEMBER = 1005,
    NOT_MEMBER = 1006,
    BANNED = 1007,
    MEMBER_FULL = 1008,
    INVALID_PARAMS = 1009,
    RATE_LIMITED = 1010,
    INVITE_CODE_INVALID = 1011,
    REQUEST_EXISTS = 1012,
    BROADCAST_CONFLICT = 1013,
    ACTION_NOT_IMPL = 1099,

    // Duty error codes
    DUTY_NOT_ENABLED = 1020,
    NOT_DUTY_AGENT = 1021,
    AGENT_MD_NOT_FOUND = 1024,
    AGENT_MD_INVALID = 1025,
}

const CODE_MESSAGES: Record<number, string> = {
    0: "success",
    1001: "group not found",
    1002: "no permission",
    1003: "group dissolved",
    1004: "group suspended",
    1005: "already member",
    1006: "not member",
    1007: "banned",
    1008: "member full",
    1009: "invalid params",
    1010: "rate limited",
    1011: "invite code invalid",
    1012: "request exists",
    1013: "broadcast conflict",
    1020: "duty not enabled",
    1021: "not duty agent",
    1024: "agent.md not found",
    1025: "agent.md invalid",
    1099: "action not implemented",
};

export class GroupError extends Error {
    action: string;
    code: number;
    error: string;
    group_id: string;

    constructor(action: string, code: number, error: string = "", group_id: string = "") {
        const msg = error || CODE_MESSAGES[code] || "unknown error";
        super(`${action} failed: code=${code} error=${msg}`);
        this.name = "GroupError";
        this.action = action;
        this.code = code;
        this.error = msg;
        this.group_id = group_id;
    }
}

// ============================================================
// Wire Protocol Types
// ============================================================

export interface GroupRequest {
    action: string;
    request_id: string;
    group_id?: string;
    params?: Record<string, any> | null;
}

export function buildGroupRequest(
    action: string,
    request_id: string,
    group_id: string = "",
    params?: Record<string, any> | null
): GroupRequest {
    const req: GroupRequest = { action, request_id };
    if (group_id) req.group_id = group_id;
    if (params != null) req.params = params;
    return req;
}

export function groupRequestToJson(req: GroupRequest): string {
    return JSON.stringify(req);
}

export interface GroupResponse {
    action: string;
    request_id: string;
    code: number;
    group_id: string;
    data?: any;
    error: string;
}

export function parseGroupResponse(d: Record<string, any>): GroupResponse {
    return {
        action: d.action ?? "",
        request_id: d.request_id ?? "",
        code: d.code ?? -1,
        group_id: d.group_id ?? "",
        data: d.data,
        error: d.error ?? "",
    };
}

export interface GroupNotify {
    action: string; // always "group_notify"
    group_id: string;
    event: string;
    data?: any;
    timestamp: number;
}

export function parseGroupNotify(d: Record<string, any>): GroupNotify {
    return {
        action: d.action ?? "group_notify",
        group_id: d.group_id ?? "",
        event: d.event ?? "",
        data: d.data,
        timestamp: d.timestamp ?? 0,
    };
}

// ============================================================
// Domain Model Types
// ============================================================

export interface GroupMessage {
    msg_id: number;
    sender: string;
    content: string;
    content_type: string;
    timestamp: number;
    metadata?: Record<string, any> | null;
}

export interface GroupEvent {
    event_id: number;
    event_type: string;
    actor: string;
    timestamp: number;
    target?: string;
    data?: Record<string, any> | null;
}

export interface MsgCursor {
    start_msg_id: number;
    current_msg_id: number;
    latest_msg_id: number;
    unread_count: number;
}

export function createMsgCursor(d?: Partial<MsgCursor>): MsgCursor {
    return {
        start_msg_id: d?.start_msg_id ?? 0,
        current_msg_id: d?.current_msg_id ?? 0,
        latest_msg_id: d?.latest_msg_id ?? 0,
        unread_count: d?.unread_count ?? 0,
    };
}

export interface EventCursor {
    start_event_id: number;
    current_event_id: number;
    latest_event_id: number;
    unread_count: number;
}

export function createEventCursor(d?: Partial<EventCursor>): EventCursor {
    return {
        start_event_id: d?.start_event_id ?? 0,
        current_event_id: d?.current_event_id ?? 0,
        latest_event_id: d?.latest_event_id ?? 0,
        unread_count: d?.unread_count ?? 0,
    };
}

export interface CursorState {
    msg_cursor: MsgCursor;
    event_cursor: EventCursor;
}

// ============================================================
// Operation Response Types
// ============================================================


export interface CreateGroupResp {
    group_id: string;
    group_url: string;
}

export interface SendMessageResp {
    msg_id: number;
    timestamp: number;
}

export interface PullMessagesResp {
    messages: Record<string, any>[];
    has_more: boolean;
    latest_msg_id: number;
}

export interface PullEventsResp {
    events: Record<string, any>[];
    has_more: boolean;
    latest_event_id: number;
}

export interface GroupInfoResp {
    group_id: string;
    name: string;
    creator: string;
    visibility: string;
    member_count: number;
    created_at: number;
    updated_at: number;
    alias: string;
    subject: string;
    status: string;
    tags: string[];
    master: string;
}

export interface BanlistResp {
    banned: Record<string, any>[];
}

export interface RequestJoinResp {
    /** "joined" = 已直接加入（公开群）, "pending" = 等待审核（私密群） */
    status: string;
    request_id: string;
}

export interface BatchReviewResp {
    processed: number;
    total: number;
}

export interface PendingRequestsResp {
    requests: Record<string, any>[];
}

export interface MembersResp {
    members: Record<string, any>[];
}

export interface AdminsResp {
    admins: Record<string, any>[];
}

export interface RulesResp {
    max_members: number;
    max_message_size: number;
    broadcast_policy?: Record<string, any> | null;
}

export interface AnnouncementResp {
    content: string;
    updated_by: string;
    updated_at: number;
}

export interface JoinRequirementsResp {
    mode: string;
    require_all: boolean;
}

export interface MasterResp {
    master: string;
    master_transferred_at: number;
    transfer_reason: string;
}

export interface InviteCodeResp {
    code: string;
    group_id: string;
    created_by: string;
    created_at: number;
    label: string;
    max_uses: number;
    expires_at: number;
}

export interface InviteCodeListResp {
    codes: Record<string, any>[];
}

export interface BroadcastLockResp {
    acquired: boolean;
    expires_at: number;
    holder: string;
}

export interface BroadcastPermissionResp {
    allowed: boolean;
    reason: string;
}

export interface SyncStatusResp {
    msg_cursor: MsgCursor;
    event_cursor: EventCursor;
    sync_percentage: number;
}

export interface SyncLogResp {
    entries: Record<string, any>[];
}

export interface ChecksumResp {
    file: string;
    checksum: string;
}

export interface PublicGroupInfoResp {
    group_id: string;
    name: string;
    creator: string;
    visibility: string;
    member_count: number;
    created_at: number;
    alias: string;
    subject: string;
    tags: string[];
    join_mode: string;
}

export interface SearchGroupsResp {
    groups: PublicGroupInfoResp[];
    total: number;
}

export interface DigestResp {
    date: string;
    period: string;
    message_count: number;
    unique_senders: number;
    data_size: number;
    generated_at: number;
    top_contributors: Record<string, any>[];
}

export interface MembershipInfo {
    group_id: string;
    group_url: string;
    group_server: string;
    session_id: string;
    role: string;
    status: number;
    created_at: number;
    updated_at: number;
}

export interface ListMyGroupsResp {
    groups: MembershipInfo[];
    total: number;
}

export interface GetFileResp {
    data: string;
    total_size: number;
    offset: number;
}

export interface GetSummaryResp {
    date: string;
    message_count: number;
    senders: string[];
    data_size: number;
}

export interface GetMetricsResp {
    goroutines: number;
    alloc_mb: number;
    sys_mb: number;
    gc_cycles: number;
}

// ============================================================
// Notify Event Constants
// ============================================================

export const NOTIFY_NEW_MESSAGE = "new_message";
export const NOTIFY_NEW_EVENT = "new_event";
export const NOTIFY_GROUP_INVITE = "group_invite";
export const NOTIFY_JOIN_APPROVED = "join_approved";
export const NOTIFY_JOIN_REJECTED = "join_rejected";
export const NOTIFY_JOIN_REQUEST_RECEIVED = "join_request_received";
export const NOTIFY_GROUP_MESSAGE = "group_message";
export const NOTIFY_GROUP_EVENT = "group_event";
// Group Event Type Constants
export const EVENT_MEMBER_JOINED = "member_joined";
export const EVENT_MEMBER_REMOVED = "member_removed";
export const EVENT_MEMBER_LEFT = "member_left";
export const EVENT_MEMBER_BANNED = "member_banned";
export const EVENT_META_UPDATED = "meta_updated";
export const EVENT_RULES_UPDATED = "rules_updated";
export const EVENT_ANNOUNCEMENT_UPDATED = "announcement_updated";
export const EVENT_GROUP_DISSOLVED = "group_dissolved";
export const EVENT_MASTER_TRANSFERRED = "master_transferred";
export const EVENT_GROUP_SUSPENDED = "group_suspended";
export const EVENT_GROUP_RESUMED = "group_resumed";
export const EVENT_MEMBER_UNBANNED = "member_unbanned";
export const EVENT_JOIN_REQUIREMENTS_UPDATED = "join_requirements_updated";
export const EVENT_INVITE_CODE_CREATED = "invite_code_created";
export const EVENT_INVITE_CODE_REVOKED = "invite_code_revoked";

// ============================================================
// Duty (值班) Types
// ============================================================

export interface DutyConfig {
    mode: "none" | "fixed" | "rotation";
    rotation_strategy?: "round_robin" | "random";
    shift_duration_ms?: number;
    max_messages_per_shift?: number;
    duty_priority_window_ms?: number;
    enable_rule_prelude?: boolean;
    agents?: string[];
}

export interface DutyState {
    current_duty_agent?: string;
    shift_start_time?: number;
    messages_in_shift?: number;
    [key: string]: any;
}

export interface DutyStatusResp {
    config: DutyConfig;
    state: DutyState;
}

// ============================================================
// Batch Push Constants & Types
// ============================================================

export const ACTION_MESSAGE_BATCH_PUSH = "message_batch_push";

export interface GroupMessageBatch {
    messages: GroupMessage[];
    start_msg_id: number;
    latest_msg_id: number;
    count: number;
}
