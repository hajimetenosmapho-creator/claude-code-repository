"""
E2E テスト: v1.16.0 AI Rewrite Foundation

テストシナリオ:
    1.  RewriteConfig.from_env() が設定を読み込める
    2.  AI_REWRITE_ENABLED 未設定時に NullRewriteService が返る
    3.  ArticleProvider が ABC として定義されている
    4.  NullArticleProvider.fetch() が空文字列を返す
    5.  WordPressArticleProvider が ArticleProvider のサブクラスである
    6.  RewritePromptBuilder.build() が元記事ありでプロンプトを生成できる
    7.  RewritePromptBuilder.build() が元記事なし（空文字）でもプロンプトを生成できる
    8.  RewriteParser.parse() が正常にパースできる
    9.  RewriteParser.parse() が空レスポンス時に success=False を返す
    10. RewriteParser.parse() が不正 JSON 時に success=False と error_message を返す
    11. RewriteResult.success=True / False が正しく設定される
    12. RewriteResult.error_message が失敗時に設定される
    13. RewriteResult.to_dict() が全フィールドを含む
    14. RewriteResult.empty() が success=False の result を返す
    15. RewriteRepository.save() が Markdown + JSON を保存できる
    16. RewriteRepository に _save_json / _save_markdown が非公開で存在する
    17. success=False の RewriteResult も保存できる
    18. RewriteService.rewrite() の正常フロー（NullArticleProvider + mock client）
    19. RewriteService.rewrite() が article_content="" でも動作する
    20. NullRewriteService.rewrite() が success=False の RewriteResult を返す
    21. NullRewriteService.rewrite_batch() が空リストを返す
    22. RewriteService.rewrite_batch() の件数制限が動作する
    23. ClaudeClient が変更されていない（既存 import が通る）
    24. scripts/run_ai_rewrite.py が存在する
    25. __init__.py が新クラスをエクスポートする
    26. v1.14.0 パッケージの import が壊れない
    27. v1.15.0 パッケージの import が壊れない

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v1_16_0_ai_rewrite_foundation.py
"""
import inspect
import json
import os
import sys
import tempfile
from abc import ABC
from datetime import datetime
from pathlib import Path

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
        print(f"       期待値: {expected!r}")
        print(f"       実際値: {actual!r}")

def check_true(label: str, value: bool):
    check(label, value, True)

def check_false(label: str, value: bool):
    check(label, value, False)

def check_contains(label: str, text: str, keyword: str):
    check(label, keyword in str(text), True)

def check_none(label: str, value):
    check(label, value is None, True)

def check_not_none(label: str, value):
    check(label, value is not None, True)

# ─── モック ClaudeClient ───

class MockClaudeClient:
    """テスト用の ClaudeClient モック（実 API を叩かない）。"""
    def __init__(self, response: str = ""):
        self._response = response

    def is_available(self) -> bool:
        return True

    def send(self, prompt: str) -> str:
        return self._response

# ─── テスト用 RewriteResult ファクトリ ───

def make_suggestion():
    """テスト用の ImprovementSuggestion を生成する。"""
    from ai import ImprovementSuggestion
    return ImprovementSuggestion(
        article_id="test-article-slug",
        title="テスト記事タイトル",
        permalink="https://example.com/test-article",
        prompt_version="v1",
        summary="改善が必要な記事です",
        priority="high",
        issues=["タイトルが弱い", "内部リンクが少ない"],
        suggestions=["タイトルにキーワードを追加する", "関連記事へのリンクを追加する"],
    )

# ─── テスト実行 ───

print("=" * 60)
print("v1.16.0 AI Rewrite Foundation E2E テスト")
print("=" * 60)
print()

# ── テスト1: RewriteConfig.from_env() ──
print("[テスト1-2] RewriteConfig")
from ai import RewriteConfig

os.environ.pop("AI_REWRITE_ENABLED", None)
config = RewriteConfig.from_env()
check_false("1. デフォルトで enabled=False", config.enabled)
check("1. デフォルトモデル", config.model, "claude-sonnet-4-6")
check("1. デフォルトプロンプトバージョン", config.prompt_version, "v1")
check("1. デフォルト最大件数", config.max_articles, 5)
check("1. デフォルト出力ディレクトリ", config.output_dir, "outputs/ai_rewrites")

os.environ["AI_REWRITE_ENABLED"] = "false"
config2 = RewriteConfig.from_env()
check_false("1. AI_REWRITE_ENABLED=false で is_ready()=False", config2.is_ready())

# ── テスト2: NullRewriteService ──
from ai import RewriteService, NullRewriteService

