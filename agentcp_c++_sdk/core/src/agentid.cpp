#include "agentcp/agentcp.h"

#include "internal.h"
#include "acp_log.h"
#include "client/auth_client.h"
#include "client/heartbeat_client.h"
#include "client/message_client.h"
#include "client/stream_client_impl.h"
#include "net/http_client.h"
#include "protocol/message_protocol.h"
#include "protocol/heartbeat_protocol.h"

#include "third_party/json.hpp"

#include <chrono>
#include <utility>

using json = nlohmann::json;

namespace agentcp {

AgentID::AgentID(const std::string& aid) : aid_(aid) {
    sessions_ptr_ = new SessionManager(this);
    file_client_ptr_ = new FileClient(this);
}

AgentID::~AgentID() {
    Offline();
    delete sessions_ptr_;
    delete file_client_ptr_;
}

Result AgentID::Online() {
    ACP_LOGI("Online() called for aid=%s", aid_.c_str());
    std::lock_guard<std::mutex> lock(mutex_);
    if (invalidated_) {
        ACP_LOGE("Online() failed: agent id has been deleted");
        return MakeError(ErrorCode::AID_INVALID, "agent id has been deleted");
    }
    if (owner_ == nullptr || !owner_->IsInitialized()) {
        ACP_LOGE("Online() failed: agentcp is not initialized");
        return MakeError(ErrorCode::NOT_INITIALIZED, "agentcp is not initialized");
    }

    AgentState old_state = state_;
    if (state_ == AgentState::Online || state_ == AgentState::Connecting) {
        ACP_LOGW("Online() skipped: already online or connecting (state=%d)", (int)state_);
        return MakeError(ErrorCode::INVALID_ARGUMENT, "already online");
    }
    state_ = AgentState::Connecting;

    if (state_change_handler_) {
        state_change_handler_(old_state, AgentState::Connecting);
    }

    // Get config from owner
    std::string ap_base = owner_->GetAPBase();
    std::string storage_path = owner_->GetStoragePath();
    ACP_LOGI("Online() config: ap_base=%s, storage_path=%s", ap_base.c_str(), storage_path.c_str());
    if (ap_base.empty()) {
        ACP_LOGE("Online() failed: AP base URL not configured");
        state_ = AgentState::Offline;
        if (state_change_handler_) {
            state_change_handler_(AgentState::Connecting, AgentState::Offline);
        }
        return MakeError(ErrorCode::NOT_INITIALIZED, "AP base URL not configured");
    }

    // Determine cert path for auth: use certs_path_ set during CreateAID/LoadAID
    std::string cert_path = certs_path_;
    if (cert_path.empty()) {
        // Fallback: construct from storage_path
        cert_path = (storage_path.empty() ? "." : storage_path) + "/" + aid_ + "/private/certs";
    }

    // Phase 1: Authentication with AP server (matches Python SDK's ApClient.initialize())
    ACP_LOGI("Online() Phase 1: Authenticating with AP server...");
    state_ = AgentState::Authenticating;
    if (state_change_handler_) {
        state_change_handler_(AgentState::Connecting, AgentState::Authenticating);
    }

    // Step 1a: Sign in to AP server to get signature
    std::string ap_api_url = ap_base + "/api/accesspoint";
    ACP_LOGD("Online() Creating AP auth_client: aid=%s, url=%s, cert_path=%s", aid_.c_str(), ap_api_url.c_str(), cert_path.c_str());
    auth_client_ = std::make_unique<client::AuthClient>(
        aid_, ap_api_url, cert_path, seed_password_);

    ACP_LOGI("Online() Calling AP auth_client_->SignIn()...");
    if (!auth_client_->SignIn()) {
        ACP_LOGE("Online() AP auth SignIn FAILED");
        state_ = AgentState::Error;
        if (state_change_handler_) {
            state_change_handler_(AgentState::Authenticating, AgentState::Error);
        }
        auth_client_.reset();
        return MakeError(ErrorCode::AUTH_FAILED, "AP sign-in failed");
    }
    signature_ = auth_client_->GetSignature();
    ACP_LOGI("Online() AP auth SignIn succeeded, signature_len=%zu", signature_.size());

    // Step 1b: Get accesspoint config (heartbeat_server, message_server)
    // Matches Python SDK's ApClient.get_entrypoint_config()
    std::string heartbeat_server_url;
    std::string message_server_url;
    {
        std::string config_url = ap_api_url + "/get_accesspoint_config";
        ACP_LOGI("Online() Getting accesspoint config from %s", config_url.c_str());

        json config_req;
        config_req["agent_id"] = aid_;
        config_req["signature"] = signature_;

        net::HttpClient http;
        http.SetVerifySSL(false);
        http.SetTimeout(30);
        auto config_resp = http.PostJson(config_url, config_req.dump());

        if (config_resp.ok()) {
            try {
                auto config_json = json::parse(config_resp.body);
                auto config_data = config_json.value("config", json::object());
                if (config_data.is_string()) {
                    config_data = json::parse(config_data.get<std::string>());
                }
                heartbeat_server_url = config_data.value("heartbeat_server", std::string());
                message_server_url = config_data.value("message_server", std::string());
                ACP_LOGI("Online() config: heartbeat_server=%s, message_server=%s",
                          heartbeat_server_url.c_str(), message_server_url.c_str());
            } catch (...) {
                ACP_LOGW("Online() failed to parse accesspoint config: %s", config_resp.body.substr(0, 200).c_str());
            }
        } else {
            ACP_LOGW("Online() get_accesspoint_config failed: status=%d", config_resp.status_code);
        }
    }

    // Fallback to ap_base if config didn't provide server URLs
    if (heartbeat_server_url.empty()) {
        heartbeat_server_url = ap_base;
        ACP_LOGW("Online() heartbeat_server not in config, falling back to ap_base: %s", ap_base.c_str());
    }
    if (message_server_url.empty()) {
        message_server_url = ap_base;
        ACP_LOGW("Online() message_server not in config, falling back to ap_base: %s", ap_base.c_str());
    }

    // Phase 2: Create heartbeat client with heartbeat server URL
    ACP_LOGI("Online() Phase 2: Starting heartbeat with %s", heartbeat_server_url.c_str());
    heartbeat_client_ = std::make_unique<client::HeartbeatClient>(
        aid_, heartbeat_server_url, cert_path, seed_password_);

    ACP_LOGI("Online() Calling heartbeat_client_->Initialize() (SignIn)...");
    if (!heartbeat_client_->Initialize()) {
        ACP_LOGE("Online() heartbeat Initialize (SignIn) FAILED");
        state_ = AgentState::Error;
        if (state_change_handler_) {
            state_change_handler_(AgentState::Authenticating, AgentState::Error);
        }
        heartbeat_client_.reset();
        return MakeError(ErrorCode::AUTH_FAILED, "heartbeat sign-in failed");
    }
    ACP_LOGI("Online() heartbeat Initialize (SignIn) succeeded");

    if (!heartbeat_client_->Online()) {
        ACP_LOGE("Online() heartbeat Online() FAILED");
        state_ = AgentState::Error;
        if (state_change_handler_) {
            state_change_handler_(AgentState::Authenticating, AgentState::Error);
        }
        heartbeat_client_.reset();
        return MakeError(ErrorCode::NETWORK_ERROR, "failed to start heartbeat");
    }
    ACP_LOGI("Online() heartbeat started successfully");

    // Set invite handler on heartbeat client
    heartbeat_client_->SetInviteCallback(
        [this](const protocol::InviteMessageReq& invite) {
            if (invite_handler_) {
                invite_handler_(invite.session_id, invite.inviter_agent_id);
            }
            // Auto-join session via message client
            if (message_client_ && message_client_->IsConnected()) {
                std::string request_id = std::to_string(protocol::NowMs());
                std::string msg = protocol::BuildJoinSessionReq(
                    invite.session_id, request_id,
                    invite.inviter_agent_id, invite.invite_code);
                message_client_->SendMessage(msg);
            }
        });

    // Phase 3: Connect message WebSocket
    message_server_ = message_server_url;
    ACP_LOGI("Online() Phase 3: Connecting message WebSocket to %s", message_server_.c_str());

    message_client_ = std::make_unique<client::MessageClient>(
        aid_, message_server_, nullptr, client::MessageClientConfig());

    // Create a separate auth client for the message server
    // Pass message_server_url directly (Python SDK pattern: AuthClient appends /sign_in)
    ACP_LOGD("Online() Creating auth_client for message server: %s", message_server_url.c_str());
    auto msg_auth_client = std::make_unique<client::AuthClient>(
        aid_, message_server_url, cert_path, seed_password_);

    ACP_LOGI("Online() Calling msg_auth_client->SignIn() for message server...");
    if (!msg_auth_client->SignIn()) {
        ACP_LOGW("Online() msg_auth_client SignIn for message server failed, using AP signature as fallback");
    } else {
        ACP_LOGI("Online() msg_auth_client SignIn for message server succeeded");
        // Replace auth_client_ with the message server one
        auth_client_ = std::move(msg_auth_client);
    }

    // Recreate message client with the auth client
    message_client_ = std::make_unique<client::MessageClient>(
        aid_, message_server_, auth_client_.get());

    // Set message handler
    message_client_->SetMessageHandler(
        [this](const std::string& cmd, const std::string& data_json) {
            ACP_LOGI("AgentID::MessageHandler: cmd=%s, data_len=%zu", cmd.c_str(), data_json.size());

            // Route group protocol messages first
            if (HandleGroupMessage(cmd, data_json)) {
                return;
            }

            if (cmd == "session_message" && message_handler_) {
                ACP_LOGI("AgentID: Processing session_message");
                try {
                    auto j = json::parse(data_json);
                    Message msg;
                    if (j.contains("message_id")) msg.message_id = j["message_id"].get<std::string>();
                    if (j.contains("session_id")) msg.session_id = j["session_id"].get<std::string>();
                    if (j.contains("sender")) msg.sender = j["sender"].get<std::string>();
                    if (j.contains("receiver")) msg.receiver = j["receiver"].get<std::string>();
                    if (j.contains("timestamp")) {
                        if (j["timestamp"].is_string()) {
                            msg.timestamp = std::stoull(j["timestamp"].get<std::string>());
                        } else {
                            msg.timestamp = j["timestamp"].get<uint64_t>();
                        }
                    }
                    // Decode message blocks
                    if (j.contains("message")) {
                        std::string encoded_msg = j["message"].get<std::string>();
                        std::string decoded = protocol::UrlDecode(encoded_msg);
                        auto blocks_j = json::parse(decoded);
                        if (blocks_j.is_array()) {
                            for (const auto& block_j : blocks_j) {
                                Block block;
                                if (block_j.contains("type")) {
                                    std::string type_str = block_j["type"].get<std::string>();
                                    if (type_str == "content") block.type = BlockType::Content;
                                    else if (type_str == "file") block.type = BlockType::File;
                                    else if (type_str == "image") block.type = BlockType::Image;
                                    else block.type = BlockType::Content;
                                }
                                if (block_j.contains("content")) {
                                    if (block_j["content"].is_string()) {
                                        block.text = block_j["content"].get<std::string>();
                                    }
                                }
                                if (block_j.contains("timestamp")) {
                                    if (block_j["timestamp"].is_number()) {
                                        block.timestamp = block_j["timestamp"].get<uint64_t>();
                                    }
                                }
                                msg.blocks.push_back(block);
                            }
                        }
                    }
                    ACP_LOGI("AgentID: Calling message_handler, msg_id=%s, sender=%s",
                             msg.message_id.c_str(), msg.sender.c_str());
                    message_handler_(msg);
                } catch (const std::exception& e) {
                    ACP_LOGE("AgentID: Failed to parse session_message: %s", e.what());
                } catch (...) {
                    ACP_LOGE("AgentID: Failed to parse session_message: unknown error");
                }
            } else if (cmd == "session_message") {
                ACP_LOGW("AgentID: Received session_message but message_handler_ is null");
            } else if (cmd == "system_message") {
                // Handle system messages if needed
            }
        });

    if (!message_client_->Connect()) {
        ACP_LOGW("Online() message WebSocket connect failed (will auto-reconnect)");
        // WebSocket connection failed, but heartbeat is running
        // This is recoverable - message client will auto-reconnect
    } else {
        ACP_LOGI("Online() message WebSocket connected");
    }

    state_ = AgentState::Online;
    ACP_LOGI("Online() SUCCESS - agent is now Online: %s", aid_.c_str());
    if (state_change_handler_) {
        state_change_handler_(AgentState::Authenticating, AgentState::Online);
    }
    return Result::Ok();
}

void AgentID::Offline() {
    AgentState old_state;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        old_state = state_;
        if (state_ == AgentState::Offline) return;
        state_ = AgentState::Offline;
    }

