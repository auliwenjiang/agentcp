#pragma once

#include <string>
#include <vector>

#include "agentcp/export.h"
#include "agentcp/group_types.h"

namespace agentcp {
namespace group {

class ACPGroupClient;

// ============================================================
// SyncHandler - callback interface for syncGroup
// ============================================================

class ACP_API SyncHandler {
public:
    virtual ~SyncHandler() = default;
    virtual void OnMessages(const std::string& group_id, const std::vector<GroupMessage>& messages) = 0;
    virtual void OnEvents(const std::string& group_id, const std::vector<GroupEvent>& events) = 0;
};

// ============================================================
// GroupOperations - all 5 phases of group operations
// ============================================================

class ACP_API GroupOperations {
public:
    explicit GroupOperations(ACPGroupClient* client);

    // -- Utility --

    /// Parse group URL into targetAid and groupId.
    /// e.g. "https://group.agentcp.io/aa6f95b5-..." => {"group.agentcp.io", "aa6f95b5-..."}
    struct ParsedGroupUrl {
        std::string target_aid;
        std::string group_id;
    };
    static ParsedGroupUrl ParseGroupUrl(const std::string& group_url);

    /// Join group by URL. With invite_code: no approval needed. Without: submit join request.
    /// Returns RequestJoinResp with status ("joined" or "pending") and request_id.
    RequestJoinResp JoinByUrl(const std::string& group_url,
                          const std::string& invite_code = "",
                          const std::string& message = "");

    // ============================================================
    // Phase 0: Lifecycle (register / heartbeat / unregister)
    // ============================================================

    /// Register online, tell group.ap client is online and can receive push.
    /// Call once when client starts or reconnects.
    void RegisterOnline(const std::string& target_aid);

    /// Graceful offline. Immediately removes from online list.
    void UnregisterOnline(const std::string& target_aid);

    /// Heartbeat keep-alive. Online registration has 5-min timeout,
    /// SDK should send periodically (recommended 2~4 minutes).
    void Heartbeat(const std::string& target_aid);

    // ============================================================
    // Phase 1: Basic Operations
    // ============================================================

    CreateGroupResp CreateGroup(const std::string& target_aid, const std::string& name,
                                const std::string& alias = "", const std::string& subject = "",
                                const std::string& visibility = "",
                                const std::string& description = "",
                                const std::vector<std::string>& tags = {});

    void AddMember(const std::string& target_aid, const std::string& group_id,
                   const std::string& agent_id, const std::string& role = "");

    SendMessageResp SendGroupMessage(const std::string& target_aid, const std::string& group_id,
                                     const std::string& content, const std::string& content_type = "",
                                     const std::string& metadata_json = "");

    /// Pull messages.
    /// - after_msg_id > 0: explicit position mode, pull from that ID onwards
    /// - after_msg_id = 0: auto-cursor mode (recommended), server computes from current_msg_id
    PullMessagesResp PullMessages(const std::string& target_aid, const std::string& group_id,
                                  int64_t after_msg_id = 0, int limit = 0);

    void AckMessages(const std::string& target_aid, const std::string& group_id, int64_t msg_id);

    PullEventsResp PullEvents(const std::string& target_aid, const std::string& group_id,
                              int64_t after_event_id, int limit = 0);

    void AckEvents(const std::string& target_aid, const std::string& group_id, int64_t event_id);

    CursorState GetCursor(const std::string& target_aid, const std::string& group_id);

    void SyncGroup(const std::string& target_aid, const std::string& group_id, SyncHandler* handler);

    // ============================================================
    // Phase 2: Management Operations
    // ============================================================

    void RemoveMember(const std::string& target_aid, const std::string& group_id,
                      const std::string& agent_id);

    void LeaveGroup(const std::string& target_aid, const std::string& group_id);

    void DissolveGroup(const std::string& target_aid, const std::string& group_id);

    void BanAgent(const std::string& target_aid, const std::string& group_id,
                  const std::string& agent_id, const std::string& reason = "",
                  int64_t expires_at = 0);

    void UnbanAgent(const std::string& target_aid, const std::string& group_id,
                    const std::string& agent_id);

    BanlistResp GetBanlist(const std::string& target_aid, const std::string& group_id);

    /// Returns request_id
    RequestJoinResp RequestJoin(const std::string& target_aid, const std::string& group_id,
                            const std::string& message = "");

    void ReviewJoinRequest(const std::string& target_aid, const std::string& group_id,
                           const std::string& agent_id, const std::string& action,
                           const std::string& reason = "");

    BatchReviewResp BatchReviewJoinRequests(const std::string& target_aid, const std::string& group_id,
                                            const std::vector<std::string>& agent_ids,
                                            const std::string& action, const std::string& reason = "");

    PendingRequestsResp GetPendingRequests(const std::string& target_aid, const std::string& group_id);

    // ============================================================
    // Phase 3: Full Features
    // ============================================================

    GroupInfoResp GetGroupInfo(const std::string& target_aid, const std::string& group_id);

