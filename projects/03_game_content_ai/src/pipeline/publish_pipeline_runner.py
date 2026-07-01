"""
Publishパイプライン実行層（v2.4.0）

PublishPipelineRunner: AiPublishService.run() を直接呼び出す実行層

変換の流れ:
    PublishPipelineRunner
        ↓
    AiPublishService.run()
        ↓
    Path | None（保存したMarkdownレポートのパス）
        ↓
    PipelineResult

設計方針:
    - subprocessは使わない（WorkflowPipelineRunner と同じ理由。AiPublishService は
      通常のPythonクラスであり、sys.exit()もCLI引数解析も内部に持たない）。
    - PublishPipelineRunner が AiPublishService を呼び出すことは、Pipeline層が実行対象を
      呼び出す責務を持つため許容される。重要なのは、Agent層（PublishTriggerAgent）が
      AiPublishService を直接知らないことである。
    - AiPublishService のimportは run() 内で遅延させる。
      本ファイルはトップレベルでは ai 層をimportしない
      （WorkflowPipelineRunner と同じく、pipeline → ai → pipeline という
      循環importを避けるための措置）。
    - AiPublishService.run() / get_results() のシグネチャは一切変更しない。
      PublishPipelineRunner は薄い委譲ラッパーに徹する（実処理ロジックは持たない）。
    - success の判定は「保存したレポートのパスが返ってきたか（report_path is not None）」
      のみを根拠にする。AiPublishService.get_results() は article_id 絞り込みだけで
      過去の全投稿履歴を返す（今回の実行分だけではない）ため、この結果件数を
      success 判定に使うと過去の失敗まで巻き込んでしまう。そのため get_results() は
      「保存結果を読み戻せるか（正常に完了したか）」の確認目的でのみ呼び出す。
    - config は実行に必要な属性（project_root）を持つオブジェクトであれば何でもよい
      形（ダックタイピング）にしている（WorkflowPipelineRunner の _RunnerConfig と同じ考え方）。
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Protocol

from .pipeline_result import PipelineResult


class _RunnerConfig(Protocol):
    """PublishPipelineRunner が実行に必要とする設定値の形。"""
    project_root: Path


class PublishPipelineRunner:
    """AiPublishService.run() を直接呼び出し、結果を PipelineResult として返す実行層。"""

    def __init__(self, config: _RunnerConfig):
        self._config = config

    def run(self, params: dict[str, object] | None = None) -> PipelineResult:
        """
        AiPublishService を構築・実行し、結果を PipelineResult として返す。

        Args:
            params: 呼び出し元（PublishTriggerAgent）から渡されるパラメータ。
                    "article_id"（絞り込む記事ID）を受け取る。
        """
        params = params or {}
        article_id = params.get("article_id")

        start = time.time()
        try:
            from ai import AiPublishService

            service = AiPublishService.from_env(base_dir=self._config.project_root)
            report_path = service.run(article_id=article_id)
            service.get_results(article_id=article_id)
        except Exception as e:
            return PipelineResult(
                success=False,
                returncode=None,
                elapsed_sec=time.time() - start,
                stdout_log_path=None,
                stderr_log_path=None,
                error_message=str(e),
            )

        elapsed_sec = time.time() - start
        success = report_path is not None
        error_message = None if success else "Publish report was not saved."

        return PipelineResult(
            success=success,
            returncode=None,
            elapsed_sec=elapsed_sec,
            stdout_log_path=None,
            stderr_log_path=None,
            error_message=error_message,
        )
