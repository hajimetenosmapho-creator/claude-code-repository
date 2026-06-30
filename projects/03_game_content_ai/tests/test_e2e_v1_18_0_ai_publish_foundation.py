"""
E2E テスト: v1.18.0 AI Publish Foundation

テストシナリオ:
    ── AiPublishConfig ──
    1.  is_ready() が enabled=False の場合に False を返す
    2.  is_ready() が wordpress_url 未設定時に False を返す
    3.  is_ready() が wordpress_username 未設定時に False を返す
    4.  is_ready() が wordpress_app_password 未設定時に False を返す
    5.  is_ready() が全条件を満たした場合に True を返す

    ── AiPublishResult ──
    6.  success=True の AiPublishResult を生成できる
    7.  to_dict() が全フィールドを含む
    8.  to_dict() が source_rewrite_created_at を ISO 文字列で保存する
    9.  to_dict() が source_rewrite_created_at=None を None で保存する
    10. to_json() が有効な JSON を返す
    11. skipped=True の AiPublishResult を生成できる
    12. success=False / error_message の AiPublishResult を生成できる
    13. JSON から復元して全フィールドが一致する

    ── NullWordPressDraftClient ──
    14. post_draft() が {"skipped": True, ...} を返す
    15. post_draft() の "reason" キーが str である
    16. 異なる reason を指定して NullWordPressDraftClient を生成できる

    ── AiPublishRepository ──
    17. load_adopted_reviews() が ADOPTED のみ返す
    18. load_adopted_reviews() が ADOPTED 以外を除外する
    19. load_adopted_reviews() がレビューなし時に空リストを返す
    20. load_rewrite_by_article_id() が最新 success=True の結果を返す
    21. load_rewrite_by_article_id() が存在しない article_id に None を返す
    22. filter_unpublished() が success=True 済みの記事を除外する
    23. filter_unpublished() が success=False（スキップ）の記事を含める
    24. filter_unpublished() が投稿結果なしの記事を含める
    25. save() が JSON ファイルを生成する
    26. load_publish_results() が保存済み結果を返す
    27. load_publish_results() がディレクトリ不存在時に空リストを返す

    ── AiPublishReportBuilder ──
    28. build() が str を返す
    29. 空リストで「対象なし」Markdown を生成する
    30. 投稿成功の記事が Markdown に含まれる
    31. スキップ情報が Markdown に含まれる
    32. 投稿失敗情報が Markdown に含まれる

    ── AiPublishService / NullAiPublishService ──
    33. run() が ADOPTED レビューを処理する
    34. run() が filter_unpublished で既投稿をスキップする
    35. run() が Markdown レポートを保存し Path を返す
    36. run() が NullWordPressDraftClient の skipped 応答を処理する
    37. run() が RuntimeError 時に success=False で処理継続する
    38. run(article_id=...) が特定記事のみ処理する
    39. run() で同一 article_id の複数レビューが重複投稿されない
    40. NullAiPublishService.run() が None を返す
    41. NullAiPublishService.get_results() が空リストを返す

    ── 構成・互換性 ──
    42. scripts/run_ai_publish.py が存在する
    43. __init__.py が新クラスをエクスポートする
    44. v1.14.0〜v1.17.0 の後方互換性が壊れない
    45. WordPress API を実際に呼び出さない（urllib を使わない）

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v1_18_0_ai_publish_foundation.py
"""
import json
import os
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

def make_rewrite_json(
    article_id="test-slug",
    title="テスト記事",
    permalink="https://example.com/test/",
    original_content="元記事の本文です。",
    rewrite_draft="改善版の本文です。",
    improvement_summary="改善しました。",
    changes=None,
    success=True,
    error_message=None,
    created_at="2026-06-30T10:00:00",
) -> dict:
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
        "created_at": created_at,
        "success": success,
        "error_message": error_message,
    }


def make_review_json(
    article_id="test-slug",
    title="テスト記事",
    permalink="https://example.com/test/",
    review_status="adopted",
    success=True,
    reviewed_at="2026-06-30T12:00:00",
    created_at="2026-06-30T10:00:00",
) -> dict:
    return {
        "article_id": article_id,
        "title": title,
        "permalink": permalink,
        "review_status": review_status,
        "review_note": "",
        "original_char_count": 10,
        "rewrite_char_count": 15,
        "char_diff": 5,
        "original_line_count": 1,
        "rewrite_line_count": 2,
        "line_diff": 1,
        "change_ratio": 0.5,
        "diff_summary": [],
        "changes_count": 1,
        "improvement_summary": "改善しました。",
        "changes": ["タイトル改善"],
        "created_at": created_at,
        "reviewed_at": reviewed_at,
        "success": success,
    }


def make_publish_result(
    article_id="test-slug",
    title="テスト記事",
    permalink="https://example.com/test/",
    source_review_status="adopted",
    source_rewrite_created_at=None,
    wp_post_id=123,
    wp_draft_slug="test-slug-rewrite-20260630",
    wp_edit_url="https://example.com/wp-admin/post.php?post=123&action=edit",
    wp_draft_permalink="https://example.com/?p=123",
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
        source_rewrite_created_at=source_rewrite_created_at,
        wp_post_id=wp_post_id,
        wp_draft_slug=wp_draft_slug,
        wp_edit_url=wp_edit_url,
        wp_draft_permalink=wp_draft_permalink,
        published_at=datetime(2026, 6, 30, 13, 0, 0),
        success=success,
        skipped=skipped,
        skip_reason=skip_reason,
        error_message=error_message,
    )


