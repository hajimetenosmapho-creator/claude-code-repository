# v2.3.0 Workflow Trigger Agent Foundation 設計書

作成日：2026-07-02
状態：実装完了（Step 1〜6完了、E2Eテスト110/110 PASS、本ドキュメントはStep 6.6で実装との整合を確定）

---

## 1. Goal

v2.0.0で作られたAgent Foundation（`BaseAgent` / `AgentExecutor` / `AgentManager`）に、`WorkflowRunner`（v1.20.0）の起動タイミングを判断する2つ目の具体的なAgent **`WorkflowTriggerAgent`** を追加する。`WorkflowTriggerAgent`は「Workflow（記事改善→リライト→公開の6ステップ）そのもの」ではなく「Workflowを今実行すべきかを判断する」上位レイヤーであり、判断がYesの場合のみ新設した実行層 **`WorkflowPipelineRunner`** 経由で`WorkflowRunner`を起動する。

```
WorkflowTriggerAgent   （判断：起動すべきか）
      ↓
WorkflowPipelineRunner （実行：起動する）
      ↓
WorkflowRunner         （既存のオーケストレーター、v1.20.0、無改修）
```

---

## 2. Background

- v2.0.0でAgent Foundation（判断のための骨組み）が作られたが、`AgentManager.from_config()`の`executors`は空リストのままだった。
- v2.2.0で`NewsAgent`が実装され、**Agent（判断）＝BaseAgent実装 → PipelineRunner（実行）＝`src/pipeline/`配下** という責務分離パターンが確立した。`docs/design/news_agent_foundation.md` §16（Future Extensions）でも「`WorkflowRunner`は既にimport可能なクラスであり`sys.exit()`問題がないため、`WorkflowPipelineRunner`はsubprocessではなく`WorkflowRunner.run()`を直接呼ぶ薄いラッパーとして実装できる可能性がある」と明記されており、本バージョンはその想定を実現するものである。
- `docs/ROADMAP.md`の「v2.x以降の候補」に「v2.3.0 Workflow Trigger Agent Foundation」として本リリースが明記されている。
- Project Charter（2026-07-02、承認済み）に基づき、本設計書はその内容を実装レベルまで具体化するものである。

---

## 3. Scope

### 実装対象

- `WorkflowTriggerAgentConfig`（`src/ai/workflow_trigger_agent_config.py`）：判断・実行双方の設定値
- `WorkflowPipelineRunner`（`src/pipeline/workflow_pipeline_runner.py`）：`WorkflowRunner.run()`を直接呼び出す実行層
- `WorkflowTriggerAgent`（`src/ai/workflow_trigger_agent.py`、`BaseAgent`継承）：`decide()` / `act()` / `name()`
- `AgentManager.from_config()`の`executors`への`WorkflowTriggerAgent`用`AgentExecutor`のDI（二重ゲート方式）
- `scripts/run_workflow_trigger_agent.py`：手動実行用の最小CLIエントリ

### 対象外（詳細は4章）

- `WorkflowRunner` / `WorkflowConfig` / `WorkflowStepExecutor`等、Workflow層本体の改修
- `NewsAgent` / `NewsPipelineRunner` / `BaseAgent` / `AgentExecutor` / `AgentContext` / `AgentDecision` / `AgentResult` / `AgentConfig`の改修
- 新しい実行ログ基盤の追加
- `PipelineResult`の汎用化・共通Runner Interfaceの抽出

---

## 4. Non Goal

- `WorkflowTriggerAgent`はWorkflowの中身（改善提案・リライト・公開等）のロジックを**一切持たない**。実際の処理はすべて既存の`WorkflowRunner`に委譲する。
- `WorkflowTriggerAgent`は`WorkflowRunner`の起動方法（直接呼び出しか、将来的に別の方式か）を**一切知らない**。起動方法は`WorkflowPipelineRunner`に完全に閉じ込める。
- `WorkflowRunner` / `WorkflowConfig`本体への変更は行わない。
- 新しい実行ログ基盤（例：`logs/workflow_agent/`）は本バージョンでは作らない。判断材料は既存の`outputs/workflow_reports/`のファイル更新日時（mtime）で代用する。
- `PipelineResult`の汎用化・共通Runner Interface（Protocol/ABC）の抽出は行わない。既存の`PipelineResult`をそのまま利用し、subprocess由来のフィールド（`returncode` / `stdout_log_path` / `stderr_log_path`）は固定値で埋める。
- 記事（`article_id`）単位の高度な判断ロジックは扱わない。`decide()`は「Workflow全体を今実行すべきか」の単純な経過時間判断に限定する。
- Windowsタスクスケジューラ統合、重要度別公開制御などの長期ビジョン項目は対象外。

