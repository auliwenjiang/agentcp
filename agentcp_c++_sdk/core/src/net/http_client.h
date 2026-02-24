#pragma once

#include <string>
#include <map>
#include <vector>
#include <functional>
#include <cstdint>

namespace agentcp {
namespace net {

struct HttpResponse {
    int status_code = 0;
    std::string body;
    std::map<std::string, std::string> headers;

    bool ok() const { return status_code >= 200 && status_code < 300; }
};

using ProgressCallback = std::function<void(size_t bytes_transferred, size_t total_bytes)>;

// Custom DNS resolver: given a hostname, return resolved IP string (e.g. "1.2.3.4").
// Return empty string on failure. Used on Android where native getaddrinfo may not
// go through the system DNS resolver.
using DnsResolveFunc = std::function<std::string(const std::string& host)>;

class HttpClient {
public:
    HttpClient();
    ~HttpClient();

    void SetVerifySSL(bool verify);
    void SetTimeout(int timeout_seconds);
    void SetUserAgent(const std::string& user_agent);

    // Set a platform-specific DNS resolver (e.g. JNI callback to Java InetAddress).
    // If set, SocketConnection will use it before falling back to getaddrinfo.
    static void SetDnsResolver(DnsResolveFunc resolver);
    static DnsResolveFunc GetDnsResolver();

    // POST JSON
    HttpResponse PostJson(const std::string& url,
                          const std::string& json_body);

    // POST multipart form-data with file
    HttpResponse PostMultipart(const std::string& url,
                               const std::map<std::string, std::string>& fields,
                               const std::string& file_field_name,
                               const std::string& file_path,
                               ProgressCallback progress = nullptr);

    // GET with streaming download to file
    HttpResponse GetToFile(const std::string& url,
                           const std::string& output_path,
                           ProgressCallback progress = nullptr);

    // GET
    HttpResponse Get(const std::string& url);

private:
    struct ParsedUrl {
        std::string scheme;
        std::string host;
        int port;
        std::string path;
    };

    static ParsedUrl ParseUrl(const std::string& url);

    bool verify_ssl_ = false;
    int timeout_seconds_ = 30;
    std::string user_agent_ = "AgentCP/0.1.0";
};

}  // namespace net
}  // namespace agentcp
