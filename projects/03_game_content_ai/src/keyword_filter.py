"""
Claude API呼び出し前にキーワードでニュースを事前スクリーニングするモジュール。
大量ニュース取得時のAPI使用量・コストを削減するのが目的。
"""

from collector import NewsItem

# 優先キーワード：これらを含む記事はフィルター通過
PRIORITY_KEYWORDS = [
    # ハード・機種名
    "nintendo", "switch", "playstation", "ps5", "ps6",
    "xbox", "series x", "series s",
    # 周辺機器・デバイス
    "controller", "コントローラー", "gaming device", "ゲーミングデバイス",
    "accessory", "周辺機器", "headset", "ヘッドセット",
    # 日本語ハード名
    "任天堂", "プレイステーション", "スイッチ",
    # 評価・レビュー
    "review", "レビュー",
    # 購入系
    "発売", "予約", "価格", "セール", "発表",
]

# 除外キーワード：タイトルにこれらしか含まない場合は除外
SKIP_KEYWORDS = [
    "esports", "eスポーツ", "tournament", "トーナメント",
    "mobile game", "スマホゲー", "スマホゲーム", "モバイルゲーム",
]

# 除外対象の判定に使うパターン
SKIP_ONLY_PATTERNS = [
    # eスポーツ大会結果（ゲーム機名が含まれていない場合）
    ["esports", "tournament"],
    ["esports", "championship"],
    ["eスポーツ", "トーナメント"],
    # モバイルのみ
    ["mobile", "ios", "android"],
    ["スマホ", "ios", "android"],
]


def _normalize(text: str) -> str:
    return text.lower().strip()


def _contains_priority_keyword(text: str) -> bool:
    normalized = _normalize(text)
    return any(kw in normalized for kw in PRIORITY_KEYWORDS)


def _is_skip_only(title: str, summary: str) -> bool:
    """明らかに無関係なニュースかどうかを判定する。"""
    combined = _normalize(title + " " + summary)

    # SKIP_ONLYパターンのいずれかに完全一致し、かつ優先キーワードを含まない場合
    for pattern in SKIP_ONLY_PATTERNS:
        if all(kw in combined for kw in pattern):
            if not _contains_priority_keyword(combined):
                return True
    return False


def filter_news(news_list: list[NewsItem]) -> dict:
    """
    ニュースリストをキーワードでフィルタリングする。

    Args:
        news_list: collector.py から取得した NewsItem のリスト

    Returns:
        dict: {
            "pass": 通過したニュースのリスト（重要度判定へ進む）,
            "pending": 保留ニュースのリスト（低優先）,
            "skip": 除外したニュースのリスト
        }
    """
    passed = []
    pending = []
    skipped = []

    for item in news_list:
        combined_text = item.title + " " + item.summary

        if _is_skip_only(item.title, item.summary):
            skipped.append(item)
        elif _contains_priority_keyword(combined_text):
            passed.append(item)
        else:
            pending.append(item)

    print(f"キーワードフィルター結果：")
    print(f"  通過（重要度判定へ）: {len(passed)} 件")
    print(f"  保留（低優先）      : {len(pending)} 件")
    print(f"  除外               : {len(skipped)} 件\n")

    return {
        "pass": passed,
        "pending": pending,
        "skip": skipped,
    }
