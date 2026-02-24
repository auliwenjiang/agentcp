#include "auth_client.h"

#include "../net/http_client.h"
#include "../protocol/auth_protocol.h"
#include "../protocol/message_protocol.h"
#include "../crypto.h"
#include "../acp_log.h"

#include <fstream>
#include <sstream>
#include <thread>
#include <chrono>

#if AGENTCP_USE_OPENSSL
#include <openssl/pem.h>
#include <openssl/evp.h>
#include <openssl/ec.h>
#include <openssl/err.h>
#endif

namespace agentcp {
namespace client {

namespace {

#if AGENTCP_USE_OPENSSL

// Load an ECDSA private key from PEM file (password-protected)
EVP_PKEY* LoadECPrivateKey(const std::string& path, const std::string& password) {
    FILE* fp = nullptr;
#if defined(_WIN32)
    fopen_s(&fp, path.c_str(), "rb");
#else
    fp = fopen(path.c_str(), "rb");
#endif
    if (!fp) return nullptr;

    EVP_PKEY* pkey = PEM_read_PrivateKey(fp, nullptr, nullptr,
                                          const_cast<char*>(password.c_str()));
    fclose(fp);
    return pkey;
}

// Sign data with ECDSA P-256 + SHA256
std::string ECDSASign(EVP_PKEY* pkey, const std::string& data) {
    EVP_MD_CTX* ctx = EVP_MD_CTX_new();
    if (!ctx) return {};

    if (EVP_DigestSignInit(ctx, nullptr, EVP_sha256(), nullptr, pkey) != 1) {
        EVP_MD_CTX_free(ctx);
        return {};
    }

    if (EVP_DigestSignUpdate(ctx, data.data(), data.size()) != 1) {
        EVP_MD_CTX_free(ctx);
        return {};
    }

    size_t sig_len = 0;
    if (EVP_DigestSignFinal(ctx, nullptr, &sig_len) != 1) {
        EVP_MD_CTX_free(ctx);
        return {};
    }

    std::vector<uint8_t> sig(sig_len);
    if (EVP_DigestSignFinal(ctx, sig.data(), &sig_len) != 1) {
        EVP_MD_CTX_free(ctx);
        return {};
    }

    EVP_MD_CTX_free(ctx);
    sig.resize(sig_len);
    return crypto::HexEncode(sig);
}

// Read PEM certificate from file
std::string ReadPEMFile(const std::string& path) {
    std::ifstream f(path);
    if (!f.is_open()) return {};
    std::ostringstream ss;
    ss << f.rdbuf();
    return ss.str();
}

// Get PEM-encoded public key from certificate
std::string GetPublicKeyPEMFromCert(const std::string& cert_pem) {
    BIO* bio = BIO_new_mem_buf(cert_pem.data(), (int)cert_pem.size());
    if (!bio) return {};

    X509* cert = PEM_read_bio_X509(bio, nullptr, nullptr, nullptr);
    BIO_free(bio);
    if (!cert) return {};

    EVP_PKEY* pkey = X509_get_pubkey(cert);
    X509_free(cert);
    if (!pkey) return {};

    BIO* out_bio = BIO_new(BIO_s_mem());
    PEM_write_bio_PUBKEY(out_bio, pkey);
    EVP_PKEY_free(pkey);

    char* pem_data = nullptr;
    long pem_len = BIO_get_mem_data(out_bio, &pem_data);
    std::string result(pem_data, pem_len);
    BIO_free(out_bio);

    return result;
}

#endif  // AGENTCP_USE_OPENSSL

}  // anonymous namespace

AuthClient::AuthClient(const std::string& agent_id,
                       const std::string& server_url,
                       const std::string& aid_path,
                       const std::string& seed_password)
    : agent_id_(agent_id)
    , server_url_(server_url)
    , aid_path_(aid_path)
    , seed_password_(seed_password) {}

AuthClient::~AuthClient() = default;

bool AuthClient::SignIn(int max_retries) {
    ACP_LOGI("AuthClient::SignIn() agent=%s, server=%s, max_retries=%d", agent_id_.c_str(), server_url_.c_str(), max_retries);
    net::HttpClient http;
    http.SetVerifySSL(false);
    http.SetUserAgent("AgentCP/0.1.0 (AuthClient; " + agent_id_ + ")");

    std::string sign_in_url = server_url_ + "/sign_in";
    ACP_LOGD("AuthClient::SignIn() url=%s", sign_in_url.c_str());

    for (int retry = 0; retry <= max_retries; ++retry) {
        try {
            // Step 1: Challenge
            ACP_LOGI("AuthClient::SignIn() Step 1: Challenge (retry=%d/%d)", retry, max_retries);
            protocol::SignInChallengeRequest challenge_req;
            challenge_req.agent_id = agent_id_;
            challenge_req.request_id = protocol::GenerateUuidHex();

            std::string body = protocol::SerializeSignInChallenge(challenge_req);
            ACP_LOGD("AuthClient::SignIn() POST challenge, body_len=%zu", body.size());
            auto resp = http.PostJson(sign_in_url, body);
            ACP_LOGD("AuthClient::SignIn() challenge response: status=%d, body_len=%zu", resp.status_code, resp.body.size());

            if (!resp.ok()) {
                ACP_LOGW("AuthClient::SignIn() challenge HTTP failed: status=%d, body=%s", resp.status_code, resp.body.substr(0, 200).c_str());
                if (retry < max_retries) {
                    ACP_LOGD("AuthClient::SignIn() sleeping 6s before retry...");
                    std::this_thread::sleep_for(std::chrono::seconds(6));
                    continue;
                }
                ACP_LOGE("AuthClient::SignIn() all retries exhausted at challenge step");
                return false;
            }

            protocol::SignInChallengeResponse challenge_resp;
            if (!protocol::DeserializeSignInChallengeResponse(resp.body, &challenge_resp)) {
                ACP_LOGE("AuthClient::SignIn() failed to parse challenge response: %s", resp.body.substr(0, 300).c_str());
                return false;
            }
            ACP_LOGD("AuthClient::SignIn() challenge parsed: nonce_len=%zu, sig_len=%zu", challenge_resp.nonce.size(), challenge_resp.signature.size());

            if (challenge_resp.nonce.empty()) {
                // No nonce returned, check if we got a direct signature
                if (!challenge_resp.signature.empty()) {
                    ACP_LOGI("AuthClient::SignIn() got direct signature (no nonce), sign-in OK");
                    std::lock_guard<std::mutex> lock(mutex_);
                    signature_ = challenge_resp.signature;
                    signed_in_ = true;
                    return true;
                }
                ACP_LOGE("AuthClient::SignIn() no nonce and no signature in challenge response");
                return false;
            }

#if AGENTCP_USE_OPENSSL
            // Load private key
            std::string key_path = aid_path_ + "/" + agent_id_ + ".key";
            ACP_LOGD("AuthClient::SignIn() loading private key: %s (password_len=%zu)", key_path.c_str(), seed_password_.size());
            EVP_PKEY* pkey = LoadECPrivateKey(key_path, seed_password_);
            if (!pkey) {
                // Log OpenSSL error for debugging
                unsigned long err = ERR_peek_last_error();
                char err_buf[256];
                ERR_error_string_n(err, err_buf, sizeof(err_buf));
                ACP_LOGE("AuthClient::SignIn() FAILED to load private key: %s", err_buf);
                return false;
            }
            ACP_LOGD("AuthClient::SignIn() private key loaded OK");

            // Load certificate
            std::string cert_path = aid_path_ + "/" + agent_id_ + ".crt";
            ACP_LOGD("AuthClient::SignIn() loading certificate: %s", cert_path.c_str());
            std::string cert_pem = ReadPEMFile(cert_path);
            if (cert_pem.empty()) {
                ACP_LOGE("AuthClient::SignIn() FAILED to load certificate");
                EVP_PKEY_free(pkey);
                return false;
            }
            ACP_LOGD("AuthClient::SignIn() certificate loaded, len=%zu", cert_pem.size());

            // Get public key PEM from certificate
            std::string public_key_pem = GetPublicKeyPEMFromCert(cert_pem);

            // Sign the nonce
            ACP_LOGD("AuthClient::SignIn() signing nonce...");
            std::string sig_hex = ECDSASign(pkey, challenge_resp.nonce);
            EVP_PKEY_free(pkey);

            if (sig_hex.empty()) {
                ACP_LOGE("AuthClient::SignIn() ECDSA sign FAILED");
                return false;
            }
            ACP_LOGD("AuthClient::SignIn() nonce signed, sig_len=%zu", sig_hex.size());

            // Step 2: Proof
            ACP_LOGI("AuthClient::SignIn() Step 2: Proof (retry=%d/%d)", retry, max_retries);
            protocol::SignInProofRequest proof_req;
            proof_req.agent_id = agent_id_;
            proof_req.request_id = challenge_req.request_id;
            proof_req.nonce = challenge_resp.nonce;
            proof_req.public_key = public_key_pem;
            proof_req.cert = cert_pem;
            proof_req.signature = sig_hex;

            body = protocol::SerializeSignInProof(proof_req);
            ACP_LOGD("AuthClient::SignIn() POST proof, body_len=%zu", body.size());
            resp = http.PostJson(sign_in_url, body);
            ACP_LOGD("AuthClient::SignIn() proof response: status=%d, body_len=%zu", resp.status_code, resp.body.size());

            if (!resp.ok()) {
                ACP_LOGW("AuthClient::SignIn() proof HTTP failed: status=%d, body=%s", resp.status_code, resp.body.substr(0, 200).c_str());
                if (retry < max_retries) {
                    ACP_LOGD("AuthClient::SignIn() sleeping 6s before retry...");
                    std::this_thread::sleep_for(std::chrono::seconds(6));
                    continue;
                }
                ACP_LOGE("AuthClient::SignIn() all retries exhausted at proof step");
                return false;
            }

            protocol::SignInProofResponse proof_resp;
            if (!protocol::DeserializeSignInProofResponse(resp.body, &proof_resp)) {
                ACP_LOGE("AuthClient::SignIn() failed to parse proof response: %s", resp.body.substr(0, 300).c_str());
                return false;
            }

            ACP_LOGI("AuthClient::SignIn() SUCCESS: server_ip=%s, port=%d, sig_len=%zu",
                      proof_resp.server_ip.c_str(), proof_resp.port, proof_resp.signature.size());

            {
                std::lock_guard<std::mutex> lock(mutex_);
                signature_ = proof_resp.signature;
                server_ip_ = proof_resp.server_ip;
                port_ = proof_resp.port;
                sign_cookie_ = proof_resp.sign_cookie;
                signed_in_ = true;
            }
            return true;

#else
            // Without OpenSSL, we can't do ECDSA signing
            return false;
#endif

        } catch (...) {
            ACP_LOGE("AuthClient::SignIn() exception caught (retry=%d/%d)", retry, max_retries);
            if (retry < max_retries) {
                std::this_thread::sleep_for(std::chrono::seconds(6));
                continue;
            }
            return false;
        }
    }
    ACP_LOGE("AuthClient::SignIn() loop ended without success");
    return false;
}

void AuthClient::SignOut() {
    std::string sig;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (!signed_in_) return;
        sig = signature_;
    }

    net::HttpClient http;
    http.SetVerifySSL(false);
    http.SetUserAgent("AgentCP/0.1.0 (AuthClient; " + agent_id_ + ")");

    std::string sign_out_url = server_url_ + "/sign_out";
    protocol::SignOutRequest req;
    req.agent_id = agent_id_;
    req.signature = sig;
    http.PostJson(sign_out_url, protocol::SerializeSignOut(req));

    {
        std::lock_guard<std::mutex> lock(mutex_);
        signature_.clear();
        signed_in_ = false;
    }
}

std::string AuthClient::GetSignature() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return signature_;
}

std::string AuthClient::GetServerIP() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return server_ip_;
}

int AuthClient::GetPort() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return port_;
}

uint64_t AuthClient::GetSignCookie() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return sign_cookie_;
}

bool AuthClient::IsSignedIn() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return signed_in_;
}

}  // namespace client
}  // namespace agentcp
