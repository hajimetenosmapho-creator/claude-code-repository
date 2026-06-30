"""
AI 改善提案バッチスクリプト（v1.14.0）

投稿直後ではなく、Search Console / GA4 データが蓄積された後に
バッチとして AI 改善提案を実行するスクリプト。

使い方:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe scripts/run_ai_improvement.py
    ./venv/Scripts/python.exe scripts/run_ai_improvement.py --date 20260630
    ./venv/Scripts/python.exe scripts/run_ai_improvement.py --max-articles 3

動作の流れ:
    1. logs/articles/YYYYMMDD_articles.jsonl から投稿済み記事を読み込む
    2. logs/analytics/YYYYMMDD_analytics.jsonl からパフォーマンスデータを読み込む
    3. has_performance_data=True の記事のみ処理対象にする
    4. AiImprovementService で改善提案を生成する
    5. outputs/ai_improvements/YYYYMMDD_{slug}_improvement.json に保存する

前提条件（.env に設定が必要）:
    AI_IMPROVEMENT_ENABLED=true
    ANTHROPIC_API_KEY=your_key_here
    ANALYTICS_ENABLED=true

なぜ投稿直後ではなく別スクリプトか:
    Search Console / GA4 のデータは記事公開後 24〜48 時間以上経過してから
    反映されるため、投稿時点では意味のある改善提案が生成できない。
    このスクリプトを日次バッチとして実行することで、実データに基づいた
    改善提案を得ることができる。
"""
import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from analytics import AnalyticsManager, NullAnalyticsManager
from ai import AiImprovementService, NullAiImprovementService


def main():
    parser = argparse.ArgumentParser(
        description="AI 改善提案バッチ（v1.14.0）"
    )
    parser.add_argument(
        "--date",
        default=date.today().strftime("%Y%m%d"),
        metavar="YYYYMMDD",
        help="対象日付（デフォルト: 今日）",
    )
    parser.add_argument(
        "--max-articles",
        type=int,
        default=None,
        metavar="N",
        help="最大処理件数（デフォルト: AI_IMPROVEMENT_MAX_ARTICLES）",
    )
    args = parser.parse_args()
    date_str = args.date

    base_dir = Path(__file__).parent.parent

    # AiImprovementService の確認（AI_IMPROVEMENT_ENABLED=true + ANTHROPIC_API_KEY が必要）
    ai_service = AiImprovementService.from_env(base_dir=base_dir)
    if isinstance(ai_service, NullAiImprovementService):
        print("[エラー] AI 改善提案が無効です。以下を確認してください：")
        print("  AI_IMPROVEMENT_ENABLED=true")
        print("  ANTHROPIC_API_KEY=your_key_here")
        sys.exit(1)

    # AnalyticsManager の確認（ANALYTICS_ENABLED=true が必要）
    analytics_manager = AnalyticsManager.from_env(base_dir=base_dir)
    if isinstance(analytics_manager, NullAnalyticsManager):
        print("[エラー] ANALYTICS_ENABLED=true が必要です。")
        print("  .env に ANALYTICS_ENABLED=true を設定してください。")
        sys.exit(1)

    # 対象記事の読み込み
    log_dir = base_dir / "logs"
    articles = list(analytics_manager.load_article_logs(log_dir=log_dir, date_str=date_str))

    if not articles:
        print(f"対象記事なし（{date_str}）")
        sys.exit(0)

    # アナリティクスデータの読み込み
    analytics_map = analytics_manager.load_analytics_logs(date_str=date_str)

    # ArticleAnalysisRecord を生成し、has_performance_data=True のものをフィルタリング
    ai_inputs = []
    for article in articles:
        post_id = article.get("post_id", 0)
        analytics_entry = analytics_map.get(post_id)
        analysis_record = analytics_manager.build_analysis_record(article, analytics_entry)
        if analysis_record is None:
            continue
        ai_input = analytics_manager.build_ai_input(analysis_record)
        if ai_input is None:
            continue
        ai_inputs.append(ai_input)

    total = len(ai_inputs)
    performance_count = sum(1 for r in ai_inputs if r.has_performance_data)

    print(f"AI 改善提案バッチ開始（{date_str}）")
    print(f"  対象記事: {total}件")
    print(f"  パフォーマンスデータあり: {performance_count}件")
    print()

    if not performance_count:
        print("パフォーマンスデータがある記事がありません。")
        print("先に以下のバッチを実行してください：")
        print("  scripts/fetch_search_console_metrics.py")
        print("  scripts/fetch_google_analytics_metrics.py")
        sys.exit(0)

    max_articles = args.max_articles
    suggestions = ai_service.improve_batch(
        ai_inputs=ai_inputs,
        performance_only=True,
        max_articles=max_articles,
    )

    print()
    print(f"完了: 改善提案={len(suggestions)}件 / 処理対象={performance_count}件 / 合計={total}件")
    print(f"保存先: {base_dir / 'outputs' / 'ai_improvements'}/")


if __name__ == "__main__":
    main()
