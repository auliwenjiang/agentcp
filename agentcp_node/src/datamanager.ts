import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';

// 默认数据目录：用户主目录下的 acp 文件夹
const DEFAULT_ACP_DIR = path.join(os.homedir(), 'acp');
export { DEFAULT_ACP_DIR };

// 本地 logger（避免与 utils.ts 循环依赖）
function _ts(): string {
    const n = new Date();
    const y = n.getFullYear();
    const m = String(n.getMonth() + 1).padStart(2, '0');
    const d = String(n.getDate()).padStart(2, '0');
    const h = String(n.getHours()).padStart(2, '0');
    const min = String(n.getMinutes()).padStart(2, '0');
    const s = String(n.getSeconds()).padStart(2, '0');
    return `${y}/${m}/${d} ${h}:${min}:${s}`;
}
const logger = {
    log: (...args: any[]) => console.log(`[${_ts()}]`, ...args),
    warn: (...args: any[]) => console.warn(`[${_ts()}]`, ...args),
    error: (...args: any[]) => console.error(`[${_ts()}]`, ...args),
};

// 统一的环境检测函数
const isNodeEnvironment = typeof process !== 'undefined' &&
    process.versions != null &&
    process.versions.node != null;

// Node.js 环境下的文件存储实现
class NodeStorage {
    private static dataDir = path.join(DEFAULT_ACP_DIR, '.acp-data');
    private static dataFile = path.join(NodeStorage.dataDir, 'storage.json');
    private static cache: Record<string, any> = {};
    private static initialized = false;

    private static init() {
        if (this.initialized) return;
        try {
            if (!fs.existsSync(this.dataDir)) {
                fs.mkdirSync(this.dataDir, { recursive: true });
            }
            if (fs.existsSync(this.dataFile)) {
                const data = fs.readFileSync(this.dataFile, 'utf-8');
                this.cache = JSON.parse(data);
            }
            this.initialized = true;
        } catch (e) {
            logger.error('NodeStorage init error:', e);
            this.cache = {};
            this.initialized = true;
        }
    }

    private static save() {
        try {
            fs.writeFileSync(this.dataFile, JSON.stringify(this.cache, null, 2));
        } catch (e) {
            logger.error('NodeStorage save error:', e);
        }
    }

    static async setItem(key: string, value: string): Promise<void> {
        this.init();
        this.cache[key] = value;
        this.save();
    }

    static async getItem(key: string): Promise<string | null> {
        this.init();
        return this.cache[key] ?? null;
    }
}

// 动态选择存储后端
let AsyncStorage: { setItem: (key: string, value: string) => Promise<void>; getItem: (key: string) => Promise<string | null> };

if (isNodeEnvironment) {
    AsyncStorage = NodeStorage;
} else {
    // 浏览器/React Native 环境
    try {
        AsyncStorage = require('@react-native-async-storage/async-storage').default;
    } catch (e) {
        // 如果加载失败，使用内存存储作为后备
        logger.warn('AsyncStorage not available, using memory storage');
        const memoryStore: Record<string, string> = {};
        AsyncStorage = {
            setItem: async (key: string, value: string) => { memoryStore[key] = value; },
            getItem: async (key: string) => memoryStore[key] ?? null
        };
    }
}

export class CertAndKeyStore {
    static aidKey = 'currentAidKey'
    private static basePath: string = DEFAULT_ACP_DIR;

    static setBasePath(p: string) {
        this.basePath = p;
    }

    static getAIDsDir(): string {
        return path.join(this.basePath, 'AIDs');
    }

    // 存储数据（仍用 storage.json，用于会话/消息）
    static async storeData(key: string, value: any) {
        try {
            await AsyncStorage.setItem(key, JSON.stringify(value));
        } catch (e) {
            logger.error(e);
        }
    }
    // 获取数据（仍用 storage.json，用于会话/消息）
    static async getData(key: string): Promise<any> {
        try {
            const value = await AsyncStorage.getItem(key);
            if (value == null) return null;
            let parsed: any;
            try {
                parsed = JSON.parse(value);
            } catch (e) {
                parsed = value;
            }
            return parsed;
        } catch (e) {
            logger.error(e);
            return null;
        }
    }

