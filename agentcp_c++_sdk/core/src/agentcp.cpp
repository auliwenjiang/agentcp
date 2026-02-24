#include "agentcp/agentcp.h"

#include "internal.h"
#include "crypto.h"
#include "acp_log.h"
#include "net/http_client.h"
#include "third_party/json.hpp"

#include <algorithm>
#include <sys/stat.h>

#if defined(_WIN32)
#include <direct.h>
#include <io.h>
#define acp_mkdir(p) _mkdir(p)
#else
#include <dirent.h>
#include <unistd.h>
#define acp_mkdir(p) mkdir(p, 0755)
#endif

using json = nlohmann::json;

namespace agentcp {

namespace {

// Create directory and all parent directories
bool MakeDirsRecursive(const std::string& path) {
    if (path.empty()) return false;
    // Try creating the directory; if it succeeds or already exists, done
    struct stat st;
    if (stat(path.c_str(), &st) == 0) return true;

    // Find parent
    size_t pos = path.find_last_of("/\\");
    if (pos != std::string::npos && pos > 0) {
        std::string parent = path.substr(0, pos);
        if (!MakeDirsRecursive(parent)) return false;
    }
    int ret = acp_mkdir(path.c_str());
    return ret == 0 || errno == EEXIST;
}

// Remove a directory recursively
bool RemoveDirRecursive(const std::string& path) {
#if defined(_WIN32)
    // Use system command on Windows
    std::string cmd = "rmdir /s /q \"" + path + "\" >nul 2>&1";
    return system(cmd.c_str()) == 0;
#else
    std::string cmd = "rm -rf \"" + path + "\"";
    return system(cmd.c_str()) == 0;
#endif
}

// List subdirectories in a directory
std::vector<std::string> ListSubdirectories(const std::string& path) {
    std::vector<std::string> result;
#if defined(_WIN32)
    std::string pattern = path + "\\*";
    struct _finddata_t fd;
    intptr_t handle = _findfirst(pattern.c_str(), &fd);
    if (handle == -1) return result;
    do {
        if ((fd.attrib & _A_SUBDIR) && fd.name[0] != '.') {
            result.push_back(fd.name);
        }
    } while (_findnext(handle, &fd) == 0);
    _findclose(handle);
#else
    DIR* dir = opendir(path.c_str());
    if (!dir) return result;
    struct dirent* entry;
    while ((entry = readdir(dir)) != nullptr) {
        if (entry->d_name[0] == '.') continue;
        std::string full = path + "/" + entry->d_name;
        struct stat st;
        if (stat(full.c_str(), &st) == 0 && S_ISDIR(st.st_mode)) {
            result.push_back(entry->d_name);
        }
    }
    closedir(dir);
#endif
    return result;
}

// Check if a file exists
bool FileExists(const std::string& path) {
    struct stat st;
    return stat(path.c_str(), &st) == 0;
}

}  // anonymous namespace

AgentCP& AgentCP::Instance() {
    static AgentCP instance;
    return instance;
}

AgentCP::AgentCP() = default;
AgentCP::~AgentCP() = default;

bool AgentCP::IsInitialized() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return initialized_;
}

Result AgentCP::Initialize() {
    std::lock_guard<std::mutex> lock(mutex_);
    initialized_ = true;
    return Result::Ok();
}

void AgentCP::Shutdown() {
    std::lock_guard<std::mutex> lock(mutex_);
    for (auto& kv : aids_) {
        kv.second->Invalidate();
    }
    aids_.clear();
    initialized_ = false;
}

Result AgentCP::SetBaseUrls(const std::string& ca_base, const std::string& ap_base) {
    if (ca_base.empty() || ap_base.empty()) {
        return MakeError(ErrorCode::INVALID_ARGUMENT, "base url is empty");
    }

    std::lock_guard<std::mutex> lock(mutex_);
    ca_base_ = ca_base;
    ap_base_ = ap_base;
    return Result::Ok();
}

Result AgentCP::SetProxy(const ProxyConfig& config) {
    std::lock_guard<std::mutex> lock(mutex_);
    proxy_ = config;
    return Result::Ok();
}

Result AgentCP::SetTLSPolicy(const TLSConfig& config) {
    std::lock_guard<std::mutex> lock(mutex_);
    tls_ = config;
    return Result::Ok();
}

Result AgentCP::SetStoragePath(const std::string& path) {
    if (path.empty()) {
        return MakeError(ErrorCode::INVALID_ARGUMENT, "storage path is empty");
    }

    std::lock_guard<std::mutex> lock(mutex_);
    storage_path_ = path;
    return Result::Ok();
}

