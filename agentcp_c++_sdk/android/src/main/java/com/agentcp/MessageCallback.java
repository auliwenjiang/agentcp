package com.agentcp;

public interface MessageCallback {
    void onMessage(String messageId, String sessionId, String sender, long timestamp, String blocksJson);
}
