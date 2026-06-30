"""
出力処理の抽象基底クラスと共通データクラスを定義するモジュール。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from collector import NewsItem
from publishing_config import PublishStatus
from .save_result import SaveResult


@dataclass
class ArticleData:
    """記事生成結果をまとめて出力処理に渡すデータクラス。"""
    item: NewsItem
    importance: str
    seo_title: str
    article_body: str
    x_post: str
    featured_image_url: str = ""              # アイキャッチ画像候補URL（空文字 = なし）
    excerpt: str = ""                         # WordPress抜粋・Markdown記録用（v1.4.0 追加）
    meta_description: str = ""                # 将来のSEOプラグイン連携用（v1.4.0ではexcerptと同値）
    slug: str = ""                            # WordPress slug（v1.5.0 追加）
    featured_media_id: int = 0                # WordPress media_id（v1.6.0 追加、0 = アイキャッチなし）
    publish_status: PublishStatus = PublishStatus.DRAFT  # 投稿ステータス（v1.7.0 追加）


class BaseOutput(ABC):
    """全出力クラスの抽象基底クラス。"""

    @abstractmethod
    def save(self, article: ArticleData) -> SaveResult:
        """
        記事を保存・投稿する。

        Args:
            article: 保存対象の記事データ

        Returns:
            SaveResult: 保存結果（post_id / edit_url / success 等を格納）
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """この出力先が利用可能な状態かどうかを返す。"""
        ...
