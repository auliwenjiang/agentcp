#pragma once

#include <string>
#include <cstdint>

namespace agentcp {
namespace protocol {

// Sign-in step 1 request
struct SignInChallengeRequest {
    std::string agent_id;
    std::string request_id;  // UUID hex (32 chars)
};

// Sign-in step 1 response
struct SignInChallengeResponse {
    std::string nonce;
    std::string cert;       // PEM (optional)
    std::string signature;  // hex (optional)
};

// Sign-in step 2 request
struct SignInProofRequest {
    std::string agent_id;
    std::string request_id;
    std::string nonce;
    std::string public_key;  // PEM
    std::string cert;        // PEM
    std::string signature;   // hex (ECDSA over nonce)
};

// Sign-in step 2 response
struct SignInProofResponse {
    std::string signature;    // session token
    std::string server_ip;    // for heartbeat UDP
    int port = 0;             // for heartbeat UDP
    uint64_t sign_cookie = 0; // for heartbeat UDP
};

// Sign-out request
struct SignOutRequest {
    std::string agent_id;
    std::string signature;
};

// Serialize/deserialize helpers
std::string SerializeSignInChallenge(const SignInChallengeRequest& req);
bool DeserializeSignInChallengeResponse(const std::string& json, SignInChallengeResponse* resp);

std::string SerializeSignInProof(const SignInProofRequest& req);
bool DeserializeSignInProofResponse(const std::string& json, SignInProofResponse* resp);

std::string SerializeSignOut(const SignOutRequest& req);

}  // namespace protocol
}  // namespace agentcp
