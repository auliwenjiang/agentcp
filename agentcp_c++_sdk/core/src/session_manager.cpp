#include "agentcp/agentcp.h"

#include "internal.h"
#include "acp_log.h"
#include "client/message_client.h"
#include "protocol/message_protocol.h"

#include "third_party/json.hpp"

#include <algorithm>
#include <chrono>
#include <utility>

using json = nlohmann::json;

namespace agentcp {

SessionManager::SessionManager(AgentID* owner) : owner_(owner) {}

Result SessionManager::CreateSession(const std::vector<std::string>& members, std::string* session_id_out) {
    if (session_id_out == nullptr) {
        return MakeError(ErrorCode::INVALID_ARGUMENT, "session_id_out is null");
    }
    if (owner_ == nullptr || !owner_->IsOnline()) {
        return MakeError(ErrorCode::NOT_INITIALIZED, "agent is offline");
    }

    ACP_LOGI("CreateSession: self='%s', memberCount=%zu", owner_->GetAID().c_str(), members.size());
    for (size_t i = 0; i < members.size(); ++i) {
        ACP_LOGI("CreateSession: member[%zu]='%s' (len=%zu)", i, members[i].c_str(), members[i].size());
    }

    // Send create_session_req via WebSocket if message client is available
    if (owner_->message_client_ && owner_->message_client_->IsConnected()) {
        std::string request_id = protocol::GenerateUuidHex();
        std::string msg = protocol::BuildCreateSessionReq(
            request_id, "public", "", "");

        std::string ack_json = owner_->message_client_->SendAndWaitAck(
            msg, "create_session_ack", request_id, 10000);

        ACP_LOGI("CreateSession: ack_json='%s'", ack_json.c_str());

        if (!ack_json.empty()) {
            protocol::CreateSessionAck ack;
            if (protocol::ParseCreateSessionAck(ack_json, &ack) && !ack.session_id.empty()) {
                ACP_LOGI("CreateSession: server session_id='%s', status='%s'",
                         ack.session_id.c_str(), ack.status_code.c_str());
                // Server-assigned session ID
                auto session = std::unique_ptr<Session>(new Session(owner_, ack.session_id));

                SessionMember owner_member;
                owner_member.agent_id = owner_->GetAID();
                owner_member.role = "owner";
                owner_member.joined_at = static_cast<uint64_t>(
                    std::chrono::duration_cast<std::chrono::milliseconds>(
                        std::chrono::system_clock::now().time_since_epoch()).count());

                {
                    std::lock_guard<std::mutex> session_lock(session->mutex_);
                    session->members_.push_back(owner_member);

                    for (const auto& member_id : members) {
                        if (member_id.empty() || member_id == owner_member.agent_id) {
                            continue;
                        }
                        SessionMember m;
                        m.agent_id = member_id;
                        m.role = "member";
                        m.joined_at = owner_member.joined_at;
                        session->members_.push_back(m);
                    }
                }

                {
                    std::lock_guard<std::mutex> lock(mutex_);
                    sessions_.emplace(ack.session_id, std::move(session));
                }

                // Invite additional members
                for (const auto& member_id : members) {
                    if (member_id.empty() || member_id == owner_->GetAID()) continue;
                    ACP_LOGI("CreateSession: auto-inviting member='%s' to session='%s'",
                             member_id.c_str(), ack.session_id.c_str());
                    InviteAgent(ack.session_id, member_id);
                }

                *session_id_out = ack.session_id;
                return Result::Ok();
            }
        }
    }

    // Fallback: local-only session creation
    ACP_LOGW("CreateSession: FALLBACK to local-only session (no server ack)");
    auto session_id = GenerateId("session");
    auto session = std::unique_ptr<Session>(new Session(owner_, session_id));

    SessionMember owner_member;
    owner_member.agent_id = owner_->GetAID();
    owner_member.role = "owner";
    owner_member.joined_at = static_cast<uint64_t>(
        std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch()).count());

    {
        std::lock_guard<std::mutex> session_lock(session->mutex_);
        session->members_.push_back(owner_member);

        for (const auto& member_id : members) {
            if (member_id.empty() || member_id == owner_member.agent_id) {
                continue;
            }
            SessionMember m;
            m.agent_id = member_id;
            m.role = "member";
            m.joined_at = owner_member.joined_at;
            session->members_.push_back(m);
        }
    }

