/**
 * ACP Group Client - core request/response transport.
 * Mirrors Python SDK: agentcp/group/client.py
 *
 * Key difference: Python uses queue.Queue blocking; TypeScript uses Promise + Deferred pattern.
 * JS single-threaded: no locks needed.
 */

import {
    GroupRequest, GroupResponse, GroupNotify, GroupMessageBatch,
    buildGroupRequest, parseGroupResponse, parseGroupNotify,
    NOTIFY_GROUP_MESSAGE,
} from './types';
import { ACPGroupEventHandler, dispatchAcpNotify } from './events';
import { CursorStore } from './cursor_store';
import { logger } from '../utils';

/** Type alias: send_func(targetAid, payload) -> void */
export type SendFunc = (targetAid: string, payload: string) => void;

interface PendingRequest {
    resolve: (resp: GroupResponse) => void;
    reject: (err: Error) => void;
    timer: ReturnType<typeof setTimeout>;
}

export class ACPGroupClient {
    private _agentId: string;
    private _sendFunc: SendFunc;
    private _pendingReqs: Map<string, PendingRequest> = new Map();
    private _handler: ACPGroupEventHandler | null = null;
    private _cursorStore: CursorStore | null = null;
    private _reqTimeout: number = 30000; // ms
    private _seqId: number = 0;

    constructor(agentId: string, sendFunc: SendFunc) {
        this._agentId = agentId;
        this._sendFunc = sendFunc;
    }

    // -- Configuration --

    setEventHandler(handler: ACPGroupEventHandler): void {
        this._handler = handler;
    }

    setCursorStore(store: CursorStore): void {
        this._cursorStore = store;
    }

    getCursorStore(): CursorStore | null {
        return this._cursorStore;
    }

    setTimeout(timeout: number): void {
        this._reqTimeout = timeout;
    }

    // -- Request / Response --

    private _nextRequestId(): string {
        this._seqId++;
        return `${this._agentId}-${Date.now()}-${this._seqId}`;
    }

    /**
     * Send a request and wait for response (Promise-based).
     * Rejects with TimeoutError on timeout, Error on send failure.
     */
    async sendRequest(
        targetAid: string,
        groupId: string,
        action: string,
        params?: Record<string, any> | null,
        timeout?: number,
    ): Promise<GroupResponse> {
        const reqId = this._nextRequestId();
        const req = buildGroupRequest(action, reqId, groupId, params);
        const payload = JSON.stringify(req);

        const effectiveTimeout = timeout ?? this._reqTimeout;

        // logger.log(`[GroupClient] >>> sendRequest: action=${action} group=${groupId} reqId=${reqId} target=${targetAid}`);
        // logger.log(`[GroupClient] >>> payload: ${payload}`);

        return new Promise<GroupResponse>((resolve, reject) => {
            const timer = setTimeout(() => {
                this._pendingReqs.delete(reqId);
                logger.error(`[GroupClient] !!! TIMEOUT: action=${action} group=${groupId} reqId=${reqId}, pendingReqs remaining: [${Array.from(this._pendingReqs.keys()).join(', ')}]`);
                reject(new Error(`request timeout: action=${action} group=${groupId}`));
            }, effectiveTimeout);

            this._pendingReqs.set(reqId, { resolve, reject, timer });

            try {
                this._sendFunc(targetAid, payload);
                // logger.log(`[GroupClient] >>> sendFunc called OK`);
            } catch (e) {
                clearTimeout(timer);
                this._pendingReqs.delete(reqId);
                logger.error(`[GroupClient] !!! sendFunc error:`, e);
                reject(e instanceof Error ? e : new Error(String(e)));
            }
        });
    }

    // -- Incoming message handling --

    /**
     * Handle an incoming ACP message (response or notification).
     * Called by the message dispatch chain in AgentCP.
     */
    handleIncoming(payload: string): void {
        let data: Record<string, any>;
        try {
            data = JSON.parse(payload);
        } catch (e) {
            logger.error(`[GroupClient] JSON.parse failed for incoming payload:`, e);
            return;
        }

        // Try as response (has request_id)
        const requestId = data.request_id ?? "";
        if (requestId) {
            const resp = parseGroupResponse(data);
            const pending = this._pendingReqs.get(requestId);
            if (pending) {
                clearTimeout(pending.timer);
                this._pendingReqs.delete(requestId);
                pending.resolve(resp);
                // 如果响应同时携带 event 字段，也要 dispatch 通知
                const event = data.event ?? "";
                if (event && this._handler != null) {
                    const notify = parseGroupNotify(data);
                    dispatchAcpNotify(this._handler, notify);
                }
                return;
            } else {
                logger.warn(`[GroupClient] !!! request_id=${requestId} NOT found in pendingReqs. Current pending: [${Array.from(this._pendingReqs.keys()).join(', ')}]`);
            }
        }

        // Try as notification (has event field)
        const event = data.event ?? "";
        if (event) {
            const notify = parseGroupNotify(data);
            if (this._handler != null) {
                dispatchAcpNotify(this._handler, notify);
            } else {
                logger.warn(`[GroupClient] !!! notification event="${event}" dropped: no event handler registered. Call setEventHandler() first.`);
            }
            return;
        }

        // Handle action-based push messages from group.ap (e.g. message_push)
        // These have action field but no event/request_id, need to be mapped to notification events
        const action = data.action ?? "";
        if (action === "message_push" && data.data) {
            logger.log(`[GroupClient] message_push -> group_message: group=${data.group_id} msg_id=${data.data.msg_id}`);
            const msgData = data.data;
            const notify: GroupNotify = {
                action: "group_notify",
                group_id: data.group_id ?? "",
                event: NOTIFY_GROUP_MESSAGE,
                data: {
                    msg_id: msgData.msg_id ?? 0,
                    sender: msgData.sender ?? "",
                    content: msgData.content ?? "",
                    content_type: msgData.content_type ?? "text",
                    timestamp: msgData.timestamp ?? 0,
                    metadata: msgData.metadata ?? null,
                },
                timestamp: msgData.timestamp ?? 0,
            };
            if (this._handler != null) {
                dispatchAcpNotify(this._handler, notify);
            } else {
                logger.warn(`[GroupClient] !!! message_push dropped: no event handler registered.`);
            }
            return;
        }

        if (action === "message_batch_push" && data.data) {
            const batch = data.data as GroupMessageBatch;
            logger.log(`[GroupClient] message_batch_push -> onGroupMessageBatch: group=${data.group_id} count=${batch.count} range=[${batch.start_msg_id}, ${batch.latest_msg_id}]`);
            if (this._handler != null) {
                this._handler.onGroupMessageBatch(data.group_id ?? "", batch);
            } else {
                logger.warn(`[GroupClient] !!! message_batch_push dropped: no event handler registered.`);
            }
            return;
        }

        logger.warn(`[GroupClient] !!! unhandled incoming message: no request_id and no event field`, JSON.stringify(data).substring(0, 300));
    }

    // -- Lifecycle --

    /**
     * Close client, cancel all pending requests.
     */
    close(): void {
        for (const [reqId, pending] of this._pendingReqs) {
            clearTimeout(pending.timer);
            pending.reject(new Error(`request cancelled: reqId=${reqId}`));
        }
        this._pendingReqs.clear();

        if (this._cursorStore != null) {
            try {
                this._cursorStore.close();
            } catch (e) {
                logger.error("[ACPGroupClient] cursor store close error:", e);
            }
        }
    }
}
