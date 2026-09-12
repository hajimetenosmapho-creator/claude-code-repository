"""
E2E テスト: Release 6.32 WordPressDraftStateStore exact contract
（§28.3・§28.-32 Invariant #8・Cross-Store関連）

Source of Truth:
    docs/design/side_effect_fail_closed_human_review_safety_foundation.md
    9.3節（Store公開API）・9.5節（Manager層）・28.3節（12件）・28.-32節（Invariant #8）。

本ファイルは、read-only照合で発見したproduction defectの修正
（Human Gate承認済み）の直接検証である。

**production fix適用箇所（本テスト実行前提）**:
    src/wordpress_draft_state/wordpress_draft_state_store.py
    `JsonWordPressDraftStateStore.transition_to_confirmed()`が、
    record不存在・member_run_id mismatch・current state != ATTEMPTED
    （terminal non-recycle含む）・persisted identity/schema corruptionの
    いずれのcompare-and-transition不成立ケースでも例外を送出せず、
    `TransitionResult(acknowledged=False, reason=..., record=None)`を
    返すよう修正した（§9.3・§9.5・§28.3#5・#6・#7・#8・#12）。
    `create_attempted()`の既存exception semantics（duplicate create等）は
    無変更。真の`WordPressDraftStateIOError`（filesystem I/O failure）は
    catchせず、pre-commit failureとしてそのまま伝播する。

対象production: src/wordpress_draft_state/wordpress_draft_state_store.py
（transition_to_confirmed()のみ変更。create_attempted()・get()は無変更）。

Store層はStore層のcontractを直接assertする（Manager経由のテストは
既存test_e2e_v6_32_0_side_effect_fail_closed_foundation.pyでCOMPLETEの
ため重複実装しない。テスト11のみ、Store→Managerのacknowledged=False→
例外変換という既存設計が実際に成立することを確認する）。

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_32_19_wordpress_draft_state_store_contract.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).parent.parent
SRC_DIR = PROJECT_ROOT / "src"
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


print("=" * 60)
print("WordPressDraftStateStore exact contract（§28.3・§28.-32）E2E テスト")
print("=" * 60)
print()

from side_effect_safety.side_effect_operation_identity import (
    ProtectedSideEffectKind,
    SideEffectOperationIdentity,
    SideEffectOperationState,
    SideEffectSite,
)
from wordpress_draft_state.errors import (
    WordPressDraftStateCorruptedError,
    WordPressDraftStateIOError,
    WordPressDraftStateTransitionError,
)
from wordpress_draft_state.wordpress_draft_state_manager import WordPressDraftStateManager
from wordpress_draft_state.wordpress_draft_state_store import JsonWordPressDraftStateStore, TransitionResult


def _tmp() -> Path:
    return Path(tempfile.mkdtemp(prefix="v6_32_19_"))


def _make_store(tmpdir: Path) -> JsonWordPressDraftStateStore:
    return JsonWordPressDraftStateStore(tmpdir / "state", tmpdir / "locks")


def _identity(instance_key="art1", root_run_id="r1", attempt_ordinal=1, site=SideEffectSite.NEWS_STEP):
    return SideEffectOperationIdentity(
        root_run_id=root_run_id, attempt_ordinal=attempt_ordinal,
        operation_kind=ProtectedSideEffectKind.WORDPRESS_DRAFT_CREATION,
        effect_site=site, operation_instance_key=instance_key,
    )


# =====================================================================
# [テスト1] valid ATTEMPTED + exact identity/member_run_id一致 → CONFIRMED_SUCCESS
# =====================================================================

print("[テスト1] valid ATTEMPTED → transition_to_confirmed() → acknowledged=True・CONFIRMED_SUCCESS")

tmp_1 = _tmp()
store_1 = _make_store(tmp_1)
identity_1 = _identity()

created_1 = store_1.create_attempted(identity_1, "member-1", "2026-01-01T00:00:00+00:00")
check_true("1a. create_attempted()成功", created_1.acknowledged)

result_1 = store_1.transition_to_confirmed(identity_1, "member-1", 123, "2026-01-01T00:01:00+00:00")

check_true("1b. acknowledged=True", result_1.acknowledged)
check_true("1c. reasonはNone", result_1.reason is None)
check_true("1d. recordが返る", result_1.record is not None)
check("1e. stateはCONFIRMED_SUCCESS", result_1.record.state, SideEffectOperationState.CONFIRMED_SUCCESS)
check("1f. wp_post_idが伝播する", result_1.record.wp_post_id, 123)

read_back_1 = store_1.get(identity_1, "member-1")
check("1g. get()で読み直してもCONFIRMED_SUCCESS", read_back_1.state, SideEffectOperationState.CONFIRMED_SUCCESS)
print()


# =====================================================================
# [テスト2] already CONFIRMED_SUCCESS（terminal non-recycle）→ acknowledged=False・例外なし
# =====================================================================

print("[テスト2] 確定済みrecordへの再遷移（terminal non-recycle）→ acknowledged=False、exceptionなし")

raised_2 = None
try:
    result_2 = store_1.transition_to_confirmed(identity_1, "member-1", 999, "2026-01-01T00:02:00+00:00")
except Exception as e:
    raised_2 = e

check_true("2a. 例外は送出されない", raised_2 is None)
check_false("2b. acknowledged=False", result_2.acknowledged)
check_true("2c. recordはNone", result_2.record is None)
check_true("2d. reasonは非None（stable reason）", result_2.reason is not None)

read_back_2 = store_1.get(identity_1, "member-1")
check("2e. durable stateは変化しない（wp_post_id=123のまま）", read_back_2.wp_post_id, 123)
check_false("2f. duplicate confirmedがacknowledged=Trueへ丸められていない", result_2.acknowledged)
print()


# =====================================================================
# [テスト3] member_run_id mismatch → acknowledged=False・例外なし
# =====================================================================

print("[テスト3] member_run_id mismatch → acknowledged=False、exceptionなし")

tmp_3 = _tmp()
store_3 = _make_store(tmp_3)
identity_3 = _identity(instance_key="art3")
store_3.create_attempted(identity_3, "member-3", "2026-01-01T00:00:00+00:00")

raised_3 = None
try:
    result_3 = store_3.transition_to_confirmed(identity_3, "WRONG-MEMBER", 1, "2026-01-01T00:01:00+00:00")
except Exception as e:
    raised_3 = e

check_true("3a. 例外は送出されない", raised_3 is None)
check_false("3b. acknowledged=False", result_3.acknowledged)
check_true("3c. recordはNone", result_3.record is None)

read_back_3 = store_3.get(identity_3, "member-3")
check("3d. durable stateはATTEMPTEDのまま変化しない", read_back_3.state, SideEffectOperationState.ATTEMPTED)
print()


# =====================================================================
# [テスト4] record不存在 → acknowledged=False
# =====================================================================

print("[テスト4] record不存在（create_attempted()未実行）→ acknowledged=False")

tmp_4 = _tmp()
store_4 = _make_store(tmp_4)
identity_4 = _identity(instance_key="art4")

raised_4 = None
try:
    result_4 = store_4.transition_to_confirmed(identity_4, "member-4", 1, "2026-01-01T00:00:00+00:00")
except Exception as e:
    raised_4 = e

check_true("4a. 例外は送出されない", raised_4 is None)
check_false("4b. acknowledged=False", result_4.acknowledged)
check_true("4c. get()もNone（record自体が存在しない）", store_4.get(identity_4, "member-4") is None)
print()


# =====================================================================
# [テスト5] cross-attempt identity mismatch → acknowledged=False（no ATTEMPTED record）
# =====================================================================

print("[テスト5] cross-attempt（別attempt_ordinalのidentity）→ acknowledged=False")

tmp_5 = _tmp()
store_5 = _make_store(tmp_5)
identity_5_attempt1 = _identity(instance_key="art5", attempt_ordinal=1)
identity_5_attempt2 = _identity(instance_key="art5", attempt_ordinal=2)
store_5.create_attempted(identity_5_attempt1, "member-5", "2026-01-01T00:00:00+00:00")

raised_5 = None
try:
    result_5 = store_5.transition_to_confirmed(identity_5_attempt2, "member-5", 1, "2026-01-01T00:01:00+00:00")
except Exception as e:
    raised_5 = e

check_true("5a. 例外は送出されない", raised_5 is None)
check_false("5b. acknowledged=False（別ファイル、レコード自体が存在しない）", result_5.acknowledged)
check("5c. attempt1側のrecordは無傷（ATTEMPTEDのまま）", store_5.get(identity_5_attempt1, "member-5").state, SideEffectOperationState.ATTEMPTED)
print()


# =====================================================================
# [テスト6] cross-effect-site mismatch → acknowledged=False（同上）
# =====================================================================

print("[テスト6] cross-effect-site（NEWS_STEP vs PUBLISH_STEP）→ acknowledged=False")

tmp_6 = _tmp()
store_6 = _make_store(tmp_6)
identity_6_news = _identity(instance_key="art6", site=SideEffectSite.NEWS_STEP)
identity_6_publish = _identity(instance_key="art6", site=SideEffectSite.PUBLISH_STEP)
store_6.create_attempted(identity_6_news, "member-6", "2026-01-01T00:00:00+00:00")

raised_6 = None
try:
    result_6 = store_6.transition_to_confirmed(identity_6_publish, "member-6", 1, "2026-01-01T00:01:00+00:00")
except Exception as e:
    raised_6 = e

check_true("6a. 例外は送出されない", raised_6 is None)
check_false("6b. acknowledged=False", result_6.acknowledged)
check("6c. NEWS側のrecordは無傷（ATTEMPTEDのまま、identity分離が成立）", store_6.get(identity_6_news, "member-6").state, SideEffectOperationState.ATTEMPTED)
print()


# =====================================================================
# [テスト7] persisted identity/schema corruption → acknowledged=False
#           WordPressDraftStateCorruptedErrorを外へ出さない
# =====================================================================

print("[テスト7] persisted identity corruption → acknowledged=False、CorruptedErrorを外へ出さない")

tmp_7 = _tmp()
store_7 = _make_store(tmp_7)
identity_7 = _identity(instance_key="art7")
store_7.create_attempted(identity_7, "member-7", "2026-01-01T00:00:00+00:00")

path_7 = store_7._path_for(identity_7)
doc_7 = json.loads(path_7.read_text(encoding="utf-8"))
doc_7["attempt_ordinal"] = 999  # identity fieldsのうち1つを人為的に破損させる
path_7.write_text(json.dumps(doc_7), encoding="utf-8")

raised_7 = None
try:
    result_7 = store_7.transition_to_confirmed(identity_7, "member-7", 1, "2026-01-01T00:01:00+00:00")
except Exception as e:
    raised_7 = e

check_true("7a. WordPressDraftStateCorruptedErrorは外へ出ない（例外なし）", raised_7 is None)
check_false("7b. acknowledged=False", result_7.acknowledged)
check_true("7c. recordはNone", result_7.record is None)

# get()自体は既存契約どおりCorruptedErrorを送出し続けること（get()の契約は無変更）
get_raised_7 = None
try:
    store_7.get(identity_7, "member-7")
except WordPressDraftStateCorruptedError as e:
    get_raised_7 = e
check_true("7d. get()側の既存契約（CorruptedError送出）は無変更のまま維持される", get_raised_7 is not None)
print()


# =====================================================================
# [テスト8] 真のWordPressDraftStateIOError → propagate、acknowledged=Falseへ丸めない
# =====================================================================

print("[テスト8] 真のfilesystem I/O failure → WordPressDraftStateIOErrorがそのまま伝播する")

tmp_8 = _tmp()
store_8 = _make_store(tmp_8)
identity_8 = _identity(instance_key="art8")
store_8.create_attempted(identity_8, "member-8", "2026-01-01T00:00:00+00:00")


class _IOFailingStore(JsonWordPressDraftStateStore):
    def _read_raw(self, identity):
        raise WordPressDraftStateIOError("simulated filesystem read failure")


io_store_8 = _IOFailingStore(tmp_8 / "state", tmp_8 / "locks")

raised_8 = None
try:
    io_store_8.transition_to_confirmed(identity_8, "member-8", 1, "2026-01-01T00:01:00+00:00")
except WordPressDraftStateIOError as e:
    raised_8 = e
except Exception as e:
    raised_8 = e

check_true("8a. WordPressDraftStateIOErrorが送出される（catchされず伝播）", isinstance(raised_8, WordPressDraftStateIOError))
check_false("8b. IOErrorがacknowledged=Falseへ丸められていない（例外のまま）", isinstance(raised_8, TransitionResult))
print()


# =====================================================================
# [テスト9] write/atomic persistence failure → success捏造なし
# =====================================================================

print("[テスト9] CONFIRMED_SUCCESS書き込み自体の失敗 → success捏造なし")

tmp_9 = _tmp()
store_9 = _make_store(tmp_9)
identity_9 = _identity(instance_key="art9")
store_9.create_attempted(identity_9, "member-9", "2026-01-01T00:00:00+00:00")


class _WriteFailingStore(JsonWordPressDraftStateStore):
    def _write_raw(self, record):
        raise WordPressDraftStateIOError("simulated write failure")


write_failing_store_9 = _WriteFailingStore(tmp_9 / "state", tmp_9 / "locks")

raised_9 = None
try:
    write_failing_store_9.transition_to_confirmed(identity_9, "member-9", 1, "2026-01-01T00:01:00+00:00")
except WordPressDraftStateIOError as e:
    raised_9 = e

check_true("9a. write失敗はWordPressDraftStateIOErrorとして伝播する", raised_9 is not None)
# 別store instance（同一durable dir）で確認: durable stateはATTEMPTEDのまま（CONFIRMEDへ捏造されていない）
verify_store_9 = _make_store(tmp_9)
check("9b. durable stateはATTEMPTEDのまま（success捏造なし）", verify_store_9.get(identity_9, "member-9").state, SideEffectOperationState.ATTEMPTED)
print()


# =====================================================================
# [テスト10] create_attempted()既存exception semantics不変
# =====================================================================

print("[テスト10] create_attempted()の既存exception semanticsは無変更")

tmp_10 = _tmp()
store_10 = _make_store(tmp_10)
identity_10 = _identity(instance_key="art10")

first_10 = store_10.create_attempted(identity_10, "member-10", "2026-01-01T00:00:00+00:00")
check_true("10a. 1回目は成功", first_10.acknowledged)

raised_10 = None
try:
    store_10.create_attempted(identity_10, "member-10", "2026-01-01T00:01:00+00:00")
except WordPressDraftStateTransitionError as e:
    raised_10 = e

check_true("10b. duplicate createは依然としてWordPressDraftStateTransitionErrorを送出する（変更なし）", raised_10 is not None)
print()


# =====================================================================
# [テスト11] Manager経由: acknowledged=False → WordPressDraftStateTransitionErrorへ変換
# =====================================================================

print("[テスト11] Manager経由でStoreのacknowledged=FalseがWordPressDraftStateTransitionErrorへ変換される")

tmp_11 = _tmp()
store_11 = _make_store(tmp_11)
manager_11 = WordPressDraftStateManager(store_11)
identity_11 = _identity(instance_key="art11")

manager_11.record_attempted(identity_11, "member-11")

raised_11a = None
try:
    manager_11.record_confirmed(identity_11, "WRONG-MEMBER", 1)
except WordPressDraftStateTransitionError as e:
    raised_11a = e

check_true("11a. Manager.record_confirmed()のmember_run_id mismatchはWordPressDraftStateTransitionErrorへ変換される", raised_11a is not None)

confirmed_11 = manager_11.record_confirmed(identity_11, "member-11", 42)
check("11b. 正しいmember_run_idでは正常にCONFIRMED_SUCCESSへ", confirmed_11.state, SideEffectOperationState.CONFIRMED_SUCCESS)

raised_11b = None
try:
    manager_11.record_confirmed(identity_11, "member-11", 999)
except WordPressDraftStateTransitionError as e:
    raised_11b = e

check_true("11c. 確定済みへの再遷移もWordPressDraftStateTransitionErrorへ変換される（terminal non-recycle）", raised_11b is not None)
print()


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
