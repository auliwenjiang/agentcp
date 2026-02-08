# -*- coding: utf-8 -*-
# Copyright 2025 AgentUnion Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from typing import Union
import uuid
import requests
from cryptography import x509
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from agentcp.ca.ca_root import CARoot
from agentcp.base.log import log_error, log_exception, log_info
from cryptography.hazmat.backends import default_backend
import os

class AuthClient:
    
    success_crt_list = []
    
    def __init__(self, agent_id: str, server_url: str,aid_path: str,seed_password: str):
        """认证客户端类
        Args:
            agent_id: 代理ID
            server_url: 服务器URL
        """
        self.agent_id = agent_id
        self.server_url = server_url
        self.signature = None
        self.aid_path = aid_path
        self.seed_password = seed_password
        self.is_retry = False

    def sign_in(self,retry_count = 0,max_retry_num = 10) -> Union[dict, None]:
        """登录方法"""
        try:
            if retry_count > max_retry_num:
                log_info(f"Retry sign in, count: {retry_count}")
                log_error("重试登录失败，请检查网络链接，重启服务")
                return ""
            hb_url = self.server_url + "/sign_in"
            log_info(f"Sign in: {hb_url}")
            request_id = uuid.uuid4().hex
            data = {
                "agent_id": self.agent_id,
                "request_id": request_id,
            }
            headers = {
                'User-Agent': f'AgentCP/{__import__("agentcp").__version__} (AuthClient; {self.agent_id})'
            }
            response = requests.post(hb_url, json=data, verify=False,headers=headers)
            if response.status_code == 200:
                self.is_retry = False
                log_info(f"Sign in url: {hb_url}, response: {response.json()}")
                aid_path = os.path.join(self.aid_path,self.agent_id+".key")
                private_key = self.__load_private_key(aid_path)
                if private_key == None:
                    raise Exception("私钥加载失败,请检查加密种子是否一致")
                aid_path = os.path.join(self.aid_path,self.agent_id+".crt")
                with open(aid_path, "rb") as f:
                    certificate_pem = f.read().decode('utf-8')
                cert = x509.load_pem_x509_certificate(certificate_pem.encode('utf-8'))
                public_key = cert.public_key()
                public_key_pem = public_key.public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo
                ).decode('utf-8')
                if "nonce" in response.json():
                    nonce = response.json()["nonce"]
                    server_cert_valid = True
                    if "cert" in response.json() and "signature" in response.json():
                        server_cert_valid = False
                        try:
                            # 将 PEM 格式的证书文本转换为证书对象
                            cert = response.json()["cert"].encode('utf-8')
                            server_cert = x509.load_pem_x509_certificate(cert, default_backend())
                            # 获取服务器证书的公钥
                            server_public_key = server_cert.public_key()
                            # 拼接 self.agent_id 和 current_time_ms
                            data_to_verify = (self.agent_id + str(request_id)).lower().encode('utf-8')
                            # 将十六进制的签名转换为字节
                            signature_bytes = bytes.fromhex(response.json()["signature"])
                            server_public_key.verify(
                                signature_bytes,
                                data_to_verify,
                                ec.ECDSA(hashes.SHA256())
                            )
                            log_info("服务器签名验证成功")
                            server_cert_valid = self.__check_server_cert(server_cert)
                            if server_cert_valid == False:
                                raise Exception("服务器证书验证失败")
                        except Exception as e:
                            server_cert_valid = False
                            raise Exception(f"{e}")
                        if not server_cert_valid:
                            raise Exception("服务器证书是无效证书，请注意通信安全")
                    if nonce:
                        signature = private_key.sign(
                            nonce.encode('utf-8'),
                            ec.ECDSA(hashes.SHA256())
                        )
                        data = {
                            "agent_id": self.agent_id,
                            "request_id": request_id,
                            "nonce": nonce,
                            "public_key": public_key_pem,
                            "cert": certificate_pem,
                            "signature": signature.hex(),
                        }
                        response = requests.post(hb_url, json=data, verify=False,headers=headers)
                        if response.status_code == 200:
                            data =  response.json()
                            self.signature = data.get("signature")
                            return data
                        else:
                            log_error(f"Sign in FAILED: {response.status_code} - {response.json().get('error', '')}")
            else:
                log_error(f"Sign in failed: {response.status_code} - {response.json().get('error', '')}")
        except Exception as e:
            log_error(f"链接建立失败，正在重试")
            import time
            if self.is_retry == False:
                log_error("重试登录失败，6s后尝试重新连接")
                self.is_retry = True
                time.sleep(6)
                self.sign_in(retry_count+1,max_retry_num)
            
            
    def __load_private_key(self,aid_path):
        try:
            # 加载私钥
            with open(aid_path, "rb") as f:
                private_key = serialization.load_pem_private_key(
                    f.read(),
                    password=self.seed_password.encode('utf-8'),
                )
            return private_key
        except Exception as e:
            #兼容性代码，按照不加密获取private_key
            return None


    def sign_out(self) -> None:
        """登出方法"""
        try:
            if self.signature is None:
                return
            hb_url = self.server_url + "/sign_out"
            data = {
                "agent_id": self.agent_id,
                "signature": self.signature,
            }
            headers = {
                'User-Agent': f'AgentCP/{__import__("agentcp").__version__} (AuthClient; {self.agent_id})'
            }
            response = requests.post(hb_url, json=data, verify=False,headers=headers)
            if response.status_code == 200:
                log_info(f"Sign out OK: {response.json()}")
            else:
                log_error(f"Sign out failed: {response.json()}")
        except Exception as e:
            log_exception("Sign out exception")
            
    def __check_server_cert(self, server_cert):
        try:
            # 尝试获取主体的组织及 common name
            try:
                organization = server_cert.subject.get_attributes_for_oid(NameOID.ORGANIZATION_NAME)
                common_name = server_cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
                if organization:
                    log_info(f"__check_server_cert 证书的组织名称为: {organization[0].value}")
                else:
                    log_info("__check_server_cert 未找到证书的组织名称")
                if common_name:
                    log_info(f"__check_server_cert 证书的通用名称为: {common_name[0].value}")
                else:
                    log_info("__check_server_cert 未找到证书的通用名称")
            except AttributeError:
                log_error("获取证书主体信息时出错，可能证书对象不存在或格式不正确。")
                return False
            aia_ext = server_cert.extensions.get_extension_for_class(x509.AuthorityInformationAccess)
            log_info(f"aia_ext:{aia_ext}")
            issuer_url = None
            for desc in aia_ext.value:
                if desc.access_method == x509.oid.AuthorityInformationAccessOID.CA_ISSUERS:
                    issuer_url = desc.access_location.value
                    break
    
            if issuer_url:
                log_info(f"证书颁发者 URL: {issuer_url}")
                if issuer_url in AuthClient.success_crt_list:
                    log_info(f"证书之前验证成功 {issuer_url}")
                    return True
                try:
                    issuer_response = requests.get(issuer_url, verify=False)
                    issuer_response.raise_for_status()
                    #TODO:将证书内存以issuer_url为键值缓存在本地，避免重复下载和验证证书
                    issuer_cert = x509.load_pem_x509_certificate(issuer_response.content, default_backend())
                    # 验证服务器证书的有效性
                    issuer_public_key = issuer_cert.public_key()
                    issuer_public_key.verify(
                        server_cert.signature,
                        server_cert.tbs_certificate_bytes,
                        ec.ECDSA(server_cert.signature_hash_algorithm)
                    )
                    #TODO标记证书是受信任的
                    log_info(f"证书验证成功 {issuer_url}")
                    AuthClient.success_crt_list.append(issuer_url)
                    return self.__check_server_cert(issuer_cert)
                except requests.RequestException as e:
                    log_error(f"下载证书颁发者证书时出错: {e}")
                    return False
                except Exception as e:
                    log_error(f"验证证书时出错: {e}")
                    return False
            else:
                log_error("未找到证书颁发者信息")
                return False
        except x509.ExtensionNotFound:
            log_error("证书中未包含 AIA 扩展信息")
            try:
                root_cert_pem = CARoot().get_ca_root_crt()
                root_cert = x509.load_pem_x509_certificate(root_cert_pem.encode('utf-8'), default_backend())
                root_public_key = root_cert.public_key()
                root_public_key.verify(
                    server_cert.signature,
                    server_cert.tbs_certificate_bytes,
                    ec.ECDSA(server_cert.signature_hash_algorithm)
                )
                log_info("用root.crt 证书进行验证成功")
                return True
            except FileNotFoundError:
                log_error("未找到 root.crt 文件，请检查文件路径。")
                return False
            except Exception as e:
                log_error(f"加载 root.crt 证书时出错: {e}")
                return False
        except Exception as e:
            log_error(f"服务器证书验证失败: {e}")
            return False