os.environ["AI_REWRITE_ENABLED"] = "false"
service = RewriteService.from_env()
check("2. AI_REWRITE_ENABLED=false → NullRewriteService", type(service).__name__, "NullRewriteService")
check_false("2. NullRewriteService.is_available()=False", service.is_available())
print()

# ── テスト3-5: ArticleProvider ──
print("[テスト3-5] ArticleProvider")
from ai import ArticleProvider, NullArticleProvider, WordPressArticleProvider

check_true("3. ArticleProvider が ABC である", issubclass(ArticleProvider, ABC))
check_true("3. ArticleProvider.fetch が abstractmethod", getattr(ArticleProvider.fetch, "__isabstractmethod__", False))

null_provider = NullArticleProvider()
result_fetch = null_provider.fetch("test-slug", "https://example.com")
check("4. NullArticleProvider.fetch() が空文字を返す", result_fetch, "")

check_true("5. WordPressArticleProvider が ArticleProvider のサブクラス", issubclass(WordPressArticleProvider, ArticleProvider))
print()

# ── テスト6-7: RewritePromptBuilder ──
print("[テスト6-7] RewritePromptBuilder")
from ai import RewritePromptBuilder

suggestion = make_suggestion()
builder = RewritePromptBuilder(prompt_version="v1")

# 元記事あり
prompt_with_content = builder.build(suggestion, article_content="元記事の本文です。")
check_contains("6. プロンプトに article_id が含まれる", prompt_with_content, "test-article-slug")
check_contains("6. プロンプトにタイトルが含まれる", prompt_with_content, "テスト記事タイトル")
check_contains("6. プロンプトに元記事本文が含まれる", prompt_with_content, "元記事の本文です")
check_contains("6. プロンプトに issues が含まれる", prompt_with_content, "タイトルが弱い")
check_contains("6. プロンプトに suggestions が含まれる", prompt_with_content, "タイトルにキーワードを追加する")

# 元記事なし
prompt_no_content = builder.build(suggestion, article_content="")
check_contains("7. 元記事なし時も記事IDが含まれる", prompt_no_content, "test-article-slug")
check_contains("7. 元記事なし時に代替メッセージが含まれる", prompt_no_content, "元記事の取得ができませんでした")
print()

# ── テスト8-10: RewriteParser ──
print("[テスト8-10] RewriteParser")
from ai import RewriteParser

parser = RewriteParser()

# 正常なレスポンス
valid_response = json.dumps({
    "rewrite_draft": "# 改善版記事\n\n改善後の本文です。",
    "improvement_summary": "タイトルとリンクを改善しました。",
    "changes": ["タイトルにキーワード追加", "内部リンク追加"],
}, ensure_ascii=False)
parsed = parser.parse(
    raw_response=valid_response,
    article_id="test-slug",
    title="テスト記事",
    permalink="https://example.com",
    prompt_version="v1",
    original_content="元の記事です。",
)
check_true("8. 正常パース時に success=True", parsed.success)
check_none("8. 正常パース時に error_message=None", parsed.error_message)
check_contains("8. rewrite_draft が含まれる", parsed.rewrite_draft, "改善版記事")
check("8. improvement_summary が正しい", parsed.improvement_summary, "タイトルとリンクを改善しました。")
check("8. changes が正しい件数", len(parsed.changes), 2)
check("8. original_content が保持される", parsed.original_content, "元の記事です。")

# 空レスポンス
empty_parsed = parser.parse(raw_response="", article_id="test", title="test")
check_false("9. 空レスポンス時に success=False", empty_parsed.success)
check_not_none("9. 空レスポンス時に error_message が設定される", empty_parsed.error_message)

# 不正 JSON
bad_parsed = parser.parse(raw_response="これはJSONではありません", article_id="test", title="test")
check_false("10. 不正 JSON 時に success=False", bad_parsed.success)
check_not_none("10. 不正 JSON 時に error_message が設定される", bad_parsed.error_message)
print()

# ── テスト11-14: RewriteResult ──
print("[テスト11-14] RewriteResult")
from ai import RewriteResult

result_ok = RewriteResult(
    article_id="slug",
    title="タイトル",
    permalink="https://example.com",
    prompt_version="v1",
    original_content="元記事",
    rewrite_draft="改善版記事",
    improvement_summary="改善しました",
    changes=["変更1"],
    success=True,
    error_message=None,
)
check_true("11. success=True が設定される", result_ok.success)
check_none("11. success=True の時 error_message=None", result_ok.error_message)

result_fail = RewriteResult.empty(
    article_id="slug",
    title="タイトル",
    error_message="テストエラー",
)
check_false("12. empty() で success=False", result_fail.success)
check("12. empty() で error_message が設定される", result_fail.error_message, "テストエラー")

