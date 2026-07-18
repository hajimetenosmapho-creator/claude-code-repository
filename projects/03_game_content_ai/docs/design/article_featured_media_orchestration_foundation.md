# Article Featured Media Orchestration Foundation — Architecture Design（v6.14.0）

作成日：2026-07-18
作成者：Claude Code（Architecture Designドラフト／Architecture Review／Non-Blocking Finding修正／Production Implementation／新規E2E作成／Code Review／Formal Regression／Documentation Integration／Release Review）／ChatGPT（Architecture Review確認・Code Review確認・Release Review確認：未実施）／ユーザー（最終承認：未実施）
状態：**Release Review実施済み（結果は0章Header参照）**
分類：**Architecture Release**（development_workflow.md 6章・7章。新規独立package・新規Public API・新規Dependency方向の確立を伴うため）

---

## 0. Header

```text
Release：6.14
Version：v6.14.0
正式名称：Article Featured Media Orchestration Foundation
Classification：Architecture Release
Status：Release Completed（Release Review Approved）
Architecture Design：Completed（本文書）
Architecture Review状態：Approved（Claude Codeによる独立Review。初回Changes
    Required：Critical 0・Major 0・Minor 9件（AR14-m-1〜AR14-m-9）・
    Suggestion 1件（AR14-S-1）、いずれもNon-Blocking Finding修正工程で
    本文書へ反映済み。再Review：Approved、Critical/Major/Minor/Suggestion
    いずれも0件、Blocking Issueなし）
Production Implementation：Completed（25.1節。新規package
    `src/article_featured_media_orchestration/`2ファイル、Architecture
    Designからの逸脱なし）
New E2E：PASS（26.11節。217/217 PASS、0 FAIL、終了コード0）
Code Review状態：Approved with Suggestions（Claude Codeによる独立Review。
    Critical 0・Major 0・Minor 0・Suggestion 1件（CR14-S-1、Non-Blocking、
    未反映のまま記録）、Blocking Issueなし）
Formal Regression状態：PASS（28.1節。正式対象17ファイル、既存16ファイル
    2054/2054 PASS＋新規v6.14.0 217/217 PASS＝総合2271/2271 PASS、FAIL 0・
    Warning 0・終了コード非0 0、Blocking Issueなし）
Documentation Integration状態：Completed（29.1節。ROADMAP.md／
    architecture.md／CHANGELOG.mdへ反映済み。Historical Record変更なし、
    CR14-S-1はNon-Blockingのまま維持、Blocking Issueなし）
Release Review状態：Approved（Claude Codeによる独立Review。初回Changes
    Required：Critical 0・Major 0・Minor 2件（RR14-m-1・RR14-m-2、いずれも
    本文書冒頭・末尾の状態表記が最新フェーズを反映していなかった文書
    staleness、Production／E2E／Contractへの影響なし）、Suggestion 0件
    （CR14-S-1はCode Review由来の既存記録として維持、Release Review自体の
    新規Suggestionではない）。Non-Blocking Finding修正工程で本文書へ反映済み。
    再Review：Approved、Critical/Major/Minor/Suggestionいずれも0件、
    Blocking Issueなし）
Release：Completed（37章 Review History参照）
```

本文書はArchitecture Design・Architecture Review・Production Implementation・Code Reviewフェーズの成果物である。Formal Regression・既存統合文書更新（ROADMAP.md／architecture.md／CHANGELOG.md）・commit・pushのいずれも行っていない。

---

## 1. Purpose

Release 6.9.0〜6.13.0で追加された次の4つのConsumer-less Foundationを、決まった順序で呼び出す単一のOrchestratorへ束ねる。

```text
AIImageGenerator.generate(prompt)                         （ai_image_generation, v6.10.0 Contract）
GeneratedImage → WordPress Media Upload capability.upload() （generated_image_wordpress_media, v6.12.0 相当）
bind_featured_media(article, media_result)                （article_featured_media, v6.13.0）
```

本Releaseが確立するのは、次の純粋な呼び出し順序Contractのみである。

```text
ArticleData
prompt
filename
    ↓
ArticleFeaturedMediaOrchestrator.apply(article, prompt, filename)
    ↓
featured_media_idが設定された新しいArticleData
```

## 2. Background

- `docs/ROADMAP.md:779-786`は、v6.13.0完了直後の次候補として「Article Featured Media Runtime Wiring」を記載しており、「一括のReleaseとするか複数Releaseへ分割するか…いずれも未確定であり、独立したArchitecture Reviewを要する」と明記している。
- 2026-07-18実施のRelease 6.14候補調査（本Architecture Designの直前工程、読み取り専用）により、次の事実が判明している。
  - `AIImageGenerator`（`src/ai_image_generation/ai_image_generator.py:9-20`）・`GeneratedImage`（`src/ai_image_generation/generated_image.py:11-37`）・`OpenAIImageGenerator`（`src/openai_image_generation/openai_image_generator.py`）・`GeneratedImageWordPressMediaUploader`（`src/generated_image_wordpress_media/generated_image_wordpress_media_uploader.py:15-41`）・`WordPressMediaUploader`（`src/wordpress_media/wordpress_media_uploader.py:92-211`）・`bind_featured_media`（`src/article_featured_media/article_featured_media_binder.py:18-48`）は、いずれも`tests/`以外からの消費者（consumer）がゼロである（grep確認済み）
  - これら5パッケージは相互にimportし合う鎖（`openai_image_generation → ai_image_generation`、`generated_image_wordpress_media → ai_image_generation + wordpress_media`、`article_featured_media → outputs + wordpress_media`）を形成しているが、末端（`main.py`・`src/image_resolver.py`・`src/outputs/`・`src/pipeline/`・`src/retry_*`・`scripts/`）への接続はゼロである
  - `ArticleData.featured_media_id`（`src/outputs/base.py:24`、v1.6.0）・`WordPressOutput.save()`のfeatured_media反映ロジック（`src/outputs/wordpress_output.py:66-67`、既存）はいずれも変更不要であることが、v6.13設計書3章で既に確認済みである
- 本Releaseは、上記5パッケージのうち画像生成・Media Upload・Bindingの3ステップを「決まった順序で呼び出す」という一点のみを担う、新規Consumer-less Foundationである。`main.py`・`image_resolver.py`・Composition Root・環境変数・実HTTP通信のいずれにも触れない。

## 3. Current State（再確認済みProduction Code）

候補調査で確認済みの事実を、本Architecture Design着手前に以下のファイルを再読して再確認した。

### 3.1 AIImageGenerator（`src/ai_image_generation/ai_image_generator.py:9-20`）

```python
class AIImageGenerator(Protocol):
    def generate(self, prompt: str) -> GeneratedImage: ...
```

`typing.Protocol`による構造的型付け。`@runtime_checkable`は付与されていない（`isinstance()`検証不可）。`src/ai_image_generation/__init__.py:9-15`により`from ai_image_generation import AIImageGenerator, GeneratedImage`で公開されている。

### 3.2 GeneratedImage（`src/ai_image_generation/generated_image.py:11-37`）

```python
@dataclass(frozen=True)
class GeneratedImage:
    image_bytes: bytes = field(repr=False)
    mime_type: str

    def __post_init__(self) -> None:
        # type(image_bytes) is not bytes → ValueError
        # len(image_bytes) == 0 → ValueError
        # isinstance(mime_type, str) 不成立 → ValueError
        # mime_type が canonical "image/<subtype>" 正規表現に不一致 → ValueError
```

Self-validatingなfrozen dataclass。`__post_init__`により構築時点で内容の妥当性が保証されている（15章で扱う）。

### 3.3 OpenAIImageGenerator（`src/openai_image_generation/openai_image_generator.py:1-11, 191-`）

`AIImageGenerator`を明示的にimportせず、構造的部分型のみで`generate(self, prompt: str) -> GeneratedImage`を満たす（ファイル冒頭コメント確認済み）。`ai_image_generation`からは`GeneratedImage`のみimportする。本Releaseはこの具象実装へ直接依存しない（8.2節・12章）。

### 3.4 GeneratedImageWordPressMediaUploader（`src/generated_image_wordpress_media/generated_image_wordpress_media_uploader.py:15-41`）

```python
class GeneratedImageWordPressMediaUploader:
    def __init__(self, media_uploader: WordPressMediaUploader) -> None:
        self._media_uploader = media_uploader

    def upload(self, image: GeneratedImage, filename: str) -> MediaUploadResult:
        # isinstance(image, GeneratedImage) 不成立 → ValueError
        # callable(getattr(media_uploader, "upload", None)) 不成立 → TypeError
        #   固定message: "media_uploader must provide a callable upload method"
        # 適合時: upload_method(image_bytes=image.image_bytes, filename=filename, mime_type=image.mime_type)
```

`media_uploader`はDuck Typing（Constructor Injection、`isinstance()`によるnominal型検証なし）。capability検証は`upload()`呼び出し時まで遅延。

### 3.5 WordPressMediaUploader（`src/wordpress_media/wordpress_media_uploader.py:92-211`）

`__init__(site_url, username, app_password)` / `from_env()`（`WP_SITE_URL` / `WP_USERNAME` / `WP_APP_PASSWORD`） / `upload(image_bytes, filename, mime_type) -> MediaUploadResult`。唯一の専用例外`WordPressMediaUploadError(RuntimeError)`。

### 3.6 MediaUploadResult（`src/wordpress_media/media_upload_result.py:8-21`）

```python
@dataclass(frozen=True)
class MediaUploadResult:
    media_id: int
    source_url: str | None
    mime_type: str | None
```

`__post_init__`によるself-validationは**存在しない**（v6.13設計書15.4節で確認済みの既知の非対称性）。

### 3.7 bind_featured_media（`src/article_featured_media/article_featured_media_binder.py:18-48`）

```python
def bind_featured_media(article: ArticleData, media_result: MediaUploadResult) -> ArticleData:
    # isinstance(article, ArticleData) 不成立 → ValueError "article must be an ArticleData"
    # isinstance(media_result, MediaUploadResult) 不成立 → ValueError "media_result must be a MediaUploadResult"
    # media_result.media_id が bool／非int／1未満 → ValueError "media_result.media_id must be a positive int"
    return replace(article, featured_media_id=media_id)
```

module-level function。既存`featured_media_id`の値に関わらず常に決定的に上書きする（v6.13設計書14章）。

### 3.8 ArticleData（`src/outputs/base.py:12-25`）

```python
@dataclass
class ArticleData:
    item: NewsItem
    importance: str
    seo_title: str
    article_body: str
    x_post: str
    featured_image_url: str = ""
    excerpt: str = ""
    meta_description: str = ""
    slug: str = ""
    featured_media_id: int = 0
    publish_status: PublishStatus = PublishStatus.DRAFT
```

`@dataclass`（`frozen`指定なし）。`src/outputs/__init__.py:1`により`from outputs import ArticleData`で公開。

### 3.9 Runtime未接続の再確認

`main.py`（全import文、L20-50相当）・`src/image_resolver.py`（全文）・`src/outputs/wordpress_output.py`・`src/outputs/manager.py`・`src/pipeline/`配下全ファイル・`src/retry_composition/retry_composition_root.py`・`src/retry_runtime_orchestrator/retry_runtime_orchestrator.py`・`scripts/`配下を確認したが、いずれも上記5パッケージ（`ai_image_generation` / `openai_image_generation` / `wordpress_media` / `generated_image_wordpress_media` / `article_featured_media`）を一切importしていない。なお`src/retry_runtime/`という単一packageは存在せず、実際は`retry_runtime_lock` / `retry_runtime_logging` / `retry_runtime_loop` / `retry_runtime_orchestrator` / `retry_runtime_shutdown`の5個別packageに分かれている（ディレクトリ一覧で確認済み）。

### 3.10 既存Orchestrator precedent（`src/retry_runtime_orchestrator/retry_runtime_orchestrator.py:88-126`）

```python
class RetryRuntimeOrchestrator:
    def __init__(self, trigger, scheduler, manager, queue, history, policy):
        self.trigger = trigger
        # ...（6つの依存参照をConstructorで保持するのみ）

    @classmethod
    def from_composition_root(cls, root: RetryCompositionRoot) -> "RetryRuntimeOrchestrator":
        return cls(trigger=root.trigger, ...)

    def run_once(self, dry_run: bool = False) -> RetryRuntimeCycleResult:
        # 決まった順序でdependencyを呼び出し、結果をRetryRuntimeCycleResultへ集約
```

本プロジェクトにおける直接のOrchestrator命名precedent。「Composition（組み立て）はComposition Rootの責務、Orchestratorは既存インスタンスへの参照を保持し実行順序を決めることだけに限定する」という責務分離が明記されている（`retry_runtime_orchestrator.py:9-19`）。本Releaseはこの責務分離をそのまま踏襲する。

## 4. Problem Statement

「画像生成 → Media Upload → Binding」という3ステップの処理順序を、呼び出しごとに毎回手書きする手段しか現状存在しない。この3ステップは次の性質を持つため、専用のOrchestrator層として確立する価値がある。

```text
3つの異なるpackage（ai_image_generation / generated_image_wordpress_media相当 / article_featured_media）
    にまたがる呼び出し順序が固定されている
順序を誤ると（例：Upload before generate）意味をなさない
各ステップの失敗時に後続を呼んではならない、という不変のContractがある
将来のProduction Runtime Wiring（main.py接続）が、この順序を再実装せず
    再利用できる状態を先に確立する必要がある
```

## 5. Release Goal

```text
ArticleData
prompt
filename
    ↓
ArticleFeaturedMediaOrchestrator.apply(article, prompt, filename)
    1. Orchestrator自身の入力Validation
    2. image_generator.generate(prompt) → GeneratedImage
    3. media_uploader.upload(generated_image, filename) → MediaUploadResult
    4. bind_featured_media(article, media_result) → 新しいArticleData
    5. 新しいArticleDataを返す
    ↓
featured_media_idが設定された新しいArticleData
```

必須要件（すべて満たす）：

```text
処理順序（generate → upload → bind）を固定する
各dependencyを正常系で正確に1回だけ呼び出す
いずれかのステップが失敗した場合、後続ステップを呼び出さない
dependency例外を無変換伝播する（wrapしない、変換しない、fallbackしない）
元ArticleDataを変更しない（bind_featured_mediaへ完全委譲）
OpenAI固有Adapterへ依存しない（AIImageGenerator Protocolのみに依存する）
main.py・image_resolver.py・WordPressOutput・OutputManager・Pipeline・
    Composition Root・Retry Runtime・scriptsのいずれへも接続しない
promptを生成しない（Callerから受け取る）
filenameを生成しない（Callerから受け取る）
環境変数・credential・HTTP通信・ファイルI/O・Loggingを一切行わない
```

## 6. In Scope

```text
既存4 Foundation（AIImageGenerator Contract, GeneratedImage → Media Upload capability,
    bind_featured_media）を決まった順序で呼び出す、単一のOrchestrator classの追加
上記Orchestratorが依存する最小限のUpload Capability Protocolの新設（12章で確定）
上記Orchestratorを公開する新規独立package（1package・1module・
    Public class 1つ・Public Protocol 1つ）の追加
Orchestrator自身のPublic Boundary Validation Contract
    （article型・prompt型/値・filename型/値・dependency capability）の確立
Orchestrator自身のError Contract・呼び出し順序Contract・State Contractの確立
```

## 7. Out of Scope

