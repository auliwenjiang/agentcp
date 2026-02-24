package com.agentcp;

public enum LogLevel {
    Error(0),
    Warn(1),
    Info(2),
    Debug(3),
    Trace(4);

    private final int value;

    LogLevel(int value) {
        this.value = value;
    }

    public int value() {
        return value;
    }
}