---

## 5. User Workflow

### Before（v2.2.0まで）

- ブロガーが`python scripts/run_ai_workflow.py`を手動実行する必要があった。「今Workflowを実行すべきか」の判断はブロガー自身が行っていた。

### After（v2.3.0）

- `AI_AGENT_ENABLED=false`（デフォルト）の場合：挙動は一切変わらない。
- `AI_AGENT_ENABLED=true`だが`WORKFLOW_TRIGGER_AGENT_ENABLED=false`（デフォルト）の場合：`NewsAgent`のみが有効化され、`WorkflowTriggerAgent`は生成されない（＝Publishを含むWorkflowが意図せず自動実行されることはない）。
- `AI_AGENT_ENABLED=true` **かつ** `WORKFLOW_TRIGGER_AGENT_ENABLED=true`の場合のみ：`python scripts/run_workflow_trigger_agent.py`（または将来のAgentManager一括実行）を実行すると、`WorkflowTriggerAgent`が「前回Workflow実行からの経過時間」を根拠に実行要否を判断し、必要な場合のみ`WorkflowPipelineRunner`経由で`WorkflowRunner`を起動する。
- `--dry-run`を付けた場合：判断結果（実行すべきか、その理由）のみ表示し、実際のWorkflow実行（Publishを含む）は行わない。

---

## 6. System Workflow

```
scripts/run_workflow_trigger_agent.py [--dry-run] [--article-id SLUG]
  → AgentConfig.from_env()
  → AgentManager.from_config(config)
       config.is_ready()=False（AI_AGENT_ENABLED=false）
         → NullAgentManager（v2.0.0のまま変更なし）
       config.is_ready()=True（AI_AGENT_ENABLED=true）
         → executors = [AgentExecutor(NewsAgent(...))]  ← v2.2.0のまま変更なし
         → WorkflowTriggerAgentConfig.from_env(project_root=config.base_dir)
              .is_ready()=False（WORKFLOW_TRIGGER_AGENT_ENABLED=false、
               またはAI_WORKFLOW_ENABLED=false）
                → executorsに追加しない（WorkflowTriggerAgentは生成すらされない）
              .is_ready()=True（WORKFLOW_TRIGGER_AGENT_ENABLED=true
               かつ AI_WORKFLOW_ENABLED=true）
                → WorkflowPipelineRunner(workflow_trigger_agent_config)
                     （この時点では WorkflowConfig / WorkflowRunner はまだ構築しない）
                → WorkflowTriggerAgent(config=workflow_trigger_agent_config,
                                        runner=workflow_pipeline_runner)
                → executors.append(AgentExecutor(WorkflowTriggerAgent(...)))
  → AgentManager.run(AgentTask(task_id="run_workflow", params={...}), dry_run=...)
       → AgentExecutor.execute(context)          ← v2.0.0のまま変更なし
            1. WorkflowTriggerAgent.decide(context)
                 - outputs/workflow_reports/*.md のmtimeを読み取り専用で走査（副作用なし）
            2. should_act=False、または dry_run=True の場合
                 → act() を呼ばず AgentExecutor が AgentResult を組み立てる
                   （WorkflowPipelineRunner へは到達しない。WorkflowRunnerは絶対に起動しない）
            3. should_act=True かつ dry_run=False の場合のみ
                 → WorkflowTriggerAgent.act(decision, context)
                      → WorkflowPipelineRunner.run(params=context.task.params)
                           → WorkflowConfig.from_env(base_dir=config.project_root)
                           → WorkflowRunner.from_config(workflow_config)
                           → WorkflowRunner.run(article_id=..., dry_run=...)
                                （Improvement→ImprovementReview→Rewrite→RewriteReview→
                                  Publish→PublishReviewの6ステップを実行）
                           → WorkflowResult を PipelineResult に変換
                      → WorkflowTriggerAgent が PipelineResult を AgentResult に変換
  → AgentResult のリストを返す
```

`WorkflowTriggerAgent`は`NewsAgent`とは別系統のAgentであり、互いに依存しない。両者は`AgentManager`の`executors`リストに独立して並ぶ。

---

## 7. Data Model

### `WorkflowTriggerAgentConfig`（`src/ai/workflow_trigger_agent_config.py`）

