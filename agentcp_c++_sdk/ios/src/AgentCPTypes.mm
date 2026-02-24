#import "AgentCPTypes.h"

@implementation ACPResult

- (instancetype)initWithCode:(NSInteger)code
                      message:(NSString *)message
                      context:(NSString *)context {
    self = [super init];
    if (self) {
        _code = code;
        _message = [message copy];
        _context = [context copy];
    }
    return self;
}

- (BOOL)ok {
    return self.code == 0;
}

@end
