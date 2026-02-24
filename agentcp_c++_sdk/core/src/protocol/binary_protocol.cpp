#include "binary_protocol.h"

#include <cstring>

#if AGENTCP_USE_ZLIB
#include <zlib.h>
#endif

namespace agentcp {
namespace protocol {

namespace {

void WriteBE16(std::vector<uint8_t>& buf, uint16_t v) {
    buf.push_back(static_cast<uint8_t>((v >> 8) & 0xFF));
    buf.push_back(static_cast<uint8_t>(v & 0xFF));
}

void WriteBE32(std::vector<uint8_t>& buf, uint32_t v) {
    buf.push_back(static_cast<uint8_t>((v >> 24) & 0xFF));
    buf.push_back(static_cast<uint8_t>((v >> 16) & 0xFF));
    buf.push_back(static_cast<uint8_t>((v >> 8) & 0xFF));
    buf.push_back(static_cast<uint8_t>(v & 0xFF));
}

uint16_t ReadBE16(const uint8_t* p) {
    return (static_cast<uint16_t>(p[0]) << 8) | p[1];
}

uint32_t ReadBE32(const uint8_t* p) {
    return (static_cast<uint32_t>(p[0]) << 24) |
           (static_cast<uint32_t>(p[1]) << 16) |
           (static_cast<uint32_t>(p[2]) << 8) |
           static_cast<uint32_t>(p[3]);
}

// CRC32 implementation
#if AGENTCP_USE_ZLIB

uint32_t ComputeCRC32(const uint8_t* data, size_t len) {
    return static_cast<uint32_t>(crc32(0L, data, static_cast<uInt>(len)));
}

std::vector<uint8_t> ZlibCompress(const uint8_t* data, size_t len) {
    std::vector<uint8_t> out;
    uLongf dest_len = compressBound(static_cast<uLong>(len));
    out.resize(dest_len);
    if (compress(out.data(), &dest_len, data, static_cast<uLong>(len)) != Z_OK) {
        return {};
    }
    out.resize(dest_len);
    return out;
}

std::vector<uint8_t> ZlibDecompress(const uint8_t* data, size_t len) {
    std::vector<uint8_t> out;
    uLongf dest_len = static_cast<uLongf>(len * 4);
    if (dest_len < 1024) dest_len = 1024;

    for (int attempt = 0; attempt < 5; ++attempt) {
        out.resize(dest_len);
        int ret = uncompress(out.data(), &dest_len, data, static_cast<uLong>(len));
        if (ret == Z_OK) {
            out.resize(dest_len);
            return out;
        } else if (ret == Z_BUF_ERROR) {
            dest_len *= 2;
            continue;
        } else {
            return {};
        }
    }
    return {};
}

#else  // !AGENTCP_USE_ZLIB

// Simple CRC32 without zlib
static const uint32_t crc32_table[256] = {
    0x00000000,0x77073096,0xEE0E612C,0x990951BA,0x076DC419,0x706AF48F,0xE963A535,0x9E6495A3,
    0x0EDB8832,0x79DCB8A4,0xE0D5E91B,0x97D2D988,0x09B64C2B,0x7EB17CBE,0xE7B82D09,0x90BF1D9F,
    0x1DB71064,0x6AB020F2,0xF3B97148,0x84BE41DE,0x1ADAD47D,0x6DDDE4EB,0xF4D4B551,0x83D385C7,
    0x136C9856,0x646BA8C0,0xFD62F97A,0x8A65C9EC,0x14015C4F,0x63066CD9,0xFA0F3D63,0x8D080DF5,
    0x3B6E20C8,0x4C69105E,0xD56041E4,0xA2677172,0x3C03E4D1,0x4B04D447,0xD20D85FD,0xA50AB56B,
    0x35B5A8FA,0x42B2986C,0xDBBBC9D6,0xACBCF940,0x32D86CE3,0x45DF5C75,0xDCD60DCF,0xABD13D59,
    0x26D930AC,0x51DE003A,0xC8D75180,0xBFD06116,0x21B4F0B5,0x56B3C423,0xCFBA9599,0xB8BDA50F,
    0x2802B89E,0x5F058808,0xC60CD9B2,0xB10BE924,0x2F6F7C87,0x58684C11,0xC1611DAB,0xB6662D3D,
    0x76DC4190,0x01DB7106,0x98D220BC,0xEFD5102A,0x71B18589,0x06B6B51F,0x9FBFE4A5,0xE8B8D433,
    0x7807C9A2,0x0F00F934,0x9609A88E,0xE10E9818,0x7F6A0DBB,0x086D3D2D,0x91646C97,0xE6635C01,
    0x6B6B51F4,0x1C6C6162,0x856530D8,0xF262004E,0x6C0695ED,0x1B01A57B,0x8208F4C1,0xF50FC457,
    0x65B0D9C6,0x12B7E950,0x8BBEB8EA,0xFCB9887C,0x62DD1DDF,0x15DA2D49,0x8CD37CF3,0xFBD44C65,
    0x4DB26158,0x3AB551CE,0xA3BC0074,0xD4BB30E2,0x4ADFA541,0x3DD895D7,0xA4D1C46D,0xD3D6F4FB,
    0x4369E96A,0x346ED9FC,0xAD678846,0xDA60B8D0,0x44042D73,0x33031DE5,0xAA0A4C5F,0xDD0D7822,
    0x5005713C,0x270241AA,0xBE0B1010,0xC90C2086,0x5768B525,0x206F85B3,0xB966D409,0xCE61E49F,
    0x5EDEF90E,0x29D9C998,0xB0D09822,0xC7D7A8B4,0x59B33D17,0x2EB40D81,0xB7BD5C3B,0xC0BA6CAD,
    0xEDB88320,0x9ABFB3B6,0x03B6E20C,0x74B1D29A,0xEAD54739,0x9DD277AF,0x04DB2615,0x73DC1683,
    0xE3630B12,0x94643B84,0x0D6D6A3E,0x7A6A5ACE,0xEE0E363F,0x990F0609,0x00060C0F,0x7701049D,
    0xE0010177,0x97063114,0x0E0F6008,0x710F5050,0xE7097BA7,0x90064B31,0x09077B8B,0x7E006C1D,
    0xED6669C0,0x9A616A56,0x036A1BEC,0x746D0B7A,0xEA237A85,0x9D202013,0x04293F57,0x73263EC1,
    0xE4C11DB7,0x93C42D21,0x0AC4759B,0x7DC3450D,0xE3077AEE,0x94001478,0x0D0945C2,0x7A0E3554,
    0xED063D8A,0x9A011A1C,0x030812A6,0x74052230,0xEA416D93,0x9D405D05,0x0449D4BF,0x734E4429,
    0xA9501698,0xDE57260E,0x477E77B4,0x30794722,0xAE3D3681,0xD93A0617,0x405B57AD,0x3758673B,
    0xA7E1F0AA,0xD0E6C03C,0x47EFB186,0x30E88110,0xAE0CF4B3,0xD90BE425,0x400CB59F,0x370CAE09,
    0xBA03A5FC,0xCD04956A,0x540DC4D0,0x23091B46,0xBD6D88E5,0xCA6AB873,0x536DE9C9,0x2464D85F,
    0xB4D3CBCE,0xC3D4FB58,0x5ADDA8E2,0x2DD2B874,0xB3B6CCDD,0xC4B1BC4B,0x5DB8ACF1,0x2ABF9C67,
    0xDBD7BE81,0xACCDA117,0x35C460AD,0x42C3503B,0xDCC37298,0xABB2420E,0x32B939B4,0x45BE0922,
    0xD5B14AB3,0xA2B67A25,0x3BBF2B9F,0x4CB81B09,0xD2F8ECAA,0xA5FF7C3C,0x3CF68686,0x4BF1B610,
    0xB86D70E5,0xCF6A0073,0x5863B1C9,0x2F64815F,0xB100E4FC,0xC607D46A,0x5F0EE5D0,0x280E9546,
    0xB801C2D7,0xCF06B241,0x580FE3FB,0x2F08D36D,0xB10BC0CE,0xC60C5058,0x5F058CE2,0x28020A74,
    0xC1CDEE0D,0xB6CAD09B,0x2FC39121,0x58C4A1B7,0xC6A0B614,0xB1A78682,0x28AED738,0x5FA9E7AE,
    0xCF10FA3F,0xB817CAA9,0x21109B13,0x5617AB85,0xC87B6E26,0xBF7C5EB0,0x267B0F0A,0x517C3F9C
};

uint32_t ComputeCRC32(const uint8_t* data, size_t len) {
    uint32_t crc = 0xFFFFFFFF;
    for (size_t i = 0; i < len; ++i) {
        crc = crc32_table[(crc ^ data[i]) & 0xFF] ^ (crc >> 8);
    }
    return crc ^ 0xFFFFFFFF;
}

std::vector<uint8_t> ZlibCompress(const uint8_t*, size_t) {
    return {};  // compression not available without zlib
}

std::vector<uint8_t> ZlibDecompress(const uint8_t*, size_t) {
    return {};  // decompression not available without zlib
}

#endif  // AGENTCP_USE_ZLIB

void SerializeHeader(std::vector<uint8_t>& buf, const WssBinaryHeader& h) {
    buf.push_back(h.magic1);
    buf.push_back(h.magic2);
    WriteBE16(buf, h.version);
    WriteBE32(buf, h.flags);
    WriteBE16(buf, h.msg_type);
    WriteBE32(buf, h.msg_seq);
    buf.push_back(h.content_type);
    buf.push_back(h.compressed);
    WriteBE32(buf, h.reserved);
    WriteBE32(buf, h.crc32);
    WriteBE32(buf, h.payload_length);
}

bool DeserializeHeader(const uint8_t* data, WssBinaryHeader* h) {
    h->magic1 = data[0];
    h->magic2 = data[1];
    h->version = ReadBE16(data + 2);
    h->flags = ReadBE32(data + 4);
    h->msg_type = ReadBE16(data + 8);
    h->msg_seq = ReadBE32(data + 10);
    h->content_type = data[14];
    h->compressed = data[15];
    h->reserved = ReadBE32(data + 16);
    h->crc32 = ReadBE32(data + 20);
    h->payload_length = ReadBE32(data + 24);
    return true;
}

}  // anonymous namespace

std::vector<uint8_t> EncodeWssBinaryMessage(const std::string& json_data, uint32_t msg_seq) {
    WssBinaryHeader header;
    header.msg_type = 1;
    header.msg_seq = msg_seq;
    header.content_type = 1;

    std::vector<uint8_t> payload(json_data.begin(), json_data.end());

#if AGENTCP_USE_ZLIB
    if (payload.size() >= 512) {
        header.compressed = 1;
        payload = ZlibCompress(payload.data(), payload.size());
        if (payload.empty()) return {};
    } else {
        header.compressed = 0;
    }
#else
    header.compressed = 0;
#endif

    header.crc32 = ComputeCRC32(payload.data(), payload.size());
    header.payload_length = static_cast<uint32_t>(payload.size());

    std::vector<uint8_t> result;
    result.reserve(WssBinaryHeader::SIZE + payload.size());
    SerializeHeader(result, header);
    result.insert(result.end(), payload.begin(), payload.end());
    return result;
}

std::string DecodeWssBinaryMessage(const uint8_t* data, size_t len) {
    if (len < WssBinaryHeader::SIZE) return {};

    WssBinaryHeader header;
    DeserializeHeader(data, &header);

    if (header.magic1 != 0x4D || header.magic2 != 0x55) return {};

    const uint8_t* payload = data + WssBinaryHeader::SIZE;
    size_t payload_len = len - WssBinaryHeader::SIZE;

    if (payload_len != header.payload_length) return {};

    // CRC32 check
    uint32_t computed_crc = ComputeCRC32(payload, payload_len);
    if (computed_crc != header.crc32) return {};

    if (header.compressed != 0 && header.compressed != 1) return {};

    if (header.compressed == 1) {
        auto decompressed = ZlibDecompress(payload, payload_len);
        if (decompressed.empty()) return {};
        return std::string(decompressed.begin(), decompressed.end());
    }

    return std::string(reinterpret_cast<const char*>(payload), payload_len);
}

std::string DecodeWssBinaryMessage(const std::vector<uint8_t>& data) {
    return DecodeWssBinaryMessage(data.data(), data.size());
}

std::vector<uint8_t> EncodeWssBinaryBuffer(const uint8_t* payload, size_t payload_len,
                                             const WssBinaryHeader& header_in) {
    WssBinaryHeader h = header_in;
    h.magic1 = 0x4D;
    h.magic2 = 0x55;
    h.crc32 = ComputeCRC32(payload, payload_len);
    h.payload_length = static_cast<uint32_t>(payload_len);

    std::vector<uint8_t> result;
    result.reserve(WssBinaryHeader::SIZE + payload_len);
    SerializeHeader(result, h);
    result.insert(result.end(), payload, payload + payload_len);
    return result;
}

std::vector<uint8_t> EncodeWssBinaryBuffer(const std::vector<uint8_t>& payload,
                                             const WssBinaryHeader& header) {
    return EncodeWssBinaryBuffer(payload.data(), payload.size(), header);
}

bool DecodeWssBinaryBuffer(const uint8_t* data, size_t len, WssBinaryFrame* out) {
    if (len < WssBinaryHeader::SIZE) return false;

    DeserializeHeader(data, &out->header);

    if (out->header.magic1 != 0x4D || out->header.magic2 != 0x55) return false;

    const uint8_t* payload = data + WssBinaryHeader::SIZE;
    size_t payload_len = len - WssBinaryHeader::SIZE;

    if (payload_len != out->header.payload_length) return false;

    uint32_t computed_crc = ComputeCRC32(payload, payload_len);
    if (computed_crc != out->header.crc32) return false;

    if (out->header.compressed == 1) {
        out->payload = ZlibDecompress(payload, payload_len);
        if (out->payload.empty()) return false;
    } else {
        out->payload.assign(payload, payload + payload_len);
    }

    return true;
}

bool DecodeWssBinaryBuffer(const std::vector<uint8_t>& data, WssBinaryFrame* out) {
    return DecodeWssBinaryBuffer(data.data(), data.size(), out);
}

}  // namespace protocol
}  // namespace agentcp
