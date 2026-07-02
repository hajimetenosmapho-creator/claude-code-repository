# v2.4.0 Publish Trigger Agent Foundation 設計書

作成日：2026-07-02（実装完了後の事後整備）
状態：実装完了（コード・テストはmainに反映済み。本ドキュメントは実装内容との整合を確認したうえで作成）

---

## 1. Goal

v2.0.0で作られたAgent Foundation（`BaseAgent` / `AgentExecutor` / `AgentManager`）に、`AiPublishService`（v1.18.0、WordPress下書き投稿）の起動タイミングを判断する3つ目の具体的なAgent **`PublishTriggerAgent`** を追加する。`PublishTriggerAgent`は「WordPress下書き投稿そのもの」ではなく「Publishを今実行すべきかを判断する」上位レイヤーであり、判断がYesの場合のみ新設した実行層 **`PublishPipelineRunner`** 経由で`AiPublishService`を起動する。

```
PublishTriggerAgent   （判断：起動すべきか）
      ↓
PublishPipelineRunner （実行：起動する）
      ↓
AiPublishService       （既存のサービス、v1.18.0、無改修）
```

`NewsAgent`（v2.2.0）・`WorkflowTriggerAgent`（v2.3.0）と同じ「Agent（判断）→ Pipeline（実行）→ 対象サービス」パターンを踏襲する。

---

## 2. Background

- v2.3.0で`WorkflowTriggerAgent`が実装され、「Agent（判断）→ PipelineRunner（実行）→ 既存のオーケストレーター/サービス」という3層責務分離パターンが2例（`NewsAgent` / `WorkflowTriggerAgent`）で確立した。
- `docs/ROADMAP.md`の「v2.x以降の候補」に「v2.4.0 Publish Trigger Agent Foundation」として、`AiPublishService`（v1.18.0）を対象に同じパターンを再利用する方針が明記されていた。
- `WorkflowTriggerAgent`が二重ゲート（`AI_AGENT_ENABLED` × `WORKFLOW_TRIGGER_AGENT_ENABLED` かつ `AI_WORKFLOW_ENABLED`）で安全側に倒した設計を踏襲し、`PublishTriggerAgent`ではWordPressへの実書き込みを伴うため、既存の`AiPublishConfig.is_ready()`（`AI_PUBLISH_ENABLED` + WordPress認証情報3点）をそのまま3段目のゲートとして再利用する**三重ゲート方式**を採用した。

---

## 3. Scope

### 実装対象

- `PublishTriggerAgentConfig`（`src/ai/publish_trigger_agent_config.py`）：判断・実行双方の設定値
- `PublishPipelineRunner`（`src/pipeline/publish_pipeline_runner.py`）：`AiPublishService.run()`を直接呼び出す実行層
- `PublishTriggerAgent`（`src/ai/publish_trigger_agent.py`、`BaseAgent`継承）：`decide()` / `act()` / `name()`
- `AgentManager.from_config()`の`executors`への`PublishTriggerAgent`用`AgentExecutor`のDI（三重ゲート方式）
- `scripts/run_publish_trigger_agent.py`：手動実行用の最小CLIエントリ
- `tests/test_e2e_v2_4_0_publish_trigger_agent_foundation.py`：新規E2Eテスト

### 対象外

- `AiPublishService` / `AiPublishConfig` / `WordPressDraftClient`等、Publish層本体の改修
- `NewsAgent` / `WorkflowTriggerAgent`・それぞれの`PipelineRunner`・`BaseAgent` / `AgentExecutor` / `AgentContext` / `AgentDecision` / `AgentResult` / `AgentConfig`の改修
- 新しい実行ログ基盤の追加
- `PipelineResult`の汎用化・共通Runner Interfaceの抽出（Runner実装が3つ目になった段階だが、v2.3.0設計書 §16で「実装が2つ出揃った時点ではまだ早計」としており、本バージョンでも見送り）

---

## 4. Non Goal

