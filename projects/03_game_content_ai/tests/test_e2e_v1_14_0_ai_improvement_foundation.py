"""
E2E テスト: v1.14.0 AI Improvement Foundation

テストシナリオ:
    1.  AiImprovementConfig が環境変数から読み込める
    2.  disabled 時に NullAiImprovementService が安全に動く
    3.  PromptBuilder が日本語プロンプトを生成する
    4.  PromptBuilder に Prompt Version が反映される
    5.  ImprovementSuggestionParser が正常な JSON を parse できる
    6.  JSON 前後に余計な文章がある場合も parse できる
    7.  不正 JSON 時に安全に失敗する（empty suggestion を返す）
    8.  AiInputRecord.permalink 追加で既存テストが壊れない
    9.  ArticleAnalysisRecord.wp_public_url が存在する（v1.13.0 から継続）
    10. AiImprovementService が has_performance_data=True の記事のみ処理する
    11. API 呼び出し部分は mock 化（実 API を叩かない）
    12. ImprovementSuggestion.to_dict() / to_json() が動作する
    13. ImprovementSuggestion.empty() が正しいデフォルト値を持つ
    14. PromptBuilder が未知のバージョンで v1 にフォールバックする
    15. v1 プロンプトに必須情報が含まれる（記事情報・SC指標・GA4指標）
    16. NullClaudeClient が is_available()=False / send()="" を返す
    17. ClaudeClient.from_env() が APIキーなしで NullClaudeClient を返す
    18. ImprovementSuggestionParser の ```json ブロック抽出
    19. ImprovementSuggestionParser の生 JSON 抽出
    20. AiImprovementService.improve_batch() のフィルタリング動作
    21. main.py で投稿直後に AI 改善提案を実行しない
    22. v1.13.0 / v1.12.0 / v1.10.0 互換性（インポートテスト）

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v1_14_0_ai_improvement_foundation.py
"""
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# ─── テスト用ユーティリティ ───

results = []

def check(label: str, actual, expected, exact: bool = True):
    if exact:
        ok = actual == expected
    else:
        ok = expected in str(actual)
    status = "PASS" if ok else "FAIL"
    results.append((status, label))
    mark = "OK" if ok else "NG"
    print(f"  [{mark}] {label}")
    if not ok:
        print(f"       Expected: {expected!r}")
        print(f"       Actual:   {actual!r}")


def make_ai_input(
    post_id=1,
    slug="test-article",
    seo_title="テスト記事タイトル",
    importance="A",
    source_name="TestSource",
    published=True,
    x_posted=False,
    has_performance_data=True,
    impressions=1000,
    clicks=50,
    ctr=0.05,
    avg_position=5.0,
    page_views=200,
    sessions=180,
    bounce_rate=0.4,
    avg_engagement_time=45.0,
    permalink="https://example.com/test-article/",
):
    from analytics.analytics_entry import AiInputRecord
    return AiInputRecord(
        post_id=post_id,
        slug=slug,
        seo_title=seo_title,
        importance=importance,
        source_name=source_name,
        published=published,
        x_posted=x_posted,
        has_performance_data=has_performance_data,
        impressions=impressions,
        clicks=clicks,
        ctr=ctr,
        avg_position=avg_position,
        page_views=page_views,
        sessions=sessions,
        bounce_rate=bounce_rate,
        avg_engagement_time=avg_engagement_time,
        permalink=permalink,
    )


# ─── Scenario 1: AiImprovementConfig ───

print("\n=== Scenario 1: AiImprovementConfig.from_env() ===")

from ai.ai_improvement_config import AiImprovementConfig

for key in ["AI_IMPROVEMENT_ENABLED", "AI_IMPROVEMENT_MODEL", "AI_IMPROVEMENT_PROMPT_VERSION",
            "AI_IMPROVEMENT_MAX_ARTICLES", "ANTHROPIC_API_KEY", "AI_TIMEOUT_SECONDS"]:
    os.environ.pop(key, None)

config_default = AiImprovementConfig.from_env()
check("デフォルト: enabled=False", config_default.enabled, False)
check("デフォルト: model=claude-sonnet-4-6", config_default.model, "claude-sonnet-4-6")
check("デフォルト: prompt_version=v1", config_default.prompt_version, "v1")
check("デフォルト: max_articles=10", config_default.max_articles, 10)
check("デフォルト: api_key=None", config_default.api_key, None)
check("デフォルト: timeout_seconds=60", config_default.timeout_seconds, 60)
check("デフォルト: is_ready()=False", config_default.is_ready(), False)

