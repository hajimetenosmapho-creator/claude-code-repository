"""
E2E テスト: v6.28.0 Article Media Upload State Foundation（DI-6）

Source of Truth:
    docs/design/article_media_upload_state_foundation.md

article単位でWordPress media uploadの「試行開始」「確定成功」のみを記録・照会する、
Consumer-lessな独立Foundation（src/article_media_upload_state/）。本Releaseは
main.py等へのruntime wiringを一切行わない（HWP-1〜HWP-3、設計書13章）。

本テストは実WordPress API・実HTTP通信・実課金のいずれも発生させない。
一時ディレクトリへのファイルI/Oとgitのローカル呼び出しのみ。

Scenario構成:
    LIFECYCLE-   record_upload_started / record_upload_succeeded / get_state の
                 transition table全経路（設計書4.2節）
    ENTRY-       Public API入口でのfail-fast validation（identity・media_id）が
                 store accessより前に働くこと（設計書4.1節、Codex Round 4 M-1）
    RECORD-      ArticleMediaUploadRecord の __post_init__ invariant（設計書6章）
    TIMESTAMP-   canonical UTC ISO8601 + round-trip equality（設計書7章）
    SCHEMA-      closed JSON schema・identity整合性・corruption fail-closed
                 （設計書8章・9章）
    IO-          filesystem write失敗の統一Contract・fd leak防止（設計書11章）
    ZERODIFF-    既存protected pathに一切触れていないこと
    EXPORT-      article_media_upload_state パッケージのexport確認

実行方法:
    cd projects/03_game_content_ai
    .\\venv\\Scripts\\python.exe tests\\test_e2e_v6_28_0_article_media_upload_state_foundation.py
"""
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).parent.parent
TESTS_DIR = Path(__file__).parent
sys.path.insert(0, str(TESTS_DIR))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import zero_diff_guard_registry as registry  # noqa: E402

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


def check_raises(label: str, fn, exc_type):
    try:
        fn()
        check_true(label, False)
    except exc_type:
        check_true(label, True)
    except Exception as e:
        results_log.append(("FAIL", label))
        print(f"  [NG] {label}")
        print(f"       期待した例外型: {exc_type.__name__}")
        print(f"       実際の例外型: {type(e).__name__}: {e}")


print("=" * 60)
print("v6.28.0 Article Media Upload State Foundation E2E テスト")
print("=" * 60)
print()

from article_media_upload_state import (  # noqa: E402
    ArticleMediaUploadRecord,
    ArticleMediaUploadState,
    ArticleMediaUploadStateConfig,
    ArticleMediaUploadStateConflictError,
    ArticleMediaUploadStateCorruptedError,
    ArticleMediaUploadStateIOError,
    ArticleMediaUploadStateManager,
    ArticleMediaUploadStateStore,
    ArticleMediaUploadStateTransitionError,
    JsonArticleMediaUploadStateStore,
)
from article_media_upload_state.article_media_upload_record import (  # noqa: E402
    is_canonical_utc_iso8601,
    now_utc_iso,
)
from article_media_upload_state.json_article_media_upload_state_store import (  # noqa: E402
    _identity_hash,
)


class _SpyStore(ArticleMediaUploadStateStore):
    """store accessが発生したかどうかを記録するだけのテスト用Store。"""

    def __init__(self, canned_record=None):
        self.get_calls = 0
        self.save_calls = 0
        self._canned_record = canned_record

    def get(self, article_identity):
        self.get_calls += 1
        return self._canned_record

    def save(self, record):
        self.save_calls += 1


# ─── [テスト1] LIFECYCLE: transition table全経路 ───

print("[テスト1] LIFECYCLE: transition table全経路")

