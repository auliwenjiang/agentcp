#include "agentcp/group_operations.h"
#include "agentcp/group_client.h"
#include "agentcp/cursor_store.h"

#include "third_party/json.hpp"

#include <stdexcept>

using json = nlohmann::json;

namespace agentcp {
namespace group {

// ============================================================
// Helper: safe JSON data accessor
// ============================================================

static json ParseDataJson(const GroupResponse& resp) {
    if (resp.data_json.empty()) return json::object();
    try { return json::parse(resp.data_json); }
    catch (...) { return json::object(); }
}

static std::vector<std::string> JsonToStringVec(const json& j, const char* key) {
    std::vector<std::string> v;
    if (j.contains(key) && j[key].is_array()) {
        for (auto& e : j[key]) v.push_back(e.get<std::string>());
    }
    return v;
}

static GroupMessage JsonToGroupMessage(const json& m) {
    GroupMessage msg;
    msg.msg_id       = m.value("msg_id", (int64_t)0);
    msg.sender       = m.value("sender", "");
    msg.content      = m.value("content", "");
    msg.content_type = m.value("content_type", "");
    msg.timestamp    = m.value("timestamp", (int64_t)0);
    if (m.contains("metadata") && !m["metadata"].is_null())
        msg.metadata_json = m["metadata"].dump();
    return msg;
}

static GroupEvent JsonToGroupEvent(const json& e) {
    GroupEvent evt;
    evt.event_id   = e.value("event_id", (int64_t)0);
    evt.event_type = e.value("event_type", "");
    evt.actor      = e.value("actor", "");
    evt.timestamp  = e.value("timestamp", (int64_t)0);
    evt.target     = e.value("target", "");
    if (e.contains("data") && !e["data"].is_null())
        evt.data_json = e["data"].dump();
    return evt;
}

// ============================================================
// GroupOperations
// ============================================================

GroupOperations::GroupOperations(ACPGroupClient* client)
    : client_(client) {}

void GroupOperations::Check(const GroupResponse& resp, const std::string& action) {
    if (resp.code != static_cast<int>(GroupErrorCode::SUCCESS)) {
        throw GroupError(action, resp.code, resp.error, resp.group_id);
    }
}

// -- Utility --

GroupOperations::ParsedGroupUrl GroupOperations::ParseGroupUrl(const std::string& group_url) {
    // Parse "https://host/path" or "http://host/path" without regex
    // L1/L2 fix: simple string parsing, handles query params
    std::string url = group_url;

    // Strip scheme
    size_t scheme_end = url.find("://");
    if (scheme_end == std::string::npos) {
        throw std::runtime_error("invalid group URL (no scheme): " + group_url);
    }
    url = url.substr(scheme_end + 3);  // "host/path?query"

    // Split host and path
    size_t slash_pos = url.find('/');
    if (slash_pos == std::string::npos || slash_pos == 0) {
        throw std::runtime_error("invalid group URL (no path): " + group_url);
    }
    std::string host = url.substr(0, slash_pos);
    std::string path = url.substr(slash_pos + 1);

    // Strip query params and fragment from path
    size_t query_pos = path.find('?');
    if (query_pos != std::string::npos) path = path.substr(0, query_pos);
    size_t frag_pos = path.find('#');
    if (frag_pos != std::string::npos) path = path.substr(0, frag_pos);

    // Strip trailing slashes
    while (!path.empty() && path.back() == '/') path.pop_back();

    if (host.empty() || path.empty()) {
        throw std::runtime_error("group URL missing targetAid or groupId: " + group_url);
    }

    return {host, path};
}

RequestJoinResp GroupOperations::JoinByUrl(const std::string& group_url,
                                       const std::string& invite_code,
                                       const std::string& message) {
    auto parsed = ParseGroupUrl(group_url);
    if (!invite_code.empty()) {
        UseInviteCode(parsed.target_aid, parsed.group_id, invite_code);
        return {"joined", ""};
    }
    return RequestJoin(parsed.target_aid, parsed.group_id, message);
}

// ============================================================
// Phase 0: Lifecycle (register / heartbeat / unregister)
// ============================================================

void GroupOperations::RegisterOnline(const std::string& target_aid) {
    auto resp = client_->SendRequest(target_aid, "", "register_online");
    Check(resp, "register_online");
}

void GroupOperations::UnregisterOnline(const std::string& target_aid) {
    auto resp = client_->SendRequest(target_aid, "", "unregister_online");
    Check(resp, "unregister_online");
}

void GroupOperations::Heartbeat(const std::string& target_aid) {
    auto resp = client_->SendRequest(target_aid, "", "heartbeat");
    Check(resp, "heartbeat");
}

// ============================================================
// Phase 1: Basic Operations
// ============================================================

CreateGroupResp GroupOperations::CreateGroup(const std::string& target_aid, const std::string& name,
                                             const std::string& alias, const std::string& subject,
                                             const std::string& visibility,
                                             const std::string& description,
                                             const std::vector<std::string>& tags) {
    json params;
    params["name"] = name;
    if (!alias.empty()) params["alias"] = alias;
    if (!subject.empty()) params["subject"] = subject;
    if (!description.empty()) params["description"] = description;
    if (!visibility.empty()) params["visibility"] = visibility;
    if (!tags.empty()) params["tags"] = tags;

    auto resp = client_->SendRequest(target_aid, "", "create_group", params.dump());
    Check(resp, "create_group");
    auto d = ParseDataJson(resp);
    return {d.value("group_id", ""), d.value("group_url", "")};
}

void GroupOperations::AddMember(const std::string& target_aid, const std::string& group_id,
                                const std::string& agent_id, const std::string& role) {
    json params;
    params["agent_id"] = agent_id;
    if (!role.empty()) params["role"] = role;
    auto resp = client_->SendRequest(target_aid, group_id, "add_member", params.dump());
    Check(resp, "add_member");
}

SendMessageResp GroupOperations::SendGroupMessage(const std::string& target_aid,
                                                   const std::string& group_id,
                                                   const std::string& content,
                                                   const std::string& content_type,
                                                   const std::string& metadata_json) {
    json params;
    params["content"] = content;
    if (!content_type.empty()) params["content_type"] = content_type;
    if (!metadata_json.empty()) {
        try { params["metadata"] = json::parse(metadata_json); } catch (...) {}
    }
    auto resp = client_->SendRequest(target_aid, group_id, "send_message", params.dump());
    Check(resp, "send_message");
    auto d = ParseDataJson(resp);
    return {d.value("msg_id", (int64_t)0), d.value("timestamp", (int64_t)0)};
}

PullMessagesResp GroupOperations::PullMessages(const std::string& target_aid,
                                               const std::string& group_id,
                                               int64_t after_msg_id, int limit) {
    // after_msg_id > 0: explicit position mode
    // after_msg_id = 0: auto-cursor mode (send empty params, server uses current_msg_id)
    std::string params_str;
    if (after_msg_id > 0 || limit > 0) {
        json params;
        if (after_msg_id > 0) params["after_msg_id"] = after_msg_id;
        if (limit > 0) params["limit"] = limit;
        params_str = params.dump();
    }
    auto resp = client_->SendRequest(target_aid, group_id, "pull_messages", params_str);
    Check(resp, "pull_messages");
    auto d = ParseDataJson(resp);

    PullMessagesResp result;
    result.has_more = d.value("has_more", false);
    result.latest_msg_id = d.value("latest_msg_id", (int64_t)0);
    if (d.contains("messages") && d["messages"].is_array()) {
        for (auto& m : d["messages"]) {
            result.messages.push_back(JsonToGroupMessage(m));
        }
    }
    return result;
}

void GroupOperations::AckMessages(const std::string& target_aid, const std::string& group_id,
                                  int64_t msg_id) {
    json params;
    params["msg_id"] = msg_id;
    auto resp = client_->SendRequest(target_aid, group_id, "ack_messages", params.dump());
    Check(resp, "ack_messages");
    auto store = client_->GetCursorStore();
    if (store) store->SaveMsgCursor(group_id, msg_id);
}

PullEventsResp GroupOperations::PullEvents(const std::string& target_aid,
                                           const std::string& group_id,
                                           int64_t after_event_id, int limit) {
    json params;
    params["after_event_id"] = after_event_id;
    if (limit > 0) params["limit"] = limit;
    auto resp = client_->SendRequest(target_aid, group_id, "pull_events", params.dump());
    Check(resp, "pull_events");
    auto d = ParseDataJson(resp);

    PullEventsResp result;
    result.has_more = d.value("has_more", false);
    result.latest_event_id = d.value("latest_event_id", (int64_t)0);
    if (d.contains("events") && d["events"].is_array()) {
        for (auto& e : d["events"]) {
            result.events.push_back(JsonToGroupEvent(e));
        }
    }
    return result;
}

void GroupOperations::AckEvents(const std::string& target_aid, const std::string& group_id,
                                int64_t event_id) {
    json params;
    params["event_id"] = event_id;
    auto resp = client_->SendRequest(target_aid, group_id, "ack_events", params.dump());
    Check(resp, "ack_events");
    auto store = client_->GetCursorStore();
    if (store) store->SaveEventCursor(group_id, event_id);
}

CursorState GroupOperations::GetCursor(const std::string& target_aid, const std::string& group_id) {
    auto resp = client_->SendRequest(target_aid, group_id, "get_cursor");
    Check(resp, "get_cursor");
    auto d = ParseDataJson(resp);

    CursorState state;
    if (d.contains("msg_cursor")) {
        auto& mc = d["msg_cursor"];
        state.msg_cursor.start_msg_id   = mc.value("start_msg_id", (int64_t)0);
        state.msg_cursor.current_msg_id = mc.value("current_msg_id", (int64_t)0);
        state.msg_cursor.latest_msg_id  = mc.value("latest_msg_id", (int64_t)0);
        state.msg_cursor.unread_count   = mc.value("unread_count", (int64_t)0);
    }
    if (d.contains("event_cursor")) {
        auto& ec = d["event_cursor"];
        state.event_cursor.start_event_id   = ec.value("start_event_id", (int64_t)0);
        state.event_cursor.current_event_id = ec.value("current_event_id", (int64_t)0);
        state.event_cursor.latest_event_id  = ec.value("latest_event_id", (int64_t)0);
        state.event_cursor.unread_count     = ec.value("unread_count", (int64_t)0);
    }
    return state;
}

void GroupOperations::SyncGroup(const std::string& target_aid, const std::string& group_id,
                                SyncHandler* handler) {
    auto cursor = GetCursor(target_aid, group_id);
    auto store = client_->GetCursorStore();
    if (store) {
        auto [local_msg, local_event] = store->LoadCursor(group_id);
        if (local_msg > cursor.msg_cursor.current_msg_id)
            cursor.msg_cursor.current_msg_id = local_msg;
        if (local_event > cursor.event_cursor.current_event_id)
            cursor.event_cursor.current_event_id = local_event;
    }
    SyncMessages(target_aid, group_id, cursor, handler);
    SyncEventsLoop(target_aid, group_id, cursor, handler);
}

void GroupOperations::SyncMessages(const std::string& target_aid, const std::string& group_id,
                                   CursorState& cursor, SyncHandler* handler) {
    int64_t after = cursor.msg_cursor.current_msg_id;
    while (true) {
        auto result = PullMessages(target_aid, group_id, after, 50);
        if (!result.messages.empty()) {
            handler->OnMessages(group_id, result.messages);
            int64_t last_id = result.messages.back().msg_id;
            AckMessages(target_aid, group_id, last_id);
            after = last_id;
        }
        if (!result.has_more) break;
    }
}

void GroupOperations::SyncEventsLoop(const std::string& target_aid, const std::string& group_id,
                                     CursorState& cursor, SyncHandler* handler) {
    int64_t after = cursor.event_cursor.current_event_id;
    while (true) {
        auto result = PullEvents(target_aid, group_id, after, 50);
        if (!result.events.empty()) {
            handler->OnEvents(group_id, result.events);
            int64_t last_id = result.events.back().event_id;
            AckEvents(target_aid, group_id, last_id);
            after = last_id;
        }
        if (!result.has_more) break;
    }
}

// ============================================================
// Phase 2: Management Operations
// ============================================================

void GroupOperations::RemoveMember(const std::string& target_aid, const std::string& group_id,
                                   const std::string& agent_id) {
    json params; params["agent_id"] = agent_id;
    auto resp = client_->SendRequest(target_aid, group_id, "remove_member", params.dump());
    Check(resp, "remove_member");
}

void GroupOperations::LeaveGroup(const std::string& target_aid, const std::string& group_id) {
    auto resp = client_->SendRequest(target_aid, group_id, "leave_group");
    Check(resp, "leave_group");
}

void GroupOperations::DissolveGroup(const std::string& target_aid, const std::string& group_id) {
    auto resp = client_->SendRequest(target_aid, group_id, "dissolve_group");
    Check(resp, "dissolve_group");
}

void GroupOperations::BanAgent(const std::string& target_aid, const std::string& group_id,
                               const std::string& agent_id, const std::string& reason,
                               int64_t expires_at) {
    json params; params["agent_id"] = agent_id;
    if (!reason.empty()) params["reason"] = reason;
    if (expires_at > 0) params["expires_at"] = expires_at;
    auto resp = client_->SendRequest(target_aid, group_id, "ban_agent", params.dump());
    Check(resp, "ban_agent");
}

void GroupOperations::UnbanAgent(const std::string& target_aid, const std::string& group_id,
                                 const std::string& agent_id) {
    json params; params["agent_id"] = agent_id;
    auto resp = client_->SendRequest(target_aid, group_id, "unban_agent", params.dump());
    Check(resp, "unban_agent");
}

BanlistResp GroupOperations::GetBanlist(const std::string& target_aid, const std::string& group_id) {
    auto resp = client_->SendRequest(target_aid, group_id, "get_banlist");
    Check(resp, "get_banlist");
    auto d = ParseDataJson(resp);
    BanlistResp r;
    r.banned_json = d.contains("banned") ? d["banned"].dump() : "[]";
    return r;
}

RequestJoinResp GroupOperations::RequestJoin(const std::string& target_aid, const std::string& group_id,
                                         const std::string& message) {
    json params;
    if (!message.empty()) params["message"] = message;
    std::string p = params.empty() ? "" : params.dump();
    auto resp = client_->SendRequest(target_aid, group_id, "request_join", p);
    Check(resp, "request_join");
    auto d = ParseDataJson(resp);
    return {d.value("status", "pending"), d.value("request_id", "")};
}

void GroupOperations::ReviewJoinRequest(const std::string& target_aid, const std::string& group_id,
                                        const std::string& agent_id, const std::string& action,
                                        const std::string& reason) {
    json params; params["agent_id"] = agent_id; params["action"] = action;
    if (!reason.empty()) params["reason"] = reason;
    auto resp = client_->SendRequest(target_aid, group_id, "review_join_request", params.dump());
    Check(resp, "review_join_request");
}

BatchReviewResp GroupOperations::BatchReviewJoinRequests(const std::string& target_aid,
                                                         const std::string& group_id,
                                                         const std::vector<std::string>& agent_ids,
                                                         const std::string& action,
                                                         const std::string& reason) {
    json params; params["agent_ids"] = agent_ids; params["action"] = action;
    if (!reason.empty()) params["reason"] = reason;
    auto resp = client_->SendRequest(target_aid, group_id, "batch_review_join_requests", params.dump());
    Check(resp, "batch_review_join_requests");
    auto d = ParseDataJson(resp);
    return {d.value("processed", 0), d.value("total", 0)};
}

PendingRequestsResp GroupOperations::GetPendingRequests(const std::string& target_aid,
                                                        const std::string& group_id) {
    auto resp = client_->SendRequest(target_aid, group_id, "get_pending_requests");
    Check(resp, "get_pending_requests");
    auto d = ParseDataJson(resp);
    PendingRequestsResp r;
    r.requests_json = d.contains("requests") ? d["requests"].dump() : "[]";
    return r;
}

// ============================================================
// Phase 3: Full Features
// ============================================================

GroupInfoResp GroupOperations::GetGroupInfo(const std::string& target_aid, const std::string& group_id) {
    auto resp = client_->SendRequest(target_aid, group_id, "get_group_info");
    Check(resp, "get_group_info");
    auto d = ParseDataJson(resp);
    GroupInfoResp r;
    r.group_id     = d.value("group_id", "");
    r.name         = d.value("name", "");
    r.creator      = d.value("creator", "");
    r.visibility   = d.value("visibility", "");
    r.member_count = d.value("member_count", (int64_t)0);
    r.created_at   = d.value("created_at", (int64_t)0);
    r.updated_at   = d.value("updated_at", (int64_t)0);
    r.alias        = d.value("alias", "");
    r.subject      = d.value("subject", "");
    r.status       = d.value("status", "");
    r.tags         = JsonToStringVec(d, "tags");
    r.master       = d.value("master", "");
    return r;
}

void GroupOperations::UpdateGroupMeta(const std::string& target_aid, const std::string& group_id,
                                      const std::string& params_json) {
    auto resp = client_->SendRequest(target_aid, group_id, "update_group_meta", params_json);
    Check(resp, "update_group_meta");
}

MembersResp GroupOperations::GetMembers(const std::string& target_aid, const std::string& group_id) {
    auto resp = client_->SendRequest(target_aid, group_id, "get_members");
    Check(resp, "get_members");
    auto d = ParseDataJson(resp);
    MembersResp r;
    r.members_json = d.contains("members") ? d["members"].dump() : "[]";
    return r;
}

AdminsResp GroupOperations::GetAdmins(const std::string& target_aid, const std::string& group_id) {
    auto resp = client_->SendRequest(target_aid, group_id, "get_admins");
    Check(resp, "get_admins");
    auto d = ParseDataJson(resp);
    AdminsResp r;
    r.admins_json = d.contains("admins") ? d["admins"].dump() : "[]";
    return r;
}

RulesResp GroupOperations::GetRules(const std::string& target_aid, const std::string& group_id) {
    auto resp = client_->SendRequest(target_aid, group_id, "get_rules");
    Check(resp, "get_rules");
    auto d = ParseDataJson(resp);
    RulesResp r;
    r.max_members       = d.value("max_members", 0);
    r.max_message_size  = d.value("max_message_size", 0);
    if (d.contains("broadcast_policy") && !d["broadcast_policy"].is_null())
        r.broadcast_policy_json = d["broadcast_policy"].dump();
    return r;
}

void GroupOperations::UpdateRules(const std::string& target_aid, const std::string& group_id,
                                  const std::string& params_json) {
    auto resp = client_->SendRequest(target_aid, group_id, "update_rules", params_json);
    Check(resp, "update_rules");
}

AnnouncementResp GroupOperations::GetAnnouncement(const std::string& target_aid,
                                                   const std::string& group_id) {
    auto resp = client_->SendRequest(target_aid, group_id, "get_announcement");
    Check(resp, "get_announcement");
    auto d = ParseDataJson(resp);
    return {d.value("content", ""), d.value("updated_by", ""), d.value("updated_at", (int64_t)0)};
}

void GroupOperations::UpdateAnnouncement(const std::string& target_aid, const std::string& group_id,
                                         const std::string& content) {
    json params; params["content"] = content;
    auto resp = client_->SendRequest(target_aid, group_id, "update_announcement", params.dump());
    Check(resp, "update_announcement");
}

JoinRequirementsResp GroupOperations::GetJoinRequirements(const std::string& target_aid,
                                                          const std::string& group_id) {
    auto resp = client_->SendRequest(target_aid, group_id, "get_join_requirements");
    Check(resp, "get_join_requirements");
    auto d = ParseDataJson(resp);
    return {d.value("mode", ""), d.value("require_all", false)};
}

void GroupOperations::UpdateJoinRequirements(const std::string& target_aid,
                                             const std::string& group_id,
                                             const std::string& params_json) {
    auto resp = client_->SendRequest(target_aid, group_id, "update_join_requirements", params_json);
    Check(resp, "update_join_requirements");
}

void GroupOperations::SuspendGroup(const std::string& target_aid, const std::string& group_id) {
    auto resp = client_->SendRequest(target_aid, group_id, "suspend_group");
    Check(resp, "suspend_group");
}

void GroupOperations::ResumeGroup(const std::string& target_aid, const std::string& group_id) {
    auto resp = client_->SendRequest(target_aid, group_id, "resume_group");
    Check(resp, "resume_group");
}

void GroupOperations::TransferMaster(const std::string& target_aid, const std::string& group_id,
                                     const std::string& new_master_aid, const std::string& reason) {
    json params; params["new_master_aid"] = new_master_aid;
    if (!reason.empty()) params["reason"] = reason;
    auto resp = client_->SendRequest(target_aid, group_id, "transfer_master", params.dump());
    Check(resp, "transfer_master");
}

MasterResp GroupOperations::GetMaster(const std::string& target_aid, const std::string& group_id) {
    auto resp = client_->SendRequest(target_aid, group_id, "get_master");
    Check(resp, "get_master");
    auto d = ParseDataJson(resp);
    return {d.value("master", ""), d.value("master_transferred_at", (int64_t)0),
            d.value("transfer_reason", "")};
}

InviteCodeResp GroupOperations::CreateInviteCode(const std::string& target_aid,
                                                  const std::string& group_id,
                                                  const std::string& label, int max_uses,
                                                  int64_t expires_at) {
    json params;
    if (!label.empty()) params["label"] = label;
    if (max_uses > 0) params["max_uses"] = max_uses;
    if (expires_at > 0) params["expires_at"] = expires_at;
    std::string p = params.empty() ? "" : params.dump();
    auto resp = client_->SendRequest(target_aid, group_id, "create_invite_code", p);
    Check(resp, "create_invite_code");
    auto d = ParseDataJson(resp);
    InviteCodeResp r;
    r.code       = d.value("code", "");
    r.group_id   = d.value("group_id", "");
    r.created_by = d.value("created_by", "");
    r.created_at = d.value("created_at", (int64_t)0);
    r.label      = d.value("label", "");
    r.max_uses   = d.value("max_uses", 0);
    r.expires_at = d.value("expires_at", (int64_t)0);
    return r;
}

void GroupOperations::UseInviteCode(const std::string& target_aid, const std::string& group_id,
                                    const std::string& code) {
    json params; params["code"] = code;
    auto resp = client_->SendRequest(target_aid, group_id, "use_invite_code", params.dump());
    Check(resp, "use_invite_code");
}

InviteCodeListResp GroupOperations::ListInviteCodes(const std::string& target_aid,
                                                     const std::string& group_id) {
    auto resp = client_->SendRequest(target_aid, group_id, "list_invite_codes");
    Check(resp, "list_invite_codes");
    auto d = ParseDataJson(resp);
    InviteCodeListResp r;
    r.codes_json = d.contains("codes") ? d["codes"].dump() : "[]";
    return r;
}

void GroupOperations::RevokeInviteCode(const std::string& target_aid, const std::string& group_id,
                                       const std::string& code) {
    json params; params["code"] = code;
    auto resp = client_->SendRequest(target_aid, group_id, "revoke_invite_code", params.dump());
    Check(resp, "revoke_invite_code");
}

BroadcastLockResp GroupOperations::AcquireBroadcastLock(const std::string& target_aid,
                                                         const std::string& group_id) {
    auto resp = client_->SendRequest(target_aid, group_id, "acquire_broadcast_lock");
    Check(resp, "acquire_broadcast_lock");
    auto d = ParseDataJson(resp);
    return {d.value("acquired", false), d.value("expires_at", (int64_t)0), d.value("holder", "")};
}

void GroupOperations::ReleaseBroadcastLock(const std::string& target_aid,
                                           const std::string& group_id) {
    auto resp = client_->SendRequest(target_aid, group_id, "release_broadcast_lock");
    Check(resp, "release_broadcast_lock");
}

BroadcastPermissionResp GroupOperations::CheckBroadcastPermission(const std::string& target_aid,
                                                                   const std::string& group_id) {
    auto resp = client_->SendRequest(target_aid, group_id, "check_broadcast_permission");
    Check(resp, "check_broadcast_permission");
    auto d = ParseDataJson(resp);
    return {d.value("allowed", false), d.value("reason", "")};
}

// -- Duty (值班) Operations --

void GroupOperations::UpdateDutyConfig(const std::string& target_aid, const std::string& group_id,
                                       const std::string& config_json) {
    json params;
    try {
        params["duty_config"] = json::parse(config_json);
    } catch (...) {
        params["duty_config"] = json::object();
    }
    auto resp = client_->SendRequest(target_aid, group_id, "update_duty_config", params.dump());
    Check(resp, "update_duty_config");
}

void GroupOperations::SetFixedAgents(const std::string& target_aid, const std::string& group_id,
                                     const std::vector<std::string>& agents) {
    json params;
    params["agents"] = agents;
    auto resp = client_->SendRequest(target_aid, group_id, "set_fixed_agents", params.dump());
    Check(resp, "set_fixed_agents");
}

DutyStatusResp GroupOperations::GetDutyStatus(const std::string& target_aid,
                                               const std::string& group_id) {
    auto resp = client_->SendRequest(target_aid, group_id, "get_duty_status");
    Check(resp, "get_duty_status");
    auto d = ParseDataJson(resp);

    DutyStatusResp r;
    if (d.contains("config") && d["config"].is_object()) {
        auto& c = d["config"];
        r.config.mode                    = c.value("mode", "none");
        r.config.rotation_strategy       = c.value("rotation_strategy", "");
        r.config.shift_duration_ms       = c.value("shift_duration_ms", (int64_t)0);
        r.config.max_messages_per_shift  = c.value("max_messages_per_shift", 0);
        r.config.duty_priority_window_ms = c.value("duty_priority_window_ms", (int64_t)0);
        r.config.enable_rule_prelude     = c.value("enable_rule_prelude", false);
        r.config.agents                  = JsonToStringVec(c, "agents");
    }
    if (d.contains("state") && d["state"].is_object()) {
        auto& s = d["state"];
        r.state.current_duty_agent = s.value("current_duty_agent", "");
        r.state.shift_start_time   = s.value("shift_start_time", (int64_t)0);
        r.state.messages_in_shift  = s.value("messages_in_shift", 0);
        r.state.extra_json         = s.dump();
    }
    return r;
}

void GroupOperations::RefreshMemberTypes(const std::string& target_aid,
                                         const std::string& group_id) {
    auto resp = client_->SendRequest(target_aid, group_id, "refresh_member_types");
    Check(resp, "refresh_member_types");
}

// ============================================================
// Phase 4: SDK Convenience
// ============================================================

SyncStatusResp GroupOperations::GetSyncStatus(const std::string& target_aid,
                                              const std::string& group_id) {
    auto resp = client_->SendRequest(target_aid, group_id, "get_sync_status");
    Check(resp, "get_sync_status");
    auto d = ParseDataJson(resp);
    SyncStatusResp r;
    if (d.contains("msg_cursor")) {
        auto& mc = d["msg_cursor"];
        r.msg_cursor.start_msg_id   = mc.value("start_msg_id", (int64_t)0);
        r.msg_cursor.current_msg_id = mc.value("current_msg_id", (int64_t)0);
        r.msg_cursor.latest_msg_id  = mc.value("latest_msg_id", (int64_t)0);
        r.msg_cursor.unread_count   = mc.value("unread_count", (int64_t)0);
    }
    if (d.contains("event_cursor")) {
        auto& ec = d["event_cursor"];
        r.event_cursor.start_event_id   = ec.value("start_event_id", (int64_t)0);
        r.event_cursor.current_event_id = ec.value("current_event_id", (int64_t)0);
        r.event_cursor.latest_event_id  = ec.value("latest_event_id", (int64_t)0);
        r.event_cursor.unread_count     = ec.value("unread_count", (int64_t)0);
    }
    r.sync_percentage = d.value("sync_percentage", 0.0);
    return r;
}

SyncLogResp GroupOperations::GetSyncLog(const std::string& target_aid, const std::string& group_id,
                                        const std::string& start_date) {
    json params; params["start_date"] = start_date;
    auto resp = client_->SendRequest(target_aid, group_id, "get_sync_log", params.dump());
    Check(resp, "get_sync_log");
    auto d = ParseDataJson(resp);
    SyncLogResp r;
    r.entries_json = d.contains("entries") ? d["entries"].dump() : "[]";
    return r;
}

ChecksumResp GroupOperations::GetChecksum(const std::string& target_aid, const std::string& group_id,
                                          const std::string& file) {
    json params; params["file"] = file;
    auto resp = client_->SendRequest(target_aid, group_id, "get_checksum", params.dump());
    Check(resp, "get_checksum");
    auto d = ParseDataJson(resp);
    return {d.value("file", ""), d.value("checksum", "")};
}

ChecksumResp GroupOperations::GetMessageChecksum(const std::string& target_aid,
                                                  const std::string& group_id,
                                                  const std::string& date) {
    json params; params["date"] = date;
    auto resp = client_->SendRequest(target_aid, group_id, "get_message_checksum", params.dump());
    Check(resp, "get_message_checksum");
    auto d = ParseDataJson(resp);
    return {d.value("file", ""), d.value("checksum", "")};
}

PublicGroupInfoResp GroupOperations::GetPublicInfo(const std::string& target_aid,
                                                    const std::string& group_id) {
    auto resp = client_->SendRequest(target_aid, group_id, "get_public_info");
    Check(resp, "get_public_info");
    auto d = ParseDataJson(resp);
    PublicGroupInfoResp r;
    r.group_id     = d.value("group_id", "");
    r.name         = d.value("name", "");
    r.creator      = d.value("creator", "");
    r.visibility   = d.value("visibility", "");
    r.member_count = d.value("member_count", (int64_t)0);
    r.created_at   = d.value("created_at", (int64_t)0);
    r.alias        = d.value("alias", "");
    r.subject      = d.value("subject", "");
    r.tags         = JsonToStringVec(d, "tags");
    r.join_mode    = d.value("join_mode", "");
    return r;
}

SearchGroupsResp GroupOperations::SearchGroups(const std::string& target_aid,
                                               const std::string& keyword,
                                               const std::vector<std::string>& tags,
                                               int limit, int offset) {
    json params; params["keyword"] = keyword;
    if (!tags.empty()) params["tags"] = tags;
    if (limit > 0) params["limit"] = limit;
    if (offset > 0) params["offset"] = offset;
    auto resp = client_->SendRequest(target_aid, "", "search_groups", params.dump());
    Check(resp, "search_groups");
    auto d = ParseDataJson(resp);
    SearchGroupsResp r;
    r.total = d.value("total", 0);
    if (d.contains("groups") && d["groups"].is_array()) {
        for (auto& g : d["groups"]) {
            PublicGroupInfoResp info;
            info.group_id     = g.value("group_id", "");
            info.name         = g.value("name", "");
            info.creator      = g.value("creator", "");
            info.visibility   = g.value("visibility", "");
            info.member_count = g.value("member_count", (int64_t)0);
            info.created_at   = g.value("created_at", (int64_t)0);
            info.alias        = g.value("alias", "");
            info.subject      = g.value("subject", "");
            info.tags         = JsonToStringVec(g, "tags");
            info.join_mode    = g.value("join_mode", "");
            r.groups.push_back(std::move(info));
        }
    }
    return r;
}

DigestResp GroupOperations::GenerateDigest(const std::string& target_aid, const std::string& group_id,
                                           const std::string& date, const std::string& period) {
    json params; params["date"] = date; params["period"] = period;
    auto resp = client_->SendRequest(target_aid, group_id, "generate_digest", params.dump());
    Check(resp, "generate_digest");
    auto d = ParseDataJson(resp);
    DigestResp r;
    r.date                  = d.value("date", "");
    r.period                = d.value("period", "");
    r.message_count         = d.value("message_count", (int64_t)0);
    r.unique_senders        = d.value("unique_senders", (int64_t)0);
    r.data_size             = d.value("data_size", (int64_t)0);
    r.generated_at          = d.value("generated_at", (int64_t)0);
    r.top_contributors_json = d.contains("top_contributors") ? d["top_contributors"].dump() : "[]";
    return r;
}

DigestResp GroupOperations::GetDigest(const std::string& target_aid, const std::string& group_id,
                                      const std::string& date, const std::string& period) {
    json params; params["date"] = date; params["period"] = period;
    auto resp = client_->SendRequest(target_aid, group_id, "get_digest", params.dump());
    Check(resp, "get_digest");
    auto d = ParseDataJson(resp);
    DigestResp r;
    r.date                  = d.value("date", "");
    r.period                = d.value("period", "");
    r.message_count         = d.value("message_count", (int64_t)0);
    r.unique_senders        = d.value("unique_senders", (int64_t)0);
    r.data_size             = d.value("data_size", (int64_t)0);
    r.generated_at          = d.value("generated_at", (int64_t)0);
    r.top_contributors_json = d.contains("top_contributors") ? d["top_contributors"].dump() : "[]";
    return r;
}

// ============================================================
// Phase 5: Home AP Membership Index
// ============================================================

ListMyGroupsResp GroupOperations::ListMyGroups(const std::string& target_aid, int status) {
    json params;
    if (status != 0) params["status"] = status;
    std::string p = params.empty() ? "" : params.dump();
    auto resp = client_->SendRequest(target_aid, "", "list_my_groups", p);
    Check(resp, "list_my_groups");
    auto d = ParseDataJson(resp);
    ListMyGroupsResp r;
    r.total = d.value("total", 0);
    if (d.contains("groups") && d["groups"].is_array()) {
        for (auto& g : d["groups"]) {
            MembershipInfo info;
            info.group_id     = g.value("group_id", "");
            info.group_url    = g.value("group_url", "");
            info.group_server = g.value("group_server", "");
            info.session_id   = g.value("session_id", "");
            info.role         = g.value("role", "");
            info.status       = g.value("status", 0);
            info.created_at   = g.value("created_at", (int64_t)0);
            info.updated_at   = g.value("updated_at", (int64_t)0);
            r.groups.push_back(std::move(info));
        }
    }
    return r;
}

void GroupOperations::UnregisterMembership(const std::string& target_aid,
                                           const std::string& group_id) {
    auto resp = client_->SendRequest(target_aid, group_id, "unregister_membership");
    Check(resp, "unregister_membership");
}

void GroupOperations::ChangeMemberRole(const std::string& target_aid, const std::string& group_id,
                                       const std::string& agent_id, const std::string& new_role) {
    json params; params["agent_id"] = agent_id; params["new_role"] = new_role;
    auto resp = client_->SendRequest(target_aid, group_id, "change_member_role", params.dump());
    Check(resp, "change_member_role");
}

GetFileResp GroupOperations::GetFile(const std::string& target_aid, const std::string& group_id,
                                     const std::string& file, int64_t offset) {
    json params; params["file"] = file;
    if (offset > 0) params["offset"] = offset;
    auto resp = client_->SendRequest(target_aid, group_id, "get_file", params.dump());
    Check(resp, "get_file");
    auto d = ParseDataJson(resp);
    return {d.value("data", ""), d.value("total_size", (int64_t)0), d.value("offset", (int64_t)0)};
}

GetSummaryResp GroupOperations::GetSummary(const std::string& target_aid, const std::string& group_id,
                                           const std::string& date) {
    json params; params["date"] = date;
    auto resp = client_->SendRequest(target_aid, group_id, "get_summary", params.dump());
    Check(resp, "get_summary");
    auto d = ParseDataJson(resp);
    GetSummaryResp r;
    r.date          = d.value("date", "");
    r.message_count = d.value("message_count", (int64_t)0);
    r.senders       = JsonToStringVec(d, "senders");
    r.data_size     = d.value("data_size", (int64_t)0);
    return r;
}

GetMetricsResp GroupOperations::GetMetrics(const std::string& target_aid) {
    auto resp = client_->SendRequest(target_aid, "", "get_metrics");
    Check(resp, "get_metrics");
    auto d = ParseDataJson(resp);
    GetMetricsResp r;
    r.goroutines = d.value("goroutines", 0);
    r.alloc_mb   = d.value("alloc_mb", 0.0);
    r.sys_mb     = d.value("sys_mb", 0.0);
    r.gc_cycles  = d.value("gc_cycles", 0);
    return r;
}

}  // namespace group
}  // namespace agentcp
