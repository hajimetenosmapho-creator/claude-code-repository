"""
Claude API との通信を担うモジュール（v1.14.0）

Single Responsibility:
    - Anthropic Claude API への HTTP 通信のみを担う
    - APIキー・モデル設定を環境変数から読み込む
    - プロンプト文字列を受け取り、raw_response（str）を返す

禁止事項:
    - レスポンスの解析（ImprovementSuggestionParser の責務）
    - ImprovementSuggestion への変換
    - ファイル I/O

設計方針（Configuration First）:
    AI_IMPROVEMENT_ENABLED=false または APIキー未設定 → from_env() が NullClaudeClient を返す
    テスト時は NullClaudeClient を使用（実 API を叩かない）
"""
from __future__ import annotations

from .ai_improvement_config import AiImprovementConfig


class ClaudeClient:
    """
    Anthropic Claude API と通信するクライアント。

    テスト容易性のため、client オブジェクトを注入できる設計にする。
    """

    def __init__(self, config: AiImprovementConfig, client=None):
        self._config = config
        self._client = client  # テスト時に mock を注入できる

    @classmethod
    def from_env(cls) -> "ClaudeClient | NullClaudeClient":
        """
        環境変数から設定を読み込み、適切なクライアントを返す。

        ANTHROPIC_API_KEY 未設定または AI_IMPROVEMENT_ENABLED=false の場合は NullClaudeClient。
        """
        config = AiImprovementConfig.from_env()
        if not config.is_ready():
            return NullClaudeClient()
        return cls(config)

    def _get_client(self):
        """anthropic.Anthropic クライアントを返す（遅延初期化）。"""
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self._config.api_key)
        return self._client

    def is_available(self) -> bool:
        """API 通信が可能な状態かを返す。"""
        return self._config.is_ready()

    def send(self, prompt: str) -> str:
        """
        Claude API にプロンプトを送信し、raw_response を返す。

        Args:
            prompt: Claude API に渡すプロンプト文字列

        Returns:
            str: Claude の応答テキスト。失敗時は空文字列。

        Raises:
            なし（例外はキャッチし、[AI WARNING] を出力して空文字列を返す）
        """
        if not self.is_available():
            return ""

        try:
            client = self._get_client()
            message = client.messages.create(
                model=self._config.model,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text if message.content else ""
        except Exception as e:
            print(f"  [AI WARNING] Claude API エラー（処理継続）: {e}")
            return ""


class NullClaudeClient:
    """
    AI_IMPROVEMENT_ENABLED=false または APIキー未設定のときに返されるダミー実装。
    is_available() が False を返し、send() は空文字列を返す。
    """

    def is_available(self) -> bool:
        return False

    def send(self, prompt: str) -> str:
        return ""
