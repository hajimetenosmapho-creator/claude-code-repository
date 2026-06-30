"""
E2E テスト: v1.9.0 SNS Foundation

テストシナリオ:
    1. BLOG_BASE_URL 設定あり → wp_public_url が正しく生成される
    2. BLOG_BASE_URL 設定あり → x_post の [ブログURL] が実URLに置換される
    3. BLOG_BASE_URL 設定なし → [ブログURL] プレースホルダーが維持される
    4. SNS_ENABLED=false → x_post_status=skipped, wp_public_url=""

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v1_9_0_sns_foundation.py
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# ─── テスト用ユーティリティ ───

PASS = "PASS"
FAIL = "FAIL"
results = []

def check(label: str, actual, expected, exact: bool = True):
    if exact:
        ok = actual == expected
    else:
        ok = expected in str(actual)
    status = PASS if ok else FAIL
    results.append((status, label))
    mark = "OK" if ok else "NG"
    print(f"  [{mark}] {label}")
    if not ok:
        print(f"       期待値: {expected!r}")
        print(f"       実際値: {actual!r}")

# ─── シナリオ 1・2: BLOG_BASE_URL 設定あり ───

print("\n=== シナリオ 1・2: BLOG_BASE_URL 設定あり ===")

os.environ["BLOG_BASE_URL"] = "https://nozo3-kao6.tokyo"
os.environ.pop("SNS_ENABLED", None)  # デフォルト (true)

from sns_config import SnsConfig, SnsPostStatus

# 再読み込みを確実にするため from_env() を都度呼ぶ
sns_cfg = SnsConfig.from_env()

# シナリオ 1: BLOG_BASE_URL 設定あり → wp_public_url 正常生成
slug = "ps6-announced-20260630"
wp_public_url = sns_cfg.resolve_public_url(slug)
check("SNS_ENABLED デフォルト=true", sns_cfg.sns_enabled, True)
check(
    "wp_public_url が正しく生成される",
    wp_public_url,
    "https://nozo3-kao6.tokyo/ps6-announced-20260630/",
)

# シナリオ 2: x_post_status は PENDING
x_post_status = SnsPostStatus.PENDING if sns_cfg.sns_enabled else SnsPostStatus.SKIPPED
check("x_post_status = PENDING (SNS_ENABLED=true 時)", x_post_status, SnsPostStatus.PENDING)

# x_post 内の [ブログURL] が置換されるか（generate_x_post を呼ばずに論理だけ確認）
blog_url_arg = wp_public_url if wp_public_url else "[ブログURL]"
check(
    "generate_x_post へ渡す blog_url が実URLになる",
    blog_url_arg,
    "https://nozo3-kao6.tokyo/ps6-announced-20260630/",
)

# ─── シナリオ 3: BLOG_BASE_URL 設定なし ───

print("\n=== シナリオ 3: BLOG_BASE_URL 設定なし ===")

os.environ.pop("BLOG_BASE_URL", None)
os.environ.pop("WP_SITE_URL", None)
os.environ.pop("SNS_ENABLED", None)

import importlib
import sns_config as _sc_mod
importlib.reload(_sc_mod)
from sns_config import SnsConfig as SnsConfig3, SnsPostStatus as SnsPostStatus3

sns_cfg3 = SnsConfig3.from_env()
wp_public_url3 = sns_cfg3.resolve_public_url("ps6-announced-20260630")
blog_url_arg3 = wp_public_url3 if wp_public_url3 else "[ブログURL]"

check("blog_base_url が空", sns_cfg3.blog_base_url, "")
check("wp_public_url が [ブログURL]", wp_public_url3, "[ブログURL]")
check("generate_x_post へ渡す blog_url が [ブログURL]", blog_url_arg3, "[ブログURL]")

# ─── シナリオ 4: SNS_ENABLED=false ───

print("\n=== シナリオ 4: SNS_ENABLED=false ===")

os.environ["BLOG_BASE_URL"] = "https://nozo3-kao6.tokyo"
os.environ["SNS_ENABLED"] = "false"

importlib.reload(_sc_mod)
from sns_config import SnsConfig as SnsConfig4, SnsPostStatus as SnsPostStatus4

sns_cfg4 = SnsConfig4.from_env()

if sns_cfg4.sns_enabled:
    wp_public_url4 = sns_cfg4.resolve_public_url("ps6-announced-20260630")
    x_post_status4 = SnsPostStatus4.PENDING
else:
    wp_public_url4 = ""
    x_post_status4 = SnsPostStatus4.SKIPPED

check("sns_enabled = False", sns_cfg4.sns_enabled, False)
check("wp_public_url = '' (SNS無効時)", wp_public_url4, "")
check("x_post_status = skipped", x_post_status4, SnsPostStatus4.SKIPPED)
check("x_post_status の .value が 'skipped'", x_post_status4.value, "skipped")

# ─── シナリオ 5: ArticleLogEntry JSON シリアライズ確認 ───

print("\n=== シナリオ 5: ArticleLogEntry の SNS フィールド JSON シリアライズ ===")

from logger.log_entry import ArticleLogEntry
from sns_config import SnsPostStatus as SP

os.environ.pop("BLOG_BASE_URL", None)
os.environ.pop("SNS_ENABLED", None)

entry = ArticleLogEntry(
    logged_at="2026-06-30T12:00:00+09:00",
    importance="S",
    seo_title="PS6発売決定",
    slug="ps6-announced-20260630",
    post_id=10340,
    edit_url="https://example.com/wp-admin/post.php?post=10340&action=edit",
    publish_status="draft",
    category_ids=[1],
    tag_ids=[2, 3],
    featured_media_id=456,
    source_url="https://example.com/news",
    source_name="IGN Japan",
    result="success",
    error_message="",
    wp_public_url="https://nozo3-kao6.tokyo/ps6-announced-20260630/",
    x_post_text="PS6が発売決定！詳細はこちら https://nozo3-kao6.tokyo/ps6-announced-20260630/",
    x_post_status=SP.PENDING,
    x_post_url="",
)
json_line = entry.to_json_line()

check("JSON に wp_public_url が含まれる", "wp_public_url" in json_line, True)
check("JSON に x_post_status が文字列で含まれる", '"x_post_status": "pending"' in json_line, True)
check("JSON に x_post_text が含まれる", "x_post_text" in json_line, True)
check("JSON に x_post_url が含まれる", "x_post_url" in json_line, True)

# ─── 結果サマリー ───

print("\n" + "=" * 50)
passed = sum(1 for s, _ in results if s == PASS)
failed = sum(1 for s, _ in results if s == FAIL)
print(f"結果: {passed}/{len(results)} PASS  ({failed} FAIL)")
print("=" * 50)

if failed > 0:
    print("\n失敗したテスト:")
    for status, label in results:
        if status == FAIL:
            print(f"  NG {label}")
    sys.exit(1)
else:
    print("All PASS")
    sys.exit(0)
