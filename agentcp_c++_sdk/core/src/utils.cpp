#include "internal.h"

#include <atomic>
#include <chrono>
#include <sstream>

namespace agentcp {

const char* ErrorCodeToString(ErrorCode code) {
    switch (code) {
        case ErrorCode::OK: return "OK";
        case ErrorCode::UNKNOWN_ERROR: return "UNKNOWN_ERROR";
        case ErrorCode::INVALID_ARGUMENT: return "INVALID_ARGUMENT";
        case ErrorCode::NOT_INITIALIZED: return "NOT_INITIALIZED";
        case ErrorCode::NOT_IMPLEMENTED: return "NOT_IMPLEMENTED";
        case ErrorCode::AUTH_FAILED: return "AUTH_FAILED";
        case ErrorCode::INVALID_SIGNATURE: return "INVALID_SIGNATURE";
        case ErrorCode::TOKEN_EXPIRED: return "TOKEN_EXPIRED";
        case ErrorCode::CERT_ERROR: return "CERT_ERROR";
        case ErrorCode::HB_AUTH_FAILED: return "HB_AUTH_FAILED";
        case ErrorCode::HB_TIMEOUT: return "HB_TIMEOUT";
        case ErrorCode::HB_REAUTH_REQUIRED: return "HB_REAUTH_REQUIRED";
        case ErrorCode::WS_CONNECT_FAILED: return "WS_CONNECT_FAILED";
        case ErrorCode::WS_DISCONNECTED: return "WS_DISCONNECTED";
        case ErrorCode::WS_SEND_FAILED: return "WS_SEND_FAILED";
        case ErrorCode::WS_TIMEOUT: return "WS_TIMEOUT";
        case ErrorCode::AID_NOT_FOUND: return "AID_NOT_FOUND";
        case ErrorCode::AID_ALREADY_EXISTS: return "AID_ALREADY_EXISTS";
        case ErrorCode::AID_INVALID: return "AID_INVALID";
        case ErrorCode::SESSION_NOT_FOUND: return "SESSION_NOT_FOUND";
        case ErrorCode::SESSION_NOT_MEMBER: return "SESSION_NOT_MEMBER";
        case ErrorCode::SESSION_PERMISSION_DENIED: return "SESSION_PERMISSION_DENIED";
        case ErrorCode::SESSION_CLOSED: return "SESSION_CLOSED";
        case ErrorCode::STREAM_NOT_CONNECTED: return "STREAM_NOT_CONNECTED";
        case ErrorCode::STREAM_SEND_FAILED: return "STREAM_SEND_FAILED";
        case ErrorCode::STREAM_CLOSED: return "STREAM_CLOSED";
        case ErrorCode::FILE_NOT_FOUND: return "FILE_NOT_FOUND";
        case ErrorCode::FILE_TOO_LARGE: return "FILE_TOO_LARGE";
        case ErrorCode::FILE_UPLOAD_FAILED: return "FILE_UPLOAD_FAILED";
        case ErrorCode::FILE_DOWNLOAD_FAILED: return "FILE_DOWNLOAD_FAILED";
        case ErrorCode::DB_OPEN_FAILED: return "DB_OPEN_FAILED";
        case ErrorCode::DB_QUERY_FAILED: return "DB_QUERY_FAILED";
        case ErrorCode::DB_MIGRATION_FAILED: return "DB_MIGRATION_FAILED";
        case ErrorCode::NETWORK_ERROR: return "NETWORK_ERROR";
        case ErrorCode::NETWORK_TIMEOUT: return "NETWORK_TIMEOUT";
        case ErrorCode::DNS_FAILED: return "DNS_FAILED";
        case ErrorCode::TLS_ERROR: return "TLS_ERROR";
        default: return "UNKNOWN_ERROR";
    }
}

std::string GenerateId(const std::string& prefix) {
    static std::atomic<uint64_t> counter{0};
    auto now = std::chrono::system_clock::now().time_since_epoch();
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(now).count();

    std::ostringstream oss;
    oss << prefix << "-" << ms << "-" << counter.fetch_add(1);
    return oss.str();
}

}  // namespace agentcp
