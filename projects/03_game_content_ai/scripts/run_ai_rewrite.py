"""
AI リライトバッチスクリプト（v1.16.0）

outputs/ai_improvements/ に保存された改善提案 JSON を読み込み、
Claude に改善版記事（Rewrite Draft）を生成させ、
outputs/ai_rewrites/ に Markdown + JSON で保存する。

Claude API を呼び出す（AI_REWRITE_ENABLED=true と ANTHROPIC_API_KEY が必要）。

使い方:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe scripts/run_ai_rewrite.py
    ./venv/Scripts/python.exe scripts/run_ai_rewrite.py --priority high
    ./venv/Scripts/python.exe scripts/run_ai_rewrite.py --article-id ps6-announced-20260630
    ./venv/Scripts/python.exe scripts/run_ai_rewrite.py --max-articles 3

動作の流れ:
    1. outputs/ai_improvements/ の改善提案 JSON を読み込む
    2. 優先度 / 記事ID でフィルタリング（オプション）
    3. RewriteService.rewrite_batch() でリライトを実行する
    4. outputs/ai_rewrites/YYYYMMDD_{slug}_rewrite.json に JSON を保存する
    5. outputs/ai_rewrites/YYYYMMDD_{slug}_rewrite.md に Markdown を保存する

前提条件（.env に設定が必要）:
    AI_REWRITE_ENABLED=true
    ANTHROPIC_API_KEY=your_key_here

元記事取得（オプション）:
    WordPress 認証情報が設定されていると元記事本文を基にリライトします。
    未設定の場合は改善提案の内容のみでリライトします。
    WORDPRESS_URL=https://your-blog.com
    WORDPRESS_USERNAME=your_username
    WORDPRESS_APP_PASSWORD=your_app_password

なぜ別スクリプトか:
    リライトは AI 改善提案（run_ai_improvement.py）の後工程として実行する。
    改善提案 JSON が outputs/ai_improvements/ に存在することが前提。
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from ai import ImprovementRepository, RewriteService, NullRewriteService


def main():
    parser = argparse.ArgumentParser(
        description="AI リライトバッチ（v1.16.0）"
    )
    parser.add_argument(
        "--priority",
        choices=["high", "medium", "low"],
        default=None,
        help="絞り込む優先度（未指定: 全件）",
    )
    parser.add_argument(
        "--article-id",
        default=None,
        metavar="SLUG",
        help="絞り込む記事ID（slug）",
    )
    parser.add_argument(
        "--max-articles",
        type=int,
        default=None,
        metavar="N",
        help="最大処理件数（デフォルト: AI_REWRITE_MAX_ARTICLES）",
    )
    args = parser.parse_args()

    base_dir = Path(__file__).parent.parent

    # RewriteService の確認（AI_REWRITE_ENABLED=true + ANTHROPIC_API_KEY が必要）
    rewrite_service = RewriteService.from_env(base_dir=base_dir)
    if isinstance(rewrite_service, NullRewriteService):
        print("[エラー] AI リライトが無効です。以下を確認してください：")
        print("  AI_REWRITE_ENABLED=true")
        print("  ANTHROPIC_API_KEY=your_key_here")
        sys.exit(1)

    # 改善提案 JSON の読み込み
    improvement_dir = base_dir / "outputs" / "ai_improvements"
    repository = ImprovementRepository(improvement_dir)
    suggestions = repository.load_all()

    if not suggestions:
        print(f"改善提案 JSON が見つかりません: {improvement_dir}")
        print("先に以下のバッチを実行してください：")
        print("  scripts/run_ai_improvement.py")
        sys.exit(0)

    # フィルタリング
    if args.article_id:
        suggestions = [s for s in suggestions if s.article_id == args.article_id]
        print(f"  絞り込み: article_id={args.article_id}")
    if args.priority:
        suggestions = repository.filter_by_priority(suggestions, args.priority)
        print(f"  絞り込み: priority={args.priority}")

    total = len(suggestions)
    if not total:
        print("対象となる改善提案がありません。")
        sys.exit(0)

    print(f"AI リライトバッチ開始")
    print(f"  対象: {total} 件の改善提案")
    print()

    results = rewrite_service.rewrite_batch(
        suggestions=suggestions,
        max_articles=args.max_articles,
    )

    success_count = sum(1 for r in results if r.success)
    fail_count = sum(1 for r in results if not r.success)

    print()
    print(f"完了: 成功={success_count}件 / 失敗={fail_count}件 / 合計={len(results)}件")
    print(f"保存先: {base_dir / 'outputs' / 'ai_rewrites'}/")

    if fail_count:
        print()
        print("失敗した記事:")
        for r in results:
            if not r.success:
                print(f"  - {r.article_id}: {r.error_message}")


if __name__ == "__main__":
    main()