# ─── テスト用 WordPress クライアントスタブ ───

class _SuccessWordPressDraftClient:
    """テスト用: 常に成功レスポンスを返す偽クライアント。"""
    def __init__(self, post_id=100):
        self._post_id = post_id

    def post_draft(self, title, content, slug, excerpt=None):
        return {
            "post_id": self._post_id,
            "slug": slug,
            "edit_url": f"https://example.com/wp-admin/post.php?post={self._post_id}&action=edit",
            "permalink": f"https://example.com/?p={self._post_id}",
        }


class _ErrorWordPressDraftClient:
    """テスト用: 常に RuntimeError を送出する偽クライアント。"""
    def post_draft(self, title, content, slug, excerpt=None):
        raise RuntimeError("接続タイムアウト")


# ═══════════════════════════════════════════════════════════
# テスト1〜5: AiPublishConfig
# ═══════════════════════════════════════════════════════════

print("=" * 60)
print("v1.18.0 AI Publish Foundation E2E テスト")
print("=" * 60)
print()

print("[テスト1-5] AiPublishConfig")
from ai import AiPublishConfig

check_false("1. enabled=False → is_ready()=False",
            AiPublishConfig(enabled=False, wordpress_url="http://x.com",
                            wordpress_username="u", wordpress_app_password="p").is_ready())

check_false("2. wordpress_url 未設定 → is_ready()=False",
            AiPublishConfig(enabled=True, wordpress_url=None,
                            wordpress_username="u", wordpress_app_password="p").is_ready())

check_false("3. wordpress_username 未設定 → is_ready()=False",
            AiPublishConfig(enabled=True, wordpress_url="http://x.com",
                            wordpress_username=None, wordpress_app_password="p").is_ready())

check_false("4. wordpress_app_password 未設定 → is_ready()=False",
            AiPublishConfig(enabled=True, wordpress_url="http://x.com",
                            wordpress_username="u", wordpress_app_password=None).is_ready())

check_true("5. 全条件を満たした場合 → is_ready()=True",
           AiPublishConfig(enabled=True, wordpress_url="http://x.com",
                           wordpress_username="u", wordpress_app_password="p").is_ready())
print()

# ═══════════════════════════════════════════════════════════
# テスト6〜13: AiPublishResult
# ═══════════════════════════════════════════════════════════

print("[テスト6-13] AiPublishResult")
from ai import AiPublishResult

result_ok = make_publish_result()

# テスト6
check("6. article_id が設定される",    result_ok.article_id,   "test-slug")
check("6. success が True",            result_ok.success,      True)
check("6. skipped が False",           result_ok.skipped,      False)
check("6. wp_post_id が設定される",    result_ok.wp_post_id,   123)

# テスト7: to_dict() 全フィールド
d = result_ok.to_dict()
required_keys = [
    "article_id", "title", "original_permalink",
    "source_review_status", "source_rewrite_created_at",
    "wp_post_id", "wp_draft_slug", "wp_edit_url", "wp_draft_permalink",
    "published_at", "success", "skipped", "skip_reason", "error_message",
]
for key in required_keys:
    check_true(f"7. to_dict() に {key} が含まれる", key in d)

# テスト8: source_rewrite_created_at が ISO 文字列
result_with_dt = make_publish_result(
    source_rewrite_created_at=datetime(2026, 6, 30, 10, 0, 0)
)
d_with_dt = result_with_dt.to_dict()
check_true("8. source_rewrite_created_at が str", isinstance(d_with_dt["source_rewrite_created_at"], str))
check_contains("8. ISO 形式（2026-06-30）", d_with_dt["source_rewrite_created_at"], "2026-06-30")

# テスト9: source_rewrite_created_at=None
result_no_dt = make_publish_result(source_rewrite_created_at=None)
check_none("9. source_rewrite_created_at=None が None で保存される",
           result_no_dt.to_dict()["source_rewrite_created_at"])

# テスト10: to_json()
json_str = result_ok.to_json()
check_true("10. to_json() が str", isinstance(json_str, str))
parsed = json.loads(json_str)
check("10. to_json() がパース可能", parsed["article_id"], "test-slug")

# テスト11: skipped=True
result_skipped = make_publish_result(
    success=False, skipped=True, skip_reason="AI_PUBLISH_ENABLED=false",
    wp_post_id=None, wp_draft_slug=None, wp_edit_url=None, wp_draft_permalink=None,
)
check_true("11. skipped=True の AiPublishResult を生成できる", result_skipped.skipped)
check_false("11. skipped=True 時 success=False", result_skipped.success)
check("11. skip_reason が設定される", result_skipped.skip_reason, "AI_PUBLISH_ENABLED=false")

# テスト12: success=False / error_message
result_error = make_publish_result(
    success=False, skipped=False, error_message="接続タイムアウト",
    wp_post_id=None, wp_draft_slug=None, wp_edit_url=None, wp_draft_permalink=None,
)
check_false("12. success=False の AiPublishResult を生成できる", result_error.success)
check("12. error_message が設定される", result_error.error_message, "接続タイムアウト")