    // H1 fix: Close group client FIRST (before message_client)
    // This cancels all pending requests, ensuring no send_func calls
    // are in-flight when message_client is destroyed.
    group_ops_.reset();
    if (group_client_) {
        group_client_->Close();
        group_client_.reset();
    }
    group_target_aid_.clear();
    group_session_id_.clear();

    // Stop message client
    if (message_client_) {
        message_client_->Disconnect();
        message_client_.reset();
    }

    // Stop heartbeat
    if (heartbeat_client_) {
        heartbeat_client_->Offline();
        heartbeat_client_.reset();
    }

    // Sign out
    if (auth_client_) {
        auth_client_->SignOut();
        auth_client_.reset();
    }

    signature_.clear();

    if (state_change_handler_) {
        state_change_handler_(old_state, AgentState::Offline);
    }
}

bool AgentID::IsOnline() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return !invalidated_ && state_ == AgentState::Online;
}

bool AgentID::IsValid() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return !invalidated_;
}

AgentState AgentID::GetState() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return state_;
}

std::string AgentID::GetAID() const {
    return aid_;
}

std::string AgentID::GetSignature() const {
    return signature_;
}

std::string AgentID::GetPublicKey() const {
    return std::string();  // No longer using raw Ed25519 keys
}

std::string AgentID::GetCertificate() const {
    return cert_pem_;
}

