# 出力アーキテクチャ設計

作成日：2026-06-26  
更新日：2026-07-02（v2.7.0 — Workflow Engine層を追記。Scheduler → Workflow Engine → NewsAgent → ReviewTriggerAgent → PublishTriggerAgentの関係、既存Agentの独立性を維持したまま上位オーケストレーション層を追加した設計判断を明記）  
更新日：2026-07-02（v2.6.0 — Scheduler層を追記。v2.6.0リリース時に未実施だった本追記を、v2.7.0ドキュメント整備時にあわせて実施。`docs/CHANGELOG.md` [KI-2]参照）  
更新日：2026-07-02（v2.5.0 — ReviewTriggerAgent → ReviewPipelineRunner → AiPublishReviewService の関係を追記。ReviewTriggerAgentのみ二重ゲートである理由を明記）  
更新日：2026-07-02（v2.4.0 — PublishTriggerAgent → PublishPipelineRunner → AiPublishService の関係を追記。v2.4.0リリース時に未実施だった本追記を、v2.5.0ドキュメント整備時にあわせて実施）  
更新日：2026-07-02（v2.3.0 — WorkflowTriggerAgent → WorkflowPipelineRunner → WorkflowRunner の関係を追記。Agent → Pipeline → Runner パターンをRelease 2.x標準アーキテクチャとして整理）  
更新日：2026-07-01（v2.2.0 — Pipeline層（実行層）を追記。News Agent → NewsPipelineRunner → main.py の関係を明記）  
更新日：2026-07-01（v2.1.0 — Workflow層・Agent層を追記。全体像を「出力アーキテクチャ」から「アプリケーション全体アーキテクチャ」へ拡張）

> 本ドキュメントは元々「出力アーキテクチャ（`OutputManager`まわり）」のみを扱っていましたが、
> v1.14.0〜v2.0.0でAI系の層（Workflow層・Agent層）が追加されたため、
> 全体像を俯瞰できるよう章を追加しました。
> 各バージョンの詳細な設計意図は `docs/design/` 配下の個別設計書を参照してください。

---

## 背景・目的

v1.0 では `main.py` に `_save_as_markdown()` が直書きされており、
出力先を追加するたびに `main.py` を修正する必要があった。

WordPress REST API 連携（v1.x）を追加するにあたり、
「どこへ出力するか」を差し替えやすい構造へ変更する。

---

## 現在（v1.0）の構造

```
main.py
  └─ _save_as_markdown()  ← Markdownへの保存処理が直書き
```

---

## 変更後（v1.1〜）の構造

```
main.py
  └─ output_manager.save_all(article)
       └─ OutputManager
            ├─ MarkdownOutput     ← v1.1 実装済み
            ├─ WordPressOutput    ← v1.1 実装済み
            ├─ NotionOutput       ← 将来
            └─ DiscordOutput      ← 将来
```

`main.py` は「何を出力するか（ArticleData）」だけを知り、
「どこへ出力するか」は `OutputManager` に委ねる。

---

## ディレクトリ構成

```
src/
├── image_extractor.py       # RSSエントリーから画像URL候補を抽出（v1.3 追加）
├── image_resolver.py        # アイキャッチ画像候補URLを解決（v1.4 追加）
├── slug_generator.py        # WordPress slug を生成（v1.5 追加）
├── publishing_config.py     # PublishStatus Enum・PublishingConfig dataclass（v1.7 追加）
└── outputs/
    ├── __init__.py          # OutputManager, MarkdownOutput, ArticleData を公開
    ├── base.py              # ArticleData dataclass / BaseOutput 抽象クラス
    ├── manager.py           # OutputManager
    ├── markdown_output.py   # MarkdownOutput（実装済み）
    ├── taxonomy_config.py   # カテゴリ・タグIDの設定（v1.2 追加）
    └── wordpress_output.py  # WordPressOutput（v1.1 実装済み）
```

---

## 各クラスの責務

### ImageResolver（`image_resolver.py`）（v1.4 追加）

アイキャッチ画像候補URLと WordPress media_id を解決するモジュール。

| 関数 | 役割 |
|------|------|
| `resolve_featured_image(item)` | NewsItem から使用する画像URLを1件選んで返す（Markdown記録用） |
| `resolve_media_id(item, default_media_id)` | WordPress に設定する featured_media の ID を返す（v1.6 追加） |

`resolve_media_id()` は v1.6.0 では `image_terms_confirmed == False` のため常に `default_media_id` を返す。v1.7.0 以降で `True` の場合に `MediaUploader` 経由でアップロード結果の ID を返す拡張ポイントとして設計。

### ArticleData（`base.py`）

記事生成結果をまとめて出力処理に渡すデータクラス。