# テスト13: JSON から復元
with tempfile.TemporaryDirectory() as tmpdir:
    pub_dir = Path(tmpdir) / "ai_publishes"
    pub_dir.mkdir()
    json_path = pub_dir / "20260630_test-slug_publish.json"
    json_path.write_text(result_ok.to_json(), encoding="utf-8")

    loaded_data = json.loads(json_path.read_text(encoding="utf-8"))
    check("13. JSON の article_id が一致する", loaded_data["article_id"], "test-slug")
    check("13. JSON の success が一致する",    loaded_data["success"],    True)
    check("13. JSON の wp_post_id が一致する", loaded_data["wp_post_id"], 123)
print()

# ═══════════════════════════════════════════════════════════
# テスト14〜16: NullWordPressDraftClient
# ═══════════════════════════════════════════════════════════

print("[テスト14-16] NullWordPressDraftClient")
from ai import NullWordPressDraftClient

null_client = NullWordPressDraftClient()
response = null_client.post_draft(title="テスト", content="本文", slug="test-rewrite-20260630")

check_true("14. post_draft() が dict を返す",          isinstance(response, dict))
check_true("14. 'skipped' キーが True",                response.get("skipped") is True)
check_true("15. 'reason' キーが存在する",              "reason" in response)
check_true("15. 'reason' が str 型",                   isinstance(response.get("reason"), str))

custom_client = NullWordPressDraftClient(reason="AI_PUBLISH_ENABLED=false")
custom_response = custom_client.post_draft(title="T", content="C", slug="s")
check("16. カスタム reason が設定される", custom_response.get("reason"), "AI_PUBLISH_ENABLED=false")
print()

# ═══════════════════════════════════════════════════════════
# テスト17〜27: AiPublishRepository
# ═══════════════════════════════════════════════════════════

print("[テスト17-27] AiPublishRepository")
from ai import AiPublishRepository
from ai.rewrite_review_repository import RewriteReviewRepository

# テスト17: load_adopted_reviews() が ADOPTED のみ返す
with tempfile.TemporaryDirectory() as tmpdir:
    review_dir  = Path(tmpdir) / "ai_rewrite_reviews"
    rewrite_dir = Path(tmpdir) / "ai_rewrites"
    publish_dir = Path(tmpdir) / "ai_publishes"
    review_dir.mkdir()
    rewrite_dir.mkdir()

    for status, slug in [("adopted", "art-a"), ("pending", "art-b"), ("adopted", "art-c")]:
        d = make_review_json(article_id=slug, review_status=status)
        (review_dir / f"20260630_{slug}_review.json").write_text(
            json.dumps(d, ensure_ascii=False), encoding="utf-8"
        )

    rr_repo = RewriteReviewRepository(rewrite_dir=rewrite_dir, review_dir=review_dir)
    repo = AiPublishRepository(rewrite_review_repo=rr_repo, publish_dir=publish_dir)
    adopted = repo.load_adopted_reviews()

    check("17. load_adopted_reviews() が ADOPTED 2件を返す", len(adopted), 2)
    check_true("17. 全て review_status == ADOPTED",
               all(r.review_status.value == "adopted" for r in adopted))

# テスト18: ADOPTED 以外を除外
with tempfile.TemporaryDirectory() as tmpdir:
    review_dir  = Path(tmpdir) / "ai_rewrite_reviews"
    rewrite_dir = Path(tmpdir) / "ai_rewrites"
    publish_dir = Path(tmpdir) / "ai_publishes"
    review_dir.mkdir(); rewrite_dir.mkdir()

    for status in ["pending", "on_hold", "rejected"]:
        d = make_review_json(article_id=f"art-{status}", review_status=status)
        (review_dir / f"20260630_art-{status}_review.json").write_text(
            json.dumps(d, ensure_ascii=False), encoding="utf-8"
        )

    rr_repo = RewriteReviewRepository(rewrite_dir=rewrite_dir, review_dir=review_dir)
    repo = AiPublishRepository(rewrite_review_repo=rr_repo, publish_dir=publish_dir)
    check("18. ADOPTED 以外は除外される", len(repo.load_adopted_reviews()), 0)

# テスト19: レビューなし
with tempfile.TemporaryDirectory() as tmpdir:
    review_dir  = Path(tmpdir) / "ai_rewrite_reviews"
    rewrite_dir = Path(tmpdir) / "ai_rewrites"
    publish_dir = Path(tmpdir) / "ai_publishes"
    rewrite_dir.mkdir()

    rr_repo = RewriteReviewRepository(rewrite_dir=rewrite_dir, review_dir=review_dir)
    repo = AiPublishRepository(rewrite_review_repo=rr_repo, publish_dir=publish_dir)
    check("19. レビューなし時に空リスト", len(repo.load_adopted_reviews()), 0)

