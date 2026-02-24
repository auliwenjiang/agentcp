# AgentCP SDK ProGuard Rules

# Keep all public classes and methods
-keep public class com.agentcp.** { public *; }

# Keep native methods
-keepclasseswithmembernames class * {
    native <methods>;
}

# Keep Result class (used by JNI)
-keep class com.agentcp.Result { *; }

# Keep AgentCPException (used by JNI)
-keep class com.agentcp.AgentCPException { *; }

# Keep enums
-keepclassmembers enum com.agentcp.** {
    public static **[] values();
    public static ** valueOf(java.lang.String);
}
