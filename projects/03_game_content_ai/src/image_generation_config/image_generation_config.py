"""
画像生成機能の有効/無効を制御するConfiguration-First Gate。

Source of Truth:
    docs/design/image_generation_configuration_gate_foundation.md
    （Architecture Review：Approved）

Consumer-less Foundation: Production Runtimeへの配線は行わない。
enabledのみを保持し、Provider APIキーやタイムアウト設定は読み取らない
（それらはOpenAIImageGeneratorの`from_env()`の責務のまま維持する）。

Gate値検証（v6.27.0、DI-9 Image Generation Gate Value Strict Validation）:
    未設定・空文字・空白のみは無効（警告なし）として扱う。"true"/"false"
    （前後空白除去・大文字小文字無視）はそのまま解釈する。それ以外の
    明示的な値（typo等）は無効へフォールバックしつつ、WARNINGを1回出力する
    （raw値はWARNINGへ含めない）。いずれの入力でも例外は送出しない
    （v6.15.0からのFail Closed Contractを維持。Fail Fastは不採用。
    理由はdocs/design/image_generation_gate_value_validation_foundation.md参照）。
"""
import os
from dataclasses import dataclass

_ENV_ENABLED = "AI_IMAGE_GENERATION_ENABLED"
_TRUE_VALUE = "true"
_FALSE_VALUE = "false"


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
                （前後空白を除去し大文字小文字を無視して判定する）
                - 未設定・空文字・空白のみ: 無効（警告なし）
                - "true": 有効
                - "false": 無効
                - 上記いずれにも該当しない値: 無効（WARNINGを1回出力してから
                  フォールバックする。raw値はWARNINGへ含めない）

        Returns:
            ImageGenerationConfig: 検証済みの設定インスタンス（例外は送出しない）
        """
        raw_value = os.getenv(_ENV_ENABLED, "")
        normalized = raw_value.strip().lower()

        if normalized == "":
            return cls(enabled=False)
        if normalized == _TRUE_VALUE:
            return cls(enabled=True)
        if normalized == _FALSE_VALUE:
            return cls(enabled=False)

        print(
            f'  [WARNING] {_ENV_ENABLED} は無効な値です。"false" にフォールバックします。'
            f" 有効な値: true | false"
        )
        return cls(enabled=False)