- `PublishTriggerAgent`はPublishの中身（重複チェック・WordPress投稿処理等）のロジックを**一切持たない**。実際の処理はすべて既存の`AiPublishService`に委譲する。
- `PublishTriggerAgent`は`AiPublishService`の起動方法を**一切知らない**。起動方法は`PublishPipelineRunner`に完全に閉じ込める。
- `AiPublishService` / `AiPublishConfig`本体への変更は行わない。
- 新しい実行ログ基盤（例：`logs/publish_agent/`）は本バージョンでは作らない。判断材料は既存の`outputs/ai_publish_reports/`のファイル更新日時（mtime）で代用する。
- 未投稿の`ADOPTED`レビュー件数を直接見に行く判断方式は採用しない（`PublishTriggerAgent`が`AiPublishRepository`等のPublish実処理側のデータ構造を直接参照する責務を持たないようにするため。時間間隔方式を採用する。将来の改善候補として16章に記録）。
- Windowsタスクスケジューラ統合、重要度別の公開制御などの長期ビジョン項目は対象外。

---

## 5. User Workflow

### Before（v2.3.0まで）

- ブロガーが`python scripts/run_ai_publish.py`を手動実行する必要があった。「今Publishを実行すべきか」の判断はブロガー自身が行っていた。

### After（v2.4.0）

- `AI_AGENT_ENABLED=false`（デフォルト）の場合：挙動は一切変わらない。
- `AI_AGENT_ENABLED=true`だが`PUBLISH_TRIGGER_AGENT_ENABLED=false`（デフォルト）の場合：`PublishTriggerAgent`は生成されない（`NewsAgent`・条件を満たせば`WorkflowTriggerAgent`のみが有効化される）。
- `AI_AGENT_ENABLED=true` **かつ** `PUBLISH_TRIGGER_AGENT_ENABLED=true` **かつ** `AiPublishConfig.is_ready()`（`AI_PUBLISH_ENABLED=true`＋WordPress認証情報3点設定済み）の場合のみ：`python scripts/run_publish_trigger_agent.py`（または将来のAgentManager一括実行）を実行すると、`PublishTriggerAgent`が「前回Publish実行からの経過時間」を根拠に実行要否を判断し、必要な場合のみ`PublishPipelineRunner`経由で`AiPublishService`を起動する。
- `--dry-run`を付けた場合：判断結果（実行すべきか、その理由）のみ表示し、実際のPublish実行（WordPress下書き投稿）は行わない。

---

## 6. System Workflow

```
scripts/run_publish_trigger_agent.py [--dry-run] [--article-id SLUG]
  → AgentConfig.from_env()
  → AgentManager.from_config(config)
       config.is_ready()=False（AI_AGENT_ENABLED=false）
         → NullAgentManager（v2.0.0のまま変更なし）
       config.is_ready()=True（AI_AGENT_ENABLED=true）
         → executors = [AgentExecutor(NewsAgent(...))]  ← v2.2.0のまま変更なし
         → WorkflowTriggerAgentConfig.is_ready() 次第で WorkflowTriggerAgent を追加 ← v2.3.0のまま変更なし
         → PublishTriggerAgentConfig.from_env(project_root=config.base_dir)
              .is_ready()=False（PUBLISH_TRIGGER_AGENT_ENABLED=false、
               または AiPublishConfig.from_env().is_ready()=False）
                → executorsに追加しない（PublishTriggerAgentは生成すらされない）
              .is_ready()=True（PUBLISH_TRIGGER_AGENT_ENABLED=true
               かつ AiPublishConfig.is_ready()=True）
                → PublishPipelineRunner(publish_trigger_agent_config)
                     （この時点では AiPublishService はまだ構築しない）
                → PublishTriggerAgent(config=publish_trigger_agent_config,
                                       runner=publish_pipeline_runner)
                → executors.append(AgentExecutor(PublishTriggerAgent(...)))
  → AgentManager.run(AgentTask(task_id="run_publish", params={...}), dry_run=...)
       → AgentExecutor.execute(context)          ← v2.0.0のまま変更なし
            1. PublishTriggerAgent.decide(context)
                 - outputs/ai_publish_reports/*.md のmtimeを読み取り専用で走査（副作用なし）
            2. should_act=False、または dry_run=True の場合
                 → act() を呼ばず AgentExecutor が AgentResult を組み立てる
                   （PublishPipelineRunner へは到達しない。AiPublishServiceは絶対に起動しない）
            3. should_act=True かつ dry_run=False の場合のみ
                 → PublishTriggerAgent.act(decision, context)
                      → PublishPipelineRunner.run(params=context.task.params)
                           → AiPublishService.from_env(base_dir=config.project_root)
                           → service.run(article_id=...)
                           → service.get_results(article_id=...)（読み戻し確認のみ）
                           → 結果を PipelineResult に変換
                      → PublishTriggerAgent が PipelineResult を AgentResult に変換
  → AgentResult のリストを返す
```

