"""
Post-Codex-delta-review Amendment: exact env isolation契約。

Codex delta review（NOT APPROVED、Major#1・Major#3）が指摘した2点への対応：
1. Scenario B・Dのretry phaseが「テストハーネス自身のos.environへ必要な値を
   overlayするだけ」であったため、host由来のPYTHONPATHや絶対path override等の
   ambient変数がmain.py実subprocessへ`{**os.environ,...}`経由でそのまま漏れ
   得た（`src/pipeline/news_pipeline_runner.py:130`）。`ExactEnv`は
   overlayではなく`os.environ`を完全に置換し、終了時に完全復元することで、
   in-process構築（同一プロセス内でのWorkflowEngineManager/
   RetryCompositionRoot直接構築、6.16a節）を維持したまま、closed allowlist
   subprocess env（Scenario A/C/D-handshake-worker/F1/F2）と同水準の隔離を
   実現する。
2. `APPDATA`にhostの実値をそのまま渡すと、インストール済みAnthropic SDKが
   hostの実際のAnthropic active-config pointerを読みに行きうる
   （`venv/Lib/site-packages/anthropic/lib/credentials/_constants.py`）。
   `make_scenario_appdata_dir()`は、シナリオ専用の空ディレクトリを新規に
   用意し、SDKの`_config_dir()`が要求するディレクトリ探索のみを満たしつつ、
   host設定を一切露出しない。
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path


def make_scenario_appdata_dir() -> Path:
    """シナリオ専用の空APPDATAディレクトリを新規作成する（host実値は使わない）。"""
    return Path(tempfile.mkdtemp(prefix="scenario_appdata_"))


def cleanup_scenario_appdata_dir(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


def base_windows_vars(appdata_dir: Path) -> dict:
    """Windows subprocess起動に必須の基盤変数（SystemRoot・PATHはhost実値、
    APPDATAはscenario-owned empty directory）。"""
    env = {}
    for key in ("SystemRoot", "PATH"):
        if key in os.environ:
            env[key] = os.environ[key]
    env["APPDATA"] = str(appdata_dir)
    return env


class ExactEnv:
    """os.environを完全に置換し、終了時に完全復元する（overlayではない）。

    Scenario B・DのようにWorkflowEngineManager/RetryCompositionRootを
    テストハーネス自身のプロセス内で直接構築するシナリオ専用。`with`ブロック
    に入った瞬間、host由来の変数を含む既存のos.environは一旦退避され、
    `updates`で指定した値のみが有効なos.environとなる。ブロックを抜けると
    （正常終了・例外いずれの経路でも）元のos.environへ完全に復元される。
    """

    def __init__(self, updates: dict):
        self._updates = dict(updates)
        self._saved: dict | None = None

    def __enter__(self) -> "ExactEnv":
        self._saved = dict(os.environ)
        os.environ.clear()
        os.environ.update(self._updates)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        assert self._saved is not None
        os.environ.clear()
        os.environ.update(self._saved)
