# Protocols

This document describes the client-side protocol requirements based on the existing AP AID system.

## 1. AP Authentication
Endpoint base:
- {ap_base}/api/accesspoint

### sign_in Step 1 (challenge)
POST {ap_base}/api/accesspoint/sign_in

Request:
```json
{
  "agent_id": "alice.ap.example.com",
  "request_id": "550e8400e29b41d4a716446655440000"
}
```

Response (Success):
```json
{
  "nonce": "a1b2c3d4e5f6...",
  "cert": "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----",
  "signature": "3045022100..."
}
```

Response (Error):
```json
{
  "error": {
    "code": "AGENT_NOT_FOUND",
    "message": "Agent ID not registered"
  }
}
```

### sign_in Step 2 (proof)
POST {ap_base}/api/accesspoint/sign_in

If nonce exists, client signs the nonce with its private key:
Request:
```json
{
  "agent_id": "alice.ap.example.com",
  "request_id": "550e8400e29b41d4a716446655440000",
  "nonce": "a1b2c3d4e5f6...",
  "public_key": "-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----",
  "cert": "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----",
  "signature": "3046022100..."
}
```

Response (Success):
```json
{
  "signature": "eyJhbGciOiJFUzM4NCIsInR5cCI6IkpXVCJ9..."
}
```

Response (Error):
```json
{
  "error": {
    "code": "INVALID_SIGNATURE",
    "message": "Signature verification failed"
  }
}
```

### get_accesspoint_config
POST {ap_base}/api/accesspoint/get_accesspoint_config

Request:
```json
{
  "agent_id": "alice.ap.example.com",
  "signature": "eyJhbGciOiJFUzM4NCIsInR5cCI6IkpXVCJ9..."
}
```

Response (Success):
```json
{
  "config": {
    "heartbeat_server": "https://hb.example.com",
    "message_server": "wss://msg.example.com"
  }
}
```

Response (Error):
```json
{
  "error": {
    "code": "UNAUTHORIZED",
    "message": "Invalid or expired signature"
  }
}
```

### Error Codes (AP)
| Code | HTTP Status | Description | Retry |
|------|-------------|-------------|-------|
| AGENT_NOT_FOUND | 404 | Agent ID not registered | No |
| INVALID_SIGNATURE | 401 | Signature verification failed | No |
| UNAUTHORIZED | 401 | Token expired or invalid | Re-auth |
| RATE_LIMIT_EXCEEDED | 429 | Too many requests | Backoff |
| INTERNAL_ERROR | 500 | Server error | Retry |

### Retry Policy (AP)
- 401/403: Re-authenticate, do not retry with same token
- 429: Exponential backoff starting at 1s, max 60s
- 500/502/503: Retry 3 times with 2s, 4s, 8s delays
- Network errors: Retry 3 times with exponential backoff

## 2. Heartbeat (HTTP + UDP)
### sign_in
POST {heartbeat_server}/sign_in

Request:
```json
{
  "agent_id": "alice.ap.example.com",
  "signature": "eyJhbGciOiJFUzM4NCIsInR5cCI6IkpXVCJ9..."
}
```

Response:
```json
{
  "server_ip": "203.0.113.42",
  "port": 8888,
  "sign_cookie": 1234567890123456
}
```

### UDP Framing
Header fields (varint + fixed):
```
+----------------+----------------+----------------+----------------+
| MessageMask    | MessageSeq     | MessageType    | PayloadSize    |
| (varint)       | (varint)       | (uint16 BE)    | (uint16 BE)    |
+----------------+----------------+----------------+----------------+
| Payload (PayloadSize bytes)                                       |
+-------------------------------------------------------------------+
```

- MessageMask: varint, bitmask for optional fields
- MessageSeq: varint, sequence number for ordering
- MessageType: uint16, big-endian
- PayloadSize: uint16, big-endian

### Heartbeat Request (type 0x0201 / 513)
```
+----------------+----------------+----------------+
| AgentIdLen     | AgentId        | SignCookie     |
| (varint)       | (bytes)        | (uint64 BE)    |
+----------------+----------------+----------------+
```

### Heartbeat Response (type 0x0102 / 258)
```
+----------------+
| NextBeat       |
| (uint64 BE ms) |
+----------------+
```
- NextBeat: milliseconds until next heartbeat
- If NextBeat == 401: re-authenticate required

### Invite Notification (type 0x0204 / 516)
```
+----------+----------+----------+----------+----------+
| AgentId  | Inviter  | Session  | SignCookie          |
| (len+str)| (len+str)| (len+str)| (uint64 BE)         |
+----------+----------+----------+----------+----------+
```

