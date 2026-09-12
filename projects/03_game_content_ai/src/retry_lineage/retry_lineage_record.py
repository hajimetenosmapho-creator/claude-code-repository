"""
Retry Lineage Record定義（v6.31.0、Release 6.31）

RetryLineageMembershipEntry: lineageに属する1つのrun_id（attemptの実行run_id）を記録する
RetryLineageTransitionEvent: 1回のphase遷移イベントを記録する（append-only）
RetryAttemptExecutionScope:  1 attempt分の実行scope（steps_confirmed_done_before / steps_to_execute）
RetryLineageRecord:          1 lineageのdurable stateを保持するデータクラス（1 lineage = 1 JSONファイル）

設計方針（docs/design/retry_lineage_eligibility_durable_attempt_state.md 6・13章）:
    - Execution Historyとは別の、root_run_idキーの独立したminimal durable Retry
      Control Store。
    - max_attemptsはlineage作成時に一度だけRetryPolicy.max_attemptsからsnapshotされ、
      以後そのlineageの生涯を通じて不変（7.2・9.8章）。
    - attempt_countはmark_execution_started()のdurable ack成功時点でのみ+1する。
      dispositionを問わず一切減算されない（payback廃止、9.8.1.3章）。
    - attempt_scopesへの書き込みは create_new_lineage()（attempt 1用）と
      open_next_attempt()（attempt 2以降用）の2箇所のみ。mark_terminal()は一切
      書き込まない（12章、B-1対応）。いずれの書き込みも_canonicalize_step_order()
      を通した後の値を保存する（7.3章、MIN-R9-1対応）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from .retry_lineage_disposition import RetryLineageDisposition
from .retry_lineage_phase import RetryLineagePhase


class HumanReviewResolution(Enum):
    """Release 6.32、17.1節（不変）。"""

    RETRY_ALLOWED = "retry_allowed"
    ABANDONED = "abandoned"


@dataclass
class HumanReviewResolutionRecord:
    """Release 6.32、17.2節。`opened_attempt_no`はcrash-resumable dispatch
    marker（17.3節）——`resolve_human_review()`記録時点ではNone、
    `open_next_attempt()`のHRR authorized経路が次attempt番号を設定し、
    `mark_execution_started()`が実際にそのattemptの実行開始を確認した時点で
    レコード全体がクリアされる。"""

    resolution: HumanReviewResolution
    actor: str
    note: str | None
    resolved_at: datetime
    opened_attempt_no: int | None = None

    def to_dict(self) -> dict:
        return {
            "resolution": self.resolution.value,
            "actor": self.actor,
            "note": self.note,
            "resolved_at": self.resolved_at.isoformat(),
            "opened_attempt_no": self.opened_attempt_no,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "HumanReviewResolutionRecord":
        opened_attempt_no = data.get("opened_attempt_no")
        if opened_attempt_no is not None and (
            not isinstance(opened_attempt_no, int)
            or isinstance(opened_attempt_no, bool)
            or opened_attempt_no <= 0
        ):
            # 破損データ：Noneでも有効なpositive intでもない値は、値の推測を行わず
            # ValueErrorとする（22.1c節、既存のfail-closed規律と同型）。
            raise ValueError(
                f"human_review_resolution.opened_attempt_no is neither None nor a "
                f"positive int: {opened_attempt_no!r}"
            )
        return cls(
            resolution=HumanReviewResolution(data["resolution"]),
            actor=data["actor"],
            note=data.get("note"),
            resolved_at=datetime.fromisoformat(data["resolved_at"]),
            opened_attempt_no=opened_attempt_no,
        )


@dataclass
class RetryLineageMembershipEntry:
    run_id: str
    parent_run_id: str | None
    attempt_no: int
    recorded_at: datetime

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "parent_run_id": self.parent_run_id,
            "attempt_no": self.attempt_no,
            "recorded_at": self.recorded_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RetryLineageMembershipEntry":
        return cls(
            run_id=data["run_id"],
            parent_run_id=data.get("parent_run_id"),
            attempt_no=data["attempt_no"],
            recorded_at=datetime.fromisoformat(data["recorded_at"]),
        )


@dataclass
class RetryLineageTransitionEvent:
    attempt_no: int
    from_phase: RetryLineagePhase | None
    to_phase: RetryLineagePhase
    run_id: str | None
    at: datetime
    detail: str | None = None
    correlation_id: str | None = None  # to_phase==CLAIMEDの遷移イベントにのみ設定される

    def to_dict(self) -> dict:
        return {
            "attempt_no": self.attempt_no,
            "from_phase": self.from_phase.value if self.from_phase else None,
            "to_phase": self.to_phase.value,
            "run_id": self.run_id,
            "at": self.at.isoformat(),
            "detail": self.detail,
            "correlation_id": self.correlation_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RetryLineageTransitionEvent":
        return cls(
            attempt_no=data["attempt_no"],
            from_phase=RetryLineagePhase(data["from_phase"]) if data.get("from_phase") else None,
            to_phase=RetryLineagePhase(data["to_phase"]),
            run_id=data.get("run_id"),
            at=datetime.fromisoformat(data["at"]),
            detail=data.get("detail"),
            correlation_id=data.get("correlation_id"),
        )


@dataclass
class RetryAttemptExecutionScope:
    attempt_no: int
    steps_confirmed_done_before: list[str]
    steps_to_execute: list[str]
    determined_at: datetime

    def to_dict(self) -> dict:
        return {
            "attempt_no": self.attempt_no,
            "steps_confirmed_done_before": list(self.steps_confirmed_done_before),
            "steps_to_execute": list(self.steps_to_execute),
            "determined_at": self.determined_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RetryAttemptExecutionScope":
        return cls(
            attempt_no=data["attempt_no"],
            steps_confirmed_done_before=list(data.get("steps_confirmed_done_before", [])),
            steps_to_execute=list(data.get("steps_to_execute", [])),
            determined_at=datetime.fromisoformat(data["determined_at"]),
        )


@dataclass
class RetryLineageRecord:
    root_run_id: str
    parent_run_id: str | None
    latest_run_id: str
    attempt_count: int
    max_attempts: int
    next_attempt_ordinal: int
    phase: RetryLineagePhase
    terminal_disposition: RetryLineageDisposition | None
    next_eligible_at: datetime | None
    owner_token: str | None
    steps_confirmed_done: list[str]
    membership: list[RetryLineageMembershipEntry] = field(default_factory=list)
    transition_history: list[RetryLineageTransitionEvent] = field(default_factory=list)
    attempt_scopes: list[RetryAttemptExecutionScope] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    side_effect_contract_version: int | None = None  # Release 6.32、18章。create_new_lineage()
    # のみがスタンプし、open_next_attempt()は上書きしない。既存（pre-6.32）lineageはNoneのまま。
    human_review_resolution: "HumanReviewResolutionRecord | None" = None  # Release 6.32、17.2節

    def to_dict(self) -> dict:
        return {
            "root_run_id": self.root_run_id,
            "parent_run_id": self.parent_run_id,
            "latest_run_id": self.latest_run_id,
            "attempt_count": self.attempt_count,
            "max_attempts": self.max_attempts,
            "next_attempt_ordinal": self.next_attempt_ordinal,
            "phase": self.phase.value,
            "terminal_disposition": self.terminal_disposition.value if self.terminal_disposition else None,
            "next_eligible_at": self.next_eligible_at.isoformat() if self.next_eligible_at else None,
            "owner_token": self.owner_token,
            "steps_confirmed_done": list(self.steps_confirmed_done),
            "membership": [m.to_dict() for m in self.membership],
            "transition_history": [t.to_dict() for t in self.transition_history],
            "attempt_scopes": [s.to_dict() for s in self.attempt_scopes],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "side_effect_contract_version": self.side_effect_contract_version,
            "human_review_resolution": (
                self.human_review_resolution.to_dict() if self.human_review_resolution else None
            ),
        }

    def to_json(self) -> str:
        import json
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> "RetryLineageRecord":
        return cls(
            root_run_id=data["root_run_id"],
            parent_run_id=data.get("parent_run_id"),
            latest_run_id=data["latest_run_id"],
            attempt_count=data["attempt_count"],
            max_attempts=data["max_attempts"],
            next_attempt_ordinal=data["next_attempt_ordinal"],
            phase=RetryLineagePhase(data["phase"]),
            terminal_disposition=(
                RetryLineageDisposition(data["terminal_disposition"])
                if data.get("terminal_disposition")
                else None
            ),
            next_eligible_at=(
                datetime.fromisoformat(data["next_eligible_at"])
                if data.get("next_eligible_at")
                else None
            ),
            owner_token=data.get("owner_token"),
            steps_confirmed_done=list(data.get("steps_confirmed_done", [])),
            membership=[RetryLineageMembershipEntry.from_dict(m) for m in data.get("membership", [])],
            transition_history=[
                RetryLineageTransitionEvent.from_dict(t) for t in data.get("transition_history", [])
            ],
            attempt_scopes=[
                RetryAttemptExecutionScope.from_dict(s) for s in data.get("attempt_scopes", [])
            ],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            side_effect_contract_version=data.get("side_effect_contract_version"),
            human_review_resolution=(
                HumanReviewResolutionRecord.from_dict(data["human_review_resolution"])
                if data.get("human_review_resolution")
                else None
            ),
        )
