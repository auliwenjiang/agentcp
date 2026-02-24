#include <jni.h>

#include <string>
#include <vector>

#include <android/log.h>
#define JNI_LOG(fmt, ...) __android_log_print(ANDROID_LOG_INFO, "AgentCP_JNI", fmt, ##__VA_ARGS__)
#define JNI_LOGW(fmt, ...) __android_log_print(ANDROID_LOG_WARN, "AgentCP_JNI", fmt, ##__VA_ARGS__)
#define JNI_LOGE(fmt, ...) __android_log_print(ANDROID_LOG_ERROR, "AgentCP_JNI", fmt, ##__VA_ARGS__)

#include "agentcp/agentcp.h"
#include "net/http_client.h"
#include "third_party/json.hpp"

using json = nlohmann::json;

namespace {

JavaVM* g_jvm = nullptr;

std::string JStringToString(JNIEnv* env, jstring value) {
    if (value == nullptr) {
        return std::string();
    }
    const char* chars = env->GetStringUTFChars(value, nullptr);
    if (chars == nullptr) {
        return std::string();
    }
    std::string result(chars);
    env->ReleaseStringUTFChars(value, chars);
    return result;
}

jobject MakeResult(JNIEnv* env, const agentcp::Result& result) {
    jclass cls = env->FindClass("com/agentcp/Result");
    if (cls == nullptr) {
        return nullptr;
    }
    jmethodID ctor = env->GetMethodID(cls, "<init>", "(ILjava/lang/String;Ljava/lang/String;)V");
    if (ctor == nullptr) {
        env->DeleteLocalRef(cls);
        return nullptr;
    }
    jstring message = env->NewStringUTF(result.message.empty() ? "" : result.message.c_str());
    jstring context = env->NewStringUTF(result.context.empty() ? "" : result.context.c_str());
    jobject obj = env->NewObject(cls, ctor, static_cast<jint>(result.code), message, context);
    env->DeleteLocalRef(message);
    env->DeleteLocalRef(context);
    env->DeleteLocalRef(cls);
    return obj;
}

void ThrowAgentCPException(JNIEnv* env, const agentcp::Result& result) {
    jclass exc_cls = env->FindClass("com/agentcp/AgentCPException");
    if (exc_cls == nullptr) {
        env->ExceptionClear();
        jclass runtime_cls = env->FindClass("java/lang/RuntimeException");
        if (runtime_cls != nullptr) {
            env->ThrowNew(runtime_cls, "AgentCP error");
            env->DeleteLocalRef(runtime_cls);
        }
        return;
    }
    jmethodID ctor = env->GetMethodID(exc_cls, "<init>", "(Lcom/agentcp/Result;)V");
    if (ctor == nullptr) {
        env->DeleteLocalRef(exc_cls);
        env->ExceptionClear();
        jclass runtime_cls = env->FindClass("java/lang/RuntimeException");
        if (runtime_cls != nullptr) {
            env->ThrowNew(runtime_cls, "AgentCP error");
            env->DeleteLocalRef(runtime_cls);
        }
        return;
    }
    jobject result_obj = MakeResult(env, result);
    if (result_obj == nullptr) {
        env->DeleteLocalRef(exc_cls);
        jclass runtime_cls = env->FindClass("java/lang/RuntimeException");
        if (runtime_cls != nullptr) {
            env->ThrowNew(runtime_cls, "AgentCP error");
            env->DeleteLocalRef(runtime_cls);
        }
        return;
    }
    jobject exc_obj = env->NewObject(exc_cls, ctor, result_obj);
    env->DeleteLocalRef(result_obj);
    env->DeleteLocalRef(exc_cls);
    if (exc_obj != nullptr) {
        env->Throw(static_cast<jthrowable>(exc_obj));
        env->DeleteLocalRef(exc_obj);
    }
}

JNIEnv* GetEnv() {
    JNIEnv* env = nullptr;
    if (g_jvm) {
        g_jvm->GetEnv(reinterpret_cast<void**>(&env), JNI_VERSION_1_6);
    }
    return env;
}

JNIEnv* AttachCurrentThread() {
    JNIEnv* env = nullptr;
    if (g_jvm) {
        if (g_jvm->GetEnv(reinterpret_cast<void**>(&env), JNI_VERSION_1_6) == JNI_EDETACHED) {
            g_jvm->AttachCurrentThread(&env, nullptr);
        }
    }
    return env;
}

void LogAndClearJavaException(JNIEnv* env, const char* where) {
    if (env != nullptr && env->ExceptionCheck()) {
        JNI_LOGE("%s: Java exception raised from callback", where);
        env->ExceptionDescribe();
        env->ExceptionClear();
    }
}

std::string BlocksToJson(const std::vector<agentcp::Block>& blocks) {
    json arr = json::array();
    for (const auto& b : blocks) {
        json obj;
        obj["type"] = static_cast<int>(b.type);
        obj["text"] = b.text;
        obj["timestamp"] = b.timestamp;
        arr.push_back(obj);
    }
    return arr.dump();
}

std::vector<agentcp::Block> JsonToBlocks(const std::string& blocks_json) {
    std::vector<agentcp::Block> blocks;
    try {
        json arr = json::parse(blocks_json);
        for (const auto& obj : arr) {
            std::string text = obj.value("text", "");
            blocks.push_back(agentcp::Block::Text(text));
        }
    } catch (...) {
        // If parse fails, treat entire string as single text block
        blocks.push_back(agentcp::Block::Text(blocks_json));
    }
    return blocks;
}

}  // namespace

extern "C" JNIEXPORT jint JNICALL
JNI_OnLoad(JavaVM* vm, void* /*reserved*/) {
    g_jvm = vm;

    // Register Java-based DNS resolver so native HTTP uses Android's DNS stack
    agentcp::net::HttpClient::SetDnsResolver([](const std::string& host) -> std::string {
        JNIEnv* env = nullptr;
        bool attached = false;
        if (g_jvm->GetEnv(reinterpret_cast<void**>(&env), JNI_VERSION_1_6) == JNI_EDETACHED) {
            g_jvm->AttachCurrentThread(&env, nullptr);
            attached = true;
        }
        if (!env) return "";

        std::string result;
        jclass inet_cls = env->FindClass("java/net/InetAddress");
        if (inet_cls) {
            jmethodID getByName = env->GetStaticMethodID(inet_cls, "getByName",
                "(Ljava/lang/String;)Ljava/net/InetAddress;");
            jmethodID getHostAddr = env->GetMethodID(inet_cls, "getHostAddress",
                "()Ljava/lang/String;");
            if (getByName && getHostAddr) {
                jstring jhost = env->NewStringUTF(host.c_str());
                jobject addr = env->CallStaticObjectMethod(inet_cls, getByName, jhost);
                if (env->ExceptionCheck()) {
                    env->ExceptionClear();
                } else if (addr) {
                    jstring jip = (jstring)env->CallObjectMethod(addr, getHostAddr);
                    if (jip) {
                        const char* ip = env->GetStringUTFChars(jip, nullptr);
                        if (ip) {
                            result = ip;
                            env->ReleaseStringUTFChars(jip, ip);
                        }
                        env->DeleteLocalRef(jip);
                    }
                    env->DeleteLocalRef(addr);
                }
                env->DeleteLocalRef(jhost);
            }
            env->DeleteLocalRef(inet_cls);
        }

        if (attached) {
            g_jvm->DetachCurrentThread();
        }
        return result;
    });

    return JNI_VERSION_1_6;
}

extern "C" JNIEXPORT jobject JNICALL
Java_com_agentcp_AgentCP_nativeInitialize(JNIEnv* env, jobject /*thiz*/) {
    agentcp::Result r = agentcp::AgentCP::Instance().Initialize();
    return MakeResult(env, r);
}

extern "C" JNIEXPORT void JNICALL
Java_com_agentcp_AgentCP_nativeShutdown(JNIEnv* /*env*/, jobject /*thiz*/) {
    agentcp::AgentCP::Instance().Shutdown();
}

extern "C" JNIEXPORT jobject JNICALL
Java_com_agentcp_AgentCP_nativeSetBaseUrls(JNIEnv* env, jobject /*thiz*/, jstring ca_base, jstring ap_base) {
    std::string ca = JStringToString(env, ca_base);
    std::string ap = JStringToString(env, ap_base);
    agentcp::Result r = agentcp::AgentCP::Instance().SetBaseUrls(ca, ap);
    return MakeResult(env, r);
}

extern "C" JNIEXPORT jobject JNICALL
Java_com_agentcp_AgentCP_nativeSetStoragePath(JNIEnv* env, jobject /*thiz*/, jstring path) {
    std::string storage = JStringToString(env, path);
    agentcp::Result r = agentcp::AgentCP::Instance().SetStoragePath(storage);
    return MakeResult(env, r);
}

extern "C" JNIEXPORT jobject JNICALL
Java_com_agentcp_AgentCP_nativeSetLogLevel(JNIEnv* env, jobject /*thiz*/, jint level) {
    agentcp::LogLevel lvl = static_cast<agentcp::LogLevel>(level);
    agentcp::Result r = agentcp::AgentCP::Instance().SetLogLevel(lvl);
    return MakeResult(env, r);
}

