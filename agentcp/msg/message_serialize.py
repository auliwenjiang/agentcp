# -*- coding: utf-8 -*-
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
import io
from typing import Tuple


def uint64_to_varint(v: int) -> bytes:
    buf = b''
    while v >= 0x80:
        buf += bytes([v & 0x7F | 0x80])
        v >>= 7
    buf += bytes([v])
    return buf

def varint_to_uint64(buf: bytes) -> Tuple[int, int]:
    v = 0
    shift = 0
    for i, b in enumerate(buf):
        v |= (b & 0x7F) << shift
        shift += 7
        if not (b & 0x80):
            return v, i + 1
    raise ValueError("Invalid varint")

class UdpMessageHeader:
    def __init__(self):
        self.MessageMask: int = 0
        self.MessageSeq: int = 0
        self.MessageType: int = 0
        self.PayloadSize: int = 0
    
    def serialize(self, buf: io.BytesIO) -> None:
        buf.write(uint64_to_varint(self.MessageMask))
        buf.write(uint64_to_varint(self.MessageSeq))
        buf.write(self.MessageType.to_bytes(2, 'big'))
        buf.write(self.PayloadSize.to_bytes(2, 'big'))
    
    @classmethod
    def deserialize(cls, buf: bytes, offset: int) -> Tuple['UdpMessageHeader', int]:
        obj = cls()
        obj.MessageMask, read = varint_to_uint64(buf[offset:])
        offset += read
        obj.MessageSeq, read = varint_to_uint64(buf[offset:])
        offset += read
        obj.MessageType = int.from_bytes(buf[offset:offset+2], 'big')
        offset += 2
        obj.PayloadSize = int.from_bytes(buf[offset:offset+2], 'big')
        offset += 2
        return obj, offset

# ================== HeartbeatMessageReq ==================
class HeartbeatMessageReq:
    def __init__(self):
        self.header = UdpMessageHeader()
        self.AgentId: str = ""
        self.SignCookie: int = 0
    
    def serialize(self, buf: io.BytesIO) -> None:
        self.header.serialize(buf)
        agent_id_bytes = self.AgentId.encode('utf-8')
        buf.write(uint64_to_varint(len(agent_id_bytes)))
        buf.write(agent_id_bytes)
        buf.write(self.SignCookie.to_bytes(8, 'big'))
    
    @classmethod
    def deserialize(cls, buf: bytes, offset: int) -> Tuple['HeartbeatMessageReq', int]:
        obj = cls()
        obj.header, offset = UdpMessageHeader.deserialize(buf, offset)
        len_agent_id, read = varint_to_uint64(buf[offset:])
        offset += read
        obj.AgentId = buf[offset:offset+int(len_agent_id)].decode('utf-8')
        offset += int(len_agent_id)
        obj.SignCookie = int.from_bytes(buf[offset:offset+8], 'big')
        offset += 8
        return obj, offset

# ================== HeartbeatMessageResp ==================
class HeartbeatMessageResp:
    def __init__(self):
        self.header = UdpMessageHeader()
        self.NextBeat: int = 0
    
    def serialize(self, buf: io.BytesIO) -> None:
        self.header.serialize(buf)
        buf.write(self.NextBeat.to_bytes(8, 'big'))
    
    @classmethod
    def deserialize(cls, buf: bytes, offset: int) -> Tuple['HeartbeatMessageResp', int]:
        obj = cls()
        obj.header, offset = UdpMessageHeader.deserialize(buf, offset)
        obj.NextBeat = int.from_bytes(buf[offset:offset+8], 'big')
        offset += 8
        return obj, offset

# ================== InviteMessageReq ==================
class InviteMessageReq:
    def __init__(self):
        self.header = UdpMessageHeader()
        self.InviterAgentId: str = ""
        self.InviteCode: str = ""
        self.InviteCodeExpire: int = 0
        self.SessionId: str = ""
        self.MessageServer: str = ""

    def serialize(self, buf: io.BytesIO) -> None:
        self.header.serialize(buf)
        # 序列化 InviterAgentId
        inviter_bytes = self.InviterAgentId.encode('utf-8')
        buf.write(uint64_to_varint(len(inviter_bytes)))
        buf.write(inviter_bytes)
        # 序列化 InviteCode
        invite_code_bytes = self.InviteCode.encode('utf-8')
        buf.write(uint64_to_varint(len(invite_code_bytes)))
        buf.write(invite_code_bytes)
        # 序列化 InviteCodeExpire（int64 转换为 uint64 处理）
        buf.write(uint64_to_varint(abs(self.InviteCodeExpire)) if self.InviteCodeExpire < 0 else self.InviteCodeExpire.to_bytes(8, 'big'))
        # 更准确的处理：直接按 int64 字节处理
        buf.write(self.InviteCodeExpire.to_bytes(8, 'big', signed=True))
        # 序列化 SessionId
        session_id_bytes = self.SessionId.encode('utf-8')
        buf.write(uint64_to_varint(len(session_id_bytes)))
        buf.write(session_id_bytes)
        # 序列化MessageServer
        message_server_bytes = self.MessageServer.encode("utf-8")
        buf.write(uint64_to_varint(len(message_server_bytes)))
        buf.write(message_server_bytes)

    @classmethod
    def deserialize(cls, buf: bytes, offset: int) -> Tuple['InviteMessageReq', int]:
        obj = cls()
        obj.header, offset = UdpMessageHeader.deserialize(buf, offset)
        # 反序列化 InviterAgentId
        len_inviter, read = varint_to_uint64(buf[offset:])
        offset += read
        obj.InviterAgentId = buf[offset:offset+int(len_inviter)].decode('utf-8')
        offset += int(len_inviter)
        # 反序列化 InviteCode
        len_invite_code, read = varint_to_uint64(buf[offset:])
        offset += read
        obj.InviteCode = buf[offset:offset+int(len_invite_code)].decode('utf-8')
        offset += int(len_invite_code)
        # 反序列化 InviteCodeExpire
        obj.InviteCodeExpire = int.from_bytes(buf[offset:offset+8], 'big', signed=True)
        offset += 8
        # 反序列化 SessionId
        len_session_id, read = varint_to_uint64(buf[offset:])
        offset += read
        obj.SessionId = buf[offset:offset+int(len_session_id)].decode('utf-8')
        offset += int(len_session_id)
        # 反序列化MessageServer
        len_message_server, read = varint_to_uint64(buf[offset:])
        offset += read
        obj.MessageServer = buf[offset:offset+int(len_message_server)].decode('utf-8')
        offset += int(len_message_server)
        return obj, offset

