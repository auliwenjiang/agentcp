# AgentCP SDK Consumer ProGuard Rules
# These rules are automatically applied to apps that use this library

# Keep all public API classes
-keep public class com.agentcp.AgentCP { public *; }
-keep public class com.agentcp.AgentID { public *; }
-keep public class com.agentcp.Result { *; }
-keep public class com.agentcp.AgentCPException { *; }
-keep public class com.agentcp.AgentState { *; }
-keep public class com.agentcp.LogLevel { *; }
-keep public class com.agentcp.GroupSyncHandler { *; }

# Keep native methods
-keepclasseswithmembernames class * {
    native <methods>;
}
