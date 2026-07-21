# Article Featured Media Composition Root Foundation

## 0. Header／Status

```text
Release: v6.18.0
名称: Article Featured Media Composition Root Foundation
分類: Architecture Release
作成日: 2026-07-21

Status:
  Repository Survey:         Completed（本文書作成前に実施。3章参照）
  Architecture Design:       Completed（本文書）
  Architecture Review 1:     Changes Required（Blocking 0・Major 2・Minor 3・Suggestion 4）
  Architecture Amendment 1:  Completed（本文書。F-1〜F-9すべてに対応）
  Architecture Review 2:     Approved with Suggestions（Blocking 0・Major 0・Minor 2・
                             Suggestion 4。Minor 2件はいずれも実装前修正必須ではなく、
                             Production Implementation／Documentation Integration時の
                             軽微な追記で解消可能と判定）
  Architecture Amendment 2:  Not Required
  Production Implementation: Completed
  New E2E:                   Completed（146 Assertion、146/146 PASS、0 FAIL）
  Code Review:               Approved with Suggestions（Blocking 0・Major 0・
                             Minor 3・Suggestion 2。Code Review 2：Not Required）
  Formal Regression:         Completed／Passed（正式Inventory21ファイル、
                             総Assertion 2790、2790/2790 PASS、FAIL 0、
                             warning 0、skip 0、外部接続0）
  Documentation Integration: Completed（本文書）
  Release Review:            Approved with Suggestions（Blocking 0・Major 0・
                             Minor 1・Suggestion 1。Release Review 2：Not Required）

Release: Completed
```

本文書はDocumentation Integrationの成果物であり、Release Review（Approved with
Suggestions、Blocking 0・Major 0・Minor 1・Suggestion 1）を経て**Release：Completed**
となった。

Production Implementation〜Documentation Integrationの各工程で作成・変更した
ファイルは、本設計書自身を含め次の5件である（Production Implementation報告の
「4件」という記載は、報告主体である本設計書自身を勘定に含めていなかった誤りであり、
本工程で訂正した。tracked／untrackedの区別と、工程上の作成・編集ファイル数は
別概念である点に注意）。

```text
新規  src/article_featured_media_composition/__init__.py
新規  src/article_featured_media_composition/article_featured_media_composition_root.py
新規  tests/test_e2e_v6_18_0_article_featured_media_composition_root_foundation.py
追加  src/openai_image_generation/openai_image_generator.py
        → output_mime_type property の追加のみ（既存9行の純追加diff。
          既存attribute・method・signature・挙動は無変更）
更新  docs/design/article_featured_media_composition_root_foundation.md
        → 本文書自身。Architecture Amendment 1・Production Implementation・
          Documentation Integrationの各工程で更新（本Status欄・本節を含む）
```

`main.py`・Runtime packageはいずれも無変更である。ROADMAP.md・architecture.md・
CHANGELOG.mdは本Documentation Integration工程で更新した（本工程の対象文書）。

Architecture Review 1・Architecture Review 2・Code Review・Formal Regressionの
指摘と結果、および各工程の実施記録の詳細は29章 Review Historyを参照。

---

## 1. Background

Release 6.9.0〜6.17.0で、AI画像生成からWordPress featured media設定に至る一連の
Foundationが整備された。

```text
v6.9  WordPress Media Upload Foundation              src/wordpress_media/
v6.10 AI Image Generation Contract Foundation        src/ai_image_generation/
v6.11 OpenAI Image Generation Adapter Foundation     src/openai_image_generation/
v6.12 Generated Image WP Media Upload Wiring         src/generated_image_wordpress_media/
v6.13 Article Featured Media Binding Foundation      src/article_featured_media/
v6.14 Article Featured Media Orchestration           src/article_featured_media_orchestration/
v6.15 Image Generation Configuration Gate            src/image_generation_config/
v6.16 Generated Image Filename Policy Foundation     src/generated_image_filename_policy/
v6.17 Article Image Prompt Construction Foundation   src/article_image_prompt_construction/
```

これら9パッケージは**いずれもConsumer-less**である。Repository全体を`*.py`で走査した結果、
これらのsymbolは自パッケージ内と`tests/`以外に一切出現せず、`main.py`・`scripts/`・
`src/pipeline/`・`src/ai/`・`src/outputs/`・`src/retry_*`からの参照はゼロである。

一方で、これらを実際に組み立てる層がRepository内に存在しない。`ArticleFeaturedMediaOrchestrator`
は`image_generator`・`media_uploader`をConstructor Injectionで受け取る設計だが
（`src/article_featured_media_orchestration/article_featured_media_orchestrator.py:44-56`）、
その2つを実際に構築して注入する箇所がどこにもない。

`docs/ROADMAP.md:919-920`は次を明記している。

```text
ただしPublish Composition Root Foundationは依然未着手であり、
本Wiring（Article Featured Media Runtime Wiring）へ直行できる状態には至っていない
```

本Releaseは、この不足を埋める。ただしPublish全体ではなく、**Article Featured Media画像処理に
限定した**Composition Rootを新設する（Repository Survey確定事項1）。

---

## 2. Problem Statement

現状、`ArticleFeaturedMediaOrchestrator`を実際に利用しようとする呼び出し側は、次のすべてを
自前で実施しなければならない。

```text
P-1  ImageGenerationConfig.from_env() を呼び、enabled を評価する
P-2  OpenAIImageGenerator.from_env() を呼ぶ（OPENAI_API_KEY 未設定なら ValueError）
P-3  WordPressMediaUploader.from_env() を呼ぶ（WP_* 3点未設定なら ValueError）
P-4  GeneratedImageWordPressMediaUploader で v6.9 → v6.12 を接続する
P-5  ArticleFeaturedMediaOrchestrator を構築する
P-6  記事ごとに再構築せず単一インスタンスを保持する
P-7  無効時の安全な状態を自前で表現する
P-8  filename 構築に必要な MIME 情報を自前で調達する（後述 P-9）
```

現状これらは**すべて`main.py:main()`という単体テスト不能な1関数へ流れ込む**構造になっている。
`main.py`は`sys.exit()`・`argparse`・`print`を多用し、`main()`を単体で呼び出して検証することが
できない（`main.py:181-441`）。

さらに、実装済みContract間に構造的な欠落が1件ある。

```text
P-9  MIME情報の供給経路が存在しない

  ArticleFeaturedMediaOrchestrator.apply(article, prompt, filename)
      → filename を「事前入力」として要求する
        （article_featured_media_orchestrator.py:58, 67-70）

  generate_image_filename(title, mime_type)
      → mime_type を要求する
        （generated_image_filename_policy.py:43, 53-63）

  GeneratedImage.mime_type
      → generate() の「戻り値」にしか存在しない
        （generated_image.py, ai_image_generator.py:19）

  OpenAIImageGenerator
      → output_format を private 属性 `_output_format` として保持するのみ。
        MIME／output format を公開する Public API を持たない
        （openai_image_generator.py:233）
```

すなわち、**filenameはgenerateより前に必要だが、mime_typeはgenerateの後にしか手に入らない**。
呼び出し側は`"image/png"`をハードコードするか、v6.11の内部定数`_MIME_TYPE_BY_OUTPUT_FORMAT`
（`openai_image_generator.py:33-37`）を再実装するしかない。これはSingle Source of Truthの
喪失であり、実装済みContractだけでは合成が成立しないことを意味する。

---

## 3. Repository Survey Findings

本設計はすべて実ファイルの実読に基づく。推測は含まない。

### 3.1 調査対象パッケージの正確なパスとPublic API

タスク指示に記載された`src/generated_image_wordpress_media_upload/`は**存在しない**。
実際のパスは`src/generated_image_wordpress_media/`である。以下は実在を確認した一覧。

| パッケージ | `__all__` | factory | immutable |
|---|---|---|---|
| `src/ai_image_generation/` | `GeneratedImage`, `AIImageGenerator` | なし | `GeneratedImage`＝`@dataclass(frozen=True)` |
| `src/openai_image_generation/` | `OpenAIImageGenerator`, `OpenAIImageGenerationError`, `OpenAIImageGenerationErrorReason` | `from_env()` | なし（通常class） |
| `src/wordpress_media/` | `MediaUploadResult`, `WordPressMediaUploadError`, `WordPressMediaUploader` | `from_env()` | `MediaUploadResult`＝`frozen=True` |
| `src/generated_image_wordpress_media/` | `GeneratedImageWordPressMediaUploader` | なし | なし |
| `src/article_featured_media/` | `bind_featured_media` | — （module-level関数） | — |
| `src/article_featured_media_orchestration/` | `ArticleFeaturedMediaOrchestrator`, `GeneratedImageUploadCapability` | なし | なし |
| `src/image_generation_config/` | `ImageGenerationConfig` | `from_env()` | `@dataclass(frozen=True)` |
| `src/generated_image_filename_policy/` | `generate_image_filename` | — （module-level関数） | — |
| `src/article_image_prompt_construction/` | `construct_article_image_prompt` | — （module-level関数） | — |
| `src/retry_composition/` | `RetryCompositionRoot` | `from_env(base_dir=None)` | なし（通常class） |

### 3.2 environment参照タイミング

| symbol | 参照する環境変数 | 参照タイミング |
|---|---|---|
| `ImageGenerationConfig.from_env()` | `AI_IMAGE_GENERATION_ENABLED` | 呼び出し時のみ |
| `OpenAIImageGenerator.from_env()` | `OPENAI_API_KEY`, `OPENAI_IMAGE_TIMEOUT_SECONDS` | 呼び出し時のみ |
| `WordPressMediaUploader.from_env()` | `WP_SITE_URL`, `WP_USERNAME`, `WP_APP_PASSWORD` | 呼び出し時のみ |

**import時にenvironmentを読むmoduleは1つもない**（全moduleの実読で確認）。
`os.getenv`／`os.environ.get`はいずれも関数本体の内側にのみ出現する。

### 3.3 外部接続タイミング（重要）

`OpenAIImageGenerator`は`import openai`を**module levelで行わない**。
`openai`のimportは`_get_client()`（`openai_image_generator.py:259`）と
`generate()`（同283-284行）の内側でのみ行われる。
`from_env()`と`__init__`はいずれも`openai`をimportせず、`self._client = client`（既定`None`）を
保持するのみである（同236行）。

`WordPressMediaUploader`は`requests`をmodule levelでimportするが（`wordpress_media_uploader.py:9`）、
`from_env()`／`__init__`は文字列の検証と正規化のみを行い、HTTP通信を一切行わない。

**したがって、本Composition Rootの`from_env()`は、Gate ONかつ全credentialが揃っていても、
外部API接続を一切発生させない。** これは本Releaseのtestabilityの根拠であり、
17章Security Contract・20章Test Strategyの前提となる。

### 3.4 error contract（既存）

| symbol | 例外 | 条件 |
|---|---|---|
| `ImageGenerationConfig.from_env()` | **なし** | 不正値・未設定はすべて`False`（Fail Closed、`image_generation_config.py:11, 38-39`） |
| `OpenAIImageGenerator.from_env()` | `ValueError` | `OPENAI_API_KEY`が未設定または空白（242行）／`OPENAI_IMAGE_TIMEOUT_SECONDS`が非整数または非正（250-252行） |
| `OpenAIImageGenerator.__init__` | `ValueError` | `api_key`／`model`／`size`／`quality`／`output_format`／`timeout_seconds`の型・値不正（208-228行） |
| `WordPressMediaUploader.from_env()` | `ValueError` | `WP_SITE_URL`／`WP_USERNAME`／`WP_APP_PASSWORD`のいずれかが未設定または空白（126-129行） |
| `WordPressMediaUploader.__init__` | `ValueError` | 各値が非str／空白／正規化後空（105-112行） |
| `GeneratedImageWordPressMediaUploader.__init__` | **なし** | 検証を`upload()`まで遅延（Duck Typing、`generated_image_wordpress_media_uploader.py:18-25`） |
| `ArticleFeaturedMediaOrchestrator.__init__` | `TypeError` | `image_generator`／`media_uploader`のcapability不足（49-53行、固定messageがPublic Contract） |

**secret露出の確認**：`OpenAIImageGenerator.from_env()`の例外message
`"missing or blank environment variable: OPENAI_API_KEY"`、
`WordPressMediaUploader.from_env()`の
`"missing or blank environment variables: WP_SITE_URL, ..."`は、いずれも**環境変数名のみ**を
含み、値を含まない。したがってこれらの例外はそのまま伝播させてもsecretを露出しない。

### 3.5 Protocolとconcrete adapterの境界

```text
AIImageGenerator (Protocol, v6.10)
    generate(prompt: str) -> GeneratedImage
    @runtime_checkable を付与しない（v6.10設計判断）
    ↑ OpenAIImageGenerator は明示継承せず、構造的部分型のみで満たす
      （openai_image_generator.py:191-195 に明記）

GeneratedImageUploadCapability (Protocol, v6.14)
    upload(image: GeneratedImage, filename: str) -> MediaUploadResult
    ★ 消費者側パッケージ（article_featured_media_orchestration）で宣言されている。
      wordpress_media / generated_image_wordpress_media 側では宣言されていない。
      「消費者が必要なContractを自分で宣言する」というDependency Inversionのprecedent
      （article_featured_media_orchestrator.py:21-30 に明記）
```

### 3.6 `RetryCompositionRoot`の責務・構築順序・公開属性

`src/retry_composition/retry_composition_root.py`。本Releaseの主要precedentである。

```text
責務（同ファイル14-16行に明記）:
    「本クラスの責務は『組み立てて属性として公開すること』のみに限定する。
      enqueue_pending_failures() / execute_dispatchable_retries() 等の呼び出し、
      実行順序の決定、ループ・デーモン化はいずれも行わない（Non-Goal）」

    「新規business logicは追加しない。各値の組み立ては既存の
      from_env()/from_config() への委譲のみで完結する」

構造:
    通常class（frozen dataclassではない）
    __init__ は全構成要素を受け取るPublic constructor（テストからの注入が可能）
    from_env(base_dir: Path | None = None) が唯一のenvironment入口
    公開属性は10件（monitor / queue / history / guard / trigger / policy /
                    manager / retry_source / retry_decision / scheduler）
    具象classを直接importする（NullRetryQueueManager等も含む）
    Protocolを新設しない

構築順序（from_env内、105-131行）:
    monitor → queue → history → guard → trigger
    → retry_source → retry_decision → scheduler
    → policy → agent_config → workflow_engine_manager → manager
```

**重要な観察**：`RetryCompositionRoot`は**Protocolを一切新設せず、具象classを直接importする**。
Composition Rootは「具象を知る層」であるというprecedentが確立している。

### 3.7 利用可能性precedent

| precedent | 場所 | 形 |
|---|---|---|
| `WordPressOutput.is_available()` | `src/outputs/wordpress_output.py:33-35` | 3 credentialすべてがtruthyなら`True`。例外を投げない |
| `AgentConfig.is_ready()` | `src/ai/agent_config.py:43-45` | `enabled`をそのまま返す |
| `AiPublishConfig.is_ready()` | `src/ai/ai_publish_config.py:49-64` | `enabled` **かつ** WordPress credential 3点。4条件AND |
| `OutputManager.save_all()` | `src/outputs/manager.py:32-34` | `is_available()`が`False`の出力先を`continue`でskip |

### 3.8 Null Object precedent

Repository内にNull Object patternが広く存在する。

```text
NullRetryQueueManager       ← RetryQueueManager.from_config()    が gate OFF 時に返す
NullWorkflowMonitorManager  ← WorkflowMonitorManager.from_config() 同上
NullRetryManager            ← RetryManager.from_config()          同上
NullAnalyticsManager        ← AnalyticsManager.from_env()          同上
NullAiPublishService        ← AiPublishService.from_env()          同上
NullExecutionHistoryManager / NullRetrySchedulerSource / NullWorkflowEngineManager
```

いずれも**「methodを持つmanager／service」**をNull化したものであり、
Null実装は「副作用なくDISABLED相当の結果を返す」（`null_retry_queue_manager.py:4-5`）。

### 3.9 v6.14 orchestratorのconstructorと`apply()` contract

```text
__init__(image_generator: AIImageGenerator,
         media_uploader: GeneratedImageUploadCapability) -> None
    callable(getattr(x, "generate"/"upload", None)) による capability 検証（fail-fast）
    不足時 TypeError（固定message）
    request単位のstateをインスタンス属性へ保存しない（stateless）

apply(article: ArticleData, prompt: str, filename: str) -> ArticleData
    article/prompt/filename を検証（ValueError、固定message）
    generate → upload → bind を固定順序で1回ずつ呼ぶ
    下位例外は無変換伝播（try/except を一切持たない）

Failure Boundary（設計書18章）:
    「画像生成に失敗しても記事投稿を続けるか」等9項目はいずれも Out of Scope。
    Runtime側の継続・中止判断は将来の Runtime Wiring の責務
```

設計書408-409行は次を明記している。

```text
image_generatorとmedia_uploaderという2つのdependencyは、将来のCaller
（Runtime WiringのComposition Root）が一度だけ構築し、複数記事に対して
（再利用することを想定している）
```

**本Releaseはこの「一度だけ構築するCaller」を実装するものである。**

### 3.10 filename policyが必要とする入力／`GeneratedImage`のMIME情報／OpenAI adapterのoutput format

```text
generate_image_filename(title: str, mime_type: str) -> str
    mime_type は次4種のみ許可（generated_image_filename_policy.py:56-61）:
        image/png → png, image/jpeg → jpg, image/webp → webp, image/gif → gif
    それ以外は ValueError("mime_type is not a supported image type")

GeneratedImage(image_bytes: bytes, mime_type: str)
    mime_type は canonical MIME type。frozen dataclass。
    generate() の戻り値としてのみ得られる

OpenAIImageGenerator
    _DEFAULT_OUTPUT_FORMAT = "png"                       （21行）
    _ALLOWED_OUTPUT_FORMATS = {"png","jpeg","webp"}      （31行）
    _MIME_TYPE_BY_OUTPUT_FORMAT = {                       （33-37行）
        "png": "image/png", "jpeg": "image/jpeg", "webp": "image/webp"}
    self._output_format = output_format                   （233行、private）
    _build_generated_image() は
        mime_type = _MIME_TYPE_BY_OUTPUT_FORMAT[output_format]   （187行）
        を用いて GeneratedImage を構築する
```

**決定的に重要な事実**：`generate()`が返す`GeneratedImage.mime_type`は、
`_MIME_TYPE_BY_OUTPUT_FORMAT[self._output_format]`という**決定論的写像で生成される**。
すなわち「予定MIME」と「実際MIME」は、v6.11 Adapterにおいて**同一の写像・同一のSSOTから
導出されており、構造的に一致することが保証されている**（15章で詳述）。

