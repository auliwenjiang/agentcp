import axios from 'axios';
import { logger } from './utils';

// 环境检测（与项目其他模块保持一致）
const isNodeEnvironment = typeof process !== 'undefined' &&
    process.versions != null &&
    process.versions.node != null;

/**
 * 文件同步状态
 */
export type FileSyncStatus = 'idle' | 'syncing' | 'completed' | 'error';

/**
 * 本地文件信息（用于同步请求）
 */
export interface LocalFileInfo {
    /** 相对路径 */
    full_path: string;
    /** 文件大小（字节） */
    size: number;
    /** 最后修改时间（毫秒时间戳） */
    last_modified: number;
    /** SHA256哈希值 */
    sha256: string;
}

/**
 * 同步结果接口
 */
export interface SyncResult {
    /** 同步状态 */
    status: FileSyncStatus;
    /** 成功上传的文件列表 */
    uploadedFiles: string[];
    /** 成功下载的文件列表 */
    downloadedFiles: string[];
    /** 上传失败的文件列表 */
    uploadFailedFiles: string[];
    /** 下载失败的文件列表 */
    downloadFailedFiles: string[];
    /** 错误信息 */
    error?: string;
}

/**
 * 文件同步配置
 */
export interface FileSyncConfig {
    /** API服务器地址 */
    apiUrl: string;
    /** 智能体ID */
    aid: string;
    /** 签名 */
    signature: string;
    /** 本地公共文件目录（Node.js 环境） */
    localDir?: string;
}

/**
 * 文件同步类
 * 提供公共文件的上传、下载和同步功能
 * 参考 Python 版本 agentcp 的 sync_public_files 实现
 */
export class FileSync {
    private config: FileSyncConfig;
    private status: FileSyncStatus = 'idle';
    private statusCallback: ((status: FileSyncStatus) => void) | null = null;
    private progressCallback: ((progress: { phase: string; current: number; total: number; fileName: string }) => void) | null = null;

    constructor(config: FileSyncConfig) {
        this.config = config;
    }

    /**
     * 计算文件的SHA256哈希值
     * @param filePath 文件路径
     * @returns 哈希值
     */
    private async calculateFileHash(filePath: string): Promise<string> {
        if (!isNodeEnvironment) {
            throw new Error('calculateFileHash 仅支持 Node.js 环境');
        }
        const crypto = require('crypto');
        const fs = require('fs');

        return new Promise((resolve, reject) => {
            const hash = crypto.createHash('sha256');
            const stream = fs.createReadStream(filePath);
            stream.on('data', (data: Buffer) => hash.update(data));
            stream.on('end', () => resolve(hash.digest('hex')));
            stream.on('error', reject);
        });
    }

    /**
     * 扫描文件夹，获取所有文件信息
     * @param folderPath 文件夹路径
     * @returns 文件信息列表
     */
    private async scanFolder(folderPath: string): Promise<LocalFileInfo[]> {
        if (!isNodeEnvironment) {
            return [];
        }

        const fs = require('fs');
        const path = require('path');
        const fileList: LocalFileInfo[] = [];

        if (!fs.existsSync(folderPath)) {
            return fileList;
        }

        const scanDir = async (dir: string) => {
            const entries = fs.readdirSync(dir, { withFileTypes: true });

            for (const entry of entries) {
                const fullPath = path.join(dir, entry.name);

                if (entry.isDirectory()) {
                    await scanDir(fullPath);
                } else if (entry.isFile()) {
                    try {
                        const stats = fs.statSync(fullPath);
                        const relativePath = path.relative(folderPath, fullPath).replace(/\\/g, '/');
                        const sha256 = await this.calculateFileHash(fullPath);

                        fileList.push({
                            full_path: relativePath,
                            size: stats.size,
                            last_modified: Math.floor(stats.mtimeMs),
                            sha256: sha256
                        });
                    } catch (error) {
                        logger.error(`处理文件 ${fullPath} 时出错:`, error);
                    }
                }
            }
        };

        await scanDir(folderPath);
        return fileList;
    }

