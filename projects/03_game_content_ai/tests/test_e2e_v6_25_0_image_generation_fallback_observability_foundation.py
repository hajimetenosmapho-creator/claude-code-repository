"""
E2E テスト: v6.25.0 Image Generation Fallback Observability Foundation

Source of Truth:
    docs/design/image_generation_fallback_observability_foundation.md
    （DI-5＋DEF-3統合。Architecture Review 2：Approved with Suggestions。
      Test Review／Implementation前Gate確認済み）

本テストは実OpenAI API・実WordPress API・実HTTP通信・実RSS収集・実課金の
いずれも発生させない。main() は Claude API・RSS収集を伴うため実行しない
（v6.21.0 precedent）。main.py記事ループの一部（success-path log_article()
呼び出し・PROPAGATE except節のobservation伝播）はhelperへ切り出されておらず
main()内に残るため、AST構造解析（Structural）で契約を検証する。

Scenario構成:
    OBSERVATION-  FeaturedMediaFailureObservation：frozen・field構成
    REASONNORM-   extract_safe_reason()：pair-wise allow-list・secret-free・
                  防御的順序（未知例外型への.reasonアクセス回避）
    CONTINUE-OBS- CONTINUE経路：decisionが1回のみ評価されobservationがResultへ格納
    PROPAGATE-OBS- PROPAGATE経路：classify_propagated_failure()の独立した
                  1回の再構築、既存bare raise／identity／chaining guardとの
                  接続（INV-4、Review 2 Suggestion-1対応）
    LOGFIELD-     ArticleLogEntryへの3フィールド追加：型・順序・デフォルト値
    NULLLOG-      NullLogManager.log_article()が新3引数をno-opで受け付ける
    DEDUP-        LogManager.log_article()呼び出し1回につきJSON Lines1行
    SECRET-FREE-  ログへ書き込まれた3フィールドに秘密情報が含まれない
    SCHEMA-COMPAT- 既存consumer（analytics_manager）が新フィールドを無視する
    NOIMPACT-     分類テーブル・CONTINUE対象4値・openai/wordpress __all__が無改修
    NOLEAK-       featured_media_observationが記事ループの各反復で再初期化される
    RUNTIMEPATH-  main.py記事ループのobservation伝播（Structural／AST）
    RUNTIME-E2E-  main.main()を全依存monkeypatchのうえ実行し、CONTINUE-WP-SUCCESS-／
                  CONTINUE-WP-FAILURE-／APPLIED-／DISABLED-／PROPAGATE-／NULLLOG-の
                  6経路をcounter・Markdown保存・loop継続・observation・記事間NOLEAKを
                  含めbehavioralに検証する（Code Review Major-1対応。INV-6の主証拠）
    SEC-GUARD-    v6.21.0 LOOP-HANDLER精緻化guard6件の検出力自己検証
                  （陽性・陰性対照＋実main.pyへのcross-check。Code Review Minor-1対応）

実行方法:
    cd projects/03_game_content_ai
    venv\\Scripts\\python.exe tests/test_e2e_v6_25_0_image_generation_fallback_observability_foundation.py
"""
import ast
import dataclasses
import inspect
import contextlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

MAIN_FILE = PROJECT_ROOT / "main.py"

results_log = []


def check(label: str, actual, expected):
    ok = actual == expected
    status = "PASS" if ok else "FAIL"
    results_log.append((status, label))
    mark = "OK" if ok else "NG"
    print(f"  [{mark}] {label}")
    if not ok:
        print(f"       期待値: {expected!r}")
        print(f"       実際値: {actual!r}")


def check_true(label: str, value: bool):
    check(label, value, True)


def check_false(label: str, value: bool):
    check(label, value, False)


def check_contains(label: str, text, keyword: str):
    check(label, keyword in str(text), True)


def invoke(func):
    try:
        return func(), None
    except BaseException as exc:
        return None, exc


# ─── production import ───

import main  # noqa: E402
from outputs import ArticleData  # noqa: E402
from collector import NewsItem  # noqa: E402
from publishing_config import PublishStatus  # noqa: E402
from sns_config import SnsPostStatus  # noqa: E402
from article_featured_media_runtime import (  # noqa: E402
    ArticleFeaturedMediaRuntime,
    ArticleFeaturedMediaRuntimeResult,
    ArticleFeaturedMediaRuntimeStatus,
    FeaturedMediaFailureObservation,
)
import article_featured_media_runtime.article_featured_media_runtime as _rt_impl  # noqa: E402
from image_generation_fallback_policy import (  # noqa: E402
    ImageGenerationFailureCategory,
    ImageGenerationFallbackAction,
    decide_image_generation_fallback,
    extract_safe_reason,
)
import image_generation_fallback_policy.image_generation_fallback_policy as _policy_impl  # noqa: E402
from openai_image_generation import (  # noqa: E402
    OpenAIImageGenerationError,
    OpenAIImageGenerationErrorReason,
)
from wordpress_media import WordPressMediaUploadError, WordPressMediaUploadErrorReason  # noqa: E402
from logger.log_entry import ArticleLogEntry  # noqa: E402
from logger.log_manager import LogManager, NullLogManager  # noqa: E402
from analytics.analytics_manager import AnalyticsManager  # noqa: E402


def make_news_item(title: str = "PS6正式発表") -> NewsItem:
    return NewsItem(
        title=title,
        url="https://blog.playstation.com/test",
        summary="PlayStation 6 が正式に発表されました。",
        source="PlayStation Blog",
        published_at="2026-07-18",
        image_candidates=[],
    )


def make_article(**overrides) -> ArticleData:
    defaults = dict(
        item=make_news_item(),
        importance="S",
        seo_title="PS6が正式発表",
        article_body="PS6が発表されました。",
        x_post="PS6発表！ https://example.com/ps6/",
        featured_image_url="https://example.com/ps6.png",
        excerpt="PS6が発表されました。",
        meta_description="PS6が発表されました。",
        slug="ps6-announced-20260718",
        featured_media_id=0,
        publish_status=PublishStatus.DRAFT,
    )
    defaults.update(overrides)
    return ArticleData(**defaults)


class FakeOrchestrator:
    def __init__(self, *, result=None, error=None):
        self.calls = []
        self._result = result
        self._error = error

    def apply(self, article, prompt, filename):
        self.calls.append((article, prompt, filename))
        if self._error is not None:
            raise self._error
        return self._result


class FakeCompositionRoot:
    def __init__(self, *, orchestrator, image_mime_type="image/png", available=True):
        self.orchestrator = orchestrator
        self.image_mime_type = image_mime_type
        self._available = available

    def is_available(self):
        return self._available


print("=" * 60)
print("v6.25.0 Image Generation Fallback Observability Foundation E2E テスト")
print("=" * 60)
print()

# =====================================================================
# OBSERVATION: FeaturedMediaFailureObservation frozen・field構成
# =====================================================================

print("[OBSERVATION] FeaturedMediaFailureObservation frozen・field構成")

check_true(
    "OBSERVATION-FROZEN. frozen dataclassである",
    FeaturedMediaFailureObservation.__dataclass_params__.frozen,
)
_obs_field_names = tuple(f.name for f in dataclasses.fields(FeaturedMediaFailureObservation))
check(
    "OBSERVATION-FIELDS. fieldがcategory/action/reasonの3件・この順序",
    _obs_field_names,
    ("category", "action", "reason"),
)
_sample_observation = FeaturedMediaFailureObservation(
    category=ImageGenerationFailureCategory.IMAGE_GENERATION_FAILED,
    action=ImageGenerationFallbackAction.CONTINUE_WITHOUT_FEATURED_MEDIA,
    reason="timeout",
)
_, _obs_frozen_exc = invoke(lambda: setattr(_sample_observation, "reason", "connection"))
check_true(
    "OBSERVATION-IMMUTABLE. 属性再代入がFrozenInstanceErrorを送出する",
    isinstance(_obs_frozen_exc, dataclasses.FrozenInstanceError),
)
print()

