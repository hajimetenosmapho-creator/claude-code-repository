"""WP-P2 1.1節：プレイ時間（分）を日本語の文字列に整形する。"""


def format_playtime(minutes) -> str:
    """分数を「X時間Y分」形式の文字列に変換する。"""
    # 手順1：int以外（bool・float・strを含む）はTypeError
    if type(minutes) is not int:
        raise TypeError("minutes must be int")

    # 手順2：負数はValueError
    if minutes < 0:
        raise ValueError("minutes must not be negative")

    # 手順3：時間と分に分ける
    hours, mins = divmod(minutes, 60)

    # 手順4：1時間未満は分だけ
    if hours == 0:
        return f"{mins}分"

    # 手順5：ちょうどの時間は時間だけ
    if mins == 0:
        return f"{hours}時間"

    # 手順6：それ以外は時間と分
    return f"{hours}時間{mins}分"
