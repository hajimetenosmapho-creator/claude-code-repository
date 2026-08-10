"""
Article Featured Media Runtime Foundation.

Source of Truth:
    docs/design/article_featured_media_runtime_wiring.md
    （Architecture Review 2：Approved with Suggestions／Architecture Amendment 2）

Release 6.9.0〜6.19.0で整備された画像系Foundationを、main.pyが唯一参照する
Facadeとして単一責務にまとめる：Gate評価の委譲・prompt構築・filename構築・
Orchestrator呼び出し・fallback policy消費。main.pyへの実接続（配線）は
DI-4 Runtime Wiring（v6.21.0）の責務であり、本packageはconsumer-lessである
（main.py・image_resolver.py・outputs・pipeline・scripts・ai・scheduler・
retry_*関連の既存コードのいずれへも依存しない）。

provider adapter（OpenAIImageGenerator）・Orchestrator（v6.14.0）へ継続／伝播の
業務判断を持たせない（設計書5.4節）。継続／伝播の判断は
decide_image_generation_fallback()（v6.19.0）のみが行い、その消費は本Facade
のapply()のみが行う。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from article_featured_media_composition import ArticleFeaturedMediaCompositionRoot
from article_image_prompt_construction import construct_article_image_prompt
from generated_image_filename_policy import generate_image_filename
from image_generation_fallback_policy import (
    ImageGenerationFailureCategory,
    ImageGenerationFallbackAction,
    ImageGenerationFallbackDecision,
    decide_image_generation_fallback,
    extract_safe_reason,
)
from outputs import ArticleData


class ArticleFeaturedMediaRuntimeStatus(Enum):
    """apply() の結果種別。provider中立。"""

    DISABLED = "DISABLED"
    APPLIED = "APPLIED"
    CONTINUED_WITHOUT_FEATURED_MEDIA = "CONTINUED_WITHOUT_FEATURED_MEDIA"


@dataclass(frozen=True)
class FeaturedMediaFailureObservation:
    """featured media処理失敗の観測用スナップショット（DI-5、v6.25.0）。

    fallback判断（apply()内部のCONTINUE/PROPAGATE決定）には一切関与しない、
    読み取り専用の記録専用オブジェクト。raw exception・例外message・prompt・
    credential・Provider応答本文・image bytesのいずれも保持しない。
    """

    category: ImageGenerationFailureCategory
    action: ImageGenerationFallbackAction
    reason: str | None


def _build_observation(
    decision: ImageGenerationFallbackDecision, error: Exception
) -> FeaturedMediaFailureObservation:
    """decisionとerrorから observation を1回だけ構築する（DI-5、v6.25.0）。

    CONTINUE（apply()内部）とPROPAGATE（classify_propagated_failure()）の
    両方が使用する唯一の生成箇所。
    """
    return FeaturedMediaFailureObservation(
        category=decision.category,
        action=decision.action,
        reason=extract_safe_reason(error),
    )


@dataclass(frozen=True)
class ArticleFeaturedMediaRuntimeResult:
    """apply() の戻り値。Immutable。

    Attributes:
        article:     DISABLED／CONTINUED_WITHOUT_FEATURED_MEDIA時は引数と同一object
                     （未改変）。APPLIED時はOrchestratorが返した新しいArticleData。
        status:      apply() の結果種別。
        category:    CONTINUED_WITHOUT_FEATURED_MEDIA の場合にのみ非None。
                     v6.19.0 の provider中立5値であり、秘密情報・provider名を含まない。
        observation: CONTINUED_WITHOUT_FEATURED_MEDIA の場合にのみ非None
                     （DI-5、v6.25.0）。category／action／reasonをまとめて
                     保持する観測用スナップショット。
    """

    article: ArticleData
    status: ArticleFeaturedMediaRuntimeStatus
    category: ImageGenerationFailureCategory | None = None
    observation: FeaturedMediaFailureObservation | None = None


class ArticleFeaturedMediaRuntime:
    """
    ArticleFeaturedMediaCompositionRoot（v6.18.0）を Constructor Injection で
    受け取り、記事1件に対する featured media 適用を行う唯一の Facade。

    root は ArticleFeaturedMediaCompositionRoot を想定するが、isinstance による
    nominal型検証は行わない（Duck Typing。v6.12.0 GeneratedImageWordPressMediaUploader
    のprecedentに従う）。
    """

    def __init__(self, root) -> None:
        self._root = root

    @classmethod
    def from_env(cls) -> "ArticleFeaturedMediaRuntime":
        """
        環境変数からConfiguration・credentialを読み込み、Facadeを構築する。

        ArticleFeaturedMediaCompositionRoot.from_env() へ委譲するのみ。
        Gate OFF なら無効状態、Gate ON かつ credential 不足なら既存factoryの
        ValueError を無変換伝播する（Fail Fast。v6.18.0 の Contract をそのまま踏襲）。
        """
        return cls(ArticleFeaturedMediaCompositionRoot.from_env())

    def is_available(self) -> bool:
        """画像featured media処理を実行してよいかを返す。例外を送出しない。"""
        return self._root.is_available()

    def apply(self, article: ArticleData) -> ArticleFeaturedMediaRuntimeResult:
        """
        記事1件に対し、featured media の生成・Upload・Bindingを試みる。

        Args:
            article: 対象のArticleData。

        Returns:
            ArticleFeaturedMediaRuntimeResult: 常に返す。

        Raises:
            ValueError: article が ArticleData のinstanceでない場合。
            Exception: PROPAGATE_ORIGINAL_ERROR と判断された場合、
                orchestrator.apply() が送出した元の例外を無変換で再送出する
                （bare raise。wrap・chaining・型変換・message加工を行わない）。
        """
        if not isinstance(article, ArticleData):
            raise ValueError("article must be an ArticleData")

        if not self.is_available():
            return ArticleFeaturedMediaRuntimeResult(
                article=article,
                status=ArticleFeaturedMediaRuntimeStatus.DISABLED,
                category=None,
            )

        prompt = construct_article_image_prompt(article.seo_title, article.excerpt)
        filename = generate_image_filename(article.seo_title, self._root.image_mime_type)

        try:
            applied_article = self._root.orchestrator.apply(article, prompt, filename)
        except Exception as error:
            decision = decide_image_generation_fallback(error)
            if decision.action is ImageGenerationFallbackAction.PROPAGATE_ORIGINAL_ERROR:
                raise
            return ArticleFeaturedMediaRuntimeResult(
                article=article,
                status=ArticleFeaturedMediaRuntimeStatus.CONTINUED_WITHOUT_FEATURED_MEDIA,
                category=decision.category,
                observation=_build_observation(decision, error),
            )

        return ArticleFeaturedMediaRuntimeResult(
            article=applied_article,
            status=ArticleFeaturedMediaRuntimeStatus.APPLIED,
            category=None,
        )

    def classify_propagated_failure(self, error: Exception) -> FeaturedMediaFailureObservation:
        """PROPAGATE後、呼び出し側（main.py）がobservability目的で失敗を分類する
        ための読み取り専用API（DI-5、v6.25.0）。

        apply() 内部のCONTINUE/PROPAGATE決定には一切関与しない。stateを持たず、
        I/Oも行わない。error を読み取るのみで、変更・再送出・wrapは一切行わない。

        Args:
            error: apply() がbare raiseした（呼び出し側が捕捉した）元の例外。

        Returns:
            FeaturedMediaFailureObservation: category／action／reasonの
                観測用スナップショット。
        """
        decision = decide_image_generation_fallback(error)
        return _build_observation(decision, error)
