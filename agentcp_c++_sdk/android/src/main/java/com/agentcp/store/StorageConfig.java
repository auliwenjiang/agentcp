package com.agentcp.store;

public final class StorageConfig {
    private final StorageMode mode;
    private final String customPath;

    private StorageConfig(StorageMode mode, String customPath) {
        this.mode = mode;
        this.customPath = customPath;
    }

    public static StorageConfig internal() {
        return new StorageConfig(StorageMode.INTERNAL, null);
    }

    public static StorageConfig external() {
        return new StorageConfig(StorageMode.EXTERNAL, null);
    }

    public static StorageConfig custom(String path) {
        if (path == null || path.isEmpty()) {
            throw new IllegalArgumentException("Custom storage path must not be null or empty");
        }
        return new StorageConfig(StorageMode.CUSTOM, path);
    }

    public StorageMode getMode() {
        return mode;
    }

    public String getCustomPath() {
        return customPath;
    }
}
