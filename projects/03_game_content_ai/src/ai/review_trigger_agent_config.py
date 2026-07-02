"""
Review Trigger Agent設定（v2.5.0）

ReviewTriggerAgentConfig: ReviewTriggerAgent / ReviewPipelineRunner が使用する設定値のみを保持するデータクラス

設計方針:
    - 設定値のみを保持する（実行時状態は AgentContext / PipelineResult が担う）
    - Configuration First: 二重ゲート方式（REVIEW_TRIGGER_AGENT_ENABLED）をここで判定する
      （1段目の AI_AGENT_ENABLED は AgentConfig が担う。AgentManager側で両方をチェックする）
    - AiPublishReviewService には Config クラス / is_ready() が存在しないため、
      WorkflowTriggerAgentConfig / PublishTriggerAgentConfig のように既存Configの
      is_ready() を再利用する3段目は持たない（無理に三重ゲートへ寄せない）。
      is_ready() は self.enabled のみを返す
    - reports_dir は outputs/ai_publish_review_reports/ を指すが、is_ready() 判定では
      存在確認をしない（未実行で存在しない場合も「過去実行なし」として判断できるようにするため。
      実際の存在確認は ReviewTriggerAgent.decide() 側の責務とする）
    - decide() は時間間隔方式（reports_dir 内 *.md の最終更新日時 と min_interval_minutes の比較）
      を採用する。未レビュー件数・入力/出力差分を見る方式は今回は採用しない
      （Agent が Review 実処理側のデータ構造 [AiPublishReviewRepository 等] を直接見に行く
      責務を持たないようにするため。将来の改善候補として記録のみ残す）

環境変数:
    REVIEW_TRIGGER_AGENT_ENABLED               (default: false)
    REVIEW_TRIGGER_AGENT_MIN_INTERVAL_MINUTES  (default: 1440)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ReviewTriggerAgentConfig:
    enabled: bool
    min_interval_minutes: int
    reports_dir: Path
    project_root: Path

    @classmethod
    def from_env(cls, project_root: Path) -> "ReviewTriggerAgentConfig":
        """
        環境変数から ReviewTriggerAgentConfig を構築する。

        Args:
            project_root: 03_game_content_ai のプロジェクトルート（outputs/ が置かれているディレクトリ）
        """
        enabled = os.environ.get("REVIEW_TRIGGER_AGENT_ENABLED", "false").lower() == "true"
        min_interval_minutes = int(
            os.environ.get("REVIEW_TRIGGER_AGENT_MIN_INTERVAL_MINUTES", "1440")
        )

        return cls(
            enabled=enabled,
            min_interval_minutes=min_interval_minutes,
            reports_dir=project_root / "outputs" / "ai_publish_review_reports",
            project_root=project_root,
        )

    def is_ready(self) -> bool:
        """
        ReviewTriggerAgentが実行可能な状態か返す（二重ゲートの2段目）。

        AiPublishReviewService には is_ready() 相当の判定が存在しないため、
        self.enabled のみを返す（WorkflowTriggerAgentConfig / PublishTriggerAgentConfig
        のような enabled and xxx_enabled という2項判定にはならない）。

        reports_dir が現時点でディスク上に存在するかどうかは判定に含めない。
        初回実行（レポート未生成）の場合でも is_ready()=True とし、
        「過去実行なし＝初回実行と判断」という decide() 側の判断に委ねる。
        """
        return self.enabled
