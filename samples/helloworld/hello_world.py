# coding:utf-8
# @Time    : 2025/5/3 下午1:46
# @File    : am.py
# @Project : main.py

# Description：
'''
1.创建身份
2.选择一个身份登录
3.任何请求,都回复"hello world"
'''
import agentcp

if __name__ == "__main__":
    print(f"\n开始:agentcp版本:{agentcp.__version__},{__file__}")
    #以当前文件夹为acp根路径
    acp = agentcp.AgentCP(".",seed_password="888777")
    llrecv = acp.create_aid("agentunion.cn","name1")
    @llrecv.message_handler()
    async def sync_message_handler(msg):
        print("收到消息:", msg)
        llrecv.reply_message(msg, "hello world")
        return True

    
    llrecv.online()
    # 最简单的实现方式
    llsend = acp.create_aid("agentunion.cn","name2")
    @llsend.message_handler()
    async def sync_message_handler_test(msg):
        llsend.reply_message(msg, "hello world")
        return True
    llsend.online()
    while True:
        user_input = input("请输入内容：")
        print("您输入的内容是：", user_input)
        llsend.quick_send_messsage_content(llrecv.id,user_input,sync_message_handler_test)
    exit(2)


