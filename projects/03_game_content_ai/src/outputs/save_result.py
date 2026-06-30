"""
保存処理の結果を表す構造化データクラス。

v1.11.0: WordPressOutput.save() の戻り値を文字列から SaveResult に変更し、
         WordPress REST API レスポンスから post_id を直接取得する。
         edit_url からの正規表現抽出（v1.8.0 の暫定実装）を廃止する。

設計方針（Single Source of Truth）:
    post_id は WordPress API レスポンスの "id" フィールドから直接取得する。
    edit_url や他の文字列から post_id を推測しない。
"""
from dataclasses import dataclass, field


@dataclass
class SaveResult:
    """
    BaseOutput.save() の保存結果。
    WordPress と Markdown ファイルで共通の構造を持つ。

    Attributes:
        success:       保存が成功したかどうか
        output_type:   保存先の種別（"wordpress" / "file"）
        post_id:       WordPress 投稿ID（WordPress API レスポンスの "id" より取得）
        title:         WordPress 投稿タイトル（rendered）
        slug:          WordPress slug（API レスポンスから取得した確定値）
        status:        WordPress 投稿ステータス（"draft" / "pending" 等）
        edit_url:      WordPress 管理画面の編集URL / Markdown ファイルのパス
        permalink:     WordPress 公開URL（API レスポンスの "link"）
        error_message: 失敗時のエラーメッセージ（成功時は None）
        raw_response:  WordPress REST API の生レスポンス（repr 対象外）
    """
    success: bool
    output_type: str = "file"          # "wordpress" / "file"
    post_id: int | None = None
    title: str | None = None
    slug: str | None = None
    status: str | None = None
    edit_url: str | None = None
    permalink: str | None = None
    error_message: str | None = None
    raw_response: dict | None = field(default=None, repr=False)

    @property
    def is_wordpress(self) -> bool:
        """WordPress への投稿結果かどうかを返す。"""
        return self.output_type == "wordpress"

    @property
    def destination(self) -> str:
        """後方互換用: edit_url があればそれを、なければ空文字を返す。"""
        return self.edit_url or ""
