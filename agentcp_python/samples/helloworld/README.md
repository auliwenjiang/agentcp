```markdown:d:\github_agentcp\samples\helloworld\README.md
## 功能简介
该Agent基于`agentcp`库构建的hello world示例，主要演示以下功能：

- 创建两个基础Agent身份（name1/name2）
- 实现Agent间的消息接收与回复
- 控制台输入消息的测试能力
- 固定回复"hello world"的简单交互逻辑
```

2. **使用方法更新**（新增交互测试部分）：
```markdown:d:\github_agentcp\samples\helloworld\README.md
## 使用方法

// ... existing code ...

5. 控制台交互测试
```python
while True:
    user_input = input("请输入内容：")
    print("您输入的内容是：", user_input)
    llsend.quick_send_messsage_content(llrecv.id, user_input, sync_message_handler_test)
```

3. **完整示例代码更新**（保持与hello_world.py一致）：
```markdown:d:\github_agentcp\samples\helloworld\README.md
## 完整示例代码
```python
# coding:utf-8
import agentcp

if __name__ == "__main__":
    print(f"\n开始:agentcp版本:{agentcp.__version__},{__file__}")
    # 以当前文件夹为acp根路径
    acp = agentcp.AgentCP(".", seed_password="888777")
    
    # 创建接收者Agent
    llrecv = acp.create_aid("agentunion.cn","name1")
    
    @llrecv.message_handler()
    async def sync_message_handler(msg):
        print("收到消息:", msg)
        llrecv.reply_message(msg, "hello world")
        return True
    
    llrecv.online()
    
    # 创建发送者Agent
    llsend = acp.create_aid("agentunion.cn","name2")
    
    @llsend.message_handler()
    async def sync_message_handler_test(msg):
        llsend.reply_message(msg, "hello world")
        return True
        
    llsend.online()
    
    # 控制台交互测试
    while True:
        user_input = input("请输入内容：")
        llsend.quick_send_messsage_content(llrecv.id, user_input, sync_message_handler_test)
```

主要修改点说明：
1. 移除了原README中关于qwen2大模型和openai调用的相关内容
2. 新增了双Agent架构的说明
3. 保持与hello_world.py一致的create_aid创建方式
4. 补充了控制台交互测试流程说明