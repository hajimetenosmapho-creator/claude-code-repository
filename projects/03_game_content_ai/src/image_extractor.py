"""
RSSエントリーから画像URL候補を抽出するモジュール。

著作権上の注意：
  取得した画像URLは「候補」として記録するだけにとどめる。
  外部サイトの画像を自サーバーへアップロードする場合は、
  各サイトの利用規約・著作権を個別に確認すること。
"""


def extract_image_url(entry) -> str:
    """
    feedparser のエントリーから画像URLを1件抽出して返す。
    取得できない場合は空文字を返す（例外は発生させない）。

    試みる順序：
      1. media:thumbnail
      2. enclosures（image/* タイプ）
      3. media:content（medium="image"）

    Args:
        entry: feedparser が解析したエントリーオブジェクト

    Returns:
        str: 画像URL。取得できない場合は空文字。
    """
    try:
        # 1. media:thumbnail（多くのニュースサイトが対応）
        thumbnails = getattr(entry, "media_thumbnail", [])
        if thumbnails and isinstance(thumbnails, list):
            url = thumbnails[0].get("url", "")
            if url:
                return url

        # 2. enclosures（image/* タイプのみ対象）
        enclosures = getattr(entry, "enclosures", [])
        for enc in enclosures:
            if enc.get("type", "").startswith("image/"):
                url = enc.get("href", "")
                if url:
                    return url

        # 3. media:content（medium="image" のみ対象）
        media_contents = getattr(entry, "media_content", [])
        for mc in media_contents:
            if mc.get("medium") == "image":
                url = mc.get("url", "")
                if url:
                    return url

    except Exception:
        pass

    return ""