os.environ["AI_IMPROVEMENT_ENABLED"] = "true"
os.environ["AI_IMPROVEMENT_MODEL"] = "claude-haiku-4-5-20251001"
os.environ["AI_IMPROVEMENT_MAX_ARTICLES"] = "5"
os.environ["ANTHROPIC_API_KEY"] = "test-key-12345"

config_enabled = AiImprovementConfig.from_env()
check("有効時: enabled=True", config_enabled.enabled, True)
check("有効時: model 設定済み", config_enabled.model, "claude-haiku-4-5-20251001")
check("有効時: max_articles=5", config_enabled.max_articles, 5)
check("有効時: api_key 設定済み", config_enabled.api_key, "test-key-12345")
check("有効時: is_ready()=True", config_enabled.is_ready(), True)

for key in ["AI_IMPROVEMENT_ENABLED", "AI_IMPROVEMENT_MODEL", "AI_IMPROVEMENT_MAX_ARTICLES", "ANTHROPIC_API_KEY"]:
    os.environ.pop(key, None)

# ─── Scenario 2: NullAiImprovementService ───

print("\n=== Scenario 2: NullAiImprovementService ===")

from ai.ai_improvement_service import NullAiImprovementService

null_service = NullAiImprovementService()
check("NullService: is_available()=False", null_service.is_available(), False)

ai_input = make_ai_input()
null_result = null_service.improve(ai_input)
check("NullService: improve() が ImprovementSuggestion を返す", null_result.__class__.__name__, "ImprovementSuggestion")
check("NullService: improve() の article_id", null_result.article_id, "test-article")

null_batch = null_service.improve_batch([ai_input])
check("NullService: improve_batch() が空リストを返す", null_batch, [])

# ─── Scenario 3 & 4: PromptBuilder ───

print("\n=== Scenario 3 & 4: PromptBuilder ===")

from ai.prompt_builder import PromptBuilder

builder_v1 = PromptBuilder(prompt_version="v1")
check("PromptBuilder: prompt_version=v1", builder_v1.prompt_version, "v1")

ai_input_with_data = make_ai_input(
    seo_title="PS6発表！次世代ゲーム機の詳細判明",
    slug="ps6-announced-20260630",
    importance="S",
    impressions=5000,
    clicks=250,
    ctr=0.05,
    avg_position=3.2,
    page_views=800,
    sessions=720,
    bounce_rate=0.35,
    avg_engagement_time=62.5,
    permalink="https://example.com/ps6-announced-20260630/",
)

prompt = builder_v1.build(ai_input_with_data)
check("プロンプトが文字列", isinstance(prompt, str), True)
check("プロンプトが空でない", len(prompt) > 100, True)
check("日本語を含む", "記事" in prompt, True)
check("SEOタイトルを含む", "PS6発表！次世代ゲーム機の詳細判明" in prompt, True)
check("permalink を含む", "https://example.com/ps6-announced-20260630/" in prompt, True)
check("importance の説明を含む", "最重要ニュース" in prompt, True)
check("SC 表示回数を含む", "5,000" in prompt, True)
check("GA4 ページビューを含む", "800" in prompt, True)
check("avg_engagement_time の説明を含む", "エンゲージメント時間" in prompt, True)
check("avg_position の説明を含む", "掲載順位" in prompt, True)
check("JSON 返答指示を含む", "JSON" in prompt, True)
check("自動リライト禁止を含む", "自動" in prompt, True)

# ─── Scenario 4: Prompt Version フォールバック ───

print("\n=== Scenario 4: Prompt Version フォールバック ===")

builder_unknown = PromptBuilder(prompt_version="v99")
check("未知バージョン: v1 にフォールバック", builder_unknown.prompt_version, "v1")
prompt_fallback = builder_unknown.build(ai_input)
check("フォールバックプロンプトが生成できる", len(prompt_fallback) > 10, True)

# ─── Scenario 5 & 6 & 7: ImprovementSuggestionParser ───

