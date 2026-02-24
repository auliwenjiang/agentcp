#include "agentcp/cursor_store.h"

#include <fstream>
#include <sstream>

// Use nlohmann/json for serialization
#include "third_party/json.hpp"
using json = nlohmann::json;

namespace agentcp {
namespace group {

// ============================================================
// LocalCursorStore
// ============================================================

LocalCursorStore::LocalCursorStore(const std::string& file_path)
    : file_path_(file_path) {
    if (!file_path_.empty()) {
        Load();
    }
}

LocalCursorStore::~LocalCursorStore() {
    Close();
}

void LocalCursorStore::SaveMsgCursor(const std::string& group_id, int64_t msg_cursor) {
    std::lock_guard<std::mutex> lock(mutex_);
    auto& entry = cursors_[group_id];
    if (msg_cursor > entry.msg_cursor) {
        entry.msg_cursor = msg_cursor;
        dirty_ = true;
    }
}

void LocalCursorStore::SaveEventCursor(const std::string& group_id, int64_t event_cursor) {
    std::lock_guard<std::mutex> lock(mutex_);
    auto& entry = cursors_[group_id];
    if (event_cursor > entry.event_cursor) {
        entry.event_cursor = event_cursor;
        dirty_ = true;
    }
}

std::pair<int64_t, int64_t> LocalCursorStore::LoadCursor(const std::string& group_id) {
    std::lock_guard<std::mutex> lock(mutex_);
    auto it = cursors_.find(group_id);
    if (it == cursors_.end()) {
        return {0, 0};
    }
    return {it->second.msg_cursor, it->second.event_cursor};
}

void LocalCursorStore::RemoveCursor(const std::string& group_id) {
    std::lock_guard<std::mutex> lock(mutex_);
    auto it = cursors_.find(group_id);
    if (it != cursors_.end()) {
        cursors_.erase(it);
        dirty_ = true;
    }
}

void LocalCursorStore::Flush() {
    std::lock_guard<std::mutex> lock(mutex_);
    if (file_path_.empty() || !dirty_) return;
    Write();
}

void LocalCursorStore::Close() {
    Flush();
}

void LocalCursorStore::Write() {
    try {
        json j = json::object();
        for (auto& [gid, entry] : cursors_) {
            j[gid] = {
                {"msg_cursor", entry.msg_cursor},
                {"event_cursor", entry.event_cursor}
            };
        }
        std::ofstream ofs(file_path_);
        if (ofs.is_open()) {
            ofs << j.dump(2);
            dirty_ = false;
        }
    } catch (...) {
        // silently ignore write errors
    }
}

void LocalCursorStore::Load() {
    try {
        std::ifstream ifs(file_path_);
        if (!ifs.is_open()) return;

        std::ostringstream ss;
        ss << ifs.rdbuf();
        std::string content = ss.str();
        if (content.empty()) return;

        auto j = json::parse(content);
        for (auto& [key, val] : j.items()) {
            CursorEntry entry;
            entry.msg_cursor = val.value("msg_cursor", (int64_t)0);
            entry.event_cursor = val.value("event_cursor", (int64_t)0);
            cursors_[key] = entry;
        }
    } catch (...) {
        // silently ignore load errors
    }
}

}  // namespace group
}  // namespace agentcp
