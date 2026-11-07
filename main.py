import os
import datetime
import time
import hmac
import hashlib
import base64
import feedparser
import requests
import json

# ==================== 1. 配置与环境变量 ====================
RSS_FEEDS = [
    "https://openai.com/news/rss.xml",
    "https://dair.ai/feed.xml",
    "https://rsshub.app/hackernews",
]

LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

# 飞书相关配置
WEBHOOK_URL = os.getenv("FEISHU_WEBHOOK_URL")
SECRET = os.getenv("FEISHU_SECRET")


# ==================== 2. RSS 抓取逻辑 ====================
def get_latest_articles(hours=24):
    """获取过去 24 小时内的 RSS 文章列表"""
    articles = []
    now = datetime.datetime.now(datetime.timezone.utc)
    threshold = now - datetime.timedelta(hours=hours)

    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                published_parsed = entry.get("published_parsed") or entry.get("updated_parsed")
                if published_parsed:
                    published_dt = datetime.datetime(*published_parsed[:6], tzinfo=datetime.timezone.utc)
                    if published_dt > threshold:
                        articles.append({
                            "title": entry.title,
                            "link": entry.link,
                            "summary": entry.get("summary", "")[:500]
                        })
        except Exception as e:
            print(f"解析 RSS 发生错误 ({feed_url}): {e}")
    return articles


# ==================== 3. 大模型摘要生成逻辑 ====================
def summarize_with_llm(articles):
    """使用大语言模型处理文章内容摘要"""
    if not articles:
        return "今日暂无关注的最新 AI 资讯。"

    # 使用 OpenAI SDK
    from openai import OpenAI
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

    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"LLM 调用失败: {e}")
        return "生成 AI 摘要时发生错误。"


# ==================== 4. 飞书加签与安全推送逻辑 ====================
def gen_sign(secret, timestamp):
    """根据时间戳和 Secret 计算飞书签名"""
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256
    ).digest()
    sign = base64.b64encode(hmac_code).decode("utf-8")
    return sign

def send_feishu_message(markdown_content):
    if not WEBHOOK_URL or not SECRET:
        print("错误：未找到 FEISHU_WEBHOOK_URL 或 FEISHU_SECRET 环境变量。")
        return

    timestamp = str(int(time.time()))
    sign = gen_sign(SECRET, timestamp)

    headers = {
        "Content-Type": "application/json"
    }
    
    # 飞书 Markdown 文本消息格式
    payload = {
        "timestamp": timestamp,
        "sign": sign,
        "msg_type": "interactive", # 使用卡片消息可以获得更好的 Markdown 排版
        "card": {
            "config": {
                "wide_screen_mode": True
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": markdown_content
                }
            ],
            "header": {
                "template": "blue",
                "title": {
                    "content": "🤖 每日 AI 行业资讯速报",
                    "tag": "plain_text"
                }
            }
        }
    }

    response = requests.post(WEBHOOK_URL, headers=headers, data=json.dumps(payload))
    
    if response.status_code == 200:
        print("飞书资讯推送成功！")
    else:
        print(f"推送失败，状态码: {response.status_code}, 内容: {response.text}")


# ==================== 5. 主程序入口 ====================
if __name__ == "__main__":
    print("1. 开始抓取最新 RSS 资讯...")
    items = get_latest_articles(hours=24)
    print(f"抓取完成，共找到 {len(items)} 条新更新。")

    if items:
        print("2. 正在调用大模型生成摘要...")
        summary = summarize_with_llm(items)
        
        print("3. 正在计算签名并通过飞书推送...")
        send_feishu_message(summary)
    else:
        print("今日暂无新资讯，跳过推送。")