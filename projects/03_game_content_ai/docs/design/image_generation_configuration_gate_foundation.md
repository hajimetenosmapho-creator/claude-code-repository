# Image Generation Configuration Gate Foundation — Architecture Design（v6.15.0）

作成日：2026-07-20（Architecture Designドラフト／Architecture Review／Production Implementation／新規E2E作成／Code Review／Formal Regression／Documentation Integration／Release Review）
作成者：Claude Code（Architecture Designドラフト／Architecture Review／Production Implementation／新規E2E作成／Code Review／Formal Regression／Documentation Integration／Release Review）／ChatGPT（Architecture Review確認・Code Review確認・Release Review確認：未実施）／ユーザー（最終承認：未実施）
状態：**Release Review実施済み（結果は0章Header参照）**
分類：**Architecture Release**（development_workflow.md 86行付近の定義。新規独立package・新規Public API・新規Dependency方向の確立を伴うため）

---

## 0. Header

```text
Release：6.15
Version：v6.15.0
正式名称：Image Generation Configuration Gate
Classification：Architecture Release
Status：Release Review Completed（Approved）
Architecture Design：Completed（本文書）
Architecture Review状態：Approved（Claude Codeによる独立Review。検出：
    Blocking 0・Major 1（AR18-M-1）・Minor 5（AR3-m-1、AR12-m-2、
    AR13-m-3、AR33-m-4、AR33-m-5）・Suggestion 2（AR20-S-1、AR23-S-2）。
    いずれも本文書内の修正で解消し、再Review：Blocking/Major/Minor/
    Suggestionいずれも0件、Blocking Issueなし。38章 Review History参照）
Production Implementation：Completed（35.1節。新規package
    `src/image_generation_config/`2ファイル、Architecture Designからの
    逸脱なし）
New E2E：PASS（24.2節。94/94 PASS、0 FAIL、終了コード0）
Code Review状態：Approved with Suggestions（Claude Codeによる独立Review。
    検出：Blocking 0・Major 0・Minor 3（CR9-m-1、CR14-m-1、CR15-m-1、
    いずれもTest実装の是正でありArchitecture Decision変更なし）・
    Suggestion 2（CR10-S-1：動的import検出はAST Guard対象外、v6.14
    precedentと同じ既知の制約として維持／CR19-S-1：本文書への実績反映、
    本Code Review内で実施済み）。Minor 3件は本工程で修正し新規E2E再実行
    94/94 PASS再確認済み、Suggestion CR10-S-1のみNon-Blockingのまま維持、
    Blocking Issueなし。38章 Review History参照）
Formal Regression状態：PASS（25.1節。既存17ファイル2271/2271 PASS＋新規
    v6.15.0 E2E 94/94 PASS＝総合2365/2365 PASS、FAIL 0、Warning 0、
    終了コード非0なし、実HTTP・実credential読込・実課金いずれもなし）
Documentation Integration状態：Completed（docs/ROADMAP.md／docs/architecture.md／
    docs/CHANGELOG.mdへv6.15.0を反映済み。既存Release記載・Historical Record
    は変更していない。38章 Review History参照）
Release Review状態：Approved（Claude Codeによる独立Review。検出：Blocking 0・
    Major 0・Minor 2（RR-m-1：Code Review完了報告の新規E2E行数「441行」が
    実ファイル「444行」と異なっていた単純な報告集計誤差、実ファイル内容は
    変更されておらず94/94 PASS再実行で内容一致を確認済み／RR-m-2：
    architecture.mdの新Component節に"18ファイル"という明示的合計表記が
    なかったため1箇所へ追記）・Suggestion 0件（CR10-S-1はCode Review由来の
    既存記録として維持、Release Review自体の新規Suggestionではない）。
    Minor 2件はいずれも文書表記の是正のみで、Public API・Environment
    Variable Contract・Architecture Decision・Production Code・Testへの
    影響なし。Blocking Issueなし。38章 Review History参照）
Release：Completed（38章 Review History参照）
```

本文書はArchitecture Design・Architecture Review・Production Implementation・新規E2E作成・Code Review・Formal Regression・Documentation Integration・Release Review（ROADMAP.md／architecture.md／CHANGELOG.md更新を含む）フェーズの成果物である。commit・pushのいずれも行っていない。

---

## 1. Executive Summary

Release 6.14までに、画像生成関連の5つのConsumer-less Foundation（`ai_image_generation` v6.10.0、`openai_image_generation` v6.11.0、`generated_image_wordpress_media` v6.12.0、`article_featured_media` v6.13.0、`article_featured_media_orchestration` v6.14.0）が確立された。いずれもProduction Runtime（`main.py`）へは未接続であり、直近の候補調査（Read-only Repository Survey、2026-07-20）により、Runtime Wiringを直ちに開始することは**Not Recommended Yet**と判定されている。

本Releaseは、そのRuntime Wiringに先立つ最初の前提Foundationとして、画像生成機能の有効/無効をConfiguration-Firstで制御するGateのみを確立する。新規package `image_generation_config` に、`enabled: bool` の1フィールドのみを持つ不変Configuration object `ImageGenerationConfig` を追加する。本Release単独では、いかなる既存Production Codeも変更せず、OpenAI API・WordPress APIのいずれも呼び出さない。

## 2. Background

- `docs/ROADMAP.md`のv6.14.0実績直後には、次候補「Article Featured Media Runtime Wiring」の前提条件がv6.14.0時点でも未充足である旨が記載されている（Future Candidatesに「Publish Composition Root Foundation」「Article Image Prompt Construction Foundation」「Generated Image Filename Policy Foundation」等が7件列挙されている）。
- 2026-07-20実施のRead-only Repository Survey（本Architecture Designの直前工程）により、次が確定している。
  - `ArticleFeaturedMediaOrchestrator`・`OpenAIImageGenerator`・`GeneratedImageWordPressMediaUploader`はいずれも`main.py`から未参照（grep確認済み、本文書4章で再確認）
  - 画像生成の有効/無効を切り替えるConfiguration Gateが repository内に存在しない
  - `OPENAI_API_KEY`・`OPENAI_IMAGE_TIMEOUT_SECONDS`は`OpenAIImageGenerator.from_env()`（`src/openai_image_generation/openai_image_generator.py:239-255`）が読み込むが、`.env.example`に未記載
  - Runtime WiringはNot Recommended Yet（Configuration Gate・Prompt Construction・Filename Policy・Composition Root・failure/retry境界のいずれも未整備のため）
- 本Releaseは、上記のうち「Configuration Gate」のみを対象とする。他の前提Foundation（Composition Root・Prompt Construction・Filename Policy）は本ReleaseのOut of Scopeとし、後続の独立Releaseへ委ねる。

## 3. Repository Survey Findings（本Architecture Design着手前の再確認）

Architecture Design着手前に、次のファイルをRead-onlyで再確認した。

| ファイル | 確認事項 | 結果 |
|---|---|---|
| `projects/03_game_content_ai/.env.example`（176行） | 既存`*_ENABLED`変数の記載パターン | `LOG_ENABLED`・`EXECUTION_HISTORY_ENABLED`・`SNS_ENABLED`・`ANALYTICS_ENABLED`・`SEARCH_CONSOLE_ENABLED`・`GOOGLE_ANALYTICS_ENABLED`・`AI_IMPROVEMENT_ENABLED`はセクション区切りコメント＋用途説明＋デフォルト値の順で記載。`OPENAI_API_KEY`・`OPENAI_IMAGE_TIMEOUT_SECONDS`・`AI_AGENT_ENABLED`は未記載（既知のDocumentation Gap） |
| `src/publishing_config.py` | `PublishingConfig`のenum-basedパース規約 | 不正値はWARNING print＋既定値へフォールバック（例外を出さない） |
| `src/ai/agent_config.py` | `AgentConfig.enabled`のbool parsing | `os.environ.get("AI_AGENT_ENABLED", "false").lower() == "true"`（strip無し） |
| `src/openai_image_generation/openai_image_generator.py` | `OPENAI_API_KEY`・`OPENAI_IMAGE_TIMEOUT_SECONDS`の既存責務 | `from_env()`（239-255行）が両方を読み込み、`OPENAI_API_KEY`未設定/空文字は`ValueError`、`OPENAI_IMAGE_TIMEOUT_SECONDS`不正値も`ValueError` |
| `src/article_featured_media_orchestration/__init__.py` | 直近Foundationのpackage構造規約 | docstringで担当範囲と非依存対象を明記、`__all__`でPublic API限定 |
| `src/openai_image_generation/__init__.py` | 同上 | 同上パターン |
| `src/analytics/analytics_config.py` | `*_ENABLED`系Configurationのdataclass形状 | `@dataclass`（frozenではない）、`from_env()`classmethod |
| リポジトリ全体（grep） | `*_ENABLED`のbool parsing規約の網羅確認（Architecture Reviewで再集計） | 19箇所中17箇所が`os.environ.get/os.getenv(..., "<default>").lower()[.strip()] == "true"`形式（Fail Closed）。残り2箇所（`LOG_ENABLED`：`src/logger/log_manager.py:47-48`、`SNS_ENABLED`：`src/sns_config.py:74`）は`.lower().strip() != "false"`という逆方向の判定（Fail Open、いずれもdefault "true"の機能）。例外を出す実装は19箇所中0件（この点は19/19で正しい） |
| `docs/development_workflow.md` | Release分類定義 | 「新規Subsystem・Public API変更・Composition Root変更・Layer変更・Dependency変更・Design Pattern変更・責務変更・永続化変更・外部サービス変更・Roadmap変更を伴うRelease」= Architecture Release。「迷った場合はArchitecture Release」の方針も明記 |
| `docs/design/article_featured_media_orchestration_foundation.md` | 直近設計書のCode Review由来Non-Blocking Finding（CR14-S-1） | 21章と22章のReverse Dependency Guard対象package数の**差異**がSuggestion指摘の原因。本設計書では21章・22章で完全に同一のGuard対象リストを使用し、同種の指摘を回避する（21章・22章参照） |
| `tests/test_e2e_v6_14_0_article_featured_media_orchestration_foundation.py` | E2E命名・Scenario/Assertion集計規約 | Scenario数は設計時に確定（例：v6.14は34 Scenario）、Assertion実測数は実装後のTest実行で確定（例：v6.14は217/217）。本設計書もこの区別を踏襲する（24章参照） |

