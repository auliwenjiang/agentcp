package com.agentcp.store;

import java.util.UUID;

public class ChatMessage {
    public static final int DIRECTION_RECEIVED = 0;
    public static final int DIRECTION_SENT = 1;

    public String messageId;
    public String sessionId;
    public String sender;
    public String peerAid;
    public int direction;
    public long timestamp;
    public String blocksJson;
    public String status;

    public static ChatMessage received(String msgId, String sessionId,
                                       String sender, long timestamp, String blocksJson) {
        ChatMessage msg = new ChatMessage();
        msg.messageId = msgId;
        msg.sessionId = sessionId;
        msg.sender = sender;
        msg.peerAid = sender;
        msg.direction = DIRECTION_RECEIVED;
        msg.timestamp = timestamp;
        msg.blocksJson = blocksJson;
        msg.status = "received";
        return msg;
    }

    public static ChatMessage sent(String sessionId, String myAid,
                                   String peerAid, String blocksJson) {
        ChatMessage msg = new ChatMessage();
        msg.messageId = UUID.randomUUID().toString();
        msg.sessionId = sessionId;
        msg.sender = myAid;
        msg.peerAid = peerAid;
        msg.direction = DIRECTION_SENT;
        msg.timestamp = System.currentTimeMillis();
        msg.blocksJson = blocksJson;
        msg.status = "sent";
        return msg;
    }
}
