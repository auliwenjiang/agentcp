#import "AgentID.h"

#import <os/log.h>

#include "agentcp/agentcp.h"

namespace {

ACPResult *ResultFromCpp(const agentcp::Result &result) {
    NSString *message = result.message.empty() ? @"" : [NSString stringWithUTF8String:result.message.c_str()];
    NSString *context = result.context.empty() ? @"" : [NSString stringWithUTF8String:result.context.c_str()];
    return [[ACPResult alloc] initWithCode:result.code message:message context:context];
}

std::string ToStdString(NSString *value) {
    if (value == nil) return std::string();
    const char *utf8 = [value UTF8String];
    return utf8 ? std::string(utf8) : std::string();
}

NSString *ToNSString(const std::string &value) {
    return [NSString stringWithUTF8String:value.c_str()] ?: @"";
}

NSString *JsonStringFromObject(id obj) {
    if (obj == nil || ![NSJSONSerialization isValidJSONObject:obj]) {
        os_log_error(OS_LOG_DEFAULT, "[AgentID][JSON] invalid object for serialization");
        return @"{}";
    }
    NSError *error = nil;
    NSData *data = [NSJSONSerialization dataWithJSONObject:obj options:0 error:&error];
    if (error != nil || data == nil) {
        os_log_error(OS_LOG_DEFAULT, "[AgentID][JSON] serialization failed: %{public}@", error.localizedDescription ?: @"unknown");
        return @"{}";
    }
    NSString *json = [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding];
    if (json == nil) {
        os_log_error(OS_LOG_DEFAULT, "[AgentID][JSON] utf8 conversion failed after serialization");
        return @"{}";
    }
    return json;
}

id JsonObjectFromString(const std::string &text, id fallback) {
    if (text.empty()) return fallback;
    NSData *data = [NSData dataWithBytes:text.data() length:text.size()];
    if (data == nil) {
        os_log_error(OS_LOG_DEFAULT, "[AgentID][JSON] failed to create NSData from string");
        return fallback;
    }
    NSError *error = nil;
    id obj = [NSJSONSerialization JSONObjectWithData:data options:0 error:&error];
    if (error != nil || obj == nil) {
        os_log_error(OS_LOG_DEFAULT, "[AgentID][JSON] parse failed: %{public}@", error.localizedDescription ?: @"unknown");
        return fallback;
    }
    return obj;
}

}  // namespace

class ObjcSyncHandler : public agentcp::group::SyncHandler {
public:
    explicit ObjcSyncHandler(id<ACPGroupSyncHandler> handler) : handler_(handler) {}

    void OnMessages(const std::string& group_id, const std::vector<agentcp::group::GroupMessage>& messages) override {
        if (handler_ == nil) {
            os_log_error(OS_LOG_DEFAULT, "[AgentID][Group] OnMessages skipped: handler released");
            return;
        }
        NSMutableArray *arr = [NSMutableArray arrayWithCapacity:messages.size()];
        for (const auto &m : messages) {
            NSMutableDictionary *item = [@{
                @"msg_id": @(m.msg_id),
                @"sender": ToNSString(m.sender),
                @"content": ToNSString(m.content),
                @"content_type": ToNSString(m.content_type),
                @"timestamp": @(m.timestamp)
            } mutableCopy];
            id metadata = JsonObjectFromString(m.metadata_json, nil);
            if (metadata != nil) item[@"metadata"] = metadata;
            [arr addObject:item];
        }
        NSString *gid = ToNSString(group_id);
        NSString *messagesJson = JsonStringFromObject(arr);
        os_log_info(OS_LOG_DEFAULT, "[AgentID][Group] OnMessages dispatch: group=%{public}@ count=%lu", gid, (unsigned long)messages.size());
        @try {
            [handler_ onMessages:gid messagesJson:messagesJson];
        } @catch (NSException *exception) {
            os_log_error(OS_LOG_DEFAULT, "[AgentID][Group] OnMessages callback exception: %{public}@", exception.reason ?: @"unknown");
        }
    }

    void OnEvents(const std::string& group_id, const std::vector<agentcp::group::GroupEvent>& events) override {
        if (handler_ == nil) {
            os_log_error(OS_LOG_DEFAULT, "[AgentID][Group] OnEvents skipped: handler released");
            return;
        }
        NSMutableArray *arr = [NSMutableArray arrayWithCapacity:events.size()];
        for (const auto &e : events) {
            NSMutableDictionary *item = [@{
                @"event_id": @(e.event_id),
                @"event_type": ToNSString(e.event_type),
                @"actor": ToNSString(e.actor),
                @"timestamp": @(e.timestamp),
                @"target": ToNSString(e.target)
            } mutableCopy];
            id data = JsonObjectFromString(e.data_json, nil);
            if (data != nil) item[@"data"] = data;
            [arr addObject:item];
        }
        NSString *gid = ToNSString(group_id);
        NSString *eventsJson = JsonStringFromObject(arr);
        os_log_info(OS_LOG_DEFAULT, "[AgentID][Group] OnEvents dispatch: group=%{public}@ count=%lu", gid, (unsigned long)events.size());
        @try {
            [handler_ onEvents:gid eventsJson:eventsJson];
        } @catch (NSException *exception) {
            os_log_error(OS_LOG_DEFAULT, "[AgentID][Group] OnEvents callback exception: %{public}@", exception.reason ?: @"unknown");
        }
    }

private:
    __strong id<ACPGroupSyncHandler> handler_;
};

// Bridge: implements C++ ACPGroupEventHandler, dispatches to ObjC callbacks
class ObjcGroupEventHandler : public agentcp::group::ACPGroupEventHandler {
public:
    __strong id<ACPGroupMessageBatchCallback> msg_batch_cb;
    __strong id<ACPGroupEventCallback> evt_cb;

    void OnNewMessage(const std::string& group_id, int64_t latest_msg_id,
                      const std::string& sender, const std::string& preview) override {
        if (evt_cb == nil) return;
        @try {
            [evt_cb onNewMessage:ToNSString(group_id) latestMsgId:latest_msg_id
                          sender:ToNSString(sender) preview:ToNSString(preview)];
        } @catch (NSException *e) {
            os_log_error(OS_LOG_DEFAULT, "[AgentID][Group] OnNewMessage exception: %{public}@", e.reason);
        }
    }

