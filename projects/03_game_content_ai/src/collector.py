"""
RSSフィードからゲームニュースを収集するモジュール。
"""

import feedparser
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional
from image_extractor import extract_image_url


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


@dataclass
class FeedStats:
    source: str
    count: int
    status: str        # "ok" / "error" / "empty"
    error_message: str = ""


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
    "Steam": "https://store.steampowered.com/feeds/news/?l=japanese",
}

FEED_GROUPS = {
    "日本語": ["4Gamer", "Game*Spark"],
    "公式": ["PlayStation公式", "Nintendo公式", "Xbox公式", "Steam"],
    "総合英語": ["IGN", "GameSpot", "Eurogamer", "Gematsu",
                 "VGC", "Insider Gaming", "PC Gamer"],
    "プラットフォーム特化": ["Nintendo Life", "Push Square", "Pure Xbox"],
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


def fetch_from_feed(source_name: str, feed_url: str, max_items: int = 20) -> tuple[list[NewsItem], FeedStats]:
    """
    指定されたRSSフィードからニュースを取得して NewsItem のリストと FeedStats を返す。

    Args:
        source_name: ニュースソース名（例: "4Gamer"）
        feed_url: RSSフィードのURL
        max_items: 取得する最大件数

    Returns:
        (NewsItem のリスト, FeedStats)
    """
    try:
        feed = feedparser.parse(feed_url)

        if feed.bozo and not feed.entries:
            return [], FeedStats(source_name, 0, "error", "RSSの取得・解析に問題があります")

        items = []
        for entry in feed.entries[:max_items]:
            title = getattr(entry, "title", "").strip()
            url = getattr(entry, "link", "").strip()

            if not title or not url:
                continue

            image_url = extract_image_url(entry)
            item = NewsItem(
                title=title,
                url=url,
                summary=_extract_summary(entry),
                source=source_name,
                published_at=_parse_published(entry),
                image_candidates=[image_url] if image_url else [],
            )
            items.append(item)

        status = "empty" if len(items) == 0 else "ok"
        return items, FeedStats(source_name, len(items), status)

    except Exception as e:
        return [], FeedStats(source_name, 0, "error", str(e))


def collect_all_news(max_items_per_feed: int = 20) -> tuple[list[NewsItem], list[FeedStats]]:
    """
    全RSSフィードからニュースを収集して一覧と取得統計を返す。

    Args:
        max_items_per_feed: フィードごとの最大取得件数

    Returns:
        (全ソースの NewsItem リスト, 各フィードの FeedStats リスト)
    """
    print("ニュースを収集しています...")
    all_items: list[NewsItem] = []
    all_stats: list[FeedStats] = []

    for source_name, feed_url in RSS_FEEDS.items():
        items, stats = fetch_from_feed(source_name, feed_url, max_items_per_feed)
        all_items.extend(items)
        all_stats.append(stats)

    return all_items, all_stats