| フィールド | 型 | デフォルト | 内容 |
|---|---|---|---|
| `enabled` | `bool` | `False`（`WORKFLOW_TRIGGER_AGENT_ENABLED`） | 二重ゲートの2段目。`False`の場合`is_ready()`は`False`になる |
| `min_interval_minutes` | `int` | `1440`（`WORKFLOW_TRIGGER_AGENT_MIN_INTERVAL_MINUTES`） | 前回Workflow実行からこの分数以上経過していない場合は`should_act=False`。News Agent（180分）より慎重な値として24時間をデフォルトとする |
| `reports_dir` | `Path` | `project_root / "outputs" / "workflow_reports"` | 判断材料として走査するディレクトリ（`WorkflowRunner._save_report()`の既存出力先） |
| `workflow_enabled` | `bool` | `True`（`AI_WORKFLOW_ENABLED`、`WorkflowConfig.from_env(base_dir=project_root).is_ready()`をそのまま再利用して取得） | 既存の`WorkflowConfig`とのAI_WORKFLOW_ENABLED解釈のズレを防ぐため、env var解析を重複実装しない |
| `project_root` | `Path` | 呼び出し元から渡される値 | プロジェクトルート。`reports_dir`の組み立てや`WorkflowConfig.from_env(base_dir=...)`への引き渡しに使う |

`is_ready()`は`enabled and workflow_enabled`（二重ゲートの2段目`WORKFLOW_TRIGGER_AGENT_ENABLED` **かつ** `AI_WORKFLOW_ENABLED`）を返す。`reports_dir`がディスク上に実在するかどうかは`is_ready()`の判定に含めない（初回実行時も`is_ready()=True`とし、実際の存在確認は`decide()`側の責務とする）。

### `PipelineResult`（`src/pipeline/pipeline_result.py`、既存型を無改修で流用）

`WorkflowPipelineRunner.run()`は`WorkflowResult`を以下のルールで`PipelineResult`にマッピングする。

| フィールド | 値 | 理由 |
|---|---|---|
| `success` | `WorkflowResult.overall_success`（例外発生時は`False`） | Workflow全体の成否をそのまま反映 |
| `returncode` | `None`固定 | subprocessではないため終了コードの概念がない |
| `elapsed_sec` | `WorkflowPipelineRunner.run()`呼び出し全体を`time.time()`差分で実測した値 | `WorkflowResult`のフィールドには依存しない。`WorkflowConfig.from_env()` / `WorkflowRunner.from_config()`の構築時間も含めた壁時計時間をそのまま計測する |
| `stdout_log_path` | `None`固定 | subprocessではないため標準出力の概念がない |
| `stderr_log_path` | `None`固定 | 同上 |
| `error_message` | 失敗時（`overall_success=False`）：固定文言`"Workflow completed with failed steps."`／例外発生時：`str(exc)`／成功時：`None` | 最初は簡潔な実装とする。失敗ステップ名を動的に要約する詳細化は行わない（将来拡張として16章に記載） |

`WorkflowResult`が持つ`report_path`（Markdownレポートの保存先）等の詳細情報は`PipelineResult`には転記しない（`PipelineResult`の型を拡張しないという合意のため）。詳細を参照したい場合は、`outputs/workflow_reports/`配下のレポートファイルを直接確認する運用とする。

### `AgentTask.params`（既存構造の再利用）

| キー | 型 | 内容 |
|---|---|---|
| `article_id` | `str`（任意） | 指定時は`WorkflowPipelineRunner`が`WorkflowRunner.run(article_id=...)`にそのまま渡す |

`dry_run`は`AgentTask.params`には含めない。Agent経由の実行は`AgentContext.dry_run`（`AgentExecutor`が管理する既存の仕組み）によってのみ制御し、Workflow層独自のdry_run（`scripts/run_ai_workflow.py --dry-run`）とは混同しない（11章参照）。

---

## 8. Directory Structure

```
src/
├── ai/
│   ├── workflow_trigger_agent_config.py   # WorkflowTriggerAgentConfig（新規）
│   ├── workflow_trigger_agent.py          # WorkflowTriggerAgent（新規、BaseAgent継承）
│   ├── agent_manager.py                   # executorsへの二重ゲートDI追加（既存ファイル更新）
│   └── __init__.py                        # WorkflowTriggerAgent / WorkflowTriggerAgentConfig をexport（既存ファイル更新）
│
└── pipeline/
    ├── workflow_pipeline_runner.py         # WorkflowPipelineRunner（新規）
    └── __init__.py                         # WorkflowPipelineRunner をexport（既存ファイル更新）

scripts/
└── run_workflow_trigger_agent.py           # 手動実行エントリ（新規）

tests/
└── test_e2e_v2_3_0_workflow_trigger_agent_foundation.py   # 新規
```

`main.py` / `WorkflowRunner`本体（`workflow_runner.py`等） / `NewsAgent` / `NewsPipelineRunner`は1行も変更していない（`git diff`で確認済み、15章参照）。