Result AgentCP::SetLogLevel(LogLevel level) {
    std::lock_guard<std::mutex> lock(mutex_);
    log_level_ = level;
    return Result::Ok();
}

Result AgentCP::CreateAID(const std::string& aid, const std::string& seed_password, AgentID** out) {
    if (aid.empty() || seed_password.empty() || out == nullptr) {
        return MakeError(ErrorCode::INVALID_ARGUMENT, "invalid arguments");
    }

    std::lock_guard<std::mutex> lock(mutex_);
    if (!initialized_) {
        return MakeError(ErrorCode::NOT_INITIALIZED, "call Initialize first");
    }

    auto it = aids_.find(aid);
    if (it != aids_.end()) {
        return MakeError(ErrorCode::AID_ALREADY_EXISTS, "aid already exists");
    }

    if (ca_base_.empty()) {
        return MakeError(ErrorCode::NOT_INITIALIZED, "CA base URL not configured");
    }

    // Step 1: Generate ECDSA P-384 key
    ACP_LOGI("CreateAID: generating ECDSA P-384 key for %s", aid.c_str());
    std::string private_key_pem = crypto::GenerateECP384Key();
    if (private_key_pem.empty()) {
        ACP_LOGE("CreateAID: failed to generate ECDSA P-384 key");
        return MakeError(ErrorCode::CERT_ERROR, "failed to generate ECDSA P-384 key");
    }

    // Step 2: Generate CSR
    ACP_LOGI("CreateAID: generating CSR for %s", aid.c_str());
    std::string csr_pem = crypto::GenerateCSR(aid, private_key_pem);
    if (csr_pem.empty()) {
        ACP_LOGE("CreateAID: failed to generate CSR");
        return MakeError(ErrorCode::CERT_ERROR, "failed to generate CSR");
    }

    // Step 3: POST to CA server to get certificate
    std::string ca_url = ca_base_ + "/api/accesspoint/sign_cert";
    ACP_LOGI("CreateAID: requesting certificate from %s", ca_url.c_str());

    json req_json;
    req_json["id"] = aid;
    req_json["csr"] = csr_pem;

    net::HttpClient http;
    http.SetVerifySSL(false);
    http.SetTimeout(30);
    auto resp = http.PostJson(ca_url, req_json.dump());

    if (!resp.ok()) {
        ACP_LOGE("CreateAID: CA server returned status %d: %s",
                  resp.status_code, resp.body.substr(0, 200).c_str());
        return MakeError(ErrorCode::NETWORK_ERROR, "CA server request failed: " + std::to_string(resp.status_code) + ": " + resp.body.substr(0, 500));
    }

    // Step 4: Parse certificate from response
    std::string cert_pem;
    try {
        auto resp_json = json::parse(resp.body);
        if (resp_json.contains("certificate")) {
            cert_pem = resp_json["certificate"].get<std::string>();
        }
    } catch (...) {
        ACP_LOGE("CreateAID: failed to parse CA response");
        return MakeError(ErrorCode::NETWORK_ERROR, "failed to parse CA response");
    }

    if (cert_pem.empty()) {
        ACP_LOGE("CreateAID: no certificate in CA response");
        return MakeError(ErrorCode::NETWORK_ERROR, "no certificate in CA response");
    }
    ACP_LOGI("CreateAID: certificate received, len=%zu", cert_pem.size());

    // Step 5: Create directory structure
    std::string certs_dir = storage_path_ + "/" + aid + "/private/certs";
    if (!MakeDirsRecursive(certs_dir)) {
        ACP_LOGE("CreateAID: failed to create directory %s", certs_dir.c_str());
        return MakeError(ErrorCode::FILE_NOT_FOUND, "failed to create certs directory");
    }

    // Step 6: Save files
    std::string key_path = certs_dir + "/" + aid + ".key";
    std::string crt_path = certs_dir + "/" + aid + ".crt";
    std::string csr_path = certs_dir + "/" + aid + ".csr";

    if (!crypto::SavePrivateKeyPEM(key_path, private_key_pem, seed_password)) {
        ACP_LOGE("CreateAID: failed to save private key to %s", key_path.c_str());
        return MakeError(ErrorCode::FILE_NOT_FOUND, "failed to save private key");
    }
    ACP_LOGI("CreateAID: saved encrypted private key to %s", key_path.c_str());

    if (!crypto::SavePEMFile(crt_path, cert_pem)) {
        ACP_LOGE("CreateAID: failed to save certificate to %s", crt_path.c_str());
        return MakeError(ErrorCode::FILE_NOT_FOUND, "failed to save certificate");
    }

    if (!crypto::SavePEMFile(csr_path, csr_pem)) {
        ACP_LOGW("CreateAID: failed to save CSR to %s (non-fatal)", csr_path.c_str());
    }

    // Step 7: Create AgentID object
    auto agent = std::unique_ptr<AgentID>(new AgentID(aid));
    agent->owner_ = this;
    agent->seed_password_ = seed_password;
    agent->aid_path_ = storage_path_;
    agent->certs_path_ = certs_dir;
    agent->cert_pem_ = cert_pem;

    AgentID* raw = agent.get();
    aids_.emplace(aid, std::move(agent));
    *out = raw;
    ACP_LOGI("CreateAID: SUCCESS for %s", aid.c_str());
    return Result::Ok();
}

