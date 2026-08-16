"""
Article Media Upload State Config定義（v6.28.0）

Source of Truth: docs/design/article_media_upload_state_foundation.md

設計方針:
    - 本Foundationはconsumer-lessであり、既存runtime（main.py等）からのFeature Gateを
      持たない（enabled/disabledの概念がない。呼び出し元が存在しないため）。
    - Configはpersistence先ディレクトリのみを保持する最小構成とする。

環境変数:
    ARTICLE_MEDIA_UPLOAD_STATE_DIR  (default: logs/article_media_upload_state)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_DEFAULT_BASE_DIR = str(Path("logs") / "article_media_upload_state")


@dataclass
class ArticleMediaUploadStateConfig:
    base_dir: Path

    @classmethod
    def from_env(cls) -> "ArticleMediaUploadStateConfig":
        """環境変数から ArticleMediaUploadStateConfig を構築する。"""
        base_dir = Path(os.environ.get("ARTICLE_MEDIA_UPLOAD_STATE_DIR", _DEFAULT_BASE_DIR))
        return cls(base_dir=base_dir)