```text
main.py変更
image_resolver.py変更
WordPressOutput変更
OutputManager変更
Publish系Composition Root追加
Runtime Wiring（main.py・image_resolver.py等の実Production Runtimeへの接続）
WordPress記事投稿
画像prompt生成（記事タイトル・本文・SEO情報からの自動生成を含む）
filename自動生成（拡張子推測・日時・UUID等の生成を含む）
Configuration First有効化フラグの新設
Environment Variable読込
OpenAI client生成
WordPress client生成
fallback Policy（画像生成/Upload失敗時の継続方針）
DEFAULT_MEDIA_IDとの統合
既存featured_media_idを維持するPolicy（呼び出すか否かの判断はCaller側）
Retry Runtime接続
Retry Queue拡張
media_id永続化
重複画像生成防止
重複Media Upload防止
idempotency key
Media削除API
unused media cleanup
rollback
Upload成功後の記事投稿失敗時の整合性
Scheduler接続
Agent接続
OpenAIImageGenerator等の具象Adapterへの直接依存
GeneratedImageWordPressMediaUploader具象classそのものへの必須依存
    （12章のCapability Protocol採用により回避）
```

これらは35章（Future Candidates）へ後続Release候補として引き継ぐ。番号・正式名称は本文書で確定しない。

## 8. Architecture Decision

| # | 内容 |
|---|---|
| AD-1 | 責務モデル：`ArticleData` / `prompt` / `filename`を受け取り、画像生成→Media Upload→Bindingを固定順序で呼び出し、`featured_media_id`が設定された新しい`ArticleData`を返す、純粋な呼び出しOrchestration。HTTP通信・credential取得・prompt/filename生成のいずれも行わない |
| AD-2 | Package配置：新規独立package`src/article_featured_media_orchestration/`（Consumer-less Foundationとして導入、9章） |
| AD-3 | Public API形状：**Class＋Constructor Injection**を採用する（詳細は11章） |
| AD-4 | Constructor：`image_generator: AIImageGenerator`・`media_uploader: GeneratedImageUploadCapability`の2依存を受け取り、参照のみを保持する。Constructor時点で両dependencyのcapability検証を行う（TypeError、17章） |
| AD-5 | 依存Contract：`ai_image_generation.AIImageGenerator` / `ai_image_generation.GeneratedImage` / `wordpress_media.MediaUploadResult` / `article_featured_media.bind_featured_media` / `outputs.ArticleData`のみに依存する。`openai_image_generation` / `wordpress_media.WordPressMediaUploader` / `generated_image_wordpress_media`のいずれにも依存しない（21章） |
| AD-6 | Media Upload依存の形状：Orchestrator専用の最小Capability Protocol（`GeneratedImageUploadCapability`）を新設し、これへ依存する。既存`generated_image_wordpress_media.GeneratedImageWordPressMediaUploader`具象classへは依存しない（Option B採用、12章） |
| AD-7 | ArticleData複製方式：Orchestrator自身は`dataclasses.replace()`を呼ばない。`bind_featured_media()`へ完全委譲する（Single Source of Truth、15章） |
| AD-8 | Validation方式：Constructor時点でdependency capability（`generate` / `upload`のcallable検証）、`apply()`時点でarticle型・prompt型/値・filename型/値を検証する（16章） |
| AD-9 | Error Contract：Orchestrator自身のBoundary検証失敗は`ValueError`（固定message）、dependency capability不足は`TypeError`（固定message）。dependency呼び出し（generate/upload/bind）由来の例外は無変換伝播する（17章） |
| AD-10 | 呼び出し順序：`generate → upload → bind`を固定し、各dependencyは正常系で正確に1回だけ呼ぶ。途中失敗時は後続を呼ばない（14章） |
| AD-11 | State Contract：Constructor Injectionされた2つのdependency参照以外、インスタンス状態を一切保持しない。`apply()`はrequest単位のstateをインスタンス属性へ保存しない（20章） |
| AD-12 | Failure Boundary：画像生成/Upload失敗時に記事投稿を続けるか等の業務判断は行わない。例外の無変換伝播のみを責務とする（18章） |
| AD-13 | prompt／filename：Callerから引数として受け取るのみ。Orchestrator内部で生成・推測・変換しない（13章） |
| AD-14 | Logging：追加しない |
| AD-15 | Retry：追加しない。Retry Runtimeへの接続もしない |
| AD-16 | Runtime接続：main.py・image_resolver.py・WordPressOutput・OutputManager・Pipeline・Composition Root・Retry Runtime・scriptsのいずれへも接続しない（Consumer-less Foundation継続） |

## 9. Package Structure

```text
projects/03_game_content_ai/src/article_featured_media_orchestration/
├── __init__.py
└── article_featured_media_orchestrator.py   # ArticleFeaturedMediaOrchestrator, GeneratedImageUploadCapability
```

### 9.1 package名の検討

| 候補 | 却下／採用理由 |
|---|---|
| `article_featured_media_runtime_wiring` | 本Releaseはmain.py等の実Production Runtimeへ接続しない（7章）。「Runtime Wiring」を含む名称は11章の命名条件（Runtime全体を接続しない場合はRuntime Wiringと断定しない）に反する |
| `article_featured_media_binding_orchestration` | `article_featured_media`（v6.13.0）と語が重複し、既存package名との識別性が下がる。responsibility自体もBindingそのものではなく複数Foundationの呼び出し順序管理である |
| **`article_featured_media_orchestration`（採用）** | ユーザー指定の第一候補と一致。`ArticleData`＋`featured_media`という既存概念（v6.13.0で確立済み）に「Orchestration」という責務語を付加しており、責務が名前から一意に読み取れる。既存package名（`generated_image_wordpress_media`等）と同様に`_foundation`を含まないディレクトリ命名規則とも整合する |

命名上の問題は確認されなかった。想定パス`projects/03_game_content_ai/src/article_featured_media_orchestration/`をそのまま採用する。

### 9.2 module名の検討

`article_featured_media_orchestrator.py`を採用する。既存precedent（`article_featured_media_binder.py`は`article_featured_media`package内で`bind_featured_media()`を定義、`generated_image_wordpress_media_uploader.py`は`generated_image_wordpress_media`package内で`GeneratedImageWordPressMediaUploader`を定義）と同様、`<package名>_<責務を表す名詞>.py`という既存命名パターンに従う。

### 9.3 ファイル分割の検討

`GeneratedImageUploadCapability`（12章で確定するProtocol）を専用fileへ分けるか、同一file内に置くかを比較した。

| 案 | 内容 | 採否 |
|---|---|---|
| 同一file内（採用） | `article_featured_media_orchestrator.py`内にProtocol定義＋Orchestrator classの両方を置く | **採用**。Protocolは`ArticleFeaturedMediaOrchestrator`のConstructor引数の型を表現するためだけに存在し、独立した責務を持つモジュールではない。元のArchitecture Design依頼プロンプト19章「新規Package候補」の指示「不要なファイル分割を避けてください」と、`ai_image_generation`package内で`AIImageGenerator`（Protocol）と`GeneratedImage`（dataclass）が別fileに分かれているprecedentはあるが、そちらは2つとも独立して再利用される主要な型である点が異なる。本Releaseの`GeneratedImageUploadCapability`はOrchestrator専用の補助的な型定義であり、同一fileに置く方が責務の近さを反映する |
| 専用file（`generated_image_upload_capability.py`等） | Protocolのみを別fileに分離 | 不採用。ファイル数が増えるだけで可読性・保守性の向上が見込めない（9.3節の判断基準：不要な分割の回避） |

## 10. Public API

```python
# src/article_featured_media_orchestration/article_featured_media_orchestrator.py
from typing import Protocol

from ai_image_generation import AIImageGenerator, GeneratedImage
from article_featured_media import bind_featured_media
from outputs import ArticleData
from wordpress_media import MediaUploadResult


class GeneratedImageUploadCapability(Protocol):
    def upload(self, image: GeneratedImage, filename: str) -> MediaUploadResult: ...


class ArticleFeaturedMediaOrchestrator:
    def __init__(
        self,
        image_generator: AIImageGenerator,
        media_uploader: GeneratedImageUploadCapability,
    ) -> None: ...

    def apply(self, article: ArticleData, prompt: str, filename: str) -> ArticleData: ...
```

```python
# src/article_featured_media_orchestration/__init__.py
from .article_featured_media_orchestrator import (
    ArticleFeaturedMediaOrchestrator,
    GeneratedImageUploadCapability,
)

__all__ = [
    "ArticleFeaturedMediaOrchestrator",
    "GeneratedImageUploadCapability",
]
```

- Public import path：`from article_featured_media_orchestration import ArticleFeaturedMediaOrchestrator, GeneratedImageUploadCapability`
- Constructor引数名：`image_generator`（`AIImageGenerator`）、`media_uploader`（`GeneratedImageUploadCapability`）
- `apply()`引数名：`article`（`ArticleData`）、`prompt`（`str`）、`filename`（`str`）
- `apply()`戻り値型：`ArticleData`（新しいobject）

## 11. Dependency Injection Contract（Public API形状の比較）

| 案 | 内容 | 採否 |
|---|---|---|
| **Class＋Constructor Injection（採用）** | `ArticleFeaturedMediaOrchestrator(image_generator, media_uploader)`を構築し、`apply(article, prompt, filename)`を複数回呼び出す | **採用** |
| module-level function＋dependency引数 | `apply_article_featured_media(image_generator, media_uploader, article, prompt, filename)`のような5引数関数 | 不採用 |
| dataclass based service | `@dataclass`で`image_generator` / `media_uploader`をfieldとして保持し、method経由で呼び出す | 不採用（Classと実質的に同じだが不要な複雑さを追加） |
| Callable composition | `image_generator`と`media_uploader`をあらかじめ合成した単一のCallableを返す高階関数 | 不採用 |

**採用理由**：

```text
image_generatorとmedia_uploaderという2つのdependencyは、将来のCaller
    （Runtime WiringのComposition Root）が一度だけ構築し、複数記事に対して
    繰り返しapply()を呼び出す使われ方が想定される（bind_featured_media()の
    ような「呼ぶたびに全依存を渡す」使い方とは性質が異なる）
既存precedent：GeneratedImageWordPressMediaUploader（v6.12.0）・
    RetryRuntimeOrchestrator（v5.2.0）はいずれも複数dependencyを
    Constructor Injectionで保持し、method呼び出し時はrequest単位の
    引数のみを受け取るという同型パターンを採用している
    （3.4節・3.10節で確認済み）
module-level functionの場合、apply()を呼ぶたびに2つのdependencyを
    毎回渡す必要があり、Callerが誤った組み合わせのdependencyを
    渡すリスクが増える
dataclass based serviceはClass＋Constructor Injectionと実質的に同じ
    構造だが、Behaviorを持つオブジェクトを@dataclassとして宣言する
    必然性がなく、既存precedent（GeneratedImageWordPressMediaUploaderは
    通常のclassとして実装、@dataclassではない）とも一致しない
Callable compositionは、2つのdependencyの型・責務が明確に異なる
    （画像生成／Media Upload）ため、単一のCallableへ合成すると
    型Contractが読み取りにくくなる
```

これは`bind_featured_media()`（v6.13.0、module-level function採用）との対比で「一貫性がない」という懸念が生じうるため、10.1節の判断基準との違いを次に明記する。

### 11.1 bind_featured_media()との対比

`bind_featured_media()`がmodule-level functionを採用した理由（v6.13設計書10.1節）は「依存注入の必要がない」ことだった。対して本Releaseの`ArticleFeaturedMediaOrchestrator`は最初から2つのdependency（`image_generator` / `media_uploader`）を注入する必要があり、`GeneratedImageWordPressMediaUploader`（1つのdependencyをConstructor Injectionする既存precedent）とより近い性質を持つ。「依存注入の要否」という同一の判断基準を適用した結果、`bind_featured_media()`はfunction、`ArticleFeaturedMediaOrchestrator`はClassという異なる結論になっており、これは矛盾ではなく判断基準の一貫した適用である。

## 12. Uploader Dependency Alternatives（案A／B／C比較）

### 12.1 比較表

| 観点 | 案A：具象class依存 | 案B：最小Capability Protocol（採用） | 案C：Callable Injection |
|---|---|---|---|
| 内容 | `media_uploader: GeneratedImageWordPressMediaUploader` | `media_uploader: GeneratedImageUploadCapability`（新設Protocol、`upload(image, filename) -> MediaUploadResult`） | `media_uploader: Callable[[GeneratedImage, str], MediaUploadResult]` |
| 既存Public APIとの整合性 | `generated_image_wordpress_media.GeneratedImageWordPressMediaUploader`のPublic API（`upload(image, filename)`）とシグネチャ一致 | 同左シグネチャを構造的に表現するのみ、既存classへの依存はゼロ | シグネチャは一致するが、`image=` / `filename=`というkeyword引数名の情報が型注釈から失われる |
| Dependency Inversion | 低い（具象classへ直接依存、8.2節が`AIImageGenerator`について要求するDependency Inversionと非対称になる） | 高い（`image_generator`側と同じ抽象化レベルに揃う） | 高いが、Protocolより型の意味が薄い（単なる関数シグネチャで、`upload`という method名の情報が失われる） |
| 過剰抽象化の回避 | 該当なし（抽象化しない） | 懸念あり：具象実装が`GeneratedImageWordPressMediaUploader`の1つしか存在しない段階での新規Protocol新設 | 該当なし（抽象化の形が異なるだけ） |
| E2Eでのfake注入容易性 | `GeneratedImageWordPressMediaUploader`を継承しないfakeは型注釈上不正合になる（実行時はDuck Typingで動くが、型Contractとしては不整合） | 高い（任意のfake classがmethodを1つ持てば型的に適合） | 最も高い（単なる関数を渡すだけでよい） |
| 型Contractの明確さ | 高い（既存class） | 高い（method名`upload`・引数名が明示される） | 低い（引数名の情報が型注釈に現れない） |
| 将来Adapter追加への耐性 | 低い（将来別のUpload先＝別CMS等が増えた場合、具象class名がOrchestratorのContractに固定されてしまう） | 高い | 高い |
| Protocolの配置場所 | 該当なし | 本package内（9.3節） | 該当なし |
| Reverse Dependency risk | `generated_image_wordpress_media`パッケージへ本Releaseが依存することになるが、逆方向（`generated_image_wordpress_media → article_featured_media_orchestration`）は発生しない限りRisk自体はない | 発生しない（Protocolは本package内で完結） | 発生しない |
| 既存packageを変更せずに実現できるか | 可能（既存`GeneratedImageWordPressMediaUploader`は無改修） | 可能（新規Protocolは本package内に新設するのみ） | 可能 |

### 12.2 採用理由（案B：最小Capability Protocol）

```text
8.2節が要求する「OpenAIImageGenerator具象Adapterへ依存せずAIImageGenerator
    Protocolへ依存する」というDependency Inversion方針と、Media Upload側の
    依存方針を対称に保つ。image_generator側だけProtocol、media_uploader側は
    具象classという非対称な設計は、Orchestratorの2つのdependencyが
    異なる抽象化原則に従うことになり、Contractとして一貫性を欠く

既存precedent：ai_image_generation.AIImageGenerator（v6.10.0）は、
    具象実装（OpenAIImageGenerator、v6.11.0）が存在するより先に
    Protocolとして確立された（Contract First）。本Releaseの
    GeneratedImageUploadCapabilityも、現時点で具象実装が
    GeneratedImageWordPressMediaUploader（v6.12.0）の1つしかない点は
    AIImageGenerator確立時の状況（具象実装ゼロ）よりもむしろ材料が
    揃っている。「1つの実装しか存在しない段階でのProtocol新設」は、
    本プロジェクトが既に採用してきたContract Firstの設計哲学の延長であり、
    過剰設計とは判断しない

GeneratedImageWordPressMediaUploader自体もmedia_uploaderを
    Duck Typing（isinstance()によるnominal型検証なし）で受け取る設計
    （3.4節）であり、「型の名前ではなく振る舞いで依存を表現する」という
    既存プロジェクトの一貫した設計判断とも整合する

E2Eにおいて、実際のWordPressMediaUploaderやGeneratedImageWordPressMediaUploaderを
    経由せずに、単純なfakeオブジェクト（upload()メソッドを1つ持つだけの
    テスト用class）を型的に正しく注入できる
```

