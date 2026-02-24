#include "websocket_client.h"

#include <ixwebsocket/IXWebSocket.h>

namespace agentcp {
namespace net {

struct WebSocketClient::Impl {
    ix::WebSocket ws;
    WsMessageCallback on_message;
    WsBinaryCallback on_binary;
    WsOpenCallback on_open;
    WsCloseCallback on_close;
    WsErrorCallback on_error;
    std::atomic<bool> connected{false};
    int ping_interval = 3;
    bool verify_ssl = false;
};

WebSocketClient::WebSocketClient() : impl_(std::make_unique<Impl>()) {}

WebSocketClient::~WebSocketClient() {
    Disconnect();
}

void WebSocketClient::SetOnMessage(WsMessageCallback callback) {
    impl_->on_message = std::move(callback);
}

void WebSocketClient::SetOnBinary(WsBinaryCallback callback) {
    impl_->on_binary = std::move(callback);
}

void WebSocketClient::SetOnOpen(WsOpenCallback callback) {
    impl_->on_open = std::move(callback);
}

void WebSocketClient::SetOnClose(WsCloseCallback callback) {
    impl_->on_close = std::move(callback);
}

void WebSocketClient::SetOnError(WsErrorCallback callback) {
    impl_->on_error = std::move(callback);
}

void WebSocketClient::SetPingInterval(int seconds) {
    impl_->ping_interval = seconds;
}

void WebSocketClient::SetVerifySSL(bool verify) {
    impl_->verify_ssl = verify;
}

bool WebSocketClient::Connect(const std::string& url) {
    impl_->ws.setUrl(url);
    impl_->ws.setPingInterval(impl_->ping_interval);
    impl_->ws.disablePerMessageDeflate();

    ix::SocketTLSOptions tls_options;
    if (!impl_->verify_ssl) {
        tls_options.caFile = "NONE";
    }
    impl_->ws.setTLSOptions(tls_options);

    // Disable automatic reconnection - we handle it ourselves
    impl_->ws.disableAutomaticReconnection();

    impl_->ws.setOnMessageCallback([this](const ix::WebSocketMessagePtr& msg) {
        switch (msg->type) {
            case ix::WebSocketMessageType::Message:
                if (msg->binary) {
                    if (impl_->on_binary) {
                        std::vector<uint8_t> data(msg->str.begin(), msg->str.end());
                        impl_->on_binary(data);
                    }
                } else {
                    if (impl_->on_message) {
                        impl_->on_message(msg->str);
                    }
                }
                break;
            case ix::WebSocketMessageType::Open:
                impl_->connected = true;
                if (impl_->on_open) {
                    impl_->on_open();
                }
                break;
            case ix::WebSocketMessageType::Close:
                impl_->connected = false;
                if (impl_->on_close) {
                    impl_->on_close(msg->closeInfo.code, msg->closeInfo.reason);
                }
                break;
            case ix::WebSocketMessageType::Error:
                impl_->connected = false;
                if (impl_->on_error) {
                    impl_->on_error(msg->errorInfo.reason);
                }
                break;
            case ix::WebSocketMessageType::Ping:
            case ix::WebSocketMessageType::Pong:
            case ix::WebSocketMessageType::Fragment:
                break;
        }
    });

    impl_->ws.start();

    // Wait for connection with timeout
    int wait_ms = 0;
    const int timeout_ms = 5000;
    while (!impl_->connected && wait_ms < timeout_ms) {
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
        wait_ms += 50;
    }

    return impl_->connected;
}

void WebSocketClient::Disconnect() {
    impl_->ws.stop();
    impl_->connected = false;
}

bool WebSocketClient::IsConnected() const {
    return impl_->connected;
}

bool WebSocketClient::SendText(const std::string& message) {
    if (!impl_->connected) return false;
    auto result = impl_->ws.send(message);
    return result.success;
}

bool WebSocketClient::SendBinary(const std::vector<uint8_t>& data) {
    return SendBinary(data.data(), data.size());
}

bool WebSocketClient::SendBinary(const uint8_t* data, size_t len) {
    if (!impl_->connected) return false;
    std::string binary_data(reinterpret_cast<const char*>(data), len);
    auto result = impl_->ws.sendBinary(binary_data);
    return result.success;
}

}  // namespace net
}  // namespace agentcp