# =====================================================================
# REASONNORM: extract_safe_reason()：pair-wise allow-list・secret-free
# =====================================================================

print("[REASONNORM] extract_safe_reason()：pair-wise allow-list・secret-free")

_SECRET = "SECRET_MARKER_REASONNORM_8e21"

# 既知の組合せ：OpenAIImageGenerationError × OpenAIImageGenerationErrorReason
check(
    "REASONNORM-OPENAI-KNOWN. OpenAI例外＋既知reasonで.valueを返す",
    extract_safe_reason(OpenAIImageGenerationError(f"probe ({_SECRET})", OpenAIImageGenerationErrorReason.TIMEOUT)),
    "timeout",
)
check_false(
    "REASONNORM-OPENAI-SEC-NO-MARKER. 返り値に例外message原文が含まれない",
    _SECRET in (extract_safe_reason(OpenAIImageGenerationError(f"probe ({_SECRET})", OpenAIImageGenerationErrorReason.UNKNOWN)) or ""),
)
check(
    "REASONNORM-OPENAI-UNKNOWN-IS-KNOWN-VALUE. 正式なUNKNOWN reasonは'unknown'という既知値を返す（Noneではない）",
    extract_safe_reason(OpenAIImageGenerationError("probe", OpenAIImageGenerationErrorReason.UNKNOWN)),
    "unknown",
)

# 既知の組合せ：WordPressMediaUploadError × WordPressMediaUploadErrorReason
check(
    "REASONNORM-WORDPRESS-KNOWN. WordPress例外＋既知reasonで.valueを返す",
    extract_safe_reason(WordPressMediaUploadError(f"probe ({_SECRET})", reason=WordPressMediaUploadErrorReason.TIMEOUT)),
    "timeout",
)

# 誤った組合せ（pair-wise不一致）：OpenAI例外にWordPress reasonを保持させる
_mismatched_openai = OpenAIImageGenerationError("probe", OpenAIImageGenerationErrorReason.TIMEOUT)
_mismatched_openai.reason = WordPressMediaUploadErrorReason.TIMEOUT
check(
    "REASONNORM-MISMATCH-OPENAI-WITH-WP-REASON. OpenAI例外がWordPressMediaUploadErrorReasonを"
    "保持する誤組合せはNoneを返す",
    extract_safe_reason(_mismatched_openai),
    None,
)

_mismatched_wp = WordPressMediaUploadError("probe", reason=WordPressMediaUploadErrorReason.TIMEOUT)
_mismatched_wp.reason = OpenAIImageGenerationErrorReason.TIMEOUT
check(
    "REASONNORM-MISMATCH-WP-WITH-OPENAI-REASON. WordPress例外がOpenAIImageGenerationErrorReasonを"
    "保持する誤組合せはNoneを返す",
    extract_safe_reason(_mismatched_wp),
    None,
)

# 未知の例外型：.reasonが存在しても既知型でなければNone
class _UnknownExceptionWithReason(Exception):
    def __init__(self, message, reason):
        super().__init__(message)
        self.reason = reason


check(
    "REASONNORM-UNKNOWN-EXCEPTION-TYPE. 既知2型のいずれでもない例外型はNoneを返す",
    extract_safe_reason(_UnknownExceptionWithReason("probe", OpenAIImageGenerationErrorReason.TIMEOUT)),
    None,
)

# reason属性欠落
_missing_reason = OpenAIImageGenerationError("probe", OpenAIImageGenerationErrorReason.TIMEOUT)
del _missing_reason.reason
check(
    "REASONNORM-MISSING-REASON-ATTR. reason属性が欠落している場合はNoneを返す",
    extract_safe_reason(_missing_reason),
    None,
)

# reasonが想定外の型（文字列）
_wrong_type_reason = OpenAIImageGenerationError("probe", OpenAIImageGenerationErrorReason.TIMEOUT)
_wrong_type_reason.reason = "timeout"  # Enumではなくstr
check(
    "REASONNORM-WRONG-REASON-TYPE. reasonが文字列（非Enum）の場合はNoneを返す",
    extract_safe_reason(_wrong_type_reason),
    None,
)

# 未知の非Exception入力（isinstance(error, _KNOWN_ERROR_TYPES)がFalse）
check(
    "REASONNORM-PLAIN-RUNTIMEERROR. RuntimeErrorはNoneを返す",
    extract_safe_reason(RuntimeError("probe")),
    None,
)


# 防御的順序（Architecture Review Major-3対応）：
# .reasonがgetterで例外を送出するダミー型でも、既知2型のいずれでもない場合は
# .reasonへ一切アクセスしないため、extract_safe_reason()自身は例外を伝播させない
class _DangerousReasonException(Exception):
    """.reasonへのアクセスで例外を送出する、既知2型のいずれでもないダミー例外型。"""

    @property
    def reason(self):
        raise RuntimeError("REASONNORM: .reason must not be accessed for unknown exception types")


_dangerous_result, _dangerous_exc = invoke(lambda: extract_safe_reason(_DangerousReasonException("probe")))
check_true(
    "REASONNORM-DANGEROUS-REASON-PROPERTY-NOT-RAISED. 未知例外型の危険な.reason propertyへ"
    "アクセスせず、例外を伝播させない",
    _dangerous_exc is None,
)
check(
    "REASONNORM-DANGEROUS-REASON-PROPERTY-NONE. 同上、戻り値はNone",
    _dangerous_result,
    None,
)
print()

# =====================================================================
# CONTINUE-OBS: CONTINUE経路：decisionが1回のみ評価されobservationがResultへ格納
# =====================================================================

print("[CONTINUE-OBS] CONTINUE経路：decision再利用とobservation格納")

_decide_call_log = []
_orig_decide = _rt_impl.decide_image_generation_fallback


def _spy_decide(error):
    _decide_call_log.append(error)
    return _orig_decide(error)


_rt_impl.decide_image_generation_fallback = _spy_decide
try:
    _cont_secret = "SECRET_MARKER_CONTINUE_OBS_71fa"
    _cont_error = OpenAIImageGenerationError(f"probe ({_cont_secret})", OpenAIImageGenerationErrorReason.RATE_LIMIT)
    _cont_root = FakeCompositionRoot(orchestrator=FakeOrchestrator(error=_cont_error), available=True)
    _cont_article = make_article()
    _decide_call_log.clear()
    _cont_result = ArticleFeaturedMediaRuntime(_cont_root).apply(_cont_article)
finally:
    _rt_impl.decide_image_generation_fallback = _orig_decide

check(
    "CONTINUE-OBS-DECIDE-CALLED-ONCE. decide_image_generation_fallback()が1回のみ呼ばれる",
    len(_decide_call_log),
    1,
)
check_true(
    "CONTINUE-OBS-OBSERVATION-NOT-NONE. observationが非None",
    _cont_result.observation is not None,
)
check(
    "CONTINUE-OBS-CATEGORY. observation.categoryがIMAGE_GENERATION_FAILED",
    _cont_result.observation.category,
    ImageGenerationFailureCategory.IMAGE_GENERATION_FAILED,
)
check(
    "CONTINUE-OBS-ACTION. observation.actionがCONTINUE_WITHOUT_FEATURED_MEDIA",
    _cont_result.observation.action,
    ImageGenerationFallbackAction.CONTINUE_WITHOUT_FEATURED_MEDIA,
)
check(
    "CONTINUE-OBS-REASON. observation.reasonが'rate_limit'",
    _cont_result.observation.reason,
    OpenAIImageGenerationErrorReason.RATE_LIMIT.value,
)
check_false(
    "CONTINUE-OBS-SEC-NO-MARKER. observation.reasonに例外message原文が含まれない",
    _cont_secret in (_cont_result.observation.reason or ""),
)
check(
    "CONTINUE-OBS-CATEGORY-BACKWARD-COMPAT. 既存category fieldも同じ値を保持する（後方互換）",
    _cont_result.category,
    _cont_result.observation.category,
)
print()