結論：既存の`*_ENABLED`系Configuration規約は、19箇所中17箇所が`== "true"`のFail Closed方式である。残り2箇所（`LOG_ENABLED`・`SNS_ENABLED`）は`!= "false"`のFail Open方式だが、いずれもdefault "true"（デフォルト有効機能を明示的にOFFにする用途）であり、本Gate（default OFF・Feature opt-in）とは意味的なユースケースが異なるため参考にしない。本Releaseは、default OFF機能における多数派パターン（17/19、Fail Closed）に完全準拠する設計とする。

## 4. Problem Statement

画像生成機能（`OpenAIImageGenerator`・`ArticleFeaturedMediaOrchestrator`等）をProduction Runtimeへ配線する将来のReleaseに先立ち、次の問題が未解決である。

- 画像生成の有効/無効を制御する正式なConfiguration Contractが存在しない
- Gateが存在しないままRuntime Wiringを行うと、記事生成の全runで無条件にOpenAI Images APIが実課金呼び出しされる構造になる
- 既存の19箇所の`*_ENABLED`系Configurationと整合する新規Gateの正式仕様（環境変数名・parsing規則・Public API形状）が未決定である

## 5. Goals

```text
G-1: 画像生成の有効/無効を表す正式なConfiguration Contractを確立する
G-2: 未設定時のdefaultをOFFとし、既存Runtime挙動（無条件API呼び出しゼロ）を維持する
G-3: 意図しないOpenAI Images API呼び出し・API cost発生を防ぐ
G-4: 後続のRuntime Wiring／Composition Root Foundationから再利用できるGateを作る
G-5: 既存の*_ENABLED系Configuration規約のうち、default OFF機能で採用されている
      Fail Closed方式（19箇所中17箇所）と完全に整合させる（3章参照）
```

## 6. Non-Goals

```text
NG-1: main.pyへのRuntime Wiringを行わない
NG-2: ArticleFeaturedMediaOrchestrator／OpenAIImageGenerator／
      GeneratedImageWordPressMediaUploaderのRuntime生成を行わない
NG-3: Publish Composition Root Foundationを実装しない
NG-4: Article Image Prompt Construction Foundationを実装しない
NG-5: Generated Image Filename Policy Foundationを実装しない
NG-6: 画像生成failure continuation policy／fallback／retry／idempotency／
      unused media cleanupを決定しない
NG-7: image_resolver.py／WordPress記事投稿フロー／ArticleData／
      bind_featured_mediaを変更しない
NG-8: 既存Foundation（ai_image_generation〜article_featured_media_orchestration）の
      Public APIを変更しない
NG-9: OPENAI_API_KEY・OPENAI_IMAGE_TIMEOUT_SECONDSのvalidation責務を
      OpenAIImageGeneratorから奪わない
```

## 7. Scope

### 7.1 In Scope

```text
IS-1: 画像生成有効/無効設定の正式Contract（環境変数名・parsing規則・default）
IS-2: 新規Configuration package（Public API・不変性）
IS-3: OPENAI_API_KEY・OPENAI_IMAGE_TIMEOUT_SECONDSとの責務分離の明文化
IS-4: .env.exampleへの画像生成関連設定の追加方針（実装は本Release後続の
      Production Implementationフェーズで行う。本Architecture Design
      フェーズでは.env.example自体は変更しない）
IS-5: 新規E2E Test Strategy・Test Inventory（実装は後続フェーズ）
IS-6: Architecture Guard／Reverse Dependency Guard戦略
IS-7: Security／Logging Contract
```

### 7.2 Out of Scope

```text
OS-1:  main.pyへのRuntime Wiring
OS-2:  ArticleFeaturedMediaOrchestratorのRuntime接続
OS-3:  OpenAIImageGeneratorのRuntime生成
OS-4:  GeneratedImageWordPressMediaUploaderのRuntime生成
OS-5:  WordPressMediaUploaderのRuntime生成
OS-6:  Publish Composition Root Foundation
OS-7:  Article Image Prompt Construction Foundation
OS-8:  Generated Image Filename Policy Foundation
OS-9:  画像生成failure continuation policy
OS-10: fallback
OS-11: retry
OS-12: idempotency
OS-13: unused media cleanup
OS-14: WordPress記事投稿フロー変更
OS-15: image_resolver.py変更
OS-16: ArticleData変更
OS-17: bind_featured_media変更
OS-18: 既存FoundationのPublic API変更
OS-19: OpenAI API実呼び出し
OS-20: WordPress API実呼び出し
```

## 8. Scope Boundary Rationale

画像生成を安全にRuntimeへ接続するには、最低でも「有効/無効を切り替えられること」「promptを生成できること」「filenameを生成できること」の3つが必要である（Repository Surveyより）。本Releaseはこのうち最も前提条件が少なく、単独で安全に完結できる「有効/無効の切り替え」のみを対象とする。Prompt・Filenameは意味的に無関係な別責務であり、同一Releaseに混在させるとConsumer-less Foundationとしてのレビュー容易性が損なわれるため、意図的に分離した。

## 9. Terminology

```text
Gate：
    本文書における「有効/無効を表すbool値を提供するConfiguration Contract」を指す。
    Class名としては採用しない（10章参照）。

Configuration-First：
    本Repositoryの既存Foundationが一貫して採用する設計方針。機能追加時は
    まず環境変数によるopt-in/opt-outを用意し、未設定時は既存動作を維持する。

Consumer-less Foundation：
    tests/以外からの参照（consumer）を持たない、独立して完結したpackage。
    Release 6.9.0〜6.14.0の画像生成関連Foundationすべてがこの性質を持つ。

Fail Closed：
    不正・未知の入力値を「無効（OFF）」として扱い、例外を発生させない方針。
    既存の*_ENABLED系Configuration 19箇所中17箇所がこの方針を採用している
    （残り2箇所はFail Open、3章参照。default OFF機能に限れば17/17が
    Fail Closed）。

Reverse Dependency：
    本Foundationへ依存する側（将来のConsumer）ではなく、本Foundationが
    誤って既存Runtime componentへ依存してしまう方向を指す。本Releaseでは
    後者（禁止対象）の意味で使用する。
```

## 10. Existing Architecture（現状Runtime・Configuration構造）

- Configuration-First系のenable/disableフラグは、機能ごとに独立した`<Feature>Config`という名前の`@dataclass`として実装され、`from_env()` classmethodで環境変数を読み込む（`AgentConfig`・`AnalyticsConfig`・`SnsConfig`・`RetryConfig`・`SchedulerConfig`等、19箇所で確認）。
- これらのConfigクラスは既存の機能package内（例：`src/ai/agent_config.py`、`src/analytics/analytics_config.py`）に同居しており、Configだけの単独packageという先例は存在しない。ただし、v6.9.0以降の画像生成関連Foundation（`ai_image_generation`・`openai_image_generation`・`generated_image_wordpress_media`・`article_featured_media`・`article_featured_media_orchestration`）はいずれも「1機能＝1独立package＋`__init__.py`によるPublic API限定」という新しい規約を確立しており、本Releaseはこの新しい規約系列（v6.9.0以降）に属する。
- `main.py`はConfiguration系オブジェクト（`PublishingConfig.from_env()`・`SnsConfig.from_env()`等）を関数本体内でインラインに構築しており、専用Composition Rootは存在しない（唯一の例外は`RetryCompositionRoot`だが、Retry/Workflow/Scheduler専用）。

## 11. Proposed Architecture

新規package `src/image_generation_config/` を追加する。

```text
src/image_generation_config/
    __init__.py                    Public API限定（ImageGenerationConfigのみexport）
    image_generation_config.py     ImageGenerationConfig（frozen dataclass）の定義
```

依存方向：

```text
（将来）Composition Root／Runtime Consumer
    ↓ 依存（本Releaseでは未接続）
image_generation_config.ImageGenerationConfig
    ↓ 依存
Python標準ライブラリ（os, dataclasses）のみ
```

本Release単独では、上図の「将来」矢印は存在しない（Consumer-less、20章参照）。

## 12. Public API

```python
# src/image_generation_config/__init__.py
from .image_generation_config import ImageGenerationConfig

__all__ = [
    "ImageGenerationConfig",
]
```

```python
# src/image_generation_config/image_generation_config.py
from dataclasses import dataclass


@dataclass(frozen=True)
class ImageGenerationConfig:
    enabled: bool

    @classmethod
    def from_env(cls) -> "ImageGenerationConfig":
        ...
```

利用イメージ（本Release単独ではいかなるProduction Codeからも呼び出されない）：

```python
from image_generation_config import ImageGenerationConfig

config = ImageGenerationConfig.from_env()
if config.enabled:
    ...
```

## 13. Environment Variable Contract

### AD-1: Environment Variable名

**決定：`AI_IMAGE_GENERATION_ENABLED`**

比較した候補：

