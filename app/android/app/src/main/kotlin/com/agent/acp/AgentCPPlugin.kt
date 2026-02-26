package com.agent.acp

import android.content.Context
import android.net.Uri
import android.util.Log
import com.agentcp.AgentCP
import com.agentcp.AgentCPException
import com.agentcp.AgentID
import com.agentcp.AgentState
import com.agentcp.InviteCallback
import com.agentcp.LogLevel
import com.agentcp.MessageCallback
import com.agentcp.StateChangeCallback
import com.agentcp.GroupMessageCallback
import com.agentcp.GroupEventCallback
import com.agentcp.store.StorageConfig
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import io.flutter.plugin.common.MethodChannel.MethodCallHandler
import io.flutter.plugin.common.MethodChannel.Result
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.TimeoutException

/**
 * AgentCP SDK Flutter Plugin
 *
 * 提供 AgentCP SDK 的 Flutter 绑定，通过 MethodChannel 与 Dart 代码通信
 */
class AgentCPPlugin(private val context: Context) : MethodCallHandler {

    companion object {
        private const val TAG = "AgentCPPlugin"
        const val CHANNEL_NAME = "com.agent.acp/agentcp"
    }

    private val executor = Executors.newSingleThreadExecutor()

    // SDK 实例
    private val sdk: AgentCP = AgentCP.getInstance()

    // 当前加载的 AgentID
    private var currentAgent: AgentID? = null

    // 当前 seed password (set during createAID, reused for loadAID)
    private var currentPassword: String = ""

    // SDK 状态
    private var isInitialized = false

    // MethodChannel for sending callbacks to Flutter
    private var methodChannel: MethodChannel? = null

    fun setMethodChannel(channel: MethodChannel) {
        methodChannel = channel
    }

    override fun onMethodCall(call: MethodCall, result: Result) {
        when (call.method) {
            "initialize" -> initialize(call, result)
            "setBaseUrls" -> setBaseUrls(call, result)
            "setStoragePath" -> setStoragePath(call, result)
            "setLogLevel" -> setLogLevel(call, result)
            "createAID" -> createAID(call, result)
            "loadAID" -> loadAID(call, result)
            "deleteAID" -> deleteAID(call, result)
            "listAIDs" -> listAIDs(result)
            "online" -> online(result)
            "offline" -> offline(result)
            "isOnline" -> isOnline(result)
            "getState" -> getState(result)
            "getCurrentAID" -> getCurrentAID(result)
            "getVersion" -> getVersion(result)
            "getSignature" -> getSignature(result)
            "shutdown" -> shutdown(result)
            "setHandlers" -> setHandlers(result)
            "createSession" -> createSession(call, result)
            "inviteAgent" -> inviteAgent(call, result)
            "joinSession" -> joinSession(call, result)
            "getActiveSessions" -> getActiveSessions(result)
            "getSessionInfo" -> getSessionInfo(call, result)
            "sendMessage" -> sendMessage(call, result)
            "enableMessageStore" -> enableMessageStore(result)
            "getAllConversations" -> getAllConversations(result)
            "getMessages" -> getMessages(call, result)
            "deleteMessage" -> deleteMessageFromStore(call, result)
            "clearSession" -> clearSession(call, result)
            // Group methods
            "enableGroupMessageStore" -> enableGroupMessageStore(result)
            "initGroupClient" -> initGroupClient(call, result)
            "groupCreateGroup" -> groupCreateGroup(call, result)
            "groupJoinByUrl" -> groupJoinByUrl(call, result)
            "groupListMyGroups" -> groupListMyGroups(call, result)
            "groupGetInfo" -> groupGetInfo(call, result)
            "groupGetMembers" -> groupGetMembers(call, result)
            "groupLeaveGroup" -> groupLeaveGroup(call, result)
            "groupSearchGroups" -> groupSearchGroups(call, result)
            "groupSendMessage" -> groupSendMessage(call, result)
            "groupGetGroupList" -> groupGetGroupList(result)
            "groupGetMessages" -> groupGetMessages(call, result)
            "groupMarkRead" -> groupMarkRead(call, result)
            "joinGroupSession" -> joinGroupSession(call, result)
            "leaveGroupSession" -> leaveGroupSession(call, result)
            "setGroupHandlers" -> setGroupHandlers(result)
            else -> result.notImplemented()
        }
    }

    /**
     * 初始化 SDK
     */
    private fun initialize(call: MethodCall, result: Result) {
        executor.execute {
            try {
                Log.d(TAG, "Initializing SDK...")
                Log.d(TAG, "SDK version: ${sdk.getVersion()}")
                Log.d(TAG, "SDK build info: ${sdk.getBuildInfo()}")

                val r = sdk.initialize(context, StorageConfig.internal())
                Log.d(TAG, "SDK initialize result: ok=${r.ok()}, code=${r.code}, message=${r.message}, context=${r.context}")

                if (!r.ok()) {
                    postError(result, "INIT_FAILED", r.message, r.context)
                    return@execute
                }

                isInitialized = true
                Log.i(TAG, "SDK initialized successfully")

                postSuccess(result, mapOf(
                    "success" to true,
                    "message" to "SDK initialized successfully"
                ))
            } catch (e: Exception) {
                Log.e(TAG, "Initialize failed", e)
                postError(result, "INIT_FAILED", e.message, null)
            }
        }
    }

    /**
     * 设置服务器地址
     */
    private fun setBaseUrls(call: MethodCall, result: Result) {
        val caBaseUrl = call.argument<String>("caBaseUrl")
        val apBaseUrl = call.argument<String>("apBaseUrl")

        if (caBaseUrl == null || apBaseUrl == null) {
            result.error("INVALID_ARGS", "caBaseUrl and apBaseUrl are required", null)
            return
        }

        executor.execute {
            try {
                Log.d(TAG, "Setting base URLs: CA=$caBaseUrl, AP=$apBaseUrl")
                val r = sdk.setBaseUrls(caBaseUrl, apBaseUrl)
                Log.d(TAG, "setBaseUrls result: ok=${r.ok()}, code=${r.code}, message=${r.message}")

                if (!r.ok()) {
                    postError(result, "SET_URLS_FAILED", r.message, r.context)
                    return@execute
                }

                Log.i(TAG, "Base URLs set: CA=$caBaseUrl, AP=$apBaseUrl")

                postSuccess(result, mapOf(
                    "success" to true,
                    "message" to "Base URLs set successfully"
                ))
            } catch (e: Exception) {
                Log.e(TAG, "Set base URLs failed", e)
                postError(result, "SET_URLS_FAILED", e.message, null)
            }
        }
    }

