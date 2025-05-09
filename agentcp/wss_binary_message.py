# Copyright 2025 AgentUnion Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import struct
import zlib

def encode_wss_binary_message(json_data):
    magic_byte1 = ord('M')
    magic_byte2 = ord('U')
    version = 0x101
    flags = 0
    msg_type = 1
    # 假设 msg_seq 初始为 0，可根据实际情况调整
    msg_seq = 0
    payload = json_data.encode()
    if len(payload) < 512:
        content_type = 1
        compressed = 0
    else:
        content_type = 1
        compressed = 1
        payload = zlib.compress(payload)
    reserved = 0
    crc32 = zlib.crc32(payload)
    payload_length = len(payload)


    header = struct.pack('>BBHIHIBBIII', magic_byte1, magic_byte2, version, flags, msg_type, msg_seq, content_type, compressed, reserved, crc32, payload_length)
    #print(f"Header: {header}")
    #print(f"Payload: {payload}")
    return header + payload


def decode_wss_binary_message(data):
    try:
        magic_byte1, magic_byte2, version, flags, msg_type, msg_seq, content_type, compressed, reserved, crc32, payload_length = struct.unpack('>BBHIHIBBIII', data[:28])
        if magic_byte1 != ord('M') or magic_byte2 != ord('U'):
            return ""
        payload = data[28:]
        if len(payload) != payload_length:
            return ""
        if zlib.crc32(payload) != crc32:
            return ""
        if compressed != 0 and compressed != 1:
            return ""
        if compressed == 1:
            payload = zlib.decompress(payload)
        return payload.decode()
    except (struct.error, zlib.error):
        return ""