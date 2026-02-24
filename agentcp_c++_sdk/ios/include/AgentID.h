#import <Foundation/Foundation.h>

#import "AgentCPTypes.h"

NS_ASSUME_NONNULL_BEGIN

@protocol ACPGroupSyncHandler <NSObject>
- (void)onMessages:(NSString *)groupId messagesJson:(NSString *)messagesJson;
- (void)onEvents:(NSString *)groupId eventsJson:(NSString *)eventsJson;
@end

@protocol ACPGroupMessageBatchCallback <NSObject>
/// Called when a batch of group messages is pushed from group.ap.
/// @param groupId The group ID
/// @param batchJson JSON string: {"messages":[...], "start_msg_id":N, "latest_msg_id":N, "count":N}
- (void)onGroupMessageBatch:(NSString *)groupId batchJson:(NSString *)batchJson;
@end

@protocol ACPGroupEventCallback <NSObject>
- (void)onNewMessage:(NSString *)groupId latestMsgId:(int64_t)latestMsgId sender:(NSString *)sender preview:(NSString *)preview;
- (void)onNewEvent:(NSString *)groupId latestEventId:(int64_t)latestEventId eventType:(NSString *)eventType summary:(NSString *)summary;
- (void)onGroupInvite:(NSString *)groupId groupAddress:(NSString *)groupAddress invitedBy:(NSString *)invitedBy;
- (void)onJoinApproved:(NSString *)groupId groupAddress:(NSString *)groupAddress;
- (void)onJoinRejected:(NSString *)groupId reason:(NSString *)reason;
- (void)onJoinRequestReceived:(NSString *)groupId agentId:(NSString *)agentId message:(NSString *)message;
- (void)onGroupEvent:(NSString *)groupId eventJson:(NSString *)eventJson;
@end

@interface ACPAgentID : NSObject

- (ACPResult *)online;
- (void)offline;
- (BOOL)isOnline;
- (ACPAgentState)state;
- (NSString *)aid;

// Group module lifecycle
- (void)initGroupClient:(NSString *)sessionId targetAid:(nullable NSString *)targetAid;
- (void)initGroupClient:(NSString *)sessionId;
- (void)closeGroupClient;
- (NSString *)groupTargetAid;

// Group module operations (JSON string results for complex payloads)
- (void)groupRegisterOnline;
- (void)groupUnregisterOnline;
- (void)groupHeartbeat;
- (NSString *)groupCreateGroup:(NSString *)name
                         alias:(nullable NSString *)alias
                       subject:(nullable NSString *)subject
                    visibility:(nullable NSString *)visibility
                   description:(nullable NSString *)description
                          tags:(nullable NSArray<NSString *> *)tags;
- (void)groupAddMember:(NSString *)groupId agentId:(NSString *)agentId role:(nullable NSString *)role;
- (NSString *)groupSendMessage:(NSString *)groupId
                       content:(NSString *)content
                   contentType:(nullable NSString *)contentType
                  metadataJson:(nullable NSString *)metadataJson;
- (NSString *)groupPullMessages:(NSString *)groupId afterMsgId:(int64_t)afterMsgId limit:(NSInteger)limit;
- (void)groupAckMessages:(NSString *)groupId msgId:(int64_t)msgId;
- (NSString *)groupPullEvents:(NSString *)groupId afterEventId:(int64_t)afterEventId limit:(NSInteger)limit;
- (void)groupAckEvents:(NSString *)groupId eventId:(int64_t)eventId;
- (NSString *)groupGetCursor:(NSString *)groupId;
- (void)groupSync:(NSString *)groupId handler:(id<ACPGroupSyncHandler>)handler;
- (NSString *)groupJoinByUrl:(NSString *)groupUrl inviteCode:(nullable NSString *)inviteCode message:(nullable NSString *)message;
- (NSString *)groupRequestJoin:(NSString *)groupId message:(nullable NSString *)message;
- (void)groupReviewJoinRequest:(NSString *)groupId agentId:(NSString *)agentId action:(NSString *)action reason:(nullable NSString *)reason;
- (NSString *)groupBatchReviewJoinRequests:(NSString *)groupId
                                  agentIds:(NSArray<NSString *> *)agentIds
                                    action:(NSString *)action
                                    reason:(nullable NSString *)reason;
