import os
from browser_use import Agent, Browser, BrowserConfig
from langchain_openai import ChatOpenAI, OpenAI
import asyncio

# Configure the browser to connect to your Chrome instance
browser = Browser(
    config=BrowserConfig(
        # Specify the path to your Chrome executable
        # browser_binary_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",  # macOS path
        # For Windows, typically: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
        # For Linux, typically: '/usr/bin/google-chrome'
        keep_alive=True,  # Keep the browser alive after the script ends
    )
)
llm = ChatOpenAI(
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    model="qwen-plus",
    api_key=os.getenv("DASHSCOPE_API_KEY"),
)

# Create the agent with your configured browser
agent = Agent(
    task="打开京东，搜索“iphone15”，找一个价格最便宜的，但不要2手的手机，然后打开它的详情页",
    llm=llm,
    browser=browser,
    planner_llm=llm,
    page_extraction_llm=llm,
    # 配置浏览器的代理
)


async def main():
    await agent.run()

    input("Press Enter to close the browser...")
    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
