# Generated Image Filename Policy Foundation — Architecture Design（v6.16.0）

作成日：2026-07-20
作成者：Claude Code（Architecture Designドラフト／Architecture Review／Architecture Amendment／Production Implementation／新規E2E作成／Code Review／Non-Blocking Finding反映／Formal Regression／Documentation Integration／Release Review）／ChatGPT（Architecture Review：未実施）／ユーザー（最終承認：未実施）
状態：**Release Completed（Release Review Approved）**
分類：**Architecture Release**（`development_workflow.md` 6章・7章。新規独立package・新規Public API・新規Dependency方向の確立を伴うため。7章のFast Track候補条件1「Public API変更なし」に抵触するため、Fast Trackは候補にならない）

---

## 0. Header

```text
Release：6.16
Version：v6.16.0
正式名称：Generated Image Filename Policy Foundation
Classification：Architecture Release
Status：**Release Completed**（Documentation Integration Completed・Release
    Review Approved）
Architecture Design：Completed（本文書）
Architecture Review状態：Approved（初回Review：Claude Codeによる独立Review。
    検出：Blocking 0・Major 1（AR-Major-1）・Minor 8（AR-Minor-1〜8）・
    Suggestion 2（AR-S-1〜2）、いずれも本文書内の修正で解消）
Architecture Amendment状態：Approved（Japanese／Unicode Fallback Collision
    再評価。検出：Blocking 0・Major 1（AM-Major-1）・Minor 4（AM-Minor-1〜4）・
    Suggestion 2（AM-S-1〜2）、いずれも本文書内の修正で解消。12.5節・
    29章 Review History参照）
Production Implementation：Completed（`src/generated_image_filename_policy/`
    __init__.py・generated_image_filename_policy.pyの2ファイル）
New E2E：Completed／PASS（19章確定Inventory：60 Scenario・104 Case・
    143 Assertion、143/143 PASS。実行時labelの動的捕捉による独立検証で
    設計書§19表との完全一致（欠落0・余剰0）を確認済み）
Code Review状態：Approved with Suggestions（Blocking Issueなし。Minor 1件
    （CR-Minor-1、設計書内の文字数誤記）は本文書内で解消。Suggestion 1件
    （CR-S-1）はNon-Blockingのまま維持。29章 Review History参照）
Formal Regression状態：Completed（正式対象19ファイル、既存18ファイル
    2365/2365 PASS＋新規v6.16 E2E 143/143 PASS＝総合2508/2508 PASS、
    FAIL 0・Warning 0・終了コード非0なし・外部API実接続0・Environment
    残留なし。初回実行はvenvの`openai`未導入により1ファイルが実行不能
    だったため`Failed`と判定し、`requirements.txt`準拠でvenvを修復した
    うえで全19ファイルを再実行しCompletedとした。20章・29章 Review
    History参照）
Documentation Integration状態：Completed（本工程。`docs/ROADMAP.md`／
    `docs/architecture.md`／`docs/CHANGELOG.md`および本設計書のHeader・
    Review History・実績節・Acceptance Criteriaを更新）
Release Review状態：Approved（Claude Codeによる独立Review。Blocking 0・
    Major 0・Minor 0・Suggestion 1（CR-S-1をNon-Blockingのまま維持、
    Known Issueへは昇格させない）。Public Contract・E2E Inventory
    （60／104／143）・Formal Regression記録（19ファイル・2508/2508 PASS）・
    4文書間整合・Historical Record非改変・Runtime Zero Diffのいずれも
    適合と判定。Release成果物7ファイル全体を承認）
```

本文書はArchitecture Design・Architecture Review・Architecture Amendment・Production Implementation・新規E2E作成・Code Review・Formal Regression・Documentation Integration・Release Review工程の成果物である。Architecture Review・Architecture Amendment・Code Review・Release Reviewはいずれも独立した評価として実施し、自己承認（設計書の結論を無条件に前提とした追認）は行っていない（29章 Review History参照）。Release Review Approvedをもって、Release 6.16として完了した。

### 0.1 名称・ファイル名の確認

Release 6.16候補調査（直前工程）が確定した正式名称「Generated Image Filename Policy Foundation」を、本文書でもそのまま採用する。`docs/ROADMAP.md:855-856`の候補記載名と完全一致しており、変更しない。

設計書ファイル名も、候補調査プロンプトが示した`generated_image_filename_policy_foundation.md`をそのまま採用する。既存precedent（`article_featured_media_binding_foundation.md`・`generated_image_wordpress_media_upload_wiring_foundation.md`・`image_generation_configuration_gate_foundation.md`）と同じ「正式名称をsnake_caseにしたもの」という命名規則に一致しており、変更理由はない。

---

## 1. Purpose

`ArticleFeaturedMediaOrchestrator.apply(article, prompt, filename)`（v6.14.0）が受け取る`filename: str`引数を、生成画像のtitle相当文字列と`mime_type`から決定論的に構築する、独立したFilename Policy Foundationを確立する。

本Releaseが確立するのは、次の純粋なContractのみである。

```text
title: str
mime_type: str
    ↓
Generated Image Filename Policy
    ↓
filename: str（basenameのみ、拡張子込み、path非含有）
```

## 2. Background

- `docs/ROADMAP.md:855-856`は、v6.14.0／v6.15.0完了後の次候補として「Generated Image Filename Policy Foundation（filenameの命名規則・拡張子決定方針を確立する専用Foundation）」を記載している。
- `docs/architecture.md`のArticle Featured Media Orchestration Foundation節（v6.14.0）・Image Generation Configuration Gate Foundation節（v6.15.0）はいずれも、Future Extensionとして本Foundationを含む3点（Article Image Prompt Construction／Generated Image Filename Policy／Publish Composition Root）をRuntime Wiring前提として明記している。
- Release 6.16候補調査（本Architecture Designの直前工程）は、Runtime Wiring前提3点のうち本Foundationが「依存関係ゼロで即着手可能・precedent（`src/slug_generator.py`）が明確・設計判断の幅が最小」であることを理由に第一候補として選定した。
- `ArticleFeaturedMediaOrchestrator.apply(article, prompt, filename)`（v6.14.0）は`filename`を呼び出し元から受け取るのみで、生成・正規化・拡張子付与のいずれも行わない（`docs/architecture.md` v6.14.0節「apply() Validation順序とContract」明記）。本Releaseはこの`filename`引数を構築する専用Foundationである。

## 3. Goals／Non-Goals

### 3.1 Goals

```text
title文字列とmime_type文字列から、決定論的にfilename（basename、拡張子込み）を
    構築するPublic関数を1つ確立する
filenameの正規化規則（ASCII化・lowercase化・separator・最大長・fallback）を確立する
mime_typeから拡張子を導出する固定マッピングを確立する
directory traversal・絶対path生成が構造的に不可能なfilename Contractを確立する
```

### 3.2 Non-Goals（本Releaseに含めないもの）

```text
Runtime Wiring（main.py／image_resolver.pyへの接続）
Composition Root
OpenAI API呼び出し
WordPress API呼び出し
Media Upload実行
Featured Media Binding実行
Retry／Idempotency
Unused Media Cleanup
Image Prompt Construction（本Releaseとは独立したFoundation候補）
.env追加（本Releaseは環境変数を一切読まない）
既存Runtimeへの接続
```

これらは25章（Future Candidates）へ後続Release候補として引き継ぐ。番号・正式名称は本文書で確定しない。

## 4. Repository Survey

Architecture Design着手前に、以下を実読して確認した（候補調査の仮定を無条件に採用せず、現時点のRepositoryを再確認した）。

### 4.1 `src/slug_generator.py`（precedent）

```python
def generate_slug(seo_title: str, date_str: str) -> str:
    ascii_text = re.sub(r'[^\x00-\x7F]+', ' ', seo_title)
    cleaned = re.sub(r'[^a-zA-Z0-9\s]', '', ascii_text).lower()
    slug_base = re.sub(r'\s+', '-', cleaned.strip()).strip('-')
    slug_base = re.sub(r'-+', '-', slug_base)
    if len(slug_base) > 30:
        truncated = slug_base[:30]
        cut = truncated.rfind('-')
        slug_base = truncated[:cut] if cut > 0 else truncated
    slug_base = slug_base.strip('-')
    if slug_base:
        return f"{slug_base}-{date_str}"
    return f"article-{date_str}"
```

最も近い直接precedent。非ASCII→space変換→`[^a-zA-Z0-9\s]`除去→lowercase化→separator正規化→単語境界を優先した最大長切り詰め→空の場合はfallback、という手順は、本Foundationのfilename正規化にもほぼそのまま転用できる。相違点は「date_strを外部から受け取り末尾に付与する」点であり、本Foundationでは12章で別途検討する。

### 4.2 `src/ai_image_generation/generated_image.py`（v6.10.0、既存Contract）

```python
@dataclass(frozen=True)
class GeneratedImage:
    image_bytes: bytes = field(repr=False)
    mime_type: str

    def __post_init__(self) -> None:
        ...
        if not _MIME_TYPE_PATTERN.fullmatch(self.mime_type):
            raise ValueError(...)
```

`mime_type`はcanonical正規表現`^image/[A-Za-z0-9][A-Za-z0-9._+-]*$`で検証済みの文字列（小文字固定、前後空白なし、ASCII限定）。`filename` / `filename_extension`は意図的に含まれない（v6.10.0 Out of Scope：「filenameはWordPress固有の語彙であり、後続のMedia Upload Wiring側の責務として分離している」）。本Foundationはこの空白を埋める後続Foundationの1つである。

### 4.3 `src/generated_image_wordpress_media/generated_image_wordpress_media_uploader.py`（v6.12.0）

`upload(self, image: GeneratedImage, filename: str) -> MediaUploadResult`。`filename`は呼び出し元が構築済みの文字列として受け取るのみで、本モジュールは生成・検証（`WordPressMediaUploader._validate_filename`委譲のみ）を行わない。

### 4.4 `src/wordpress_media/wordpress_media_uploader.py`（v6.9.0、最終消費者のContract）

```python
_FILENAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

def _validate_filename(filename) -> None:
    if not isinstance(filename, str):
        raise ValueError("filename must be a str")
    if not _FILENAME_PATTERN.fullmatch(filename):
        raise ValueError("filename contains characters that are not allowed")
```

本Foundationが返すfilenameの**将来の実際の消費者**（`WordPressMediaUploader.upload()`、Runtime Wiring後）は、この正規表現（先頭英数字・以降は英数字／ドット／アンダースコア／ハイフンのみ）を要求する。本Foundationは`wordpress_media`へ依存しない（15章）が、出力charsetをこの正規表現の部分集合に収まるよう自律的に設計する（22章Alternativesで非依存の理由と互換性の関係を明記）。

### 4.5 `src/article_featured_media_orchestration/article_featured_media_orchestrator.py`（v6.14.0）

```python
def apply(self, article: ArticleData, prompt: str, filename: str) -> ArticleData:
    ...
    if not isinstance(filename, str):
        raise ValueError("filename must be a str")
    if not filename.strip():
        raise ValueError("filename must not be blank")
    ...
```

`filename`はConsumer側（Orchestrator）で「str型・非空白」のみを検証する。本Foundationが返す値は、この検証を確実に通過できるContract（常に非空str）を持たなければならない（11章）。

### 4.6 `src/outputs/base.py`（`ArticleData`）

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

`seo_title: str`は既に`generate_slug(seo_title, date_str)`（`main.py`）の入力として使われている既存fieldであり、「記事のtitle相当文字列」として最も自然に転用できる候補である。ただし本Foundationは`ArticleData`型そのものには依存しない（9章の入力Contract比較で判断根拠を示す）。

### 4.7 v6.10〜v6.15正式設計書・`docs/architecture.md`

7 Foundation（v6.9.0〜v6.15.0）はいずれも次の共通パターンを持つ。

```text
新規独立package（src/直下、__init__.pyがPublic APIのみを再export）
Consumer-less Foundation（既存側からのimportゼロ）
Dependency Directionは常に一方向（新規packageのみが既存複数packageをimportする側）
Validation不正はValueError（isinstance不正）／TypeError（capability不正）で明確に使い分け
固定messageのException Contract
State非保持（module-level function or Constructor Injectionのみのimmutable class）
AST Guardによる機械的なDependency Guard・Side Effect Guard・State Guard
E2Eはpytest不使用、check()系helperによる独立スクリプト実行方式
```

本Foundationもこのパターンを踏襲する。

### 4.8 `docs/development_workflow.md`

7章のFast Track候補条件8項目のうち、少なくとも項目1（Public API変更なし）・項目5（Dependency変更なし）に抵触する（新規Public関数・新規package間importを追加するため）。したがって本Releaseは Architecture Release に分類する（6章「判断に迷う場合はArchitecture Releaseを選択する」の原則にも合致）。

### 4.9 既存モジュールとの命名衝突確認

`src/image_resolver.py`（v1.4.0〜）・`src/image_extractor.py`は、いずれもRSS収集画像URLを扱うモジュールであり、AI生成画像とは無関係。新規package名`generated_image_filename_policy`はこれらと衝突せず、`generated_image_wordpress_media`（v6.12.0）と同じ「`generated_image_`」接頭辞により、AI生成画像専用のFoundationであることが名前から一意に読み取れる。

## 5. Problem Statement

`ArticleFeaturedMediaOrchestrator.apply()`（v6.14.0）は`filename: str`を呼び出し元から受け取る契約だが、この文字列を実際にどう構築するかは、Repository上のどこにも定義されていない。将来のCaller（Composition Root等）が独自にfilenameを組み立てようとすると、次の問題が生じる。

```text
ASCII化・lowercase化・separator正規化の規則がCallerごとにばらつく
mime_typeから拡張子を導出する方式が定義されていない
directory traversal文字（/, \, ..）の除去がCaller任せになり、実装漏れのリスクがある
WordPressMediaUploader._validate_filename()（4.4節）の正規表現に適合しないfilenameを
    Callerが誤って構築するリスクがある
```

本Releaseはこれらを一元的に解決する、単一責務のFoundationを提供する。

## 6. Architecture Decision

| # | 内容 |
|---|---|
| AD-1 | 責務モデル：`title: str`・`mime_type: str`を受け取り、正規化・拡張子付与済みの`filename: str`を返す、純粋なデータ変換のみ。Media Upload・画像生成・HTTP通信のいずれも行わない |
| AD-2 | Package配置：新規独立package`src/generated_image_filename_policy/`（Consumer-less Foundationとして導入、7章） |
| AD-3 | Public API形状：**module-level function**を採用する（8.1節） |
| AD-4 | Constructor：不要（AD-3の帰結） |
| AD-5 | 依存Contract：Python標準ライブラリ（`re`）のみに依存する。`outputs.ArticleData`・`ai_image_generation.GeneratedImage`・`wordpress_media`のいずれにも依存しない（15章） |
| AD-6 | 入力Contract：`title: str`と`mime_type: str`の個別引数を採用する（`ArticleData`全体は受け取らない、9章） |
| AD-7 | title正規化：`generate_slug()`（4.1節）と同型のASCII化・除去・lowercase化・separator正規化・単語境界truncationを踏襲する（10章） |
| AD-8 | 拡張子導出：`mime_type`を入力として、固定の明示的allow-listマッピングから導出する。Python標準ライブラリ`mimetypes`モジュールは環境（OSレジストリ）依存で非決定的なため採用しない（11章） |
| AD-9 | 一意性：完全な一意性保証は本Releaseの責務外のまま維持する（Caller supplied identifier・日付・時刻は採用しない）。ただし、ASCII slugが生成できない場合（fallback発動時）に限り、`title`原文の決定的hashをsuffixとして付与し、異なるtitle間の固定文字列への収束を低減する（Architecture Amendment、12.5節） |
| AD-10 | title不正（空・空白のみ・非ASCII由来で使用可能文字が0件）：例外を送出せず、固定fallback basenameへ切り替える（13章） |
| AD-11 | mime_type不正（非str・allow-list外）：`ValueError`（固定message）を送出する。fallbackしない（13章） |
| AD-12 | Windows予約デバイス名（`CON`／`PRN`／`AUX`／`NUL`／`COM1`-`9`／`LPT1`-`9`、大文字小文字無視）に正規化後basenameが完全一致した場合：固定suffixを付与して回避する（10.6節） |
| AD-13 | 戻り値：拡張子込みの単一`str`（basenameのみ、path非含有）。tuple／dataclassは返さない |
| AD-14 | Logging：追加しない |
| AD-15 | Runtime Wiring・Composition Root接続：Out of Scope（3.2節） |

## 7. Package Structure

```text
projects/03_game_content_ai/src/generated_image_filename_policy/
├── __init__.py                                # Public API export
└── generated_image_filename_policy.py         # generate_image_filename()
```

### 7.1 Package名の検討

| 候補 | 却下／採用理由 |
|---|---|
| `filename_policy` | 「Generated Image」という起点が名前から読み取れず、既存`slug_generator.py`（記事slug）等の他の命名生成ロジックと混同されるリスクがある |
| `image_filename` | AI生成画像専用であることが名前から不明瞭。既存RSS画像系モジュール（`image_resolver.py`／`image_extractor.py`）との役割の違いが名前だけでは判別できない |
| **`generated_image_filename_policy`（採用）** | `docs/ROADMAP.md`記載の正式名称と一致し、`generated_image_wordpress_media`（v6.12.0）と同じ「`generated_image_`」接頭辞により、AI生成画像専用のFoundationであることが名前から一意に読み取れる |

### 7.2 Module名の検討

`image_generation_config/image_generation_config.py`（v6.15.0）と同じ、「package名＝module名」の命名を採用する。本モジュールは`ArticleFeaturedMediaOrchestrator`や`GeneratedImageWordPressMediaUploader`のような固有の「actor」を表すclassを持たず（8.1節）、`bind_featured_media()`の`article_featured_media_binder.py`のような「-er」動作主体名も不要と判断した。「Policy」という語自体が「規則の集合」を意味しており、moduleを追加の役割名で修飾する必要がない。

### 7.3 flatモジュールとの比較（`src/slug_generator.py`との対比）

`slug_generator.py`はpackage化されていない、`src/`直下のflatモジュールである（v1.5.0、Foundation-patternが確立される前の設計）。v6.9.0以降の全Foundation（`wordpress_media`〜`image_generation_config`）は一貫してpackage形式（`__init__.py`によるPublic API re-export・独立したDependency Guard対象単位）を採用している。本Releaseは直近6 Foundationとの一貫性を優先し、package形式を採用する。

## 8. Public API Contract

```python
# src/generated_image_filename_policy/generated_image_filename_policy.py
def generate_image_filename(title: str, mime_type: str) -> str:
    ...
```