| フィールド | 型 | 内容 |
|-----------|-----|------|
| `item` | `NewsItem` | 元ニュース情報（タイトル・URL・ソース等） |
| `importance` | `str` | 重要度（S / A / B） |
| `seo_title` | `str` | AIが生成したSEOタイトル |
| `article_body` | `str` | AIが生成した記事本文 |
| `x_post` | `str` | AIが生成したX投稿文 |
| `featured_image_url` | `str` | アイキャッチ画像候補URL（v1.3 追加、空文字 = なし） |
| `excerpt` | `str` | WordPress抜粋・Markdown記録用（v1.4 追加、空文字 = なし） |
| `meta_description` | `str` | 将来のSEOプラグイン連携用（v1.4 追加、現在はexcerptと同値） |
| `slug` | `str` | WordPress slug（v1.5 追加、空文字 = なし） |
| `featured_media_id` | `int` | WordPress media_id（v1.6 追加、0 = アイキャッチなし） |
| `publish_status` | `PublishStatus` | WordPress 投稿ステータス（v1.7 追加、デフォルト = DRAFT） |

### BaseOutput（`base.py`）

全出力クラスの抽象基底クラス。

| メソッド | 返り値 | 役割 |
|---------|-------|------|
| `save(article)` | `str` | 記事を保存・投稿する。保存先を示す文字列を返す |
| `is_available()` | `bool` | この出力先が利用可能かを返す（APIキー不足などを検知） |

### MarkdownOutput（`markdown_output.py`）

`output/` フォルダへのMarkdownファイル保存を担う。
v1.0 の `_save_as_markdown()` をクラスとして移植したもの。
`is_available()` は常に `True`（ディスク書き込みは常に可能とみなす）。

### OutputManager（`manager.py`）

複数の `BaseOutput` を受け取り、`save_all()` で全出力先に一括保存する。

- 1つの出力先が失敗しても他の出力先への保存は続行する
- `is_available()` が `False` の出力先はスキップする
- 保存に成功した保存先文字列のリストを返す

---

## main.py からの呼び出し

```python
# 起動時に1回だけ初期化
output_manager = OutputManager(outputs=[
    MarkdownOutput(output_dir=OUTPUT_DIR),
    WordPressOutput.from_env(),  # .env 未設定時は is_available()=False で自動スキップ
])

# 記事生成後の保存（v1.6.0 以降）
excerpt            = _extract_excerpt(article_body)            # ルールベース・API追加なし
featured_image_url = resolve_featured_image(item)              # Markdown記録用URL（v1.4 追加）
featured_media_id  = resolve_media_id(item, default_media_id)  # WordPress media_id（v1.6 追加）
article = ArticleData(
    item=item,
    importance=importance,
    seo_title=seo_title,
    article_body=article_body,
    x_post=x_post,
    featured_image_url=featured_image_url,
    excerpt=excerpt,
    meta_description=excerpt,    # v1.4.0 では excerpt と同値
    slug=slug,                   # v1.5 追加
    featured_media_id=featured_media_id,  # v1.6 追加
)
destinations = output_manager.save_all(article)
```

---

## 将来の拡張手順

新しい出力先（Notion・Discord など）を追加する場合：

1. `src/outputs/` に新しいクラスファイルを作成し `BaseOutput` を継承する
2. `save()` と `is_available()` を実装する
3. `src/outputs/__init__.py` でエクスポートする
4. `main.py` の `OutputManager([...])` に追加する

**既存ファイルへの変更は最小限（main.py の1行追加のみ）。**

---

## 全体構成（v2.5.0 時点）

`main.py`（投稿処理）とは別に、`src/ai/` 配下に投稿後の改善サイクルおよび判断層が、
`src/pipeline/` 配下に実行層が育っている。いずれも独立して実行され、`main.py` は
Workflow層・Agent層・Pipeline層を呼び出さない（呼ばれる側に徹する）。