---

## 9. Module Design

### `WorkflowTriggerAgentConfig`

```python
from .workflow_config import WorkflowConfig


@dataclass
class WorkflowTriggerAgentConfig:
    enabled: bool
    min_interval_minutes: int
    reports_dir: Path
    workflow_enabled: bool
    project_root: Path

    @classmethod
    def from_env(cls, project_root: Path) -> "WorkflowTriggerAgentConfig":
        enabled = os.environ.get("WORKFLOW_TRIGGER_AGENT_ENABLED", "false").lower() == "true"
        min_interval_minutes = int(
            os.environ.get("WORKFLOW_TRIGGER_AGENT_MIN_INTERVAL_MINUTES", "1440")
        )
        workflow_enabled = WorkflowConfig.from_env(base_dir=project_root).is_ready()

        return cls(
            enabled=enabled,
            min_interval_minutes=min_interval_minutes,
            reports_dir=project_root / "outputs" / "workflow_reports",
            workflow_enabled=workflow_enabled,
            project_root=project_root,
        )

    def is_ready(self) -> bool:
        return self.enabled and self.workflow_enabled
```

### `WorkflowPipelineRunner`

```python
class WorkflowPipelineRunner:
    """WorkflowRunner.run() を直接呼び出す薄いラッパー。"""

    def __init__(self, config):  # project_root: Path を持つオブジェクト
        self._config = config

    def run(self, params: dict | None = None) -> PipelineResult:
        params = params or {}
        article_id = params.get("article_id")
        dry_run = bool(params.get("dry_run", False))

        start = time.time()  # run()全体を壁時計で計測する
        try:
            from ai import WorkflowConfig, WorkflowRunner

            workflow_config = WorkflowConfig.from_env(base_dir=self._config.project_root)
            runner = WorkflowRunner.from_config(workflow_config)
            workflow_result = runner.run(article_id=article_id, dry_run=dry_run)
        except Exception as e:
            return PipelineResult(
                success=False,
                returncode=None,
                elapsed_sec=time.time() - start,
                stdout_log_path=None,
                stderr_log_path=None,
                error_message=str(e),
            )

        error_message = (
            None if workflow_result.overall_success
            else "Workflow completed with failed steps."
        )

        return PipelineResult(
            success=workflow_result.overall_success,
            returncode=None,
            elapsed_sec=time.time() - start,
            stdout_log_path=None,
            stderr_log_path=None,
            error_message=error_message,
        )
```

`WorkflowPipelineRunner`が`WorkflowRunner`を直接呼び出すことは、Pipeline層が実行対象を呼び出す責務を持つため許容される。重要なのは、Agent層（`WorkflowTriggerAgent`）が`WorkflowRunner`を直接知らないことである。

`WorkflowPipelineRunner`自身は`AgentContext` / `AgentDecision` / `AgentResult`等のAgent層の型を一切importしない（`NewsPipelineRunner`と同じ原則）。`ai`パッケージのimportは`run()`メソッド内に遅延させている（`agent_manager.py`が`from pipeline import ...`で`pipeline`パッケージをimportする既存の依存関係があるため、`pipeline/__init__.py`が`WorkflowPipelineRunner`をexportする際に`pipeline → ai → pipeline`という循環importが起きないようにするための措置）。

例外処理は`WorkflowPipelineRunner`内で`try/except Exception`により捕捉し、`PipelineResult(success=False, error_message=str(exc))`として返す（呼び出し元へは伝播させない）。`WorkflowConfig.from_env()` / `WorkflowRunner.from_config()` / `WorkflowRunner.run()`のいずれで例外が発生してもこの1箇所で吸収される。`NewsPipelineRunner`が`subprocess.TimeoutExpired`のみを個別に捕捉するのとは異なり、`WorkflowPipelineRunner`は直接呼び出し（in-process）であるため`Exception`全体を対象とする、より広い捕捉範囲を採用している。

### `WorkflowTriggerAgent`

```python
class WorkflowTriggerAgent(BaseAgent):
    def __init__(self, config: WorkflowTriggerAgentConfig, runner: WorkflowPipelineRunner):
        self._config = config
        self._runner = runner

    def name(self) -> str:
        return "workflow_trigger_agent"

    def decide(self, context: AgentContext) -> AgentDecision:
        """outputs/workflow_reports/ のmtimeから直近のWorkflow実行時刻を求め、
        min_interval_minutes と比較して実行要否を判断する（副作用なし）。"""
        ...

    def act(self, decision: AgentDecision, context: AgentContext) -> AgentResult:
        assert not context.dry_run
        result = self._runner.run(params=context.task.params)
        return AgentResult(
            run_id=context.run_id,
            agent_name=context.agent_name,
            task=context.task,
            decision=decision,
            action_taken=True,
            success=result.success,
            workflow_result=None,   # 9章末尾の設計ノート参照
            error_message=result.error_message,
            started_at=context.started_at,
            finished_at=context.finished_at,
            warnings=list(context.warnings),
        )
```

