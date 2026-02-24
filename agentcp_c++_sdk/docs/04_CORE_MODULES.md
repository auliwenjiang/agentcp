# Core Modules

## AgentCP
Responsibility:
- Entry point for creating and loading AIDs
- Holds global configuration (CA/AP base URLs, proxy, TLS policy)
- Creates AgentID instances
- Singleton pattern for global state management

### Class Definition
```cpp
class AgentCP {
public:
    static AgentCP& Instance();

    // Configuration
    Result SetBaseUrls(const std::string& ca_base, const std::string& ap_base);
    Result SetProxy(const ProxyConfig& config);
    Result SetTLSPolicy(const TLSConfig& config);
    Result SetStoragePath(const std::string& path);

    // AID Management
    Result CreateAID(const std::string& aid, const std::string& seed_password, AgentID** out);
    Result LoadAID(const std::string& aid, AgentID** out);
    Result DeleteAID(const std::string& aid);
    std::vector<std::string> ListAIDs();

    // Lifecycle
    Result Initialize();
    void Shutdown();

private:
    AgentCP();
    ~AgentCP();
    AgentCP(const AgentCP&) = delete;
    AgentCP& operator=(const AgentCP&) = delete;
};
```

### Error Codes
| Code | Description |
|------|-------------|
| ACP_OK | Success |
| ACP_INVALID_URL | Invalid base URL format |
| ACP_AID_EXISTS | AID already exists |
| ACP_AID_NOT_FOUND | AID not found |
| ACP_STORAGE_ERROR | Storage path error |
| ACP_INIT_FAILED | Initialization failed |

### Thread Safety
- All methods are thread-safe
- Internal mutex protects global state
- Can be called from multiple threads concurrently

## AgentID
Responsibility:
- Owns AID runtime state, handlers, and connection objects
- Online/offline lifecycle management
- Message send/receive and stream control
- Coordinates CAClient, AuthClient, HeartbeatClient, MessageClient

### Class Definition
```cpp
class AgentID {
public:
    // Lifecycle
    Result Online();
    void Offline();
    bool IsOnline() const;
    AgentState GetState() const;

    // Identity
    std::string GetAID() const;
    std::string GetPublicKey() const;
    std::string GetCertificate() const;

    // Managers
    SessionManager& Sessions();
    FileClient& Files();
    StreamClient& Streams();

    // Handlers
    void SetMessageHandler(MessageHandler handler);
    void SetErrorHandler(ErrorHandler handler);
    void SetMetricsHandler(MetricsHandler handler);
    void SetStateChangeHandler(StateChangeHandler handler);

    // Direct messaging
    Result SendMessage(const std::string& session_id, const std::vector<Block>& blocks);
    Result SendMessageWithInstruction(const std::string& session_id,
                                      const std::vector<Block>& blocks,
                                      const Instruction& instruction);

    // Stream
    Result CreateStream(const std::string& session_id,
                        const std::string& receiver,
                        const std::string& content_type,
                        Stream** out);

    // File
    Result UploadFile(const std::string& path, FileUploadCallback callback);
    Result DownloadFile(const std::string& url,
                        const std::string& output_path,
                        FileDownloadCallback callback);

private:
    friend class AgentCP;
    AgentID(const std::string& aid);
    ~AgentID();
};
```

### Agent States
```cpp
enum class AgentState {
    Offline,        // Not connected
    Connecting,     // AP auth in progress
    Authenticating, // HB/WS auth in progress
    Online,         // Fully connected
    Reconnecting,   // Lost connection, attempting reconnect
    Error           // Unrecoverable error
};
```

### Error Codes
| Code | Description |
|------|-------------|
| AID_OK | Success |
| AID_ALREADY_ONLINE | Already online |
| AID_NOT_ONLINE | Not online |
| AID_AUTH_FAILED | Authentication failed |
| AID_NETWORK_ERROR | Network error |
| AID_CERT_ERROR | Certificate error |

### Thread Safety
- Online/Offline are thread-safe but should be called from main thread
- Handlers are invoked on background threads
- SendMessage can be called from any thread

## CAClient
Responsibility:
- Generate ECDSA P-384 key and CSR
- Store key/cert/CSR to local path
- Request certificate from CA server
- Certificate renewal management

### Class Definition
```cpp
class CAClient {
public:
    Result EnsureCertificate(const std::string& aid);
    Result RenewCertificate(const std::string& aid);
    Result GetCertificateInfo(const std::string& aid, CertInfo* out);
    bool IsCertificateValid(const std::string& aid);

private:
    Result GenerateKeyPair(const std::string& aid);
    Result GenerateCSR(const std::string& aid);
    Result RequestCertFromCA(const std::string& aid, const std::string& csr);
};
```

### Error Codes
| Code | Description |
|------|-------------|
| CA_OK | Success |
| CA_KEY_GEN_FAILED | Key generation failed |
| CA_CSR_GEN_FAILED | CSR generation failed |
| CA_REQUEST_FAILED | CA request failed |
| CA_CERT_INVALID | Certificate invalid |