with tempfile.TemporaryDirectory() as tmpdir:
    store = JsonArticleMediaUploadStateStore(Path(tmpdir))
    manager = ArticleMediaUploadStateManager(store)
    identity = "https://example.com/news/1"

    check_true("1a. 初期状態はNone", manager.get_state(identity) is None)

    record = manager.record_upload_started(identity)
    check_true("1b. None -> started -> ATTEMPT_STARTED", record.state is ArticleMediaUploadState.ATTEMPT_STARTED)
    check_true("1c. ATTEMPT_STARTEDのmedia_idはNone", record.media_id is None)

    check_raises(
        "1d. 既存ATTEMPT_STARTEDへのstartedはTransitionError（fail-closed）",
        lambda: manager.record_upload_started(identity),
        ArticleMediaUploadStateTransitionError,
    )

    confirmed = manager.record_upload_succeeded(identity, 42)
    check_true("1e. ATTEMPT_STARTED -> succeeded -> UPLOAD_CONFIRMED", confirmed.state is ArticleMediaUploadState.UPLOAD_CONFIRMED)
    check_true("1f. UPLOAD_CONFIRMEDのmedia_idが確定", confirmed.media_id == 42)

    check_raises(
        "1g. UPLOAD_CONFIRMEDへのstartedはTransitionError（保護terminal state）",
        lambda: manager.record_upload_started(identity),
        ArticleMediaUploadStateTransitionError,
    )

    replay = manager.record_upload_succeeded(identity, 42)
    check_true("1h. 同一media_id再確認はstable replay（no-op）", replay.media_id == 42 and replay.state is ArticleMediaUploadState.UPLOAD_CONFIRMED)

    check_raises(
        "1i. 異なるmedia_idはConflictError",
        lambda: manager.record_upload_succeeded(identity, 99),
        ArticleMediaUploadStateConflictError,
    )

    still_confirmed = manager.get_state(identity)
    check_true("1j. Conflict後もmedia_idは変化しない", still_confirmed.media_id == 42)

    other_identity = "https://example.com/news/never-started"
    check_raises(
        "1k. recordなしからのsucceededはTransitionError（direct success禁止）",
        lambda: manager.record_upload_succeeded(other_identity, 1),
        ArticleMediaUploadStateTransitionError,
    )

print()


# ─── [テスト2] ENTRY: Public API入口でのfail-fast validation ───

print("[テスト2] ENTRY: Public API入口でのfail-fast validation")

invalid_identities = ["", "   ", "\t\n", 123, None, 1.5, b"bytes"]
for invalid in invalid_identities:
    spy = _SpyStore()
    manager = ArticleMediaUploadStateManager(spy)
    check_raises(
        f"2a. record_upload_started(invalid identity={invalid!r})はValueError",
        lambda inv=invalid: manager.record_upload_started(inv),
        ValueError,
    )
    check_true(f"2a. invalid identity={invalid!r}でstore.get()が呼ばれない", spy.get_calls == 0)

    spy2 = _SpyStore()
    manager2 = ArticleMediaUploadStateManager(spy2)
    check_raises(
        f"2b. get_state(invalid identity={invalid!r})はValueError",
        lambda inv=invalid: manager2.get_state(inv),
        ValueError,
    )
    check_true(f"2b. invalid identity={invalid!r}でstore.get()が呼ばれない", spy2.get_calls == 0)

    spy3 = _SpyStore()
    manager3 = ArticleMediaUploadStateManager(spy3)
    check_raises(
        f"2c. record_upload_succeeded(invalid identity={invalid!r}, 1)はValueError",
        lambda inv=invalid: manager3.record_upload_succeeded(inv, 1),
        ValueError,
    )
    check_true(f"2c. invalid identity={invalid!r}でstore.get()が呼ばれない", spy3.get_calls == 0)

invalid_media_ids = [True, False, 0, -1, -100, 1.0, "1", None, b"1"]
for invalid_media_id in invalid_media_ids:
    spy = _SpyStore()
    manager = ArticleMediaUploadStateManager(spy)
    check_raises(
        f"2d. record_upload_succeeded(valid identity, media_id={invalid_media_id!r})はValueError",
        lambda mid=invalid_media_id: manager.record_upload_succeeded("https://example.com/x", mid),
        ValueError,
    )
    check_true(f"2d. media_id={invalid_media_id!r}はstore.get()より前に拒否される", spy.get_calls == 0)

# M-1の核心シナリオ：既存UPLOAD_CONFIRMED(media_id=1)に対してmedia_id=Trueを渡す
existing_confirmed = ArticleMediaUploadRecord(
    article_identity="https://example.com/bool-trap",
    state=ArticleMediaUploadState.UPLOAD_CONFIRMED,
    media_id=1,
    updated_at=now_utc_iso(),
)
bool_trap_store = _SpyStore(canned_record=existing_confirmed)
bool_trap_manager = ArticleMediaUploadStateManager(bool_trap_store)
check_raises(
    "2e. 既存UPLOAD_CONFIRMED(media_id=1)へmedia_id=Trueを渡すとValueError（1==True誤受理を防止）",
    lambda: bool_trap_manager.record_upload_succeeded("https://example.com/bool-trap", True),
    ValueError,
)
check_true("2e. media_id=Trueはexisting.media_idとの比較（store.get）より前に拒否される", bool_trap_store.get_calls == 0)

print()


# ─── [テスト3] RECORD: __post_init__ invariant（直接構築） ───

print("[テスト3] RECORD: __post_init__ invariant（直接構築）")