```
main.py（記事収集・投稿）
  └─ output_manager.save_all(article)   ← 本ドキュメント前半の「出力アーキテクチャ」

scripts/run_news_agent.py（ニュース収集の実行要否判断・main.pyとは独立実行）
  └─ AgentManager（判断）
       └─ NewsAgent                     ← Agent層（v2.2.0、判断のみ）
            └─ NewsPipelineRunner       ← Pipeline層（v2.2.0、実行のみ）
                 └─ main.py（subprocess起動。無改修）

scripts/run_workflow_trigger_agent.py（Workflowの実行要否判断・main.pyとは独立実行）
  └─ AgentManager（判断）
       └─ WorkflowTriggerAgent          ← Agent層（v2.3.0、判断のみ）
            └─ WorkflowPipelineRunner   ← Pipeline層（v2.3.0、実行のみ。subprocessは使わない）
                 └─ WorkflowRunner（直接呼び出し。無改修）
                      └─ WorkflowStepExecutor × 6（下記と同一の6ステップ）

scripts/run_publish_trigger_agent.py（Publishの実行要否判断・main.pyとは独立実行）
  └─ AgentManager（判断）
       └─ PublishTriggerAgent           ← Agent層（v2.4.0、判断のみ）
            └─ PublishPipelineRunner    ← Pipeline層（v2.4.0、実行のみ。subprocessは使わない）
                 └─ AiPublishService（直接呼び出し。無改修）

scripts/run_review_trigger_agent.py（公開前レビューレポート生成の実行要否判断・main.pyとは独立実行）
  └─ AgentManager（判断）
       └─ ReviewTriggerAgent            ← Agent層（v2.5.0、判断のみ、二重ゲート）
            └─ ReviewPipelineRunner     ← Pipeline層（v2.5.0、実行のみ。subprocessは使わない）
                 └─ AiPublishReviewService（直接呼び出し。無改修）

scripts/run_ai_workflow.py（投稿後の改善サイクルの手動一括実行・main.pyとは独立実行）
  └─ WorkflowRunner（実行）              ← Workflow層（v1.20.0）。Agent層を経由しない直接実行
       └─ WorkflowStepExecutor × 6
            ├─ Improvement       （v1.14.0 AiImprovementService）
            ├─ ImprovementReview （v1.15.0 ImprovementReviewService）
            ├─ Rewrite           （v1.16.0 RewriteService）
            ├─ RewriteReview     （v1.17.0 RewriteReviewService）
            ├─ Publish           （v1.18.0 AiPublishService）
            └─ PublishReview     （v1.19.0 AiPublishReviewService）
```

`scripts/run_ai_workflow.py`（人間が手動で一括実行）と`scripts/run_workflow_trigger_agent.py`（Agentが実行要否を判断してから実行）は、どちらも最終的に同じ`WorkflowRunner`・同じ6ステップへたどり着くが、**経路が異なる**（前者はAgent層を経由しない直接実行、後者はAgent層＋Pipeline層を経由する）。

各層の役割：

| 層 | 実装 | 責務 |
|---|---|---|
| Agent層 | `AgentManager` / `AgentExecutor` / `BaseAgent` | 「今、何かを実行すべきか」を**判断**する。実行そのものは行わない |
| Pipeline層 | `NewsPipelineRunner` / `WorkflowPipelineRunner` / `PublishPipelineRunner` / `ReviewPipelineRunner` / `PipelineResult` | Agent層から渡されたタスクを実際に**実行**する。Agent層には依存しない |
| Workflow層 | `WorkflowRunner` / `WorkflowStepExecutor` | 決まった6ステップを、決まった順序で**実行**する |
| Service層 | `AiImprovementService` 等 | 各ステップの実処理（Claude API呼び出し・WordPress投稿・レポート生成） |

詳細は次項および各 `docs/design/*.md` を参照。

---

## Workflow層（`src/ai/workflow_*.py`、v1.20.0 追加）

`WorkflowRunner` は、v1.14.0〜v1.19.0で個別に実装した6つのServiceを、決まった順序で呼び出すオーケストレーター。

- `WorkflowStep` Enum：`IMPROVEMENT` → `IMPROVEMENT_REVIEW` → `REWRITE` → `REWRITE_REVIEW` → `PUBLISH` → `PUBLISH_REVIEW`
- `WorkflowRunner` は各Serviceを直接importしない。`WorkflowStepExecutor`（ステップごとのラッパー）をコンストラクタでDIすることで、Workflow層とService層の責務を分離している
- `AI_WORKFLOW_ENABLED=false` の場合は `NullWorkflowRunner` を返す（Configuration First）
- 実行結果は `WorkflowResult`（`overall_success` / `total_processed` / `steps` / `warnings`）にまとめられ、`WorkflowReportBuilder` がMarkdownレポートを生成する

詳細設計：`docs/design/ai_workflow_foundation.md`

---

## Agent層（`src/ai/agent_*.py`、v2.0.0 追加）

`AgentManager` は、Workflow層のさらに上位に位置する「判断」レイヤー。