# テスト20: load_rewrite_by_article_id() が最新 success=True を返す
with tempfile.TemporaryDirectory() as tmpdir:
    review_dir  = Path(tmpdir) / "ai_rewrite_reviews"
    rewrite_dir = Path(tmpdir) / "ai_rewrites"
    publish_dir = Path(tmpdir) / "ai_publishes"
    review_dir.mkdir(); rewrite_dir.mkdir()

    # success=False のリライト（古い）
    d_fail = make_rewrite_json(
        article_id="art-x", success=False, created_at="2026-06-29T10:00:00"
    )
    (rewrite_dir / "20260629_art-x_rewrite.json").write_text(
        json.dumps(d_fail, ensure_ascii=False), encoding="utf-8"
    )
    # success=True のリライト（新しい）
    d_ok = make_rewrite_json(
        article_id="art-x", success=True,
        rewrite_draft="最新の改善版",
        created_at="2026-06-30T10:00:00"
    )
    (rewrite_dir / "20260630_art-x_rewrite.json").write_text(
        json.dumps(d_ok, ensure_ascii=False), encoding="utf-8"
    )

    rr_repo = RewriteReviewRepository(rewrite_dir=rewrite_dir, review_dir=review_dir)
    repo = AiPublishRepository(rewrite_review_repo=rr_repo, publish_dir=publish_dir)
    rewrite = repo.load_rewrite_by_article_id("art-x")

    check_not_none("20. success=True の結果が返る", rewrite)
    check_true("20. success=True の結果のみ", rewrite is not None and rewrite.success)

# テスト21: 存在しない article_id
with tempfile.TemporaryDirectory() as tmpdir:
    review_dir  = Path(tmpdir) / "ai_rewrite_reviews"
    rewrite_dir = Path(tmpdir) / "ai_rewrites"
    publish_dir = Path(tmpdir) / "ai_publishes"
    rewrite_dir.mkdir()

    rr_repo = RewriteReviewRepository(rewrite_dir=rewrite_dir, review_dir=review_dir)
    repo = AiPublishRepository(rewrite_review_repo=rr_repo, publish_dir=publish_dir)
    check_none("21. 存在しない article_id → None", repo.load_rewrite_by_article_id("nonexistent"))

# テスト22: filter_unpublished() が success=True 済みを除外
with tempfile.TemporaryDirectory() as tmpdir:
    review_dir  = Path(tmpdir) / "ai_rewrite_reviews"
    rewrite_dir = Path(tmpdir) / "ai_rewrites"
    publish_dir = Path(tmpdir) / "ai_publishes"
    review_dir.mkdir(); rewrite_dir.mkdir()

    rr_repo = RewriteReviewRepository(rewrite_dir=rewrite_dir, review_dir=review_dir)
    repo = AiPublishRepository(rewrite_review_repo=rr_repo, publish_dir=publish_dir)

    # 成功済みの publish 結果を保存
    published = make_publish_result(article_id="art-published", success=True)
    repo.save(published)

    # レビューリストを作成（published と unpublished）
    from ai import RewriteReviewResult, ReviewStatus
    review_published = RewriteReviewResult(
        article_id="art-published", title="公開済み", permalink=None,
        review_status=ReviewStatus.ADOPTED, review_note="",
        original_char_count=10, rewrite_char_count=15, char_diff=5,
        original_line_count=1, rewrite_line_count=2, line_diff=1,
        change_ratio=0.5, diff_summary=[], changes_count=1,
        improvement_summary="", changes=[],
        created_at=datetime(2026, 6, 30, 10, 0), success=True,
    )
    review_new = RewriteReviewResult(
        article_id="art-new", title="未公開", permalink=None,
        review_status=ReviewStatus.ADOPTED, review_note="",
        original_char_count=10, rewrite_char_count=15, char_diff=5,
        original_line_count=1, rewrite_line_count=2, line_diff=1,
        change_ratio=0.5, diff_summary=[], changes_count=1,
        improvement_summary="", changes=[],
        created_at=datetime(2026, 6, 30, 10, 0), success=True,
    )
    filtered = repo.filter_unpublished([review_published, review_new])
    check("22. filter_unpublished() が success=True 済みを除外", len(filtered), 1)
    check("22. 残るのは未投稿の記事", filtered[0].article_id, "art-new")

# テスト23: filter_unpublished() が success=False（スキップ）を含める
with tempfile.TemporaryDirectory() as tmpdir:
    review_dir  = Path(tmpdir) / "ai_rewrite_reviews"
    rewrite_dir = Path(tmpdir) / "ai_rewrites"
    publish_dir = Path(tmpdir) / "ai_publishes"
    review_dir.mkdir(); rewrite_dir.mkdir()

    rr_repo = RewriteReviewRepository(rewrite_dir=rewrite_dir, review_dir=review_dir)
    repo = AiPublishRepository(rewrite_review_repo=rr_repo, publish_dir=publish_dir)

    # スキップ結果（success=False）を保存
    skipped_result = make_publish_result(
        article_id="art-skipped", success=False, skipped=True,
        skip_reason="AI_PUBLISH_ENABLED=false",
        wp_post_id=None, wp_draft_slug=None, wp_edit_url=None, wp_draft_permalink=None,
    )
    repo.save(skipped_result)

    review_skipped = RewriteReviewResult(
        article_id="art-skipped", title="スキップ済み", permalink=None,
        review_status=ReviewStatus.ADOPTED, review_note="",
        original_char_count=10, rewrite_char_count=15, char_diff=5,
        original_line_count=1, rewrite_line_count=2, line_diff=1,
        change_ratio=0.5, diff_summary=[], changes_count=1,
        improvement_summary="", changes=[],
        created_at=datetime(2026, 6, 30, 10, 0), success=True,
    )
    filtered = repo.filter_unpublished([review_skipped])
    check("23. スキップ済み（success=False）は再試行対象に含まれる", len(filtered), 1)

