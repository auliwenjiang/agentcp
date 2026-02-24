#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace agentcp {
namespace protocol {

// WSS Binary Message header: 28 bytes, big-endian
// struct.pack('>BBHIHIBBIII', ...)
struct WssBinaryHeader {
    uint8_t magic1 = 0x4D;       // 'M'
    uint8_t magic2 = 0x55;       // 'U'
    uint16_t version = 0x0101;
    uint32_t flags = 0;
    uint16_t msg_type = 1;       // 1=JSON, 5=file chunk
    uint32_t msg_seq = 0;
    uint8_t content_type = 1;    // 1=JSON, 5=binary file
    uint8_t compressed = 0;      // 0=no, 1=zlib
    uint32_t reserved = 0;       // for file chunk: file offset
    uint32_t crc32 = 0;
    uint32_t payload_length = 0;

    static constexpr size_t SIZE = 28;
};

// Encode a JSON string into a WSS binary frame
// Automatically compresses if payload >= 512 bytes
std::vector<uint8_t> EncodeWssBinaryMessage(const std::string& json_data, uint32_t msg_seq = 0);

// Decode a WSS binary frame and return the JSON string
// Returns empty string on failure
std::string DecodeWssBinaryMessage(const uint8_t* data, size_t len);
std::string DecodeWssBinaryMessage(const std::vector<uint8_t>& data);

// Encode a raw binary buffer with custom header
std::vector<uint8_t> EncodeWssBinaryBuffer(const uint8_t* payload, size_t payload_len,
                                             const WssBinaryHeader& header);
std::vector<uint8_t> EncodeWssBinaryBuffer(const std::vector<uint8_t>& payload,
                                             const WssBinaryHeader& header);

// Decode a WSS binary buffer and return the header + payload
// Returns false on failure
struct WssBinaryFrame {
    WssBinaryHeader header;
    std::vector<uint8_t> payload;
};

bool DecodeWssBinaryBuffer(const uint8_t* data, size_t len, WssBinaryFrame* out);
bool DecodeWssBinaryBuffer(const std::vector<uint8_t>& data, WssBinaryFrame* out);

}  // namespace protocol
}  // namespace agentcp
