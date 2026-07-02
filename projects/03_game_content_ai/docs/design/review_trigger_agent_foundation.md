# v2.5.0 Review Trigger Agent Foundation 設計書

作成日：2026-07-02
状態：Architecture Design 確定（実装未着手）。`docs/design/review_trigger_agent_charter.md`（Project Charter）の Open Questions を本ドキュメントで確定する。

---

## 1. Goal

v2.0.0で作られたAgent Foundation（`BaseAgent` / `AgentExecutor` / `AgentManager`）に、`AiPublishReviewService`（v1.19.0、WordPress下書き投稿後の**公開前レビューレポート生成**）の起動タイミングを判断する4つ目の具体的なAgent **`ReviewTriggerAgent`**を追加する。`ReviewTriggerAgent`は「レビューレポート生成そのもの」ではなく「レビューレポート生成を今実行すべきかを判断する」上位レイヤーであり、判断がYesの場合のみ新設した実行層 **`ReviewPipelineRunner`** 経由で`AiPublishReviewService`を起動する。

```
ReviewTriggerAgent   （判断：起動すべきか）
      ↓
ReviewPipelineRunner （実行：起動する）
      ↓
AiPublishReviewService（既存のサービス、v1.19.0、無改修）
```

`NewsAgent`（v2.2.0）・`WorkflowTriggerAgent`（v2.3.0）・`PublishTriggerAgent`（v2.4.0）と同じ「Agent（判断）→ Pipeline（実行）→ 対象Service」パターンの4例目として実装する。

---

## 2. Background

`docs/design/review_trigger_agent_charter.md`（Project Charter、2026-07-02作成）を前提とする。Charterで確認した事実：

- `AiPublishReviewService`は`outputs/ai_publishes/`（投稿結果JSON）を読み込み、`outputs/ai_publish_reviews/`（レビューJSON）と`outputs/ai_publish_review_reports/`（Markdownレポート）を生成する**非破壊・読み取り確認のみ**のService。WordPress書き込み・Claude API呼び出しは一切行わない。
- 現状は`scripts/run_ai_publish_review.py`による**手動実行**が唯一の実行経路。
- `AiPublishReviewService`には`main.py` / `WorkflowRunner` / `AiPublishService`と異なり、独自の`Config`クラスも`is_ready()`も存在しない（`from_paths()`のみで構築可能、常時実行できる設計）。

Charterで残していたOpen Questionsを、本ドキュメントの3章以降で確定する。

---

## 3. Scope

### 実装対象

- `ReviewTriggerAgentConfig`（`src/ai/review_trigger_agent_config.py`）：判断・実行双方の設定値
- `ReviewPipelineRunner`（`src/pipeline/review_pipeline_runner.py`）：`AiPublishReviewService.run()`を直接呼び出す実行層
- `ReviewTriggerAgent`（`src/ai/review_trigger_agent.py`、`BaseAgent`継承）：`decide()` / `act()` / `name()`
- `AgentManager.from_config()`の`executors`への`ReviewTriggerAgent`用`AgentExecutor`のDI（二重ゲート方式）
- `scripts/run_review_trigger_agent.py`：手動実行用の最小CLIエントリ
- `tests/test_e2e_v2_5_0_review_trigger_agent_foundation.py`：新規E2Eテスト（実装フェーズで作成）

### 対象外

- `AiPublishReviewService` / `AiPublishReviewRepository` / `AiPublishReviewReportBuilder`等、Review層本体の改修
- `ImprovementReviewService`（v1.15.0）・`RewriteReviewService`（v1.17.0）への対応（Charter §3参照、対象外）
- `NewsAgent` / `WorkflowTriggerAgent` / `PublishTriggerAgent`・それぞれの`PipelineRunner`・`BaseAgent` / `AgentExecutor` / `AgentContext` / `AgentDecision` / `AgentResult` / `AgentConfig`の改修
- `review_status`（PENDING固定）を人が更新する機能
- 新しい実行ログ基盤の追加
- `PipelineResult`の汎用化・共通Runner Interfaceの抽出（Runner実装が4つ目になるが、v2.4.0設計書と同じ理由で見送り）
- `.env.example`のドキュメント負債解消（別タスク、Charter §3参照）