- **Workflowを置き換えるものではない**。「今、Workflowを実行すべきかどうか」を判断する上位概念として設計されている
- `BaseAgent`（ABC）は `decide()`（判断のみ・副作用なし）と `act()`（`should_act=True`かつ`dry_run=False`の場合のみ呼ばれる実行）に責務を分離
- `AgentExecutor` が `decide()` → `act()` の呼び出し順序・`dry_run`判定・実行時刻の計測を一括管理する（`BaseAgent`実装側はこれらを意識しなくてよい）
- `AgentManager.run()` はタスクごとに新しい `run_id` を発行し、登録された `AgentExecutor` に実行させ、`AgentResult` のリストを返す
- v2.0.0時点では `BaseAgent` の具体的な実装（News Agent等）はまだ存在せず、`AgentManager.from_config()` は `is_ready()=True` でも `executors=[]`（空リスト）を返す。**次の具体的なAgent実装（News Agent / Workflow Trigger Agent）を追加するための骨組みのみが完成した状態**
- v2.5.0時点では `NewsAgent`（v2.2.0）・`WorkflowTriggerAgent`（v2.3.0）・`PublishTriggerAgent`（v2.4.0）・`ReviewTriggerAgent`（v2.5.0）の4つの具体的なAgent実装が揃っている（後述「Agent → Pipeline → Runner パターン」参照）
- デフォルトは無効（`AI_AGENT_ENABLED=false`）。既存の `WorkflowRunner` 経由の自動実行フローには影響しない

詳細設計：`docs/design/agent_foundation.md`

### 新しいAgentを追加する場合（将来手順）

1. `src/ai/` に `BaseAgent` を継承した新しいAgentクラスを作成し、`decide()` / `act()` / `name()` を実装する
2. `AgentManager.from_config()` 内で、新しいAgentを包んだ `AgentExecutor` を `executors` リストに追加する（DI）
3. 必要であれば `AgentConfig` に判断材料となる設定値を追加する

**Workflow層・Service層への変更は不要（Agent層はWorkflowを呼び出す側であり、呼び出される側ではない）。**

---

## Pipeline層（`src/pipeline/`、v2.2.0 / v2.3.0 / v2.4.0 / v2.5.0 追加）

対応するAgentが「実行すべき」と判断した後、実際の処理を担う実行層。設計レビューの結果、
「Agentが実行手段（subprocess等）を直接扱う」設計は責務混同を招くと判断され、Agent層とは別パッケージとして分離した。

### NewsPipelineRunner（`src/pipeline/news_pipeline_runner.py`、v2.2.0 追加）

- **Agent＝判断、PipelineRunner＝実行**：`NewsAgent`は`NewsPipelineRunner.run(params) -> PipelineResult`という薄いインターフェースのみを呼び、実行方式（subprocess／将来的なimport呼び出し／API呼び出し等）を一切知らない
- `NewsPipelineRunner`は`main.py`をsubprocessとして起動する。`main.py`本体は無改修（`argparse`が`sys.argv`を読む・複数箇所で`sys.exit()`を呼ぶという既存の実装特性上、直接importして呼び出すとAgentプロセスごと道連れにするリスクがあるため、プロセスとして隔離している）

```
NewsAgent（判断）
  └─ NewsPipelineRunner.run(params)（実行）
       └─ subprocess.run([python_executable, main_py_path], cwd=working_directory, timeout=timeout_sec)
            └─ main.py（無改修。既存のニュース収集パイプラインをそのまま実行）
```

詳細設計：`docs/design/news_agent_foundation.md`

### WorkflowPipelineRunner（`src/pipeline/workflow_pipeline_runner.py`、v2.3.0 追加）

- **Agent＝判断、PipelineRunner＝実行**：`WorkflowTriggerAgent`は`WorkflowPipelineRunner.run(params) -> PipelineResult`という薄いインターフェースのみを呼び、`WorkflowRunner`のクラス名・呼び出しシグネチャを一切知らない
- `WorkflowPipelineRunner`は`WorkflowRunner.run()`を**直接呼び出す**（subprocessは使わない）。`WorkflowRunner`は通常のPythonクラスであり、`main.py`のような`argparse`/`sys.exit()`問題を持たないため、プロセス分離が不要と判断された（`NewsPipelineRunner`との実行方式の違いは、実行対象それぞれの実装特性に起因するものであり、Pipeline層の設計原則自体の違いではない）
- `ai`パッケージのimportは`run()`メソッド内に遅延させている。これにより`src/pipeline/`が`src/ai/`をimportする形になっても、`pipeline → ai → pipeline`という循環importを構造的に回避している

```
WorkflowTriggerAgent（判断）
  └─ WorkflowPipelineRunner.run(params)（実行）
       └─ WorkflowRunner.from_config(...).run(article_id=..., dry_run=...)（直接呼び出し。無改修）
            └─ WorkflowStepExecutor × 6（Improvement〜PublishReview）
```

詳細設計：`docs/design/workflow_trigger_agent_foundation.md`

### PublishPipelineRunner（`src/pipeline/publish_pipeline_runner.py`、v2.4.0 追加）

