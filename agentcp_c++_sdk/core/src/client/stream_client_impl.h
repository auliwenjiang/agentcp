#pragma once

#include <string>
#include <memory>
#include <mutex>
#include <atomic>
#include <cstdint>
#include <functional>

namespace agentcp {
namespace net {
class WebSocketClient;
}

namespace client {

class AuthClient;

using StreamErrorCallback = std::function<void(const std::string& error)>;

class StreamClientImpl {
public:
    StreamClientImpl(const std::string& push_url,
                     const std::string& agent_id,
                     const std::string& signature);
    ~StreamClientImpl();

    StreamClientImpl(const StreamClientImpl&) = delete;
    StreamClientImpl& operator=(const StreamClientImpl&) = delete;

    // Connect to the stream WebSocket
    bool Connect();

    // Disconnect
    void Disconnect();

    // Send text chunk (builds push_text_stream_req)
    bool SendText(const std::string& chunk);

    // Send binary data (uses WSS binary protocol)
    bool SendBinary(const uint8_t* data, size_t len);

    // Close the stream (sends close_stream_req)
    void Close();

    bool IsConnected() const;

    void SetErrorCallback(StreamErrorCallback callback);

private:
    std::string push_url_;
    std::string agent_id_;
    std::string signature_;

    std::unique_ptr<net::WebSocketClient> ws_;
    std::atomic<bool> connected_{false};
    std::atomic<uint32_t> msg_seq_{0};

    StreamErrorCallback error_callback_;
    mutable std::mutex mutex_;
};

}  // namespace client
}  // namespace agentcp
