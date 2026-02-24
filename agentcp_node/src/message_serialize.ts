/**
 * UDP 消息序列化/反序列化工具
 * 与 Python 端的 message_serialize.py 保持一致
 */

// Varint 编码
export function uint64ToVarint(v: number): Buffer {
    const bytes: number[] = [];
    while (v >= 0x80) {
        bytes.push((v & 0x7F) | 0x80);
        v = Math.floor(v / 128);
    }
    bytes.push(v);
    return Buffer.from(bytes);
}

// Varint 解码（带边界检查）
export function varintToUint64(buf: Buffer, offset: number): { value: number; bytesRead: number } {
    let v = 0;
    let shift = 0;
    let bytesRead = 0;
    const maxBytes = 10; // 64位整数最多需要10字节varint

    for (let i = offset; i < buf.length && bytesRead < maxBytes; i++) {
        const b = buf[i];
        v |= (b & 0x7F) << shift;
        shift += 7;
        bytesRead++;
        if (!(b & 0x80)) {
            return { value: v, bytesRead };
        }
    }
    throw new Error(`Invalid varint at offset ${offset}`);
}

// 64位整数编码为 8 字节 big-endian
function encode64BitInt(value: number): Buffer {
    const buffer = Buffer.alloc(8);
    const high = Math.floor(value / 0x100000000);
    const low = value >>> 0;
    buffer.writeUInt32BE(high, 0);
    buffer.writeUInt32BE(low, 4);
    return buffer;
}

// 从 8 字节 big-endian 解码 64 位整数
function decode64BitInt(buf: Buffer, offset: number): number {
    const high = buf.readUInt32BE(offset);
    const low = buf.readUInt32BE(offset + 4);
    return high * 0x100000000 + low;
}

// 从 8 字节 big-endian 解码 64 位有符号整数
function decode64BitSignedInt(buf: Buffer, offset: number): number {
    const high = buf.readInt32BE(offset);
    const low = buf.readUInt32BE(offset + 4);
    return high * 0x100000000 + low;
}

// UDP 消息头
export class UdpMessageHeader {
    MessageMask: number = 0;
    MessageSeq: number = 0;
    MessageType: number = 0;
    PayloadSize: number = 0;

    serialize(): Buffer {
        const parts: Buffer[] = [];
        parts.push(uint64ToVarint(this.MessageMask));
        parts.push(uint64ToVarint(this.MessageSeq));

        // MessageType: 2 bytes big-endian
        const typeBuffer = Buffer.alloc(2);
        typeBuffer.writeUInt16BE(this.MessageType, 0);
        parts.push(typeBuffer);

        // PayloadSize: 2 bytes big-endian
        const sizeBuffer = Buffer.alloc(2);
        sizeBuffer.writeUInt16BE(this.PayloadSize, 0);
        parts.push(sizeBuffer);

        return Buffer.concat(parts);
    }

    static deserialize(buf: Buffer, offset: number): { header: UdpMessageHeader; offset: number } {
        const header = new UdpMessageHeader();

        let result = varintToUint64(buf, offset);
        header.MessageMask = result.value;
        offset += result.bytesRead;

        result = varintToUint64(buf, offset);
        header.MessageSeq = result.value;
        offset += result.bytesRead;

        header.MessageType = buf.readUInt16BE(offset);
        offset += 2;

        header.PayloadSize = buf.readUInt16BE(offset);
        offset += 2;

        return { header, offset };
    }
}

// 心跳请求消息
export class HeartbeatMessageReq {
    header: UdpMessageHeader = new UdpMessageHeader();
    AgentId: string = '';
    SignCookie: number = 0;

    serialize(): Buffer {
        const parts: Buffer[] = [];
        parts.push(this.header.serialize());

        // AgentId: varint length + utf8 bytes
        const agentIdBytes = Buffer.from(this.AgentId, 'utf-8');
        parts.push(uint64ToVarint(agentIdBytes.length));
        parts.push(agentIdBytes);

        // SignCookie: 8 bytes big-endian
        parts.push(encode64BitInt(this.SignCookie));

        return Buffer.concat(parts);
    }