**設計ノート（`workflow_result`が常に`None`である理由）**：`AgentResult.workflow_result`フィールドは「act()がWorkflowを起動した場合の参照」を意図したものだが（`agent_result.py`のdocstring）、`WorkflowTriggerAgent`は`WorkflowPipelineRunner`が返す**抽象化された`PipelineResult`のみ**を受け取り、生の`WorkflowResult`にはアクセスしない設計にしている。これはPipeline層の抽象化境界（`PipelineResult`は実行手段に依存しない共通結果型）を維持するための意図的な選択であり、`NewsAgent`が`workflow_result=None`固定にしているのと同じ扱いである。この扱いはProject Charterで承認済み（16章のFuture Extensionsで再検討候補として残している）。

### `AgentManager.from_config()`（DI配線のみ更新、二重ゲート方式）

```python
@classmethod
def from_config(cls, config: AgentConfig) -> "AgentManager | NullAgentManager":
    if not config.is_ready():
        return NullAgentManager()

    news_agent_config = NewsAgentConfig.from_env(project_root=config.base_dir)
    news_pipeline_runner = NewsPipelineRunner(news_agent_config)
    news_agent = NewsAgent(config=news_agent_config, runner=news_pipeline_runner)

    executors: list[AgentExecutor] = [
        AgentExecutor(news_agent),
    ]

    workflow_trigger_agent_config = WorkflowTriggerAgentConfig.from_env(
        project_root=config.base_dir
    )
    if workflow_trigger_agent_config.is_ready():
        workflow_pipeline_runner = WorkflowPipelineRunner(workflow_trigger_agent_config)
        workflow_trigger_agent = WorkflowTriggerAgent(
            config=workflow_trigger_agent_config,
            runner=workflow_pipeline_runner,
        )
        executors.append(AgentExecutor(workflow_trigger_agent))

    return cls(config=config, executors=executors)
```

`config.is_ready()`（`AI_AGENT_ENABLED`）が1段目のゲート、`workflow_trigger_agent_config.is_ready()`（`WORKFLOW_TRIGGER_AGENT_ENABLED` **かつ** `AI_WORKFLOW_ENABLED`）が2段目のゲートであり、**両方が`True`の場合のみ`WorkflowTriggerAgent`が生成される**。`AI_AGENT_ENABLED=true`のみでは`NewsAgent`しか有効化されない。

`WorkflowConfig` / `WorkflowRunner`はこの時点（DI時）では構築されない。両者の構築は`WorkflowPipelineRunner.run()`が実際に呼ばれた瞬間（＝`act()`が呼ばれた場合のみ）まで遅延される（9章の`WorkflowPipelineRunner`コード例を参照）。

`AgentManager`のpublicインターフェース（`is_available()` / `run()`）・`AgentExecutor`・`BaseAgent`は無変更。

---

## 10. Configuration Design

```
# .env.example への追記（案）
AI_AGENT_ENABLED=false                          # 既存（v2.0.0）
NEWS_AGENT_MIN_INTERVAL_MINUTES=180             # 既存（v2.2.0）
NEWS_AGENT_TIMEOUT_SEC=1800                     # 既存（v2.2.0）
NEWS_AGENT_LOG_LOOKBACK_DAYS=2                  # 既存（v2.2.0）
WORKFLOW_TRIGGER_AGENT_ENABLED=false            # 新規：二重ゲートの2段目（デフォルト無効）
WORKFLOW_TRIGGER_AGENT_MIN_INTERVAL_MINUTES=1440  # 新規：前回Workflow実行から何分空けるか（デフォルト24時間）
```

**二重ゲート方式（Configuration First の強化）**：`AI_AGENT_ENABLED=false`の場合は`NewsAgent`を含め何も生成されない（v2.0.0のまま）。`AI_AGENT_ENABLED=true`でも`WORKFLOW_TRIGGER_AGENT_ENABLED=false`（デフォルト）の場合、`WorkflowTriggerAgentConfig` / `WorkflowPipelineRunner` / `WorkflowTriggerAgent`のいずれのオブジェクトも生成されない。News収集（`NewsAgent`）とWorkflow自動実行（`WorkflowTriggerAgent`、Publishを含む）を独立して制御できることが、この二重ゲートの目的である。

---