```python
# src/generated_image_filename_policy/__init__.py
from .generated_image_filename_policy import generate_image_filename

__all__ = [
    "generate_image_filename",
]
```

- Public import path：`from generated_image_filename_policy import generate_image_filename`
- 引数名：`title`（`str`）、`mime_type`（`str`）
- 戻り値型：`str`（basenameのみ、拡張子込み）
- Constructor：なし
- Thread Safety：構造的に保証される（module-level function、共有可変stateなし、引数以外の外部状態を一切参照しない。16章）
- External Side Effect：なし（HTTP・ファイルI/O・環境変数読込・logging・print・時刻取得のいずれも行わない、16章）

### 8.1 module-level function／immutable class／policy objectの比較

| 観点 | module-level function（採用） | immutable class（Constructor Injectionなし） | Policy Object（設定値を保持するclass） |
|---|---|---|---|
| 依存の有無 | なし | なし（Constructorが空になる） | なし（設定値は将来拡張の余地として保持しうるが、本Releaseでは設定値自体が存在しない） |
| 既存precedent | `generate_slug()`・`resolve_media_id()`・`bind_featured_media()`はいずれも依存注入不要な変換をmodule-level functionとして実装 | プロジェクト内に「空Constructorを持つだけのclass」のprecedentがない | `ImageGenerationConfig`はPolicy的だが`enabled: bool`という保持すべき状態（環境変数由来の設定値）を持つ点が本Foundationと異なる（本Foundationは呼び出しごとに完結し、保持すべき状態がない） |
| 呼び出し時の余計な手順 | `generate_image_filename(title, mime_type)`と直接呼び出せる | 呼び出し前に空のConstructor呼び出しが必要 | 同上、かつ「何を設定として保持しているのか」が呼び出し元から見て不明瞭になる |
| 将来の拡張余地 | 引数追加で対応可能（Public API変更としてArchitecture Reviewを要する） | 同上 | 「拡張子allow-listを実行時に差し替え可能にする」等の柔軟性を持てるが、本Releaseはそのような要件を持たない（YAGNI） |

**結論**：`generate_slug()` / `bind_featured_media()`という直接precedentに倣い、依存注入・状態保持のいずれも不要な本機能はmodule-level functionとして実装する。

## 9. Input Contract

### 9.1 比較

| 案 | 内容 | 採否 |
|---|---|---|
| A. 記事タイトル`str`だけを受け取る | `title`のみを引数とし、拡張子は固定または別関数とする | 不採用（拡張子決定という本Foundationの目的の半分を満たせない） |
| B. `ArticleData`全体を受け取る | `ArticleData`を引数とし、内部で`seo_title`等を参照する | 不採用（9.2節） |
| C. タイトルとMIME type等を個別引数で受け取る | `title: str`・`mime_type: str`の2引数 | **採用** |

### 9.2 案Bを不採用とする理由

```text
outputs.ArticleDataへの依存が発生し、Dependency Direction（15章）が
    「標準ライブラリのみ」というConsumer-less Foundationとして最も
    独立性の高い形から後退する
ArticleDataが保持する22 field中、本Foundationが実際に必要とするのは
    seo_title相当の1文字列のみであり、型全体を受け取る必然性がない
    （bind_featured_media()がArticleData全体を受け取るのは、戻り値も
    ArticleDataでなければならないためであり、本Foundationとは事情が異なる）
将来ArticleDataにfieldが追加・変更されても、本Foundationのシグネチャに
    一切影響しない（narrow Public APIの原則、5章要求）
mime_typeはArticleDataのfieldではなく、GeneratedImage（ai_image_generation、
    v6.10.0）由来の値であるため、いずれにせよArticleData単独では入力を
    完結できない
```

案Aも「`GeneratedImage`オブジェクトを丸ごと受け取り、内部で`mime_type`を参照する」という亜種が考えられるが、これも`ai_image_generation`への依存を発生させ、`image_bytes`という本Foundationが一切使用しない値まで受け取ることになるため、同じ理由で不採用とする。

### 9.3 `title`引数のValidation Contract

| 入力パターン | 挙動 |
|---|---|
| 型不正（`str`以外：`None`／`int`／`bytes`等） | `ValueError`（固定message、13章） |
| 通常のASCII文字列 | 10章の正規化規則を適用 |
| 空文字列（`""`） | 例外を送出せず、10.5節のfallback basenameへ切り替える |
| 空白のみ（`"   "`、全角空白含む） | 同上（正規化後に空になるため、fallbackと同じ経路） |
| Unicode／日本語タイトル（ASCII文字を含まない） | 正規化により使用可能文字が0件になるため、fallbackへ切り替える |
| 日本語とASCIIの混在タイトル | ASCII部分のみ抽出して正規化（`generate_slug()`と同じ挙動） |
| 制御文字（NUL・ESC等） | 10.2節の正規化により除去される（例外にしない） |
| タブ・改行・復帰（`\t` `\n` `\r`） | 空白扱いとしてseparatorへ正規化される（`\s`に含まれるため） |
| path separator（`/`・`\`） | 10.2節の正規化により除去される（例外にしない、10.4節でtraversal非発生を保証） |
| Windows予約文字（`< > : " | ? *`） | 10.2節の正規化により除去される（alnum・空白以外は全除去のため） |
| 先頭・末尾のdot／space | dotは正規化により完全除去、spaceはtrim対象（10章） |
| 非常に長い入力（数千文字等） | 10.5節の最大長でtruncateする（例外にしない） |

**方針**：`title`はいかなる`str`値に対しても例外を送出しない（型不正時を除く）。「使いにくい・使用不能な文字が多いtitle」は業務上ありふれた入力（日本語記事タイトルが大半を占める本プロジェクトの性質上、むしろ標準的な入力）であり、`generate_slug()`が確立した「fallbackで吸収する」という既存precedentと一貫させる。

### 9.4 `mime_type`引数のValidation Contract

| 入力パターン | 挙動 |
|---|---|
| 型不正（`str`以外） | `ValueError`（固定message、13章） |
| allow-list内のcanonical値（`"image/png"`等、11章） | 対応する拡張子を導出 |
| allow-list外の値（`"image/tiff"`・`"text/plain"`・`""`・大文字混在・前後空白・parameter付き等） | `ValueError`（固定message、13章）。fallbackしない |

**方針**：`mime_type`は`title`とは異なり、fallbackを一切行わない（AD-11）。拡張子は生成ファイルの実体（バイト列の形式）と対応していなければならず、誤った拡張子は後続のWordPress Media Upload・ブラウザでの画像表示に実害を及ぼしうるため、不正値は早期に`ValueError`として拒否する。

### 9.5 型判定方式：`isinstance()`採用（`str` subclassの扱い、Architecture Review Finding AR-Minor-1反映）

`title`・`mime_type`いずれも`isinstance(value, str)`で型検証する（`type(value) is str`は採用しない）。したがって`str`のsubclassインスタンスは受理される。

**根拠**：v6.10.0（`GeneratedImage`）は`image_bytes`のみ`type(value) is bytes`という厳密な型検証を採用しているが、これは「`bytes`のsubclassがbuffer共有等により`__post_init__`検証後に外部から内容を書き換えられる」という`bytes`固有の可変性リスクに対するCode Review指摘（`docs/architecture.md` v6.10.0節「Code Reviewでは...`isinstance()`実装がbytesのsubclassを許可してしまう不整合を...指摘」）への対応である。一方`mime_type`（`GeneratedImage`側）・`filename`（`WordPressMediaUploader._validate_filename`）・`article`／`media_result`（`bind_featured_media`）はいずれも`isinstance(value, str)`または`isinstance(value, <dataclass>)`を採用しており、`str`は不変（immutable）でありsubclass化してもbuffer共有・事後書き換えの脅威が構造的に存在しないため、`bytes`と同じ厳格化を適用する理由がない。本Foundationもこの既存precedentに合わせ、`title`・`mime_type`双方で`isinstance()`を採用する。

E2Eでは`str`のsubclassインスタンス（例：`class _T(str): pass`）を`title`・`mime_type`双方に与え、例外を送出せず正常な戻り値を返すことを確認するScenario（19章 TYPE-3）を設ける。

## 10. Filename Normalization Contract（title → slug部分）

`generate_slug()`（4.1節）を踏襲しつつ、本Foundation固有の要件（10.6節）を追加する。

### 10.1 手順（Architecture Review Finding AR-Minor-2反映：`generate_slug()`実装コードの実際の処理順序に厳密に一致させた）

`generate_slug()`（4.1節）の実装は次の順序で処理する。

```python
ascii_text = re.sub(r'[^\x00-\x7F]+', ' ', seo_title)
cleaned = re.sub(r'[^a-zA-Z0-9\s]', '', ascii_text).lower()
slug_base = re.sub(r'\s+', '-', cleaned.strip()).strip('-')
slug_base = re.sub(r'-+', '-', slug_base)
```

本Foundationは、この実装順序（非ASCII→space変換 → 記号除去＋lowercase化 → `strip()`してから空白→ハイフン変換＋端のハイフン除去 → 連続ハイフン圧縮）をそのまま踏襲し、末尾に最大長・fallback・Windows予約名チェック・拡張子付与を追加する。

```text
1. isinstance(title, str)を検証。不適合はValueError（13章）
2. 非ASCII文字（\x00-\x7Fの範囲外）の連続をすべて半角space 1個へ変換する
   （ascii_text = re.sub(r'[^\x00-\x7F]+', ' ', title)）
3. [^a-zA-Z0-9\s]（英数字・空白以外）をすべて除去したうえでlowercase化する
   （cleaned = re.sub(r'[^a-zA-Z0-9\s]', '', ascii_text).lower()。制御文字・
    path separator・Windows予約文字・記号・dotはすべてこの手順で除去される）
4. cleanedの前後空白をstrip()してから、連続する空白を単一のハイフンへ変換し、
   結果の前後のハイフンを再度strip('-')する
   （slug_base = re.sub(r'\s+', '-', cleaned.strip()).strip('-')）
5. 連続するハイフンを単一のハイフンへ正規化する（既存precedentの防御的な
   冗長ステップを踏襲。手順2〜4のパイプライン上は理論上到達しないが、
   `generate_slug()`と挙動を完全に一致させるため同一の実装を維持する）
   （slug_base = re.sub(r'-+', '-', slug_base)）
6. 10.5節の最大長でtruncateする（単語境界を優先）
7. truncate後、再度先頭・末尾のハイフンを除去する
8. 結果が空文字列の場合、10.5.2節のhash付きfallback basename
   （`"generated-image-" + sha256(title.encode("utf-8")).hexdigest()[:8]`、
   titleは正規化前の原文）へ切り替える（Architecture Amendment反映。
   単なる固定文字列ではなくhash suffix付きとする）
9. 10.6節のWindows予約デバイス名チェックを行う（手順8の結果に対して。
   hash付きfallback経路では構造的に不一致になる、10.6節末尾を参照）
10. 11章の拡張子を付与して最終文字列を返す
```

### 10.2 使用可能文字

```text
許可：小文字英字（a-z）・数字（0-9）・ハイフン（-）
不許可：大文字（lowercase化で吸収）・空白（ハイフンへ変換）・非ASCII文字
    （spaceへ変換後に除去）・dot・記号類・制御文字・path separator・
    Windows予約文字（いずれも手順3で除去）
```

separatorはハイフン（`-`）に固定する（`generate_slug()`と同一。アンダースコア（`_`）は不採用：既存precedentとの一貫性を優先し、新しいseparator文字を導入しない）。

### 10.3 連続separatorの正規化

手順5・6により、スペース・記号除去後に生じる連続ハイフンは常に単一のハイフンへ圧縮される（例：`"foo   bar//baz"` → `"foo-bar-baz"`）。

### 10.4 Directory Traversal非発生の保証

```text
"/"・"\\"は手順3で除去される（英数字でも空白でもないため）
".."は"."自体が手順3で除去されるため、正規化後の文字列に"."は
    一切出現しない（拡張子のドットは本Foundationが手順11で別途1個だけ付与する）
先頭が"/"になることも、drive letter（"C:"等）が残ることもない
    （":"も手順3で除去される）
```

したがって、10章の手順を経たbasenameにdirectory traversal・絶対path文字列が含まれることは構造的に不可能である。

### 10.5 最大長とfallback basename

| 項目 | 値 | 根拠 |
|---|---|---|
| slug部分の最大長 | 60文字（拡張子除く） | `generate_slug()`の30文字は「slugのみで別途date_strを付与する」前提の予算配分。本Foundationはsuffixを付与しない（12章）ため、単独でより説明的なfilenameを許容できる予算とした。一般的なfilesystem制限（255バイト）・WordPress `sanitize_file_name()`の実務的な制限に対して十分な安全マージンを持つ |
| truncate方式 | 単語境界優先（`generate_slug()`と同一：`rfind('-')`で区切り、見つからなければ機械的に切り詰め） | 既存precedentを踏襲 |
| fallback prefix | `"generated-image"` | `generate_slug()`の`"article"`と同型の、責務ドメインを表す固定文字列。Architecture Amendment（10.5.2節）により、単独では使用せず常にhash suffixと組み合わせる |
| 非空保証 | 常に成立 | 正規化結果が空の場合は必ずfallback basenameへ切り替わる（10.1節手順10）ため、`generate_image_filename()`の戻り値（拡張子込み）が空文字列になることはない |

最大長は拡張子を含まない「slug部分」に対して適用する（拡張子は固定4種のいずれか、最大5文字（`.webp`））。

### 10.5.1 戻り値全体の最大長Contract（Architecture Review Finding AR-Minor-5反映）

`generate_image_filename()`のPublic APIはfilename全体（basename＋拡張子）を単一の`str`として返す。したがって呼び出し元が実際に依拠すべきContractは「slug部分の最大長」ではなく「戻り値全体の最大長」である。本節でこれを明示的に確定する。

```text
戻り値全体の最大長：65文字
    内訳：slug部分（10.5節、fallback・Windows予約名suffix適用後を含む）
    最大60文字 ＋ "." 1文字 ＋ 拡張子最大4文字（webp） ＝ 65文字
```

10.6節のWindows予約デバイス名suffix（`"-image"`、6文字）は、予約デバイス名自体が最大4文字（`COM1`〜`LPT9`）であるため、suffix適用後でも最大10文字にしかならず、60文字上限を超えることはない（10.6節「suffix付与後の最大長」を参照。Architecture Amendment時点で誤って「10.6.1節」と参照していた箇所を訂正した——10.6節はサブ節番号を持たない構成である）。10.5.2節のhash付きfallback（固定24文字。Code Review時点の軽微な文字数誤記修正：旧稿は「25文字」としていたが、`"generated-image-"`は16文字＋8桁hex＝24文字が正しい）も60文字上限に対し十分な余裕がある。したがって65文字という上限は、fallback・Windows予約名suffix・hash付きfallbackのいずれの有無に関わらず、あらゆる正常系の入力に対して不変のContractとして成立する。

### 10.5.2 Hash付きFallback Basename Contract（Architecture Amendment：Japanese／Unicode Fallback Collision対策）

**背景（Finding AM-Major-1）**：10.5節の固定fallback（`"generated-image"`のみ）は、ASCII slugが生成できないtitle（日本語・絵文字・記号のみ等）に対して常に同一のbasenameを返す。本プロジェクトの実際のドメイン（日本語記事title主体、12.4節）では、異なる多数の記事が同一filename（例：`generated-image.jpg`が繰り返し生成される）へ収束し、次の実務上の問題を生む。

```text
将来のWordPress Media Uploadで同名ファイルが大量に発生し、WordPress側の
    自動rename（-1、-2等のsuffix付与）に事実上依存する運用になる
    （12.2節が「Contractとしては採用しない」としたWordPress挙動へ、
     実務上は依存せざるを得ない状態に陥る）
障害調査時、どのfilenameがどの記事のAI生成画像だったかをfilenameだけから
    判別できない
将来のWordPress Unused Media Cleanup Foundationが「未使用Media」を
    判定する際、同名ファイルが多数存在すると判定ロジックが複雑化する
```

**採用Contract**：ASCII slugが生成できる場合（10.1節手順7終了時点でslug_baseが非空）は現行slugをそのまま使用する（変更なし）。ASCII slugが生成できない場合（手順7終了時点でslug_baseが空文字列）に限り、`title`原文（正規化前の引数そのもの）の決定的hashをsuffixとして付与した、次の形式のbasenameを使用する。

```text
generated-image-<8桁小文字hex>
```

具体例（UTF-8エンコードでの実測値、実装工程での参照値）：

```text
title="速報】新作発表"        → "generated-image-de4b4035"
title="速報２】新作発表"      → "generated-image-83a9c887"
title=""（空文字列）           → "generated-image-e3b0c442"
title="   "（半角space）       → "generated-image-0aad7da7"
title="　　"（全角space）      → "generated-image-aa27d704"
title="!!!@@@###"（記号のみ）  → "generated-image-509ee51c"
title="🎮🕹️"（絵文字のみ）     → "generated-image-15b257f2"
```

上記は`hashlib.sha256(title.encode("utf-8")).hexdigest()[:8]`の実測結果であり、実装工程のE2E期待値としてそのまま使用できる（19章）。

#### 10.5.2.1 Hash Contract（確定）

```text
algorithm：hashlib.sha256（Python標準ライブラリ）
encoding：UTF-8（title.encode("utf-8")、他のencodingは使用しない）
hash入力文字列：title引数の原文（10.1節の正規化を一切適用する前の値）
    ※正規化後（空文字列）をhash入力にすると、fallbackする全titleが
      同一hash（sha256("")の固定値）になり目的を達成できないため、
      必ず正規化前の原文を入力とする
digest表現：hexdigest()（16進数文字列）
使用文字：hexdigest()の性質上、小文字a-f・数字0-9のみ（大文字は
    出現しない。hashlib.hexdigest()は仕様上常に小文字を返す）
hash長：先頭8文字（32bit相当）。sha256の全64文字ではなく8文字に
    切り詰める理由は10.5.2.2節で説明する
saltなし：salt・pepper・nonceのいずれも使用しない（同一titleが常に
    同一hashになることが目的であるため、salt付与は目的と矛盾する）
environment非依存：環境変数・ロケール・タイムゾーン・実行時刻の
    いずれも参照しない（Python文字列のUTF-8エンコードはlocale非依存
    であり、hashlib.sha256の計算もOS・環境に依存しない）
同一入力での決定性：同一title文字列に対し、実行環境・実行時刻・
    呼び出し回数に関わらず常に同一のhash文字列を返す
collisionを完全保証しないこと：8文字（32bit）への切り詰めにより、
    異なるtitleが同一hashを生成する確率は理論上ゼロではない
    （誕生日問題により、約77,000件のユニークtitleでcollision確率が
    約50%に達する）。本Foundationはcollisionの完全排除を保証せず、
    「固定文字列への100%収束」から「低確率のcollisionへの低減」への
    改善として位置づける（本プロジェクトの実際の記事数規模を踏まえれば
    実務上十分な低減効果がある）
security／credential保護目的ではないこと：sha256を選定した理由は
    Python標準ライブラリでの可用性・決定性のみであり、暗号学的な
    衝突耐性・原像計算困難性をセキュリティ特性として利用する意図はない
    （14.1節でさらに詳述）
```

