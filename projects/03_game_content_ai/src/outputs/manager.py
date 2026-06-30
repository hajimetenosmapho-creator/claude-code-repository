"""
複数の出力先をまとめて管理するモジュール。
"""

from .base import BaseOutput, ArticleData
from .save_result import SaveResult


class OutputManager:
    """
    登録された出力先（BaseOutput）に記事を一括保存する。
    1つの出力先が失敗しても他の出力先への保存は続行する。
    """

    def __init__(self, outputs: list[BaseOutput]):
        self.outputs = outputs

    def save_all(self, article: ArticleData) -> list[SaveResult]:
        """
        登録された全出力先に記事を保存する。

        v1.11.0: 戻り値を list[str] から list[SaveResult] に変更。
                 失敗した場合も SaveResult(success=False) として結果に含める。

        Args:
            article: 保存対象の記事データ

        Returns:
            list[SaveResult]: 全出力先の保存結果（成功・失敗を問わず記録）
        """
        results = []
        for output in self.outputs:
            if not output.is_available():
                continue
            output_type = "wordpress" if "WordPress" in output.__class__.__name__ else "file"
            try:
                result = output.save(article)
                results.append(result)
            except Exception as e:
                print(f"  [警告] {output.__class__.__name__} 保存失敗: {e}")
                results.append(SaveResult(
                    success=False,
                    output_type=output_type,
                    error_message=str(e),
                ))
        return results
