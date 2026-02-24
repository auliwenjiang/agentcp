#import "AgentCP.h"

#import <dispatch/dispatch.h>

#import "AgentID.h"

#include <string>

#include "agentcp/agentcp.h"

namespace {

std::string ToStdString(NSString *value) {
    if (value == nil) {
        return std::string();
    }
    const char *utf8 = [value UTF8String];
    return utf8 ? std::string(utf8) : std::string();
}

ACPResult *ResultFromCpp(const agentcp::Result &result) {
    NSString *message = result.message.empty() ? @"" : [NSString stringWithUTF8String:result.message.c_str()];
    NSString *context = result.context.empty() ? @"" : [NSString stringWithUTF8String:result.context.c_str()];
    return [[ACPResult alloc] initWithCode:result.code message:message context:context];
}

}  // namespace

@interface ACPAgentID (Internal)
- (instancetype)initWithNative:(agentcp::AgentID *)native;
@end

@implementation ACPAgentCP

+ (instancetype)shared {
    static ACPAgentCP *instance = nil;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        instance = [[ACPAgentCP alloc] init];
    });
    return instance;
}

- (ACPResult *)initialize {
    agentcp::Result r = agentcp::AgentCP::Instance().Initialize();
    return ResultFromCpp(r);
}

- (void)shutdown {
    agentcp::AgentCP::Instance().Shutdown();
}

- (ACPResult *)setBaseUrls:(NSString *)caBase apBase:(NSString *)apBase {
    agentcp::Result r = agentcp::AgentCP::Instance().SetBaseUrls(ToStdString(caBase), ToStdString(apBase));
    return ResultFromCpp(r);
}

- (ACPResult *)setStoragePath:(NSString *)path {
    agentcp::Result r = agentcp::AgentCP::Instance().SetStoragePath(ToStdString(path));
    return ResultFromCpp(r);
}

- (ACPResult *)setLogLevel:(ACPLogLevel)level {
    agentcp::Result r = agentcp::AgentCP::Instance().SetLogLevel(static_cast<agentcp::LogLevel>(level));
    return ResultFromCpp(r);
}

- (ACPAgentID *)createAID:(NSString *)aid
             seedPassword:(NSString *)password
                    error:(ACPResult * _Nullable * _Nullable)error {
    agentcp::AgentID *out = nullptr;
    agentcp::Result r = agentcp::AgentCP::Instance().CreateAID(ToStdString(aid), ToStdString(password), &out);
    if (!r) {
        if (error) {
            *error = ResultFromCpp(r);
        }
        return nil;
    }
    if (error) {
        *error = nil;
    }
    return [[ACPAgentID alloc] initWithNative:out];
}

- (ACPAgentID *)loadAID:(NSString *)aid
            seedPassword:(NSString *)password
                  error:(ACPResult * _Nullable * _Nullable)error {
    agentcp::AgentID *out = nullptr;
    agentcp::Result r = agentcp::AgentCP::Instance().LoadAID(ToStdString(aid), ToStdString(password), &out);
    if (!r) {
        if (error) {
            *error = ResultFromCpp(r);
        }
        return nil;
    }
    if (error) {
        *error = nil;
    }
    return [[ACPAgentID alloc] initWithNative:out];
}

- (ACPResult *)deleteAID:(NSString *)aid {
    agentcp::Result r = agentcp::AgentCP::Instance().DeleteAID(ToStdString(aid));
    return ResultFromCpp(r);
}

- (NSArray<NSString *> *)listAIDs {
    std::vector<std::string> ids = agentcp::AgentCP::Instance().ListAIDs();
    NSMutableArray<NSString *> *array = [NSMutableArray arrayWithCapacity:ids.size()];
    for (const auto &value : ids) {
        [array addObject:[NSString stringWithUTF8String:value.c_str()]];
    }
    return array;
}

- (NSString *)version {
    std::string value = agentcp::AgentCP::GetVersion();
    return [NSString stringWithUTF8String:value.c_str()];
}

- (NSString *)buildInfo {
    std::string value = agentcp::AgentCP::GetBuildInfo();
    return [NSString stringWithUTF8String:value.c_str()];
}

@end