## 11. WorkflowTriggerAgent.decide() の判断基準

`outputs/workflow_reports/`配下（`WorkflowRunner._save_report()`が書き込む既存の出力先、v1.20.0）を読み取り専用で走査し、最新のファイル更新日時（mtime）を現在時刻と比較する。

```
1. outputs/workflow_reports/ 配下の *_workflow_report.md を列挙
2. 各ファイルの mtime（最終更新日時）を取得
3. 最新の mtime を採用
   a. ディレクトリが存在しない、またはファイルが1件もない場合
        → should_act=True, reason="Workflow実行レポートが見つからないため初回実行と判断"
   b. 経過時間 >= min_interval_minutes の場合
        → should_act=True, reason="前回Workflow実行から{経過分}分経過（基準: {min_interval_minutes}分）"
   c. 経過時間 < min_interval_minutes の場合
        → should_act=False, reason="前回Workflow実行から{経過分}分のみ経過（基準: {min_interval_minutes}分、あと{残り分}分で実行可能）"
4. ファイル取得に失敗した場合はスキップし、context.warnings に記録する
5. 全てのファイルが取得不能で判断材料が皆無の場合
        → should_act=True（安全側：News Agentと同じ方針。ただしmin_interval_minutesのデフォルトが
          1440分と長いため、実際に連続起動するリスクはNews Agentより低い）
```

`decide()`はファイルの**メタデータ取得のみ**を行い、書き込み・削除・外部API呼び出しは一切行わない。

**既知の制約**：`outputs/workflow_reports/`のファイル名は`YYYYMMDD_workflow_report.md`と日付単位のため、同日内に複数回`WorkflowRunner`を実行すると同一ファイルが上書きされる。この場合、mtimeは「同日内の最新実行時刻」を正しく反映するため実用上は問題ないが、「同日に何回実行されたか」という回数情報は失われる。より正確な履歴が必要になった場合は、専用ログ基盤の追加を将来検討する（16章）。

---

## 12. WorkflowTriggerAgent.act() の実行方式（WorkflowPipelineRunner経由）

### Agent＝判断、PipelineRunner＝実行

`WorkflowTriggerAgent.act()`は`WorkflowPipelineRunner.run(params) -> PipelineResult`という薄いインターフェースのみを呼び出す。`WorkflowRunner`のクラス名・呼び出しシグネチャを`WorkflowTriggerAgent`は一切知らない。

- `WorkflowTriggerAgent`が持つのは`WorkflowPipelineRunner`インスタンスへの参照のみ（コンストラクタでDI）
- `act()`内で`WorkflowRunner`をimportする必要がない
- `workflow_result`は常に`None`（9章の設計ノート参照）

### WorkflowPipelineRunnerがWorkflowRunnerを直接呼び出せる理由

`NewsPipelineRunner`がsubprocessを使う必要があったのは、`main.py`の`argparse`が`sys.argv`を誤読するリスクと、`main()`内の`sys.exit()`がAgentプロセスごと終了させるリスクがあったためである（`docs/design/news_agent_foundation.md` §12）。

`WorkflowRunner`にはこれらの問題がない。`WorkflowRunner.run(article_id, dry_run)`は通常のPythonメソッドであり、`sys.exit()`やCLI引数解析を内部に持たない（それらは`scripts/run_ai_workflow.py`側にのみ存在し、`WorkflowRunner`本体には影響しない）。したがって`WorkflowPipelineRunner`は`WorkflowRunner.run()`を**直接呼び出す薄いラッパー**として実装できる。

### dry_run=Trueで WorkflowRunner が起動しない保証

`WorkflowTriggerAgent.act()`は`AgentExecutor`（v2.0.0、無変更）によって`should_act=True`かつ`context.dry_run=False`の場合のみ呼び出される。したがって：

- `dry_run=True`の場合、`act()`自体が呼ばれない → `WorkflowPipelineRunner.run()`も呼ばれない → `WorkflowRunner.run()`も実行されない → Publishを含む一切の処理は発生しない
- `act()`冒頭に`assert not context.dry_run`を置き、万一の呼び出し経路の誤りを早期検出する（`NewsAgent`と同じ形）

この保証は既存のE2Eテスト（v2.2.0・18番/21番相当）と同じ手法で実測確認済み（15章参照）。

---

## 13. 既存 WorkflowRunner との関係