#### 10.5.2.2 hash長を8文字とする理由

```text
64文字（sha256全体）：filenameとして冗長に長く、10.5.1節の65文字上限
    （拡張子込み）を大幅に超過するため不採用
16文字（64bit相当）：collision確率は8文字よりさらに低くなるが、本
    Foundationの目的は「セキュリティレベルの衝突耐性」ではなく「実用上の
    可読性を保ったまま、固定文字列への100%収束を解消すること」であり、
    本プロジェクトの実際の記事投稿規模（個人ブログ運営、CLAUDE.md記載の
    「小さく作成→動作確認→改善」という開発規模）に対して8文字
    （32bit、約42億通り）で実務上十分と判断した
4文字（16bit相当）：約65,536通りしかなく、記事数が数百〜数千件規模に
    達した段階でcollision確率が無視できなくなるため、安全マージンを
    優先し不採用
本Releaseでは8文字を採用する。将来、実際の記事投稿規模がこの前提を
    超えると判明した場合は、別Releaseでhash長の拡張を検討する
    （25章 Future Candidates）
```

#### 10.5.2.3 適用条件の統一（Architecture Amendment Finding AM-Minor-1関連、5.1節に対応）

空文字列・空白のみ・日本語のみ・絵文字のみ・記号のみ・制御文字のみ・非常に長いがASCII成分ゼロのtitleは、いずれも10.1節手順7終了時点でslug_baseが空文字列になるという**単一の共通条件**でhash付きfallbackへ切り替わる。空・空白titleと非空Unicode titleとで異なるfallback規則を設けない（次の理由による）。

```text
呼び出し元の視点では「titleからASCIIのslugを作れなかった」という
    結果は同一であり、原因（空文字列か日本語かなど）によって挙動を
    分岐させる実務上の利益がない
単一の条件（slug_base空文字列）にすることで、Contract・実装・E2Eの
    いずれも単純化される
空文字列titleのhash（sha256("")の固定値、常に"e3b0c442"）は、
    「空titleは常に区別不能な入力である」という事実を正しく反映して
    おり、特別扱いする理由がない（同じ空文字列titleを渡せば常に
    同じ結果になることは、他のfallback原因と同様に決定性Contract
    （10.5.2.1節）どおりである）
```

### 10.6 Windows予約デバイス名の回避

正規化後のslug部分（拡張子付与**前**の時点）が、大文字小文字を無視して次のいずれかに完全一致する場合、末尾に`"-image"`を付与してから拡張子付与の手順へ進む。

```text
CON, PRN, AUX, NUL, COM1〜COM9, LPT1〜LPT9
```

**判定対象範囲の確定（Architecture Review Finding AR-Minor-4反映）**：`COM0`・`COM10`・`LPT0`・`LPT10`はいずれも対象外とする。Windowsが実際に予約するデバイス名は`COM1`〜`COM9`・`LPT1`〜`LPT9`（数字は1〜9のみ）であり、`COM0`・`COM10`以降は予約名ではない。誤って対象を広げると、`"com10"`のような実在しうる正当な文字列（例：型番・製品名）まで不要にsuffixが付与されてしまうため、判定集合は上記の個別名22種（`CON` `PRN` `AUX` `NUL`の4種＋`COM1`〜`COM9`の9種＋`LPT1`〜`LPT9`の9種）に厳密に限定する（Production Implementation工程での軽微な件数誤記修正：旧稿は「11種」と表記していたが、これは`COM1`-`COM9`／`LPT1`-`LPT9`を範囲表記の2トークンとして数えた場合の数であり、実際の判定対象（個別デバイス名の集合）とは表記が不一致だったため、個別名ベースの正しい数へ訂正した。Contract（判定対象の集合自体）に変更はない）。

**拡張子付与前のslug部分に対して判定する理由（Architecture Review Finding AR-Minor-3反映）**：Windowsのファイルシステムは、予約デバイス名を**拡張子の有無に関わらず**同一のデバイスへの参照として扱う（例：`CON.txt`・`CON.png`はいずれも`CON`と同じ予約名として扱われ、通常のファイルとして作成できない）。したがって本判定は「拡張子込みの最終filenameが予約名と完全一致するか」ではなく、「拡張子付与**前**のslug部分が予約名と完全一致するか」で行う。これにより、`title="CON"`・`mime_type="image/png"`から生成される`"con.png"`のような、拡張子が付くことで見かけ上は予約名と異なる文字列になっていても、実質的にはCONデバイスの別名であるケースを正しく検出できる。

**suffix付与後の最大長（Architecture Review Finding AR-Minor-6反映）**：予約名は最大4文字（`COM1`〜`LPT9`）であり、`"-image"`（6文字）を付与しても最大10文字にしかならない。10.5.1節の60文字上限に対し十分な余裕があるため、suffix付与後に改めてtruncateする処理は不要である（本Foundationはsuffix付与後の再truncateを行わない）。

**根拠**：本Foundationの戻り値は「filename」という汎用的な語彙を持つContractであり、将来の消費者がWordPress REST API経由に限定される保証はない（Consumer-less Foundationのため消費者は未確定）。上記デバイス名はWindowsファイルシステム上で予約された特別な意味を持ち、偶然の一致（例：`title="Con"`）でも回避しておくことが低コストな防御的設計である。WordPress Media REST APIの実際の挙動（サーバー側は通常Linuxであり直接の実害は薄い）に依存しない、Contract自体の頑健性として採用する。

**hash付きfallback（10.5.2節）との処理順序（Architecture Amendment Finding AM-Minor-3反映）**：本Guardは10.1節手順9（Windows予約デバイス名チェック）として、手順8（fallback判定・hash付きfallback生成を含む）の**後**に実行される。すなわち、判定対象は「ASCII slugが得られた場合はそのslug」「ASCII slugが得られなかった場合はhash付きfallback basename（`"generated-image-<8桁hex>"`）」のいずれかであり、常に最終的なbasename候補1つに対してのみ判定する。

hash付きfallback basenameが予約デバイス名と偶然一致することは構造的に発生しない。理由：予約デバイス名は最大4文字（`COM1`〜`LPT9`）であるのに対し、hash付きfallback basenameは常に`"generated-image-"`（16文字）＋8桁hexの合計24文字であり、予約デバイス名の文字数を最初から超過しているため、`fullmatch`的な完全一致判定が構造的に成立しない（Code Review時点の軽微な文字数誤記修正：旧稿は「17文字」「合計25文字」としていたが、実際に数えると`"generated-image-"`は16文字であり、正しくは16＋8＝24文字である。Contract（構造的に予約名と一致し得ないという結論）自体に変更はない）。したがって、Windows予約デバイス名Guardが実際に意味を持つのは「ASCII slugが得られた場合」の経路のみであり、hash付きfallback経路では常にスキップされる（Guard自体は両経路に対して無条件に実行するが、結果として不一致になる）。

## 11. Filename／Extension Contract

### 11.1 比較

| 案 | 内容 | 採否 |
|---|---|---|
| A. MIME typeを入力として拡張子を導出 | `mime_type: str`を受け取り、固定allow-listから拡張子を導出する | **採用** |
| B. 呼び出し側が拡張子を渡す | `extension: str`を別引数として受け取る | 不採用（11.2節） |
| C. 固定拡張子 | 常に`.png`固定とする | 不採用（11.2節） |
| D. 拡張子をこのFoundationの責務外とする | 拡張子を含まないbasenameのみを返す | 不採用（11.2節） |

### 11.2 不採用理由

```text
案B：拡張子とmime_typeの対応関係という「Policy」そのものを呼び出し元へ
    委譲することになり、本Foundation（Filename Policy Foundation）の
    存在意義（docs/ROADMAP.md:855-856「拡張子決定方針を確立する」）を
    満たせない
案C：AIImageGenerator Protocol（v6.10.0）はprovider非依存であり、
    GeneratedImage.mime_typeはPNG固定を保証しない（現在のOpenAI Images APIは
    主にPNGを返すが、これはOpenAI Image Generation Adapter（v6.11.0）が
    観測した実装詳細であり、Contract上の保証ではない）。固定拡張子は
    provider非依存の原則（5章）と矛盾し、mime_typeとfilenameの拡張子が
    将来的に不整合を起こすリスクを内包する
案D：ROADMAP候補名・Purpose（1章）が「filenameの命名規則・拡張子決定方針」を
    セットで求めており、拡張子を欠いたbasenameはArticleFeaturedMediaOrchestrator
    経由でWordPressMediaUploaderへ渡した場合に無拡張子ファイルとなり、
    実用上不完全である
```

### 11.3 標準ライブラリ`mimetypes`モジュールを採用しない理由

Python標準ライブラリの`mimetypes.guess_extension()`は、OS・Pythonバージョンにより登録内容が異なるレジストリ（Windowsでは追加でレジストリ参照）に依存し、同一入力に対して環境ごとに異なる拡張子を返しうる（例：環境によって`.jpe`／`.jpg`のいずれを返すか不定）。これは5章のdeterministic要件（同一入力に対し常に同一出力）と両立しないため、採用しない。本Foundationは自前の固定allow-listを持つ（11.4節）。

### 11.4 拡張子マッピング（固定allow-list）

| `mime_type`（canonical、完全一致） | 拡張子 |
|---|---|
| `image/png` | `png` |
| `image/jpeg` | `jpg`（`jpeg`ではなく`jpg`を採用：WordPress標準アップロードのデフォルト慣行・既存`.env.example`等に`jpg`表記の先例があるため） |
| `image/webp` | `webp` |
| `image/gif` | `gif` |

上記4種はOpenAI Images API（v6.11.0 Adapter経由）が実際に返しうる形式、かつWordPress Media Libraryが標準サポートする形式の交差集合として選定した。

### 11.5 unsupported MIME type・case sensitivity・canonical form

```text
allow-list外の値（例："image/tiff"、"image/svg+xml"）：ValueError（13章）
大文字小文字：区別する。"image/PNG"はallow-list外として拒否する
    （GeneratedImage.mime_typeは既にv6.10.0 Contractでlowercase固定の
     canonical値であるため、本Foundーションが独自にlowercase化・trimする
     必要はなく、むしろ非canonical値を無条件に許容しない方が、
     上流Contract違反を早期検知できる）
canonical form：v6.10.0の_MIME_TYPE_PATTERN（^image/[A-Za-z0-9][A-Za-z0-9._+-]*$）
    への一致は要求しない。本Foundationはallow-list方式（完全一致の集合
    メンバーシップ判定）を採用するため、正規表現による構文検証は不要
    （allow-listの4値自体が既にcanonical構文を満たしている）
```

## 12. Uniqueness and Determinism

### 12.1 比較

| 案 | 内容 | Testability | 採否 |
|---|---|---|---|
| A. title由来slugのみ | suffixなし。同一(title, mime_type)は常に同一出力 | 最高（純粋関数） | **ASCII slugが得られる場合のみ採用**（fallback発動時はD'を併用、12.5節） |
| B. 日付suffix | `date_str`を追加引数として受け取り末尾へ付与 | 高（外部から日付を注入可能） | 不採用（12.2節） |
| C. 時刻suffix | 内部で`datetime.now()`等を呼び出し付与 | 低（Mock必須、非決定的） | 不採用（12.2節） |
| D. hash suffix（画像バイト列等） | 画像バイト列（`GeneratedImage.image_bytes`）等のhashを付与 | 中（入力拡大が必要） | 不採用（12.2節） |
| E. caller supplied identifier | 呼び出し元が一意性トークンを別引数で渡す | 高 | 不採用（12.2節、将来検討） |
| F. 一意性を責務外とする | 本Foundationはbasenameのみ返し、一意性は完全に呼び出し元・将来Releaseに委ねる | 最高 | 案Aと同じ結論（Aは「実装がsuffixを持たない」、Fは「責務として持たない」という同一結論の異なる表現） |
| D'. hash suffix（title文字列、fallback発動時のみ、Architecture Amendment追加） | 既存入力`title`（追加入力不要）の決定的hashを、ASCII slugが得られない場合のみsuffixとして付与 | 最高（純粋関数のまま、モック不要） | **採用（12.5節）** |

### 12.2 不採用理由と採用理由

```text
案B（日付suffix）：generate_slug()と表面的には近いが、「date_strを
    誰が・いつ決定するか」という責務が本Foundationへ入り込み、
    Runtime Wiring（Out of Scope、3.2章）の前提を先取りすることになる。
    また、WordPress Media Library自体が同名ファイルアップロード時に
    自動リネーム（-1、-2等のsuffix付与）を行う既知の挙動があり、
    グローバル一意性の保証を本Foundationが担う必然性が薄い
    （この挙動はWordPress側の実装詳細であり、本Foundationの
     Public Contractとしては採用しない。あくまで一意性を本Foundationの
     責務としない判断の傍証として記載する）
案C（時刻suffix）：本文書の指示どおり「現在時刻を内部取得する設計は、
    必要性とTestabilityを慎重に検討」した結果、内部でのdatetime.now()
    呼び出しはE2Eでのモック・時刻固定が必須になり、5章のdeterministic
    要件（同一入力に対する出力の等価性を時刻非依存で検証できること）と
    真っ向から矛盾するため不採用とする
案D（hash suffix、画像バイト列）：本Foundationの入力Contract（9章）は
    title・mime_typeの2つのみであり、画像バイト列（GeneratedImage.
    image_bytes）を入力として受け取っていない。hash suffixのために
    入力Contractを広げることは、9.2節で確立した「narrow Public API」の
    原則に反する。※Architecture Amendment（12.5節）：本項の不採用理由は
    「画像バイト列という新規入力を要するhash」に限定される。既存入力
    である`title`文字列のhashは入力Contractを一切拡大しないため、
    本項の不採用理由は適用されない（案D'として別途評価する）
案E（caller supplied identifier）：現時点で実際のCallerが存在しない
    （Consumer-less Foundation）ため、識別子の型・生成方式・一意性保証の
    強度を今決定する根拠がない。将来Runtime Wiring・Media Upload
    Retry／Idempotency Foundationのいずれかで、実際の要件が判明した
    時点でArchitecture Reviewを経て追加すべき論点であり、25章
    （Future Candidates）へ引き継ぐ
```

**採用（案A、ASCII slugが得られる場合）**：`generate_image_filename(title, mime_type)`は純粋関数として、ASCII slugが得られる場合はsuffixを一切持たない。同一入力に対し常に同一のfilenameを返す（決定論的）。ASCII slugが得られない場合（fallback発動時）は案D'（title文字列のhash suffix）を併用する。この修正の詳細な再評価は12.5節（Architecture Amendment）を参照。

### 12.3 将来のidempotencyとの整合

本Foundationの決定性（同一入力→同一出力）は、将来の「Media Upload Retry／Idempotency Foundation」（ROADMAP次候補）にとって好都合な性質である。Retry時に同一のtitle・mime_typeを再度本Foundationへ渡せば、常に同一filenameが得られるため、Idempotency Keyの構成要素として利用可能である（ただし本Foundation自体がidempotency制御を行うわけではない。将来Releaseの検討事項として25章へ引き継ぐ）。

### 12.4 日本語title優勢ドメインにおける実務上の含意（Architecture Review Finding AR-Major-1反映）

**Finding（Major）**：本プロジェクトはCLAUDE.md記載のとおり「海外ゲームニュース収集AI」「WordPressブログ記事作成AI」を対象とし、実際の記事titleの大半は日本語である（`docs/CHANGELOG.md`・`docs/blog_strategy.md`の実例も日本語title主体）。10章の正規化規則はASCII-onlyであり、日本語のみのtitleは使用可能文字が0件になるため、10.5節のfallback basename（`"generated-image"`）へ収束する（AD-10）。したがって、実運用で同一mime_type（例：`image/png`のみを使い続ける場合）の記事が連続すると、本Foundation単体の出力は**常に同一のfilenameになる**。これは12.1節〜12.3節で述べた「一意性を責務外とする」という設計判断の帰結だが、当初の22章（Risks）はこれを一般的なリスクの1項目として軽く言及するに留めており、実際の主要ユースケースにおいてほぼ恒常的に発生する事象であることが十分に強調されていなかった。

**評価**：この帰結自体は12.2節の判断（案A〜F比較）を覆す理由にはならない——一意性suffixを内部実装すると、Testability低下（案C）・narrow Public API違反（案D）・Runtime Wiring前提の先取り（案B・E）のいずれかを招くことに変わりはなく、この設計書のScope（3.2節）が明示的に定める「一意性は責務外」という与件とも整合する。したがって対応は、Contract自体の変更ではなく、**この帰結を本Foundationの正式なContractとして明示的に受け入れ、将来のCallerに対する要求事項として文書化すること**とする。

**確定Contract**：

```text
generate_image_filename()は、同一(title, mime_type)に対して常に同一の
    filenameを返す（12.1節の決定性Contractの直接の帰結）
本プロジェクトの主要ユースケース（日本語title）では、多くの入力が
    fallback basenameへ収束するため、本Foundation単体の出力の実務上の
    一意性は低い（多くの場合、同一のfilenameが返る）
本Foundationはこれを解決しない（Contract上の既知の性質として受け入れる）
複数画像を区別する一意性が必要な場合、将来のCaller（Publish Composition
    Root等）が本関数の戻り値に対して追加の一意化処理（例：連番・
    タイムスタンプ・記事IDのprefix／suffix付与）を行う責務を負う
WordPress Media Libraryの同名ファイル自動リネーム挙動（12.2節で言及）は、
    この一意性の欠如を軽減しうる副次的な事実ではあるが、WordPress側の
    実装詳細でありContract上の保証としては採用しない
```

このFindingは26章（Acceptance Criteria）へも反映する。

## 12.5 Architecture Amendment：Japanese／Unicode Fallback Collision対策（12.4節の帰結を修正）

12.4節（初回Architecture Review、AR-Major-1）は「fallback収束」を既知の性質として受け入れる方針を確定した。その後の再評価（Architecture Amendment、Finding AM-Major-1）により、この帰結は次の理由で**実用的なfilename policyとして不十分**と判断し、12.4節の結論を修正する。

