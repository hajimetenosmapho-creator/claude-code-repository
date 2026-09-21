"""
RSSフィードからゲームニュースを収集するモジュール。
"""

import ipaddress
import json
import os
import re
import unicodedata
from urllib.parse import urlsplit

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

NEWS_RSS_FEED_URLS_OVERRIDE_ENV = "NEWS_RSS_FEED_URLS_OVERRIDE"

_IPV4_SHAPE_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
_DNS_HOSTNAME_RE = re.compile(
    r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*$"
)
_NUMERIC_LABEL_RE = re.compile(r"^[0-9]+$")
_HEX_LABEL_RE = re.compile(r"^0x[0-9a-f]+$")
_BAD_PERCENT_RE = re.compile(r"%(?![0-9A-Fa-f]{2})")


def _reject_duplicate_keys(pairs: list) -> dict:
    """JSONオブジェクトのキー重複をfail-closedに拒否するobject_pairs_hook。"""
    seen: set = set()
    for key, _ in pairs:
        if key in seen:
            raise ValueError(
                f"NEWS_RSS_FEED_URLS_OVERRIDEに重複キーが含まれています: {key!r}"
            )
        seen.add(key)
    return dict(pairs)


def _validate_feed_url(value) -> str:
    """1件のfeed URL値を検証し、trimmed値をcanonical resultとして返す。"""
    if type(value) is not str:
        raise ValueError("feed URLは文字列である必要があります")

    trimmed = value.strip()
    if trimmed == "":
        raise ValueError("feed URLが空です")

    for ch in trimmed:
        if (
            ch.isspace()
            or ord(ch) < 0x20
            or ord(ch) == 0x7F
            or unicodedata.category(ch) in ("Cc", "Cf")
        ):
            raise ValueError("feed URLに空白または制御文字が含まれています")

    if not (trimmed.startswith("http://") or trimmed.startswith("https://")):
        raise ValueError("feed URLはhttp://またはhttps://で始まる必要があります")

    parsed = urlsplit(trimmed)

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("feed URLにhostnameが含まれていません")

    if _IPV4_SHAPE_RE.match(hostname):
        try:
            ipaddress.IPv4Address(hostname)
        except ValueError:
            raise ValueError("feed URLのhostnameが不正なIPv4アドレスです")
    else:
        if len(hostname) > 253 or not _DNS_HOSTNAME_RE.match(hostname):
            raise ValueError("feed URLのhostnameが不正なDNSホスト名です")
        for label in hostname.split("."):
            if _NUMERIC_LABEL_RE.match(label) or _HEX_LABEL_RE.match(label):
                raise ValueError(
                    "feed URLのhostnameラベルがIPv4代替表記の疑いがあり拒否されました"
                )

    if _BAD_PERCENT_RE.search(trimmed):
        raise ValueError("feed URLに不正なpercent-escapeが含まれています")

    host_port = parsed.netloc.rpartition("@")[2]
    if host_port.endswith(":"):
        raise ValueError("feed URLのportが明示的に空です")

    try:
        port = parsed.port
    except ValueError:
        raise ValueError("feed URLのportが不正です")

    if port is not None and port == 0:
        raise ValueError("feed URLのportに0は使用できません")

    return trimmed


def _resolve_rss_feeds() -> dict:
    """
    NEWS_RSS_FEED_URLS_OVERRIDEが未設定ならRSS_FEEDSをそのまま返す。
    設定されている場合はJSONとしてvalidationした上で置き換えたdictを返す（fail-closed）。
    """
    override = os.environ.get(NEWS_RSS_FEED_URLS_OVERRIDE_ENV)
    if override is None:
        return RSS_FEEDS

    parsed = json.loads(override, object_pairs_hook=_reject_duplicate_keys)

    if not isinstance(parsed, dict) or set(parsed.keys()) != set(RSS_FEEDS.keys()):
        raise ValueError(
            "NEWS_RSS_FEED_URLS_OVERRIDEはRSS_FEEDSと完全に一致する16キーを持つ"
            "JSONオブジェクトである必要があります"
        )

    return {key: _validate_feed_url(value) for key, value in parsed.items()}


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

    feeds = _resolve_rss_feeds()
    for source_name, feed_url in feeds.items():
        items, stats = fetch_from_feed(source_name, feed_url, max_items_per_feed)
        all_items.extend(items)
        all_stats.append(stats)

    return all_items, all_stats