print("\n=== Scenario 5, 6, 7: ImprovementSuggestionParser ===")

from ai.improvement_suggestion_parser import ImprovementSuggestionParser

parser = ImprovementSuggestionParser()

# 正常な JSON
valid_json = json.dumps({
    "summary": "記事は概ね良好ですが、SEO改善の余地があります。",
    "priority": "medium",
    "issues": ["CTRが低い", "タイトルに数字がない"],
    "suggestions": ["タイトルに具体的な数字を入れる", "メタディスクリプションを最適化する"],
    "seo_title_suggestion": "PS6発表！スペック・価格・発売日まとめ【2026年版】",
    "meta_description_suggestion": "PS6の全情報を徹底解説。"
}, ensure_ascii=False)

result_valid = parser.parse(
    raw_response=valid_json,
    article_id="test-slug",
    title="テスト記事",
    permalink="https://example.com/test/",
    prompt_version="v1",
)
check("正常JSON: summary", result_valid.summary, "記事は概ね良好ですが、SEO改善の余地があります。")
check("正常JSON: priority=medium", result_valid.priority, "medium")
check("正常JSON: issues 件数", len(result_valid.issues), 2)
check("正常JSON: suggestions 件数", len(result_valid.suggestions), 2)
check("正常JSON: seo_title_suggestion", result_valid.seo_title_suggestion, "PS6発表！スペック・価格・発売日まとめ【2026年版】")
check("正常JSON: article_id", result_valid.article_id, "test-slug")
check("正常JSON: raw_response 保持", result_valid.raw_response, valid_json)

# ```json ブロックあり
markdown_json = f"""
ここに改善提案を示します。

```json
{valid_json}
```

以上です。
"""

result_markdown = parser.parse(
    raw_response=markdown_json,
    article_id="test-slug",
    title="テスト記事",
    permalink=None,
    prompt_version="v1",
)
check("```json ブロック: parse 成功", result_markdown.priority, "medium")
check("```json ブロック: issues 件数", len(result_markdown.issues), 2)

# ``` ブロックのみ
plain_block = f"```\n{valid_json}\n```"
result_block = parser.parse(
    raw_response=plain_block,
    article_id="test-slug",
    title="テスト",
    permalink=None,
    prompt_version="v1",
)
check("``` ブロック: parse 成功", result_block.priority, "medium")

# { ... } 抽出パターン
brace_json = f"改善提案は以下の通りです: {valid_json} 以上です。"
result_brace = parser.parse(
    raw_response=brace_json,
    article_id="brace-test",
    title="テスト",
    permalink=None,
    prompt_version="v1",
)
check("中括弧抽出: parse 成功", result_brace.priority, "medium")

# 不正 JSON → empty suggestion
result_invalid = parser.parse(
    raw_response="これはJSON形式ではありません。",
    article_id="invalid-test",
    title="テスト",
    permalink=None,
    prompt_version="v1",
)
check("不正JSON: empty suggestion 返却", result_invalid.summary, "")
check("不正JSON: priority=low", result_invalid.priority, "low")
check("不正JSON: issues 空", result_invalid.issues, [])
check("不正JSON: raw_response 保持", result_invalid.raw_response, "これはJSON形式ではありません。")

# 空文字 → empty suggestion
result_empty = parser.parse(
    raw_response="",
    article_id="empty-test",
    title="テスト",
    permalink=None,
    prompt_version="v1",
)
check("空文字: empty suggestion", result_empty.summary, "")

# ─── Scenario 8: AiInputRecord.permalink ───

print("\n=== Scenario 8: AiInputRecord.permalink 追加 ===")

from analytics.analytics_entry import AiInputRecord

# permalink なし（後方互換）
ai_no_permalink = AiInputRecord(
    post_id=1,
    slug="old-article",
    seo_title="古い記事",
    importance="B",
    source_name="OldSource",
    published=False,
    x_posted=False,
    has_performance_data=False,
    impressions=0,
    clicks=0,
    ctr=0.0,
    avg_position=0.0,
    page_views=0,
)
check("permalink 未指定: None", ai_no_permalink.permalink, None)