また、`_ALLOWED_OUTPUT_FORMATS`（png/jpeg/webp）から導かれるMIMEは、
v6.16 filename policyの許可4種の**部分集合**である。したがってv6.11の任意の設定に対し、
v6.16は必ずfilenameを生成できる（`gif`のみv6.16側に余剰）。

### 3.11 Runtime実行経路（差込点の再確認）

```text
[A] python main.py
[B] scripts/run_news_agent.py → NewsAgent → NewsPipelineRunner
        → subprocess.run(["python", "main.py", ...])   ★プロセス隔離
両者とも main.py:main() へ収束
```

`NewsPipelineRunner`は`subprocess`によるプロセス隔離であり
（`news_pipeline_runner.py:19-21`「main.py本体には一切手を加えない」）、
Pythonオブジェクトの注入経路を持たない。したがって**Agent層・Scheduler層・Retry Runtimeから
画像dependencyを注入する経路は構造的に存在せず**、将来のRuntime Wiringの接続点は
`main.py:main()`内部（dependency構築ブロック201-214行、記事ループ310-391行）に限定される。

本Releaseはこの接続を**行わない**（Runtime Zero Diff）。

---

## 4. Goals

```text
G-1  Release 6.9〜6.17の画像関連dependencyを、Runtimeから独立した単一境界で
     構築・接続できる設計を確立する
G-2  Composition Rootの責務を「configuration評価／credential解決／adapter構築／
     adapter間接続／orchestrator構築／利用可能状態の公開」の6点に限定する
G-3  MIME情報のSingle Source of Truthを確立し、P-9の欠落を解消する
G-4  Gate OFF を「設定エラー」ではなく「正常な無効状態」として定義する
G-5  Gate ON＋設定不備を可視化する（暗黙のsoft skip化を行わない）
G-6  Consumer-less・Runtime Zero Diffを維持する
G-7  外部API実接続ゼロで全Contractを検証可能にする
G-8  後続Runtime Wiringのblast radiusを最小化する
```

---

## 5. Non-Goals（Out of Scope）

```text
N-1   画像workflowの実行（apply() の呼び出し）
N-2   promptの実生成（construct_article_image_prompt の呼び出し）
N-3   filenameの実生成（generate_image_filename の呼び出し）
N-4   ArticleData から title／excerpt を抽出する処理
N-5   失敗時の継続／中止判断（Image Generation Fallback Policy）
N-6   記事publish順序の決定
N-7   Runtimeへの配線（main.py / image_resolver.py / OutputManager /
      Pipeline / Agent / Scheduler / Retry Runtime / CLI scripts）
N-8   retry
N-9   idempotency
N-10  cleanup（未使用WordPress Media削除）
N-11  rollback
N-12  外部API実接続（OpenAI／WordPress）
N-13  logging（本Releaseではlog出力を一切行わない。17章 S-4参照。
      Documentation Integration工程で「19章参照」という誤ったcross-referenceを
      訂正した。19章はBackward Compatibilityでありlogging記述はない。
      logging Contractは17章Security ContractのS-4が正式な参照先である）
N-14  Documentation Integration（ROADMAP／architecture.md／CHANGELOG）
N-15  dependency追加（requirements.txt無変更）
N-16  Publish全体のComposition Root化（Anthropic client／LogManager／
      AnalyticsManager／OutputManager／PublishingConfig／SnsConfig）
```

**N-16の根拠**：これらは既に`from_env()`を持ち正常動作しており、触れればblast radiusが
`main.py`全体へ拡大する。CLAUDE.mdの「小さく作成 → 動作確認 → 改善」方針にも反する。
Publish全体のComposition Root化は、本Releaseの成功後に別Releaseとして再検討する（26章）。

---

## 6. Existing Architecture

```text
                       ┌──────────────────────────────┐
                       │  main.py:main()               │
                       │  （de facto Composition Root）│
                       │  201-214行: dependency構築    │
                       │  297-300行: OutputManager構築 │
                       │  310-391行: 記事ループ         │
                       └──────────────────────────────┘
                                    │
                                    ▼
                       ArticleData → OutputManager.save_all()
                                       → WordPressOutput.save()
                                          payload["featured_media"]
                                            = article.featured_media_id （>0のときのみ）

  ┌─────────────────────────────────────────────────────────┐
  │  画像系9パッケージ（v6.9〜v6.17）                        │
  │  ★ 上記Runtimeからの参照ゼロ＝完全にConsumer-less        │
  │  ★ 相互に組み立てる層が存在しない                        │
  └─────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────┐
  │  RetryCompositionRoot（v5.1／v5.2）                      │
  │  ★ Retry系にのみ存在する正式なComposition Root           │
  │  ★ publish系・画像系には対応物が存在しない  ← 本Releaseが埋める │
  └─────────────────────────────────────────────────────────┘
```

---

## 7. Precedent Analysis

| # | precedent | 場所 | 本設計への反映 |
|---|---|---|---|
| PR-1 | `RetryCompositionRoot`の責務限定（「組み立てて属性として公開することのみ」） | `retry_composition_root.py:14-16` | 9章の責務定義をそのまま踏襲。実行・順序決定・ループを行わない |
| PR-2 | `RetryCompositionRoot`が具象classを直接importし、Protocolを新設しない | 同48-58行 | **本Releaseも新規Protocolを追加しない**（11.6節） |
| PR-3 | `RetryCompositionRoot`が公開Constructor＋`from_env()`の二本立て | 同70-144行 | 同構造を採用（11.3節）。テストからのfake注入を可能にする |
| PR-4 | `RetryCompositionRoot`が新規business logicを追加しない | 同31-32行 | 本Composition Rootも既存`from_env()`への委譲のみで完結させる |
| PR-5 | `WordPressOutput.is_available()`（例外を投げない可用性述語） | `wordpress_output.py:33-35` | `is_available()`の形と命名を踏襲（14章） |
| PR-6 | v6.15 Gate の Fail Closed（不正値・未設定はすべて`False`、例外なし） | `image_generation_config.py:11` | Gate評価は例外を発生させない（13章） |
| PR-7 | v6.14 の無変換伝播（`try`/`except`を持たない、wrapしない、fallbackしない） | v6.14設計書17章 | 構築時例外も無変換伝播とする（16章） |
| PR-8 | v6.14 の ValueError／TypeError 使い分け（isinstance不正＝ValueError、capability不足＝TypeError） | v6.14設計書17.1節 | `__post_init__`検証の例外型選択に適用（11.5節） |
| PR-9 | v6.14 の消費者側Protocol宣言（`GeneratedImageUploadCapability`） | `article_featured_media_orchestrator.py:21-30` | 15.5節で比較検討のうえ、本Releaseでは不採用（理由明記） |
| PR-10 | Null Object pattern（`NullRetryQueueManager`等8種） | 3.8節 | 12章で比較検討のうえ、**不採用**（理由明記） |
| PR-11 | `AiPublishConfig.is_ready()`＝gate＋credential 4条件AND、`AiPublishService.from_env()`がNull Objectを返す | `ai_publish_config.py:49-64`, `ai_publish_service.py:73-75` | 13.3節で比較検討のうえ、credential不足については**不採用**（理由明記） |
| PR-12 | `main.py`のANTHROPIC_API_KEY必須チェック（未設定なら即時停止） | `main.py:201-205` | Gate ON＋credential不足のFail Fast判断の根拠（13.3節） |
| PR-13 | 画像系Foundationのimmutable model採用（`GeneratedImage`／`MediaUploadResult`／`ImageGenerationConfig`がいずれも`frozen=True`） | 3.1節 | 本Composition Rootも`frozen=True`とする（11.2節） |
| PR-14 | E2Eテストのstandalone script形式＋AST依存Guard＋Runtime Zero Diff静的検証 | `tests/test_e2e_v6_17_0_*.py:656-679` | 20章のTest Strategyへ踏襲 |

---

## 8. Proposed Architecture — 配置・命名

### 8.1 package名

| 候補 | 評価 |
|---|---|
| **`src/article_featured_media_composition/`** | **採用**。`src/retry_composition/`＋`RetryCompositionRoot`という「`<domain>_composition`パッケージに`<Domain>CompositionRoot`を置く」precedentに完全一致。かつ`src/article_featured_media_orchestration/`（v6.14）と同じ`article_featured_media_`接頭辞を共有し、画像featured media領域に属することが名称から明らかになる |
| `src/article_featured_media_composition_root/` | 不採用。`retry_composition`はパッケージ名に`_root`を含まない。module名側に`_root`を付ける規則である |
| `src/publish_composition/` | 不採用。実際のscope（画像featured mediaのみ）より広く、`main.py`のpublish全体を担うという誤解を招く（Repository Survey確定事項1、N-16） |
| `src/image_composition/` | 不採用。`article_featured_media_*`という既存2パッケージの接頭辞から乖離し、v6.13／v6.14との系列関係が読み取れない |

### 8.2 module名・class名

```text
package : src/article_featured_media_composition/
module  : article_featured_media_composition_root.py
          （retry_composition/retry_composition_root.py と同型）
class   : ArticleFeaturedMediaCompositionRoot
          （RetryCompositionRoot と同型。ArticleFeaturedMediaOrchestrator（v6.14）・
            ArticleFeaturedMediaBinding（v6.13）と同じdomain接頭辞）
```

### 8.3 設計書ファイル名

```text
docs/design/article_featured_media_composition_root_foundation.md
（docs/design/retry_composition_root_foundation.md と同型。本ファイル）
```

---

## 9. Composition Rootの責務定義

**担当する（6点のみ）**

```text
R-1  configuration評価         ImageGenerationConfig.from_env() の呼び出しとenabled判定
R-2  credential／environment依存の解決  各既存 from_env() への委譲
R-3  adapter構築               OpenAIImageGenerator / WordPressMediaUploader の構築
R-4  adapter間の接続           GeneratedImageWordPressMediaUploader による v6.9→v6.12 接続
R-5  orchestrator構築          ArticleFeaturedMediaOrchestrator の単一インスタンス構築
R-6  利用可能状態の公開        is_available() / orchestrator / image_mime_type の公開
```

**担当しない**

5章 N-1〜N-16 のすべて。特に次を強調する。

```text
・apply() を呼ばない（実行しない）
・prompt を作らない（v6.17を呼ばない）
・filename を作らない（v6.16を呼ばない）
・ArticleData に触れない（import すらしない）
・例外を握りつぶして「画像なしで続行」を決めない（＝Fallback Policyを持たない）
・新規business logicを追加しない（PR-4）
```

**「構築失敗」と「実行失敗」を混同しない**という原則を明記する。

```text
構築失敗（本Releaseの責務範囲）
    Gate ON なのに OPENAI_API_KEY が無い、等。
    記事生成が1件も始まっていない時点で、外部副作用ゼロの状態で判明する。

実行失敗（本ReleaseのOut of Scope）
    generate() が RATE_LIMIT で失敗、upload() が HTTP 500、等。
    記事ごとに発生し、Fallback Policy（別Release）の対象である。
```

---

## 10. Dependency Graph

### 10.1 構築グラフ

```text
ArticleFeaturedMediaCompositionRoot.from_env()
│
├─[1] ImageGenerationConfig.from_env()
│        env: AI_IMAGE_GENERATION_ENABLED
│        例外: なし（Fail Closed）
│        → config.enabled: bool
│
├─[2] Gate判定
│        enabled == False  →  cls(orchestrator=None, image_mime_type=None) を返して終了
│                              ★ 以降のenvironmentを一切読まない
│                              ★ credentialを要求しない
│                              ★ adapterを一切構築しない
│        enabled == True   →  [3] へ
│
├─[3] OpenAIImageGenerator.from_env()
│        env: OPENAI_API_KEY, OPENAI_IMAGE_TIMEOUT_SECONDS
│        例外: ValueError（無変換伝播）
│        外部接続: なし（openai は import すらされない。3.3節）
│        → image_generator
│
├─[4] image_mime_type = image_generator.output_mime_type
│        ★ v6.11 へ追加する read-only property（15章）
│        例外: なし
│
├─[5] WordPressMediaUploader.from_env()
│        env: WP_SITE_URL, WP_USERNAME, WP_APP_PASSWORD
│        例外: ValueError（無変換伝播）
│        外部接続: なし（HTTP通信は upload() 内でのみ発生）
│        → wordpress_media_uploader
│
├─[6] GeneratedImageWordPressMediaUploader(wordpress_media_uploader)
│        例外: なし（Duck Typing、検証は upload() まで遅延）
│        → generated_image_upload_capability
│
├─[7] bind_featured_media  ← 構築不要
│        module-level 純粋関数であり、v6.14 orchestrator が内部で直接 import 済み
│        （article_featured_media_orchestrator.py:16）。
│        Composition Root は参照も注入もしない
│
├─[8] ArticleFeaturedMediaOrchestrator(
│         image_generator=image_generator,
│         media_uploader=generated_image_upload_capability)
│        例外: TypeError（capability不足。本経路では構造上到達不能＝防御的）
│        → orchestrator
│
└─[9] cls(orchestrator=orchestrator, image_mime_type=image_mime_type)
         __post_init__ による不変条件検証（11.5節）
```

### 10.2 構築順序の根拠

```text
[3] OpenAI を [5] WordPress より先に構築する理由:
    ・実行時のデータフロー順（generate → upload）と一致し、v6.14 が固定した
      呼び出し順序（generate → upload → bind）と読み手の期待が揃う
    ・[4] の image_mime_type が [3] に依存するため、[3] を先に置くと
      グラフが一直線になり、途中で戻る枝が生まれない
    ・両者とも外部I/Oを伴わない純粋な構築であるため、順序が可用性に影響しない
      （どちらを先にしても、Gate ON かつ設定完備なら必ず両方成功する）

[2] のGate判定を最優先に置く理由:
    ・Gate OFF 時に credential を要求しないことを構造的に保証するため
      （13.2節「Gate OFFはcredentialを要求しない」の実装上の担保）
```

### 10.3 パッケージ依存方向

```text
article_featured_media_composition
  ├→ image_generation_config              (v6.15)
  ├→ openai_image_generation              (v6.11)
  ├→ wordpress_media                      (v6.9)
  ├→ generated_image_wordpress_media      (v6.12)
  └→ article_featured_media_orchestration (v6.14)
         └→ ai_image_generation / article_featured_media / outputs / wordpress_media

逆方向の依存は一切作らない（既存9パッケージは本パッケージをimportしない）。
本パッケージがimportしないもの:
    outputs（ArticleData）／ai_image_generation／article_featured_media／
    generated_image_filename_policy（v6.16）／article_image_prompt_construction（v6.17）／
    main／image_resolver／pipeline／ai／scheduler／retry_*／logger／analytics
```

**v6.16／v6.17をimportしない根拠**（設計判断7への回答）：

両者はmodule-levelの純粋関数であり、環境変数・credential・構築対象状態を一切持たない。
「構築」すべきものが存在しないため、Composition Rootが保持する意味がない。
関数参照として公開属性に持たせる案も検討したが、次の理由で不採用とした。

```text
・公開属性を最小限に限定するという方針（11.4節）に反する
・configuration由来の情報を一切含まない値を Composition Root が中継することは、
  「configuration評価とdependency構築」という責務定義（9章 R-1〜R-6）から外れる
・Runtime Wiring 側が `from generated_image_filename_policy import generate_image_filename`
  と直接importすれば済み、間接参照は可読性を下げる
→ v6.16／v6.17 は Runtime 側に残す（＝Runtime Wiring が直接 import する）
```

対照的に`image_mime_type`は**構築されたgeneratorの設定に依存する値**であるため、
Composition Rootが公開する正当な理由がある（15章）。

---

## 11. Public API

### 11.1 全体像

```python
# src/article_featured_media_composition/__init__.py
from .article_featured_media_composition_root import ArticleFeaturedMediaCompositionRoot

__all__ = [
    "ArticleFeaturedMediaCompositionRoot",
]
```

```python
# src/article_featured_media_composition/article_featured_media_composition_root.py
from dataclasses import dataclass, field

@dataclass(frozen=True)
class ArticleFeaturedMediaCompositionRoot:

    orchestrator: "ArticleFeaturedMediaOrchestrator | None" = field(repr=False)
    image_mime_type: "str | None"

    def __post_init__(self) -> None: ...

    @classmethod
    def from_env(cls) -> "ArticleFeaturedMediaCompositionRoot": ...

    def is_available(self) -> bool: ...
```

**Amendment 1（F-1対応）**：`orchestrator` fieldへ`field(repr=False)`を付与する。
`field()`へ`default`／`default_factory`を指定しないため、`orchestrator`は
`repr=False`付与後も**必須引数のまま**であり（省略時は`TypeError`）、`image_mime_type`との
field順序（default値なしのfieldがdefault値ありのfieldへ後続してはならない、という
dataclassの制約）にも抵触しない。両fieldは引き続きPublic constructorの必須引数であり、
INV-1〜INV-3（11.5節）による検証も無変更である。根拠と代替案の比較は17章 S-2を参照。

### 11.2 immutableとするか → **する（`@dataclass(frozen=True)`）**

| 根拠 | 内容 |
|---|---|
| PR-13 | 画像系Foundationは`GeneratedImage`／`MediaUploadResult`／`ImageGenerationConfig`がいずれも`frozen=True`。本Releaseは画像系の系列に属する |
| 意味論 | 構築結果は構築後に変化しない。可変にする理由がない |
| 不変条件の保護 | `orchestrator`と`image_mime_type`のペア不変条件（11.5節）を、事後代入で破壊されないようにする |

`RetryCompositionRoot`が通常classである点との差異は意図的である。`RetryCompositionRoot`は
v5.1.0時点でfrozen dataclassのprecedentが画像系ほど確立していなかった段階の実装であり、
本Releaseはより新しい画像系precedent（v6.10／v6.15）を優先する。
`frozen=True`は`RetryCompositionRoot`の責務定義（PR-1）と矛盾しない。

なお、`frozen=True`が保証するのは**Composition Root自身の属性の再代入不可**であり、
`orchestrator`が指すオブジェクトの内部状態までは凍結しない。ただし
`ArticleFeaturedMediaOrchestrator`はstateless（v6.14設計、3.9節）であるため、実質的な
可変状態は存在しない。この限界を設計書に明記する。

### 11.3 constructorをPublicにするか → **する**

`frozen=True`のdataclassが自動生成する`__init__(orchestrator, image_mime_type)`を
Public APIとする。