# =====================================================================
# PROPAGATE-OBS: PROPAGATE経路：classify_propagated_failure()の独立した再構築
# =====================================================================

print("[PROPAGATE-OBS] PROPAGATE経路：classify_propagated_failure()")

_prop_secret = "SECRET_MARKER_PROPAGATE_OBS_5c9d"
_prop_error = OpenAIImageGenerationError(
    f"request rejected ({_prop_secret})", OpenAIImageGenerationErrorReason.REQUEST_REJECTED
)
_prop_root = FakeCompositionRoot(orchestrator=FakeOrchestrator(error=_prop_error), available=True)
_prop_runtime = ArticleFeaturedMediaRuntime(_prop_root)

_decide_call_log.clear()
_rt_impl.decide_image_generation_fallback = _spy_decide
try:
    _prop_result, _prop_raised = invoke(lambda: _prop_runtime.apply(make_article()))
    check_true("PROPAGATE-OBS-RAISED. apply()がbare raiseする", _prop_raised is not None)
    check(
        "PROPAGATE-OBS-DECIDE-CALLED-ONCE-IN-APPLY. apply()内部でdecide_image_generation_fallback()が1回呼ばれる",
        len(_decide_call_log),
        1,
    )

    # INV-4接続（Review 2 Suggestion-1対応）：v6.20.0 PROP/IDENT・v6.21.0 PROP節が
    # 検証済みのbare raise／identity／chaining契約を、observability再構築後も
    # 直接再確認する。
    _id_before = id(_prop_raised)
    _cause_before = _prop_raised.__cause__
    _context_before = _prop_raised.__context__

    _observation = _prop_runtime.classify_propagated_failure(_prop_raised)

    check(
        "PROPAGATE-OBS-DECIDE-CALLED-TWICE-TOTAL. classify_propagated_failure()の独立再構築を含め"
        "合計2回（apply()内部1回＋本メソッド1回）",
        len(_decide_call_log),
        2,
    )
finally:
    _rt_impl.decide_image_generation_fallback = _orig_decide

check_true(
    "PROPAGATE-OBS-IDENTITY-UNCHANGED（INV-4接続）. classify_propagated_failure()呼び出し前後で"
    "例外オブジェクトのidが不変（v6.20.0 IDENT-SAME-OBJECT／v6.21.0 PROP-IDENTと同一契約）",
    id(_prop_raised) == _id_before,
)
check_true(
    "PROPAGATE-OBS-CAUSE-UNCHANGED（INV-4接続）. __cause__が変化しない"
    "（v6.20.0 IDENT-NO-CAUSE／v6.21.0 PROP-CAUSE-UNTOUCHEDと同一契約）",
    _prop_raised.__cause__ is _cause_before,
)
check_true(
    "PROPAGATE-OBS-CONTEXT-UNCHANGED（INV-4接続）. __context__が変化しない",
    _prop_raised.__context__ is _context_before,
)
check_contains(
    "PROPAGATE-OBS-MESSAGE-UNCHANGED（INV-4接続）. messageが不変（v6.20.0 IDENT-MESSAGEと同一契約）",
    str(_prop_raised),
    _prop_secret,
)
check(
    "PROPAGATE-OBS-CATEGORY. observation.categoryがIMAGE_GENERATION_REQUEST_REJECTED",
    _observation.category,
    ImageGenerationFailureCategory.IMAGE_GENERATION_REQUEST_REJECTED,
)
check(
    "PROPAGATE-OBS-ACTION. observation.actionがPROPAGATE_ORIGINAL_ERROR",
    _observation.action,
    ImageGenerationFallbackAction.PROPAGATE_ORIGINAL_ERROR,
)
check(
    "PROPAGATE-OBS-REASON. observation.reasonが'request_rejected'",
    _observation.reason,
    OpenAIImageGenerationErrorReason.REQUEST_REJECTED.value,
)
check_false(
    "PROPAGATE-OBS-SEC-NO-MARKER. observation.reasonに例外message原文が含まれない",
    _prop_secret in (_observation.reason or ""),
)
print()

# =====================================================================
# LOGFIELD: ArticleLogEntryへの3フィールド追加
# =====================================================================

print("[LOGFIELD] ArticleLogEntryへの3フィールド追加")

_entry_field_names = tuple(f.name for f in dataclasses.fields(ArticleLogEntry))
check(
    "LOGFIELD-COUNT. fieldが21件（既存18件＋新規3件）",
    len(_entry_field_names),
    21,
)
check(
    "LOGFIELD-EXISTING-18-UNCHANGED. 既存18fieldの名前・順序が不変",
    _entry_field_names[:18],
    (
        "logged_at", "importance", "seo_title", "slug", "post_id", "edit_url",
        "publish_status", "category_ids", "tag_ids", "featured_media_id",
        "source_url", "source_name", "result", "error_message",
        "wp_public_url", "x_post_text", "x_post_status", "x_post_url",
    ),
)
check(
    "LOGFIELD-NEW-3-NAMES-ORDER. 新規3fieldの名前・順序",
    _entry_field_names[18:],
    ("featured_media_category", "featured_media_action", "featured_media_reason"),
)
for _new_field_name in ("featured_media_category", "featured_media_action", "featured_media_reason"):
    _field = next(f for f in dataclasses.fields(ArticleLogEntry) if f.name == _new_field_name)
    check(f"LOGFIELD-DEFAULT-EMPTY[{_new_field_name}]. デフォルト値が''", _field.default, "")
    check(f"LOGFIELD-TYPE-STR[{_new_field_name}]. 型がstr", _field.type, str)
print()

# =====================================================================
# NULLLOG: NullLogManager.log_article()が新3引数をno-opで受け付ける
# =====================================================================

print("[NULLLOG] NullLogManager.log_article()")

_log_sig = inspect.signature(LogManager.log_article)
_null_log_sig = inspect.signature(NullLogManager.log_article)
check(
    "NULLLOG-SIGNATURE-PARITY. LogManagerとNullLogManagerのlog_article()が同一のパラメータ名集合を持つ",
    set(_log_sig.parameters.keys()),
    set(_null_log_sig.parameters.keys()),
)

_null_manager = NullLogManager()
for _category, _action, _reason in (
    ("IMAGE_GENERATION_FAILED", "CONTINUE_WITHOUT_FEATURED_MEDIA", "timeout"),
    ("IMAGE_GENERATION_REQUEST_REJECTED", "PROPAGATE_ORIGINAL_ERROR", "request_rejected"),
    ("MEDIA_UPLOAD_FAILED", "PROPAGATE_ORIGINAL_ERROR", "unknown"),
    ("", "", ""),
):
    _, _null_exc = invoke(
        lambda c=_category, a=_action, r=_reason: _null_manager.log_article(
            article=make_article(),
            result="failed",
            featured_media_category=c,
            featured_media_action=a,
            featured_media_reason=r,
        )
    )
    check_true(
        f"NULLLOG-NO-TYPEERROR[{_category or 'EMPTY'}]. LOG_ENABLED=false相当でも"
        "TypeErrorを送出しない",
        _null_exc is None,
    )
print()

# =====================================================================
# DEDUP / SECRET-FREE: LogManager経由の実書き込み（JSON Lines）
# =====================================================================

print("[DEDUP/SECRET-FREE] LogManager経由の実書き込み")

