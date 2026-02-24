#include "heartbeat_client.h"
#include "auth_client.h"

#include "../net/udp_socket.h"
#include "../protocol/heartbeat_protocol.h"
#include "../acp_log.h"

#include <chrono>
#include <cstring>

namespace agentcp {
namespace client {

HeartbeatClient::HeartbeatClient(const std::string& agent_id,
                                 const std::string& server_url,
                                 const std::string& aid_path,
                                 const std::string& seed_password,
                                 AuthClient* auth_client)
    : agent_id_(agent_id)
    , server_url_(server_url)
    , aid_path_(aid_path)
    , seed_password_(seed_password) {

    // Use server_url directly as the auth API base
    // (caller is responsible for providing the correct base URL)
    std::string api_url = server_url;

    if (auth_client) {
        auth_client_ = auth_client;
    } else {
        owned_auth_client_ = std::make_unique<AuthClient>(agent_id, api_url, aid_path, seed_password);
        auth_client_ = owned_auth_client_.get();
    }
}

HeartbeatClient::~HeartbeatClient() {
    Offline();
}

bool HeartbeatClient::Initialize() {
    ACP_LOGI("HeartbeatClient::Initialize() calling auth SignIn...");
    if (!auth_client_->SignIn()) {
        ACP_LOGE("HeartbeatClient::Initialize() auth SignIn FAILED");
        return false;
    }

    std::lock_guard<std::mutex> lock(mutex_);
    server_ip_ = auth_client_->GetServerIP();
    port_ = auth_client_->GetPort();
    sign_cookie_ = auth_client_->GetSignCookie();

    ACP_LOGI("HeartbeatClient::Initialize() OK: server_ip=%s, port=%d, cookie=%llu",
             server_ip_.c_str(), port_, (unsigned long long)sign_cookie_);
    return !server_ip_.empty() && port_ != 0;
}

bool HeartbeatClient::Online() {
    ACP_LOGI("HeartbeatClient::Online() starting...");
    if (is_running_) {
        ACP_LOGW("HeartbeatClient::Online() already running");
        return true;
    }

    udp_socket_ = std::make_unique<net::UdpSocket>();
    if (!udp_socket_->Bind("0.0.0.0", 0)) {
        ACP_LOGE("HeartbeatClient::Online() UDP bind FAILED");
        return false;
    }

    is_running_ = true;
    is_sending_ = true;

    send_thread_ = std::thread(&HeartbeatClient::SendHeartbeatLoop, this);
    receive_thread_ = std::thread(&HeartbeatClient::ReceiveLoop, this);

    ACP_LOGI("HeartbeatClient::Online() threads started");
    return true;
}

void HeartbeatClient::Offline() {
    is_sending_ = false;
    is_running_ = false;

    if (udp_socket_) {
        udp_socket_->Close();
    }

    if (send_thread_.joinable()) {
        send_thread_.join();
    }
    if (receive_thread_.joinable()) {
        receive_thread_.join();
    }

    udp_socket_.reset();
}

bool HeartbeatClient::Reauthenticate() {
    if (!auth_client_->SignIn()) return false;

    std::lock_guard<std::mutex> lock(mutex_);
    server_ip_ = auth_client_->GetServerIP();
    port_ = auth_client_->GetPort();
    sign_cookie_ = auth_client_->GetSignCookie();
    return true;
}

void HeartbeatClient::SetInviteCallback(InviteCallback callback) {
    invite_callback_ = std::move(callback);
}

std::string HeartbeatClient::GetSignature() const {
    return auth_client_->GetSignature();
}

std::string HeartbeatClient::GetServerIP() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return server_ip_;
}

int HeartbeatClient::GetPort() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return port_;
}

uint64_t HeartbeatClient::GetSignCookie() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return sign_cookie_;
}

bool HeartbeatClient::IsRunning() const {
    return is_running_;
}