`PublishTriggerAgent`は`NewsAgent` / `WorkflowTriggerAgent`とは別系統のAgentであり、互いに依存しない。3者は`AgentManager`の`executors`リストに独立して並ぶ。

---

## 7. Data Model

### `PublishTriggerAgentConfig`（`src/ai/publish_trigger_agent_config.py`）

| フィールド | 型 | デフォルト | 内容 |
|---|---|---|---|
| `enabled` | `bool` | `False`（`PUBLISH_TRIGGER_AGENT_ENABLED`） | 三重ゲートの2段目。`False`の場合`is_ready()`は`False`になる |
| `min_interval_minutes` | `int` | `1440`（`PUBLISH_TRIGGER_AGENT_MIN_INTERVAL_MINUTES`） | 前回Publish実行からこの分数以上経過していない場合は`should_act=False`。`WorkflowTriggerAgent`と同じ24時間をデフォルトとする |
| `reports_dir` | `Path` | `project_root / "outputs" / "ai_publish_reports"` | 判断材料として走査するディレクトリ（`AiPublishReportBuilder`の既存出力先） |
| `publish_enabled` | `bool` | `False`相当（`AiPublishConfig.from_env().is_ready()`をそのまま再利用して取得） | 三重ゲートの3段目。`AI_PUBLISH_ENABLED`＋WordPress認証情報3点の判定を`AiPublishConfig`に委譲し、重複実装しない |
| `project_root` | `Path` | 呼び出し元から渡される値 | プロジェクトルート。`reports_dir`の組み立てや`AiPublishService.from_env(base_dir=...)`への引き渡しに使う |

`is_ready()`は`enabled and publish_enabled`（三重ゲートの2段目`PUBLISH_TRIGGER_AGENT_ENABLED` **かつ** 3段目`AiPublishConfig.is_ready()`）を返す。1段目の`AI_AGENT_ENABLED`は`AgentConfig`が担い、`AgentManager`側で3段すべてをチェックする。`reports_dir`がディスク上に実在するかどうかは`is_ready()`の判定に含めない（初回実行時も`is_ready()=True`とし、実際の存在確認は`decide()`側の責務とする）。

### `PipelineResult`（`src/pipeline/pipeline_result.py`、既存型を無改修で流用）

`PublishPipelineRunner.run()`は`AiPublishService.run()`の戻り値を以下のルールで`PipelineResult`にマッピングする。

| フィールド | 値 | 理由 |
|---|---|---|
| `success` | `report_path is not None`（保存したMarkdownレポートのパスが返ってきたか） | `AiPublishService.get_results()`は`article_id`絞り込みのみで過去の全投稿履歴を返す（今回実行分だけではない）ため、件数を`success`判定に使うと過去の失敗まで巻き込んでしまう。そのため`run()`の戻り値のみを根拠にする |
| `returncode` | `None`固定 | subprocessではないため終了コードの概念がない |
| `elapsed_sec` | `PublishPipelineRunner.run()`呼び出し全体を`time.time()`差分で実測した値 | `AiPublishService.from_env()`の構築時間も含めた壁時計時間をそのまま計測する |
| `stdout_log_path` | `None`固定 | subprocessではないため標準出力の概念がない |
| `stderr_log_path` | `None`固定 | 同上 |
| `error_message` | 失敗時（`report_path is None`）：固定文言`"Publish report was not saved."`／例外発生時：`str(exc)`／成功時：`None` | `WorkflowPipelineRunner`と同じく、最初は簡潔な実装とする |