check_raises(
    "3a. article_identity=''は拒否",
    lambda: ArticleMediaUploadRecord("", ArticleMediaUploadState.ATTEMPT_STARTED, None, now_utc_iso()),
    ValueError,
)
check_raises(
    "3b. article_identity='   '（空白のみ）は拒否",
    lambda: ArticleMediaUploadRecord("   ", ArticleMediaUploadState.ATTEMPT_STARTED, None, now_utc_iso()),
    ValueError,
)
check_raises(
    "3c. state='attempt_started'（生文字列、非Enum）は拒否",
    lambda: ArticleMediaUploadRecord("id", "attempt_started", None, now_utc_iso()),
    ValueError,
)
check_raises(
    "3d. ATTEMPT_STARTEDでmedia_id=1は拒否",
    lambda: ArticleMediaUploadRecord("id", ArticleMediaUploadState.ATTEMPT_STARTED, 1, now_utc_iso()),
    ValueError,
)
check_raises(
    "3e. UPLOAD_CONFIRMEDでmedia_id=Noneは拒否",
    lambda: ArticleMediaUploadRecord("id", ArticleMediaUploadState.UPLOAD_CONFIRMED, None, now_utc_iso()),
    ValueError,
)
check_raises(
    "3f. UPLOAD_CONFIRMEDでmedia_id=0は拒否",
    lambda: ArticleMediaUploadRecord("id", ArticleMediaUploadState.UPLOAD_CONFIRMED, 0, now_utc_iso()),
    ValueError,
)
check_raises(
    "3g. UPLOAD_CONFIRMEDでmedia_id=-1は拒否",
    lambda: ArticleMediaUploadRecord("id", ArticleMediaUploadState.UPLOAD_CONFIRMED, -1, now_utc_iso()),
    ValueError,
)
check_raises(
    "3h. UPLOAD_CONFIRMEDでmedia_id=True（bool）は拒否",
    lambda: ArticleMediaUploadRecord("id", ArticleMediaUploadState.UPLOAD_CONFIRMED, True, now_utc_iso()),
    ValueError,
)
check_raises(
    "3i. UPLOAD_CONFIRMEDでmedia_id=1.0（float）は拒否",
    lambda: ArticleMediaUploadRecord("id", ArticleMediaUploadState.UPLOAD_CONFIRMED, 1.0, now_utc_iso()),
    ValueError,
)

# 正常系（直接構築が成功すること自体もInvariantの一部）
ok_started = ArticleMediaUploadRecord("id", ArticleMediaUploadState.ATTEMPT_STARTED, None, now_utc_iso())
check_true("3j. 正常なATTEMPT_STARTED直接構築は成功", ok_started.state is ArticleMediaUploadState.ATTEMPT_STARTED)
ok_confirmed = ArticleMediaUploadRecord("id", ArticleMediaUploadState.UPLOAD_CONFIRMED, 5, now_utc_iso())
check_true("3k. 正常なUPLOAD_CONFIRMED直接構築は成功", ok_confirmed.media_id == 5)

print()


# ─── [テスト4] TIMESTAMP: canonical UTC ISO8601 + round-trip equality ───

print("[テスト4] TIMESTAMP: canonical UTC ISO8601 + round-trip equality")

check_true("4a. generator出力はcanonicalとして受理される", is_canonical_utc_iso8601(now_utc_iso()))
check_false("4b. naive timestampは拒否", is_canonical_utc_iso8601(datetime(2026, 8, 14, 12, 0, 0).isoformat()))
check_false(
    "4c. non-UTC offset（+09:00）は拒否",
    is_canonical_utc_iso8601(datetime(2026, 8, 14, 12, 0, 0, tzinfo=timezone(timedelta(hours=9))).isoformat()),
)
check_false("4d. Zサフィックスは拒否", is_canonical_utc_iso8601("2026-08-14T12:00:00+00:00".replace("+00:00", "Z")))
check_false(
    "4e. space separator（generator非生成表現）はround-trip equalityで拒否",
    is_canonical_utc_iso8601("2026-08-14 12:34:56+00:00"),
)
check_false(
    "4f. 明示的.000000マイクロ秒（generatorが省略する表現）はround-trip equalityで拒否",
    is_canonical_utc_iso8601("2026-08-14T12:34:56.000000+00:00"),
)
check_false("4g. 非str値は拒否", is_canonical_utc_iso8601(12345))
check_false("4h. 不正な文字列は拒否", is_canonical_utc_iso8601("not-a-timestamp"))

check_raises(
    "4i. Recordはnaive timestampを拒否",
    lambda: ArticleMediaUploadRecord("id", ArticleMediaUploadState.ATTEMPT_STARTED, None, "2026-08-14T12:00:00"),
    ValueError,
)

print()


# ─── [テスト5] SCHEMA: closed JSON schema・identity整合性・corruption fail-closed ───

print("[テスト5] SCHEMA: closed JSON schema・identity整合性・corruption fail-closed")