# permalink あり
ai_with_permalink = AiInputRecord(
    post_id=2,
    slug="new-article",
    seo_title="新しい記事",
    importance="S",
    source_name="NewSource",
    published=True,
    x_posted=True,
    has_performance_data=True,
    impressions=100,
    clicks=10,
    ctr=0.1,
    avg_position=2.0,
    page_views=50,
    permalink="https://example.com/new-article/",
)
check("permalink 設定済み", ai_with_permalink.permalink, "https://example.com/new-article/")

# to_dict() に permalink が含まれる
ai_dict = ai_with_permalink.to_dict()
check("to_dict() に permalink 含む", "permalink" in ai_dict, True)
check("to_dict() の permalink 値", ai_dict["permalink"], "https://example.com/new-article/")

# ─── Scenario 9: ArticleAnalysisRecord.wp_public_url ───

print("\n=== Scenario 9: ArticleAnalysisRecord.wp_public_url ===")

from analytics.analytics_entry import ArticleAnalysisRecord

record = ArticleAnalysisRecord(
    post_id=1,
    slug="test-article",
    seo_title="テスト",
    importance="A",
    publish_status="pending",
    logged_at="2026-06-30T00:00:00+09:00",
    source_name="TestSource",
    wp_public_url="https://example.com/test-article/",
    x_post_status="posted",
    measured_at="2026-06-30",
    period_days=28,
    impressions=1000,
    clicks=50,
    ctr=0.05,
    avg_position=5.0,
    page_views=200,
)
check("ArticleAnalysisRecord.wp_public_url 存在", record.wp_public_url, "https://example.com/test-article/")

# ─── Scenario 10 & 11: AiImprovementService バッチフィルタリング（mock）───

print("\n=== Scenario 10: AiImprovementService improve_batch() ===")

from ai.ai_improvement_service import AiImprovementService
from ai.ai_improvement_config import AiImprovementConfig
from ai.claude_client import NullClaudeClient

# has_performance_data=True の記事のみ処理する
with tempfile.TemporaryDirectory() as tmpdir:
    config = AiImprovementConfig(
        enabled=True,
        model="claude-sonnet-4-6",
        prompt_version="v1",
        max_articles=10,
        output_dir=tmpdir,
        api_key="test-key",
        timeout_seconds=60,
    )

    # mock クライアントを注入
    mock_client = MagicMock()
    mock_client.is_available.return_value = True
    mock_client.send.return_value = json.dumps({
        "summary": "モックレスポンス",
        "priority": "medium",
        "issues": ["テスト問題"],
        "suggestions": ["テスト提案"],
        "seo_title_suggestion": None,
        "meta_description_suggestion": None,
    }, ensure_ascii=False)

    service = AiImprovementService(config=config, client=mock_client, output_dir=Path(tmpdir))

    ai_with_data = make_ai_input(slug="has-data", has_performance_data=True)
    ai_without_data = make_ai_input(slug="no-data", has_performance_data=False)

    suggestions = service.improve_batch(
        ai_inputs=[ai_with_data, ai_without_data],
        performance_only=True,
    )

    check("improve_batch: performance_only で has_data のみ処理", len(suggestions), 1)
    check("improve_batch: 処理された slug", suggestions[0].article_id, "has-data")
    check("improve_batch: mock が1回呼ばれた", mock_client.send.call_count, 1)

    # JSON ファイルが保存されているか
    saved_files = list(Path(tmpdir).glob("*_improvement.json"))
    check("JSON ファイルが保存されている", len(saved_files), 1)

# max_articles 制限
with tempfile.TemporaryDirectory() as tmpdir:
    config_limit = AiImprovementConfig(
        enabled=True,
        model="claude-sonnet-4-6",
        prompt_version="v1",
        max_articles=1,
        output_dir=tmpdir,
        api_key="test-key",
    )
    mock_client2 = MagicMock()
    mock_client2.is_available.return_value = True
    mock_client2.send.return_value = json.dumps({
        "summary": "テスト", "priority": "low",
        "issues": [], "suggestions": [],
        "seo_title_suggestion": None, "meta_description_suggestion": None,
    })

    service_limit = AiImprovementService(config=config_limit, client=mock_client2, output_dir=Path(tmpdir))
    inputs = [make_ai_input(slug=f"article-{i}", has_performance_data=True) for i in range(3)]
    results_limited = service_limit.improve_batch(inputs, performance_only=True)
    check("max_articles=1: 1件のみ処理", len(results_limited), 1)