---

## 4. Non Goal

- `ReviewTriggerAgent`はAiPublishReviewService本体の責務を変更しない。レビューロジック・Markdown生成は一切持たない
- `ReviewTriggerAgent`は`AiPublishReviewService`の起動方法を一切知らない。起動方法は`ReviewPipelineRunner`に完全に閉じ込める
- `AiPublishReviewService`は読み取り専用Serviceのため、WordPressへの書き込みは構造的に発生しない（対象Service自体の性質による安全性であり、Agent層の設計に起因するものではない）
- `outputs/ai_publishes/`・`outputs/ai_publish_reviews/`の中身（投稿結果件数・レビュー内容等）を`ReviewTriggerAgent`が解析することはしない（6章参照。`decide()`は`outputs/ai_publish_review_reports/`のファイルメタデータ［mtime］のみを見る）
- 複数Review系Service（Improvement/Rewrite/Publish）を横断的に判断する汎用Agentは作らない
- Windowsタスクスケジューラ統合、重要度別の公開制御などの長期ビジョン項目は対象外

---

## 5. User Workflow

### Before（v2.4.0まで）

- ブロガーが`python scripts/run_ai_publish_review.py`を手動実行する必要があった。「今レビューレポートを生成すべきか」の判断はブロガー自身が行っていた。

### After（v2.5.0）

- `AI_AGENT_ENABLED=false`（デフォルト）の場合：挙動は一切変わらない。
- `AI_AGENT_ENABLED=true`だが`REVIEW_TRIGGER_AGENT_ENABLED=false`（デフォルト）の場合：`ReviewTriggerAgent`は生成されない（`NewsAgent`・条件を満たせば`WorkflowTriggerAgent` / `PublishTriggerAgent`のみが有効化される）。
- `AI_AGENT_ENABLED=true` **かつ** `REVIEW_TRIGGER_AGENT_ENABLED=true`の場合のみ：`python scripts/run_review_trigger_agent.py`（または将来のAgentManager一括実行）を実行すると、`ReviewTriggerAgent`が「前回レビューレポート生成からの経過時間」を根拠に実行要否を判断し、必要な場合のみ`ReviewPipelineRunner`経由で`AiPublishReviewService`を起動する。
- `--dry-run`を付けた場合：判断結果（実行すべきか、その理由）のみ表示し、実際のレビューレポート生成は行わない。

---

## 6. Gate方式（Open Question #1 の結論）

**結論：二重ゲート方式を採用する。**

```
AI_AGENT_ENABLED（AgentConfig.is_ready()）
    ×
REVIEW_TRIGGER_AGENT_ENABLED（ReviewTriggerAgentConfig.is_ready()）
```

### 理由

- `AiPublishReviewService`には`Config`クラスも`is_ready()`も存在しない（2章）。`WorkflowTriggerAgent` / `PublishTriggerAgent`の3段目は「対象Service側の`is_ready()`を再利用する」ことで実現していたが、再利用する対象が存在しないため、無理に3段目を作らない。
- 3段目を「実装するために」新設する（例：`AiPublishReviewConfig`を`AiPublishReviewService`に後付けする）ことは、対象Service本体の改修になり、3章「対象外」に反する。
- `AiPublishReviewService`は読み取り専用・非破壊であり、`AiPublishService`（WordPress書き込み）や`WorkflowRunner`（Publishを含む）ほど安全側に倒す必要性が低い。二重ゲートでも安全性は十分に確保できる。
- `ReviewTriggerAgentConfig.is_ready()`は`self.enabled`のみを返す（`WorkflowTriggerAgentConfig` / `PublishTriggerAgentConfig`のように`enabled and xxx_enabled`という2項ではなく、他Serviceのゲートを合成する要素がないため単項になる）。

