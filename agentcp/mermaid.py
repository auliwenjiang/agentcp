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

from pathlib import Path

from agentcp.base.log import log_error, log_info


class Mermaid:
    def __init__(self, content):
        self.mermaid_code = content
        self.graph_type = None
        self.graph_direction = None  # 新增：存储图的方向
        self.nodes = []
        self.node_dict = {}
        self.node_styles = {}
        self.edges = []
        self.parse_mermaid()

        log_info(f"图类型:{self.graph_type}")
        log_info(f"总共{len(self.nodes)}个节点,节点列表如下:\n\t{self.nodes}")
        for node in self.node_dict.items():
            log_info(f"节点映射:{node}")
        for edge in self.edges:
            log_info(f"边关系:{edge}")


    @classmethod
    def from_file(cls, dir_path, file_name):
        return cls(cls.read_mermaid_code(dir_path, file_name))
    def read_mermaid_code(dir_path: str, file_name: str):
        file_path = Path(dir_path) / f"{file_name}.mmd"
        absolute_path = file_path.absolute()
        log_info(f"读取Mermaid文件，绝对路径: {absolute_path}")
        if file_path.is_file():
            try:
                with file_path.open('r', encoding='utf-8') as f:
                    content = f.read()
                    content = content.replace('&nbsp;', '').replace(u'\xa0', u'')
                    return content
            except Exception as e:
                log_error(f"读取文件错误: {e}")
                return ""
        else:
            log_error(f"文件 {file_path} 未找到")
            return ""

    def parse_mermaid(self):
        if not self.mermaid_code:
            return

        # 检查图类型和方向
        for line in self.mermaid_code.split('\n'):
            line = line.strip()
            if not line or line.startswith('%'):
                continue

            if line.startswith('graph'):
                parts = line.split()
                if len(parts) >= 2:
                    self.graph_type = 'graph'
                    self.graph_direction = parts[1]  # 存储方向 (TD, LR, BT, RL等)
                break
            elif line.startswith(('pie', 'sequenceDiagram', 'gantt', 'classDiagram', 'stateDiagram')):
                self.graph_type = line.split()[0]
                log_error(f"不支持 {self.graph_type} 类型的图")
                return
            else:
                log_error("无法识别的图类型")
                return

        if self.graph_type != 'graph':
            return

        # 解析内容
        for line in self.mermaid_code.split('\n'):
            line = line.strip()
            if not line or line.startswith(('%', 'classDef', 'linkStyle', 'style', 'graph')):
                continue

            # 解析节点
            if (any(x in line for x in ['[', '(', '{']) and
                not any(x in line for x in ['-->', '--', '->'])) or \
                    (not any(x in line for x in ['-->', '--', '->']) and
                     line not in self.node_dict and
                     not line.startswith('graph')):
                self.parse_node(line)

            # 解析边关系
            if any(x in line for x in ['-->', '--', '->']):
                self.parse_edge(line)

    def parse_node(self, line):
        """解析节点定义"""
        node_name = ''
        node_desc = ''
        style_class = ''

        # 提取样式类 (:::xxx)
        if ':::' in line:
            parts = line.split(':::')
            line = parts[0].strip()
            style_class = parts[1].strip()

        # 花括号格式: A{描述}
        if '{' in line and '}' in line:
            start = line.find('{')
            end = line.find('}')
            node_name = line[:start].strip()
            node_desc = line[start + 1:end].strip('" ')

        # 方括号格式: A["描述"]
        elif '[' in line and ']' in line:
            start = line.find('[')
            end = line.find(']')
            node_name = line[:start].strip()
            node_desc = line[start + 1:end].strip('" ')

        # 圆括号格式: A(描述)
        elif '(' in line and ')' in line:
            start = line.find('(')
            end = line.find(')')
            node_name = line[:start].strip()
            node_desc = line[start + 1:end].strip('" ')

        # 无描述节点: A
        else:
            node_name = line.strip()
            node_desc = node_name

        if node_name and node_name not in self.node_dict:
            self.node_dict[node_name] = node_desc or node_name
            self.nodes.append(self.node_dict[node_name])
            if style_class:
                self.node_styles[node_name] = style_class

    def parse_edge(self, line):
        """解析边关系"""
        line = line.replace(' ', '')

        # 处理 A-->|描述|B 格式
        if '-->|' in line and '|' in line[line.find('-->|') + 3:]:
            arrow_pos = line.find('-->|')
            desc_start = arrow_pos + 4
            desc_end = line.find('|', desc_start)
            source = line[:arrow_pos]
            target = line[desc_end + 1:]
            description = line[desc_start:desc_end]
            self.edges.append((source, description, target))
            return

        # 处理 A-->B 格式
        if '-->' in line:
            parts = line.split('-->')
            if len(parts) == 2:
                self.edges.append((parts[0], '', parts[1]))
            return

        # 处理 A--描述-->B 格式
        if '--' in line and '-->' in line:
            arrow_pos = line.find('-->')
            source = line[:line.find('--')]
            target = line[arrow_pos + 3:]
            description = line[line.find('--') + 2:arrow_pos]
            self.edges.append((source, description, target))
            return

        # 处理 A->B 格式
        if '->' in line:
            parts = line.split('->')
            if len(parts) == 2:
                self.edges.append((parts[0], '', parts[1]))
            return
# 示例使用
if __name__ == "__main__":
    #mermaid = Mermaid.from_file('.', 'workflow')
    mmd = """
    graph TD
    %% ===== 节点定义 =====
    Z[用户交互层User]:::user
    A[任务拆解/推进/退出]:::Planner 
    B(个人助手):::PA
    D[Agent选择 AgentSelector]:::selector
    F[协作Agents]:::action
    G[单步任务执行]:::process
    Z -->|自然语言任务| B
    A -->|任务推进| D
    B -->|简单任务直接执行交付或复杂任务执行完成交付| Z
    B -->|复杂任务| A
    A -->|复杂任务完成所有步骤或者达成退出条件,交付| B
    D -->|任务推进|G
    G -->|调用| F
    F -->|成功/失败| G
    G -->|有失败任务未达到交付条件,重选Agent| D
    G -->|执行成功后交付|A
    """

    mermaid2 = Mermaid(mmd)
