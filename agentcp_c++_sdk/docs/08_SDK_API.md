# SDK API Design

## Type Definitions

### Result Type
```cpp
struct Result {
    int code;
    std::string message;
    std::string context;

    bool ok() const { return code == 0; }
    operator bool() const { return ok(); }
};

// Usage
Result r = aid.Online();
if (!r) {
    std::cerr << "Error: " << r.message << std::endl;
}
```

### Configuration Types
```cpp
struct ProxyConfig {
    enum class Type { None, Http, Socks5, System };

    Type type = Type::None;
    std::string host;
    uint16_t port = 0;
    std::string username;
    std::string password;
    std::vector<std::string> bypass_list;
};

struct TLSConfig {
    bool verify = true;
    bool allow_self_signed = false;
    std::string ca_cert_path;
    std::string client_cert_path;
    std::string client_key_path;
    std::vector<std::string> pinned_certs;  // SHA256 fingerprints
};

struct ApConfig {
    std::string heartbeat_server;
    std::string message_server;
};
```

### Message Block Types
```cpp
enum class BlockType {
    Content,
    File,
    Image,
    Audio,
    Video,
    Form,
    FormResult,
    Instruction
};

enum class BlockStatus {
    Pending,
    Sent,
    Delivered,
    Failed
};

struct Block {
    BlockType type;
    BlockStatus status;
    uint64_t timestamp;

    // Factory methods
    static Block Text(const std::string& content);
    static Block File(const FileContent& file);
    static Block Image(const ImageContent& image);
    static Block Audio(const AudioContent& audio);
    static Block Video(const VideoContent& video);
    static Block Form(const FormContent& form);
    static Block FormResult(const FormResultContent& result);
};

struct FileContent {
    std::string url;
    std::string file_name;
    size_t file_size;
    std::string mime_type;
    std::string md5;
};

struct ImageContent {
    std::string url;
    std::string thumbnail_url;
    int width;
    int height;
    size_t file_size;
};

struct AudioContent {
    std::string url;
    int duration;  // seconds
    size_t file_size;
    std::string mime_type;
};

struct VideoContent {
    std::string url;
    std::string thumbnail_url;
    int duration;  // seconds
    int width;
    int height;
    size_t file_size;
    std::string mime_type;
};

struct FormField {
    std::string field_id;
    std::string label;
    std::string type;  // text, number, select, checkbox
    bool required;
    std::vector<std::string> options;  // for select type
};

struct FormContent {
    std::string form_id;
    std::string title;
    std::string description;
    std::vector<FormField> fields;
};

struct FormResultContent {
    std::string form_id;
    std::map<std::string, std::string> results;
};

struct Instruction {
    std::string cmd;
    std::map<std::string, std::string> params;
    std::string description;
    std::string model;
};
```

### Message Types
```cpp
struct Message {
    std::string message_id;
    std::string session_id;
    std::string sender;
    std::string receiver;
    std::string ref_msg_id;
    uint64_t timestamp;
    std::vector<Block> blocks;
    std::optional<Instruction> instruction;
};

struct SessionMember {
    std::string agent_id;
    std::string role;  // owner, admin, member
    uint64_t joined_at;
};

struct SessionInfo {
    std::string session_id;
    std::vector<SessionMember> members;
    uint64_t created_at;
    uint64_t updated_at;
    std::string last_msg_id;
};
```

### Callback Types
```cpp
// Message handler - called when message received
using MessageHandler = std::function<void(const Message& message)>;

// Error handler - called on errors
struct ErrorInfo {
    std::string subsystem;
    std::string code;
    std::string message;
    ErrorSeverity severity;
    std::map<std::string, std::string> context;
    uint64_t timestamp;
};
using ErrorHandler = std::function<void(const ErrorInfo& error)>;

// State change handler
using StateChangeHandler = std::function<void(AgentState old_state, AgentState new_state)>;

// Metrics handler
using MetricsHandler = std::function<void(const MetricsSnapshot& snapshot)>;

// File progress callbacks
using FileUploadCallback = std::function<void(size_t bytes_sent, size_t total_bytes)>;
using FileDownloadCallback = std::function<void(size_t bytes_received, size_t total_bytes)>;

// Invite handler
using InviteHandler = std::function<void(const std::string& session_id,
                                          const std::string& inviter_id)>;
```