    /**
     * 设置存储路径
     */
    private fun setStoragePath(call: MethodCall, result: Result) {
        val path = call.argument<String>("path")
            ?: context.filesDir.absolutePath + "/agentcp"

        executor.execute {
            try {
                // 确保目录存在
                val dir = java.io.File(path)
                if (!dir.exists()) {
                    dir.mkdirs()
                }

                Log.d(TAG, "Setting storage path: $path, exists=${dir.exists()}, canWrite=${dir.canWrite()}")
                val r = sdk.setStoragePath(path)
                Log.d(TAG, "setStoragePath result: ok=${r.ok()}, code=${r.code}, message=${r.message}")
                if (!r.ok()) {
                    postError(result, "SET_PATH_FAILED", r.message, r.context)
                    return@execute
                }

                Log.i(TAG, "Storage path set: $path")

                postSuccess(result, mapOf(
                    "success" to true,
                    "message" to "Storage path set successfully",
                    "path" to path
                ))
            } catch (e: Exception) {
                Log.e(TAG, "Set storage path failed", e)
                postError(result, "SET_PATH_FAILED", e.message, null)
            }
        }
    }

    /**
     * 设置日志级别
     */
    private fun setLogLevel(call: MethodCall, result: Result) {
        val level = call.argument<String>("level") ?: "info"

        try {
            val logLevel = when (level.lowercase()) {
                "error" -> LogLevel.Error
                "warn" -> LogLevel.Warn
                "info" -> LogLevel.Info
                "debug" -> LogLevel.Debug
                "trace" -> LogLevel.Trace
                else -> LogLevel.Info
            }

            val r = sdk.setLogLevel(logLevel)
            if (!r.ok()) {
                result.error("SET_LOG_LEVEL_FAILED", r.message, r.context)
                return
            }

            Log.i(TAG, "Log level set: $level")

            result.success(mapOf(
                "success" to true,
                "message" to "Log level set to $level"
            ))
        } catch (e: Exception) {
            Log.e(TAG, "Set log level failed", e)
            result.error("SET_LOG_LEVEL_FAILED", e.message, null)
        }
    }

    /**
     * 创建新的 Agent ID
     */
    private fun createAID(call: MethodCall, result: Result) {
        val aid = call.argument<String>("aid")
        val password = call.argument<String>("password")

        if (aid.isNullOrEmpty()) {
            result.error("INVALID_ARGS", "aid is required", null)
            return
        }

        if (password.isNullOrEmpty()) {
            result.error("INVALID_ARGS", "password is required", null)
            return
        }

        executor.execute {
            try {
                // 关闭之前的 Agent
                currentAgent?.close()

                Log.d(TAG, "Creating AID: $aid")

                // 创建新的 Agent
                currentAgent = sdk.createAID(aid, password)
                currentPassword = password

                // 自动启用消息持久化
                tryEnableMessageStore(currentAgent!!)

                Log.i(TAG, "Agent created: $aid, handle=${currentAgent}")

                postSuccess(result, mapOf(
                    "success" to true,
                    "message" to "Agent created successfully",
                    "aid" to aid
                ))
            } catch (e: AgentCPException) {
                val r = e.result
                Log.e(TAG, "Create AID failed: code=${r?.code}, msg=${r?.message}, ctx=${r?.context}", e)
                // 优先从 context 中提取服务器返回的具体错误信息
                val detail = extractServerError(r?.context) ?: r?.message ?: e.message
                postError(result, "CREATE_AID_FAILED", detail, null)
            } catch (e: Exception) {
                Log.e(TAG, "Create AID failed: ${e.javaClass.simpleName}: ${e.message}", e)
                postError(result, "CREATE_AID_FAILED", e.message, null)
            }
        }
    }

    /**
     * 加载已有的 Agent ID
     */
    private fun loadAID(call: MethodCall, result: Result) {
        val aid = call.argument<String>("aid")
        val password = call.argument<String>("password") ?: currentPassword

        if (aid == null) {
            result.error("INVALID_ARGS", "aid is required", null)
            return
        }

        executor.execute {
            try {
                // 关闭之前的 Agent
                currentAgent?.close()

                Log.d(TAG, "Loading AID: $aid")

                // 加载 Agent
                currentAgent = sdk.loadAID(aid, password)
                if (password.isNotEmpty()) {
                    currentPassword = password
                }

                // 自动启用消息持久化
                tryEnableMessageStore(currentAgent!!)

                Log.i(TAG, "Agent loaded: $aid, handle=${currentAgent}, state=${currentAgent?.getState()?.name}")

                postSuccess(result, mapOf(
                    "success" to true,
                    "message" to "Agent loaded successfully",
                    "aid" to aid
                ))
            } catch (e: Exception) {
                Log.e(TAG, "Load AID failed: ${e.javaClass.simpleName}: ${e.message}", e)
                postError(result, "LOAD_AID_FAILED", e.message, null)
            }
        }
    }

    /**
     * 删除 Agent ID
     */
    private fun deleteAID(call: MethodCall, result: Result) {
        val aid = call.argument<String>("aid")

        if (aid == null) {
            result.error("INVALID_ARGS", "aid is required", null)
            return
        }

        executor.execute {
            try {
                // 如果是当前 Agent，先关闭
                if (currentAgent?.getAID() == aid) {
                    currentAgent?.offline()
                    currentAgent?.close()
                    currentAgent = null
                }

                val r = sdk.deleteAID(aid)
                if (!r.ok()) {
                    postError(result, "DELETE_AID_FAILED", r.message, r.context)
                    return@execute
                }

                Log.i(TAG, "Agent deleted: $aid")

                postSuccess(result, mapOf(
                    "success" to true,
                    "message" to "Agent deleted successfully"
                ))
            } catch (e: Exception) {
                Log.e(TAG, "Delete AID failed", e)
                postError(result, "DELETE_AID_FAILED", e.message, null)
            }
        }
    }

    /**
     * 列出所有 Agent ID
     */
    private fun listAIDs(result: Result) {
        executor.execute {
            try {
                val aids = sdk.listAIDs()

                Log.i(TAG, "Listed AIDs: ${aids.toList()}")

                postSuccess(result, mapOf(
                    "success" to true,
                    "aids" to aids.toList()
                ))
            } catch (e: Exception) {
                Log.e(TAG, "List AIDs failed", e)
                postError(result, "LIST_AIDS_FAILED", e.message, null)
            }
        }
    }

