"""
E2E テスト: v6.8.0 Retry Notification CLI Report Wiring Foundation

テストシナリオ（docs/design/retry_notification_cli_report_wiring_foundation.md 対応、
承認済みTest Design 30 Scenario）:

    ── Public Model／Public API ──
    PM-1  RetryNotificationCliReport Contract（frozen dataclass・5フィールド・型・責務なし）
    PM-2  build_report／format_report／main のシグネチャ、__all__非漏洩

    ── Pipeline統合 ──
    PI-1  Empty Log Pipeline（HEALTHY→NONE→NO_NOTIFICATION、実Builder）
    PI-2  Non-empty HEALTHY Pipeline（複数Record集計・期間Pass-through）
    PI-3  DEGRADED Pipeline（実Builder、正式固定Message）
    PI-4  UNHEALTHY Pipeline（実Builder、正式固定Message、PI-3との収束確認）
    PI-5  Message Builder Call Contract（Counter Fake、PI-5A：NO_NOTIFICATION／PI-5B：NOTIFY）

    ── File／Reader Contract ──
    FR-1  File Not Found
    FR-2  Empty File
    FR-3  Partial Invalid JSON
    FR-4  All Invalid JSON
    FR-5  Missing Field／Type Error
    FR-6  Unreadable Path

    ── Exception／Exit Code ──
    EX-1  ValueError（Fake Evaluator）
    EX-2  RuntimeError（Fake Evaluator、非捕捉確認）
    EX-3  argparse Error

    ── Output Contract ──
    OUT-1  NOTIFY Report Structure
    OUT-2  Metrics Value Formatting
    OUT-3  Ratio Boundaries
    OUT-4  Empty／NO_NOTIFICATION Report
    OUT-5  Newline Contract

    ── CLI Argument／Default Path ──
    CLI-1  Argument／Default Path
    CLI-2  CWD Independence

    ── Dependency Direction ──
    DEP-1  CLI Import Direction（AST）
    DEP-2  Reverse Dependency Absence

    ── I/O Guard ──
    IO-1  Forbidden I/O／External Dependencies（AST）

    ── Pure Function ──
    PF-1  format_report Pure Function（振る舞い＋AST）

    ── Subprocess ──
    SP-1  Subprocess Success
    SP-2  Subprocess argparse Error
    SP-3  Subprocess OSError

Working Tree／git diff状態は恒久E2Eへ含めない。既存production code無改修の確認は
Release Review時にGitコマンドで行う。

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_8_0_retry_notification_cli_report_wiring_foundation.py
"""
from __future__ import annotations

import ast
import atexit
import contextlib
import importlib.util
import inspect
import io
import os
import subprocess
import sys
import tempfile
import typing
from contextlib import contextmanager
from dataclasses import FrozenInstanceError, fields, is_dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

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


def check_not_contains(label: str, text: str, keyword: str):
    check(label, keyword not in str(text), True)


print("=" * 60)
print("v6.8.0 Retry Notification CLI Report Wiring Foundation E2E テスト")
print("=" * 60)
print()

# ─── 既存Foundation（Fixture構築・比較のため直接import） ───

from retry_alert import RetryAlert, RetryAlertLevel
from retry_metrics import RetryMetricsSnapshot
from retry_monitoring import RetryHealthReport, RetryHealthStatus
from retry_notification import RetryNotificationDecision, RetryNotificationStatus
from retry_notification_message import RetryNotificationMessage

import retry_alert as retry_alert_pkg
import retry_metrics as retry_metrics_pkg
import retry_monitoring as retry_monitoring_pkg
import retry_notification as retry_notification_pkg
import retry_notification_message as retry_notification_message_pkg

EXPECTED_NOTIFICATION_MESSAGE_BODY = (
    "Retry Runtimeで通知対象の状態が検出されました。詳細を確認してください。"
)

# ─── CLIモジュールロード（sys.modules安全登録） ───

SCRIPT_PATH = PROJECT_ROOT / "scripts" / "show_retry_notification.py"
MODULE_NAME = "show_retry_notification_v6_8_e2e"

check_true("0. show_retry_notification.py が存在する", SCRIPT_PATH.exists())

