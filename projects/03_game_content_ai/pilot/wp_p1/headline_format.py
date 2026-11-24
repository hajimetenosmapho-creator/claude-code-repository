"""WP-P1 1.1節の見出し整形関数。

標準ライブラリだけを使い、ファイル・ネットワーク等の入出力は行わない。
"""

ELLIPSIS = "…"  # 「…」（1文字）


def normalize_headline(text, max_length=60) -> str:
    """見出しの空白を整え、max_length を超える場合は末尾を「…」で切り詰める。"""
    # 1. text の型チェック（最初に行う）
    if not isinstance(text, str):
        raise TypeError("text must be a str")

    # 2. max_length のチェック
    if not isinstance(max_length, int) or max_length < 1:
        raise ValueError("max_length must be an int of 1 or more")

    # 3. 空白の整形（前後の空白を除き、連続する空白を半角スペース1つにまとめる）
    normalized = " ".join(text.split())

    # 4. 長さが上限以内ならそのまま返す（空の場合は "" になる）
    if len(normalized) <= max_length:
        return normalized

    # 5. 上限を超える場合は切り詰め、末尾の半角スペースを除いて「…」を付ける
    return normalized[:max_length - 1].rstrip(" ") + ELLIPSIS