- `WorkflowRunner` / `WorkflowConfig` / `WorkflowStepExecutor`等、Workflow層本体は**1行も変更しない**。
- `WorkflowTriggerAgent`は`WorkflowRunner`を外部から呼び出す「呼び出し元」であり、`WorkflowRunner`は自分がAgent経由で呼ばれていることを一切意識しない。
- 既存の`python scripts/run_ai_workflow.py`によるユーザーの手動実行フローは影響を受けず、引き続き利用可能。
- 既存の判断材料（`outputs/workflow_reports/*.md`）は`WorkflowTriggerAgent.decide()`の判断材料として**読み取り専用で再利用**する。ファイルの生成ロジック（`WorkflowReportBuilder` / `WorkflowRunner._save_report()`）は変更していない。
- `NewsAgent` / `NewsPipelineRunner`（v2.2.0）とは無関係。`WorkflowTriggerAgent`は`NewsAgent`を一切importしない。

---

## 14. Error Handling

| ケース | 対応 |
|---|---|
| `outputs/workflow_reports/`が存在しない、またはファイルが1件もない（初回実行） | `should_act=True`（安全側デフォルト） |
| ファイルのmtime取得失敗（`OSError`等） | 該当ファイルをスキップし、`context.warnings`に記録。全滅した場合は`should_act=True` |
| `WorkflowRunner.run()`が正常に返るが`overall_success=False` | `PipelineResult(success=False, error_message="Workflow completed with failed steps.")`（固定文言）。`WorkflowTriggerAgent`は例外を投げず`AgentResult`として返す |
| `WorkflowConfig.from_env()` / `WorkflowRunner.from_config()` / `WorkflowRunner.run()`のいずれかで予期せぬ例外が発生 | `WorkflowPipelineRunner`が`try/except Exception`で捕捉し、`PipelineResult(success=False, returncode=None, elapsed_sec=実測値, error_message=str(exc))`を返す。例外は`WorkflowTriggerAgent` / `AgentExecutor`へは伝播しない |
| `AI_AGENT_ENABLED=false` | `NullAgentManager`が空リストを返す（v2.0.0と同じ、変更なし） |
| `AI_AGENT_ENABLED=true`だが`WORKFLOW_TRIGGER_AGENT_ENABLED=false`（デフォルト） | `WorkflowTriggerAgent`は生成されない。`NewsAgent`のみが`executors`に含まれる |
| `AI_WORKFLOW_ENABLED=false`（`WorkflowConfig`側、既存） | `WorkflowRunner.from_config()`が`NullWorkflowRunner`を返す。`WorkflowPipelineRunner.run()`はその`NullWorkflowRunner.run()`を呼び、`overall_success=False`の`WorkflowResult`を受け取ってそのまま`PipelineResult(success=False)`に変換する（特別扱い不要、ダックタイピングで自然に動作する） |

---

## 15. Testing Strategy（実施済み）

### 新規E2Eテスト

`tests/test_e2e_v2_3_0_workflow_trigger_agent_foundation.py`：**110/110 PASS**

- `WorkflowTriggerAgentConfig.from_env()`のデフォルト値（`enabled=False` / `min_interval_minutes=1440` / `workflow_enabled=True`）・環境変数上書き・`AI_WORKFLOW_ENABLED=false`時の`is_ready()=False`
- `WorkflowPipelineRunner.run()`：`WorkflowResult`→`PipelineResult`の変換（成功時／失敗時／例外発生時の3パターン、`WorkflowConfig.from_env` / `WorkflowRunner.from_config`は`unittest.mock.patch.object`でモック化）
- `WorkflowPipelineRunner`が`subprocess`をimportしない・使わないこと（静的検査）
- `WorkflowTriggerAgent.decide()`：レポートなし／ファイル0件／間隔超過／間隔内／新旧混在で最新mtime優先の5パターン（各パターンで`runner.run()`が呼ばれない副作用ゼロも確認）
- `WorkflowTriggerAgent.act()`が`WorkflowPipelineRunner.run()`のみを呼び、`PipelineResult`を`AgentResult`へ変換すること（`workflow_result`は常に`None`）
- `WorkflowTriggerAgent`が`WorkflowRunner`を直接importしないこと（import文の静的検査）
- `dry_run=True`では`act()`自体が呼ばれないこと（`AgentExecutor`経由、実測確認）
- `AgentManager.from_config()`の二重ゲート分岐：4パターン（disabled／`WORKFLOW_TRIGGER_AGENT_ENABLED`未設定／二重ゲートON・`AI_WORKFLOW_ENABLED=true`／二重ゲートON・`AI_WORKFLOW_ENABLED=false`）
- `scripts/run_workflow_trigger_agent.py --dry-run`が`WorkflowRunner.run()`（実Publish含む）を起動しないこと（実サブプロセスで検証、`outputs/workflow_reports/`にファイルが増えないことで確認）
- `src/ai/__init__.py` / `src/pipeline/__init__.py`のexport確認
- `WorkflowRunner` / `NewsAgent` / `NewsPipelineRunner` / `main.py`等19ファイルに変更がないこと（`git diff --quiet`）