extern "C" JNIEXPORT jlong JNICALL
Java_com_agentcp_AgentCP_nativeCreateAID(JNIEnv* env, jobject /*thiz*/, jstring aid, jstring password) {
    std::string aid_str = JStringToString(env, aid);
    std::string password_str = JStringToString(env, password);

    agentcp::AgentID* out = nullptr;
    agentcp::Result r = agentcp::AgentCP::Instance().CreateAID(aid_str, password_str, &out);
    if (!r) {
        ThrowAgentCPException(env, r);
        return 0;
    }
    return reinterpret_cast<jlong>(out);
}

extern "C" JNIEXPORT jlong JNICALL
Java_com_agentcp_AgentCP_nativeLoadAID(JNIEnv* env, jobject /*thiz*/, jstring aid, jstring seed_password) {
    std::string aid_str = JStringToString(env, aid);
    std::string password_str = JStringToString(env, seed_password);

    agentcp::AgentID* out = nullptr;
    agentcp::Result r = agentcp::AgentCP::Instance().LoadAID(aid_str, password_str, &out);
    if (!r) {
        ThrowAgentCPException(env, r);
        return 0;
    }
    return reinterpret_cast<jlong>(out);
}

extern "C" JNIEXPORT jobject JNICALL
Java_com_agentcp_AgentCP_nativeDeleteAID(JNIEnv* env, jobject /*thiz*/, jstring aid) {
    std::string aid_str = JStringToString(env, aid);
    agentcp::Result r = agentcp::AgentCP::Instance().DeleteAID(aid_str);
    return MakeResult(env, r);
}

extern "C" JNIEXPORT jobjectArray JNICALL
Java_com_agentcp_AgentCP_nativeListAIDs(JNIEnv* env, jobject /*thiz*/) {
    std::vector<std::string> aids = agentcp::AgentCP::Instance().ListAIDs();
    jclass string_cls = env->FindClass("java/lang/String");
    jobjectArray array = env->NewObjectArray(static_cast<jsize>(aids.size()), string_cls, nullptr);
    for (jsize i = 0; i < static_cast<jsize>(aids.size()); ++i) {
        jstring value = env->NewStringUTF(aids[static_cast<size_t>(i)].c_str());
        env->SetObjectArrayElement(array, i, value);
        env->DeleteLocalRef(value);
    }
    return array;
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_agentcp_AgentCP_nativeGetVersion(JNIEnv* env, jobject /*thiz*/) {
    std::string version = agentcp::AgentCP::GetVersion();
    return env->NewStringUTF(version.c_str());
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_agentcp_AgentCP_nativeGetBuildInfo(JNIEnv* env, jobject /*thiz*/) {
    std::string info = agentcp::AgentCP::GetBuildInfo();
    return env->NewStringUTF(info.c_str());
}

extern "C" JNIEXPORT jobject JNICALL
Java_com_agentcp_AgentID_nativeOnline(JNIEnv* env, jobject /*thiz*/, jlong handle) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (aid == nullptr || !aid->IsValid()) {
        return MakeResult(env, agentcp::Result::Error(agentcp::ErrorCode::AID_INVALID, "invalid handle"));
    }
    agentcp::Result r = aid->Online();
    return MakeResult(env, r);
}

extern "C" JNIEXPORT void JNICALL
Java_com_agentcp_AgentID_nativeOffline(JNIEnv* /*env*/, jobject /*thiz*/, jlong handle) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (aid != nullptr && aid->IsValid()) {
        aid->Offline();
    }
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_agentcp_AgentID_nativeIsOnline(JNIEnv* /*env*/, jobject /*thiz*/, jlong handle) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (aid == nullptr || !aid->IsValid()) {
        return JNI_FALSE;
    }
    return aid->IsOnline() ? JNI_TRUE : JNI_FALSE;
}

extern "C" JNIEXPORT jint JNICALL
Java_com_agentcp_AgentID_nativeGetState(JNIEnv* /*env*/, jobject /*thiz*/, jlong handle) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (aid == nullptr || !aid->IsValid()) {
        return static_cast<jint>(agentcp::AgentState::Error);
    }
    return static_cast<jint>(aid->GetState());
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_agentcp_AgentID_nativeGetAID(JNIEnv* env, jobject /*thiz*/, jlong handle) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (aid == nullptr || !aid->IsValid()) {
        return env->NewStringUTF("");
    }
    std::string value = aid->GetAID();
    return env->NewStringUTF(value.c_str());
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_agentcp_AgentID_nativeGetSignature(JNIEnv* env, jobject /*thiz*/, jlong handle) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (aid == nullptr || !aid->IsValid()) {
        return env->NewStringUTF("");
    }
    std::string value = aid->GetSignature();
    return env->NewStringUTF(value.c_str());
}

extern "C" JNIEXPORT void JNICALL
Java_com_agentcp_AgentID_nativeRelease(JNIEnv* /*env*/, jobject /*thiz*/, jlong /*handle*/) {
    // AgentID instances are owned by AgentCP; no-op.
}

// --- Callback handlers ---

extern "C" JNIEXPORT void JNICALL
Java_com_agentcp_AgentID_nativeSetMessageHandler(JNIEnv* env, jobject /*thiz*/, jlong handle, jobject callback) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (aid == nullptr || !aid->IsValid()) return;

    if (callback == nullptr) {
        aid->SetMessageHandler(nullptr);
        return;
    }

    jobject global_cb = env->NewGlobalRef(callback);
    aid->SetMessageHandler([global_cb](const agentcp::Message& msg) {
        JNI_LOG("MessageHandler called, msg_id=%s, sender=%s, session=%s",
                msg.message_id.c_str(), msg.sender.c_str(), msg.session_id.c_str());

        JNIEnv* cb_env = AttachCurrentThread();
        if (cb_env == nullptr) {
            JNI_LOGE("Failed to attach current thread");
            return;
        }

        jclass cls = cb_env->GetObjectClass(global_cb);
        if (cls == nullptr) {
            JNI_LOGE("Failed to get callback class");
            return;
        }
        jmethodID mid = cb_env->GetMethodID(cls, "onMessage",
            "(Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;JLjava/lang/String;)V");
        cb_env->DeleteLocalRef(cls);
        if (mid == nullptr) {
            JNI_LOGE("Failed to get onMessage method");
            return;
        }

        jstring messageId = cb_env->NewStringUTF(msg.message_id.c_str());
        jstring sessionId = cb_env->NewStringUTF(msg.session_id.c_str());
        jstring sender = cb_env->NewStringUTF(msg.sender.c_str());
        std::string blocks_json = BlocksToJson(msg.blocks);
        jstring blocksJson = cb_env->NewStringUTF(blocks_json.c_str());

        JNI_LOG("Calling Java onMessage callback");
        cb_env->CallVoidMethod(global_cb, mid, messageId, sessionId, sender,
                               static_cast<jlong>(msg.timestamp), blocksJson);

        cb_env->DeleteLocalRef(messageId);
        cb_env->DeleteLocalRef(sessionId);
        cb_env->DeleteLocalRef(sender);
        cb_env->DeleteLocalRef(blocksJson);
    });
}

extern "C" JNIEXPORT void JNICALL
Java_com_agentcp_AgentID_nativeSetInviteHandler(JNIEnv* env, jobject /*thiz*/, jlong handle, jobject callback) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (aid == nullptr || !aid->IsValid()) return;

    if (callback == nullptr) {
        aid->SetInviteHandler(nullptr);
        return;
    }

    jobject global_cb = env->NewGlobalRef(callback);
    aid->SetInviteHandler([global_cb](const std::string& session_id, const std::string& inviter_id) {
        JNIEnv* cb_env = AttachCurrentThread();
        if (cb_env == nullptr) return;

        jclass cls = cb_env->GetObjectClass(global_cb);
        if (cls == nullptr) return;
        jmethodID mid = cb_env->GetMethodID(cls, "onInvite",
            "(Ljava/lang/String;Ljava/lang/String;)V");
        cb_env->DeleteLocalRef(cls);
        if (mid == nullptr) return;

        jstring jSessionId = cb_env->NewStringUTF(session_id.c_str());
        jstring jInviterId = cb_env->NewStringUTF(inviter_id.c_str());

        cb_env->CallVoidMethod(global_cb, mid, jSessionId, jInviterId);

        cb_env->DeleteLocalRef(jSessionId);
        cb_env->DeleteLocalRef(jInviterId);
    });
}

extern "C" JNIEXPORT void JNICALL
Java_com_agentcp_AgentID_nativeSetStateChangeHandler(JNIEnv* env, jobject /*thiz*/, jlong handle, jobject callback) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (aid == nullptr || !aid->IsValid()) return;

    if (callback == nullptr) {
        aid->SetStateChangeHandler(nullptr);
        return;
    }

    jobject global_cb = env->NewGlobalRef(callback);
    aid->SetStateChangeHandler([global_cb](agentcp::AgentState old_state, agentcp::AgentState new_state) {
        JNIEnv* cb_env = AttachCurrentThread();
        if (cb_env == nullptr) return;

        jclass cls = cb_env->GetObjectClass(global_cb);
        if (cls == nullptr) return;
        jmethodID mid = cb_env->GetMethodID(cls, "onStateChange", "(II)V");
        cb_env->DeleteLocalRef(cls);
        if (mid == nullptr) return;

        cb_env->CallVoidMethod(global_cb, mid,
                               static_cast<jint>(old_state),
                               static_cast<jint>(new_state));
    });
}