SessionManager& AgentID::Sessions() {
    return *sessions_ptr_;
}

FileClient& AgentID::Files() {
    return *file_client_ptr_;
}

void AgentID::SetMessageHandler(MessageHandler handler) {
    message_handler_ = std::move(handler);
}

void AgentID::SetErrorHandler(ErrorHandler handler) {
    error_handler_ = std::move(handler);
}

void AgentID::SetMetricsHandler(MetricsHandler handler) {
    metrics_handler_ = std::move(handler);
}

void AgentID::SetStateChangeHandler(StateChangeHandler handler) {
    state_change_handler_ = std::move(handler);
}

void AgentID::SetInviteHandler(InviteHandler handler) {
    invite_handler_ = std::move(handler);
}

Result AgentID::SendMessage(const std::string& session_id, const std::vector<Block>& blocks) {
    return SendMessage(session_id, std::string(), blocks);
}

Result AgentID::SendMessage(const std::string& session_id,
                            const std::string& receiver_override,
                            const std::vector<Block>& blocks) {
    if (!IsOnline()) {
        ACP_LOGW("SendMessage: agent is offline");
        return MakeError(ErrorCode::NOT_INITIALIZED, "agent is offline");
    }

    if (!message_client_ || !message_client_->IsConnected()) {
        ACP_LOGW("SendMessage: websocket not connected, client=%p", message_client_.get());
        return MakeError(ErrorCode::WS_DISCONNECTED, "websocket not connected");
    }

    // Serialize blocks to JSON array (match Python SDK format)
    json blocks_json = json::array();
    uint64_t now_ms = static_cast<uint64_t>(
        std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch()).count());
    for (const auto& block : blocks) {
        json bj;
        switch (block.type) {
            case BlockType::Content: bj["type"] = "content"; break;
            case BlockType::File: bj["type"] = "file"; break;
            case BlockType::Image: bj["type"] = "image"; break;
            case BlockType::Audio: bj["type"] = "audio"; break;
            case BlockType::Video: bj["type"] = "video"; break;
            case BlockType::Form: bj["type"] = "form"; break;
            case BlockType::FormResult: bj["type"] = "form_result"; break;
            case BlockType::Instruction: bj["type"] = "instruction"; break;
            default: bj["type"] = "content"; break;
        }
        bj["content"] = block.text;
        bj["timestamp"] = static_cast<int64_t>(block.timestamp != 0 ? block.timestamp : now_ms);
        bj["status"] = "success";
        blocks_json.push_back(bj);
    }

    std::string message_id = protocol::GenerateUuidHex();

    std::string receiver = receiver_override;
    if (receiver.empty()) {
        SessionInfo sinfo;
        if (Sessions().GetSessionInfo(session_id, &sinfo)) {
            for (const auto& m : sinfo.members) {
                if (m.agent_id == aid_) continue;
                if (!receiver.empty()) receiver += ",";
                receiver += m.agent_id;
            }
        }
    }
    ACP_LOGI("SendMessage: session=%s, msg_id=%s, receiver='%s', blocks=%zu",
             session_id.c_str(), message_id.c_str(), receiver.c_str(), blocks.size());

    std::string msg = protocol::BuildSessionMessage(
        message_id, session_id, aid_, receiver,
        blocks_json.dump());

    if (!message_client_->SendMessage(msg)) {
        ACP_LOGE("SendMessage: ws SendMessage failed for msg_id=%s", message_id.c_str());
        return MakeError(ErrorCode::WS_SEND_FAILED, "failed to send message");
    }

    ACP_LOGI("SendMessage: SUCCESS msg_id=%s", message_id.c_str());
    return Result::Ok();
}

