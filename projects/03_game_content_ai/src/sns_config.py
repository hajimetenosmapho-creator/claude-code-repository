"""
SNS連携の設定と投稿ステータスを管理するモジュール。

v1.9.0: WordPress公開予定URLの生成・SNS機能の有効/無効・SnsPostStatus Enum を実装。
将来: X API認証情報・他SNSプラットフォーム設定の追加。
"""
import os
from dataclasses import dataclass
from enum import Enum


class SnsPostStatus(str, Enum):
    """
    X（旧Twitter）投稿ステータスの列挙型。

    str を継承することで SnsPostStatus.PENDING == "pending" が True になり、
    JSON シリアライズ・ログ出力でそのまま文字列として使える。

    v1.9.0 対応: PENDING / SKIPPED
    将来対応  : POSTED / FAILED
    """
    PENDING = "pending"   # X未投稿（デフォルト）
    POSTED  = "posted"    # X投稿済み（将来: X API 対応時）
    FAILED  = "failed"    # X投稿失敗（将来: X API 対応時）
    SKIPPED = "skipped"   # SNS_ENABLED=false によりスキップ


@dataclass
class SnsConfig:
    """
    SNS連携の設定。.env から読み込む。

    設計方針（Configuration First）:
        - BLOG_BASE_URL を優先して公開URLを生成する（本番運用推奨）
        - BLOG_BASE_URL 未設定時は WP_SITE_URL にフォールバック
        - どちらも未設定なら "[ブログURL]" プレースホルダーを維持（v1.8.0 互換）
        - SNS_ENABLED=false でSNS機能全体を無効化できる

    将来の拡張フィールド（現在は未実装・コメントとして予約）:
        x_api_key: str          - X API キー（将来の自動投稿用）
        x_api_secret: str       - X API シークレット（将来の自動投稿用）
        x_access_token: str     - X アクセストークン（将来の自動投稿用）
        x_access_secret: str    - X アクセスシークレット（将来の自動投稿用）
        instagram_enabled: bool - Instagram 連携（将来対応）
        threads_enabled: bool   - Threads 連携（将来対応）

    Attributes:
        blog_base_url: 公開記事URLのベース（BLOG_BASE_URL 優先・WP_SITE_URL フォールバック）
        sns_enabled:   SNS機能全体の有効/無効
    """
    blog_base_url: str = ""
    sns_enabled: bool = True

    @classmethod
    def from_env(cls) -> "SnsConfig":
        """
        環境変数から設定を読み込む。

        読み込む環境変数:
            BLOG_BASE_URL: ブログ公開URLのベース（優先）
            WP_SITE_URL:   WordPress接続URL（BLOG_BASE_URL 未設定時のフォールバック）
            SNS_ENABLED:   SNS機能の有効/無効（未設定時: "true"）

        優先順位:
            BLOG_BASE_URL → WP_SITE_URL → "" （→ resolve_public_url が "[ブログURL]" を返す）

        Returns:
            SnsConfig: 検証済みの設定インスタンス
        """
        blog_base_url = (
            os.getenv("BLOG_BASE_URL") or os.getenv("WP_SITE_URL", "")
        ).rstrip("/")

        sns_enabled = os.getenv("SNS_ENABLED", "true").lower().strip() != "false"

        return cls(
            blog_base_url=blog_base_url,
            sns_enabled=sns_enabled,
        )

    def resolve_public_url(self, slug: str) -> str:
        """
        WordPress slug から公開予定URLを生成する。

        URL構造: {blog_base_url}/{slug}/
        例: "https://nozo3-kao6.tokyo/ps6-announced-20260630/"

        前提: WordPress のパーマリンク設定が「投稿名」形式（/%postname%/）であること。

        Args:
            slug: WordPress slug（例: "ps6-announced-20260630"）

        Returns:
            str: 公開予定URL。blog_base_url または slug が空の場合は "[ブログURL]"。
        """
        if not self.blog_base_url or not slug:
            return "[ブログURL]"
        return f"{self.blog_base_url}/{slug}/"
