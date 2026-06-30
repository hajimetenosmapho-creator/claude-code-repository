"""
E2E テスト: v1.11.0 SaveResult Foundation

テストシナリオ:
    1. SaveResult のフィールド・プロパティ確認
    2. MarkdownOutput.save() が SaveResult を返す
    3. WordPressOutput.save() が SaveResult を返す（HTTP モック使用）
    4. WordPressOutput.save() 失敗時に RuntimeError が発生する
    5. OutputManager.save_all() が list[SaveResult] を返す
    6. LogManager.log_article() が post_id を直接受け取れる
    7. LogManager 後方互換（post_id 未指定時は edit_url から抽出）
    8. post_id が API レスポンスから直接取得される（正規表現非依存の確認）

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v1_11_0_save_result.py
"""
import sys
import os
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

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

# ─── シナリオ 1: SaveResult フィールド・プロパティ ───

print("\n=== Scenario 1: SaveResult fields and properties ===")

from outputs.save_result import SaveResult

wp_result = SaveResult(
    success=True,
    output_type="wordpress",
    post_id=10340,
    title="PS6正式発表",
    slug="ps6-announced-20260630",
    status="draft",
    edit_url="https://nozo3-kao6.tokyo/wp-admin/post.php?post=10340&action=edit",
    permalink="https://nozo3-kao6.tokyo/ps6-announced-20260630/",
)
file_result = SaveResult(
    success=True,
    output_type="file",
    edit_url="/path/to/output/file.md",
)
failed_result = SaveResult(
    success=False,
    output_type="wordpress",
    error_message="WordPress投稿失敗 (HTTP 401): Unauthorized",
)

check("WP SaveResult.is_wordpress = True", wp_result.is_wordpress, True)
check("File SaveResult.is_wordpress = False", file_result.is_wordpress, False)
check("WP SaveResult.post_id = 10340", wp_result.post_id, 10340)
check("WP SaveResult.slug = ps6-announced-20260630", wp_result.slug, "ps6-announced-20260630")
check("WP SaveResult.destination (後方互換)", wp_result.destination, "https://nozo3-kao6.tokyo/wp-admin/post.php?post=10340&action=edit")
check("File SaveResult.destination", file_result.destination, "/path/to/output/file.md")
check("Failed SaveResult.success = False", failed_result.success, False)
check("Failed SaveResult.is_wordpress = True", failed_result.is_wordpress, True)
check("Failed SaveResult.post_id = None", failed_result.post_id, None)

# ─── シナリオ 2: MarkdownOutput.save() が SaveResult を返す ───

print("\n=== Scenario 2: MarkdownOutput returns SaveResult ===")

from outputs.markdown_output import MarkdownOutput
from outputs.save_result import SaveResult as SR
from collector import NewsItem
from publishing_config import PublishStatus
from outputs.base import ArticleData

def make_article():
    item = NewsItem(
        title="PS6正式発表",
        url="https://blog.playstation.com/test",
        summary="PlayStation 6 が正式に発表されました。",
        source="PlayStation Blog",
        published_at="2026-06-30",
        image_candidates=[],
    )
    return ArticleData(
        item=item,
        importance="S",
        seo_title="PS6が正式発表",
        article_body="PS6が発表されました。",
        x_post="PS6発表！ https://nozo3-kao6.tokyo/ps6/",
        slug="ps6-announced-20260630",
        publish_status=PublishStatus.DRAFT,
    )

with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp)
    md_output = MarkdownOutput(output_dir=tmp_path)
    article = make_article()
    result = md_output.save(article)

    check("MarkdownOutput.save() returns SaveResult", isinstance(result, SR), True)
    check("MarkdownOutput result.success = True", result.success, True)
    check("MarkdownOutput result.output_type = file", result.output_type, "file")
    check("MarkdownOutput result.is_wordpress = False", result.is_wordpress, False)
    check("MarkdownOutput result.edit_url はファイルパス", result.edit_url is not None and result.edit_url.endswith(".md"), True)
    check("MarkdownOutput 実ファイルが存在する", Path(result.edit_url).exists(), True)

# ─── シナリオ 3: WordPressOutput.save() が SaveResult を返す（HTTP モック）───

