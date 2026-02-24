import { CertAndKeyStore } from './datamanager';
import { createSignedCertificateAsync } from './cert';
import { KEYUTIL, KJUR } from 'jsrsasign';
import { signCert } from './api';

function getTimestamp(): string {
    const now = new Date();
    const y = now.getFullYear();
    const m = String(now.getMonth() + 1).padStart(2, '0');
    const d = String(now.getDate()).padStart(2, '0');
    const h = String(now.getHours()).padStart(2, '0');
    const min = String(now.getMinutes()).padStart(2, '0');
    const s = String(now.getSeconds()).padStart(2, '0');
    return `${y}/${m}/${d} ${h}:${min}:${s}`;
}

export const logger = {
    log: (...args: any[]) => console.log(`[${getTimestamp()}]`, ...args),
    warn: (...args: any[]) => console.warn(`[${getTimestamp()}]`, ...args),
    error: (...args: any[]) => console.error(`[${getTimestamp()}]`, ...args),
    info: (...args: any[]) => console.info(`[${getTimestamp()}]`, ...args),
};

// 解密私钥数据
function decryptPrivateKey(encryptedData: string, password: string): (string | null) {
    try {
        const hashPWD = getSha256(password);
        const privateKeyObj = KEYUTIL.getKey(encryptedData, hashPWD);
        const privateKeyPEM = KEYUTIL.getPEM(privateKeyObj, 'PKCS8PRV');
        return privateKeyPEM;
    }
    catch (err) {
        logger.error('私钥解密失败:', err);
        return null;
    }
}

// 加密私钥数据
function encryptPrivateKey(privateKeyPEM: string, password: string): (string | null) {
    try {
        const hashPWD = getSha256(password);
        const prvKeyObj = KEYUTIL.getKey(privateKeyPEM);
        const encryptedPEM = KEYUTIL.getPEM(prvKeyObj, 'PKCS8PRV', hashPWD);
        return encryptedPEM;
    }
    catch (err) {
        logger.error('私钥加密失败:', err);
        return null;
    }
}

function getSha256(inputStr: string): string {
    const hash = KJUR.crypto.Util.sha256(inputStr);
    return hash
}

function handleError(error: unknown, customMessage?: string): never {
    const errorMessage = error instanceof Error ? error.message : String(error);
    throw new Error(`${customMessage || '操作失败'}: ${errorMessage}`);
}

export async function getDecryptKey(aid: string, password: string) {
    const privateKey = await CertAndKeyStore.getPrivateKey(aid);
    if (!privateKey) {
        handleError(new Error("privateKey 不应为空"));
    }
    const decryptedPrivateKey = decryptPrivateKey(privateKey, password);
    return decryptedPrivateKey;
}

export async function savePrivateKey(aid: string, privateKey: string, password: string) {
    const encryptedPrivateKey = encryptPrivateKey(privateKey, password);
    if (!encryptedPrivateKey) {
        handleError(new Error("encryptedPrivateKey 不应为空"));
    }
    await CertAndKeyStore.savePrivateKey(aid, encryptedPrivateKey);
}

export async function createAid(aid: string, apiUrl: string, seedPassword: string): Promise<boolean> {
    const {
        csrPEM,
        prvKeyPEM
    } = await createSignedCertificateAsync(aid);
    const cert = await signCert(aid, apiUrl, csrPEM);
    if (cert) {
        await CertAndKeyStore.saveAid(aid);
        await CertAndKeyStore.saveCertificate(aid, cert);
        await CertAndKeyStore.saveCsr(aid, csrPEM);
        await savePrivateKey(aid, prvKeyPEM, seedPassword);
        return true;
    } else {
        return false;
    }
}