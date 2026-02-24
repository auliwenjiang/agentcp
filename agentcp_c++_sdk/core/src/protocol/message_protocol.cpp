#include "message_protocol.h"

#include "third_party/json.hpp"
#include "../crypto.h"

#include <chrono>
#include <sstream>
#include <iomanip>

using json = nlohmann::json;

namespace agentcp {
namespace protocol {

// ============== Utility ==============

uint64_t NowMs() {
    return static_cast<uint64_t>(
        std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch()).count());
}

std::string GenerateUuidHex() {
    auto bytes = crypto::RandomBytes(16);
    return crypto::HexEncode(bytes);
}

std::string UrlEncode(const std::string& s) {
    std::ostringstream out;
    for (unsigned char c : s) {
        if (isalnum(c) || c == '-' || c == '_' || c == '.' || c == '~') {
            out << c;
        } else {
            out << '%' << std::uppercase;
            out << "0123456789ABCDEF"[c >> 4];
            out << "0123456789ABCDEF"[c & 0x0F];
        }
    }
    return out.str();
}

std::string UrlDecode(const std::string& s) {
    std::string result;
    for (size_t i = 0; i < s.size(); ++i) {
        if (s[i] == '%' && i + 2 < s.size()) {
            int val = 0;
            auto hex_to_int = [](char c) -> int {
                if (c >= '0' && c <= '9') return c - '0';
                if (c >= 'a' && c <= 'f') return c - 'a' + 10;
                if (c >= 'A' && c <= 'F') return c - 'A' + 10;
                return -1;
            };
            int hi = hex_to_int(s[i + 1]);
            int lo = hex_to_int(s[i + 2]);
            if (hi >= 0 && lo >= 0) {
                val = (hi << 4) | lo;
                result += static_cast<char>(val);
                i += 2;
            } else {
                result += s[i];
            }
        } else if (s[i] == '+') {
            result += ' ';
        } else {
            result += s[i];
        }
    }
    return result;
}

// ============== Envelope ==============

bool ParseEnvelope(const std::string& json_str, MessageEnvelope* out) {
    try {
        auto j = json::parse(json_str);
        if (!j.contains("cmd")) return false;
        out->cmd = j["cmd"].get<std::string>();
        if (j.contains("data")) {
            out->data_json = j["data"].dump();
        }
        return true;
    } catch (...) {
        return false;
    }
}

std::string BuildEnvelope(const std::string& cmd, const std::string& data_json) {
    json j;
    j["cmd"] = cmd;
    j["data"] = json::parse(data_json);
    return j.dump();
}

// ============== Command builders ==============

std::string BuildSessionMessage(
    const std::string& message_id,
    const std::string& session_id,
    const std::string& sender,
    const std::string& receiver,
    const std::string& message_json_array,
    const std::string& ref_msg_id,
    const std::string& instruction_json,
    uint64_t timestamp) {

    if (timestamp == 0) timestamp = NowMs();

    json data;
    data["message_id"] = message_id;
    data["session_id"] = session_id;
    data["sender"] = sender;
    data["receiver"] = receiver;
    data["message"] = UrlEncode(message_json_array);
    data["ref_msg_id"] = ref_msg_id;
    data["timestamp"] = std::to_string(timestamp);

    if (instruction_json != "null" && !instruction_json.empty()) {
        data["instruction"] = json::parse(instruction_json);
    } else {
        data["instruction"] = nullptr;
    }

    return BuildEnvelope("session_message", data.dump());
}

std::string BuildCreateSessionReq(
    const std::string& request_id,
    const std::string& type,
    const std::string& group_name,
    const std::string& subject,
    uint64_t timestamp) {

    if (timestamp == 0) timestamp = NowMs();

    json data;
    data["request_id"] = request_id;
    data["type"] = type;
    data["group_name"] = group_name;
    data["subject"] = subject;
    data["timestamp"] = std::to_string(timestamp);

    return BuildEnvelope("create_session_req", data.dump());
}

std::string BuildJoinSessionReq(
    const std::string& session_id,
    const std::string& request_id,
    const std::string& inviter_agent_id,
    const std::string& invite_code,
    const std::string& last_msg_id) {

    json data;
    data["session_id"] = session_id;
    data["request_id"] = request_id;
    data["inviter_agent_id"] = inviter_agent_id;
    data["invite_code"] = invite_code;
    data["last_msg_id"] = last_msg_id;

    return BuildEnvelope("join_session_req", data.dump());
}

std::string BuildLeaveSessionReq(
    const std::string& session_id,
    const std::string& request_id) {

    json data;
    data["session_id"] = session_id;
    data["request_id"] = request_id;

    return BuildEnvelope("leave_session_req", data.dump());
}

std::string BuildCloseSessionReq(
    const std::string& session_id,
    const std::string& request_id,
    const std::string& identifying_code) {

    json data;
    data["session_id"] = session_id;
    data["request_id"] = request_id;
    data["identifying_code"] = identifying_code;

    return BuildEnvelope("close_session_req", data.dump());
}

std::string BuildInviteAgentReq(
    const std::string& session_id,
    const std::string& request_id,
    const std::string& inviter_id,
    const std::string& acceptor_id,
    const std::string& invite_code) {

    json data;
    data["session_id"] = session_id;
    data["request_id"] = request_id;
    data["inviter_id"] = inviter_id;
    data["acceptor_id"] = acceptor_id;
    data["invite_code"] = invite_code;

    return BuildEnvelope("invite_agent_req", data.dump());
}

std::string BuildEjectAgentReq(
    const std::string& session_id,
    const std::string& request_id,
    const std::string& eject_agent_id,
    const std::string& identifying_code) {

    json data;
    data["session_id"] = session_id;
    data["request_id"] = request_id;
    data["eject_agent_id"] = eject_agent_id;
    data["identifying_code"] = identifying_code;

    return BuildEnvelope("eject_agent_req", data.dump());
}

std::string BuildGetMemberListReq(
    const std::string& session_id,
    const std::string& request_id) {

    json data;
    data["session_id"] = session_id;
    data["request_id"] = request_id;

    return BuildEnvelope("get_member_list", data.dump());
}

std::string BuildCreateStreamReq(
    const std::string& session_id,
    const std::string& request_id,
    const std::string& ref_msg_id,
    const std::string& sender,
    const std::string& receiver,
    const std::string& content_type,
    uint64_t timestamp) {

    if (timestamp == 0) timestamp = NowMs();

    json data;
    data["session_id"] = session_id;
    data["request_id"] = request_id;
    data["ref_msg_id"] = ref_msg_id;
    data["sender"] = sender;
    data["receiver"] = receiver;
    data["content_type"] = content_type;
    data["timestamp"] = std::to_string(timestamp);

    return BuildEnvelope("session_create_stream_req", data.dump());
}

std::string BuildPushTextStreamReq(const std::string& chunk) {
    json data;
    data["chunk"] = UrlEncode(chunk);
    return BuildEnvelope("push_text_stream_req", data.dump());
}

std::string BuildCloseStreamReq() {
    return BuildEnvelope("close_stream_req", "{}");
}

// ============== Response parsing ==============

bool ParseCreateSessionAck(const std::string& data_json, CreateSessionAck* out) {
    try {
        auto j = json::parse(data_json);
        if (j.contains("request_id")) out->request_id = j["request_id"].get<std::string>();
        if (j.contains("session_id")) out->session_id = j["session_id"].get<std::string>();
        if (j.contains("identifying_code")) out->identifying_code = j["identifying_code"].get<std::string>();
        if (j.contains("status_code")) {
            if (j["status_code"].is_string()) {
                out->status_code = j["status_code"].get<std::string>();
            } else {
                out->status_code = std::to_string(j["status_code"].get<int>());
            }
        }
        if (j.contains("message")) out->message = j["message"].get<std::string>();
        return true;
    } catch (...) {
        return false;
    }
}

bool ParseCreateStreamAck(const std::string& data_json, CreateStreamAck* out) {
    try {
        auto j = json::parse(data_json);
        if (j.contains("request_id")) out->request_id = j["request_id"].get<std::string>();
        if (j.contains("session_id")) out->session_id = j["session_id"].get<std::string>();
        if (j.contains("push_url")) out->push_url = j["push_url"].get<std::string>();
        if (j.contains("pull_url")) out->pull_url = j["pull_url"].get<std::string>();
        if (j.contains("message_id")) out->message_id = j["message_id"].get<std::string>();
        if (j.contains("error")) out->error = j["error"].get<std::string>();
        if (j.contains("message")) out->error_message = j["message"].get<std::string>();
        return true;
    } catch (...) {
        return false;
    }
}

bool ParseInviteAgentAck(const std::string& data_json, InviteAgentAck* out) {
    try {
        auto j = json::parse(data_json);
        if (j.contains("request_id")) out->request_id = j["request_id"].get<std::string>();
        if (j.contains("status_code")) {
            if (j["status_code"].is_string()) {
                out->status_code = j["status_code"].get<std::string>();
            } else {
                out->status_code = std::to_string(j["status_code"].get<int>());
            }
        }
        if (j.contains("message")) out->message = j["message"].get<std::string>();
        return true;
    } catch (...) {
        return false;
    }
}

}  // namespace protocol
}  // namespace agentcp
