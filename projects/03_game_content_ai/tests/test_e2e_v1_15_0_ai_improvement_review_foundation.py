"""
E2E テスト: v1.15.0 AI Improvement Review Foundation

テストシナリオ:
    1.  ImprovementRepository が JSON ファイルを読み込める
    2.  複数ファイルを読み込める
    3.  不正 JSON を安全にスキップできる
    4.  priority で絞り込める
    5.  prompt_version で絞り込める
    6.  article_id で絞り込める
    7.  ディレクトリが存在しない場合に空リストを返す
    8.  ImprovementReportBuilder が Markdown を生成できる
    9.  Markdown に title / permalink / priority / issues / suggestions が含まれる
    10. Markdown に summary / seo_title_suggestion / created_at が含まれる
    11. 優先度別（high / medium / low）に整理される
    12. 対象なし時のレポートが生成できる
    13. ImprovementReviewService がレポートを保存できる
    14. ImprovementReviewService の絞り込み動作
    15. scripts/run_ai_improvement_report.py が存在する
    16. Claude API を呼び出さない（API 呼び出しコードが ai review 系にない）
    17. v1.14.0 パッケージの __init__.py が新クラスをエクスポートする
    18. v1.14.0 テストが壊れない（インポート確認）

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v1_15_0_ai_improvement_review_foundation.py
"""
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# ─── テスト用ユーティリティ ───

results = []

def check(label: str, actual, expected, exact: bool = True):
    if exact:
        ok = actual == expected
    else:
        ok = expected in str(actual)
    status = "PASS" if ok else "FAIL"
    results.append((status, label))
    mark = "OK" if ok else "NG"
    print(f"  [{mark}] {label}")
    if not ok:
        print(f"       Expected: {expected!r}")
        print(f"       Actual:   {actual!r}")


def make_suggestion_dict(
    article_id="test-article",
    title="テスト記事",
    permalink="https://example.com/test-article/",
    prompt_version="v1",
    summary="改善の余地があります。",
    priority="medium",
    issues=None,
    suggestions=None,
    seo_title_suggestion=None,
    meta_description_suggestion=None,
    internal_link_suggestions=None,
    raw_response="",
    created_at=None,
):
    return {
        "article_id": article_id,
        "title": title,
        "permalink": permalink,
        "prompt_version": prompt_version,
        "summary": summary,
        "priority": priority,
        "issues": issues or ["問題点1", "問題点2"],
        "suggestions": suggestions or ["改善提案1", "改善提案2"],
        "seo_title_suggestion": seo_title_suggestion,
        "meta_description_suggestion": meta_description_suggestion,
        "internal_link_suggestions": internal_link_suggestions or [],
        "raw_response": raw_response,
        "created_at": created_at or datetime.now().isoformat(),
    }


# ─── Scenario 1 & 2: ImprovementRepository ───

print("\n=== Scenario 1 & 2: ImprovementRepository の読み込み ===")

from ai.improvement_repository import ImprovementRepository

with tempfile.TemporaryDirectory() as tmpdir:
    imp_dir = Path(tmpdir) / "ai_improvements"
    imp_dir.mkdir()

    # 1件の JSON を作成
    data1 = make_suggestion_dict(article_id="article-1", priority="high", title="記事1")
    (imp_dir / "20260630_article-1_improvement.json").write_text(
        json.dumps(data1, ensure_ascii=False), encoding="utf-8"
    )

    repo = ImprovementRepository(imp_dir)
    suggestions = repo.load_all()

    check("1件読み込み: 件数=1", len(suggestions), 1)
    check("1件読み込み: article_id", suggestions[0].article_id, "article-1")
    check("1件読み込み: priority=high", suggestions[0].priority, "high")
    check("1件読み込み: title", suggestions[0].title, "記事1")
    check("1件読み込み: issues 件数", len(suggestions[0].issues), 2)
    check("1件読み込み: suggestions 件数", len(suggestions[0].suggestions), 2)

    # 2件目を追加
    data2 = make_suggestion_dict(article_id="article-2", priority="low", title="記事2")
    (imp_dir / "20260630_article-2_improvement.json").write_text(
        json.dumps(data2, ensure_ascii=False), encoding="utf-8"
    )

    suggestions2 = repo.load_all()
    check("2件読み込み: 件数=2", len(suggestions2), 2)