`service.get_results(article_id=...)`は保存結果を読み戻せるか（正常に完了したか）の確認目的でのみ呼び出し、戻り値は`PipelineResult`には反映しない。

### `AgentTask.params`（既存構造の再利用）

| キー | 型 | 内容 |
|---|---|---|
| `article_id` | `str`（任意） | 指定時は`PublishPipelineRunner`が`AiPublishService.run(article_id=...)`にそのまま渡す |

---

## 8. Directory Structure

```
src/
├── ai/
│   ├── publish_trigger_agent_config.py    # PublishTriggerAgentConfig（新規）
│   ├── publish_trigger_agent.py           # PublishTriggerAgent（新規、BaseAgent継承）
│   ├── agent_manager.py                   # executorsへの三重ゲートDI追加（既存ファイル更新）
│   └── __init__.py                        # PublishTriggerAgent / PublishTriggerAgentConfig をexport（既存ファイル更新）
│
└── pipeline/
    ├── publish_pipeline_runner.py          # PublishPipelineRunner（新規）
    └── __init__.py                         # PublishPipelineRunner をexport（既存ファイル更新）

scripts/
└── run_publish_trigger_agent.py            # 手動実行エントリ（新規）

tests/
└── test_e2e_v2_4_0_publish_trigger_agent_foundation.py   # 新規（39テストケース）
```

`AiPublishService`本体（`ai_publish_service.py`等） / `AiPublishConfig` / `WorkflowRunner` / `NewsAgent` / `WorkflowTriggerAgent`は無変更（テスト §37 Architecture Guardで`git diff`確認済み）。

---

## 9. Module Design

実装済みコードは`src/ai/publish_trigger_agent_config.py` / `src/ai/publish_trigger_agent.py` / `src/pipeline/publish_pipeline_runner.py`を参照。設計方針は`WorkflowTriggerAgent`系（v2.3.0）と同一で、以下の点のみ異なる。

- **三重ゲート**：`WorkflowTriggerAgentConfig`は`enabled and workflow_enabled`の二重ゲートだが、`PublishTriggerAgentConfig`は`enabled and publish_enabled`（`publish_enabled`が`AI_PUBLISH_ENABLED`＋WordPress認証情報3点をまとめた`AiPublishConfig.is_ready()`）であり、`AI_AGENT_ENABLED`と合わせて実質三重のゲートになる
- **実行対象への引き渡し**：`AiPublishService.from_env(base_dir=...)`→`service.run(article_id=...)`→`service.get_results(article_id=...)`の3呼び出しを`PublishPipelineRunner.run()`内で行う（`WorkflowPipelineRunner`は`WorkflowConfig.from_env()`→`WorkflowRunner.from_config()`→`runner.run()`の3呼び出し）
- **`decide()`の判断材料**：`outputs/ai_publish_reports/`配下の`*.md`のmtime（`WorkflowTriggerAgent`は`outputs/workflow_reports/`配下）
- **`workflow_result`は常に`None`**：`AgentResult.workflow_result`フィールドは`PublishTriggerAgent`では使用しない（`NewsAgent` / `WorkflowTriggerAgent`と同じ扱い）

### `AgentManager.from_config()`（DI配線、三重ゲート方式）

```python
publish_trigger_agent_config = PublishTriggerAgentConfig.from_env(
    project_root=config.base_dir
)
if publish_trigger_agent_config.is_ready():
    publish_pipeline_runner = PublishPipelineRunner(publish_trigger_agent_config)
    publish_trigger_agent = PublishTriggerAgent(
        config=publish_trigger_agent_config,
        runner=publish_pipeline_runner,
    )
    executors.append(AgentExecutor(publish_trigger_agent))
```