    static async getGuestAid(): Promise<string | null> {
        try {
            const aids = await this.getAids();
            if (aids) {
                const firstGuestAid = aids.find((aid: string) => aid.startsWith('guest'));
                if (firstGuestAid) {
                    return firstGuestAid;
                }
            }
            return null;
        } catch (e) {
            logger.error('获取访客ID失败:', e);
            return null;
        }
    }

    static async getAids(): Promise<string[]> {
        try {
            const aidsDir = this.getAIDsDir();
            if (!fs.existsSync(aidsDir)) {
                return [];
            }
            const entries = fs.readdirSync(aidsDir, { withFileTypes: true });
            return entries.filter(e => {
                if (!e.isDirectory()) return false;
                const aidName = e.name;
                const keyPath = path.join(aidsDir, aidName, 'private', `${aidName}.key`);
                const crtPath = path.join(aidsDir, aidName, 'public', `${aidName}.crt`);
                return fs.existsSync(keyPath) && fs.existsSync(crtPath);
            }).map(e => e.name);
        } catch (e) {
            logger.error('扫描 AIDs 目录失败:', e);
            return [];
        }
    }

    static async saveAid(aid: string): Promise<void> {
        try {
            const privateDir = path.join(this.getAIDsDir(), aid, 'private');
            const publicDir = path.join(this.getAIDsDir(), aid, 'public');
            if (!fs.existsSync(privateDir)) {
                fs.mkdirSync(privateDir, { recursive: true });
            }
            if (!fs.existsSync(publicDir)) {
                fs.mkdirSync(publicDir, { recursive: true });
            }
        } catch (e) {
            logger.error('创建 AID 目录失败:', e);
        }
    }

    static async getCertificate(aid: string): Promise<string | null> {
        try {
            const certPath = path.join(this.getAIDsDir(), aid, 'public', `${aid}.crt`);
            if (fs.existsSync(certPath)) {
                return fs.readFileSync(certPath, 'utf-8');
            }
            return null;
        } catch (e) {
            logger.error('读取证书失败:', e);
            return null;
        }
    }

    static async saveCertificate(aid: string, cert: string) {
        await this.saveAid(aid);
        const certPath = path.join(this.getAIDsDir(), aid, 'public', `${aid}.crt`);
        fs.writeFileSync(certPath, cert, 'utf-8');
    }

    static async getCsr(aid: string): Promise<string | null> {
        try {
            const csrPath = path.join(this.getAIDsDir(), aid, 'private', `${aid}.csr`);
            if (fs.existsSync(csrPath)) {
                return fs.readFileSync(csrPath, 'utf-8');
            }
            return null;
        } catch (e) {
            logger.error('读取 CSR 失败:', e);
            return null;
        }
    }

    static async saveCsr(aid: string, csr: string) {
        await this.saveAid(aid);
        const csrPath = path.join(this.getAIDsDir(), aid, 'private', `${aid}.csr`);
        fs.writeFileSync(csrPath, csr, 'utf-8');
    }

    static async savePrivateKey(aid: string, key: string) {
        await this.saveAid(aid);
        const keyPath = path.join(this.getAIDsDir(), aid, 'private', `${aid}.key`);
        fs.writeFileSync(keyPath, key, 'utf-8');
    }

    static async getPrivateKey(aid: string): Promise<string | null> {
        try {
            const keyPath = path.join(this.getAIDsDir(), aid, 'private', `${aid}.key`);
            if (fs.existsSync(keyPath)) {
                return fs.readFileSync(keyPath, 'utf-8');
            }
            return null;
        } catch (error) {
            logger.error('获取私钥失败:', error);
            throw new Error('获取私钥失败');
        }
    }
}