# ─── Scenario 3: 不正 JSON スキップ ───

print("\n=== Scenario 3: 不正 JSON スキップ ===")

with tempfile.TemporaryDirectory() as tmpdir:
    imp_dir = Path(tmpdir) / "ai_improvements"
    imp_dir.mkdir()

    # 正常ファイル
    data_valid = make_suggestion_dict(article_id="valid-article", priority="medium")
    (imp_dir / "20260630_valid-article_improvement.json").write_text(
        json.dumps(data_valid, ensure_ascii=False), encoding="utf-8"
    )

    # 不正 JSON ファイル
    (imp_dir / "20260630_broken_improvement.json").write_text(
        "これは不正なJSONです{{{", encoding="utf-8"
    )

    # 空ファイル
    (imp_dir / "20260630_empty_improvement.json").write_text("", encoding="utf-8")

    repo = ImprovementRepository(imp_dir)
    suggestions = repo.load_all()

    check("不正JSONスキップ: 正常ファイルのみ読み込む", len(suggestions), 1)
    check("不正JSONスキップ: 正常ファイルの article_id", suggestions[0].article_id, "valid-article")

# ─── Scenario 4 & 5 & 6: 絞り込み ───

print("\n=== Scenario 4, 5, 6: 絞り込み ===")

with tempfile.TemporaryDirectory() as tmpdir:
    imp_dir = Path(tmpdir) / "ai_improvements"
    imp_dir.mkdir()

    # high / v1
    d_high = make_suggestion_dict(article_id="art-high", priority="high", prompt_version="v1")
    (imp_dir / "20260630_art-high_improvement.json").write_text(
        json.dumps(d_high, ensure_ascii=False), encoding="utf-8"
    )

    # medium / v1
    d_medium = make_suggestion_dict(article_id="art-medium", priority="medium", prompt_version="v1")
    (imp_dir / "20260630_art-medium_improvement.json").write_text(
        json.dumps(d_medium, ensure_ascii=False), encoding="utf-8"
    )

    # low / v2
    d_low = make_suggestion_dict(article_id="art-low", priority="low", prompt_version="v2")
    (imp_dir / "20260630_art-low_improvement.json").write_text(
        json.dumps(d_low, ensure_ascii=False), encoding="utf-8"
    )

    repo = ImprovementRepository(imp_dir)
    all_suggestions = repo.load_all()

    # priority 絞り込み
    high_only = repo.filter_by_priority(all_suggestions, "high")
    check("priority=high 絞り込み: 件数=1", len(high_only), 1)
    check("priority=high 絞り込み: article_id", high_only[0].article_id, "art-high")

    medium_only = repo.filter_by_priority(all_suggestions, "medium")
    check("priority=medium 絞り込み: 件数=1", len(medium_only), 1)

    low_only = repo.filter_by_priority(all_suggestions, "low")
    check("priority=low 絞り込み: 件数=1", len(low_only), 1)

    not_found = repo.filter_by_priority(all_suggestions, "unknown")
    check("priority=unknown 絞り込み: 件数=0", len(not_found), 0)

    # prompt_version 絞り込み
    v1_only = repo.filter_by_prompt_version(all_suggestions, "v1")
    check("prompt_version=v1 絞り込み: 件数=2", len(v1_only), 2)

    v2_only = repo.filter_by_prompt_version(all_suggestions, "v2")
    check("prompt_version=v2 絞り込み: 件数=1", len(v2_only), 1)

    # article_id 絞り込み
    by_id = repo.load_by_article_id("art-medium")
    check("article_id 絞り込み: 件数=1", len(by_id), 1)
    check("article_id 絞り込み: 一致", by_id[0].article_id, "art-medium")

    by_id_none = repo.load_by_article_id("nonexistent")
    check("article_id 不一致: 件数=0", len(by_id_none), 0)

# ─── Scenario 7: ディレクトリ不存在 ───

print("\n=== Scenario 7: ディレクトリ不存在 ===")

repo_empty = ImprovementRepository(Path("/nonexistent/path/ai_improvements"))
result_empty = repo_empty.load_all()
check("ディレクトリ不存在: 空リスト", result_empty, [])

# ─── Scenario 8 & 9 & 10 & 11: ImprovementReportBuilder ───

print("\n=== Scenario 8, 9, 10, 11: ImprovementReportBuilder ===")

