"""
E2E テスト: v1.13.0 Google Analytics Foundation

テストシナリオ:
    1. GoogleAnalyticsConfig.from_env() の動作確認
    2. GOOGLE_ANALYTICS_ENABLED=false → NullGoogleAnalyticsClient
    3. NullGoogleAnalyticsClient が安全に動作する
    4. page_url → pagePath 抽出ロジックの確認
    5. GoogleAnalyticsFetcher が GoogleAnalyticsMetrics を返す（モック）
    6. API 失敗時にゼロ値 GoogleAnalyticsMetrics を返す
    7. GoogleAnalyticsMetrics の重複定義がない（Single Source of Truth）
    8. ArticleAnalysisRecord に sessions / bounce_rate / avg_engagement_time が追加されている
    9. AiInputRecord に sessions / bounce_rate / avg_engagement_time が追加されている
    10. AnalyticsManager が GA4 指標を全フィールドマッピングする
    11. 投稿直後に GA4 API を呼ばない（main.py の確認）
    12. Search Console Foundation が壊れていない（v1.12.0 回帰）
    13. v1.11.0 / v1.10.0 互換性（インポートテスト）

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v1_13_0_google_analytics_foundation.py
"""
import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

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

# ─── シナリオ 1: GoogleAnalyticsConfig.from_env() ───

print("\n=== Scenario 1: GoogleAnalyticsConfig.from_env() ===")

from analytics.google_analytics_config import GoogleAnalyticsConfig

# デフォルト（全環境変数未設定）
for key in ["GOOGLE_ANALYTICS_ENABLED", "GA4_PROPERTY_ID", "GA4_APPLICATION_CREDENTIALS"]:
    os.environ.pop(key, None)

config_default = GoogleAnalyticsConfig.from_env()
check("デフォルト: enabled=False", config_default.enabled, False)
check("デフォルト: property_id=None", config_default.property_id, None)
check("デフォルト: credentials_path=None", config_default.credentials_path, None)
check("デフォルト: period_days=28", config_default.period_days, 28)
check("デフォルト: timeout_seconds=30", config_default.timeout_seconds, 30)
check("デフォルト: is_ready()=False", config_default.is_ready(), False)

# 有効化（設定あり）
os.environ["GOOGLE_ANALYTICS_ENABLED"] = "true"
os.environ["GA4_PROPERTY_ID"] = "123456789"
os.environ["GA4_APPLICATION_CREDENTIALS"] = "credentials/google_analytics_sa.json"

config_enabled = GoogleAnalyticsConfig.from_env()
check("有効時: enabled=True", config_enabled.enabled, True)
check("有効時: property_id 設定済み", config_enabled.property_id, "123456789")
check("有効時: credentials_path 設定済み", config_enabled.credentials_path, "credentials/google_analytics_sa.json")
check("有効時: is_ready()=True", config_enabled.is_ready(), True)

# enabled=true でも property_id なし → is_ready()=False
os.environ.pop("GA4_PROPERTY_ID", None)
config_no_prop = GoogleAnalyticsConfig.from_env()
check("property_id 不足: is_ready()=False", config_no_prop.is_ready(), False)

# GA4_APPLICATION_CREDENTIALS は GOOGLE_APPLICATION_CREDENTIALS と別変数であることを確認
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "credentials/search_console_sa.json"
os.environ["GA4_PROPERTY_ID"] = "123456789"
config_sep = GoogleAnalyticsConfig.from_env()
check("GA4認証情報がSCと独立 (GA4_APPLICATION_CREDENTIALS使用)", config_sep.credentials_path, "credentials/google_analytics_sa.json")

for key in ["GOOGLE_ANALYTICS_ENABLED", "GA4_PROPERTY_ID", "GA4_APPLICATION_CREDENTIALS", "GOOGLE_APPLICATION_CREDENTIALS"]:
    os.environ.pop(key, None)

