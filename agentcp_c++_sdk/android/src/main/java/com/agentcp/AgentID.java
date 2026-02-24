package com.agentcp;

import android.os.Handler;
import android.os.Looper;
import android.util.Log;

import com.agentcp.store.ChatMessage;
import com.agentcp.store.GroupChatMessage;
import com.agentcp.store.GroupMessageStore;
import com.agentcp.store.MessageStore;
import com.agentcp.store.StorageConfig;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.Timer;
import java.util.TimerTask;

public final class AgentID implements AutoCloseable {
    private long nativeHandle;
    private MessageStore messageStore;
    private MessageCallback userCallback;

    // Group module
    private GroupMessageStore groupMessageStore;
    private GroupMessageCallback userGroupMsgCallback;
    private GroupEventCallback userGroupEvtCallback;
    private final Set<String> onlineGroups = new HashSet<>();
    private Timer heartbeatTimer;
    private long heartbeatIntervalMs = 180_000; // 3 minutes, mirrors Node SDK

    private static final String TAG = "AgentID";

    AgentID(long handle) {
        if (handle == 0) {
            throw new IllegalStateException("Native AgentID handle is null");
        }
        this.nativeHandle = handle;
    }

    // ===== P2P Message Store =====

    public void enableMessageStore() {
        AgentCP sdk = AgentCP.getInstance();
        StorageConfig config = sdk.getStorageConfig();
        if (sdk.getAppContext() == null || config == null) {
            throw new IllegalStateException(
                    "Must call AgentCP.initialize(Context, StorageConfig) before enabling message store");
        }
        if (this.messageStore != null) {
            this.messageStore.close();
        }
        this.messageStore = new MessageStore(sdk.getAppContext(), getAID(), config);
    }

    public MessageStore getMessageStore() {
        return messageStore;
    }

    // ===== Agent Lifecycle =====

    public Result online() {
        return nativeOnline(nativeHandle);
    }

    public void offline() {
        // Close group session before going offline (mirrors Node SDK closeGroupClient in Offline)
        leaveAllGroupSessions();
        nativeOffline(nativeHandle);
    }

    public boolean isOnline() {
        return nativeIsOnline(nativeHandle);
    }

    public AgentState getState() {
        return AgentState.fromValue(nativeGetState(nativeHandle));
    }

    public String getAID() {
        return nativeGetAID(nativeHandle);
    }

    public String getSignature() {
        return nativeGetSignature(nativeHandle);
    }

    // ===== P2P Message Handling =====

    public void setMessageHandler(MessageCallback callback) {
        this.userCallback = callback;
        nativeSetMessageHandler(nativeHandle, (msgId, sessId, sender, ts, blocks) -> {
            if (messageStore != null) {
                try {
                    ChatMessage msg = ChatMessage.received(msgId, sessId, sender, ts, blocks);
                    messageStore.saveMessage(msg);
                } catch (Exception e) {
                    Log.e(TAG, "Failed to store received message: " + msgId, e);
                }
            }
            if (userCallback != null) {
                userCallback.onMessage(msgId, sessId, sender, ts, blocks);
            }
        });
    }

    public void setInviteHandler(InviteCallback callback) {
        nativeSetInviteHandler(nativeHandle, callback);
    }

    public void setStateChangeHandler(StateChangeCallback callback) {
        nativeSetStateChangeHandler(nativeHandle, callback);
    }

    // ===== Session Management =====

    public String createSession(String[] members) {
        return nativeCreateSession(nativeHandle, members);
    }

    public Result inviteAgent(String sessionId, String agentId) {
        return nativeInviteAgent(nativeHandle, sessionId, agentId);
    }

    public Result joinSession(String sessionId) {
        return nativeJoinSession(nativeHandle, sessionId);
    }

    public String[] getActiveSessions() {
        return nativeGetActiveSessions(nativeHandle);
    }

    public String getSessionInfo(String sessionId) {
        return nativeGetSessionInfo(nativeHandle, sessionId);
    }

    public Result sendMessage(String sessionId, String peerAid, String blocksJson) {
        Log.i(TAG, "sendMessage called: session=" + sessionId + ", peerAid='" + peerAid + "', blocksLen=" + (blocksJson != null ? blocksJson.length() : 0));
        Result r = nativeSendMessage(nativeHandle, sessionId, peerAid, blocksJson);
        if (r.ok() && messageStore != null) {
            try {
                ChatMessage msg = ChatMessage.sent(sessionId, getAID(), peerAid, blocksJson);
                messageStore.saveMessage(msg);
            } catch (Exception e) {
                Log.e(TAG, "Failed to store sent message for session: " + sessionId, e);
            }
        }
        return r;
    }