### 12.3 案A（具象class依存）を不採用とする理由

```text
将来、WordPress以外のCMS・別のUpload経路（Future Candidates、35章）が
    追加された場合、Orchestrator自身のPublic Contract（Constructor引数の
    型注釈）がGeneratedImageWordPressMediaUploaderという具象class名に
    固定されてしまい、Orchestrator側の変更（Constructor引数の型変更）が
    必要になる。これはAD-5（Dependency Inversion維持）に反する
image_generator側でOpenAIImageGenerator具象Adapterへの直接依存を
    明示的に禁止している（8.2節）のに対し、media_uploader側だけ具象class
    依存を許すと、Orchestrator全体のDependency Inversion方針が
    非対称になり、Architecture Reviewでの説明可能性が低下する
```

### 12.4 案C（Callable Injection）を不採用とする理由

```text
upload(image, filename)という2引数の意味（どちらがGeneratedImageで
    どちらがfilenameか）が、Callable型注釈（Callable[[GeneratedImage, str],
    MediaUploadResult]）だけでは引数名として表現されない。既存
    GeneratedImageWordPressMediaUploader.upload()がkeyword引数
    （image_bytes= / filename= / mime_type=）で委譲する設計（3.4節）を
    採用している既存精神とも整合しにくい
Protocol（案B）はCallableに比べて追加コストがほぼない
    （1 method・2行のinterfaceを定義するだけ）にもかかわらず、
    型の意味（method名・引数名）を保持できるため、Callable Injectionを
    選ぶ実利がない
```

### 12.5 GeneratedImageUploadCapabilityをPublic APIとするか

Public APIとして`__init__.py`からexportする（10章）。理由：

```text
既存precedent：ai_image_generation.AIImageGenerator（Protocol）は
    package rootからexportされている（3.1節）。本Releaseの
    GeneratedImageUploadCapabilityも同様にexportし、将来のCaller
    （テスト・Runtime Wiring双方）が型注釈として参照できるようにする
Python の構造的部分型はexportしていなくても満たせるが、
    型チェッカー（mypy等）による静的検証や、E2Eでのfake実装作成時の
    Contract明示のため、Public APIとして公開する意義がある
```

## 13. promptとfilenameの責務

Release 6.14では、`prompt`・`filename`をいずれも`apply()`の引数としてCallerから受け取る。Orchestrator内部では次を一切行わない。

```text
記事タイトル・記事本文・SEO情報からのprompt生成
slug生成
filenameの自動生成（拡張子推測・日時・UUID等の生成を含む）
環境変数からのprompt取得
設定ファイルからのfilename取得
```

**理由**：

```text
Release 6.14の責務をOrchestration（既存4 Foundationの呼び出し順序管理）
    へ限定する。prompt engineering・filename policyはいずれも
    Orchestrationとは異なる責務であり、別Foundationとして独立に
    検討すべき事項である（35章 Future Candidates：Article Image Prompt
    Construction Foundation・Generated Image Filename Policy Foundation）
既存4 Foundationのいずれもprompt/filenameを生成しない
    （3.1節〜3.7節で確認済み。OpenAIImageGeneratorはOut of Scopeとして
    filename生成を明示的に除外しており、GeneratedImageWordPressMediaUploaderも
    filenameをCallerから受け取るのみ）という既存Contractと整合させる
deterministicなE2Eを可能にする（prompt/filenameが固定値として
    Fakeへ渡され、生成ロジックに依存しないテストが書ける）
Runtime Wiring時（将来Release）にPolicy変更（例：prompt生成方式の変更）が
    発生しても、本Orchestrator自体には影響しない
```

## 14. Runtime／Call Sequence Contract

```text
Caller（本Releaseでは未実装＝Consumer-less。将来のRuntime Wiring、35章）
  → ArticleFeaturedMediaOrchestrator(image_generator, media_uploader)  ※Constructor
      - image_generatorのcapability検証（callable(getattr(image_generator, "generate", None))）
        不適合なら TypeError（17章）
      - media_uploaderのcapability検証（callable(getattr(media_uploader, "upload", None))）
        不適合なら TypeError（17章）
      - 参照を self._image_generator / self._media_uploader へ保持
  → orchestrator.apply(article, prompt, filename)
      1. isinstance(article, ArticleData) を検証。不適合なら ValueError（16章）
      2. prompt の型・値を検証（str かつ非空白）。不適合なら ValueError（16章）
      3. filename の型・値を検証（str かつ非空白）。不適合なら ValueError（16章）
      4. self._image_generator.generate(prompt) → GeneratedImage
         （例外発生時は無変換伝播し、5.以降を実行しない）
      5. self._media_uploader.upload(generated_image, filename) → MediaUploadResult
         （例外発生時は無変換伝播し、6.以降を実行しない）
      6. bind_featured_media(article, media_result) → 新しいArticleData
         （例外発生時は無変換伝播する）
      7. 新しいArticleDataを返す
```

正常系では、`generate()` / `upload()` / `bind_featured_media()`はいずれも**apply()呼び出しごとに正確に1回だけ**呼ばれる。次を禁止する。

```text
uploadをgenerateより先に呼ぶ
bindingをuploadより先に呼ぶ
generateを複数回呼ぶ
uploadを複数回呼ぶ
bind_featured_mediaを複数回呼ぶ
処理結果をcacheする（同一prompt/filenameでも毎回実行する）
失敗後に自動再試行する
例外発生後に後続dependencyを呼ぶ
```

本Release自体はCallerを持たない（Consumer-less Foundation、Foundation First原則の継続）。

## 15. Validation Contract

### 15.1 Constructor Validation（dependency capability）

```python
if not callable(getattr(image_generator, "generate", None)):
    raise TypeError("image_generator must provide a callable generate method")

if not callable(getattr(media_uploader, "upload", None)):
    raise TypeError("media_uploader must provide a callable upload method")
```

**方式選定**：`isinstance()`によるnominal型検証は行わない。`AIImageGenerator`は`@runtime_checkable`が付与されていないProtocolであり（3.1節）、`isinstance(image_generator, AIImageGenerator)`は`TypeError: Instance and class checks can only be used with @runtime_checkable protocols`を送出してしまうため構造的に不可能である。`getattr(...) + callable(...)`によるDuck Typing検証は、既存precedent（`GeneratedImageWordPressMediaUploader.upload()`のmedia_uploader capability検証、3.4節）と同一の方式であり、`media_uploader`側のmessageもその固定文言（`"media_uploader must provide a callable upload method"`）をそのまま踏襲する。`image_generator`側は対称の文言（`"image_generator must provide a callable generate method"`）を新設する。

**新設`GeneratedImageUploadCapability`に`@runtime_checkable`を付与しない理由**：`AIImageGenerator`（既存）と対称に、`GeneratedImageUploadCapability`（新設）にも`@runtime_checkable`を付与しない。理由：Constructor Validation（本節）は`isinstance()`ではなく`getattr(...) + callable(...)`によるDuck Typingのみを採用しており、Production Code内で`isinstance(media_uploader, GeneratedImageUploadCapability)`を呼び出す箇所が存在しないため、`@runtime_checkable`を付与する実利がない。これは12.2節で述べた「型の名前ではなく振る舞いで依存を表現する」という既存プロジェクトの一貫した設計判断とも整合する。将来、Production Code側で`isinstance()`検証が必要になった場合は、その時点で`@runtime_checkable`の追加を独立に検討する（Protocol定義自体の変更を伴うため、追加時はConstructor Validation方式の変更として扱う）。

**`getattr()`がAttributeError以外の例外を送出した場合の扱い**：`generate`／`upload`が通常のmethod属性ではなく、アクセス自体が例外を送出する`@property`等の実装だった場合、`getattr(obj, name, default)`は`AttributeError`のみを`default`（`None`）へ変換し、それ以外の例外（例：propertyのgetter内部で発生した`RuntimeError`等）はそのまま`getattr()`呼び出し元へ伝播する。本Constructorはこの標準的なPython挙動を上書きしない。すなわち、`AttributeError`以外の理由でcapability検証自体が失敗した場合、その例外はConstructor Validationの一部として無変換伝播する（17章のError Contract「dependency呼び出し由来の例外は無変換伝播する」という原則がConstructor Validation自体にもそのまま適用される、という整理である）。

**Constructor時点で検証する理由（v6.12.0との相違点の明記）**：`GeneratedImageWordPressMediaUploader`（v6.12.0）はConstructorで検証せず、`upload()`呼び出し時まで検証を遅延させる設計だった（3.4節）。これは同classが単一のdependency（`media_uploader`）のみを保持するためである。本Releaseの`ArticleFeaturedMediaOrchestrator`は2つのdependencyを保持し、`apply()`内で`generate()` → `upload()`という順序で呼び出す構造上、`media_uploader`のcapability不備を`upload()`直前まで検出しない設計にすると、「`generate()`が（将来のRuntime Wiringで実際に画像生成・課金を伴う場合）既に実行された後で`media_uploader`の不備が判明する」という無駄な実行を許してしまう。Constructor時点で両dependencyのcapabilityを検証することで、`apply()`を1回も呼ぶ前に構成不備を検出できる（fail-fast）。本Release自体は実際の画像生成・課金を行わないが、将来のRuntime Wiringでこの構造がそのまま踏襲されることを見込んだ設計判断である。

### 15.2 apply() Validation（article／prompt／filename）

```python
# 1. article
if not isinstance(article, ArticleData):
    raise ValueError("article must be an ArticleData")

# 2. prompt
if not isinstance(prompt, str):
    raise ValueError("prompt must be a str")
if not prompt.strip():
    raise ValueError("prompt must not be blank")

# 3. filename
if not isinstance(filename, str):
    raise ValueError("filename must be a str")
if not filename.strip():
    raise ValueError("filename must not be blank")
```

**article検証のmessage**：`bind_featured_media()`（v6.13.0）の`"article must be an ArticleData"`と完全に同一の文言を採用する（3.7節）。Orchestratorが検証する対象・意味が`bind_featured_media()`のarticle検証と同一であるため、既存Public Contractとの表記揺れを避ける。

**prompt／filenameの型検証**：`isinstance(x, str)`を採用する。`bytes`や`pathlib.Path`が渡された場合、`isinstance(x, str)`はFalseとなり明示的に拒否される（暗黙変換をしない、元のArchitecture Design依頼プロンプト12章の指示に対応）。`type(x) is not str`のような完全一致検証は採用しない。理由：`GeneratedImage.__post_init__`は`image_bytes`（`bytes`という可変性のない基本型）には`type(x) is not bytes`を用いる一方、`mime_type`（`str`）には`isinstance(x, str)`を用いており（3.2節）、既存プロジェクトの精度基準は「`bytes`は完全一致、`str`は`isinstance`」で統一されている。本Releaseの`prompt`／`filename`はいずれも`str`であるため、既存precedentに合わせて`isinstance`を採用する。

**空白のみ文字列の扱い**：`prompt.strip()`／`filename.strip()`が空になる場合（空文字列・空白のみ文字列の両方）を`ValueError`とする。理由：空白のみのpromptを`AIImageGenerator.generate()`へ渡すこと、空白のみのfilenameを`upload()`へ渡すことは、いずれもOrchestrator Boundary時点で意味をなさない入力であり、後続dependency（特に`WordPressMediaUploader._validate_filename`のfilenameパターン検証、3.5節）へ伝播させる前にfail-fastする方が呼び出しコストを抑えられる。ただし、`WordPressMediaUploader`が行う詳細なfilenameパターン検証（`^[A-Za-z0-9][A-Za-z0-9._-]*$`）や`OpenAIImageGenerator`が行う詳細なprompt検証（最大長・許可制御文字）を、本Orchestratorが重複実装することはしない（元のArchitecture Design依頼プロンプト12章の指示「既存dependency内部で検証される値をOrchestratorが過剰に重複検証しない」に従う）。

**Validationにはstrip()を使用するがdependencyへ渡す値は元の文字列**：`prompt.strip()`／`filename.strip()`は空白のみ判定という検証目的でのみ使用する。検証を通過した後、`image_generator.generate(prompt)` / `media_uploader.upload(generated_image, filename)`（14章）へ渡す値は、`strip()`されていない元の`prompt`／`filename`引数そのものである。Orchestratorは`prompt = prompt.strip()`のような再代入を一切行わず、文字列の正規化（前後空白の除去・大文字小文字変換等）を行わない。前後に空白を含むが空白のみではない`prompt`／`filename`（例：`" cat "`）は、Validationを通過し、空白を含んだまま後続dependencyへそのまま渡される。

### 15.3 固定message一覧

```text
Constructor（TypeError）：
    image_generator must provide a callable generate method
    media_uploader must provide a callable upload method

apply()（ValueError）：
    article must be an ArticleData
    prompt must be a str
    prompt must not be blank
    filename must be a str
    filename must not be blank
```

## 16. Validation Order

```text
Constructor：
    1. image_generator capability検証
    2. media_uploader capability検証

apply()：
    3. articleの型検証
    4. promptの型・値検証
    5. filenameの型・値検証
    6. image_generator.generate(prompt) 呼び出し
    7. media_uploader.upload(generated_image, filename) 呼び出し
    8. bind_featured_media(article, media_result) 呼び出し
    9. 戻り値の返却
```

複数の入力が同時に不正な場合、最初に検証を満たさなかった項目の例外のみが送出される（fail-fast、逐次検証）。これは`bind_featured_media()`（articleの検証→media_resultの検証の順、v6.13設計書16章）・`WordPressMediaUploader.upload()`（image_bytes→filename→mime_typeの順）・`GeneratedImageWordPressMediaUploader.upload()`（image型検証→capability検証の順）と同一の既存パターンである。

article検証（3番目）をprompt／filename検証（4〜5番目）より先に行う理由：`apply()`の最終ステップ（8番目）で必要になる`article`を最初に検証しておくことで、article自体が不正な場合にprompt/filenameの検証コストを払わずに即座にfail-fastできる（v6.13設計書のarticle優先検証と同じ考え方）。

## 17. Error Contract

```text
image_generator capability不足の例外型：TypeError（固定message完全一致）
media_uploader capability不足の例外型：TypeError（固定message完全一致）
article型不正の例外型：ValueError（固定message完全一致）
prompt型不正・空白のみの例外型：ValueError（固定message完全一致）
filename型不正・空白のみの例外型：ValueError（固定message完全一致）
固定messageをPublic Contractとする：する（7種すべて完全一致でPublic Contract化する）

image_generator.generate()由来の例外：無変換伝播（catchしない、変換しない、
    ラップしない、fallbackしない）。media_uploader.upload()・
    bind_featured_media()はいずれも呼び出さない
media_uploader.upload()由来の例外：無変換伝播。bind_featured_media()は
    呼び出さない
bind_featured_media()由来の例外：無変換伝播
```

原則（既存precedentを踏襲）：