    void OnNewEvent(const std::string& group_id, int64_t latest_event_id,
                    const std::string& event_type, const std::string& summary) override {
        if (evt_cb == nil) return;
        @try {
            [evt_cb onNewEvent:ToNSString(group_id) latestEventId:latest_event_id
                     eventType:ToNSString(event_type) summary:ToNSString(summary)];
        } @catch (NSException *e) {
            os_log_error(OS_LOG_DEFAULT, "[AgentID][Group] OnNewEvent exception: %{public}@", e.reason);
        }
    }

    void OnGroupInvite(const std::string& group_id, const std::string& group_address,
                       const std::string& invited_by) override {
        if (evt_cb == nil) return;
        @try {
            [evt_cb onGroupInvite:ToNSString(group_id) groupAddress:ToNSString(group_address)
                        invitedBy:ToNSString(invited_by)];
        } @catch (NSException *e) {
            os_log_error(OS_LOG_DEFAULT, "[AgentID][Group] OnGroupInvite exception: %{public}@", e.reason);
        }
    }

    void OnJoinApproved(const std::string& group_id, const std::string& group_address) override {
        if (evt_cb == nil) return;
        @try {
            [evt_cb onJoinApproved:ToNSString(group_id) groupAddress:ToNSString(group_address)];
        } @catch (NSException *e) {
            os_log_error(OS_LOG_DEFAULT, "[AgentID][Group] OnJoinApproved exception: %{public}@", e.reason);
        }
    }

    void OnJoinRejected(const std::string& group_id, const std::string& reason) override {
        if (evt_cb == nil) return;
        @try {
            [evt_cb onJoinRejected:ToNSString(group_id) reason:ToNSString(reason)];
        } @catch (NSException *e) {
            os_log_error(OS_LOG_DEFAULT, "[AgentID][Group] OnJoinRejected exception: %{public}@", e.reason);
        }
    }

    void OnJoinRequestReceived(const std::string& group_id, const std::string& agent_id,
                               const std::string& message) override {
        if (evt_cb == nil) return;
        @try {
            [evt_cb onJoinRequestReceived:ToNSString(group_id) agentId:ToNSString(agent_id)
                                  message:ToNSString(message)];
        } @catch (NSException *e) {
            os_log_error(OS_LOG_DEFAULT, "[AgentID][Group] OnJoinRequestReceived exception: %{public}@", e.reason);
        }
    }

    void OnGroupMessageBatch(const std::string& group_id, const agentcp::group::GroupMessageBatch& batch) override {
        if (msg_batch_cb == nil) return;
        // Serialize batch to JSON
        NSMutableArray *msgs = [NSMutableArray arrayWithCapacity:batch.messages.size()];
        for (const auto &m : batch.messages) {
            NSMutableDictionary *item = [@{
                @"msg_id": @(m.msg_id),
                @"sender": ToNSString(m.sender),
                @"content": ToNSString(m.content),
                @"content_type": ToNSString(m.content_type),
                @"timestamp": @(m.timestamp)
            } mutableCopy];
            id metadata = JsonObjectFromString(m.metadata_json, nil);
            if (metadata != nil) item[@"metadata"] = metadata;
            [msgs addObject:item];
        }
        NSDictionary *batchDict = @{
            @"messages": msgs,
            @"start_msg_id": @(batch.start_msg_id),
            @"latest_msg_id": @(batch.latest_msg_id),
            @"count": @(batch.count)
        };
        NSString *batchJson = JsonStringFromObject(batchDict);
        @try {
            [msg_batch_cb onGroupMessageBatch:ToNSString(group_id) batchJson:batchJson];
        } @catch (NSException *e) {
            os_log_error(OS_LOG_DEFAULT, "[AgentID][Group] OnGroupMessageBatch exception: %{public}@", e.reason);
        }
    }

    void OnGroupEvent(const std::string& group_id, const agentcp::group::GroupEvent& evt) override {
        if (evt_cb == nil) return;
        NSMutableDictionary *j = [@{
            @"event_id": @(evt.event_id),
            @"event_type": ToNSString(evt.event_type),
            @"actor": ToNSString(evt.actor),
            @"timestamp": @(evt.timestamp),
            @"target": ToNSString(evt.target)
        } mutableCopy];
        id data = JsonObjectFromString(evt.data_json, nil);
        if (data != nil) j[@"data"] = data;
        @try {
            [evt_cb onGroupEvent:ToNSString(group_id) eventJson:JsonStringFromObject(j)];
        } @catch (NSException *e) {
            os_log_error(OS_LOG_DEFAULT, "[AgentID][Group] OnGroupEvent exception: %{public}@", e.reason);
        }
    }
};

@interface ACPAgentID () {
    agentcp::AgentID *_native;
    std::unique_ptr<ObjcGroupEventHandler> _groupEventHandler;
    NSMutableSet<NSString *> *_onlineGroups;
    NSTimer *_heartbeatTimer;
    NSTimeInterval _heartbeatInterval;
}
@end

@implementation ACPAgentID

- (instancetype)initWithNative:(agentcp::AgentID *)native {
    self = [super init];
    if (self) {
        _native = native;
        _onlineGroups = [NSMutableSet new];
        _heartbeatInterval = 180.0; // 3 minutes, mirrors Android/Node SDK
    }
    return self;
}

- (ACPResult *)online {
    if (_native == nullptr || !_native->IsValid()) {
        return [[ACPResult alloc] initWithCode:static_cast<NSInteger>(agentcp::ErrorCode::AID_INVALID)
                                       message:@"invalid native handle"
                                       context:@""];
    }
    agentcp::Result r = _native->Online();
    return ResultFromCpp(r);
}

- (void)offline {
    if (_native != nullptr && _native->IsValid()) {
        _native->Offline();
    }
}

- (BOOL)isOnline {
    if (_native == nullptr || !_native->IsValid()) {
        return NO;
    }
    return _native->IsOnline() ? YES : NO;
}

