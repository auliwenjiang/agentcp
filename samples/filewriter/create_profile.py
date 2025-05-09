# Copyright 2025 ModelUnion Inc.
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

from datetime import datetime, timezone
import agentcp
from pathlib import Path  # 新增导入
import json

def create_financial_analyzer_json(publisherInfo):
    """创建智能体能力、权限描述"""
    data = {
        "publisherInfo": publisherInfo,
        "version": "1.0.0",
        "lastUpdated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "name": "文件读写",
        "description": "读写agent目录下的文件",
        "avaUrl": "https://t8.baidu.com/it/u=655275816,1648044724&fm=193",
        "capabilities": {
            "core": ["读取文件", "写入文件", "查询文件列表"],
            "extended": [],
        },
        "llm": {
            "model": "qwen-plus",  # 模型名称，或使用aid
            "num_parameters": "",  # 模型参数量（如"7B"表示70亿参数）
            "quantization_bits": "",  # 量化位数（如Q4表示4位量化）
            "context_length": "",  # 上下文长度（如"4096"表示4096个token）
        },
        "references": {
            "knowledgeBases": [""],
            "tools": [""],
            "companyInfo": [""],
            "productInfo": [""],
        },
        "authorization": {
            "modes": ["free"],
            "fee": {},
            "description": "",
            "sla": {},
        },
        "input": {
            "types": ["content"],
            "formats": ["json"],  #  详细类型
            "examples": {
                "type": "content",
                "format": "text",
                "content": "查询文件列表",
            },
            "semantics": [""],
            "compatibleAids": ["*"],
        },
        "output": {
            "types": ["content"],
            "formats": ["markdown"],
            "examples": {"type": "content", "format": "markdown", "content": ""},
            "semantics": [""],
            "compatibleAids": [""],
        },
        "supportStream": True,  # False代表当前智能体不支持流式输出
        "supportAsync": True,
        "permission": ["*"],
    }
    return data


def write_agent_profile_json(json_data):
    try:
        import os

        json_path = Path(__file__).resolve()
        json_dir = json_path.parent
        json_file = os.path.join(json_dir, "agentprofile.json")
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
            print("智能体描述文件已保存至当前目录下agentprofile.json")
    except Exception as e:
        print(f"文件写入失败: {str(e)}")
        exit(1)


if __name__ == "__main__":
    # 创建JSON数据
    # 将加密种子修改为自己的加密种子，可以是随机字符串，也可以是固定字符串，只要保证一致即可。
    acp = agentcp.AgentCP(".", seed_password="888777", debug=False)
    agentid_list = acp.get_aid_list()
    agentid: agentcp.AgentID = None
    while agentid is None:
        print("请选择一个身份（aid）:")
        for i, agentid in enumerate(agentid_list):
            print(f"{i+1}. {agentid}")
        print(f"{len(agentid_list)+1}. 创建一个新的身份（aid）")
        choice = input("请输入数字选择一个身份（aid）: ")
        try:
            choice = int(choice) - 1
            if choice < 0 or choice > len(agentid_list):
                raise ValueError
            if choice == len(agentid_list):
                aid = input("请输入名称: ")
                agentid = acp.create_aid("agentunion.cn", aid)
                if agentid is None:
                    print("创建身份（aid）失败，请打开日志查看原因")
                    exit(1)
                agentid_list = acp.get_aid_list()
            else:
                agentid = acp.load_aid(agentid_list[choice])
                if agentid is None:
                    print("加载身份（aid）失败,请打开日志查看原因")
                    exit(1)
        except ValueError:
            print("无效的选择，请重新输入。")
    print(f"当前选择的身份（aid）是: {str(agentid)}")
    agentid.init_ap_client()
    json_data = create_financial_analyzer_json(agentid.get_publisher_info())
    write_agent_profile_json(json_data)
    select_result = input("是否将文件拷贝到agent公有数据目录下（Y/N）: ")
    if select_result.upper() != "Y":
        print("程序运行结束")
        exit(1)
    agentid.create_agent_profile(json_data)
    select_result = input("拷贝成功，是否同步到接入服务器（Y/N）: ")
    if select_result.upper() != "Y":
        print("程序运行结束")
        exit(1)
    result = agentid.sync_public_files()
    if result:
        print("文件同步成功！")
    else:
        print("文件同步失败,请初始化ACP时打开日志查看")
