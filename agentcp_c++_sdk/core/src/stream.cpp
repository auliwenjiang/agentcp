#include "agentcp/agentcp.h"

#include "internal.h"
#include "client/stream_client_impl.h"

#include <utility>

namespace agentcp {

Stream::Stream(const std::string& stream_id) : stream_id_(stream_id), connected_(false) {}

std::string Stream::GetStreamId() const {
    return stream_id_;
}

bool Stream::IsConnected() const {
    std::lock_guard<std::mutex> lock(mutex_);
    if (stream_impl_) return stream_impl_->IsConnected();
    return connected_;
}

Result Stream::SendText(const std::string& chunk) {
    if (!IsConnected()) {
        return MakeError(ErrorCode::STREAM_NOT_CONNECTED, "stream is not connected");
    }

    if (stream_impl_) {
        if (stream_impl_->SendText(chunk)) {
            return Result::Ok();
        }
        return MakeError(ErrorCode::STREAM_SEND_FAILED, "failed to send text chunk");
    }

    return MakeError(ErrorCode::NOT_IMPLEMENTED, "stream impl not available");
}

Result Stream::SendBinary(const uint8_t* buffer, size_t size) {
    if (!IsConnected()) {
        return MakeError(ErrorCode::STREAM_NOT_CONNECTED, "stream is not connected");
    }

    if (stream_impl_) {
        if (stream_impl_->SendBinary(buffer, size)) {
            return Result::Ok();
        }
        return MakeError(ErrorCode::STREAM_SEND_FAILED, "failed to send binary data");
    }

    return MakeError(ErrorCode::NOT_IMPLEMENTED, "stream impl not available");
}

void Stream::Close() {
    std::lock_guard<std::mutex> lock(mutex_);
    connected_ = false;
    if (stream_impl_) {
        stream_impl_->Close();
        stream_impl_.reset();
    }
}

void Stream::SetErrorHandler(ErrorHandler handler) {
    error_handler_ = std::move(handler);
    if (stream_impl_) {
        stream_impl_->SetErrorCallback([this](const std::string& err) {
            if (error_handler_) {
                ErrorInfo info;
                info.subsystem = "stream";
                info.message = err;
                info.severity = ErrorSeverity::Error;
                error_handler_(info);
            }
        });
    }
}

}  // namespace agentcp