spec = importlib.util.spec_from_file_location(MODULE_NAME, SCRIPT_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("show_retry_notification.pyをロードできません")

show_retry_notification = importlib.util.module_from_spec(spec)

_previous_module = sys.modules.get(MODULE_NAME)
sys.modules[MODULE_NAME] = show_retry_notification

try:
    spec.loader.exec_module(show_retry_notification)
except Exception:
    if _previous_module is None:
        sys.modules.pop(MODULE_NAME, None)
    else:
        sys.modules[MODULE_NAME] = _previous_module
    raise

RetryNotificationCliReport = show_retry_notification.RetryNotificationCliReport
build_report = show_retry_notification.build_report
format_report = show_retry_notification.format_report
main = show_retry_notification.main


def _restore_sys_modules() -> None:
    """
    sys.modules[MODULE_NAME] を元の状態へ復元する。手動復元（スクリプト末尾）に加え、
    Scenario実行中に予期しない例外でスクリプトが異常終了した場合でも復元が保証されるよう
    atexitへ登録する（複数回呼ばれても冪等）。
    """
    if _previous_module is None:
        sys.modules.pop(MODULE_NAME, None)
    else:
        sys.modules[MODULE_NAME] = _previous_module


atexit.register(_restore_sys_modules)


# ─── Fixture Helper ───


def make_record_dict(
    cycle_number: int,
    timestamp: str,
    enqueue_scanned: int,
    enqueue_enqueued: int,
    dry_run: bool = False,
) -> dict:
    """有効な1レコード分のdictを返す。Calculatorの計算ロジックはコピーしない。"""
    return {
        "cycle_number": cycle_number,
        "timestamp": timestamp,
        "dry_run": dry_run,
        "enqueue_scanned": enqueue_scanned,
        "enqueue_enqueued": enqueue_enqueued,
        "enqueue_skipped_existing": 0,
        "enqueue_skipped_status": 0,
        "enqueue_skipped_history": 0,
        "enqueue_failed": 0,
        "scheduler_candidates": 0,
        "execution_executed": 0,
        "removal_removed": 0,
        "cleanup_cleaned": 0,
        "terminal_cleanup_cleaned": 0,
        "history_recorded": 0,
    }


def write_jsonl(path: Path, lines: list[str]) -> None:
    """生の行（有効JSON文字列・不正文字列いずれも可）をそのままJSONLとして書き込む。1行以上のFixture専用。"""
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_unreadable_path(tmp_dir: Path) -> Path:
    """ディレクトリそのものをlog_pathとして渡すことで確定的にOSErrorを誘発する。"""
    unreadable = tmp_dir / "not_a_file"
    unreadable.mkdir()
    return unreadable


def make_snapshot(
    cycle_count: int,
    period_start,
    period_end,
    ratio,
) -> RetryMetricsSnapshot:
    """OUT系Scenario用に、表示対象4フィールド以外を0で埋めたSnapshotを構築する。"""
    return RetryMetricsSnapshot(
        cycle_count=cycle_count,
        period_start=period_start,
        period_end=period_end,
        dry_run_cycle_count=0,
        enqueue_scanned_total=0,
        enqueue_enqueued_total=0,
        enqueue_skipped_existing_total=0,
        enqueue_skipped_status_total=0,
        enqueue_skipped_history_total=0,
        enqueue_failed_total=0,
        scheduler_candidates_total=0,
        execution_executed_total=0,
        removal_removed_total=0,
        cleanup_cleaned_total=0,
        terminal_cleanup_cleaned_total=0,
        history_recorded_total=0,
        enqueue_success_ratio=ratio,
    )


@contextmanager
def patched_attr(module, name: str, fake_value):
    original = getattr(module, name)
    setattr(module, name, fake_value)
    try:
        yield
    finally:
        setattr(module, name, original)


def make_raising_evaluator(exc_factory):
    """evaluate() が exc_factory() の例外を送出する、無引数コンストラクタのFakeクラスを返す。"""

    class _RaisingEvaluator:
        def evaluate(self, _input):
            raise exc_factory()

    return _RaisingEvaluator


class CountingMessageBuilder:
    last_instance = None

    def __init__(self):
        self.calls = 0
        self.decisions = []
        type(self).last_instance = self

    def build(self, decision):
        self.calls += 1
        self.decisions.append(decision)
        return RetryNotificationMessage(body="fake body")


def extract_section(text: str, header: str, next_headers: list[str]) -> str:
    """textからheader直後〜次のheaderまでの範囲を切り出す（セクション内ラベル検証用）。"""
    start = text.index(header) + len(header)
    end = len(text)
    for nh in next_headers:
        idx = text.find(nh, start)
        if idx != -1:
            end = min(end, idx)
    return text[start:end]


# ─── AST Helper ───


def parse_module_ast(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def collect_import_names(tree: ast.AST) -> set:
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])
    return names


def collect_from_import_modules(tree: ast.AST) -> set:
    """ImportFrom.module の完全な文字列（サブモジュール含む）の集合を返す。"""
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _dotted_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted_name(node.value)
        if base is None:
            return None
        return f"{base}.{node.attr}"
    return None


def collect_call_dotted_names(tree: ast.AST) -> set:
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            dotted = _dotted_name(node.func)
            if dotted is not None:
                names.add(dotted)
    return names


def collect_call_attrs(tree: ast.AST) -> set:
    """Attribute呼び出し（x.method(...)）の最終属性名（メソッド名）の集合。"""
    attrs = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            attrs.add(node.func.attr)
    return attrs


def collect_attribute_dotted_names(tree: ast.AST) -> set:
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            dotted = _dotted_name(node)
            if dotted is not None:
                names.add(dotted)
    return names