    /**
     * 上传单个文件
     * @param localPath 本地完整路径
     * @param fileName 文件名（相对路径）
     * @returns 上传结果
     */
    private async uploadFile(localPath: string, fileName: string): Promise<{ success: boolean; url?: string }> {
        if (!isNodeEnvironment) {
            throw new Error('uploadFile 仅支持 Node.js 环境');
        }

        const fs = require('fs');
        const FormData = require('form-data');

        try {
            const form = new FormData();
            form.append('agent_id', this.config.aid);
            form.append('signature', this.config.signature);
            form.append('file_name', fileName);
            form.append('file', fs.createReadStream(localPath));

            const response = await axios.post(
                `${this.config.apiUrl}/upload_file`,
                form,
                {
                    headers: form.getHeaders(),
                    maxContentLength: Infinity,
                    maxBodyLength: Infinity
                }
            );

            if (response.status === 200) {
                return { success: true, url: response.data.url };
            }
            return { success: false };
        } catch (error) {
            logger.error(`上传文件失败 [${fileName}]:`, error);
            return { success: false };
        }
    }

    /**
     * 下载单个文件
     * @param fileName 文件名（相对路径）
     * @param savePath 保存路径
     * @returns 是否成功
     */
    private async downloadFile(fileName: string, savePath: string): Promise<boolean> {
        if (!isNodeEnvironment) {
            throw new Error('downloadFile 仅支持 Node.js 环境');
        }

        const fs = require('fs');
        const path = require('path');

        try {
            const downloadUrl = `${this.config.apiUrl}/download_file?file_name=${encodeURIComponent(fileName)}&agent_id=${encodeURIComponent(this.config.aid)}&signature=${encodeURIComponent(this.config.signature)}`;

            const response = await axios.get(downloadUrl, {
                responseType: 'stream'
            });

            // 确保目录存在
            const dir = path.dirname(savePath);
            if (!fs.existsSync(dir)) {
                fs.mkdirSync(dir, { recursive: true });
            }

            // 流式写入文件
            const writer = fs.createWriteStream(savePath);
            response.data.pipe(writer);

            return new Promise((resolve, reject) => {
                writer.on('finish', () => resolve(true));
                writer.on('error', (err: Error) => {
                    logger.error(`写入文件失败 [${fileName}]:`, err);
                    resolve(false);
                });
            });
        } catch (error) {
            logger.error(`下载文件失败 [${fileName}]:`, error);
            return false;
        }
    }

    /**
     * 更新同步状态
     */
    private updateStatus(status: FileSyncStatus): void {
        this.status = status;
        if (this.statusCallback) {
            this.statusCallback(status);
        }
    }

    /**
     * 触发进度回调
     */
    private emitProgress(phase: string, current: number, total: number, fileName: string): void {
        if (this.progressCallback) {
            this.progressCallback({ phase, current, total, fileName });
        }
    }

    /**
     * 同步公共文件
     * 参考 Python 版本实现：
     * 1. 扫描本地文件夹，获取文件列表
     * 2. 发送文件列表到服务器，获取需要上传/下载的文件
     * 3. 上传需要上传的文件
     * 4. 下载需要下载的文件
     * @returns 同步结果
     */
    public async syncPublicFiles(): Promise<SyncResult> {
        const result: SyncResult = {
            status: 'idle',
            uploadedFiles: [],
            downloadedFiles: [],
            uploadFailedFiles: [],
            downloadFailedFiles: []
        };

        if (!isNodeEnvironment) {
            result.status = 'error';
            result.error = '本地目录同步仅支持 Node.js 环境';
            return result;
        }

        if (!this.config.localDir) {
            result.status = 'error';
            result.error = '未配置本地目录 localDir';
            return result;
        }

        const path = require('path');

        try {
            this.updateStatus('syncing');

            // 1. 扫描本地文件夹
            this.emitProgress('scanning', 0, 0, '');
            const fileList = await this.scanFolder(this.config.localDir);

            // 2. 发送同步请求到服务器
            const syncResponse = await axios.post(
                `${this.config.apiUrl}/sync_public_files`,
                {
                    agent_id: this.config.aid,
                    signature: this.config.signature,
                    file_list: fileList
                }
            );

            if (syncResponse.status !== 200) {
                throw new Error(`sync_public_files 请求失败: ${syncResponse.status}`);
            }

            const responseData = syncResponse.data;
            const needUploadFiles: string[] = responseData.need_upload_files || [];
            const needDownloadFiles: string[] = responseData.need_download_files || [];

            // 3. 上传需要上传的文件
            for (let i = 0; i < needUploadFiles.length; i++) {
                const fileName = needUploadFiles[i];
                const fullPath = path.join(this.config.localDir, fileName);

                this.emitProgress('uploading', i + 1, needUploadFiles.length, fileName);

                const uploadResult = await this.uploadFile(fullPath, fileName);
                if (uploadResult.success) {
                    result.uploadedFiles.push(fileName);
                    logger.log(`文件 ${fileName} 上传成功 => ${uploadResult.url}`);
                } else {
                    result.uploadFailedFiles.push(fileName);
                    logger.error(`文件 ${fileName} 上传失败`);
                }
            }

            // 4. 下载需要下载的文件
            for (let i = 0; i < needDownloadFiles.length; i++) {
                const fileName = needDownloadFiles[i];
                const savePath = path.join(this.config.localDir, fileName);

                this.emitProgress('downloading', i + 1, needDownloadFiles.length, fileName);

                const success = await this.downloadFile(fileName, savePath);
                if (success) {
                    result.downloadedFiles.push(fileName);
                    logger.log(`文件 ${fileName} 下载成功，保存路径: ${savePath}`);
                } else {
                    result.downloadFailedFiles.push(fileName);
                    logger.error(`文件 ${fileName} 下载失败`);
                }
            }

            // 判断最终状态
            const hasFailures = result.uploadFailedFiles.length > 0 || result.downloadFailedFiles.length > 0;
            result.status = hasFailures ? 'error' : 'completed';
            this.updateStatus(result.status);

        } catch (error: any) {
            result.status = 'error';
            result.error = error.message || '同步过程中发生错误';
            this.updateStatus('error');
            logger.error('sync_public_files 错误:', error);
        }

        return result;
    }

