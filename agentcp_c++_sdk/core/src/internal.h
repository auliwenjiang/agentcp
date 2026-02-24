#pragma once

#include <string>

#include "agentcp/result.h"

namespace agentcp {

const char* ErrorCodeToString(ErrorCode code);
std::string GenerateId(const std::string& prefix);

inline Result MakeError(ErrorCode code, const std::string& context = {}) {
    return Result::Error(code, ErrorCodeToString(code), context);
}

}  // namespace agentcp
