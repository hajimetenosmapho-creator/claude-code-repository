"""
URLの正規化と重複ニュース排除モジュール。
collector.py はRSS取得のみに責務を限定するため、
重複判定はこのファイルで行う。
"""

from urllib.parse import urlparse, urlencode, parse_qsl, urlunparse
from collector import NewsItem


def normalize_url(url: str) -> str:
    """
    URLを正規化して比較しやすい形式に統一する。
    - 末尾スラッシュを除去
    - utm_* パラメータを除去
    """
    parsed = urlparse(url)

    filtered_params = [
        (k, v) for k, v in parse_qsl(parsed.query)
        if not k.startswith("utm_")
    ]
    normalized_query = urlencode(filtered_params)

    path = parsed.path.rstrip("/")

    return urlunparse((
        parsed.scheme,
        parsed.netloc,
        path,
        parsed.params,
        normalized_query,
        "",
    ))


def deduplicate_news(news_list: list[NewsItem]) -> list[NewsItem]:
    """
    URLが重複するニュースを除去する。
    URLは normalize_url() で正規化してから比較する。
    同じURLが複数のRSSフィードから取得された場合、最初の1件のみ残す。
    """
    seen_urls: set[str] = set()
    deduped: list[NewsItem] = []

    for item in news_list:
        key = normalize_url(item.url)
        if key not in seen_urls:
            seen_urls.add(key)
            deduped.append(item)

    removed = len(news_list) - len(deduped)
    if removed > 0:
        print(f"  重複排除：{len(news_list)}件 → {len(deduped)}件（{removed}件を除去）")

    return deduped
