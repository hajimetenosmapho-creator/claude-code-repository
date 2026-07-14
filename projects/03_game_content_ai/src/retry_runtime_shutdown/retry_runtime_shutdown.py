"""
Retry Runtime Shutdown（v6.1.0）

RetryRuntimeShutdown: --loop実行中のRetry Runtimeに対して、Graceful Shutdown
                       （実行中サイクルは完了させたうえで、次のサイクルを
                       開始せず終了する）を実現するための、Retryドメインを
                       一切知らない汎用コンポーネント。

設計方針（docs/design/retry_runtime_graceful_shutdown_foundation.md）:
    - 本クラスの責務は「停止シグナルの受信検知（フラグ管理）」と、
      RetryRuntimeLoopへそのまま渡せる should_continue_fn / sleep_fn
      相当の2メソッドの提供のみに限定する（2章 Component Responsibilities）。
    - RetryRuntimeLoopは本クラスの存在を一切知らず、本クラスもRetryRuntimeLoopの
      存在を一切知らない。両者はDI（Constructor Injectionされた関数参照）
      のみで接続される（1.2節）。
    - Signal Registration（install/uninstall）とSignal Handling（_handle）を
      メソッド単位で分離する（2.1節）。_handle()はフラグを立てるのみで、
      I/Oは一切行わない（シグナルセーフ性への配慮）。
    - 状態はRUNNING/SHUTDOWN_REQUESTEDの2値のみをboolで表現する。STOPPEDは
      本クラスの外側（RetryRuntimeLoop.run()の呼び出し元）で判定される
      状態であり、本クラス自身の内部状態には含まれない（1.3節）。
    - RetryCompositionRoot / RetryRuntimeOrchestrator / RetryRuntimeLoop /
      RetryManager等、他のretry_*パッケージのいずれにも依存しない。
    - install()は個々のシグナル登録の失敗（プラットフォーム非対応等）に対して
      ベストエフォートとし、例外を送出しない（5章 Failure Handling）。
"""
from __future__ import annotations

import signal
import time
from typing import Optional


class RetryRuntimeShutdown:
    """
    停止シグナルの受信検知と、RetryRuntimeLoopへ渡すための
    should_continue_fn / sleep_fn の提供のみを行う、Retryドメインを
    一切知らない汎用コンポーネント。
    """

    def __init__(self, poll_interval_seconds: float = 0.5):
        self._requested = False
        self._signal_name: Optional[str] = None
        self._poll_interval_seconds = poll_interval_seconds
        self._previous_handlers: dict = {}

    # ─── Signal Registration ───

    def install(self) -> None:
        """
        プラットフォームで利用可能な停止シグナル（SIGINT、及び対応する
        場合はSIGTERM／SIGBREAK）にハンドラを登録する。

        個々のシグナルが登録できない場合（プラットフォーム非対応、
        メインスレッド以外からの呼び出し等）はそのシグナルの登録のみ
        スキップし、他のシグナルの登録は継続する（ベストエフォート。
        全滅した場合でも例外は送出しない）。
        """
        for sig in self._candidate_signals():
            try:
                previous = signal.signal(sig, self._handle)
            except (ValueError, OSError, AttributeError):
                continue
            self._previous_handlers[sig] = previous

    def uninstall(self) -> None:
        """
        install()前のシグナルハンドラへ復元する。主にテストでの
        グローバル状態リークを防ぐために使用する。
        """
        for sig, previous in self._previous_handlers.items():
            try:
                signal.signal(sig, previous)
            except (ValueError, OSError, AttributeError):
                pass
        self._previous_handlers.clear()

    @staticmethod
    def _candidate_signals() -> list:
        candidates = [signal.SIGINT]
        sigterm = getattr(signal, "SIGTERM", None)
        if sigterm is not None:
            candidates.append(sigterm)
        sigbreak = getattr(signal, "SIGBREAK", None)
        if sigbreak is not None:
            candidates.append(sigbreak)
        return candidates

    # ─── Signal Handling ───

    def _handle(self, signum, frame) -> None:
        """
        シグナル受信時に呼ばれる。フラグを立てるのみでI/Oは行わない。
        """
        self._requested = True
        if self._signal_name is None:
            self._signal_name = self._signal_display_name(signum)

    @staticmethod
    def _signal_display_name(signum) -> str:
        try:
            return signal.Signals(signum).name
        except ValueError:
            return str(signum)

    # ─── RetryRuntimeLoopへ渡す2メソッド（DIのみで接続。1.2節） ───

    @property
    def requested(self) -> bool:
        """停止要求を受信済みかどうか（SHUTDOWN_REQUESTED状態かどうか）。"""
        return self._requested

    @property
    def signal_name(self) -> Optional[str]:
        """受信したシグナル名（未受信の場合はNone）。終了メッセージ表示用。"""
        return self._signal_name

    def should_continue(self) -> bool:
        """RetryRuntimeLoopのshould_continue_fnとしてそのまま渡す。"""
        return not self._requested

    def interruptible_sleep(self, seconds: float) -> None:
        """
        RetryRuntimeLoopのsleep_fnとしてそのまま渡す。poll_interval_seconds
        単位で停止要求を確認しながら待機し、停止要求を受信した時点で
        残り時間を待たずに即座にreturnする。停止要求を受信しない場合の
        合計待機時間はseconds（time.sleepとほぼ同一、ポーリング粒度分の
        誤差を除く）。
        """
        remaining = seconds
        while remaining > 0 and not self._requested:
            chunk = min(self._poll_interval_seconds, remaining)
            time.sleep(chunk)
            remaining -= chunk
