#pragma once

#include <string>
#include <cstdint>
#include <mutex>

namespace agentcp {
namespace client {

class AuthClient {
public:
    AuthClient(const std::string& agent_id,
               const std::string& server_url,
               const std::string& aid_path,
               const std::string& seed_password);
    ~AuthClient();

    // Execute the two-step sign-in flow
    // Returns true on success, populates signature and server info
    bool SignIn(int max_retries = 2);

    // Sign out (invalidate session)
    void SignOut();

    // Getters
    std::string GetSignature() const;
    std::string GetServerIP() const;
    int GetPort() const;
    uint64_t GetSignCookie() const;
    bool IsSignedIn() const;

private:
    std::string agent_id_;
    std::string server_url_;
    std::string aid_path_;
    std::string seed_password_;

    mutable std::mutex mutex_;
    std::string signature_;
    std::string server_ip_;
    int port_ = 0;
    uint64_t sign_cookie_ = 0;
    bool signed_in_ = false;
};

}  // namespace client
}  // namespace agentcp