print("\n=== Scenario 3: WordPressOutput returns SaveResult (mocked HTTP) ===")

from outputs.wordpress_output import WordPressOutput

mock_response_data = {
    "id": 10340,
    "slug": "ps6-announced-20260630",
    "status": "draft",
    "title": {"rendered": "PS6が正式発表"},
    "link": "https://nozo3-kao6.tokyo/ps6-announced-20260630/",
}

mock_response = MagicMock()
mock_response.status_code = 201
mock_response.json.return_value = mock_response_data

with patch("requests.post", return_value=mock_response):
    wp_output = WordPressOutput(
        site_url="https://nozo3-kao6.tokyo",
        username="testuser",
        app_password="xxxx xxxx xxxx xxxx xxxx xxxx",
    )
    article = make_article()
    result = wp_output.save(article)

check("WordPressOutput.save() returns SaveResult", isinstance(result, SR), True)
check("WP result.success = True", result.success, True)
check("WP result.output_type = wordpress", result.output_type, "wordpress")
check("WP result.is_wordpress = True", result.is_wordpress, True)
check("WP result.post_id = 10340 (API から直接取得)", result.post_id, 10340)
check("WP result.slug = ps6-announced-20260630", result.slug, "ps6-announced-20260630")
check("WP result.status = draft", result.status, "draft")
check("WP result.permalink = https://nozo3-kao6.tokyo/ps6-announced-20260630/", result.permalink, "https://nozo3-kao6.tokyo/ps6-announced-20260630/")
check("WP result.edit_url に post_id が含まれる", "10340" in (result.edit_url or ""), True)
check("WP result.raw_response に id が含まれる", result.raw_response is not None and result.raw_response.get("id") == 10340, True)

# ─── シナリオ 4: WordPressOutput.save() 失敗時 ───

print("\n=== Scenario 4: WordPressOutput.save() failure ===")

mock_error_response = MagicMock()
mock_error_response.status_code = 401
mock_error_response.text = "Unauthorized"

error_raised = False
with patch("requests.post", return_value=mock_error_response):
    wp_output2 = WordPressOutput(
        site_url="https://nozo3-kao6.tokyo",
        username="bad_user",
        app_password="wrong_pass",
    )
    try:
        wp_output2.save(make_article())
    except RuntimeError as e:
        error_raised = True
        check("RuntimeError に HTTP 401 が含まれる", "401" in str(e), True)

check("RuntimeError が発生した", error_raised, True)

# ─── シナリオ 5: OutputManager.save_all() が list[SaveResult] を返す ───

print("\n=== Scenario 5: OutputManager.save_all() returns list[SaveResult] ===")

from outputs.manager import OutputManager

with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp)
    md = MarkdownOutput(output_dir=tmp_path)
    wp = WordPressOutput(site_url="", username="", app_password="")  # is_available=False

    mgr_no_wp = OutputManager([md, wp])
    article = make_article()
    results_list = mgr_no_wp.save_all(article)

    check("save_all() returns list", isinstance(results_list, list), True)
    check("save_all() の要素が SaveResult", all(isinstance(r, SR) for r in results_list), True)
    check("WP 未設定時は1件（Markdown のみ）", len(results_list), 1)
    check("Markdown 結果の output_type = file", results_list[0].output_type, "file")

# WP 有効 + 成功
with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp)
    md2 = MarkdownOutput(output_dir=tmp_path)
    wp2 = WordPressOutput(
        site_url="https://nozo3-kao6.tokyo",
        username="user",
        app_password="pass",
    )
    mgr_with_wp = OutputManager([md2, wp2])
    article = make_article()

    with patch("requests.post", return_value=mock_response):
        results_list2 = mgr_with_wp.save_all(article)

    check("WP 有効時は2件（Markdown + WP）", len(results_list2), 2)
    wp_r = next((r for r in results_list2 if r.is_wordpress), None)
    md_r = next((r for r in results_list2 if not r.is_wordpress), None)
    check("WP 結果が含まれる", wp_r is not None, True)
    check("Markdown 結果が含まれる", md_r is not None, True)
    check("WP 結果の post_id = 10340", wp_r.post_id if wp_r else None, 10340)

