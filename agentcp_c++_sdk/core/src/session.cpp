#include "agentcp/agentcp.h"

#include "internal.h"

namespace agentcp {

Session::Session(AgentID* owner, const std::string& session_id)
    : owner_(owner), session_id_(session_id) {}

std::string Session::GetSessionId() const {
    return session_id_;
}

std::vector<SessionMember> Session::GetMembers() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return members_;
}

bool Session::IsMember(const std::string& agent_id) const {
    std::lock_guard<std::mutex> lock(mutex_);
    for (const auto& member : members_) {
        if (member.agent_id == agent_id) {
            return true;
        }
    }
    return false;
}

Result Session::SendMessage(const std::vector<Block>& blocks) {
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (closed_) {
            return MakeError(ErrorCode::SESSION_CLOSED, "session is closed");
        }
    }
    if (owner_ == nullptr) {
        return MakeError(ErrorCode::NOT_INITIALIZED, "owner is null");
    }
    return owner_->SendMessage(session_id_, blocks);
}

Result Session::SendMessageWithInstruction(const std::vector<Block>& blocks,
                                           const Instruction& instruction) {
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (closed_) {
            return MakeError(ErrorCode::SESSION_CLOSED, "session is closed");
        }
    }
    if (owner_ == nullptr) {
        return MakeError(ErrorCode::NOT_INITIALIZED, "owner is null");
    }
    return owner_->SendMessageWithInstruction(session_id_, blocks, instruction);
}

Result Session::CreateStream(const std::string& receiver,
                             const std::string& content_type,
                             Stream** out) {
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (closed_) {
            return MakeError(ErrorCode::SESSION_CLOSED, "session is closed");
        }
    }
    if (owner_ == nullptr) {
        return MakeError(ErrorCode::NOT_INITIALIZED, "owner is null");
    }
    return owner_->CreateStream(session_id_, receiver, content_type, out);
}

Result Session::SendFile(const std::string& file_path, FileUploadCallback callback) {
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (closed_) {
            return MakeError(ErrorCode::SESSION_CLOSED, "session is closed");
        }
    }
    if (owner_ == nullptr) {
        return MakeError(ErrorCode::NOT_INITIALIZED, "owner is null");
    }
    std::string url;
    Result r = owner_->UploadFile(file_path, callback, &url);
    if (!r) {
        return r;
    }

    // Extract filename from path
    std::string filename = file_path;
    auto slash = filename.find_last_of("/\\");
    if (slash != std::string::npos) filename = filename.substr(slash + 1);

    // Send a file block with the URL
    Block block;
    block.type = BlockType::File;
    block.text = url;
    FileContent fc;
    fc.url = url;
    fc.file_name = filename;
    block.file = fc;

    std::vector<Block> blocks = {block};
    return owner_->SendMessage(session_id_, blocks);
}

Result Session::GetMessages(int limit, int offset, std::vector<Message>* messages_out) {
    (void)limit;
    (void)offset;
    if (messages_out == nullptr) {
        return MakeError(ErrorCode::INVALID_ARGUMENT, "messages_out is null");
    }
    return MakeError(ErrorCode::NOT_IMPLEMENTED, "get messages not implemented");
}

}  // namespace agentcp