### UDP Reliability
- No built-in retransmission; rely on periodic heartbeat
- Packet loss detection via missing sequence numbers
- Client should send heartbeat at NextBeat interval
- If no response after 3 consecutive heartbeats, reconnect via HTTP

## 3. Message Server (WebSocket)
### Connection
WebSocket URL:
```
wss://{message_server}/session?agent_id={aid}&signature={signature}
```

Connection headers:
```
Sec-WebSocket-Protocol: acp-v1
Origin: https://client.example.com
```

### Envelope Format
All messages use JSON envelope:
```json
{
  "cmd": "<command>",
  "request_id": "<uuid>",
  "data": { ... }
}
```

### Core Commands

#### session_message (send/receive)
Request:
```json
{
  "cmd": "session_message",
  "request_id": "uuid-1234",
  "data": {
    "session_id": "session-uuid",
    "ref_msg_id": null,
    "receiver": "bob.ap.example.com,carol.ap.example.com",
    "instruction": null,
    "message": "%5B%7B%22type%22%3A%22content%22%2C%22content%22%3A%22hello%22%7D%5D"
  }
}
```

Response:
```json
{
  "cmd": "session_message_ack",
  "request_id": "uuid-1234",
  "data": {
    "message_id": "msg-uuid-5678",
    "timestamp": 1704067200000
  }
}
```

Inbound message (server push):
```json
{
  "cmd": "session_message",
  "data": {
    "message_id": "msg-uuid-5678",
    "session_id": "session-uuid",
    "ref_msg_id": null,
    "sender": "alice.ap.example.com",
    "instruction": null,
    "receiver": "bob.ap.example.com",
    "message": "%5B%7B%22type%22%3A%22content%22%2C%22content%22%3A%22hello%22%7D%5D",
    "timestamp": 1704067200000
  }
}
```

#### invite_agent_req
Request:
```json
{
  "cmd": "invite_agent_req",
  "request_id": "uuid-1234",
  "data": {
    "session_id": "session-uuid",
    "agent_id": "bob.ap.example.com"
  }
}
```

Response:
```json
{
  "cmd": "invite_agent_resp",
  "request_id": "uuid-1234",
  "data": {
    "success": true
  }
}
```

#### join_session_req
Request:
```json
{
  "cmd": "join_session_req",
  "request_id": "uuid-1234",
  "data": {
    "session_id": "session-uuid"
  }
}
```

#### leave_session_req
Request:
```json
{
  "cmd": "leave_session_req",
  "request_id": "uuid-1234",
  "data": {
    "session_id": "session-uuid"
  }
}
```

#### close_session_req
Request:
```json
{
  "cmd": "close_session_req",
  "request_id": "uuid-1234",
  "data": {
    "session_id": "session-uuid"
  }
}
```

#### get_member_list
Request:
```json
{
  "cmd": "get_member_list",
  "request_id": "uuid-1234",
  "data": {
    "session_id": "session-uuid"
  }
}
```

Response:
```json
{
  "cmd": "get_member_list_resp",
  "request_id": "uuid-1234",
  "data": {
    "members": [
      {"agent_id": "alice.ap.example.com", "role": "owner"},
      {"agent_id": "bob.ap.example.com", "role": "member"}
    ]
  }
}
```

#### eject_agent_req
Request:
```json
{
  "cmd": "eject_agent_req",
  "request_id": "uuid-1234",
  "data": {
    "session_id": "session-uuid",
    "agent_id": "bob.ap.example.com"
  }
}
```

### WebSocket Ping/Pong
- Client sends ping every 30 seconds
- Server responds with pong within 10 seconds
- If no pong received, close and reconnect

### Error Responses
```json
{
  "cmd": "error",
  "request_id": "uuid-1234",
  "data": {
    "code": "SESSION_NOT_FOUND",
    "message": "Session does not exist"
  }
}
```

### WebSocket Error Codes
| Code | Description | Action |
|------|-------------|--------|
| SESSION_NOT_FOUND | Session does not exist | Check session ID |
| NOT_A_MEMBER | Not a member of session | Join first |
| PERMISSION_DENIED | No permission for action | Check role |
| INVALID_MESSAGE | Malformed message | Fix format |
| RATE_LIMITED | Too many messages | Backoff |

## 4. Stream Control

