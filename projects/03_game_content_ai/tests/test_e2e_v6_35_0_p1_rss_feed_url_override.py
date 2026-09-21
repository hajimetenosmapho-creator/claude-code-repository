"""
E2E テスト: Release 6.35 P1 — NEWS_RSS_FEED_URLS_OVERRIDE

Source of Truth:
    docs/design/mvp_end_to_end_hardening_validation.md 7.5.1a節（完全仕様）。

対象production: src/collector.py（_resolve_rss_feeds() / _validate_feed_url() /
_reject_duplicate_keys()、新設関数のみ。RSS_FEEDS・FEED_GROUPSは無変更）。

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_35_0_p1_rss_feed_url_override.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).parent.parent
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SRC_DIR))

results_log = []


def check(label: str, actual, expected):
    ok = actual == expected
    status = "PASS" if ok else "FAIL"
    results_log.append((status, label))
    mark = "OK" if ok else "NG"
    print(f"  [{mark}] {label}")
    if not ok:
        print(f"       期待値: {expected!r}")
        print(f"       実際値: {actual!r}")


def check_true(label: str, value: bool):
    check(label, bool(value), True)


def check_false(label: str, value: bool):
    check(label, bool(value), False)


def check_raises(label: str, fn, exc_type=ValueError):
    try:
        fn()
    except exc_type:
        check(label, True, True)
    except Exception as e:  # noqa: BLE001 - 想定外の例外種別も明示的にFAILへ落とす
        check(label, f"raised {type(e).__name__}", f"raised {exc_type.__name__}")
    else:
        check(label, "no exception", f"raised {exc_type.__name__}")


print("=" * 60)
print("Release 6.35 P1: NEWS_RSS_FEED_URLS_OVERRIDE E2E テスト")
print("=" * 60)
print()

import collector  # noqa: E402
from collector import (  # noqa: E402
    RSS_FEEDS,
    NEWS_RSS_FEED_URLS_OVERRIDE_ENV,
    _resolve_rss_feeds,
    _validate_feed_url,
)

_ENV_KEY = NEWS_RSS_FEED_URLS_OVERRIDE_ENV
_saved_env = os.environ.get(_ENV_KEY)


def _clear_env():
    os.environ.pop(_ENV_KEY, None)


def _valid_override_dict() -> dict:
    return {key: f"http://127.0.0.1:8123/rss/{i}" for i, key in enumerate(RSS_FEEDS.keys())}


# =====================================================================
# [テスト1] 未設定時：既存RSS_FEEDS動作を完全維持
# =====================================================================
print("[テスト1] 未設定時の挙動")
_clear_env()
result_1 = _resolve_rss_feeds()
check_true("1a. 未設定時はRSS_FEEDSと同一オブジェクトを返す", result_1 is RSS_FEEDS)
check("1b. 未設定時はRSS_FEEDSと内容が完全一致", result_1, RSS_FEEDS)
print()

# =====================================================================
# [テスト2] 設定時：valid overrideで全16件置換
# =====================================================================
print("[テスト2] valid overrideの適用")
override_2 = _valid_override_dict()
os.environ[_ENV_KEY] = json.dumps(override_2)
result_2 = _resolve_rss_feeds()
check("2a. valid override適用後は指定した16件と完全一致", result_2, override_2)
check("2b. キー集合はRSS_FEEDSと完全一致", set(result_2.keys()), set(RSS_FEEDS.keys()))
_clear_env()
print()

# =====================================================================
# [テスト3] trimmed canonical result
# =====================================================================
print("[テスト3] trimmed canonical result")
override_3 = _valid_override_dict()
key0 = next(iter(RSS_FEEDS.keys()))
override_3[key0] = "   http://127.0.0.1:8123/rss/padded   "
os.environ[_ENV_KEY] = json.dumps(override_3)
result_3 = _resolve_rss_feeds()
check("3a. 前後空白はstrip()されたcanonical値になる", result_3[key0], "http://127.0.0.1:8123/rss/padded")
_clear_env()
print()

# =====================================================================
# [テスト4] duplicate JSON key拒否
# =====================================================================
print("[テスト4] duplicate JSON keyの拒否")
keys_4 = list(RSS_FEEDS.keys())
pairs_4 = ",".join(f'"{k}": "http://127.0.0.1:1/{i}"' for i, k in enumerate(keys_4))
raw_4 = "{" + pairs_4 + f', "{keys_4[0]}": "http://127.0.0.1:1/dup"' + "}"
os.environ[_ENV_KEY] = raw_4
check_raises("4a. 重複キーを含むJSONはValueErrorで拒否される", _resolve_rss_feeds)
_clear_env()
print()

# =====================================================================
# [テスト5] キー不足・過剰・非object・malformed JSON拒否
# =====================================================================
print("[テスト5] キー集合不一致・不正JSON構造の拒否")

override_5a = _valid_override_dict()
del override_5a[next(iter(override_5a))]
os.environ[_ENV_KEY] = json.dumps(override_5a)
check_raises("5a. キー不足（15件）はValueErrorで拒否される", _resolve_rss_feeds)
_clear_env()

override_5b = _valid_override_dict()
override_5b["ExtraSource"] = "http://127.0.0.1:1/extra"
os.environ[_ENV_KEY] = json.dumps(override_5b)
check_raises("5b. キー過剰（17件）はValueErrorで拒否される", _resolve_rss_feeds)
_clear_env()

os.environ[_ENV_KEY] = json.dumps([1, 2, 3])
check_raises("5c. JSON配列（dictでない）はValueErrorで拒否される", _resolve_rss_feeds)
_clear_env()

os.environ[_ENV_KEY] = "{not valid json"
check_raises("5d. 構文的に不正なJSONはValueErrorで拒否される", _resolve_rss_feeds)
_clear_env()
print()

# =====================================================================
# [テスト6] invalid URL/hostname/port/control/percent
# =====================================================================
print("[テスト6] 不正なURL/hostname/port/control文字/percent-escapeの拒否")

_bad_urls = [
    ("6a. scheme-only", "https://"),
    ("6b. host欠落", "https:///path"),
    ("6c. 非対応scheme", "ftp://example.com/feed"),
    ("6d. 大文字scheme", "HTTPS://example.com/feed"),
    ("6e. host中の空白", "https://exam ple.com"),
    ("6f. port範囲外", "https://example.com:99999"),
    ("6g. port 0", "https://example.com:0"),
    ("6h. 明示的な空port", "https://example.com:/feed"),
    ("6i. 非数値port", "https://example.com:abc"),
    ("6j. IPv4形状だがoctet範囲外", "https://999.999.999.999/feed"),
    ("6k. IPv4短縮表記", "https://127.1/feed"),
    ("6l. IPv4整数一括表記", "https://2130706433/feed"),
    ("6m. IPv4 16進octet表記", "https://0x7f.0.0.1/feed"),
    ("6n. RFC1123外文字（アンダースコア）", "https://exa_mple.com/feed"),
    ("6o. 不正percent-escape", "https://example.com/%zz"),
    ("6p. 空文字列", ""),
    ("6q. 空白のみ", "   "),
    ("6r. 双方向制御文字混入", "https://exa‮mple.com/feed"),
    ("6s. DEL文字混入", "https://example.com/feed"),
]
for label, bad_url in _bad_urls:
    check_raises(f"{label}: 拒否される", lambda u=bad_url: _validate_feed_url(u))

check_raises("6t. 非string値（bool）は拒否される", lambda: _validate_feed_url(True))
print()

# =====================================================================
# [テスト7] 正常値の受理・1件でもinvalidならoverride全体fail-closed
# =====================================================================
print("[テスト7] 正常値の受理・全体fail-closed")

check("7a. localhost hostnameは受理される",
      _validate_feed_url("https://localhost/feed"), "https://localhost/feed")
check("7b. IPv4 literalは受理される",
      _validate_feed_url("http://127.0.0.1:8123/rss/4gamer"), "http://127.0.0.1:8123/rss/4gamer")

override_7 = _valid_override_dict()
override_7[key0] = "ftp://example.com/feed"
os.environ[_ENV_KEY] = json.dumps(override_7)
check_raises("7c. 1件でもinvalidなら16件全体がfail-closedで拒否される", _resolve_rss_feeds)
_clear_env()
print()

# =====================================================================
# [テスト8] 既存default behavior維持・network access前にvalidation完了
# =====================================================================
print("[テスト8] 既存default behavior維持")

check("8a. RSS_FEEDSは16キー", len(RSS_FEEDS), 16)

_fetch_calls = []


def _fake_fetch(source_name, feed_url, max_items):
    _fetch_calls.append((source_name, feed_url))
    return [], collector.FeedStats(source_name, 0, "empty")


_clear_env()
_original_fetch = collector.fetch_from_feed
collector.fetch_from_feed = _fake_fetch
try:
    collector.collect_all_news(max_items_per_feed=5)
finally:
    collector.fetch_from_feed = _original_fetch

check("8b. 未設定時、collect_all_news()はRSS_FEEDSの順序どおりfetch_from_feed()を呼ぶ",
      _fetch_calls, list(RSS_FEEDS.items()))

# network access前にvalidation完了：不正overrideの場合、fetch_from_feed()は一度も呼ばれない
# 【Post-Codex-delta-review Amendment、Minor#3対応】_fake_fetch()は常に
# _fetch_calls（8b用の共有list）へ追記するため、別の空listを検査すると
# 「一度も呼ばれない」がfetch実施の有無に関わらず常に真になり無効化された
# assertionになっていた（Codex delta review Minor#3で指摘）。8b終了時点の
# _fetch_callsの長さを基準点として保存し、8cの前後での増分（差分）で
# 実効的にfetch発生の有無を検証するよう修正する。
_fetch_calls_count_before_8c = len(_fetch_calls)
collector.fetch_from_feed = _fake_fetch
override_8 = _valid_override_dict()
override_8[key0] = "ftp://example.com/feed"
os.environ[_ENV_KEY] = json.dumps(override_8)
try:
    check_raises("8c. 不正overrideはcollect_all_news()内でもValueErrorとして伝播する",
                 lambda: collector.collect_all_news(max_items_per_feed=5))
finally:
    collector.fetch_from_feed = _original_fetch
    _clear_env()
check("8d. validation失敗時はfetch_from_feed()（network access）が一度も呼ばれない",
      len(_fetch_calls) - _fetch_calls_count_before_8c, 0)
print()

# ── 後始末：テスト実行前の環境変数状態を復元 ──
if _saved_env is None:
    _clear_env()
else:
    os.environ[_ENV_KEY] = _saved_env


# =====================================================================
# 結果サマリ
# =====================================================================
print("=" * 60)
passed = sum(1 for s, _ in results_log if s == "PASS")
failed = sum(1 for s, _ in results_log if s == "FAIL")
print(f"結果: {passed} PASS / {failed} FAIL / 合計 {len(results_log)}")
if failed:
    print("失敗したテスト:")
    for s, label in results_log:
        if s == "FAIL":
            print(f"  - {label}")
    sys.exit(1)
print("全テストPASS")
