# v1.14.0 AI Improvement Foundation 設計書

作成日：2026-07-01（v2.1.0 Documentation Foundationにて事後作成）

> 本設計書は実装（2026-06-30, commit `73e2bfd`）から遅れて作成されたものです。
> 内容はソースコードのDocstring・実装から再構成しています。実装当時の検討過程（なぜこの設計に至ったか）の一次情報は
> 各モジュールのDocstringを参照してください。

---

## 1. Goal

Analytics Foundation（v1.10.0）で蓄積した記事のパフォーマンスデータ（`AiInputRecord`）を入力とし、
Claude APIを使って「この記事をどう改善すべきか」の提案を生成する基盤を作る。

v1.14.0では改善提案の**生成**のみを行い、記事の書き換えは行わない（書き換えはv1.16.0 AI Rewrite Foundationで実装）。

---

## 2. Background

### 現状の問題点

- v1.10.0までで記事のパフォーマンスデータを蓄積する構造（`AiInputRecord`）は用意したが、
  そのデータを実際に活用する仕組みがなかった。
- 記事の改善は完全に人手に依存しており、「どの記事を」「どう直すべきか」の判断材料がなかった。

### v1.14.0 が解決すること

- `AiInputRecord` を受け取り、Claude APIで改善提案（`ImprovementSuggestion`）を生成する。
- 生成した提案は `outputs/ai_improvements/` にJSONファイルとして保存し、後続のレビュー・リライト工程で再利用できるようにする。

---

## 3. Scope

### 実装対象

- `src/ai/` パッケージ新規作成（以降のAI系機能すべての起点）
- `ClaudeClient` / `NullClaudeClient`（Claude APIとの通信）
- `PromptBuilder`（プロンプト生成）
- `ImprovementSuggestionParser`（JSONレスポンス解析）
- `AiImprovementService` / `NullAiImprovementService`（上記を統合するサービス層）
- `scripts/run_ai_improvement.py`（バッチ実行スクリプト）

### 対象外（Non Goalへ）

- 記事本文の書き換え（v1.16.0）
- 改善提案のレビュー・レポート化（v1.15.0）
- `main.py`（投稿処理）からの自動呼び出し

---

## 4. Non Goal

- `main.py` から本機能を呼び出さない。投稿直後はSearch Console/GA4データが存在しないため、
  データが蓄積された後に別スクリプト（`scripts/run_ai_improvement.py`）として実行する設計とする。
- 記事の自動書き換え・自動投稿は行わない（v1.16.0以降のスコープ）。

---

## 5. User Workflow

### Before（v1.13.0）

- Search Console / GA4のデータは取得できるが、そこから何をすべきかはブロガー本人が判断する必要があった。

### After（v1.14.0）

1. ブロガーが `python scripts/run_ai_improvement.py` を実行する
2. パフォーマンスデータのある記事について、Claude APIが改善提案を生成する
3. 提案は `outputs/ai_improvements/YYYYMMDD_{slug}_improvement.json` に保存される
4. ブロガーはJSONファイル（またはv1.15.0のレポート）を見て、リライトするかを判断する

---

## 6. System Workflow

```
AiInputRecord（Analytics Foundationが生成）
  → PromptBuilder.build()                 プロンプト文字列を組み立てる
  → ClaudeClient.send()                   Claude API へ送信し raw_response を得る
  → ImprovementSuggestionParser.parse()   JSON文字列を ImprovementSuggestion に変換
  → AiImprovementService._save()          outputs/ai_improvements/ へJSON保存
```

`AiImprovementService` はこの一連の処理を統合する役割のみを持ち、各ステップの実処理（プロンプト生成・API通信・解析）は行わない（Single Responsibility）。

---

## 7. Data Model

### `ImprovementSuggestion`（`improvement_suggestion.py`）

| フィールド | 型 | 内容 |
|---|---|---|
| `article_id` | `str` | 記事識別子（slug） |
| `title` | `str` | 記事SEOタイトル |
| `permalink` | `str \| None` | WordPress公開URL |
| `prompt_version` | `str` | 使用したプロンプトバージョン |
| `summary` | `str` | 改善提案の要約 |
| `priority` | `str` | 優先度（`high` / `medium` / `low`） |
| `issues` | `list[str]` | 検出された問題点 |
| `suggestions` | `list[str]` | 改善提案 |
| `seo_title_suggestion` | `str \| None` | SEOタイトル改善案 |
| `meta_description_suggestion` | `str \| None` | メタディスクリプション改善案 |
| `internal_link_suggestions` | `list[str]` | 内部リンク提案（Release 2.0向けの拡張フィールド） |
| `raw_response` | `str` | Claudeの生レスポンス（デバッグ用） |
| `created_at` | `datetime` | 生成日時 |

`empty()` クラスメソッドで、失敗時・無効時に返す空のSuggestionを生成できる（`priority="low"`、他は空リスト）。

### JSON Lines 出力例

`outputs/ai_improvements/20260630_sample-article-20260630_improvement.json` に、`to_dict()` の内容がインデント付きJSONで保存される。

---

## 8. Directory Structure