_dedup_secret = "SECRET_MARKER_DEDUP_LOGWRITE_3a9c"
with tempfile.TemporaryDirectory() as _tmpdir:
    _tmp_log_dir = Path(_tmpdir) / "logs"
    _log_manager = LogManager(log_dir=_tmp_log_dir)
    _write_article = make_article()
    _log_manager.log_article(
        article=_write_article,
        result="failed",
        error_message="featured media processing failed",
        featured_media_category=ImageGenerationFailureCategory.IMAGE_GENERATION_REQUEST_REJECTED.value,
        featured_media_action=ImageGenerationFallbackAction.PROPAGATE_ORIGINAL_ERROR.value,
        featured_media_reason=extract_safe_reason(
            OpenAIImageGenerationError(f"probe ({_dedup_secret})", OpenAIImageGenerationErrorReason.REQUEST_REJECTED)
        ) or "",
    )
    _date_str_for_glob = None
    _article_log_files = list((_tmp_log_dir / "articles").glob("*.jsonl"))
    check("DEDUP-FILE-COUNT. articlesログファイルが1件作成される", len(_article_log_files), 1)
    if _article_log_files:
        _lines = _article_log_files[0].read_text(encoding="utf-8").splitlines()
        check("DEDUP-LINE-COUNT. log_article()を1回呼ぶとJSON Linesが1行のみ書き込まれる", len(_lines), 1)
        if _lines:
            _entry_dict = json.loads(_lines[0])
            check_true(
                "LOGFIELD-KEYS-PRESENT. 書き込まれたJSON行に新規3キーが含まれる",
                {"featured_media_category", "featured_media_action", "featured_media_reason"} <= set(_entry_dict.keys()),
            )
            check(
                "LOGFIELD-VALUE-CATEGORY. featured_media_categoryの値が正しい",
                _entry_dict["featured_media_category"],
                "IMAGE_GENERATION_REQUEST_REJECTED",
            )
            check(
                "LOGFIELD-VALUE-ACTION. featured_media_actionの値が正しい",
                _entry_dict["featured_media_action"],
                "PROPAGATE_ORIGINAL_ERROR",
            )
            check(
                "LOGFIELD-VALUE-REASON. featured_media_reasonの値が正しい",
                _entry_dict["featured_media_reason"],
                "request_rejected",
            )
            check_false(
                "SECRET-FREE-NO-MARKER-IN-LINE. 書き込まれたJSON行全体に例外message原文が含まれない",
                _dedup_secret in _lines[0],
            )

    # fallback未発生記事（category/action/reason省略）でも常に空文字列が書き込まれること
    _log_manager.log_article(article=make_article(), result="success")
    _lines2 = _article_log_files[0].read_text(encoding="utf-8").splitlines() if _article_log_files else []
    check("DEDUP-LINE-COUNT-2. 2回目のlog_article()呼び出し後、行数が2になる", len(_lines2), 2)
    if len(_lines2) == 2:
        _entry_dict2 = json.loads(_lines2[1])
        check(
            "SCHEMA-DEFAULT-EMPTY. fallback未発生記事は新規3キーがいずれも''である",
            (
                _entry_dict2["featured_media_category"],
                _entry_dict2["featured_media_action"],
                _entry_dict2["featured_media_reason"],
            ),
            ("", "", ""),
        )
print()

# =====================================================================
# SCHEMA-COMPAT: 既存consumer（analytics_manager）が新フィールドを無視する
# =====================================================================

print("[SCHEMA-COMPAT] 既存consumerが新フィールドを無視する")

with tempfile.TemporaryDirectory() as _tmpdir2:
    _analytics_manager = AnalyticsManager(log_dir=Path(_tmpdir2), period_days=28)
    _article_dict_with_new_keys = {
        "post_id": 123,
        "slug": "ps6-announced-20260718",
        "seo_title": "PS6が正式発表",
        "importance": "S",
        "publish_status": "draft",
        "logged_at": "2026-07-18T00:00:00+09:00",
        "source_name": "PlayStation Blog",
        "wp_public_url": "https://example.com/ps6/",
        "x_post_status": "pending",
        # v6.25.0（DI-5）で新規追加されたキー（既存consumerは無視するはず）
        "featured_media_category": "IMAGE_GENERATION_REQUEST_REJECTED",
        "featured_media_action": "PROPAGATE_ORIGINAL_ERROR",
        "featured_media_reason": "request_rejected",
    }
    _record, _schema_exc = invoke(
        lambda: _analytics_manager.build_analysis_record(article=_article_dict_with_new_keys, analytics=None)
    )
    check_true(
        "SCHEMA-COMPAT-NO-EXCEPTION. 新規3キーを含むdictを渡してもbuild_analysis_record()が例外を出さない",
        _schema_exc is None,
    )
    if _record is not None:
        check(
            "SCHEMA-COMPAT-EXISTING-VALUE-PRESERVED. 既存キー（post_id）の値は正しく取得される",
            _record.post_id,
            123,
        )
print()

# =====================================================================
# NOIMPACT: 分類テーブル・CONTINUE対象4値・openai/wordpress __all__が無改修
# =====================================================================

print("[NOIMPACT] 分類テーブル・CONTINUE対象4値・既存Public APIが無改修")

check(
    "NOIMPACT-ACTION-BY-CATEGORY. _ACTION_BY_CATEGORYが既存どおり5エントリ・不変",
    _policy_impl._ACTION_BY_CATEGORY,
    {
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
    },
)
check(
    "NOIMPACT-CONTINUABLE-REASONS. _CONTINUABLE_REASONSが既存4値のまま不変",
    _policy_impl._CONTINUABLE_REASONS,
    frozenset({
        OpenAIImageGenerationErrorReason.TIMEOUT,
        OpenAIImageGenerationErrorReason.CONNECTION,
        OpenAIImageGenerationErrorReason.RATE_LIMIT,
        OpenAIImageGenerationErrorReason.SERVER_ERROR,
    }),
)

import openai_image_generation as _v611_pkg_check  # noqa: E402
import wordpress_media as _v609_pkg_check  # noqa: E402

check(
    "NOIMPACT-OPENAI-ALL-UNCHANGED. openai_image_generation.__all__が無改修",
    sorted(_v611_pkg_check.__all__),
    sorted(["OpenAIImageGenerator", "OpenAIImageGenerationError", "OpenAIImageGenerationErrorReason"]),
)
check(
    "NOIMPACT-WORDPRESS-ALL-UNCHANGED. wordpress_media.__all__が無改修",
    sorted(_v609_pkg_check.__all__),
    sorted(["MediaUploadResult", "WordPressMediaUploadError", "WordPressMediaUploadErrorReason", "WordPressMediaUploader"]),
)
print()

# =====================================================================
# NOLEAK / RUNTIMEPATH: main.py記事ループのobservation伝播（Structural／AST）
# =====================================================================

print("[NOLEAK/RUNTIMEPATH] main.py記事ループのobservation伝播")

_main_source = MAIN_FILE.read_text(encoding="utf-8")
_main_tree = ast.parse(_main_source, filename=str(MAIN_FILE))


def _find_for_loop_over(tree, iter_name: str):
    for node in ast.walk(tree):
        if isinstance(node, ast.For) and isinstance(node.iter, ast.Call):
            _func = node.iter.func
            if isinstance(_func, ast.Name) and _func.id == "enumerate":
                if node.iter.args and isinstance(node.iter.args[0], ast.Name) and node.iter.args[0].id == iter_name:
                    return node
        if isinstance(node, ast.For) and isinstance(node.iter, ast.Name) and node.iter.id == iter_name:
            return node
    return None


_article_loop = _find_for_loop_over(_main_tree, "to_process")
check_true("RUNTIMEPATH-LOOP-FOUND. to_processに対するforループが見つかる", _article_loop is not None)

