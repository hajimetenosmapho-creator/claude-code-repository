"""
03_game_content_ai — ゲームニュース記事生成ツール

使い方:
    python main.py                    # 通常動作（S全件 + A最大5件）
    python main.py --max-articles 3   # テスト用：先頭3件のみ生成

動作の流れ:
    1. 各ゲームサイトのRSSからニュースを収集
    2. キーワードフィルターで不要記事を除外（API節約）
    3. Claude AIで重要度(S/A/B)を判定
    4. 記事化ルールに従って対象を絞り込み
       - S評価: 全件記事化
       - A評価: 最大5件まで記事化（超過分は候補ファイルへ）
       - B評価: 記事化しない（候補ファイルへ保存）
    5. 記事下書き・SEOタイトル・X投稿文を生成
    6. output/ フォルダにMarkdownファイルとして保存
"""

import argparse
import os
import sys
import anthropic

# Windowsコンソールの文字コード問題を防ぐ
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv

# プロジェクトルートの src/ をインポートパスに追加
sys.path.insert(0, str(Path(__file__).parent / "src"))

from collector import collect_all_news, NewsItem, FeedStats, FEED_GROUPS
from keyword_filter import filter_news
from duplicate_filter import deduplicate_news
from importance_judge import judge_all
from article_generator import generate_article
from seo_title_generator import generate_seo_title
from x_post_generator import generate_x_post

# .env ファイルを読み込む
load_dotenv()

OUTPUT_DIR = Path(__file__).parent / "output"

# A評価ニュースの記事化上限（超過分は候補ファイルへ保存）
A_ARTICLE_LIMIT = 5


def _print_rss_summary(
    feed_stats: list[FeedStats],
    total: int,
    filtered: int,
    deduped: int,
    generated: int,
) -> None:
    """RSS取得結果と処理パイプラインの統計をカテゴリ別に表示する。"""
    print("=" * 30)
    print("RSS取得結果")
    print("=" * 7)

    stats_by_source = {s.source: s for s in feed_stats}

    for group_name, sources in FEED_GROUPS.items():
        print(f"\n【{group_name}】")
        for source in sources:
            stat = stats_by_source.get(source)
            if stat is None:
                continue
            label = f"{source:<20}"
            if stat.status == "error":
                print(f"  {label} [取得失敗] {stat.error_message}")
            elif stat.status == "empty":
                print(f"  {label} 0件（記事なし）")
            else:
                print(f"  {label} {stat.count}件")

    print()
    print("-" * 30)
    print(f"  {'取得合計':<18} {total}件")
    print(f"  {'フィルター通過':<16} {filtered}件")
    print(f"  {'重複除去後':<17} {deduped}件")
    print(f"  {'記事生成':<18} {generated}件")
    print("=" * 20)
    print()


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


def _save_b_candidates_markdown(candidates: list[dict]) -> Path:
    """
    B評価ニュースとAスキップ分をまとめた候補一覧ファイルを output/ に保存する。

    Args:
        candidates: [{"item": NewsItem, "importance": str, "reason": str}, ...]

    Returns:
        Path: 保存したファイルのパス
    """
    OUTPUT_DIR.mkdir(exist_ok=True)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_B_candidates.md"
    output_path = OUTPUT_DIR / filename

    rows = []
    for i, entry in enumerate(candidates, 1):
        item: NewsItem = entry["item"]
        importance: str = entry["importance"]
        reason: str = entry.get("reason", "")
        rows.append(f"| {i} | {importance} | [{item.title[:40]}]({item.url}) | {item.source} | {reason[:40]} |")

    table = "\n".join(rows)

    content = f"""---
generated_at: "{now}"
total_count: {len(candidates)}
---

# ニュース候補一覧（記事化スキップ）

> B評価またはA評価の上限超過により記事化しなかったニュースの一覧です。

| # | 評価 | タイトル | ソース | 判定理由 |
|---|------|---------|--------|---------|
{table}

---
*生成日時: {now}*
"""

    output_path.write_text(content, encoding="utf-8")
    return output_path