```text
将来のRuntime Wiringで実運用が始まった場合、日本語title主体という
    ドメイン特性上、多数の記事画像が恒常的に同一filenameへ収束する
    （固定文字列の1点への収束は「衝突頻度が低い」という通常の
    collision問題とは性質が異なり、「同一class内では常に100%衝突する」
    という質的に異なる問題である）
retry／idempotency・unused media cleanup・障害調査のいずれにおいても、
    「どのfilenameがどの記事由来か」を区別できないことは実務上の障害になる
WordPress側の自動renameへ実質的に依存する運用になり、12.2節が
    「Contractとしては採用しない」とした前提と、実際の運用実態が
    乖離する
```

### 12.5.1 比較した案（独立評価、設計書の結論を無条件に前提としない）

| 案 | 内容 | 評価 | 採否 |
|---|---|---|---|
| A：現行固定fallback維持 | `generated-image.jpg`のみ | 単純・deterministic・Public API不変だが、衝突頻度が実運用で100%に近い。WordPress renameへの実質依存・retry／idempotency／障害調査の困難化を招く | **不採用** |
| B：決定的hash付きfallback（fallbackのみ） | `generated-image-a84f29c1.jpg` | 同一titleで同一filename・異なるtitleで異なるfilename（低確率でcollisionしうる）・時刻／乱数／environment非依存・Testability最高・Public API不変（`title`は既存入力） | **採用**（12.5.2節） |
| C：すべてのtitleへhash suffix付与 | `fortnite-new-season-a84f29c1.jpg` | ASCII titleの衝突も低減できるが、可読性・SEO価値（CLAUDE.md「SEOを意識する」要求）を全titleで犠牲にする。ASCII title同士の衝突は「異なる記事が異なる語を使う」という性質上、fallback収束（同一class内100%衝突）より本質的に発生確率が低く、対策の優先度が異なる | **不採用**（12.5.3節） |
| D：Unicode filenameを許可 | `フォートナイト新シーズン.jpg` | 4.4節で確認したとおり、将来の実際の消費者（`WordPressMediaUploader._validate_filename`、`_FILENAME_PATTERN`）はASCII限定の正規表現であり、Unicode filenameは構造的に拒否される。HTTPの`Content-Disposition`ヘッダ（`wordpress_media_uploader.py`の`f'attachment; filename="{filename}"'`）も非ASCII文字のRFC 5987/6266相当のencodingを実装しておらず、そのまま送信すると文字化け・拒否のリスクがある | **不採用**（技術的な非互換性、12.5.4節） |
| E：caller supplied identifier | `identifier: str`を第3引数として追加 | Public API拡大を伴う。現時点でCallerが存在しない（Consumer-less Foundation）ため、識別子の型・生成方式が未確定であり、Runtime Wiring・Composition Rootの設計を先取りすることになる（12.2節の既存判断と同じ理由） | **不採用**（12.5.5節） |

### 12.5.2 案B（title文字列のhash付きfallback）を採用する理由

```text
Public APIを一切変更しない：hashの入力はtitle（既存の第1引数）であり、
    第3引数の追加や既存引数の意味変更を要しない。narrow Public API
    （5章）を完全に維持できる
既存入力Contract（9章）を一切変更しない：title・mime_typeの2引数のまま
external I/Oなし：hashlib.sha256の計算はPython標準ライブラリの
    純粋なメモリ内計算であり、ネットワーク・ファイル・環境変数への
    アクセスを一切伴わない（16章 State／Side Effect Contractと矛盾しない）
deterministic：sha256は決定的アルゴリズムであり、salt・時刻・乱数を
    使用しない（10.5.2.1節）ため、12章の決定性要件と矛盾しない
Testability：モック・時刻固定のいずれも不要（12.2節が案C＝時刻suffixを
    却下した理由と対照的）
```

### 12.5.3 案C（全titleへhash suffix付与）を不採用とする理由

```text
ASCII titleが生成する衝突は、fallback収束（同一class内で常に100%衝突）
    とは質的に異なる問題である。異なる記事が偶然同じslugになる確率は、
    異なる語彙・表現を使う限り実用上低い（generate_slug()が既存
    precedentとしてこのリスクを許容していることとも整合する）
全titleへhash suffixを付与すると、"hello-world-a1b2c3d4.png"のように
    可読性の高いASCII titleに対しても機械的な文字列が付加され、
    画像ファイル名としてのSEO価値（記事内容を示唆するfilename）を
    毀損する（22章Risksが既に指摘している既存のtrade-off）
本Foundationの入力（9章）・出力（8章）Contractの変更範囲を、実際に
    問題となっているfallback経路のみに限定する方が、変更の影響範囲が
    最小になる（Architecture Amendmentの原則としても、問題の scope を
    超えて変更範囲を広げるべきではない）
```

### 12.5.4 案D（Unicode filename許可）を不採用とする理由

```text
将来の実際の消費者（4.4節、WordPressMediaUploader._validate_filename、
    _FILENAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")）は
    ASCII限定の正規表現であり、Unicode文字を含むfilenameは
    構造的に拒否される。本Foundationが「消費者が受理できない値」を
    返すことは、Filename Policy Foundationとしての存在意義
    （1章Purpose「filename引数を構築する」）と矛盾する
HTTPのContent-Dispositionヘッダ（同ファイル`upload()`メソッド）は
    単純な`filename="..."`形式であり、RFC 5987／6266が定める
    `filename*=UTF-8''...`形式のencodingを実装していない。非ASCII
    filenameをそのまま送信すると、サーバー側実装によって文字化け・
    拒否・別文字への置換が発生するリスクがある
provider（OpenAI等）・environment（OS・ファイルシステム）間で
    Unicode正規化形式（NFC／NFD等）の扱いが異なる可能性があり、
    5章のdeterministic要件・Repository既存方針（generate_slug()の
    ASCII-only方針）との整合性も損なう
```

### 12.5.5 案E（caller supplied identifier）を不採用とする理由

```text
12.2節（案E）が既に述べた理由（Consumer-less Foundationの段階でCaller
    が存在せず、識別子の型・生成方式を決定する根拠がない）がそのまま
    適用される
案B（title文字列のhash）が、Public API変更なしに同等以上の効果
    （異なるtitle間の収束回避）を達成できるため、Public API拡大という
    より大きなコストを払ってまでこの案を採用する理由がない
将来、記事ID等の安定した識別子を用いたより強力な一意性が必要になった
    場合は、Media Upload Retry／Idempotency Foundation（25章）で
    改めて検討する
```

### 12.5.6 確定Contract（一意性責務との境界の分離、5.4節に対応）

```text
完全な一意性は保証しない：本Foundationは「異なるtitleに対し高い確率で
    異なるfilenameを返す」ことを目指すが、collisionをゼロに保証する
    ものではない（10.5.2.1節）
異なるUnicode title間の固定fallback集中を回避する：これが本Amendmentの
    直接の目的である。日本語title主体の実運用で、同一fallbackへの
    100%収束という質的な問題を解消する
collision riskを低減する（排除ではない）：8文字hash（32bit）による
    実務上十分な低減であり、暗号学的・数学的なゼロcollision保証では
    ない（10.5.2.2節）
WordPress側renameをContractとして依存しない：12.2節の既存判断を維持
    する。本Amendmentにより、この非依存の実務上の必要性そのものが
    低下する（fallback収束が緩和されるため、WordPress renameに
    頼らざるを得ない場面自体が減る）
upload結果やmedia IDを用いたidempotencyは将来Foundationの責務のまま：
    本Amendmentはfilenameの「区別可能性」を高めるのみであり、
    Media Upload Retry／Idempotency Foundation（25章）が担うべき
    「同一画像の重複Upload防止」とは異なる問題である。本Foundationの
    決定性（同一title→同一hash）は、そちらのFoundationにとって
    引き続き好都合な性質である（12.3節）
時刻・乱数・counterは使用しない：10.5.2.1節のとおり、sha256は
    saltなし・時刻非依存・環境非依存である
```

### 12.5.7 影響範囲

本Amendmentによる変更は、10.5節（fallback prefixの位置づけ変更）・10.5.2節（新設）・10.6節（処理順序の明記）・13章（変更なしの確認）・14章（14.1節新設）・15章（`hashlib`許可への変更）・18章（原則適合の再確認）・19章（E2E Inventory更新）・20章（Formal Regression予定件数更新）に及ぶ。Public API（8章）・入力Contract（9章）・拡張子Contract（11章）・Dependency Direction（15章の許可/禁止リストの構造そのもの）・Package Structure（7章）はいずれも変更しない。

## 13. Error Contract

```text
title型不正の例外型：ValueError（固定message："title must be a str"）
mime_type型不正の例外型：ValueError（固定message："mime_type must be a str"）
mime_type allow-list外の例外型：ValueError（固定message：
    "mime_type is not a supported image type"）
固定messageをPublic Contractとする：する（3種すべて完全一致でPublic Contract化する）
title不正値（空・空白のみ・使用可能文字0件）：例外を送出しない
    （10.5節のfallback basenameへ切り替え、AD-10）
```

### 13.1 Validation Order

```text
1. titleの型検証（9.3節）。不適合はValueError
2. mime_typeの型検証（9.4節）。不適合はValueError
3. mime_typeのallow-list検証（11.5節）。不適合はValueError
4. titleの正規化（10章）。fallback判定を含む（例外を送出しない）
5. Windows予約デバイス名チェック（10.6節）
6. 拡張子付与
7. 戻り値の返却
```

複数の入力が同時に不正な場合、最初に検証を満たさなかった項目の例外のみが送出される（fail-fast、逐次検証。既存precedent（`bind_featured_media()`のValidation Order、v6.13.0）と同一の考え方）。

### 13.2 原則（既存precedentの継承）

```text
try／exceptを不要に追加しない
例外wrapperを作らない
raise ... from ... を使用しない
予期しないPython runtime例外を変換しない
例外messageへtitle／mime_typeの実際の値を含めない（14章Security Contract）
```

### 13.3 isinstance不正の例外型（ValueError採用根拠）

`title`・`mime_type`いずれも「呼び出し元がPublic関数へ渡した引数」を検証するPublic Boundary入力検証であり、`bind_featured_media()`の15.2節（v6.13.0設計書）が確立したprecedent（Public Boundaryにおける`isinstance`不正は`TypeError`ではなく`ValueError`とする）に合わせる。本Foundationは`callable(getattr(...))`によるcapability検証（`TypeError`を用いる既存precedent、例：`ArticleFeaturedMediaOrchestrator.__init__`）を一切行わない（依存オブジェクトを受け取らないため）。したがって本Foundationの例外型は全件`ValueError`のみとなる。

### 13.4 Architecture Amendment後のError Contract再確認（変更なし）

12.5節のhash付きfallback導入は、Error Contractに影響しない。理由：

```text
hashlib.sha256(title.encode("utf-8")).hexdigest()[:8]は、titleが
    有効なstr（9.3節のValidation Contractを通過済み）である限り、
    失敗しうる経路を持たない（str.encode("utf-8")はPythonの
    サロゲート単体文字等の一部の異常なstrを除き例外を送出しない。
    正規のtitle入力に対しては構造的に失敗しない純粋計算である）
title自体の型検証（9.3節）は、hash計算より前の手順1（10.1節）で
    既に完了しているため、hash計算の対象は常に検証済みのstrである
fallback発動条件（10.5.2.3節：正規化後slug_baseが空文字列）は、
    従来どおり例外を送出しない経路のまま維持される（fallbackは
    Error Contractの対象ではなく、Validation Contractの対象、
    9.3節・13.1節）
```

したがって13章のError Contract（title型不正・mime_type型不正・mime_type unsupported の3種、全件`ValueError`固定message）は**変更不要**であり、既存precedent（`bind_featured_media()`のisinstance不正＝ValueError precedent、上記引用）も引き続きそのまま適用される。

## 14. Security Contract

```text
directory traversal防止：10.4節（構造的に不可能、AST GuardではなくRuntime
    Guardで境界値を直接検証する）
absolute path生成禁止：10.4節（drive letter・先頭"/"がいずれも
    手順3で除去されるため構造的に不可能）
separator除去：10.2節（path separatorは英数字・空白のいずれでもないため
    手順3で除去される）
secret／本文／promptをfilenameへ含めない：構造的に保証される
    （9.2節の入力Contract決定により、本Foundationはtitle・mime_typeの
     2引数のみを受け取り、article_body／prompt／credential／
     image_bytesのいずれも入力として受け付けない）
logging／printの有無：いずれも実装しない（v6.9.0〜v6.15.0の一貫した方針を継承）
元タイトルを保存・記録する責務を持たないこと：呼び出しごとに独立して
    計算し、module-level・インスタンス変数のいずれにも保存しない
    （16章 State Contract）
例外messageへの入力値埋め込み：しない（13.2節）
```

**Security Contractの適用範囲の明確化（Architecture Review Finding AR-Minor-7反映）**：上記「構造的に不可能」「構造的に保証される」という表現は、いずれも「`generate_image_filename()`が返す`str`自体の性質」に対する保証であり、`title`引数として渡された元の文字列や、呼び出し元が別途行う他の処理の安全性まで保証するものではない。すなわち、本Foundationは「戻り値にdirectory traversal文字列・secret・prompt断片が含まれないこと」を保証するが、「呼び出し元が`title`へどのような文字列を渡すか」「呼び出し元がその戻り値をfilename以外の用途（例：SQLクエリ・shellコマンド）へ転用した場合の安全性」までは関知しない。本Foundationの入力Contract（9章）がtitle・mime_typeの2つのplain strのみを受け付けるという設計自体が、body／prompt／credentialの混入を防ぐ唯一の機序であり、それ以上の一般的な入力サニタイズ責務を負うものではない。

### 14.1 Hash付きFallbackのSecurity表現（Architecture Amendment Finding AM-Minor-4反映）

10.5.2節のhash導入に伴い、次を明確に定める。

```text
hashから元titleを復元できない、とは主張しない：sha256自体は
    暗号学的に一方向性を持つアルゴリズムだが、本Foundationは
    digestを8文字（32bit）に切り詰めており、かつ実際の記事title
    候補は無限ではなく現実的な語彙・話題の集合に限られるため、
    候補titleの辞書に対する総当たり照合（brute force）で元titleを
    特定できる可能性は現実的に排除できない。本Foundationは
    「hashから元titleを復元不可能である」という安全性上の主張を
    一切行わない
hashは匿名化・暗号化・credential保護ではない：sha256を選定した
    唯一の理由はPython標準ライブラリでの可用性・決定性であり
    （10.5.2.1節）、機密性・秘匿性を提供する目的の機構ではない。
    titleに機密情報を含めて渡すことは、本Foundationの想定する
    利用方法ではない（14章本文が既に述べる、呼び出し元の責務の範囲）
元titleをlogging／print／保存しない：hash計算はローカル変数内で
    完結する一時計算であり、10.5.2節の追加によってもこの方針
    （14章本文・16章 State Contract）は変わらない
credentialやpromptを専用引数として受け取らない：本Amendmentは
    Public API（8章）・入力Contract（9章）を一切変更しないため、
    この既存Contractもそのまま維持される
呼び出し側が誤ってtitleへ機密情報を渡すことまでは防止しない：
    AR-Minor-7で確認済みの既存の限定（14章本文）がそのまま適用される。
    むしろhash導入により、機密情報を含むtitleがhash値の一部として
    公開filenameへ（8文字の低次元表現とはいえ）反映される経路が
    新たに生じるため、この限定の重要性は本Amendment後もそのまま
    維持されるべきである
directory traversal／absolute path／separatorを返さない：hexdigest()
    の出力charsetは`0-9a-f`のみであり、10.2節の許可charset
    （小文字英数字・ハイフン）の部分集合に収まる。10.4節の
    Directory Traversal非発生の保証は、hash付きfallback経路でも
    構造的に維持される
```

## 15. Dependency Rules（Dependency Guard）

```text
許可：
generated_image_filename_policy → Python標準ライブラリの re のみ
generated_image_filename_policy → Python標準ライブラリの hashlib のみ
    （Architecture Amendment反映。10.5.2節のtitle文字列hash計算専用。
    15.4節で許可へ変更した理由を説明する）

禁止：
generated_image_filename_policy → outputs（ArticleDataを含む）
generated_image_filename_policy → ai_image_generation（GeneratedImageを含む）
generated_image_filename_policy → openai_image_generation
generated_image_filename_policy → wordpress_media
generated_image_filename_policy → generated_image_wordpress_media
generated_image_filename_policy → article_featured_media
generated_image_filename_policy → article_featured_media_orchestration
generated_image_filename_policy → image_generation_config
generated_image_filename_policy → image_resolver
generated_image_filename_policy → ai（Agent層）
generated_image_filename_policy → pipeline
generated_image_filename_policy → workflow_engine
generated_image_filename_policy → scheduler
generated_image_filename_policy → retry_*（Retry Runtime全体）
generated_image_filename_policy → scripts
generated_image_filename_policy → main
generated_image_filename_policy → mimetypes（標準ライブラリだが11.3節の理由で禁止）
generated_image_filename_policy → unicodedata（標準ライブラリだが15.3節の理由で禁止）
generated_image_filename_policy → datetime（12.2節の理由で禁止）
generated_image_filename_policy → random／uuid（一意性非対応の帰結として禁止。
    hashlibはsaltなし・非乱数のため、この禁止方針と矛盾しない
    （10.5.2.1節「saltなし」参照））
generated_image_filename_policy → requests／urllib（HTTP通信は行わない）
generated_image_filename_policy → os（環境変数読込・ファイルI/Oは行わない）
generated_image_filename_policy → logging

逆依存禁止：
outputs → generated_image_filename_policy
ai_image_generation → generated_image_filename_policy
wordpress_media → generated_image_filename_policy
generated_image_wordpress_media → generated_image_filename_policy
article_featured_media → generated_image_filename_policy
article_featured_media_orchestration → generated_image_filename_policy
image_generation_config → generated_image_filename_policy
openai_image_generation → generated_image_filename_policy
```

```text
Dependency Diagram（Release 6.16後、Architecture Amendment反映後）

generated_image_filename_policy
└── generate_image_filename()
        │
        └──▶ Python標準ライブラリ（re, hashlib）のみ
```

他の全既存packageから独立した、Repository内で最も依存が少ないFoundationとなる（`outputs`・`ai_image_generation`のいずれにも依存しない点で、v6.13.0（`article_featured_media`）・v6.14.0（`article_featured_media_orchestration`）よりも依存グラフ上の位置が更に独立している）。`hashlib`追加後も、project内packageへの依存はゼロのまま維持される。

### 15.1 動的import非使用

`importlib.import_module()`等の動的importは使用しない（v6.15.0 Code Review Suggestion CR10-S-1が指摘したAST Guardの限界（`ast.Import`／`ast.ImportFrom`のみが検出対象）を踏まえ、本Foundationでも動的importを一切用いないことを明記する）。

### 15.2 循環importの有無