# テスト24: 投稿結果なしの記事を含める
with tempfile.TemporaryDirectory() as tmpdir:
    review_dir  = Path(tmpdir) / "ai_rewrite_reviews"
    rewrite_dir = Path(tmpdir) / "ai_rewrites"
    publish_dir = Path(tmpdir) / "ai_publishes"
    review_dir.mkdir(); rewrite_dir.mkdir()

    rr_repo = RewriteReviewRepository(rewrite_dir=rewrite_dir, review_dir=review_dir)
    repo = AiPublishRepository(rewrite_review_repo=rr_repo, publish_dir=publish_dir)

    review_no_result = RewriteReviewResult(
        article_id="art-no-result", title="投稿履歴なし", permalink=None,
        review_status=ReviewStatus.ADOPTED, review_note="",
        original_char_count=10, rewrite_char_count=15, char_diff=5,
        original_line_count=1, rewrite_line_count=2, line_diff=1,
        change_ratio=0.5, diff_summary=[], changes_count=1,
        improvement_summary="", changes=[],
        created_at=datetime(2026, 6, 30, 10, 0), success=True,
    )
    filtered = repo.filter_unpublished([review_no_result])
    check("24. 投稿履歴なしの記事は対象に含まれる", len(filtered), 1)

# テスト25〜27: save() / load_publish_results()
with tempfile.TemporaryDirectory() as tmpdir:
    review_dir  = Path(tmpdir) / "ai_rewrite_reviews"
    rewrite_dir = Path(tmpdir) / "ai_rewrites"
    publish_dir = Path(tmpdir) / "ai_publishes"
    review_dir.mkdir(); rewrite_dir.mkdir()

    rr_repo = RewriteReviewRepository(rewrite_dir=rewrite_dir, review_dir=review_dir)
    repo = AiPublishRepository(rewrite_review_repo=rr_repo, publish_dir=publish_dir)

    r = make_publish_result(article_id="save-test")
    saved_path = repo.save(r)

    check_not_none("25. save() がパスを返す", saved_path)
    check_true("25. 保存ファイルが存在する",
               saved_path is not None and saved_path.exists())
    check_true("25. ファイル名が _publish.json で終わる",
               saved_path is not None and saved_path.name.endswith("_publish.json"))

    loaded = repo.load_publish_results()
    check("26. load_publish_results() 件数=1", len(loaded), 1)
    check("26. article_id が一致する", loaded[0].article_id, "save-test")
    check("26. success が一致する",    loaded[0].success,    True)

# テスト27: ディレクトリ不存在時
with tempfile.TemporaryDirectory() as tmpdir:
    review_dir  = Path(tmpdir) / "ai_rewrite_reviews"
    rewrite_dir = Path(tmpdir) / "ai_rewrites"
    publish_dir = Path(tmpdir) / "nonexistent_publishes"
    rewrite_dir.mkdir()

    rr_repo = RewriteReviewRepository(rewrite_dir=rewrite_dir, review_dir=review_dir)
    repo = AiPublishRepository(rewrite_review_repo=rr_repo, publish_dir=publish_dir)
    check("27. ディレクトリ不存在時に空リスト", repo.load_publish_results(), [])
print()

# ═══════════════════════════════════════════════════════════
# テスト28〜32: AiPublishReportBuilder
# ═══════════════════════════════════════════════════════════

print("[テスト28-32] AiPublishReportBuilder")
from ai import AiPublishReportBuilder

builder = AiPublishReportBuilder()

# テスト28: 空リスト
empty_md = builder.build([])
check_true("28. 空リストで str を返す", isinstance(empty_md, str))

# テスト29: 空リストで「対象なし」
check_contains("29. 空リストで「対象なし」を含む", empty_md, "対象なし")
check_contains("29. 空リストで「0 件」を含む",     empty_md, "0 件")

# テスト30〜32: 成功・スキップ・失敗の混在
results_for_report = [
    make_publish_result(
        article_id="success-art", title="成功記事",
        success=True, skipped=False,
    ),
    make_publish_result(
        article_id="skipped-art", title="スキップ記事",
        success=False, skipped=True, skip_reason="AI_PUBLISH_ENABLED=false",
        wp_post_id=None, wp_draft_slug=None, wp_edit_url=None, wp_draft_permalink=None,
    ),
    make_publish_result(
        article_id="failed-art", title="失敗記事",
        success=False, skipped=False, error_message="接続タイムアウト",
        wp_post_id=None, wp_draft_slug=None, wp_edit_url=None, wp_draft_permalink=None,
    ),
]

md = builder.build(results_for_report)
check_true("30. build() が str を返す", isinstance(md, str))
check_contains("30. 成功記事タイトルが含まれる",   md, "成功記事")
check_contains("30. 投稿成功セクションが含まれる", md, "投稿成功")
check_contains("31. スキップ記事タイトルが含まれる", md, "スキップ記事")
check_contains("31. スキップ理由が含まれる",        md, "AI_PUBLISH_ENABLED=false")
check_contains("32. 失敗記事タイトルが含まれる",   md, "失敗記事")
check_contains("32. エラー情報が含まれる",          md, "接続タイムアウト")
print()