`config.is_ready()`（`AI_AGENT_ENABLED`）が1段目、`publish_trigger_agent_config.is_ready()`内の`enabled`（`PUBLISH_TRIGGER_AGENT_ENABLED`）が2段目、`publish_enabled`（`AiPublishConfig.is_ready()`＝`AI_PUBLISH_ENABLED`＋WordPress認証情報3点）が3段目であり、**3段すべてが`True`の場合のみ`PublishTriggerAgent`が生成される**。`NewsAgent`・`WorkflowTriggerAgent`のDIには影響しない（`agent_manager.py`の実装を参照、独立して並列に判定される）。

---

## 10. Configuration Design

```
# 実装済みの環境変数（現時点では .env.example への追記は未実施。別タスクで対応予定）
AI_AGENT_ENABLED=false                            # 既存（v2.0.0）
PUBLISH_TRIGGER_AGENT_ENABLED=false               # 新規：三重ゲートの2段目（デフォルト無効）
PUBLISH_TRIGGER_AGENT_MIN_INTERVAL_MINUTES=1440   # 新規：前回Publish実行から何分空けるか（デフォルト24時間）
AI_PUBLISH_ENABLED=false                          # 既存（v1.18.0、三重ゲートの3段目として再利用）
WORDPRESS_URL=                                    # 既存（v1.18.0、AiPublishConfigが参照）
WORDPRESS_USERNAME=                               # 既存（v1.18.0、同上）
WORDPRESS_APP_PASSWORD=                           # 既存（v1.18.0、同上）
```

**三重ゲート方式（Configuration First の強化）**：`AI_AGENT_ENABLED=false`の場合は何も生成されない（v2.0.0のまま）。`AI_AGENT_ENABLED=true`でも`PUBLISH_TRIGGER_AGENT_ENABLED=false`（デフォルト）の場合、`PublishTriggerAgentConfig` / `PublishPipelineRunner` / `PublishTriggerAgent`のいずれのオブジェクトも生成されない。`PUBLISH_TRIGGER_AGENT_ENABLED=true`でも`AI_PUBLISH_ENABLED=false`またはWordPress認証情報が未設定の場合も同様に生成されない。News収集（`NewsAgent`）・Workflow自動実行（`WorkflowTriggerAgent`）・Publish自動実行（`PublishTriggerAgent`）を独立して制御できることが、この三重ゲートの目的である。

**注意**：`WORDPRESS_URL` / `WORDPRESS_USERNAME` / `WORDPRESS_APP_PASSWORD`は`.env.example`内の既存項目`WP_SITE_URL` / `WP_USERNAME` / `WP_APP_PASSWORD`（v1.0.0由来のコメントアウト項目）とは**別名の環境変数**であり、`AiPublishService`（v1.18.0）系はこちらを参照する。`.env.example`にはいずれも未記載であり、`AI_IMPROVEMENT_ENABLED`（v1.14.0）以降の全環境変数（`AI_REWRITE_ENABLED` / `AI_PUBLISH_ENABLED` / `AI_WORKFLOW_ENABLED` / `AI_AGENT_ENABLED` / `NEWS_AGENT_*` / `WORKFLOW_TRIGGER_AGENT_*` / `PUBLISH_TRIGGER_AGENT_*`含む）が未記載という、本バージョン固有ではないドキュメント負債が存在する（16章に記録。対応は別タスク）。

---

## 11. PublishTriggerAgent.decide() の判断基準

`outputs/ai_publish_reports/`配下（`AiPublishReportBuilder`が書き込む既存の出力先、v1.18.0）を読み取り専用で走査し、最新のファイル更新日時（mtime）を現在時刻と比較する。ロジックは`WorkflowTriggerAgent.decide()`（v2.3.0設計書 §11）と同一で、対象ディレクトリのみが異なる。