with tempfile.TemporaryDirectory() as tmpdir:
    base_dir = Path(tmpdir)
    store = JsonArticleMediaUploadStateStore(base_dir)
    identity = "https://example.com/schema-test"

    def _write_raw(article_identity: str, content: str) -> Path:
        base_dir.mkdir(parents=True, exist_ok=True)
        path = base_dir / f"{_identity_hash(article_identity)}.json"
        path.write_text(content, encoding="utf-8")
        return path

    _write_raw(identity, "{not valid json")
    check_raises("5a. malformed JSON構文はCorruptedError", lambda: store.get(identity), ArticleMediaUploadStateCorruptedError)

    _write_raw(identity, json.dumps(["not", "a", "dict"]))
    check_raises("5b. top-levelがdictでない（配列）はCorruptedError", lambda: store.get(identity), ArticleMediaUploadStateCorruptedError)

    valid_doc = {
        "schema_version": 1,
        "article_identity": identity,
        "state": "attempt_started",
        "media_id": None,
        "updated_at": now_utc_iso(),
    }

    missing_key_doc = dict(valid_doc)
    del missing_key_doc["media_id"]
    _write_raw(identity, json.dumps(missing_key_doc))
    check_raises("5c. key欠落はCorruptedError", lambda: store.get(identity), ArticleMediaUploadStateCorruptedError)

    extra_key_doc = dict(valid_doc)
    extra_key_doc["extra_field"] = "unexpected"
    _write_raw(identity, json.dumps(extra_key_doc))
    check_raises("5d. key余剰はCorruptedError", lambda: store.get(identity), ArticleMediaUploadStateCorruptedError)

    bad_version_doc = dict(valid_doc)
    bad_version_doc["schema_version"] = True  # bool、1と等しいがtype()比較で拒否されるべき
    _write_raw(identity, json.dumps(bad_version_doc))
    check_raises("5e. schema_version=true（bool）はCorruptedError（type()比較でTrueを1として誤受理しない）", lambda: store.get(identity), ArticleMediaUploadStateCorruptedError)

    bad_version_doc2 = dict(valid_doc)
    bad_version_doc2["schema_version"] = 2
    _write_raw(identity, json.dumps(bad_version_doc2))
    check_raises("5f. 未知schema_version（2）はCorruptedError（silent upgradeしない）", lambda: store.get(identity), ArticleMediaUploadStateCorruptedError)

    bad_state_doc = dict(valid_doc)
    bad_state_doc["state"] = "deleted"
    _write_raw(identity, json.dumps(bad_state_doc))
    check_raises("5g. 未知state文字列はCorruptedError", lambda: store.get(identity), ArticleMediaUploadStateCorruptedError)

    bool_media_doc = dict(valid_doc)
    bool_media_doc["state"] = "upload_confirmed"
    bool_media_doc["media_id"] = True
    _write_raw(identity, json.dumps(bool_media_doc))
    check_raises("5h. UPLOAD_CONFIRMEDでmedia_id=trueはCorruptedError", lambda: store.get(identity), ArticleMediaUploadStateCorruptedError)

    mismatch_doc = dict(valid_doc)
    mismatch_doc["article_identity"] = "https://example.com/different-article"
    _write_raw(identity, json.dumps(mismatch_doc))
    check_raises(
        "5i. requested/persisted identity不一致はCorruptedError",
        lambda: store.get(identity),
        ArticleMediaUploadStateCorruptedError,
    )

    # raw content非漏洩の確認
    secret_doc = dict(valid_doc)
    secret_doc["article_identity"] = "https://example.com/SECRET-TOKEN-abc123"
    path = _write_raw(identity, json.dumps(secret_doc))
    try:
        store.get(identity)
        check_true("5j. secretを含むidentity不一致でも例外は送出される", False)
    except ArticleMediaUploadStateCorruptedError as e:
        check_true("5j. 例外メッセージにraw article_identity値が含まれない", "SECRET-TOKEN-abc123" not in str(e))

    # 正常系：ラウンドトリップ
    _write_raw(identity, json.dumps(valid_doc))
    record = store.get(identity)
    check_true("5k. 正常なschemaは正しくRecordへ復元される", record is not None and record.state is ArticleMediaUploadState.ATTEMPT_STARTED)

print()


# ─── [テスト6] IO: filesystem write失敗の統一Contract・fd leak防止 ───

print("[テスト6] IO: filesystem write失敗の統一Contract・fd leak防止")

