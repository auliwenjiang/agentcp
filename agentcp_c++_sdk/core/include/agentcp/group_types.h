#pragma once

#include <cstdint>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

#include "agentcp/export.h"

namespace agentcp {
namespace group {

// ============================================================
// Error Codes
// ============================================================

enum class GroupErrorCode : int {
    SUCCESS             = 0,
    GROUP_NOT_FOUND     = 1001,
    NO_PERMISSION       = 1002,
    GROUP_DISSOLVED     = 1003,
    GROUP_SUSPENDED     = 1004,
    ALREADY_MEMBER      = 1005,
    NOT_MEMBER          = 1006,
    BANNED              = 1007,
    MEMBER_FULL         = 1008,
    INVALID_PARAMS      = 1009,
    RATE_LIMITED        = 1010,
    INVITE_CODE_INVALID = 1011,
    REQUEST_EXISTS      = 1012,
    BROADCAST_CONFLICT  = 1013,

    // Duty error codes
    DUTY_NOT_ENABLED    = 1020,
    NOT_DUTY_AGENT      = 1021,
    AGENT_MD_NOT_FOUND  = 1024,
    AGENT_MD_INVALID    = 1025,

    ACTION_NOT_IMPL     = 1099,
};

ACP_API const char* GroupErrorCodeMessage(int code);

// ============================================================
// GroupError Exception
// ============================================================
class ACP_API GroupError : public std::runtime_error {
public:
    GroupError(const std::string& action, int code,
              const std::string& error = "", const std::string& group_id = "");