    static deserialize(buf: Buffer, offset: number): { req: HeartbeatMessageReq; offset: number } {
        const req = new HeartbeatMessageReq();

        const headerResult = UdpMessageHeader.deserialize(buf, offset);
        req.header = headerResult.header;
        offset = headerResult.offset;

        const lenResult = varintToUint64(buf, offset);
        offset += lenResult.bytesRead;

        req.AgentId = buf.slice(offset, offset + lenResult.value).toString('utf-8');
        offset += lenResult.value;

        req.SignCookie = decode64BitInt(buf, offset);
        offset += 8;

        return { req, offset };
    }
}

// 心跳响应消息
export class HeartbeatMessageResp {
    header: UdpMessageHeader = new UdpMessageHeader();
    NextBeat: number = 0;

    static deserialize(buf: Buffer, offset: number): { resp: HeartbeatMessageResp; offset: number } {
        const resp = new HeartbeatMessageResp();

        const headerResult = UdpMessageHeader.deserialize(buf, offset);
        resp.header = headerResult.header;
        offset = headerResult.offset;

        // NextBeat 是 varint 编码，不是固定 8 字节
        const nextBeatResult = varintToUint64(buf, offset);
        resp.NextBeat = nextBeatResult.value;
        offset += nextBeatResult.bytesRead;

        return { resp, offset };
    }
}

// 邀请请求消息
export class InviteMessageReq {
    header: UdpMessageHeader = new UdpMessageHeader();
    InviterAgentId: string = '';
    InviteCode: string = '';
    InviteCodeExpire: number = 0;
    SessionId: string = '';
    MessageServer: string = '';

    static deserialize(buf: Buffer, offset: number): { req: InviteMessageReq; offset: number } {
        const req = new InviteMessageReq();

        const headerResult = UdpMessageHeader.deserialize(buf, offset);
        req.header = headerResult.header;
        offset = headerResult.offset;

        // InviterAgentId
        let lenResult = varintToUint64(buf, offset);
        offset += lenResult.bytesRead;
        req.InviterAgentId = buf.slice(offset, offset + lenResult.value).toString('utf-8');
        offset += lenResult.value;

        // InviteCode
        lenResult = varintToUint64(buf, offset);
        offset += lenResult.bytesRead;
        req.InviteCode = buf.slice(offset, offset + lenResult.value).toString('utf-8');
        offset += lenResult.value;

        // InviteCodeExpire (8 bytes, signed)
        req.InviteCodeExpire = decode64BitSignedInt(buf, offset);
        offset += 8;

        // SessionId
        lenResult = varintToUint64(buf, offset);
        offset += lenResult.bytesRead;
        req.SessionId = buf.slice(offset, offset + lenResult.value).toString('utf-8');
        offset += lenResult.value;

        // MessageServer
        lenResult = varintToUint64(buf, offset);
        offset += lenResult.bytesRead;
        req.MessageServer = buf.slice(offset, offset + lenResult.value).toString('utf-8');
        offset += lenResult.value;

        return { req, offset };
    }
}

// 邀请响应消息
export class InviteMessageResp {
    header: UdpMessageHeader = new UdpMessageHeader();
    AgentId: string = '';
    InviterAgentId: string = '';
    SessionId: string = '';
    SignCookie: number = 0;

    serialize(): Buffer {
        const parts: Buffer[] = [];
        parts.push(this.header.serialize());

        // AgentId
        const agentIdBytes = Buffer.from(this.AgentId, 'utf-8');
        parts.push(uint64ToVarint(agentIdBytes.length));
        parts.push(agentIdBytes);

        // InviterAgentId
        const inviterBytes = Buffer.from(this.InviterAgentId, 'utf-8');
        parts.push(uint64ToVarint(inviterBytes.length));
        parts.push(inviterBytes);

        // SessionId
        const sessionBytes = Buffer.from(this.SessionId, 'utf-8');
        parts.push(uint64ToVarint(sessionBytes.length));
        parts.push(sessionBytes);

        // SignCookie: 8 bytes big-endian
        parts.push(encode64BitInt(this.SignCookie));

        return Buffer.concat(parts);
    }
}

// 消息类型常量
export const MessageType = {
    HEARTBEAT_REQ: 513,   // 心跳请求
    HEARTBEAT_RESP: 258,  // 心跳响应
    INVITE_REQ: 259,      // 邀请请求
    INVITE_RESP: 516,     // 邀请响应
};
