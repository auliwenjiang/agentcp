
```markdown README.md
# AgentCP - 基于ACP协议的Agent标准通信库

## Agent Communication Protocol(智能体通信协议,简称ACP)
    ACP是一个开放协议,用于解决Agent互相通信协作的问题
    ACP定义了agent的数据规范、agent之间的通信以及agent之间的授权规范
    ACP Python SDK
        ACP Python SDK是一个基于ACP协议的Agent标准通信库，用于解决Agent间的身份认证及通信问题。
        ACP Python SDK提供了一系列API，用于创建AID、连接入网、构建会话，收发消息等。
        ACP Python SDK支持多Agent协作，异步消息处理，支持内网穿透，支持Agent访问的负载均衡

## 功能特性

- 🔐 Agent之间采用对等网络通信
- 🛡️ 基于https安全通信及PKI体系的安全身份认证、连接管理
- 🔄 异步消息处理，支持全链路流式输入输出
- 🤖 多 Agent 协作模式支持
- 📦 简洁易用的 API 设计
- 📊 支持Agent的高并发场景
- 📚 支持多种消息类型，包括文本、图片、文件等
- 🔗 支持内网部署，全网服务
- 🌐 异构兼容：标准化通信接口支持不同架构的Agent互联


## 开始使用 AgentCP 吧！
## 安装

```bash
pip install agentcp
```
## 快速入门

### 初始化ACP实例

```python
from agentcp import AgentCP

# 创建 AgentCP 实例
#   - agent_data_path: agent数据存储路径，必须外部指定,"."为当前目录
#   - seed_password: 加密种子，用于私有证书加密
#   - debug: 是否开启调试模式，默认为False
#   - 注意：日志默认输出在控制台&当前路径下log.txt文件中
agent_data_path = "."
acp = AgentCP(agent_data_path,seed_password = "123456",debug=True)
```

### 创建新身份

```python
# 创建新身份
#   - ap: 接入点URL，指定Agent网络的接入点（如："agentunion.cn"）
#   - name: Agent的身份标识，用于在该接入点上唯一标识该Agent
#   - 创建身份成功，返回aid对象，创建身份失败，抛出异常，可获取失败原因
#   - ps:下面两行代码将创建一个临时的aid标识,用于临时演示，实际使用时，需要将name替换为自己的名字，注意不能以guest开头
#   - 正式的aid标识可以在浏览器中像二级域名一样直接访问
name = "guest"
aid = acp.create_aid("agentunion.cn", name)
```
### 获取身份列表
```python
# 获取身份列表
list = acp.get_aid_list()
```

### 加载现有身份
```python
#   - load_success: 加载成功返回aid对象,加载失败返回None，详细原因请打开日志查看
aid = acp.load_aid("yourname.agentunion.cn")
```

### 设置消息监听器
#### 方式1：通过装饰器方式
```python
#   - msg: 当有消息
@aid.message_handler()
async def sync_message_handler(msg):
    #print(f"收到消息数据: {msg}")
    return True
```

#### 方式2：通过方法灵活设置
```python
#   - msg: 当有消息
async def sync_message_handler(msg):
    #print(f"收到消息数据: {msg}")
    return True
aid.add_message_handler(sync_message_handler)
```

#### 方式3：绑定sesion_id和方法监听器，指定监听某个会话的消息，该消息将不会被其他监听器监听
```python
#   - msg: 当有消息
async def sync_message_handler(msg):
    #print(f"收到消息数据: {msg}")
    return True
aid.add_message_handler(sync_message_handler,session_id = session_id)
```

### 移除消息监听器

```python
#   - msg: 当有消息
async def sync_message_handler(msg):
    #print(f"收到消息数据: {msg}")
    return True
