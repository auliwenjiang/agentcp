#pragma once

#include <string>

#include "agentcp/export.h"
#include "agentcp/group_types.h"

namespace agentcp {
namespace group {

// ============================================================
// ACPGroupEventHandler - notification callbacks from server
// ============================================================

class ACP_API ACPGroupEventHandler {
public:
    virtual ~ACPGroupEventHandler() = default;

    virtual void OnNewMessage(const std::string& group_id, int64_t latest_msg_id,
                              const std::string& sender, const std::string& preview) = 0;
    virtual void OnNewEvent(const std::string& group_id, int64_t latest_event_id,
                            const std::string& event_type, const std::string& summary) = 0;
    virtual void OnGroupInvite(const std::string& group_id, const std::string& group_address,
                               const std::string& invited_by) = 0;
    virtual void OnJoinApproved(const std::string& group_id, const std::string& group_address) = 0;
    virtual void OnJoinRejected(const std::string& group_id, const std::string& reason) = 0;
    virtual void OnJoinRequestReceived(const std::string& group_id, const std::string& agent_id,
                                       const std::string& message) = 0;
    /// Optional: called on single message push (message_push action).
    /// Default implementation does nothing. Override to handle individual messages.
    virtual void OnGroupMessage(const std::string& group_id, const GroupMessage& msg) { (void)group_id; (void)msg; }
    virtual void OnGroupMessageBatch(const std::string& group_id, const GroupMessageBatch& batch) = 0;
    virtual void OnGroupEvent(const std::string& group_id, const GroupEvent& evt) = 0;
};

// ============================================================
// EventProcessor - structured group events from MSG/Session
// ============================================================

class ACP_API EventProcessor {
public:
    virtual ~EventProcessor() = default;

    virtual void OnMemberJoined(const std::string& group_id, const std::string& agent_id,
                                const std::string& role) = 0;
    virtual void OnMemberRemoved(const std::string& group_id, const std::string& agent_id,
                                 const std::string& reason) = 0;
    virtual void OnMemberLeft(const std::string& group_id, const std::string& agent_id,
                              const std::string& reason) = 0;
    virtual void OnMemberBanned(const std::string& group_id, const std::string& agent_id,
                                const std::string& reason) = 0;
    virtual void OnMemberUnbanned(const std::string& group_id, const std::string& agent_id) = 0;
    virtual void OnAnnouncementUpdated(const std::string& group_id, const std::string& updated_by) = 0;
    virtual void OnRulesUpdated(const std::string& group_id, const std::string& updated_by) = 0;
    virtual void OnMetaUpdated(const std::string& group_id, const std::string& updated_by) = 0;
    virtual void OnGroupDissolved(const std::string& group_id, const std::string& dissolved_by,
                                  const std::string& reason) = 0;
    virtual void OnMasterTransferred(const std::string& group_id, const std::string& from_agent,
                                     const std::string& to_agent, const std::string& reason) = 0;
    virtual void OnGroupSuspended(const std::string& group_id, const std::string& suspended_by,
                                  const std::string& reason) = 0;
    virtual void OnGroupResumed(const std::string& group_id, const std::string& resumed_by) = 0;
    virtual void OnJoinRequirementsUpdated(const std::string& group_id, const std::string& updated_by) = 0;
    virtual void OnInviteCodeCreated(const std::string& group_id, const std::string& code,
                                     const std::string& created_by) = 0;
    virtual void OnInviteCodeRevoked(const std::string& group_id, const std::string& code,
                                     const std::string& revoked_by) = 0;
};

// ============================================================
// Dispatch functions
// ============================================================

/// Dispatch an ACP group notification to the handler.
/// Returns true if dispatched, false if unrecognized or handler/notify is null.
ACP_API bool DispatchAcpNotify(ACPGroupEventHandler* handler, const GroupNotify& notify);

/// Dispatch a structured group event to EventProcessor.
/// Returns true if handled, false otherwise.
ACP_API bool DispatchEvent(EventProcessor* processor, const std::string& msg_type,
                           const std::string& payload);

}  // namespace group
}  // namespace agentcp