```text
try／exceptを追加しない
例外wrapperを作らない
raise ... from ... を使用しない
予期しないPython runtime例外を変換しない
部分成功を成功として返さない（generate成功・upload失敗の場合、
    GeneratedImageやMediaUploadResultを部分的な戻り値として返さない。
    例外送出のみで表現する）
credentialや入力objectのrepr／str表現をmessageへ含めない
```

`KeyboardInterrupt` / `SystemExit`は`BaseException`のsubtypeであり、本層は`Exception`のみを対象とした`except`を一切持たないため、これらを握りつぶすことはない（本層は`try`/`except`自体を持たない）。

### 17.1 ValueError／TypeErrorの使い分け根拠

`article` / `prompt` / `filename`という「呼び出し元が`apply()`へ渡した引数」の型・値不正はいずれも`ValueError`とする。これは`bind_featured_media()`の`isinstance`不正判定が`ValueError`を採用した既存precedent（v6.13設計書15.2節：Public Boundaryにおける`isinstance`型不正を`ValueError`として扱う）をそのまま踏襲する。

`image_generator` / `media_uploader`という「Constructorへ渡されたdependency」のcapability不足は`TypeError`とする。これは`GeneratedImageWordPressMediaUploader.upload()`の`media_uploader`capability不足判定が`TypeError`を採用した既存precedent（3.4節、固定message`"media_uploader must provide a callable upload method"`）をそのまま踏襲する。

**使い分けの整理**：本プロジェクトの既存Contractでは、「型そのものが違う（isinstance不正）」＝`ValueError`、「必要なmethodを持たない（capability不正）」＝`TypeError`、という2種類のBoundary検証が別の例外型に対応している。本Releaseの`article`／`prompt`／`filename`はいずれも型そのものの不正（isinstance）であるため`ValueError`、`image_generator`／`media_uploader`はいずれもcapability不正（callable検証）であるため`TypeError`という判定を、既存2つのprecedentへ機械的に整合させた。

## 18. Failure Boundary

Release 6.14では、Orchestratorが次のPolicyを決定しない（Out of Scope、7章）。

```text
画像生成に失敗しても記事投稿を続けるか
Uploadに失敗しても記事投稿を続けるか
既存featured_media_idを維持するか
DEFAULT_MEDIA_IDへfallbackするか
画像なしでWordPress投稿するか
Retryへ送るか
再生成するか
再Uploadするか
Mediaを削除するか
```

Release 6.14で確定するFailure Boundaryは次のみである。

```text
成功：新しいArticleDataを返す
失敗：発生した例外をCallerへ無変換伝播する
途中失敗：失敗箇所以降の処理を実行しない
    （generate失敗 → upload/bind未実行、upload失敗 → bind未実行）
```

Runtime側の継続・中止判断は、将来のArticle Featured Media Runtime Wiringの責務とする（35章）。

## 19. ArticleData不変性Contract

Release 6.13 Contractを維持する。

```text
元ArticleDataを変更しない
戻り値は別ArticleData object
featured_media_id以外を変更しない
nested object参照を維持する
同じmedia_idの場合でも新しいArticleDataを返す
```

Release 6.14側では`ArticleData`を直接`dataclasses.replace()`しない。必ず既存Public API`bind_featured_media(article, media_result)`（v6.13.0）を呼び出す。これにより、Binding ContractのSingle Source of Truthを`article_featured_media`package側に一元化したまま維持する（AD-7）。`apply()`内で`dataclasses`モジュール自体をimportする必要はない。

## 20. State Contract

`ArticleFeaturedMediaOrchestrator`は、Constructor Injectionされた2つのdependency参照（`self._image_generator` / `self._media_uploader`）のみを保持する。これらは構築時に一度だけ設定され、以後変更されない。

### 20.1 「stateless」の定義（RetryRuntimeOrchestratorとの整合）

本Releaseにおける「stateless」とは、「request単位（`apply()`呼び出しごと）のmutable stateを一切保持しない」ことを指し、「Constructor Injectionされたdependency参照を保持しない」ことを意味しない。この定義は既存precedent（`RetryRuntimeOrchestrator`が`trigger` / `scheduler` / `manager` / `queue` / `history` / `policy`の6参照をConstructorで保持しつつ、`run_once()`呼び出しごとのmutable stateを持たない設計、3.10節）と完全に一致する。

### 20.2 禁止するstate

```text
article（apply()引数）
prompt（apply()引数）
filename（apply()引数）
generated_image（generate()の戻り値）
media_result（upload()の戻り値）
戻り値ArticleData
例外object
request単位の一時値
```

### 20.3 Production Codeでの保証方法

```text
apply()は、image_generator／media_uploader以外のいかなるself属性への
    書き込みも行わない（self.article = ... 等の代入を一切持たない）
apply()はmodule-level変数への書き込みを一切行わない
apply()の関数本体は、global文・nonlocal文のいずれも使用しない
関数内で生成した中間値（generated_image／media_result／新しいArticleData）は
    いずれもローカル変数として扱われ、関数終了とともに破棄される
cache・memoizationの仕組みを一切持たない（同一prompt/filenameでの
    apply()再呼び出しでも、generate()／upload()を毎回実行する）
```

### 20.4 E2Eでの保証方法（20章で詳細化）

```text
Runtime Guard：同一Constructorインスタンスに対しapply()を複数回
    （異なるarticle/prompt/filenameで）呼び出し、1回目の呼び出しが
    2回目の呼び出し結果へ一切影響しないことを確認する
AST Guard（module-level state）：article_featured_media_orchestrator.py
    全体のASTを走査し、module-levelのAssign（クラス定義・関数定義・
    importを除く）が存在しないことを確認する
AST Guard（global／nonlocal）：apply()の関数本体（ast.FunctionDefのbody）を
    走査し、ast.Global／ast.Nonlocalノードが1件も存在しないことを確認する
AST Guard（request単位state非保存）：apply()の関数本体を走査し、
    self属性への値の設定を意味する次のいずれの構文も存在しないことを
    確認する（__init__内の self._image_generator / self._media_uploader
    への代入は対象外。v6.12.0のupload() state非保持AST Guard、3.4節の
    既存precedentと同型）：
        ast.Assign（self.xxx = ...）
        ast.AugAssign（self.xxx += ... 等の複合代入）
        ast.AnnAssign（self.xxx: T = ... 型注釈付き代入）
        setattr(self, ...) 呼び出し（ast.Call、func名がsetattrかつ
            第1引数がself）
        object.__setattr__(self, ...) 呼び出し（ast.Call、
            属性アクセスチェーンがobject.__setattr__かつ第1引数がself）
```

## 21. Dependency Direction

```text
許可：
article_featured_media_orchestration → ai_image_generation
    （AIImageGenerator, GeneratedImageの両方）
article_featured_media_orchestration → wordpress_media
    （MediaUploadResultのみ）
article_featured_media_orchestration → article_featured_media
    （bind_featured_mediaのみ）
article_featured_media_orchestration → outputs
    （ArticleDataのみ）
article_featured_media_orchestration → standard library（typing）

禁止：
article_featured_media_orchestration → openai_image_generation
article_featured_media_orchestration → wordpress_media.WordPressMediaUploader
    （具象Uploader本体は使わない。MediaUploadResult型のみ許可）
article_featured_media_orchestration → generated_image_wordpress_media
    （具象Wiring classへは依存しない。12章で確定したCapability Protocol経由のみ）
article_featured_media_orchestration → image_resolver
article_featured_media_orchestration → ai（Agent層）
article_featured_media_orchestration → pipeline
article_featured_media_orchestration → workflow_engine
article_featured_media_orchestration → scheduler
article_featured_media_orchestration → retry_*（Retry Runtime全体）
article_featured_media_orchestration → scripts
article_featured_media_orchestration → main
article_featured_media_orchestration → outputs.WordPressOutput
    （outputs.ArticleData以外は使わない）
article_featured_media_orchestration → outputs.OutputManager
article_featured_media_orchestration → requests／urllib（HTTP通信は行わない）
article_featured_media_orchestration → openai（SDK）

逆依存禁止：
ai_image_generation → article_featured_media_orchestration
openai_image_generation → article_featured_media_orchestration
wordpress_media → article_featured_media_orchestration
generated_image_wordpress_media → article_featured_media_orchestration
article_featured_media → article_featured_media_orchestration
outputs → article_featured_media_orchestration
```

```text
Dependency Diagram（Release 6.14後）

ai_image_generation          wordpress_media          outputs
  ├── AIImageGenerator          └── MediaUploadResult    └── ArticleData
  └── GeneratedImage                    │                       │
         │                              │                       │
         └──────────┬───────────────────┴───────────┬───────────┘
                     │                                │
                     │                    article_featured_media
                     │                    └── bind_featured_media()
                     │                                │
                     └────────────────┬───────────────┘
                                       ▼
                     article_featured_media_orchestration
                     ├── GeneratedImageUploadCapability（Protocol、本package内で新設）
                     └── ArticleFeaturedMediaOrchestrator
```

`generated_image_wordpress_media`・`openai_image_generation`はいずれも本Releaseから依存されない（12章で確定したCapability Protocol経由の間接的な適合のみ）。`ai_image_generation` / `wordpress_media` / `outputs` / `article_featured_media`は、本Release後も相互に依存しない（既存Dependency Graphを維持）。新規package`article_featured_media_orchestration`のみが4つのpackageすべてをimportするCaller／Adapter側になる。

### 21.1 循環importの有無

`ai_image_generation` / `wordpress_media` / `outputs` / `article_featured_media`のいずれも`article_featured_media_orchestration`をimportしないため、循環は発生しない。`article_featured_media_orchestration`はすべての依存先から見て純粋な下流（Caller）にのみ位置する。

### 21.2 WordPress固有型・OpenAI固有型の流入有無

流入しない。`ArticleData`定義（`src/outputs/base.py`）・`AIImageGenerator`定義（`src/ai_image_generation/ai_image_generator.py`）はいずれも本Releaseで一切変更しない（AD-2要件）。`OpenAIImageGenerator` / `GeneratedImageWordPressMediaUploader` / `WordPressMediaUploader`のいずれの具象型も、本Orchestratorのシグネチャには一切現れない（12章）。

## 22. Reverse Dependency Guard

```text
確認事項：
ai_image_generation（ai_image_generator.py／generated_image.py／__init__.py）が
    article_featured_media_orchestrationをimportしていないこと
wordpress_media（media_upload_result.py／wordpress_media_uploader.py／__init__.py）が
    article_featured_media_orchestrationをimportしていないこと
article_featured_media（article_featured_media_binder.py／__init__.py）が
    article_featured_media_orchestrationをimportしていないこと
outputs（base.py／wordpress_output.py／manager.py／__init__.py）が
    article_featured_media_orchestrationをimportしていないこと
```

確認方法（v6.13設計書20章のvacuous pass防止手順を踏襲）：新規E2Eにおいて、次の順序で検証する。

```text
1. 対象directory（src/ai_image_generation/, src/wordpress_media/,
   src/article_featured_media/, src/outputs/）がそれぞれ存在することを確認する
2. 各directory配下の.pyファイル一覧を取得する
3. 各directoryについて、取得した.pyファイル一覧が1件以上であることを
   Assertionする（vacuous pass防止）
4. 手順3を通過した全.pyファイルをAST走査する
5. article_featured_media_orchestrationへの絶対import
   （import article_featured_media_orchestration／
   from article_featured_media_orchestration import ...）が
   存在しないことをAssertionする
```

本プロジェクトでは対象4packageはいずれも`src`直下のtop-level packageであり、相対importによって`article_featured_media_orchestration`へ到達する経路は構造的に存在しない（v6.13設計書20章と同一の理由）。そのため絶対importのみを検査対象とする。

AST走査（`ast.Import` / `ast.ImportFrom`）は、`import article_featured_media_orchestration as x`のようなalias import（`as`句によるローカル名の変更）についても、AST上のノードが記録するmodule名自体（`asname`ではなく`name`）を参照して検出するため、alias importを見逃さない。

## 23. Security Contract

```text
image bytesを保存しない（GeneratedImage.image_bytesはgenerate()の戻り値を
    upload()へそのまま渡すだけで、self属性へも一時変数以外へも保持しない）
image bytesをlog出力しない（Loggingを一切追加しない、24章）
image bytesをreprへ含めない（GeneratedImage自体がfield(repr=False)を
    採用済み、3.2節。Orchestrator側で新たにreprへ含める操作もしない）
promptを不用意にlog出力しない（Loggingを一切追加しない）
credentialを受け取らない（Constructor引数・apply()引数のいずれにも
    credential相当の値は含まれない）
credentialを保存しない
credentialをlog出力しない
API keyを読まない（Environment Variable読込を一切行わない）
WordPress passwordを読まない
Environment Variableを読まない（os.environ／os.getenvを一切呼ばない）
HTTP requestを直接実行しない（requests／urllibを一切importしない）
filesystemへ出力しない（open()を一切呼ばない）
```

Orchestratorは、`image_generator.generate(prompt)` / `media_uploader.upload(generated_image, filename)` / `bind_featured_media(article, media_result)`へ引数を渡すだけであり、外部I/Oの詳細（credential取得・HTTP通信）はいずれもdependency側（将来のRuntime Wiring・Composition Root）の責務であり、Orchestrator自身はそれを一切知らない。

## 24. Prohibited Behavior（禁止事項）

Release 6.14 Production実装に対する禁止事項を次のとおり確定する。

```text
try／except（dependency呼び出しをラップする用途）
raise ... from ...
retry
sleep
loop（for／while、および list／set／dict comprehension・generator expression。
    呼び出し順序は直線的な逐次呼び出しのみで表現し、いかなる反復構造・
    comprehension構文も必要としない）
thread
async
scheduler
subprocess
HTTP（requests／urllib）
Environment Variable（os.environ／os.getenv）
credential（API key／password文字列の直接保持・読込）
filesystem I/O（open）
logging（logging module）
print
cache（functools.lru_cache等のmemoization）
module state（module-levelのmutable変数）
global
nonlocal
singleton（module-levelでのOrchestratorインスタンス保持）
OpenAI SDK import（openai）
requests import
urllib import
main.py import
image_resolver import
pipeline import
retry_* package import（全19package）
scheduler import
workflow_engine import
WordPressOutput import
OutputManager import
generated_image_wordpress_media import（12章で確定：具象Wiring classへ依存しない）
openai_image_generation import
```

**許可対象として整理する標準library import**：`typing.Protocol`（`GeneratedImageUploadCapability`のProtocol定義に必要）。それ以外の標準libraryのimportは本Releaseの責務上不要である（`dataclasses`は`bind_featured_media()`へ完全委譲するため本package内では不要、19章）。

## 25. Production File Plan

```text
新規（Production Code、実装工程で作成。本Architecture Design工程では作成しない）：
    projects/03_game_content_ai/src/article_featured_media_orchestration/__init__.py
    projects/03_game_content_ai/src/article_featured_media_orchestration/
        article_featured_media_orchestrator.py

新規（Test、実装工程で作成。本Architecture Design工程では作成しない）：
    projects/03_game_content_ai/tests/
        test_e2e_v6_14_0_article_featured_media_orchestration_foundation.py

変更：
    なし

削除：
    なし
```

本Architecture Design工程では、上記いずれのファイルも作成していない。本文書（設計書1件）のみが本工程の成果物である。

### 25.1 Implementation実績（Production Implementation工程で反映）

