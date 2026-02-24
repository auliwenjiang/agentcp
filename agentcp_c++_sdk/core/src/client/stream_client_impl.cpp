#include "stream_client_impl.h"

#include "../net/websocket_client.h"
#include "../protocol/message_protocol.h"
#include "../protocol/binary_protocol.h"

namespace agentcp {
namespace client {

StreamClientImpl::StreamClientImpl(const std::string& push_url,
                                   const std::string& agent_id,
                                   const std::string& signature)
    : push_url_(push_url)
    , agent_id_(agent_id)
    , signature_(signature) {}

StreamClientImpl::~StreamClientImpl() {
    Disconnect();
}

bool StreamClientImpl::Connect() {
    ws_ = std::make_unique<net::WebSocketClient>();
    ws_->SetPingInterval(3);
    ws_->SetVerifySSL(false);

    ws_->SetOnOpen([this]() {
        connected_ = true;
    });

    ws_->SetOnClose([this](int, const std::string&) {
        connected_ = false;
    });

    ws_->SetOnError([this](const std::string& err) {
        connected_ = false;
        if (error_callback_) error_callback_(err);
    });

    // Build URL with auth params
    std::string url = push_url_;
    if (url.find('?') != std::string::npos) {
        url += "&";
    } else {
        url += "?";
    }
    url += "agent_id=" + agent_id_ + "&signature=" + signature_;

    bool ok = ws_->Connect(url);
    if (!ok) {
        ws_.reset();
        return false;
    }

    return true;
}

void StreamClientImpl::Disconnect() {
    connected_ = false;
    if (ws_) {
        ws_->Disconnect();
        ws_.reset();
    }
}

bool StreamClientImpl::SendText(const std::string& chunk) {
    if (!connected_ || !ws_) return false;

    std::string msg = protocol::BuildPushTextStreamReq(chunk);

    // Encode as WSS binary message
    uint32_t seq = ++msg_seq_;
    auto binary = protocol::EncodeWssBinaryMessage(msg, seq);
    if (binary.empty()) return false;

    return ws_->SendBinary(binary);
}

bool StreamClientImpl::SendBinary(const uint8_t* data, size_t len) {
    if (!connected_ || !ws_) return false;

    uint32_t seq = ++msg_seq_;

    protocol::WssBinaryHeader header;
    header.msg_type = 5;  // file chunk
    header.msg_seq = seq;
    header.content_type = 5;  // binary file
    header.compressed = 0;

    auto binary = protocol::EncodeWssBinaryBuffer(data, len, header);
    if (binary.empty()) return false;

    return ws_->SendBinary(binary);
}

void StreamClientImpl::Close() {
    if (!connected_ || !ws_) return;

    std::string msg = protocol::BuildCloseStreamReq();
    uint32_t seq = ++msg_seq_;
    auto binary = protocol::EncodeWssBinaryMessage(msg, seq);
    if (!binary.empty()) {
        ws_->SendBinary(binary);
    }

    // Brief delay for close message to be sent
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    Disconnect();
}

bool StreamClientImpl::IsConnected() const {
    return connected_;
}

void StreamClientImpl::SetErrorCallback(StreamErrorCallback callback) {
    error_callback_ = std::move(callback);
}

}  // namespace client
}  // namespace agentcp