| 候補 | 評価 |
|---|---|
| `IMAGE_GENERATION_ENABLED` | 短く明確だが、既存Foundation群の確立済み名称「AI Image Generation」（`ai_image_generation` package、v6.10.0正式名称「AI Image Generation Contract Foundation」）との一貫性がない |
| `AI_IMAGE_GENERATION_ENABLED`（採用） | `ai_image_generation` package名・v6.10.0正式名称と完全に一致し、Release 6.10〜6.14の一連の命名（`ai_image_generation` → `openai_image_generation` → `generated_image_wordpress_media` → `article_featured_media` → `article_featured_media_orchestration`）の系列に自然に接続する。`src/ai/`配下の`AI_AGENT_ENABLED`等（Agent自動実行サブシステム専用）とは意味的に異なる対象だが、「AI-based image generation」という機能を正確に表すため許容する |
| provider固有名（例：`OPENAI_IMAGE_GENERATION_ENABLED`） | 不採用。GateがOpenAI固有になり、将来別Providerを追加した際に再設計が必要になるため（`AIImageGenerator` Protocol自体がprovider非依存であることと矛盾する） |

`AI_AGENT_ENABLED`・`AI_IMPROVEMENT_ENABLED`・`AI_WORKFLOW_ENABLED`等（`src/ai/`配下）とは責務が異なる別軸のGateであることを、本章および`.env.example`の将来的なコメント（Production Implementationフェーズで追加）で明記する。

### Validation／Error Contract決定表

| 入力 | 結果 | 備考 |
|---|---|---|
| 環境変数未設定 | `enabled=False` | `os.getenv(..., "false")`のdefault |
| 空文字 `""` | `enabled=False` | `"".lower().strip() == "true"` は False |
| 空白のみ `"   "` | `enabled=False` | strip後は空文字 |
| `"true"` | `enabled=True` | |
| `"TRUE"` | `enabled=True` | `.lower()`で正規化 |
| `"True"` | `enabled=True` | 同上 |
| `"  true  "`（前後空白付き） | `enabled=True` | `.strip()`で正規化 |
| `"false"` | `enabled=False` | |
| `"FALSE"` | `enabled=False` | |
| `"1"` | `enabled=False` | `"true"`の同義語として扱わない（Fail Closed） |
| `"0"` | `enabled=False` | |
| `"yes"` | `enabled=False` | 同上 |
| `"no"` | `enabled=False` | |
| `"on"` | `enabled=False` | |
| `"off"` | `enabled=False` | |
| 未知文字列（例：`"enable"`） | `enabled=False` | |
| 非ASCII文字列（例：`"はい"`） | `enabled=False` | |

例外を送出するケースは存在しない（AD-6参照）。

## 14. Validation Contract

- 唯一の有効化条件は、`.lower().strip()`後の文字列が厳密に`"true"`と一致することのみ。
- `"1"` / `"yes"` / `"on"`等の同義語は**サポートしない**。既存19箇所の`*_ENABLED`系Configurationがいずれも`"true"`の単一リテラルのみを許容しており、同義語を追加すると本Foundationだけが独自規約を持つことになるため。
- 大文字/小文字は区別しない（`.lower()`適用）。前後空白は無視する（`.strip()`適用、`ai_improvement_config.py`・`analytics_config.py`等の新しめのConfigurationと同じ規約）。
- 非ASCII値・ロケール依存の解釈は行わない（Python標準の`str.lower()`はASCII文字のみを対象とした単純な変換であり、ロケール依存の大文字小文字変換は行わない）。

## 15. Error Contract

### AD-6: 不正値の扱い

**決定：Fail Closed（不正値はOFFとして扱い、例外を送出しない）**

比較：

| | Fail Closed（採用） | Fail Fast |
|---|---|---|
| 利点 | API cost防止／安全側／既存17箇所（default OFF機能）の*_ENABLED系Configurationと一致 | 設定ミスの即時検出 |
| 欠点 | 設定ミスを黙って見逃す可能性 | 後続Runtime Wiring時に起動失敗要因になりうる |

採用理由：
1. 既存19箇所のうち17箇所（default OFF機能はすべて）が**例外なく**Fail Closed（`.lower()[.strip()] == "true"`比較のみ、非"true"はすべてFalse）である。残り2箇所（`LOG_ENABLED`・`SNS_ENABLED`）はdefault "true"の機能で`!= "false"`というFail Open方式を採るが、これは「デフォルト有効機能を明示的にOFFにできること」を優先した別ユースケースであり、本Gate（default OFF・Feature opt-in）には適用しない。本FoundationがFail Closedを採用しても、default OFF機能の規約上の一貫性は崩れない。
2. 本Releaseの目的そのものが「API cost防止」であり、不正値を例外にして起動を止めるより、安全側（OFF）に倒す方が目的に合致する。
3. Consumer-lessの段階でFail Fastにしても、実際に運用時の設定ミスを検出する機会（Runtime起動時）はまだ到来していない。

したがって、本Foundationは例外型・固定messageを**持たない**。`from_env()`はどのような文字列に対しても例外を送出せず、常に`ImageGenerationConfig`インスタンスを返す。

## 16. Security Contract

```text
SEC-C-1: OPENAI_API_KEYを読み取らない（コード内に文字列 "OPENAI_API_KEY" が
         出現しない）
SEC-C-2: OPENAI_API_KEYを保持しない（instance stateにapi_key相当のfieldを
         持たない）
SEC-C-3: API keyをexception messageへ含めない（そもそも例外を送出しない、
         15章）
SEC-C-4: environment全体をreprしない（os.environをそのまま出力する処理を
         持たない）
SEC-C-5: os.environをログ出力しない（14章 Logging Contract参照）
SEC-C-6: enabled: bool以外をinstance stateへ保持しない（元のenvironment
         文字列rawは変数として一時利用するのみで、instance属性として
         保持しない）
SEC-C-7: secretをtest fixtureへ直書きしない（本Foundationの環境変数は
         secretではないbool値のみであり、後続E2E実装でもsecret相当の
         値は使用しない）
SEC-C-8: OpenAI APIを呼ばない（本Foundationはネットワークアクセスを
         一切行わない）
SEC-C-9: WordPress APIを呼ばない（同上）
SEC-C-10: `@dataclass(frozen=True)`の自動生成`repr()`（例：
          `ImageGenerationConfig(enabled=True)`）は`enabled: bool`の値
          のみを含み、secretを含まない。フィールドがenabledの1つのみ
          （AD-10）であるため、自動reprによる情報漏洩は構造的に発生し
          得ない。
```

## 17. Logging Contract

**決定：Configuration parsing時にloggingを一切追加しない（副作用なし・loggingなし・printなし）。**

理由：
- 本FoundationはConsumer-less Foundationであり、実行されるのはE2E内のみである。
- `PublishingConfig._parse_status`のようにWARNING printを行う先例も存在するが、それは「不正値をdraftへフォールバックする」という運用上重要な通知であるのに対し、本Foundationは「無効/未設定」を区別しないFail Closed設計（15章）であるため、print対象となる「不正値」という概念自体を持たない。
- 将来、Composition Root／Runtime Wiring Foundationが本Configurationを消費する段階で、Gate ON/OFFのログ出力が必要であれば、そのFoundation側の責務として追加する（本Foundationの責務としない）。

## 18. Dependency Direction

```text
（将来）Composition Root／Runtime Consumer
    ↓
image_generation_config.ImageGenerationConfig
    ↓
Python標準ライブラリ（os, dataclasses）のみ
```

禁止（Reverse Dependency）：

本章では概念図として依存方向のみを示す。禁止対象の正式な列挙（R-1〜R-13、
13対象）は21章のみに存在し、本章では重複した個別列挙を行わない。v6.14の
CR14-S-1（21章・22章間のGuard対象数の差異）と同種の章間不整合を、本文書
自身の18章・21章間で再発させないための措置である（Architecture Review
AR18-M-1で修正。修正前は本章に11項目の簡略リストが存在し、21章の13対象
（特に`src/generated_image_wordpress_media/`）と数・対象が一致していな
かった）。本Foundationが依存してはならない既存Runtime／機能packageの
範囲は、main.pyからscripts/まで21章R-1〜R-13がすべてを網羅する。

## 19. Runtime Zero Diff Contract

本Release単独では、次のいずれも変更しない（Architecture Review AR19-m-6で修正：旧「16章 Zero Diff Scope」という誤ったChapter参照を削除。§16はSecurity Contractであり、Zero Diff Scopeは本章自身が定義する）。

```text
main.py
src/image_resolver.py
src/outputs/base.py
src/outputs/manager.py
src/outputs/wordpress_output.py
src/ai_image_generation/
src/openai_image_generation/
src/wordpress_media/
src/generated_image_wordpress_media/
src/article_featured_media/
src/article_featured_media_orchestration/
src/retry_*/
src/pipeline/
src/workflow_engine/
src/scheduler/
scripts/
```

本Release単独でのOpenAI API呼び出し数：**0**（構造的に保証。`image_generation_config`パッケージは`openai`パッケージをimportしない）
本Release単独でのWordPress API呼び出し数：**0**（同様に`requests`等のHTTPクライアントをimportしない）

## 20. Consumer-less Contract

### AD-9: Consumer-less Contract

```text
main.pyは image_generation_config をimportしない
src/image_resolver.py は image_generation_config をimportしない
OutputManager（src/outputs/manager.py）は image_generation_config をimportしない
WordPressOutput（src/outputs/wordpress_output.py）は image_generation_config をimportしない
OpenAIImageGenerator（src/openai_image_generation/）は image_generation_config をimportしない
ArticleFeaturedMediaOrchestrator（src/article_featured_media_orchestration/）は
    image_generation_config をimportしない
GeneratedImageWordPressMediaUploader（src/generated_image_wordpress_media/）は
    image_generation_config をimportしない
WordPressMediaUploader（src/wordpress_media/）は image_generation_config をimportしない
retry_*（全retry系package。Architecture Review時点で実在17package：
    retry_alert, retry_composition, retry_engine, retry_enqueue_trigger,
    retry_history, retry_metrics, retry_monitoring, retry_notification,
    retry_notification_message, retry_queue, retry_runtime_lock,
    retry_runtime_logging, retry_runtime_loop, retry_runtime_orchestrator,
    retry_runtime_shutdown, retry_scheduler_decision, retry_scheduler_source。
    Guard自体はglobパターンで動的に対象を捕捉するため、将来package数が
    増減しても21章R-9・24章DEP-10は追随する）は image_generation_config
    をimportしない
src/pipeline/ は image_generation_config をimportしない
src/workflow_engine/ は image_generation_config をimportしない
src/scheduler/ は image_generation_config をimportしない
scripts/ は image_generation_config をimportしない
Production RuntimeではGateを消費しない
本Release単独ではAPI call数は0
```

