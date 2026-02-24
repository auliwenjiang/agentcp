#include "http_client.h"

#include "../acp_log.h"

#include <fstream>
#include <sstream>
#include <algorithm>
#include <cstring>
#include <stdexcept>
#include <mutex>

#if defined(_WIN32)
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <winsock2.h>
#include <ws2tcpip.h>
#pragma comment(lib, "ws2_32.lib")
#else
#include <sys/socket.h>
#include <netdb.h>
#include <unistd.h>
#include <arpa/inet.h>
#endif

#if AGENTCP_USE_OPENSSL
#include <openssl/ssl.h>
#include <openssl/err.h>
#endif

namespace agentcp {
namespace net {

namespace {

// Global DNS resolver callback (set from JNI on Android)
static DnsResolveFunc g_dns_resolver;
static std::mutex g_dns_mutex;

#if defined(_WIN32)
struct WinsockInit {
    WinsockInit() {
        WSADATA wsa;
        WSAStartup(MAKEWORD(2, 2), &wsa);
    }
    ~WinsockInit() { WSACleanup(); }
};
static WinsockInit winsock_init;

using socket_t = SOCKET;
constexpr socket_t INVALID_SOCK = INVALID_SOCKET;
inline void close_socket(socket_t s) { closesocket(s); }
#else
using socket_t = int;
constexpr socket_t INVALID_SOCK = -1;
inline void close_socket(socket_t s) { close(s); }
#endif

// Simple URL-encoding for non-ascii / special chars
std::string UrlEncode(const std::string& s) {
    std::ostringstream out;
    for (unsigned char c : s) {
        if (isalnum(c) || c == '-' || c == '_' || c == '.' || c == '~') {
            out << c;
        } else {
            out << '%' << std::uppercase;
            out << "0123456789ABCDEF"[c >> 4];
            out << "0123456789ABCDEF"[c & 0x0F];
        }
    }
    return out.str();
}

std::string GenerateBoundary() {
    static int counter = 0;
    std::ostringstream ss;
    ss << "----AgentCPBoundary" << ++counter << "x";
    return ss.str();
}

class SocketConnection {
public:
    SocketConnection() = default;
    ~SocketConnection() { Close(); }

