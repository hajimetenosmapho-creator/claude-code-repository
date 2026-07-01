# 出力アーキテクチャ設計

作成日：2026-06-26  
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

## 全体構成（v2.2.0 時点）

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

scripts/run_ai_workflow.py（投稿後の改善サイクル・main.pyとは独立実行）
  └─ AgentManager（判断）                ← Agent層（v2.0.0、現時点では判断のみ）
       └─ WorkflowRunner（実行）         ← Workflow層（v1.20.0）
            └─ WorkflowStepExecutor × 6
                 ├─ Improvement       （v1.14.0 AiImprovementService）
                 ├─ ImprovementReview （v1.15.0 ImprovementReviewService）
                 ├─ Rewrite           （v1.16.0 RewriteService）
                 ├─ RewriteReview     （v1.17.0 RewriteReviewService）
                 ├─ Publish           （v1.18.0 AiPublishService）
                 └─ PublishReview     （v1.19.0 AiPublishReviewService）
```

各層の役割：

| 層 | 実装 | 責務 |
|---|---|---|
| Agent層 | `AgentManager` / `AgentExecutor` / `BaseAgent` | 「今、何かを実行すべきか」を**判断**する。実行そのものは行わない |
| Pipeline層 | `NewsPipelineRunner` / `PipelineResult` | Agent層から渡されたタスクを実際に**実行**する（v2.2.0、`main.py`の起動など）。Agent層には依存しない |
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

## Pipeline層（`src/pipeline/`、v2.2.0 追加）

`NewsAgent`（Agent層）が「実行すべき」と判断した後、実際の処理を担う実行層。設計レビューの結果、
「Agentがsubprocessを直接実行する」設計は責務混同を招くと判断され、Agent層とは別パッケージとして分離した。

- **Agent＝判断、PipelineRunner＝実行**：`NewsAgent`は`NewsPipelineRunner.run(params) -> PipelineResult`という薄いインターフェースのみを呼び、実行方式（subprocess／将来的なimport呼び出し／API呼び出し等）を一切知らない
- `NewsPipelineRunner`は`main.py`をsubprocessとして起動する。`main.py`本体は無改修（`argparse`が`sys.argv`を読む・複数箇所で`sys.exit()`を呼ぶという既存の実装特性上、直接importして呼び出すとAgentプロセスごと道連れにするリスクがあるため、プロセスとして隔離している）
- **Pipeline層はAgent層に依存しない**：`src/pipeline/`配下のモジュールは`AgentContext` / `AgentDecision` / `AgentResult`等のAgent層の型、および`WorkflowRunner`を一切importしない。設定値の受け渡しは`Protocol`によるダックタイピングで行い、`ai → pipeline`の一方向依存のみを許可する
- 実行結果は`PipelineResult`（`success` / `returncode` / `elapsed_sec` / `stdout_log_path` / `stderr_log_path` / `error_message`）にまとめられ、`NewsAgent`がこれを`AgentResult`へ変換する（`workflow_result`は常に`None`）
- `dry_run=True`の場合、`AgentExecutor`（v2.0.0の既存設計）により`NewsAgent.act()`自体が呼ばれないため、`NewsPipelineRunner.run()`（＝`main.py`起動）は構造的に発生しない

```
NewsAgent（判断）
  └─ NewsPipelineRunner.run(params)（実行）
       └─ subprocess.run([python_executable, main_py_path], cwd=working_directory, timeout=timeout_sec)
            └─ main.py（無改修。既存のニュース収集パイプラインをそのまま実行）
```

詳細設計：`docs/design/news_agent_foundation.md`

### 新しいPipelineRunnerを追加する場合（将来手順）

将来のWorkflow Trigger Agent / Publish Agent / Scheduler Agentも、同じ形の実行層を追加していく想定。

1. `src/pipeline/` に新しいRunnerクラス（例：`WorkflowPipelineRunner`）を作成し、`run(params) -> PipelineResult`を実装する
2. 対応するAgent（例：`WorkflowTriggerAgent`）の`act()`から、そのRunnerの`run()`のみを呼ぶ
3. Runner実装が2つ以上になった段階で、共通インターフェース（`Protocol`/ABC）への抽出を検討する（v2.2.0時点では1実装のみのため抽象化を先取りしていない）

**Agent層への変更は不要（Pipeline層はAgentから呼ばれる側であり、Agent層の型を知る必要がない）。**
