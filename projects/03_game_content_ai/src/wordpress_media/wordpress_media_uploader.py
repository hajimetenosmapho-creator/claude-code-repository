"""
WordPress Media REST API (POST /wp-json/wp/v2/media) への画像アップロードを担うモジュール。

Consumer-less Foundation: 既存の記事投稿・アイキャッチ関連の既存コードのいずれへも配線しない。
"""
import os
import re

import requests

from .media_upload_result import MediaUploadResult

_FILENAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

_TIMEOUT_SECONDS = 30
_MAX_CODE_LENGTH = 100
_MAX_MESSAGE_LENGTH = 200

_ENV_SITE_URL = "WP_SITE_URL"
_ENV_USERNAME = "WP_USERNAME"
_ENV_APP_PASSWORD = "WP_APP_PASSWORD"


class WordPressMediaUploadError(RuntimeError):
    """WordPress Media APIへの通信・応答に関する失敗を表す唯一の専用例外。"""
    pass


def _is_control_char(ch: str) -> bool:
    return ord(ch) < 0x20 or ord(ch) == 0x7F


def _sanitize_control_chars(text: str) -> str:
    """制御文字（CR/LF/tab/NUL/DEL等）を空白へ正規化する。連続空白の圧縮は行わない。"""
    return "".join(" " if _is_control_char(ch) else ch for ch in text)


def _validate_image_bytes(image_bytes) -> None:
    if not isinstance(image_bytes, bytes):
        raise ValueError("image_bytes must be a bytes object")
    if not image_bytes:
        raise ValueError("image_bytes must not be empty")


def _validate_filename(filename) -> None:
    if not isinstance(filename, str):
        raise ValueError("filename must be a str")
    if not _FILENAME_PATTERN.fullmatch(filename):
        raise ValueError("filename contains characters that are not allowed")


def _validate_mime_type(mime_type) -> None:
    if not isinstance(mime_type, str):
        raise ValueError("mime_type must be a str")
    if not mime_type.strip():
        raise ValueError("mime_type must not be empty")
    if mime_type != mime_type.strip():
        raise ValueError("mime_type must not have leading or trailing whitespace")
    if any(_is_control_char(ch) for ch in mime_type):
        raise ValueError("mime_type must not contain control characters")


def _build_non_2xx_message(response) -> str:
    message = f"WordPress Media API returned HTTP {response.status_code}"

    try:
        data = response.json()
    except ValueError:
        return message

    if not isinstance(data, dict):
        return message

    safe_parts = []

    code = data.get("code")
    if isinstance(code, str):
        safe_parts.append(f"code={_sanitize_control_chars(code)[:_MAX_CODE_LENGTH]}")

    wp_message = data.get("message")
    if isinstance(wp_message, str):
        safe_parts.append(
            f"message={_sanitize_control_chars(wp_message)[:_MAX_MESSAGE_LENGTH]}"
        )

    if safe_parts:
        message += " (" + ", ".join(safe_parts) + ")"

    return message


class WordPressMediaUploader:
    """
    WordPress Media Library（POST /wp-json/wp/v2/media）へ画像バイナリをアップロードする。

    既存WordPressOutput（記事投稿）とは独立しており、いずれの既存productionコードへも依存しない。
    """

    def __init__(self, site_url: str, username: str, app_password: str) -> None:
        for field_name, value in (
            ("site_url", site_url),
            ("username", username),
            ("app_password", app_password),
        ):
            if not isinstance(value, str):
                raise ValueError(f"{field_name} must be a str")
            if not value.strip():
                raise ValueError(f"{field_name} must not be empty")

        normalized_site_url = site_url.strip().rstrip("/")
        if not normalized_site_url:
            raise ValueError("site_url must not be empty after normalization")

        self.site_url = normalized_site_url
        self.username = username
        self.app_password = app_password

    @classmethod
    def from_env(cls) -> "WordPressMediaUploader":
        raw = {
            _ENV_SITE_URL: os.environ.get(_ENV_SITE_URL, ""),
            _ENV_USERNAME: os.environ.get(_ENV_USERNAME, ""),
            _ENV_APP_PASSWORD: os.environ.get(_ENV_APP_PASSWORD, ""),
        }
        missing = [name for name, value in raw.items() if not value.strip()]
        if missing:
            raise ValueError(
                f"missing or blank environment variables: {', '.join(missing)}"
            )

        return cls(
            site_url=raw[_ENV_SITE_URL],
            username=raw[_ENV_USERNAME],
            app_password=raw[_ENV_APP_PASSWORD],
        )

    def upload(
        self,
        image_bytes: bytes,
        filename: str,
        mime_type: str,
    ) -> MediaUploadResult:
        _validate_image_bytes(image_bytes)
        _validate_filename(filename)
        _validate_mime_type(mime_type)

        endpoint = f"{self.site_url}/wp-json/wp/v2/media"

        try:
            response = requests.post(
                endpoint,
                data=image_bytes,
                headers={
                    "Content-Type": mime_type,
                    "Content-Disposition": f'attachment; filename="{filename}"',
                },
                auth=(self.username, self.app_password),
                timeout=_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise WordPressMediaUploadError(
                "WordPress Media APIへの通信に失敗しました"
            ) from exc

        if not (200 <= response.status_code < 300):
            raise WordPressMediaUploadError(_build_non_2xx_message(response))

        try:
            data = response.json()
        except ValueError as exc:
            raise WordPressMediaUploadError(
                "WordPress Media APIの成功レスポンスが不正です"
            ) from exc

        if not isinstance(data, dict):
            raise WordPressMediaUploadError(
                "WordPress Media APIの成功レスポンスが不正です"
            )

        media_id = data.get("id")
        if isinstance(media_id, bool) or not isinstance(media_id, int) or media_id < 1:
            raise WordPressMediaUploadError(
                "WordPress Media APIの成功レスポンスが不正です（id）"
            )

        if "source_url" not in data:
            raise WordPressMediaUploadError(
                "WordPress Media APIの成功レスポンスが不正です（source_url）"
            )
        source_url = data["source_url"]
        if source_url is not None and not isinstance(source_url, str):
            raise WordPressMediaUploadError(
                "WordPress Media APIの成功レスポンスが不正です（source_url）"
            )

        if "mime_type" not in data:
            raise WordPressMediaUploadError(
                "WordPress Media APIの成功レスポンスが不正です（mime_type）"
            )
        response_mime_type = data["mime_type"]
        if response_mime_type is not None and not isinstance(response_mime_type, str):
            raise WordPressMediaUploadError(
                "WordPress Media APIの成功レスポンスが不正です（mime_type）"
            )

        return MediaUploadResult(
            media_id=media_id,
            source_url=source_url,
            mime_type=response_mime_type,
        )