    /**
     * 上线
     */
    private fun online(result: Result) {
        val agent = currentAgent
        Log.d(TAG, "online() called, currentAgent=$agent, aid=${agent?.getAID()}, state=${agent?.getState()?.name}, isOnline=${agent?.isOnline()}")

        if (agent == null) {
            Log.e(TAG, "online() failed: No agent loaded")
            result.error("NO_AGENT", "No agent loaded. Call createAID or loadAID first.", null)
            return
        }

        val replied = java.util.concurrent.atomic.AtomicBoolean(false)

        val future = executor.submit<Unit> {
            try {
                Log.d(TAG, "Calling agent.online() for ${agent.getAID()}, pre-state=${agent.getState().name}...")
                val r = agent.online()
                Log.d(TAG, "agent.online() returned: ok=${r.ok()}, code=${r.code}, message=${r.message}, context=${r.context}")
                Log.d(TAG, "Post-online state: ${agent.getState().name}, isOnline=${agent.isOnline()}")

                if (!r.ok()) {
                    Log.e(TAG, "online() failed: ${r.message}")
                    if (replied.compareAndSet(false, true)) {
                        postError(result, "ONLINE_FAILED", r.message, r.context)
                    }
                    return@submit
                }

                Log.i(TAG, "Agent is now online: ${agent.getAID()}")

                if (replied.compareAndSet(false, true)) {
                    postSuccess(result, mapOf(
                        "success" to true,
                        "message" to "Agent is now online",
                        "aid" to agent.getAID()
                    ))
                }
            } catch (e: Exception) {
                Log.e(TAG, "Online failed", e)
                if (replied.compareAndSet(false, true)) {
                    postError(result, "ONLINE_FAILED", e.message, null)
                }
            }
        }

        // 30秒超时监控，避免 online() 阻塞导致 UI 永远加载
        Thread {
            try {
                future.get(30, TimeUnit.SECONDS)
            } catch (e: TimeoutException) {
                Log.e(TAG, "online() timed out after 30s, state=${agent.getState().name}")
                future.cancel(true)
                if (replied.compareAndSet(false, true)) {
                    postError(result, "ONLINE_TIMEOUT", "连接超时(30s)，请检查网络或服务器地址", agent.getState().name)
                }
            } catch (e: Exception) {
                // future 正常完成或被取消，忽略
            }
        }.start()
    }

    /**
     * 下线
     */
    private fun offline(result: Result) {
        executor.execute {
            try {
                currentAgent?.offline()

                Log.i(TAG, "Agent is now offline")

                postSuccess(result, mapOf(
                    "success" to true,
                    "message" to "Agent is now offline"
                ))
            } catch (e: Exception) {
                Log.e(TAG, "Offline failed", e)
                postError(result, "OFFLINE_FAILED", e.message, null)
            }
        }
    }

    /**
     * 检查是否在线
     */
    private fun isOnline(result: Result) {
        val agent = currentAgent
        val online = agent?.isOnline() ?: false
        Log.i(TAG, "isOnline() called: agent=$agent, isOnline=$online")

        result.success(mapOf(
            "success" to true,
            "isOnline" to online
        ))
    }

    /**
     * 获取当前状态
     */
    private fun getState(result: Result) {
        val agent = currentAgent
        val state = agent?.getState() ?: AgentState.Offline
        Log.i(TAG, "getState() called: agent=$agent, state=${state.name}")

        result.success(mapOf(
            "success" to true,
            "state" to state.name
        ))
    }

    /**
     * 获取当前 AID
     */
    private fun getCurrentAID(result: Result) {
        result.success(mapOf(
            "success" to true,
            "aid" to currentAgent?.getAID()
        ))
    }

    /**
     * 获取 SDK 版本
     */
    private fun getVersion(result: Result) {
        val version = sdk.getVersion()

        result.success(mapOf(
            "success" to true,
            "version" to version
        ))
    }

    /**
     * 获取当前 Agent 的签名
     */
    private fun getSignature(result: Result) {
        val agent = currentAgent
        if (agent == null) {
            result.error("NO_AGENT", "No agent loaded", null)
            return
        }
        val signature = agent.getSignature()
        result.success(mapOf(
            "success" to true,
            "signature" to signature
        ))
    }

    /**
     * 关闭 SDK
     */
    private fun shutdown(result: Result) {
        executor.execute {
            try {
                currentAgent?.offline()
                currentAgent?.close()
                currentAgent = null

                sdk.shutdown()
                isInitialized = false

                Log.i(TAG, "SDK shutdown")

                postSuccess(result, mapOf(
                    "success" to true,
                    "message" to "SDK shutdown successfully"
                ))
            } catch (e: Exception) {
                Log.e(TAG, "Shutdown failed", e)
                postError(result, "SHUTDOWN_FAILED", e.message, null)
            }
        }
    }

    /**
     * Register native callbacks that forward to Flutter via MethodChannel
     */
    private fun setHandlers(result: Result) {
        val agent = currentAgent
        if (agent == null) {
            result.error("NO_AGENT", "No agent loaded", null)
            return
        }

        Log.i(TAG, "Setting up handlers for agent: ${agent.getAID()}")

        agent.setMessageHandler(object : MessageCallback {
            override fun onMessage(messageId: String, sessionId: String, sender: String, timestamp: Long, blocksJson: String) {
                Log.d(TAG, "=== onMessage CALLBACK TRIGGERED ===")
                Log.d(TAG, "onMessage: session=$sessionId, sender=$sender, msgId=$messageId")
                Log.d(TAG, "onMessage: timestamp=$timestamp, blocksJson=$blocksJson")
                android.os.Handler(context.mainLooper).post {
                    Log.d(TAG, "onMessage: Invoking Flutter method channel")
                    methodChannel?.invokeMethod("onMessage", mapOf(
                        "messageId" to messageId,
                        "sessionId" to sessionId,
                        "sender" to sender,
                        "timestamp" to timestamp,
                        "blocksJson" to blocksJson
                    ))
                    Log.d(TAG, "onMessage: Flutter method invoked")
                }
            }
        })

        agent.setInviteHandler(object : InviteCallback {
            override fun onInvite(sessionId: String, inviterId: String) {
                Log.d(TAG, "=== onInvite CALLBACK TRIGGERED ===")
                Log.d(TAG, "onInvite: session=$sessionId, inviter=$inviterId")
                android.os.Handler(context.mainLooper).post {
                    Log.d(TAG, "onInvite: Invoking Flutter method channel")
                    methodChannel?.invokeMethod("onInvite", mapOf(
                        "sessionId" to sessionId,
                        "inviterId" to inviterId
                    ))
                    Log.d(TAG, "onInvite: Flutter method invoked")
                }
            }
        })

        agent.setStateChangeHandler(object : StateChangeCallback {
            override fun onStateChange(oldState: Int, newState: Int) {
                Log.d(TAG, "=== onStateChange CALLBACK TRIGGERED ===")
                Log.d(TAG, "onStateChange: $oldState -> $newState")
                android.os.Handler(context.mainLooper).post {
                    methodChannel?.invokeMethod("onStateChange", mapOf(
                        "oldState" to oldState,
                        "newState" to newState
                    ))
                }
            }
        })

        Log.i(TAG, "Handlers registered successfully for ${agent.getAID()}")
        result.success(mapOf("success" to true, "message" to "Handlers registered"))
    }