# ================== InviteMessageResp ==================
class InviteMessageResp:
    def __init__(self):
        self.header = UdpMessageHeader()
        self.AgentId: str = ""
        self.SignCookie: int = 0
        self.InviterAgentId: str = ""
        self.SessionId: str = ""
    
    def serialize(self, buf: io.BytesIO) -> None:
        self.header.serialize(buf)
        agent_id_bytes = self.AgentId.encode('utf-8')
        buf.write(uint64_to_varint(len(agent_id_bytes)))
        buf.write(agent_id_bytes)
        inviter_agent_id_bytes = self.InviterAgentId.encode('utf-8')
        buf.write(uint64_to_varint(len(inviter_agent_id_bytes)))
        buf.write(inviter_agent_id_bytes)
        session_id_bytes = self.SessionId.encode('utf-8')
        buf.write(uint64_to_varint(len(session_id_bytes)))
        buf.write(session_id_bytes)
        buf.write(self.SignCookie.to_bytes(8, 'big'))
    
    @classmethod
    def deserialize(cls, buf: bytes, offset: int) -> Tuple['InviteMessageResp', int]:
        obj = cls()
        obj.header, offset = UdpMessageHeader.deserialize(buf, offset)
        len_agent_id, read = varint_to_uint64(buf[offset:])
        offset += read
        obj.AgentId = buf[offset:offset+int(len_agent_id)].decode('utf-8')
        offset += int(len_agent_id)
        len_inviter_agent_id, read = varint_to_uint64(buf[offset:])
        offset += read
        obj.InviterAgentId = buf[offset:offset+int(len_inviter_agent_id)].decode('utf-8')
        offset += int(len_inviter_agent_id)
        len_session_id, read = varint_to_uint64(buf[offset:])
        offset += read
        obj.SessionId = buf[offset:offset+int(len_session_id)].decode('utf-8')
        offset += int(len_session_id)
        obj.SignCookie = int.from_bytes(buf[offset:offset+8], 'big')
        offset += 8
        return obj, offset

if __name__ == "__main__":
    # 测试 HeartbeatMessageReq
    req = HeartbeatMessageReq()
    req.header.MessageMask = 1
    req.header.MessageSeq = 2
    req.header.MessageType = 3
    req.header.PayloadSize = 100
    req.AgentId = "agent-1"
    req.SignCookie = 12345
    buf = io.BytesIO()
    req.serialize(buf)
    data = buf.getvalue()
    deser_req, _ = HeartbeatMessageReq.deserialize(data, 0)
    
    # 测试 HeartbeatMessageResp
    resp = HeartbeatMessageResp()
    resp.header.MessageMask = 4
    resp.header.MessageSeq = 5
    resp.header.MessageType = 4
    resp.header.PayloadSize = 8
    resp.NextBeat = 60000
    buf = io.BytesIO()
    resp.serialize(buf)
    data = buf.getvalue()
    deser_resp, _ = HeartbeatMessageResp.deserialize(data, 0)
    
    # 测试 InviteMessageReq
    invite_req = InviteMessageReq()
    invite_req.header.MessageMask = 6
    invite_req.header.MessageSeq = 7
    invite_req.header.MessageType = 5
    invite_req.header.PayloadSize = 200
    invite_req.InviterAgentId = "inviter-1"
    invite_req.InviteCode = "CODE123"
    invite_req.InviteCodeExpire = 1680000000
    invite_req.SessionId = "session-1"
    buf = io.BytesIO()
    invite_req.serialize(buf)
    data = buf.getvalue()
    deser_invite_req, _ = InviteMessageReq.deserialize(data, 0)
    
    # 测试 InviteMessageResp
    invite_resp = InviteMessageResp()
    invite_resp.header.MessageMask = 8
    invite_resp.header.MessageSeq = 9
    invite_resp.header.MessageType = 6
    invite_resp.header.PayloadSize = 150
    invite_resp.AgentId = "resp-agent"
    invite_resp.SignCookie = 98765
    buf = io.BytesIO()
    invite_resp.serialize(buf)
    data = buf.getvalue()
    deser_invite_resp, _ = InviteMessageResp.deserialize(data, 0)