// --- Session management ---

extern "C" JNIEXPORT jstring JNICALL
Java_com_agentcp_AgentID_nativeCreateSession(JNIEnv* env, jobject /*thiz*/, jlong handle, jobjectArray members) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (aid == nullptr || !aid->IsValid()) {
        return env->NewStringUTF("");
    }

    std::vector<std::string> member_list;
    if (members != nullptr) {
        jsize len = env->GetArrayLength(members);
        for (jsize i = 0; i < len; ++i) {
            auto elem = static_cast<jstring>(env->GetObjectArrayElement(members, i));
            member_list.push_back(JStringToString(env, elem));
            env->DeleteLocalRef(elem);
        }
    }

    JNI_LOG("nativeCreateSession: self='%s', memberCount=%zu", aid->GetAID().c_str(), member_list.size());
    for (size_t i = 0; i < member_list.size(); ++i) {
        JNI_LOG("nativeCreateSession: member[%zu]='%s' (len=%zu)", i, member_list[i].c_str(), member_list[i].size());
    }

    std::string session_id;
    agentcp::Result r = aid->Sessions().CreateSession(member_list, &session_id);
    if (!r) {
        JNI_LOG("nativeCreateSession: FAILED code=%d msg='%s'", r.code, r.message.c_str());
        ThrowAgentCPException(env, r);
        return nullptr;
    }
    JNI_LOG("nativeCreateSession: OK session_id='%s'", session_id.c_str());
    return env->NewStringUTF(session_id.c_str());
}

extern "C" JNIEXPORT jobject JNICALL
Java_com_agentcp_AgentID_nativeInviteAgent(JNIEnv* env, jobject /*thiz*/, jlong handle, jstring session_id, jstring agent_id) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (aid == nullptr || !aid->IsValid()) {
        return MakeResult(env, agentcp::Result::Error(agentcp::ErrorCode::AID_INVALID, "invalid handle"));
    }
    std::string sid = JStringToString(env, session_id);
    std::string target = JStringToString(env, agent_id);
    agentcp::Result r = aid->Sessions().InviteAgent(sid, target);
    return MakeResult(env, r);
}

extern "C" JNIEXPORT jobject JNICALL
Java_com_agentcp_AgentID_nativeJoinSession(JNIEnv* env, jobject /*thiz*/, jlong handle, jstring session_id) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (aid == nullptr || !aid->IsValid()) {
        return MakeResult(env, agentcp::Result::Error(agentcp::ErrorCode::AID_INVALID, "invalid handle"));
    }
    std::string sid = JStringToString(env, session_id);
    agentcp::Result r = aid->Sessions().JoinSession(sid);
    return MakeResult(env, r);
}

extern "C" JNIEXPORT jobjectArray JNICALL
Java_com_agentcp_AgentID_nativeGetActiveSessions(JNIEnv* env, jobject /*thiz*/, jlong handle) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    jclass string_cls = env->FindClass("java/lang/String");
    if (aid == nullptr || !aid->IsValid()) {
        return env->NewObjectArray(0, string_cls, nullptr);
    }
    std::vector<std::string> sessions = aid->Sessions().GetActiveSessions();
    jobjectArray array = env->NewObjectArray(static_cast<jsize>(sessions.size()), string_cls, nullptr);
    for (jsize i = 0; i < static_cast<jsize>(sessions.size()); ++i) {
        jstring value = env->NewStringUTF(sessions[static_cast<size_t>(i)].c_str());
        env->SetObjectArrayElement(array, i, value);
        env->DeleteLocalRef(value);
    }
    return array;
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_agentcp_AgentID_nativeGetSessionInfo(JNIEnv* env, jobject /*thiz*/, jlong handle, jstring session_id) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (aid == nullptr || !aid->IsValid()) {
        return env->NewStringUTF("{}");
    }
    std::string sid = JStringToString(env, session_id);
    agentcp::SessionInfo info;
    agentcp::Result r = aid->Sessions().GetSessionInfo(sid, &info);
    if (!r) {
        return env->NewStringUTF("{}");
    }

    json j;
    j["session_id"] = info.session_id;
    j["created_at"] = info.created_at;
    j["updated_at"] = info.updated_at;
    j["last_msg_id"] = info.last_msg_id;
    json members_arr = json::array();
    for (const auto& m : info.members) {
        json mj;
        mj["agent_id"] = m.agent_id;
        mj["role"] = m.role;
        mj["joined_at"] = m.joined_at;
        members_arr.push_back(mj);
    }
    j["members"] = members_arr;

    std::string result_str = j.dump();
    return env->NewStringUTF(result_str.c_str());
}

extern "C" JNIEXPORT jobject JNICALL
Java_com_agentcp_AgentID_nativeSendMessage(JNIEnv* env, jobject /*thiz*/, jlong handle, jstring session_id, jstring peer_aid, jstring blocks_json) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (aid == nullptr || !aid->IsValid()) {
        return MakeResult(env, agentcp::Result::Error(agentcp::ErrorCode::AID_INVALID, "invalid handle"));
    }
    std::string sid = JStringToString(env, session_id);
    std::string peer = JStringToString(env, peer_aid);
    std::string bj = JStringToString(env, blocks_json);
    JNI_LOG("nativeSendMessage: session=%s, peer='%s', blocks_len=%zu", sid.c_str(), peer.c_str(), bj.size());
    std::vector<agentcp::Block> blocks = JsonToBlocks(bj);
    agentcp::Result r = aid->SendMessage(sid, peer, blocks);
    return MakeResult(env, r);
}

// ============================================================
// Group Module JNI
// ============================================================

extern "C" JNIEXPORT void JNICALL
Java_com_agentcp_AgentID_nativeInitGroupClient(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                                jstring session_id, jstring target_aid) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (aid == nullptr || !aid->IsValid()) return;
    std::string sid = JStringToString(env, session_id);
    std::string ta = JStringToString(env, target_aid);
    aid->InitGroupClient(sid, ta);
}

extern "C" JNIEXPORT void JNICALL
Java_com_agentcp_AgentID_nativeCloseGroupClient(JNIEnv* /*env*/, jobject /*thiz*/, jlong handle) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (aid == nullptr || !aid->IsValid()) return;
    aid->CloseGroupClient();
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_agentcp_AgentID_nativeGetGroupTargetAid(JNIEnv* env, jobject /*thiz*/, jlong handle) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (aid == nullptr || !aid->IsValid()) return env->NewStringUTF("");
    return env->NewStringUTF(aid->GetGroupTargetAid().c_str());
}