    /**
     * 获取当前同步状态
     */
    public getStatus(): FileSyncStatus {
        return this.status;
    }

    /**
     * 设置状态变更回调
     */
    public onStatusChange(cb: (status: FileSyncStatus) => void): void {
        this.statusCallback = cb;
    }

    /**
     * 设置进度回调
     * @param cb 回调函数，phase 可能的值: 'scanning' | 'uploading' | 'downloading'
     */
    public onProgress(cb: (progress: { phase: string; current: number; total: number; fileName: string }) => void): void {
        this.progressCallback = cb;
    }

    /**
     * 上传 agent.md 文件
     * 将智能体描述文件上传到服务器，上传后可通过 https://{agent_id}/agent.md 访问
     * @param content agent.md 文件内容（Markdown 格式，最大 4KB）
     * @returns 上传结果 { success: boolean, url?: string, error?: string }
     */
    public async uploadAgentMd(content: string): Promise<{ success: boolean; url?: string; error?: string }> {
        if (!content || content.trim().length === 0) {
            return { success: false, error: 'Empty content' };
        }

        // 检查文件大小限制（4KB）
        let contentSize: number;
        if (isNodeEnvironment) {
            contentSize = Buffer.byteLength(content, 'utf8');
        } else {
            contentSize = new Blob([content]).size;
        }
        if (contentSize > 4 * 1024) {
            return { success: false, error: `文件大小超过限制: ${contentSize} bytes > 4KB` };
        }

        try {
            // URL 格式: https://{agent_id}/agent.md
            const url = `https://${this.config.aid}/agent.md`;

            const response = await axios.post(url, content, {
                headers: {
                    'Content-Type': 'text/markdown',
                    'Authorization': `Bearer ${this.config.signature}`
                }
            });

            if (response.status === 200) {
                return {
                    success: true,
                    url: response.data.url || url
                };
            }

            return {
                success: false,
                error: response.data?.message || `上传失败: ${response.status}`
            };
        } catch (error: any) {
            const errorMsg = error.response?.data?.message || error.message || '上传 agent.md 失败';
            logger.error('uploadAgentMd 错误:', errorMsg);
            return { success: false, error: errorMsg };
        }
    }

    /**
     * 从本地文件上传 agent.md（仅 Node.js 环境）
     * @param filePath 本地 agent.md 文件路径
     * @returns 上传结果
     */
    public async uploadAgentMdFromFile(filePath: string): Promise<{ success: boolean; url?: string; error?: string }> {
        if (!isNodeEnvironment) {
            return { success: false, error: '此方法仅支持 Node.js 环境' };
        }

        const fs = require('fs');

        try {
            if (!fs.existsSync(filePath)) {
                return { success: false, error: `文件不存在: ${filePath}` };
            }

            const content = fs.readFileSync(filePath, 'utf8');
            return this.uploadAgentMd(content);
        } catch (error: any) {
            return { success: false, error: error.message || '读取文件失败' };
        }
    }
}