## Core C++ API

### AgentCP
```cpp
class AgentCP {
public:
    static AgentCP& Instance();

    // Configuration
    Result SetBaseUrls(const std::string& ca_base, const std::string& ap_base);
    Result SetProxy(const ProxyConfig& config);
    Result SetTLSPolicy(const TLSConfig& config);
    Result SetStoragePath(const std::string& path);
    Result SetLogLevel(LogLevel level);

    // AID Management
    Result CreateAID(const std::string& aid,
                     const std::string& seed_password,
                     AgentID** out);
    Result LoadAID(const std::string& aid, AgentID** out);
    Result DeleteAID(const std::string& aid);
    std::vector<std::string> ListAIDs();

    // Lifecycle
    Result Initialize();
    void Shutdown();

    // Version info
    static std::string GetVersion();
    static std::string GetBuildInfo();
};
```

### AgentID
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

    // Handlers
    void SetMessageHandler(MessageHandler handler);
    void SetErrorHandler(ErrorHandler handler);
    void SetMetricsHandler(MetricsHandler handler);
    void SetStateChangeHandler(StateChangeHandler handler);
    void SetInviteHandler(InviteHandler handler);

    // Messaging
    Result SendMessage(const std::string& session_id,
                       const std::vector<Block>& blocks);
    Result SendMessageWithInstruction(const std::string& session_id,
                                      const std::vector<Block>& blocks,
                                      const Instruction& instruction);

    // Stream
    Result CreateStream(const std::string& session_id,
                        const std::string& receiver,
                        const std::string& content_type,
                        Stream** out);

    // File
    Result UploadFile(const std::string& path,
                      FileUploadCallback callback,
                      std::string* url_out);
    Result DownloadFile(const std::string& url,
                        const std::string& output_path,
                        FileDownloadCallback callback);
};
```

### SessionManager
```cpp
class SessionManager {
public:
    Result CreateSession(const std::vector<std::string>& members,
                         std::string* session_id_out);
    Result InviteAgent(const std::string& session_id,
                       const std::string& agent_id);
    Result JoinSession(const std::string& session_id);
    Result LeaveSession(const std::string& session_id);
    Result CloseSession(const std::string& session_id);
    Result GetMemberList(const std::string& session_id,
                         std::vector<SessionMember>* members_out);
    Result EjectAgent(const std::string& session_id,
                      const std::string& agent_id);

    Session* GetSession(const std::string& session_id);
    std::vector<std::string> GetActiveSessions();
    Result GetSessionInfo(const std::string& session_id, SessionInfo* info_out);
};
```

### Session
```cpp
class Session {
public:
    std::string GetSessionId() const;
    std::vector<SessionMember> GetMembers() const;
    bool IsMember(const std::string& agent_id) const;

    Result SendMessage(const std::vector<Block>& blocks);
    Result SendMessageWithInstruction(const std::vector<Block>& blocks,
                                      const Instruction& instruction);
    Result CreateStream(const std::string& receiver,
                        const std::string& content_type,
                        Stream** out);
    Result SendFile(const std::string& file_path,
                    FileUploadCallback callback);

    // History
    Result GetMessages(int limit, int offset,
                       std::vector<Message>* messages_out);
};
```

### Stream
```cpp
class Stream {
public:
    std::string GetStreamId() const;
    bool IsConnected() const;

    Result SendText(const std::string& chunk);
    Result SendBinary(const uint8_t* buffer, size_t size);
    void Close();

    void SetErrorHandler(ErrorHandler handler);
};
```

## Error Model

### Error Code Ranges
```cpp
// Error code ranges by subsystem
enum ErrorCodeRange {
    // General: 0-999
    OK = 0,
    UNKNOWN_ERROR = 1,
    INVALID_ARGUMENT = 2,
    NOT_INITIALIZED = 3,

