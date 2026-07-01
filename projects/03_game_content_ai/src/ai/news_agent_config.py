"""
News Agent設定（v2.2.0）

NewsAgentConfig: NewsAgent / NewsPipelineRunner が使用する設定値のみを保持するデータクラス

設計方針:
    - 設定値のみを保持する（実行時状態は AgentContext / PipelineResult が担う）
    - Configuration First: AgentConfig と同様、既存フローに影響を与えない安全側のデフォルト値とする
    - main_py_path / working_directory / python_executable を明示的に持たせることで、
      NewsPipelineRunner がファイル名・実行環境を決め打ちしない設計にする
      （main.py 固有の実行手段を NewsAgentConfig 側に閉じ込め、Runner は値を使うだけにする）

環境変数:
    NEWS_AGENT_MIN_INTERVAL_MINUTES  (default: 180)
    NEWS_AGENT_TIMEOUT_SEC           (default: 1800)
    NEWS_AGENT_LOG_LOOKBACK_DAYS     (default: 2)
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class NewsAgentConfig:
    min_interval_minutes: int
    timeout_sec: int
    log_lookback_days: int
    main_py_path: Path
    working_directory: Path
    python_executable: Path

    @classmethod
    def from_env(cls, project_root: Path) -> "NewsAgentConfig":
        """
        環境変数から NewsAgentConfig を構築する。

        Args:
            project_root: 03_game_content_ai のプロジェクトルート（main.py が置かれているディレクトリ）
        """
        min_interval_minutes = int(os.environ.get("NEWS_AGENT_MIN_INTERVAL_MINUTES", "180"))
        timeout_sec = int(os.environ.get("NEWS_AGENT_TIMEOUT_SEC", "1800"))
        log_lookback_days = int(os.environ.get("NEWS_AGENT_LOG_LOOKBACK_DAYS", "2"))

        return cls(
            min_interval_minutes=min_interval_minutes,
            timeout_sec=timeout_sec,
            log_lookback_days=log_lookback_days,
            main_py_path=project_root / "main.py",
            working_directory=project_root,
            python_executable=Path(sys.executable),
        )
