#include "agentcp/group_client.h"
#include "agentcp/group_events.h"
#include "agentcp/cursor_store.h"

#include "../acp_log.h"
#include "third_party/json.hpp"

#include <chrono>
#include <sstream>

using json = nlohmann::json;

namespace agentcp {
namespace group {

// ============================================================
// Helper: build request JSON
// ============================================================

static std::string BuildRequestJson(const std::string& action,
                                    const std::string& request_id,
                                    const std::string& group_id,
                                    const std::string& params_json) {
    json j;
    j["action"] = action;
    j["request_id"] = request_id;
    if (!group_id.empty()) {
        j["group_id"] = group_id;
    }
    if (!params_json.empty()) {
        try {
            j["params"] = json::parse(params_json);
        } catch (const std::exception& e) {
            // M1 fix: log warning instead of silently dropping
            ACP_LOGW("[GroupClient] invalid params_json for action=%s: %s",
                     action.c_str(), e.what());
        }
    }
    return j.dump();
}

// ============================================================
// Helper: parse response from JSON object
// ============================================================

static GroupResponse ParseResponse(const json& j) {
    GroupResponse resp;
    resp.action     = j.value("action", "");
    resp.request_id = j.value("request_id", "");
    resp.code       = j.value("code", -1);
    resp.group_id   = j.value("group_id", "");
    resp.error      = j.value("error", "");
    if (j.contains("data") && !j["data"].is_null()) {
        resp.data_json = j["data"].dump();
    }
    return resp;
}

// ============================================================
// Helper: parse notify from JSON object
// ============================================================

static GroupNotify ParseNotify(const json& j) {
    GroupNotify n;
    n.action    = j.value("action", "group_notify");
    n.group_id  = j.value("group_id", "");
    n.event     = j.value("event", "");
    n.timestamp = j.value("timestamp", (int64_t)0);
    if (j.contains("data") && !j["data"].is_null()) {
        n.data_json = j["data"].dump();
    }
    return n;
}

// ============================================================
// ACPGroupClient
// ============================================================

ACPGroupClient::ACPGroupClient(const std::string& agent_id, SendFunc send_func)
    : agent_id_(agent_id)
    , send_func_(std::move(send_func)) {}

ACPGroupClient::~ACPGroupClient() {
    Close();
}

void ACPGroupClient::SetEventHandler(ACPGroupEventHandler* handler) {
    handler_.store(handler, std::memory_order_release);  // H2 fix: atomic store
}

void ACPGroupClient::SetCursorStore(CursorStore* store) {
    cursor_store_.store(store, std::memory_order_release);  // H2 fix: atomic store
}

CursorStore* ACPGroupClient::GetCursorStore() const {
    return cursor_store_.load(std::memory_order_acquire);  // H2 fix: atomic load
}

void ACPGroupClient::SetTimeout(int timeout_ms) {
    req_timeout_ms_.store(timeout_ms, std::memory_order_relaxed);
}

std::string ACPGroupClient::NextRequestId() {
    int64_t seq = seq_id_.fetch_add(1) + 1;
    auto now = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();

    std::ostringstream oss;
    oss << agent_id_ << "-" << now << "-" << seq;
    return oss.str();
}

GroupResponse ACPGroupClient::SendRequest(const std::string& target_aid,
                                          const std::string& group_id,
                                          const std::string& action,
                                          const std::string& params_json,
                                          int timeout_ms) {
    if (closed_.load(std::memory_order_acquire)) {
        throw std::runtime_error("group client is closed");
    }

    std::string req_id = NextRequestId();
    std::string payload = BuildRequestJson(action, req_id, group_id, params_json);
    int effective_timeout = (timeout_ms > 0) ? timeout_ms : req_timeout_ms_.load(std::memory_order_relaxed);

    // Create pending request
    auto pending = std::make_shared<PendingRequest>();
    pending->request_id = req_id;

    {
        std::lock_guard<std::mutex> lock(pending_mutex_);
        pending_reqs_[req_id] = pending;
    }

    // Send
    try {
        send_func_(target_aid, payload);
    } catch (const std::exception& e) {
        std::lock_guard<std::mutex> lock(pending_mutex_);
        pending_reqs_.erase(req_id);
        throw std::runtime_error(std::string("send failed: ") + e.what());
    }

    // Wait for response
    {
        std::unique_lock<std::mutex> lock(pending_mutex_);
        bool got_it = pending->cv.wait_for(lock,
            std::chrono::milliseconds(effective_timeout),
            [&pending]() { return pending->ready || pending->cancelled; });

        pending_reqs_.erase(req_id);

        if (pending->cancelled) {
            throw std::runtime_error("request cancelled: reqId=" + req_id);
        }
        if (!got_it) {
            ACP_LOGE("[GroupClient] TIMEOUT: action=%s group=%s reqId=%s",
                     action.c_str(), group_id.c_str(), req_id.c_str());
            throw std::runtime_error("request timeout: action=" + action + " group=" + group_id);
        }
    }

    return pending->response;
}

void ACPGroupClient::HandleIncoming(const std::string& payload) {
    json data;
    try {
        data = json::parse(payload);
    } catch (...) {
        ACP_LOGW("[GroupClient] JSON parse failed for incoming payload");
        return;
    }

    // Try as response (has request_id)
    std::string request_id = data.value("request_id", "");
    if (!request_id.empty()) {
        GroupResponse resp = ParseResponse(data);
        {
            std::lock_guard<std::mutex> lock(pending_mutex_);
            auto it = pending_reqs_.find(request_id);
            if (it != pending_reqs_.end()) {
                it->second->response = resp;
                it->second->ready = true;
                it->second->cv.notify_all();
                // If response also carries an event field, dispatch as notification
                std::string event = data.value("event", "");
                if (!event.empty()) {
                    auto* handler = handler_.load(std::memory_order_acquire);
                    if (handler) {
                        GroupNotify notify = ParseNotify(data);
                        DispatchAcpNotify(handler, notify);
                    }
                }
                return;
            }
        }
        ACP_LOGW("[GroupClient] request_id=%s NOT found in pending", request_id.c_str());
    }

    // Try as notification (has event field)
    std::string event = data.value("event", "");
    if (!event.empty()) {
        GroupNotify notify = ParseNotify(data);
        // H2 fix: atomic load of handler_
        auto* handler = handler_.load(std::memory_order_acquire);
        if (handler) {
            DispatchAcpNotify(handler, notify);
        } else {
            ACP_LOGW("[GroupClient] notification event=%s dropped: no event handler", event.c_str());
        }
        return;
    }

    // Handle action-based push messages from group.ap
    // These have action field but no event/request_id
    std::string action = data.value("action", "");

    // Single message push: convert to NOTIFY_GROUP_MESSAGE notification
    if (action == "message_push" && data.contains("data") && !data["data"].is_null()) {
        try {
            auto& msg_data = data["data"];
            GroupMessage msg;
            msg.msg_id       = msg_data.value("msg_id", (int64_t)0);
            msg.sender       = msg_data.value("sender", "");
            msg.content      = msg_data.value("content", "");
            msg.content_type = msg_data.value("content_type", "text");
            msg.timestamp    = msg_data.value("timestamp", (int64_t)0);
            if (msg_data.contains("metadata") && !msg_data["metadata"].is_null()) {
                msg.metadata_json = msg_data["metadata"].dump();
            }

            auto* handler = handler_.load(std::memory_order_acquire);
            if (handler) {
                // Dispatch as OnGroupMessage
                handler->OnGroupMessage(data.value("group_id", ""), msg);
                // Also dispatch as notification for NOTIFY_GROUP_MESSAGE listeners
                GroupNotify notify;
                notify.action    = "group_notify";
                notify.group_id  = data.value("group_id", "");
                notify.event     = NOTIFY_GROUP_MESSAGE;
                notify.data_json = msg_data.dump();
                notify.timestamp = msg.timestamp;
                DispatchAcpNotify(handler, notify);
            } else {
                ACP_LOGW("[GroupClient] message_push dropped: no event handler");
            }
        } catch (const std::exception& e) {
            ACP_LOGW("[GroupClient] message_push parse error: %s", e.what());
        } catch (...) {
            ACP_LOGW("[GroupClient] message_push unknown parse error");
        }
        return;
    }

    // Batch message push
    if (action == ACTION_MESSAGE_BATCH_PUSH && data.contains("data") && !data["data"].is_null()) {
        try {
            auto& batch_data = data["data"];
            GroupMessageBatch batch;
            batch.start_msg_id  = batch_data.value("start_msg_id", (int64_t)0);
            batch.latest_msg_id = batch_data.value("latest_msg_id", (int64_t)0);
            batch.count         = batch_data.value("count", 0);

            if (batch_data.contains("messages") && batch_data["messages"].is_array()) {
                for (const auto& m : batch_data["messages"]) {
                    if (!m.is_object()) continue;
                    GroupMessage msg;
                    msg.msg_id       = m.value("msg_id", (int64_t)0);
                    msg.sender       = m.value("sender", "");
                    msg.content      = m.value("content", "");
                    msg.content_type = m.value("content_type", "text/plain");
                    msg.timestamp    = m.value("timestamp", (int64_t)0);
                    if (m.contains("metadata") && !m["metadata"].is_null()) {
                        msg.metadata_json = m["metadata"].dump();
                    }
                    batch.messages.push_back(std::move(msg));
                }
            }

            auto* handler = handler_.load(std::memory_order_acquire);
            if (handler) {
                handler->OnGroupMessageBatch(data.value("group_id", ""), batch);
            } else {
                ACP_LOGW("[GroupClient] message_batch_push dropped: no event handler");
            }
        } catch (const std::exception& e) {
            ACP_LOGW("[GroupClient] message_batch_push parse error: %s", e.what());
        } catch (...) {
            ACP_LOGW("[GroupClient] message_batch_push unknown parse error");
        }
        return;
    }

    ACP_LOGW("[GroupClient] unhandled incoming: no request_id and no event");
}

void ACPGroupClient::Close() {
    // Prevent double-close
    bool expected = false;
    if (!closed_.compare_exchange_strong(expected, true)) {
        return;
    }

    // H3 fix: cancel pending requests under lock, then close cursor store outside lock
    {
        std::lock_guard<std::mutex> lock(pending_mutex_);
        for (auto& [req_id, pending] : pending_reqs_) {
            pending->cancelled = true;
            pending->cv.notify_all();
        }
        pending_reqs_.clear();
    }

    // Close cursor store outside pending_mutex_ to avoid blocking
    auto* store = cursor_store_.load(std::memory_order_acquire);
    if (store) {
        try {
            store->Close();
        } catch (const std::exception& e) {
            ACP_LOGW("[GroupClient] cursor store close error: %s", e.what());
        } catch (...) {
            ACP_LOGW("[GroupClient] cursor store close unknown error");
        }
    }
}

}  // namespace group
}  // namespace agentcp