# ─── シナリオ 2: GOOGLE_ANALYTICS_ENABLED=false → NullGoogleAnalyticsClient ───

print("\n=== Scenario 2: GOOGLE_ANALYTICS_ENABLED=false → NullGoogleAnalyticsClient ===")

from analytics.google_analytics_client import GoogleAnalyticsClient, NullGoogleAnalyticsClient

os.environ.pop("GOOGLE_ANALYTICS_ENABLED", None)
client_from_env = GoogleAnalyticsClient.from_env()

check("from_env() が NullGoogleAnalyticsClient を返す", isinstance(client_from_env, NullGoogleAnalyticsClient), True)
check("NullGoogleAnalyticsClient.is_available()=False", client_from_env.is_available(), False)

# credentials 不足でも NullGoogleAnalyticsClient
os.environ["GOOGLE_ANALYTICS_ENABLED"] = "true"
os.environ.pop("GA4_PROPERTY_ID", None)
os.environ.pop("GA4_APPLICATION_CREDENTIALS", None)
client_missing = GoogleAnalyticsClient.from_env()
check("credentials 不足 → NullGoogleAnalyticsClient", isinstance(client_missing, NullGoogleAnalyticsClient), True)

os.environ.pop("GOOGLE_ANALYTICS_ENABLED", None)

# ─── シナリオ 3: NullGoogleAnalyticsClient が安全に動作する ───

print("\n=== Scenario 3: NullGoogleAnalyticsClient safe operation ===")

null_client = NullGoogleAnalyticsClient()
check("NullGoogleAnalyticsClient.is_available()=False", null_client.is_available(), False)

raw = null_client.fetch_raw("https://nozo3-kao6.tokyo/ps6/")
check("NullGoogleAnalyticsClient.fetch_raw() = {}", raw, {})

raw_with_period = null_client.fetch_raw("https://nozo3-kao6.tokyo/ps6/", period_days=14)
check("NullGoogleAnalyticsClient.fetch_raw(period_days=14) = {}", raw_with_period, {})

# ─── シナリオ 4: page_url → pagePath 抽出ロジック ───

print("\n=== Scenario 4: page_url → pagePath extraction ===")

from urllib.parse import urlparse

test_cases = [
    ("https://nozo3-kao6.tokyo/ps6-announced-20260630/", "/ps6-announced-20260630/"),
    ("https://example.com/path/to/article/", "/path/to/article/"),
    ("https://example.com/", "/"),
    ("https://nozo3-kao6.tokyo/game-news/ps5-update/", "/game-news/ps5-update/"),
]

for url, expected_path in test_cases:
    path = urlparse(url).path or "/"
    check(f"pagePath: {url[:45]}...", path, expected_path)

# ─── シナリオ 5: GoogleAnalyticsFetcher が GoogleAnalyticsMetrics を返す（モック）───

print("\n=== Scenario 5: GoogleAnalyticsFetcher returns GoogleAnalyticsMetrics (mocked) ===")

from analytics.google_analytics_fetcher import GoogleAnalyticsFetcher
from analytics.analytics_entry import GoogleAnalyticsMetrics

mock_ga4_response = {
    "rows": [
        {
            "screenPageViews": 2500,
            "sessions": 2000,
            "bounceRate": 0.35,
            "averageEngagementTime": 62.5,
        }
    ]
}

mock_client = MagicMock()
mock_client.is_available.return_value = True
mock_client.fetch_raw.return_value = mock_ga4_response

fetcher = GoogleAnalyticsFetcher(client=mock_client)
check("fetcher.is_available()=True（モック）", fetcher.is_available(), True)

metrics = fetcher.fetch("https://nozo3-kao6.tokyo/ps6-announced-20260630/", period_days=28)

