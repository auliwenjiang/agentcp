#pragma once

#include <string>

namespace agentcp {

enum class ErrorCode : int {
    OK = 0,
    UNKNOWN_ERROR = 1,
    INVALID_ARGUMENT = 2,
    NOT_INITIALIZED = 3,
    NOT_IMPLEMENTED = 4,

    AUTH_FAILED = 1000,
    INVALID_SIGNATURE = 1001,
    TOKEN_EXPIRED = 1002,
    CERT_ERROR = 1003,

    HB_AUTH_FAILED = 2000,
    HB_TIMEOUT = 2001,
    HB_REAUTH_REQUIRED = 2002,

    WS_CONNECT_FAILED = 3000,
    WS_DISCONNECTED = 3001,
    WS_SEND_FAILED = 3002,
    WS_TIMEOUT = 3003,

    AID_NOT_FOUND = 4000,
    AID_ALREADY_EXISTS = 4001,
    AID_INVALID = 4002,

    SESSION_NOT_FOUND = 4100,
    SESSION_NOT_MEMBER = 4101,
    SESSION_PERMISSION_DENIED = 4102,
    SESSION_CLOSED = 4103,

    STREAM_NOT_CONNECTED = 5000,
    STREAM_SEND_FAILED = 5001,
    STREAM_CLOSED = 5002,

    FILE_NOT_FOUND = 6000,
    FILE_TOO_LARGE = 6001,
    FILE_UPLOAD_FAILED = 6002,
    FILE_DOWNLOAD_FAILED = 6003,

    DB_OPEN_FAILED = 7000,
    DB_QUERY_FAILED = 7001,
    DB_MIGRATION_FAILED = 7002,

    NETWORK_ERROR = 8000,
    NETWORK_TIMEOUT = 8001,
    DNS_FAILED = 8002,
    TLS_ERROR = 8003
};

struct Result {
    int code = 0;
    std::string message;
    std::string context;

    bool ok() const { return code == 0; }
    operator bool() const { return ok(); }

    static Result Ok() { return Result{}; }
    static Result Error(ErrorCode code, const std::string& message, const std::string& context = {}) {
        Result r;
        r.code = static_cast<int>(code);
        r.message = message;
        r.context = context;
        return r;
    }
};

}  // namespace agentcp
