github
```language
https://
```


** 说明文档 README.md **
基于 agentcp 库实现了一个串并行调用的智能体（Agent），支持消息处理、工具检索、多工具并行调用以及与外部Agent的通信。
# 1. 主要功能
## 1.1 智能体搜索
接收自然语言文本消息，根据文本消息进行相关智能体搜索，获取可能用到的智能体列表。
## 1.2 工具选择与调用
  - 将智能体列表（工具）发送给大模型（llm_agent_id）进行决策。
  - 执行选中的工具并返回结果。
## 1.3 多智能体（Agent）协作
  - 支持跨Agent通信，通过aid标识调用其他Agent的服务。~~

---
# 2. 代码结构解析
```bash
├── main.py       # 核心业务逻辑
├── create_profile.py   # 智能体配置文件生成
```
## 2.1 核心类 `Agent`
#### 初始化方法 `__init__`
- 初始化Agent ID、`agentcp`实例和大模型Agent标识。
- 依赖数据目录：`../data`（无需预先配置，会自动生成）。
## 2.2 主要方法
#### 1. `async_message_handler`
- **功能**：异步处理接收到的消息。
- 流程：
  1. 检查消息接收者是否为当前Agent。
  2. 提取消息内容并调用工具选择逻辑。

#### 2. `mult_tool_choose`
- **功能**：收集可用工具信息并发送给大模型。
- 工具信息包括：
  - `aid`（Agent唯一标识）
  - `name`（工具名称）
  - `description`（工具描述）

#### 3. `mult_tool_call`
- **功能**：执行大模型返回的工具调用请求。
- 遍历工具调用列表，异步发送请求并处理结果。

#### 4. `reply_message_handler`
- **功能**：处理大模型的返回结果。
- 根据返回类型决定是否继续调用工具或直接回复消息。

---

# 3. 使用方法
### 依赖项
```python
pip install agentcp  # 需确保 agentcp 库可用
```
### 启动Agent
```python
python main.py