# ═══════════════════════════════════════════════════════════
# テスト33〜41: AiPublishService / NullAiPublishService
# ═══════════════════════════════════════════════════════════

print("[テスト33-41] AiPublishService / NullAiPublishService")
from ai import AiPublishService, NullAiPublishService

# テスト33: run() が ADOPTED レビューを処理する
with tempfile.TemporaryDirectory() as tmpdir:
    review_dir  = Path(tmpdir) / "ai_rewrite_reviews"
    rewrite_dir = Path(tmpdir) / "ai_rewrites"
    publish_dir = Path(tmpdir) / "ai_publishes"
    report_dir  = Path(tmpdir) / "ai_publish_reports"
    review_dir.mkdir(); rewrite_dir.mkdir()

    # ADOPTED レビューと対応するリライトを配置
    d_review  = make_review_json(article_id="test-art", review_status="adopted")
    d_rewrite = make_rewrite_json(article_id="test-art", success=True)
    (review_dir  / "20260630_test-art_review.json").write_text(
        json.dumps(d_review,  ensure_ascii=False), encoding="utf-8"
    )
    (rewrite_dir / "20260630_test-art_rewrite.json").write_text(
        json.dumps(d_rewrite, ensure_ascii=False), encoding="utf-8"
    )

    rr_repo = RewriteReviewRepository(rewrite_dir=rewrite_dir, review_dir=review_dir)
    repo    = AiPublishRepository(rewrite_review_repo=rr_repo, publish_dir=publish_dir)
    service = AiPublishService(
        repository=repo,
        client=_SuccessWordPressDraftClient(post_id=42),
        report_dir=report_dir,
    )
    service.run()

    pub_results = repo.load_publish_results()
    check("33. run() が採用済みレビューを処理する", len(pub_results), 1)
    check("33. 投稿成功 success=True",   pub_results[0].success,    True)
    check("33. wp_post_id が設定される", pub_results[0].wp_post_id, 42)

# テスト34: 既投稿をスキップする
with tempfile.TemporaryDirectory() as tmpdir:
    review_dir  = Path(tmpdir) / "ai_rewrite_reviews"
    rewrite_dir = Path(tmpdir) / "ai_rewrites"
    publish_dir = Path(tmpdir) / "ai_publishes"
    report_dir  = Path(tmpdir) / "ai_publish_reports"
    review_dir.mkdir(); rewrite_dir.mkdir()

    d_review  = make_review_json(article_id="already-pub", review_status="adopted")
    d_rewrite = make_rewrite_json(article_id="already-pub", success=True)
    (review_dir  / "20260630_already-pub_review.json").write_text(
        json.dumps(d_review,  ensure_ascii=False), encoding="utf-8"
    )
    (rewrite_dir / "20260630_already-pub_rewrite.json").write_text(
        json.dumps(d_rewrite, ensure_ascii=False), encoding="utf-8"
    )

    rr_repo = RewriteReviewRepository(rewrite_dir=rewrite_dir, review_dir=review_dir)
    repo    = AiPublishRepository(rewrite_review_repo=rr_repo, publish_dir=publish_dir)

    # 事前に成功済み publish 結果を保存
    repo.save(make_publish_result(article_id="already-pub", success=True))

    service = AiPublishService(
        repository=repo,
        client=_SuccessWordPressDraftClient(),
        report_dir=report_dir,
    )
    service.run()

    pub_results = repo.load_publish_results()
    check("34. 既投稿は再投稿されない（件数=1のまま）", len(pub_results), 1)

# テスト35: run() が Markdown レポートを返す
with tempfile.TemporaryDirectory() as tmpdir:
    review_dir  = Path(tmpdir) / "ai_rewrite_reviews"
    rewrite_dir = Path(tmpdir) / "ai_rewrites"
    publish_dir = Path(tmpdir) / "ai_publishes"
    report_dir  = Path(tmpdir) / "ai_publish_reports"
    review_dir.mkdir(); rewrite_dir.mkdir()

    rr_repo = RewriteReviewRepository(rewrite_dir=rewrite_dir, review_dir=review_dir)
    repo    = AiPublishRepository(rewrite_review_repo=rr_repo, publish_dir=publish_dir)
    service = AiPublishService(
        repository=repo,
        client=NullWordPressDraftClient(),
        report_dir=report_dir,
    )
    report_path = service.run()

    check_not_none("35. run() がパスを返す", report_path)
    check_true("35. レポートファイルが存在する",
               report_path is not None and report_path.exists())
    check_true("35. レポートが .md ファイル",
               report_path is not None and report_path.suffix == ".md")

