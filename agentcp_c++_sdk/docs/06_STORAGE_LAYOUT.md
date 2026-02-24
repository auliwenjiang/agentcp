# Storage Layout

## Directory Structure
```
{storage_root}/
├── AIDs/
│   └── {aid}/
│       ├── public/
│       │   ├── profile.json
│       │   └── avatar.png
│       └── private/
│           ├── db.sqlite
│           ├── db.sqlite-wal
│           ├── db.sqlite-shm
│           ├── proxy_config.json
│           └── certs/
│               ├── {aid}.key      # ECDSA P-384 private key
│               ├── {aid}.crt      # Certificate
│               └── {aid}.csr      # Certificate signing request
├── cache/
│   └── files/
│       └── {file_hash}/
│           └── {filename}
├── backup/
│   ├── metrics.json
│   └── metrics_timeseries.db
└── logs/
    └── sdk.log
```

## SQLite Schema

### Complete Schema Definition
```sql
-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at INTEGER NOT NULL,
    description TEXT
);

-- Sessions table
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    member_count INTEGER DEFAULT 0,
    last_msg_id TEXT,
    last_msg_time INTEGER,
    is_closed INTEGER DEFAULT 0,
    metadata TEXT  -- JSON for extensibility
);

CREATE INDEX idx_sessions_updated ON sessions(updated_at DESC);
CREATE INDEX idx_sessions_last_msg ON sessions(last_msg_time DESC);

-- Session members table
CREATE TABLE IF NOT EXISTS session_members (
    session_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',  -- owner, admin, member
    joined_at INTEGER NOT NULL,
    PRIMARY KEY (session_id, agent_id),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX idx_members_agent ON session_members(agent_id);

-- Messages table
CREATE TABLE IF NOT EXISTS messages (
    message_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    sender TEXT NOT NULL,
    receiver TEXT,  -- comma-separated AIDs or NULL for broadcast
    ref_msg_id TEXT,
    timestamp INTEGER NOT NULL,
    content TEXT NOT NULL,  -- JSON array of blocks
    instruction TEXT,  -- JSON instruction block
    status TEXT DEFAULT 'received',  -- sent, received, read, failed
    is_deleted INTEGER DEFAULT 0,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX idx_messages_session ON messages(session_id, timestamp DESC);
CREATE INDEX idx_messages_sender ON messages(sender, timestamp DESC);
CREATE INDEX idx_messages_timestamp ON messages(timestamp DESC);

-- Friends/Contacts table
CREATE TABLE IF NOT EXISTS friends (
    agent_id TEXT PRIMARY KEY,
    alias TEXT,
    public_data TEXT,  -- JSON
    avatar_url TEXT,
    added_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    is_blocked INTEGER DEFAULT 0
);

CREATE INDEX idx_friends_alias ON friends(alias);

-- Configuration table
CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at INTEGER NOT NULL
);

-- File cache metadata
CREATE TABLE IF NOT EXISTS file_cache (
    file_id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    local_path TEXT NOT NULL,
    file_name TEXT,
    file_size INTEGER,
    mime_type TEXT,
    md5 TEXT,
    cached_at INTEGER NOT NULL,
    last_accessed INTEGER NOT NULL,
    expires_at INTEGER
);

CREATE INDEX idx_file_cache_accessed ON file_cache(last_accessed);
CREATE INDEX idx_file_cache_url ON file_cache(url);

-- Pending messages (offline queue)
CREATE TABLE IF NOT EXISTS pending_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    content TEXT NOT NULL,  -- JSON
    created_at INTEGER NOT NULL,
    retry_count INTEGER DEFAULT 0,
    last_retry INTEGER
);

CREATE INDEX idx_pending_created ON pending_messages(created_at);
```

### Data Types
| SQLite Type | Usage | Notes |
|-------------|-------|-------|
| TEXT | Strings, JSON, UUIDs | UTF-8 encoded |
| INTEGER | Timestamps, counts, booleans | Unix milliseconds for time |
| REAL | Not used | Avoid floating point |
| BLOB | Not used | Files stored externally |

## Storage Policy

