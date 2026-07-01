# 出力アーキテクチャ設計

作成日：2026-06-26  
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

## 全体構成（v2.3.0 時点）

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
| Pipeline層 | `NewsPipelineRunner` / `WorkflowPipelineRunner` / `PipelineResult` | Agent層から渡されたタスクを実際に**実行**する。Agent層には依存しない |
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
- デフォルトは無効（`AI_AGENT_ENABLED=false`）。既存の `WorkflowRunner` 経由の自動実行フローには影響しない

詳細設計：`docs/design/agent_foundation.md`

### 新しいAgentを追加する場合（将来手順）

1. `src/ai/` に `BaseAgent` を継承した新しいAgentクラスを作成し、`decide()` / `act()` / `name()` を実装する
2. `AgentManager.from_config()` 内で、新しいAgentを包んだ `AgentExecutor` を `executors` リストに追加する（DI）
3. 必要であれば `AgentConfig` に判断材料となる設定値を追加する

**Workflow層・Service層への変更は不要（Agent層はWorkflowを呼び出す側であり、呼び出される側ではない）。**

---

## Pipeline層（`src/pipeline/`、v2.2.0 / v2.3.0 追加）

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

### 両Runnerに共通する設計原則

- **Pipeline層はAgent層に依存しない**：`src/pipeline/`配下のモジュールは`AgentContext` / `AgentDecision` / `AgentResult`等のAgent層の型を一切importしない。設定値の受け渡しは`Protocol`によるダックタイピングで行う
- 実行結果は共通の`PipelineResult`（`success` / `returncode` / `elapsed_sec` / `stdout_log_path` / `stderr_log_path` / `error_message`）にまとめられ、各Agentがこれを`AgentResult`へ変換する（`workflow_result`は常に`None`）
- `dry_run=True`の場合、`AgentExecutor`（v2.0.0の既存設計）により`act()`自体が呼ばれないため、PipelineRunnerの`run()`は構造的に発生しない（`NewsAgent` / `WorkflowTriggerAgent`共通の保証）
- **`NewsAgent`系と`WorkflowTriggerAgent`系は互いに独立したPipelineを持つ**：`NewsPipelineRunner`と`WorkflowPipelineRunner`は互いをimportせず、依存関係を持たない

### 新しいPipelineRunnerを追加する場合（将来手順）

将来のPublish Agent / Scheduler Agentも、同じ形の実行層を追加していく想定。

1. `src/pipeline/` に新しいRunnerクラス（例：`PublishPipelineRunner`）を作成し、`run(params) -> PipelineResult`を実装する
2. 対応するAgent（例：`PublishTriggerAgent`）の`act()`から、そのRunnerの`run()`のみを呼ぶ
3. Runner実装が3つ目になった段階で、共通インターフェース（`Protocol`/ABC）への抽出を検討する（v2.3.0時点では`NewsPipelineRunner` / `WorkflowPipelineRunner`の2実装のみのため抽象化を先取りしていない）

**Agent層への変更は不要（Pipeline層はAgentから呼ばれる側であり、Agent層の型を知る必要がない）。**

---

## Agent → Pipeline → Runner パターン（Release 2.x 標準アーキテクチャ）

v2.2.0（News Agent Foundation）・v2.3.0（Workflow Trigger Agent Foundation）を通じて、以下の3層パターンがRelease 2.x系のAgent実装における標準アーキテクチャとして確立した。

```
[判断] BaseAgent実装（decide() / act()）
   ↓
[実行] PipelineRunner実装（run(params) -> PipelineResult）
   ↓
[対象] 既存の資産（main.py / WorkflowRunner等、無改修のまま呼び出される）
```

| Agent（判断） | Pipeline層（実行） | 実行対象 | 実行方式 |
|---|---|---|---|
| `NewsAgent`（v2.2.0） | `NewsPipelineRunner` | `main.py` | subprocess起動（`argparse`/`sys.exit()`問題を隔離するため） |
| `WorkflowTriggerAgent`（v2.3.0） | `WorkflowPipelineRunner` | `WorkflowRunner` | 直接呼び出し（`WorkflowRunner`にsubprocess化が必要な問題がないため） |

このパターンに共通する設計原則：

1. Agentは「判断」のみを行い、副作用（実際の起動）を持たない（`decide()`は読み取り専用）
2. Agentは実行対象（`main.py` / `WorkflowRunner`）を直接importしない。実行方式はPipelineRunnerに完全に閉じ込める
3. PipelineRunnerはAgent層の型（`AgentContext`等）をimportしない（`ai → pipeline`の一方向依存が原則。ただし`WorkflowPipelineRunner`のように実行対象自体が`ai`パッケージ内にある場合は、遅延importにより循環を避けたうえでこれを呼び出すことが許容される）
4. PipelineRunnerの実行方式（subprocessか直接呼び出しか）は、実行対象の実装特性（`sys.exit()`の有無等）によって決まる。パターン自体は変わらない
5. **`NewsAgent`系と`WorkflowTriggerAgent`系は互いに独立したPipelineを持つ**。`AgentManager`の`executors`リストにそれぞれ独立したエントリとして並び、実行層同士が依存し合うことはない
6. `dry_run=True`の場合、`AgentExecutor`の既存保証により`act()`自体が呼ばれないため、PipelineRunnerの`run()`は構造的に発生しない

将来のPublish Agent（`AiPublishService`対象）・Scheduler Agent（Windowsタスクスケジューラ統合）も同じパターンで追加していく想定。詳細は`docs/design/news_agent_foundation.md` §16、`docs/design/workflow_trigger_agent_foundation.md` §16（Future Extensions）を参照。