```text
作成Production file（2件）：
    projects/03_game_content_ai/src/article_featured_media_orchestration/__init__.py
        （19行）
    projects/03_game_content_ai/src/article_featured_media_orchestration/
        article_featured_media_orchestrator.py（74行）

作成Test file（1件）：
    projects/03_game_content_ai/tests/
        test_e2e_v6_14_0_article_featured_media_orchestration_foundation.py

変更：なし（既存Production Code・既存Test Code・既存設計書・ROADMAP.md・
    architecture.md・CHANGELOG.md・.env.exampleはいずれも無改修）
削除：なし
```

`article_featured_media_orchestrator.py`は、10章のPublic APIコードブロック・15章のValidation
Contractコードブロック・14章のRuntime／Call Sequenceで確定した処理順序を、そのままProduction
Codeへ転記する形で実装した。Constructor（`__init__`）は
`image_generator`のcapability検証 → `media_uploader`のcapability検証 →
`self._image_generator`代入 → `self._media_uploader`代入、という16章のConstructor順序を
厳密に踏襲し、Validationに成功する前に片方のdependencyだけをselfへ保存しない構造（15.1節）を
維持した。`apply()`は article型検証 → prompt型検証 → prompt空白検証 → filename型検証 →
filename空白検証 → `generate()` → `upload()` → `bind_featured_media()` → returnという16章の
順序をそのまま8つの逐次文として実装し、`try`／`except`・`for`／`while`・comprehension・
`global`／`nonlocal`・module-level Assignのいずれも使用しない（24章・27章）。

固定Error Message 7種（15.3節）・Dependency Direction（21章：`typing.Protocol`／
`ai_image_generation.{AIImageGenerator, GeneratedImage}`／`wordpress_media.MediaUploadResult`／
`article_featured_media.bind_featured_media`／`outputs.ArticleData`のみ）は、実装後に
grepで禁止キーワード（`async`／`await`／`thread`／`sleep`／`subprocess`／`scheduler`／
`functools`／`singleton`／`import os`／`import logging`／`import requests`／
`import urllib`／`import openai`／`dataclasses`／`print(`／`open(`）が1件も含まれないことを
再確認した（0件）。

## 26. E2E Test Strategy

想定新規E2Eファイル：`tests/test_e2e_v6_14_0_article_featured_media_orchestration_foundation.py`

**実行方式**：既存precedent（v6.9.0〜v6.13.0）と同様、`pytest`は使用せず、Pythonスクリプトとして直接実行し、`check()`系helperで結果を集計する方式を採用する。

### 26.1 正常系Scenario候補

```text
Public import：from article_featured_media_orchestration import
    ArticleFeaturedMediaOrchestrator, GeneratedImageUploadCapability が成功すること

Constructor Injection成功：image_generator／media_uploaderの両方がcapabilityを
    満たすFake（generate() / upload()を持つ単純なtest double）である場合、
    構築が成功すること

正常系Runtime Flow：
    apply(article, prompt, filename) が新しいArticleDataを返すこと
    promptがgenerate()へ同一value（文字列として同一）で渡ること
    Fake generate()が返したGeneratedImageが、そのままupload()の
        image引数へ渡ること（object identityで確認）
    filenameがupload()へ正確に渡ること（同一value）
    Fake upload()が返したMediaUploadResultが、そのままbind_featured_media()の
        media_result引数へ渡ること
    Fake bind_featured_media相当（または実bind_featured_mediaを使用する場合は
        media_idの反映結果）がArticleData.featured_media_idへ反映されること
    元ArticleDataが不変であること（呼び出し前後で全field比較）
    戻り値が入力articleとは別objectであること（is比較でFalse）
    featured_media_id以外の全fieldが既存値のまま引き継がれること
    item（NewsItem）が同一object参照のまま引き継がれること（deep copyしない、
        bind_featured_media()のContractがそのまま反映される）
    同一media_idであっても新しいArticleData objectが返ること（is比較）
```

**bind_featured_media()の扱い**：正常系Scenarioでは実際の`article_featured_media.bind_featured_media()`をそのまま呼び出す（モック化しない）。理由：Single Source of Truth（AD-7・19章）を検証するには、実際の`bind_featured_media()`のContract（不変性・決定的上書き）がOrchestrator経由でも正しく機能することを確認する必要がある。`image_generator` / `media_uploader`の2つのみをFake化し、`bind_featured_media`は実装をそのまま利用する。

### 26.2 呼び出し順序Scenario候補

```text
generate → upload → bind → returnの順序で呼ばれることを、呼び出し記録
    （順序を記録するFake、例：呼ばれるたびにリストへmethod名を追記する
    RecordingFake）で確認する
各dependency（generate／upload）が正常系apply()呼び出し1回につき
    正確に1回だけ呼ばれることを確認する（呼び出し回数カウント）
```

### 26.3 画像生成失敗Scenario候補

```text
generateが任意のsentinel exception（テスト専用の一意なException subclass）を
    送出する
同一exception objectが無変換伝播すること（例外のtype・args・identityを確認）
media_uploader.upload()が呼ばれていないこと（呼び出し回数0を確認）
    bind_featured_media相当の処理が呼ばれていないこと
元ArticleDataが不変であること
```

### 26.4 Upload失敗Scenario候補

```text
image_generator.generate()は1回呼ばれ、正常にGeneratedImageを返すこと
media_uploaderがsentinel exceptionを送出する
同一exception objectが無変換伝播すること
bind_featured_media相当の処理が呼ばれていないこと
元ArticleDataが不変であること
```

### 26.5 Binding失敗Scenario候補

```text
image_generator.generate()・media_uploader.upload()はいずれも正常に完了し、
    Fake media_uploader.upload()が意図的に不正なMediaUploadResult
    （例：media_id=0）を返すことで、実bind_featured_media()の既存Validation
    （v6.13.0、media_id 1未満はValueError）を自然に発火させる
既存bind_featured_media()由来のValueError（固定message
    "media_result.media_id must be a positive int"）が無変換伝播すること
```

既存componentやdataclassを不正に改変してBinding失敗を作らない（指示どおり、Fakeが返す`MediaUploadResult`の値のみで自然にBinding失敗を誘発する）。

### 26.6 Validation Scenario候補

```text
Constructor：
    image_generatorがgenerate属性を持たない → TypeError（固定message完全一致）
    image_generatorのgenerateがcallableでない（例：属性は存在するが
        int等の非callable値） → TypeError（固定message完全一致）
    media_uploaderがupload属性を持たない → TypeError（固定message完全一致）
    media_uploaderのuploadがcallableでない → TypeError（固定message完全一致）

apply()：
    articleがArticleDataでない → ValueError（固定message完全一致）
    promptがstrでない（int／None／bytes等） → ValueError（固定message完全一致）
    promptが空文字列 → ValueError（固定message完全一致）
    promptが空白のみ文字列 → ValueError（固定message完全一致）
    filenameがstrでない（bytes／pathlib.Path等） → ValueError（固定message完全一致）
    filenameが空文字列 → ValueError（固定message完全一致）
    filenameが空白のみ文字列 → ValueError（固定message完全一致）

Validation Order：
    articleとprompt双方が不正な場合、articleの検証由来のValueErrorのみが
        送出されること
    articleが正当でpromptが不正な場合、prompt型検証由来のValueErrorが
        送出されること
    article・prompt双方が正当でfilenameが不正な場合、filename型検証由来の
        ValueErrorが送出されること

Validation失敗時にdependency未呼び出し：
    上記いずれのValidation失敗時も、image_generator.generate() /
        media_uploader.upload()が一切呼ばれていないこと（呼び出し回数0）
```

### 26.7 Dependency／静的Guard Scenario候補

```text
Reverse Dependency Guard（22章）：
    src/ai_image_generation/・src/wordpress_media/・
        src/article_featured_media/・src/outputs/それぞれについて、
        走査対象の.pyファイル一覧が1件以上であることを先にAssertionした
        うえで（vacuous pass防止）、article_featured_media_orchestrationを
        importしていないことをAST Guardで確認する

禁止import Guard（21章・24章）：
    article_featured_media_orchestrator.pyのimportが
        ai_image_generation（AIImageGenerator, GeneratedImage）・
        wordpress_media（MediaUploadResultのみ）・
        article_featured_media（bind_featured_mediaのみ）・
        outputs（ArticleDataのみ）・typing に限られること（AST Guard）
    禁止import（openai, openai_image_generation, generated_image_wordpress_media,
        wordpress_media.WordPressMediaUploader（module全体importの禁止という
        形では表現できないため、wordpress_media importがMediaUploadResultのみに
        限定されることをAST ImportFromのnames検査で確認する）、
        requests, urllib, os, logging, subprocess, image_resolver, ai,
        pipeline, workflow_engine, scheduler, retry_*, scripts, main）が
        存在しないこと

main.py未接続Guard：
    main.pyがarticle_featured_media_orchestrationをimportしていないこと
image_resolver.py未接続Guard：
    src/image_resolver.pyがarticle_featured_media_orchestrationを
        importしていないこと
pipeline未接続Guard：
    src/pipeline/配下のいずれのファイルもarticle_featured_media_orchestrationを
        importしていないこと
retry未接続Guard：
    src/retry_*配下（全19package）のいずれのファイルも
        article_featured_media_orchestrationをimportしていないこと
scripts未接続Guard：
    scripts/配下のいずれのファイルもarticle_featured_media_orchestrationを
        importしていないこと
    （上記5つのGuardは、本Releaseが生成した新規ファイルであるため、
     既存ファイル側のこれらのimportは本Releaseの実装によって発生
     しようがないが、v6.13設計書25.1節と同様、Zero Diff Policyの成立を
     裏付ける確認として実施する）

OpenAI SDK禁止Guard／HTTP library禁止Guard／Environment Variable禁止Guard／
logging・print禁止Guard／try・except禁止Guard／global・nonlocal禁止Guard／
module state禁止Guard：
    いずれもAST走査（ast.Import／ast.ImportFrom／ast.Try／ast.Global／
    ast.Nonlocal／module-levelast.Assign／ast.Call名探索）で機械的に検証する
    （v6.9.0〜v6.13.0の既存precedentに倣う）

Protocol構造互換性Guard（静的、GeneratedImageWordPressMediaUploaderとの
    シグネチャ一致確認）：
    inspect.signature(GeneratedImageWordPressMediaUploader.upload)と
        inspect.signature(GeneratedImageUploadCapability.upload)を比較し、
        パラメータ名の並び（self除く：image, filename）が完全一致することを
        Assertionする（importのみ行い、いずれのclassも実際にconstruct・
        呼び出ししない、Runtime非依存の静的比較）
    本Guardは、将来GeneratedImageWordPressMediaUploader.upload()の
        シグネチャが変更された場合に、GeneratedImageUploadCapability
        （本Release新設Protocol）との構造的適合が崩れたことを検出する
        唯一の自動化された手段である。32章Riskで言及する「構造的適合の
        確認手段」は、本Guardを指す（26.10節のScope外テスト「実
        GeneratedImageWordPressMediaUploaderを用いた統合テスト」とは
        異なり、実際にconstructor・upload()を呼び出さない静的signature比較
        であるため、Scope外の対象外＝本Releaseの新規E2Eに含める）
```

### 26.8 Security Scenario候補

```text
画像bytes非保存：Fake GeneratedImageのimage_bytesが、apply()呼び出し後の
    Orchestratorインスタンスのいかなるself属性にも保持されていないこと
    （インスタンスの__dict__を検査し、image_generator／media_uploader
    参照以外のkeyが存在しないことを確認する）
画像bytes非ログ：logging importが存在しないことをAST Guardで確認する
    （26.7節と共通）
credential fieldなし：ArticleFeaturedMediaOrchestratorのインスタンスが
    保持する属性が image_generator参照／media_uploader参照の2つのみで
    あることを確認する
Environment Variable参照なし：os.environ／os.getenv呼び出しがAST Guardで
    検出されないこと
HTTP処理なし：requests／urllib importが存在しないことをAST Guardで
    確認すること
filesystem I/Oなし：open()呼び出しがAST Guardで検出されないこと
```

### 26.9 Fake／Stub方針

```text
実OpenAI APIを呼ばない（OpenAIImageGeneratorを一切importしない、
    テスト専用の単純なFake classのみを使用する）
実WordPress APIを呼ばない（WordPressMediaUploader／
    GeneratedImageWordPressMediaUploaderを一切importしない）
課金を発生させない
networkを使わない
Environment Variableを使わない
dependencyの呼び出し記録が可能（呼び出し回数・引数・呼び出し順序を
    記録するRecordingFakeパターンを採用する）
sentinel object／sentinel exceptionを使用可能（一意性を保証するため、
    テストモジュール内で専用のException subclassおよびsentinel値
    （object()等）を定義する）
```

### 26.10 Scope外テスト

明示的に次をScope外とし、本Release（v6.14.0）の新規E2Eには含めない。

```text
main.py Runtime Wiring
WordPress投稿payload
画像機能有効化フラグ
fallback
DEFAULT_MEDIA_ID
Retry
重複Upload
idempotency
Media cleanup
rollback
Upload成功後の記事投稿失敗
実OpenAIImageGenerator・実WordPressMediaUploader・実GeneratedImageWordPressMediaUploaderを
    構築・呼び出しする統合テスト（実際にconstructor・generate()／upload()を
    呼び出す動作確認は、将来のRuntime Wiring Releaseで実施する）
```

ただし、26.7節の「Protocol構造互換性Guard（静的）」は上記Scope外テストとは異なり、`GeneratedImageWordPressMediaUploader`を実際に構築・呼び出しせず、`inspect.signature`によるシグネチャの静的比較のみを行うため、本Releaseの新規E2Eに含める（Scope外としない）。

### 26.11 新規E2E実績（Production Implementation工程で反映）