extern "C" JNIEXPORT void JNICALL
Java_com_agentcp_AgentID_nativeSetGroupEventHandler(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                                     jobject msg_callback, jobject event_callback) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (aid == nullptr || !aid->IsValid() || aid->GroupClient() == nullptr) return;

    if (msg_callback == nullptr && event_callback == nullptr) {
        aid->SetGroupEventHandler(nullptr);
        return;
    }

    // Create persistent global refs
    jobject g_msg_cb = msg_callback ? env->NewGlobalRef(msg_callback) : nullptr;
    jobject g_evt_cb = event_callback ? env->NewGlobalRef(event_callback) : nullptr;

    // Create a C++ event handler that dispatches to Java callbacks
    // Using a static class so the pointers survive across calls
    class JniGroupEventHandler : public agentcp::group::ACPGroupEventHandler {
    public:
        jobject msg_cb;
        jobject evt_cb;

        JniGroupEventHandler(jobject mc, jobject ec) : msg_cb(mc), evt_cb(ec) {}

        ~JniGroupEventHandler() override {
            JNIEnv* e = AttachCurrentThread();
            if (e) {
                if (msg_cb) e->DeleteGlobalRef(msg_cb);
                if (evt_cb) e->DeleteGlobalRef(evt_cb);
            }
        }

        void OnNewMessage(const std::string& group_id, int64_t latest_msg_id,
                          const std::string& sender, const std::string& preview) override {
            if (!evt_cb) return;
            JNIEnv* e = AttachCurrentThread();
            if (!e) return;
            jclass cls = e->GetObjectClass(evt_cb);
            jmethodID mid = e->GetMethodID(cls, "onNewMessage",
                "(Ljava/lang/String;JLjava/lang/String;Ljava/lang/String;)V");
            e->DeleteLocalRef(cls);
            if (!mid) return;
            jstring jGid = e->NewStringUTF(group_id.c_str());
            jstring jSender = e->NewStringUTF(sender.c_str());
            jstring jPreview = e->NewStringUTF(preview.c_str());
            e->CallVoidMethod(evt_cb, mid, jGid, (jlong)latest_msg_id, jSender, jPreview);
            e->DeleteLocalRef(jGid); e->DeleteLocalRef(jSender); e->DeleteLocalRef(jPreview);
        }

        void OnNewEvent(const std::string& group_id, int64_t latest_event_id,
                        const std::string& event_type, const std::string& summary) override {
            if (!evt_cb) return;
            JNIEnv* e = AttachCurrentThread();
            if (!e) return;
            jclass cls = e->GetObjectClass(evt_cb);
            jmethodID mid = e->GetMethodID(cls, "onNewEvent",
                "(Ljava/lang/String;JLjava/lang/String;Ljava/lang/String;)V");
            e->DeleteLocalRef(cls);
            if (!mid) return;
            jstring jGid = e->NewStringUTF(group_id.c_str());
            jstring jType = e->NewStringUTF(event_type.c_str());
            jstring jSummary = e->NewStringUTF(summary.c_str());
            e->CallVoidMethod(evt_cb, mid, jGid, (jlong)latest_event_id, jType, jSummary);
            e->DeleteLocalRef(jGid); e->DeleteLocalRef(jType); e->DeleteLocalRef(jSummary);
        }

        void OnGroupInvite(const std::string& group_id, const std::string& group_address,
                           const std::string& invited_by) override {
            if (!evt_cb) return;
            JNIEnv* e = AttachCurrentThread();
            if (!e) return;
            jclass cls = e->GetObjectClass(evt_cb);
            jmethodID mid = e->GetMethodID(cls, "onGroupInvite",
                "(Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;)V");
            e->DeleteLocalRef(cls);
            if (!mid) return;
            jstring jGid = e->NewStringUTF(group_id.c_str());
            jstring jAddr = e->NewStringUTF(group_address.c_str());
            jstring jBy = e->NewStringUTF(invited_by.c_str());
            e->CallVoidMethod(evt_cb, mid, jGid, jAddr, jBy);
            e->DeleteLocalRef(jGid); e->DeleteLocalRef(jAddr); e->DeleteLocalRef(jBy);
        }

        void OnJoinApproved(const std::string& group_id, const std::string& group_address) override {
            if (!evt_cb) return;
            JNIEnv* e = AttachCurrentThread();
            if (!e) return;
            jclass cls = e->GetObjectClass(evt_cb);
            jmethodID mid = e->GetMethodID(cls, "onJoinApproved",
                "(Ljava/lang/String;Ljava/lang/String;)V");
            e->DeleteLocalRef(cls);
            if (!mid) return;
            jstring jGid = e->NewStringUTF(group_id.c_str());
            jstring jAddr = e->NewStringUTF(group_address.c_str());
            e->CallVoidMethod(evt_cb, mid, jGid, jAddr);
            e->DeleteLocalRef(jGid); e->DeleteLocalRef(jAddr);
        }

        void OnJoinRejected(const std::string& group_id, const std::string& reason) override {
            if (!evt_cb) return;
            JNIEnv* e = AttachCurrentThread();
            if (!e) return;
            jclass cls = e->GetObjectClass(evt_cb);
            jmethodID mid = e->GetMethodID(cls, "onJoinRejected",
                "(Ljava/lang/String;Ljava/lang/String;)V");
            e->DeleteLocalRef(cls);
            if (!mid) return;
            jstring jGid = e->NewStringUTF(group_id.c_str());
            jstring jReason = e->NewStringUTF(reason.c_str());
            e->CallVoidMethod(evt_cb, mid, jGid, jReason);
            e->DeleteLocalRef(jGid); e->DeleteLocalRef(jReason);
        }

        void OnJoinRequestReceived(const std::string& group_id, const std::string& agent_id,
                                   const std::string& message) override {
            if (!evt_cb) return;
            JNIEnv* e = AttachCurrentThread();
            if (!e) return;
            jclass cls = e->GetObjectClass(evt_cb);
            jmethodID mid = e->GetMethodID(cls, "onJoinRequestReceived",
                "(Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;)V");
            e->DeleteLocalRef(cls);
            if (!mid) return;
            jstring jGid = e->NewStringUTF(group_id.c_str());
            jstring jAgent = e->NewStringUTF(agent_id.c_str());
            jstring jMsg = e->NewStringUTF(message.c_str());
            e->CallVoidMethod(evt_cb, mid, jGid, jAgent, jMsg);
            e->DeleteLocalRef(jGid); e->DeleteLocalRef(jAgent); e->DeleteLocalRef(jMsg);
        }

        void OnGroupMessageBatch(const std::string& group_id, const agentcp::group::GroupMessageBatch& batch) override {
            if (!msg_cb) return;
            JNIEnv* e = AttachCurrentThread();
            if (!e) return;
            jclass cls = e->GetObjectClass(msg_cb);
            jmethodID mid = e->GetMethodID(cls, "onGroupMessageBatch",
                "(Ljava/lang/String;Ljava/lang/String;)V");
            e->DeleteLocalRef(cls);
            if (!mid) return;
            // Serialize batch to JSON for Java layer
            std::string jsonStr;
            try {
                json j;
                j["start_msg_id"] = batch.start_msg_id;
                j["latest_msg_id"] = batch.latest_msg_id;
                j["count"] = batch.count;
                json msgs = json::array();
                for (const auto& m : batch.messages) {
                    json mj;
                    mj["msg_id"] = m.msg_id;
                    mj["sender"] = m.sender;
                    mj["content"] = m.content;
                    mj["content_type"] = m.content_type;
                    mj["timestamp"] = m.timestamp;
                    if (!m.metadata_json.empty()) {
                        try { mj["metadata"] = json::parse(m.metadata_json); } catch (...) {}
                    }
                    msgs.push_back(mj);
                }
                j["messages"] = msgs;
                jsonStr = j.dump();
            } catch (const std::exception& ex) {
                JNI_LOGW("OnGroupMessageBatch JSON serialize error: %s", ex.what());
                return;
            }
            jstring jGid = e->NewStringUTF(group_id.c_str());
            jstring jBatchJson = e->NewStringUTF(jsonStr.c_str());
            if (jGid && jBatchJson) {
                e->CallVoidMethod(msg_cb, mid, jGid, jBatchJson);
            }
            if (jGid) e->DeleteLocalRef(jGid);
            if (jBatchJson) e->DeleteLocalRef(jBatchJson);
        }

        void OnGroupEvent(const std::string& group_id, const agentcp::group::GroupEvent& evt) override {
            if (!evt_cb) return;
            JNIEnv* e = AttachCurrentThread();
            if (!e) return;
            jclass cls = e->GetObjectClass(evt_cb);
            jmethodID mid = e->GetMethodID(cls, "onGroupEvent",
                "(Ljava/lang/String;Ljava/lang/String;)V");
            e->DeleteLocalRef(cls);
            if (!mid) return;
            // Serialize event to JSON for Java layer
            json j;
            j["event_id"] = evt.event_id;
            j["event_type"] = evt.event_type;
            j["actor"] = evt.actor;
            j["timestamp"] = evt.timestamp;
            j["target"] = evt.target;
            if (!evt.data_json.empty()) {
                try { j["data"] = json::parse(evt.data_json); } catch (...) {}
            }
            jstring jGid = e->NewStringUTF(group_id.c_str());
            jstring jEvtJson = e->NewStringUTF(j.dump().c_str());
            e->CallVoidMethod(evt_cb, mid, jGid, jEvtJson);
            e->DeleteLocalRef(jGid); e->DeleteLocalRef(jEvtJson);
        }
    };

    // Store the handler so it lives as long as needed
    // We use a static to ensure only one handler exists at a time
    static std::unique_ptr<JniGroupEventHandler> s_group_handler;
    s_group_handler = std::make_unique<JniGroupEventHandler>(g_msg_cb, g_evt_cb);
    aid->SetGroupEventHandler(s_group_handler.get());
}

// --- Group Operations (blocking, call from background thread) ---

extern "C" JNIEXPORT void JNICALL
Java_com_agentcp_AgentID_nativeGroupRegisterOnline(JNIEnv* env, jobject /*thiz*/, jlong handle) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return;
    try {
        aid->GroupOps()->RegisterOnline(aid->GetGroupTargetAid());
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
    }
}

extern "C" JNIEXPORT void JNICALL
Java_com_agentcp_AgentID_nativeGroupUnregisterOnline(JNIEnv* env, jobject /*thiz*/, jlong handle) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return;
    try {
        aid->GroupOps()->UnregisterOnline(aid->GetGroupTargetAid());
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
    }
}

extern "C" JNIEXPORT void JNICALL
Java_com_agentcp_AgentID_nativeGroupHeartbeat(JNIEnv* env, jobject /*thiz*/, jlong handle) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return;
    try {
        aid->GroupOps()->Heartbeat(aid->GetGroupTargetAid());
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
    }
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_agentcp_AgentID_nativeGroupSendMessage(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                                 jstring group_id, jstring content,
                                                 jstring content_type, jstring metadata_json) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return env->NewStringUTF("{}");
    try {
        std::string gid = JStringToString(env, group_id);
        std::string ct = JStringToString(env, content);
        std::string ctype = JStringToString(env, content_type);
        std::string meta = JStringToString(env, metadata_json);
        auto resp = aid->GroupOps()->SendGroupMessage(
            aid->GetGroupTargetAid(), gid, ct, ctype, meta);
        json j;
        j["msg_id"] = resp.msg_id;
        j["timestamp"] = resp.timestamp;
        return env->NewStringUTF(j.dump().c_str());
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
        return nullptr;
    }
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_agentcp_AgentID_nativeGroupPullMessages(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                                  jstring group_id, jlong after_msg_id, jint limit) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return env->NewStringUTF("{}");
    try {
        std::string gid = JStringToString(env, group_id);
        auto resp = aid->GroupOps()->PullMessages(
            aid->GetGroupTargetAid(), gid, after_msg_id, limit);
        json j;
        j["has_more"] = resp.has_more;
        j["latest_msg_id"] = resp.latest_msg_id;
        json msgs = json::array();
        for (auto& m : resp.messages) {
            json mj;
            mj["msg_id"] = m.msg_id;
            mj["sender"] = m.sender;
            mj["content"] = m.content;
            mj["content_type"] = m.content_type;
            mj["timestamp"] = m.timestamp;
            if (!m.metadata_json.empty()) {
                try { mj["metadata"] = json::parse(m.metadata_json); } catch (...) {}
            }
            msgs.push_back(mj);
        }
        j["messages"] = msgs;
        return env->NewStringUTF(j.dump().c_str());
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
        return nullptr;
    }
}

