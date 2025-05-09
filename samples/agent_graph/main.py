import json
from agentcp import AgentCP
import networkx as nx
from pyvis.network import Network


class Graph(nx.DiGraph):

    def add(self, source, target, info=""):
        if self.has_edge(source, target):
            # 更新 info 信息
            self[source][target]["info"] = info
        else:
            # 添加新边
            self.add_edge(source, target, info=info)

    def draw(self, name="agent_call_graph.html"):
        net = Network(
            height="600px",
            width="100%",
            directed=True,
            notebook=False,
            cdn_resources="in_line",
        )
        net.from_nx(self)
        root_nodes = [node for node in self.nodes if self.in_degree(node) == 0]

        # 创建 pyvis 网络图
        net = Network(
            height="600px",
            width="100%",
            directed=True,
            notebook=False,
            cdn_resources="in_line",
        )

        # 从 NetworkX 图导入结构
        net.from_nx(self)

        # 放大节点
        for node in net.nodes:
            node["size"] = 15  # 默认 25 左右，40 会明显更大
            node["color"] = "#ADD8E6"  # 可选：设置更醒目的颜色
            node["font"] = {"size": 20}  # 放大标签字体
            if self.in_degree(node["id"]) == 0:
                node["color"] = "#CFD8E6"  # 可选：设置更醒目的颜色

        # 更新每条边的 title（hover 时显示调用频率）
        for edge in net.edges:
            src = edge["from"]
            tgt = edge["to"]
            info = self.get_edge_data(src, tgt).get("info", "")
            edge["title"] = info  # 设置 hover 提示
            edge["arrows"] = "to"  # 确保箭头方向正确

        # 添加物理布局和交互设置
        net.set_options(
            """
        var options = {
          "physics": {
            "enabled": false,
            "stabilization": {
              "iterations": 300
            }
          },
          "interaction": {
            "hover": true,
            "navigationButtons": true,
            "zoomView": true,
            "dragNodes": true
          }
        }
        """
        )

        # 生成 HTML 并在浏览器中打开
        net.write_html(name, local=False, notebook=False, open_browser=True)


class AgentGraph:

    def __init__(self, name, endpoint="agentunion.cn"):
        self.name = name
        self.endpoint = endpoint
        self.acp = AgentCP("./", seed_password="888777")
        self.graph = Graph()
        self.aid = self.acp.create_aid(self.endpoint, self.name)
        self.call_count = {}
        self.id = f'{self.name}.{self.endpoint}'
        self.aid.add_message_handler(self.message_handler)
        self.graph_file = f"{self.aid.get_agent_public_path()}/agent_call_graph.html"

    async def message_handler(self, msg):
        """
        消息处理器 - 根据消息内容安全地读取文件
        {
            'session_id': '1831173476580327424', 
            'request_id': '', 'message_id': '9', 
            'ref_msg_id': '', 
            'sender': 'samplesdeveloper.agentunion.cn', 
            'receiver': 'guest_1831158907166261248.agentunion.cn', 
            'message': '[{"type": "text", "status": "success", "timestamp": 1746343146261, 
            "content": "{\\"text\\":\\"\\u8bfb\\u53d6\\u6587\\u4ef6agentprofile.json\\",\\"files\\":[],\\"links\\":[],\\"search\\":false,\\"think\\":false}",
            "stream": false, "prompt": null, "extra": null, "artifact": null}]',
            'timestamp': '1746343146265'
        }
        """

        sender = msg.get("sender")
        self.call_count[sender] = self.call_count.get(sender, 0) + 1
        print(f"收到来自 {sender} 的消息")
        self.graph.add(sender, self.id, f"调用次数: {self.call_count[sender]}")
        message = json.loads(msg.get("message"))[0]
        message = json.loads(message.get('content', '{}'))
        message = message.get('text', '')
        # self.graph.add(self.id, sender, f'调用次数: {self.call_count[sender]}')
        members = self.aid.get_session_member_list(msg.get("session_id"))
        print(f"群成员: {members}")
        for member in members:
            print(f"群组成员: {member}")
            # self.graph.add(self.id, member, f'调用次数: {self.call_count[member]}'
        if message.find('关系图') != -1:
            print(f"生成关系图: {self.graph_file}")
            try:
                self.graph.draw(name=self.graph_file)
                self.aid.sync_public_files()
                url = f'https://{self.aid.id}/{self.graph_file.split("/")[-1]}'
                self.aid.reply_message(msg, f"关系图已生成可访问: {url} 查看")
                self.graph.add(self.id, sender, f"调用次数: {self.call_count[sender]}")
            except Exception as e:
                print(f"生成关系图失败: {e}")
        else:
            self.graph.add(self.id, sender, f"调用次数: {self.call_count[sender]}")
            self.aid.reply_message(msg, "收到消息")

    def online(self):
        self.aid.online()
        self.acp.register_signal_handler()
        self.acp.serve_forever()

    def offline(self):
        self.aid.offline()
        self.graph.draw()


if __name__ == "__main__":
    ENDPOINT = "agentunion.cn"
    AGENT_NAME = "gggg12"
    agent = AgentGraph(AGENT_NAME, ENDPOINT)
    agent.online()
