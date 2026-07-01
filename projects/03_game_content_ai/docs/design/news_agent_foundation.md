# v2.2.0 News Agent Foundation 設計書

作成日：2026-07-01
状態：実装完了（Step 1〜6完了、本ドキュメントはStep 7で確定版として保存）

---

## 1. Goal

v2.0.0で作られたAgent Foundation（`BaseAgent` / `AgentExecutor` / `AgentManager`）に、初めて具体的なAgent実装 **`NewsAgent`** を追加する。`NewsAgent`は「ゲームニュース収集そのもの」ではなく「ゲームニュース収集を今実行すべきかを判断する」上位レイヤーであり、判断がYesの場合のみ既存のニュース収集パイプライン（`main.py`）を、新設した実行層 **`NewsPipelineRunner`** 経由で安全に起動する。

---

## 2. Background

- v1.0〜v1.20.0で「ニュース収集→記事化→投稿」（`main.py`）と「投稿済み記事の改善」（`WorkflowRunner`）という2つの実行系が完成している。いずれも**人間が手動でスクリプトを起動**する前提。
- v2.0.0でAgent Foundation（判断のための骨組み）が作られたが、`AgentManager.from_config()`の`executors`は空リストのままで、具体的なAgentは1つも存在しなかった。
- v2.1.0のROADMAPで「News Agent Foundation」が次の候補として明記され、Project Charter承認・Architecture Review（Approve）を経て本バージョンで実装した。
- 設計レビューの過程で「Agentがsubprocessを直接実行する」設計は責務混同につながると判断され、**Agent（判断）とPipelineRunner（実行）を分離する**方針に修正した。これにより、将来のWorkflow Trigger Agent / Publish Agent / Scheduler Agentが同じ実行層の形を再利用できる土台となっている。

---

## 3. Scope

### 実装対象

- `NewsAgentConfig`（`src/ai/news_agent_config.py`）：判断・実行双方の設定値
- `PipelineResult`（`src/pipeline/pipeline_result.py`）：実行層の共通結果データクラス
- `NewsPipelineRunner`（`src/pipeline/news_pipeline_runner.py`）：`main.py`をsubprocessとして起動する実行層
- `NewsAgent`（`src/ai/news_agent.py`、`BaseAgent`継承）：`decide()` / `act()` / `name()`
- `AgentManager.from_config()`の`executors`への`NewsAgent`用`AgentExecutor`のDI
- `scripts/run_news_agent.py`：手動実行用の最小CLIエントリ

### 対象外

- `main.py` / `collector.py` / `keyword_filter.py` / `duplicate_filter.py` / `importance_judge.py` / `article_generator.py`等、既存ニュース収集パイプライン本体の改修
- `WorkflowRunner`（v1.20.0）・`BaseAgent` / `AgentExecutor` / `AgentContext` / `AgentDecision` / `AgentResult`の変更
- Windowsタスクスケジューラ統合
- 自動投稿・公開ロジックの新規追加

---

## 4. Non Goal

- `NewsAgent`は収集ロジックを**一切持たない**。実際の収集・記事化・投稿はすべて既存パイプライン（`main.py`）に委譲する。
- `NewsAgent`は実行方式（subprocess等）を**一切知らない**。実行方式は`NewsPipelineRunner`に完全に閉じ込める。
- `main.py`への直接的なコード変更は行わない（後述13章の通り、サブプロセス方式を採用するため`main.py`は無改修で済む）。
- `dry_run=True`の場合、`NewsAgent.act()`自体が呼ばれない（v2.0.0の`AgentExecutor`設計により構造的に保証）。判断ロジック（`decide()`）のみが実行され、既存パイプラインは絶対に起動しない。
- 判断基準の高度化（ニュースの重要度先読み等）は将来のバージョンに委ねる。v2.2.0は「経過時間ベースの単純な判断」に限定する。

---

## 5. User Workflow

### Before（v2.1.0まで）

- ブロガーが`python main.py`を手動実行するか、将来的にタスクスケジューラで無条件実行する必要があった。「今収集すべきか」の判断はブロガー自身が行っていた。

