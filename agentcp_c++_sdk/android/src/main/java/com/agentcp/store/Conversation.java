package com.agentcp.store;

public class Conversation {
    public static final int TYPE_SINGLE = 0;
    public static final int TYPE_GROUP = 1;

    public String sessionId;
    public String peerAid;
    public int sessionType;
    public String lastMsgId;
    public long lastMsgTime;
    public String lastMsgPreview;
    public int unreadCount;
}
