"""
複数の出力先をまとめて管理するモジュール。
"""

from .base import BaseOutput, ArticleData


class OutputManager:
    """
    登録された出力先（BaseOutput）に記事を一括保存する。
    1つの出力先が失敗しても他の出力先への保存は続行する。
    """

    def __init__(self, outputs: list[BaseOutput]):
        self.outputs = outputs

    def save_all(self, article: ArticleData) -> list[str]:
        """
        登録された全出力先に記事を保存する。

        Args:
            article: 保存対象の記事データ

        Returns:
            list[str]: 保存に成功した保存先文字列のリスト
        """
        results = []
        for output in self.outputs:
            if not output.is_available():
                continue
            try:
                destination = output.save(article)
                results.append(destination)
            except Exception as e:
                print(f"  [警告] {output.__class__.__name__} 保存失敗: {e}")
        return results
