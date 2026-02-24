/**
 * Group message/event persistent store.
 * Stores group messages and events in JSONL format, similar to MessageStore.
 *
 * Storage layout:
 *   AIDs/{aid}/groups/_index.json
 *   AIDs/{aid}/groups/{group_id}/messages.jsonl
 *   AIDs/{aid}/groups/{group_id}/events.jsonl
 */

import { isNodeEnvironment } from '../websocket';
import { GroupMessage, GroupEvent } from './types';
import { logger } from '../utils';

export interface GroupRecord {
    groupId: string;
    groupName: string;
    targetAid: string;
    lastMsgId: number;
    lastEventId: number;
    messageCount: number;
    eventCount: number;
    lastMessageAt: number;
    joinedAt: number;
}

interface GroupData {
    record: GroupRecord;
    messages: GroupMessage[];
    events: GroupEvent[];
}

export class GroupMessageStore {
    private persistMessages: boolean;
    private basePath: string;
    private ownerAid: string = '';
    private maxMessagesPerGroup: number;
    private maxEventsPerGroup: number;
    private groups: Map<string, GroupData> = new Map();
    private _indexDirty: boolean = false;

    constructor(options: {
        persistMessages: boolean;
        basePath: string;
        maxMessagesPerGroup?: number;
        maxEventsPerGroup?: number;
    }) {
        this.persistMessages = options.persistMessages;
        this.basePath = options.basePath;
        this.maxMessagesPerGroup = options.maxMessagesPerGroup ?? 5000;
        this.maxEventsPerGroup = options.maxEventsPerGroup ?? 2000;
    }

    // ---- path helpers ----

    private getGroupsDir(aid: string): string {
        const path = require('path');
        return path.join(this.basePath, 'AIDs', aid, 'groups');
    }

    private getIndexPath(aid: string): string {
        const path = require('path');
        return path.join(this.getGroupsDir(aid), '_index.json');
    }

    private getGroupDir(aid: string, groupId: string): string {
        const path = require('path');
        return path.join(this.getGroupsDir(aid), groupId);
    }

    private getMessagesPath(aid: string, groupId: string): string {
        const path = require('path');
        return path.join(this.getGroupDir(aid, groupId), 'messages.jsonl');
    }

    private getEventsPath(aid: string, groupId: string): string {
        const path = require('path');
        return path.join(this.getGroupDir(aid, groupId), 'events.jsonl');
    }

    private ensureDir(dir: string): void {
        if (!isNodeEnvironment) return;
        const fs = require('fs');
        if (!fs.existsSync(dir)) {
            fs.mkdirSync(dir, { recursive: true });
        }
    }

    // ---- load ----

    async loadGroupsForAid(ownerAid: string): Promise<void> {
        await this.flushAll();
        this.groups.clear();
        this.ownerAid = ownerAid;

        if (!this.persistMessages || !isNodeEnvironment) return;

        const fs = require('fs');
        const indexPath = this.getIndexPath(ownerAid);
        if (!fs.existsSync(indexPath)) return;

        try {
            const raw = fs.readFileSync(indexPath, 'utf-8');
            const records: GroupRecord[] = JSON.parse(raw);
            if (!Array.isArray(records)) return;
            for (const r of records) {
                const messages = this.readJsonl<GroupMessage>(
                    this.getMessagesPath(ownerAid, r.groupId));
                const events = this.readJsonl<GroupEvent>(
                    this.getEventsPath(ownerAid, r.groupId));
                this.groups.set(r.groupId, { record: r, messages, events });
            }
        } catch (e) {
            logger.error('[GroupMessageStore] 加载索引失败:', e);
        }
    }

    private readJsonl<T>(filePath: string): T[] {
        if (!isNodeEnvironment) return [];
        const fs = require('fs');
        if (!fs.existsSync(filePath)) return [];
        try {
            const raw: string = fs.readFileSync(filePath, 'utf-8');
            const items: T[] = [];
            for (const line of raw.split('\n')) {
                const l = line.trim();
                if (!l) continue;
                try { items.push(JSON.parse(l)); } catch {}
            }
            return items;
        } catch {
            return [];
        }
    }

    // ---- group record management ----

    getOrCreateGroup(groupId: string, targetAid: string, groupName: string = ''): GroupRecord {
        let data = this.groups.get(groupId);
        if (!data) {
            const record: GroupRecord = {
                groupId, groupName, targetAid,
                lastMsgId: 0, lastEventId: 0,
                messageCount: 0, eventCount: 0,
                lastMessageAt: 0, joinedAt: Date.now(),
            };
            data = { record, messages: [], events: [] };
            this.groups.set(groupId, data);
            this._indexDirty = true;
            this.flushIndexAsync();
        }
        return data.record;
    }