with tempfile.TemporaryDirectory() as tmpdir:
    base_dir = Path(tmpdir) / "state"
    store = JsonArticleMediaUploadStateStore(base_dir)
    record = ArticleMediaUploadRecord(
        "https://example.com/io-test", ArticleMediaUploadState.ATTEMPT_STARTED, None, now_utc_iso()
    )

    with patch("pathlib.Path.mkdir", side_effect=OSError("mkdir boom")):
        check_raises("6a. mkdir失敗はArticleMediaUploadStateIOError", lambda: store.save(record), ArticleMediaUploadStateIOError)

    with patch("tempfile.mkstemp", side_effect=OSError("mkstemp boom")):
        check_raises("6b. mkstemp失敗はArticleMediaUploadStateIOError", lambda: store.save(record), ArticleMediaUploadStateIOError)
    check_true("6b. mkstemp失敗後、tmpファイルが残存しない", len(list(base_dir.glob("*.tmp"))) == 0)

    import os as os_module

    with patch("os.fdopen", side_effect=OSError("fdopen boom")), \
         patch("os.close", wraps=os_module.close) as mock_close:
        check_raises("6c. fdopen失敗はArticleMediaUploadStateIOError", lambda: store.save(record), ArticleMediaUploadStateIOError)
    check_true("6c. fdopen失敗時、raw fdがちょうど1回closeされる（leak防止）", mock_close.call_count == 1)
    check_true("6c. fdopen失敗後、tmpファイルが残存しない", len(list(base_dir.glob("*.tmp"))) == 0)

    with patch("os.fsync", side_effect=OSError("fsync boom")):
        check_raises("6d. fsync失敗はArticleMediaUploadStateIOError", lambda: store.save(record), ArticleMediaUploadStateIOError)
    check_true("6d. fsync失敗後、tmpファイルが残存しない（cleanup成功）", len(list(base_dir.glob("*.tmp"))) == 0)

    # 事前に正常なrecordを保存しておき、replace失敗時に元ファイルが無傷であることを確認
    store.save(record)
    original_path = base_dir / f"{_identity_hash(record.article_identity)}.json"
    original_content = original_path.read_text(encoding="utf-8")

    updated_record = ArticleMediaUploadRecord(
        record.article_identity, ArticleMediaUploadState.UPLOAD_CONFIRMED, 7, now_utc_iso()
    )
    with patch("os.replace", side_effect=OSError("replace boom")):
        check_raises("6e. replace失敗はArticleMediaUploadStateIOError", lambda: store.save(updated_record), ArticleMediaUploadStateIOError)
    check_true("6e. replace失敗後、tmpファイルが残存しない（best-effort cleanup）", len(list(base_dir.glob("*.tmp"))) == 0)
    check_true("6e. replace失敗後も既存のtarget fileは無傷（partial writeを避ける）", original_path.read_text(encoding="utf-8") == original_content)

    # 正常なsaveが成功することの確認（IO異常系の後でも通常経路が壊れていないこと）
    store.save(record)
    check_true("6f. 通常のsave/getは正常に機能する", store.get(record.article_identity).state is ArticleMediaUploadState.ATTEMPT_STARTED)

print()


# ─── [テスト7] ZERODIFF: 既存protected pathへの無変更確認 ───

print("[テスト7] ZERODIFF: 既存protected pathへの無変更確認")

unchanged_paths = [
    "main.py",
    "src/retry_queue",
    "src/article_featured_media",
    "src/article_featured_media_composition",
    "src/article_featured_media_orchestration",
    "src/article_featured_media_runtime",
    "src/logger",
    "src/outputs",
    "src/wordpress_media",
    "src/retry_runtime_lock",
]
# tests/zero_diff_guard_registry.py は本Releaseでappend-only編集する
# （REGISTRY-セクション参照）ため、無変更確認の対象から除外する。

git_available = True
try:
    subprocess.run(["git", "--version"], capture_output=True, cwd=str(PROJECT_ROOT), timeout=10)
except Exception:
    git_available = False

if git_available:
    for rel_path in unchanged_paths:
        completed = subprocess.run(
            ["git", "diff", "--quiet", "--", rel_path],
            cwd=str(PROJECT_ROOT), capture_output=True, timeout=10,
        )
        check_true(f"7. {rel_path} に変更がない（git diff）", completed.returncode == 0)
else:
    check_true("7. gitが利用できないため無変更確認をスキップ", True)

print()


# ─── [テスト8] EXPORT: パッケージのexport確認 ───

print("[テスト8] EXPORT: パッケージのexport確認")

import article_media_upload_state as amus_pkg  # noqa: E402

for name in (
    "ArticleMediaUploadState",
    "ArticleMediaUploadRecord",
    "ArticleMediaUploadStateStore",
    "JsonArticleMediaUploadStateStore",
    "ArticleMediaUploadStateConfig",
    "ArticleMediaUploadStateManager",
    "ArticleMediaUploadStateCorruptedError",
    "ArticleMediaUploadStateIOError",
    "ArticleMediaUploadStateConflictError",
    "ArticleMediaUploadStateTransitionError",
):
    check_true(f"8. {name} が article_media_upload_state パッケージからエクスポートされている", hasattr(amus_pkg, name))
    check_true(f"8. {name} が article_media_upload_state.__all__ に含まれる", name in amus_pkg.__all__)