    @Deprecated
    public Result sendMessage(String sessionId, String blocksJson) {
        return sendMessage(sessionId, sessionId, blocksJson);
    }

    // ============================================================
    // Group Module
    // ============================================================

    /**
     * Enable group message store (SQLite-based, following P2P MessageStore pattern).
     */
    public void enableGroupMessageStore() {
        AgentCP sdk = AgentCP.getInstance();
        StorageConfig config = sdk.getStorageConfig();
        if (sdk.getAppContext() == null || config == null) {
            throw new IllegalStateException(
                    "Must call AgentCP.initialize(Context, StorageConfig) before enabling group message store");
        }
        if (this.groupMessageStore != null) {
            this.groupMessageStore.close();
        }
        this.groupMessageStore = new GroupMessageStore(sdk.getAppContext(), getAID(), config);
    }

    public GroupMessageStore getGroupMessageStore() {
        return groupMessageStore;
    }

    /**
     * Initialize group client. Must be called after online().
     * Mirrors Node SDK's initGroupClient().
     *
     * @param sessionId Session ID with group.{issuer}
     * @param targetAid Target group AID, empty for auto-computed "group.{issuer}"
     */
    public void initGroupClient(String sessionId, String targetAid) {
        nativeInitGroupClient(nativeHandle, sessionId, targetAid != null ? targetAid : "");
        // Set default event handler that auto-stores messages + auto-ACKs
        // Mirrors Node SDK's _createDefaultGroupEventHandler()
        setupDefaultGroupEventHandler();
    }

    /**
     * Initialize group client with auto-computed target AID.
     */
    public void initGroupClient(String sessionId) {
        initGroupClient(sessionId, "");
    }

    /**
     * Close group client and release resources.
     * Mirrors Node SDK's closeGroupClient().
     */
    public void closeGroupClient() {
        stopHeartbeat();
        onlineGroups.clear();
        nativeCloseGroupClient(nativeHandle);
    }

    /**
     * Get the group target AID (e.g. "group.aid.net").
     */
    public String getGroupTargetAid() {
        return nativeGetGroupTargetAid(nativeHandle);
    }

    /**
     * Set group message callback (overrides the default auto-store handler).
     * Mirrors Node SDK's setGroupEventHandler().
     */
    public void setGroupMessageHandler(GroupMessageCallback callback) {
        this.userGroupMsgCallback = callback;
        // Re-setup the native handler to include the user callback
        setupNativeGroupEventHandler();
    }

    /**
     * Set group event callback for non-message events.
     */
    public void setGroupEventHandler(GroupEventCallback callback) {
        this.userGroupEvtCallback = callback;
        setupNativeGroupEventHandler();
    }

    /**
     * Register online in group AP.
     */
    public void groupRegisterOnline() {
        nativeGroupRegisterOnline(nativeHandle);
    }

    /**
     * Unregister online in group AP.
     */
    public void groupUnregisterOnline() {
        nativeGroupUnregisterOnline(nativeHandle);
    }

    /**
     * Send group heartbeat.
     */
    public void groupHeartbeat() {
        nativeGroupHeartbeat(nativeHandle);
    }

    /**
     * Setup the default group event handler that:
     * - Auto-stores group messages to GroupMessageStore
     * - Auto-ACKs messages
     * - Forwards to user callbacks
     * Mirrors Node SDK's _createDefaultGroupEventHandler().
     */
    private void setupDefaultGroupEventHandler() {
        setupNativeGroupEventHandler();
    }

