"""
OpenAI Images API（gpt-image-2）を用いたAIImageGenerator Protocol実装。

Source of Truth:
    docs/design/openai_image_generation_adapter_foundation.md
    （Architecture Review 5：Approved、Test Review 6：Approved）

Consumer-less Foundation: WordPress・記事投稿Pipelineへの配線は行わない。
`openai`パッケージへの依存はこのモジュール内に閉じ込め、`ai_image_generation`からは
`GeneratedImage`のみをimportする（`AIImageGenerator`はimportしない）。
"""
import base64
import binascii
import os
from enum import Enum

from ai_image_generation import GeneratedImage

_DEFAULT_MODEL = "gpt-image-2-2026-04-21"
_DEFAULT_SIZE = "1024x1024"
_DEFAULT_QUALITY = "medium"
_DEFAULT_OUTPUT_FORMAT = "png"
_DEFAULT_TIMEOUT_SECONDS = 180

_ALLOWED_SIZES = frozenset({
    "1024x1024", "1536x1024", "1024x1536",
    "2048x2048", "2048x1152",
    "3840x2160", "2160x3840",
})
_ALLOWED_QUALITIES = frozenset({"low", "medium", "high"})
_ALLOWED_OUTPUT_FORMATS = frozenset({"png", "jpeg", "webp"})

_MIME_TYPE_BY_OUTPUT_FORMAT = {
    "png": "image/png",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}

_FIXED_N = 1
_FIXED_BACKGROUND = "opaque"

_ENV_API_KEY = "OPENAI_API_KEY"
_ENV_TIMEOUT_SECONDS = "OPENAI_IMAGE_TIMEOUT_SECONDS"

_ALLOWED_CONTROL_CHARS = frozenset({"\t", "\n", "\r"})
_MAX_PROMPT_LENGTH = 32000

_MISSING = object()

_MSG_UNEXPECTED_ERROR = "OpenAI Images APIの呼び出し中に予期しないエラーが発生しました"
_MSG_INVALID_RESPONSE_STRUCTURE = "OpenAI Images APIのレスポンス構造が不正です"
_MSG_INVALID_BASE64 = "OpenAI Images APIのレスポンスのBase64データが不正です"
_MSG_EMPTY_DECODE_RESULT = "OpenAI Images APIのレスポンスのデコード結果が空でした"


class OpenAIImageGenerationErrorReason(Enum):
    """OpenAIImageGenerationErrorの安全な失敗分類。秘密情報・Provider固有の生データは
    一切含まない、固定された分類ラベルのみで構成する。

    v6.23.0（DI-11前半）で、要求拒否系の4つのSDK例外型を個別のreasonへ細分化した。
    REQUEST_REJECTEDは後方互換のため削除せず保持する（productionからは
    到達しなくなるが、値・意味・下流の写像はいずれも従来どおり）。

    v6.24.0（DI-11後半）で、UNKNOWNのうちgeneric except Exception経路のみを
    UNEXPECTED_EXCEPTIONへ、INVALID_RESPONSEのうちdata／b64_json構造不正2経路のみを
    INVALID_RESPONSE_STRUCTUREへ分離した。UNKNOWN／INVALID_RESPONSEは後方互換のため
    削除せず保持する（productionから生成される経路は縮小するが、値・意味・下流の
    写像はいずれも従来どおり）。
    """
    AUTHENTICATION = "authentication"
    PERMISSION_DENIED = "permission_denied"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    CONNECTION = "connection"
    REQUEST_REJECTED = "request_rejected"
    SERVER_ERROR = "server_error"
    INVALID_RESPONSE = "invalid_response"
    UNKNOWN = "unknown"
    # ─── v6.23.0 追加（既存9値の後ろへ追加する。既存の定義順は変更しない）───
    BAD_REQUEST = "bad_request"
    RESOURCE_NOT_FOUND = "resource_not_found"
    CONFLICT = "conflict"
    UNPROCESSABLE_ENTITY = "unprocessable_entity"
    # ─── v6.24.0 追加（既存13値の後ろへ追加する。既存の定義順は変更しない）───
    UNEXPECTED_EXCEPTION = "unexpected_exception"
    INVALID_RESPONSE_STRUCTURE = "invalid_response_structure"


