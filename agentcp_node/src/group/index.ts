/**
 * ACP Group Operations package.
 * Mirrors Python SDK: agentcp/group/__init__.py
 */

// Types
export {
    GroupErrorCode, GroupError,
    GroupRequest, GroupResponse, GroupNotify,
    buildGroupRequest, groupRequestToJson,
    parseGroupResponse, parseGroupNotify,
    GroupMessage, GroupEvent,
    MsgCursor, EventCursor, CursorState,
    createMsgCursor, createEventCursor,
    // Response types
    CreateGroupResp, SendMessageResp, PullMessagesResp, PullEventsResp,
    GroupInfoResp, BanlistResp, BatchReviewResp, PendingRequestsResp,
    RequestJoinResp,
    MembersResp, AdminsResp, RulesResp, AnnouncementResp,
    JoinRequirementsResp, MasterResp,
    InviteCodeResp, InviteCodeListResp,
    BroadcastLockResp, BroadcastPermissionResp,
    SyncStatusResp, SyncLogResp, ChecksumResp,
    PublicGroupInfoResp, SearchGroupsResp, DigestResp,
    MembershipInfo, ListMyGroupsResp, GetFileResp, GetSummaryResp, GetMetricsResp,
    // Notify event constants
    NOTIFY_NEW_MESSAGE, NOTIFY_NEW_EVENT, NOTIFY_GROUP_INVITE,
    NOTIFY_JOIN_APPROVED, NOTIFY_JOIN_REJECTED, NOTIFY_JOIN_REQUEST_RECEIVED,
    NOTIFY_GROUP_MESSAGE, NOTIFY_GROUP_EVENT,
    // Group event type constants
    EVENT_MEMBER_JOINED, EVENT_MEMBER_REMOVED, EVENT_MEMBER_LEFT,
    EVENT_MEMBER_BANNED, EVENT_META_UPDATED, EVENT_RULES_UPDATED,
    EVENT_ANNOUNCEMENT_UPDATED, EVENT_GROUP_DISSOLVED, EVENT_MASTER_TRANSFERRED,
    EVENT_GROUP_SUSPENDED, EVENT_GROUP_RESUMED, EVENT_MEMBER_UNBANNED,
    EVENT_JOIN_REQUIREMENTS_UPDATED, EVENT_INVITE_CODE_CREATED, EVENT_INVITE_CODE_REVOKED,
    // Batch push
    ACTION_MESSAGE_BATCH_PUSH, GroupMessageBatch,
    // Duty types
    DutyConfig, DutyState, DutyStatusResp,
} from './types';

// Client
export { ACPGroupClient, SendFunc } from './client';

// Operations
export { GroupOperations, SyncHandler } from './operations';

// Events
export {
    ACPGroupEventHandler, EventProcessor,
    dispatchAcpNotify, dispatchEvent,
} from './events';

// Cursor Store
export { CursorStore, LocalCursorStore } from './cursor_store';

// Message Store
export { GroupMessageStore, GroupRecord } from './message_store';