check("metrics は GoogleAnalyticsMetrics インスタンス", isinstance(metrics, GoogleAnalyticsMetrics), True)
check("page_views=2500", metrics.page_views, 2500)
check("sessions=2000", metrics.sessions, 2000)
check("bounce_rate=0.35", metrics.bounce_rate, 0.35)
check("avg_time_on_page=62.5", metrics.avg_time_on_page, 62.5)

# ─── シナリオ 6: API 失敗時にゼロ値を返す ───

print("\n=== Scenario 6: API failure returns zero GoogleAnalyticsMetrics ===")

mock_fail = MagicMock()
mock_fail.is_available.return_value = True
mock_fail.fetch_raw.side_effect = Exception("GA4 Network error")

fetcher_fail = GoogleAnalyticsFetcher(client=mock_fail)
metrics_fail = fetcher_fail.fetch("https://nozo3-kao6.tokyo/test/", period_days=28)

check("例外時: GoogleAnalyticsMetrics インスタンス", isinstance(metrics_fail, GoogleAnalyticsMetrics), True)
check("例外時: page_views=0", metrics_fail.page_views, 0)
check("例外時: sessions=0", metrics_fail.sessions, 0)
check("例外時: bounce_rate=0.0", metrics_fail.bounce_rate, 0.0)
check("例外時: avg_time_on_page=0.0", metrics_fail.avg_time_on_page, 0.0)

# rows が空の場合
mock_empty = MagicMock()
mock_empty.is_available.return_value = True
mock_empty.fetch_raw.return_value = {"rows": []}
fetcher_empty = GoogleAnalyticsFetcher(client=mock_empty)
metrics_empty = fetcher_empty.fetch("https://nozo3-kao6.tokyo/old-article/")
check("rows 空: page_views=0", metrics_empty.page_views, 0)
check("rows 空: sessions=0", metrics_empty.sessions, 0)

# NullGoogleAnalyticsClient → ゼロ値
fetcher_null = GoogleAnalyticsFetcher(client=NullGoogleAnalyticsClient())
metrics_null = fetcher_null.fetch("https://nozo3-kao6.tokyo/test/")
check("NullClient: page_views=0", metrics_null.page_views, 0)
check("NullClient: is_available()=False", fetcher_null.is_available(), False)

# ─── シナリオ 7: GoogleAnalyticsMetrics の重複定義がない（Single Source of Truth）───

print("\n=== Scenario 7: GoogleAnalyticsMetrics Single Source of Truth ===")

from analytics.analytics_entry import GoogleAnalyticsMetrics as GAM_from_entry
from analytics import GoogleAnalyticsMetrics as GAM_from_init

check("analytics_entry と analytics.__init__ が同一クラス", GAM_from_entry is GAM_from_init, True)

fetcher_check = GoogleAnalyticsFetcher(client=NullGoogleAnalyticsClient())
zero_metrics = fetcher_check.fetch("https://example.com/")
check("Fetcher が返す型も同一クラス（重複定義なし）", type(zero_metrics) is GAM_from_entry, True)

# ─── シナリオ 8: ArticleAnalysisRecord の GA4 フィールド拡張 ───

print("\n=== Scenario 8: ArticleAnalysisRecord GA4 field expansion ===")

from analytics.analytics_entry import ArticleAnalysisRecord
import dataclasses

field_names = {f.name for f in dataclasses.fields(ArticleAnalysisRecord)}
check("ArticleAnalysisRecord に sessions フィールドあり", "sessions" in field_names, True)
check("ArticleAnalysisRecord に bounce_rate フィールドあり", "bounce_rate" in field_names, True)
check("ArticleAnalysisRecord に avg_engagement_time フィールドあり", "avg_engagement_time" in field_names, True)