extern "C" JNIEXPORT void JNICALL
Java_com_agentcp_AgentID_nativeGroupAckMessages(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                                 jstring group_id, jlong msg_id) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return;
    try {
        std::string gid = JStringToString(env, group_id);
        aid->GroupOps()->AckMessages(aid->GetGroupTargetAid(), gid, msg_id);
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
    }
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_agentcp_AgentID_nativeGroupGetInfo(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                             jstring group_id) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return env->NewStringUTF("{}");
    try {
        std::string gid = JStringToString(env, group_id);
        auto info = aid->GroupOps()->GetGroupInfo(aid->GetGroupTargetAid(), gid);
        json j;
        j["group_id"] = info.group_id;
        j["name"] = info.name;
        j["creator"] = info.creator;
        j["visibility"] = info.visibility;
        j["member_count"] = info.member_count;
        j["created_at"] = info.created_at;
        j["alias"] = info.alias;
        j["subject"] = info.subject;
        j["status"] = info.status;
        j["tags"] = info.tags;
        j["master"] = info.master;
        return env->NewStringUTF(j.dump().c_str());
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
        return nullptr;
    }
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_agentcp_AgentID_nativeGroupListMyGroups(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                                  jint status) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return env->NewStringUTF("{}");
    try {
        auto resp = aid->GroupOps()->ListMyGroups(aid->GetGroupTargetAid(), status);
        json j;
        j["total"] = resp.total;
        json groups = json::array();
        for (auto& g : resp.groups) {
            json gj;
            gj["group_id"] = g.group_id;
            gj["group_url"] = g.group_url;
            gj["group_server"] = g.group_server;
            gj["session_id"] = g.session_id;
            gj["role"] = g.role;
            gj["status"] = g.status;
            gj["created_at"] = g.created_at;
            gj["updated_at"] = g.updated_at;
            groups.push_back(gj);
        }
        j["groups"] = groups;
        return env->NewStringUTF(j.dump().c_str());
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
        return nullptr;
    }
}

extern "C" JNIEXPORT void JNICALL
Java_com_agentcp_AgentID_nativeGroupUnregisterMembership(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                                          jstring group_id) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return;
    try {
        aid->GroupOps()->UnregisterMembership(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id)
        );
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
    }
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_agentcp_AgentID_nativeGroupCreateGroup(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                                 jstring name, jstring alias, jstring subject,
                                                 jstring visibility, jstring description,
                                                 jobjectArray tags) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return env->NewStringUTF("{}");
    try {
        std::vector<std::string> tags_vec;
        if (tags != nullptr) {
            jsize len = env->GetArrayLength(tags);
            for (jsize i = 0; i < len; ++i) {
                auto elem = static_cast<jstring>(env->GetObjectArrayElement(tags, i));
                tags_vec.push_back(JStringToString(env, elem));
                env->DeleteLocalRef(elem);
            }
        }

        auto resp = aid->GroupOps()->CreateGroup(
            aid->GetGroupTargetAid(),
            JStringToString(env, name),
            JStringToString(env, alias),
            JStringToString(env, subject),
            JStringToString(env, visibility),
            JStringToString(env, description),
            tags_vec
        );
        json j;
        j["group_id"] = resp.group_id;
        j["group_url"] = resp.group_url;
        return env->NewStringUTF(j.dump().c_str());
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
        return nullptr;
    }
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_agentcp_AgentID_nativeGroupJoinByUrl(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                               jstring group_url, jstring invite_code, jstring message) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid()) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, "Agent not valid");
        return nullptr;
    }
    if (!aid->GroupOps()) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, "Group client not initialized. Call initGroupClient first.");
        return nullptr;
    }
    try {
        auto resp = aid->GroupOps()->JoinByUrl(
            JStringToString(env, group_url),
            JStringToString(env, invite_code),
            JStringToString(env, message)
        );
        return env->NewStringUTF(resp.request_id.c_str());
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
        return nullptr;
    }
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_agentcp_AgentID_nativeGroupRequestJoin(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                                 jstring group_id, jstring message) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return env->NewStringUTF("");
    try {
        auto resp = aid->GroupOps()->RequestJoin(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id),
            JStringToString(env, message)
        );
        return env->NewStringUTF(resp.request_id.c_str());
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
        return nullptr;
    }
}

extern "C" JNIEXPORT void JNICALL
Java_com_agentcp_AgentID_nativeGroupUseInviteCode(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                                   jstring group_id, jstring code) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return;
    try {
        aid->GroupOps()->UseInviteCode(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id),
            JStringToString(env, code)
        );
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
    }
}

extern "C" JNIEXPORT void JNICALL
Java_com_agentcp_AgentID_nativeGroupReviewJoinRequest(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                                       jstring group_id, jstring agent_id,
                                                       jstring action, jstring reason) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return;
    try {
        aid->GroupOps()->ReviewJoinRequest(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id),
            JStringToString(env, agent_id),
            JStringToString(env, action),
            JStringToString(env, reason)
        );
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
    }
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_agentcp_AgentID_nativeGroupGetPendingRequests(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                                        jstring group_id) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return env->NewStringUTF("{}");
    try {
        auto resp = aid->GroupOps()->GetPendingRequests(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id)
        );
        json j;
        try {
            j["requests"] = json::parse(resp.requests_json);
        } catch (...) {
            j["requests"] = json::array();
        }
        return env->NewStringUTF(j.dump().c_str());
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
        return nullptr;
    }
}

extern "C" JNIEXPORT void JNICALL
Java_com_agentcp_AgentID_nativeGroupLeaveGroup(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                                jstring group_id) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return;
    try {
        aid->GroupOps()->LeaveGroup(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id)
        );
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
    }
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_agentcp_AgentID_nativeGroupGetMembers(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                                jstring group_id) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return env->NewStringUTF("{}");
    try {
        auto resp = aid->GroupOps()->GetMembers(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id)
        );
        json j;
        try {
            j["members"] = json::parse(resp.members_json);
        } catch (...) {
            j["members"] = json::array();
        }
        return env->NewStringUTF(j.dump().c_str());
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
        return nullptr;
    }
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_agentcp_AgentID_nativeGroupCreateInviteCode(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                                      jstring group_id, jstring label,
                                                      jint max_uses, jlong expires_at) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return env->NewStringUTF("{}");
    try {
        auto resp = aid->GroupOps()->CreateInviteCode(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id),
            JStringToString(env, label),
            static_cast<int>(max_uses),
            static_cast<int64_t>(expires_at)
        );
        json j;
        j["code"] = resp.code;
        j["group_id"] = resp.group_id;
        j["created_by"] = resp.created_by;
        j["created_at"] = resp.created_at;
        j["label"] = resp.label;
        j["max_uses"] = resp.max_uses;
        j["expires_at"] = resp.expires_at;
        return env->NewStringUTF(j.dump().c_str());
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
        return nullptr;
    }
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_agentcp_AgentID_nativeGroupListInviteCodes(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                                     jstring group_id) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return env->NewStringUTF("{}");
    try {
        auto resp = aid->GroupOps()->ListInviteCodes(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id)
        );
        json j;
        try {
            j["codes"] = json::parse(resp.codes_json);
        } catch (...) {
            j["codes"] = json::array();
        }
        return env->NewStringUTF(j.dump().c_str());
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
        return nullptr;
    }
}

extern "C" JNIEXPORT void JNICALL
Java_com_agentcp_AgentID_nativeGroupRevokeInviteCode(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                                      jstring group_id, jstring code) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return;
    try {
        aid->GroupOps()->RevokeInviteCode(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id),
            JStringToString(env, code)
        );
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
    }
}

extern "C" JNIEXPORT void JNICALL
Java_com_agentcp_AgentID_nativeGroupAddMember(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                               jstring group_id, jstring agent_id, jstring role) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return;
    try {
        aid->GroupOps()->AddMember(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id),
            JStringToString(env, agent_id),
            JStringToString(env, role)
        );
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
    }
}

extern "C" JNIEXPORT void JNICALL
Java_com_agentcp_AgentID_nativeGroupRemoveMember(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                                  jstring group_id, jstring agent_id) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return;
    try {
        aid->GroupOps()->RemoveMember(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id),
            JStringToString(env, agent_id)
        );
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
    }
}

extern "C" JNIEXPORT void JNICALL
Java_com_agentcp_AgentID_nativeGroupChangeMemberRole(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                                      jstring group_id, jstring agent_id, jstring new_role) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return;
    try {
        aid->GroupOps()->ChangeMemberRole(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id),
            JStringToString(env, agent_id),
            JStringToString(env, new_role)
        );
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
    }
}

