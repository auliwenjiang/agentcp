package com.agentcp.store;

/**
 * Data model for a group chat message.
 * Mirrors Node SDK's GroupMessage type.
 */
public class GroupChatMessage {
    public String groupId;
    public long msgId;
    public String sender;
    public String content;
    public String contentType;
    public long timestamp;
    public String metadataJson;

    public static GroupChatMessage create(String groupId, long msgId, String sender,
                                          String content, String contentType,
                                          long timestamp, String metadataJson) {
        GroupChatMessage msg = new GroupChatMessage();
        msg.groupId = groupId;
        msg.msgId = msgId;
        msg.sender = sender;
        msg.content = content;
        msg.contentType = contentType != null ? contentType : "text";
        msg.timestamp = timestamp;
        msg.metadataJson = metadataJson;
        return msg;
    }
}
