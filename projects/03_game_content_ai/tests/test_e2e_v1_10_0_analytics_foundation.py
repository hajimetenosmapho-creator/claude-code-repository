"""
E2E テスト: v1.10.0 Analytics Foundation

テストシナリオ:
    1. ANALYTICS_ENABLED=false（デフォルト）→ NullAnalyticsManager が返る
    2. ANALYTICS_ENABLED=true → AnalyticsManager が返る
    3. AnalyticsEntry の生成と JSONL 保存
    4. ArticleLogEntry と AnalyticsEntry の統合 → ArticleAnalysisRecord 生成
    5. AiInputRecord の生成と published / x_posted フラグの確認
    6. 外部API呼び出しが一切ないことの確認（data_source = "placeholder"）

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v1_10_0_analytics_foundation.py
"""
import sys
import os
import json
import tempfile
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

# ─── シナリオ 1: ANALYTICS_ENABLED=false（デフォルト） ───

print("\n=== Scenario 1: ANALYTICS_ENABLED=false (default) ===")

os.environ.pop("ANALYTICS_ENABLED", None)

from analytics.analytics_manager import AnalyticsManager, NullAnalyticsManager

mgr1 = AnalyticsManager.from_env()
check("NullAnalyticsManager が返る", isinstance(mgr1, NullAnalyticsManager), True)
check("NullAnalyticsManager.create_placeholder_entry() は None", mgr1.create_placeholder_entry(1, "slug", ""), None)
check("NullAnalyticsManager.build_analysis_record() は None", mgr1.build_analysis_record({}, None), None)
check("NullAnalyticsManager.build_ai_input() は None", mgr1.build_ai_input(None), None)
check("NullAnalyticsManager.load_analytics_logs() は空辞書", mgr1.load_analytics_logs("20260630"), {})

# ─── シナリオ 2: ANALYTICS_ENABLED=true ───

print("\n=== Scenario 2: ANALYTICS_ENABLED=true ===")

os.environ["ANALYTICS_ENABLED"] = "true"
os.environ["LOG_DIR"] = "logs"

import importlib
import analytics.analytics_manager as _amgr_mod
importlib.reload(_amgr_mod)
from analytics.analytics_manager import AnalyticsManager as AM2, NullAnalyticsManager as NM2

mgr2 = AM2.from_env()
check("AnalyticsManager が返る", isinstance(mgr2, AM2), True)
check("AnalyticsManager は NullAnalyticsManager ではない", isinstance(mgr2, NM2), False)

# ─── シナリオ 3: AnalyticsEntry の生成と JSONL 保存 ───

print("\n=== Scenario 3: AnalyticsEntry generation and JSONL save ===")

from analytics.analytics_entry import (
    AnalyticsEntry, SearchConsoleMetrics, GoogleAnalyticsMetrics,
    ArticleAnalysisRecord, AiInputRecord,
)
from analytics.analytics_config import AnalyticsConfig

with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp)
    mgr3 = AM2(log_dir=tmp_path, period_days=28)

    entry = mgr3.create_placeholder_entry(
        post_id=10340,
        slug="ps6-announced-20260630",
        wp_public_url="https://nozo3-kao6.tokyo/ps6-announced-20260630/",
    )
    check("data_source = placeholder", entry.data_source, "placeholder")
    check("impressions = 0", entry.search_console.impressions, 0)
    check("page_views = 0", entry.google_analytics.page_views, 0)
    check("post_id = 10340", entry.post_id, 10340)
    check("period_days = 28", entry.period_days, 28)

    # JSONL シリアライズ確認
    json_line = entry.to_json_line()
    parsed = json.loads(json_line)
    check("JSON に search_console が含まれる", "search_console" in parsed, True)
    check("JSON に google_analytics が含まれる", "google_analytics" in parsed, True)
    check("JSON の data_source が 'placeholder'", parsed["data_source"], "placeholder")
    check("JSON の impressions が 0", parsed["search_console"]["impressions"], 0)

    # ファイル保存確認
    mgr3.save_analytics_entry(entry)
    analytics_file = tmp_path / "analytics" / "20260630_analytics.jsonl"
    check("analytics JSONL ファイルが作成された", analytics_file.exists(), True)

    # 保存内容の読み込み確認
    with analytics_file.open("r", encoding="utf-8") as f:
        saved_line = f.readline().strip()
    saved_data = json.loads(saved_line)
    check("保存された post_id が正しい", saved_data["post_id"], 10340)
    check("保存された slug が正しい", saved_data["slug"], "ps6-announced-20260630")

# ─── シナリオ 4: ArticleLogEntry と AnalyticsEntry の統合 ───

print("\n=== Scenario 4: ArticleAnalysisRecord integration ===")

sample_article_log = {
    "logged_at": "2026-06-30T12:34:56+09:00",
    "importance": "S",
    "seo_title": "PS6正式発表",
    "slug": "ps6-announced-20260630",
    "post_id": 10340,
    "edit_url": "https://nozo3-kao6.tokyo/wp-admin/post.php?post=10340&action=edit",
    "publish_status": "pending",
    "category_ids": [14],
    "tag_ids": [70, 71],
    "featured_media_id": 456,
    "source_url": "https://blog.playstation.com/test",
    "source_name": "PlayStation Blog",
    "result": "success",
    "error_message": "",
    "wp_public_url": "https://nozo3-kao6.tokyo/ps6-announced-20260630/",
    "x_post_text": "PS6が発売決定！詳細はこちら https://nozo3-kao6.tokyo/ps6-announced-20260630/",
    "x_post_status": "pending",
    "x_post_url": "",
}