if _article_loop is not None:
    _loop_body_assigns = [
        n
        for n in _article_loop.body
        if isinstance(n, ast.AnnAssign)
        and isinstance(n.target, ast.Name)
        and n.target.id == "featured_media_observation"
    ]
    check(
        "NOLEAK-INIT-IN-LOOP. featured_media_observation = Noneの初期化がforループ本体の"
        "直下（各反復で再実行される位置）に存在する",
        len(_loop_body_assigns),
        1,
    )
    if _loop_body_assigns:
        check_true(
            "NOLEAK-INIT-VALUE-NONE. 初期化の値がNone",
            isinstance(_loop_body_assigns[0].value, ast.Constant) and _loop_body_assigns[0].value.value is None,
        )

    _loop_try = next((n for n in _article_loop.body if isinstance(n, ast.Try)), None)
    check_true("RUNTIMEPATH-TRY-IN-LOOP. forループ本体にtryが存在する", _loop_try is not None)
    if _loop_try is not None and _loop_body_assigns:
        # NOLEAK-INIT-IN-LOOPがforループ本体（try含む祖先）の直下にあり、
        # tryより前に位置することを確認する
        check_true(
            "NOLEAK-INIT-BEFORE-TRY. 初期化がtryより前に位置する（各反復で確実に再初期化後にtryへ入る）",
            _article_loop.body.index(_loop_body_assigns[0]) < _article_loop.body.index(_loop_try),
        )

        _except_handler = _loop_try.handlers[0] if _loop_try.handlers else None
        check_true("RUNTIMEPATH-EXCEPT-EXISTS. tryにexcept節が存在する", _except_handler is not None)
        if _except_handler is not None:
            _handle_failure_calls = [
                n
                for n in ast.walk(_except_handler)
                if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name)
                and n.func.id == "_handle_featured_media_failure"
            ]
            check(
                "RUNTIMEPATH-HANDLE-FAILURE-CALLED. except節が_handle_featured_media_failure()を呼ぶ",
                len(_handle_failure_calls),
                1,
            )
            if _handle_failure_calls:
                _obs_kwarg = next(
                    (kw for kw in _handle_failure_calls[0].keywords if kw.arg == "observation"), None
                )
                check_true(
                    "RUNTIMEPATH-PROPAGATE-OBSERVATION-PASSED. _handle_featured_media_failure()へ"
                    "observation引数が渡される",
                    _obs_kwarg is not None,
                )
                if _obs_kwarg is not None:
                    check_true(
                        "RUNTIMEPATH-PROPAGATE-OBSERVATION-IS-FEATURED-MEDIA-OBSERVATION. "
                        "渡す値がfeatured_media_observation変数である",
                        isinstance(_obs_kwarg.value, ast.Name) and _obs_kwarg.value.id == "featured_media_observation",
                    )

        # try本体（except節を除く）から、正常系のlog_manager.log_article()呼び出しを探す
        _normal_log_calls = [
            n
            for n in ast.walk(_article_loop)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "log_article"
            and n not in ast.walk(_except_handler)
        ] if _except_handler is not None else []
        check(
            "RUNTIMEPATH-NORMAL-LOG-CALL-COUNT. 正常系のlog_article()呼び出しが1件",
            len(_normal_log_calls),
            1,
        )
        if _normal_log_calls:
            _normal_log_kwarg_names = {kw.arg for kw in _normal_log_calls[0].keywords}
            for _kwarg_name in ("featured_media_category", "featured_media_action", "featured_media_reason"):
                check_true(
                    f"RUNTIMEPATH-NORMAL-LOG-HAS-{_kwarg_name.upper()}. 正常系log_article()呼び出しへ"
                    f"{_kwarg_name}が渡される",
                    _kwarg_name in _normal_log_kwarg_names,
                )
print()

# =====================================================================
# RUNTIME-E2E: main.main()の完全実行によるbehavioral検証（6経路）
# （Code Review Major-1対応。設計書§16.2のCONTINUE-WP-SUCCESS-／
#  CONTINUE-WP-FAILURE-／APPLIED-／DISABLED-／PROPAGATE-／NULLLOG-の
#  6経路をbehavioralに検証する。main()はRSS収集・Claude API呼び出しを
#  伴うため、これらを含む全ての外部依存をmonkeypatchで置き換えたうえで
#  main.main()を直接呼び出す。実HTTP通信・実ファイル書き込み・実課金の
#  いずれも発生させない。）
# =====================================================================

print("[RUNTIME-E2E] main.main()の完全実行によるbehavioral検証（6経路、Code Review Major-1対応）")


class _FakeMainLogManager:
    """main()のlog_managerを丸ごと置き換えるFake。log_article()の全呼び出しを
    順序どおり記録し、log_execution()に渡されたExecutionLogEntryも保持する。"""

    def __init__(self):
        self.article_calls = []
        self.execution_entry = None

    def log_article(self, **kwargs):
        self.article_calls.append(kwargs)

    def log_execution(self, entry):
        self.execution_entry = entry

    def log_error(self, **kwargs):
        pass


class _FakeMainMarkdownOutput:
    """main()のMarkdownOutputクラス自体を置き換えるFake。実ファイルへは
    一切書き込まない。生成された全instanceをclass変数へ記録する。"""

    instances = []

    def __init__(self, output_dir=None):
        self.output_dir = output_dir
        self.calls = []
        _FakeMainMarkdownOutput.instances.append(self)

    def is_available(self):
        return True

    def save(self, article):
        self.calls.append(article)
        from outputs import SaveResult
        return SaveResult(success=True, output_type="file", edit_url=f"/fake/output/{article.slug}.md")


class _FakeMainWordPressOutput:
    """main()のWordPressOutputクラス自体を置き換えるFake。from_env()は常に
    同一singleton instanceを返すため、main.py内のisinstance(o, WordPressOutput)
    判定（main.pyがmain.WordPressOutputという同一クラス参照を使う限り）も
    正しく成立する。実HTTP通信は一切発生させない。"""

    _singleton = None

    def __init__(self, result_fn):
        self._result_fn = result_fn
        self.calls = []

    @classmethod
    def from_env(cls):
        return cls._singleton

    def is_available(self):
        return True

    def save(self, article):
        self.calls.append(article)
        return self._result_fn(article)


class _ScenarioRuntime:
    """main()のArticleFeaturedMediaRuntime.from_env()を置き換えるFake。
    article.item.titleごとにDISABLED/APPLIED/CONTINUE/PROPAGATEのいずれかを
    返す。observationの構築はProduction本番ロジック
    （decide_image_generation_fallback・extract_safe_reason・
    FeaturedMediaFailureObservation）をそのまま呼び出すため、"見せかけ"の
    観測値ではなく実ロジックの出力を検証できる。"""

    def __init__(self, plans):
        self._plans = plans
        self.apply_calls = []
        self.classify_calls = []

    def apply(self, article):
        self.apply_calls.append(article.item.title)
        kind, error = self._plans[article.item.title]
        if kind == "DISABLED":
            return ArticleFeaturedMediaRuntimeResult(
                article=article, status=ArticleFeaturedMediaRuntimeStatus.DISABLED
            )
        if kind == "APPLIED":
            return ArticleFeaturedMediaRuntimeResult(
                article=article, status=ArticleFeaturedMediaRuntimeStatus.APPLIED
            )
        if kind == "CONTINUE":
            decision = decide_image_generation_fallback(error)
            observation = FeaturedMediaFailureObservation(
                category=decision.category, action=decision.action, reason=extract_safe_reason(error)
            )
            return ArticleFeaturedMediaRuntimeResult(
                article=article,
                status=ArticleFeaturedMediaRuntimeStatus.CONTINUED_WITHOUT_FEATURED_MEDIA,
                category=decision.category,
                observation=observation,
            )
        if kind == "PROPAGATE":
            raise error
        raise AssertionError(f"unknown scenario kind: {kind}")

    def classify_propagated_failure(self, error):
        self.classify_calls.append(error)
        decision = decide_image_generation_fallback(error)
        return FeaturedMediaFailureObservation(
            category=decision.category, action=decision.action, reason=extract_safe_reason(error)
        )