    private void setupNativeGroupEventHandler() {
        // Create interceptor that auto-stores + auto-ACKs batch, then forwards to user callback
        GroupMessageCallback msgInterceptor = (groupId, batchJson) -> {
            Log.d(TAG, "[Group] onGroupMessageBatch: group=" + groupId);
            try {
                JSONObject batch = new JSONObject(batchJson);
                JSONArray messages = batch.optJSONArray("messages");
                if (messages != null && messages.length() > 0) {
                    // Sort by msg_id ascending
                    List<JSONObject> sorted = new ArrayList<>();
                    for (int i = 0; i < messages.length(); i++) {
                        sorted.add(messages.getJSONObject(i));
                    }
                    sorted.sort((a, b) -> Long.compare(a.optLong("msg_id", 0), b.optLong("msg_id", 0)));

                    // Auto-store messages (mirrors Node SDK processAndAckBatch)
                    if (groupMessageStore != null) {
                        List<GroupChatMessage> chatMsgs = new ArrayList<>();
                        for (JSONObject m : sorted) {
                            chatMsgs.add(GroupChatMessage.create(
                                    groupId,
                                    m.optLong("msg_id", 0),
                                    m.optString("sender", ""),
                                    m.optString("content", ""),
                                    m.optString("content_type", "text/plain"),
                                    m.optLong("timestamp", 0),
                                    m.has("metadata") ? m.getJSONObject("metadata").toString() : null));
                        }
                        try {
                            groupMessageStore.saveMessages(groupId, chatMsgs);
                        } catch (Exception e) {
                            Log.e(TAG, "[Group] Failed to store batch messages", e);
                        }
                    }

                    // Auto-ACK last message in sorted batch (async fire-and-forget)
                    long lastMsgId = sorted.get(sorted.size() - 1).optLong("msg_id", 0);
                    if (lastMsgId > 0) {
                        final long handle = nativeHandle;
                        if (handle != 0) {
                            new Thread(() -> {
                                try {
                                    nativeGroupAckMessages(handle, groupId, lastMsgId);
                                } catch (Exception e) {
                                    Log.w(TAG, "[Group] auto ack batch failed: group=" + groupId + " lastMsgId=" + lastMsgId, e);
                                }
                            }).start();
                        }
                    }
                }
            } catch (Exception e) {
                Log.e(TAG, "[Group] Failed to process batch", e);
            }
            // Forward to user callback
            if (userGroupMsgCallback != null) {
                userGroupMsgCallback.onGroupMessageBatch(groupId, batchJson);
            }
        };

        nativeSetGroupEventHandler(nativeHandle, msgInterceptor, userGroupEvtCallback);
    }

    // ===== Group Session Lifecycle (mirrors Node SDK joinGroupSession / leaveGroupSession) =====

    /**
     * Join a group session:
     * 1. register_online -> tell group.ap we're online
     * 2. Pull historical messages (cold-start sync)
     * 3. Add to online groups set
     * 4. Start heartbeat timer if needed
     * Mirrors Node SDK's joinGroupSession().
     * MUST be called from a background thread (blocking native call).
     */
    public void joinGroupSession(String groupId) {
        nativeGroupRegisterOnline(nativeHandle);

        // Cold-start sync: pull messages after register_online, before entering batch push mode
        // Mirrors Node SDK: pullAndStoreMessages after register_online
        if (groupMessageStore != null) {
            try {
                long lastMsgId = groupMessageStore.getLastMsgId(groupId);
                Log.i(TAG, "[Group] joinGroupSession cold-start sync: group=" + groupId + " afterMsgId=" + lastMsgId);
                pullAndStoreGroupMessages(groupId, lastMsgId, 50);
            } catch (Exception e) {
                Log.w(TAG, "[Group] joinGroupSession cold-start sync failed: group=" + groupId, e);
            }
        }

        onlineGroups.add(groupId);
        Log.i(TAG, "[Group] joinGroupSession: group=" + groupId);
        ensureHeartbeat();
    }

    /**
     * Leave a group session:
     * 1. Remove from online groups set
     * 2. If no online groups left, unregister_online + stop heartbeat
     * Mirrors Node SDK's leaveGroupSession().
     * MUST be called from a background thread (blocking native call).
     */
    public void leaveGroupSession(String groupId) {
        onlineGroups.remove(groupId);
        if (onlineGroups.isEmpty()) {
            try {
                nativeGroupUnregisterOnline(nativeHandle);
            } catch (Exception e) {
                Log.w(TAG, "[Group] unregisterOnline failed", e);
            }
            stopHeartbeat();
        }
    }

    /**
     * Leave all group sessions.
     * Mirrors Node SDK's leaveAllGroupSessions().
     */
    public void leaveAllGroupSessions() {
        String[] groups = onlineGroups.toArray(new String[0]);
        for (String gid : groups) {
            try {
                leaveGroupSession(gid);
            } catch (Exception e) {
                Log.w(TAG, "[Group] leaveGroupSession failed for " + gid, e);
            }
        }
    }

    /**
     * Get currently online groups.
     */
    public Set<String> getOnlineGroups() {
        return new HashSet<>(onlineGroups);
    }

    /**
     * Set heartbeat interval in milliseconds (default 180000 = 3 minutes).
     * Mirrors Node SDK's setHeartbeatInterval().
     */
    public void setHeartbeatInterval(long intervalMs) {
        this.heartbeatIntervalMs = intervalMs;
        if (heartbeatTimer != null) {
            stopHeartbeat();
            ensureHeartbeat();
        }
    }

    private void ensureHeartbeat() {
        if (heartbeatTimer != null) return;
        if (onlineGroups.isEmpty()) return;

        heartbeatTimer = new Timer("GroupHeartbeat", true);
        heartbeatTimer.scheduleAtFixedRate(new TimerTask() {
            @Override
            public void run() {
                sendHeartbeat();
            }
        }, heartbeatIntervalMs, heartbeatIntervalMs);
        Log.i(TAG, "[Group] heartbeat started: interval=" + heartbeatIntervalMs + "ms");
    }

