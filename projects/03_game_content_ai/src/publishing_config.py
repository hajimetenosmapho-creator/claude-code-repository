"""
投稿ステータスを重要度に応じて解決するモジュール。

v1.7.0: PublishStatus Enum + PublishingConfig dataclass を実装。
        draft / pending の 2 ステータスをサポート。
将来: future（予約投稿）/ publish（承認ゲート付き自動公開）を追加予定。
"""
import os
from dataclasses import dataclass
from enum import Enum


class PublishStatus(str, Enum):
    """
    WordPress 投稿ステータスの列挙型。

    str を継承することで PublishStatus.DRAFT == "draft" が True になり、
    JSON シリアライズ・ログ出力でそのまま文字列として使える。

    v1.7.0 対応: DRAFT / PENDING
    将来対応  : FUTURE / PUBLISH
    """
    DRAFT   = "draft"    # 下書き（デフォルト）
    PENDING = "pending"  # レビュー待ち（人間が公開ボタンを押すまで非公開）
    FUTURE  = "future"   # 予約投稿（将来実装：date パラメータが必要）
    PUBLISH = "publish"  # 即時公開（将来実装：承認ゲートが必要）


# v1.7.0 で設定可能なステータス。誤公開防止のため FUTURE / PUBLISH は対象外。
_ALLOWED_STATUSES = {PublishStatus.DRAFT, PublishStatus.PENDING}


def _parse_status(raw: str, env_key: str) -> PublishStatus:
    """
    環境変数の文字列を PublishStatus に変換する。

    変換ルール:
        1. 文字列が PublishStatus の値に存在しない → WARNING + DRAFT にフォールバック
        2. 存在するが v1.7.0 の許可リスト外（FUTURE / PUBLISH）→ WARNING + DRAFT にフォールバック
        3. 許可リスト内（DRAFT / PENDING）→ そのまま返す

    Args:
        raw:     .env から読み込んだ生の文字列
        env_key: 環境変数名（警告メッセージ用）

    Returns:
        PublishStatus: 検証済みのステータス値
    """
    normalized = raw.lower().strip()

    try:
        status = PublishStatus(normalized)
    except ValueError:
        print(f'  [WARNING] {env_key}="{raw}" は無効な値です。"draft" にフォールバックします。')
        print(f'           有効な値: draft | pending')
        return PublishStatus.DRAFT

    if status not in _ALLOWED_STATUSES:
        print(f'  [WARNING] {env_key}="{raw}" は v1.7.0 では未対応です。"draft" にフォールバックします。')
        print(f'           v1.7.0 で使用可能な値: draft | pending')
        return PublishStatus.DRAFT

    return status


@dataclass
class PublishingConfig:
    """
    投稿ステータス設定。.env から読み込む。

    設計方針（Configuration First）:
        - 未設定の場合はすべて DRAFT（Release 1.0 と完全互換）
        - .env を変更しない限り、従来と全く同じ動作をする
        - 不正値は DRAFT にフォールバックし、コードが落ちない

    将来の拡張フィールド（現在は未実装・コメントとして予約）:
        publish_time: str      - 予約投稿の時刻（例: "09:00"）→ FUTURE ステータスで使用
        timezone: str          - タイムゾーン（例: "Asia/Tokyo"）→ 予約投稿の日時計算用
        review_required: bool  - 公開前に人間の承認を必須にするか → 承認ゲートで使用
        priority: int          - 記事の優先度（将来の表示順・通知制御用）

    Attributes:
        status_s: S評価記事の WordPress 投稿ステータス
        status_a: A評価記事の WordPress 投稿ステータス
    """
    status_s: PublishStatus = PublishStatus.DRAFT
    status_a: PublishStatus = PublishStatus.DRAFT

    @classmethod
    def from_env(cls) -> "PublishingConfig":
        """
        環境変数から設定を読み込んでインスタンスを生成する。

        読み込む環境変数:
            PUBLISH_STATUS_S: S評価記事のステータス（未設定時: "draft"）
            PUBLISH_STATUS_A: A評価記事のステータス（未設定時: "draft"）

        Returns:
            PublishingConfig: 検証済みの設定インスタンス
        """
        raw_s = os.getenv("PUBLISH_STATUS_S", "draft")
        raw_a = os.getenv("PUBLISH_STATUS_A", "draft")

        return cls(
            status_s=_parse_status(raw_s, "PUBLISH_STATUS_S"),
            status_a=_parse_status(raw_a, "PUBLISH_STATUS_A"),
        )

    def resolve_status(self, importance: str) -> PublishStatus:
        """
        重要度から投稿ステータスを解決する。

        Args:
            importance: "S" / "A" / "B"

        Returns:
            PublishStatus: 対応する投稿ステータス。B評価は DRAFT 固定。
        """
        if importance == "S":
            return self.status_s
        if importance == "A":
            return self.status_a
        return PublishStatus.DRAFT
