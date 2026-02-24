#pragma once

#include <string>
#include <vector>
#include <cstdint>

namespace agentcp {
namespace net {

#if defined(_WIN32)
using socket_t = unsigned long long;  // SOCKET on Windows
#else
using socket_t = int;
#endif

class UdpSocket {
public:
    UdpSocket();
    ~UdpSocket();

    UdpSocket(const UdpSocket&) = delete;
    UdpSocket& operator=(const UdpSocket&) = delete;

    // Bind to a local address and port (0 for any port)
    bool Bind(const std::string& local_ip, uint16_t local_port);

    // Send data to a specific address
    int SendTo(const uint8_t* data, size_t len,
               const std::string& dest_ip, uint16_t dest_port);

    int SendTo(const std::vector<uint8_t>& data,
               const std::string& dest_ip, uint16_t dest_port);

    // Receive data (blocking)
    int RecvFrom(uint8_t* buffer, size_t buffer_size,
                 std::string* sender_ip = nullptr, uint16_t* sender_port = nullptr);

    // Get the local bound address
    uint16_t GetLocalPort() const;
    std::string GetLocalIP() const;

    void Close();
    bool IsValid() const;

private:
    socket_t sock_;
    std::string local_ip_;
    uint16_t local_port_ = 0;
};

}  // namespace net
}  // namespace agentcp
