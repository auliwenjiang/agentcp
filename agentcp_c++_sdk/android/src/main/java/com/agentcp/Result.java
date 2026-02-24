package com.agentcp;

public final class Result {
    public final int code;
    public final String message;
    public final String context;

    public Result(int code, String message, String context) {
        this.code = code;
        this.message = message;
        this.context = context;
    }

    public boolean ok() {
        return code == 0;
    }

    @Override
    public String toString() {
        return "Result{" +
            "code=" + code +
            ", message='" + message + '\'' +
            ", context='" + context + '\'' +
            '}';
    }
}