- (NSString *)groupGetPendingRequests:(NSString *)groupId;
- (void)groupUseInviteCode:(NSString *)groupId code:(NSString *)code;
- (NSString *)groupGetInfo:(NSString *)groupId;
- (void)groupUpdateMeta:(NSString *)groupId paramsJson:(NSString *)paramsJson;
- (NSString *)groupGetMembers:(NSString *)groupId;
- (NSString *)groupGetAdmins:(NSString *)groupId;
- (NSString *)groupGetRules:(NSString *)groupId;
- (void)groupUpdateRules:(NSString *)groupId paramsJson:(NSString *)paramsJson;
- (NSString *)groupGetAnnouncement:(NSString *)groupId;
- (void)groupUpdateAnnouncement:(NSString *)groupId content:(NSString *)content;
- (NSString *)groupGetJoinRequirements:(NSString *)groupId;
- (void)groupUpdateJoinRequirements:(NSString *)groupId paramsJson:(NSString *)paramsJson;
- (void)groupSuspend:(NSString *)groupId;
- (void)groupResume:(NSString *)groupId;
- (void)groupTransferMaster:(NSString *)groupId newMasterAid:(NSString *)newMasterAid reason:(nullable NSString *)reason;
- (NSString *)groupGetMaster:(NSString *)groupId;
- (NSString *)groupCreateInviteCode:(NSString *)groupId
                               label:(nullable NSString *)label
                             maxUses:(NSInteger)maxUses
                           expiresAt:(int64_t)expiresAt;
- (NSString *)groupListInviteCodes:(NSString *)groupId;
- (void)groupRevokeInviteCode:(NSString *)groupId code:(NSString *)code;
- (NSString *)groupAcquireBroadcastLock:(NSString *)groupId;
- (void)groupReleaseBroadcastLock:(NSString *)groupId;
- (NSString *)groupCheckBroadcastPermission:(NSString *)groupId;
- (void)groupRemoveMember:(NSString *)groupId agentId:(NSString *)agentId;
- (void)groupLeaveGroup:(NSString *)groupId;
- (void)groupDissolveGroup:(NSString *)groupId;
- (void)groupBanAgent:(NSString *)groupId agentId:(NSString *)agentId reason:(nullable NSString *)reason expiresAt:(int64_t)expiresAt;
- (void)groupUnbanAgent:(NSString *)groupId agentId:(NSString *)agentId;
- (NSString *)groupGetBanlist:(NSString *)groupId;
- (NSString *)groupGetSyncStatus:(NSString *)groupId;
- (NSString *)groupGetSyncLog:(NSString *)groupId startDate:(NSString *)startDate;
- (NSString *)groupGetChecksum:(NSString *)groupId file:(NSString *)file;
- (NSString *)groupGetMessageChecksum:(NSString *)groupId date:(NSString *)date;
- (NSString *)groupGetPublicInfo:(NSString *)groupId;
- (NSString *)groupSearchGroups:(NSString *)keyword tags:(nullable NSArray<NSString *> *)tags limit:(NSInteger)limit offset:(NSInteger)offset;
- (NSString *)groupGenerateDigest:(NSString *)groupId date:(NSString *)date period:(NSString *)period;
- (NSString *)groupGetDigest:(NSString *)groupId date:(NSString *)date period:(NSString *)period;
- (NSString *)groupListMyGroups:(NSInteger)status;
- (void)groupUnregisterMembership:(NSString *)groupId;
- (void)groupChangeMemberRole:(NSString *)groupId agentId:(NSString *)agentId newRole:(NSString *)newRole;
- (NSString *)groupGetFile:(NSString *)groupId file:(NSString *)file offset:(int64_t)offset;
- (NSString *)groupGetSummary:(NSString *)groupId date:(NSString *)date;
- (NSString *)groupGetMetrics;

// Group push callback registration
- (void)setGroupMessageBatchHandler:(nullable id<ACPGroupMessageBatchCallback>)callback;
- (void)setGroupEventCallback:(nullable id<ACPGroupEventCallback>)callback;

// Group session lifecycle (mirrors Android joinGroupSession/leaveGroupSession)
- (void)joinGroupSession:(NSString *)groupId;
- (void)leaveGroupSession:(NSString *)groupId;
- (void)leaveAllGroupSessions;
- (NSArray<NSString *> *)onlineGroups;
- (void)setHeartbeatInterval:(NSTimeInterval)intervalSeconds;

@end

NS_ASSUME_NONNULL_END
