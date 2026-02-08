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
import datetime
import os
import shutil
import time

import requests
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from agentcp.base.env import Environ
from agentcp.base.log import log_debug, log_error, log_exception, log_info

from ..context import ErrorContext, exceptions


class CAClient:
    def __init__(self, ca_server, aid_path, seed_password: str, timeout=30):
        self.ca_server = ca_server or Environ.CA_SERVER.get()  # 移除末尾的斜杠
        if not self.ca_server or not self.ca_server.startswith(("http://", "https://")):
            raise ValueError("无效的CA服务器地址")

        self.ca_server = self.ca_server.rstrip("/")  # 移除末尾的斜杠
        self.ca_server = self.ca_server + "/api/accesspoint"
        self.timeout = timeout
        self.seed_password = seed_password
        self.aid_path = aid_path

    def get_aid_certs_path(self, aid_str):
        return os.path.join(self.aid_path, aid_str, "private", "certs")

    def __save_csr_to_file(self, csr, filename):
        try:
            # 确保目录存在
            file_dir = os.path.dirname(filename)
            os.makedirs(file_dir, exist_ok=True)
            with open(filename, "wb") as f:
                f.write(csr.public_bytes(serialization.Encoding.PEM))
            log_debug(f"CSR save to {filename}")  # 调试用
        except Exception as e:
            log_exception(f"save csr to file error: {e}")  # 调试用

    def save_cert_to_file(self, name, certificate: str):
        try:
            aid_path = os.path.join(self.aid_path, name, "private", "certs")
            # 确保目录存在
            os.makedirs(aid_path, exist_ok=True)
            aid_path = os.path.join(aid_path, name + ".crt")
            with open(aid_path, "wb") as f:
                f.write(certificate.encode("utf-8"))
            log_debug(f"private key saveto {name}.key")  # 调试用
        except Exception as e:
            log_exception(f"save private key to file error{e}")  # 调试用
            ErrorContext.publish(exceptions.SDKError(f"保存证书失败: {e}"))
            raise RuntimeError("保存证书失败")

    def save_private_key_to_file(self, name, private_key):
        try:
            aid_path = os.path.join(self.aid_path, name, "private", "certs")
            # 确保目录存在
            os.makedirs(aid_path, exist_ok=True)
            aid_path = os.path.join(aid_path, name + ".key")
            with open(aid_path, "wb") as f:
                f.write(
                    private_key.private_bytes(
                        encoding=serialization.Encoding.PEM,
                        format=serialization.PrivateFormat.PKCS8,
                        encryption_algorithm=serialization.BestAvailableEncryption(self.seed_password.encode()),
                    )
                )
            log_debug(f"private key saveto {name}.key")  # 调试用
        except Exception as e:
            log_exception(f"save private key to file error{e}")  # 调试用
            ErrorContext.publish(exceptions.SDKError(f"保存私钥失败: {e}"))
            raise RuntimeError("保存私钥失败")

    def modify_seed_password(self, aid_str, private_key, new_send_password):
        temp_path = os.path.join(self.aid_path, aid_str)
        os.path.exists(temp_path) or os.makedirs(temp_path)
        aid_path = os.path.join(temp_path, aid_str + ".key")
        with open(aid_path, "wb") as f:
            f.write(
                private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.BestAvailableEncryption(new_send_password.encode("utf-8")),
                )
            )
        old_aid_path = os.path.join(self.aid_path, aid_str, "private", aid_str + ".key")
        old_key_path = os.path.join(self.aid_path, aid_str, "private", "old.key")
        os.rename(old_aid_path, old_key_path)
        # 复制新文件到旧路径
        shutil.copy2(aid_path, old_aid_path)
        # 删除old.key
        os.remove(old_key_path)
        os.remove(aid_path)

    def __generate_private_key(self):
        """
        生成NIST P-384椭圆曲线私钥
        :return: 返回生成的私钥对象
        """
        # 使用SECP384R1曲线生成私钥
        private_key = ec.generate_private_key(ec.SECP384R1())
        return private_key

    def __generate_csr(self, private_key, common_name):
        """
        使用NIST P-384私钥生成证书签名请求(CSR)
        :param private_key: NIST P-384椭圆曲线私钥
        :param common_name: 证书通用名称
        :return: 返回生成的CSR对象
        """
        # 创建 CSR 的主体信息
        csr_builder = x509.CertificateSigningRequestBuilder().subject_name(
            x509.Name(
                [
                    x509.NameAttribute(NameOID.COUNTRY_NAME, "CN"),
                    x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "SomeState"),
                    x509.NameAttribute(NameOID.LOCALITY_NAME, "SomeCity"),
                    x509.NameAttribute(NameOID.ORGANIZATION_NAME, "SomeOrganization"),
                    x509.NameAttribute(NameOID.COMMON_NAME, common_name),
                ]
            )
        )

        # 添加扩展（可选）
        csr_builder = csr_builder.add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True,
        )

        # 使用私钥对 CSR 进行签名
        csr = csr_builder.sign(private_key, hashes.SHA256(), default_backend())
        return csr

    def __load_csr(self, agent_id):
        aid_path = os.path.join(self.aid_path, agent_id, "private", "certs", agent_id + ".csr")
        if os.path.exists(aid_path):
            with open(aid_path, "rb") as f:
                csr = x509.load_pem_x509_csr(f.read())
            return csr
        return None

    def load_private_key_str(self, agent_id, seed_password: str):
        try:
            aid_path = os.path.join(self.aid_path, agent_id, "private", "certs", agent_id + ".key")
            with open(aid_path, "rb") as f:
                private_key = serialization.load_pem_private_key(
                    f.read(),
                    password=seed_password.encode("utf-8"),
                )
                return private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.BestAvailableEncryption(seed_password.encode("utf-8")),
                ).decode("utf-8")
        except Exception as e:
            ErrorContext.publish(exceptions.SDKError(f"load_private_key_str: {e}"))
            return ""

    # def load_cert_str(self,agent_id):
    #     try:
    #         aid_path = os.path.join(self.aid_path,agent_id,'private','certs',agent_id+".crt")
    #         with open(aid_path, "rb") as f:
    #             certificate_pem = f.read().decode('utf-8')
    #         return certificate_pem
    #     except Exception as e:
    #         return ""

    def load_private_key(self, agent_id):
        try:
            # 加载私钥
            aid_path = os.path.join(self.aid_path, agent_id, "private", "certs", agent_id + ".key")
            with open(aid_path, "rb") as f:
                private_key = serialization.load_pem_private_key(
                    f.read(),
                    password=self.seed_password.encode("utf-8"),
                )
            return private_key
        except Exception as e:
            # 兼容性代码，按照不加密获取private_key
            ErrorContext.publish(exceptions.SDKError(f"load_private_key: {e}"))
            return None

    def __load_public_key_pem(self, public_key):
        public_key_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode("utf-8")
        return public_key_pem

    def load_certificate_pem(self, agent_id):
        aid_path = os.path.join(self.aid_path, agent_id, "private", "certs", agent_id + ".crt")
        with open(aid_path, "rb") as f:
            certificate_pem = f.read().decode("utf-8")
        return certificate_pem

    def __get_guest_aid(self):
        os.path.exists(self.aid_path) or os.makedirs(self.aid_path)
        for entry in os.scandir(self.aid_path):
            array = entry.name.split(".")
            if entry.is_dir() and entry.name.startswith("guest"):
                return entry.name
        return ""

    def get_guest_aid(self):
        try:
            local_guest_aid = self.__get_guest_aid()
            path = os.path.join(self.aid_path, local_guest_aid, "private", "certs", local_guest_aid + ".crt")
            if local_guest_aid and self.__pen_is_valid(path):
                return local_guest_aid
            elif local_guest_aid:
                # 删除这个目录下的所有文件和子目录
                shutil.rmtree(os.path.join(self.aid_path, local_guest_aid))
            url = self.ca_server + "/sign_guest_cert"
            response = requests.get(url, verify=False)
            if response.status_code == 200:
                rjs = response.json()
                if "guest_aid" in rjs and "key" in rjs and "cert" in rjs and "entrypoint" in rjs:
                    log_info(f"sign_guest_cert ok:{rjs}")
                    guest_aid = rjs["guest_aid"]
                    guest_key = rjs["key"]
                    guest_cert = rjs["cert"]
                    # 打印 guest_cert 内容，检查是否包含正确的 CSR 标记

                    try:
                        # 尝试加载证书
                        certificate = x509.load_pem_x509_certificate(guest_cert.encode("utf-8"), default_backend())
                    except Exception as e:
                        log_error(f"加载证书失败: {e}")
                        return None

                    guest_key = serialization.load_pem_private_key(guest_key.encode("utf-8"), password=None)

                    if not os.path.exists(os.path.join(self.aid_path, guest_aid)):
                        os.makedirs(os.path.join(self.aid_path, guest_aid), exist_ok=True)

                    self.save_private_key_to_file(guest_aid, guest_key)

                    # 保存证书文件
                    aid_path = os.path.join(self.aid_path, guest_aid, "private", "certs")
                    cert_name = os.path.join(aid_path, guest_aid + ".crt")
                    with open(cert_name, "wb") as f:
                        f.write(guest_cert.encode("utf-8"))
                    time.sleep(0.5)
                    return guest_aid
                else:
                    log_error(f"sign_guest_cert failed:{rjs}")
                    return None
            else:
                log_error(f"sign_guest_cert failed:{response.status_code} - {response.json().get('error', '')}")
                return None
        except Exception as e:
            ErrorContext.publish(exceptions.SDKError(f"获取访问身份失败: {e}"))
            log_error(f"获取访问身份失败: {e}")
            # log_error("详细堆栈信息:")
            # traceback.print_exc()
            return None

    def __pen_is_valid(self, agent_id_key_path: str):
        cert_valid = False
        try:
            aid_path = agent_id_key_path
            certificate_pem = ""
            with open(aid_path, "rb") as f:
                certificate_pem = f.read().decode("utf-8")
            certificate = x509.load_pem_x509_certificate(certificate_pem.encode("utf-8"), default_backend())
            # 获取证书的有效期
            not_valid_before = certificate.not_valid_before_utc
            not_valid_after = certificate.not_valid_after_utc
            # 获取当前时间
            current_time = datetime.datetime.now(datetime.timezone.utc)
            # 检查证书是否过期
            if current_time < not_valid_before:
                log_error("证书尚未生效")
            elif current_time > not_valid_after:
                log_error("证书已过期")
            elif current_time + (not_valid_after - not_valid_before) / 10 > not_valid_after:
                log_error("证书剩余有效期不足一半，需要续签")
            else:
                log_info("证书在有效期内")
                cert_valid = True
        except Exception as e:
            log_error(f"解析证书时出错: {e}")
            ErrorContext.publish(exceptions.SDKError(f"解析证书时出错: {e}"))
            cert_valid = False
        return cert_valid

    def resign_csr(self, agent_id) -> bool:
        path = os.path.join(self.aid_path, agent_id, "private", "certs", agent_id + ".crt")
        if self.__pen_is_valid(path):
            return True
        # 从CSR中提取公钥
        csr = self.__generate_csr(self.load_private_key(agent_id), agent_id)
        if csr == None:
            raise Exception("读取csr证书文件失败")
        public_key = csr.public_key()
        private_key = self.load_private_key(agent_id)
        public_key_pem = self.__load_public_key_pem(public_key)

        # 加载原有的证书文件
        certificate_pem = self.load_certificate_pem(agent_id)

        # 获取当前Unix时间戳(毫秒)
        current_time_ms = int(datetime.datetime.now().timestamp() * 1000)

        # 准备发送给服务器的数据
        data = {"id": agent_id, "request_id": f"{current_time_ms}", "public_key": public_key_pem}

        # 发送到服务器
        response = requests.post(f"{self.ca_server}/resign_cert", json=data, verify=False)
        log_info(f"resign cert response: {response.content}")
        if response.status_code == 200:
            if "nonce" in response.json():
                nonce = response.json()["nonce"]
                if nonce:
                    # 使用私钥对[公钥+盐]签名，以使服务器信任私钥仍然有效
                    # 使用NIST P-384私钥对nonce进行签名
                    signature = private_key.sign((public_key_pem + nonce).encode("utf-8"), ec.ECDSA(hashes.SHA256()))
                    csr_pem = csr.public_bytes(serialization.Encoding.PEM).decode("utf-8")
                    data = {
                        "id": agent_id,
                        "request_id": f"{current_time_ms}",
                        "public_key": public_key_pem,
                        "nonce": nonce,
                        "csr": csr_pem,
                        "cert": certificate_pem,
                        "signature": signature.hex(),  # 将签名转为十六进制字符串
                    }

                    # 发送到服务器

                    response = requests.post(self.ca_server + "/resign_cert", json=data, verify=False)
                    log_debug(f"resign cert response: {response.content}")
                    if response.status_code == 200:
                        entrypoint = ";"
                        if "entrypoint" in response.json():
                            entrypoint = response.json()["entrypoint"]
                        aid_path = os.path.join(self.aid_path, agent_id, "private", "certs", agent_id + ".crt")
                        with open(aid_path, "wb") as f:
                            f.write(response.json()["certificate"].encode("utf-8"))  # 从JSON响应中获取证书内容
                        return True
                    else:
                        log_error(f"resign csr failed: {response.status_code} - {response.json()['error']}")  # 调试用
                        return False
            else:
                log_info(
                    f"verify public key failed: {response.status_code} - {response.json().get('error', '')}"
                )  # 调试用
                ErrorContext.publish(
                    exceptions.SDKError(
                        f"verify public key failed: {response.status_code} - {response.json().get('error', '')}"
                    )
                )
                return False

    def send_csr_to_server(self, agent_id: str) -> bool:
        # 确保证书文件路径存在
        try:
            # 确保目录存在
            aid_path = os.path.join(self.aid_path, agent_id, "private", "certs")
            os.makedirs(aid_path, exist_ok=True)  # 确保aid/name目录存在

            private_key = self.__generate_private_key()
            csr = self.__generate_csr(private_key, agent_id)

            csr_pem = csr.public_bytes(serialization.Encoding.PEM).decode("utf-8")
            data = {"id": agent_id, "csr": csr_pem}
            response = requests.post(f"{self.ca_server}/sign_cert", json=data, verify=False)
            if response.status_code == 200:
                # 确保目录存在后再保存文件
                if not os.path.exists(aid_path):
                    os.makedirs(aid_path, exist_ok=True)
                crt_name = os.path.join(aid_path, agent_id + ".crt")
                with open(crt_name, "wb") as f:
                    f.write(response.json()["certificate"].encode("utf-8"))
                    csr_name = os.path.join(aid_path, agent_id + ".csr")
                    self.__save_csr_to_file(csr, csr_name)
                    self.save_private_key_to_file(agent_id, private_key)
                log_info(f"signed certificate successfully: {agent_id} {csr_name}")  # 调试用
                return True
            else:
                delete_path = os.path.join(self.aid_path, agent_id)
                shutil.rmtree(delete_path)
                log_error(f"sign failed: {self.ca_server}, {response.status_code} - {response.text}")  # 调试用
                return response.json()["error"]
        except requests.RequestException as e:
            ErrorContext.publish(exceptions.SDKError(f"send csr to server error: {e}"))
            log_exception("send csr to server error")  # 调试用
            raise RuntimeError("send csr to server error")

    def aid_is_not_exist(self, agent_id):
        path = self.aid_path
        for entry in os.scandir(path):
            if entry.is_dir() and entry.name == agent_id:
                return False
        return True