`generated_image_filename_policy`は他の全project内packageから独立しているため、循環importは構造的に発生しない。

### 15.3 `unicodedata`を採用しない理由（Architecture Review Finding AR-Minor-8反映）

`unicodedata.normalize('NFKC', title)`を10章の正規化手順の先頭に追加すれば、全角英数字（例：日本語記事titleに頻出する`"Ｎｉｎｔｅｎｄｏ Ｓｗｉｔｃｈ２"`）を半角ASCIIへ変換したうえで10章の既存パイプラインへ通すことができ、12.4節で述べた「日本語title主体の実運用でfallback basenameへ収束しやすい」という帰結を部分的に緩和できる可能性がある。

検討のうえ、本Releaseでは不採用とする。理由：

```text
generate_slug()（4.1節、既存precedent）はunicodedata正規化を行っておらず、
    非ASCII文字を一律spaceへ変換するのみである。本Foundationが独自に
    unicodedata正規化を追加すると、同じプロジェクト内に「似て非なる」
    2つの文字列正規化ロジックが並存することになり、将来の保守者が
    両者の挙動差異を認識しないまま類推適用するリスクを生む
新しい標準ライブラリdependency（unicodedata）の追加は、15章の
    Dependency Guardを拡張する変更であり、AD-5「標準ライブラリのreのみに
    依存する」というArchitecture Decisionの見直しを要する
効果は全角英数字混在titleに限定的であり、純粋な漢字・仮名のみのtitle
    （本ドメインで最も典型的なケース）には効果がない
```

12.4節で確定したとおり、fallback basenameへの収束という帰結自体は「一意性を責務外とする」という既存のArchitecture Decision（AD-9）と矛盾しない既知の性質として受け入れる方針としたため、この効果の限定的な緩和策を本Releaseのスコープに含める必然性はない。将来、実際のfallback発生率が問題になった場合の改善候補として23章（Alternatives Considered）・25章（Future Candidates）へ記録するに留める。

> **Architecture Amendment時点の補足**：上記段落は初回Architecture Review時点（12.4節、AR-Major-1）の記述であり、その後のArchitecture Amendment（12.5節）で「fallback収束という帰結自体を受け入れる」という前提そのものを見直した。したがって本節（15.3節）の`unicodedata`不採用の結論自体は変更しない（15.3節はASCII全titleに対するslug品質向上の話であり、hash付きfallback（10.5.2節、`title`の決定的hashを用いる別の解決手段）とは独立した論点である）が、上記の「fallback収束を受け入れているため緩和策は不要」という理由付けは12.5節の結論により部分的に古くなっている。`unicodedata`を採用しない結論そのものは、15.3節冒頭で述べた別の独立した理由（既存precedentとの一貫性・新規dependency追加の是非・効果が全角英数字混在titleに限定的であること）により、Architecture Amendment後も変更なく成立する。

### 15.4 `hashlib`を許可へ変更する理由（他の禁止stdlib moduleとの区別、Architecture Amendment反映）

本Releaseは`mimetypes`（11.3節）・`unicodedata`（15.3節）・`datetime`／`random`／`uuid`（12.2節）をいずれも不採用としているが、`hashlib`はこれらとは異なる評価軸で許可へ変更した。区別を明確にする。

```text
mimetypes：環境（OSレジストリ）依存で非決定的（11.3節）。hashlibの
    sha256計算はOS・環境に一切依存しない（10.5.2.1節「environment
    非依存」）ため、この不採用理由は適用されない
unicodedata：効果が限定的（全角英数字混在titleのみ）かつ既存
    precedent（generate_slug()）との一貫性を優先した判断（15.3節）。
    hashlibはgenerate_slug()に存在しない新規要件（fallback発動時の
    差別化）を満たすために導入するものであり、「既存precedentとの
    一貫性」という判断基準がそもそも異なる（generate_slug()には
    hash付きfallbackに相当する概念自体が存在しないため、一貫性を
    比較する対象がない）
datetime／random／uuid：非決定的（時刻・乱数に依存する、12.2節）。
    hashlibのsha256計算はsaltなし・決定的であり、この不採用理由は
    適用されない（10.5.2.1節）
```

`hashlib`は「決定的」「environment非依存」という、本Foundationが12章・16章で確立した中核原則（deterministic・stateless・external I/Oなし）と完全に整合する数少ない追加候補であり、他の禁止moduleとは性質が異なるため区別して許可する。

## 16. State／Side Effect／Thread Safety Contract

```text
module-level function（8.1節）であるため、インスタンス状態という概念が
    構造的に存在しない
module-levelのmutable state・global文・nonlocal文のいずれも持たない
title・mime_type・正規化中間値・戻り値のいずれも、関数呼び出しを超えて
    保持しない（呼び出しごとに独立したローカル変数のみで完結する）
HTTP通信・ファイルI/O・環境変数読込・時刻取得・乱数生成・logging・print・
    subprocess・sleepのいずれも行わない
Thread Safety：共有可変stateを一切持たないため、複数threadからの
    同時呼び出しに対して構造的に安全（追加のlockが不要）
```

**Architecture Amendment後の確認**：10.5.2節の`hashlib.sha256(...).hexdigest()`呼び出しは、引数titleのみから戻り値を計算する純粋関数呼び出しであり、`hashlib`モジュール自体もconstructorが返す`hash`オブジェクトも、本Foundationのローカル変数スコープを超えて保持されない。したがって上記のState／Side Effect／Thread Safety Contractは、Architecture Amendment後も無変更のまま成立する。

## 17. Runtime Zero Diff Contract

本Releaseは既存の全package・全モジュールを無改修のまま追加する。

```text
無改修対象：ai_image_generation / openai_image_generation / wordpress_media /
    generated_image_wordpress_media / article_featured_media /
    article_featured_media_orchestration / image_generation_config /
    outputs（ArticleData含む） / image_resolver.py / main.py /
    記事生成Pipeline / Workflow / Scheduler / Retry Runtime / scripts配下全体
```

`generate_image_filename()`を実際に呼び出すCaller・Composition Root・Runtime Wiringは本Releaseの対象外である（Consumer-less Foundation）。本Release単独では、既存Runtimeの挙動は一切変化しない。

## 18. Architecture原則チェック

| 原則 | 適合状況 |
|---|---|
| Consumer-less Foundation | 適合。既存側からの参照ゼロ（新規package追加のみ） |
| Runtime Zero Diff | 適合（17章） |
| provider非依存 | 適合。OpenAI固有の語彙・値を一切含まない（11.4節のallow-listはOpenAI固有ではなく画像形式一般の分類） |
| WordPress非依存 | 適合。`wordpress_media`への依存を持たない（4.4節・11.4節はcompatibility観点の言及のみで、Contract上の依存ではない） |
| external I/Oなし | 適合（16章。`hashlib.sha256()`はメモリ内純粋計算であり、Architecture Amendment後も外部I/Oを伴わない） |
| immutable／stateless | 適合（16章、module-level functionのため構造的に保証） |
| deterministic | 適合（12章・10.5.2.1節。`hashlib.sha256()`はsaltなし・時刻非依存の決定的計算であり、時刻・乱数・環境変数のいずれにも依存しない） |
| narrow Public API | 適合。公開symbolは`generate_image_filename`の1つのみ（Architecture Amendmentによる引数追加なし） |
| dependency directionの一方向性 | 適合（15章、他の全project内packageから独立した末端。`hashlib`追加後もproject内package依存はゼロ） |
| 既存packageへの変更なし | 適合（17章） |

全10原則を維持できる。逸脱事項なし（Architecture Amendment後も再確認済み）。

## 19. E2E Test Strategy（実績反映、Production Implementation・Formal Regression完了）

新規E2Eファイル：`tests/test_e2e_v6_16_0_generated_image_filename_policy_foundation.py`（作成済み）

**実行方式**：既存precedent（v6.9.0〜v6.15.0）と同様、`pytest`は使用せず、Pythonスクリプトとして直接実行し、`check()`系helperで結果を集計する方式を採用した。実行コマンドは`python tests/test_e2e_v6_16_0_generated_image_filename_policy_foundation.py`（`projects/03_game_content_ai`をカレントディレクトリとして実行）。

Architecture Review時点で、19.1節のInventoryを「目安」から**正式確定値**へ改めた（Architecture Review Finding AR-S-1）。その後のArchitecture Amendment（12.5節、Japanese／Unicode Fallback Collision対策）により、fallback関連の期待値・Scenarioを更新し、Inventory件数を55／98／137から**60 Scenario／104 Case／143 Assertion**へ改訂した（Finding AM-S-1）。Production Implementation工程で本節どおりに実装し、**60 Scenario・104 Case・143 Assertion・143/143 PASS（終了コード0、Warning 0、Traceback 0）** を実測した。Case数104は、設計書§19.1のCase ID列を機械的に抽出した集合と、新規E2E実行時に各`check()`呼び出しへ渡された実際のlabel文字列（f-string・ループ変数展開後の値）を動的に捕捉した集合とを突合し、**欠落0・余剰0の完全一致**であることを独立に確認した（Code Review・Formal Regression両工程で再確認済み）。実装中の構成変更はなく、Baselineからの差分はない。

### 19.1 Scenario／Case／Assertion Inventory（確定）

各行はCase単位。同一Scenario IDの行を合算するとScenario単位のAssertion数になる。

