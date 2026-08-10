"""
Image Generation Fallback Policy Foundation.

Source of Truth:
    docs/design/image_generation_fallback_policy_foundation.md
    （Architecture Review 4：Approved with Suggestions、Blocking 0・Major 0）

Consumer-less Foundation: `ArticleFeaturedMediaOrchestrator.apply()`（v6.14.0）の
実行中に発生した失敗に対し、「featured mediaなしで記事投稿を継続してよいか」
「呼び出し側が元の例外を無変換で再送出すべきか」を決定する、stateless・
副作用なしの判断規則。`openai_image_generation`（v6.11.0）・`wordpress_media`
（v6.9.0）の2つの専用例外型のみをimportし、それ以外の画像系・Runtime系
package（`ai_image_generation` / `article_featured_media_orchestration` /
`article_featured_media_composition` / `image_generation_config` /
`generated_image_filename_policy` / `article_image_prompt_construction` /
`outputs` / `main` / `image_resolver` / `pipeline` / `ai` / `scheduler` /
`retry_*` / `logger` / `analytics` / `scripts`）のいずれへも依存しない。

本packageは try／except を1つも持たず、受け取った例外を再送出・wrap・変換
しない。分類は例外の型（isinstance）と `OpenAIImageGenerationError.reason`
（v6.11が secret-free と定めた分類Enum）の同一性比較（`is`）および
module-level allow-list（`frozenset`）への所属判定のみに基づき、
例外message・provider応答本文・HTTPステータスコードのいずれも読み取らない
（設計書13.2節・13.5節）。

v6.23.0（DI-11前半）で `_REJECTED_REASONS` を追加し、v6.11が細分化した
要求拒否系4 reason と既存の REQUEST_REJECTED をまとめて
`IMAGE_GENERATION_REQUEST_REJECTED` へ写像する。継続対象
（`_CONTINUABLE_REASONS` の4値）は変更していない。

v6.25.0（DI-5）で `extract_safe_reason()` を追加し、fallback判断とは独立に
secret-freeなreason文字列を取り出す観測用の補助関数を公開する。分類
テーブル・CONTINUE対象・`decide_image_generation_fallback()`のロジックは
いずれも無変更。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from openai_image_generation import (
    OpenAIImageGenerationError,
    OpenAIImageGenerationErrorReason,
)
from wordpress_media import WordPressMediaUploadError, WordPressMediaUploadErrorReason


class ImageGenerationFallbackAction(Enum):
    """失敗に対して呼び出し側が取るべき行動。

    CONTINUE_WITHOUT_FEATURED_MEDIA:
        featured mediaを設定せずに、その記事の処理を継続してよい。
        呼び出し側は捕捉した例外を破棄してよく、ArticleData.featured_media_id は
        既存値（既定 0 = アイキャッチなし）のまま WordPress へ投稿される。

    PROPAGATE_ORIGINAL_ERROR:
        本policyが例外をraiseするという意味ではない。
        呼び出し側が、捕捉した「元の例外オブジェクト」を無変換で再送出する
        （wrapしない、chainingしない、新しい例外型へ変換しない）ことを意味する。
        再送出された例外をどの層が受け止めるか——記事1件を失敗として記録して
        次の記事へ進むか、run全体を停止するか——は本policyの決定事項ではなく、
        DI-4 Runtime Wiringおよび既存Runtime境界（OutputManager 等）の責任である
        （設計書13.3節）。
    """

    CONTINUE_WITHOUT_FEATURED_MEDIA = "CONTINUE_WITHOUT_FEATURED_MEDIA"
    PROPAGATE_ORIGINAL_ERROR = "PROPAGATE_ORIGINAL_ERROR"


class ImageGenerationFailureCategory(Enum):
    """失敗のprovider中立な分類。

    provider名・provider固有のエラーコード・HTTPステータス・応答本文を含まない。
    """

    IMAGE_GENERATION_FAILED = "IMAGE_GENERATION_FAILED"
    IMAGE_GENERATION_REQUEST_REJECTED = "IMAGE_GENERATION_REQUEST_REJECTED"
    IMAGE_GENERATION_NOT_AUTHORIZED = "IMAGE_GENERATION_NOT_AUTHORIZED"
    MEDIA_UPLOAD_FAILED = "MEDIA_UPLOAD_FAILED"
    UNCLASSIFIED = "UNCLASSIFIED"


# module-levelの分類表。実行時に書き換えられることを想定しない
# （v4.4.0 RETRY_OUTCOME_TERMINALITY と同型。設計書11.4.1節・11.5節）。
_ACTION_BY_CATEGORY = {
    ImageGenerationFailureCategory.IMAGE_GENERATION_FAILED:
        ImageGenerationFallbackAction.CONTINUE_WITHOUT_FEATURED_MEDIA,
    ImageGenerationFailureCategory.IMAGE_GENERATION_REQUEST_REJECTED:
        ImageGenerationFallbackAction.PROPAGATE_ORIGINAL_ERROR,
    ImageGenerationFailureCategory.IMAGE_GENERATION_NOT_AUTHORIZED:
        ImageGenerationFallbackAction.PROPAGATE_ORIGINAL_ERROR,
    ImageGenerationFailureCategory.MEDIA_UPLOAD_FAILED:
        ImageGenerationFallbackAction.PROPAGATE_ORIGINAL_ERROR,
    ImageGenerationFailureCategory.UNCLASSIFIED:
        ImageGenerationFallbackAction.PROPAGATE_ORIGINAL_ERROR,
}

# CONTINUE となる reason の allow-list（設計書10.3節・10.7節 C-17）。
# 実行時に書き換えられることを想定しない。deny-list（それ以外は継続）ではなく
# allow-list（これだけが継続）であるため、v6.11が将来reasonを追加しても
# 新しい値は自動的にUNCLASSIFIED（安全側）へ落ちる。
_CONTINUABLE_REASONS = frozenset({
    OpenAIImageGenerationErrorReason.TIMEOUT,
    OpenAIImageGenerationErrorReason.CONNECTION,
    OpenAIImageGenerationErrorReason.RATE_LIMIT,
    OpenAIImageGenerationErrorReason.SERVER_ERROR,
})

# 「要求そのものが拒否された」ことを表す reason の allow-list（設計書10.5節）。
# v6.23.0（DI-11前半）でv6.11のREQUEST_REJECTEDが4値へ細分化されたため、
# 単一値の同一性照合（is）から集合照合へ変更した。
# _CONTINUABLE_REASONSと同じくallow-list（deny-listではない）であるため、
# v6.11が将来さらにreasonを追加しても、新しい値はこの集合にも
# _CONTINUABLE_REASONSにも属さず、自動的にUNCLASSIFIED（安全側）へ落ちる。
# REQUEST_REJECTEDはproductionからは生成されなくなったが、外部から構築された
# 場合に従来と同一の結論を返すため、集合に残す（後方互換）。
_REJECTED_REASONS = frozenset({
    OpenAIImageGenerationErrorReason.REQUEST_REJECTED,
    OpenAIImageGenerationErrorReason.BAD_REQUEST,
    OpenAIImageGenerationErrorReason.RESOURCE_NOT_FOUND,
    OpenAIImageGenerationErrorReason.CONFLICT,
    OpenAIImageGenerationErrorReason.UNPROCESSABLE_ENTITY,
})


@dataclass(frozen=True)
class ImageGenerationFallbackDecision:
    """decide_image_generation_fallback() の判定結果を表すImmutableな値オブジェクト。

    保存fieldは category のみ。action は category から一意に導出される
    read-only property であり、dataclass field ではない
    （repr／asdict／astuple／eq のいずれにも現れない。設計書17.2節）。
    """

    category: ImageGenerationFailureCategory

    @property
    def action(self) -> ImageGenerationFallbackAction:
        """category から導出される Fallback Action。"""
        return _ACTION_BY_CATEGORY[self.category]


def decide_image_generation_fallback(
    error: Exception,
) -> ImageGenerationFallbackDecision:
    """画像featured media処理の実行時失敗に対する判断を返す。

    Args:
        error: `ArticleFeaturedMediaOrchestrator.apply()` 実行中に捕捉された、
            Exceptionのinstance（BaseExceptionの他の系統は対象外）。

    Returns:
        ImageGenerationFallbackDecision: 常に返す（Noneを返さない）。

    Raises:
        TypeError: errorがExceptionのinstanceでない場合
            （固定message"error must be an Exception"）。
            これが本関数が送出する唯一の例外である。
    """
    if not isinstance(error, Exception):
        raise TypeError("error must be an Exception")

    if isinstance(error, OpenAIImageGenerationError):
        reason = getattr(error, "reason", None)
        if reason is OpenAIImageGenerationErrorReason.AUTHENTICATION \
                or reason is OpenAIImageGenerationErrorReason.PERMISSION_DENIED:
            category = ImageGenerationFailureCategory.IMAGE_GENERATION_NOT_AUTHORIZED
        elif (
            isinstance(reason, OpenAIImageGenerationErrorReason)
            and reason in _REJECTED_REASONS
        ):
            category = ImageGenerationFailureCategory.IMAGE_GENERATION_REQUEST_REJECTED
        elif (
            isinstance(reason, OpenAIImageGenerationErrorReason)
            and reason in _CONTINUABLE_REASONS
        ):
            category = ImageGenerationFailureCategory.IMAGE_GENERATION_FAILED
        else:
            # INVALID_RESPONSE／UNKNOWN／未知reason／reason属性欠落／
            # ハッシュ不可能なreason値（list・dict・set等）をすべてここへ落とす
            category = ImageGenerationFailureCategory.UNCLASSIFIED
    elif isinstance(error, WordPressMediaUploadError):
        category = ImageGenerationFailureCategory.MEDIA_UPLOAD_FAILED
    else:
        category = ImageGenerationFailureCategory.UNCLASSIFIED

    return ImageGenerationFallbackDecision(category=category)


def extract_safe_reason(error: Exception) -> str | None:
    """error から secret-free な reason 文字列を安全に取り出す（DI-5、v6.25.0）。

    error が allow-list 対象の既知 Exception 型であり、かつその .reason が
    その型に対応する既知 Reason Enum である場合のみ、.value（str）を返す。
    str(error)／repr(error)／type(error).__name__ はいずれも参照しない。

    各例外型は「自分自身のreason型」としか組まない（pair-wise allow-list）。
    誤った組合せ（例：OpenAIImageGenerationErrorがWordPressMediaUploadErrorReasonを
    保持する人工的なケース）はいずれもNoneへ落ちる。

    未知の Exception 型に対しては .reason へ一切アクセスしない（isinstance
    確認を先に行うことで、未知の Exception サブクラスが .reason という名前の
    property／descriptor を独自に定義し、そのgetterが例外を送出する可能性を
    排除する）。

    Args:
        error: 任意の Exception。

    Returns:
        str | None: 既知の(error型, reason型)の組合せに一致する場合はreasonの
            .value。それ以外（未知の例外型・reason属性欠落・誤った型の組合せ・
            未知reason値）はすべて None。
    """
    if isinstance(error, OpenAIImageGenerationError):
        reason = getattr(error, "reason", None)
        return reason.value if isinstance(reason, OpenAIImageGenerationErrorReason) else None
    if isinstance(error, WordPressMediaUploadError):
        reason = getattr(error, "reason", None)
        return reason.value if isinstance(reason, WordPressMediaUploadErrorReason) else None
    return None
