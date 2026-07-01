"""
Workflowパイプライン実行層（v2.3.0）

WorkflowPipelineRunner: WorkflowRunner.run() を直接呼び出す実行層

変換の流れ:
    WorkflowPipelineRunner
        ↓
    WorkflowRunner.run()
        ↓
    WorkflowResult
        ↓
    PipelineResult

設計方針:
    - subprocessは使わない。NewsPipelineRunner がsubprocessを使うのは main.py の
      argparse/sys.exit問題を避けるためであり、WorkflowRunner にはその問題がない
      （通常のPythonクラス。sys.exit()もCLI引数解析も内部に持たない）。
    - WorkflowPipelineRunner が WorkflowRunner を呼び出すことは、Pipeline層が実行対象を
      呼び出す責務を持つため許容される。重要なのは、Agent層（WorkflowTriggerAgent）が
      WorkflowRunner を直接知らないことである。
    - WorkflowConfig / WorkflowRunner のimportは run() 内で遅延させる。
      本ファイルはトップレベルでは ai 層をimportしない
      （agent_manager.py 等が `from pipeline import NewsPipelineRunner` を経由して
      pipeline層をimportする既存の依存関係があるため、将来 pipeline/__init__.py が
      WorkflowPipelineRunner をexportするようになった際の
      pipeline → ai → pipeline という循環importを避けるための措置）。
    - config は実行に必要な属性（project_root）を持つオブジェクトであれば何でもよい
      形（ダックタイピング）にしている（NewsPipelineRunner の _RunnerConfig と同じ考え方）。
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Protocol

from .pipeline_result import PipelineResult


class _RunnerConfig(Protocol):
    """WorkflowPipelineRunner が実行に必要とする設定値の形。"""
    project_root: Path


class WorkflowPipelineRunner:
    """WorkflowRunner.run() を直接呼び出し、結果を PipelineResult として返す実行層。"""

    def __init__(self, config: _RunnerConfig):
        self._config = config

    def run(self, params: dict[str, object] | None = None) -> PipelineResult:
        """
        WorkflowRunner を構築・実行し、結果を PipelineResult として返す。

        Args:
            params: 呼び出し元（WorkflowTriggerAgent）から渡されるパラメータ。
                    "article_id"（絞り込む記事ID）、"dry_run"（WorkflowRunner.run()
                    自体に渡すdry_run。Agent経由のdry_runとは別概念）を受け取る。
        """
        params = params or {}
        article_id = params.get("article_id")
        dry_run = bool(params.get("dry_run", False))

        start = time.time()
        try:
            from ai import WorkflowConfig, WorkflowRunner

            workflow_config = WorkflowConfig.from_env(base_dir=self._config.project_root)
            runner = WorkflowRunner.from_config(workflow_config)
            workflow_result = runner.run(article_id=article_id, dry_run=dry_run)
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
        error_message = (
            None if workflow_result.overall_success
            else "Workflow completed with failed steps."
        )

        return PipelineResult(
            success=workflow_result.overall_success,
            returncode=None,
            elapsed_sec=elapsed_sec,
            stdout_log_path=None,
            stderr_log_path=None,
            error_message=error_message,
        )
