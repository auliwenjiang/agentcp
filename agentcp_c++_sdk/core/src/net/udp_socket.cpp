#include "udp_socket.h"

#include <cstring>

#if defined(_WIN32)
#include <winsock2.h>
#include <ws2tcpip.h>
#pragma comment(lib, "ws2_32.lib")
static constexpr unsigned long long INVALID_SOCK = (unsigned long long)(~0);
inline void close_sock(unsigned long long s) { closesocket((SOCKET)s); }
#else
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <netdb.h>
static constexpr int INVALID_SOCK = -1;
inline void close_sock(int s) { ::close(s); }
#endif

namespace agentcp {
namespace net {

UdpSocket::UdpSocket() : sock_(INVALID_SOCK) {}

namespace {

bool ResolveIpv4(const std::string& host, struct in_addr* out_addr) {
    if (out_addr == nullptr) return false;

    // Fast path: already an IPv4 literal.
    if (inet_pton(AF_INET, host.c_str(), out_addr) == 1) {
        return true;
    }

    // Fallback: resolve hostname to IPv4.
    struct addrinfo hints{};
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_DGRAM;

    struct addrinfo* result = nullptr;
    int rc = getaddrinfo(host.c_str(), nullptr, &hints, &result);
    if (rc != 0 || result == nullptr) {
        return false;
    }

    auto* ipv4 = reinterpret_cast<struct sockaddr_in*>(result->ai_addr);
    *out_addr = ipv4->sin_addr;
    freeaddrinfo(result);
    return true;
}

}  // namespace

UdpSocket::~UdpSocket() {
    Close();
}

bool UdpSocket::Bind(const std::string& local_ip, uint16_t local_port) {
    Close();

#if defined(_WIN32)
    sock_ = (socket_t)::socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
#else
    sock_ = ::socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
#endif
    if (sock_ == INVALID_SOCK) return false;

    struct sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(local_port);

    if (local_ip.empty() || local_ip == "0.0.0.0") {
        addr.sin_addr.s_addr = INADDR_ANY;
    } else {
        inet_pton(AF_INET, local_ip.c_str(), &addr.sin_addr);
    }

    if (::bind((int)sock_, (struct sockaddr*)&addr, sizeof(addr)) != 0) {
        Close();
        return false;
    }

    // Get actual bound address
    struct sockaddr_in bound_addr{};
    socklen_t addr_len = sizeof(bound_addr);
    if (getsockname((int)sock_, (struct sockaddr*)&bound_addr, &addr_len) == 0) {
        local_port_ = ntohs(bound_addr.sin_port);
        char ip_buf[INET_ADDRSTRLEN];
        inet_ntop(AF_INET, &bound_addr.sin_addr, ip_buf, sizeof(ip_buf));
        local_ip_ = ip_buf;
    }

    return true;
}

int UdpSocket::SendTo(const uint8_t* data, size_t len,
                       const std::string& dest_ip, uint16_t dest_port) {
    if (sock_ == INVALID_SOCK) return -1;

    struct sockaddr_in dest{};
    dest.sin_family = AF_INET;
    dest.sin_port = htons(dest_port);
    if (!ResolveIpv4(dest_ip, &dest.sin_addr)) {
        return -1;
    }

    return (int)sendto((int)sock_, (const char*)data, (int)len, 0,
                       (struct sockaddr*)&dest, sizeof(dest));
}

int UdpSocket::SendTo(const std::vector<uint8_t>& data,
                       const std::string& dest_ip, uint16_t dest_port) {
    return SendTo(data.data(), data.size(), dest_ip, dest_port);
}

int UdpSocket::RecvFrom(uint8_t* buffer, size_t buffer_size,
                         std::string* sender_ip, uint16_t* sender_port) {
    if (sock_ == INVALID_SOCK) return -1;

    struct sockaddr_in from{};
    socklen_t from_len = sizeof(from);

    int n = (int)recvfrom((int)sock_, (char*)buffer, (int)buffer_size, 0,
                          (struct sockaddr*)&from, &from_len);

    if (n > 0) {
        if (sender_ip) {
            char ip_buf[INET_ADDRSTRLEN];
            inet_ntop(AF_INET, &from.sin_addr, ip_buf, sizeof(ip_buf));
            *sender_ip = ip_buf;
        }
        if (sender_port) {
            *sender_port = ntohs(from.sin_port);
        }
    }

    return n;
}

uint16_t UdpSocket::GetLocalPort() const {
    return local_port_;
}

std::string UdpSocket::GetLocalIP() const {
    return local_ip_;
}

void UdpSocket::Close() {
    if (sock_ != INVALID_SOCK) {
        close_sock(sock_);
        sock_ = INVALID_SOCK;
    }
}

bool UdpSocket::IsValid() const {
    return sock_ != INVALID_SOCK;
}

}  // namespace net
}  // namespace agentcp