- **Agent＝判断、PipelineRunner＝実行**：`PublishTriggerAgent`は`PublishPipelineRunner.run(params) -> PipelineResult`という薄いインターフェースのみを呼び、`AiPublishService`のクラス名・呼び出しシグネチャを一切知らない
- `PublishPipelineRunner`は`AiPublishService.run()`を**直接呼び出す**（subprocessは使わない）。`WorkflowPipelineRunner`と同じ理由（`AiPublishService`が通常のPythonクラスであり`argparse`/`sys.exit()`問題を持たないため）
- `ai`パッケージのimportは`run()`メソッド内に遅延させ、`pipeline → ai → pipeline`という循環importを構造的に回避している

```
PublishTriggerAgent（判断）
  └─ PublishPipelineRunner.run(params)（実行）
       └─ AiPublishService.from_env(base_dir=...).run(article_id=...)（直接呼び出し。無改修）
```

詳細設計：`docs/design/publish_trigger_agent_foundation.md`

### ReviewPipelineRunner（`src/pipeline/review_pipeline_runner.py`、v2.5.0 追加）

- **Agent＝判断、PipelineRunner＝実行**：`ReviewTriggerAgent`は`ReviewPipelineRunner.run(params) -> PipelineResult`という薄いインターフェースのみを呼び、`AiPublishReviewService`のクラス名・呼び出しシグネチャを一切知らない
- `ReviewPipelineRunner`は`AiPublishReviewService.run()`を**直接呼び出す**（subprocessは使わない）。`PublishPipelineRunner`と同じ理由
- `ai`パッケージのimportは`run()`メソッド内に遅延させ、`pipeline → ai → pipeline`という循環importを構造的に回避している

```
ReviewTriggerAgent（判断）
  └─ ReviewPipelineRunner.run(params)（実行）
       └─ AiPublishReviewService.from_paths(base_dir=...).run(article_id=...)（直接呼び出し。無改修）
```

詳細設計：`docs/design/review_trigger_agent_foundation.md`

### 全Runnerに共通する設計原則

- **Pipeline層はAgent層に依存しない**：`src/pipeline/`配下のモジュールは`AgentContext` / `AgentDecision` / `AgentResult`等のAgent層の型を一切importしない。設定値の受け渡しは`Protocol`によるダックタイピングで行う
- 実行結果は共通の`PipelineResult`（`success` / `returncode` / `elapsed_sec` / `stdout_log_path` / `stderr_log_path` / `error_message`）にまとめられ、各Agentがこれを`AgentResult`へ変換する（`workflow_result`は常に`None`）
- `dry_run=True`の場合、`AgentExecutor`（v2.0.0の既存設計）により`act()`自体が呼ばれないため、PipelineRunnerの`run()`は構造的に発生しない（`NewsAgent` / `WorkflowTriggerAgent` / `PublishTriggerAgent` / `ReviewTriggerAgent`共通の保証）
- **`NewsAgent`系・`WorkflowTriggerAgent`系・`PublishTriggerAgent`系・`ReviewTriggerAgent`系は互いに独立したPipelineを持つ**：`NewsPipelineRunner` / `WorkflowPipelineRunner` / `PublishPipelineRunner` / `ReviewPipelineRunner`は互いをimportせず、依存関係を持たない

### 新しいPipelineRunnerを追加する場合（将来手順）

将来のScheduler Agent等も、同じ形の実行層を追加していく想定。

1. `src/pipeline/` に新しいRunnerクラスを作成し、`run(params) -> PipelineResult`を実装する
2. 対応するAgentの`act()`から、そのRunnerの`run()`のみを呼ぶ
3. 共通インターフェース（`Protocol`/ABC）への抽出は、v2.5.0時点で4実装（`NewsPipelineRunner` / `WorkflowPipelineRunner` / `PublishPipelineRunner` / `ReviewPipelineRunner`）が揃った後も引き続き見送っている（各design docのFuture Extensions参照。抽象化の必要性が具体的に生じた時点で再検討する）

**Agent層への変更は不要（Pipeline層はAgentから呼ばれる側であり、Agent層の型を知る必要がない）。**

---

## Agent → Pipeline → Runner パターン（Release 2.x 標準アーキテクチャ）

v2.2.0（News Agent Foundation）・v2.3.0（Workflow Trigger Agent Foundation）・v2.4.0（Publish Trigger Agent Foundation）・v2.5.0（Review Trigger Agent Foundation）を通じて、以下の3層パターンがRelease 2.x系のAgent実装における標準アーキテクチャとして確立した。

```
[判断] BaseAgent実装（decide() / act()）
   ↓
[実行] PipelineRunner実装（run(params) -> PipelineResult）
   ↓
[対象] 既存の資産（main.py / WorkflowRunner / AiPublishService / AiPublishReviewService等、無改修のまま呼び出される）
```