```
1. outputs/ai_publish_reports/ 配下の *.md を列挙
2. 各ファイルの mtime（最終更新日時）を取得
3. 最新の mtime を採用
   a. ディレクトリが存在しない、またはファイルが1件もない場合
        → should_act=True, reason="No previous publish report found."
   b. 経過時間 >= min_interval_minutes の場合
        → should_act=True, reason="Publish interval exceeded."
   c. 経過時間 < min_interval_minutes の場合
        → should_act=False, reason="Publish interval not exceeded."
4. ファイル取得に失敗した場合はスキップし、context.warnings に記録する
5. 全てのファイルが取得不能で判断材料が皆無の場合
        → should_act=True（安全側：News Agent / WorkflowTriggerAgentと同じ方針）
```

`decide()`はファイルの**メタデータ取得のみ**を行い、書き込み・削除・外部API呼び出しは一切行わない。

---

## 12. PublishTriggerAgent.act() の実行方式（PublishPipelineRunner経由）

### Agent＝判断、PipelineRunner＝実行

`PublishTriggerAgent.act()`は`PublishPipelineRunner.run(params) -> PipelineResult`という薄いインターフェースのみを呼び出す。`AiPublishService`のクラス名・呼び出しシグネチャを`PublishTriggerAgent`は一切知らない。

### PublishPipelineRunnerがAiPublishServiceを直接呼び出せる理由

`AiPublishService.run(article_id)`は`WorkflowRunner.run()`（v2.3.0設計書 §12参照）と同様、通常のPythonメソッドであり、`sys.exit()`やCLI引数解析を内部に持たない。したがって`PublishPipelineRunner`は`AiPublishService`を**直接呼び出す薄いラッパー**として実装できる（`main.py`をsubprocess起動する`NewsPipelineRunner`とは異なる）。`AiPublishService`のimportは`run()`メソッド内に遅延させ、`pipeline → ai → pipeline`という循環importを構造的に回避している（`WorkflowPipelineRunner`と同じ手法）。

### dry_run=Trueで AiPublishService が起動しない保証

`PublishTriggerAgent.act()`は`AgentExecutor`（v2.0.0、無変更）によって`should_act=True`かつ`context.dry_run=False`の場合のみ呼び出される。したがって：

- `dry_run=True`の場合、`act()`自体が呼ばれない → `PublishPipelineRunner.run()`も呼ばれない → `AiPublishService.run()`も実行されない → WordPressへの実書き込みは発生しない
- `act()`冒頭に`assert not context.dry_run`を置き、万一の呼び出し経路の誤りを早期検出する（`NewsAgent` / `WorkflowTriggerAgent`と同じ形）

この保証はE2Eテスト（§35「三重ゲートON --dry-run --article-id」で`outputs/ai_publish_reports/`にファイルが増えないことを実サブプロセスで確認）で実測確認済み。

---

## 13. 既存 AiPublishService との関係

- `AiPublishService` / `AiPublishConfig` / `WordPressDraftClient`等、Publish層本体は**1行も変更しない**。
- `PublishTriggerAgent`は`AiPublishService`を外部から呼び出す「呼び出し元」であり、`AiPublishService`は自分がAgent経由で呼ばれていることを一切意識しない。
- 既存の`python scripts/run_ai_publish.py`によるユーザーの手動実行フローは影響を受けず、引き続き利用可能。
- 既存の判断材料（`outputs/ai_publish_reports/*.md`）は`PublishTriggerAgent.decide()`の判断材料として**読み取り専用で再利用**する。ファイルの生成ロジック（`AiPublishReportBuilder`）は変更していない。
- `NewsAgent` / `WorkflowTriggerAgent`とは無関係。`PublishTriggerAgent`はそれらを一切importしない。

---

## 14. Error Handling