    getGroupList(): GroupRecord[] {
        return Array.from(this.groups.values())
            .map(d => ({ ...d.record }))
            .sort((a, b) => b.lastMessageAt - a.lastMessageAt);
    }

    getGroup(groupId: string): GroupRecord | null {
        const data = this.groups.get(groupId);
        return data ? { ...data.record } : null;
    }

    async deleteGroup(groupId: string): Promise<boolean> {
        const data = this.groups.get(groupId);
        if (!data) return false;
        this.groups.delete(groupId);
        this._indexDirty = true;

        if (this.persistMessages && isNodeEnvironment && this.ownerAid) {
            const fs = require('fs');
            const dir = this.getGroupDir(this.ownerAid, groupId);
            try {
                if (fs.existsSync(dir)) {
                    fs.rmSync(dir, { recursive: true, force: true });
                }
            } catch (e) {
                logger.error(`[GroupMessageStore] 删除群目录失败 (${groupId}):`, e);
            }
            await this.flushIndex();
        }
        return true;
    }

    // ---- message storage ----

    addMessage(groupId: string, msg: GroupMessage): void {
        const data = this.groups.get(groupId);
        if (!data) return;
        // dedup: skip if msg_id already seen
        if (msg.msg_id <= data.record.lastMsgId) return;

        data.messages.push(msg);
        data.record.lastMsgId = msg.msg_id;
        data.record.messageCount = data.messages.length;
        data.record.lastMessageAt = msg.timestamp || Date.now();
        this._indexDirty = true;

        // truncate if over limit
        if (data.messages.length > this.maxMessagesPerGroup) {
            const excess = data.messages.length - this.maxMessagesPerGroup;
            data.messages.splice(0, excess);
            data.record.messageCount = data.messages.length;
            this.flushMessages(groupId);
        } else {
            this.appendJsonl(
                this.getMessagesPath(this.ownerAid, groupId), msg);
        }
        this.flushIndexAsync();
    }

    addMessages(groupId: string, msgs: GroupMessage[]): void {
        const data = this.groups.get(groupId);
        if (!data) {
            logger.warn(`[GroupMessageStore] addMessages: group=${groupId} NOT FOUND in store! Available groups: [${Array.from(this.groups.keys()).join(', ')}]`);
            return;
        }

        if (!msgs || msgs.length === 0) return;

        logger.log(`[GroupMessageStore] addMessages: group=${groupId} incoming=${msgs.length} currentLastMsgId=${data.record.lastMsgId} incomingMsgIds=[${msgs.map(m => m.msg_id).join(',')}]`);

        let added = 0;
        for (const msg of msgs) {
            if (msg.msg_id <= data.record.lastMsgId) {
                logger.log(`[GroupMessageStore] addMessages: SKIP duplicate msg_id=${msg.msg_id} <= lastMsgId=${data.record.lastMsgId}`);
                continue;
            }
            data.messages.push(msg);
            data.record.lastMsgId = msg.msg_id;
            data.record.lastMessageAt = msg.timestamp || Date.now();
            added++;
        }
        logger.log(`[GroupMessageStore] addMessages result: group=${groupId} added=${added}/${msgs.length} newLastMsgId=${data.record.lastMsgId} totalMessages=${data.messages.length}`);
        if (added === 0) return;

        data.record.messageCount = data.messages.length;
        this._indexDirty = true;

        if (data.messages.length > this.maxMessagesPerGroup) {
            const excess = data.messages.length - this.maxMessagesPerGroup;
            data.messages.splice(0, excess);
            data.record.messageCount = data.messages.length;
            this.flushMessages(groupId);
        } else {
            this.flushMessages(groupId);
        }
        this.flushIndexAsync();
    }

    getMessages(groupId: string, options?: {
        afterMsgId?: number;
        beforeMsgId?: number;
        limit?: number;
    }): GroupMessage[] {
        const data = this.groups.get(groupId);
        if (!data) return [];

        let result = data.messages;
        if (options?.afterMsgId) {
            result = result.filter(m => m.msg_id > options.afterMsgId!);
        }
        if (options?.beforeMsgId) {
            result = result.filter(m => m.msg_id < options.beforeMsgId!);
        }
        if (options?.limit && options.limit > 0) {
            result = result.slice(-options.limit);
        }
        return result;
    }

    getLatestMessages(groupId: string, limit: number = 50): GroupMessage[] {
        const data = this.groups.get(groupId);
        if (!data) return [];
        return data.messages.slice(-limit);
    }

    // ---- event storage ----

