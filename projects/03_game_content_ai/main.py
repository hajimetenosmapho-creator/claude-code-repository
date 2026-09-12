"""
03_game_content_ai — ゲームニュース記事生成ツール

使い方:
    python main.py                    # 通常動作（S全件 + A最大5件）
    python main.py --max-articles 3   # テスト用：先頭3件のみ生成

動作の流れ:
    1. 各ゲームサイトのRSSからニュースを収集
    2. キーワードフィルターで不要記事を除外（API節約）
    3. Claude AIで重要度(S/A/B)を判定
    4. 記事化ルールに従って対象を絞り込み
       - S評価: 全件記事化
       - A評価: 最大5件まで記事化（超過分は候補ファイルへ）
       - B評価: 記事化しない（候補ファイルへ保存）
    5. 記事下書き・SEOタイトル・X投稿文を生成
    6. output/ フォルダにMarkdownファイルとして保存
"""

import argparse
import os
import re
import sys
import time
import anthropic

# Windowsコンソールの文字コード問題を防ぐ
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv

# プロジェクトルートの src/ をインポートパスに追加
sys.path.insert(0, str(Path(__file__).parent / "src"))

from collector import collect_all_news, NewsItem, FeedStats, FEED_GROUPS
from keyword_filter import filter_news
from duplicate_filter import deduplicate_news
from importance_judge import judge_all
from article_generator import generate_article
from seo_title_generator import generate_seo_title
from x_post_generator import generate_x_post
from image_resolver import resolve_featured_image, resolve_media_id
from slug_generator import generate_slug
from publishing_config import PublishingConfig
from sns_config import SnsConfig, SnsPostStatus
from outputs import OutputManager, MarkdownOutput, WordPressOutput, ArticleData, SaveResult
from logger import LogManager, ExecutionLogEntry
from analytics import AnalyticsManager
from article_featured_media_runtime import (
    ArticleFeaturedMediaRuntime,
    ArticleFeaturedMediaRuntimeResult,
    ArticleFeaturedMediaRuntimeStatus,
    FeaturedMediaFailureObservation,
)
from side_effect_safety import (
    SIDE_EFFECT_CONTRACT_VIOLATION_EXIT_CODE,
    LegacyDirectExecutionContext,
    ProtectedSideEffectKind,
    RetryLineageProtectedExecutionContext,
    SideEffectExecutionModeContractError,
    SideEffectOperationIdentity,
    SideEffectSite,
    build_media_upload_safety_coordinator,
)
from side_effect_safety.side_effect_execution_mode import (
    ExecutionModeFailureReasonCode,
    _parse_execution_context_from_env,
)
from side_effect_safety.media_upload_applicability_store import JsonMediaUploadApplicabilityStore
from side_effect_safety.media_upload_attempt_context_store import JsonMediaUploadAttemptContextStore
from side_effect_safety.media_upload_write_ahead_wiring import (
    FeaturedMediaPropagatedFailure,
    LegacyFeaturedMediaSideEffectBinding,
    MediaUploadWriteAheadAdapters,
    ProtectedFeaturedMediaSideEffectBinding,
    build_legacy_featured_media_side_effect_binding,
    build_protected_featured_media_runtime,
    build_protected_featured_media_side_effect_binding,
)
from article_media_upload_state import ArticleMediaUploadStateManager, JsonArticleMediaUploadStateStore
from protected_operation_manifest import (
    JsonProtectedOperationManifestStore,
    ManifestRegistrarFacade,
    build_manifest_entry,
    raise_if_not_registered,
)
from wordpress_draft_state import JsonWordPressDraftStateStore, WordPressDraftStateManager

# .env ファイルを読み込む
load_dotenv()