    private void stopHeartbeat() {
        if (heartbeatTimer != null) {
            heartbeatTimer.cancel();
            heartbeatTimer = null;
            Log.i(TAG, "[Group] heartbeat stopped");
        }
    }

    private void sendHeartbeat() {
        try {
            nativeGroupHeartbeat(nativeHandle);
        } catch (Exception e) {
            Log.w(TAG, "[Group] heartbeat failed", e);
        }
    }

    // ===== Group Operations (call from background thread) =====

    /**
     * Send a group message.
     * @return JSON string with {msg_id, timestamp}
     */
    public String groupSendMessage(String groupId, String content, String contentType, String metadataJson) {
        return nativeGroupSendMessage(nativeHandle, groupId, content,
                contentType != null ? contentType : "", metadataJson != null ? metadataJson : "");
    }

    /**
     * Pull messages from server.
     * @param afterMsgId 0 for auto-cursor mode, >0 for explicit position
     * @return JSON string with {messages[], has_more, latest_msg_id}
     */
    public String groupPullMessages(String groupId, long afterMsgId, int limit) {
        return nativeGroupPullMessages(nativeHandle, groupId, afterMsgId, limit);
    }

    /**
     * ACK messages (update server cursor).
     */
    public void groupAckMessages(String groupId, long msgId) {
        nativeGroupAckMessages(nativeHandle, groupId, msgId);
    }

    /**
     * Get group info.
     * @return JSON string with group details
     */
    public String groupGetInfo(String groupId) {
        return nativeGroupGetInfo(nativeHandle, groupId);
    }

    /**
     * List my groups from Home AP.
     * @return JSON string with {groups[], total}
     */
    public String groupListMyGroups(int status) {
        return nativeGroupListMyGroups(nativeHandle, status);
    }

    /**
     * Unregister group membership index from Home AP.
     */
    public void groupUnregisterMembership(String groupId) {
        nativeGroupUnregisterMembership(nativeHandle, groupId);
    }

    /**
     * Create a new group.
     * @return JSON string with {group_id, group_url}
     */
    public String groupCreateGroup(String name, String alias, String subject,
                                   String visibility, String description, String[] tags) {
        return nativeGroupCreateGroup(
                nativeHandle,
                name != null ? name : "",
                alias != null ? alias : "",
                subject != null ? subject : "",
                visibility != null ? visibility : "",
                description != null ? description : "",
                tags
        );
    }

    /**
     * Join group by URL.
     * With inviteCode: direct join. Without inviteCode: submit join request.
     * @return request_id for approval flow, or empty string for invite code flow.
     */
    public String groupJoinByUrl(String groupUrl, String inviteCode, String message) {
        return nativeGroupJoinByUrl(
                nativeHandle,
                groupUrl != null ? groupUrl : "",
                inviteCode != null ? inviteCode : "",
                message != null ? message : ""
        );
    }

    /**
     * Request join a group.
     * @return request_id
     */
    public String groupRequestJoin(String groupId, String message) {
        return nativeGroupRequestJoin(
                nativeHandle,
                groupId,
                message != null ? message : ""
        );
    }

    /**
     * Join group with invite code.
     */
    public void groupUseInviteCode(String groupId, String code) {
        nativeGroupUseInviteCode(nativeHandle, groupId, code);
    }

    /**
     * Review a pending join request.
     * action should be "approve" or "reject".
     */
    public void groupReviewJoinRequest(String groupId, String agentId, String action, String reason) {
        nativeGroupReviewJoinRequest(
                nativeHandle,
                groupId,
                agentId,
                action,
                reason != null ? reason : ""
        );
    }

    /**
     * Get pending join requests.
     * @return JSON string with {requests:[...]}
     */
    public String groupGetPendingRequests(String groupId) {
        return nativeGroupGetPendingRequests(nativeHandle, groupId);
    }

    /**
     * Leave group membership.
     */
    public void groupLeaveGroup(String groupId) {
        nativeGroupLeaveGroup(nativeHandle, groupId);
    }

    /**
     * Get current members.
     * @return JSON string with {members:[...]}
     */
    public String groupGetMembers(String groupId) {
        return nativeGroupGetMembers(nativeHandle, groupId);
    }

    /**
     * Create invite code.
     * @return JSON string with invite code details
     */
    public String groupCreateInviteCode(String groupId, String label, int maxUses, long expiresAt) {
        return nativeGroupCreateInviteCode(
                nativeHandle,
                groupId,
                label != null ? label : "",
                maxUses,
                expiresAt
        );
    }