void HeartbeatClient::SendHeartbeatLoop() {
    while (is_sending_ && is_running_) {
        try {
            auto now_ms = static_cast<uint64_t>(
                std::chrono::duration_cast<std::chrono::milliseconds>(
                    std::chrono::system_clock::now().time_since_epoch()).count());

            uint64_t interval;
            std::string ip;
            int port;
            uint64_t cookie;
            {
                std::lock_guard<std::mutex> lock(mutex_);
                interval = heartbeat_interval_ms_;
                ip = server_ip_;
                port = port_;
                cookie = sign_cookie_;
            }

            if (now_ms > (last_heartbeat_ms_ + interval)) {
                last_heartbeat_ms_ = now_ms;
                uint64_t seq = ++msg_seq_;

                protocol::HeartbeatMessageReq req;
                req.header.message_mask = 0;
                req.header.message_seq = seq;
                req.header.message_type = protocol::MSG_TYPE_HEARTBEAT_REQ;
                req.header.payload_size = 100;
                req.agent_id = agent_id_;
                req.sign_cookie = cookie;

                auto data = req.Serialize();
                if (udp_socket_ && udp_socket_->IsValid()) {
                    udp_socket_->SendTo(data, ip, static_cast<uint16_t>(port));
                }
            }

            std::this_thread::sleep_for(std::chrono::seconds(1));
        } catch (...) {
            std::this_thread::sleep_for(std::chrono::seconds(1));
        }
    }
}

void HeartbeatClient::ReceiveLoop() {
    uint8_t buffer[1536];
    while (is_running_) {
        try {
            if (!udp_socket_ || !udp_socket_->IsValid()) {
                std::this_thread::sleep_for(std::chrono::milliseconds(100));
                continue;
            }

            int n = udp_socket_->RecvFrom(buffer, sizeof(buffer));
            if (n <= 0) {
                std::this_thread::sleep_for(std::chrono::milliseconds(100));
                continue;
            }

            // Parse header to get message type
            size_t offset = 0;
            auto header = protocol::UdpMessageHeader::Deserialize(buffer, n, &offset);

            if (header.message_type == protocol::MSG_TYPE_HEARTBEAT_RESP) {
                auto resp = protocol::HeartbeatMessageResp::Deserialize(buffer, n);

                if (resp.next_beat == 401) {
                    // Server requires re-authentication
                    Reauthenticate();
                } else {
                    std::lock_guard<std::mutex> lock(mutex_);
                    heartbeat_interval_ms_ = resp.next_beat;
                    if (heartbeat_interval_ms_ < 5000) {
                        heartbeat_interval_ms_ = 5000;
                    }
                }
            } else if (header.message_type == protocol::MSG_TYPE_INVITE_REQ) {
                auto invite_req = protocol::InviteMessageReq::Deserialize(buffer, n);

                if (invite_callback_) {
                    invite_callback_(invite_req);
                }

                // Send invite response
                uint64_t cookie;
                std::string ip;
                int port;
                {
                    std::lock_guard<std::mutex> lock(mutex_);
                    cookie = sign_cookie_;
                    ip = server_ip_;
                    port = port_;
                }

                uint64_t seq = ++msg_seq_;
                protocol::InviteMessageResp resp;
                resp.header.message_mask = 0;
                resp.header.message_seq = seq;
                resp.header.message_type = protocol::MSG_TYPE_INVITE_RESP;
                resp.header.payload_size = 0;
                resp.agent_id = agent_id_;
                resp.inviter_agent_id = invite_req.inviter_agent_id;
                resp.sign_cookie = cookie;

                auto data = resp.Serialize();
                if (udp_socket_ && udp_socket_->IsValid()) {
                    udp_socket_->SendTo(data, ip, static_cast<uint16_t>(port));
                }
            }
        } catch (...) {
            std::this_thread::sleep_for(std::chrono::milliseconds(1500));
        }
    }
}

}  // namespace client
}  // namespace agentcp