from ai.improvement_report_builder import ImprovementReportBuilder
from ai.improvement_suggestion import ImprovementSuggestion

builder = ImprovementReportBuilder()

suggestions_for_report = [
    ImprovementSuggestion(
        article_id="ps6-announce",
        title="PS6発表！詳細まとめ",
        permalink="https://example.com/ps6-announce/",
        prompt_version="v1",
        summary="CTRが低くSEO改善が必要です。",
        priority="high",
        issues=["タイトルにキーワードが不足", "メタディスクリプション未設定"],
        suggestions=["タイトルに『PS6』『価格』を追加", "メタディスクリプションを設定する"],
        seo_title_suggestion="PS6正式発表！価格・スペック・発売日まとめ【2026年版】",
        meta_description_suggestion="PS6の全情報を徹底解説。価格・スペック・発売日を一挙紹介。",
        internal_link_suggestions=["関連: PS5 vs PS6 比較記事"],
        raw_response="",
        created_at=datetime(2026, 6, 30, 12, 0, 0),
    ),
    ImprovementSuggestion(
        article_id="xbox-update",
        title="Xbox 最新アップデート情報",
        permalink="https://example.com/xbox-update/",
        prompt_version="v1",
        summary="概ね良好ですが読みやすさに改善の余地があります。",
        priority="medium",
        issues=["段落が長い"],
        suggestions=["段落を短く分割する"],
        raw_response="",
        created_at=datetime(2026, 6, 30, 11, 0, 0),
    ),
    ImprovementSuggestion(
        article_id="nintendo-news",
        title="任天堂ニュース",
        permalink=None,
        prompt_version="v1",
        summary="問題なし。",
        priority="low",
        issues=[],
        suggestions=["画像のalt属性を追加する"],
        raw_response="",
        created_at=datetime(2026, 6, 30, 10, 0, 0),
    ),
]

markdown = builder.build(suggestions_for_report)

check("Markdown が str", isinstance(markdown, str), True)
check("Markdown が空でない", len(markdown) > 100, True)
check("タイトルを含む", "PS6発表！詳細まとめ" in markdown, True)
check("permalink を含む", "https://example.com/ps6-announce/" in markdown, True)
check("priority を含む", "high" in markdown, True)
check("issues を含む", "タイトルにキーワードが不足" in markdown, True)
check("suggestions を含む", "タイトルに『PS6』『価格』を追加" in markdown, True)
check("summary を含む", "CTRが低くSEO改善が必要です。" in markdown, True)
check("seo_title_suggestion を含む", "PS6正式発表！価格・スペック・発売日まとめ【2026年版】" in markdown, True)
check("created_at を含む", "2026-06-30" in markdown, True)
check("High セクションを含む", "High" in markdown, True)
check("Medium セクションを含む", "Medium" in markdown, True)
check("Low セクションを含む", "Low" in markdown, True)
check("生成日時を含む", "生成日時" in markdown, True)
check("対象記事数を含む", "3" in markdown, True)

# ─── Scenario 12: 対象なし時 ───

print("\n=== Scenario 12: 対象なしのレポート ===")

empty_markdown = builder.build([])
check("空リストでもMarkdown生成", isinstance(empty_markdown, str), True)
check("空リスト: 対象記事数0", "0 件" in empty_markdown, True)

# ─── Scenario 13 & 14: ImprovementReviewService ───

print("\n=== Scenario 13 & 14: ImprovementReviewService ===")

from ai.improvement_review_service import ImprovementReviewService