### After（v2.2.0）

- `AI_AGENT_ENABLED=false`（デフォルト）の場合：挙動は一切変わらない。`python main.py`の手動実行がそのまま利用可能。
- `AI_AGENT_ENABLED=true`の場合：`python scripts/run_news_agent.py`を実行すると、`NewsAgent`が「前回実行からの経過時間」を根拠に収集要否を判断し、必要な場合のみ`NewsPipelineRunner`経由で既存パイプラインを起動する。
- `--dry-run`を付けた場合：判断結果（実行すべきか、その理由）のみ表示し、実際の収集は行わない。

---

## 6. System Workflow

```
scripts/run_news_agent.py [--dry-run] [--max-articles N]
  → AgentConfig.from_env()
  → AgentManager.from_config(config)
       is_ready()=False → NullAgentManager（v2.0.0のまま変更なし）
       is_ready()=True  → executors=[
                             AgentExecutor(
                               NewsAgent(
                                 config=NewsAgentConfig.from_env(project_root=config.base_dir),
                                 runner=NewsPipelineRunner(news_agent_config),
                               )
                             )
                           ]
  → AgentManager.run(AgentTask(task_id="collect_news", params={...}), dry_run=...)
       → AgentExecutor.execute(context)          ← v2.0.0のまま変更なし
            1. NewsAgent.decide(context)
                 - logs/execution/*.jsonl を読み取り専用で走査（副作用なし）
            2. should_act=False、または dry_run=True の場合
                 → act() を呼ばず AgentExecutor が AgentResult を組み立てる
                   （NewsPipelineRunner へは到達しない。既存パイプラインは絶対に起動しない）
            3. should_act=True かつ dry_run=False の場合のみ
                 → NewsAgent.act(decision, context)
                      → NewsPipelineRunner.run(params=context.task.params)
                           → subprocess.run([python_executable, main_py_path],
                                             cwd=working_directory, timeout=timeout_sec)
                           → stdout/stderr を working_directory/logs/news_agent/ に保存
                           → PipelineResult を返す
                      → NewsAgent が PipelineResult を AgentResult に変換
  → AgentResult のリストを返す
```

`NewsAgent`は`WorkflowRunner`を一切呼び出さない。`WorkflowRunner`（記事改善系）を呼び出す将来の「Workflow Trigger Agent」とは**別系統のAgent**である。

---

## 7. Data Model

### `NewsAgentConfig`（`src/ai/news_agent_config.py`）

| フィールド | 型 | デフォルト | 内容 |
|---|---|---|---|
| `min_interval_minutes` | `int` | `180`（`NEWS_AGENT_MIN_INTERVAL_MINUTES`） | 前回実行からこの分数以上経過していない場合は`should_act=False` |
| `timeout_sec` | `int` | `1800`（`NEWS_AGENT_TIMEOUT_SEC`） | `NewsPipelineRunner`がサブプロセスを待つ最大秒数 |
| `log_lookback_days` | `int` | `2`（`NEWS_AGENT_LOG_LOOKBACK_DAYS`） | 実行履歴を遡って探索する日数 |
| `main_py_path` | `Path` | `project_root / "main.py"` | 起動対象スクリプトの絶対パス |
| `working_directory` | `Path` | `project_root` | サブプロセスの`cwd`、および`logs/`の基準ディレクトリ |
| `python_executable` | `Path` | `sys.executable` | 起動に使うPythonインタプリタ（Agentを実行しているものと同じ） |

`NewsPipelineRunner`はこれらの値をすべて`NewsAgentConfig`から受け取り、ファイル名や実行環境を自ら決め打ちしない（Architecture Reviewでの指摘を反映）。

### `PipelineResult`（`src/pipeline/pipeline_result.py`）