### 既存回帰確認

Release 2.3の開発過程で以下を確認した（全てPASS、実Publish・外部API呼び出しは発生させていない）。

- `tests/test_e2e_v2_0_0_ai_agent_foundation.py`：**118/118 PASS**
- `tests/test_e2e_v2_2_0_news_agent_foundation.py`：**120/120 PASS**
- `tests/test_e2e_v1_20_0_ai_workflow_foundation.py`：**170/170 PASS**

**注意**：テスト実施時は`WorkflowConfig.from_env` / `WorkflowRunner.from_config`をモック化し、実際のPublish（WordPress書き込み）や外部API呼び出しが発生しないようにしている。

---

## 16. Future Extensions

- `error_message`の詳細化：現在は失敗時に固定文言`"Workflow completed with failed steps."`を返すのみ。`WorkflowResult.steps`から失敗ステップ名を動的に要約する（例：`"失敗ステップ: rewrite, publish"`）等、より詳細な情報を`error_message`に含める拡張は次バージョン以降で検討する
- `WorkflowResult`の詳細情報（`report_path`・各ステップの`processed_count`等）を`PipelineResult`または`AgentResult`側で保持する設計の再検討。現状は`outputs/workflow_reports/`配下のレポートファイルを直接確認する運用に留めている
- 専用実行ログ基盤（例：`logs/workflow_agent/`）の追加による`decide()`判断精度の向上（同日複数回実行の区別等）
- `PipelineResult`の汎用化・共通Runner Interface（Protocol/ABC）の抽出（Runner実装が3つ目になった段階で検討。実装が2つ（`NewsPipelineRunner` / `WorkflowPipelineRunner`）出揃った時点ではまだ早計と判断し、v2.3.0では見送る）
- `AgentResult.workflow_result`に実際の`WorkflowResult`参照を持たせるかどうかの再検討（9章の設計ノート）
- Publish Agent（`AiPublishService`を直接対象とするAgent）、Scheduler Agent（Windowsタスクスケジューラ統合）への展開
- 重要度別の公開制御との連携
- 長期ビジョン（半自律的なブログ運営支援）は`docs/ROADMAP.md`を参照

---

## 17. Definition of Done

### コード

- [x] `WorkflowTriggerAgentConfig`（`src/ai/workflow_trigger_agent_config.py`）
- [x] `WorkflowPipelineRunner`（`src/pipeline/workflow_pipeline_runner.py`、subprocess不使用・`WorkflowRunner.run()`を直接呼ぶ薄いラッパー）
- [x] `WorkflowTriggerAgent`（`src/ai/workflow_trigger_agent.py`、`WorkflowRunner`を直接importしない）
- [x] `AgentManager.from_config()`の`executors`更新（二重ゲート方式：`AI_AGENT_ENABLED` × `WorkflowTriggerAgentConfig.is_ready()`）
- [x] `scripts/run_workflow_trigger_agent.py`（`--dry-run` / `--article-id` / `--workflow-dry-run`対応）
- [x] `src/ai/__init__.py` / `src/pipeline/__init__.py`への新規シンボルのexport追加

### テスト

- [x] `tests/test_e2e_v2_3_0_workflow_trigger_agent_foundation.py`：110/110 PASS
- [x] 既存回帰確認：`v2.0.0`（118/118 PASS）・`v2.2.0`（120/120 PASS）・`v1.20.0`（170/170 PASS）
- [x] `dry_run=True`で`act()`（ひいては`WorkflowRunner.run()`）が起動しないことの実測確認
- [x] 二重ゲート（`AI_AGENT_ENABLED` × `WORKFLOW_TRIGGER_AGENT_ENABLED` × `AI_WORKFLOW_ENABLED`）の4組み合わせ確認
- [x] Architecture Guard：`WorkflowTriggerAgent`が`WorkflowRunner`を直接importしないこと・`WorkflowPipelineRunner`が`subprocess`を使わないことの静的検査
- [x] `main.py` / `WorkflowRunner`本体 / `NewsAgent` / `NewsPipelineRunner`等19ファイルが無変更であることの`git diff`確認

### ドキュメント

- [x] 本設計書（実装完了後に記述を実装と整合させる更新を実施済み）
- [ ] `CHANGELOG.md` / `ROADMAP.md`への記載（Release 2.3の対象範囲外、別途実施）
- [ ] `docs/architecture.md`への追記（Release 2.3の対象範囲外、別途実施）

### リリース

- [ ] コミット・push（Release Review後）
