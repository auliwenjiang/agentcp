#import <Foundation/Foundation.h>

#import "AgentCPTypes.h"

NS_ASSUME_NONNULL_BEGIN

@class ACPAgentID;

@interface ACPAgentCP : NSObject

+ (instancetype)shared;

- (ACPResult *)initialize;
- (void)shutdown;

- (ACPResult *)setBaseUrls:(NSString *)caBase apBase:(NSString *)apBase;
- (ACPResult *)setStoragePath:(NSString *)path;
- (ACPResult *)setLogLevel:(ACPLogLevel)level;

- (nullable ACPAgentID *)createAID:(NSString *)aid
                       seedPassword:(NSString *)password
                              error:(ACPResult * _Nullable * _Nullable)error;
- (nullable ACPAgentID *)loadAID:(NSString *)aid
                     seedPassword:(NSString *)password
                            error:(ACPResult * _Nullable * _Nullable)error;

- (ACPResult *)deleteAID:(NSString *)aid;
- (NSArray<NSString *> *)listAIDs;

- (NSString *)version;
- (NSString *)buildInfo;

@end

NS_ASSUME_NONNULL_END