| フィールド | 型 | 内容 |
|---|---|---|
| `success` | `bool` | 実行が成功したか（`returncode == 0`） |
| `returncode` | `int \| None` | 子プロセスの終了コード（タイムアウト時は`None`） |
| `elapsed_sec` | `float` | 実行にかかった秒数 |
| `stdout_log_path` | `Path \| None` | 標準出力を保存したログファイルのパス |
| `stderr_log_path` | `Path \| None` | 標準エラー出力を保存したログファイルのパス |
| `error_message` | `str \| None` | 失敗時のメッセージ（成功時は`None`） |

`AgentResult`（Agent層の型）とは独立した型。`to_dict()` / `to_json()`を実装（既存の`AgentResult` / `WorkflowResult`と同じ形式）。

### `AgentTask.params`（既存構造の再利用）

| キー | 型 | 内容 |
|---|---|---|
| `max_articles` | `int`（任意） | 指定時は`NewsPipelineRunner`が`main.py --max-articles N`として渡す |

---

## 8. Directory Structure

```
src/
├── ai/
│   ├── （既存ファイル、v2.0.0まで無変更）
│   ├── news_agent_config.py   # NewsAgentConfig
│   └── news_agent.py          # NewsAgent（BaseAgent継承。判断＋委譲のみ）
│
└── pipeline/                  # 新規パッケージ（実行層。将来の共通基盤）
    ├── __init__.py            # PipelineResult / NewsPipelineRunner をexport
    ├── pipeline_result.py     # PipelineResult
    └── news_pipeline_runner.py  # NewsPipelineRunner

scripts/
└── run_news_agent.py          # 手動実行エントリ

tests/
└── test_e2e_v2_2_0_news_agent_foundation.py
```

`src/pipeline/`を`src/ai/`とは別パッケージとして独立させている。実行層（Pipeline）が判断層（Agent）に依存しない構造であることをディレクトリ構成上も明示するため。

`main.py` / `src/collector.py`等の既存ニュース収集パイプラインは1行も変更していない。

---

## 9. Module Design

### `NewsAgentConfig`

```python
@dataclass
class NewsAgentConfig:
    min_interval_minutes: int
    timeout_sec: int
    log_lookback_days: int
    main_py_path: Path
    working_directory: Path
    python_executable: Path

    @classmethod
    def from_env(cls, project_root: Path) -> "NewsAgentConfig": ...
```

### `PipelineResult`

```python
@dataclass
class PipelineResult:
    success: bool
    returncode: int | None
    elapsed_sec: float
    stdout_log_path: Path | None
    stderr_log_path: Path | None
    error_message: str | None

    def to_dict(self) -> dict: ...
    def to_json(self) -> str: ...
```

### `NewsPipelineRunner`

```python
class _RunnerConfig(Protocol):
    """Agent層の型への依存を避けるためのダックタイピング用Protocol。"""
    python_executable: Path
    main_py_path: Path
    working_directory: Path
    timeout_sec: int


class NewsPipelineRunner:
    def __init__(self, config: _RunnerConfig):
        self._config = config

    def run(self, params: dict) -> PipelineResult:
        """main.py を起動し、実行結果を PipelineResult として返す。"""
        ...
```

`NewsAgentConfig`を直接importせず、実行に必要な4属性を持つオブジェクトであれば何でも受け取れる`Protocol`でダックタイピングにしている。これにより`src/pipeline/`パッケージは`src/ai/`パッケージを一切importしない（一方向の依存：`ai → pipeline`）。

### `NewsAgent`

```python
class NewsAgent(BaseAgent):
    def __init__(self, config: NewsAgentConfig, runner: NewsPipelineRunner):
        self._config = config
        self._runner = runner

    def name(self) -> str:
        return "news_agent"

    def decide(self, context: AgentContext) -> AgentDecision: ...

    def act(self, decision: AgentDecision, context: AgentContext) -> AgentResult:
        assert not context.dry_run
        result = self._runner.run(params=context.task.params)
        return AgentResult(..., workflow_result=None, success=result.success,
                            error_message=result.error_message, ...)
```

### `AgentManager.from_config()`（DI配線のみ更新）