    /**
     * Create a new session
     */
    private fun createSession(call: MethodCall, result: Result) {
        val members = call.argument<List<String>>("members") ?: emptyList()
        val agent = currentAgent
        Log.i(TAG, "createSession: members=$members, memberCount=${members.size}")
        for ((i, m) in members.withIndex()) {
            Log.i(TAG, "createSession: member[$i]='$m' (len=${m.length})")
        }
        if (agent == null) {
            result.error("NO_AGENT", "No agent loaded", null)
            return
        }

        executor.execute {
            try {
                val sessionId = agent.createSession(members.toTypedArray())
                Log.i(TAG, "Session created: $sessionId")
                postSuccess(result, mapOf(
                    "success" to true,
                    "sessionId" to sessionId
                ))
            } catch (e: Exception) {
                Log.e(TAG, "Create session failed", e)
                postError(result, "CREATE_SESSION_FAILED", e.message, null)
            }
        }
    }

    /**
     * Invite an agent to a session
     */
    private fun inviteAgent(call: MethodCall, result: Result) {
        val sessionId = call.argument<String>("sessionId")
        val agentId = call.argument<String>("agentId")
        val agent = currentAgent

        if (agent == null || sessionId == null || agentId == null) {
            result.error("INVALID_ARGS", "sessionId and agentId are required", null)
            return
        }

        executor.execute {
            try {
                val r = agent.inviteAgent(sessionId, agentId)
                Log.i(TAG, "Invite sent: session=$sessionId, target=$agentId, ok=${r.ok()}")
                if (!r.ok()) {
                    postError(result, "INVITE_FAILED", r.message, r.context)
                    return@execute
                }
                postSuccess(result, mapOf("success" to true))
            } catch (e: Exception) {
                Log.e(TAG, "Invite agent failed", e)
                postError(result, "INVITE_FAILED", e.message, null)
            }
        }
    }

    /**
     * Join a session
     */
    private fun joinSession(call: MethodCall, result: Result) {
        val sessionId = call.argument<String>("sessionId")
        val agent = currentAgent

        if (agent == null || sessionId == null) {
            result.error("INVALID_ARGS", "sessionId is required", null)
            return
        }

        executor.execute {
            try {
                val r = agent.joinSession(sessionId)
                Log.i(TAG, "Join session: $sessionId, ok=${r.ok()}")
                if (!r.ok()) {
                    postError(result, "JOIN_FAILED", r.message, r.context)
                    return@execute
                }
                postSuccess(result, mapOf("success" to true))
            } catch (e: Exception) {
                Log.e(TAG, "Join session failed", e)
                postError(result, "JOIN_FAILED", e.message, null)
            }
        }
    }

    /**
     * Get active sessions
     */
    private fun getActiveSessions(result: Result) {
        val agent = currentAgent
        if (agent == null) {
            result.error("NO_AGENT", "No agent loaded", null)
            return
        }

        executor.execute {
            try {
                val sessions = agent.getActiveSessions()
                Log.i(TAG, "Active sessions: ${sessions.toList()}")
                postSuccess(result, mapOf(
                    "success" to true,
                    "sessions" to sessions.toList()
                ))
            } catch (e: Exception) {
                Log.e(TAG, "Get active sessions failed", e)
                postError(result, "GET_SESSIONS_FAILED", e.message, null)
            }
        }
    }

    /**
     * Get session info as JSON
     */
    private fun getSessionInfo(call: MethodCall, result: Result) {
        val sessionId = call.argument<String>("sessionId")
        val agent = currentAgent

        if (agent == null || sessionId == null) {
            result.error("INVALID_ARGS", "sessionId is required", null)
            return
        }

        executor.execute {
            try {
                val info = agent.getSessionInfo(sessionId)
                Log.i(TAG, "Session info: $info")
                postSuccess(result, mapOf(
                    "success" to true,
                    "info" to info
                ))
            } catch (e: Exception) {
                Log.e(TAG, "Get session info failed", e)
                postError(result, "GET_SESSION_INFO_FAILED", e.message, null)
            }
        }
    }

    /**
     * Send a message to a session
     */
    private fun sendMessage(call: MethodCall, result: Result) {
        val sessionId = call.argument<String>("sessionId")
        val peerAid = call.argument<String>("peerAid")
        val blocksJson = call.argument<String>("blocksJson")
        val agent = currentAgent

        if (agent == null || sessionId == null || peerAid == null || blocksJson == null) {
            result.error("INVALID_ARGS", "sessionId, peerAid and blocksJson are required", null)
            return
        }

        executor.execute {
            try {
                Log.i(TAG, "Send request: session=$sessionId, peer='$peerAid', blocksLen=${blocksJson.length}, aid=${agent.getAID()}")
                val r = agent.sendMessage(sessionId, peerAid, blocksJson)
                Log.i(TAG, "Send result: session=$sessionId, peer='$peerAid', ok=${r.ok()}, code=${r.code}, message=${r.message}, context=${r.context}")
                if (!r.ok()) {
                    postError(result, "SEND_FAILED", r.message, r.context)
                    return@execute
                }
                postSuccess(result, mapOf("success" to true))
            } catch (e: Exception) {
                Log.e(TAG, "Send message failed", e)
                postError(result, "SEND_FAILED", e.message, null)
            }
        }
    }

    // ===== MessageStore bridge methods =====

    /**
     * 尝试自动启用 MessageStore（在 createAID/loadAID 后调用）
     */
    private fun tryEnableMessageStore(agent: AgentID) {
        try {
            val sdkInstance = AgentCP.getInstance()
            // Initialize SDK if needed
            try {
                sdkInstance.initialize(context, StorageConfig.internal())
            } catch (e: Exception) {
                // Already initialized, ignore
            }
            agent.enableMessageStore()
            Log.i(TAG, "MessageStore auto-enabled for ${agent.getAID()}")
            try {
                agent.enableGroupMessageStore()
                Log.i(TAG, "GroupMessageStore auto-enabled for ${agent.getAID()}")
            } catch (e2: Exception) {
                Log.w(TAG, "Failed to auto-enable GroupMessageStore: ${e2.message}")
            }
        } catch (e: Exception) {
            Log.w(TAG, "Failed to auto-enable MessageStore: ${e.message}")
        }
    }

    /**
     * 启用 SDK 消息持久化
     */
    private fun enableMessageStore(result: Result) {
        val agent = currentAgent
        if (agent == null) {
            result.error("NO_AGENT", "No agent loaded", null)
            return
        }

        executor.execute {
            try {
                // Ensure SDK has context and StorageConfig
                val sdkInstance = AgentCP.getInstance()
                try {
                    sdkInstance.initialize(context, StorageConfig.internal())
                } catch (e: Exception) {
                    // Already initialized, ignore
                }

                agent.enableMessageStore()
                Log.i(TAG, "MessageStore enabled for ${agent.getAID()}")

                postSuccess(result, mapOf(
                    "success" to true,
                    "message" to "MessageStore enabled"
                ))
            } catch (e: Exception) {
                Log.e(TAG, "enableMessageStore failed", e)
                postError(result, "ENABLE_STORE_FAILED", e.message, null)
            }
        }
    }

