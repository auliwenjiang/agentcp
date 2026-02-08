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
import os

from agentcp.base.log import log_error, log_info
class CARoot:
    _instance = None
    
    def __new__(cls):
        if not cls._instance:
            cls._instance = super().__new__(cls)
            cls._instance.__initialized = False
        return cls._instance
    
    def set_ca_root_crt(self,ca_root_path):
        self.__ca_root_path = ca_root_path
    
    def __init__(self):
        self.__ca_crt = []
        # 内置根证书（PEM格式）
        self.__ca_crt.append("""\
-----BEGIN CERTIFICATE-----
MIICJjCCAYigAwIBAgIQf2zjuigigLrW8Su0I+2AiTAKBggqhkjOPQQDBDAnMRMw
EQYDVQQKEwpBZ2VudFVuaW9uMRAwDgYDVQQDEwdSb290IENBMB4XDTI1MDUwODA3
MDE1OFoXDTQ1MDUwODA3MDE1OFowJzETMBEGA1UEChMKQWdlbnRVbmlvbjEQMA4G
A1UEAxMHUm9vdCBDQTCBmzAQBgcqhkjOPQIBBgUrgQQAIwOBhgAEAUuDc4dMcjXI
GVxem8HStonZlyfyqtujfpTz8WP4ZcMUCTlrvnxZRjzNarmzSc2Yx2COcK1VEuzP
TcyQGE/Pw9i4AP9qGtX0j3dwLw+i2+TzEOmgoulm+t+fyjxhLsmqyWrIUdTv6T5C
IYVkSnX1mM0UPVQYxZi/2Uuyw8FOcPzIq7eWo1MwUTAOBgNVHQ8BAf8EBAMCAf4w
DwYDVR0lBAgwBgYEVR0lADAPBgNVHRMBAf8EBTADAQH/MB0GA1UdDgQWBBQhkljB
FddnHb7Y0j6YEZ7wtYReNzAKBggqhkjOPQQDBAOBiwAwgYcCQWKjy52NZwqJZ1FN
1n1BRPAIy6nFDTke+HbM/JFWGyFrNSx4ceVSurpa+Uy9TWmwNUuog82MHRDXnlYp
e1KpOe6qAkIBGGII4Yfzoc5x+ZC0le7kyAYTJJl1XVLCdwECPRfzk/uZHonFA4tV
nHMwnEqFoMdsj2GgOqoRqAw/miMQwo2T0hA=
-----END CERTIFICATE-----
""")
        self.__ca_root_path = None
        self.__initialized = True
        
    def get_ca_root_crt_number(self):
        return len(self.__ca_crt)
    
    def get_ca_root_crt(self,index=0):
        if self.__ca_root_path:
            try:
                crt_files = sorted([f for f in os.listdir(self.__ca_root_path) if f.endswith('.crt')])
                if not crt_files:
                    log_error(f"目录 {self.__ca_root_path} 中没有证书文件")
                    return self.__ca_crt[index]
                    
                if index >= len(crt_files):
                    log_error(f"索引 {index} 超出文件数量 {len(crt_files)}")
                    return None
                    
                cert_path = os.path.join(self.__ca_root_path, crt_files[index])
                with open(cert_path, 'r', encoding='utf-8') as f:
                    return f.read()
            except FileNotFoundError:
                log_error(f"根证书目录 {self.__ca_root_path} 不存在")
            except Exception as e:
                log_error(f"根读取证书文件失败: {str(e)}")
        return self.__ca_crt[index]