```text
根拠:
  PR-3  RetryCompositionRoot は全構成要素を受け取るPublic constructor を持つ
  testability  environment に触れずに fake orchestrator を注入した
               is_available() / 不変条件のテストが可能になる
  Runtime Wiring  将来、環境変数以外の経路（設定ファイル等）から構築する
                  拡張余地を閉じない
```

### 11.4 公開属性 → **2件のみ**

| 属性 | 型 | 意味 |
|---|---|---|
| `orchestrator` | `ArticleFeaturedMediaOrchestrator \| None` | 構築済みorchestrator。Gate OFF時は`None` |
| `image_mime_type` | `str \| None` | 構築済みgeneratorが生成する予定のMIME type。Gate OFF時は`None` |

**公開しないもの（および理由）**

| 非公開とするもの | 理由 |
|---|---|
| `config` / `enabled` | `is_available()`と完全に冗長（14.2節で証明）。属性を増やすと2つの真実源が生まれる |
| `image_generator` | Runtime Wiringは`orchestrator.apply()`のみを使う。単独公開はorchestratorを迂回した直接呼び出しを誘発し、v6.14が固定した順序保証を無効化しうる |
| `wordpress_media_uploader` / `generated_image_upload_capability` | 同上。加えて生credentialを保持するオブジェクトの露出面を減らす（17章） |
| `api_key` / `site_url` / `username` / `app_password` | Security Contract（17章）。secretを属性として保持しない |
| `bind_featured_media` | v6.14が内部でimport済み。中継する意味がない（10.1節[7]） |
| `generate_image_filename` / `construct_article_image_prompt` | 10.3節の理由により Runtime 側に残す |

「公開属性は後続Runtime Wiringに必要な最小限へ限定する」という要求に対し、
Runtime Wiringが必要とするのは次の3つだけである。

```text
1. 画像処理を行ってよいか            → is_available()
2. 画像処理の実行手段                → orchestrator.apply(article, prompt, filename)
3. filename構築に必要なMIME情報      → image_mime_type
```

### 11.5 `__post_init__`の不変条件検証

```python
不変条件 INV-1:
    (orchestrator is None) == (image_mime_type is None)
    違反時: ValueError("orchestrator and image_mime_type must be both set or both None")

検証 INV-2（orchestrator が None でない場合）:
    callable(getattr(orchestrator, "apply", None)) であること
    違反時: TypeError("orchestrator must provide a callable apply method")

検証 INV-3（image_mime_type が None でない場合）:
    isinstance(image_mime_type, str) であること
    違反時: ValueError("image_mime_type must be a str")
    かつ image_mime_type.strip() が非空であること
    違反時: ValueError("image_mime_type must not be blank")
```

**例外型の使い分け根拠（PR-8）**：v6.14設計書17.1節が確立した規則
「型そのものが違う＝`ValueError`／必要なmethodを持たない＝`TypeError`」を機械的に適用した。
INV-1・INV-3は値・型の不正であるため`ValueError`、INV-2はcapability不正であるため`TypeError`。

**`isinstance(orchestrator, ArticleFeaturedMediaOrchestrator)`を用いない根拠**：
v6.14 orchestrator自身がdependencyに対してnominal型検証を行わずcapability検証（Duck Typing）を
採用している（`article_featured_media_orchestrator.py:49-53`、v6.12も同様）。
同precedentを踏襲することで、テストからのfake注入が可能になり、testabilityが確保される。

**固定messageをPublic Contract化する**：v6.14が7種の固定messageを完全一致でPublic Contract化した
precedent（設計書684行）に倣い、上記4種の固定messageもPublic Contractとする。

### 11.6 Protocolを追加する必要があるか → **追加しない**

| 案 | 評価 |
|---|---|
| **新規Protocolを追加しない（採用）** | PR-2：`RetryCompositionRoot`はProtocolを一切新設せず具象classを直接importする。Composition Rootは本質的に「具象を知る層」であり、自身が構築する対象を抽象化しても抽象化の利得が生じない（構築する具象を選ぶことこそがComposition Rootの仕事である） |
| generator の MIME capability Protocol を新設 | 不採用。現時点でProviderは`OpenAIImageGenerator` 1件のみであり、複数実装という実需が存在しない。speculative generalityにあたる。将来Providerが2件目に達した時点で`ai_image_generation`へ追加する（26章 Deferred Item DI-2） |
| `AIImageGenerator` Protocol を拡張して MIME を含める | 不採用。**破壊的変更**にあたる。v6.10は`AIImageGenerator`を「実装すべき最小限のContract」として設計しており（`ai_image_generator.py`のdocstring）、属性を追加すると既存の構造的部分型が満たされなくなりうる（15.5節で再論） |

---

## 12. `None` と Null Object

### 12.1 決定：**案A（`orchestrator: ArticleFeaturedMediaOrchestrator | None`）を採用する**

### 12.2 根拠

Repository内にNull Object precedentは8種存在する（3.8節）。しかし本Releaseへは適用しない。

```text
決定的な理由：Null Orchestrator の apply() が返すべき値を決めることは、
              Fallback Policy を決めることと同義であり、本ReleaseのOut of Scope（N-5）である。

  仮に NullArticleFeaturedMediaOrchestrator.apply(article, prompt, filename) を作るとき、
  戻り値の候補は次のいずれかになる。

    (a) article をそのまま返す
          → 「画像なしで記事処理を継続してよい」という業務判断そのもの
    (b) featured_media_id=0 の ArticleData を返す
          → 既存 featured_media_id / DEFAULT_MEDIA_ID を破棄するという業務判断
    (c) 例外を送出する
          → Null Object としての意味を失う（呼び出し側が結局分岐を書く）

  (a)(b) はいずれも Image Generation Fallback Policy（別Release）が
  Architecture Review を経て決めるべき判断である。本Releaseが Null Object を導入すると、
  「Fallback Policy は Out of Scope」と宣言しながら実質的にそれを決めてしまう。
```

既存8種のNull Objectは、**戻り値の意味が自明な操作**（`enqueue()`→`DISABLED`結果、
`list()`→空リスト、`count()`→0、`save_analytics_entry()`→no-op）に対して適用されている。
`apply(article, ...) -> ArticleData`のように**戻り値が業務判断を内包する操作**に対する
Null Object precedentはRepository内に存在しない。

### 12.3 補足根拠

```text
・is_available() との組み合わせは WordPressOutput precedent（PR-5）と
  OutputManager.save_all() の skip pattern（manager.py:32-34）に整合する
・scope を最小に保てる（Null class・その apply() Contract・その E2E が不要）
・Null Object は将来 Fallback Policy Release が
  「画像なしで継続」を正式決定した時点で、非破壊的に追加できる（26章 DI-1）
```

### 12.4 型注釈の明示

`orchestrator`の型注釈は`ArticleFeaturedMediaOrchestrator | None`とし、
Runtime Wiring側に`None`チェック（または`is_available()`）を必ず経由させる。

---

## 13. Gate Contract

### 13.1 Gateの定義

```text
Gate: ImageGenerationConfig.from_env().enabled
      env: AI_IMAGE_GENERATION_ENABLED
      "true"（前後空白除去・大文字小文字無視の完全一致）のみ True。それ以外はすべて False。
      未設定も False。例外を送出しない（Fail Closed、PR-6）
```

本Releaseは**Gateの判定規則を一切変更しない**。v6.15の`from_env()`を呼ぶだけである。

### 13.2 Gate OFF → **正常な無効状態**（設定エラーではない）

```text
戻り値       : ArticleFeaturedMediaCompositionRoot インスタンス（正常に生成される）
orchestrator : None
image_mime_type : None
is_available(): False
例外         : 送出しない
environment  : AI_IMAGE_GENERATION_ENABLED 以外を一切読まない
credential   : 要求しない（OPENAI_API_KEY／WP_* が未設定でも成功する）
adapter      : OpenAIImageGenerator／WordPressMediaUploader を構築しない
外部接続     : 発生しない
```

これは`.env.example:188`の既定値`AI_IMAGE_GENERATION_ENABLED=false`と一致し、
**何も設定していない利用者にとっての既定動作が正常系である**ことを意味する。

### 13.3 Gate ON ＋ 設定不備 → **Fail Fast（既存factoryの`ValueError`を無変換伝播）**

3案を比較した。

| 案 | 内容 | 評価 |
|---|---|---|
| **Fail Fast（採用）** | `OpenAIImageGenerator.from_env()`／`WordPressMediaUploader.from_env()`の`ValueError`を捕捉せず、そのまま呼び出し側へ伝播する | **採用** |
| Fail Closed | `ValueError`を吸収し、`is_available()==False`のComposition Rootを返す | 不採用 |
| Domain Error | `ArticleFeaturedMediaCompositionError`等の固有例外へ変換する | 不採用 |

**Fail Fastを採用する根拠**

```text
FF-1  画像系Foundation群の一貫したerror contractに整合する。
      v6.14 は「無変換伝播（catchしない、変換しない、ラップしない、fallbackしない）」を
      明文化しており（設計書686-705行）、v6.12 も下位例外を無変換伝播する。
      Composition Root だけが例外を吸収すると、画像系の error contract が層ごとに分裂する。

FF-2  credential検証の責務は既に各 factory に委譲済みである。
      v6.15 設計書は「enabledのみを保持し、Provider APIキーやタイムアウト設定は読み取らない
      （それらは OpenAIImageGenerator の from_env() の責務のまま維持する）」と明記している
      （image_generation_config.py:9-11）。
      Composition Root がその判定を横取りして吸収するのは責務侵犯にあたる。

FF-3  吸収すると「未設定」と「設定ミス」が区別不能になる。
      OpenAIImageGenerator.from_env() は次の2種をいずれも ValueError で表現する。
          ・OPENAI_API_KEY が未設定           （＝まだ設定していない）
          ・OPENAI_IMAGE_TIMEOUT_SECONDS="abc"（＝設定したが値が誤っている）
      両者は例外型で区別できず、message文字列はPublic Contractではない。
      一律に吸収すれば、後者という明確な設定ミスが恒久的に不可視化される。
      これは「暗黙にsoft skip化しない」という本Releaseの要求（G-5）に正面から反する。

FF-4  Gate ON は利用者の明示的な意思表示である。
      AI_IMAGE_GENERATION_ENABLED=true は「画像生成を使いたい」という宣言であり、
      その状態で credential が無いのは達成不能な要求である。
      main.py:201-205 は ANTHROPIC_API_KEY 未設定時に即時停止する precedent を持つ
      （PR-12）。「明示的に要求された依存の欠落は即時停止」という Repository の方針に整合する。

FF-5  コストが最小のタイミングで失敗する。
      Composition Root の構築は記事生成が1件も始まる前に行われる。
      この時点での失敗は、外部副作用ゼロ・課金ゼロ・部分状態ゼロであり、
      失われる作業が存在しない。実行中の記事ループ内での失敗とは性質が異なる。

FF-6  secret を露出しない。
      3.4節のとおり、両 from_env() の例外message は環境変数「名」のみを含み値を含まない。
      無変換伝播しても Security Contract（17章）に違反しない。
```

**Fail Closedを不採用とする根拠（AiPublishConfig precedent PR-11との差異）**

`AiPublishConfig.is_ready()`は`enabled`＋WordPress credential 3点の4条件ANDで判定し、
`AiPublishService.from_env()`は不成立時に`NullAiPublishService`を返す（3.7節・3.8節）。
これは本設計と逆の判断に見えるが、構造が異なる。

```text
AiPublishConfig は credential 自身を dataclass field として保持し
（wordpress_url / wordpress_username / wordpress_app_password、ai_publish_config.py:30-32）、
その有無を自分で判定できる。

本 Composition Root は Security Contract（17章）により credential を属性として
保持しない。したがって同じ形（自分で保持して is_ready() で判定する）を採れない。
credential の有無を自前で判定するには環境変数名を本パッケージへ複製する必要があり、
env var 名の Single Source of Truth（v6.11 の _ENV_API_KEY、v6.9 の _ENV_SITE_URL 等、
いずれも private 定数）が二重化する。

→ credential 検証は所有者である各 factory に委ね、その判定結果（例外）を
  そのまま伝播させるのが、SSOT を壊さない唯一の形である。
```

**Domain Errorを不採用とする根拠**

```text
・変換は情報を失う。ValueError の message（どの環境変数が欠けているか）は
  利用者にとって最も有用な情報であり、固有例外へ包むと from ... 連鎖を追う必要が生じる
・v6.14 が「raise ... from ... を使用しない」を明文化している（設計書699行）
・新規例外型は Public API 面積を増やす。Composition Root が独自の失敗語彙を持つ必然性がない
```

### 13.4 Gate OFF と Gate ON＋設定不備が同一状態にならないことの確認

本設計では両者は**構造的に区別される**。

```text
Gate OFF          → インスタンスが生成される（is_available() == False）
Gate ON ＋設定不備 → インスタンスが生成されない（ValueError が伝播する）
```

インスタンスの存在自体が両者を分けるため、設定ミスが正常な無効状態に紛れ込むことはない。
これによりG-5（暗黙のsoft skip化を行わない）が構造的に達成される。

### 13.5 `ValueError`の吸収について

**本設計は`ValueError`を一切吸収しない。** したがって「吸収対象・理由・観測可能性」の
記載義務は発生しない。`try`/`except`を1つも書かないことをContractとする
（v6.14 precedent、設計書697行「try／exceptを追加しない」）。

### 13.6 Inherited Limitation（v6.15から継承する制約）

**Amendment 1（F-3対応）**。本節は、v6.15 Gate Contractのうち本Releaseが変更しない部分に
起因する既存の非対称性を明示する。新たな設計判断ではなく、v6.15の既存Approved Contractを
そのまま継承した結果を記録するものである。

```text
事実:
  `AI_IMAGE_GENERATION_ENABLED=ture` のような値のtypoは、v6.15の Fail Closed規則
  （image_generation_config.py:38-39、`raw_value.strip().lower() == "true"` の完全一致判定）
  により、例外を送出せず静かに Gate OFF（13.2節と同一の正常な無効状態）として扱われる。

非対称性:
  Gate ON かつ credential 不足        → ValueError（Fail Fast、13.3節）で大声に失敗する
  Gate 値そのもののtypo（Gate OFF側） → 無言で Gate OFF になる（例外なし）

  FF-3（13.3節）は「未設定」と「設定ミス」の区別不能を Fail Fast 採用の主要根拠として
  挙げているが、Gate値自体には同じ論理が適用されておらず、この非対称性は設計書内で
  未説明のまま残っていた（Architecture Review 1 Finding F-3）。

本Releaseが新たに導入するものではないことの確認:
  本Releaseは ImageGenerationConfig.from_env()（v6.15）を無変更のまま呼び出すのみであり
  （13.1節「本Releaseは Gate の判定規則を一切変更しない」）、Gate値の parsing規則・
  Fail Closed方針のいずれも本Release由来ではない。v6.15 は Release Review Approved 済みの
  独立したContractであり、本非対称性は本Releaseの新規導入事項ではなく、v6.15からの
  継承事項（Inherited Limitation）である。

本Releaseでv6.15のContractを変更しない理由:
  ・v6.15 は Release Review Approved 済みであり、Fail Closed は意図的な設計判断である
    （image_generation_config.py:11「不正値・未設定はいずれもFalseとして扱い、
      例外は送出しない（Fail Closed）」）
  ・Gate値の厳格化（許可値の allowlist 化・不正値での例外送出）は v6.15 の
    Public Contract 変更にあたり、本Releaseの Scope（Composition Root新設、8〜9章）を
    超える。独立した Architecture Review を要する
  ・変更すれば Runtime Zero Diff（18章）・Backward Compatibility（19章）のいずれも
    損なう（v6.15 は本Releaseの変更対象外ファイルである。18.1節参照）

対応:
  Gate値厳格化は Deferred Item DI-9（Image Generation Gate Value Strict Validation、
  26章）として記録し、本Release完了後に独立検討する。本Releaseはこの限界を
  Inherited Limitation として明記するに留める。
```

---

## 14. Availability Contract

### 14.1 `is_available()`の定義

```python
def is_available(self) -> bool:
    return self.orchestrator is not None
```

```text
例外を送出しない（PR-5：WordPressOutput.is_available() と同じ性質）
副作用を持たない
environment を読まない（構築時に確定した状態のみを参照する）
何度呼んでも同じ値を返す（frozen であるため）
```

### 14.2 `is_available()` ≡ Gate ON であることの証明

```text
Gate OFF                → orchestrator = None            → False
Gate ON ＋ 設定完備      → orchestrator = 構築済み        → True
Gate ON ＋ 設定不備      → ValueError（インスタンス不在）  → 呼び出し自体が発生しない
Public constructor 経由  → INV-1 により両fieldは常にペア  → 一貫性が保証される
```

したがって、**`from_env()`が正常にインスタンスを返した場合に限り**、
`is_available() == config.enabled`が成立する（Amendment 1、F-9対応）。
Public constructor経由では、呼び出し側がGate状態と無関係な組合せ（例：
`enabled=False`相当の状況でも`orchestrator`を持つインスタンスを直接構築する等）を
作れるため、この等式の成立を保証しない。Gate ON＋構築失敗ではインスタンス自体が
返らないため、この等式の比較対象そのものが存在しない（14.3節）。
`enabled`を別属性として公開する必要がない（11.4節）ことの根拠は、あくまで
`from_env()`経由のインスタンスに関するものである。

### 14.3 状態一覧

| 状態 | インスタンス生成 | `orchestrator` | `image_mime_type` | `is_available()` | 例外 |
|---|---|---|---|---|---|
| Gate OFF | される | `None` | `None` | `False` | なし |
| Gate ON ＋ 正常設定 | される | 構築済み | `"image/png"`（既定） | `True` | なし |
| Gate ON ＋ OpenAI credential不足 | されない | — | — | — | `ValueError`（v6.11由来） |
| Gate ON ＋ `OPENAI_IMAGE_TIMEOUT_SECONDS`不正 | されない | — | — | — | `ValueError`（v6.11由来） |
| Gate ON ＋ WordPress credential不足 | されない | — | — | — | `ValueError`（v6.9由来） |
| Public constructor ＋ 不変条件違反 | されない | — | — | — | `ValueError`／`TypeError`（本Release） |

### 14.4 `is_available()`の保証範囲（Amendment 1、F-4対応）

`is_available() == True`が**保証すること**：

```text
・orchestrator が None ではないこと
・orchestrator.apply が callable であること（INV-2、11.5節）
・image_mime_type が非空 str であること（INV-3、11.5節）
・Composition Root の構築（from_env() または Public constructor の呼び出し）が
  完了していること
```

`is_available() == True`が**保証しないこと**：