```python
@classmethod
def from_config(cls, config: AgentConfig) -> "AgentManager | NullAgentManager":
    if not config.is_ready():
        return NullAgentManager()

    news_agent_config = NewsAgentConfig.from_env(project_root=config.base_dir)
    news_pipeline_runner = NewsPipelineRunner(news_agent_config)
    news_agent = NewsAgent(config=news_agent_config, runner=news_pipeline_runner)

    executors: list[AgentExecutor] = [AgentExecutor(news_agent)]
    return cls(config=config, executors=executors)
```

`AgentManager`のpublicインターフェース（`is_available()` / `run()`）・`AgentExecutor`・`BaseAgent`は無変更。

---

## 10. Configuration Design

```
# .env.example への追記（案。.env.example自体の更新は本バージョンでは未実施）
AI_AGENT_ENABLED=false                  # 既存（v2.0.0）
NEWS_AGENT_MIN_INTERVAL_MINUTES=180     # 新規：前回収集から何分空けるか
NEWS_AGENT_TIMEOUT_SEC=1800             # 新規：サブプロセスのタイムアウト秒数
NEWS_AGENT_LOG_LOOKBACK_DAYS=2          # 新規：実行履歴を遡る日数
```

**Configuration First**：`AI_AGENT_ENABLED=false`（デフォルト）では`NewsAgentConfig` / `NewsPipelineRunner` / `NewsAgent`のいずれのオブジェクトも生成されない。`NEWS_AGENT_*`系の変数は`AI_AGENT_ENABLED=true`のときのみ意味を持つ。

---

## 11. NewsAgent.decide() の判断基準

直近の実行ログ（`logs/execution/*.jsonl`、v1.8.0 Logging Foundationの既存ファイル）から最新の`finished_at`を読み取り専用で取得し、現在時刻との経過時間を`min_interval_minutes`と比較する。

```
1. logs/execution/ 配下を、当日分から log_lookback_days 日分遡って走査
2. 各ファイルをJSON Lines形式でパースし、finished_at を収集
3. 最新の finished_at を採用
   a. ログが1件も見つからない場合
        → should_act=True, reason="実行履歴が見つからないため初回実行と判断"
   b. 経過時間 >= min_interval_minutes の場合
        → should_act=True, reason="前回実行から{経過分}分経過（基準: {min_interval_minutes}分）"
   c. 経過時間 < min_interval_minutes の場合
        → should_act=False, reason="前回実行から{経過分}分のみ経過（基準: {min_interval_minutes}分、あと{残り分}分で実行可能）"
4. 壊れたJSON行・読み取り失敗はスキップし、context.warnings に記録する
5. 全てのログが読み取り不能で判断材料が皆無の場合
        → should_act=True（安全側：収集が永久停止することを避ける）
```

`decide()`はファイルの**読み取りのみ**を行い、書き込み・削除・外部API呼び出しは一切行わない。

---

## 12. NewsAgent.act() の実行方式（NewsPipelineRunner経由）

### Agent＝判断、PipelineRunner＝実行

設計レビューの結果、`NewsAgent`が`subprocess.run()`を直接呼び出す設計は不採用とした。`NewsAgent.act()`は`NewsPipelineRunner.run(params) -> PipelineResult`という薄いインターフェースのみを呼び出し、実行方式（subprocess／将来的なimport呼び出し／API呼び出し等）は一切知らない。

```python
def act(self, decision: AgentDecision, context: AgentContext) -> AgentResult:
    assert not context.dry_run
    result = self._runner.run(params=context.task.params)
    return AgentResult(
        ..., action_taken=True, success=result.success,
        workflow_result=None, error_message=result.error_message,
        warnings=[...stdout/stderrログパス...],
    )
```

- `NewsAgent`が持つのは`NewsPipelineRunner`インスタンスへの参照のみ（コンストラクタでDI）
- `act()`内で`subprocess`をimportする必要がない
- `workflow_result`は常に`None`（`NewsPipelineRunner`は`WorkflowRunner`ではないため）

### main.pyを直接importしない理由（NewsPipelineRunner側の設計判断）

