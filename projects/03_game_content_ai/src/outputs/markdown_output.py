"""
Markdownファイルへの記事保存を担うモジュール。
main.py にあった _save_as_markdown() をここに移植。
"""

from pathlib import Path
from datetime import datetime, timezone
from .base import BaseOutput, ArticleData


class MarkdownOutput(BaseOutput):
    """生成した記事を Markdown ファイルとして output/ に保存する。"""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir

    def is_available(self) -> bool:
        return True

    def save(self, article: ArticleData) -> str:
        """
        記事データを Markdown ファイルとして保存する。

        Returns:
            str: 保存したファイルのパス文字列
        """
        self.output_dir.mkdir(exist_ok=True)

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        source_slug = (
            article.item.source
            .replace(" ", "_")
            .replace("*", "")
            .replace("/", "")
        )
        filename = f"{timestamp}_{source_slug}_{article.importance}.md"
        output_path = self.output_dir / filename

        candidates = article.item.image_candidates
        if candidates:
            image_candidates_yaml = "\n" + "\n".join(f'  - "{u}"' for u in candidates)
        else:
            image_candidates_yaml = "[]"

        image_comment = (
            f"\n<!-- アイキャッチ候補: {article.featured_image_url} -->\n"
            if article.featured_image_url else ""
        )

        references_yaml = (
            "references:\n"
            f"  - title: \"{article.item.title}\"\n"
            f"    url: \"{article.item.url}\"\n"
            f"    publisher: \"{article.item.source}\"\n"
            f"    published_date: \"{article.item.published_at}\""
        )

        excerpt_safe = article.excerpt.replace('"', "'")
        meta_description_safe = article.meta_description.replace('"', "'")

        content = f"""---
title: "{article.seo_title}"
importance: {article.importance}
source: {article.item.source}
source_url: "{article.item.url}"
generated_at: "{now}"
excerpt: "{excerpt_safe}"
meta_description: "{meta_description_safe}"
official_news_url: ""
official_site_url: ""
official_trailer_url: ""
official_presskit_url: ""
image_candidates: {image_candidates_yaml}
image_source: ""
image_terms_confirmed: false
{references_yaml}
---

# {article.seo_title}

{article.article_body}

---

## X投稿文

{article.x_post}
{image_comment}"""

        output_path.write_text(content, encoding="utf-8")
        return str(output_path)
