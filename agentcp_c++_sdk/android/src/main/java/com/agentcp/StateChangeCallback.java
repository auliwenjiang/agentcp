package com.agentcp;

public interface StateChangeCallback {
    void onStateChange(int oldState, int newState);
}