Guard対象外とするpackageは存在しない（本Foundationが依存しうる既存Runtime component・機能packageすべてを21章・22章のGuard対象へ含めている）。

## 21. Reverse Dependency Rules

CR14-S-1（v6.14設計書における21章・22章のGuard対象package数の**差異**、Non-Blocking Suggestion）を踏まえ、本設計書では21章と22章で**完全に同一のGuard対象リスト**を使用する。以下がその正式なリスト（13対象）である。

```text
R-1:  main.py
R-2:  src/image_resolver.py
R-3:  src/outputs/manager.py（OutputManager）
R-4:  src/outputs/wordpress_output.py（WordPressOutput）
R-5:  src/openai_image_generation/（OpenAIImageGenerator）
R-6:  src/article_featured_media_orchestration/（ArticleFeaturedMediaOrchestrator）
R-7:  src/generated_image_wordpress_media/（GeneratedImageWordPressMediaUploader）
R-8:  src/wordpress_media/（WordPressMediaUploader）
R-9:  src/retry_*/（全retry系package、ディレクトリ数は実装時にglobで動的取得。
      v6.14と同じ「vacuous pass防止」方式を踏襲する）
R-10: src/pipeline/
R-11: src/workflow_engine/
R-12: src/scheduler/
R-13: scripts/
```

追加で、本Foundation自身の出力方向のGuardとして：

```text
R-OUT-1: image_generation_config は標準ライブラリ（os, dataclasses）以外を
         importしない（openai・anthropic・requests等のいずれも禁止）
```

## 22. Architecture Guard Strategy

E2Eで機械的に検証するGuard対象は、21章のR-1〜R-13およびR-OUT-1と**完全一致**させる（数・対象いずれも差異を作らない）。検証方式は、v6.14 E2E（`tests/test_e2e_v6_14_0_article_featured_media_orchestration_foundation.py`のRUNTIME-1節）と同じ、AST解析によるimport検出を踏襲する。

```text
方式：
    1. 対象ファイル／ディレクトリの存在確認（vacuous pass防止）
    2. Python ASTでimport文を解析し、"image_generation_config" への
       importが存在しないことを確認
    3. 念のため、文字列 "ImageGenerationConfig" が対象ファイルへ
       出現しないことも確認（import以外の手段での混入を防止）
```

## 23. E2E Test Strategy

新規E2Eファイル候補：`tests/test_e2e_v6_15_0_image_generation_configuration_gate.py`（Production Implementationフェーズで作成、本Architecture Designでは未作成）。

Environment変数の隔離・復元は、既存precedent（`tests/test_e2e_v1_12_0_search_console_foundation.py`・`tests/test_e2e_v1_13_0_google_analytics_foundation.py`・`tests/test_e2e_v1_16_0_ai_rewrite_foundation.py`等）と同じ、`os.environ["KEY"] = "value"`による設定と`os.environ.pop("KEY", None)`による復元の直接操作方式を踏襲する（pytest fixture等の新しい依存は追加しない、AD-12と同じく既存規約準拠を優先）。

Scenario区分：

```text
Configuration Contract（CFG）：environment variable値ごとのparsing結果
Public API（API）：import surface・__all__・field形状
Immutability（IMM）：frozen・state非共有
Dependency Guard（DEP）：21章R-1〜R-13・R-OUT-1のAST Guard
Runtime Zero Diff（RTZ）：API非呼び出し・副作用なし
Security（SEC）：secret非保持・非露出
.env.example（ENV）：Production Implementationフェーズで.env.example自体を
    更新した後に検証するScenario（本Architecture Design時点では対象ファイル
    未変更のため、Scenario定義のみ行う）
```

## 24. Test Inventory

Scenario数はArchitecture Design時点で確定できる（24.1節、54 Scenario）。Assertion実測数は、v6.14の先例（Scenario数34を設計時に確定、Assertion実測217/217はProduction Implementation完了後に確定）と同様に、本Releaseでも**Production Implementation完了後のE2E実行結果をもって確定する**方針とする（推測値は記載しない）。R-9（retry_*）はディレクトリ数に応じた動的Assertion数を持つため、Scenario単位では1件として数えるが、実際のAssertion数は実装時のrepository状態に依存する。

### 24.1 Scenario一覧（54 Scenario）

**Configuration Contract（CFG、20 Scenario）**
```text
CFG-1  未設定時 → enabled=False
CFG-2  空文字 → enabled=False
CFG-3  空白のみ → enabled=False
CFG-4  "true" → enabled=True
CFG-5  "TRUE" → enabled=True
CFG-6  "True" → enabled=True
CFG-7  前後空白付き"  true  " → enabled=True
CFG-8  "false" → enabled=False
CFG-9  "FALSE" → enabled=False
CFG-10 "1" → enabled=False
CFG-11 "0" → enabled=False
CFG-12 "yes" → enabled=False
CFG-13 "no" → enabled=False
CFG-14 "on" → enabled=False
CFG-15 "off" → enabled=False
CFG-16 未知文字列 → enabled=False
CFG-17 非ASCII文字列 → enabled=False
CFG-18 from_env()複数回呼び出しで独立したインスタンスを返す
CFG-19 environment変更後の再読み込みで新しい値を反映する（都度読み込み）
CFG-20 いかなる入力でも例外を送出しない（Fail Closed Contract確認）
```

**Public API（API、6 Scenario）**
```text
API-1 package rootから ImageGenerationConfig をimportできる
API-2 __all__ に ImageGenerationConfig のみが含まれる
API-3 private helperがpackage rootからimportできない
API-4 ImageGenerationConfig が enabled フィールドを持つ
API-5 enabled フィールドの型が bool である
API-6 from_env が classmethod として呼び出せる
```

**Immutability（IMM、3 Scenario）**
```text
IMM-1 frozen=True により enabled再代入が FrozenInstanceError になる
IMM-2 2つの from_env() 呼び出し結果のinstance間でstateが共有されない
IMM-3 instanceが enabled 以外のmutable stateを保持しない
```

**Dependency Guard（DEP、14 Scenario、21章R-1〜R-13・R-OUT-1に対応）**
```text
DEP-1  image_generation_config が標準ライブラリ以外をimportしない（R-OUT-1）
DEP-2  main.py が image_generation_config をimportしない（R-1）
DEP-3  image_resolver.py が image_generation_config をimportしない（R-2）
DEP-4  OutputManager が image_generation_config をimportしない（R-3）
DEP-5  WordPressOutput が image_generation_config をimportしない（R-4）
DEP-6  OpenAIImageGenerator が image_generation_config をimportしない（R-5）
DEP-7  ArticleFeaturedMediaOrchestrator が image_generation_config を
       importしない（R-6）
DEP-8  GeneratedImageWordPressMediaUploader が image_generation_config を
       importしない（R-7）
DEP-9  WordPressMediaUploader が image_generation_config をimportしない（R-8）
DEP-10 retry_* 配下が image_generation_config をimportしない（R-9、
       vacuous pass防止のためディレクトリ数≥1を確認）
DEP-11 pipeline 配下が image_generation_config をimportしない（R-10）
DEP-12 workflow_engine 配下が image_generation_config をimportしない（R-11）
DEP-13 scheduler 配下が image_generation_config をimportしない（R-12）
DEP-14 scripts 配下が image_generation_config をimportしない（R-13）
```

**Runtime Zero Diff（RTZ、3 Scenario）**
```text
RTZ-1 openai パッケージへのimportがE2E実行中に一切発生しない
RTZ-2 requests等HTTPクライアントへのimportがE2E実行中に一切発生しない
RTZ-3 import・from_env()実行のみでファイルシステムへの書き込みが発生しない
```

**Security（SEC、5 Scenario）**
```text
SEC-1 "OPENAI_API_KEY" という文字列がコード内に出現しない
SEC-2 enabled 以外のfieldをinstance stateとして保持しない
SEC-3 repr(instance) に環境変数の生文字列が含まれない
SEC-4 例外発生経路が存在しない（15章 Fail Closed Contractの構造的確認）
SEC-5 test fixture内にsecret実値を直書きしていない
```

**`.env.example`（ENV、3 Scenario、Production Implementationフェーズで.env.example更新後に検証）**
```text
ENV-1 正式なGate環境変数名（AI_IMAGE_GENERATION_ENABLED）が.env.exampleに記載される
ENV-2 default OFFであることがコメントから理解できる
ENV-3 placeholderがsecret実値に見えない
```

合計：20 + 6 + 3 + 14 + 3 + 5 + 3 = **54 Scenario**

### 24.2 New E2E実績（Production Implementation・Code Review完了後の実測）

```text
file path：tests/test_e2e_v6_15_0_image_generation_configuration_gate.py
Scenario：54（24.1節と完全一致、欠落・重複・水増しなし）
Assertion：94（実測。Code Review初回実装時は95だったが、設計書24.1節に
    存在しない"CFG-9b"という余剰Scenarioを削除したCode Review Finding
    CR15-m-1の対応により94へ変化。Assertion数はresults_logへの実行時
    追記件数の実測であり、手動カウンタではないため乖離しない）
PASS：94／FAIL：0／Warning：0／終了コード：0
実行日：2026-07-20（Code Review内での最終再実行）
```

