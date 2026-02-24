#pragma once

#include <cstdint>
#include <functional>
#include <map>
#include <optional>
#include <string>
#include <vector>

#include "agentcp/result.h"

namespace agentcp {

enum class LogLevel {
    Error = 0,
    Warn = 1,
    Info = 2,
    Debug = 3,
    Trace = 4
};

enum class AgentState {
    Offline,
    Connecting,
    Authenticating,
    Online,
    Reconnecting,
    Error
};

enum class ErrorSeverity {
    Info,
    Warning,
    Error,
    Fatal
};

enum class BlockType {
    Content,
    File,
    Image,
    Audio,
    Video,
    Form,
    FormResult,
    Instruction
};

enum class BlockStatus {
    Pending,
    Sent,
    Delivered,
    Failed
};

struct ProxyConfig {
    enum class Type { None, Http, Socks5, System };

    Type type = Type::None;
    std::string host;
    uint16_t port = 0;
    std::string username;
    std::string password;
    std::vector<std::string> bypass_list;
};

struct TLSConfig {
    bool verify = true;
    bool allow_self_signed = false;
    std::string ca_cert_path;
    std::string client_cert_path;
    std::string client_key_path;
    std::vector<std::string> pinned_certs;
};

struct ApConfig {
    std::string heartbeat_server;
    std::string message_server;
};

struct FileContent {
    std::string url;
    std::string file_name;
    size_t file_size = 0;
    std::string mime_type;
    std::string md5;
};

struct ImageContent {
    std::string url;
    std::string thumbnail_url;
    int width = 0;
    int height = 0;
    size_t file_size = 0;
};

struct AudioContent {
    std::string url;
    int duration = 0;
    size_t file_size = 0;
    std::string mime_type;
};

struct VideoContent {
    std::string url;
    std::string thumbnail_url;
    int duration = 0;
    int width = 0;
    int height = 0;
    size_t file_size = 0;
    std::string mime_type;
};

struct FormField {
    std::string field_id;
    std::string label;
    std::string type;
    bool required = false;
    std::vector<std::string> options;
};

struct FormContent {
    std::string form_id;
    std::string title;
    std::string description;
    std::vector<FormField> fields;
};

struct FormResultContent {
    std::string form_id;
    std::map<std::string, std::string> results;
};

struct Instruction {
    std::string cmd;
    std::map<std::string, std::string> params;
    std::string description;
    std::string model;
};

struct Block {
    BlockType type = BlockType::Content;
    BlockStatus status = BlockStatus::Pending;
    uint64_t timestamp = 0;

    std::string text;
    std::optional<FileContent> file;
    std::optional<ImageContent> image;
    std::optional<AudioContent> audio;
    std::optional<VideoContent> video;
    std::optional<FormContent> form;
    std::optional<FormResultContent> form_result;
    std::optional<Instruction> instruction;

    static Block Text(const std::string& content) {
        Block b;
        b.type = BlockType::Content;
        b.text = content;
        return b;
    }

    static Block File(const FileContent& content) {
        Block b;
        b.type = BlockType::File;
        b.file = content;
        return b;
    }

    static Block Image(const ImageContent& content) {
        Block b;
        b.type = BlockType::Image;
        b.image = content;
        return b;
    }

    static Block Audio(const AudioContent& content) {
        Block b;
        b.type = BlockType::Audio;
        b.audio = content;
        return b;
    }

    static Block Video(const VideoContent& content) {
        Block b;
        b.type = BlockType::Video;
        b.video = content;
        return b;
    }

    static Block Form(const FormContent& content) {
        Block b;
        b.type = BlockType::Form;
        b.form = content;
        return b;
    }

    static Block FormResult(const FormResultContent& content) {
        Block b;
        b.type = BlockType::FormResult;
        b.form_result = content;
        return b;
    }

    static Block InstructionBlock(const Instruction& content) {
        Block b;
        b.type = BlockType::Instruction;
        b.instruction = content;
        return b;
    }
};

struct Message {
    std::string message_id;
    std::string session_id;
    std::string sender;
    std::string receiver;
    std::string ref_msg_id;
    uint64_t timestamp = 0;
    std::vector<Block> blocks;
    std::optional<Instruction> instruction;
};

struct SessionMember {
    std::string agent_id;
    std::string role;
    uint64_t joined_at = 0;
};

struct SessionInfo {
    std::string session_id;
    std::vector<SessionMember> members;
    uint64_t created_at = 0;
    uint64_t updated_at = 0;
    std::string last_msg_id;
};

struct MetricsSnapshot {
    uint64_t message_count = 0;
    uint64_t avg_latency_ms = 0;
    uint64_t max_latency_ms = 0;
    uint64_t reconnect_count = 0;
    std::map<std::string, uint64_t> error_counts;
    uint64_t timestamp = 0;
};

struct ErrorInfo {
    std::string subsystem;
    std::string code;
    std::string message;
    ErrorSeverity severity = ErrorSeverity::Error;
    std::map<std::string, std::string> context;
    uint64_t timestamp = 0;
};

using MessageHandler = std::function<void(const Message& message)>;
using ErrorHandler = std::function<void(const ErrorInfo& error)>;
using StateChangeHandler = std::function<void(AgentState old_state, AgentState new_state)>;
using MetricsHandler = std::function<void(const MetricsSnapshot& snapshot)>;
using FileUploadCallback = std::function<void(size_t bytes_sent, size_t total_bytes)>;
using FileDownloadCallback = std::function<void(size_t bytes_received, size_t total_bytes)>;
using InviteHandler = std::function<void(const std::string& session_id, const std::string& inviter_id)>;

}  // namespace agentcp