    {
        std::lock_guard<std::mutex> lock(mutex_);
        sessions_.emplace(session_id, std::move(session));
    }

    *session_id_out = session_id;
    return Result::Ok();
}

Result SessionManager::InviteAgent(const std::string& session_id, const std::string& agent_id) {
    if (session_id.empty() || agent_id.empty()) {
        return MakeError(ErrorCode::INVALID_ARGUMENT, "invalid arguments");
    }

    ACP_LOGI("InviteAgent: session='%s', target='%s' (len=%zu), self='%s'",
             session_id.c_str(), agent_id.c_str(), agent_id.size(), owner_->GetAID().c_str());

    // Send invite_agent_req via WebSocket
    if (owner_->message_client_ && owner_->message_client_->IsConnected()) {
        std::string request_id = protocol::GenerateUuidHex();
        std::string msg = protocol::BuildInviteAgentReq(
            session_id, request_id, owner_->GetAID(), agent_id, "");
        bool sent = owner_->message_client_->SendMessage(msg);
        ACP_LOGI("InviteAgent: invite_agent_req sent=%d, req_id='%s', payload_len=%zu",
                 sent, request_id.c_str(), msg.size());
    } else {
        ACP_LOGW("InviteAgent: ws not connected, invite NOT sent");
    }

    // Update local state
    Session* session = nullptr;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = sessions_.find(session_id);
        if (it == sessions_.end()) {
            return MakeError(ErrorCode::SESSION_NOT_FOUND, "session not found");
        }
        session = it->second.get();
    }

    std::lock_guard<std::mutex> session_lock(session->mutex_);
    for (const auto& member : session->members_) {
        if (member.agent_id == agent_id) {
            return Result::Ok();
        }
    }

    SessionMember m;
    m.agent_id = agent_id;
    m.role = "member";
    m.joined_at = static_cast<uint64_t>(
        std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch()).count());
    session->members_.push_back(m);
    return Result::Ok();
}

Result SessionManager::JoinSession(const std::string& session_id) {
    if (session_id.empty()) {
        return MakeError(ErrorCode::INVALID_ARGUMENT, "invalid session id");
    }

    // Send join_session_req via WebSocket
    if (owner_->message_client_ && owner_->message_client_->IsConnected()) {
        std::string request_id = std::to_string(protocol::NowMs());
        std::string msg = protocol::BuildJoinSessionReq(
            session_id, request_id, "", "");
        owner_->message_client_->SendMessage(msg);
    }

    // Create local session if it doesn't exist
    {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = sessions_.find(session_id);
        if (it == sessions_.end()) {
            auto session = std::unique_ptr<Session>(new Session(owner_, session_id));
            SessionMember m;
            m.agent_id = owner_->GetAID();
            m.role = "member";
            m.joined_at = static_cast<uint64_t>(
                std::chrono::duration_cast<std::chrono::milliseconds>(
                    std::chrono::system_clock::now().time_since_epoch()).count());
            session->members_.push_back(m);
            sessions_.emplace(session_id, std::move(session));
        }
    }

    return Result::Ok();
}

Result SessionManager::LeaveSession(const std::string& session_id) {
    if (session_id.empty()) {
        return MakeError(ErrorCode::INVALID_ARGUMENT, "invalid session id");
    }

    // Send leave_session_req via WebSocket
    if (owner_->message_client_ && owner_->message_client_->IsConnected()) {
        std::string request_id = std::to_string(protocol::NowMs());
        std::string msg = protocol::BuildLeaveSessionReq(session_id, request_id);
        owner_->message_client_->SendMessage(msg);
    }

    Session* session = nullptr;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = sessions_.find(session_id);
        if (it == sessions_.end()) {
            return MakeError(ErrorCode::SESSION_NOT_FOUND, "session not found");
        }
        session = it->second.get();
    }

    const auto& aid = owner_ ? owner_->GetAID() : std::string();
    std::lock_guard<std::mutex> session_lock(session->mutex_);
    session->members_.erase(
        std::remove_if(session->members_.begin(), session->members_.end(),
            [&](const SessionMember& m) { return m.agent_id == aid; }),
        session->members_.end());
    return Result::Ok();
}

