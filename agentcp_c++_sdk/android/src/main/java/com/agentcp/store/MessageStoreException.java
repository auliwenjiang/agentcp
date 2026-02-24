package com.agentcp.store;

public class MessageStoreException extends RuntimeException {

    public MessageStoreException(String message) {
        super(message);
    }

    public MessageStoreException(String message, Throwable cause) {
        super(message, cause);
    }
}