    bool Connect(const std::string& host, int port, bool use_ssl, bool verify) {
        host_ = host;
        use_ssl_ = use_ssl;

        ACP_LOGD("SocketConnection::Connect() host=%s, port=%d, ssl=%d, verify=%d", host.c_str(), port, use_ssl, verify);

        struct addrinfo hints{}, *result = nullptr;
        hints.ai_family = AF_INET;
        hints.ai_socktype = SOCK_STREAM;

        std::string port_str = std::to_string(port);
        bool resolved = false;

        // Try platform DNS resolver first (e.g. Java InetAddress on Android)
        {
            DnsResolveFunc resolver;
            {
                std::lock_guard<std::mutex> lock(g_dns_mutex);
                resolver = g_dns_resolver;
            }
            if (resolver) {
                ACP_LOGD("SocketConnection::Connect() trying platform DNS resolver for %s ...", host.c_str());
                std::string ip = resolver(host);
                if (!ip.empty()) {
                    ACP_LOGD("SocketConnection::Connect() platform resolver returned: %s", ip.c_str());
                    if (getaddrinfo(ip.c_str(), port_str.c_str(), &hints, &result) == 0) {
                        resolved = true;
                    } else {
                        ACP_LOGW("SocketConnection::Connect() getaddrinfo failed for resolved IP %s", ip.c_str());
                    }
                } else {
                    ACP_LOGW("SocketConnection::Connect() platform DNS resolver returned empty for %s", host.c_str());
                }
            }
        }

        // Fallback to native getaddrinfo
        if (!resolved) {
            ACP_LOGD("SocketConnection::Connect() resolving DNS for %s:%s ...", host.c_str(), port_str.c_str());
            if (getaddrinfo(host.c_str(), port_str.c_str(), &hints, &result) != 0) {
                ACP_LOGE("SocketConnection::Connect() DNS resolution FAILED for %s", host.c_str());
                return false;
            }
        }
        ACP_LOGD("SocketConnection::Connect() DNS resolved OK");

        sock_ = socket(result->ai_family, result->ai_socktype, result->ai_protocol);
        if (sock_ == INVALID_SOCK) {
            ACP_LOGE("SocketConnection::Connect() socket() FAILED");
            freeaddrinfo(result);
            return false;
        }

        ACP_LOGD("SocketConnection::Connect() TCP connecting...");
        if (::connect(sock_, result->ai_addr, (int)result->ai_addrlen) != 0) {
            ACP_LOGE("SocketConnection::Connect() TCP connect FAILED to %s:%d", host.c_str(), port);
            close_socket(sock_);
            sock_ = INVALID_SOCK;
            freeaddrinfo(result);
            return false;
        }
        freeaddrinfo(result);
        ACP_LOGD("SocketConnection::Connect() TCP connected OK");

#if AGENTCP_USE_OPENSSL
        if (use_ssl) {
            ACP_LOGD("SocketConnection::Connect() TLS handshake starting...");
            ssl_ctx_ = SSL_CTX_new(TLS_client_method());
            if (!ssl_ctx_) {
                ACP_LOGE("SocketConnection::Connect() SSL_CTX_new FAILED");
                Close();
                return false;
            }

            if (!verify) {
                SSL_CTX_set_verify(ssl_ctx_, SSL_VERIFY_NONE, nullptr);
            }

            ssl_ = SSL_new(ssl_ctx_);
            SSL_set_fd(ssl_, (int)sock_);
            SSL_set_tlsext_host_name(ssl_, host.c_str());

            if (SSL_connect(ssl_) != 1) {
                unsigned long err = ERR_get_error();
                char err_buf[256];
                ERR_error_string_n(err, err_buf, sizeof(err_buf));
                ACP_LOGE("SocketConnection::Connect() SSL_connect FAILED: %s", err_buf);
                Close();
                return false;
            }
            ACP_LOGD("SocketConnection::Connect() TLS handshake OK");
        }
#else
        if (use_ssl) {
            ACP_LOGE("SocketConnection::Connect() SSL requested but OpenSSL not available");
            // No SSL support without OpenSSL
            Close();
            return false;
        }
#endif
        ACP_LOGI("SocketConnection::Connect() SUCCESS %s:%d (ssl=%d)", host.c_str(), port, use_ssl);
        return true;
    }

    int Send(const void* data, int len) {
#if AGENTCP_USE_OPENSSL
        if (ssl_) return SSL_write(ssl_, data, len);
#endif
        return ::send(sock_, (const char*)data, len, 0);
    }

    int Recv(void* buf, int len) {
#if AGENTCP_USE_OPENSSL
        if (ssl_) return SSL_read(ssl_, buf, len);
#endif
        return ::recv(sock_, (char*)buf, len, 0);
    }

    bool SendAll(const std::string& data) {
        size_t sent = 0;
        while (sent < data.size()) {
            int n = Send(data.data() + sent, (int)(data.size() - sent));
            if (n <= 0) return false;
            sent += n;
        }
        return true;
    }

    std::string RecvAll() {
        std::string result;
        char buf[4096];
        while (true) {
            int n = Recv(buf, sizeof(buf));
            if (n <= 0) break;
            result.append(buf, n);
        }
        return result;
    }

