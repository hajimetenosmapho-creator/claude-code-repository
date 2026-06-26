"""
RSSフィードからゲームニュースを収集するモジュール。
"""

import feedparser
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class NewsItem:
    title: str
    url: str
    summary: str
    source: str
    published_at: str
    official_news_url: str = ""
    official_site_url: str = ""
    official_trailer_url: str = ""
    official_presskit_url: str = ""
    image_candidates: list = field(default_factory=list)
    image_source: str = ""
    image_terms_confirmed: bool = False


RSS_FEEDS = {
    "4Gamer": "https://www.4gamer.net/rss/index.xml",
    "Game*Spark": "https://www.gamespark.jp/rss/index.rdf",
    "IGN": "https://feeds.feedburner.com/ign/news",
    "GameSpot": "https://www.gamespot.com/feeds/news/",
    "Eurogamer": "https://www.eurogamer.net/?format=rss",
    "PlayStation公式": "https://www.playstation.com/ja-jp/rss/blog.xml",
    "Nintendo公式": "https://topics.nintendo.co.jp/rss.xml",
    "Xbox公式": "https://news.xbox.com/en-us/feed/",
    "Gematsu": "https://www.gematsu.com/feed",
    "VGC": "https://www.videogameschronicle.com/feed/",
    "Insider Gaming": "https://insider-gaming.com/feed/",
    "PC Gamer": "https://www.pcgamer.com/rss/",
    "Nintendo Life": "https://www.nintendolife.com/feeds/latest",
    "Push Square": "https://www.pushsquare.com/feeds/latest",
    "Pure Xbox": "https://www.purexbox.com/feeds/latest",
}


def _parse_published(entry) -> str:
    """feedparserのエントリーから公開日時を文字列で取得する。"""
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%S")
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _extract_summary(entry, max_length: int = 500) -> str:
    """エントリーから本文抜粋を取得する。"""
    summary = ""
    if hasattr(entry, "summary"):
        summary = entry.summary
    elif hasattr(entry, "description"):
        summary = entry.description

    # HTMLタグを簡易除去
    import re
    summary = re.sub(r"<[^>]+>", "", summary)
    summary = summary.strip()

    return summary[:max_length] if len(summary) > max_length else summary


def fetch_from_feed(source_name: str, feed_url: str, max_items: int = 20) -> list[NewsItem]:
    """
    指定されたRSSフィードからニュースを取得して NewsItem のリストを返す。

    Args:
        source_name: ニュースソース名（例: "4Gamer"）
        feed_url: RSSフィードのURL
        max_items: 取得する最大件数

    Returns:
        NewsItem のリスト（取得失敗時は空リスト）
    """
    try:
        feed = feedparser.parse(feed_url)

        if feed.bozo and not feed.entries:
            print(f"  [警告] {source_name}: RSSの取得・解析に問題があります")
            return []

        items = []
        for entry in feed.entries[:max_items]:
            title = getattr(entry, "title", "").strip()
            url = getattr(entry, "link", "").strip()

            if not title or not url:
                continue

            item = NewsItem(
                title=title,
                url=url,
                summary=_extract_summary(entry),
                source=source_name,
                published_at=_parse_published(entry),
            )
            items.append(item)

        print(f"  [{source_name}] {len(items)}件取得")
        return items

    except Exception as e:
        print(f"  [エラー] {source_name}: {e}")
        return []


def collect_all_news(max_items_per_feed: int = 20) -> list[NewsItem]:
    """
    全RSSフィードからニュースを収集して一覧を返す。

    Args:
        max_items_per_feed: フィードごとの最大取得件数

    Returns:
        全ソースのニュースをまとめた NewsItem のリスト
    """
    print("ニュースを収集しています...")
    all_items = []

    for source_name, feed_url in RSS_FEEDS.items():
        items = fetch_from_feed(source_name, feed_url, max_items_per_feed)
        all_items.extend(items)

    print(f"\n合計 {len(all_items)} 件のニュースを取得しました。\n")
    return all_items