| Agent（判断） | Pipeline層（実行） | 実行対象 | 実行方式 |
|---|---|---|---|
| `NewsAgent`（v2.2.0） | `NewsPipelineRunner` | `main.py` | subprocess起動（`argparse`/`sys.exit()`問題を隔離するため） |
| `WorkflowTriggerAgent`（v2.3.0） | `WorkflowPipelineRunner` | `WorkflowRunner` | 直接呼び出し（`WorkflowRunner`にsubprocess化が必要な問題がないため） |
| `PublishTriggerAgent`（v2.4.0） | `PublishPipelineRunner` | `AiPublishService` | 直接呼び出し（`AiPublishService`にsubprocess化が必要な問題がないため） |
| `ReviewTriggerAgent`（v2.5.0） | `ReviewPipelineRunner` | `AiPublishReviewService` | 直接呼び出し（`AiPublishReviewService`にsubprocess化が必要な問題がないため） |

このパターンに共通する設計原則：

1. Agentは「判断」のみを行い、副作用（実際の起動）を持たない（`decide()`は読み取り専用）
2. Agentは実行対象（`main.py` / `WorkflowRunner` / `AiPublishService` / `AiPublishReviewService`）を直接importしない。実行方式はPipelineRunnerに完全に閉じ込める
3. PipelineRunnerはAgent層の型（`AgentContext`等）をimportしない（`ai → pipeline`の一方向依存が原則。ただし`WorkflowPipelineRunner` / `PublishPipelineRunner` / `ReviewPipelineRunner`のように実行対象自体が`ai`パッケージ内にある場合は、遅延importにより循環を避けたうえでこれを呼び出すことが許容される）
4. PipelineRunnerの実行方式（subprocessか直接呼び出しか）は、実行対象の実装特性（`sys.exit()`の有無等）によって決まる。パターン自体は変わらない
5. **各Agent系は互いに独立したPipelineを持つ**（`NewsAgent`系・`WorkflowTriggerAgent`系・`PublishTriggerAgent`系・`ReviewTriggerAgent`系）。`AgentManager`の`executors`リストにそれぞれ独立したエントリとして並び、実行層同士が依存し合うことはない
6. `dry_run=True`の場合、`AgentExecutor`の既存保証により`act()`自体が呼ばれないため、PipelineRunnerの`run()`は構造的に発生しない

### Gate方式のバリエーション

対象Serviceの性質に応じて、DI時のゲート段数が異なる。

| Agent | Gate方式 | 内訳 |
|---|---|---|
| `NewsAgent`（v2.2.0） | 単一ゲート | `AI_AGENT_ENABLED`のみ（`main.py`自体に独立した有効/無効フラグがないため） |
| `WorkflowTriggerAgent`（v2.3.0） | 三重ゲート | `AI_AGENT_ENABLED` × `WORKFLOW_TRIGGER_AGENT_ENABLED` × `AI_WORKFLOW_ENABLED`（`WorkflowConfig.is_ready()`を再利用） |
| `PublishTriggerAgent`（v2.4.0） | 三重ゲート | `AI_AGENT_ENABLED` × `PUBLISH_TRIGGER_AGENT_ENABLED` × `AiPublishConfig.is_ready()`（`AI_PUBLISH_ENABLED`＋WordPress認証情報3点） |
| `ReviewTriggerAgent`（v2.5.0） | **二重ゲート** | `AI_AGENT_ENABLED` × `REVIEW_TRIGGER_AGENT_ENABLED`のみ |

**`ReviewTriggerAgent`のみ二重ゲートである理由**：

- 対象の`AiPublishReviewService`（v1.19.0）には、`WorkflowConfig` / `AiPublishConfig`のような独自の`Config`クラス・`is_ready()`相当の判定が**存在しない**ため、3段目として再利用できる既存の判定がない
- 3段目を実現するために`AiPublishReviewService`側へ`Config`を後付けすることは、対象Service本体の改修になり「既存Service本体は改修しない」という方針に反するため行わない
- そのため`AI_AGENT_ENABLED` × `REVIEW_TRIGGER_AGENT_ENABLED`の二重ゲートで確定し、デフォルト無効（`REVIEW_TRIGGER_AGENT_ENABLED=false`）という安全側の初期状態は維持している

詳細は`docs/design/review_trigger_agent_charter.md`（Open Question #1）・`docs/design/review_trigger_agent_foundation.md` §6を参照。

将来のScheduler Agent（Windowsタスクスケジューラ統合）も同じパターンで追加していく想定。詳細は`docs/design/news_agent_foundation.md` §16、`docs/design/workflow_trigger_agent_foundation.md` §16、`docs/design/publish_trigger_agent_foundation.md` §16、`docs/design/review_trigger_agent_foundation.md` §16（各Future Extensions）を参照。

