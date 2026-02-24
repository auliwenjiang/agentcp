package com.agentcp.store;

import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;

import java.io.File;
import java.util.ArrayList;
import java.util.List;

/**
 * SQLite-based group message store.
 * Follows the same pattern as P2P MessageStore but for group messages.
 * Mirrors Node SDK's GroupMessageStore (JSONL-based) but uses SQLite for Android.
 */
public class GroupMessageStore {

    private static final String DB_NAME = "agentcp_group_messages.db";
    private static final int DB_VERSION = 1;

    private final DbHelper dbHelper;

    public GroupMessageStore(Context context, String myAid, StorageConfig config) {
        if (context == null || myAid == null || config == null) {
            throw new MessageStoreException("context, myAid, and config must not be null");
        }
        this.dbHelper = new DbHelper(context, myAid, config);
    }

    // ===== Group conversation management =====

    /**
     * Get or create a group conversation record.
     * Mirrors Node SDK's GroupMessageStore.getOrCreateGroup().
     */
    public GroupConversation getOrCreateGroup(String groupId, String targetAid, String groupName) {
        SQLiteDatabase db = dbHelper.getWritableDatabase();
        Cursor c = db.rawQuery(
                "SELECT * FROM group_conversations WHERE group_id = ?",
                new String[]{groupId});
        try {
            if (c.moveToFirst()) {
                return cursorToConversation(c);
            }
        } finally {
            c.close();
        }

        // Create new
        ContentValues cv = new ContentValues();
        cv.put("group_id", groupId);
        cv.put("group_name", groupName != null ? groupName : groupId);
        cv.put("target_aid", targetAid != null ? targetAid : "");
        cv.put("last_msg_id", 0);
        cv.put("message_count", 0);
        cv.put("last_message_at", 0);
        cv.put("joined_at", System.currentTimeMillis());
        cv.put("unread_count", 0);
        db.insertWithOnConflict("group_conversations", null, cv, SQLiteDatabase.CONFLICT_IGNORE);

        GroupConversation conv = new GroupConversation();
        conv.groupId = groupId;
        conv.groupName = groupName != null ? groupName : groupId;
        conv.targetAid = targetAid != null ? targetAid : "";
        conv.lastMsgId = 0;
        conv.messageCount = 0;
        conv.lastMessageAt = 0;
        conv.joinedAt = System.currentTimeMillis();
        conv.unreadCount = 0;
        return conv;
    }

    /**
     * Get all group conversations sorted by last message time.
     */
    public List<GroupConversation> getGroupList() {
        SQLiteDatabase db = dbHelper.getReadableDatabase();
        Cursor c = db.rawQuery(
                "SELECT * FROM group_conversations ORDER BY last_message_at DESC", null);
        List<GroupConversation> list = new ArrayList<>();
        try {
            while (c.moveToNext()) {
                list.add(cursorToConversation(c));
            }
        } finally {
            c.close();
        }
        return list;
    }

    /**
     * Get a single group conversation.
     */
    public GroupConversation getGroup(String groupId) {
        SQLiteDatabase db = dbHelper.getReadableDatabase();
        Cursor c = db.rawQuery(
                "SELECT * FROM group_conversations WHERE group_id = ?",
                new String[]{groupId});
        try {
            if (c.moveToFirst()) {
                return cursorToConversation(c);
            }
            return null;
        } finally {
            c.close();
        }
    }

    /**
     * Delete a group and all its messages.
     */
    public void deleteGroup(String groupId) {
        SQLiteDatabase db = dbHelper.getWritableDatabase();
        db.beginTransaction();
        try {
            db.delete("group_messages", "group_id = ?", new String[]{groupId});
            db.delete("group_conversations", "group_id = ?", new String[]{groupId});
            db.setTransactionSuccessful();
        } finally {
            db.endTransaction();
        }
    }

    // ===== Message storage =====

    /**
     * Save a single group message. Deduplicates by msg_id.
     * Mirrors Node SDK's GroupMessageStore.addMessage().
     */
    public void saveMessage(GroupChatMessage msg) {
        if (msg == null) return;
        SQLiteDatabase db = dbHelper.getWritableDatabase();
        db.beginTransaction();
        try {
            insertMessage(db, msg);
            updateConversationOnMessage(db, msg);
            db.setTransactionSuccessful();
        } finally {
            db.endTransaction();
        }
    }

