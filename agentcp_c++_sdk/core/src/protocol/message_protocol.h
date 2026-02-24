#pragma once

#include <string>
#include <vector>
#include <cstdint>
#include <map>
#include <optional>

namespace agentcp {
namespace protocol {

// Message envelope: {"cmd": "...", "data": {...}}
struct MessageEnvelope {
    std::string cmd;
    std::string data_json;  // raw JSON string of the data field
};

// Parse a message envelope from raw JSON
bool ParseEnvelope(const std::string& json, MessageEnvelope* out);

// Build a message envelope JSON string
std::string BuildEnvelope(const std::string& cmd, const std::string& data_json);

// ============== Command builders ==============

// session_message
std::string BuildSessionMessage(
    const std::string& message_id,
    const std::string& session_id,
    const std::string& sender,
    const std::string& receiver,
    const std::string& message_json_array,  // URL-encoded JSON array of blocks
    const std::string& ref_msg_id = "",
    const std::string& instruction_json = "null",
    uint64_t timestamp = 0);

// create_session_req
std::string BuildCreateSessionReq(
    const std::string& request_id,
    const std::string& type,         // "public" or "private"
    const std::string& group_name,
    const std::string& subject,
    uint64_t timestamp = 0);

// join_session_req
std::string BuildJoinSessionReq(
    const std::string& session_id,
    const std::string& request_id,
    const std::string& inviter_agent_id,
    const std::string& invite_code,
    const std::string& last_msg_id = "0");

// leave_session_req
std::string BuildLeaveSessionReq(
    const std::string& session_id,
    const std::string& request_id);

// close_session_req
std::string BuildCloseSessionReq(
    const std::string& session_id,
    const std::string& request_id,
    const std::string& identifying_code);

// invite_agent_req
std::string BuildInviteAgentReq(
    const std::string& session_id,
    const std::string& request_id,
    const std::string& inviter_id,
    const std::string& acceptor_id,
    const std::string& invite_code);

// eject_agent_req
std::string BuildEjectAgentReq(
    const std::string& session_id,
    const std::string& request_id,
    const std::string& eject_agent_id,
    const std::string& identifying_code);

// get_member_list
std::string BuildGetMemberListReq(
    const std::string& session_id,
    const std::string& request_id);

// session_create_stream_req
std::string BuildCreateStreamReq(
    const std::string& session_id,
    const std::string& request_id,
    const std::string& ref_msg_id,
    const std::string& sender,
    const std::string& receiver,
    const std::string& content_type,
    uint64_t timestamp = 0);

// push_text_stream_req
std::string BuildPushTextStreamReq(const std::string& chunk);

// close_stream_req
std::string BuildCloseStreamReq();

// ============== Response parsing ==============

struct CreateSessionAck {
    std::string request_id;
    std::string session_id;
    std::string identifying_code;
    std::string status_code;
    std::string message;
};

bool ParseCreateSessionAck(const std::string& data_json, CreateSessionAck* out);

struct CreateStreamAck {
    std::string request_id;
    std::string session_id;
    std::string push_url;
    std::string pull_url;
    std::string message_id;
    std::string error;
    std::string error_message;
};

bool ParseCreateStreamAck(const std::string& data_json, CreateStreamAck* out);

struct InviteAgentAck {
    std::string request_id;
    std::string status_code;
    std::string message;
};

bool ParseInviteAgentAck(const std::string& data_json, InviteAgentAck* out);

// ============== Utility ==============

// URL-encode a string (for message content)
std::string UrlEncode(const std::string& s);

// URL-decode a string
std::string UrlDecode(const std::string& s);

// Get current timestamp in milliseconds
uint64_t NowMs();

// Generate a UUID hex string (32 lowercase hex chars, no dashes)
std::string GenerateUuidHex();

}  // namespace protocol
}  // namespace agentcp
