"""
Pipeline実行層パッケージ（v2.2.0 / v2.3.0 / v2.4.0）

既存の各種処理（ニュース収集パイプライン、WorkflowRunner、AiPublishService等）を
実行するための実行層。BaseAgent実装（NewsAgent / WorkflowTriggerAgent /
PublishTriggerAgent等）から呼び出される。

設計方針:
    - NewsPipelineRunner は Agent層（src/ai/）の型・WorkflowRunnerを一切importしない。
    - WorkflowPipelineRunner が WorkflowRunner を、PublishPipelineRunner が
      AiPublishService を呼び出すことは、Pipeline層が実行対象を呼び出す責務を持つため
      許容される（run()内での遅延importにより、pipeline → ai → pipeline という
      循環importは発生しない）。重要なのは、Agent層（WorkflowTriggerAgent /
      PublishTriggerAgent）が実行対象（WorkflowRunner / AiPublishService）を
      直接知らないことである。
    - 各Runnerは run(params: dict) -> PipelineResult という共通の形で結果を返す。
      将来 Scheduler Agent 等が追加された際も、
      同じ形のRunnerをこのパッケージに追加していくことを想定している。
"""
from .pipeline_result import PipelineResult
from .news_pipeline_runner import NewsPipelineRunner
from .workflow_pipeline_runner import WorkflowPipelineRunner
from .publish_pipeline_runner import PublishPipelineRunner

__all__ = [
    "PipelineResult",
    "NewsPipelineRunner",
    "WorkflowPipelineRunner",
    "PublishPipelineRunner",
]