Result AgentID::SendMessageWithInstruction(const std::string& session_id,
                                           const std::vector<Block>& blocks,
                                           const Instruction& instruction) {
    if (!IsOnline()) {
        return MakeError(ErrorCode::NOT_INITIALIZED, "agent is offline");
    }

    if (!message_client_ || !message_client_->IsConnected()) {
        return MakeError(ErrorCode::WS_DISCONNECTED, "websocket not connected");
    }

    // Serialize blocks
    json blocks_json = json::array();
    for (const auto& block : blocks) {
        json bj;
        switch (block.type) {
            case BlockType::Content: bj["type"] = "content"; break;
            case BlockType::File: bj["type"] = "file"; break;
            case BlockType::Image: bj["type"] = "image"; break;
            default: bj["type"] = "content"; break;
        }
        bj["content"] = block.text;
        bj["timestamp"] = static_cast<int64_t>(block.timestamp);
        blocks_json.push_back(bj);
    }

    // Serialize instruction
    json instr_json;
    instr_json["cmd"] = instruction.cmd;
    instr_json["description"] = instruction.description;
    instr_json["model"] = instruction.model;
    json params_j = json::object();
    for (const auto& kv : instruction.params) {
        params_j[kv.first] = kv.second;
    }
    instr_json["params"] = params_j;

    std::string message_id = protocol::GenerateUuidHex();
    std::string msg = protocol::BuildSessionMessage(
        message_id, session_id, aid_, "",
        blocks_json.dump(), "", instr_json.dump());

    if (!message_client_->SendMessage(msg)) {
        return MakeError(ErrorCode::WS_SEND_FAILED, "failed to send message");
    }

    return Result::Ok();
}