---

## Scheduler層（`src/scheduler/`、v2.6.0 追加）

> このセクションはcommit `0d28d30`時点で本ドキュメントへの追記が漏れていたため、v2.7.0ドキュメント整備作業（2026-07-02）で遡及的に追加したものです（`docs/CHANGELOG.md` [KI-2]参照）。

`src/scheduler/`は、「いつ実行すべきか」を判定するだけの独立パッケージ。`SchedulerEngine.evaluate(jobs, now)`は副作用のない純粋関数で、登録された`SchedulerJob`一覧と現在時刻から、実行対象と判定された`SchedulerJob`ごとに`SchedulerEvent`を生成して返す。

```
SchedulerJob（登録） → SchedulerManager（管理） → SchedulerRepository（保持、v2.6.0はInMemoryのみ）
    → SchedulerEngine.evaluate(jobs, now)（判定） → SchedulerEvent（生成）
```

- **Event Driven Architectureの原則**：Schedulerは`NewsAgent` / `ReviewTriggerAgent` / `PublishTriggerAgent`等の既存Trigger Agentを一切importせず、直接呼び出すこともしない。`SchedulerEvent`を生成するところで責務が終わる。「判断」と「実行」の分離を、`src/ai/` / `src/pipeline/`への依存を一切持たないパッケージ構成そのもので体現している
- v2.6.0時点では`SchedulerEvent`を受け取って実際にAgentを起動する呼び出し元が存在しなかった（Foundation Releaseのため、判定エンジンの骨組みのみ）。この接続は次項のWorkflow Engine層（v2.7.0）で実装された
- デフォルトは無効（`SCHEDULER_ENABLED=false`）
- Foundation Releaseのため、cron完全互換ではない（`TriggerType`はDAILY / INTERVAL / ONCEの3種類のみ、分単位マッチング）。永続化（`InMemorySchedulerRepository`のみ）・retry・`last_run_at`保持・Windows Task Scheduler / Linux cron連携はいずれも対象外（将来Releaseの拡張候補）

---

## Workflow Engine層（`src/workflow_engine/`、v2.7.0 追加）

Scheduler（v2.6.0）が生成する`SchedulerEvent`を起点に、既存3つのTrigger Agent（`NewsAgent` v2.2.0 → `ReviewTriggerAgent` v2.5.0 → `PublishTriggerAgent` v2.4.0）を決まった順序で実行する、Agent層のさらに上位に位置するオーケストレーション層。

```
Scheduler            （判断：今このJobを実行すべきか、v2.6.0、無改修）
   ↓ SchedulerEvent
Workflow Engine        （実行：登録されたステップを順序どおりに実行する、v2.7.0）
   ↓
NewsAgent             （既存、v2.2.0、無改修）
   ↓
ReviewTriggerAgent    （既存、v2.5.0、無改修）
   ↓
PublishTriggerAgent   （既存、v2.4.0、無改修）
```

### 既存Agentの独立性を維持していること

v2.2.0〜v2.5.0で確立した「各Agent系は互いに独立したPipelineを持つ」という原則（上記「Agent → Pipeline → Runner パターン」参照）は、Workflow Engineの追加によって破棄されていない。

- `WorkflowEngineManager`は`AgentManager`（v2.0.0）を経由せず、既存の`NewsAgent` / `ReviewTriggerAgent` / `PublishTriggerAgent`とそれぞれの`Config` / `PipelineRunner`を無改修のままimportし、独自にインスタンスを構築する（`docs/design/workflow_engine_foundation.md` 8.2節「案B」）
- `AgentManager` / `AgentExecutor` / `BaseAgent` / 既存4 Trigger Agent・Scheduler本体はいずれも無改修。`scripts/run_news_agent.py`等、`AgentManager`を経由する既存の個別実行経路は従来どおり利用できる
- Workflow Engineは「独立したAgent群」という既存モデルの**上に**「決まった順序で呼び出す」層を追加したものであり、置き換えではない

### 名前空間の分離

`src/workflow_engine/`のクラスはすべて`WorkflowEngine`接頭辞を持ち、`src/ai/workflow_*.py`（v1.20.0、AI記事改善6ステップ用の`WorkflowStep` / `WorkflowContext` / `WorkflowResult`等）とはパッケージ・クラス名の両方で分離されている（`WorkflowEngineStep` vs `WorkflowStep`等）。両者は対象が異なる別物であり、混同しないこと。

### Gate二層構造

