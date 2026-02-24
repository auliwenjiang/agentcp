package com.agentcp;

import android.content.Context;

import com.agentcp.store.StorageConfig;

public final class AgentCP {
    static {
        System.loadLibrary("agentcp_jni");
    }

    private static final AgentCP INSTANCE = new AgentCP();

    private Context appContext;
    private StorageConfig storageConfig;

    private AgentCP() {}

    public static AgentCP getInstance() {
        return INSTANCE;
    }

    public Result initialize() {
        return nativeInitialize();
    }

    public Result initialize(Context context, StorageConfig config) {
        if (context == null) {
            throw new IllegalArgumentException("Context must not be null");
        }
        if (config == null) {
            throw new IllegalArgumentException("StorageConfig must not be null");
        }
        this.appContext = context.getApplicationContext();
        this.storageConfig = config;
        return nativeInitialize();
    }

    public void shutdown() {
        nativeShutdown();
    }

    public Result setBaseUrls(String caBase, String apBase) {
        return nativeSetBaseUrls(caBase, apBase);
    }

    public Result setStoragePath(String path) {
        return nativeSetStoragePath(path);
    }

    public Result setLogLevel(LogLevel level) {
        return nativeSetLogLevel(level != null ? level.value() : 2);
    }

    public AgentID createAID(String aid, String password) {
        long handle = nativeCreateAID(aid, password);
        return new AgentID(handle);
    }

    public AgentID loadAID(String aid, String seedPassword) {
        long handle = nativeLoadAID(aid, seedPassword);
        return new AgentID(handle);
    }

    public Result deleteAID(String aid) {
        return nativeDeleteAID(aid);
    }

    public String[] listAIDs() {
        return nativeListAIDs();
    }

    public String getVersion() {
        return nativeGetVersion();
    }

    public String getBuildInfo() {
        return nativeGetBuildInfo();
    }

    Context getAppContext() {
        return appContext;
    }

    StorageConfig getStorageConfig() {
        return storageConfig;
    }

    private native Result nativeInitialize();
    private native void nativeShutdown();
    private native Result nativeSetBaseUrls(String caBase, String apBase);
    private native Result nativeSetStoragePath(String path);
    private native Result nativeSetLogLevel(int level);
    private native long nativeCreateAID(String aid, String password);
    private native long nativeLoadAID(String aid, String seedPassword);
    private native Result nativeDeleteAID(String aid);
    private native String[] nativeListAIDs();
    private native String nativeGetVersion();
    private native String nativeGetBuildInfo();
}