# reason/failure系APIが存在しないことの確認（設計書3.1節）
check_false("8. record_upload_failed は存在しない", hasattr(ArticleMediaUploadStateManager, "record_upload_failed"))
check_false("8. record_upload_uncertain は存在しない", hasattr(ArticleMediaUploadStateManager, "record_upload_uncertain"))
check_false("8. FAILED state は存在しない", hasattr(ArticleMediaUploadState, "FAILED"))
check_true("8. ArticleMediaUploadStateConfig.from_env()が動作する", isinstance(ArticleMediaUploadStateConfig.from_env(), ArticleMediaUploadStateConfig))

print()


# ─── [テスト9] REGISTRY: v6.28.0のtest contributionがzero_diff_guard_registry.pyへ
#     O(1)で反映されていること（src/article_media_upload_stateはPROTECTED_PATHS
#     対象外のためsource contributionは不要。v6.27.0 REGISTRY-1〜13と同型の
#     最小パターンのみを検証する） ───

print("[テスト9] REGISTRY: v6.28.0 contributionのO(1)反映")

# REGISTRY-1/2は、v6.27.0自身のE2Eで発見・修正したのと同型の
# 「自分が永遠にRELEASE_ORDERの末尾である」というover-constraintを
# 再導入しないよう、当初からratchet-safe契約（存在確認＋自分までの
# prefix完全一致。v6.29.0以降のappendは対象外として許容）で書く。
check_true("REGISTRY-1. v6.28.0がRELEASE_ORDERに存在する（v6.29.0以降のappendを妨げない）",
           "v6.28.0" in registry.RELEASE_ORDER)
_v628_prefix_index = registry.release_index("v6.28.0")
check(
    "REGISTRY-2. v6.28.0までのprefixがv6.28.0リリース時点の期待順序と完全一致する"
    "（過去の削除・並べ替え・途中挿入は検知しつつ、v6.28.0より後へのfuture release"
    "appendは許容するratchet-safe契約）",
    registry.RELEASE_ORDER[: _v628_prefix_index + 1],
    ("v6.21.0", "v6.22.0", "v6.23.0", "v6.24.0", "v6.25.0", "v6.26.0", "v6.27.0", "v6.28.0"),
)

check("REGISTRY-3. BASELINE_COMMITSがv6.28.0を新規登録していない（新しいbaseline-fixed guardを新設しない）",
      set(registry.BASELINE_COMMITS.keys()),
      {"v6.21.0", "v6.22.0", "v6.23.0", "v6.24.0", "v6.25.0"})

# REGISTRY-4修正（Release Review Major-1対応。REGISTRY-1/2と同型の
# over-constraintだった）: 元実装は共有・追記可能な_SOURCE_CHANGE_CONTRIBUTIONS
# 全体を現在値と完全一致で凍結しており、v6.29以降が正当な新規source
# contributionを1件でも追加すると機械的にFAILしていた。
# 「v6.27.0までに確定していたsource contributionが変更・削除・並べ替え
# されていない」（4a、ratchet-safe：boundaryはv6.27.0のindexで区切り、
# それより後のthreshold（v6.29以降）は対象外として許容する）と、
# 「v6.28.0自身が直接登録したsource contributionは0件である」（4b、新規
# packageがPROTECTED_PATHS対象外のため）へ分離する。
_v627_boundary_index = registry.release_index("v6.27.0")
_historical_source_contributions = tuple(
    c for c in registry._SOURCE_CHANGE_CONTRIBUTIONS
    if registry.release_index(c[1]) <= _v627_boundary_index
)
check(
    "REGISTRY-4a. v6.27.0までに確定していたsource contributionが本Releaseで一切"
    "書き換わっていない（v6.29以降の正当な末尾appendはratchet-safeに対象外とする）",
    _historical_source_contributions,
    (
        ("src/wordpress_media", "v6.22.0", frozenset({
            "src/wordpress_media/__init__.py",
            "src/wordpress_media/wordpress_media_uploader.py",
        })),
        ("src/openai_image_generation", "v6.24.0", frozenset({
            "src/openai_image_generation/openai_image_generator.py",
        })),
        ("src/image_generation_fallback_policy", "v6.25.0", frozenset({
            "src/image_generation_fallback_policy/image_generation_fallback_policy.py",
            "src/image_generation_fallback_policy/__init__.py",
        })),
        ("src/article_featured_media_runtime", "v6.25.0", frozenset({
            "src/article_featured_media_runtime/article_featured_media_runtime.py",
            "src/article_featured_media_runtime/__init__.py",
        })),
        ("src/logger", "v6.25.0", frozenset({
            "src/logger/log_entry.py",
            "src/logger/log_manager.py",
        })),
        ("src/image_generation_config", "v6.27.0", frozenset({
            "src/image_generation_config/image_generation_config.py",
        })),
    ),
)
_v628_own_source = [c for c in registry._SOURCE_CHANGE_CONTRIBUTIONS if c[1] == "v6.28.0"]
check(
    "REGISTRY-4b. v6.28.0自身が直接登録したsource contributionは0件である"
    "（新規packageがPROTECTED_PATHS対象外のため）",
    len(_v628_own_source), 0,
)

