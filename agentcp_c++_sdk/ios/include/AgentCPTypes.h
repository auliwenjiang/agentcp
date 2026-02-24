#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

typedef NS_ENUM(NSInteger, ACPLogLevel) {
    ACPLogLevelError = 0,
    ACPLogLevelWarn = 1,
    ACPLogLevelInfo = 2,
    ACPLogLevelDebug = 3,
    ACPLogLevelTrace = 4
};

typedef NS_ENUM(NSInteger, ACPAgentState) {
    ACPAgentStateOffline = 0,
    ACPAgentStateConnecting = 1,
    ACPAgentStateAuthenticating = 2,
    ACPAgentStateOnline = 3,
    ACPAgentStateReconnecting = 4,
    ACPAgentStateError = 5
};

@interface ACPResult : NSObject

@property (nonatomic, readonly) NSInteger code;
@property (nonatomic, readonly) NSString *message;
@property (nonatomic, readonly) NSString *context;

- (instancetype)initWithCode:(NSInteger)code
                      message:(NSString *)message
                      context:(NSString *)context;
- (BOOL)ok;

@end

NS_ASSUME_NONNULL_END
