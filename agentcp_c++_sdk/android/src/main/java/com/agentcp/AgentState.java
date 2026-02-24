package com.agentcp;

public enum AgentState {
    Offline(0),
    Connecting(1),
    Authenticating(2),
    Online(3),
    Reconnecting(4),
    Error(5);

    private final int value;

    AgentState(int value) {
        this.value = value;
    }

    public int value() {
        return value;
    }

    public static AgentState fromValue(int value) {
        for (AgentState state : values()) {
            if (state.value == value) {
                return state;
            }
        }
        return Error;
    }
}
