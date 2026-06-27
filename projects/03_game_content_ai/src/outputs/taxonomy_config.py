"""
WordPress カテゴリ・タグIDの設定と解決を行うモジュール。

設定方法：
  WordPress管理画面（投稿 → カテゴリー / タグ）でIDを確認し、
  下記の定数を実際のIDに書き換えてください。
"""

# ゲームニュースカテゴリID
# WordPress管理画面 → 投稿 → カテゴリー → 該当行にマウスを乗せてIDを確認
GAME_NEWS_CATEGORY_ID: int = 0  # 例: 3（0のままだとカテゴリは付与されません）

# 重要度別タグID
# WordPress管理画面 → 投稿 → タグ → 該当行にマウスを乗せてIDを確認
_TAG_ID_BY_IMPORTANCE: dict[str, list[int]] = {
    "S": [0],  # 注目タグID（例: 12）
    "A": [0],  # 速報タグID（例: 13）
    "B": [],   # タグなし
}


def resolve_taxonomy(importance: str) -> tuple[list[int], list[int]]:
    """
    重要度から WordPress カテゴリID・タグIDのリストを返す。

    ID が 0 のものは未設定とみなしてスキップする。

    Args:
        importance: 重要度文字列（"S" / "A" / "B"）

    Returns:
        tuple[list[int], list[int]]: (カテゴリIDリスト, タグIDリスト)
    """
    categories = [GAME_NEWS_CATEGORY_ID] if GAME_NEWS_CATEGORY_ID > 0 else []
    raw_tags = _TAG_ID_BY_IMPORTANCE.get(importance, [])
    tags = [tag_id for tag_id in raw_tags if tag_id > 0]
    return categories, tags