### `AgentManager.from_config()`への影響（Open Question #6 の結論）

`NewsAgent` / `WorkflowTriggerAgent` / `PublishTriggerAgent`のDIブロックの後に、以下を追加する（既存3ブロックの並び方をそのまま踏襲。3ブロックはいずれも改修しない）。

```python
review_trigger_agent_config = ReviewTriggerAgentConfig.from_env(
    project_root=config.base_dir
)
if review_trigger_agent_config.is_ready():
    review_pipeline_runner = ReviewPipelineRunner(review_trigger_agent_config)
    review_trigger_agent = ReviewTriggerAgent(
        config=review_trigger_agent_config,
        runner=review_pipeline_runner,
    )
    executors.append(AgentExecutor(review_trigger_agent))
```

`config.is_ready()`（`AI_AGENT_ENABLED`）が1段目、`review_trigger_agent_config.is_ready()`（`REVIEW_TRIGGER_AGENT_ENABLED`）が2段目。4つのAgentは`executors`リストに独立して並び、互いに依存しない。

---

## 7. Data Model

### `ReviewTriggerAgentConfig`（`src/ai/review_trigger_agent_config.py`）

| フィールド | 型 | デフォルト | 内容 |
|---|---|---|---|
| `enabled` | `bool` | `False`（`REVIEW_TRIGGER_AGENT_ENABLED`） | 二重ゲートの2段目。`False`の場合`is_ready()`は`False`になる |
| `min_interval_minutes` | `int` | `1440`（`REVIEW_TRIGGER_AGENT_MIN_INTERVAL_MINUTES`） | 前回レビューレポート生成からこの分数以上経過していない場合は`should_act=False`。`WorkflowTriggerAgent` / `PublishTriggerAgent`と同じ24時間をデフォルトとする（8章参照） |
| `reports_dir` | `Path` | `project_root / "outputs" / "ai_publish_review_reports"` | 判断材料として走査するディレクトリ（`AiPublishReviewService._save_report()`の既存出力先） |
| `project_root` | `Path` | 呼び出し元から渡される値 | プロジェクトルート。`reports_dir`の組み立てや`AiPublishReviewService.from_paths(base_dir=...)`への引き渡しに使う |

`is_ready()`は`self.enabled`を返す（6章参照）。`reports_dir`がディスク上に実在するかどうかは`is_ready()`の判定に含めない（初回実行時も`is_ready()=True`とし、実際の存在確認は`decide()`側の責務とする。既存3Agentと同じ方針）。

### `PipelineResult`（`src/pipeline/pipeline_result.py`、既存型を無改修で流用）

`ReviewPipelineRunner.run()`は`AiPublishReviewService.run()`の戻り値を以下のルールで`PipelineResult`にマッピングする（`PublishPipelineRunner`と同じ変換方針）。

| フィールド | 値 | 理由 |
|---|---|---|
| `success` | `report_path is not None`（保存したMarkdownレポートのパスが返ってきたか） | `AiPublishReviewService.get_reviews()`は`article_id`絞り込みのみで過去の全レビュー履歴を返すため、件数を`success`判定に使うと過去の結果まで巻き込んでしまう。`PublishPipelineRunner`と同じ理由で`run()`の戻り値のみを根拠にする |
| `returncode` | `None`固定 | subprocessではないため終了コードの概念がない |
| `elapsed_sec` | `ReviewPipelineRunner.run()`呼び出し全体を`time.time()`差分で実測した値 | `AiPublishReviewService.from_paths()`の構築時間も含めた壁時計時間をそのまま計測する |
| `stdout_log_path` | `None`固定 | subprocessではないため標準出力の概念がない |
| `stderr_log_path` | `None`固定 | 同上 |
| `error_message` | 失敗時（`report_path is None`）：固定文言`"Review report was not saved."`／例外発生時：`str(exc)`／成功時：`None` | 既存3Runnerと同じく、最初は簡潔な実装とする |