    /**
     * 获取所有会话列表
     */
    private fun getAllConversations(result: Result) {
        val agent = currentAgent
        if (agent == null) {
            result.error("NO_AGENT", "No agent loaded", null)
            return
        }

        executor.execute {
            try {
                val store = agent.getMessageStore()
                if (store == null) {
                    postError(result, "STORE_NOT_ENABLED", "MessageStore not enabled. Call enableMessageStore first.", null)
                    return@execute
                }

                val conversations = store.getAllConversations()
                val list = conversations.map { conv ->
                    mapOf(
                        "sessionId" to conv.sessionId,
                        "peerAid" to conv.peerAid,
                        "sessionType" to conv.sessionType,
                        "lastMsgId" to conv.lastMsgId,
                        "lastMsgTime" to conv.lastMsgTime,
                        "lastMsgPreview" to conv.lastMsgPreview,
                        "unreadCount" to conv.unreadCount
                    )
                }

                Log.i(TAG, "getAllConversations: ${list.size} conversations")
                postSuccess(result, mapOf(
                    "success" to true,
                    "conversations" to list
                ))
            } catch (e: Exception) {
                Log.e(TAG, "getAllConversations failed", e)
                postError(result, "GET_CONVERSATIONS_FAILED", e.message, null)
            }
        }
    }

    /**
     * 获取指定会话的消息列表
     */
    private fun getMessages(call: MethodCall, result: Result) {
        val sessionId = call.argument<String>("sessionId")
        val limit = call.argument<Int>("limit") ?: 100
        val offset = call.argument<Int>("offset") ?: 0
        val agent = currentAgent

        if (agent == null || sessionId == null) {
            result.error("INVALID_ARGS", "sessionId is required", null)
            return
        }

        executor.execute {
            try {
                val store = agent.getMessageStore()
                if (store == null) {
                    postError(result, "STORE_NOT_ENABLED", "MessageStore not enabled", null)
                    return@execute
                }

                val messages = store.getMessages(sessionId, limit, offset)
                val list = messages.map { msg ->
                    mapOf(
                        "messageId" to msg.messageId,
                        "sessionId" to msg.sessionId,
                        "sender" to msg.sender,
                        "peerAid" to msg.peerAid,
                        "direction" to msg.direction,
                        "timestamp" to msg.timestamp,
                        "blocksJson" to msg.blocksJson,
                        "status" to msg.status
                    )
                }

                Log.d(TAG, "getMessages: session=$sessionId, count=${list.size}")
                postSuccess(result, mapOf(
                    "success" to true,
                    "messages" to list
                ))
            } catch (e: Exception) {
                Log.e(TAG, "getMessages failed", e)
                postError(result, "GET_MESSAGES_FAILED", e.message, null)
            }
        }
    }

    /**
     * 删除单条消息（软删除）
     */
    private fun deleteMessageFromStore(call: MethodCall, result: Result) {
        val messageId = call.argument<String>("messageId")
        val agent = currentAgent

        if (agent == null || messageId == null) {
            result.error("INVALID_ARGS", "messageId is required", null)
            return
        }

        executor.execute {
            try {
                val store = agent.getMessageStore()
                if (store == null) {
                    postError(result, "STORE_NOT_ENABLED", "MessageStore not enabled", null)
                    return@execute
                }

                store.deleteMessage(messageId)
                Log.d(TAG, "deleteMessage: $messageId")
                postSuccess(result, mapOf("success" to true))
            } catch (e: Exception) {
                Log.e(TAG, "deleteMessage failed", e)
                postError(result, "DELETE_MESSAGE_FAILED", e.message, null)
            }
        }
    }

    /**
     * 清空指定会话的所有消息
     */
    private fun clearSession(call: MethodCall, result: Result) {
        val sessionId = call.argument<String>("sessionId")
        val agent = currentAgent

        if (agent == null || sessionId == null) {
            result.error("INVALID_ARGS", "sessionId is required", null)
            return
        }

        executor.execute {
            try {
                val store = agent.getMessageStore()
                if (store == null) {
                    postError(result, "STORE_NOT_ENABLED", "MessageStore not enabled", null)
                    return@execute
                }

                store.clearSession(sessionId)
                Log.d(TAG, "clearSession: $sessionId")
                postSuccess(result, mapOf("success" to true))
            } catch (e: Exception) {
                Log.e(TAG, "clearSession failed", e)
                postError(result, "CLEAR_SESSION_FAILED", e.message, null)
            }
        }
    }

    // ===== Group methods =====

    private fun enableGroupMessageStore(result: Result) {
        val agent = currentAgent
        if (agent == null) {
            result.error("NO_AGENT", "No agent loaded", null)
            return
        }
        executor.execute {
            try {
                agent.enableGroupMessageStore()
                Log.i(TAG, "GroupMessageStore enabled for ${agent.getAID()}")
                postSuccess(result, mapOf("success" to true, "message" to "GroupMessageStore enabled"))
            } catch (e: Exception) {
                Log.e(TAG, "enableGroupMessageStore failed", e)
                postError(result, "ENABLE_GROUP_STORE_FAILED", e.message, null)
            }
        }
    }

    private fun initGroupClient(call: MethodCall, result: Result) {
        val sessionId = call.argument<String>("sessionId") ?: ""
        val targetAid = call.argument<String>("targetAid") ?: ""
        val agent = currentAgent
        if (agent == null) {
            result.error("NO_AGENT", "No agent loaded", null)
            return
        }
        executor.execute {
            try {
                agent.initGroupClient(sessionId, targetAid)
                Log.i(TAG, "GroupClient initialized: session=$sessionId, target=$targetAid")
                postSuccess(result, mapOf("success" to true, "message" to "GroupClient initialized"))
            } catch (e: Exception) {
                Log.e(TAG, "initGroupClient failed", e)
                postError(result, "INIT_GROUP_CLIENT_FAILED", e.message, null)
            }
        }
    }

    private fun groupCreateGroup(call: MethodCall, result: Result) {
        val name = call.argument<String>("name") ?: ""
        val alias = call.argument<String>("alias") ?: ""
        val subject = call.argument<String>("subject") ?: ""
        val visibility = call.argument<String>("visibility") ?: "public"
        val description = call.argument<String>("description") ?: ""
        val tagsString = call.argument<String>("tags") ?: ""
        val tagsArray = if (tagsString.isNotEmpty()) tagsString.split(",").map { it.trim() }.toTypedArray() else arrayOf()
        val agent = currentAgent
        if (agent == null) {
            result.error("NO_AGENT", "No agent loaded", null)
            return
        }
        executor.execute {
            try {
                ensureGroupClientInitialized(agent)
                val json = agent.groupCreateGroup(name, alias, subject, visibility, description, tagsArray)
                Log.i(TAG, "groupCreateGroup result: $json")
                // Parse JSON to extract group_id and group_url
                val parsed = org.json.JSONObject(json)
                postSuccess(result, mapOf(
                    "success" to true,
                    "groupId" to parsed.optString("group_id", ""),
                    "groupUrl" to parsed.optString("group_url", ""),
                    "raw" to json
                ))
            } catch (e: Exception) {
                Log.e(TAG, "groupCreateGroup failed", e)
                postError(result, "GROUP_CREATE_FAILED", e.message, null)
            }
        }
    }

