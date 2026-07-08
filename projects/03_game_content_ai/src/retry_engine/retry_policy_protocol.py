"""
Retry Policy Protocol（v4.5.0）

RetryDecisionPolicy:   再試行すべきかどうかを判定する、あらゆるRetry戦略に
                       共通する最小契約（Protocol）
ExplainableRetryPolicy: RetryDecisionPolicyを拡張し、RetryManager._skip_reason()
                       がスキップ理由の文字列を生成するために必要とする属性
                       （target_statuses / max_attempts）を追加した契約

命名についての注意（混同注意）:
    本ファイルは抽象契約（Protocol）のみを定義する。再試行ルールの具体的な
    実装は引き続き RetryPolicy（retry_policy.py、本Releaseでも無改修）である。
    名称が似ている（RetryDecisionPolicy / ExplainableRetryPolicy vs
    RetryPolicy）ため混同しないこと。RetryPolicy は本ファイルを一切import
    せず、構造的に（Protocolの性質上、明示的な継承なしに）両契約を満たす。

設計方針:
    - Protocol（typing.Protocol）を採用し、既存RetryPolicyへの変更を一切
      発生させない（docs/design/retry_policy_foundation.md 3章 Option比較①）。
    - 「判定」（RetryDecisionPolicy）と「説明に必要な属性の公開」
      （ExplainableRetryPolicy）を2段階に分離する。target_statuses /
      max_attempts は Fixed Retry Policy（RetryPolicy）に根ざした概念であり、
      将来の戦略（Exponential Backoff等）がこの拡張契約まで満たす必要は
      ない。RetryDecisionPolicy（最小契約）のみで足りる
      （同設計書4章 Option比較②、案C）。
    - Stateless。両Protocolともデータを持たない（構造の宣言のみ）。
    - @runtime_checkable を付与し、isinstance() による構造適合の確認を
      可能にする。ただしこれはメソッド・属性の「存在」のみを検証し、
      シグネチャ（引数の型・個数・戻り値の型）までは検証しない。差し替え
      可能性の確認には、isinstance() による構造確認に加えて、実際に
      RetryManager(policy=...).retry(...) を呼び出す振る舞いテストを
      併用すること（同設計書7章・12.5節）。
    - 新しいRetry戦略（FixedRetryPolicy / ExponentialBackoffPolicy /
      AdaptiveRetryPolicy等）の実装は本Releaseの対象外（Non-Goal）。
      本Releaseは差し替え可能な構造の整備のみを行う。
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from workflow_monitor import WorkflowMonitorStatus


@runtime_checkable
class RetryDecisionPolicy(Protocol):
    """
    再試行すべきかどうかを判定する、あらゆるRetry戦略に共通する最小契約。
    RetryManager.retry() が唯一呼び出す判定メソッドのみを要求する。
    """

    def should_retry(self, monitor_status: WorkflowMonitorStatus, attempt: int) -> bool: ...


@runtime_checkable
class ExplainableRetryPolicy(RetryDecisionPolicy, Protocol):
    """
    RetryDecisionPolicyに加え、RetryManager._skip_reason() がスキップ理由の
    文字列を生成するために必要とする属性を公開する契約。

    target_statuses / max_attempts は Fixed Retry Policy（RetryPolicy）に
    根ざした概念であり、将来の戦略がこの契約まで満たす必要はない
    （RetryDecisionPolicyのみで足りる）。
    """

    target_statuses: frozenset[WorkflowMonitorStatus]
    max_attempts: int
