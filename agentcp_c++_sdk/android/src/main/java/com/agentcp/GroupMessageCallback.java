package com.agentcp;

/**
 * Callback interface for group message batch push events (message_batch_push from group.ap).
 * Replaces the old single-message onGroupMessage callback.
 */
public interface GroupMessageCallback {
    /**
     * Called when a batch of group messages is received (pushed from group.ap).
     *
     * @param groupId   The group ID
     * @param batchJson JSON string containing the batch:
     *                  {
     *                    "messages": [{msg_id, sender, content, content_type, timestamp, metadata}, ...],
     *                    "start_msg_id": number,
     *                    "latest_msg_id": number,
     *                    "count": number
     *                  }
     */
    void onGroupMessageBatch(String groupId, String batchJson);
}
