"""
Workflow Engine Post-Admission Hook定義（v6.31.0、Release 6.31）

PostAdmissionHookResult: post-admission hookの戻り値
PostAdmissionHook:       post-admission hookの型エイリアス

設計方針（docs/design/retry_lineage_eligibility_durable_attempt_state.md 10.1〜10.2章）:
    - hookは`start_run()` ack確認の直後、step実行ループの直前に、
      `WorkflowEngineExecutor.run()`から`run_id`のみを引数に呼ばれる
      （`Callable[[str], PostAdmissionHookResult]`）。
    - hookは`WorkflowEngineContext.post_admission_hook`（呼び出しごとの値、
      省略時None）として渡される。`WorkflowEngineExecutor`のコンストラクタでは
      保持しない——同一の`WorkflowEngineExecutor`インスタンスが、hookを必要と
      しない非retry呼び出し元（`scripts/run_workflow_engine.py`等）と、
      呼び出しごとに異なるlineage/attempt文脈を持つRetryExecutor経由の呼び出しの
      両方から共有されるため、hookをExecutor構築時ではなく呼び出しごとの
      Context値として受け渡す（`RetryExecutor`が`claim()`結果ごとに新しい
      hookクロージャを構築し、`WorkflowEngineManager.run(..., post_admission_hook=hook)`
      経由で渡す）。
    - hookがNone（既存の全非retry呼び出し元）の場合、Executorはhook呼び出し自体を
      スキップし、既存の挙動を完全に維持する（Zero-Diff）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class PostAdmissionHookResult:
    acknowledged: bool


PostAdmissionHook = Callable[[str], PostAdmissionHookResult]
