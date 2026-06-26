"""
Claude APIを使って記事下書きを生成するモジュール。
KAORUの部屋ブログ方針・SNS反応ルールをプロンプトに組み込み済み。
"""

import anthropic
from functools import lru_cache
from pathlib import Path
from collector import NewsItem

PROMPT_FILE = Path(__file__).parent.parent / "prompts" / "article_prompt.md"

# 記事生成には高品質なモデルを使用
ARTICLE_MODEL = "claude-sonnet-4-6"


@lru_cache(maxsize=1)
def _load_prompt_template() -> str:
    return PROMPT_FILE.read_text(encoding="utf-8")


def generate_article(client: anthropic.Anthropic, item: NewsItem, importance: str) -> str:
    """
    1件のニュースから記事下書きを生成する。

    Args:
        client: Anthropic クライアント
        item: 記事化する NewsItem
        importance: 重要度（"S" | "A" | "B"）

    Returns:
        str: 生成された記事本文
    """
    template = _load_prompt_template()
    prompt = template.format(
        title=item.title,
        summary=item.summary,
        source=item.source,
        url=item.url,
        importance=importance,
    )

    # 重要度に応じてトークン数を調整
    max_tokens_map = {"S": 3000, "A": 2000, "B": 800}
    max_tokens = max_tokens_map.get(importance, 1500)

    try:
        message = client.messages.create(
            model=ARTICLE_MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()

    except Exception as e:
        print(f"  [エラー] 記事生成失敗（{item.title[:30]}...）: {e}")
        return f"記事生成に失敗しました。元記事URL: {item.url}"