| ケース | 対応 |
|---|---|
| `outputs/ai_publish_reports/`が存在しない、またはファイルが1件もない（初回実行） | `should_act=True`（安全側デフォルト） |
| ファイルのmtime取得失敗（`OSError`等） | 該当ファイルをスキップし、`context.warnings`に記録。全滅した場合は`should_act=True` |
| `AiPublishService.run()`が正常に返るが`report_path=None` | `PipelineResult(success=False, error_message="Publish report was not saved.")`（固定文言）。`PublishTriggerAgent`は例外を投げず`AgentResult`として返す |
| `AiPublishService.from_env()` / `service.run()` / `service.get_results()`のいずれかで予期せぬ例外が発生 | `PublishPipelineRunner`が`try/except Exception`で捕捉し、`PipelineResult(success=False, returncode=None, elapsed_sec=実測値, error_message=str(exc))`を返す。例外は`PublishTriggerAgent` / `AgentExecutor`へは伝播しない |
| `AI_AGENT_ENABLED=false` | `NullAgentManager`が空リストを返す（v2.0.0と同じ、変更なし） |
| `AI_AGENT_ENABLED=true`だが`PUBLISH_TRIGGER_AGENT_ENABLED=false`（デフォルト） | `PublishTriggerAgent`は生成されない |
| `PUBLISH_TRIGGER_AGENT_ENABLED=true`だが`AI_PUBLISH_ENABLED=false`またはWordPress認証情報未設定 | `AiPublishConfig.is_ready()=False`により`publish_enabled=False`となり、`PublishTriggerAgent`は生成されない |

---

## 15. Testing Strategy（実施済み・実測確認）

### 新規E2Eテスト

`tests/test_e2e_v2_4_0_publish_trigger_agent_foundation.py`：**120/120 PASS**（本ドキュメント作成時に実測、39テストケース）

- `PublishTriggerAgentConfig.from_env()`のデフォルト値・環境変数上書き・三重ゲート各段の`is_ready()`判定（テスト1〜5）
- `PublishTriggerAgent.decide()`：レポートなし／ファイル0件／間隔超過／間隔内／新旧混在で最新mtime優先の5パターン（テスト6〜10）
- `PublishTriggerAgent.act()`：`PublishPipelineRunner.run()`のみを呼ぶこと・成功/失敗時の`AgentResult`変換・`workflow_result`が常に`None`・`dry_run=True`直接呼び出しで`AssertionError`（テスト11〜16）
- `PublishPipelineRunner`：`AiPublishService`をモック化した`from_env`呼び出し引数・`run`/`get_results`呼び出し引数・成功/失敗/例外時の`PipelineResult`変換（テスト17〜26）
- `AgentManager.from_config()`の三重ゲート分岐：5パターン（テスト27〜31）
- `scripts/run_publish_trigger_agent.py`（実サブプロセス、常にdry-run）：スクリプト存在確認・無効時の安全終了・三重ゲートON時の`outputs/ai_publish_reports/`無変化確認等（テスト32〜36）
- Architecture Guard：`AiPublishService`本体・`AiPublishConfig`・`WorkflowRunner`・既存Agent（`NewsAgent`/`WorkflowTriggerAgent`）等19ファイルに変更がないこと（`git diff`）、禁止import静的検査、`src/ai/__init__.py` / `src/pipeline/__init__.py`のexport確認（テスト37〜39）

### 既存回帰確認（本ドキュメント作成時に再実測）

- `tests/test_e2e_v2_0_0_ai_agent_foundation.py`：**118/118 PASS**
- `tests/test_e2e_v2_2_0_news_agent_foundation.py`：**120/120 PASS**
- `tests/test_e2e_v2_3_0_workflow_trigger_agent_foundation.py`：**110/110 PASS**
- `tests/test_e2e_v1_20_0_ai_workflow_foundation.py`：**170/170 PASS**

**注意**：テスト実施時は`AiPublishService.from_env`をモック化し、実際のPublish（WordPress書き込み）や外部API呼び出しが発生しないようにしている。

---

## 16. Future Extensions

