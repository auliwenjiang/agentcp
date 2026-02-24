package com.agentcp.store;

/**
 * Data model for a group conversation summary.
 * Mirrors Node SDK's GroupRecord type.
 */
public class GroupConversation {
    public String groupId;
    public String groupName;
    public String targetAid;
    public long lastMsgId;
    public int messageCount;
    public long lastMessageAt;
    public long joinedAt;
    public int unreadCount;
}
