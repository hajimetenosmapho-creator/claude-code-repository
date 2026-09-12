"""
Retry Lineage Disposition定義（v6.31.0、Release 6.31）

RetryLineageDisposition: 1 attemptのterminal dispositionを表すEnum

設計方針（docs/design/retry_lineage_eligibility_durable_attempt_state.md 9.8.1・11.5章）:
    - SUCCEEDED：全executed stepがGENUINE_SUCCESS（NOT_APPLICABLE/INTENTIONAL_NO_ACTIONは許容）。
    - FAILED：いずれかのstepがRETRYABLE_FAILUREまたはUNKNOWN（fail-closed）。
    - NOT_ACTIONED：いずれのstepもRETRYABLE_FAILURE/UNKNOWNではないが、いずれかが
      SILENT_NO_ACTION（interval guard等によるgenuineなno-op）。
    - FAILED・NOT_ACTIONEDのみがretryable（is_retryable()、9.8.1.2章）。paybackは
      行わない（NOT_ACTIONEDもattempt_countを消費する、9.8.1.3章）。
"""
from __future__ import annotations

from enum import Enum


class RetryLineageDisposition(Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    NOT_ACTIONED = "not_actioned"
    HUMAN_REVIEW_REQUIRED = "human_review_required"  # Release 6.32、13章