    /**
     * List invite codes.
     * @return JSON string with {codes:[...]}
     */
    public String groupListInviteCodes(String groupId) {
        return nativeGroupListInviteCodes(nativeHandle, groupId);
    }

    /**
     * Revoke invite code.
     */
    public void groupRevokeInviteCode(String groupId, String code) {
        nativeGroupRevokeInviteCode(nativeHandle, groupId, code);
    }

    /**
     * Add member into group.
     */
    public void groupAddMember(String groupId, String agentId, String role) {
        nativeGroupAddMember(
                nativeHandle,
                groupId,
                agentId,
                role != null ? role : ""
        );
    }

    /**
     * Remove member from group.
     */
    public void groupRemoveMember(String groupId, String agentId) {
        nativeGroupRemoveMember(nativeHandle, groupId, agentId);
    }

    /**
     * Change a member role.
     */
    public void groupChangeMemberRole(String groupId, String agentId, String newRole) {
        nativeGroupChangeMemberRole(nativeHandle, groupId, agentId, newRole);
    }

    /**
     * Ban agent in group.
     */
    public void groupBanAgent(String groupId, String agentId, String reason, long expiresAt) {
        nativeGroupBanAgent(
                nativeHandle,
                groupId,
                agentId,
                reason != null ? reason : "",
                expiresAt
        );
    }

    /**
     * Unban agent in group.
     */
    public void groupUnbanAgent(String groupId, String agentId) {
        nativeGroupUnbanAgent(nativeHandle, groupId, agentId);
    }

    /**
     * Get banlist.
     * @return JSON string with {banned:[...]}
     */
    public String groupGetBanlist(String groupId) {
        return nativeGroupGetBanlist(nativeHandle, groupId);
    }

    /**
     * Dissolve group.
     */
    public void groupDissolveGroup(String groupId) {
        nativeGroupDissolveGroup(nativeHandle, groupId);
    }

    /**
     * Pull group events from server.
     * @return JSON string with {events[], has_more, latest_event_id}
     */
    public String groupPullEvents(String groupId, long afterEventId, int limit) {
        return nativeGroupPullEvents(nativeHandle, groupId, afterEventId, limit);
    }

    /**
     * ACK group events (update server cursor).
     */
    public void groupAckEvents(String groupId, long eventId) {
        nativeGroupAckEvents(nativeHandle, groupId, eventId);
    }

    /**
     * Get current server cursor.
     * @return JSON string with {msg_cursor, event_cursor}
     */
    public String groupGetCursor(String groupId) {
        return nativeGroupGetCursor(nativeHandle, groupId);
    }

    /**
     * Sync group messages/events using server cursor + local cursor store.
     * Mirrors Node SDK's syncGroup().
     */
    public void groupSync(String groupId, GroupSyncHandler handler) {
        if (groupId == null || groupId.trim().isEmpty()) {
            throw new IllegalArgumentException("groupId must not be empty");
        }
        if (handler == null) {
            throw new IllegalArgumentException("handler must not be null");
        }
        try {
            Log.i(TAG, "[Group] sync start: group=" + groupId);
            nativeGroupSync(nativeHandle, groupId, handler);
            Log.i(TAG, "[Group] sync completed: group=" + groupId);
        } catch (RuntimeException e) {
            Log.e(TAG, "[Group] sync failed: group=" + groupId, e);
            throw e;
        }
    }

    /**
     * Batch review join requests.
     * @return JSON string with {processed, total}
     */
    public String groupBatchReviewJoinRequests(String groupId, String[] agentIds, String action, String reason) {
        return nativeGroupBatchReviewJoinRequests(
                nativeHandle,
                groupId,
                agentIds,
                action,
                reason != null ? reason : ""
        );
    }

    /**
     * Update group meta.
     * paramsJson should be a JSON object string.
     */
    public void groupUpdateMeta(String groupId, String paramsJson) {
        nativeGroupUpdateMeta(
                nativeHandle,
                groupId,
                paramsJson != null ? paramsJson : "{}"
        );
    }

    /**
     * Get group admins.
     * @return JSON string with {admins:[...]}
     */
    public String groupGetAdmins(String groupId) {
        return nativeGroupGetAdmins(nativeHandle, groupId);
    }

    /**
     * Get group rules.
     * @return JSON string with {max_members, max_message_size, broadcast_policy}
     */
    public String groupGetRules(String groupId) {
        return nativeGroupGetRules(nativeHandle, groupId);
    }

    /**
     * Update group rules.
     * paramsJson should be a JSON object string.
     */
    public void groupUpdateRules(String groupId, String paramsJson) {
        nativeGroupUpdateRules(
                nativeHandle,
                groupId,
                paramsJson != null ? paramsJson : "{}"
        );
    }

