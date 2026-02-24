#!/usr/bin/env node

import { startServer } from './server';
import * as path from 'path';
import * as fs from 'fs';
import { execSync, spawnSync } from 'child_process';
import { logger } from './utils';

// 判断是否为 Windows 平台
const isWindows = process.platform === 'win32';

// 获取 npm 命令（Windows 需要使用 npm.cmd）
function getNpmCommand(): string {
    return isWindows ? 'npm.cmd' : 'npm';
}

// 读取版本号
function getVersion(): string {
    try {
        const pkgPath = path.join(__dirname, '..', 'package.json');
        const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf-8'));
        return pkg.version || '未知';
    } catch {
        return '未知';
    }
}

// 更新到最新版本
function update(): void {
    logger.log('正在检查更新...');

    const npm = getNpmCommand();

    try {
        // 获取最新版本号
        const result = spawnSync(npm, ['view', 'acp-ts', 'version'], {
            encoding: 'utf-8',
            timeout: 30000
        });

        if (result.error) {
            throw new Error('无法连接到 npm 服务器，请检查网络连接');
        }

        if (result.status !== 0) {
            throw new Error(result.stderr || '获取版本信息失败');
        }

        const latestVersion = result.stdout.trim();
        const currentVersion = getVersion();

        if (latestVersion === currentVersion) {
            logger.log(`当前已是最新版本 v${currentVersion}`);
            return;
        }

        logger.log(`发现新版本 v${latestVersion}，当前版本 v${currentVersion}`);
        logger.log('正在更新...');

        // 执行全局更新
        const installResult = spawnSync(npm, ['install', '-g', 'acp-ts@latest'], {
            stdio: 'inherit',
            shell: true
        });

        if (installResult.status === 0) {
            logger.log(`更新成功！已更新到 v${latestVersion}`);
        } else {
            // 可能是权限问题
            if (!isWindows) {
                logger.log('\n更新失败，可能需要管理员权限，请尝试运行:');
                logger.log('  sudo npm install -g acp-ts@latest');
            } else {
                logger.log('\n更新失败，请尝试以管理员身份运行命令提示符后重试');
            }
            process.exit(1);
        }
    } catch (error: any) {
        logger.error('更新失败:', error.message);
        process.exit(1);
    }
}

const args = process.argv.slice(2);
let port = 9527;  // 使用非常用端口
let apiUrl = 'agentcp.io';  // 默认服务地址
let dataDir = '';  // 数据目录

// 解析命令行参数
for (let i = 0; i < args.length; i++) {
    if (args[i] === 'update') {
        update();
        process.exit(0);
    } else if (args[i] === '-v' || args[i] === '--version') {
        logger.log(`acp-ts v${getVersion()}`);
        process.exit(0);
    } else if (args[i] === '-p' || args[i] === '--port') {
        const portArg = args[i + 1];
        if (!portArg || portArg.startsWith('-')) {
            logger.error('错误: -p 参数需要指定端口号');
            process.exit(1);
        }
        const parsedPort = parseInt(portArg, 10);
        if (isNaN(parsedPort) || parsedPort < 1 || parsedPort > 65535) {
            logger.error('错误: 端口号必须是 1-65535 之间的数字');
            process.exit(1);
        }
        port = parsedPort;
        i++;
    } else if (args[i] === '-u' || args[i] === '--url') {
        const urlArg = args[i + 1];
        if (!urlArg || urlArg.startsWith('-')) {
            logger.error('错误: -u 参数需要指定 URL');
            process.exit(1);
        }
        apiUrl = urlArg;
        i++;
    } else if (args[i] === '-d' || args[i] === '--data-dir') {
        const dirArg = args[i + 1];
        if (!dirArg || dirArg.startsWith('-')) {
            logger.error('错误: -d 参数需要指定数据目录路径');
            process.exit(1);
        }
        dataDir = dirArg;
        i++;
    } else if (args[i] === '-h' || args[i] === '--help') {
        logger.log(`
acp-ts - 智能体通信调试工具 v${getVersion()}

用法:
  acp-ts [选项]
  acp-ts update      更新到最新版本

选项:
  -v, --version        显示版本号
  -p, --port <端口>    指定服务端口 (默认: 9527)
  -u, --url <地址>     指定 API 服务器地址 (默认: agentcp.io)
  -d, --data-dir <路径> 指定数据目录 (默认: 当前目录)
  -h, --help           显示帮助信息

安装:
  npm install -g acp-ts

示例:
  acp-ts
  acp-ts -p 8080
  acp-ts update
`);
        process.exit(0);
    }
}

startServer(port, apiUrl, dataDir);
