"""
画像生成機能の有効/無効を制御するConfiguration-First Gate。

Source of Truth:
    docs/design/image_generation_configuration_gate_foundation.md
    （Architecture Review：Approved）

Consumer-less Foundation: Production Runtimeへの配線は行わない。
enabledのみを保持し、Provider APIキーやタイムアウト設定は読み取らない
（それらはOpenAIImageGeneratorの`from_env()`の責務のまま維持する）。
不正値・未設定はいずれもFalseとして扱い、例外は送出しない（Fail Closed）。
"""
import os
from dataclasses import dataclass

_ENV_ENABLED = "AI_IMAGE_GENERATION_ENABLED"


@dataclass(frozen=True)
class ImageGenerationConfig:
    """画像生成機能の有効/無効設定。enabledのみを保持する。"""

    enabled: bool

    @classmethod
    def from_env(cls) -> "ImageGenerationConfig":
        """
        環境変数から設定を読み込んでインスタンスを生成する。

        読み込む環境変数:
            AI_IMAGE_GENERATION_ENABLED: 画像生成機能の有効/無効
                （未設定時: 無効。前後空白を除去し大文字小文字を無視して
                  "true"と完全一致する場合のみ有効。それ以外はすべて無効）

        Returns:
            ImageGenerationConfig: 検証済みの設定インスタンス
        """
        raw_value = os.getenv(_ENV_ENABLED, "")
        return cls(enabled=raw_value.strip().lower() == "true")