# デフォルト値の確認（既存互換性）
record = ArticleAnalysisRecord(
    post_id=10340, slug="test", seo_title="テスト", importance="S",
    publish_status="draft", logged_at="2026-06-30T00:00:00+09:00",
    source_name="テスト", wp_public_url="", x_post_status="pending",
    measured_at="2026-06-30", period_days=28,
    impressions=0, clicks=0, ctr=0.0, avg_position=0.0, page_views=0,
)
check("ArticleAnalysisRecord.sessions デフォルト=0", record.sessions, 0)
check("ArticleAnalysisRecord.bounce_rate デフォルト=0.0", record.bounce_rate, 0.0)
check("ArticleAnalysisRecord.avg_engagement_time デフォルト=0.0", record.avg_engagement_time, 0.0)

# has_analytics_data() が sessions も考慮するか
record_with_sessions = ArticleAnalysisRecord(
    post_id=1, slug="s", seo_title="t", importance="A",
    publish_status="draft", logged_at="2026-06-30T00:00:00", source_name="src",
    wp_public_url="", x_post_status="pending",
    measured_at="2026-06-30", period_days=28,
    impressions=0, clicks=0, ctr=0.0, avg_position=0.0, page_views=0,
    sessions=100,
)
check("has_analytics_data() が sessions=100 を検出", record_with_sessions.has_analytics_data(), True)

# ─── シナリオ 9: AiInputRecord の GA4 フィールド拡張 ───

print("\n=== Scenario 9: AiInputRecord GA4 field expansion ===")

from analytics.analytics_entry import AiInputRecord

ai_field_names = {f.name for f in dataclasses.fields(AiInputRecord)}
check("AiInputRecord に sessions フィールドあり", "sessions" in ai_field_names, True)
check("AiInputRecord に bounce_rate フィールドあり", "bounce_rate" in ai_field_names, True)
check("AiInputRecord に avg_engagement_time フィールドあり", "avg_engagement_time" in ai_field_names, True)

ai_record = AiInputRecord(
    post_id=1, slug="test", seo_title="テスト", importance="S",
    source_name="PS Blog", published=True, x_posted=False,
    has_performance_data=True, impressions=100, clicks=5, ctr=0.05,
    avg_position=3.2, page_views=500,
)
check("AiInputRecord.sessions デフォルト=0", ai_record.sessions, 0)
check("AiInputRecord.bounce_rate デフォルト=0.0", ai_record.bounce_rate, 0.0)
check("AiInputRecord.avg_engagement_time デフォルト=0.0", ai_record.avg_engagement_time, 0.0)

# ─── シナリオ 10: AnalyticsManager が GA4 指標を全フィールドマッピングする ───

print("\n=== Scenario 10: AnalyticsManager maps all GA4 fields ===")

from analytics.analytics_entry import (
    AnalyticsEntry, SearchConsoleMetrics,
)
from analytics import AnalyticsManager

with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp)
    mgr = AnalyticsManager(log_dir=tmp_path)

    ga_metrics = GoogleAnalyticsMetrics(
        page_views=2500,
        sessions=2000,
        bounce_rate=0.35,
        avg_time_on_page=62.5,
    )
    entry = AnalyticsEntry(
        measured_at="2026-06-30",
        post_id=10340,
        slug="ps6-announced-20260630",
        wp_public_url="https://nozo3-kao6.tokyo/ps6-announced-20260630/",
        period_days=28,
        search_console=SearchConsoleMetrics(impressions=1500, clicks=75, ctr=0.05, avg_position=3.2),
        google_analytics=ga_metrics,
        data_source="google_analytics",
    )

    article_dict = {
        "post_id": 10340, "slug": "ps6-announced-20260630",
        "seo_title": "PS6正式発表", "importance": "S",
        "publish_status": "pending", "logged_at": "2026-06-30T00:00:00+09:00",
        "source_name": "PlayStation Blog",
        "wp_public_url": "https://nozo3-kao6.tokyo/ps6-announced-20260630/",
        "x_post_status": "pending",
    }

    analysis = mgr.build_analysis_record(article=article_dict, analytics=entry)

    check("build_analysis_record: page_views=2500", analysis.page_views, 2500)
    check("build_analysis_record: sessions=2000", analysis.sessions, 2000)
    check("build_analysis_record: bounce_rate=0.35", analysis.bounce_rate, 0.35)
    check("build_analysis_record: avg_engagement_time=62.5 (avg_time_on_pageから変換)", analysis.avg_engagement_time, 62.5)
    check("build_analysis_record: impressions=1500 (SC)", analysis.impressions, 1500)

    ai_input = mgr.build_ai_input(analysis)
    check("build_ai_input: page_views=2500", ai_input.page_views, 2500)
    check("build_ai_input: sessions=2000", ai_input.sessions, 2000)
    check("build_ai_input: bounce_rate=0.35", ai_input.bounce_rate, 0.35)
    check("build_ai_input: avg_engagement_time=62.5", ai_input.avg_engagement_time, 62.5)
    check("build_ai_input: has_performance_data=True", ai_input.has_performance_data, True)

