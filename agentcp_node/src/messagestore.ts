import * as fs from 'fs';
import * as path from 'path';
import { CertAndKeyStore } from './datamanager';
import { logger } from './utils';

// ---- 类型定义 ----

export type MessageItem = {
    type: 'sent' | 'received';
    content: string;
    from?: string;
    to?: string;
    timestamp: number;
};

export interface SessionRecord {
    sessionId: string;
    identifyingCode: string;
    peerAid: string;
    ownerAid: string;
    type: 'outgoing' | 'incoming';
    createdAt: number;
    lastMessageAt: number;
    messageCount: number;
    closed: boolean;
}

export interface Session extends SessionRecord {
    messages: MessageItem[];
}

export interface SessionSummary {
    sessionId: string;
    peerAid: string;
    ownerAid: string;
    type: 'outgoing' | 'incoming';
    lastMessageAt: number;
    messageCount: number;
    createdAt: number;
    lastMessage: string;
    closed: boolean;
}

// ---- MessageStore 类 ----

export class MessageStore {
    private persistMessages: boolean;
    private basePath: string;
    private maxMessagesPerSession: number;
    private sessions: Map<string, Session> = new Map();
    constructor(options: {
        persistMessages: boolean;
        basePath: string;
        maxMessagesPerSession?: number;
    }) {
        this.persistMessages = options.persistMessages;
        this.basePath = options.basePath;
        this.maxMessagesPerSession = options.maxMessagesPerSession ?? 1000;
    }

    // ---- 路径工具 ----

    private getSessionsDir(aid: string): string {
        return path.join(this.basePath, 'AIDs', aid, 'sessions');
    }

    private getIndexPath(aid: string): string {
        return path.join(this.getSessionsDir(aid), '_index.json');
    }

    private getSessionFilePath(aid: string, sessionId: string): string {
        return path.join(this.getSessionsDir(aid), `${sessionId}.jsonl`);
    }

    private ensureDir(dir: string): void {
        if (!fs.existsSync(dir)) {
            fs.mkdirSync(dir, { recursive: true });
        }
    }

    // ---- 核心操作 ----

    async loadSessionsForAid(ownerAid: string): Promise<void> {
        // 先 flush 当前内存中所有 AID 的数据
        await this.flushAll();
        // 清空内存
        this.sessions.clear();

        if (!this.persistMessages) return;

        const indexPath = this.getIndexPath(ownerAid);

        // 检测是否需要从旧格式迁移
        if (!fs.existsSync(indexPath)) {
            await this.migrateFromLegacy(ownerAid);
            // 迁移已将数据加载到内存并写入文件，无需再读
            if (this.sessions.size > 0) return;
        }

        // 从文件夹结构加载
        if (fs.existsSync(indexPath)) {
            try {
                const raw = fs.readFileSync(indexPath, 'utf-8');
                const records: SessionRecord[] = JSON.parse(raw);
                if (Array.isArray(records)) {
                    for (const r of records) {
                        const msgs = this.readMessagesFromFile(ownerAid, r.sessionId);
                        this.sessions.set(r.sessionId, { ...r, messages: msgs });
                    }
                }
            } catch (e) {
                logger.error('[MessageStore] 加载索引失败:', e);
            }
        }
    }