_v628_own_tests = [
    name for name, threshold in registry._TEST_CHANGE_CONTRIBUTIONS if threshold == "v6.28.0"
]
check("REGISTRY-5. v6.28.0自身が直接登録したtest contributionがちょうど3件である",
      len(_v628_own_tests), 3)
check("REGISTRY-6. v6.28.0のtest contributionが新規E2E自身・zero_diff_guard_registry.py自身・"
      "（future-fragileだったREGISTRY-1/2をratchet-safe契約へ修正した）"
      "test_e2e_v6_27_0_*.py自身の3件のみである（生record参照。将来Releaseの寄与とは独立に"
      "恒久的に安定する）",
      set(_v628_own_tests),
      {
          "test_e2e_v6_28_0_article_media_upload_state_foundation.py",
          "zero_diff_guard_registry.py",
          "test_e2e_v6_27_0_image_generation_gate_value_validation_foundation.py",
      })

# REGISTRY-7修正（Release Review Major-1対応。REGISTRY-4と同型のover-constraint
# だった）: 元実装は`threshold != "v6.28.0"`でfilterしており、v6.29以降が
# 新規test contributionを追加すると（そのthresholdも"v6.28.0"ではないため）
# 過去snapshotへ取り込まれてしまい機械的にFAILしていた。boundaryを
# release_index("v6.27.0")で明示的に区切り、「v6.27.0までに確定していた
# recordだけ」を対象とすることで、v6.29以降の正当な末尾appendを構造的に
# 対象外とするratchet-safe判定へ変更する。
_v627_boundary_index_for_tests = registry.release_index("v6.27.0")
_pre_v628_tests = frozenset(
    (name, threshold)
    for name, threshold in registry._TEST_CHANGE_CONTRIBUTIONS
    if registry.release_index(threshold) <= _v627_boundary_index_for_tests
)
_pre_v628_tests_expected = frozenset({
    ("test_e2e_v6_13_0_article_featured_media_binding_foundation.py", "v6.21.0"),
    ("test_e2e_v6_9_0_wordpress_media_upload_foundation.py", "v6.22.0"),
    ("test_e2e_v6_19_0_image_generation_fallback_policy_foundation.py", "v6.24.0"),
    ("test_e2e_v6_20_0_article_featured_media_runtime_foundation.py", "v6.25.0"),
    ("test_e2e_v6_21_0_article_featured_media_runtime_wiring.py", "v6.24.0"),
    (
        "test_e2e_v6_22_0_wordpress_media_upload_failure_reason_classification_foundation.py",
        "v6.24.0",
    ),
    ("test_e2e_v6_11_0_openai_image_generation_adapter_foundation.py", "v6.24.0"),
    (
        "test_e2e_v6_23_0_openai_image_generation_api_rejection_reason_classification_foundation.py",
        "v6.24.0",
    ),
    (
        "test_e2e_v6_24_0_openai_image_generation_unknown_and_invalid_response_reason_"
        "refinement_foundation.py",
        "v6.24.0",
    ),
    ("test_e2e_v6_25_0_image_generation_fallback_observability_foundation.py", "v6.25.0"),
    ("zero_diff_guard_registry.py", "v6.26.0"),
    ("test_e2e_v6_26_0_zero_diff_guard_registry_foundation.py", "v6.26.0"),
    ("test_e2e_v6_21_0_article_featured_media_runtime_wiring.py", "v6.26.0"),
    (
        "test_e2e_v6_22_0_wordpress_media_upload_failure_reason_classification_foundation.py",
        "v6.26.0",
    ),
    (
        "test_e2e_v6_23_0_openai_image_generation_api_rejection_reason_classification_foundation.py",
        "v6.26.0",
    ),
    (
        "test_e2e_v6_24_0_openai_image_generation_unknown_and_invalid_response_reason_"
        "refinement_foundation.py",
        "v6.26.0",
    ),
    ("test_e2e_v6_15_0_image_generation_configuration_gate.py", "v6.27.0"),
    ("zero_diff_guard_registry.py", "v6.27.0"),
    ("test_e2e_v6_26_0_zero_diff_guard_registry_foundation.py", "v6.27.0"),
    ("test_e2e_v6_27_0_image_generation_gate_value_validation_foundation.py", "v6.27.0"),
})
check("REGISTRY-7. v6.21.0〜v6.27.0で確定済みのtest contribution recordが本Releaseで一切書き換わっていない"
      "（append-only。v6.29以降の正当な末尾appendはratchet-safeに対象外とする）",
      _pre_v628_tests, _pre_v628_tests_expected)

