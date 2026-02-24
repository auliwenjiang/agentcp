#include "auth_protocol.h"

#include "third_party/json.hpp"

using json = nlohmann::json;

namespace agentcp {
namespace protocol {

std::string SerializeSignInChallenge(const SignInChallengeRequest& req) {
    json j;
    j["agent_id"] = req.agent_id;
    j["request_id"] = req.request_id;
    return j.dump();
}

bool DeserializeSignInChallengeResponse(const std::string& json_str, SignInChallengeResponse* resp) {
    try {
        auto j = json::parse(json_str);
        if (j.contains("nonce")) resp->nonce = j["nonce"].get<std::string>();
        if (j.contains("cert")) resp->cert = j["cert"].get<std::string>();
        if (j.contains("signature")) resp->signature = j["signature"].get<std::string>();
        return true;
    } catch (...) {
        return false;
    }
}

std::string SerializeSignInProof(const SignInProofRequest& req) {
    json j;
    j["agent_id"] = req.agent_id;
    j["request_id"] = req.request_id;
    j["nonce"] = req.nonce;
    j["public_key"] = req.public_key;
    j["cert"] = req.cert;
    j["signature"] = req.signature;
    return j.dump();
}

bool DeserializeSignInProofResponse(const std::string& json_str, SignInProofResponse* resp) {
    try {
        auto j = json::parse(json_str);
        if (j.contains("signature")) resp->signature = j["signature"].get<std::string>();
        if (j.contains("server_ip")) resp->server_ip = j["server_ip"].get<std::string>();
        if (j.contains("port")) {
            if (j["port"].is_string()) {
                resp->port = std::stoi(j["port"].get<std::string>());
            } else {
                resp->port = j["port"].get<int>();
            }
        }
        if (j.contains("sign_cookie")) {
            if (j["sign_cookie"].is_string()) {
                resp->sign_cookie = std::stoull(j["sign_cookie"].get<std::string>());
            } else {
                resp->sign_cookie = j["sign_cookie"].get<uint64_t>();
            }
        }
        return true;
    } catch (...) {
        return false;
    }
}

std::string SerializeSignOut(const SignOutRequest& req) {
    json j;
    j["agent_id"] = req.agent_id;
    j["signature"] = req.signature;
    return j.dump();
}

}  // namespace protocol
}  // namespace agentcp