    // Auth/AP: 1000-1999
    AUTH_FAILED = 1000,
    INVALID_SIGNATURE = 1001,
    TOKEN_EXPIRED = 1002,
    CERT_ERROR = 1003,

    // Heartbeat: 2000-2999
    HB_AUTH_FAILED = 2000,
    HB_TIMEOUT = 2001,
    HB_REAUTH_REQUIRED = 2002,

    // WebSocket: 3000-3999
    WS_CONNECT_FAILED = 3000,
    WS_DISCONNECTED = 3001,
    WS_SEND_FAILED = 3002,
    WS_TIMEOUT = 3003,

    // Session: 4000-4999
    SESSION_NOT_FOUND = 4000,
    SESSION_NOT_MEMBER = 4001,
    SESSION_PERMISSION_DENIED = 4002,
    SESSION_CLOSED = 4003,

    // Stream: 5000-5999
    STREAM_NOT_CONNECTED = 5000,
    STREAM_SEND_FAILED = 5001,
    STREAM_CLOSED = 5002,

    // File: 6000-6999
    FILE_NOT_FOUND = 6000,
    FILE_TOO_LARGE = 6001,
    FILE_UPLOAD_FAILED = 6002,
    FILE_DOWNLOAD_FAILED = 6003,

    // Database: 7000-7999
    DB_OPEN_FAILED = 7000,
    DB_QUERY_FAILED = 7001,
    DB_MIGRATION_FAILED = 7002,

    // Network: 8000-8999
    NETWORK_ERROR = 8000,
    NETWORK_TIMEOUT = 8001,
    DNS_FAILED = 8002,
    TLS_ERROR = 8003,
};
```

## Thread Safety Annotations

```cpp
// Thread safety markers (documentation only)
#define ACP_THREAD_SAFE      // Can be called from any thread
#define ACP_MAIN_THREAD      // Should be called from main thread
#define ACP_CALLBACK_THREAD  // Called on background thread

class AgentID {
public:
    ACP_THREAD_SAFE Result Online();
    ACP_THREAD_SAFE void Offline();
    ACP_THREAD_SAFE bool IsOnline() const;

    ACP_THREAD_SAFE Result SendMessage(...);

    // Handlers are invoked on callback thread
    ACP_MAIN_THREAD void SetMessageHandler(MessageHandler handler);
};
```

## Memory Ownership

```cpp
// Ownership rules:
// 1. AgentCP owns AgentID instances - do not delete manually
// 2. AgentID owns Session instances - do not delete manually
// 3. Caller owns Stream instances - must call Close() when done
// 4. Callback data is valid only during callback execution
// 5. String outputs are copied - caller owns the copy

// Example:
AgentID* aid = nullptr;
Result r = AgentCP::Instance().LoadAID("alice.ap.example.com", &aid);
// aid is owned by AgentCP, do not delete

Stream* stream = nullptr;
r = aid->CreateStream(session_id, receiver, "text/plain", &stream);
// stream is owned by caller
stream->SendText("hello");
stream->Close();
delete stream;  // caller must delete
```

## Example Usage

### Complete Login Flow
```cpp
#include "agentcp.h"

int main() {
    // Initialize SDK
    AgentCP& acp = AgentCP::Instance();
    acp.Initialize();
    acp.SetBaseUrls("https://ca.example.com", "https://ap.example.com");

    // Optional: Configure proxy
    ProxyConfig proxy;
    proxy.type = ProxyConfig::Type::Http;
    proxy.host = "proxy.example.com";
    proxy.port = 8080;
    acp.SetProxy(proxy);

    // Load or create AID
    AgentID* aid = nullptr;
    Result r = acp.LoadAID("alice.ap.example.com", &aid);
    if (!r) {
        r = acp.CreateAID("alice.ap.example.com", "password123", &aid);
        if (!r) {
            std::cerr << "Failed to create AID: " << r.message << std::endl;
            return 1;
        }
    }

    // Set handlers
    aid->SetMessageHandler([](const Message& msg) {
        std::cout << "Message from " << msg.sender << std::endl;
    });

    aid->SetErrorHandler([](const ErrorInfo& err) {
        std::cerr << "Error [" << err.subsystem << "]: " << err.message << std::endl;
    });

    aid->SetStateChangeHandler([](AgentState old_state, AgentState new_state) {
        std::cout << "State changed: " << (int)old_state << " -> " << (int)new_state << std::endl;
    });

    // Go online
    r = aid->Online();
    if (!r) {
        std::cerr << "Failed to go online: " << r.message << std::endl;
        return 1;
    }

    std::cout << "Online!" << std::endl;

    // ... application logic ...

    // Cleanup
    aid->Offline();
    acp.Shutdown();
    return 0;
}
```

### Message Send/Receive
```cpp
// Send text message
std::vector<Block> blocks;
blocks.push_back(Block::Text("Hello, world!"));

