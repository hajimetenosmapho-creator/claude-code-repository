"""
Scheduler Dispatch Ledger Store（v6.34.0、Release 6.34）

SchedulerDispatchLedgerStoreReadError: recordの読み取り・パース・スキーマ検証に
                                        失敗した場合に送出される例外
SchedulerDispatchLedgerStore:          DispatchLedgerEntryの永続化方式を抽象化する
                                        インターフェース
JsonSchedulerDispatchLedgerStore:      {store_dir}/{sanitized event_identity}.json へ
                                        JSON形式でatomicに保存する実装

設計方針（docs/design/scheduler_driver_duplicate_dispatch_safety_foundation.md 8.5章）:
    - 書き込み（save）のatomic save契約は既存のJsonRetryLineageStore/
      JsonExecutionHistoryStoreを踏襲する（tempfile.mkstemp → write → flush →
      fsync → close → os.replace）。書き込み失敗はraiseせず bool（False）で
      呼び出し元へ通知する（8.5章(2)）。
    - **読み取り（get/list_all）はJsonRetryLineageStoreの既存precedentと意図的に
      異なる契約を持つ**：JsonRetryLineageStoreのget()/list_all()は読み取り失敗
      （壊れたJSON等）をログ出力のうえNone/スキップとして扱うが、本Storeでは
      「読み取り不能」と「recordが確実に存在しない」を明確に区別するため、
      読み取り・パース・スキーマ検証のいずれかに失敗した場合は
      SchedulerDispatchLedgerStoreReadErrorを送出する（Noneを返さない）。
      これは8.5章 共通原則「読み取りエラーをrecordが存在しないと暗黙に等値変換
      することを禁止する」を実装するための意図的な差分であり、実装漏れではない。
    - event_identity（例："workflow_engine_demo_daily::2026-09-16T09:00"）は
      ":" を含みWindowsのファイル名として不正なため、ファイル名としては
      `_sanitize_event_identity()` による単射（injective）なエスケープ形式
      （安全文字＝数字・"_"・"."のみリテラル通過、それ以外は全てUTF-8バイト単位で
      "~XX"（2桁16進、常に大文字）へエスケープ）を用いる（JSON内容自体の
      event_identityフィールドは元の値を保持する）。ASCII英字も安全文字集合に
      含めない設計により、Windowsファイルシステムのcase-insensitivityに対しても
      単射性を維持する（Codex Independent Code Review Round 4・5対応）。
"""
from __future__ import annotations

import json
import os
import stat
import tempfile
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

from .dispatch_ledger_entry import DispatchLedgerEntry
from .dispatch_phase import DispatchPhase

_VALID_PHASE_VALUES = {p.value for p in DispatchPhase}


class SchedulerDispatchLedgerStoreReadError(Exception):
    """recordの読み取り・パース・スキーマ検証に失敗した場合に送出される例外。
    「読み取り不能」と「recordが確実に存在しない」を区別するために使う。"""


_SAFE_FILENAME_CHARS = frozenset("0123456789_.")


