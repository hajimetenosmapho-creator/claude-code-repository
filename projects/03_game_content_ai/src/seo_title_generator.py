"""
Claude APIを使ってSEOタイトルを生成するモジュール。
"""

import anthropic
from pathlib import Path
from collector import NewsItem

PROMPT_FILE = Path(__file__).parent.parent / "prompts" / "seo_prompt.md"

SEO_MODEL = "claude-haiku-4-5-20251001"


def _load_prompt_template() -> str:
    return PROMPT_FILE.read_text(encoding="utf-8")


def generate_seo_title(client: anthropic.Anthropic, item: NewsItem, importance: str) -> str:
    """
    1件のニュースのSEOタイトルを生成する。

    Args:
        client: Anthropic クライアント
        item: 対象の NewsItem
        importance: 重要度（"S" | "A" | "B"）

    Returns:
        str: 生成されたSEOタイトル（失敗時は元タイトルを返す）
    """
    template = _load_prompt_template()
    prompt = template.format(
        title=item.title,
        importance=importance,
        source=item.source,
    )

    try:
        message = client.messages.create(
            model=SEO_MODEL,
            max_tokens=128,
            messages=[{"role": "user", "content": prompt}],
        )
        seo_title = message.content[0].text.strip()
        # 余計な引用符を除去
        seo_title = seo_title.strip('"').strip("「」")
        return seo_title

    except Exception as e:
        print(f"  [警告] SEOタイトル生成失敗（{item.title[:30]}...）: {e}")
        return item.title