    /**
     * Save a batch of group messages. Deduplicates by msg_id.
     * Mirrors Node SDK's GroupMessageStore.addMessages().
     */
    public void saveMessages(String groupId, List<GroupChatMessage> msgs) {
        if (msgs == null || msgs.isEmpty()) return;
        SQLiteDatabase db = dbHelper.getWritableDatabase();
        db.beginTransaction();
        try {
            GroupChatMessage lastMsg = null;
            for (GroupChatMessage msg : msgs) {
                msg.groupId = groupId;
                insertMessage(db, msg);
                lastMsg = msg;
            }
            if (lastMsg != null) {
                updateConversationOnMessage(db, lastMsg);
            }
            db.setTransactionSuccessful();
        } finally {
            db.endTransaction();
        }
    }

    /**
     * Get messages for a group, ordered by msg_id descending (newest first).
     */
    public List<GroupChatMessage> getMessages(String groupId, int limit, int offset) {
        SQLiteDatabase db = dbHelper.getReadableDatabase();
        Cursor c = db.rawQuery(
                "SELECT * FROM group_messages WHERE group_id = ? ORDER BY msg_id DESC LIMIT ? OFFSET ?",
                new String[]{groupId, String.valueOf(limit), String.valueOf(offset)});
        return readMessages(c);
    }

    /**
     * Get the latest N messages for a group, returned in chronological order (oldest first).
     */
    public List<GroupChatMessage> getLatestMessages(String groupId, int limit) {
        SQLiteDatabase db = dbHelper.getReadableDatabase();
        // Sub-query gets latest N by descending, outer query reverses to ascending
        Cursor c = db.rawQuery(
                "SELECT * FROM (SELECT * FROM group_messages WHERE group_id = ? ORDER BY msg_id DESC LIMIT ?) ORDER BY msg_id ASC",
                new String[]{groupId, String.valueOf(limit)});
        return readMessages(c);
    }

    /**
     * Get messages after a specific msg_id (for incremental pull).
     */
    public List<GroupChatMessage> getMessagesAfter(String groupId, long afterMsgId, int limit) {
        SQLiteDatabase db = dbHelper.getReadableDatabase();
        Cursor c = db.rawQuery(
                "SELECT * FROM group_messages WHERE group_id = ? AND msg_id > ? ORDER BY msg_id ASC LIMIT ?",
                new String[]{groupId, String.valueOf(afterMsgId), String.valueOf(limit)});
        return readMessages(c);
    }

    /**
     * Get the last msg_id for a group (for incremental pull).
     * Mirrors Node SDK's getGroupLastMsgId().
     */
    public long getLastMsgId(String groupId) {
        GroupConversation conv = getGroup(groupId);
        return conv != null ? conv.lastMsgId : 0;
    }

    /**
     * Mark group as read (reset unread count).
     */
    public void markGroupRead(String groupId) {
        SQLiteDatabase db = dbHelper.getWritableDatabase();
        ContentValues cv = new ContentValues();
        cv.put("unread_count", 0);
        db.update("group_conversations", cv, "group_id = ?", new String[]{groupId});
    }

    // ===== Lifecycle =====

    public void close() {
        dbHelper.close();
    }

    // ===== Internal helpers =====

    private void insertMessage(SQLiteDatabase db, GroupChatMessage msg) {
        ContentValues cv = new ContentValues();
        cv.put("group_id", msg.groupId);
        cv.put("msg_id", msg.msgId);
        cv.put("sender", msg.sender);
        cv.put("content", msg.content);
        cv.put("content_type", msg.contentType);
        cv.put("timestamp", msg.timestamp);
        cv.put("metadata_json", msg.metadataJson);
        cv.put("created_at", System.currentTimeMillis());
        // IGNORE on conflict = dedup by (group_id, msg_id) unique index
        db.insertWithOnConflict("group_messages", null, cv, SQLiteDatabase.CONFLICT_IGNORE);
    }

    private void updateConversationOnMessage(SQLiteDatabase db, GroupChatMessage msg) {
        // Upsert conversation: update last_msg_id, message_count, unread_count
        Cursor c = db.rawQuery(
                "SELECT last_msg_id, unread_count FROM group_conversations WHERE group_id = ?",
                new String[]{msg.groupId});
        try {
            if (c.moveToFirst()) {
                long currentLastMsgId = c.getLong(0);
                int unread = c.getInt(1);
                if (msg.msgId > currentLastMsgId) {
                    ContentValues cv = new ContentValues();
                    cv.put("last_msg_id", msg.msgId);
                    cv.put("last_message_at", msg.timestamp > 0 ? msg.timestamp : System.currentTimeMillis());
                    cv.put("unread_count", unread + 1);
                    // Update message_count via subquery
                    db.update("group_conversations", cv, "group_id = ?", new String[]{msg.groupId});
                }
            }
        } finally {
            c.close();
        }
    }

    private List<GroupChatMessage> readMessages(Cursor c) {
        List<GroupChatMessage> list = new ArrayList<>();
        try {
            while (c.moveToNext()) {
                list.add(cursorToMessage(c));
            }
        } finally {
            c.close();
        }
        return list;
    }