    private fun groupJoinByUrl(call: MethodCall, result: Result) {
        val rawGroupUrl = call.argument<String>("groupUrl") ?: ""
        val inviteCodeArg = call.argument<String>("inviteCode") ?: ""
        val message = call.argument<String>("message") ?: ""
        val agent = currentAgent
        if (agent == null) {
            result.error("NO_AGENT", "No agent loaded", null)
            return
        }
        executor.execute {
            try {
                val (groupUrl, groupId, inviteCode) = parseGroupJoinInput(rawGroupUrl, inviteCodeArg)
                ensureGroupClientInitialized(agent)

                var requestId = ""
                var hasExistingRequest = false
                try {
                    requestId = agent.groupJoinByUrl(groupUrl, inviteCode, message)
                    Log.i(TAG, "groupJoinByUrl: requestId=$requestId, groupId=$groupId")
                } catch (e: Exception) {
                    val msg = e.message ?: ""
                    if (msg.contains("request already exists") || msg.contains("code=1012")) {
                        hasExistingRequest = true
                        Log.w(TAG, "groupJoinByUrl: request already exists, will report as pending")
                    } else {
                        throw e
                    }
                }

                val joinStatus = detectJoinStatus(agent, groupId, inviteCode, requestId, hasExistingRequest)
                val joined = joinStatus == "joined"
                val pending = joinStatus == "pending"

                var groupName = groupId
                if (groupId.isNotEmpty()) {
                    try {
                        val infoJson = agent.groupGetInfo(groupId)
                        val info = org.json.JSONObject(infoJson)
                        groupName = info.optString("name", groupId)
                        Log.i(TAG, "groupJoinByUrl: groupName=$groupName")
                    } catch (e: Exception) {
                        Log.w(TAG, "groupJoinByUrl: getInfo failed: ${e.message}")
                    }
                }

                if (joined && groupId.isNotEmpty()) {
                    joinGroupSessionWithRetry(agent, groupId)
                }

                postSuccess(result, mapOf(
                    "success" to true,
                    "requestId" to requestId,
                    "groupId" to groupId,
                    "groupName" to groupName,
                    "hasExistingRequest" to hasExistingRequest,
                    "pending" to pending,
                    "joined" to joined,
                    "status" to joinStatus
                ))
            } catch (e: Exception) {
                Log.e(TAG, "groupJoinByUrl failed", e)
                postError(result, "GROUP_JOIN_FAILED", e.message, null)
            }
        }
    }

    private fun groupListMyGroups(call: MethodCall, result: Result) {
        val statusString = call.argument<String>("status") ?: "0"
        val status = statusString.toIntOrNull() ?: 0
        val agent = currentAgent
        if (agent == null) {
            result.error("NO_AGENT", "No agent loaded", null)
            return
        }
        executor.execute {
            try {
                ensureGroupClientInitialized(agent)
                val json = agent.groupListMyGroups(status)
                Log.i(TAG, "groupListMyGroups: $json")
                postSuccess(result, mapOf("success" to true, "data" to json))
            } catch (e: Exception) {
                Log.e(TAG, "groupListMyGroups failed", e)
                postError(result, "GROUP_LIST_FAILED", e.message, null)
            }
        }
    }

    private fun groupGetInfo(call: MethodCall, result: Result) {
        val groupId = call.argument<String>("groupId") ?: ""
        val agent = currentAgent
        if (agent == null) {
            result.error("NO_AGENT", "No agent loaded", null)
            return
        }
        executor.execute {
            try {
                val json = agent.groupGetInfo(groupId)
                Log.i(TAG, "groupGetInfo: $json")
                postSuccess(result, mapOf("success" to true, "data" to json))
            } catch (e: Exception) {
                Log.e(TAG, "groupGetInfo failed", e)
                postError(result, "GROUP_GET_INFO_FAILED", e.message, null)
            }
        }
    }

    private fun groupGetMembers(call: MethodCall, result: Result) {
        val groupId = call.argument<String>("groupId") ?: ""
        val agent = currentAgent
        if (agent == null) {
            result.error("NO_AGENT", "No agent loaded", null)
            return
        }
        executor.execute {
            try {
                val json = agent.groupGetMembers(groupId)
                Log.i(TAG, "groupGetMembers: $json")
                postSuccess(result, mapOf("success" to true, "data" to json))
            } catch (e: Exception) {
                Log.e(TAG, "groupGetMembers failed", e)
                postError(result, "GROUP_GET_MEMBERS_FAILED", e.message, null)
            }
        }
    }

    private fun groupLeaveGroup(call: MethodCall, result: Result) {
        val groupId = call.argument<String>("groupId") ?: ""
        val agent = currentAgent
        if (agent == null) {
            result.error("NO_AGENT", "No agent loaded", null)
            return
        }
        executor.execute {
            try {
                agent.groupLeaveGroup(groupId)
                Log.i(TAG, "groupLeaveGroup: $groupId")
                postSuccess(result, mapOf("success" to true))
            } catch (e: Exception) {
                Log.e(TAG, "groupLeaveGroup failed", e)
                postError(result, "GROUP_LEAVE_FAILED", e.message, null)
            }
        }
    }

    private fun groupSearchGroups(call: MethodCall, result: Result) {
        val keyword = call.argument<String>("keyword") ?: ""
        val tagsString = call.argument<String>("tags") ?: ""
        val tagsArray = if (tagsString.isNotEmpty()) tagsString.split(",").map { it.trim() }.toTypedArray() else arrayOf()
        val limit = call.argument<Int>("limit") ?: 20
        val offset = call.argument<Int>("offset") ?: 0
        val agent = currentAgent
        if (agent == null) {
            result.error("NO_AGENT", "No agent loaded", null)
            return
        }
        executor.execute {
            try {
                ensureGroupClientInitialized(agent)
                val json = agent.groupSearchGroups(keyword, tagsArray, limit, offset)
                Log.i(TAG, "groupSearchGroups: $json")
                postSuccess(result, mapOf("success" to true, "data" to json))
            } catch (e: Exception) {
                Log.e(TAG, "groupSearchGroups failed", e)
                postError(result, "GROUP_SEARCH_FAILED", e.message, null)
            }
        }
    }