# ─── シナリオ 11: 投稿直後に GA4 API を呼ばない（main.py の確認）───

print("\n=== Scenario 11: main.py does NOT call GA4 API on post ===")

import importlib.util

main_path = Path(__file__).parent.parent / "main.py"
main_content = main_path.read_text(encoding="utf-8")

ga4_client_in_main = "GoogleAnalyticsClient" in main_content or "GoogleAnalyticsFetcher" in main_content
check("main.py に GoogleAnalyticsClient/Fetcher が含まれない", ga4_client_in_main, False)

ga4_import_in_main = "google_analytics_client" in main_content or "google_analytics_fetcher" in main_content
check("main.py に GA4 クライアントのインポートがない", ga4_import_in_main, False)

# ─── シナリオ 12: Search Console Foundation が壊れていない ───

print("\n=== Scenario 12: Search Console Foundation regression ===")

from analytics.search_console_client import NullSearchConsoleClient
from analytics.search_console_fetcher import SearchConsoleFetcher
from analytics.analytics_entry import SearchConsoleMetrics as SCM

sc_null = NullSearchConsoleClient()
check("SC NullClient.is_available()=False", sc_null.is_available(), False)
check("SC NullClient.fetch_raw() = {}", sc_null.fetch_raw("https://example.com/"), {})

sc_fetcher = SearchConsoleFetcher(client=sc_null)
sc_metrics = sc_fetcher.fetch("https://nozo3-kao6.tokyo/test/")
check("SC Fetcher でゼロ値 SearchConsoleMetrics を返す", isinstance(sc_metrics, SCM), True)
check("SC Fetcher ゼロ値: impressions=0", sc_metrics.impressions, 0)

# ─── シナリオ 13: 既存バージョン互換性（インポートテスト）───

print("\n=== Scenario 13: backward compatibility import test ===")

from analytics import (
    AnalyticsManager, NullAnalyticsManager,
    SearchConsoleConfig, SearchConsoleClient, NullSearchConsoleClient,
    SearchConsoleFetcher, GoogleApiClient,
    GoogleAnalyticsConfig, GoogleAnalyticsClient, NullGoogleAnalyticsClient,
    GoogleAnalyticsFetcher,
)

check("全クラスのインポート成功", True, True)

from analytics.analytics_entry import (
    SearchConsoleMetrics, GoogleAnalyticsMetrics,
    AnalyticsEntry, ArticleAnalysisRecord, AiInputRecord,
)
check("全エントリクラスのインポート成功", True, True)

# ─── 結果サマリー ───

print("\n" + "=" * 60)
passed = sum(1 for s, _ in results if s == "PASS")
failed = sum(1 for s, _ in results if s == "FAIL")
print(f"Result: {passed}/{len(results)} PASS  ({failed} FAIL)")
print("=" * 60)

if failed > 0:
    print("\nFailed tests:")
    for status, label in results:
        if status == "FAIL":
            print(f"  NG {label}")
    sys.exit(1)
else:
    print("All PASS")
    sys.exit(0)
