#include "agentcp/group_types.h"

#include <sstream>

namespace agentcp {
namespace group {

const char* GroupErrorCodeMessage(int code) {
    switch (code) {
        case 0:    return "success";
        case 1001: return "group not found";
        case 1002: return "no permission";
        case 1003: return "group dissolved";
        case 1004: return "group suspended";
        case 1005: return "already member";
        case 1006: return "not member";
        case 1007: return "banned";
        case 1008: return "member full";
        case 1009: return "invalid params";
        case 1010: return "rate limited";
        case 1011: return "invite code invalid";
        case 1012: return "request exists";
        case 1013: return "broadcast conflict";
        case 1020: return "duty not enabled";
        case 1021: return "not duty agent";
        case 1024: return "agent.md not found";
        case 1025: return "agent.md invalid";
        case 1099: return "action not implemented";
        default:   return "unknown error";
    }
}

GroupError::GroupError(const std::string& action, int code,
                       const std::string& error, const std::string& group_id)
    : std::runtime_error([&]() {
          std::ostringstream oss;
          oss << action << " failed: code=" << code
              << " error=" << (error.empty() ? GroupErrorCodeMessage(code) : error.c_str());
          return oss.str();
      }())
    , action_(action)
    , code_(code)
    , error_(error.empty() ? GroupErrorCodeMessage(code) : error)
    , group_id_(group_id) {}

}  // namespace group
}  // namespace agentcp
