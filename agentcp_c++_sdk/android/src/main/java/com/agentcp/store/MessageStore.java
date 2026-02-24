package com.agentcp.store;

import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;

import java.util.ArrayList;
import java.util.List;

public class MessageStore {

    private final MessageDbHelper dbHelper;
    private final String myAid;

    public MessageStore(Context context, String myAid, StorageConfig config) {
        if (context == null || myAid == null || config == null) {
            throw new MessageStoreException("context, myAid, and config must not be null");
        }
        if (!StoragePermissionHelper.hasPermission(context, config)) {
            throw new MessageStoreException(
                    "Storage permission not granted for mode: " + config.getMode());
        }
        this.myAid = myAid;
        this.dbHelper = new MessageDbHelper(context, myAid, config);
    }

    // ===== Write =====

    public void saveMessage(ChatMessage message) {
        if (message == null) {
            return;
        }
        if (message.sender == null && message.direction == ChatMessage.DIRECTION_SENT) {
            message.sender = myAid;
        }
        SQLiteDatabase db = dbHelper.getWritableDatabase();
        db.beginTransaction();
        try {
            insertMessage(db, message);
            upsertConversation(db, message);
            db.setTransactionSuccessful();
        } finally {
            db.endTransaction();
        }
    }

    public void updateMessageStatus(String messageId, String status) {
        SQLiteDatabase db = dbHelper.getWritableDatabase();
        ContentValues cv = new ContentValues();
        cv.put("status", status);
        db.update("messages", cv, "message_id = ?", new String[]{messageId});
    }

    // ===== Hierarchical queries =====

    public List<String> getPeerAids() {
        List<String> peers = new ArrayList<>();
        SQLiteDatabase db = dbHelper.getReadableDatabase();
        Cursor c = db.rawQuery(
                "SELECT DISTINCT peer_aid FROM conversations ORDER BY updated_at DESC", null);
        try {
            while (c.moveToNext()) {
                peers.add(c.getString(0));
            }
        } finally {
            c.close();
        }
        return peers;
    }

    public List<Conversation> getConversations(String peerAid) {
        SQLiteDatabase db = dbHelper.getReadableDatabase();
        Cursor c = db.rawQuery(
                "SELECT * FROM conversations WHERE peer_aid = ? ORDER BY updated_at DESC",
                new String[]{peerAid});
        return readConversations(c);
    }