    /**
     * Get group announcement.
     * @return JSON string with {content, updated_by, updated_at}
     */
    public String groupGetAnnouncement(String groupId) {
        return nativeGroupGetAnnouncement(nativeHandle, groupId);
    }

    /**
     * Update group announcement.
     */
    public void groupUpdateAnnouncement(String groupId, String content) {
        nativeGroupUpdateAnnouncement(
                nativeHandle,
                groupId,
                content != null ? content : ""
        );
    }

    /**
     * Get join requirements.
     * @return JSON string with {mode, require_all}
     */
    public String groupGetJoinRequirements(String groupId) {
        return nativeGroupGetJoinRequirements(nativeHandle, groupId);
    }

    /**
     * Update join requirements.
     * paramsJson should be a JSON object string.
     */
    public void groupUpdateJoinRequirements(String groupId, String paramsJson) {
        nativeGroupUpdateJoinRequirements(
                nativeHandle,
                groupId,
                paramsJson != null ? paramsJson : "{}"
        );
    }

    /**
     * Suspend group.
     */
    public void groupSuspend(String groupId) {
        nativeGroupSuspend(nativeHandle, groupId);
    }

    /**
     * Resume group.
     */
    public void groupResume(String groupId) {
        nativeGroupResume(nativeHandle, groupId);
    }

    /**
     * Transfer master role.
     */
    public void groupTransferMaster(String groupId, String newMasterAid, String reason) {
        nativeGroupTransferMaster(
                nativeHandle,
                groupId,
                newMasterAid,
                reason != null ? reason : ""
        );
    }

    /**
     * Get current master info.
     * @return JSON string with {master, master_transferred_at, transfer_reason}
     */
    public String groupGetMaster(String groupId) {
        return nativeGroupGetMaster(nativeHandle, groupId);
    }

    /**
     * Acquire broadcast lock.
     * @return JSON string with {acquired, expires_at, holder}
     */
    public String groupAcquireBroadcastLock(String groupId) {
        return nativeGroupAcquireBroadcastLock(nativeHandle, groupId);
    }

    /**
     * Release broadcast lock.
     */
    public void groupReleaseBroadcastLock(String groupId) {
        nativeGroupReleaseBroadcastLock(nativeHandle, groupId);
    }

    /**
     * Check broadcast permission.
     * @return JSON string with {allowed, reason}
     */
    public String groupCheckBroadcastPermission(String groupId) {
        return nativeGroupCheckBroadcastPermission(nativeHandle, groupId);
    }

    /**
     * Get sync status.
     * @return JSON string with {msg_cursor, event_cursor, sync_percentage}
     */
    public String groupGetSyncStatus(String groupId) {
        return nativeGroupGetSyncStatus(nativeHandle, groupId);
    }

    /**
     * Get sync log entries.
     * @return JSON string with {entries:[...]}
     */
    public String groupGetSyncLog(String groupId, String startDate) {
        return nativeGroupGetSyncLog(
                nativeHandle,
                groupId,
                startDate != null ? startDate : ""
        );
    }

    /**
     * Get file checksum.
     * @return JSON string with {file, checksum}
     */
    public String groupGetChecksum(String groupId, String file) {
        return nativeGroupGetChecksum(
                nativeHandle,
                groupId,
                file != null ? file : ""
        );
    }

    /**
     * Get message checksum by date.
     * @return JSON string with {file, checksum}
     */
    public String groupGetMessageChecksum(String groupId, String date) {
        return nativeGroupGetMessageChecksum(
                nativeHandle,
                groupId,
                date != null ? date : ""
        );
    }

    /**
     * Get public group info.
     * @return JSON string with public group fields
     */
    public String groupGetPublicInfo(String groupId) {
        return nativeGroupGetPublicInfo(nativeHandle, groupId);
    }

    /**
     * Search groups.
     * @return JSON string with {groups:[...], total}
     */
    public String groupSearchGroups(String keyword, String[] tags, int limit, int offset) {
        return nativeGroupSearchGroups(
                nativeHandle,
                keyword != null ? keyword : "",
                tags,
                limit,
                offset
        );
    }

    /**
     * Generate digest.
     * @return JSON string with digest fields
     */
    public String groupGenerateDigest(String groupId, String date, String period) {
        return nativeGroupGenerateDigest(
                nativeHandle,
                groupId,
                date != null ? date : "",
                period != null ? period : ""
        );
    }

    /**
     * Get digest.
     * @return JSON string with digest fields
     */
    public String groupGetDigest(String groupId, String date, String period) {
        return nativeGroupGetDigest(
                nativeHandle,
                groupId,
                date != null ? date : "",
                period != null ? period : ""
        );
    }

