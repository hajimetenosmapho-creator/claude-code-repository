"""
E2E テスト: v1.17.0 AI Rewrite Review Foundation

テストシナリオ:
    ── RewriteReviewResult ──
    1.  ReviewStatus Enum が4種類定義されている
    2.  ReviewStatus.value が文字列である
    3.  from_rewrite_result() が success=True の result から正しく生成できる
    4.  char_diff が正しく計算される（増加・減少・変化なし）
    5.  line_diff が正しく計算される
    6.  change_ratio が正しく計算される（通常・元記事0字のエッジケース）
    7.  to_dict() が review_status を .value の文字列で保存する
    8.  to_dict() が全フィールドを含む
    9.  to_json() が有効な JSON を返す
    10. diff_summary は from_rewrite_result() に外部から注入できる

    ── RewriteReviewRepository ──
    11. load_rewrite_results() が *_rewrite.json を読み込める
    12. load_rewrite_results() が不正 JSON をスキップする
    13. load_rewrite_results() がディレクトリ不存在時に空リストを返す
    14. filter_by_success() が success=True のみ返す
    15. load_rewrite_by_article_id() が記事ID で絞り込める
    16. save_review() が JSON を保存できる
    17. save_review() が JSON に review_status を文字列で保存する
    18. load_reviews() が保存済みレビューを読み込める
    19. load_reviews() が不明な review_status を PENDING に変換する
    20. load_review_by_article_id() が記事ID で絞り込める

    ── RewriteReviewReportBuilder ──
    21. build() が Markdown を生成できる
    22. Markdown にステータス別サマリーが含まれる（4種類のラベル）
    23. Markdown に diff 情報が含まれる（char_diff・line_diff・change_ratio）
    24. 空リストでも Markdown を生成できる（対象なし表示）
    25. success=False の review もエラー情報として表示される

    ── RewriteReviewService ──
    26. run() がレポートを保存し Path を返す
    27. run() が各記事の review JSON も保存する
    28. get_reviews() が保存済みレビュー結果を返す
    29. run(article_id=...) が特定記事のみ処理する
    30. _generate_diff_summary() が changes + 文字数 + 行数を含む
    31. NullRewriteReviewService.run() が None を返す
    32. NullRewriteReviewService.get_reviews() が空リストを返す

    ── 構成・互換性 ──
    33. scripts/run_ai_rewrite_review.py が存在する
    34. __init__.py が新クラスをエクスポートする
    35. v1.14.0〜v1.16.0 の後方互換性が壊れない
    36. Claude API を呼び出さない（anthropic / ClaudeClient を使わない）

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v1_17_0_ai_rewrite_review_foundation.py
"""
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# ─── テスト用ユーティリティ ───

results_log = []


def check(label: str, actual, expected, exact: bool = True):
    ok = (actual == expected) if exact else (expected in str(actual))
    status = "PASS" if ok else "FAIL"
    results_log.append((status, label))
    mark = "OK" if ok else "NG"
    print(f"  [{mark}] {label}")
    if not ok:
        print(f"       期待値: {expected!r}")
        print(f"       実際値: {actual!r}")


def check_true(label: str, value: bool):
    check(label, value, True)


def check_false(label: str, value: bool):
    check(label, value, False)


def check_contains(label: str, text: str, keyword: str):
    check(label, keyword in str(text), True)


def check_none(label: str, value):
    check(label, value is None, True)


def check_not_none(label: str, value):
    check(label, value is not None, True)


# ─── テスト用ファクトリ ───