class OpenAIImageGenerationError(RuntimeError):
    """OpenAI Images APIとの通信・応答に関する失敗を表す唯一の専用例外。

    reason属性は安全な分類ラベルのみを保持し、Provider例外オブジェクト・
    レスポンス生データ・prompt・API keyのいずれも保持しない。
    """

    def __init__(self, message: str, reason: OpenAIImageGenerationErrorReason) -> None:
        super().__init__(message)
        self.reason = reason


def _validate_prompt(prompt) -> None:
    if type(prompt) is not str:
        raise ValueError("prompt must be a str")
    if not prompt.strip():
        raise ValueError("prompt must not be empty or whitespace-only")
    if len(prompt) > _MAX_PROMPT_LENGTH:
        raise ValueError(f"prompt must not exceed {_MAX_PROMPT_LENGTH} characters")
    for ch in prompt:
        if ch in _ALLOWED_CONTROL_CHARS:
            continue
        codepoint = ord(ch)
        if codepoint < 0x20 or codepoint == 0x7F:
            raise ValueError("prompt must not contain disallowed control characters")


def _classify_api_error(exc: "openai.APIError"):
    """openai.APIError系の例外を、固定メッセージとreasonのペアへ分類する純粋関数。

    Providerメッセージ・response body・status codeの生値・prompt断片は
    一切読み取らない。分類は例外の型（isinstance）のみに基づく。
    raiseは行わない。具体的なsubclassから一般的なAPIError（catch-all）の
    順に判定する。

    ── 例外引数の使用形に関する契約（I-EXC-1、設計書7.8節）──
    本関数の中で引数 exc を使ってよいのは isinstance(exc, ...) の第1引数
    としてのみである。exc.<属性>・exc[...]・str(exc)・repr(exc)・vars(exc)・
    getattr(exc, ...)・hasattr(exc, ...)・isinstance以外の関数への引き渡し・
    比較・演算・return・代入・collection格納は、いずれも禁止する。
    属性名を列挙して禁止するのではなく「許可される使用形はこの1つだけ」と
    定めているため、SDKが将来追加する未知の属性も自動的に禁止側へ落ちる。
    この契約はE2EのNOPARSE- guardがAST検査で機械的に強制する。

    ── 判定順序の契約（設計書7.3節）──
    APITimeoutErrorはAPIConnectionErrorのsubclassであるため、必ず先に判定する
    （v6.11から継承する既存contract）。v6.23.0で追加した4型（BadRequestError／
    NotFoundError／ConflictError／UnprocessableEntityError）は、いずれも
    APIStatusErrorの直接subclassであり相互にsubclass関係を持たないため、
    4型どうしの順序は結果に影響しない（openai 2.46.0で実測確認済み）。
    それでも将来のSDK変更を検出できるよう、判定位置は現行のまま固定する。
    """
    import openai

    if isinstance(exc, openai.AuthenticationError):
        return (
            "OpenAI APIへの認証に失敗しました",
            OpenAIImageGenerationErrorReason.AUTHENTICATION,
        )
    if isinstance(exc, openai.PermissionDeniedError):
        return (
            "OpenAI APIへのアクセス権限がありません（Organization Verification等の可能性）",
            OpenAIImageGenerationErrorReason.PERMISSION_DENIED,
        )
    if isinstance(exc, openai.RateLimitError):
        return (
            "OpenAI APIのレート制限に達しました",
            OpenAIImageGenerationErrorReason.RATE_LIMIT,
        )
    if isinstance(exc, openai.APITimeoutError):
        # APIConnectionErrorのsubclassのため、APIConnectionErrorより先に判定する。
        return (
            "OpenAI APIへのリクエストがタイムアウトしました",
            OpenAIImageGenerationErrorReason.TIMEOUT,
        )
    if isinstance(exc, openai.APIConnectionError):
        return (
            "OpenAI APIへの接続に失敗しました",
            OpenAIImageGenerationErrorReason.CONNECTION,
        )
    # v6.23.0（DI-11前半）: 従来はこの4型を単一のタプルで判定し
    # REQUEST_REJECTEDへ集約していた。messageは4型とも従来と完全に同一の
    # 文字列を維持し、reasonのみを細分化する（設計書7.6節のmessage凍結）。
    if isinstance(exc, openai.BadRequestError):
        return (
            "OpenAI APIへのリクエストが不正です（Content Policy等による生成拒否を含む）",
            OpenAIImageGenerationErrorReason.BAD_REQUEST,
        )
    if isinstance(exc, openai.NotFoundError):
        return (
            "OpenAI APIへのリクエストが不正です（Content Policy等による生成拒否を含む）",
            OpenAIImageGenerationErrorReason.RESOURCE_NOT_FOUND,
        )
    if isinstance(exc, openai.ConflictError):
        return (
            "OpenAI APIへのリクエストが不正です（Content Policy等による生成拒否を含む）",
            OpenAIImageGenerationErrorReason.CONFLICT,
        )
    if isinstance(exc, openai.UnprocessableEntityError):
        return (
            "OpenAI APIへのリクエストが不正です（Content Policy等による生成拒否を含む）",
            OpenAIImageGenerationErrorReason.UNPROCESSABLE_ENTITY,
        )
    if isinstance(exc, openai.InternalServerError):
        return (
            "OpenAI API側でエラーが発生しました",
            OpenAIImageGenerationErrorReason.SERVER_ERROR,
        )

    return (
        "OpenAI Images APIの呼び出しに失敗しました",
        OpenAIImageGenerationErrorReason.UNKNOWN,
    )