Result AgentCP::LoadAID(const std::string& aid, const std::string& seed_password, AgentID** out) {
    if (aid.empty() || out == nullptr) {
        return MakeError(ErrorCode::INVALID_ARGUMENT, "invalid arguments");
    }

    std::lock_guard<std::mutex> lock(mutex_);
    if (!initialized_) {
        return MakeError(ErrorCode::NOT_INITIALIZED, "call Initialize first");
    }

    // Check if already loaded in memory
    auto it = aids_.find(aid);
    if (it != aids_.end()) {
        *out = it->second.get();
        return Result::Ok();
    }

    // Try to load from disk
    std::string certs_dir = storage_path_ + "/" + aid + "/private/certs";
    std::string crt_path = certs_dir + "/" + aid + ".crt";

    if (!FileExists(crt_path)) {
        ACP_LOGE("LoadAID: certificate not found at %s", crt_path.c_str());
        return MakeError(ErrorCode::AID_NOT_FOUND, "aid not found on disk");
    }

    std::string cert_pem = crypto::ReadPEMFile(crt_path);
    if (cert_pem.empty()) {
        ACP_LOGE("LoadAID: failed to read certificate from %s", crt_path.c_str());
        return MakeError(ErrorCode::FILE_NOT_FOUND, "failed to read certificate");
    }

    auto agent = std::unique_ptr<AgentID>(new AgentID(aid));
    agent->owner_ = this;
    agent->seed_password_ = seed_password;
    agent->aid_path_ = storage_path_;
    agent->certs_path_ = certs_dir;
    agent->cert_pem_ = cert_pem;

    AgentID* raw = agent.get();
    aids_.emplace(aid, std::move(agent));
    *out = raw;
    ACP_LOGI("LoadAID: loaded %s from disk", aid.c_str());
    return Result::Ok();
}

Result AgentCP::DeleteAID(const std::string& aid) {
    if (aid.empty()) {
        return MakeError(ErrorCode::INVALID_ARGUMENT, "invalid aid");
    }

    std::lock_guard<std::mutex> lock(mutex_);
    if (!initialized_) {
        return MakeError(ErrorCode::NOT_INITIALIZED, "call Initialize first");
    }

    // Remove from memory
    auto it = aids_.find(aid);
    if (it != aids_.end()) {
        it->second->Invalidate();
        aids_.erase(it);
    }

    // Remove from disk
    std::string aid_dir = storage_path_ + "/" + aid;
    if (FileExists(aid_dir)) {
        ACP_LOGI("DeleteAID: removing directory %s", aid_dir.c_str());
        RemoveDirRecursive(aid_dir);
    }

    return Result::Ok();
}

std::vector<std::string> AgentCP::ListAIDs() {
    std::lock_guard<std::mutex> lock(mutex_);
    std::vector<std::string> ids;

    if (storage_path_.empty()) return ids;

    // Scan storage directory for subdirectories with valid cert files
    auto subdirs = ListSubdirectories(storage_path_);
    for (const auto& name : subdirs) {
        std::string crt_path = storage_path_ + "/" + name + "/private/certs/" + name + ".crt";
        if (FileExists(crt_path)) {
            ids.push_back(name);
        }
    }

    std::sort(ids.begin(), ids.end());
    return ids;
}

std::string AgentCP::GetVersion() {
    return std::to_string(ACP_VERSION_MAJOR) + "." +
        std::to_string(ACP_VERSION_MINOR) + "." +
        std::to_string(ACP_VERSION_PATCH);
}

std::string AgentCP::GetBuildInfo() {
    return std::string(__DATE__) + " " + std::string(__TIME__);
}

std::string AgentCP::GetAPBase() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return ap_base_;
}

std::string AgentCP::GetCABase() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return ca_base_;
}

std::string AgentCP::GetStoragePath() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return storage_path_;
}

}  // namespace agentcp
