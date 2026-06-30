"""
E2E テスト: v1.19.0 AI Publish Review Foundation

テストシナリオ:
    ── PublishReviewStatus ──
    1.  PENDING / APPROVED / ON_HOLD / REJECTED の4値が定義されている
    2.  各値の .value が正しい文字列を返す

    ── AiPublishReviewResult ──
    3.  from_publish_result() が success=True の AiPublishResult を変換できる
    4.  publish_status が "success" / "skipped" / "failed" に正しく設定される
    5.  is_publish_candidate が publish_success and not publish_skipped で計算される
    6.  review_status が PENDING で生成される（デフォルト）
    7.  review_status を明示指定して生成できる
    8.  review_note が "" で生成される（デフォルト）
    9.  to_dict() が全フィールドを含む
    10. to_dict() の review_status が文字列で保存される
    11. to_dict() の published_at / reviewed_at が ISO 文字列で保存される
    12. to_json() が有効な JSON を返す
    13. JSON から復元して全フィールドが一致する
    14. skipped=True の AiPublishResult が publish_status="skipped" に変換される
    15. is_publish_candidate が skipped=True 時に False になる
    16. success=False / skipped=False が publish_status="failed" に変換される

    ── AiPublishReviewRepository ──
    17. load_publish_results() が投稿結果 JSON を返す
    18. load_publish_results(article_id=...) が絞り込みできる
    19. load_publish_results() がディレクトリ不存在時に空リストを返す
    20. save_review() が JSON ファイルを生成する
    21. save_review() のファイル名が YYYYMMDD_{article_id}_publish_review.json 形式
    22. load_reviews() が保存済み結果を返す
    23. load_reviews() がディレクトリ不存在時に空リストを返す
    24. load_reviews_by_article_id() が絞り込みできる
    25. 不正 JSON ファイルをスキップして処理継続する
    26. from_paths() が AiPublishReviewRepository を返す

    ── AiPublishReviewReportBuilder ──
    27. build() が str を返す
    28. 空リストで「対象なし」Markdown を生成する
    29. 空リストで「0 件」メッセージを含む
    30. 空リストでスクリプト案内を含む
    31. 公開候補が「公開候補（投稿成功）」セクションに含まれる
    32. is_publish_candidate の件数がサマリーに含まれる
    33. スキップが「スキップ一覧」に含まれる
    34. 失敗が「投稿失敗一覧」に含まれる
    35. review_status の件数がサマリーに含まれる
    36. wp_edit_url が公開候補に含まれる
    37. 注意書き「公開操作は含まれません」が含まれる

    ── AiPublishReviewService / NullAiPublishReviewService ──
    38. from_paths() が常に AiPublishReviewService を返す（データ0件でも）
    39. run() が投稿結果 0 件でも Path を返す（「対象なし」レポート）
    40. run() が「対象なし」レポートを生成する
    41. run() が投稿結果ありで JSON を保存する
    42. run() が Markdown レポートを保存し Path を返す
    43. run() が review_status=PENDING で生成する
    44. run() が is_publish_candidate を正しく設定する
    45. run(article_id=...) が絞り込みできる
    46. NullAiPublishReviewService.run() が None を返す
    47. NullAiPublishReviewService.get_reviews() が空リストを返す

    ── 構成・互換性 ──
    48. scripts/run_ai_publish_review.py が存在する
    49. __init__.py が新クラスをエクスポートする
    50. v1.14.0〜v1.18.0 の後方互換性が壊れない
    51. WordPress API を実際に呼び出さない（urllib を使わない）

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v1_19_0_ai_publish_review_foundation.py
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

def make_publish_result(
    article_id="test-slug",
    title="テスト記事",
    permalink="https://example.com/test/",
    source_review_status="adopted",
    wp_post_id=123,
    wp_draft_slug="test-slug-rewrite-20260630",
    wp_edit_url="https://example.com/wp-admin/post.php?post=123&action=edit",
    wp_draft_permalink="https://example.com/?p=123",
    published_at=None,
    success=True,
    skipped=False,
    skip_reason=None,
    error_message=None,
):
    from ai import AiPublishResult
    return AiPublishResult(
        article_id=article_id,
        title=title,
        original_permalink=permalink,
        source_review_status=source_review_status,
        source_rewrite_created_at=datetime(2026, 6, 30, 10, 0, 0),
        wp_post_id=wp_post_id,
        wp_draft_slug=wp_draft_slug,
        wp_edit_url=wp_edit_url,
        wp_draft_permalink=wp_draft_permalink,
        published_at=published_at or datetime(2026, 6, 30, 13, 0, 0),
        success=success,
        skipped=skipped,
        skip_reason=skip_reason,
        error_message=error_message,
    )


def make_publish_json(
    article_id="test-slug",
    title="テスト記事",
    permalink="https://example.com/test/",
    source_review_status="adopted",
    wp_post_id=123,
    success=True,
    skipped=False,
    skip_reason=None,
    error_message=None,
) -> dict:
    return {
        "article_id": article_id,
        "title": title,
        "original_permalink": permalink,
        "source_review_status": source_review_status,
        "source_rewrite_created_at": "2026-06-30T10:00:00",
        "wp_post_id": wp_post_id,
        "wp_draft_slug": f"{article_id}-rewrite-20260630",
        "wp_edit_url": f"https://example.com/wp-admin/post.php?post={wp_post_id}&action=edit",
        "wp_draft_permalink": f"https://example.com/?p={wp_post_id}",
        "published_at": "2026-06-30T13:00:00",
        "success": success,
        "skipped": skipped,
        "skip_reason": skip_reason,
        "error_message": error_message,
    }


# ═══════════════════════════════════════════════════════════
# テスト1〜2: PublishReviewStatus
# ═══════════════════════════════════════════════════════════

print("=" * 60)
print("v1.19.0 AI Publish Review Foundation E2E テスト")
print("=" * 60)
print()

print("[テスト1-2] PublishReviewStatus")
from ai import PublishReviewStatus

check_true("1. PENDING が定義されている",  hasattr(PublishReviewStatus, "PENDING"))
check_true("1. APPROVED が定義されている", hasattr(PublishReviewStatus, "APPROVED"))
check_true("1. ON_HOLD が定義されている",  hasattr(PublishReviewStatus, "ON_HOLD"))
check_true("1. REJECTED が定義されている", hasattr(PublishReviewStatus, "REJECTED"))

check("2. PENDING.value == 'pending'",   PublishReviewStatus.PENDING.value,  "pending")
check("2. APPROVED.value == 'approved'", PublishReviewStatus.APPROVED.value, "approved")
check("2. ON_HOLD.value == 'on_hold'",   PublishReviewStatus.ON_HOLD.value,  "on_hold")
check("2. REJECTED.value == 'rejected'", PublishReviewStatus.REJECTED.value, "rejected")
print()

# ═══════════════════════════════════════════════════════════
# テスト3〜16: AiPublishReviewResult
# ═══════════════════════════════════════════════════════════

print("[テスト3-16] AiPublishReviewResult")
from ai import AiPublishReviewResult

# テスト3: success=True の変換
result_ok = make_publish_result(success=True, skipped=False)
review_ok = AiPublishReviewResult.from_publish_result(result_ok)

check("3. article_id が引き継がれる", review_ok.article_id, "test-slug")
check("3. title が引き継がれる",      review_ok.title,      "テスト記事")
check_not_none("3. reviewed_at が設定される", review_ok.reviewed_at)

# テスト4: publish_status
check("4. success=True → publish_status='success'", review_ok.publish_status, "success")

result_skipped = make_publish_result(success=False, skipped=True, skip_reason="disabled",
                                     wp_post_id=None, wp_draft_slug=None,
                                     wp_edit_url=None, wp_draft_permalink=None)
review_skipped = AiPublishReviewResult.from_publish_result(result_skipped)
check("4. skipped=True → publish_status='skipped'", review_skipped.publish_status, "skipped")

result_failed = make_publish_result(success=False, skipped=False, error_message="タイムアウト",
                                    wp_post_id=None, wp_draft_slug=None,
                                    wp_edit_url=None, wp_draft_permalink=None)
review_failed = AiPublishReviewResult.from_publish_result(result_failed)
check("4. success=False/skipped=False → publish_status='failed'", review_failed.publish_status, "failed")

# テスト5: is_publish_candidate
check_true("5. success=True → is_publish_candidate=True",   review_ok.is_publish_candidate)
check_false("5. skipped=True → is_publish_candidate=False", review_skipped.is_publish_candidate)
check_false("5. failed → is_publish_candidate=False",       review_failed.is_publish_candidate)

# テスト6: review_status デフォルト
check("6. review_status が PENDING（デフォルト）",
      review_ok.review_status, PublishReviewStatus.PENDING)

# テスト7: review_status 明示指定
review_approved = AiPublishReviewResult.from_publish_result(
    result_ok, review_status=PublishReviewStatus.APPROVED
)
check("7. review_status=APPROVED を明示指定できる",
      review_approved.review_status, PublishReviewStatus.APPROVED)

# テスト8: review_note デフォルト
check("8. review_note が '' （デフォルト）", review_ok.review_note, "")
review_with_note = AiPublishReviewResult.from_publish_result(result_ok, review_note="確認済み")
check("8. review_note を指定できる", review_with_note.review_note, "確認済み")

# テスト9: to_dict() 全フィールド
d = review_ok.to_dict()
required_keys = [
    "article_id", "title", "original_permalink", "source_review_status",
    "wp_post_id", "wp_draft_slug", "wp_edit_url", "wp_draft_permalink",
    "published_at", "publish_status", "publish_success", "publish_skipped",
    "publish_skip_reason", "publish_error", "is_publish_candidate",
    "review_status", "review_note", "reviewed_at",
]
for key in required_keys:
    check_true(f"9. to_dict() に {key} が含まれる", key in d)

# テスト10: review_status が文字列
check_true("10. to_dict() の review_status が str", isinstance(d["review_status"], str))
check("10. review_status の値が 'pending'", d["review_status"], "pending")

# テスト11: ISO 文字列
check_true("11. published_at が str", isinstance(d["published_at"], str))
check_true("11. reviewed_at が str",  isinstance(d["reviewed_at"], str))
check_contains("11. published_at が ISO 形式", d["published_at"], "2026-06-30")

# テスト12: to_json()
json_str = review_ok.to_json()
check_true("12. to_json() が str", isinstance(json_str, str))
parsed = json.loads(json_str)
check("12. to_json() がパース可能", parsed["article_id"], "test-slug")
check("12. to_json() の is_publish_candidate が True", parsed["is_publish_candidate"], True)

# テスト13: JSON から復元
from ai import AiPublishReviewRepository
from ai.ai_publish_review_repository import _dict_to_publish_review_result

d_restore = review_ok.to_dict()
restored = _dict_to_publish_review_result(d_restore)
check("13. article_id が一致する",          restored.article_id,          review_ok.article_id)
check("13. publish_status が一致する",      restored.publish_status,      review_ok.publish_status)
check("13. is_publish_candidate が一致する", restored.is_publish_candidate, review_ok.is_publish_candidate)
check("13. review_status が一致する",        restored.review_status,        review_ok.review_status)

# テスト14: skipped の変換
check("14. skipped → publish_status='skipped'", review_skipped.publish_status, "skipped")
check_true("14. publish_skipped=True", review_skipped.publish_skipped)
check_false("14. publish_success=False", review_skipped.publish_success)

# テスト15: is_publish_candidate が skipped 時に False
check_false("15. skipped → is_publish_candidate=False", review_skipped.is_publish_candidate)

# テスト16: failed の変換
check("16. failed → publish_status='failed'", review_failed.publish_status, "failed")
check_false("16. publish_success=False", review_failed.publish_success)
check_false("16. publish_skipped=False", review_failed.publish_skipped)
print()

# ═══════════════════════════════════════════════════════════
# テスト17〜26: AiPublishReviewRepository
# ═══════════════════════════════════════════════════════════

print("[テスト17-26] AiPublishReviewRepository")
from ai import AiPublishRepository
from ai.rewrite_review_repository import RewriteReviewRepository


def make_review_repo(tmpdir: str, publish_dir_name="ai_publishes", review_dir_name="ai_publish_reviews"):
    """テスト用 AiPublishReviewRepository を構築する。"""
    base = Path(tmpdir)
    pub_dir = base / publish_dir_name
    rev_dir = base / review_dir_name
    pub_dir.mkdir(exist_ok=True)

    rr_repo = RewriteReviewRepository(rewrite_dir=pub_dir, review_dir=pub_dir)
    publish_repo = AiPublishRepository(rewrite_review_repo=rr_repo, publish_dir=pub_dir)
    return AiPublishReviewRepository(publish_repo=publish_repo, review_dir=rev_dir)


# テスト17: load_publish_results()
with tempfile.TemporaryDirectory() as tmpdir:
    repo = make_review_repo(tmpdir)
    pub_dir = Path(tmpdir) / "ai_publishes"

    d1 = make_publish_json(article_id="art-a", success=True)
    d2 = make_publish_json(article_id="art-b", success=False, skipped=True, skip_reason="disabled")
    (pub_dir / "20260630_art-a_publish.json").write_text(
        json.dumps(d1, ensure_ascii=False), encoding="utf-8"
    )
    (pub_dir / "20260630_art-b_publish.json").write_text(
        json.dumps(d2, ensure_ascii=False), encoding="utf-8"
    )

    results = repo.load_publish_results()
    check("17. load_publish_results() が2件返す", len(results), 2)

# テスト18: load_publish_results(article_id=...)
with tempfile.TemporaryDirectory() as tmpdir:
    repo = make_review_repo(tmpdir)
    pub_dir = Path(tmpdir) / "ai_publishes"

    d1 = make_publish_json(article_id="art-a")
    d2 = make_publish_json(article_id="art-b")
    (pub_dir / "20260630_art-a_publish.json").write_text(json.dumps(d1, ensure_ascii=False), encoding="utf-8")
    (pub_dir / "20260630_art-b_publish.json").write_text(json.dumps(d2, ensure_ascii=False), encoding="utf-8")

    results = repo.load_publish_results(article_id="art-a")
    check("18. article_id 絞り込みで1件返す", len(results), 1)
    check("18. 返った article_id が正しい", results[0].article_id, "art-a")

# テスト19: ディレクトリ不存在時
with tempfile.TemporaryDirectory() as tmpdir:
    repo = make_review_repo(tmpdir, publish_dir_name="nonexistent_publishes")
    check("19. ディレクトリ不存在時に空リスト", repo.load_publish_results(), [])

# テスト20: save_review() が JSON ファイルを生成する
with tempfile.TemporaryDirectory() as tmpdir:
    repo = make_review_repo(tmpdir)
    review = AiPublishReviewResult.from_publish_result(make_publish_result(article_id="save-test"))
    saved_path = repo.save_review(review)

    check_not_none("20. save_review() がパスを返す", saved_path)
    check_true("20. 保存ファイルが存在する",
               saved_path is not None and saved_path.exists())

# テスト21: ファイル名形式
with tempfile.TemporaryDirectory() as tmpdir:
    repo = make_review_repo(tmpdir)
    review = AiPublishReviewResult.from_publish_result(make_publish_result(article_id="fmt-test"))
    saved_path = repo.save_review(review)
    check_true("21. ファイル名が _publish_review.json で終わる",
               saved_path is not None and saved_path.name.endswith("_publish_review.json"))
    check_contains("21. ファイル名に article_id が含まれる",
                   saved_path.name if saved_path else "", "fmt-test")

# テスト22: load_reviews() が保存済み結果を返す
with tempfile.TemporaryDirectory() as tmpdir:
    repo = make_review_repo(tmpdir)
    r1 = AiPublishReviewResult.from_publish_result(make_publish_result(article_id="load-a"))
    r2 = AiPublishReviewResult.from_publish_result(make_publish_result(article_id="load-b"))
    repo.save_review(r1)
    repo.save_review(r2)

    loaded = repo.load_reviews()
    check("22. load_reviews() が2件返す", len(loaded), 2)
    article_ids = {r.article_id for r in loaded}
    check_true("22. article_id が一致する", "load-a" in article_ids and "load-b" in article_ids)

# テスト23: load_reviews() ディレクトリ不存在時
with tempfile.TemporaryDirectory() as tmpdir:
    repo = make_review_repo(tmpdir)
    check("23. review ディレクトリ不存在時に空リスト", repo.load_reviews(), [])

# テスト24: load_reviews_by_article_id()
with tempfile.TemporaryDirectory() as tmpdir:
    repo = make_review_repo(tmpdir)
    r1 = AiPublishReviewResult.from_publish_result(make_publish_result(article_id="find-me"))
    r2 = AiPublishReviewResult.from_publish_result(make_publish_result(article_id="not-me"))
    repo.save_review(r1)
    repo.save_review(r2)

    found = repo.load_reviews_by_article_id("find-me")
    check("24. load_reviews_by_article_id() が1件返す", len(found), 1)
    check("24. 返った article_id が正しい", found[0].article_id, "find-me")

# テスト25: 不正 JSON のスキップ
with tempfile.TemporaryDirectory() as tmpdir:
    repo = make_review_repo(tmpdir)
    rev_dir = Path(tmpdir) / "ai_publish_reviews"
    rev_dir.mkdir()

    # 不正 JSON
    (rev_dir / "20260630_invalid_publish_review.json").write_text("not-json", encoding="utf-8")
    # 正常 JSON
    r = AiPublishReviewResult.from_publish_result(make_publish_result(article_id="valid"))
    (rev_dir / "20260630_valid_publish_review.json").write_text(r.to_json(), encoding="utf-8")

    loaded = repo.load_reviews()
    check("25. 不正ファイルをスキップして1件返す", len(loaded), 1)
    check("25. 正常ファイルの article_id が正しい", loaded[0].article_id, "valid")

# テスト26: from_paths()
with tempfile.TemporaryDirectory() as tmpdir:
    base = Path(tmpdir)
    (base / "outputs" / "ai_publishes").mkdir(parents=True)
    repo = AiPublishReviewRepository.from_paths(base_dir=base)
    check_true("26. from_paths() が AiPublishReviewRepository を返す",
               isinstance(repo, AiPublishReviewRepository))
print()

# ═══════════════════════════════════════════════════════════
# テスト27〜37: AiPublishReviewReportBuilder
# ═══════════════════════════════════════════════════════════

print("[テスト27-37] AiPublishReviewReportBuilder")
from ai import AiPublishReviewReportBuilder

builder = AiPublishReviewReportBuilder()

# テスト27〜30: 空リスト
empty_md = builder.build([])
check_true("27. 空リストで str を返す", isinstance(empty_md, str))
check_contains("28. 空リストで「対象なし」を含む",    empty_md, "対象なし")
check_contains("29. 空リストで「0 件」を含む",        empty_md, "0 件")
check_contains("30. 空リストでスクリプト案内を含む",  empty_md, "run_ai_publish.py")

# テスト31〜37: 成功・スキップ・失敗の混在
results_for_report = [
    AiPublishReviewResult.from_publish_result(
        make_publish_result(
            article_id="success-art", title="成功記事",
            success=True, skipped=False,
            wp_edit_url="https://example.com/wp-admin/post.php?post=1&action=edit",
        )
    ),
    AiPublishReviewResult.from_publish_result(
        make_publish_result(
            article_id="skipped-art", title="スキップ記事",
            success=False, skipped=True, skip_reason="AI_PUBLISH_ENABLED=false",
            wp_post_id=None, wp_draft_slug=None,
            wp_edit_url=None, wp_draft_permalink=None,
        )
    ),
    AiPublishReviewResult.from_publish_result(
        make_publish_result(
            article_id="failed-art", title="失敗記事",
            success=False, skipped=False, error_message="接続タイムアウト",
            wp_post_id=None, wp_draft_slug=None,
            wp_edit_url=None, wp_draft_permalink=None,
        )
    ),
]

md = builder.build(results_for_report)
check_true("31. 公開候補セクションが含まれる", "公開候補（投稿成功）" in md)
check_contains("31. 成功記事タイトルが含まれる", md, "成功記事")

candidates = [r for r in results_for_report if r.is_publish_candidate]
check_contains("32. is_publish_candidate の件数がサマリーに含まれる",
               md, f"公開候補 (投稿成功): {len(candidates)} 件")

check_contains("33. スキップ一覧セクションが含まれる",  md, "スキップ一覧")
check_contains("33. スキップ記事タイトルが含まれる",    md, "スキップ記事")
check_contains("33. スキップ理由が含まれる",            md, "AI_PUBLISH_ENABLED=false")

check_contains("34. 投稿失敗セクションが含まれる",  md, "投稿失敗一覧")
check_contains("34. 失敗記事タイトルが含まれる",    md, "失敗記事")
check_contains("34. エラー内容が含まれる",          md, "接続タイムアウト")

check_contains("35. review_status の件数がサマリーに含まれる", md, "pending")

check_contains("36. wp_edit_url が公開候補に含まれる", md, "wp-admin")

check_contains("37. 注意書きが含まれる", md, "公開操作は含まれません")
print()

# ═══════════════════════════════════════════════════════════
# テスト38〜47: AiPublishReviewService / NullAiPublishReviewService
# ═══════════════════════════════════════════════════════════

print("[テスト38-47] AiPublishReviewService / NullAiPublishReviewService")
from ai import AiPublishReviewService, NullAiPublishReviewService

# テスト38: from_paths() が常に AiPublishReviewService を返す
with tempfile.TemporaryDirectory() as tmpdir:
    base = Path(tmpdir)
    # ai_publishes が存在しない状態でも AiPublishReviewService を返す
    service = AiPublishReviewService.from_paths(base_dir=base)
    check_true("38. from_paths() が AiPublishReviewService を返す（データなし）",
               isinstance(service, AiPublishReviewService))

with tempfile.TemporaryDirectory() as tmpdir:
    base = Path(tmpdir)
    (base / "outputs" / "ai_publishes").mkdir(parents=True)
    service = AiPublishReviewService.from_paths(base_dir=base)
    check_true("38. from_paths() が AiPublishReviewService を返す（ディレクトリあり）",
               isinstance(service, AiPublishReviewService))

# テスト39〜40: データ0件でも Path を返す
with tempfile.TemporaryDirectory() as tmpdir:
    base = Path(tmpdir)
    repo = make_review_repo(str(base), publish_dir_name="ai_publishes",
                            review_dir_name="ai_publish_reviews")
    rep_dir = base / "ai_publish_review_reports"
    service = AiPublishReviewService(repository=repo, report_dir=rep_dir)

    report_path = service.run()
    check_not_none("39. 0件でも run() が Path を返す", report_path)
    check_true("39. レポートファイルが存在する",
               report_path is not None and report_path.exists())

    if report_path and report_path.exists():
        content = report_path.read_text(encoding="utf-8")
        check_contains("40. 「対象なし」レポートが生成される", content, "対象なし")

# テスト41〜45: 投稿結果ありで動作確認
with tempfile.TemporaryDirectory() as tmpdir:
    base = Path(tmpdir)
    pub_dir = base / "ai_publishes"
    pub_dir.mkdir(parents=True)

    # 成功・スキップ・失敗を1件ずつ配置
    d_ok = make_publish_json(article_id="ok-art", title="成功記事", success=True)
    d_sk = make_publish_json(article_id="sk-art", title="スキップ記事",
                             success=False, skipped=True, skip_reason="disabled",
                             wp_post_id=None)
    d_er = make_publish_json(article_id="er-art", title="失敗記事",
                             success=False, skipped=False, error_message="タイムアウト",
                             wp_post_id=None)
    (pub_dir / "20260630_ok-art_publish.json").write_text(json.dumps(d_ok, ensure_ascii=False), encoding="utf-8")
    (pub_dir / "20260630_sk-art_publish.json").write_text(json.dumps(d_sk, ensure_ascii=False), encoding="utf-8")
    (pub_dir / "20260630_er-art_publish.json").write_text(json.dumps(d_er, ensure_ascii=False), encoding="utf-8")

    rr_repo = RewriteReviewRepository(rewrite_dir=pub_dir, review_dir=pub_dir)
    publish_repo = AiPublishRepository(rewrite_review_repo=rr_repo, publish_dir=pub_dir)
    rev_dir = base / "ai_publish_reviews"
    rep_dir = base / "ai_publish_review_reports"
    repo    = AiPublishReviewRepository(publish_repo=publish_repo, review_dir=rev_dir)
    service = AiPublishReviewService(repository=repo, report_dir=rep_dir)

    report_path = service.run()

    # テスト41: JSON が保存される
    review_files = list(rev_dir.glob("*_publish_review.json"))
    check("41. 3件分の JSON が保存される", len(review_files), 3)

    # テスト42: Markdown レポートが保存される
    check_not_none("42. run() が Path を返す", report_path)
    check_true("42. レポートが .md ファイル",
               report_path is not None and report_path.suffix == ".md")
    check_true("42. レポートファイルが存在する",
               report_path is not None and report_path.exists())

    # テスト43: review_status が PENDING
    reviews = repo.load_reviews()
    check_true("43. 全件 review_status=PENDING",
               all(r.review_status == PublishReviewStatus.PENDING for r in reviews))

    # テスト44: is_publish_candidate
    candidates = [r for r in reviews if r.is_publish_candidate]
    check("44. is_publish_candidate=True が1件", len(candidates), 1)
    check("44. 公開候補の article_id が正しい", candidates[0].article_id, "ok-art")

# テスト45: run(article_id=...) の絞り込み
with tempfile.TemporaryDirectory() as tmpdir:
    base = Path(tmpdir)
    pub_dir = base / "ai_publishes"
    pub_dir.mkdir(parents=True)

    d1 = make_publish_json(article_id="target-art")
    d2 = make_publish_json(article_id="other-art")
    (pub_dir / "20260630_target-art_publish.json").write_text(json.dumps(d1, ensure_ascii=False), encoding="utf-8")
    (pub_dir / "20260630_other-art_publish.json").write_text(json.dumps(d2, ensure_ascii=False), encoding="utf-8")

    rr_repo = RewriteReviewRepository(rewrite_dir=pub_dir, review_dir=pub_dir)
    publish_repo = AiPublishRepository(rewrite_review_repo=rr_repo, publish_dir=pub_dir)
    rev_dir = base / "ai_publish_reviews"
    rep_dir = base / "ai_publish_review_reports"
    repo    = AiPublishReviewRepository(publish_repo=publish_repo, review_dir=rev_dir)
    service = AiPublishReviewService(repository=repo, report_dir=rep_dir)

    service.run(article_id="target-art")
    reviews = repo.load_reviews()
    check("45. run(article_id=...) が1件のみ処理する", len(reviews), 1)
    check("45. 処理された article_id が正しい", reviews[0].article_id, "target-art")

# テスト46〜47: NullAiPublishReviewService
null_service = NullAiPublishReviewService()
null_result  = null_service.run()
check_none("46. NullAiPublishReviewService.run() が None を返す", null_result)
null_reviews = null_service.get_reviews()
check("47. NullAiPublishReviewService.get_reviews() が空リスト", null_reviews, [])
print()

# ═══════════════════════════════════════════════════════════
# テスト48〜51: 構成・互換性
# ═══════════════════════════════════════════════════════════

print("[テスト48-51] 構成・互換性")

# テスト48: スクリプト存在確認
script_path = Path(__file__).parent.parent / "scripts" / "run_ai_publish_review.py"
check_true("48. scripts/run_ai_publish_review.py が存在する", script_path.exists())
if script_path.exists():
    script_content = script_path.read_text(encoding="utf-8")
    check_contains("48. スクリプトに AiPublishReviewService の使用", script_content, "AiPublishReviewService")
    check_contains("48. スクリプトに --article-id オプション",       script_content, "--article-id")

# テスト49: __init__.py エクスポート確認
import ai as ai_pkg
new_exports = [
    "PublishReviewStatus",
    "AiPublishReviewResult",
    "AiPublishReviewRepository",
    "AiPublishReviewReportBuilder",
    "AiPublishReviewService",
    "NullAiPublishReviewService",
]
for name in new_exports:
    check_true(f"49. {name} が __init__.py からエクスポートされている", hasattr(ai_pkg, name))

# テスト50: 後方互換性確認
try:
    from ai import (
        AiImprovementConfig, ImprovementSuggestion, ImprovementSuggestionParser,
        PromptBuilder, ClaudeClient, NullClaudeClient,
        AiImprovementService, NullAiImprovementService,
    )
    check_true("50. v1.14.0 の全クラスが import できる", True)
except ImportError as e:
    check_true(f"50. v1.14.0 の全クラスが import できる（失敗: {e}）", False)

try:
    from ai import ImprovementRepository, ImprovementReportBuilder, ImprovementReviewService
    check_true("50. v1.15.0 の全クラスが import できる", True)
except ImportError as e:
    check_true(f"50. v1.15.0 の全クラスが import できる（失敗: {e}）", False)

try:
    from ai import (
        RewriteConfig, RewriteResult,
        ArticleProvider, WordPressArticleProvider, NullArticleProvider,
        RewritePromptBuilder, RewriteParser, RewriteRepository,
        RewriteService, NullRewriteService,
    )
    check_true("50. v1.16.0 の全クラスが import できる", True)
except ImportError as e:
    check_true(f"50. v1.16.0 の全クラスが import できる（失敗: {e}）", False)

try:
    from ai import (
        ReviewStatus, RewriteReviewResult,
        RewriteReviewRepository, RewriteReviewReportBuilder,
        RewriteReviewService, NullRewriteReviewService,
    )
    check_true("50. v1.17.0 の全クラスが import できる", True)
except ImportError as e:
    check_true(f"50. v1.17.0 の全クラスが import できる（失敗: {e}）", False)

try:
    from ai import (
        AiPublishConfig, AiPublishResult,
        WordPressDraftClient, NullWordPressDraftClient,
        AiPublishRepository, AiPublishReportBuilder,
        AiPublishService, NullAiPublishService,
    )
    check_true("50. v1.18.0 の全クラスが import できる", True)
except ImportError as e:
    check_true(f"50. v1.18.0 の全クラスが import できる（失敗: {e}）", False)

# テスト51: WordPress API を実際に呼ばない
new_modules = [
    "ai_publish_review_result.py",
    "ai_publish_review_repository.py",
    "ai_publish_review_report_builder.py",
    "ai_publish_review_service.py",
]
for filename in new_modules:
    src_path = Path(__file__).parent.parent / "src" / "ai" / filename
    if src_path.exists():
        content = src_path.read_text(encoding="utf-8")
        check_false(f"51. {filename}: urllib.request を使わない", "urllib.request" in content)
    else:
        check_true(f"51. {filename} が存在する（確認失敗）", False)
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