def _validate_response_structure(response):
    """response構造を防御的（getattrベース）に検証する。

    戻り値: (error_message, error_reason, b64_json_or_None)
    いずれのフィールドも欠落・不正な場合はerror_message/error_reasonを設定し、
    正常な場合はerror_message=None・error_reason=None・b64_jsonの値を返す。
    """
    data = getattr(response, "data", _MISSING)
    if not isinstance(data, list) or len(data) != 1:
        return (_MSG_INVALID_RESPONSE_STRUCTURE, OpenAIImageGenerationErrorReason.INVALID_RESPONSE_STRUCTURE, None)

    b64_json = getattr(data[0], "b64_json", _MISSING)
    if not isinstance(b64_json, str) or not b64_json:
        return (_MSG_INVALID_RESPONSE_STRUCTURE, OpenAIImageGenerationErrorReason.INVALID_RESPONSE_STRUCTURE, None)

    return (None, None, b64_json)


def _build_generated_image(response, output_format: str) -> GeneratedImage:
    error_message, error_reason, b64_value = _validate_response_structure(response)

    decoded = None
    if error_message is None:
        try:
            decoded = base64.b64decode(b64_value, validate=True)
        except (binascii.Error, ValueError):
            error_message = _MSG_INVALID_BASE64
            error_reason = OpenAIImageGenerationErrorReason.INVALID_RESPONSE
        else:
            if len(decoded) == 0:
                error_message = _MSG_EMPTY_DECODE_RESULT
                error_reason = OpenAIImageGenerationErrorReason.INVALID_RESPONSE

    if error_message is not None:
        raise OpenAIImageGenerationError(error_message, error_reason) from None

    mime_type = _MIME_TYPE_BY_OUTPUT_FORMAT[output_format]
    return GeneratedImage(image_bytes=decoded, mime_type=mime_type)


