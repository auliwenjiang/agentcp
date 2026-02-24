import axios from 'axios';
import { v4 as uuidv4 } from 'uuid';
import { CertAndKeyStore } from './datamanager';
import { getPublicKeyPem, isPemValid, signPrivate } from './cert';
import { savePrivateKey , logger } from './utils';

export async function getGuestAid(apiUrl: string, seedPassword: string): Promise<string | null> {
    try {
        const localAid = await CertAndKeyStore.getGuestAid();

        if (localAid && localAid.length > 0) {
            const cert = await CertAndKeyStore.getCertificate(localAid);
            if (cert && isPemValid(cert)) {
                return localAid;
            }
        }

        const response = await axios.get(`${apiUrl}/sign_guest_cert`, {});
        if (response.status === 200) {
            const { guest_aid, key, cert } = response.data as { guest_aid: string; key: string; cert: string };
            if (guest_aid && key && cert) {
                await CertAndKeyStore.saveAid(guest_aid);
                await CertAndKeyStore.saveCertificate(guest_aid, cert);
                await savePrivateKey(guest_aid, key, seedPassword);
                return guest_aid;
            }
        }
        return null;
    } catch (error) {
        logger.error('获取访客证书失败:', error);
        return null;
    }
}

export async function getEntryPointConfig(aid: string, apiUrl: string): Promise<{
    heartbeatServer: string,
    messageServer: string
} | null> {
    try {
        const data = {
            agent_id: aid,
        };
        const response = await axios.post(`${apiUrl}/get_accesspoint_config`, data);
        if (response.status === 200) {
            const data = response.data as { config: string };
            const configObj = JSON.parse(data.config);
            const {
                heartbeat_server,
                message_server
            } = configObj;
            return {
                heartbeatServer: heartbeat_server,
                messageServer: message_server
            };
        }
        return null;
    } catch (error) {
        logger.error('获取接入点配置失败:', error);
        return null;
    }
}

export async function signCert(agentId: string, apiUrl: string, csr: string): Promise<string | null> {
    const data = {
        id: agentId,
        csr: csr
    };
    try {
        const headers = {
            'Content-Type': 'application/json'
        };
        const response = await axios.post(`${apiUrl}/sign_cert`, data, { headers });
        if (response.status === 200) {
            const { certificate } = response.data as { certificate: string };
            return certificate
        }
        return null;
    } catch (error) {
        logger.error('sign_cert接口异常:', error, data);
        return null;
    }
}

export async function signIn(
    agentId: string,
    apiUrl: string,
    privateKey: string,
    publicKeyPem?: string,
    certPem?: string
): Promise<{
    signature: string | null,
    signData: any
} | null> {
    try {
        const requestId = uuidv4();
        const data = {
            agent_id: agentId,
            request_id: requestId,
            client_info: `AgentCP/0.1.31 (AuthClient; ${agentId})`
        };

        const headers = {
            'Content-Type': 'application/json'
        };

        const response = await axios.post(`${apiUrl}/sign_in`, data, { headers });
        if (response.status === 200) {
            const { nonce } = response.data as { nonce: string };

            // 使用传入的参数或重新获取
            let publicKey = publicKeyPem;
            let certificate = certPem;

            // 如果缺少任何一个参数，就获取完整信息
            if (!publicKey || !certificate) {
                const keyInfo = await getPublicKeyPem(agentId);
                publicKey = publicKey || keyInfo.publicKeyPem;
                certificate = certificate || keyInfo.certPem;
            }

            if (!publicKey || !certificate) {
                logger.error('signIn 失败: 无法获取公钥或证书');
                return null;
            }

            const signatureHex = await signPrivate(nonce, privateKey);
            const data = {
                agent_id: agentId,
                request_id: requestId,
                nonce: nonce,
                public_key: publicKey,
                cert: certificate,
                signature: signatureHex,
            }
            const res = await axios.post(`${apiUrl}/sign_in`, data, { headers });
            if (res.status === 200) {
                const { signature } = res.data as { signature: string };
                const signData = res.data;
                return {
                    signature,
                    signData
                };
            }
            logger.error('signIn 第二步失败:', res.status, res.data);
            return null;
        }
        logger.error('signIn 第一步失败:', response.status, response.data);
        return null
    } catch (error: any) {
        const errMsg = error.response?.data?.message || error.message || error;
        logger.error('登录异常:', errMsg);
        return null
    }
}

export async function signOut(agentId: string, apiUrl: string): Promise<boolean> {
    try {
        const requestId = uuidv4();
        const data = {
            agent_id: agentId,
            request_id: requestId,
            client_info: `AgentCP/0.1.31 (AuthClient; ${agentId})`
        };
        const headers = {
            'Content-Type': 'application/json'
        };
        const response = await axios.post(`${apiUrl}/sign_out`, data, { headers });
        if (response.status === 200) {
            return true;
        }
        return false;
    } catch (error) {
        logger.error('退出登录异常:', error);
        return false;
    }
}