OUTPUT_DIR = Path(__file__).parent / "output"
# Release 6.32（9.3節）：WORDPRESS_DRAFT_CREATIONのdurable write-ahead state保存先
WORDPRESS_DRAFT_STATE_DIR = Path(__file__).parent / "state" / "wordpress_draft_state"
# Release 6.32（9.9節）：MEDIA_UPLOADのdurable write-ahead state保存先（呼び出し箇所B）
MEDIA_UPLOAD_STATE_DIR = Path(__file__).parent / "state" / "article_media_upload_state"
MEDIA_UPLOAD_APPLICABILITY_DIR = Path(__file__).parent / "state" / "media_upload_applicability"
MEDIA_UPLOAD_ATTEMPT_CONTEXT_DIR = Path(__file__).parent / "state" / "media_upload_attempt_context"
MEDIA_UPLOAD_LOCKS_DIR = Path(__file__).parent / "state" / "media_upload_locks"
# Architecture Amendment（Protected Operation Manifest）：RetryCompositionRootが
# 構築するmanifest storeと同一のディレクトリ（呼び出し箇所A/B共通）。
PROTECTED_OPERATION_MANIFEST_DIR = Path(__file__).parent / "state" / "protected_operation_manifest"

# A評価ニュースの記事化上限（超過分は候補ファイルへ保存）
A_ARTICLE_LIMIT = 5


def _print_rss_summary(
    feed_stats: list[FeedStats],
    total: int,
    filtered: int,
    deduped: int,
    generated: int,
) -> None:
    """RSS取得結果と処理パイプラインの統計をカテゴリ別に表示する。"""
    print("=" * 30)
    print("RSS取得結果")
    print("=" * 7)

    stats_by_source = {s.source: s for s in feed_stats}

    for group_name, sources in FEED_GROUPS.items():
        print(f"\n【{group_name}】")
        for source in sources:
            stat = stats_by_source.get(source)
            if stat is None:
                continue
            label = f"{source:<20}"
            if stat.status == "error":
                print(f"  {label} [取得失敗] {stat.error_message}")
            elif stat.status == "empty":
                print(f"  {label} 0件（記事なし）")
            else:
                print(f"  {label} {stat.count}件")

    print()
    print("-" * 30)
    print(f"  {'取得合計':<18} {total}件")
    print(f"  {'フィルター通過':<16} {filtered}件")
    print(f"  {'重複除去後':<17} {deduped}件")
    print(f"  {'記事生成':<18} {generated}件")
    print("=" * 20)
    print()


def _extract_excerpt(article_body: str, max_chars: int = 150) -> str:
    """
    記事本文の先頭段落からMarkdown記法を除いて抜粋テキストを生成する。
    APIを呼び出さず、ルールベースで生成する。

    Args:
        article_body: generate_article() が返した記事本文
        max_chars: 最大文字数（デフォルト150字）

    Returns:
        str: 抜粋テキスト。本文が空の場合は空文字。
    """
    # Markdown見出し・太字・斜体を除去
    text = re.sub(r'^#{1,6}\s+', '', article_body, flags=re.MULTILINE)
    text = re.sub(r'\*{1,2}(.+?)\*{1,2}', r'\1', text)

    # 段落ごとに分割し、最初の本文段落を取得
    paragraphs = [p.strip().replace('\n', ' ') for p in text.split('\n\n') if p.strip()]
    if not paragraphs:
        return ""

    first = paragraphs[0]
    if len(first) <= max_chars:
        return first

    # 句点・読点で自然に切れる位置を探す
    truncated = first[:max_chars]
    cut = truncated.rfind('。')
    if cut == -1:
        cut = truncated.rfind('、')
    if cut > max_chars // 2:
        return truncated[:cut + 1]
    return truncated


def _save_b_candidates_markdown(candidates: list[dict]) -> Path:
    """
    B評価ニュースとAスキップ分をまとめた候補一覧ファイルを output/ に保存する。

    Args:
        candidates: [{"item": NewsItem, "importance": str, "reason": str}, ...]

    Returns:
        Path: 保存したファイルのパス
    """
    OUTPUT_DIR.mkdir(exist_ok=True)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_B_candidates.md"
    output_path = OUTPUT_DIR / filename

    rows = []
    for i, entry in enumerate(candidates, 1):
        item: NewsItem = entry["item"]
        importance: str = entry["importance"]
        reason: str = entry.get("reason", "")
        rows.append(f"| {i} | {importance} | [{item.title[:40]}]({item.url}) | {item.source} | {reason[:40]} |")

    table = "\n".join(rows)

    content = f"""---
generated_at: "{now}"
total_count: {len(candidates)}
---

# ニュース候補一覧（記事化スキップ）

> B評価またはA評価の上限超過により記事化しなかったニュースの一覧です。

| # | 評価 | タイトル | ソース | 判定理由 |
|---|------|---------|--------|---------|
{table}

---
*生成日時: {now}*
"""

    output_path.write_text(content, encoding="utf-8")
    return output_path