class OpenAIImageGenerator:
    """OpenAI Images API（gpt-image-2）を用いたAIImageGenerator Protocolの具象実装。

    `AIImageGenerator`を明示継承しない（構造的部分型のみ）。
    """

    def __init__(
        self,
        api_key: str,
        *,
        model: str = _DEFAULT_MODEL,
        size: str = _DEFAULT_SIZE,
        quality: str = _DEFAULT_QUALITY,
        output_format: str = _DEFAULT_OUTPUT_FORMAT,
        timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
        client: "openai.OpenAI | None" = None,
    ) -> None:
        if type(api_key) is not str:
            raise ValueError("api_key must be a str")
        if not api_key.strip():
            raise ValueError("api_key must not be empty or whitespace-only")

        if type(model) is not str:
            raise ValueError("model must be a str")
        if not model.strip():
            raise ValueError("model must not be empty or whitespace-only")

        if type(size) is not str or size not in _ALLOWED_SIZES:
            raise ValueError("size must be one of the allowed values")

        if type(quality) is not str or quality not in _ALLOWED_QUALITIES:
            raise ValueError("quality must be one of the allowed values")

        if type(output_format) is not str or output_format not in _ALLOWED_OUTPUT_FORMATS:
            raise ValueError("output_format must be one of the allowed values")

        if type(timeout_seconds) is not int or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be a positive int")

        self._api_key = api_key
        self._model = model
        self._size = size
        self._quality = quality
        self._output_format = output_format
        self._timeout_seconds = timeout_seconds
        self._client = client

    @classmethod
    def from_env(cls) -> "OpenAIImageGenerator":
        api_key = os.environ.get(_ENV_API_KEY, "")
        if not api_key.strip():
            raise ValueError(f"missing or blank environment variable: {_ENV_API_KEY}")

        kwargs = {}
        raw_timeout = os.environ.get(_ENV_TIMEOUT_SECONDS)
        if raw_timeout is not None:
            try:
                timeout_seconds = int(raw_timeout)
            except ValueError:
                raise ValueError(f"{_ENV_TIMEOUT_SECONDS} must be an integer")
            if timeout_seconds <= 0:
                raise ValueError(f"{_ENV_TIMEOUT_SECONDS} must be a positive integer")
            kwargs["timeout_seconds"] = timeout_seconds

        return cls(api_key=api_key, **kwargs)

    @property
    def output_mime_type(self) -> str:
        """このgeneratorが生成する予定の画像のcanonical MIME type。

        generate() の戻り値 GeneratedImage.mime_type と同一の写像
        （_MIME_TYPE_BY_OUTPUT_FORMAT）から導出されるため、両者は常に一致する。
        """
        return _MIME_TYPE_BY_OUTPUT_FORMAT[self._output_format]

    def _get_client(self) -> "openai.OpenAI":
        if self._client is None:
            import openai
            self._client = openai.OpenAI(api_key=self._api_key)

        if not hasattr(self._client, "with_options"):
            raise TypeError(
                "OpenAIImageGenerator: injected client does not implement with_options()"
            )

        return self._client.with_options(
            timeout=self._timeout_seconds,
            max_retries=0,
        )

    def _build_kwargs(self, prompt: str) -> dict:
        return {
            "model": self._model,
            "prompt": prompt,
            "n": _FIXED_N,
            "size": self._size,
            "quality": self._quality,
            "output_format": self._output_format,
            "background": _FIXED_BACKGROUND,
        }

    def generate(self, prompt: str) -> GeneratedImage:
        import openai

        _validate_prompt(prompt)
        client = self._get_client()

        error_message = None
        error_reason = None
        response = None
        try:
            response = client.images.generate(**self._build_kwargs(prompt))
        except openai.APIError as exc:
            error_message, error_reason = _classify_api_error(exc)
        except Exception:
            error_message = _MSG_UNEXPECTED_ERROR
            error_reason = OpenAIImageGenerationErrorReason.UNEXPECTED_EXCEPTION

        if error_message is not None:
            raise OpenAIImageGenerationError(error_message, error_reason) from None

        return _build_generated_image(response, self._output_format)