aid.remove_message_handler(sync_message_handler,session_id = session_id)
```

### 连接到网络

```python
# aid上线，开始监听消息
aid.online()
```


### 快速回复消息

```python
# msg  收到的消息dict
# message 发送的消息对象或者消息文本
aid.reply_message(msg,message)
```

### 快速发送文本消息

```python
# to_aid = "" 快速给aid发送消息
# message_content 消息文本
# asnyc_message_result 快速消息回调
aid.quick_send_messsage_content(to_aid,message_content,asnyc_message_result)
```


### 快速发送消息

```python
# to_aid = "" 快速给aid发送消息
# message 消息对象
# asnyc_message_result 快速消息回调
aid.quick_send_messsage(to_aid,message,asnyc_message_result)
```



### 创建会话

```python
# 创建会话
session_id = aid.create_session(
    name="",
    subject=""
)
```


### 再会话中发送文本消息

```python
# to_aid_list = [] 指定多人接收处理
# session_id 会话id
# llm_content 大模型处理结果 
aid.send_message_content(to_aid_list, session_id,llm_content)
```

### 在会话中发送消息

```python
# 在会话中发送消息
aid.send_message(
    session_id=session_id,
    to_aid_list=["member1.agentunion.cn"],
    message={"type": "text", "content": "你好！"}
)
```



### 在会话中发送流式消息

```python
# to_aid_list = [] 指定多人接收处理
# session_id 会话id
# llm_content 大模型处理结果 
# 大模型调用流式response
#type默认为text/event-stream
await aid.send_stream_message(to_aid_list, session_id,response,type)
```

## 核心 API

### `AgentCP` 类
主要负责信号处理和程序持续运行的控制。

| 方法 | 描述 |
|------|------|
| `__init__()` | 初始化信号量和退出钩子函数，可传入app_path |
| `get_aid_list()` | 获取aid列表，返回aid字符串列表 |
| `create_aid("ep_point,name")` | 创建aid,返回aid实例|
| `load_aid(aid_str)` | 加载aid,返回aid实例 |
| `register_signal_handler(exit_hook_func=None)` | 注册信号处理函数，处理 `SIGTERM` 和 `SIGINT` 信号 |
| `serve_forever()` | 使程序持续运行，直到关闭标志被设置 |
| `signal_handle(signum, frame)` | 信号处理函数，设置关闭标志并调用退出钩子函数 |

### `AgentID` 类
核心的 Agent 身份管理类，提供身份创建、消息处理、会话管理等功能。

#### 连接管理
| 方法 | 描述 |
|------|------|
| `__init__(id, app_path, ca_client, ep_url)` | 初始化 AgentID 实例 |
| `online()` | 初始化入口点客户端、心跳客户端和会话管理器，并建立连接 |
| `offline()` | 使 Agent 下线，关闭心跳客户端和入口点客户端 |
| `get_aid_info()` | 获取 Agent 的基本信息 |

#### 会话管理
| 方法 | 描述 |
|------|------|
| `create_session(name, subject, *, type='public')` | 创建会话，返回会话 ID 或 `None` |
| `invite_member(session_id, to_aid)` | 邀请成员加入指定会话 |
| `get_online_status(aids)` | 获取指定 Agent 的在线状态 |
| `get_conversation_list(aid, main_aid, page, page_size)` | 获取会话列表 |

#### 消息处理
| 方法 | 描述 |
|------|------|
| `add_message_handler(handler: Callable[[dict], Awaitable[None]], session_id: str = "")` | 添加消息监听器 |
| `send_message(to_aid_list: list, session_id: str, message: Union[AssistantMessageBlock, list[AssistantMessageBlock], dict], ref_msg_id: str = "", message_id: str = "")` | 发送消息 |
| `async send_stream_message(to_aid_list: list, session_id: str, response: AsyncGenerator[bytes, None], type: str = "text/event-stream", ref_msg_id: str = "")` | 发送流式消息 |
| `remove_message_handler(handler: typing.Callable[[dict], typing.Awaitable[None]], session_id:str="")` | 移除消息监听器 |
| `send_message_content(to_aid_list: list, session_id: str, llm_content: str, ref_msg_id: str="", message_id:str="")` | 发送文本消息 |
| `send_message(to_aid_list: list, sessionId: str, message: Union[AssistantMessageBlock, list[AssistantMessageBlock], dict], ref_msg_id: str="", message_id:str="")` | 发送消息，可以处理不同类型的消息对象 |
| `async send_stream_message(to_aid_list: list, session_id: str, response, type="text/event-stream", ref_msg_id:str="")` | 发送流式消息 |

#### 其他功能
| 方法 | 描述 |
|------|------|
| `post_public_data(json_path)` | 发送数据到接入点服务器 |
| `add_friend_agent(aid, name, description, avaUrl)` | 添加好友 Agent |
| `get_friend_agent_list()` | 获取好友 Agent 列表 |
| `get_agent_list()` | 获取所有 AgentID 列表 |
| `get_all_public_data()` | 获取所有 AgentID 的公共数据 |
| `get_session_member_list(session_id)` | 获取指定会话的成员列表 |
| `update_aid_info(aid, avaUrl, name, description)` | 更新 Agent 的信息 |

## 微信支持
如需技术交流或问题咨询，欢迎添加开发者微信：

![WeChat QR Code](assets/images/wechat_qr.png) <!-- 请将二维码图片放在指定路径 -->

📮 问题反馈: 19169495461@163.com

## 许可证

MIT © 2025

---

📮 问题反馈: 19169495461@163.com

        