`service.get_reviews(article_id=...)`は保存結果を読み戻せるか（正常に完了したか）の確認目的でのみ呼び出し、戻り値は`PipelineResult`には反映しない（`PublishPipelineRunner`が`service.get_results()`を同目的で呼ぶのと同じパターン）。

### `AgentTask.params`（既存構造の再利用）

| キー | 型 | 内容 |
|---|---|---|
| `article_id` | `str`（任意） | 指定時は`ReviewPipelineRunner`が`AiPublishReviewService.run(article_id=...)`にそのまま渡す |

---

## 8. decide() の判断基準（Open Question #2 の結論）

**結論：時間間隔方式（mtimeベース）を採用する。差分方式（未レビュー件数を数える方式）は採用しない。**

```
1. outputs/ai_publish_review_reports/ 配下の *.md を列挙
2. 各ファイルの mtime（最終更新日時）を取得
3. 最新の mtime を採用
   a. ディレクトリが存在しない、またはファイルが1件もない場合
        → should_act=True, reason="No previous review report found."
   b. 経過時間 >= min_interval_minutes の場合
        → should_act=True, reason="Review interval exceeded."
   c. 経過時間 < min_interval_minutes の場合
        → should_act=False, reason="Review interval not exceeded."
4. ファイル取得に失敗した場合はスキップし、context.warnings に記録する
5. 全てのファイルが取得不能で判断材料が皆無の場合
        → should_act=True（安全側：既存3Agentと同じ方針）
```

`decide()`はファイルの**メタデータ取得のみ**を行い、書き込み・削除・外部API呼び出しは一切行わない。`WorkflowTriggerAgent.decide()`（v2.3.0）・`PublishTriggerAgent.decide()`（v2.4.0）とロジック・reasonの命名パターンが完全に一致する（対象ディレクトリのみが異なる）。

### 差分方式（未レビュー件数）を採用しなかった理由

Charterの Open Question #2 では、「`outputs/ai_publishes/`（入力）に対する`outputs/ai_publish_review_reports/`（出力）の差分を見る」方式も選択肢としていた。この方式は「未レビューの投稿が実際にあるか」をより正確に判断できる利点があるが、以下の理由で本バージョンでは見送る。

- `outputs/ai_publishes/`配下のJSON構造（`AiPublishResult`のフィールド等）を`ReviewTriggerAgent.decide()`が直接解析する必要が生じ、Agentが対象Serviceのデータ構造を知ってしまう。これは`PublishTriggerAgent`設計時に「Agentが実処理側のデータ構造（`AiPublishRepository`等）を直接見に行く責務を持たないようにする」として明示的に避けた方針（`publish_trigger_agent_config.py`のdocstring）と矛盾する
- 件数比較（`outputs/ai_publishes/`のファイル数 と `outputs/ai_publish_reviews/`のファイル数の差）であればJSON中身のparseは避けられるが、それでも「2つのディレクトリを横断して数える」ロジックが必要になり、`decide()`が単純な「1ディレクトリのmtime走査」から複雑化する
- 4章「まずはシンプルな基盤を作る」というProject Charterの方針（設計方針欄）を優先し、既存3Agentと完全に同じ形の時間間隔方式でまず基盤を作る

**将来この方式へ切り替える場合**：差分計算ロジックは`ReviewTriggerAgent.decide()`に直接書かず、`ReviewPipelineRunner`側（またはその先の`AiPublishReviewRepository`）に判断材料の提供を委ねる薄いインターフェース（例：`count_pending_reviews() -> int`）を追加する形にし、Agent側の責務を増やさない設計にする（16章 Future Extensionsに記録）。

---

## 9. act() の実行方式（ReviewPipelineRunner経由）

### Agent＝判断、PipelineRunner＝実行