| 層 | ゲート |
|---|---|
| Workflow Engine全体（二重ゲート） | `AI_AGENT_ENABLED`（`AgentConfig.is_ready()`） × `WORKFLOW_ENGINE_ENABLED`（`WorkflowEngineConfig.is_ready()`） |
| NEWSステップ | 常に有効（`NewsAgentConfig`にゲートが存在しないため） |
| REVIEWステップ | `ReviewTriggerAgentConfig.is_ready()`（`REVIEW_TRIGGER_AGENT_ENABLED`）を再利用 |
| PUBLISHステップ | `PublishTriggerAgentConfig.is_ready()`（`PUBLISH_TRIGGER_AGENT_ENABLED` × `AiPublishConfig.is_ready()`）を再利用 |

ステップ別ゲートが閉じている場合、そのステップは`WorkflowEngineExecutor`側で「スキップ」（`success=True`）として扱われ、後続ステップの実行は継続する。

### 打ち切り基準

「実行した結果として失敗した（`AgentResult.success=False`）」場合のみ後続ステップを打ち切る。Gate閉鎖・`decide()`による`should_act=False`判断は失敗として扱わず、後続ステップの実行を継続する。打ち切りが発生した場合も、未到達のステップは`WorkflowEngineResult.steps`に`skipped_reason=REASON_NOT_REACHED`として記録され、`steps`の件数は常に`WorkflowEngineDefinition.steps`と同じ件数になる。

### `scripts/run_workflow_engine.py` の使い方と運用上の注意

```bash
cd projects/03_game_content_ai
./venv/Scripts/python.exe scripts/run_workflow_engine.py              # Scheduler判定経由
./venv/Scripts/python.exe scripts/run_workflow_engine.py --dry-run    # dry-run（副作用なし）
./venv/Scripts/python.exe scripts/run_workflow_engine.py --job-id manual-run  # Scheduler判定を経由しない手動起動
```

前提条件（.env、二重ゲート）：`AI_AGENT_ENABLED=true` かつ `WORKFLOW_ENGINE_ENABLED=true`。Review/Publishステップを実際に動かすには、それぞれ`REVIEW_TRIGGER_AGENT_ENABLED=true` / `PUBLISH_TRIGGER_AGENT_ENABLED=true`（+ WordPress認証情報3点）も必要。

運用上、以下の点に注意すること（詳細は`docs/design/workflow_engine_foundation.md` 13.1節）。

1. **固定・最小限（1件のみ）のデモJobを扱う**：`scripts/run_workflow_engine.py`は、Scheduler経由で実行する場合に`job_id="workflow_engine_demo_daily"`（DAILY / `09:00`固定）のデモJobを1件だけ登録する。複数Jobの登録・Job定義の設定ファイル化・実行時の動的登録は現時点では対応していない（Future Extensions）
2. **既存script群との同時実行を避けること**：`scripts/run_news_agent.py` / `scripts/run_review_trigger_agent.py` / `scripts/run_publish_trigger_agent.py` / `scripts/run_workflow_trigger_agent.py`など、`AgentManager`経由の既存script群と`scripts/run_workflow_engine.py`を同時に手動実行しないこと
3. **ロック機構は未実装**：`decide()`の判断から`act()`完了（ファイル書き込みによるmtime更新）までの間、いかなるロックも存在しない。上記1・2を守らずに同時実行した場合、News収集・レビューレポート生成・**WordPress下書き投稿**などが二重に発生するリスクがある
4. **短い間隔での連続起動も避けること**：`SchedulerEngine`（v2.6.0）は`last_run_at`を保持しないため、`scripts/run_workflow_engine.py`自体を短い間隔で繰り返し起動すると、同一分内で同じ`SchedulerEvent`が繰り返し発火し、上記3のリスクをさらに増幅させる可能性がある

これらはRelease 2.7時点でロック実装を見送り、運用制約として明記するにとどめた既知の制約である（Development Charter 6章「技術的負債との向き合い方」に従い、可視化・理由・将来の解消タイミングの3条件を満たす形で`docs/design/workflow_engine_foundation.md` 17章 Future Extensionsに記録済み）。

### 新しいステップをWorkflow Engineへ追加する場合（将来手順）

1. `WorkflowEngineStep`に新しいメンバーを追加する（既存メンバーの意味は変えない）
2. 対応する既存Agent（またはPipeline構成）を、`WorkflowEngineManager.from_config()`内に他ステップと同じ形で構築するブロックを追加する
3. `ALL_WORKFLOW_ENGINE_STEPS`の並び順を、新しいステップを含めて更新する
4. Agent層・Pipeline層・Scheduler層への変更は不要（Workflow Engine層は既存資産を呼ぶ側であり、呼ばれる側ではない）

詳細は`docs/design/workflow_engine_foundation.md`（Project Charter・Architecture Design）を参照。
