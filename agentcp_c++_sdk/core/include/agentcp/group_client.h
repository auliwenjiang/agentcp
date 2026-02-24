#pragma once

#include <atomic>
#include <condition_variable>
#include <cstdint>
#include <functional>
#include <map>
#include <memory>
#include <mutex>
#include <string>

#include "agentcp/export.h"
#include "agentcp/group_types.h"

namespace agentcp {
namespace group {

class ACPGroupEventHandler;
class CursorStore;

/// SendFunc: (targetAid, payload) -> void
using SendFunc = std::function<void(const std::string& target_aid, const std::string& payload)>;

// ============================================================
// ACPGroupClient - core request/response transport
// ============================================================

class ACP_API ACPGroupClient {
public:
    ACPGroupClient(const std::string& agent_id, SendFunc send_func);
    ~ACPGroupClient();

    ACPGroupClient(const ACPGroupClient&) = delete;
    ACPGroupClient& operator=(const ACPGroupClient&) = delete;

    // -- Configuration --
    void SetEventHandler(ACPGroupEventHandler* handler);
    void SetCursorStore(CursorStore* store);
    CursorStore* GetCursorStore() const;
    void SetTimeout(int timeout_ms);

    // -- Request / Response --

    /// Send a request and block until response or timeout.
    /// Thread-safe. Throws GroupError on protocol error, std::runtime_error on timeout/send failure.
    GroupResponse SendRequest(const std::string& target_aid,
                              const std::string& group_id,
                              const std::string& action,
                              const std::string& params_json = "",
                              int timeout_ms = 0);

    // -- Incoming message handling --

    /// Handle an incoming ACP message (response or notification).
    /// Called by the message dispatch chain.
    void HandleIncoming(const std::string& payload);

    // -- Lifecycle --

    /// Close client, cancel all pending requests.
    void Close();

private:
    std::string NextRequestId();

    std::string agent_id_;
    SendFunc send_func_;
    std::atomic<ACPGroupEventHandler*> handler_{nullptr};
    std::atomic<CursorStore*> cursor_store_{nullptr};
    std::atomic<int> req_timeout_ms_{30000};
    std::atomic<int64_t> seq_id_{0};
    std::atomic<bool> closed_{false};

    struct PendingRequest {
        std::string request_id;
        GroupResponse response;
        bool ready = false;
        bool cancelled = false;
        std::condition_variable cv;
    };

    mutable std::mutex pending_mutex_;
    std::map<std::string, std::shared_ptr<PendingRequest>> pending_reqs_;
};

}  // namespace group
}  // namespace agentcp