    addEvent(groupId: string, evt: GroupEvent): void {
        const data = this.groups.get(groupId);
        if (!data) return;
        if (evt.event_id <= data.record.lastEventId) return;

        data.events.push(evt);
        data.record.lastEventId = evt.event_id;
        data.record.eventCount = data.events.length;
        this._indexDirty = true;

        if (data.events.length > this.maxEventsPerGroup) {
            const excess = data.events.length - this.maxEventsPerGroup;
            data.events.splice(0, excess);
            data.record.eventCount = data.events.length;
            this.flushEvents(groupId);
        } else {
            this.appendJsonl(
                this.getEventsPath(this.ownerAid, groupId), evt);
        }
        this.flushIndexAsync();
    }

    addEvents(groupId: string, evts: GroupEvent[]): void {
        const data = this.groups.get(groupId);
        if (!data) return;

        let added = 0;
        for (const evt of evts) {
            if (evt.event_id <= data.record.lastEventId) continue;
            data.events.push(evt);
            data.record.lastEventId = evt.event_id;
            added++;
        }
        if (added === 0) return;

        data.record.eventCount = data.events.length;
        this._indexDirty = true;

        if (data.events.length > this.maxEventsPerGroup) {
            const excess = data.events.length - this.maxEventsPerGroup;
            data.events.splice(0, excess);
            data.record.eventCount = data.events.length;
        }
        this.flushEvents(groupId);
        this.flushIndexAsync();
    }

    getEvents(groupId: string, options?: {
        afterEventId?: number;
        limit?: number;
    }): GroupEvent[] {
        const data = this.groups.get(groupId);
        if (!data) return [];

        let result = data.events;
        if (options?.afterEventId) {
            result = result.filter(e => e.event_id > options.afterEventId!);
        }
        if (options?.limit && options.limit > 0) {
            result = result.slice(-options.limit);
        }
        return result;
    }

    // ---- persistence ----

    private appendJsonl(filePath: string, item: any): void {
        if (!this.persistMessages || !isNodeEnvironment || !this.ownerAid) return;
        const fs = require('fs');
        const path = require('path');
        this.ensureDir(path.dirname(filePath));
        try {
            fs.appendFileSync(filePath, JSON.stringify(item) + '\n');
        } catch (e) {
            logger.error(`[GroupMessageStore] 追加写入失败 (${filePath}):`, e);
        }
    }

    private writeJsonl(filePath: string, items: any[]): void {
        if (!this.persistMessages || !isNodeEnvironment || !this.ownerAid) return;
        const fs = require('fs');
        const path = require('path');
        this.ensureDir(path.dirname(filePath));
        try {
            const lines = items.map(i => JSON.stringify(i)).join('\n');
            fs.writeFileSync(filePath, lines ? lines + '\n' : '');
        } catch (e) {
            logger.error(`[GroupMessageStore] 全量写入失败 (${filePath}):`, e);
        }
    }

    private flushMessages(groupId: string): void {
        const data = this.groups.get(groupId);
        if (!data || !this.ownerAid) return;
        this.writeJsonl(
            this.getMessagesPath(this.ownerAid, groupId), data.messages);
    }

    private flushEvents(groupId: string): void {
        const data = this.groups.get(groupId);
        if (!data || !this.ownerAid) return;
        this.writeJsonl(
            this.getEventsPath(this.ownerAid, groupId), data.events);
    }

    private flushIndexAsync(): void {
        this.flushIndex().catch(() => {});
    }

    async flushIndex(): Promise<void> {
        if (!this.persistMessages || !isNodeEnvironment || !this.ownerAid) return;
        if (!this._indexDirty) return;

        const fs = require('fs');
        const dir = this.getGroupsDir(this.ownerAid);
        this.ensureDir(dir);

        const records: GroupRecord[] = Array.from(this.groups.values())
            .map(d => d.record);
        try {
            fs.writeFileSync(this.getIndexPath(this.ownerAid),
                JSON.stringify(records, null, 2));
            this._indexDirty = false;
        } catch (e) {
            logger.error('[GroupMessageStore] 写入索引失败:', e);
        }
    }

    async flush(ownerAid: string): Promise<void> {
        if (!this.persistMessages || !isNodeEnvironment) return;
        this.ownerAid = ownerAid;
        await this.flushIndex();
        for (const [groupId, data] of this.groups) {
            this.flushMessages(groupId);
            this.flushEvents(groupId);
        }
    }

    async flushAll(): Promise<void> {
        if (!this.ownerAid) return;
        await this.flush(this.ownerAid);
    }

    async close(): Promise<void> {
        await this.flushAll();
        this.groups.clear();
    }
}