## AuthClient / ApClient
Responsibility:
- AP sign_in challenge-response flow
- Validate server certificate
- Retrieve heartbeat and message endpoints
- AP data endpoints for public/private metadata
- Token refresh management

### Class Definition
```cpp
class ApClient {
public:
    Result SignIn(const std::string& aid, std::string* signature_out);
    Result GetAccessPointConfig(const std::string& aid,
                                const std::string& signature,
                                ApConfig* config_out);
    Result GetAgentPublicData(const std::string& aid, std::string* data_out);
    Result PostAgentPrivateData(const std::string& aid,
                                const std::string& signature,
                                const std::string& data);
    Result RefreshSignature(const std::string& aid, std::string* signature_out);

private:
    Result SignInStep1(const std::string& aid, std::string* nonce_out);
    Result SignInStep2(const std::string& aid,
                       const std::string& nonce,
                       std::string* signature_out);
};
```

### Error Codes
| Code | Description |
|------|-------------|
| AP_OK | Success |
| AP_AUTH_FAILED | Authentication failed |
| AP_INVALID_SIGNATURE | Invalid signature |
| AP_TOKEN_EXPIRED | Token expired |
| AP_NETWORK_ERROR | Network error |

## HeartbeatClient
Responsibility:
- Authenticate to heartbeat server
- Send UDP heartbeats and receive invites
- Re-auth on NextBeat == 401
- Maintain connection liveness

### Class Definition
```cpp
class HeartbeatClient {
public:
    Result Start(const std::string& server_url,
                 const std::string& aid,
                 const std::string& signature);
    void Stop();
    bool IsRunning() const;

    void SetInviteHandler(InviteHandler handler);
    void SetHeartbeatErrorHandler(ErrorHandler handler);

private:
    Result HttpSignIn();
    void UdpHeartbeatLoop();
    void HandleInvite(const InviteMessage& invite);
};
```

### Error Codes
| Code | Description |
|------|-------------|
| HB_OK | Success |
| HB_AUTH_FAILED | Authentication failed |
| HB_NETWORK_ERROR | Network error |
| HB_TIMEOUT | Heartbeat timeout |
| HB_REAUTH_REQUIRED | Re-authentication required |

## MessageClient
Responsibility:
- WebSocket connect/disconnect
- Send JSON commands and route inbound messages
- Automatic reconnect with backoff
- Ping/pong keepalive

### Class Definition
```cpp
class MessageClient {
public:
    Result Connect(const std::string& ws_url,
                   const std::string& aid,
                   const std::string& signature);
    void Disconnect();
    bool IsConnected() const;

    Result SendCommand(const std::string& cmd,
                       const std::string& request_id,
                       const json& data);

    void SetMessageHandler(WsMessageHandler handler);
    void SetConnectionStateHandler(ConnectionStateHandler handler);
    void SetErrorHandler(ErrorHandler handler);

private:
    void OnWsMessage(const std::string& message);
    void OnWsError(const std::string& error);
    void OnWsClose();
    void ReconnectWithBackoff();
};
```

### Error Codes
| Code | Description |
|------|-------------|
| WS_OK | Success |
| WS_CONNECT_FAILED | Connection failed |
| WS_DISCONNECTED | Disconnected |
| WS_SEND_FAILED | Send failed |
| WS_TIMEOUT | Operation timeout |

## SessionManager / Session
Responsibility:
- Manage session lifecycle and membership
- Provide high-level methods for session actions
- Track active sessions and members

### Class Definition
```cpp
class SessionManager {
public:
    Result CreateSession(const std::vector<std::string>& members,
                         std::string* session_id_out);
    Result InviteAgent(const std::string& session_id, const std::string& agent_id);
    Result JoinSession(const std::string& session_id);
    Result LeaveSession(const std::string& session_id);
    Result CloseSession(const std::string& session_id);
    Result GetMemberList(const std::string& session_id,
                         std::vector<SessionMember>* members_out);

    Session* GetSession(const std::string& session_id);
    std::vector<std::string> GetActiveSessions();
};

class Session {
public:
    std::string GetSessionId() const;
    std::vector<SessionMember> GetMembers() const;

    Result SendMessage(const std::vector<Block>& blocks);
    Result SendMessageWithInstruction(const std::vector<Block>& blocks,
                                      const Instruction& instruction);
    Result CreateStream(const std::string& receiver,
                        const std::string& content_type,
                        Stream** out);
    Result SendFile(const std::string& file_path);
};
```

### Error Codes
| Code | Description |
|------|-------------|
| SESSION_OK | Success |
| SESSION_NOT_FOUND | Session not found |
| SESSION_NOT_MEMBER | Not a member |
| SESSION_PERMISSION_DENIED | Permission denied |
| SESSION_CLOSED | Session closed |

## StreamClient
Responsibility:
- Connect to stream push URL
- Send text or binary frames
- Manage stream close and error state
- Handle backpressure