def _extract_confirmed_media_id(applied_article: object) -> int | None:
    """1〜4のいずれかを満たさない場合はNoneを返す。呼び出し元はNoneの場合、
    record_confirmed()を呼んではならない（fail-closed、15.5.1節）。"""
    if not isinstance(applied_article, ArticleData):
        return None
    media_id = getattr(applied_article, "featured_media_id", None)
    if type(media_id) is not int:  # bool除外
        return None
    if media_id <= 0:
        return None
    return media_id


def _apply_featured_media_step(
    article: ArticleData,
    *,
    side_effect_binding: "LegacyFeaturedMediaSideEffectBinding | ProtectedFeaturedMediaSideEffectBinding",
) -> ArticleFeaturedMediaRuntimeResult:
    """
    v6.21.0: アイキャッチ画像のfeatured media適用ステップ。

    Release 6.32（15.4.1・22.3.2節）: 呼び出し箇所B。record_confirmed()の
    唯一のowner。side_effect_binding をexhaustiveにdispatchし（legacy/protected
    以外の経路は持たない）、legacy/protectedいずれの分岐でも runtime.apply(article)
    を単一のtry/exceptで包む。PROPAGATE対象の例外はここで分類済みの
    FeaturedMediaFailureObservation として FeaturedMediaPropagatedFailure へ包み、
    main.py記事ループへ運ぶ（Foundation自体のPROPAGATE分類ロジックは無変更）。

    v6.25.0（DI-5）: 戻り値を ArticleFeaturedMediaRuntimeResult そのものへ変更し、
    呼び出し元が result.article／result.observation を個別に取り出す。
    """
    media_upload_coordinator = None
    identity = None
    member_run_id = None

    if isinstance(side_effect_binding, LegacyFeaturedMediaSideEffectBinding):
        runtime = side_effect_binding.runtime
        # legacy modeでは4 safety methods（record_not_applicable/record_prepared/
        # record_attempted/record_confirmed）のいずれも呼ばない（15.4.1節）。
    elif isinstance(side_effect_binding, ProtectedFeaturedMediaSideEffectBinding):
        context = side_effect_binding.context
        media_upload_coordinator = side_effect_binding.media_upload_coordinator
        adapters = side_effect_binding.adapters
        manifest_registrar = side_effect_binding.manifest_registrar
        member_run_id = context.member_run_id
        # Codex Final Review Blocking#2対応：protected bindingでは
        # manifest_registrarの省略によるregistration bypassを許可しない
        # （legacy bindingのみ既存どおり省略を許容する）。「composition rootが
        # 必ず注入するはず」という前提のみをsafety guaranteeにせず、この
        # production関数自身がfail-closedする（Gate ON/OFFいずれも本チェックの
        # 対象、既存write-ahead・uploadのいずれへも進む前に停止する）。
        if manifest_registrar is None:
            raise SideEffectExecutionModeContractError(
                ExecutionModeFailureReasonCode.PROTECTED_MANIFEST_REGISTRAR_REQUIRED,
            )
        identity = SideEffectOperationIdentity(
            root_run_id=context.root_run_id,
            attempt_ordinal=context.attempt_ordinal,
            operation_kind=ProtectedSideEffectKind.MEDIA_UPLOAD,
            effect_site=SideEffectSite.NEWS_STEP,
            operation_instance_key=article.slug,
        )
        # Architecture Amendment（Protected Operation Manifest、§4.2・§5・
        # §15）：既存write-ahead呼び出し（record_not_applicable()/
        # record_prepared()）より先にmanifestへ自分自身のentryを登録する。
        # Gate ON/OFFいずれの場合も必ず登録する（Gate OFFであっても
        # MEDIA_UPLOAD operationの判定対象であることの記録を残すため）。
        # durable ACKを必ず確認し、未ack時は既存write-ahead・外部I/Oの
        # いずれへも進まずfail-closedする。
        raise_if_not_registered(
            manifest_registrar.register(
                context.root_run_id, context.attempt_ordinal, context.member_run_id,
                build_manifest_entry(
                    ProtectedSideEffectKind.MEDIA_UPLOAD, SideEffectSite.NEWS_STEP, article.slug,
                ),
            )
        )
        if not adapters.enabled:
            media_upload_coordinator.record_not_applicable(identity, member_run_id)
        else:
            media_upload_coordinator.record_prepared(identity, member_run_id)
        # Gate ON/OFFいずれの場合も同一の関数で記事専用runtimeを構築する
        # （build_protected_featured_media_runtime()自体がadapters.enabledに
        # 応じてdecorator付き/なしのruntimeを内部で適切に返す）。
        runtime = build_protected_featured_media_runtime(
            adapters, media_upload_coordinator, identity, member_run_id,
        )
    else:
        raise SideEffectExecutionModeContractError(ExecutionModeFailureReasonCode.UNKNOWN_EXECUTION_MODE)

    observation = None
    try:
        runtime_result = runtime.apply(article)
    except SideEffectExecutionModeContractError:
        raise  # runtime.apply()自体はこの例外を送出しない既存ロジックだが、
               # 他のcarve-outと同型の防御として明示する
    except Exception as exc:
        observation = runtime.classify_propagated_failure(exc)

    if observation is not None:
        raise FeaturedMediaPropagatedFailure(observation)

    if runtime_result.status is ArticleFeaturedMediaRuntimeStatus.CONTINUED_WITHOUT_FEATURED_MEDIA:
        print(f"    アイキャッチ画像なしで継続します（分類: {runtime_result.category.value}）")

    if media_upload_coordinator is not None and (
        runtime_result.status is ArticleFeaturedMediaRuntimeStatus.APPLIED
    ):
        media_id = _extract_confirmed_media_id(runtime_result.article)
        if media_id is not None:
            media_upload_coordinator.record_confirmed(identity, member_run_id, media_id)
            # POST（record_confirmed()）成功前にクラッシュした場合、durable stateは
            # 「IO_ARMED+ATTEMPTED」のまま残り、9.9.7節Cross-Store Combination Table
            # を経てHUMAN_REVIEW_REQUIREDへ導く（15.5.2節）。

    return runtime_result


