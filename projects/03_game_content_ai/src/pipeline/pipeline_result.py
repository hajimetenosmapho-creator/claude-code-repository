"""
Pipeline実行結果（v2.2.0）

PipelineResult: PipelineRunner（NewsPipelineRunner等）が返す実行結果を保持するデータクラス

設計方針:
    - Agent層の型（AgentResult等）とは独立した型として定義する。
      Pipeline層（src/pipeline/）はAgent層に依存しない実行手段の抽象化であり、
      Agent層のデータモデルを知らない設計にするため。
    - stdout / stderr の全文は保持せず、保存先のログファイルパスのみを保持する
      （PipelineResultが肥大化するのを防ぐため）。

フィールド:
    success:          実行が成功したか（returncode == 0）
    returncode:       子プロセスの終了コード（タイムアウト時は None）
    elapsed_sec:      実行にかかった秒数
    stdout_log_path:  標準出力を保存したログファイルのパス（保存できなかった場合は None）
    stderr_log_path:  標準エラー出力を保存したログファイルのパス（保存できなかった場合は None）
    error_message:    失敗時のメッセージ（成功時は None）
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PipelineResult:
    success: bool
    returncode: int | None
    elapsed_sec: float
    stdout_log_path: Path | None
    stderr_log_path: Path | None
    error_message: str | None

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "returncode": self.returncode,
            "elapsed_sec": self.elapsed_sec,
            "stdout_log_path": str(self.stdout_log_path) if self.stdout_log_path else None,
            "stderr_log_path": str(self.stderr_log_path) if self.stderr_log_path else None,
            "error_message": self.error_message,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
