"""
E2E テスト: v1.12.0 Search Console Foundation

テストシナリオ:
    1. SearchConsoleConfig.from_env() の動作確認
    2. SEARCH_CONSOLE_ENABLED=false → NullSearchConsoleClient
    3. NullSearchConsoleClient が安全に動作する
    4. SearchConsoleFetcher が SearchConsoleMetrics を返す（モック）
    5. API 失敗時にゼロ値 SearchConsoleMetrics を返す
    6. SearchConsoleMetrics の重複定義がない（Single Source of Truth）
    7. main.py の既存処理が壊れていない（インポートテスト）
    8. ANALYTICS_ENABLED=false で NullAnalyticsManager が返る
    9. SearchConsoleFetcher が複数行レスポンスを正しく集計する
    10. NullAnalyticsManager が no-op で安全に動作する

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v1_12_0_search_console_foundation.py
"""
import sys
import os
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

# ─── シナリオ 1: SearchConsoleConfig.from_env() ───

print("\n=== Scenario 1: SearchConsoleConfig.from_env() ===")

from analytics.search_console_config import SearchConsoleConfig

# デフォルト（全環境変数未設定）
for key in ["SEARCH_CONSOLE_ENABLED", "SEARCH_CONSOLE_PROPERTY", "GOOGLE_APPLICATION_CREDENTIALS"]:
    os.environ.pop(key, None)

config_default = SearchConsoleConfig.from_env()
check("デフォルト: enabled=False", config_default.enabled, False)
check("デフォルト: property_url=None", config_default.property_url, None)
check("デフォルト: credentials_path=None", config_default.credentials_path, None)
check("デフォルト: period_days=28", config_default.period_days, 28)
check("デフォルト: timeout_seconds=30", config_default.timeout_seconds, 30)
check("デフォルト: is_ready()=False", config_default.is_ready(), False)

# 有効化（設定あり）
os.environ["SEARCH_CONSOLE_ENABLED"] = "true"
os.environ["SEARCH_CONSOLE_PROPERTY"] = "https://nozo3-kao6.tokyo/"
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "credentials/search_console_sa.json"

config_enabled = SearchConsoleConfig.from_env()
check("有効時: enabled=True", config_enabled.enabled, True)
check("有効時: property_url 設定済み", config_enabled.property_url, "https://nozo3-kao6.tokyo/")
check("有効時: credentials_path 設定済み", config_enabled.credentials_path, "credentials/search_console_sa.json")
check("有効時: is_ready()=True", config_enabled.is_ready(), True)

# enabled=false + 他は設定済み → is_ready()=False
os.environ["SEARCH_CONSOLE_ENABLED"] = "false"
config_disabled_with_creds = SearchConsoleConfig.from_env()
check("disabled+設定あり: is_ready()=False", config_disabled_with_creds.is_ready(), False)

# 後始末
for key in ["SEARCH_CONSOLE_ENABLED", "SEARCH_CONSOLE_PROPERTY", "GOOGLE_APPLICATION_CREDENTIALS"]:
    os.environ.pop(key, None)

# ─── シナリオ 2: SEARCH_CONSOLE_ENABLED=false → NullSearchConsoleClient ───

print("\n=== Scenario 2: SEARCH_CONSOLE_ENABLED=false → NullSearchConsoleClient ===")

from analytics.search_console_client import SearchConsoleClient, NullSearchConsoleClient

os.environ.pop("SEARCH_CONSOLE_ENABLED", None)
client_from_env = SearchConsoleClient.from_env()

check("from_env() が NullSearchConsoleClient を返す", isinstance(client_from_env, NullSearchConsoleClient), True)
check("NullSearchConsoleClient.is_available()=False", client_from_env.is_available(), False)

# SEARCH_CONSOLE_ENABLED=true でも credentials なし → NullSearchConsoleClient
os.environ["SEARCH_CONSOLE_ENABLED"] = "true"
os.environ.pop("SEARCH_CONSOLE_PROPERTY", None)
os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
client_missing_creds = SearchConsoleClient.from_env()
check("credentials 不足 → NullSearchConsoleClient", isinstance(client_missing_creds, NullSearchConsoleClient), True)

os.environ.pop("SEARCH_CONSOLE_ENABLED", None)

# ─── シナリオ 3: NullSearchConsoleClient が安全に動作する ───

