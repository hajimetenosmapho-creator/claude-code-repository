"""
SEOタイトルからWordPress用のslugを生成するモジュール。
"""

import re


def generate_slug(seo_title: str, date_str: str) -> str:
    """
    SEOタイトルからWordPress用のslugを生成する。

    ASCII英数字部分を抽出してケバブケースに変換し、
    末尾に日付文字列を付けて一意性を保証する。

    例:
        "【速報】PS6はNintendo Switch型に？ソニー次世代機の噂"
        → "ps6-nintendo-switch-20260630"

        英字が取れない場合:
        → "article-20260630"

    Args:
        seo_title: SEOタイトル文字列
        date_str:  日付文字列（例: "20260630"）

    Returns:
        str: WordPress slug（小文字英数字・ハイフンのみ）
    """
    # 非ASCII文字をスペースに変換してASCII部分だけ残す
    ascii_text = re.sub(r'[^\x00-\x7F]+', ' ', seo_title)
    # 英数字・スペース以外（記号類）を除去し、小文字化
    cleaned = re.sub(r'[^a-zA-Z0-9\s]', '', ascii_text).lower()
    # 連続スペース・ハイフンを単一ハイフンに変換
    slug_base = re.sub(r'\s+', '-', cleaned.strip()).strip('-')
    # 連続ハイフンを1つに正規化
    slug_base = re.sub(r'-+', '-', slug_base)

    # 最大30文字で切り詰め（単語境界を優先）
    if len(slug_base) > 30:
        truncated = slug_base[:30]
        cut = truncated.rfind('-')
        slug_base = truncated[:cut] if cut > 0 else truncated

    # 末尾のハイフンを除去
    slug_base = slug_base.strip('-')

    if slug_base:
        return f"{slug_base}-{date_str}"
    return f"article-{date_str}"