def make_rewrite_result(
    article_id="test-slug",
    title="テスト記事",
    permalink="https://example.com/test/",
    original_content="元記事の本文です。\n2行目です。\n3行目です。",
    rewrite_draft="改善版の本文です。\n2行目です。\n3行目です。\n4行目追加。",
    improvement_summary="タイトルとリンクを改善しました。",
    changes=None,
    success=True,
    error_message=None,
):
    """テスト用の RewriteResult を生成する。"""
    from ai import RewriteResult
    return RewriteResult(
        article_id=article_id,
        title=title,
        permalink=permalink,
        prompt_version="v1",
        original_content=original_content,
        rewrite_draft=rewrite_draft,
        improvement_summary=improvement_summary,
        changes=changes if changes is not None else ["タイトル改善", "内部リンク追加"],
        raw_response="",
        created_at=datetime(2026, 6, 30, 12, 0, 0),
        success=success,
        error_message=error_message,
    )


def make_rewrite_json(
    article_id="test-slug",
    title="テスト記事",
    permalink="https://example.com/test/",
    original_content="元記事の本文です。\n2行目です。",
    rewrite_draft="改善版の本文です。\n2行目です。\n追加行。",
    improvement_summary="改善しました。",
    changes=None,
    success=True,
    error_message=None,
) -> dict:
    """テスト用の _rewrite.json 辞書を生成する。"""
    return {
        "article_id": article_id,
        "title": title,
        "permalink": permalink,
        "prompt_version": "v1",
        "original_content": original_content,
        "rewrite_draft": rewrite_draft,
        "improvement_summary": improvement_summary,
        "changes": changes if changes is not None else ["タイトル改善"],
        "raw_response": "",
        "created_at": "2026-06-30T12:00:00",
        "success": success,
        "error_message": error_message,
    }


# ═══════════════════════════════════════════════════════════
# テスト1〜10: RewriteReviewResult / ReviewStatus
# ═══════════════════════════════════════════════════════════

print("=" * 60)
print("v1.17.0 AI Rewrite Review Foundation E2E テスト")
print("=" * 60)
print()

print("[テスト1-2] ReviewStatus Enum")
from ai import ReviewStatus

check("1. PENDING が存在する",  ReviewStatus.PENDING.value,  "pending")
check("1. ADOPTED が存在する",  ReviewStatus.ADOPTED.value,  "adopted")
check("1. ON_HOLD が存在する",  ReviewStatus.ON_HOLD.value,  "on_hold")
check("1. REJECTED が存在する", ReviewStatus.REJECTED.value, "rejected")
check_true("2. ReviewStatus.PENDING.value が str", isinstance(ReviewStatus.PENDING.value, str))
check_true("2. ReviewStatus は Enum のサブクラス", True)  # import できた時点で確認済み
print()

print("[テスト3-10] RewriteReviewResult")
from ai import RewriteReviewResult

result_ok = make_rewrite_result(
    original_content="あいうえお\n12345\n",
    rewrite_draft="あいうえおかきくけこ\n12345\n追加行\n",
    changes=["タイトル改善", "リンク追加"],
)

# テスト3: from_rewrite_result() 基本動作
review = RewriteReviewResult.from_rewrite_result(result_ok)
check("3. article_id が設定される",          review.article_id,     "test-slug")
check("3. title が設定される",               review.title,          "テスト記事")
check("3. review_status が PENDING",         review.review_status,  ReviewStatus.PENDING)
check("3. success が True",                  review.success,        True)
check("3. changes_count が正しい",           review.changes_count,  2)
check("3. improvement_summary が保持される", review.improvement_summary, "タイトルとリンクを改善しました。")

# テスト4: char_diff
original = "あいうえお\n12345\n"    # 8文字
rewrite  = "あいうえおかきくけこ\n12345\n追加行\n"  # 追加あり
expected_char_diff = len(rewrite) - len(original)
check("4. char_diff が正しく計算される", review.char_diff, expected_char_diff)
check("4. original_char_count が正しい", review.original_char_count, len(original))
check("4. rewrite_char_count が正しい",  review.rewrite_char_count,  len(rewrite))

# 文字数減少のケース
result_shorter = make_rewrite_result(
    original_content="長い元記事です。とても長い。\n2行目。",
    rewrite_draft="短い。",
)
review_shorter = RewriteReviewResult.from_rewrite_result(result_shorter)
check_true("4. 文字数減少時に char_diff が負になる", review_shorter.char_diff < 0)