| Scenario ID | Case ID | カテゴリ | 入力（要約） | 期待結果／期待例外 | Assertion数 |
|---|---|---|---|---|---|
| PUB-1 | PUB-1a | Public API import | `from generated_image_filename_policy import generate_image_filename` | import成功、かつ`callable()`がTrue | 2 |
| SIG-1 | SIG-1a | signature | `inspect.signature(generate_image_filename)` | 引数2個・引数名`("title","mime_type")`・`*args`/`**kwargs`なし | 3 |
| NORM-1 | NORM-1a | normal ASCII title | `"Hello World"`, `image/png` | `"hello-world.png"` | 1 |
| NORM-1 | NORM-1b | normal ASCII title | `"PS5 Pro Review"`, `image/png` | `"ps5-pro-review.png"` | 1 |
| NORM-2 | NORM-2a | mixed case | `"HELLO World"`, `image/png` | `"hello-world.png"` | 1 |
| NORM-2 | NORM-2b | mixed case | `"PlayStation5"`, `image/png` | `"playstation5.png"` | 1 |
| NORM-3 | NORM-3a | punctuation／spaces | `"Hello, World!"`, `image/png` | `"hello-world.png"` | 1 |
| NORM-3 | NORM-3b | punctuation／spaces | `"Foo/Bar?"`, `image/png` | `"foobar.png"`（区切り文字が隣接文字なしで除去される） | 1 |
| NORM-3 | NORM-3c | punctuation／spaces | `"A (Big) Update"`, `image/png` | `"a-big-update.png"` | 1 |
| NORM-4 | NORM-4a | repeated separators | `"Hello   World"`（連続space）, `image/png` | `"hello-world.png"` | 1 |
| NORM-4 | NORM-4b | repeated separators | `"Foo!!!Bar"`（space挟まない記号連続）, `image/png` | `"foobar.png"` | 1 |
| UNI-1 | UNI-1a | Japanese／Unicode title | `"速報】新作発表"`, `image/png` | `"generated-image-de4b4035.png"`（hash付きfallback、Architecture Amendment反映。UTF-8実測値） | 1 |
| UNI-2 | UNI-2a | Japanese／Unicode title | `"速報 Nintendo Direct"`, `image/png` | `"nintendo-direct.png"` | 1 |
| UNI-2 | UNI-2b | Japanese／Unicode title | `"PS5【新型】発表"`, `image/png` | `"ps5.png"` | 1 |
| EMPTY-1 | EMPTY-1a | empty／whitespace title | `""`, `image/png` | `"generated-image-e3b0c442.png"`（hash付きfallback。sha256("")の固定値、UTF-8実測値） | 1 |
| EMPTY-2 | EMPTY-2a | empty／whitespace title | `"   "`（半角space） , `image/png` | `"generated-image-0aad7da7.png"`（hash付きfallback、UTF-8実測値） | 1 |
| EMPTY-2 | EMPTY-2b | empty／whitespace title | `"　　"`（全角space、非ASCII） , `image/png` | `"generated-image-aa27d704.png"`（hash付きfallback、UTF-8実測値） | 1 |
| CTRL-1 | CTRL-1a | control characters | `"foo\x00bar"`（NUL）, `image/png` | `"foobar.png"` | 1 |
| CTRL-1 | CTRL-1b | control characters | `"foo\x1bbar"`（ESC）, `image/png` | `"foobar.png"` | 1 |
| CTRL-2 | CTRL-2a | control characters | `"foo\tbar"`, `image/png` | `"foo-bar.png"` | 1 |
| CTRL-2 | CTRL-2b | control characters | `"foo\nbar"`, `image/png` | `"foo-bar.png"` | 1 |
| WIN-1 | WIN-1a | Windows予約文字 | `"foo<>:bar"`（space非隣接）, `image/png` | `"foobar.png"` | 1 |
| WIN-1 | WIN-1b | Windows予約文字 | `"foo | bar ? baz * qux"`, `image/png` | `"foo-bar-baz-qux.png"` | 1 |
| WIN-2 | WIN-2a | Windows予約デバイス名 | `"CON"`, `image/png` | `"con-image.png"` | 1 |
| WIN-2 | WIN-2b | Windows予約デバイス名 | `"con"`, `image/png` | `"con-image.png"` | 1 |
| WIN-2 | WIN-2c | Windows予約デバイス名 | `"Aux"`, `image/png` | `"aux-image.png"` | 1 |
| WIN-2 | WIN-2d | Windows予約デバイス名 | `"com1"`, `image/png` | `"com1-image.png"` | 1 |
| WIN-3 | WIN-3a | 予約名境界（対象外の確認） | `"COM0"`, `image/png` | `"com0.png"`（suffix付与されない） | 1 |
| WIN-3 | WIN-3b | 予約名境界（対象外の確認） | `"COM10"`, `image/png` | `"com10.png"`（suffix付与されない） | 1 |
| WIN-3 | WIN-3c | 予約名境界（対象外の確認） | `"conquest"`, `image/png` | `"conquest.png"`（予約名の部分一致では発火しない） | 1 |
| SLASH-1 | SLASH-1a | slash／backslash | `"foo/bar"`（space非隣接）, `image/png` | `"foobar.png"` | 1 |
| SLASH-1 | SLASH-1b | slash／backslash | `"foo / bar"`, `image/png` | `"foo-bar.png"` | 1 |
| SLASH-2 | SLASH-2a | slash／backslash（traversal様） | `"..\\..\\etc\\passwd"`, `image/png` | `"etcpasswd.png"`（`.`／`\`とも出力に残らない） | 1 |
| SLASH-2 | SLASH-2b | slash／backslash（traversal様） | `"../../secret"`, `image/png` | `"secret.png"` | 1 |
| DOT-1 | DOT-1a | dot／space edge cases | `".hidden title."`, `image/png` | `"hidden-title.png"` | 1 |
| DOT-1 | DOT-1b | dot／space edge cases | `"...triple..."`, `image/png` | `"triple.png"` | 1 |
| DOT-2 | DOT-2a | dot／space edge cases | `"  padded title  "`, `image/png` | `"padded-title.png"` | 1 |
| DOT-2 | DOT-2b | dot／space edge cases | `"　padded"`（全角先頭space）, `image/png` | `"padded.png"` | 1 |
| LEN-1 | LEN-1a | maximum length | ハイフン区切り語を連結した80文字超のASCII title, `image/png` | 単語境界でtruncateされた正確な値、かつslug部分`len()<=60` | 2 |
| LEN-2 | LEN-2a | maximum length境界 | ハイフンを含まない単一alnum語ちょうど60文字, `image/png` | 60文字のまま切り詰められず`+".png"` | 1 |
| LEN-2 | LEN-2b | maximum length境界 | ハイフンを含まない単一alnum語61文字（`rfind('-')`が見つからない場合）, `image/png` | 先頭60文字へhard-cut、かつ戻り値全体`len()<=65` | 2 |
| FALLBACK-1 | FALLBACK-1a | fallback basename | `"!!!@@@###"`（記号のみ）, `image/png` | `"generated-image-509ee51c.png"`（hash付きfallback、UTF-8実測値） | 1 |
| FALLBACK-1 | FALLBACK-1b | fallback basename | `"🎮🕹️"`（絵文字のみ、非ASCII）, `image/png` | `"generated-image-15b257f2.png"`（hash付きfallback、UTF-8実測値） | 1 |
| HASH-1 | HASH-1a | hash差別化（Architecture Amendment新規） | `"速報】新作発表"`と`"速報２】新作発表"`（異なる日本語title）をそれぞれ呼び出し | 戻り値が異なる（`"generated-image-de4b4035.png"` ≠ `"generated-image-83a9c887.png"`） | 1 |
| HASH-2 | HASH-2a | hash決定性（Architecture Amendment新規） | `("速報】新作発表", "image/png")`を2回連続呼び出し | 2回とも同一文字列（`"generated-image-de4b4035.png"`） | 1 |
| HASH-3 | HASH-3a | hash形式（Architecture Amendment新規） | UNI-1／EMPTY-1／EMPTY-2／FALLBACK-1の各戻り値からsuffix部分を抽出 | いずれも正規表現`^[0-9a-f]{8}$`に一致する（小文字hex8桁） | 1 |
| LONGUNI-1 | LONGUNI-1a | long Unicode title（Architecture Amendment新規） | 156文字の日本語title（ASCII成分ゼロ）, `image/png` | `"generated-image-7aa76c4f.png"`（UTF-8実測値）、かつ入力長に関わらずhash部分が常に8文字であること | 2 |
| HASH-ENV-1 | HASH-ENV-1a | environment／locale非依存（AST、Architecture Amendment新規） | ソースAST走査 | `locale`のimportが存在しない（`os.environ`非参照はENV-1で確認済み。UTF-8固定エンコードがPythonのlocale設定に依存しないことの裏付け） | 1 |
| MIME-1 | MIME-1a | MIME typeマッピング | 任意の有効title, `image/png` | 拡張子`.png` | 1 |
| MIME-2 | MIME-2a | MIME typeマッピング | 同上, `image/jpeg` | 拡張子`.jpg` | 1 |
| MIME-3 | MIME-3a | MIME typeマッピング | 同上, `image/webp` | 拡張子`.webp` | 1 |
| MIME-4 | MIME-4a | MIME typeマッピング | 同上, `image/gif` | 拡張子`.gif` | 1 |
| MIME-5 | MIME-5a | 非canonical（"jpg"誤記） | 同上, `image/jpg` | `ValueError`（固定message完全一致） | 2 |
| MIME-6 | MIME-6a | unsupported（allow-list外） | 同上, `image/tiff` | `ValueError`（固定message完全一致） | 2 |
| MIME-6 | MIME-6b | unsupported（allow-list外） | 同上, `image/svg+xml` | `ValueError` | 2 |
| MIME-7 | MIME-7a | MIME case | 同上, `IMAGE/PNG` | `ValueError` | 2 |
| MIME-7 | MIME-7b | MIME case | 同上, `Image/Png` | `ValueError` | 2 |
| MIME-8 | MIME-8a | MIME whitespace | 同上, `" image/png "` | `ValueError` | 2 |
| MIME-8 | MIME-8b | MIME whitespace | 同上, `"image/png\n"` | `ValueError` | 2 |
| MIME-9 | MIME-9a | MIME parameter付き | 同上, `"image/png; charset=binary"` | `ValueError` | 2 |
| MIME-9 | MIME-9b | MIME parameter付き | 同上, `"image/jpeg;q=0.9"` | `ValueError` | 2 |
| MIME-10 | MIME-10a | MIME空文字／空白 | 同上, `""` | `ValueError` | 2 |
| MIME-10 | MIME-10b | MIME空文字／空白 | 同上, `"   "` | `ValueError` | 2 |
| TYPE-1 | TYPE-1a | invalid title type | `None`, `image/png` | `ValueError`（固定message`"title must be a str"`） | 2 |
| TYPE-1 | TYPE-1b | invalid title type | `123`, `image/png` | `ValueError` | 2 |
| TYPE-1 | TYPE-1c | invalid title type | `b"bytes"`, `image/png` | `ValueError` | 2 |
| TYPE-1 | TYPE-1d | invalid title type | `["list"]`, `image/png` | `ValueError` | 2 |
| TYPE-2 | TYPE-2a | invalid mime_type type | `"Foo"`, `None` | `ValueError`（固定message`"mime_type must be a str"`） | 2 |
| TYPE-2 | TYPE-2b | invalid mime_type type | `"Foo"`, `123` | `ValueError` | 2 |
| TYPE-2 | TYPE-2c | invalid mime_type type | `"Foo"`, `b"image/png"` | `ValueError` | 2 |
| TYPE-3 | TYPE-3a | str subclass受理（9.5節） | `title`をstr subclassインスタンスで渡す, `image/png` | 例外を送出せず正常な戻り値 | 1 |
| TYPE-3 | TYPE-3b | str subclass受理（9.5節） | `"Foo"`, `mime_type`をstr subclassインスタンス（値`"image/png"`）で渡す | 例外を送出せず正常な戻り値 | 1 |
| ORDER-1 | ORDER-1a | Validation Order | `title=None`, `mime_type=None` | title由来のValueErrorのみ（messageがtitle用固定文言と一致） | 1 |
| ORDER-2 | ORDER-2a | Validation Order | `title="Foo"`, `mime_type=None` | mime_type型不正由来のValueError | 1 |
| ORDER-3 | ORDER-3a | Validation Order | `title=""`（fallback対象）, `mime_type="image/tiff"`（unsupported） | mime_typeのValueError（title側のfallbackが例外送出をもみ消さないこと） | 1 |
| DETERM-1 | DETERM-1a | determinism | `("Foo Bar", "image/png")`を5回連続呼び出し | 5回とも同一文字列 | 1 |
| DETERM-2 | DETERM-2a | determinism（AST） | ソースAST走査 | `datetime`／`random`／`uuid`のimportがいずれも存在しない | 3 |
| BASENAME-1 | BASENAME-1a | no path traversal | NORM／SLASH／UNI／EMPTY各Caseの戻り値を集約 | いずれも`"/"`・`"\\"`を含まない | 1 |
| BASENAME-2 | BASENAME-2a | no absolute path | 同上の集約 | 先頭が`"/"`でない、かつ`":"`を含まない | 2 |
| EXT-1 | EXT-1a | extension Contract | MIME-1〜4の戻り値を集約 | 拡張子部分がallow-list4値のいずれかに完全一致し、`"."`が1個のみ | 1 |
| NONEMPTY-1 | NONEMPTY-1a | 非空保証 | fallback系Caseを含む全Caseの戻り値を集約 | いずれも空文字列でない | 1 |
| NOAPI-1 | NOAPI-1a | no external API call（AST） | ソースAST走査 | `requests`／`urllib`／`openai`のimportがいずれも存在しない | 3 |
| NOLOG-1 | NOLOG-1a | no logging（AST） | ソースAST走査 | `logging`のimportが存在しない | 1 |
| NOLOG-2 | NOLOG-2a | no print（AST） | ソースAST走査 | `print()`呼び出しが存在しない | 1 |
| ENV-1 | ENV-1a | environment non-dependency（AST） | ソースAST走査 | `os`のimportが存在しない | 1 |
| NOFS-1 | NOFS-1a | no file I/O／非決定的依存（AST） | ソースAST走査 | `open()`呼び出し・`mimetypes`importがいずれも存在しない（Architecture Amendment反映：`hashlib`は10.5.2節により許可対象へ変更、DEP-1cで肯定的に検証） | 2 |
| STATE-AST-1 | STATE-AST-1a | module-level state非保持（AST） | ソースAST走査 | module-levelのAssign文（関数定義・import除く）が存在しない | 1 |
| STATE-AST-2 | STATE-AST-2a | global／nonlocal非使用（AST） | 関数本体AST走査 | `ast.Global`・`ast.Nonlocal`がいずれも存在しない | 2 |
| DEP-1 | DEP-1a | Dependency Guard | `generated_image_filename_policy.py`のimport文AST走査 | `re`／`hashlib`以外のimportが存在しない（Architecture Amendment反映） | 1 |
| DEP-1 | DEP-1b | Dependency Guard | `__init__.py`のimport文AST走査 | 自module内相対import以外が存在しない | 1 |
| DEP-1 | DEP-1c | Dependency Guard（Architecture Amendment新規） | `generated_image_filename_policy.py`のimport文AST走査 | `hashlib`のimportが存在する（10.5.2節の実装に必須であることの肯定的確認） | 1 |
| DEP-2 | DEP-2a | Reverse Dependency Guard | `src/outputs/`配下`.py`一覧 | ファイル1件以上（vacuous pass防止）＋`generated_image_filename_policy`非import | 2 |
| DEP-2 | DEP-2b | Reverse Dependency Guard | `src/ai_image_generation/`配下 | 同上 | 2 |
| DEP-2 | DEP-2c | Reverse Dependency Guard | `src/wordpress_media/`配下 | 同上 | 2 |
| DEP-2 | DEP-2d | Reverse Dependency Guard | `src/generated_image_wordpress_media/`配下 | 同上 | 2 |
| DEP-2 | DEP-2e | Reverse Dependency Guard | `src/article_featured_media/`配下 | 同上 | 2 |
| DEP-2 | DEP-2f | Reverse Dependency Guard | `src/article_featured_media_orchestration/`配下 | 同上 | 2 |
| DEP-2 | DEP-2g | Reverse Dependency Guard | `src/image_generation_config/`配下 | 同上 | 2 |
| DEP-2 | DEP-2h | Reverse Dependency Guard | `src/openai_image_generation/`配下 | 同上 | 2 |
| RUNTIME-1 | RUNTIME-1a | Runtime Zero Diff | `main.py`のimport文AST走査 | `generated_image_filename_policy`をimportしない | 1 |
| RUNTIME-1 | RUNTIME-1b | Runtime Zero Diff | `src/image_resolver.py`のimport文AST走査 | 同上 | 1 |
| SEC-1 | SEC-1a | Security（例外message） | TYPE-1相当、識別しやすい値のtitle（例：`"SECRET_TITLE_VALUE"`） | 例外messageに当該値が含まれない | 1 |
| SEC-1 | SEC-1b | Security（例外message） | TYPE-2相当、識別しやすい値のmime_type | 例外messageに当該値が含まれない | 1 |
| SEC-1 | SEC-1c | Security（例外message） | MIME-6相当、識別しやすい非対応mime_type文字列 | 例外messageに当該値が含まれない | 1 |

### 19.2 Scenario／Case／Assertion合計（機械的に照合可能な集計、Architecture Amendment反映後）

```text
Scenario合計：60
Case合計：104
Assertion合計：143
```

カテゴリ別内訳（Scenario数・Case数・Assertion数）：

| カテゴリ | Scenario数 | Case数 | Assertion数 |
|---|---|---|---|
| Public API import／signature | 2 | 2 | 5 |
| normal ASCII／mixed case／punctuation／repeated separators | 4 | 9 | 9 |
| Unicode／Japanese title | 2 | 3 | 3 |
| empty／whitespace title | 2 | 3 | 3 |
| control characters | 2 | 4 | 4 |
| Windows予約文字／予約デバイス名／境界 | 3 | 9 | 9 |
| slash／backslash | 2 | 4 | 4 |
| dot／space edge cases | 2 | 4 | 4 |
| maximum length境界 | 2 | 3 | 5 |
| fallback basename | 1 | 2 | 2 |
| **hash付きfallback Contract（差別化／決定性／形式／長文／locale非依存、Architecture Amendment新規）** | **5** | **5** | **6** |
| MIME typeマッピング（対応4種） | 4 | 4 | 4 |
| MIME type不正系（jpg誤記／unsupported／case／whitespace／parameter／空） | 6 | 11 | 22 |
| invalid type（title／mime_type／str subclass） | 3 | 9 | 16 |
| Validation Order | 3 | 3 | 3 |
| determinism | 2 | 2 | 4 |
| no path traversal／絶対path | 2 | 2 | 3 |
| extension Contract／非空保証 | 2 | 2 | 2 |
| no external API／no logging／no print／no env／no file I/O | 5 | 5 | 8 |
| State非保持（AST） | 2 | 2 | 3 |
| Dependency Guard（許可import／逆依存） | 2 | 11 | 19 |
| Runtime Zero Diff | 1 | 2 | 2 |
| Security（例外message） | 1 | 3 | 3 |
| **合計** | **60** | **104** | **143** |

### 19.3 採用しないScenario

```text
mime_typeのcase-insensitive許容（"image/PNG"を受理する等）：11.5節で
    大文字小文字を区別する方針を確定したため、「許容されること」を
    検証するScenarioは作成しない（逆に「拒否されること」をMIME-7で検証する）
拡張子とtitle正規化の組み合わせ全パターン（4拡張子 × 全titleパターン）の
    総当たり：拡張子付与はtitle正規化と独立した処理段階であるため、
    それぞれを独立したScenario群（10.x／11.x／19.1のMIME-x）として検証すれば
    十分であり、組み合わせ総当たりによるAssertion水増しは行わない
COM0／COM10と類似する非予約の3〜4文字語（例："abc"）を網羅的に追加すること：
    WIN-3節で境界（0／10・実在語conquest）を代表させれば十分であり、
    予約名リスト（11種）の各要素に対する非予約バリエーションを総当たりで
    追加する必要はない
collisionを完全に保証しないことの網羅的検証（Architecture Amendment新規）：
    「collisionが発生しないこと」は、実質的に無限の入力組み合わせに
    対する非存在証明であり、単発のE2E Scenarioで検証できる性質の
    ものではない。10.5.2.1節・10.5.2.2節が明記する「collisionを
    完全保証しない」という設計文書レベルのContractとして扱い、
    E2E Scenarioとしては追加しない（HASH-1が「異なる2つの代表的な
    titleについて実際に異なる結果になること」を確認すれば、
    「意図した差別化機構が機能していること」の検証としては十分）
WordPress側renameへの非依存の直接検証（Architecture Amendment新規）：
    本Foundationが`wordpress_media`パッケージへ一切依存しないことは
    DEP-1（許可importが`re`／`hashlib`のみ）・NOAPI-1（`requests`／
    `urllib`／`openai`のimport非存在）で既に構造的に検証済みであり、
    「WordPress側のrename挙動に依存していないこと」を別途検証する
    Scenarioは、既存Guardの反復にしかならないため追加しない
```

### 19.4 AST／Source Guard方針

v6.9.0〜v6.15.0の既存precedent（`ast.Import` / `ast.ImportFrom` / `ast.Call`によるDependency Guard・Side Effect Guard）に倣い、AST解析で機械的に検証する。

```text
採用するGuard：
    module-levelのAssign文が存在しないこと（STATE-AST-1）
    関数本体にast.Global／ast.Nonlocalが存在しないこと（STATE-AST-2）
    禁止import（15章列挙の全項目：requests／urllib／openai／os／logging／
        datetime／random／uuid／mimetypes／unicodedata／locale）が
        存在しないこと（DEP-1、NOAPI-1、NOLOG-1、ENV-1、DETERM-2、
        NOFS-1、HASH-ENV-1を統合的にAST走査で検証する。Architecture
        Amendment反映：`hashlib`は禁止対象から除外し、DEP-1cで
        存在することを肯定的に確認する）
    open() / print() / sleep()呼び出しが存在しないこと（NOLOG-2、NOFS-1）
    Dependency Direction（15章）で許可されたimport（re, hashlib のみ、
        Architecture Amendment反映）以外が存在しないこと（DEP-1a）
    `hashlib`のimportが存在すること（DEP-1c、Architecture Amendment新規、
        肯定的Guard）

採用しないGuard：
    正規化アルゴリズムの実装手段（正規表現の具体的なパターン文字列等）を
        固定するGuard。10章のContract（振る舞い）さえ満たせば、
        実装手段の変更を妨げるべきではない
```

## 20. Formal Regression Strategy（実績反映、Completed）

正式Regressionの基準は、Release 6.15完了時点の`docs/CHANGELOG.md`記載の実測値を参照する。

```text
Release 6.15完了時点の累積Regression Inventory：
    対象：18ファイル（既存17ファイル＋v6.15.0新規E2E）
    総合：2365/2365 PASS

Release 6.16実装後に想定するもの（Architecture Amendment Finding AM-S-2反映、
19章確定Inventoryに基づく正式な予定件数）：
    Release 6.15までの正式Regression（18ファイル、2365件）：2365/2365 PASS維持
    Release 6.16新規E2E：143/143 PASS（19章確定Inventory：60 Scenario・
        104 Case・143 Assertion、Architecture Amendment反映後）
    予定総Assertion数：2508件（＝既存2365件＋新規143件）
    Warning：0件
    終了コード非0：0ファイル
    実行対象合計：19ファイル（既存18ファイル＋新規v6.16.0 E2E 1ファイル）
    実HTTP・実credential読込・実課金：いずれもなし
```

上記の「143」「2508」はArchitecture Amendment時点でのInventoryに基づく予定値であり、20.1節のとおり実測値と完全一致した（初回Architecture Review時点の「137」「2502」から、Japanese／Unicode Fallback Collision対策の追加により更新したもの）。

現行tests全体の無差別実行は正式Regressionとしない（既存precedentと同一の「累積Regression Inventory方式」に従い、正式対象ファイルのみを個別実行する）。既存E2Eファイルは1件も変更していない（Zero Diff、17章）。

### 20.1 Formal Regression実績

```text
実行日：2026-07-20
正式対象：19ファイル（既存18ファイル＋新規v6.16.0 E2E 1ファイル）
実行方式：各ファイルを個別に`python tests/<file>`で実行（一括`pytest`実行なし）
実行順序：v1.11.0 → v5.9.0 → v6.0.0 → v6.1.0 → v6.2.0 → v6.3.0 → v6.4.0 →
    v6.5.0 → v6.6.0 → v6.7.0 → v6.8.0 → v6.9.0 → v6.10.0 → v6.11.0 →
    v6.12.0 → v6.13.0 → v6.14.0 → v6.15.0 → v6.16.0
```

Version別実測結果（すべて終了コード0、Warning 0、Traceback 0）：

```text
v1.11.0：43/43   v5.9.0：64/64    v6.0.0：43/43    v6.1.0：44/44
v6.2.0：64/64    v6.3.0：174/174  v6.4.0：171/171  v6.5.0：131/131
v6.6.0：135/135  v6.7.0：117/117  v6.8.0：197/197  v6.9.0：331/331
v6.10.0：78/78   v6.11.0：248/248 v6.12.0：91/91   v6.13.0：123/123
v6.14.0：217/217 v6.15.0：94/94   v6.16.0：143/143
```

```text
既存18ファイル対象数：18
既存PASS合計：2365（Release 6.15完了時点baseline 2365/2365と完全一致、
    ベースライン変更なし）
新規v6.16.0対象数：1
新規v6.16.0 PASS：143（19章・Code Review時点の実測143/143と完全一致）
総合対象数：19
総合PASS合計：2508
FAIL合計：0
Warning合計：0（`DeprecationWarning`／`UserWarning`等のPython warning class
    パターンで19ファイル全ログを機械確認し0件。"WARNING"という文字列一致は
    `RetryAlertLevel.WARNING`等のContract文言・"Tracebackを含まない"という
    テストlabel文言としての出現であり、Python runtime warning・実際の
    Tracebackではないことを個別に文脈確認した）
Traceback出力：0件（実行ログ全件で確認。初回実行時のみv6.11.0で
    `ModuleNotFoundError`によるTracebackが発生したが、これは後述のとおり
    venv環境要因であり、修復後の本実績には含まれない）
終了コード非0：0ファイル
外部API実接続：0件（`OPENAI_API_KEY`等の認証情報はいずれも未設定のまま
    全19ファイルが正常終了）
Environment残留：なし（`AI_IMAGE_GENERATION_ENABLED`等7変数・cwdを実行前後で
    比較し不変を確認）
重複実行・二重集計：なし（各ファイル1回のみ実行）
```

Formal Regression判定：**Completed**（正式対象19ファイル全実行・各終了コード0・全Assertion PASS・FAIL 0・Warning 0・対象外ファイル混入なし・既存E2E無改修）

### 20.2 初回Formal Regression失敗の経緯（Release 6.16のProduction defectではないことの明記）

初回のFormal Regression試行（2026-07-20）は、`test_e2e_v6_11_0_openai_image_generation_adapter_foundation.py`が`import openai`時点で`ModuleNotFoundError: No module named 'openai'`を送出し、終了コード1で実行不能となったため`Failed`と判定した。

原因調査の結果、`requirements.txt`には`openai>=2.46.0,<3.0.0`が既にv6.11.0リリース時から記載されていたにもかかわらず、`projects/03_game_content_ai/venv`（ローカル実行環境）には`openai`パッケージが未インストールであることが判明した（`pip show openai`で不在を確認）。これはv6.11.0以降のいずれかの時点でvenvが`requirements.txt`と乖離した**既存の環境セットアップ差分**であり、Release 6.16が追加・変更したPublic API・依存関係・Production Codeのいずれにも起因しない（Release 6.16のDependency Guardは`re`／`hashlib`のみを対象とし、`openai`には一切関与しない）。

`python -m pip install -r requirements.txt`（venv明示指定、`requirements.txt`自体は無変更）によりvenvを`requirements.txt`の宣言と整合させたうえで19ファイルを再実行し、20.1節のとおり全件PASSを確認した。したがって本Findingは**Release 6.16のProduction defectではなく、ローカル実行環境のセットアップ不備**として記録する。

## 21. Documentation Integration Plan（Completed）

実装工程完了後、次の文書を更新する想定であった。Documentation Integration工程（本工程）で以下をすべて反映済み。

```text
docs/ROADMAP.md：v6.16.0実績エントリの追加、次候補リストから
    「Generated Image Filename Policy Foundation」を実績化 → 反映済み
