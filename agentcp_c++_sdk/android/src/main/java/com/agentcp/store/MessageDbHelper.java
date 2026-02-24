package com.agentcp.store;

import android.content.Context;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;

import java.io.File;

class MessageDbHelper extends SQLiteOpenHelper {

    private static final String DB_NAME = "agentcp_messages.db";
    private static final int DB_VERSION = 1;

    private static final String CREATE_MESSAGES_TABLE =
            "CREATE TABLE IF NOT EXISTS messages ("
                    + "message_id  TEXT PRIMARY KEY,"
                    + "session_id  TEXT NOT NULL,"
                    + "sender      TEXT NOT NULL,"
                    + "peer_aid    TEXT NOT NULL,"
                    + "direction   INTEGER NOT NULL,"
                    + "timestamp   INTEGER NOT NULL,"
                    + "blocks_json TEXT NOT NULL,"
                    + "status      TEXT DEFAULT 'received',"
                    + "is_deleted  INTEGER DEFAULT 0,"
                    + "created_at  INTEGER NOT NULL"
                    + ")";

    private static final String CREATE_CONVERSATIONS_TABLE =
            "CREATE TABLE IF NOT EXISTS conversations ("
                    + "session_id       TEXT PRIMARY KEY,"
                    + "peer_aid         TEXT NOT NULL,"
                    + "session_type     INTEGER DEFAULT 0,"
                    + "last_msg_id      TEXT,"
                    + "last_msg_time    INTEGER,"
                    + "last_msg_preview TEXT,"
                    + "unread_count     INTEGER DEFAULT 0,"
                    + "updated_at       INTEGER NOT NULL"
                    + ")";

    MessageDbHelper(Context context, String myAid, StorageConfig config) {
        super(context, resolveDbPath(context, myAid, config), null, DB_VERSION);
    }

    @Override
    public void onCreate(SQLiteDatabase db) {
        db.execSQL(CREATE_MESSAGES_TABLE);
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_msg_peer ON messages(peer_aid)");
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_msg_session ON messages(session_id, timestamp)");
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_msg_peer_sess ON messages(peer_aid, session_id, timestamp)");

        db.execSQL(CREATE_CONVERSATIONS_TABLE);
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_conv_peer ON conversations(peer_aid)");
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_conv_time ON conversations(updated_at DESC)");
    }

    @Override
    public void onUpgrade(SQLiteDatabase db, int oldVersion, int newVersion) {
        // Future schema migrations go here
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
                // fall through to internal if external unavailable
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