1. `main()`関数内部で`argparse.ArgumentParser().parse_args()`が`sys.argv`を読む。別スクリプトから直接importして呼び出すと、そのスクリプト自身の引数を`main.py`のargparseが誤って解釈しうる。
2. `main()`はエラー条件（APIキー未設定、ニュース0件等）で複数箇所`sys.exit()`を呼んでいる。直接importして呼び出すと、これが**Agentプロセスそのものを強制終了させる**（`sys.exit()`は`SystemExit`を送出するため、通常の`except Exception`では捕捉されない）。
3. `main.py`本体を「大規模改修しない」という制約上、上記2点を安全にするための構造変更（argparse分離・sys.exit除去）は本バージョンのスコープ外とした。

→ そのため`NewsPipelineRunner`は`subprocess.run([python_executable, main_py_path], cwd=working_directory, timeout=timeout_sec)`でPythonの独立プロセスとして起動する。`main.py`内で`sys.exit()`が呼ばれても影響範囲はサブプロセス内に閉じ、Agentプロセス（および呼び出し元の`NewsAgent`）は継続する。

### dry_run=Trueでmain.pyが起動しない保証

`NewsAgent.act()`は`AgentExecutor`（v2.0.0、無変更）によって`should_act=True`かつ`context.dry_run=False`の場合のみ呼び出される。したがって：

- `dry_run=True`の場合、`act()`自体が呼ばれない → `NewsPipelineRunner.run()`も呼ばれない → `subprocess.run()`も実行されない → `main.py`は起動しない
- `act()`冒頭に`assert not context.dry_run`を置き、万一の呼び出し経路の誤り（契約違反）を早期検出する

この保証はE2Eテスト（18番・21番、後述15章）で実測確認済み。

---

## 13. 既存 main.py / ニュース収集パイプラインとの関係

- `main.py`・`collector.py`・`keyword_filter.py`・`duplicate_filter.py`・`importance_judge.py`・`article_generator.py`・`outputs/`配下は**1行も変更していない**（`git diff`で無変更を確認済み）。
- `NewsAgent`は`main.py`を外部プロセスとして起動する「呼び出し元」であり、既存パイプラインは自分がAgent経由で呼ばれていることを一切意識しない。
- 既存の`python main.py`によるユーザーの手動実行フローは影響を受けず、引き続き利用可能。
- 既存の実行ログ（`logs/execution/*.jsonl`）は`NewsAgent.decide()`の判断材料として**読み取り専用で再利用**する。ログの形式・書き込みロジック（`LogManager`）は変更していない。
- `WorkflowRunner`（v1.20.0）とは無関係。`NewsAgent`は`WorkflowRunner`を一切importしない。

---

## 14. Error Handling

| ケース | 対応 |
|---|---|
| 実行ログが1件も見つからない（初回実行、または`LOG_ENABLED=false`） | `should_act=True`（安全側デフォルト） |
| 実行ログのパース失敗（壊れたJSON行等） | 該当行をスキップし、`context.warnings`に記録。全滅した場合は`should_act=True` |
| `subprocess.run()`が異常終了（`returncode != 0`） | `PipelineResult(success=False, error_message=stderr末尾500字)`。`NewsAgent`は例外を投げず`AgentResult`として返す |
| `subprocess.run()`がタイムアウト | `PipelineResult(success=False, returncode=None, error_message="タイムアウトしました（N秒）")` |
| `AI_AGENT_ENABLED=false` | `NullAgentManager`が空リストを返す（v2.0.0と同じ、変更なし） |
| `decide()` / `act()`内で予期せぬ例外 | `AgentExecutor`の既存try/exceptで捕捉、`context.errors`に記録（v2.0.0の設計をそのまま利用） |

---

## 15. Testing Strategy（実施済み）

### 新規E2Eテスト

`tests/test_e2e_v2_2_0_news_agent_foundation.py`：**117/117 PASS**