```
src/ai/
├── __init__.py                      # 公開API（v1.14.0〜v2.0.0まで累積）
├── ai_improvement_config.py         # AiImprovementConfig
├── claude_client.py                 # ClaudeClient / NullClaudeClient
├── prompt_builder.py                # PromptBuilder
├── improvement_suggestion.py        # ImprovementSuggestion
├── improvement_suggestion_parser.py # ImprovementSuggestionParser
├── ai_improvement_service.py        # AiImprovementService / NullAiImprovementService
└── prompts/
    └── v1_improvement.py            # プロンプトテンプレート（v1）

scripts/
└── run_ai_improvement.py            # バッチ実行スクリプト

outputs/
└── ai_improvements/                 # 改善提案JSONの保存先
```

---

## 9. Module Design

### `AiImprovementConfig`（`ai_improvement_config.py`）

環境変数から設定値のみを読み込むdataclass。`is_ready()` は `enabled and bool(api_key)` を返す。

| フィールド | デフォルト |
|---|---|
| `enabled` | `False` |
| `model` | `"claude-sonnet-4-6"` |
| `prompt_version` | `"v1"` |
| `max_articles` | `10` |
| `output_dir` | `"outputs/ai_improvements"` |
| `timeout_seconds` | `60` |

### `ClaudeClient` / `NullClaudeClient`（`claude_client.py`）

- `send(prompt) -> str`：Claude APIにプロンプトを送信し、応答テキストを返す。例外発生時は `[AI WARNING]` を出力して空文字列を返す（呼び出し元を止めない）
- `NullClaudeClient`：`is_available()=False`、`send()`は常に空文字列（APIキー未設定・機能無効時）
- テスト容易性のため、`client` オブジェクトを外部から注入可能（mock差し替え用）

### `AiImprovementService` / `NullAiImprovementService`（`ai_improvement_service.py`）

- `improve(ai_input)`：1件のAiInputRecordから改善提案を生成・保存する。失敗時は空のSuggestionを返して処理継続
- `improve_batch(ai_inputs, performance_only=True, max_articles=None)`：複数件をまとめて処理。`performance_only=True`なら`has_performance_data=True`の記事のみ対象。件数上限は`max_articles`（未指定時はConfigの値）
- `_save()`：保存失敗（`OSError`）時も `[AI WARNING]` を出力して処理継続（例外を伝播させない）

---

## 10. Configuration Design

`.env.example` への追記内容（v1.14.0時点）：

```
AI_IMPROVEMENT_ENABLED=false
# AI_IMPROVEMENT_MODEL=claude-sonnet-4-6
# AI_IMPROVEMENT_PROMPT_VERSION=v1
# AI_IMPROVEMENT_MAX_ARTICLES=10
# AI_IMPROVEMENT_OUTPUT_DIR=outputs/ai_improvements
# AI_TIMEOUT_SECONDS=60
```

`ANTHROPIC_API_KEY` は既存の必須設定（ファイル冒頭）をそのまま利用する。

### Configuration First の設計意図

`AI_IMPROVEMENT_ENABLED=false`（デフォルト）または`ANTHROPIC_API_KEY`未設定の場合、`AiImprovementService.from_env()` は `NullAiImprovementService` を返す。呼び出し側（`scripts/run_ai_improvement.py`）は分岐を書かずに同じインターフェースで呼び出せる（Null Object Pattern）。

---

## 11. Analytics Foundation との関係

- 入力：`AiInputRecord`（`src/analytics/analytics_entry.py`、v1.10.0で定義）
- `AiImprovementService` は `AiInputRecord` の生成方法（Search Console/GA4連携）には関知しない。責務はプロンプト生成〜提案保存のみ

---

## 12. Error Handling

| ケース | 対応 |
|---|---|
| Claude API呼び出し失敗 | `[AI WARNING]` 出力、空文字列を返す（`ClaudeClient`側） |
| JSON解析失敗 | `ImprovementSuggestionParser`が失敗を検知し、`empty()` のSuggestionにフォールバック |
| ファイル保存失敗（`OSError`） | `[AI WARNING]` 出力、処理は継続（提案自体は呼び出し元に返る） |
| `AI_IMPROVEMENT_ENABLED=false` | `NullAiImprovementService`が終始no-opで動作し、例外を発生させない |

いずれのケースでもシステム全体（バッチ処理）を停止させないことを優先する。

---

## 13. AI Rewrite Foundation との関係（v1.16.0への引き継ぎ）

`AiImprovementService.improve()` が返す `ImprovementSuggestion` は、v1.16.0 `RewriteService` の入力として使われる。
`internal_link_suggestions` フィールドはv1.14.0時点では未使用で、Release 2.0以降の拡張ポイントとして予約されている。

---

## 14. Future Extensions

- Phase 2：`ImprovementReviewService`によるレポート化（v1.15.0で実装済み）
- Phase 3：改善提案を元にした自動リライト（v1.16.0で実装済み）
- Phase 4：`internal_link_suggestions` を実際に活用した内部リンク自動提案（Release 2.0以降、未着手）
- Phase 5：Agent層（v2.0.0）による「改善提案を生成すべきか」の自動判断（未着手）

---

## 15. Definition of Done

### コード

- [x] `src/ai/` パッケージ一式の実装
- [x] Configuration First（`NullAiImprovementService`）の実装

### テスト

- [x] `tests/test_e2e_v1_14_0_ai_improvement_foundation.py`: 74/74 PASS

### ドキュメント

- [x] 本設計書（v2.1.0にて事後作成）
- [x] CHANGELOG.md / ROADMAP.md への記載

### リリース

- [x] 2026-06-30 コミット済み（`73e2bfd`）