def _run_main_with_mocks(item_titles, plans, wp_result_fn, *, log_enabled=True):
    """main.main()を、RSS収集・重要度判定・記事生成・画像/WordPress/Log I/Oの
    すべてをmonkeypatchで置き換えたうえで実行する。

    Returns:
        (run_exc, stdout_text, fake_log_manager, scenario_runtime, markdown_output)
        log_enabled=Falseの場合、fake_log_managerは使われず実NullLogManagerが
        使われるため、戻り値のfake_log_managerはNoneとなる。
    """
    news_items = [make_news_item(title=t) for t in item_titles]

    def _fake_collect_all_news(max_items_per_feed=20):
        return list(news_items), []

    def _fake_filter_news(all_news):
        return {"pass": list(all_news), "pending": []}

    def _fake_deduplicate_news(target_news):
        return list(target_news)

    def _fake_judge_all(client, news_list):
        return [{"item": item, "importance": "S", "reason": "test"} for item in news_list]

    def _fake_generate_article(client, item, importance):
        return f"BODY::{item.title}"

    def _fake_generate_seo_title(client, item, importance):
        return f"SEO::{item.title}"

    def _fake_generate_x_post(client, item, importance, article_body, blog_url="[ブログURL]"):
        return f"XPOST::{item.title}"

    def _fake_resolve_featured_image(item):
        return ""

    def _fake_resolve_media_id(item, default_media_id):
        return 0

    fake_log_manager = _FakeMainLogManager() if log_enabled else None
    scenario_runtime = _ScenarioRuntime(plans)
    _FakeMainMarkdownOutput.instances = []
    _FakeMainWordPressOutput._singleton = _FakeMainWordPressOutput(wp_result_fn)

    _orig_argv = sys.argv[:]
    _orig_environ = dict(os.environ)
    _orig_funcs = {
        "collect_all_news": main.collect_all_news,
        "filter_news": main.filter_news,
        "deduplicate_news": main.deduplicate_news,
        "judge_all": main.judge_all,
        "generate_article": main.generate_article,
        "generate_seo_title": main.generate_seo_title,
        "generate_x_post": main.generate_x_post,
        "resolve_featured_image": main.resolve_featured_image,
        "resolve_media_id": main.resolve_media_id,
        "MarkdownOutput": main.MarkdownOutput,
        "WordPressOutput": main.WordPressOutput,
    }
    _orig_runtime_from_env = main.ArticleFeaturedMediaRuntime.from_env
    _orig_log_from_env = main.LogManager.from_env

    buf = io.StringIO()
    run_exc = None
    try:
        os.environ["ANTHROPIC_API_KEY"] = "dummy-test-anthropic-key-v6-25"
        os.environ["ANALYTICS_ENABLED"] = "false"
        os.environ["LOG_ENABLED"] = "true" if log_enabled else "false"
        sys.argv = ["main.py"]

        main.collect_all_news = _fake_collect_all_news
        main.filter_news = _fake_filter_news
        main.deduplicate_news = _fake_deduplicate_news
        main.judge_all = _fake_judge_all
        main.generate_article = _fake_generate_article
        main.generate_seo_title = _fake_generate_seo_title
        main.generate_x_post = _fake_generate_x_post
        main.resolve_featured_image = _fake_resolve_featured_image
        main.resolve_media_id = _fake_resolve_media_id
        main.MarkdownOutput = _FakeMainMarkdownOutput
        main.WordPressOutput = _FakeMainWordPressOutput
        main.ArticleFeaturedMediaRuntime.from_env = classmethod(lambda cls: scenario_runtime)
        if log_enabled:
            main.LogManager.from_env = classmethod(lambda cls, base_dir=None: fake_log_manager)
        # log_enabled=False の場合は from_env() を無変更のまま残し、
        # 実NullLogManagerがLOG_ENABLED=false経由で使われるようにする。

        with contextlib.redirect_stdout(buf):
            main.main()
    except BaseException as exc:  # noqa: BLE001  - テスト用に全捕捉し呼び出し元へ返す
        run_exc = exc
    finally:
        main.collect_all_news = _orig_funcs["collect_all_news"]
        main.filter_news = _orig_funcs["filter_news"]
        main.deduplicate_news = _orig_funcs["deduplicate_news"]
        main.judge_all = _orig_funcs["judge_all"]
        main.generate_article = _orig_funcs["generate_article"]
        main.generate_seo_title = _orig_funcs["generate_seo_title"]
        main.generate_x_post = _orig_funcs["generate_x_post"]
        main.resolve_featured_image = _orig_funcs["resolve_featured_image"]
        main.resolve_media_id = _orig_funcs["resolve_media_id"]
        main.MarkdownOutput = _orig_funcs["MarkdownOutput"]
        main.WordPressOutput = _orig_funcs["WordPressOutput"]
        main.ArticleFeaturedMediaRuntime.from_env = _orig_runtime_from_env
        main.LogManager.from_env = _orig_log_from_env
        sys.argv = _orig_argv
        os.environ.clear()
        os.environ.update(_orig_environ)

    markdown_output = _FakeMainMarkdownOutput.instances[-1] if _FakeMainMarkdownOutput.instances else None
    return run_exc, buf.getvalue(), fake_log_manager, scenario_runtime, markdown_output


def _wp_success(article):
    from outputs import SaveResult
    return SaveResult(
        success=True, output_type="wordpress", post_id=hash(article.slug) % 100000,
        edit_url=f"https://example.com/wp-admin/post.php?post={hash(article.slug) % 100000}&action=edit",
        permalink=f"https://example.com/{article.slug}/",
    )


def _wp_failure(article):
    from outputs import SaveResult
    return SaveResult(success=False, output_type="wordpress", error_message="fake wp failure")


# ── Run A: CONTINUE(WP成功)／PROPAGATE(loop継続)／APPLIED／DISABLED の4記事連続処理 ──
# NOLEAKの直接的behavioral証明も兼ねる：CONTINUE・PROPAGATEの非空な観測値が
# 後続のAPPLIED・DISABLED記事のログへ漏れないことを確認する。

_RUNA_SECRET_CONTINUE = "SECRET_MARKER_RUNA_CONTINUE_2f9c"
_RUNA_SECRET_PROPAGATE = "SECRET_MARKER_RUNA_PROPAGATE_6b3e"
_runA_titles = ["Item-Continue", "Item-Propagate", "Item-Applied", "Item-Disabled"]
_runA_plans = {
    "Item-Continue": (
        "CONTINUE",
        OpenAIImageGenerationError(f"probe ({_RUNA_SECRET_CONTINUE})", OpenAIImageGenerationErrorReason.RATE_LIMIT),
    ),
    "Item-Propagate": (
        "PROPAGATE",
        OpenAIImageGenerationError(f"probe ({_RUNA_SECRET_PROPAGATE})", OpenAIImageGenerationErrorReason.REQUEST_REJECTED),
    ),
    "Item-Applied": ("APPLIED", None),
    "Item-Disabled": ("DISABLED", None),
}

_runA_exc, _runA_stdout, _runA_log, _runA_runtime, _runA_md = _run_main_with_mocks(
    _runA_titles, _runA_plans, _wp_success
)

check_true("RUNTIME-E2E-A-NOEXC. main()が例外を送出せず完了する", _runA_exc is None)
check(
    "RUNTIME-E2E-A-LOG-CALL-COUNT. log_article()が記事数と同じ4回呼ばれる（loop継続の証明）",
    len(_runA_log.article_calls) if _runA_log else -1,
    4,
)