Result SessionManager::CloseSession(const std::string& session_id) {
    if (session_id.empty()) {
        return MakeError(ErrorCode::INVALID_ARGUMENT, "invalid session id");
    }

    // Send close_session_req via WebSocket
    if (owner_->message_client_ && owner_->message_client_->IsConnected()) {
        std::string request_id = std::to_string(protocol::NowMs());
        std::string msg = protocol::BuildCloseSessionReq(session_id, request_id, "");
        owner_->message_client_->SendMessage(msg);
    }

    Session* session = nullptr;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = sessions_.find(session_id);
        if (it == sessions_.end()) {
            return MakeError(ErrorCode::SESSION_NOT_FOUND, "session not found");
        }
        session = it->second.get();
    }

    std::lock_guard<std::mutex> session_lock(session->mutex_);
    session->closed_ = true;
    return Result::Ok();
}

Result SessionManager::GetMemberList(const std::string& session_id, std::vector<SessionMember>* members_out) {
    if (session_id.empty() || members_out == nullptr) {
        return MakeError(ErrorCode::INVALID_ARGUMENT, "invalid arguments");
    }

    // Optionally send get_member_list via WebSocket
    if (owner_->message_client_ && owner_->message_client_->IsConnected()) {
        std::string request_id = std::to_string(protocol::NowMs());
        std::string msg = protocol::BuildGetMemberListReq(session_id, request_id);
        owner_->message_client_->SendMessage(msg);
    }

    Session* session = nullptr;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = sessions_.find(session_id);
        if (it == sessions_.end()) {
            return MakeError(ErrorCode::SESSION_NOT_FOUND, "session not found");
        }
        session = it->second.get();
    }

    std::lock_guard<std::mutex> session_lock(session->mutex_);
    *members_out = session->members_;
    return Result::Ok();
}

Result SessionManager::EjectAgent(const std::string& session_id, const std::string& agent_id) {
    if (session_id.empty() || agent_id.empty()) {
        return MakeError(ErrorCode::INVALID_ARGUMENT, "invalid arguments");
    }

    // Send eject_agent_req via WebSocket
    if (owner_->message_client_ && owner_->message_client_->IsConnected()) {
        std::string request_id = std::to_string(protocol::NowMs());
        std::string msg = protocol::BuildEjectAgentReq(session_id, request_id, agent_id, "");
        owner_->message_client_->SendMessage(msg);
    }

    Session* session = nullptr;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = sessions_.find(session_id);
        if (it == sessions_.end()) {
            return MakeError(ErrorCode::SESSION_NOT_FOUND, "session not found");
        }
        session = it->second.get();
    }

    std::lock_guard<std::mutex> session_lock(session->mutex_);
    auto& members = session->members_;
    members.erase(std::remove_if(members.begin(), members.end(),
        [&](const SessionMember& m) { return m.agent_id == agent_id; }), members.end());
    return Result::Ok();
}

Session* SessionManager::GetSession(const std::string& session_id) {
    std::lock_guard<std::mutex> lock(mutex_);
    auto it = sessions_.find(session_id);
    if (it == sessions_.end()) {
        return nullptr;
    }
    return it->second.get();
}

std::vector<std::string> SessionManager::GetActiveSessions() {
    std::lock_guard<std::mutex> lock(mutex_);
    std::vector<std::string> ids;
    ids.reserve(sessions_.size());
    for (const auto& kv : sessions_) {
        ids.push_back(kv.first);
    }
    return ids;
}

Result SessionManager::GetSessionInfo(const std::string& session_id, SessionInfo* info_out) {
    if (session_id.empty() || info_out == nullptr) {
        return MakeError(ErrorCode::INVALID_ARGUMENT, "invalid arguments");
    }

    Session* session = nullptr;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = sessions_.find(session_id);
        if (it == sessions_.end()) {
            return MakeError(ErrorCode::SESSION_NOT_FOUND, "session not found");
        }
        session = it->second.get();
    }

    std::lock_guard<std::mutex> session_lock(session->mutex_);
    info_out->session_id = session->session_id_;
    info_out->members = session->members_;
    return Result::Ok();
}

}  // namespace agentcp
