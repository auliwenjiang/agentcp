#include "agentcp/group_events.h"

#include "../acp_log.h"
#include "third_party/json.hpp"
using json = nlohmann::json;

namespace agentcp {
namespace group {

// ============================================================
// Helper: parse GroupMessage / GroupEvent from JSON
// ============================================================

static GroupMessage ParseGroupMessageFromJson(const json& j) {
    GroupMessage msg;
    msg.msg_id       = j.value("msg_id", (int64_t)0);
    msg.sender       = j.value("sender", "");
    msg.content      = j.value("content", "");
    msg.content_type = j.value("content_type", "");
    msg.timestamp    = j.value("timestamp", (int64_t)0);
    if (j.contains("metadata") && !j["metadata"].is_null()) {
        msg.metadata_json = j["metadata"].dump();
    }
    return msg;
}

static GroupEvent ParseGroupEventFromJson(const json& j) {
    GroupEvent evt;
    evt.event_id   = j.value("event_id", (int64_t)0);
    evt.event_type = j.value("event_type", "");
    evt.actor      = j.value("actor", "");
    evt.timestamp  = j.value("timestamp", (int64_t)0);
    evt.target     = j.value("target", "");
    if (j.contains("data") && !j["data"].is_null()) {
        evt.data_json = j["data"].dump();
    }
    return evt;
}

// ============================================================
// DispatchAcpNotify
// ============================================================

bool DispatchAcpNotify(ACPGroupEventHandler* handler, const GroupNotify& notify) {
    if (!handler) return false;

    json data;
    try {
        if (!notify.data_json.empty()) {
            data = json::parse(notify.data_json);
        }
    } catch (...) {
        data = json::object();
    }

    const auto& event = notify.event;
    const auto& gid = notify.group_id;

    try {
        if (event == NOTIFY_NEW_MESSAGE) {
            handler->OnNewMessage(gid,
                data.value("latest_msg_id", (int64_t)0),
                data.value("sender", ""),
                data.value("preview", ""));
        } else if (event == NOTIFY_NEW_EVENT) {
            handler->OnNewEvent(gid,
                data.value("latest_event_id", (int64_t)0),
                data.value("event_type", ""),
                data.value("summary", ""));
        } else if (event == NOTIFY_GROUP_INVITE) {
            handler->OnGroupInvite(gid,
                data.value("group_address", ""),
                data.value("invited_by", ""));
        } else if (event == NOTIFY_JOIN_APPROVED) {
            handler->OnJoinApproved(gid, data.value("group_address", ""));
        } else if (event == NOTIFY_JOIN_REJECTED) {
            handler->OnJoinRejected(gid, data.value("reason", ""));
        } else if (event == NOTIFY_JOIN_REQUEST_RECEIVED) {
            handler->OnJoinRequestReceived(gid,
                data.value("agent_id", ""),
                data.value("message", ""));
        } else if (event == NOTIFY_GROUP_MESSAGE) {
            handler->OnGroupMessage(gid, ParseGroupMessageFromJson(data));
        } else if (event == NOTIFY_GROUP_EVENT) {
            handler->OnGroupEvent(gid, ParseGroupEventFromJson(data));
        } else {
            return false;
        }
        return true;
    } catch (const std::exception& e) {
        ACP_LOGW("[GroupEvents] dispatch error for event=%s: %s", event.c_str(), e.what());
        return false;
    } catch (...) {
        ACP_LOGW("[GroupEvents] dispatch unknown error for event=%s", event.c_str());
        return false;
    }
}

// ============================================================
// DispatchEvent
// ============================================================

bool DispatchEvent(EventProcessor* processor, const std::string& msg_type,
                   const std::string& payload) {
    if (!processor) return false;

    json data;
    try {
        data = json::parse(payload);
    } catch (...) {
        return false;
    }

    std::string gid = data.value("group_id", "");
    std::string event = data.value("event", msg_type);

    try {
        if (event == EVENT_MEMBER_JOINED) {
            processor->OnMemberJoined(gid, data.value("agent_id", ""), data.value("role", ""));
        } else if (event == EVENT_MEMBER_REMOVED) {
            processor->OnMemberRemoved(gid, data.value("agent_id", ""), data.value("reason", ""));
        } else if (event == EVENT_MEMBER_LEFT) {
            processor->OnMemberLeft(gid, data.value("agent_id", ""), data.value("reason", ""));
        } else if (event == EVENT_MEMBER_BANNED) {
            processor->OnMemberBanned(gid, data.value("agent_id", ""), data.value("reason", ""));
        } else if (event == EVENT_MEMBER_UNBANNED) {
            processor->OnMemberUnbanned(gid, data.value("agent_id", ""));
        } else if (event == EVENT_ANNOUNCEMENT_UPDATED) {
            processor->OnAnnouncementUpdated(gid, data.value("updated_by", ""));
        } else if (event == EVENT_RULES_UPDATED) {
            processor->OnRulesUpdated(gid, data.value("updated_by", ""));
        } else if (event == EVENT_META_UPDATED) {
            processor->OnMetaUpdated(gid, data.value("updated_by", ""));
        } else if (event == EVENT_GROUP_DISSOLVED) {
            processor->OnGroupDissolved(gid, data.value("dissolved_by", ""), data.value("reason", ""));
        } else if (event == EVENT_MASTER_TRANSFERRED) {
            processor->OnMasterTransferred(gid, data.value("from_agent", ""),
                data.value("to_agent", ""), data.value("reason", ""));
        } else if (event == EVENT_GROUP_SUSPENDED) {
            processor->OnGroupSuspended(gid, data.value("suspended_by", ""), data.value("reason", ""));
        } else if (event == EVENT_GROUP_RESUMED) {
            processor->OnGroupResumed(gid, data.value("resumed_by", ""));
        } else if (event == EVENT_JOIN_REQUIREMENTS_UPDATED) {
            processor->OnJoinRequirementsUpdated(gid, data.value("updated_by", ""));
        } else if (event == EVENT_INVITE_CODE_CREATED) {
            processor->OnInviteCodeCreated(gid, data.value("code", ""), data.value("created_by", ""));
        } else if (event == EVENT_INVITE_CODE_REVOKED) {
            processor->OnInviteCodeRevoked(gid, data.value("code", ""), data.value("revoked_by", ""));
        } else {
            return false;
        }
        return true;
    } catch (const std::exception& e) {
        ACP_LOGW("[GroupEvents] dispatch_event error for %s: %s", event.c_str(), e.what());
        return false;
    } catch (...) {
        ACP_LOGW("[GroupEvents] dispatch_event unknown error for %s", event.c_str());
        return false;
    }
}

}  // namespace group
}  // namespace agentcp