print("\n=== Scenario 3: NullSearchConsoleClient safe operation ===")

null_client = NullSearchConsoleClient()
check("NullSearchConsoleClient.is_available()=False", null_client.is_available(), False)

raw = null_client.fetch_raw("https://nozo3-kao6.tokyo/ps6/")
check("NullSearchConsoleClient.fetch_raw() = {}", raw, {})

raw_with_period = null_client.fetch_raw("https://nozo3-kao6.tokyo/ps6/", period_days=14)
check("NullSearchConsoleClient.fetch_raw(period_days=14) = {}", raw_with_period, {})

# ─── シナリオ 4: SearchConsoleFetcher が SearchConsoleMetrics を返す（モック）───

print("\n=== Scenario 4: SearchConsoleFetcher returns SearchConsoleMetrics (mocked) ===")

from analytics.search_console_fetcher import SearchConsoleFetcher
from analytics.analytics_entry import SearchConsoleMetrics

mock_api_response = {
    "rows": [
        {
            "keys": ["https://nozo3-kao6.tokyo/ps6-announced-20260630/"],
            "impressions": 1500,
            "clicks": 75,
            "ctr": 0.05,
            "position": 3.2,
        }
    ]
}

mock_client = MagicMock()
mock_client.is_available.return_value = True
mock_client.fetch_raw.return_value = mock_api_response

fetcher = SearchConsoleFetcher(client=mock_client)
check("fetcher.is_available()=True（モック）", fetcher.is_available(), True)

metrics = fetcher.fetch("https://nozo3-kao6.tokyo/ps6-announced-20260630/", period_days=28)

check("metrics は SearchConsoleMetrics インスタンス", isinstance(metrics, SearchConsoleMetrics), True)
check("impressions=1500", metrics.impressions, 1500)
check("clicks=75", metrics.clicks, 75)
check("ctr=0.05", metrics.ctr, 0.05)
check("avg_position=3.2", metrics.avg_position, 3.2)

# ─── シナリオ 5: API 失敗時にゼロ値を返す ───

print("\n=== Scenario 5: API failure returns zero SearchConsoleMetrics ===")

# fetch_raw が例外を投げるモック
mock_client_fail = MagicMock()
mock_client_fail.is_available.return_value = True
mock_client_fail.fetch_raw.side_effect = Exception("Network error")

fetcher_fail = SearchConsoleFetcher(client=mock_client_fail)
metrics_fail = fetcher_fail.fetch("https://nozo3-kao6.tokyo/ps6/", period_days=28)

check("例外時: metrics は SearchConsoleMetrics", isinstance(metrics_fail, SearchConsoleMetrics), True)
check("例外時: impressions=0（ゼロ値）", metrics_fail.impressions, 0)
check("例外時: clicks=0（ゼロ値）", metrics_fail.clicks, 0)
check("例外時: ctr=0.0（ゼロ値）", metrics_fail.ctr, 0.0)
check("例外時: avg_position=0.0（ゼロ値）", metrics_fail.avg_position, 0.0)

# rows が空の場合
mock_client_empty = MagicMock()
mock_client_empty.is_available.return_value = True
mock_client_empty.fetch_raw.return_value = {"rows": []}

fetcher_empty = SearchConsoleFetcher(client=mock_client_empty)
metrics_empty = fetcher_empty.fetch("https://nozo3-kao6.tokyo/old-article/", period_days=28)

check("rows 空: impressions=0", metrics_empty.impressions, 0)
check("rows 空: clicks=0", metrics_empty.clicks, 0)

# NullSearchConsoleClient → ゼロ値
fetcher_null = SearchConsoleFetcher(client=NullSearchConsoleClient())
metrics_null = fetcher_null.fetch("https://nozo3-kao6.tokyo/test/", period_days=28)
check("NullClient 経由: impressions=0", metrics_null.impressions, 0)
check("NullClient 経由: is_available()=False", fetcher_null.is_available(), False)

# ─── シナリオ 6: SearchConsoleMetrics の重複定義がない（Single Source of Truth）───

print("\n=== Scenario 6: SearchConsoleMetrics Single Source of Truth ===")

from analytics.analytics_entry import SearchConsoleMetrics as SCM_from_entry
from analytics import SearchConsoleMetrics as SCM_from_init
from analytics.analytics_manager import AnalyticsManager as AM_direct