def _handle_featured_media_failure(
    markdown_output,
    log_manager,
    article: ArticleData,
    saved_files: list,
    *,
    importance: str,
    seo_title: str,
    wp_public_url: str,
    x_post_status,
    observation: FeaturedMediaFailureObservation | None = None,
) -> None:
    """
    v6.21.0: アイキャッチ処理の失敗が伝播（PROPAGATE）したときの後処理。

    WordPress へは投稿せず、Markdown のみを直接保存して「失敗」として記録する。
    本関数は WordPress 出力を一切参照しないため、構造的に投稿は行われない。

    Markdown 保存自体が失敗した場合も例外を外へ出さず、固定ラベルの警告のみを
    表示する（例外メッセージ原文は出力しない）。記事1件の失敗として扱い、
    run 全体は停止させない。

    v6.25.0（DI-5）: observation（category／action／secret-freeなreason）を
    ArticleLogへ記録する。observation が None の場合は3フィールドとも ""。
    """
    try:
        markdown_save = markdown_output.save(article)
    except Exception:
        markdown_save = None

    if markdown_save is not None and markdown_save.success:
        output_path = Path(markdown_save.edit_url)
        saved_files.append((importance, seo_title, output_path))
        print(f"    保存: {output_path.name}")
    else:
        print("    警告: Markdownファイルの保存に失敗しました。")

    print("    警告: アイキャッチ画像の処理に失敗したため、この記事の投稿を見送りました。")
    log_manager.log_article(
        article=article,
        result="failed",
        error_message="featured media processing failed",
        wp_public_url=wp_public_url,
        x_post_status=x_post_status,
        post_id=None,
        featured_media_category=observation.category.value if observation else "",
        featured_media_action=observation.action.value if observation else "",
        featured_media_reason=(observation.reason or "") if observation else "",
    )