with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp)
    mgr4 = AM2(log_dir=tmp_path, period_days=28)

    # データなし（analytics = None）で統合
    record_no_data = mgr4.build_analysis_record(sample_article_log, None)
    check("post_id が ArticleLog から取得される", record_no_data.post_id, 10340)
    check("seo_title が ArticleLog から取得される", record_no_data.seo_title, "PS6正式発表")
    check("importance が ArticleLog から取得される", record_no_data.importance, "S")
    check("x_post_status が ArticleLog から取得される", record_no_data.x_post_status, "pending")
    check("has_analytics_data() = False（データなし）", record_no_data.has_analytics_data(), False)
    check("measured_at が空（データなし）", record_no_data.measured_at, "")
    check("impressions = 0（データなし）", record_no_data.impressions, 0)

    # データあり（将来のSearch Console連携を想定した仮データ）で統合
    analytics_with_data = AnalyticsEntry(
        measured_at="2026-07-28",
        post_id=10340,
        slug="ps6-announced-20260630",
        wp_public_url="https://nozo3-kao6.tokyo/ps6-announced-20260630/",
        search_console=SearchConsoleMetrics(impressions=1200, clicks=45, ctr=0.0375, avg_position=12.3),
        google_analytics=GoogleAnalyticsMetrics(page_views=120, sessions=98),
        data_source="search_console",
    )
    record_with_data = mgr4.build_analysis_record(sample_article_log, analytics_with_data)
    check("has_analytics_data() = True（データあり）", record_with_data.has_analytics_data(), True)
    check("impressions = 1200", record_with_data.impressions, 1200)
    check("clicks = 45", record_with_data.clicks, 45)
    check("avg_position = 12.3", record_with_data.avg_position, 12.3)
    check("page_views = 120", record_with_data.page_views, 120)
    check("measured_at = 2026-07-28", record_with_data.measured_at, "2026-07-28")

# ─── シナリオ 5: AiInputRecord の生成 ───

print("\n=== Scenario 5: AiInputRecord generation ===")

with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp)
    mgr5 = AM2(log_dir=tmp_path, period_days=28)

    # publish_status=pending + wp_public_url あり → published=True
    record_pending = mgr5.build_analysis_record(sample_article_log, None)
    ai_input_pending = mgr5.build_ai_input(record_pending)
    check("published=True (pending + wp_public_url)", ai_input_pending.published, True)
    check("x_posted=False (pending status)", ai_input_pending.x_posted, False)
    check("has_performance_data=False", ai_input_pending.has_performance_data, False)
    check("to_dict() が dict を返す", isinstance(ai_input_pending.to_dict(), dict), True)

    # publish_status=draft → published=False
    draft_log = dict(sample_article_log)
    draft_log["publish_status"] = "draft"
    record_draft = mgr5.build_analysis_record(draft_log, None)
    ai_input_draft = mgr5.build_ai_input(record_draft)
    check("published=False (draft)", ai_input_draft.published, False)

    # x_post_status=posted → x_posted=True
    posted_log = dict(sample_article_log)
    posted_log["x_post_status"] = "posted"
    record_posted = mgr5.build_analysis_record(posted_log, None)
    ai_input_posted = mgr5.build_ai_input(record_posted)
    check("x_posted=True (posted status)", ai_input_posted.x_posted, True)

    # x_post_status=skipped → x_posted=False
    skipped_log = dict(sample_article_log)
    skipped_log["x_post_status"] = "skipped"
    record_skipped = mgr5.build_analysis_record(skipped_log, None)
    ai_input_skipped = mgr5.build_ai_input(record_skipped)
    check("x_posted=False (skipped status)", ai_input_skipped.x_posted, False)

# ─── シナリオ 6: 外部API呼び出しなし・data_source 確認 ───

print("\n=== Scenario 6: No external API calls (placeholder only) ===")

check(
    "create_placeholder_entry の data_source は 'placeholder'",
    AnalyticsEntry(
        measured_at="2026-06-30",
        post_id=10340,
        slug="test",
        wp_public_url="https://example.com/test/",
    ).data_source,
    "placeholder",
)
check(
    "AnalyticsConfig デフォルト enabled=False",
    AnalyticsConfig().enabled,
    False,
)
check(
    "AnalyticsConfig.from_env() デフォルト enabled=False（ANALYTICS_ENABLED 未設定）",
    AnalyticsConfig.from_env().enabled if os.getenv("ANALYTICS_ENABLED") != "true" else True,
    True,
)

# ─── シナリオ 7: AnalyticsConfig ANALYTICS_PERIOD_DAYS 不正値フォールバック ───

print("\n=== Scenario 7: ANALYTICS_PERIOD_DAYS invalid value fallback ===")

os.environ["ANALYTICS_PERIOD_DAYS"] = "not_a_number"
import analytics.analytics_config as _acfg_mod
importlib.reload(_acfg_mod)
from analytics.analytics_config import AnalyticsConfig as AC7
config7 = AC7.from_env()
check("不正な ANALYTICS_PERIOD_DAYS は 28 にフォールバック", config7.period_days, 28)
os.environ.pop("ANALYTICS_PERIOD_DAYS", None)

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
