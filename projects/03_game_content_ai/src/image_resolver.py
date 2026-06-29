"""
アイキャッチ画像候補URLを解決するモジュール。

v1.4.0: image_candidates の先頭URLを返すのみ。
v1.6.0: resolve_media_id() 追加。デフォルト画像（DEFAULT_MEDIA_ID）対応。
v1.7.0以降: 権利確認済み画像・AI生成画像への切り替えをここで担う。
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


def resolve_media_id(item: NewsItem, default_media_id: int) -> int:
    """
    WordPress に設定する featured_media の ID を返す。

    現時点では RSS 画像の無断アップロードを避けるため、
    image_terms_confirmed が True の画像のみアップロード対象とする。
    v1.6.0 では全 RSS 画像が未確認（False）のため、常にデフォルト値を返す。

    将来の拡張:
        v1.7.0: image_terms_confirmed == True の場合に MediaUploader 経由でアップロード

    Args:
        item: 対象の NewsItem
        default_media_id: .env の DEFAULT_MEDIA_ID。0 の場合はアイキャッチなし。

    Returns:
        int: WordPress media_id。0 の場合は featured_media を設定しない。
    """
    if item.image_terms_confirmed:
        # 将来（v1.7.0）: アップロード済み画像の media_id をここで返す
        pass
    return default_media_id