- (ACPAgentState)state {
    if (_native == nullptr || !_native->IsValid()) {
        return ACPAgentStateError;
    }
    return static_cast<ACPAgentState>(_native->GetState());
}

- (NSString *)aid {
    if (_native == nullptr || !_native->IsValid()) {
        return @"";
    }
    std::string value = _native->GetAID();
    return [NSString stringWithUTF8String:value.c_str()];
}

- (void)initGroupClient:(NSString *)sessionId targetAid:(NSString *)targetAid {
    if (_native == nullptr || !_native->IsValid()) return;
    _native->InitGroupClient(ToStdString(sessionId), ToStdString(targetAid));
}

- (void)initGroupClient:(NSString *)sessionId {
    [self initGroupClient:sessionId targetAid:nil];
}

- (void)closeGroupClient {
    if (_native == nullptr || !_native->IsValid()) return;
    _native->CloseGroupClient();
}

- (NSString *)groupTargetAid {
    if (_native == nullptr || !_native->IsValid()) return @"";
    return ToNSString(_native->GetGroupTargetAid());
}
- (void)groupRegisterOnline {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return;
    _native->GroupOps()->RegisterOnline(_native->GetGroupTargetAid());
}
- (void)groupUnregisterOnline {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return;
    _native->GroupOps()->UnregisterOnline(_native->GetGroupTargetAid());
}
- (void)groupHeartbeat {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return;
    _native->GroupOps()->Heartbeat(_native->GetGroupTargetAid());
}

- (void)groupAckEvents:(NSString *)groupId eventId:(int64_t)eventId {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return;
    _native->GroupOps()->AckEvents(_native->GetGroupTargetAid(), ToStdString(groupId), eventId);
}

- (NSString *)groupGetCursor:(NSString *)groupId {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return @"{}";
    auto c = _native->GroupOps()->GetCursor(_native->GetGroupTargetAid(), ToStdString(groupId));
    NSDictionary *obj = @{
        @"msg_cursor": @{
            @"start_msg_id": @(c.msg_cursor.start_msg_id),
            @"current_msg_id": @(c.msg_cursor.current_msg_id),
            @"latest_msg_id": @(c.msg_cursor.latest_msg_id),
            @"unread_count": @(c.msg_cursor.unread_count)
        },
        @"event_cursor": @{
            @"start_event_id": @(c.event_cursor.start_event_id),
            @"current_event_id": @(c.event_cursor.current_event_id),
            @"latest_event_id": @(c.event_cursor.latest_event_id),
            @"unread_count": @(c.event_cursor.unread_count)
        }
    };
    return JsonStringFromObject(obj);
}

- (void)groupSync:(NSString *)groupId handler:(id<ACPGroupSyncHandler>)handler {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) {
        os_log_error(OS_LOG_DEFAULT, "[AgentID][Group] groupSync skipped: invalid native/group ops");
        return;
    }
    if (groupId == nil || [groupId length] == 0) {
        os_log_error(OS_LOG_DEFAULT, "[AgentID][Group] groupSync skipped: empty groupId");
        return;
    }
    if (handler == nil) {
        os_log_error(OS_LOG_DEFAULT, "[AgentID][Group] groupSync skipped: nil handler");
        return;
    }
    @try {
        os_log_info(OS_LOG_DEFAULT, "[AgentID][Group] groupSync start: %{public}@", groupId);
        ObjcSyncHandler syncHandler(handler);
        _native->GroupOps()->SyncGroup(_native->GetGroupTargetAid(), ToStdString(groupId), &syncHandler);
        os_log_info(OS_LOG_DEFAULT, "[AgentID][Group] groupSync completed: %{public}@", groupId);
    } @catch (NSException *exception) {
        os_log_error(OS_LOG_DEFAULT, "[AgentID][Group] groupSync objective-c exception: %{public}@", exception.reason ?: @"unknown");
    } catch (const std::exception &e) {
        os_log_error(OS_LOG_DEFAULT, "[AgentID][Group] groupSync c++ exception: %{public}s", e.what());
    } catch (...) {
        os_log_error(OS_LOG_DEFAULT, "[AgentID][Group] groupSync unknown exception");
    }
}

- (NSString *)groupJoinByUrl:(NSString *)groupUrl inviteCode:(NSString *)inviteCode message:(NSString *)message {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return @"";
    auto requestId = _native->GroupOps()->JoinByUrl(ToStdString(groupUrl), ToStdString(inviteCode), ToStdString(message));
    return ToNSString(requestId);
}

- (NSString *)groupRequestJoin:(NSString *)groupId message:(NSString *)message {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return @"";
    auto requestId = _native->GroupOps()->RequestJoin(_native->GetGroupTargetAid(), ToStdString(groupId), ToStdString(message));
    return ToNSString(requestId);
}

- (void)groupReviewJoinRequest:(NSString *)groupId agentId:(NSString *)agentId action:(NSString *)action reason:(NSString *)reason {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return;
    _native->GroupOps()->ReviewJoinRequest(_native->GetGroupTargetAid(), ToStdString(groupId), ToStdString(agentId), ToStdString(action), ToStdString(reason));
}

- (NSString *)groupBatchReviewJoinRequests:(NSString *)groupId
                                  agentIds:(NSArray<NSString *> *)agentIds
                                    action:(NSString *)action
                                    reason:(NSString *)reason {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return @"{}";
    std::vector<std::string> ids;
    for (NSString *aid in agentIds) ids.push_back(ToStdString(aid));
    auto r = _native->GroupOps()->BatchReviewJoinRequests(_native->GetGroupTargetAid(), ToStdString(groupId), ids, ToStdString(action), ToStdString(reason));
    return JsonStringFromObject(@{@"processed": @(r.processed), @"total": @(r.total)});
}

- (NSString *)groupGetPendingRequests:(NSString *)groupId {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return @"{}";
    auto r = _native->GroupOps()->GetPendingRequests(_native->GetGroupTargetAid(), ToStdString(groupId));
    id arr = JsonObjectFromString(r.requests_json, @[]);
    return JsonStringFromObject(@{@"requests": arr ?: @[]});
}