    const std::string& action() const { return action_; }
    int code() const { return code_; }
    const std::string& error_msg() const { return error_; }
    const std::string& group_id() const { return group_id_; }

private:
    std::string action_;
    int code_;
    std::string error_;
    std::string group_id_;
};

// ============================================================
// Wire Protocol Types
// ============================================================

struct GroupRequest {
    std::string action;
    std::string request_id;
    std::string group_id;
    std::map<std::string, std::string> params_flat;  // simple k-v params
    std::string params_json;  // raw JSON params for complex objects
};

struct GroupResponse {
    std::string action;
    std::string request_id;
    int code = -1;
    std::string group_id;
    std::string data_json;  // raw JSON data
    std::string error;
};

struct GroupNotify {
    std::string action;  // always "group_notify"
    std::string group_id;
    std::string event;
    std::string data_json;  // raw JSON data
    int64_t timestamp = 0;
};

// ============================================================
// Domain Model Types
// ============================================================
struct GroupMessage {
    int64_t msg_id = 0;
    std::string sender;
    std::string content;
    std::string content_type;
    int64_t timestamp = 0;
    std::string metadata_json;  // optional JSON metadata
};

struct GroupMessageBatch {
    std::vector<GroupMessage> messages;
    int64_t start_msg_id = 0;
    int64_t latest_msg_id = 0;
    int count = 0;
};

struct GroupEvent {
    int64_t event_id = 0;
    std::string event_type;
    std::string actor;
    int64_t timestamp = 0;
    std::string target;
    std::string data_json;  // optional JSON data
};

struct MsgCursor {
    int64_t start_msg_id = 0;
    int64_t current_msg_id = 0;
    int64_t latest_msg_id = 0;
    int64_t unread_count = 0;
};

struct EventCursor {
    int64_t start_event_id = 0;
    int64_t current_event_id = 0;
    int64_t latest_event_id = 0;
    int64_t unread_count = 0;
};

struct CursorState {
    MsgCursor msg_cursor;
    EventCursor event_cursor;
};

// ============================================================
// Operation Response Types
// ============================================================

struct CreateGroupResp {
    std::string group_id;
    std::string group_url;
};

struct SendMessageResp {
    int64_t msg_id = 0;
    int64_t timestamp = 0;
};

struct PullMessagesResp {
    std::vector<GroupMessage> messages;
    bool has_more = false;
    int64_t latest_msg_id = 0;
};

struct PullEventsResp {
    std::vector<GroupEvent> events;
    bool has_more = false;
    int64_t latest_event_id = 0;
};
struct GroupInfoResp {
    std::string group_id;
    std::string name;
    std::string creator;
    std::string visibility;
    int64_t member_count = 0;
    int64_t created_at = 0;
    int64_t updated_at = 0;
    std::string alias;
    std::string subject;
    std::string status;
    std::vector<std::string> tags;
    std::string master;
};

struct BanlistResp {
    std::string banned_json;  // JSON array
};

struct RequestJoinResp {
    std::string status;      // "joined" or "pending"
    std::string request_id;
};

struct BatchReviewResp {
    int processed = 0;
    int total = 0;
};

struct PendingRequestsResp {
    std::string requests_json;  // JSON array
};

struct MembersResp {
    std::string members_json;  // JSON array
};

struct AdminsResp {
    std::string admins_json;  // JSON array
};

struct RulesResp {
    int max_members = 0;
    int max_message_size = 0;
    std::string broadcast_policy_json;
};

struct AnnouncementResp {
    std::string content;
    std::string updated_by;
    int64_t updated_at = 0;
};

struct JoinRequirementsResp {
    std::string mode;
    bool require_all = false;
};

struct MasterResp {
    std::string master;
    int64_t master_transferred_at = 0;
    std::string transfer_reason;
};

struct InviteCodeResp {
    std::string code;
    std::string group_id;
    std::string created_by;
    int64_t created_at = 0;
    std::string label;
    int max_uses = 0;
    int64_t expires_at = 0;
};

struct InviteCodeListResp {
    std::string codes_json;  // JSON array
};
struct BroadcastLockResp {
    bool acquired = false;
    int64_t expires_at = 0;
    std::string holder;
};

struct BroadcastPermissionResp {
    bool allowed = false;
    std::string reason;
};

struct SyncStatusResp {
    MsgCursor msg_cursor;
    EventCursor event_cursor;
    double sync_percentage = 0.0;
};

struct SyncLogResp {
    std::string entries_json;  // JSON array
};

struct ChecksumResp {
    std::string file;
    std::string checksum;
};

struct PublicGroupInfoResp {
    std::string group_id;
    std::string name;
    std::string creator;
    std::string visibility;
    int64_t member_count = 0;
    int64_t created_at = 0;
    std::string alias;
    std::string subject;
    std::vector<std::string> tags;
    std::string join_mode;
};

struct SearchGroupsResp {
    std::vector<PublicGroupInfoResp> groups;
    int total = 0;
};

struct DigestResp {
    std::string date;
    std::string period;
    int64_t message_count = 0;
    int64_t unique_senders = 0;
    int64_t data_size = 0;
    int64_t generated_at = 0;
    std::string top_contributors_json;  // JSON array
};

struct MembershipInfo {
    std::string group_id;
    std::string group_url;
    std::string group_server;
    std::string session_id;
    std::string role;
    int status = 0;
    int64_t created_at = 0;
    int64_t updated_at = 0;
};

struct ListMyGroupsResp {
    std::vector<MembershipInfo> groups;
    int total = 0;
};

struct GetFileResp {
    std::string data;
    int64_t total_size = 0;
    int64_t offset = 0;
};

struct GetSummaryResp {
    std::string date;
    int64_t message_count = 0;
    std::vector<std::string> senders;
    int64_t data_size = 0;
};

struct GetMetricsResp {
    int goroutines = 0;
    double alloc_mb = 0.0;
    double sys_mb = 0.0;
    int gc_cycles = 0;
};

// ============================================================
// Notify Event Constants
// ============================================================

constexpr const char* NOTIFY_NEW_MESSAGE           = "new_message";
constexpr const char* NOTIFY_NEW_EVENT             = "new_event";
constexpr const char* NOTIFY_GROUP_INVITE          = "group_invite";
constexpr const char* NOTIFY_JOIN_APPROVED         = "join_approved";
constexpr const char* NOTIFY_JOIN_REJECTED         = "join_rejected";
constexpr const char* NOTIFY_JOIN_REQUEST_RECEIVED = "join_request_received";
constexpr const char* NOTIFY_GROUP_MESSAGE          = "group_message";
constexpr const char* NOTIFY_GROUP_EVENT           = "group_event";

// Action constants
constexpr const char* ACTION_MESSAGE_BATCH_PUSH    = "message_batch_push";

// Group Event Type Constants
constexpr const char* EVENT_MEMBER_JOINED              = "member_joined";
constexpr const char* EVENT_MEMBER_REMOVED             = "member_removed";
constexpr const char* EVENT_MEMBER_LEFT                = "member_left";
constexpr const char* EVENT_MEMBER_BANNED              = "member_banned";
constexpr const char* EVENT_MEMBER_UNBANNED            = "member_unbanned";
constexpr const char* EVENT_META_UPDATED               = "meta_updated";
constexpr const char* EVENT_RULES_UPDATED              = "rules_updated";
constexpr const char* EVENT_ANNOUNCEMENT_UPDATED       = "announcement_updated";
constexpr const char* EVENT_GROUP_DISSOLVED            = "group_dissolved";
constexpr const char* EVENT_MASTER_TRANSFERRED         = "master_transferred";
constexpr const char* EVENT_GROUP_SUSPENDED            = "group_suspended";
constexpr const char* EVENT_GROUP_RESUMED              = "group_resumed";
constexpr const char* EVENT_JOIN_REQUIREMENTS_UPDATED  = "join_requirements_updated";
constexpr const char* EVENT_INVITE_CODE_CREATED        = "invite_code_created";
constexpr const char* EVENT_INVITE_CODE_REVOKED        = "invite_code_revoked";

// ============================================================
// Duty (值班) Types
// ============================================================

struct DutyConfig {
    std::string mode;                // "none", "fixed", "rotation"
    std::string rotation_strategy;   // "round_robin", "random"
    int64_t shift_duration_ms = 0;
    int max_messages_per_shift = 0;
    int64_t duty_priority_window_ms = 0;
    bool enable_rule_prelude = false;
    std::vector<std::string> agents;
};

struct DutyState {
    std::string current_duty_agent;
    int64_t shift_start_time = 0;
    int messages_in_shift = 0;
    std::string extra_json;  // additional dynamic fields
};

struct DutyStatusResp {
    DutyConfig config;
    DutyState state;
};

}  // namespace group
}  // namespace agentcp
