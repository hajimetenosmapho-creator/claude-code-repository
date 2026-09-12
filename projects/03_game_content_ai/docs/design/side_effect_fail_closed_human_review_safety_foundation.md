# Side-Effect Fail-Closed & Human Review Safety（Release 6.32）設計書

## 0. Scope and Normative Authority

本節は本書のscopeとauthorityのみを記す。

- **Scope**: 本書はRelease 6.32 target architectureとして、呼び出し箇所A（NEWS側WordPress draft、`WordPressOutput.save()`）・B（NEWS側media upload、`ArticleFeaturedMediaRuntime.apply()`）・C（PUBLISH側WordPress draft、`AiPublishService._post()`）の3経路（1.2節）に対するExplicit Side-Effect Execution Mode（discriminated union、2章）・write-ahead fail-closed契約・durable Human Review terminal dispositionを定める。
- **Explicit Side-Effect Execution Mode**: discriminated union（`RetryLineageProtectedExecutionContext`／`LegacyDirectExecutionContext`、フィールド構成そのものが異なる2つの型、2.1節）をtrusted composition boundaryから明示的に供給する契約（2章）。context欠落・unknown・矛盾はすべてfail-closed。main.pyは暗黙のデフォルト値を一切持たない（14.3節）。
- **呼び出し箇所A/B/Cの統合**: A＝15.7節、B＝15.4節、C＝15.6節が個別に規定する。3経路すべてが§9系のWordPress draft/media uploadのdurable storeを共有し、write-ahead契約から漏れる呼び出し箇所はない。
- **Authority boundary**: §§0〜31 = current normative target architecture、§32（Completed History）= non-normative。

---

## 1. Background / Motivation

Release 6.32は、4-phase state machine・`RetryLineageDisposition`（既存、無変更）を土台に、partial success・外部副作用発生済みrunに対するwrite-ahead fail-closed契約と、durable Human Review terminal dispositionを定める。

### 1.1 自動Retry経路が持つクラッシュ窓

`_reconcile_all_locked()`が`EXECUTION_STARTED`のまま再起動を跨いだlineageを`disposition_from_categories()`のみで再分類し、`FAILED`/`NOT_ACTIONED`なら自動的に`open_next_attempt()`を呼ぶため、「PUBLISH stepでWordPress draft POST成功直後にプロセス停止→再起動→自動再Retry→重複下書き」という経路が既存コードに存在する。

### 1.2 外部副作用の呼び出し箇所（3箇所）

| # | 呼び出し箇所 | 実装 | 属するstep | write-ahead機構 |
|---|---|---|---|---|
| A | `src/outputs/wordpress_output.py::WordPressOutput.save()`（69行目） | `requests` | NEWS | なし |
| B | `src/article_featured_media_orchestration/article_featured_media_orchestrator.py`（73行目） | `WordPressMediaUploader.upload()` | NEWS（Aより先、Gate依存） | 既存Foundationあり、未接続 |
| C | `src/ai/wordpress_draft_client.py::WordPressDraftClient.post_draft()`（71行目） | `urllib` | PUBLISH | なし |

### 1.3 画像生成Gateは既存の正常な運用構成として存在する

`ArticleFeaturedMediaRuntime.is_available()`が`False`の場合、`apply()`は`orchestrator.apply()`（media uploadを含む）を一切呼ばず`DISABLED`を返す。画像生成Gate OFFは、段階導入されてきた既存の正常な運用構成である。したがって「NEWS stepは成功したが`MEDIA_UPLOAD`のwrite-aheadレコードが一切ない」は日常的に発生する**正常系**であり、これを`CONTRACT_VIOLATION`扱いしてはならない。

### 1.4 `article_media_upload_state`はconsumer-lessである

`src/article_media_upload_state/`（`ArticleMediaUploadStateManager`）は、**パッケージ自身の`__init__.py`以外にどこからも呼び出されない**。これは22.2節「No Bypass Proof」にとって重要な事実である——**6.32が導入する呼び出しが、このManagerに対する唯一の新規呼び出しである**ため、「既存の別経路がshared coordination boundaryを迂回している」という状況は存在しない。Coordinatorを経由せず直接Managerを呼ぶ経路が生じないことは22章の規律による。

### 1.5 main.py subprocess境界にはrun_id/attempt情報が渡っていない

`src/pipeline/news_pipeline_runner.py::NewsPipelineRunner.run()`（99〜117行目）は`subprocess.run(cmd, cwd=..., capture_output=True, text=True, timeout=...)`を呼んでおり、**`env=`引数が一切渡されていない**（親プロセスの環境をそのまま継承するのみ）。`cmd`も`[python, main.py, --max-articles, N]`のみで、run_id・root_run_id・attempt_ordinalに相当する情報は一切含まれない。

これは、P1-1が要求する「attempt-scoped identity」を呼び出し箇所A・B（main.py subprocess内）で構成するために、**新たな配線（root_run_id/attempt_ordinal/member_run_idをsubprocessへ伝達する経路）が必須である**ことを意味する具体的事実である。14章で扱う。

### 1.6 既知の残存リスク（Out of Scope）

6.31起因の未対応residual riskは存在しうる（`[KI-31]`は解決済みのため対象外）が、Release 6.32 Out of Scope（4章）とする。

---

## 2. Scope境界

6.32の責務はScope境界（本章）に限定する。6.31が確立したAPI形状は破壊的変更をしない。`ArticleMediaUploadState`（既存2値Enum・既存スキーマ）はそのまま維持する。

**generic automatic re-dispatch（Out of Scope）**：`FAILED`/`NOT_ACTIONED`終端のlineageが`open_next_attempt()`により`READY_ELIGIBLE`へ再度到達した後、その新しいattemptを自動的に`RetryManager.retry()`へdispatchする一般的な仕組み（`RetryEnqueueTrigger`のmembership-first除外により、既存lineage memberのrun_idはscheduler/queue駆動の自動dispatch経路に構造的に乗らない）は、6.32でも6.31以前と同じ挙動のまま変更しない。`RetryEnqueueTrigger`・`SchedulerEngine`・`RetrySchedulerSource`・retry queueのgeneric動作は6.32の対象外とする。HRR authorized retryのみ、17.3節が定める明示的なcomposition層の呼び出し（`retry_after_human_review()`）という専用のdispatch経路を持つ——これはgeneric automatic re-dispatchの一般解ではなく、human-in-the-loopなHRR resolutionに限定した個別のdispatch契約である。

### 2.1 Trusted Composition Boundary Invariant

**却下する設計**：単一の`SideEffectExecutionContext`（`execution_mode`フィールド＋Optional-heavyな4フィールド）という設計は、「`LEGACY_DIRECT`かつ全フィールドNone」という状態と「本来protectedであるべきなのに実装バグで全フィールドが欠落したLEGACY_DIRECT」という状態を**値のレベルで区別できない**。durable store側の証拠（過去のwrite-ahead record）を横断的に検索してこの2つを見分ける方式も検討したが、`operation_instance_key`だけでは正当なlegacy実行を誤って拒否しうる（false positive）ため採用しない。

**新設する契約**：mode混同を**型レベルで構造的に不可能にする**。「protected」と「legacy」を単一の型＋Optionalフィールドで表現するのをやめ、**discriminated union**（互いにフィールド構成が異なる2つのfrozen dataclass）へ分離する：

**AgentManager fan-out legacy provenance**：`LegacyExecutionOrigin`は「どのscriptから起動されたか」のみでは不十分である——`AgentManager.run()`は単一の`AgentTask`に対して**複数のexecutor（Agent種別）を同一呼び出し内でfan-outする**という構造（`src/ai/agent_manager.py:150-161`）を持つため、同一`AgentManager.run()`呼び出し内で複数Agentが実行される構成（例：`AI_AGENT_ENABLED`・`WORKFLOW_TRIGGER_AGENT_ENABLED`・`PUBLISH_TRIGGER_AGENT_ENABLED`が同時に有効）では、起動scriptベースの単一origin値では実行中の全Agentの監査証跡として不十分である。`src/ai/workflow_runner.py::WorkflowRunner.from_config()`は`PublishStepExecutor(service=AiPublishService.from_env(...))`を構築しており（97-99行目）、`WorkflowTriggerAgent`（`AgentManager`の4番目のexecutor種別）は`WorkflowPipelineRunner`→`WorkflowRunner`→`PublishStepExecutor`を経由して**呼び出し箇所C（`AiPublishService._post()`）へ到達しうる**。`scripts/run_workflow_trigger_agent.py`・`scripts/run_review_trigger_agent.py`という2本の既存legacy scriptが実在し、いずれも`AgentManager.from_config().run()`を呼ぶため、これらのscriptから起動された場合も登録済みの全Agentのprovenanceを正しく供給する必要がある。以下のとおり、provenanceを2段階へ分離する：

```python
class LegacyEntrypoint(Enum):
    """Stage 1：プロセスがどのlegacy entrypointから起動されたかを示すclosed set（8値、
    `scripts/`配下の7スクリプト＋project-root `main.py`に1:1対応、22.3.11節が定めるclosed set）。
    project-root `main.py`の直接手動実行（`python main.py`をラッパースクリプトなしで
    起動する既知の正当な運用、14.2・14.3節）専用の値を持つ——他のentrypointの値を
    代用・偽装申告する経路は持たない。"""
    RUN_NEWS_AGENT = "run_news_agent"                          # scripts/run_news_agent.py
    RUN_WORKFLOW_TRIGGER_AGENT = "run_workflow_trigger_agent"  # scripts/run_workflow_trigger_agent.py
    RUN_PUBLISH_TRIGGER_AGENT = "run_publish_trigger_agent"    # scripts/run_publish_trigger_agent.py
    RUN_REVIEW_TRIGGER_AGENT = "run_review_trigger_agent"      # scripts/run_review_trigger_agent.py
    RUN_AI_PUBLISH = "run_ai_publish"                          # scripts/run_ai_publish.py（AgentManager非経由）
    RUN_AI_WORKFLOW = "run_ai_workflow"                        # scripts/run_ai_workflow.py（AgentManager非経由）
    RUN_WORKFLOW_ENGINE_DIRECT = "run_workflow_engine_direct"  # scripts/run_workflow_engine.py（AgentManager非経由）
                                                                 # のRetry Lineage外呼び出し
    RUN_MAIN_DIRECT = "run_main_direct"                        # project-root main.py（AgentManager非経由、
                                                                 # 直接手動実行）


class LegacyExecutionOrigin(Enum):
    """Stage 2：実際にprotected side-effect operation（呼び出し箇所A/B/C）へ
    到達しうるコンポーネントの識別子（closed set、8値）。AgentManager経由の
    場合はfan-out境界で実際にdispatchされるexecutorの種別から、非AgentManager
    経由の場合はentrypointそのものから、いずれも1:1・曖昧性なく決定される。"""
    NEWS_AGENT = "news_agent"                          # AgentManager経由、NewsAgent（呼び出し箇所A・B）
    WORKFLOW_TRIGGER_AGENT = "workflow_trigger_agent"   # AgentManager経由、WorkflowTriggerAgent
                                                          # （WorkflowRunner.PublishStepExecutor経由で
                                                          #  呼び出し箇所Cへ到達しうる、22.3節）
    PUBLISH_TRIGGER_AGENT = "publish_trigger_agent"     # AgentManager経由、PublishTriggerAgent（呼び出し箇所C）
    REVIEW_TRIGGER_AGENT = "review_trigger_agent"       # AgentManager経由、ReviewTriggerAgent
                                                          # （現状は呼び出し箇所A/B/Cのいずれにも到達しないが、
                                                          #  推測によるunmapped扱いを避けるため明示的にmappingする）
    AI_PUBLISH_DIRECT = "ai_publish_direct"             # 非AgentManager、run_ai_publish.py（呼び出し箇所C）
    AI_WORKFLOW_DIRECT = "ai_workflow_direct"           # 非AgentManager、run_ai_workflow.py（呼び出し箇所C、
                                                          # WorkflowRunner.PublishStepExecutor経由。
                                                          # AgentManagerを経由しないため、WORKFLOW_TRIGGER_AGENT
                                                          # とは値のレベルで区別する——同じPublishStepExecutorへ
                                                          # 到達する経路でも、Agent抽象層を経由するか直接呼び出し
                                                          # かで監査証跡上は別origin）
    WORKFLOW_ENGINE_DIRECT = "workflow_engine_direct"   # 非AgentManager、run_workflow_engine.py
    MAIN_DIRECT = "main_direct"                         # 非AgentManager、project-root main.py直接手動実行
                                                          # （呼び出し箇所A・B。main.py自身がStage 1/Stage 2
                                                          #  非依存の直接経路であり、他のentrypointのoriginを
                                                          #  流用・偽装しない）


@dataclass(frozen=True)
class LegacyDirectProvenance:
    """Stage 1完成物。trusted direct composition root（8つのlegacy entrypoint）で
    一度だけ構築する。単体では実I/O呼び出しの契約を満たさない——呼び出し箇所A/B/Cが
    要求するのは、Stage 2で完成した`LegacyDirectExecutionContext`のみである（下記）。"""
    legacy_entrypoint: LegacyEntrypoint


@dataclass(frozen=True)
class RetryLineageProtectedExecutionContext:
    """RETRY_LINEAGE_PROTECTEDの最終形。4フィールドすべて必須（Optionalではない）。
    このクラスのインスタンスを構築できるのは2.1a節の「protected factory」のみ
    （trusted composition boundary、22.1f節）。legacy_entrypoint/legacy_execution_origin
    フィールドを持たないため、「protectedなのにlegacy側のfieldだけ設定されている」
    という混同状態は型として存在しえない。"""
    root_run_id: str
    attempt_ordinal: int
    member_run_id: str
    side_effect_contract_version: int


@dataclass(frozen=True)
class LegacyDirectExecutionContext:
    """LEGACY_DIRECTの最終形（Stage 2完成物）。`legacy_entrypoint`（Stage 1、
    どのscriptから来たか）と`legacy_execution_origin`（Stage 2、実際に到達を
    試みるコンポーネントは何か）の両方を持つ。root_run_id等のprotected identity
    fieldsは一切持たない——「フィールドをNoneにクリアする」という操作自体が
    型として存在しない。"""
    legacy_entrypoint: LegacyEntrypoint
    legacy_execution_origin: LegacyExecutionOrigin


SideEffectExecutionContext = "RetryLineageProtectedExecutionContext | LegacyDirectExecutionContext"
```

**Formal Trust-Boundary Invariant（25章#38として追加）**：Execution provenance is established exactly once at a trusted composition boundary and transported as a typed immutable value. Downstream components MUST NOT infer, upgrade, or downgrade execution provenance from missing fields, scheduler/event metadata, arbitrary params, correlation metadata, operation_instance_key history, or ambient state.

**保証しない範囲**：trusted composition root自身が誤ったfactoryを選択するprogramming defect（例：本来`build_protected_execution_context()`を呼ぶべき箇所が誤って legacy factoryを呼んでしまう）を、side-effect呼び出し箇所（呼び出し箇所A/B/C）だけで完全に検出できる、という保証はこの設計の対象外である——これは原理的に不可能な保証である（`LegacyDirectExecutionContext`が正当に構築された時点で、そのcontextからは「本来protectedだったはずだ」という情報が一切得られない）。代わりに、(a) 型分離そのもの（フィールドをクリアして混同を作ることが構造的に不可能）、(b) closed-set origin（8 explicit legacy entrypoints＝7スクリプト＋project-root `main.py`以外は`legacy_entrypoint`を持てず、`AgentManager`が実際に構築する4つのAgent型以外は`legacy_execution_origin`を持てない）、(c) 網羅的なwiring tests（22.1f節、28.-14節、28.-19節、28.-20節）、の3層で防ぐ。

### 2.1a Factory

```python
def build_protected_execution_context(
    root_run_id: str, attempt_ordinal: int, member_run_id: str, side_effect_contract_version: int,
) -> RetryLineageProtectedExecutionContext:
    """protected factory。RetryLineageRecordのauthoritative valueからのみ
    呼び出してよい（2.2節）。production APIとして、modeを引数で自由に切り替え
    られる汎用constructorは提供しない——呼び出せる関数自体が「protected」に
    固定されている。"""
    return RetryLineageProtectedExecutionContext(
        root_run_id=root_run_id, attempt_ordinal=attempt_ordinal,
        member_run_id=member_run_id, side_effect_contract_version=side_effect_contract_version,
    )


def build_legacy_direct_provenance(legacy_entrypoint: LegacyEntrypoint) -> LegacyDirectProvenance:
    """legacy Stage 1 factory。8つのlegacy entrypoint（`run_ai_workflow.py`・
    project-root `main.py`を含む、2.1・2.3・22.3.11節）のcomposition rootからのみ
    呼び出してよい（2.3節）。"""
    return LegacyDirectProvenance(legacy_entrypoint=legacy_entrypoint)


def complete_legacy_execution_context(
    provenance: LegacyDirectProvenance, legacy_execution_origin: LegacyExecutionOrigin,
) -> LegacyDirectExecutionContext:
    """legacy Stage 2 factory（唯一の完成点）。非AgentManager経由
    （`run_ai_publish.py`・`run_workflow_engine.py`）は、`build_legacy_direct_provenance()`
    直後の同一composition pointでこれを呼ぶ——fan-outのambiguityが存在しないため、
    entrypointがそのままexecution originを一意に決める（2.3節の対応表）。
    AgentManager経由の場合は、`AgentManager.run()`のfan-out境界（実際にdispatch
    するexecutorが確定した時点）でのみ呼ぶ——provenance構築時点ではまだexecutorが
    未確定のため、この時点では呼べない（2.3節）。"""
    return LegacyDirectExecutionContext(
        legacy_entrypoint=provenance.legacy_entrypoint,
        legacy_execution_origin=legacy_execution_origin,
    )
```

`member_run_id`は`RetryExecutor.execute()`の時点ではまだ確定していない（`WorkflowEngineExecutor`が自ら発行する`run_id`と同一値、10.2節）ため、`RetryExecutor`は`RetryLineageProtectedExecutionContext`を直接構築せず、以下の**pre-context**を`WorkflowEngineManager.run()`へ渡す（2.6節）：

```python
@dataclass(frozen=True)
class RetryLineageProtectedProvenance:
    """RetryExecutorが構築時点で確定できる3フィールドのみを持つ。member_run_id
    はまだ含まない。WorkflowEngineExecutorが自らのrun_id発行後、protected
    factoryを呼んでRetryLineageProtectedExecutionContextへ完成させる（2.6節）。"""
    root_run_id: str
    attempt_ordinal: int
    side_effect_contract_version: int


SideEffectExecutionProvenance = "RetryLineageProtectedProvenance | LegacyDirectExecutionContext"
# WorkflowEngineManager.run()が受け取る型（2.6節）。LegacyDirectExecutionContextは
# 既に完成形なのでそのまま使う。RetryLineageProtectedProvenanceのみ、
# WorkflowEngineExecutor内でprotected factoryにより完成される。
```

### 2.1b 共通Validator（呼び出し箇所A/B/C全体で単一のvalidation contractを再利用）

```python
def validate_side_effect_execution_context(
    context: "SideEffectExecutionContext | None",
) -> "SideEffectExecutionContext":
    """呼び出し箇所A/B/C（15.4・15.6・15.7節）が共通で呼ぶ、唯一のvalidation関数。
    isinstance判定のみで分岐する——値のフィールド組み合わせから矛盾を推測する
    ロジックは持たない（型分離により、その種の矛盾は構造的に発生しない、2.1節）。"""
    if context is None:
        raise SideEffectExecutionModeContractError(
            ExecutionModeFailureReasonCode.MISSING_EXECUTION_MODE,
        )

    if isinstance(context, RetryLineageProtectedExecutionContext):
        if not _is_well_formed_root_run_id(context.root_run_id):
            raise SideEffectExecutionModeContractError(
                ExecutionModeFailureReasonCode.MISSING_LINEAGE_CONTEXT,
            )  # 2.2節#3：root_run_id自体が識別不能。hard failure。
        if not _is_well_formed_attempt_ordinal(context.attempt_ordinal):
            raise SideEffectExecutionModeContractError(
                ExecutionModeFailureReasonCode.CONTEXT_MISMATCH,
            )  # 2.2節#2：root_run_idは識別できているためCONTRACT_VIOLATION経路
        if not _is_well_formed_member_run_id(context.member_run_id):
            raise SideEffectExecutionModeContractError(
                ExecutionModeFailureReasonCode.CONTEXT_MISMATCH,
            )
        if not _is_well_formed_contract_version(context.side_effect_contract_version):
            raise SideEffectExecutionModeContractError(
                ExecutionModeFailureReasonCode.CONTRACT_VERSION_MISMATCH,
            )
        return context

    if isinstance(context, LegacyDirectExecutionContext):
        # 2フィールドともclosed set内であることを個別に検証する。
        # 片方だけの検証では、Stage 1（entrypoint）は正しいがStage 2
        # （execution origin）がfan-out境界での構築漏れ・取り違えによりclosed set外
        # またはNone相当になっている、という部分的な契約違反を見逃しうる。
        if context.legacy_entrypoint not in LegacyEntrypoint:
            raise SideEffectExecutionModeContractError(
                ExecutionModeFailureReasonCode.UNKNOWN_LEGACY_ENTRYPOINT,
            )  # closed set外のentrypoint値（malformed deserialization等）
        if context.legacy_execution_origin not in LegacyExecutionOrigin:
            raise SideEffectExecutionModeContractError(
                ExecutionModeFailureReasonCode.UNKNOWN_LEGACY_EXECUTION_ORIGIN,
            )  # closed set外のexecution origin値（AgentManagerのfan-out境界での
               # mapping漏れ・未知のexecutor型を含む）
        # 2.1c節：個別に有効な値同士でも、組み合わせがALLOWED_LEGACY_ENTRYPOINT_ORIGINS
        # に存在しなければ矛盾したペアとしてfail-closedする（例：直接単独entrypoint
        # であるRUN_AI_PUBLISHにAgentManager fan-out origin NEWS_AGENTが対応付けられて
        # いる等、個別には有効だが組み合わせとして到達不可能な値）。
        if (context.legacy_entrypoint, context.legacy_execution_origin) not in ALLOWED_LEGACY_ENTRYPOINT_ORIGINS:
            raise SideEffectExecutionModeContractError(
                ExecutionModeFailureReasonCode.CONTRADICTORY_LEGACY_PAIR,
            )
        return context

    # RetryLineageProtectedExecutionContextでもLegacyDirectExecutionContextでもない
    raise SideEffectExecutionModeContractError(
        ExecutionModeFailureReasonCode.UNKNOWN_EXECUTION_MODE,
    )
```

呼び出し箇所A（15.7節）・B（15.4節）・C（15.6節）は、いずれも自前で個別の検証ロジックを実装せず、`validate_side_effect_execution_context(context)`を呼び出し、成功した場合のみ以降の処理へ進む（失敗時は例外がそのまま伝播し、実I/O前でfail-closedする、2.4節）。

### 2.1c Legacy Entrypoint/Origin Compatibility Matrix

`legacy_entrypoint`と`legacy_execution_origin`は、それぞれ独立にclosed set内であることに加え、両者の組み合わせも到達可能な組でなければならない。実現可能な組み合わせは以下の2群に分かれる：

**群1（AgentManager fan-out、config依存・launcher名非依存）**：`scripts/run_news_agent.py`・`scripts/run_workflow_trigger_agent.py`・`scripts/run_publish_trigger_agent.py`・`scripts/run_review_trigger_agent.py`はいずれも`AgentConfig.from_env()` → `AgentManager.from_config(config)` → `manager.run(task, dry_run)`という同一の呼び出し形を持ち、`from_config()`自身は起動元scriptを一切参照しない（`src/ai/agent_manager.py:77-144`）。`NewsAgent`は`config.is_ready()`のみで無条件に登録され、`WorkflowTriggerAgent`/`PublishTriggerAgent`/`ReviewTriggerAgent`はそれぞれ独立した`is_ready()`ゲート（三重・二重ゲート）でのみ登録可否が決まる。したがって、この4 entrypointのいずれから起動しても、config次第で4 origin（`NEWS_AGENT`/`WORKFLOW_TRIGGER_AGENT`/`PUBLISH_TRIGGER_AGENT`/`REVIEW_TRIGGER_AGENT`）のいずれにも到達しうる——4×4＝16組すべてが到達可能である。

**群2（direct、fan-outなし、1:1固定）**：`RUN_AI_PUBLISH`・`RUN_AI_WORKFLOW`・`RUN_WORKFLOW_ENGINE_DIRECT`・`RUN_MAIN_DIRECT`はいずれも単一composition point（fan-outのambiguityなし、2.3節）であり、それぞれ対応する1つのoriginにのみ1:1で対応する。

```python
_AGENT_MANAGER_ENTRYPOINTS = (
    LegacyEntrypoint.RUN_NEWS_AGENT,
    LegacyEntrypoint.RUN_WORKFLOW_TRIGGER_AGENT,
    LegacyEntrypoint.RUN_PUBLISH_TRIGGER_AGENT,
    LegacyEntrypoint.RUN_REVIEW_TRIGGER_AGENT,
)
_AGENT_MANAGER_ORIGINS = (
    LegacyExecutionOrigin.NEWS_AGENT,
    LegacyExecutionOrigin.WORKFLOW_TRIGGER_AGENT,
    LegacyExecutionOrigin.PUBLISH_TRIGGER_AGENT,
    LegacyExecutionOrigin.REVIEW_TRIGGER_AGENT,
)

ALLOWED_LEGACY_ENTRYPOINT_ORIGINS: frozenset[tuple[LegacyEntrypoint, LegacyExecutionOrigin]] = frozenset({
    # 群1：AgentManager.from_config()はconfigのis_ready()ゲートのみで各Agentを
    # 登録し、起動元scriptを一切参照しない（src/ai/agent_manager.py:77-144）ため、
    # 4 entrypoint x 4 originの全組み合わせがconfig次第で到達可能である。
    *(
        (entrypoint, origin)
        for entrypoint in _AGENT_MANAGER_ENTRYPOINTS
        for origin in _AGENT_MANAGER_ORIGINS
    ),
    # 群2：fan-outのambiguityがない単一composition point、1:1固定対応（2.3節）。
    (LegacyEntrypoint.RUN_AI_PUBLISH, LegacyExecutionOrigin.AI_PUBLISH_DIRECT),
    (LegacyEntrypoint.RUN_AI_WORKFLOW, LegacyExecutionOrigin.AI_WORKFLOW_DIRECT),
    (LegacyEntrypoint.RUN_WORKFLOW_ENGINE_DIRECT, LegacyExecutionOrigin.WORKFLOW_ENGINE_DIRECT),
    (LegacyEntrypoint.RUN_MAIN_DIRECT, LegacyExecutionOrigin.MAIN_DIRECT),
})
```

このmatrixはclosed setである——将来新しいentrypoint/originが追加される場合は、このmatrix自体を明示的に拡張しなければならず、暗黙に到達可能とみなされることはない。個別には有効な値同士の組み合わせであっても、このmatrixに存在しない場合（例：`RUN_AI_PUBLISH`と`NEWS_AGENT`の組み合わせ——`RUN_AI_PUBLISH`はAgentManagerを経由しない単一originのentrypointであるため、AgentManager fan-out origin側の値と組み合わさることは構造的にありえない）は、2.1b節のvalidatorが`CONTRADICTORY_LEGACY_PAIR`でfail-closedする。

### 2.2 `RetryLineageProtectedExecutionContext`の要件

`RetryExecutor.execute()`（15.1〜15.2節）は、`RetryLineageRecord`のauthoritative valueから`RetryLineageProtectedProvenance`（2.1a節）を構築する：

- `root_run_id`（`RetryLineageRecord.root_run_id`）
- `attempt_ordinal`（`RetryLineageRecord`の現attempt、`claim.attempt_no`）
- `side_effect_contract_version`（18章、`RetryLineageRecord.side_effect_contract_version`）

構築直後、`RetryExecutor`は自身が保持する`lineage`/`claim`参照（同一関数呼び出し内で直接アクセス可能、trusted composition boundary、2.1節）に対し、構築した`RetryLineageProtectedProvenance`の3フィールドがそれぞれ一致することを照合する（2.2a節(1)、実装バグにより構築値が本来のlineage/claimと乖離した状態を検出する防御層）。この照合を通過した値のみを**validated pre-context**として`WorkflowEngineManager.run()`へ渡す。`member_run_id`（10.2節、`WorkflowEngineResult.run_id`）はこの時点ではまだ生成されないため`RetryLineageProtectedProvenance`には含まれない——`WorkflowEngineExecutor`が自らのrun_id発行後、protected factory（2.1a節）を呼んでvalidated pre-contextの3値をそのまま引き継ぎ、`member_run_id`のみを補完して`RetryLineageProtectedExecutionContext`を完成させる（2.2a節(2)・2.6節）。

**missing/malformed/mismatch時の扱い（fail-closed、legacyへのfallback禁止）**：

1. **external WordPress/media I/O は必ず0**——write-ahead ACKに到達する前に検証するため、実I/Oへは構造的に到達しない。
2. `root_run_id`が存在し、対応する`RetryLineageRecord`を安全に識別できる場合（＝どのlineageの問題かをdurableに特定できる場合）：`CONTRACT_VIOLATION`として12章の決定表へ合流させ、`resolve_final_disposition()`（13章）経由で`HUMAN_REVIEW_REQUIRED`へ導く。
3. `root_run_id`自体が欠落・破損しており、対応するlineageを安全に識別できない場合：lineageへ書き込むべき対象自体が定まらないため、`SideEffectExecutionModeContractError`を送出するhard failureとし、呼び出し元（`RetryExecutor`/`WorkflowEngineExecutor`）へfail-fastで伝播させる。この場合もsecret-safeな構造化診断（2.5節）のみを記録する。

### 2.2a Authoritative Completion Boundary Identity Consistency（2段階責務分離）

Identity consistencyの保証は、以下の2段階に分離される。`WorkflowEngineManager.run()`は`lineage`／`claim`オブジェクト自体を受け取らない（2.6節Propagation Contract）ため、`WorkflowEngineExecutor`は`lineage`／`claim`への参照を持たない——この分離は実装可能性そのものに基づく（`WorkflowEngineExecutor`が`lineage`/`claim`へ直接参照を持つという前提は実装不能であるため採用しない）。

**(1) RetryExecutor — Consistency Validation Boundary**：`RetryExecutor.execute()`が`RetryLineageProtectedProvenance`を構築した直後（2.2節）、`RetryExecutor`自身が保持する`lineage`／`claim`参照（同一関数呼び出し内、trusted composition boundary、2.1節）に対し、構築した`root_run_id`／`attempt_ordinal`／`side_effect_contract_version`（いずれも2.1a節の既存field）が一致することを照合する。新しいidentity field／schemaは追加しない——既存3フィールドの相互一致チェックのみを行う。

**個別にはwell-formedだが構築元のlineage/claimと矛盾する値**（例：`RetryLineageProtectedProvenance.root_run_id`が、それ自体は妥当な形式のIDだが、`RetryExecutor`が実際に処理している`lineage.root_run_id`とは異なる値である——実装バグにより別lineageのprovenanceが誤って構築された状態を模擬）は、対応する理由コードでfail-closedする：

- `root_run_id`不一致：`MISSING_LINEAGE_CONTEXT`（識別対象そのものが本実行のlineageと一致しないため、2.2節#3と同じhard failure経路）
- `attempt_ordinal`不一致：`CONTEXT_MISMATCH`（`root_run_id`は正しいlineageを指すが、attempt世代が処理中のclaimと矛盾、2.2節#2と同じCONTRACT_VIOLATION経路）
- `side_effect_contract_version`不一致：`CONTRACT_VERSION_MISMATCH`

これらはいずれも2.5節の既存理由コードをそのまま再利用する——新しい理由コードは追加しない。この照合は2.1b節のwell-formedness検証より後に行われる（malformed検証が先、consistency照合は個別に有効な値同士にのみ適用される、28.-37節#5）。通過した値のみが**validated pre-context**として`WorkflowEngineManager.run()`へ渡される（`external I/O = 0`のままpre-I/O fail-closed、2.4節）。

**(2) WorkflowEngineExecutor — Member Completion Boundary**：`WorkflowEngineExecutor`は(1)で確立済みのvalidated pre-context（`root_run_id`／`attempt_ordinal`／`side_effect_contract_version`）を**再照合・再構築しない**——`lineage`／`claim`への参照を持たないため、そもそも再照合する手段を持たない。`WorkflowEngineExecutor`が行うのは、自らが発行する`run_id`（既存の`AgentContext.run_id`と同一値、10.2節）を`member_run_id`としてvalidated pre-contextへ追加し、protected factory（`build_protected_execution_context()`、2.1a節）を呼んで`RetryLineageProtectedExecutionContext`を完成させることのみである。この完成処理はvalidated pre-contextの3値を(1)から不変のまま引き継ぎ、書き換えない。`member_run_id`は`WorkflowEngineExecutor`自身が発行した値のみを用いる——呼び出し元・caller供給の値で上書きする経路は存在しない。

完成した`RetryLineageProtectedExecutionContext`はこれ以降、downstream boundary（2.6節）ではlosslessに伝播されるのみで、再照合・再構築は行われない。

### 2.3 `LegacyDirectExecutionContext`の要件

**Stage 1（`legacy_entrypoint`）**：以下の**既知のnon-lineage production entry point**（8本、22.1f・22.3.11節）のみが、`LegacyEntrypoint`のうち対応する値を指定して`build_legacy_direct_provenance()`（Stage 1 legacy factory、2.1a節）を呼んでよい：

- `scripts/run_news_agent.py` → `LegacyEntrypoint.RUN_NEWS_AGENT`
- `scripts/run_workflow_trigger_agent.py` → `LegacyEntrypoint.RUN_WORKFLOW_TRIGGER_AGENT`
- `scripts/run_publish_trigger_agent.py` → `LegacyEntrypoint.RUN_PUBLISH_TRIGGER_AGENT`
- `scripts/run_review_trigger_agent.py` → `LegacyEntrypoint.RUN_REVIEW_TRIGGER_AGENT`
- `scripts/run_ai_publish.py` → `LegacyEntrypoint.RUN_AI_PUBLISH`
- `scripts/run_ai_workflow.py` → `LegacyEntrypoint.RUN_AI_WORKFLOW`（下記参照）
- `scripts/run_workflow_engine.py`の`--job-id`手動指定／Scheduler経由実行 → `LegacyEntrypoint.RUN_WORKFLOW_ENGINE_DIRECT`
- project-root `main.py`の直接手動実行（ラッパースクリプトを経由しない`python main.py`起動、14.2・14.3節） → `LegacyEntrypoint.RUN_MAIN_DIRECT`（下記参照）

この8本は、`scripts/`配下の全ファイルのうち既知のnon-lineage entry pointの全量である（22.3.11節に詳細）。`AgentManager.from_config()`が構築する`self._executors`は、呼び出し元scriptに関わらず各Agent種別のConfig gateにのみ依存するため（2.1c節）、AgentManager経由の4本（`run_news_agent.py`・`run_workflow_trigger_agent.py`・`run_publish_trigger_agent.py`・`run_review_trigger_agent.py`）はいずれもfan-out先のAgentに応じたStage 2 originを要する。`run_ai_workflow.py`は`WorkflowRunner.from_config(config)`→`runner.run(article_id=..., dry_run=...)`をAgentManagerを一切経由せず直接呼ぶ独立したentrypointであり、`WorkflowRunner.from_config()`（`src/ai/workflow_runner.py:97-99`）が構築する`PublishStepExecutor(service=AiPublishService.from_env(...))`経由で呼び出し箇所Cへ到達する（下記「`run_ai_workflow.py`のStage 1/Stage 2」参照）。project-root`main.py`の直接手動実行は、`RUN_MAIN_DIRECT`/`MAIN_DIRECT`という専用の値を持つ（下記「`main.py`のStage 1/Stage 2」参照）——他のentrypointの値を代用・偽装申告する経路は持たない。

**Stage 2（`legacy_execution_origin`、fan-out境界での完成）**：`AgentManager.run()`は、fan-outする各`AgentExecutor`ごとに、その`AgentExecutor`が実際に包む具体的なAgent型（`AgentManager.from_config()`が構築時点で確実に把握している型、下記の対応表）から`LegacyExecutionOrigin`を決定し、`complete_legacy_execution_context(provenance, legacy_execution_origin)`（Stage 2 legacy factory、2.1a節）を呼んで`LegacyDirectExecutionContext`を個別に完成させる。**同一`AgentManager.run()`呼び出し内で複数executorが存在する場合、各executorは自分専用に完成させた別個の`LegacyDirectExecutionContext`インスタンスを受け取り、他のexecutor用に完成させたインスタンスを再利用（使い回し）しない**（immutableなdataclassであるため、参照を共有しても値としては安全ではあるが、`legacy_execution_origin`が別executorのものであれば監査証跡として誤りになる——値の安全性と監査証跡の正確性は別の要求である）：

| `AgentManager.from_config()`が構築するAgent型 | `LegacyExecutionOrigin` |
|---|---|
| `NewsAgent` | `NEWS_AGENT` |
| `WorkflowTriggerAgent` | `WORKFLOW_TRIGGER_AGENT` |
| `PublishTriggerAgent` | `PUBLISH_TRIGGER_AGENT` |
| `ReviewTriggerAgent` | `REVIEW_TRIGGER_AGENT` |

このmappingは`AgentManager.from_config()`（`src/ai/agent_manager.py:76-144`）が各Agentを構築する箇所で、Agent型が確定した時点の情報からのみ決定する——`AgentExecutor.execute()`実行時の文字列ベースの`self._agent.name()`照合には依存しない（`name()`は`AgentResult.agent_name`という別目的の既存fieldへ流れる値であり、fail-closedなauthoritative mappingの根拠には使わない、25章新規invariant参照）。**未知のAgent型が将来`AgentManager._executors`へ追加され、上記対応表に存在しない場合**：`complete_legacy_execution_context()`を呼ばず、当該executorの`side_effect_execution_context`を欠落のまま扱い、2.4節のfail-closedマトリクスに従う（当該executorがprotected side-effect operationへ到達する経路があれば、そこでmissing contextとしてfail-closedする——他のexecutor（正しくmappingされているもの）の実行には影響しない）。

**Stage 1/Stage 2非依存の直接経路**：`run_ai_publish.py`・`run_workflow_engine.py`は`AgentManager`を経由しないため、fan-outのambiguityが存在しない。これらのcomposition rootは、`build_legacy_direct_provenance()`直後の同一地点で`complete_legacy_execution_context(provenance, LegacyExecutionOrigin.AI_PUBLISH_DIRECT)`／`complete_legacy_execution_context(provenance, LegacyExecutionOrigin.WORKFLOW_ENGINE_DIRECT)`をそれぞれ呼び、Stage 1とStage 2を実質的に同時に完了させる。

**`main.py`のStage 1/Stage 2（trusted direct composition root）**：project-root`main.py`の直接手動実行（ラッパースクリプトを経由しない`python main.py`起動）も、`AgentManager`・`WorkflowRunner`のいずれも経由しない単一プロセスであり、fan-outのambiguityが存在しない。この運用では、`main.py`自身が**trusted direct composition root**として機能する——外部のoperatorや薄いラッパーが事前にcontextを構築・環境変数へserializeすることは、bare `python main.py`が成立するための前提条件ではない。

`main.py`起動時のStage 1/Stage 2解決規則（14.3節`_parse_execution_context_from_env()`が権威）は以下の通り：

1. **authoritative serialized execution contextが環境変数として存在する場合**：14.3節の既存contractに従いstrict parse・validateしたうえで使用する（NEWS step subprocess・`run_workflow_engine.py`のRetry Lineage外呼び出し等、既知のsubprocess composition rootはこの経路を使う——これらのcomposition rootは14.2節の契約により、`main.py`をsubprocess起動する際は常に明示的にこの環境変数を設定する）。
2. **serialized contextが不在、かつ実際のtrusted entrypointがproject-root`main.py`の直接起動である場合**：`main.py`自身が`build_legacy_direct_provenance(LegacyEntrypoint.RUN_MAIN_DIRECT)`（Stage 1）の直後に`complete_legacy_execution_context(provenance, LegacyExecutionOrigin.MAIN_DIRECT)`（Stage 2）を自分自身の中で呼び、trusted composition rootとしてprovenanceをoriginする。これは「context欠落＝legacyへの汎用的な推測」ではない——欠落時に無条件でlegacyへfallbackするわけではなく、closed set上のただ1つの具体的なentrypoint（`main.py`自身であり、かつ既知のsubprocess composition rootは常に環境変数を明示的に設定するという14.2節の契約があるため、この分岐へ到達するのは構造的にbare direct invocationのみである）についてのみ、そのentrypoint自身がStage 1 provenanceの発生源になるという具体的な規則である。
3. **serialized contextが存在するが malformed／unknown／矛盾している場合**：規則2のself-origination経路へfallbackしない——`RUN_MAIN_DIRECT`への迂回的救済は行わず、既存の`CONTRADICTORY_SERIALIZED_FORM`／`UNKNOWN_LEGACY_ENTRYPOINT`等のfail-closed経路（14.3節）をそのまま適用し、実I/O前に停止する。
4. **downstream boundary（`main.py`より後段）でcontextが欠落した場合**：legacy推測は行わず、そのままfail-closedする（2.4節Fail-Closed Matrixと同一原則）。
5. **correlation metadataからのprovenance再構築は、いかなる場合も行わない**（2.1節Formal Trust-Boundary Invariant、25章#38）。

main.pyがサブプロセスとして`NewsPipelineRunner`から起動される場合（`legacy_execution_origin=NEWS_AGENT`）・`run_workflow_engine.py`のRetry Lineage外呼び出し経由で起動される場合（`legacy_execution_origin=WORKFLOW_ENGINE_DIRECT`）・運用者による直接手動実行の場合（`legacy_execution_origin=MAIN_DIRECT`、規則2）の3通りは、いずれも`main.py`側の分岐ロジックを変えない——値がclosed set内であることのみを検証する（14.2節と同一原則）。

**`run_ai_workflow.py`のStage 1/Stage 2**：`run_ai_workflow.py`も`AgentManager`を経由しないが、`AgentManager`のような複数Agent型のfan-outは存在しない一方で、`WorkflowRunner.run()`自身が内部で複数step（Improvement/ImprovementReview/Rewrite/RewriteReview/Publish/PublishReview）を1回の呼び出し内で順に実行する（`src/ai/workflow_runner.py:106-160`）。このうち`side_effect_execution_context`を実際に消費するのは`PublishStepExecutor`のみである（他のstep executorはWordPress/media protected operationへ到達しない）。したがって、`run_ai_workflow.py`のcomposition rootは、`build_legacy_direct_provenance(LegacyEntrypoint.RUN_AI_WORKFLOW)`（Stage 1）の直後に`complete_legacy_execution_context(provenance, LegacyExecutionOrigin.AI_WORKFLOW_DIRECT)`（Stage 2）を呼び、完成済みcontextを`WorkflowRunner.run(article_id, dry_run, side_effect_execution_context=completed_context)`（`WorkflowTriggerAgent`経路と同一引数、22.1f節）へそのまま渡す。`WorkflowRunner.run()`は受け取ったcontextを`WorkflowContext`（既存field、22.1f節）へ格納し、`PublishStepExecutor.execute()`のみがこれを読み取って`AiPublishService.run()`へ伝播する——`WorkflowRunner`自身は呼び出し元が`WorkflowTriggerAgent`経由か`run_ai_workflow.py`直接かを区別する必要がなく、既存の単一`side_effect_execution_context`引数をそのまま中継するだけでよい（Stage 2の完成はあくまで各composition rootの責務であり、`WorkflowRunner`はそれを受け取って中継する薄い経路のまま維持される）。

**mode未指定をlegacyへ推測しない**：上記8 explicit legacy entrypoints（7スクリプト＋project-root `main.py`）以外の呼び出し元が`SideEffectExecutionContext`を供給しなかった場合、これを`LegacyDirectExecutionContext`とみなさず、2.4節のfail-closedマトリクスに従う（missing contextとして扱う）。同様に、AgentManager経由でStage 2が未完成のまま（`legacy_execution_origin`が決定できないまま）呼び出し箇所へ到達することも、missing contextと同様にfail-closedする——Stage 1のみでStage 2を推測することはない。

**Durable Evidence Contractの精緻化（2.3節）**：durable store（`WordPressDraftStateStore`/`MediaUploadSafetyCoordinator`）は、**exact protected identity（`root_run_id`/`attempt_ordinal`/`operation_instance_key`等がすべて揃っている場合）**についてのみ、matching検証（member mismatch・attempt mismatch・phase/state contradiction等）を行う——これは9.9.4.4節の`_read_all()`・12章の決定表として既に確立済みの、既存の仕組みそのものである。**durable storeを「identityなしのlegacy mode検出器」として使うことはしない**——`operation_instance_key`（記事単位の識別子）だけを手がかりに過去のprotected record有無を横断検索し、それを根拠に`LegacyDirectExecutionContext`を拒否するような検証は、正当なlegacy実行をfalse positiveで拒否しうるため、意図的に実装しない（6節参照）。

この場合、既存（6.31以前）のlegacy behaviorのまま動作する。6.32のwrite-ahead contractを要求しない。markerが存在しないことを`CONTRACT_VIOLATION`扱いしない——そもそも6.32の判定機構（10〜13章）自体が適用対象外である（18章のLegacy互換と同型の判定：`_is_6_32_contract_lineage()`相当の判定が、`RetryLineageRecord`自体が存在しないケースへ自然に拡張される）。

### 2.4 Fail-Closed Matrix

| context | 判定 |
|---|---|
| `RetryLineageProtectedExecutionContext`、全フィールド正常 | 6.32 write-ahead契約を適用（正常経路） |
| `RetryLineageProtectedExecutionContext`、`root_run_id`のみ欠落/破損 | hard failure（識別不能、external I/O=0、2.2節#3） |
| `RetryLineageProtectedExecutionContext`、`attempt_ordinal`/`member_run_id`/`side_effect_contract_version`のいずれか欠落/破損（`root_run_id`は正常） | `CONTRACT_VIOLATION`→HRR（識別可能、external I/O=0、2.2節#2） |
| `LegacyDirectExecutionContext`、`legacy_entrypoint`・`legacy_execution_origin`いずれもclosed set内 | legacy behavior（正常経路） |
| `LegacyDirectExecutionContext`、`legacy_entrypoint`がclosed set外 | hard failure（`UNKNOWN_LEGACY_ENTRYPOINT`） |
| `LegacyDirectExecutionContext`、`legacy_execution_origin`がclosed set外・または未完成（Stage 2未到達） | hard failure（`UNKNOWN_LEGACY_EXECUTION_ORIGIN`。AgentManager fan-out境界でのmapping漏れ・未知のexecutor型を含む） |
| `LegacyDirectExecutionContext`、`legacy_entrypoint`・`legacy_execution_origin`とも個別にはclosed set内だが、両者の組み合わせが`ALLOWED_LEGACY_ENTRYPOINT_ORIGINS`（2.1c節）に存在しない | hard failure（`CONTRADICTORY_LEGACY_PAIR`。individually-valid値同士の到達不可能な組み合わせ） |
| **context欠落（`None`）** | **hard failure（external I/O=0）。legacyへの推測は行わない** |
| **contextがいずれの型でもない** | **hard failure（external I/O=0、`UNKNOWN_EXECUTION_MODE`）** |
| **subprocess境界での serialized form が矛盾**（protected tag + legacy origin同時に存在、legacy tag + protected field同時に存在等） | **hard failure（14.3節、pre-I/O、external I/O=0）** |

### 2.5 Diagnostics（secret-safe構造化理由コード）

`SideEffectExecutionModeContractError`が保持する理由コードは、9.9.4.2節`CleanupFailureReasonCode`と同様のclosed-set・secret-safe設計とする：

```python
class ExecutionModeFailureReasonCode(Enum):
    MISSING_EXECUTION_MODE = "missing_execution_mode"
    UNKNOWN_EXECUTION_MODE = "unknown_execution_mode"          # RetryLineageProtectedExecutionContext/
                                                                  # LegacyDirectExecutionContextいずれでもない
    UNKNOWN_LEGACY_ENTRYPOINT = "unknown_legacy_entrypoint"      # legacy_entrypointがclosed set外
                                                                   # （Stage 1）
    UNKNOWN_LEGACY_EXECUTION_ORIGIN = "unknown_legacy_execution_origin"  # legacy_execution_originが
                                                                   # closed set外または未完成
                                                                   # （Stage 2）
    CONTRADICTORY_LEGACY_PAIR = "contradictory_legacy_pair"      # legacy_entrypoint・legacy_execution_origin
                                                                   # は個別にはclosed set内だが、両者の組み合わせが
                                                                   # ALLOWED_LEGACY_ENTRYPOINT_ORIGINS（2.1c節）に
                                                                   # 存在しない
    MISSING_LINEAGE_CONTEXT = "missing_lineage_context"          # root_run_id自体が欠落（2.2節#3）
    CONTEXT_MISMATCH = "context_mismatch"                        # attempt/member等の不一致（2.2節#2、CONTRACT_VIOLATIONへ合流）
    CONTRACT_VERSION_MISMATCH = "contract_version_mismatch"      # side_effect_contract_version不整合
    CONTRADICTORY_SERIALIZED_FORM = "contradictory_serialized_form"  # subprocess境界でmode tag+
                                                                        # 対応しないfieldが同時に存在、
                                                                        # またはmode tag自体が欠落して
                                                                        # いるのにprotected/legacy field
                                                                        # のいずれかが1つでも存在する
                                                                        # partial/orphan envelope（14.3節）
    SUBPROCESS_CONTRACT_VIOLATION = "subprocess_contract_violation"  # NEWS subprocess境界（14.6節）で
                                                                        # childがcontract violationにより
                                                                        # 予約exit codeで終了したことを親側
                                                                        # で検出。childの具体的なreason code
                                                                        # は境界を越えて伝達しない（stderr等の
                                                                        # 生テキストをprotocolにしないため）——
                                                                        # 親側はこの1値のみで再構築する


class SideEffectExecutionModeContractError(Exception):
    """SideEffectExecutionMode契約違反を表すfail-closed例外。呼び出し元
    （main.py・AiPublishService._post()等、15.6節）はこの例外をcatchして
    成功へ変換してはならない——常にそのまま伝播させるか、識別可能なlineageが
    存在する場合のみ12章のCONTRACT_VIOLATION経路へ変換する。"""
    def __init__(self, reason_code: ExecutionModeFailureReasonCode):
        self.reason_code = reason_code
        super().__init__(reason_code.value)  # 生の環境変数値・secretは一切含めない


# NEWS subprocess境界（14.6節）専用の予約exit code。main.py Outcome Contract
# （production_canonical_run_outcome_contract_foundation.md 5節）が既に使用する
# 0（SUCCESS）／1（GENERIC_FAILURE）／2（argparse usage error、同文書が明示的に
# 使用しないと定める）／20（PARTIAL）／21（ALL_FAILED）のいずれとも衝突しない値
# として3を予約する。child（main.py）・parent（NewsPipelineRunner）双方がこの
# 単一定数をimportし、値のハードコード重複を避ける。
SIDE_EFFECT_CONTRACT_VIOLATION_EXIT_CODE = 3
```

例外メッセージ本文・生の環境変数値・secret・payload本文はいずれも保存しない（9.9.4.5節と同一の規律）。

### 2.6 Propagation Contract

**既存コードの構造（`workflow_engine_manager.py`・`workflow_engine_executor.py`・`agent_context.py`・`agent_task.py`・`news_agent.py`）**：

1. `WorkflowEngineManager.run(..., correlation_metadata=...)`の`correlation_metadata`は`WorkflowEngineContext`経由で`_call_start_run()`（History記録専用）へのみ渡され、**`AgentContext`の構築には一切使われない**（`workflow_engine_executor.py`）。
2. 各stepの`AgentContext`は`AgentContext(task=AgentTask(task_id=..., params=dict(context.event.metadata)), dry_run=..., run_id=run_id, agent_name="")`として構築される——`params`は`WorkflowEngineEvent.metadata`（Scheduler由来）のみであり、retry lineageのidentityを運ぶ経路が存在しない。
3. `NewsAgent.act()`は`self._runner.run(params=context.task.params)`と、`AgentContext`の`task.params`のみを`NewsPipelineRunner.run()`へ渡している。

**是正した契約（discriminated union、2.1〜2.1b節、authoritative source）**：`correlation_metadata`・`event.metadata`・`task.params`のいずれも、side-effect safety identityのauthoritative sourceとして使わない。代わりに、専用のtyped channel（`AgentContext.side_effect_execution_context`という新規field、`WorkflowEngineContext.side_effect_execution_provenance`という新規field）を新設し、以下の経路で欠落なく伝播する：

```
RetryLineageRecord（root_run_id・attempt_ordinal・side_effect_contract_version、durable state）
  → RetryExecutor.execute()
      # RetryLineageProtectedProvenance（2.1a節、member_run_idはまだ未確定）を構築し、
      # 2.2a節(1)のconsistency validationを通過したもののみをvalidated
      # pre-contextとして渡す。このprovenanceを構築・検証できるのはRetryExecutor
      # のみ（trusted composition boundary、2.1節）。correlation_metadataは従来
      # どおりHistory相関用に別途構築・伝播する（無変更）。
    → WorkflowEngineManager.run(
          event, dry_run=..., target_step_filter=..., post_admission_hook=...,
          correlation_metadata=...,                       # 既存、History/相関用途のみ（無変更）
          side_effect_execution_provenance=...,            # 新設、2.1a節のUnion型
      )
      → WorkflowEngineContext（新規field: side_effect_execution_provenance）
        → WorkflowEngineExecutor
            # provenanceがRetryLineageProtectedProvenanceの場合のみ、このexecutorが
            # 発行するrun_id（既存のAgentContext.run_idと同一値）を渡して
            # protected factory（build_protected_execution_context()、2.1a節）を呼び、
            # RetryLineageProtectedExecutionContextを完成させる。3値の再照合は
            # 行わない（lineage/claimへの参照を持たない、2.2a節(2)）。
            # provenanceがLegacyDirectExecutionContextの場合は既に完成形なので
            # そのまま使う（factoryを再度呼ばない）。
          → AgentContext(
                task=AgentTask(task_id=..., params=dict(context.event.metadata)),  # 無変更、上書きしない
                dry_run=..., run_id=run_id, agent_name="",
                side_effect_execution_context=completed_context,  # 新規field、専用channel
                                                                     # （RetryLineageProtectedExecutionContext
                                                                     #  またはLegacyDirectExecutionContext）
            )
            → AgentExecutor.execute(agent_context) → BaseAgent.act(decision, context)
              → [NEWS] NewsAgent.act(): self._runner.run(
                    params=context.task.params,                              # 既存、無変更
                    side_effect_execution_context=context.side_effect_execution_context,  # 新規引数
                )
                → NewsPipelineRunner.run(params, side_effect_execution_context)
                  → subprocess.run(cmd, env={
                        ...,  # 既存env（ANTHROPIC_API_KEY等、無変更）
                        **_serialize_execution_context(side_effect_execution_context),  # 14.2節
                    })
                    → main.py（14.3節でtyped contextへ復元・検証）
                      → WordPressOutput.save()（呼び出し箇所A、15.7節）
                      → ArticleFeaturedMediaRuntime.apply()（呼び出し箇所B、15.4節）
              → [PUBLISH] PublishTriggerAgent.act()（NewsAgentと同型のBaseAgent実装）:
                    self._runner.run(
                        params=context.task.params,
                        side_effect_execution_context=context.side_effect_execution_context,
                    )
                → PublishPipelineRunner.run(params, side_effect_execution_context)
                  → AiPublishService.run(article_id=..., side_effect_execution_context=...)
                    → AiPublishService._post(review, rewrite, side_effect_execution_context)
                        （呼び出し箇所C、15.6節。subprocessを介さないため通常の関数引数として
                        そのまま伝播する——PUBLISH stepもNEWS stepと**同一のAgentContext経由の
                        channel**を使う。「PUBLISHは別経路で偶然contextを受け取る」という前提は
                        置かない、5節参照）
```

**`event.metadata`との非干渉**：`side_effect_execution_context`は`AgentContext`・`AgentTask`のいずれにおいても`params`/`metadata`とは独立した専用fieldであるため、Schedulerが供給する`event.metadata`にlineage-likeなキー（例：`"root_run_id"`という名前の任意の値）が偶然含まれていても、authoritative contextを上書き・混入する経路は構造的に存在しない（3節）。

**`_serialize_execution_context()`（14.2節）**：environment variablesは常にこの関数を通じて`side_effect_execution_context`（typed union）から生成する。`RetryLineageProtectedExecutionContext`ならprotected mode tag + 4フィールド、`LegacyDirectExecutionContext`ならlegacy mode tag + `legacy_entrypoint` + `legacy_execution_origin`（Stage分離済み）を書き出す——両者を混在させたenvを生成する経路自体が関数として存在しない（4節）。main.py側の`_parse_execution_context_from_env()`（14.3節）がこの逆変換を担い、mode tagと実際に存在するfieldの組み合わせが矛盾する場合（例：legacy tagなのに`RETRY_LINEAGE_ROOT_RUN_ID`が設定されている）は`CONTRADICTORY_SERIALIZED_FORM`でfail-closedする。

**Composition Root Provenance Contract（一般則）**：environment-variable経由のprovenance解決は、全entrypointに共通する以下の5規則に従う：

1. **approved trusted origin**：closed set上の各trusted composition root（2.1a・2.3節のfactory呼び出し元）は、それぞれのentrypoint固有のorigin ruleに従い、自分自身でStage 1 provenanceをoriginしてよい。これはlegacy推測ではなく、closed set上で一意に定まる具体的な規則である（例：main.pyのbare直接起動時のself-origination、2.3節「`main.py`のStage 1/Stage 2」規則2）。
2. **downstream consumer**：trusted composition root自身ではない、伝播経路の下流にあるコンポーネントは、missing contextからlegacyを推測しない——欠落は常にfail-closedする（2.4節Fail-Closed Matrix）。
3. **serialized envelope present**：authoritative serialized contextが環境変数として存在する場合、常にstrict parse・validateしたうえで使用する（14.3節）。
4. **envelope malformed／unknown／矛盾**：規則1のtrusted-origin self-generation経路へfallbackしない——実I/O前にfail-closedする（既存の`CONTRADICTORY_SERIALIZED_FORM`／`UNKNOWN_LEGACY_ENTRYPOINT`等の経路、14.3節）。
5. **correlation metadataからの再構築禁止**：いかなる場合もcorrelation metadata等からprovenanceを再構築しない（2.1節Formal Trust-Boundary Invariant、25章#38）。

main.pyは規則1に該当するtrusted composition rootの1つである——bare `python main.py`起動時、環境変数が一切設定されていない場合でも`MISSING_EXECUTION_MODE`による無条件hard failureにはならず、main.py自身が`LegacyEntrypoint.RUN_MAIN_DIRECT`／`LegacyExecutionOrigin.MAIN_DIRECT`をself-originする（2.3節「`main.py`のStage 1/Stage 2」規則2、14.2・14.3節）。一方、main.pyがsubprocessとして起動される場合（`scripts/run_news_agent.py`経由の`NewsPipelineRunner`・`run_workflow_engine.py`のRetry Lineage外呼び出し等）は、起動元のcomposition rootが規則1に基づき既にStage 1/Stage 2を完成させたうえで環境変数へserializeする——main.py自身は規則3に従いこれをstrict parse・validateするのみで、self-originationは行わない（14.2節「main.pyをsubprocess起動する際は常に明示的にこの環境変数を設定する」契約と整合）。main.pyを人手で直接実行する既知の正当な運用では、環境変数を一切設定しない場合は規則1のself-origination経路（`RUN_MAIN_DIRECT`/`MAIN_DIRECT`）がそのまま適用され、運用者による事前の環境変数設定は必須の前提条件ではない（14.3節「運用上の帰結」）。環境変数を明示的に設定する運用（`RETRY_LINEAGE_EXECUTION_MODE=legacy_direct`・`RETRY_LINEAGE_LEGACY_ENTRYPOINT=run_main_direct`・`RETRY_LINEAGE_LEGACY_EXECUTION_ORIGIN=main_direct`）も引き続き有効であり、規則3に従いstrict parse・validateされる。

**Legacy経路（`AgentManager`経由）の2段階provenance**：`scripts/run_news_agent.py`・`scripts/run_workflow_trigger_agent.py`・`scripts/run_publish_trigger_agent.py`・`scripts/run_review_trigger_agent.py`（2.3節）は、`AgentManager.from_config(config)`を構築した直後、Stage 1として`build_legacy_direct_provenance(LegacyEntrypoint.RUN_XXX)`（起動元scriptに対応する値、2.3節の対応表）を1回だけ構築する。この`LegacyDirectProvenance`は単体では呼び出し箇所A/B/Cへ渡せない（型が異なる、2.1節）——`AgentManager.run(task, dry_run, legacy_provenance)`（Stage 2、シグネチャへ`legacy_provenance: LegacyDirectProvenance`引数を追加）が、fan-outする各`AgentExecutor`ごとに、2.3節の対応表（`AgentManager.from_config()`が構築時点で確定させた各executorの具体的なAgent型）に基づき`complete_legacy_execution_context(legacy_provenance, legacy_execution_origin)`を個別に呼び、`AgentContext(..., side_effect_execution_context=completed_context)`として各executorへ渡す——**同一`run()`呼び出し内の複数executorへ同じ`LegacyDirectExecutionContext`インスタンスを使い回さない**（2.3節）：

```
scripts/run_news_agent.py（他3スクリプトも同型）
  → config = AgentConfig.from_env(...)
  → manager = AgentManager.from_config(config)          # 既存、無変更
  → legacy_provenance = build_legacy_direct_provenance(LegacyEntrypoint.RUN_NEWS_AGENT)  # Stage 1、新規
  → results = manager.run(task, dry_run=..., legacy_provenance=legacy_provenance)  # Stage 2の起点

AgentManager.run(task, dry_run, legacy_provenance):
  for executor in self._executors:      # 既存のfan-outループ、構造は無変更
      legacy_execution_origin = self._origin_for(executor)   # 2.3節の対応表、新規
      # 対応表に存在しない（未知のAgent型）場合は、side_effect_execution_context=None
      # のままAgentContextを構築する——2.4節のfail-closedマトリクスに従い、当該
      # executorが実際にprotected operationへ到達した時点でmissing contextとして
      # fail-closedする（推測しない）。
      completed_context = (
          complete_legacy_execution_context(legacy_provenance, legacy_execution_origin)
          if legacy_execution_origin is not None else None
      )
      context = AgentContext(
          task=task, dry_run=dry_run, run_id=self._generate_run_id(), agent_name="",
          side_effect_execution_context=completed_context,  # executorごとに個別完成、使い回さない
      )
      results.append(executor.execute(context))
```

`run_ai_publish.py`（`AgentContext`を経由しない直接呼び出し）は、Stage 1（`build_legacy_direct_provenance(LegacyEntrypoint.RUN_AI_PUBLISH)`）の直後、同一composition pointでStage 2（`complete_legacy_execution_context(provenance, LegacyExecutionOrigin.AI_PUBLISH_DIRECT)`）を呼び、`AiPublishService.run()`へ完成済みcontextを直接引数として渡す（fan-outが存在しないため、2段階を同時に完了させてよい、2.3節）。`run_workflow_engine.py`のRetry Lineage外呼び出しも同様に、`WorkflowEngineManager.run()`へ`complete_legacy_execution_context(provenance, LegacyExecutionOrigin.WORKFLOW_ENGINE_DIRECT)`の結果を明示的に渡す（`RetryExecutor`経由でない`.run()`呼び出しに、暗黙のデフォルトは存在しない）。**汎用的な`SideEffectExecutionContext`コンストラクタをmodeパラメータ付きで公開するproduction APIは提供しない**——呼び出せる関数自体がprotected factory/legacy Stage 1 factory/legacy Stage 2 factoryのいずれかに固定されている（2.1a節）。

**`WorkflowTriggerAgent`経由の呼び出し箇所C到達（22.3節詳細）**：`WorkflowTriggerAgent`（`AgentManager`の4executor種別の1つ）は、`AgentContext.side_effect_execution_context`を`WorkflowPipelineRunner.run(params, side_effect_execution_context)`→`WorkflowRunner.run(article_id, dry_run, side_effect_execution_context)`→`WorkflowContext.side_effect_execution_context`（新規field）→`PublishStepExecutor.execute(context)`→`AiPublishService.run(article_id=..., side_effect_execution_context=context.side_effect_execution_context)`という、NEWS/PUBLISH双方の既存経路（本節冒頭の図、15.6節）とは別個の伝播chainを経由して、呼び出し箇所Cへ到達する。この経路も`legacy_execution_origin=WORKFLOW_TRIGGER_AGENT`を保持したまま到達する（`PublishTriggerAgent`経由の`legacy_execution_origin=PUBLISH_TRIGGER_AGENT`とは値のレベルで区別される）。

CLI option化は必須としない（環境変数のみで契約を満たす、14.2節の既存方針を維持）。

### 2.7 Accepted Residual Risk

`LEGACY_DIRECT`経路における、WordPress POST成功と結果の永続化（`AiPublishRepository.save()`等の既存の非coordination保存処理）の間のクラッシュ窓は、6.32では解消されない。4章Non-Goals・29章に記録する。新しいdirect execution crash-window解消自体は引き続きOut of Scopeとする。

## 3. Goals

1. Protected Side Effect（7章で定義するclosed set）の実行前に、durableなwrite-ahead ACKを書く。ACK失敗時は外部I/Oを実行しない（9.9.3節）。
2. write-ahead ACK後・結果確定前にクラッシュ・再起動が発生した場合、当該runをfail-closedで`HUMAN_REVIEW_REQUIRED`（新規`RetryLineageDisposition`値）へ導き、自動Retryを構造的に阻止する（13章）。
3. `HUMAN_REVIEW_REQUIRED`はdurableに記録され、再起動を跨いで保持され、明示的なHuman actionなしに自動解除されない。
4. Step実行結果の分類（`StepOutcomeCategory`、6.31）と、副作用の安全性分類（新設）を、責務を混在させずにpureな最終disposition resolverで統合する（13章）。
5. Legacy（write-aheadマーカー導入以前）のExecution HistoryレコードをHRRへ一律で倒さない、6.32対象のみをdurablyに識別する仕組みを持つ（18章）。
6. 各Protected Side Effect Operationの安全性判定はattempt単位で独立し、他attemptの記録を再利用・誤帰属しない。
7. marker欠落を安全とみなせるのは、非到達／NOT_APPLICABLEをdurable evidenceで証明できる場合のみとする。
8. 同一article・同一attempt内でNEWS/PUBLISH双方の副作用が発生しても、identityが衝突しない。
9. durable stateへの書き込みは、明示的なcreate/compare-and-transition契約のみを経由し、任意の上書き・resetを行えるAPIを一切公開しない。
10. operationごとに構造的なON/OFF判定（Gate）が存在する場合、その判定結果をoperation単位のdurable evidenceとして記録し、stepレベルの成功/失敗と混同しない。
11. Operation Applicabilityの判定はoperation単位で独立に行い、同一step内の複数operationの評価結果が互いに影響しないようにする。
12. `NOT_APPLICABLE`の確定はdurable ACKを必須とし、ACKされない場合は「未確定（unproven）」として扱い、決して安全側へ推測しない。
13. `MEDIA_UPLOAD`の安全性判定が複数の独立したdurable storeにまたがる場合でも、単一のcoordination boundaryを経由することで、cross-store矛盾を発生させず、発生した場合は必ず検出する。
14. side-effect durable stateのread時、identityの全構成要素とmember_run_idを、record自身からではなく現在のRetry Lineageの権威ある状態から供給された期待値と照合し、一致しない場合は無条件にfail-closedとする。
15. durableに表現すべき境界を「呼び出しが成功を返したか」ではなく「external I/Oを開始してよい状態まで実際にcommitされたか」とし、両者が乖離しうる実装上の窓（呼び出し完了直前の副次的失敗）によって不要なHuman Reviewが発生しないようにする。
16. durable commitの権威を持つメソッド（`record_not_applicable()`・`record_prepared()`・`record_attempted()`・`record_confirmed()`）すべてについて、post-commitのcleanup失敗（lock解放・診断ログ含む）がsemantic successを虚偽のfailureへ反転させないことを、単一の共通機構で保証する。
17. `HUMAN_REVIEW_REQUIRED`という権威あるterminal dispositionの権威は`RetryLineageRecord`（`terminal_disposition`・`human_review_resolution`・`transition_history`）のみが持つ。独立した二次的判定経路（`RetryQueueUpdateDecider`のstep-only再計算等）によってCOMPLETE（成功）へ潰されることはない（22.4節）——Queue側はHRR専用の状態を持たず、既存のFAIL/FAILEDへ合流する。
18. protected side-effect（呼び出し箇所A/B/C）の実行provenance（`RetryLineageProtectedExecutionContext`/`LegacyDirectExecutionContext`のdiscriminated union、2章）は、trusted composition boundaryから常に明示的に供給される。値の有無からの暗黙推測によってprotected/legacyを判定しない。context欠落・型不一致・closed set外の値はすべてfail-closedとする。

## 4. Non-Goals

完全なidempotency key実装・`HUMAN_REVIEW_REQUIRED`解除UI・6.31 residual risksの無条件取り込み・`article_media_upload_state`の内部実装/スキーマ変更・Scheduler/Observability配線・画像生成Gate自体のロジック変更・record外部の事実との突合、はいずれもOut of Scope。

6.32はRetry Lineage context（`root_run_id`/`attempt_ordinal`/`member_run_id`が`RetryLineageRecord`から供給される実行）に限定したExplicit Side-Effect Execution Mode契約（2.1〜2.7節）である（29章#2）。以下は明示的にOut of Scopeとする（**2.3節・22.3.11節がauthoritativeなclosed setであり、本節の一覧はそれと同一の8本の集合を指す**）：

- `scripts/run_ai_publish.py`（`AiPublishService.from_env().run()`を直接呼ぶ手動実行）
- `scripts/run_ai_workflow.py`（`WorkflowRunner.from_config().run()`を直接呼ぶ手動実行）
- `scripts/run_news_agent.py`・`scripts/run_workflow_trigger_agent.py`・`scripts/run_publish_trigger_agent.py`・`scripts/run_review_trigger_agent.py`（いずれも`AgentManager`経由、`RetryLineageManager`を一切経由しない）
- `scripts/run_workflow_engine.py`の`--job-id`手動指定・Scheduler経由の直接実行（`RetryExecutor`を経由しない`WorkflowEngineManager.run()`直接呼び出し）
- project-root`main.py`の直接手動実行（ラッパースクリプトを経由しない`python main.py`起動、14.2・14.3節）

これらの経路における、既存WordPress POST成功と`AiPublishRepository.save()`（結果の永続化）の間のクラッシュ窓の完全解消は、6.32のOut of Scopeとする。これは**accepted residual risk**として29章に記録し、本Releaseでは修正しない。理由：これらの経路は`RetryLineageRecord`を一切生成・参照しないため、6.32のwrite-ahead機構が要求する`SideEffectOperationIdentity`（8章）を構成するために必要な`root_run_id`/`attempt_ordinal`/`member_run_id`が構造的に存在しない（10.2節、14章）。

---

## 5. 用語・キー概念

以下の用語を用いる（`MediaUploadContextPhase`・IO_ARMED・Safe Continuation・ACK Determinism等を含む）。

| 用語 | 定義 |
|---|---|
| **semantic commit point** | あるメソッドにとって、durable stateがauthoritativeに確定したとみなす唯一の瞬間。この瞬間以降のいかなる失敗も、そのメソッドの成功結果を覆さない（9.9.4節）。メソッドごとに異なる（9.9.4・9.9.6・9.9.7節）。 |
| **Commit-Aware Lock Helper** | lock取得・body実行・lock解放を統一的に扱い、pre-commit失敗とpost-commit cleanup失敗を明確に区別する共通ヘルパー（9.9.4節）。 |
| **Structured Outcome（`acknowledged`/`cleanup_warning`）** | `acknowledged`はsemantic durable commitの成否を表すauthoritativeな値、`cleanup_warning`はpost-commit cleanup失敗の非authoritativeな診断情報（9.9.9節）。 |
| **identity-scoped lock** | `MEDIA_UPLOAD`のlockをCoordinator全体で1つではなく、Side-Effect Operation Identityごとに独立させる設計。あるidentityのstale lockが他identityの操作をブロックしない（27章）。 |

---

## 6. Design Decision A：Protected Side Effect Operationのclosed set（不変）

```python
class ProtectedSideEffectKind(Enum):
    WORDPRESS_DRAFT_CREATION = "wordpress_draft_creation"
    MEDIA_UPLOAD = "media_upload"
```

## 7. Design Decision B：Side-Effect Operation State Machine

```python
class SideEffectOperationState(Enum):
    NOT_APPLICABLE = "not_applicable"
    ATTEMPTED = "attempted"
    CONFIRMED_SUCCESS = "confirmed_success"
```

## 8. Design Decision C：Identity Schema（不変）

```python
class SideEffectSite(Enum):
    NEWS_STEP = "news_step"
    PUBLISH_STEP = "publish_step"


@dataclass(frozen=True)
class SideEffectOperationIdentity:
    root_run_id: str
    attempt_ordinal: int
    operation_kind: ProtectedSideEffectKind
    effect_site: SideEffectSite
    operation_instance_key: str

    def as_store_key(self) -> str:
        return (
            f"{self.root_run_id}:{self.attempt_ordinal}:"
            f"{self.operation_kind.value}:{self.effect_site.value}:"
            f"{self.operation_instance_key}"
        )
```

---

## 9. Design Decision D：Durable Record Schema と Create/Compare-and-Transition契約

### 9.1 パッケージ構成（不変）

- `src/article_media_upload_state/`（無変更）
- `src/wordpress_draft_state/`（新規、`WORDPRESS_DRAFT_CREATION`用）
- `src/side_effect_safety/`（新規、統合層）

### 9.2 Recordスキーマ

```python
@dataclass(frozen=True)
class WordPressDraftRecord:
    identity: SideEffectOperationIdentity
    member_run_id: str
    state: SideEffectOperationState      # 7章。NOT_APPLICABLE / ATTEMPTED / CONFIRMED_SUCCESS
    wp_post_id: int | None               # CONFIRMED_SUCCESSでのみ正のint必須。NOT_APPLICABLE/ATTEMPTEDではNone必須
    updated_at: str
    contract_version: int
```

### 9.3 Store公開API：create系1操作＋compare-and-transition1操作＋get

`WordPressDraftStateStore.create_not_applicable()`は、6.32時点のいずれの呼び出し箇所（15.6・15.7節）からも呼ばれないconsumer-less APIであり、6.32 current APIのscopeから除外する。将来`WORDPRESS_DRAFT_CREATION`に対する能動的なNOT_APPLICABLE確定が必要になった場合は、別Releaseで改めて設計する（7章のstate machine自体は`NOT_APPLICABLE`状態を引き続き閉じた集合の一員として保持し、`MediaUploadSafetyCoordinator`側の`record_not_applicable()`＜9.9節、能動的に使用中＞との構造的対称性は概念レベルでは維持するが、`WordPressDraftStateStore`/`WordPressDraftStateManager`の実装APIとしては6.32では提供しない）。

```python
@dataclass(frozen=True)
class CreateResult:
    acknowledged: bool
    reason: str | None
    record: WordPressDraftRecord | None


@dataclass(frozen=True)
class TransitionResult:
    acknowledged: bool
    reason: str | None
    record: WordPressDraftRecord | None


class WordPressDraftStateStore(ABC):
    @abstractmethod
    def create_attempted(
        self, identity: SideEffectOperationIdentity, member_run_id: str, updated_at: str,
    ) -> CreateResult:
        """新規identityにATTEMPTED状態のrecordをdurableに作成する（write-ahead）。"""

    @abstractmethod
    def transition_to_confirmed(
        self,
        identity: SideEffectOperationIdentity,
        expected_member_run_id: str,
        wp_post_id: int,
        updated_at: str,
    ) -> TransitionResult:
        """既存recordが (a) identityに一致し、(b) member_run_idが一致し、
        (c) state==ATTEMPTEDである場合のみCONFIRMED_SUCCESSへcompare-and-transitionする。"""

    @abstractmethod
    def get(
        self, identity: SideEffectOperationIdentity, expected_member_run_id: str,
    ) -> WordPressDraftRecord | None:
        """read-only・lock-free（27.3節、authoritative）。レコード非存在はNone。
        schema違反・identity不一致・expected_member_run_id不一致は
        WordPressDraftStateCorruptedErrorを送出する
        （9.3節「get(identity, expected_member_run_id)の契約」参照）。"""
```

`save()`・`delete()`・`reset()`・`overwrite()`に相当するAPIは一切存在しない。`create_not_applicable()`も6.32 current APIから除外済み（本節冒頭参照）。

**`WORDPRESS_DRAFT_CREATION`：単一StoreがShared Coordination Boundaryを兼ねる（WordPress parity）**：`WordPressDraftStateStore`（`create_attempted()`/`transition_to_confirmed()`/`get()`）は単一のstoreであり、9.4節のduplicate排他がそのままShared Coordination Boundaryとして機能する。

**`get(identity, expected_member_run_id)`の契約**：レコードが見つかった場合、以下をすべて検証する——

1. 永続化された`root_run_id`/`attempt_ordinal`/`operation_kind`/`effect_site`/`operation_instance_key`が、要求された`identity`の各構成要素と一致すること（9.7節、requested/persisted identity突合）。
2. 永続化された`WordPressDraftRecord.member_run_id`（9.2節、既存フィールド）が`expected_member_run_id`と一致すること。

いずれか1つでも不一致・破損していれば`WordPressDraftStateCorruptedError`を送出する（`CONTRACT_VIOLATION`、12章）。`WORDPRESS_DRAFT_CREATION`は`member_run_id`が常にrecord自身のフィールドとして存在するため、`MEDIA_UPLOAD`（9.9節）のような追加のcontext storeは不要である（WordPress parity、9.3節）。

### 9.4 duplicate判定は`state`を問わない

duplicate判定は「このidentityに何らかのrecordが既に存在するか」の1点のみで行う（`create_attempted()`が唯一のcreate系操作であり、同一identityへの2回目の呼び出しはこの1点のみでduplicateとして拒否される、9.3節）。

### 9.5 Manager層

```python
class WordPressDraftStateManager:
    """record_not_applicable()は6.32 current APIから除外済み
    （9.3節）。将来必要になれば別Releaseで追加する。"""
    def __init__(self, store: WordPressDraftStateStore):
        self._store = store

    def record_attempted(
        self, identity: SideEffectOperationIdentity, member_run_id: str,
    ) -> WordPressDraftRecord:
        result = self._store.create_attempted(identity, member_run_id, now_utc_iso())
        if not result.acknowledged:
            raise WordPressDraftStateTransitionError(result.reason)
        return result.record

    def record_confirmed(
        self, identity: SideEffectOperationIdentity, member_run_id: str, wp_post_id: int,
    ) -> WordPressDraftRecord:
        if type(wp_post_id) is not int or wp_post_id <= 0:
            raise ValueError("wp_post_id must be a positive int (bool rejected)")
        result = self._store.transition_to_confirmed(identity, member_run_id, wp_post_id, now_utc_iso())
        if not result.acknowledged:
            raise WordPressDraftStateTransitionError(result.reason)
        return result.record

    def get_state(
        self, identity: SideEffectOperationIdentity, expected_member_run_id: str,
    ) -> WordPressDraftRecord | None:
        return self._store.get(identity, expected_member_run_id)
```

### 9.6 例外の分離（不変）

```python
class WordPressDraftStateIOError(Exception): ...
class WordPressDraftStateCorruptedError(Exception): ...
class WordPressDraftStateTransitionError(Exception): ...
```

`create_attempted()`の`WordPressDraftStateIOError`は、通常のI/O失敗として例外がそのまま送出される（9.3節、fail-closed）。`create_not_applicable()`は6.32 current APIから除外されているため（9.3節）、これに関する記述は本節にはない。

### 9.7 永続化キーとcorrupted判定（不変）

`{base_dir}/{sha256(identity.as_store_key())}.json`。ハッシュ化前の個別フィールドを冗長に保存し、読み取り時に突合する。

### 9.8 `article_media_upload_state`側の統合アダプター（不変）

`ATTEMPTED`/`CONFIRMED_SUCCESS`は既存`article_media_upload_state`へ委譲する。

`WordPressDraftStateStore`の`create_attempted()`/`transition_to_confirmed()`にも、9.9.4節と同型のCommit-Aware Lock Helperを適用する（25章）。`create_not_applicable()`はcurrent APIから除外されているため対象外（9.6節）。

### 9.9 `MEDIA_UPLOAD`：`MediaUploadSafetyCoordinator`

#### 9.9.1 durably表現すべき境界の再定義

「`record_attempted()`が呼び出し元へsuccessを返したこと」は安全性の境界としない——これは**プロセス内の関数呼び出しの成否**であり、durable stateとして独立に検証できるものではない。durable write自体が成功していても、その後の些末な処理（lock解放等）が失敗すれば、呼び出しは失敗を報告しうる。

**現行の境界定義**：durably表現すべき境界は「callerが成功を受け取ったか」ではなく、**「external I/Oを開始してよい状態まで、必要な全durable stateが実際にcommitされたか」**である。この境界自体を、durable state（`IO_ARMED`という明示的なphase値）として表現し、呼び出し側の成否とは独立に、reconciliationが直接観測できるようにする。

#### 9.9.2 `MediaUploadContextPhase`：2-phase design

```python
class MediaUploadContextPhase(Enum):
    PREPARED = "prepared"    # write-ahead準備中/完了。external I/O禁止
    IO_ARMED = "io_armed"    # external I/O開始前に必要な全durable stateが確定済み


@dataclass(frozen=True)
class MediaUploadAttemptContextRecord:
    identity: SideEffectOperationIdentity
    member_run_id: str
    phase: MediaUploadContextPhase
    updated_at: str
```

**遷移契約**：`PREPARED`から`IO_ARMED`への遷移のみをstrict compare-and-transitionとして許可する。逆方向（`IO_ARMED→PREPARED`）・reset（既存`IO_ARMED`を`PREPARED`へ戻す、または既存recordを削除して新規`PREPARED`を作り直す）は、いずれもAPIとして一切提供しない（9.9.6節Non-Recycleと同型の構造的禁止）。

#### 9.9.3 Write-ahead Ordering Contract

```
1. shared identity lock（MediaUploadSafetyCoordinatorLock、27章）を取得する
2. context PREPARED のdurable create + ACK確認（MediaUploadAttemptContextStore）
   ACKが得られなければ、ここで例外を送出し以降のステップへ進まない
3. ArticleMediaUploadState ATTEMPTED のdurable create + ACK確認
   （article_media_upload_state経由）
   ACKが得られなければ、ここで例外を送出し以降のステップへ進まない
4. context PREPARED→IO_ARMED のdurable compare-and-transition + ACK確認
   ACKが得られなければ、ここで例外を送出し以降のステップへ進まない
5. lock解放
6. 呼び出し元（15.4節）が external upload を実行する
   ※ステップ4のACKが確認できるまで、呼び出し元はこのステップへ進んではならない
7. CONFIRMED_SUCCESS のdurable transition（record_confirmed()、15.5節のConfirmation
   Invariant成立時のみ）
```

**契約（本節の核心）**：external I/O（ステップ6）は、ステップ4（`IO_ARMED`への遷移）のdurable ACKが確認された**後**にのみ実行してよい。ステップ2・3・4のいずれかが失敗した場合、呼び出し元は`orchestrator.apply()`を呼び出してはならない。

#### 9.9.4 Commit-Aware Lock Helper と4メソッドの実装

##### 9.9.4.1 なぜ単一メソッドへの適用では不十分か

`record_attempted()`にのみACK Determinismパターンを適用するのでは不十分である——`record_confirmed()`（`CONFIRMED_SUCCESS`のdurable ACK）と`record_not_applicable()`（`NOT_APPLICABLE`のdurable ACK）にも、durable commit成功後にlock解放等が失敗しうる同種の窓が存在する。`except OSError`という型限定や、ログ処理自体の非throwing保証の欠如といった不備も、単一メソッドへの局所対応では解消できない。

**設計方針**：4メソッドすべてに適用できる、単一の共通ヘルパー（`_run_with_commit_aware_lock()`）へロジックを集約し、個々のメソッドが独自にlock/cleanup処理を実装しない（バグの発生源を1箇所に限定する）。この集約設計により、4番目のメソッド`record_prepared()`（9.9.4.7節）も同一ヘルパーへ無改造で統合されている。

##### 9.9.4.2 Structured Outcome

```python
class CleanupFailureReasonCode(Enum):
    """cleanup_diagnosticsのreason_codeとして使う、closed-setな固定値。"""
    LOCK_RELEASE_FAILED = "lock_release_failed"
    POST_COMMIT_BODY_EXCEPTION = "post_commit_body_exception"
    # `_value_or_recover()`のStage 1・Stage 2でRecoveryPolicy.validate()が
    # wrong-kindを検出した場合に使う。
    RECOVERY_VALIDATION_FAILED = "recovery_validation_failed"


@dataclass(frozen=True)
class CleanupDiagnostic:
    """post-commit cleanup失敗のsecret-safeな診断情報（9.9.3節）。
    exception message本文・URL・credentials/token・API応答本文・
    request payload・記事本文・raw tracebackのいずれも保持しない。"""
    reason_code: CleanupFailureReasonCode
    exception_type: str          # 例外クラス名のみ（例："OSError"）。メッセージ本文は含まない
    operation_kind: str | None   # 既にsafeと定義された構造化識別子（6章）
    effect_site: str | None      # 同上（8章）
    occurred_at: str             # canonical UTC ISO8601


@dataclass(frozen=True)
class CommitAwareResult:
    """semantic resultとcleanup resultを分離する（9.9.3節）。"""
    acknowledged: bool                              # semantic durable commitの成否。常にTrue
                                                      # （Falseの場合はhelperが例外を送出するため、
                                                      #  この型のインスタンスとしては観測されない）
    value: object                                    # bodyの戻り値
    cleanup_diagnostics: tuple[CleanupDiagnostic, ...]  # post-commit cleanup失敗の
                                                      # 非authoritative診断（0件のことが多い）


@dataclass(frozen=True)
class NotApplicableMediaUploadSafetyRecord:
    """`record_not_applicable()`のみが構築するsemantic kind（Gate OFF、
    NOT_APPLICABLE durable marker）。"""
    identity: SideEffectOperationIdentity
    member_run_id: str
    updated_at: str


@dataclass(frozen=True)
class PreparedMediaUploadSafetyRecord:
    """`record_prepared()`のみが構築するsemantic kind（9.9.4.7節）。
    `MediaUploadContextPhase.PREPARED`のdurable ACKのみを表し、ATTEMPTED/IO_ARMED
    へは一切進んでいないことを型で保証する。`NotApplicableMediaUploadSafetyRecord`
    とは構造的に別の型であり、相互変換APIを持たない（PREPARED != NOT_APPLICABLE、
    29章#37）。"""
    identity: SideEffectOperationIdentity
    member_run_id: str
    updated_at: str


@dataclass(frozen=True)
class IoArmedMediaUploadSafetyRecord:
    """`record_attempted()`のsemantic commit point（IO_ARMED durable ACK確認、
    9.9.4.4節冒頭の表）が構築するsemantic kind。`article_media_upload_state`側の
    ATTEMPTEDと`MediaUploadAttemptContextStore`側のIO_ARMEDの両方が確定済み
    であることを表す。"""
    identity: SideEffectOperationIdentity
    member_run_id: str
    updated_at: str


@dataclass(frozen=True)
class ConfirmedMediaUploadSafetyRecord:
    """`record_confirmed()`のみが構築するsemantic kind（CONFIRMED_SUCCESS
    durable ACK）。"""
    identity: SideEffectOperationIdentity
    member_run_id: str
    media_id: int
    updated_at: str


# `MediaUploadSafetyCoordinator`の4公開メソッドの戻り値型（typed closed union、
# `_value_or_recover()`の保証機構はRecoveryPolicyベースのruntime validation）。
# 単一`MediaUploadSafetyRecord`dataclass＋`state: SideEffectOperationState`
# フィールドという設計は採用しない——既存3値の`SideEffectOperationState`
# （NOT_APPLICABLE/ATTEMPTED/CONFIRMED_SUCCESS、7章、`WORDPRESS_DRAFT_CREATION`側の
# state machineであり本ファイルとは無関係に不変）のいずれもPREPARED-onlyの状態を
# 正確に表せず、post-commit recovery経路が暫定的に`NOT_APPLICABLE`を代用して
# しまう欠陥を生む。4つのfrozen dataclassをclosed unionとして扱うことで、
# 各semantic kindを独立した型として表現する——4つの型はnominally distinct
# （相互に異なる名前・フィールド構成を持つ独立した型）である。
# ただし、Pythonの動的型システムは
# 「別のkindへの変換」を構文レベルで物理的に禁止するsealed unionを提供しない
# ——`isinstance`チェックを経ずに任意のdataclassインスタンスを返す実装バグは、
# 型定義それ自体では防げない。正しいsemantic kindの保証は、(1) 4つの型が
# nominally distinctであること、(2) 各公開メソッドが自分自身のkindのみを
# 構築するexact typingの実装規律、(3) `_value_or_recover()`の各フォールバック
# 段で`RecoveryPolicy.validate()`（下記）による明示的なruntime `isinstance`
# 検証を必ず経ること、という3層の組み合わせで初めて成立する（formal
# invariant、25章#40参照）。「構造的に不可能」という表現は、この3層目の
# runtime validationという実際の防御機構を覆い隠すため、本ファイルの
# `MediaUploadSafetyRecord`関連の記述からは用いない。
# 新しいdurable state・classificationの追加ではない——4つの型はいずれも
# 既存の`MediaUploadContextPhase`（PREPARED/IO_ARMED）・`ArticleMediaUploadState`
# （ATTEMPTED/CONFIRMED_SUCCESS）・NOT_APPLICABLE markerの組み合わせ（9.9.7節）を
# 型として表現し直したものに過ぎない。
MediaUploadSafetyRecord = (
    NotApplicableMediaUploadSafetyRecord
    | PreparedMediaUploadSafetyRecord
    | IoArmedMediaUploadSafetyRecord
    | ConfirmedMediaUploadSafetyRecord
)


def _minimal_safety_record(
    identity: SideEffectOperationIdentity,
    member_run_id: str,
    policy: "MediaUploadSafetyRecoveryPolicy",
) -> MediaUploadSafetyRecord:
    """`_value_or_recover()`の最終フォールバック段。追加のI/O（filesystem read等）
    を一切行わず、`policy.build_minimal()`（下記`MediaUploadSafetyRecoveryPolicy`、
    各公開メソッドが自分自身のsemantic kindへ束縛したpolicyインスタンス）を
    呼ぶだけで完結する。

    この関数はexternal storeへの依存を一切持たないため、durable read固有の
    失敗モード（一時的I/Oエラー・parse失敗・複数storeにまたがる部分観測等）を
    構造的に持たない——`_value_or_recover()`の段1（構築済み値）・段2（durable
    read）がいずれも失敗しても、この段だけは原則として失敗しえない、という
    設計上の役割は不変。

    `updated_at`のみ`now_utc_iso()`（純粋な時刻取得、I/Oなし）に依存するが、
    念のため個別にfail-safeとする。"""
    try:
        updated_at = now_utc_iso()
    except Exception:
        updated_at = ""
    return policy.build_minimal(updated_at)


# `_value_or_recover()`のvariant-specific recovery policy。expected concrete
# type・minimal construction・validationの3つを単一のPolicyオブジェクトへ
# 一体化し、呼び出し元がこれらを独立した複数引数として自由に組み合わせる
# API surfaceを持たない——各Policyクラスは自分自身のexpected_type以外の
# コンストラクタを呼ばない設計になっている（1クラス1コンストラクタ呼び出し）。
# 各公開メソッドが正しいPolicyクラスを選択していることは、28.-29節の
# direct source/static testで別途検証する（25章#40）。
class MediaUploadSafetyRecoveryPolicy(Protocol):
    """4つの具体的なPolicy（下記）が満たすべき最小契約。`expected_type`は
    各Policyクラスに固定されたClassVarであり、インスタンスごとに差し替え
    不可能——`build_minimal()`は必ず`expected_type`のインスタンスのみを
    構築する（各Policyクラスの実装規律、コンストラクタ呼び出し1箇所のみ）。
    `validate()`は例外を送出せず、wrong kindの場合は`None`を返す（呼び出し元
    ＝`_value_or_recover()`がフォールスルーの契機として使う、9.9.4.4節）。"""
    expected_type: "ClassVar[type[MediaUploadSafetyRecord]]"

    def build_minimal(self, updated_at: str) -> "MediaUploadSafetyRecord": ...

    def validate(self, value: object) -> "MediaUploadSafetyRecord | None": ...


@dataclass(frozen=True)
class NotApplicableRecoveryPolicy:
    """`record_not_applicable()`専用（9.9.4.4節）。"""
    identity: SideEffectOperationIdentity
    member_run_id: str
    expected_type: "ClassVar[type]" = NotApplicableMediaUploadSafetyRecord

    def build_minimal(self, updated_at: str) -> "MediaUploadSafetyRecord":
        return NotApplicableMediaUploadSafetyRecord(
            identity=self.identity, member_run_id=self.member_run_id, updated_at=updated_at,
        )

    def validate(self, value: object) -> "MediaUploadSafetyRecord | None":
        return value if isinstance(value, self.expected_type) else None


@dataclass(frozen=True)
class PreparedRecoveryPolicy:
    """`record_prepared()`専用（9.9.4.7節）。"""
    identity: SideEffectOperationIdentity
    member_run_id: str
    expected_type: "ClassVar[type]" = PreparedMediaUploadSafetyRecord

    def build_minimal(self, updated_at: str) -> "MediaUploadSafetyRecord":
        return PreparedMediaUploadSafetyRecord(
            identity=self.identity, member_run_id=self.member_run_id, updated_at=updated_at,
        )

    def validate(self, value: object) -> "MediaUploadSafetyRecord | None":
        return value if isinstance(value, self.expected_type) else None


@dataclass(frozen=True)
class IoArmedRecoveryPolicy:
    """`record_attempted()`専用（9.9.4.4節）。"""
    identity: SideEffectOperationIdentity
    member_run_id: str
    expected_type: "ClassVar[type]" = IoArmedMediaUploadSafetyRecord

    def build_minimal(self, updated_at: str) -> "MediaUploadSafetyRecord":
        return IoArmedMediaUploadSafetyRecord(
            identity=self.identity, member_run_id=self.member_run_id, updated_at=updated_at,
        )

    def validate(self, value: object) -> "MediaUploadSafetyRecord | None":
        return value if isinstance(value, self.expected_type) else None


@dataclass(frozen=True)
class ConfirmedRecoveryPolicy:
    """`record_confirmed()`専用（9.9.4.4節）。`media_id`はconstruction時の
    引数であり、`expected_type`同様インスタンス化時に固定される——他の
    Policyの`build_minimal()`と混同されうる余地はない（各クラスがコンストラクタ
    呼び出しを1箇所のみ持つ）。"""
    identity: SideEffectOperationIdentity
    member_run_id: str
    media_id: int
    expected_type: "ClassVar[type]" = ConfirmedMediaUploadSafetyRecord

    def build_minimal(self, updated_at: str) -> "MediaUploadSafetyRecord":
        return ConfirmedMediaUploadSafetyRecord(
            identity=self.identity, member_run_id=self.member_run_id,
            media_id=self.media_id, updated_at=updated_at,
        )

    def validate(self, value: object) -> "MediaUploadSafetyRecord | None":
        return value if isinstance(value, self.expected_type) else None
```

##### 9.9.4.3 Commit-Aware Lock Helper

```python
def _run_with_commit_aware_lock(lock, identity, body) -> CommitAwareResult:
    """lock取得・body実行・lock解放を統一的に扱う（9.9.4節）。

    契約：
      - lock.acquire()が失敗した場合、bodyは一切実行されない（fail-closed）。
      - bodyはcommit_state（{"committed": bool, "value": object|None}、初期値
        {"committed": False, "value": None}）を受け取る。semantic commit point
        （メソッドごとに異なる、9.9.4.4節の表）に到達した時点で**直ちに**
        commit_state["committed"] = Trueを設定し、その**後**に戻り値を構築して
        commit_state["value"]へ格納すること（実装契約、9.9.4.4節）。
      - **bodyがcommitted=Trueを設定した
        後、通常のException（KeyboardInterrupt等のprocess-control例外を除く）を
        送出した場合**：本ヘルパーはcommit_state["committed"]を確認し、Trueであれば
        commit_state["value"]を用いて`acknowledged=True`のCommitAwareResultを
        返す（例外の内容はsecret-safeなCleanupDiagnosticへ変換してcleanup_diagnostics
        へ格納する、9.9.4.2節）。durable commitが既に確定している以上、これを
        failureとして報告しない。
      - bodyがcommitted=Trueに到達する前に通常のExceptionを送出した場合
        （pre-commit failure）：cleanup（lock解放）は試行するが、その結果に
        関わらず、元のbody例外をそのまま送出する（cleanup failureが
        pre-commit failureを上書きしない）。
      - **bodyが`Exception`ではないBaseException
        （`KeyboardInterrupt`・`SystemExit`・`GeneratorExit`等、process-control/
        cancellationを表す例外）を送出した場合**：commit_state["committed"]の
        値に関わらず、cleanup（lock解放）をbest-effortで試行した上で、
        **必ず**そのまま再送出する。durable commitの成否によってこれらの
        例外をsuppressしない（プロセスのシャットダウン・キャンセルを妨げない）。
      - bodyが正常returnしたにもかかわらずcommitted=Trueが設定されていない場合、
        実装契約違反として明示的に例外を送出する（`assert`には依存しない。
        `-O`/`PYTHONOPTIMIZE`実行時にも必ず検査される）。
      - post-commit cleanup（lock解放・診断情報構築）はExceptionの範囲で捕捉する。
        BaseExceptionを無条件に握りつぶすコードは、cleanup処理を含め一切設けない。
    """
    lock.acquire()
    commit_state = {"committed": False, "value": None}
    try:
        result = body(commit_state)
    except Exception as exc:
        if commit_state["committed"]:
            # durable commitは既に確定している。
            # body側の残処理（戻り値構築等）が失敗しても、成功を維持する。
            body_diag = _build_cleanup_diagnostic(
                CleanupFailureReasonCode.POST_COMMIT_BODY_EXCEPTION, exc, identity,
            )
            release_diag = _try_release_capturing_diagnostic(lock, identity)
            diagnostics = tuple(d for d in (body_diag, release_diag) if d is not None)
            return CommitAwareResult(
                acknowledged=True, value=commit_state["value"], cleanup_diagnostics=diagnostics,
            )
        _try_release_ignoring_result(lock)
        raise  # pre-commit failure：元のbody例外をそのまま送出する
    except BaseException:
        # KeyboardInterrupt/SystemExit/GeneratorExit等の
        # process-control例外は、commit_state["committed"]の値に関わらず、
        # cleanupのみbest-effortで試行して必ず再送出する（成功へ変換しない）。
        _try_release_ignoring_result(lock)
        raise

    if not commit_state["committed"]:
        # assertではなく明示的な例外送出（最適化実行時にも
        # 必ず動作する）。
        _try_release_ignoring_result(lock)
        raise MediaUploadSafetyImplementationContractError(
            "body returned normally without setting committed=True; "
            "this is an implementation contract violation"
        )

    release_diag = _try_release_capturing_diagnostic(lock, identity)
    diagnostics = (release_diag,) if release_diag is not None else ()
    return CommitAwareResult(acknowledged=True, value=result, cleanup_diagnostics=diagnostics)


def _try_release_ignoring_result(lock) -> None:
    """pre-commit failure・process-control例外経路でのcleanup。lock.release()自体の
    失敗は、元の例外の報告を妨げない（9.9.4節）。Exceptionの範囲でのみ捕捉する
    （BaseExceptionは素通しする——release()自体がKeyboardInterrupt等を送出した場合、
    それも再送出対象となる）。"""
    try:
        lock.release()
    except Exception:
        pass


def _try_release_capturing_diagnostic(lock, identity) -> "CleanupDiagnostic | None":
    """post-commit成功経路でのcleanup。lock.release()の失敗はCleanupDiagnosticとして
    記録するのみで、semantic successを覆さない（9.9.4節）。Exceptionの
    範囲でのみ捕捉する。診断情報自体が構築できない場合は`None`（診断なし）と
    なりうる（`_build_cleanup_diagnostic()`）——呼び出し元
    はいずれも`None`を許容する形で`cleanup_diagnostics`を組み立てる。"""
    try:
        lock.release()
        return None
    except Exception as release_error:
        return _build_cleanup_diagnostic(
            CleanupFailureReasonCode.LOCK_RELEASE_FAILED, release_error, identity,
        )


def _build_cleanup_diagnostic(
    reason_code: CleanupFailureReasonCode, error: BaseException, identity,
) -> "CleanupDiagnostic | None":
    """secret-safeな診断情報を構築する。
    exception message本文・URL・credentials/token・API応答本文・request payload・
    記事本文・raw tracebackのいずれも参照しない——例外の型名のみを扱う。

    自己防御的に構成し、**どのフィールド計算が失敗しても例外を外部へ伝播させない**
    （個々のフィールドごとのtry/except）。

    `CleanupDiagnostic(...)`構築自体が失敗した場合の最終防衛線は、**失敗しうる
    同じコンストラクタを再度呼ばない**——コンストラクタ自体が構造的に常に失敗する
    ような状況では、同じコンストラクタに依存する防衛線も失敗し例外が伝播しうる。
    構築が失敗した場合は診断情報なし（`None`）を返す——診断情報の欠落は
    許容できる劣化だが、post-commit成功を虚偽のfailureへ変える方がはるかに
    深刻であるため、この優先順位を採用する。戻り値の型を`CleanupDiagnostic | None`
    へ変更し、呼び出し元（9.9.4.3節のhelper・9.9.4.4節の各メソッド）は
    いずれも`None`を「診断なし」として扱う（既存の`tuple(d for d in (...) if d is not None)`
    パターンで自然に吸収される）。
    """
    try:
        exception_type = type(error).__name__
    except Exception:
        exception_type = "UnknownExceptionType"
    try:
        occurred_at = now_utc_iso()
    except Exception:
        occurred_at = ""
    try:
        operation_kind = identity.operation_kind.value if identity is not None else None
    except Exception:
        operation_kind = None
    try:
        effect_site = identity.effect_site.value if identity is not None else None
    except Exception:
        effect_site = None
    try:
        return CleanupDiagnostic(
            reason_code=reason_code,
            exception_type=exception_type,
            operation_kind=operation_kind,
            effect_site=effect_site,
            occurred_at=occurred_at,
        )
    except Exception:
        # 最終防衛線：CleanupDiagnostic自体の構築が失敗する場合、同じ
        # コンストラクタへは依存せず、診断情報なし（None）を返す。
        return None
```

##### 9.9.4.4 4メソッドの実装（commit-point sequencing統一、4メソッド共通）

**Architecture Invariant（4メソッド共通）**：durable semantic ACKと`committed=True`の間に、例外を送出しうる任意の処理を置かない。戻り値の構築は必ず`committed=True`設定の**後**に行う。

| メソッド | semantic ACK | `committed=True` | 戻り値構築 |
|---|---|---|---|
| `record_not_applicable` | `applicability_store.create()`が`acknowledged=True`を返した瞬間（NOT_APPLICABLE ACK） | ACK確認の直後 | `committed=True`設定後 |
| `record_prepared`（9.9.4.7節） | `attempt_context_store.create_prepared()`が`acknowledged=True`を返した瞬間（PREPARED ACK） | ACK確認の直後 | `committed=True`設定後 |
| `record_attempted` | `attempt_context_store.transition_to_io_armed()`が`acknowledged=True`を返した瞬間（IO_ARMED ACK） | ACK確認の直後 | `committed=True`設定後 |
| `record_confirmed` | `record_upload_succeeded()`の呼び出しが成功した瞬間（CONFIRMED_SUCCESS ACK） | ACK確認の直後 | `committed=True`設定後 |

これが4メソッド共通のcanonical Architecture Invariant表である（9.9.4.7節の`record_prepared()`実装はこの表の`record_prepared`行に従う）。

```python
class MediaUploadSafetyCoordinator:
    def __init__(
        self,
        media_upload_manager: ArticleMediaUploadStateManager,
        applicability_store: "MediaUploadApplicabilityStore",
        attempt_context_store: "MediaUploadAttemptContextStore",
        lock_factory: "Callable[[SideEffectOperationIdentity], MediaUploadSafetyCoordinatorLock]",
    ):
        self._media_upload_manager = media_upload_manager
        self._applicability_store = applicability_store
        self._attempt_context_store = attempt_context_store
        self._lock_factory = lock_factory

    def record_not_applicable(
        self, identity: SideEffectOperationIdentity, member_run_id: str,
    ) -> "NotApplicableMediaUploadSafetyRecord":
        def body(commit_state):
            self._read_all(identity, member_run_id, allow_absent_only=True)
            result = self._applicability_store.create(identity, member_run_id, now_utc_iso())
            if not result.acknowledged:
                raise MediaUploadSafetyIOError(result.reason)
            # NOT_APPLICABLE durable ACK確認。**直ちに**committed=Trueを設定する
            # （ACKとcommitted=Trueの間に、例外を
            #  送出しうる処理を置かない）。戻り値の構築はその後に行う。
            commit_state["committed"] = True
            prospective_record = NotApplicableMediaUploadSafetyRecord(
                identity=identity, member_run_id=member_run_id, updated_at=result.record.updated_at,
            )
            commit_state["value"] = prospective_record
            return prospective_record

        outcome = _run_with_commit_aware_lock(self._lock_factory(identity), identity, body)
        self._log_cleanup_diagnostics_if_any(identity, "record_not_applicable", outcome.cleanup_diagnostics)
        return self._value_or_recover(
            outcome, identity, member_run_id,
            policy=NotApplicableRecoveryPolicy(identity=identity, member_run_id=member_run_id),
        )

    def record_attempted(
        self, identity: SideEffectOperationIdentity, member_run_id: str,
    ) -> "IoArmedMediaUploadSafetyRecord":
        def body(commit_state):
            snapshot = self._read_all(identity, member_run_id, allow_absent_only=False)

            if snapshot.category == "ALL_ABSENT":
                context_result = self._attempt_context_store.create_prepared(
                    identity, member_run_id, now_utc_iso(),
                )
                if not context_result.acknowledged:  # PREPARED ACK（committed=Falseのまま）
                    raise MediaUploadSafetyIOError(context_result.reason)
                upload_started = self._media_upload_manager.record_upload_started(  # ATTEMPTED ACK
                    article_identity=identity.as_store_key(),
                )  # （committed=Falseのまま）
            elif snapshot.category in ("PREPARED_ONLY", "PREPARED_PLUS_ATTEMPTED"):
                if snapshot.category == "PREPARED_ONLY":
                    upload_started = self._media_upload_manager.record_upload_started(
                        article_identity=identity.as_store_key(),
                    )
                else:
                    upload_started = snapshot.upload_state  # Safe Continuation（不変）
            else:
                raise MediaUploadSafetyTransitionError(
                    f"cannot proceed: unexpected existing combination {snapshot.category}"
                )

            transition_result = self._attempt_context_store.transition_to_io_armed(
                identity, member_run_id, now_utc_iso(),
            )
            if not transition_result.acknowledged:
                raise MediaUploadSafetyIOError(transition_result.reason)
            # IO_ARMED durable ACK確認。**直ちに**committed=Trueを設定する
            # （PREPARED ACK・
            #  ATTEMPTED ACKの時点ではcommitted=Falseのままであり、その間に
            #  例外が発生した場合はpre-commit failureとして扱われ、9.9.5節の
            #  Crash Semantics「PREPARED+ATTEMPTED → safe pre-I/O」が
            #  restart後の分類を正しく処理する）。
            commit_state["committed"] = True
            prospective_record = IoArmedMediaUploadSafetyRecord(
                identity=identity, member_run_id=member_run_id, updated_at=upload_started.updated_at,
            )
            commit_state["value"] = prospective_record
            return prospective_record

        outcome = _run_with_commit_aware_lock(self._lock_factory(identity), identity, body)
        self._log_cleanup_diagnostics_if_any(identity, "record_attempted", outcome.cleanup_diagnostics)
        return self._value_or_recover(
            outcome, identity, member_run_id,
            policy=IoArmedRecoveryPolicy(identity=identity, member_run_id=member_run_id),
        )

    def record_confirmed(
        self, identity: SideEffectOperationIdentity, member_run_id: str, media_id: int,
    ) -> "ConfirmedMediaUploadSafetyRecord":
        def body(commit_state):
            snapshot = self._read_all(identity, member_run_id, allow_absent_only=False)
            if snapshot.category != "IO_ARMED_PLUS_ATTEMPTED":
                raise MediaUploadSafetyTransitionError(
                    f"cannot confirm: current combination is {snapshot.category}, "
                    f"expected IO_ARMED_PLUS_ATTEMPTED"
                )
            record = self._media_upload_manager.record_upload_succeeded(  # CONFIRMED_SUCCESS durable ACK
                article_identity=identity.as_store_key(), media_id=media_id,
            )
            # CONFIRMED_SUCCESS durable ACK確認。**直ちに**committed=Trueを設定する
            # （同一パターン、9.9.4.4節冒頭の表）。
            commit_state["committed"] = True
            prospective_record = ConfirmedMediaUploadSafetyRecord(
                identity=identity, member_run_id=member_run_id,
                media_id=media_id, updated_at=record.updated_at,
            )
            commit_state["value"] = prospective_record
            return prospective_record

        outcome = _run_with_commit_aware_lock(self._lock_factory(identity), identity, body)
        self._log_cleanup_diagnostics_if_any(identity, "record_confirmed", outcome.cleanup_diagnostics)
        return self._value_or_recover(
            outcome, identity, member_run_id,
            policy=ConfirmedRecoveryPolicy(identity=identity, member_run_id=member_run_id, media_id=media_id),
        )

    def _value_or_recover(
        self,
        outcome: "CommitAwareResult",
        identity: SideEffectOperationIdentity,
        member_run_id: str,
        policy: "MediaUploadSafetyRecoveryPolicy",
    ) -> "MediaUploadSafetyRecord":
        """post-commit経路で`commit_state["value"]`が構築されないまま
        （bodyの戻り値構築がcommitted=True設定後に失敗した場合）
        `outcome.value`が`None`になりうる。公開メソッドは自分自身の
        exact semantic kind（`policy.expected_type`）を返す契約を持つため、
        `None`はもちろん、wrong-kindの値もそのまま返さない。

        **（現行契約）** 単一の`policy`
        引数（9.9.4.2節`MediaUploadSafetyRecoveryPolicy`）のみを受け取り、
        expected concrete type・minimal construction・validationを呼び出し元が
        独立した複数引数として自由に組み合わせるAPI surfaceを持たない。
        3段階のfallbackで構成する。**全段で
        `policy.validate()`によるruntime `isinstance`検証を行い**、前段が
        失敗した、またはwrong kindを返したという理由だけでは例外を外部へ
        伝播させない：

        1. `outcome.value`（body内で正常に構築済みの値）。`policy.validate()`
           を通し、`policy.expected_type`と一致すればそのまま返す——この段で
           無検証returnすると、`outcome.value`がbody実装のバグにより
           `expected_type`と異なるkindだった場合、それをそのまま呼び出し元へ
           返してしまう。
           一致しない場合（non-Noneかつwrong kind）は、`_log_recovery_
           validation_failure()`でsecret-safeな固定診断（型名のみ、値・
           内容は含まない）を記録した上で、次段へフォールスルーする。
        2. `self._read_all()`（**lockを取得しない**）
           によるdurable stateの読み直し。durable writeが既に成功している場合、
           最も正確な値が得られる。ただし、この読み取り自体が（一時的なI/O
           エラー・parse失敗・複数storeの部分的観測等により）失敗する
           可能性がある——この失敗を無防備に伝播させると、acknowledged commit
           を再びfailureとして報告してしまうため、ここは例外を捕捉し次段へ
           フォールスルーする。
           読み取りに成功した場合も`policy.validate()`を通し、`expected_type`
           と一致しない場合（本来到達しないはずのcross-store不整合等）は、
           同じく`_log_recovery_validation_failure()`で記録した上で、誤った
           semantic kindのrecordをそのまま返さず段3へフォールスルーする。
        3. `_minimal_safety_record()`：追加I/Oを一切行わない、`policy.
           build_minimal()`（呼び出し元の公開メソッドが自分自身のsemantic
           kindへ束縛したpolicyインスタンス）のみから合成する、最終防衛線。
           この段も`policy.validate()`を通す——契約上は常に`expected_type`
           と一致するはずだが（`build_minimal()`の実装規律、コンストラクタ
           呼び出しを1箇所のみ持つ各Policyクラス）、万一一致しない場合は
           `assert`に依存しない明示的な実装契約違反として例外を送出する
           （25章#24と同型）。それ以外はこの段は原則として失敗しえない
           （filesystem・store等の外部依存を一切持たないため）。

        各公開メソッドの呼び出し元（exact ownerは15.4・15.5.1・22.3.2節を
        参照——本節はsemantic recoveryの内部機構のみを扱い、production
        caller ownershipをここで規定しない）はいずれも戻り値の詳細を実際には
        使用しないため、段2・3で返る値が
        durable storeの最新内容と完全に一致しなくても実害はない——重要なのは、
        durable commitが確定した
        （`outcome.acknowledged == True`）以上、**例外を送出しないこと**、
        および**（formal invariant——25章#40）
        acknowledged durable semantic commitを、戻り値構築・durable reread・
        post-commit cleanupのいずれの失敗によっても、別のsemantic kindへ
        再分類しないこと**である。`policy`は呼び出し元（9.9.4.4・9.9.4.7節の
        各公開メソッド）が固定するため、本メソッド自身が受け取った`policy`
        以外のsemantic kindを返すことはない——**この保証はPythonの型システムが
        変換を物理的に禁止するからではなく、`policy.validate()`が全段で
        runtime `isinstance`検証を行うことによって成立する**（9.9.4.2節冒頭
        コメント参照）。ただし本メソッド自身が保証できるのは「受け取った
        `policy`との整合性」のみである——呼び出し元の公開メソッドが、
        実装バグにより自分自身のsemantic kindとは異なる誤った`RecoveryPolicy`
        インスタンスを本メソッドへ渡してしまうケースまでは、本メソッドの
        runtime validationでは検出できない（本メソッドには「正しいpolicyは
        どれか」を知る手段がなく、渡された`policy`をそのまま信頼するほかない
        ため）。この「各公開メソッドが自分自身の正しい`RecoveryPolicy`を
        選択すること」自体はimplementation trust boundaryであり、28.-29節の
        direct source/static testによって別途担保する（25章#40）。
        """
        validated = policy.validate(outcome.value) if outcome.value is not None else None
        if validated is not None:
            return validated
        if outcome.value is not None:
            self._log_recovery_validation_failure(
                identity, "stage1_commit_state_value", policy.expected_type, type(outcome.value),
            )

        try:
            snapshot = self._read_all(identity, member_run_id, allow_absent_only=False)
            candidate = snapshot.to_safety_record()
        except Exception:
            candidate = None  # 復旧読み取り自体の失敗を、
            # acknowledged commitのfailure化に転嫁しない。段3へフォールスルーする。
        else:
            validated = policy.validate(candidate)
            if validated is not None:
                return validated
            if candidate is not None:
                self._log_recovery_validation_failure(
                    identity, "stage2_durable_reread", policy.expected_type, type(candidate),
                )

        minimal = _minimal_safety_record(identity, member_run_id, policy)
        validated = policy.validate(minimal)
        if validated is None:
            # 到達しないはずの経路（各Policyクラスの`build_minimal()`は常に
            # `expected_type`のみを返す実装規律を持つ）。到達した場合は
            # `assert`ではなく明示的な例外送出でfail-closedする（25章#24と同型）。
            raise MediaUploadSafetyImplementationContractError(
                "RecoveryPolicy.build_minimal() returned a value that fails its own "
                "validate(); this is an implementation contract violation"
            )
        return validated

    def get(
        self, identity: SideEffectOperationIdentity, expected_member_run_id: str,
    ) -> "MediaUploadSafetyRecord | None":
        """read専用・lock-free（27.3節、authoritative）。durable stateのみを権威とする
        （reconciliationがCONFIRMED_SUCCESS/NOT_APPLICABLEをauthoritativeに扱えることの
        直接的な根拠、9.9.6・9.9.7節）。identity-scoped lockは取得しない——stale
        identity lockの影響も受けない（27.5節）。`_read_all()`が読む各storeは
        それぞれ単体でold-or-newのcomplete file内容を返すが、複数store横断の
        composite atomicityは保証しない——cross-store skew自体は正常な
        観測タイミングの結果であり、その意味はCross-Store Combination
        Table（9.9.7節）が定めるexactな組み合わせ判定にのみ従う（27.3節）。"""
        snapshot = self._read_all(identity, expected_member_run_id, allow_absent_only=False)
        return snapshot.to_safety_record()

    def _log_cleanup_diagnostics_if_any(
        self, identity, method_name: str, diagnostics: "tuple[CleanupDiagnostic, ...]",
    ) -> None:
        """cleanup_diagnosticsが存在する場合、best-effortでログする。この処理自体の
        失敗も呼び出し元へ伝播させない。ログへ渡すのはCleanupDiagnostic（secret-safe、
        9.9.4.2節）のみであり、例外メッセージ本文・tracebackは一切渡さない。"""
        for diagnostic in diagnostics:
            try:
                logger.warning(
                    "post-commit cleanup failed after durable ACK",
                    extra={
                        "identity": identity.as_store_key(),
                        "method": method_name,
                        "reason_code": diagnostic.reason_code.value,
                        "exception_type": diagnostic.exception_type,
                        "operation_kind": diagnostic.operation_kind,
                        "effect_site": diagnostic.effect_site,
                        "occurred_at": diagnostic.occurred_at,
                    },
                )
            except Exception:
                pass  # ログ出力自体の失敗もsemantic resultへ伝播させない

    def _log_recovery_validation_failure(
        self, identity, stage: str, expected_type: type, actual_type: type,
    ) -> None:
        """`_value_or_recover()`の
        Stage 1・Stage 2で`RecoveryPolicy.validate()`がwrong-kindを検出した
        場合の、secret-safeな固定診断ログ。`CleanupDiagnostic`（9.9.4.2節）
        と同様、型名・stage名・operation_kind/effect_siteのみを保持し、
        recordの内容・値そのもの・例外メッセージ本文はいずれも保持しない。
        best-effortであり、この処理自体の失敗も呼び出し元（`_value_or_recover()`
        のフォールスルー）へ伝播させない。"""
        try:
            logger.warning(
                "recovery policy validation rejected unexpected semantic kind",
                extra={
                    "identity": identity.as_store_key(),
                    "stage": stage,
                    "expected_type": expected_type.__name__,
                    "actual_type": actual_type.__name__,
                    "reason_code": CleanupFailureReasonCode.RECOVERY_VALIDATION_FAILED.value,
                },
            )
        except Exception:
            pass  # ログ出力自体の失敗もフォールスルーを妨げない

    def _read_all(self, identity, expected_member_run_id, allow_absent_only) -> "_ThreeStoreSnapshot":
        """marker・context（phase含む）・upload_stateの3つを読み、
        identity全構成要素とmember_run_idを検証する。9.9.7節の組み合わせ表に従い
        categoryを判定する。

        allow_absent_only=Trueで呼ばれ、
        判定したcategoryがALL_ABSENTでない場合（record_not_applicable()が
        同一identity・同一member_run_idで2回目以降呼ばれた等、既存durable
        evidenceが存在する状態）、本メソッド自身がMediaUploadSafetyTransitionError
        を直接送出する。これが唯一の決定的outcomeであり、既存recordを冪等に
        そのまま返す分岐は存在しない。この送出はrecord_not_applicable()の
        body内でself._applicability_store.create()（duplicate durable mutation）
        を呼ぶ前に発生するため、9.9.4.3節のpre-commit failure契約により
        _run_with_commit_aware_lock()はcleanupのみを試行して元の例外をそのまま
        呼び出し元へ再送出する。commit_state["committed"]はFalseのまま
        （create()自体が一度も呼ばれない）であり、_value_or_recover()の
        durable reread（Stage 2）には一切到達しない。duplicate呼び出しが
        既存recordを回復結果として受け取ることはない（Invariant #11、
        28.-33節#1）。"""
        ...
```

##### 9.9.4.5 秘密情報の非保存

**なぜ例外メッセージ本文を保持しないか**：`str(error)[:200]`という形で例外メッセージ本文を200文字まで引用する設計は、200文字以内に収まる秘密情報（認証情報を含むURL・APIレスポンス本文の先頭部分等）をそのまま記録してしまう可能性があり、「秘密情報を保存しない」契約を満たさない。

**契約**：cleanup診断情報（`CleanupDiagnostic`、9.9.4.2節）が保持してよいのは、以下の4フィールドのみとする：

- `reason_code`：`CleanupFailureReasonCode`という閉じた集合（`LOCK_RELEASE_FAILED`/`POST_COMMIT_BODY_EXCEPTION`）の固定値
- `exception_type`：例外クラス名のみ（`type(error).__name__`、例："OSError"）
- `operation_kind`・`effect_site`：既にsafeと定義された構造化識別子（6・8章のclosed-set Enum値）
- `occurred_at`：canonical UTC ISO8601タイムスタンプ

**明示的に保存を禁止する情報**：例外メッセージ本文（`str(error)`・`repr(error)`）・URL・credentials/token・API応答本文・request payload・記事本文・任意のuser/external text・raw traceback。`_build_cleanup_diagnostic()`（9.9.4.3節）はこれらのいずれも参照しない実装とする。

診断情報の構築処理自体が失敗しても外部へ例外を伝播させず、semantic resultを変更しない（`_build_cleanup_diagnostic()`内の個別`try/except Exception`、9.9.4.3節）。この設計は`FeaturedMediaFailureObservation`（v6.25.0）の「raw exception・prompt・credential・Provider応答本文を保持しない」という既存precedentと同水準、またはそれ以上に厳格である。

##### 9.9.4.6 例外

```python
class MediaUploadSafetyIOError(Exception): ...              # filesystem I/O自体の失敗
class MediaUploadSafetyTransitionError(Exception): ...       # 許可されない遷移・duplicate・cross-store競合
class MediaUploadSafetyContractViolationError(Exception): ... # get()時、矛盾を検出
class MediaUploadSafetyImplementationContractError(Exception): ...
# bodyがcommit_state["committed"]=Trueを設定せずに正常returnした
# 場合に送出する（9.9.4.3節）。これは外部要因（I/O失敗等）ではなく、
# コーディネーター自身の実装契約違反（バグ）を示すため、他の3例外とは
# 性質が異なる——リトライやfail-closedな運用対応では解決せず、実装修正が
# 必要な不変条件違反として扱う。
```

##### 9.9.4.7 `record_prepared()`：4番目の公開メソッド

**理由**：15.4節が定めるpre-upload fallback境界（画像生成失敗で`upload()`へ一度も到達しないCONTINUE fallback）に対するoperation-specific durable evidenceを、既存3メソッド（`record_not_applicable()`/`record_attempted()`/`record_confirmed()`）だけでは表現できない——`record_attempted()`はPREPARED ACK→ATTEMPTED ACK→IO_ARMED ACKを単一の呼び出し内で不可分に駆動するため、「PREPARED止まりで意図的に停止する」独立entry pointを持たない。`record_prepared()`は、既存の内部機構（`_run_with_commit_aware_lock()`・`MediaUploadAttemptContextStore.create_prepared()`）をそのまま再利用し、ATTEMPTED/IO_ARMEDへは進まずPREPARED ACKのみでコミットして戻る。**新しいstate・classificationは一切追加しない**——`MediaUploadContextPhase.PREPARED`（9.9.2節）・`SideEffectSafetyCategory.SAFE_TO_CONTINUE`（9.9.7節）を既存のまま再利用する。

**保証の成立根拠**：`MediaUploadSafetyRecord`は`SideEffectOperationState`フィールド付きの単一dataclassではなく、`NotApplicableMediaUploadSafetyRecord`/`PreparedMediaUploadSafetyRecord`/`IoArmedMediaUploadSafetyRecord`/`ConfirmedMediaUploadSafetyRecord`の4つの型からなるtyped closed unionとする（9.9.4.2節）。acknowledged durable semantic commitが、戻り値構築・durable reread・post-commit cleanupのいずれの失敗によっても別のsemantic kindへ再分類されないことは、**型だけで構造的に保証されるのではなく**、(1) 4公開メソッドのexact public return type、(2) variant-specific internal `RecoveryPolicy`（9.9.4.2節）、(3) `_value_or_recover()`のStage 1/2/3全段でのruntime validation（`policy.validate()`）、(4) 各公開メソッドが自分自身の正しい`RecoveryPolicy`を選択していることを直接検証するsource/static test（28.-29節）——という4層の組み合わせによって成立する（formal invariant、25章#40）。(1)〜(3)はruntime validationが「渡されたpolicyとの整合性」を保証するのみであり、「公開メソッドが正しいpolicyを選択したこと」自体は実装側の責務（implementation trust boundary）であって、(4)のdirect testによって別途担保する。

**semantics**：

- 対象は**protected**（`RetryLineageProtectedExecutionContext`）＋**applicable**（Gate ON）な`MEDIA_UPLOAD`のみ。Gate OFF（not applicable）の場合は`record_not_applicable()`を呼ぶ——`record_prepared()`は呼ばない、PREPAREDを作らない（15.4.1節authoritative protected flow参照）。
- `PREPARED`のdurable ACKのみをコミット対象とする。`ArticleMediaUploadState`（`article_media_upload_state`）を`ATTEMPTED`へ進めない。
- `MediaUploadContextPhase`を`IO_ARMED`へ進めない。
- 本メソッド自身はexternal upload（`media_uploader.upload()`）を一切呼ばない・呼び出し元に許可しない（9.9.3節Ordering Contractのステップ2相当のみを実行し、ステップ3以降には進まない）。
- PREPARED ACK自体が失敗した場合（`context_result.acknowledged == False`、またはstore自体のI/O例外）：`MediaUploadSafetyIOError`を送出し、fail-closedする。**external upload count = 0**（そもそもwrite-ahead境界の手前で停止しているため、構造的にuploadへ到達しない）。
- identity・member_run_id・`SideEffectOperationIdentity`の全構成要素の検証は、他3メソッドと同一の`_read_all()`（9.9.4.4節）を経由する——exact identity/member validation（不一致は`MediaUploadSafetyTransitionError`）。
- 既存evidenceとの矛盾（例：`ATTEMPTED`/`IO_ARMED`/`CONFIRMED_SUCCESS`が既に存在する状態で`record_prepared()`が呼ばれる等、9.9.7節Cross-Store Combination Tableの矛盾行に該当する組み合わせ）は`MediaUploadSafetyContractViolationError`（またはTransition相当）でfail-closedし、`CONTRACT_VIOLATION`として扱う。既にPREPARED（またはPREPARED+ATTEMPTED）が存在する場合は、Safe Continuationと同型の冪等な no-op として扱い、既存recordをそのまま返す（duplicate PREPARED createとしてエラーにしない）。
- `record_prepared()`成功後のdurable stateは`SideEffectSafetyCategory.SAFE_TO_CONTINUE`に分類される（9.9.7節、既存行「非存在｜`PREPARED`｜非存在」）。**`PREPARED`は`NOT_APPLICABLE`と等価ではない**——`NOT_APPLICABLE`はGate OFFの明示markerであり、`PREPARED`はGate ON・applicable・pre-I/O段階のdurable evidenceである（両者は9.9.7節で別々の行として扱われ、混同しない）。
- pre-upload CONTINUE/PROPAGATE fallback（15.4節）では、step-level `StepOutcomeCategory`からsafeを推測しない——本メソッドが書き込んだPREPARED durable evidenceのみを安全性の根拠とする。
- 実際にuploadへ進む場合、既存`record_attempted()`は同一identityのPREPARED（`snapshot.category in ("PREPARED_ONLY", "PREPARED_PLUS_ATTEMPTED")`、9.9.4.4節の既存分岐）からATTEMPTED→IO_ARMEDへそのまま継続できる——`record_prepared()`が書き込んだPREPARED recordは、`record_attempted()`の既存Safe Continuation分岐にそのまま合流する契約であり、`record_attempted()`側の変更は不要。

**Commit-Aware Lock Helperへの統合（他3メソッドと同一パターン、9.9.4.4節の canonical Architecture Invariant表に`record_prepared`行として統合済み）**：

```python
    def record_prepared(
        self, identity: SideEffectOperationIdentity, member_run_id: str,
    ) -> "PreparedMediaUploadSafetyRecord":
        def body(commit_state):
            snapshot = self._read_all(identity, member_run_id, allow_absent_only=False)
            if snapshot.category == "ALL_ABSENT":
                context_result = self._attempt_context_store.create_prepared(
                    identity, member_run_id, now_utc_iso(),
                )
                if not context_result.acknowledged:  # PREPARED ACK
                    raise MediaUploadSafetyIOError(context_result.reason)
                context_record = context_result.record
            elif snapshot.category in ("PREPARED_ONLY", "PREPARED_PLUS_ATTEMPTED"):
                context_record = snapshot.context  # 冪等no-op（Safe Continuationと同型）
            else:
                raise MediaUploadSafetyTransitionError(
                    f"cannot prepare: unexpected existing combination {snapshot.category}"
                )
            # PREPARED durable ACK確認。**直ちに**committed=Trueを設定する
            # （他3メソッドと同一パターン、9.9.4.4節冒頭の表）。
            commit_state["committed"] = True
            prospective_record = PreparedMediaUploadSafetyRecord(
                identity=identity, member_run_id=member_run_id, updated_at=context_record.updated_at,
            )
            commit_state["value"] = prospective_record
            return prospective_record

        outcome = _run_with_commit_aware_lock(self._lock_factory(identity), identity, body)
        self._log_cleanup_diagnostics_if_any(identity, "record_prepared", outcome.cleanup_diagnostics)
        return self._value_or_recover(
            outcome, identity, member_run_id,
            policy=PreparedRecoveryPolicy(identity=identity, member_run_id=member_run_id),
        )
```

**`_value_or_recover()`のPREPARED-only recovery**：`PreparedRecoveryPolicy(identity=identity, member_run_id=member_run_id)`（9.9.4.2節）を`_value_or_recover()`へ渡すことで、段1（構築済み値）・段2（durable reread）・段3（`_minimal_safety_record()`）のいずれも`policy.validate()`によるruntime `isinstance`検証を経る（9.9.4.2節の`MediaUploadSafetyRecord`型定義、formal invariant＝25章#40）。呼び出し元はこの戻り値の詳細（`updated_at`の精度等）を実際には使用しない（29章#28・#33）が、**返る値のsemantic kindが誤って伝播することは、全フォールバック段のruntime validationによって防がれる**——この保証はPythonの型システムが変換を物理的に禁止することによってではなく、runtime validationによって成立する。

| durable state | external I/Oの状態 | 分類 | 理由 |
|---|---|---|---|
| `PREPARED`のみ（ATTEMPTED未確定） | 確実に未実行（I/O=0） | `SAFE_TO_CONTINUE`（durable safe pre-I/O state） | ステップ2で停止。ステップ3以降に到達していない |
| `PREPARED` + `ATTEMPTED` | 確実に未実行（I/O=0） | `SAFE_TO_CONTINUE`（durable safe pre-I/O state、Safe Continuation対象） | ステップ3で停止。`IO_ARMED`（ステップ4）に到達していないため、ステップ6（external I/O）へは絶対に進めない |
| `IO_ARMED` + `ATTEMPTED` | 開始された可能性を否定できない | `IN_PROGRESS_OR_UNKNOWN` → **HRR** | ステップ4のACK後、ステップ5（lock解放）〜ステップ6（external I/O）のどこかで停止した可能性がある |
| `IO_ARMED` durable ACK確認後、external call前にクラッシュ | 実際にはI/O=0 | `IN_PROGRESS_OR_UNKNOWN` → **HRR（許容する）** | 9.9.1節の設計上、`IO_ARMED`は「これ以降はexternal I/Oが発生したかどうかをdurable stateだけからは区別できない」という意図的な境界であるため、実際にはI/Oが発生していなくても安全側に倒す。**これは6.32のfail-closed crash windowとして明示的に受容する** |
| `IO_ARMED` + `CONFIRMED_SUCCESS` | 確定成功 | `CONFIRMED_SUCCESS` | ステップ7まで完了 |

**この設計の意義**：境界を`IO_ARMED`まで押し下げることで、**不要なHRRが発生しうる窓を「ステップ4のACK確認後からステップ6実行までの間」という、本質的に不可避な最小の窓にまで縮小している**（「`ATTEMPTED`が存在する」こと自体を安全性判断の境界とすると、ステップ2〜3の間のcrashもHRRになりうる過剰保守となる）。この最小の窓でのHRRは、`WORDPRESS_DRAFT_CREATION`の`ATTEMPTED`が持つのと同種の、意図的に受容するfail-closed窓である。

#### 9.9.6 ACK Determinism

**原則**：`transition_to_io_armed()`（ステップ4）のACKが確認された時点（`io_armed_committed = True`）以降、`record_attempted()`の戻り値は、後続の副次的な処理（lock解放、ログ出力、診断情報の記録等）の成否によって左右されない。

- 9.9.4節のコード例が示すとおり、`finally`ブロック内でのlock解放失敗は、`io_armed_committed`が`True`であれば例外として再送出せず、ログのみに留める。
- **例外（fail-closedの対象）**：`transition_to_io_armed()`自体の呼び出しが、ACKされたか否か判断できない形で失敗した場合（例：タイムアウトにより、durable writeが実際に成功したかどうか呼び出し元が知りようがない場合）は、`io_armed_committed`を`True`にせず、通常どおり例外を送出してfail-closedとする。「commit ACK自体が不明」な場合にまでsemantic resultとcleanup resultを分離する対象を広げない。
- この原則は、戻り値の構築（`_to_safety_record()`という共通ヘルパーを介さず、各公開メソッドが自分自身のsemantic kind——`NotApplicableMediaUploadSafetyRecord`等、9.9.4.2節——のfrozen dataclassコンストラクタを直接呼ぶ、9.9.4.4・9.9.4.7節）が例外を送出しないことを前提とする——既知良好な値（`_read_all()`で検証済みのidentity・member_run_id、durable writeが返した`record`オブジェクトの`updated_at`等）を単純に詰め替えるだけであり、I/O・追加のバリデーション・例外を発生させうる処理を一切行わない、という設計制約を課す（9.9.4節コメント）。

#### 9.9.7 Cross-Store Combination Table（PREPARED/IO_ARMEDを反映）

marker（`NOT_APPLICABLE`用）・context phase（`PREPARED`/`IO_ARMED`/非存在）・upload_state（`ATTEMPTED`/`CONFIRMED_SUCCESS`/非存在）の組み合わせ（18通り）：

| marker | context phase | upload_state | 分類 |
|---|---|---|---|
| 非存在 | 非存在 | 非存在 | 「all absent」→**`CONTRACT_VIOLATION`**（`MEDIA_UPLOAD`は`NOT_APPLICABLE`marker・`PREPARED`のいずれも書き込まれていない時点では、Gate ONで未着手・Gate OFFだがNOT_APPLICABLE ACK未完了のいずれかを区別できず、operation-specific durable non-reach evidenceが存在しないため、12.2節authoritative ruleにより`CONTRACT_VIOLATION`とする） |
| 非存在 | 非存在 | `ATTEMPTED` | **`CONTRACT_VIOLATION`**（contextなしでupload_state存在、lifecycle違反） |
| 非存在 | 非存在 | `CONFIRMED_SUCCESS` | **`CONTRACT_VIOLATION`**（同上） |
| 非存在 | `PREPARED` | 非存在 | `SAFE_TO_CONTINUE`（durable safe pre-I/O state） |
| 非存在 | `PREPARED` | `ATTEMPTED` | `SAFE_TO_CONTINUE`（durable safe pre-I/O state、Safe Continuation対象） |
| 非存在 | `PREPARED` | `CONFIRMED_SUCCESS` | **`CONTRACT_VIOLATION`**（`CONFIRMED_SUCCESS`は`IO_ARMED`到達後にのみ発生しうるため矛盾） |
| 非存在 | `IO_ARMED` | 非存在 | **`CONTRACT_VIOLATION`**（`IO_ARMED`は`ATTEMPTED`確定後にのみ到達するため矛盾） |
| 非存在 | `IO_ARMED` | `ATTEMPTED` | `IN_PROGRESS_OR_UNKNOWN` → HRR |
| 非存在 | `IO_ARMED` | `CONFIRMED_SUCCESS` | `CONFIRMED_SUCCESS` |
| あり | 非存在 | 非存在 | `NOT_APPLICABLE`（唯一の正常な「markerあり」ケース） |
| あり | それ以外の8通り | - | **`CONTRACT_VIOLATION`**（`NOT_APPLICABLE`とcontext/upload_stateの併存は常に矛盾） |

いずれかのstoreの読み取り時にidentity構成要素・member_run_idの不一致・レコード破損を検出した場合、この表を評価する前に無条件で`CONTRACT_VIOLATION`とする。**`ATTEMPTED`単独ではexternal-I/O-possibleのauthoritative evidenceにしない**——必ずcontext phaseとの組み合わせで判断する（9.9.1節の再定義と整合）。

#### 9.9.8 補助ストア・No Automatic Repair・例外

```python
class MediaUploadAttemptContextStore(ABC):
    def create_prepared(self, identity, member_run_id, updated_at) -> "CreateResult": ...
    def transition_to_io_armed(self, identity, expected_member_run_id, updated_at) -> "TransitionResult": ...
    def get(self, identity, expected_member_run_id) -> "MediaUploadAttemptContextRecord | None": ...
```

#### 9.9.9 Structured Outcomeの意義

`CommitAwareResult`の`acknowledged`フィールドは、reconciliation・呼び出し元の双方にとって単一の権威ある成否シグナルである。`cleanup_diagnostics`（9.9.4.2節）は運用診断のためだけに存在し、**disposition判定（12章）・Cross-Store Combination Table（9.9.7節）のいずれにも一切影響しない**——分類は常にdurable state（get()が読む実際のstore内容）のみに基づき、`cleanup_diagnostics`の有無や内容を参照しない。これにより、post-commit cleanup failureがdisposition判定へ迂回的に混入する経路を構造的に排除する。

---

## 10. Design Decision E：Operation Applicability原則とtyped Side-Effect Safety統合層

### 10.1 Operation Applicabilityはoperation単位で独立に判定する

Operation Applicabilityの判定はoperation単位で独立に行い、同一step内の複数operationの評価結果が互いに影響しないようにする（3章 Goals #11、25章 Defense-in-Depth Invariant #11と同一原則）。例えば同一NEWS step内で`WORDPRESS_DRAFT_CREATION`（常時applicable）と`MEDIA_UPLOAD`（Gate依存）が同時に評価されても、一方の判定が他方の判定へ波及しない（28.2節テスト#7で検証）。

### 10.2 `expected_member_run_id`の権威

`SideEffectSafetyClassifier.classify()`が受け取る`member_run_id`引数は、**呼び出し元がRetry Lineageの権威ある状態から供給する**——side-effect record自身（`WordPressDraftRecord`/`MediaUploadSafetyRecord`）から読み取った値を「期待値」として使うことは決してない：

- 同期経路（15.1節、`RetryExecutor.execute()`）：`engine_result.run_id`（今まさに実行中のattemptの、`WorkflowEngineManager`自身が発行したrun_id）。
- reconciliation経路（15.2節、`_reconcile_all_locked()`）：`record.latest_run_id`（`RetryLineageRecord`、6.31が`mark_execution_started()`で durableに記録した、当該attemptの権威あるmember_run_id）。

いずれも、6.31が既に確立した「lineageのdurable state」を情報源とし、6.32のside-effect storeが持つ値を情報源にしない。これにより、たとえside-effect storeのレコードが破損・改ざんされていても、「期待値」自体は汚染されない（9.9節の全ての`CONTRACT_VIOLATION`判定が、この汚染されていない期待値との比較に基づく）。

```python
class SideEffectSafetyClassifier:
    def __init__(
        self,
        media_coordinator: "MediaUploadSafetyCoordinator",
        draft_state: WordPressDraftStateStore,
    ): ...

    def classify(
        self,
        root_run_id: str,
        attempt_ordinal: int,
        member_run_id: str,  # 10.2節：Retry Lineageから供給された権威ある値
        operations: list[ProtectedOperationContext],
    ) -> "SideEffectSafetyReport":
        """各operationについて8章のidentityを構成する。operation_kind==MEDIA_UPLOADの
        場合はmedia_coordinator.get(identity, member_run_id)を、WORDPRESS_DRAFT_CREATIONの
        場合はdraft_state.get(identity, member_run_id)を呼ぶ——いずれもこの
        classify()が受け取ったmember_run_idをそのまま、変更せずに渡す。
        いずれかがContractViolation系の例外を送出した場合、当該operationは
        12章の通常の決定表を経由せず、直接SideEffectSafetyCategory.CONTRACT_VIOLATION
        へ分類する（12.5節）。"""
```

### 10.3 Reconciliationは現在のGate/configを再評価しない

reconciliation・classifyは、いかなる場合も現在のGate/config（環境変数等）を再評価しない。durable recordのみを権威とする（25章 Defense-in-Depth Invariant #13）。

---

## 11. Design Decision F：`SideEffectSafetyCategory`とHRRの位置づけ

### 11.1 closed set

**closed setの設計根拠**：`NOT_APPLICABLE`と`SAFE_TO_CONTINUE`は、(a) 明示的なdurable `NOT_APPLICABLE`marker、(b) durable safe pre-I/O state（`MEDIA_UPLOAD`の`PREPARED`系、9.9.5節）、という**2つの異なるdurable evidence**にそれぞれ対応する、明確に区別されたcategoryである。両者を単一のcategory名の下に融合すると、「record非存在時、step-level `StepOutcomeCategory`（`SILENT_NO_ACTION`等）を根拠にそのcategoryへ倒す」という誤った拡張を許す構造的リスクを生む——広い意味に読める単一category名は、evidence種別ごとの精密さを失わせる。両categoryとも13章`resolve_final_disposition()`における優先順位上は同じ最下位（HRRを発火させない）として扱う。

```python
class SideEffectSafetyCategory(Enum):
    NOT_APPLICABLE = "not_applicable"                  # 明示的なdurable NOT_APPLICABLE markerが存在する（12.2節）
    SAFE_TO_CONTINUE = "safe_to_continue"               # durable safe pre-I/O stateが存在し、I/O開始前で停止したことを
                                                          # operation-specific durable evidenceが証明する（9.9.5節PREPARED系）
    CONFIRMED_SUCCESS = "confirmed_success"             # CONFIRMED_SUCCESSレコードあり、かつmember_run_id等の整合性確認済み
    IN_PROGRESS_OR_UNKNOWN = "in_progress_or_unknown"   # ATTEMPTEDのまま（Crash Window B/C/D）、またはIO_ARMED到達後
    CONTRACT_VIOLATION = "contract_violation"           # 12章の決定表でどのカテゴリにも安全に分類できない全てのケース
                                                          # （record非存在だがoperation-specific durable non-reach evidence
                                                          #  が存在しない場合を含む）
```

`CONTRACT_VIOLATION`は「レコード破損」だけでなく、**「marker欠落だが到達を否定できない」ケースを含む正式なclosed-set categoryである**。`NOT_APPLICABLE`/`SAFE_TO_CONTINUE`という具体的evidence-boundなcategoryにのみ絞り込み、それ以外のrecord非存在は一律`CONTRACT_VIOLATION`とする、という厳格な型レベルの区別を採用する（12.2節）。

### 11.2 HRRとStepOutcomeCategoryを混在させない

- `StepOutcomeCategory`（6.31、6値）は無変更のまま維持し、`HUMAN_REVIEW_REQUIRED`をここへ追加しない。
- `SideEffectSafetyCategory`（本章、6.32新規5値、11.1節参照）も、`RetryLineageDisposition`ではない独立したclosed setとして維持する。
- 両者を統合するのは13章の`resolve_final_disposition()`のみであり、この関数だけが両方のenumを読み取り、単一の`RetryLineageDisposition`を出力する。

---

## 12. Design Decision G：Absence/Evidence Decision Table

**12.1〜12.4節の性格に関する注記**：以下12.1〜12.4節は、本書の他章が定める契約（2.2節Fail-Closed Matrix、9.3節`get()`のread時検証、9.9.7節Cross-Store Combination Table、10.1〜10.3節Operation Applicability、11.1〜11.2節`SideEffectSafetyCategory`、13章`resolve_final_disposition()`、15.5.2節、18.2節、`StepOutcomeCategory`実装＝`src/retry_lineage/retry_lineage_genuine_action.py`）から一意に導出したarchitecture decisionであり、既存章と矛盾しない。

### 12.1 `WORDPRESS_DRAFT_CREATION`のOperation Applicability（新規起草）

`WORDPRESS_DRAFT_CREATION`は6章Design Decision Aで確定済みのclosed set 2値のうち、`MEDIA_UPLOAD`と異なり**Gate依存の任意適用性を持たない**（10.1節「`WORDPRESS_DRAFT_CREATION`（常時applicable）」）。すなわち、あるattemptにおいて`WORDPRESS_DRAFT_CREATION`が「expected」かどうかは、**そのoperationが属するstep（`effect_site`＝`NEWS_STEP`または`PUBLISH_STEP`、15.3節`_STEP_TO_PROTECTED_OPERATIONS`表）が、当該attemptの`claim.steps_to_execute`（15.1節）に含まれているかどうかのみ**で決まる——config・環境変数・実行時のGate状態を一切参照しない（10.3節と同一原則）。stepが`steps_to_execute`に含まれていれば、`WORDPRESS_DRAFT_CREATION`は無条件にexpectedであり、`MEDIA_UPLOAD`のような「Gate OFFなら正常にNOT_APPLICABLE」という中間状態を持たない。

### 12.2 Decision Table

**authoritative rule（本節・9.9.7節が共通で従う）**：

1. marker absence（record自体が存在しないこと）は、それ単独では`NOT_APPLICABLE`にも`SAFE_TO_CONTINUE`にもならない。
2. `SideEffectSafetyCategory.NOT_APPLICABLE`/`SAFE_TO_CONTINUE`は、**durableかつoperation-specificなnon-reach evidenceが実在する場合にのみ**用いる。
3. 現行architectureにそのevidenceが存在しないoperation（`WORDPRESS_DRAFT_CREATION`、9.9.1節の意味でPREPARED相当の中間phaseを持たない単一phase write-ahead）については、evidenceを新規に推測・発明しない。
4. 具体的な写像：**explicit durable `NOT_APPLICABLE` marker → `NOT_APPLICABLE`**。**durable safe pre-I/O state（`MEDIA_UPLOAD`の`PREPARED`系、9.9.5節） → `SAFE_TO_CONTINUE`**。**confirmed state → `CONFIRMED_SUCCESS`**。**expected protected operationでrequired recordが非存在 → `CONTRACT_VIOLATION`**（`_expected_operation_contexts()`＜15.1節＞に含まれる時点で常にexpectedであるため、`operations`引数として`classify()`へ渡された全operationがこの意味で常にexpectedである、10.1節）。**I/O開始可能性を排除できない状態 → `IN_PROGRESS_OR_UNKNOWN`**。**`CONTRACT_VIOLATION`/`IN_PROGRESS_OR_UNKNOWN` → `HUMAN_REVIEW_REQUIRED`**（13・24章）。

`get(identity, expected_member_run_id)`（9.3節）が返す`WordPressDraftRecord | None`について、9.3節のread時検証（identity・member_run_id突合、不一致・破損は無条件で`CONTRACT_VIOLATION`、12.5節）を通過した後、以下の表を適用する：

| record state | 判定 |
|---|---|
| `CONFIRMED_SUCCESS` | `SideEffectSafetyCategory.CONFIRMED_SUCCESS`（durable evidenceが直接確定） |
| `ATTEMPTED` | `SideEffectSafetyCategory.IN_PROGRESS_OR_UNKNOWN`（write-ahead済みだが確認未達、9章のCrash Window） |
| `NOT_APPLICABLE`（明示marker） | `SideEffectSafetyCategory.NOT_APPLICABLE`（12.4節：現時点の6.32呼び出し箇所はこのmarkerを書き込まないが、APIとしては存在するため表に含める） |
| **非存在（record自体が`None`）** | **`SideEffectSafetyCategory.CONTRACT_VIOLATION`（上記authoritative rule#4。`WORDPRESS_DRAFT_CREATION`にはPREPARED相当のsafe pre-I/O durable evidenceが存在しないため、record非存在は常にCONTRACT_VIOLATIONとする）** |

**なぜstep-levelの`StepOutcomeCategory`を根拠にしないか**：`StepOutcomeCategory`（6.31既存、`classify_step_outcome()`/`classify_execution_history_step()`、`src/retry_lineage/retry_lineage_genuine_action.py`）はstep全体（NEWS step等）の粗い分類であり、その`action_taken`フィールドは「stepが何らかの出力を試みたか」を示すのみで、**同一step内の特定のprotected side-effect operation（`WORDPRESS_DRAFT_CREATION`）が実際にexternal I/Oへ到達したかどうかを個別に証明しない**——特に`SILENT_NO_ACTION`（`action_taken=False`）は「対象記事0件」等、stepレベルで出力対象が存在しなかったことしか示さず、**当該operationのexternal I/O未開始のoperation-specific durable evidenceではない**。したがって、record非存在時にstep-level `StepOutcomeCategory`を参照して`NOT_APPLICABLE`/`SAFE_TO_CONTINUE`等へ倒す「reachability rules」は採用しない（上記authoritative rule参照）。

**この節の直接の帰結**：「marker欠落を無条件に`NOT_APPLICABLE`/`SAFE_TO_CONTINUE`とみなす」は採用しない。`NOT_APPLICABLE`/`SAFE_TO_CONTINUE`と判定してよいのは、**operation-specificなdurable evidence（明示markerまたはPREPARED相当のsafe pre-I/O phase）が実在する場合のみ**であり、それ以外（record非存在一般、実行された可能性・失敗の詳細不明・分類不能）はすべて`CONTRACT_VIOLATION`として12.5節・13章経由で`HUMAN_REVIEW_REQUIRED`へ合流する。

### 12.3 Decision Tableの6原則（新規起草）

1. **durable evidence優先**：record自体が`ATTEMPTED`/`CONFIRMED_SUCCESS`/`NOT_APPLICABLE`のいずれかで存在する場合、record非存在時のfallback rule（12.2節）を一切参照しない——durable recordはstep-level推論より常に優先する。
2. **absenceは既定でsafeではない**：record非存在は、operation-specificなdurable evidence（明示`NOT_APPLICABLE`markerまたはPREPARED相当のsafe pre-I/O phase）が実在する場合にのみ`NOT_APPLICABLE`/`SAFE_TO_CONTINUE`とし、それ以外は`CONTRACT_VIOLATION`とする（本章の中核原則）。**stepレベルの`StepOutcomeCategory`（`action_taken`の有無を含む）は、record非存在時の判定根拠として一切使わない**。
3. **read時検証が最優先**：identity・member_run_id不一致やrecord破損（9.3節・9.7節）は、本表を評価する前に無条件で`CONTRACT_VIOLATION`とする（12.5節）。
4. **現在のGate/configを再評価しない**：本表はdurable state（record自体）のみを参照し、分類時点の環境変数・Gate状態を再取得・再評価しない（10.3節、25章#13と同一原則）。
5. **CONTRACT_VIOLATIONは自動修復しない**：`CONTRACT_VIOLATION`は`resolve_final_disposition()`（13章）を経て`HUMAN_REVIEW_REQUIRED`へ導かれるのみであり、reconciliationがこれを`NOT_APPLICABLE`/`SAFE_TO_CONTINUE`や`CONFIRMED_SUCCESS`へ推測的に読み替えることは一切ない（26章Non-Recycleと同型のno-automatic-repair原則）。
6. **operation単位の独立判定**：本表は`WORDPRESS_DRAFT_CREATION`単体のevidenceのみに基づいて判定し、同一step内の他operation（`MEDIA_UPLOAD`）のevidenceを代用・参照しない（10.1節Operation Applicability原則、25章#36）。

### 12.4 `NOT_APPLICABLE`markerの現状

`WordPressDraftStateManager.record_not_applicable()`（9.5節）・`WordPressDraftStateStore.create_not_applicable()`（9.3節）は6.32 current APIのscopeから除外されている（9.3・9.5節）——**したがって`WORDPRESS_DRAFT_CREATION`が明示的なdurable `NOT_APPLICABLE`markerを持つ経路は、6.32時点では構造的に存在しない**（APIが存在しないため、呼び出し漏れではなく設計上不可能）。12.2節の決定表における「`NOT_APPLICABLE`（明示marker）」行は、`MEDIA_UPLOAD`側の対応する仕組み（`MediaUploadSafetyCoordinator.record_not_applicable()`、9.9節、能動的に使用中）との構造的対称性を将来の設計変更で回復する余地を示す記録として表には残すが、6.32時点の`WORDPRESS_DRAFT_CREATION`ではこの行に到達する経路がない。将来この能動的なNOT_APPLICABLE確定が必要になった場合は、別Releaseで改めて設計する（1.4節の`article_media_upload_state`とは異なりAPI自体を今回削除するため、consumer-lessな予約APIとしての残置ではない点に注意）。

### 12.5 Contradictory Evidence原則

**`WORDPRESS_DRAFT_CREATION`**：9.3節のread時検証を通過すれば12.2節の表を適用する（不変）。

**`MEDIA_UPLOAD`**：`classify()`が`media_coordinator.get()`を呼ぶ。返り値が`None`の場合のみ12.2節の「レコード非存在」行（`CONTRACT_VIOLATION`、reachability rulesは参照しない）を適用する。それ以外は9.9.7節のCross-Store Combination Tableが最終的な分類を既に決定しているため、そのkindを直接`SideEffectSafetyCategory`へ写像する（`NOT_APPLICABLE`marker系→`NOT_APPLICABLE`、`PREPARED`系→`SAFE_TO_CONTINUE`、`IO_ARMED`+`ATTEMPTED`→`IN_PROGRESS_OR_UNKNOWN`、`IO_ARMED`+`CONFIRMED_SUCCESS`→`CONFIRMED_SUCCESS`）。`MediaUploadSafetyContractViolationError`は無条件に`CONTRACT_VIOLATION`。

---

## 13. Design Decision H：pureな最終Disposition Resolver

```python
def resolve_final_disposition(
    step_categories: list[StepOutcomeCategory],   # 6.31、無変更
    safety_report: SideEffectSafetyReport,         # 6.32、11・12章
) -> RetryLineageDisposition:
    """disposition_from_categories()（6.31、step-onlyの3値判定）はこの関数の内部で
    そのまま再利用し、変更しない。"""
    worst = safety_report.worst_case()  # 優先順位：CONTRACT_VIOLATION == IN_PROGRESS_OR_UNKNOWN > CONFIRMED_SUCCESS
                                          # > SAFE_TO_CONTINUE == NOT_APPLICABLE（disposition解決上の
                                          # 優先順位は最下位、HRRを発火させない、11.1節）

    if worst in (SideEffectSafetyCategory.IN_PROGRESS_OR_UNKNOWN,
                 SideEffectSafetyCategory.CONTRACT_VIOLATION):
        return RetryLineageDisposition.HUMAN_REVIEW_REQUIRED

    base_disposition = disposition_from_categories(step_categories)  # 6.31、無変更

    if worst == SideEffectSafetyCategory.CONFIRMED_SUCCESS and base_disposition != RetryLineageDisposition.SUCCEEDED:
        return RetryLineageDisposition.HUMAN_REVIEW_REQUIRED  # 本節末尾の解説段落を参照
                                                                 # （§11は11.1〜11.2のみで構成される）

    return base_disposition
```

本節の帰結（§11は11.1〜11.2のみで構成される）：`resolve_final_disposition()`が実際にRetry可能（`FAILED`/`NOT_ACTIONED`のまま）と判定するのは、(1) このattemptでProtected Side Effectに到達しなかったことをoperation-specificなdurable evidenceが示す場合（`worst`が`NOT_APPLICABLE`または`SAFE_TO_CONTINUE`のいずれか、11.1・12.2節）、(2) 副作用が確定成功しかつ他の全stepもGENUINE_SUCCESSだった場合（そもそも`SUCCEEDED`）、のいずれかのみである。

---

## 14. Subprocess/Cross-boundary Identity Propagation

### 14.1 何を伝達する必要があるか

main.py subprocess（NEWS step）が書き込むのは常に`effect_site=NEWS_STEP`の操作のみである。**`effect_site`はコンパイル時に呼び出し箇所ごとに固定されており、プロセス境界を越えて伝達する必要はない**（main.pyの中のWordPress POST呼び出しは常に`NEWS_STEP`、`ArticleFeaturedMediaOrchestrator`の呼び出しも常に`NEWS_STEP`と決め打ちでよい）。

伝達が必要なのは`SideEffectExecutionContext`（discriminated union、2.1節）全体であり、mode-specificなenvelopeとして以下のfieldから構成される（14.2節が権威）：

- **execution mode discriminator**（protected/legacyのいずれであるかを示すtag、2.1節）
- **Protected（`RetryLineageProtectedExecutionContext`）の場合**：`root_run_id`・`attempt_ordinal`・`member_run_id`・`side_effect_contract_version`の4フィールド全て
- **Legacy（`LegacyDirectExecutionContext`）の場合**：`legacy_entrypoint`・`legacy_execution_origin`の2フィールド全て（Stage分離、2.1節）

protected/legacyいずれのmodeも、上記envelopeの一部フィールドのみで完成した状態とはみなさない——mode discriminatorと、そのmodeに対応する全フィールドが揃って初めて有効なcontextとして扱う（4節・14.3節`CONTRADICTORY_SERIALIZED_FORM`）。

### 14.2 設計方針

- `root_run_id`・`attempt_ordinal`・`member_run_id`・`side_effect_contract_version`・`legacy_entrypoint`・`legacy_execution_origin`（Stage分離、2.1節）の伝達は、`correlation_metadata["retry_lineage"]`経由ではなく、2.6節Propagation Contractが定める唯一の経路（`SideEffectExecutionContext`→`WorkflowEngineManager`/`WorkflowEngineContext`→`WorkflowEngineExecutor`→`AgentContext`専用field→`NewsAgent`→`NewsPipelineRunner.run(params, side_effect_execution_context)`）を経由する。`correlation_metadata`はHistory/tracing用途としてのみ許可され、side-effect identityやexecution provenanceのauthoritative sourceとして使わない（2.6節）。`NewsPipelineRunner.run()`は受け取った`side_effect_execution_context`を`_serialize_execution_context()`（本節）で環境変数へ変換し、`subprocess.run(cmd, env=..., ...)`で`main.py`へ渡す。
- 環境変数（main.py既存CLI/env varとは衝突しない）：`RETRY_LINEAGE_ROOT_RUN_ID` / `RETRY_LINEAGE_ATTEMPT_ORDINAL` / `RETRY_LINEAGE_MEMBER_RUN_ID` / `RETRY_LINEAGE_CONTRACT_VERSION`（`RetryLineageProtectedExecutionContext`用）に加え、**`RETRY_LINEAGE_EXECUTION_MODE`（`"retry_lineage_protected"`/`"legacy_direct"`のmode tag）・`RETRY_LINEAGE_LEGACY_ENTRYPOINT`（`LegacyEntrypoint`の値、Stage 1）・`RETRY_LINEAGE_LEGACY_EXECUTION_ORIGIN`（`LegacyExecutionOrigin`の値、Stage 2。`LegacyDirectExecutionContext`用）を新規に追加する**（2.6節Propagation Contract）。

```python
def _serialize_execution_context(context: "SideEffectExecutionContext") -> dict[str, str]:
    """2.1a節のtyped unionをenvironment variablesへ変換する唯一の関数。
    protected/legacyそれぞれ対応するfieldのみを書き出し、両者を混在させない
    （4節）。"""
    if isinstance(context, RetryLineageProtectedExecutionContext):
        return {
            "RETRY_LINEAGE_EXECUTION_MODE": "retry_lineage_protected",
            "RETRY_LINEAGE_ROOT_RUN_ID": context.root_run_id,
            "RETRY_LINEAGE_ATTEMPT_ORDINAL": str(context.attempt_ordinal),
            "RETRY_LINEAGE_MEMBER_RUN_ID": context.member_run_id,
            "RETRY_LINEAGE_CONTRACT_VERSION": str(context.side_effect_contract_version),
        }
    if isinstance(context, LegacyDirectExecutionContext):
        return {
            "RETRY_LINEAGE_EXECUTION_MODE": "legacy_direct",
            "RETRY_LINEAGE_LEGACY_ENTRYPOINT": context.legacy_entrypoint.value,
            "RETRY_LINEAGE_LEGACY_EXECUTION_ORIGIN": context.legacy_execution_origin.value,
        }
    raise SideEffectExecutionModeContractError(ExecutionModeFailureReasonCode.UNKNOWN_EXECUTION_MODE)
```

main.pyへ到達するlegacy contextは、NEWS step経由のsubprocess境界を越える2通り（`NewsAgent`→`NewsPipelineRunner`→main.py subprocess、`legacy_execution_origin=NEWS_AGENT`／`run_workflow_engine.py`のRetry Lineage外呼び出しが`WorkflowEngineManager`経由でNEWS stepを実行する場合、`legacy_execution_origin=WORKFLOW_ENGINE_DIRECT`）に加え、運用者による直接手動実行（`legacy_execution_origin=MAIN_DIRECT`、subprocess境界を越えず起動時に自プロセス用の環境変数として直接供給される、2.3節「`main.py`のStage 1/Stage 2」）の計3通りがありうる——main.pyは`legacy_execution_origin`の具体的な値によって挙動を分岐せず、closed set内であることのみを検証する（値そのものは2.5節のsecret-safe診断・監査証跡として保持されるのみ）。

- **（採用しない設計、silent downgrade防止）** 「環境変数が未設定の場合、write-ahead機構を作動させない」という設計は採用しない——これは2.1節が禁止する「mode inference by absence」に該当する。既知のsubprocess composition root（`scripts/run_retry_runtime.py`経由の`RetryLineageProtectedExecutionContext`由来の5変数、`scripts/run_news_agent.py`・`scripts/run_workflow_engine.py`のRetry Lineage外呼び出し（22.1f節）が使う`LegacyDirectExecutionContext`由来の3変数）は、常に上記`_serialize_execution_context()`の出力どおり環境変数を明示的に設定してsubprocessを起動する契約である点は不変。project-root`main.py`の直接手動実行（環境変数を一切経由しない起動）については、main.py自身がtrusted direct composition rootとして`RUN_MAIN_DIRECT`/`MAIN_DIRECT`のprovenanceを自ら発生させる（2.3節「`main.py`のStage 1/Stage 2」、14.3節が権威）——運用者が事前に環境変数を設定することはこの経路の前提条件ではない。環境変数が設定されているが内容が矛盾／不明な場合は、この自己発生経路へ迂回せずfail-closedする（14.3節）。

### 14.3 main.py側のExplicit Execution Mode検証

main.pyは起動直後、環境変数から**`SideEffectExecutionContext`全体**（discriminated union、2.1節）を解決し、15.7節と同型のfail-closed検証を行う。解決した同一のcontextインスタンスは、呼び出し箇所A（`WordPressOutput`、15.7節）へは直接構築時に渡す一方、呼び出し箇所B（`ArticleFeaturedMediaRuntime`）へは**渡さない**——Bについては6.32 integration wiring層（`MediaUploadWriteAheadAdapters`・`build_protected_featured_media_runtime()`、22.3.2節）へ渡し、Foundationのconstructor（`ArticleFeaturedMediaRuntime.__init__(self, root)`）自体は無変更のまま維持する（15.4節「main.py側の配線との整合」）：

```python
def _parse_execution_context_from_env() -> "SideEffectExecutionContext":
    """14.2節`_serialize_execution_context()`の逆変換。main.py起動時に一度だけ呼ぶ。
    mode tagと実際に存在するfieldの組み合わせが矛盾する場合（例：legacy tagなのに
    protected fieldが設定されている、または mode tag自体が欠落しているのに
    protected/legacy fieldのいずれかが1つでも存在する）は、いずれの型も構築せず
    CONTRADICTORY_SERIALIZED_FORMでfail-closedする（4節、subprocess serialization
    boundary固有のチェック——型分離だけでは防げない、untypedな環境変数という
    媒体自体のリスクに対処する）。

    execution-envelope関連変数（mode tag・protected 4変数・legacy 2変数の
    いずれも）が完全に1つも存在しない場合に**限り**、main.py自身がtrusted direct
    composition rootとして`RUN_MAIN_DIRECT`/`MAIN_DIRECT`のStage 1/Stage 2
    provenanceを自己発生させる（2.3節「main.pyのStage 1/Stage 2」規則2が権威）。
    既知のsubprocess composition root（NEWS step・`run_workflow_engine.py`の
    Retry Lineage外呼び出し）は14.2節の契約により常にこの環境変数を明示的に
    設定するため、この分岐へ到達するのは構造的にbare `python main.py`直接起動
    のみである。"""
    protected_keys = (
        "RETRY_LINEAGE_ROOT_RUN_ID", "RETRY_LINEAGE_ATTEMPT_ORDINAL",
        "RETRY_LINEAGE_MEMBER_RUN_ID", "RETRY_LINEAGE_CONTRACT_VERSION",
    )
    legacy_keys = ("RETRY_LINEAGE_LEGACY_ENTRYPOINT", "RETRY_LINEAGE_LEGACY_EXECUTION_ORIGIN")
    protected_fields_present = any(os.environ.get(k) is not None for k in protected_keys)
    legacy_fields_present = any(os.environ.get(k) is not None for k in legacy_keys)

    raw_mode = os.environ.get("RETRY_LINEAGE_EXECUTION_MODE")
    if raw_mode is None:
        if protected_fields_present or legacy_fields_present:
            # mode discriminatorは欠落しているが、protected/legacy関連fieldの
            # いずれか1つでも存在する——partial/orphan envelope。「discriminator
            # 欠落＝legacyとして扱ってよい」という汎用推測は行わず、
            # self-origination経路へも迂回しない。
            raise SideEffectExecutionModeContractError(
                ExecutionModeFailureReasonCode.CONTRADICTORY_SERIALIZED_FORM,
            )
        # execution-envelope関連変数が完全に1つも存在しない場合のみ、main.py
        # 自身がtrusted composition rootとしてStage 1/Stage 2両方をその場で
        # 完成させる（2.3節規則2）。これはclosed set上のただ1つの具体的な
        # entrypointについてのみ成立する規則であり、context欠落全般に対する
        # 汎用fallbackではない——他の呼び出し箇所（呼び出し箇所A/B/C自体、
        # 2.2・2.4節）ではmissing contextは引き続きfail-closedのままである。
        provenance = build_legacy_direct_provenance(LegacyEntrypoint.RUN_MAIN_DIRECT)
        return complete_legacy_execution_context(provenance, LegacyExecutionOrigin.MAIN_DIRECT)

    if raw_mode == "retry_lineage_protected":
        if legacy_fields_present:
            raise SideEffectExecutionModeContractError(
                ExecutionModeFailureReasonCode.CONTRADICTORY_SERIALIZED_FORM,
            )  # protected tagなのにlegacy fieldのいずれかも設定されている（矛盾）
        root_run_id = os.environ.get("RETRY_LINEAGE_ROOT_RUN_ID")
        if not _is_well_formed_root_run_id(root_run_id):
            raise SideEffectExecutionModeContractError(
                ExecutionModeFailureReasonCode.MISSING_LINEAGE_CONTEXT,
            )  # 2.2節#3、識別不能。external I/O = 0
        attempt_ordinal, member_run_id, contract_version = _parse_and_validate_remaining_context(
            os.environ.get("RETRY_LINEAGE_ATTEMPT_ORDINAL"),
            os.environ.get("RETRY_LINEAGE_MEMBER_RUN_ID"),
            os.environ.get("RETRY_LINEAGE_CONTRACT_VERSION"),
        )  # 欠落/malformedなら2.2節#2（CONTEXT_MISMATCH/CONTRACT_VERSION_MISMATCH）を送出。
           # root_run_idは識別済みのため、ここでの失敗はhard failureではなく12章の
           # CONTRACT_VIOLATION経路（reconciliation側で当該lineageがHRRへ導かれる）へ
           # 委ねる形とする。
        return build_protected_execution_context(
            root_run_id=root_run_id, attempt_ordinal=attempt_ordinal,
            member_run_id=member_run_id, side_effect_contract_version=contract_version,
        )  # protected factory（2.1a節）のみが呼べる

    if raw_mode == "legacy_direct":
        if protected_fields_present:
            raise SideEffectExecutionModeContractError(
                ExecutionModeFailureReasonCode.CONTRADICTORY_SERIALIZED_FORM,
            )  # legacy tagなのにprotected fieldが設定されている（矛盾）
        raw_entrypoint = os.environ.get("RETRY_LINEAGE_LEGACY_ENTRYPOINT")
        try:
            entrypoint = LegacyEntrypoint(raw_entrypoint)
        except ValueError:
            raise SideEffectExecutionModeContractError(
                ExecutionModeFailureReasonCode.UNKNOWN_LEGACY_ENTRYPOINT,
            )
        raw_origin = os.environ.get("RETRY_LINEAGE_LEGACY_EXECUTION_ORIGIN")
        try:
            origin = LegacyExecutionOrigin(raw_origin)
        except ValueError:
            raise SideEffectExecutionModeContractError(
                ExecutionModeFailureReasonCode.UNKNOWN_LEGACY_EXECUTION_ORIGIN,
            )
        # main.py subprocess境界はStage 1（起動元）・Stage 2（実行origin）の両方が
        # 既に確定した状態でしか呼ばれない（14.2節、Composition Rootが常に完成済み
        # LegacyDirectExecutionContextをシリアライズする）ため、Stage 2完成factory
        # を呼ぶのではなく、両フィールドから直接構築する（本関数は
        # _serialize_execution_context()の逆変換であり、fan-out境界そのものではない）。
        return LegacyDirectExecutionContext(
            legacy_entrypoint=entrypoint, legacy_execution_origin=origin,
        )

    raise SideEffectExecutionModeContractError(ExecutionModeFailureReasonCode.UNKNOWN_EXECUTION_MODE)
```

main.pyはこの`side_effect_execution_context`を**1回だけ**解決する（値の再構築・再推測はしない、6章のformal invariant）。呼び出し箇所A（`WordPressOutput`、15.7節）へはこの同一インスタンスをそのまま構築時に渡す。呼び出し箇所B（`ArticleFeaturedMediaRuntime`、15.4節）へは、**Foundationのconstructor/apply()へ直接渡すことはない**——6.32 integration wiring層（`MediaUploadWriteAheadAdapters`・`build_protected_featured_media_runtime()`、22.3.2節）が同一インスタンスを受け取り、記事ごとのidentity・member_run_id・write-ahead decoratorへ反映する（15.4節「main.py側の配線との整合」）。

**運用上の帰結（14.5節）**：execution-envelope関連変数（mode tag・protected 4変数・legacy 2変数のいずれも）を一切設定しない生の手動実行（`python main.py`をラッパースクリプトなしで直接起動する等）は、main.py自身がtrusted direct composition rootとして`RUN_MAIN_DIRECT`/`MAIN_DIRECT`のprovenanceを自己発生させ、既存のA（NEWS WordPress draft）・B（MEDIA_UPLOAD）へ通常どおり到達する（2.3節「`main.py`のStage 1/Stage 2」規則2、14.3節`_parse_execution_context_from_env()`が権威）——運用者が事前に環境変数を設定することはこの経路の前提条件ではない。環境変数を明示的に設定してmain.pyを起動する経路（NEWS step subprocess・`run_workflow_engine.py`のRetry Lineage外呼び出し）も引き続き利用できるが、これはbare直接起動を機能させるための必須条件ではなくなった。mode tagが設定されているが内容が矛盾／不明（`CONTRADICTORY_SERIALIZED_FORM`・`UNKNOWN_LEGACY_ENTRYPOINT`等）な場合、および**mode tagが欠落しているにもかかわらずprotected/legacy関連fieldのいずれか1つでも設定されている場合（partial/orphan envelope）**は、self-origination経路へ迂回せずfail-closedする——後者はmode tag欠落を「legacyとして扱ってよい」根拠にしない、という6章formal invariantの直接的な帰結である。

### 14.4 PUBLISH stepとの非対称性

PUBLISH stepはsubprocess境界を越えないため、`SideEffectExecutionContext`はenvironment variables経由ではなく、`AgentContext.side_effect_execution_context`（2.6節Propagation Contract）から`PublishPipelineRunner.run()`→`AiPublishService.run()`→`_post()`まで、通常の関数引数として直接伝播する（15.6節）。`effect_site=PUBLISH_STEP`も呼び出し箇所で決め打ちでよい。PUBLISH stepもNEWS stepも共に`WorkflowEngineExecutor`が構築する同一の`AgentContext`型を経由するため、両stepのcontext取得経路は構造的に対称（同一channel）である——NEWS側のみsubprocess境界を挟むためenvironment variablesへの変換（14.2〜14.3節）が追加で必要になる、という一点のみが非対称。

### 14.5 main.py CLI/起動契約への影響範囲

本章（14章）が定めるsubprocess境界の契約は、main.pyのCLI/起動契約に触れる。関連要件は§31 Implementation Requirementsに一覧化されている（本節では重複定義しない）。

### 14.6 NEWS Subprocess境界 — Contract-Error Exit Protocol

`SideEffectExecutionModeContractError`はPython例外objectであり、`NewsPipelineRunner.run()`が起動する`main.py`のsubprocess境界（`subprocess.run()`、14.2〜14.3節）を越えて直接伝播しない。境界の両側（child／parent）は、以下の専用protocolで初めて連携する——例外objectそのものをsubprocess経由で伝達することは要求しない。

**Child（`main.py`）側**：`main.py`のtop-level起動部（`if __name__ == "__main__":`）は、`main()`本体の呼び出しを`SideEffectExecutionModeContractError`専用のcatchで包む。この例外のみを対象とし、他の例外・`main()`の通常の戻り値（0/1/20/21、5節）は無変更のまま扱う：

```python
if __name__ == "__main__":
    try:
        sys.exit(main())
    except SideEffectExecutionModeContractError:
        sys.exit(SIDE_EFFECT_CONTRACT_VIOLATION_EXIT_CODE)  # 2.5節、値=3
```

このcatchが存在しない場合、`SideEffectExecutionModeContractError`は素通しの未捕捉例外としてPythonのdefault挙動（traceback表示・exit code 1）に落ち、既存の`NEWS_OUTCOME_GENERIC_FAILURE_EXIT_1`（通常のバグ・実行時エラー）と値のレベルで区別不能になる——本節はこの区別不能を専用exit codeにより解消する。例外のメッセージ本文・reason_code値はexit codeという単一の整数のみに縮退し、stdout/stderrへ出力しない（2.5節のsecret-safe規律をsubprocess境界でも維持する）。

**Parent（`NewsPipelineRunner.run()`）側**：`subprocess.run()`完了後、`completed.returncode`を`_news_outcome_token()`（既存の`_EXIT_CODE_TOKENS`分岐、0以外を一律`PipelineResult(success=False, ...)`へ変換する既存ロジック）へ渡す**前**に、`SIDE_EFFECT_CONTRACT_VIOLATION_EXIT_CODE`との一致を判定する：

```python
elapsed = time.time() - start
if completed.returncode == SIDE_EFFECT_CONTRACT_VIOLATION_EXIT_CODE:
    # 既存のログ保存は維持する（診断用途、2.5節のsecret-safe規律の範囲内）。
    self._save_log(run_timestamp, "stdout", _normalize_subprocess_output(completed.stdout))
    self._save_log(run_timestamp, "stderr", _normalize_subprocess_output(completed.stderr))
    raise SideEffectExecutionModeContractError(
        ExecutionModeFailureReasonCode.SUBPROCESS_CONTRACT_VIOLATION,
    )  # PipelineResultへ変換せず素通しする。childの具体的なreason codeは
       # 境界を越えて伝達されないため、親側は単一の集約reason codeで再構築する。

stdout_text = _normalize_subprocess_output(completed.stdout)
# ...既存のsuccess/token判定ロジック（無変更）...
```

**上流への伝播**：`NewsPipelineRunner.run()`が送出したこの例外は、`NewsAgent.act()`（`src/ai/news_agent.py`、`self._runner.run(...)`をtry/exceptで包まない）を無変換のまま通過し、`AgentExecutor.execute()`（22.3節で確立済みの`except SideEffectExecutionModeContractError: raise`carve-out、Agent種別を問わず共通の実行層）・`AgentManager.run()`（try/exceptを持たない）を経て、Stage-1 callerまで未変換の例外として到達する。`WorkflowEngineExecutor`が構築する`AgentContext`経由でNEWS stepへ到達する経路（`run_workflow_engine.py`直接実行・`RetryExecutor`経由のRetry Lineage実行を含む、いずれも同一の`WorkflowEngineExecutor`→`AgentExecutor.execute()`→`NewsAgent.act()`chainを共有）でも同一の伝播が成立する——`NewsPipelineRunner`の呼び出し元がAgentManager経由かWorkflowEngineManager経由かによらず、chain構造が単一であるため。

**条件（本節の適用範囲）**：`SIDE_EFFECT_CONTRACT_VIOLATION_EXIT_CODE=3`は、main.py Outcome Contract（`production_canonical_run_outcome_contract_foundation.md`5節）が定める既存値（0/1/2/20/21、当該文書5節が定める「`2`はargparse usage errorと衝突するため使用しない」を含む）のいずれとも衝突しない。値は`side_effect_execution_mode.py`（2.5節）の単一定数として定義し、child・parent双方がこれをimportする——値のハードコード重複は行わない。

---

## 15. 呼び出し元の統合

### 15.1 `RetryExecutor.execute()`

```python
if not request.dry_run:
    newly_confirmed = compute_newly_confirmed(engine_result)
    step_categories = [classify_step_outcome(s) for s in engine_result.steps]
    operations = _expected_operation_contexts(claim.steps_to_execute, engine_result.steps)
    safety_report = self._side_effect_classifier.classify(
        lineage.root_run_id, claim.attempt_no, engine_result.run_id, operations,
    )
    disposition = resolve_final_disposition(step_categories, safety_report)
    mark_result = self._lineage.mark_terminal(
        lineage.root_run_id, disposition, engine_result.run_id, newly_confirmed,
    )
```

### 15.2 `_reconcile_all_locked()`

12.2節と同型の原則を用いる。`_expected_operation_contexts_for_history()`が15.3節の写像表を使う。member_run_idの供給元は10.2節参照。

### 15.3 step→(operation_kind, effect_site)対応表

```python
_STEP_TO_PROTECTED_OPERATIONS: dict[WorkflowEngineStep, list[tuple[ProtectedSideEffectKind, SideEffectSite]]] = {
    WorkflowEngineStep.NEWS: [
        (ProtectedSideEffectKind.WORDPRESS_DRAFT_CREATION, SideEffectSite.NEWS_STEP),
        (ProtectedSideEffectKind.MEDIA_UPLOAD, SideEffectSite.NEWS_STEP),
    ],
    WorkflowEngineStep.REVIEW: [],
    WorkflowEngineStep.PUBLISH: [
        (ProtectedSideEffectKind.WORDPRESS_DRAFT_CREATION, SideEffectSite.PUBLISH_STEP),
    ],
}
```

`effect_site`は常にこの表からのみ導出し、呼び出しコードの各所で独自に組み立てない（8章、§8はsubsection構成を持たない単一章）。

### 15.4 呼び出し箇所B（NEWS側media upload）の統合

**真の外部I/O境界**：`self._root.orchestrator.apply(article, prompt, filename)`は`ArticleFeaturedMediaOrchestrator.apply()`（`src/article_featured_media_orchestration/article_featured_media_orchestrator.py:58-74`）を呼ぶ。この関数は**固定順序で2種類の外部I/Oを行う**：

```python
# ArticleFeaturedMediaOrchestrator.apply()（既存、無変更）の内部（58-74行目）
generated_image = self._image_generator.generate(prompt)      # 外部I/O其の1：AI画像生成
                                                                 # （OpenAI等、6.32のMEDIA_UPLOAD
                                                                 #  protected operationではない）
media_result = self._media_uploader.upload(generated_image, filename)  # 外部I/O其の2：
                                                                 # WordPress media upload
                                                                 # ＝MEDIA_UPLOAD protected
                                                                 # operationの本体、write-ahead
                                                                 # 境界を置くべき唯一の呼び出し
return bind_featured_media(article, media_result)               # I/Oなし（純粋なbinding）
```

したがって、write-ahead irreversible boundary（`record_attempted()`のIO_ARMED ACK）は、`self._media_uploader.upload(...)`の直前に置く——`self._root.orchestrator.apply(article, prompt, filename)`という**呼び出し全体の前**に置く設計は採用しない。呼び出し全体の前に置いた場合、画像生成（`generate()`）だけが失敗し`media_uploader.upload()`に一度も到達しないCONTINUE fallbackの経路でも、durable stateは`IO_ARMED`（実際には到達していない外部I/Oを「開始可能」と記録した状態）のまま残り、`resolve_final_disposition()`（13章）が`IN_PROGRESS_OR_UNKNOWN`→`HUMAN_REVIEW_REQUIRED`と誤判定する。CONTINUE fallbackは`decide_image_generation_fallback()`が扱う**日常的な、想定内の回復可能失敗**（レート制限・コンテンツポリシー等）であり、これが6.32導入後にHRRを恒常的に誤発火させることは、既存の正常な運用を破壊するため採用しない。

**protected flowの契約（現行、確定済み）**：

```
main.py::_apply_featured_media_step()（唯一のexact caller、22.3.2節）
  → applicability resolution（is_available()、Gate ON/OFF判定、無変更）
  → operation-specific durable pre-I/O evidence（record_prepared()、9.9.4.7節、確定済み）
  → 既存のimage generation/fallback logic（generate() → 例外時はdecide_image_generation_fallback()、無変更・省略しない）
  → uploadを実際に行う場合のみ：
      ATTEMPTED durable ACK → IO_ARMED durable ACK（write-ahead-aware decorator経由、確定済み——22.3.2節。decoratorはrecord_confirmed()を呼ばない）
      → external upload（media_uploader.upload()）
      → runtime.apply()がArticleFeaturedMediaRuntimeResultを返す
      → CONFIRMED_SUCCESS（15.5節）：**呼び出し元（main.py::_apply_featured_media_step()）が単独のownerとして`record_confirmed()`を呼ぶ**——`runtime_result.status is ArticleFeaturedMediaRuntimeStatus.APPLIED`（actual upload path到達・成功のauthoritative evidence、既存enum、新規flag不要）かつ`_extract_confirmed_media_id(runtime_result.article)`が非Noneの場合のみ（15.5.1節）
```

以下の2点は、いずれも確定済みの契約である：

- **pre-upload fallback（画像生成失敗でuploadへ未到達）のdurable evidence**：`MediaUploadSafetyCoordinator`の4番目の公開メソッド`record_prepared()`（9.9.4.7節）が、既存state（`PREPARED`）・既存classification（`SAFE_TO_CONTINUE`）を一切変更せずにこれを表現する。
- **write-ahead境界を`media_uploader.upload()`直前に正確に配置する実装方法**：`GeneratedImageUploadCapability`Protocol（既存のDependency Inversion拡張点）を実装するwrite-ahead-aware decorator（6.32新規）を6.32 integration層（Orchestrator/CompositionRoot自体ではなく、その外側のwiring層）で構築し、注入する。`ArticleFeaturedMediaOrchestrator`・`ArticleFeaturedMediaCompositionRoot`という既存のConsumer-less Foundationは無変更のまま維持する。exact file/symbolは22.3.2節が一意に定める。

#### 15.4.1 Option (a) 確定契約

**authoritative protected flow**：

```
main.py::_apply_featured_media_step()（22.3.2節、exact caller・record_confirmed()の唯一のowner）
  → applicability decision（is_available()相当、Gate ON/OFF判定、無変更）
  → applicable の場合：
       record_prepared() durable ACK（9.9.4.7節、PREPARED、external I/O禁止）
       → runtime.apply(article) を呼ぶ（既存 ArticleFeaturedMediaRuntime.apply()、無変更）
           - 既存の画像生成ロジック（generate()）は無変更
           - 既存のCONTINUE/PROPAGATE fallback（decide_image_generation_fallback()）は無変更
           - 実際に upload が必要な場合のみ、runtime.apply()の内部で：
                decorated MediaUploader.upload()（6.32 integration層のdecorator経由）
                  → record_attempted()（PREPARED→ATTEMPTED→IO_ARMED、既存9.9.3節Ordering Contract）
                  → IO_ARMED durable ACK
                  → 実際の media_uploader.upload()（真の外部I/O）
                  → upload()から呼び出し元（orchestrator）へreturn
                ※ decoratorの責務はここまで。record_confirmed()はdecoratorのnested scope内では一切呼ばれない
       ← runtime.apply(article) がArticleFeaturedMediaRuntimeResultをreturn（呼び出しchainを抜け、main.pyの制御フローへ戻る）
       → applied_article = runtime_result.article（明示的unwrap）
       → runtime_result.status is ArticleFeaturedMediaRuntimeStatus.APPLIED であることを要求（15.5.1節条件0）
       → _extract_confirmed_media_id(applied_article) でvalid media_idを確認（15.5.1節条件1〜4）
       → 上記すべてを満たす場合のみ、main.py::_apply_featured_media_step()自身が record_confirmed()（15.5節）を呼ぶ
  → applicable でない場合（Gate OFF）：
       record_not_applicable()（既存、9.9節）。PREPAREDは作らない。
```

pre-upload fallback（画像生成失敗でCONTINUE/PROPAGATE、uploadへ未到達）の経路では、decorated uploaderの`upload()`自体が一度も呼ばれない——`PREPARED`のみがoperation-specific durable non-I/O evidenceとして残り、`SAFE_TO_CONTINUE`として分類される（9.9.7節）。

**integration層への実装配置（6.32 wiring層、`ArticleFeaturedMediaOrchestrator`/`ArticleFeaturedMediaCompositionRoot`/`ArticleFeaturedMediaRuntime`自体は変更しない。exact file/symbolは22.3.2節を参照）**：write-ahead-aware decorator（`GeneratedImageUploadCapability`Protocolの実装、`WriteAheadAwareMediaUploadCapability`、新設`src/side_effect_safety/media_upload_write_ahead_capability.py`）は、`upload(image, filename)`の直前で`record_attempted()`（IO_ARMED ACK確認）を行い、その後にのみ実際の（decorateされる前の）`media_uploader.upload(image, filename)`を呼ぶ——`record_confirmed()`はdecorator自身は呼ばない。**`record_confirmed()`は、`ArticleFeaturedMediaRuntime.apply(article)`の唯一の呼び出し元・owner（`main.py::_apply_featured_media_step()`、22.3.2節で特定するexact symbol）が、`runtime_result.status is ArticleFeaturedMediaRuntimeStatus.APPLIED`を確認した上で、`.apply()`の戻り値（`ArticleFeaturedMediaRuntimeResult`）から明示的にunwrapした`runtime_result.article`（`ArticleData`）へ15.5.1節の`_extract_confirmed_media_id()`を適用し、その結果が非`None`の場合のみ呼ぶ**（`_extract_confirmed_media_id()`はwrapperではなく`ArticleData`にのみ適用可能であり、この区別を誤ると成功時ですら`record_confirmed()`が一度も呼ばれずfalse HRRに陥る）。15.5.1節の既存契約（呼び出し元が`applied_article`から抽出したmedia_idを使う）をそのまま維持し、decorator側の役割はIO_ARMED ACK（record_attempted()）のみに限定する。identity（8章、`operation_instance_key=article.slug`、15.7節・15.6節と同一の既存規律）は、記事ごとにこの呼び出し元が構築し、decoratorへ束縛する——`upload(image, filename)`というProtocol署名は固定されており、identityを呼び出しごとの引数として渡す経路を持たないため、decorator（および内部の`ArticleFeaturedMediaOrchestrator`インスタンス）は記事1件ごとに新規構築する（22.3.2節）。decoratorの構築・注入は6.32 integration層（main.py起動時のwiring相当）が行い、`ArticleFeaturedMediaCompositionRoot.from_env()`を経由せずOrchestratorへ注入する——Foundation自体は6.32 module・Retry Lineage・6.32 execution contextのいずれもimportしない（Consumer-less Foundation契約は無変更のまま維持）。

**Legacy（`LegacyDirectExecutionContext`）時の扱い（既存設計のまま、確定事項）**：decorator/write-ahead呼び出しを一切適用しない。既存（6.31以前）のfallback semantics・media state semanticsを完全に維持する（15.4節「legacy direct執行時の扱い」と同一）。

**注入点**：6.32 integration層は、既存の`GeneratedImageUploadCapability`Protocol（`article_featured_media_orchestrator.py:21,44`・`article_featured_media_composition_root.py:91`、Dependency Inversion拡張点として実装済み）をそのままdecorator注入点として利用する。この既存seamで注入要件（decoratorをOrchestratorへ渡す経路）を満たすため、**Foundationへ新しい6.32-specific または generic dependency-injection APIを追加しない**。Consumer-less Foundationのzero-diff dependency境界（default construction/behaviorが既存`from_env()`経路と完全に同一であること）は、新規APIを追加しないことでそのまま維持される。6.32専用のCompositionRoot経路（30章#42、不採用）も引き続き作らない。

**post-IO ambiguityの扱い（既存設計のまま、確定事項）**：`media_uploader.upload()`実行中・実行後（IO_ARMED ACK確認後）に発生する例外・失敗は、既存の`decide_image_generation_fallback()`によるCONTINUE/PROPAGATE判断が存在しても、side-effect safety evidenceとしては`IN_PROGRESS_OR_UNKNOWN`のままとする——`resolve_final_disposition()`（13章）は引き続きHRRを維持する（9.9.1節の意図的なfail-closed crash windowと同型）。既存のfallback判断（CONTINUE/PROPAGATE）は`ArticleFeaturedMediaRuntimeResult`の戻り値（呼び出し元・observabilityへの報告）にのみ影響し、6.32のsafety classificationには一切影響しない——9.9.9節「cleanup_diagnosticsはdisposition判定に影響しない」と同型の分離原則をここでも適用する。

**legacy direct執行時の扱い（既存設計のまま、確定事項）**：`isinstance(context, LegacyDirectExecutionContext)`の場合、write-ahead呼び出しを一切行わない。`decide_image_generation_fallback()`によるCONTINUE/PROPAGATEを含む既存（6.31以前）のfallback semanticsは完全に無変更のまま維持する。

**main.py側の配線との整合**：14.3節・15.7節が確立した「main.pyは`side_effect_execution_context`を1回だけ解決する」という契約は、呼び出し箇所A（`WordPressOutput`）については無変更のまま成立する——`WordPressOutput.__init__()`は`side_effect_execution_context`を直接受け取る（15.7節、Foundationではないため直接変更可能）。**呼び出し箇所B（`ArticleFeaturedMediaRuntime`）については、main.pyが解決した`side_effect_execution_context`を`ArticleFeaturedMediaRuntime`のconstructor（`__init__(self, root)`）へ直接渡すことはない**——`article_featured_media_runtime.py:106-107`に`side_effect_execution_context`引数は存在せず、Consumer-less Foundationとして無変更のまま維持する（22.3.2節）。6.32のcontextは、main.pyが6.32 integration wiring層（`MediaUploadWriteAheadAdapters`・`build_protected_featured_media_runtime()`、22.3.2節）へ渡し、そこで記事ごとのidentity・member_run_id・decoratorへ反映される——`ArticleFeaturedMediaRuntime`自体・その`root`（`ArticleFeaturedMediaCompositionRoot`）のconstructor shapeへは一切伝播しない。

### 15.5 Confirmation Invariant

#### 15.5.1 `record_confirmed()`を呼べる条件

以下を**すべて**満たす場合にのみ、`record_confirmed(identity, context.member_run_id, media_id)`（15.4節、`identity`は`validate_side_effect_execution_context()`後の`context`から導出したもの）を呼ぶ：

0. `runtime_result.status is ArticleFeaturedMediaRuntimeStatus.APPLIED`である——「今回の呼び出しでactual uploadが実際に発生し成功した」ことのauthoritative evidenceであり、`featured_media_id > 0`という値のみをこの証拠として用いない（22.3.2節「actual-upload evidenceの根拠」参照）。この条件を満たさない場合（`DISABLED`・`CONTINUED_WITHOUT_FEATURED_MEDIA`）は、以下1〜4の評価自体を行わず`record_confirmed()`を呼ばない。
1. `applied_article`（＝`runtime_result.article`、明示的にunwrapした値）が期待される結果構造（`ArticleData`のinstance）である。
2. `applied_article.featured_media_id`が存在する。
3. `featured_media_id`の型が`int`である（`bool`は`int`のサブクラスだが明示的に除外する。`ArticleMediaUploadStateManager.record_upload_succeeded()`の既存invariant検証と同じ規律）。
4. `featured_media_id > 0`（`0`は既存契約上「アイキャッチなし」を意味する。`docs/architecture.md`のImageResolver設計方針・v1.6 `resolve_media_id()`節を参照）。

1〜4は呼び出し元が`_extract_confirmed_media_id()`として事前にチェックする（純関数、副作用なし）。ここでいう「呼び出し元」は`ArticleFeaturedMediaRuntime.apply()`自身ではない——同メソッドはConsumer-less Foundationの一部であり無変更のまま維持されるため、`record_confirmed()`を呼ぶ責務を持ちえない。実際の唯一の呼び出し元・owner は`main.py::_apply_featured_media_step()`（22.3.2節で特定するexact symbol）である。`runtime.apply(article)`が返すのは`ArticleData`ではなく`ArticleFeaturedMediaRuntimeResult`（`article`・`status`・`category`・`observation`フィールドを持つwrapper、`article_featured_media_runtime.py`）であるため、**`_extract_confirmed_media_id()`はこのwrapperではなく`runtime_result.article`（明示的にunwrapした`ArticleData`）へ適用する**——`_extract_confirmed_media_id()`自体は`ArticleData`専用のhelperのまま維持し、helper内で`ArticleFeaturedMediaRuntimeResult`をunwrapする変更は行わない（呼び出し元がunwrapを担う）：

```python
def _extract_confirmed_media_id(applied_article: object) -> int | None:
    """1〜4のいずれかを満たさない場合はNoneを返す。呼び出し元はNoneの場合、
    record_confirmed()を呼んではならない（fail-closed）。"""
    if not isinstance(applied_article, ArticleData):
        return None
    media_id = getattr(applied_article, "featured_media_id", None)
    if type(media_id) is not int:  # bool除外
        return None
    if media_id <= 0:
        return None
    return media_id
```

5. **（Coordinator内部で検証、15.4節の呼び出しが行われた後）** identity整合：`existing.upload_state is not None`（正しいATTEMPTEDレコードの存在、9.9.2節）。
6. **（Coordinator内部で検証）** member_run_id整合：`MediaUploadAttemptContextStore`に記録された値との一致（9.9.2・9.9.4節）。

0〜4は呼び出し元の事前条件、5〜6はCoordinatorが`record_confirmed()`実行時に検証する事後条件であり、いずれか一方が欠けても安全性は成立しない（両方を本節で明文化する）。

#### 15.5.2 Fail-Closedの帰結

以下のいずれのケースでも、**`record_confirmed()`を呼ばない、または呼んでも拒否される**。いずれの場合も**`NOT_APPLICABLE`への再分類は行わない**——このoperationは既に`record_attempted()`によって`ATTEMPTED`へ進んでいるため、7章の状態機械（closed set 3値の一方向遷移）上、`NOT_APPLICABLE`へ遷移するAPI自体が存在しない。「安全な成功を証明できない」状態としてfail-closedし、`ATTEMPTED`のまま維持されたレコードが、`MEDIA_UPLOAD`の場合は9.9.7節Cross-Store Combination Table（`IO_ARMED` + `ATTEMPTED` → `IN_PROGRESS_OR_UNKNOWN`）、`WORDPRESS_DRAFT_CREATION`の場合は12.2節Decision Table（`ATTEMPTED` → `IN_PROGRESS_OR_UNKNOWN`）を経て最終的に`HUMAN_REVIEW_REQUIRED`へ到達する。MEDIA_UPLOADのnon-empty state判定の権威は9.9.7節に一本化する。

| ケース | `record_confirmed()`を呼ぶか | 検証段階 |
|---|---|---|
| `featured_media_id == 0` | 呼ばない（`_extract_confirmed_media_id()`が`None`を返す） | 15.5.1節 #4 |
| `featured_media_id is None` | 呼ばない | 15.5.1節 #2 |
| `featured_media_id`が非int（`bool`含む）・`applied_article`の型不正 | 呼ばない | 15.5.1節 #1・#3 |
| identity不一致（該当identityにATTEMPTEDレコードが存在しない） | 呼ぶが`MediaUploadSafetyTransitionError`で拒否 | 15.5.1節 #5 |
| member_run_id不一致 | 呼ぶが`MediaUploadSafetyTransitionError`で拒否 | 15.5.1節 #6 |
| `record_confirmed()`のdurable ACK失敗（`article_media_upload_state`側のI/O失敗） | 呼ぶが例外送出、状態は`ATTEMPTED`のまま | — |

いずれのケースも、最終的な安全性は9.9.7節Cross-Store Combination Table（`MEDIA_UPLOAD`のnon-empty state authority）が担保するため、15.5節はこの表に新しい分岐を追加するものではなく、**「`record_confirmed()`を正しく呼ばない（呼べない）ことで、既存のfail-closed経路へ正しく合流させる」ための呼び出し規律**である。

### 15.6 呼び出し箇所C（PUBLISH側）の統合

`src/ai/ai_publish_service.py::AiPublishService._post()`が呼び出し箇所C（`WordPressDraftClient.post_draft()`、1.2節）への唯一のprocess内呼び出し元である。`SideEffectExecutionContext`（2.1a節）は、コンストラクタ時のprovider callableではなく、`run()`/`_post()`呼び出しごとの**明示的な引数**として、2.6節のPropagation Contractに従い`PublishPipelineRunner.run(params, side_effect_execution_context)`→`AiPublishService.run(article_id, side_effect_execution_context)`→`_post()`と伝播する。検証は自前実装せず、**2.1b節の共通validatorを呼ぶ**：

```python
def _post(
    self, review: RewriteReviewResult, rewrite: RewriteResult,
    side_effect_execution_context: "SideEffectExecutionContext",  # 2.1a節、必須引数（デフォルトなし）
) -> AiPublishResult:
    context = validate_side_effect_execution_context(side_effect_execution_context)
    # 2.1b節の共通validatorを呼ぶ。mode欠落/unknown/originのclosed set外は
    # この1行で一括検出され、post_draft()より前でfail-closedする（呼び出し箇所
    # A・Bと同一の検証ロジックを再利用する、個別実装の重複を避ける）。isinstance
    # 分岐のみを使い、フィールド値からmodeを推測しない（2.1節）。

    identity = None
    if isinstance(context, RetryLineageProtectedExecutionContext):
        identity = SideEffectOperationIdentity(
            root_run_id=context.root_run_id,
            attempt_ordinal=context.attempt_ordinal,
            operation_kind=ProtectedSideEffectKind.WORDPRESS_DRAFT_CREATION,
            effect_site=SideEffectSite.PUBLISH_STEP,
            operation_instance_key=review.article_id,
        )
        self._draft_state_manager.record_attempted(identity, context.member_run_id)
        # ACK確認後にのみ実I/Oへ進む（9.9.3節と同型のOrdering Contract）

    # isinstance(context, LegacyDirectExecutionContext)の場合、以降write-ahead
    # 呼び出しを一切行わず、既存（6.31以前）のロジックのまま進む——この型は
    # そもそもroot_run_id等のfieldを持たないため、混同の余地がない（2.1節）。

    response = self._client.post_draft(title=review.title, content=rewrite.rewrite_draft, slug=new_slug)

    if isinstance(context, RetryLineageProtectedExecutionContext):
        self._draft_state_manager.record_confirmed(identity, context.member_run_id, response["post_id"])

    ...  # 既存のAiPublishResult生成ロジック（無変更）
```

**`run()`シグネチャの拡張**：`AiPublishService.run(self, article_id=None, *, side_effect_execution_context)`は`side_effect_execution_context`を必須引数（デフォルトなし）として受け取り、`_process()`経由で`_post()`へそのまま渡す。呼び出し元は必ず明示的に値を渡さなければならない——省略時の暗黙のデフォルト値は存在しない（2.1a節）。

Retry Lineage context外（`LEGACY_DIRECT`）の呼び出しに対する`filter_unpublished()`ベースの既存idempotencyは無変更のまま維持する（2.7節Accepted Residual Risk）。

### 15.7 呼び出し箇所A（NEWS側WordPress draft）の統合

**呼び出し箇所Aの構造**：呼び出し箇所A（1.2節、`WordPressOutput.save()`、NEWS stepでのWordPress下書き投稿）は、呼び出し箇所B（`ArticleFeaturedMediaRuntime.apply()`経由のmedia upload）・呼び出し箇所C（`AiPublishService._post()`、15.6節）のいずれとも独立した、**別個の`WordPressOutput.save()`呼び出し**であり、`OutputManager.save_all(article)`（`src/outputs/manager.py`）が`BaseOutput`を実装する各出力先へ**汎用的に**（WordPress固有の知識を持たずに）`save(article)`をポリモーフィックに呼び出す構造である。

**設計方針**：呼び出し箇所B・Cと同じく、**既存の§9 `WordPressDraftStateStore`/`WordPressDraftStateManager`をそのまま再利用する**（新しい並行state machineは作らない）。`WORDPRESS_DRAFT_CREATION`はNEWS_STEP・PUBLISH_STEPの両方で発生しうるが、8章のidentity（`effect_site`を含む5要素）により、両者は構造的に別のSide-Effect Operation Identityとして扱われ、衝突しない（15.3節の`_STEP_TO_PROTECTED_OPERATIONS`表は元々この2つを独立したentryとして記載しており、本節はその表を初めて具体的な呼び出しコードへ落とし込むものである）。

`OutputManager.save_all()`はWordPress固有の知識を持たない汎用dispatcherであり、その`save(article)`呼び出しに`side_effect_execution_context`を追加引数として通す変更は行わない（`OutputManager`はいかなるstep/executionの概念も持たない既存の薄いdispatcherのまま維持する）。`SideEffectExecutionContext`は、main.py起動時に一度だけ解決され（14.3節）、`WordPressOutput`インスタンスの**構築時**に注入する。この構築はmain.pyの実行1回につき1回だけ行われ、main.py自体が2.6節のPropagation Contractにより毎回明示的なcontextを受け取って起動される（main.pyというprocess自体がrun-scopedな単位であるため、`WorkflowEngineManager`のような「1回構築・複数回`.run()`」という再利用構造を持たない。したがってmain.py起動時のconstructor injectionは、`WorkflowEngineManager`/`AgentExecutor`のように1回構築・複数回呼び出しされるcomponentへcall-time値を構築時注入してしまう誤り（22.1f節）には該当しない）：

```python
class WordPressOutput(BaseOutput):
    def __init__(
        self, site_url: str, username: str, app_password: str,
        side_effect_execution_context: "SideEffectExecutionContext",  # 2.1a節、必須引数（デフォルトなし）
        draft_state_manager: "WordPressDraftStateManager | None" = None,  # RETRY_LINEAGE_PROTECTED時のみ必須
    ):
        self.site_url = site_url.rstrip("/")
        self.username = username
        self.app_password = app_password
        self._context = side_effect_execution_context
        self._draft_state_manager = draft_state_manager

    def save(self, article: ArticleData) -> SaveResult:
        context = validate_side_effect_execution_context(self._context)
        # 2.1b節の共通validatorを呼ぶ。main.py起動時に一度だけ解決された値
        # （self._context）をそのまま渡し、save()呼び出しごとの再取得・再推測は
        # 行わない。mode欠落/unknown/矛盾（LEGACY_DIRECTでの4フィールド部分検証漏れ
        # を含む）はいずれもこの1行で一括検出され、requests.post()より前で
        # fail-closedする。

        identity = None
        if isinstance(context, RetryLineageProtectedExecutionContext):
            identity = SideEffectOperationIdentity(
                root_run_id=context.root_run_id,
                attempt_ordinal=context.attempt_ordinal,
                operation_kind=ProtectedSideEffectKind.WORDPRESS_DRAFT_CREATION,
                effect_site=SideEffectSite.NEWS_STEP,  # 15.6節（PUBLISH_STEP）とは
                                                         # 構造的に別identity（8章）
                operation_instance_key=article.slug,    # 既存のarticle識別子をそのまま
                                                         # 再利用する（本メソッド内で
                                                         # WordPress payload構築にも使う
                                                         # 既存フィールド、新しい導出規則
                                                         # は作らない）
            )
            self._draft_state_manager.record_attempted(identity, context.member_run_id)
            # durable ACK確認後にのみ、以降のrequests.post()（実I/O）へ進む
            # （9.9.3節と同型のOrdering Contract、WORDPRESS_DRAFT_CREATIONは
            #  IO_ARMEDフェーズを持たない単一フェーズのため、ACK＝record_attempted()
            #  の成功のみで足りる、9.3・9.9.1節の設計差異どおり）

        # isinstance(context, LegacyDirectExecutionContext)の場合、以降write-ahead
        # 呼び出しを一切行わず、既存（6.31以前）のロジックのまま進む——この型は
        # そもそもroot_run_id等のfieldを持たないため、混同の余地がない（2.1節）。

        # --- 既存のWordPress POSTロジック（endpoint構築・payload構築・requests.post()、無変更）---
        endpoint = f"{self.site_url}/wp-json/wp/v2/posts"
        ...
        response = requests.post(endpoint, json=payload, auth=(self.username, self.app_password), timeout=30)
        if response.status_code not in (200, 201):
            raise RuntimeError(f"WordPress投稿失敗 (HTTP {response.status_code}): {response.text[:200]}")
        response_data = response.json()
        post_id = response_data.get("id")
        # --- 既存ロジックここまで ---

        if isinstance(context, RetryLineageProtectedExecutionContext):
            self._draft_state_manager.record_confirmed(identity, context.member_run_id, post_id)
            # POST成功後・record_confirmed()前にクラッシュした場合、durable stateは
            # 「ATTEMPTED」のまま残り、restart後は12.2節の決定表（ATTEMPTED →
            #  IN_PROGRESS_OR_UNKNOWN）を経て
            #  resolve_final_disposition()（13章）がHUMAN_REVIEW_REQUIREDへ導く。
            #  16章のopen_next_attempt()ガードにより自動retryはこのlineageに対して
            #  構造的に拒否される（既存の9.9.5節Crash Semanticsと同型の帰結、
            #  WORDPRESS_DRAFT_CREATIONはIO_ARMEDを持たないためATTEMPTED到達時点で
            #  既にPOSTが実行された可能性を否定できず、確認する術がないことが
            #  この設計のfail-closed境界そのものである——9.9.1節のMEDIA_UPLOAD側
            #  再定義とは異なり、WORDPRESS_DRAFT_CREATIONは元々9章でこの境界を
            #  ATTEMPTED確定時点に置いている設計）。

        return SaveResult(success=True, output_type="wordpress", post_id=post_id)  # 既存ロジック
```

**WordPress draftとmedia uploadの独立性**：呼び出し箇所A（本節）が書き込む`WordPressDraftStateManager`のrecordと、呼び出し箇所B（15.4節）が書き込む`MediaUploadSafetyCoordinator`のrecordは、`operation_kind`（`WORDPRESS_DRAFT_CREATION` vs `MEDIA_UPLOAD`）が異なるため、8章のidentityレベルで完全に別個のrecordとなる。10.1節のOperation Applicability原則（operation単位で独立に判定）により、一方のevidence（例：media uploadがCONFIRMED_SUCCESS）を他方（WordPress draft creationの状態）の代用証拠として用いることは構造的に発生しない——`classify()`（10章）は`operations: list[ProtectedOperationContext]`の各要素を個別に評価し、`media_coordinator.get()`と`draft_state.get()`を混同して呼び出す経路を持たない。

**main.py側の配線**：main.pyは14.3節で`side_effect_execution_context`を一度だけ解決し（main.py起動そのものがrun-scoped単位のため、`WorkflowEngineManager`とは異なりconstructor injectionで問題ない）、`WordPressOutput.from_env()`ではなく、この値を注入する新しいファクトリ（例：`WordPressOutput.from_env_with_context(side_effect_execution_context, draft_state_manager)`）経由で構築する（22.1f節）。呼び出し箇所B（`ArticleFeaturedMediaRuntime`、15.4節）はこの値を共有するが、Foundationのconstructor/apply()へ直接渡すことはない——main.py内で1回解決した同一インスタンスは、6.32 integration wiring層（`MediaUploadWriteAheadAdapters`・`build_protected_featured_media_runtime()`、22.3.2節）へ渡り、そこで呼び出し箇所Bの記事ごとのidentity・decoratorへ反映される（値の再構築・再推測はしない、6章のformal invariant。15.4節「main.py側の配線との整合」）。

---

## 16. Design Decision I：`open_next_attempt()`のHRR authorized-retry拡張

本節は既存`RetryLineageManager.open_next_attempt()`（whole-record atomic save、1回の`with self._store_lock():`ブロック内で全フィールドを更新する既存実装、9.2章）をそのまま拡張する。新しいCAS API・新しいstore method・per-identity lockのいずれも追加しない——既存のグローバルな`RetryLineageStoreLock`（`_store_lock()`）と、呼び出し元が保持する`RetryExecutionLock`のみを用いる。

```python
def open_next_attempt(self, root_run_id: str) -> OpenNextAttemptResult:
    with self._store_lock():
        record = self._store.get(root_run_id)
        if record is None or record.phase != RetryLineagePhase.TERMINAL:
            return OpenNextAttemptResult(acknowledged=False, reason="phase mismatch: not TERMINAL")

        resolution = record.human_review_resolution
        hrr_authorized = (
            record.terminal_disposition == RetryLineageDisposition.HUMAN_REVIEW_REQUIRED
            and resolution is not None
            and resolution.resolution == HumanReviewResolution.RETRY_ALLOWED
        )
        if (
            record.terminal_disposition not in (RetryLineageDisposition.FAILED, RetryLineageDisposition.NOT_ACTIONED)
            and not hrr_authorized
        ):
            return OpenNextAttemptResult(
                acknowledged=False,
                reason="terminal_disposition is not retryable (HUMAN_REVIEW_REQUIRED requires an "
                       "explicit RETRY_ALLOWED resolution via resolve_human_review(), 17章)."
            )

        if record.attempt_count >= record.max_attempts:
            return OpenNextAttemptResult(acknowledged=False, reason="max_attempts exhausted")

        # （既存の next_attempt_ordinal 同期チェック・steps_to_execute 非空チェックは無変更。
        #  hrr_authorized経路もこれらのガードを一切迂回しない。）
        ...

        now = datetime.now()
        next_attempt_no = record.next_attempt_ordinal + 1
        next_scope = RetryAttemptExecutionScope(
            attempt_no=next_attempt_no,
            steps_confirmed_done_before=list(record.steps_confirmed_done),
            steps_to_execute=_canonicalize_step_order(steps_to_execute),
            determined_at=now,
        )
        record.attempt_scopes.append(next_scope)
        record.phase = RetryLineagePhase.READY_ELIGIBLE
        record.terminal_disposition = None
        if hrr_authorized:
            # 6.32新設：HRR authorized経路では human_review_resolution をクリアせず、
            # dispatch resumeのためのcrash-resumable markerとしてopened_attempt_noへ
            # 新attempt番号を記録する（17.2節）。この段階ではクリアしない——クリアは
            # mark_execution_started()が実際にこのattemptの実行開始を確認した時点
            # まで遅延させる（17.2節）。
            record.human_review_resolution = replace(resolution, opened_attempt_no=next_attempt_no)
        else:
            record.human_review_resolution = None
        record.next_eligible_at = None
        record.next_attempt_ordinal = next_attempt_no
        record.transition_history.append(
            RetryLineageTransitionEvent(
                attempt_no=next_attempt_no, from_phase=RetryLineagePhase.TERMINAL,
                to_phase=RetryLineagePhase.READY_ELIGIBLE, run_id=None, at=now,
                detail=(
                    "next attempt opened via RETRY_ALLOWED human review resolution"
                    if hrr_authorized else "next attempt opened"
                ),
            )
        )
        record.updated_at = now
        ok = self._store.save(record)
        if not ok:
            return OpenNextAttemptResult(acknowledged=False, reason="lineage store save failed")
        return OpenNextAttemptResult(acknowledged=True, attempt_no=next_attempt_no)


def open_next_attempt_after_human_review(self, root_run_id: str) -> OpenNextAttemptResult:
    """operator-invoked専用のself-locking wrapper（`reconcile_all()`と同型）。
    `open_next_attempt()`自身はRetryExecutionLockを取得しない——呼び出し元が既に
    取得済みであることを前提とする既存契約（9.3章）。自動reconciliation sweep
    （`_reconcile_all_locked()`）以外から`open_next_attempt()`を呼ぶ経路は、
    本wrapperのみを経由する。呼び出し元（composition層の`retry_after_human_review()`、
    17.3節）は、本メソッドを呼ぶ前にpeek()でresumable state（既にopened_attempt_no
    が確定済みのREADY_ELIGIBLE record）かどうかを確認し、resumable であれば
    本メソッドを再度呼ばない——本メソッド自身は常にTERMINALからの新規openのみを扱う。"""
    try:
        with RetryExecutionLock(self.execution_lock_path):
            return self.open_next_attempt(root_run_id)
    except RetryExecutionLockBusyError:
        return OpenNextAttemptResult(acknowledged=False, reason="execution lock busy")
```

**呼び出し元での二重ガード（Defense-in-depth invariant #5、25章）**：`_reconcile_all_locked()`のopened_countループ（`terminal_disposition in (FAILED, NOT_ACTIONED)`のみを対象にする既存フィルタ）は、`human_review_resolution`の値に関わらずHRR lineageを常に除外する——自動reconciliation sweepが`open_next_attempt()`をHRR lineageに対して呼ぶ経路は存在しない。RETRY_ALLOWED resolutionに基づく再試行は、この自動sweepとは完全に別の経路である`open_next_attempt_after_human_review()`（操作者が`resolve_human_review()`実行後に個別に呼ぶ、明示的なmanual retry呼び出し）からのみ到達する。`open_next_attempt()`自身の明示チェック（`hrr_authorized`の判定）と合わせ、**自動的なHRR再試行が発生しない経路は呼び出し元・関数自身の双方に存在する**（片方が将来のリファクタリングで欠落しても、もう片方が防御する）。

**crash-safety（duplicate attempt = 0）**：`open_next_attempt()`の全変更（`attempt_scopes`追加・`phase`遷移・`terminal_disposition`クリア・`human_review_resolution`更新・`next_attempt_ordinal`前進・`transition_history`追記）は、既存実装と同じく**1回の`self._store.save(record)`呼び出し**で原子的にdurable化される。save前にクラッシュした場合はdurable stateが完全に無変更のため、`open_next_attempt_after_human_review()`の再呼び出しはそのまま安全に同じ結果へ到達する。save成功後・呼び出し元が戻り値を受け取る前にクラッシュした場合、durable stateは既に`phase=READY_ELIGIBLE`（`TERMINAL`ではない）になっているため、`open_next_attempt_after_human_review()`自身の再呼び出しは既存の`if record.phase != RetryLineagePhase.TERMINAL`ガードにより`acknowledged=False`（安全なno-op）を返す——ただし、この場合`human_review_resolution.opened_attempt_no`がdurableに確定済みであるため、呼び出し元（composition層）はこの状態を「再openすべき失敗」ではなく「既にopen済みのattemptをdispatch resumeすべき状態」として区別できる（17.3節）。新しいCAS・追加のsub-phaseを一切導入せずとも、`phase`フィールドと`human_review_resolution.opened_attempt_no`の組み合わせが冪等性・resume判別子として機能し、2つ目のattemptが作成される経路は構造的に存在しない。

**過去attemptのHRR evidenceの永続性**：`terminal_disposition`は次attemptが開かれる時点で`None`へクリアされる（FAILED/NOT_ACTIONEDの既存経路と同一の挙動）。「あるattemptが`HUMAN_REVIEW_REQUIRED`に到達した」という事実は、`mark_terminal()`が記録する`transition_history`のエントリ（`detail="disposition=human_review_required"`）にappend-onlyで永久に保存され、`open_next_attempt()`はこの履歴を一切書き換えない（9.4節のAPI設計、削除・上書き相当のAPIは存在しない、26章）。**「`terminal_disposition`そのものが永久にimmutableである」という表現は撤回する**——immutableであるのは、過去attemptがHRRに到達したという`transition_history`上のevidenceであり、lineageの現在状態を表す`terminal_disposition`フィールド自体ではない。

---

## 17. Human Resolution Lifecycle

### 17.1 API（不変）

```python
class HumanReviewResolution(Enum):
    RETRY_ALLOWED = "retry_allowed"
    ABANDONED = "abandoned"

def resolve_human_review(
    self, root_run_id: str, resolution: HumanReviewResolution, actor: str, note: str | None = None,
) -> ResolveHumanReviewResult:
    ...
```

### 17.2 `resolve_human_review()`：durable one-shot resolution

`RetryLineageRecord`は補助フィールド`human_review_resolution: HumanReviewResolutionRecord | None`を保持する（既存の`next_eligible_at`/`owner_token`と同型の、新規CAS APIを要しない単純なoptional field）：

```python
@dataclass
class HumanReviewResolutionRecord:
    resolution: HumanReviewResolution
    actor: str
    note: str | None
    resolved_at: datetime
    opened_attempt_no: int | None = None  # 6.32新設：crash-resumable dispatch marker（17.3節）
```

**`opened_attempt_no`の役割**：`resolve_human_review(RETRY_ALLOWED)`が記録する時点では`opened_attempt_no=None`（未open）。`open_next_attempt()`（16章）がHRR authorized経路で次attemptを開く際、同一の`save()`呼び出し内で`opened_attempt_no`へ新しい`attempt_no`を設定する——この時点では`human_review_resolution`全体をクリアしない（16章）。これにより、`open_next_attempt()`成功後・実際のdispatch（`RetryManager.retry()`）前にクラッシュしても、durable recordから「どのattemptが既にopenされ、dispatchを再開すべきか」を一意に読み取れる（17.3節）。

`resolve_human_review()`は`RetryExecutionLock`を自ら取得してから（`reconcile_all()`と同型のself-locking method）、既存の`_store_lock()`（`RetryLineageStoreLock`）でread-modify-writeを行う（9.3章Lock Ordering：`RetryExecutionLock`→`RetryLineageStoreLock`）：

```python
def resolve_human_review(
    self, root_run_id: str, resolution: HumanReviewResolution, actor: str, note: str | None = None,
) -> ResolveHumanReviewResult:
    try:
        with RetryExecutionLock(self.execution_lock_path):
            return self._resolve_human_review_locked(root_run_id, resolution, actor, note)
    except RetryExecutionLockBusyError:
        return ResolveHumanReviewResult(acknowledged=False, reason="execution lock busy")


def _resolve_human_review_locked(
    self, root_run_id: str, resolution: HumanReviewResolution, actor: str, note: str | None,
) -> ResolveHumanReviewResult:
    with self._store_lock():
        record = self._store.get(root_run_id)
        if (
            record is None
            or record.phase != RetryLineagePhase.TERMINAL
            or record.terminal_disposition != RetryLineageDisposition.HUMAN_REVIEW_REQUIRED
        ):
            return ResolveHumanReviewResult(acknowledged=False, reason="not in HUMAN_REVIEW_REQUIRED")

        existing = record.human_review_resolution
        if existing is not None:
            if existing.resolution == resolution:
                # 同一decisionの再送：idempotent success。actor/note/resolved_atは
                # 既存recordのまま上書きしない。追加のdurable writeも行わない。
                return ResolveHumanReviewResult(acknowledged=True)
            return ResolveHumanReviewResult(
                acknowledged=False,
                reason=f"conflicting resolution already recorded: {existing.resolution.value}",
            )

        now = datetime.now()
        record.human_review_resolution = HumanReviewResolutionRecord(
            resolution=resolution, actor=actor, note=note, resolved_at=now,
        )
        attempt_no = record.attempt_scopes[-1].attempt_no if record.attempt_scopes else record.next_attempt_ordinal
        record.transition_history.append(
            RetryLineageTransitionEvent(
                attempt_no=attempt_no, from_phase=RetryLineagePhase.TERMINAL,
                to_phase=RetryLineagePhase.TERMINAL, run_id=None, at=now,
                detail=f"human_review_resolution={resolution.value}",
            )
        )
        record.updated_at = now
        ok = self._store.save(record)
        if not ok:
            return ResolveHumanReviewResult(acknowledged=False, reason="lineage store save failed")
        return ResolveHumanReviewResult(acknowledged=True)
```

**前提条件**：`phase == TERMINAL`かつ`terminal_disposition == HUMAN_REVIEW_REQUIRED`の場合にのみ受理する。それ以外は`acknowledged=False`。

**未resolutionの場合**：`resolution`引数（`RETRY_ALLOWED`または`ABANDONED`）をそのままdurableに記録する。`RETRY_ALLOWED`はauthorizationの記録のみを行い、`open_next_attempt()`・queueいずれに対しても自動的な作用を一切発生させない（次attemptを開くのは16章が定める別経路、`open_next_attempt_after_human_review()`の明示呼び出しのみ）。`ABANDONED`は次attemptを永続的に禁止する——`open_next_attempt()`の`hrr_authorized`判定（16章）は`resolution.resolution == RETRY_ALLOWED`を要求するため、`ABANDONED`が記録された状態でこの判定が真になることはない。

**同一decisionの再送**：既に記録済みのresolutionと同じ値が渡された場合、`acknowledged=True`のidempotent successを返す。`actor`/`note`/`resolved_at`は最初の記録のまま上書きされない。

**異なるdecision（conflicting resolution）**：既に記録済みのresolutionと異なる値が渡された場合、`acknowledged=False`でfail-closedする（例：`RETRY_ALLOWED`記録済みの状態で`ABANDONED`を渡す、またはその逆）。

**`human_review_resolution`のクリアタイミング**：`open_next_attempt()`のHRR authorized経路は、次attemptを開く時点で`human_review_resolution`をクリアしない——`opened_attempt_no`へ新しい`attempt_no`を設定するのみである（16章）。クリアは`mark_execution_started()`（9.5章）が実際にこのattemptの実行開始を確認した時点まで遅延させる：`mark_execution_started()`は、既存の処理（`phase`を`EXECUTION_STARTED`へ遷移・`attempt_count`を+1・`membership`追記・`transition_history`追記）と**同一の`save()`呼び出し内**で、`record.human_review_resolution is not None and record.human_review_resolution.opened_attempt_no == attempt_no`（この`mark_execution_started()`が確定させるattempt番号と一致する場合のみ）を条件に`record.human_review_resolution = None`へクリアする。これにより、同一lineageが将来再び`HUMAN_REVIEW_REQUIRED`に到達した場合、そのattemptに対して独立に新しい`resolve_human_review()`を受け付けられる。FAILED/NOT_ACTIONED由来の通常経路（`hrr_authorized`が偽）では`human_review_resolution`は元々`None`のままであり、この追加ロジックは無効果（no-op）である。

**attempt budget / lineage integrity**：`open_next_attempt()`のHRR authorized経路は、既存のattempt budget（`max_attempts`）検証・`next_attempt_ordinal`同期チェック・`steps_to_execute`非空チェックのいずれも迂回しない（16章、通常のFAILED/NOT_ACTIONED経路と完全に同一のガードを共有する）。

### 17.3 Dispatch：composition層の`retry_after_human_review()`

**queue/schedulerへの依存なし**：`resolve_human_review()`・`open_next_attempt_after_human_review()`はいずれも`RetryQueueManager`／`retry_queue_status`への書き込みを一切行わない。HRR authorized経路が`open_next_attempt()`を通じて`phase=READY_ELIGIBLE`にした後、この新attemptをFAILED/NOT_ACTIONED由来の自動retryと同じscheduler/queue駆動の経路（`RetryEnqueueTrigger`→scheduler event→`RetryManager.retry()`）へ載せることはしない——`RetryEnqueueTrigger.enqueue_pending_failures()`のmembership-first除外（22.1e節）は、既にlineage memberとなったrun_idを常に対象外とするため、この経路は構造的にHRR authorized attemptを拾わない。**Release 6.32はこの一般的な自動re-dispatch gapを修正しない**（§2 Non-Goals）——HRR authorized retryは、以下の明示的なcomposition層の呼び出しのみによってdispatchされる。

**`retry_after_human_review()`（新設、composition層）**：`retry_lineage`パッケージの外側、`RetryLineageManager`と`RetryManager`の両方を組み立て済みの参照として保持しているcomposition層（例：`retry_composition`）に配置する。依存方向は`composition → RetryLineageManager`・`composition → RetryManager`の一方向のみであり、**`retry_lineage`から`retry_engine`/`retry_queue`/`scheduler`への逆依存は追加しない**（`retry_lineage`は本節の関数を一切importしない）。

```python
def retry_after_human_review(
    lineage: "RetryLineageManager",
    manager: "RetryManager",
    root_run_id: str,
    resolution: "HumanReviewResolution",
    actor: str,
    note: str | None = None,
) -> "RetryResult | ResolveHumanReviewResult | OpenNextAttemptResult":
    # crash-resumable resume判定：resolve_human_review()を再度呼ぶ前に、
    # 既にauthorized-openが完了しdispatch待ちの状態かどうかをread-onlyで確認する。
    record = lineage.peek(root_run_id)
    if (
        record is not None
        and record.phase == RetryLineagePhase.READY_ELIGIBLE
        and record.human_review_resolution is not None
        and record.human_review_resolution.resolution == HumanReviewResolution.RETRY_ALLOWED
        and record.human_review_resolution.opened_attempt_no is not None
        and record.human_review_resolution.opened_attempt_no == record.next_attempt_ordinal
    ):
        # 既にauthorized-open済み（前回呼び出しがdispatch前にクラッシュした等）——
        # resolve_human_review()・open_next_attempt()のいずれも再度呼ばず、
        # 記録済みのattempt_noでdispatchのみを再開する。
        return manager.retry(root_run_id, attempt=record.human_review_resolution.opened_attempt_no)

    result = lineage.resolve_human_review(root_run_id, resolution, actor, note)
    if not result.acknowledged or resolution != HumanReviewResolution.RETRY_ALLOWED:
        return result

    opened = lineage.open_next_attempt_after_human_review(root_run_id)
    if not opened.acknowledged:
        return opened

    return manager.retry(root_run_id, attempt=opened.attempt_no)
```

**resume判定のexactness**：`opened_attempt_no`が`record.next_attempt_ordinal`と一致しない場合（データ破損等、通常発生しない）、または`phase`が`TERMINAL`でも上記resume条件を満たす`READY_ELIGIBLE`でもない場合（ambiguous state）は、いずれもresume分岐を通らず`resolve_human_review()`へフォールスルーする——`phase != TERMINAL`であればそこで`acknowledged=False, reason="not in HUMAN_REVIEW_REQUIRED"`としてfail-closedし、推測によるdispatchは行わない。

**`RetryManager.retry()`は無改修**：`retry_after_human_review()`は既存の`RetryManager.retry(root_run_id, attempt=...)`をそのまま呼ぶ。`_retry_locked()`は`open_next_attempt()`を呼ばず、既にREADY_ELIGIBLEなattemptを`find_existing_lineage()`→`claim()`→`execute()`でdispatchするのみであるため、`open_next_attempt_after_human_review()`が既にattemptを開いた後に`retry()`が重ねて`open_next_attempt()`を呼び直す経路は存在せず、二重attemptのリスクは構造的にない。`claim()`は`phase == READY_ELIGIBLE`のみを受理し非READY_ELIGIBLEな状態からの二重claimを拒否するため、`retry_after_human_review()`を誤って複数回呼んでも、2回目以降は`claim()`の既存ガードにより安全に失敗する。

**post-hoc bookkeepingとの分離**：22.4節の`RetryQueueUpdateDecider`（HRR専用のoutcome/status値は追加しない）は、既に実行された再試行結果に対するpost-hoc bookkeeping（Queue項目のCOMPLETED/FAILED判定・cleanup、HRRはFAILEDへ合流）のみを担い、retry eligibility・authorization・dispatchのauthorityではない。

### 17.4 Human解決時の情報開示（不変）

`list_operations_for_lineage(root_run_id)`（読み取り専用。具体的な出力形状はImplementation Detail、29章#10）。

---

## 18. Design Decision J：Legacy互換・Contract Version Snapshot

### 18.1 設計

- `RetryLineageRecord.side_effect_contract_version: int | None`。
- `create_new_lineage()`のみがスタンプ（`SIDE_EFFECT_CONTRACT_VERSION = 1`）、`open_next_attempt()`は上書きしない（6.31の`max_attempts`スナップショットと同じ原則）。

`side_effect_contract_version`が`None`（正式なpre-6.32/legacy）でも`>= 1`（6.32 protected contract）でもない値（`0`・負値・非intのmalformed値）は、**legacyへ推測せず、invalid contract evidenceとしてfail-closedする**——3値のclosed setとして扱う：

```python
class ContractVersionEvidence(Enum):
    LEGACY = "legacy"        # side_effect_contract_version is None（正式なpre-6.32/legacy lineage）
    PROTECTED = "protected"  # side_effect_contract_version >= 1（6.32 protected contract）
    INVALID = "invalid"      # 0・負値・非intのmalformed値（legacyでもprotectedでもない）


def classify_contract_version_evidence(record: "RetryLineageRecord") -> "ContractVersionEvidence":
    """side_effect_contract_versionの妥当性判定を行う唯一の関数（本節が18章・22.4章・
    22.4a章すべてのauthority）。呼び出し元はこの関数の
    戻り値のみに基づいて分岐し、独自の`< 1`・`is None`比較を重複実装しない。"""
    version = record.side_effect_contract_version
    if version is None:
        return ContractVersionEvidence.LEGACY
    if isinstance(version, int) and not isinstance(version, bool) and version >= 1:
        return ContractVersionEvidence.PROTECTED
    return ContractVersionEvidence.INVALID


def _is_6_32_contract_lineage(record: RetryLineageRecord) -> bool:
    """後方互換のための薄いwrapper（18.2節の分岐で使用）。PROTECTED以外は
    Falseを返すが、INVALIDをLEGACYと同一視しない——18.2節でINVALIDは
    別途fail-closedされる（本表の直後を参照）。"""
    return classify_contract_version_evidence(record) == ContractVersionEvidence.PROTECTED
```

### 18.2 判定ロジックとの接続

- `classify_contract_version_evidence(record) == ContractVersionEvidence.LEGACY`：`resolve_final_disposition()`（13章）を呼ばず、6.31までの`disposition_from_categories()`のみを使う。12章のAbsence/Evidence Decision Tableは**適用しない**（write-aheadマーカーが存在しないことを理由にHRRへ倒さない、要求#11）。
- `classify_contract_version_evidence(record) == ContractVersionEvidence.PROTECTED`：12章の決定表を適用する。
- `classify_contract_version_evidence(record) == ContractVersionEvidence.INVALID`：**LEGACYへもPROTECTEDへも倒さない。** `RetryLineageContractVersionError`（9.6節と同型の実装契約違反例外）を送出し、fail-closedする。`0`・負値・malformedな`side_effect_contract_version`は、`create_new_lineage()`のスタンプ契約（本節）が正しく守られていれば発生しないはずの状態であり、発生した場合はdurable dataの破損またはスタンプ処理自体のバグを示す——推測による復旧（legacyとして扱う、あるいはprotectedとして扱う）を一切行わない。

### 18.3 適用範囲

新契約は`create_new_lineage()`により新規作成されるlineageにのみ適用される。それ以外のlineageへの遡及的保護は行わない（Non-Goal）。

---

## 19. Design Decision K：Human Review Observability

### 19.1 Structured Reason Code

```python
class HumanReviewReasonCode(Enum):
    SIDE_EFFECT_IN_PROGRESS_OR_UNKNOWN = "side_effect_in_progress_or_unknown"
    SIDE_EFFECT_CONTRACT_VIOLATION = "side_effect_contract_violation"
    CONFIRMED_SIDE_EFFECT_WITH_UNSAFE_PARTIAL_FAILURE = "confirmed_side_effect_with_unsafe_partial_failure"
```

`RetryLineageTransitionEvent`に`human_review_reason_code`・`human_review_side_effect_context`（secret/API応答全文非保持、`FeaturedMediaFailureObservation`の precedent踏襲）を追加する。自由テキストの`detail`は非authoritative。

### 19.2 Human解決記録

17章の`resolve_human_review()`呼び出しも、同様に`RetryLineageTransitionEvent`（`to_phase`は変化しないため専用の新規イベント種別。`human_resolution`フィールド追加か別クラス化かはImplementation Detailとする）としてdurableに記録する。**自動解除は一切のAPI経路を持たない**（Defense-in-depth invariant #7、25章）。

---

## 20. State Machine

```
[MEDIA_UPLOAD: MediaUploadSafetyCoordinator（9.9節）、identity-scoped lock（27章）]
  lock（該当identity専用）acquire
    body実行（4メソッド共通のACK→committed=True→戻り値構築の順序、9.9.4.4節の表。
    `record_prepared()`を含む4メソッドに一律適用）：
      record_prepared(): all absent（またはPREPARED/PREPARED+ATTEMPTEDの冪等no-op）
        --PREPARED ACK--> commit_state["committed"]=True --> 戻り値構築（PreparedMediaUploadSafetyRecord）
      record_attempted(): all absent --PREPARED ACK--> --ATTEMPTED ACK--> --IO_ARMED ACK-->
        commit_state["committed"]=True --> 戻り値構築（IoArmedMediaUploadSafetyRecord）
      record_attempted(): PREPARED(+ATTEMPTED) --Safe Continuation--> --IO_ARMED ACK-->
        commit_state["committed"]=True --> 戻り値構築（IoArmedMediaUploadSafetyRecord）
    bodyがcommitted=True到達前にExceptionを送出 --> pre-commit failure、cleanup試行（結果無視）、元の例外を送出
    bodyがcommitted=True到達後にExceptionを送出（戻り値構築失敗等）--> post-commit success維持、
      cleanup試行、CommitAwareResult(acknowledged=True, cleanup_diagnostics=(...))を返す
    bodyがKeyboardInterrupt/SystemExit等のBaseExceptionを送出 --> committed状態に関わらず、
      cleanup試行後に必ず再送出（握りつぶさない）
    bodyが正常returnしたがcommitted=True未設定 --> MediaUploadSafetyImplementationContractError送出
  lock release（best-effort、post-commitなら失敗してもsemantic successを維持、secret-safeなCleanupDiagnosticのみ記録）
  （lock解放後）--external upload（呼び出し元、15.4節）--> 実I/O実行
  IO_ARMED + ATTEMPTED --record_confirmed()、CONFIRMED_SUCCESS ACK直後にcommit_state["committed"]=True--> CONFIRMED_SUCCESS

[Cross-Store Combination Table（9.9.7節、不変）→ SideEffectSafetyCategory]
  （disposition判定はdurable stateのみを参照、cleanup_diagnosticsは無関係）

[RetryLineageDisposition（TERMINAL到達時、resolve_final_disposition()が決定）]
  SUCCEEDED / FAILED / NOT_ACTIONED / HUMAN_REVIEW_REQUIRED（不変）
```

---

## 21. Crash Matrix

シナリオ1〜30は、両operation（`WORDPRESS_DRAFT_CREATION`／`MEDIA_UPLOAD`）・全3呼び出し箇所（A/B/C）にわたる**構造レベルのcrash/fault点**（write-ahead境界・確認境界・cross-store整合・reconciliation・retry除外・legacy互換・contract version妥当性）を対象とし、それぞれの結果は7章state machine・9.9.1〜9.9.9節・12章Decision Table・13章`resolve_final_disposition()`・15章統合・16章retry除外・18章legacy互換・25章invariantsが定める契約に従う。

シナリオ31〜52は、`MediaUploadSafetyCoordinator`のCommit-Aware Lock Helper（9.9.4節）が扱うACK順序・例外境界・cleanup診断・3段fallbackという**実装内部の頑健性**を検証する、より詳細な粒度のシナリオ群である。両者は粒度が異なるが矛盾しない——31〜52は1〜30の一部（特にIO_ARMED境界前後の窓）をさらに細分化したものである。

各シナリオは以下7項目を明示する：**Crash/Fault Point**（発生点）・**Durable Evidence Before Crash**（クラッシュ時点で存在するdurable evidence）・**Possible External I/O State**（durable evidenceから排除できない外部I/O状態の範囲。実際の真の状態と、分類器が証明できる範囲は区別する）・**Restart Classification**（`SideEffectSafetyCategory`、11.1節5値）・**Final Disposition**（`RetryLineageDisposition`）・**Retry Allowed/Forbidden**（自動retry可否）・**Expected External I/O Count**（想定される外部I/O回数）。

| # | Group | Crash/Fault Point | Durable Evidence Before Crash | Possible External I/O State（排除できない範囲） | Restart Classification | Final Disposition | Retry Allowed/Forbidden | Expected External I/O Count |
|---|---|---|---|---|---|---|---|---|
| 1 | WP-A（`WORDPRESS_DRAFT_CREATION`、NEWS_STEP、呼び出し箇所A） | `record_attempted()`が一度も呼ばれる前にプロセスが終了する（真の状態としてはI/O=0のはずだが、それを示すdurable evidenceが一切ない） | absent（record自体が存在しない） | 0とも1とも断定できない（実際は0のはずだが、この事実自体がdurable化されていないため分類器は証明できない） | `CONTRACT_VIOLATION`（12.2節authoritative rule、operation-specific durable evidenceなし） | `HUMAN_REVIEW_REQUIRED` | 禁止 | 分類上「不明」（真の値は0） |
| 2 | WP-A | `record_attempted()`のATTEMPTED ACK確認後・`requests.post()`実行前にクラッシュ | `ATTEMPTED` | 0（真の状態）だが記録からは排除できない | `IN_PROGRESS_OR_UNKNOWN` | `HUMAN_REVIEW_REQUIRED`（15.7節が明示的に受容するfail-closed窓） | 禁止 | 0〜1（不明） |
| 3 | WP-A | `requests.post()`成功・`record_confirmed()`呼び出し前にクラッシュ | `ATTEMPTED`（#2と同一durable state） | 1（真の状態） | `IN_PROGRESS_OR_UNKNOWN`（#2と分類上区別不能） | `HUMAN_REVIEW_REQUIRED` | 禁止 | 1（だが分類上は#2と見分けがつかない、fail-closedの本質） |
| 4 | WP-A | `record_confirmed()`ACK成功、他stepも全てGENUINE_SUCCESS | `CONFIRMED_SUCCESS` | 1 | `CONFIRMED_SUCCESS` | `SUCCEEDED`（13章、base_dispositionと一致） | 該当なし（正常終端） | 1 |
| 5 | WP-A | `record_confirmed()`ACK成功だが同一attempt内の他stepが失敗（base_disposition≠SUCCEEDED） | `CONFIRMED_SUCCESS` | 1 | `CONFIRMED_SUCCESS` | `HUMAN_REVIEW_REQUIRED`（13章） | 禁止（確定成功した副作用の重複防止） | 1 |
| 6 | WP-A | `record_confirmed()`のdurable ACK書き込み自体がI/Oエラーで失敗 | `ATTEMPTED`のまま（confirmedへ遷移しない） | 1（POSTは既に成功） | `IN_PROGRESS_OR_UNKNOWN` | `HUMAN_REVIEW_REQUIRED` | 禁止 | 1 |
| 7 | WP-A | 同一identityへ`create_attempted()`を2回呼ぶ（duplicate、9.4節） | 既存`ATTEMPTED`（1回目のまま不変） | 2回目呼び出し自体はI/Oを発生させない | 既存recordの状態に従う（通常`IN_PROGRESS_OR_UNKNOWN`） | 既存recordの状態に従う | 既存recordの状態に従う | 2回目呼び出し由来の追加I/O=0 |
| 8 | WP-A | `transition_to_confirmed()`をmember_run_id不一致で呼ぶ（compare-and-transition拒否） | `ATTEMPTED`維持（上書きされない） | 1（POSTは既に発生済み） | `IN_PROGRESS_OR_UNKNOWN` | `HUMAN_REVIEW_REQUIRED` | 禁止 | 1 |
| 9 | WP-A | `get()`のread時検証がidentity/member_run_id不一致・record破損を検出（9.3節） | 破損・不一致record | 不明（fail-closed、真の値によらず一律） | `CONTRACT_VIOLATION`（read時検証が本表評価より優先） | `HUMAN_REVIEW_REQUIRED` | 禁止 | 不明 |
| 10 | WP-C（`WORDPRESS_DRAFT_CREATION`、PUBLISH_STEP、呼び出し箇所C） | `record_attempted()`ACK後・`post_draft()`実行前にクラッシュ | `ATTEMPTED`（`effect_site=PUBLISH_STEP`） | 0（真の状態）だが排除できない | `IN_PROGRESS_OR_UNKNOWN` | `HUMAN_REVIEW_REQUIRED` | 禁止 | 不明 |
| 11 | WP-C | 同一article・同一attemptでNEWS_STEP側が既に`CONFIRMED_SUCCESS`確定済みの状態で、PUBLISH_STEP側がscenario 10と同時に発生する（8章identityによる非干渉の確認） | NEWS側`CONFIRMED_SUCCESS`／PUBLISH側`ATTEMPTED` | NEWS側1・PUBLISH側は排除できない | `worst_case()`はPUBLISH側の`IN_PROGRESS_OR_UNKNOWN`が優先（10.1節Operation Applicability独立判定） | `HUMAN_REVIEW_REQUIRED`（attempt全体） | 禁止 | NEWS側1＋PUBLISH側不明（互いに非干渉） |
| 12 | MU-B（`MEDIA_UPLOAD`、NEWS_STEP、呼び出し箇所B、9.9.4節Commit-Aware Lock Helperの内部機構＝シナリオ31以降とは異なる構造レベルのcrash点） | Gate OFF、`record_not_applicable()`のNOT_APPLICABLE ACKが成功 | 明示`NOT_APPLICABLE`marker | 0 | `NOT_APPLICABLE` | base_dispositionそのまま（このoperationはHRRを発火させない） | 通常どおり許可 | 0 |
| 13 | MU-B | Gate OFF、`record_not_applicable()`のACK自体がI/Oエラーで失敗し、その直後にクラッシュ | all absent（markerが確定していない、invariant#12） | 0（真の状態）だが排除できない | `CONTRACT_VIOLATION`（9.9.7「all absent」行） | `HUMAN_REVIEW_REQUIRED` | 禁止 | 不明 |
| 14 | MU-B | Gate ON、いかなるMEDIA_UPLOAD write-ahead呼び出しにも到達せずクラッシュ | all absent | 0（真の状態）だが排除できない | `CONTRACT_VIOLATION`（12.2節authoritative rule、`StepOutcomeCategory`は一切参照しない） | `HUMAN_REVIEW_REQUIRED` | 禁止 | 不明 |
| 15 | MU-B | `create_prepared()`ACK後・`record_attempted()`（ATTEMPTED作成）前にクラッシュ | `PREPARED`のみ | 0（確実、9.9.1節境界） | `SAFE_TO_CONTINUE` | base_dispositionそのまま | 許可（同一attempt内でSafe Continuationにより再開） | 0 |
| 16 | MU-B | `PREPARED`+`ATTEMPTED`確定後・`transition_to_io_armed()`前にクラッシュ | `PREPARED`+`ATTEMPTED` | 0（確実、`IO_ARMED`未到達） | `SAFE_TO_CONTINUE` | base_dispositionそのまま | 許可（Safe Continuation） | 0 |
| 17 | MU-B | `IO_ARMED`ACK確認後（decorated`upload()`内部、`orchestrator.apply()`実行の**途中**——`orchestrator.apply()`の実行開始前ではない）、実`media_uploader.upload()`の前後・`runtime.apply()`のreturn前後・main.py側の`record_confirmed()`呼び出し前のいずれかでクラッシュ（durable stateのみからは区別不能） | `IO_ARMED`+`ATTEMPTED` | 0または1（意図的に受容する窓、9.9.1節） | `IN_PROGRESS_OR_UNKNOWN` | `HUMAN_REVIEW_REQUIRED` | 禁止 | 不明（0または1） |
| 18 | MU-B | `runtime.apply(article)`が`runtime_result.status is ArticleFeaturedMediaRuntimeStatus.APPLIED`を返し、main.py側が`applied_article = runtime_result.article`をunwrapした上で`_extract_confirmed_media_id(applied_article)`を呼んだ結果、これが`None`を返す（`featured_media_id`が0/None/非int） | `IO_ARMED`+`ATTEMPTED`（main.py側owner=`_apply_featured_media_step()`が`record_confirmed()`を呼ばない、15.5.1節条件1〜4未達） | 1 | `IN_PROGRESS_OR_UNKNOWN` | `HUMAN_REVIEW_REQUIRED`（15.5.2節） | 禁止 | 1 |
| 19 | MU-B | `record_confirmed()`ACK成功、他stepも全てGENUINE_SUCCESS（restart後もdurableに保持されることを含む、26章Non-Recycle） | `IO_ARMED`+`CONFIRMED_SUCCESS` | 1 | `CONFIRMED_SUCCESS` | `SUCCEEDED` | 該当なし | 1 |
| 20 | MU-B | `record_confirmed()`ACK成功だがbase_disposition≠SUCCEEDED | `IO_ARMED`+`CONFIRMED_SUCCESS` | 1 | `CONFIRMED_SUCCESS` | `HUMAN_REVIEW_REQUIRED`（13章） | 禁止 | 1 |
| 21 | MU-B | cross-store矛盾（markerと`PREPARED`/`ATTEMPTED`/`CONFIRMED_SUCCESS`の併存、または`IO_ARMED`単独存在等、9.9.7節の矛盾行全般を人為的に注入） | 矛盾するrecord組み合わせ | 不明（fail-closed） | `CONTRACT_VIOLATION`（9.9.7節） | `HUMAN_REVIEW_REQUIRED` | 禁止 | 不明 |
| 22 | MU-B | `record_confirmed()`（`MEDIA_UPLOAD`）のdurable ACK書き込み自体が`article_media_upload_state`側のI/Oエラーで失敗 | `IO_ARMED`+`ATTEMPTED`のまま | 1（upload自体は成功） | `IN_PROGRESS_OR_UNKNOWN` | `HUMAN_REVIEW_REQUIRED` | 禁止 | 1 |
| 23 | MU-B | あるidentity Xの`MediaUploadSafetyCoordinatorLock`がpost-commit cleanup失敗によりstaleのまま残存する状態で、別のidentity Yへ`record_attempted()`を呼ぶ（27.5節identity-scoped lock） | X：stale lock影響下（Xのdurable stateは既存のまま）／Y：無関係 | Y側は正常に進行（Xの影響を受けない） | Y側はY自身のdurable stateのみに従って独立に判定される | Y側は通常どおり | Y側は通常どおり | Y側I/OはXの存在によって増減しない（0増加） |
| 24 | C（cross-cutting：operation independence） | 同一NEWS step内で`WORDPRESS_DRAFT_CREATION`（常時applicable）と`MEDIA_UPLOAD`（Gate OFF）が同時に評価される | WP側：正常確定（`ATTEMPTED`/`CONFIRMED_SUCCESS`）／MU側：明示`NOT_APPLICABLE`marker | WP側1・MU側0 | 各operationが10.1節Operation Applicability原則により独立に判定される（一方の結果が他方に波及しない） | 各operationの判定を個別に13章の優先順位へ入力 | 各operationの状態に従う | WP側1＋MU側0（独立） |
| 25 | C（reconciliation） | `HUMAN_REVIEW_REQUIRED`確定lineageに対し、`reconcile_all()`を複数回実行する（restartを挟む場合・挟まない場合の双方） | HRR確定時のdurable stateのまま不変 | 追加I/O発生なし（reconciliationはclassify/disposition解決のみでread-only、10.3節） | 変化なし（26章Non-Recycle、No Automatic Repair） | `HUMAN_REVIEW_REQUIRED`のまま維持 | 禁止（`open_next_attempt()`が16章のガードにより暗黙拒否） | 0（reconciliation自体は外部I/Oを一切発生させない） |
| 26 | C（retry再開のcontrol case） | `FAILED`/`NOT_ACTIONED`終端lineage（protected side effectのいずれにも一切到達していない、safety report自体がこのoperationを含まない）に対し`open_next_attempt()`を呼ぶ | 該当operationのrecordが一切存在しない（Operation Applicability上そもそも評価対象外だったケースを含む） | 0 | （safety reportに影響されず、base_dispositionのみで判定） | `FAILED`/`NOT_ACTIONED` | 許可（新しい`attempt_ordinal`で新規attemptが開始される、17.2節） | 0（新attemptは新しいSide-Effect Operation Identity） |
| 27 | C（legacy互換） | pre-6.32 legacy lineage（`side_effect_contract_version is None`）で、`LegacyDirectExecutionContext`経由のWordPress POST/media upload実行中にクラッシュする | 6.32のwrite-aheadマーカーは一切生成されない（設計どおり、2.1・15.4・15.6・15.7節） | 6.31以前と同一の不確定性（6.32の観測範囲外） | `classify_contract_version_evidence()`が`LEGACY`を返すため12章の決定表は適用されない（18.2節） | 6.31 `disposition_from_categories()`のみで決定（6.32のHRR拡張の影響を受けない） | 6.31契約のまま | 6.31契約範囲内（6.32の追跡対象外） |
| 27a | `scripts/run_ai_workflow.py`が`WorkflowRunner.run()`をStage 1/Stage 2のいずれも供給せずに呼ぶ（実装漏れ・呼び出し順序ミス等を模擬） | `AiPublishService._post()`到達前に`side_effect_execution_context`が欠落 | 0（pre-I/O fail-closedのため） | 該当なし（`validate_side_effect_execution_context()`が`MISSING_EXECUTION_MODE`でhard failureを送出、disposition解決へ進まない） | `SideEffectExecutionModeContractError`（2.4節fail-closed matrix） | 該当なし（disposition未確定のため） | 0（呼び出し箇所Cへ到達する前に停止、28.-20節#3の直接確認） |
| 28 | C（contract version妥当性） | `RetryLineageProtectedExecutionContext`配下のlineageで、`side_effect_contract_version`が0・負値・malformedである（`create_new_lineage()`のスタンプ契約が破られたdurable data corruptionを模擬） | 破損した`side_effect_contract_version` | 判定不能につきdisposition解決へ進む前にfail-closedする | `classify_contract_version_evidence()`が`INVALID`を返す | `RetryLineageContractVersionError`（18.2節、legacyへもprotectedへも推測しない） | 該当なし（disposition自体が未決定のため） | 該当なし（disposition解決前に停止するためexternal I/O概念に到達しない） |
| 29 | C（No Automatic Repair回帰確認） | 破損・矛盾するrecord（read時検証・cross-store検証のいずれかで検出される状態）を人為的に注入した状態で、複数回`reconcile_all()`を実行する | 破損record（複数回のreconcileでも不変） | 不明（fail-closed） | `CONTRACT_VIOLATION`（繰り返し確認しても変化しない） | `HUMAN_REVIEW_REQUIRED`（繰り返し確認しても変化しない、26章と同型のno-automatic-repair） | 禁止 | 不明（この値自体が繰り返し確認しても変化しないことを実証する） |
| 30 | C（dual-success baseline control case） | `WORDPRESS_DRAFT_CREATION`と`MEDIA_UPLOAD`の両方が同一attempt内で`CONFIRMED_SUCCESS`に到達し、他の全stepも`GENUINE_SUCCESS`（クラッシュなし、両operation完全成功の対照ケース） | 両operationとも`CONFIRMED_SUCCESS` | 各1（合計2） | 両operationとも`CONFIRMED_SUCCESS` | `SUCCEEDED` | 該当なし（正常終端） | 2（各operation1回ずつ、10.1節独立判定の正常系確認） |

write-ahead契約を経由しない外部呼び出しの検出限界は、crash/fault-point scenarioとしての性質を持たない構造的limitationであるため本章の対象外とし、§22.2「構造的限界の正直な記載」が扱う（29章#15）。

### 21.1 シナリオ31〜52

シナリオ1〜30（上記21章本表）は9列（Group・Crash/Fault Point・Durable Evidence Before Crash・Possible External I/O State・Restart Classification・Final Disposition・Retry Allowed/Forbidden・Expected External I/O Count）のcanonical schemaを持つのに対し、シナリオ31〜52は3列schema（#・シナリオ・6.32での結果）である——列構成が異なるため別表とする。両者は21章冒頭で述べたとおり内容として矛盾しない。

| # | シナリオ | 6.32での結果 |
|---|---|---|
| 31 | `record_not_applicable()`のNOT_APPLICABLE durable ACK確認後、lock解放が`Exception`（`OSError`に限らない任意の型）で失敗する | `CommitAwareResult(acknowledged=True, cleanup_diagnostics=(...))`が返り、`record_not_applicable()`は成功を返す。当該operationは`NOT_APPLICABLE`のまま維持され、再びapplicable/unknown扱いされない（9.9.7節） |
| 32 | `record_confirmed()`のCONFIRMED_SUCCESS durable ACK確認後、lock解放が失敗する | 成功を返す。reconciliationはdurable`CONFIRMED_SUCCESS`をauthoritativeに扱う（13章） |
| 33 | `record_attempted()`のATTEMPTED ACK後・IO_ARMED ACK前（`transition_to_io_armed()`呼び出し中）に例外が発生する——この呼び出しはdecorated`upload()`内部、すなわち`orchestrator.apply()`が既にgenerate()を終え実行中の状態から発生する（`orchestrator.apply()`自体はこの時点で既に呼ばれている。「呼び出し元がorchestrator.apply()を呼ばない」という記述は誤り） | `commit_state["committed"]`は`False`のまま。pre-commit failureとして扱われ、元の例外がdecorated`upload()`→`orchestrator.apply()`→`ArticleFeaturedMediaRuntime.apply()`のtry/exceptへそのまま伝播する（decide_image_generation_fallback()によるCONTINUE/PROPAGATE判断、15.4節既存ロジック）。IO_ARMED ACKが確定していないため、いずれの判断でもmain.py側は`record_confirmed()`を呼ばない。durable stateは「PREPARED + ATTEMPTED」のまま——`SAFE_TO_CONTINUE`（safe pre-I/O）として分類される（9.9.5節と整合） |
| 34 | post-commit cleanup（lock解放）の**捕捉処理自体**（`_build_cleanup_diagnostic()`または`_log_cleanup_diagnostics_if_any()`）が例外を送出する | いずれも自己防御的に`try/except Exception: pass`（または文字列化失敗時のfallback）を持つため、外部へ伝播しない |
| 35 | pre-commit failure（例：ステップ2のPREPARED create ACK失敗）の直後、cleanup（lock解放）も失敗する | `_try_release_ignoring_result()`がcleanup失敗を握りつぶし、元のpre-commit失敗（`MediaUploadSafetyIOError`）がそのまま送出される。cleanup失敗が「実は成功だった」ように見せかけることはない |
| 36 | あるidentity Xのlockがpost-commit cleanup失敗によりstaleのまま残存する状態で、別のidentity Yへの`record_attempted()`を呼ぶ | identity-scoped lock（27章）のため、Yの操作はXのstale lockから一切影響を受けない |
| 37 | `record_confirmed()`のbody内、`commit_state["committed"] = True`設定後・`commit_state["value"]`への代入や`return`が完了する前に、（理論上の防御シナリオとして）通常のExceptionが発生する | `_run_with_commit_aware_lock()`のexcept節が`commit_state["committed"]`を確認し`True`と判定。`acknowledged=True`・`value=commit_state["value"]`（未設定なら`None`）・`cleanup_diagnostics`にsecret-safeな診断を格納して返す。呼び出し元は成功として扱う |
| 38 | `body`の実装に契約違反があり、`commit_state["committed"]`を`True`にしないまま正常returnしてしまう（実装バグを模擬） | `-O`/`PYTHONOPTIMIZE`実行下でも`MediaUploadSafetyImplementationContractError`が確実に送出される（`assert`ではなく明示的な`if`文で検査するため）。lockはcleanupされ（結果は無視）、呼び出し元は失敗として扱う |
| 39 | `record_not_applicable()`のbody内、`applicability_store.create()`のACK確認**直後**に`commit_state["committed"] = True`を設定した**後**、`NotApplicableMediaUploadSafetyRecord`の構築（戻り値構築）が例外を送出する | `commit_state["committed"]`は既に`True`のため、helperのexcept節が`acknowledged=True`を維持する（シナリオ37と同型、対称性の確認） |
| 40 | 4メソッド（`record_prepared()`含む）いずれかのbody内で、`commit_state["committed"] = True`設定後に`KeyboardInterrupt`が発生する | commit_state["committed"]の値に関わらず、cleanup（lock解放）をbest-effortで試行した上で、**`KeyboardInterrupt`をそのまま再送出する**（成功へ変換しない）。呼び出し元・上位のプロセス制御へ正しく伝播する（`_run_with_commit_aware_lock()`は4メソッド共通のヘルパーであるため、`record_prepared()`にも無改造で同一契約が適用される） |
| 41 | 4メソッド（`record_prepared()`含む）いずれかのbody内で、`commit_state["committed"] = True`設定前（pre-commit）に`SystemExit`が発生する | cleanupをbest-effortで試行した上で、`SystemExit`がそのまま再送出される（pre-commit経路・post-commit経路のいずれでもBaseException系は必ず伝播する。`record_prepared()`のPREPARED ACK前も同一のpre-commit経路として扱われる） |
| 42 | post-commit cleanup失敗（lock解放失敗、またはbody側post-commit例外）が発生し、その例外メッセージに（テストのため意図的に）認証情報・URL・記事本文相当の文字列を含める | `CleanupDiagnostic`には例外の型名（`exception_type`）・`reason_code`・`operation_kind`・`effect_site`・`occurred_at`のみが記録され、注入した秘密情報相当の文字列がログ・診断情報のいずれにも一切含まれないことを確認する |
| 43 | post-commit経路で、`_build_cleanup_diagnostic()`内の`identity.operation_kind.value`アクセス自体が（例えば`identity`が想定外の型である等で）例外を送出する | `_build_cleanup_diagnostic()`の個別フィールドtry/exceptにより`operation_kind=None`へfallbackし、関数全体としては正常にCleanupDiagnosticを返す。呼び出し元（helper）へは例外が伝播しない |
| 44 | post-commit経路で、`CleanupDiagnostic(...)`のdataclass構築自体が例外を送出する | `_build_cleanup_diagnostic()`の最終防衛線が作動し、**同じコンストラクタへ依存せず**診断情報なし（`None`）を返す。helperへは例外が伝播しない |
| 45（段1失敗の起点） | `record_not_applicable()`のbody内、`commit_state["committed"] = True`設定後、`NotApplicableMediaUploadSafetyRecord`の構築が例外を送出し、`commit_state["value"]`が`None`のままhelperから`CommitAwareResult(acknowledged=True, value=None, ...)`が返る | `_value_or_recover()`段1（`outcome.value`）が`None`のため段2（`_read_all()`）へ進み、durable state（既にNOT_APPLICABLEとしてACK済み）から権威あるrecordを再取得する。公開メソッド`record_not_applicable()`は有効な`MediaUploadSafetyRecord`を返し、`None`を返さない |
| 46 | シナリオ45と同様の状況が`record_prepared()`・`record_attempted()`・`record_confirmed()`でも発生する | 同様に段2がdurable stateから復旧する。4メソッドいずれも`None`を返す経路を持たず、かつ各メソッド固有のsemantic kind（`PreparedMediaUploadSafetyRecord`等）以外を返す経路も持たない（25章#40） |
| 47 | 段2（`_read_all()`）を実行しても、（理論上到達しないはずだが）durable stateが見つからない・`to_safety_record()`が`None`を返す | 例外を送出せず、段3（`_minimal_safety_record()`）へフォールスルーする。追加I/Oなしで合成されたrecordが返る |
| 48 | post-commit cleanup（lock解放）自体が失敗し（stale lock発生）、同一メソッド呼び出し内で戻り値構築も失敗する（複合シナリオ） | `_value_or_recover()`段2の`_read_all()`呼び出しはlockを取得しないため、stale lockの影響を受けずdurable stateを正しく読み直せる。`record_*()`は有効なrecordを返す |
| 49 | `CleanupDiagnostic`クラス自体が常に例外を送出するよう仕込む | `_build_cleanup_diagnostic()`が`None`を返し、`_run_with_commit_aware_lock()`は引き続き`acknowledged=True`のCommitAwareResultを返す（`cleanup_diagnostics`は空タプルまたは他の診断のみを含む） |
| 50 | 段2（`_read_all()`）自体が、一時的なI/Oエラー・parse失敗・複数storeにまたがる部分観測（`MediaUploadSafetyContractViolationError`含む）等、任意の理由で例外を送出する | `_value_or_recover()`がこの例外を捕捉し、段3（`_minimal_safety_record()`）へフォールスルーする。呼び出し元へ例外は伝播しない |
| 51 | `_minimal_safety_record()`が呼ばれる状況で、`now_utc_iso()`自体が例外を送出する | `updated_at=""`にfallbackし、`_minimal_safety_record()`自体は例外を送出せず、合成されたrecordを返す |
| 52 | `_build_cleanup_diagnostic()`の実装（9.9.4.3節）を、構文的に正しいPythonコードとして実装できることを確認する（`return None`後にorphanなコード片が存在しない） | コードレビューでの静的確認によりPASSすること |

---

## 22. Exact Integration Points

### 22.1 新設（`side_effect_safety`パッケージ、内容更新）

- `src/side_effect_safety/media_upload_safety_coordinator.py`（9.9.4節）
- `src/side_effect_safety/commit_aware_lock.py`（`_run_with_commit_aware_lock()`・`CommitAwareResult`、9.9.4節、`wordpress_draft_state`からも共有利用、9章）
- `src/side_effect_safety/media_upload_applicability_store.py`
- `src/side_effect_safety/media_upload_attempt_context_store.py`
- `src/side_effect_safety/media_upload_context_phase.py`
- `src/side_effect_safety/media_upload_safety_coordinator_lock.py`（27章、identity-scoped化）
- `src/side_effect_safety/errors.py`
- `src/side_effect_safety/media_upload_write_ahead_capability.py`（`WriteAheadAwareMediaUploadCapability`、22.3.2節）
- `src/side_effect_safety/media_upload_write_ahead_wiring.py`（`MediaUploadWriteAheadAdapters`・`build_protected_featured_media_runtime()`、22.3.2節）
- `_extract_confirmed_media_id()`（15.5節）

### 22.1b 新設（`wordpress_draft_state`パッケージ）

- `src/wordpress_draft_state/wordpress_draft_record.py`（`WordPressDraftRecord`、9.2節）
- `src/wordpress_draft_state/wordpress_draft_state_store.py`（`WordPressDraftStateStore`・`JsonWordPressDraftStateStore`、9.3節。atomic write契約は`retry_lineage_store.py`のtempfile→fsync→os.replaceパターンをそのまま踏襲する、27.2節）
- `src/wordpress_draft_state/wordpress_draft_state_store_lock.py`（`WordPressDraftStateStoreLock`、27.1〜27.4節、identity-scoped）
- `src/wordpress_draft_state/wordpress_draft_state_manager.py`（`WordPressDraftStateManager`、9.5節）
- `src/wordpress_draft_state/errors.py`（`WordPressDraftStateIOError`・`WordPressDraftStateCorruptedError`・`WordPressDraftStateTransitionError`、9.6節）

### 22.1c 既存`retry_lineage`パッケージへの直接変更（直接変更方式・案B）

以下が変更対象ファイルである：

- `src/retry_lineage/retry_lineage_disposition.py`：`RetryLineageDisposition`に`HUMAN_REVIEW_REQUIRED = "human_review_required"`を追加（現状`SUCCEEDED`/`FAILED`/`NOT_ACTIONED`の3値のみ）。
- `src/retry_lineage/retry_lineage_target_resolution.py`：`resolve_final_disposition()`（13章）を新設し、既存の`decide_disposition()`/`disposition_from_categories()`は**無変更のまま**内部から呼び出す（13章）。
- `src/retry_lineage/retry_lineage_manager.py`：`mark_terminal()`の呼び出し元（`RetryExecutor.execute()`・`_reconcile_all_locked()`、15.1〜15.2節）が`resolve_final_disposition()`の結果を渡すよう配線。`open_next_attempt()`の既存ガードは、16章が定める`hrr_authorized`判定を追加した形へ**必ず拡張しなければならない**——`HUMAN_REVIEW_REQUIRED`は`terminal_disposition not in (FAILED, NOT_ACTIONED)`という既存ガードのタプルに含まれないため、ガードを無改修のままにするとHRRは常に拒否され続け、17章が定める`RETRY_ALLOWED`後の許可（`hrr_authorized`が真の場合のみ次attemptを開く）が構造的に到達不能になる。既存ガードをそのまま維持してよい、という選択肢は存在しない——16章のコード例（`hrr_authorized`判定・authorized分岐）が本ファイルへの必須の変更内容である。`_reconcile_all_locked()`のopened_countループ側フィルタ（`terminal_disposition in (FAILED, NOT_ACTIONED)`のみを対象）は無改修のまま維持し、自動sweepからのHRR到達を引き続き構造的に排除する（16章「呼び出し元での二重ガード」）。`resolve_human_review()`・`_resolve_human_review_locked()`・`open_next_attempt_after_human_review()`（17.2・16章）を本ファイルへ新設する。**`mark_execution_started()`**（9.5章、既存メソッド）は、既存の処理（`phase`を`EXECUTION_STARTED`へ遷移・`attempt_count`を+1・`membership`追記・`transition_history`追記）と**同一の`save()`呼び出し内**で、`record.human_review_resolution is not None and record.human_review_resolution.opened_attempt_no == attempt_no`の場合にのみ`record.human_review_resolution = None`へクリアする1条件分岐を追加する（17.2節、crash-resumable markerの解放）。この条件が偽の場合（通常のFAILED/NOT_ACTIONED経路、または`human_review_resolution`が`None`の場合）は既存の処理に一切影響しない。
- `src/retry_lineage/retry_lineage_record.py`：`RetryLineageRecord.side_effect_contract_version: int | None`フィールド追加（18章）。deserialization（`RetryLineageDisposition(data["terminal_disposition"])`）は汎用Enum構築のため無改修で新値に対応する。**HRR用の追加（17章）**：本ファイルへ`HumanReviewResolution`（Enum、`RETRY_ALLOWED = "retry_allowed"`／`ABANDONED = "abandoned"`）と`HumanReviewResolutionRecord`（`@dataclass`、`resolution: HumanReviewResolution`・`actor: str`・`note: str | None`・`resolved_at: datetime`・`opened_attempt_no: int | None = None`の5フィールド、`consumed`フィールドは持たない）を新設する——既存の`RetryAttemptExecutionScope`・`RetryLineageMembershipEntry`・`RetryLineageTransitionEvent`と同じファイルに小さな値型を配置する既存パターンに倣う（新しいモジュールは作らない）。`RetryLineageRecord`へ`human_review_resolution: HumanReviewResolutionRecord | None = None`フィールドを追加する。

  `HumanReviewResolutionRecord.to_dict()`（exact定義）：
  ```python
  def to_dict(self) -> dict:
      return {
          "resolution": self.resolution.value,
          "actor": self.actor,
          "note": self.note,
          "resolved_at": self.resolved_at.isoformat(),
          "opened_attempt_no": self.opened_attempt_no,
      }
  ```

  `HumanReviewResolutionRecord.from_dict()`（exact定義、フィールドごとの変換を1つずつ明記する）：
  ```python
  @classmethod
  def from_dict(cls, data: dict) -> "HumanReviewResolutionRecord":
      opened_attempt_no = data.get("opened_attempt_no")
      if opened_attempt_no is not None and (
          not isinstance(opened_attempt_no, int)
          or isinstance(opened_attempt_no, bool)
          or opened_attempt_no <= 0
      ):
          # 破損データ：Noneでも有効なpositive intでもない値は、値の推測（例：Noneへ
          # 読み替える）を行わずValueErrorとする——新しい例外型は追加しない。
          # JsonRetryLineageStore.get()の既存except節（OSError, ValueError, KeyError）
          # がこれを捕捉し、record全体を読み込み不能（None）として扱う（既存のfail-closed
          # 規律、`RetryLineageDisposition(data["terminal_disposition"])`のEnum構築が
          # 不正値でValueErrorを送出するのと同一の扱い）。
          raise ValueError(
              f"human_review_resolution.opened_attempt_no is neither None nor a "
              f"positive int: {opened_attempt_no!r}"
          )
      return cls(
          resolution=HumanReviewResolution(data["resolution"]),  # closed set外はValueError→fail-closed
          actor=data["actor"],  # 必須。欠落時はKeyError→fail-closed（actor省略を許容しない）
          note=data.get("note"),  # Optional、欠落時はNone
          resolved_at=datetime.fromisoformat(data["resolved_at"]),
          opened_attempt_no=opened_attempt_no,
      )
  ```
  `RetryLineageRecord.to_dict()`は`"human_review_resolution": self.human_review_resolution.to_dict() if self.human_review_resolution else None`。`RetryLineageRecord.from_dict()`は`human_review_resolution=HumanReviewResolutionRecord.from_dict(data["human_review_resolution"]) if data.get("human_review_resolution") else None`（`.get()`により、この新フィールドを持たない既存durableファイル＜pre-6.32 legacy record＞からの読み込みでも`None`へ安全にフォールバックする——既存の`next_eligible_at`/`owner_token`と同型のOptionalフィールド追加パターン）。
- `src/retry_lineage/retry_lineage_results.py`：`ResolveHumanReviewResult`（`@dataclass`、`acknowledged: bool`・`reason: str | None = None`の2フィールド）を新設する——既存の`MarkTerminalResult`と同一の形。
- `src/retry_lineage/__init__.py`：`resolve_final_disposition`・`side_effect_contract_version`関連シンボルに加え、`HumanReviewResolution`・`HumanReviewResolutionRecord`（`retry_lineage_record`より）・`ResolveHumanReviewResult`（`retry_lineage_results`より）を`from ... import`・`__all__`双方へ追加する（既存の`RetryLineageRecord`等と同一の公開パターン）。新規のstore API・CAS・別attempt store・別トランザクション層は一切追加しない——`RetryLineageStore`（`retry_lineage_store.py`）・`RetryLineageStoreLock`（`retry_lineage_store_lock.py`）・`RetryExecutionLock`（`retry_execution_lock.py`）はいずれも無改修のまま、既存の`save()`（whole-record atomic replace）・`_store_lock()`・`execution_lock_path`のみを`resolve_human_review()`・`open_next_attempt_after_human_review()`が利用する（17.2・16章）。
- `src/retry_composition/`（composition層、新設関数のみ）：`retry_after_human_review()`（17.3節、exact定義済み）を新設する。依存方向は`retry_composition → retry_lineage`・`retry_composition → retry_engine`の一方向のみ——`retry_lineage`パッケージ自体は`retry_engine`/`retry_queue`/`scheduler`のいずれもimportしない（既存の依存方向を維持、新規の逆依存を追加しない）。

**回帰確認**：`disposition_from_categories()`（`retry_lineage_target_resolution.py:42-51`）自体は無変更（4章Non-Goals）。既存151/151 E2Eへの影響は28章Regression節で確認する。

### 22.1d `RetryQueueUpdateDecider`改修（HRR用の新しいQueue状態は追加しない）

以下の変更を行う：

- `src/retry_engine/retry_queue_update_decider.py`：`decide()`のシグネチャを`queue_decision_input: RetryQueueDecisionInput`（必須引数、discriminated union）へ変更する（詳細は22.4節）。`LineageAuthoritativeDispositionInput`かつ`terminal_disposition == HUMAN_REVIEW_REQUIRED`の場合も、既存の`RetryQueueUpdateOutcome.FAIL`／`RetryQueueStatus.FAILED`へ合流させる——**`RetryQueueUpdateOutcome`・`RetryQueueStatus`に新しい値（`REVIEW_REQUIRED`等）は追加しない**。**併せて`decide_all(requests: Sequence[RetryQueueDecisionRequest])`（22.4a節）を、単体`decide()`と同一contractの下に置くbatch APIとして改修する。旧1引数`decide_all(execution_results)`は残さない。** `build_queue_decision_input()`（単体、22.4節）・`build_retry_queue_decision_requests()`（batch、22.4a節）のいずれも、呼ぶのは`RetryManager.decide_retry_queue_updates()`（`RetryRuntimeOrchestrator.run_once()`から呼ばれる、22.4a節）のみ。
- `src/retry_engine/retry_queue_removal_executor.py`・`retry_queue_cleanup_decider.py`・`retry_queue_terminal_cleanup_decider.py`・`src/retry_engine/retry_outcome_terminality.py`・`src/retry_queue/retry_queue_status.py`：HRRのためにこれらのファイルを変更しない。HRR終端lineageは既存の`FAIL`／`FAILED`経路をそのまま通り、これら既存コンポーネントは無改修のまま正しく動作する。
- Retry Trigger/Eligibility（`src/retry_enqueue_trigger/retry_enqueue_trigger.py::RetryEnqueueTrigger.enqueue_pending_failures()`、22.1eに詳細）：新規の変更は不要——既存の`lineage`引数によるmembership-first除外が、6.32のHRR terminal lineageに対しても構造的に機能する。

### 22.1e Retry Trigger再enqueue防止の3層防御

「HRR終端のlineageがRetry Triggerによって誤って再enqueueされても実害に至らない」という**Layer 3（defense-in-depth）**に加え、「そもそも再enqueueされない」という**Layer 1（primary contract）**が実ファイル（`src/retry_enqueue_trigger/retry_enqueue_trigger.py`、`src/retry_composition/retry_composition_root.py`）において実際に成立する。§28.-8テスト#4はLayer 1相当の「再enqueueされないこと」を要求する。

**Layer 1（primary contract）：Retry Trigger自体がlineage-trackedなrun_idを候補から除外する**：`RetryEnqueueTrigger.enqueue_pending_failures()`は、`WorkflowMonitorManager.list_status()`が返す`monitor_status in {FAILED, TIMEOUT}`の候補それぞれについて、`self._lineage.find_by_member_run_id(record.run_id) is not None`が真であれば`skipped_lineage_member`として即座に除外し、以降のGuard判定・Queue重複確認・`enqueue()`へは一切進まない（membership-first判定、Release 6.31で新設）。この判定は`terminal_disposition`の値を一切参照しない——**あるrun_idが（disposition問わず）いずれかのlineageのmemberとして記録されている、という事実だけで除外する**ため、HRR終端のlineageの各attempt run_idも構造的にこの除外対象へ含まれる。6.32 contract対象lineageの各attemptは、実行のためには必ず`mark_execution_started()`（membership記録）を経ているため（15.1〜15.2節）、HRR確定に至った時点で該当run_idは既にlineage memberとして記録済みである。
この保護は`self._lineage`が`None`でない場合にのみ有効であるため、Composition Root配線への依存が残る——`src/retry_composition/retry_composition_root.py:145-146`において、production Composition Rootは`RetryEnqueueTrigger(monitor=monitor, queue=queue, history=history, guard=guard, lineage=lineage)`と`lineage`引数を常に明示的に渡す（`lineage=None`で構築される経路はproduction composition rootに存在しない）。

**Layer 2（Queue側のnon-retryable性）**：HRR終端lineageのQueue項目は、22.4節の`decide()`により既存の`RetryQueueUpdateOutcome.FAIL`／`RetryQueueStatus.FAILED`へ合流し（HRR専用のQueue状態は追加しない）、既存の`RetryQueueRemovalExecutor`の`_REMOVABLE_OUTCOMES`（無改修）によりterminal状態としてQueueから除去される。`RetryEnqueueTrigger`自体はそもそもQueue状態ではなくWorkflow Monitor状態（`monitor_status`）とlineage membershipのみを根拠に候補を決定するため、Queue側の状態（`FAILED`）自体がRetry Triggerの再enqueue判定へ入力されることもない。

**Layer 3（defense-in-depth、Layer 1・2が何らかの理由で破られた場合の最終防御）**：Layer 1がバイパスされる状況（例：将来のリファクタリングで`lineage=None`のComposition Rootが誤って追加される、または`find_by_member_run_id()`自体にバグが混入する等）を想定し、それでもHRR終端lineageに対する実際のretry実行が発生しないことを、`claim()`のphaseチェックが独立した防御層として担保する：`RetryManager.retry()`の内部実装`_retry_locked()`が既存lineageに対して呼ぶ`claim()`（`retry_lineage_manager.py:302-312`）は、`record.phase != RetryLineagePhase.READY_ELIGIBLE`の場合に無条件で拒否する。`mark_terminal()`（12章）確定後のlineageは`phase=TERMINAL`のままであり、`phase`を`READY_ELIGIBLE`へ戻せるのは`open_next_attempt()`のみ（自動sweepからは`_reconcile_all_locked()`経由、23章 Reconciliation Priority）——その`open_next_attempt()`自体が、通常は`terminal_disposition in (FAILED, NOT_ACTIONED)`のみを対象とし、`HUMAN_REVIEW_REQUIRED`については明示的な`RETRY_ALLOWED`resolutionが記録されている場合（`hrr_authorized`、16・17章）に限り例外的に許可するガードを持つ。したがって、たとえstale queue entry・実装バグ・raceによりHRR run_idが誤ってenqueueされたとしても、対応するlineageに`RETRY_ALLOWED`resolutionが記録されていない限りphaseは`TERMINAL`のまま変化せず、`claim()`のphaseチェックが機能して実際のretry実行には至らない。

**保証水準の整理**：「HRR終端lineageはLayer 1により正常経路では再enqueueされない」ことを**primary contract**とし、「万一Layer 1がバイパスされても、Layer 3がretry実行そのものを阻止する」ことを**defense-in-depth**として明示的に区別する（Layer 2はQueue側の記録・除去の一貫性を担う）。§28.-8テスト#4は、この3層をそれぞれ独立に検証するテストへ分割する（28.-8節#4・#4b・#4c）。

### 22.1f 新設

2.1a・2.6節が定める統合内容（`workflow_engine_executor.py`/`agent_context.py`/`agent_task.py`/`news_agent.py`）。**`WorkflowEngineManager`/`AgentExecutor`は1回構築・複数回呼び出しされる構造であるため、per-call typed context propagation方式を採用する（constructor-time provider injection方式は不採用）：**

- `src/side_effect_safety/side_effect_execution_mode.py`：`LegacyEntrypoint`・`LegacyExecutionOrigin`・`RetryLineageProtectedExecutionContext`・`LegacyDirectProvenance`・`LegacyDirectExecutionContext`・`RetryLineageProtectedProvenance`（discriminated union、2.1節）・`build_protected_execution_context()`/`build_legacy_direct_provenance()`/`complete_legacy_execution_context()`（factory、2.1a節）・`validate_side_effect_execution_context()`（2.1b節）・`SideEffectExecutionModeContractError`・`ExecutionModeFailureReasonCode`
- `src/ai/agent_context.py`：`AgentContext`へ`side_effect_execution_context: "SideEffectExecutionContext | None" = None`フィールドを追加（`task.params`/`event.metadata`とは独立した専用channel、2.6節）
- `src/workflow_engine/workflow_engine_context.py`：`WorkflowEngineContext`へ`side_effect_execution_provenance`フィールドを追加（`member_run_id`未確定のまま伝播するのは2.1a節の`SideEffectExecutionProvenance`型の値であり、`correlation_metadata`とは別の新規フィールドとして、History/相関用途とside-effect safety identityを分離する。2.6節コード例（`WorkflowEngineContext（新規field: side_effect_execution_provenance）`）と整合させる）
- `src/workflow_engine/workflow_engine_manager.py`：`WorkflowEngineManager.run()`のシグネチャへ`side_effect_execution_provenance`引数を追加し（2.6節コード例と同一名）、`WorkflowEngineContext`へそのまま渡す（構築時＜`from_env()`/`from_config()`＞ではなく、呼び出しごとの引数として扱う——construction時にmodeを注入する設計は採用しない）
- `src/workflow_engine/workflow_engine_executor.py`：`AgentContext`構築箇所（323〜331行目）にて、`context.side_effect_execution_provenance`（`WorkflowEngineContext`が保持するのは未完成のprovenanceであり、`side_effect_execution_context`という名の完成済みフィールドは存在しない）が`RetryLineageProtectedProvenance`の場合のみ、このexecutor自身が発行する`run_id`（既存の`AgentContext.run_id`と同一値）でprotected factory（`build_protected_execution_context()`、2.1a節）を呼び、`RetryLineageProtectedExecutionContext`へ完成させたうえで、`AgentContext(..., side_effect_execution_context=completed_context)`（`LegacyDirectExecutionContext`の場合は既に完成形のためfactoryを再度呼ばずそのまま渡す）を追加（2.6節）
- `src/ai/news_agent.py::NewsAgent.act()`：既存コード（`self._runner.run(params=context.task.params)`）へ`side_effect_execution_context=context.side_effect_execution_context`を追加引数として渡すよう変更
- `src/pipeline/news_pipeline_runner.py::NewsPipelineRunner.run()`：シグネチャへ`side_effect_execution_context`引数を追加し、`_serialize_execution_context()`（14.2節）で環境変数へ変換した上で`subprocess.run(..., env=...)`へ渡す
- `main.py`：起動時に`_parse_execution_context_from_env()`（14.3節）で環境変数からtyped discriminated unionを解決する。`WordPressOutput`（呼び出し箇所A、15.7節）へはこのインスタンスをそのまま構築時に渡す。呼び出し箇所B（`ArticleFeaturedMediaRuntime`、15.4節）へは**Foundationのconstructor/apply()へ直接渡すことはなく**、同一インスタンスは6.32 integration wiring層（`MediaUploadWriteAheadAdapters`・`build_protected_featured_media_runtime()`、22.3.2節）へ渡す
- `src/outputs/wordpress_output.py`：`WordPressOutput.__init__()`へ`side_effect_execution_context`（必須引数）・`draft_state_manager`引数を追加、`save()`をExplicit Execution Mode対応へ改修（15.7節）
- `src/ai/ai_publish_service.py`：`AiPublishService.run()`/`_process()`/`_post()`のシグネチャへ`side_effect_execution_context`引数を追加（コンストラクタではなく呼び出しごとの引数、15.6節）
- `src/pipeline/publish_pipeline_runner.py::PublishPipelineRunner.run()`：シグネチャへ`side_effect_execution_context`引数を追加し、`AiPublishService.run(article_id=..., side_effect_execution_context=...)`へそのまま渡す
- `src/ai/agent_manager.py::AgentManager.run()`：シグネチャへ`legacy_provenance: LegacyDirectProvenance`引数を追加。既存のfan-outループ（150〜161行目、構造は無変更）内で、各`executor`ごとに2.3節の対応表（`AgentManager.from_config()`が構築時点で確定させたAgent型）から`legacy_execution_origin`を決定し、`complete_legacy_execution_context(legacy_provenance, legacy_execution_origin)`を個別に呼んで、`side_effect_execution_context=completed_context`を各`AgentContext`へ設定する（2.6節「Legacy経路（AgentManager経由）の2段階provenance」参照、詳細な擬似コードあり）。対応表に存在しないAgent型の場合は`side_effect_execution_context=None`のまま構築し、推測しない。
- `src/ai/agent_manager.py::AgentManager.from_config()`：各Agent型を構築する既存箇所（107-142行目）で、`legacy_execution_origin`対応表（2.3節）を実装するための内部mapping（`AgentExecutor`インスタンスと対応する`LegacyExecutionOrigin`の組）を、Agent型が確定した時点の情報から構築する（新規、`self._agent.name()`という別目的の文字列には依存しない）。
- `scripts/run_news_agent.py`・`scripts/run_workflow_trigger_agent.py`・`scripts/run_publish_trigger_agent.py`・`scripts/run_review_trigger_agent.py`：`AgentManager.from_config(config)`構築直後に`legacy_provenance = build_legacy_direct_provenance(LegacyEntrypoint.RUN_XXX)`（起動元scriptに対応する値）を構築し、`manager.run(task, dry_run=..., legacy_provenance=legacy_provenance)`へ渡す。
- `scripts/run_ai_publish.py`：`AiPublishService.from_env().run(article_id=...)`呼び出しに`side_effect_execution_context=complete_legacy_execution_context(build_legacy_direct_provenance(LegacyEntrypoint.RUN_AI_PUBLISH), LegacyExecutionOrigin.AI_PUBLISH_DIRECT)`を明示的に追加
- `scripts/run_ai_workflow.py`：`WorkflowRunner.from_config(config).run(article_id=..., dry_run=...)`呼び出しに`side_effect_execution_context=complete_legacy_execution_context(build_legacy_direct_provenance(LegacyEntrypoint.RUN_AI_WORKFLOW), LegacyExecutionOrigin.AI_WORKFLOW_DIRECT)`を明示的に追加（22.3.11・22.3.12節）
- `src/workflow_engine/workflow_engine_manager.py`（`.run()`の呼び出し元側）：`scripts/run_workflow_engine.py`のRetry Lineage外呼び出し（`--job-id`手動指定・Scheduler経由）は、`WorkflowEngineManager.run(event, dry_run=..., side_effect_execution_provenance=complete_legacy_execution_context(build_legacy_direct_provenance(LegacyEntrypoint.RUN_WORKFLOW_ENGINE_DIRECT), LegacyExecutionOrigin.WORKFLOW_ENGINE_DIRECT))`を明示的に渡す
- `src/ai/workflow_runner.py::WorkflowRunner.run()`：シグネチャへ`side_effect_execution_context`引数を追加し、`WorkflowContext`構築時（121行目）へそのまま渡す。
- `src/ai/workflow_context.py::WorkflowContext`：`side_effect_execution_context: "SideEffectExecutionContext | None" = None`フィールドを追加。
- `src/ai/workflow_step_executor.py::PublishStepExecutor.execute()`：既存コード（`report_path = self._service.run(article_id=context.article_id)`、271行目）へ`side_effect_execution_context=context.side_effect_execution_context`を追加引数として渡すよう変更。
- `src/pipeline/workflow_pipeline_runner.py::WorkflowPipelineRunner.run()`：シグネチャへ`side_effect_execution_context`引数を追加し、`WorkflowRunner.run(article_id=..., dry_run=..., side_effect_execution_context=...)`へそのまま渡す。
- `src/ai/workflow_trigger_agent.py::WorkflowTriggerAgent.act()`：`self._runner.run(params=context.task.params)`へ`side_effect_execution_context=context.side_effect_execution_context`を追加引数として渡すよう変更（`NewsAgent.act()`と同型）。
- `src/retry_engine/retry_executor.py::RetryExecutor.execute()`：`RetryExecutor.execute()`時点では`member_run_id`がまだ確定していないため（2.1a節、`WorkflowEngineExecutor`が自ら発行する`run_id`と同一値、10.2節）、この段階で構築できるのは完成形の`SideEffectExecutionContext`ではなく、`lineage.root_run_id`・`claim.attempt_no`・`record.side_effect_contract_version`の3フィールドのみを持つ`RetryLineageProtectedProvenance`（2.1a節のpre-context）である。`RetryExecutor`は`RetryLineageProtectedExecutionContext`を直接構築せず（2.2節）、このprovenanceを`self._engine.run(..., side_effect_execution_provenance=...)`へ渡す（既存の`correlation_metadata`構築とは独立した、並行する構築処理を追加）。`member_run_id`の補完・`RetryLineageProtectedExecutionContext`への完成は、authoritative `member_run_id`を確定できる唯一の地点である`WorkflowEngineExecutor`のprotected factory呼び出し（上記`workflow_engine_executor.py`の項、2.6節）でのみ行われる——`RetryExecutor`が`member_run_id`をmetadata/params等から推測して完成済みcontextを組み立てることはない
- `src/retry_composition/retry_composition_root.py`：上記`RetryExecutor`の構築に必要な依存関係の配線を確認（新規injectionなし、既存の`RetryLineageManager`参照で足りる）

### 22.2 No Bypass Proof

**`orchestrator.apply()`呼び出し箇所はprocess内で単一である**が、**そこへ至るtop-level entry point（起動スクリプト）は単一ではない**。`scripts/`配下には以下の複数entry pointが存在する：

| Entry point | 経路 | Retry Lineage経由か |
|---|---|---|
| `scripts/run_retry_runtime.py` | `RetryCompositionRoot`→`RetryRuntimeOrchestrator`→`RetryExecutor.execute()`→`WorkflowEngineManager.run()` | ✅ 経由する（2.2節（RETRY_LINEAGE_PROTECTED）） |
| `scripts/run_workflow_engine.py`（`--job-id`手動指定／Scheduler経由） | `WorkflowEngineManager.run()`を直接呼ぶ | ❌ 経由しない（2.3節（LEGACY_DIRECT）） |
| `scripts/run_news_agent.py` / `scripts/run_publish_trigger_agent.py` | `AgentManager.run()`→`NewsAgent`/`PublishTriggerAgent`を独自構築 | ❌ 経由しない（2.3節（LEGACY_DIRECT）） |
| `scripts/run_ai_publish.py` | `AiPublishService.from_env().run()`を直接呼ぶ（PUBLISH側のみ） | ❌ 経由しない（2.3節（LEGACY_DIRECT）） |

**6.32 Retry Lineage contract対象production path（2.2節（RETRY_LINEAGE_PROTECTED）、`scripts/run_retry_runtime.py`経由）について、bypassなし。** すなわち、Retry Lineage context下で実行される限り、`WordPressOutput.save()`のPOST（呼び出し箇所A、NEWS側WordPress draft、15.7節）・`orchestrator.apply()`（呼び出し箇所B、media upload、15.4節）・`WordPressDraftClient.post_draft()`（呼び出し箇所C、PUBLISH側WordPress draft、15.6節）のいずれも、必ず対応するCoordinator/Store経由のwrite-ahead ACKを通過する。`orchestrator.apply()`が担うのは呼び出し箇所Bのみであり、呼び出し箇所Aは`WordPressOutput.save()`内の`requests.post()`である。2.3節（LEGACY_DIRECT）の経路（Retry Lineage context外）は、この保証の対象外であり、6.32以前と同じlegacy behaviorのまま動作する——これは欠陥ではなく、2章で明記したExplicit Side-Effect Execution Mode契約の一部である。

**write-ahead ATTEMPTEDが必ずShared Coordination Boundaryを通ることの証明（2.2節（RETRY_LINEAGE_PROTECTED）の範囲に限定）**：

- 15.4節の設計により、上記path上で実際のexternal media upload（`media_uploader.upload()`、`ArticleFeaturedMediaOrchestrator.apply()`内部、22.3.2節参照）が呼ばれる**唯一の箇所**は`ArticleFeaturedMediaRuntime.apply()`が起点となる呼び出しchainのみである。**write-ahead呼び出し（`media_upload_coordinator.record_attempted()`のIO_ARMED ACK）は`upload()`の直前に正確に配置される（22.3.2節——write-ahead-aware decoratorが`upload()`自体を包む形で実装されるため、境界の精度は実装方式そのものによって保証される）。**
- `ArticleFeaturedMediaRuntime`のコンストラクタは`__init__(self, root)`（15.4.1節・22.3.2節、Foundation zero-diff）のみを保持し、`MediaUploadSafetyCoordinator`・`ArticleMediaUploadStateManager`のいずれのインスタンスへの参照も直接受け取らない。`MediaUploadSafetyCoordinator`への参照は、6.32 integration層（`media_upload_write_ahead_wiring.py::build_protected_featured_media_runtime()`、22.3.2節）が構築する`WriteAheadAwareMediaUploadCapability`（decorator、Orchestratorへ`media_uploader`引数として渡される）が保持するのみであり、`ArticleFeaturedMediaRuntime`／`ArticleFeaturedMediaOrchestrator`／`ArticleFeaturedMediaCompositionRoot`のいずれの公開フィールドにも`MediaUploadSafetyCoordinator`は現れない（DI wiring discipline）。
- `article_featured_media_orchestrator.py`（`ArticleFeaturedMediaOrchestrator`）自体も同様に、`ArticleMediaUploadStateManager`への参照を持たない（無変更、9.9.3節の対象外——このファイルはwrite-aheadに関与しない、単にupload実行のみを担う既存コンポーネントのまま。22.3.2節で確定した注入方法は、このファイル自体への変更を伴わない）。
- `article_media_upload_state`パッケージは1.4節のとおり他に呼び出し元を持たない。**6.32 integration層（`media_upload_write_ahead_wiring.py`、22.3.2節。`article_featured_media_composition_root.py`自体への変更を伴わない）が、`ArticleMediaUploadStateManager`インスタンスを`MediaUploadSafetyCoordinator`にのみ渡し、他のいかなる公開APIからもこのManagerインスタンスへ到達できないよう組み立てる**ことを、6.32の実装契約として定める。

**構造的限界の正直な記載（本節の記述自体が根拠であり、§21への参照は不要）**：Pythonの言語仕様上、`ArticleMediaUploadStateManager`を直接importして新しいインスタンスを構築し、Coordinatorを経由せず呼び出すコードを将来誰かが書くこと自体を、型システムやアクセス制御で完全に禁止することはできない。本証明が保証するのは、**2.2節（RETRY_LINEAGE_PROTECTED）の経路について、6.32時点でのComposition Root配線が例外なくCoordinator経由になっている**ことであり、将来の実装変更がこの規律を破らないことは、コードレビュー・22.1節のExact Integration Pointsに対する変更監査（既存の`retry_outcome_terminality.py`の「新しいenum値追加時は参照箇所を全数監査する」という恒久ルールと同種の運用規律）に委ねる。2.3節（LEGACY_DIRECT）の経路については、本証明の対象外であることを2.7節のAccepted Residual Riskとして明記済み。

### 22.3 Exact Integration Points

本節は、Release 6.32 architecture（本書2〜19章）が要求する統合内容を、`src/`配下の実在するfile/moduleに対して定める。normative referenceのauthorityは常に「file + symbol」（例：`retry_lineage_manager.py::_reconcile_all_locked()`）であり、行番号を伴う場合もそれは補助的な位置づけとする。

#### 22.3.1 NEWS WordPress（呼び出し箇所A、15.7節）

- `src/outputs/wordpress_output.py`（`WordPressOutput.__init__(self, site_url, username, app_password)`・`save(self, article)`）：`__init__()`へ`side_effect_execution_context`（必須）・`draft_state_manager`（Optional）引数を追加し、`save()`冒頭で`validate_side_effect_execution_context()`を呼んでから`requests.post()`前後にwrite-ahead呼び出しを挿入する（15.7節）。
- `src/outputs/manager.py`（`OutputManager.save_all()`）：シグネチャ変更は行わない（15.7節、WordPress固有知識を持たない汎用dispatcherのまま維持）。

#### 22.3.2 MEDIA_UPLOAD

**既存の構築chain（Foundation、無変更）**：`ArticleFeaturedMediaRuntime.__init__(self, root)`（`article_featured_media_runtime.py:106-107`、`root`をduck-typedに保持するのみ）は、`ArticleFeaturedMediaCompositionRoot.from_env()`（`article_featured_media_composition_root.py:72-101`）が構築する`root`を受け取る。`from_env()`内部（84-99行目）は`WordPressMediaUploader.from_env()`を`GeneratedImageWordPressMediaUploader`（既存、`GeneratedImageUploadCapability`Protocolの既存実装）でラップし、`ArticleFeaturedMediaOrchestrator(image_generator=..., media_uploader=...)`（`article_featured_media_orchestrator.py:44-56`、`media_uploader`引数は`GeneratedImageUploadCapability`Protocol型）へ渡す。`apply()`（`article_featured_media_orchestrator.py:58-74`）は`self._media_uploader.upload(generated_image, filename)`（73行目）を呼ぶ——この`media_uploader`引数こそが既存のDependency Inversion拡張点であり、6.32のdecorator注入点である。

**6.32が新設する箇所（いずれもFoundation 3ファイル——`article_featured_media_runtime.py`／`article_featured_media_orchestrator.py`／`article_featured_media_composition_root.py`——への変更を伴わない）**：

- 新設 `src/side_effect_safety/media_upload_write_ahead_capability.py`：`WriteAheadAwareMediaUploadCapability`（`GeneratedImageUploadCapability`Protocolの実装、Duck Typing）。コンストラクタで`inner: GeneratedImageUploadCapability`（既存の`GeneratedImageWordPressMediaUploader`インスタンス）・`media_upload_coordinator: MediaUploadSafetyCoordinator`・`identity: SideEffectOperationIdentity`・`member_run_id: str`を受け取る。`upload(self, image, filename) -> MediaUploadResult`は、`media_upload_coordinator.record_attempted(identity, member_run_id)`（IO_ARMED durable ACK確認、9.9.4.4節）を呼んだ**後にのみ**`self._inner.upload(image, filename)`（真の外部I/O）を呼び、その結果をそのまま返す。`record_confirmed()`はここでは呼ばない（15.5.1節、呼び出し元の責務）。
- 新設 `src/side_effect_safety/media_upload_write_ahead_wiring.py`：
  - `MediaUploadWriteAheadAdapters`（frozen dataclass、プロセス起動時に1回だけ構築）：`enabled: bool`・`image_generator: AIImageGenerator | None`・`base_media_uploader: GeneratedImageUploadCapability | None`・`image_mime_type: str | None`を保持する。`from_env()`は`ArticleFeaturedMediaCompositionRoot.from_env()`（84-99行目）と同一の環境変数読み取り・adapter構築ロジックを**独立に複製する**（`ImageGenerationConfig.from_env()`→Gate OFF時は`enabled=False`のみ返す→Gate ON時は`OpenAIImageGenerator.from_env()`・`WordPressMediaUploader.from_env()`・`GeneratedImageWordPressMediaUploader`を構築）——`ArticleFeaturedMediaCompositionRoot.from_env()`自体は呼ばない（呼ぶとdecorator非注入のOrchestratorが確定してしまうため）。credential解決・Fail Fastの挙動（ValueError無変換伝播）は既存`from_env()`と同一に保つ。
  - `build_protected_featured_media_runtime(adapters, media_upload_coordinator, identity, member_run_id) -> ArticleFeaturedMediaRuntime`：記事1件ごとに呼ばれる。`adapters.enabled`が`False`なら`ArticleFeaturedMediaRuntime(ArticleFeaturedMediaCompositionRoot(orchestrator=None, image_mime_type=None))`相当（Gate OFF時の既存`from_env()`と同一構造）を返す。`True`なら`WriteAheadAwareMediaUploadCapability(adapters.base_media_uploader, media_upload_coordinator, identity, member_run_id)`で`adapters.base_media_uploader`をラップし、新規`ArticleFeaturedMediaOrchestrator(image_generator=adapters.image_generator, media_uploader=decorated_uploader)`を構築し、`ArticleFeaturedMediaCompositionRoot(orchestrator=orchestrator, image_mime_type=adapters.image_mime_type)`（`from_env()`を経由せず、公開dataclassコンストラクタを直接呼ぶ）で包み、`ArticleFeaturedMediaRuntime(root)`を返す。identityは`upload(image, filename)`というProtocol署名に含められないため（呼び出しごとの引数として渡す経路がない）、記事ごとにOrchestrator／CompositionRoot／Runtimeを新規構築することでdecoratorへ束縛する——安価なobject構築のみで追加I/Oは発生しない（adapter自体はプロセス起動時に1回だけ構築済みのものを再利用する）。
  - **`FeaturedMediaSideEffectBinding`（closed discriminated union、以下が最終確定型名——alias/alternative命名は本書内に残さない）**：

    ```python
    @dataclass(frozen=True)
    class ProtectedFeaturedMediaSideEffectBinding:
        """protected（RetryLineageProtectedExecutionContext）実行時のみ構築される。
        4 safety methods（record_not_applicable/record_prepared/record_attempted/
        record_confirmed）を呼びうる経路は、このbindingの下でのみ有効。
        runtime自体はこのbindingに直接保持しない——`adapters`・`media_upload_coordinator`
        が、記事ごとに`build_protected_featured_media_runtime()`（本節、下記の
        runtime builder/wiring capability）を呼ぶために必要十分な材料であり、
        `_apply_featured_media_step()`はこの2フィールド＋記事単位の`identity`／
        `member_run_id`から、呼び出しのたびに明示的にruntimeを構築する——
        runtime源泉はbinding側から一意に導出可能である（orphanな`runtime`引数は
        持たない）。"""
        context: "RetryLineageProtectedExecutionContext"
        media_upload_coordinator: "MediaUploadSafetyCoordinator"
        adapters: "MediaUploadWriteAheadAdapters"

    @dataclass(frozen=True)
    class LegacyFeaturedMediaSideEffectBinding:
        """legacy（LegacyDirectExecutionContext）実行時のみ構築される。
        media_upload_coordinator/adaptersへの参照自体を保持しないため、4 safety
        methods zero-call・protected dependency構築ゼロが構造的に保証される。
        `runtime`は既存（6.31以前）のlegacy起動時構築済み`ArticleFeaturedMediaRuntime`
        （main.py起動時、記事ループの外側で`ArticleFeaturedMediaRuntime.from_env()`
        により1回だけ構築、下記main.py配線）をそのまま保持する——legacy modeは
        記事ごとの再構築を行わない（既存6.31以前の挙動を無変更のまま維持する）。"""
        context: "LegacyDirectExecutionContext"
        runtime: "ArticleFeaturedMediaRuntime"

    FeaturedMediaSideEffectBinding = (
        "ProtectedFeaturedMediaSideEffectBinding | LegacyFeaturedMediaSideEffectBinding"
    )


    class FeaturedMediaPropagatedFailure(Exception):
        """`_apply_featured_media_step()`がPROPAGATE対象の例外（15.4節の既存
        `classify_propagated_failure()`分類ロジック、v6.25.0・無変更）を内部で
        分類した結果を、main.py記事ループ（22.3.13節）まで運ぶための6.32
        integration層専用exception。legacy/protectedいずれの分岐でも、runtime
        構築後の`runtime.apply(article)`呼び出しを共通に包む単一のtry/exceptから
        送出される（本節下記）。運ぶのは`FeaturedMediaFailureObservation`
        （Foundation型、無変更）のみであり、元のraw exceptionオブジェクト・
        そのmessage・tracebackへの参照は一切保持しない——新しいobservation
        schemaの追加ではない。この保証は、`raise`が対応する`except`ブロックの
        外側（本節下記のtry/except直後）で行われることにより成立する——raise
        実行時点で「現在処理中の例外」が存在しないため、Pythonは暗黙の
        `__context__`をこのインスタンスへ一切付与しない（`carrier.__context__
        is None`・`carrier.__cause__ is None`が常に成立する。`raise ... from
        None`によるcontext抑制には依存しない、構造自体による保証）。"""
        def __init__(self, observation: "FeaturedMediaFailureObservation"):
            self.observation = observation
            super().__init__()


    def build_protected_featured_media_side_effect_binding(
        protected_context: "RetryLineageProtectedExecutionContext",
        media_upload_coordinator: "MediaUploadSafetyCoordinator",
        adapters: "MediaUploadWriteAheadAdapters",
    ) -> "ProtectedFeaturedMediaSideEffectBinding":
        """protected専用builder。coordinator/adaptersを必須で受け取り、そのまま
        bindingへ束縛する。legacy modeからは呼ばれない（呼び出し元が型でdispatch
        するため、このbuilderがlegacy contextを受け取ることは構造的にない）。
        runtime自体はここでは構築しない——記事ごとに`_apply_featured_media_step()`
        側で`build_protected_featured_media_runtime()`（本節）を呼んで導出する。"""
        return ProtectedFeaturedMediaSideEffectBinding(protected_context, media_upload_coordinator, adapters)

    def build_legacy_featured_media_side_effect_binding(
        legacy_context: "LegacyDirectExecutionContext",
        runtime: "ArticleFeaturedMediaRuntime",
    ) -> "LegacyFeaturedMediaSideEffectBinding":
        """legacy専用builder。引数は`legacy_context`と、main.py起動時に既に構築
        済みのlegacy runtimeの2つのみ——`media_upload_coordinator`・`adapters`は
        このbuilderのシグネチャに一切現れない。legacy modeでprotected
        dependencies（Coordinator・write-ahead adapters）を構築してから破棄する、
        という経路が構造的に存在しないことをシグネチャ自体が保証する。runtime引数を
        必須化することで、`_apply_featured_media_step()`のシグネチャからorphanな
        `runtime`位置引数を排除しつつ、legacy modeのruntime源泉を一意に確定する。"""
        return LegacyFeaturedMediaSideEffectBinding(legacy_context, runtime)
    ```

    **trusted composition boundary（main.py起動時、1箇所のみ）が、`validate_side_effect_execution_context()`（2.1b節の共通validator）が返した検証済み`context`の型でdispatchし、対応するbuilderのみを呼ぶ（単一factory契約は採用せず2 builder化とし、legacy builderは`runtime`引数を必須とする）**：`isinstance(context, RetryLineageProtectedExecutionContext)`の場合のみ`media_upload_coordinator`・`adapters`（`MediaUploadWriteAheadAdapters.from_env()`）を構築し`build_protected_featured_media_side_effect_binding(context, media_upload_coordinator, adapters)`を呼ぶ。`isinstance(context, LegacyDirectExecutionContext)`の場合は`media_upload_coordinator`・`adapters`のいずれも構築せず、既存起動時構築済みの`featured_media_runtime`（下記main.py配線）を渡して`build_legacy_featured_media_side_effect_binding(context, featured_media_runtime)`を呼ぶ。いずれの型にも一致しない場合は、いずれのbuilderも呼ばれる前に`SideEffectExecutionModeContractError(ExecutionModeFailureReasonCode.UNKNOWN_EXECUTION_MODE)`でfail-closedする（`None`・Optional値はここへ到達しない——欠落は共通validatorが既にfail-closed済み）。`ambient/global状態からの再構築`・`Noneからのlegacy推論`・`correlation_metadataからのmode推測`・`unknown typeのlegacy fallback`のいずれも行わない。`FeaturedMediaSideEffectBinding`はこのdispatchが返す2 builderいずれかの戻り値の型（discriminated union）であり、それ自体は新しいprovenance authorityではなく、既に確定した`context`（2.1節の型）をtransportするintegration bindingに過ぎない。
- `main.py`（起動時construction経路は単一である）：main.pyは起動時（記事ループの外側）、`_parse_execution_context_from_env()`（14.3節）で`context`（discriminated union）を解決した**直後に**、その型で分岐する。この分岐が、293行目`ArticleFeaturedMediaRuntime.from_env()`を呼ぶかどうか自体を決定する——「両分岐で共通して1回実行してから、protected側だけ後から破棄してよい／構築しなくてもよい」という二択は採用しない。`isinstance(context, LegacyDirectExecutionContext)`の場合**のみ**、`featured_media_runtime = ArticleFeaturedMediaRuntime.from_env()`（293行目）を呼び、これを`build_legacy_featured_media_side_effect_binding(context, featured_media_runtime)`へ渡してbindingへ束縛する（legacy modeは既存6.31以前の「起動時に1回構築したruntimeを記事ループ全体で使い回す」挙動を無変更のまま維持する）。`isinstance(context, RetryLineageProtectedExecutionContext)`の場合、`ArticleFeaturedMediaRuntime.from_env()`は**一切呼ばない**（構築してから破棄する経路・構築を省略する経路という2通りの実装は許容しない）——起動時には代わりに`MediaUploadWriteAheadAdapters.from_env()`のみを1回構築し、記事専用の`ArticleFeaturedMediaRuntime`は記事ごとに`_apply_featured_media_step()`内部で`build_protected_featured_media_runtime()`（本節）により新規構築する（Gate ON/OFFいずれの場合も、この関数が記事ごとに適切な形のruntimeを返す——Gate OFF時は`build_protected_featured_media_runtime()`自身がdecoratorなしのruntimeを返すため、`_apply_featured_media_step()`が別の未定義runtime源泉に頼る必要はない）。main.pyは起動時（記事ループの外側）に、上記dispatchに従い`isinstance(context, RetryLineageProtectedExecutionContext)`なら`side_effect_binding = build_protected_featured_media_side_effect_binding(context, media_upload_coordinator, adapters)`を、`isinstance(context, LegacyDirectExecutionContext)`なら`side_effect_binding = build_legacy_featured_media_side_effect_binding(context, featured_media_runtime)`を、それぞれ1回だけ呼ぶ。legacy分岐では`media_upload_coordinator`・`adapters`のいずれも構築しない——protected分岐では`ArticleFeaturedMediaRuntime.from_env()`（legacy credential/config解決を含む）を一切構築しない——いずれの方向でも「使わない依存を構築してから破棄する」経路は構造的に存在しない。記事ループの各iterationでこの同一bindingインスタンスを`_apply_featured_media_step(article, side_effect_binding=side_effect_binding)`へ明示的に渡す（orphanな`runtime`位置引数は持たない——runtimeの源泉はbinding自身（legacy＝`binding.runtime`、protected＝binding情報から呼び出しのたびに構築）が一意に持つ）。globals・モジュールレベルのambient状態・hidden singletonを経由した伝達は行わない——bindingはmain()のローカル変数として保持され、関数の明示的な引数としてのみ伝播する。
- `main.py::_apply_featured_media_step()`（187-203行目、既存。orphanな`runtime`位置引数は持たない確定シグネチャ）：新シグネチャは以下のとおり——

  ```python
  def _apply_featured_media_step(
      article: ArticleData,
      *,
      side_effect_binding: "FeaturedMediaSideEffectBinding",
  ) -> ArticleFeaturedMediaRuntimeResult:
      ...  # 本文は以下のdispatchロジック（28.-35節）
  ```

  **`runtime: ArticleFeaturedMediaRuntime`を第1位置引数として要求する設計は採用しない——protected modeでは起動時に`ArticleFeaturedMediaRuntime.from_env()`を呼ばない設計（上記main.py配線）と矛盾し、呼び出し元がこの引数へ渡すべき値が存在しないためである。runtime自体をbindingの責務とすることでこの矛盾を解消する——protected/legacyいずれも、runtimeの源泉は`side_effect_binding`一つから一意に導出される。**

  **確定したexact caller、かつ`record_confirmed()`の唯一のowner（decoratorはrecord_confirmed()を呼ばない——上記`WriteAheadAwareMediaUploadCapability`の説明参照）。`ArticleFeaturedMediaRuntime`のconstructor/`apply()`シグネチャへは一切追加しない（Foundation 3ファイル無変更、`side_effect_binding`はRuntime自体へは渡さない）。** 関数本体の先頭で`side_effect_binding`をexhaustiveにdispatchする（`isinstance`連鎖、以下の3分岐以外の経路を持たない）：

  - `isinstance(side_effect_binding, LegacyFeaturedMediaSideEffectBinding)`：`runtime = side_effect_binding.runtime`（main.py起動時に構築済みのlegacy runtime、上記main.py配線）を取り出す。4 safety methodsのいずれも呼ばない（15.4.1節「legacy direct執行時の扱い」と同一）。
  - `isinstance(side_effect_binding, ProtectedFeaturedMediaSideEffectBinding)`：`context = side_effect_binding.context`・`media_upload_coordinator = side_effect_binding.media_upload_coordinator`・`adapters = side_effect_binding.adapters`を取り出す（`validate_side_effect_execution_context()`は、binding構築時点（`build_protected_featured_media_side_effect_binding()`）で既に完了済みのため、ここでの再呼び出しは不要）。`identity = SideEffectOperationIdentity(root_run_id=context.root_run_id, attempt_ordinal=context.attempt_ordinal, operation_kind=ProtectedSideEffectKind.MEDIA_UPLOAD, effect_site=SideEffectSite.NEWS_STEP, operation_instance_key=article.slug)`（15.7節と同一の`operation_instance_key`規律）を構築する。Gate OFF（`not adapters.enabled`）なら`media_upload_coordinator.record_not_applicable(identity, context.member_run_id)`を呼んだ**後に**、Gate ONなら`media_upload_coordinator.record_prepared(identity, context.member_run_id)`（durable ACK、9.9.4.7節）を呼んだ**後に**、**Gate ON/OFFいずれの場合も同一の**`runtime = build_protected_featured_media_runtime(adapters, media_upload_coordinator, identity, context.member_run_id)`で記事専用runtimeを構築する（`build_protected_featured_media_runtime()`自体が`adapters.enabled`に応じてdecorator付き/なしのruntimeを内部で適切に返すため、呼び出し元は分岐を問わず常にこの1つの関数を呼べば足りる——Gate OFF分岐で未定義の`runtime`引数へ暗黙に依存する設計は採用しない）。
  - **いずれの型にも一致しない場合（欠落・未知・矛盾したbinding）**：`media_upload_coordinator.record_*()`・`runtime.apply()`のいずれも呼ぶ**前**に`SideEffectExecutionModeContractError(ExecutionModeFailureReasonCode.UNKNOWN_EXECUTION_MODE)`を送出しfail-closedする（**external I/O = 0**）。`None`からのlegacy推論・ambient/global状態からの再構築・`correlation_metadata`からのmode推測はいずれも行わない。

  **`runtime.apply(article)`呼び出し（上記2分岐いずれかで確定した同一`runtime`変数に対し、legacy/protectedを問わず`_apply_featured_media_step()`内部の単一箇所で行う）**：15.4節の既存PROPAGATE分類ロジック（`classify_propagated_failure()`、v6.25.0・無変更）を、runtimeを所有するこの関数内部で完結させるため、以下の共通try/exceptで包む——main.py outer article loop（22.3.13節）にはprotected modeのruntimeが存在しないため、分類はこの関数内部でのみ行える：

  ```python
  observation = None
  try:
      runtime_result = runtime.apply(article)
  except SideEffectExecutionModeContractError:
      raise  # runtime.apply()自体はこの例外を送出しない既存(v6.21以前)ロジックだが、
             # 他のcarve-outと同型の防御として明示する
  except Exception as exc:
      observation = runtime.classify_propagated_failure(exc)  # 15.4節の既存分類、無変更

  if observation is not None:
      raise FeaturedMediaPropagatedFailure(observation)  # main.py記事ループ（22.3.13節）へ
             # observationのみを運ぶ。except節の外でraiseするため、raiseの時点で
             # 「現在処理中の例外」は存在せず、carrierへ暗黙のexception chaining
             # （__context__/__cause__）は一切付与されない（`raise ... from None`
             # には依存しない、構造自体による保証）。
  ```

  legacy/protectedいずれの分岐も同一のtry/exceptを経由するため、main.py側（22.3.13節）は分岐を問わず単一の`except FeaturedMediaPropagatedFailure`節で処理できる。`SideEffectExecutionModeContractError`はexcept節内でそのままre-raiseされ、`FeaturedMediaPropagatedFailure`へ包まれることはない。

  **`record_confirmed()`の呼び出し条件**：`runtime_result.status is ArticleFeaturedMediaRuntimeStatus.APPLIED`の場合**のみ**、`applied_article = runtime_result.article`（`ArticleFeaturedMediaRuntimeResult`からの明示的なunwrap——15.5.1節の`_extract_confirmed_media_id()`は`ArticleData`専用のhelperのまま維持し、`ArticleFeaturedMediaRuntimeResult`をhelper内でunwrapしない）を取り出し、`media_id = _extract_confirmed_media_id(applied_article)`を適用する。`media_id`が非`None`の場合のみ`media_upload_coordinator.record_confirmed(identity, context.member_run_id, media_id)`を呼ぶ。`runtime_result.status`が`DISABLED`または`CONTINUED_WITHOUT_FEATURED_MEDIA`の場合は`record_confirmed()`を一切呼ばない——`featured_media_id > 0`という値の単独チェックを「今回のactual uploadが発生した証拠」として用いることはしない。

  **actual-upload evidenceの根拠（新規flag不要）**：`ArticleFeaturedMediaOrchestrator.apply()`（`article_featured_media_orchestrator.py:58-74`）は`generate()`→`upload()`→`bind_featured_media()`を例外分岐なしの固定順序で呼び出す。したがって`ArticleFeaturedMediaRuntime.apply()`（`article_featured_media_runtime.py:124-170`）が`status=APPLIED`（153-154・166-170行目、`try`ブロックが例外なく完了した場合のみ到達）を返すのは、`self._root.orchestrator.apply()`が例外を送出せず正常returnした場合に限られる——これは`generate()`・decorated`upload()`（内部で`record_attempted()`のIO_ARMED durable ACKを経由した後の真の外部upload）・`bind_featured_media()`のすべてが成功したことを意味する。既存の`ArticleFeaturedMediaRuntimeStatus`enum（v6.21.0、無変更）がこの区別をすでに提供しているため、6.32が新しいpredicate・flagを追加する必要はない。legacy実行時（`isinstance(context, LegacyDirectExecutionContext)`）は上記のいずれも呼ばず、既存（6.31以前）のロジックのまま`runtime.apply(article)`を呼ぶのみとする（15.4.1節「legacy direct執行時の扱い」と同一）。

#### 22.3.3 PUBLISH WordPress（呼び出し箇所C、15.6節）

- `src/ai/ai_publish_service.py`（`AiPublishService.run(self, article_id=None)`・`_process(self, review)`・`_post(self, review, rewrite)`）：`run()`/`_process()`/`_post()`のシグネチャへ`side_effect_execution_context`（必須引数）を追加し、`_post()`内の`WordPressDraftClient.post_draft()`呼び出し前後にwrite-ahead呼び出しを挿入する（15.6節）。2.2節（RETRY_LINEAGE_PROTECTED）のcontextが利用可能な場合のみ発動し、2.3節（LEGACY_DIRECT）の場合はlegacy behaviorのまま素通しする分岐を持つ。

**呼び出し箇所Cへの第3の経路**：`AiPublishService`の構築・`.run()`呼び出しは、`scripts/run_ai_publish.py`（直接）・`PublishPipelineRunner`（`PublishTriggerAgent`経由）に加え、**`src/ai/workflow_runner.py::WorkflowRunner.from_config()`が構築する`PublishStepExecutor(service=AiPublishService.from_env(...))`（97-99行目）を経由する第3の構築点**を持つ。`WorkflowRunner`は`WorkflowTriggerAgent`（`AgentManager`の4executor種別の1つ）→`WorkflowPipelineRunner`→`WorkflowRunner.run()`→`PublishStepExecutor.execute()`（`src/ai/workflow_step_executor.py:264-292`、271行目で`self._service.run(article_id=context.article_id)`を呼ぶ）という経路で到達する、呼び出し箇所Cへの経路である。この経路にも`side_effect_execution_context`を伝播させる必要がある（22.3.10節・2.6節に詳細）。

#### 22.3.4 RetryExecutor / provenance（22.1f節）

- `src/retry_engine/retry_executor.py`（`RetryExecutor.execute(self, request, lineage, claim)`。docstringが`request.dry_run`・`claim.steps_to_execute`・`self._lineage.mark_execution_started()`・`decide_disposition()`/`mark_terminal()`の呼び出し順序を定める）：`.run()`呼び出し箇所へ`side_effect_execution_provenance`（`RetryLineageProtectedProvenance`、member_run_id未確定）を追加で構築・伝播する（22.1f節）。

#### 22.3.5 WorkflowEngine propagation（22.1f節）

- `src/workflow_engine/workflow_engine_manager.py`（`WorkflowEngineManager.run(self, event, dry_run=False, target_step_filter=None, post_admission_hook=None, correlation_metadata=None)`）：シグネチャへ`side_effect_execution_provenance`引数を追加。
- `src/workflow_engine/workflow_engine_context.py`：`WorkflowEngineContext`へ`side_effect_execution_provenance`フィールドを追加。
- `src/workflow_engine/workflow_engine_executor.py`：`AgentContext`構築箇所でprotected factoryを呼び、完成済み`side_effect_execution_context`を注入。
- `src/ai/agent_context.py`（`AgentContext`は`task`・`dry_run`・`run_id`・`agent_name`を保持する）：`side_effect_execution_context`専用フィールドを追加。
- `src/ai/news_agent.py`（`NewsAgent.act(self, decision, context)`）：`self._runner.run(params=context.task.params)`へ`side_effect_execution_context=context.side_effect_execution_context`を追加。
- `src/pipeline/news_pipeline_runner.py`（`NewsPipelineRunner.run(self, params: dict)`）：`side_effect_execution_context`引数をシグネチャへ追加し`_serialize_execution_context()`で環境変数化。
- `src/pipeline/publish_pipeline_runner.py`（`PublishPipelineRunner.run()`の詳細シグネチャは15.6節と同様の追加を行う）：シグネチャへ`side_effect_execution_context`引数を追加。

#### 22.3.6 Retry Queue batch path（22.4・22.4a節）

**target call graph**：`src/retry_runtime_orchestrator/retry_runtime_orchestrator.py`の`run_once()`は、`self.manager.execute_dispatchable_retries()`を呼んで`execution_results`を取得し、続けて`self.manager.decide_retry_queue_updates(execution_results)`（`RetryManager`経由）のみを呼ぶ——`RetryQueueUpdateDecider().decide_all(execution_results)`を`run_once()`から直接構築・呼出しする経路は持たない。`execute_dispatchable_retries()`を呼ぶ主体・回数は変更しない。`RetryManager.decide_retry_queue_updates(execution_results)`は単一引数のシグネチャとし、内部で`execute_dispatchable_retries()`を再実行しない。詳細な実装契約は22.4a節を参照。

#### 22.3.7 retry trigger / eligibility（22.1e節）

- `src/retry_enqueue_trigger/retry_enqueue_trigger.py`（`RetryEnqueueTrigger.enqueue_pending_failures(self, limit=None, max_attempts=1, dry_run=False)`、168-263行目）：202行目`if self._lineage.find_by_member_run_id(record.run_id) is not None: ... skipped_lineage_member += 1; continue`がLayer 1のmembership-first除外として存在する（22.1e節の記述と一致）。新規変更は不要。
- `src/retry_composition/retry_composition_root.py`（145-147行目）：`RetryEnqueueTrigger(monitor=monitor, queue=queue, history=history, guard=guard, lineage=lineage, history_store=history_store,)`と`lineage`引数が常に明示的に渡される（22.1e節の記述と一致、行番号も一致）。

#### 22.3.8 reconciliation / open_next_attempt / claim（16・22.1c節）

- `src/retry_lineage/retry_lineage_manager.py`：`find_by_member_run_id(self, candidate_run_id: str) -> str | None`（145-147行目、線形走査`_find_root_by_member_run_id()`に委譲、**戻り値は単一の`root_run_id: str`または`None`——複数マッチを検出する機構は持たない**）・`claim(self, root_run_id: str) -> ClaimResult`（302行目）・`open_next_attempt(self, root_run_id: str) -> OpenNextAttemptResult`（465行目）を持つ。`RetryLineageDisposition`に`HUMAN_REVIEW_REQUIRED`を追加する変更（22.1c節）は、これら既存メソッドのシグネチャに影響しない。
- **22.4a節との整合**：`find_by_member_run_id()`は単一`str | None`を返す実装であるため、`build_retry_queue_decision_requests()`（22.4a節）は複数件を返すambiguous mapping検出用の新規APIを設計せず、既存の`find_by_member_run_id()`をそのまま採用する。member_run_id → root_run_id一意性は既存6.31 contract（`create_new_lineage()`のグローバル一意性チェック＋UUID4再利用なしの設計＋Layer 1が既にこの単一値契約を信頼している実績）により前提とされている（22.4a節参照）。

#### 22.3.9 serialization / state stores（9.3・22.1b節）

- `src/retry_lineage/retry_lineage_store.py`：`tempfile.mkstemp()`→write→flush→`os.fsync(fd)`→close→`os.replace(tmp_path, final_path)`という atomic write パターンを持つ（9〜85行目、`save()`/`get()`/`list_all()`）。新設する`JsonWordPressDraftStateStore`（22.1b節）はこのパターンをそのまま踏襲する（27.2節の主張と一致）。

**未変更（6.32では変更しない）**：`src/article_media_upload_state/`（9.8節、既存の統合アダプター経由でのみ再利用）、`src/retry_queue/retry_queue_status.py`・`src/retry_engine/retry_queue_removal_executor.py`・`retry_queue_cleanup_decider.py`・`retry_queue_terminal_cleanup_decider.py`・`retry_outcome_terminality.py`（22.1d節、HRRは新しいoutcome/status値を経由せず既存の`FAIL`/`FAILED`へ合流するため、これらは無改修のまま正しく動作する）。

#### 22.3.10 AgentManager fan-out legacy provenance

`src/ai/agent_manager.py`・`src/ai/agent_executor.py`・`scripts/run_news_agent.py`・`scripts/run_workflow_trigger_agent.py`・`scripts/run_publish_trigger_agent.py`・`scripts/run_review_trigger_agent.py`に対する統合内容。

- `src/ai/agent_manager.py`：`AgentManager.__init__(self, config, executors: list[AgentExecutor])`（72-74行目）・`from_config()`（76-144行目、`NewsAgent`常時＋`WorkflowTriggerAgent`/`PublishTriggerAgent`/`ReviewTriggerAgent`を各Configの`is_ready()`ゲートで条件付き追加）・`run(self, task, dry_run=False)`（150-161行目、`self._executors`を単一ループでfan-outし、各executorへ`AgentContext(task=task, dry_run=dry_run, run_id=self._generate_run_id(), agent_name="")`を個別構築）を持つ。`agent_name=""`は常に空文字列で構築されており（158行目）、実行中のAgent種別を`AgentContext`自身から読み取る手段は現状存在しない——`AgentExecutor._before_execute()`（`agent_executor.py:99-102`）が`context.agent_name = self._agent.name()`で事後的に上書きするのみであり、`AgentManager.run()`のfan-outループ内（`AgentContext`構築時点）ではこの値はまだ設定されていない。このため、Stage 2の`legacy_execution_origin`決定は`self._agent.name()`の文字列照合ではなく、`AgentManager.from_config()`が各Agentを構築する時点（Agent型が確実にわかっている）で確立するmappingに基づく（2.3節）。
- `src/ai/agent_executor.py`：`AgentExecutor.__init__(self, agent: BaseAgent)`（33-34行目）は`self._agent`を非公開で保持し、公開accessorを持たない。`AgentExecutor`自体への変更は不要——Agent型の識別は`AgentManager.from_config()`側で完結させる。
- `scripts/run_news_agent.py`・`scripts/run_workflow_trigger_agent.py`・`scripts/run_publish_trigger_agent.py`・`scripts/run_review_trigger_agent.py`（いずれも`AgentManager.from_config(config)`→`manager.run(task, dry_run=args.dry_run)`という同一パターンを持つ）：Stage 1 provenance構築を追加（22.1f節）。4スクリプトとも2.3節の閉集合に含まれる。
- `src/ai/workflow_runner.py`：`WorkflowRunner.from_config()`（57-104行目）が`PublishStepExecutor(service=AiPublishService.from_env(base_dir=base_dir))`（97-99行目）を構築する——`WorkflowTriggerAgent`経由で呼び出し箇所Cへ到達する経路の起点（22.3.3節）。`run(self, article_id=None, dry_run=False)`（106-160行目）のシグネチャへ`side_effect_execution_context`を追加。
- `src/ai/workflow_context.py`：`WorkflowContext`（19-30行目）は`article_id`・`dry_run`・ランタイム状態のみを保持する単純なdataclass。`side_effect_execution_context`フィールドを追加。
- `src/ai/workflow_step_executor.py`：`PublishStepExecutor.execute()`（255-292行目、271行目で`self._service.run(article_id=context.article_id)`）。`ReviewPipelineRunner`→`AiPublishReviewService`（`review_pipeline_runner.py`）は、Markdownレポート保存のみを行い、WordPress POST・media uploadのいずれにも到達しないため、6.32のprotected operationの対象外である（変更不要）。
- `src/pipeline/workflow_pipeline_runner.py`：`WorkflowPipelineRunner.run(self, params=None)`（51-94行目）のシグネチャへ`side_effect_execution_context`を追加。

#### 22.3.11 Entrypoint Closure Contract

**Candidate root定義**：production entrypointのcandidate rootは、(a) project-root配下の全`*.py`ファイル、(b) `scripts/**/*.py`、(c) 実在するpackaging/console-script entrypoint（`pyproject.toml`/`setup.py`/`setup.cfg`のentry_points宣言）の合併とする。

**Classification rule（recursive intra-project static call/import closure、sink-terminal方式）**：あるcandidate rootのclassification（`SIDE_EFFECT_CAPABLE`／`NON_SIDE_EFFECT_CAPABLE`）は、symbol名・キーワードの字面一致（grep）では決定しない——`AiPublishReviewService`（`AiPublish`を含むが呼び出し箇所Cとは無関係の読み取り専用クラス）のような偽陽性、および文字列一致だけでは判定できない間接呼び出しの双方を避けるため、以下の**到達可能性closure**のみを唯一のoracleとする：

1. candidate rootのモジュールから開始し、そのfileが直接importする本repository内（project-root・`src/`・`scripts/`配下）のモジュール・呼び出す関数/メソッドを、AST解析により再帰的に辿る（標準ライブラリ・サードパーティ依存はhalt——追跡対象は本repositoryのソースのみ）。
2. 3つの**terminal sink**を固定して定義する：A＝`WordPressOutput.save()`の呼び出し、B＝`ArticleFeaturedMediaRuntime.apply()`（`orchestrator.apply()`）の呼び出し、C＝`AiPublishService.run()`/`_process()`/`_post()`のいずれかの呼び出し。closure探索は、これらのsinkへの呼び出し文（`Call`ノード）に到達した時点でそのsinkを「到達」として記録し、それ以上追跡を続けない（sinkはterminal）。
3. あるcandidate rootのclosureが、いずれのsinkにも到達せず、かつ探索したすべての呼び出し辺が静的に解決済み（後述のdynamic edgeが存在しない）である場合、そのcandidate rootは`NON_SIDE_EFFECT_CAPABLE`（到達operation集合＝空集合）に分類する。
4. `AgentManager`経由のfile（`AgentManager.run()`/`.from_config()`を呼ぶ4 launcher）については、静的な単一具象実装を持たないfan-out（登録されるexecutor集合が実行時Config依存、22.3.10節）を経由するため、通常のclosure追跡では個別の具象Agentを一意に確定できない——この既知のfan-out構造については、22.3.10節が定める登録契約（`NewsAgent`は無条件登録、`WorkflowTriggerAgent`/`PublishTriggerAgent`/`ReviewTriggerAgent`は各々の`is_ready()`ゲートで条件付き登録）を直接の静的解析対象とし、config次第でどの組み合わせが実際に登録されてもそのunion（和集合）が到達しうるsink集合であることを個別に証明する（**aggregate reachability {A, B, C}**、launcher名に紐づく固定subsetにはならない）。この4 launcher以外のfan-outは本repositoryに存在しない。
5. **Protocol/抽象型経由呼び出しのfinite-set resolution**：closure探索中に、呼び出しのreceiverがProtocol/abstract base/抽象型注釈（例：`RewriteService._provider: ArticleProvider`）で宣言されている場合、repository実在のconstruction/composition/config箇所（`from_env()`・`from_config()`等のfactory）を静的に解析し、その抽象型へ実際に代入されうる具象実装の集合が**有限（finite）であることを証明できるか**を確認する。証明できる場合（例：`ArticleProvider`は`WordPressArticleProvider`または`NullArticleProvider`のいずれかにのみ解決されることが、これらのfactory・config分岐から静的に確定できる場合）——finite set内の**すべての**具象実装についてそれぞれ独立にclosure解析（1〜4）を行い、到達するsink集合の**和集合**をその呼び出し箇所の到達sink集合として採用する。finite setの証明ができない場合は6.の`unresolvable`へ進む。
6. 上記4・5以外の箇所で、closure探索中に**静的に解決不能な動的呼び出し辺**（例：Protocol/抽象型の具象実装集合がfiniteであると証明できない間接呼び出し、`getattr`による動的属性呼び出し等）に遭遇した場合、そのcandidate rootの分類は**証明不能**とし、`SIDE_EFFECT_CAPABLE`にも`NON_SIDE_EFFECT_CAPABLE`にも分類せずFAILとする（安全側へ推測しない）。

**現行のclosed set**：`scripts/run_retry_runtime.py`が唯一のprotected composition root（`RetryCompositionRoot`→`RetryRuntimeOrchestrator`→`RetryExecutor.execute()`→`WorkflowEngineManager.run()`、2.2節RETRY_LINEAGE_PROTECTED、A・B・C到達）である。以下の8 entrypointが`LegacyEntrypoint`/`LegacyExecutionOrigin`のclosed set（2.3節、8値）を構成する：

| Entrypoint | 到達しうるprotected operation | 備考 |
|---|---|---|
| project-root `main.py` | A・B | `LegacyEntrypoint.RUN_MAIN_DIRECT`／`LegacyExecutionOrigin.MAIN_DIRECT`（14.2・14.3節） |
| `scripts/run_news_agent.py` | A・B・C（aggregate、上記Classification rule） | Stage 1固定`RUN_NEWS_AGENT`、Stage 2はdispatchされたAgent型ごとに決定（2.3節対応表・28.-19節） |
| `scripts/run_workflow_trigger_agent.py` | A・B・C（aggregate） | Stage 1固定`RUN_WORKFLOW_TRIGGER_AGENT` |
| `scripts/run_publish_trigger_agent.py` | A・B・C（aggregate） | Stage 1固定`RUN_PUBLISH_TRIGGER_AGENT` |
| `scripts/run_review_trigger_agent.py` | A・B・C（aggregate） | Stage 1固定`RUN_REVIEW_TRIGGER_AGENT`（`ReviewTriggerAgent`自身は到達operationを持たないが、同一`AgentManager.run()`呼び出し内でfan-outしうる他Agent型により、このlauncherもaggregate {A,B,C}を持つ） |
| `scripts/run_ai_publish.py` | C | `RUN_AI_PUBLISH`／`AI_PUBLISH_DIRECT` |
| `scripts/run_ai_workflow.py` | C | `RUN_AI_WORKFLOW`／`AI_WORKFLOW_DIRECT` |
| `scripts/run_workflow_engine.py` | A・B・C | `RUN_WORKFLOW_ENGINE_DIRECT`／`WORKFLOW_ENGINE_DIRECT`（`--job-id`手動指定／Scheduler経由、Retry Lineage外） |

**closed classification manifest（全candidate root、9 + 10 = 19エントリ）**：candidate root定義（上記(a)(b)(c)）に一致するfileは、以下いずれか1つの分類へ**exactly once**属さなければならない——上記9 entrypoint（`SIDE_EFFECT_CAPABLE`、到達operationは上表のとおり）に加え、以下10 fileを`NON_SIDE_EFFECT_CAPABLE`（Classification ruleが定める到達可能性closureにより、いずれのterminal sink（A/B/C）にも到達しないことが証明済み——`scripts/run_ai_publish_review.py`は`AiPublishReviewService`のみをimportし`AiPublishService`を一切importしない、`scripts/run_ai_rewrite.py`は`RewriteService`経由で`article_provider.py::WordPressArticleProvider`（GET-onlyの読み取り専用、28.-34節#4のsink oracleでも`safe-non-mutation`と分類される既知の安全な経路）にのみ到達し呼び出し箇所A/B/Cのいずれにも到達しない、のように、`AiPublish`等の字面一致ではなく実際のimport/call closureで確認する）として明示的にmanifestへ含める：

| Entrypoint | 分類 |
|---|---|
| `scripts/fetch_google_analytics_metrics.py` | `NON_SIDE_EFFECT_CAPABLE` |
| `scripts/fetch_search_console_metrics.py` | `NON_SIDE_EFFECT_CAPABLE` |
| `scripts/run_ai_improvement.py` | `NON_SIDE_EFFECT_CAPABLE` |
| `scripts/run_ai_improvement_report.py` | `NON_SIDE_EFFECT_CAPABLE` |
| `scripts/run_ai_publish_review.py` | `NON_SIDE_EFFECT_CAPABLE` |
| `scripts/run_ai_rewrite.py` | `NON_SIDE_EFFECT_CAPABLE` |
| `scripts/run_ai_rewrite_review.py` | `NON_SIDE_EFFECT_CAPABLE` |
| `scripts/show_execution_history.py` | `NON_SIDE_EFFECT_CAPABLE` |
| `scripts/show_retry_notification.py` | `NON_SIDE_EFFECT_CAPABLE` |
| `scripts/show_workflow_status.py` | `NON_SIDE_EFFECT_CAPABLE` |

**Fail condition**：(1) candidate root定義に一致するfileが、上記19エントリのmanifestに**存在しない**場合（新規root）、これはcontract violationであり、到達可能性のclosure探索を試みる前に直ちにFAILとする。(2) manifestの同一fileが複数の分類（`SIDE_EFFECT_CAPABLE`のいずれかの行と`NON_SIDE_EFFECT_CAPABLE`、または`SIDE_EFFECT_CAPABLE`内の複数行）に**重複して**属す場合もcontract violationとする。(3) `SIDE_EFFECT_CAPABLE`に分類されたentrypointについて、実際の到達可能性closureが上表と一致しない場合、および`NON_SIDE_EFFECT_CAPABLE`に分類されたfileが実際にはterminal sink（A/B/C）へ到達するclosureを持つ場合も、同様にcontract violationとする。(4) いずれかのcandidate rootのclosure探索が静的に解決不能な動的呼び出し辺に遭遇し、分類を証明できない場合も、同様にcontract violationとする（安全側へ推測せずFAILする）。(1)(2)は新規未分類root・重複分類の検出、(3)は既存19エントリの回帰検出、(4)は証明不能ケースの検出であり——これらは異なる検証段階として扱う（28.-34節#3）。この契約に対する実行可能なオラクルは28.-34節#3が定める。

#### 22.3.12 `run_ai_workflow.py`のwiring

- `scripts/run_ai_workflow.py`（`WorkflowRunner.from_config(config)`→`runner.run(article_id=args.article_id, dry_run=args.dry_run)`、114・121行目）：`WorkflowRunner.from_config(config)`構築直後に`legacy_provenance = build_legacy_direct_provenance(LegacyEntrypoint.RUN_AI_WORKFLOW)`を構築し、`complete_legacy_execution_context(legacy_provenance, LegacyExecutionOrigin.AI_WORKFLOW_DIRECT)`を`runner.run(article_id=..., dry_run=..., side_effect_execution_context=completed_context)`へ渡す（2.3節「`run_ai_workflow.py`のStage 1/Stage 2」参照）。
- `src/ai/workflow_runner.py::WorkflowRunner.run()`・`src/ai/workflow_context.py::WorkflowContext`・`src/ai/workflow_step_executor.py::PublishStepExecutor.execute()`：22.1f節・22.3.10節が定義する伝播契約に従う——`WorkflowRunner.run()`シグネチャへ`side_effect_execution_context`引数を追加し`WorkflowContext`構築時へ渡す、`WorkflowContext`へ`side_effect_execution_context`フィールドを追加、`PublishStepExecutor.execute()`が`context.side_effect_execution_context`を`AiPublishService.run()`へ追加引数として渡す。`run_ai_workflow.py`はこの伝播経路（`WorkflowRunner.run()`→`WorkflowContext`→`PublishStepExecutor.execute()`→`AiPublishService.run()`）を、`WorkflowTriggerAgent`経由の呼び出し（22.3.10節）と共有する——経路自体は22.1f・22.3.10節が定義する単一の伝播契約であり、`run_ai_workflow.py`起点専用の別契約ではない。protected/legacy provenanceのlossless propagation・missing/unknown modeのfail-closed・`correlation_metadata`からの再構築禁止は、いずれも2.6節Propagation Contract・2.1b節共通validatorの既存契約がそのまま適用される（本節固有の追加契約はない）。

**`PublishStepExecutor`をauthoritative validation boundaryとして確定**：`PublishStepExecutor.execute()`（`workflow_step_executor.py:270-292`）は`self._service.run(article_id=context.article_id)`呼び出し全体を`try: ... except Exception as e: return WorkflowStepResult(success=False, ...)`という広範な例外捕捉で包んでいるため、`SideEffectExecutionModeContractError`がここに到達すると通常のstep failureへ黙って変換されてしまう。`PublishStepExecutor.execute()`（`src/ai/workflow_step_executor.py`）を、`context.side_effect_execution_context`のauthoritative validation boundaryとして確定する：

```python
def execute(self, context: WorkflowContext) -> WorkflowStepResult:
    started_at = datetime.now()

    if context.dry_run:
        return _dry_run_result(self.step(), started_at)

    # 6.32新設：AiPublishServiceを呼ぶ既存try/exceptブロックの外側（手前）で
    # validationを行う——ここで送出されるSideEffectExecutionModeContractErrorは
    # 下記except Exceptionに捕捉されず、呼び出し元（WorkflowRunner.run()）へ
    # そのまま伝播する。
    validated_context = validate_side_effect_execution_context(
        context.side_effect_execution_context,
    )  # 2.1b節共通validator。missing/unknown/矛盾はここでfail-closedし、
       # self._service.run()以下のexternal I/Oを一切呼ばない。

    try:
        report_path   = self._service.run(
            article_id=context.article_id,
            side_effect_execution_context=validated_context,
        )
        results       = self._service.get_results(article_id=context.article_id)
        success_count = sum(1 for r in results if r.success)
        return WorkflowStepResult(
            step=self.step(), success=True, processed_count=success_count,
            report_path=report_path, error_message=None,
            started_at=started_at, finished_at=datetime.now(),
        )
    except Exception as e:
        return WorkflowStepResult(
            step=self.step(), success=False, processed_count=0,
            report_path=None, error_message=str(e),
            started_at=started_at, finished_at=datetime.now(),
        )
```

validationを既存`try`ブロックの**外側**（手前）に置くことで、`SideEffectExecutionModeContractError`は構造的に`except Exception`へ到達しえない——通常のstep failure（`WorkflowStepResult(success=False, ...)`）へ変換されることなく、`WorkflowRunner.run()`（22.1f節）まで独立した例外として伝播する。missing/unknown/矛盾したcontextの場合、`self._service.run/_process/_post`のいずれも呼ばれる**前**にfail-closedする（**external I/O = 0**）。`correlation_metadata`等からの再構築は行わない（2.1b節共通validatorの既存契約をそのまま適用、本節固有の追加ロジックはない）。

**contract errorがStage-1 caller到達前に外側のbroad `except Exception`へ吸収される問題**：`PublishStepExecutor`自身の境界設計に加え、`WorkflowTriggerAgent`経由の実production chain（`AgentManager.run()`→`AgentExecutor.execute()`→`WorkflowTriggerAgent.act()`→`WorkflowPipelineRunner.run()`→`WorkflowRunner.run()`→`PublishStepExecutor.execute()`）には、`PublishStepExecutor.execute()`より外側に**さらに2箇所**のbroad `except Exception`が存在し、`SideEffectExecutionModeContractError`が`WorkflowRunner.run()`を無事に脱出した後もStage-1 caller（起動scriptまたは`AgentManager.run()`の呼び出し元）へ到達する前に通常のfailureへ暗黙変換されうる：

- `src/pipeline/workflow_pipeline_runner.py::WorkflowPipelineRunner.run()`（51-94行目）：65行目`try:`〜71行目`except Exception as e:`が`runner.run(article_id=article_id, dry_run=dry_run)`（70行目、`WorkflowRunner.run()`の呼び出し）全体を包み、あらゆる例外を`PipelineResult(success=False, error_message=str(e))`（72-79行目）へ変換する。
- `src/ai/agent_executor.py::AgentExecutor.execute()`（36-97行目）：53行目`try:`〜80行目`except Exception as e:`が`self._agent.act(decision, context)`（79行目、`WorkflowTriggerAgent.act()`の呼び出し。内部で上記`WorkflowPipelineRunner.run()`を呼ぶ）全体を包み、あらゆる例外を`AgentResult(success=False, error_message=str(e))`（87-94行目）へ変換する。

（`scripts/run_ai_workflow.py`経由＝`AI_WORKFLOW_DIRECT`の場合はこの2箇所を経由しない——`run_ai_workflow.py`（114・121行目）は`runner.run(...)`を`try/except`で包まずそのまま呼ぶため、`SideEffectExecutionModeContractError`は`main()`まで未変換の例外として自然に伝播し、script自体が非0終了コードでクラッシュする。この経路は既に契約どおり動作している。）

**契約**：`SideEffectExecutionModeContractError`（2.1b節共通validatorが送出する唯一の契約違反例外family、reason codeは2.5節`ExecutionModeFailureReasonCode`のclosed setで表現され、例外の型自体は単一のまま）は、上記2箇所を含む`WorkflowTriggerAgent`経由chain上のいずれのbroad `except Exception`によっても`re-raise`され、通常の`PipelineResult`/`AgentResult`失敗へ変換されない：

```python
# src/pipeline/workflow_pipeline_runner.py::WorkflowPipelineRunner.run()
try:
    workflow_result = runner.run(article_id=article_id, dry_run=dry_run)
except SideEffectExecutionModeContractError:
    raise  # 6.32新設：contract violationはPipelineResultへ変換せず素通しする
except Exception as e:
    return PipelineResult(
        success=False,
        returncode=None,
        elapsed_sec=time.time() - start,
        stdout_log_path=None,
        stderr_log_path=None,
        error_message=str(e),
    )  # 既存、無変更

# src/ai/agent_executor.py::AgentExecutor.execute()
try:
    result = self._agent.act(decision, context)
except SideEffectExecutionModeContractError:
    raise  # 6.32新設：contract violationはAgentResultへ変換せず素通しする
except Exception as e:
    context.errors.append(str(e))
    result = self._build_result(
        context=context,
        decision=decision,
        action_taken=False,
        success=False,
        workflow_result=None,
        error_message=str(e),
    )  # 既存のAgentResult(success=False)構築、無変更
```

`Exception`一般の既存挙動（`PipelineResult(success=False, ...)`／`AgentResult(success=False, ...)`への変換）はいずれも無変更のまま維持する——`SideEffectExecutionModeContractError`という単一の既存例外型のみを対象としたcarve-outであり、新しい例外階層・新しいcontract-error型を追加しない。この結果、`SideEffectExecutionModeContractError`は`AgentManager.run()`（`agent_manager.py:150-161`、それ自身はtry/exceptを持たないため素通しする）を経由して、`scripts/run_news_agent.py`等のStage-1 caller（22.3.10節）まで未変換の例外として到達する——external I/Oはこの伝播の間、一切発生しない。

#### 22.3.13 呼び出し箇所A/B/C — 全broad `except Exception`監査とContract-Error Non-Absorption

**目的**：`validate_side_effect_execution_context()`（2.1b節）が送出する`SideEffectExecutionModeContractError`が、呼び出し箇所A（NEWS WordPress draft、15.7節）・B（MEDIA_UPLOAD、15.4節）・C（PUBLISH WordPress draft、15.6節）へ到達する実production chain上のいずれのbroad `except Exception`によっても、通常の失敗結果へ暗黙変換されないことを、repository-backedに列挙・監査する。22.3.12節が`WorkflowTriggerAgent`経由chain（`WorkflowPipelineRunner.run()`・`AgentExecutor.execute()`）を既に対象としているため、本節はそれ以外の3箇所を対象とする。

**(1) 呼び出し箇所C — `PublishTriggerAgent`経由chain（`AgentManager`→`PublishTriggerAgent`→`PublishPipelineRunner`→`AiPublishService`）**：`src/pipeline/publish_pipeline_runner.py::PublishPipelineRunner.run()`（55-94行目）は、67行目`try:`〜73行目`except Exception as e:`が`service.run(article_id=article_id)`（71行目、`AiPublishService.run()`の呼び出し。内部で呼び出し箇所Cの`validate_side_effect_execution_context()`を通る、15.6節）全体を包み、あらゆる例外を`PipelineResult(success=False, error_message=str(e))`（74-81行目）へ変換する。22.3.12節と同型のcarve-outを適用する：

```python
# src/pipeline/publish_pipeline_runner.py::PublishPipelineRunner.run()
try:
    from ai import AiPublishService

    service = AiPublishService.from_env(base_dir=self._config.project_root)
    report_path = service.run(article_id=article_id)
    service.get_results(article_id=article_id)
except SideEffectExecutionModeContractError:
    raise  # 6.32新設：contract violationはPipelineResultへ変換せず素通しする
except Exception as e:
    return PipelineResult(
        success=False, returncode=None, elapsed_sec=time.time() - start,
        stdout_log_path=None, stderr_log_path=None, error_message=str(e),
    )  # 既存、無変更
```

`AgentExecutor.execute()`（22.3.12節で既にcarve-out済み、`src/ai/agent_executor.py`）はAgent種別を問わず共通の実行層であるため、`PublishTriggerAgent`経由でもこのcarve-outはそのまま適用される——本節が追加するのは`PublishPipelineRunner.run()`側のみである。

**(2) 呼び出し箇所A — `OutputManager.save_all()`**：`src/outputs/manager.py::OutputManager.save_all()`（18-46行目）は、36行目`try:`〜39行目`except Exception as e:`が`output.save(article)`（37行目。`output`が`WordPressOutput`の場合、内部で呼び出し箇所Aの`validate_side_effect_execution_context()`を通る、15.7節）全体を包み、あらゆる例外を`SaveResult(success=False, error_message=str(e))`（41-45行目）へ変換し、警告表示（`print()`、40行目）の上でループを継続する（他の出力先への保存を続行する既存の設計方針、本節でも維持）。22.3.12節と同型のcarve-outを適用する：

```python
# src/outputs/manager.py::OutputManager.save_all()
for output in self.outputs:
    if not output.is_available():
        continue
    output_type = "wordpress" if "WordPress" in output.__class__.__name__ else "file"
    try:
        result = output.save(article)
        results.append(result)
    except SideEffectExecutionModeContractError:
        raise  # 6.32新設：contract violationは他出力先へのcontinueへ変換せず素通しする
    except Exception as e:
        print(f"  [警告] {output.__class__.__name__} 保存失敗: {e}")
        results.append(SaveResult(
            success=False, output_type=output_type, error_message=str(e),
        ))  # 既存、無変更
```

**(3) 呼び出し箇所B — `main.py`記事ループの`_apply_featured_media_step()`呼び出し**：`main.py`記事ループは`_apply_featured_media_step(article, side_effect_binding=side_effect_binding)`（22.3.2節。呼び出し箇所Bの`validate_side_effect_execution_context()`はbinding構築時点で既に経由済み）を呼ぶ。画像生成・upload失敗の分類（`classify_propagated_failure()`、既存のPROPAGATE分類ロジック、v6.25.0・無変更）は、22.3.2節が定める通り`_apply_featured_media_step()`内部（runtimeを所有する箇所、legacy/protected分岐を問わず単一のtry/except）で完結し、分類済みの`FeaturedMediaFailureObservation`は22.3.2節新設の`FeaturedMediaPropagatedFailure`例外で運ばれる——main.pyはこの例外を捕捉してobservationを取り出すのみであり、`runtime`インスタンス自体を参照しない（protected modeではmain.py outer loopにruntimeが存在しないため）。`SideEffectExecutionModeContractError`（fail-closed contract violation）は`FeaturedMediaPropagatedFailure`とは独立した例外型であり、同じPROPAGATE経路へ誤って合流させてはならない：

```python
# main.py 記事ループ
try:
    featured_media_result = _apply_featured_media_step(article, side_effect_binding=side_effect_binding)
    article = featured_media_result.article
    featured_media_observation = featured_media_result.observation
except SideEffectExecutionModeContractError:
    raise  # 6.32新設：contract violationはFeaturedMediaPropagatedFailureのPROPAGATE分類へ
           # 合流させず、記事ループの外（main()呼び出し元）まで未変換のまま伝播させる
except FeaturedMediaPropagatedFailure as propagated:
    featured_media_observation = propagated.observation  # 22.3.2節、runtime内部で分類済み
    _handle_featured_media_failure(
        markdown_output, log_manager, article, saved_files,
        importance=importance, seo_title=seo_title, wp_public_url=wp_public_url,
        x_post_status=x_post_status, observation=featured_media_observation,
    )
    wp_failed_count += 1
    continue
```

`_apply_featured_media_step()`が画像生成・upload失敗（PROPAGATE対象）以外の未分類の例外を送出することはない（22.3.2節の共通try/exceptが`runtime.apply(article)`呼び出しを包み尽くすため）——本節のcatchに汎用`except Exception`は不要であり、持たない。

**契約**：`SideEffectExecutionModeContractError`は、上記(1)〜(3)を含む呼び出し箇所A/B/C到達chain上のいずれのbroad `except Exception`によっても`re-raise`され、通常の成功/失敗結果（`SaveResult`/`PipelineResult`/`FeaturedMediaPropagatedFailure`のPROPAGATE分類）へ変換されない。`Exception`一般の既存挙動（各既存の失敗結果構築・continue）はいずれも無変更のまま維持する——`SideEffectExecutionModeContractError`という単一の既存例外型のみを対象としたcarve-outであり、新しい例外階層は追加しない（`FeaturedMediaPropagatedFailure`は22.3.2節が定める、これとは独立した用途専用の薄いobservation carrierであり、`SideEffectExecutionModeContractError`のsubtype・variantではない）。

**repository-backed exhaustiveness**：呼び出し箇所A/B/Cへ到達するproduction chain（22.1f・22.3.10・22.3.11・22.3.12節、本節）に列挙された経路以外に、`AiPublishService`または呼び出し箇所A/B/Cのvalidation呼び出し以降で`Exception`を広く捕捉する箇所は`src/`配下に存在しない。

### 22.4 Retry Queue Update整合

**要件**：`RetryQueueUpdateDecider.decide()`は、独立の`decide_disposition(retry_result.workflow_engine_result)`（6.31 step-onlyの純粋関数）による再計算のみに基づいて`COMPLETE`／`FAIL`を決定してはならない。13章`resolve_final_disposition()`の優先順位1は、side-effect safety evidenceをstep-levelの成功/失敗より優先する（24章）ため、あるlineageの権威あるterminal_dispositionが`HUMAN_REVIEW_REQUIRED`であっても、workflow step自体が全て成功していれば`decide_disposition()`の独立再計算は`SUCCEEDED`相当の値を返しうる——`decide()`は6.32 contract対象lineageについて`RetryLineageManager.mark_terminal()`が確定させる権威あるterminal_dispositionを直接使用し、Queueが誤って`COMPLETE`（`RetryQueueStatus.COMPLETED`）へ倒れてreview必要というlineageの権威ある判定と食い違うことを防がなければならない。

**契約**：

**採用しない設計**：`authoritative_disposition: RetryLineageDisposition | None = None`というOptional引数で「6.32 contract対象か・legacyか」を暗黙に推測する設計は、呼び出し元（`RetryRuntimeOrchestrator.run_once()`）の配線漏れ（本来渡すべき`terminal_disposition`を渡し忘れる実装バグ）と、正当なpre-6.32 legacy lineageとを、値のレベルで区別できない。この場合、6.32対象lineageの権威あるterminal_dispositionが`decide_disposition()`ベースの独立再計算（`SUCCEEDED`/`FAILED`/`NOT_ACTIONED`のみを返す）へ静かに転落し、優先順位1（24章）が要求するsafety-evidence優先の判定が失われうる——2章のExplicit Side-Effect Execution Modeが解消したのと同種の「値の欠落からのlegacy推測」を、本節だけが未反映のまま残していた。

**新設する契約**：mode混同を型レベルで構造的に不可能にする、2章と同型のdiscriminated unionへ置き換える：

```python
@dataclass(frozen=True)
class LineageAuthoritativeDispositionInput:
    """6.32 contract対象lineage用（side_effect_contract_version is not None、18章）。
    mark_terminal()が確定させた権威あるterminal_dispositionを必須で保持する。
    このフィールドが欠落した状態は型として存在しない。"""
    terminal_disposition: "RetryLineageDisposition"


@dataclass(frozen=True)
class LegacyQueueDecisionInput:
    """pre-6.32 legacy lineage用（side_effect_contract_version is None、18章）。
    フィールドを持たない——「legacyとして扱う」という選択自体を型として明示する。
    decide_disposition()による従来のstep-only再計算を選択したことの直接的な証跡。"""


RetryQueueDecisionInput = "LineageAuthoritativeDispositionInput | LegacyQueueDecisionInput"


def build_queue_decision_input(record: "RetryLineageRecord") -> "RetryQueueDecisionInput":
    """RetryRuntimeOrchestrator.run_once()（22.1d節）が、実行対象lineageの
    RetryLineageRecordから構築する唯一の関数（trusted composition boundaryと
    同型の規律、2.1a節）。値の欠落からの推測はここでも行わない。
    contract versionの妥当性判定は18.1節classify_contract_version_evidence()
    のみを唯一のpredicateとして使う——独自に`is not None`のみでprotected/legacyを
    判定する設計は、0・負値・malformedなside_effect_contract_versionを誤って
    protected扱いしてしまうため採用しない。"""
    evidence = classify_contract_version_evidence(record)  # 18.1節、唯一のauthority
    if evidence == ContractVersionEvidence.INVALID:
        # invalid contract-version evidence：legacyへ推測せずcontract failureとする
        # （18.1節と同一のfail-closed規律）。
        raise RetryQueueUpdateContractError(
            f"lineage {record.root_run_id!r} has invalid side_effect_contract_version="
            f"{record.side_effect_contract_version!r}; refusing to infer legacy behavior."
        )
    if evidence == ContractVersionEvidence.PROTECTED:
        if record.terminal_disposition is None:
            # 6.32 contract対象lineageのはずが、この呼び出し時点でmark_terminal()が
            # 未確定——15.1〜15.2節の契約上発生しないはずだが、発生した場合は
            # legacyへ推測せずcontract failureとしてfail-closedする。
            raise RetryQueueUpdateContractError(
                "6.32 contract lineage reached queue-update without an authoritative "
                "terminal_disposition; refusing to infer legacy behavior."
            )
        return LineageAuthoritativeDispositionInput(terminal_disposition=record.terminal_disposition)
    return LegacyQueueDecisionInput()  # evidence == LEGACY、明示的にlegacy経路を選択（18章）
```

1. `RetryQueueUpdateDecider.decide()`は、`authoritative_disposition: RetryLineageDisposition | None`というOptional引数ではなく、**`queue_decision_input: RetryQueueDecisionInput`を必須引数（デフォルトなし）として受け取る**よう改める。呼び出し元（`RetryRuntimeOrchestrator.run_once()`、22.1d節）は、`build_queue_decision_input()`（上記）が返す値をそのまま渡す——`decide()`自身がOptional値の有無からcontract種別を推測することはない。
2. `queue_decision_input`が`LineageAuthoritativeDispositionInput`の場合、その`terminal_disposition`をそのまま使う。`SUCCEEDED`は`RetryQueueUpdateOutcome.COMPLETE`へ、それ以外（`FAILED`・`NOT_ACTIONED`・`HUMAN_REVIEW_REQUIRED`のすべて）は既存の`RetryQueueUpdateOutcome.FAIL`へ合流させる。**`RetryQueueUpdateOutcome`・`RetryQueueStatus`に新しい値は追加しない**——HRR終端lineageのretry eligibility/authorityは`RetryLineageRecord.terminal_disposition`・`human_review_resolution`（16・17章）のみが権威であり、Queue側は独立した状態を持たない。本節が解決するのは「`decide_disposition()`の独立再計算により、権威あるHRR判定が誤って`COMPLETE`へ倒れること」の防止のみである。
3. `queue_decision_input`が`LegacyQueueDecisionInput`の場合、従来どおり`decide_disposition(retry_result.workflow_engine_result)`ベースの判定を維持する（6.31 semanticsは無変更）。
4. `SUCCEEDED`/`FAILED`/`NOT_ACTIONED`の既存6.31 semantics（`RetryQueueUpdateOutcome.COMPLETE`/`FAIL`への写像）は変更しない。`RetryQueueCleanupDecider`・`RetryQueueTerminalCleanupDecider`・`RetryQueueRemovalExecutor`・`retry_outcome_terminality.py`は本節の変更に伴い無改修のままとする（新しいoutcome/status値を経由しないため）。
5. `RetryQueueDecisionInput`の型判定はisinstance分岐のみとし、いずれの型でもない値が渡された場合は`RetryQueueUpdateContractError`でfail-closedする（暗黙のlegacy fallbackを行わない）。

```python
def decide(
    self,
    execution_result: RetryExecutionResult,
    queue_decision_input: "RetryQueueDecisionInput",  # 必須引数、デフォルトなし
) -> RetryQueueUpdateDecision:
    """queue_decision_inputのisinstance分岐のみで経路を決定する。Optional値の
    有無からcontract種別を推測するロジックは持たない（discriminated unionにより
    その種の推測が構造的に不要になった、2章と同型の規律）。"""
    retry_result = execution_result.retry_result
    if retry_result.outcome != RetryOutcome.RETRIED:
        return RetryQueueUpdateDecision(  # 既存のNOOP経路、無変更
            execution_result=execution_result, outcome=RetryQueueUpdateOutcome.NOOP,
            target_status=None,
            reason=f"no retry was executed (retry_result.outcome={retry_result.outcome.value}).",
        )

    if isinstance(queue_decision_input, LineageAuthoritativeDispositionInput):
        disposition = queue_decision_input.terminal_disposition  # lineageのmark_terminal()確定値（権威）
    elif isinstance(queue_decision_input, LegacyQueueDecisionInput):
        disposition = decide_disposition(retry_result.workflow_engine_result)  # legacy、無変更
    else:
        raise RetryQueueUpdateContractError(
            f"unknown queue_decision_input type: {type(queue_decision_input)!r}"
        )

    if disposition == RetryLineageDisposition.SUCCEEDED:
        return RetryQueueUpdateDecision(
            execution_result=execution_result, outcome=RetryQueueUpdateOutcome.COMPLETE,
            target_status=RetryQueueStatus.COMPLETED,
            reason="retry was executed and disposition==SUCCEEDED.",
        )
    return RetryQueueUpdateDecision(  # FAILED / NOT_ACTIONED / HUMAN_REVIEW_REQUIRED、
        # いずれも既存のFAIL outcomeへ合流する（新しいoutcome値は追加しない）。
        execution_result=execution_result, outcome=RetryQueueUpdateOutcome.FAIL,
        target_status=RetryQueueStatus.FAILED,
        reason=f"retry was executed but disposition=={disposition.value}.",
    )
```

`RetryQueueUpdateContractError`は9.6節の例外分離規律・2.5節のsecret-safe診断規律と同様、実装契約違反（バグ）を示す例外として新設する（22.1d節）。

### 22.4a `decide_all()`バッチ経路の統合

`run_once()`は、`self.manager.execute_dispatchable_retries()`実行後に取得した`execution_results`を`self.manager.decide_retry_queue_updates(execution_results)`へ渡す経路のみを持つ（`retry_runtime_orchestrator.py::run_once()`）。`RetryQueueUpdateDecider().decide_all(execution_results)`を`run_once()`から直接構築・呼出しする経路は持たない。複数マッチ検出用の`find_all_by_member_run_id()`のようなAPIは公開しない——`find_by_member_run_id() -> str | None`（単一値）のみをauthoritative lookupとする。

**採用する設計**：`run_once()`のexecution control flow（`execute_dispatchable_retries()`を呼ぶ回数は正確に1回）はそのまま維持し、取得済みの`execution_results`を`self.manager.decide_retry_queue_updates(execution_results)`へ渡す。

**member_run_id → root_run_idの一意性契約**：`src/retry_lineage/retry_lineage_manager.py`は以下の設計により、この一意性を保証する——

- `find_by_member_run_id(candidate_run_id: str) -> str | None`：全lineageを線形走査し、最初に一致した`root_run_id`（単一値）を返す公開API。§22.1e節Layer 1（`RetryEnqueueTrigger.enqueue_pending_failures()`）は、この単一値の戻り値を追加の曖昧性検証なしにauthoritative lookupとして使用する。
- `create_new_lineage()`は、新規lineage作成時にグローバルmembership一意性チェックを実行し、既に他のlineageのroot/membershipとして記録されているrun_idでの新規lineage作成をfail-closedで拒否する。run_idのglobalな一意性は本システムの明示的な設計意図（named invariant）である。
- `mark_execution_started()`は、attempt実行のrun_id（`WorkflowEngineManager._generate_run_id()`が発行する`uuid.uuid4().hex`、毎回新規生成・再利用されない）を対象lineageの`membership`へ追記する際、上記と同型の再検証は行わない——この追記されるrun_idは常に新規UUID4であり、既存のいかなるlineageのroot/membershipとも衝突しない前提（26章Non-Recycle・append-onlyの設計と整合）で動作する。

member_run_id → root_run_idの一意性は、(a) lineage作成時点でのグローバル一意性チェック、(b) 実行時run_idがUUID4で毎回新規発行され再利用されないという設計、(c) Layer 1が既にこの単一値契約を無条件に信頼して動作する設計、の3点により成立する不変条件である。`mark_execution_started()`自体はmember追記時に再検証を行わないため、この一意性はcreate時のチェック＋run_id生成規律による設計上の保証であり、あらゆる書き込み経路で冗長に再検証される強制invariantではない——この前提が崩れる状況（durable data corruption等）は、`peek()`のNone復帰という別経路でfail-closedに検出する（後述）。

**typed per-item request**：

```python
@dataclass(frozen=True)
class RetryQueueDecisionRequest:
    """decide_all()の各要素。execution_resultとdecision_inputを単一の型で
    bindすることで、2つのparallel listをインデックスで対応付ける設計
    （順序不一致・要素数不一致によりmember/run identityが取り違えられる
    リスクを持つ）を構造的に排除する。"""
    execution_result: "RetryExecutionResult"
    decision_input: "RetryQueueDecisionInput"  # 22.4節のdiscriminated union
                                                 # （LineageAuthoritativeDispositionInput
                                                 #  | LegacyQueueDecisionInput）
```

**`RetryQueueUpdateDecider.decide_all()`のシグネチャ変更**：

```python
def decide_all(
    self, requests: "Sequence[RetryQueueDecisionRequest]",
) -> list["RetryQueueUpdateDecision"]:
    """各requestについて、既存のdecide()相当のロジック（22.4節）を
    request.execution_result・request.decision_inputへ適用する。
    parallel listの単純zip（zip(execution_results, queue_decision_inputs)等）は
    禁止する——1要素でも数・順序が食い違えば、あるexecution resultへ別の
    lineageのdecision_inputが誤って適用されうるため（member/run identityの
    取り違え）。各requestは自己完結した
    単一の単位として扱う。`RetryRuntimeOrchestrator.run_once()`は`decide_all()`を
    直接呼ばず、`self.manager.decide_retry_queue_updates(execution_results)`
    経由に一本化する（22.3.6・22.4a節）。"""
    return [
        self.decide(request.execution_result, request.decision_input)
        for request in requests
    ]
```

**builder：`build_retry_queue_decision_requests(execution_results, lineage)`（唯一の構築点、モジュール関数）**：

```python
def build_retry_queue_decision_requests(
    execution_results: "Sequence[RetryExecutionResult]",
    lineage: "RetryLineageManager",
) -> list["RetryQueueDecisionRequest"]:
    """RetryManager.decide_retry_queue_updates()が、取得済みのexecution_results
    から構築する唯一の関数。lineage引数はRetryManagerがコンストラクタで
    保持するself._lineageをそのまま渡す。
    parallel listのインデックス対応には一切依存しない。"""
    requests: list["RetryQueueDecisionRequest"] = []
    for execution_result in execution_results:
        member_run_id = execution_result.workflow_engine_result.run_id
        root_run_id = lineage.find_by_member_run_id(member_run_id)  # 既存API、str | None

        if root_run_id is None:
            # 正式なpre-6.32/legacy：いかなるlineageのmemberでもないrun_idは、
            # legacy execution（Retry Lineage契約外）として明示的にLegacyQueueDecisionInput
            # を選択する（18章、22.4節と同一原則）。
            requests.append(RetryQueueDecisionRequest(
                execution_result=execution_result,
                decision_input=LegacyQueueDecisionInput(),
            ))
            continue

        record = lineage.peek(root_run_id)  # 既存API（retry_lineage_manager.py:149-151）、read-only
        if record is None:
            # find_by_member_run_id()がroot_run_idを解決した直後にpeek()がNoneを返す
            # ことは、上記の一意性前提（lineage作成時グローバルチェック＋UUID4再利用なし）が
            # durable data corruption等で崩れた場合にのみ発生しうる。legacyへ推測せず
            # contract failureとする（No Automatic Repair、26章と同型の規律）。
            raise RetryQueueUpdateContractError(
                f"find_by_member_run_id({member_run_id!r}) resolved root_run_id="
                f"{root_run_id!r}, but peek({root_run_id!r}) returned None; "
                "refusing to infer legacy behavior."
            )

        # 18.1節のclassify_contract_version_evidence()を唯一のpredicateとして使う
        # （本builder独自の`is None`/`< 1`比較は重複実装しない）。
        evidence = classify_contract_version_evidence(record)
        if evidence == ContractVersionEvidence.LEGACY:
            requests.append(RetryQueueDecisionRequest(
                execution_result=execution_result,
                decision_input=LegacyQueueDecisionInput(),
            ))
            continue

        if evidence == ContractVersionEvidence.INVALID:
            # invalid contract-version evidence：18.1節が定めるとおり、
            # 0・負値・malformedはlegacyへ推測せずcontract failureとしてfail-closedする。
            raise RetryQueueUpdateContractError(
                f"lineage {record.root_run_id!r} has invalid side_effect_contract_version="
                f"{record.side_effect_contract_version!r}; refusing to infer legacy behavior."
            )

        # ここに到達する時点でevidence == ContractVersionEvidence.PROTECTED。
        if record.terminal_disposition is None:
            # required disposition missing：6.32 contract対象lineageのはずが、
            # mark_terminal()が未確定のままqueue-updateへ到達した——22.4節
            # build_queue_decision_input()と同一のcontract failure。
            raise RetryQueueUpdateContractError(
                f"lineage {record.root_run_id!r} is a 6.32 contract lineage but reached "
                "queue-update without an authoritative terminal_disposition; refusing to "
                "infer legacy behavior."
            )

        requests.append(RetryQueueDecisionRequest(
            execution_result=execution_result,
            decision_input=LineageAuthoritativeDispositionInput(
                terminal_disposition=record.terminal_disposition,
            ),
        ))
    return requests
```

**`RetryManager.decide_retry_queue_updates()`のシグネチャ変更（実装契約）**：

```python
# src/retry_engine/retry_manager.py
# decide_retry_queue_updates()の唯一の呼び出し元はrun_once()である。
# execute_dispatchable_retries()を内部で再実行しない——呼び出し元が
# 既に取得済みのexecution_resultsをそのまま受け取る。

def decide_retry_queue_updates(
    self, execution_results: list["RetryExecutionResult"],
) -> list["RetryQueueUpdateDecision"]:
    """呼び出し元（run_once()）が既に取得済みのexecution_resultsを受け取り、
    execute_dispatchable_retries()を再実行しない——run_once()の既存invariant
    「execute_dispatchable_retries()を2回以上呼ばない」を維持する。
    self._lineage・self._queue_update_decider
    はいずれも既存のコンストラクタで既に保持されているフィールドであり、
    新規の依存注入は不要。"""
    requests = build_retry_queue_decision_requests(execution_results, self._lineage)
    return self._queue_update_decider.decide_all(requests)
```

`NullRetryManager.decide_retry_queue_updates()`（`retry_manager.py:775-782`）も同一シグネチャへ変更し、`execute_dispatchable_retries()`と同様に常に空リストを返す（他コンポーネントへの参照を一切保持しない既存の設計原則、713-782行目と同型）。

**`RetryRuntimeOrchestrator.run_once()`の実装契約**：

```python
# src/retry_runtime_orchestrator/retry_runtime_orchestrator.py
execution_results = self.manager.execute_dispatchable_retries(events, dry_run=dry_run)
decisions = self.manager.decide_retry_queue_updates(execution_results)
```

`execute_dispatchable_retries()`を呼ぶ箇所は本メソッド内で1箇所のみであり、`run_once()`自身のdocstringが定める既存invariant（「execute_dispatchable_retries()を2回以上呼び出す変更は行わないこと」）を維持する。`run_once()`のその他の処理（`reconcile_all()`・`trigger.enqueue_pending_failures()`・`scheduler.run_due()`・`RetryQueueRemovalExecutor`以降の後続処理・`RetryRuntimeCycleResult`の構築）は本節の対象外とする。

**legacy fallback禁止**：上記builderのいかなる分岐も、member/run解決の失敗・contract-version異常・disposition欠落を「pre-6.32 legacyとして扱ってよい」根拠にしない——legacyを選択できるのは、`find_by_member_run_id()`が`None`を返す場合（そもそもいかなるlineageのmemberでもない）または`side_effect_contract_version is None`（明示的にlegacy契約下にあると確認できる）の場合のみであり、それ以外の異常はすべて`RetryQueueUpdateContractError`とする（2章・22.4節のdiscriminated union原則と同型）。

**No bypass**：production（`src/`・`scripts/`）において、`RetryQueueUpdateDecider.decide_all()`を`run_once()`等から直接呼ぶ経路を持たない——canonical production entry pointは`RetryManager.decide_retry_queue_updates(execution_results)`のみとする。単体テストがDeciderを直接呼ぶことは許容する（28.-18節参照）。

**Retry Trigger/Eligibilityからの除外（2層防御）**：22.1e節が定める**Layer 1**（`RetryEnqueueTrigger.enqueue_pending_failures()`のmembership-first除外、正常経路ではそもそも再enqueueされない）と**Layer 3**（16章`open_next_attempt()`の`hrr_authorized`判定——`RETRY_ALLOWED`resolutionが記録されていない限りHRRを拒否する、22.1c節）の2層により、HRRのlineageが自動retry対象として再選定される経路を構造的に持たない。HRR終端のQueue項目自体は本節（22.4節）の`decide()`により既存の`FAILED`へ合流し、既存の除去（Removal）経路をそのまま通る（Layer 2、22.1e節）——HRR専用のQueue状態・cleanup経路を新設しない。「正常経路では再enqueueされないこと」がprimary contract（Layer 1）であり、「万一再enqueueされても、`RETRY_ALLOWED`resolutionが記録されていない限り実行には至らないこと」（Layer 3）はそれに対するdefense-in-depthである（22.1e節）。

---

## 23. Reconciliation Priority

`_reconcile_all_locked()`内での処理順序（6.31から不変、6.32はロジック内容のみ変更）：

1. `phase==EXECUTION_STARTED`の解決（12.2節、side-effect safety合成込み）
2. `phase==TERMINAL and terminal_disposition in (FAILED, NOT_ACTIONED)`の`open_next_attempt()`（HRRは対象外、13章）
3. `phase==CLAIMED`のorphan回収（6.31、無変更）

**優先順位が重要な理由**：ステップ1で新たに`HUMAN_REVIEW_REQUIRED`が確定したlineageは、同一`reconcile_all()`呼び出し内の直後のステップ2では`phase==TERMINAL`かつ`terminal_disposition==HUMAN_REVIEW_REQUIRED`であるため、ステップ2の対象条件（`in (FAILED, NOT_ACTIONED)`）に自動的に該当せず、**同一サイクル内でHRR確定と自動Retry再開が同時に起きることはない**。この不変条件は独立検証の対象とする。

---

## 24. Disposition Precedence

1. `SideEffectSafetyCategory`が`IN_PROGRESS_OR_UNKNOWN`または`CONTRACT_VIOLATION` → 無条件に`HUMAN_REVIEW_REQUIRED`
2. 上記に該当せず、`CONFIRMED_SUCCESS`かつ`base_disposition != SUCCEEDED` → `HUMAN_REVIEW_REQUIRED`
3. 上記いずれにも該当しない → `base_disposition`

12.2節のAbsence/Evidence Decision Tableにより、`CONTRACT_VIOLATION`は「レコード破損」だけでなく「到達可能性を否定できないmarker欠落」も含む。

---

## 25. Defense-in-Depth Invariants（全40件）

1. **durable write-ahead ACK前のexternal I/O禁止**：9.9.1節（`MEDIA_UPLOAD`のPREPARED/IO_ARMED境界定義）・15.4/15.6/15.7節（呼び出し箇所A/B/CのOrdering Contract）。
2. **duplicate create要求のfail-closed拒否**：9.4節（`create_attempted()`のduplicate検出）。
3. **compare-and-transitionによる不正遷移の拒否**：9.4節（`transition_to_confirmed()`のexpected-state/member_run_id/identity検証）。
4. **identity/member_run_id mismatchのfail-closed化**：9.7節・12章。
5. **unresolved HRRからの`open_next_attempt()`禁止（二重ガード）**：16章。
6. **reconciliationに「marker absence=safe」というdefaultを置かない**：12章。
7. **Human resolutionはdurable one-shot resolutionとして保持され、自動解除・自動retry・自動re-enqueueを一切行わない**：`resolve_human_review()`は、既存の`RetryLineageStore`/`RetryExecutionLock`をそのまま用いて`human_review_resolution`（`RETRY_ALLOWED`または`ABANDONED`）を一度だけdurableに記録する（同一decisionの再送はidempotent success、異なるdecisionはfail-closedで拒否、17.2節）。`open_next_attempt()`は、`human_review_resolution.resolution == RETRY_ALLOWED`の場合に限り次attemptを開く——この経路は`open_next_attempt_after_human_review()`という明示的なmanual呼び出しからのみ到達し、自動reconciliation sweep（`_reconcile_all_locked()`）はresolutionの有無に関わらずHRR lineageに対し`open_next_attempt()`を呼ばない（16・17・19章）。次attemptが開かれる際、`terminal_disposition`は常に既存の1回のwhole-record atomic saveの中で`None`へクリアされる。`human_review_resolution`は経路によって扱いが異なる——通常の非HRR path（`FAILED`/`NOT_ACTIONED`からの再open）では、`human_review_resolution`はそもそも存在しない（`None`のまま）。HRR authorized path（`hrr_authorized`成立時）では`human_review_resolution`はクリアされず、`RETRY_ALLOWED`のまま`opened_attempt_no`へ新attempt番号を記録した状態でopen→dispatchのcrash-resumable markerとして保持され、`mark_execution_started()`が当該attemptの実行開始を実際に確認した時点で初めて`None`へクリアされる（17.2節）。「過去attemptがHRRに到達した」という事実は、この最終的なclearより前に`mark_terminal()`が`transition_history`へappend-onlyで記録済みのevidenceとして永続する（16章）。
8. **terminal recordの非recycle（identity分離＋transition validationの二重保証）**：26章。
9. **arbitrary record replacement APIを公開しない**：9.4節（Store公開APIはcreate/compare-and-transition/getのみ）。
10. **compare-and-swapのatomicity保証**：27章。
11. operationレベルのdurable evidence（`NOT_APPLICABLE`）は、stepレベルの粗い判定より優先されるが、`MediaUploadApplicabilityStore.create()`（`MEDIA_UPLOAD`側、9.9節、能動的に使用中）自体もduplicate検出・fail-closedなACK契約の対象である（`WordPressDraftStateStore.create_not_applicable()`は6.32 current APIには存在しないため、本項は`MEDIA_UPLOAD`側の対応する仕組みを指す、9.3節）。
12. **`NOT_APPLICABLE`はACKされて初めてauthoritativeとなり、ACK失敗は「正常なNOT_APPLICABLE確定」として扱わない**（9.6・12.4節）。
13. **reconciliation・classifyは、いかなる場合も現在のGate/config（環境変数等）を再評価しない。durable recordのみを権威とする**（10.3節）。
14. **operation-level evidence優先の設計でも、record自身の内部整合性（identity・member_run_id・schema）に関する矛盾は無視せず`CONTRACT_VIOLATION`とする**（12.5節）。record外部の事実との突合はOut of Scope（4章）として明示的に境界線を引く。
15. **`MEDIA_UPLOAD`の全durable state変更は、単一の`MediaUploadSafetyCoordinator`（Shared Coordination Boundary）を経由する。書き込み時はlock内での2 store確認、読み取り時は両store確認＋矛盾検出のいずれも欠かさない**（9.9節）。
16. **（Shared Coordination Lockのserialization保証範囲）** Coordinatorのshared coordination lock（同一side-effect identityに対する`MediaUploadSafetyCoordinatorLock`）は、**同一identityへのcompeting durable mutationsをserializeする**——同一identityに対する複数のcritical section（`_run_with_commit_aware_lock()`のbody実行区間）が同時にoverlapしないことのみを保証する。**1つのlock保持区間内で、複数storeへの逐次durable write（sequential write）を行ってよい**——`PREPARED`（`MediaUploadAttemptContextStore`）→`ArticleMediaUploadState` `ATTEMPTED`（`article_media_upload_state`）→`IO_ARMED`（`MediaUploadAttemptContextStore`）という、9.9.3節Write-ahead Ordering Contractのcross-store sequential writesは、この設計の正式な契約である（9.9.3・9.9.4.4節`record_attempted()`が示すとおり）。**shared lockはrace prevention boundaryであり、cross-store transaction・atomic commitではない**——lockが複数storeを1つの原子的操作として保証することはなく、途中でのクラッシュにより一部storeのみ書き込まれた部分的なdurable evidence（partial durable evidence）が生じうる。この部分的evidenceは、9.9.5節Crash Semantics・9.9.7節Cross-Store Combination Table・12章Decision Tableに従い、`SAFE_TO_CONTINUE`（安全にI/O未実行と確認できる中間状態）／`IN_PROGRESS_OR_UNKNOWN`（HRRへ、外部I/O開始の可否が確認できない場合の意図的な受容窓）／`CONTRACT_VIOLATION`（想定されない組み合わせ）のいずれかへ、fail-closedに解決される（9.9.1〜9.9.7・12・27章）。
17. **read時のexpected_member_run_idは、side-effect record自身からではなく、常にRetry Lineageの権威ある状態（`WorkflowEngineResult.run_id`または`RetryLineageRecord.latest_run_id`）から供給される**（10.2節）。
18. **No Automatic Repair：reconciliationは矛盾・欠落を検出したら常に`CONTRACT_VIOLATION`とし、推測による補完・再生成を一切行わない**（9.9.6節）。
19. **durably表現する境界は「呼び出しの成否」ではなく「external I/O開始の可否」自体（`IO_ARMED`）とする**（9.9.1節）。
20. **ACK Determinism：durable commitのACK確定後、副次的な処理の失敗によって成功結果を巻き戻して報告しない。ただしcommit ACK自体が不明な場合はfail-closedのまま維持する**（9.9.6節）。

21. ACK Determinismは、durable commitを行う全メソッド（`WordPressDraftStateStore`・`MediaUploadSafetyCoordinator`双方）に、単一の共通ヘルパー（Commit-Aware Lock Helper）を通じて一律に適用する（9.9.4節）。個々のメソッドが独自にlock/cleanup処理を実装しない。
22. post-commit cleanup失敗の診断（`cleanup_diagnostics`）は、disposition判定・Cross-Store Combination Tableのいずれにも影響しない。分類は常にdurable stateの直接読み取りのみに基づく（9.9.9節）。
23. `commit_state["committed"] = True`設定後にbody自身が例外を送出しても、helperのexcept節がcommitted状態を確認し、durable commitの成功を維持する（9.9.4.3節）。「committed後は代入のみ」という実装規律（9.9.4.4節）と、helper側の防御的なexcept節確認（9.9.4.3節）の二重の保護として設計する。
24. fail-closedな不変条件検査は、`assert`文（最適化フラグで無効化されうる）ではなく、常に実行される明示的な条件分岐＋例外送出として実装する（9.9.4.3節）。
25. durable semantic ACKと`committed=True`の間に、例外を送出しうる任意処理を置かない、という順序規律を4メソッド全てに一律適用する（9.9.4.4節の表、`record_prepared()`を含む）。
26. `Exception`（通常のapplication/cleanup failure）と、`KeyboardInterrupt`/`SystemExit`等のprocess-control/cancellationを表す`BaseException`は、明確に異なる扱いをする。後者はsemantic commitの成否に関わらず、cleanupをbest-effortで試行した上で必ず再送出し、決して成功結果へ変換しない（9.9.4.3節）。
27. cleanup診断情報（`CleanupDiagnostic`）は、`reason_code`・`exception_type`・`operation_kind`・`effect_site`・`occurred_at`の5フィールドに限定する。例外メッセージ本文等はいかなる状況でも含めない（9.9.4.5節）。
28. 診断情報を構築する関数（`_build_cleanup_diagnostic()`）自体は、いかなる内部計算が失敗しても、外部へ例外を伝播させない（9.9.4.3節）。個々のフィールド計算のtry/exceptで保護する。
29. post-commit成功経路で、body側の戻り値構築が失敗し`commit_state["value"]`が未設定のまま返った場合、公開メソッドは`None`を返さず、durable stateを読み直して権威あるrecordを再構築する（9.9.4.4節`_value_or_recover()`）。
30. durable stateの読み直し（`_value_or_recover()`段2）は、post-commit cleanup失敗でstale化しうる`MediaUploadSafetyCoordinatorLock`を再取得しない。lockを取得しない`self._read_all()`を直接呼ぶ（9.9.4.4節）。
31. 診断情報構築の最終防衛線（フォールバック）は、失敗しうる同じコンストラクタ・同じ計算経路に依存しない。真に独立した、原則として失敗しえない経路（`None`）で構成する（9.9.4.3節）。
32. post-commit経路での戻り値復旧は単一の手段に頼らず、独立した複数段のfallback（構築済み値→lockなしdurable read→追加I/Oなしの合成値）として構成する。いずれかの段が失敗しても、必ず次の段へフォールスルーし、最終段は外部依存を一切持たないため原則として失敗しえない（9.9.4.2・9.9.4.4節`_value_or_recover()`・`_minimal_safety_record()`）。
33. **設計書中の擬似コードは、実装時にそのまま参照される可能性を踏まえ、構文的に妥当な状態を維持する**——独立した完全モジュールとして示されるコードブロックは、コピーしてそのまま解釈できることを要求する。クラス本体を伴わない単独メソッド定義等、意図的にインデントされた部分snippetとして示されるコードブロックは、周囲の文脈（囲むクラス）を保った状態でのcontext-preserving dedent（`textwrap.dedent()`相当）後に構文的に妥当であることを要求する。Editによる部分置換後は、置換前後の境界に断片が残っていないか確認する（オラクルは28.-25節、dedent適用）。
34. 実行provenanceを表すdiscriminated union（`RetryLineageProtectedExecutionContext`/`LegacyDirectExecutionContext`）は、trusted composition boundaryから常に明示的に供給される。いかなる呼び出し経路も、値の欠落（`None`）を「legacyとして扱ってよい」根拠にしない——欠落・型不一致・宣言との矛盾はすべて`SideEffectExecutionModeContractError`によるhard failureまたはCONTRACT_VIOLATION（識別可能な場合）とし、silent downgradeを構造的に排除する（2章）。
35. `WORDPRESS_DRAFT_CREATION`はNEWS_STEP（呼び出し箇所A、15.7節）・PUBLISH_STEP（呼び出し箇所C、15.6節）の両方で発生しうるが、いずれも§9の同一`WordPressDraftStateStore`/`WordPressDraftStateManager`を再利用し、8章のidentity（`effect_site`を含む）により構造的に別recordとして扱われる。呼び出し箇所A・B・C（1.2節）のいずれも、write-ahead契約の対象から漏れることのないよう、22章のExact Integration Pointsで網羅的に列挙する（22.1f・22.1c・22.3節）。この網羅性は、22章の（既知symbolのimport/呼び出し検出に基づく）entrypoint/call-graph closureに加え、28.-34節が定めるRelease 6.32 closed WordPress-mutation transport policyに対するreceiver非依存のsink-oriented static oracle（28.-34節#4、6.32 scope）によっても独立に検証される——このオラクルはreceiver（変数の型・取得経路）を判定条件とせず、`.post`/`.put`/`.patch`/`.delete`/`.request`/`.urlopen`というメソッド名・呼び出し形と`Request(...)`構築のみに基づいて候補を識別し、動的/解決不能なmethod名は無条件でcandidateとして扱う（fail-closed）ため、別名のuploader・新規の直接HTTP呼び出しが追加されても、known symbolリストへの追加漏れによっては検出をすり抜けない。このpolicyが列挙しないtransport mechanism（別のHTTPクライアントライブラリ等）を用いた実装は、本invariantの自動検出範囲外であり、それ自体が22.2節No Bypass Proofの規律の対象となるcontract violationである——arbitrary未来のtransport実装を本テストのみで完全検出できるという主張はしない。
36. `WORDPRESS_DRAFT_CREATION`のevidence（`WordPressDraftStateManager`が管理）と`MEDIA_UPLOAD`のevidence（`MediaUploadSafetyCoordinator`が管理）は、`operation_kind`が異なるため常に別identityの別recordであり、一方のevidenceを他方の代用として参照する経路を持たない（10.1節Operation Applicability原則、15.7節）。
37. **（formal invariant、3段階の責務分離）** A protected side-effect operation MUST derive its identity and execution mode from the authoritative run-scoped side-effect execution context（discriminated union、2.1節）。この保証は以下の3段階の責務分離として成立する：**(1) Consistency validation boundary**（`RetryExecutor.execute()`が`RetryLineageRecord`/claimから`RetryLineageProtectedProvenance`を構築した直後、2.2節）で、構築した`root_run_id`・`attempt_ordinal`・`side_effect_contract_version`が、`RetryExecutor`自身が保持する既存のRetry Lineage authority（`lineage.root_run_id`・`claim.attempt_no`・`RetryLineageRecord.side_effect_contract_version`、いずれも既存field）と一致することを直接照合する——individually well-formedな値であっても、この時点で構築元のlineage/claimと一致しなければfail-closedする（2.2a節(1)）。**(2) Member completion boundary**（`WorkflowEngineExecutor`が(1)を通過したvalidated pre-contextへ`member_run_id`を補完し`RetryLineageProtectedExecutionContext`を完成させる時点、2.1a節protected factory）では、`lineage`/`claim`への参照を持たないため(1)の3値を再照合せず、そのまま不変で引き継ぐ——`WorkflowEngineExecutor`の責務は`member_run_id`（自身が発行した`run_id`のみ、caller供給値によるoverride禁止）の補完のみに限定される（2.2a節(2)）。**(3) Downstream propagation boundary**（`WorkflowEngineManager.run()`・`AgentContext`・NEWS/PUBLISH pipeline runner・subprocess境界・`WorkflowTriggerAgent`→`WorkflowPipelineRunner`→`WorkflowRunner`→`WorkflowContext`→`PublishStepExecutor`のchain、2.6節）では、(2)で完成したcontextをlossless transportするのみとし、第二の独立したauthorityを新設しない——downstream boundaryの責務は、missing/unknown/malformed contextのfail-closed・correlation metadataからの再構築禁止・protected⇔legacy間の変換禁止・upstream contextの置換禁止に限定される（downstream boundaryが独立にwell-formedなprotected identityの矛盾を検出する責務は持たない——比較対象となるauthorityが存在しないため、この要求は課さない）。scheduler event metadata（`WorkflowEngineEvent.metadata`）・arbitrary task params（`AgentTask.params`）・ambient environment state（明示的に検証された環境変数を除く、14.3節）からの再構築・推測はいずれの段階でも禁止する。
38. **（formal trust-boundary invariant、2.1節）** Execution provenance is established exactly once at a trusted composition boundary and transported as a typed immutable value. Downstream components MUST NOT infer, upgrade, or downgrade execution provenance from missing fields, scheduler/event metadata, arbitrary params, correlation metadata, operation_instance_key history, or general ambient state. **唯一の明示的authorized reconstruction boundary**は、main.pyの`_parse_execution_context_from_env()`（14.3節）——subprocess境界を越えて`_serialize_execution_context()`がシリアライズした、明示的に定義されたenvelope変数（mode discriminator・protected 4変数・legacy 2変数）のみを読み取り、trusted composition rootとして自らprovenanceを再構成する、この1箇所のみである。これは「downstream componentがambient stateから推測する」ことの例外ではなく、trusted composition boundary自身がsubprocess境界越しに自己のprovenanceを再確立する行為であり、それ以外のいかなるboundary（`WorkflowEngineManager.run()`・`AgentContext`・NEWS/PUBLISH pipeline runner・`WorkflowTriggerAgent`→`WorkflowPipelineRunner`→`WorkflowRunner`→`WorkflowContext`→`PublishStepExecutor`のchain等）でも、新規のprotected/legacy contextインスタンス構築は一切発生しない（**new protected context construction = 0**、この唯一の例外を除く全boundaryで直接検証、28.-14節#19・28.-36節#12）。trusted composition root自身が誤ったfactoryを選択するprogramming defectをside-effect呼び出し箇所だけで完全検出できるという保証はこの設計に含まれない——型分離（`RetryLineageProtectedExecutionContext`/`LegacyDirectExecutionContext`が互いにフィールドを共有しない）・closed-set origin・網羅的wiring testsの3層で防ぐ（2.1節）。
39. **（fan-out境界のprovenance完全性）** `AgentManager.run()`が単一呼び出し内で複数の`AgentExecutor`をfan-outする場合、各executorは自分専用に完成させた別個の`LegacyDirectExecutionContext`インスタンス（`legacy_execution_origin`が自分自身のAgent型と一致するもの）を受け取る。他executor向けに完成させたインスタンスを共有・使い回すことは行わない（2.3・2.6節）。`AgentManager.from_config()`が構築するAgent型のうち、`LegacyExecutionOrigin`のmapping対応表（2.3節）に存在しない未知の型は、`side_effect_execution_context`を欠落のまま扱い、推測によるmapping・値の使い回しのいずれも行わない——当該executorが実際にprotected operationへ到達した時点でのみ、missing contextとしてfail-closedする（2.4節）。
40. **（formal invariant、4層構成）** Acknowledged durable semantic commit MUST NOT be reclassified into a different semantic kind because return construction, durable reread, or post-commit cleanup failed. `MediaUploadSafetyCoordinator`の4公開メソッドはそれぞれ固有のsemantic kind（`NotApplicableMediaUploadSafetyRecord`/`PreparedMediaUploadSafetyRecord`/`IoArmedMediaUploadSafetyRecord`/`ConfirmedMediaUploadSafetyRecord`、9.9.4.2節のnominally distinctなtyped closed union）のみを返す契約を持ち、`_value_or_recover()`の全フォールバック段（構築済み値・lockなしdurable reread・追加I/Oなしの`_minimal_safety_record()`）は、呼び出し元が自分自身のsemantic kindへ束縛した単一の`RecoveryPolicy`インスタンス（9.9.4.2節、`expected_type`・`build_minimal()`・`validate()`を一体化）のみを用いる。この保証は、Pythonの型システムが変換を物理的に禁止することによってではなく、次の4層の組み合わせによって成立する：(1) 4公開メソッドのexact public return type（9.9.4.4・9.9.4.7節、直接テストは28.-30節#1）、(2) variant-specific internal `RecoveryPolicy`（9.9.4.2節、各Policyクラス自身が`expected_type`以外を構築しないことの直接テストは28.-30節#2・#3）、(3) `_value_or_recover()`の**全段で`policy.validate()`によるruntime `isinstance`検証を必須とする**こと（「構造的に不可能」という過剰な表現は用いない。直接テストは28.-23#14・28.-24#9）、(4) 各公開メソッドが自分自身の正しい`RecoveryPolicy`を選択していることを直接検証するsource/static test（28.-29節）——(1)〜(3)は「渡された`policy`との整合性」を保証するのみであり、「公開メソッドが正しい`policy`を選択したこと」自体は(4)が担保するimplementation trust boundaryである。段1（構築済み値）・段2（durable reread）のいずれかが期待と異なるsemantic kindの値を返した場合も、それをそのまま返さず、secret-safeな固定診断（`_log_recovery_validation_failure()`、9.9.4.4節）を記録した上で次段へフォールスルーする（9.9.4.4節`_value_or_recover()`）。

---

## 26. Non-Recycle Invariant

要求された5つの禁止事項について、それぞれがどのメカニズムで保証されるかを個別に示す。

| 禁止事項 | 保証メカニズム | 説明 |
|---|---|---|
| **terminal → nonterminal**（`CONFIRMED_SUCCESS`から`ATTEMPTED`への逆行） | API形状（構造的に不可能） | `transition_to_confirmed()`は常に`ATTEMPTED→CONFIRMED_SUCCESS`の一方向のみを実装する。逆方向の遷移を行うAPI自体が存在しない。`MediaUploadSafetyCoordinator`側も同様に、`record_confirmed()`から`record_attempted()`へ戻すAPIを持たない（9.9.4.4節）。 |
| **attempt変更**（あるidentityのrecordを別のattempt_ordinalへ「移動」させる） | API形状（構造的に不可能） | `attempt_ordinal`はidentityの構成要素であり、`transition_to_confirmed()`/`record_confirmed()`の引数はidentity全体を再指定するのではなく、既存identityに対する検証済み遷移のみを行う。「recordのattempt_ordinalを書き換える」操作は公開APIに存在しない。 |
| **member_run_id変更** | 明示的なtransition validation | `transition_to_confirmed()`は`expected_member_run_id`と既存recordの`member_run_id`が一致する場合のみ遷移を許可し、遷移後のrecordのmember_run_idは常に元の値のまま保持される（新しい値で上書きするAPIがない）。`MediaUploadSafetyCoordinator`側も`_read_all()`のmember_run_id検証（9.9.4.4節）で同型の保証を持つ。 |
| **operation_kind/effect_site変更** | API形状（構造的に不可能）＋ 永続化パスの一意性 | `operation_kind`・`effect_site`はidentityの構成要素であり、かつ永続化ファイルパス（9.7節、`sha256(identity.as_store_key())`）自体がこれらの値から決定的に導出される。値を変えることは、必然的に**別のファイルパス（＝別のレコード）**を指すことになり、既存recordの「変更」ではなく単なる無関係な新規lookupになる。 |
| **terminal record reset/recycle** | API形状（構造的に不可能）＋ compare-and-swap条件 | `create_attempted()`は既存recordがあればduplicateとして拒否し（9.4節）、`transition_to_confirmed()`は`expected_state==ATTEMPTED`を要求するため`CONFIRMED_SUCCESS`のrecordには一切作用しない。delete/reset相当のAPIも存在しない。`MediaUploadContextPhase`側も同型（`PREPARED→IO_ARMED`の一方向のみ、下記追加）。 |

**結論**：これら5つの禁止事項はすべて、(a) 該当する操作を行うAPI自体を公開しない、(b) identityの構成要素を可変フィールドではなく永続化パスの導出元として扱う、(c) compare-and-swapの前提条件（expected state/member_run_id）を満たさない限り一切の書き込みを行わない、という3つの構造的性質の組み合わせによって保証される。8章の「identityにattempt_ordinalを含める」設計だけに依存するのではなく、9章のStore/Manager API設計そのものが独立した防御層を成す（Defense-in-depth invariant #8、25章）。

**`MediaUploadContextPhase`の遷移制約**：`MediaUploadAttemptContextStore.transition_to_io_armed()`は`PREPARED→IO_ARMED`の一方向のみを実装し、逆方向遷移・reset相当のAPIを一切公開しない（9.9.2節）。これにより「`IO_ARMED`から`PREPARED`へ戻す」「`IO_ARMED`確定済みのcontextを未確定として再利用する」といった操作は構造的に不可能である。

---

## 27. Concurrency / Locking

`src/retry_lineage/retry_lineage_store.py:56-85`が実装するatomic write機構は、`JsonExecutionHistoryStore`由来のパターンを踏襲する。ロック粒度はidentity-scoped化されており（27.5節）、store単位の粗粒度ロックは採用しない。

### 27.1 想定される同時実行

- 通常運用では、あるSide-Effect Operation Identity（8章）に対して書き込みを行うのは、**そのattemptを現在実行中の唯一のプロセス**のみである（identityがattempt_ordinal・effect_site・operation_instance_keyまで一意に絞り込まれているため、他のプロセス・他のlineage・他のattemptがこのidentityへ書き込むことは通常発生しない）。
- ただし、`_reconcile_all_locked()`（15.2節）は`get()`（read-only）を並行して呼びうる。

**Retry Lineage経由実行のグローバル排他保証**：上記の前提は、6.31の`RetryExecutionLock`（`src/retry_lineage/retry_execution_lock.py`）により、Retry Lineage経由の実行については**さらに強い形で保証されている**。`RetryExecutionLock`は「`RetryManager.retry()`と`RetryLineageManager.reconcile_all()`双方にとって唯一の**グローバル**実行時排他境界」（同ファイルdocstring、`retry_lineage_manager.py:585-586`コメントで再確認）であり、`retry_manager.py:426`（`with RetryExecutionLock(...): return self._retry_locked(...)`）・`retry_lineage_manager.py:540`（`with RetryExecutionLock(...): return self._reconcile_all_locked(...)`）のいずれも、ロックが**関数呼び出し全体の実行期間**を包む。ロックファイルパスはidentity単位ではなく単一の共有パス（`execution_lock_path`）であるため、**Retry Lineage経由の実行に関する限り、いかなるidentityへのconcurrent writerも存在しない**（identity単位の排他よりも強い、プロセス全体でのsingle-flight保証）。9.9.4.4節`_value_or_recover()`のlock-free `_read_all()`（27.3節）が前提とする「同一identityへのconcurrent writerなし」は、この事実により完全に満たされる。

**適用範囲の限定（2章Explicit Execution Mode契約との関係）**：この保証はRetry Lineage context（2.2節（RETRY_LINEAGE_PROTECTED））を経由する実行にのみ適用される。2.3節（LEGACY_DIRECT）（Retry Lineage context外の直接/手動/Agent経由実行）は`RetryExecutionLock`を一切取得しないため、この保証の対象外である——これは2.7節のAccepted Residual Riskとして別途扱う。

### 27.2 Atomicityの保証範囲

1. **単一ファイル書き込みのatomicity**：`JsonWordPressDraftStateStore`（22.1b節）は、v6.30 `JsonExecutionHistoryStore`由来・`retry_lineage_store.py`と同型のパターン（`tempfile.mkstemp()` → `fdopen`/`write` → `flush` → `os.fsync(fd)` → `close` → `os.replace(tmp_path, final_path)`）をそのまま踏襲する。これにより、`create_attempted()`・`transition_to_confirmed()`いずれの内部書き込みも、途中経過が観測される（torn write）ことなく、旧内容か新内容かのいずれかが常に読み取られることを保証する。
2. **read-check-writeシーケンスのatomicity（compare-and-swap本体）**：`transition_to_confirmed()`は「既存recordを読む → 条件（identity/member_run_id/state）を検証する → 新recordを書く」という複数ステップから成る。この一連の操作全体を、`WordPressDraftStateStoreLock`で保護し、read-check-writeの間に他の書き込みが割り込むことを防ぐ。**Lock Scope（identity-scoped）**：`WordPressDraftStateStoreLock`はidentity-scopedである——ロックファイルパスを`{base_dir}/.locks/{sha256(identity.as_store_key())}.lock`とし、durable mutationを行う`create_*()`/`transition_to_confirmed()`はいずれも対象identityのロックのみを取得する（27.5節、stale lockが他identityへ波及しない設計）。`get()`はread-onlyかつlock-freeであり、このロックを一切取得しない（27.3節、authoritative）。`MediaUploadSafetyCoordinator`側も同型（durable mutationを行う4公開メソッドは`_run_with_commit_aware_lock()`を経由してidentityロックを取得し、`get()`はlock-free、9.9.4.3・9.9.4.4節、27.3・27.5節）。
3. **`create_attempted()`も同じロックで保護する**：duplicate検出（既存recordの有無を見てから書き込む）自体もread-check-writeシーケンスであるため、`transition_to_confirmed()`と同じロックを使う。

### 27.3 ロックを取得しない操作（lock-free readの根拠、authoritative）

**`get()`はidentity-scoped lockを取得しない（authoritative）。** `WordPressDraftStateStore.get()`・`MediaUploadSafetyCoordinator.get()`のいずれも、対象identityのlockを一切取得せずに読み取る（9.3節・9.9.4.4節の実装がこの契約に従う）。

- **単一store（`WordPressDraftStateStore.get()`）のatomicity保証**：27.2節1.のatomic write pattern（`tempfile.mkstemp()` → `fdopen`/`write` → `flush` → `os.fsync(fd)` → `close` → `os.replace(tmp_path, final_path)`）により、`get()`が読む単一ファイルは常に「ある1回の書き込みの完全な旧内容」または「完全な新内容」のいずれかであり、**torn/partial file stateを読むことは構造的に発生しない**。
- **`MediaUploadSafetyCoordinator.get()`はこの保証をstore単位でのみ持ち、複数store全体へは拡張しない**：`get()`が呼ぶ`_read_all()`（9.9.4.4節）は、`applicability_store`・`attempt_context_store`・`article_media_upload_state`（`ArticleMediaUploadStateManager`経由）という独立した複数のstoreを個別に読む。各storeは自身のファイルについて上記と同一のatomic write patternを持つため、**個々のstoreの読み取り結果はそれぞれtorn/partial stateではない**。しかし、これら複数storeをまとめて読むこと自体は単一の原子的操作（1つのcomposite old-or-newスナップショット）ではない——同一identityへのconcurrent mutation（`record_attempted()`等）が進行中の場合、各storeへの書き込みタイミングのズレにより、あるstoreは新内容・別のstoreは旧内容という組み合わせ（cross-store skew、例：`attempt_context_store`は既に`IO_ARMED`だが`article_media_upload_state`はまだ`ATTEMPTED`更新前）を観測しうる。この可能性は、shared coordination lockがcross-store transactionではないと明記する既存のInvariant #16（25章）・Cross-Store Combination Table（9.9.7節）が既に前提としている正常系であり、本節が新たに弱化するものではない。
- **cross-store skew自体を禁止・一律fail-closed視しない／partial/inconsistent observationを無条件に安全側と推定もしない**：cross-store skewは、それ自体が異常事象ではなく、concurrent mutation進行中に生じうる正常な観測タイミングの結果である。`get()`が観測した組み合わせの意味は、常に既存のCross-Store Combination Table（9.9.7節）が定める**当該組み合わせごとのexactな`SideEffectSafetyCategory`**によって決まる——これは`SAFE_TO_CONTINUE`／`IN_PROGRESS_OR_UNKNOWN`／`CONTRACT_VIOLATION`に限らず、`CONFIRMED_SUCCESS`・`NOT_APPLICABLE`を含む、Tableが定めるいずれの値にもなりうる（例：`IO_ARMED`（旧）＋`CONFIRMED_SUCCESS`（新）というskewは`CONFIRMED_SUCCESS`が正しい分類であり、これをfail-closed側の3分類へ強制的に丸めることは既存契約9.9.7節に反する）。`get()`自身がskewの意味を独自に安全側・危険側と推定することはなく、Tableの個別combination行のみがその責務を負う。undefined／matched contract violation行に該当する組み合わせのみ`CONTRACT_VIOLATION`とし、それ以外を安全側へ丸めることはしない。単一storeのatomic write契約（27.2節1.）を、Coordinator全体のcomposite read atomicityへ拡張して主張しない。
- **linearizabilityは保証しない**：`get()`はlock-freeであるため、呼び出し時点で他のwriterがconcurrentに書き込み中の場合、（各storeについて）`get()`が返す値は「その書き込み完了前の直近のcomplete snapshot」であり得る（stale snapshot）。`get()`が保証するのは「各storeについて読む内容が常にいずれかの時点のcomplete file内容であること（torn状態を返さないこと）」のみであり、「呼び出し時点で最新のconfirmed値であること」も「複数store間で同一時点の整合したcomposite snapshotであること」も保証しない。concurrent writer下でのstale snapshot・cross-store skewの観測はいずれも許容された正常系である。
- 同じ原理により、`MediaUploadSafetyCoordinator._value_or_recover()`の`_read_all()`（9.9.4.4節）もlockを取得しない。27.1節で確認したとおり、Retry Lineage context下では同一identityへのconcurrent writerが存在しないため、lock-free readは安全である。
- stale snapshotの許容はread-only用途（`get()`、reconciliationの初期観測）に限定される。lock-freeなread結果のみを根拠にdurable mutationへ進んではならない——read後にmutationを行う経路の順序契約は27.6節が定める。

### 27.4 デッドロック回避

`WordPressDraftStateStoreLock`（`WordPressDraftStateStoreLock`/`MediaUploadSafetyCoordinatorLock`共通）は、`create_attempted()`/`transition_to_confirmed()`/`record_attempted()`等の呼び出し1回につき取得・解放する短命なロックであり、呼び出し元（main.py・`AiPublishService`）がこのロックを保持したまま他のロック（`RetryLineageStoreLock`・`RetryExecutionLock`）を取得する経路は設計上存在しない（副作用の呼び出し元はlineageの内部ロックを一切意識しない、9章のManager/Store層のみがこのロックを扱う）。

### 27.5 現在のidentity-scoped coordination

**Lock Primitive**：`RetryLineageStoreLock`と同一の実装パターン（`os.open(lock_path, O_CREAT|O_EXCL|O_WRONLY)`、短時間リトライ）を維持する。

**Lock Scope**：Coordinatorは**identity単位のロックファイル**（`{base_dir}/.locks/{sha256(identity.as_store_key())}.lock`）を用いる。`MediaUploadSafetyCoordinator`は`lock_factory: Callable[[identity], MediaUploadSafetyCoordinatorLock]`を受け取り（9.9.4.4節のコンストラクタ）、各メソッド呼び出しごとに対象identity専用のロックインスタンスを構築する。

**採用理由**：粗粒度ロック（store単位）では、あるidentityのpost-commit cleanup失敗が原因のstale lockが、無関係な別identityの操作まで無期限にブロックしてしまうという可用性上の問題がある。この問題を避けるため、identity-scoped lockを採用する（27.5節）。

**Crash Recovery**：あるidentityのlockがstaleのまま残存した場合、`RetryExecutionLock`9.4章と同型のManual Stale Lock Recovery Procedureに従う（PID・timestampを診断目的で記録、自動staleness検出・自動解放は行わない）。**このstale lockが影響する範囲は、当該identityへのdurable mutationメソッド（`MediaUploadSafetyCoordinator`側：`record_not_applicable()`/`record_prepared()`/`record_attempted()`/`record_confirmed()`、`WordPressDraftStateStore`側：`create_attempted()`/`transition_to_confirmed()`）のみに限定される**（別identityへの不要な全体停止を起こさない、27.5節「採用理由」。`record_prepared()`も9.9.4.7節で同一の`_run_with_commit_aware_lock()`／`MediaUploadSafetyCoordinatorLock`経路を使うため、この一覧に含まれる）。**`get()`・read-only reconciliationはこのstale lockの影響を受けない**——`get()`はlock-freeであり（27.3節、authoritative）、stale identity lockが存在してもfail-closedで阻止されず、当該identityの直近のcomplete snapshotを読み取り続けることができる。自動的なlock破棄・推測修復は行わない——運用者が当該PIDのプロセスが実際に存在しないことを確認した上で、該当identityのロックファイルのみを手動削除する。

**性能への影響**：identityごとに個別のロックファイルを持つことで、ファイル数は増加するが（1 lineageあたり、記事数×operation_kind数程度）、6.32のスコープ（1 NEWS step attemptあたり数記事〜数十記事程度）ではディスクI/O・ファイルシステム上のオーバーヘッドは無視できる水準と判断する（29章#26）。

**Lockが保証する範囲の明記**：本ロックはrace preventionの手段であり、複数storeへの書き込みを1つの原子的トランザクションとして扱うものではない。

### 27.6 Reconciliation Safety：Read-Then-Mutate Ordering

`get()`（lock-free、27.3節）が返すsnapshotは、read-only用途（reconciliationの初期観測、外部への状態表示等）にのみ用いてよい。**lock-freeなread結果のみを根拠にdurable mutationへ進んではならない**——read後にdurable mutationを行う経路は、必ず以下の順序に従う：

1. 対象identityのidentity-scoped lockを取得する（`WordPressDraftStateStoreLock`／`MediaUploadSafetyCoordinatorLock`、27.5節）。
2. lock保持区間内で、authoritative stateを再読する（lock-freeな`get()`のsnapshotをそのまま使わず、`_read_all()`等によるlock内readを行う）。
3. 遷移前提条件（expected state・member_run_id・identity一致等）をlock保持区間内で再検証する。
4. 検証を通過した場合のみdurable mutationを実行する。

この順序は、`create_attempted()`・`transition_to_confirmed()`（9.3〜9.4節）・`record_not_applicable()`/`record_prepared()`/`record_attempted()`/`record_confirmed()`（9.9.4.4節）がいずれも既に踏襲しているread-check-write-under-lock契約（27.2節2.）と同一である。本節は新しい実装機構を追加するものではなく、「lock-freeな`get()`のsnapshotを直接mutation判断へ流用する経路を新設しない」という既存契約の明示化である。

**適用範囲の限定（side-effect storage domainのみ）**：本節が定める順序契約は、side-effect storage domain（`WordPressDraftStateStore`・`MediaUploadSafetyCoordinator`が管理する対象identityのdurable state、いずれも本節が扱う`WordPressDraftStateStoreLock`／`MediaUploadSafetyCoordinatorLock`の対象）内で完結するread-then-mutate経路にのみ適用される。`RetryLineageManager.open_next_attempt()`・`_reconcile_all_locked()`（15.2節・16章）は、別domain（Retry Lineage record、`RetryExecutionLock`／`RetryLineageStoreLock`、27.1節）に属する既存の独立した契約であり、本節が定めるidentity-scoped lockを用いた順序契約の一事例ではない——本節の対象外として明示的に扱う。reconciliationがside-effect側の`get()`結果を観測した上でRetry Lineageのdurable mutation（`open_next_attempt()`等）へ進む経路の正しさは、Retry Lineage側の既存契約（16章`open_next_attempt()`自体が`_store_lock()`内でlineage recordを再読・前提条件を再検証すること）にのみ依拠し、本節はこれについて何も主張しない。

---

## 28. Test Strategy / Test Matrix

### 28.-8 Retry Queue Update整合・Disposition優先順位1 必須テスト（8件）

| # | シナリオ | 検証項目 |
|---|---|---|
| 1（29章#1） | 6.32 contract対象lineageで`mark_terminal()`が`terminal_disposition=HUMAN_REVIEW_REQUIRED`を確定させた後、`RetryQueueUpdateDecider.decide()`を`queue_decision_input=LineageAuthoritativeDispositionInput(terminal_disposition=HUMAN_REVIEW_REQUIRED)`で呼ぶ | `RetryQueueUpdateOutcome.FAIL`・`target_status=RetryQueueStatus.FAILED`が返ること（22.4節、HRR専用のQueue状態は追加しない） |
| 2（29章#1） | 同上の状況で、`decide_disposition(workflow_engine_result)`ベースの独立再計算では`SUCCEEDED`相当になりうる状況（workflow step自体は全て成功）を人為的に作る | `queue_decision_input`が権威ある`terminal_disposition=HUMAN_REVIEW_REQUIRED`を渡している限り、`decide()`の戻り値`outcome`は`decide_disposition()`の再計算結果に関わらず`FAIL`のままであること（優先順位1・24章が要求するsafety-evidence優先の判定が、Queue側の独立再計算によって`COMPLETE`へ誤って倒れないことの直接確認） |
| 3（29章#1） | `FAIL`終端のQueue項目に対し、`RetryQueueRemovalExecutor.apply()`を呼ぶ | 既存の`_REMOVABLE_OUTCOMES`（無改修）に含まれるため除去対象となり、`remove_fn`が呼ばれること（22.1d節） |
| 4（29章#1、Layer 1・正常経路） | `HUMAN_REVIEW_REQUIRED`終端のlineageの各attempt run_idが、`WorkflowMonitorManager`上に`FAILED`/`TIMEOUT`として観測される状態で、`RetryEnqueueTrigger.enqueue_pending_failures()`（`lineage`が正しく注入された状態）を実行する | `RetryQueueManager.enqueue()`の呼び出し回数が0であること（`skipped_lineage_member`としてカウントされること）。**enqueue call/count = 0**（22.1e節Layer 1、primary contract） |
| 4b（29章#1、Layer 2、既存sibling stageとしてのexact確認） | HRR由来の`RetryQueueUpdateDecision`（outcome=`FAIL`、#1で確定）を、実際のsibling stage構成（`run_once()`と同一の配線、22.4a節）で個別に流す：(i) `RetryQueueRemovalExecutor.apply_all([decision], remove_fn=...)`を直接呼ぶ、(ii) 同一decisionを`RetryQueueCleanupDecider.decide()`へ直接渡す、(iii) 同一decisionを`RetryQueueTerminalCleanupDecider.decide()`へ直接渡す | (i) `RetryQueueRemovalExecutor`が`outcome=FAIL`を既存の`_REMOVABLE_OUTCOMES`（無改修）に基づき除去対象と判定し、`remove_fn`を呼ぶこと——HRR由来のQueue除去は**このsibling stageのみ**が担うことを直接確認する。(ii)(iii) `RetryQueueCleanupDecider`・`RetryQueueTerminalCleanupDecider`はいずれも`outcome != NOOP`（`FAIL`はNOOPではない）という既存判定により`KEEP`を返し、`remove_fn`を一切呼ばないこと（cleanup decider自身がRemovalExecutorを呼ぶ、という前提は採用しない——両deciderはFAIL outcomeに対して常にno-opであり、除去は(i)のsibling stageが独立に行う）。この3つの独立したassertionにより、`RetryQueueCleanupDecider`・`RetryQueueTerminalCleanupDecider`（22.1d節がゼロ変更を要求する対象）が実際に無改修のまま正しく動作し、22.1d節のzero-HRR-change contractと矛盾しないことを直接証明する |
| 4c（29章#1、Layer 3・defense-in-depth） | `RetryEnqueueTrigger`の`lineage`引数を意図的に`None`にする、または`find_by_member_run_id()`が誤って`None`を返す状況を人為的に作り、`HUMAN_REVIEW_REQUIRED`終端lineageのrun_idが`RetryQueueManager.enqueue()`される（＝Layer 1が破られた）状態を模擬したうえで、`RetryManager.retry()`を実行する | `claim()`が`record.phase != READY_ELIGIBLE`によりリクエストを拒否し、実際のretry実行（`WorkflowEngineManager.run()`呼び出し）が発生しないこと（22.1e節Layer 3、Layer 1バイパス時の最終防御の直接確認） |
| 5（29章#1） | pre-6.32 legacy lineage（`side_effect_contract_version is None`）に対し`RetryQueueUpdateDecider.decide()`を`queue_decision_input=LegacyQueueDecisionInput()`で呼ぶ | 既存の`decide_disposition()`ベース判定（`SUCCEEDED`→COMPLETE、それ以外→FAIL）が無変更のまま動作すること（回帰確認、18章） |
| 5b（29章#1） | 6.32 contract対象lineage（`side_effect_contract_version is not None`）で、`mark_terminal()`が未確定のまま（`terminal_disposition is None`）`build_queue_decision_input()`を呼ぶ | `RetryQueueUpdateContractError`が送出され、`LegacyQueueDecisionInput()`へ暗黙にフォールバックしないこと（値の欠落からのlegacy推測が0であることの直接確認） |
| 5c（29章#1） | `side_effect_contract_version`が`0`・負値・非intのlineageで`build_queue_decision_input()`を呼ぶ | `RetryQueueUpdateContractError`が送出され、`LegacyQueueDecisionInput()`にも`LineageAuthoritativeDispositionInput`にもならないこと（18.1節`classify_contract_version_evidence()`のINVALID分岐が単体`decide()`経路でも機能することの直接確認、28.-18節#6のbatch版に対応する単体版） |
| 6（29章#1） | 6.32 contract対象lineageで、restart（プロセス再起動）後に`terminal_disposition=HUMAN_REVIEW_REQUIRED`のlineageに対し`reconcile_all()`を複数回実行する | Queue側の`FAILED`状態とlineage側のHRRが再起動を跨いで整合したまま維持されること（restart後の状態整合、21章と同型のシナリオ） |
| 7（29章#4） | 全stepがUNKNOWNに分類され、かつside-effect safety report の`worst_case()`が`NOT_APPLICABLE`（例：Gate OFFで`MEDIA_UPLOAD`がNOT_APPLICABLE確定）である状態を作る | `resolve_final_disposition()`が`FAILED`を返すこと（`disposition_from_categories()`のUNKNOWN→FAILED判定がそのまま採用され、HRRにならないこと、13章） |
| 8（29章#4） | あるstepがUNKNOWNに分類され、かつside-effect safety reportの`worst_case()`が`IN_PROGRESS_OR_UNKNOWN`（write-ahead ATTEMPTED後にクラッシュ等）である状態を作る | `resolve_final_disposition()`が`HUMAN_REVIEW_REQUIRED`を返すこと。かつ`disposition_from_categories()`（step-only判定）が一切呼ばれない（優先順位1が短絡すること）ことをモック呼び出し回数で確認する（13章） |

### 28.-7b Safe Continuation 同一プロセス内二重呼び出し 必須テスト（1件）

| # | シナリオ | 検証項目 |
|---|---|---|
| 1（29章#25） | 同一プロセス内で、同一identityへ`record_attempted()`を（restartを伴わず）意図的に2回連続で呼ぶ（例：呼び出し元のバグによる二重呼び出しを模擬） | Safe Continuation分岐（9.9.4.4節、`snapshot.category in (PREPARED_ONLY, PREPARED_PLUS_ATTEMPTED)`）が発火し、2回目の呼び出しがエラーにならず安全に処理されること。かつ`external upload count`が2回目の呼び出しの結果として増加しない（実I/Oが呼び出し元の責務であり、本テストはCoordinator層のみを検証する）こと。この結果はプロセス再起動を伴う既存のSafe Continuationテスト（28.-1節#3）と同一の安全側動作であることを確認する |

### 28.-7 必須テスト（5件）

| # | シナリオ | 検証項目 |
|---|---|---|
| 1 | `_value_or_recover()`段2（`self._read_all()`）自体が例外（一時的I/Oエラー等）を送出する状況を作る | 例外が捕捉され、段3（`_minimal_safety_record()`）へフォールスルーすること。呼び出し元へ例外が伝播しないこと（21章シナリオ50） |
| 2 | 段2が`MediaUploadSafetyContractViolationError`（durable state矛盾検出）を送出する状況を作る | 同様に段3へフォールスルーすること（矛盾検出そのものをここでは特別扱いせず、durable read失敗の一種として一律にfallbackする設計を確認する） |
| 3 | `_minimal_safety_record()`が呼ばれる際、追加のfilesystem I/O・store呼び出しが一切発生しないことを確認する | 呼び出しトレースに`_applicability_store`・`_attempt_context_store`・`_media_upload_manager`への追加アクセスが含まれないこと |
| 4 | `_minimal_safety_record()`内の`now_utc_iso()`が例外を送出する状況を作る | `updated_at=""`にfallbackし、`_minimal_safety_record()`自体は例外を送出せず有効なrecordを返すこと（21章シナリオ51） |
| 5 | 9.9.4.2・9.9.4.4節の内容を踏まえた既存crash/restart/identity/legacy testの回帰確認 | 既存の全testがPASSすること |

### 28.-6 lockなしdurable read・複合fault耐性必須

本節は21章シナリオ48・49・9.9.4.4節（3段fallback構成）・27.3節（lock-free read）に基づく、対象シナリオ2件＋回帰確認2件の計4件で構成される。

| # | シナリオ | 検証項目 |
|---|---|---|
| 1 | post-commit cleanup（lock解放）自体が失敗し（stale lock発生）、同一メソッド呼び出し内で戻り値構築（各semantic kindのdataclassコンストラクタ呼び出し）も失敗する複合状況を作る | `_value_or_recover()`段2の`_read_all()`はlockを取得しないため、stale lockの影響を受けずdurable stateを正しく読み直せること。公開メソッドは有効な`MediaUploadSafetyRecord`を返すこと（21章シナリオ48、27.3節） |
| 2 | `CleanupDiagnostic`クラス自体が常に例外を送出するよう仕込む | `_build_cleanup_diagnostic()`が`None`を返し、`_run_with_commit_aware_lock()`は引き続き`acknowledged=True`の`CommitAwareResult`を返すこと（`cleanup_diagnostics`は空タプルまたは他の診断のみを含む、21章シナリオ49） |
| 3 | 段2（`_read_all()`）が正常に成功する基準ケース（段1・段2いずれも失敗していない）で`_value_or_recover()`を呼ぶ | 段1（`outcome.value`）が非Noneであればそのまま使用し、段2以降へは進まないこと。段1がNoneの場合のみ段2が正しく読み直すこと（9.9.4.4節、3段構成の基準動作確認） |
| 4 | 4メソッド（`record_not_applicable()`／`record_prepared()`／`record_attempted()`／`record_confirmed()`）それぞれについて、3段構成（構築済み値→lockなしdurable read→追加I/Oなしの`_minimal_safety_record()`）のいずれか1段のみを失敗させ、残り2段は正常とする組み合わせを網羅する | いずれの組み合わせでも必ず次の段へフォールスルーし、公開メソッドが`None`を返す経路・自分自身のsemantic kind以外を返す経路のいずれも存在しないこと（9.9.4.2・9.9.4.4節、4メソッド×3段失敗パターンの回帰確認、25章#40） |

### 28.-5 Cleanup診断構築・段1→段2復旧必須

本節は21章シナリオ43〜47・9.9.4.2〜9.9.4.4節に基づき構成される。

**28.-7節との重複回避**：シナリオ47（段2失敗→段3フォールスルー）・段2の`MediaUploadSafetyContractViolationError`扱い・`_minimal_safety_record()`の追加I/Oなし要件・`now_utc_iso()`例外時のfallbackは28.-7節#1〜#4が検証する。本節は43〜46（`_build_cleanup_diagnostic()`のフィールド単位fallback・最終防衛線・段1→段2復旧）に固有の4件のみを定義する。

| # | シナリオ | 検証項目 |
|---|---|---|
| 1 | `_build_cleanup_diagnostic()`内の`identity.operation_kind.value`アクセス自体が例外を送出する状況を作る | 個別フィールドのtry/exceptにより`operation_kind=None`へfallbackし、関数全体としては正常に`CleanupDiagnostic`を返すこと。呼び出し元（helper）へ例外が伝播しないこと（21章シナリオ43） |
| 1b（残り4フィールドの個別fault injection、closed failure sites） | `CleanupDiagnostic`の5フィールド（27章）のうち`operation_kind`以外の4フィールド（`reason_code`・`exception_type`・`effect_site`・`occurred_at`）それぞれについて、その値を計算する内部処理が個別に例外を送出する状況を1フィールドずつ作る | #1と同一趣旨を残り4フィールドへ適用：各フィールドが個別のtry/exceptにより`None`（または安全なfallback値）へfallbackし、関数全体としては正常に`CleanupDiagnostic`を返すこと。5フィールドの失敗箇所が`_build_cleanup_diagnostic()`が持つ計算箇所のclosed set（27章が定める5フィールド）と1:1対応することを直接確認する |
| 2 | `CleanupDiagnostic(...)`のdataclass構築自体が例外を送出する状況を作る | `_build_cleanup_diagnostic()`の最終防衛線が作動し、同じコンストラクタへ依存せず診断情報なし（`None`）を返すこと。helperへ例外が伝播しないこと（21章シナリオ44） |
| 3 | `record_not_applicable()`のbody内、`commit_state["committed"] = True`設定後に`NotApplicableMediaUploadSafetyRecord`の構築が例外を送出し、`commit_state["value"]`が`None`のまま返る状況を作る | `_value_or_recover()`段1（`outcome.value`）が`None`のため段2（`_read_all()`）へ進み、durable state（既にNOT_APPLICABLEとしてACK済み）から権威あるrecordを再取得すること。公開メソッドは有効な`MediaUploadSafetyRecord`を返し、`None`を返さないこと（21章シナリオ45） |
| 4 | 上記と同様の状況を`record_prepared()`・`record_attempted()`・`record_confirmed()`でも作る | 同様に段2がdurable stateから復旧すること。4メソッドいずれも`None`を返す経路・自分自身以外のsemantic kindを返す経路を持たないこと（21章シナリオ46） |

段2失敗→段3フォールスルー（21章シナリオ47）・`MediaUploadSafetyContractViolationError`の一律fallback扱い・`_minimal_safety_record()`の追加I/Oなし要件・`now_utc_iso()`例外時のfallbackは28.-7節#1〜#4を参照。

### 28.-4 必須テスト（13件）

| # | シナリオ | 検証項目 |
|---|---|---|
| 1 | `record_not_applicable()`：NOT_APPLICABLE ACK直後、戻り値構築（`NotApplicableMediaUploadSafetyRecord`の構築）で通常のExceptionを注入する | semantic success維持（21章シナリオ39、9.9.4.4節の表どおりACK直後にcommitted=Trueが設定されているため） |
| 2 | `record_attempted()`：IO_ARMED ACK直後、戻り値構築で通常のExceptionを注入する | semantic success維持（21章シナリオ37と対称） |
| 3 | `record_confirmed()`：CONFIRMED_SUCCESS ACK直後、戻り値構築で通常のExceptionを注入する | semantic success維持 |
| 4 | 4メソッドそれぞれについて、durable ACK確認の直後（次の文）で`commit_state["committed"]`が`True`になっていることを確認する | 9.9.4.4節のArchitecture Invariant表どおりの順序であること（構築処理より前にcommitted=Trueが設定されること） |
| 5 | post-commitで通常のException（`Exception`のサブクラス）を送出する | semantic success維持（`cleanup_diagnostics`に格納されるのみ） |
| 6 | post-commitで`KeyboardInterrupt`を送出する | cleanupがbest-effortで試行された後、`KeyboardInterrupt`がそのまま再送出されること（成功へ変換されないこと。21章シナリオ40） |
| 7 | post-commitで`SystemExit`を送出する | 同様に、cleanup試行後に再送出されること（21章シナリオ41） |
| 8 | pre-commit（`committed=False`のまま）で通常のExceptionを送出する | semantic failureとして扱われること（元の例外がそのまま送出される） |
| 9 | post-commit cleanupの`_build_cleanup_diagnostic()`呼び出し自体（またはlogger呼び出し）で通常のExceptionを送出する | semantic resultが変化しないこと（呼び出し元は例外を受け取らない） |
| 10 | post-commit cleanupの`_build_cleanup_diagnostic()`呼び出し自体で`BaseException`（`Exception`ではないもの）を送出する | 25章#26で定めた契約どおり、そのまま再送出されること（cleanup処理自体もBaseExceptionを無条件に握りつぶさない） |
| 11 | secret相当の文字列（認証情報・URL・article本文の断片等）を例外メッセージに含む例外を、post-commit cleanup失敗として注入する | `CleanupDiagnostic`のいずれのフィールドにも、注入した秘密情報相当の文字列が一切含まれないこと（21章シナリオ42） |
| 12 | `CleanupDiagnostic`の内容を検査し、含まれるフィールドが`reason_code`／`exception_type`／`operation_kind`／`effect_site`／`occurred_at`の5つのみであることを確認する | スキーマ上、それ以外のフィールド（メッセージ本文・traceback等）を保持する余地がないこと |
| 13 | 9.9.4.3・9.9.4.4節の内容を踏まえた既存crash/restart/identity/legacy testの回帰確認 | 既存の全testがPASSすること |

### 28.-3 実装契約違反検出（`-O`/PYTHONOPTIMIZE耐性）必須

本節は21章シナリオ37・38・9.9.4.3節に基づく。シナリオ37（`commit_state["committed"]=True`設定後の通常Exception）は28.-4節#2で検証済みのため本節では再掲しない。本節はシナリオ38（`-O`/PYTHONOPTIMIZE実行下でも契約違反検出が機能すること）に固有の内容として、契約違反の検出そのもの・最適化フラグ耐性・3メソッド共通性の3件を定義する。

| # | シナリオ | 検証項目 |
|---|---|---|
| 1 | `body`の実装に契約違反があり、`commit_state["committed"]`を`True`にしないまま正常returnしてしまう状況を模擬する（実装バグの模擬） | `MediaUploadSafetyImplementationContractError`が確実に送出されること。lockはcleanupされ（結果は無視）、呼び出し元は失敗として扱うこと（21章シナリオ38、9.9.4.3節） |
| 2 | 上記#1の検査を`-O`/`PYTHONOPTIMIZE=1`相当の実行環境（`assert`文が無効化される条件）下で行う | 同じ`MediaUploadSafetyImplementationContractError`が確実に送出されること——`assert`文ではなく常に評価される明示的な`if`文＋例外送出として実装されているため、最適化フラグの有無によって検査が消えないこと（25章#24） |
| 3 | `record_not_applicable()`／`record_prepared()`／`record_attempted()`／`record_confirmed()`の4メソッドそれぞれについて#1・#2と同じ契約違反状況を作る | 4メソッドいずれも同一の`MediaUploadSafetyImplementationContractError`検出契約を持つこと（実装が単一の共通Commit-Aware Lock Helperに集約されているため、メソッド間で挙動が分岐しないことの確認、9.9.4節） |

### 28.-2 必須テスト（16件）

| # | シナリオ | 検証項目 |
|---|---|---|
| 1 | `record_attempted()`のIO_ARMED ACK後、lock解放が`Exception`（非`OSError`含む）で失敗する | semantic success維持——呼び出し元が例外を受け取らず、正常な`IoArmedMediaUploadSafetyRecord`の戻り値（exact type、nominal success）をそのまま受け取ること |
| 2 | `record_confirmed()`のCONFIRMED_SUCCESS ACK後、lock解放が`Exception`で失敗する | semantic success維持——呼び出し元が例外を受け取らず、正常な`ConfirmedMediaUploadSafetyRecord`の戻り値（exact type、nominal success）をそのまま受け取ること |
| 3 | `record_not_applicable()`のNOT_APPLICABLE ACK後、lock解放が`Exception`で失敗する | semantic success維持——durable stateが`NOT_APPLICABLE`のまま保持されるだけでなく、`record_not_applicable()`の呼び出し元が例外を受け取らず、正常な`NotApplicableMediaUploadSafetyRecord`の戻り値（nominal success）をそのまま受け取ること（#1・#2と同一の呼び出し元視点でのsemantic success確認を`record_not_applicable()`へ適用） |
| 4 | 各メソッド（4種：`record_not_applicable`/`record_prepared`/`record_attempted`/`record_confirmed`）で、post-commit `_log_cleanup_diagnostics_if_any()`（ロガー呼び出し）自体が例外を送出する | semantic success維持（呼び出し元は例外を受け取らない） |
| 5 | pre-commit body failure（例：PREPARED create ACK失敗）+ lock解放も失敗する | semantic failureが維持され、cleanup失敗が元のエラーを成功へ変換しないこと（元のエラーがそのまま送出される） |
| 6 | ATTEMPTED ACK後・IO_ARMED ACK前に失敗させる | `commit_state["committed"]`が`False`のまま扱われること（pre-commit failureとして扱われる、9.9.4節） |
| 7 | `transition_to_io_armed()`自体のACKが不明瞭な形で失敗する | **external I/O count == 0**（呼び出し元が`orchestrator.apply()`へ進まない） |
| 8 | `record_upload_succeeded()`（CONFIRMED_SUCCESS ACK）自体が失敗する | 成功を捏造しない（例外がそのまま送出され、durable stateは「IO_ARMED + ATTEMPTED」のまま） |
| 9 | `applicability_store.create()`（NOT_APPLICABLE ACK）自体が失敗する | `NOT_APPLICABLE`を捏造しない（例外がそのまま送出され、durable stateは「all absent」のまま） |
| 10 | post-commit cleanup failure（test #1〜3相当）が発生した後、同一identityへ再度同じメソッドを呼ぶ | semantic mutationがduplicate retryされない（9.4節のduplicate検出、または9.9.7節のcategory判定により、既存のdurable stateがそのまま尊重される） |
| 11 | stale identity lock（あるidentityのlockファイルが残存した状態）を作った後、reconciliationや別の呼び出しがそれを自動破棄しないことを確認する | lockファイルが人手を介さず消えないこと。当該identityへの新規操作はタイムアウト後fail-closedで例外送出されること |
| 12 | test #4のcleanup diagnostic failureが、呼び出し元（`ArticleFeaturedMediaRuntime`）まで一切伝播しないことを確認する | 呼び出し元のコードパスに影響が出ないこと |
| 13 | 既存crash/restart test（PREPARED only／PREPARED+ATTEMPTED／IO_ARMED+ATTEMPTED／IO_ARMED+CONFIRMED_SUCCESS等）が、Commit-Aware Lock Helper導入後も同じ結果を維持することを確認する（回帰） | 28.-1節の12件すべてがPASSすること |
| 14（`record_prepared()`のACK Determinism） | `record_prepared()`のPREPARED ACK後、lock解放が`Exception`で失敗する | semantic success維持（`record_prepared()`が正常に`PreparedMediaUploadSafetyRecord`を返す。#1・#3と同一趣旨を`record_prepared()`へ適用） |
| 15（`record_prepared()`のACK失敗は成功を捏造しない） | `record_prepared()`のPREPARED ACK自体が失敗する状況を作る | `PREPARED`を捏造しない（例外がそのまま送出され、durable stateは「all absent」のまま。#9と同一趣旨を`record_prepared()`へ適用、28.-22節#2は補完的evidence） |
| 16（cleanup_diagnosticsはdisposition/cross-store classification inputに入らない） | (a) `classify()`（10章）・`resolve_final_disposition()`（13章）・9.9.7節Cross-Store Combination Tableの判定ロジックをsource監査し、これらが`cleanup_diagnostics`フィールドを一切参照しないことを確認する。(b) 実際のdurable state（例：`CONFIRMED_SUCCESS`）とは矛盾する内容の`cleanup_diagnostics`（例：`reason_code=CONTRACT_VIOLATION`相当の診断情報）を人為的に注入した状態で`classify()`を呼ぶ | (a) source上、判定ロジックの入力に`cleanup_diagnostics`が一切現れないこと（AST監査で直接確認）。(b) 矛盾する内容の診断情報が存在しても、`classify()`の結果はdurable state（`CONFIRMED_SUCCESS`）のみに基づいて決まり、診断情報の内容に左右されないこと（25章#22の直接確認、#4・#12が検証する「診断失敗自体が伝播しないこと」とは異なるclause） |

### 28.-1 必須テスト（PREPARED/IO_ARMED対応、12件）

| # | シナリオ | 検証項目 |
|---|---|---|
| 1 | `context.create_prepared()`のACK後にクラッシュ | **external upload count == 0**、HRRにならない（`SAFE_TO_CONTINUE`、21章シナリオ15） |
| 2 | `ATTEMPTED`のdurable create後・`IO_ARMED`遷移前にクラッシュ | **external upload count == 0**、HRRにならない（21章シナリオ16） |
| 3 | test #2のクラッシュ後にrestartし、同一identityへ`record_attempted()`を再度呼ぶ（Safe Continuation） | 既存の`PREPARED`+`ATTEMPTED`から安全に`IO_ARMED`へ継続できること。duplicate createエラーにならないこと |
| 4 | `IO_ARMED`のACK確認後・external call前にクラッシュ | HRR（21章シナリオ17、意図的に受容する窓） |
| 5 | `IO_ARMED` + `ATTEMPTED`の状態でreconciliationを実行 | `IN_PROGRESS_OR_UNKNOWN`→HRR |
| 6 | `PREPARED` + `CONFIRMED_SUCCESS`という（本来到達しないはずの）組み合わせを人為的に作る | `CONTRACT_VIOLATION`→HRR（9.9.7節） |
| 7 | `IO_ARMED`のみ（`ATTEMPTED`なし）という組み合わせを人為的に作る | `CONTRACT_VIOLATION`→HRR（9.9.7節） |
| 8 | `IO_ARMED`のdurable transitionのACK確認後、lock解放（`MediaUploadSafetyCoordinatorLock.release()`）を意図的に失敗させる | `record_attempted()`が成功を返すこと（ACK Determinism。本シナリオの内容はCommit-Aware Lock Helper機構＜シナリオ32・37＞へ一般化されている）。呼び出し元が正しく`orchestrator.apply()`へ進むこと |
| 9 | `transition_to_io_armed()`自体のACKが不明瞭な形で失敗する（タイムアウト等を模擬） | `io_armed_committed`が`True`にならず、fail-closedで例外送出。**external upload count == 0** |
| 10 | test #3のSafe Continuationを、identity/member_run_idが微妙に異なる状態で試みる | duplicate/継続とみなさず`CONTRACT_VIOLATION`拒否（不一致検出） |
| 11 | identity/member_run_idの不一致を`_read_all()`のいずれかのstore読み取りで発生させる | `CONTRACT_VIOLATION`→HRR |
| 12 | pre-6.32 legacy（`side_effect_contract_version is None`）のlineageで、`MEDIA_UPLOAD`関連のいずれのstoreにもレコードがない | 6.31互換のまま処理されること |

**注記**：下記28.0aの#7・#8は9.9.5・9.9.7節の分類（`SAFE_TO_CONTINUE`）に従う。

### 28.0a 必須テスト（Cross-Store Combination Table対応、14件）

| # | シナリオ | 検証項目 |
|---|---|---|
| 1 | upload_state（`ATTEMPTED`または`CONFIRMED_SUCCESS`）+ 一致するcontext | 正しく分類されること（`IN_PROGRESS_OR_UNKNOWN`または`CONFIRMED_SUCCESS`） |
| 2 | `ATTEMPTED` + context欠落 | `CONTRACT_VIOLATION`→HRR（9.9.4節「upload_state without context」） |
| 3 | `CONFIRMED_SUCCESS` + context欠落 | `CONTRACT_VIOLATION`→HRR（同上） |
| 4 | context member_run_id不一致 | `CONTRACT_VIOLATION`→HRR |
| 5 | context identity不一致／破損 | `CONTRACT_VIOLATION`→HRR |
| 6 | context durable write（`create()`）のACK失敗を注入 | `ATTEMPTED`の作成（9.9.2節ステップ4）へ進まない、**external upload count == 0** |
| 7 | context ACK後・ATTEMPTED作成前にクラッシュ | **external upload count == 0**。「context only」は`SAFE_TO_CONTINUE`（safe pre-I/O）として分類される（21章シナリオ15、9.9.5節） |
| 8 | ATTEMPTED ACK後・external upload前にクラッシュ | 「PREPARED+ATTEMPTED」は`SAFE_TO_CONTINUE`（safe pre-I/O、Safe Continuation対象）として分類される（21章シナリオ16、9.9.5節） |
| 9 | `NOT_APPLICABLE` marker + context が同一identityに存在 | `CONTRACT_VIOLATION`→HRR（9.9.4節） |
| 10 | `NOT_APPLICABLE` marker + upload_state が同一identityに存在 | `CONTRACT_VIOLATION`→HRR |
| 11 | `WordPressDraftRecord`のmember_run_idがexpected_member_run_idと不一致 | `CONTRACT_VIOLATION`→HRR（9.3節） |
| 12 | context欠落＋upload_state存在の状態を作った後、reconciliationを複数回実行する | 自動修復されず、`CONTRACT_VIOLATION`→HRRが繰り返し観測されること（9.9.6節、No Automatic Repair） |
| 13 | classify()が`media_coordinator.get()`/`draft_state.get()`へ渡す`expected_member_run_id`の出所を確認する | 値が`RetryLineageRecord.latest_run_id`（reconciliation経路）または`WorkflowEngineResult.run_id`（同期経路）から供給され、side-effect record自身からは一切読み取られていないこと（10.2節） |
| 14 | pre-6.32 legacy（`side_effect_contract_version is None`）のlineageで、`MEDIA_UPLOAD`関連のいずれのstoreにもレコードがない | 6.31互換のまま処理されること |

### 28.0b 必須テスト（`media_id`導出・Confirmation Invariant対応、6件）

| # | シナリオ | 検証項目 |
|---|---|---|
| 1 | upload成功、`runtime_result.status is ArticleFeaturedMediaRuntimeStatus.APPLIED`かつ`runtime_result.article.featured_media_id > 0` | `_apply_featured_media_step()`が`runtime_result.article`をunwrapして`_extract_confirmed_media_id()`へ渡し、`record_confirmed()`が正しい`media_id`で呼ばれ、`CONFIRMED_SUCCESS`が確定すること（15.4・15.5.1節） |
| 1b | `runtime_result.status is ArticleFeaturedMediaRuntimeStatus.CONTINUED_WITHOUT_FEATURED_MEDIA`（pre-upload fallback、uploadへ未到達）の状態を人為的に作り、テスト用に`runtime_result.article.featured_media_id`が（他の経路由来で）たまたま正の値を持つ状況を注入する | `status`が`APPLIED`でないため、`_extract_confirmed_media_id()`が呼ばれる前に`record_confirmed()`呼び出しが抑止されること——`featured_media_id > 0`という値のみを「actual upload発生の証拠」として扱っていないことの直接確認（15.5.1節条件0） |
| 2 | `runtime_result.status is APPLIED`、`runtime_result.article.featured_media_id == 0` | `_extract_confirmed_media_id()`が`None`を返し、`record_confirmed()`が呼ばれない。durable stateは`ATTEMPTED`のまま、最終的にHRR（15.5.2節、21章シナリオ18） |
| 3 | `runtime_result.status is APPLIED`、`runtime_result.article.featured_media_id`が`None`または非int（malformed） | 同上（15.5.2節、21章シナリオ18） |
| 4 | `record_confirmed()`のdurable ACK失敗（`article_media_upload_state`側のI/Oエラーを注入） | `ATTEMPTED`のまま、最終的にHRR（15.5.2節、21章シナリオ22） |
| 5 | test #1で`CONFIRMED_SUCCESS`が確定した後、Runtime再起動を模擬 | `CONFIRMED_SUCCESS`がdurableに保持されること（21章シナリオ19。restart durabilityは26章Non-Recycleにより構造的に保証される） |
| 6 | test #5の状態で、同一identityへの`MEDIA_UPLOAD`が重複実行されないことを確認 | **duplicate media upload count == 0**（`CONFIRMED_SUCCESS`確定後は`record_attempted()`/`record_not_applicable()`いずれも9.9.3節のCross-Store Invariantにより拒否されるため、外部API呼び出しへ到達しないこと） |

### 28.1 必須テスト（Shared Coordination Boundary対応、12件）

| # | シナリオ | 検証項目 |
|---|---|---|
| 1 | `record_not_applicable()`と`record_attempted()`を同一identityへ並行実行（concurrent race） | `MediaUploadSafetyCoordinatorLock`により直列化され、一方のみ成功し、他方は`MediaUploadSafetyTransitionError`（duplicate/cross-store競合）で拒否されること |
| 2 | `NOT_APPLICABLE`確定後、同一identityへ`record_attempted()`を呼ぶ | 拒否されること（9.9.3節） |
| 3 | `ATTEMPTED`確定後、同一identityへ`record_not_applicable()`を呼ぶ | 拒否されること |
| 4 | 両storeへ人為的に矛盾するレコードを直接書き込んでおく（テストのセットアップとしてCoordinatorを経由せず直接両storeへ書く） | `get()`が`MediaUploadSafetyContractViolationError`を送出し、`classify()`が`CONTRACT_VIOLATION`→HRRに分類すること |
| 5 | `ArticleMediaUploadStateManager`側にのみ`ATTEMPTED`が存在する状態で`get()`を呼ぶ | marker-first priorityで隠蔽されず、`ATTEMPTED`として正しく検出されること（marker側は非存在） |
| 6 | 既存`ArticleMediaUploadStateManager`を（テストコード内で）Coordinatorを経由せず直接呼び出す経路を模擬する | Coordinator側のcross-store保証が及ばないことを確認した上で、その後Coordinator経由の`get()`を呼べば、cross-store矛盾（もし発生していれば）が検出されること（22.2節の構造的限界の実証） |
| 7 | `MediaUploadSafetyCoordinatorLock`の取得に失敗させる（他プロセスがロック保持中を模擬） | `record_attempted()`が例外送出、**external upload count == 0**（実I/O未実行） |
| 8 | `MediaUploadApplicabilityStore.create()`のdurable writeを失敗させる（`record_not_applicable()`のACK失敗） | `MediaUploadSafetyIOError`送出、**external upload count == 0**（Gate OFFなので元々実行されないが、これも確認） |
| 9 | 同一identityへ`record_attempted()`を意図的に重複・並行呼び出しする | **duplicate upload count == 0**（実際のupload API呼び出しが複数回発生しないこと。write-aheadの時点で2回目が拒否されるため） |
| 10 | Cross-store矛盾状態（test #4相当）を作った後、Runtime再起動を模擬し複数回reconcileする | 矛盾状態が自動修復されず、HRRのまま維持されること（自動解除禁止の原則、17章と整合） |
| 11 | pre-6.32 legacy（`side_effect_contract_version is None`）のlineageで、`MEDIA_UPLOAD`関連のいずれのstoreにもレコードがない | 6.31互換のまま処理され、Coordinator機構自体が適用されないこと（18章） |
| 12（全4公開メソッドのwrite-time two-store check網羅） | `record_not_applicable()`／`record_prepared()`／`record_attempted()`／`record_confirmed()`の4公開メソッドそれぞれについて、書き込み直前の相手側store状態（9.9.7節Cross-Store Combination Tableが定める組み合わせ）を個別に構成し、矛盾する組み合わせを注入する | 4メソッドすべてが、書き込み前のcross-store確認により矛盾する組み合わせをfail-closedで拒否すること（#1〜#3が示す特定ペア間の検出を4メソッド全体へ一般化し、直接確認する） |

### 28.2 必須テスト（Gate OFF対応、8件）

| # | シナリオ | 検証項目 |
|---|---|---|
| 1 | NEWS success + media Gate OFF + durable `NOT_APPLICABLE` | HRRにならないこと（`SideEffectSafetyCategory.NOT_APPLICABLE`） |
| 2 | Gate OFFの`NOT_APPLICABLE`がRuntime再起動後も保持される | `get()`が再起動前と同一のidentity・同一の`NOT_APPLICABLE`状態を返すこと |
| 3 | Gate OFF判定後、`MediaUploadSafetyCoordinator.record_not_applicable()`（→`MediaUploadApplicabilityStore.create()`）のdurable ACKが失敗する（`MEDIA_UPLOAD`のauthoritative path、9.9節。`WORDPRESS_DRAFT_CREATION`にはGate相当のOFF概念自体が存在しない、12.1節） | 「正常なNOT_APPLICABLE確定」として扱われないこと。レコード非存在のまま、後続分類で`CONTRACT_VIOLATION`→HRRになること。**external media I/O count = 0**（9.9.4節） |
| 4 | Gate ON状態で、required marker（`ATTEMPTED`/`CONFIRMED_SUCCESS`のいずれか）が欠落 | `CONTRACT_VIOLATION`→HRR（P1-2の継続確認、Gate ONケースでの回帰） |
| 5 | `NOT_APPLICABLE`のrecordと、（テスト内で人為的に注入した）外部side effect成功を示す矛盾するevidence | `CONTRACT_VIOLATION`→HRR（12.5節、record内部整合性違反として検出可能な範囲でシミュレートする——例：identityを共有する2つの異なるstate値を書き込もうとして9.4節のduplicate検出に阻まれることを確認する形で、矛盾が構造的に排除されることを実証する） |
| 6 | あるattemptで`NOT_APPLICABLE`が確定した後、（テスト環境の）現在のGate設定を変更し、同じlineageに対して再度reconcileを実行する | 過去attemptの`NOT_APPLICABLE`判定が、変更後の現在設定によって再解釈されないこと（10.3節、durable recordのみが権威であることの確認） |
| 7 | 同一NEWS step内で`WORDPRESS_DRAFT_CREATION`（Gate ONに相当・常時applicable）と`MEDIA_UPLOAD`（Gate OFF）が同時に評価される | 2つのoperationのapplicability判定が独立しており、一方の結果が他方に影響しないこと（10.1節、21章シナリオ24） |
| 8 | pre-6.32 legacy（`side_effect_contract_version is None`）のlineageで、`MEDIA_UPLOAD`のmarkerが存在しない | 6.31互換のまま処理され、`NOT_APPLICABLE`機構自体が適用されないこと（18章、Contract Version Snapshotとの整合） |

### 28.3 必須テスト（12件）

| # | シナリオ | 検証項目 |
|---|---|---|
| 1 | 同一article・同一attemptでNEWS stepとPUBLISH stepの両方がWordPress draft作成を実行 | 2つの`create_attempted()`呼び出しがそれぞれ独立したidentity（`effect_site`違い）を持ち、互いにduplicate扱いされないこと |
| 2 | `ATTEMPTED`確定後に再起動し、同一attemptの同一operationを再度参照 | `get()`が同一identityで同一recordを返すこと（8章`as_store_key()`の決定論性） |
| 3 | attempt 1とattempt 2で同一記事・同一operation_kind・同一effect_siteの操作を行う | 2つの`create_attempted()`が異なるidentity（`attempt_ordinal`違い）を持ち、互いに影響しないこと |
| 4 | `create_attempted()`成功後、`transition_to_confirmed()`をmember_run_id一致・state==ATTEMPTEDで呼ぶ | `CONFIRMED_SUCCESS`へ正常に遷移すること |
| 5 | `CONFIRMED_SUCCESS`のrecordに対し`transition_to_confirmed()`を再度呼ぶ | acknowledged=False（expected_state不一致）、record内容は変化しないこと |
| 6 | `transition_to_confirmed()`をexpected_member_run_id不一致で呼ぶ | acknowledged=False、record内容は変化しないこと |
| 7 | 別attemptのidentityに対して`transition_to_confirmed()`相当の操作を試みる（cross-attempt） | 対象identityのレコードが存在しない（別ファイル）ため、acknowledged=False（no ATTEMPTED record） |
| 8 | 別effect_siteのidentityに対して同様の操作を試みる（cross-effect-site） | 同上（別ファイル、acknowledged=False） |
| 9 | 同一identityへ`create_attempted()`を2回呼ぶ（duplicate create） | 1回目成功、2回目は`WordPressDraftStateTransitionError`（duplicate） |
| 10 | `create_attempted()`成功後、`transition_to_confirmed()`を呼ばずにプロセスをクラッシュさせ、再起動後にreconcile | `ATTEMPTED`のままdurableに残り、`SideEffectSafetyCategory.IN_PROGRESS_OR_UNKNOWN`→HRRになること |
| 11 | 同一identityに対し、`create_attempted()`（またはtransition）を意図的に並行実行（concurrent呼び出しを模擬） | `WordPressDraftStateStoreLock`（27章）により直列化され、片方のみが成功し、もう片方はduplicate/mismatchとして安全に拒否されること。レコードが不正な中間状態にならないこと |
| 12（transition-time identity validation、exact result固定） | `ATTEMPTED`のrecordに対し、record自身が保持するidentity fields（`operation_kind`/`effect_site`/`instance_key`/`attempt_ordinal`、8章）のいずれか1つを人為的に破損させた状態（durable data corruptionを模擬）で、正しいexpected_state・正しいmember_run_idを渡して`transition_to_confirmed()`を呼ぶ | `transition_to_confirmed()`は`TransitionResult(acknowledged=False, ...)`を返す（#5・#6と同一の戻り値契約——例外を送出する経路は存在しない）。expected_state・member_run_id一致だけでは遷移を許可せず、record自身のidentity fieldsとの整合性も遷移時に検証されること。`CONFIRMED_SUCCESS`へ遷移せず、durable stateは`ATTEMPTED`のまま変化しないこと（#5・#6がexpected-state/member_run_id mismatchを検証するのに対し、本項はidentity自体の整合性検証を直接検証する） |

### 28.4 必須テスト（12件）

| # | シナリオ | 検証項目 |
|---|---|---|
| 12 | attempt 1で`ATTEMPTED`/`CONFIRMED_SUCCESS`を記録後、attempt 2が同一記事の同一operation_kindを処理 | attempt 2が独立した新しいidentityのレコードを作成すること |
| 13 | attempt 1がHRR確定 → `resolve_human_review(RETRY_ALLOWED)` → attempt 2開始 | attempt 2が新しい`attempt_ordinal`で新規side-effect stateを生成し、attempt 1のレコードは監査履歴として残存すること |
| 14 | owning step `GENUINE_SUCCESS` + markerなし | `CONTRACT_VIOLATION` → HRR |
| 15 | owning step `RUNNING`/`UNKNOWN` + markerなし | HRR |
| 16 | owning step `RETRYABLE_FAILURE` + markerなし、副作用前失敗を証明不能 | HRR |
| 17 | durable evidence（`NOT_APPLICABLE`）で非到達 | `NOT_APPLICABLE` |
| 18 | corrupted/mismatched marker | HRR |
| 19 | pre-6.32 legacy（`side_effect_contract_version is None`）でmarker missing | 6.31互換 |
| 20 | write-ahead integration bypassを模擬 | `CONTRACT_VIOLATION` → HRR、自動Retryなし |
| 21 | write-ahead ACK成功 → fake external success → durable confirmation前fault → restart → reconcile | disposition==HRR、external call count == 1 |
| 22 | write-ahead ACK失敗 | external call count == 0 |
| 23 | HRR確定後、`resolve_human_review()`を呼ばずに放置・複数回reconcile | 自動解除されない |

### 28.4a 回帰確認（不変、2件）

| # | シナリオ | 検証項目 |
|---|---|---|
| 24 | Protected Side Effectに一切到達しない通常のFAILED | HRRにならず通常どおりFAILED |
| 25 | 全stepがGENUINE_SUCCESSかつside effectもCONFIRMED_SUCCESS | `SUCCEEDED` |

### 28.5 Fault Injection設計・Regression

**Fault Injection設計**：`WordPressDraftStateStore`/`ArticleMediaUploadStateStore`（アダプター経由）をFake実装に差し替え、write-ahead呼び出しと実I/O呼び出しの間にfault injection hookを挿入する。external call countはFake WordPress clientが記録する実際の呼び出し回数とする。

**Regression**：既存の共通要件（Roadmap 305章）に従う。既存E2E（151/151、6.31）への影響有無を確認する。

### 28.6 Invariant → Test 内容ベース対応表

本表は、25章が定める40項目（#1〜#40）それぞれについて、対応するtest ID（direct＝その項目を主目的として検証するtest、indirect＝他目的のtestの一部として副次的に検証される）を定める。各行は、当該行が指すtest定義（28.-4〜28.-39節等）への直接参照によって、25章の当該Invariant本文の各節（clause）がその中でどう検証されるかを個別に確認できる形でなければならない。判定基準：partial（複合claimの一部のみ）・indirect-only・prose/pseudo-code参照のみ・Crash Matrix scenarioのみ・手動table参照のみ、のいずれかに該当する行はdirectと表示してはならない。

| Invariant # | 保証内容（要約） | 対応test ID | direct/indirect |
|---|---|---|---|
| 1 | durable write-ahead ACK前のexternal I/O禁止 | **direct**：28.-2#7（`transition_to_io_armed()`自体のACKが失敗する状況を作り、external I/O count==0を直接検証、MEDIA_UPLOAD側＝呼び出し箇所B）・28.-11#2（`record_attempted()`自体のACKが失敗する状況を作り、POST count==0を直接検証、呼び出し箇所A）・28.-11#12（同一趣旨を呼び出し箇所C＝`AiPublishService._post()`へ適用、POST count==0）。呼び出し箇所A/B/Cすべてを直接カバーする。**indirect**（ACK成功後・external I/O前の受容窓を検証するのみで、ACK失敗自体は注入しない）：28.-1#1・2・4・9、28.0a#6・7・8、28.-15#1・2 | direct（28.-2#7・28.-11#2・#12）／indirect（他） |
| 2 | duplicate create要求のfail-closed拒否 | 28.3#9、21章シナリオ7 | direct |
| 3 | compare-and-transitionによる不正遷移の拒否（expected-state・member_run_id・record自身のidentity検証） | 28.3#5（expected-state mismatch）・#6（member_run_id mismatch）・#12（record自身のidentity fields破損に対するtransition-time validation） | direct |
| 4 | identity/member_run_id mismatchのfail-closed化 | 28.0a#4・5・11、21章シナリオ9 | direct |
| 5 | unresolved（unauthorized）HRRからの`open_next_attempt()`禁止（二重ガード） | **direct**：28.-31節#1・#2（`_reconcile_all_locked()`をspy/mockで直接exerciseし、`HUMAN_REVIEW_REQUIRED`に対して`open_next_attempt()`が呼ばれないことを直接検証、呼び出し元フィルタ層の単体カバレッジ）・28.-31節#3・28.-9#1（`open_next_attempt()`自身のガード、unauthorized→reject）。**対比evidence**：28.-9#2（同一ガードが`resolve_human_review(RETRY_ALLOWED)`後は`hrr_authorized`真となりpermitすることを直接確認——「unresolved」という条件修飾が実際に意味を持つこと自体をこの対比によって直接証明する。authorized permit自体の完全なlifecycleはInvariant #7・28.-26節が担う）。28.4#23・21章シナリオ25は補完的evidence | direct |
| 6 | reconciliationに「marker absence=safe」というdefaultを置かない | 28.-16#2・3・5、28.-17#1・2・3、21章シナリオ1・14 | direct |
| 7 | Human resolutionはdurable one-shot resolution・自動解除/自動retry/自動re-enqueue禁止。authorized retryはcrash-resumable markerを介したcomposition層dispatchを持つ | **direct**：28.-26節#1・#2（durable生成・restart survival）・#3（resolution不在時の自動解除禁止）・#4（自動reconciliation sweepはHRRを常に除外）・#5（resolution無しのauthorized openは拒否）・#6（RETRY_ALLOWED記録は自動作用なし）・#7（authorized open→ちょうど1件の次attempt、markerは維持）・#8（crash before save→unchanged）・#9（crash after open save・before dispatch→resume可能、duplicate=0）・#10（過去attemptのHRR evidenceはtransition_history上でimmutable）・#11（同一decision再送→idempotent success）・#12（conflicting resolution→reject）・#13（ABANDONED→次attempt永続禁止）・#14（mark_execution_started()によるmarkerクリア）・#15（クリア後の独立な新規HRR）・#16（crash after claim・before mark_execution_started→marker保持・resume可能）・#17（execution_started以降は既存6.31 recovery）・#18（retry_after_human_review()のend-to-end dispatch、queue/scheduler依存=0）・#19（resume判定のexactness、ambiguous state→fail-closed）・#20（attempt budget/integrity迂回なし）。28.1#10・21章シナリオ25・29は補完的evidence | direct |
| 8 | terminal recordの非recycle（identity分離＋transition validationの二重保証） | **direct**：28.-32節（transition validation＝28.3#5・9、identity分離＝28.3#3・7・8、reconcile繰り返しでの非recycle＝28.-16#7を明示的にmapping） | direct |
| 9 | arbitrary record replacement APIを公開しない | 28.-16#9（`WordPressDraftStateStore`の公開APIをclosed-set exact matchで完全列挙、`{create_attempted, transition_to_confirmed, get}`以外は0件）。28.-16#8は補完的evidence | direct |
| 10 | compare-and-swapのatomicity保証 | 28.3#11 | direct |
| 11（duplicate検出の二択を単一決定的outcomeへ確定） | operation-level durable evidence（`NOT_APPLICABLE`）のstep-level優先、`MediaUploadApplicabilityStore.create()`のduplicate検出・fail-closed ACK（複合claim） | **direct**：28.-33節#1（duplicate検出＝`MediaUploadSafetyTransitionError`単一outcome）・#1b（ACK済みcommit後のreturn/recovery failureとの区別）・#2（operation-level evidence優先、28.-16#2・3・28.-17#1・2を明示的にmapping）・#3（ACK失敗のfail-closed契約、28.1#8） | direct |
| 12 | `NOT_APPLICABLE`はACKされて初めてauthoritative | 28.2#3、21章シナリオ13 | direct |
| 13 | reconciliation・classifyは現在のGate/configを再評価しない | 28.2#6 | direct |
| 14 | record内部整合性の矛盾はCONTRACT_VIOLATION | 28.1#4、28.0a#4・5 | direct |
| 15 | 6.32 protected production `MEDIA_UPLOAD`実行経路のdurable state mutationはすべてCoordinator経由。書き込み時はlock内での2 store確認、読み取り時は両store確認＋矛盾検出のいずれも欠かさない（低レベルmanager API自体の存在・test-only bypass注入は禁止しない） | **direct**：28.-27節#1（production wiringのstatic監査、Coordinator以外がstore/manager参照を保持しないこと）・#2（protected pathからのbypass呼び出し=0のcall-graph監査）——production wiring closureを検証。28.1#1・2・3（write-time two-store check、特定ペア間）・#12（4公開メソッド全体への一般化）・#4（read-time両store確認＋矛盾検出）——書き込み時/読み取り時の挙動clauseを直接検証。28.1#6・7は補完的evidence | direct |
| 16 | 同一identityのshared coordination lockはcompeting durable mutationsをserializeする。1つのlock保持区間内での複数storeへの逐次durable write（cross-store sequential write）は正式契約であり、lockはrace prevention boundaryであってcross-store transactionではない | **direct**：28.-25節Invariant #16 #1（同一identityへの競合operationのdeterministicなserialize・critical section非overlap）・#2（矛盾するdurable combinationが正常successとして成立しないこと）・#3（sequential multi-store writesが正式に許容されること、PREPARED→ATTEMPTED→IO_ARMEDの3回の逐次durable writeを直接観測）・#4（cross-store atomicityは主張せず、ATTEMPTED確定後・IO_ARMED到達前という具体的クラッシュ点でのpartial durable evidenceが、9.9.7節・21章シナリオ16と一致する`SAFE_TO_CONTINUE`へexact matchでfail-closedに解決されること）——訂正版invariant本文の全節をそれぞれ直接検証 | direct |
| 17 | read時`expected_member_run_id`はRetry Lineageから供給 | 28.0a#13 | direct |
| 18 | No Automatic Repair | 28.1#10、28.-16#7、21章シナリオ25・29 | direct |
| 19 | durably表現する境界は`IO_ARMED`自体 | 21章シナリオ17、28.-1#4・5 | direct |
| 20 | ACK Determinism（4公開メソッド全体に適用） | 28.-2#1・2・3・6・7・8・9（`record_not_applicable`/`record_attempted`/`record_confirmed`）・#14・15（`record_prepared`を追加）、28.-1#8 | direct |
| 21 | Commit-Aware Lock Helper一律適用（`WordPressDraftStateStore`・`MediaUploadSafetyCoordinator`双方、4公開メソッド全体） | **direct**：28.-28節#1（`WordPressDraftStateStore`が同一helper symbolを経由することのstatic監査）・#2・#3（`WordPressDraftStateStore`側でのfault injection）・#4（Coordinator側4公開メソッド全体が同一helper symbolを経由することのstatic監査、#1と対をなす直接確認）。28.-2全件・28.-4全件はCoordinator側の補完的fault-injection evidence | direct |
| 22 | cleanup_diagnosticsはdisposition判定・cross-store classification inputのいずれにも影響しない | 28.-2#4・12（診断失敗自体の非伝播）・#16（source監査による入力非参照の直接確認＋矛盾する診断内容を注入してもclassify()結果が変化しないことの直接確認） | direct |
| 23 | committed=True後の例外でも成功維持（post-commit ordering disciplineに支えられる） | 28.-4#1・2・3・5、21章シナリオ37・39、**28.-4#4**（ACK直後にcommitted=Trueが設定されるという順序規律自体を直接確認——本項が主張する「committed=True後の例外でも成功維持」は、この順序が先に成立していることを前提とするため、順序自体のdirect testを本mapping行へ明示する） | direct |
| 24 | assert文でなく明示的if文（`-O`耐性） | 28.-3#1・2・3 | direct |
| 25 | ACKとcommitted=Trueの間に処理を置かない | 28.-4#4 | direct |
| 26 | Exception/BaseException境界 | 28.-4#6・7・9・10 | direct |
| 27 | `CleanupDiagnostic`5フィールド限定 | 28.-4#11・12 | direct |
| 28 | `_build_cleanup_diagnostic()`自体は、いかなる内部計算（5フィールドそれぞれの計算・dataclass構築自体）が失敗しても例外を伝播させない | 28.-5#1（`operation_kind`フィールド）・#1b（残り4フィールド`reason_code`/`exception_type`/`effect_site`/`occurred_at`、closed failure sitesとして5フィールド全体をカバー）・#2（`CleanupDiagnostic(...)`コンストラクタ自体の失敗、最終防衛線） | direct |
| 29 | `commit_state["value"]`未設定時の復旧（段1→段2） | 28.-5#3・4 | direct |
| 30 | `_value_or_recover()`段2はlockなし | 28.-6#1 | direct |
| 31 | 最終防衛線はコンストラクタに依存しない | 28.-5#2 | direct |
| 32 | 独立した複数段fallback（3段構成） | 28.-7#1・2・3・4、28.-6#3・4 | direct |
| 33 | 擬似コードの構文的妥当性 | **direct**：28.-25節Invariant #33 #1（本設計書内の全```pythonコードフェンスに対する`ast.parse()`静的構文解析、documentation-level static syntax test）。21章シナリオ52（Crash Matrix scenario兼prose code review）はもはやdirect testとしてカウントしない | direct |
| 34 | 実行provenanceは常に明示的に供給、silent downgrade禁止。project-root`main.py`を含む8 explicit legacy entrypointsのclosed setが、bare直接起動（envelope完全不在）・envelope present-but-malformed・envelope present-but-unknown/contradictory・partial/orphan envelope（mode discriminator欠落＋protected/legacy fieldの一部のみ存在、全nonempty subset）のいずれについてもfail-closedまたはself-originationのうち規則どおり一意な経路のみを辿ること | 28.-10全14件（#11・#14はproject-root`main.py`を含む8 entrypoints universeを直接確認）＋28.-20節#7〜#11（bare self-origination・malformed/unknown/contradictory envelope fail-closed・correlation metadata再構築禁止・偽装申告不要）・#12〜#14（partial/orphan envelope、protected全15 subset×legacy全3 subset×mixed全45組み合わせのfull parameterization） | direct |
| 35（exhaustivenessオラクルはrepository-backed、fail-fast manifest match + sink-oriented oracleの相互補完） | A（NEWS WordPress draft）・B（MEDIA_UPLOAD）・C（PUBLISH WordPress draft）のprotected production side-effect closed setをexhaustiveに検証。A/Cは同一store/manager契約を再利用しつつ`effect_site`で構造的に別record | **direct**：28.-34節#1（A/C再利用＋identity分離、28.-11#6・28.3#1を明示的にmapping）・#2（B独立性、28.-11#7を明示的にmapping）・#3（Stage A：candidate rootとclosed classification manifest（`SIDE_EFFECT_CAPABLE`9＋`NON_SIDE_EFFECT_CAPABLE`10、計19エントリ）のexactly-once match、新規root/重複分類=FAIL。Stage B：manifest内19エントリのaggregate/individual reachability回帰確認）・#4（sink-oriented static oracle、receiver非依存＋closed dynamic-call grammar——`.post`/`.put`/`.patch`/`.delete`/`.request`/`.urlopen`というメソッド名・呼び出し形と`Request(...)`構築・string literal `getattr`をHTTPミューテーションprimitiveとして直接検出し、`Request`/`urlopen`のdef-use linkingにより論理的operationを統合、known symbolリストにもreceiverの型解決にも依存しない独立検証）。test #3・#4がともにPASSする場合に限り、unclassified protected production side-effect site = 0が成立する | direct |
| 36 | `WORDPRESS_DRAFT_CREATION`と`MEDIA_UPLOAD`は別identity | 28.-16#6、28.-11#7、21章シナリオ24 | direct |
| 37 | protected identity consistencyはRetryExecutorのconsistency validation boundaryで確立され、WorkflowEngineExecutorのmember completion boundaryを経て、以降downstreamへlosslessに伝播される（missing/malformed/unknown contextはfail-closed、再構築・mode変換は禁止） | **direct**：**(1) consistency validation boundary（RetryExecutor）**＝28.-37節#1〜#5（`RetryExecutor`が`RetryLineageProtectedProvenance`を構築した直後、`root_run_id`/`attempt_ordinal`/`side_effect_contract_version`が処理中の`lineage`/`claim`と一致することを直接検証。root/attempt/contract version各mismatchのfail-closed、malformed fieldとの検証順序を含む）。**(2) member completion boundary（WorkflowEngineExecutor）**＝28.-37節#6〜#7（validated pre-contextの3値がpass-throughで不変であること、`member_run_id`が`WorkflowEngineExecutor`自身が発行した実際のrun_idと一致すること、caller供給値によるoverride経路が存在しないことを直接検証）。**(3) downstream propagation**＝28.-12全13件＋28.-36節#1〜#11（`WorkflowTriggerAgent`→`WorkflowPipelineRunner`→`WorkflowRunner`→`WorkflowContext`→`PublishStepExecutor`という実protected/legacy chainのlossless propagation、unknown context fail-closed、correlation metadataからの再構築禁止、protected/legacy相互のsilent downgrade/upgrade=0、contract errorのgeneric catch非吸収（#7・#8）、malformed protected context（#9）、malformed/contradictory legacy context（#10・#11）のfail-closedを直接検証）＋28.-36節#12（correlation metadata/task params以外の一般的なambient environment state——未検証env var・module-level/thread-local状態——からの再構築禁止を直接検証）＋28.-38節#1〜#3（22.3.13節、`WorkflowTriggerAgent`経由chain以外の呼び出し箇所A/B/C production chain——`PublishPipelineRunner.run()`・`OutputManager.save_all()`・main.py記事ループの`_apply_featured_media_step()`呼び出し——それぞれのbroad `except Exception`によるcontract errorのgeneric catch非吸収を直接検証）＋28.-39節#1〜#5（14.6節、NEWS subprocess境界——`main.py`のcontract-error exit protocol・`NewsPipelineRunner.run()`の予約exit code検出・再送出・`AgentManager.run()`→`AgentExecutor.execute()`→`NewsAgent.act()`→`NewsPipelineRunner.run()`という実subprocess chain全体でのnon-normalization・既存0/1/20/21回帰・exit code衝突=0を直接検証）。downstream boundaryは第二の独立したauthorityを新設せず、(1)(2)で確立済みのcontextをlossless transportするのみという責務分離（25章#37）と、mapping全体が整合している | direct |
| 38 | Execution provenanceは一度だけ確立、typed immutable value。missing fields・partial/orphan envelopeからの推測・upgrade・downgrade禁止。arbitrary task paramsは権威を上書きしない。protected contextはimmutable。唯一のauthorized reconstruction boundaryはmain.pyのserialized subprocess envelope parserのみ | 28.-14全20件（#18＝`RetryLineageProtectedExecutionContext`のimmutability直接確認、#19＝established-once・arbitrary task params非上書きの直接確認、**#20＝repository全体を対象としたprotected/legacy context constructorのclosed-set enumeration——authority owner initial construction・main.py envelope parserのみを許可し、それ以外のconstruction箇所=0を直接証明**）＋28.-20節#7・#10・#12〜#14（main.py self-origination境界でのmissing/orphan field非推測の直接test） | direct |
| 39 | AgentManager fan-out境界のprovenance完全性 | 28.-19#1〜7全件（下記） | direct |
| 40 | Acknowledged durable semantic commitを別のsemantic kindへ再分類しない（typed closed union、9.9.4.2節）。**4公開メソッド全体（`record_not_applicable`/`record_prepared`/`record_attempted`/`record_confirmed`）に適用される。保証は4層の組み合わせ：(1) exact public return type、(2) variant-specific `RecoveryPolicy`、(3) `_value_or_recover()`のStage 1/2/3 runtime validation、(4) 各公開メソッドの正しいpolicy選択を検証するdirect source/static test（25章#40）** | **direct**：(1)は28.-30#1（`typing.get_type_hints()`等による4メソッドの戻り値annotationの直接introspection、authoritative mappingとの厳密一致を実行可能テストとして確認）。(2)は28.-30#2・#3（4つの`RecoveryPolicy`クラス自身の`expected_type`と`build_minimal()`の一致・`validate()`の交差検証をstatic監査で直接確認）。(3)は28.-23#14（4メソッドそれぞれについて、戻り値構築・durable reread・cleanupのいずれかが失敗する状況で、返るrecordが必ず自分自身のsemantic kindと一致し他kindへのreplay・再分類が発生しないことを直接検証）・28.-24#9（acknowledged durable semantic commitが確定した後、4メソッド×Stage1/2/3の全組み合わせで、返るrecordのkindがdurable storeにcommitされたsemantic kindと常に一致することを直接検証）。(4)は28.-29#1〜#3（method→policy binding、authoritative mapping表に基づくsource/static監査＋実行時型検証）が直接検証する。（28.-23#2・#3はPREPARED固有のfault caseとして28.-23節に引き続き存在し、補完的なindirect evidenceとして扱う） | direct |

**Mapping要件**：25章の40項目それぞれに、少なくとも1件のdirect testが対応付けられなければならない。判定基準は上記の通り：partial（複合claimの一部のみ）・indirect-only・prose/pseudo-code参照のみ・Crash Matrix scenario-only・manual-table-onlyのいずれかに該当する行はdirectとして扱わない。各行は、対応するtest定義（28.-4〜28.-39節等）への直接参照によって、25章当該Invariant本文の各節が実際にそこで検証されることを、本表とは独立に確認できる形で記述されなければならない。Invariant #37は、consistency validation boundary（RetryExecutor、28.-37節#1〜#5）・member completion boundary（WorkflowEngineExecutor、28.-37節#6〜#7）・downstream propagation boundary（28.-12・28.-36・28.-38・28.-39節）という3段階の責務分離（25章#37）に沿ってmappingする。いずれの段も新しい比較authorityの発明を要求しない（consistency validationは既存Retry Lineage authorityとの照合、member completionはpass-through整合性の検証、downstreamはlossless transportの検証のみ）。Invariant #35は、entrypoint/call-graph closure（28.-34節#1〜#3）とsink-oriented static oracle（28.-34節#4）という2種の独立オラクルの相互補完に沿ってmappingする。

### 28.-16 §12.1〜12.4 必須テスト（9件）

| # | シナリオ | 検証項目 |
|---|---|---|
| 1 | `WordPressDraftRecord`が`CONFIRMED_SUCCESS`/`ATTEMPTED`/明示`NOT_APPLICABLE`のいずれかで存在する状態で`classify()`を呼ぶ | record非存在時のfallback rule（12.2節、`CONTRACT_VIOLATION`固定）が一切参照されず、durable recordの状態のみから`SideEffectSafetyCategory`が決まること（12.3節原則1） |
| 2 | record非存在＋対応stepの`StepOutcomeCategory`が`NOT_APPLICABLE`/`INTENTIONAL_NO_ACTION`/`SILENT_NO_ACTION`のいずれかである状態を、6.31既存の`classify_step_outcome()`/`classify_execution_history_step()`（`src/retry_lineage/retry_lineage_genuine_action.py`）が実際に返す値を用いて作る | **`SideEffectSafetyCategory.CONTRACT_VIOLATION`が返ること**（`SILENT_NO_ACTION`等のstep-level evidenceをoperation-specific non-reach proofとして使う設計を採用していないため、この3値でも他の3値と同じく`CONTRACT_VIOLATION`となる。28.-17節#1で明示的に回帰確認する） |
| 3 | record非存在＋対応stepの`StepOutcomeCategory`が`GENUINE_SUCCESS`/`RETRYABLE_FAILURE`/`UNKNOWN`のいずれかである状態を作る | `SideEffectSafetyCategory.CONTRACT_VIOLATION`が返ること（#2の3値と本行の3値が同一の結果になること自体が、`StepOutcomeCategory`を一切判定根拠にしていないことの傍証となる、28.-17節#2で直接確認） |
| 4 | 9.3節のread時検証（identity不一致・member_run_id不一致・record破損）が失敗する状態を、record非存在時のfallback ruleより先に作る | `CONTRACT_VIOLATION`が即座に返り、`StepOutcomeCategory`が一切参照されないこと（12.3節原則3） |
| 5 | `MEDIA_UPLOAD`側の全3ストアが非存在（9.9.7節「all absent」）の状態を作る | **`SideEffectSafetyCategory.CONTRACT_VIOLATION`が返ること**（9.9.7節「all absent」行が直接`CONTRACT_VIOLATION`を返す。28.-17節#3でstepの`StepOutcomeCategory`をどの値に変えても結果が変化しないことを直接確認する） |
| 6 | 同一NEWS step内で`WORDPRESS_DRAFT_CREATION`が`CONTRACT_VIOLATION`、`MEDIA_UPLOAD`が`CONFIRMED_SUCCESS`（またはその逆）となる状態を作る | 一方の判定が他方の判定へ一切影響しないこと（12.3節原則6、25章#36の直接確認） |
| 7 | `CONTRACT_VIOLATION`と判定されたoperationに対し、reconciliationを複数回実行する | `NOT_APPLICABLE`/`SAFE_TO_CONTINUE`や`CONFIRMED_SUCCESS`へ自動的に読み替えられないこと（12.3節原則5、26章Non-Recycleとの整合） |
| 8 | `WordPressDraftStateManager`・`WordPressDraftStateStore`の公開APIをコード監査で確認する | `record_not_applicable()`/`create_not_applicable()`のいずれも存在しないこと（6.32 current APIから除外済み、9.3・9.5・12.4節） |
| 9（complete public API enumeration、arbitrary record replacement API = 0） | `WordPressDraftStateStore`の全public method（`_`prefixを持たない、dataclass由来の自動生成メソッドを除く）を`inspect.getmembers()`等で機械的に列挙する | 列挙された集合が`{create_attempted, transition_to_confirmed, get}`（9.4節）と完全に一致すること——個別method名の不在確認（#8）ではなく、公開APIのclosed-set exact matchとして直接検証する。上記3つ以外のいかなるpublic method（record内容を無条件で書き換える・削除する・resetするAPIを含む）も存在しないこと |

### 28.-17 SILENT_NO_ACTION等のstep-level evidence非reach-proof化 必須テスト（5件）

| # | シナリオ | 検証項目 |
|---|---|---|
| 1 | `WORDPRESS_DRAFT_CREATION`のrecordが非存在の状態で、対応stepの`StepOutcomeCategory`を6値（`NOT_APPLICABLE`/`INTENTIONAL_NO_ACTION`/`SILENT_NO_ACTION`/`GENUINE_SUCCESS`/`RETRYABLE_FAILURE`/`UNKNOWN`）それぞれに変えて`classify()`を呼ぶ | いずれの値でも`SideEffectSafetyCategory.CONTRACT_VIOLATION`が返ること（6値全てで同一結果であることの直接確認） |
| 2 | test #1と同一の6状態それぞれについて、`classify()`の呼び出し前後で`StepOutcomeCategory`を読み取る呼び出し（`classify_step_outcome()`/`classify_execution_history_step()`）の呼び出し回数をモックで計測する | `classify()`の内部から`StepOutcomeCategory`関連の値が一切参照されないこと（引数として渡されても使われないこと、12.2節authoritative rule#3の直接確認） |
| 3 | `MEDIA_UPLOAD`側の全3ストアが非存在の状態で、対応stepの`StepOutcomeCategory`を6値それぞれに変えて`classify()`を呼ぶ | いずれの値でも`SideEffectSafetyCategory.CONTRACT_VIOLATION`が返ること（9.9.7節「all absent」行が`StepOutcomeCategory`を参照しないことの直接確認、28.-16節#5の期待値更新の裏付け） |
| 4 | `MEDIA_UPLOAD`の`PREPARED`のみ／`PREPARED`+`ATTEMPTED`の状態で`classify()`を呼ぶ | `SideEffectSafetyCategory.SAFE_TO_CONTINUE`が返ること（9.9.5・9.9.7節、`NOT_ATTEMPTED`からの改称確認） |
| 5 | `WORDPRESS_DRAFT_CREATION`・`MEDIA_UPLOAD`いずれかの明示`NOT_APPLICABLE`markerが存在する状態で`classify()`を呼ぶ | `SideEffectSafetyCategory.NOT_APPLICABLE`が返ること（12.2・9.9.7節、`NOT_ATTEMPTED`からの改称確認） |

### 28.-15 呼び出し箇所B（NEWS側media upload）必須テスト（11件）

| # | シナリオ | 検証項目 |
|---|---|---|
| 1 | `RETRY_LINEAGE_PROTECTED`＋正常context（root/attempt/member/contract_versionすべて正常）＋画像生成成功で`ArticleFeaturedMediaRuntime.apply()`を実行する | `record_attempted()`のdurable IO_ARMED ACK確認**後**にのみ`media_uploader.upload()`（真の外部I/O、`orchestrator.apply()`内部）が呼ばれること（15.4節Ordering Contract、9.9.3節。境界は画像生成`generate()`を含まない`upload()`直前） |
| 2 | write-ahead ACK（`record_attempted()`、IO_ARMED遷移）自体が失敗する状況を作る | `media_uploader.upload()`が一切呼ばれない（**upload count = 0**）。`generate()`（画像生成）自体の呼び出し有無は本テストの対象外（pre-upload fallback境界、15.4節で扱う） |
| 3 | `LegacyDirectExecutionContext`（closed set内の`legacy_entrypoint`・`legacy_execution_origin`）を明示選択し、`is_available()=True`で`apply()`を実行する | `MediaUploadSafetyCoordinator`の`record_not_applicable()`/`record_prepared()`/`record_attempted()`/`record_confirmed()`の**4公開メソッドすべて**が一度も呼ばれないこと（**coordinator呼び出し数=0**）。`orchestrator.apply()`は既存（6.31以前）のpre-6.32 legacy behaviorのまま直接呼ばれ、既存のmedia state semantics（v1.6等）が変化しないこと（回帰確認） |
| 4 | `main.py::_apply_featured_media_step()`（22.3.2節、exact caller）へ渡る`side_effect_execution_context`が`None`、またはいずれの型でもない状態で、protected実行として本関数を呼ぶ | **upload count = 0**。`_apply_featured_media_step()`冒頭の`validate_side_effect_execution_context()`呼び出しで`MISSING_EXECUTION_MODE`/`UNKNOWN_EXECUTION_MODE`が送出され、`identity`構築・`record_prepared()`・`runtime.apply()`のいずれにも到達しないこと（呼び出し箇所A/Cと同一のvalidatorが最初に呼ばれることの直接確認） |
| 5 | `RETRY_LINEAGE_PROTECTED`＋`root_run_id`欠落 | **upload count = 0**。`MISSING_LINEAGE_CONTEXT`によるhard failure（2.2節#3と同型） |
| 6 | `RETRY_LINEAGE_PROTECTED`＋`attempt_ordinal`/`member_run_id`/`side_effect_contract_version`のいずれかが欠落/malformed（`root_run_id`は正常） | **upload count = 0**。`CONTRACT_VIOLATION`→`HUMAN_REVIEW_REQUIRED`（2.2節#2と同型） |
| 7 | `apply()`内で構築される`SideEffectOperationIdentity`（`operation_kind=MEDIA_UPLOAD`）が、`validate_side_effect_execution_context()`の戻り値（ローカル変数`context`）のみから導出され、コンストラクタ引数や関数外の変数（`media_upload_identity`/`member_run_id`相当の自由変数）を一切参照しないことをコード監査で確認する | 出所不明の自由変数参照 = 0（設計欠陥の回帰確認） |
| 8 | `RetryExecutor.execute()`が構築する値の型を確認する | `RetryLineageProtectedProvenance`（未完成、`member_run_id`を持たない）であり、`RetryLineageProtectedExecutionContext`（完成形）を構築しないこと。`WorkflowEngineManager.run()`へ渡る引数名が`side_effect_execution_provenance`であること（22.1f節、28.-12節#1と同一趣旨の直接確認） |
| 9 | `WorkflowEngineExecutor`が`RetryLineageProtectedProvenance`から`RetryLineageProtectedExecutionContext`への完成処理（`build_protected_execution_context()`呼び出し）を行う箇所をcall graph監査で数える | 完成処理が発生する箇所は1箇所のみであること（member completion occurs exactly once at authoritative boundary） |
| 10 | 呼び出し箇所A（`WordPressOutput.__init__()`）・C（`AiPublishService._post()`）が受け取る型注釈、および呼び出し箇所B（`ArticleFeaturedMediaRuntime.__init__(self, root)`・`apply(self, article)`、`article_featured_media_runtime.py`）の実シグネチャをそれぞれ確認する | A・Cはいずれも完成済み`SideEffectExecutionContext`（`RetryLineageProtectedExecutionContext \| LegacyDirectExecutionContext`）を直接受け取り、未完成の`SideEffectExecutionProvenance`型を受け取る経路が存在しないこと（provenanceが未完成のままside-effect runtimeへ到達しないことの型レベル確認）。**Bについては、`ArticleFeaturedMediaRuntime`の`__init__`・`apply`のいずれのシグネチャにも`side_effect_execution_context`・`side_effect_execution_provenance`に相当する6.32-specificパラメータが存在しないこと（Runtime Foundationに6.32-specific context/provenance parameter = 0）を直接確認する**——Bのcontext検証は`main.py::_apply_featured_media_step()`（22.3.2節、exact caller）が担い、Foundationのconstructor/apply shapeへは一切伝播しない。protected contextは6.32 integration wiring層（`build_protected_featured_media_runtime()`）を経由して`WriteAheadAwareMediaUploadCapability`（decorator）のconstructorへのみ渡ることを、call graph監査で確認する |
| 11 | 呼び出し箇所A/B/Cおよび22.1f節の全記述が参照する型・関数のimport元を確認する | いずれも`side_effect_safety/side_effect_execution_mode.py`の現行discriminated union型のみを参照し、旧世代の単一Optional-heavy型（`execution_mode`フィールド＋4 Optionalフィールドの汎用`SideEffectExecutionContext`クラス）への参照が0件であること（obsolete generic type reference = 0） |

### 28.-14 Trusted Composition Boundary 必須テスト（20件）

**Trusted Composition Boundary Validator挙動**：discriminated union化（2.1節）により、`LegacyDirectExecutionContext`は`legacy_entrypoint`・`legacy_execution_origin`以外のfieldを持たない——「`LEGACY_DIRECT`＋一部フィールドのみ非None」という状態は型として構築不可能である。以下の17件がvalidator挙動を検証する。

| # | シナリオ | 検証項目 |
|---|---|---|
| 1 | `RetryExecutor.execute()`が`side_effect_execution_provenance`を構築する際に呼ぶ関数を確認する | `build_protected_execution_context()`（protected factory）またはそれに対応する`RetryLineageProtectedProvenance`構築のみを使い、legacy factory（`build_legacy_direct_provenance()`/`complete_legacy_execution_context()`）を一度も呼ばないこと（trusted composition boundary、2.1a節） |
| 2 | `build_protected_execution_context()`が`RetryLineageRecord`由来ではない値（テスト用の任意の値）で呼ばれる状況を作る | `RetryLineageProtectedExecutionContext`が構築されること自体は成功する（factory自体は値の出所を検証しない、trust boundaryはfactoryの**呼び出し元**の正しさに依存する設計であることの確認）が、2.2節の`validate_side_effect_execution_context()`が別途well-formedness検証を行うことを確認する |
| 3 | 2.3節の8 explicit legacy entrypoints（`run_ai_publish.py`・`run_ai_workflow.py`・`run_workflow_engine.py`の直接呼び出し、`run_news_agent.py`・`run_workflow_trigger_agent.py`・`run_publish_trigger_agent.py`・`run_review_trigger_agent.py`のAgentManager経由、project-root`main.py`の直接手動実行）それぞれが呼ぶfactoryを確認する | いずれも`build_legacy_direct_provenance()`（Stage 1）＋`complete_legacy_execution_context()`（Stage 2）のみを呼び、対応する`LegacyEntrypoint`／`LegacyExecutionOrigin`を渡すこと。`build_protected_execution_context()`を一度も呼ばないこと |
| 4 | `complete_legacy_execution_context()`をclosed set外の値（`LegacyEntrypoint`/`LegacyExecutionOrigin`のメンバーでない値）で呼ぶ | 呼び出し自体が失敗する（Python型システムレベル、いずれも`Enum`のため）か、`validate_side_effect_execution_context()`が`UNKNOWN_LEGACY_ENTRYPOINT`/`UNKNOWN_LEGACY_EXECUTION_ORIGIN`で拒否すること |
| 5 | `WorkflowEngineManager.run()`・`AgentManager.run()`等のtransport APIを、`side_effect_execution_context`（または`side_effect_execution_provenance`）引数を省略して呼ぶ | 呼び出し自体がTypeError等で失敗する（必須引数、デフォルト値なし）か、明示的に`MISSING_EXECUTION_MODE`でfail-closedすること。暗黙のlegacy fallbackが発生しないこと |
| 6 | `RetryLineageProtectedExecutionContext`を構築する際、`root_run_id`を欠落/malformedにする | **external I/O = 0**。`MISSING_LINEAGE_CONTEXT`が送出されること（2.2節#3） |
| 7 | `LegacyDirectExecutionContext`を構築した後、そこへprotected identity fieldを追加しようとする（テストとして、dataclassのfrozen属性を回避する等の異常操作を試みる） | 通常のPython APIでは不可能であること（`frozen=True`）。型として構造的にフィールド追加ができないことの直接確認 |
| 8 | `LegacyEntrypoint`または`LegacyExecutionOrigin`が欠落/unknownの状態でlegacy factory相当の呼び出しを試みる | **external I/O = 0**。それぞれ`UNKNOWN_LEGACY_ENTRYPOINT`/`UNKNOWN_LEGACY_EXECUTION_ORIGIN`が送出されること |
| 9 | `RetryLineageProtectedExecutionContext`が構築された`AgentContext`が、誤って`LegacyExecutionOrigin`を持つ経路（例：4スクリプトのいずれか）へ渡る状況を作る | 型不一致により、`validate_side_effect_execution_context()`のisinstance分岐いずれにも該当せず、`UNKNOWN_EXECUTION_MODE`で拒否されること（想定される通常の運用では発生しないが、防御的に確認） |
| 10 | `RetryLineageProtectedExecutionContext`をsubprocess経由でmain.pyへ渡し、`_serialize_execution_context()`→`_parse_execution_context_from_env()`のround-tripを行う | 4フィールドすべてが欠落なく往復すること（`root_run_id`/`attempt_ordinal`/`member_run_id`/`side_effect_contract_version`） |
| 11 | `WorkflowEngineContext`・`AgentContext`・NEWS/PUBLISH runner・subprocess境界のいずれか1箇所で`side_effect_execution_context`が欠落する状況を作る（各boundaryごとに個別テスト） | **external protected side-effect I/O = 0**。該当boundaryでfail-closedすること |
| 12 | `scripts/run_retry_runtime.py`経由の実行が、legacy factory（`build_legacy_direct_provenance()`/`complete_legacy_execution_context()`）または`LegacyDirectExecutionContext`へ到達しうる経路がないかcall graphを監査する | Retry production path（`RetryExecutor`→`WorkflowEngineManager`→`WorkflowEngineExecutor`）のいずれのコードパスからもlegacy factoryへ到達できないこと（trusted composition boundaryの構造的分離の確認） |
| 13 | 2.3節の8 explicit legacy entrypoints（7スクリプト＋project-root`main.py`）それぞれが実際に生成する`LegacyEntrypoint`（Stage 1）を確認する | 各entrypointが期待どおりの固有entrypoint値（重複なし、1:1対応）を生成すること。AgentManager経由の4スクリプトは、fan-out境界でさらに`LegacyExecutionOrigin`（Stage 2）が各executorごとに正しく決定されることも併せて確認する |
| 14 | main.pyのsubprocess環境変数へ、`event.metadata`相当のキー（テストとして意図的に注入）を混入させる | `_parse_execution_context_from_env()`が`RETRY_LINEAGE_*`のキーのみを参照し、他のキーの値によってcontextが変化しないこと |
| 15 | `operation_instance_key`（`article.slug`/`review.article_id`）が同一の記事に対し、過去に`RetryLineageProtectedExecutionContext`でのprotected recordが存在する状態で、別のroot_run_idを持つ明示的な`LegacyDirectExecutionContext`実行（正当な4スクリプトのいずれかから）を行う | 過去のprotected recordの存在によって、この明示的なlegacy実行が拒否されないこと（2.3節「Durable Evidence Contractの精緻化」、false positive防止の直接確認） |
| 16 | `RetryLineageProtectedExecutionContext`の`root_run_id`が正しく識別可能で、かつdurable store側の既存recordと`member_run_id`が不一致（durable evidenceとの矛盾）である状況を作る | `CONTRACT_VIOLATION`→`HUMAN_REVIEW_REQUIRED`（既存の9.9.4.4節`_read_all()`・12章決定表がそのまま機能すること、trusted composition boundaryの変更がこの既存経路を破壊しないことの回帰確認） |
| 17 | NEWS呼び出し箇所A・B（15.4・15.7節）とPUBLISH呼び出し箇所C（15.6節）が、いずれも同一の`validate_side_effect_execution_context()`・discriminated union型を使うことを確認する | 3箇所すべてが同一のimport元（`side_effect_execution_mode.py`）から型・関数を参照し、独自の並行実装を持たないこと |
| 18（protected context immutability） | `RetryLineageProtectedExecutionContext`インスタンスを構築した後、そのfield（`root_run_id`等）へ代入を試みる | `dataclasses.FrozenInstanceError`が送出されること（`frozen=True`、#7が`LegacyDirectExecutionContext`について確認するのと同一の直接確認を`RetryLineageProtectedExecutionContext`へ適用） |
| 19（established-once、arbitrary task paramsは権威を上書きしない） | `RetryExecutor.execute()`でのStage 1 provenance構築から`WorkflowEngineExecutor`でのStage 2 member completionを経て、`AgentContext`・`WorkflowEngineContext`・subprocess境界（main.py）までの全boundaryにわたり、各boundaryで実際に保持される`side_effect_execution_context`（またはprotected完成前は`side_effect_execution_provenance`）のオブジェクトIDまたは値を記録する。同時に、各boundaryが参照する`AgentTask.params`へ、正規のcontextと同型に見える別のfake値（意図的に異なる`root_run_id`等を持つ辞書）を注入する | 全boundaryを通じて値が完成後は不変であり（Stage 2完成後、4フィールドいずれも変化しない）、いずれのboundaryも新しい`RetryLineageProtectedExecutionContext`インスタンスを再構築しないこと（authoritative contextの確立が構成boundaryで一度だけ起こり、以降はtransportのみであることの直接確認）。`AgentTask.params`に注入したfake値は、いずれのboundaryの`side_effect_execution_context`にも反映されないこと（arbitrary task paramsが権威を上書きしないことの直接確認、28.-36節#4・#12とは異なりcomposition boundary全体を横断して確認する）。本テストが対象とするchain（`RetryExecutor`→`WorkflowEngineExecutor`→downstream）は、main.pyの`_parse_execution_context_from_env()`（唯一のauthorized reconstruction boundary、25章#38）を経由しない別経路であるため、「new protected context construction = 0」の対象boundaryにmain.pyの自己origination自体は含まれない |
| 20（repository-wide protected/legacy context constructor oracle） | `src/`・`scripts/`・project-root`main.py`の**全`*.py`ファイル**をAST走査し、`RetryLineageProtectedExecutionContext`・`LegacyDirectExecutionContext`の直接コンストラクタ呼び出し、および`build_protected_execution_context()`・`build_legacy_direct_provenance()`・`complete_legacy_execution_context()`（factory、2.1a節）の呼び出し箇所を、repository全体から機械的に列挙する | 列挙された全呼び出し箇所が、以下の**closed setのいずれか1つ**に属することを確認する：**(1) authority ownerでのinitial construction**——`RetryExecutor.execute()`のprovenance構築（2.2節）・`WorkflowEngineExecutor`のprotected factory呼び出し（2.2a節(2)、28.-37節#6〜#7が単体検証）・8 legacy entrypoint（main.py＋7スクリプト、2.3節）それぞれのlegacy factory呼び出し・`AgentManager.run()`のfan-out内4箇所（2.3・2.6節、28.-19節）。**(2) serialized subprocess envelope parserでのexplicit authorized reconstruction**——main.pyの`_parse_execution_context_from_env()`（14.3節）のみ。上記(1)(2)のいずれにも属さない呼び出し箇所が1件でも検出された場合、本テストはFAILする（**その他new protected/legacy context construction = 0**、general ambient/task/event/correlation/env stateからの再構築がclosed set外の経路として存在しないことをrepository全体で直接証明する） |

### 28.-12 Typed Context Propagation 必須テスト（13件）

| # | シナリオ | 検証項目 |
|---|---|---|
| 1 | `RetryExecutor.execute()`が`lineage.root_run_id`・`claim.attempt_no`・`record.side_effect_contract_version`から`RetryLineageProtectedProvenance`を構築し、`WorkflowEngineManager.run()`へ渡す | 構築されたprovenanceの型が`RetryLineageProtectedProvenance`であり、`root_run_id`/`attempt_ordinal`/`side_effect_contract_version`がlineageのdurable stateと一致すること（2.6節） |
| 2 | `WorkflowEngineManager.run(side_effect_execution_provenance=prov)`を呼び、`WorkflowEngineContext`が構築される（この段階の値は未完成のprovenanceであり、`side_effect_execution_context`という完成済みcontext用の名は使わない、22.1f節） | `WorkflowEngineContext.side_effect_execution_provenance`が引数`prov`と同一値を保持すること（値のコピー・再構築による差異がないこと） |
| 3 | `WorkflowEngineExecutor`が各stepの`AgentContext`を構築する | `AgentContext.side_effect_execution_context`が、`WorkflowEngineContext.side_effect_execution_provenance`にprotected factory（`RETRY_LINEAGE_PROTECTED`の場合は`member_run_id`をexecutor自身の`run_id`で補完）を適用した完成済みの値と一致すること（`LEGACY_DIRECT`の場合は`LegacyDirectExecutionContext`がすでに完成形のため、factoryを介さずそのまま一致すること） |
| 4 | `WorkflowEngineEvent.metadata`に`root_run_id`という名前のキーを（テストとして）意図的に含めた状態で、`AgentContext`が構築される | `AgentContext.side_effect_execution_context`の値が`event.metadata`の内容によって一切上書きされないこと（`task.params`のみが`event.metadata`由来であり、`side_effect_execution_context`は独立したfieldであることの直接確認、6章formal invariant） |
| 5 | `NewsAgent.act()`が`NewsPipelineRunner.run()`を呼ぶ | `side_effect_execution_context`が`context.side_effect_execution_context`と同一値で渡されること |
| 6 | `PublishTriggerAgent.act()`が`PublishPipelineRunner.run()`を呼ぶ | 同上（PUBLISH側、5節「PUBLISHが別経路で偶然contextを受け取ると仮定しない」の直接検証） |
| 7 | `NewsPipelineRunner.run()`が`subprocess.run(..., env=...)`を呼ぶ | `env`の`RETRY_LINEAGE_*`各変数が、`_serialize_execution_context(side_effect_execution_context)`（typed context）からのみ生成され、他のソース（`params`の任意キー等）から値が混入しないこと |
| 8 | `WorkflowEngineContext`・`AgentContext`・NEWS/PUBLISH runner・subprocess境界のいずれか1箇所で`side_effect_execution_context`が`None`になる状況を作る（各boundaryごとに個別テスト） | **external protected side-effect I/O = 0**。該当boundaryでfail-closedすること |
| 9 | `RETRY_LINEAGE_PROTECTED`のcontextで`root_run_id`/`member_run_id`/`attempt_ordinal`/`side_effect_contract_version`のいずれかがmismatch（durable stateと不一致）する状況を作る | **external I/O = 0**（2.2節#2・#3と同型の判定） |
| 10 | `scripts/run_ai_publish.py`・`scripts/run_ai_workflow.py`・`scripts/run_publish_trigger_agent.py`・`scripts/run_news_agent.py`・`scripts/run_workflow_trigger_agent.py`・`scripts/run_review_trigger_agent.py`・Retry Lineage外の`scripts/run_workflow_engine.py`・project-root`main.py`の直接手動実行のいずれかを実行する | いずれも`build_legacy_direct_provenance()`（Stage 1）→`complete_legacy_execution_context()`（Stage 2）を明示的に呼び、対応する`LegacyDirectExecutionContext`を構築・供給すること（22.1f節） |
| 11 | 上記4スクリプトのいずれかで、`side_effect_execution_context`の供給自体を（テストとして）省略する状況を作る | `LEGACY_DIRECT`へ自動的にフォールバックしないこと。`MISSING_EXECUTION_MODE`によりfail-closedすること（context欠落がlegacyへ推測されないことの直接確認） |
| 12 | test #4〜11を通じて、`RETRY_LINEAGE_PROTECTED`のcontextが途中で`LEGACY_DIRECT`相当の挙動へ静かに変化する経路がないことを確認する | **protected→legacy silent downgrade path = 0** |
| 13 | `RETRY_LINEAGE_PROTECTED`経路で、あるattemptの実行がPOST成功後にクラッシュし、restart後に同一lineageへ`RetryExecutor.execute()`が再度呼ばれる（Safe Continuation、9.9.5節と同型） | 再構築される`SideEffectExecutionContext`の`root_run_id`/`attempt_ordinal`が、クラッシュ前の実行と同一のSide-Effect Operation Identityを指すこと（8章、restart durability） |

### 28.-11 呼び出し箇所A・C（WordPress draft）必須テスト（12件）

| # | シナリオ | 検証項目 |
|---|---|---|
| 1 | `RETRY_LINEAGE_PROTECTED`＋正常context（root/attempt/member/contract_versionすべて正常）で`WordPressOutput.save()`を実行する | `record_attempted()`のdurable ACK確認**後**にのみ`requests.post()`が呼ばれること（15.7節Ordering Contract） |
| 2 | write-ahead ACK（`record_attempted()`）自体が失敗する状況を作る | `requests.post()`が一切呼ばれない（**POST count = 0**） |
| 3 | `requests.post()`成功＋`record_confirmed()`成功のフルパスを実行する | durable stateが`CONFIRMED_SUCCESS`になり、`SaveResult(success=True)`が返ること |
| 4 | `requests.post()`成功後・`record_confirmed()`実行前にプロセスをクラッシュさせ、再起動後にreconcileする | durable stateは`ATTEMPTED`のまま。`resolve_final_disposition()`が`HUMAN_REVIEW_REQUIRED`を返すこと。**POST count = 1**（重複POSTが発生しないこと、15.7節「POST成功後・record_confirmed()前にクラッシュ」の帰結） |
| 5 | test #4の状態（HRR確定）に対し、`open_next_attempt()`を呼ぶ | 16章の既存ガードにより拒否され、自動retryが発生しないこと |
| 6 | 同一article・同一attemptで呼び出し箇所A（`effect_site=NEWS_STEP`）と呼び出し箇所C（`effect_site=PUBLISH_STEP`）の両方がWordPress draft creationを実行する | 2つの`record_attempted()`呼び出しがそれぞれ独立したidentity（`effect_site`違い）を持ち、互いにduplicate扱いされないこと（8章、15.6・15.7節の非衝突性） |
| 7 | 同一article・同一attemptで、呼び出し箇所A（`WORDPRESS_DRAFT_CREATION`）と呼び出し箇所B（`MEDIA_UPLOAD`）が同時に評価される | 一方のevidence（例：media uploadがCONFIRMED_SUCCESS）が他方（WordPress draft creationの状態）の判定に一切影響しないこと（25章#36） |
| 8 | `LegacyDirectExecutionContext`（closed set内の`legacy_entrypoint`・`legacy_execution_origin`）を明示選択し、`WordPressOutput.save()`を実行する | 既存（6.31以前）のlegacy behaviorが維持されること（write-ahead呼び出しが一切発生しないこと、回帰確認） |
| 9 | `WordPressOutput`のコンストラクタへ渡す`side_effect_execution_context`が`None`、または`RetryLineageProtectedExecutionContext`/`LegacyDirectExecutionContext`のいずれの型でもない値である状態で`save()`を実行する（2.1節のdiscriminated union化以降、`execution_mode`という名のフィールドを持つ型は存在しない） | **POST count = 0**。`MISSING_EXECUTION_MODE`/`UNKNOWN_EXECUTION_MODE`が送出されること |
| 10 | `RETRY_LINEAGE_PROTECTED`＋`root_run_id`欠落、または`attempt_ordinal`/`member_run_id`/`side_effect_contract_version`のいずれかが欠落/malformed | **POST count = 0**。識別不能ならhard failure、識別可能なら`CONTRACT_VIOLATION`→HRR（2.2節#2・#3と同型） |
| 11 | test #3（CONFIRMED_SUCCESS確定）後にRuntime再起動を模擬する | `CONFIRMED_SUCCESS`がdurableに保持され、再起動後も`get()`が同一identityで同一recordを返すこと（restart durability） |
| 12（呼び出し箇所C、write-ahead ACK failure） | `RETRY_LINEAGE_PROTECTED`＋正常contextで`AiPublishService._post()`（呼び出し箇所C、`effect_site=PUBLISH_STEP`）を実行し、write-ahead ACK（`record_attempted()`）自体が失敗する状況を作る | test #2と同一趣旨をCへ適用：WordPress POST（C側のmutating HTTPリクエスト）が一切呼ばれないこと（**POST count = 0**、external I/O = 0） |

### 28.-10 Explicit Side-Effect Execution Mode 必須テスト（14件）

| # | シナリオ | 検証項目 |
|---|---|---|
| 1 | `RetryLineageProtectedExecutionContext`（`root_run_id`/`attempt_ordinal`/`member_run_id`/`side_effect_contract_version`すべて正常）で呼び出し箇所A/B/Cを実行する | write-ahead契約（9.9.3節）が正常に適用され、6.32のprotectionがactiveであること |
| 2 | `RetryLineageProtectedExecutionContext`＋`root_run_id`欠落 | **external I/O = 0**。`SideEffectExecutionModeContractError(MISSING_LINEAGE_CONTEXT)`がhard failureとして送出されること（2.2節#3） |
| 3 | `RetryLineageProtectedExecutionContext`＋`attempt_ordinal`欠落/malformed（`root_run_id`は正常） | **external I/O = 0**。`CONTRACT_VIOLATION`（`CONTEXT_MISMATCH`）へ合流し、識別可能なlineageがHRRへ導かれること（2.2節#2） |
| 4 | `RetryLineageProtectedExecutionContext`＋`member_run_id`欠落/mismatch（`root_run_id`は正常） | 同上（**external I/O = 0**、`CONTEXT_MISMATCH`→CONTRACT_VIOLATION→HRR） |
| 5 | `RetryLineageProtectedExecutionContext`＋`side_effect_contract_version`欠落/mismatch | **external I/O = 0**。`CONTRACT_VERSION_MISMATCH`が送出されること |
| 6 | `LegacyDirectExecutionContext`（closed set内の`legacy_entrypoint`・`legacy_execution_origin`）で呼び出し箇所A/B/Cを実行する | 既存（6.31以前）のlegacy behaviorが維持されること（write-ahead呼び出しが一切発生しないこと） |
| 7 | `AgentContext.side_effect_execution_context`が`None`の状態で呼び出し箇所A/B/Cへ到達する | **external I/O = 0**。`MISSING_EXECUTION_MODE`が送出され、**legacyへの推測が行われないこと**（2.1・2.4節の中核） |
| 8 | `side_effect_execution_context`が`RetryLineageProtectedExecutionContext`/`LegacyDirectExecutionContext`いずれの型でもない状態を作る | **external I/O = 0**。`UNKNOWN_EXECUTION_MODE`が送出されること |
| 9 | `LegacyDirectExecutionContext`の`legacy_entrypoint`または`legacy_execution_origin`がclosed set外の値である状態を作る | **external I/O = 0**。それぞれ`UNKNOWN_LEGACY_ENTRYPOINT`/`UNKNOWN_LEGACY_EXECUTION_ORIGIN`が送出されること（2.1節、discriminated union化により「フィールドが非Noneで存在する」という旧来の矛盾検出は構造的に不要になった） |
| 10 | `scripts/run_retry_runtime.py`経由（`RetryExecutor.execute()`→`WorkflowEngineManager.run(side_effect_execution_provenance=...)`）で呼び出しを実行する | `RetryExecutor.execute()`が呼び出しごとに`RetryLineageProtectedProvenance`を構築して渡すこと（22.1f節、28.-12節#1と同型、construction時ではなくcall時の注入であることを確認） |
| 11 | `scripts/run_ai_publish.py`・`scripts/run_ai_workflow.py`・`scripts/run_publish_trigger_agent.py`・`scripts/run_news_agent.py`・`scripts/run_workflow_trigger_agent.py`・`scripts/run_review_trigger_agent.py`・Retry Lineage外の`scripts/run_workflow_engine.py`・project-root`main.py`の直接手動実行（2.3節の8 explicit legacy entrypoints＝7スクリプト＋main.py）を実行する | いずれも呼び出しごとに`build_legacy_direct_provenance()`→`complete_legacy_execution_context()`（legacy factory）経由で`LegacyDirectExecutionContext`を明示的に供給すること（未指定でも黙ってlegacyになるのではなく、各entrypointが明示的に選択していることを確認。main.py固有の詳細は28.-20節#7・#8を参照） |
| 12 | protected経路でmain.pyをsubprocess起動し、main.py側で`_parse_execution_context_from_env()`とidentity解決を行う（14.2〜14.3節） | subprocess境界を越えて`side_effect_contract_version`・`root_run_id`/`attempt_ordinal`/`member_run_id`が欠落なく伝播すること（28.-12節#7と同型） |
| 13 | `RETRY_LINEAGE_PROTECTED`経路で、`MediaUploadSafetyCoordinator`/`WordPressDraftStateManager`の初期化自体が失敗する（例：Composition Root構築時の例外） | 初期化失敗が`LEGACY_DIRECT`相当の動作へ黙ってfallbackしないこと——初期化失敗はfail-closedなhard failureとしてそのまま伝播し、6.32保護が「たまたま動かなかっただけ」で素通しされないこと |
| 14 | `LEGACY_DIRECT`経路（2.3節の8 explicit legacy entrypoints＝7スクリプト＋main.py）の既存動作（`filter_unpublished()`ベースのidempotency、write-aheadなしの直接POST）が変化しないことを確認する | 回帰確認（既存E2E含む）。2.7節Accepted Residual Riskの範囲が変わらないこと |

### 28.-9 `open_next_attempt()` HRR直接ガード 必須テスト（2件）

| # | シナリオ | 検証項目 |
|---|---|---|
| 1（unauthorized → reject） | `terminal_disposition=HUMAN_REVIEW_REQUIRED`かつ`human_review_resolution is None`のlineageに対し、reconciliation等の経路を介さず`RetryLineageManager.open_next_attempt()`を**直接**呼び出す | `OpenNextAttemptResult(acknowledged=False, reason=...)`が返り、`next_attempt_ordinal`・`attempt_scopes`のいずれも変化しないこと（16章、`hrr_authorized`が偽となるため既存の`not in (FAILED, NOT_ACTIONED)`ガードがそのまま拒否することの単体レベル直接確認） |
| 2（explicit authorized human-review path → permit） | 同一lineageに対し`resolve_human_review(root_run_id, RETRY_ALLOWED, actor, note)`（17.2節）を実行した後、`open_next_attempt()`を**直接**呼び出す | `hrr_authorized`が真となり、`OpenNextAttemptResult(acknowledged=True, attempt_no=...)`が返ること。新しいattemptがちょうど1件作成されること（automatic HRR open＝#1はrejectのまま、explicit authorized human-review pathのみがpermitされることを両ケースで対比的に直接確認、16・17章、28.-26節#5・#7と同一趣旨の単体レベル確認） |

### 28.-18 `decide_all()`バッチ経路統合 必須テスト（12件）

| # | シナリオ | 検証項目 |
|---|---|---|
| 1 | `RetryRuntimeOrchestrator.run_once()`の実装を監査し、`execute_dispatchable_retries()`の呼び出し回数をモックで計測する | ちょうど1回だけ呼ばれること（`run_once()`自身のdocstring invariantの直接確認、22.4a節「配線」） |
| 2 | `run_once()`が`execute_dispatchable_retries()`から得た`execution_results`を`self.manager.decide_retry_queue_updates()`へそのまま渡すことを確認する | `decide_retry_queue_updates()`へ渡される引数が、`execute_dispatchable_retries()`の戻り値と同一（内容一致）であること。`run_once()`内で`RetryQueueUpdateDecider()`が直接構築されないこと |
| 3 | `RetryManager.decide_retry_queue_updates()`が、`build_retry_queue_decision_requests()`を経由して各`execution_result`につき1件の`RetryQueueDecisionRequest`を構築することを確認する | 返る`RetryQueueUpdateDecision`の件数が入力`execution_results`の件数と一致すること。各requestが対応する`execution_result`と正しい`decision_input`を1組として保持していること |
| 4 | 6.32 contract対象lineage（`side_effect_contract_version >= 1`、`mark_terminal()`確定済み）に対応する`execution_result`を渡す | `LineageAuthoritativeDispositionInput`が構築され、`terminal_disposition`がlineageのdurable stateと一致すること |
| 5 | 6.32 contract対象lineageで、`mark_terminal()`が未確定のまま（`terminal_disposition is None`）渡す | `RetryQueueUpdateContractError`が送出され、`LegacyQueueDecisionInput()`へ暗黙にフォールバックしないこと（required disposition missingの直接確認） |
| 6 | `side_effect_contract_version`が`0`または負値のlineageに対応する`execution_result`を渡す | `RetryQueueUpdateContractError`が送出され、legacyへ推測されないこと（18.1節の統一predicateとbatch経路の整合確認） |
| 7 | `find_by_member_run_id()`が解決した`root_run_id`に対し、`peek()`が`None`を返す状態（durable data corruption等を模擬）を作る | `RetryQueueUpdateContractError`が送出され、legacyへもprotectedへも推測しないこと（22.4a節「member_run_id → root_run_id uniquenessの確認結果」の防御的分岐の直接確認） |
| 8 | いかなるlineageのmemberでもない`member_run_id`（`find_by_member_run_id()`が`None`を返す）を持つ`execution_result`を渡す | 正当なpre-6.32/legacyとして明示的に`LegacyQueueDecisionInput()`が選択されること（legacy fallbackではなく、`None`という実測事実に基づく明示的選択であることの区別） |
| 9 | 複数の`execution_result`を含むbatchに対し、意図的に順序を入れ替えた（あるいは要素数を変えた）2つの`RetryQueueDecisionRequest`列を用意し、それぞれで`decide_all()`を呼ぶ | 各`RetryQueueUpdateDecision`が、入力`RetryQueueDecisionRequest`内の`execution_result`と`decision_input`のみに基づいて決定され、他の要素の`decision_input`と取り違えられないこと（parallel list zip禁止の直接確認） |
| 10 | production（`src/`・`scripts/`全体）を対象に、`RetryQueueUpdateDecider.decide_all()`の呼び出し箇所をcall graph監査する | `RetryManager.decide_retry_queue_updates()`内部の1箇所のみであること（**production direct bypass = 0**、単体テストからの直接呼び出しは対象外） |
| 11 | HRR確定lineageに対応する`execution_result`で`decide_retry_queue_updates()`を呼ぶ | `RetryQueueUpdateOutcome.FAIL`・`target_status=RetryQueueStatus.FAILED`が返ること（HRR専用のQueue状態は追加しない。28.-8節#1〜#2の内容がbatch経路でも成立することの統合確認） |
| 12 | 6.31 semantics（`SUCCEEDED`→`COMPLETE`、`FAILED`/`NOT_ACTIONED`→`FAIL`）が本改修後も無変更であることを、pre-6.32 legacy lineage・6.32 protected lineageの両方で確認する | 既存の`RetryQueueUpdateOutcome`マッピングが破壊されていないこと（回帰確認、22.4節#4・#5） |

### 28.-19 AgentManager fan-out legacy provenance 必須テスト（8件）

| # | シナリオ | 検証項目 |
|---|---|---|
| 1 | `AgentConfig`・`WorkflowTriggerAgentConfig`・`PublishTriggerAgentConfig`・`ReviewTriggerAgentConfig`をすべて`is_ready()=True`にした状態で`AgentManager.from_config(config)`を構築し、`legacy_provenance`（Stage 1、`LegacyEntrypoint.RUN_NEWS_AGENT`等いずれか1つ）を渡して単一の`manager.run(task, dry_run=False, legacy_provenance=legacy_provenance)`を呼ぶ | `self._executors`に4つの`AgentExecutor`（NewsAgent/WorkflowTriggerAgent/PublishTriggerAgent/ReviewTriggerAgent）が登録され、単一の`run()`呼び出し内ですべてが実行されること（2.3・2.6節の前提となる実際のfan-out構造の直接確認） |
| 2 | 上記状態で各executorが受け取る`AgentContext.side_effect_execution_context`を検査する | 4つのexecutorそれぞれが、`legacy_execution_origin`が自分自身のAgent型と一致する`LegacyDirectExecutionContext`を受け取ること（`NEWS_AGENT`/`WORKFLOW_TRIGGER_AGENT`/`PUBLISH_TRIGGER_AGENT`/`REVIEW_TRIGGER_AGENT`、2.3節対応表の直接確認） |
| 3 | 上記4つの`LegacyDirectExecutionContext`それぞれの`legacy_entrypoint`フィールドを検査する | 4つとも同一の`legacy_entrypoint`（Stage 1で1回だけ構築された値）を保持すること——`legacy_execution_origin`のみがexecutorごとに異なり、`legacy_entrypoint`はentrypoint provenanceとして適切にimmutableに共有されること（Stage 1/Stage 2の役割分担の直接確認） |
| 4 | 4つの`LegacyDirectExecutionContext`インスタンスの`id()`（オブジェクト同一性）を相互に比較する | いずれのペアも異なるインスタンスであること（**mutable/shared context reuse = 0**、25章#39の直接確認。immutableなdataclassのため値としての安全性はあるが、監査証跡としての正確性は別インスタンスであることに依存する） |
| 5 | `AgentManager._executors`に、2.3節のmapping対応表に存在しない未知のAgent型をテスト用に追加し、`run()`を呼ぶ | 当該executorの`AgentContext.side_effect_execution_context`が`None`のまま構築されること。他の（正しくmappingされた）executorの実行・contextには一切影響しないこと（unmapped executor fail-closed、25章#39・2.3節の直接確認） |
| 6 | `scripts/run_publish_trigger_agent.py`のfan-out（`AI_AGENT_ENABLED`・`PUBLISH_TRIGGER_AGENT_ENABLED`が有効、他は無効の構成）を監査する | `NewsAgent`と`PublishTriggerAgent`のみが登録され、`NewsAgent`は`legacy_execution_origin=NEWS_AGENT`、`PublishTriggerAgent`は`legacy_execution_origin=PUBLISH_TRIGGER_AGENT`をそれぞれ受け取ること（起動scriptが`run_publish_trigger_agent.py`であっても、`NewsAgent`側の`legacy_execution_origin`が`PUBLISH_TRIGGER_AGENT`に誤って倒れないことの直接確認） |
| 7 | `run_ai_publish.py`・`run_workflow_engine.py`（非AgentManager経由の2スクリプト）を実行する | Stage 1（`build_legacy_direct_provenance()`）直後に同一composition pointでStage 2（`complete_legacy_execution_context()`）が呼ばれ、`legacy_entrypoint`・`legacy_execution_origin`がそれぞれ`RUN_AI_PUBLISH`/`AI_PUBLISH_DIRECT`、`RUN_WORKFLOW_ENGINE_DIRECT`/`WORKFLOW_ENGINE_DIRECT`という正しい組み合わせで供給されること（fan-outが存在しない経路でもStage分離の契約自体は維持されることの確認） |
| 8（launcher-name reachability inference = 0） | `scripts/run_review_trigger_agent.py`を、`AI_AGENT_ENABLED`・`WORKFLOW_TRIGGER_AGENT_ENABLED`をいずれも有効にした構成で実行する（launcher自身の名前は「review」だが、構成上は`NewsAgent`・`WorkflowTriggerAgent`も同時に登録される） | `NewsAgent`（呼び出し箇所A・B到達）・`WorkflowTriggerAgent`（呼び出し箇所C到達）が`ReviewTriggerAgent`と共に実際に`run()`内でfan-outし実行されること——起動scriptの名前（`run_review_trigger_agent.py`）からは呼び出し箇所A・B・Cのいずれにも到達しないと推測できてしまうが、実際にはconfig次第で到達することを直接反証する（22.3.11節の訂正・28.-34#3の6段階オラクルの直接裏付け） |

### 28.-20 `run_ai_workflow.py`entrypoint closure 必須テスト（14件）

| # | シナリオ | 検証項目 |
|---|---|---|
| 1 | `scripts/run_ai_workflow.py`を実行する | `WorkflowRunner.from_config(config)`構築直後に`build_legacy_direct_provenance(LegacyEntrypoint.RUN_AI_WORKFLOW)`（Stage 1）→`complete_legacy_execution_context(provenance, LegacyExecutionOrigin.AI_WORKFLOW_DIRECT)`（Stage 2）が同一composition pointで呼ばれ、`runner.run(article_id=..., dry_run=..., side_effect_execution_context=completed_context)`へ渡されること（22.3.12節の直接確認） |
| 2 | 上記contextが`WorkflowRunner.run()`→`WorkflowContext`→`PublishStepExecutor.execute()`→`AiPublishService.run()`まで欠落なく伝播することを確認する | `AiPublishService._post()`が受け取る`side_effect_execution_context`の`legacy_execution_origin`が`AI_WORKFLOW_DIRECT`であること（`WORKFLOW_TRIGGER_AGENT`と混同されないこと、22.3.10節との既存伝播経路の共有確認） |
| 3 | `run_ai_workflow.py`がStage 1/Stage 2のいずれも供給せず`WorkflowRunner.run()`を呼ぶ状況を作る | `PublishStepExecutor.execute()`が到達する`AiPublishService._post()`で`MISSING_EXECUTION_MODE`によりfail-closedすること（**external I/O = 0**、legacyへの推測が行われないことの直接確認） |
| 4 | `AI_WORKFLOW_DIRECT`と`WORKFLOW_TRIGGER_AGENT`の2つの`LegacyExecutionOrigin`値を、同一の`PublishStepExecutor`経路へそれぞれ供給して`decide`系のログ・診断情報を比較する | 監査証跡上、どちらの経路（`run_ai_workflow.py`直接／`WorkflowTriggerAgent`経由）から到達したかを区別できること（値のレベルでの混同が0であることの直接確認） |
| 5 | 22.3.11節が定めるclosed classification manifestとの整合を回帰確認する——**オラクルは28.-34節#3が定めるsink-terminal closure解析そのものであり、本テストは独立したgrep heuristicを持たない**（28.-34節#3のStage A/Bをそのまま呼び出す） | side-effect-capable（`SIDE_EFFECT_CAPABLE`）entrypointが、28.-34節#3が算出するrepository-derived canonical set（`run_retry_runtime.py`＝protected composition root、`main.py`・`run_news_agent.py`・`run_workflow_trigger_agent.py`・`run_publish_trigger_agent.py`・`run_review_trigger_agent.py`・`run_ai_publish.py`・`run_ai_workflow.py`・`run_workflow_engine.py`＝legacy closed set）以外に存在しないこと。残る`*.py`ファイルはすべて`NON_SIDE_EFFECT_CAPABLE`としてmanifestにexactly once属すこと。**unclassified/duplicate-classified production entrypoint = 0**（固定件数のハードコードではなく、28.-34節#3のclosure解析ロジックとの一致を直接オラクルとする） |
| 6 | `run_ai_workflow.py`の既存動作（`WorkflowRunner.run()`が実行する6 step全体、Improvement/ImprovementReview/Rewrite/RewriteReview/Publish/PublishReview）が、`side_effect_execution_context`供給後も無変更であることを確認する | PUBLISH以外のstepの挙動・戻り値（`WorkflowResult`）が回帰しないこと |
| 7（bare main.py self-origination） | project-root`main.py`を、`RETRY_LINEAGE_EXECUTION_MODE`を含む関連環境変数を一切設定しない状態（upstream context envelope不在）で直接起動する | `_parse_execution_context_from_env()`が外部からの供給に一切依存せず、`main.py`自身の中で`build_legacy_direct_provenance(LegacyEntrypoint.RUN_MAIN_DIRECT)`（Stage 1）→`complete_legacy_execution_context(provenance, LegacyExecutionOrigin.MAIN_DIRECT)`（Stage 2）を呼び、`LegacyDirectExecutionContext(legacy_entrypoint=RUN_MAIN_DIRECT, legacy_execution_origin=MAIN_DIRECT)`を構築すること。呼び出し箇所A（`WordPressOutput`）・呼び出し箇所B（6.32 integration wiring層経由の`ArticleFeaturedMediaRuntime`）双方でこの同一contextが使われ、既存のA/B以外の新しいside-effect siteが導入されないこと。かつ、この経路は「context欠落全般をlegacyへ推測する」汎用ルールの適用ではないこと——同一の`_parse_execution_context_from_env()`が呼ばれる呼び出し箇所A/B/C自体（main.py以外の箇所、2.2・2.4節）では、context欠落は引き続き`MISSING_EXECUTION_MODE`でfail-closedすることを併せて確認する |
| 8（malformed envelope fail-closed） | `RETRY_LINEAGE_EXECUTION_MODE=legacy_direct`を設定しつつ、`RETRY_LINEAGE_LEGACY_ENTRYPOINT`を欠落させる、または closed set外の値（例："run_unknown_script"）を設定した状態で`main.py`を直接起動する | `UNKNOWN_LEGACY_ENTRYPOINT`によりfail-closedすること。この場合`RUN_MAIN_DIRECT`のself-origination経路（規則2）へ迂回的に救済されないこと（規則3の直接確認、**external I/O = 0**） |
| 9（unknown/contradictory envelope fail-closed） | (a) `RETRY_LINEAGE_EXECUTION_MODE`にclosed set外の値（例："legacy_hybrid"）を設定する、または (b) `RETRY_LINEAGE_EXECUTION_MODE=legacy_direct`としつつprotected側のfield（`RETRY_LINEAGE_ROOT_RUN_ID`等）も同時に設定した状態で`main.py`を直接起動する | (a)は`UNKNOWN_EXECUTION_MODE`、(b)は`CONTRADICTORY_SERIALIZED_FORM`でそれぞれfail-closedすること。いずれの場合も`RUN_MAIN_DIRECT`のself-origination経路（規則2）へ迂回的に救済されないこと（規則3の直接確認、**external I/O = 0**） |
| 10（correlation metadataからの再構築禁止） | typed environment variable（`RETRY_LINEAGE_EXECUTION_MODE`等）はすべて不在のまま、それらしいcontext情報を含む偽の`correlation_metadata`相当の値（例：`CORRELATION_METADATA`等の非公式env var・診断ログ内のfree-text）を追加で与えた状態で`main.py`を直接起動する | 動作が規則2（bare self-origination、`RUN_MAIN_DIRECT`/`MAIN_DIRECT`）のみに従い、偽のcorrelation metadataからprotected/legacyいずれのcontextも再構築されないこと（2.1節Formal Trust-Boundary Invariant・25章#38の直接確認） |
| 11（main.py偽装申告=0、不変） | 環境変数`RETRY_LINEAGE_LEGACY_ENTRYPOINT`に`run_workflow_engine_direct`を設定したまま、実際には`main.py`を直接手動実行する | main.py側では起動元プロセスの実態を検証できないため、`LegacyEntrypoint`値そのものはclosed set内であれば受理される（14.3節の原則どおり）——ただし`main.py`の正当な直接手動実行に対しては規則2のself-origination経路（環境変数を明示的に設定しない）が既定の運用であり、`run_workflow_engine_direct`を偽って申告する必要自体が既に存在しないことをdocumentation/運用手順レベルで確認する |
| 12（protected orphan field、全nonempty subsetをparameterize、mode discriminator欠落→fail） | `RETRY_LINEAGE_EXECUTION_MODE`を設定せず、protected 4変数（`RETRY_LINEAGE_ROOT_RUN_ID`/`RETRY_LINEAGE_ATTEMPT_ORDINAL`/`RETRY_LINEAGE_MEMBER_RUN_ID`/`RETRY_LINEAGE_CONTRACT_VERSION`）の**全15通りのnonempty subset**（`2^4-1`通り、単一field 4通り・2field 6通り・3field 4通り・4field全部1通りを含む）それぞれについて、そのsubsetに含まれるfieldのみを設定した状態で`main.py`を直接起動するテストをparameterizeする | 15通りすべてで`CONTRADICTORY_SERIALIZED_FORM`によりfail-closedすること。`RUN_MAIN_DIRECT`のself-origination経路（規則2）へ迂回的に救済されないこと（**external I/O = 0**）。`_parse_execution_context_from_env()`の実装（14.3節）が`protected_fields_present = any(...)`という単一のOR判定であり、どのfieldがどう組み合わさっても同一のfail-closed分岐へ到達することがこの全数parameterizeにより直接証明される（25章#34・#38） |
| 13（legacy orphan field、全nonempty subsetをparameterize、mode discriminator欠落→fail） | `RETRY_LINEAGE_EXECUTION_MODE`を設定せず、legacy 2変数（`RETRY_LINEAGE_LEGACY_ENTRYPOINT`/`RETRY_LINEAGE_LEGACY_EXECUTION_ORIGIN`）の**全3通りのnonempty subset**（単一field 2通り・2field全部1通り）それぞれについて、そのsubsetに含まれるfieldのみを設定した状態で`main.py`を直接起動するテストをparameterizeする | 3通りすべてで`CONTRADICTORY_SERIALIZED_FORM`によりfail-closedすること。`RUN_MAIN_DIRECT`のself-origination経路（規則2）へ迂回的に救済されないこと（**external I/O = 0**）。`legacy_fields_present = any(...)`という同一のOR判定構造により、どのfieldの組み合わせでも同一のfail-closed分岐へ到達することを直接証明する（25章#34・#38） |
| 14（mixed orphan fields、protected×legacy全組み合わせをparameterize、mode discriminator欠落→fail） | `RETRY_LINEAGE_EXECUTION_MODE`を設定せず、#12の15通りのnonempty protected subsetと#13の3通りのnonempty legacy subsetの**全45通りの組み合わせ**（`15×3`）それぞれについて、両方のsubsetに含まれるfieldを同時に設定した状態で`main.py`を直接起動するテストをparameterizeする | 45通りすべてで`CONTRADICTORY_SERIALIZED_FORM`によりfail-closedすること。`RUN_MAIN_DIRECT`のself-origination経路（規則2）へ迂回的に救済されないこと（**external I/O = 0**）（25章#34・#38） |

### 28.-21 `ArticleFeaturedMediaRuntime.apply()`境界修正 必須テスト（6件）

| # | シナリオ | 検証項目 |
|---|---|---|
| 1（pre-upload fallback境界） | protected + 画像生成失敗（`generate()`が例外） + `decide_image_generation_fallback()`がCONTINUEと判断 | **external media upload = 0**。`record_prepared()`によるoperation-specific durable pre-I/O evidence（`PREPARED`のみの状態、9.9.4.7節）が存在すること。false HRRなし（`resolve_final_disposition()`が`SAFE_TO_CONTINUE`ベースでHRRを発火させないこと） |
| 2 | protected + `generate()`成功前・呼び出し前にPROPAGATE相当の致命的状況を作る（例：`is_available()`前の想定外の状態） | upload = 0。marker absenceによる誤`CONTRACT_VIOLATION`なし（Operation Applicability自体が非該当と判定される場合、12章decision tableへ到達しないことの確認） |
| 3（pre-upload fallback境界） | ATTEMPTED/IO_ARMED ACK failure（`record_attempted()`自体が失敗） | **external upload = 0**（28.-15節#2と同一趣旨、`media_uploader.upload()`直前での失敗として再確認） |
| 4（post-upload境界） | IO_ARMED ACK確認後、`media_uploader.upload()`実行中・実行後にfailure/crashが発生する（既存の`decide_image_generation_fallback()`によるCONTINUE/PROPAGATE判断が存在する場合を含む） | `resolve_final_disposition()`が`HUMAN_REVIEW_REQUIRED`を維持すること（既存fallback判断の有無に関わらず、side-effect safety evidenceは`IN_PROGRESS_OR_UNKNOWN`のまま）。**duplicate uploadなし**（9.9.3節Cross-Store Invariantにより2回目の`record_attempted()`が拒否されること） |
| 5（post-upload境界） | `media_uploader.upload()`成功、`_extract_confirmed_media_id()`が有効な`media_id`を返す | `CONFIRMED_SUCCESS`が確定すること（15.5節、既存ロジック無変更の直接確認） |
| 6 | `LegacyDirectExecutionContext`（explicit legacy direct）で画像生成失敗＋CONTINUE fallbackを実行する | 既存（6.31以前）のfallback semantics（`decide_image_generation_fallback()`の挙動・`ArticleFeaturedMediaRuntimeResult`の戻り値）が完全に無変更のまま回帰しないこと。write-ahead呼び出しが一切発生しないこと |

### 28.-22 `record_prepared()`・Option (a) decorator injection必須テスト

| # | シナリオ | 検証項目 |
|---|---|---|
| 1 | protected + applicable（Gate ON） | `record_prepared()`のPREPARED ACK確認**後**にのみ既存`ArticleFeaturedMediaRuntime.apply()`ロジック（画像生成）へ進むこと（9.9.4.7節・15.4.1節Ordering） |
| 2 | `record_prepared()`のPREPARED ACK自体が失敗する状況を作る | `MediaUploadSafetyIOError`送出、**external upload = 0**（そもそもwrite-ahead境界前で停止） |
| 3 | 画像生成失敗（`generate()`が例外）＋`decide_image_generation_fallback()`がCONTINUEと判断 | `PREPARED`のみが確定、**external upload = 0**、false HRRなし（28.-21節#1と同一趣旨の直接確認） |
| 4 | pre-upload PROPAGATE（`decide_image_generation_fallback()`がPROPAGATEと判断） | `PREPARED`が確定、**external upload = 0** |
| 5 | 実際にuploadへ進む場合のみ | decorated `MediaUploader.upload()`直前で`record_attempted()`が呼ばれ、ATTEMPTED→IO_ARMED ACK確認**後**にのみ実`media_uploader.upload()`（真の外部I/O）が呼ばれること（15.4.1節authoritative protected flow） |
| 6 | IO_ARMED ACK自体が失敗する状況を作る | 実`media_uploader.upload()`が一切呼ばれない（**real upload = 0**） |
| 7 | IO_ARMED ACK確認後、decorated `upload()`実行中・実行後にcrashが発生する（プロセス再起動を模擬） | 再起動後の分類が`HUMAN_REVIEW_REQUIRED`（既存9.9.5節Crash Semantics「IO_ARMED+ATTEMPTED」と同型） |
| 8 | upload成功、`_extract_confirmed_media_id()`が有効な`media_id`を返す | `CONFIRMED_SUCCESS`が確定すること |
| 9 | Gate OFF（not applicable） | `record_prepared()`が一度も呼ばれないこと（**PREPAREDが作られないこと**）。`record_not_applicable()`のみが呼ばれ`NOT_APPLICABLE`に分類されること |
| 10 | `LegacyDirectExecutionContext`（legacy direct）で画像生成失敗＋CONTINUE fallbackを実行する | decorated uploaderが一切適用されず、既存（6.31以前）のfallback semanticsが完全に無変更のまま維持されること（28.-21節#6と同一趣旨） |
| 11 | `ArticleFeaturedMediaOrchestrator`/`ArticleFeaturedMediaCompositionRoot`のdefault construction（6.32 wiring層を経由しない既存の`from_env()`経路）を実行する | 6.32固有dependency（decorator・Retry Lineage・6.32 execution context）が一切構築・注入されず、既存の挙動と完全に同一であること（zero-diff） |
| 12 | `ArticleFeaturedMediaOrchestrator`/`ArticleFeaturedMediaCompositionRoot`のimport文・モジュール依存をコード監査で確認する | 6.32-specific module（`MediaUploadSafetyCoordinator`・Retry Lineage関連module等）への直接importが0件であること（Consumer-less Foundation維持の直接確認） |

### 28.-23 `record_prepared()` fault matrix・4メソッド共通invariant必須テスト

**`record_prepared()` fault cases 必須テスト（7件）**：

| # | シナリオ | 検証項目 |
|---|---|---|
| 1 | PREPARED ACK前failure（`attempt_context_store.create_prepared()`自体がI/O例外を送出、またはACK自体が失敗） | semantic commitなし（`commit_state["committed"]`は`False`のまま）。`MediaUploadSafetyIOError`がそのまま送出され、pre-commit failureとして扱われること |
| 2 | ACK成功 + 戻り値構築（`PreparedMediaUploadSafetyRecord`の構築）自体が失敗する | `_value_or_recover()`段2（durable reread）が`PreparedMediaUploadSafetyRecord`を正しく復旧すること（Prepared recover、9.9.4.4節） |
| 3 | ACK成功 + durable reread（`_read_all()`）自体が失敗する（一時的I/Oエラー等） | 例外を伝播させず、`_minimal_safety_record()`（`PreparedRecoveryPolicy.build_minimal()`経由、9.9.4.2節）が正確なexact minimal `PreparedMediaUploadSafetyRecord`を返すこと |
| 4 | post-commit cleanup（lock解放）で通常の`Exception`が発生する | semantic success維持（`record_prepared()`が正常に`PreparedMediaUploadSafetyRecord`を返す。25章#23・#26と同型） |
| 5 | post-commit cleanupで`BaseException`（`KeyboardInterrupt`/`SystemExit`等）が発生する | cleanupをbest-effortで試行した上で、`BaseException`をそのまま再送出する（成功へ変換しない。25章#26、21章シナリオ40と同型） |
| 6 | 上記#4・#5のcleanup failureが発生した状況で、`record_prepared()`の戻り値・durable stateを確認する | cleanup failureによってsemantic mutation（PREPARED→他kindへの変化）が一切replayされないこと。durable stateは`PREPARED`のまま、返るrecordも`PreparedMediaUploadSafetyRecord`のままであること |
| 7 | `MediaUploadSafetyCoordinatorLock`がstale（他プロセスのPIDが実在しない状態で残存）のまま`record_prepared()`を呼ぶ | 自動的なlock破棄・自動解放を一切行わないこと（Manual Stale Lock Recovery Procedure、27章と同型）。運用者による手動削除以外でstale lockが解消されないこと |

**typed closed union 必須テスト**：

| # | シナリオ | 検証項目 |
|---|---|---|
| 8 | PREPARED ACK後、戻り値構築失敗＋durable rereadも失敗する複合状況を作る | `_minimal_safety_record()`が返すrecordが正確に`PreparedMediaUploadSafetyRecord`型であり、`NotApplicableMediaUploadSafetyRecord`等の別semantic kindへ一切変換されないこと（25章#40） |
| 9 | `record_not_applicable()`・`record_prepared()`・`record_attempted()`・`record_confirmed()`のいずれについても、durable reread（段2）が自分自身の`policy.expected_type`と異なる型のrecordを返す状況を人為的に作る（cross-store不整合の注入） | 誤った型をそのまま返さず、必ず段3（`_minimal_safety_record()`）へフォールスルーすること（`_value_or_recover()`の`policy.validate()`チェック、9.9.4.4節。28.-24節#2でも直接カバー） |
| 10 | `PreparedMediaUploadSafetyRecord`と`NotApplicableMediaUploadSafetyRecord`が構造的に別の型であり、相互変換API・共通の書き換え可能フィールドを持たないことをコード監査で確認する | PREPAREDとNOT_APPLICABLEの非等価性が型レベルで保証されていること（9.9.4.2節、29章#37） |

**4メソッド共通invariant必須テスト（既存テストの適用範囲拡張）**：

| # | シナリオ | 検証項目 |
|---|---|---|
| 11 | 4メソッド（`record_not_applicable()`／`record_prepared()`／`record_attempted()`／`record_confirmed()`）それぞれについて、post-commit cleanupで通常の`Exception`を注入する | 全4メソッドでsemantic success維持（25章#23、28.-8節#1〜#3の対象を4メソッドへ拡張した回帰確認） |
| 12 | 4メソッドそれぞれについて、post-commitで`BaseException`（`KeyboardInterrupt`/`SystemExit`）を注入する | 全4メソッドでcleanupをbest-effortで試行した上でBaseExceptionがそのまま再送出されること（25章#26、21章シナリオ40・41の対象を4メソッドへ拡張） |
| 13 | 4メソッドそれぞれについて、`cleanup_diagnostics`が`reason_code`/`exception_type`/`operation_kind`/`effect_site`/`occurred_at`の5フィールドのみを保持し、例外メッセージ本文・URL・credentials等を一切含まないことを確認する | 全4メソッドで secret-safe診断契約（25章#27、9.9.4.5節）が維持されること |
| 14 | 4メソッドそれぞれについて、acknowledged durable semantic commit確定後に戻り値構築・durable reread・cleanupのいずれかが失敗する状況を作り、返るrecordのsemantic kindを確認する | 全4メソッドで、返るrecordが必ず自分自身のsemantic kind（`policy.expected_type`）と一致し、他のkindへのreplay・再分類が一切発生しないこと（25章#40、formal invariant） |

### 28.-24 RecoveryPolicy validation必須テスト

`_value_or_recover()`の全3段は、`RecoveryPolicy`（9.9.4.2節、4つのnominally distinctなdataclass：`NotApplicableRecoveryPolicy`/`PreparedRecoveryPolicy`/`IoArmedRecoveryPolicy`/`ConfirmedRecoveryPolicy`）の単一の`policy`引数のみを受け取り、`policy.validate()`によるruntime `isinstance`検証を必須とする（9.9.4.4節）。

| # | シナリオ | 検証項目 |
|---|---|---|
| 1 | `_run_with_commit_aware_lock()`のbody実装を意図的に改変し、`commit_state["value"]`へ`policy.expected_type`と異なる型のインスタンス（例：`record_not_applicable()`呼び出し中に`ConfirmedMediaUploadSafetyRecord`を混入）を設定する状況を人為的に作る | Stage 1で`policy.validate()`が`None`を返し、Stage 2（durable reread）へフォールスルーすること。wrong-kindの値がそのまま返らないこと（Stage 1 reject） |
| 2 | Stage 1が空振り（`outcome.value is None`、またはStage 1がwrong kindでreject）する状況を作った上で、`_read_all()`が返すdurable snapshotを人為的に別kindのrecordへ差し替える（cross-store不整合の注入） | Stage 2で`policy.validate()`が`None`を返し、Stage 3（`_minimal_safety_record()`）へフォールスルーすること。wrong-kindのdurable recordがそのまま返らないこと（Stage 2 reject） |
| 3 | 4つの`RecoveryPolicy`実装（`NotApplicableRecoveryPolicy`等）の`build_minimal()`を監査し、それぞれが自分自身の`expected_type`以外のコンストラクタを一切呼ばないことを確認する。仮に`build_minimal()`が誤ったkindを返す状況をテスト用スタブで注入した場合、Stage 3の`policy.validate()`がこれを検出し`MediaUploadSafetyImplementationContractError`でfail-closedすること | `_minimal_safety_record()`・`build_minimal()`のいずれもwrong variantをそのまま公開メソッドの戻り値として伝播させないこと（minimal factory/policy wrong variant reject） |
| 4 | `record_prepared()`を、Stage 1〜3のいずれかが失敗する複数の状況（post-commit cleanup Exception・durable reread失敗・両方failure）で呼び出す | いずれの状況でも戻り値の型が厳密に`PreparedMediaUploadSafetyRecord`であること（`isinstance`で確認、他のkindでないこと） |
| 5 | `record_not_applicable()`を同様の複数状況で呼び出す | 戻り値の型が厳密に`NotApplicableMediaUploadSafetyRecord`であること |
| 6 | `record_attempted()`を同様の複数状況で呼び出す | 戻り値の型が厳密に`IoArmedMediaUploadSafetyRecord`であること |
| 7 | `record_confirmed()`を同様の複数状況で呼び出す | 戻り値の型が厳密に`ConfirmedMediaUploadSafetyRecord`であること（`media_id`フィールドも正しく伝播していること） |
| 8 | `MediaUploadSafetyCoordinator`の4公開メソッドのソースコードを監査し、`_value_or_recover()`への呼び出しがいずれも単一の`policy=`引数のみを渡し、expected concrete typeとminimal constructionを独立した2引数として呼び出し元が組み合わせるAPIが現行コードに一切存在しないことを確認する | mismatched type/factory pairを構成可能なcurrent API = 0（API surface監査、9.9.4.2・9.9.4.4・9.9.4.7節） |
| 9 | acknowledged durable semantic commit（`outcome.acknowledged == True`）が確定した後、4メソッドいずれについても、最終的に呼び出し元へ返るrecordのkindが、durable storeに実際にcommitされたsemantic kindと常に一致することを、4メソッド×Stage1/2/3の全組み合わせで確認する | acknowledged semantic commitのkind mutation = 0（25章#40、formal invariant） |

### 28.-25 Invariant #16・#33 direct test

以下は、Invariant #16（27.5節Coordinator lockのrace-prevention原則）・Invariant #33（擬似コードの構文的妥当性）それぞれに対するdirect testの定義である（28.6節の判定基準に基づき、Crash Matrix scenario・prose code reviewはいずれもdirect testとして数えない）。

現行のInvariant #16本文は「shared lockはsame identityへのcompeting durable mutationsをserializeするrace prevention boundaryであり、1つのlock保持区間内での複数storeへの逐次durable write（cross-store sequential write）は正式契約である」（25章#16）。以下のtest定義は、この現行invariant本文の**全節**（同一identity競合のserialize・critical section非overlap・sequential multi-store writesの許容・矛盾する組み合わせの排除・cross-store atomicityの非主張）をそれぞれ直接検証する。

**Invariant #16（同一identityのshared coordination lockはcompeting durable mutationsをserializeする。1つのlock保持区間内での複数storeへの逐次durable writeは正式契約であり、lockはrace prevention boundaryであってcross-store transactionではない）**：

| # | シナリオ | 検証項目 |
|---|---|---|
| 1 | 同一identity（同一`SideEffectOperationIdentity`）に対し、`MediaUploadSafetyCoordinator`の2つのメソッド呼び出し（例：スレッドA＝`record_attempted()`、スレッドB＝`record_confirmed()`または同一メソッドの再入）を、`MediaUploadSafetyCoordinatorLock`（27.5節、identity-scoped）を実際に経由させて同時に発行する（テスト用の同期プリミティブ——例えば片方のcritical section内にbarrier/eventを仕込み、もう片方が到達したことを確認してから解放する——を用いてdeterministicにoverlapさせようとする状況を作る） | 2つのcritical section（`_run_with_commit_aware_lock()`のbody実行区間）が実際にoverlapしないこと（片方が`lock.acquire()`で待機し、先行呼び出しの`lock.release()`後にのみ実行が進むことを、共有カウンタ/フラグ等の副作用で直接確認する）。すなわち同一identityへの競合operationがCoordinator lockによってdeterministicにserializeされること |
| 2（exact expected result、全orderingを列挙） | 同一identityに対し、相互排他的なmethod pair（`record_not_applicable()` vs `record_attempted()`）を、#1と同一の同期プリミティブでdeterministicにoverlapさせる。lock取得順序の両方（`record_not_applicable()`が先／`record_attempted()`が先）を個別に実行する | いずれのlock取得順序でも、**先にlockを取得したcall**が正常にcommitされ、authoritative method→policy mapping（28.-29節）どおりの戻り値型（`record_not_applicable()`が先の場合は`NotApplicableMediaUploadSafetyRecord`、`record_attempted()`が先の場合は`IoArmedMediaUploadSafetyRecord`——呼ばれたmethod自身の戻り値型のみをexactに固定し、他方の型と取り違えない）を返すこと、**後からlockを取得したcall**は例外的にcommitされず`MediaUploadSafetyTransitionError`（28.1#1と同一のduplicate/cross-store競合検出、9.9.3節）を送出することを、lock取得順序ごとに個別にexactな結果として固定する——「例外を送出するかCONTRACT_VIOLATIONとして検出可能」という複数受理条件（OR acceptance）は用いない |
| 3 | `record_attempted()`を単独で（競合なしで）呼び出し、単一のlock保持区間内で`MediaUploadAttemptContextStore`（PREPARED durable ACK）→`article_media_upload_state`（ATTEMPTED durable ACK）→`MediaUploadAttemptContextStore`（IO_ARMED durable ACK）という3回の逐次durable writeが実際に行われることを、各storeへの実際の書き込み呼び出し回数・順序を直接観測して確認する（9.9.3節Write-ahead Ordering Contract） | **sequential multi-store writesが、lockはrace preventionの手段であるという原則の下で正式に許容されていること**（cross-store sequential writeは矛盾ではなく正式契約である、25章#16訂正版）。1つのlock保持区間内で複数storeへ書き込むこと自体を禁止・制限しないこと |
| 4 | lock保持中にbodyが2つ以上のstore（`applicability_store`・`attempt_context_store`・`media_upload_manager`のうち複数）へ書き込みを行う既存の実装（`record_attempted()`のPREPARED→ATTEMPTED→IO_ARMEDのように、単一lock保持区間内で複数storeへ逐次書き込む設計、9.9.3節）の、`ATTEMPTED`durable ACK確定後・`transition_to_io_armed()`（IO_ARMED durable ACK）到達前という具体的な1点でクラッシュを模擬する | **cross-store書き込み全体が単一のトランザクションとしてatomicに成功/失敗するという主張・テストは行わない**——lockはrace prevention（同一identityへの同時アクセス排除）の手段であることのみを確認する。この具体的なクラッシュ点で生じるpartial durable evidence（`PREPARED`+`ATTEMPTED`確定・`IO_ARMED`未到達）は、9.9.7節Cross-Store Combination Table・21章シナリオ16と一致する唯一のケースであり、restart classificationは**`SAFE_TO_CONTINUE`（他の2値ではない、exact match）**であることを直接確認する（27.2節Atomicityの保証範囲との整合、cross-store transactional atomicityの新規保証は行わない） |

**Invariant #33（設計書中の擬似コードは構文的に妥当な状態を維持する）**：

| # | シナリオ | 検証項目 |
|---|---|---|
| 1（オラクルは自己参照化——固定件数のハードコードは排除） | 本設計書（`side_effect_fail_closed_human_review_safety_foundation.md`）内の全```pythonコードフェンスを機械的に抽出し、各ブロックを`textwrap.dedent()`してから（クラス本体を伴わない単独メソッド定義等、意図的にインデントされた部分snippetを、単なるインデント起因の`IndentationError`で誤ってfailさせないため）`ast.parse()`（Python標準ライブラリ、構文解析のみ・実行しない）を実行する、documentation-level static syntax testを実装・実行する | 抽出されたブロック総数を`discovered_count`、`ast.parse()`が成功したブロック数を`pass_count`とし、`pass_count == discovered_count`（＝`SyntaxError`が0件）であることを検証する——本オラクルは実行のたびに`discovered_count`を動的に数え直す自己参照的な形とし、特定のRound時点のブロック総数を固定値としてoracle定義自体に埋め込まない（設計書の編集でブロック数が増減しても、本オラクルの定義文言自体は不変のまま機能する）。これは実装コード（`src/`配下）ではなく本設計書ファイル自体を対象とする、Invariant #33の文言（「設計書中の擬似コードは...構文的に妥当な状態を維持する」）に対する直接的・自動的な検証であり、Crash Matrix scenarioにもprose code reviewにも依存しない。本節（normative）自体は`discovered_count`／`pass_count`の固定数を記載しない——オラクルは実行のたびに実測する |

Invariant #16は「lockはrace preventionの手段」という文言を核とし、cross-store transactional atomicityを主張しない。Invariant #33は「擬似コードの構文的妥当性」を、ast.parse()による静的構文解析（本節#1）で自動検証する。

### 28.-26 Invariant #7 / HRR resolve_human_review()・authorized-retry・dispatch direct test

Invariant #7（25章）は複合claimである：(a) HRR terminal dispositionがdurable event/recordとして生成され、restart後も永続すること、(b) resolutionが記録されない限り自動解除・自動retryが一切発生しないこと、(c) `resolve_human_review()`がdurable one-shot resolutionを記録し、同一decisionの再送はidempotent success・異なるdecisionはfail-closedで拒否すること、(d) `open_next_attempt_after_human_review()`が`RETRY_ALLOWED`時のみ次attemptを開き、既存の1回のwhole-record atomic saveの範囲内でcrash-safeに完結し二重attempt生成を起こさないこと、(e) 「過去attemptのHRR evidence」が`transition_history`にimmutableに保存されること（`terminal_disposition`フィールド自体の永久不変性は主張しない、16章）、(f) 既存のattempt budget/lineage integrity検証を迂回しないこと、(g) authorized-openの成功後、`human_review_resolution.opened_attempt_no`がcrash-resumable dispatch markerとして機能し、`mark_execution_started()`が実行開始を確認するまで維持されること、(h) composition層の`retry_after_human_review()`（17.3節）が、resume判定・dispatch（`RetryManager.retry()`）を含めてqueue/scheduler非依存でend-to-endに機能すること。以下がこれを直接検証する。

| # | シナリオ | 検証項目 |
|---|---|---|
| 1（durable record生成） | `resolve_final_disposition()`（13章）が`HUMAN_REVIEW_REQUIRED`を確定させ、`RetryLineageManager.mark_terminal()`を呼ぶ | `RetryLineageRecord`が`terminal_disposition=HUMAN_REVIEW_REQUIRED`のdurable recordとしてstore（`retry_lineage_store.py`のtempfile→fsync→os.replaceパターン、22.3.9節）へ書き込まれること |
| 2（restart survival） | 上記#1の後、`RetryLineageManager`インスタンスを破棄し、同一storeパスから新規インスタンスを再構築する（プロセス再起動相当） | 再構築後の`get()`/`peek()`が、再起動前と同一の`root_run_id`・`terminal_disposition=HUMAN_REVIEW_REQUIRED`を返すこと |
| 3（resolution不在時の自動解除禁止） | 上記#2の状態に対し、`resolve_human_review()`を呼ばずに`open_next_attempt()`・`open_next_attempt_after_human_review()`・`claim()`・`RetryEnqueueTrigger.enqueue_pending_failures()`（`lineage`が正しく注入された状態）・reconciliation複数回実行のいずれを行っても | `terminal_disposition`が`HUMAN_REVIEW_REQUIRED`のまま変化せず、`human_review_resolution`も`None`のままであること（既存28.1#10・21章シナリオ25・29と同一趣旨をrestart後の状態に対しても直接確認）。**`RetryEnqueueTrigger.enqueue_pending_failures()`実行時、`RetryQueueManager.enqueue()`の呼び出し回数が0であること（enqueue call/count = 0、`skipped_lineage_member`としてカウントされることを直接確認、22.1e節Layer 1と同一趣旨をHRR resolution不在の状態に対しても直接確認）** |
| 4（自動reconciliation sweepはHRRを常に除外） | resolutionの有無（`None`／`RETRY_ALLOWED`／`ABANDONED`いずれの状態も含む）に関わらず、`_reconcile_all_locked()`のopened_countループを実行する | `_reconcile_all_locked()`が`open_next_attempt()`をHRR lineageに対して一度も呼ばないこと（`terminal_disposition in (FAILED, NOT_ACTIONED)`フィルタによる構造的除外を直接確認、16章） |
| 5（resolution無しでのauthorized open → reject） | `human_review_resolution is None`のHRR recordに対し`open_next_attempt()`（および`open_next_attempt_after_human_review()`）を呼ぶ | `acknowledged=False`が返り、attempt creation等いかなるdurable I/Oも発生しないこと（**external I/O = 0**） |
| 6（RETRY_ALLOWED記録 → 自動作用なし） | `resolve_human_review(root_run_id, RETRY_ALLOWED, actor, note)`を呼んだ直後（`open_next_attempt_after_human_review()`呼び出し前）の状態を確認する | `human_review_resolution`が`RETRY_ALLOWED`で記録され、`transition_history`に解決記録（`detail="human_review_resolution=retry_allowed"`）が追記されること。`phase`は`TERMINAL`のまま、`attempt_scopes`・`next_attempt_ordinal`のいずれも変化しないこと（**resolve_human_review()単体はattempt creation・queue writeのいずれも発生させない**） |
| 7（authorized open → exactly one next attempt、markerは維持） | 上記#6の状態に続けて`open_next_attempt_after_human_review(root_run_id)`を呼ぶ | 新しい`attempt_no`を持つattemptがちょうど1件作成され、同一の`save()`呼び出し内で`phase=READY_ELIGIBLE`・`terminal_disposition=None`・`next_attempt_ordinal`前進が同時に反映されること。`human_review_resolution`は`None`へクリアされず、`human_review_resolution.opened_attempt_no`が新しい`attempt_no`と一致した状態で維持されること（17.2節、crash-resumable marker）。`transition_history`に`detail="next attempt opened via RETRY_ALLOWED human review resolution"`が追記されること |
| 8（crash before save → unchanged、安全な再試行） | `open_next_attempt_after_human_review()`実行中、`self._store.save(record)`呼び出し**前**にプロセスをクラッシュさせ、再度呼ぶ | durable stateがクラッシュ前と完全に同一（`phase=TERMINAL`・`human_review_resolution.opened_attempt_no=None`のまま）であり、再呼び出しが#7と同一の結果に正常に到達すること |
| 9（crash after open save、before dispatch → resume可能） | #7実行後（`phase=READY_ELIGIBLE`・`human_review_resolution.opened_attempt_no`確定済み）、`retry_after_human_review()`（17.3節）のdispatchステップ（`RetryManager.retry()`呼び出し）に到達する前にプロセスをクラッシュさせ、`retry_after_human_review()`を再度呼ぶ | 2回目の呼び出しが、resume判定（`phase==READY_ELIGIBLE`かつ`human_review_resolution.opened_attempt_no == record.next_attempt_ordinal`）により`resolve_human_review()`・`open_next_attempt_after_human_review()`のいずれも再度呼ばず、`RetryManager.retry(root_run_id, attempt=opened_attempt_no)`へ直接進むこと。2件目のattemptが作成されないこと（duplicate attempt = 0、新しいCAS・sub-phaseを用いず`phase`+`opened_attempt_no`の組み合わせが冪等性の判別子として機能することを直接確認） |
| 10（過去attemptのHRR evidenceはtransition_history上でimmutable） | #7実行後、`transition_history`を確認する | `mark_terminal()`が記録した`detail="disposition=human_review_required"`のエントリが、`open_next_attempt()`実行後も削除・書き換えされず存在し続けること（**「`terminal_disposition`そのものが永久immutable」という表現は採用せず、`transition_history`上のevidenceの永続性のみを主張する**、16章） |
| 11（同一decisionの再送 → idempotent success） | `resolve_human_review(root_run_id, RETRY_ALLOWED, actor_A, note_A)`実行後、同一`resolution=RETRY_ALLOWED`で`resolve_human_review(root_run_id, RETRY_ALLOWED, actor_B, note_B)`を再度呼ぶ | 2回目の呼び出しが`acknowledged=True`を返すこと。`record.human_review_resolution`の`actor`/`note`/`resolved_at`が最初の呼び出し（`actor_A`/`note_A`）のまま変化しないこと（上書きされない）。2回目の呼び出しで`transition_history`への追記・`save()`が発生しないこと |
| 12（異なるdecision＝conflicting resolution → reject） | `RETRY_ALLOWED`が記録された状態で`resolve_human_review(root_run_id, ABANDONED, ...)`を呼ぶ（およびその逆：`ABANDONED`記録済みの状態で`RETRY_ALLOWED`を呼ぶ） | いずれの組み合わせも`acknowledged=False`を返し、既存の`human_review_resolution`が変化しないこと |
| 13（ABANDONED → 次attempt永続禁止） | `resolve_human_review(root_run_id, ABANDONED, actor, note)`実行後、`open_next_attempt()`（および`open_next_attempt_after_human_review()`）を呼ぶ | `hrr_authorized`判定（`resolution.resolution == RETRY_ALLOWED`を要求、16章）が偽となり、`acknowledged=False`が返ること。attempt creationが発生しないこと |
| 14（`mark_execution_started()`によるmarkerクリア） | #7実行後（`phase=READY_ELIGIBLE`・`human_review_resolution.opened_attempt_no`確定済み）、`claim()`→`mark_execution_started(root_run_id, run_id)`を実際に実行する | `mark_execution_started()`の同一`save()`呼び出し内で、`record.human_review_resolution.opened_attempt_no == attempt_no`（一致）が確認され`human_review_resolution`が`None`へクリアされること。既存の処理（`phase=EXECUTION_STARTED`・`attempt_count`+1・`membership`追記・`transition_history`追記）が無影響のまま実行されること |
| 15（次attempt cycleでのresolutionクリア後、独立な新規HRR） | #14実行後（`human_review_resolution=None`にクリアされた後）、その新attemptが再び`HUMAN_REVIEW_REQUIRED`へ到達する状況を作り、`resolve_human_review()`を呼ぶ | 新しいHRR occurrenceに対して独立に新規resolutionを記録できること（#11の「既存resolution存在時は再送のみ許可」というガードに、過去attemptのresolutionが干渉しないこと） |
| 16（crash after claim、before mark_execution_started → marker保持・resume可能） | #7実行後、`claim()`が成功（`phase=CLAIMED`）した直後・`mark_execution_started()`到達前にプロセスをクラッシュさせ、既存の`_reconcile_all_locked()`のorphan-CLAIMED回収（`release_claim()`、既存6.31機構）を実行した後、`retry_after_human_review()`を再度呼ぶ | `release_claim()`は`human_review_resolution`に触れないため、回収後も`phase=READY_ELIGIBLE`・`human_review_resolution.opened_attempt_no`は維持されること。`retry_after_human_review()`の2回目の呼び出しがresume判定により`RetryManager.retry()`へ直接進み、`claim()`が再度成功すること（duplicate attempt = 0） |
| 17（execution_started以降は既存6.31 recoveryに委ねる） | #14実行後（`human_review_resolution=None`）、`EXECUTION_STARTED`状態でクラッシュさせ再起動する | 既存の6.31 crash/restart機構（`_reconcile_all_locked()`のEXECUTION_STARTED処理・`mark_terminal()`経路）がそのまま機能し、HRR固有の追加ロジックが一切介在しないこと（`human_review_resolution`が既に`None`のため、以降のいかなる分岐にも影響しない） |
| 18（`retry_after_human_review()`のend-to-end dispatch） | `resolve_human_review(RETRY_ALLOWED)`→`open_next_attempt_after_human_review()`→`RetryManager.retry()`の3ステップを、composition層の`retry_after_human_review()`（17.3節）経由でend-to-endに実行する（クラッシュ注入なし） | `RetryManager.retry(root_run_id, attempt=opened_attempt_no)`が実際に呼ばれ、`claim()`が成功し、`RetryExecutor.execute()`まで到達すること。`RetryQueueManager`・`SchedulerEngine`・`RetryEnqueueTrigger`のいずれのメソッドも一切呼ばれないこと（**queue/scheduler依存 = 0**の直接確認、17.3節） |
| 19（resume判定のexactness、ambiguous state → fail-closed） | `human_review_resolution.opened_attempt_no`が`record.next_attempt_ordinal`と一致しない状態（データ破損を模擬）で`retry_after_human_review()`を呼ぶ、および`phase`が`TERMINAL`でも上記resume条件を満たす`READY_ELIGIBLE`でもない状態（例：`phase=CLAIMED`）で呼ぶ | いずれのケースもresume分岐を通らず`resolve_human_review()`へフォールスルーし、`phase != TERMINAL`であれば`acknowledged=False, reason="not in HUMAN_REVIEW_REQUIRED"`でfail-closedすること。推測によるdispatch（`RetryManager.retry()`の呼び出し）が発生しないこと |
| 20（attempt budget / lineage integrity enforced、全guardを個別確認） | authorized（`RETRY_ALLOWED`記録済み）状態で`open_next_attempt_after_human_review()`を呼ぶ際、以下3つの既存ガードそれぞれが個別に発火する状況を作る：(a) lineageの既存`attempt_count`が`max_attempts`に達している、(b) `record.next_attempt_ordinal`が`record.attempt_scopes[-1].attempt_no`と同期していない（invariant違反を人為的に注入）、(c) 再計算した`steps_to_execute`が空集合になる（`steps_confirmed_done`が全stepを covering） | authorized経路であっても、(a)(b)(c)いずれの既存ガードもattempt creationを拒否すること——`open_next_attempt()`内の`record.attempt_count >= record.max_attempts`（16章）・`next_attempt_ordinal`同期チェック・`steps_to_execute`非空チェックの3つを個別に直接確認し、authorized経路が通常のFAILED/NOT_ACTIONED経路と完全に同一のガードを共有すること（迂回が存在しないこと）を証明する |

### 28.-27 Invariant #15 direct test

Invariant #15（25章）の「`MEDIA_UPLOAD`の全durable state変更は、単一の`MediaUploadSafetyCoordinator`を経由する」という主張は、production wiringの閉包性（closure）についての主張である。以下は、**repository全体（project-root配下の全`*.py`ファイル・`src/`・`scripts/`配下の全`*.py`ファイル）を対象としたstatic enumerationにより**、Coordinator以外の経路（`ArticleMediaUploadStateManager`・`MediaUploadAttemptContextStore`・`MediaUploadApplicabilityStore`等の低レベルAPI）を直接公開・配線していないことを直接検証する（Coordinator自身の排他制御・cross-store検出の挙動は28.1#1・#6・#7が検証する）。**意味の精密化**：本Invariantは「6.32 protected production `MEDIA_UPLOAD`実行経路のdurable state mutationは、すべてCoordinator経由である」ことを主張するものであり、低レベルmanager API自体の存在や、テスト内で意図的にCoordinatorをバイパスして矛盾を注入すること（28.1#4・#6が行う、構造的限界の実証目的の行為）を禁止するものではない。

| # | シナリオ | 検証項目 |
|---|---|---|
| 1（repository-wide static enumeration） | project-root配下の全`*.py`ファイル（`main.py`を含む）・`src/`・`scripts/`配下の**全`*.py`ファイル**をAST走査し、`ArticleMediaUploadStateManager`・`MediaUploadAttemptContextStore`・`MediaUploadApplicabilityStore`の3つの型**すべて**について、(a) コンストラクタ呼び出し（インスタンス生成）箇所、(b) 生成済みインスタンスが関数引数・戻り値・属性代入として`MediaUploadSafetyCoordinator`以外のオブジェクトへ渡される箇所、の両方をrepository全体から機械的に列挙する（22.1・22.3.2節が特定する既知のComposition Rootファイルへ探索範囲を限定しない。project-root`main.py`は6.32 integration wiring層の起点であり、探索対象から除外しない） | (a)のコンストラクタ呼び出しが、`MediaUploadSafetyCoordinator`自身の初期化コード（Composition Root、22.1・22.3.2節）以外に1件でも存在する場合、および(b)で生成済みインスタンスがCoordinator以外へ渡される箇所が1件でも存在する場合、いずれもFAILとする（**production wiringにおいて、これら3つのstore/manager型への参照を`MediaUploadSafetyCoordinator`以外が保持する箇所 = 0**、repository全体を対象とした直接証明。22.2節「Composition Root...他のいかなる公開APIからもこのManagerインスタンスへ到達できないよう組み立てる」契約の直接検証） |
| 2 | 呼び出し箇所B（15.4節・22.3.2節）のprotected実行パスにおいて、`ArticleMediaUploadStateManager`・`MediaUploadAttemptContextStore`・`MediaUploadApplicabilityStore`の**3つすべて**への直接呼び出し（Coordinator経由ではない呼び出し。`MediaUploadApplicabilityStore`はGate OFF時の`record_not_applicable()`が用いるstoreであり、この3つ目を欠かすとGate OFF経路のCoordinator bypassを見落とす）が**repository全体の**実コード（project-root`main.py`を含む）に存在するかをAST/static call-graph監査で確認する（探索範囲をprotected実行パス上の既知ファイルへ限定しない） | production protected pathからのCoordinator bypassするmutation呼び出し = 0であること（3つのstore型すべてを対象とし、`MediaUploadApplicabilityStore`直接呼び出し=0を含む。production wiringのoracleとして、実際のソースコード・call graphをrepository全体で直接参照する。テスト専用のCoordinator bypass注入（28.1#4・#6）はこの監査の対象外として明示的に除外する） |

### 28.-28 Invariant #21 direct test

Invariant #21（25章）は「ACK Determinismは、durable commitを行う全メソッド（`WordPressDraftStateStore`・`MediaUploadSafetyCoordinator`双方）に、単一の共通ヘルパーを通じて一律に適用する」と主張する。以下は`WordPressDraftStateStore.create_attempted()`/`transition_to_confirmed()`（9.4節）・`MediaUploadSafetyCoordinator`の4公開メソッドの両方が実際に同一ヘルパーを経由することを直接検証する。

| # | シナリオ | 検証項目 |
|---|---|---|
| 1 | `src/wordpress_draft_state/wordpress_draft_state_store.py`（22.1b節）のソースコードをstatic監査（AST解析または直接のsource inspection）し、`create_attempted()`・`transition_to_confirmed()`の実装本体が`src/side_effect_safety/commit_aware_lock.py::_run_with_commit_aware_lock()`（22.1節、共有module）を実際に呼び出していることを確認する | `WordPressDraftStateStore`の両methodが、Coordinator側と同一の共通ヘルパーsymbolを経由すること（個別に独自のlock/cleanup処理を実装していないこと）の直接確認 |
| 2 | `WordPressDraftStateStore.create_attempted()`のbody内でcommitted=True設定後に通常の`Exception`を注入する（28.-4#1・#2・#3・#5と同型のfault injectionを、`MediaUploadSafetyCoordinator`ではなく`WordPressDraftStateStore`側に対して実施する） | `MediaUploadSafetyCoordinator`側のACK Determinism（durable commit成功が維持されること）が、`WordPressDraftStateStore`側でも同一に成立すること |
| 3 | `WordPressDraftStateStore.transition_to_confirmed()`のbody内でcommitted=True設定後に`BaseException`（`KeyboardInterrupt`）を注入する（28.-4#6・#9・#10と同型） | `WordPressDraftStateStore`側でも、cleanupをbest-effortで試行した上で`BaseException`がそのまま再送出されること（Exception/BaseException境界がCoordinator側と同一に適用されること） |
| 4（Coordinator 4公開メソッド全体のstatic監査） | `src/side_effect_safety/media_upload_safety_coordinator.py`のソースコードをstatic監査（AST解析）し、`record_not_applicable()`・`record_prepared()`・`record_attempted()`・`record_confirmed()`の4公開メソッドすべての実装本体が、`src/side_effect_safety/commit_aware_lock.py::_run_with_commit_aware_lock()`を実際に呼び出していることを確認する（#1と同一手法をCoordinator側4メソッド全体へ適用） | 4メソッドすべてが同一の共通ヘルパーsymbolを経由し、個別に独自のlock/cleanup処理を実装していないことを、fault injection（28.-2全件・28.-4全件、indirect evidence）ではなくstatic sourceの直接確認として証明する |

**Mapping品質要件**：25章の40項目のいずれについても、direct test IDがindirectのみ・prose inspectionのみ・Crash Matrix scenarioのみ・test-only negative pathのみに依存してはならない。test-only negative pathをproduction wiring proofとして扱うことは、28.-27節#2が明示的に除外する。

### 28.-29 method→policy binding direct test

**背景**：25章Invariant #40・9.9.4.2/9.9.4.7節が主張する「acknowledged durable semantic commitは別のsemantic kindへ再分類されない」という保証は、`_value_or_recover()`のruntime validation（`policy.validate()`）だけでは完結しない——`_value_or_recover()`は「渡された`policy`との整合性」しか検証できず、「呼び出し元の公開メソッドが実装バグにより誤った`RecoveryPolicy`を渡した」場合までは検出できない。各公開メソッドが自分自身の正しい`RecoveryPolicy`を選択していることは、以下のfixed mappingに対する直接的なsource/static testで担保する。

**authoritative method→policy mapping**：

| 公開メソッド | RecoveryPolicy |
|---|---|
| `record_not_applicable()` | `NotApplicableRecoveryPolicy` |
| `record_prepared()` | `PreparedRecoveryPolicy` |
| `record_attempted()` | `IoArmedRecoveryPolicy` |
| `record_confirmed()` | `ConfirmedRecoveryPolicy` |

| # | シナリオ | 検証項目 |
|---|---|---|
| 1 | `MediaUploadSafetyCoordinator`のソースコード（9.9.4.4・9.9.4.7節の実装、`src/side_effect_safety/media_upload_safety_coordinator.py`）をstatic監査（AST解析またはsource inspection）し、各公開メソッドが`_value_or_recover()`へ渡す`policy=`引数のコンストラクタ呼び出しを特定する | 4メソッドそれぞれが、上記authoritative mappingどおりのRecoveryPolicyクラスのみをインスタンス化してpolicy引数へ渡していること（`record_not_applicable()`→`NotApplicableRecoveryPolicy`等、4件の1:1対応を直接確認。誤った組み合わせ＝mismatched method/policy pair = 0） |
| 2 | 上記#1の監査を、コードレビュー等の人手プロセスではなく、実行可能な自動テスト（ソースコードを解析するテストコード自体）として実装する | このテストがCIで実行可能であり、将来いずれかのメソッドが誤ったpolicyクラスへ変更された場合に機械的に検出できること（実装バグに対する直接的な回帰防止、prose code reviewには依存しない） |
| 3 | 4メソッドそれぞれを実際に呼び出し、返り値の型が`isinstance()`でauthoritative mappingどおりのexact typeと一致することを、Stage 1（正常経路）で直接確認する | `record_not_applicable()`→`isinstance(result, NotApplicableMediaUploadSafetyRecord)`等、4件の実行時型検証（28.-24節の既存テストと組み合わせて、静的監査＝#1・#2と動的検証＝#3の両方で担保する） |

**確認事項**：Invariant #40の保証は、25章本文が明記する4層（exact return type・variant-specific policy・Stage1/2/3 runtime validation・本節のmethod→policy binding direct test）の組み合わせで成立し、そのいずれか1層のみに依存しない。

### 28.-30 Invariant #40 Layer 1・Layer 2 direct test

Invariant #40が明記する4層のうち、Layer 1（4公開メソッドのexact public return type annotation）・Layer 2（各`RecoveryPolicy`クラス自身がvariant-specificであること）を、以下のdirect testが検証する。28.-24節（Stage 1/2/3 runtime validation＝Layer 3）・28.-29節（method→policy binding＝Layer 4）とあわせ、Invariant #40の4層すべてが実行可能なtest IDを持つ。

**Layer 1（exact public return annotations）**：

| # | シナリオ | 検証項目 |
|---|---|---|
| 1 | `MediaUploadSafetyCoordinator`の4公開メソッドに対し、`typing.get_type_hints()`（または`inspect.signature().return_annotation`と同等の直接introspection）を用いて宣言済みの戻り値annotationを取得する | 4メソッドの戻り値annotationが、authoritative mapping（`record_not_applicable`→`NotApplicableMediaUploadSafetyRecord`／`record_prepared`→`PreparedMediaUploadSafetyRecord`／`record_attempted`→`IoArmedMediaUploadSafetyRecord`／`record_confirmed`→`ConfirmedMediaUploadSafetyRecord`）と厳密に一致すること（広い`MediaUploadSafetyRecord`型union・`Any`等ではないこと）を、実行可能なintrospection testとして直接確認する。CIで実行可能であり、いずれかのメソッドの戻り値annotationが変更された場合に機械的に検出できること |

**Layer 2（variant-specific RecoveryPolicy自身の正しさ）**：

| # | シナリオ | 検証項目 |
|---|---|---|
| 2 | 4つの`RecoveryPolicy`クラス（`NotApplicableRecoveryPolicy`/`PreparedRecoveryPolicy`/`IoArmedRecoveryPolicy`/`ConfirmedRecoveryPolicy`、9.9.4.2節）のソースコードをstatic監査（AST解析またはsource inspection）し、各クラスの`expected_type`（ClassVar）と`build_minimal()`メソッド本体が構築するdataclassコンストラクタが一致することを直接確認する | 4クラスそれぞれについて、`expected_type`が指す型と`build_minimal()`が実際にインスタンス化する型が同一であること（例：`PreparedRecoveryPolicy.expected_type is PreparedMediaUploadSafetyRecord`かつ`build_minimal()`が`PreparedMediaUploadSafetyRecord(...)`のみを呼ぶこと）。4クラス×1:1対応、mismatched expected_type/build_minimal pair = 0 |
| 3 | 4つの`RecoveryPolicy`クラスの`validate()`メソッドを、他クラスが構築するsemantic kindの値で呼び出す（例：`PreparedRecoveryPolicy().validate(ConfirmedMediaUploadSafetyRecord(...))`） | いずれの組み合わせでも`None`が返ること（自分自身の`expected_type`以外を受理しないことの直接確認、4×3=12通りの交差検証） |

**§28.6 Invariant #40 mapping更新**：上記2件（Layer 1・Layer 2）を28.-30節として追加し、§28.6のInvariant #40行のLayer 1・Layer 2列を、design pseudo-code自体への参照から本節のtest IDへ差し替える。

### 28.-31 Invariant #5 direct test

Invariant #5（25章、「unresolved HRRからの`open_next_attempt()`禁止（二重ガード）」）は、16章冒頭の「呼び出し元での二重ガード」が主張する2層（呼び出し元のフィルタ・関数自身のチェック）から成る。以下は、`_reconcile_all_locked()`自身が禁止されたterminal disposition（`HUMAN_REVIEW_REQUIRED`）に対して`open_next_attempt()`を**呼ばないこと**を呼び出し元側の層についてspy/mockで直接検証する（関数自身のチェック層は28.-9#1・28.4#23・21章シナリオ25が検証する）。

| # | シナリオ | 検証項目 |
|---|---|---|
| 1 | `RetryLineageManager.open_next_attempt()`をspy/mock（呼び出し回数・引数を記録するダブル）へ差し替えた状態で、`terminal_disposition=HUMAN_REVIEW_REQUIRED`のlineageを1件含む複数lineageに対して`_reconcile_all_locked()`（`retry_lineage_manager.py:576`）を直接呼び出す | 当該HRR lineageの`root_run_id`を引数とする`open_next_attempt()`呼び出しが**一度も発生しないこと**（call count == 0 for that root_run_id）を、spyの記録から直接確認する——`_reconcile_all_locked()`の`opened_countループ`（`terminal_disposition in (FAILED, NOT_ACTIONED)`フィルタ）自体を直接exerciseする |
| 2 | 同様のspy構成で、`terminal_disposition`が`FAILED`・`NOT_ACTIONED`・`HUMAN_REVIEW_REQUIRED`の3種のlineageを混在させて`_reconcile_all_locked()`を呼ぶ | `FAILED`・`NOT_ACTIONED`のlineageに対してのみ`open_next_attempt()`が呼ばれ（call count == 1 each）、`HUMAN_REVIEW_REQUIRED`のlineageに対しては呼ばれないこと（call count == 0）を同一実行内で対比確認する——呼び出し元フィルタが特定のdispositionのみを正しく除外していることの直接証拠 |
| 3 | test #1の状態で、`open_next_attempt()`自体をspyではなく実装のまま呼び出し可能にしておく（呼び出し元フィルタが万一欠落した場合の第2層を単独でも exercise できることを確認） | `open_next_attempt()`自身が`HUMAN_REVIEW_REQUIRED`に対して`acknowledged=False`を返すこと（28.-9#1と同一趣旨、本節では呼び出し元フィルタとの二重性を同一テストスイート内で対比するための再掲） |

### 28.-32 Invariant #8 direct test

Invariant #8（25章、「terminal recordの非recycle（identity分離＋transition validationの二重保証）」）の直接検証は、transition validation（terminal recordへの逆遷移拒否、28.3#5・9・28.-16#7）とidentity分離（別attempt・別effect_siteは構造的に別recordであり、terminal recordの「recycle」に該当しないこと、cross-attempt・cross-effect-siteの識別対象recordが存在しないことを確認する28.3#7・#8）の両方から成る。

- **terminal non-recycle（transition validation）**：28.3#5（`CONFIRMED_SUCCESS`確定済みrecordへの再遷移試行が`acknowledged=False`で拒否され、record内容が変化しないこと）・28.3#9（duplicate create拒否）。
- **identity分離**：28.3#3（attempt 1/2で別identity）・28.3#7（cross-attemptの識別対象recordが存在しないためterminal recordを誤って再利用できないこと）・28.3#8（cross-effect-siteで同様）。
- **reconcile繰り返しでの非recycle**：28.-16#7（`CONTRACT_VIOLATION`判定が複数回のreconcileでも`NOT_APPLICABLE`/`SAFE_TO_CONTINUE`/`CONFIRMED_SUCCESS`へ自動的に読み替えられないこと）。

### 28.-33 Invariant #11 direct test

Invariant #11（25章）は複合claimであり、(a) operation-levelのdurable evidence（`NOT_APPLICABLE`）がstep-levelの粗い判定より優先されること、(b) `MediaUploadApplicabilityStore.create()`自体のduplicate検出、(c) 同ACKのfail-closed契約、の3点を主張する。以下がこの3点を直接検証する（(c)は28.1#8も参照）。

| # | シナリオ | 検証項目 |
|---|---|---|
| 1（duplicate検出、単一決定的outcome） | Gate OFFの`MEDIA_UPLOAD`に対し、`MediaUploadSafetyCoordinator.record_not_applicable()`を同一identity・同一member_run_idで2回連続して呼ぶ | 1回目は`NOT_APPLICABLE`のdurable ACKに成功する。2回目は`_read_all(..., allow_absent_only=True)`（9.9.4.4節）がcategory≠`ALL_ABSENT`を検出し、**必ず**`MediaUploadSafetyTransitionError`を送出すること——既存recordを冪等にそのまま返す分岐は許容しない。2回目の呼び出しで`MediaUploadApplicabilityStore.create()`が一切呼ばれないこと（**追加のdurable write・external I/Oが発生しないこと**）をモックの呼び出し回数で直接確認する |
| 1b（ACK済みcommit後のreturn/recovery failureとの区別、新設） | 1回目の`record_not_applicable()`呼び出しで、`applicability_store.create()`のACK確認・`commit_state["committed"] = True`設定の**後**に、戻り値（`NotApplicableMediaUploadSafetyRecord`）構築を人為的に例外送出させる（21章シナリオ45と同一の注入点） | このcommit-then-construction-failureの場合は、`_run_with_commit_aware_lock()`のpost-commit契約（9.9.4.3節）により`_value_or_recover()`のStage 2（durable reread）が実行され、直前にこの呼び出し自身がACKした`NotApplicableMediaUploadSafetyRecord`を正しく返すこと（duplicate mutationの再実行ではない——`create()`は1回しか呼ばれていない）。test #1（pre-commit・別呼び出しからのduplicate）とは区別されるシナリオであることを同一テストスイート内で対比確認する |
| 2（operation-level evidence優先、既存testの直接参照） | 28.-16#2・#3（record非存在＋`StepOutcomeCategory`を6値それぞれに変えても、durable operation-level evidenceが存在しない限り常に`CONTRACT_VIOLATION`となり、step-level値が一切参照されないこと）・28.-17#1・#2（`classify()`内部で`StepOutcomeCategory`関連の値が一切参照されないことをモックの呼び出し回数で直接確認） | 上記各testが、operation-levelのdurable evidence（本節#1で確認する`NOT_APPLICABLE`のACK済みrecordを含む）のみが安全性判定の根拠となり、stepレベルの粗い判定に優先することの直接証拠として、本Invariantのmapping行に含まれる |
| 3（ACK失敗のfail-closed契約、既存test） | 28.1#8（`MediaUploadApplicabilityStore.create()`のdurable writeを失敗させる） | `MediaUploadSafetyIOError`が送出され、**external upload count == 0**（Gate OFFのため元々0だが、ACK失敗自体がfail-closedに扱われることを確認） |

### 28.-34 Invariant #35 direct test

Invariant #35（25章）は、A（NEWS側WordPress draft）・C（PUBLISH側WordPress draft）が同一`WordPressDraftStateStore`/`WordPressDraftStateManager`契約を再利用しつつ`effect_site`で構造的に別recordとなること、およびA/B/C（1.2節）のいずれも write-ahead契約から漏れないことを主張する。以下の4件がこれを直接検証する。

**Release 6.32 closed WordPress-mutation transport policy**：6.32のprotected production side-effect（呼び出し箇所A/B/C）がWordPressへmutating HTTPリクエストを送る手段は、以下のtransport mechanismのclosed setに限定される——(i) 任意のreceiver（module-level `requests`、`requests.Session()`インスタンス、コンストラクタ注入・factory戻り値・attribute経由で取得したSessionを含む、receiverの取得経路を問わない）に対する`.post(...)`/`.put(...)`/`.patch(...)`/`.delete(...)`呼び出し、(ii) 任意のreceiverに対する`.request(...)`呼び出し（`method`引数が`"POST"`/`"PUT"`/`"PATCH"`/`"DELETE"`のいずれか、または静的に安全側〈`"GET"`/`"HEAD"`/`"OPTIONS"`〉と証明できない値）、(iii) `data=`または非GET `method=`を伴う`urllib.request.Request(...)`構築、(iv) 任意のreceiverに対する`.urlopen(...)`呼び出し（`Request`オブジェクトを経由しない直接呼び出し形を含む）。本policyは呼び出しのreceiver（変数の型・取得経路）を判定条件とせず、メソッド名・呼び出し形のみによって候補を識別する——receiverの型が静的に解決できない場合や未知の型である場合も、候補から除外しない。動的な呼び出し形は、28.-34節#4が定めるclosed dynamic-call grammar（直接の属性呼び出し・`Request(...)`構築・string literal引数の`getattr(...)`呼び出しの3形式、およびstring literalでない`getattr(...)`呼び出しをfail-closed candidateとして扱う規則）の範囲でのみ候補として扱う——このgrammarの外側にある間接呼び出し形（変数・辞書・`functools.partial`等に格納されたcallableの呼び出し等）は本policyの自動検出範囲外であると明示的に宣言する。このpolicyが列挙しないtransport mechanism（別のHTTPクライアントライブラリの使用、closed dynamic-call grammarの外側にある間接呼び出し形の使用等）を用いてWordPress mutationを実装することは、それ自体がこのpolicyへのcontract violationである。現時点でapprovedなmutation siteはA（`src/outputs/wordpress_output.py`）・B（`src/wordpress_media/wordpress_media_uploader.py`）・C（`src/ai/wordpress_draft_client.py`）の3箇所のみである。test #4はこのpolicyが定めるreceiver非依存の検出規則に基づきrepository全体を静的に検査し、approved A/B/C・safe-non-mutation・unknown（fail-closed candidate）への分類を行う——policy外のtransport mechanism（`requests`/`urllib.request`のいずれのimportにも依存しない別ライブラリでの実装）を用いた未知の実装が存在しないことまでは、本テストのみでは証明しない（それはコードレビュー運用・22.2節No Bypass Proofの規律に委ねる）。

| # | シナリオ | 検証項目 |
|---|---|---|
| 1（A/C再利用＋identity分離、既存testの直接参照） | 28.-11#6（同一article・同一attemptでA＝`effect_site=NEWS_STEP`とC＝`effect_site=PUBLISH_STEP`の両方が`WORDPRESS_DRAFT_CREATION`を実行）・28.3#1（同一趣旨） | A・Cが同一`WordPressDraftStateStore`/`WordPressDraftStateManager`契約を経由しつつ、`effect_site`の違いにより8章のidentityレベルで完全に別recordとなり、互いにduplicate扱いされないこと |
| 2（B独立性、既存testの直接参照） | 28.-11#7（同一article・同一attemptでA＝`WORDPRESS_DRAFT_CREATION`とB＝`MEDIA_UPLOAD`が同時に評価される） | 一方のevidence（例：Bが`CONFIRMED_SUCCESS`）が他方（Aの状態）の判定に一切影響しないこと（`operation_kind`差異による構造的分離、25章#36） |
| 3（closed set exhaustiveness、repository-backed enumeration、fail-fast manifest match + 回帰検証の2段構成） | **オラクルはrepository自身とする（22.3.11節の手動tableではない）。22.3.11節と28.-20節#5は本節と同一のオラクル定義を参照するのみで、独立したgrep heuristicを持たない。** 以下の2段で機械的に算出する：<br>**Stage A（fail-fast manifest match、新規root発見・重複分類検出）**：<br>　**(1) candidate root列挙**：(a) project-root配下の全`*.py`ファイル（project-root直下に新たに追加される`*.py`ファイルも自動的に含む）、(b) `scripts/**/*.py`（`scripts/`配下の全`*.py`ファイル）、(c) repository実在のpackaging/console-script entrypoint（`pyproject.toml`/`setup.py`/`setup.cfg`のentry_points宣言、本repositoryには存在しないため空集合）の合併をファイルシステムから直接列挙する。<br>　**(2) closed classification manifestとのexactly-once match**：(1)で列挙した各candidate rootのファイルパスが、22.3.11節の分類manifest（`SIDE_EFFECT_CAPABLE`9エントリ＋`NON_SIDE_EFFECT_CAPABLE`10エントリ、計19エントリ）にちょうど1回だけ出現するか確認する。manifestに1件も出現しないcandidate root（新規に追加されたfile等）が存在する場合、または2つ以上の分類に重複して出現するcandidate rootが存在する場合、**この時点で本テストは無条件にFAILする**——到達可能性のclosure探索を試みる前に、unclassified/duplicate-classified rootとして直ちに検出する。<br>**Stage B（manifestに存在する19エントリの回帰検証、22.3.11節Classification ruleと同一のsink-terminal closureオラクルを使用）**：Stage Aを通過した（＝manifestとexactly-once一致した）19エントリについてのみ、実際の分類が22.3.11節のmanifestと一致することを以下の手順で確認する：<br>　**(3) `AgentManager.run()`到達launcherの識別**：4ファイル（`run_news_agent.py`・`run_workflow_trigger_agent.py`・`run_publish_trigger_agent.py`・`run_review_trigger_agent.py`）のASTを解析し、`AgentManager.from_config`/`.run`のimport・呼び出しを確認する。<br>　**(4) registered executor集合の導出**：`src/ai/agent_manager.py::AgentManager.from_config()`を静的解析し、`NewsAgent`が無条件登録（`AgentConfig.is_ready()`のみに依存）、`WorkflowTriggerAgent`/`PublishTriggerAgent`/`ReviewTriggerAgent`が各Configの`is_ready()`ゲートで条件付き登録されることを確認する——**launcher scriptの名前からこの集合を決定しない**。<br>　**(5) aggregate reachability確認**：(4)の登録契約はどの`AgentManager`経由launcherからでも同一であるため、4ファイルいずれについても到達しうるoperation集合は{A, B, C}のaggregateと一致することを確認する（22.3.11節Classification ruleと同一の結論——launcher名で異なる固定subsetにはならない）。<br>　**(6) 非AgentManager経由15ファイル（`SIDE_EFFECT_CAPABLE`5・`NON_SIDE_EFFECT_CAPABLE`10、AgentManager経由4を除く全19エントリ中の残り15ファイル）のclosure解析**：各fileについて、22.3.11節Classification ruleが定める**recursive intra-project static call/import closure**（本repository内のimport/呼び出しを再帰的に辿り、A＝`WordPressOutput.save()`・B＝`ArticleFeaturedMediaRuntime.apply()`・C＝`AiPublishService.run()`/`_process()`/`_post()`のいずれかの呼び出しをterminal sinkとして記録する）を実際にAST解析で構築し、到達したsink集合を算出する。`SIDE_EFFECT_CAPABLE`5ファイル（`main.py`・`run_ai_publish.py`・`run_ai_workflow.py`・`run_workflow_engine.py`・`run_retry_runtime.py`）は算出結果が22.3.11節の表と一致することを、`NON_SIDE_EFFECT_CAPABLE`10ファイルは算出結果が空集合であることを、それぞれ確認する（`run_ai_publish_review.py`が`AiPublishReviewService`のみをimportし`AiPublishService`を一切importしないこと、`run_ai_rewrite.py`が`WordPressArticleProvider`経由でsink非到達のGET-only経路にのみ到達すること、をclosureの実際の中間ノードとして直接確認する——symbol名の字面一致には依存しない）。<br>　**(6b) Protocol/抽象型経由呼び出しのfinite-set resolution**：closure探索中に、呼び出しのreceiverがProtocol/abstract base/抽象型注釈（例：`RewriteService._provider: ArticleProvider`）で宣言されている場合、まずrepository実在のconstruction/composition/config箇所（`from_env()`・`from_config()`等のfactory）を静的に解析し、その抽象型へ実際に代入されうる**具象実装の集合が有限（finite）であることを証明できるか**を確認する。証明できる場合（例：`ArticleProvider`は`WordPressArticleProvider`または`NullArticleProvider`のいずれかにのみ解決されることが、これらのfactory・config分岐から静的に確定できる場合）——finite set内の**すべての**具象実装についてそれぞれ独立にclosure解析を行い、到達するsink集合の**和集合**をその呼び出し箇所の到達sink集合として採用する（`WordPressArticleProvider`は呼び出し箇所A/B/Cいずれにも到達しないGET-only経路のみ、`NullArticleProvider`はいかなる呼び出しも行わない——union = 空集合）。finite setの証明ができない場合（実装が動的にロードされる、外部プラグイン機構経由である等）は(7)の`unresolvable`へ進む。<br>　**(7) 証明不能ケースの検出**：(6)(6b)のclosure解析中に静的に解決不能な動的呼び出し辺（Protocol/抽象型の具象実装集合がfiniteであると証明できない間接呼び出し、`getattr`動的属性呼び出し等）に遭遇した場合、当該candidate rootを`unresolvable`として記録する | Stage A：(1)で列挙したcandidate rootのうち1件でもmanifest（22.3.11節19エントリ）に存在しない場合、または2つ以上の分類に重複して出現する場合、到達可能性の判定を行う前に本テストはFAILする（**unclassified/duplicate-classified protected production side-effect site = 0**、repository-to-manifest比較として直接証明する）。project-root配下の`*.py`ファイルは`scripts/**/*.py`側と同様に新規追加時も自動的に検出対象へ含まれ、候補集合を事前に手動拡張する手順は不要である。Stage B：(5)のaggregate reachabilityが22.3.11節の表（A・B・C）と食い違う場合、(6)のclosure算出結果がmanifestの記載（`SIDE_EFFECT_CAPABLE`の到達operation集合、または`NON_SIDE_EFFECT_CAPABLE`の空集合）と食い違う場合、または(7)で`unresolvable`と記録されたcandidate rootが1件でも存在する場合、本テストはFAILする（証明不能を安全側へ推測しない）。closure解析は本repository内のimport/呼び出しグラフを直接辿るため、known symbolの固定リストに依存する検出限界を持たない——この限界はむしろ#4のsink-oriented static oracle（HTTPミューテーションprimitive自体を検出、known symbol非依存）と相互補完の関係にあり、両者は独立に実行され、いずれかがFAILすればInvariant #35全体がFAILとなる |
| 4（sink-oriented static oracle、receiver非依存、closed dynamic-call grammar、6.32 scope） | **オラクルはHTTPミューテーションのprimitiveそのものとする（known symbol importの検出でも、receiver変数のtype解決でもない）**。以下の手順で機械的に算出する：<br>**(1) closed grammarによるcandidate discovery**：production code（`src/`・`scripts/`・project-root`*.py`、`tests/`等は対象外）の全`*.py`ファイルをASTで走査し、以下の閉じた文法（closed grammar）に構文的に一致する`Call`ノードのみを候補として扱う：<br>　(a) 属性アクセス名が`post`/`put`/`patch`/`delete`/`request`/`urlopen`である直接呼び出し（`<any-receiver>.M(...)`、receiver式の型を解決せず属性名のみで候補とする——Pythonの構文上、属性名は常にAST上のリテラル識別子であるため、このアクセス自体に「動的な属性名」は存在しない）。<br>　(b) 呼び出し名（属性アクセスまたは単純name、import-alias解決込み）が`Request`である構築呼び出し。<br>　(c) `getattr(<receiver>, <name>)(...)`形式の呼び出しで、`<name>`がstring literalである場合——`<receiver>.<name>(...)`と等価に扱い、(a)へ帰着させる。<br>　(d) `getattr(<receiver>, <name-expr>)(...)`形式で`<name-expr>`がstring literalでない場合（属性名自体が実行時に決定される）——この呼び出し形はAST上の構造（`Call(func=Call(func=Name("getattr"), args=[..., <non-literal>]))`）で機械的に識別可能であり、除外判定が構造的に不可能であるため無条件で`unknown` candidateとして扱う（fail-closed）。<br>(a)〜(d)以外の間接呼び出し形（変数・辞書・`functools.partial`等に格納されたcallableの呼び出し、`operator.methodcaller`等）は、この閉じた文法の外側にあるため**本オラクルの候補discovery対象外と明示的に宣言する**——任意のPython動的呼び出しパターンを網羅的に検出するという主張はしない。このような間接化を用いてWordPress mutationを実装することは、それ自体が本節冒頭のtransport policyへのcontract violationであり、22.2節No Bypass Proofの運用規律の対象となる。<br>**(2) method判定（(a)(c)の`.request`）**：`method`引数（キーワードまたは対応するpositional）がstring literalとして解決でき、かつ`"GET"`/`"HEAD"`/`"OPTIONS"`のいずれかである場合のみ`safe-non-mutation`。それ以外（`"POST"`等のmutating literal、動的値、省略）はmutating candidate。<br>**(3) `Request(...)`自身の判定（(b)(c)、urllib仕様に合わせたexact判定、positional引数も含む）**：`urllib.request.Request.__init__`の実シグネチャ（`Request(url, data=None, headers={}, origin_req_host=None, unverifiable=False, method=None)`）に基づき、`data`は`data=`キーワードまたは第2 positional引数のいずれか、`method`は`method=`キーワードまたは第6 positional引数のいずれかで判定対象とする（キーワード・positionalいずれか一方にのみ着目する実装は不可——`Request(url, encoded, {}, None, False, "DELETE")`のような全positional指定のmutationを見落とさない）。同一呼び出しで`data`（または`method`）がキーワードとpositionalの両方で指定されているように見える場合（本来のPython構文では単一呼び出し内で同時に成立しないが、解析上の混同を避けるため）——`unknown`として扱う（fail-closed、いずれの値を採用するか推測しない）。<br>　(A) `data`引数が存在しない、またはliteralの`None`であり、かつ`method`引数も存在しない場合——urllib仕様の既定動作（dataなし＝GET相当）に従い`safe-non-mutation`とする。<br>　(B) `data`引数が(A)と同様に不在/Noneであり、`method`が`"GET"`/`"HEAD"`/`"OPTIONS"`のいずれかのstring literal（キーワードまたは第6 positional）である場合——`safe-non-mutation`とする（`"GET"`のみを安全側として扱う実装は誤り——HEAD/OPTIONSも同様にmutationを行わない）。<br>　(C) `data`引数（キーワード・第2 positionalいずれか）がNoneでない値として渡されている場合——その値が静的に解決可能か動的かを問わず、mutation candidateとする（urllibは`data`が与えられると既定でPOSTとして送信するため）。<br>　(D) `method`（キーワードまたは第6 positional）が`"POST"`/`"PUT"`/`"PATCH"`/`"DELETE"`等、GET/HEAD/OPTIONS以外のstring literalである場合——`data`の有無に関わらずmutation candidateとする。<br>　(E) `method`が変数・式・f-string等で静的に解決できない場合、または`data`引数がNoneかどうか静的に証明できない場合——`unknown`として扱う（fail-closed、安全側へ推測しない）。<br>**(4) `urlopen`呼び出しの論理的関連付け（logical transport operation linking）**：(a)/(c)で識別した`urlopen`呼び出しの第1引数（`url`パラメータに対応する式）について：<br>　(i) 引数がinlineの`Request(...)`呼び出しである場合——その`Request(...)`自身を(3)で判定し、`urlopen`呼び出し全体をその結果（safe-non-mutation／mutating candidate）として扱い、`Request(...)`と`urlopen(...)`を1つの論理的transport operationとして統合する（2件の独立candidateとしてdouble-countしない）。<br>　(ii) 引数が単純なlocal変数`X`であり、同一関数scope内で`X = Request(...)`という単一の代入（分岐による複数代入・再代入・関数外へのescape〈return・attribute格納・別関数への引渡し〉のいずれも存在しない、静的に一意なdef-useリンク）によって束縛されている場合——(i)と同様に、その`Request(...)`を(3)で判定し、`urlopen(X)`呼び出しへ結果を伝播させ、1つの論理的transport operationとして統合する（`src/ai/article_provider.py`の`req = urllib.request.Request(api_url, headers=...)` → `urlopen(req, timeout=15)`がこの実例であり、`Request`構築に`data=`も非GET `method=`もないためsafe-non-mutationとなる）。<br>　(iii) 引数が`Request(...)`のいずれかの形（inlineまたはdef-use解決済み変数）にも解決されず、かつ静的にURL-like value（string literalまたはf-string、`Request`型ではないことが構文上明らかな式）であると証明できる場合——`urllib.request.urlopen(url, data=None, ...)`の実シグネチャに基づき、`urlopen`呼び出し自身に`data=`キーワードまたは第2 positional引数が存在しなければ`safe-non-mutation`とする（いずれかの形で`data`が存在すればmutating candidate）。**「`urlopen`呼び出し自身に`data=`がないから安全」という判定は、この`Request`型ではないと証明済みの場合にのみ適用してよく、それ以外には適用しない。**<br>　(iv) 上記(i)(ii)(iii)のいずれにも該当しない場合（引数が関数パラメータ、複数代入・分岐を経た変数、他関数の戻り値、`Request`型かどうかが静的に確定できないその他の式——provenanceがunresolved/ambiguous）——`unknown`として扱う（fail-closed）。解決不能な`Request`風オブジェクトが内包しうる`method=`は`urlopen`呼び出し自身の引数からは観測できないため、「`urlopen`にdata=がないだけ」を理由に安全側へ倒さない。<br>**(5) classification（approved A/B/C・safe-non-mutation・unknown）**：(4)で統合済みの論理的transport operationおよび単独candidateを、file/line/enclosing symbolで一意に識別し、`src/outputs/wordpress_output.py`の`requests.post`（呼び出し箇所A）・`src/wordpress_media/wordpress_media_uploader.py`の`requests.post`（呼び出し箇所B）・`src/ai/wordpress_draft_client.py`の`Request(data=..., method="POST")`+`urlopen()`統合site（呼び出し箇所C）のいずれかへ対応付けたclassification tableと突き合わせる。A/B/Cのいずれにも対応付かない候補のうち、(2)(3)(4)の除外条件を満たすものは`safe-non-mutation`として分類し、(1)(d)のdynamic-attribute candidateを含め、それ以外はすべて`unknown`として分類する。<br>**(6) unknown candidate = 0**：`unknown`に分類された候補が1件でもあれば、本テストは無条件でFAILとする——A/B/Cへの推測分類・自動割り当ては行わない | (a) repository全体のcandidate discoveryが、A（`wordpress_output.py`）・B（`wordpress_media_uploader.py`）・C（`wordpress_draft_client.py`の`Request`+`urlopen`統合site）の3件をapprovedとして検出し、他に検出される候補は`safe-non-mutation`としてのみ分類されること。`src/ai/article_provider.py`の`Request(GET-like)`→`urlopen(req)`は、(4)(ii)のdef-useリンクにより1つの統合siteとしてsafe-non-mutationに分類され、`urlopen`単体が独立`unknown`candidateにならないことを直接確認する（spurious unknown = 0）。(b) `unknown`分類の候補（(1)(d)のdynamic-attribute呼び出しを含む）が検出された場合、本テストはFAILする。(c) 本オラクルは「Release 6.32 closed WordPress-mutation transport policy」（本節冒頭）が定めるclosed grammarにscopeを限定し、任意のPython動的呼び出しを完全検出するという主張はしない——(1)で明示的に宣言した間接呼び出し形・policy外のHTTPクライアントライブラリ・汎用external-I/O analyzerへは拡張しない（4章Non-Goals） |

**Invariant #35のPASS条件**：test #3（fail-fast manifest match + sink-terminal closure解析）とtest #4（sink-oriented static oracle）の両方が独立にPASSすること。片方のみのPASSでは`direct`とみなさない——2つのオラクルは異なる検出原理（import/call closureのsink到達性 vs. HTTPミューテーションprimitive自体の構文検出）に基づく相互補完であり、一方の限界（test #3のclosure解析はPythonのimport/call構造を辿るがHTTP呼び出しの意味は見ない、test #4はHTTP呼び出しの意味を見るがどのentrypointから到達するかは見ない）をもう一方が構造的に補う。

### 28.-35 `_apply_featured_media_step()`明示的dependency binding direct test

**背景**：`main.py::_apply_featured_media_step()`は22.3.2節の要求（`side_effect_execution_context`・`MediaUploadWriteAheadAdapters`・`MediaUploadSafetyCoordinator`・legacy/protected execution mode・既存legacy Runtimeへのアクセス）を満たすため、`FeaturedMediaSideEffectBinding`（closed discriminated union、`ProtectedFeaturedMediaSideEffectBinding`/`LegacyFeaturedMediaSideEffectBinding`）を用いた確定シグネチャを持つ（22.3.2節）。build系は`build_protected_featured_media_side_effect_binding(protected_context, coordinator, adapters)`／`build_legacy_featured_media_side_effect_binding(legacy_context, runtime)`の2 builderに分かれ、legacy builderのシグネチャはcoordinator/adaptersを持たない。`_apply_featured_media_step()`自体は`runtime`位置引数を持たず、runtimeの源泉は`side_effect_binding`側（legacy＝binding自身が保持する既存runtime、protected＝binding情報から呼び出しのたびに`build_protected_featured_media_runtime()`で構築）に一本化されている。以下はこの契約のdirect test。

| # | シナリオ | 検証項目 |
|---|---|---|
| 1（explicit binding signature） | `main.py::_apply_featured_media_step`のシグネチャをinspect（`inspect.signature()`）する | 位置引数は`article`の1つのみであり、`runtime`という名の位置引数が存在しないこと。keyword-only引数`side_effect_binding`（型注釈`FeaturedMediaSideEffectBinding`）が存在すること。globals・モジュールレベルの`media_upload_coordinator`等の暗黙参照を関数本体がimport/参照していないこと（AST監査、`ast.parse()`によるstatic import解析） |
| 2（protected binding propagation） | `build_protected_featured_media_side_effect_binding(context, media_upload_coordinator, adapters)`が返す`ProtectedFeaturedMediaSideEffectBinding`を、`side_effect_binding`として`_apply_featured_media_step(article, side_effect_binding=binding)`へ渡す | `binding.context`・`binding.media_upload_coordinator`・`binding.adapters`から取り出した値のみが`identity`構築・`record_prepared()`/`record_not_applicable()`/`build_protected_featured_media_runtime()`呼び出しへ使われること（モックのcall引数を直接検証）。関数呼び出し全体を通じて外部から`runtime`が渡されていないこと |
| 3（legacy binding zero safety calls） | `build_legacy_featured_media_side_effect_binding(context, runtime)`が返す`LegacyFeaturedMediaSideEffectBinding`（`media_upload_coordinator`・`adapters`フィールド自体を持たないが`runtime`フィールドを持つ）を`_apply_featured_media_step(article, side_effect_binding=binding)`へ渡す | `record_not_applicable()`/`record_prepared()`/`record_attempted()`/`record_confirmed()`の4メソッドいずれも呼び出し回数0であること（spy/mockで直接確認）。`binding.runtime.apply(article)`のみが呼ばれ（渡した`runtime`インスタンスと`is`比較で同一）、成功時の戻り値（`ArticleFeaturedMediaRuntimeResult`）が既存（6.31以前）のまま無変更で伝播すること。`apply()`がPROPAGATE対象例外を送出した場合は22.3.2節の共通try/exceptにより`runtime.classify_propagated_failure(exc)`（既存、無変更）で分類され`FeaturedMediaPropagatedFailure`として送出されること（raw exceptionの直接伝播ではない——protected分岐と共通の単一try/exceptを経由することの確認） |
| 4（missing/unknown binding fail-closed） | `side_effect_binding`に`ProtectedFeaturedMediaSideEffectBinding`/`LegacyFeaturedMediaSideEffectBinding`いずれでもないオブジェクト（`None`を含む）を人為的に渡す | `media_upload_coordinator.record_*()`・`runtime.apply()`のいずれも呼ばれる**前**に`SideEffectExecutionModeContractError(ExecutionModeFailureReasonCode.UNKNOWN_EXECUTION_MODE)`が送出されること（**external I/O = 0**、call count 0を直接確認） |
| 5（globals/ambient fallback = 0） | `src/`・`main.py`をsource監査（static grep/AST）する | `_apply_featured_media_step()`本体が、`side_effect_binding`引数以外の経路（module-level変数・`os.environ`直接参照・singleton取得関数呼び出し等）から`MediaUploadSafetyCoordinator`・`RetryLineageProtectedExecutionContext`・`LegacyDirectExecutionContext`・`ArticleFeaturedMediaRuntime`のいずれかのインスタンスを取得していないこと |
| 6（Foundation constructor zero-diff） | `article_featured_media_runtime.py`・`article_featured_media_orchestrator.py`・`article_featured_media_composition_root.py`の3ファイルをsource監査する | `FeaturedMediaSideEffectBinding`・`ProtectedFeaturedMediaSideEffectBinding`・`LegacyFeaturedMediaSideEffectBinding`のいずれのimport・型参照も存在しないこと（Foundation 3ファイルへの6.32 module importが0件であることの直接確認、15.4.1節・28.-22節#11・#12と同一趣旨） |
| 7（protected builder exact dependencies） | `build_protected_featured_media_side_effect_binding(protected_context, coordinator, adapters)`を呼ぶ | 返る`ProtectedFeaturedMediaSideEffectBinding`の`context`・`media_upload_coordinator`・`adapters`各フィールドが、引数として渡した値とそれぞれ同一（`is`比較）であること。シグネチャが3引数すべて必須（デフォルト値なし）であること（`inspect.signature()`）。フィールドに`runtime`が存在しないこと（protected runtimeはbindingに保持せず呼び出しのたびに導出する契約であることの確認） |
| 8（legacy builder requires context and runtime） | `build_legacy_featured_media_side_effect_binding(legacy_context, runtime)`のシグネチャを`inspect.signature()`でinspectする | 引数が`legacy_context`・`runtime`の2つ（いずれも位置引数、デフォルト値なし）のみであり、`media_upload_coordinator`・`adapters`に相当するparameterが存在しないこと。返る`LegacyFeaturedMediaSideEffectBinding`が`media_upload_coordinator`・`adapters`のいずれのfieldも持たず、`context`・`runtime`の2 fieldのみを持つ（`dataclasses.fields()`で直接確認）dataclassであること |
| 9（legacy path zero protected-dependency factory calls） | `isinstance(context, LegacyDirectExecutionContext)`の経路でmain.py起動処理を実行し、`MediaUploadSafetyCoordinator`のコンストラクタ・`MediaUploadWriteAheadAdapters.from_env()`をspy/mockで監視する | いずれも呼び出し回数0であること（**legacy modeでprotected dependenciesを構築してから破棄する経路が存在しないことの直接証明**） |
| 10（production dispatch path uses authoritative builder） | `main.py`のtrusted composition boundary（起動時のtype dispatch箇所）をsource監査、および`RetryLineageProtectedExecutionContext`/`LegacyDirectExecutionContext`それぞれを与えてmain()の当該分岐を実際に実行する（test #2・#3が行っていた`ProtectedFeaturedMediaSideEffectBinding`/`LegacyFeaturedMediaSideEffectBinding`の直接構築によるbuilder bypassとは異なり、本テストは実際のdispatchコードパスを経由する） | `main.py`が`ProtectedFeaturedMediaSideEffectBinding`/`LegacyFeaturedMediaSideEffectBinding`のコンストラクタを直接呼ばず、必ず`build_protected_featured_media_side_effect_binding()`/`build_legacy_featured_media_side_effect_binding()`のいずれかを経由して`side_effect_binding`を得ていること（AST監査＋実行時spy）。legacy分岐では起動時に構築済みの`featured_media_runtime`（`ArticleFeaturedMediaRuntime.from_env()`）が`build_legacy_featured_media_side_effect_binding()`の`runtime`引数へそのまま渡されていること。単一factory`build_featured_media_side_effect_binding()`（不採用、30章参照）への参照が0件であること |
| 11（protected runtime source uniqueness） | `ProtectedFeaturedMediaSideEffectBinding`を`side_effect_binding`として`_apply_featured_media_step(article, side_effect_binding=binding)`を、Gate ON・Gate OFF双方の`adapters.enabled`値でそれぞれ呼ぶ | いずれの場合も`build_protected_featured_media_runtime(binding.adapters, binding.media_upload_coordinator, identity, binding.context.member_run_id)`が呼ばれ、その戻り値の`.apply(article)`が呼ばれること（モックのcall順序・引数を直接確認）。Gate ON/OFFで呼び出しコードパスが分岐しないこと（**runtime source ambiguity = 0**の直接証明） |
| 12（legacy runtime is the prebuilt instance） | main.py起動時に構築される`featured_media_runtime`のインスタンスIDを記録し、`build_legacy_featured_media_side_effect_binding(context, featured_media_runtime)`経由で`_apply_featured_media_step()`まで伝播させる | `_apply_featured_media_step()`内で`.apply()`が呼ばれる`runtime`オブジェクトが、起動時に構築された`featured_media_runtime`と`is`比較で同一インスタンスであること（記事ごとの再構築が発生しないこと、legacy modeの既存6.31以前の挙動が無変更であることの直接証明） |
| 13（helper signatureにorphan runtime argument = 0） | `_apply_featured_media_step`・`build_protected_featured_media_side_effect_binding`・`build_legacy_featured_media_side_effect_binding`・`ProtectedFeaturedMediaSideEffectBinding`・`LegacyFeaturedMediaSideEffectBinding`のシグネチャ／フィールドをすべて`inspect`/`dataclasses.fields()`で列挙する | `runtime`という名のパラメータ・フィールドが存在するのは`LegacyFeaturedMediaSideEffectBinding.runtime`・`build_legacy_featured_media_side_effect_binding()`の`runtime`引数の2箇所のみであり、それ以外（`_apply_featured_media_step`の引数・`ProtectedFeaturedMediaSideEffectBinding`のフィールド・protected builderの引数）には一切出現しないこと |
| 14（protected startupでのunused legacy runtime construction = 0） | `main.py`の起動処理を`isinstance(context, RetryLineageProtectedExecutionContext)`の経路で実行し、`ArticleFeaturedMediaRuntime.from_env()`・`ArticleFeaturedMediaCompositionRoot.from_env()`をspy/mockで監視する | いずれも呼び出し回数0であること（**protected startupで「使わないlegacy Runtimeを構築してから破棄する」経路、および「構築するかどうかを実装が選択できる」という二択が構造的に存在しないことの直接証明**）。同一spyで`isinstance(context, LegacyDirectExecutionContext)`の経路を実行した場合は`ArticleFeaturedMediaRuntime.from_env()`が呼び出し回数1であることも合わせて確認し、分岐ごとの起動経路が単一であることを対比的に証明する |
| 15（PROPAGATE分類carrier、legacy/protected共通） | `runtime.apply(article)`がPROPAGATE対象の例外（`decide_image_generation_fallback()`がPROPAGATEと判定するもの）を送出する状況を、`ProtectedFeaturedMediaSideEffectBinding`・`LegacyFeaturedMediaSideEffectBinding`それぞれについて`_apply_featured_media_step(article, side_effect_binding=binding)`へ渡して再現する | いずれの分岐でも`FeaturedMediaPropagatedFailure`が送出され：(1) `carrier.observation`が`runtime.classify_propagated_failure(exc)`（既存、無変更）の戻り値と等価であること、(2) `carrier.__context__ is None`かつ`carrier.__cause__ is None`であること（`raise`が対応するexcept節の外側で行われるため、暗黙のexception chainingが一切付与されないことの直接確認——`raise ... from None`への依存ではない）、(3) raw exceptionオブジェクト自体・その`str(exc)`メッセージのいずれも`carrier`の属性から到達不能であること（`vars(carrier)`が`observation`以外のフィールドを持たないことを直接確認）、(4) legacy/protected双方で同一の`.observation`値・同一の`__context__`/`__cause__`が`None`という結果が得られること（分岐間のsemantics一致）。`SideEffectExecutionModeContractError`を送出する状況（test #4）では`FeaturedMediaPropagatedFailure`が送出されない（`except SideEffectExecutionModeContractError: raise`が`except Exception`より先に評価され、carrier化されない）ことも合わせて確認する |

### 28.-36 WorkflowRunner Chain Invariant #37 direct closure

Invariant #37（25章）は、protected side-effect operationがauthoritative run-scoped side-effect execution context（2.1節discriminated union）由来の識別のみを用い、scheduler event metadata・`AgentTask.params`・ambient環境状態から再構築・推測しないこと、および各boundary（`WorkflowEngineManager.run()`・`WorkflowEngineExecutor`・`AgentContext`・NEWS/PUBLISH pipeline runner・subprocess境界・protected side-effect runtime）でcontextがmissing/malformed/mismatchであればfail-closedすることを主張する。28.-12節（13件）が`WorkflowEngineContext`→`AgentContext`および News/Publish pipeline runnerの一般的なpropagationを直接検証するのに対し、以下は実際の`WorkflowTriggerAgent`→`WorkflowPipelineRunner`→`WorkflowRunner`→`WorkflowContext`→`PublishStepExecutor`という具体的なprotected chainを直接exerciseするtest、およびWorkflowRunner-chainレベルでunknown context type・correlation metadataからの再構築禁止を直接検証するtestである。

`PublishStepExecutor.execute()`をauthoritative validation boundaryとし（`validate_side_effect_execution_context()`を既存`try`ブロックの外側で呼ぶ、22.3.12節）、test #3・#4はこの契約を検証する。test #7はcontract errorのgeneric catch非吸収を検証する。

`WorkflowPipelineRunner.run()`（`workflow_pipeline_runner.py:65-79`）・`AgentExecutor.execute()`（`agent_executor.py:53-94`）という、`PublishStepExecutor.execute()`よりさらに外側の2つのbroad `except Exception`についても、22.3.12節が`except SideEffectExecutionModeContractError: raise`carve-outを定める。test #8（full-chain contract error非吸収）・#9（malformed protected context）・#10（malformed/mismatched legacy context）がこれを検証する。malformed/mismatched test caseはいずれも2.1b節`validate_side_effect_execution_context()`が既に定義するfield-level検証（`_is_well_formed_*()`・closed set判定）からのみ導出し、新しいvalidation semanticsは追加していない。

| # | シナリオ | 検証項目 |
|---|---|---|
| 1（protected full-chain lossless propagation） | `RetryLineageProtectedExecutionContext`を`WorkflowTriggerAgent.act()`の`AgentContext.side_effect_execution_context`として供給し、`WorkflowPipelineRunner.run()`→`WorkflowRunner.run()`→`WorkflowContext`構築→`PublishStepExecutor.execute()`→`AiPublishService.run()`/`_process()`/`_post()`まで実行する（22.3.3節「呼び出し箇所Cへの第3の経路」の実chain） | `AiPublishService._post()`が受け取る`side_effect_execution_context`が、`WorkflowTriggerAgent`が最初に受け取った`RetryLineageProtectedExecutionContext`インスタンスと値として完全一致（`root_run_id`/`attempt_ordinal`/`member_run_id`/`side_effect_contract_version`すべて）すること。chain中のいずれの中間boundary（`WorkflowPipelineRunner`・`WorkflowRunner.run()`・`WorkflowContext`・`PublishStepExecutor.execute()`）でも値が欠落・上書き・再構築されないこと（各boundaryでの直接assertion） |
| 2（legacy full-chain lossless propagation、`WorkflowTriggerAgent`経由） | `LegacyDirectExecutionContext`（`legacy_execution_origin=WORKFLOW_TRIGGER_AGENT`、`scripts/run_workflow_trigger_agent.py`起動、22.3.11節）を同一chain（`WorkflowTriggerAgent`→`WorkflowPipelineRunner`→`WorkflowRunner`→`WorkflowContext`→`PublishStepExecutor`）で実行する（28.-20節#1・#2が検証する`run_ai_workflow.py`直接起動＝`AI_WORKFLOW_DIRECT`経路とは異なる起動originであることに注意） | `AiPublishService._post()`が受け取る`side_effect_execution_context`の`legacy_execution_origin`が`WORKFLOW_TRIGGER_AGENT`のまま保持され、`AI_WORKFLOW_DIRECT`と混同されないこと（28.-20節#4と同型の非混同確認を、本chain自身で直接実施） |
| 3（WorkflowRunner-chain unknown context fail-closed） | `AgentContext.side_effect_execution_context`に、2.1節のdiscriminated union（`RetryLineageProtectedExecutionContext`/`LegacyDirectExecutionContext`）いずれでもないオブジェクトを人為的に設定した状態で、`WorkflowRunner.run()`→`WorkflowContext`→`PublishStepExecutor.execute()`chainを実行する | `PublishStepExecutor.execute()`内の`validate_side_effect_execution_context()`呼び出し（既存`try`ブロックの外側、22.3.12節）が`SideEffectExecutionModeContractError(UNKNOWN_EXECUTION_MODE)`を送出し、`AiPublishService.run()`/`_process()`/`_post()`のいずれも呼ばれないこと（**external I/O = 0**）。この例外が`WorkflowStepResult(success=False, ...)`へ変換されず、`WorkflowRunner.run()`まで独立した例外として伝播すること（spy/mockのcall回数＋例外型の直接確認） |
| 4（WorkflowRunner-chain missing context + correlation metadataからの再構築禁止） | `AgentContext.side_effect_execution_context`を`None`にした状態で、`WorkflowEngineEvent.metadata`または`AgentTask.params`に、正規の`RetryLineageProtectedExecutionContext`と同型に見えるfakeな値（`root_run_id`等のキーを含む辞書）を混入させた上で、`WorkflowRunner.run()`→`WorkflowContext`→`PublishStepExecutor.execute()`chainを実行する | `PublishStepExecutor.execute()`に到達する`context.side_effect_execution_context`が`None`のまま（fake値から再構築されない）であり、`validate_side_effect_execution_context()`が`MISSING_EXECUTION_MODE`を送出して、`AiPublishService`のいずれのメソッドも呼ばれる前にfail-closedすること（**external I/O = 0**。28.-12節#4はこれを`AgentContext`構築時点のみで確認していたが、本テストはWorkflowRunner-chainの終端＝`PublishStepExecutor.execute()`到達時点まで再構築が発生しないことを直接確認する） |
| 5（protected→legacy silent downgrade = 0、chainレベル） | test #1（protected）のchainを実行し、`WorkflowRunner.run()`・`WorkflowContext`・`PublishStepExecutor.execute()`の各boundaryで、値が`LegacyDirectExecutionContext`型へ変化する経路がないことをtype-levelで確認する | chain中のいずれのboundaryでも`side_effect_execution_context`の型が`RetryLineageProtectedExecutionContext`のまま維持されること（isinstance確認、型変化=0） |
| 6（legacy→protected silent upgrade = 0、chainレベル） | test #2（legacy）のchainを実行し、同様に型が`RetryLineageProtectedExecutionContext`へ変化する経路がないことを確認する | chain中のいずれのboundaryでも`side_effect_execution_context`の型が`LegacyDirectExecutionContext`のまま維持されること（isinstance確認、型変化=0） |
| 7（contract errorのgeneric catch非吸収） | `PublishStepExecutor.execute()`のsource（`src/ai/workflow_step_executor.py`）をAST監査し、かつtest #3のシナリオを実行して例外伝播を直接観測する | `validate_side_effect_execution_context()`の呼び出しが、`self._service.run(...)`を含む`try`ブロックの外側（手前）に位置すること（AST上のnode位置で直接確認）。実行時、test #3で送出される`SideEffectExecutionModeContractError`が`except Exception as e:`節に一切捕捉されず（当該except節のカバレッジ計測で通過回数0を確認）、`WorkflowStepResult(success=False, error_message=str(e))`という形へ変換されずに`WorkflowRunner.run()`まで伝播すること |
| 8（contract errorがStage-1 callerまで生存すること） | test #3のunknown context fail-closedシナリオを、`PublishStepExecutor.execute()`単体ではなく、`AgentManager.run()`→`AgentExecutor.execute()`→`WorkflowTriggerAgent.act()`→`WorkflowPipelineRunner.run()`→`WorkflowRunner.run()`→`PublishStepExecutor.execute()`という実chain全体を通して実行する。`src/pipeline/workflow_pipeline_runner.py::WorkflowPipelineRunner.run()`・`src/ai/agent_executor.py::AgentExecutor.execute()`のsourceもAST監査する | 両ファイルの`except Exception`節の直前に`except SideEffectExecutionModeContractError: raise`節が存在すること（AST上のnode順序で直接確認、22.3.12節の契約）。実行時、`SideEffectExecutionModeContractError`が`WorkflowPipelineRunner.run()`の`except Exception`（71行目）・`AgentExecutor.execute()`の`except Exception`（80行目）のいずれにも捕捉されず（カバレッジ計測で両except節の通過回数0を確認）、`PipelineResult(success=False, ...)`にも`AgentResult(success=False, ...)`にも変換されないこと。`AgentManager.run()`の呼び出し元（Stage-1 caller）まで未変換の例外として到達すること。この間`AiPublishService`の3メソッド（`run`/`_process`/`_post`）はいずれも呼び出し回数0であること（**external I/O = 0**） |
| 9（malformed protected context、full-chain fail-closed） | `RetryLineageProtectedExecutionContext`の`root_run_id`／`attempt_ordinal`／`member_run_id`／`side_effect_contract_version`のいずれか1フィールドのみを、2.1b節`validate_side_effect_execution_context()`が定義する不正値（例：空文字列の`root_run_id`、負値の`attempt_ordinal`、空文字列の`member_run_id`、closed set外の`side_effect_contract_version`）へ差し替えた状態で、test #1と同一のfull chain（`WorkflowTriggerAgent`→`WorkflowPipelineRunner`→`WorkflowRunner`→`WorkflowContext`→`PublishStepExecutor`）を4パターン（フィールドごと）実行する | 各パターンで、対応する理由コード（`root_run_id`不正＝`MISSING_LINEAGE_CONTEXT`、`attempt_ordinal`/`member_run_id`不正＝`CONTEXT_MISMATCH`、`side_effect_contract_version`不正＝`CONTRACT_VERSION_MISMATCH`。2.1b節の既存判定をそのまま流用、新しいvalidation semanticsは追加しない）を伴う`SideEffectExecutionModeContractError`が`PublishStepExecutor.execute()`で送出され、test #8と同様にStage-1 callerまで未変換のまま伝播すること。`AiPublishService`への到達＝0（**external I/O = 0**） |
| 10（malformed/mismatched legacy context、full-chain fail-closed） | `LegacyDirectExecutionContext`の`legacy_entrypoint`をclosed set外の値へ、または`legacy_execution_origin`をclosed set外の値へ差し替えた状態（2パターン、2.1b節の既存判定基準をそのまま流用）で、test #2と同一のfull chainを実行する | 各パターンで、対応する理由コード（`legacy_entrypoint`不正＝`UNKNOWN_LEGACY_ENTRYPOINT`、`legacy_execution_origin`不正＝`UNKNOWN_LEGACY_EXECUTION_ORIGIN`）を伴う`SideEffectExecutionModeContractError`が送出され、Stage-1 callerまで未変換のまま伝播すること。`AiPublishService`への到達＝0（**external I/O = 0**） |
| 11（contradictory legacy pair、individually-valid値同士の到達不可能な組み合わせ、full-chain fail-closed） | `LegacyDirectExecutionContext`の`legacy_entrypoint`・`legacy_execution_origin`をいずれも個別にはclosed set内の値としつつ、両者の組み合わせが2.1c節`ALLOWED_LEGACY_ENTRYPOINT_ORIGINS`に存在しない値へ差し替えた状態（例：`legacy_entrypoint=RUN_AI_PUBLISH`・`legacy_execution_origin=NEWS_AGENT`——AgentManagerを経由しない単一originのentrypointにAgentManager fan-out originが対応付けられている、群1・群2間の交差）で、test #2と同一のfull chainを実行する | `CONTRADICTORY_LEGACY_PAIR`を伴う`SideEffectExecutionModeContractError`が`PublishStepExecutor.execute()`で送出され、Stage-1 callerまで未変換のまま伝播すること。`AiPublishService`への到達＝0（**external I/O = 0**）。偽のcorrelation metadataで組み合わせを"修復"できないこと（28.-12節#4と同型、correlation metadataからの再構築禁止の直接確認） |
| 12（general ambient environment stateからの再構築禁止、correlation metadata/task params以外） | `AgentContext.side_effect_execution_context`を`None`にした状態で、(a) `_parse_execution_context_from_env()`が読む14.3節の明示的検証対象env var以外の任意のprocess環境変数（例：正規のenvelope変数名と類似した非公式env var、`os.environ`上のその他の値）、(b) `WorkflowRunner`/`PublishStepExecutor`インスタンスが保持するmodule-levelのglobal cache・class変数・thread-localな状態、のいずれかに正規contextと同型に見えるfake値を混入させた上で、test #4と同一のchain（`WorkflowRunner.run()`→`WorkflowContext`→`PublishStepExecutor.execute()`）を実行する | `PublishStepExecutor.execute()`に到達する`context.side_effect_execution_context`が`None`のまま（(a)(b)いずれのambient stateからも再構築されない）であり、`validate_side_effect_execution_context()`が`MISSING_EXECUTION_MODE`を送出して`AiPublishService`のいずれのメソッドも呼ばれる前にfail-closedすること（**external I/O = 0**。test #4がcorrelation metadata・`AgentTask.params`という2種類のambient stateを検証するのに対し、本項はそれ以外の一般的なambient state（明示的に検証されないenv var・module-level/thread-local状態）からの再構築禁止を直接検証する） |

### 28.-37 Authoritative Completion Boundary Identity Consistency 必須テスト（7件）

2.2a節が定める2段階の責務分離のうち、(1) `RetryExecutor`のconsistency validation boundaryと(2) `WorkflowEngineExecutor`のmember completion boundaryを直接検証する。28.-36節のtest群（downstream propagation boundary）とは異なる境界を対象とする。

| # | シナリオ | 検証項目 |
|---|---|---|
| 1（valid — RetryExecutor validation PASS） | `RetryLineageRecord`（`root_run_id=R`・`side_effect_contract_version=V`）・claim（`attempt_no=A`）から`RetryExecutor`が`RetryLineageProtectedProvenance(R, A, V)`を構築し、同一の`lineage`/`claim`参照に対しconsistency validationを行う | validationがPASSし、`RetryLineageProtectedProvenance(R, A, V)`がvalidated pre-contextとして`WorkflowEngineManager.run()`へ渡されること |
| 2（root mismatch、RetryExecutor） | `RetryLineageProtectedProvenance`構築直後に`root_run_id`を、それ自体は`_is_well_formed_root_run_id()`を満たす値としつつ、`RetryExecutor`が実際に処理している`lineage.root_run_id`とは異なる値へ差し替えた状態でconsistency validationを行う | `MISSING_LINEAGE_CONTEXT`を伴う`SideEffectExecutionModeContractError`が`RetryExecutor`内でfail-closedすること。`WorkflowEngineManager.run()`呼び出し回数=0、external I/O = 0 |
| 3（attempt mismatch、RetryExecutor） | `attempt_ordinal`を、`_is_well_formed_attempt_ordinal()`を満たす値としつつ、`claim.attempt_no`とは異なる値へ差し替えた状態でconsistency validationを行う | `CONTEXT_MISMATCH`を伴う`SideEffectExecutionModeContractError`が`RetryExecutor`内でfail-closedすること。`WorkflowEngineManager.run()`呼び出し回数=0、external I/O = 0 |
| 4（contract version mismatch、RetryExecutor） | `side_effect_contract_version`を、`_is_well_formed_contract_version()`を満たす値としつつ、`lineage.side_effect_contract_version`とは異なる値へ差し替えた状態でconsistency validationを行う | `CONTRACT_VERSION_MISMATCH`を伴う`SideEffectExecutionModeContractError`が`RetryExecutor`内でfail-closedすること。`WorkflowEngineManager.run()`呼び出し回数=0、external I/O = 0 |
| 5（malformed field、consistency照合到達前のfail-closed） | `RetryLineageProtectedProvenance`のいずれかのfieldをmalformed（空文字列の`root_run_id`等）にした状態で`RetryExecutor`のconsistency validationを行う | 2.1b節の既存well-formedness検証が先に発火し、2.2a節(1)のconsistency照合（本節）には到達しないこと——検証順序が明示的であること（malformed検証が先、consistency照合は個別に有効な値同士にのみ適用される） |
| 6（member completion — pass-through整合性） | test #1のvalidated pre-context（`R`・`A`・`V`）を`WorkflowEngineExecutor`が受け取り、自身が発行した`run_id=M`を補完してprotected factoryを呼ぶ | 完成した`RetryLineageProtectedExecutionContext`が`root_run_id=R`・`attempt_ordinal=A`・`side_effect_contract_version=V`（validated pre-contextの3値から一切変更されていない）・`member_run_id=M`（`WorkflowEngineExecutor`自身が発行した実際のrun_idと一致）を持つこと。`WorkflowEngineManager.run()`のシグネチャに`lineage`/`claim`引数が存在せず、`WorkflowEngineExecutor`が`lineage`/`claim`を参照する経路自体が存在しないこと（static監査） |
| 7（member_run_id caller override禁止） | `WorkflowEngineExecutor`のprotected factory呼び出し箇所をsource監査する | protected factory（`build_protected_execution_context()`）の呼び出しが`WorkflowEngineExecutor`自身の`run_id`のみを渡しており、呼び出し元・caller供給の値を`member_run_id`として受け付ける引数・分岐が存在しないこと（static監査） |

これら7件は`RetryExecutor`/`WorkflowEngineExecutor`という2つの完成境界の単体テストであり、28.-36節のfull-chain propagation testとは独立に実行される。

### 28.-38 呼び出し箇所A/B/C Contract-Error Non-Absorption 必須テスト（3件）

22.3.13節が定める、`WorkflowTriggerAgent`経由chain以外の3箇所（呼び出し箇所A・B・Cそれぞれの production chain）でのcontract-error non-absorptionを直接検証する。

| # | シナリオ | 検証項目 |
|---|---|---|
| 1（呼び出し箇所C、PublishTriggerAgent chain） | `AiPublishService.run()`が`SideEffectExecutionModeContractError`を送出する状況（missing/unknown context）を作り、`PublishPipelineRunner.run()`を実行する | 例外が`PipelineResult(success=False, ...)`へ変換されず、`PublishPipelineRunner.run()`の呼び出し元まで未変換のまま伝播すること（該当except節のカバレッジ計測で通過回数0を確認）。`AiPublishService`の`_post()`以降の呼び出し（実I/O）は0であること |
| 2（呼び出し箇所A、OutputManager） | `WordPressOutput.save()`が`SideEffectExecutionModeContractError`を送出する状況を作り、`OutputManager.save_all()`を実行する | 例外が`SaveResult(success=False, ...)`へ変換されず、他の出力先への継続（loop continuation）も行われずに`save_all()`の呼び出し元まで未変換のまま伝播すること。他の登録済み出力先（`MarkdownOutput`等）の`save()`が呼ばれる前に伝播すること（呼び出し順序に依存しないよう、`WordPressOutput`が最初に処理される構成・後に処理される構成の両方で確認） |
| 3（呼び出し箇所B、main.py記事ループ） | `_apply_featured_media_step()`内部（`runtime.apply()`経由）で`SideEffectExecutionModeContractError`を送出する状況を作り、main.pyの記事ループを実行する | 例外が22.3.2節の共通try/exceptで`FeaturedMediaPropagatedFailure`へ変換されず（`except SideEffectExecutionModeContractError: raise`が`except Exception`より先に評価されること）、main.py側の`except FeaturedMediaPropagatedFailure`にも捕捉されず、`_handle_featured_media_failure()`も呼ばれず、`continue`で次の記事へ進むこともなく、記事ループの外まで未変換のまま伝播すること。`markdown_output.save()`・WordPress POST・media upload（真の外部I/O）のいずれも呼び出し回数0であること |

これら3件は22.3.13節が定める3箇所の単体テストであり、28.-36・28.-37節のtestとは独立に実行される。

### 28.-39 NEWS Subprocess境界 Contract-Error Exit Protocol 必須テスト（5件）

14.6節が定める、`main.py`（child）と`NewsPipelineRunner.run()`（parent）の実subprocess境界を直接検証する。28.-38節の3件（main.py記事ループ・OutputManager・PublishPipelineRunner）とは異なる境界を対象とする。

| # | シナリオ | 検証項目 |
|---|---|---|
| 1（child exit protocol） | `main.py`の`main()`内部で`SideEffectExecutionModeContractError`を送出する状況（テスト用に注入）を作り、`main.py`をプロセスとして実行する | プロセスのexit codeが`SIDE_EFFECT_CONTRACT_VIOLATION_EXIT_CODE`（=3）であること。stdout/stderrに例外のtraceback・reason_code値・メッセージ本文が含まれないこと（secret-safe、2.5節） |
| 2（parent detection、full subprocess chain） | test #1と同一の注入を行った`main.py`を、`NewsPipelineRunner.run()`から実際に`subprocess.run()`経由で起動する（mock化せず実プロセス境界を経由させる） | `NewsPipelineRunner.run()`が`SideEffectExecutionModeContractError(SUBPROCESS_CONTRACT_VIOLATION)`を送出し、`PipelineResult(success=False, ...)`が返らないこと。`_news_outcome_token()`・`_EXIT_CODE_TOKENS`分岐に到達しないこと（呼び出し回数0） |
| 3（upper chain non-normalization） | test #2のシナリオを、`AgentManager.run()`→`AgentExecutor.execute()`→`NewsAgent.act()`→`NewsPipelineRunner.run()`という実chain全体を通して実行する | 例外が`NewsAgent.act()`（try/exceptなし）・`AgentExecutor.execute()`の`except SideEffectExecutionModeContractError: raise`carve-out（22.3節）を通過し、`AgentResult(success=False, ...)`へ変換されずにStage-1 callerまで未変換のまま伝播すること。この間、WordPress POST・media upload（真の外部I/O）はいずれも呼び出し回数0であること（**external I/O = 0**） |
| 4（既存0/1/20/21回帰確認） | `main.py`が通常の0・1・20・21いずれかのexit codeで終了する既存シナリオ（`SideEffectExecutionModeContractError`を送出しない）を、test #2と同一のsubprocess境界で実行する | `_news_outcome_token()`・`_EXIT_CODE_TOKENS`分岐が従来どおり発火し、`PipelineResult`が返ること（本節の変更が既存contract 0/1/20/21の挙動を破壊しないことの回帰確認） |
| 5（exit code collision = 0） | `production_canonical_run_outcome_contract_foundation.md`5節が定めるmain.py Outcome Contract（0/1/2/20/21）と、`SIDE_EFFECT_CONTRACT_VIOLATION_EXIT_CODE`の値をsource上で比較する | 値が衝突しないこと（3 ∉ {0, 1, 2, 20, 21}）。`SIDE_EFFECT_CONTRACT_VIOLATION_EXIT_CODE`が`side_effect_execution_mode.py`（2.5節）の単一定数として定義され、`main.py`・`NewsPipelineRunner`双方がこれをimportし、値をハードコード重複していないこと（static監査） |

これら5件は14.6節が定めるNEWS subprocess境界の単体テストであり、28.-38節のtestとは独立に実行される。

### 28.-40 §27.3・27.5・27.6 get() Lock-Free Semantics, Cross-Store Read Scope & Read-Then-Mutate Ordering 必須テスト（6件）

27章が定める`get()`のidentity-lock-free契約・cross-store read scope（複数store横断のcomposite atomicityを主張しない）・27.6節のread-then-mutate順序契約を直接検証する。28.-25節（Invariant #16・#33）・28.-6節（Invariant #30、`_value_or_recover()`段2はlockなし）とは異なる境界（公開`get()`自体・複数store読み取りのscope・27.6節の順序契約）を対象とする。

| # | シナリオ | 検証項目 |
|---|---|---|
| 1 | 対象identityの`WordPressDraftStateStoreLock`／`MediaUploadSafetyCoordinatorLock`を意図的にstaleのまま残存させた状態で、同一identityへ`get()`を呼ぶ | `get()`がブロックされず、staleロックの解放を待たずに成功して、各store個別の直近complete file内容から構成された結果を返すこと（27.5節、stale lockの影響範囲からの除外） |
| 2 | test #1と同一のstale lock状態で、同一identityへ`create_attempted()`/`transition_to_confirmed()`（`MediaUploadSafetyCoordinator`側は`record_not_applicable()`/`record_prepared()`/`record_attempted()`/`record_confirmed()`）を呼ぶ | durable mutationメソッドはstale lockの取得待ちでfail-closedに（ブロックまたはManual Stale Lock Recovery Procedure、27.5節）扱われ、staleロックを迂回して書き込みが成立しないこと |
| 3 | 単一store（`WordPressDraftStateStore`の1ファイル、または`MediaUploadSafetyCoordinator`が読む個々のstore1ファイル）について、`os.replace(tmp_path, final_path)`によるatomic書き込みが進行中の区間と重なるタイミングでget/readする（fault injection） | 当該1ファイルについては常に「書き込み前の完全な旧内容」または「書き込み後の完全な新内容」のいずれかであり、torn/partial file stateに由来する部分的な内容・パース失敗を一切観測しないこと（27.3節、per-storeのatomicity保証。複数store間の同時性は主張しない） |
| 4 | `MediaUploadSafetyCoordinator.get()`が観測する複数storeの内容を、time-skewed observationとして以下の具体的な組み合わせごとに人為的に構成し、`get()`（内部的には`classify()`が9.9.7節Tableへ照合する経路）を呼ぶ：(a) marker非存在・`attempt_context_store`＝`IO_ARMED`（旧）・`article_media_upload_state`＝`CONFIRMED_SUCCESS`（新、concurrent `record_confirmed()`実行中に典型的なskew）、(b) marker非存在・`attempt_context_store`＝`PREPARED`・`article_media_upload_state`＝`ATTEMPTED`（`record_attempted()`の内部書き込み順序中に典型的な、safeなpre-I/O skew）、(c) marker非存在・`attempt_context_store`＝`IO_ARMED`・`article_media_upload_state`＝`ATTEMPTED`（I/O開始可否が確認できないambiguousな中間状態）、(d) marker非存在・`attempt_context_store`非存在・`article_media_upload_state`＝`ATTEMPTED`（context無しでupload_stateのみ存在する、lifecycle違反の矛盾combination） | 各combinationについて、Cross-Store Combination Table（9.9.7節）が定める**当該組み合わせのexactな`SideEffectSafetyCategory`**と一致すること——(a)は`CONFIRMED_SUCCESS`、(b)は`SAFE_TO_CONTINUE`、(c)は`IN_PROGRESS_OR_UNKNOWN`、(d)は`CONTRACT_VIOLATION`（いずれも9.9.7節の該当行と一致）。cross-store skewそのものを`SAFE_TO_CONTINUE`／`IN_PROGRESS_OR_UNKNOWN`／`CONTRACT_VIOLATION`という3分類へ一律強制するのではなく、Tableが定める個別の組み合わせごとの結果（`CONFIRMED_SUCCESS`・`NOT_APPLICABLE`を含む）と厳密一致することを検証する。skewの存在自体を禁止・異常視せず、その観測結果の安全な解釈はTableのexact combination semanticsのみが担うこと。undefined/矛盾する組み合わせを安全側と推定して正常値へ丸めないこと |
| 5 | 破損・不正な形式のレコード（schema違反、identity/member_run_id不一致等）が既にdurable storeへ書き込まれている状態で`get()`を呼ぶ | `get()`が破損内容を正常値として返さず、既存の契約どおり`WordPressDraftStateCorruptedError`／`MediaUploadSafetyContractViolationError`を送出すること（malformed/torn stateのsilent successへの変換=0） |
| 6 | `get()`（lock-free）で得たsnapshotを用いて、同一Coordinator/Store内のdurable mutation（`transition_to_confirmed()`等）を実行する経路をコード監査で確認する | 27.6節が定める順序（lock取得→relevant state再read→precondition再validate→mutation）が守られており、`get()`のsnapshot自体をmutationのcompare-and-swap前提条件として直接使い回す経路が存在しないこと。この契約はside-effect storage domain（`WordPressDraftStateStore`／`MediaUploadSafetyCoordinator`）内のmutationにのみ適用され、`RetryLineageManager`のreconciliation／`open_next_attempt()`（別domain、`RetryExecutionLock`／`RetryLineageStoreLock`）には適用しないこと（27.6節「適用範囲の限定」）を監査で確認する |

これら6件は27章のconcurrency/locking契約に対する単体テストであり、28.-25・28.-6・9.9.4.4節の既存テストとは独立に実行される。

## 29. Architecture Classification Register

**分類凡例**：Normative Contract＝current architectureの一部として確定している事項／Release 6.32 Out of Scope／Implementation Detail（Architecture変更なし、通常のエンジニアリング判断・コードレビューで解決する事項）。

### 29.1 Architecture Classification（38項目）

1. **Normative Contract** — Reporting/CLIからの`RetryLineageDisposition`参照は、22.4節（Retry Queue Update整合）が定める`RetryQueueUpdateDecider`経由の統合設計に一本化する。独立したCLI/reporting消費者・独立再計算ロジックは、本architectureでは想定しない。
2. **Normative Contract** — 呼び出し箇所Cのwrite-ahead挿入位置：`AiPublishService._post()`統合を正式採用する（15.6節）。2章のExplicit Side-Effect Execution Mode契約により、Retry Lineage context外の経路（22.2節の複数entry point）は明示的にOut of Scope・legacy behaviorと位置づける。
3. **Implementation Detail** — Contract Version Snapshotと`max_attempts`スナップショットの実装整合。通常のコーディング判断で解決可能。
4. **Normative Contract** — 優先順位1（24章）は、既存6.31 UNKNOWN→FAILED経路（`disposition_from_categories()`）と矛盾しない設計としなければならない（28.-8節#7・#8が直接検証する）。
5. **Release 6.32 Out of Scope** — 13章（§11は11.1〜11.2のみ）の帰結の運用インパクト見積もり（運用インパクト評価は対象外）。
6. **Normative Contract** — media upload経路のmember_run_id整合性：`MediaUploadAttemptContextStore`（9.9.2節）が担保する。バイパスコードに対する残存リスクは22.2節「No Bypass Proof」の運用規律（shared coordinator bypass禁止）に委ねる。
7. **Normative Contract** — `SILENT_NO_ACTION`のguard位置：`SILENT_NO_ACTION`を含むstep-level `StepOutcomeCategory`をoperation-specific non-reach proofとして使う設計を採用していないため（12.2節）、当該論点自体が発生しない。`classify()`は`StepOutcomeCategory`を一切参照しない（28.-17節#2）。
8. **Implementation Detail** — `operation_instance_key`（article_identity）の具体的な導出方法と既存ロジックとの整合。
9. **Normative Contract** — 14章の環境変数方式と既存main.py CLI引数・6.30契約の関係：既存CLI（`--max-articles`のみ）・既存env var（`ANTHROPIC_API_KEY`・`DEFAULT_MEDIA_ID`）のいずれとも衝突しない。14.2節の環境変数案（`RETRY_LINEAGE_ROOT_RUN_ID`等）を採用する。
10. **Implementation Detail** — `list_operations_for_lineage()`の具体的な出力形状（17.4節）。
11. **Release 6.32 Out of Scope** — `_STEP_TO_PROTECTED_OPERATIONS`を静的なまま維持し、動的なGate結果を12章側で吸収する設計。
12. **Normative Contract** — `MEDIA_UPLOAD`の安全性検証水準の非対称性：`MediaUploadAttemptContextStore`（9.9.4節）が担保する。
13. **Normative Contract** — `create_not_applicable()`自体のACK失敗時の扱い：9.9.3・12.4節が定める（正常確定として扱わずfail-closedへ倒れる）。
14. **Release 6.32 Out of Scope** — `WORDPRESS_DRAFT_CREATION`にはGate相当の概念がない、という前提の頑健性（前提は6.32 architectureにおいて成立している）。
15. **Release 6.32 Out of Scope** — write-ahead契約を経由しない外部呼び出しの検出限界（§22.2「構造的限界の正直な記載」参照、4章Non-Goals）。
16. **Implementation Detail** — 12.3節「Decision Tableの6原則」の文言表現の精度は、architecture変更を伴わないimplementation detailとする。
17. **Implementation Detail** — `MediaUploadSafetyCoordinatorLock`のstale lock復旧手順（27.5節が定める）の運用者向けドキュメント配置先は、architecture契約の一部としない。
18. **Release 6.32 Out of Scope** — 「No Bypass Proof」のコードレビュー運用依存部分に対する技術的強制（lintルール等）の導入は、本Releaseのscope外とする。
19. **Release 6.32 Out of Scope** — 27.5節のLock Orderingは「6.31の2ロックとはネストしない」という前提の上に成立する。この前提自体のさらなる頑健性検証は本Releaseのscope外とする。
20. **Implementation Detail** — `record_attempted()`の2-store順次書き込み（`MediaUploadAttemptContextStore`・`article_media_upload_state`）の非トランザクション性に対する運用上の可観測性（ログ設計）は、architecture契約の一部としない。
21. **Release 6.32 Out of Scope** — `MediaUploadAttemptContextStore`自体の永続化ライフサイクル（レコードが削除されず残り続ける）が、長期運用でのディスク使用量にどの程度影響するか（#23と関連）。
22. **Implementation Detail** — 9.9.4節の「context only→SAFE_TO_CONTINUE」という判断は、9.9.2節のLifecycle Ordering Contractへの準拠に依存する。28.-1節等のテストでカバーされる。
23. **Release 6.32 Out of Scope** — `MediaUploadAttemptContextStore`のレコードは、CONFIRMED_SUCCESS確定後も削除されず残り続ける（26章Non-Recycle）。長期的なディスク使用量への影響（#21と同一論点）。
24. **Normative Contract** — 9.9.6節のACK Determinism原則と`WordPressDraftStateStore`側（9.3節）の関係：9章・27.1〜27.4節でCommit-Aware Lock Helperを共有し、identity-scoped lock化も適用する。
25. **Normative Contract** — Safe Continuation（9.9.5節）が、6.31の「同一attempt_ordinalの再claim」以外の経路でも正しく機能すること：28.-7b節「同一プロセス内二重呼び出し」の専用テストが、restart経由（28.-1節#3）と同一の安全側動作を検証する。
26. **Release 6.32 Out of Scope** — 27.5節のidentity-scoped lock化により、1 attemptあたりのロックファイル生成・削除数が記事数×operation_kind数に比例して増加する（27.5節末尾参照）。
27. **Normative Contract** — `_run_with_commit_aware_lock()`の`assert commit_state["committed"]`の実装方式：`assert`は採用せず、常に評価される`if`文＋明示的な例外送出（`MediaUploadSafetyImplementationContractError`）とする（24章）。
28. **Implementation Detail** — `commit_state["value"]`が未設定（None）のままpost-commit body例外によりhelperのexcept節経由で返される場合の呼び出し元側のNone値ハンドリングは、architecture契約の一部としない（現行の唯一の呼び出し元`ArticleFeaturedMediaRuntime.apply()`はこの値を使用しない）。
29. **Implementation Detail** — 9.9.4.4節のArchitecture Invariant表に対する機械的検証手段の選定は、architecture契約の一部としない。
30. **Implementation Detail** — `CleanupDiagnostic`の`operation_kind`/`effect_site`フィールドは、identity自体が取得できないより根本的な失敗ではNoneになりうる。このドキュメント化はarchitecture契約の一部としない。
31. **Release 6.32 Out of Scope** — `_value_or_recover()`が追加のdurable read（`get()`/`_read_all()`）を行うことで、post-commit失敗という稀なケースに限りわずかな追加I/Oが発生する。3段fallback化は性能懸念そのものを解消するものではない（計測課題）。
32. **Normative Contract** — `_value_or_recover()`が`self._read_all()`を直接呼ぶ設計の前提：Retry Lineage context下では「いかなるidentityへのconcurrent writerも存在しない」というより強い保証が成立する（27.1節、`RetryExecutionLock`）。2.3節（LEGACY_DIRECT）（Retry Lineage context外）はこの保証の対象外であり、#2のOut-of-Scope境界として扱う。
33. **Implementation Detail** — `_minimal_safety_record()`が返す合成recordは、durable storeの実内容（正確な`updated_at`等）と厳密には一致しない可能性がある。現行の唯一の呼び出し元（15.4節）はこの差異に依存しない設計であり、この近似の扱いはarchitecture契約の一部としない。
34. **Release 6.32 Out of Scope** — 3段fallback（`_value_or_recover()`）の各段の発火頻度（特に段3到達ケース）に対する実運用の観測性強化（ログ・診断情報`cleanup_diagnostics`からの把握）は、本Releaseのscope外とする。
35. **Normative Contract** — `src/wordpress_draft_state/`パッケージ一式・`retry_lineage`直接変更の配置：22.1b節（`wordpress_draft_state`新設）・22.1c節（`retry_lineage`直接変更ファイル一覧）が定める。
36. **Normative Contract** — §12.1〜12.4（`WORDPRESS_DRAFT_CREATION`の判定・6原則の決定表本文）：既存の確定済み契約（2.2節Fail-Closed Matrix・9.3節read時検証・9.9.7節Cross-Store Combination Table・10.1〜10.3節Operation Applicability・11.1〜11.2節`SideEffectSafetyCategory`・13章・`StepOutcomeCategory`実装）から一意に導出する形で12.1〜12.4節が定める（reachability rules・6原則・`NOT_APPLICABLE`marker未使用を含む、12章）。
37. **Normative Contract** — `ArticleFeaturedMediaRuntime.apply()`のpre-upload fallback（画像生成失敗でuploadへ未到達）に対するoperation-specific durable evidence：`MediaUploadSafetyCoordinator`の4番目の公開メソッド`record_prepared()`（既存の`PREPARED`state／`SAFE_TO_CONTINUE`classificationをそのまま再利用し、新しいstateは追加しない）が表現する。詳細契約は9.9.4.7節を参照。
38. **Normative Contract** — write-ahead呼び出しを`media_uploader.upload()`直前へ正確に配置する実装方法（`ArticleFeaturedMediaOrchestrator`／`ArticleFeaturedMediaCompositionRoot`の「Consumer-less Foundation」契約との両立）：6.32 integration層でwrite-ahead-aware decoratorを構築し独自に注入する（`ArticleFeaturedMediaOrchestrator`/`ArticleFeaturedMediaCompositionRoot`へ6.32・Retry Lineage固有の依存を直接導入しない）。不採用の代替案は30章#40〜#42を参照。詳細契約は15.4節を参照。

### 29.2 分類内訳

| 分類 | 該当項目 |
|---|---|
| Normative Contract | 1, 2, 4, 6, 7, 9, 12, 13, 24, 25, 27, 32, 35, 36, 37, 38 |
| Release 6.32 Out of Scope | 5, 11, 14, 15, 18, 19, 21, 23, 26, 31, 34 |
| Implementation Detail | 3, 8, 10, 16, 17, 20, 22, 28, 29, 30, 33 |

---

## 30. Rejected Alternatives

以下は、本architectureが採用しない設計形態と、その理由である。

35. `_value_or_recover()`の段2（durable read）が失敗した場合、単純に例外を再送出する（段3を設けない）：棄却。この設計はdurable read自体の失敗可能性を無視している。追加I/Oに依存しない段3を設けることで、真に「失敗しえない」最終防衛線を確保する。
36. `_minimal_safety_record()`にも`_read_all()`相当の検証（identity整合性チェック等）を持たせる：棄却。検証ロジックを持たせるということは、その検証自体が失敗しうる（＝新たな失敗モードを持ち込む）ことを意味し、「原則として失敗しえない最終防衛線」という段3の存在意義に反する。段3は意図的に、検証を一切行わない単純な値の詰め替えに限定する。
37. `lineage_context is not None`ならprotected、`None`ならlegacy、という値の有無からの暗黙推測をmode判定の唯一の根拠として採用し続ける：棄却。`lineage_context`の供給し忘れ・供給失敗といった実装バグが、構造的に「legacyとして正常動作した」と誤認され、6.32のfail-closed保証を静かに迂回しうる（silent downgrade）ため、composition/entry boundaryからのexplicit close-set mode供給契約（2章）へ置き換える。
38. main.py起動時、`RETRY_LINEAGE_EXECUTION_MODE`未設定を`LEGACY_DIRECT`という**値の推測**として扱う（envelope全体が不在かどうかを区別せず、mode未設定というシグナル単独から暗黙にlegacyへ倒す）：棄却。これは「値の欠落からの推測」の一種であり、2.1節の禁止事項と矛盾する（28.-10節#7の要求と非整合）。14.3節が定める契約はこれとは異なる——execution-envelope全体（mode discriminator・protected 4変数・legacy 2変数のすべて）が完全に不在の場合に限り、main.py自身がtrusted composition rootとして`RUN_MAIN_DIRECT`/`MAIN_DIRECT`のprovenanceを明示的に自己発生させる（値の推測ではなく、trusted boundary自身による明示的宣言、2.1a節）。mode discriminatorが未設定のままprotected/legacy envelope変数のいずれか1つでも存在する場合（orphan field）は、この自己発生経路を取らずfail-closedする。main.py以外の呼び出し箇所A/B/C自体（2.2・2.4節）では、mode discriminatorの欠落は常にfail-closedであり、この自己発生規則の対象外である。
39. 21章のcrash/fault-point scenarioスキーマ（Crash/Fault Point・Durable Evidence Before Crash等7項目）を、write-ahead契約を経由しない外部呼び出しの検出限界（特定のクラッシュ時点・durable state遷移を持たない構造的limitation）にも適用する：棄却。7項目スキーマへ強制すると内容が空洞化する。この論点は§22.2「構造的限界の正直な記載」が自己完結した記述を持つため、そちらへ一本化する（21章冒頭・22.2節・29章#15）。
40. **（29章#38関連）** 選択肢(b)：`ArticleFeaturedMediaCompositionRoot`へ6.32/write-ahead専用の新しい構築経路（uploaderのdecorator/wrapperを注入可能なclassmethod等）を追加する：棄却。既存パターン（`from_env()`）に沿う利点はあるが、「Consumer-less Foundation」を謳うfile自体へ6.32固有の構築経路を追加することになり、9.9.4.7・15.4節が採用したOption (a)（6.32 integration層のみでdecoratorを構築・注入し、Foundation自体は無変更のまま維持する）よりFoundationへの影響が大きい。
41. **（29章#38関連）** 選択肢(c)：境界の精度を妥協し`orchestrator.apply()`全体をwrite-ahead境界とする：棄却。15.4節が定めるpre-upload fallback境界のとおり、画像生成（`generate()`）失敗だけで`media_uploader.upload()`に一度も到達しないCONTINUE fallbackの経路でも、durable stateが`IO_ARMED`（未到達の外部I/Oを「開始可能」と記録した状態）のまま残り、`resolve_final_disposition()`が誤って`HUMAN_REVIEW_REQUIRED`を発火させる。日常的な想定内の回復可能失敗（レート制限・コンテンツポリシー等）のたびにfalse HRRが発生するため不採用。
42. **（29章#38関連）** 6.32専用CompositionRoot（`ArticleFeaturedMediaCompositionRoot`と並立する、6.32 execution contextを知る別のCompositionRootクラス）を新設し、6.32 integration層がそちらを経由してOrchestratorを構築する：棄却。Consumer-less Foundationの原則自体（Foundationは特定Releaseの実行文脈を知らない）とは矛盾しないように見えるが、Orchestratorの構築経路が2系統（既存`from_env()`系と6.32専用系）に分岐し、Release追加のたびに専用CompositionRootが増殖する構造的リスクを持つ。既存の`GeneratedImageUploadCapability`Protocol（Dependency Inversion拡張点）へのdecorator注入という汎用DI seamのみを許可し、6.32専用経路の新設は禁止する。

---

## 31. Implementation Requirements

本章は、本書§§0〜30が定める要件のうち、複数章にまたがる整合性を要する事項をMUST文で列挙する静的な参照表である。個別章がすでに定める契約の逐語的な再掲・test-mapping detailは含まない。

1. `_value_or_recover()`は3段fallback構成（構築済み値→lockなしdurable read→追加I/Oなしの`_minimal_safety_record()`）でなければならず、各段の失敗は次段への単純なフォールスルーでなければならない。
2. Trusted Composition Boundary契約（`RetryLineageProtectedExecutionContext`/`LegacyDirectExecutionContext`のdiscriminated union・fail-closedマトリクス、2章）は、これを参照する全章で一貫していなければならない。
3. `RetryQueueUpdateDecider`はHRR専用の新しいoutcome/status値を持ってはならない——`HUMAN_REVIEW_REQUIRED`は既存の`RetryQueueUpdateOutcome.FAIL`/`RetryQueueStatus.FAILED`へ合流し、既存6.31 semantics（`SUCCEEDED`/`FAILED`/`NOT_ACTIONED`の写像）を変更してはならない。
4. 呼び出し箇所B（MEDIA_UPLOAD）は、呼び出し箇所A/Cと同一の`validate_side_effect_execution_context()`契約を使用しなければならない。
5. `RetryLineageProtectedProvenance`/`side_effect_execution_provenance`（member確定前）と`RetryLineageProtectedExecutionContext`/`side_effect_execution_context`（member確定後）の型stageは、全出現箇所で一貫していなければならない。
6. `RetryQueueUpdateDecider.decide()`の入力はdiscriminated union（`LineageAuthoritativeDispositionInput`/`LegacyQueueDecisionInput`）でなければならず、Optional値の欠落からlegacyを推測してはならない。
7. HRR lineageの再enqueue防止は、Layer 1（primary contract）・Layer 2・Layer 3（defense-in-depth）の3層構成でなければならない（22.1e節）。
8. `SideEffectSafetyCategory`は5値（`NOT_APPLICABLE`/`SAFE_TO_CONTINUE`/`CONFIRMED_SUCCESS`/`IN_PROGRESS_OR_UNKNOWN`/`CONTRACT_VIOLATION`）でなければならず、record非存在時にstep-level `StepOutcomeCategory`を参照してはならない。
9. `decide_all()`はtyped `RetryQueueDecisionRequest`の列を受け取らなければならず、`RetryManager.decide_retry_queue_updates()`・`RetryRuntimeOrchestrator.run_once()`双方のproduction経路は同一builderを経由しなければならない。
10. `classify_contract_version_evidence()`は、全てのcontract-version判定箇所（18.2・22.4・22.4a節）で唯一のpredicateでなければならない。
11. `WordPressDraftStateStore.create_not_applicable()`/`WordPressDraftStateManager.record_not_applicable()`は6.32 APIに存在してはならない。
12. `RetryRuntimeOrchestrator.run_once()`は`RetryManager.decide_retry_queue_updates(execution_results)`のみを呼ばなければならない（22.3.6・22.4a節）。
13. `RetryLineageManager.find_by_member_run_id() -> str | None`（単一値）＋`peek()`のみを前提とし、`find_all_by_member_run_id()`のような実在しないAPIへ依存してはならない（22.4a節）。
14. `LegacyEntrypoint`（Stage 1）／`LegacyExecutionOrigin`（Stage 2）の2段階provenanceは、`AgentManager.from_config()`が構築する4 Agent型・現行8 explicit legacy entrypointsに1:1対応しなければならず、同一`AgentManager.run()`呼び出し内で`LegacyDirectExecutionContext`インスタンスを使い回してはならない。
15. 呼び出し箇所Cへの第3の経路（`WorkflowTriggerAgent`→`WorkflowPipelineRunner`→`WorkflowRunner`→`PublishStepExecutor`→`AiPublishService`）は、22.1f節の配線契約に従わなければならない。
16. `MediaUploadSafetyRecord`は、`NotApplicableMediaUploadSafetyRecord`/`PreparedMediaUploadSafetyRecord`/`IoArmedMediaUploadSafetyRecord`/`ConfirmedMediaUploadSafetyRecord`からなるtyped closed unionでなければならず、acknowledged commitの別semantic kindへの再分類は、exact typing＋固定`RecoveryPolicy`＋`_value_or_recover()`全段のruntime `isinstance`検証によって防がれなければならない。
17. 4公開メソッド（`record_not_applicable`/`record_prepared`/`record_attempted`/`record_confirmed`）は、単一のcanonical Architecture Invariant表・単一のCommit-Aware Lock Helperに統合されていなければならない。
18. `_value_or_recover()`は単一の`RecoveryPolicy`引数（`expected_type`・`build_minimal()`・`validate()`を一体化）のみを受け取らなければならず、expected concrete typeとminimal constructionを独立引数として自由に組み合わせるAPIを持ってはならない。
19. `_value_or_recover()`の全3段は、`policy.validate()`によるruntime `isinstance`検証を経なければならない。
20. `_extract_confirmed_media_id()`へ渡す引数は、`runtime.apply(article)`の戻り値ではなく、明示的にunwrapした`runtime_result.article`（`ArticleData`）でなければならない。
21. `record_confirmed()`の唯一のownerは`main.py::_apply_featured_media_step()`でなければならず、decoratorが`record_confirmed()`を呼んではならない。
22. `record_confirmed()`は`runtime_result.status is ArticleFeaturedMediaRuntimeStatus.APPLIED`の場合にのみ呼ばれなければならず、`featured_media_id`の値のみを証拠として扱ってはならない。
23. `build_featured_media_side_effect_binding()`という単一factoryではなく、`build_protected_featured_media_side_effect_binding()`/`build_legacy_featured_media_side_effect_binding()`の2 builderへ分割されていなければならない。legacy builderのシグネチャに`media_upload_coordinator`/`adapters`が現れてはならない。
24. Protected startupでは、`isinstance(context, ...)`分岐が起動時construction経路自体を単一に決定しなければならない（`ArticleFeaturedMediaRuntime.from_env()`を呼ぶかどうかの二択は採用しない）。Protected分岐でlegacy credential/config/runtimeを構築してはならない。
25. `SideEffectExecutionModeContractError`は、`PublishStepExecutor.execute()`・`WorkflowPipelineRunner.run()`・`AgentExecutor.execute()`のいずれのbroad `except Exception`によっても`re-raise`されなければならず、Stage-1 callerまで未変換のまま到達しなければならない。
26. Bare `python main.py`直接起動は、外部operator/wrapperによる事前の環境変数serializationを前提条件とせず、main.py自身がtrusted direct composition rootとして`RUN_MAIN_DIRECT`/`MAIN_DIRECT`のprovenanceを自己発生させなければならない。ただしexecution-envelope関連変数（mode discriminator・protected 4変数・legacy 2変数）のいずれか1つでも存在する場合（mode discriminator欠落時のorphan fieldを含む）は、self-origination経路を取らずfail-closedしなければならない。

## 32. Completed History

本章は、本書に対する外部review（Codex Final Architecture Re-Review）とそのremediationの完了記録を保持する歴史的記録である。

Codex Final Architecture Re-Review（番号体系確定前のFinal Re-Review相当分を含む）を通じて指摘されたBlocking/Major findingsは、いずれもremediationにより解消済みである。いずれのroundも実装・commit・push・production外部I/Oは行っていない。

§30が現在保持するrejected alternative（35番以降）より前に存在したとされる旧#1〜34、および§29の現行番号体系（#1〜#38）確定前に別採番されていた旧#11・旧#12は、本書のいかなるauthoritative sourceからも内容を復元できない。推測による復元・再作成は行わず、「かつて存在した」という事実のみをここに記録する。

§30がかつて保持していた3項目（旧citationの再解釈禁止・§30番号が#35から始まることの推測的復元禁止・test項目数を旧時点の件数に合わせる数合わせの禁止）は、いずれもrejected architecture alternativeではなくdocument編集方針に関する記録だったため、§30から除去し、事実としてここにのみ記録する。