```text
実行ファイル：tests/test_e2e_v6_14_0_article_featured_media_orchestration_foundation.py
実行方法：python tests/test_e2e_v6_14_0_article_featured_media_orchestration_foundation.py
    （cd projects/03_game_content_ai の後に実行）
実行結果：217/217 PASS、0 FAIL、終了コード0、意図しないWarning・Traceback なし

Scenario数（独立scenario、ヘッダーコメント記載）：34
    PUB-1 / SIG-1 / CTOR-1 / CAP-1〜4 / CTOR-PROP-1/2 / CTOR-ORDER-1 /
    CTOR-ORDER-AST-1 / NORM-1 / IMMUT-1 / VAL-ARTICLE-1 / VAL-PROMPT-1/2 /
    VAL-FILENAME-1/2 / VAL-ORDER-1/2/3 / VAL-NOCALL-1 / STRSUB-1 / GENFAIL-1 /
    UPLOADFAIL-1 / BINDFAIL-1 / PROTO-1 / STATE-1 / STATE-AST-1 / LOOP-AST-1 /
    TRY-AST-1 / GLOBAL-AST-1 / MODULE-AST-1 / SEC-1 / DEP-1 / DEP-2 /
    RUNTIME-1 / SIDE-1

for文ブロック数（module-levelトップレベル、AST機械集計）：15
    うちValidation展開用for文ブロック数：7
        （CAP-1〜3, CAP-4a〜c, VAL-ARTICLE-1, VAL-PROMPT-1, VAL-PROMPT-2,
         VAL-FILENAME-1, VAL-FILENAME-2）
    うちGuard関連for文ブロック数：8
        （SEC-1×2, DEP-1, DEP-2, RUNTIME-1×3, SIDE-1）
    ネストを含めた全ast.For数（AST utility関数内の11件を除く）：21

Validation展開case総数（AST機械集計、各case毎に2 Assertion）：25
    image_generator capability: 3 / media_uploader capability: 3 /
    article型不正: 3 / prompt型不正: 3 / prompt空白: 5 /
    filename型不正: 3 / filename空白: 5

静的check系呼出数（source上のcheck*()呼出箇所のうちfor文の外側、
    AST機械集計。1箇所につき実行時1回のみ）：111
実行時Assertion数（results_logへの実記録件数、実行結果と一致）：217
    （111件の静的呼出＋ループ内呼出箇所29件がネストを含む反復により
     実行時106回に展開＝217。ネストしたループ（例：SIDE-1の
     FILES.items()×禁止import 7種／禁止call 4種）による多重展開を含む）

Fake数：6（_RecordingImageGenerator, _RecordingMediaUploader,
    _FailingImageGenerator, _FailingMediaUploader,
    _PropertyRaisingGenerateGenerator, _PropertyRaisingUploadUploader）
Stub数：6（_MissingGenerateGenerator, _NoneGenerateGenerator,
    _StringGenerateGenerator, _MissingUploadUploader, _NoneUploadUploader,
    _StringUploadUploader）
その他test double：str subclass 2件（_PromptStr, _FilenameStr）、
    sentinel exception class 3件（_SentinelGenerateError,
    _SentinelUploadError, _SentinelPropertyError）

集計方法：いずれもtests/test_e2e_v6_14_0_article_featured_media_orchestration_foundation.py
    をast.parse()した結果に対しPythonスクリプトで機械的に算出した（目視推測ではない）。
    実行時Assertion数は、実行結果（results_logの件数）と機械集計値が完全一致することを
    確認済み。

実HTTP・実OpenAI API・実WordPress API・実credential読込・実課金：いずれもなし
    （image_generator／media_uploaderはすべてFake、bind_featured_media()のみ実装を
     使用、PROTO-1はGeneratedImageWordPressMediaUploaderをimportしてsignatureのみ
     参照し、構築・呼出は行わない）
```

## 27. Static／AST Guard Strategy

State非保持とSide Effect非存在は、v6.9.0〜v6.13.0の既存precedent（`ast.Import` / `ast.ImportFrom` / `ast.Call` / `ast.Global` / `ast.Nonlocal`によるDependency Guard・Side Effect Guard・State Guard）に倣い、AST解析で機械的に検証する。

```text
採用するGuard：
    module-levelのAssign文が存在しないこと（20.3節）
    apply()の関数本体にast.Global／ast.Nonlocalが存在しないこと（20.3節）
    __init__()以外でself属性への値の設定（ast.Assign／ast.AugAssign／
        ast.AnnAssign／setattr(self, ...)／object.__setattr__(self, ...)の
        いずれか）が存在しないこと（request単位state非保持、20.3節・20.4節）
    禁止import（openai, requests, urllib, os, logging, subprocess,
        generated_image_wordpress_media, openai_image_generation,
        image_resolver, main, pipeline, retry_*, scheduler, workflow_engine,
        scripts）が存在しないこと
    open() / print() / sleep()呼び出しが存在しないこと
    try/except（ast.Try）が存在しないこと
    for/while（ast.For／ast.While）およびcomprehension／generator expression
        （ast.ListComp／ast.SetComp／ast.DictComp／ast.GeneratorExp）が
        存在しないこと（apply()の処理は6ステップの直線的な逐次呼び出しのみで
        表現でき、いかなる反復構造も必要としないため、for/whileと同様に
        comprehension・generator expressionも禁止対象に含める。本Guardは
        Production Code（article_featured_media_orchestrator.py）のみを
        対象とし、新規E2E側のテストコード・Fake実装（26章）内でのループ・
        comprehension使用は本Guardの対象外とする）
    Dependency Direction（21章）で許可されたimport以外が存在しないこと
    Protocol構造互換性（inspect.signatureによる静的比較、26.7節）：
        GeneratedImageWordPressMediaUploader.uploadとGeneratedImageUploadCapability.upload
        のパラメータ名の並びが一致すること（実際の呼び出し・構築は行わない）

採用しないGuard：
    Constructor capability検証（getattr + callable）の実装手段そのものを
        固定するGuard（Contract（capability不足時にTypeErrorを送出する）
        さえ満たせば、実装の内部手段は将来変更を妨げない）
    dependency呼び出し時のkeyword引数名を固定するGuard（image_generator.generate()
        呼び出しがpositional引数かkeyword引数かは、AIImageGenerator Protocol
        Contract自体が固定していないため、本Guardでは検証しない）
```

vacuous pass防止（22章のReverse Dependency Guardと同様の手順）を、対象ファイル一覧の非空検証を伴う形で全AST Guardへ適用する。

## 28. Formal Regression Strategy

正式Regressionの基準は、Release 6.13完了時点の`docs/CHANGELOG.md`記載の実測値を参照する（Architecture Design時点のbaselineとして記載する。過去のHistorical Recordは変更しない）。

```text
Release 6.13完了時点の正式Regression（docs/CHANGELOG.md [v6.13.0] Testedセクション確認済み）：
    対象：16ファイル（既存15ファイル＋v6.13.0新規E2E）
    総合：2054/2054 PASS

Release 6.14実装後に想定するもの：
    Release 6.13までの正式Regression（16ファイル、2054件）：2054/2054 PASS維持
    Release 6.14新規E2E：全PASS
    Warning：0件
    終了コード非0：0ファイル
    実行対象合計：17ファイル（既存16ファイル＋新規v6.14.0 E2E 1ファイル）
```

対象16ファイルの内訳（`docs/CHANGELOG.md:435-449`確認済み）：`test_e2e_v1_11_0_save_result.py`（1件）／`test_e2e_v5_9_0_*.py`（1件）／`test_e2e_v6_0_0_*.py` 〜 `test_e2e_v6_13_0_*.py`（v6.0.0〜v6.13.0の連番14ファイル）＝合計16ファイル。正確な最新baselineは、本Releaseの実装工程開始時点で`docs/CHANGELOG.md`の最新Entryを再確認して採用する。

本Architecture Design工程ではテストを実行しない（Production実装・E2E作成・Formal Regression実行はいずれも別工程の責務であり、本工程のScope外である）。

### 28.1 Formal Regression実績（Formal Regression工程で反映）

```text
実行日：2026-07-18
正式対象：17ファイル（既存16ファイル＋新規v6.14.0 E2E 1ファイル）
実行方式：各ファイルを個別に`python tests/<file>`で実行（一括実行なし、
    結果混在なし）
実行順序：v1.11.0 → v5.9.0 → v6.0.0 → v6.1.0 → v6.2.0 → v6.3.0 → v6.4.0 →
    v6.5.0 → v6.6.0 → v6.7.0 → v6.8.0 → v6.9.0 → v6.10.0 → v6.11.0 →
    v6.12.0 → v6.13.0 → v6.14.0
```

Version別実測結果（すべて終了コード0、Warning 0、Traceback 0）：

```text
v1.11.0（test_e2e_v1_11_0_save_result.py）：            43/43 PASS（0.29秒）
v5.9.0（test_e2e_v5_9_0_retry_runtime_loop_wiring_foundation.py）：
                                                          64/64 PASS（2.00秒）
v6.0.0（test_e2e_v6_0_0_retry_runtime_lock_foundation.py）：
                                                          43/43 PASS（1.46秒）
v6.1.0（test_e2e_v6_1_0_retry_runtime_graceful_shutdown_foundation.py）：
                                                          44/44 PASS（3.29秒）
v6.2.0（test_e2e_v6_2_0_structured_loop_logging_foundation.py）：
                                                          64/64 PASS（0.53秒）
v6.3.0（test_e2e_v6_3_0_retry_metrics_foundation.py）：  174/174 PASS（0.54秒）
v6.4.0（test_e2e_v6_4_0_retry_monitoring_foundation.py）：
                                                          171/171 PASS（0.57秒）
v6.5.0（test_e2e_v6_5_0_retry_alert_foundation.py）：    131/131 PASS（0.28秒）
v6.6.0（test_e2e_v6_6_0_retry_notification_foundation.py）：
                                                          135/135 PASS（0.13秒）
v6.7.0（test_e2e_v6_7_0_retry_notification_message_foundation.py）：
                                                          117/117 PASS（0.13秒）
v6.8.0（test_e2e_v6_8_0_retry_notification_cli_report_wiring_foundation.py）：
                                                          197/197 PASS（0.40秒）
v6.9.0（test_e2e_v6_9_0_wordpress_media_upload_foundation.py）：
                                                          331/331 PASS（0.26秒）
v6.10.0（test_e2e_v6_10_0_ai_image_generation_contract_foundation.py）：
                                                          78/78 PASS（0.13秒）
v6.11.0（test_e2e_v6_11_0_openai_image_generation_adapter_foundation.py）：
                                                          248/248 PASS（0.91秒）
v6.12.0（test_e2e_v6_12_0_generated_image_wordpress_media_upload_wiring_foundation.py）：
                                                          91/91 PASS（0.23秒）
v6.13.0（test_e2e_v6_13_0_article_featured_media_binding_foundation.py）：
                                                          123/123 PASS（0.26秒）
v6.14.0（test_e2e_v6_14_0_article_featured_media_orchestration_foundation.py）：
                                                          217/217 PASS（0.29秒）
```

集計（Pythonスクリプトによる機械的再計算で確認済み）：

```text
既存16ファイル対象数：16
既存PASS合計：2054（Release 6.13完了時点baseline 2054/2054と完全一致）
新規v6.14.0対象数：1
新規v6.14.0 PASS：217（Code Review時点の実測217/217と完全一致、Reporting
    差異なし）
総合対象数：17
総合PASS合計：2271
FAIL合計：0
Warning合計：0（Python標準の`XWarning:`形式出力・`warnings`モジュール出力
    いずれも17ファイル全ログで0件、grep機械確認済み。テスト内の
    "WARNING"という文字列一致はRetryAlertLevel等のContract文言としての
    出現であり、Python runtime warningではないことを個別確認した）
Traceback出力：0件（17ファイル全ログでgrep機械確認済み）
終了コード非0：0ファイル
重複実行・二重集計：なし（各ファイル1回のみ実行）
```

Formal Regression判定：**PASS**（15章の完了条件をすべて満たす：正式対象17
ファイル全実行・各終了コード0・全Assertion PASS・FAIL 0・Warning 0・対象
漏れなし・重複実行なし・既存16ファイル合計2054・新規v6.14.0合計217・
総合2271・想定外ファイル変更なし）。

CR14-S-1（21章と22章のReverse Dependency Guard対象package数の差異、
Non-Blocking Suggestion）への影響：なし。本Formal Regressionでは21章・
22章・Production Code・新規E2Eのいずれも変更していない。CR14-S-1は
Non-Blockingのまま維持する（Resolvedへは変更しない）。

過去Release（v1.11.0〜v6.13.0）の実測値・日付・Historical Recordはいずれも
本工程で変更していない。上記16ファイルの実測値は、既存`docs/CHANGELOG.md`
記載のbaseline値との一致を確認するために本Formal Regression実行で得られた
実測値であり、`docs/CHANGELOG.md`自体は本工程で変更していない。

## 29. Documentation Integration Plan（将来工程の予告）

本Architecture Design工程では文書統合を行わない（ROADMAP.md・architecture.md・CHANGELOG.mdはいずれも本工程で変更しない、禁止事項）。将来のDocumentation Integration工程（本Releaseの実装完了後）で、次を反映する想定を記録するのみとする。

```text
docs/ROADMAP.md：v6.14.0実績としてArticle Featured Media Orchestration
    Foundationを追加し、次候補「Article Featured Media Runtime Wiring」の
    前提条件充足を明記する
docs/architecture.md：article_featured_media_orchestration component節を
    新設し、Consumer-less Foundation・Runtime未接続を明記する
docs/CHANGELOG.md：[v6.14.0] Entryを新規追加する
```

### 29.1 Documentation Integration実績（Documentation Integration工程で反映）

```text
実行日：2026-07-18
更新文書：
    docs/ROADMAP.md（v6.13.0エントリ直後にv6.14.0実績[x]を追加、
        「Article Featured Media Runtime Wiring」候補の前提Releaseを
        v6.13.0からv6.14.0へ更新、Future Candidates 7件を追加）
    docs/architecture.md（末尾へ「Article Featured Media Orchestration層」
        節を新設。Purpose／Package Boundary／Public API／Constructor・
        apply() Validation順序／依存関係／Error Contract／State非保持
        Contract／Security Contract／Backward Compatibility／
        Out of Scope／Test Review・Code Review・Regression実績／
        Future Extensionを記載）
    docs/CHANGELOG.md（[v6.13.0]の直前に[v6.14.0] Entryを新規追加。
        Release状態が`In Progress`でRelease Review未実施であることを
        Entry冒頭のblockquoteで明記）
    docs/design/article_featured_media_orchestration_foundation.md
        （本文書。Header・29.1節・Review Historyへ反映）

反映内容：
    Release 6.14実績（Version・正式名称・分類）
    Public API（ArticleFeaturedMediaOrchestrator, GeneratedImageUploadCapability、
        引数名・順序・戻り値を3文書・正式設計書間で完全一致させた）
    Architecture Contract（Class＋Constructor Injection、generate→upload→bind、
        Protocol依存、ArticleData不変性、例外無変換伝播、Consumer-less）
    Validation／Error Contract（固定message7種はarchitecture.md・CHANGELOG.mdへ
        全件記載、ROADMAP.mdは要点のみの粒度とした）
    新規E2E実績（217/217 PASS、34シナリオ。詳細集計は正式設計書26.11節に
        維持し、3文書へは要点のみ記載）
    Formal Regression実績（2271/2271 PASS、17ファイル。Version別内訳は
        正式設計書28.1節に維持し、3文書へは総合値のみ記載）
    Architecture Review結果（Approved、Blocking Issueなし）
    Code Review結果（Approved with Suggestions、CR14-S-1をNon-Blockingの
        まま3文書・正式設計書間で一貫して記載）
    Consumer-less状態（main.py／image_resolver.py／WordPressOutput／
        OutputManager／Composition Root／Pipeline／Workflow／Scheduler／
        Retry Runtime／scriptsいずれも未接続である旨を、architecture.mdの
        blockquote・ROADMAP.mdの次候補説明・CHANGELOG.mdのOut of Scope
        欄で重複を避けつつ記載）
    Future Candidates（Article Featured Media Runtime Wiringを筆頭に、
        Publish Composition Root Foundation等7件をROADMAP.mdへ追加）

Historical Record変更：なし（Release 6.13以前のCHANGELOG Entry・ROADMAP
    完了記録・architecture.md既存節・過去Review Historyのいずれも変更して
    いない。既存v1.11.0〜v6.13.0のTested値・日付も無変更）
CR14-S-1：Non-Blockingのまま維持（Resolved・Known Issue・Open Questionへの
    昇格はいずれも行っていない）
Release状態：`In Progress`のまま維持（Release Review未実施のため
    `Completed`へは移行していない。「Runtime Wiring完了」「main.py接続済み」
    「画像自動生成が本番稼働済み」等の誤った表現はいずれの文書にも記載して
    いない）
Blocking Issue：なし
```

## 30. Acceptance Criteria