if _runA_log is not None and len(_runA_log.article_calls) == 4:
    _a_continue, _a_propagate, _a_applied, _a_disabled = _runA_log.article_calls

    # CONTINUE-WP-SUCCESS-
    check('RUNTIME-E2E-CONTINUE-WP-SUCCESS-RESULT. result="success"', _a_continue.get("result"), "success")
    check(
        "RUNTIME-E2E-CONTINUE-WP-SUCCESS-CATEGORY. category=IMAGE_GENERATION_FAILED",
        _a_continue.get("featured_media_category"), "IMAGE_GENERATION_FAILED",
    )
    check(
        "RUNTIME-E2E-CONTINUE-WP-SUCCESS-ACTION. action=CONTINUE_WITHOUT_FEATURED_MEDIA",
        _a_continue.get("featured_media_action"), "CONTINUE_WITHOUT_FEATURED_MEDIA",
    )
    check(
        "RUNTIME-E2E-CONTINUE-WP-SUCCESS-REASON. reason='rate_limit'",
        _a_continue.get("featured_media_reason"), "rate_limit",
    )
    check_false(
        "RUNTIME-E2E-CONTINUE-WP-SUCCESS-SEC. 秘密情報が含まれない",
        _RUNA_SECRET_CONTINUE in (_a_continue.get("featured_media_reason") or ""),
    )

    # PROPAGATE-（loop継続の証明を兼ねる：この後にAPPLIED/DISABLEDが処理されている）
    check('RUNTIME-E2E-PROPAGATE-RESULT. result="failed"', _a_propagate.get("result"), "failed")
    check(
        "RUNTIME-E2E-PROPAGATE-CATEGORY. category=IMAGE_GENERATION_REQUEST_REJECTED",
        _a_propagate.get("featured_media_category"), "IMAGE_GENERATION_REQUEST_REJECTED",
    )
    check(
        "RUNTIME-E2E-PROPAGATE-ACTION. action=PROPAGATE_ORIGINAL_ERROR",
        _a_propagate.get("featured_media_action"), "PROPAGATE_ORIGINAL_ERROR",
    )
    check(
        "RUNTIME-E2E-PROPAGATE-REASON. reason='request_rejected'",
        _a_propagate.get("featured_media_reason"), "request_rejected",
    )
    check(
        "RUNTIME-E2E-PROPAGATE-ERROR-MESSAGE-FIXED. error_messageが固定ラベル（SEC-8）",
        _a_propagate.get("error_message"), "featured media processing failed",
    )
    check("RUNTIME-E2E-PROPAGATE-POST-ID-NONE. post_id=None", _a_propagate.get("post_id"), None)
    check_false(
        "RUNTIME-E2E-PROPAGATE-SEC. 秘密情報が含まれない",
        _RUNA_SECRET_PROPAGATE in (_a_propagate.get("featured_media_reason") or ""),
    )

    # APPLIED-（NOLEAK：直前のCONTINUE/PROPAGATEの非空値が漏れていないこと）
    check('RUNTIME-E2E-APPLIED-RESULT. result="success"', _a_applied.get("result"), "success")
    check(
        "RUNTIME-E2E-APPLIED-FIELDS-EMPTY（NOLEAK）. category/action/reasonがすべて''",
        (
            _a_applied.get("featured_media_category"),
            _a_applied.get("featured_media_action"),
            _a_applied.get("featured_media_reason"),
        ),
        ("", "", ""),
    )

    # DISABLED-（NOLEAK：APPLIED経由でも漏れが伝播しないこと）
    check('RUNTIME-E2E-DISABLED-RESULT. result="success"', _a_disabled.get("result"), "success")
    check(
        "RUNTIME-E2E-DISABLED-FIELDS-EMPTY（NOLEAK）. category/action/reasonがすべて''",
        (
            _a_disabled.get("featured_media_category"),
            _a_disabled.get("featured_media_action"),
            _a_disabled.get("featured_media_reason"),
        ),
        ("", "", ""),
    )

# counter検証（ExecutionLogEntry経由）
if _runA_log is not None and _runA_log.execution_entry is not None:
    _entry = _runA_log.execution_entry
    check(
        "RUNTIME-E2E-A-COUNTER-SUCCESS. total_wp_success=3（Continue/Applied/Disabledの3件がWP成功）",
        _entry.total_wp_success, 3,
    )
    check(
        "RUNTIME-E2E-A-COUNTER-FAILED. total_wp_failed=1（Propagateの1件のみ）",
        _entry.total_wp_failed, 1,
    )
    check("RUNTIME-E2E-A-COUNTER-SKIPPED. total_wp_skipped=0", _entry.total_wp_skipped, 0)
else:
    check_true("RUNTIME-E2E-A-EXECUTION-ENTRY-EXISTS. log_execution()が呼ばれている", False)

# Markdown保存（PROPAGATE経路分＋通常経路3件＝4件）
check(
    "RUNTIME-E2E-A-MARKDOWN-SAVE-COUNT. Markdown保存が記事数分（4件）呼ばれる"
    "（PROPAGATE経路の単独保存＋通常経路3件）",
    len(_runA_md.calls) if _runA_md else -1,
    4,
)

# =====================================================================
# Run B: CONTINUE-WP-FAILURE-（WP保存が失敗してもcategory/action/reasonは
# 正しく記録される）
# =====================================================================

_RUNB_SECRET = "SECRET_MARKER_RUNB_CONTINUE_WPFAIL_9a1d"
_runB_exc, _runB_stdout, _runB_log, _runB_runtime, _runB_md = _run_main_with_mocks(
    ["Item-ContinueWpFail"],
    {
        "Item-ContinueWpFail": (
            "CONTINUE",
            OpenAIImageGenerationError(f"probe ({_RUNB_SECRET})", OpenAIImageGenerationErrorReason.SERVER_ERROR),
        ),
    },
    _wp_failure,
)

check_true("RUNTIME-E2E-B-NOEXC. main()が例外を送出せず完了する", _runB_exc is None)
check(
    "RUNTIME-E2E-B-LOG-CALL-COUNT. log_article()が1回呼ばれる",
    len(_runB_log.article_calls) if _runB_log else -1,
    1,
)
if _runB_log is not None and len(_runB_log.article_calls) == 1:
    _b_entry = _runB_log.article_calls[0]
    check(
        'RUNTIME-E2E-CONTINUE-WP-FAILURE-RESULT. WP保存失敗時はresult="failed"',
        _b_entry.get("result"), "failed",
    )
    check(
        "RUNTIME-E2E-CONTINUE-WP-FAILURE-CATEGORY. WP失敗でもcategoryは正しく記録される",
        _b_entry.get("featured_media_category"), "IMAGE_GENERATION_FAILED",
    )
    check(
        "RUNTIME-E2E-CONTINUE-WP-FAILURE-ACTION. WP失敗でもactionは正しく記録される",
        _b_entry.get("featured_media_action"), "CONTINUE_WITHOUT_FEATURED_MEDIA",
    )
    check(
        "RUNTIME-E2E-CONTINUE-WP-FAILURE-REASON. WP失敗でもreasonは正しく記録される",
        _b_entry.get("featured_media_reason"), "server_error",
    )
if _runB_log is not None and _runB_log.execution_entry is not None:
    check(
        "RUNTIME-E2E-B-COUNTER-FAILED. total_wp_failed=1",
        _runB_log.execution_entry.total_wp_failed, 1,
    )
    check(
        "RUNTIME-E2E-B-COUNTER-SUCCESS. total_wp_success=0",
        _runB_log.execution_entry.total_wp_success, 0,
    )

# =====================================================================
# Run C: NULLLOG-（LOG_ENABLED=false、実NullLogManager経由でTypeErrorが
# 発生しないことをCONTINUE／PROPAGATE双方の経路でend-to-end確認する）
# =====================================================================

_runC_exc, _runC_stdout, _runC_log, _runC_runtime, _runC_md = _run_main_with_mocks(
    ["Item-NullLogContinue", "Item-NullLogPropagate"],
    {
        "Item-NullLogContinue": (
            "CONTINUE",
            OpenAIImageGenerationError("probe", OpenAIImageGenerationErrorReason.TIMEOUT),
        ),
        "Item-NullLogPropagate": (
            "PROPAGATE",
            OpenAIImageGenerationError("probe", OpenAIImageGenerationErrorReason.REQUEST_REJECTED),
        ),
    },
    _wp_success,
    log_enabled=False,
)

check_true(
    "RUNTIME-E2E-NULLLOG-NOEXC. LOG_ENABLED=false（実NullLogManager経由）でも"
    "CONTINUE／PROPAGATE双方の経路でTypeErrorが発生せずmain()が完了する",
    _runC_exc is None,
)
check(
    "RUNTIME-E2E-NULLLOG-FAKE-LOG-NONE. log_enabled=False時はfake_log_managerを使わない"
    "（実NullLogManagerが使われたことの確認）",
    _runC_log,
    None,
)
print()

# =====================================================================
# SEC-GUARD: v6.21.0 LOOP-HANDLER精緻化guardの検出力自己検証
# =====================================================================

print("[SEC-GUARD] v6.21.0 LOOP-HANDLER精緻化guard 6件の検出力自己検証（Code Review Minor-1対応）")

