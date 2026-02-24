/**
 * Cursor store for local persistence of group message/event cursors.
 * Mirrors Python SDK: agentcp/group/cursor_store.py
 */

import { isNodeEnvironment } from '../websocket';
import { logger } from '../utils';

/**
 * Abstract interface for cursor persistence.
 */
export interface CursorStore {
    saveMsgCursor(groupId: string, msgCursor: number): void;
    saveEventCursor(groupId: string, eventCursor: number): void;
    loadCursor(groupId: string): [number, number]; // [msg_cursor, event_cursor]
    removeCursor(groupId: string): void;
    flush(): void;
    close(): void;
}

/**
 * In-memory + JSON file cursor store.
 *
 * Monotonic cursor advancement (never goes backward).
 * file_path="" means pure in-memory mode.
 * Node.js environment uses fs for file persistence; browser is pure in-memory.
 */
export class LocalCursorStore implements CursorStore {
    private _cursors: Record<string, { msg_cursor: number; event_cursor: number }> = {};
    private _filePath: string;
    private _dirty: boolean = false;

    constructor(filePath: string = "") {
        this._filePath = filePath;
        if (filePath && isNodeEnvironment) {
            this._load();
        }
    }

    saveMsgCursor(groupId: string, msgCursor: number): void {
        if (!this._cursors[groupId]) {
            this._cursors[groupId] = { msg_cursor: 0, event_cursor: 0 };
        }
        if (msgCursor > this._cursors[groupId].msg_cursor) {
            this._cursors[groupId].msg_cursor = msgCursor;
            this._dirty = true;
        }
    }

    saveEventCursor(groupId: string, eventCursor: number): void {
        if (!this._cursors[groupId]) {
            this._cursors[groupId] = { msg_cursor: 0, event_cursor: 0 };
        }
        if (eventCursor > this._cursors[groupId].event_cursor) {
            this._cursors[groupId].event_cursor = eventCursor;
            this._dirty = true;
        }
    }

    loadCursor(groupId: string): [number, number] {
        const entry = this._cursors[groupId];
        if (!entry) {
            return [0, 0];
        }
        return [entry.msg_cursor, entry.event_cursor];
    }

    removeCursor(groupId: string): void {
        if (groupId in this._cursors) {
            delete this._cursors[groupId];
            this._dirty = true;
        }
    }

    flush(): void {
        if (!this._filePath || !isNodeEnvironment) {
            return;
        }
        if (!this._dirty) {
            return;
        }
        this._write();
    }

    close(): void {
        this.flush();
    }

    private _write(): void {
        try {
            const fs = require('fs');
            fs.writeFileSync(this._filePath, JSON.stringify(this._cursors, null, 2), 'utf-8');
            this._dirty = false;
        } catch (e) {
            logger.error(`[CursorStore] write to ${this._filePath} failed:`, e);
        }
    }

    private _load(): void {
        try {
            const fs = require('fs');
            if (!fs.existsSync(this._filePath)) {
                return;
            }
            const content = fs.readFileSync(this._filePath, 'utf-8');
            if (content) {
                this._cursors = JSON.parse(content);
            }
        } catch (e) {
            console.debug(`[CursorStore] load from ${this._filePath} failed:`, e);
        }
    }
}
