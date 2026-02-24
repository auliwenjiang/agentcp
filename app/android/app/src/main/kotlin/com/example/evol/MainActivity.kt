package com.example.evol

import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {

    private lateinit var agentCPChannel: MethodChannel

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
    }

    override fun onDestroy() {
        super.onDestroy()
        agentCPChannel.setMethodCallHandler(null)
    }
}