内訳（Scenario区分ごとの実測Assertion数）：

| 区分 | Scenario数 | Assertion数 |
|---|---|---|
| Configuration Contract(CFG) | 20 | 22 |
| Public API(API) | 6 | 7 |
| Immutability(IMM) | 3 | 4 |
| Dependency Guard(DEP) | 14 | 40 |
| Runtime Zero Diff(RTZ) | 3 | 6 |
| Security(SEC) | 5 | 9 |
| `.env.example`(ENV) | 3 | 6 |
| 合計 | 54 | 94 |

## 25. Regression Strategy

Formal Regressionは本Architecture Designでは実施しない（Production Implementation完了後に実施）。

**（Formal Regression工程での訂正）** 当初、対象候補をv6.10.0〜v6.14.0の画像生成Foundation chain＋既存Configuration関連E2Eという形で記載していたが、Formal Regression工程でRepository（`docs/CHANGELOG.md`・`docs/design/article_featured_media_orchestration_foundation.md` 28章）を確認した結果、`03_game_content_ai`の正式なFormal Regression運用規約は、**v1.11.0以降蓄積された累積Regression Inventoryを毎回全件個別実行する方式**であることが判明した。v6.14.0時点の正式Inventoryは17ファイル（`test_e2e_v1_11_0_save_result.py`／`test_e2e_v5_9_0_retry_runtime_loop_wiring_foundation.py`／`test_e2e_v6_0_0_*.py`〜`test_e2e_v6_14_0_*.py`の連番15ファイル）であり、本Releaseはこの17ファイルに新規v6.15.0 E2Eを加えた**18ファイル**を対象とする。既存Configuration関連E2E（`AgentConfig`・`AnalyticsConfig`等、11ファイル）は、`.env.example`を参照する既存Testが皆無であり（grep確認済み）、`image_generation_config`という新規package名とも一切重複しないため、技術的結合が存在しないと判断し、累積Inventory外として対象外とする（25.1節参照）。

## 25.1 Formal Regression実績（Formal Regression工程で反映）

```text
実行日：2026-07-20
正式対象：18ファイル（既存17ファイル＋新規v6.15.0 E2E 1ファイル）
実行方式：各ファイルを個別に`python tests/<file>`で実行（一括実行なし、結果混在なし）
実行順序：v1.11.0 → v5.9.0 → v6.0.0 → v6.1.0 → v6.2.0 → v6.3.0 → v6.4.0 →
    v6.5.0 → v6.6.0 → v6.7.0 → v6.8.0 → v6.9.0 → v6.10.0 → v6.11.0 →
    v6.12.0 → v6.13.0 → v6.14.0 → v6.15.0
baseline出典：docs/design/article_featured_media_orchestration_foundation.md
    28.1節（v6.14.0 Formal Regression実測記録、Python機械集計で確認済みの
    既存16ファイル＋v6.14.0自身の実測値）
```

Version別実測結果（すべて終了コード0、Warning 0、Traceback 0、baselineと完全一致）：

```text
v1.11.0（test_e2e_v1_11_0_save_result.py）：                    43/43 PASS
v5.9.0（test_e2e_v5_9_0_retry_runtime_loop_wiring_foundation.py）：64/64 PASS
v6.0.0（test_e2e_v6_0_0_retry_runtime_lock_foundation.py）：      43/43 PASS
v6.1.0（test_e2e_v6_1_0_retry_runtime_graceful_shutdown_foundation.py）：
                                                                  44/44 PASS
v6.2.0（test_e2e_v6_2_0_structured_loop_logging_foundation.py）： 64/64 PASS
v6.3.0（test_e2e_v6_3_0_retry_metrics_foundation.py）：         174/174 PASS
v6.4.0（test_e2e_v6_4_0_retry_monitoring_foundation.py）：      171/171 PASS
v6.5.0（test_e2e_v6_5_0_retry_alert_foundation.py）：           131/131 PASS
v6.6.0（test_e2e_v6_6_0_retry_notification_foundation.py）：    135/135 PASS
v6.7.0（test_e2e_v6_7_0_retry_notification_message_foundation.py）：
                                                                117/117 PASS
v6.8.0（test_e2e_v6_8_0_retry_notification_cli_report_wiring_foundation.py）：
                                                                197/197 PASS
v6.9.0（test_e2e_v6_9_0_wordpress_media_upload_foundation.py）：331/331 PASS
v6.10.0（test_e2e_v6_10_0_ai_image_generation_contract_foundation.py）：
                                                                  78/78 PASS
v6.11.0（test_e2e_v6_11_0_openai_image_generation_adapter_foundation.py）：
                                                                248/248 PASS
v6.12.0（test_e2e_v6_12_0_generated_image_wordpress_media_upload_wiring_foundation.py）：
                                                                  91/91 PASS
v6.13.0（test_e2e_v6_13_0_article_featured_media_binding_foundation.py）：
                                                                123/123 PASS
v6.14.0（test_e2e_v6_14_0_article_featured_media_orchestration_foundation.py）：
                                                                217/217 PASS
v6.15.0（test_e2e_v6_15_0_image_generation_configuration_gate.py、新規）：
                                                                  94/94 PASS
```

集計：

```text
既存17ファイル対象数：17
既存PASS合計：2271（v6.14.0完了時点baseline 2271/2271と完全一致、新規差分なし）
新規v6.15.0対象数：1
新規v6.15.0 PASS：94（Code Review時点の実測94/94と完全一致）
総合対象数：18
総合PASS合計：2365
FAIL：0
Warning：0（Python標準`XWarning:`形式出力・`warnings`モジュール出力いずれも
    18ファイル全ログで0件、機械的grep確認済み）
Traceback出力：0件（18ファイル全ログでgrep機械確認済み）
終了コード非0：0ファイル
実HTTP・実credential読込・実課金：いずれもなし（開始前にAI_IMAGE_GENERATION_ENABLED・
    OPENAI_API_KEY・OPENAI_IMAGE_TIMEOUT_SECONDS・ANTHROPIC_API_KEY・
    WP_SITE_URL・WP_USERNAME・WP_APP_PASSWORDがいずれも未設定であることを確認済み。
    v6.9.0・v6.11.0はrequests.post／httpxへの参照を含むが、いずれも文字列
    存在確認またはFakeオブジェクト構築のみで実通信なし）
Environment残留：なし（実行前後でAI_IMAGE_GENERATION_ENABLED等3変数が
    いずれも未設定のままであることを確認済み）
```

Formal Regression判定：**PASS**（既存17ファイル2271/2271 PASS＋新規v6.15.0 E2E
94/94 PASS＝総合2365/2365 PASS、FAIL 0、Warning 0、終了コード非0なし、対象
漏れなし、重複実行なし。Code Review Suggestion CR10-S-1はNon-Blockingのまま
Formal Regression結果へ影響しない）。

既存Configuration関連E2E（`AgentConfig`等11ファイル）は、上記の理由により累積
Regression Inventory外として対象外とした。Zero Diff（`main.py`以下14対象）は
`git diff --name-only`で無変更を確認済み。`__pycache__`等の生成物は
`.gitignore`対象であり、Git管理・変更ファイル一覧に影響しない。

## 26. Compatibility

- 既存Public API（`ai_image_generation`〜`article_featured_media_orchestration`の5 Foundation）への変更は一切ない。
- 既存環境変数（`.env.example`記載の全変数）の意味・default値への変更は一切ない。
- 新規環境変数`AI_IMAGE_GENERATION_ENABLED`は、未設定時に既存Runtime挙動（画像生成なし）と完全に一致するため、既存運用環境への後方互換性は保たれる。

## 27. Migration

Migration作業は不要。新規package追加のみであり、既存データ・既存設定ファイルの変換は発生しない。

## 28. Operational Considerations

- 本Release単独では運用手順の変更はない（Consumer-less、Runtime未接続のため）。
- `.env.example`への追記（Production Implementationフェーズ）以降、運用者が任意で`AI_IMAGE_GENERATION_ENABLED=true`を設定できるようになるが、本Release単独ではこの値を消費するConsumerが存在しないため、設定しても挙動に変化はない。

## 29. API Cost Safety

- 本Foundationは`openai`パッケージを一切importせず、`OpenAIImageGenerator`も生成しない（19章・20章）。
- 本Release完了時点でも、`main.py`実行によるOpenAI Images API呼び出し回数は既存と同じ**0回のまま**である（Runtime未接続のため）。
- 本Foundationが将来Consumerに消費されるようになった段階（後続Release）で初めて、Gate ONの場合にAPI呼び出しが発生しうる状態になる。その段階のAPI cost制御は、後続Releaseの責務とする。

## 30. Risks

```text
RISK-1: Gate名（AI_IMAGE_GENERATION_ENABLED）が将来のRuntime Wiring責務と
        合わない可能性
        軽減策：13章AD-1で"AI Image Generation"という既存確立済み用語に
        揃えており、Runtime Wiringの対象範囲（AIImageGenerator Protocol
        全体）と一致させている

RISK-2: 設定値解析規則が既存Configuration patternと不整合になる可能性
        軽減策：既存19箇所の*_ENABLED実装を悉皆調査し、default OFF機能
        17箇所のFail Closed方式と完全一致させた（3章・14章・15章）

RISK-3: 不正値を黙ってOFFにすることで設定ミスを見逃す可能性
        軽減策：Fail Closedは意図的な採用であり（15章AD-6）、既存規約との
        一貫性・API cost防止を優先した。運用者向けの`.env.example`コメント
        （Production Implementationフェーズ）で正しい値を明記することで
        軽減する

RISK-4: OPENAI_API_KEYの存在とGate有効状態の責務が混同される可能性
        軽減策：13章・16章でGate componentがOPENAI_API_KEYを一切読み取ら
        ないことを構造的に保証（SEC-C-1・SEC-C-2）

RISK-5: Configuration Foundationの段階でRuntime branchingまで実装し、
        Scopeが膨張する可能性
        軽減策：7.2節Out of Scope・19章Runtime Zero Diff Contractで
        明示的に禁止

RISK-6: 専用Configuration objectが過剰設計になる可能性
        軽減策：フィールドをenabled: boolのみに限定し、model/size/quality/
        timeout等の将来使うかもしれないフィールドを先行追加しない
        （AD-10・AD-2参照）

RISK-7: 既存のAI_AGENT_ENABLED等との命名・解析規約が不統一になる可能性
        軽減策：14章で命名・解析規約の完全一致を確認済み
```

