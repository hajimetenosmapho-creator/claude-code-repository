"""
Newsパイプライン実行層（v2.2.0）

NewsPipelineRunner: 既存のニュース収集パイプライン（main.py）をサブプロセスとして起動する実行層

設計方針:
    - NewsAgent（判断層）と NewsPipelineRunner（実行層）を分離する。
      NewsAgent は「実行すべきか」の判断のみを行い、実際の起動方法（subprocess等）は
      すべて NewsPipelineRunner に閉じ込める（責務の混同を避けるため）。
    - main_py_path / working_directory / python_executable / timeout_sec はすべて
      コンストラクタで渡される設定値（NewsAgentConfig）から取得し、
      NewsPipelineRunner 自身はファイル名や実行環境を決め打ちしない
      （将来 main.py 以外のパイプラインにも同じ実行層の形を再利用できるようにするため）。
    - AgentContext / AgentDecision / AgentResult 等の Agent 層の型、および
      WorkflowRunner は一切importしない（Pipeline層はAgent層から呼び出される側であり、
      逆方向の依存を作らないため）。設定値の受け渡しは型を固定せず、
      実行に必要な4属性（python_executable / main_py_path / working_directory / timeout_sec）
      を持つオブジェクトであれば何でもよい形（ダックタイピング）にしている。
    - main.py 本体には一切手を加えない。サブプロセスとして隔離することで、
      main.py 内部の sys.exit() 呼び出しや argparse の sys.argv 依存が
      呼び出し元プロセス（Agent側）に影響しないようにする。
"""
from __future__ import annotations

import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Protocol

from .pipeline_result import PipelineResult

LOG_SUBDIR = "logs/news_agent"


class _RunnerConfig(Protocol):
    """NewsPipelineRunner が実行に必要とする設定値の形（Agent層の型への依存を避けるためのProtocol）。"""
    python_executable: Path
    main_py_path: Path
    working_directory: Path
    timeout_sec: int


class NewsPipelineRunner:
    """main.py をサブプロセスとして起動し、結果を PipelineResult として返す実行層。"""

    def __init__(self, config: _RunnerConfig):
        self._config = config

    def run(self, params: dict) -> PipelineResult:
        """
        main.py を起動し、実行結果を PipelineResult として返す。

        Args:
            params: 呼び出し元（NewsAgent）から渡されるパラメータ。
                    "max_articles" キーがあれば main.py に --max-articles として渡す。
        """
        cmd = [
            str(self._config.python_executable),
            str(self._config.main_py_path),
        ]
        max_articles = params.get("max_articles")
        if max_articles is not None:
            cmd += ["--max-articles", str(max_articles)]

        run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        start = time.time()

        try:
            completed = subprocess.run(
                cmd,
                cwd=self._config.working_directory,
                capture_output=True,
                text=True,
                timeout=self._config.timeout_sec,
            )
        except subprocess.TimeoutExpired as e:
            elapsed = time.time() - start
            stdout_path = self._save_log(run_timestamp, "stdout", e.stdout)
            stderr_path = self._save_log(run_timestamp, "stderr", e.stderr)
            return PipelineResult(
                success=False,
                returncode=None,
                elapsed_sec=elapsed,
                stdout_log_path=stdout_path,
                stderr_log_path=stderr_path,
                error_message=f"タイムアウトしました（{self._config.timeout_sec}秒）",
            )

        elapsed = time.time() - start
        stdout_path = self._save_log(run_timestamp, "stdout", completed.stdout)
        stderr_path = self._save_log(run_timestamp, "stderr", completed.stderr)
        success = completed.returncode == 0

        return PipelineResult(
            success=success,
            returncode=completed.returncode,
            elapsed_sec=elapsed,
            stdout_log_path=stdout_path,
            stderr_log_path=stderr_path,
            error_message=None if success else (completed.stderr or "")[-500:],
        )

    def _save_log(self, run_timestamp: str, kind: str, content: str | None) -> Path | None:
        """stdout/stderr を working_directory 配下の logs/news_agent/ に保存する。"""
        try:
            log_dir = self._config.working_directory / LOG_SUBDIR
            log_dir.mkdir(parents=True, exist_ok=True)
            path = log_dir / f"{run_timestamp}_{kind}.log"
            path.write_text(content or "", encoding="utf-8")
            return path
        except OSError:
            return None
