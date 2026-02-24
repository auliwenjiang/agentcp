package com.agentcp;

public final class AgentCPException extends RuntimeException {
    private final Result result;

    public AgentCPException(Result result) {
        super(result != null ? result.message : "AgentCP error");
        this.result = result;
    }

    public Result getResult() {
        return result;
    }
}
