"""
Article Image Prompt Construction Foundation.

Source of Truth:
    docs/design/article_image_prompt_construction_foundation.md
    （Architecture Review 2：Approved with Suggestions）

Consumer-less Foundation: title・excerptから、AIImageGenerator.generate(prompt)
互換のprompt文字列を決定論的に構築する、単一責務のpure function。
outputs（ArticleData）・ai_image_generation・openai_image_generation・
generated_image_wordpress_media・article_featured_media・
article_featured_media_orchestration・image_generation_config・
generated_image_filename_policy・wordpress_media・ai（prompt_builder含む）・
main・image_resolver・Pipeline・Composition Rootのいずれへも依存しない。
"""
import re

_MAX_PROMPT_LENGTH = 1000

_PREFIX = "「"
_MID = "」というゲームニュース記事のアイキャッチ画像を生成してください。"
_EXCERPT_LABEL = "記事概要："
_EXCERPT_OPEN = "「"
_EXCERPT_CLOSE = "」。"
_SUFFIX = (
    "画像内に読める文字、透かし、UIやテキストの"
    "オーバーレイを含めないでください。"
)
_TRUNCATION_MARKER = "…"

_FIXED_LEN_TITLE_ONLY = (
    len(_PREFIX)
    + len(_MID)
    + len(_SUFFIX)
)

_FIXED_LEN_WITH_EXCERPT = (
    len(_PREFIX)
    + len(_MID)
    + len(_EXCERPT_LABEL)
    + len(_EXCERPT_OPEN)
    + len(_EXCERPT_CLOSE)
    + len(_SUFFIX)
)

_CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")
_WHITESPACE_PATTERN = re.compile(r"\s+")


def _normalize(value: str) -> str:
    """ASCII制御文字（\\t\\n\\rを除く）をspaceへ、\\s+一致空白を半角space 1個へ
    収束させ、前後空白を除去する。zero-width space・Unicode format
    characters・bidi control charactersはこの正規化の対象外（保証しない）。"""
    cleaned = _CONTROL_CHAR_PATTERN.sub(" ", value)
    cleaned = _WHITESPACE_PATTERN.sub(" ", cleaned)
    return cleaned.strip()


def _fit(text: str, budget: int) -> str:
    """textをbudget code point以内へ収める。収まる場合はそのまま返す。
    収まらない場合は末尾を切り詰め、_TRUNCATION_MARKER（1 code point）を
    budgetへ含めて付与する。budget <= 0の場合は空文字を返す。"""
    if budget <= 0:
        return ""

    if len(text) <= budget:
        return text

    if budget == 1:
        return _TRUNCATION_MARKER

    return (
        text[: budget - len(_TRUNCATION_MARKER)]
        + _TRUNCATION_MARKER
    )


def _assemble_title_only(normalized_title: str) -> str:
    title_budget = (
        _MAX_PROMPT_LENGTH
        - _FIXED_LEN_TITLE_ONLY
    )

    fitted_title = _fit(
        normalized_title,
        title_budget,
    )

    return (
        _PREFIX
        + fitted_title
        + _MID
        + _SUFFIX
    ).strip()


def construct_article_image_prompt(title: str, excerpt: str) -> str:
    """
    記事のtitle・excerptから、画像生成用prompt文字列を決定論的に構築する。

    Args:
        title: 記事タイトル相当のplain text。必須、空・空白のみは不可。
        excerpt: 記事概要相当のplain text。空文字列を許容する。

    Returns:
        str: 常に非空・単一行・長さ1000以下のprompt文字列。
             固定suffixを常に完全な形で含む。

    Raises:
        ValueError: titleがstrでない場合（"title must be a str"）。
        ValueError: 正規化後のtitleが空になる場合（"title must not be blank"）。
        ValueError: excerptがstrでない場合（"excerpt must be a str"）。
    """
    if not isinstance(title, str):
        raise ValueError("title must be a str")
    normalized_title = _normalize(title)
    if not normalized_title:
        raise ValueError("title must not be blank")

    if not isinstance(excerpt, str):
        raise ValueError("excerpt must be a str")
    normalized_excerpt = _normalize(excerpt)

    if not normalized_excerpt:
        return _assemble_title_only(normalized_title)

    title_budget = (
        _MAX_PROMPT_LENGTH
        - _FIXED_LEN_WITH_EXCERPT
    )
    fitted_title = _fit(normalized_title, title_budget)
    remaining = title_budget - len(fitted_title)
    fitted_excerpt = _fit(normalized_excerpt, remaining) if remaining > 0 else ""

    if not fitted_excerpt:
        return _assemble_title_only(normalized_title)

    return (
        _PREFIX
        + fitted_title
        + _MID
        + _EXCERPT_LABEL
        + _EXCERPT_OPEN
        + fitted_excerpt
        + _EXCERPT_CLOSE
        + _SUFFIX
    ).strip()