def _sanitize_event_identity(event_identity: str) -> str:
    """event_identityを、ファイル名として安全かつ**単射（injective）**な
    形式へ変換する（Codex Independent Code Review Round 4 Major対応、
    Round 5 Major対応でさらに改訂）。

    旧実装（":"→"-"等の単純な固定文字置換）は単射性を持たなかった——
    例えばjob_idに文字列"-"を含む値と、":"を含み"-"へ置換された値が
    偶然同じsanitized文字列に**衝突**しうる。衝突すると`save()`が
    別eventのrecordを上書きし、`get()`が誤ったrecordを返しうる。これは
    duplicate dispatch防止という本Storeの中核安全性を破壊しうる欠陥
    だったため、単射性を持つエスケープ方式へ置き換えた（Round 4）。

    **Round 5改訂**：安全文字集合から英字（大文字・小文字）を除外し、
    数字・"_"・"."のみとした。NTFS等のWindowsファイルシステムは
    大文字小文字を区別しない（case-insensitive、ただしcase-preserving）
    ため、Pythonの文字列としては単射なsanitized文字列であっても、
    大文字小文字のみが異なる2つの識別子（例："Job::..."と"job::..."）が
    実際のファイルパスとしては同一ファイルに衝突しうる——Round 4の
    修正はPython文字列レベルの単射性のみを保証し、Windowsファイル
    システムレベルの単射性を保証していなかった。英字を含むあらゆる
    文字を"~XX"（XXは2桁16進、常に大文字で生成される自分自身の出力
    のみが安全文字集合外に現れるため大文字小文字の曖昧性は生じない）
    へエスケープすることで、安全文字集合自体が大文字小文字の区別を
    一切持たない状態にし、ファイルシステムのcase-insensitivityに
    対しても単射性を維持する。

    エスケープマーカー"~"自体も安全文字集合に含まれない（＝必ず
    エスケープ対象となる）ため、任意の異なる入力が同じ出力へ写る
    ことは構造的にない（左から一意に復号できる＝単射）。get()/
    list_all()側でも、復号したrecordのevent_identityが要求元・
    ファイル名由来の期待値と一致することを別途クロスチェックする
    （多層防御、8.5章・16章参照）。"""
    out_chars: list[str] = []
    for ch in event_identity:
        if ch in _SAFE_FILENAME_CHARS:
            out_chars.append(ch)
        else:
            for b in ch.encode("utf-8"):
                out_chars.append(f"~{b:02X}")
    return "".join(out_chars)


def _entry_to_dict(entry: DispatchLedgerEntry) -> dict:
    return {
        "event_identity": entry.event_identity,
        "job_id": entry.job_id,
        "occurrence_minute": entry.occurrence_minute,
        "phase": entry.phase.value,
        "claimed_at": entry.claimed_at.isoformat(),
        "confirmed_at": entry.confirmed_at.isoformat() if entry.confirmed_at is not None else None,
        "dispatch_run_id": entry.dispatch_run_id,
        "outcome_summary": entry.outcome_summary,
        "detail": entry.detail,
        "updated_at": entry.updated_at.isoformat(),
    }


def _entry_from_dict(data: dict) -> DispatchLedgerEntry:
    """スキーマ検証を含む（Codex Independent Code Review Round 1 Major対応、拡充）。
    必須フィールド欠落はKeyError、型不正・phaseが3値以外・event_identityと
    job_id/occurrence_minoteの不整合はTypeError/ValueErrorを送出する
    （呼び出し元がSchedulerDispatchLedgerStoreReadErrorへ変換する）。"""
    if not isinstance(data, dict):
        raise TypeError(f"record is not a JSON object: {type(data).__name__}")

    event_identity = data["event_identity"]
    job_id = data["job_id"]
    occurrence_minute = data["occurrence_minute"]
    phase_value = data["phase"]

    for _field_name, _value in (
        ("event_identity", event_identity),
        ("job_id", job_id),
        ("occurrence_minute", occurrence_minute),
        ("phase", phase_value),
    ):
        if not isinstance(_value, str) or not _value:
            raise TypeError(f"{_field_name} must be a non-empty string, got {_value!r}")

    if event_identity != f"{job_id}::{occurrence_minute}":
        raise ValueError(
            f"event_identity ({event_identity!r}) does not match "
            f"job_id::occurrence_minute ({job_id}::{occurrence_minute})"
        )

    if phase_value not in _VALID_PHASE_VALUES:
        raise ValueError(f"invalid phase value: {phase_value!r}")
    phase = DispatchPhase(phase_value)

    claimed_at = datetime.fromisoformat(data["claimed_at"])
    # Codex Round 2 Minor対応：truthy判定（if confirmed_at_raw）だと0/False/""
    # のような非Noneのfalsy値を誤ってNoneへ丸めてしまう。`is not None`で
    # 判定したうえで、型自体もstrであることを要求する（fromisoformat()の
    # 引数がstr以外なら即座にTypeErrorとなり読み取り失敗として扱われる）。
    confirmed_at_raw = data.get("confirmed_at")
    if confirmed_at_raw is not None and not isinstance(confirmed_at_raw, str):
        raise TypeError(f"confirmed_at must be a string or null, got {confirmed_at_raw!r}")
    confirmed_at = datetime.fromisoformat(confirmed_at_raw) if confirmed_at_raw is not None else None
    updated_at = datetime.fromisoformat(data["updated_at"])

    for _field_name, _value in (
        ("dispatch_run_id", data.get("dispatch_run_id")),
        ("outcome_summary", data.get("outcome_summary")),
        ("detail", data.get("detail")),
    ):
        if _value is not None and not isinstance(_value, str):
            raise TypeError(f"{_field_name} must be a string or null, got {_value!r}")

    return DispatchLedgerEntry(
        event_identity=event_identity,
        job_id=job_id,
        occurrence_minute=occurrence_minute,
        phase=phase,
        claimed_at=claimed_at,
        confirmed_at=confirmed_at,
        dispatch_run_id=data.get("dispatch_run_id"),
        outcome_summary=data.get("outcome_summary"),
        detail=data.get("detail"),
        updated_at=updated_at,
    )