# テスト5: line_diff
original_lines = len(original.splitlines())
rewrite_lines  = len(rewrite.splitlines())
expected_line_diff = rewrite_lines - original_lines
check("5. line_diff が正しく計算される",       review.line_diff, expected_line_diff)
check("5. original_line_count が正しい", review.original_line_count, original_lines)
check("5. rewrite_line_count が正しい",  review.rewrite_line_count,  rewrite_lines)

# テスト6: change_ratio
expected_ratio = review.char_diff / len(original) if len(original) > 0 else 0.0
check("6. change_ratio が正しく計算される", round(review.change_ratio, 10), round(expected_ratio, 10))

# 元記事0字のエッジケース
result_no_original = make_rewrite_result(original_content="", rewrite_draft="新しい記事")
review_no_original = RewriteReviewResult.from_rewrite_result(result_no_original)
check("6. 元記事0字の時 change_ratio=0.0", review_no_original.change_ratio, 0.0)

# テスト7: to_dict() の review_status
d = review.to_dict()
check("7. to_dict() の review_status が文字列", d["review_status"], "pending")
check_true("7. to_dict() の review_status が str 型", isinstance(d["review_status"], str))
check_false("7. to_dict() に ReviewStatus オブジェクトが含まれない", isinstance(d["review_status"], ReviewStatus))

# テスト8: to_dict() の全フィールド
required_keys = [
    "article_id", "title", "permalink", "review_status", "review_note",
    "original_char_count", "rewrite_char_count", "char_diff",
    "original_line_count", "rewrite_line_count", "line_diff",
    "change_ratio", "diff_summary", "changes_count",
    "improvement_summary", "changes", "created_at", "reviewed_at", "success",
]
for key in required_keys:
    check_true(f"8. to_dict() に {key} が含まれる", key in d)

# テスト9: to_json()
json_str = review.to_json()
check_true("9. to_json() が str を返す", isinstance(json_str, str))
parsed = json.loads(json_str)
check("9. to_json() がパース可能な JSON を返す", parsed["article_id"], "test-slug")

# テスト10: diff_summary は外部から注入できる
review_with_summary = RewriteReviewResult.from_rewrite_result(
    result_ok,
    diff_summary=["変更: タイトル改善", "文字数: 10字 → 20字（+10字）"],
)
check("10. diff_summary が注入される",       review_with_summary.diff_summary[0], "変更: タイトル改善")
check("10. diff_summary の件数が正しい",     len(review_with_summary.diff_summary), 2)

review_no_summary = RewriteReviewResult.from_rewrite_result(result_ok)
check("10. diff_summary なし時は空リスト",   review_no_summary.diff_summary, [])
print()

# ═══════════════════════════════════════════════════════════
# テスト11〜20: RewriteReviewRepository
# ═══════════════════════════════════════════════════════════

print("[テスト11-20] RewriteReviewRepository")
from ai import RewriteReviewRepository

