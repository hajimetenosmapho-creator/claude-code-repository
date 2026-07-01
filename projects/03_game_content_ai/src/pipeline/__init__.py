"""
Pipeline実行層パッケージ（v2.2.0）

既存の各種処理（ニュース収集パイプライン等）を、Agent層に依存しない形で
起動・監視するための実行層。BaseAgent実装（NewsAgent等）から呼び出される。

設計方針:
    - Agent層（src/ai/）の型・WorkflowRunnerを一切importしない。
      Pipeline層はAgent層から呼び出される側であり、逆方向の依存を作らない。
    - 各Runnerは run(params: dict) -> PipelineResult という共通の形で結果を返す。
      将来 Workflow Trigger Agent / Publish Agent / Scheduler Agent 等が追加された際も、
      同じ形のRunnerをこのパッケージに追加していくことを想定している。
"""
from .pipeline_result import PipelineResult
from .news_pipeline_runner import NewsPipelineRunner

__all__ = [
    "PipelineResult",
    "NewsPipelineRunner",
]