### Message Retention
```cpp
struct RetentionPolicy {
    enum class Mode { Time, Count, Size };

    Mode mode = Mode::Time;
    int64_t max_age_days = 90;      // For Time mode
    int64_t max_count = 100000;     // For Count mode
    int64_t max_size_mb = 500;      // For Size mode
    bool keep_starred = true;       // Never delete starred messages
};

// Cleanup query examples
// Time-based
DELETE FROM messages
WHERE timestamp < ? AND is_deleted = 0 AND message_id NOT IN (
    SELECT message_id FROM starred_messages
);

// Count-based (keep newest N per session)
DELETE FROM messages WHERE message_id IN (
    SELECT message_id FROM (
        SELECT message_id, ROW_NUMBER() OVER (
            PARTITION BY session_id ORDER BY timestamp DESC
        ) as rn FROM messages
    ) WHERE rn > ?
);
```

### File Cache
```cpp
struct CachePolicy {
    int64_t max_size_mb = 1024;     // 1GB default
    int64_t max_age_days = 30;
    bool lru_cleanup = true;
    std::vector<std::string> keep_types = {"image/*", "audio/*"};
};

// LRU cleanup
void CleanupCache(int64_t target_size_bytes) {
    // 1. Delete expired files
    DELETE FROM file_cache WHERE expires_at < ?;

    // 2. Delete by LRU until under target size
    while (GetCacheSize() > target_size_bytes) {
        auto oldest = SELECT * FROM file_cache
                      ORDER BY last_accessed LIMIT 1;
        DeleteFile(oldest.local_path);
        DELETE FROM file_cache WHERE file_id = oldest.file_id;
    }
}
```

### Backup Strategy
```cpp
struct BackupConfig {
    bool enabled = true;
    int64_t interval_hours = 24;
    int64_t keep_count = 7;
    std::string backup_path;
    bool include_messages = true;
    bool include_files = false;
};

// Backup procedure
void PerformBackup() {
    // 1. Checkpoint WAL
    sqlite3_wal_checkpoint_v2(db, NULL, SQLITE_CHECKPOINT_TRUNCATE, ...);

    // 2. Copy database file
    std::filesystem::copy(db_path, backup_path / timestamp_filename);

    // 3. Export metrics
    ExportMetricsToJson(backup_path / "metrics.json");

    // 4. Cleanup old backups
    CleanupOldBackups(keep_count);
}
```

## Migration

### Version Management
```cpp
const int CURRENT_SCHEMA_VERSION = 3;

struct Migration {
    int from_version;
    int to_version;
    std::string sql;
    std::string description;
};

std::vector<Migration> migrations = {
    {0, 1, R"(
        -- Initial schema
        CREATE TABLE sessions (...);
        CREATE TABLE messages (...);
    )", "Initial schema"},

    {1, 2, R"(
        -- Add file cache
        CREATE TABLE file_cache (...);
        ALTER TABLE messages ADD COLUMN is_deleted INTEGER DEFAULT 0;
    )", "Add file cache and soft delete"},

    {2, 3, R"(
        -- Add pending messages
        CREATE TABLE pending_messages (...);
        CREATE INDEX idx_messages_status ON messages(status);
    )", "Add offline queue"},
};

Result RunMigrations() {
    int current = GetSchemaVersion();
    for (const auto& m : migrations) {
        if (m.from_version == current) {
            BeginTransaction();
            ExecuteSQL(m.sql);
            SetSchemaVersion(m.to_version);
            CommitTransaction();
            current = m.to_version;
        }
    }
    return Result::OK();
}
```

## Encryption at Rest

### SQLCipher Integration (Optional)
```cpp
// Open encrypted database
sqlite3_key(db, password.data(), password.size());

// Or use SQLCipher pragma
PRAGMA key = 'user-password';
PRAGMA cipher_page_size = 4096;
PRAGMA kdf_iter = 256000;
PRAGMA cipher_hmac_algorithm = HMAC_SHA512;
PRAGMA cipher_kdf_algorithm = PBKDF2_HMAC_SHA512;
```

### Key Derivation
```cpp
// Derive encryption key from user password
std::vector<uint8_t> DeriveKey(const std::string& password,
                                const std::string& aid) {
    // Use PBKDF2 with AID as salt
    return PBKDF2_SHA256(password, aid, 100000, 32);
}
```

## Platform-Specific Paths

### Android
```
/data/data/{package}/files/agentcp/
├── AIDs/
├── cache/
└── ...
```

### iOS
```
{Documents}/agentcp/
├── AIDs/
├── cache/  (in Caches directory)
└── ...
```

### Path Resolution
```cpp
std::string GetStoragePath(Platform platform) {
    switch (platform) {
        case Platform::Android:
            return GetAndroidFilesDir() + "/agentcp";
        case Platform::iOS:
            return GetDocumentsDir() + "/agentcp";
        default:
            return "./agentcp";
    }
}
```