`ReviewTriggerAgent.act()`は`ReviewPipelineRunner.run(params) -> PipelineResult`という薄いインターフェースのみを呼び出す。`AiPublishReviewService`のクラス名・呼び出しシグネチャを`ReviewTriggerAgent`は一切知らない。

### ReviewPipelineRunnerがAiPublishReviewServiceを直接呼び出せる理由

`AiPublishReviewService.run(article_id)`は`AiPublishService.run()`（v2.4.0設計書 §12参照）と同様、通常のPythonメソッドであり、`sys.exit()`やCLI引数解析を内部に持たない。したがって`ReviewPipelineRunner`は`AiPublishReviewService`を**直接呼び出す薄いラッパー**として実装できる。`AiPublishReviewService`のimportは`run()`メソッド内に遅延させ、`pipeline → ai → pipeline`という循環importを構造的に回避する（`WorkflowPipelineRunner` / `PublishPipelineRunner`と同じ手法）。

### dry_run=Trueで AiPublishReviewService が起動しない保証

`ReviewTriggerAgent.act()`は`AgentExecutor`（v2.0.0、無変更）によって`should_act=True`かつ`context.dry_run=False`の場合のみ呼び出される。したがって：

- `dry_run=True`の場合、`act()`自体が呼ばれない → `ReviewPipelineRunner.run()`も呼ばれない → `AiPublishReviewService.run()`も実行されない
- `act()`冒頭に`assert not context.dry_run`を置き、万一の呼び出し経路の誤りを早期検出する（既存3Agentと同じ形）
- `enabled=False`（`REVIEW_TRIGGER_AGENT_ENABLED`未設定）の場合は、6章の二重ゲートにより`ReviewTriggerAgent`自体が`AgentManager.from_config()`で生成されないため、`decide()` / `act()`のいずれも呼ばれることがない（構造的に保証される。個別のif分岐で防ぐのではなく、DIされないことによる保証）

実装フェーズでは、この保証をE2Eテスト（実サブプロセスによる`--dry-run`実行、`outputs/ai_publish_review_reports/`にファイルが増えないことの確認）で実測する方針とする（12章参照）。

---

## 10. Directory Structure

```
src/
├── ai/
│   ├── review_trigger_agent_config.py     # ReviewTriggerAgentConfig（新規）
│   ├── review_trigger_agent.py            # ReviewTriggerAgent（新規、BaseAgent継承）
│   ├── agent_manager.py                   # executorsへの二重ゲートDI追加（既存ファイル更新）
│   └── __init__.py                        # ReviewTriggerAgent / ReviewTriggerAgentConfig をexport（既存ファイル更新）
│
└── pipeline/
    ├── review_pipeline_runner.py           # ReviewPipelineRunner（新規）
    └── __init__.py                         # ReviewPipelineRunner をexport（既存ファイル更新）

scripts/
└── run_review_trigger_agent.py             # 手動実行エントリ（新規）

tests/
└── test_e2e_v2_5_0_review_trigger_agent_foundation.py   # 新規（実装フェーズで作成）
```

`AiPublishReviewService`本体（`ai_publish_review_service.py`等） / `AiPublishReviewRepository` / `AiPublishReviewReportBuilder` / `AiPublishService` / `WorkflowRunner` / `NewsAgent` / `WorkflowTriggerAgent` / `PublishTriggerAgent`は無変更とする想定（実装フェーズで`git diff`により確認する）。

---

## 11. scripts/run_review_trigger_agent.py のCLI設計

既存の`scripts/run_publish_trigger_agent.py`（v2.4.0）と同一の骨格を踏襲する。