    private fun groupSendMessage(call: MethodCall, result: Result) {
        val groupId = call.argument<String>("groupId") ?: ""
        val content = call.argument<String>("content") ?: ""
        val contentType = call.argument<String>("contentType") ?: "text"
        val metadataJson = call.argument<String>("metadataJson") ?: ""
        val agent = currentAgent
        if (agent == null) {
            result.error("NO_AGENT", "No agent loaded", null)
            return
        }
        executor.execute {
            try {
                ensureGroupClientInitialized(agent)
                val json = agent.groupSendMessage(groupId, content, contentType, metadataJson)
                Log.i(TAG, "groupSendMessage: $json")
                val parsed = org.json.JSONObject(json)
                postSuccess(result, mapOf(
                    "success" to true,
                    "msgId" to parsed.optString("msg_id", ""),
                    "timestamp" to parsed.optLong("timestamp", 0L),
                    "raw" to json
                ))
            } catch (e: Exception) {
                Log.e(TAG, "groupSendMessage failed", e)
                postError(result, "GROUP_SEND_FAILED", e.message, null)
            }
        }
    }

    private fun groupGetGroupList(result: Result) {
        val agent = currentAgent
        if (agent == null) {
            result.error("NO_AGENT", "No agent loaded", null)
            return
        }
        executor.execute {
            try {
                val store = agent.getGroupMessageStore()
                if (store == null) {
                    postError(result, "GROUP_STORE_NOT_ENABLED", "GroupMessageStore not enabled", null)
                    return@execute
                }
                val groups = store.getGroupList()
                val list = groups.map { g ->
                    mapOf(
                        "groupId" to g.groupId,
                        "groupName" to g.groupName,
                        "unreadCount" to g.unreadCount,
                        "lastMsgTime" to g.lastMessageAt
                    )
                }
                Log.i(TAG, "groupGetGroupList: ${list.size} groups")
                postSuccess(result, mapOf("success" to true, "groups" to list))
            } catch (e: Exception) {
                Log.e(TAG, "groupGetGroupList failed", e)
                postError(result, "GROUP_GET_LIST_FAILED", e.message, null)
            }
        }
    }

    private fun groupGetMessages(call: MethodCall, result: Result) {
        val groupId = call.argument<String>("groupId") ?: ""
        val limit = call.argument<Int>("limit") ?: 100
        val offset = call.argument<Int>("offset") ?: 0
        val agent = currentAgent
        if (agent == null) {
            result.error("NO_AGENT", "No agent loaded", null)
            return
        }
        executor.execute {
            try {
                val store = agent.getGroupMessageStore()
                if (store == null) {
                    postError(result, "GROUP_STORE_NOT_ENABLED", "GroupMessageStore not enabled", null)
                    return@execute
                }
                val messages = store.getLatestMessages(groupId, limit)
                val list = messages.map { m ->
                    mapOf(
                        "msgId" to m.msgId,
                        "groupId" to m.groupId,
                        "sender" to m.sender,
                        "content" to m.content,
                        "contentType" to m.contentType,
                        "timestamp" to m.timestamp
                    )
                }
                Log.d(TAG, "groupGetMessages: group=$groupId, count=${list.size}")
                postSuccess(result, mapOf("success" to true, "messages" to list))
            } catch (e: Exception) {
                Log.e(TAG, "groupGetMessages failed", e)
                postError(result, "GROUP_GET_MESSAGES_FAILED", e.message, null)
            }
        }
    }

    private fun groupMarkRead(call: MethodCall, result: Result) {
        val groupId = call.argument<String>("groupId") ?: ""
        val agent = currentAgent
        if (agent == null) {
            result.error("NO_AGENT", "No agent loaded", null)
            return
        }
        executor.execute {
            try {
                val store = agent.getGroupMessageStore()
                if (store == null) {
                    postError(result, "GROUP_STORE_NOT_ENABLED", "GroupMessageStore not enabled", null)
                    return@execute
                }
                store.markGroupRead(groupId)
                Log.d(TAG, "groupMarkRead: $groupId")
                postSuccess(result, mapOf("success" to true))
            } catch (e: Exception) {
                Log.e(TAG, "groupMarkRead failed", e)
                postError(result, "GROUP_MARK_READ_FAILED", e.message, null)
            }
        }
    }

    private fun joinGroupSession(call: MethodCall, result: Result) {
        val groupId = call.argument<String>("groupId") ?: ""
        val agent = currentAgent
        if (agent == null) {
            result.error("NO_AGENT", "No agent loaded", null)
            return
        }
        executor.execute {
            try {
                agent.joinGroupSession(groupId)
                Log.i(TAG, "joinGroupSession: $groupId")
                postSuccess(result, mapOf("success" to true))
            } catch (e: Exception) {
                Log.e(TAG, "joinGroupSession failed", e)
                postError(result, "JOIN_GROUP_SESSION_FAILED", e.message, null)
            }
        }
    }

    private fun leaveGroupSession(call: MethodCall, result: Result) {
        val groupId = call.argument<String>("groupId") ?: ""
        val agent = currentAgent
        if (agent == null) {
            result.error("NO_AGENT", "No agent loaded", null)
            return
        }
        executor.execute {
            try {
                agent.leaveGroupSession(groupId)
                Log.i(TAG, "leaveGroupSession: $groupId")
                postSuccess(result, mapOf("success" to true))
            } catch (e: Exception) {
                Log.e(TAG, "leaveGroupSession failed", e)
                postError(result, "LEAVE_GROUP_SESSION_FAILED", e.message, null)
            }
        }
    }