with tempfile.TemporaryDirectory() as tmpdir:
    imp_dir = Path(tmpdir) / "outputs" / "ai_improvements"
    rep_dir = Path(tmpdir) / "outputs" / "ai_improvement_reports"
    imp_dir.mkdir(parents=True)

    # テスト用 JSON を作成
    for i, priority in enumerate(["high", "medium", "low"]):
        d = make_suggestion_dict(
            article_id=f"article-{i}",
            title=f"テスト記事{i}",
            priority=priority,
        )
        (imp_dir / f"20260630_article-{i}_improvement.json").write_text(
            json.dumps(d, ensure_ascii=False), encoding="utf-8"
        )

    service = ImprovementReviewService.from_paths(
        improvement_dir=imp_dir,
        report_dir=rep_dir,
    )

    # 全件レポート
    report_path = service.run()
    check("レポートが保存される", report_path is not None, True)
    check("レポートファイルが存在する", report_path.exists() if report_path else False, True)
    check("レポートが .md ファイル", report_path.suffix if report_path else "", ".md")

    report_content = report_path.read_text(encoding="utf-8") if report_path else ""
    check("レポートに全件が含まれる", "article-0" in report_content, True)
    check("レポートに high が含まれる", "high" in report_content, True)

    # priority 絞り込み
    high_suggestions = service.get_suggestions(priority="high")
    check("get_suggestions(priority=high): 件数=1", len(high_suggestions), 1)
    check("get_suggestions(priority=high): article_id", high_suggestions[0].article_id, "article-0")

    medium_suggestions = service.get_suggestions(priority="medium")
    check("get_suggestions(priority=medium): 件数=1", len(medium_suggestions), 1)

    # article_id 絞り込み
    by_id = service.get_suggestions(article_id="article-2")
    check("get_suggestions(article_id='article-2'): 件数=1", len(by_id), 1)

    # 存在しない article_id
    not_found = service.get_suggestions(article_id="nonexistent")
    check("get_suggestions(nonexistent): 件数=0", len(not_found), 0)

# ─── Scenario 15: scripts/run_ai_improvement_report.py が存在する ───

print("\n=== Scenario 15: スクリプト存在確認 ===")

script_path = Path(__file__).parent.parent / "scripts" / "run_ai_improvement_report.py"
check("run_ai_improvement_report.py が存在する", script_path.exists(), True)

script_content = script_path.read_text(encoding="utf-8")
check("スクリプトに ImprovementReviewService の使用", "ImprovementReviewService" in script_content, True)
check("スクリプトに --priority オプション", "--priority" in script_content, True)

# ─── Scenario 16: Claude API を呼び出さない ───

print("\n=== Scenario 16: AI API 非呼び出しの確認 ===")

for filename in ["improvement_repository.py", "improvement_report_builder.py", "improvement_review_service.py"]:
    src_path = Path(__file__).parent.parent / "src" / "ai" / filename
    content = src_path.read_text(encoding="utf-8")
    check(f"{filename}: anthropic をインポートしない", "import anthropic" not in content, True)
    check(f"{filename}: ClaudeClient を使わない", "ClaudeClient" not in content, True)

# ─── Scenario 17: __init__.py エクスポート確認 ───

print("\n=== Scenario 17: ai パッケージのエクスポート ===")

from ai import (
    ImprovementRepository,
    ImprovementReportBuilder,
    ImprovementReviewService,
)
check("ImprovementRepository がエクスポートされている", ImprovementRepository.__name__, "ImprovementRepository")
check("ImprovementReportBuilder がエクスポートされている", ImprovementReportBuilder.__name__, "ImprovementReportBuilder")
check("ImprovementReviewService がエクスポートされている", ImprovementReviewService.__name__, "ImprovementReviewService")

# v1.14.0 クラスも引き続きエクスポート
from ai import AiImprovementService, NullAiImprovementService, ImprovementSuggestion
check("v1.14.0: AiImprovementService エクスポート継続", AiImprovementService.__name__, "AiImprovementService")
check("v1.14.0: NullAiImprovementService エクスポート継続", NullAiImprovementService.__name__, "NullAiImprovementService")

# ─── Scenario 18: v1.14.0 互換性 ───

print("\n=== Scenario 18: v1.14.0 互換性確認 ===")

try:
    from ai import AiImprovementConfig, PromptBuilder, ClaudeClient, NullClaudeClient
    from ai import ImprovementSuggestionParser
    from analytics import AnalyticsManager, NullAnalyticsManager
    check("v1.14.0 全クラスのインポート成功", True, True)
except ImportError as e:
    check("v1.14.0 全クラスのインポート成功", str(e), "")

# ─── 結果集計 ───

print()
print("=" * 60)
total = len(results)
passed = sum(1 for s, _ in results if s == "PASS")
failed = sum(1 for s, _ in results if s == "FAIL")
print(f"結果: {passed}/{total} PASS  |  FAIL: {failed}")
print("=" * 60)

if failed > 0:
    print()
    print("【失敗したテスト】")
    for status, label in results:
        if status == "FAIL":
            print(f"  NG  {label}")
    sys.exit(1)
else:
    print("すべてのテストが通過しました。")