```
使い方:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe scripts/run_review_trigger_agent.py
    ./venv/Scripts/python.exe scripts/run_review_trigger_agent.py --dry-run
    ./venv/Scripts/python.exe scripts/run_review_trigger_agent.py --article-id sample-article

引数:
    --dry-run       実際のレビューレポート生成は行わず、判断結果のみ確認する（Agent側dry_run）
    --article-id    レビュー対象を絞り込む記事ID（未指定: 全件）

動作の流れ:
    1. AgentConfig.from_env() で Agent Foundation の設定を読み込む
    2. AgentManager.from_config(config) で Manager を構築する
       （AI_AGENT_ENABLED=false の場合は NullAgentManager が返り、run() は空リストを返す）
    3. AgentTask(task_id="run_review", params={...}) を組み立てる
    4. manager.run(task, dry_run=args.dry_run) を実行する

前提条件（.env 設定、二重ゲート）:
    AI_AGENT_ENABLED=true
    REVIEW_TRIGGER_AGENT_ENABLED=true

注意:
    - 本スクリプトは AiPublishReviewService を直接呼び出さない。
      AgentManager → ReviewTriggerAgent → ReviewPipelineRunner → AiPublishReviewService
      という既存の標準構成を経由して実行される。
    - manager.run() は AgentManager に登録されているすべての Agent
      （NewsAgent / WorkflowTriggerAgent / PublishTriggerAgent / ReviewTriggerAgent）を
      同じタスクで実行する。Agentを個別に選んで実行する仕組みは現時点では存在しない
      （run_publish_trigger_agent.py と同じ制約）。
    - --dry-run を指定した場合、実際のレビューレポート生成は行われない。
      これは AgentExecutor（v2.0.0）の設計により構造的に保証されている。
```

`task_id`は他3スクリプトの命名（`"run_news"` 相当・`"run_workflow"` / `"run_publish"`）に合わせて`"run_review"`とする。

---

## 12. Error Handling

| ケース | 対応 |
|---|---|
| `outputs/ai_publish_review_reports/`が存在しない、またはファイルが1件もない（初回実行） | `should_act=True`（安全側デフォルト） |
| ファイルのmtime取得失敗（`OSError`等） | 該当ファイルをスキップし、`context.warnings`に記録。全滅した場合は`should_act=True` |
| `AiPublishReviewService.run()`が正常に返るが`report_path=None` | `PipelineResult(success=False, error_message="Review report was not saved.")`（固定文言）。`ReviewTriggerAgent`は例外を投げず`AgentResult`として返す |
| `AiPublishReviewService.from_paths()` / `service.run()` / `service.get_reviews()`のいずれかで予期せぬ例外が発生 | `ReviewPipelineRunner`が`try/except Exception`で捕捉し、`PipelineResult(success=False, returncode=None, elapsed_sec=実測値, error_message=str(exc))`を返す。例外は`ReviewTriggerAgent` / `AgentExecutor`へは伝播しない |
| `AI_AGENT_ENABLED=false` | `NullAgentManager`が空リストを返す（v2.0.0と同じ、変更なし） |
| `AI_AGENT_ENABLED=true`だが`REVIEW_TRIGGER_AGENT_ENABLED=false`（デフォルト） | `ReviewTriggerAgent`は生成されない |

---

## 13. 既存Releaseへの影響範囲

| 対象 | 影響 |
|---|---|
| v1.19.0（`AiPublishReviewService`本体） | 無変更。`ReviewTriggerAgent`から読み取り専用で呼ばれる呼び出し先が増えるのみ |
| v2.0.0（Agent Foundation：`BaseAgent` / `AgentExecutor` / `AgentContext` / `AgentDecision` / `AgentResult` / `AgentConfig`） | 無変更 |
| v2.2.0（`NewsAgent` / `NewsPipelineRunner`） | 無変更。`AgentManager.from_config()`内の別ブロックとして独立に追加されるのみ |
| v2.3.0（`WorkflowTriggerAgent` / `WorkflowPipelineRunner`） | 無変更。同上 |
| v2.4.0（`PublishTriggerAgent` / `PublishPipelineRunner`） | 無変更。同上 |
| `AgentManager.from_config()`（`src/ai/agent_manager.py`） | 更新（4番目のDIブロック追加のみ。既存3ブロックのコードは変更しない） |
| `src/ai/__init__.py` / `src/pipeline/__init__.py` | 更新（新規シンボルのexport追加のみ） |
| `scripts/run_ai_publish_review.py`（既存の手動実行スクリプト、v1.19.0） | 無変更。引き続き利用可能（5章 User Workflow参照） |
| `main.py` | 無変更 |

