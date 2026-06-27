"""
WordPress カテゴリ・タグIDの設定と解決を行うモジュール。

IDはWordPress管理画面（投稿 → カテゴリー / タグ）で確認できます。
"""

# ---- カテゴリID ----
CATEGORY_GAME_NEWS: int = 14   # ゲームニュース（03_game_content_ai の投稿先）
CATEGORY_REVIEW: int = 4       # レビュー（将来のレビュー記事生成ツール用）
CATEGORY_AI_DEV: int = 69      # AI開発（将来のAI開発記事用）

# ---- タグID ----
TAG_NOTABLE: int = 70   # 注目（S評価記事に付与）
TAG_BREAKING: int = 71  # 速報（S・A評価記事に付与）

# ---- 重要度別の投稿設定 ----
# S記事：ゲームニュース + 注目 + 速報
# A記事：ゲームニュース + 速報
# B記事：ゲームニュースのみ
_TAXONOMY_BY_IMPORTANCE: dict[str, dict[str, list[int]]] = {
    "S": {"categories": [CATEGORY_GAME_NEWS], "tags": [TAG_NOTABLE, TAG_BREAKING]},
    "A": {"categories": [CATEGORY_GAME_NEWS], "tags": [TAG_BREAKING]},
    "B": {"categories": [CATEGORY_GAME_NEWS], "tags": []},
}


def resolve_taxonomy(importance: str) -> tuple[list[int], list[int]]:
    """
    重要度から WordPress カテゴリID・タグIDのリストを返す。

    Args:
        importance: 重要度文字列（"S" / "A" / "B"）

    Returns:
        tuple[list[int], list[int]]: (カテゴリIDリスト, タグIDリスト)
    """
    config = _TAXONOMY_BY_IMPORTANCE.get(importance, {"categories": [], "tags": []})
    return config["categories"], config["tags"]
