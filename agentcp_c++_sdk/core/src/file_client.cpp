#include "agentcp/agentcp.h"

#include "internal.h"
#include "net/http_client.h"
#include "client/auth_client.h"

#include "third_party/json.hpp"

#include <fstream>

using json = nlohmann::json;

namespace agentcp {

FileClient::FileClient(AgentID* owner) : owner_(owner) {}

Result FileClient::UploadFile(const std::string& path,
                              FileUploadCallback callback,
                              std::string* url_out) {
    if (path.empty() || url_out == nullptr) {
        return MakeError(ErrorCode::INVALID_ARGUMENT, "invalid arguments");
    }
    if (owner_ == nullptr || !owner_->IsOnline()) {
        return MakeError(ErrorCode::NOT_INITIALIZED, "agent is offline");
    }

    // Check file exists
    {
        std::ifstream f(path);
        if (!f.good()) {
            return MakeError(ErrorCode::FILE_NOT_FOUND, "file not found: " + path);
        }
    }

    // Get owner's info
    std::string agent_id = owner_->GetAID();
    std::string signature = owner_->signature_;

    if (signature.empty() && owner_->auth_client_) {
        signature = owner_->auth_client_->GetSignature();
    }

    // Build OSS upload URL
    // Pattern: https://oss.{agent_network}/api/oss/upload_file
    // For now, use the AP base URL to derive the OSS URL
    std::string ap_base = owner_->owner_ ? owner_->owner_->GetAPBase() : "";
    if (ap_base.empty()) {
        return MakeError(ErrorCode::NOT_INITIALIZED, "AP base URL not configured");
    }

    // Derive OSS URL from AP base
    // e.g., https://ap.example.com -> https://oss.example.com/api/oss/upload_file
    std::string oss_url = ap_base;
    // Replace the subdomain: find "://" then the first "."
    auto scheme_end = oss_url.find("://");
    if (scheme_end != std::string::npos) {
        auto host_start = scheme_end + 3;
        auto first_dot = oss_url.find('.', host_start);
        if (first_dot != std::string::npos) {
            oss_url = oss_url.substr(0, scheme_end + 3) + "oss" + oss_url.substr(first_dot);
        }
    }
    oss_url += "/api/oss/upload_file";

    // Extract filename
    std::string filename = path;
    auto slash = filename.find_last_of("/\\");
    if (slash != std::string::npos) filename = filename.substr(slash + 1);

    net::HttpClient http;
    http.SetVerifySSL(false);
    http.SetUserAgent("AgentCP/0.1.0");

    std::map<std::string, std::string> fields;
    fields["agent_id"] = agent_id;
    fields["signature"] = signature;
    fields["file_name"] = filename;

    auto resp = http.PostMultipart(oss_url, fields, "file", path,
        [&callback](size_t sent, size_t total) {
            if (callback) callback(sent, total);
        });

    if (!resp.ok()) {
        return MakeError(ErrorCode::FILE_UPLOAD_FAILED,
                        "upload failed: HTTP " + std::to_string(resp.status_code));
    }

    // Parse response JSON for URL
    try {
        auto j = json::parse(resp.body);
        if (j.contains("url")) {
            *url_out = j["url"].get<std::string>();
            return Result::Ok();
        }
        return MakeError(ErrorCode::FILE_UPLOAD_FAILED, "no url in response");
    } catch (...) {
        return MakeError(ErrorCode::FILE_UPLOAD_FAILED, "invalid upload response");
    }
}

Result FileClient::DownloadFile(const std::string& url,
                                const std::string& output_path,
                                FileDownloadCallback callback) {
    if (url.empty() || output_path.empty()) {
        return MakeError(ErrorCode::INVALID_ARGUMENT, "invalid arguments");
    }
    if (owner_ == nullptr || !owner_->IsOnline()) {
        return MakeError(ErrorCode::NOT_INITIALIZED, "agent is offline");
    }

    std::string agent_id = owner_->GetAID();
    std::string signature = owner_->signature_;

    if (signature.empty() && owner_->auth_client_) {
        signature = owner_->auth_client_->GetSignature();
    }

    // Append auth params to URL
    std::string download_url = url;
    if (download_url.find('?') != std::string::npos) {
        download_url += "&";
    } else {
        download_url += "?";
    }
    download_url += "agent_id=" + agent_id + "&signature=" + signature;

    net::HttpClient http;
    http.SetVerifySSL(false);
    http.SetUserAgent("AgentCP/0.1.0");

    auto resp = http.GetToFile(download_url, output_path,
        [&callback](size_t received, size_t total) {
            if (callback) callback(received, total);
        });

    if (!resp.ok()) {
        return MakeError(ErrorCode::FILE_DOWNLOAD_FAILED,
                        "download failed: HTTP " + std::to_string(resp.status_code));
    }

    return Result::Ok();
}

}  // namespace agentcp