**影響範囲のまとめ**：新規ファイル追加5点＋`AgentManager` / 2つの`__init__.py`への追記のみ。既存Agent・既存Serviceの実装ロジックには一切触れない。

---

## 14. Testing Strategy（実装フェーズで実施予定）

`docs/design/publish_trigger_agent_foundation.md`（v2.4.0）のテスト構成を土台に、対象を`AiPublishReviewService`に置き換えて`tests/test_e2e_v2_5_0_review_trigger_agent_foundation.py`を新規作成する想定（実装フェーズで確定）。

### 新規E2Eテスト（想定シナリオ）

- `ReviewTriggerAgentConfig.from_env()`のデフォルト値（`enabled=False` / `min_interval_minutes=1440`）・環境変数上書き・二重ゲートの`is_ready()`判定
- `ReviewTriggerAgent.decide()`：レポートなし／ファイル0件／間隔超過／間隔内／新旧混在で最新mtime優先の5パターン（各パターンで`runner.run()`が呼ばれない副作用ゼロも確認）
- `ReviewTriggerAgent.act()`：`ReviewPipelineRunner.run()`のみを呼ぶこと・成功/失敗時の`AgentResult`変換・`workflow_result`が常に`None`・`dry_run=True`直接呼び出しで`AssertionError`
- `ReviewPipelineRunner`：`AiPublishReviewService`をモック化した`from_paths`呼び出し引数・`run`/`get_reviews`呼び出し引数・成功/失敗/例外時の`PipelineResult`変換
- `AgentManager.from_config()`の二重ゲート分岐：`REVIEW_TRIGGER_AGENT_ENABLED`未設定／二重ゲートON／4Agent（News + Workflow + Publish + Review）すべて有効時の登録確認
- `scripts/run_review_trigger_agent.py`（実サブプロセス、常にdry-run）：スクリプト存在確認・無効時の安全終了・二重ゲートON時に`outputs/ai_publish_review_reports/`にファイルが増えないことの確認
- Architecture Guard：`AiPublishReviewService`本体・既存3Agent（`NewsAgent`/`WorkflowTriggerAgent`/`PublishTriggerAgent`）等に変更がないこと（`git diff`）、`ReviewTriggerAgent`が`AiPublishReviewService`を直接importしないこと・`ReviewPipelineRunner`が`subprocess`を使わないことの静的検査
- `src/ai/__init__.py` / `src/pipeline/__init__.py`のexport確認

### 既存回帰確認（実装フェーズで実施予定）

- `tests/test_e2e_v2_0_0_ai_agent_foundation.py`
- `tests/test_e2e_v2_2_0_news_agent_foundation.py`
- `tests/test_e2e_v2_3_0_workflow_trigger_agent_foundation.py`
- `tests/test_e2e_v2_4_0_publish_trigger_agent_foundation.py`
- `tests/test_e2e_v1_20_0_ai_workflow_foundation.py`

いずれも実装フェーズで実際に実行し、実測したPASS件数をCHANGELOG・本ドキュメントの更新に反映する（本ドキュメント作成時点ではまだ実装していないため、件数の記載はしない）。

---

## 15. 実装前にChatGPTへ確認したい点