```text
[ ] Release GoalがOrchestration（既存4 Foundationの呼び出し順序管理）
    だけに限定されている（5章）
[ ] Public APIが確定している（ArticleFeaturedMediaOrchestrator,
    GeneratedImageUploadCapability、10章）
[ ] dependency型が確定している（AIImageGenerator,
    GeneratedImageUploadCapability、10章・12章）
[ ] Constructor Injection方針が確定している（11章）
[ ] prompt／filename責務が確定している（Callerから受け取るのみ、13章）
[ ] Validation順序が確定している（16章）
[ ] Error Contractが固定されている（17章、7種の固定message）
[ ] 例外無変換伝播が明記されている（17章・18章）
[ ] 正常系呼び出し順序が固定されている（generate→upload→bind、14章）
[ ] 失敗後の後続処理禁止が固定されている（14章・18章）
[ ] ArticleData不変性が維持される（19章、bind_featured_media()への完全委譲）
[ ] bind_featured_mediaをSingle Source of Truthとして利用する（AD-7・19章）
[ ] OpenAI固有Adapterへ依存しない（AIImageGenerator Protocolのみ、8.2節相当・21章）
[ ] Runtimeへ接続しない（main.py／image_resolver.py／WordPressOutput／
    OutputManager／Pipeline／Composition Root／Retry Runtime／scriptsのいずれも
    未接続、3.9節で再確認済み）
[ ] Reverse Dependencyが発生しない（22章）
[ ] HTTP／Environment Variable／credentialを扱わない（23章・24章）
[ ] Retry／fallback／cleanupを含めない（7章）
[ ] E2E Test Strategyが実装可能な粒度で定義されている（26章）
[ ] vacuous pass防止策が含まれる（22章・27章）
[ ] 既存Release 6.9〜6.13 Contractと矛盾しない（3章で再確認済み）
```

## 31. Alternatives Considered

### 31.1 Public API形状（11章の再掲・補足）

11章で比較したClass／module-level function／dataclass based service／Callable compositionの4案のうち、Class＋Constructor Injectionを採用した。不採用理由は11章のとおり。

### 31.2 apply()以外のmethod名候補

| 候補 | 却下／採用理由 |
|---|---|
| **`apply`（採用）** | 「このOrchestration操作をこのArticleDataへ適用する」という意味が、引数`article`を主語とした自然な動詞として読み取れる。ユーザー提示の候補と一致する |
| `execute` | `RetryExecutor.execute()`（既存、retry_engine）と同名になり、両者の責務（Retry実行 vs 画像/Media/Binding Orchestration）が異なるにもかかわらず混同されるリスクがある |
| `run` | `RetryRuntimeOrchestrator.run_once()`と語感が近く、「1サイクル実行」という別の意味との混同を避けるため不採用。本Releaseは「1記事に対する処理」であり「1サイクル」という周期的実行のニュアンスを持たない |
| `orchestrate` | class名自体に`Orchestrator`が含まれるため、`orchestrator.orchestrate()`という冗長な表現になる |
| `generate_and_bind_featured_media` | 処理内容（generate・upload・bind）をすべて列挙すると名前が長くなり、将来ステップが増減した場合に名前の追随が必要になる。`apply()`のような抽象度の高い名前の方が変更に強い |

### 31.3 Uploader Dependency（12章の再掲）

12章で比較した案A（具象class依存）・案B（最小Capability Protocol）・案C（Callable Injection）のうち、案Bを採用した。不採用理由は12.3節・12.4節のとおり。

### 31.4 Constructor capability検証のタイミング

| 案 | 内容 | 採否 |
|---|---|---|
| **Constructor時点で検証（採用）** | `__init__()`内でcapability検証を行い、不適合ならConstructor自体が例外を送出する | **採用**（15.1節で理由を詳述） |
| apply()呼び出し時まで遅延 | `GeneratedImageWordPressMediaUploader`（v6.12.0）と同型の遅延検証 | 不採用。理由は15.1節のとおり（2 dependency・順序実行という構造上、fail-fastの価値がより高い） |

## 32. Risks

```text
本Orchestrator自身は、generate → upload → bindという内部呼び出し順序を
    apply()内で強制する（14章）ため、将来のRuntime Wiringにおいて
    Caller側がこの内部順序を意識・管理する必要はない。本Riskが対象と
    するのは内部順序ではなく、より上位の呼び出しレベルの懸念である：
    Callerがそもそもapply()を呼び出し忘れる（例：WordPress投稿の直前に
    Orchestratorを経由せず、featured_media_idが未設定のままArticleDataを
    投稿してしまう）、または同一articleに対しapply()を意図せず複数回
    呼び出す（画像の重複生成・重複Upload）といった、Orchestratorの外側で
    発生するCaller実装品質の問題である。本層自身では、apply()が
    「いつ・何回呼ばれるか」を制御できない（Foundation Firstの性質上の
    制約であり、既存v6.9.0〜v6.13.0とも共通のリスク）

GeneratedImageUploadCapability（新設Protocol）は、現時点で
    GeneratedImageWordPressMediaUploaderという唯一の具象実装候補が
    構造的に適合するかどうかを、本Architecture Design時点では机上での
    シグネチャ一致（3.4節のupload(image, filename)と10章の
    upload(self, image, filename) -> MediaUploadResult）を確認したのみで
    ある。実装工程では、26.7節「Protocol構造互換性Guard（静的）」により
    inspect.signatureベースの自動検証を新規E2Eへ組み込む。ただし本Guardは
    パラメータ名の並びのみを検証し、型注釈の実行時一致・戻り値の実際の
    互換性までは検証しない（Pythonの型注釈は実行時に強制されないため）。
    型注釈レベルの完全な互換性は型チェッカー（mypy等）による静的検証に
    委ねる（本Releaseは型チェッカーの実行自体をFormal Regressionへ
    組み込まない、28章）

Constructor時点でのcapability検証（15.1節）は、将来Runtime Wiringにおいて
    「一時的に無効なdependencyでConstructorを構築し、後から差し替える」
    ような柔軟な構成パターンを許容しない。本Releaseの用途（Consumer-less、
    Fakeによる単体テストのみ）では問題にならないが、将来のComposition Root
    設計時にこの制約が影響する可能性がある

apply()の失敗時に「どこまで進んだか」（generate成功／upload成功等）を
    Caller側が知る手段は、送出された例外の型・発生元スタックトレースの
    みである。本Releaseは進捗情報を返す専用の型（部分結果オブジェクト等）を
    持たない設計としており（17章：部分成功を成功として返さない）、
    これは意図的な設計判断だが、将来のRuntime Wiringでリトライ判断等に
    詳細な進捗情報が必要になった場合、別途の設計が必要になる
```

## 33. Known Issues

なし（本Architecture Design時点で確認されたKnown Issueはない）。

## 34. Open Questions

```text
なし
```

12章（Uploader Dependency）・31.2節（method名）・15.1節（capability検証タイミング）・15.2節（空白のみ文字列の扱い）・12.5節（新規ProtocolをPublic APIに含めるか）はいずれも本文書内で設計判断として確定済みであり、Open Questionとしては残さない。

## 35. Future Candidates

以下は、本Release完了後の別Releaseで検討する候補である。番号・正式名称は本文書で確定しない。

```text
Article Featured Media Runtime Wiring
    （ArticleFeaturedMediaOrchestrator.apply()を実際にmain.py／
     image_resolver.py等のProduction Runtimeへ接続する経路の確立）

Publish Composition Root Foundation
    （記事生成→WordPress投稿の一連の生成・配線を専用に担う、
     RetryCompositionRootと対をなすComposition Rootの新設）

Image Generation Configuration Gate
    （画像生成機能の有効／無効を切り替えるConfiguration First方式の
     環境変数ゲートの新設。AI_AGENT_ENABLED等の既存precedentに倣う）

Article Image Prompt Construction Foundation
    （記事タイトル・本文・SEO情報からpromptを構築する専用Foundation）

Generated Image Filename Policy Foundation
    （filenameの命名規則・拡張子決定方針を確立する専用Foundation）

Image Generation Fallback Policy
    （画像生成・Upload失敗時に記事投稿を継続するか中止するかの
     業務判断を確立するFoundation）

Media Upload Retry／Idempotency Foundation
    （Retry Queueのmedia_id保持field拡張、重複Upload防止、
     idempotency keyの確立。既存RetryQueueItemにmedia_id相当のfieldが
     存在しないことを踏まえ独立検討する）

WordPress Unused Media Cleanup Foundation
    （Upload成功後の記事投稿失敗時に残る未使用WordPress Mediaの
     検出・削除方針。WordPressMediaUploaderに削除APIが現状存在しない
     ことを踏まえ独立検討する）
```

次Release候補として最も近いのは「Article Featured Media Runtime Wiring」だが、v6.14.0完了後にRepositoryを再確認して正式判断するものとする。

## 36. Review Checklist（Architecture Designセルフレビュー）

```text
[x] Release名とScopeが一致しているか
    → 一致。「Orchestration Foundation」という名称どおり、既存4 Foundationの
      呼び出し順序管理のみをScopeとしている（5章・6章）

[x] FoundationとRuntime Wiringが混在していないか
    → 混在していない。main.py／image_resolver.py接続はいずれも7章で
      明示的にOut of Scope化されている

[x] Orchestration以外のBusiness Policyが混入していないか
    → 混入していない。Failure Boundary（18章）は「無変換伝播のみ」に
      限定し、継続／中止判断はOut of Scope（7章・18章）

[x] OpenAI固有依存が混入していないか
    → 混入していない。Constructor引数は AIImageGenerator Protocol型のみ
      （10章）、openai_image_generationへの依存は21章・24章で明示的に禁止

[x] WordPress HTTP詳細が混入していないか
    → 混入していない。media_uploaderはGeneratedImageUploadCapability
      Protocol型のみ（10章・12章）、requests／urllibは24章で明示的に禁止

[x] prompt生成方針が混入していないか
    → 混入していない。13章でCallerから受け取るのみと明記

[x] filename生成方針が混入していないか
    → 混入していない。13章でCallerから受け取るのみと明記

[x] fallback方針が混入していないか
    → 混入していない。18章でOut of Scopeと明記

[x] Retry／cleanup／idempotencyが混入していないか
    → 混入していない。7章・35章で明示的にFuture Candidates化

[x] Validation順序が一意か
    → 一意。16章でConstructor 2ステップ・apply() 7ステップの
      合計順序を1本のリストとして確定

[x] 固定Error Messageに矛盾がないか
    → 矛盾なし。17.3節（15.3節）で7種すべてを一覧化し、既存precedent
      （bind_featured_media・GeneratedImageWordPressMediaUploader）との
      文言一致・非一致を明示している

[x] Error ContractとE2E Strategyが一致しているか
    → 一致。26.6節のValidation Scenarioが17章・15章の全パターンを
      過不足なく網羅している

[x] Dependency Directionと禁止import Guardが一致しているか
    → 一致。21章の許可／禁止importと26.7節のAST Guard対象が同一である

[x] Public APIとProduction File Planが一致しているか
    → 一致。10章のPublic API（2 class）と25章のfile plan（1 module）が
      対応している

[x] Out of ScopeとFuture Candidatesが一致しているか
    → 一致。7章のOut of Scope各項目が、35章のFuture Candidatesの
      いずれかに対応するか、または本Releaseの範囲外として恒久的に
      対象外（例：main.py変更は35章のRuntime Wiringに対応、Retry関連は
      35章のMedia Upload Retry／Idempotency Foundationに対応）

[x] 内部章参照が正しいか
    → 本文書全体を通読し、章番号参照（例：「12章」「17章」等）が
      実際の章番号と一致することを確認した

[x] Historical Recordを書き換えていないか
    → 書き換えていない。既存設計書（v6.9.0〜v6.13.0）・ROADMAP.md・
      architecture.md・CHANGELOG.mdはいずれも参照のみで変更していない

[x] 設計書以外を変更していないか
    → 変更していない（本文書自体は最終Git確認の章を持たない。Git状態の
      確認・報告はArchitecture Design／Architecture Reviewプロセス側の
      手順として、本文書の外で別途実施する）
```

矛盾は確認されなかった。

## 37. Review History