docs/architecture.md：Generated Image Filename Policy Foundation層の
    component節を新設 → 反映済み
docs/CHANGELOG.md：`## [v6.16.0]`Entryの新規追加（Added／Public API／
    Architecture・Behavior／Tested／Scope） → 反映済み
本設計書：Header・Review History・Formal Regression実績節の更新 → 反映済み
```

Historical Record（v1.11.0〜v6.15.0の既存Entry）はいずれも変更していない。

## 22. Risks

```text
本Foundationは11.4節のallow-list（4形式）のみをサポートする。将来
    OpenAI Images APIが新しいmime_typeを返すようになった場合、
    Runtime Wiring側で本Foundationの拡張（allow-list追加）を伴う
    Architecture Reviewが別途必要になる
title正規化（10章）はgenerate_slug()と同型のASCII-onlyアプローチを
    採用しているため、日本語titleは常にhash付きfallback（10.5.2節、
    Architecture Amendment反映）へ切り替わる。画像ファイル名としての
    SEO価値（記事内容を示唆するfilename）は英語titleの場合にのみ得られ、
    日本語titleの場合は`"generated-image-<hash8>"`という機械的な
    filenameになる。この制約自体（ASCII-onlyな読みやすいslugを
    日本語titleから得られないこと）は既存generate_slug()と同一であり、
    本Foundation固有の新規リスクではない。Architecture Amendmentが
    解消したのは「異なる日本語titleが常に同一の固定文字列に収束する」
    という別の問題（12.4節・12.5節）であり、SEO価値の制約そのものは
    引き続き残存する（両者は別の論点である）
14章のSecurity Contractは「本Foundationが受け取る入力」の範囲でのみ
    保証される。将来Caller側がtitleへ機微情報を含めて渡した場合、
    正規化後の断片（ASCII部分の一部）がfilenameへ残存する可能性は
    構造的に排除できない（generate_slug()と同一の既知の制約）
```

## 23. Alternatives Considered

### Alternative A：`ArticleData`を直接受け取る

不採用。9.2節で詳述。

### Alternative B：`GeneratedImage`（v6.10.0）を直接受け取る

不採用。理由：

```text
image_bytesという本Foundationが一切使用しないfieldまで受け取ることになる
ai_image_generationへの依存が発生し、Dependency Directionが後退する
mime_type単独を受け取る案（採用案）と比べて、Public APIが不必要に広くなる
```

### Alternative C：class形式（`GeneratedImageFilenamePolicy`）＋`resolve()`メソッド

不採用。8.1節で詳述。依存注入を必要としないため、空Constructorを持つclassは既存precedentと不整合。

### Alternative D：標準ライブラリ`mimetypes`モジュールの利用

不採用。11.3節で詳述。環境依存の非決定的挙動が5章のdeterministic要件と矛盾する。

### Alternative E：filenameを`(basename, extension)`のtupleで返す

不採用。理由：

```text
ArticleFeaturedMediaOrchestrator.apply(article, prompt, filename)は
    filename: strという単一文字列を期待しており（v6.14.0 Contract）、
    tupleを返すと将来のCallerが結合処理を別途実装する必要が生じる
単一strを返すことで、戻り値の扱いが最も単純になる（8章AD-13）
```

### Alternative F：filenameに一意性suffixを内部で自動付与する

12.2節（初回Architecture Design時点）では全面的に不採用としていた。Architecture Amendment（12.5節）により、**ASCII slugが得られる場合には全面不採用のまま維持し、ASCII slugが得られない場合（fallback発動時）に限りtitle文字列の決定的hashをsuffixとして付与する**、という限定的な採用へ修正した。全titleへ一律にsuffixを付与する案（本Amendmentの案C、12.5.3節）は改めて不採用としており、Alternative Fの「全面採用」という選択肢自体は依然として採用していない。

### Alternative G：`wordpress_media._FILENAME_PATTERN`を直接importして検証に使う

不採用。理由：

```text
wordpress_mediaへの依存が発生し、Consumer-less Foundationの独立性
    （15章）が損なわれる
本Foundationの出力charset（10.2節：小文字英数字・ハイフン・単一dot）は、
    wordpress_mediaの正規表現（^[A-Za-z0-9][A-Za-z0-9._-]*$）の
    部分集合として構造的に適合するため、依存せずとも実務上の
    互換性は保たれる（4.4節に非拘束の互換性情報として記載）
```

### Alternative H：`unicodedata.normalize('NFKC', title)`による全角英数字の半角化（Architecture Review Finding AR-Minor-8反映）

不採用。15.3節で詳述。`generate_slug()`との一貫性を優先し、新規標準ライブラリdependencyの追加を本Releaseでは行わない。効果は限定的（全角英数字混在titleのみ）であり、12.4節で受け入れた「fallback収束」という帰結を解消するものでもない。将来、実際のfallback発生率が問題になった場合の改善候補として25章（Future Candidates）へ記録する。

## 24. Open Questions

```text
なし
```

候補調査で提起されたOpen Questions（画像生成呼び出しのタイミング、
Publish Composition Rootの配線方式等）は、いずれも本Release（Filename
Policyのみ）のScope外であり、25章（Future Candidates）で後続Release側の
論点として引き継ぐ。本層自体のPublic Contract（Package／Public API形状・
入力Contract・正規化規則・拡張子Contract・一意性判断・Error・Security・
Dependency Direction）については、本文書内ですべて確定できたと判断する。

## 25. Future Candidates

以下は、本Release完了後の別Releaseで検討する候補である。番号・正式名称は本文書で確定しない。

```text
Article Featured Media Runtime Wiring
    （本Foundation・Article Image Prompt Construction・Publish Composition
     Rootのうち残る前提が揃った時点でのmain.py／image_resolver.py接続）

Article Image Prompt Construction Foundation
    （記事タイトル・本文・SEO情報からOpenAI Images API向けpromptを構築する、
     本Releaseとは独立したFoundation）

Publish Composition Root Foundation
    （RetryCompositionRootと対をなす、記事生成→WordPress投稿の生成・配線を
     専用に担うComposition Root。本Foundationが返すfilenameの実際の
     呼び出し元候補の1つ）

Image Generation Fallback Policy
    （画像生成・Upload失敗時に記事投稿を継続するか中止するかの業務判断）

Media Upload Retry／Idempotency Foundation
    （本Foundationの決定性（12.3節）を活用しうる、Idempotency Keyの
     確立を含む後続Foundation）

WordPress Unused Media Cleanup Foundation
    （Upload成功後の記事投稿失敗時に残る未使用WordPress Mediaの検出・
     削除方針。WordPressMediaUploaderに削除APIが現状存在しないことを
     踏まえ独立検討する）

拡張子allow-listの拡張
    （22章Risks参照。OpenAI Images APIの対応形式変更等に応じて
     別Releaseとして検討する）

hash長の拡張（10.5.2.2節参照。Architecture Amendmentで8文字と確定した
    hash長は、本プロジェクトの現在の記事投稿規模を前提としている。
    将来、実際の記事数がこの前提を大きく超えると判明した場合は、
    hash長を拡張する別Releaseを検討する）

unicodedata NFKC正規化の追加（15.3節・23章Alternative H参照。全角
    英数字混在titleに対するASCII slug品質向上策。hash付きfallback
    （Architecture Amendment）とは独立した改善であり、実際の運用データ
    （fallback発生率）が判明した時点で検討する）
```

## 26. Acceptance Criteria

```text
[x] generate_image_filename()がPublic importできる
[x] title・mime_typeの2引数を受け取り、strを返す
[x] 通常のASCII titleがkebab-case化・lowercase化されること
[x] 日本語のみ・空・空白のみのtitleがhash付きfallback basename
    （"generated-image-<hash8>"、10.5.2節。Documentation Integration時点で
    Architecture Amendment前の記述「"generated-image"のみ」を訂正した）
    へ切り替わること（例外を送出しない）
[x] 制御文字・path separator（/ \）・Windows予約文字（< > : " | ? *）が
    正規化後のbasenameに一切含まれないこと
[x] Windows予約デバイス名（CON等、拡張子付与前のslug部分で判定。
    COM0・COM10・LPT0・LPT10は対象外）に完全一致した場合、
    suffix（"-image"）が付与されること
[x] 戻り値の先頭・末尾にdot／spaceが残らないこと
[x] slug部分が60文字を超える場合、単語境界を優先してtruncateされること
[x] 戻り値全体（拡張子込み）の長さが常に65文字以内であること（10.5.1節）
[x] titleまたはmime_typeがstrのsubclassである場合、例外を送出せず
    正常に処理されること（9.5節）
[x] 同一(title, mime_type)は常に同一のfilenameを返し、本Foundation
    単体では完全な一意性を保証しないことがContractとして明記されて
    いること（12.4節・12.5.6節）
[x] ASCII slugが生成できない場合（fallback発動時）、title原文の
    sha256決定的hash（UTF-8エンコード、先頭8文字、小文字hex）を
    suffixとして付与した`"generated-image-<hash8>"`を返すこと
    （10.5.2節、Architecture Amendment）
[x] 異なるtitleが（低確率のcollisionを除き）異なるhash付きfallback
    filenameを返すこと、同一titleは常に同一のhash付きfallback
    filenameを返すこと（10.5.2.1節・12.5.2節）
[x] hash計算がtitleの正規化前の原文を入力とし、UTF-8エンコード・
    saltなし・時刻／乱数／環境非依存であること（10.5.2.1節）
[x] hash付きfallbackが戻り値全体の最大長（65文字）を超えないこと
    （固定24文字＋拡張子、10.5.1節）
[x] hash付きfallback basenameがWindows予約デバイス名と構造的に
    衝突しないこと（10.6節）
[x] 本層が`hashlib`を許可依存とし、`mimetypes`／`unicodedata`／
    `datetime`／`random`／`uuid`／`locale`はいずれも禁止のまま
    維持すること（15章・15.4節）
[x] image/png・image/jpeg・image/webp・image/gifがそれぞれ.png・.jpg・
    .webp・.gifへ正しくマッピングされること
[x] allow-list外・非canonicalなmime_typeがValueError（固定message）を
    送出すること（fallbackしない）
[x] title・mime_typeの型不正がいずれもValueError（固定message）を
    送出すること
[x] Validation Orderが13.1節のとおり確定していること
[x] 同一(title, mime_type)に対する戻り値が常に等価（決定論的）であること
[x] 戻り値がdirectory traversal文字列・絶対path形式を一切含まないこと
[x] 本層がHTTP通信・credential読込・環境変数読込・ファイルI/O・
    Logging・時刻取得・乱数生成のいずれも行わないこと
[x] 本層がPython標準ライブラリ（re, hashlib）以外の project内package・
    外部package依存を持たないこと（Architecture Amendment反映）
[x] 既存package（outputs／ai_image_generation／wordpress_media等）の
    いずれもgenerated_image_filename_policyへ逆依存しないこと
[x] 循環importが発生しないこと
[x] 既存の全package・全モジュールが無変更であること（17章 Zero Diff）
[x] 新規E2E（tests/test_e2e_v6_16_0_generated_image_filename_policy_foundation.py）
    が全PASSすること（143/143 PASS、実測済み）
[x] 既存正式Regression（18ファイル・2365件）が維持されること
    （2365/2365 PASS、実測済み）
```

全項目を実測・実装・Code Review・Formal Regressionで確認済み。未充足項目なし。

## 27. Implementation File Plan（実績）

```text
新規（Production Code、作成済み）：
    projects/03_game_content_ai/src/generated_image_filename_policy/__init__.py
    projects/03_game_content_ai/src/generated_image_filename_policy/generated_image_filename_policy.py

新規（Test、作成済み）：
    projects/03_game_content_ai/tests/test_e2e_v6_16_0_generated_image_filename_policy_foundation.py

新規（本設計書、Documentation Integrationにより最終更新）：
    projects/03_game_content_ai/docs/design/generated_image_filename_policy_foundation.md

変更（Documentation Integration工程のみ）：
    projects/03_game_content_ai/docs/ROADMAP.md（v6.16.0実績エントリ追加）
    projects/03_game_content_ai/docs/architecture.md（component節新設）
    projects/03_game_content_ai/docs/CHANGELOG.md（`## [v6.16.0]`Entry追加）

削除：
    なし
```

Production Implementation・Formal Regression工程を通じて、上記計画からの逸脱はなかった（実装したファイルは当初計画どおりの2ファイル＋新規E2E1ファイルのみ）。

## 28. Review Checklist（Architecture Amendment完了時点、Claude Codeによる独立Review）

```text
[x] Release GoalがFilenameのContract定義だけに限定されている（1章・3章）
[x] Runtime Wiringを要求していない（3.2節・17章）
[x] Composition Root接続を要求していない（3.2節）
[x] OpenAI／WordPress API呼び出しをScopeへ含めていない（3.2節・16章）
[x] Media Upload実行・Featured Media Binding実行をScopeへ含めていない（3.2節）
[x] Retry／Idempotency・Unused Media CleanupをScopeへ含めていない（3.2節）
[x] Image Prompt ConstructionをScopeへ含めていない（3.2節）
[x] .env変更を要求していない（3.2節）
[x] 入力Contract（title, mime_type）が既存ArticleData／GeneratedImageへの
    型依存なしで確定している（9章）。設計書の当初結論（narrow input採用）を
    Architecture Reviewでも独立に妥当と判断した（4.1節相当のReview観点）
[x] title・mime_typeの型判定方式（isinstance() vs type() is str、str subclass
    の扱い）が既存precedentとの比較根拠つきで確定している（9.5節、
    AR-Minor-1で追加確定）
[x] title正規化規則が既存precedent（generate_slug）の実装コード順序と
    厳密に一致する形で確定している（10.1節、AR-Minor-2で精緻化）
[x] 拡張子Contractが固定allow-list・非決定的手段（mimetypes／unicodedata）の
    排除を根拠に確定している（11章・15.3節）
[x] MIME type Contractがcanonical入力のみを受理する方式（正規化しない）で
    あることが明記され、大文字小文字・空白・parameter付き・"image/jpg"誤記の
    いずれも拒否することが確定している（9.4節・11.5節）
[x] 戻り値全体（拡張子込み）の最大長がContract化されている（65文字、
    10.5.1節、AR-Minor-5で追加）
[x] Windows予約デバイス名Guardの対象範囲（COM0／COM10除外）・判定タイミング
    （拡張子付与前）・suffix付与後の長さが確定している（10.6節、
    AR-Minor-3・AR-Minor-4・AR-Minor-6で追加確定）
[x] 一意性・決定性の判断が6案比較のうえ確定しており、実際のドメイン
    （日本語title主体）における実務上の帰結（fallback収束）がContract上の
    既知の性質として明示的に受け入れられている（12章・12.4節、
    AR-Major-1で追加確定）
[x] Validation順序が確定している（13.1節）
[x] 例外Contractが確定している（非strはValueError、unsupported MIME type
    もValueError、fallback対象とfallbackしない対象の境界が明確、13章）
[x] directory traversal・absolute path生成が構造的に不可能であることが
    示されており、その保証範囲（戻り値自体の性質に限定されること）も
    明記されている（10.4節・14章、AR-Minor-7で保証範囲を明確化）
[x] Dependency Directionが一方向（他の全project内packageから独立）で
    あり、`re`のみで十分（`unicodedata`は明示的に検討のうえ不採用）
    であることが確定している（15章、AR-Minor-8で検討過程を追加）
[x] 循環importがない（15.2節）
[x] State非保持・Thread Safetyが明記されている（16章）
[x] Runtime Zero Diffが明記されている（17章）
[x] Architecture原則（5章の10項目）との適合が確認されている（18章）
[x] E2E Test Strategyが「目安」ではなく正式Inventory（初回Architecture
    Review：AR-S-1で55 Scenario・98 Case・137 Assertionとして確定、
    Architecture AmendmentでAM-S-1により60 Scenario・104 Case・
    143 Assertionへ更新）として確定し、Scenario／Case／Assertionの
    対応・カテゴリ別内訳・合計が機械的に照合可能な形式になっている
    （19章、現行値：60／104／143）
[x] Regression基準がRelease 6.15記録（2365/2365 PASS）と19章確定Assertion数
    （現行値143、AM-S-2で更新）を根拠に、予定総Assertion数2508件として
    正確に算出されている（20章）
[x] Documentation Integration Planが計画のみで実施していないことが明記
    されている（21章）
[x] Open Questionsが後続Releaseへ明確に切り分けられている（24章）
[x] Japanese／Unicode Fallback Collision問題が独立に再評価され、
    5案（A〜E）すべてに対する明示的な比較・却下理由が示されている
    （12.5.1節、AM-Major-1で確定）
[x] 採用案（title文字列の決定的hash付きfallback）がPublic API・入力
    Contractのいずれも変更しないことが確認されている（12.5.2節）
[x] Unicode filename許可案（案D）が、既存の実消費者（WordPressMedia
    Uploader._validate_filename）との構造的非互換性を根拠に却下されて
    いる（12.5.4節）
[x] hash Contract（algorithm・encoding・hash入力（正規化前の原文）・
    digest表現・長さ・大文字小文字・salt・environment非依存・
    決定性・collision非保証・非セキュリティ目的）が曖昧なく確定して
    いる（10.5.2.1節）
[x] fallback発動条件が単一の条件（正規化後slug_base空文字列）に
    統一され、空／空白titleと非空Unicode titleとで規則を分岐させない
    理由が示されている（10.5.2.3節）
[x] hash付きfallbackとWindows予約デバイス名Guardの処理順序、および
    両者が構造的に衝突しないことが確認されている（10.6節、AM-Minor-3）
[x] Error Contract（13章）が本Amendmentにより変更不要であることが、
    既存precedentの再引用とともに確認されている（13.4節）
[x] hashのSecurity表現（復元不可能性を主張しない、匿名化目的では
    ない、非セキュリティ用途）が明記されている（14.1節、AM-Minor-4）
[x] `hashlib`を許可へ変更する理由が、他の禁止stdlib module
    （mimetypes／unicodedata／datetime／random／uuid）との評価軸の
    違いとともに示されている（15.4節）