extern "C" JNIEXPORT void JNICALL
Java_com_agentcp_AgentID_nativeGroupBanAgent(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                              jstring group_id, jstring agent_id,
                                              jstring reason, jlong expires_at) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return;
    try {
        aid->GroupOps()->BanAgent(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id),
            JStringToString(env, agent_id),
            JStringToString(env, reason),
            static_cast<int64_t>(expires_at)
        );
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
    }
}

extern "C" JNIEXPORT void JNICALL
Java_com_agentcp_AgentID_nativeGroupUnbanAgent(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                                jstring group_id, jstring agent_id) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return;
    try {
        aid->GroupOps()->UnbanAgent(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id),
            JStringToString(env, agent_id)
        );
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
    }
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_agentcp_AgentID_nativeGroupGetBanlist(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                                jstring group_id) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return env->NewStringUTF("{}");
    try {
        auto resp = aid->GroupOps()->GetBanlist(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id)
        );
        json j;
        try {
            j["banned"] = json::parse(resp.banned_json);
        } catch (...) {
            j["banned"] = json::array();
        }
        return env->NewStringUTF(j.dump().c_str());
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
        return nullptr;
    }
}

extern "C" JNIEXPORT void JNICALL
Java_com_agentcp_AgentID_nativeGroupDissolveGroup(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                                   jstring group_id) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return;
    try {
        aid->GroupOps()->DissolveGroup(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id)
        );
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
    }
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_agentcp_AgentID_nativeGroupPullEvents(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                                jstring group_id, jlong after_event_id, jint limit) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return env->NewStringUTF("{}");
    try {
        auto resp = aid->GroupOps()->PullEvents(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id),
            static_cast<int64_t>(after_event_id),
            static_cast<int>(limit)
        );
        json j;
        j["has_more"] = resp.has_more;
        j["latest_event_id"] = resp.latest_event_id;
        json events = json::array();
        for (const auto& e : resp.events) {
            json ej;
            ej["event_id"] = e.event_id;
            ej["event_type"] = e.event_type;
            ej["actor"] = e.actor;
            ej["timestamp"] = e.timestamp;
            ej["target"] = e.target;
            if (!e.data_json.empty()) {
                try { ej["data"] = json::parse(e.data_json); } catch (...) {}
            }
            events.push_back(ej);
        }
        j["events"] = events;
        return env->NewStringUTF(j.dump().c_str());
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
        return nullptr;
    }
}

extern "C" JNIEXPORT void JNICALL
Java_com_agentcp_AgentID_nativeGroupAckEvents(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                               jstring group_id, jlong event_id) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return;
    try {
        aid->GroupOps()->AckEvents(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id),
            static_cast<int64_t>(event_id)
        );
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
    }
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_agentcp_AgentID_nativeGroupGetCursor(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                               jstring group_id) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return env->NewStringUTF("{}");
    try {
        auto cursor = aid->GroupOps()->GetCursor(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id)
        );
        json j;
        j["msg_cursor"] = {
            {"start_msg_id", cursor.msg_cursor.start_msg_id},
            {"current_msg_id", cursor.msg_cursor.current_msg_id},
            {"latest_msg_id", cursor.msg_cursor.latest_msg_id},
            {"unread_count", cursor.msg_cursor.unread_count}
        };
        j["event_cursor"] = {
            {"start_event_id", cursor.event_cursor.start_event_id},
            {"current_event_id", cursor.event_cursor.current_event_id},
            {"latest_event_id", cursor.event_cursor.latest_event_id},
            {"unread_count", cursor.event_cursor.unread_count}
        };
        return env->NewStringUTF(j.dump().c_str());
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
        return nullptr;
    }
}

extern "C" JNIEXPORT void JNICALL
Java_com_agentcp_AgentID_nativeGroupSync(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                          jstring group_id, jobject sync_handler) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps() || sync_handler == nullptr) {
        JNI_LOGW("nativeGroupSync: skipped (aid/groupOps/handler invalid)");
        return;
    }

    const std::string gid = JStringToString(env, group_id);
    if (gid.empty()) {
        JNI_LOGW("nativeGroupSync: skipped due to empty groupId");
        return;
    }

    jobject g_handler = env->NewGlobalRef(sync_handler);
    if (g_handler == nullptr) {
        JNI_LOGE("nativeGroupSync: failed to create global ref for handler");
        return;
    }

    class JniSyncHandler : public agentcp::group::SyncHandler {
    public:
        jobject handler;
        explicit JniSyncHandler(jobject h) : handler(h) {}
        ~JniSyncHandler() override {
            JNIEnv* e = AttachCurrentThread();
            if (e && handler) {
                e->DeleteGlobalRef(handler);
            }
        }

        void OnMessages(const std::string& group_id, const std::vector<agentcp::group::GroupMessage>& messages) override {
            JNIEnv* e = AttachCurrentThread();
            if (!e || !handler) return;

            jclass cls = e->GetObjectClass(handler);
            if (cls == nullptr) {
                JNI_LOGE("nativeGroupSync.OnMessages: failed to get handler class");
                LogAndClearJavaException(e, "nativeGroupSync.OnMessages.GetObjectClass");
                return;
            }
            jmethodID mid = e->GetMethodID(cls, "onMessages", "(Ljava/lang/String;Lorg/json/JSONArray;)V");
            if (!mid) {
                JNI_LOGE("nativeGroupSync.OnMessages: missing callback method onMessages(String, JSONArray)");
                e->DeleteLocalRef(cls);
                LogAndClearJavaException(e, "nativeGroupSync.OnMessages.GetMethodID(onMessages)");
                return;
            }

            json arr = json::array();
            for (const auto& m : messages) {
                json item;
                item["msg_id"] = m.msg_id;
                item["sender"] = m.sender;
                item["content"] = m.content;
                item["content_type"] = m.content_type;
                item["timestamp"] = m.timestamp;
                if (!m.metadata_json.empty()) {
                    try { item["metadata"] = json::parse(m.metadata_json); } catch (...) {}
                }
                arr.push_back(item);
            }

            jclass jsonArrayCls = e->FindClass("org/json/JSONArray");
            if (jsonArrayCls == nullptr) {
                JNI_LOGE("nativeGroupSync.OnMessages: failed to find org/json/JSONArray");
                e->DeleteLocalRef(cls);
                LogAndClearJavaException(e, "nativeGroupSync.OnMessages.FindClass");
                return;
            }
            jmethodID ctor = e->GetMethodID(jsonArrayCls, "<init>", "(Ljava/lang/String;)V");
            if (ctor == nullptr) {
                JNI_LOGE("nativeGroupSync.OnMessages: failed to resolve JSONArray ctor");
                e->DeleteLocalRef(jsonArrayCls);
                e->DeleteLocalRef(cls);
                LogAndClearJavaException(e, "nativeGroupSync.OnMessages.GetMethodID");
                return;
            }
            jstring jArrText = e->NewStringUTF(arr.dump().c_str());
            if (jArrText == nullptr) {
                JNI_LOGE("nativeGroupSync.OnMessages: failed to allocate message json string");
                e->DeleteLocalRef(jsonArrayCls);
                e->DeleteLocalRef(cls);
                LogAndClearJavaException(e, "nativeGroupSync.OnMessages.NewStringUTF");
                return;
            }
            jobject jArr = e->NewObject(jsonArrayCls, ctor, jArrText);
            if (jArr == nullptr) {
                JNI_LOGE("nativeGroupSync.OnMessages: failed to construct JSONArray");
                e->DeleteLocalRef(jArrText);
                e->DeleteLocalRef(jsonArrayCls);
                e->DeleteLocalRef(cls);
                LogAndClearJavaException(e, "nativeGroupSync.OnMessages.NewObject");
                return;
            }
            jstring jGid = e->NewStringUTF(group_id.c_str());
            if (jGid == nullptr) {
                JNI_LOGE("nativeGroupSync.OnMessages: failed to allocate groupId string");
                e->DeleteLocalRef(jArr);
                e->DeleteLocalRef(jArrText);
                e->DeleteLocalRef(jsonArrayCls);
                e->DeleteLocalRef(cls);
                LogAndClearJavaException(e, "nativeGroupSync.OnMessages.NewStringUTF(groupId)");
                return;
            }
            e->CallVoidMethod(handler, mid, jGid, jArr);
            LogAndClearJavaException(e, "nativeGroupSync.OnMessages.CallVoidMethod");
            e->DeleteLocalRef(jGid);
            e->DeleteLocalRef(jArr);
            e->DeleteLocalRef(jArrText);
            e->DeleteLocalRef(jsonArrayCls);
            e->DeleteLocalRef(cls);
        }

        void OnEvents(const std::string& group_id, const std::vector<agentcp::group::GroupEvent>& events) override {
            JNIEnv* e = AttachCurrentThread();
            if (!e || !handler) return;

            jclass cls = e->GetObjectClass(handler);
            if (cls == nullptr) {
                JNI_LOGE("nativeGroupSync.OnEvents: failed to get handler class");
                LogAndClearJavaException(e, "nativeGroupSync.OnEvents.GetObjectClass");
                return;
            }
            jmethodID mid = e->GetMethodID(cls, "onEvents", "(Ljava/lang/String;Lorg/json/JSONArray;)V");
            if (!mid) {
                JNI_LOGE("nativeGroupSync.OnEvents: missing callback method onEvents(String, JSONArray)");
                e->DeleteLocalRef(cls);
                LogAndClearJavaException(e, "nativeGroupSync.OnEvents.GetMethodID(onEvents)");
                return;
            }

            json arr = json::array();
            for (const auto& evt : events) {
                json item;
                item["event_id"] = evt.event_id;
                item["event_type"] = evt.event_type;
                item["actor"] = evt.actor;
                item["timestamp"] = evt.timestamp;
                item["target"] = evt.target;
                if (!evt.data_json.empty()) {
                    try { item["data"] = json::parse(evt.data_json); } catch (...) {}
                }
                arr.push_back(item);
            }

            jclass jsonArrayCls = e->FindClass("org/json/JSONArray");
            if (jsonArrayCls == nullptr) {
                JNI_LOGE("nativeGroupSync.OnEvents: failed to find org/json/JSONArray");
                e->DeleteLocalRef(cls);
                LogAndClearJavaException(e, "nativeGroupSync.OnEvents.FindClass");
                return;
            }
            jmethodID ctor = e->GetMethodID(jsonArrayCls, "<init>", "(Ljava/lang/String;)V");
            if (ctor == nullptr) {
                JNI_LOGE("nativeGroupSync.OnEvents: failed to resolve JSONArray ctor");
                e->DeleteLocalRef(jsonArrayCls);
                e->DeleteLocalRef(cls);
                LogAndClearJavaException(e, "nativeGroupSync.OnEvents.GetMethodID");
                return;
            }
            jstring jArrText = e->NewStringUTF(arr.dump().c_str());
            if (jArrText == nullptr) {
                JNI_LOGE("nativeGroupSync.OnEvents: failed to allocate events json string");
                e->DeleteLocalRef(jsonArrayCls);
                e->DeleteLocalRef(cls);
                LogAndClearJavaException(e, "nativeGroupSync.OnEvents.NewStringUTF");
                return;
            }
            jobject jArr = e->NewObject(jsonArrayCls, ctor, jArrText);
            if (jArr == nullptr) {
                JNI_LOGE("nativeGroupSync.OnEvents: failed to construct JSONArray");
                e->DeleteLocalRef(jArrText);
                e->DeleteLocalRef(jsonArrayCls);
                e->DeleteLocalRef(cls);
                LogAndClearJavaException(e, "nativeGroupSync.OnEvents.NewObject");
                return;
            }
            jstring jGid = e->NewStringUTF(group_id.c_str());
            if (jGid == nullptr) {
                JNI_LOGE("nativeGroupSync.OnEvents: failed to allocate groupId string");
                e->DeleteLocalRef(jArr);
                e->DeleteLocalRef(jArrText);
                e->DeleteLocalRef(jsonArrayCls);
                e->DeleteLocalRef(cls);
                LogAndClearJavaException(e, "nativeGroupSync.OnEvents.NewStringUTF(groupId)");
                return;
            }
            e->CallVoidMethod(handler, mid, jGid, jArr);
            LogAndClearJavaException(e, "nativeGroupSync.OnEvents.CallVoidMethod");
            e->DeleteLocalRef(jGid);
            e->DeleteLocalRef(jArr);
            e->DeleteLocalRef(jArrText);
            e->DeleteLocalRef(jsonArrayCls);
            e->DeleteLocalRef(cls);
        }
    };

    try {
        JNI_LOG("nativeGroupSync: start group=%s", gid.c_str());
        JniSyncHandler h(g_handler);
        aid->GroupOps()->SyncGroup(aid->GetGroupTargetAid(), gid, &h);
        JNI_LOG("nativeGroupSync: completed group=%s", gid.c_str());
    } catch (const std::exception& e) {
        JNI_LOGE("nativeGroupSync: failed group=%s err=%s", gid.c_str(), e.what());
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
    } catch (...) {
        JNI_LOGE("nativeGroupSync: failed group=%s unknown exception", gid.c_str());
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, "nativeGroupSync: unknown exception");
    }
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_agentcp_AgentID_nativeGroupBatchReviewJoinRequests(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                                             jstring group_id, jobjectArray agent_ids,
                                                             jstring action, jstring reason) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return env->NewStringUTF("{}");
    try {
        std::vector<std::string> ids;
        if (agent_ids != nullptr) {
            jsize len = env->GetArrayLength(agent_ids);
            for (jsize i = 0; i < len; ++i) {
                auto elem = static_cast<jstring>(env->GetObjectArrayElement(agent_ids, i));
                ids.push_back(JStringToString(env, elem));
                env->DeleteLocalRef(elem);
            }
        }
        auto resp = aid->GroupOps()->BatchReviewJoinRequests(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id),
            ids,
            JStringToString(env, action),
            JStringToString(env, reason)
        );
        json j;
        j["processed"] = resp.processed;
        j["total"] = resp.total;
        return env->NewStringUTF(j.dump().c_str());
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
        return nullptr;
    }
}