```text
・外部API（OpenAI／WordPress）実行が成功すること
・credential が実サービスで有効であること（from_env() は形式検証のみ行い、
  実際にOpenAI／WordPressへ疎通できるかは検証しない。3.3節）
・apply() の実行そのものが成功すること
・upload の成功
・bind の成功
・Public constructor 経由で構築した場合、image_mime_type が v6.16
  generate_image_filename() の許可集合と互換であること
```

**`from_env()`限定の構造的保証**：`from_env()`が正常に返したインスタンスに**限り**、
`image_mime_type`はv6.16 filename policyと構造的に互換であることが保証される。

```text
根拠:
  v6.11 の output format:  png / jpeg / webp（_ALLOWED_OUTPUT_FORMATS、3.10節）
  対応する MIME:           image/png / image/jpeg / image/webp
  v6.16 の許可 MIME:       image/png / image/jpeg / image/webp / image/gif
                          （generated_image_filename_policy.py:56-61）

  v6.11 の output format から導かれる MIME の集合は、v6.16 の許可集合の
  真部分集合である（image/gif のみ v6.16 側の余剰）。
  したがって from_env() が返す image_mime_type は、
  generate_image_filename(title, image_mime_type) を必ず ValueError なく完走させる。
```

**Public constructorの責任**：Public constructorは任意の非空`str`を`image_mime_type`として
受け付ける現行のINV-3検証を維持し、v6.16のMIME allowlistをComposition Root側へ
複製する検証（canonical MIME検証）は**追加しない**。

```text
複製しない理由:
  ・v6.16 の許可集合（generated_image_filename_policy.py:56-61）はモジュール内部の
    ローカル dict であり、Public API として公開されていない
  ・Composition Root 側へ allowlist を複製すると、SSOT が v6.16 と Composition Root の
    2箇所へ分裂する。v6.16 が将来 image/gif 以外の形式を追加・変更した場合、
    Composition Root 側の複製が追随せず不整合を生む
  ・本Release の Public constructor は fake 注入と testability のために残している
    経路であり（11.3節）、任意の値を受け付けることを許容範囲とする
  ・from_env() 経路では上記のとおり互換性が構造的に保証されるため、
    追加検証を要しない
```

**Gate OFF時の利用precondition**：Gate OFF時、`orchestrator`は`None`である。
呼び出し側は`root.orchestrator`へアクセスする前に、必ず`is_available()`を確認
しなければならない。これは呼び出し側が守るべきContract（precondition）であり、
本Release自身はこれを強制する機構（Null Objectや例外での防御）を持たない
（12章、Null Object不採用の判断）。この場合に発生する挙動は16章 E-18を参照。

---

## 15. MIME Information Contract

本章はP-9（2章）の解消方針を定める。

### 15.1 比較した6案

| # | 案 | SSOT | provider非依存 | 既存Public API影響 | Runtime Wiringの単純さ | testability | scope creep | 評価 |
|---|---|---|---|---|---|---|---|---|
| 1 | `OpenAIImageGenerator`が予定output MIMEを公開する | v6.11内に維持 | △（具象に紐づく） | **追加のみ**（非破壊） | 高 | 高 | 小 | **採用** |
| 2 | provider非依存のgenerator capability Protocolを新設し、そこでMIMEを公開する | v6.11内に維持 | ◎ | 追加（Protocol新設）＋案1も必要 | 高 | 高 | 中 | 不採用（26章へDeferred） |
| 3 | output formatを独立configuration valueとして公開する（`ImageGenerationConfig`拡張等） | **config側へ移動** | ◎ | **変更**（v6.15 Public API拡張＋新env var） | 中 | 中 | 大 | 不採用 |
| 4 | filename policyの入力Contractを変更する（`GeneratedImage`を受け取る等） | v6.10 | ◎ | **破壊的**（v6.16 Public API変更） | 低 | 中 | 大 | 不採用 |
| 5 | orchestratorの処理順序・責務を変更する（filenameを内部生成する） | v6.10 | ◎ | **破壊的**（v6.14 `apply()` signature変更） | 高 | 中 | 大 | 不採用（26章へDeferred） |
| 6 | upload直前にfilenameを決定する新しい境界を設ける | v6.10 | ◎ | 追加（新Protocol＋新層） | 低 | 中 | 大 | 不採用 |

### 15.2 採用案：案1

**v6.11 `OpenAIImageGenerator`に read-only property を追加する。**

```python
# src/openai_image_generation/openai_image_generator.py（追加のみ）

@property
def output_mime_type(self) -> str:
    """このgeneratorが生成する予定の画像のcanonical MIME type。

    generate() の戻り値 GeneratedImage.mime_type と同一の写像
    （_MIME_TYPE_BY_OUTPUT_FORMAT）から導出されるため、両者は常に一致する。
    """
    return _MIME_TYPE_BY_OUTPUT_FORMAT[self._output_format]
```

```text
変更種別: 追加（Addition）
          既存attribute・method・signature・挙動のいずれも変更しない
          既存の呼び出し・テストは1件も影響を受けない
破壊的変更: なし
新規env var: なし
新規dependency: なし
```

### 15.3 Single Source of Truth

```text
SSOT: src/openai_image_generation/openai_image_generator.py の
      _MIME_TYPE_BY_OUTPUT_FORMAT（33-37行）と self._output_format（233行）

  この2つは既に「実際に生成される GeneratedImage.mime_type」の唯一の決定要因である
  （_build_generated_image、187行）。
  output_mime_type property はこの既存 SSOT を読み取って公開するだけであり、
  新しい真実源を作らない。

  Composition Root は image_mime_type を「保持」するが「決定」しない。
  Composition Root 内に MIME 文字列リテラルを一切書かないことを Contract とする。
```

### 15.4 「予定MIME」と「実際MIME」の不一致可能性

```text
v6.11 Adapter においては、構造的に不一致が起こらない。

  予定: output_mime_type       = _MIME_TYPE_BY_OUTPUT_FORMAT[self._output_format]
  実際: GeneratedImage.mime_type = _MIME_TYPE_BY_OUTPUT_FORMAT[self._output_format]
        （_build_generated_image、187行。同一のdict・同一のkey）

  同一式であるため、同一インスタンスに対して両者は常に等しい。
  さらに OpenAIImageGenerator は frozen ではないが、_output_format は __init__ 後に
  変更する Public API を持たない（private属性であり setter が存在しない）。
```

**将来の他providerに対する保証**：本Releaseは`OpenAIImageGenerator`以外のproviderを扱わない。
将来、`output_format`指定を無視するproviderが追加された場合、予定と実際が乖離しうる。
その場合の権威は**常に`GeneratedImage.mime_type`（実際値）**であることを本設計で明記する。
`image_mime_type`はあくまで「filenameを事前構築するための予定値」であり、
不一致の検出・是正はRuntime Wiring以降の責務とする（27章 OQ-1）。

### 15.5 不採用案の理由

```text
案2（provider非依存 capability Protocol）
  ・案1を実施したうえで、さらに Protocol を追加する形になる（案1の上位互換ではなく追加）
  ・Provider が OpenAIImageGenerator の1件しかない現時点では、
    複数実装という実需が存在せず speculative generality にあたる
  ・PR-2：Composition Root は具象を知る層であり、
    Composition Root からの利用に限れば Protocol は抽象化の利得を生まない
  ・v6.10 の AIImageGenerator を拡張する形を採ると破壊的変更になる
    （既存の構造的部分型が満たされなくなる）
  → Provider が2件目に達した時点で ai_image_generation へ追加する（26章 DI-2）

案3（独立configuration value）
  ・v6.15 設計は「enabledのみを保持し、Provider APIキーやタイムアウト設定は読み取らない」
    ことを明示的な Non-Goal としている（image_generation_config.py:9-11）。
    output format を追加することはこの Non-Goal に正面から反する
  ・新しい環境変数の追加が必要になり、.env.example 変更と利用者への説明義務が生じる
  ・SSOT が v6.11 から v6.15 へ「移動」する。移動先の config が指定した format を
    generator へ渡す配線が新たに必要になり、config と generator の既定値が
    二重管理になるリスクが生じる
  ・scope creep が最大

案4（filename policy の入力Contract変更）
  ・v6.16 の Public API `generate_image_filename(title, mime_type)` を変更する
    破壊的変更にあたる。v6.16 は Release Review Approved 済みであり、
    その Contract を次Releaseで壊すのは Release 運用として不健全
  ・かつ、この案単独では順序問題を解決しない。orchestrator が filename を
    事前入力として要求する構造は変わらないため、結局案5が必要になる

案5（orchestrator の順序・責務変更）
  ・問題の最も自然な根本解決である（filename は本来 mime_type に依存するため、
    generate 後に決まるべき値である）ことは認める
  ・しかし v6.14 の apply(article, prompt, filename) は Release Review Approved 済みの
    Public Contract であり、固定messageまで含めて Contract 化されている（設計書684行）。
    これを変更することは破壊的変更であり、本Releaseの Scope（Composition Root新設）から
    完全に逸脱する
  ・本Releaseは「既存Contractを組み立てる」ことが責務であり、
    「既存Contractを作り直す」ことは責務ではない（PR-4：新規business logicを追加しない）
  → 将来「Article Featured Media Orchestration v2」として独立検討する（26章 DI-3）

案6（upload直前に filename を決定する新境界）
  ・GeneratedImageUploadCapability.upload(image, filename) の filename 引数を
    実質的に無視する層を挟むことになり、Contract の意味が濁る
  ・新Protocol＋新層＋新E2E が必要で、Composition Root Release の scope を超える
  ・Runtime Wiring から見て「filename をどこで決めているか」が追いにくくなる
```

### 15.6 Runtime Wiring（将来）における利用イメージ（参考、本Releaseでは実装しない）

```text
root = ArticleFeaturedMediaCompositionRoot.from_env()   # 起動時に1回

if root.is_available():
    prompt   = construct_article_image_prompt(article.seo_title, article.excerpt)  # v6.17
    filename = generate_image_filename(article.seo_title, root.image_mime_type)    # v6.16
    article  = root.orchestrator.apply(article, prompt, filename)                  # v6.14
```

この4行が成立することをもって、本Releaseの設計目標G-1・G-3・G-8が達成されたと判断する。
なお`try`/`except`をどこに置くか、`article.seo_title`と`article.item.title`のどちらを
titleに充てるかはいずれも本ReleaseのOut of Scopeである（N-4・N-5）。

---

## 16. Error Contract

### 16.1 分類表

| # | 事象 | 発生元 | 例外型 | 扱い |
|---|---|---|---|---|
| E-1 | Gate OFF | v6.15 | — | **例外なし**。正常な無効状態（13.2節） |
| E-2 | `AI_IMAGE_GENERATION_ENABLED`の値不正（`1`／`yes`／`TRUE `等） | v6.15 | — | **例外なし**。Fail Closedにより`False`＝E-1と同一（PR-6） |
| E-3 | `OPENAI_API_KEY`未設定・空白 | v6.11 `from_env()` | `ValueError` | **無変換伝播** |
| E-4 | `OPENAI_IMAGE_TIMEOUT_SECONDS`が非整数・非正 | v6.11 `from_env()` | `ValueError` | **無変換伝播** |
| E-5 | `WP_SITE_URL`／`WP_USERNAME`／`WP_APP_PASSWORD`未設定・空白 | v6.9 `from_env()` | `ValueError` | **無変換伝播** |
| E-6 | v6.11 constructorの値検証失敗 | v6.11 `__init__` | `ValueError` | **無変換伝播**（`from_env()`経由では`api_key`検証以外到達しないが、Contractとして記載） |
| E-7 | v6.9 constructorの値検証失敗 | v6.9 `__init__` | `ValueError` | **無変換伝播**（同上） |
| E-8 | v6.12 constructorのcapability不一致 | v6.12 `__init__` | — | **例外なし**。v6.12はDuck Typingで検証を`upload()`まで遅延する（3.4節） |
| E-9 | v6.14 constructorのcapability不足 | v6.14 `__init__` | `TypeError` | **無変換伝播**。`from_env()`経路では構造上到達不能（v6.11／v6.12はいずれも該当methodを持つ）だが、Contractとして保証する |
| E-10 | signature不一致（`generate`／`upload`が存在するが引数が異なる） | — | — | **検出しない**。v6.14のcapability検証は`callable()`のみであり、signature検証をしない。本Releaseもこれを変更しない。不一致は`apply()`実行時に`TypeError`として顕在化する（Runtime Wiring以降の関心事） |
| E-11 | 不変条件INV-1違反（片方だけ`None`） | 本Release `__post_init__` | `ValueError` | **送出**（固定message、Public Contract） |
| E-12 | 不変条件INV-2違反（`orchestrator`が`apply`を持たない） | 本Release `__post_init__` | `TypeError` | **送出**（固定message、Public Contract） |
| E-13 | 不変条件INV-3違反（`image_mime_type`が非str／空白） | 本Release `__post_init__` | `ValueError` | **送出**（固定message、Public Contract） |
| E-14 | import error（`openai`未インストール） | — | — | **本Releaseでは発生しない**。`openai`は`generate()`／`_get_client()`内で遅延importされ、`from_env()`／`__init__`はimportしない（3.3節）。`requests`は既存の必須依存であり`requirements.txt`に存在する |
| E-15 | dependency内部例外（`generate()`のRATE_LIMIT、`upload()`のHTTP 500等） | v6.11／v6.9 | `OpenAIImageGenerationError`／`WordPressMediaUploadError` | **本ReleaseのOut of Scope**。構築後の実行時にのみ発生する。Fallback Policy（別Release）の対象（9章「構築失敗と実行失敗を混同しない」） |
| E-16 | unexpected error（上記以外のPython runtime例外） | 任意 | 任意 | **変換しない・捕捉しない**。素通しする（v6.14 precedent、設計書700行） |
| E-17 | `KeyboardInterrupt`／`SystemExit` | 任意 | `BaseException`系 | **握りつぶさない**。本パッケージは`try`/`except`を1つも持たないため構造的に保証される |
| E-18 | `is_available()`未確認での`orchestrator`直接使用（precondition違反） | 呼び出し側 | Python標準例外（例：`AttributeError`） | **本Releaseの責務外**。Gate OFF時`orchestrator`は`None`であり（14.4節）、呼び出し側が`is_available()`を確認せず`root.orchestrator.apply(...)`等を呼び出した場合、Pythonのpreconditionチェックにより標準例外が発生し得る。本Releaseはこれを捕捉・変換しない（Amendment 1、F-4対応）。**正確な例外メッセージ・例外型はPublic Contractとして固定しない**（Pythonのバージョンや呼び出し形態により変わり得るため）。固定Public Contractとするのは「捕捉・変換しない」という方針のみである |

### 16.2 原則

```text
try／except を1つも書かない
例外 wrapper を作らない
raise ... from ... を使用しない
新規例外型を定義しない
部分的に構築された状態を返さない（構築途中で失敗した場合、
    インスタンスは生成されず、呼び出し側は None も半端な object も受け取らない）
credential や環境変数の「値」を message へ含めない
```

### 16.3 構築失敗の観測可能性

Fail Fastの採用（13.3節）により、設定不備は次の形で観測可能となる。

```text
・Python標準の traceback として即座に表面化する
・例外 message が欠落している環境変数「名」を含む
  （"missing or blank environment variable: OPENAI_API_KEY" 等）
・記事生成が1件も始まる前、外部副作用ゼロの時点で発生する
・本Releaseでは log 出力を行わない（N-13）。観測は例外の伝播のみで担保する
```

---

## 17. Security Contract

**Amendment 1（F-1対応）**：Architecture Review 1は、旧版の「secretを保持しない」という
表現が事実として不正確であることを指摘した（Finding F-1）。実測（`dataclasses.asdict()`・
`repr()`・属性到達性の直接検証）に基づき、本章を精密な表現へ全面的に書き直す。

### 17.1 直接保持と間接保持の区別

```text
Composition Root自身の直接field:
    orchestrator と image_mime_type の2件のみ（11.4節）。
    api_key・app_password・site_url・username等のsecretをfieldとして持たない。
    → 「Composition Root自身の直接fieldとしてsecretを保持しない」ことは事実として正確。

Composition Root が間接保持するもの:
    orchestrator field は ArticleFeaturedMediaOrchestrator インスタンスを保持し、
    そのインスタンスは内部（private属性）に OpenAIImageGenerator（_api_key を保持）と
    GeneratedImageWordPressMediaUploader 経由の WordPressMediaUploader
    （app_password を保持）への参照を持つ。

    root.orchestrator._image_generator._api_key             （実測到達可能。private属性のみ）
    root.orchestrator._media_uploader._media_uploader.app_password
                                                              （実測到達可能。★最終hopはpublic属性）

    → 「Composition Rootはorchestrator経由でsecret-bearing dependencyを
       間接保持する」ことが事実として正確な表現である。
```

### 17.2 Security Contract表