Runtime Wiring・Retry・Idempotencyに関するRiskは、本Release内で解決するRiskとして扱わない（後続ReleaseのRiskとする、NG-6参照）。

## 31. Alternatives Considered

### AD-2: Public API形状

| 案 | 内容 | 評価 | 採否 |
|---|---|---|---|
| 案A | `def is_image_generation_enabled() -> bool` | 既存19箇所の`*_ENABLED`系Configurationはいずれも`@dataclass` + `from_env()`パターンであり、bare functionの先例が repository内に存在しない。将来フィールド追加（本Releaseでは行わないが）の余地もない | 不採用 |
| 案B（採用） | `@dataclass(frozen=True) class ImageGenerationConfig: enabled: bool` + `from_env()` | 既存19/19のConfig class命名規約（`<Feature>Config`）と完全一致。testabilityも高い（instance生成のみで検証可能） | **採用** |
| 案C | `PublishingConfig`等の既存Configuration componentへfield追加 | 意味的に無関係な既存機能（投稿ステータス等）へ混入することになり、責務分離に反する。また対象となりうる既存Foundation（`ai_image_generation`等）はZero Diff対象であり変更不可 | 不採用 |

### AD-10: Configuration objectの不変性

`@dataclass(frozen=True)`を採用（`slots=True`は不採用：repository内の`frozen=True`使用箇所（`GeneratedImage`・`MediaUploadResult`・retry_engine配下の各種Result/Record等、20箇所以上）はいずれも`slots=True`を併用していないため、既存規約との一貫性を優先）。フィールドは`enabled: bool`のみとし、`model`・`size`・`quality`・`timeout`等は将来使うかもしれないという理由だけでは追加しない（それらは`OpenAIImageGenerator`が既に管理している責務であり、AD-7・AD-8で明確に分離する）。`repr`・`eq`・`hash`は`@dataclass(frozen=True)`のデフォルト自動生成のまま変更しない。Subclassingは想定しない。Request単位のstateは保持しない（field自体が`enabled`のみであるため構造的に保証される）。

### AD-11: Environment読み取りタイミング

module import時の環境変数読み取りは採用しない。既存19箇所すべてが`from_env()`という明示的なclassmethod呼び出し時に読み込む方式であり、本Foundationもこれに従う。Constructorへboolを渡す方式（`ImageGenerationConfig(enabled=True)`）はテスト・将来のComposition Rootからの直接構築のために引き続き利用可能とする（`from_env()`はその薄いラッパーとして位置づける）。

### AD-12: Environment accessの抽象化

`os.getenv(...)`を採用する（既存19箇所のうち8箇所が`os.getenv`、11箇所が`os.environ.get`を使用しており、両者は機能的に同一。本Foundationは`os.getenv`を採用し新しい表記ゆれを増やさない）。Environment mapping注入（`Mapping[str, str] | None = None`のようなDI）は、repository内のどの既存Configurationにも先例がなく、過剰抽象化と判断し不採用とする。E2Eでのtestabilityは、Python標準の`os.environ`一時操作（設定→実行→復元）で十分に確保できる（既存Configuration関連E2Eと同じ手法を踏襲する）。

## 32. Architecture Decisions（AD一覧）

```text
AD-1  Environment Variable名：AI_IMAGE_GENERATION_ENABLED
      理由：ai_image_generation package・v6.10.0正式名称との一貫性。
      provider非依存を維持。

AD-2  Public API形状：専用Configuration object（案B）
      理由：既存19/19のConfig class命名規約と完全一致。

AD-3  Default値：未設定時 = OFF（False）
      理由：既存Runtime挙動維持・無条件API呼び出し防止・API cost防止。

AD-4  有効値：リテラル"true"のみ（大文字小文字を区別しない、前後空白を
      無視する）。"1"/"yes"/"on"等の同義語は非サポート
      理由：既存19箇所中17箇所（default OFF機能はすべて）の
      Configuration規約と一致（3章）。

AD-5  空文字：未設定相当としてOFF
      理由：既存*_ENABLED系Configurationのdefault fallback方式と一致。
      例外にする先例が repository内に存在しない。

AD-6  不正値：Fail Closed（OFFとして扱い、例外を送出しない）
      理由：既存default OFF機能17/17が例外なくFail Closed（3章）。
      API cost防止という本Releaseの目的とも合致。

AD-7  OPENAI_API_KEYとの関係：本Foundationは一切読み取らない・保持しない。
      Validation責務はOpenAIImageGenerator.from_env()に維持する
      理由：責務分離。Gate ONでもOFFでもOPENAI_API_KEYの状態に
      無関係に動作する。

AD-8  OPENAI_IMAGE_TIMEOUT_SECONDSとの関係：本Foundationは扱わない。
      OpenAIImageGenerator.from_env()の責務として維持する
      理由：有効/無効とAdapter timeoutは別責務。.env.exampleへの記載は
      Production Implementationフェーズで両方行うが、Configuration
      objectとしては統合しない。

AD-9  Consumer-less Contract：main.py以下13Reverse Dependency対象
      （21章R-1〜R-13）いずれからも未参照。Production RuntimeでGateを
      消費しない。本Release単独でAPI call数は0
      理由：Runtime Wiring・Composition Rootの最終形を先取りしない。

AD-10 Configuration objectの不変性：@dataclass(frozen=True)、
      slots=Trueは不採用、フィールドはenabledのみ
      理由：既存frozen=True規約（slots未使用）との一貫性。過剰設計回避。

AD-11 Environment読み取りタイミング：from_env()呼び出し時（import時では
      ない）
      理由：既存19/19の規約と一致。

AD-12 Environment accessの抽象化：os.getenv(...)を直接使用。Mapping注入
      は不採用
      理由：既存規約に先例なし。過剰抽象化を回避。

AD-13 Public import surface：package名 image_generation_config、
      module名 image_generation_config.py、class名 ImageGenerationConfig、
      __all__ = ["ImageGenerationConfig"]
      理由：class名は既存19/19の<Feature>Config規約に従う。package名は
      class名と直接対応させ、余分な表記ゆれを避ける。

AD-14 .env.exampleのScope：案A（画像生成関連のみ追加：Gate変数・
      OPENAI_API_KEY・OPENAI_IMAGE_TIMEOUT_SECONDS）を採用。
      AI_AGENT_ENABLEDの追記はOut of Scopeとし、既知のDocumentation Gap
      として33章Open Questions／34章Known Issuesへ記録する
      理由：Scope creep回避。本Releaseの目的（画像生成API cost防止）に
      直接関係する変数のみに限定する。実装自体はProduction
      Implementationフェーズで行う（本Architecture Designでは
      .env.example自体を変更しない）。

AD-15 正式設計書ファイル名：image_generation_configuration_gate_foundation.md
      （既存Release 6.10〜6.14の`<正式名称>_foundation.md`命名規約に
      従い、正式名称"Image Generation Configuration Gate"を採用。
      package名（image_generation_config）とはやや表記が異なるが、
      Release公式名称の完全性を優先した。class名はConfig系19/19の
      規約を優先し"ImageGenerationConfig"とした（"...ConfigurationGate"
      という新規suffixは作らない）
```

## 33. Open Questions（Architecture Reviewへ持ち越す事項）

```text
OQ-1: AI_IMAGE_GENERATION_ENABLED という変数名は、将来Runtime Wiring
      Foundationが正式にConsumeする段階で変更不要か（Architecture Review
      で最終確認）

OQ-2:（Architecture Reviewで解決）package名 image_generation_config と、
      正式設計書名 image_generation_configuration_gate_foundation.md の
      表記差異は、32章AD-15の理由（class名はConfig系19箇所の命名規約を
      優先、設計書名はRelease公式名称の完全性を優先）により許容する。
      これ以上のOpen Questionとしては扱わない。

OQ-3:（Architecture Reviewで解決）AI_AGENT_ENABLED 等の.env.example
      未記載は、本Release（AD-14でOut of Scope）では扱わない。34章
      KI-1として記録済みであり、別の独立したDocumentation Gap是正
      Releaseで扱うべき事項として確定する。

OQ-4: 将来のPublish Composition Root Foundationは、本
      ImageGenerationConfig をどう消費する設計にするか（本Releaseでは
      未決定・Consumer-less）

OQ-5: Fail Closed方針（AD-6）は、将来Runtime Wiring段階でも維持すべきか、
      それとも起動時Fail Fastへ変更すべきか（本Releaseでは判断しない）
```

## 34. Known Issues

```text
KI-1: .env.exampleに OPENAI_API_KEY・OPENAI_IMAGE_TIMEOUT_SECONDS・
      AI_AGENT_ENABLED が未記載（Repository Survey既知）。本Releaseの
      Production Implementationフェーズで OPENAI_API_KEY・
      OPENAI_IMAGE_TIMEOUT_SECONDS・新規Gate変数の3件を追加するが、
      AI_AGENT_ENABLED はOut of Scopeのまま残る（AD-14）

KI-2: ArticleData（src/outputs/base.py）は型システム上immutableではない
      （@dataclass のみ、frozen=True ではない）。本Releaseとは無関係の
      既存事実だが、将来のArticleFeaturedMedia系Runtime Wiring検討時に
      再度参照される可能性があるため記録する
```

