package com.agent.acp

import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {

    private lateinit var agentCPChannel: MethodChannel
    private lateinit var appLifecycleChannel: MethodChannel

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        // 注册 AgentCP MethodChannel
        agentCPChannel = MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            AgentCPPlugin.CHANNEL_NAME
        )

        val plugin = AgentCPPlugin(applicationContext)
        plugin.setMethodChannel(agentCPChannel)
        agentCPChannel.setMethodCallHandler(plugin)

        appLifecycleChannel = MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            "com.agent.acp/app_lifecycle"
        )
        appLifecycleChannel.setMethodCallHandler { call, result ->
            when (call.method) {
                "moveTaskToBack" -> {
                    moveTaskToBack(true)
                    result.success(true)
                }
                else -> result.notImplemented()
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        agentCPChannel.setMethodCallHandler(null)
        appLifecycleChannel.setMethodCallHandler(null)
    }
}