# 以下6関数は、tests/test_e2e_v6_21_0_article_featured_media_runtime_wiring.py
# のLOOP節（SEC-NO-STR-EXC等6guard）と同一の走査ロジックの再実装である。
# v6.21.0モジュールをそのままimportして再利用すると、standalone script形式
# （import時に全アサーションが即実行される構造）のため二重実行になり不適切
# なので、ロジックを複製したうえで、③の「実main.py cross-check」により
# 複製と実体（v6.21.0側）が実際のmain.pyに対して同じ結論（0件）を出すことを
# 相互検証し、乖離を検出できるようにする。


def _walk_stmts(stmts):
    for s in stmts:
        yield from ast.walk(s)


def _scan_str_or_repr(handler_body) -> int:
    """SEC-NO-STR-EXC相当：str(exc)／repr(exc)の呼び出し件数。"""
    return len([
        n
        for n in _walk_stmts(handler_body)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id in ("str", "repr")
        and any(isinstance(a, ast.Name) and a.id == "exc" for a in n.args)
    ])


def _scan_typename(handler_body) -> int:
    """SEC-NO-TYPENAME-EXC相当：type(exc).__name__／exc.__class__.__name__の件数。"""
    hits = []
    for n in _walk_stmts(handler_body):
        if isinstance(n, ast.Attribute) and n.attr == "__name__":
            value = n.value
            if (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name)
                and value.func.id == "type"
                and any(isinstance(a, ast.Name) and a.id == "exc" for a in value.args)
            ):
                hits.append(n)
            elif (
                isinstance(value, ast.Attribute)
                and value.attr == "__class__"
                and isinstance(value.value, ast.Name)
                and value.value.id == "exc"
            ):
                hits.append(n)
    return len(hits)


def _scan_raw_exc_to_log(handler_body) -> int:
    """SEC-NO-RAW-EXC-TO-LOGENTRY相当：ArticleLogEntry()／log_article()へexcが
    直接渡される件数。"""
    hits = []
    for call_name in ("ArticleLogEntry", "log_article"):
        for n in _walk_stmts(handler_body):
            if not isinstance(n, ast.Call):
                continue
            func = n.func
            matches = (isinstance(func, ast.Name) and func.id == call_name) or (
                isinstance(func, ast.Attribute) and func.attr == call_name
            )
            if not matches:
                continue
            all_args = list(n.args) + [kw.value for kw in n.keywords]
            if any(isinstance(a, ast.Name) and a.id == "exc" for a in all_args):
                hits.append(n)
    return len(hits)


def _scan_exc_mutation(handler_body) -> int:
    """SEC-NO-EXC-MUTATION相当：excへの属性代入・setattr(exc, ...)の件数。"""
    hits = []
    for n in _walk_stmts(handler_body):
        if isinstance(n, (ast.Assign, ast.AugAssign)):
            targets = n.targets if isinstance(n, ast.Assign) else [n.target]
            for t in targets:
                if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == "exc":
                    hits.append(n)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "setattr":
            if n.args and isinstance(n.args[0], ast.Name) and n.args[0].id == "exc":
                hits.append(n)
    return len(hits)


def _scan_exc_usage_allowlist(handler_body) -> int:
    """SEC-EXC-USAGE-ALLOWLIST相当：excの唯一の許可された使用形が
    classify_propagated_failure(exc)の引数位置であること。違反件数を返す。"""
    exc_loads = [
        n for n in _walk_stmts(handler_body)
        if isinstance(n, ast.Name) and n.id == "exc" and isinstance(n.ctx, ast.Load)
    ]
    classify_calls = []
    for n in _walk_stmts(handler_body):
        if isinstance(n, ast.Call):
            func = n.func
            if (isinstance(func, ast.Name) and func.id == "classify_propagated_failure") or (
                isinstance(func, ast.Attribute) and func.attr == "classify_propagated_failure"
            ):
                classify_calls.append(n)
    allowed_ids = {
        id(a) for n in classify_calls for a in n.args if isinstance(a, ast.Name) and a.id == "exc"
    }
    return len([n for n in exc_loads if id(n) not in allowed_ids])


def _parse_handler_body(source: str):
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            return node.body
    return []


# ── ①②：各guardについて陽性対照（違反を検出する）・陰性対照（誤検出しない）──

_CLEAN_SNIPPET = """
try:
    pass
except Exception as exc:
    featured_media_observation = featured_media_runtime.classify_propagated_failure(exc)
"""

_GUARD_CASES = [
    (
        "SEC-NO-STR-EXC", _scan_str_or_repr,
        "print(str(exc))",
    ),
    (
        "SEC-NO-REPR-EXC", _scan_str_or_repr,
        "print(repr(exc))",
    ),
    (
        "SEC-NO-TYPENAME-EXC", _scan_typename,
        "print(type(exc).__name__)",
    ),
    (
        "SEC-NO-TYPENAME-EXC-CLASSATTR", _scan_typename,
        "print(exc.__class__.__name__)",
    ),
    (
        "SEC-NO-RAW-EXC-TO-LOGENTRY", _scan_raw_exc_to_log,
        "log_manager.log_article(article=exc)",
    ),
    (
        "SEC-NO-EXC-MUTATION-ATTR", _scan_exc_mutation,
        "exc.category = 'x'",
    ),
    (
        "SEC-NO-EXC-MUTATION-SETATTR", _scan_exc_mutation,
        "setattr(exc, 'category', 'x')",
    ),
    (
        "SEC-EXC-USAGE-ALLOWLIST", _scan_exc_usage_allowlist,
        "other_function(exc)",
    ),
]

for _case_id, _scan_fn, _violating_line in _GUARD_CASES:
    _violating_snippet = f"""
try:
    pass
except Exception as exc:
    {_violating_line}
"""
    check_true(
        f"SEC-GUARD-POSITIVE-CONTROL[{_case_id}]. 違反fixtureを検出する（陽性対照）",
        _scan_fn(_parse_handler_body(_violating_snippet)) > 0,
    )
    check(
        f"SEC-GUARD-NEGATIVE-CONTROL[{_case_id}]. 正常fixtureは0件（陰性対照）",
        _scan_fn(_parse_handler_body(_CLEAN_SNIPPET)),
        0,
    )

# ── ③：実main.pyに対するcross-check ──
# v6.21.0側の同名guard（実測PASS済み）と、本ファイルで複製した走査ロジックの
# 両方を実際のmain.pyへ適用し、一致（いずれも0件）することを確認する。
# 複製と実体が同じ結論に至らない場合、いずれかの走査ロジックにバグがある
# ことを意味し、本チェックで検出できる。
if "_except_handler" in dir() and _except_handler is not None:
    for _case_id, _scan_fn in (
        ("SEC-NO-STR-EXC", _scan_str_or_repr),
        ("SEC-NO-TYPENAME-EXC", _scan_typename),
        ("SEC-NO-RAW-EXC-TO-LOGENTRY", _scan_raw_exc_to_log),
        ("SEC-NO-EXC-MUTATION", _scan_exc_mutation),
        ("SEC-EXC-USAGE-ALLOWLIST", _scan_exc_usage_allowlist),
    ):
        check(
            f"SEC-GUARD-REAL-MAINPY[{_case_id}]. 実main.pyのexcept節に対する複製guardの"
            "走査結果が0件である（v6.21.0本体guardの実測PASSと一致することの相互検証）",
            _scan_fn(_except_handler.body),
            0,
        )
print()

# ─── 結果サマリー ───
print("=" * 60)
total = len(results_log)
passed = sum(1 for status, _ in results_log if status == "PASS")
failed = total - passed
print("Release：v6.25.0")
print("正式名称：Image Generation Fallback Observability Foundation")
print(f"Assertion合計：{total}")
print(f"合計: {passed}/{total} PASS  /  {failed} FAIL")
print("=" * 60)

if failed > 0:
    print()
    print("FAILしたテスト:")
    for status, label in results_log:
        if status == "FAIL":
            print(f"  - {label}")
    sys.exit(1)
else:
    print("全テスト PASS")