## 35. Implementation Plan（Production Implementationフェーズの予告、本Architecture Designでは未実施）

```text
Step 1: src/image_generation_config/ パッケージ作成
        （__init__.py, image_generation_config.py）
Step 2: tests/test_e2e_v6_15_0_image_generation_configuration_gate.py
        作成（24章Test Inventory、54 Scenario）
Step 3: .env.example へ「Image Generation Configuration Gate」セクション
        追加（AI_IMAGE_GENERATION_ENABLED・OPENAI_API_KEY・
        OPENAI_IMAGE_TIMEOUT_SECONDSの3変数、AD-14）
Step 4: Formal Regression実行（25章対象）
Step 5: Documentation Integration（ROADMAP.md／architecture.md／
        CHANGELOG.md、本Architecture Designでは未実施）
Step 6: Release Review
```

上記はいずれも本Architecture Design完了時点では未着手である。

### 35.1 Production Implementation実績（Production Implementation・Code Review完了後に反映）

```text
実行日：2026-07-20
新規package：src/image_generation_config/（__init__.py 15行、
    image_generation_config.py 39行、いずれも末尾改行あり）
Public API：Architecture Designからの逸脱なし（12章のPublic API仕様と
    完全一致）
.env.example：AI_IMAGE_GENERATION_ENABLED・OPENAI_API_KEY・
    OPENAI_IMAGE_TIMEOUT_SECONDSの3変数を追記（AD-14どおり）。既存行の
    変更・削除・並べ替えなし（20行追加のみ）
新規E2E：tests/test_e2e_v6_15_0_image_generation_configuration_gate.py
    （24.2節参照）
Zero Diff：main.py／image_resolver.py／outputs／ai_image_generation／
    openai_image_generation／wordpress_media／
    generated_image_wordpress_media／article_featured_media／
    article_featured_media_orchestration／retry_*／pipeline／
    workflow_engine／scheduler／scriptsのいずれもgit diffで無変更を確認
Code Review Finding：38章 Review History参照（Minor 3件検出・修正、
    Suggestion 2件、Blocking/Major 0件）
```

## 36. Review Checklist（セルフレビュー）

```text
[x] Release名とScopeが一致しているか            → 一致（7章・8章）
[x] Gate以外の責務が混入していないか            → 混入なし（7.2章 Out of Scope）
[x] Runtime Wiringが混入していないか            → 混入なし（NG-1、19章）
[x] default OFFが明確か                        → 明確（AD-3）
[x] API cost防止が成立するか                    → 成立（29章）
[x] provider固有Gateになっていないか            → なっていない（AD-1）
[x] OPENAI_API_KEY責務と混同していないか        → 混同なし（AD-7、SEC-C-1/2）
[x] timeout責務と混同していないか               → 混同なし（AD-8）
[x] 既存bool parsing規約と整合しているか        → 整合（AD-4、14章）
[x] 不正値Contractが明確か                      → 明確（AD-6、15章）
[x] Public APIが最小か                          → 最小（enabled: boolのみ、AD-10）
[x] Configuration objectが過剰設計でないか      → 過剰設計でない（AD-10、RISK-6）
[x] Consumer-lessが保証されるか                 → 保証される（AD-9、20章）
[x] Reverse Dependency Guardが網羅的か          → 網羅的（21章R-1〜R-13、R-OUT-1）
[x] Guard対象外のpackage理由が明記されているか  → 対象外なし（20章末尾）
[x] Zero Diff Scopeが明確か                     → 明確（19章）
[x] secret非露出が保証されるか                  → 保証される（16章）
[x] E2Eだけで外部APIを呼ばず検証できるか        → 可能（23章・24章 RTZ）
[x] 後続Runtime Wiringで再利用できるか          → 可能（AD-2、12章 Public API）
[x] 21章と22章のGuard対象リストが一致しているか → 一致（CR14-S-1の再発防止、
                                                    21章・22章参照）
```

## 37. Definition of Done（本Architecture Designフェーズ）

```text
[x] Git開始状態を確認した
[x] 既存Configuration pattern（19箇所）を悉皆調査した
[x] Release名とScopeを確定提案した
[x] Environment Variable名を決定した（AD-1）
[x] Public APIを決定した（AD-2、12章）
[x] default OFF Contractを決定した（AD-3）
[x] bool parsing Contractを決定した（AD-4、14章）
[x] 空文字Contractを決定した（AD-5）
[x] 不正値Contractを決定した（AD-6、15章）
[x] OPENAI_API_KEYとの責務分離を決定した（AD-7）
[x] timeoutとの責務分離を決定した（AD-8）
[x] Consumer-less Contractを決定した（AD-9、20章）
[x] Runtime Zero Diff Contractを決定した（19章）
[x] Reverse Dependency Guardを決定した（21章・22章、一致確認済み）
[x] E2E Test Inventoryを設計した（24章、54 Scenario）
[x] 正式設計書を作成した（本文書）
[x] Architecture DesignをCompletedにした（0章）
[x] Architecture Review 1を実施し、Approvedにした（0章・38章。Architecture
    Design完了時点ではPendingだったが、本文書内で実施したArchitecture
    Reviewにより更新済み）
[x] Production Code変更（35.1節。Production Implementation完了）
[x] Test作成（24.2節。新規E2E 54 Scenario、Code Review完了）
[x] .env.example変更（35.1節。AD-14どおり3変数追記、Code Review完了）
[x] Formal Regression実施（25.1節。既存17ファイル2271/2271 PASS＋新規
    v6.15.0 E2E 94/94 PASS＝総合2365/2365 PASS、FAIL 0、Warning 0）
[x] Documentation Integration実施（docs/ROADMAP.md／docs/architecture.md／
    docs/CHANGELOG.mdへv6.15.0を統合）
[x] Release Review実施（Approved、Blocking Issueなし、Minor 2件はいずれも
    文書表記の是正のみで解消、Suggestion CR10-S-1はNon-Blockingのまま維持。
    Release 6.15として完了）
```

（本Definition of Doneは元々Architecture Designフェーズのみを対象としていたが、Production Implementation・新規E2E作成・Code Review・Formal Regression・Documentation Integration・Release Reviewが本文書内で完了したため、実績を反映した。本文書に関するすべての工程が完了している。）

## 38. Review History

