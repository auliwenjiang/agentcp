import { X509, KEYUTIL, KJUR } from 'jsrsasign';
import { CertAndKeyStore } from './datamanager';
import { logger } from './utils';

function createSignedCertificate(aid: string = '') {
    const { pubKeyObj, prvKeyObj } = KEYUTIL.generateKeypair("EC", "secp384r1");
    const prvKeyPEM = KEYUTIL.getPEM(prvKeyObj, "PKCS8PRV");
    const pubKeyPEM = KEYUTIL.getPEM(pubKeyObj)
    const csrPEM = createCSR(aid, prvKeyPEM, pubKeyPEM);
    return {
        csrPEM,
        prvKeyPEM,
        pubKeyPEM
    }
}

export async function createSignedCertificateAsync(aid: string = ''): Promise<{
    csrPEM: string;
    prvKeyPEM: string;
    pubKeyPEM: string;
}> {
    return await new Promise((resolve) => {
        const cert = createSignedCertificate(aid);
        resolve(cert);
    });
}

export function isPemValid(certPem: string): boolean {
    // 解析为Date对象
    function parseTime(timeStr: string) {
        const year2 = parseInt(timeStr.substring(0, 2), 10);
        const year = year2 >= 50 ? 1900 + year2 : 2000 + year2;
        const month = timeStr.substring(2, 4);
        const day = timeStr.substring(4, 6);
        const hour = timeStr.substring(6, 8);
        const minute = timeStr.substring(8, 10);
        const second = timeStr.substring(10, 12);
        return new Date(`${year}-${month}-${day}T${hour}:${minute}:${second}Z`);
    }
    // 解析证书
    const x509 = new X509();
    x509.readCertPEM(certPem);
    const notBeforeStr = x509.getNotBefore();
    const notAfterStr = x509.getNotAfter();

    const notBefore = parseTime(notBeforeStr);
    const notAfter = parseTime(notAfterStr);
    const now = new Date();

    const valid = now >= notBefore && now <= notAfter;
    return valid;
}

export async function getPublicKeyPem(agentId: string): Promise<{
    publicKeyPem: string;
    certPem: string;
}> {
    try {
        const certPem = await CertAndKeyStore.getCertificate(agentId);
        if (!certPem) {
            throw new Error('证书不存在');
        }
        const publicKeyPem = await extractPublicKeyFromPem(certPem);
        return {
            publicKeyPem,
            certPem
        };
    } catch (error) {
        logger.error('获取公钥 PEM 格式失败:', error);
        throw new Error('获取公钥失败');
    }
}

// 检测运行环境
const isReactNative = (typeof global !== 'undefined' && (global as any).HermesInternal !== undefined) ||
    (typeof navigator !== 'undefined' && navigator.userAgent?.includes('ReactNative'));

/**
 * 签名函数
 */
export async function signPrivate(nonce: string, privateKey: string): Promise<string> {
    return new Promise((resolve, reject) => {
        // 使用 setTimeout 确保不阻塞 UI 线程
        setTimeout(async () => {
            try {
                let signature: string;

                if (isReactNative) {
                    // React Native 环境下的优化处理
                    signature = await signInChunks(nonce, privateKey);
                } else {
                    // Web 环境可以直接处理
                    signature = await signDirect(nonce, privateKey);
                }

                resolve(signature);
            } catch (error) {
                reject(error);
            }
        }, 0);
    });
}

/**
 * 分块处理签名，避免长时间阻塞UI
 */
async function signInChunks(nonce: string, privateKey: string): Promise<string> {
    return new Promise((resolve, reject) => {
        let step = 0;
        let sig: any;

        const processStep = () => {
            try {
                switch (step) {
                    case 0:
                        // 第一步：初始化签名对象
                        sig = new KJUR.crypto.Signature({ alg: "SHA256withECDSA" });
                        step++;
                        setTimeout(processStep, 0);
                        break;

                    case 1:
                        // 第二步：初始化私钥
                        sig.init(privateKey);
                        step++;
                        setTimeout(processStep, 0);
                        break;

                    case 2:
                        // 第三步：更新数据并签名
                        sig.updateString(nonce);
                        const signatureHex = sig.sign();
                        resolve(signatureHex);
                        break;
                }
            } catch (error) {
                reject(error);
            }
        };

        processStep();
    });
}

/**
 * 直接签名处理（非 RN 环境）
 */
async function signDirect(nonce: string, privateKey: string): Promise<string> {
    const sig = new KJUR.crypto.Signature({ alg: "SHA256withECDSA" });
    sig.init(privateKey);
    sig.updateString(nonce);
    return sig.sign();
}

/**
 * 公钥提取函数
 */
async function extractPublicKeyFromPem(certPem: string): Promise<string> {
    return new Promise((resolve, reject) => {
        setTimeout(async () => {
            try {
                let publicKey: string;

                if (isReactNative) {
                    // React Native 环境下的分块处理
                    publicKey = await extractInChunks(certPem);
                } else {
                    // Web 环境直接处理
                    publicKey = await extractDirect(certPem);
                }

                resolve(publicKey);
            } catch (error) {
                reject(error);
            }
        }, 0);
    });
}

/**
 * 分块提取公钥，避免长时间阻塞UI
 */
async function extractInChunks(certPem: string): Promise<string> {
    return new Promise((resolve, reject) => {
        let step = 0;
        let x509: any;
        let pubKeyObj: any;

        const processStep = () => {
            try {
                switch (step) {
                    case 0:
                        // 第一步：初始化X509对象
                        x509 = new X509();
                        step++;
                        setTimeout(processStep, 0);
                        break;

                    case 1:
                        // 第二步：读取证书并提取公钥
                        x509.readCertPEM(certPem);
                        pubKeyObj = x509.getPublicKey();
                        const pubKeyPem = KEYUTIL.getPEM(pubKeyObj);
                        resolve(pubKeyPem);
                        break;
                }
            } catch (error) {
                reject(error);
            }
        };

        processStep();
    });
}

/**
 * 直接提取公钥（非 RN 环境）
 */
async function extractDirect(certPem: string): Promise<string> {
    const x509 = new X509();
    x509.readCertPEM(certPem);
    const pubKeyObj = x509.getPublicKey();
    const pubKeyPem = KEYUTIL.getPEM(pubKeyObj);
    return pubKeyPem;
}

/**
 * 预加载 jsrsasign 模块
 */
export async function preloadCrypto(): Promise<void> {
    try {
        // 预加载 jsrsasign 模块
        require('jsrsasign');
    } catch (error) {
        logger.warn('Crypto preload failed:', error);
    }
}


function createCSR(commonName: string, prvKeyPEM: string, pubKeyPEM: string): string {
    const csr = new KJUR.asn1.csr.CertificationRequest({
        subject: {
            str: `/C=CN/ST=SomeState/L=SomeCity/O=SomeOrganization/CN=${commonName}`
        },
        sbjpubkey: pubKeyPEM,
        sbjprvkey: prvKeyPEM,
        sigalg: "SHA256withECDSA",
        extreq: [
            {
                extname: "basicConstraints",
            }
        ]
    });
    const csrPEM = csr.getPEM();
    return csrPEM;
}