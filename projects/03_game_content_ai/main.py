"""
03_game_content_ai — ゲームニュース記事生成ツール

使い方:
    python main.py

動作の流れ:
    1. 各ゲームサイトのRSSからニュースを収集
    2. キーワードフィルターで不要記事を除外（API節約）
    3. Claude AIで重要度(S/A/B)を判定
    4. 記事下書き・SEOタイトル・X投稿文を生成
    5. output/ フォルダにMarkdownファイルとして保存
"""

import os
import sys
import anthropic
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv

# プロジェクトルートの src/ をインポートパスに追加
sys.path.insert(0, str(Path(__file__).parent / "src"))

from collector import collect_all_news, NewsItem
from keyword_filter import filter_news
from importance_judge import judge_all
from article_generator import generate_article
from seo_title_generator import generate_seo_title
from x_post_generator import generate_x_post

# .env ファイルを読み込む
load_dotenv()

OUTPUT_DIR = Path(__file__).parent / "output"


def _save_as_markdown(
    item: NewsItem,
    importance: str,
    seo_title: str,
    article_body: str,
    x_post: str,
) -> Path:
    """
    生成した記事データを Markdown ファイルとして output/ に保存する。

    Returns:
        Path: 保存したファイルのパス
    """
    OUTPUT_DIR.mkdir(exist_ok=True)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    # ファイル名：日時_ソース名（スペースはアンダースコアに変換）
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    source_slug = item.source.replace(" ", "_").replace("*", "").replace("/", "")
    filename = f"{timestamp}_{source_slug}_{importance}.md"
    output_path = OUTPUT_DIR / filename

    # 画像候補・出典情報（将来用）
    image_candidates_yaml = "[]"
    references_yaml = (
        "references:\n"
        f"  - title: \"{item.title}\"\n"
        f"    url: \"{item.url}\"\n"
        f"    publisher: \"{item.source}\"\n"
        f"    published_date: \"{item.published_at}\""
    )

    content = f"""---
title: "{seo_title}"
importance: {importance}
source: {item.source}
source_url: "{item.url}"
generated_at: "{now}"
official_news_url: ""
official_site_url: ""
official_trailer_url: ""
official_presskit_url: ""
image_candidates: {image_candidates_yaml}
image_source: ""
image_terms_confirmed: false
{references_yaml}
---

# {seo_title}

{article_body}

---

## X投稿文

{x_post}
"""

    output_path.write_text(content, encoding="utf-8")
    return output_path


def main():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("エラー: ANTHROPIC_API_KEY が設定されていません。")
        print(".env ファイルに ANTHROPIC_API_KEY=your_key を追加してください。")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    print("=" * 60)
    print("  ゲームニュース記事生成ツール - KAORUの部屋")
    print("=" * 60)
    print()

    # Step 1: ニュース収集
    all_news = collect_all_news(max_items_per_feed=20)
    if not all_news:
        print("ニュースを取得できませんでした。インターネット接続を確認してください。")
        sys.exit(1)

    # Step 2: キーワードフィルタリング
    filtered = filter_news(all_news)
    target_news = filtered["pass"]

    if not target_news:
        print("フィルター通過後のニュースが0件でした。")
        print("保留ニュース数:", len(filtered["pending"]))
        sys.exit(0)

    # Step 3: 重要度判定
    judged = judge_all(client, target_news)

    # 重要度「なし」は除外
    judged = [r for r in judged if r["importance"] != "なし"]

    if not judged:
        print("記事化対象のニュースが見つかりませんでした。")
        sys.exit(0)

    # Step 4 & 5: 記事生成・保存
    print(f"記事を生成しています（{len(judged)}件）...")
    saved_files = []

    for i, entry in enumerate(judged, 1):
        item: NewsItem = entry["item"]
        importance: str = entry["importance"]

        print(f"\n  [{i}/{len(judged)}] {importance} - {item.title[:50]}")

        article_body = generate_article(client, item, importance)
        seo_title = generate_seo_title(client, item, importance)
        x_post = generate_x_post(client, item, importance, article_body)

        output_path = _save_as_markdown(item, importance, seo_title, article_body, x_post)
        saved_files.append((importance, seo_title, output_path))
        print(f"    保存: {output_path.name}")

    # 完了サマリー
    print()
    print("=" * 60)
    print(f"  完了！ {len(saved_files)} 件の記事を生成しました")
    print("=" * 60)
    print()

    s_count = sum(1 for imp, _, _ in saved_files if imp == "S")
    a_count = sum(1 for imp, _, _ in saved_files if imp == "A")
    b_count = sum(1 for imp, _, _ in saved_files if imp == "B")
    print(f"  重要度S（優先）: {s_count}件")
    print(f"  重要度A（通常）: {a_count}件")
    print(f"  重要度B（短文）: {b_count}件")
    print()
    print(f"  保存先: {OUTPUT_DIR}")
    print()
    print("生成されたファイル一覧:")
    for importance, title, path in saved_files:
        print(f"  [{importance}] {title[:45]} → {path.name}")


if __name__ == "__main__":
    main()