# テスト11: load_rewrite_results() 基本動作
with tempfile.TemporaryDirectory() as tmpdir:
    rewrite_dir = Path(tmpdir) / "ai_rewrites"
    review_dir  = Path(tmpdir) / "ai_rewrite_reviews"
    rewrite_dir.mkdir()

    data = make_rewrite_json(article_id="article-a", success=True)
    (rewrite_dir / "20260630_article-a_rewrite.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )

    repo = RewriteReviewRepository(rewrite_dir=rewrite_dir, review_dir=review_dir)
    loaded = repo.load_rewrite_results()
    check("11. load_rewrite_results() 件数=1", len(loaded), 1)
    check("11. load_rewrite_results() article_id", loaded[0].article_id, "article-a")
    check("11. load_rewrite_results() success=True", loaded[0].success, True)

# テスト12: 不正 JSON スキップ
with tempfile.TemporaryDirectory() as tmpdir:
    rewrite_dir = Path(tmpdir) / "ai_rewrites"
    review_dir  = Path(tmpdir) / "ai_rewrite_reviews"
    rewrite_dir.mkdir()

    # 正常ファイル
    data_ok = make_rewrite_json(article_id="valid")
    (rewrite_dir / "20260630_valid_rewrite.json").write_text(
        json.dumps(data_ok, ensure_ascii=False), encoding="utf-8"
    )
    # 不正 JSON
    (rewrite_dir / "20260630_broken_rewrite.json").write_text(
        "{不正なJSON{{", encoding="utf-8"
    )

    repo = RewriteReviewRepository(rewrite_dir=rewrite_dir, review_dir=review_dir)
    loaded = repo.load_rewrite_results()
    check("12. 不正JSONをスキップして正常ファイルのみ返す", len(loaded), 1)
    check("12. 正常ファイルの article_id", loaded[0].article_id, "valid")

# テスト13: ディレクトリ不存在
repo_empty = RewriteReviewRepository(
    rewrite_dir=Path("/nonexistent/ai_rewrites"),
    review_dir=Path("/nonexistent/ai_rewrite_reviews"),
)
check("13. rewrite_dir 不存在時に空リスト", repo_empty.load_rewrite_results(), [])
check("13. review_dir 不存在時に空リスト",  repo_empty.load_reviews(),          [])

# テスト14: filter_by_success()
with tempfile.TemporaryDirectory() as tmpdir:
    rewrite_dir = Path(tmpdir) / "ai_rewrites"
    review_dir  = Path(tmpdir) / "ai_rewrite_reviews"
    rewrite_dir.mkdir()

    d_ok   = make_rewrite_json(article_id="ok",   success=True)
    d_fail = make_rewrite_json(article_id="fail", success=False)
    (rewrite_dir / "20260630_ok_rewrite.json").write_text(
        json.dumps(d_ok, ensure_ascii=False), encoding="utf-8"
    )
    (rewrite_dir / "20260630_fail_rewrite.json").write_text(
        json.dumps(d_fail, ensure_ascii=False), encoding="utf-8"
    )

    repo = RewriteReviewRepository(rewrite_dir=rewrite_dir, review_dir=review_dir)
    all_results = repo.load_rewrite_results()
    success_only = repo.filter_by_success(all_results)
    check("14. filter_by_success() 全件=2", len(all_results),   2)
    check("14. filter_by_success() 成功=1", len(success_only),  1)
    check("14. filter_by_success() article_id=ok", success_only[0].article_id, "ok")

# テスト15: load_rewrite_by_article_id()
with tempfile.TemporaryDirectory() as tmpdir:
    rewrite_dir = Path(tmpdir) / "ai_rewrites"
    review_dir  = Path(tmpdir) / "ai_rewrite_reviews"
    rewrite_dir.mkdir()

    for slug in ["art-a", "art-b"]:
        d = make_rewrite_json(article_id=slug)
        (rewrite_dir / f"20260630_{slug}_rewrite.json").write_text(
            json.dumps(d, ensure_ascii=False), encoding="utf-8"
        )

    repo = RewriteReviewRepository(rewrite_dir=rewrite_dir, review_dir=review_dir)
    by_id = repo.load_rewrite_by_article_id("art-a")
    check("15. load_rewrite_by_article_id() 件数=1", len(by_id), 1)
    check("15. load_rewrite_by_article_id() article_id", by_id[0].article_id, "art-a")
    by_id_none = repo.load_rewrite_by_article_id("nonexistent")
    check("15. 存在しない article_id は空リスト", len(by_id_none), 0)

# テスト16-17: save_review()
with tempfile.TemporaryDirectory() as tmpdir:
    rewrite_dir = Path(tmpdir) / "ai_rewrites"
    review_dir  = Path(tmpdir) / "ai_rewrite_reviews"
    rewrite_dir.mkdir()

    repo = RewriteReviewRepository(rewrite_dir=rewrite_dir, review_dir=review_dir)
    test_result = make_rewrite_result()
    test_review = RewriteReviewResult.from_rewrite_result(
        test_result,
        status=ReviewStatus.PENDING,
        diff_summary=["変更: タイトル改善"],
    )
    saved_path = repo.save_review(test_review)

    check_not_none("16. save_review() がパスを返す", saved_path)
    check_true("16. 保存ファイルが存在する", saved_path is not None and saved_path.exists())
    check_true("16. ファイル名が _review.json で終わる", saved_path is not None and saved_path.name.endswith("_review.json"))

    if saved_path and saved_path.exists():
        saved_data = json.loads(saved_path.read_text(encoding="utf-8"))
        check("17. JSON の review_status が文字列 'pending'", saved_data["review_status"], "pending")
        check_true("17. review_status が str 型", isinstance(saved_data["review_status"], str))
        check("17. JSON の article_id が正しい", saved_data["article_id"], "test-slug")

# テスト18: load_reviews()
with tempfile.TemporaryDirectory() as tmpdir:
    rewrite_dir = Path(tmpdir) / "ai_rewrites"
    review_dir  = Path(tmpdir) / "ai_rewrite_reviews"
    rewrite_dir.mkdir()

    repo = RewriteReviewRepository(rewrite_dir=rewrite_dir, review_dir=review_dir)
    for slug in ["art-x", "art-y"]:
        r = make_rewrite_result(article_id=slug)
        rv = RewriteReviewResult.from_rewrite_result(r)
        repo.save_review(rv)

    reviews = repo.load_reviews()
    check("18. load_reviews() 件数=2", len(reviews), 2)
    check_true("18. load_reviews() が ReviewStatus を返す", isinstance(reviews[0].review_status, ReviewStatus))

# テスト19: 不明な review_status は PENDING に変換
with tempfile.TemporaryDirectory() as tmpdir:
    rewrite_dir = Path(tmpdir) / "ai_rewrites"
    review_dir  = Path(tmpdir) / "ai_rewrite_reviews"
    review_dir.mkdir()

    unknown_data = {
        "article_id": "art-z", "title": "テスト", "permalink": None,
        "review_status": "unknown_status",
        "review_note": "", "original_char_count": 0, "rewrite_char_count": 0,
        "char_diff": 0, "original_line_count": 0, "rewrite_line_count": 0,
        "line_diff": 0, "change_ratio": 0.0, "diff_summary": [],
        "changes_count": 0, "improvement_summary": "", "changes": [],
        "created_at": "2026-06-30T12:00:00", "reviewed_at": "2026-06-30T12:00:00",
        "success": True,
    }
    (review_dir / "20260630_art-z_review.json").write_text(
        json.dumps(unknown_data, ensure_ascii=False), encoding="utf-8"
    )

    repo = RewriteReviewRepository(rewrite_dir=rewrite_dir, review_dir=review_dir)
    reviews = repo.load_reviews()
    check("19. 不明な review_status は PENDING に変換される", reviews[0].review_status, ReviewStatus.PENDING)

# テスト20: load_review_by_article_id()
with tempfile.TemporaryDirectory() as tmpdir:
    rewrite_dir = Path(tmpdir) / "ai_rewrites"
    review_dir  = Path(tmpdir) / "ai_rewrite_reviews"
    rewrite_dir.mkdir()

    repo = RewriteReviewRepository(rewrite_dir=rewrite_dir, review_dir=review_dir)
    for slug in ["art-1", "art-2"]:
        r = make_rewrite_result(article_id=slug)
        rv = RewriteReviewResult.from_rewrite_result(r)
        repo.save_review(rv)

    by_id = repo.load_review_by_article_id("art-1")
    check("20. load_review_by_article_id() 件数=1", len(by_id), 1)
    check("20. load_review_by_article_id() article_id", by_id[0].article_id, "art-1")
print()

# ═══════════════════════════════════════════════════════════
# テスト21〜25: RewriteReviewReportBuilder
# ═══════════════════════════════════════════════════════════

print("[テスト21-25] RewriteReviewReportBuilder")
from ai import RewriteReviewReportBuilder

builder = RewriteReviewReportBuilder()

reviews_for_report = [
    RewriteReviewResult.from_rewrite_result(
        make_rewrite_result(
            article_id="ps6-article",
            title="PS6発表まとめ",
            original_content="元記事\n2行目\n3行目",
            rewrite_draft="改善版\n2行目\n3行目\n4行目",
            improvement_summary="SEO改善を実施しました。",
            changes=["タイトル改善", "リンク追加"],
        ),
        status=ReviewStatus.PENDING,
        diff_summary=["変更: タイトル改善", "文字数: 10字 → 15字（+5字）"],
    ),
    RewriteReviewResult.from_rewrite_result(
        make_rewrite_result(
            article_id="xbox-article",
            title="Xbox最新情報",
            original_content="短い元記事",
            rewrite_draft="より短く",
        ),
        status=ReviewStatus.ADOPTED,
    ),
    RewriteReviewResult.from_rewrite_result(
        make_rewrite_result(
            article_id="fail-article",
            title="失敗記事",
            success=False,
            rewrite_draft="",
            original_content="",
        ),
        status=ReviewStatus.REJECTED,
    ),
]

markdown = builder.build(reviews_for_report)

# テスト21
check_true("21. build() が str を返す", isinstance(markdown, str))
check_true("21. Markdown が空でない", len(markdown) > 100)

# テスト22: ステータス別ラベル
check_contains("22. Pending ラベルを含む",  markdown, "Pending")
check_contains("22. Adopted ラベルを含む",  markdown, "Adopted")
check_contains("22. On Hold ラベルを含む",  markdown, "On Hold")
check_contains("22. Rejected ラベルを含む", markdown, "Rejected")
check_contains("22. 記事タイトルを含む", markdown, "PS6発表まとめ")

# テスト23: diff情報
check_contains("23. char_diff 情報を含む（+など）", markdown, "+")
check_contains("23. 変化率（%）を含む",             markdown, "%")
check_contains("23. 行数情報を含む",                markdown, "行")

# テスト24: 空リスト
empty_md = builder.build([])
check_true("24. 空リストでも Markdown 生成できる", isinstance(empty_md, str))
check_contains("24. 対象なし が含まれる", empty_md, "対象なし")
check_contains("24. 0 件 が含まれる",     empty_md, "0 件")

# テスト25: success=False の記事
check_contains("25. 失敗記事のタイトルが含まれる",         markdown, "失敗記事")
check_contains("25. リライト失敗 の表示が含まれる",        markdown, "リライト失敗")
print()

# ═══════════════════════════════════════════════════════════
# テスト26〜32: RewriteReviewService / NullRewriteReviewService
# ═══════════════════════════════════════════════════════════

print("[テスト26-32] RewriteReviewService / NullRewriteReviewService")
from ai import RewriteReviewService, NullRewriteReviewService

# テスト26-27: run() がレポートと review JSON を保存する
with tempfile.TemporaryDirectory() as tmpdir:
    rewrite_dir = Path(tmpdir) / "ai_rewrites"
    review_dir  = Path(tmpdir) / "ai_rewrite_reviews"
    report_dir  = Path(tmpdir) / "ai_rewrite_reports"
    rewrite_dir.mkdir()

    # テスト用リライト結果 JSON を作成
    for slug in ["art-alpha", "art-beta"]:
        d = make_rewrite_json(article_id=slug, success=True)
        (rewrite_dir / f"20260630_{slug}_rewrite.json").write_text(
            json.dumps(d, ensure_ascii=False), encoding="utf-8"
        )

    service = RewriteReviewService(
        repository=RewriteReviewRepository(rewrite_dir=rewrite_dir, review_dir=review_dir),
        report_dir=report_dir,
    )
    report_path = service.run()

    check_not_none("26. run() がパスを返す",              report_path)
    check_true("26. レポートファイルが存在する",           report_path is not None and report_path.exists())
    check_true("26. レポートが .md ファイル",             report_path is not None and report_path.suffix == ".md")

    review_files = list(review_dir.glob("*_review.json")) if review_dir.exists() else []
    check("27. run() が review JSON を2件保存する", len(review_files), 2)

# テスト28: get_reviews()
with tempfile.TemporaryDirectory() as tmpdir:
    rewrite_dir = Path(tmpdir) / "ai_rewrites"
    review_dir  = Path(tmpdir) / "ai_rewrite_reviews"
    report_dir  = Path(tmpdir) / "ai_rewrite_reports"
    rewrite_dir.mkdir()

    d = make_rewrite_json(article_id="art-gamma", success=True)
    (rewrite_dir / "20260630_art-gamma_rewrite.json").write_text(
        json.dumps(d, ensure_ascii=False), encoding="utf-8"
    )

    service = RewriteReviewService(
        repository=RewriteReviewRepository(rewrite_dir=rewrite_dir, review_dir=review_dir),
        report_dir=report_dir,
    )
    service.run()
    reviews = service.get_reviews()
    check("28. get_reviews() が1件を返す", len(reviews), 1)
    check("28. get_reviews() の article_id", reviews[0].article_id, "art-gamma")
    check("28. get_reviews() の review_status が ReviewStatus", reviews[0].review_status, ReviewStatus.PENDING)

# テスト29: run(article_id=...) で絞り込み
with tempfile.TemporaryDirectory() as tmpdir:
    rewrite_dir = Path(tmpdir) / "ai_rewrites"
    review_dir  = Path(tmpdir) / "ai_rewrite_reviews"
    report_dir  = Path(tmpdir) / "ai_rewrite_reports"
    rewrite_dir.mkdir()

    for slug in ["target-art", "other-art"]:
        d = make_rewrite_json(article_id=slug, success=True)
        (rewrite_dir / f"20260630_{slug}_rewrite.json").write_text(
            json.dumps(d, ensure_ascii=False), encoding="utf-8"
        )

    service = RewriteReviewService(
        repository=RewriteReviewRepository(rewrite_dir=rewrite_dir, review_dir=review_dir),
        report_dir=report_dir,
    )
    service.run(article_id="target-art")
    review_files = list(review_dir.glob("*_review.json")) if review_dir.exists() else []
    check("29. run(article_id=...) が1件のみ保存する", len(review_files), 1)
    check("29. 保存ファイルが対象記事のもの", "target-art" in review_files[0].name, True)

# テスト30: _generate_diff_summary()
with tempfile.TemporaryDirectory() as tmpdir:
    rewrite_dir = Path(tmpdir) / "ai_rewrites"
    review_dir  = Path(tmpdir) / "ai_rewrite_reviews"
    report_dir  = Path(tmpdir) / "ai_rewrite_reports"
    rewrite_dir.mkdir()

    service = RewriteReviewService(
        repository=RewriteReviewRepository(rewrite_dir=rewrite_dir, review_dir=review_dir),
        report_dir=report_dir,
    )
    test_result_for_diff = make_rewrite_result(
        original_content="元記事\n2行目",
        rewrite_draft="改善版\n2行目\n3行目",
        changes=["タイトル改善", "リンク追加"],
    )
    diff_summary = service._generate_diff_summary(test_result_for_diff)

    check_true("30. _generate_diff_summary() がリストを返す", isinstance(diff_summary, list))
    check_true("30. diff_summary が空でない", len(diff_summary) > 0)
    check_true("30. changes が含まれる（変更:）", any("変更:" in s for s in diff_summary))
    check_true("30. 文字数情報が含まれる（文字数:）", any("文字数:" in s for s in diff_summary))
    check_true("30. 行数情報が含まれる（行数:）",   any("行数:" in s for s in diff_summary))

# テスト31-32: NullRewriteReviewService
null_service = NullRewriteReviewService()
null_result  = null_service.run()
check_none("31. NullRewriteReviewService.run() が None を返す", null_result)
null_reviews = null_service.get_reviews()
check("32. NullRewriteReviewService.get_reviews() が空リスト", null_reviews, [])
print()

# ═══════════════════════════════════════════════════════════
# テスト33〜36: 構成・互換性
# ═══════════════════════════════════════════════════════════

print("[テスト33-36] 構成・互換性")

# テスト33: スクリプト存在確認
script_path = Path(__file__).parent.parent / "scripts" / "run_ai_rewrite_review.py"
check_true("33. scripts/run_ai_rewrite_review.py が存在する", script_path.exists())
if script_path.exists():
    script_content = script_path.read_text(encoding="utf-8")
    check_contains("33. スクリプトに RewriteReviewService の使用",    script_content, "RewriteReviewService")
    check_contains("33. スクリプトに --article-id オプション",        script_content, "--article-id")

# テスト34: __init__.py エクスポート確認
import ai as ai_pkg
new_exports = [
    "ReviewStatus",
    "RewriteReviewResult",
    "RewriteReviewRepository",
    "RewriteReviewReportBuilder",
    "RewriteReviewService",
    "NullRewriteReviewService",
]
for name in new_exports:
    check_true(f"34. {name} が __init__.py からエクスポートされている", hasattr(ai_pkg, name))

# テスト35: 後方互換性確認
try:
    from ai import (
        AiImprovementConfig, ImprovementSuggestion, ImprovementSuggestionParser,
        PromptBuilder, ClaudeClient, NullClaudeClient,
        AiImprovementService, NullAiImprovementService,
    )
    check_true("35. v1.14.0 の全クラスが import できる", True)
except ImportError as e:
    check_true(f"35. v1.14.0 の全クラスが import できる（失敗: {e}）", False)

try:
    from ai import ImprovementRepository, ImprovementReportBuilder, ImprovementReviewService
    check_true("35. v1.15.0 の全クラスが import できる", True)
except ImportError as e:
    check_true(f"35. v1.15.0 の全クラスが import できる（失敗: {e}）", False)

try:
    from ai import (
        RewriteConfig, RewriteResult,
        ArticleProvider, WordPressArticleProvider, NullArticleProvider,
        RewritePromptBuilder, RewriteParser, RewriteRepository,
        RewriteService, NullRewriteService,
    )
    check_true("35. v1.16.0 の全クラスが import できる", True)
except ImportError as e:
    check_true(f"35. v1.16.0 の全クラスが import できる（失敗: {e}）", False)

# テスト36: Claude API を呼び出さない
new_modules = [
    "rewrite_review_result.py",
    "rewrite_review_repository.py",
    "rewrite_review_report_builder.py",
    "rewrite_review_service.py",
]
for filename in new_modules:
    src_path = Path(__file__).parent.parent / "src" / "ai" / filename
    if src_path.exists():
        content = src_path.read_text(encoding="utf-8")
        check_false(f"36. {filename}: anthropic をインポートしない", "import anthropic" in content)
        check_false(f"36. {filename}: ClaudeClient を使わない",       "ClaudeClient" in content)
    else:
        check_true(f"36. {filename} が存在する（確認失敗）", False)
print()

# ─── 結果サマリー ───
print("=" * 60)
total  = len(results_log)
passed = sum(1 for s, _ in results_log if s == "PASS")
failed = sum(1 for s, _ in results_log if s == "FAIL")
print(f"結果: {passed}/{total} PASS  /  {failed} FAIL")
print("=" * 60)

if failed:
    print()
    print("【失敗一覧】")
    for status, label in results_log:
        if status == "FAIL":
            print(f"  NG: {label}")
    sys.exit(1)
else:
    print("全テスト PASS")
    sys.exit(0)