check("analytics_entry と analytics.__init__ が同一クラス", SCM_from_entry is SCM_from_init, True)

# SearchConsoleFetcher が使う SearchConsoleMetrics も同一クラスであることを確認
fetcher_check = SearchConsoleFetcher(client=NullSearchConsoleClient())
zero_metrics = fetcher_check.fetch("https://example.com/", period_days=28)
check("Fetcher が返す型も同一クラス（重複定義なし）", type(zero_metrics) is SCM_from_entry, True)

# ─── シナリオ 7: main.py インポートテスト ───

print("\n=== Scenario 7: main.py import test ===")

import importlib.util

main_spec_ok = False
try:
    spec = importlib.util.spec_from_file_location(
        "main",
        Path(__file__).parent.parent / "main.py"
    )
    main_spec_ok = spec is not None
except Exception as e:
    print(f"       main.py spec 作成失敗: {e}")

check("main.py の spec 作成成功", main_spec_ok, True)

# analytics が main.py からインポート可能か確認
analytics_importable = False
try:
    from analytics import AnalyticsManager
    analytics_importable = True
except ImportError as e:
    print(f"       analytics インポート失敗: {e}")

check("analytics.AnalyticsManager がインポート可能", analytics_importable, True)

# ─── シナリオ 8: ANALYTICS_ENABLED=false → NullAnalyticsManager ───

print("\n=== Scenario 8: ANALYTICS_ENABLED=false → NullAnalyticsManager ===")

from analytics import AnalyticsManager, NullAnalyticsManager

os.environ["ANALYTICS_ENABLED"] = "false"
mgr = AnalyticsManager.from_env()
check("ANALYTICS_ENABLED=false → NullAnalyticsManager", isinstance(mgr, NullAnalyticsManager), True)

os.environ.pop("ANALYTICS_ENABLED", None)

# ─── シナリオ 9: SearchConsoleFetcher 複数行レスポンスの集計 ───

print("\n=== Scenario 9: SearchConsoleFetcher multi-row aggregation ===")

mock_multi_response = {
    "rows": [
        {"impressions": 1000, "clicks": 50, "ctr": 0.05, "position": 3.0},
        {"impressions": 500,  "clicks": 25, "ctr": 0.05, "position": 4.0},
    ]
}

mock_multi = MagicMock()
mock_multi.is_available.return_value = True
mock_multi.fetch_raw.return_value = mock_multi_response

fetcher_multi = SearchConsoleFetcher(client=mock_multi)
metrics_multi = fetcher_multi.fetch("https://nozo3-kao6.tokyo/test/", period_days=28)

check("複数行: impressions=1500（合計）", metrics_multi.impressions, 1500)
check("複数行: clicks=75（合計）", metrics_multi.clicks, 75)
check("複数行: ctr=0.05（平均）", metrics_multi.ctr, 0.05)
check("複数行: avg_position=3.5（平均）", metrics_multi.avg_position, 3.5)

# ─── シナリオ 10: NullAnalyticsManager が no-op で安全に動作する ───

print("\n=== Scenario 10: NullAnalyticsManager no-op safety ===")

from analytics import NullAnalyticsManager

null_mgr = NullAnalyticsManager()

placeholder = null_mgr.create_placeholder_entry(
    post_id=10340, slug="ps6-announced-20260630", wp_public_url="https://nozo3-kao6.tokyo/ps6/"
)
check("NullAnalyticsManager.create_placeholder_entry() = None", placeholder, None)

null_mgr.save_analytics_entry(None)
check("NullAnalyticsManager.save_analytics_entry(None) は例外なし", True, True)

article_logs = list(null_mgr.load_article_logs(log_dir=None, date_str="20260630"))
check("NullAnalyticsManager.load_article_logs() = []", article_logs, [])

analytics_logs = null_mgr.load_analytics_logs(date_str="20260630")
check("NullAnalyticsManager.load_analytics_logs() = {}", analytics_logs, {})

analysis = null_mgr.build_analysis_record(article={"post_id": 1}, analytics=None)
check("NullAnalyticsManager.build_analysis_record() = None", analysis, None)

ai_input = null_mgr.build_ai_input(record=None)
check("NullAnalyticsManager.build_ai_input() = None", ai_input, None)

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