d = result_ok.to_dict()
check_true("13. to_dict() に success が含まれる", "success" in d)
check_true("13. to_dict() に error_message が含まれる", "error_message" in d)
check_true("13. to_dict() に rewrite_draft が含まれる", "rewrite_draft" in d)
check_true("13. to_dict() に original_content が含まれる", "original_content" in d)
check_true("13. to_dict() に changes が含まれる", "changes" in d)

result_empty = RewriteResult.empty()
check_false("14. empty() は success=False", result_empty.success)
check("14. empty() の rewrite_draft は空文字", result_empty.rewrite_draft, "")
check("14. empty() の changes は空リスト", result_empty.changes, [])
print()

# ── テスト15-17: RewriteRepository ──
print("[テスト15-17] RewriteRepository")
from ai import RewriteRepository

with tempfile.TemporaryDirectory() as tmpdir:
    repo = RewriteRepository(Path(tmpdir))

    success_result = RewriteResult(
        article_id="test-slug",
        title="テスト記事",
        permalink="https://example.com",
        prompt_version="v1",
        original_content="元記事",
        rewrite_draft="# 改善版\n\n改善版の本文。",
        improvement_summary="改善しました",
        changes=["変更1", "変更2"],
        success=True,
        error_message=None,
    )
    json_path, md_path = repo.save(success_result)

    check_not_none("15. save() が JSON パスを返す", json_path)
    check_not_none("15. save() が Markdown パスを返す", md_path)
    check_true("15. JSON ファイルが存在する", json_path is not None and json_path.exists())
    check_true("15. Markdown ファイルが存在する", md_path is not None and md_path.exists())

    if json_path and json_path.exists():
        with json_path.open(encoding="utf-8") as f:
            saved_data = json.load(f)
        check("15. JSON に article_id が含まれる", saved_data.get("article_id"), "test-slug")
        check_true("15. JSON に success が含まれる", "success" in saved_data)

    if md_path and md_path.exists():
        md_content = md_path.read_text(encoding="utf-8")
        check_contains("15. Markdown にタイトルが含まれる", md_content, "テスト記事")
        check_contains("15. Markdown に改善版記事が含まれる", md_content, "改善版")

# _save_json / _save_markdown が非公開メソッドとして存在するか
check_true("16. _save_json が内部メソッドとして存在する", hasattr(RewriteRepository, "_save_json"))
check_true("16. _save_markdown が内部メソッドとして存在する", hasattr(RewriteRepository, "_save_markdown"))
check_false("16. save_json（公開名）は存在しない", hasattr(RewriteRepository, "save_json"))
check_false("16. save_markdown（公開名）は存在しない", hasattr(RewriteRepository, "save_markdown"))

# success=False の result も保存できるか
with tempfile.TemporaryDirectory() as tmpdir:
    repo2 = RewriteRepository(Path(tmpdir))
    fail_result = RewriteResult.empty(
        article_id="fail-slug",
        title="失敗記事",
        error_message="テストエラー",
    )
    j_path, m_path = repo2.save(fail_result)
    check_not_none("17. success=False の result を JSON 保存できる", j_path)
    check_not_none("17. success=False の result を Markdown 保存できる", m_path)
    if m_path and m_path.exists():
        fail_md = m_path.read_text(encoding="utf-8")
        check_contains("17. Markdown にエラー情報が含まれる", fail_md, "テストエラー")
print()

# ── テスト18-22: RewriteService / NullRewriteService ──
print("[テスト18-22] RewriteService / NullRewriteService")
from ai import RewriteService, NullRewriteService, RewriteConfig
from ai.article_provider import NullArticleProvider
from ai.rewrite_prompt_builder import RewritePromptBuilder
from ai.rewrite_parser import RewriteParser
from ai.rewrite_repository import RewriteRepository

valid_rewrite_response = json.dumps({
    "rewrite_draft": "# 改善版タイトル\n\n改善版の本文。",
    "improvement_summary": "タイトルを改善しました。",
    "changes": ["タイトル改善"],
}, ensure_ascii=False)

with tempfile.TemporaryDirectory() as tmpdir:
    test_config = RewriteConfig(
        enabled=True,
        model="claude-sonnet-4-6",
        prompt_version="v1",
        max_articles=5,
        output_dir=tmpdir,
        api_key="test-key",
    )
    mock_client = MockClaudeClient(response=valid_rewrite_response)
    test_repo = RewriteRepository(Path(tmpdir))
    test_service = RewriteService(
        config=test_config,
        provider=NullArticleProvider(),
        client=mock_client,
        repository=test_repo,
    )

    suggestion = make_suggestion()
    result = test_service.rewrite(suggestion)
    check_true("18. rewrite() が success=True を返す", result.success)
    check_none("18. rewrite() で error_message=None", result.error_message)
    check_contains("18. rewrite_draft が生成される", result.rewrite_draft, "改善版タイトル")

    # 元記事なし（article_content=""）でも動作するか
    result_no_content = test_service.rewrite(suggestion)
    check_true("19. article_content='' でも success=True", result_no_content.success)