```text
2026-07-18: Claude Code（Architecture Designドラフト初版作成）。
    Architecture Review・Code Review・Release Reviewはいずれも未実施。
    Production実装・E2E作成・文書統合・commit・pushのいずれも行っていない。

2026-07-18: Architecture Review（Claude Codeによる独立Review、初回）：Changes
    Required。Blocking Issueなし。Critical 0件・Major 0件・Minor 9件
    （AR14-m-1〜AR14-m-9）・Suggestion 1件（AR14-S-1）。

    AR14-m-1：36章セルフレビューが本文書に存在しない「38章」を参照していた。
    AR14-m-2：9.3節「19章の指示」・15.2節「Section 12の指示」（2箇所）が、
        元のArchitecture Design依頼プロンプトの章番号を指しているにも
        関わらず、本文書自身の12章（Uploader Dependency Alternatives）・
        19章（ArticleData不変性Contract）と番号が衝突し、無関係な内容と
        誤認されうる曖昧な参照になっていた。
    AR14-m-3：28章のFormal Regression baseline内訳が「v6.0.0〜v6.13.0」と
        記載しつつ、括弧内で矛盾する「v6.2.0〜v6.13.0の連番12ファイル」と
        記載しており、算術的に一致しなかった（正しくはv6.0.0〜v6.13.0の
        14ファイル、総計16ファイル）。
    AR14-m-4：32章のRisk記述「（Protocol構造適合は）実装時のE2Eでのみ
        確認できる」が、26.10節の「実GeneratedImageWordPressMediaUploaderを
        用いた統合テストはScope外」という記述と矛盾していた。また、将来の
        シグネチャdriftをvacuous passなく検出する具体的Guardが存在しな
        かった。
    AR14-m-5：Constructor capability validation（15.1節）が、`getattr()`
        呼び出し時に`generate`／`upload`が`@property`等で例外を送出した
        場合の扱いを明記していなかった。
    AR14-m-6：新設`GeneratedImageUploadCapability`に`@runtime_checkable`を
        付与しない理由が、既存`AIImageGenerator`については説明されて
        いたが、新設Protocol自身については明示的な説明がなかった。
    AR14-m-7：self属性代入Guard（20.4節・27章）が`ast.Assign`形式のみを
        言及し、`AugAssign`／`AnnAssign`／`setattr(self, ...)`／
        `object.__setattr__`等の代替形式を列挙していなかった。
    AR14-m-8：loop禁止Guard（24章・27章）がlist/dict/set comprehension・
        generator expressionへの言及を欠いていた。
    AR14-m-9：32章冒頭のRisk記述「正しい順序・タイミングで呼び出すという
        前提に依存している」という表現が、Orchestrator自身が内部順序
        （generate→upload→bind）を保証するにも関わらず、Callerが内部順序を
        意識する必要があるかのように誤読されうる曖昧な表現だった。
    AR14-S-1（Suggestion）：22章のReverse Dependency Guardが、alias import
        （`import X as Y`）を検出対象に含むことを明示していなかった。

2026-07-18: Non-Blocking Finding修正（Claude Codeによる同一Session内修正）。
    AR14-m-1〜AR14-m-9・AR14-S-1のすべてを本文書へ反映した：36章の「38章」
    参照を削除し章体系外である旨へ修正、9.3節・15.2節の外部プロンプト参照を
    「元のArchitecture Design依頼プロンプトN章」と明記、28章のbaseline内訳を
    v6.0.0〜v6.13.0の14ファイル＋2ファイル＝16ファイルへ訂正、26.7節へ
    「Protocol構造互換性Guard（静的、inspect.signatureによるパラメータ名
    比較）」を新設し27章の採用Guard一覧・26.10節のScope境界へ反映、32章の
    Risk記述を「Caller呼び出しレベルの懸念（呼び出し忘れ・二重呼び出し）」
    へ明確化するとともに構造適合確認手段を26.7節Guardへ整合、15.1節へ
    `getattr()`のAttributeError以外の例外伝播・新設Protocolの
    `@runtime_checkable`非付与理由を追記、20.4節・27章のself属性代入Guardへ
    AugAssign／AnnAssign／setattr／object.__setattr__を列挙、24章・27章の
    loop禁止Guardへcomprehension／generator expressionを追加、22章へalias
    import検出に関する説明を追記した。Production Code・Test Code・既存
    設計書・ROADMAP.md・architecture.md・CHANGELOG.md・.env.exampleは
    いずれも変更していない。

2026-07-18: Architecture Review（Claude Codeによる独立Review、再Review）：
    Approved。Blocking Issueなし。Critical 0件・Major 0件・Minor 0件・
    Suggestion 0件（前回Findingはすべて反映により解消）。新規Findingなし。
    章番号体系（0章〜37章）に欠落・重複がないことを再確認した。Public API
    ・Dependency Direction・Validation Contract・Error Contract・呼び出し
    順序・Failure Boundary・ArticleData不変性・Security Contract・
    禁止事項・E2E Test Strategy・Formal Regression Strategy・Historical
    Record非改変のいずれについても、Production Codeとの直接照合により
    矛盾が確認されなかった。Production実装・E2E作成・既存統合文書更新・
    commit・pushはいずれも実施していない。

2026-07-18: Production Implementation＋新規E2E作成（Claude Code）。Approved済み
    Architecture Designに完全準拠し、新規独立package
    `src/article_featured_media_orchestration/`（`__init__.py`19行、
    `article_featured_media_orchestrator.py`74行）を作成した（25.1節）。
    Public API（`ArticleFeaturedMediaOrchestrator` / `GeneratedImageUploadCapability`）・
    固定Error Message 7種・Constructor／apply()のValidation順序・呼び出し順序
    （generate→upload→bind）・ArticleData不変性（`bind_featured_media()`への
    完全委譲）・Dependency Direction・Security Contract・禁止事項（try/except・
    loop・comprehension・global/nonlocal・module state等）のいずれも、正式
    設計書の記載どおりに実装した。新規E2E
    （`tests/test_e2e_v6_14_0_article_featured_media_orchestration_foundation.py`、
    34 Scenario）を作成し、単独実行で217/217 PASS・終了コード0・Warning／
    Traceback 0件を確認した（26.11節）。実装セルフレビュー（29項目）を実施し、
    Architecture Designからの逸脱・Blocking Issueともになしと判定した。
    Formal Regression（既存16ファイルとの合算実行）は本工程では実施していない
    （Code Review Approved後の別工程）。Code Reviewは未実施のため、Code Review
    状態はNot Startedのまま変更していない。Production Code・Test Code以外
    （ROADMAP.md・architecture.md・CHANGELOG.md・既存Release 6.9〜6.13
    package・main.py・image_resolver.py等）はいずれも変更していない。

2026-07-18: Code Review（Claude Codeによる独立Review、初回）：Approved with
    Suggestions。Blocking Issueなし。Critical 0件・Major 0件・Minor 0件・
    Suggestion 1件（CR14-S-1）。

    確認内容：Public API（class名・method名・引数名・順序・型注釈・戻り値・
    default引数の有無）、GeneratedImageUploadCapability（`@runtime_checkable`
    非付与・具象Uploader非import・`GeneratedImageWordPressMediaUploader.upload`
    との構造適合を実Production Code比較で確認）、Constructor（capability検証
    2件→self代入2件の順序をAST行番号で確認、Validation成功前の部分代入なし）、
    apply()（article→prompt型→prompt空白→filename型→filename空白→generate→
    upload→bind→returnの順序を実装から直接確認）、固定Error Message 7種
    （実装・E2E・設計書15.3節の三者完全一致）、正常系呼び出し順序（各
    dependency正確に1回、identity引き渡し）、Failure Boundary（try/except
    不使用による自然な例外伝播、可能な箇所でexception object identity確認
    済み、bind失敗のみ実`bind_featured_media()`由来のため型・message一致で
    確認）、ArticleData不変性（`dataclasses`非import、`bind_featured_media()`
    への完全委譲をDEP-1で確認）、Stateless Contract（インスタンス属性が
    `_image_generator`／`_media_uploader`の2つのみ）、禁止構文（Try／For／
    While／ListComp／SetComp／DictComp／GeneratorExp／Global／Nonlocalを
    ast.walk()で実測、いずれも0件）、self属性代入Guard（Assign／AugAssign／
    AnnAssign／setattr／object.__setattr__の5形式）、Dependency Direction
    （AST Import／ImportFrom解析による許可集合の部分集合確認、`outputs`・
    `wordpress_media`からのimport名がそれぞれ`ArticleData`・
    `MediaUploadResult`のみに限定されていることを確認）、Security Contract
    （credential／env var／HTTP／logging／filesystem I/Oいずれも0件）を、
    いずれもProduction Codeへの直接照合で確認した。

    新規E2E（1452行、34 Scenario）を全文確認し、Assertion品質（重複・恒真・
    vacuous pass）を精査した結果、実質的な重複・恒真Assertionは検出されな
    かった。Protocol構造互換性Guard（PROTO-1）が
    `GeneratedImageUploadCapability`と`GeneratedImageWordPressMediaUploader`
    という別classを比較していること（自己比較ではないこと）、Public API
    Guard・Dependency Guard・Consumer-less Guard・Reverse Dependency Guard・
    AST Guard・Security Guardのいずれも、対象file／directory／class／method
    の存在確認またはファイル一覧非空確認を先行させておりvacuous passしない
    ことを確認した。E2E集計を`ast.parse()`による独立スクリプトで再計算し、
    独立Scenario数34・module-level for文ブロック数15（Validation用7・Guard
    関連8）・Validation展開case総数25・静的check系呼出数111・実行時
    Assertion数217・Fake数6・Stub数6・str subclass数2・sentinel exception
    class数3のいずれも実装報告と完全一致することを確認した（Reporting
    Findingなし）。新規E2Eを独立に再実行し、217/217 PASS・0 FAIL・終了コード
    0・実行時間約0.22秒を確認した（実行前の実装工程時点の結果と完全一致）。

    CR14-S-1（Suggestion、Non-Blocking）：21章「Dependency Direction」の
    「逆依存禁止」リストは`ai_image_generation`・`openai_image_generation`・
    `wordpress_media`・`generated_image_wordpress_media`・
    `article_featured_media`・`outputs`の6packageを列挙しているが、22章
    「Reverse Dependency Guard」（実際にE2E化される確認事項）はこのうち
    `openai_image_generation`・`generated_image_wordpress_media`を除いた
    4packageのみを対象としている（22章866行が、この2packageは本Release
    からimportされないため対象外とした設計判断を明記している）。Production
    実装（DEP-1で禁止import確認済み）・新規E2E（DEP-2）は、22章が定める
    最終Approved scope（4package）とは完全に一致しており、Approved
    Contractとの不一致はない。したがって本FindingはBlockingではなく、
    Production／E2Eの修正も要求しない。将来Releaseで21章の6package全件を
    Reverse Dependency Guardの対象へ揃えるかどうかは、Architecture判断
    （21章と22章の記載自体をどちらに合わせて整理するか）を伴うため、本
    Code Reviewのscope外として記録するのみとし、Production Code・新規E2E・
    正式設計書のいずれも変更しない（Architecture Designの再設計・Release
    Scope拡張を今回禁止されているため）。

    Production Code・新規E2E・正式設計書以外（既存Release 6.9〜6.13
    package・main.py・image_resolver.py・ROADMAP.md・architecture.md・
    CHANGELOG.md等）はいずれも変更していない。Formal Regression・
    Documentation Integration・Release Review・commit・pushはいずれも
    実施していない。

2026-07-18: Formal Regression（Claude Code）：PASS。正式対象17ファイル
    （既存16ファイル＋新規v6.14.0 E2E 1ファイル）を28.1節の実行順序どおり
    個別実行し、既存16ファイル2054/2054 PASS（Release 6.13完了時点baseline
    と完全一致、新規差分なし）＋新規v6.14.0 E2E 217/217 PASS（Code Review
    時点の実測と完全一致）＝総合2271/2271 PASS。FAIL 0・Warning 0
    （Python native warning形式・Tracebackとも17ファイル全ログで0件を
    grep機械確認済み）・終了コード非0 0ファイル・重複実行なし。集計は
    Pythonスクリプトによる機械的再計算で確認した。Blocking Issueなし。
    CR14-S-1（Suggestion、Non-Blocking）はResolvedへ変更せず、そのまま
    維持した。Production Code・新規E2E・既存Test Code・ROADMAP.md・
    architecture.md・CHANGELOG.md等はいずれも変更していない（本文書
    28.1節・Header・本Review Historyエントリのみを追記した）。
    Documentation Integration・Release Review・commit・pushはいずれも
    実施していない。

2026-07-18: Documentation Integration（Claude Code）：Completed。
    `docs/ROADMAP.md`（v6.13.0エントリ直後にv6.14.0実績[x]を追加、
    「Article Featured Media Runtime Wiring」候補の前提Releaseをv6.14.0へ
    更新、Future Candidates 7件を追加）・`docs/architecture.md`（末尾へ
    「Article Featured Media Orchestration層」節を新設）・
    `docs/CHANGELOG.md`（[v6.13.0]の直前へ[v6.14.0] Entryを新規追加、
    Release状態が`In Progress`でRelease Review未実施である旨をEntry冒頭の
    blockquoteで明記）へ反映した（29.1節）。Public API・固定Error Message・
    新規E2E実績（217/217、34シナリオ）・Formal Regression実績
    （2271/2271、17ファイル）・Architecture Review結果（Approved）・
    Code Review結果（Approved with Suggestions）・CR14-S-1（Non-Blocking
    のまま維持、Resolved・Known Issue・Open Questionへの昇格なし）・
    Consumer-less状態・Future Candidatesを、各文書の既存粒度に合わせて
    反映した。Release 6.13以前のCHANGELOG Entry・ROADMAP完了記録・
    architecture.md既存節・過去Review Historyはいずれも変更していない。
    Release状態は`In Progress`のまま維持し、`Completed`への移行・
    Runtime Wiring完了・main.py接続済み等の誤った表現はいずれの文書にも
    記載していない。Production Code・新規E2E・既存Test Codeは本工程で
    変更していない。Blocking Issueなし。Release Review・commit・pushは
    いずれも実施していない。

2026-07-18: Release Review（Claude Codeによる独立Review、初回）：Changes
    Required。Blocking Issueなし。Critical 0件・Major 0件・Minor 2件
    （RR14-m-1・RR14-m-2）・Suggestion 0件（新規）。

    RR14-m-1：本文書冒頭（0章Headerより前）の「作成者」「状態」行が、
        Architecture Reviewフェーズ時点の記述のまま残っており、その後の
        Production Implementation・Code Review・Formal Regression・
        Documentation Integrationが反映されていなかった。
    RR14-m-2：本文書末尾の結び文が「Architecture Review・Production
        Implementation・New E2E・Code Review・Formal Regression・
        Documentation Integration・Release Reviewのいずれも未実施であり、
        Release 6.14はまだ完了していない」のまま残っており、実際の完了
        状況と矛盾していた。

    いずれもProduction Code・新規E2E・Architecture Contract・Public API・
    Validation／Error Contract・Historical Recordには一切影響しない、
    本文書内の状態表記の陳腐化のみであった。

    Release全体の横断確認結果：Release Scope（generate → upload → bind
    のみ、main.py Runtime Wiring／Composition Root／OpenAI・WordPress
    client生成／Environment Variable／prompt生成／filename生成／
    fallback／DEFAULT_MEDIA_ID／WordPress記事投稿／Retry／idempotency／
    cleanup／rollback／Scheduler／Agentのいずれも非混入）・Public API
    （class名・method名・引数名・順序・型注釈が実装・E2E・4文書間で
    完全一致）・Architecture Contract（Class＋Constructor Injection、
    Protocol依存、Dependency Inversion、ArticleData不変性、例外無変換
    伝播、Consumer-less）・Validation／Error Contract（固定message7種・
    Validation順序が実装と完全一致）・Failure Boundary（try/except等
    禁止構文0件を実ファイルで再確認）・Security（credential／HTTP／
    logging／filesystem I/O等いずれも0件）・Consumer-less状態（main.py・
    image_resolver.py・outputs/・pipeline/・retry_*/・scripts/のいずれも
    未接続）・Architecture Review完了（Approved、Blocking Issueなし）・
    Production Implementation完了（Code Review時点から無変更、mtime確認
    済み）・新規E2E完了（217/217 PASS、34シナリオ、Production Code・
    Test Codeとも今回変更なし、再実行はせず前回実測を正とした）・
    Code Review完了（Approved with Suggestions、CR14-S-1がNon-Blocking
    のまま維持されていることを確認）・Formal Regression完了
    （2271/2271 PASS、17ファイル、Version別内訳一致）・Documentation
    Integration完了（ROADMAP.md／architecture.md／CHANGELOG.md／本文書の
    4文書間で内容一致）・Historical Record保護（`git diff --numstat`で
    `CHANGELOG.md`・`architecture.md`の削除行数が0であること、
    `ROADMAP.md`の8行削除が未着手候補の意図した置換のみであることを
    確認）を、いずれもRepository内の実ファイルから独立に確認した。

2026-07-18: Non-Blocking Finding修正（Claude Codeによる同一Session内修正）。
    RR14-m-1（冒頭「作成者」「状態」行を全フェーズ完了を反映する表現へ
    更新）・RR14-m-2（末尾結び文をRelease 6.14完了を反映する表現へ更新）を
    本文書へ反映した。Production Code・新規E2E・既存設計書・ROADMAP.md・
    architecture.md・CHANGELOG.mdはいずれも変更していない。

2026-07-18: Release Review（Claude Codeによる独立Review、再Review）：
    Approved。Blocking Issueなし。Critical 0件・Major 0件・Minor 0件・
    Suggestion 0件（前回Finding RR14-m-1・RR14-m-2はいずれも反映により
    解消。新規Findingなし）。CR14-S-1（Code Review由来の既存Non-Blocking
    Suggestion）はResolved・Known Issue・Open Questionへ昇格させず、
    そのまま維持した。CR14-S-1の存在自体はRelease Reviewの最終判定を
    `Approved with Suggestions`へ変更する理由とはならない（Release
    Review自体に新規Suggestionが存在しないため）。Release完了条件
    （Architecture Design Completed・Architecture Review Approved・
    Production Implementation Completed・新規E2E PASS・Code Review
    Approved系・Formal Regression PASS・Documentation Integration
    Completed・Release Review Approved系・Critical/Major/Minorいずれも
    0件・Blocking Issueなし・想定7ファイルのみ・`git diff --check`成功）を
    すべて充足したことを確認し、Release 6.14を`Completed`と判定した。
    Production Code・新規E2E・既存Test Codeはいずれも変更していない。
    `git add`・`commit`・`push`はいずれも実施していない。
```

---

（本文書はArchitecture Design・Architecture Review Approved・Production Implementation Completed・New E2E Completed（217/217 PASS）・Code Review Approved with Suggestions（CR14-S-1はNon-Blockingのまま維持）・Formal Regression PASS（2271/2271）・Documentation Integration Completed・Release Review Approvedをもって、Release 6.14として完了した。）
