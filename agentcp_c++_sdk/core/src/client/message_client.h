#pragma once

#include <string>
#include <functional>
#include <memory>
#include <mutex>
#include <atomic>
#include <queue>
#include <map>
#include <condition_variable>
#include <thread>

namespace agentcp {
namespace net {
class WebSocketClient;
}

namespace protocol {
struct CreateSessionAck;
struct CreateStreamAck;
}

namespace client {

class AuthClient;

struct MessageClientConfig {
    int max_queue_size = 5000;
    float connection_timeout = 3.0f;
    int ping_interval = 3;
    bool auto_reconnect = true;
    float reconnect_base_interval = 0.5f;
    float reconnect_max_interval = 10.0f;
    float reconnect_backoff_factor = 1.5f;
    int max_message_size = 10 * 1024 * 1024;
};

enum class ConnectionState {
    Disconnected,
    Connecting,
    Connected,
    Reconnecting
};

using OnMessageCallback = std::function<void(const std::string& cmd, const std::string& data_json)>;
using OnDisconnectCallback = std::function<void(int code, const std::string& reason)>;
using OnReconnectCallback = std::function<void()>;

class MessageClient {
public:
    MessageClient(const std::string& agent_id,
                  const std::string& server_url,
                  AuthClient* auth_client,
                  const MessageClientConfig& config = MessageClientConfig());
    ~MessageClient();

    MessageClient(const MessageClient&) = delete;
    MessageClient& operator=(const MessageClient&) = delete;

    // Start WebSocket connection
    bool Connect();

    // Stop WebSocket connection
    void Disconnect();

    // Send a raw JSON message through WebSocket
    bool SendMessage(const std::string& json_message);

    // Send and wait for a specific ack (returns the ack data_json)
    // Used for create_session, create_stream, etc.
    std::string SendAndWaitAck(const std::string& json_message,
                                const std::string& expected_cmd,
                                const std::string& request_id,
                                int timeout_ms = 5000);

    // Connection state
    ConnectionState GetState() const;
    bool IsConnected() const;
    bool IsHealthy() const;
    bool IsReconnectLoopRunning() const;

    // Callbacks
    void SetMessageHandler(OnMessageCallback handler);
    void SetDisconnectCallback(OnDisconnectCallback callback);
    void SetReconnectCallback(OnReconnectCallback callback);

    // Queue management
    size_t GetQueueSize() const;
    void FlushQueue();

private:
    void OnWsMessage(const std::string& message);
    void OnWsOpen();
    void OnWsClose(int code, const std::string& reason);
    void OnWsError(const std::string& error);

    void ReconnectLoop();
    void FlushPendingMessages();
    void StartReconnectLoopIfNeeded();

    std::string BuildWebSocketUrl() const;

    std::string agent_id_;
    std::string server_url_;
    AuthClient* auth_client_;
    MessageClientConfig config_;

    std::unique_ptr<net::WebSocketClient> ws_;
    std::atomic<ConnectionState> state_{ConnectionState::Disconnected};
    std::atomic<bool> shutdown_requested_{false};

    OnMessageCallback message_handler_;
    OnDisconnectCallback disconnect_callback_;
    OnReconnectCallback reconnect_callback_;

    // Message queue for buffering during disconnects
    mutable std::mutex queue_mutex_;
    std::queue<std::string> message_queue_;

    // Ack waiting mechanism
    struct AckWaiter {
        std::string request_id;
        std::string cmd;
        std::string result;
        std::condition_variable cv;
        bool ready = false;
    };
    mutable std::mutex ack_mutex_;
    std::map<std::string, std::shared_ptr<AckWaiter>> ack_waiters_;

    // Reconnection
    std::thread reconnect_thread_;
    std::atomic<bool> reconnect_loop_running_{false};
    float current_reconnect_interval_ = 0.5f;
    int reconnect_attempt_count_ = 0;

    mutable std::mutex mutex_;
};

}  // namespace client
}  // namespace agentcp