    public List<ChatMessage> getMessages(String sessionId, int limit, int offset) {
        SQLiteDatabase db = dbHelper.getReadableDatabase();
        Cursor c = db.rawQuery(
                "SELECT * FROM messages WHERE session_id = ? AND is_deleted = 0 "
                        + "ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                new String[]{sessionId, String.valueOf(limit), String.valueOf(offset)});
        return readMessages(c);
    }

    // ===== Convenience queries =====

    public List<Conversation> getAllConversations() {
        SQLiteDatabase db = dbHelper.getReadableDatabase();
        Cursor c = db.rawQuery(
                "SELECT * FROM conversations ORDER BY updated_at DESC", null);
        return readConversations(c);
    }
    public ChatMessage getMessage(String messageId) {
        SQLiteDatabase db = dbHelper.getReadableDatabase();
        Cursor c = db.rawQuery(
                "SELECT * FROM messages WHERE message_id = ? AND is_deleted = 0",
                new String[]{messageId});
        try {
            if (c.moveToFirst()) {
                return cursorToMessage(c);
            }
            return null;
        } finally {
            c.close();
        }
    }

    public int getUnreadCount(String peerAid) {
        SQLiteDatabase db = dbHelper.getReadableDatabase();
        Cursor c = db.rawQuery(
                "SELECT SUM(unread_count) FROM conversations WHERE peer_aid = ?",
                new String[]{peerAid});
        try {
            if (c.moveToFirst()) {
                return c.getInt(0);
            }
            return 0;
        } finally {
            c.close();
        }
    }

    // ===== Update =====

    public void markSessionRead(String sessionId) {
        SQLiteDatabase db = dbHelper.getWritableDatabase();
        ContentValues cv = new ContentValues();
        cv.put("unread_count", 0);
        db.update("conversations", cv, "session_id = ?", new String[]{sessionId});
    }

    // ===== Delete =====

    public void deleteMessage(String messageId) {
        SQLiteDatabase db = dbHelper.getWritableDatabase();
        ContentValues cv = new ContentValues();
        cv.put("is_deleted", 1);
        db.update("messages", cv, "message_id = ?", new String[]{messageId});
    }

    public void clearSession(String sessionId) {
        SQLiteDatabase db = dbHelper.getWritableDatabase();
        db.beginTransaction();
        try {
            db.delete("messages", "session_id = ?", new String[]{sessionId});
            db.delete("conversations", "session_id = ?", new String[]{sessionId});
            db.setTransactionSuccessful();
        } finally {
            db.endTransaction();
        }
    }
    public void clearByPeer(String peerAid) {
        SQLiteDatabase db = dbHelper.getWritableDatabase();
        db.beginTransaction();
        try {
            db.delete("messages", "peer_aid = ?", new String[]{peerAid});
            db.delete("conversations", "peer_aid = ?", new String[]{peerAid});
            db.setTransactionSuccessful();
        } finally {
            db.endTransaction();
        }
    }

    public void clearAll() {
        SQLiteDatabase db = dbHelper.getWritableDatabase();
        db.beginTransaction();
        try {
            db.delete("messages", null, null);
            db.delete("conversations", null, null);
            db.setTransactionSuccessful();
        } finally {
            db.endTransaction();
        }
    }

    // ===== Lifecycle =====

    public void close() {
        dbHelper.close();
    }

    // ===== Internal helpers =====

    private void insertMessage(SQLiteDatabase db, ChatMessage msg) {
        ContentValues cv = new ContentValues();
        cv.put("message_id", msg.messageId);
        cv.put("session_id", msg.sessionId);
        cv.put("sender", msg.sender);
        cv.put("peer_aid", msg.peerAid);
        cv.put("direction", msg.direction);
        cv.put("timestamp", msg.timestamp);
        cv.put("blocks_json", msg.blocksJson);
        cv.put("status", msg.status);
        cv.put("is_deleted", 0);
        cv.put("created_at", System.currentTimeMillis());
        db.insertWithOnConflict("messages", null, cv, SQLiteDatabase.CONFLICT_REPLACE);
    }

    private void upsertConversation(SQLiteDatabase db, ChatMessage msg) {
        long now = System.currentTimeMillis();
        String preview = truncatePreview(msg.blocksJson, 100);

        ContentValues cv = new ContentValues();
        cv.put("session_id", msg.sessionId);
        cv.put("peer_aid", msg.peerAid);
        cv.put("last_msg_id", msg.messageId);
        cv.put("last_msg_time", msg.timestamp);
        cv.put("last_msg_preview", preview);
        cv.put("updated_at", now);
        // Check if conversation exists
        Cursor existing = db.rawQuery(
                "SELECT unread_count FROM conversations WHERE session_id = ?",
                new String[]{msg.sessionId});
        try {
            if (existing.moveToFirst()) {
                int unread = existing.getInt(0);
                if (msg.direction == ChatMessage.DIRECTION_RECEIVED) {
                    cv.put("unread_count", unread + 1);
                }
                db.update("conversations", cv, "session_id = ?",
                        new String[]{msg.sessionId});
            } else {
                cv.put("session_type", Conversation.TYPE_SINGLE);
                cv.put("unread_count", msg.direction == ChatMessage.DIRECTION_RECEIVED ? 1 : 0);
                db.insert("conversations", null, cv);
            }
        } finally {
            existing.close();
        }
    }

    private static String truncatePreview(String text, int maxLen) {
        if (text == null) {
            return "";
        }
        return text.length() <= maxLen ? text : text.substring(0, maxLen);
    }

    private List<ChatMessage> readMessages(Cursor c) {
        List<ChatMessage> list = new ArrayList<>();
        try {
            while (c.moveToNext()) {
                list.add(cursorToMessage(c));
            }
        } finally {
            c.close();
        }
        return list;
    }

    private ChatMessage cursorToMessage(Cursor c) {
        ChatMessage msg = new ChatMessage();
        msg.messageId = c.getString(c.getColumnIndexOrThrow("message_id"));
        msg.sessionId = c.getString(c.getColumnIndexOrThrow("session_id"));
        msg.sender = c.getString(c.getColumnIndexOrThrow("sender"));
        msg.peerAid = c.getString(c.getColumnIndexOrThrow("peer_aid"));
        msg.direction = c.getInt(c.getColumnIndexOrThrow("direction"));
        msg.timestamp = c.getLong(c.getColumnIndexOrThrow("timestamp"));
        msg.blocksJson = c.getString(c.getColumnIndexOrThrow("blocks_json"));
        msg.status = c.getString(c.getColumnIndexOrThrow("status"));
        return msg;
    }

    private List<Conversation> readConversations(Cursor c) {
        List<Conversation> list = new ArrayList<>();
        try {
            while (c.moveToNext()) {
                Conversation conv = new Conversation();
                conv.sessionId = c.getString(c.getColumnIndexOrThrow("session_id"));
                conv.peerAid = c.getString(c.getColumnIndexOrThrow("peer_aid"));
                conv.sessionType = c.getInt(c.getColumnIndexOrThrow("session_type"));
                conv.lastMsgId = c.getString(c.getColumnIndexOrThrow("last_msg_id"));
                conv.lastMsgTime = c.getLong(c.getColumnIndexOrThrow("last_msg_time"));
                conv.lastMsgPreview = c.getString(c.getColumnIndexOrThrow("last_msg_preview"));
                conv.unreadCount = c.getInt(c.getColumnIndexOrThrow("unread_count"));
                list.add(conv);
            }
        } finally {
            c.close();
        }
        return list;
    }
}
