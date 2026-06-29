"""
アイキャッチ画像候補URLを解決するモジュール。

v1.4.0: image_candidates の先頭URLを返すのみ。
v1.5.0以降: デフォルト画像・権利確認済み画像・AI生成画像への切り替えをここで担う。
"""

from collector import NewsItem


def resolve_featured_image(item: NewsItem) -> str:
    """
    NewsItem からアイキャッチ画像URLを1件選んで返す。
    候補が存在しない場合は空文字を返す。

    Args:
        item: 対象の NewsItem

    Returns:
        str: 使用する画像URL。候補なしの場合は空文字。
    """
    if item.image_candidates:
        return item.image_candidates[0]
    return ""