    /** 从 JSONL 文件读取消息列表 */
    private readMessagesFromFile(ownerAid: string, sessionId: string): MessageItem[] {
        const msgPath = this.getSessionFilePath(ownerAid, sessionId);
        if (!fs.existsSync(msgPath)) return [];
        try {
            const raw = fs.readFileSync(msgPath, 'utf-8');
            // 兼容旧 JSON 数组格式
            const trimmed = raw.trimStart();
            if (trimmed.startsWith('[')) {
                const parsed = JSON.parse(raw);
                if (Array.isArray(parsed)) return parsed;
                return [];
            }
            // JSONL 格式：每行一个 JSON 对象
            const msgs: MessageItem[] = [];
            for (const line of raw.split('\n')) {
                const l = line.trim();
                if (!l) continue;
                try {
                    msgs.push(JSON.parse(l));
                } catch (e) {
                    logger.error('[MessageStore] 解析消息行失败:', e);
                }
            }
            return msgs;
        } catch {
            return [];
        }
    }
    private async migrateFromLegacy(ownerAid: string): Promise<void> {
        try {
            const records: SessionRecord[] | null = await CertAndKeyStore.getData(`sessions_${ownerAid}`);
            if (!records || !Array.isArray(records) || records.length === 0) return;

            this.ensureDir(this.getSessionsDir(ownerAid));

            for (const r of records) {
                const msgs: MessageItem[] | null = await CertAndKeyStore.getData(`msgs_${r.sessionId}`);
                const messages = msgs && Array.isArray(msgs) ? msgs : [];
                this.sessions.set(r.sessionId, { ...r, messages });
            }

            // 写入新文件夹结构
            await this.flush(ownerAid);
            logger.log(`[MessageStore] 已从旧格式迁移 ${records.length} 个会话 (AID: ${ownerAid})`);
        } catch (e) {
            logger.error('[MessageStore] 迁移旧数据失败:', e);
        }
    }

    getOrCreateSession(
        sessionId: string,
        identifyingCode: string,
        peerAid: string,
        type: 'outgoing' | 'incoming',
        ownerAid: string
    ): Session {
        let session = this.sessions.get(sessionId);
        if (!session) {
            session = {
                sessionId,
                identifyingCode,
                peerAid,
                ownerAid,
                type,
                messages: [],
                createdAt: Date.now(),
                lastMessageAt: Date.now(),
                messageCount: 0,
                closed: false,
            };
            this.sessions.set(sessionId, session);
            // 异步持久化索引（不阻塞）
            this.flushIndex(ownerAid).catch(() => {});
        }
        return session;
    }

    addMessageToSession(sessionId: string, msg: MessageItem): void {
        const session = this.sessions.get(sessionId);
        if (session) {
            session.messages.push(msg);
            const truncated = session.messages.length > this.maxMessagesPerSession;
            if (truncated) {
                session.messages.shift();
            }
            session.lastMessageAt = msg.timestamp;
            session.messageCount = session.messages.length;
            // 检测会话关闭消息
            if (msg.content && msg.content.includes('[END] Session closed')) {
                session.closed = true;
            }
            // 异步持久化
            this.flushIndex(session.ownerAid).catch(() => {});
            if (truncated) {
                // 截断后需要重写整个文件
                this.flushSession(session.ownerAid, sessionId).catch(() => {});
            } else {
                // 正常情况只追加一行
                this.appendMessage(session.ownerAid, sessionId, msg);
            }
        }
    }
    getSessionList(ownerAid: string): SessionSummary[] {
        return Array.from(this.sessions.values())
            .filter(s => s.ownerAid === ownerAid)
            .map(s => {
                const firstMsg = s.messages.length > 0 ? s.messages[0].content : '';
                return {
                    sessionId: s.sessionId,
                    peerAid: s.peerAid,
                    ownerAid: s.ownerAid,
                    type: s.type,
                    lastMessageAt: s.lastMessageAt,
                    messageCount: s.messages.length,
                    createdAt: s.createdAt,
                    lastMessage: firstMsg,
                    closed: s.closed || false,
                };
            })
            .sort((a, b) => b.lastMessageAt - a.lastMessageAt);
    }

    hasSession(sessionId: string): boolean {
        return this.sessions.has(sessionId);
    }

    getSession(sessionId: string): Session | null {
        return this.sessions.get(sessionId) || null;
    }

    // ---- 持久化 ----