- (void)groupUseInviteCode:(NSString *)groupId code:(NSString *)code {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return;
    _native->GroupOps()->UseInviteCode(_native->GetGroupTargetAid(), ToStdString(groupId), ToStdString(code));
}
- (NSString *)groupCreateGroup:(NSString *)name
                         alias:(NSString *)alias
                        subject:(NSString *)subject
                     visibility:(NSString *)visibility
                    description:(NSString *)description
                          tags:(NSArray<NSString *> *)tags {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return @"{}";
    std::vector<std::string> tagVec;
    for (NSString *tag in (tags ?: @[])) {
        const char *u = [tag UTF8String];
        if (u) tagVec.emplace_back(u);
    }
    auto r = _native->GroupOps()->CreateGroup(
        _native->GetGroupTargetAid(),
        name ? std::string([name UTF8String]) : std::string(),
        alias ? std::string([alias UTF8String]) : std::string(),
        subject ? std::string([subject UTF8String]) : std::string(),
        visibility ? std::string([visibility UTF8String]) : std::string(),
        description ? std::string([description UTF8String]) : std::string(),
        tagVec
    );
    NSDictionary *obj = @{
        @"group_id": [NSString stringWithUTF8String:r.group_id.c_str()] ?: @"",
        @"group_url": [NSString stringWithUTF8String:r.group_url.c_str()] ?: @""
    };
    NSError *error = nil;
    NSData *data = [NSJSONSerialization dataWithJSONObject:obj options:0 error:&error];
    if (error || !data) return @"{}";
    return [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding] ?: @"{}";
}
- (void)groupAddMember:(NSString *)groupId agentId:(NSString *)agentId role:(NSString *)role {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return;
    _native->GroupOps()->AddMember(
        _native->GetGroupTargetAid(),
        groupId ? std::string([groupId UTF8String]) : std::string(),
        agentId ? std::string([agentId UTF8String]) : std::string(),
        role ? std::string([role UTF8String]) : std::string()
    );
}
- (NSString *)groupSendMessage:(NSString *)groupId
                        content:(NSString *)content
                    contentType:(NSString *)contentType
                   metadataJson:(NSString *)metadataJson {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return @"{}";
    auto r = _native->GroupOps()->SendGroupMessage(
        _native->GetGroupTargetAid(),
        groupId ? std::string([groupId UTF8String]) : std::string(),
        content ? std::string([content UTF8String]) : std::string(),
        contentType ? std::string([contentType UTF8String]) : std::string(),
        metadataJson ? std::string([metadataJson UTF8String]) : std::string()
    );
    NSDictionary *obj = @{@"msg_id": @(r.msg_id), @"timestamp": @(r.timestamp)};
    NSError *error = nil;
    NSData *data = [NSJSONSerialization dataWithJSONObject:obj options:0 error:&error];
    if (error || !data) return @"{}";
    return [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding] ?: @"{}";
}
- (NSString *)groupPullMessages:(NSString *)groupId afterMsgId:(int64_t)afterMsgId limit:(NSInteger)limit {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return @"{}";
    auto r = _native->GroupOps()->PullMessages(
        _native->GetGroupTargetAid(),
        groupId ? std::string([groupId UTF8String]) : std::string(),
        afterMsgId,
        (int)limit
    );
    NSMutableArray *msgs = [NSMutableArray arrayWithCapacity:r.messages.size()];
    for (const auto &m : r.messages) {
        NSMutableDictionary *item = [@{
            @"msg_id": @(m.msg_id),
            @"sender": [NSString stringWithUTF8String:m.sender.c_str()] ?: @"",
            @"content": [NSString stringWithUTF8String:m.content.c_str()] ?: @"",
            @"content_type": [NSString stringWithUTF8String:m.content_type.c_str()] ?: @"",
            @"timestamp": @(m.timestamp)
        } mutableCopy];
        if (!m.metadata_json.empty()) {
            NSData *md = [NSData dataWithBytes:m.metadata_json.data() length:m.metadata_json.size()];
            if (md) {
                id mo = [NSJSONSerialization JSONObjectWithData:md options:0 error:nil];
                if (mo) item[@"metadata"] = mo;
            }
        }
        [msgs addObject:item];
    }
    NSDictionary *obj = @{@"messages": msgs, @"has_more": @(r.has_more), @"latest_msg_id": @(r.latest_msg_id)};
    NSData *data = [NSJSONSerialization dataWithJSONObject:obj options:0 error:nil];
    return data ? ([[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding] ?: @"{}") : @"{}";
}
- (void)groupAckMessages:(NSString *)groupId msgId:(int64_t)msgId {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return;
    _native->GroupOps()->AckMessages(
        _native->GetGroupTargetAid(),
        groupId ? std::string([groupId UTF8String]) : std::string(),
        msgId
    );
}
- (NSString *)groupPullEvents:(NSString *)groupId afterEventId:(int64_t)afterEventId limit:(NSInteger)limit {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return @"{}";
    auto r = _native->GroupOps()->PullEvents(
        _native->GetGroupTargetAid(),
        groupId ? std::string([groupId UTF8String]) : std::string(),
        afterEventId,
        (int)limit
    );
    NSMutableArray *evts = [NSMutableArray arrayWithCapacity:r.events.size()];
    for (const auto &e : r.events) {
        NSMutableDictionary *item = [@{
            @"event_id": @(e.event_id),
            @"event_type": [NSString stringWithUTF8String:e.event_type.c_str()] ?: @"",
            @"actor": [NSString stringWithUTF8String:e.actor.c_str()] ?: @"",
            @"timestamp": @(e.timestamp),
            @"target": [NSString stringWithUTF8String:e.target.c_str()] ?: @""
        } mutableCopy];
        if (!e.data_json.empty()) {
            NSData *dd = [NSData dataWithBytes:e.data_json.data() length:e.data_json.size()];
            if (dd) {
                id dobj = [NSJSONSerialization JSONObjectWithData:dd options:0 error:nil];
                if (dobj) item[@"data"] = dobj;
            }
        }
        [evts addObject:item];
    }
    NSDictionary *obj = @{@"events": evts, @"has_more": @(r.has_more), @"latest_event_id": @(r.latest_event_id)};
    NSData *data = [NSJSONSerialization dataWithJSONObject:obj options:0 error:nil];
    return data ? ([[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding] ?: @"{}") : @"{}";
}
- (NSString *)groupGetInfo:(NSString *)groupId {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return @"{}";
    auto i = _native->GroupOps()->GetGroupInfo(_native->GetGroupTargetAid(), ToStdString(groupId));
    NSMutableArray *tags = [NSMutableArray arrayWithCapacity:i.tags.size()];
    for (const auto &t : i.tags) [tags addObject:ToNSString(t)];
    return JsonStringFromObject(@{
        @"group_id": ToNSString(i.group_id),
        @"name": ToNSString(i.name),
        @"creator": ToNSString(i.creator),
        @"visibility": ToNSString(i.visibility),
        @"member_count": @(i.member_count),
        @"created_at": @(i.created_at),
        @"updated_at": @(i.updated_at),
        @"alias": ToNSString(i.alias),
        @"subject": ToNSString(i.subject),
        @"status": ToNSString(i.status),
        @"tags": tags,
        @"master": ToNSString(i.master)
    });
}
- (void)groupUpdateMeta:(NSString *)groupId paramsJson:(NSString *)paramsJson {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return;
    _native->GroupOps()->UpdateGroupMeta(_native->GetGroupTargetAid(), ToStdString(groupId), ToStdString(paramsJson));
}
- (NSString *)groupGetMembers:(NSString *)groupId {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return @"{}";
    auto r = _native->GroupOps()->GetMembers(_native->GetGroupTargetAid(), ToStdString(groupId));
    return JsonStringFromObject(@{@"members": JsonObjectFromString(r.members_json, @[]) ?: @[]});
}
- (NSString *)groupGetAdmins:(NSString *)groupId {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return @"{}";
    auto r = _native->GroupOps()->GetAdmins(_native->GetGroupTargetAid(), ToStdString(groupId));
    return JsonStringFromObject(@{@"admins": JsonObjectFromString(r.admins_json, @[]) ?: @[]});
}
- (NSString *)groupGetRules:(NSString *)groupId {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return @"{}";
    auto r = _native->GroupOps()->GetRules(_native->GetGroupTargetAid(), ToStdString(groupId));
    NSMutableDictionary *obj = [@{
        @"max_members": @(r.max_members),
        @"max_message_size": @(r.max_message_size)
    } mutableCopy];
    id policy = JsonObjectFromString(r.broadcast_policy_json, nil);
    if (policy) obj[@"broadcast_policy"] = policy;
    return JsonStringFromObject(obj);
}
- (void)groupUpdateRules:(NSString *)groupId paramsJson:(NSString *)paramsJson {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return;
    _native->GroupOps()->UpdateRules(_native->GetGroupTargetAid(), ToStdString(groupId), ToStdString(paramsJson));
}
- (NSString *)groupGetAnnouncement:(NSString *)groupId {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return @"{}";
    auto r = _native->GroupOps()->GetAnnouncement(_native->GetGroupTargetAid(), ToStdString(groupId));
    return JsonStringFromObject(@{
        @"content": ToNSString(r.content),
        @"updated_by": ToNSString(r.updated_by),
        @"updated_at": @(r.updated_at)
    });
}
- (void)groupUpdateAnnouncement:(NSString *)groupId content:(NSString *)content {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return;
    _native->GroupOps()->UpdateAnnouncement(_native->GetGroupTargetAid(), ToStdString(groupId), ToStdString(content));
}
- (NSString *)groupGetJoinRequirements:(NSString *)groupId {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return @"{}";
    auto r = _native->GroupOps()->GetJoinRequirements(_native->GetGroupTargetAid(), ToStdString(groupId));
    return JsonStringFromObject(@{@"mode": ToNSString(r.mode), @"require_all": @(r.require_all)});
}
- (void)groupUpdateJoinRequirements:(NSString *)groupId paramsJson:(NSString *)paramsJson {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return;
    _native->GroupOps()->UpdateJoinRequirements(_native->GetGroupTargetAid(), ToStdString(groupId), ToStdString(paramsJson));
}
- (void)groupSuspend:(NSString *)groupId {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return;
    _native->GroupOps()->SuspendGroup(_native->GetGroupTargetAid(), ToStdString(groupId));
}
- (void)groupResume:(NSString *)groupId {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return;
    _native->GroupOps()->ResumeGroup(_native->GetGroupTargetAid(), ToStdString(groupId));
}
- (void)groupTransferMaster:(NSString *)groupId newMasterAid:(NSString *)newMasterAid reason:(NSString *)reason {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return;
    _native->GroupOps()->TransferMaster(_native->GetGroupTargetAid(), ToStdString(groupId), ToStdString(newMasterAid), ToStdString(reason));
}
- (NSString *)groupGetMaster:(NSString *)groupId {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return @"{}";
    auto r = _native->GroupOps()->GetMaster(_native->GetGroupTargetAid(), ToStdString(groupId));
    return JsonStringFromObject(@{
        @"master": ToNSString(r.master),
        @"master_transferred_at": @(r.master_transferred_at),
        @"transfer_reason": ToNSString(r.transfer_reason)
    });
}
- (NSString *)groupCreateInviteCode:(NSString *)groupId
                               label:(NSString *)label
                             maxUses:(NSInteger)maxUses
                            expiresAt:(int64_t)expiresAt {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return @"{}";
    auto r = _native->GroupOps()->CreateInviteCode(_native->GetGroupTargetAid(), ToStdString(groupId), ToStdString(label), (int)maxUses, expiresAt);
    return JsonStringFromObject(@{
        @"code": ToNSString(r.code),
        @"group_id": ToNSString(r.group_id),
        @"created_by": ToNSString(r.created_by),
        @"created_at": @(r.created_at),
        @"label": ToNSString(r.label),
        @"max_uses": @(r.max_uses),
        @"expires_at": @(r.expires_at)
    });
}
- (NSString *)groupListInviteCodes:(NSString *)groupId {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return @"{}";
    auto r = _native->GroupOps()->ListInviteCodes(_native->GetGroupTargetAid(), ToStdString(groupId));
    return JsonStringFromObject(@{@"codes": JsonObjectFromString(r.codes_json, @[]) ?: @[]});
}
- (void)groupRevokeInviteCode:(NSString *)groupId code:(NSString *)code {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return;
    _native->GroupOps()->RevokeInviteCode(_native->GetGroupTargetAid(), ToStdString(groupId), ToStdString(code));
}
- (NSString *)groupAcquireBroadcastLock:(NSString *)groupId {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return @"{}";
    auto r = _native->GroupOps()->AcquireBroadcastLock(_native->GetGroupTargetAid(), ToStdString(groupId));
    return JsonStringFromObject(@{
        @"acquired": @(r.acquired),
        @"expires_at": @(r.expires_at),
        @"holder": ToNSString(r.holder)
    });
}
- (void)groupReleaseBroadcastLock:(NSString *)groupId {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return;
    _native->GroupOps()->ReleaseBroadcastLock(_native->GetGroupTargetAid(), ToStdString(groupId));
}
- (NSString *)groupCheckBroadcastPermission:(NSString *)groupId {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return @"{}";
    auto r = _native->GroupOps()->CheckBroadcastPermission(_native->GetGroupTargetAid(), ToStdString(groupId));
    return JsonStringFromObject(@{
        @"allowed": @(r.allowed),
        @"reason": ToNSString(r.reason)
    });
}
- (void)groupRemoveMember:(NSString *)groupId agentId:(NSString *)agentId {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return;
    _native->GroupOps()->RemoveMember(_native->GetGroupTargetAid(), ToStdString(groupId), ToStdString(agentId));
}
- (void)groupLeaveGroup:(NSString *)groupId {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return;
    _native->GroupOps()->LeaveGroup(_native->GetGroupTargetAid(), ToStdString(groupId));
}
- (void)groupDissolveGroup:(NSString *)groupId {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return;
    _native->GroupOps()->DissolveGroup(_native->GetGroupTargetAid(), ToStdString(groupId));
}
- (void)groupBanAgent:(NSString *)groupId agentId:(NSString *)agentId reason:(NSString *)reason expiresAt:(int64_t)expiresAt {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return;
    _native->GroupOps()->BanAgent(_native->GetGroupTargetAid(), ToStdString(groupId), ToStdString(agentId), ToStdString(reason), expiresAt);
}
- (void)groupUnbanAgent:(NSString *)groupId agentId:(NSString *)agentId {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return;
    _native->GroupOps()->UnbanAgent(_native->GetGroupTargetAid(), ToStdString(groupId), ToStdString(agentId));
}
- (NSString *)groupGetBanlist:(NSString *)groupId {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return @"{}";
    auto r = _native->GroupOps()->GetBanlist(_native->GetGroupTargetAid(), ToStdString(groupId));
    return JsonStringFromObject(@{@"banned": JsonObjectFromString(r.banned_json, @[]) ?: @[]});
}
- (NSString *)groupGetSyncStatus:(NSString *)groupId {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return @"{}";
    auto r = _native->GroupOps()->GetSyncStatus(_native->GetGroupTargetAid(), ToStdString(groupId));
    return JsonStringFromObject(@{
        @"msg_cursor": @{
            @"start_msg_id": @(r.msg_cursor.start_msg_id),
            @"current_msg_id": @(r.msg_cursor.current_msg_id),
            @"latest_msg_id": @(r.msg_cursor.latest_msg_id),
            @"unread_count": @(r.msg_cursor.unread_count)
        },
        @"event_cursor": @{
            @"start_event_id": @(r.event_cursor.start_event_id),
            @"current_event_id": @(r.event_cursor.current_event_id),
            @"latest_event_id": @(r.event_cursor.latest_event_id),
            @"unread_count": @(r.event_cursor.unread_count)
        },
        @"sync_percentage": @(r.sync_percentage)
    });
}
- (NSString *)groupGetSyncLog:(NSString *)groupId startDate:(NSString *)startDate {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return @"{}";
    auto r = _native->GroupOps()->GetSyncLog(_native->GetGroupTargetAid(), ToStdString(groupId), ToStdString(startDate));
    return JsonStringFromObject(@{@"entries": JsonObjectFromString(r.entries_json, @[]) ?: @[]});
}
- (NSString *)groupGetChecksum:(NSString *)groupId file:(NSString *)file {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return @"{}";
    auto r = _native->GroupOps()->GetChecksum(_native->GetGroupTargetAid(), ToStdString(groupId), ToStdString(file));
    return JsonStringFromObject(@{@"file": ToNSString(r.file), @"checksum": ToNSString(r.checksum)});
}
- (NSString *)groupGetMessageChecksum:(NSString *)groupId date:(NSString *)date {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return @"{}";
    auto r = _native->GroupOps()->GetMessageChecksum(_native->GetGroupTargetAid(), ToStdString(groupId), ToStdString(date));
    return JsonStringFromObject(@{@"file": ToNSString(r.file), @"checksum": ToNSString(r.checksum)});
}
- (NSString *)groupGetPublicInfo:(NSString *)groupId {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return @"{}";
    auto i = _native->GroupOps()->GetPublicInfo(_native->GetGroupTargetAid(), ToStdString(groupId));
    NSMutableArray *tags = [NSMutableArray arrayWithCapacity:i.tags.size()];
    for (const auto &t : i.tags) [tags addObject:ToNSString(t)];
    return JsonStringFromObject(@{
        @"group_id": ToNSString(i.group_id),
        @"name": ToNSString(i.name),
        @"creator": ToNSString(i.creator),
        @"visibility": ToNSString(i.visibility),
        @"member_count": @(i.member_count),
        @"created_at": @(i.created_at),
        @"alias": ToNSString(i.alias),
        @"subject": ToNSString(i.subject),
        @"tags": tags,
        @"join_mode": ToNSString(i.join_mode)
    });
}
- (NSString *)groupSearchGroups:(NSString *)keyword tags:(NSArray<NSString *> *)tags limit:(NSInteger)limit offset:(NSInteger)offset {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return @"{}";
    std::vector<std::string> tv;
    for (NSString *t in (tags ?: @[])) tv.push_back(ToStdString(t));
    auto r = _native->GroupOps()->SearchGroups(_native->GetGroupTargetAid(), ToStdString(keyword), tv, (int)limit, (int)offset);
    NSMutableArray *groups = [NSMutableArray arrayWithCapacity:r.groups.size()];
    for (const auto &g : r.groups) {
        NSMutableArray *gTags = [NSMutableArray arrayWithCapacity:g.tags.size()];
        for (const auto &t : g.tags) [gTags addObject:ToNSString(t)];
        [groups addObject:@{
            @"group_id": ToNSString(g.group_id),
            @"name": ToNSString(g.name),
            @"creator": ToNSString(g.creator),
            @"visibility": ToNSString(g.visibility),
            @"member_count": @(g.member_count),
            @"created_at": @(g.created_at),
            @"alias": ToNSString(g.alias),
            @"subject": ToNSString(g.subject),
            @"tags": gTags,
            @"join_mode": ToNSString(g.join_mode)
        }];
    }
    return JsonStringFromObject(@{@"groups": groups, @"total": @(r.total)});
}
- (NSString *)groupGenerateDigest:(NSString *)groupId date:(NSString *)date period:(NSString *)period {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return @"{}";
    auto r = _native->GroupOps()->GenerateDigest(_native->GetGroupTargetAid(), ToStdString(groupId), ToStdString(date), ToStdString(period));
    return JsonStringFromObject(@{
        @"date": ToNSString(r.date),
        @"period": ToNSString(r.period),
        @"message_count": @(r.message_count),
        @"unique_senders": @(r.unique_senders),
        @"data_size": @(r.data_size),
        @"generated_at": @(r.generated_at),
        @"top_contributors": JsonObjectFromString(r.top_contributors_json, @[]) ?: @[]
    });
}
- (NSString *)groupGetDigest:(NSString *)groupId date:(NSString *)date period:(NSString *)period {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return @"{}";
    auto r = _native->GroupOps()->GetDigest(_native->GetGroupTargetAid(), ToStdString(groupId), ToStdString(date), ToStdString(period));
    return JsonStringFromObject(@{
        @"date": ToNSString(r.date),
        @"period": ToNSString(r.period),
        @"message_count": @(r.message_count),
        @"unique_senders": @(r.unique_senders),
        @"data_size": @(r.data_size),
        @"generated_at": @(r.generated_at),
        @"top_contributors": JsonObjectFromString(r.top_contributors_json, @[]) ?: @[]
    });
}
- (NSString *)groupListMyGroups:(NSInteger)status {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return @"{}";
    auto r = _native->GroupOps()->ListMyGroups(_native->GetGroupTargetAid(), (int)status);
    NSMutableArray *groups = [NSMutableArray arrayWithCapacity:r.groups.size()];
    for (const auto &g : r.groups) {
        [groups addObject:@{
            @"group_id": ToNSString(g.group_id),
            @"group_url": ToNSString(g.group_url),
            @"group_server": ToNSString(g.group_server),
            @"session_id": ToNSString(g.session_id),
            @"role": ToNSString(g.role),
            @"status": @(g.status),
            @"created_at": @(g.created_at),
            @"updated_at": @(g.updated_at)
        }];
    }
    return JsonStringFromObject(@{@"groups": groups, @"total": @(r.total)});
}
- (void)groupUnregisterMembership:(NSString *)groupId {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return;
    _native->GroupOps()->UnregisterMembership(_native->GetGroupTargetAid(), ToStdString(groupId));
}
- (void)groupChangeMemberRole:(NSString *)groupId agentId:(NSString *)agentId newRole:(NSString *)newRole {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return;
    _native->GroupOps()->ChangeMemberRole(_native->GetGroupTargetAid(), ToStdString(groupId), ToStdString(agentId), ToStdString(newRole));
}
- (NSString *)groupGetFile:(NSString *)groupId file:(NSString *)file offset:(int64_t)offset {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return @"{}";
    auto r = _native->GroupOps()->GetFile(_native->GetGroupTargetAid(), ToStdString(groupId), ToStdString(file), offset);
    return JsonStringFromObject(@{@"data": ToNSString(r.data), @"total_size": @(r.total_size), @"offset": @(r.offset)});
}
- (NSString *)groupGetSummary:(NSString *)groupId date:(NSString *)date {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return @"{}";
    auto r = _native->GroupOps()->GetSummary(_native->GetGroupTargetAid(), ToStdString(groupId), ToStdString(date));
    NSMutableArray *senders = [NSMutableArray arrayWithCapacity:r.senders.size()];
    for (const auto &s : r.senders) [senders addObject:ToNSString(s)];
    return JsonStringFromObject(@{
        @"date": ToNSString(r.date),
        @"message_count": @(r.message_count),
        @"senders": senders,
        @"data_size": @(r.data_size)
    });
}
- (NSString *)groupGetMetrics {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return @"{}";
    auto r = _native->GroupOps()->GetMetrics(_native->GetGroupTargetAid());
    return JsonStringFromObject(@{
        @"goroutines": @(r.goroutines),
        @"alloc_mb": @(r.alloc_mb),
        @"sys_mb": @(r.sys_mb),
        @"gc_cycles": @(r.gc_cycles)
    });
}

- (void)dealloc {
    [self leaveAllGroupSessions];
    _groupEventHandler.reset();
    _native = nullptr;
}

// ===== Group push callback registration =====

- (void)setGroupMessageBatchHandler:(id<ACPGroupMessageBatchCallback>)callback {
    if (!_groupEventHandler) {
        _groupEventHandler = std::make_unique<ObjcGroupEventHandler>();
    }
    _groupEventHandler->msg_batch_cb = callback;
    if (_native != nullptr && _native->IsValid()) {
        _native->SetGroupEventHandler(_groupEventHandler.get());
    }
}

- (void)setGroupEventCallback:(id<ACPGroupEventCallback>)callback {
    if (!_groupEventHandler) {
        _groupEventHandler = std::make_unique<ObjcGroupEventHandler>();
    }
    _groupEventHandler->evt_cb = callback;
    if (_native != nullptr && _native->IsValid()) {
        _native->SetGroupEventHandler(_groupEventHandler.get());
    }
}

// ===== Group session lifecycle =====

- (void)joinGroupSession:(NSString *)groupId {
    if (_native == nullptr || !_native->IsValid() || _native->GroupOps() == nullptr) return;

    // 1. register_online
    _native->GroupOps()->RegisterOnline(_native->GetGroupTargetAid());

    // 2. Cold-start sync: pull messages after register_online
    @try {
        std::string gid = ToStdString(groupId);
        std::string targetAid = _native->GetGroupTargetAid();
        // Pull from after_msg_id=0 (auto-cursor mode) to catch up
        // Upper bound to prevent infinite loop on misbehaving server
        bool hasMore = true;
        int64_t afterMsgId = 0;
        int maxRounds = 100;
        while (hasMore && maxRounds-- > 0) {
            auto resp = _native->GroupOps()->PullMessages(targetAid, gid, afterMsgId, 50);
            if (resp.messages.empty()) break;
            // ACK last message
            int64_t lastId = resp.messages.back().msg_id;
            if (lastId <= afterMsgId) break; // safety: no progress
            if (lastId > 0) {
                _native->GroupOps()->AckMessages(targetAid, gid, lastId);
            }
            afterMsgId = lastId;
            hasMore = resp.has_more;
        }
        os_log_info(OS_LOG_DEFAULT, "[AgentID][Group] joinGroupSession cold-start sync done: %{public}@", groupId);
    } @catch (NSException *e) {
        os_log_error(OS_LOG_DEFAULT, "[AgentID][Group] joinGroupSession cold-start sync exception: %{public}@", e.reason);
    } catch (const std::exception &e) {
        os_log_error(OS_LOG_DEFAULT, "[AgentID][Group] joinGroupSession cold-start sync error: %{public}s", e.what());
    } catch (...) {
        os_log_error(OS_LOG_DEFAULT, "[AgentID][Group] joinGroupSession cold-start sync unknown error");
    }

    // 3. Add to online groups
    @synchronized (_onlineGroups) {
        [_onlineGroups addObject:groupId];
    }

    // 4. Start heartbeat if needed
    [self ensureHeartbeat];
    os_log_info(OS_LOG_DEFAULT, "[AgentID][Group] joinGroupSession: %{public}@", groupId);
}

- (void)leaveGroupSession:(NSString *)groupId {
    BOOL empty;
    @synchronized (_onlineGroups) {
        [_onlineGroups removeObject:groupId];
        empty = (_onlineGroups.count == 0);
    }
    if (empty) {
        @try {
            if (_native != nullptr && _native->IsValid() && _native->GroupOps() != nullptr) {
                _native->GroupOps()->UnregisterOnline(_native->GetGroupTargetAid());
            }
        } @catch (NSException *e) {
            os_log_error(OS_LOG_DEFAULT, "[AgentID][Group] unregisterOnline exception: %{public}@", e.reason);
        } catch (...) {}
        [self stopHeartbeat];
    }
}

- (void)leaveAllGroupSessions {
    NSArray<NSString *> *groups;
    @synchronized (_onlineGroups) {
        groups = [_onlineGroups allObjects];
    }
    for (NSString *gid in groups) {
        [self leaveGroupSession:gid];
    }
}

- (NSArray<NSString *> *)onlineGroups {
    @synchronized (_onlineGroups) {
        return [_onlineGroups allObjects];
    }
}

- (void)setHeartbeatInterval:(NSTimeInterval)intervalSeconds {
    _heartbeatInterval = intervalSeconds;
    if (_heartbeatTimer != nil) {
        [self stopHeartbeat];
        [self ensureHeartbeat];
    }
}

- (void)ensureHeartbeat {
    if (_heartbeatTimer != nil) return;
    BOOL empty;
    @synchronized (_onlineGroups) {
        empty = (_onlineGroups.count == 0);
    }
    if (empty) return;

    __weak typeof(self) weakSelf = self;
    // Schedule on main RunLoop to ensure timer fires regardless of calling thread
    dispatch_async(dispatch_get_main_queue(), ^{
        __strong typeof(weakSelf) strongSelf = weakSelf;
        if (!strongSelf || strongSelf->_heartbeatTimer != nil) return;
        strongSelf->_heartbeatTimer = [NSTimer scheduledTimerWithTimeInterval:strongSelf->_heartbeatInterval
                                                                       repeats:YES
                                                                         block:^(NSTimer *timer) {
            __strong typeof(weakSelf) innerSelf = weakSelf;
            if (innerSelf) {
                // Heartbeat calls C++ which may block; dispatch off main
                dispatch_async(dispatch_get_global_queue(DISPATCH_QUEUE_PRIORITY_DEFAULT, 0), ^{
                    [innerSelf sendHeartbeat];
                });
            } else {
                [timer invalidate];
            }
        }];
        os_log_info(OS_LOG_DEFAULT, "[AgentID][Group] heartbeat started: interval=%.0fs", strongSelf->_heartbeatInterval);
    });
}

- (void)stopHeartbeat {
    if (_heartbeatTimer != nil) {
        [_heartbeatTimer invalidate];
        _heartbeatTimer = nil;
        os_log_info(OS_LOG_DEFAULT, "[AgentID][Group] heartbeat stopped");
    }
}

- (void)sendHeartbeat {
    @try {
        if (_native != nullptr && _native->IsValid() && _native->GroupOps() != nullptr) {
            _native->GroupOps()->Heartbeat(_native->GetGroupTargetAid());
        }
    } @catch (NSException *e) {
        os_log_error(OS_LOG_DEFAULT, "[AgentID][Group] heartbeat exception: %{public}@", e.reason);
    } catch (...) {
        os_log_error(OS_LOG_DEFAULT, "[AgentID][Group] heartbeat error");
    }
}

@end