# REGISTRY-8: v6.28.0のtest contributionが、v6.21.0〜v6.27.0いずれの視点からの
# windowへもO(1)で波及している（membership。将来Releaseの正当な追加を妨げない
# 部分集合判定。REGISTRY-9/10と同型）。
for _rel in ("v6.21.0", "v6.22.0", "v6.23.0", "v6.24.0", "v6.25.0", "v6.26.0", "v6.27.0"):
    _allowed_tests_v628 = registry.allowed_test_changes_for(_rel)
    check_true(
        f"REGISTRY-8[{_rel}]. {_rel}視点のtest allow-listへtest_e2e_v6_28_0_*.pyの寄与がO(1)で波及している",
        "test_e2e_v6_28_0_article_media_upload_state_foundation.py" in _allowed_tests_v628,
    )
    check_true(
        f"REGISTRY-8[{_rel}]. {_rel}視点のtest allow-listへzero_diff_guard_registry.pyの寄与がO(1)で波及している",
        "zero_diff_guard_registry.py" in _allowed_tests_v628,
    )
    check_true(
        f"REGISTRY-8[{_rel}]. {_rel}視点のtest allow-listへtest_e2e_v6_27_0_*.pyの寄与がO(1)で波及している",
        "test_e2e_v6_27_0_image_generation_gate_value_validation_foundation.py" in _allowed_tests_v628,
    )

# REGISTRY-9修正（Release Review Major-1対応。REGISTRY-4/7と同型の
# over-constraintだった）: 元実装は`allowed_test_changes_for("v6.28.0")`
# （v6.28.0自身を含む未来すべてのwindow）が自身の3件のみとの完全一致で
# 固定されていた。v6.29.0がRELEASE_ORDERへ追記されると、v6.29.0の寄与も
# release_index上はv6.28.0以降のためv6.28.0視点のwindowへ算入され、
# 完全一致が機械的に崩れる（REGISTRY-9/13で確立したmembership判定パターンと
# 揃える）。「v6.28.0自身が直接登録した3件が必ずwindow内に存在する」という
# 部分集合判定へ変更し、future release contributionの追加でもPASSするように
# する。
_v628_own_test_set = frozenset({
    "test_e2e_v6_28_0_article_media_upload_state_foundation.py",
    "zero_diff_guard_registry.py",
    "test_e2e_v6_27_0_image_generation_gate_value_validation_foundation.py",
})
check_true(
    "REGISTRY-9. v6.28.0視点のtest allow-listに、v6.28.0自身が直接登録した3件が"
    "必ず含まれている（membership判定。future releaseの正当な追加寄与があってもPASSする）",
    _v628_own_test_set <= registry.allowed_test_changes_for("v6.28.0"),
)

# RATCHET: v6.21.0〜v6.28.0の連鎖でtest allow-listが単調非増加であることを
# 確認する（window semantics自体は本Releaseで変更していないことの確認）。
_ratchet_chain_v628 = [
    "v6.21.0", "v6.22.0", "v6.23.0", "v6.24.0", "v6.25.0", "v6.26.0", "v6.27.0", "v6.28.0",
]
for _earlier, _later in zip(_ratchet_chain_v628, _ratchet_chain_v628[1:]):
    _earlier_test_v628 = registry.allowed_test_changes_for(_earlier)
    _later_test_v628 = registry.allowed_test_changes_for(_later)
    check_true(
        f"REGISTRY-10[{_earlier}->{_later}]. test allow-listが単調非増加である（GR-9 ratchet維持）",
        _later_test_v628 <= _earlier_test_v628,
    )

print()


# ─── 結果サマリー ───
print("=" * 60)
total = len(results_log)
passed = sum(1 for status, _ in results_log if status == "PASS")
failed = total - passed
print(f"合計: {passed}/{total} PASS  /  {failed} FAIL")
print("=" * 60)

if failed > 0:
    print()
    print("FAILしたテスト:")
    for status, label in results_log:
        if status == "FAIL":
            print(f"  - {label}")
    sys.exit(1)
else:
    print("全テスト PASS")
