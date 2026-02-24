#pragma once

#include <string>
#include <vector>
#include <cstdint>

namespace agentcp {
namespace protocol {

// Varint encoding/decoding (protobuf-style, little-endian, 7 bits per byte)
std::vector<uint8_t> EncodeVarint(uint64_t value);
uint64_t DecodeVarint(const uint8_t* data, size_t len, size_t* bytes_read);

// UDP Message Header
struct UdpMessageHeader {
    uint64_t message_mask = 0;
    uint64_t message_seq = 0;
    uint16_t message_type = 0;
    uint16_t payload_size = 0;

    std::vector<uint8_t> Serialize() const;
    static UdpMessageHeader Deserialize(const uint8_t* data, size_t len, size_t* offset);
};

// Message types
constexpr uint16_t MSG_TYPE_HEARTBEAT_REQ  = 513;
constexpr uint16_t MSG_TYPE_HEARTBEAT_RESP = 258;
constexpr uint16_t MSG_TYPE_INVITE_REQ     = 259;
constexpr uint16_t MSG_TYPE_INVITE_RESP    = 516;

// HeartbeatMessageReq (type=513): Client -> Server
struct HeartbeatMessageReq {
    UdpMessageHeader header;
    std::string agent_id;
    uint64_t sign_cookie = 0;

    std::vector<uint8_t> Serialize() const;
    static HeartbeatMessageReq Deserialize(const uint8_t* data, size_t len);
};

// HeartbeatMessageResp (type=258): Server -> Client
struct HeartbeatMessageResp {
    UdpMessageHeader header;
    uint64_t next_beat = 0;  // ms; 401 = re-authenticate

    static HeartbeatMessageResp Deserialize(const uint8_t* data, size_t len);
};

// InviteMessageReq (type=259): Server -> Client
struct InviteMessageReq {
    UdpMessageHeader header;
    std::string inviter_agent_id;
    std::string invite_code;
    int64_t invite_code_expire = 0;
    std::string session_id;
    std::string message_server;

    static InviteMessageReq Deserialize(const uint8_t* data, size_t len);
};

// InviteMessageResp (type=516): Client -> Server
struct InviteMessageResp {
    UdpMessageHeader header;
    std::string agent_id;
    std::string inviter_agent_id;
    std::string session_id;
    uint64_t sign_cookie = 0;

    std::vector<uint8_t> Serialize() const;
};

// Helper: encode a length-prefixed string
void WriteVarintString(std::vector<uint8_t>& buf, const std::string& s);

// Helper: decode a length-prefixed string
std::string ReadVarintString(const uint8_t* data, size_t len, size_t* offset);

// Helper: write big-endian uint16
void WriteBE16(std::vector<uint8_t>& buf, uint16_t v);

// Helper: write big-endian uint64
void WriteBE64(std::vector<uint8_t>& buf, uint64_t v);

// Helper: read big-endian uint16
uint16_t ReadBE16(const uint8_t* data);

// Helper: read big-endian uint64
uint64_t ReadBE64(const uint8_t* data);

// Helper: read big-endian int64
int64_t ReadBE64Signed(const uint8_t* data);

}  // namespace protocol
}  // namespace agentcp
