#pragma once

#include <cstdint>
#include <map>
#include <mutex>
#include <string>
#include <utility>

#include "agentcp/export.h"

namespace agentcp {
namespace group {

// ============================================================
// CursorStore - abstract interface for cursor persistence
// ============================================================

class ACP_API CursorStore {
public:
    virtual ~CursorStore() = default;

    virtual void SaveMsgCursor(const std::string& group_id, int64_t msg_cursor) = 0;
    virtual void SaveEventCursor(const std::string& group_id, int64_t event_cursor) = 0;

    /// Returns {msg_cursor, event_cursor}
    virtual std::pair<int64_t, int64_t> LoadCursor(const std::string& group_id) = 0;

    virtual void RemoveCursor(const std::string& group_id) = 0;
    virtual void Flush() = 0;
    virtual void Close() = 0;
};

// ============================================================
// LocalCursorStore - in-memory + JSON file persistence
// ============================================================

class ACP_API LocalCursorStore : public CursorStore {
public:
    /// @param file_path  JSON file path. Empty = pure in-memory mode.
    explicit LocalCursorStore(const std::string& file_path = "");
    ~LocalCursorStore() override;

    void SaveMsgCursor(const std::string& group_id, int64_t msg_cursor) override;
    void SaveEventCursor(const std::string& group_id, int64_t event_cursor) override;
    std::pair<int64_t, int64_t> LoadCursor(const std::string& group_id) override;
    void RemoveCursor(const std::string& group_id) override;
    void Flush() override;
    void Close() override;

private:
    void Load();
    void Write();

    struct CursorEntry {
        int64_t msg_cursor = 0;
        int64_t event_cursor = 0;
    };

    std::string file_path_;
    bool dirty_ = false;
    mutable std::mutex mutex_;
    std::map<std::string, CursorEntry> cursors_;
};

}  // namespace group
}  // namespace agentcp