### session_create_stream_req
Request:
```json
{
  "cmd": "session_create_stream_req",
  "request_id": "uuid-1234",
  "data": {
    "session_id": "session-uuid",
    "ref_msg_id": "msg-uuid-prev",
    "sender": "alice.ap.example.com",
    "receiver": "bob.ap.example.com",
    "content_type": "text/plain",
    "timestamp": 1704067200000
  }
}
```

Response (Ack):
```json
{
  "cmd": "session_create_stream_ack",
  "request_id": "uuid-1234",
  "data": {
    "session_id": "session-uuid",
    "message_id": "stream-msg-uuid",
    "push_url": "wss://stream.example.com/push/stream-id",
    "pull_url": "wss://stream.example.com/pull/stream-id"
  }
}
```

### push_text_stream_req
Request (via push_url WebSocket):
```json
{
  "cmd": "push_text_stream_req",
  "data": {
    "chunk": "Hello%20world"
  }
}
```

### close_stream_req
Request:
```json
{
  "cmd": "close_stream_req",
  "data": {
    "stream_id": "stream-id"
  }
}
```

## 5. Binary Stream Format (WSS)

### Binary Frame Header (28 bytes)
```
+------+------+----------+----------+----------+----------+----------+----------+----------+
| Magic| Magic| Version  | Flags    | MsgType  | MsgSeq   | Content  |Compressed| Reserved |
| 'M'  | 'U'  | (uint16) | (uint32) | (uint16) | (uint32) | (uint8)  | (uint8)  | (uint32) |
+------+------+----------+----------+----------+----------+----------+----------+----------+
| CRC32        | PayloadLength                                                              |
| (uint32)     | (uint32)                                                                   |
+--------------+----------------------------------------------------------------------------+
```

All multi-byte fields are big-endian.

Fields:
- Magic: 'M' (0x4D), 'U' (0x55)
- Version: 0x0101
- Flags: uint32, reserved for future use
- MsgType: uint16
  - 0x0005: File chunk
  - 0x0006: Stream data
- MsgSeq: uint32, sequence number
- ContentType: uint8
  - 0x05: File
  - 0x06: Binary stream
- Compressed: uint8
  - 0x00: No compression
  - 0x01: zlib
- Reserved: uint32, for file offset in file chunks
- CRC32: uint32, checksum of payload
- PayloadLength: uint32, payload size in bytes

### File Chunk Frame
```
MsgType = 0x0005
ContentType = 0x05
Reserved = file offset (uint32)
Payload = raw file bytes
```

Example:
```
4D 55 01 01 00 00 00 00 00 05 00 00 00 01 05 00
00 00 10 00 AB CD EF 12 00 00 04 00 [1024 bytes]
```

## 6. File Upload / Download

### Upload
POST https://oss.{agent_network}/api/oss/upload_file

Request (multipart/form-data):
```
Content-Type: multipart/form-data; boundary=----WebKitFormBoundary

------WebKitFormBoundary
Content-Disposition: form-data; name="agent_id"

alice.ap.example.com
------WebKitFormBoundary
Content-Disposition: form-data; name="signature"

eyJhbGciOiJFUzM4NCIsInR5cCI6IkpXVCJ9...
------WebKitFormBoundary
Content-Disposition: form-data; name="file_name"

document.pdf
------WebKitFormBoundary
Content-Disposition: form-data; name="file"; filename="document.pdf"
Content-Type: application/pdf

<binary data>
------WebKitFormBoundary--
```

Response (Success):
```json
{
  "url": "https://oss.example.com/files/abc123/document.pdf",
  "file_id": "abc123",
  "size": 1048576,
  "md5": "d41d8cd98f00b204e9800998ecf8427e"
}
```

Response (Error):
```json
{
  "error": {
    "code": "FILE_TOO_LARGE",
    "message": "File exceeds maximum size of 100MB"
  }
}
```

### Download
GET {url}?agent_id={aid}&signature={signature}

Response Headers:
```
Content-Type: application/pdf
Content-Length: 1048576
Content-Disposition: attachment; filename="document.pdf"
```

### File Upload Error Codes
| Code | Description |
|------|-------------|
| FILE_TOO_LARGE | File exceeds size limit |
| INVALID_FILE_TYPE | File type not allowed |
| STORAGE_QUOTA_EXCEEDED | User storage quota exceeded |
| UPLOAD_FAILED | Server-side upload error |

### Upload Retry Policy
- Network error: Retry 3 times with exponential backoff
- 5xx errors: Retry 3 times
- 4xx errors: Do not retry, report to user

## 7. Message Blocks

Message is a URL-encoded JSON array of blocks. Each block has:

