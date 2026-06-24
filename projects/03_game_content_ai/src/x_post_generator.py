"""
Claude APIを使ってX（旧Twitter）投稿文を生成するモジュール。
"""

import anthropic
from pathlib import Path
from collector import NewsItem

PROMPT_FILE = Path(__file__).parent.parent / "prompts" / "x_post_prompt.md"

X_MODEL = "claude-haiku-4-5-20251001"


def _load_prompt_template() -> str:
    return PROMPT_FILE.read_text(encoding="utf-8")


def generate_x_post(
    client: anthropic.Anthropic,
    item: NewsItem,
    importance: str,
    article_body: str,
    blog_url: str = "[ブログURL]",
) -> str:
    """
    1件の記事からX投稿文を生成する。

    Args:
        client: Anthropic クライアント
        item: 対象の NewsItem
        importance: 重要度（"S" | "A" | "B"）
        article_body: 生成済みの記事本文（要約に使用）
        blog_url: ブログのURL（未確定の場合はプレースホルダー）

    Returns:
        str: 生成されたX投稿文
    """
    template = _load_prompt_template()

    # 記事本文から前半300文字を要約として渡す
    article_summary = article_body[:300].replace("\n", " ")

    prompt = template.format(
        title=item.title,
        article_summary=article_summary,
        importance=importance,
        blog_url=blog_url,
    )

    try:
        message = client.messages.create(
            model=X_MODEL,
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()

    except Exception as e:
        print(f"  [警告] X投稿文生成失敗（{item.title[:30]}...）: {e}")
        return f"{item.title}\n\n詳しくはこちら👇\n{blog_url}"