Result AgentID::CreateStream(const std::string& session_id,
                             const std::string& receiver,
                             const std::string& content_type,
                             Stream** out) {
    if (out == nullptr) {
        return MakeError(ErrorCode::INVALID_ARGUMENT, "out is null");
    }
    if (!IsOnline()) {
        return MakeError(ErrorCode::NOT_INITIALIZED, "agent is offline");
    }
    if (!message_client_ || !message_client_->IsConnected()) {
        return MakeError(ErrorCode::WS_DISCONNECTED, "websocket not connected");
    }

    // Send stream create request and wait for ack
    std::string request_id = protocol::GenerateUuidHex();
    std::string msg = protocol::BuildCreateStreamReq(
        session_id, request_id, "", aid_, receiver, content_type);

    std::string ack_json = message_client_->SendAndWaitAck(
        msg, "session_create_stream_ack", request_id, 10000);

    if (ack_json.empty()) {
        return MakeError(ErrorCode::WS_TIMEOUT, "stream create timeout");
    }

    protocol::CreateStreamAck ack;
    if (!protocol::ParseCreateStreamAck(ack_json, &ack)) {
        return MakeError(ErrorCode::WS_TIMEOUT, "invalid stream ack");
    }

    if (!ack.error.empty()) {
        return MakeError(ErrorCode::STREAM_NOT_CONNECTED, ack.error_message);
    }

    // Create the stream with WebSocket client
    auto stream = new Stream(ack.message_id.empty() ? GenerateId("stream") : ack.message_id);
    stream->push_url_ = ack.push_url;

    if (!ack.push_url.empty()) {
        stream->stream_impl_ = std::make_unique<client::StreamClientImpl>(
            ack.push_url, aid_,
            auth_client_ ? auth_client_->GetSignature() : signature_);

        if (!stream->stream_impl_->Connect()) {
            delete stream;
            return MakeError(ErrorCode::STREAM_NOT_CONNECTED, "stream websocket connect failed");
        }
        stream->connected_ = true;
    }

    *out = stream;
    return Result::Ok();
}

Result AgentID::UploadFile(const std::string& path, FileUploadCallback callback, std::string* url_out) {
    if (url_out == nullptr) {
        return MakeError(ErrorCode::INVALID_ARGUMENT, "url_out is null");
    }
    if (!IsOnline()) {
        return MakeError(ErrorCode::NOT_INITIALIZED, "agent is offline");
    }

    return file_client_ptr_->UploadFile(path, callback, url_out);
}

Result AgentID::DownloadFile(const std::string& url,
                             const std::string& output_path,
                             FileDownloadCallback callback) {
    if (!IsOnline()) {
        return MakeError(ErrorCode::NOT_INITIALIZED, "agent is offline");
    }

    return file_client_ptr_->DownloadFile(url, output_path, callback);
}