- 未投稿の`ADOPTED`レビュー件数を判断材料に使う方式への切り替え（現在は時間間隔方式のみ）
- `error_message`の詳細化（`WorkflowTriggerAgent`と同様の課題）
- 専用実行ログ基盤（例：`logs/publish_agent/`）の追加による`decide()`判断精度の向上
- `PipelineResult`の汎用化・共通Runner Interface（Protocol/ABC）の抽出（Runner実装が3つ目になったが、既存方針どおり本バージョンでも見送り。次のRunner追加時に再検討）
- **`.env.example`のドキュメント負債の解消**：`AI_IMPROVEMENT_ENABLED`（v1.14.0）以降、`AI_REWRITE_ENABLED` / `AI_PUBLISH_ENABLED` / `WORDPRESS_URL`系 / `AI_WORKFLOW_ENABLED` / `AI_AGENT_ENABLED` / `NEWS_AGENT_*` / `WORKFLOW_TRIGGER_AGENT_*` / `PUBLISH_TRIGGER_AGENT_*`が`.env.example`に一切追記されていない。本バージョン固有の問題ではなく複数バージョンにまたがる既存の負債のため、別タスクとして切り出して対応する
- Scheduler Agent（Windowsタスクスケジューラ統合）への展開
- 重要度別の公開制御との連携
- Review Trigger Agent（Release 2.5、検討中）：`AiPublishReviewService`（v1.19.0）の実行タイミングを判断するAgent。同じAgent → Pipeline → Serviceパターンの4例目となる想定

---

## 17. Definition of Done

### コード

- [x] `PublishTriggerAgentConfig`（`src/ai/publish_trigger_agent_config.py`）
- [x] `PublishPipelineRunner`（`src/pipeline/publish_pipeline_runner.py`、subprocess不使用・`AiPublishService.run()`を直接呼ぶ薄いラッパー）
- [x] `PublishTriggerAgent`（`src/ai/publish_trigger_agent.py`、`AiPublishService`を直接importしない）
- [x] `AgentManager.from_config()`の`executors`更新（三重ゲート方式：`AI_AGENT_ENABLED` × `PublishTriggerAgentConfig.is_ready()`）
- [x] `scripts/run_publish_trigger_agent.py`（`--dry-run` / `--article-id`対応）
- [x] `src/ai/__init__.py` / `src/pipeline/__init__.py`への新規シンボルのexport追加

### テスト

- [x] `tests/test_e2e_v2_4_0_publish_trigger_agent_foundation.py`：120/120 PASS（本ドキュメント作成時に実測）
- [x] 既存回帰確認：`v2.0.0`（118/118 PASS）・`v2.2.0`（120/120 PASS）・`v2.3.0`（110/110 PASS）・`v1.20.0`（170/170 PASS）（本ドキュメント作成時に実測）
- [x] `dry_run=True`で`act()`（ひいては`AiPublishService.run()`）が起動しないことの実測確認
- [x] 三重ゲート（`AI_AGENT_ENABLED` × `PUBLISH_TRIGGER_AGENT_ENABLED` × `AiPublishConfig.is_ready()`）の分岐確認
- [x] Architecture Guard：`PublishTriggerAgent`が`AiPublishService`を直接importしないこと・`PublishPipelineRunner`が`subprocess`を使わないことの静的検査
- [x] `AiPublishService`本体 / `AiPublishConfig` / `WorkflowRunner` / `NewsAgent` / `WorkflowTriggerAgent`等が無変更であることの`git diff`確認

### ドキュメント

- [x] 本設計書（実装完了後の事後整備として本タスクで作成）
- [x] `CHANGELOG.md`への記載（本タスクで追記）
- [x] `docs/ROADMAP.md`への記載（本タスクで追記）
- [ ] `docs/architecture.md`への追記（Agent → Pipeline → Runnerパターンの表にPublishTriggerAgentを追加。別タスクで対応）
- [ ] `.env.example`への追記（16章参照。複数バージョンにまたがる既存負債のため別タスクで対応）

### リリース

- [x] コミット・push（v2.4.0実装として既にmainに反映済み）