extern "C" JNIEXPORT void JNICALL
Java_com_agentcp_AgentID_nativeGroupUpdateMeta(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                                jstring group_id, jstring params_json) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return;
    try {
        aid->GroupOps()->UpdateGroupMeta(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id),
            JStringToString(env, params_json)
        );
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
    }
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_agentcp_AgentID_nativeGroupGetAdmins(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                               jstring group_id) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return env->NewStringUTF("{}");
    try {
        auto resp = aid->GroupOps()->GetAdmins(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id)
        );
        json j;
        try {
            j["admins"] = json::parse(resp.admins_json);
        } catch (...) {
            j["admins"] = json::array();
        }
        return env->NewStringUTF(j.dump().c_str());
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
        return nullptr;
    }
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_agentcp_AgentID_nativeGroupGetRules(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                              jstring group_id) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return env->NewStringUTF("{}");
    try {
        auto resp = aid->GroupOps()->GetRules(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id)
        );
        json j;
        j["max_members"] = resp.max_members;
        j["max_message_size"] = resp.max_message_size;
        if (!resp.broadcast_policy_json.empty()) {
            try { j["broadcast_policy"] = json::parse(resp.broadcast_policy_json); } catch (...) {}
        }
        return env->NewStringUTF(j.dump().c_str());
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
        return nullptr;
    }
}

extern "C" JNIEXPORT void JNICALL
Java_com_agentcp_AgentID_nativeGroupUpdateRules(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                                 jstring group_id, jstring params_json) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return;
    try {
        aid->GroupOps()->UpdateRules(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id),
            JStringToString(env, params_json)
        );
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
    }
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_agentcp_AgentID_nativeGroupGetAnnouncement(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                                     jstring group_id) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return env->NewStringUTF("{}");
    try {
        auto resp = aid->GroupOps()->GetAnnouncement(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id)
        );
        json j;
        j["content"] = resp.content;
        j["updated_by"] = resp.updated_by;
        j["updated_at"] = resp.updated_at;
        return env->NewStringUTF(j.dump().c_str());
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
        return nullptr;
    }
}

extern "C" JNIEXPORT void JNICALL
Java_com_agentcp_AgentID_nativeGroupUpdateAnnouncement(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                                        jstring group_id, jstring content) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return;
    try {
        aid->GroupOps()->UpdateAnnouncement(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id),
            JStringToString(env, content)
        );
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
    }
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_agentcp_AgentID_nativeGroupGetJoinRequirements(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                                         jstring group_id) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return env->NewStringUTF("{}");
    try {
        auto resp = aid->GroupOps()->GetJoinRequirements(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id)
        );
        json j;
        j["mode"] = resp.mode;
        j["require_all"] = resp.require_all;
        return env->NewStringUTF(j.dump().c_str());
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
        return nullptr;
    }
}

extern "C" JNIEXPORT void JNICALL
Java_com_agentcp_AgentID_nativeGroupUpdateJoinRequirements(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                                            jstring group_id, jstring params_json) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return;
    try {
        aid->GroupOps()->UpdateJoinRequirements(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id),
            JStringToString(env, params_json)
        );
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
    }
}

extern "C" JNIEXPORT void JNICALL
Java_com_agentcp_AgentID_nativeGroupSuspend(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                             jstring group_id) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return;
    try {
        aid->GroupOps()->SuspendGroup(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id)
        );
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
    }
}

extern "C" JNIEXPORT void JNICALL
Java_com_agentcp_AgentID_nativeGroupResume(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                            jstring group_id) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return;
    try {
        aid->GroupOps()->ResumeGroup(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id)
        );
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
    }
}

extern "C" JNIEXPORT void JNICALL
Java_com_agentcp_AgentID_nativeGroupTransferMaster(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                                    jstring group_id, jstring new_master_aid, jstring reason) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return;
    try {
        aid->GroupOps()->TransferMaster(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id),
            JStringToString(env, new_master_aid),
            JStringToString(env, reason)
        );
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
    }
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_agentcp_AgentID_nativeGroupGetMaster(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                               jstring group_id) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return env->NewStringUTF("{}");
    try {
        auto resp = aid->GroupOps()->GetMaster(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id)
        );
        json j;
        j["master"] = resp.master;
        j["master_transferred_at"] = resp.master_transferred_at;
        j["transfer_reason"] = resp.transfer_reason;
        return env->NewStringUTF(j.dump().c_str());
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
        return nullptr;
    }
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_agentcp_AgentID_nativeGroupAcquireBroadcastLock(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                                          jstring group_id) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return env->NewStringUTF("{}");
    try {
        auto resp = aid->GroupOps()->AcquireBroadcastLock(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id)
        );
        json j;
        j["acquired"] = resp.acquired;
        j["expires_at"] = resp.expires_at;
        j["holder"] = resp.holder;
        return env->NewStringUTF(j.dump().c_str());
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
        return nullptr;
    }
}