# テスト36: NullWordPressDraftClient の skipped 応答を処理する
with tempfile.TemporaryDirectory() as tmpdir:
    review_dir  = Path(tmpdir) / "ai_rewrite_reviews"
    rewrite_dir = Path(tmpdir) / "ai_rewrites"
    publish_dir = Path(tmpdir) / "ai_publishes"
    report_dir  = Path(tmpdir) / "ai_publish_reports"
    review_dir.mkdir(); rewrite_dir.mkdir()

    d_review  = make_review_json(article_id="skip-art", review_status="adopted")
    d_rewrite = make_rewrite_json(article_id="skip-art", success=True)
    (review_dir  / "20260630_skip-art_review.json").write_text(
        json.dumps(d_review,  ensure_ascii=False), encoding="utf-8"
    )
    (rewrite_dir / "20260630_skip-art_rewrite.json").write_text(
        json.dumps(d_rewrite, ensure_ascii=False), encoding="utf-8"
    )

    rr_repo = RewriteReviewRepository(rewrite_dir=rewrite_dir, review_dir=review_dir)
    repo    = AiPublishRepository(rewrite_review_repo=rr_repo, publish_dir=publish_dir)
    service = AiPublishService(
        repository=repo,
        client=NullWordPressDraftClient(reason="AI_PUBLISH_ENABLED=false"),
        report_dir=report_dir,
    )
    service.run()

    pub_results = repo.load_publish_results()
    check("36. skipped 応答が AiPublishResult に反映される", len(pub_results), 1)
    check_true("36. skipped=True", pub_results[0].skipped)
    check_false("36. success=False", pub_results[0].success)
    check("36. skip_reason が設定される",
          pub_results[0].skip_reason, "AI_PUBLISH_ENABLED=false")

# テスト37: RuntimeError 時に処理継続
with tempfile.TemporaryDirectory() as tmpdir:
    review_dir  = Path(tmpdir) / "ai_rewrite_reviews"
    rewrite_dir = Path(tmpdir) / "ai_rewrites"
    publish_dir = Path(tmpdir) / "ai_publishes"
    report_dir  = Path(tmpdir) / "ai_publish_reports"
    review_dir.mkdir(); rewrite_dir.mkdir()

    for slug in ["err-art-1", "err-art-2"]:
        d_r = make_review_json(article_id=slug, review_status="adopted")
        d_w = make_rewrite_json(article_id=slug, success=True)
        (review_dir  / f"20260630_{slug}_review.json").write_text(
            json.dumps(d_r, ensure_ascii=False), encoding="utf-8"
        )
        (rewrite_dir / f"20260630_{slug}_rewrite.json").write_text(
            json.dumps(d_w, ensure_ascii=False), encoding="utf-8"
        )

    rr_repo = RewriteReviewRepository(rewrite_dir=rewrite_dir, review_dir=review_dir)
    repo    = AiPublishRepository(rewrite_review_repo=rr_repo, publish_dir=publish_dir)
    service = AiPublishService(
        repository=repo,
        client=_ErrorWordPressDraftClient(),
        report_dir=report_dir,
    )
    service.run()

    pub_results = repo.load_publish_results()
    check("37. RuntimeError でも2件すべて処理される", len(pub_results), 2)
    check_true("37. 両方 success=False", all(not r.success for r in pub_results))
    check_true("37. error_message が設定される",
               all(r.error_message is not None for r in pub_results))

# テスト38: run(article_id=...) で絞り込み
with tempfile.TemporaryDirectory() as tmpdir:
    review_dir  = Path(tmpdir) / "ai_rewrite_reviews"
    rewrite_dir = Path(tmpdir) / "ai_rewrites"
    publish_dir = Path(tmpdir) / "ai_publishes"
    report_dir  = Path(tmpdir) / "ai_publish_reports"
    review_dir.mkdir(); rewrite_dir.mkdir()

    for slug in ["target", "other"]:
        d_r = make_review_json(article_id=slug, review_status="adopted")
        d_w = make_rewrite_json(article_id=slug, success=True)
        (review_dir  / f"20260630_{slug}_review.json").write_text(
            json.dumps(d_r, ensure_ascii=False), encoding="utf-8"
        )
        (rewrite_dir / f"20260630_{slug}_rewrite.json").write_text(
            json.dumps(d_w, ensure_ascii=False), encoding="utf-8"
        )

    rr_repo = RewriteReviewRepository(rewrite_dir=rewrite_dir, review_dir=review_dir)
    repo    = AiPublishRepository(rewrite_review_repo=rr_repo, publish_dir=publish_dir)
    service = AiPublishService(
        repository=repo,
        client=_SuccessWordPressDraftClient(),
        report_dir=report_dir,
    )
    service.run(article_id="target")

    pub_results = repo.load_publish_results()
    check("38. run(article_id=...) が1件のみ処理する", len(pub_results), 1)
    check("38. 処理された article_id が正しい", pub_results[0].article_id, "target")

