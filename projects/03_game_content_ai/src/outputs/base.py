"""
出力処理の抽象基底クラスと共通データクラスを定義するモジュール。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from collector import NewsItem


@dataclass
class ArticleData:
    """記事生成結果をまとめて出力処理に渡すデータクラス。"""
    item: NewsItem
    importance: str
    seo_title: str
    article_body: str
    x_post: str
    featured_image_url: str = ""  # アイキャッチ画像候補URL（空文字 = なし）
    excerpt: str = ""             # WordPress抜粋・Markdown記録用（v1.4.0 追加）
    meta_description: str = ""    # 将来のSEOプラグイン連携用（v1.4.0ではexcerptと同値）
    slug: str = ""                # WordPress slug（v1.5.0 追加）


class BaseOutput(ABC):
    """全出力クラスの抽象基底クラス。"""

    @abstractmethod
    def save(self, article: ArticleData) -> str:
        """
        記事を保存・投稿する。

        Args:
            article: 保存対象の記事データ

        Returns:
            str: 保存先を示す文字列（ファイルパス、投稿URL など）
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """この出力先が利用可能な状態かどうかを返す。"""
        ...