def main():
    # コマンドライン引数の処理
    parser = argparse.ArgumentParser(description="ゲームニュース記事生成ツール")
    parser.add_argument(
        "--max-articles",
        type=int,
        default=None,
        metavar="N",
        help="生成する記事の最大数（テスト用）。未指定時は通常ルールで動作。",
    )
    args = parser.parse_args()
    max_articles: int | None = args.max_articles

    if max_articles is not None and max_articles < 0:
        print("エラー: --max-articles には 0 以上の整数を指定してください。")
        sys.exit(1)

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
    all_news, feed_stats = collect_all_news(max_items_per_feed=20)
    if not all_news:
        print("ニュースを取得できませんでした。インターネット接続を確認してください。")
        sys.exit(1)

    total_collected = len(all_news)

    # Step 2: キーワードフィルタリング
    filtered = filter_news(all_news)
    target_news = filtered["pass"]
    filtered_count = len(target_news)

    if not target_news:
        print("フィルター通過後のニュースが0件でした。")
        print("保留ニュース数:", len(filtered["pending"]))
        sys.exit(0)

    # Step 3: 重複排除（APIコスト削減のため重要度判定の前に実施）
    target_news = deduplicate_news(target_news)
    deduped_count = len(target_news)

    # Step 4: 重要度判定
    judged = judge_all(client, target_news)

    # 重要度「なし」は除外
    judged = [r for r in judged if r["importance"] != "なし"]

    if not judged:
        print("記事化対象のニュースが見つかりませんでした。")
        sys.exit(0)

    # Step 4: 重要度別に振り分けて記事化数を制限する
    s_items = [r for r in judged if r["importance"] == "S"]
    a_items = [r for r in judged if r["importance"] == "A"]
    b_items = [r for r in judged if r["importance"] == "B"]

    # A評価は上限まで、超過分はスキップ
    a_to_process = a_items[:A_ARTICLE_LIMIT]
    a_skipped    = a_items[A_ARTICLE_LIMIT:]

    # 記事生成対象（S優先 → A）
    to_process = s_items + a_to_process
    if max_articles is not None:
        to_process = to_process[:max_articles]

    # B評価 + Aスキップ分 → 候補ファイルにまとめる
    candidates = b_items + [dict(r, importance="A(スキップ)") for r in a_skipped]

    # 振り分け結果のログ表示
    a_skip_note = f"（全{len(a_items)}件中、{len(a_skipped)}件をスキップ）" if a_skipped else ""
    print("記事生成対象の振り分け結果:")
    print(f"  S評価（全件記事化）  : {len(s_items)}件")
    print(f"  A評価（最大{A_ARTICLE_LIMIT}件まで） : {len(a_to_process)}件  {a_skip_note}")
    print(f"  B評価（記事化なし）  : {len(b_items)}件 → 候補ファイルへ保存")
    print()

    planned = len(to_process)
    print(f"  記事生成予定: {planned}件")
    print(f"  API呼び出し予測: {planned * 3}回（article×{planned} + seo×{planned} + x_post×{planned}）")

    if max_articles is not None:
        print(f"  ※ --max-articles {max_articles} が指定されたため、先頭{planned}件のみ処理します")
    print()

    # 候補ファイルの保存（記事生成より前に保存して確実に残す）
    if candidates:
        b_path = _save_b_candidates_markdown(candidates)
        print(f"  候補ファイル保存完了: {b_path.name}（{len(candidates)}件）")
        print()

    if not to_process:
        print("生成対象の記事がありません。")
        sys.exit(0)

    # Step 5: 記事生成・保存
    print(f"記事を生成しています（{len(to_process)}件）...")
    saved_files = []
    api_call_count = 0

    for i, entry in enumerate(to_process, 1):
        item: NewsItem = entry["item"]
        importance: str = entry["importance"]

        call_start = api_call_count + 1
        call_end   = api_call_count + 3
        print(f"\n  [{i}/{len(to_process)}] {importance} - {item.title[:50]}（API呼び出し: {call_start}〜{call_end}回目）")

        article_body = generate_article(client, item, importance)
        seo_title    = generate_seo_title(client, item, importance)
        x_post       = generate_x_post(client, item, importance, article_body)
        api_call_count += 3

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
    print(f"  生成結果:")
    print(f"    重要度S（優先）    : {s_count}件")
    if a_skipped:
        print(f"    重要度A（通常）    : {a_count}件  （{len(a_skipped)}件スキップ）")
    else:
        print(f"    重要度A（通常）    : {a_count}件")
    print(f"    重要度B（スキップ）: {len(b_items)}件 → 候補ファイルに保存")
    print()
    print(f"  API呼び出し（記事生成）: {api_call_count}回")
    print()
    print(f"  保存先: {OUTPUT_DIR}")
    print()
    print("生成されたファイル一覧:")
    for importance, title, path in saved_files:
        print(f"  [{importance}] {title[:45]} → {path.name}")

    print()
    _print_rss_summary(feed_stats, total_collected, filtered_count, deduped_count, len(saved_files))


if __name__ == "__main__":
    main()