### Class Definition
```cpp
class StreamClient {
public:
    Result Connect(const std::string& push_url);
    void Close();
    bool IsConnected() const;

    Result SendText(const std::string& chunk);
    Result SendBinary(const uint8_t* buffer, size_t size, size_t offset);

    void SetErrorHandler(ErrorHandler handler);
};
```

### Error Codes
| Code | Description |
|------|-------------|
| STREAM_OK | Success |
| STREAM_NOT_CONNECTED | Not connected |
| STREAM_SEND_FAILED | Send failed |
| STREAM_CLOSED | Stream closed |

## FileClient
Responsibility:
- Upload and download file via OSS server
- Support progress callbacks and retries
- Chunk-based upload for large files

### Class Definition
```cpp
class FileClient {
public:
    Result UploadFile(const std::string& path,
                      FileUploadCallback callback,
                      FileUploadResult* result_out);
    Result DownloadFile(const std::string& url,
                        const std::string& output_path,
                        FileDownloadCallback callback);

    void CancelUpload(const std::string& upload_id);
    void CancelDownload(const std::string& download_id);
};

// Callbacks
using FileUploadCallback = std::function<void(size_t bytes_sent, size_t total_bytes)>;
using FileDownloadCallback = std::function<void(size_t bytes_received, size_t total_bytes)>;
```

### Error Codes
| Code | Description |
|------|-------------|
| FILE_OK | Success |
| FILE_NOT_FOUND | File not found |
| FILE_TOO_LARGE | File too large |
| FILE_UPLOAD_FAILED | Upload failed |
| FILE_DOWNLOAD_FAILED | Download failed |

## DBManager
Responsibility:
- Provide SQLite storage for sessions and messages
- Schema migration and data integrity
- Query optimization

### Class Definition
```cpp
class DBManager {
public:
    Result InitSchema(const std::string& db_path);
    Result Migrate(int from_version, int to_version);

    Result SaveMessage(const Message& message);
    Result GetMessages(const std::string& session_id,
                       int limit,
                       int offset,
                       std::vector<Message>* messages_out);
    Result DeleteMessages(const std::string& session_id);

    Result SaveSession(const Session& session);
    Result GetSession(const std::string& session_id, Session* session_out);
    Result DeleteSession(const std::string& session_id);

    Result SaveFriend(const Friend& friend_info);
    Result GetFriend(const std::string& agent_id, Friend* friend_out);
    Result GetAllFriends(std::vector<Friend>* friends_out);
};
```

### Error Codes
| Code | Description |
|------|-------------|
| DB_OK | Success |
| DB_OPEN_FAILED | Database open failed |
| DB_QUERY_FAILED | Query failed |
| DB_MIGRATION_FAILED | Migration failed |
| DB_CONSTRAINT_VIOLATION | Constraint violation |

## Metrics / Monitoring
Responsibility:
- Collect throughput, latency, queue sizes
- Periodic snapshot for analytics
- Export metrics to app

### Class Definition
```cpp
class Metrics {
public:
    void RecordMessageLatency(uint64_t latency_ms);
    void RecordQueueSize(const std::string& queue_name, size_t size);
    void RecordReconnectCount();
    void RecordError(const std::string& subsystem, const std::string& error_code);

    MetricsSnapshot Snapshot();
    void Reset();

    void SetExportHandler(MetricsExportHandler handler);
};

struct MetricsSnapshot {
    uint64_t message_count;
    uint64_t avg_latency_ms;
    uint64_t max_latency_ms;
    uint64_t reconnect_count;
    std::map<std::string, uint64_t> error_counts;
    uint64_t timestamp;
};
```

## ErrorContext
Responsibility:
- Central error pipeline and dispatch to app callbacks
- Categorize errors by subsystem and severity
- Error logging and reporting

### Class Definition
```cpp
class ErrorContext {
public:
    void PublishError(const std::string& subsystem,
                      const std::string& code,
                      const std::string& message,
                      ErrorSeverity severity,
                      const json& context);

    void SetErrorHandler(ErrorHandler handler);
    void SetLogLevel(LogLevel level);
};

enum class ErrorSeverity {
    Info,       // Informational
    Warning,    // Recoverable issue
    Error,      // Operation failed
    Fatal       // Unrecoverable error
};

using ErrorHandler = std::function<void(const ErrorInfo& error)>;
```

## Module Dependencies

```
AgentCP
  └─> AgentID
       ├─> CAClient
       ├─> ApClient
       ├─> HeartbeatClient
       ├─> MessageClient
       │    └─> SessionManager
       │         └─> Session
       ├─> StreamClient
       ├─> FileClient
       ├─> DBManager
       ├─> Metrics
       └─> ErrorContext
```

### Initialization Order
1. AgentCP::Initialize()
2. AgentCP::SetBaseUrls()
3. AgentCP::LoadAID() or CreateAID()
4. AgentID::Online()
   - CAClient::EnsureCertificate()
   - ApClient::SignIn()
   - HeartbeatClient::Start()
   - MessageClient::Connect()

### Shutdown Order
1. AgentID::Offline()
   - MessageClient::Disconnect()
   - HeartbeatClient::Stop()
2. AgentCP::Shutdown()
