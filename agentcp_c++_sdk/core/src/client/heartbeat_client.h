#pragma once

#include <string>
#include <cstdint>
#include <thread>
#include <atomic>
#include <mutex>
#include <functional>
#include <memory>

namespace agentcp {

namespace protocol {
struct InviteMessageReq;
}

namespace net {
class UdpSocket;
}

namespace client {

class AuthClient;

using InviteCallback = std::function<void(const protocol::InviteMessageReq& invite)>;

class HeartbeatClient {
public:
    HeartbeatClient(const std::string& agent_id,
                    const std::string& server_url,
                    const std::string& aid_path,
                    const std::string& seed_password,
                    AuthClient* auth_client = nullptr);
    ~HeartbeatClient();

    // Initialize (sign in to heartbeat server)
    bool Initialize();

    // Start heartbeat send/receive threads
    bool Online();

    // Stop heartbeat threads
    void Offline();

    // Re-authenticate (on 401)
    bool Reauthenticate();

    // Set invite callback
    void SetInviteCallback(InviteCallback callback);

    // Get auth signature
    std::string GetSignature() const;

    // Get server info
    std::string GetServerIP() const;
    int GetPort() const;
    uint64_t GetSignCookie() const;

    bool IsRunning() const;

private:
    void SendHeartbeatLoop();
    void ReceiveLoop();

    std::string agent_id_;
    std::string server_url_;
    std::string aid_path_;
    std::string seed_password_;

    std::unique_ptr<AuthClient> owned_auth_client_;
    AuthClient* auth_client_ = nullptr;

    std::unique_ptr<net::UdpSocket> udp_socket_;

    std::string server_ip_;
    int port_ = 0;
    uint64_t sign_cookie_ = 0;
    uint64_t heartbeat_interval_ms_ = 5000;
    uint64_t last_heartbeat_ms_ = 0;
    std::atomic<uint64_t> msg_seq_{0};

    std::atomic<bool> is_running_{false};
    std::atomic<bool> is_sending_{false};

    std::thread send_thread_;
    std::thread receive_thread_;

    InviteCallback invite_callback_;
    mutable std::mutex mutex_;
};

}  // namespace client
}  // namespace agentcp
