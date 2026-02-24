package com.agentcp;

/**
 * Callback interface for group notification events from group.ap.
 * Mirrors Node SDK's ACPGroupEventHandler (minus batch message push which has its own callback).
 */
public interface GroupEventCallback {
    void onNewMessage(String groupId, long latestMsgId, String sender, String preview);
    void onNewEvent(String groupId, long latestEventId, String eventType, String summary);
    void onGroupInvite(String groupId, String groupAddress, String invitedBy);
    void onJoinApproved(String groupId, String groupAddress);
    void onJoinRejected(String groupId, String reason);
    void onJoinRequestReceived(String groupId, String agentId, String message);
    void onGroupEvent(String groupId, String eventJson);
}
