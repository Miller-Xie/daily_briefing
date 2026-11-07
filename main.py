import os
import datetime
import time
import feedparser
import requests
from openai import OpenAI

# 1. 配置 RSS 订阅源列表（可自行增删）
RSS_FEEDS = [
    "https://openai.com/news/rss.xml",
    "https://dair.ai/feed.xml",
    "https://rsshub.app/hackernews",
]

# 配置环境变量
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini") # 也可换为 deepseek-chat 或 gemini-2.5-flash
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

def get_latest_articles(hours=24):
    """获取过去 24 小时内的 RSS 文章列表"""
    articles = []
    now = datetime.datetime.now(datetime.timezone.utc)
    threshold = now - datetime.timedelta(hours=hours)

    for feed_url in RSS_FEEDS:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries:
            # 解析时间（部分源格式可能略有不同）
            published_parsed = entry.get("published_parsed") or entry.get("updated_parsed")
            if published_parsed:
                published_dt = datetime.datetime(*published_parsed[:6], tzinfo=datetime.timezone.utc)
                if published_dt > threshold:
                    articles.append({
                        "title": entry.title,
                        "link": entry.link,
                        "summary": entry.get("summary", "")[:500]  # 节选前500字符
                    })
    return articles

def summarize_with_llm(articles):
    """使用大语言模型处理文章内容摘要"""
    if not articles:
        return "今日暂无关注的最新 AI 资讯。"

    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)

    content_to_prompt = "\n".join([
        f"- 标题: {a['title']}\n  链接: {a['link']}\n  简介: {a['summary']}"
        for a in articles[:10]  # 控制推送数量，避免 Prompt 过长
    ])

    prompt = f"""
你是一名 AI 行业研究员。请阅读以下今日抓取到的 AI 资讯列表，生成一份格式精美的每日速报：

资讯列表：
{content_to_prompt}

要求：
1. 用 Markdown 格式输出。
2. 过滤掉无意义的广告或非科技类新闻。
3. 对每篇保留的文章，保留原链接，并用 1~2 句话总结其核心突破或行业价值。
4. 语言使用简练专业的中文。
"""

    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )

    return response.choices[0].message.content

def send_push(message):
    """通过 Webhook 推送至 Telegram 或企业微信/飞书/钉钉"""
    if not WEBHOOK_URL:
        print("未设置 WEBHOOK_URL，跳过推送：\n", message)
        return

    # 示例：Telegram Bot Webhook 格式（如果是飞书/企微需替换对应的 JSON 字段）
    payload = {
        "text": f"🤖 **每日 AI 资讯速报**\n\n{message}",
        "parse_mode": "Markdown"
    }
    
    response = requests.post(WEBHOOK_URL, json=payload)
    if response.status_code == 200:
        print("推送成功！")
    else:
        print(f"推送失败，状态码: {response.status_code}, 内容: {response.text}")
``
if __name__ == "__main__":
    print("开始抓取最新资讯...")
    items = get_latest_articles(hours=24)
    print(f"抓取完成，共找到 {len(items)} 条新更新。")

    if items:
        print("正在生成 AI 摘要...")
        summary = summarize_with_llm(items)
        print("正在发送推送消息...")``
        send_push(summary)
    else:
        print("没有可更新的内容。")