1. **Gate方式（6章）**：二重ゲート（`AI_AGENT_ENABLED` × `REVIEW_TRIGGER_AGENT_ENABLED`）で確定してよいか。将来3段目相当のガードが必要になった場合（例：レビュー対象記事数の上限等）は、そのときに`ReviewTriggerAgentConfig`側に独自の追加条件を持たせる想定でよいか
2. **decide()の判断方式（8章）**：時間間隔方式（mtimeベース）を採用し、差分方式（未レビュー件数ベース）は見送るという判断でよいか。特に「投稿はあったのにレビューレポートが古いまま」という状況を`min_interval_minutes`のデフォルト値（24時間）でどこまで許容してよいか
3. **`min_interval_minutes`のデフォルト値**：`WorkflowTriggerAgent` / `PublishTriggerAgent`と同じ1440分（24時間）で揃えているが、レビューレポートはWordPress書き込みを伴わない読み取り専用処理のため、より短い間隔（例：180分、`NewsAgent`相当）にする余地はあるか

---

## 16. Future Extensions

- 差分方式（未レビュー件数ベース）への切り替え（8章参照。`ReviewPipelineRunner`または`AiPublishReviewRepository`に判断材料提供用の薄いインターフェースを追加する形を想定）
- `ImprovementReviewService`（v1.15.0）・`RewriteReviewService`（v1.17.0）への同パターンの展開（Charter §3・§4参照。抽象化は行わず、同じ形をコピーして追加する想定）
- `error_message`の詳細化（既存3Agentと同様の課題）
- 専用実行ログ基盤（例：`logs/review_agent/`）の追加による`decide()`判断精度の向上
- `.env.example`のドキュメント負債解消（別タスク、Charter §3参照）
- Scheduler Agent（Windowsタスクスケジューラ統合）への展開
- `review_status`（PENDING固定）を人が更新する機能との連携

---

## 17. Definition of Done

### コード（未着手）

- [ ] `ReviewTriggerAgentConfig`（`src/ai/review_trigger_agent_config.py`）
- [ ] `ReviewPipelineRunner`（`src/pipeline/review_pipeline_runner.py`、subprocess不使用・`AiPublishReviewService.run()`を直接呼ぶ薄いラッパー）
- [ ] `ReviewTriggerAgent`（`src/ai/review_trigger_agent.py`、`AiPublishReviewService`を直接importしない）
- [ ] `AgentManager.from_config()`の`executors`更新（二重ゲート方式：`AI_AGENT_ENABLED` × `ReviewTriggerAgentConfig.is_ready()`）
- [ ] `scripts/run_review_trigger_agent.py`（`--dry-run` / `--article-id`対応）
- [ ] `src/ai/__init__.py` / `src/pipeline/__init__.py`への新規シンボルのexport追加

### テスト（未着手）

- [ ] `tests/test_e2e_v2_5_0_review_trigger_agent_foundation.py`
- [ ] 既存回帰確認：`v2.0.0` / `v2.2.0` / `v2.3.0` / `v2.4.0` / `v1.20.0`
- [ ] `dry_run=True`で`act()`（ひいては`AiPublishReviewService.run()`）が起動しないことの実測確認
- [ ] 二重ゲート（`AI_AGENT_ENABLED` × `REVIEW_TRIGGER_AGENT_ENABLED`）の分岐確認
- [ ] Architecture Guard：`ReviewTriggerAgent`が`AiPublishReviewService`を直接importしないこと・`ReviewPipelineRunner`が`subprocess`を使わないことの静的検査
- [ ] `AiPublishReviewService`本体 / 既存3Agent（`NewsAgent` / `WorkflowTriggerAgent` / `PublishTriggerAgent`）等が無変更であることの`git diff`確認

### ドキュメント

- [x] `docs/design/review_trigger_agent_charter.md`（Project Charter、作成済み）
- [x] 本設計書（Architecture Design、本タスクで作成）
- [ ] Architecture Review・ChatGPTレビュー
- [ ] `docs/CHANGELOG.md` / `docs/ROADMAP.md`への記載（実装完了後）
- [ ] `docs/architecture.md`への追記（Agent → Pipeline → Runnerパターンの表にReviewTriggerAgentを追加。実装完了後）

### リリース

- [ ] コミット・push（実装完了・Architecture Review承認後）