void AgentID::SetState(AgentState state) {
    AgentState old_state;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        old_state = state_;
        state_ = state;
    }
    if (state_change_handler_) {
        state_change_handler_(old_state, state);
    }
}

void AgentID::Invalidate() {
    Offline();
    std::lock_guard<std::mutex> lock(mutex_);
    invalidated_ = true;
    state_ = AgentState::Error;
}

// ============================================================
// Group Module Integration
// ============================================================

void AgentID::InitGroupClient(const std::string& session_id, const std::string& target_aid) {
    std::lock_guard<std::mutex> lock(mutex_);

    group_session_id_ = session_id;

    // Compute target AID: default to "group.{issuer}"
    if (!target_aid.empty()) {
        group_target_aid_ = target_aid;
    } else {
        // Extract issuer from aid_ (e.g. "myagent.aid.net" -> issuer = "aid.net")
        auto dot_pos = aid_.find('.');
        if (dot_pos != std::string::npos) {
            group_target_aid_ = "group." + aid_.substr(dot_pos + 1);
        } else {
            group_target_aid_ = "group." + aid_;
        }
    }

    // Create send function that routes through message_client_
    // Mirrors TS SDK's sendRaw: builds session_message WITHOUT URL encoding
    auto send_func = [this](const std::string& to_aid, const std::string& payload) {
        if (!message_client_ || !message_client_->IsConnected()) {
            throw std::runtime_error("websocket not connected");
        }
        // Build raw session_message envelope (no URL encoding on payload)
        // This matches the TS WSClient.sendRaw() behavior
        json data;
        data["message_id"] = std::to_string(protocol::NowMs());
        data["session_id"] = group_session_id_;
        data["ref_msg_id"] = "";
        data["sender"] = aid_;
        data["receiver"] = to_aid;
        data["message"] = payload;  // raw JSON, no URL encoding
        data["timestamp"] = std::to_string(protocol::NowMs());

        json envelope;
        envelope["cmd"] = "session_message";
        envelope["data"] = data;

        std::string msg = envelope.dump();
        if (!message_client_->SendMessage(msg)) {
            throw std::runtime_error("failed to send group message");
        }
    };

    group_client_ = std::make_unique<group::ACPGroupClient>(aid_, send_func);
    group_ops_ = std::make_unique<group::GroupOperations>(group_client_.get());

    ACP_LOGI("InitGroupClient: target_aid=%s, session_id=%s",
             group_target_aid_.c_str(), group_session_id_.c_str());
}

void AgentID::InitGroupClientCrossAp(const std::string& session_id, const std::string& target_aid) {
    InitGroupClient(session_id, target_aid);
}

std::string AgentID::GetGroupTargetAid() const {
    return group_target_aid_;
}

void AgentID::CloseGroupClient() {
    std::lock_guard<std::mutex> lock(mutex_);
    group_ops_.reset();
    if (group_client_) {
        group_client_->Close();
        group_client_.reset();
    }
    group_target_aid_.clear();
    group_session_id_.clear();
}

bool AgentID::HandleGroupMessage(const std::string& cmd, const std::string& data_json) {
    if (cmd != "session_message" || !group_client_) return false;

    try {
        auto j = json::parse(data_json);
        std::string sender = j.value("sender", "");

        // Check if sender matches group target AID (exact match only)
        // Mirrors TS SDK: sender === this._groupTargetAid
        if (sender != group_target_aid_) {
            return false;
        }

        // Extract the message content (group protocol payload)
        // sendRaw does NOT URL-encode, so we read directly (no UrlDecode)
        std::string raw_msg = j.value("message", "");
        if (raw_msg.empty()) return false;

        group_client_->HandleIncoming(raw_msg);
        return true;
    } catch (const std::exception& e) {
        ACP_LOGW("[Group] HandleGroupMessage error: %s", e.what());
        return false;
    } catch (...) {
        ACP_LOGW("[Group] HandleGroupMessage unknown error");
        return false;
    }
}

void AgentID::SetGroupEventHandler(group::ACPGroupEventHandler* handler) {
    if (group_client_) {
        group_client_->SetEventHandler(handler);
    }
}

void AgentID::SetGroupCursorStore(group::CursorStore* store) {
    if (group_client_) {
        group_client_->SetCursorStore(store);
    }
}

group::GroupOperations* AgentID::GroupOps() {
    return group_ops_.get();
}

group::ACPGroupClient* AgentID::GroupClient() {
    return group_client_.get();
}

}  // namespace agentcp
