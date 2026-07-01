"""
Publish Trigger Agent設定（v2.4.0）

PublishTriggerAgentConfig: PublishTriggerAgent / PublishPipelineRunner が使用する設定値のみを保持するデータクラス

設計方針:
    - 設定値のみを保持する（実行時状態は AgentContext / PipelineResult が担う）
    - Configuration First: 三重ゲート方式の2段目（PUBLISH_TRIGGER_AGENT_ENABLED）をここで判定する
      （1段目の AI_AGENT_ENABLED は AgentConfig が担う。AgentManager側で両方をチェックする）
    - publish_enabled は既存の AiPublishConfig.is_ready() をそのまま再利用し、
      AI_PUBLISH_ENABLED / WordPress認証情報の判定ロジックを重複実装しない
      （AiPublishConfig とのズレを防ぐため。WorkflowTriggerAgentConfig が
      WorkflowConfig.is_ready() を再利用する設計と同じ考え方）
    - reports_dir は outputs/ai_publish_reports/ を指すが、is_ready() 判定では
      存在確認をしない（未実行で存在しない場合も「過去実行なし」として判断できるようにするため。
      実際の存在確認は PublishTriggerAgent.decide() 側の責務とする）
    - decide() は時間間隔方式（reports_dir 内 *.md の最終更新日時 と min_interval_minutes の比較）
      を採用する。未投稿の ADOPTED レビュー件数を見る方式は今回は採用しない
      （Agent が Publish 実処理側のデータ構造 [AiPublishRepository 等] を直接見に行く
      責務を持たないようにするため。将来の改善候補として記録のみ残す）

環境変数:
    PUBLISH_TRIGGER_AGENT_ENABLED               (default: false)
    PUBLISH_TRIGGER_AGENT_MIN_INTERVAL_MINUTES  (default: 1440)
    AI_PUBLISH_ENABLED                          (default: false。AiPublishConfigと共有する環境変数)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .ai_publish_config import AiPublishConfig


@dataclass
class PublishTriggerAgentConfig:
    enabled: bool
    min_interval_minutes: int
    reports_dir: Path
    publish_enabled: bool
    project_root: Path

    @classmethod
    def from_env(cls, project_root: Path) -> "PublishTriggerAgentConfig":
        """
        環境変数から PublishTriggerAgentConfig を構築する。

        Args:
            project_root: 03_game_content_ai のプロジェクトルート（outputs/ が置かれているディレクトリ）
        """
        enabled = os.environ.get("PUBLISH_TRIGGER_AGENT_ENABLED", "false").lower() == "true"
        min_interval_minutes = int(
            os.environ.get("PUBLISH_TRIGGER_AGENT_MIN_INTERVAL_MINUTES", "1440")
        )
        publish_enabled = AiPublishConfig.from_env().is_ready()

        return cls(
            enabled=enabled,
            min_interval_minutes=min_interval_minutes,
            reports_dir=project_root / "outputs" / "ai_publish_reports",
            publish_enabled=publish_enabled,
            project_root=project_root,
        )

    def is_ready(self) -> bool:
        """
        PublishTriggerAgentが実行可能な状態か返す（三重ゲートの2段目 + AiPublish自体の有効性）。

        reports_dir が現時点でディスク上に存在するかどうかは判定に含めない。
        初回実行（レポート未生成）の場合でも is_ready()=True とし、
        「過去実行なし＝初回実行と判断」という decide() 側の判断に委ねる。
        """
        return self.enabled and self.publish_enabled