    /**
     * Get file content fragment.
     * @return JSON string with {data, total_size, offset}
     */
    public String groupGetFile(String groupId, String file, long offset) {
        return nativeGroupGetFile(
                nativeHandle,
                groupId,
                file != null ? file : "",
                offset
        );
    }

    /**
     * Get summary by date.
     * @return JSON string with {date, message_count, senders, data_size}
     */
    public String groupGetSummary(String groupId, String date) {
        return nativeGroupGetSummary(
                nativeHandle,
                groupId,
                date != null ? date : ""
        );
    }

    /**
     * Get server metrics.
     * @return JSON string with {goroutines, alloc_mb, sys_mb, gc_cycles}
     */
    public String groupGetMetrics() {
        return nativeGroupGetMetrics(nativeHandle);
    }

    /**
     * Pull messages from server and store locally.
     * Mirrors Node SDK's pullAndStoreGroupMessages().
     * Loops until has_more=false, auto-ACKs each batch.
     * MUST be called from a background thread.
     *
     * @return All locally stored messages for this group
     */
    public List<GroupChatMessage> pullAndStoreGroupMessages(String groupId, long afterMsgId, int limit) {
        if (limit <= 0) limit = 50;
        long after = afterMsgId;
        int maxRounds = 100; // safety: prevent infinite loop on misbehaving server

        try {
            while (maxRounds-- > 0) {
                String resultJson = groupPullMessages(groupId, after, limit);
                JSONObject result = new JSONObject(resultJson);
                JSONArray messages = result.optJSONArray("messages");
                if (messages == null || messages.length() == 0) break;

                List<GroupChatMessage> batch = new ArrayList<>();
                long lastMsgId = 0;
                for (int i = 0; i < messages.length(); i++) {
                    JSONObject m = messages.getJSONObject(i);
                    GroupChatMessage msg = GroupChatMessage.create(
                            groupId,
                            m.optLong("msg_id", 0),
                            m.optString("sender", ""),
                            m.optString("content", ""),
                            m.optString("content_type", "text"),
                            m.optLong("timestamp", 0),
                            m.has("metadata") ? m.getJSONObject("metadata").toString() : null
                    );
                    batch.add(msg);
                    lastMsgId = msg.msgId;
                }

                if (groupMessageStore != null) {
                    groupMessageStore.saveMessages(groupId, batch);
                }

                // ACK last message in batch
                if (lastMsgId > 0) {
                    groupAckMessages(groupId, lastMsgId);
                }

                if (lastMsgId <= after) break; // safety: no progress
                after = lastMsgId;
                if (!result.optBoolean("has_more", false)) break;
            }
        } catch (Exception e) {
            Log.w(TAG, "[Group] pullAndStoreGroupMessages error", e);
        }

        // Return all stored messages
        if (groupMessageStore != null) {
            return groupMessageStore.getLatestMessages(groupId, 500);
        }
        return new ArrayList<>();
    }

    // ===== Lifecycle =====

    @Override
    public void close() {
        leaveAllGroupSessions();
        if (groupMessageStore != null) {
            groupMessageStore.close();
            groupMessageStore = null;
        }
        if (messageStore != null) {
            messageStore.close();
            messageStore = null;
        }
        if (nativeHandle != 0) {
            nativeRelease(nativeHandle);
            nativeHandle = 0;
        }
    }

    // ===== Native methods: Agent lifecycle =====
    private native Result nativeOnline(long handle);
    private native void nativeOffline(long handle);
    private native boolean nativeIsOnline(long handle);
    private native int nativeGetState(long handle);
    private native String nativeGetAID(long handle);
    private native String nativeGetSignature(long handle);
    private native void nativeRelease(long handle);

    // ===== Native methods: P2P =====
    private native void nativeSetMessageHandler(long handle, MessageCallback callback);
    private native void nativeSetInviteHandler(long handle, InviteCallback callback);
    private native void nativeSetStateChangeHandler(long handle, StateChangeCallback callback);
    private native String nativeCreateSession(long handle, String[] members);
    private native Result nativeInviteAgent(long handle, String sessionId, String agentId);
    private native Result nativeJoinSession(long handle, String sessionId);
    private native String[] nativeGetActiveSessions(long handle);
    private native String nativeGetSessionInfo(long handle, String sessionId);
    private native Result nativeSendMessage(long handle, String sessionId, String peerAid, String blocksJson);