    void UpdateGroupMeta(const std::string& target_aid, const std::string& group_id,
                         const std::string& params_json);

    MembersResp GetMembers(const std::string& target_aid, const std::string& group_id);

    AdminsResp GetAdmins(const std::string& target_aid, const std::string& group_id);

    RulesResp GetRules(const std::string& target_aid, const std::string& group_id);

    void UpdateRules(const std::string& target_aid, const std::string& group_id,
                     const std::string& params_json);

    AnnouncementResp GetAnnouncement(const std::string& target_aid, const std::string& group_id);

    void UpdateAnnouncement(const std::string& target_aid, const std::string& group_id,
                            const std::string& content);

    JoinRequirementsResp GetJoinRequirements(const std::string& target_aid, const std::string& group_id);

    void UpdateJoinRequirements(const std::string& target_aid, const std::string& group_id,
                                const std::string& params_json);

    void SuspendGroup(const std::string& target_aid, const std::string& group_id);

    void ResumeGroup(const std::string& target_aid, const std::string& group_id);

    void TransferMaster(const std::string& target_aid, const std::string& group_id,
                        const std::string& new_master_aid, const std::string& reason = "");

    MasterResp GetMaster(const std::string& target_aid, const std::string& group_id);

    InviteCodeResp CreateInviteCode(const std::string& target_aid, const std::string& group_id,
                                    const std::string& label = "", int max_uses = 0,
                                    int64_t expires_at = 0);

    void UseInviteCode(const std::string& target_aid, const std::string& group_id,
                       const std::string& code);

    InviteCodeListResp ListInviteCodes(const std::string& target_aid, const std::string& group_id);

    void RevokeInviteCode(const std::string& target_aid, const std::string& group_id,
                          const std::string& code);

    BroadcastLockResp AcquireBroadcastLock(const std::string& target_aid, const std::string& group_id);

    void ReleaseBroadcastLock(const std::string& target_aid, const std::string& group_id);

    BroadcastPermissionResp CheckBroadcastPermission(const std::string& target_aid,
                                                     const std::string& group_id);

    // -- Duty (值班) Operations --

    /// Update duty configuration. Requires creator or admin permission.
    void UpdateDutyConfig(const std::string& target_aid, const std::string& group_id,
                          const std::string& config_json);

    /// Shortcut to set fixed duty agents (auto-switches to "fixed" mode).
    void SetFixedAgents(const std::string& target_aid, const std::string& group_id,
                        const std::vector<std::string>& agents);

    /// Get duty status including config and state.
    DutyStatusResp GetDutyStatus(const std::string& target_aid, const std::string& group_id);

    /// Re-fetch all members' agent.md and update AgentType.
    void RefreshMemberTypes(const std::string& target_aid, const std::string& group_id);

    // ============================================================
    // Phase 4: SDK Convenience
    // ============================================================

    SyncStatusResp GetSyncStatus(const std::string& target_aid, const std::string& group_id);

    SyncLogResp GetSyncLog(const std::string& target_aid, const std::string& group_id,
                           const std::string& start_date);

    ChecksumResp GetChecksum(const std::string& target_aid, const std::string& group_id,
                             const std::string& file);

    ChecksumResp GetMessageChecksum(const std::string& target_aid, const std::string& group_id,
                                    const std::string& date);

    PublicGroupInfoResp GetPublicInfo(const std::string& target_aid, const std::string& group_id);

    SearchGroupsResp SearchGroups(const std::string& target_aid, const std::string& keyword,
                                  const std::vector<std::string>& tags = {},
                                  int limit = 0, int offset = 0);

    DigestResp GenerateDigest(const std::string& target_aid, const std::string& group_id,
                              const std::string& date, const std::string& period);

    DigestResp GetDigest(const std::string& target_aid, const std::string& group_id,
                         const std::string& date, const std::string& period);

    // ============================================================
    // Phase 5: Home AP Membership Index
    // ============================================================

    ListMyGroupsResp ListMyGroups(const std::string& target_aid, int status = 0);

    void UnregisterMembership(const std::string& target_aid, const std::string& group_id);

    void ChangeMemberRole(const std::string& target_aid, const std::string& group_id,
                          const std::string& agent_id, const std::string& new_role);

    GetFileResp GetFile(const std::string& target_aid, const std::string& group_id,
                        const std::string& file, int64_t offset = 0);

    GetSummaryResp GetSummary(const std::string& target_aid, const std::string& group_id,
                              const std::string& date);

    GetMetricsResp GetMetrics(const std::string& target_aid);

private:
    void Check(const GroupResponse& resp, const std::string& action);

    void SyncMessages(const std::string& target_aid, const std::string& group_id,
                      CursorState& cursor, SyncHandler* handler);
    void SyncEventsLoop(const std::string& target_aid, const std::string& group_id,
                        CursorState& cursor, SyncHandler* handler);

    ACPGroupClient* client_;
};

}  // namespace group
}  // namespace agentcp