| # | 項目 | 決定 |
|---|---|---|
| S-1 | secretの直接／間接保持 | **直接fieldとしては保持しない**（`api_key`／`app_password`等をComposition Root自身のfieldに持たない）。**ただし`orchestrator`経由でsecret-bearing dependencyを間接保持する**（17.1節）。secretをComposition Rootへ重複コピーしない（`from_env()`は各下位factoryへcredentialをそのまま渡すのみで、自身の変数へ複製しない）。secretをComposition Root**自身の**直接Public属性として公開しない（`api_key`／`app_password`等のfieldを持たない） |
| S-2 | `repr`／`str`にsecretを含めない | **含めない（`repr(root)` / `str(root)`に限る）**。`orchestrator` fieldへ`field(repr=False)`を付与し（11.1節、Amendment 1採用）、dataclass自動生成`__repr__`／`__str__`から`orchestrator`を完全に除外する。これにより`repr(root)`・`str(root)`は`image_mime_type`のみを出力し、内部dependency（v6.9／v6.11／v6.12／v6.14）が将来`__repr__`を独自定義してもsecretを露出しない（採用理由・代替案比較は17.3節） |
| S-3 | exception messageへsecretを含めない | **含めない**。本Releaseが定義する4種の固定messageは入力値を一切埋め込まない。伝播する既存例外も環境変数「名」のみを含む（3.4節） |
| S-4 | log出力を本Releaseで行うか | **行わない**（N-13）。`print`・`logging`・ファイル書き込みを一切含まない。observability contractは将来Releaseで検討する（26章 DI-5） |
| S-5 | environment snapshotを保存するか | **保存しない**。`os.environ`のコピー・`ImageGenerationConfig`インスタンス・読み取った環境変数値のいずれもfieldとして保持しない |
| S-6 | image bytesを保持するか | **保持しない**。`GeneratedImage`をimportすらしない。本Releaseは画像バイナリに一切触れない |
| S-7 | import時にenvironmentを読むか | **読まない**。module levelに`os.getenv`／`os.environ`を書かない。環境変数の読み取りは`from_env()`の内側でのみ発生する（既存9パッケージのprecedentと一致、3.2節） |
| S-8 | module importだけで外部接続するか | **しない**。本moduleのimportは他パッケージのimportを引き起こすが、`requests`のimport（副作用なし）が最も重い操作であり、`openai`はimportされない（3.3節） |
| S-9 | constructor／`from_env()`だけで外部API実接続するか | **しない**。3.3節で実証済み。`from_env()`はGate ON＋全credential設定済みでも、HTTPリクエストを1本も送らず、OpenAI SDKをimportすらしない |
| S-10 | 内部dependencyの露出（属性到達性） | `image_generator`（`OpenAIImageGenerator._api_key`）と`WordPressMediaUploader`は**Composition Rootの公開属性としない**（11.4節）。ただし到達経路は一様に「private」ではない。`root.orchestrator._image_generator._api_key`は全hopがprivate属性だが、`root.orchestrator._media_uploader._media_uploader.app_password`は**最終hopがpublic属性**である（`WordPressMediaUploader.app_password`は`wordpress_media_uploader.py:114-117`で`self.app_password`として公開されている。実測確認済み）。「いずれもprivate属性である」という表現は事実と異なるため使用しない（Amendment 1、F-1対応） |
| S-11 | `dataclasses.asdict(root)`の扱い | `asdict(root)`は**secret-safeなserializationまたはlogging手段ではない**。`asdict()`は非dataclass fieldを`copy.deepcopy()`するため、戻り値の`"orchestrator"`キーには`OpenAIImageGenerator._api_key`・`WordPressMediaUploader.app_password`を保持したdependency object graphの複製が含まれ得る（実測確認済み。`field(repr=False)`は`__repr__`のみに影響し、`fields()`／`asdict()`の対象からは除外されない）。本Releaseは`asdict(root)`を公開用データ生成・logging・serializationへ使用しない（本Release自体がそもそも`asdict()`を呼び出さない。N-13）。呼び出し側が`asdict(root)`を安全なserialization手段として扱うことをContractとして保証しない |

**S-11の限定範囲（Documentation Integration工程で明確化、Architecture Review 2
Finding-1対応。Release Reviewにて訂正、RRF-1対応）**：本Releaseは`apply()`を
一切実行しない（N-1、9章「担当しない」）。新規E2E（SEC- Scenario、20.4節）が
検証対象とする`root`は、常に`from_env()`直後・画像workflow未実行の状態のみである。
`ArticleFeaturedMediaOrchestrator`自身はstateless（`apply()`はインスタンス属性へ
request単位のstateを保存しない、v6.14設計）だが、`root`が保持する
`OpenAIImageGenerator`は初回`generate()`呼び出し時に`openai.OpenAI` clientを
遅延生成し、`self._client`へキャッシュする（`_get_client()`、
`openai_image_generator.py`）。そのため`root`から到達可能なobject graphは
`apply()`実行後に変化し得る。本Releaseで実施したrepr／str／
`repr(asdict(root))`の検証、およびS-11・17.4節の評価は、いずれも
`from_env()`直後・`apply()`未実行の`root`に限定される。`apply()`実行後は、
生きた`openai.OpenAI` client（内部に`threading.RLock`を保持）を含む
dependency graphとなるため、`dataclasses.asdict(root)`は内部の
`copy.deepcopy()`で`TypeError: cannot pickle '_thread.RLock' object`と
なる可能性があり、S-11・17.4節の評価がそのまま成立するとは限らない。
本Releaseは`apply()`を実行する経路を一切持たないため（Composition Root自身も
E2Eも`apply()`を呼び出さない）、この`apply()`実行後の状態は本Releaseの
評価範囲外である。将来のRuntime Wiring（DI-4）が実際に`apply()`を呼び出す
構成となった時点で、`apply()`実行後のSecurityおよびserialization特性を
改めて実測・評価すること。

### 17.3 `repr=False`の採用（Architecture Review 1 AR-4／F-1対応）

Architecture Review 1は次の2案を比較したうえで、案A（`repr=False`）を第一推奨とした。

| 案 | 内容 | 評価 |
|---|---|---|
| **案A：`field(repr=False)`（採用）** | `orchestrator` fieldをdataclass自動`__repr__`から除外する | **採用** |
| 案B：現行の自動repr維持 | 内部dependencyのdefault reprへ依存することを明記するのみ | 不採用 |

**案A採用の根拠**

```text
・追加コストが小さい（1 field への decorator 相当の追加のみ）
・repr(root) / str(root) の安全性を、内部dependency（v6.9／v6.11／v6.12／v6.14）が
  将来 __repr__ を独自定義するか否かから完全に分離できる。dataclass生成の
  __repr__ は repr=False の field を「参照すらしない」ため（実測確認済み。
  17.4節参照）、依存package側の将来変更に対する回帰リスクをrepr(root)については
  構造的にゼロへ落とせる
・orchestratorの内部状態をComposition Rootのreprへ表示する実需がない
  （Runtime Wiringは is_available() / apply() / image_mime_type のみを使う。11.4節）
・custom __repr__ の自作は不要。field(repr=False) のみで目的を達成できる
  （custom __repr__ は保守対象コードを増やし、dataclass標準機構から外れるため
    採用しない）
```

案Bを不採用とした理由は上記の裏返しである。「内部dependencyがdefault object repr
であることに依存する」状態を維持すると、将来いずれかのpackageがdataclass化や
`__repr__`定義を行った場合に`repr(root)`からsecretが露出しうる。回帰検知手段
（20章 SEC-系Scenario）だけでは検知が実装後になり、事前の構造的防止にならない。

### 17.4 `repr=False`が保護する範囲と保護しない範囲（重要な限界）

**Amendment 1における実測確認**：`field(repr=False)`は`repr(root)`／`str(root)`を
完全に保護するが、`repr(dataclasses.asdict(root))`は保護しない。両者は異なる機構で
あるため、明確に区別する。

```text
保護される:
  repr(root)                        → "ArticleFeaturedMediaCompositionRoot(image_mime_type='image/png')"
                                        orchestrator は出力に一切現れない（実測確認）
  str(root)                         → 同上（dataclassの __str__ は __repr__ に委譲される）

  → repr=False は dataclass 生成の __repr__ メソッド自体が orchestrator field を
    参照しないようにする。したがって内部dependencyが将来どのような __repr__ を
    定義しても、repr(root) / str(root) の安全性には一切影響しない。

保護されない:
  repr(dataclasses.asdict(root))    → 辞書の値として orchestrator インスタンスが
                                        そのまま格納され、その repr() が呼ばれる
                                        （実測: <...ArticleFeaturedMediaOrchestrator
                                          object at 0x...> という orchestrator 自身の
                                          default object repr がテキスト中に現れる）

  → asdict() は dataclass の __repr__ を経由せず、fields() を直接走査して
    非dataclass fieldを deepcopy するのみである。repr=False は __repr__ 生成にのみ
    作用するmetadataであり、fields()／asdict()の挙動には影響しない（実測確認）。
    したがって repr(asdict(root)) の安全性は、現状では引き続き
    v6.9／v6.11／v6.12／v6.14 が __repr__ を独自定義していない
    （default object reprのままである）ことに依存する。
```

**残存する依存関係の記録**：`repr(asdict(root))`の安全性が内部dependencyのdefault repr
維持に依存するという性質（S-10の限界の系譜）は、`repr=False`採用後も完全には解消され
ない。ただし、本Release自身が`asdict()`を呼び出さないこと（S-11）、および`asdict()`を
安全なserialization手段として扱わないというContract（S-11）により、この残存依存は
「本Releaseが誤って安全と主張する」形にはならない。将来この経路の安全性を積極的に
検証したい場合は、20章 SEC-系Scenarioの回帰検知（F-7対応）が同じ入力に対して
繰り返し実行される形で担保する。

---

## 18. Runtime Zero Diff

### 18.1 変更しないファイル

```text
main.py
src/image_resolver.py
src/outputs/（base.py / manager.py / wordpress_output.py / markdown_output.py /
             save_result.py / taxonomy_config.py）
src/pipeline/（全4ファイル）
src/ai/（全ファイル）
src/scheduler/ / src/workflow_engine/ / src/execution_history/ / src/workflow_monitor/
src/retry_*（全パッケージ。retry_composition を含む）
src/logger/ / src/analytics/
src/collector.py / keyword_filter.py / duplicate_filter.py / importance_judge.py /
    article_generator.py / seo_title_generator.py / x_post_generator.py /
    slug_generator.py / image_extractor.py / publishing_config.py / sns_config.py
scripts/（全17ファイル）
既存publish実行順序（main.py:310-391 の記事ループ）
requirements.txt
.env.example  ★新規環境変数がないため変更不要
```

**`.env.example`を変更しない根拠**：本Releaseは新しい環境変数を導入しない。
`AI_IMAGE_GENERATION_ENABLED`はv6.15で追記済みであり、その注記
「v6.15.0時点では、このGateを読み取って画像生成を実行するRuntime連携はまだ実装されていません
（Consumer-less Foundation）」（`.env.example:185-188`）は、本Release完了後も**真のまま**である
（本ReleaseもRuntimeへ配線しないため）。したがって記述の更新義務が生じない。

### 18.2 変更するファイル（Production Code）

```text
新規  src/article_featured_media_composition/__init__.py
新規  src/article_featured_media_composition/article_featured_media_composition_root.py
追加  src/openai_image_generation/openai_image_generator.py
        → output_mime_type property の追加のみ（15.2節）
        → 既存attribute・method・signature・挙動を一切変更しない
```

### 18.3 Runtime Zero Diffの証明方針

| # | 検証 | 方法 |
|---|---|---|
| RZ-1 | Runtime対象ファイルが本パッケージをimportしていない | v6.17 precedent（`test_e2e_v6_17_0_*.py:656-679`）の静的テキスト参照Guardを踏襲。対象を`main.py`／`src/image_resolver.py`／`src/outputs/*.py`／`src/pipeline/*.py`／`scripts/*.py`へ拡張する |
| RZ-2 | 本パッケージが禁止importを行っていない | AST解析による依存Guard。`outputs`／`main`／`image_resolver`／`pipeline`／`ai`／`scheduler`／`retry_*`／`logger`／`analytics`／`generated_image_filename_policy`／`article_image_prompt_construction`／`ai_image_generation`／`article_featured_media`をimportしていないことを検証（10.3節） |
| RZ-3 | v6.11への変更が追加のみであること | `output_mime_type`追加後も、v6.11の既存E2E（`test_e2e_v6_11_0_*.py`）が無改修で全件PASSすることを確認 |
| RZ-4 | 実バイト差分 | `git diff --stat`により、変更ファイルが18.2節の3件のみであることをRelease工程で確認する（E2Eの対象外。v6.17設計書precedentと同じ扱い） |
| RZ-5 | 既存publish動作の不変 | Formal Regressionにより、既存Regression Inventory全件がPASSすることを確認 |

---

## 19. Backward Compatibility

| # | 対象 | 影響 |
|---|---|---|
| BC-1 | v6.9 `wordpress_media` | **なし**（無改修） |
| BC-2 | v6.10 `ai_image_generation` | **なし**（無改修。`AIImageGenerator` Protocolを拡張しない＝既存の構造的部分型は不変） |
| BC-3 | v6.11 `openai_image_generation` | **追加のみ**。`output_mime_type` propertyの追加。既存の`__init__`／`from_env()`／`generate()`／例外Contract／`__all__`のいずれも不変。既存呼び出し側は1件も影響を受けない |
| BC-4 | v6.12〜v6.17 | **なし**（無改修） |
| BC-5 | `main.py`以下のRuntime | **なし**（Consumer-less継続。動作は完全に同一） |
| BC-6 | 既存環境変数 | **なし**。新規追加・意味変更・既定値変更のいずれもなし |
| BC-7 | 既存テスト | **なし**。既存E2E全件が無改修でPASSする想定（RZ-3・RZ-5で検証） |
| BC-8 | `requirements.txt` | **なし**（dependency追加なし） |

**変更種別の区別（要求どおり）**

```text
追加（Addition）      : output_mime_type property（v6.11）
                        article_featured_media_composition パッケージ全体（新規）
変更（Modification）  : なし
破壊的変更（Breaking）: なし
```

---

## 20. Test Strategy

### 20.1 テストファイル

```text
tests/test_e2e_v6_18_0_article_featured_media_composition_root_foundation.py

形式: standalone script（既存precedentどおり。pytestを使用しない）
実行: cd projects/03_game_content_ai
      ..\..\venv\Scripts\python.exe tests/test_e2e_v6_18_0_article_featured_media_composition_root_foundation.py
補助: check() / check_true() / check_false() / invoke() を v6.15〜v6.17 から踏襲
```

### 20.2 E2E境界（外部接続ゼロの保証）

**Amendment 1（F-2対応）**：旧版は、同一テストプロセス内での`sys.modules`検査＋
条件付きskipという設計だった。しかし同じ§20.4の`MIME-`Scenarioが`generate()`を
実行し（`openai_image_generator.py:284`が無条件`import openai`を行うため）、
実行後は`"openai"`が必ず`sys.modules`に常駐する。結果、実行順序次第で
`IMPORT-`Scenarioが恒常的にskipされ、Formal RegressionのPASS件数が不安定になる
（Architecture Review 1 Finding F-2）。本Amendmentは、skipを一切用いない
決定的な検証へ置き換える。

```text
本テストは実OpenAI API・実WordPress API・実HTTP通信・実課金のいずれも発生させない。
以下の3手段はすべてskipを設けず、PASSまたはFAILを必ず確定させる（D-B3、20.4節）。

(1) openai 未import確認（clean subprocessによる決定的検証。D-B1）
    現在のテストプロセスの sys.modules 状態に依存しない。
    Repository の venv Python（venv/Scripts/python.exe）を明示的に使用し、
    clean な subprocess 内で完結させる。

    venv/Scripts/python.exe を明示指定する理由（Documentation Integration工程で
    追記、Architecture Review 2 Finding-2対応）：
      ・Repository の正式実行契約（本設計書・既存全E2Eが
        `.\venv\Scripts\python.exe tests\<file>` を実行コマンドとして明記する
        precedent）へ固定するため
      ・`sys.executable` に委ねた場合、将来何らかの理由でCI等が異なる
        インタープリタ（system Python等）から本テストプロセス自体を起動すると、
        検証対象のsubprocessも意図せず system Python へすり替わり得るため
      ・本Repositoryの実行環境がWindows固定のvenv構成（`venv/Scripts/python.exe`）
        であり、この構成と一致させることで実行環境の想定外の分岐を避けるため
      ・PATH上の裸の`python`（bare python）を使用しないという、本Repository全体の
        運用方針（Architecture Design・Amendment・Code Review・Formal Regression
        各工程プロンプトが繰り返し明記）と一致させるため

      subprocess.run(
          [str(VENV_PYTHON), "-c", <inline script>],
          cwd=PROJECT_ROOT,
          env={**os.environ,
               "AI_IMAGE_GENERATION_ENABLED": "true",
               "OPENAI_API_KEY": "test-key",
               "WP_SITE_URL": "https://example.invalid",
               "WP_USERNAME": "test-user",
               "WP_APP_PASSWORD": "test-password"},
          capture_output=True, text=True, timeout=30,
      )

      <inline script> の内容:
          sys.path.insert(0, "src")
          from article_featured_media_composition import ArticleFeaturedMediaCompositionRoot
          root = ArticleFeaturedMediaCompositionRoot.from_env()
          print("OPENAI_IMPORTED=" + str("openai" in sys.modules))

    検証項目:
      ・subprocess の exit code が 0 であること
      ・stdout に "OPENAI_IMPORTED=False" が含まれること
      ・stderr が空（traceback 等が出ていない）こと
    この検証は実行順序に一切依存せず、常にPASSまたはFAILへ確定する。

(2) network遮断（socket低レベル経路の遮断。D-B2）
    **(1)のclean subprocessとは独立に、test本体プロセス内（in-process）で
    実施する**（Architecture Review 2 Finding-3対応で明確化）。(1)は
    「openaiが決してimportされないこと」をsys.modules汚染から隔離して
    確認するためにsubprocess化が必須だったが、(2)のsocket patchは
    test本体プロセスの状態汚染を気にする必要がない（socket関数の
    patch対象はprocess-global状態であり、他Scenarioの実行順序に
    依存しない）。したがって(2)はsubprocessを追加起動せず、
    test本体プロセス内で直接 socket.getaddrinfo／socket.socket.connect
    をpatchしてfrom_env()を呼び出す、より単純な構成を採用する。

    from_env() 実行中、少なくとも次の2経路を遮断する。
      ・socket.getaddrinfo   （DNS解決。呼ばれた時点で外部通信の準備が始まっている
                                ことを意味するため、DNS解決自体を防止対象に含める）
      ・socket.socket.connect
    いずれかが呼ばれた場合、即座に AssertionError 等で失敗させる sentinel へ
    差し替えたうえで from_env() を実行し、例外が発生しない（＝どちらも
    呼ばれなかった）ことを確認する。
    socket 層で遮断することで、requests・urllib・http.client 等の
    HTTPライブラリ固有の実装（例：requests.sessions.Session.request）へ
    依存せず、低レベルで経路を一括網羅する。
    patchは必ず try/finally で復元する（本テストコード側の処理であり、
    Production Code の「例外を捕捉しない」というContract（16章）とは別物である）。

    AC-16の「clean subprocessによる決定的検証」という表現は(1)（openai未import
    確認）を指す。(2)（network遮断）はin-process検証であり、(1)とは異なる
    実行context・異なる根拠（process-global状態の汚染有無）に基づく、独立した
    検証手段である。

(3) ダミーcredentialでの構築成功
    ダミーcredential（"test-key" / "https://example.invalid" 等）で構築が
    成功することをもって、構築が外部検証を伴わないことを実証する。

新規v6.18 E2Eは、環境状態や実行順序を理由としたskipを一切設けない。
正式Inventoryの全Scenarioは、必ずPASSまたはFAILへ確定する（D-B3）。
```

### 20.3 mock／fake方針