    private fun setGroupHandlers(result: Result) {
        val agent = currentAgent
        if (agent == null) {
            result.error("NO_AGENT", "No agent loaded", null)
            return
        }

        agent.setGroupMessageHandler(object : GroupMessageCallback {
            override fun onGroupMessageBatch(groupId: String, batchJson: String) {
                Log.d(TAG, "onGroupMessageBatch: group=$groupId")
                android.os.Handler(context.mainLooper).post {
                    methodChannel?.invokeMethod("onGroupMessageBatch", mapOf(
                        "groupId" to groupId,
                        "batchJson" to batchJson
                    ))
                }
            }
        })

        agent.setGroupEventHandler(object : GroupEventCallback {
            override fun onNewMessage(groupId: String, latestMsgId: Long, sender: String, preview: String) {
                Log.d(TAG, "onGroupNewMessage: group=$groupId, sender=$sender")
                android.os.Handler(context.mainLooper).post {
                    methodChannel?.invokeMethod("onGroupNewMessage", mapOf(
                        "groupId" to groupId,
                        "latestMsgId" to latestMsgId,
                        "sender" to sender,
                        "preview" to preview
                    ))
                }
            }

            override fun onNewEvent(groupId: String, latestEventId: Long, eventType: String, summary: String) {
                Log.d(TAG, "onGroupNewEvent: group=$groupId, type=$eventType")
                android.os.Handler(context.mainLooper).post {
                    methodChannel?.invokeMethod("onGroupNewEvent", mapOf(
                        "groupId" to groupId,
                        "latestEventId" to latestEventId,
                        "eventType" to eventType,
                        "summary" to summary
                    ))
                }
            }

            override fun onGroupInvite(groupId: String, groupAddress: String, invitedBy: String) {
                Log.d(TAG, "onGroupInvite: group=$groupId, invitedBy=$invitedBy")
                android.os.Handler(context.mainLooper).post {
                    methodChannel?.invokeMethod("onGroupInvite", mapOf(
                        "groupId" to groupId,
                        "groupAddress" to groupAddress,
                        "invitedBy" to invitedBy
                    ))
                }
            }

            override fun onJoinApproved(groupId: String, groupAddress: String) {
                Log.d(TAG, "onGroupJoinApproved: group=$groupId")
                android.os.Handler(context.mainLooper).post {
                    methodChannel?.invokeMethod("onGroupJoinApproved", mapOf(
                        "groupId" to groupId,
                        "groupAddress" to groupAddress
                    ))
                }
            }

            override fun onJoinRejected(groupId: String, reason: String) {
                Log.d(TAG, "onGroupJoinRejected: group=$groupId, reason=$reason")
                android.os.Handler(context.mainLooper).post {
                    methodChannel?.invokeMethod("onGroupJoinRejected", mapOf(
                        "groupId" to groupId,
                        "reason" to reason
                    ))
                }
            }

            override fun onJoinRequestReceived(groupId: String, agentId: String, message: String) {
                Log.d(TAG, "onGroupJoinRequestReceived: group=$groupId, agent=$agentId")
                android.os.Handler(context.mainLooper).post {
                    methodChannel?.invokeMethod("onGroupJoinRequestReceived", mapOf(
                        "groupId" to groupId,
                        "agentId" to agentId,
                        "message" to message
                    ))
                }
            }

            override fun onGroupEvent(groupId: String, eventJson: String) {
                Log.d(TAG, "onGroupEvent: group=$groupId")
                android.os.Handler(context.mainLooper).post {
                    methodChannel?.invokeMethod("onGroupEvent", mapOf(
                        "groupId" to groupId,
                        "eventJson" to eventJson
                    ))
                }
            }
        })

        Log.i(TAG, "Group handlers registered for ${agent.getAID()}")
        result.success(mapOf("success" to true, "message" to "Group handlers registered"))
    }

    // Helper: 在主线程返回成功结果
    private fun postSuccess(result: Result, data: Map<String, Any?>) {
        android.os.Handler(context.mainLooper).post {
            result.success(data)
        }
    }

    // Helper: 在主线程返回错误结果
    private fun postError(result: Result, code: String, message: String?, details: Any?) {
        android.os.Handler(context.mainLooper).post {
            result.error(code, message, details)
        }
    }

    // Helper: 确保 GroupClient 已初始化，如果未初始化则自动初始化
    // 必须在 executor 线程中调用
    private fun parseGroupJoinInput(groupUrl: String, inviteCodeArg: String): Triple<String, String, String> {
        if (groupUrl.isBlank()) {
            throw RuntimeException("groupUrl is required")
        }
        val uri = Uri.parse(groupUrl)
        val groupId = (uri.path ?: "").trim('/')
        val normalizedUrl = uri.buildUpon().clearQuery().fragment(null).build().toString()
        val inviteCodeFromUrl = uri.getQueryParameter("code")
            ?: uri.getQueryParameter("inviteCode")
            ?: ""
        val inviteCode = if (inviteCodeArg.isNotBlank()) inviteCodeArg else inviteCodeFromUrl
        return Triple(normalizedUrl, groupId, inviteCode)
    }

    private fun detectJoinStatus(
        agent: com.agentcp.AgentID,
        groupId: String,
        inviteCode: String,
        requestId: String,
        hasExistingRequest: Boolean,
    ): String {
        if (hasExistingRequest) return "pending"
        if (groupId.isEmpty()) {
            return if (inviteCode.isNotEmpty()) "joined" else if (requestId.isNotEmpty()) "pending" else "joined"
        }
        if (inviteCode.isNotEmpty()) return "joined"

        repeat(4) { attempt ->
            val membershipStatus = getMembershipStatus(agent, groupId)
            if (membershipStatus == 1) return "joined"
            if (membershipStatus == 0) return "pending"
            if (attempt < 3) Thread.sleep((attempt + 1) * 350L)
        }
        return if (requestId.isNotEmpty()) "pending" else "joined"
    }

    private fun getMembershipStatus(agent: com.agentcp.AgentID, groupId: String): Int? {
        return try {
            val json = agent.groupListMyGroups(0)
            val data = org.json.JSONObject(json)
            val groups = data.optJSONArray("groups") ?: return null
            for (i in 0 until groups.length()) {
                val group = groups.optJSONObject(i) ?: continue
                if (group.optString("group_id", "") == groupId) {
                    return if (group.has("status")) group.optInt("status", -1) else null
                }
            }
            null
        } catch (_: Exception) {
            null
        }
    }

    private fun joinGroupSessionWithRetry(agent: com.agentcp.AgentID, groupId: String) {
        var lastError: Exception? = null
        val waitSchedule = longArrayOf(800L, 1500L, 2500L)
        for ((idx, waitMs) in waitSchedule.withIndex()) {
            Thread.sleep(waitMs)
            try {
                agent.joinGroupSession(groupId)
                Log.i(TAG, "groupJoinByUrl: auto joinGroupSession succeeded (attempt=${idx + 1})")
                return
            } catch (e: Exception) {
                lastError = e
                Log.w(TAG, "groupJoinByUrl: joinGroupSession attempt ${idx + 1} failed: ${e.message}")
            }
        }
        throw RuntimeException("joinGroupSession failed for $groupId: ${lastError?.message}", lastError)
    }

    private fun ensureGroupClientInitialized(agent: com.agentcp.AgentID) {
        if (!agent.getGroupTargetAid().isNullOrEmpty()) return
        Log.w(TAG, "GroupClient not initialized, auto-initializing...")
        val aid = agent.getAID()
        val dotIndex = aid.indexOf('.')
        if (dotIndex <= 0) {
            throw RuntimeException("Cannot derive group target from AID: $aid")
        }
        val issuer = aid.substring(dotIndex + 1)
        val groupTarget = "group.$issuer"
        val sessionId = agent.createSession(arrayOf(groupTarget))
        agent.initGroupClient(sessionId, groupTarget)
        Log.i(TAG, "Auto-initialized GroupClient: target=$groupTarget, session=$sessionId")
    }

    // Helper: 从 context 字符串中提取服务器返回的错误信息
    // context 格式可能是: "CA server request failed: 400: {\"error\":\"...\"}"
    private fun extractServerError(context: String?): String? {
        if (context.isNullOrBlank()) return null
        val jsonStart = context.indexOf('{')
        if (jsonStart < 0) return null
        return try {
            val json = org.json.JSONObject(context.substring(jsonStart))
            json.optString("error", null)
        } catch (_: Exception) {
            null
        }
    }
}
