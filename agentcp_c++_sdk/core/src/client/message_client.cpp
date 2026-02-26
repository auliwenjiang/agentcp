#include "message_client.h"
#include "auth_client.h"

#include "../net/websocket_client.h"
#include "../protocol/message_protocol.h"
#include "../acp_log.h"

#include "third_party/json.hpp"

#include <algorithm>
#include <chrono>

using json = nlohmann::json;

namespace agentcp {
namespace client {

MessageClient::MessageClient(const std::string& agent_id,
                             const std::string& server_url,
                             AuthClient* auth_client,
                             const MessageClientConfig& config)
    : agent_id_(agent_id)
    , server_url_(server_url)
    , auth_client_(auth_client)
    , config_(config)
    , current_reconnect_interval_(config.reconnect_base_interval) {}

MessageClient::~MessageClient() {
    Disconnect();
}

std::string MessageClient::BuildWebSocketUrl() const {
    std::string ws_url = server_url_;
    // Replace https:// with wss:// and http:// with ws://
    if (ws_url.substr(0, 8) == "https://") {
        ws_url = "wss://" + ws_url.substr(8);
    } else if (ws_url.substr(0, 7) == "http://") {
        ws_url = "ws://" + ws_url.substr(7);
    }
    // Remove trailing slash
    while (!ws_url.empty() && ws_url.back() == '/') {
        ws_url.pop_back();
    }
    return ws_url + "/session?agent_id=" + agent_id_ +
           "&signature=" + auth_client_->GetSignature();
}

bool MessageClient::Connect() {
    if (state_ == ConnectionState::Connected) return true;
    if (shutdown_requested_) return false;

    state_ = ConnectionState::Connecting;

    ws_ = std::make_unique<net::WebSocketClient>();
    ws_->SetPingInterval(config_.ping_interval);
    ws_->SetVerifySSL(false);

    ws_->SetOnMessage([this](const std::string& msg) { OnWsMessage(msg); });
    ws_->SetOnOpen([this]() { OnWsOpen(); });
    ws_->SetOnClose([this](int code, const std::string& reason) { OnWsClose(code, reason); });
    ws_->SetOnError([this](const std::string& err) { OnWsError(err); });

    std::string url = BuildWebSocketUrl();
    bool ok = ws_->Connect(url);

    if (!ok) {
        state_ = ConnectionState::Disconnected;
        StartReconnectLoopIfNeeded();
    }

    return ok;
}

void MessageClient::Disconnect() {
    shutdown_requested_ = true;

    if (ws_) {
        ws_->Disconnect();
    }

    state_ = ConnectionState::Disconnected;

    if (reconnect_thread_.joinable()) {
        reconnect_thread_.join();
    }
    reconnect_loop_running_ = false;

    // Notify all ack waiters
    {
        std::lock_guard<std::mutex> lock(ack_mutex_);
        for (auto& kv : ack_waiters_) {
            kv.second->ready = true;
            kv.second->cv.notify_all();
        }
        ack_waiters_.clear();
    }

    ws_.reset();
}

bool MessageClient::SendMessage(const std::string& json_message) {
    if (ws_ && ws_->IsConnected()) {
        bool ok = ws_->SendText(json_message);
        ACP_LOGD("MC::SendText: ok=%d, len=%zu", ok, json_message.size());
        return ok;
    }

    ACP_LOGW("MC::SendMessage FAILED: ws not connected, state=%d", static_cast<int>(state_.load()));
    return false;
}

std::string MessageClient::SendAndWaitAck(const std::string& json_message,
                                            const std::string& expected_cmd,
                                            const std::string& request_id,
                                            int timeout_ms) {
    auto waiter = std::make_shared<AckWaiter>();
    waiter->request_id = request_id;
    waiter->cmd = expected_cmd;

    {
        std::lock_guard<std::mutex> lock(ack_mutex_);
        ack_waiters_[request_id] = waiter;
    }

    if (!SendMessage(json_message)) {
        std::lock_guard<std::mutex> lock(ack_mutex_);
        ack_waiters_.erase(request_id);
        return {};
    }

    // Wait for ack
    std::unique_lock<std::mutex> lock(ack_mutex_);
    bool got_it = waiter->cv.wait_for(lock,
        std::chrono::milliseconds(timeout_ms),
        [&waiter]() { return waiter->ready; });

    ack_waiters_.erase(request_id);

    if (got_it && !waiter->result.empty()) {
        return waiter->result;
    }
    return {};
}

ConnectionState MessageClient::GetState() const {
    return state_;
}

bool MessageClient::IsConnected() const {
    return state_ == ConnectionState::Connected && ws_ && ws_->IsConnected();
}

bool MessageClient::IsHealthy() const {
    return IsConnected() && !shutdown_requested_;
}

bool MessageClient::IsReconnectLoopRunning() const {
    return reconnect_loop_running_.load();
}

void MessageClient::SetMessageHandler(OnMessageCallback handler) {
    message_handler_ = std::move(handler);
}

void MessageClient::SetDisconnectCallback(OnDisconnectCallback callback) {
    disconnect_callback_ = std::move(callback);
}

void MessageClient::SetReconnectCallback(OnReconnectCallback callback) {
    reconnect_callback_ = std::move(callback);
}

size_t MessageClient::GetQueueSize() const {
    std::lock_guard<std::mutex> lock(queue_mutex_);
    return message_queue_.size();
}

void MessageClient::FlushQueue() {
    std::lock_guard<std::mutex> lock(queue_mutex_);
    while (!message_queue_.empty()) {
        message_queue_.pop();
    }
}

void MessageClient::OnWsMessage(const std::string& message) {
    ACP_LOGI("MC::OnWsMessage: RAW message received, len=%zu", message.size());

    // Parse envelope
    protocol::MessageEnvelope env;
    if (!protocol::ParseEnvelope(message, &env)) {
        ACP_LOGW("MC::OnWsMessage: failed to parse envelope, len=%zu", message.size());
        return;
    }
    ACP_LOGD("MC::OnWsMessage: cmd=%s, data_len=%zu", env.cmd.c_str(), env.data_json.size());

    // Check if any ack waiter matches
    {
        std::lock_guard<std::mutex> lock(ack_mutex_);
        // Try to find a matching waiter by parsing request_id from data
        try {
            auto data_j = json::parse(env.data_json);
            if (data_j.contains("request_id")) {
                std::string req_id = data_j["request_id"].get<std::string>();
                auto it = ack_waiters_.find(req_id);
                if (it != ack_waiters_.end() && it->second->cmd == env.cmd) {
                    it->second->result = env.data_json;
                    it->second->ready = true;
                    it->second->cv.notify_all();
                    return;
                }
            }
        } catch (...) {}
    }

    // Dispatch to message handler
    if (message_handler_) {
        message_handler_(env.cmd, env.data_json);
    }
}

void MessageClient::OnWsOpen() {
    ACP_LOGI("MC::WebSocket OPEN");
    state_ = ConnectionState::Connected;
    current_reconnect_interval_ = config_.reconnect_base_interval;
    reconnect_attempt_count_ = 0;

    // Flush buffered messages
    FlushPendingMessages();

    if (reconnect_callback_) {
        reconnect_callback_();
    }
}

void MessageClient::OnWsClose(int code, const std::string& reason) {
    ACP_LOGW("MC::WebSocket CLOSE: code=%d, reason=%s", code, reason.c_str());
    state_ = ConnectionState::Disconnected;

    if (disconnect_callback_) {
        disconnect_callback_(code, reason);
    }

    // Auto-reconnect if not shutting down
    StartReconnectLoopIfNeeded();
}

void MessageClient::OnWsError(const std::string& error) {
    ACP_LOGE("MC::WebSocket ERROR: %s", error.c_str());
    (void)error;
    state_ = ConnectionState::Disconnected;
    StartReconnectLoopIfNeeded();
}

void MessageClient::ReconnectLoop() {
    while (!shutdown_requested_) {
        state_ = ConnectionState::Reconnecting;

        int wait_ms = static_cast<int>(current_reconnect_interval_ * 1000);
        std::this_thread::sleep_for(std::chrono::milliseconds(wait_ms));

        if (shutdown_requested_) break;

        // Try to reconnect
        ws_ = std::make_unique<net::WebSocketClient>();
        ws_->SetPingInterval(config_.ping_interval);
        ws_->SetVerifySSL(false);
        ws_->SetOnMessage([this](const std::string& msg) { OnWsMessage(msg); });
        ws_->SetOnOpen([this]() { OnWsOpen(); });
        ws_->SetOnClose([this](int code, const std::string& reason) { OnWsClose(code, reason); });
        ws_->SetOnError([this](const std::string& err) { OnWsError(err); });

        std::string url = BuildWebSocketUrl();
        bool ok = ws_->Connect(url);

        if (ok) {
            // Successfully reconnected
            reconnect_loop_running_ = false;
            return;
        }

        // Exponential backoff
        current_reconnect_interval_ = std::min(
            current_reconnect_interval_ * config_.reconnect_backoff_factor,
            config_.reconnect_max_interval);
        ++reconnect_attempt_count_;
    }

    reconnect_loop_running_ = false;
}

void MessageClient::StartReconnectLoopIfNeeded() {
    if (!config_.auto_reconnect || shutdown_requested_) {
        return;
    }

    if (reconnect_thread_.joinable() && !reconnect_loop_running_.load()) {
        reconnect_thread_.join();
    }

    bool expected = false;
    if (reconnect_loop_running_.compare_exchange_strong(expected, true)) {
        reconnect_thread_ = std::thread(&MessageClient::ReconnectLoop, this);
    }
}

void MessageClient::FlushPendingMessages() {
    std::lock_guard<std::mutex> lock(queue_mutex_);
    while (!message_queue_.empty() && ws_ && ws_->IsConnected()) {
        ws_->SendText(message_queue_.front());
        message_queue_.pop();
    }
}

}  // namespace client
}  // namespace agentcp