# テスト39: 同一 article_id の複数レビューが重複投稿されない
with tempfile.TemporaryDirectory() as tmpdir:
    review_dir  = Path(tmpdir) / "ai_rewrite_reviews"
    rewrite_dir = Path(tmpdir) / "ai_rewrites"
    publish_dir = Path(tmpdir) / "ai_publishes"
    report_dir  = Path(tmpdir) / "ai_publish_reports"
    review_dir.mkdir(); rewrite_dir.mkdir()

    # 同じ article_id に ADOPTED レビューが2件
    d_r1 = make_review_json(
        article_id="dup-art", review_status="adopted",
        reviewed_at="2026-06-29T12:00:00"
    )
    d_r2 = make_review_json(
        article_id="dup-art", review_status="adopted",
        reviewed_at="2026-06-30T12:00:00"
    )
    d_w  = make_rewrite_json(article_id="dup-art", success=True)

    (review_dir  / "20260629_dup-art_review.json").write_text(
        json.dumps(d_r1, ensure_ascii=False), encoding="utf-8"
    )
    (review_dir  / "20260630_dup-art_review.json").write_text(
        json.dumps(d_r2, ensure_ascii=False), encoding="utf-8"
    )
    (rewrite_dir / "20260630_dup-art_rewrite.json").write_text(
        json.dumps(d_w, ensure_ascii=False), encoding="utf-8"
    )

    rr_repo = RewriteReviewRepository(rewrite_dir=rewrite_dir, review_dir=review_dir)
    repo    = AiPublishRepository(rewrite_review_repo=rr_repo, publish_dir=publish_dir)
    service = AiPublishService(
        repository=repo,
        client=_SuccessWordPressDraftClient(),
        report_dir=report_dir,
    )
    service.run()

    pub_results = repo.load_publish_results()
    check("39. 同一 article_id は1回しか投稿されない", len(pub_results), 1)

# テスト40〜41: NullAiPublishService
null_service = NullAiPublishService()
null_result  = null_service.run()
check_none("40. NullAiPublishService.run() が None を返す", null_result)
null_results = null_service.get_results()
check("41. NullAiPublishService.get_results() が空リスト", null_results, [])
print()

# ═══════════════════════════════════════════════════════════
# テスト42〜45: 構成・互換性
# ═══════════════════════════════════════════════════════════

print("[テスト42-45] 構成・互換性")

# テスト42: スクリプト存在確認
script_path = Path(__file__).parent.parent / "scripts" / "run_ai_publish.py"
check_true("42. scripts/run_ai_publish.py が存在する", script_path.exists())
if script_path.exists():
    script_content = script_path.read_text(encoding="utf-8")
    check_contains("42. スクリプトに AiPublishService の使用",  script_content, "AiPublishService")
    check_contains("42. スクリプトに --article-id オプション", script_content, "--article-id")

# テスト43: __init__.py エクスポート確認
import ai as ai_pkg
new_exports = [
    "AiPublishConfig",
    "AiPublishResult",
    "WordPressDraftClient",
    "NullWordPressDraftClient",
    "AiPublishRepository",
    "AiPublishReportBuilder",
    "AiPublishService",
    "NullAiPublishService",
]
for name in new_exports:
    check_true(f"43. {name} が __init__.py からエクスポートされている", hasattr(ai_pkg, name))

# テスト44: 後方互換性確認
try:
    from ai import (
        AiImprovementConfig, ImprovementSuggestion, ImprovementSuggestionParser,
        PromptBuilder, ClaudeClient, NullClaudeClient,
        AiImprovementService, NullAiImprovementService,
    )
    check_true("44. v1.14.0 の全クラスが import できる", True)
except ImportError as e:
    check_true(f"44. v1.14.0 の全クラスが import できる（失敗: {e}）", False)

try:
    from ai import ImprovementRepository, ImprovementReportBuilder, ImprovementReviewService
    check_true("44. v1.15.0 の全クラスが import できる", True)
except ImportError as e:
    check_true(f"44. v1.15.0 の全クラスが import できる（失敗: {e}）", False)

try:
    from ai import (
        RewriteConfig, RewriteResult,
        ArticleProvider, WordPressArticleProvider, NullArticleProvider,
        RewritePromptBuilder, RewriteParser, RewriteRepository,
        RewriteService, NullRewriteService,
    )
    check_true("44. v1.16.0 の全クラスが import できる", True)
except ImportError as e:
    check_true(f"44. v1.16.0 の全クラスが import できる（失敗: {e}）", False)

try:
    from ai import (
        ReviewStatus, RewriteReviewResult,
        RewriteReviewRepository, RewriteReviewReportBuilder,
        RewriteReviewService, NullRewriteReviewService,
    )
    check_true("44. v1.17.0 の全クラスが import できる", True)
except ImportError as e:
    check_true(f"44. v1.17.0 の全クラスが import できる（失敗: {e}）", False)

# テスト45: WordPress API を実際に呼ばない（urllib を使わない）
new_modules = [
    "ai_publish_config.py",
    "ai_publish_result.py",
    "ai_publish_repository.py",
    "ai_publish_report_builder.py",
    "ai_publish_service.py",
]
for filename in new_modules:
    src_path = Path(__file__).parent.parent / "src" / "ai" / filename
    if src_path.exists():
        content = src_path.read_text(encoding="utf-8")
        check_false(f"45. {filename}: urllib.request を使わない", "urllib.request" in content)
    else:
        check_true(f"45. {filename} が存在する（確認失敗）", False)

# wordpress_draft_client.py は urllib を使うが、テスト対象は別モジュール
client_path = Path(__file__).parent.parent / "src" / "ai" / "wordpress_draft_client.py"
if client_path.exists():
    content = client_path.read_text(encoding="utf-8")
    check_contains("45. wordpress_draft_client.py: status='draft' がハードコードされている",
                   content, '"draft"')
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