class SchedulerDispatchLedgerStore(ABC):
    """DispatchLedgerEntryの永続化方式を抽象化するインターフェース。"""

    @abstractmethod
    def save(self, entry: DispatchLedgerEntry) -> bool:
        """entryをevent_identityで保存する（新規・上書き両対応）。保存に成功したか
        （acknowledged）を返す。失敗してもraiseしない（8.5章(2)）。"""
        ...

    @abstractmethod
    def get(self, event_identity: str) -> DispatchLedgerEntry | None:
        """event_identityに対応するrecordを返す。recordが確実に存在しない場合の
        みNoneを返す。読み取り・パース・スキーマ検証に失敗した場合は
        SchedulerDispatchLedgerStoreReadErrorを送出する（Noneを返さない）。"""
        ...

    @abstractmethod
    def list_all(self) -> list[DispatchLedgerEntry]:
        """保存されているすべてのrecordを返す。列挙・個々のrecordの読み取りの
        いずれかが失敗した場合はSchedulerDispatchLedgerStoreReadErrorを送出する
        （部分的な結果を返さない、8.5章(4)(a)(b)）。"""
        ...


class JsonSchedulerDispatchLedgerStore(SchedulerDispatchLedgerStore):
    """{store_dir}/{sanitized event_identity}.json へJSON形式でatomicに保存する実装。

    Codex Independent Code Review Round 1 Blocking対応：コンストラクタが
    store_dirを即座に（eagerly）作成する。これにより、構築後にget()/
    list_all()がstore_dir不在を検出した場合は「まだ一度も初期化されていない
    正当な状態」ではなく「構築後に何らかの理由でディレクトリが消失した異常
    事態」であると構造的に断定できる——「読み取り不能」を「recordが存在しない」
    と暗黙に等値変換することを禁止する8.5章の共通原則を、ディレクトリ単位でも
    徹底する。"""

    def __init__(self, store_dir: Path):
        self._store_dir = store_dir
        self._store_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, event_identity: str) -> Path:
        return self._store_dir / f"{_sanitize_event_identity(event_identity)}.json"

    def save(self, entry: DispatchLedgerEntry) -> bool:
        try:
            self._store_dir.mkdir(parents=True, exist_ok=True)
            # Codex Independent Code Review Round 5 Minor対応：一時ファイルの
            # prefixにsanitized event_identity全体を埋め込まない。エスケープ後の
            # 文字列は元の識別子より長くなりうり（1文字→最大"~XX"×UTF-8バイト数）、
            # mkstemp()自身が追加するランダム文字列・".tmp"サフィックスと合わせて
            # Windowsのパス長制限に不必要に近づく（save()はOSErrorをFalseへ
            # 変換するためfail-closedではあるが、長い識別子で可用性上の問題に
            # なりうる回避可能な要因を減らす）。短い固定prefixのみを使う。
            fd, tmp_path_str = tempfile.mkstemp(
                prefix=".dispatch_entry.", suffix=".tmp",
                dir=str(self._store_dir),
            )
        except OSError as e:
            print(f"  [SCHEDULER DISPATCH LEDGER WARNING] entry保存に失敗しました（処理は継続します）: {e}")
            return False

        tmp_path = Path(tmp_path_str)
        try:
            try:
                f = os.fdopen(fd, "w", encoding="utf-8")
            except OSError as e:
                try:
                    os.close(fd)
                except OSError:
                    pass
                print(f"  [SCHEDULER DISPATCH LEDGER WARNING] entry保存に失敗しました（処理は継続します）: {e}")
                return False

            try:
                with f:
                    json.dump(_entry_to_dict(entry), f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
            except OSError as e:
                print(f"  [SCHEDULER DISPATCH LEDGER WARNING] entry保存に失敗しました（処理は継続します）: {e}")
                return False

            try:
                os.replace(tmp_path, self._path_for(entry.event_identity))
            except OSError as e:
                print(f"  [SCHEDULER DISPATCH LEDGER WARNING] entry保存に失敗しました（処理は継続します）: {e}")
                return False

            return True
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    def _ensure_store_dir_accessible(self) -> None:
        """store_dirの状態を、OSErrorを握りつぶさない形で確認する
        （Codex Independent Code Review Round 2 Blocking対応）。

        `Path.exists()`/`Path.is_dir()`はCPython実装上、対象のstat()呼び出しで
        発生した大半のOSError（権限エラー等を含む）を内部でcatchしFalseへ変換
        する（Python 3.14時点）。これは本Storeが依拠したい「読み取り不能を
        recordが存在しないと暗黙に等値変換しない」という8.5章の原則と正面から
        衝突する——`Path.exists()`ベースの判定では「本当に存在しない」と
        「権限エラー等で確認できない」を区別できない。`os.lstat()`（シンボリック
        リンクを辿らない版）を直接使い、`FileNotFoundError`（構築後の消失、
        正確に異常と断定できる）と、その他のOSError（権限エラー等、同じく異常）
        をいずれも明示的にraiseする（Codex Round 3対応：`os.stat()`は
        シンボリックリンクを辿るため、store_dirがディレクトリへのsymlinkに
        置き換わっていてもS_ISDIRを通過してしまう。本Storeは自らmkdir()した
        「本物のディレクトリ」以外を一切許容しないため、`os.lstat()`で
        symlink自体をS_ISDIR判定から排除する）。"""
        try:
            st = os.lstat(self._store_dir)
        except FileNotFoundError as e:
            raise SchedulerDispatchLedgerStoreReadError(
                f"store directory missing (expected to exist since construction): {self._store_dir}"
            ) from e
        except OSError as e:
            raise SchedulerDispatchLedgerStoreReadError(
                f"store directory inspection failed: {self._store_dir}: {e}"
            ) from e
        if not stat.S_ISDIR(st.st_mode):
            raise SchedulerDispatchLedgerStoreReadError(
                f"store directory path is not a real directory (symlink or non-directory): {self._store_dir}"
            )

    def _read_record_file(self, path: Path) -> DispatchLedgerEntry | None:
        """1つのrecordファイルを安全に読み取る共通ヘルパー（get()/list_all()共用、
        Codex Round 3対応）。os.lstat()（symlinkを辿らない）で種別を確認し、
        symlink・その他非regular-fileはfail-closedで異常とする。存在しない
        （FileNotFoundError）場合のみNoneを返す——ただし呼び出し元
        （get()）はこの直前にTOCTOU再確認を行う責務を持つ（list_all()は
        列挙で発見された名前を対象とするため、この時点でのFileNotFoundError
        自体が既に別driverとの競合等の異常であり、Noneへ丸めずraiseする）。"""
        try:
            st = os.lstat(path)
        except FileNotFoundError:
            return None
        except OSError as e:
            raise SchedulerDispatchLedgerStoreReadError(f"{path.name}: inspection failed: {e}") from e
        if not stat.S_ISREG(st.st_mode):
            raise SchedulerDispatchLedgerStoreReadError(
                f"{path.name}: unexpected filesystem entry type (not a regular file, possibly a symlink)"
            )
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return _entry_from_dict(data)
        except (OSError, ValueError, KeyError, TypeError) as e:
            raise SchedulerDispatchLedgerStoreReadError(f"{path.name}: {e}") from e

    def get(self, event_identity: str) -> DispatchLedgerEntry | None:
        self._ensure_store_dir_accessible()
        path = self._path_for(event_identity)
        result = self._read_record_file(path)
        if result is None:
            # Codex Round 3 Blocking対応（TOCTOU）：_ensure_store_dir_accessible()
            # と_read_record_file()内部のlstat()の間にstore_dirごと消失した
            # 可能性を排除できない限り、「recordが確実に存在しない」と断定
            # しない。親ディレクトリの健全性をこのタイミングで再確認し、
            # 再確認自体が失敗すればfail-closedで例外を伝播させる（TOCTOU
            # windowを2回のsyscall分まで縮小する。完全な排除にはアトミックな
            # プリミティブが必要でありOS標準APIには存在しないため、これは
            # 受容する残存リスクとして扱う——Architecture 12.2章のLock
            # Lifecycle Contractが受容するTOCTOU残存windowと同型）。
            self._ensure_store_dir_accessible()
            return None
        if result.event_identity != event_identity:
            # Codex Round 4 Major対応：_sanitize_event_identity()は単射へ
            # 改訂済みだが、万一の衝突（実装バグ・手動改ざん等）が発生した
            # 場合に「別eventのrecordを正当な結果として返してしまう」ことを
            # 構造的に防ぐ多層防御のクロスチェック。要求されたevent_identityと
            # 実際に読み取ったrecordのevent_identityが一致しない場合は、
            # 誤った同一視を許さずfail-closedで異常として扱う。
            raise SchedulerDispatchLedgerStoreReadError(
                f"{path.name}: filename/event_identity mismatch "
                f"(requested {event_identity!r}, record contains {result.event_identity!r}); "
                "possible filename collision"
            )
        return result

    def list_all(self) -> list[DispatchLedgerEntry]:
        self._ensure_store_dir_accessible()
        # Path.glob()もPython 3.14時点でイテレーション中のOSErrorを握りつぶし
        # うる実装であるため、os.scandir()を直接使い列挙自体のOSErrorを
        # 確実に伝播させる（Codex Round 2 Blocking対応）。名前のみで候補を
        # 絞り、実際の型検査は_read_record_file()内のlstat()に一本化する
        # （Codex Round 3対応、symlink拒否を含む）。
        try:
            with os.scandir(self._store_dir) as it:
                names = sorted(entry.name for entry in it if entry.name.endswith(".json"))
        except OSError as e:
            raise SchedulerDispatchLedgerStoreReadError(f"enumeration failure: {e}") from e

        entries: list[DispatchLedgerEntry] = []
        for name in names:
            path = self._store_dir / name
            result = self._read_record_file(path)
            if result is None:
                # 列挙直後に発見された名前が読み取り時点で消えている場合、
                # これは「最初から存在しなかった」ケースとは異なる異常
                # （別driverとの競合等）であり、Noneへ丸めずraiseする。
                raise SchedulerDispatchLedgerStoreReadError(
                    f"{name}: record disappeared between enumeration and read"
                )
            # Codex Round 4 Major対応：ファイル名（＝sanitizeされたevent_identity）
            # と、record内容自身が主張するevent_identityの整合性をクロス
            # チェックする（get()と同じ多層防御）。
            expected_name = f"{_sanitize_event_identity(result.event_identity)}.json"
            if expected_name != name:
                raise SchedulerDispatchLedgerStoreReadError(
                    f"{name}: filename/event_identity mismatch "
                    f"(record contains {result.event_identity!r} which sanitizes to {expected_name!r}); "
                    "possible filename collision"
                )
            entries.append(result)
        return entries
