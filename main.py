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
    # ==================== 国内权威与前沿信源 ====================
    # 机器之心 (国内最顶尖的 AI 垂直媒体之一)
    "https://www.jiqizhixin.com/rss",
    # 量子位 (专注于 AI 与前沿科技的专业媒体)
    "https://www.qbitai.com/feed",
    # 极客公园 (科技商业与 AI 落地结合)
    "https://www.geekpark.net/rss",

    # ==================== 海外顶级原厂与研究博客 ====================
    # OpenAI 官方动态
    "https://openai.com/news/rss.xml",
    # Anthropic 官方动态 (Claude 背后团队)
    "https://www.anthropic.com/feed.xml",
    # Google DeepMind 官方博客
    "https://deepmind.google/blog/rss.xml",
    # Meta AI 官方博客 (Llama 系列开源阵地)
    "https://ai.meta.com/blog/rss.xml",

    # ==================== 学术、开源与社区讨论 ====================
    # Hugging Face 博客 (开源模型与社区动态)
    "https://huggingface.co/blog/feed.xml",
    # Papers with Code (最新热门 AI 论文追踪)
    "https://paperswithcode.com/rss/",
    # Hacker News (全球程序员与 AI 开发者最活跃的讨论区，通过 RSSHub 代理)
    "https://rsshub.app/hackernews",
]

LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

# 飞书相关配置
WEBHOOK_URL = os.getenv("FEISHU_WEBHOOK_URL")
SECRET = os.getenv("FEISHU_SECRET")


import datetime

# 定义北京时区 (UTC+8)
BEIJING_TZ = datetime.timezone(datetime.timedelta(hours=8))

def get_latest_articles():
    """严格获取‘北京时间昨天’（00:00:00 到 23:59:59）的 RSS 文章列表"""
    articles = []
    
    # 1. 获取当前北京时间
    now_beijing = datetime.datetime.now(BEIJING_TZ)
    
    # 2. 计算北京时间昨天的日期，并设定北京时间的全天起止范围
    yesterday_date = now_beijing.date() - datetime.timedelta(days=1)
    start_of_yesterday = datetime.datetime.combine(yesterday_date, datetime.time.min, tzinfo=BEIJING_TZ)
    end_of_yesterday = datetime.datetime.combine(yesterday_date, datetime.time.max, tzinfo=BEIJING_TZ)
    
    print(f"正在抓取北京时间 {yesterday_date} 全天的资讯...")

    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                published_parsed = entry.get("published_parsed") or entry.get("updated_parsed")
                if published_parsed:
                    # feedparser 解析出来的时间通常是 UTC 时间，将其转换为北京时间进行对比
                    published_dt_utc = datetime.datetime(*published_parsed[:6], tzinfo=datetime.timezone.utc)
                    published_dt_beijing = published_dt_utc.astimezone(BEIJING_TZ)
                    
                    # 检查文章发布时间是否严格落在“北京时间昨天”的范围内
                    if start_of_yesterday <= published_dt_beijing <= end_of_yesterday:
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
你是一名 AI 行业研究员。请阅读以下今日抓取到的 AI 资讯列表，生成一份适合在飞书群聊中展示的简报：

资讯列表：
{content_to_prompt}

要求：
1. **绝对不要使用 `#`、`##` 或 `###` 等 Markdown 标题符号**（因为飞书卡片不支持）。
2. 如需分节或突出分类，请使用 **加粗文本**（例如 `**【前沿研究】**`）来代替标题。
3. 过滤掉无意义的广告或非科技类新闻。
4. 对每篇保留的文章，必须保留原链接（格式为 [文章标题](链接)），并用 1~2 句话精炼总结其核心突破或行业价值。
5. 语言使用简练专业的中文。
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
    items = get_latest_articles()
    print(f"抓取完成，共找到 {len(items)} 条新更新。")

    if items:
        print("2. 正在调用大模型生成摘要...")
        summary = summarize_with_llm(items)
        
        print("3. 正在计算签名并通过飞书推送...")
        send_feishu_message(summary)
    else:
        print("今日暂无新资讯，跳过推送。")