[x] E2E Inventoryがhash Contractの変更に合わせて更新され、Scenario・
    Case・Assertionの合計が機械的に再照合可能な形式のまま維持されて
    いる（19章、60 Scenario・104 Case・143 Assertion、AM-S-1）
[x] Formal Regression予定件数が更新後Inventoryに基づき正確に算出
    されている（20章、2508件＝2365＋143、AM-S-2）
```

**初回Architecture Review**：Blocking 0件・Major 1件（AR-Major-1）・Minor 8件（AR-Minor-1〜8）・Suggestion 2件（AR-S-1〜2）、いずれも本文書内で解消。

**Architecture Amendment（Japanese／Unicode Fallback Collision対策）**：Blocking 0件。**Major**：1件（AM-Major-1、本文書内で解消）。**Minor**：4件（AM-Minor-1〜4、本文書内で解消）。**Suggestion**：2件（AM-S-1〜2、本文書内で反映）。矛盾・未解消事項は確認されなかった。

## 29. Review History

```text
2026-07-20: Claude Code（Architecture Designドラフト初版作成）。
    Repository Survey（4章）を実施し、src/slug_generator.py・
    src/ai_image_generation/・src/generated_image_wordpress_media/・
    src/article_featured_media_orchestration/・src/outputs/base.py
    （ArticleData）・src/wordpress_media/wordpress_media_uploader.py・
    docs/ROADMAP.md・docs/architecture.md・docs/development_workflow.mdを
    実読して確認した。Architecture Review・Production Implementation・
    新規E2E作成・Code Review・Formal Regression・Documentation
    Integration・Release Reviewはいずれも未実施。

2026-07-20: Architecture Review（Claude Codeによる独立Review）：Approved。
    Blocking Issueなし。設計書の結論（narrow input採用・module-level
    function・一意性責務外・固定allow-list拡張子）を無条件の前提とせず、
    代替案を含めて独立に評価した結果、いずれも妥当と判断した。
    検出：Critical 0件・Major 1件・Minor 8件・Suggestion 2件。

    Major：
    AR-Major-1：12章の一意性判断は妥当だが、実際のドメイン（日本語title
        主体）における帰結（fallback basenameへの事実上の収束）がRisk
        としての言及に留まり、Contract上の明示的な受け入れとして
        格上げされていなかった。→ 12.4節を新設し、確定Contractとして
        明記、26章Acceptance Criteriaへも反映。

    Minor：
    AR-Minor-1：title／mime_typeのisinstance()採用（type() is str不採用、
        str subclass受理）の判断根拠が明記されていなかった。→ 9.5節を
        新設し、bytesとの違い（immutabilityによりsubclass化の脅威が
        構造的に存在しない）を根拠に明記。
    AR-Minor-2：10.1節の正規化手順の記述順序が、generate_slug()実装
        コードの実際の処理順序と厳密には一致していなかった（機能的には
        等価）。→ 10.1節を実コードの順序に厳密に合わせて書き直した。
    AR-Minor-3：Windows予約デバイス名の判定を拡張子付与前のslug部分に
        対して行う理由（Windowsは拡張子の有無に関わらず予約名を同一
        デバイスとして扱う）が明記されていなかった。→ 10.6節に追加。
    AR-Minor-4：COM0／COM10等を対象外とする根拠が明記されていなかった。
        → 10.6節に追加、E2E WIN-3として確定。
    AR-Minor-5：10.5節がslug部分の最大長のみをContract化しており、
        Public APIが返す戻り値全体の最大長が明示的にContract化されて
        いなかった。→ 10.5.1節を新設し、65文字を確定。
    AR-Minor-6：Windows予約名suffix付与後の最大長への言及がなかった。
        → 10.6節に追加（最大10文字、再truncate不要）。
    AR-Minor-7：14章のSecurity Contractの一部表現が、戻り値自体の性質
        への保証であることの限定を欠き、無限定に強く読める可能性が
        あった。→ 14章に適用範囲を明確化する注記を追加。
    AR-Minor-8：15章のDependency Guardがunicodedataを明示的に検討して
        いなかった。→ 15.3節を新設し、NFKC正規化による全角英数字対応の
        効果とtrade-offを検討のうえ不採用と確定。23章Alternative Hにも
        追加。

    Suggestion：
    AR-S-1：19章のE2E Inventoryが「目安」のまま確定していなかった。
        → 19章を55 Scenario・98 Case・137 Assertionの確定Inventory
        （Scenario ID・Case ID・入力・期待結果・Assertion数の対応表、
        カテゴリ別内訳、合計の機械的照合）へ全面的に書き換えた。
    AR-S-2：20章のFormal Regression予定件数が19章の目安値（63）を参照する
        曖昧な記述だった。→ 137という確定値を反映し、予定総Assertion数
        2502件（2365＋137）を明記した。

    Major 1件・Minor 8件・Suggestion 2件のすべてを本文書内の修正で解消し、
    Blocking Issueが0件であることを確認したうえで、最終判定を
    「Approved」とした。Production Code・Test・統合文書（ROADMAP／
    architecture.md／CHANGELOG）・Git stage／commit／pushのいずれにも
    着手していない。

2026-07-20: Architecture Amendment（Claude Codeによる独立Review、
    Japanese／Unicode Fallback Collision対策）：Approved。Blocking Issue
    なし。ユーザー指示に基づき、12.4節（初回Architecture Review、
    AR-Major-1）が受け入れた「fallback収束」という帰結を、直前の
    Approved判定を前提とせず独立に再評価した。5案（A：現行維持、
    B：hash付きfallback（title、fallbackのみ）、C：全titleへhash suffix、
    D：Unicode filename許可、E：caller supplied identifier）を比較し、
    推奨方向（B相当）を無条件に採用せず、それぞれの却下・採用理由を
    独立に検証した（12.5.1節〜12.5.5節）。

    検出：Critical 0件・Major 1件・Minor 4件・Suggestion 2件。

    Major：
    AM-Major-1：12.4節が受け入れた「fallback収束」は、実用的なfilename
        policyとして不十分と判断した（将来のretry／idempotency／
        unused media cleanup／障害調査を困難にし、WordPress側renameへ
        実質的に依存する運用を招く）。→ 12.5節を新設し、ASCII slugが
        得られない場合に限りtitle原文の決定的hash（sha256、UTF-8、
        先頭8文字）をsuffixとして付与するContractへ変更した
        （10.5.2節）。Public API・入力Contractはいずれも変更していない。

    Minor：
    AM-Minor-1：12.1節の案D（hash suffix）比較は「画像バイト列のhash」
        を評価しており、「title文字列（既存入力）のhash」という、
        入力Contractを一切拡大せずに実現できる別の変種を独立して
        評価していなかった。→ 12.1節・12.2節に案D'として明示的に
        区別・追記し、12.5.1節で改めて独立評価した。
    AM-Minor-2：15章のDependency Guardが`hashlib`を一律禁止として
        いたが、その禁止は画像バイト列hash（Option D）を前提とした
        ものであり、title文字列のhash化には適用されない区別が
        明記されていなかった。→ 15章・15.4節を更新し、`hashlib`を
        許可依存へ変更したうえで、他の禁止stdlib module
        （mimetypes／unicodedata／datetime／random／uuid）との
        評価軸の違いを明記した。
    AM-Minor-3：Windows予約デバイス名Guardとhash付きfallbackの処理
        順序、および両者が構造的に衝突しないことの検証が未記載
        だった。→ 10.6節に追記し、hash付きfallback basename
        （最小24文字、Code Review時点で「25文字」から訂正）が
        予約名（最大4文字）と構造的に一致し得ない
        ことを明記した。
    AM-Minor-4：hashの実務上の非可逆性について、過大・過小いずれの
        主張も設計書上に存在しなかった（新規追加のため必須の対応）。
        → 14.1節を新設し、8文字への切り詰めによりbrute force照合が
        現実的に可能であること、暗号学的な秘匿性を主張しないことを
        明記した。

    副次的に発見した既存の記述誤り（Blocking／Major／Minor Findingとしては
    計上せず、本工程内で修正）：10.5.1節が「10.6.1節」という存在しない
    サブ節番号を参照していた（初回Architecture Review時点で混入した誤記）。
    → 10.6節はサブ節番号を持たない構成であることを明記し、参照を修正した。

    Suggestion：
    AM-S-1：19章のE2E Inventoryがhash Contractの変更に対応していな
        かった。→ UNI-1／EMPTY-1／EMPTY-2／FALLBACK-1の期待値を
        実測hash値（UTF-8、`hashlib.sha256`で実際に計算した値）へ
        更新し、HASH-1（差別化）・HASH-2（決定性）・HASH-3（形式）・
        LONGUNI-1（長文）・HASH-ENV-1（locale非依存）の5 Scenarioを
        新規追加、DEP-1へhashlib存在確認のCaseを追加、NOFS-1から
        hashlib禁止確認を除去した。Inventoryは55／98／137から
        60／104／143へ更新した。
    AM-S-2：20章のFormal Regression予定件数が更新前の137を参照した
        ままだった。→ 143を反映し、予定総Assertion数を2508件
        （2365＋143）へ更新した。

    Major 1件・Minor 4件・Suggestion 2件のすべてを本文書内の修正で解消し、
    Blocking Issueが0件であることを確認したうえで、最終判定を
    「Approved」とした。5案の比較・採用案（title文字列のhash、
    fallback発動時のみ）はいずれも独立評価に基づく判断であり、ユーザーが
    提示した「推奨方向」を無条件の前提とはしていない（案D（Unicode
    filename許可）は技術的非互換性を独自に発見して却下し、案C（全title
    hash）はSEO価値とのtrade-offを独自に評価して却下した）。Production
    Code・Test・統合文書（ROADMAP／architecture.md／CHANGELOG）・Git
    stage／commit／pushのいずれにも着手していない。

2026-07-20: Production Implementation＋新規E2E作成（Claude Code）。設計書
    どおり`src/generated_image_filename_policy/__init__.py`・
    `generated_image_filename_policy.py`を作成した。STATE-AST-1（module-level
    Assign非存在）を満たすため、MIME拡張子mapping・Windows予約名集合を
    module-levelではなく関数ローカルへ配置し、`generate_slug()`と同様に
    正規表現もinline文字列として都度渡す実装とした。新規E2E
    （`tests/test_e2e_v6_16_0_generated_image_filename_policy_foundation.py`）を
    19章の確定Inventoryどおりに実装し、単独実行で60 Scenario・104 Case・
    143 Assertion・143/143 PASS（終了コード0、Warning／Traceback 0）を
    確認した。hash期待値はProduction関数から動的生成せず、設計書10.5.2節の
    実測値をliteralとして使用した。実装中に、設計書10.6節が予約デバイス名を
    「11種」と誤記していた点（正しくは個別名22種）を実装不能な誤記として
    発見し、Contract（判定対象集合自体）を変更しない最小修正を行った。

2026-07-20: Code Review（Claude Codeによる独立Review）：Approved with
    Suggestions。Blocking Issueなし。検出：Critical 0件・Major 0件・
    Minor 1件（CR-Minor-1）・Suggestion 1件（CR-S-1）。

    CR-Minor-1（Design document defect）：設計書内4箇所（10.5.1節・10.6節・
        26章・29章）で、hash付きfallback basenameのprefix`"generated-image-"`
        の文字数を「17文字」「合計25文字」と誤記していた（実際は16文字＋
        8桁hex＝24文字）。65文字上限に対する結論・Contract自体は不変。
        → 4箇所すべて訂正した（本文書内で解消）。
    CR-S-1（Non-Blocking Suggestion）：STATE-AST-1準拠のため、MIME mapping
        とWindows予約名集合を関数ローカルに配置しており、呼び出しごとに
        再構築される。現Contractでは正しい実装であり、実測でperformance
        問題も確認されなかったため、Production変更は行わず、Known Issueへも
        昇格しない（9章 Code Review Suggestionの扱い、参照）。

    hash期待値8個すべてを、Python標準ライブラリ`hashlib`とは別の実装
    （PowerShellの.NET `SHA256`）で独立再計算し、全件一致を確認した。
    Production Code・Testはいずれも修正不要と判断したが、CR-Minor-1の
    解消のため設計書のみ本工程内で修正した。新規E2Eは修正後も143/143 PASSを
    維持することを確認した。

2026-07-20: Formal Regression（Claude Code）：**Failed**（初回試行）。
    正式対象19ファイルを個別実行したところ、
    `test_e2e_v6_11_0_openai_image_generation_adapter_foundation.py`が
    `import openai`時点で`ModuleNotFoundError: No module named 'openai'`を
    送出し、終了コード1で実行不能となった。`requirements.txt`には
    `openai>=2.46.0,<3.0.0`が既にv6.11.0時点から記載されていたが、
    ローカルvenvには未インストールであることが原因と判明した（Release 6.16の
    変更に起因しない、既存の環境セットアップ差分）。他18ファイルはいずれも
    正式件数どおりPASSしたが、1ファイルでも実行不能があったため
    Documentation Integrationへは進まず停止した。

2026-07-20: Dependency Environment Repair（Claude Code）。`.\venv\Scripts\
    python.exe -m pip install -r requirements.txt`（venv明示指定、
    `requirements.txt`自体は無変更）によりvenvを修復した。導入前後で
    `pip show openai`（不在→2.46.0）・`pip check`（導入前後とも
    conflictなし）を確認し、使用Python executable・Git状態が導入前後で
    不変であることも確認した。

2026-07-20: Formal Regression（Claude Code）：**Completed**（再実行）。
    正式対象19ファイルを個別実行し、既存18ファイル2365/2365 PASS
    （Baseline維持、新規差分なし）＋新規v6.16.0 E2E 143/143 PASS＝
    総合2508/2508 PASSを確認した（20.1節）。FAIL 0・Warning 0
    （Python warning classパターンでの機械確認込み）・終了コード非0
    なし・外部API実接続0・Environment残留なしを確認した。詳細は20.2節に
    記録したとおり、初回失敗はRelease 6.16のProduction defectではなく
    venv環境要因であったことを明記する。

2026-07-20: Documentation Integration（Claude Code）：Completed。本文書の
    Header・19章・20章（20.1節・20.2節新設）・21章・26章（Acceptance
    Criteria全項目`[x]`化、Architecture Amendment前の記述の訂正含む）・
    27章・本Review Historyエントリを更新した。`docs/ROADMAP.md`
    （v6.16.0実績エントリ追加、次候補リストから実績化、Article Featured
    Media Runtime Wiring等の前提再整理）・`docs/architecture.md`
    （Generated Image Filename Policy Foundation層のcomponent節新設）・
    `docs/CHANGELOG.md`（`## [v6.16.0]`Entry新規追加）へ反映した。
    過去Release（v1.11.0〜v6.15.0）の記録はいずれも変更していない。
    Architecture変更なし、Blocking Issueなし。Release Reviewはまだ
    実施していない。

2026-07-20: Release Review（Claude Codeによる独立Review）：**Approved**。
    Blocking 0件・Major 0件・Minor 0件・Suggestion 1件（CR-S-1、継続）。
    Open Questionsなし。

    横断確認した内容：
    - Production Code 2ファイルを個別に精読し、設計書のPublic API・
      Validation Order（title型→mime_type型→MIME allow-list→title正規化）・
      固定Error message 3種・MIME exact match（`.strip()`／`.lower()`／
      parameter除去のいずれも不在）・slug正規化順序（`generate_slug()`と
      同一）・hash入力が正規化前の元title・fallback発動条件（slug_baseが
      空の場合のみ）・Windows予約名22個・最大長・許可import（`re`／
      `hashlib`のみ）・module-level Assign不在・logging／print／
      filesystem／network／environment参照不在のすべてが一致することを
      確認した。
    - 新規E2Eを再実行し143/143 PASS（終了コード0）を確認。実行時labelの
      動的捕捉により60 Scenario・104 Case・143 Assertionが設計書§19の
      表と欠落0・余剰0で一致することを再確認した。E2Eは`hashlib`を
      importしておらず、Production private helper（`_build_slug_base`等）
      も一切参照していないため、Productionと期待値生成処理を共有する
      self-fulfilling testでないことが構造的に保証されている（hash期待値は
      すべてliteral）。
    - Formal Regression記録（19ファイル・2508/2508 PASS）と、初回試行の
      `Failed`（venvの`openai`未導入）→venv修復→再実行`Completed`という
      経緯の双方が20.1節・20.2節・Review Historyへ保存されており、成功
      結果による上書き・隠蔽がないことを確認した。`requirements.txt`は
      当初から正しく、無変更であることをGit状態で確認した。
    - Historical Record非改変を確認した。`docs/CHANGELOG.md`は118行の
      純追加（削除0行）。`docs/ROADMAP.md`・`docs/architecture.md`の
      削除行は、いずれも`[ ]`未着手候補およびFuture Extension（前方参照
      リスト）の更新に限られ、完了済みReleaseのPASS件数・Review判定・
      Known Issueはいずれも改変していない。architecture.mdのv6.15.0節
      Future Extensionへの実装済みポインタ追記は、v6.15.0のDocumentation
      Integrationがv6.14.0節へ行った更新と同型の既存precedentである。
    - 4文書間で、Release名・version・Public API・package名・MIME
      mapping・fallback形式・hash長8桁・basename24文字・最大長65文字・
      予約名22種・60／104／143・2508/2508・各Review判定が一致することを
      確認した。旧値（55／98／137・2502・25文字・17文字）は設計書の
      Review History・訂正記録内にのみ、「旧稿」「Code Review時点で訂正」
      等の明示付きで残存しており、現行Contractとしては出現しない。
    - Runtime Wiring済みと誤解される記述がないこと、外部API実接続・
      Security Contract逸脱がないこと、Git状態が想定どおり（staged 0件・
      HEAD不変）であることを確認した。

    Release Review工程中にProduction Code・Testはいずれも変更していない
    （読み取り専用として扱った）。CR-S-1（STATE-AST-1準拠のためMIME
    mapping／Windows予約名集合を関数ローカルへ配置しており、呼び出しごとに
    再構築される）は、現Contractに適合し・実測performance問題がなく・
    Production変更不要であるため、Non-Blockingのまま維持し、Known Issueへは
    昇格させない（既存Code Review判定「Approved with Suggestions」と整合）。
    Release成果物7ファイル（正式設計書1・Production 2・新規E2E 1・統合文書3）
    全体を承認し、Release 6.16として完了とした。
```

---

（本文書はArchitecture Design・Architecture Review Approved・Architecture Amendment Approved・Production Implementation Completed・New E2E Completed（143/143 PASS）・Code Review Approved with Suggestions・Formal Regression Completed（2508/2508 PASS）・Documentation Integration Completed・Release Review Approvedをもって、Release 6.16として完了した。）