def main() -> int:
    start_time = time.time()
    started_at_iso = datetime.now(timezone.utc).astimezone().isoformat()

    # コマンドライン引数の処理
    parser = argparse.ArgumentParser(description="ゲームニュース記事生成ツール")
    parser.add_argument(
        "--max-articles",
        type=int,
        default=None,
        metavar="N",
        help="生成する記事の最大数（テスト用）。未指定時は通常ルールで動作。",
    )
    args = parser.parse_args()
    max_articles: int | None = args.max_articles

    if max_articles is not None and max_articles < 0:
        print("エラー: --max-articles には 0 以上の整数を指定してください。")
        return 1

    # Release 6.32（14.3節）：起動直後に1回だけExplicit Side-Effect Execution Mode
    # を解決する。値の再構築・再推測はしない（6章）。missing/unknown/矛盾した
    # envelopeはSideEffectExecutionModeContractErrorでfail-closedし、
    # if __name__ == "__main__": 側（14.6節）でexit code 3へ変換される。
    side_effect_execution_context = _parse_execution_context_from_env()

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("エラー: ANTHROPIC_API_KEY が設定されていません。")
        print(".env ファイルに ANTHROPIC_API_KEY=your_key を追加してください。")
        return 1

    default_media_id = int(os.getenv("DEFAULT_MEDIA_ID", "0"))
    publishing_config = PublishingConfig.from_env()
    sns_config = SnsConfig.from_env()
    log_manager = LogManager.from_env(base_dir=Path(__file__).parent)
    # v1.12.0: ANALYTICS_ENABLED=false の場合は NullAnalyticsManager（no-op）
    analytics_manager = AnalyticsManager.from_env(base_dir=Path(__file__).parent)

    # v6.21.0: アイキャッチ画像生成Runtime（Gate OFF時は無効状態のまま構築される。
    # Gate ON かつ credential 不足の場合はここで ValueError を受けて起動時に停止する）
    # Release 6.32（22.3.2節）：呼び出し箇所B。isinstance(context,
    # LegacyDirectExecutionContext)の場合のみArticleFeaturedMediaRuntime.from_env()
    # を呼ぶ（既存6.31以前の起動時1回構築をそのまま維持する）。
    # RetryLineageProtectedExecutionContextの場合はfrom_env()を一切呼ばず
    # （legacy credential/config解決を含むため）、MediaUploadWriteAheadAdapters.
    # from_env()のみを1回構築する。記事専用runtimeは_apply_featured_media_step()
    # 内部で記事ごとに構築する。
    try:
        if isinstance(side_effect_execution_context, LegacyDirectExecutionContext):
            featured_media_runtime = ArticleFeaturedMediaRuntime.from_env()
            featured_media_binding = build_legacy_featured_media_side_effect_binding(
                side_effect_execution_context, featured_media_runtime,
            )
        elif isinstance(side_effect_execution_context, RetryLineageProtectedExecutionContext):
            media_upload_adapters = MediaUploadWriteAheadAdapters.from_env()
            media_upload_coordinator = build_media_upload_safety_coordinator(
                media_upload_manager=ArticleMediaUploadStateManager(
                    JsonArticleMediaUploadStateStore(MEDIA_UPLOAD_STATE_DIR)
                ),
                applicability_store=JsonMediaUploadApplicabilityStore(MEDIA_UPLOAD_APPLICABILITY_DIR),
                attempt_context_store=JsonMediaUploadAttemptContextStore(MEDIA_UPLOAD_ATTEMPT_CONTEXT_DIR),
                locks_dir=MEDIA_UPLOAD_LOCKS_DIR,
            )
            manifest_registrar = ManifestRegistrarFacade(
                JsonProtectedOperationManifestStore(PROTECTED_OPERATION_MANIFEST_DIR)
            )
            featured_media_binding = build_protected_featured_media_side_effect_binding(
                side_effect_execution_context, media_upload_coordinator, media_upload_adapters,
                manifest_registrar,
            )
        else:
            raise SideEffectExecutionModeContractError(ExecutionModeFailureReasonCode.UNKNOWN_EXECUTION_MODE)
    except ValueError as e:
        print(f"エラー: アイキャッチ画像生成の設定が不正です: {e}")
        return 1

    client = anthropic.Anthropic(api_key=api_key)

    print("=" * 60)
    print("  ゲームニュース記事生成ツール - KAORUの部屋")
    print("=" * 60)
    print()

    # Step 1: ニュース収集
    all_news, feed_stats = collect_all_news(max_items_per_feed=20)
    if not all_news:
        print("ニュースを取得できませんでした。インターネット接続を確認してください。")
        return 1

    total_collected = len(all_news)

    # Step 2: キーワードフィルタリング
    filtered = filter_news(all_news)
    target_news = filtered["pass"]
    filtered_count = len(target_news)

    if not target_news:
        print("フィルター通過後のニュースが0件でした。")
        print("保留ニュース数:", len(filtered["pending"]))
        return 0

    # Step 3: 重複排除（APIコスト削減のため重要度判定の前に実施）
    target_news = deduplicate_news(target_news)
    deduped_count = len(target_news)

    # Step 4: 重要度判定
    judged = judge_all(client, target_news)

    # 重要度「なし」は除外
    judged = [r for r in judged if r["importance"] != "なし"]

    if not judged:
        print("記事化対象のニュースが見つかりませんでした。")
        return 0

    # Step 4: 重要度別に振り分けて記事化数を制限する
    s_items = [r for r in judged if r["importance"] == "S"]
    a_items = [r for r in judged if r["importance"] == "A"]
    b_items = [r for r in judged if r["importance"] == "B"]

    # A評価は上限まで、超過分はスキップ
    a_to_process = a_items[:A_ARTICLE_LIMIT]
    a_skipped    = a_items[A_ARTICLE_LIMIT:]

    # 記事生成対象（S優先 → A）
    to_process = s_items + a_to_process
    if max_articles is not None:
        to_process = to_process[:max_articles]

    # B評価 + Aスキップ分 → 候補ファイルにまとめる
    candidates = b_items + [dict(r, importance="A(スキップ)") for r in a_skipped]

    # 振り分け結果のログ表示
    a_skip_note = f"（全{len(a_items)}件中、{len(a_skipped)}件をスキップ）" if a_skipped else ""
    print("記事生成対象の振り分け結果:")
    print(f"  S評価（全件記事化）  : {len(s_items)}件")
    print(f"  A評価（最大{A_ARTICLE_LIMIT}件まで） : {len(a_to_process)}件  {a_skip_note}")
    print(f"  B評価（記事化なし）  : {len(b_items)}件 → 候補ファイルへ保存")
    print()

    planned = len(to_process)
    print(f"  記事生成予定: {planned}件")
    print(f"  API呼び出し予測: {planned * 3}回（article×{planned} + seo×{planned} + x_post×{planned}）")

    if max_articles is not None:
        print(f"  ※ --max-articles {max_articles} が指定されたため、先頭{planned}件のみ処理します")
    print()

    # 候補ファイルの保存（記事生成より前に保存して確実に残す）
    if candidates:
        b_path = _save_b_candidates_markdown(candidates)
        print(f"  候補ファイル保存完了: {b_path.name}（{len(candidates)}件）")
        print()

    if not to_process:
        print("生成対象の記事がありません。")
        return 0

    # Step 5: 記事生成・保存
    # v6.21.0: PROPAGATE時にMarkdownのみ直接保存するためインスタンスを保持する
    markdown_output = MarkdownOutput(output_dir=OUTPUT_DIR)
    # Release 6.32（15.7節）：呼び出し箇所A。RETRY_LINEAGE_PROTECTED時のみ
    # draft_state_managerを構築する（write-ahead ACKの実体）。LEGACY_DIRECT時は
    # Noneのまま渡し、WordPressOutput.save()は既存（6.31以前）のロジックのまま進む。
    draft_state_manager = None
    wp_manifest_registrar = None
    if isinstance(side_effect_execution_context, RetryLineageProtectedExecutionContext):
        draft_state_manager = WordPressDraftStateManager(
            JsonWordPressDraftStateStore(base_dir=WORDPRESS_DRAFT_STATE_DIR)
        )
        # Architecture Amendment（Protected Operation Manifest、呼び出し箇所A）。
        wp_manifest_registrar = ManifestRegistrarFacade(
            JsonProtectedOperationManifestStore(PROTECTED_OPERATION_MANIFEST_DIR)
        )
    # Architecture Amendment：既存Fake/exact-kwargsテストとのzero-diffのため
    # （既存の_call_start_run()等と同一理由）、manifest_registrarはNoneの場合
    # 呼び出し引数自体に含めない。
    wp_output_kwargs = {}
    if wp_manifest_registrar is not None:
        wp_output_kwargs["manifest_registrar"] = wp_manifest_registrar
    output_manager = OutputManager(outputs=[
        markdown_output,
        WordPressOutput.from_env_with_context(
            side_effect_execution_context, draft_state_manager, **wp_output_kwargs,
        ),
    ])

    print(f"記事を生成しています（{len(to_process)}件）...")
    saved_files = []
    api_call_count = 0
    wp_available = any(isinstance(o, WordPressOutput) and o.is_available() for o in output_manager.outputs)
    wp_success_count = 0
    wp_failed_count = 0
    wp_skipped_count = 0

    for i, entry in enumerate(to_process, 1):
        item: NewsItem = entry["item"]
        importance: str = entry["importance"]

        call_start = api_call_count + 1
        call_end   = api_call_count + 3
        print(f"\n  [{i}/{len(to_process)}] {importance} - {item.title[:50]}（API呼び出し: {call_start}〜{call_end}回目）")

        article_body = generate_article(client, item, importance)
        seo_title    = generate_seo_title(client, item, importance)
        # v1.9.0: slug を先に確定 → wp_public_url を生成 → x_post に埋め込む
        date_str      = datetime.now().strftime("%Y%m%d")
        slug          = generate_slug(seo_title, date_str)
        if sns_config.sns_enabled:
            wp_public_url = sns_config.resolve_public_url(slug)
            x_post_status = SnsPostStatus.PENDING
        else:
            wp_public_url = ""
            x_post_status = SnsPostStatus.SKIPPED
        x_post       = generate_x_post(
            client, item, importance, article_body,
            blog_url=wp_public_url if wp_public_url else "[ブログURL]",
        )
        api_call_count += 3

        excerpt            = _extract_excerpt(article_body)
        featured_image_url = resolve_featured_image(item)
        featured_media_id  = resolve_media_id(item, default_media_id)
        publish_status     = publishing_config.resolve_status(importance)
        article = ArticleData(
            item=item,
            importance=importance,
            seo_title=seo_title,
            article_body=article_body,
            x_post=x_post,
            featured_image_url=featured_image_url,
            excerpt=excerpt,
            meta_description=excerpt,  # v1.4.0 では excerpt と同値
            slug=slug,
            featured_media_id=featured_media_id,
            publish_status=publish_status,
        )

        # v6.25.0（DI-5）: 各記事の反復ごとに毎回Noneへ再初期化する。前の記事の
        # 観測値が次の記事へ漏れないことを保証する唯一の箇所。
        featured_media_observation: FeaturedMediaFailureObservation | None = None

        # v6.21.0: featured media適用（Gate OFF時は素通し。PROPAGATE対象の失敗は
        # ここで例外として捕捉し、WordPressへは投稿せずMarkdownのみ保存して次の記事へ進む）
        try:
            featured_media_result = _apply_featured_media_step(
                article, side_effect_binding=featured_media_binding,
            )
            article = featured_media_result.article
            featured_media_observation = featured_media_result.observation
        except SideEffectExecutionModeContractError:
            raise  # 6.32新設：contract violationはFeaturedMediaPropagatedFailureの
                   # PROPAGATE分類へ合流させず、記事ループの外まで未変換のまま伝播させる
        except FeaturedMediaPropagatedFailure as propagated:
            featured_media_observation = propagated.observation  # 22.3.2節、runtime内部で分類済み
            _handle_featured_media_failure(
                markdown_output,
                log_manager,
                article,
                saved_files,
                importance=importance,
                seo_title=seo_title,
                wp_public_url=wp_public_url,
                x_post_status=x_post_status,
                observation=featured_media_observation,
            )
            wp_failed_count += 1
            continue

        # v1.11.0: save_all() が list[SaveResult] を返す
        save_results = output_manager.save_all(article)
        wp_save = next((r for r in save_results if r.is_wordpress), None)
        edit_url = (wp_save.edit_url or "") if wp_save else ""

        # ログ記録（v1.8.0 追加、v1.11.0 で post_id を直接渡すよう改善）
        if not wp_available:
            wp_result = "skipped"
            wp_skipped_count += 1
        elif wp_save and wp_save.success:
            wp_result = "success"
            wp_success_count += 1
        else:
            wp_result = "failed"
            wp_failed_count += 1
        log_manager.log_article(
            article=article,
            edit_url=edit_url,
            result=wp_result,
            wp_public_url=wp_public_url,
            x_post_status=x_post_status,
            post_id=wp_save.post_id if wp_save else None,
            featured_media_category=(
                featured_media_observation.category.value if featured_media_observation else ""
            ),
            featured_media_action=(
                featured_media_observation.action.value if featured_media_observation else ""
            ),
            featured_media_reason=(
                (featured_media_observation.reason or "") if featured_media_observation else ""
            ),
        )

        # v1.12.0: WordPress 投稿成功時に placeholder AnalyticsEntry を保存
        # ANALYTICS_ENABLED=false の場合は NullAnalyticsManager が no-op で処理する
        if wp_save and wp_save.success and wp_save.post_id:
            placeholder = analytics_manager.create_placeholder_entry(
                post_id=wp_save.post_id,
                slug=article.slug,
                wp_public_url=wp_save.permalink or wp_public_url,
            )
            if placeholder is not None:
                analytics_manager.save_analytics_entry(placeholder)

        # v1.11.0: ファイル保存結果のみ saved_files に追加（WP URL は除外）
        for result in save_results:
            if result.success and not result.is_wordpress and result.edit_url:
                output_path = Path(result.edit_url)
                saved_files.append((importance, seo_title, output_path))
                print(f"    保存: {output_path.name}")

    # 完了サマリー・実行ログ記録（v1.8.0 追加）
    print()
    elapsed = time.time() - start_time
    finished_at_iso = datetime.now(timezone.utc).astimezone().isoformat()
    exec_result = "success" if wp_failed_count == 0 else ("partial" if wp_success_count > 0 else "failed")
    log_manager.log_execution(ExecutionLogEntry(
        executed_at=started_at_iso,
        finished_at=finished_at_iso,
        execution_time_sec=round(elapsed, 2),
        total_collected=total_collected,
        total_filtered=filtered_count,
        total_deduped=deduped_count,
        total_generated=planned,
        total_wp_success=wp_success_count,
        total_wp_failed=wp_failed_count,
        total_wp_skipped=wp_skipped_count,
        api_call_count=api_call_count,
        result=exec_result,
    ))
    print("=" * 60)
    print(f"  完了！ {len(saved_files)} 件の記事を生成しました（実行時間: {elapsed:.1f}秒）")
    print("=" * 60)
    print()

    s_count = sum(1 for imp, _, _ in saved_files if imp == "S")
    a_count = sum(1 for imp, _, _ in saved_files if imp == "A")
    print(f"  生成結果:")
    print(f"    重要度S（優先）    : {s_count}件")
    if a_skipped:
        print(f"    重要度A（通常）    : {a_count}件  （{len(a_skipped)}件スキップ）")
    else:
        print(f"    重要度A（通常）    : {a_count}件")
    print(f"    重要度B（スキップ）: {len(b_items)}件 → 候補ファイルに保存")
    print()
    print(f"  API呼び出し（記事生成）: {api_call_count}回")
    print()
    print(f"  保存先: {OUTPUT_DIR}")
    print()
    print("生成されたファイル一覧:")
    for importance, title, path in saved_files:
        print(f"  [{importance}] {title[:45]} → {path.name}")

    print()
    _print_rss_summary(feed_stats, total_collected, filtered_count, deduped_count, len(saved_files))

    # Release 6.30: main.py Outcome Contract（wp_skipped_countは判定に関与しない）
    if wp_failed_count == 0:
        return 0
    elif wp_success_count > 0:
        return 20
    else:
        return 21


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SideEffectExecutionModeContractError:
        # Release 6.32（14.6節）：NEWS Subprocess境界のContract-Error Exit Protocol。
        # メッセージ本文・reason_codeはexit codeという単一の整数へ縮退させ、
        # stdout/stderrへは出力しない（2.5節のsecret-safe規律）。
        sys.exit(SIDE_EFFECT_CONTRACT_VIOLATION_EXIT_CODE)