```text
・環境変数はすべて os.environ の直接操作＋try/finally による完全復元で制御する
  （v6.15 precedent。ENV-* Scenario）
・OpenAI SDK・WordPress API のmockは作らない（そもそも呼ばれないため不要）
・socket.getaddrinfo / socket.socket.connect の patch は try/finally で必ず復元する
  （Amendment 1、F-2対応。20.2節(2)）
・openai未import確認は subprocess で完結させ、テストプロセス自身の sys.modules は
  一切参照しない（Amendment 1、F-2対応。20.2節(1)）
・Public constructor 経由のテストでは FakeOrchestrator（apply を持つだけの最小class）を注入する
  → v6.14 が Duck Typing を採用しているため isinstance 検証に阻まれない（11.5節）
・不正入力テストでは apply を持たないobject・非str・空白strを渡す
・ダミーsecret（例："SK-TESTSECRET" / "TESTPASSWORD"）を用いる repr 回帰検知（F-7対応）
  では、実際の OpenAI／WordPress credential 形式を模倣する必要はなく、
  テキスト表現に出現しないことのみを確認する
```

### 20.4 Scenario候補

| prefix | 対象 | Scenario例 |
|---|---|---|
| `API-` | Public API | `__all__`が`["ArticleFeaturedMediaCompositionRoot"]`のみ／`from_env`がclassmethod／`is_available`が存在／期待外のsymbolを`__init__`がexportしない／field名と順序 |
| `IMM-` | immutable contract | `frozen=True`である／`orchestrator`への再代入で`FrozenInstanceError`／`image_mime_type`への再代入で同上／`fields()`が2件（`orchestrator`は`repr=False`でも`fields()`には含まれることを確認。17.4節） |
| `GATE-` | Gate OFF | 未設定→`is_available() False`／`"false"`→同／`"1"`・`"yes"`・`"TRUE"`（前後空白あり含む）→同／`" true "`→**有効**（v6.15の正規化規則）／Gate OFF時に`OPENAI_API_KEY`・`WP_*`が未設定でも例外が出ない |
| `ON-` | Gate ON＋正常設定 | ダミーcredentialで`is_available() True`／`orchestrator`が`apply`を持つ／`image_mime_type == "image/png"`／2回呼ぶと別インスタンスだが同一の可用性 |
| `ERRCFG-` | Gate ON＋設定不備 | `OPENAI_API_KEY`欠落→`ValueError`／`OPENAI_IMAGE_TIMEOUT_SECONDS="abc"`→`ValueError`／同`="0"`→`ValueError`／`WP_SITE_URL`欠落→`ValueError`／`WP_USERNAME`欠落→同／`WP_APP_PASSWORD`欠落→同／**いずれの場合もインスタンスが返らない**ことを確認 |
| `SEQ-` | 構築順序・単一インスタンス | Gate OFF時、`os.getenv`経路の読み取りkeyを直接trackingし`AI_IMAGE_GENERATION_ENABLED`以外が現れないことを確認する（**Documentation Integration工程で表現を精密化、Architecture Review 2 Finding-2対応**：credential factory（`OpenAIImageGenerator`／`WordPressMediaUploader`）は`os.environ.get`を用いるため、このtrackingは`os.getenv`経路のみを直接観測し、`os.environ.get`経路を直接検証しない。credential factoryへの誤到達自体は、credentialを全除去した状態で実行する`GATE-OFF-NO-EXCEPTION`Scenarioが、誤到達時に`ValueError`で必ず失敗する形で間接的に検出する）／Gate ON時にOpenAI credentialの欠落がWordPress credentialの欠落より先に報告される／`root.orchestrator`が複数回参照しても同一オブジェクト（`is`比較） |
| `AVAIL-` | `is_available()` | `orchestrator is None`と完全一致／例外を投げない／副作用がない／複数回呼んで同値 |
| `NONE-` | `None` Contract | Gate OFF時に`orchestrator is None`かつ`image_mime_type is None`／Null Objectを返さない（`orchestrator`が`apply`を持たないことを確認） |
| `INV-` | 不変条件 | INV-1違反（片方のみ`None`）×2方向→`ValueError`＋固定message一致／INV-2違反（`apply`なし）→`TypeError`＋固定message／INV-3違反（非str・空白）→`ValueError`＋固定message／正常なペアは成功 |
| `MIME-` | MIME Contract | `output_mime_type`がv6.11に存在しread-only（代入で`AttributeError`）／既定`"image/png"`／`output_format="jpeg"`→`"image/jpeg"`／`="webp"`→`"image/webp"`／**`generate()`が返す`GeneratedImage.mime_type`と一致**（FakeClientで`generate()`まで実行し、外部接続なしで突合。このCaseは`openai`を意図的にimportさせる唯一のScenario群であり、`IMPORT-`の決定性はsubprocess化により本Scenarioの実行有無・実行順序と無関係になる。20.2節(1)）／`generate_image_filename(title, root.image_mime_type)`が`ValueError`にならない（v6.16許可4種の部分集合であることの実証）／Composition Root moduleにMIME文字列リテラルが存在しない（AST／テキスト検査） |
| `SEC-` | Security | `repr(root)`／`str(root)`にAPI key・app passwordが含まれない（`orchestrator`が`repr=False`のため構造的に保証。17.3節・17.4節）／`fields()`に`orchestrator`／`image_mime_type`の2件のみ存在する／例外messageに環境変数「値」が含まれない／module levelに`os.getenv`が存在しない（AST検査）／**repr回帰検知（Amendment 1、F-7対応）**：ダミーsecret（例："SK-TESTSECRET" / "TESTPASSWORD"）でGate ON構築したrootに対し、`repr(root)`・`str(root)`・`repr(dataclasses.asdict(root))`のいずれのテキスト表現にもダミーsecret文字列が含まれないことを確認する。ただし`asdict(root)`そのものの**内部構造**（deepcopyされたobject graph）にsecret-bearing dependencyが到達可能であること自体は本Scenarioの合否条件にしない（17.2節 S-11・17.4節の限界の直接の帰結であり、Contract違反ではない） |
| `IMPORT-` | import副作用（Amendment 1、F-2対応で全面刷新。Architecture Review 2 Finding-3対応で(1)(2)の実行context区別を明確化） | moduleのimportだけでは環境変数を読まない（副作用なし）／`openai`が**clean subprocess内で決定的に**importされないことを確認する（20.2節(1)、skipなし）／network（`socket.getaddrinfo`・`socket.socket.connect`）が発生しない（20.2節(2)、**test本体プロセス内でのin-process検証**。(1)のsubprocessとは独立、sentinelによる遮断）／importが例外を出さない |
| `DEP-` | 依存Guard（AST。Amendment 1、F-6対応） | 10.3節の禁止import一覧を1件ずつ検証（`outputs`／`main`／`image_resolver`／`pipeline`／`ai`／`scheduler`／`retry_*`／`logger`／`analytics`／`generated_image_filename_policy`／`article_image_prompt_construction`／`ai_image_generation`／`article_featured_media`）／例外を**捕捉しない**こと（AST：`ast.ExceptHandler`ノードが0件。`ast.Try == 0`から変更——`try/finally`はcleanup目的で例外を捕捉しないため一律禁止しない。16.2節の原則「例外を捕捉しない・変換しない・wrapperを作らない」を直接検証する形へ揃える）／`ast.Raise`が`__post_init__`内のINV-1〜INV-3検証3種以外に存在しない／新規例外classを定義しない |
| `RUNTIME-` | Runtime Zero Diff | `main.py`／`src/image_resolver.py`／`src/outputs/*.py`／`src/pipeline/*.py`／`scripts/*.py`が`article_featured_media_composition`を参照していない |
| `COMPAT-` | backward compatibility | v6.11の`__all__`が不変／`OpenAIImageGenerator.__init__`のsignatureが不変／`generate`／`from_env`が存在／v6.10の`AIImageGenerator` Protocolが`generate`のみを持つ（拡張されていない）／v6.15・v6.16・v6.17の Public API が不変 |
| `ENV-` | environment isolation | 各Scenario前後で`os.environ`が完全復元される／テスト全体の終了時に開始時と同一の`os.environ`である |
| `READINESS-` | Composition Readiness（Amendment 1、F-5対応。AC-22の置き換え） | Runtime Wiringの実装・実行ではなく、既存Foundation群が後続Runtime Wiringへ進める型・Contract上の準備状態を検証する。Gate ON＋ダミーcredentialでComposition Rootを構築し、外部接続を発生させずに次を確認する：(1) `root.is_available() is True`／(2) `root.image_mime_type`が非空`str`／(3) `construct_article_image_prompt(valid_title, valid_excerpt)`が`str`を返す／(4) `generate_image_filename(valid_title, root.image_mime_type)`が`ValueError`を送出せず`str`を返す／(5) `root.orchestrator.apply`が`callable`である／(6) `apply()`自体は呼び出さない（実行しない）／(7) OpenAI／WordPressへの外部接続を発生させない。**境界の明示（Architecture Review 2 Finding-4対応）**：(3)(4)で`construct_article_image_prompt`（v6.17）・`generate_image_filename`（v6.16）をimportして呼び出すのは**test code自身**であり、`ArticleFeaturedMediaCompositionRoot`（Production Code）はこれらをimportしない（10.3節、`DEP-NO-V16-IMPORT`／`DEP-NO-V17-IMPORT`Scenarioで検証済み）。これは既存Contract間の統合可能性を確認する検証であり、Runtime Wiringの実装ではない |

**Scenario／Case／Assertion数（Amendment 1、F-8対応）**：具体的な目標数を設計上の
固定値としない。次を満たすことを設計上のContractとし、実際の件数は実装結果として
Formal Regression実績に記録する。

```text
・Acceptance Criteria（25章）をすべて被覆する
・重複Caseを作らない（同一Contractの表記違いだけを水増ししない）
・Scenario／Case／Assertion数そのものを品質目標にしない
```

### 20.5 Formal Regression

```text
既存Regression Inventory（v6.17時点で20ファイル）へ本Releaseの新規E2Eを追加し、
21ファイルとして全件実行する。

特に重点確認:
  test_e2e_v6_11_0_openai_image_generation_adapter_foundation.py
    → output_mime_type 追加後も無改修で全件PASSすること（RZ-3）
  test_e2e_v6_14_0_*.py / v6_15_0 / v6_16_0 / v6_17_0
    → 無改修で全件PASSすること

Deterministic性（Amendment 1、F-2対応）:
  新規v6.18 E2Eは環境状態・実行順序に起因するskipを一切含まない（20.2節D-B3）。
  したがってFormal Regressionの総PASS件数（既存件数＋v6.18新規件数）は、
  実行順序・実行回数によらず常に同一の値へ確定する。v6.17実績
  （2644/2644 PASS）と同様に、正確な件数をもってRelease判定の根拠とする。
```

---

## 21. Production Implementation Scope

### 21.1 新規作成ファイル

```text
src/article_featured_media_composition/__init__.py
    docstring（Composition Root の責務・Consumer-less である旨）
    from .article_featured_media_composition_root import ArticleFeaturedMediaCompositionRoot
    __all__ = ["ArticleFeaturedMediaCompositionRoot"]

src/article_featured_media_composition/article_featured_media_composition_root.py
    docstring（Source of Truth: 本設計書へのポインタ、責務、Non-Goal）
    from __future__ import annotations
    from dataclasses import dataclass, field
    from article_featured_media_orchestration import ArticleFeaturedMediaOrchestrator
    from generated_image_wordpress_media import GeneratedImageWordPressMediaUploader
    from image_generation_config import ImageGenerationConfig
    from openai_image_generation import OpenAIImageGenerator
    from wordpress_media import WordPressMediaUploader

    @dataclass(frozen=True)
    class ArticleFeaturedMediaCompositionRoot:
        orchestrator: ArticleFeaturedMediaOrchestrator | None = field(repr=False)
                                                # Amendment 1（F-1対応）。17.3節参照
        image_mime_type: str | None
        def __post_init__(self) -> None       # INV-1〜INV-3
        @classmethod
        def from_env(cls) -> ...              # 10.1節の[1]〜[9]
        def is_available(self) -> bool        # return self.orchestrator is not None

tests/test_e2e_v6_18_0_article_featured_media_composition_root_foundation.py
    ・subprocess経由でのopenai未import決定的検証を含む（20.2節(1)、Amendment 1、F-2対応）
    ・socket.getaddrinfo / socket.socket.connect の遮断による外部接続ゼロ検証を含む
      （20.2節(2)）
    ・skipを一切用いない（D-B3）
```

推定行数：Composition Root本体 約90〜120行（docstring込み）、`__init__.py` 約15行。
`field(repr=False)`の追加によるProduction Code本体の行数への影響は軽微（1行程度）。

### 21.2 変更候補ファイル（Public API変更候補）

```text
src/openai_image_generation/openai_image_generator.py
    追加: @property def output_mime_type(self) -> str        （約8行、docstring込み）
    変更: なし
    削除: なし
    __all__ / __init__.py: 変更なし（propertyはclassの一部でありexport対象が増えない）
```

### 21.3 変更不要ファイル

18.1節のとおり。`.env.example`・`requirements.txt`を含む。

### 21.4 想定blast radius

```text
新規パッケージ  : 1（既存コードから参照されない）
変更パッケージ  : 1（v6.11、追加のみ）
変更Runtimeファイル: 0
新規環境変数     : 0
新規外部依存     : 0
破壊的変更       : 0

→ 既存Runtimeへの危険性は実質ゼロ。
  唯一のリスクは v6.11 への property 追加だが、
  既存の属性名・method名と衝突しないこと（_output_format は private であり
  output_mime_type という公開名は現在未使用）を実読で確認済み。
```

---

## 22. Documentation Integration Plan（将来工程の予告）

本工程では文書統合を行わない（N-14）。将来のDocumentation Integration工程で
次を反映する想定のみを記録する。

```text
docs/ROADMAP.md
    ・v6.18.0 エントリの追加
    ・既存「Publish Composition Root Foundation（次候補）」エントリの位置づけ更新
      （本Releaseが画像スコープ限定版として先行した旨、および
        publish全体版が引き続き未着手である旨）
    ・「Article Featured Media Runtime Wiring」の前提条件の更新
      （Composition Root充足、Fallback Policy未充足）

docs/architecture.md
    ・Composition Root層への ArticleFeaturedMediaCompositionRoot 追記
      （RetryCompositionRoot と並置）

docs/CHANGELOG.md
    ・Added: article_featured_media_composition パッケージ
    ・Added: OpenAIImageGenerator.output_mime_type property
    ・Note: Consumer-less・Runtime Zero Diff 継続
    ・Tested: 新規E2E件数・Formal Regression実績

.env.example
    ・変更なし（18.1節の根拠による）
```

**実施結果（Documentation Integration工程で追記）**：上記予告のとおり、
`docs/ROADMAP.md`・`docs/architecture.md`・`docs/CHANGELOG.md`の3文書を実測値
（Formal Regression総Assertion 2790・正式Inventory21ファイル・新規E2E
1196行／128 Scenario／128 Case／146 Assertion・Runtime Zero Diff走査33ファイル等）
に基づいて更新した。`.env.example`は予告どおり無変更（新規環境変数を導入しない
ため）。各文書の反映内容は当該文書を参照。

---

## 23. Risks

| # | risk | 影響度 | 対策 |
|---|---|---|---|
| R-1 | Consumer-lessパッケージが10件目となり、「動くもの」が増えないまま複雑さだけが増す | 中 | 本Releaseは4行（15.6節）でRuntime Wiringが成立する状態を作る最後の構築系Releaseである。次はFallback Policy（小）、その次がRuntime Wiring（実動作）である旨を26章に明記する |
| R-2 | Fail Fastの採用により、将来Runtime Wiring時に`AI_IMAGE_GENERATION_ENABLED=true`かつcredential未設定の利用者の`main.py`が起動時に停止する | 中 | 意図的な設計（13.3節 FF-4／FF-5）。ただし利用者影響を伴う業務判断であるため、27章 OQ-2としてArchitecture Reviewの明示的確認事項とする |
| R-3 | v6.11への`output_mime_type`追加が、v6.11のRelease Review Approved済みContractへの事後変更にあたる | 低 | 追加のみであり破壊的変更ではない（19章 BC-3）。RZ-3で既存E2Eの無改修PASSを確認する |
| R-4 | `frozen=True`が`orchestrator`の内部状態までは凍結しない | 低 | v6.14 orchestratorはstatelessであるため実質的な可変状態が存在しない。限界を11.2節に明記済み |
| R-5 | `root.orchestrator._image_generator._api_key`という経路でsecretへ到達しうる | 低 | Pythonのprivate慣習の限界であり、v6.14が既に持つ性質。Public APIとして露出しないことを保証し、限界を17章 S-10に明記済み |
| R-6 | 「予定MIME」と「実際MIME」の乖離（将来の他provider） | 低 | v6.11では構造的に不一致が起こらないことを15.4節で実証。将来のproviderに対する権威は実際値である旨を明記し、OQ-1として記録 |
| R-7 | `is_available()`という命名が、実際には「Gateが有効か」を意味することによる誤解 | 低 | `WordPressOutput.is_available()`（credential有無）とは判定内容が異なる。ただし「この出力／機能を使ってよいか」という利用側の意味は同一であり、precedentとして妥当。14.2節で条件を明示する |
| R-8 | ~~テストが`sys.modules`の状態に依存する（`IMPORT-`系）~~ | — | **Amendment 1（F-2対応）でResolved**。openai未import確認をclean subprocessによる決定的検証へ置き換え、テストプロセス自身の`sys.modules`状態への依存とskip規定を撤廃した（20.2節(1)）。Deferred Item・既知riskからは除外する |
| R-9 | `repr(dataclasses.asdict(root))`の安全性が内部dependency（v6.9／v6.11／v6.12／v6.14）のdefault object repr維持へ依存し続ける | 低 | `field(repr=False)`（Amendment 1、17.3節）は`repr(root)`／`str(root)`を構造的に保護するが、`asdict()`はdataclassの`__repr__`を経由しないためこの保護が及ばない（17.4節で実測確認済み）。本Release自身は`asdict()`を呼び出さず、安全なserialization手段として扱わない（S-11）ことで、この残存依存を「誤って安全と主張する」形にしない。回帰検知（20章SEC-系）で継続監視する |

---

## 24. Alternatives Considered

本文中で比較した主要な代替案を再掲する。

