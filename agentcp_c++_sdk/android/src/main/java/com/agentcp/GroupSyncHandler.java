package com.agentcp;

import org.json.JSONArray;

/**
 * Callback interface for group syncGroup flow.
 * Mirrors Node SDK's SyncHandler.
 */
public interface GroupSyncHandler {
    void onMessages(String groupId, JSONArray messages);
    void onEvents(String groupId, JSONArray events);
}