    void Close() {
#if AGENTCP_USE_OPENSSL
        if (ssl_) {
            SSL_shutdown(ssl_);
            SSL_free(ssl_);
            ssl_ = nullptr;
        }
        if (ssl_ctx_) {
            SSL_CTX_free(ssl_ctx_);
            ssl_ctx_ = nullptr;
        }
#endif
        if (sock_ != INVALID_SOCK) {
            close_socket(sock_);
            sock_ = INVALID_SOCK;
        }
    }

private:
    socket_t sock_ = INVALID_SOCK;
    bool use_ssl_ = false;
    std::string host_;
#if AGENTCP_USE_OPENSSL
    SSL_CTX* ssl_ctx_ = nullptr;
    SSL* ssl_ = nullptr;
#endif
};

// Parse HTTP response from raw data
HttpResponse ParseHttpResponse(const std::string& raw) {
    HttpResponse resp;
    auto header_end = raw.find("\r\n\r\n");
    if (header_end == std::string::npos) {
        resp.status_code = 0;
        return resp;
    }

    // Parse status line
    auto first_line_end = raw.find("\r\n");
    std::string status_line = raw.substr(0, first_line_end);
    // HTTP/1.1 200 OK
    auto sp1 = status_line.find(' ');
    if (sp1 != std::string::npos) {
        auto sp2 = status_line.find(' ', sp1 + 1);
        std::string code_str = (sp2 != std::string::npos)
            ? status_line.substr(sp1 + 1, sp2 - sp1 - 1)
            : status_line.substr(sp1 + 1);
        try {
            resp.status_code = std::stoi(code_str);
        } catch (...) {
            resp.status_code = 0;
        }
    }

    // Parse headers
    std::string header_section = raw.substr(first_line_end + 2, header_end - first_line_end - 2);
    std::istringstream hs(header_section);
    std::string line;
    while (std::getline(hs, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        auto colon = line.find(':');
        if (colon != std::string::npos) {
            std::string key = line.substr(0, colon);
            std::string val = line.substr(colon + 1);
            // trim leading spaces
            while (!val.empty() && val[0] == ' ') val.erase(val.begin());
            // lowercase key for easy lookup
            std::transform(key.begin(), key.end(), key.begin(), ::tolower);
            resp.headers[key] = val;
        }
    }

    resp.body = raw.substr(header_end + 4);
    return resp;
}

// Handle chunked transfer encoding
std::string DecodeChunked(const std::string& body) {
    std::string result;
    size_t pos = 0;
    while (pos < body.size()) {
        auto line_end = body.find("\r\n", pos);
        if (line_end == std::string::npos) break;
        std::string chunk_size_str = body.substr(pos, line_end - pos);
        size_t chunk_size = 0;
        try {
            chunk_size = std::stoull(chunk_size_str, nullptr, 16);
        } catch (...) {
            break;
        }
        if (chunk_size == 0) break;
        pos = line_end + 2;
        if (pos + chunk_size > body.size()) break;
        result.append(body, pos, chunk_size);
        pos += chunk_size + 2;  // skip \r\n after chunk
    }
    return result;
}

}  // anonymous namespace

HttpClient::HttpClient() = default;
HttpClient::~HttpClient() = default;

void HttpClient::SetDnsResolver(DnsResolveFunc resolver) {
    std::lock_guard<std::mutex> lock(g_dns_mutex);
    g_dns_resolver = std::move(resolver);
}

DnsResolveFunc HttpClient::GetDnsResolver() {
    std::lock_guard<std::mutex> lock(g_dns_mutex);
    return g_dns_resolver;
}

void HttpClient::SetVerifySSL(bool verify) { verify_ssl_ = verify; }
void HttpClient::SetTimeout(int timeout_seconds) { timeout_seconds_ = timeout_seconds; }
void HttpClient::SetUserAgent(const std::string& user_agent) { user_agent_ = user_agent; }

HttpClient::ParsedUrl HttpClient::ParseUrl(const std::string& url) {
    ParsedUrl parsed;
    std::string u = url;

    // Scheme
    auto scheme_end = u.find("://");
    if (scheme_end != std::string::npos) {
        parsed.scheme = u.substr(0, scheme_end);
        u = u.substr(scheme_end + 3);
    } else {
        parsed.scheme = "http";
    }

    // Path
    auto path_start = u.find('/');
    if (path_start != std::string::npos) {
        parsed.path = u.substr(path_start);
        u = u.substr(0, path_start);
    } else {
        parsed.path = "/";
    }

    // Host and port
    auto port_start = u.find(':');
    if (port_start != std::string::npos) {
        parsed.host = u.substr(0, port_start);
        try {
            parsed.port = std::stoi(u.substr(port_start + 1));
        } catch (...) {
            parsed.port = (parsed.scheme == "https") ? 443 : 80;
        }
    } else {
        parsed.host = u;
        parsed.port = (parsed.scheme == "https") ? 443 : 80;
    }

    return parsed;
}

HttpResponse HttpClient::PostJson(const std::string& url, const std::string& json_body) {
    ACP_LOGD("HttpClient::PostJson() url=%s, body_len=%zu", url.c_str(), json_body.size());
    auto parsed = ParseUrl(url);
    bool use_ssl = (parsed.scheme == "https");
    ACP_LOGD("HttpClient::PostJson() parsed: host=%s, port=%d, path=%s, ssl=%d", parsed.host.c_str(), parsed.port, parsed.path.c_str(), use_ssl);

    SocketConnection conn;
    if (!conn.Connect(parsed.host, parsed.port, use_ssl, verify_ssl_)) {
        ACP_LOGE("HttpClient::PostJson() connection FAILED to %s:%d", parsed.host.c_str(), parsed.port);
        return HttpResponse{0, "Connection failed", {}};
    }

    std::ostringstream req;
    req << "POST " << parsed.path << " HTTP/1.1\r\n"
        << "Host: " << parsed.host << "\r\n"
        << "User-Agent: " << user_agent_ << "\r\n"
        << "Content-Type: application/json\r\n"
        << "Content-Length: " << json_body.size() << "\r\n"
        << "Connection: close\r\n"
        << "\r\n"
        << json_body;

    if (!conn.SendAll(req.str())) {
        ACP_LOGE("HttpClient::PostJson() send FAILED");
        return HttpResponse{0, "Send failed", {}};
    }
    ACP_LOGD("HttpClient::PostJson() request sent, waiting for response...");

    std::string raw = conn.RecvAll();
    ACP_LOGD("HttpClient::PostJson() received %zu bytes", raw.size());
    auto resp = ParseHttpResponse(raw);
    ACP_LOGD("HttpClient::PostJson() response status=%d, body_len=%zu", resp.status_code, resp.body.size());

    // Handle chunked encoding
    auto it = resp.headers.find("transfer-encoding");
    if (it != resp.headers.end() && it->second.find("chunked") != std::string::npos) {
        resp.body = DecodeChunked(resp.body);
    }

    return resp;
}

HttpResponse HttpClient::PostMultipart(const std::string& url,
                                        const std::map<std::string, std::string>& fields,
                                        const std::string& file_field_name,
                                        const std::string& file_path,
                                        ProgressCallback progress) {
    auto parsed = ParseUrl(url);
    bool use_ssl = (parsed.scheme == "https");

    // Read file
    std::ifstream file(file_path, std::ios::binary);
    if (!file.is_open()) {
        return HttpResponse{0, "File not found", {}};
    }
    std::string file_content((std::istreambuf_iterator<char>(file)),
                             std::istreambuf_iterator<char>());
    file.close();

    // Extract filename
    std::string filename = file_path;
    auto slash = filename.find_last_of("/\\");
    if (slash != std::string::npos) filename = filename.substr(slash + 1);

    std::string boundary = GenerateBoundary();

    // Build multipart body
    std::ostringstream body;
    for (const auto& kv : fields) {
        body << "--" << boundary << "\r\n"
             << "Content-Disposition: form-data; name=\"" << kv.first << "\"\r\n\r\n"
             << kv.second << "\r\n";
    }
    body << "--" << boundary << "\r\n"
         << "Content-Disposition: form-data; name=\"" << file_field_name << "\"; filename=\"" << filename << "\"\r\n"
         << "Content-Type: application/octet-stream\r\n\r\n";

    std::string body_prefix = body.str();
    std::string body_suffix = "\r\n--" + boundary + "--\r\n";

    size_t total_body_size = body_prefix.size() + file_content.size() + body_suffix.size();

    SocketConnection conn;
    if (!conn.Connect(parsed.host, parsed.port, use_ssl, verify_ssl_)) {
        return HttpResponse{0, "Connection failed", {}};
    }

    std::ostringstream req;
    req << "POST " << parsed.path << " HTTP/1.1\r\n"
        << "Host: " << parsed.host << "\r\n"
        << "User-Agent: " << user_agent_ << "\r\n"
        << "Content-Type: multipart/form-data; boundary=" << boundary << "\r\n"
        << "Content-Length: " << total_body_size << "\r\n"
        << "Connection: close\r\n"
        << "\r\n";

    if (!conn.SendAll(req.str())) {
        return HttpResponse{0, "Send failed", {}};
    }

    if (!conn.SendAll(body_prefix)) {
        return HttpResponse{0, "Send failed", {}};
    }

    // Send file content in chunks
    size_t sent = 0;
    const size_t chunk_size = 16384;
    while (sent < file_content.size()) {
        size_t to_send = std::min(chunk_size, file_content.size() - sent);
        int n = conn.Send(file_content.data() + sent, (int)to_send);
        if (n <= 0) return HttpResponse{0, "Send failed", {}};
        sent += n;
        if (progress) {
            progress(sent, file_content.size());
        }
    }

    if (!conn.SendAll(body_suffix)) {
        return HttpResponse{0, "Send failed", {}};
    }

    std::string raw = conn.RecvAll();
    auto resp = ParseHttpResponse(raw);

    auto it = resp.headers.find("transfer-encoding");
    if (it != resp.headers.end() && it->second.find("chunked") != std::string::npos) {
        resp.body = DecodeChunked(resp.body);
    }

    return resp;
}

HttpResponse HttpClient::GetToFile(const std::string& url,
                                    const std::string& output_path,
                                    ProgressCallback progress) {
    auto parsed = ParseUrl(url);
    bool use_ssl = (parsed.scheme == "https");

    SocketConnection conn;
    if (!conn.Connect(parsed.host, parsed.port, use_ssl, verify_ssl_)) {
        return HttpResponse{0, "Connection failed", {}};
    }

    std::ostringstream req;
    req << "GET " << parsed.path << " HTTP/1.1\r\n"
        << "Host: " << parsed.host << "\r\n"
        << "User-Agent: " << user_agent_ << "\r\n"
        << "Connection: close\r\n"
        << "\r\n";

    if (!conn.SendAll(req.str())) {
        return HttpResponse{0, "Send failed", {}};
    }

    // Read headers first
    std::string header_buf;
    char buf[4096];
    size_t header_end_pos = std::string::npos;

    while (header_end_pos == std::string::npos) {
        int n = conn.Recv(buf, sizeof(buf));
        if (n <= 0) break;
        header_buf.append(buf, n);
        header_end_pos = header_buf.find("\r\n\r\n");
    }

    if (header_end_pos == std::string::npos) {
        return HttpResponse{0, "Invalid response", {}};
    }

    auto resp = ParseHttpResponse(header_buf.substr(0, header_end_pos + 4) + "placeholder");
    resp.body.clear();

    // Get content length if available
    size_t content_length = 0;
    auto cl_it = resp.headers.find("content-length");
    if (cl_it != resp.headers.end()) {
        try { content_length = std::stoull(cl_it->second); } catch (...) {}
    }

    // Write remaining data after headers to file
    std::ofstream out(output_path, std::ios::binary);
    if (!out.is_open()) {
        return HttpResponse{0, "Cannot open output file", {}};
    }

    std::string remaining = header_buf.substr(header_end_pos + 4);
    size_t total_written = 0;
    if (!remaining.empty()) {
        out.write(remaining.data(), remaining.size());
        total_written += remaining.size();
        if (progress) progress(total_written, content_length);
    }

    while (true) {
        int n = conn.Recv(buf, sizeof(buf));
        if (n <= 0) break;
        out.write(buf, n);
        total_written += n;
        if (progress) progress(total_written, content_length);
    }

    out.close();
    resp.body = output_path;
    return resp;
}

HttpResponse HttpClient::Get(const std::string& url) {
    auto parsed = ParseUrl(url);
    bool use_ssl = (parsed.scheme == "https");

    SocketConnection conn;
    if (!conn.Connect(parsed.host, parsed.port, use_ssl, verify_ssl_)) {
        return HttpResponse{0, "Connection failed", {}};
    }

    std::ostringstream req;
    req << "GET " << parsed.path << " HTTP/1.1\r\n"
        << "Host: " << parsed.host << "\r\n"
        << "User-Agent: " << user_agent_ << "\r\n"
        << "Connection: close\r\n"
        << "\r\n";

    if (!conn.SendAll(req.str())) {
        return HttpResponse{0, "Send failed", {}};
    }

    std::string raw = conn.RecvAll();
    auto resp = ParseHttpResponse(raw);

    auto it = resp.headers.find("transfer-encoding");
    if (it != resp.headers.end() && it->second.find("chunked") != std::string::npos) {
        resp.body = DecodeChunked(resp.body);
    }

    return resp;
}

}  // namespace net
}  // namespace agentcp
