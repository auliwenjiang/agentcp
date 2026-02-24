#include "heartbeat_protocol.h"

#include <cstring>
#include <stdexcept>

namespace agentcp {
namespace protocol {

// ============== Varint ==============

std::vector<uint8_t> EncodeVarint(uint64_t value) {
    std::vector<uint8_t> buf;
    while (value >= 0x80) {
        buf.push_back(static_cast<uint8_t>((value & 0x7F) | 0x80));
        value >>= 7;
    }
    buf.push_back(static_cast<uint8_t>(value));
    return buf;
}

uint64_t DecodeVarint(const uint8_t* data, size_t len, size_t* bytes_read) {
    uint64_t value = 0;
    size_t shift = 0;
    for (size_t i = 0; i < len && i < 10; ++i) {
        value |= (static_cast<uint64_t>(data[i] & 0x7F)) << shift;
        shift += 7;
        if (!(data[i] & 0x80)) {
            if (bytes_read) *bytes_read = i + 1;
            return value;
        }
    }
    if (bytes_read) *bytes_read = 0;
    return 0;
}

// ============== Big-endian helpers ==============

void WriteBE16(std::vector<uint8_t>& buf, uint16_t v) {
    buf.push_back(static_cast<uint8_t>((v >> 8) & 0xFF));
    buf.push_back(static_cast<uint8_t>(v & 0xFF));
}

void WriteBE64(std::vector<uint8_t>& buf, uint64_t v) {
    for (int i = 7; i >= 0; --i) {
        buf.push_back(static_cast<uint8_t>((v >> (i * 8)) & 0xFF));
    }
}

uint16_t ReadBE16(const uint8_t* data) {
    return (static_cast<uint16_t>(data[0]) << 8) | data[1];
}

uint64_t ReadBE64(const uint8_t* data) {
    uint64_t v = 0;
    for (int i = 0; i < 8; ++i) {
        v = (v << 8) | data[i];
    }
    return v;
}

int64_t ReadBE64Signed(const uint8_t* data) {
    uint64_t v = ReadBE64(data);
    int64_t result;
    std::memcpy(&result, &v, sizeof(result));
    return result;
}

// ============== String helpers ==============

void WriteVarintString(std::vector<uint8_t>& buf, const std::string& s) {
    auto len_bytes = EncodeVarint(s.size());
    buf.insert(buf.end(), len_bytes.begin(), len_bytes.end());
    buf.insert(buf.end(), s.begin(), s.end());
}

std::string ReadVarintString(const uint8_t* data, size_t len, size_t* offset) {
    size_t bytes_read = 0;
    uint64_t str_len = DecodeVarint(data + *offset, len - *offset, &bytes_read);
    *offset += bytes_read;
    if (*offset + str_len > len) return {};
    std::string result(reinterpret_cast<const char*>(data + *offset), str_len);
    *offset += str_len;
    return result;
}

// ============== UdpMessageHeader ==============

std::vector<uint8_t> UdpMessageHeader::Serialize() const {
    std::vector<uint8_t> buf;
    auto mask_bytes = EncodeVarint(message_mask);
    buf.insert(buf.end(), mask_bytes.begin(), mask_bytes.end());
    auto seq_bytes = EncodeVarint(message_seq);
    buf.insert(buf.end(), seq_bytes.begin(), seq_bytes.end());
    WriteBE16(buf, message_type);
    WriteBE16(buf, payload_size);
    return buf;
}

UdpMessageHeader UdpMessageHeader::Deserialize(const uint8_t* data, size_t len, size_t* offset) {
    UdpMessageHeader h;
    size_t bytes_read = 0;

    h.message_mask = DecodeVarint(data + *offset, len - *offset, &bytes_read);
    *offset += bytes_read;

    h.message_seq = DecodeVarint(data + *offset, len - *offset, &bytes_read);
    *offset += bytes_read;

    if (*offset + 4 > len) return h;
    h.message_type = ReadBE16(data + *offset);
    *offset += 2;
    h.payload_size = ReadBE16(data + *offset);
    *offset += 2;

    return h;
}

// ============== HeartbeatMessageReq ==============

std::vector<uint8_t> HeartbeatMessageReq::Serialize() const {
    auto buf = header.Serialize();
    WriteVarintString(buf, agent_id);
    WriteBE64(buf, sign_cookie);
    return buf;
}

HeartbeatMessageReq HeartbeatMessageReq::Deserialize(const uint8_t* data, size_t len) {
    HeartbeatMessageReq req;
    size_t offset = 0;
    req.header = UdpMessageHeader::Deserialize(data, len, &offset);
    req.agent_id = ReadVarintString(data, len, &offset);
    if (offset + 8 <= len) {
        req.sign_cookie = ReadBE64(data + offset);
        offset += 8;
    }
    return req;
}

// ============== HeartbeatMessageResp ==============

HeartbeatMessageResp HeartbeatMessageResp::Deserialize(const uint8_t* data, size_t len) {
    HeartbeatMessageResp resp;
    size_t offset = 0;
    resp.header = UdpMessageHeader::Deserialize(data, len, &offset);
    if (offset + 8 <= len) {
        resp.next_beat = ReadBE64(data + offset);
        offset += 8;
    }
    return resp;
}

// ============== InviteMessageReq ==============

InviteMessageReq InviteMessageReq::Deserialize(const uint8_t* data, size_t len) {
    InviteMessageReq req;
    size_t offset = 0;
    req.header = UdpMessageHeader::Deserialize(data, len, &offset);
    req.inviter_agent_id = ReadVarintString(data, len, &offset);
    req.invite_code = ReadVarintString(data, len, &offset);
    if (offset + 8 <= len) {
        req.invite_code_expire = ReadBE64Signed(data + offset);
        offset += 8;
    }
    req.session_id = ReadVarintString(data, len, &offset);
    req.message_server = ReadVarintString(data, len, &offset);
    return req;
}

// ============== InviteMessageResp ==============

std::vector<uint8_t> InviteMessageResp::Serialize() const {
    auto buf = header.Serialize();
    WriteVarintString(buf, agent_id);
    WriteVarintString(buf, inviter_agent_id);
    WriteVarintString(buf, session_id);
    WriteBE64(buf, sign_cookie);
    return buf;
}

}  // namespace protocol
}  // namespace agentcp