- `NewsAgentConfig.from_env()`のデフォルト値・環境変数上書き
- `PipelineResult.to_dict()` / `to_json()`
- `NewsPipelineRunner`：成功／失敗／タイムアウト時の`PipelineResult`（`subprocess.run`はモック化）
- `NewsPipelineRunner`がstdout/stderrを`logs/news_agent/`に保存すること
- `NewsPipelineRunner`が`max_articles`を`--max-articles`として渡すこと
- `NewsPipelineRunner`がAgent層の型・`WorkflowRunner`をimportしないこと（import文の静的検査）
- `NewsAgent.decide()`：履歴なし／間隔超過／間隔内／壊れたJSON行の4パターン
- `NewsAgent.act()`が`NewsPipelineRunner.run()`のみを呼び、`PipelineResult`を`AgentResult`へ変換すること（`workflow_result`は常に`None`）
- `dry_run=True`では`NewsPipelineRunner.run()`が呼ばれないこと（`AgentExecutor`経由）
- `AgentManager.from_config()`の`AI_AGENT_ENABLED` false/true分岐
- `scripts/run_news_agent.py --dry-run`が`main.py`を起動しないこと（実サブプロセス実行、`logs/news_agent/`にファイルが増えないことで確認）
- `src/ai/__init__.py` / `src/pipeline/__init__.py`のexport確認
- `WorkflowRunner` / `main.py` / 既存ニュース収集パイプラインに変更がないこと（`git diff --quiet`）

### 既存回帰確認

v1.9.0〜v1.20.0・v2.0.0の既存E2Eテスト13ファイル：**合計1153/1153 PASS**（外部APIを呼ばないテストのみ、`main.py`は起動せず実施）。

`test_e2e_v1_10_0_analytics_foundation.py`は`docs/CHANGELOG.md`記載の既知問題（Known Issues [KI-1]）により実行時に`FileNotFoundError`でクラッシュするが、v2.2.0の変更とは無関係であることを確認済み（`src/analytics/`は本バージョンの変更対象外）。

---

## 16. Future Extensions

- Phase 2：**Workflow Trigger Agent**（v2.3.0候補） — `WorkflowRunner`（v1.20.0）は既にimport可能なクラスであり`sys.exit()`問題がないため、`WorkflowPipelineRunner`は「subprocessではなく`WorkflowRunner.run()`を直接呼ぶ薄いラッパー」として実装できる可能性がある。いずれにせよ`WorkflowTriggerAgent`は`WorkflowPipelineRunner.run(params) -> PipelineResult`のみを知り、実行方式の違いは`src/pipeline/`層に閉じる
- Phase 3：**Publish Agent** — `AiPublishService`（v1.18.0）を呼び出す`PublishPipelineRunner`を追加
- Phase 4：**Scheduler Agent** — Windowsタスクスケジューラとの統合を担う`SchedulerPipelineRunner`
- 上記が出揃った段階（Runner実装が2つ以上になった時点）で、`PipelineRunner`共通インターフェース（Protocol/ABC）を`src/pipeline/`に抽出することを検討する。**v2.2.0時点では抽象化を先取りしない**（実装が1つしかない段階で共通基底クラスを作ると、将来の実際の差異に対して誤った抽象化になるリスクがあるため）
- 長期ビジョン（半自律的なブログ運営支援）は`docs/ROADMAP.md`を参照

---

## 17. Definition of Done

### コード

- [x] `NewsAgentConfig`（`src/ai/news_agent_config.py`）
- [x] `PipelineResult` / `NewsPipelineRunner`（`src/pipeline/`）
- [x] `NewsAgent`（`src/ai/news_agent.py`）
- [x] `AgentManager.from_config()`の`executors`更新
- [x] `scripts/run_news_agent.py`

### テスト

- [x] `tests/test_e2e_v2_2_0_news_agent_foundation.py`: 117/117 PASS
- [x] 既存回帰確認：13ファイル合計1153/1153 PASS（v1.10.0 Known Issue除く）
- [x] `dry_run=True`で`main.py`が起動しないことの実測確認

### ドキュメント

- [x] 本設計書
- [x] `CHANGELOG.md` / `ROADMAP.md`への記載
- [x] `docs/architecture.md`にPipeline層として追記

### リリース

- [ ] コミット・push（Release Review後）
