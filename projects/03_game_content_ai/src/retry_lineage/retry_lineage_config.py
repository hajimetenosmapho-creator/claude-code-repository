"""
Retry Lineage設定（v6.31.0、Release 6.31）

RetryLineageConfig: Retry Lineage機能の有効・無効と保存先を保持するデータクラス

設計方針（docs/design/retry_lineage_eligibility_durable_attempt_state.md 9.1・16章）:
    - デフォルトは enabled=False（Retry Engine自体の RETRY_ENGINE_ENABLED と同じ
      「安全側で止める」原則。lineage stateはWorkflowを実際に再実行する契機になる）。
    - RETRY_LINEAGE_ENABLED=false（デフォルト）でも`reconcile_all()`自体は動作継続
      する仕様（16章）。ゲートが閉じている影響を受けるのは`claim()`のみ
      （fail-closedスイッチ）。

環境変数:
    RETRY_LINEAGE_ENABLED  (default: false)
    RETRY_LINEAGE_DIR      (default: state/retry_lineage、project_root からの相対パス)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RetryLineageConfig:
    enabled: bool
    lineage_dir: Path

    @classmethod
    def from_env(cls, project_root: Path) -> "RetryLineageConfig":
        """環境変数から RetryLineageConfig を構築する。"""
        enabled = os.environ.get("RETRY_LINEAGE_ENABLED", "false").lower() == "true"
        dir_name = os.environ.get("RETRY_LINEAGE_DIR", "state/retry_lineage")
        return cls(enabled=enabled, lineage_dir=project_root / dir_name)

    def is_ready(self) -> bool:
        """claim()（新規attempt許可）を行ってよいか（ゲートが開いているか）を返す。"""
        return self.enabled

    @property
    def store_dir(self) -> Path:
        return self.lineage_dir / "lineages"

    @property
    def store_lock_path(self) -> Path:
        return self.lineage_dir / ".store.lock"

    @property
    def execution_lock_path(self) -> Path:
        return self.lineage_dir / ".execution.lock"