# NullRewriteService
null_service = NullRewriteService()
suggestion = make_suggestion()
null_result = null_service.rewrite(suggestion)
check_false("20. NullRewriteService.rewrite() → success=False", null_result.success)
check_not_none("20. NullRewriteService.rewrite() → error_message 設定", null_result.error_message)

null_batch = null_service.rewrite_batch([suggestion, suggestion])
check("21. NullRewriteService.rewrite_batch() → 空リスト", null_batch, [])

# rewrite_batch の件数制限
with tempfile.TemporaryDirectory() as tmpdir:
    test_config2 = RewriteConfig(
        enabled=True,
        model="claude-sonnet-4-6",
        prompt_version="v1",
        max_articles=2,
        output_dir=tmpdir,
        api_key="test-key",
    )
    mock_client2 = MockClaudeClient(response=valid_rewrite_response)
    test_repo2 = RewriteRepository(Path(tmpdir))
    test_service2 = RewriteService(
        config=test_config2,
        provider=NullArticleProvider(),
        client=mock_client2,
        repository=test_repo2,
    )
    suggestions_list = [make_suggestion() for _ in range(5)]
    batch_results = test_service2.rewrite_batch(suggestions_list, max_articles=2)
    check("22. rewrite_batch() の件数制限が動作する", len(batch_results), 2)
print()

# ── テスト23: ClaudeClient が変更されていない ──
print("[テスト23] ClaudeClient の後方互換性")
from ai import ClaudeClient, NullClaudeClient, AiImprovementConfig

check_true("23. ClaudeClient が import できる", True)
null_client = NullClaudeClient()
check_false("23. NullClaudeClient.is_available()=False", null_client.is_available())
check("23. NullClaudeClient.send() が空文字を返す", null_client.send("test"), "")
check_false("23. ClaudeClient に from_config が存在しない", hasattr(ClaudeClient, "from_config"))
print()

# ── テスト24: scripts/run_ai_rewrite.py ──
print("[テスト24] scripts/run_ai_rewrite.py の存在確認")
script_path = Path(__file__).parent.parent / "scripts" / "run_ai_rewrite.py"
check_true("24. scripts/run_ai_rewrite.py が存在する", script_path.exists())
print()

# ── テスト25: __init__.py エクスポート確認 ──
print("[テスト25] __init__.py エクスポート確認")
import ai as ai_pkg
new_exports = [
    "RewriteConfig",
    "RewriteResult",
    "ArticleProvider",
    "WordPressArticleProvider",
    "NullArticleProvider",
    "RewritePromptBuilder",
    "RewriteParser",
    "RewriteRepository",
    "RewriteService",
    "NullRewriteService",
]
for name in new_exports:
    check_true(f"25. {name} が __init__.py からエクスポートされている", hasattr(ai_pkg, name))
print()

# ── テスト26-27: 既存バージョンの後方互換性 ──
print("[テスト26-27] v1.14.0 / v1.15.0 後方互換性")
try:
    from ai import (
        AiImprovementConfig, ImprovementSuggestion, ImprovementSuggestionParser,
        PromptBuilder, ClaudeClient, NullClaudeClient,
        AiImprovementService, NullAiImprovementService,
    )
    check_true("26. v1.14.0 の全クラスが import できる", True)
except ImportError as e:
    check_true(f"26. v1.14.0 の全クラスが import できる（失敗: {e}）", False)

try:
    from ai import (
        ImprovementRepository, ImprovementReportBuilder, ImprovementReviewService,
    )
    check_true("27. v1.15.0 の全クラスが import できる", True)
except ImportError as e:
    check_true(f"27. v1.15.0 の全クラスが import できる（失敗: {e}）", False)

print()

# ─── 結果サマリー ───
print("=" * 60)
total = len(results)
passed = sum(1 for s, _ in results if s == "PASS")
failed = sum(1 for s, _ in results if s == "FAIL")
print(f"結果: {passed}/{total} PASS  /  {failed} FAIL")
print("=" * 60)

if failed:
    print()
    print("【失敗一覧】")
    for status, label in results:
        if status == "FAIL":
            print(f"  NG: {label}")
    sys.exit(1)
else:
    print("全テスト PASS")
    sys.exit(0)