    private GroupChatMessage cursorToMessage(Cursor c) {
        GroupChatMessage msg = new GroupChatMessage();
        msg.groupId = c.getString(c.getColumnIndexOrThrow("group_id"));
        msg.msgId = c.getLong(c.getColumnIndexOrThrow("msg_id"));
        msg.sender = c.getString(c.getColumnIndexOrThrow("sender"));
        msg.content = c.getString(c.getColumnIndexOrThrow("content"));
        msg.contentType = c.getString(c.getColumnIndexOrThrow("content_type"));
        msg.timestamp = c.getLong(c.getColumnIndexOrThrow("timestamp"));
        msg.metadataJson = c.getString(c.getColumnIndexOrThrow("metadata_json"));
        return msg;
    }

    private GroupConversation cursorToConversation(Cursor c) {
        GroupConversation conv = new GroupConversation();
        conv.groupId = c.getString(c.getColumnIndexOrThrow("group_id"));
        conv.groupName = c.getString(c.getColumnIndexOrThrow("group_name"));
        conv.targetAid = c.getString(c.getColumnIndexOrThrow("target_aid"));
        conv.lastMsgId = c.getLong(c.getColumnIndexOrThrow("last_msg_id"));
        conv.messageCount = c.getInt(c.getColumnIndexOrThrow("message_count"));
        conv.lastMessageAt = c.getLong(c.getColumnIndexOrThrow("last_message_at"));
        conv.joinedAt = c.getLong(c.getColumnIndexOrThrow("joined_at"));
        conv.unreadCount = c.getInt(c.getColumnIndexOrThrow("unread_count"));
        return conv;
    }

    // ===== Inner SQLite helper =====

    private static class DbHelper extends SQLiteOpenHelper {

        private static final String CREATE_MESSAGES_TABLE =
                "CREATE TABLE IF NOT EXISTS group_messages ("
                        + "group_id     TEXT NOT NULL,"
                        + "msg_id       INTEGER NOT NULL,"
                        + "sender       TEXT NOT NULL,"
                        + "content      TEXT NOT NULL,"
                        + "content_type TEXT DEFAULT 'text',"
                        + "timestamp    INTEGER NOT NULL,"
                        + "metadata_json TEXT,"
                        + "created_at   INTEGER NOT NULL,"
                        + "PRIMARY KEY (group_id, msg_id)"
                        + ")";

        private static final String CREATE_CONVERSATIONS_TABLE =
                "CREATE TABLE IF NOT EXISTS group_conversations ("
                        + "group_id        TEXT PRIMARY KEY,"
                        + "group_name      TEXT NOT NULL,"
                        + "target_aid      TEXT NOT NULL,"
                        + "last_msg_id     INTEGER DEFAULT 0,"
                        + "message_count   INTEGER DEFAULT 0,"
                        + "last_message_at INTEGER DEFAULT 0,"
                        + "joined_at       INTEGER NOT NULL,"
                        + "unread_count    INTEGER DEFAULT 0"
                        + ")";

        DbHelper(Context context, String myAid, StorageConfig config) {
            super(context, resolveDbPath(context, myAid, config), null, DB_VERSION);
        }

        @Override
        public void onCreate(SQLiteDatabase db) {
            db.execSQL(CREATE_MESSAGES_TABLE);
            db.execSQL("CREATE INDEX IF NOT EXISTS idx_gmsg_group_time ON group_messages(group_id, timestamp)");
            db.execSQL(CREATE_CONVERSATIONS_TABLE);
            db.execSQL("CREATE INDEX IF NOT EXISTS idx_gconv_time ON group_conversations(last_message_at DESC)");
        }

        @Override
        public void onUpgrade(SQLiteDatabase db, int oldVersion, int newVersion) {
            // Future schema migrations
        }

        private static String resolveDbPath(Context context, String myAid, StorageConfig config) {
            String safeName = myAid.replaceAll("[^a-zA-Z0-9._-]", "_");
            switch (config.getMode()) {
                case EXTERNAL:
                    File extDir = context.getExternalFilesDir("agentcp");
                    if (extDir != null) {
                        extDir.mkdirs();
                        return new File(extDir, safeName + "_" + DB_NAME).getAbsolutePath();
                    }
                    // fall through
                case INTERNAL:
                    return safeName + "_" + DB_NAME;
                case CUSTOM:
                    File customDir = new File(config.getCustomPath());
                    customDir.mkdirs();
                    return new File(customDir, safeName + "_" + DB_NAME).getAbsolutePath();
                default:
                    return safeName + "_" + DB_NAME;
            }
        }
    }
}