| 論点 | 採用 | 主な不採用案と理由 |
|---|---|---|
| package名（8.1節） | `article_featured_media_composition` | `publish_composition`＝scopeより広い／`image_composition`＝既存接頭辞から乖離 |
| immutability（11.2節） | `frozen=True` | 通常class（`RetryCompositionRoot`型）＝画像系precedentに劣後、不変条件を守れない |
| Protocol追加（11.6節） | 追加しない | capability Protocol新設＝speculative generality／`AIImageGenerator`拡張＝破壊的変更 |
| 無効時の表現（12章） | `None`＋`is_available()` | Null Object＝`apply()`の戻り値決定がFallback Policyの先取りになる |
| Gate ON＋設定不備（13.3節） | Fail Fast（無変換伝播） | Fail Closed＝設定ミスの不可視化／Domain Error＝情報損失・API面積増 |
| MIME解消（15章） | v6.11に`output_mime_type` property追加 | 独立config化＝v6.15 Non-Goal違反／v6.16変更＝破壊的／v6.14変更＝破壊的かつscope逸脱 |
| v6.16／v6.17の扱い（10.3節） | Runtime側に残す | Composition Rootが関数参照を公開＝構築対象がなく責務外 |
| 公開属性（11.4節） | `orchestrator`／`image_mime_type`の2件 | `enabled`公開＝`is_available()`と冗長／adapter個別公開＝orchestrator迂回を誘発 |
| `orchestrator`のrepr方針（17.3節、Amendment 1） | `field(repr=False)` | 現行の自動repr維持（案B）＝内部dependencyの将来のrepr変更に安全性が依存し続ける／custom `__repr__`の自作＝`field(repr=False)`のみで目的を達成できるため不要な保守コストを増やす |
| openai未import検証手段（20.2節、Amendment 1） | clean subprocessによる決定的検証 | 同一プロセス内`sys.modules`検査＋条件付きskip＝`MIME-`Scenarioとの実行順序依存を生み、Formal RegressionのPASS件数が不安定になる（Architecture Review 1 Finding F-2） |
| network遮断層（20.2節、Amendment 1） | `socket.getaddrinfo`／`socket.socket.connect`の低レベル遮断 | `requests.post`／`requests.request`のみの遮断＝`requests.sessions.Session.request`経由の呼び出しを捕捉できず、urllib／http.client等の別経路も網羅できない |

---

## 25. Acceptance Criteria

```text
AC-1   src/article_featured_media_composition/ が新規作成され、
       __all__ が ["ArticleFeaturedMediaCompositionRoot"] のみである

AC-2   ArticleFeaturedMediaCompositionRoot が @dataclass(frozen=True) であり、
       fields() で得られる field が orchestrator・image_mime_type の2件のみである
       （orchestrator は field(repr=False) が付与されているが、fields() には
        引き続き含まれる。17.3節・17.4節、Amendment 1でF-1対応として追加）

AC-3   from_env() が classmethod として存在し、引数を取らない

AC-4   is_available() が「orchestrator is not None」と完全に一致し、
       例外を送出せず、副作用を持たない

AC-5   Gate OFF 時、from_env() が例外なく成功し、
       orchestrator is None かつ image_mime_type is None かつ is_available() == False となる

AC-6   Gate OFF 時、AI_IMAGE_GENERATION_ENABLED 以外の環境変数を一切読まない

AC-7   Gate ON ＋ 全credential設定時、from_env() が成功し、
       orchestrator が apply を持ち、image_mime_type が非空strとなる

AC-8   Gate ON ＋ credential不足時、既存factoryの ValueError が
       無変換で伝播し、インスタンスが返らない

AC-9   OpenAIImageGenerator に read-only property output_mime_type が追加され、
       generate() が返す GeneratedImage.mime_type と常に一致する

AC-10  Composition Root module 内に MIME 文字列リテラルが1つも存在しない
       （Single Source of Truth が v6.11 内に維持されている）

AC-11  本パッケージが例外を捕捉・変換しない（AST検証で ast.ExceptHandler が0件。
       Amendment 1でF-6対応としてast.Tryから変更——try/finallyは例外を捕捉せず
       cleanupのみ行う正当な構文であるため一律禁止しない）。また ast.Raise が
       __post_init__ 内のINV-1〜INV-3検証3種以外に存在しない

AC-12  本パッケージが新規例外型・新規Protocolを定義しない

AC-13  __post_init__ が INV-1〜INV-3 を検証し、
       固定message完全一致で ValueError／TypeError を送出する

AC-14  本パッケージが 10.3節の禁止import を1件も行わない（AST検証）

AC-15  main.py／image_resolver.py／outputs／pipeline／scripts のいずれも
       本パッケージを参照しない（静的検証）

AC-16  from_env() が openai を import せず、HTTPリクエスト（socket.getaddrinfo /
       socket.socket.connect を含む）を1本も発生させない。openai未import確認
       （20.2節(1)）はclean subprocessによる決定的検証で行い、network遮断確認
       （20.2節(2)）はそれとは独立したtest本体プロセス内でのin-process検証で
       行う（Architecture Review 2 Finding-3対応でこの区別を明確化）。
       いずれも実行順序・環境状態に起因するskipを伴わない（Amendment 1でF-2
       対応として全面改訂。20.2節(1)(2)、D-B1〜D-B3）

AC-17  module import だけでは環境変数を読まず、外部接続も発生しない

AC-18  repr(root)・str(root) のテキスト表現には、API key／app password／
       環境変数の「値」がいずれも含まれない（field(repr=False)により構造的に
       保証される。17.3節）。本Releaseが送出する例外message（固定4種、11.5節）
       にも同様に含まれない。
       なお dataclasses.asdict(root) は secret-safe な serialization手段では
       ない（S-11）。asdict(root) は非dataclass field を deepcopy するため、
       戻り値の内部構造には secret-bearing dependency の複製が含まれ得る。
       repr(dataclasses.asdict(root)) のテキスト表現についても、現時点では
       secret文字列が含まれないことをrepr回帰検知（AC-23）で確認するが、
       これは v6.9／v6.11／v6.12／v6.14 が default object repr を維持して
       いることに依存した確認であり、field(repr=False) による構造的保証の
       対象外である（Amendment 1でF-1対応として全面改訂。17章参照）

AC-19  v6.9〜v6.17 の既存 Public API が1件も変更・削除されていない
       （追加は v6.11 の output_mime_type のみ）

AC-20  .env.example・requirements.txt が無変更である

AC-21  新規E2Eが全件PASSし、Formal Regression（既存20ファイル＋新規1ファイル）が
       全件PASSする（FAIL 0・Traceback 0・外部API実接続 0）

AC-22  READINESS- Scenario（20.4節）により、Gate ON＋ダミーcredentialで
       構築したComposition Rootが、外部接続を発生させずに次を満たすことを
       検証可能な形で確認する：is_available() is True／image_mime_type が
       非空str／construct_article_image_prompt() がstrを返す／
       generate_image_filename(title, image_mime_type) がValueErrorを送出
       せずstrを返す／orchestrator.apply が callable／apply() 自体は呼び
       出さない。これはRuntime Wiringの実装ではなく、既存Foundation群が
       後続Runtime Wiringへ進める型・Contract上の準備状態（composition
       readiness）の検証である（Amendment 1でF-5対応として全面改訂。
       Architecture Review 1案A採用、WIRE-ではなくREADINESS-を使用）。
       construct_article_image_prompt（v6.17）・generate_image_filename
       （v6.16）をimportして呼び出すのはtest code自身であり、
       ArticleFeaturedMediaCompositionRoot（Production Code）はこれらを
       importしない（10.3節。Architecture Review 2 Finding-4対応で
       この境界をREADINESS- Scenario定義へ明記した）

AC-23  ダミーsecretでGate ON構築したrootに対し、repr(root)・str(root)・
       repr(dataclasses.asdict(root)) のいずれのテキスト表現にもダミー
       secret文字列が含まれないことを回帰検知する（Amendment 1でF-7対応
       として新規追加。20.4節 SEC-）。field(repr=False)採用後も、
       asdict()経路の残存依存（17.4節）に対する継続的な安全確認として
       維持する
```

---

## 26. Deferred Items（Future Candidates）

| # | 項目 | 内容・着手条件 |
|---|---|---|
| DI-1 | **Image Generation Fallback Policy** | 画像生成・Upload失敗時に記事投稿を継続するか中止するかの業務判断。**本Releaseの直後に実施すべき次候補**。Null Orchestratorの導入可否もこのReleaseで決まる（12.2節） |
| DI-2 | generator capability Protocol（provider非依存のMIME公開） | Providerが2件目に達した時点で`ai_image_generation`へ追加する（15.5節 案2） |
| DI-3 | Article Featured Media Orchestration v2（filename内部生成） | `apply()`のsignature変更を伴う破壊的変更。実際にfilename事前構築が運用上の問題を起こした場合にのみ検討する（15.5節 案5） |
| DI-4 | Article Featured Media Runtime Wiring | DI-1完了後。`main.py`への接続（15.6節の4行＋例外処理＋ログ＋集計） |
| DI-5 | observability／logging contract | 本Releaseはlog出力を行わない（N-13）。Runtime Wiring時に、画像生成の成否をどこに記録するか（`ArticleLogEntry`拡張等）を検討する |
| DI-6 | Media Upload Retry／Idempotency Foundation | `RetryQueueItem`にmedia_id相当fieldが存在しないことを踏まえ独立検討。Runtime Wiringの実運用観測後 |
| DI-7 | WordPress Unused Media Cleanup Foundation | `WordPressMediaUploader`に削除APIが存在しないことを踏まえ独立検討。Runtime Wiringの実運用観測後 |
| DI-8 | Publish Composition Root Foundation（publish全体版） | 本Releaseが画像スコープに限定したもの（N-16）。`main.py`全体のdependency構築を専用classへ移す構想。本Releaseの成功を前提に再検討する |
| DI-9 | **Image Generation Gate Value Strict Validation**（Amendment 1、F-3対応で新規追加。Documentation Integration工程でDI-10からDI-9へ繰り上げ、Architecture Review 2 Finding-5対応） | `AI_IMAGE_GENERATION_ENABLED`の値検証を、v6.15の現行Fail Closed規則（不正値は静かにGate OFF、13.6節 Inherited Limitation）から、許可値のallowlist化・不正値での例外送出（Fail Fast化）へ厳格化する構想。v6.15のPublic Contract変更にあたるため、独立したArchitecture Reviewを要する。本Release（v6.18.0）では着手しない |

---

## 27. Open Questions

本設計で解決できなかった事項のみを記載する。いずれも選択肢・推奨案・判断材料を提示する。
実装者判断へ丸投げしない。

### 27.0 Amendment 1によるOpen Question／Deferred Item整理

Architecture Review 1の指摘を受け、Production Implementationを阻害する未決事項が
残っていないことを次のとおり確認する。

```text
1. Fail Fast Construction Contractは確定事項である
   → 「変更してはいけない確定事項」（Amendment依頼冒頭）に明記のとおり、
     13.3節のFail Fast採用はArchitecture Review 1で妥当性確認済みであり、
     本Amendmentで再設計しない。OQ-2は「Composition Root自身がFail Fastか
     否か」を問うものではなく、「Runtime Wiring側がその例外を捕捉するか」
     という別階層の問いに限定される（下記2）

2. Runtime Wiring側が例外を捕捉するかは Fallback Policy Release（DI-1）へ延期
   → OQ-2 (b) の推奨に明記済み。本Releaseはこれを決定しない

3. 別providerへの対応は延期
   → Deferred Item DI-2（15.5節・26章）。OQ-1でも言及

4. Gate値の厳格化は延期
   → Deferred Item DI-9（13.6節 Inherited Limitation・26章、Amendment 1で新規追加、
     Documentation Integration工程でDI-10からDI-9へ繰り上げ）

5. 内部dependencyのrepr変更時はSecurity Contractの再検証が必要
   → これは「未決の判断」ではなく「継続監視の対象」として整理する。
     field(repr=False)採用（17.3節）によりrepr(root)／str(root)は内部
     dependencyのrepr実装から構造的に独立したため、再検証が必要な範囲は
     asdict()経路（repr(dataclasses.asdict(root))）のみに縮小した（17.4節）。
     この残存範囲は Risk R-9（23章）として記録し、AC-23のrepr回帰検知
     Scenario（20.4節 SEC-）により継続的に監視する。新たなOpen Questionとして
     未決のまま残す事項はない

6. MIMEの実際値と予定値が将来乖離する場合の検出は延期
   → OQ-1に記載済み。v6.11では構造的に乖離が起こらないことを15.4節で実証済み
```

以上により、本Releaseの Production Implementation を妨げる未決事項は残っていない。
以下のOQ-1〜OQ-3は、いずれも本Releaseの実装判断を妨げるものではなく、将来Release
（Runtime Wiring・Fallback Policy・別provider対応等）の検討材料として記録するもので
ある。

### OQ-1：予定MIMEと実際MIMEが乖離した場合の権威と検出責務

```text
選択肢:
  (a) 実際値（GeneratedImage.mime_type）を常に権威とし、乖離検出は行わない
  (b) Runtime Wiring が乖離を検出し、実際値でfilenameを作り直す
  (c) v6.14 orchestrator が乖離を検出して例外を送出する（＝破壊的変更、DI-3）

推奨: (a)
理由: v6.11では構造的に乖離が起こらないことを15.4節で実証済みであり、
      現時点で検出機構は死んだコードになる。
      乖離は複数provider時にのみ現実の問題となるため、DI-2と同時に再検討するのが自然。

判断に必要な情報:
  ・2件目のproviderを導入する時期の見込み
  ・WordPress側がfilenameの拡張子とContent-Typeの不一致をどう扱うか
    （拡張子とMIMEが食い違ったMedia Uploadの挙動）。
    本Releaseでは外部接続を行わないため未検証。
```

### OQ-2：Fail Fastが将来のRuntime Wiring時に利用者へ与える影響の許容可否（**業務判断**）

```text
状況:
  本設計（13.3節）により、AI_IMAGE_GENERATION_ENABLED=true かつ
  OPENAI_API_KEY 未設定の状態で Runtime Wiring 後の main.py を実行すると、
  記事生成が始まる前に ValueError で停止する。

選択肢:
  (a) 許容する（Fail Fast のまま）
        利用者は「なぜ画像が出ないのか分からない」状態に陥らず、
        原因（どの環境変数が欠けているか）が即座に分かる
  (b) Runtime Wiring 側で捕捉し、警告表示のうえ画像なしで続行する
        → これは Fallback Policy（DI-1）の決定事項であり、
          Composition Root の設計を変えずに実現できる
  (c) 本Releaseで Fail Closed へ変更する

推奨: (a)＋(b) の組み合わせ
理由: Composition Root は Fail Fast のまま（本Release）とし、
      「捕捉して続行するか」は Fallback Policy Release（DI-1）が決める。
      この分離により、本Releaseで業務判断を先取りしない。
      (c) は 13.3節 FF-1〜FF-6 の理由により不採用。

判断に必要な情報:
  ・利用者（本Repositoryのオーナー）が、画像生成を有効化した状態で
    APIキー未設定のまま実行する運用を想定するか
  ・起動時停止と「画像なしで静かに続行」のどちらが望ましいか
→ Architecture Review で明示的に確認すること。
```

### OQ-3：`is_available()`の命名が`WordPressOutput.is_available()`と判定内容が異なる点

```text
状況:
  WordPressOutput.is_available()  → credential 3点の有無を判定
  本Release is_available()        → Gate ON/OFF を判定（credential不足時は例外が先に出る）

選択肢:
  (a) is_available() のまま（precedent命名を優先）
  (b) is_enabled() へ改名（判定内容の正確さを優先）
  (c) 両方を提供する

推奨: (a)
理由: 呼び出し側から見た意味（「この機能を使ってよいか」）は両者で同一であり、
      OutputManager.save_all() の skip pattern と同じ形で利用できる。
      (c) は Public API 面積を増やし、11.4節の最小化方針に反する。

判断に必要な情報:
  ・Architecture Review 担当が、命名の一貫性と判定内容の正確さのどちらを重視するか
```

---

## 28. Review Checklist（Architecture Designセルフレビュー）

```text
[x] Release名とScopeが一致しているか
      → 一致。「Composition Root Foundation」の名のとおり、構築と公開のみを担い、
        実行・判断・配線を含まない（9章）

[x] Repository Survey確定事項1〜9をすべて反映したか
      → 1: 8.1節（package名）・N-16／2: 1章／3: 2章／4: 7章 PR-1〜PR-4／
        5: 2章 P-1〜P-8・9章／6: 5章・18章／7: 5章 N-5・N-8〜N-11／
        8: 2章 P-9・15章／9: 15.1節で6案を比較のうえ正式決定

[x] 実ファイル・symbol・行番号を根拠にしているか（推測を含まないか）
      → 3章がすべて実読に基づく。タスク指示の
        src/generated_image_wordpress_media_upload/ が実在しないことも指摘済み（3.1節）

[x] Composition Rootの責務6点に限定されているか
      → 9章 R-1〜R-6。それ以外はN-1〜N-16として明示的に除外

[x] Fallback Policyが混入していないか
      → 混入なし。12.2節でNull Objectを不採用とした理由が、
        まさに「Fallback Policyの先取りを避けるため」である

[x] retry／idempotency／cleanup／rollbackが混入していないか
      → N-8〜N-11で除外。DI-6・DI-7へ送った

[x] Runtime Zero Diffが維持されるか
      → 18章。変更Production Codeは新規2ファイル＋v6.11への追加1件のみ

[x] 破壊的変更を含まないか
      → 19章。追加のみ。変更・破壊的変更はゼロ

[x] Public APIが最小限か
      → 11.4節。公開属性2件＋method 2件（from_env／is_available）＋自動__init__

[x] Gate OFFとGate ON＋設定不備が区別されるか
      → 13.4節。インスタンスの存在自体が両者を分ける

[x] secretを保持・露出しないか
      → 17章 S-1〜S-11。直接保持しないが間接保持することを正確に明記し
        （17.1節・S-1）、repr(root)/str(root)はfield(repr=False)で構造的に
        保護（17.3節・S-2）、asdict()は非secret-safeであることを明記（S-11）。
        残存する限界（S-10・17.4節）もAmendment 1で正確化（F-1対応）

[x] import時・構築時に外部接続しないか
      → 3.3節で実証、17章 S-7〜S-9でContract化、20.2節でsubprocess＋socket遮断
        による決定的検証方法を定義（Amendment 1、F-2対応）

[x] 新規business logicを追加していないか（PR-4）
      → 追加なし。既存from_env()への委譲と、不変条件検証のみ

[x] MIME決定が「最小変更だから」ではなくContractとして自然か
      → 15.3節。SSOTがv6.11内に維持され、Composition RootはMIMEを「決定しない」。
        6案すべてを8観点で評価したうえでの選択（15.1節）

[x] 未確定事項を実装者判断へ丸投げしていないか
      → Open Questionは3件のみ。いずれも選択肢・推奨案・判断材料を明記（27章）

[x] Test Strategyが外部接続ゼロで全Contractを検証できるか
      → 20章。17 prefix。Scenario数は結果値として報告し目標値として固定しない
        （Amendment 1、F-8対応）。外部接続ゼロの保証方法をclean subprocess＋
        socket低レベル遮断としてskipなしで20.2節に明記（Amendment 1、F-2対応）

[x] Acceptance Criteriaが検証可能な形か
      → 25章 AC-1〜AC-23。すべてテストまたは静的検査で客観的に判定可能
        （AC-18のrepr／asdict区別、AC-22のREADINESS-化はAmendment 1で対応）

[x] 本工程で設計書1ファイル以外を変更していないか
      → 変更なし（Architecture Design時・Architecture Amendment 1時の
        いずれもgit statusにより確認する。最終報告13章参照）
```

