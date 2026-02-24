/**
 * Group event handler interfaces and dispatch logic.
 * Mirrors Python SDK: agentcp/group/events.py
 */

import { logger } from '../utils';
import {
    GroupNotify, GroupMessage, GroupEvent, GroupMessageBatch,
    NOTIFY_NEW_MESSAGE, NOTIFY_NEW_EVENT, NOTIFY_GROUP_INVITE,
    NOTIFY_JOIN_APPROVED, NOTIFY_JOIN_REJECTED, NOTIFY_JOIN_REQUEST_RECEIVED,
    NOTIFY_GROUP_MESSAGE, NOTIFY_GROUP_EVENT,
} from './types';

/**
 * Abstract handler for ACP group notifications.
 */
export interface ACPGroupEventHandler {
    onNewMessage(groupId: string, latestMsgId: number, sender: string, preview: string): void;
    onNewEvent(groupId: string, latestEventId: number, eventType: string, summary: string): void;
    onGroupInvite(groupId: string, groupAddress: string, invitedBy: string): void;
    onJoinApproved(groupId: string, groupAddress: string): void;
    onJoinRejected(groupId: string, reason: string): void;
    onJoinRequestReceived(groupId: string, agentId: string, message: string): void;
    onGroupMessage?(groupId: string, msg: GroupMessage): void;
    onGroupMessageBatch(groupId: string, batch: GroupMessageBatch): void;
    onGroupEvent(groupId: string, evt: GroupEvent): void;
}

/**
 * Abstract handler for structured group events (from MSG/Session).
 */
export interface EventProcessor {
    onMemberJoined(groupId: string, agentId: string, role: string): void;
    onMemberRemoved(groupId: string, agentId: string, reason: string): void;
    onMemberLeft(groupId: string, agentId: string, reason: string): void;
    onMemberBanned(groupId: string, agentId: string, reason: string): void;
    onMemberUnbanned(groupId: string, agentId: string): void;
    onAnnouncementUpdated(groupId: string, updatedBy: string): void;
    onRulesUpdated(groupId: string, updatedBy: string): void;
    onMetaUpdated(groupId: string, updatedBy: string): void;
    onGroupDissolved(groupId: string, dissolvedBy: string, reason: string): void;
    onMasterTransferred(groupId: string, fromAgent: string, toAgent: string, reason: string): void;
    onGroupSuspended(groupId: string, suspendedBy: string, reason: string): void;
    onGroupResumed(groupId: string, resumedBy: string): void;
    onJoinRequirementsUpdated(groupId: string, updatedBy: string): void;
    onInviteCodeCreated(groupId: string, code: string, createdBy: string): void;
    onInviteCodeRevoked(groupId: string, code: string, revokedBy: string): void;
}

/**
 * Dispatch an ACP group notification to the handler.
 * Returns true if dispatched, false if unrecognized or handler/notify is null.
 */
export function dispatchAcpNotify(handler: ACPGroupEventHandler | null, notify: GroupNotify | null): boolean {
    if (handler == null || notify == null) {
        return false;
    }

    const data = (notify.data && typeof notify.data === 'object') ? notify.data : {};
    const event = notify.event;
    const gid = notify.group_id;

    try {
        if (event === NOTIFY_NEW_MESSAGE) {
            handler.onNewMessage(gid, data.latest_msg_id ?? 0,
                data.sender ?? "", data.preview ?? "");
        } else if (event === NOTIFY_NEW_EVENT) {
            handler.onNewEvent(gid, data.latest_event_id ?? 0,
                data.event_type ?? "", data.summary ?? "");
        } else if (event === NOTIFY_GROUP_INVITE) {
            handler.onGroupInvite(gid, data.group_address ?? "",
                data.invited_by ?? "");
        } else if (event === NOTIFY_JOIN_APPROVED) {
            handler.onJoinApproved(gid, data.group_address ?? "");
        } else if (event === NOTIFY_JOIN_REJECTED) {
            handler.onJoinRejected(gid, data.reason ?? "");
        } else if (event === NOTIFY_JOIN_REQUEST_RECEIVED) {
            handler.onJoinRequestReceived(gid, data.agent_id ?? "",
                data.message ?? "");
        } else if (event === NOTIFY_GROUP_MESSAGE) {
            handler.onGroupMessage?.(gid, data as GroupMessage);
        } else if (event === NOTIFY_GROUP_EVENT) {
            handler.onGroupEvent(gid, data as GroupEvent);
        } else {
            return false;
        }
        return true;
    } catch (e) {
        logger.error(`[GroupEvents] dispatch error for event=${event}:`, e);
        return false;
    }
}

/**
 * Dispatch a group event from MSG/Session to EventProcessor.
 * Returns true if handled, false otherwise.
 */
export function dispatchEvent(processor: EventProcessor | null, msgType: string, payload: string): boolean {
    if (processor == null) {
        return false;
    }

    let data: Record<string, any>;
    try {
        data = JSON.parse(payload);
    } catch {
        return false;
    }

    const gid = data.group_id ?? "";
    const event = data.event ?? msgType;

    try {
        if (event === "member_joined") {
            processor.onMemberJoined(gid, data.agent_id ?? "", data.role ?? "");
        } else if (event === "member_removed") {
            processor.onMemberRemoved(gid, data.agent_id ?? "", data.reason ?? "");
        } else if (event === "member_banned") {
            processor.onMemberBanned(gid, data.agent_id ?? "", data.reason ?? "");
        } else if (event === "announcement_updated") {
            processor.onAnnouncementUpdated(gid, data.updated_by ?? "");
        } else if (event === "rules_updated") {
            processor.onRulesUpdated(gid, data.updated_by ?? "");
        } else if (event === "meta_updated") {
            processor.onMetaUpdated(gid, data.updated_by ?? "");
        } else if (event === "group_dissolved") {
            processor.onGroupDissolved(gid, data.dissolved_by ?? "", data.reason ?? "");
        } else if (event === "master_transferred") {
            processor.onMasterTransferred(gid, data.from_agent ?? "",
                data.to_agent ?? "", data.reason ?? "");
        } else if (event === "group_suspended") {
            processor.onGroupSuspended(gid, data.suspended_by ?? "", data.reason ?? "");
        } else if (event === "group_resumed") {
            processor.onGroupResumed(gid, data.resumed_by ?? "");
        } else if (event === "member_left") {
            processor.onMemberLeft(gid, data.agent_id ?? "", data.reason ?? "");
        } else if (event === "member_unbanned") {
            processor.onMemberUnbanned(gid, data.agent_id ?? "");
        } else if (event === "join_requirements_updated") {
            processor.onJoinRequirementsUpdated(gid, data.updated_by ?? "");
        } else if (event === "invite_code_created") {
            processor.onInviteCodeCreated(gid, data.code ?? "", data.created_by ?? "");
        } else if (event === "invite_code_revoked") {
            processor.onInviteCodeRevoked(gid, data.code ?? "", data.revoked_by ?? "");
        } else {
            return false;
        }
        return true;
    } catch (e) {
        logger.error(`[GroupEvents] dispatch_event error for ${event}:`, e);
        return false;
    }
}
