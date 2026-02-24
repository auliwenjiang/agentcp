#pragma once

#include <string>
#include <functional>
#include <memory>
#include <mutex>
#include <atomic>
#include <thread>
#include <vector>

namespace agentcp {
namespace net {

// Callback types for WebSocket events
using WsMessageCallback = std::function<void(const std::string& message)>;
using WsBinaryCallback = std::function<void(const std::vector<uint8_t>& data)>;
using WsOpenCallback = std::function<void()>;
using WsCloseCallback = std::function<void(int code, const std::string& reason)>;
using WsErrorCallback = std::function<void(const std::string& error)>;

class WebSocketClient {
public:
    WebSocketClient();
    ~WebSocketClient();

    WebSocketClient(const WebSocketClient&) = delete;
    WebSocketClient& operator=(const WebSocketClient&) = delete;

    // Set callbacks
    void SetOnMessage(WsMessageCallback callback);
    void SetOnBinary(WsBinaryCallback callback);
    void SetOnOpen(WsOpenCallback callback);
    void SetOnClose(WsCloseCallback callback);
    void SetOnError(WsErrorCallback callback);

    // Connection
    bool Connect(const std::string& url);
    void Disconnect();
    bool IsConnected() const;

    // Send
    bool SendText(const std::string& message);
    bool SendBinary(const std::vector<uint8_t>& data);
    bool SendBinary(const uint8_t* data, size_t len);

    // Settings
    void SetPingInterval(int seconds);
    void SetVerifySSL(bool verify);

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

}  // namespace net
}  // namespace agentcp