### Common Fields
```json
{
  "type": "content|file|image|audio|video|form|form_result",
  "status": "pending|sent|delivered|failed",
  "timestamp": 1704067200000
}
```

### Content Block
```json
{
  "type": "content",
  "content": "Hello, world!",
  "status": "sent",
  "timestamp": 1704067200000
}
```

### File Block
```json
{
  "type": "file",
  "content": {
    "url": "https://oss.example.com/files/abc123/document.pdf",
    "file_name": "document.pdf",
    "file_size": 1048576,
    "mime_type": "application/pdf",
    "md5": "d41d8cd98f00b204e9800998ecf8427e"
  },
  "status": "sent",
  "timestamp": 1704067200000
}
```

### Image Block
```json
{
  "type": "image",
  "content": {
    "url": "https://oss.example.com/images/xyz789/photo.jpg",
    "thumbnail_url": "https://oss.example.com/images/xyz789/thumb.jpg",
    "width": 1920,
    "height": 1080,
    "file_size": 524288
  },
  "status": "sent",
  "timestamp": 1704067200000
}
```

### Audio Block
```json
{
  "type": "audio",
  "content": {
    "url": "https://oss.example.com/audio/def456/voice.mp3",
    "duration": 120,
    "file_size": 2097152,
    "mime_type": "audio/mpeg"
  },
  "status": "sent",
  "timestamp": 1704067200000
}
```

### Video Block
```json
{
  "type": "video",
  "content": {
    "url": "https://oss.example.com/video/ghi789/clip.mp4",
    "thumbnail_url": "https://oss.example.com/video/ghi789/thumb.jpg",
    "duration": 300,
    "width": 1920,
    "height": 1080,
    "file_size": 10485760,
    "mime_type": "video/mp4"
  },
  "status": "sent",
  "timestamp": 1704067200000
}
```

### Form Block
```json
{
  "type": "form",
  "content": {
    "form_id": "form-uuid-123",
    "title": "User Survey",
    "description": "Please fill out this survey",
    "fields": [
      {
        "field_id": "field1",
        "label": "Name",
        "type": "text",
        "required": true
      },
      {
        "field_id": "field2",
        "label": "Age",
        "type": "number",
        "required": false
      },
      {
        "field_id": "field3",
        "label": "Gender",
        "type": "select",
        "options": ["Male", "Female", "Other"],
        "required": true
      }
    ]
  },
  "status": "sent",
  "timestamp": 1704067200000
}
```

### Form Result Block
```json
{
  "type": "form_result",
  "content": {
    "form_id": "form-uuid-123",
    "results": [
      {"field_id": "field1", "value": "Alice"},
      {"field_id": "field2", "value": 25},
      {"field_id": "field3", "value": "Female"}
    ]
  },
  "status": "sent",
  "timestamp": 1704067200000
}
```

### Instruction Block
```json
{
  "type": "instruction",
  "content": {
    "cmd": "execute_task",
    "params": {
      "task_id": "task-123",
      "priority": "high"
    },
    "description": "Execute the specified task",
    "model": "gpt-4"
  },
  "status": "sent",
  "timestamp": 1704067200000
}
```

## 8. TLS and Proxy

### TLS Configuration
- TLS 1.2 or higher required
- TLS verification enabled by default
- Certificate pinning optional but recommended for production

### Supported Cipher Suites
```
TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384
TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384
TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256
TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256
```

### Proxy Configuration
```json
{
  "proxy_type": "http|socks5|none",
  "proxy_host": "proxy.example.com",
  "proxy_port": 8080,
  "proxy_username": "user",
  "proxy_password": "pass",
  "bypass_list": ["localhost", "127.0.0.1", "*.internal.com"]
}
```

### Proxy Types
| Type | Description |
|------|-------------|
| none | Direct connection |
| http | HTTP/HTTPS proxy |
| socks5 | SOCKS5 proxy |
| system | Use system proxy settings |

### TLS Override (Development Only)
```cpp
// WARNING: Only for development/testing
config.tls_verify = false;
config.allow_self_signed = true;
```

When TLS verification is disabled, SDK must:
- Log a warning at startup
- Include warning in error callbacks
- Never disable in release builds by default

## 9. Protocol Version Compatibility

### Version Negotiation
- Client sends protocol version in connection header
- Server responds with supported version range
- Use highest mutually supported version

### Current Version
- Protocol version: 1.0
- Binary stream version: 0x0101
- Message format version: 1

### Backward Compatibility
- New optional fields may be added to JSON messages
- Clients must ignore unknown fields
- Breaking changes require version bump
