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
（v6.11が secret-free と定めた分類Enum）の同一性比較（`is`）のみに基づき、
例外message・provider応答本文・HTTPステータスコードのいずれも読み取らない
（設計書13.2節・13.5節）。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from openai_image_generation import (
    OpenAIImageGenerationError,
    OpenAIImageGenerationErrorReason,
)
from wordpress_media import WordPressMediaUploadError


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
        elif reason is OpenAIImageGenerationErrorReason.REQUEST_REJECTED:
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