    // ===== Native methods: Group module =====
    private native void nativeInitGroupClient(long handle, String sessionId, String targetAid);
    private native void nativeCloseGroupClient(long handle);
    private native String nativeGetGroupTargetAid(long handle);
    private native void nativeSetGroupEventHandler(long handle, GroupMessageCallback msgCallback, GroupEventCallback evtCallback);
    private native void nativeGroupRegisterOnline(long handle);
    private native void nativeGroupUnregisterOnline(long handle);
    private native void nativeGroupHeartbeat(long handle);
    private native String nativeGroupSendMessage(long handle, String groupId, String content, String contentType, String metadataJson);
    private native String nativeGroupPullMessages(long handle, String groupId, long afterMsgId, int limit);
    private native void nativeGroupAckMessages(long handle, String groupId, long msgId);
    private native String nativeGroupGetInfo(long handle, String groupId);
    private native String nativeGroupListMyGroups(long handle, int status);
    private native void nativeGroupUnregisterMembership(long handle, String groupId);
    private native String nativeGroupCreateGroup(long handle, String name, String alias, String subject,
                                                 String visibility, String description, String[] tags);
    private native String nativeGroupJoinByUrl(long handle, String groupUrl, String inviteCode, String message);
    private native String nativeGroupRequestJoin(long handle, String groupId, String message);
    private native void nativeGroupUseInviteCode(long handle, String groupId, String code);
    private native void nativeGroupReviewJoinRequest(long handle, String groupId, String agentId, String action, String reason);
    private native String nativeGroupGetPendingRequests(long handle, String groupId);
    private native void nativeGroupLeaveGroup(long handle, String groupId);
    private native String nativeGroupGetMembers(long handle, String groupId);
    private native String nativeGroupCreateInviteCode(long handle, String groupId, String label, int maxUses, long expiresAt);
    private native String nativeGroupListInviteCodes(long handle, String groupId);
    private native void nativeGroupRevokeInviteCode(long handle, String groupId, String code);
    private native void nativeGroupAddMember(long handle, String groupId, String agentId, String role);
    private native void nativeGroupRemoveMember(long handle, String groupId, String agentId);
    private native void nativeGroupChangeMemberRole(long handle, String groupId, String agentId, String newRole);
    private native void nativeGroupBanAgent(long handle, String groupId, String agentId, String reason, long expiresAt);
    private native void nativeGroupUnbanAgent(long handle, String groupId, String agentId);
    private native String nativeGroupGetBanlist(long handle, String groupId);
    private native void nativeGroupDissolveGroup(long handle, String groupId);
    private native String nativeGroupPullEvents(long handle, String groupId, long afterEventId, int limit);
    private native void nativeGroupAckEvents(long handle, String groupId, long eventId);
    private native String nativeGroupGetCursor(long handle, String groupId);
    private native void nativeGroupSync(long handle, String groupId, GroupSyncHandler handler);
    private native String nativeGroupBatchReviewJoinRequests(long handle, String groupId, String[] agentIds, String action, String reason);
    private native void nativeGroupUpdateMeta(long handle, String groupId, String paramsJson);
    private native String nativeGroupGetAdmins(long handle, String groupId);
    private native String nativeGroupGetRules(long handle, String groupId);
    private native void nativeGroupUpdateRules(long handle, String groupId, String paramsJson);
    private native String nativeGroupGetAnnouncement(long handle, String groupId);
    private native void nativeGroupUpdateAnnouncement(long handle, String groupId, String content);
    private native String nativeGroupGetJoinRequirements(long handle, String groupId);
    private native void nativeGroupUpdateJoinRequirements(long handle, String groupId, String paramsJson);
    private native void nativeGroupSuspend(long handle, String groupId);
    private native void nativeGroupResume(long handle, String groupId);
    private native void nativeGroupTransferMaster(long handle, String groupId, String newMasterAid, String reason);
    private native String nativeGroupGetMaster(long handle, String groupId);
    private native String nativeGroupAcquireBroadcastLock(long handle, String groupId);
    private native void nativeGroupReleaseBroadcastLock(long handle, String groupId);
    private native String nativeGroupCheckBroadcastPermission(long handle, String groupId);
    private native String nativeGroupGetSyncStatus(long handle, String groupId);
    private native String nativeGroupGetSyncLog(long handle, String groupId, String startDate);
    private native String nativeGroupGetChecksum(long handle, String groupId, String file);
    private native String nativeGroupGetMessageChecksum(long handle, String groupId, String date);
    private native String nativeGroupGetPublicInfo(long handle, String groupId);
    private native String nativeGroupSearchGroups(long handle, String keyword, String[] tags, int limit, int offset);
    private native String nativeGroupGenerateDigest(long handle, String groupId, String date, String period);
    private native String nativeGroupGetDigest(long handle, String groupId, String date, String period);
    private native String nativeGroupGetFile(long handle, String groupId, String file, long offset);
    private native String nativeGroupGetSummary(long handle, String groupId, String date);
    private native String nativeGroupGetMetrics(long handle);
}