Result r = aid->SendMessage(session_id, blocks);
if (!r) {
    std::cerr << "Send failed: " << r.message << std::endl;
}

// Send message with instruction
Instruction inst;
inst.cmd = "translate";
inst.params["target_lang"] = "zh";
inst.description = "Translate to Chinese";

r = aid->SendMessageWithInstruction(session_id, blocks, inst);

// Receive messages via handler
aid->SetMessageHandler([](const Message& msg) {
    for (const auto& block : msg.blocks) {
        switch (block.type) {
            case BlockType::Content:
                std::cout << "Text: " << block.text_content << std::endl;
                break;
            case BlockType::Image:
                std::cout << "Image: " << block.image.url << std::endl;
                break;
            // ... handle other types
        }
    }
});
```

### File Transfer
```cpp
// Upload file
std::string url;
Result r = aid->UploadFile("/path/to/file.pdf",
    [](size_t sent, size_t total) {
        std::cout << "Upload progress: " << sent << "/" << total << std::endl;
    },
    &url);

if (r) {
    std::cout << "Uploaded to: " << url << std::endl;

    // Send file in message
    FileContent file;
    file.url = url;
    file.file_name = "file.pdf";
    file.file_size = 1024000;
    file.mime_type = "application/pdf";

    std::vector<Block> blocks;
    blocks.push_back(Block::File(file));
    aid->SendMessage(session_id, blocks);
}

// Download file
r = aid->DownloadFile(url, "/path/to/output.pdf",
    [](size_t received, size_t total) {
        std::cout << "Download progress: " << received << "/" << total << std::endl;
    });
```

### Stream Push
```cpp
// Create text stream
Stream* stream = nullptr;
Result r = aid->CreateStream(session_id, receiver, "text/plain", &stream);
if (!r) {
    std::cerr << "Failed to create stream: " << r.message << std::endl;
    return;
}

// Push text chunks
stream->SendText("Hello ");
stream->SendText("world!");
stream->SendText(" This is streaming.");

// Close stream
stream->Close();
delete stream;
```

### Session Management
```cpp
SessionManager& sm = aid->Sessions();

// Create session with members
std::string session_id;
Result r = sm.CreateSession({"bob.ap.example.com", "carol.ap.example.com"}, &session_id);

// Invite more members
r = sm.InviteAgent(session_id, "dave.ap.example.com");

// Get member list
std::vector<SessionMember> members;
r = sm.GetMemberList(session_id, &members);
for (const auto& m : members) {
    std::cout << m.agent_id << " (" << m.role << ")" << std::endl;
}

// Leave session
r = sm.LeaveSession(session_id);

// Close session (owner only)
r = sm.CloseSession(session_id);
```

## API Versioning

### Version Format
```
MAJOR.MINOR.PATCH
```

- MAJOR: Breaking API changes
- MINOR: New features, backward compatible
- PATCH: Bug fixes

### Compatibility Policy
- Minor version updates are backward compatible
- Deprecated APIs marked with `[[deprecated]]`
- Deprecated APIs removed after 2 major versions
- Binary compatibility maintained within major version

### Version Check
```cpp
// Runtime version check
std::string version = AgentCP::GetVersion();  // e.g., "1.2.3"
std::string build = AgentCP::GetBuildInfo();  // e.g., "2024-01-15 abc123"

// Compile-time version
#if ACP_VERSION >= ACP_MAKE_VERSION(1, 2, 0)
    // Use new API
#endif
```