extern "C" JNIEXPORT void JNICALL
Java_com_agentcp_AgentID_nativeGroupReleaseBroadcastLock(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                                          jstring group_id) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return;
    try {
        aid->GroupOps()->ReleaseBroadcastLock(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id)
        );
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
    }
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_agentcp_AgentID_nativeGroupCheckBroadcastPermission(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                                              jstring group_id) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return env->NewStringUTF("{}");
    try {
        auto resp = aid->GroupOps()->CheckBroadcastPermission(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id)
        );
        json j;
        j["allowed"] = resp.allowed;
        j["reason"] = resp.reason;
        return env->NewStringUTF(j.dump().c_str());
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
        return nullptr;
    }
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_agentcp_AgentID_nativeGroupGetSyncStatus(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                                   jstring group_id) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return env->NewStringUTF("{}");
    try {
        auto resp = aid->GroupOps()->GetSyncStatus(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id)
        );
        json j;
        j["msg_cursor"] = {
            {"start_msg_id", resp.msg_cursor.start_msg_id},
            {"current_msg_id", resp.msg_cursor.current_msg_id},
            {"latest_msg_id", resp.msg_cursor.latest_msg_id},
            {"unread_count", resp.msg_cursor.unread_count}
        };
        j["event_cursor"] = {
            {"start_event_id", resp.event_cursor.start_event_id},
            {"current_event_id", resp.event_cursor.current_event_id},
            {"latest_event_id", resp.event_cursor.latest_event_id},
            {"unread_count", resp.event_cursor.unread_count}
        };
        j["sync_percentage"] = resp.sync_percentage;
        return env->NewStringUTF(j.dump().c_str());
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
        return nullptr;
    }
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_agentcp_AgentID_nativeGroupGetSyncLog(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                                jstring group_id, jstring start_date) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return env->NewStringUTF("{}");
    try {
        auto resp = aid->GroupOps()->GetSyncLog(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id),
            JStringToString(env, start_date)
        );
        json j;
        try {
            j["entries"] = json::parse(resp.entries_json);
        } catch (...) {
            j["entries"] = json::array();
        }
        return env->NewStringUTF(j.dump().c_str());
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
        return nullptr;
    }
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_agentcp_AgentID_nativeGroupGetChecksum(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                                 jstring group_id, jstring file) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return env->NewStringUTF("{}");
    try {
        auto resp = aid->GroupOps()->GetChecksum(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id),
            JStringToString(env, file)
        );
        json j;
        j["file"] = resp.file;
        j["checksum"] = resp.checksum;
        return env->NewStringUTF(j.dump().c_str());
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
        return nullptr;
    }
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_agentcp_AgentID_nativeGroupGetMessageChecksum(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                                        jstring group_id, jstring date) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return env->NewStringUTF("{}");
    try {
        auto resp = aid->GroupOps()->GetMessageChecksum(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id),
            JStringToString(env, date)
        );
        json j;
        j["file"] = resp.file;
        j["checksum"] = resp.checksum;
        return env->NewStringUTF(j.dump().c_str());
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
        return nullptr;
    }
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_agentcp_AgentID_nativeGroupGetPublicInfo(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                                   jstring group_id) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return env->NewStringUTF("{}");
    try {
        auto info = aid->GroupOps()->GetPublicInfo(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id)
        );
        json j;
        j["group_id"] = info.group_id;
        j["name"] = info.name;
        j["creator"] = info.creator;
        j["visibility"] = info.visibility;
        j["member_count"] = info.member_count;
        j["created_at"] = info.created_at;
        j["alias"] = info.alias;
        j["subject"] = info.subject;
        j["tags"] = info.tags;
        j["join_mode"] = info.join_mode;
        return env->NewStringUTF(j.dump().c_str());
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
        return nullptr;
    }
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_agentcp_AgentID_nativeGroupSearchGroups(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                                  jstring keyword, jobjectArray tags,
                                                  jint limit, jint offset) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return env->NewStringUTF("{}");
    try {
        std::vector<std::string> tags_vec;
        if (tags != nullptr) {
            jsize len = env->GetArrayLength(tags);
            for (jsize i = 0; i < len; ++i) {
                auto elem = static_cast<jstring>(env->GetObjectArrayElement(tags, i));
                tags_vec.push_back(JStringToString(env, elem));
                env->DeleteLocalRef(elem);
            }
        }
        auto resp = aid->GroupOps()->SearchGroups(
            aid->GetGroupTargetAid(),
            JStringToString(env, keyword),
            tags_vec,
            static_cast<int>(limit),
            static_cast<int>(offset)
        );
        json j;
        j["total"] = resp.total;
        json groups = json::array();
        for (const auto& g : resp.groups) {
            json gj;
            gj["group_id"] = g.group_id;
            gj["name"] = g.name;
            gj["creator"] = g.creator;
            gj["visibility"] = g.visibility;
            gj["member_count"] = g.member_count;
            gj["created_at"] = g.created_at;
            gj["alias"] = g.alias;
            gj["subject"] = g.subject;
            gj["tags"] = g.tags;
            gj["join_mode"] = g.join_mode;
            groups.push_back(gj);
        }
        j["groups"] = groups;
        return env->NewStringUTF(j.dump().c_str());
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
        return nullptr;
    }
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_agentcp_AgentID_nativeGroupGenerateDigest(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                                    jstring group_id, jstring date, jstring period) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return env->NewStringUTF("{}");
    try {
        auto resp = aid->GroupOps()->GenerateDigest(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id),
            JStringToString(env, date),
            JStringToString(env, period)
        );
        json j;
        j["date"] = resp.date;
        j["period"] = resp.period;
        j["message_count"] = resp.message_count;
        j["unique_senders"] = resp.unique_senders;
        j["data_size"] = resp.data_size;
        j["generated_at"] = resp.generated_at;
        try {
            j["top_contributors"] = json::parse(resp.top_contributors_json);
        } catch (...) {
            j["top_contributors"] = json::array();
        }
        return env->NewStringUTF(j.dump().c_str());
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
        return nullptr;
    }
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_agentcp_AgentID_nativeGroupGetDigest(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                               jstring group_id, jstring date, jstring period) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return env->NewStringUTF("{}");
    try {
        auto resp = aid->GroupOps()->GetDigest(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id),
            JStringToString(env, date),
            JStringToString(env, period)
        );
        json j;
        j["date"] = resp.date;
        j["period"] = resp.period;
        j["message_count"] = resp.message_count;
        j["unique_senders"] = resp.unique_senders;
        j["data_size"] = resp.data_size;
        j["generated_at"] = resp.generated_at;
        try {
            j["top_contributors"] = json::parse(resp.top_contributors_json);
        } catch (...) {
            j["top_contributors"] = json::array();
        }
        return env->NewStringUTF(j.dump().c_str());
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
        return nullptr;
    }
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_agentcp_AgentID_nativeGroupGetFile(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                             jstring group_id, jstring file, jlong offset) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return env->NewStringUTF("{}");
    try {
        auto resp = aid->GroupOps()->GetFile(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id),
            JStringToString(env, file),
            static_cast<int64_t>(offset)
        );
        json j;
        j["data"] = resp.data;
        j["total_size"] = resp.total_size;
        j["offset"] = resp.offset;
        return env->NewStringUTF(j.dump().c_str());
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
        return nullptr;
    }
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_agentcp_AgentID_nativeGroupGetSummary(JNIEnv* env, jobject /*thiz*/, jlong handle,
                                                jstring group_id, jstring date) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return env->NewStringUTF("{}");
    try {
        auto resp = aid->GroupOps()->GetSummary(
            aid->GetGroupTargetAid(),
            JStringToString(env, group_id),
            JStringToString(env, date)
        );
        json j;
        j["date"] = resp.date;
        j["message_count"] = resp.message_count;
        j["senders"] = resp.senders;
        j["data_size"] = resp.data_size;
        return env->NewStringUTF(j.dump().c_str());
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
        return nullptr;
    }
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_agentcp_AgentID_nativeGroupGetMetrics(JNIEnv* env, jobject /*thiz*/, jlong handle) {
    auto* aid = reinterpret_cast<agentcp::AgentID*>(handle);
    if (!aid || !aid->IsValid() || !aid->GroupOps()) return env->NewStringUTF("{}");
    try {
        auto resp = aid->GroupOps()->GetMetrics(aid->GetGroupTargetAid());
        json j;
        j["goroutines"] = resp.goroutines;
        j["alloc_mb"] = resp.alloc_mb;
        j["sys_mb"] = resp.sys_mb;
        j["gc_cycles"] = resp.gc_cycles;
        return env->NewStringUTF(j.dump().c_str());
    } catch (const std::exception& e) {
        jclass cls = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(cls, e.what());
        return nullptr;
    }
}
