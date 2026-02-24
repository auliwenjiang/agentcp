#pragma once

#include <cstdint>
#include <memory>
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>

#include "agentcp/export.h"
#include "agentcp/types.h"
#include "agentcp/version.h"
#include "agentcp/group_types.h"
#include "agentcp/group_client.h"
#include "agentcp/group_events.h"
#include "agentcp/group_operations.h"
#include "agentcp/cursor_store.h"

namespace agentcp {

class SessionManager;
class Session;
class Stream;
class FileClient;

namespace client {
class AuthClient;
class HeartbeatClient;
class MessageClient;
class StreamClientImpl;
}  // namespace client

class ACP_API AgentCP {
public:
    static AgentCP& Instance();

    Result SetBaseUrls(const std::string& ca_base, const std::string& ap_base);
    Result SetProxy(const ProxyConfig& config);
    Result SetTLSPolicy(const TLSConfig& config);
    Result SetStoragePath(const std::string& path);
    Result SetLogLevel(LogLevel level);

    Result CreateAID(const std::string& aid, const std::string& seed_password, class AgentID** out);
    Result LoadAID(const std::string& aid, const std::string& seed_password, class AgentID** out);
    Result DeleteAID(const std::string& aid);
    std::vector<std::string> ListAIDs();

    Result Initialize();
    void Shutdown();

    static std::string GetVersion();
    static std::string GetBuildInfo();

    bool IsInitialized() const;

    std::string GetAPBase() const;
    std::string GetCABase() const;
    std::string GetStoragePath() const;

private:
    AgentCP();
    ~AgentCP();
    AgentCP(const AgentCP&) = delete;
    AgentCP& operator=(const AgentCP&) = delete;

    mutable std::mutex mutex_;
    bool initialized_ = false;
    std::string ca_base_;
    std::string ap_base_;
    ProxyConfig proxy_;
    TLSConfig tls_;
    std::string storage_path_;
    LogLevel log_level_ = LogLevel::Info;
    std::unordered_map<std::string, std::unique_ptr<class AgentID>> aids_;
};

class ACP_API AgentID {
public:
    ~AgentID();

    Result Online();
    void Offline();
    bool IsOnline() const;
    bool IsValid() const;
    AgentState GetState() const;

    std::string GetAID() const;
    std::string GetSignature() const;
    std::string GetPublicKey() const;
    std::string GetCertificate() const;

    SessionManager& Sessions();
    FileClient& Files();

    void SetMessageHandler(MessageHandler handler);
    void SetErrorHandler(ErrorHandler handler);
    void SetMetricsHandler(MetricsHandler handler);
    void SetStateChangeHandler(StateChangeHandler handler);
    void SetInviteHandler(InviteHandler handler);

    // -- Group Module --

    /// Initialize group client for same-AP communication.
    /// @param session_id  Session ID with group.{issuer}
    /// @param target_aid  Target group AID (default: auto-computed as group.{issuer})
    void InitGroupClient(const std::string& session_id, const std::string& target_aid = "");

    /// Initialize group client for cross-AP communication.
    void InitGroupClientCrossAp(const std::string& session_id, const std::string& target_aid);

    /// Get the group target AID (e.g. "group.aid.net")
    std::string GetGroupTargetAid() const;

    /// Close group client and release resources.
    void CloseGroupClient();

    /// Handle incoming group protocol message. Returns true if handled.
    bool HandleGroupMessage(const std::string& cmd, const std::string& data_json);

    /// Set group event handler for notifications.
    void SetGroupEventHandler(group::ACPGroupEventHandler* handler);

    /// Set group cursor store for persistence.
    void SetGroupCursorStore(group::CursorStore* store);

    /// Get group operations interface. Returns nullptr if group client not initialized.
    group::GroupOperations* GroupOps();

    /// Get group client. Returns nullptr if not initialized.
    group::ACPGroupClient* GroupClient();

    Result SendMessage(const std::string& session_id, const std::vector<Block>& blocks);
    Result SendMessage(const std::string& session_id,
                       const std::string& receiver,
                       const std::vector<Block>& blocks);
    Result SendMessageWithInstruction(const std::string& session_id,
                                      const std::vector<Block>& blocks,
                                      const Instruction& instruction);