# WP 有効 + 失敗
with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp)
    md3 = MarkdownOutput(output_dir=tmp_path)
    wp3 = WordPressOutput(site_url="https://nozo3-kao6.tokyo", username="u", app_password="p")
    mgr_wp_fail = OutputManager([md3, wp3])
    article = make_article()

    with patch("requests.post", return_value=mock_error_response):
        results_list3 = mgr_wp_fail.save_all(article)

    wp_fail_r = next((r for r in results_list3 if r.is_wordpress), None)
    check("WP 失敗時も SaveResult として返る", wp_fail_r is not None, True)
    check("WP 失敗の success = False", wp_fail_r.success if wp_fail_r else True, False)
    check("WP 失敗の error_message に 401 が含まれる", "401" in (wp_fail_r.error_message or ""), True)

# ─── シナリオ 6: LogManager が post_id を直接受け取れる ───

print("\n=== Scenario 6: LogManager accepts post_id directly ===")

from logger.log_manager import LogManager

with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp)
    log_mgr = LogManager(log_dir=tmp_path)
    article = make_article()

    log_mgr.log_article(
        article=article,
        edit_url="https://nozo3-kao6.tokyo/wp-admin/post.php?post=10340&action=edit",
        result="success",
        post_id=10340,
    )
    date_str = __import__("datetime").datetime.now().strftime("%Y%m%d")
    log_file = tmp_path / "articles" / f"{date_str}_articles.jsonl"
    check("ArticleLog ファイルが作成された", log_file.exists(), True)

    with log_file.open("r", encoding="utf-8") as f:
        saved = json.loads(f.readline().strip())

    check("post_id = 10340 が直接記録された（API取得値）", saved["post_id"], 10340)

# ─── シナリオ 7: LogManager 後方互換（post_id 未指定 → edit_url から抽出）───

print("\n=== Scenario 7: LogManager backward compat (regex fallback) ===")

with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp)
    log_mgr2 = LogManager(log_dir=tmp_path)
    article = make_article()

    log_mgr2.log_article(
        article=article,
        edit_url="https://nozo3-kao6.tokyo/wp-admin/post.php?post=99999&action=edit",
        result="success",
        # post_id は渡さない → edit_url から正規表現で抽出
    )
    date_str = __import__("datetime").datetime.now().strftime("%Y%m%d")
    log_file2 = tmp_path / "articles" / f"{date_str}_articles.jsonl"

    with log_file2.open("r", encoding="utf-8") as f:
        saved2 = json.loads(f.readline().strip())

    check("post_id = 99999 が edit_url から抽出された（後方互換）", saved2["post_id"], 99999)

# ─── シナリオ 8: post_id が正規表現ではなく API レスポンスから取得される ───

print("\n=== Scenario 8: post_id comes from API response directly ===")

# edit_url の post番号と API レスポンスの id が異なる仮定のケースを作り、
# API レスポンス側の値が優先されることを確認する
mock_response_diff_id = MagicMock()
mock_response_diff_id.status_code = 201
mock_response_diff_id.json.return_value = {
    "id": 77777,           # API が返した本当の post_id
    "slug": "test-slug",
    "status": "draft",
    "title": {"rendered": "テスト"},
    "link": "https://nozo3-kao6.tokyo/test-slug/",
}

with patch("requests.post", return_value=mock_response_diff_id):
    wp_test = WordPressOutput(
        site_url="https://nozo3-kao6.tokyo",
        username="user",
        app_password="pass",
    )
    r = wp_test.save(make_article())

check("post_id は API レスポンスの id を使用", r.post_id, 77777)
check("edit_url に API の post_id が埋め込まれる", "77777" in (r.edit_url or ""), True)

# ─── 結果サマリー ───

print("\n" + "=" * 55)
passed = sum(1 for s, _ in results if s == "PASS")
failed = sum(1 for s, _ in results if s == "FAIL")
print(f"Result: {passed}/{len(results)} PASS  ({failed} FAIL)")
print("=" * 55)

if failed > 0:
    print("\nFailed tests:")
    for status, label in results:
        if status == "FAIL":
            print(f"  NG {label}")
    sys.exit(1)
else:
    print("All PASS")
    sys.exit(0)