```text
2026-07-20  Claude Code  Architecture Designドラフト作成（本文書、初版）
            Architecture Review：未実施
            Production Implementation：未実施
            Code Review：未実施
            Formal Regression：未実施
            Documentation Integration：未実施
            Release Review：未実施

2026-07-20  Claude Code  Architecture Review 1実施
            結果：Approved
            主要確認内容：19箇所の*_ENABLED bool parsing規約の再集計、
                os.getenv/os.environ.get使用比率の再集計、18章・21章間の
                Reverse Dependency対象一致確認、retry_*実在数確認、
                dataclass自動repr安全性確認、Open Questions内の既解決
                項目確認
            検出Finding：Blocking 0・Major 1（AR18-M-1：18章と21章の
                Reverse Dependency対象リストの数・対象不一致、
                generated_image_wordpress_mediaが18章に欠落）・
                Minor 5（AR3-m-1：19/19主張の不正確性〔実際17/19、
                LOG_ENABLED・SNS_ENABLEDはFail Open〕・AR12-m-2：
                os.getenv/os.environ.get比率の記載が実際と逆・
                AR13-m-3：dataclass自動repr安全性の未記載・
                AR33-m-4：OQ-2がAD-15で既に解決済み・AR33-m-5：
                OQ-3がKI-1と重複）・Suggestion 2（AR20-S-1：
                retry_*例示リストが実在17件中11件のみ・AR23-S-2：
                E2E環境変数隔離機構の既存precedent未引用）
            修正：Finding全件を本文書内の該当章で修正（0章・3章・5章・
                9章・14章・15章・16章・18章・20章・23章・30章・31章・
                32章・33章）
            再Review：Blocking 0・Major 0・Minor 0・Suggestion 0
                （全件修正確認済み）、Blocking Issueなし
            Production Implementation開始可否：Approved to Start

2026-07-20  Claude Code  Production Implementation・新規E2E作成実施
            （35.1節・24.2節参照）
            新規package：src/image_generation_config/（Architecture
                Designからの逸脱なし）
            .env.example：AD-14どおり3変数追記
            新規E2E：54 Scenario、初回実行95 Assertion全PASS
            Code Review開始可否：Ready for Code Review

2026-07-20  Claude Code  Code Review 1実施
            結果：Approved with Suggestions
            主要確認内容：Production Codeの最小性、Public API・
                Environment Variable Contract・型Contract・
                Immutabilityの実装一致、docstring Security Guard
                （SEC-C-1文字列非出現Contract）の妥当性、SEC-5 secret
                scannerの偽陽性／過剰依存評価、CFG-20長大文字列
                Scenarioの妥当性、Environment隔離・復元の必要性再検証、
                Dependency Guard 14 Scenarioの正確性、Output Direction
                Guardの許可対象一致、Runtime Zero Diff Guardの保証範囲、
                .env.example Scope整合、54 Scenario IDの設計書照合、
                Assertion集計方式の正確性、Windows互換性
            検出Finding：Blocking 0・Major 0・Minor 3
                （CR9-m-1：OPENAI_API_KEY／OPENAI_IMAGE_TIMEOUT_SECONDSの
                不要な環境変数保存・復元を実際に操作するAI_IMAGE_GENERATION_
                ENABLEDのみへ簡素化／CR14-m-1：ENV-2の"true"文字列検索が
                既存無関係箇所（LOG_ENABLED=true等）で自明にPASSしていた
                ため、新規セクション固有の文言"true以外の値"へ変更／
                CR15-m-1：設計書24.1節に存在しない"CFG-9b"という余剰
                Scenarioを削除し、Scenario ID・Assertion数を設計書と
                完全一致させた）・Suggestion 2（CR10-S-1：動的import
                検出はAST Guard対象外、v6.14 precedentと同じ既知の制約
                として維持しframework新設は見送り／CR19-S-1：本文書への
                実績反映、本Code Review内で実施）
            Architecture Decision変更：なし（Public API・Environment
                Variable Contract・Scopeいずれも未変更、Test実装のみ
                修正）
            修正：Minor 3件を許可範囲内（Production Code docstring・
                新規E2E）で修正し、新規E2E再実行で94/94 PASS再確認
            再Review：Blocking 0・Major 0・Minor 0（全件修正確認済み）・
                Suggestion 1（CR10-S-1、Non-Blockingのまま維持）
            Formal Regression開始可否：Approved to Start

2026-07-20  Claude Code  Formal Regression実施
            結果：Passed
            対象範囲の訂正：当初25章はv6.10.0〜v6.14.0＋既存Configuration
                関連E2Eという狭いScopeを想定していたが、
                `docs/design/article_featured_media_orchestration_foundation.md`
                28章・`docs/CHANGELOG.md`を確認した結果、
                03_game_content_aiの正式なFormal Regression運用規約は
                v1.11.0以降蓄積された累積Regression Inventory
                （v6.14.0時点17ファイル）を毎回全件個別実行する方式で
                あることが判明。ユーザー確認のうえ、累積Inventory方式
                （既存17ファイル＋新規v6.15.0 E2E＝計18ファイル）を正式
                採用し、25章を修正した
            対象：18ファイル（25.1節参照）。既存Configuration関連E2E
                （AgentConfig等11ファイル）は、.env.exampleを参照する
                既存Testが皆無であり、image_generation_configという
                package名とも重複しないため、技術的結合なしと判断し
                対象外とした
            実測：既存17ファイル2271/2271 PASS（v6.14.0完了時点baselineと
                完全一致、新規差分なし）＋新規v6.15.0 E2E 94/94 PASS
                （Code Review時点実測と完全一致）＝総合2365/2365 PASS
            FAIL：0、Warning：0、Traceback：0、終了コード非0：0ファイル
            外部API：実HTTP・実credential読込・実課金いずれもなし
                （AI_IMAGE_GENERATION_ENABLED・OPENAI_API_KEY・
                OPENAI_IMAGE_TIMEOUT_SECONDS・ANTHROPIC_API_KEY・
                WP_SITE_URL・WP_USERNAME・WP_APP_PASSWORDがいずれも
                未設定であることを実行前に確認。requests.post／httpxへの
                参照を含む2ファイル（v6.9.0・v6.11.0）はいずれも文字列
                存在確認・Fakeオブジェクト構築のみで実通信なしと確認済み）
            Environment：AI_IMAGE_GENERATION_ENABLED等3変数が実行前後で
                いずれも未設定のまま、残留なし
            Zero Diff：main.py以下14対象、`git diff --name-only`で
                無変更を確認
            Code Review Suggestion CR10-S-1：Formal Regression結果へ
                影響なし、Non-Blockingのまま維持
            Documentation Integration開始可否：Approved to Start

2026-07-20  Claude Code  Documentation Integration実施
            対象：docs/ROADMAP.md／docs/architecture.md／docs/CHANGELOG.md
                （正式設計書自身への実績反映を含む）
            ROADMAP.md：v6.14.0完了エントリ直後に「Image Generation
                Configuration Gate」を新規追加（チェックボックスは`[ ]`の
                まま維持。Release Review未実施のため「完了」とは記載せず、
                実装・Review・Test実績のみを記載）。既存Future Candidate
                「Image Generation Configuration Gate（次候補）」を削除。
                「Article Featured Media Runtime Wiring」の説明へ、本
                Gateにより前提の1つが充足されたが他の前提（Prompt
                Construction・Filename Policy・Composition Root等）は
                引き続き未充足である旨を追記
            architecture.md：末尾へ「Image Generation Configuration Gate
                Foundation層」節を新設（Purpose／Package Boundary／
                Public API／Environment Variable Contract／依存関係／
                Consumer-less Contract／Runtime Zero Diff Contract／
                Security Contract／Backward Compatibility／Out of
                Scope／Test Review・Code Review・Regression実績／Future
                Extension）。v6.14.0節のFuture Extension一覧から本Gateを
                除外し、実装済みである旨を追記
            CHANGELOG.md：[v6.14.0]の直前に[v6.15.0] Entryを新規追加。
                Release状態が`In Progress`でRelease Review未実施である
                ことをEntry冒頭のblockquoteで明記
            反映内容：Release 6.15実績（Version・正式名称・分類）、Public
                API（`ImageGenerationConfig`、`enabled: bool`のみ）、
                Environment Variable Contract（`AI_IMAGE_GENERATION_ENABLED`、
                固定message等は該当なし）、Architecture Contract
                （Configuration-First、Fail Closed、Consumer-less、
                Runtime Zero Diff）、新規E2E実績（54 Scenario、94/94
                PASS）、Formal Regression実績（累積Inventory18ファイル、
                2365/2365 PASS）、Architecture Review結果（Approved、
                Blocking Issueなし）、Code Review結果（Approved with
                Suggestions、CR10-S-1をNon-Blockingのまま3文書・正式
                設計書間で一貫して記載）、Consumer-less状態（main.py
                以下13対象いずれも未接続である旨）、Future Candidates
                （Image Generation Configuration Gateを完了側へ移動、他は
                未着手のまま維持）
            Historical Record変更：なし（Release 6.14以前のCHANGELOG
                Entry・ROADMAP完了記録・architecture.md既存節のいずれも
                変更していない）
            誤記チェック：「Release Review Approved」「Release
                Completed」「v6.15.0完了済み」「Production Ready」の
                いずれも4文書に記載していないことを全文検索で確認
            数値整合確認：「54」「94」「18」「2271」「2365」がROADMAP.md・
                architecture.md・CHANGELOG.md・正式設計書間で一致する
                ことを確認。古い「95」Assertion表記・狭い「6ファイル」
                Regression表記のいずれも残存していないことをgrep確認
            Test再実行：なし（Production Code・.env.example・新規E2Eの
                いずれも本工程で変更していないため、Formal Regression再
                実行は不要と判断）
            Release Review開始可否：Approved to Start

2026-07-20  Claude Code  Release Review実施
            結果：Approved
            主要確認内容：期待8ファイル以外の変更有無、Production Code
                （`ImageGenerationConfig`）とPublic API・Environment
                Variable Contract報告の一致、`.env.example`差分の安全性、
                新規E2E行数差異（Code Review報告441行／Documentation
                Integration報告444行）の原因調査、新規E2E再実行による
                54 Scenario／94 Assertion／94/94 PASS／終了コード0の
                再現、Formal Regression実績（累積18ファイル、2365/2365
                PASS）の照合、4文書（正式設計書／ROADMAP.md／
                architecture.md／CHANGELOG.md）間のRelease番号・正式名称・
                Public API・Environment Variable・Scenario数・Assertion
                数・Formal Regression file数・Code Review状態・
                Suggestion・Runtime状態の整合、CR10-S-1のRelease完了への
                影響評価、Consumer-less／Runtime Zero Diff、Security
                Contract、Scope逸脱の有無
            新規E2E行数差異の結論：現在の実ファイルは444行（末尾改行あり）。
                Code Reviewで報告した「441行」は、実ファイルへの変更を
                伴わない単純な報告集計誤差と判定した（Documentation
                Integration工程で新規E2Eへの編集操作が行われていないこと、
                かつ再実行で54 Scenario／94 Assertion／94/94 PASS／
                終了コード0がFormal Regression時と完全に一致することから、
                実ファイル内容自体はCode Review完了以降変更されていないと
                判断した）
            検出Finding：Blocking 0・Major 0・Minor 2（RR-m-1：新規E2E
                行数報告誤差〔上記のとおり実ファイル変更なしと確認〕・
                RR-m-2：architecture.mdの新Component節に"18ファイル"という
                明示的合計表記がなかったため1箇所へ追記）・Suggestion 0件
                （CR10-S-1はCode Review由来の既存記録として維持）
            修正：RR-m-2をarchitecture.mdの1箇所で解消。RR-m-1は実ファイル
                修正不要（報告記録の正確化のみ）
            Formal Regression再実行：なし（Production Code・`.env.example`・
                新規E2Eのいずれも本工程で変更しておらず、既存17ファイルの
                Formal Regression結果に影響する変更がないため、累積18
                ファイル全体の再実行は不要と判断。新規v6.15 E2Eのみ1回
                再実行し、Formal Regression時の実績と完全一致することを
                確認した）
            Zero Diff確認：main.py以下14対象、`git diff --name-only`で
                無変更を確認
            外部API実接続：0（新規E2E再実行時も実HTTP・実credential読込・
                実課金いずれもなし）
            文書間整合：4文書間でRelease番号・正式名称・Public API・
                Environment Variable・Default・Scenario数（54）・
                Assertion数（94）・Formal Regression file数（18）・
                Formal Regression PASS数（2365/2365）・Code Review状態・
                CR10-S-1・Runtime未接続状態のいずれも一致することを確認
            Architecture Designからの逸脱：なし
            Release判定：Approved。Release 6.15として完了
```

---

（本文書はArchitecture Design・Architecture Review・Production Implementation・新規E2E作成・Code Review・Formal Regression・Documentation Integration・Release Reviewフェーズの成果物である。commit・pushのいずれも本工程では行っていない。）