    Result CreateStream(const std::string& session_id,
                        const std::string& receiver,
                        const std::string& content_type,
                        Stream** out);

    Result UploadFile(const std::string& path,
                      FileUploadCallback callback,
                      std::string* url_out);
    Result DownloadFile(const std::string& url,
                        const std::string& output_path,
                        FileDownloadCallback callback);

private:
    friend class AgentCP;
    friend class SessionManager;
    friend class FileClient;
    explicit AgentID(const std::string& aid);

    void SetState(AgentState state);
    void Invalidate();

    std::string aid_;
    AgentCP* owner_ = nullptr;
    mutable std::mutex mutex_;
    AgentState state_ = AgentState::Offline;
    bool invalidated_ = false;

    // Certificate-based identity
    std::string cert_pem_;    // certificate PEM content
    std::string certs_path_;  // path to certs directory

    SessionManager* sessions_ptr_ = nullptr;
    FileClient* file_client_ptr_ = nullptr;

    // Network clients (owned)
    std::unique_ptr<client::AuthClient> auth_client_;
    std::unique_ptr<client::HeartbeatClient> heartbeat_client_;
    std::unique_ptr<client::MessageClient> message_client_;
    std::string signature_;
    std::string heartbeat_server_;
    std::string message_server_;
    std::string aid_path_;
    std::string seed_password_;

    MessageHandler message_handler_;
    ErrorHandler error_handler_;
    MetricsHandler metrics_handler_;
    StateChangeHandler state_change_handler_;
    InviteHandler invite_handler_;

    // Group module
    std::string group_target_aid_;
    std::string group_session_id_;
    std::unique_ptr<group::ACPGroupClient> group_client_;
    std::unique_ptr<group::GroupOperations> group_ops_;
};

class ACP_API SessionManager {
public:
    explicit SessionManager(AgentID* owner);

    Result CreateSession(const std::vector<std::string>& members, std::string* session_id_out);
    Result InviteAgent(const std::string& session_id, const std::string& agent_id);
    Result JoinSession(const std::string& session_id);
    Result LeaveSession(const std::string& session_id);
    Result CloseSession(const std::string& session_id);
    Result GetMemberList(const std::string& session_id, std::vector<SessionMember>* members_out);
    Result EjectAgent(const std::string& session_id, const std::string& agent_id);

    Session* GetSession(const std::string& session_id);
    std::vector<std::string> GetActiveSessions();
    Result GetSessionInfo(const std::string& session_id, SessionInfo* info_out);

private:
    AgentID* owner_ = nullptr;
    mutable std::mutex mutex_;
    std::unordered_map<std::string, std::unique_ptr<Session>> sessions_;
};

class ACP_API Session {
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

    Result GetMessages(int limit, int offset, std::vector<Message>* messages_out);

private:
    friend class SessionManager;
    Session(AgentID* owner, const std::string& session_id);

    AgentID* owner_ = nullptr;
    std::string session_id_;
    std::vector<SessionMember> members_;
    bool closed_ = false;
    mutable std::mutex mutex_;
};

class ACP_API Stream {
public:
    std::string GetStreamId() const;
    bool IsConnected() const;

    Result SendText(const std::string& chunk);
    Result SendBinary(const uint8_t* buffer, size_t size);
    void Close();

    void SetErrorHandler(ErrorHandler handler);

private:
    friend class AgentID;
    explicit Stream(const std::string& stream_id);

    std::string stream_id_;
    bool connected_ = false;
    mutable std::mutex mutex_;
    ErrorHandler error_handler_;
    std::string push_url_;
    std::unique_ptr<client::StreamClientImpl> stream_impl_;
};

class ACP_API FileClient {
public:
    explicit FileClient(AgentID* owner);

    Result UploadFile(const std::string& path,
                      FileUploadCallback callback,
                      std::string* url_out);
    Result DownloadFile(const std::string& url,
                        const std::string& output_path,
                        FileDownloadCallback callback);

private:
    AgentID* owner_ = nullptr;
};

}  // namespace agentcp