    /** 只写索引文件 */
    async flushIndex(ownerAid: string): Promise<void> {
        if (!this.persistMessages) return;

        const sessionsDir = this.getSessionsDir(ownerAid);
        this.ensureDir(sessionsDir);

        const records: SessionRecord[] = [];
        for (const s of this.sessions.values()) {
            if (s.ownerAid !== ownerAid) continue;
            records.push({
                sessionId: s.sessionId,
                identifyingCode: s.identifyingCode,
                peerAid: s.peerAid,
                ownerAid: s.ownerAid,
                type: s.type,
                createdAt: s.createdAt,
                lastMessageAt: s.lastMessageAt,
                messageCount: s.messages.length,
                closed: s.closed || false,
            });
        }

        const indexPath = this.getIndexPath(ownerAid);
        try {
            fs.writeFileSync(indexPath, JSON.stringify(records, null, 2));
        } catch (e) {
            logger.error('[MessageStore] 写入索引失败:', e);
        }
    }

    /** 全量重写单个会话的消息文件（JSONL 格式） */
    async flushSession(ownerAid: string, sessionId: string): Promise<void> {
        if (!this.persistMessages) return;

        const session = this.sessions.get(sessionId);
        if (!session || session.ownerAid !== ownerAid) return;

        const sessionsDir = this.getSessionsDir(ownerAid);
        this.ensureDir(sessionsDir);

        const msgPath = this.getSessionFilePath(ownerAid, sessionId);
        try {
            const lines = session.messages.map(m => JSON.stringify(m)).join('\n');
            fs.writeFileSync(msgPath, lines ? lines + '\n' : '');
        } catch (e) {
            logger.error(`[MessageStore] 写入会话文件失败 (${sessionId}):`, e);
        }
    }

    /** 追加单条消息到 JSONL 文件 */
    private appendMessage(ownerAid: string, sessionId: string, msg: MessageItem): void {
        if (!this.persistMessages) return;

        const sessionsDir = this.getSessionsDir(ownerAid);
        this.ensureDir(sessionsDir);

        const msgPath = this.getSessionFilePath(ownerAid, sessionId);
        try {
            fs.appendFileSync(msgPath, JSON.stringify(msg) + '\n');
        } catch (e) {
            logger.error(`[MessageStore] 追加消息失败 (${sessionId}):`, e);
        }
    }

    /** 全量写入指定 AID 的索引 + 所有会话消息文件 */
    async flush(ownerAid: string): Promise<void> {
        if (!this.persistMessages) return;

        await this.flushIndex(ownerAid);
        for (const s of this.sessions.values()) {
            if (s.ownerAid === ownerAid) {
                await this.flushSession(ownerAid, s.sessionId);
            }
        }
    }

    async flushAll(): Promise<void> {
        if (!this.persistMessages) return;
        const owners = new Set<string>();
        for (const s of this.sessions.values()) {
            owners.add(s.ownerAid);
        }
        for (const owner of owners) {
            await this.flush(owner);
        }
    }

    async deleteSession(sessionId: string): Promise<boolean> {
        const session = this.sessions.get(sessionId);
        if (!session) return false;

        this.sessions.delete(sessionId);
        
        if (this.persistMessages) {
            const msgPath = this.getSessionFilePath(session.ownerAid, sessionId);
            if (fs.existsSync(msgPath)) {
                try { fs.unlinkSync(msgPath); } catch (e) { logger.error('删除会话文件失败:', e); }
            }
            await this.flushIndex(session.ownerAid);
        }
        return true;
    }

    async deletePeer(peerAid: string, ownerAid: string): Promise<number> {
        const sessionsToDelete: string[] = [];
        for (const s of this.sessions.values()) {
            if (s.ownerAid === ownerAid && s.peerAid === peerAid) {
                sessionsToDelete.push(s.sessionId);
            }
        }
        
        let count = 0;
        for (const sid of sessionsToDelete) {
            if (await this.deleteSession(sid)) {
                count++;
            }
        }
        return count;
    }
}