---

## 29. Review History

```text
2026-07-21  Repository Survey 実施（読み取り専用）
              → 次Release候補5件＋追加1件を比較し、
                Publish Composition Root Foundation（画像スコープ限定）を第一推奨として選定

2026-07-21  Architecture Design（本文書）作成
              → Architecture Review 1 未実施

2026-07-21  Architecture Review 1 実施
              判定: Changes Required
              Blocking: 0 / Major: 2 / Minor: 3（実装前修正必須） / Suggestion: 4 /
                        Informational: 多数

              Major:
                F-1  Security Contractの事実誤認（S-1「secretを保持しない」の
                     不正確な表現、S-10「いずれもprivate属性」の事実誤認——
                     WordPressMediaUploader.app_passwordはpublic属性）と
                     AC-18の非決定性（asdict()の判定基準未定義）
                F-2  Test Strategy内部矛盾（MIME- Scenarioのgenerate()実行が
                     IMPORT- Scenarioのsys.modules前提を破壊し、skip規定により
                     AC-16が系統的に検証不能になる）

              Minor（実装前修正必須）:
                F-3  Gate値typo（例: "ture"）がv6.15 Fail Closedにより静かに
                     Gate OFFへ落ちる非対称性（credential不足はFail Fast）が
                     Inherited Limitationとして未明記
                F-4  is_available()の保証範囲（構築済み状態のみを保証し、
                     外部API成功やapply()成功を保証しないこと）が未定義
                F-5  AC-22「設計書上で追跡できる」が客観的判定基準を欠く

              Suggestion:
                F-6  AC-11のast.Try==0がtry/finallyまで禁止する過剰固定
                F-7  内部dependencyの将来repr変更に対する回帰検知手段の不足
                F-8  Scenario数上限（約60〜75）が本体規模に対し過大な可能性
                F-9  §14.2「常に成立する」がPublic constructor経由にも及ぶ
                     全域的主張として誤読されうる

              Architecture本体（package構成・Public API骨格・dependency graph・
              Gate Contract・Fail Fast判断・MIME解決案1・Null Object不採用・
              Runtime Zero Diff方針）は妥当と判定され、変更を要しない。

2026-07-21  Architecture Amendment 1 実施（本工程）
              → Architecture Review 1のF-1〜F-9すべてに対応。
                Architecture本体の確定事項（Single Source of Truth冒頭に列挙）は
                一切変更していない。Production Code・test code・Runtimeへの
                変更は行っていない（対象は本設計書1ファイルのみ）。

              主要Decision:
                D-A   AC-22 → 案A採用。READINESS- Scenario（20.4節）へ検証可能化
                D-B1  openai未import確認 → clean subprocessによる決定的検証へ変更
                      （20.2節(1)）。skip規定を撤廃
                D-B2  network遮断層 → socket.getaddrinfo / socket.socket.connect
                      の低レベル遮断を採用（20.2節(2)）
                D-B3  新規v6.18 E2Eはskipを一切用いない（正式Inventoryの全Scenario
                      がPASSまたはFAILへ確定する）
                D-C   repr方針 → 案A（field(repr=False)）を採用（17.3節）。
                      repr(root)/str(root)を内部dependencyの将来のrepr変更から
                      構造的に分離。ただしasdict()経路には及ばないという限界を
                      17.4節で明示し、Risk R-9・AC-23（repr回帰検知）で継続監視

              F-3対応: 13.6節 Inherited Limitation新設、Deferred Item DI-10追加
                       （後日Documentation Integration工程でDI-9へ繰り上げ）
              F-4対応: 14.4節新設（is_available()保証範囲）、
                       16章 E-18追加（precondition違反時の扱い）
              F-6対応: AC-11・DEP- ScenarioをAST検証 ast.Try→ast.ExceptHandlerへ変更
              F-8対応: 「約60〜75 Scenario」等の固定数値記述を削除し、
                       AC被覆・重複排除を条件とする結果値扱いへ変更
              F-9対応: 14.2節を「from_env()が正常に返したインスタンスに限り
                       成立する」へ限定

2026-07-21  Architecture Review 2 実施
              判定: Approved with Suggestions
              Blocking: 0 / Major: 0 / Minor: 2（実装前修正必須ではなく、
                        Production Implementation／Documentation Integration時の
                        軽微な追記で解消可能と判定） / Suggestion: 4 /
                        Informational: 多数

              F-1〜F-9はすべて解消済みと判定された（field(repr=False)の
              eq/hash/fields()件数/frozen/必須引数性への非影響を独立実測で
              再現確認、subprocess+socket遮断の決定性を確認）。

              Minor（実装前修正必須ではない、既にProduction Implementation時に
              テストfile docstringへ反映済み）:
                Finding-4  READINESS-Scenarioの境界説明不足
                           → 20.4節 READINESS-行・25章 AC-22へ明記して解消
                Finding-5  DI-9欠番の説明が設計書内に不在
                           → 本Amendmentでは対応せず、Documentation Integration
                             引継ぎ事項として保持（下記参照）

              Suggestion（4件）:
                Finding-1  §17.2 S-11の「未実行インスタンス」限定の暗黙性
                Finding-2  Python executable選択（venv/Scripts/python.exe）の
                           根拠不記載
                Finding-3  §20.2(2) network遮断の実行context（in-process／
                           subprocess）の不明示
                           → Production Implementationで20.2節(2)・AC-16・
                             20.4節IMPORT-行へ明記して解消
                Finding-6  §5 N-13の cross-reference誤り（「19章参照」→
                           正しくは17章）
                           → Documentation Integration引継ぎ事項として保持

              Architecture本体（package／class／field名・数／constructor引数／
              from_env()／is_available()／dependency graph／Gate Contract／
              Fail Fast／MIME案／None採用／Runtime Zero Diff／In・Out of Scope）
              は変更されていないことを§7〜10の再読により確認。

2026-07-21  Production Implementation 実施（本工程）
              → 承認済みArchitectureに従いProduction Codeと新規E2Eを実装した。

              作成・変更ファイル（4件）:
                新規  src/article_featured_media_composition/__init__.py
                新規  src/article_featured_media_composition/
                      article_featured_media_composition_root.py
                新規  tests/test_e2e_v6_18_0_
                      article_featured_media_composition_root_foundation.py
                追加  src/openai_image_generation/openai_image_generator.py
                      （output_mime_type property追加のみ、純追加9行diff）

              実装内容:
                ・field(repr=False)をorchestrator fieldへ実装。実測で
                  repr(root)/str(root)からorchestratorが除外され、fields()は
                  2件のまま、必須引数性・eq・hash・frozen enforcementに
                  影響しないことを確認
                ・output_mime_type propertyをv6.11へ追加。
                  _MIME_TYPE_BY_OUTPUT_FORMATを唯一のSSOTとして委譲するのみで
                  MIME文字列リテラルを重複記述しない
                ・from_env()の構築順序（Gate判定 → OpenAI → MIME取得 →
                  WordPress → 接続層 → orchestrator）を実装どおり実測確認
                ・Gate OFF時はAI_IMAGE_GENERATION_ENABLED以外の環境変数を
                  一切読まないことを実測確認（os.getenvの呼び出しtrackingで
                  検証）
                ・Gate ON＋設定不備時、既存factoryのValueErrorが無変換で
                  伝播し、固定messageが完全一致することを実測確認
                ・__post_init__のINV-1〜INV-3を実装し、4種の固定message
                  （ValueError×3・TypeError×1）が設計書と完全一致することを
                  実測確認
                ・clean subprocessによるopenai未import決定的検証、および
                  test本体プロセス内でのin-process socket遮断（Finding-3の
                  明確化を反映）を実装
                ・READINESS-Scenarioにv6.16／v6.17をtest code自身が直接呼び出す
                  旨の境界注記を実装（Finding-4対応）

              新規E2E結果:
                tests/test_e2e_v6_18_0_
                article_featured_media_composition_root_foundation.py
                146 Assertion、146/146 PASS、0 FAIL、exit code 0、skip 0件

              focused v6.11 regression結果:
                tests/test_e2e_v6_11_0_openai_image_generation_adapter_foundation.py
                （無改修で実行）248 Assertion、248/248 PASS、0 FAIL、exit code 0
                → output_mime_type追加が既存v6.11 Contractを一切破壊していない
                  ことを確認（RZ-3充足）

              Runtime Zero Diff: main.py・image_resolver.py・outputs／
              pipeline／scripts配下の全ファイルが本Releaseの新規packageへ
              一切参照していないことをRUNTIME-Scenarioで確認。

              外部接続: OpenAI／WordPressへの実接続は本工程を通じて0件
              （ダミーcredential・FakeClientのみ使用）。

              Documentation Integrationへの引継ぎ事項（本工程では対応不要
              と判定）:
                ・Finding-5：DI-9欠番の説明を設計書内へ追加する
                  （§26 Deferred Items一覧、またはDI-10→DI-9への繰り上げ）
                ・Finding-6：§5 N-13の「19章参照」を「17章参照」へ訂正する
                ・Finding-1／Finding-2：軽微な文言追記（それぞれ17章・20章）

              Code Review 未実施。

2026-07-21  Code Review 実施
              判定: Approved with Suggestions
              Blocking: 0 / Major: 0 / Minor: 3（Formal Regression前必須ではなく、
                        いずれもDocumentation Integrationまで延期可能と判定） /
                        Suggestion: 2 / Informational: 多数

              Reviewerは会話報告を鵜呑みにせず、field(repr=False)のeq/hash/
              fields()件数/frozen/必須引数性への非影響、AST Guardの陽性対照
              （openai_image_generator.pyに対しExceptHandler 4件・
              __post_init__外Raise 18件を検出することでGuard自体の実効性を確認）、
              socket sentinelの陽性対照（実際にAssertionErrorが発火することを確認）、
              Runtime Zero Diff走査33ファイルの実測（ディスク実態と完全一致）、
              Repository全体grepによる新規package参照元の独立確認（自パッケージ・
              新規E2E・設計書の4ファイルのみ）を、いずれも独立に再実行して検証した。

              Minor（3件、Formal Regression前必須ではない）:
                F-1  Production Implementation報告および設計書の「変更ファイル
                     4件」が誤り（本設計書自身を含め実際は5件）
                F-2  Gate OFF env非読取り検証（SEQ-GATE-OFF-ENV-ISOLATION）が
                     os.getenvのみをtrackingしており、credential factory
                     （OpenAIImageGenerator／WordPressMediaUploader）が用いる
                     os.environ.get経路を直接観測できない。ただしcredential
                     factory誤到達はGATE-OFF-NO-EXCEPTIONが間接的に検出するため、
                     AC-6はPASSでありProduction Code欠陥ではない
                F-3  INV-2のedge case（apply属性が存在するが非callable）が
                     新規E2E未カバー。Production Codeは正しくTypeErrorを
                     送出することをReviewer probeで確認済み

              Suggestion（2件）:
                F-4  IMPORT subprocess envでOPENAI_IMAGE_TIMEOUT_SECONDSを
                     明示除去していない（親環境汚染probeで実害なしを実証済み）
                F-5  socket patch適用のtry内移動・ENV-ISOLATION-RESTOREDの
                     ラベル精度・DEP-静的import限定の明記、の3点の軽微な
                     test改善候補

              新規v6.18 E2E再実行: 146/146 PASS（Reviewer独立実行、変更なしを確認）
              focused v6.11 regression再実行: 248/248 PASS（Reviewer独立実行）

              Code Review 2: Not Required。Formal Regressionへ進行可能と判定。

2026-07-21  Formal Regression 実施
              判定: Passed

              正式Regression Inventoryを、単純なtests/test_e2e_*.py全件glob
              ではなく、docs/CHANGELOG.mdのv6.14.0〜v6.17.0各Entryが記録する
              「累積Regression Inventory方式」の precedent に基づいて確定した
              （v1.11.0・v5.9.0・v6.0.0〜v6.17.0の既存20ファイル＋v6.18.0新規
              1ファイル＝21ファイル）。

              結果:
                対象ファイル数: 21（全件PASS、FAILファイル0）
                総Assertion: 2790（既存20ファイル 2644 ＋ v6.18新規146）
                総PASS: 2790 ／ 総FAIL: 0
                warning: 0 ／ skip: 0
                exit code非0のファイル: 0 ／ 実行不能ファイル: 0
                外部API実接続: 0件
                総実行時間: 17秒
                Git状態: Formal Regression前後で完全不変

              事前期待値（21ファイル・総Assertion 2790）と実測値は完全一致した。

              tests/test_e2e_*.pyの実在総数は70ファイルであり（71ではない）、
              正式Inventory21ファイルを除く49ファイルはCHANGELOG記録上の
              累積Inventoryに含まれてこなかった既存precedentに従い対象外とした。

              画像系直近Release（v6.14〜v6.17）は無改修のまま全件PASSし、
              v6.18の新規package・v6.11変更（output_mime_type property追加）が
              既存Public APIを一切破壊していないことを確認した。

              Documentation Integrationへ進行可能と判定。

2026-07-21  Documentation Integration 実施（本工程）
              → 正式設計書・ROADMAP.md・architecture.md・CHANGELOG.mdの4文書を
                実測値で整合させた。Production Code・test・Runtimeへの変更は
                行っていない。

              本文書（正式設計書）への反映事項:
                ・§0 Status：Code Review／Formal Regression／Documentation
                  Integrationの結果を反映し、Release Review：Not Startedへ更新
                ・変更ファイル数「4件」→「5件（本設計書自身を含む）」へ訂正
                  （F-1対応）
                ・§20.4 SEQ-の説明を精密化：os.getenv経路のみを直接trackingし、
                  os.environ.get経路はGATE-OFF-NO-EXCEPTIONによる間接検出に
                  委ねている旨を明記（F-2対応）
                ・§26 Deferred Items：DI-10をDI-9へ繰り上げ、本文参照
                  （13.3節・13.6節・27.0節・29章）をすべて整合（Finding-5対応）
                ・§5 N-13の「19章参照」を「17章参照」へ訂正（Finding-6対応）
                ・§17.2 S-11へ、検証対象rootがfrom_env()直後・apply()未実行の
                  状態に限定されること、および理論上の帰結（orchestratorが
                  statelessであるため`apply()`呼び出しの有無に関わらず`root`の
                  構造は不変）と実測範囲（apply()を実行する経路自体が本Release
                  に存在しないため未検証）を区別して明記（Finding-1対応）
                ・§20.2(1)へ、venv/Scripts/python.exeを明示指定する理由
                  （Repository正式実行契約への固定・system Pythonへの
                  すり替わり防止・Windows venv構成との一致・bare python
                  不使用の運用方針との整合）を追記（Finding-2対応）
                ・§29 Review History：Code Review・Formal Regression・
                  Documentation Integration実施記録を追加（本エントリ）

              F-3（INV-2 edge case未カバー）・F-4（subprocess env明示化）・
              F-5（socket patch位置等の軽微なtest改善）は、いずれもtest code
              変更を伴うため本工程（文書のみ変更）では対応せず、Release Review
              以降の改善候補として保持する。

              ROADMAP.md・architecture.md・CHANGELOG.mdへの反映内容は、
              各文書の当該節を参照。

              Release Review 未実施。

2026-07-21  Release Review 実施
              → Architecture／Production／Test／Documentation／Gitの
                全観点を独立に再検証した。判定：Approved with Suggestions
                （Blocking 0・Major 0・Minor 1・Suggestion 1）。
                Release Review 2：Not Required。Release Blocking Issue：0件。
                Production Codeの欠陥は検出されなかった。Runtime Zero Diff
                （main.py不変・Runtime Wiringなし・33ファイルGuard PASS）を
                再確認した。新規E2E 146/146 PASS、focused v6.11 248/248
                PASS（いずれも再実行し再確認）、Formal Regression
                21ファイル・総Assertion 2790・2790/2790 PASS・warning 0・
                skip 0・外部接続0（前回実行結果を再検証、再実行はせず）。
                Git状態：8件の物理ファイル（新規4・変更4）。

              RRF-1（Minor）：§17.2「S-11の限定範囲」の記述が、
              `ArticleFeaturedMediaOrchestrator`自身のstateless性から
              「`root`の構造はapply()呼び出しの有無に関わらず不変であり、
              S-11・17.4節の評価はapply()実行後にも理論上そのまま適用される」
              と過大に一般化していた点を指摘。実際には`root`が保持する
              `OpenAIImageGenerator`が初回`generate()`時に`openai.OpenAI`
              clientを`self._client`へ遅延キャッシュするため、`root`の
              到達可能object graphはapply()実行後に変化し、`asdict(root)`は
              生きたclientの`threading.RLock`により`TypeError`となり得る。
              本工程（Release Review反映）にて§17.2を訂正し、評価範囲を
              from_env()直後・apply()未実行の状態に限定する記述へ改め、
              apply()実行後の評価はDI-4（Runtime Wiring）へ委ねる旨を明記した。
              Security Contract本体（§17章の各表）は変更していない。
              本Findingは、本Releaseがapply()を呼び出す経路を一切持たない
              ため実害はないが、将来DI-4着手前に訂正すべきものと判定した。

              RRF-2（Suggestion）：§0 Statusブロックの「Code Review:」行の
              値開始位置が他の11行と1文字ずれていた点を指摘。半角スペース
              1個を削除し、列を揃えた。

              Code Review F-3（INV-2 edge case未カバー）・F-4（subprocess env
              明示化）・F-5（socket patch位置等の軽微なtest改善）は、
              引き続きtest改善候補としてDeferredのまま保持し、本工程では
              対応していない。

              本文書への反映事項:
                ・§0 Status：Release Review：Approved with Suggestions、
                  Release：Completedへ更新
                ・§17.2 S-11の限定範囲：RRF-1に基づき訂正
                ・§0 Status「Code Review:」行：RRF-2に基づき列揃え
                ・§29 Review History：本エントリを追加

              ROADMAP.md・architecture.md・CHANGELOG.mdへの反映内容は、
              各文書の当該節を参照。

              次工程：個別git add・commit・push。
```