# ─── Scenario 12: ImprovementSuggestion ───

print("\n=== Scenario 12 & 13: ImprovementSuggestion ===")

from ai.improvement_suggestion import ImprovementSuggestion

suggestion = ImprovementSuggestion(
    article_id="test-slug",
    title="テスト記事",
    permalink="https://example.com/test/",
    prompt_version="v1",
    summary="改善の余地があります。",
    priority="high",
    issues=["問題1", "問題2"],
    suggestions=["提案1"],
    raw_response='{"summary": "..."}',
)

d = suggestion.to_dict()
check("to_dict() が dict を返す", isinstance(d, dict), True)
check("to_dict() に article_id", d["article_id"], "test-slug")
check("to_dict() に priority", d["priority"], "high")
check("to_dict() に created_at", "created_at" in d, True)

j = suggestion.to_json()
check("to_json() が str を返す", isinstance(j, str), True)
parsed = json.loads(j)
check("to_json() がパース可能", parsed["article_id"], "test-slug")

# empty()
empty = ImprovementSuggestion.empty(
    article_id="empty-test",
    title="空の記事",
    permalink=None,
    prompt_version="v1",
    raw_response="生レスポンス",
)
check("empty(): summary 空", empty.summary, "")
check("empty(): priority=low", empty.priority, "low")
check("empty(): issues 空", empty.issues, [])
check("empty(): raw_response 保持", empty.raw_response, "生レスポンス")

# ─── Scenario 16 & 17: NullClaudeClient / ClaudeClient.from_env() ───

print("\n=== Scenario 16 & 17: ClaudeClient ===")

from ai.claude_client import ClaudeClient, NullClaudeClient

null_client = NullClaudeClient()
check("NullClaudeClient: is_available()=False", null_client.is_available(), False)
check("NullClaudeClient: send() 空文字", null_client.send("test"), "")

# APIキーなし → NullClaudeClient
for key in ["ANTHROPIC_API_KEY", "AI_IMPROVEMENT_ENABLED"]:
    os.environ.pop(key, None)

client_from_env = ClaudeClient.from_env()
check("APIキーなし: NullClaudeClient を返す", client_from_env.__class__.__name__, "NullClaudeClient")

# ─── Scenario 21: main.py で AI 改善提案を実行しない ───

print("\n=== Scenario 21: main.py で投稿直後に AI 改善提案を実行しない ===")

main_path = Path(__file__).parent.parent / "main.py"
main_content = main_path.read_text(encoding="utf-8")
check("main.py に AiImprovementService のインポートなし", "AiImprovementService" not in main_content, True)
check("main.py に ai_improvement の呼び出しなし", "ai_improvement" not in main_content, True)

# ─── Scenario 22: 互換性テスト ───

print("\n=== Scenario 22: v1.13.0 / v1.12.0 / v1.10.0 互換性 ===")

try:
    from analytics import AnalyticsManager, NullAnalyticsManager
    from analytics import SearchConsoleMetrics, GoogleAnalyticsMetrics
    from analytics import AnalyticsEntry, ArticleAnalysisRecord, AiInputRecord
    from analytics import SearchConsoleClient, NullSearchConsoleClient
    from analytics import GoogleAnalyticsClient, NullGoogleAnalyticsClient
    check("analytics パッケージのインポート", True, True)
except ImportError as e:
    check("analytics パッケージのインポート", str(e), "")

try:
    from ai import AiImprovementConfig, ImprovementSuggestion
    from ai import PromptBuilder, ClaudeClient, NullClaudeClient
    from ai import AiImprovementService, NullAiImprovementService
    check("ai パッケージのインポート", True, True)
except ImportError as e:
    check("ai パッケージのインポート", str(e), "")

# ─── 結果集計 ───

print()
print("=" * 60)
total = len(results)
passed = sum(1 for s, _ in results if s == "PASS")
failed = sum(1 for s, _ in results if s == "FAIL")
print(f"結果: {passed}/{total} PASS  |  FAIL: {failed}")
print("=" * 60)

if failed > 0:
    print()
    print("【失敗したテスト】")
    for status, label in results:
        if status == "FAIL":
            print(f"  NG  {label}")
    sys.exit(1)
else:
    print("すべてのテストが通過しました。")