def find_function_def(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise ValueError(f"関数定義が見つかりません: {name}")


CLI_SOURCE = SCRIPT_PATH.read_text(encoding="utf-8")
CLI_TREE = parse_module_ast(SCRIPT_PATH)


# ═══════════════════════════════════════════════════════════
# PM-1: Public Model Contract
# ═══════════════════════════════════════════════════════════
print("[PM-1] RetryNotificationCliReport Contract")

check_true("PM-1: dataclassである", is_dataclass(RetryNotificationCliReport))

_sample_metrics = make_snapshot(1, "2026-07-14T00:00:00+00:00", "2026-07-14T00:00:00+00:00", 1.0)
_sample_health = RetryHealthReport(status=RetryHealthStatus.HEALTHY)
_sample_alert = RetryAlert(level=RetryAlertLevel.NONE)
_sample_decision = RetryNotificationDecision(status=RetryNotificationStatus.NO_NOTIFICATION)
_sample_report = RetryNotificationCliReport(
    metrics=_sample_metrics,
    health_report=_sample_health,
    alert=_sample_alert,
    notification_decision=_sample_decision,
    message=None,
)

try:
    _sample_report.message = RetryNotificationMessage(body="x")
    _raised_frozen_error = False
except FrozenInstanceError:
    _raised_frozen_error = True
check_true("PM-1: frozen（FrozenInstanceError）", _raised_frozen_error)

_field_names = [f.name for f in fields(RetryNotificationCliReport)]
check(
    "PM-1: フィールド名・順序が5つ",
    _field_names,
    ["metrics", "health_report", "alert", "notification_decision", "message"],
)

_hints = typing.get_type_hints(RetryNotificationCliReport)
check_true("PM-1: metrics型がRetryMetricsSnapshot", _hints["metrics"] is RetryMetricsSnapshot)
check_true("PM-1: health_report型がRetryHealthReport", _hints["health_report"] is RetryHealthReport)
check_true("PM-1: alert型がRetryAlert", _hints["alert"] is RetryAlert)
check_true(
    "PM-1: notification_decision型がRetryNotificationDecision",
    _hints["notification_decision"] is RetryNotificationDecision,
)
_message_args = typing.get_args(_hints["message"])
check_true("PM-1: message型にRetryNotificationMessageを含む", RetryNotificationMessage in _message_args)
check_true("PM-1: message型にNoneTypeを含む", type(None) in _message_args)

_report_a = RetryNotificationCliReport(
    metrics=_sample_metrics,
    health_report=_sample_health,
    alert=_sample_alert,
    notification_decision=_sample_decision,
    message=None,
)
_report_b = RetryNotificationCliReport(
    metrics=_sample_metrics,
    health_report=_sample_health,
    alert=_sample_alert,
    notification_decision=_sample_decision,
    message=None,
)
check_true("PM-1: equality（同一値）", _report_a == _report_b)
_report_c = RetryNotificationCliReport(
    metrics=_sample_metrics,
    health_report=_sample_health,
    alert=_sample_alert,
    notification_decision=_sample_decision,
    message=RetryNotificationMessage(body="different"),
)
check_true("PM-1: equality（異なる値はnot equal）", _report_a != _report_c)

for _forbidden in ("build", "evaluate", "format", "run", "execute", "send", "notify"):
    check_false(
        f"PM-1: {_forbidden}() が定義されていない（責務なし）",
        hasattr(RetryNotificationCliReport, _forbidden),
    )
print()


# ═══════════════════════════════════════════════════════════
# PM-2: Public Function Signatures／__all__非漏洩
# ═══════════════════════════════════════════════════════════
print("[PM-2] Public Function Signatures／__all__非漏洩")

_build_report_sig = inspect.signature(build_report)
check("PM-2: build_reportのパラメータ", list(_build_report_sig.parameters.keys()), ["log_path"])
_build_report_hints = typing.get_type_hints(build_report)
check_true("PM-2: build_report引数型がPath", _build_report_hints["log_path"] is Path)
check_true(
    "PM-2: build_report戻り値型がRetryNotificationCliReport",
    _build_report_hints["return"] is RetryNotificationCliReport,
)

_format_report_sig = inspect.signature(format_report)
check("PM-2: format_reportのパラメータ", list(_format_report_sig.parameters.keys()), ["report"])
_format_report_hints = typing.get_type_hints(format_report)
check_true(
    "PM-2: format_report引数型がRetryNotificationCliReport",
    _format_report_hints["report"] is RetryNotificationCliReport,
)
check_true("PM-2: format_report戻り値型がstr", _format_report_hints["return"] is str)

_main_sig = inspect.signature(main)
check("PM-2: mainのパラメータ", list(_main_sig.parameters.keys()), ["argv"])
check("PM-2: argvのデフォルト値がNone", _main_sig.parameters["argv"].default, None)
_main_hints = typing.get_type_hints(main)
check_true("PM-2: main戻り値型がint", _main_hints["return"] is int)

check_false("PM-2: CLIモジュールに__all__がない", hasattr(show_retry_notification, "__all__"))

for _pkg, _pkg_name in (
    (retry_metrics_pkg, "retry_metrics"),
    (retry_monitoring_pkg, "retry_monitoring"),
    (retry_alert_pkg, "retry_alert"),
    (retry_notification_pkg, "retry_notification"),
    (retry_notification_message_pkg, "retry_notification_message"),
):
    check_false(
        f"PM-2: {_pkg_name}.__all__ にCLI型が漏洩していない",
        "RetryNotificationCliReport" in _pkg.__all__,
    )
print()


# ═══════════════════════════════════════════════════════════
# PI-1: Empty Log Pipeline
# ═══════════════════════════════════════════════════════════
print("[PI-1] Empty Log Pipeline")

with tempfile.TemporaryDirectory() as _tmp:
    _missing_path = Path(_tmp) / "does_not_exist.jsonl"
    _pi1_report = build_report(_missing_path)

check("PI-1: cycle_count == 0", _pi1_report.metrics.cycle_count, 0)
check_true("PI-1: HEALTHY", _pi1_report.health_report.status is RetryHealthStatus.HEALTHY)
check_true("PI-1: NONE", _pi1_report.alert.level is RetryAlertLevel.NONE)
check_true(
    "PI-1: NO_NOTIFICATION",
    _pi1_report.notification_decision.status is RetryNotificationStatus.NO_NOTIFICATION,
)
check_true("PI-1: message is None", _pi1_report.message is None)
print()


# ═══════════════════════════════════════════════════════════
# PI-2: Non-empty HEALTHY Pipeline
# ═══════════════════════════════════════════════════════════
print("[PI-2] Non-empty HEALTHY Pipeline（複数Record集計・期間Pass-through）")

_pi2_ts1 = "2026-07-14T00:00:00+00:00"
_pi2_ts2 = "2026-07-15T00:00:00+00:00"
with tempfile.TemporaryDirectory() as _tmp:
    _healthy_path = Path(_tmp) / "healthy.jsonl"
    import json as _json

    write_jsonl(
        _healthy_path,
        [
            _json.dumps(make_record_dict(1, _pi2_ts1, enqueue_scanned=3, enqueue_enqueued=2)),
            _json.dumps(make_record_dict(2, _pi2_ts2, enqueue_scanned=3, enqueue_enqueued=3)),
        ],
    )
    _pi2_report = build_report(_healthy_path)

check("PI-2: cycle_count == 2", _pi2_report.metrics.cycle_count, 2)
check("PI-2: period_start == 最小timestamp", _pi2_report.metrics.period_start, _pi2_ts1)
check("PI-2: period_end == 最大timestamp", _pi2_report.metrics.period_end, _pi2_ts2)
check_true(
    "PI-2: ratio == 5/6",
    abs(_pi2_report.metrics.enqueue_success_ratio - (5 / 6)) < 1e-9,
)
check_true("PI-2: HEALTHY", _pi2_report.health_report.status is RetryHealthStatus.HEALTHY)
check_true(
    "PI-2: NO_NOTIFICATION",
    _pi2_report.notification_decision.status is RetryNotificationStatus.NO_NOTIFICATION,
)
check_true("PI-2: message is None", _pi2_report.message is None)
print()


# ═══════════════════════════════════════════════════════════
# PI-3: DEGRADED Pipeline（実Builder）
# ═══════════════════════════════════════════════════════════
print("[PI-3] DEGRADED Pipeline（実Builder、正式固定Message）")


def _write_single_record_log(path: Path, scanned: int, enqueued: int) -> None:
    import json as _json

    write_jsonl(
        path,
        [_json.dumps(make_record_dict(1, "2026-07-14T00:00:00+00:00", enqueue_scanned=scanned, enqueue_enqueued=enqueued))],
    )


with tempfile.TemporaryDirectory() as _tmp:
    _degraded_path = Path(_tmp) / "degraded.jsonl"
    _write_single_record_log(_degraded_path, scanned=10, enqueued=6)
    degraded_report = build_report(_degraded_path)

check_true(
    "PI-3: ratio == 0.6",
    abs(degraded_report.metrics.enqueue_success_ratio - 0.6) < 1e-9,
)
check_true("PI-3: DEGRADED", degraded_report.health_report.status is RetryHealthStatus.DEGRADED)
check_true("PI-3: WARNING", degraded_report.alert.level is RetryAlertLevel.WARNING)
check_true(
    "PI-3: NOTIFY",
    degraded_report.notification_decision.status is RetryNotificationStatus.NOTIFY,
)
check_true("PI-3: message is not None", degraded_report.message is not None)
check(
    "PI-3: message.body == 正式固定Message",
    degraded_report.message.body,
    EXPECTED_NOTIFICATION_MESSAGE_BODY,
)
print()


# ═══════════════════════════════════════════════════════════
# PI-4: UNHEALTHY Pipeline（実Builder）
# ═══════════════════════════════════════════════════════════
print("[PI-4] UNHEALTHY Pipeline（実Builder、正式固定Message、収束確認）")

with tempfile.TemporaryDirectory() as _tmp:
    _unhealthy_path = Path(_tmp) / "unhealthy.jsonl"
    _write_single_record_log(_unhealthy_path, scanned=10, enqueued=3)
    unhealthy_report = build_report(_unhealthy_path)

check_true(
    "PI-4: ratio == 0.3",
    abs(unhealthy_report.metrics.enqueue_success_ratio - 0.3) < 1e-9,
)
check_true("PI-4: UNHEALTHY", unhealthy_report.health_report.status is RetryHealthStatus.UNHEALTHY)
check_true("PI-4: CRITICAL", unhealthy_report.alert.level is RetryAlertLevel.CRITICAL)
check_true(
    "PI-4: NOTIFY",
    unhealthy_report.notification_decision.status is RetryNotificationStatus.NOTIFY,
)
check_true("PI-4: message is not None", unhealthy_report.message is not None)
check(
    "PI-4: message.body == 正式固定Message",
    unhealthy_report.message.body,
    EXPECTED_NOTIFICATION_MESSAGE_BODY,
)
check(
    "PI-4: WARNING/CRITICALが同一Messageへ収束（実Builder）",
    unhealthy_report.message.body,
    degraded_report.message.body,
)
print()


# ═══════════════════════════════════════════════════════════
# PI-5: Message Builder Call Contract（Counter Fake）
# ═══════════════════════════════════════════════════════════
print("[PI-5A] Message Builder Call Contract - NO_NOTIFICATION側")

CountingMessageBuilder.last_instance = None
with tempfile.TemporaryDirectory() as _tmp:
    _missing_path = Path(_tmp) / "does_not_exist.jsonl"
    with patched_attr(show_retry_notification, "RetryNotificationMessageBuilder", CountingMessageBuilder):
        _pi5a_report = build_report(_missing_path)

_pi5a_instance = CountingMessageBuilder.last_instance
check_true("PI-5A: instance is not None", _pi5a_instance is not None)
check("PI-5A: calls == 0", _pi5a_instance.calls, 0)
check("PI-5A: decisions == []", _pi5a_instance.decisions, [])
check_true(
    "PI-5A: NO_NOTIFICATION",
    _pi5a_report.notification_decision.status is RetryNotificationStatus.NO_NOTIFICATION,
)
check_true("PI-5A: message is None", _pi5a_report.message is None)
CountingMessageBuilder.last_instance = None
print()


print("[PI-5B] Message Builder Call Contract - NOTIFY側")

CountingMessageBuilder.last_instance = None
with tempfile.TemporaryDirectory() as _tmp:
    _degraded_path_5b = Path(_tmp) / "degraded.jsonl"
    _write_single_record_log(_degraded_path_5b, scanned=10, enqueued=6)
    with patched_attr(show_retry_notification, "RetryNotificationMessageBuilder", CountingMessageBuilder):
        _pi5b_report = build_report(_degraded_path_5b)

_pi5b_instance = CountingMessageBuilder.last_instance
check_true("PI-5B: instance is not None", _pi5b_instance is not None)
check("PI-5B: calls == 1", _pi5b_instance.calls, 1)
check("PI-5B: len(decisions) == 1", len(_pi5b_instance.decisions), 1)
check_true(
    "PI-5B: decisions[0] is report.notification_decision（object identity）",
    _pi5b_instance.decisions[0] is _pi5b_report.notification_decision,
)
check_true("PI-5B: message is not None", _pi5b_report.message is not None)
check("PI-5B: message.body == 'fake body'", _pi5b_report.message.body, "fake body")
CountingMessageBuilder.last_instance = None
print()


# ═══════════════════════════════════════════════════════════
# FR-1〜FR-6: File／Reader Contract
# ═══════════════════════════════════════════════════════════
print("[FR-1] File Not Found")

with tempfile.TemporaryDirectory() as _tmp:
    _missing_path = Path(_tmp) / "missing.jsonl"
    _stdout_buf, _stderr_buf = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(_stdout_buf), contextlib.redirect_stderr(_stderr_buf):
        _rc = main(["--log-path", str(_missing_path)])
check("FR-1: 戻り値0", _rc, 0)
check_contains("FR-1: stdoutにタイトル", _stdout_buf.getvalue(), "Retry Notification Report")
check("FR-1: stderrが空", _stderr_buf.getvalue(), "")
print()


print("[FR-2] Empty File")

with tempfile.TemporaryDirectory() as _tmp:
    _empty_path = Path(_tmp) / "empty.jsonl"
    _empty_path.write_text("", encoding="utf-8")
    _stdout_buf, _stderr_buf = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(_stdout_buf), contextlib.redirect_stderr(_stderr_buf):
        _rc = main(["--log-path", str(_empty_path)])
check("FR-2: 戻り値0", _rc, 0)
check_contains("FR-2: stdoutにタイトル", _stdout_buf.getvalue(), "Retry Notification Report")
check("FR-2: stderrが空", _stderr_buf.getvalue(), "")
print()


print("[FR-3] Partial Invalid JSON")

with tempfile.TemporaryDirectory() as _tmp:
    import json as _json

    _partial_path = Path(_tmp) / "partial.jsonl"
    write_jsonl(
        _partial_path,
        [
            _json.dumps(make_record_dict(1, "2026-07-14T00:00:00+00:00", enqueue_scanned=5, enqueue_enqueued=5)),
            "{not valid json",
            "",
        ],
    )
    _stdout_buf, _stderr_buf = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(_stdout_buf), contextlib.redirect_stderr(_stderr_buf):
        _rc = main(["--log-path", str(_partial_path)])
_stdout_text, _stderr_text = _stdout_buf.getvalue(), _stderr_buf.getvalue()
check("FR-3: 戻り値0", _rc, 0)
check_contains("FR-3: 有効行のcycle_countがReportへ反映", _stdout_text, "対象サイクル数     : 1")
check("FR-3: WARNINGがちょうど1件", _stderr_text.count("WARNING:"), 1)
check_contains("FR-3: WARNING文言（プレフィックス）", _stderr_text, "WARNING: Failed to parse runtime log line 2:")
check_not_contains("FR-3: [ERROR]を含まない", _stderr_text, "[ERROR]")
check_not_contains("FR-3: Tracebackを含まない", _stderr_text, "Traceback")
print()


print("[FR-4] All Invalid JSON")

with tempfile.TemporaryDirectory() as _tmp:
    _all_invalid_path = Path(_tmp) / "all_invalid.jsonl"
    write_jsonl(_all_invalid_path, ["{not valid", "also not valid}"])
    _stdout_buf, _stderr_buf = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(_stdout_buf), contextlib.redirect_stderr(_stderr_buf):
        _rc = main(["--log-path", str(_all_invalid_path)])
_stdout_text, _stderr_text = _stdout_buf.getvalue(), _stderr_buf.getvalue()
check("FR-4: 戻り値0", _rc, 0)
check_contains("FR-4: cycle_count == 0", _stdout_text, "対象サイクル数     : 0")
check("FR-4: WARNINGが2件", _stderr_text.count("WARNING:"), 2)
print()


print("[FR-5] Missing Field／Type Error")

with tempfile.TemporaryDirectory() as _tmp:
    import json as _json

    _fr5_path = Path(_tmp) / "fr5.jsonl"
    _missing_key_record = make_record_dict(1, "2026-07-14T00:00:00+00:00", enqueue_scanned=1, enqueue_enqueued=1)
    del _missing_key_record["cycle_number"]
    write_jsonl(
        _fr5_path,
        [
            _json.dumps(_missing_key_record),
            "123",
        ],
    )
    _stdout_buf, _stderr_buf = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(_stdout_buf), contextlib.redirect_stderr(_stderr_buf):
        _rc = main(["--log-path", str(_fr5_path)])
_stdout_text, _stderr_text = _stdout_buf.getvalue(), _stderr_buf.getvalue()
check("FR-5: 戻り値0", _rc, 0)
check_contains("FR-5: cycle_count == 0", _stdout_text, "対象サイクル数     : 0")
check("FR-5: WARNINGが2件（KeyError＋TypeError）", _stderr_text.count("WARNING:"), 2)
print()


print("[FR-6] Unreadable Path")

with tempfile.TemporaryDirectory() as _tmp:
    _unreadable = make_unreadable_path(Path(_tmp))
    _stdout_buf, _stderr_buf = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(_stdout_buf), contextlib.redirect_stderr(_stderr_buf):
        _rc = main(["--log-path", str(_unreadable)])
_stdout_text, _stderr_text = _stdout_buf.getvalue(), _stderr_buf.getvalue()
check("FR-6: 戻り値1", _rc, 1)
check("FR-6: stdoutが空", _stdout_text, "")
check_contains("FR-6: stderrに[ERROR]", _stderr_text, "[ERROR]")
check_not_contains("FR-6: Tracebackを含まない", _stderr_text, "Traceback")
print()


# ═══════════════════════════════════════════════════════════
# EX-1〜EX-3: Exception／Exit Code Contract
# ═══════════════════════════════════════════════════════════
print("[EX-1] ValueError（Fake Evaluator）")

with tempfile.TemporaryDirectory() as _tmp:
    _missing_path = Path(_tmp) / "missing.jsonl"
    _raising_value_error = make_raising_evaluator(lambda: ValueError("fake unmapped status"))
    _stdout_buf, _stderr_buf = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(_stdout_buf), contextlib.redirect_stderr(_stderr_buf):
        with patched_attr(show_retry_notification, "RetryAlertEvaluator", _raising_value_error):
            _rc = main(["--log-path", str(_missing_path)])
_stdout_text, _stderr_text = _stdout_buf.getvalue(), _stderr_buf.getvalue()
check("EX-1: 戻り値1", _rc, 1)
check("EX-1: stdoutが空", _stdout_text, "")
check_contains("EX-1: stderrに[ERROR]", _stderr_text, "[ERROR]")
check_not_contains("EX-1: Tracebackを含まない", _stderr_text, "Traceback")
print()


print("[EX-2] RuntimeError（Fake Evaluator、非捕捉確認）")

with tempfile.TemporaryDirectory() as _tmp:
    _missing_path = Path(_tmp) / "missing.jsonl"
    _raising_runtime_error = make_raising_evaluator(lambda: RuntimeError("boom"))
    _propagated = False
    with patched_attr(show_retry_notification, "RetryAlertEvaluator", _raising_runtime_error):
        try:
            main(["--log-path", str(_missing_path)])
        except RuntimeError:
            _propagated = True
check_true("EX-2: RuntimeErrorがmain()から伝播（握り潰されない）", _propagated)
print()


print("[EX-3] argparse Error")

_stdout_buf, _stderr_buf = io.StringIO(), io.StringIO()
_system_exit_code = None
with contextlib.redirect_stdout(_stdout_buf), contextlib.redirect_stderr(_stderr_buf):
    try:
        main(["--unknown"])
    except SystemExit as exc:
        _system_exit_code = exc.code
check("EX-3: SystemExit(2)", _system_exit_code, 2)
check_not_contains("EX-3: stdoutに正常Reportなし", _stdout_buf.getvalue(), "Retry Notification Report")
print()


# ═══════════════════════════════════════════════════════════
# OUT-1〜OUT-5: Output Contract
# ═══════════════════════════════════════════════════════════
print("[OUT-1] NOTIFY Report Structure")

_out1_report = RetryNotificationCliReport(
    metrics=make_snapshot(6, "2026-07-14T00:00:00+00:00", "2026-07-15T00:00:00+00:00", 5 / 6),
    health_report=RetryHealthReport(status=RetryHealthStatus.DEGRADED),
    alert=RetryAlert(level=RetryAlertLevel.WARNING),
    notification_decision=RetryNotificationDecision(status=RetryNotificationStatus.NOTIFY),
    message=RetryNotificationMessage(body=EXPECTED_NOTIFICATION_MESSAGE_BODY),
)
_out1_text = format_report(_out1_report)

check_contains("OUT-1: タイトル", _out1_text, "Retry Notification Report")
check_true("OUT-1: 区切り線が50文字の'='", ("=" * 50) in _out1_text)
_out1_lines = _out1_text.split("\n")
check_true("OUT-1: 区切り線の実長が50文字", any(line == "=" * 50 and len(line) == 50 for line in _out1_lines))

_headers = ["[Metrics]", "[Health]", "[Alert]", "[Notification]", "[Message]"]
_indices = [_out1_text.index(h) for h in _headers]
check_true("OUT-1: セクション見出しの出現順序が単調増加", _indices == sorted(_indices))
for _h in _headers:
    check(f"OUT-1: 見出し{_h}が1回だけ出現", _out1_text.count(_h), 1)

check_contains("OUT-1: Enum .value表現（DEGRADED）", _out1_text, "DEGRADED")
check_not_contains("OUT-1: repr形式を含まない", _out1_text, "RetryHealthStatus.DEGRADED")
check_contains("OUT-1: NOTIFY Message本文", _out1_text, EXPECTED_NOTIFICATION_MESSAGE_BODY)
print()


print("[OUT-2] Metrics Value Formatting")

import re as _re

_out2_text = _out1_text  # OUT-1と同一Fixtureを再利用（cycle_count=6, ratio=5/6）

check_true(
    "OUT-2: cycle_countラベル＋半角コロン＋値",
    _re.search(r"対象サイクル数\s*:\s*6", _out2_text) is not None,
)
check_true(
    "OUT-2: period_startラベルと値が位置対応（無加工表示）",
    _re.search(r"記録開始\s*:\s*" + _re.escape("2026-07-14T00:00:00+00:00"), _out2_text) is not None,
)
check_true(
    "OUT-2: period_endラベルと値が位置対応（無加工表示）",
    _re.search(r"記録終了\s*:\s*" + _re.escape("2026-07-15T00:00:00+00:00"), _out2_text) is not None,
)
check_true(
    "OUT-2: ratioが0.83（小数第2位固定）",
    _re.search(r"Enqueue成功率\s*:\s*0\.83", _out2_text) is not None,
)
check_false("OUT-2: 全角コロンを許容しない（不使用の確認）", "：" in _out2_text)

_health_block = extract_section(_out2_text, "[Health]", ["[Alert]"])
_alert_block = extract_section(_out2_text, "[Alert]", ["[Notification]"])
_notification_block = extract_section(_out2_text, "[Notification]", ["[Message]"])
check_true(
    "OUT-2: Healthセクション内に'ステータス'ラベル＋値が位置対応",
    _re.search(r"ステータス\s*:\s*DEGRADED", _health_block) is not None,
)
check_true(
    "OUT-2: Alertセクション内に'レベル'ラベル＋値が位置対応",
    _re.search(r"レベル\s*:\s*WARNING", _alert_block) is not None,
)
check_true(
    "OUT-2: Notificationセクション内に'ステータス'ラベル＋値が位置対応",
    _re.search(r"ステータス\s*:\s*NOTIFY", _notification_block) is not None,
)
print()


print("[OUT-3] Ratio Boundaries")

_out3_zero_report = RetryNotificationCliReport(
    metrics=make_snapshot(1, "2026-07-14T00:00:00+00:00", "2026-07-14T00:00:00+00:00", 0.0),
    health_report=RetryHealthReport(status=RetryHealthStatus.UNHEALTHY),
    alert=RetryAlert(level=RetryAlertLevel.CRITICAL),
    notification_decision=RetryNotificationDecision(status=RetryNotificationStatus.NOTIFY),
    message=RetryNotificationMessage(body=EXPECTED_NOTIFICATION_MESSAGE_BODY),
)
_out3_one_report = RetryNotificationCliReport(
    metrics=make_snapshot(1, "2026-07-14T00:00:00+00:00", "2026-07-14T00:00:00+00:00", 1.0),
    health_report=RetryHealthReport(status=RetryHealthStatus.HEALTHY),
    alert=RetryAlert(level=RetryAlertLevel.NONE),
    notification_decision=RetryNotificationDecision(status=RetryNotificationStatus.NO_NOTIFICATION),
    message=None,
)
check_contains("OUT-3: ratio 0.0 -> '0.00'", format_report(_out3_zero_report), "0.00")
check_contains("OUT-3: ratio 1.0 -> '1.00'", format_report(_out3_one_report), "1.00")
print()


print("[OUT-4] Empty／NO_NOTIFICATION Report")

_out4_report = RetryNotificationCliReport(
    metrics=make_snapshot(0, None, None, None),
    health_report=RetryHealthReport(status=RetryHealthStatus.HEALTHY),
    alert=RetryAlert(level=RetryAlertLevel.NONE),
    notification_decision=RetryNotificationDecision(status=RetryNotificationStatus.NO_NOTIFICATION),
    message=None,
)
_out4_text = format_report(_out4_report)

check_true(
    "OUT-4: cycle_count 0",
    _re.search(r"対象サイクル数\s*:\s*0", _out4_text) is not None,
)
check_contains("OUT-4: period開始（記録なし）", _out4_text, "記録開始           : （記録なし）")
check_contains("OUT-4: period終了（記録なし）", _out4_text, "記録終了           : （記録なし）")
check_contains("OUT-4: ratio（算出不能）", _out4_text, "（算出不能）")
check_contains("OUT-4: 空ログ注記", _out4_text, "（Retry Runtimeの実行記録がありません）")
check_not_contains("OUT-4: cycle_count>0では注記なし（OUT-1で確認）", _out1_text, "（Retry Runtimeの実行記録がありません）")
check_contains("OUT-4: NO_NOTIFICATION固定文", _out4_text, "（通知対象ではないため、Messageは生成されません）")
print()


print("[OUT-5] Newline Contract")

check_false("OUT-5: format_report()戻り値に末尾改行なし", _out1_text.endswith("\n"))

with tempfile.TemporaryDirectory() as _tmp:
    _missing_path = Path(_tmp) / "missing.jsonl"
    _stdout_buf = io.StringIO()
    with contextlib.redirect_stdout(_stdout_buf):
        main(["--log-path", str(_missing_path)])
_main_stdout = _stdout_buf.getvalue()
check_true("OUT-5: main() stdout末尾改行が1つ", _main_stdout.endswith("\n") and not _main_stdout.endswith("\n\n"))
print()


# ═══════════════════════════════════════════════════════════
# CLI-1／CLI-2: CLI Argument／Default Path／CWD Independence
# ═══════════════════════════════════════════════════════════
print("[CLI-1] Argument／Default Path")


def _find_add_argument_type_path(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "add_argument":
            for kw in node.keywords:
                if kw.arg == "type" and isinstance(kw.value, ast.Name) and kw.value.id == "Path":
                    return True
    return False


check_true("CLI-1: --log-pathがtype=Path", _find_add_argument_type_path(CLI_TREE))

with tempfile.TemporaryDirectory() as _tmp:
    _explicit_path = Path(_tmp) / "explicit.jsonl"
    import json as _json

    write_jsonl(
        _explicit_path,
        [_json.dumps(make_record_dict(1, "2026-07-14T00:00:00+00:00", enqueue_scanned=1, enqueue_enqueued=1))],
    )
    _explicit_report = build_report(_explicit_path)
check("CLI-1: 明示指定Pathが反映（cycle_count==1）", _explicit_report.metrics.cycle_count, 1)

check(
    "CLI-1: _DEFAULT_LOG_PATH が project_root/.run/retry_runtime_log.jsonl",
    show_retry_notification._DEFAULT_LOG_PATH,
    show_retry_notification._PROJECT_ROOT / ".run" / "retry_runtime_log.jsonl",
)
check(
    "CLI-1: _PROJECT_ROOT がスクリプト位置基準",
    show_retry_notification._PROJECT_ROOT,
    SCRIPT_PATH.parent.parent,
)

_cli_import_names = collect_import_names(CLI_TREE)
check_false("CLI-1: dotenvをimportしない", "dotenv" in _cli_import_names)
print()


print("[CLI-2] CWD Independence")

check(
    "CLI-2: _PROJECT_ROOT（再確認）",
    show_retry_notification._PROJECT_ROOT,
    SCRIPT_PATH.parent.parent,
)
check(
    "CLI-2: _DEFAULT_LOG_PATH（再確認）",
    show_retry_notification._DEFAULT_LOG_PATH,
    show_retry_notification._PROJECT_ROOT / ".run" / "retry_runtime_log.jsonl",
)

_cli_call_dotted = collect_call_dotted_names(CLI_TREE)
check_false("CLI-2: Path.cwd()を呼ばない", "Path.cwd" in _cli_call_dotted)
check_false("CLI-2: os.getcwd()を呼ばない", "os.getcwd" in _cli_call_dotted)
check_false("CLI-2: os.chdir()を呼ばない", "os.chdir" in _cli_call_dotted)
print()


# ═══════════════════════════════════════════════════════════
# DEP-1／DEP-2: Dependency Direction
# ═══════════════════════════════════════════════════════════
print("[DEP-1] CLI Import Direction（AST）")

check_true("DEP-1: retry_metricsをimport", "retry_metrics" in _cli_import_names)
check_true("DEP-1: retry_monitoringをimport", "retry_monitoring" in _cli_import_names)
check_true("DEP-1: retry_alertをimport", "retry_alert" in _cli_import_names)
check_true("DEP-1: retry_notificationをimport", "retry_notification" in _cli_import_names)
check_true("DEP-1: retry_notification_messageをimport", "retry_notification_message" in _cli_import_names)

_cli_from_modules = collect_from_import_modules(CLI_TREE)
for _pkg in ("retry_metrics", "retry_monitoring", "retry_alert", "retry_notification", "retry_notification_message"):
    _has_submodule_import = any(m.startswith(f"{_pkg}.") for m in _cli_from_modules)
    check_false(f"DEP-1: {_pkg}の内部モジュールを直接importしない", _has_submodule_import)

check_false("DEP-1: retry_compositionをimportしない", "retry_composition" in _cli_import_names)
check_false("DEP-1: retry_runtime_orchestratorをimportしない", "retry_runtime_orchestrator" in _cli_import_names)
check_false("DEP-1: run_retry_runtimeをimportしない", "run_retry_runtime" in _cli_import_names)
print()


print("[DEP-2] Reverse Dependency Absence")

_retry_composition_dir = PROJECT_ROOT / "src" / "retry_composition"
_retry_runtime_orchestrator_dir = PROJECT_ROOT / "src" / "retry_runtime_orchestrator"
_run_retry_runtime_path = PROJECT_ROOT / "scripts" / "run_retry_runtime.py"

_reverse_dep_ok = True
for _py_file in list(_retry_composition_dir.glob("*.py")) + list(_retry_runtime_orchestrator_dir.glob("*.py")):
    if "show_retry_notification" in _py_file.read_text(encoding="utf-8"):
        _reverse_dep_ok = False
check_true("DEP-2: retry_composition／retry_runtime_orchestratorがCLIを参照しない", _reverse_dep_ok)

check_not_contains(
    "DEP-2: run_retry_runtime.pyがCLIを参照しない",
    _run_retry_runtime_path.read_text(encoding="utf-8"),
    "show_retry_notification",
)
print()


# ═══════════════════════════════════════════════════════════
# IO-1: Forbidden I/O／External Dependencies
# ═══════════════════════════════════════════════════════════
print("[IO-1] Forbidden I/O／External Dependencies")

_cli_call_names_bare = {
    node.func.id
    for node in ast.walk(CLI_TREE)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
}
_cli_call_attrs = collect_call_attrs(CLI_TREE)

check_false("IO-1: open()を直接呼ばない", "open" in _cli_call_names_bare)
check_false("IO-1: write_text()を呼ばない", "write_text" in _cli_call_attrs)
check_false("IO-1: write_bytes()を呼ばない", "write_bytes" in _cli_call_attrs)

_forbidden_imports = {
    "socket",
    "urllib",
    "http",
    "requests",
    "subprocess",
    "logging",
    "warnings",
    "dotenv",
    "smtplib",
    "email",
    "slack_sdk",
    "discord",
}
for _forbidden_module in sorted(_forbidden_imports):
    check_false(f"IO-1: {_forbidden_module}をimportしない", _forbidden_module in _cli_import_names)

_cli_attribute_names = collect_attribute_dotted_names(CLI_TREE)
check_false("IO-1: os.environを参照しない", "os.environ" in _cli_attribute_names)
check_false("IO-1: os.getenv()を呼ばない", "os.getenv" in _cli_call_dotted)
print()


# ═══════════════════════════════════════════════════════════
# PF-1: format_report Pure Function
# ═══════════════════════════════════════════════════════════
print("[PF-1] format_report Pure Function（振る舞い＋AST）")

# --- 振る舞い検査 ---
_pf1_result_1 = format_report(_out1_report)
_pf1_result_2 = format_report(_out1_report)
check("PF-1: 同一入力→同一出力", _pf1_result_1, _pf1_result_2)

_pf1_metrics_before = _out1_report.metrics
_pf1_health_before = _out1_report.health_report
format_report(_out1_report)
check_true("PF-1: 入力Report不変（metrics）", _out1_report.metrics is _pf1_metrics_before)
check_true("PF-1: 入力Report不変（health_report）", _out1_report.health_report is _pf1_health_before)

_pf1_stdout_buf, _pf1_stderr_buf = io.StringIO(), io.StringIO()
with contextlib.redirect_stdout(_pf1_stdout_buf), contextlib.redirect_stderr(_pf1_stderr_buf):
    format_report(_out1_report)
check("PF-1: stdout出力なし", _pf1_stdout_buf.getvalue(), "")
check("PF-1: stderr出力なし", _pf1_stderr_buf.getvalue(), "")

# --- AST検査（format_report関数本体のみ） ---
_format_report_def = find_function_def(CLI_TREE, "format_report")
_fr_call_names_bare = {
    node.func.id
    for node in ast.walk(_format_report_def)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
}
_fr_call_attrs = collect_call_attrs(_format_report_def)
_fr_call_dotted = collect_call_dotted_names(_format_report_def)
_fr_attribute_names = collect_attribute_dotted_names(_format_report_def)

check_false("PF-1: format_report内でopen()を呼ばない", "open" in _fr_call_names_bare)
check_false("PF-1: format_report内でwrite_text()を呼ばない", "write_text" in _fr_call_attrs)
check_false("PF-1: format_report内でwrite_bytes()を呼ばない", "write_bytes" in _fr_call_attrs)
check_false("PF-1: format_report内でos.environを参照しない", "os.environ" in _fr_attribute_names)
check_false("PF-1: format_report内でos.getenv()を呼ばない", "os.getenv" in _fr_call_dotted)
check_false("PF-1: format_report内でPath.cwd()を呼ばない", "Path.cwd" in _fr_call_dotted)
check_false("PF-1: format_report内でos.getcwd()を呼ばない", "os.getcwd" in _fr_call_dotted)
check_false("PF-1: format_report内でdatetime.now()を呼ばない", "datetime.now" in _fr_call_dotted)
check_false("PF-1: format_report内でtime.time()を呼ばない", "time.time" in _fr_call_dotted)
check_false("PF-1: format_report内でlocaleを参照しない", "locale" in collect_import_names(_format_report_def))
print()


# ═══════════════════════════════════════════════════════════
# SP-1〜SP-3: Subprocess Scenarios
# ═══════════════════════════════════════════════════════════
print("[SP-1〜SP-3] Subprocess Scenarios")


def run_cli(args: list[str], timeout: int = 60):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=timeout,
    )


with tempfile.TemporaryDirectory() as _tmp:
    _sp1_path = Path(_tmp) / "degraded.jsonl"
    _write_single_record_log(_sp1_path, scanned=10, enqueued=6)
    _sp1_result = run_cli(["--log-path", str(_sp1_path)])

check("SP-1: returncode 0", _sp1_result.returncode, 0)
check_contains("SP-1: stdoutにタイトル", _sp1_result.stdout, "Retry Notification Report")
check("SP-1: stderrが空", _sp1_result.stderr, "")

_sp2_result = run_cli(["--unknown"])
check("SP-2: returncode 2", _sp2_result.returncode, 2)
check_true("SP-2: stderrにusage／errorが含まれる", len(_sp2_result.stderr) > 0)
check_not_contains("SP-2: stdoutに正常Reportなし", _sp2_result.stdout, "Retry Notification Report")

with tempfile.TemporaryDirectory() as _tmp:
    _sp3_path = make_unreadable_path(Path(_tmp))
    _sp3_result = run_cli(["--log-path", str(_sp3_path)])
check("SP-3: returncode 1", _sp3_result.returncode, 1)
check_contains("SP-3: stderrに[ERROR]", _sp3_result.stderr, "[ERROR]")
check_not_contains("SP-3: Tracebackなし", _sp3_result.stderr, "Traceback")
check_not_contains("SP-3: stdoutに正常Reportなし", _sp3_result.stdout, "Retry Notification Report")
print()


# ─── sys.modules 復元（正常完了時。異常終了時はatexit登録済みの_restore_sys_modulesが保証する） ───
_restore_sys_modules()


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
