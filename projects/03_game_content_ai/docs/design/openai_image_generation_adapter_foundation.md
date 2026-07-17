# OpenAI Image Generation Adapter Foundation — Architecture Design（v6.11.0）

作成日：2026-07-17（Architecture Review 1・2：Changes Required→反映済み。Architecture Review 3：Approved。Test Review 1・2・3・4：Changes Requiredを受け反映済み。Test Review 5：Approved。Implementation着手時発見のIMP-DESIGN-1を受け、Architecture Review 4：Changes Required（AR4-m-1）を反映。Architecture Review 5：Approved。Focused Test Review 6：Approved。Implementation完了（新規E2E 248/248 PASS、既存Regression 1592/1592 PASS、合計1840/1840 PASS）。Code Review 1：Approved。Documentation Integration：Completed。Release Review 1：Changes Required（RR1-m-1）を受け反映。Focused Release Review 2：Approved、同日改訂）
作成者：Claude Code（Architecture Designドラフト作成・OpenAI公式仕様調査・独立Architecture Reviewerとして Architecture Review 1〜5実施・独立Test Reviewerとして Test Review 1〜6実施・実装担当者としてImplementation実施・独立Code Reviewerとして Code Review 1実施・IMP-DESIGN-1発見・指摘反映・Documentation Integration実施・独立Release ReviewerとしてRelease Review 1・2実施・RR1-m-1発見・指摘反映）／ChatGPT（未参加）／ユーザー（最終承認・未実施）
状態：**Architecture Design：Completed（Architecture Review 1・2：Changes Required→反映済み。Architecture Review 3：Approved。Implementation中発見のIMP-DESIGN-1を受けたArchitecture Review 4：Changes Required（AR4-m-1）→反映済み。Architecture Review 5：Approved）。Test Design：Completed（Test Review 1〜4：Changes Required→反映済み。Test Review 5：Approved。IMP-DESIGN-1によるTest Inventory訂正を受けたFocused Test Review 6：Approved）。Implementation：Completed（新規E2E 248/248 PASS・既存Regression 1592/1592 PASS・合計1840/1840 PASS）。Code Review：Review 1 Approved（Blocking/Major/Minor Findingsなし）。Documentation Integration：Completed。Release Review：Review 1 Changes Required（RR1-m-1→反映済み）、Review 2 Approved（Blocking/Major/Minor Findingsなし）。Release 6.11：commit・push可能**
分類：**Architecture Release**（development_workflow.md 6章・7章）

---

## 1. Document Information

| 項目 | 内容 |
|---|---|
| Release | 6.11 |
| Version | v6.11.0 |
| Release名 | OpenAI Image Generation Adapter Foundation |
| 対象プロジェクト | `projects/03_game_content_ai` |
| 前Release | v6.10.0 AI Image Generation Contract Foundation（`0b03148df4e8972a082059f4bc529305aa666808`、Release Review Approved） |
| 本文書のスコープ | Architecture Design作成、Implementation（production code・requirements.txt・E2E test）を含む。Architecture ReviewはArchitecture Review 5、Test ReviewはTest Review 6、Code ReviewはCode Review 1でそれぞれApproved。Documentation Integration（ROADMAP.md／architecture.md／CHANGELOG.md／本設計書）はCompleted。Release Review 1はRR1-m-1（Minor）によりChanges Required、反映済み。Focused Release Review 2はApproved（Blocking/Major/Minor Findingsなし）。Release 6.11はcommit・push可能 |
| AI構成 | Claude Code（Architecture Design作成・OpenAI公式仕様調査・独立Architecture Reviewerとして Architecture Review 1〜5実施・独立Test Reviewerとして Test Review 1〜6実施・実装担当者としてImplementation実施・独立Code Reviewerとして Code Review 1実施・IMP-DESIGN-1発見・指摘反映・Documentation Integration実施・独立Release ReviewerとしてRelease Review 1・2実施・RR1-m-1発見・指摘反映）／ChatGPT（未参加）／ユーザー（最終承認・未実施） |

---

## 2. Status

```text
Architecture Design：Completed
Architecture Review：
    Review 1：Changes Required（反映済み）
    Review 2：Changes Required（反映済み）
    Review 3：Approved
    Review 4：Changes Required（AR4-m-1反映済み）
    Review 5：Approved
Test Review：
    Review 1：Changes Required（反映済み）
    Review 2：Changes Required（反映済み）
    Review 3：Changes Required（反映済み）
    Review 4：Changes Required（反映済み）
    Review 5：Approved
    Review 6：Approved
Implementation：Completed
    production code：実装済み、正式設計書との監査完了（size 7値含め一致）
    requirements.txt：更新済み（openai>=2.46.0,<3.0.0）
    E2E test：実装完了（123 Scenario／163 Case／248 Assertion、248/248 PASS）
    既存Regression：1592/1592 PASS（v1.11.0、v5.9.0〜v6.10.0の正式13ファイル、
        docs/CHANGELOG.md v6.10.0 Testedセクションに基づく対象特定）
    合計：1840/1840 PASS
Code Review：
    Review 1：Approved
Documentation Integration：Completed
Release Review：
    Review 1：Changes Required（RR1-m-1反映済み）
    Review 2：Approved（Blocking/Major/Minor Findingsなし）
```

---

## 3. Background

Release 6.10（`docs/design/ai_image_generation_contract_foundation.md`）で、外部I/Oを一切持たないProvider非依存の画像生成Contract（`GeneratedImage` / `AIImageGenerator` Protocol）が確定・実装完了した（Release Review Approved、`0b03148`）。

```python
class AIImageGenerator(Protocol):
    def generate(self, prompt: str) -> GeneratedImage:
        ...

@dataclass(frozen=True)
class GeneratedImage:
    image_bytes: bytes = field(repr=False)
    mime_type: str
```

しかし、v6.10.0時点でこのProtocolを実装する具象Generatorはプロジェクト内に1つも存在しない（v6.10設計書21章 Out of Scope・29章 Future Extensionsで明示的に対象外とされている）。`docs/ROADMAP.md`は次候補として次を明示している。

```text
- [ ] OpenAI Image Generation Adapter Foundation（次候補・未着手）：v6.10.0の
  AIImageGenerator Protocolを実装する最初の具象Provider。
- [ ] Generated Image → WordPress Media Upload Wiring（次候補・未着手）
- [ ] Article → featured_media Wiring（次候補・未着手）
```

また、Release 6.9（`docs/design/wordpress_media_upload_foundation.md`）で、画像bytesをWordPress Media Libraryへアップロードする`WordPressMediaUploader.upload(image_bytes, filename, mime_type)`が既にConsumer-less Foundationとして完成しているが、その`image_bytes`を実際に生成する手段は依然として存在しない。

## 4. Current Architecture（現状の確認）

Architecture Design着手前に、次の既存実装を実読して確認した。

- **`src/ai_image_generation/`**（v6.10.0、無改修方針）：`__init__.py`（`GeneratedImage` / `AIImageGenerator`の2つのみexport）、`generated_image.py`（frozen dataclass、`type(value) is bytes`による厳密型検証、`field(repr=False)`、`mime_type`はcanonical正規表現`^image/[A-Za-z0-9][A-Za-z0-9._+-]*$`）、`ai_image_generator.py`（`typing.Protocol`、`@runtime_checkable`不使用）。標準ライブラリ（`dataclasses` / `re` / `typing`）のみに依存する純粋Contract package。
- **`src/wordpress_media/`**（v6.9.0）：`WordPressMediaUploader(site_url, username, app_password)` + `from_env()` + `upload(image_bytes, filename, mime_type) -> MediaUploadResult`。`requests.post()`を使用し、`requests.RequestException`を`WordPressMediaUploadError(RuntimeError)`という単一の専用例外へ変換する。`from_env()`は不足環境変数を検出した場合`ValueError`を送出する（fail-fast）。
- **`src/outputs/wordpress_output.py`**：既に`article.featured_media_id > 0`の場合のみpayloadへ`featured_media`を追加する実装済みロジックを持つ（v1.6.0由来）。本Releaseでは変更しない。
- **`src/image_resolver.py`**：`resolve_media_id()`は現状常に`default_media_id`を返すのみで、`WordPressMediaUploader`への接続は未実装（`pass`のみのコメントアウト状態）。本Releaseでは変更しない。
- **`src/ai/claude_client.py`**（v1.14.0、Anthropic API連携の既存Adapterパターン）：`client=None`のConstructor Injectionパターン、`_get_client()`による遅延Client生成、`from_env()`パターンは参考にする。一方、次の3点は**本Releaseでは踏襲しない**（ユーザー指示どおり）：
  - `except Exception as e: print(...); return ""` という例外吸収＋print警告パターン
  - provider例外の内容（`{e}`）をそのまま`print`へ埋め込むパターン
  - `AiImprovementConfig.from_env()`における「不正な環境変数値を`except ValueError: fallback`で静かにデフォルト値へ丸める」パターン（`max_articles` / `timeout_seconds`のint変換失敗時）
- **`requirements.txt`**：`anthropic` / `google-auth` / `google-api-python-client` / `google-analytics-data`という**外部サービス公式Python SDK**が既に3系統で採用されている。`requests`は公式SDKを持たないWordPress REST APIへの直接アクセス（`wordpress_media` / `wordpress_output`）でのみ使用されている。`openai`は未追加。
- **既存E2Eのtest double戦略**：32ファイルが`unittest.mock.patch` + `MagicMock`を使用。`wordpress_media`は`requests.post`という裸関数をPatchする方式（Constructor Injectionの余地がないため）。`claude_client.py`は`client=None`によるConstructor Injectionの前例を持つが、対応するE2E（`test_e2e_v1_14_0_ai_improvement_foundation.py`）は本調査では詳細確認していない。

## 5. Problem Statement

`AIImageGenerator` Protocolへ、OpenAI Images API（`gpt-image-2`）を用いた最初の具象実装を追加する必要がある。ただし次の制約を同時に満たす必要がある。

1. `ai_image_generation`（v6.10.0）の標準ライブラリ限定Contractを一切破壊しない（依存方向は`OpenAI Adapter → ai_image_generation`の一方向のみ）
2. 外部API呼び出し・APIキー・Base64デコード・Provider例外という、v6.10.0では意図的に扱わなかった領域を、安全かつテスト可能な形で初めて導入する
3. WordPress Media Upload・記事投稿Pipelineへの配線は行わない（Consumer-less Foundationとして本Adapter単体を完成させる）
4. `ClaudeClient`が採用していた「例外を吸収してprintし空文字を返す」という設計は、秘密情報漏えい・安全なFailure Contract不在の観点から踏襲しない

## 6. Goals

1. `AIImageGenerator` Protocolを構造的に満たす`OpenAIImageGenerator`を新規独立packageとして追加する
2. OpenAI Images API（`POST /v1/images/generations`、OpenAI公式Python SDK経由）を用いて、単一の`prompt: str`から単一の`GeneratedImage`を生成する
3. `b64_json`をstrict Base64 decodeし、`GeneratedImage`の既存Contract（`type(value) is bytes`・非空・canonical MIME）を満たす形で変換する
4. Provider例外・Base64異常系・レスポンス構造異常系を、単一の安全な専用例外（`OpenAIImageGenerationError`）へ変換し、秘密情報・prompt全文・画像バイナリ・provider response全体を一切漏えいさせない
5. 実HTTPなしで全Contractをテスト可能な構造（Client Injection）を確立する
6. n=1固定・自動Retryなし・Timeout必須という、費用暴発とハングを防ぐ安全側設計を採用する
7. 1 Release＝1目的を維持する（WordPress・記事Pipelineへの配線は次Release以降）

## 7. Non-Goals

21章（Out of Scope）に同じ。

## 8. Release Classification

**Architecture Release**（development_workflow.md 6章・7章）。

### Fast Track候補条件（development_workflow.md 7章）該当確認

| 条件 | 該当有無 | 内容 |
|---|---|---|
| Public API変更なし | **該当しない（変更あり）** | 新規package `openai_image_generation` の新規Public API（`OpenAIImageGenerator` / `OpenAIImageGenerationError`）を追加 |
| Constructor変更なし | **該当しない（変更あり）** | `OpenAIImageGenerator.__init__` は新規Constructor |
| Composition Root変更なし | 該当する | 本Releaseはいずれの既存Composition Rootへも配線しない |
| Layer変更なし | **該当しない（変更あり）** | `ai_image_generation`（純粋Contract層）に対する初の「具象Provider Adapter層」を新設する |
| Dependency変更なし | **該当しない（変更あり）** | `requirements.txt`へ`openai`（新規外部パッケージ）を追加予定。`openai_image_generation → ai_image_generation`という新規package間import関係も追加 |
| 永続化変更なし | 該当する | ファイル・DB等への永続化は行わない |
| Event変更なし | 該当する | イベント型の新規追加・変更なし |
| 外部I/O変更なし | **該当しない（変更あり）** | OpenAI Images APIという新規外部サービス呼び出しを追加 |

8項目中5項目が不該当（Public API・Constructor・Layer・Dependency・外部I/O）であるため、**Fast Trackの余地はなく、Architecture Releaseに確定する**。development_workflow.md 4章「判断に迷った場合はArchitecture Releaseを選択する」の原則にも合致する。

---

## 9. Architecture Decision Summary

### 9.1 Architecture Decision Record（詳細表）

| # | 決定事項 | 採用案 | 却下案 | 採用理由 | リスク | 将来変更時の影響 |
|---|---|---|---|---|---|---|
| ADR-1 | API | **Image API**（`POST /v1/images/generations`） | Responses APIの`image_generation` tool | 単一テキストpromptから単一画像を生成するという今回の用途に対し、Responses APIは会話型・複数ターン編集を前提とした余剰機能を持つ。Image APIは目的に対し最小 | Responses API側の将来機能拡張の恩恵を受けない | 将来Responses API方式が必要になった場合は別Adapter package（別Release）として追加する。既存Contractへの影響なし |
| ADR-2 | Transport | **OpenAI公式Python SDK**（`openai`） | `requests`による直接HTTP | 11章で詳細比較。型付きレスポンス・公式例外階層・公式Timeout機構により実装・テストの安全性が高い。既存リポジトリも`anthropic`/`google-*`という公式SDK採用が主流 | SDK自体のバージョン追従が必要になる | Transport変更はConstructor Contract・Error Contractに影響するため、変更時は本文書のADR-2〜ADR-12の再Architecture Reviewを要する |
| ADR-3 | Model | **固定スナップショット**（`gpt-image-2-2026-04-21`） | モデルエイリアス（`gpt-image-2`） | 20章で詳細比較。再現性・破壊的変化回避を優先する既存プロジェクトの一貫方針（`GeneratedImage`の非自動変換方針等）に合致 | OpenAI側のスナップショット廃止時に追従Releaseが必要 | 将来のモデル更新は定数値の変更のみで済み、Constructor Contract・Public APIは変更不要（Fast Track候補になりうる） |
| ADR-4 | Output count | **n=1固定**（constructor引数・env変数いずれからも変更不可） | 設定可能にする | 費用暴発防止（6.15章 Cost Control Contract）。意図しない複数画像生成を構造的に禁止する | 将来複数候補生成が必要になった場合、Constructor Contract変更を伴うArchitecture Releaseが必要 | 変更時はPublic API変更を伴うため必ずArchitecture Release |
| ADR-5 | Output format | **allowlist設定**（`png` / `jpeg` / `webp`、デフォルト`png`） | PNG固定 | OpenAI API自体のデフォルトもpngであり、既存の3形式のみを機械的に許可することで、`GeneratedImage.mime_type`のcanonical Contractと1:1対応させやすい | allowlist外の将来フォーマット追加時はコード変更が必要 | allowlistへの追加はConstructor Contract非変更（値の追加のみ）のためFast Track候補になりうる |
| ADR-6 | Size | **allowlist設定**（7種、デフォルト`1024x1024`、Implementation Finding IMP-DESIGN-1反映） | `auto` | `auto`は生成結果サイズが非決定的になり、Cost Control Contract（6.15章）が要求する費用の予測可能性と矛盾する。OpenAI Provider自体は次の4条件（最大辺3840px以下・幅と高さがともに16pxの倍数・長辺短辺比3:1以内・総ピクセル数655,360以上8,294,400以下、Architecture Review 4 Finding AR4-m-1反映）をすべて満たす任意の`WIDTHxHEIGHT`をサポートするが、本Adapterはそのうち公式ドキュメントで代表例として確認できた7値に閉じたallowlistを採用し、Provider側の4条件の数式を自前で再実装しない。任意custom sizeの受理はv6.11.0では不採用とする | 将来allowlist外の新サイズが公式追加された場合、コード変更が必要 | 同上。allowlistへの追加はFast Track候補になりうる |
| ADR-7 | Quality | **allowlist設定**（`low` / `medium` / `high`、デフォルト`medium`）、`auto`は不採用 | `high`固定、`auto` | 20章で詳細比較。`medium`はコストと記事アイキャッチとしての実用性のバランスが取れたデフォルトであり、必要な記事では`high`へ明示的に上書き可能とする。`auto`は非決定的コストのため除外 | `medium`が特定の用途で画質不足になる可能性 | quality変更は呼び出し側のconstructor引数指定のみで対応可能（Fast Track候補） |
| ADR-8 | Background | **`opaque`固定**（constructor非公開） | `auto`、`transparent` | `gpt-image-2`は透明背景非対応（公式ドキュメントで確認）。`auto`は`transparent`非対応モデルでは`opaque`と等価だが、明示的固定の方が意図が明確で将来のモデル変更時の暗黙的挙動変化を防ぐ | なし（`gpt-image-2`である限りリスクなし） | 将来transparent対応モデルへ切り替える場合、Architecture Reviewを要する新規Contract判断 |
| ADR-9 | Client construction | **Constructor Injection**（`client=None`でデフォルトは遅延生成） | 内部生成のみ（Injection不可） | 実HTTPなしのテストを可能にする必須の設計。`ClaudeClient`の`client=None`パターンを踏襲（例外吸収・print警告は踏襲しない） | なし | Client型に破壊的変更がある場合、Injection利用テストの見直しが必要 |
| ADR-10 | API key | **constructor直接引数**（`from_env()`は別途提供） | Constructor内で環境変数を直接読む | `WordPressMediaUploader`と同型（`__init__`は素の引数のみ、`from_env()`が環境変数を読んで`__init__`へ渡す）。責務分離とテスト容易性を優先 | なし | なし（既存precedentと同型のため変更耐性が高い） |
| ADR-11 | Timeout | **constructor引数**（`timeout_seconds: int`、デフォルト**180秒**）＋任意環境変数 | 固定値のみ、Client全体Timeoutに一任、デフォルト120秒（Architecture Review 1 Finding M-1により変更） | 27章で詳細検討。OpenAI SDKのデフォルト（600秒）は寛容すぎ、既存WordPress系の30秒は画像生成には短すぎる。**公式ガイド「Complex prompts may take up to 2 minutes to process」を踏まえ、120秒（公式上限と同値・安全マージンゼロ）ではなく、180秒（50%のマージン）を採用する**（Architecture Review 1 Finding M-1反映） | 180秒でも実運用で不適切な場合がある（公式ドキュメントに生成時間の確定値・分布の記載なし） | 環境変数のみで調整可能なため、値の変更はFast Track候補（Contract自体は変更なし） |
| ADR-12 | Errors | **単一の安全な専用例外＋安全なreason分類**（`OpenAIImageGenerationError` + `OpenAIImageGenerationErrorReason` Enum、Architecture Review 1 Finding M-4反映） | 単一例外・追加情報なし、Retry可否のみ分類、Provider例外種別ごとに細分化 | 25章で詳細比較。現時点で本Releaseの消費者はゼロだが、reasonという安全な分類情報（秘密情報を含まない固定Enum値）すら持たないと、将来の消費者（Observability・Retry Runtime統合等）が固定メッセージ文字列のパースという脆い手段に頼らざるを得なくなる。型分岐（subclass化）やRetry方針と結合した`retryable: bool`は引き続き時期尚早として不採用とし、最小限の分類情報のみ追加する | reasonの値自体が将来の詳細化を要する可能性がある | 将来的なsubclass化は、実際の消費者が確定した時点でArchitecture Reviewを経て追加する。reason Enumへの値追加はConstructor Contract非変更のためFast Track候補になりうる |
| ADR-13 | Retry | **実装しない**（自動Retry・sleep・Backoffを一切行わない） | 自動Retry実装 | ユーザー指示どおり。加えて、OpenAI SDKクライアントの`max_retries`デフォルト値（2、429/5xx/接続エラーに自動再試行）を明示的に`max_retries=0`へ上書きしないと、SDKが暗黙に自動Retryを行ってしまうことが判明した（10章参照）。これは「Retryを実装しない」という設計意図に反するSDKのデフォルト挙動であり、明示的に無効化する。**さらに、Client Injection時にもこの保証が及ぶよう、`with_options()`による強制適用を採用する（ADR-17、Architecture Review 1 Finding B-1反映）** | Timeout到達までの待機時間がSDK既定より短くなる（＝安全側） | Retry方針を変更する場合、Rate Limit Contract（26章）の再設計を要する |
| ADR-14 | Base64 | **strict decode**（`base64.b64decode(value, validate=True)`） | 通常decode（`validate=False`） | 24章で詳細検討。不正文字を暗黙に無視する`validate=False`は、Provider応答の破損を静かに見逃すリスクがある。プロジェクト全体の「自動変換・暗黙補正を避ける」方針（`GeneratedImage`のmime_type非自動小文字化等）と整合 | 将来Providerが仕様外の緩いBase64を返した場合に拒否される | Provider側の実際の挙動と乖離した場合はKnown Issueとして記録し、個別に再検討する |
| ADR-15 | Logging | **なし**（`print` / `logging`いずれも実装しない） | 安全なmetadataのみログ | v6.9.0・v6.10.0双方の既存precedentと完全一致。Observability追加は将来のFast Track／Architecture Release候補として別途判断する | 障害時の運用可視性が低い | 将来Observability追加時は28章の禁止リストを厳守した設計が必要 |
| ADR-16 | Exception chaining | **`__cause__`・`__context__`双方の到達不能化**（`from None`＋except節外でのraise） | `from None`のみ | 29章で詳細検討。`from None`は`__cause__`をNoneにし既定のTraceback表示を抑止するが、Python言語仕様上`__context__`は暗黙に設定され続けるため、except節を抜けた後に`raise`する制御フローへ変更することで`__context__`自体を設定させない | 制御フローがやや複雑になる（安全メッセージを一度変数へ格納してから`raise`する） | この方式は本Adapter内の全例外変換箇所（Provider例外・Base64異常）へ一貫適用する |
| ADR-17 | Client Injection時のRetry／Timeout強制 | **`_get_client()`が返す直前に、注入・自己生成いずれの場合も`client.with_options(timeout=self._timeout_seconds, max_retries=0)`を通す**（Architecture Review 1 Finding B-1反映） | 内部生成経路のみ保証し、注入Client経路は呼び出し側の責任と明記する案 | 6.6章で指摘された「Client Injectionと自動Retryなし／Timeout必須Contractの矛盾」を解消する必要があった。呼び出し側の責任とする案は、Goal 6（費用暴発とハングを防ぐ安全側設計）を注入経路でだけ弱めることになり不採用とした | 注入されたClientが`with_options()`を持たない場合は16.2章のfail-fast方針（`TypeError`）に従う。これはProviderの障害ではなくprogramming／configuration errorであるため、Provider Failure（25章）とは区別する | Test Double（31章）は`with_options(**kwargs)`を実装し、渡された引数を記録できる必要がある |
| ADR-18 | Prompt Contract：NUL以外の制御文字 | **v6.11 Adapter独自の追加制約として、tab／LF／CRのみ許可し、他のC0制御文字とDELは拒否する**（Architecture Review 1 Finding M-3・案B、18.1章） | v6.10.0の文言を字義どおり実装し、NULのみ拒否する案（当初採用、Architecture Review 1で変更を指摘） | v6.10.0はNUL拒否・tab／LF許可のみを明示し、他の制御文字を積極的に許可してはいない。プロジェクト全体のfail-fast方針・将来のPrompt Builderへの防御を優先し、v6.10.0の文言と矛盾しない範囲でv6.11固有の追加制約とする | v6.10.0本体のContractを変更するものではないため、v6.10.0の再Reviewは不要と判断する（v6.11 Adapter固有の上乗せ制約） | 将来Prompt Builderが正当な理由で他の制御文字を必要とする場合、そのReleaseでArchitecture Reviewを経て緩和を検討する |

### 9.2 Architecture Decision Summary（AD番号一覧）

既存設計書（v6.9.0・v6.10.0）の記法に合わせ、上記表の内容をAD番号としても付番する。

| # | 内容 |
|---|---|
| AD-1 | Package配置：`src/openai_image_generation/`独立package（`src/ai_image_generation/`は無改修） |
| AD-2 | Public API：`OpenAIImageGenerator`と`OpenAIImageGenerationError`の2つのみ |
| AD-3 | `AIImageGenerator`適合方法：構造的部分型のみ。明示的継承・`@runtime_checkable`・`isinstance()`検証はいずれも行わない |
| AD-4 | Transport：OpenAI公式Python SDK採用（ADR-2） |
| AD-5 | Model：固定スナップショット`gpt-image-2-2026-04-21`をデフォルト値とし、constructor引数として上書き可能（allowlist化はしない、ADR-3） |
| AD-6 | n：1固定。constructor引数にも環境変数にも存在しない（ADR-4） |
| AD-7 | size：allowlist（**7値**、Implementation Finding IMP-DESIGN-1反映）、デフォルト`1024x1024`、`auto`不採用、任意custom sizeも不採用（ADR-6） |
| AD-8 | quality：allowlist（`low`/`medium`/`high`）、デフォルト`medium`、`auto`不採用（ADR-7） |
| AD-9 | output_format：allowlist（`png`/`jpeg`/`webp`）、デフォルト`png`（ADR-5） |
| AD-10 | background：`opaque`固定、constructor非公開（ADR-8） |
| AD-11 | moderation／response_format／stream／partial_images／user／style：いずれもリクエストへ含めない（APIデフォルトに委ねる、または非対応のため） |
| AD-12 | Client construction：`client=None`によるConstructor Injection＋遅延生成（ADR-9） |
| AD-13 | API key：constructor直接引数＋`from_env()`（ADR-10） |
| AD-14 | Timeout：constructor引数（デフォルト**180秒**、Architecture Review 1 Finding M-1反映）＋任意環境変数`OPENAI_IMAGE_TIMEOUT_SECONDS`。SDK Client構築時に`timeout=`として設定（ADR-11） |
| AD-15 | `max_retries=0`をOpenAI Client使用直前に`with_options()`経由で明示指定（SDKデフォルトの暗黙Retryを無効化。Client Injection経路にも適用、ADR-13・ADR-17） |
| AD-16 | Errors：単一例外`OpenAIImageGenerationError(RuntimeError)`＋安全な`reason`分類（`OpenAIImageGenerationErrorReason` Enum、Architecture Review 1 Finding M-4反映、ADR-12） |
| AD-17 | Retry：本Releaseでは実装しない（ADR-13） |
| AD-18 | Base64：`base64.b64decode(value, validate=True)`によるstrict decode（ADR-14） |
| AD-19 | MIME type：`self._output_format`から固定allowlist mappingで導出。response側の`output_format`フィールドは読まない（22章） |
| AD-20 | decode結果が空bytesの場合：`GeneratedImage`構築前に明示チェックし`OpenAIImageGenerationError`（`ValueError`ではない）とする（24章） |
| AD-21 | Prompt Contract：v6.10.0設計書12章の「将来Adapter向けPrompt Contract」をそのまま採用する（18章） |
| AD-22 | Prompt最大長：32000文字（OpenAI公式ドキュメント確認値）をクライアント側で事前検証する（18章） |
| AD-23 | Logging：`print`/`logging`いずれも実装しない（ADR-15） |
| AD-24 | Exception chaining：`__context__`到達不能化のため、except節を抜けた後にraiseする制御フロー＋`from None`を併用する（ADR-16） |
| AD-25 | `__repr__`：独自定義しない。Python既定の`object.__repr__()`（クラス名＋メモリアドレスのみ）に委ね、秘密情報露出の余地を構造的に排除する |
| AD-26 | Null Object Pattern：本Releaseでは導入しない（`NullOpenAIImageGenerator`等を作らない）。理由は16章参照 |
| AD-27 | Dependency Guard：v6.9.0・v6.10.0と同様、AST（`ast.Import`/`ast.ImportFrom`）解析による禁止import検知を最初から採用する（32.7章） |
| AD-28 | Client Injection時のRetry／Timeout強制：`_get_client()`は注入・自己生成いずれの場合も`with_options(timeout=self._timeout_seconds, max_retries=0)`を経由してのみClientを返す（ADR-17、Architecture Review 1 Finding B-1反映） |
| AD-29 | Prompt Contractの追加制約：v6.11 Adapter固有の上乗せとして、tab／LF／CR以外の制御文字（他のC0制御文字・DEL）を拒否する（ADR-18、Architecture Review 1 Finding M-3反映） |
| AD-30 | requirements.txt version constraint：`openai>=2.46.0,<3.0.0`（互換範囲固定、Architecture Review 1 Finding M-2反映） |
| AD-31 | 実HTTP防止の構造的保証（二重防御）：**主防御＝Runtime Guard**（`openai.OpenAI`をpatchし、無許可の実Client構築が起きた場合に即座に`AssertionError`を送出させる。自己生成経路を検証するScenarioのみ、安全なFake Constructorへ局所的に差し替える）、**補助防御＝AST自己検査**（`OpenAIImageGenerator(...)`呼び出しが原則として`client=`を明示していることの静的検証）。AST自己検査はRuntime Guardの代替ではなく補助として位置づける（Architecture Review 1 Finding M-5・継続審議反映、31.4章・34章） |

---

## 10. Official OpenAI API Findings

**調査日：2026-07-17**。Claude CodeのWebSearch／WebFetchツールにより、`developers.openai.com`（OpenAI公式ドキュメントドメイン）を直接調査した。非公式ブログ・第三者記事はAPI Contractの根拠として採用していない（価格の参考情報のみ、10.6節で出典を明示のうえ区別して記載）。

### 10.1 モデル

- 正式スナップショットID：`gpt-image-2-2026-04-21`（リリース日2026-04-21）
- エイリアス：`gpt-image-2`
- 非対応機能（公式モデルページ確認）：ストリーミングされたテキスト応答用途のfunction calling・structured outputs・fine-tuning・predicted outputsは非対応（画像生成の`stream`パラメータ自体は別途Images APIで提供）

### 10.2 API・エンドポイント

- `POST /v1/images/generations`（Image API）
- OpenAI Python SDK：`client.images.generate(...)`
- Responses APIの`image_generation` tool・Image Edit API（`/v1/images/edits`）は今回不採用（5章・11章参照）

### 10.2.1 画像生成の所要時間（Architecture Review 1で追加確認）

`developers.openai.com/api/docs/guides/image-generation`に「**Complex prompts may take up to 2 minutes to process**」という記載が存在する。当初のArchitecture Design時点の調査では「公式ドキュメントに所要時間の確定値が記載されていない」としていたが（Architecture Review 1 Finding M-1）、この記載を見落としていたことが判明した。この「最大2分」という公式の目安値は、Timeout Contract（27章）のデフォルト値決定に直接関わる重要な情報であり、デフォルト値をこの上限と同値（安全マージンゼロ）にしないよう27章を改訂した。

### 10.3 リクエストパラメータ（`gpt-image-2`関連分のみ抜粋）

| パラメータ | 型 | gpt-image-2での扱い |
|---|---|---|
| `model` | string | `"gpt-image-2"`（エイリアス）または`"gpt-image-2-2026-04-21"`（スナップショット） |
| `prompt` | string | 必須。最大32000文字（GPT image系） |
| `n` | number | 複数画像生成に対応（上限は本調査で確定値を確認できず） |
| `size` | string | `auto`（Provider側デフォルト。本Adapterでは不採用、21章）、`1024x1024`、`1536x1024`、`1024x1536`、`2048x2048`、`2048x1152`、`3840x2160`、`2160x3840`（代表7値）。制約（Provider Capability、Architecture Review 4 Finding AR4-m-1反映）：最大辺3840px以下、幅と高さがともに16pxの倍数、長辺短辺比3:1以内、総ピクセル数655,360以上8,294,400以下 |
| `quality` | string | `low` / `medium` / `high` / `auto`（デフォルト`auto`）。**Architecture Review 1 Finding m-2反映**：SDKの生Literal定義は`"standard" | "hd" | "low" | "medium" | "high" | "auto"`というモデル非依存の単一型だが、`standard` / `hd`はDALL-E-3専用の値であり、`gpt-image-2`では無効である。16.1章の`_ALLOWED_QUALITIES`allowlistはこの2値を含めず、`gpt-image-2`で有効な`low` / `medium` / `high`のみに正しく限定している |
| `output_format` | string | `png`（デフォルト）／`jpeg`／`webp` |
| `output_compression` | number | 0〜100（`jpeg`/`webp`のみ有効） |
| `background` | string | `transparent` / `opaque` / `auto`（デフォルト`auto`）。**`gpt-image-2`は透明背景非対応。透明リクエストは許可されない（公式ドキュメント記載）** |
| `moderation` | string | `auto` / `low`（GPT image系のみ有効、デフォルト`auto`） |
| `response_format` | string | **GPT image系モデルでは非サポート**（常にBase64で返却されるため） |
| `stream` / `partial_images` | boolean / number | ストリーミング用途。今回不使用 |
| `user` | string | エンドユーザー識別用。今回不使用 |

### 10.4 レスポンス形（`ImagesResponse`）

```text
created: number（Unixタイムスタンプ）
background: "transparent" | "opaque"（オプション）
data: Image[]
    b64_json: string（GPT image系はデフォルトで返却）
    revised_prompt: string（オプション。DALL-E-3系のみとの記載あり）
output_format: "png" | "webp" | "jpeg"（オプション、レスポンスエコー）
quality: "low" | "medium" | "high"（オプション、レスポンスエコー）
size: string（オプション、レスポンスエコー）
usage: { input_tokens, output_tokens, total_tokens, ... }（オプション）
```

`b64_json`は常にBase64エンコードされた画像データとして返却される（`response_format`が使えないため、URL形式は選択不可）。

### 10.5 SDK例外階層（`openai-python`）

```text
Exception
└── OpenAIError
    └── APIError
        ├── APIStatusError
        │   ├── BadRequestError（HTTP 400）
        │   ├── AuthenticationError（HTTP 401）
        │   ├── PermissionDeniedError（HTTP 403）
        │   ├── NotFoundError（HTTP 404）
        │   ├── ConflictError（HTTP 409）
        │   ├── UnprocessableEntityError（HTTP 422）
        │   ├── RateLimitError（HTTP 429）
        │   └── InternalServerError（HTTP 5xx）
        └── APIConnectionError（HTTP到達不能）
            └── APITimeoutError（Timeout）
```

**重要な発見**：`APIError`は`message` / `request` / `body` / `code` / `param` / `type`属性を持ち、`APIStatusError`はさらに`response` / `status_code` / `request_id`を持つ。`request`属性は送信された実際のHTTPリクエスト相当のオブジェクトであり、**Authorizationヘッダー（APIキー）を含みうる**。`body`属性はサーバーからの生レスポンスボディを保持しうる。これらの属性を保持したまま例外チェーン（`__cause__`・`__context__`）を残すと、APIキー・prompt断片（Content Policy違反時のエラーメッセージにprompt由来のテキストが反映される場合がある）が間接的に到達可能になるリスクがある。この発見はSecurity Contract（28章）・Exception Chaining Contract（29章）の設計根拠となった。

### 10.6 Client設定（`openai` SDK）

- Timeoutデフォルト：600秒（10分）
- `max_retries`デフォルト：**2**。接続エラー・HTTP 408／409／429／5xxで**自動的に**再試行される（SDKの既定挙動）
- **重要な発見**：「今回のReleaseでは自動Retryを実装しない」という方針を守るには、`openai.OpenAI(..., max_retries=0)`を明示的に指定しなければ、SDK自体が暗黙にRetryを行ってしまう。これは当初のユーザー前提には明記されていなかった、公式ドキュメント調査によって判明した事実である（AD-15）
- **Architecture Review 1で追加確認した事実（1）**：`client.images.generate()`は、Client全体のTimeout／`max_retries`設定とは別に、**request単位の`timeout`引数**（`timeout: float | httpx.Timeout | None | NotGiven`）を受け付ける（`openai-python`ソースコード`src/openai/resources/images.py`で確認）。当初の設計時点の調査ではこの引数の存在を確認できなかったが（19.2章）、Architecture Reviewでの再調査により実在が判明した。ただし本Releaseでは、request単位設定を追加すると設定経路が2つに分裂しContractが複雑化するため、**Client単位設定のみを採用する方針は維持する**（19.2章で理由を改訂）
- **Architecture Review 1で追加確認した事実（2）**：`client.with_options(timeout=..., max_retries=...)`は、既存Clientインスタンスを変更せず、指定したオプションだけを上書きした新しいClient（またはリソース）を返す。これは注入されたClientに対しても安全にTimeout／`max_retries`を強制適用できる手段であり、Client Injection Contract（16.2章、ADR-17）の設計根拠となった
- **継続審議での再確認（`with_options()`の実在確認）**：`openai-python`ソースコード`src/openai/_client.py`を直接取得し、`OpenAI`クラスに`with_options = copy`という定義（`copy()`メソッドのエイリアス）が存在することを確認した。`copy()`は`timeout` / `max_retries`を含むキーワード引数を受け付け、ドキュメント文字列に「新しいクライアントインスタンスを再利用して、オプションを選択的にオーバーライドする」と明記されており、**元のインスタンスを変更しない**（破壊的変更ではない）ことも確認した。この確認はAdapter設計判断（16.2章）を裏付ける

### 10.7 SDKバージョン

PyPI（`https://pypi.org/project/openai/`）で確認した最新バージョンは**2.46.0（2026-07-17リリース、本調査当日）**。`gpt-image-2`は2026-04-21リリースであり、本調査時点の最新版（2.46.0）が対応していることは確実である。ただし、`gpt-image-2`固有パラメータ（`background` / `output_compression` / `moderation`）を型付きでサポートし始めた**正確な最小バージョン**は、`openai-python`公式CHANGELOG（`https://github.com/openai/openai-python/blob/main/CHANGELOG.md`）の調査では特定できなかった（ファイルが大きく該当箇所を確定できなかった。gpt-image-1.5が2.13.0で追加されたことは確認できたが、gpt-image-2の追加バージョンは未確認）。**推測でバージョンを記載しない**というユーザー指示に従い、本文書では次の方針を採る。

**Architecture Review 1 Finding M-2・m-3反映**：`openai-python`のGitHub Issue #3114（`gpt-image-2`が型付き`ImageModel` Literalへ追加されるまでの経緯を扱う）の調査により、`model`引数の型が`Union[str, ImageModel, None]`という緩い型（文字列を直接渡せる）であることを確認した。したがって、**`model`引数はstrを受け付けるためruntime（実行時）影響は限定的である**。ただし**mypy／pyright等の型チェッカーを利用する場合には影響しうる**（Issue #3114はまさにこの型チェッカー起因の指摘である）。本プロジェクトが型チェッカーを実際に使用しているかどうかは、本調査では確認しておらず断定しない。モデル名自体の型定義タイミングは実行時動作に影響しないため、`background` / `output_format` / `output_compression` / `moderation`という**型付きパラメータの追加時期**の方が実質的なバージョン制約要因である。この点を踏まえても正確な最小バージョンの特定には至らなかったため、下限は引き続き安全側（PyPIで動作確認できた版）を採用する。

加えて、当初案は下限のみを指定し上限を設けていなかったが、`openai-python`が活発に更新されている（調査期間中だけで月間複数回のマイナーリリースを確認）ことを踏まえ、**将来のメジャーバージョンアップによる無審査の破壊的変更を防ぐため、上限を追加した互換範囲固定とする**（AD-30）。

```text
requirements.txt追加候補：openai>=2.46.0,<3.0.0
```

下限は「確実に対応していることをPyPIで確認できた版」を安全側の下限として採用したものであり、理論上の最小必要バージョンではない（41章 Known Issues参照。Implementation段階でより精密な下限を確認できる場合は置き換えてよい）。上限は現行メジャーバージョン（2.x系）への固定であり、3.0.0以降がリリースされた場合は、その内容を確認したうえで別途Architecture Reviewを経て追従する。

### 10.8 価格（参考情報。固定Architecture Contractではない）

`developers.openai.com/api/docs/pricing`（公式）で確認した`gpt-image-2`のトークン単価（Standard Tier）：

```text
Image Input:  $8.00  / 1M tokens
Image Output: $30.00 / 1M tokens
Text Input:   $5.00  / 1M tokens
```

出力トークン数はサイズ・qualityに応じて概ね196〜4160トークン程度（`developers.openai.com/api/docs/guides/image-generation`で確認）。**1枚あたりの具体的な$金額（例：$0.05等）は、本文書では固定値として記載しない**。これは変動しうる運用情報であり、正確な見積りは公式の料金計算ツール（画像生成ガイド内）を都度参照すべきものである。第三者ブログ（WaveSpeed等）による$換算例は本調査で参照したが、Architecture Contractの根拠にはしていない。

**情報の区分**：

```text
固定Architecture Contract：n=1固定・quality/sizeのデフォルト値と根拠（9章ADR-6・ADR-7）
調査時点の参考料金：上記トークン単価（2026-07-17時点、公式ページ確認）
将来変動する運用情報：実際の$/image・Rate Limit Tier・月間費用（本Release対象外、ユーザーアカウント確認は禁止事項）
```

Sources:
- [GPT Image 2 Model | OpenAI API](https://developers.openai.com/api/docs/models/gpt-image-2)
- [Image generation | OpenAI API](https://developers.openai.com/api/docs/guides/image-generation)
- [Create image | OpenAI API Reference](https://developers.openai.com/api/reference/resources/images/methods/generate)
- [Pricing | OpenAI API](https://developers.openai.com/api/docs/pricing)
- [openai (PyPI)](https://pypi.org/project/openai/)
- [openai-python CHANGELOG](https://github.com/openai/openai-python/blob/main/CHANGELOG.md)
- [openai-python _exceptions.py](https://github.com/openai/openai-python/blob/main/src/openai/_exceptions.py)

---

## 11. SDK vs requests Decision

| 観点 | A. OpenAI公式Python SDK | B. requestsによる直接HTTP |
|---|---|---|
| 公式サポート | 公式提供・積極的にメンテナンスされている（2026-07-17時点で2.46.0が同日リリース） | なし（自前でエンドポイント仕様を追従する必要） |
| API変更への追従 | SDK側がレスポンス構造・新パラメータに追従 | 変更のたびに自前でリクエスト／レスポンス構造を追従する必要 |
| 型・レスポンス構造 | Pydanticベースの型付きレスポンス（`ImagesResponse` / `Image`） | 生JSON dict、型保証なし |
| Timeout | Client単位・既定値あり（600秒）、明示的上書き可能 | `requests.post(timeout=...)`で個別指定（既存`wordpress_media`と同型） |
| 例外分類 | 公式例外階層（`APIError`系統、10.5節）が最初から用意されている | `requests.RequestException`のみ。HTTPステータスによる分岐は自前実装が必要 |
| Test Double | Constructor Injection（`client=`引数）でFake Client注入が可能 | 関数`requests.post`をPatchする必要（Patch target解決の脆さがv6.9.0 Test Reviewで既に問題として顕在化した実績あり） |
| dependency追加 | `openai`パッケージを新規追加（マイナスポイント） | `requests`は既にrequirements.txtに存在（追加不要） |
| 既存リポジトリとの一貫性 | `anthropic` / `google-auth` / `google-api-python-client` / `google-analytics-data`という既存3系統の外部サービス連携は、いずれも公式SDKを採用している。`requests`直接利用は公式SDKを持たないWordPress REST APIのみ | `wordpress_media` / `wordpress_output`と同型にはなるが、それらは「公式SDKが存在しない」という制約下の選択であり、OpenAIには公式SDKが存在する以上、一貫性の観点ではSDK側が優位 |
| Security | Authorizationヘッダー構築・レスポンス検証をSDKが担う（実装ミスのリスクが小さい） | ヘッダー構築・エラーレスポンス解析を自前実装する必要があり、`wordpress_media`のAD-14相当の安全化作業を再度自前で行う必要がある |
| 保守コスト | OpenAI側のBreaking Changeへの追従はSDKのバージョンアップで対応可能 | エンドポイント仕様変更を都度自前で検知・追従する必要がある |

**結論：A（OpenAI公式Python SDK）を採用する（ADR-2）。**

「dependency追加」の1項目のみBが優位（`requests`は追加不要）だが、他の8項目すべてでAが優位、特に「既存リポジトリとの一貫性」は当初想定より強い根拠が確認できた（`requirements.txt`の外部サービス連携4系統中3系統が既に公式SDK採用）。ユーザー前提でも「現時点では公式Python SDKを第一候補とする」とされており、本調査の結果はこれを裏付ける。

---

## 12. Proposed Package Structure

### 12.1 Package名比較

| 候補 | 評価 |
|---|---|
| `src/openai_image_generation/` | **採用**。`src/wordpress_media/`（provider＋domain名）と同型の命名規則。`ai_image_generation`（provider非依存のdomain名）との対比で「provider固有の具象実装である」ことが名前から明確 |
| `src/openai_image_adapter/` | 却下。既存package群（`retry_alert` / `retry_notification` / `wordpress_media`）はいずれも「adapter」「client」のような役割Suffixを使わず、ドメイン名のみで命名されている。既存命名規則との整合性が`openai_image_generation`より低い |

### 12.2 Module構成

```text
projects/03_game_content_ai/src/openai_image_generation/
├── __init__.py                  # Public API export
└── openai_image_generator.py    # OpenAIImageGenerator + OpenAIImageGenerationError
```

`wordpress_media`が3ファイル構成（`__init__.py` / `media_upload_result.py` / `wordpress_media_uploader.py`）なのに対し、本Releaseは2ファイル構成とする。理由：`wordpress_media`は新規Public Model（`MediaUploadResult`）を導入したため専用ファイルを設けたが、本Releaseは戻り値として既存の`GeneratedImage`（`ai_image_generation`）をそのまま再利用し、新規Result型を導入しない。専用例外`OpenAIImageGenerationError`は、唯一の送出元である`openai_image_generator.py`内に定義する（`wordpress_media_uploader.py`と同じ判断、AD-10相当）。

### 12.3 既存packageの変更有無

```text
src/ai_image_generation/ ：変更なし
src/wordpress_media/     ：変更なし
src/outputs/              ：変更なし
src/image_resolver.py     ：変更なし
既存テスト一式             ：変更なし
```

---

## 13. Dependency Direction

```text
許可：
openai_image_generation → ai_image_generation（GeneratedImageのみimport。AIImageGeneratorはimportしない、15章参照）
openai_image_generation → openai（Python SDK、新規）
openai_image_generation → Python standard library（base64, os, typing等）

禁止：
openai_image_generation → wordpress_media
openai_image_generation → outputs
openai_image_generation → image_resolver
openai_image_generation → ArticleData
openai_image_generation → Workflow
openai_image_generation → Scheduler
openai_image_generation → Retry Runtime
openai_image_generation → anthropic
openai_image_generation → PIL / Pillow
openai_image_generation → requests（11章の決定によりSDK採用のため、直接HTTPライブラリは禁止対象に追加する）

既存の逆方向禁止（v6.10.0で確定済み、本Releaseでも維持）：
ai_image_generation → openai_image_generation（禁止）
ai_image_generation → openai（禁止）
```

E2EのDependency Guardは、v6.9.0・v6.10.0と同様に`ast.Import` / `ast.ImportFrom`ノード解析による禁止import検知を最初から採用する（AD-27、32.7章）。

---

## 14. Public API

**Architecture Review 1 Finding M-4反映**：単一例外方針は維持しつつ、秘密情報を含まない安全な失敗分類として`OpenAIImageGenerationErrorReason`（Enum）をPublic APIへ追加する（25章）。

```python
# src/openai_image_generation/__init__.py
from .openai_image_generator import (
    OpenAIImageGenerationError,
    OpenAIImageGenerationErrorReason,
    OpenAIImageGenerator,
)

__all__ = [
    "OpenAIImageGenerator",
    "OpenAIImageGenerationError",
    "OpenAIImageGenerationErrorReason",
]
```

`OpenAIImageGenerationRateLimitError` / `OpenAIImageGenerationAuthenticationError` / `OpenAIImageGenerationTimeoutError` / `OpenAIImageGenerationResponseError`という**独立した例外subclass**はいずれも導入しない（AD-16、25章で理由を詳述）。`OpenAIImageGenerationErrorReason`は例外の型を分岐させるsubclass階層ではなく、単一の例外型が持つ安全な分類属性（Enum）である点が異なる。

---

## 15. OpenAIImageGenerator Contract

```python
class OpenAIImageGenerator:
    def generate(self, prompt: str) -> GeneratedImage:
        ...
```

### 15.1 AIImageGeneratorとの適合方法

**構造的部分型（Structural Subtyping）のみを採用する。`AIImageGenerator`を明示継承しない。**

比較：

| 案 | 内容 | 判定 |
|---|---|---|
| 明示継承 | `class OpenAIImageGenerator(AIImageGenerator): ...` | 却下。`typing.Protocol`は構造的型付けのために設計されており、v6.10.0設計書もE2Eにおいて「Fakeが`generate(prompt)`を実装できること（構造的適合）」という方針を既に確定している（PROTO章）。明示継承は不要な結合を生み、Protocol本来の使い方から外れる |
| 構造的部分型 | `generate(self, prompt: str) -> GeneratedImage`を独立に実装するのみ | **採用**。v6.10.0のE2E Fakeパターンと完全に一致する |

`AIImageGenerator`自体をimportするかどうかも検討した。構造的部分型では実行時にimportが不要であり、`isinstance()`検証も行わない（`@runtime_checkable`が付与されていないため、行おうとしてもTypeErrorになる）。本Adapterは`ai_image_generation`から`GeneratedImage`のみをimportし、`AIImageGenerator`はimportしない（AD-3、13章）。これによりDependency Guard（32.7章）がテストすべき対象が「戻り値型のみ」に単純化される。

**PROTO Test Scenario（Test Review 1指摘反映）**：`isinstance(generator, AIImageGenerator)`は`@runtime_checkable`でないため使用しない（禁止）。構造適合は次の2 Scenarioで検証する。

```text
PROTO-STRUCTURAL：32.1章のNormal Scenarioにおいて、generate(prompt: str)を
    実際に呼び出しGeneratedImageが返ることそのものが構造適合の実証となる
    （追加のisinstance検証は不要）
PROTO-SIGNATURE：inspect.signature(OpenAIImageGenerator.generate)により、
    パラメータ名"prompt"・戻り値annotationが期待どおりであることを補助的に
    確認する（静的な明示性向上のための追加確認、1 Assertion）
```

---

## 16. Constructor Contract

```python
def __init__(
    self,
    api_key: str,
    *,
    model: str = _DEFAULT_MODEL,               # "gpt-image-2-2026-04-21"
    size: str = _DEFAULT_SIZE,                   # "1024x1024"
    quality: str = _DEFAULT_QUALITY,             # "medium"
    output_format: str = _DEFAULT_OUTPUT_FORMAT, # "png"
    timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,  # 180（Architecture Review 1 Finding M-1反映）
    client: "openai.OpenAI | None" = None,
) -> None:
    ...
```

### 16.1 各引数の検証Contract（fail-fast、`ValueError`）

| 引数 | 検証内容 |
|---|---|
| `api_key` | `type(value) is not str` → ValueError／`not value.strip()` → ValueError。値そのものは例外メッセージへ含めない（フィールド名のみ） |
| `model` | `type(value) is not str` → ValueError／`not value.strip()` → ValueError。**allowlist化しない**（将来のOpenAI側モデル追加へ追従するため。20章参照） |
| `size` | `type(value) is not str` → ValueError／`_ALLOWED_SIZES`（**7値**、Implementation Finding IMP-DESIGN-1反映）に含まれない → ValueError。`auto`・任意custom sizeのいずれも含まれない（21章） |
| `quality` | `type(value) is not str` → ValueError／`_ALLOWED_QUALITIES`（`low`/`medium`/`high`）に含まれない → ValueError。`auto`は含まれない（21章） |
| `output_format` | `type(value) is not str` → ValueError／`_ALLOWED_OUTPUT_FORMATS`（`png`/`jpeg`/`webp`）に含まれない → ValueError |
| `timeout_seconds` | `type(value) is not int`（`bool`除外） → ValueError／`value <= 0` → ValueError |
| `client` | 型検証・isinstance検証を行わない（AD-3と同じ理由でProtocol的に扱う。存在しないメソッドを呼び出した場合はSDK/Python標準の`AttributeError`が発生し、25章のcatch-allにより安全な例外へ変換される） |

`n`・`background`はconstructor引数に存在しない（ADR-4・ADR-8。9章参照）。

### 16.2 Client Injection・遅延生成

**Architecture Review 1 Finding B-1反映**：当初案は「`self._client`が`None`の場合のみ`max_retries=0`／`timeout`を設定する」という分岐構造であり、Constructor Injectionされた既存Clientにはこれらの安全設定が一切適用されないという矛盾があった（Client Injectionは31.2章のとおりproduction Constructor Contractの正式な一部であり、テスト専用ではない）。この矛盾を解消するため、**注入・自己生成いずれの経路でも、Clientを使用する直前に必ず`with_options(timeout=..., max_retries=0)`を経由させる**設計へ変更する（ADR-17・AD-28）。`with_options()`の実在・仕様は10.6章のとおり公式ソース（`src/openai/_client.py`）で確認済みである。

**Minimal Images Client Contract（Architecture Review 1 継続審議で追加）**：`client`引数（注入・自己生成いずれも）に対して本Adapterが要求する最小限のInterfaceを、次のとおり明文化する。

```text
images.generate(**kwargs) -> レスポンスオブジェクト（23章 Response Contractに従う）
with_options(*, timeout: float, max_retries: int) -> 同じInterfaceを持つClient
```

正式な`typing.Protocol`は定義しない（過剰なruntime introspectionを避けるため）。代わりに、`with_options`属性の有無を**Provider呼び出しより前の1回だけ**検査し、Interface不適合をfail-fastで検出する。これはProviderの障害ではなく、呼び出し側のprogramming／configuration errorであるため、25章のProvider Failure Contractとは明確に区別し、`OpenAIImageGenerationError`へは変換しない。

```python
def _get_client(self) -> "openai.OpenAI":
    if self._client is None:
        import openai
        self._client = openai.OpenAI(api_key=self._api_key)

    if not hasattr(self._client, "with_options"):
        # Provider障害ではなく、注入されたClientがMinimal Images Client Contract
        # を満たさないという呼び出し側の設定ミスである。25章のProvider Failure
        # Contract（OpenAIImageGenerationError）へは変換せず、Python標準の
        # TypeErrorとしてfail-fastさせる（Architecture Review 1 継続審議反映）。
        raise TypeError(
            "OpenAIImageGenerator: injected client does not implement with_options()"
        )

    # Client Injection・自己生成いずれの経路でも、使用直前に必ずこの1行を経由させる。
    # with_options()は元のClientを変更せず、指定オプションのみを上書きした新しい
    # Client（相当のView）を返すため、呼び出し側が注入したClientの本来の設定を
    # 破壊しない一方、本Adapterの安全Contract（自動Retryなし・Timeout必須）を
    # 注入経路でも構造的に保証できる（10.6章で確認したSDK仕様、AD-28）。
    return self._client.with_options(
        timeout=self._timeout_seconds,
        max_retries=0,   # AD-15・AD-28：SDK既定の暗黙Retryを、注入Clientに対しても無効化
    )
```

処理順序は次のとおり固定する（5章 継続審議の推奨処理順に対応）。

```text
1. Client準備（注入済みならそのまま、未注入ならopenai.OpenAI(api_key=...)を遅延生成）
2. Minimal Images Client Contractの充足確認（hasattr(client, "with_options")）。
   不足時は TypeError で即座にfail-fast（Provider Failureへ変換しない）
3. with_options(timeout=..., max_retries=0) を経由してClientを取得
4. images.generate(**kwargs) 呼び出し（try/exceptで包む、23章・25章・29章）
5. Provider例外だけを OpenAIImageGenerationError へ変換する（25章・29章）
```

`import openai`はメソッド内遅延import（`ClaudeClient._get_client()`の`import anthropic`と同型）とする。理由：`client`がConstructor Injectionされるテストコード経路では`openai`パッケージの実体が一切importされず、テストの独立性が高まる（Dependency Guardのテストにも寄与する）。

31章のTest Double戦略は、この`with_options()`呼び出しに対応できるFake Clientを要求する（31.2章で改訂）。`with_options()`を意図的に持たないFake Clientを用いたScenarioは、`TypeError`が送出されること（`OpenAIImageGenerationError`ではないこと）を確認するConstructor／Configuration系Scenarioとして32.2章へ追加する。

### 16.3 `__repr__` Contract（AD-25）

独自の`__repr__` / `__str__`を実装しない。Python既定の`object.__repr__()`（クラス名＋メモリアドレスのみを返す）に委ねる。`self._api_key`はインスタンス属性として保持されるが、既定のreprはインスタンス属性を列挙しないため、追加コードなしで秘密情報露出を構造的に防止できる。

---

## 17. from_env() Contract

```python
@classmethod
def from_env(cls) -> "OpenAIImageGenerator":
    ...
```

### 17.1 環境変数

| 環境変数 | 必須／任意 | 内容 |
|---|---|---|
| `OPENAI_API_KEY` | **必須** | 未設定・空文字・空白のみの場合 `ValueError`（環境変数名のみを例外メッセージに含め、値は含めない） |
| `OPENAI_IMAGE_TIMEOUT_SECONDS` | 任意 | 未設定時は`_DEFAULT_TIMEOUT_SECONDS`（180、Architecture Review 1 Finding M-1反映）を使用。設定されている場合は`int()`変換を試み、失敗時（非数値文字列等）は`ValueError`。変換成功しても`<= 0`の場合は`ValueError`。**`except ValueError`で既定値へ静かにフォールバックしない**（`ai_improvement_config.py`の`max_articles`/`timeout_seconds`パースパターンとは意図的に異なる。16.1章・4章参照） |

### 17.1.1 環境変数の隔離・復元方式（Test Review 1 Finding FIND-5反映）

**Test Review 1 Finding FIND-5**は、`from_env()`テストにおける環境変数の具体的な隔離・復元方法が設計書に明記されていないことを指摘した。標準ライブラリ`unittest.mock`の`patch.dict`を用いる方式を確定する。

```python
import os
from unittest.mock import patch

# 正常系（OPENAI_API_KEY設定済み、OPENAI_IMAGE_TIMEOUT_SECONDS未設定）：
with patch.dict(os.environ, {"OPENAI_API_KEY": "test-api-key"}, clear=True):
    ...  # from_env() を呼び出し、timeout_secondsが180であることを確認する

# 正常系（両方設定済み）：
with patch.dict(
    os.environ,
    {"OPENAI_API_KEY": "test-api-key", "OPENAI_IMAGE_TIMEOUT_SECONDS": "300"},
    clear=True,
):
    ...

# 異常系（OPENAI_API_KEY未設定）：clear=Trueにより対象変数を辞書へ含めないだけでよい
with patch.dict(os.environ, {}, clear=True):
    ...  # from_env() が ValueError を送出することを確認する
```

**必須事項**：

```text
各Caseは patch.dict(os.environ, {...}, clear=True) で環境変数を隔離する
    （clear=True により、テスト実行環境に存在する無関係な環境変数の影響を排除する）
withブロック終了時に元の環境変数へ自動復元される（unittest.mock標準機能、
    明示的なteardown処理は不要）
実OPENAI_API_KEY（テスト実行環境に実際に設定されている値があれば）を読まない
    （clear=Trueにより、withブロック内では明示的に指定した変数のみが有効になる）
実OPENAI_API_KEYを上書き・削除したままにしない（withブロックによる自動復元で保証）
Case間で環境変数状態を共有しない（各Caseが独立したpatch.dictスコープを持つ）
未設定Caseは、対象変数を辞書に含めないことで表現する
    （例：{"OPENAI_API_KEY": "test-api-key"} のみを渡し
    OPENAI_IMAGE_TIMEOUT_SECONDSを省略すれば「未設定」を表現できる）
```

環境変数値を例外・print・reprへ出さないという既存Contract（28章）は本方式でも維持される（`patch.dict`はテスト実行の隔離手段であり、production codeの挙動やSecurity Contractには影響しない）。

### 17.2 環境変数にしないもの（固定値として扱う）

```text
OPENAI_IMAGE_MODEL
OPENAI_IMAGE_SIZE
OPENAI_IMAGE_QUALITY
OPENAI_IMAGE_FORMAT
```

**判断根拠**：`model` / `size` / `quality` / `output_format`は、費用・Architecture Riskに直結する設定である（9章ADR-3・ADR-6・ADR-7・ADR-5）。これらを環境変数化すると、Architecture Review・CHANGELOG記録を経ずに運用者が費用構造やモデルの再現性を暗黙に変更できてしまい、「設定項目を増やしすぎるとContractとTest Matrixが不必要に拡大する」というユーザー指示にも反する。将来、運用上の必要性が具体的に生じた時点で、Fast Track候補（Constructor Contract非変更・値のみの拡張）として個別に追加を検討する（42章 Future Extensions）。

### 17.3 Constructorとの関係

`from_env()`は`api_key`と（設定されていれば）`timeout_seconds`のみをConstructorへ渡す。`model` / `size` / `quality` / `output_format`はConstructorのデフォルト値へ委ねる。`.env`ファイルの直接読込（`load_dotenv`等）は行わない（既存`WordPressMediaUploader.from_env()`と同じ制約）。

---

## 18. Prompt Contract

**v6.10.0設計書12章「将来Adapter向けPrompt Contract（今回は未実装）」をそのまま採用する（AD-21）。** これはv6.10.0のArchitecture Review 3で既にApprovedされた文書内で「後続のOpenAI Image Generation Adapter Foundation等、具象Generatorを実装するReleaseが従うべき規約」として明記されている内容であり、本Releaseが新規に定義するものではなく、既存Approved Contractの実装である。

```text
promptはstr型（type(value) is not str → ValueError。str subclassも拒否）
非空（ValueError）
空白のみ不可（ValueError。判定にのみ.strip()を使用し、値そのものは変更しない）
前後空白の自動stripはしない（値をそのままAPIへ渡す。空白のみでない限り前後空白は許可）
NUL文字（\x00）を拒否する（ValueError）
改行（\n）とtab（\t）は許可する
carriage return（\r）を許可する（18.1章、v6.11 Adapter固有の明確化）
NUL・tab・LF・CR以外の制御文字（他のC0制御文字とDEL）を拒否する（ValueError。18.1章、
    v6.11 Adapter固有の追加制約、AD-18・AD-29）
最大長：32000文字を超える場合ValueError（AD-22。10.3節で確認した公式上限値をクライアント側で事前検証し、無駄なAPI呼び出し・費用発生を防ぐ）
Moderation（内容の安全性判定）は行わない（OpenAI側のmoderation=autoデフォルトに委ねる）
著作権・商標判定は行わない
```

### 18.1 NUL以外の制御文字の扱い（Architecture Review 1 Finding M-3反映、案B採用）

v6.10.0の文言は「NUL文字を拒否する」「改行とtabは許可する」の2点のみを明示しており、それ以外の制御文字（`\x01`〜`\x08`、`\x0B`〜`\x1F`、`\x7F`等）や`\r`（CR）については明示的な可否判断を記載していない。

**当初案（Architecture Design初版）**は「v6.10.0で承認済みのContractに文言として存在しない拒否ルールを新規に追加しない」という原則に基づき、NUL以外の制御文字をすべて許可する案（本章では**案A**と呼ぶ）を採用していた。Architecture Review 1（Finding M-3）は、次の比較観点に基づき、**案B（tab・LF・CRのみ許可し、他のC0制御文字とDELは拒否する）**への変更を指摘した。

| 比較観点 | 案A（NULのみ拒否） | 案B（tab／LF／CRのみ許可、**採用**） | 案C（すべての制御文字拒否） |
|---|---|---|---|
| v6.10.0との整合 | 矛盾しない（最も字義通り） | 矛盾しない（v6.10.0はtab／LF許可を明示するのみで、他の制御文字の許可を義務付けていない） | **矛盾する**（v6.10.0はtab／LFを明示的に許可しており、案Cはこれを拒否してしまう） |
| 通常の日本語・英語prompt | 影響なし | 影響なし | 影響なし |
| 複数行prompt | \r\n（Windows改行）を許可 | \r\n（Windows改行）を明示的に許可 | tab／LFも拒否するため複数行prompt自体が使えない |
| 不正入力の早期拒否 | 弱い（未知の制御文字を無条件に通過させる） | **強い**（自然言語promptに現れる正当な理由のない制御文字を拒否し、上流の破損データを検知できる） | 最も強いが複数行prompt自体を破壊する |
| provider挙動 | Provider側の未定義動作に依存 | クライアント側で早期拒否し、Providerの未定義動作への依存を避ける | 同左 |
| ログ禁止Contract | 影響なし | 影響なし | 影響なし |
| 将来のPrompt Builder | 破損データ（バイナリ混入等）を検知せず有償APIへ送信してしまうリスク | **将来のPrompt Builder（42章）が破損データを生成した場合に早期検知できる** | 同左だがtab／LFも使えず実用性がない |
| テスト容易性 | 単純 | 拒否対象範囲（C0制御文字＋DEL、tab／LF／CR除く）のテストケースが必要（許容範囲） | 単純 |

**結論：案Bを採用する（AD-18・AD-29）。** 案Cはv6.10.0のApproved Contract（tab／LF許可）と直接矛盾するため明確に却下する。案Aと案Bはいずれもv6.10.0の文言と矛盾しないが、プロジェクト全体で一貫しているfail-fast・厳密検証の設計思想（`GeneratedImage`の`type(x) is bytes`、`WordPressMediaUploader`のfilename正規表現によるASCII安全文字限定等）との整合、および将来のPrompt Builder（記事本文からのprompt自動生成、42章）に対する防御という観点から、案Bをv6.11 Adapter固有の追加制約として採用する。

**この変更はv6.10.0本体のContractを変更するものではない。** v6.10.0が定めた最小限の必須拒否ルール（NUL拒否・tab／LF許可）はそのまま維持しつつ、v6.11 Adapterが独自の判断でその上に追加の拒否ルール（他のC0制御文字とDELの拒否、およびCRの明示的な許可）を上乗せする構成であり、v6.10.0側の再Reviewは不要と判断する。

### 18.2 例外・ログへの非露出

prompt全文は、`OpenAIImageGenerationError`のメッセージ・`__repr__`・テスト失敗出力へ一切含めない（28章）。

---

## 19. Request Contract

```python
_FIXED_N = 1
_FIXED_BACKGROUND = "opaque"

kwargs = {
    "model": self._model,
    "prompt": prompt,
    "n": _FIXED_N,
    "size": self._size,
    "quality": self._quality,
    "output_format": self._output_format,
    "background": _FIXED_BACKGROUND,
}
response = client.images.generate(**kwargs)
```

### 19.1 明示的に含めないパラメータ

```text
response_format（GPT image系では非サポート。10.3節）
moderation（APIデフォルトautoに委ねる。安易に緩められる設定を公開しない）
stream / partial_images（ストリーミング不使用）
user（エンドユーザー追跡は今回対象外）
style（DALL-E-3専用パラメータ、gpt-image-2には無関係）
output_compression（output_formatがpng既定のため無関係。jpeg/webp選択時もAPI既定値に委ねる。41章Known Issues）
```

### 19.2 Timeout

Timeoutはリクエスト単位ではなく、**Client単位設定**（16.2章の`with_options(timeout=..., max_retries=0)`）に統一する。

**Architecture Review 1 Finding m-1反映**：当初の記載「公式ドキュメントでリクエスト単位Timeout引数の存在を確実に確認できなかった」は事実と異なっていたため訂正する。`openai-python`ソースコード（`src/openai/resources/images.py`）を確認した結果、`client.images.generate()`は`timeout: float | httpx.Timeout | None | NotGiven`というrequest単位のtimeout引数を実際に受け付ける（10.6章）。**request単位timeoutはSDKに存在するが、Client単位の統一設定だけで今回の要件（自動Retryなし・Timeout必須という単一のAdapter全体Contract）を満たせるため不採用とする。** 設定経路を2つ（Client単位・request単位）に分裂させるとContractとTest Matrixが複雑化するため、単一の設定経路（Client単位）に統一する判断は変更しない。

---

## 20. Model Contract

### 20.1 エイリアス vs 固定スナップショット比較

| 観点 | `gpt-image-2`（エイリアス） | `gpt-image-2-2026-04-21`（固定スナップショット、**採用**） |
|---|---|---|
| 再現性 | 低い。OpenAI側の無告知更新により同一promptから異なる画像が生成されうる | 高い。スナップショットが固定される限り挙動が変わらない |
| 将来の自動更新 | あり（利点にも欠点にもなる） | なし（明示的なバージョン切替Releaseが必要） |
| 品質改善の自動反映 | 自動反映される | 反映されない（追従には版上げReleaseが必要） |
| 破壊的挙動変化のリスク | あり（プロンプト解釈・画質・料金体系が無告知で変わりうる） | なし |
| 運用保守性 | 短期的には楽（何もしなくてよい） | 長期的に安全（変化点が明示的） |
| テストへの影響 | E2Eは実HTTPを行わないため直接の影響は小さいが、Architecture Reviewでの「何を承認したか」が曖昧になる | E2Eの前提（固定文字列）が将来にわたり安定する |

**採用：固定スナップショット（AD-5）。** 既存プロジェクト全体の設計思想（`GeneratedImage`の自動変換禁止、`mime_type`の自動小文字化禁止、`from_env()`の暗黙フォールバック禁止等）が一貫して「暗黙の自動変化を避け、変更は明示的なReleaseとして扱う」という方針であることと整合する。

### 20.2 将来のバージョン更新

OpenAIが`gpt-image-2-2026-04-21`を廃止した場合、`_DEFAULT_MODEL`定数値の変更のみで対応可能であり、Public API・Constructor Contractの変更を伴わないため、Fast Track候補になりうる（development_workflow.md 7章の8条件に照らして確認が必要だが、少なくとも「Public API変更」「Constructor変更」には該当しない）。

---

## 21. Size／Quality／Format Contract

### 21.1 Size

```python
_ALLOWED_SIZES = frozenset({
    "1024x1024", "1536x1024", "1024x1536",
    "2048x2048", "2048x1152",
    "3840x2160", "2160x3840",
})
_DEFAULT_SIZE = "1024x1024"
```

`auto`は許可値に含めない（非決定的コストのため、9章ADR-6）。OpenAI側の「16px倍数」「アスペクト比3:1以内」「総ピクセル数範囲」制約は自前で再実装せず、公式ドキュメントに列挙された7値のallowlistのみで検証する（Provider側の数式をクライアント側で二重実装するとバグ・仕様追従漏れのリスクがあるため）。「ゲーム記事のアイキャッチ画像専用にしすぎない」というユーザー指示を踏まえ、デフォルトは最も汎用的で低コストな正方形`1024x1024`とし、横長サイズ（`1536x1024`等）はconstructor引数で明示選択できる形にとどめる（Adapter自体はWordPress・記事用途を特別扱いしない）。

**Provider CapabilityとAdapter Contractの区別（Implementation Finding IMP-DESIGN-1・Architecture Review 4 Finding AR4-m-1反映）**：

```text
Provider Capability（OpenAI側の実際の対応範囲）：
    次の4条件をすべて満たす任意のWIDTHxHEIGHTをサポートする
    （公式ドキュメント確認済み）。
        1. 最大辺が3840px以下
        2. 幅・高さの両方が16pxの倍数
        3. 長辺と短辺の比率が3:1以内
        4. 総ピクセル数が655,360以上8,294,400以下
    （各境界値はいずれも含む：3840px・3:1・655,360・8,294,400はそれぞれ許容範囲内）
    OpenAI自体が「7値しか受け付けない」わけではない。

v6.11.0 Adapter Contract（本Adapterが許可する範囲）：
    Provider Capabilityのうち、公式ドキュメントで代表例として確認できた
    7値のみを閉じたallowlistとして許可する。予測可能性・入力Contractの固定・
    Testability（全許可値を個別Caseとして機械的に列挙・検証できること）を
    優先し、Provider Capabilityの全域（4条件の数式検証）をそのまま公開・
    自前実装しない設計判断である。

auto：
    Provider側のデフォルト値だが、本Adapterでは不採用（9章ADR-6、
    非決定的コストのため）。

任意のcustom WIDTHxHEIGHT（allowlist外の、Provider Capability上は有効な値）：
    本Releaseでは不採用。将来的にProvider Capabilityの全域または一部を
    追加公開する場合は、42章 Future Extensionsのとおり別途Architecture Reviewを
    経て検討する。
```

### 21.2 Quality

```python
_ALLOWED_QUALITIES = frozenset({"low", "medium", "high"})
_DEFAULT_QUALITY = "medium"
```

| quality | 画像品質 | 生成時間 | アイキャッチとしての実用性 | 1記事あたり費用 | 大量生成時の費用 | 失敗時再生成コスト |
|---|---|---|---|---|---|---|
| low | 低い（アーティファクトが視認されうる） | 短い | 記事の第一印象を損なうリスク | 最小 | 最小 | 低い |
| medium | 中程度 | 中程度 | 実用上十分と判断（**採用**） | 中程度 | 中程度 | 中程度 |
| high | 高い | 長い | 最良だが過剰な場合もある | 最大 | 最大（スケール時に顕著） | 高い |
| auto | 不定 | 不定 | 非決定的（**不採用**） | 予測不能 | 予測不能 | 不定 |

`auto`を許可値から除外する理由：Cost Control Contract（30章）が要求する費用の予測可能性・「高額設定を暗黙に使用しない」という指示と矛盾するため。`medium`をデフォルトとし、品質を優先したい記事では呼び出し側が明示的に`quality="high"`を指定する。

### 21.3 Output Format

```python
_ALLOWED_OUTPUT_FORMATS = frozenset({"png", "jpeg", "webp"})
_DEFAULT_OUTPUT_FORMAT = "png"
```

比較：

| 案 | 内容 | 判定 |
|---|---|---|
| PNG固定 | `output_format`を常に`png`に固定 | 却下。将来的にjpeg/webpによる転送量削減の需要が生じうるため、allowlistの方が拡張性が高い |
| format→MIME allowlist mapping | `output_format`をconstructor引数として公開し、固定mapping表でMIME typeへ変換 | **採用** |
| providerレスポンスからMIME推測 | レスポンスの`output_format`フィールドから動的に導出 | 却下（22章） |

デフォルトを`png`とする理由：OpenAI API自体のデフォルトと一致させることで、Adapterが独自の思想でデフォルトを歪めない（「WordPress専用にしすぎない」指示とも整合する、PNGは特定用途に依存しない安全な既定値）。

---

## 22. MIME Type Contract

```python
_MIME_TYPE_BY_OUTPUT_FORMAT = {
    "png": "image/png",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}
```

### 22.1 比較

| 案 | 内容 | 判定 |
|---|---|---|
| PNG固定で`image/png`を返す | `output_format`をpng固定にした場合のみ成立する単純設計 | 却下（21.3章でallowlist化を採用したため不整合） |
| format→MIME allowlist mapping | 自分がリクエストした`output_format`（`self._output_format`）から固定表で導出 | **採用** |
| providerレスポンスから推測 | `response.output_format`（レスポンスエコー）を信頼して使う | 却下 |

**MIME typeは、レスポンスの`output_format`フィールド（10.4節で確認したレスポンスエコー）ではなく、自分がリクエストした`self._output_format`から導出する（AD-19）。** レスポンス側の`output_format`／`quality`／`size`はいずれも読まない・検証しない（41章 Known Issue「response echo未検証」として明記）。これは「providerレスポンスから曖昧に推測する」ことを避けるユーザー指示に対応するための設計であり、"推測"ではなく"自分がリクエストした既知の値からの決定的なmapping"である点が異なる。

`_MIME_TYPE_BY_OUTPUT_FORMAT`は自動小文字化・strip等の補正を一切行わない（`_ALLOWED_OUTPUT_FORMATS`のallowlistで既に正規の3値のみに制限されているため、mapping表のキーは常に一致する）。

---

## 23. Response Contract

### 23.1 Processing Order（固定）

```text
1. Prompt Validation（18章）— Client取得より前に実施
2. Client準備（16.2章、Injectionされていれば再利用、なければ遅延生成）
3. Minimal Images Client Contractの充足確認（16.2章、hasattr(client, "with_options")）。
   不足時はTypeErrorで即座にfail-fast（Provider Failureへは変換しない）
4. with_options(timeout=..., max_retries=0) を経由してClientを取得（16.2章）
5. client.images.generate(**kwargs) 呼び出し（try/exceptで包む）
6. openai.APIError系 → 分類ヘルパーで安全メッセージ・reasonを算出（except節内ではraiseしない、29章）
7. その他のException（SDK内部エラー・未知例外） → reason=UNKNOWNの汎用安全メッセージを算出（同上）
8. except節を抜けた後、安全メッセージが設定されていればraise OpenAIImageGenerationError(msg, reason) from None
9. response構造検証：response自体 → response.data → len(data) == 1 → data[0]（reason=INVALID_RESPONSE）
10. data[0].b64_json 構造検証：str型・非空（reason=INVALID_RESPONSE）
11. base64.b64decode(value, validate=True)（try/exceptで包み、失敗時は同じくexcept節外でraise、reason=INVALID_RESPONSE）
12. decode結果の非空検証（空bytesは OpenAIImageGenerationError・reason=INVALID_RESPONSE、ValueErrorではない。AD-20）
13. MIME type決定（22章、self._output_formatから導出。responseからは導出しない）
14. GeneratedImage(image_bytes=decoded, mime_type=mime_type) 構築・返却
```

### 23.2 Response構造Contract

| フィールド | Contract | reason |
|---|---|---|
| `response` | `None`不可（getattr等で防御的にアクセスし、想定外の型・欠落は`OpenAIImageGenerationError`） | `INVALID_RESPONSE` |
| `response.data` | list型必須。`None`・list以外の型は`OpenAIImageGenerationError` | `INVALID_RESPONSE` |
| `len(response.data)` | `1`のみ許可（`n=1`固定のため）。`0`または`2`以上は`OpenAIImageGenerationError`（Provider側の異常として扱う） | `INVALID_RESPONSE` |
| `response.data[0].b64_json` | str型必須・非空必須。欠落（属性なし）・`None`・str以外は`OpenAIImageGenerationError` | `INVALID_RESPONSE` |

全ての属性アクセスは`getattr(obj, "attr", _MISSING)`のような防御的パターンで行い、生の`AttributeError`をテスト用Fake（`SimpleNamespace`）や将来のSDK変更に対しても一様に`OpenAIImageGenerationError`（`reason=INVALID_RESPONSE`）へ変換する（31章）。

### 23.3 レスポンス起因の異常はすべて`OpenAIImageGenerationError`

`GeneratedImage.__post_init__`が送出する`ValueError`（v6.10.0 Contract）とは意図的に区別する。**呼び出し元にとって「自分が渡したpromptが悪い」（`ValueError`）と「Provider応答が壊れていた」（`OpenAIImageGenerationError`）は異なる意味を持つため、Adapterはこの境界を明示的に管理する。**

---

## 24. Strict Base64 Decode Contract

```python
import base64
import binascii

try:
    decoded = base64.b64decode(b64_value, validate=True)
except (binascii.Error, ValueError):
    error_message = "OpenAI Images APIのレスポンスのBase64データが不正です"
    error_reason = OpenAIImageGenerationErrorReason.INVALID_RESPONSE
else:
    if len(decoded) == 0:
        error_message = "OpenAI Images APIのレスポンスのデコード結果が空でした"
        error_reason = OpenAIImageGenerationErrorReason.INVALID_RESPONSE
    else:
        error_message = None
        error_reason = None
        # 正常系はここでGeneratedImageを構築する
```

### 24.1 異常系一覧と対応

すべて`reason=INVALID_RESPONSE`（25章）に分類する（Architecture Review 1 Finding M-4反映）。

| 異常系 | 対応 |
|---|---|
| `b64_json`が存在しない（属性欠落） | `OpenAIImageGenerationError`（23.2章） |
| `None` | 同上 |
| `str`以外 | 同上 |
| 空文字 | 同上（decode前に明示チェック） |
| 空白だけ | `validate=True`により`binascii.Error` → `OpenAIImageGenerationError` |
| 不正文字 | 同上 |
| padding不正 | 同上 |
| decode結果が空bytes | AD-20：明示チェックで`OpenAIImageGenerationError`（`GeneratedImage`の`ValueError`に委ねない）。**Test Review 1 Finding FIND-4反映：本Caseの検証方法は24.1.1章参照** |
| 複数data要素 | 23.2章（`OpenAIImageGenerationError`） |
| dataが空 | 同上 |
| dataがlistでない | 同上 |
| response自体が不正 | 同上 |

### 24.1.1 「decode結果が空bytes」Caseの特殊性（Test Review 1 Finding FIND-4反映）

**Test Review 1 Finding FIND-4**は、strict Base64 decode（`validate=True`）後の空bytes分岐（AD-20）が、実在する現実的な入力によっては到達不能であることを指摘した。次のとおり確定する。

```text
b64_json が空文字の場合は、Base64 decodeへ到達する前の時点で
    Response Contract（23.2章：「b64_json ... 非空必須」）により拒否される。
    したがって空文字自体はAD-20の分岐に到達しない。

strict decode（base64.b64decode(value, validate=True)）は、非空の入力文字列に
    対して、常に1byte以上のbytesを返すか、例外（binascii.Error）を送出する
    かのいずれかである（すべて全padding文字列"="/"=="/"===" も
    "Leading padding not allowed"として例外送出されることをローカル環境で
    確認済み）。したがって、実在するいかなる非空base64文字列によっても
    AD-20の「decode結果が空bytes」分岐には到達しない。

AD-20は、将来の実装変更（例：strict decodeの挙動変更、あるいは
    base64.b64decode以外のdecode手段への置き換え）や、Python標準ライブラリの
    将来の異常な挙動変化に備えた防御的Contractとして維持する
    （production codeの変更は不要）。
```

このCaseを検証するには、`base64.b64decode`自体を安全にpatchし、有効な非空Base64入力に対して強制的に`b""`を返させる必要がある。

```python
import unittest.mock

_B64DECODE_PATCH_TARGET = "openai_image_generation.openai_image_generator.base64.b64decode"
# production module（src/openai_image_generation/openai_image_generator.py）が
# 24章のとおり `import base64`（モジュール冒頭、openaiとは異なり遅延importする
# 理由がない標準ライブラリ）としている前提のpatch target。
# 仮に実装が `from base64 import b64decode` を採用する場合は、
# "openai_image_generation.openai_image_generator.b64decode" へ変更する必要がある
# （Implementation Plan・Code Reviewで実際のimport形式と一致させること）。


def b64_empty_result_case() -> None:
    with unittest.mock.patch(_B64DECODE_PATCH_TARGET, return_value=b""):
        # 有効な非空base64文字列（例："aGVsbG8="）を持つFake Responseで
        # generate() を呼び出す。patchにより実際のdecode結果は無視され、
        # 常にb""が返る。
        ...
    # 期待：
    #   OpenAIImageGenerationError が送出される
    #   reason は INVALID_RESPONSE
    #   固定messageは24章の文言と一致する
    #   __cause__ is None／__context__ is None（CHAIN-B64、29.2.1章代表Case経由）
```

### 24.2 なぜ`validate=True`か

`base64.b64decode(value, validate=False)`（Python既定）は、Base64アルファベット外の文字を静かに除去してからデコードする寛容な挙動を持つ。これはProvider応答の破損（切り詰め・文字化け）を検出できずに不正な画像バイトを`GeneratedImage`へ渡してしまうリスクがある。`validate=True`はプロジェクト全体の「自動補正をせずfail-fastで拒否する」という一貫方針（`GeneratedImage.mime_type`の非自動小文字化・非自動strip等）と整合する（AD-14）。

### 24.3 Base64全文・decode後bytesの非露出

Base64文字列そのもの、およびdecode後の`bytes`は、いかなる例外メッセージにも含めない。`error_message`は固定文言のみで構成する（28章）。

---

## 25. Error Contract

**Architecture Review 1 Finding M-4反映**：単一例外という構造自体は維持しつつ、秘密情報を含まない安全な`reason`分類（Enum）を追加する。

### 25.1 単一例外＋安全なreason分類（採用）

**メンバー名の比較（継続審議）**：HTTP 400系（`BadRequestError` / `NotFoundError` / `ConflictError` / `UnprocessableEntityError`、Content Policy拒否を含む）をまとめる分類名として、`BAD_REQUEST`（HTTPステータスコード用語をそのまま踏襲）／`REQUEST_REJECTED`（HTTP transportの詳細を暗示しない中立的な表現）／`CLIENT_ERROR`（Adapter自身のバグと紛らわしい）を比較した。**`REQUEST_REJECTED`を採用する**（HTTPの実装詳細を漏らさず、「Providerがこのリクエストを拒否した」という意味を中立的に表現できるため）。`CLIENT_ERROR`はAdapter自身のprogramming errorと誤読されるリスクがあるため不採用とした。Content Policy拒否については、Providerメッセージやresponse bodyを解析しないと安定して判別できないため、専用の`POLICY_REJECTION`は追加せず、`REQUEST_REJECTED`へ含める（過剰な分類の増加を避ける）。

```python
from enum import Enum


class OpenAIImageGenerationErrorReason(Enum):
    """OpenAIImageGenerationErrorの安全な失敗分類。秘密情報・Provider固有の生データは
    一切含まない、固定された分類ラベルのみで構成する。"""
    AUTHENTICATION = "authentication"
    PERMISSION_DENIED = "permission_denied"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    CONNECTION = "connection"
    REQUEST_REJECTED = "request_rejected"
    SERVER_ERROR = "server_error"
    INVALID_RESPONSE = "invalid_response"
    UNKNOWN = "unknown"


class OpenAIImageGenerationError(RuntimeError):
    """OpenAI Images APIとの通信・応答に関する失敗を表す唯一の専用例外。

    reason属性は安全な分類ラベルのみを保持し、Provider例外オブジェクト・
    レスポンス生データ・prompt・API keyのいずれも保持しない（29章）。
    """

    def __init__(self, message: str, reason: OpenAIImageGenerationErrorReason) -> None:
        super().__init__(message)
        self.reason = reason
```

### 25.2 比較（4案、Architecture Review 1 Finding M-4反映で1案追加）

| 案 | 内容 | 判定 |
|---|---|---|
| 単一例外・追加情報なし | `OpenAIImageGenerationError`の1種のみ、分類情報を一切持たない | 却下（Architecture Design初版はこれを採用していたが、Architecture Review 1で変更を指摘された）。`WordPressMediaUploadError`の既存precedentとは一致するが、25.3章の固定メッセージが「型による分岐を前提としない」ことを明言しているため、将来のいかなる消費者（Observability・Retry Runtime統合等）も、認証エラー・Rate Limit・Content Policy拒否・不正レスポンスを安全に区別する手段を一切持てない |
| 単一例外＋安全なreason Enum | `OpenAIImageGenerationError`は1種類のまま、秘密情報を含まない`reason`属性（Enum）を追加する | **採用**。例外の型は1つのままであり、上位層に型分岐（`except`の書き分け）を要求しない。一方でreasonという安全な分類情報を提供することで、将来の消費者が固定メッセージ文字列という脆いパースに頼らずに済む。「将来用の過剰設計を避ける」という指示に対しても、Enum値の追加はConstructor Contract非変更のFast Track候補であり、コストは小さい |
| 単一例外＋retryable bool | `OpenAIImageGenerationError`へ`retryable: bool`属性を追加する | 却下。「今回のReleaseでは自動Retryを実装しない」方針（ADR-13）のもとでは、再試行方針そのものと結合した情報を今から確定させるのは時期尚早。将来Retry Runtime統合時に、実際の再試行ポリシー（Rate LimitとTimeoutで扱いを変えるか等）を踏まえてArchitecture Reviewを経て追加すべき（42章） |
| Provider例外種類ごとに細分化する（4候補） | `RateLimitError` / `AuthenticationError` / `TimeoutError` / `ResponseError`のsubclass化 | 却下。上位層（消費者）が現時点で存在しないため、subclass階層という重い構造を正当化する具体的な理由を示せない。reason Enumという軽量な代替で十分 |

### 25.3 分類・reason・メッセージ（固定・静的文言のみ）

`str(exc)`や`exc.message`等の動的内容は一切メッセージへ含めない（10.5節で確認したとおり、OpenAIのエラーメッセージにはContent Policy違反時にprompt由来の内容が反映されうるため）。`reason`の値も固定Enumメンバーのみであり、Provider由来の動的な値は一切含まない。

| Provider例外 | 固定メッセージ例 | reason |
|---|---|---|
| `openai.AuthenticationError` | "OpenAI APIへの認証に失敗しました" | `AUTHENTICATION` |
| `openai.PermissionDeniedError` | "OpenAI APIへのアクセス権限がありません（Organization Verification等の可能性）" | `PERMISSION_DENIED` |
| `openai.RateLimitError` | "OpenAI APIのレート制限に達しました" | `RATE_LIMIT` |
| `openai.APITimeoutError` | "OpenAI APIへのリクエストがタイムアウトしました" | `TIMEOUT` |
| `openai.APIConnectionError` | "OpenAI APIへの接続に失敗しました" | `CONNECTION` |
| `openai.BadRequestError` | "OpenAI APIへのリクエストが不正です（Content Policy等による生成拒否を含む）" | `REQUEST_REJECTED` |
| `openai.NotFoundError` / `ConflictError` / `UnprocessableEntityError` | "OpenAI APIへのリクエストが受理されませんでした" | `REQUEST_REJECTED` |
| `openai.InternalServerError` | "OpenAI API側でエラーが発生しました" | `SERVER_ERROR` |
| `openai.APIError`（上記以外の`APIError`系） | "OpenAI Images APIの呼び出しに失敗しました" | `UNKNOWN` |
| レスポンス構造異常・Base64異常（23章・24章） | 各章の固定メッセージ | `INVALID_RESPONSE` |
| その他の`Exception`（SDK内部エラー・未知例外） | "OpenAI Images APIの呼び出し中に予期しないエラーが発生しました" | `UNKNOWN` |

すべて`OpenAIImageGenerationError`という同一の型で送出される。**メッセージ文字列は引き続き運用者向けの診断情報であり、型・文字列内容による分岐を前提としない。プログラム的な分岐が必要な場合は`exc.reason`（Enum比較）のみを安全な手段とする。**

この表を実装する`_classify_api_error()`の具体的なisinstance判定順序（`APITimeoutError`を`APIConnectionError`より先に判定する必要がある等）は29.2.1章のとおり（Architecture Review 2 Finding R2-m-1反映）。

---

## 26. Rate Limit Contract

- 自動Retry・sleep・指数Backoffは実装しない（ADR-13）
- `openai.RateLimitError`は25.3章のとおり`OpenAIImageGenerationError`（`reason=RATE_LIMIT`）へ変換する（固定メッセージ、`Retry-After`ヘッダ等の再試行ヒントはこのReleaseでは一切読まない・公開しない）
- 利用Tier推測・月額費用管理・API残高照会は行わない（30章 Cost Control Contractとも整合）
- Rate Limit・Timeoutの再試行責任は、将来の上位層またはRetry Runtimeとの責務整理後に扱う（42章 Future Extensions）
- **Architecture Review 1 Finding B-1反映**：「自動Retryなし」はClient Injection経路（呼び出し側が独自設定のClientを注入した場合）でも保証される。16.2章のとおり、`_get_client()`はClientを返す直前に必ず`with_options(max_retries=0)`を経由させるため、注入されたClientが元々`max_retries`を持っていたとしても、本Adapter経由の呼び出しでは常に無効化される

---

## 27. Timeout Contract

**Architecture Review 2 Finding R2-M-1反映**：本章は以前「`openai.OpenAI(..., timeout=self._timeout_seconds, ...)`としてClient構築時にTimeoutを設定する」という記述を持っていたが、これは16.2章の現行Contract（Client構築時にはtimeoutを渡さず、使用直前に`with_options()`を経由して適用する）と矛盾していた。B-1修正（Architecture Review 1）時に27章への反映が漏れていたために生じた不整合であり、本改訂で16.2章と完全に一致させる。

| 項目 | 決定 |
|---|---|
| OpenAI ClientのTimeout | **Client構築時に直接設定するのではない**。自己生成Clientは`openai.OpenAI(api_key=self._api_key)`（timeoutを渡さない）で準備し、注入Clientはconstructorで受け取ったものをそのまま使用する。**両経路共通で、API使用直前に必ず`client.with_options(timeout=self._timeout_seconds, max_retries=0)`を経由させ**、`with_options()`が返したClientに対して`images.generate()`を呼び出す（16.2章）。`max_retries=0`と同一箇所・同一呼び出しで強制される。`with_options()`は元のClientを破壊的に変更しない（10.6章で確認済み） |
| request単位のTimeout | 採用しない（10.6節・19.2章：SDKに存在することは確認済みだが、設定経路を分裂させないためClient単位設定へ統一する。Architecture Review 1 Finding m-1で記載を訂正） |
| 固定秒数 | デフォルト**180秒**（後述の根拠、Architecture Review 1 Finding M-1反映） |
| constructor引数 | `timeout_seconds: int`（16.1章の検証Contract） |
| 環境変数 | `OPENAI_IMAGE_TIMEOUT_SECONDS`（任意、17.1章） |

### 27.1 デフォルト値の根拠

**Architecture Review 1 Finding M-1反映**：当初のArchitecture Design時点の調査では「公式ドキュメントに画像生成の具体的な所要時間の確定値が記載されていない」としていたが、Architecture Reviewでの再調査により、`developers.openai.com/api/docs/guides/image-generation`に「**Complex prompts may take up to 2 minutes to process**」という記載が存在することが判明した（10.2.1章）。これは重要な公式の目安値であり、当初のデフォルト値（120秒）はこの上限とちょうど同値であった。つまり、複雑なpromptによる正当な生成が、安全マージンゼロの境界でタイムアウトにより打ち切られるリスクを構造的に抱えていた。

次の情報を踏まえ、180秒（公式の目安上限に対し50%のマージン）を採用する。

```text
OpenAI公式ガイド：Complex prompts may take up to 2 minutes to process（＝120秒が公式の目安上限）
OpenAI SDK既定Timeout：600秒（10分、寛容すぎる。ハング検出が遅れる）
既存WordPress系（wordpress_media/wordpress_output）：30秒固定（通常のJSON API・アップロード向けであり、画像"生成"には短すぎる可能性が高い。単純な流用はしない）
```

**180秒は公式の目安上限（2分）に対する安全マージンを加えた値であり、依然として実際の生成時間分布に基づく統計的な検証を経たものではない。** この不確実性があるからこそ、環境変数による運用調整の余地（コード変更なしでの値変更）を残した設計とした（17.1章）。180秒でも不十分と実運用で判明した場合は、Fast Track候補として値のみの調整を検討する（41章 Known Issues）。

### 27.2 禁止事項の遵守

```text
Timeoutなし・無限待機 → timeout_secondsは必須のconstructor引数（デフォルト値ありだが省略不可ではない、常に有効な正の整数が設定される）
不正値の暗黙補正 → 16.1章のとおりfail-fast ValueError
boolをintとして受理 → type(value) is not int による厳密検証でbool（intのsubclass）を除外
NaN／Infinity → int型限定のため構造的に発生しない（float非許可）
0以下 → 16.1章で明示的に拒否
```

---

## 28. Security Contract

### 28.1 例外・ログ・repr・print・テスト結果へ含めないもの（絶対条件）

```text
OPENAI_API_KEY（値そのもの、一部マスクも含め一切出力しない）
Authorization header
prompt全文
b64_json
image_bytes
Base64画像
provider response全体
認証情報
ユーザー固有情報
```

### 28.2 行わないこと

```text
provider例外をそのまま再送出する（25章の分類・固定メッセージ変換を必ず経由する）
provider例外メッセージを文字列結合する（str(exc)を使わない）
response全体をrepr／ログへ出力する
promptをログへ出力する
Base64をログへ出力する
API keyの一部をマスク表示する（マスクであってもAPI key自体を一切出力しない）
```

### 28.3 logging／print Contract

```text
production codeでprintしない
production codeでloggingしない
例外メッセージへprovider情報（動的内容）を入れない
```

v6.9.0・v6.10.0双方の既存Security Contractと完全に一致する方針である。`ClaudeClient`が採用する`print(f"... {e}")`パターンは踏襲しない（4章で明示）。

### 28.4 将来Observability追加時の禁止リスト

将来Observability（Metrics・Logging）を追加する場合も、次は記録禁止として引き継ぐ。

```text
API key
prompt全文
b64_json
image_bytes
provider response全体
Authorization header
個人情報
```

---

## 29. Exception Chaining Contract

### 29.1 `from None`だけでは不十分という発見

ユーザー前提は「`raise SafeError(...) from None`を使用してprovider例外チェーンを抑止するか」を検討事項として挙げていたが、詳細に検討した結果、次の技術的な事実が判明した。

```text
`raise X from None`は X.__cause__ = None、X.__suppress_context__ = True を設定する。
これは既定のTraceback表示（print時のchaining表示）を抑止するが、
X.__context__ 属性自体は、except節の内部でraiseした場合、
Python言語仕様により自動的に「現在処理中の例外」（=元のopenai.APIError等）へ
設定されてしまう。__context__はプログラムから引き続き到達可能であり、
`exc.__context__.request`のようなアクセスで元のProvider例外オブジェクト
（Authorizationヘッダーを含みうる）に到達できてしまう。
```

### 29.2 採用する対策（AD-24）

**except節の内部では`raise`しない。** 安全な固定メッセージ文字列と安全な`reason`（25章、Architecture Review 1 Finding M-4反映）のみをexcept節内で変数へ格納し、except節（したがって例外処理コンテキスト）を抜けたあとで初めて`raise OpenAIImageGenerationError(message, reason) from None`を実行する。`_classify_api_error()`は`(message, reason)`のタプルを返す純粋関数とし、いかなる`raise`も行わない。

```python
def generate(self, prompt: str) -> GeneratedImage:
    _validate_prompt(prompt)  # 18章
    client = self._get_client()  # 16.2章：Minimal Images Client Contract不足時はTypeErrorでfail-fast

    error_message = None
    error_reason = None
    response = None
    try:
        response = client.images.generate(**self._build_kwargs(prompt))
    except openai.APIError as exc:
        error_message, error_reason = _classify_api_error(exc)   # 純粋関数。raiseしない
    except Exception:
        error_message = "OpenAI Images APIの呼び出し中に予期しないエラーが発生しました"
        error_reason = OpenAIImageGenerationErrorReason.UNKNOWN

    if error_message is not None:
        raise OpenAIImageGenerationError(error_message, error_reason) from None

    return _build_generated_image(response)  # 23章・24章の検証を内包（同一パターンでreasonを付与）
```

`except`ブロックを抜けた時点で、Pythonの例外処理コンテキスト（`sys.exc_info()`）は解除されているため、その後の`raise`文には暗黙の`__context__`が設定されない。これにより`__cause__`（`from None`により明示的にNone）・`__context__`（制御フローにより構造的に未設定）の両方から、元のProvider例外オブジェクトへ一切到達できなくなる。

**16.2章のMinimal Images Client Contract不足検出（`TypeError`）はこのtry/except境界の外側（Client準備段階）で行う**ため、`OpenAIImageGenerationError`への変換対象にはならない。これはProvider Failureではなくprogramming／configuration errorであるため、意図的にこのExceptionチェーン安全化パターンの対象外とする（TypeErrorは秘密情報を含まない固定メッセージのみで構成されるため、`__cause__`／`__context__`の安全性については別途懸念しない）。

### 29.2.1 `_classify_api_error()`の判定順序（Architecture Review 2 Finding R2-m-1反映）

`_classify_api_error()`は25.3章のmapping表をそのまま実装した純粋関数であり、**具体的なsubclassから一般的な`openai.APIError`（catch-all）の順に`isinstance()`判定する**。特に`openai.APITimeoutError`は`openai.APIConnectionError`のsubclassである（10.5章の例外階層）ため、`APITimeoutError`を`APIConnectionError`より必ず先に判定しなければ、`APITimeoutError`のインスタンスが誤って`APIConnectionError`の分岐に一致してしまう。

```python
def _classify_api_error(
    exc: "openai.APIError",
) -> tuple[str, OpenAIImageGenerationErrorReason]:
    """openai.APIError系の例外を、固定メッセージとreasonのペアへ分類する純粋関数。

    Providerメッセージ・response body・status codeの生値・prompt断片は
    一切読み取らない。分類は例外の型（isinstance）のみに基づく。
    raiseは行わない（29.2章のclassify-then-raise-outside-exceptパターン）。
    具体的なsubclassから一般的なAPIError（catch-all）の順に判定する。
    """
    if isinstance(exc, openai.AuthenticationError):
        return (
            "OpenAI APIへの認証に失敗しました",
            OpenAIImageGenerationErrorReason.AUTHENTICATION,
        )
    if isinstance(exc, openai.PermissionDeniedError):
        return (
            "OpenAI APIへのアクセス権限がありません（Organization Verification等の可能性）",
            OpenAIImageGenerationErrorReason.PERMISSION_DENIED,
        )
    if isinstance(exc, openai.RateLimitError):
        return (
            "OpenAI APIのレート制限に達しました",
            OpenAIImageGenerationErrorReason.RATE_LIMIT,
        )
    if isinstance(exc, openai.APITimeoutError):
        # APIConnectionErrorのsubclassのため、APIConnectionErrorより先に判定する。
        return (
            "OpenAI APIへのリクエストがタイムアウトしました",
            OpenAIImageGenerationErrorReason.TIMEOUT,
        )
    if isinstance(exc, openai.APIConnectionError):
        return (
            "OpenAI APIへの接続に失敗しました",
            OpenAIImageGenerationErrorReason.CONNECTION,
        )
    if isinstance(exc, (openai.BadRequestError, openai.NotFoundError,
                         openai.ConflictError, openai.UnprocessableEntityError)):
        return (
            "OpenAI APIへのリクエストが不正です（Content Policy等による生成拒否を含む）",
            OpenAIImageGenerationErrorReason.REQUEST_REJECTED,
        )
    if isinstance(exc, openai.InternalServerError):
        return (
            "OpenAI API側でエラーが発生しました",
            OpenAIImageGenerationErrorReason.SERVER_ERROR,
        )

    # openai.APIError（上記のいずれにも一致しないその他のAPIError系）のcatch-allは最後。
    return (
        "OpenAI Images APIの呼び出しに失敗しました",
        OpenAIImageGenerationErrorReason.UNKNOWN,
    )
```

**判定順序の要点**：

```text
具体例外を一般例外より先に判定する（AuthenticationError等 → APITimeoutError →
    APIConnectionError → BadRequestError等 → InternalServerError → APIError catch-all）
APITimeoutErrorはAPIConnectionErrorのsubclassであるため、必ず前者を先に判定する
openai.APIErrorのcatch-all（else節相当の最終return）は判定順序の最後に置く
Providerメッセージ・response body・status codeの生値・prompt断片を分類に一切使わない
固定メッセージ文字列と固定reason Enumのペアだけを返す
_classify_api_error()内ではraiseしない（29.2章のパターンとの整合）
```

この判定順序は25.3章のmapping表、29.2章のProcessing Order（`generate()`の擬似コード）、32.5章のE2E Test Strategyと一致する。

### 29.3 Base64・レスポンス検証への同一パターンの適用

23章・24章のレスポンス構造検証・Base64デコードにおける異常系も、同一の「classify-then-raise-outside-except」パターンで統一する。これにより本Adapter内の例外変換ロジックが単一の一貫した安全パターンに従う。

---

## 30. Cost Control Contract

```text
1回のgenerate()呼び出しでn=1固定（constructor・環境変数いずれからも変更不可、AD-6）
意図しない複数画像生成を構造的に禁止（nがPublic Contractに一切現れない）
失敗時の自動再生成を行わない（Retry Contract 26章と同じ理由）
default quality="medium" ／ default size="1024x1024"：費用と実用性のバランスを取ったデフォルト値（21章で比較表を提示）
高額設定（quality="high"、大サイズ）を暗黙に使用しない：これらはconstructor引数での明示的な呼び出し側の選択によってのみ有効化される
Client Injection経路でも意図しない複数回課金（SDKの暗黙Retryによる二重請求）が発生しない：
    16.2章のwith_options(max_retries=0)強制適用により、注入されたClientが独自のRetry設定を
    持っていた場合でも無効化される（Architecture Review 1 Finding B-1反映）
```

費用に関する固定Architecture Contract・参考料金・将来変動する運用情報の区分は10.8章のとおり。

---

## 31. Testability／Client Injection

### 31.1 比較

| 候補 | 採用可否 | 理由 |
|---|---|---|
| OpenAI Client注入（`client=`引数） | **採用（主軸）** | 16.2章のConstructor Injectionにより、実HTTPを完全に排除できる。SDK Clientはステートフルなオブジェクトであり、`ClaudeClient`の既存precedent（`client=None`）とも一致する |
| `unittest.mock.patch` | 不採用（主軸としない） | `wordpress_media`のE2Eで「Patch targetが不明確」という指摘がTest Review 2で実際に発生した実績があり（`docs/design/wordpress_media_upload_foundation.md` 34章）、Constructor Injectionという代替手段がある以上、文字列ベースのPatch解決に頼る必要がない |
| `MagicMock` | 採用（補助） | Constructor／Normal系シナリオでの「呼び出しパラメータの記録・検証」（`mock_client.images.generate.assert_called_with(...)`）に使用する |
| SDK responseを模した`SimpleNamespace` | 採用（補助） | Response異常系シナリオでは、`MagicMock`の「どんな属性アクセスも別のMagicMockを返してしまう」という寛容さが、`isinstance`/`hasattr`検証の欠陥を覆い隠すリスクがある。`SimpleNamespace`ベースの最小Fake Responseは、意図した属性だけを持つ・持たないを明示的に表現できる |
| production Fake | **不採用** | Fake Client・Fake Responseはテストファイル内にのみ定義し、`src/openai_image_generation/`には一切追加しない（AD-26と同じ理由） |

### 31.2 テストダブルの配置

```text
production：src/openai_image_generation/openai_image_generator.py
    - client=None で注入可能なConstructor Injectionのみを提供する
    - Null Object（NullOpenAIImageGenerator等）は追加しない

test-only：tests/test_e2e_v6_11_0_openai_image_generation_adapter_foundation.py
    - _FakeImagesResource / _FakeOpenAIClient（SimpleNamespaceベース）
    - MagicMockベースの呼び出し記録確認
```

**Architecture Review 1 Finding B-1反映**：`_FakeOpenAIClient`は`with_options(timeout=..., max_retries=...)`を実装し、呼び出された引数を記録できる必要がある（16.2章）。最小実装は次のように、渡された引数を記録したうえで自分自身（または同等のFake）を返すだけでよい。

```python
class _FakeOpenAIClient:
    def __init__(self, images_resource):
        self.images = images_resource
        self.with_options_calls = []  # [(timeout, max_retries), ...] を記録

    def with_options(self, *, timeout=None, max_retries=None):
        self.with_options_calls.append((timeout, max_retries))
        return self
```

これにより、次の2点をE2Eで直接検証できる（32.1章・32.2章に追記）。

```text
Client Injection経路（client=を明示注入）でも with_options(timeout=180, max_retries=0) が
    呼ばれること（180はconstructor引数のtimeout_secondsに連動）
自己生成経路（client省略）でも同様に with_options(...) が呼ばれること
```

**Minimal Images Client Contract不足のFake（16.2章のfail-fast検証用）**：`with_options`を意図的に持たない最小Fakeも用意する。

```python
class _FakeClientWithoutWithOptions:
    def __init__(self, images_resource):
        self.images = images_resource
        # with_options属性を意図的に持たない
```

`OpenAIImageGenerator(api_key="test", client=_FakeClientWithoutWithOptions(...))`で`generate()`を呼び出すと、16.2章のとおり`TypeError`が送出されること（`OpenAIImageGenerationError`ではないこと）をConstructor／Configuration系Scenario（32.2章）で検証する。

### 31.3 Null Object Patternを採用しない理由（AD-26）

`ClaudeClient`は`NullClaudeClient`という設計を持つが、それは`AI_IMPROVEMENT_ENABLED=false`という機能フラグに基づく実際の呼び出し元（`from_env()`の消費者）が既に存在するためである。本Releaseは**Consumer-less Foundation**であり、`generate()`を実際に呼び出す機能フラグ付きComposition Rootが存在しない。したがって、`from_env()`は不足時に`ValueError`を送出するfail-fast設計（`WordPressMediaUploader.from_env()`と同型）を採用し、Null Objectは導入しない。将来Wiring Release（Generated Image → WordPress Media Upload Wiring等）で実際の機能フラグ運用が必要になった時点で、そのReleaseのArchitecture Designとして改めて検討する。

### 31.4 Runtime Guard（実HTTP防止の二重防御、Architecture Review 1 Finding M-5反映）

**Architecture Review 1 Finding M-5**は、実HTTP防止が「Client Injectionにより常にFakeへ差し替える」というテスト作成者の運用上の意図のみに依存しており、これを構造的に強制する仕組みが存在しないことを指摘した。継続審議の指摘を踏まえ、次の二重防御を採用する。

**Guard A（通常Scenarioの原則）**：32章の通常の全`generate()` Scenario（Normal・Prompt・Response・Provider Failure・Security）は、`_FakeOpenAIClient`（31.2章）を`client=`引数へ明示注入する。これはテスト作成者が守るべき原則であり、Guard Bによって構造的に強制される。

**Guard B（Runtime Guard、主防御）**：E2Eファイル全体の実行を、`openai.OpenAI`（`_get_client()`が`import openai`の直後に参照するクラス）をpatchした状態で行う。既定のpatch対象は「呼び出されたら即座に`AssertionError`を送出する」ダミーであり、これによりGuard Aが破られた場合（＝Fake Clientの注入を忘れ、コードが自己生成経路へ入った場合）に、実Clientが構築される前に確実にテストを失敗させる。

```python
import unittest.mock

_PATCH_TARGET = "openai.OpenAI"


def _raise_if_real_client_constructed(**kwargs):
    raise AssertionError(
        "OpenAIImageGenerator attempted to construct a real openai.OpenAI client "
        "during E2E execution. Every Scenario must inject client= explicitly "
        "(Architecture Review 1 Finding M-5)."
    )


# E2Eファイル全体（Normal・Prompt・Response・Provider Failure・Security等の
# 通常Scenario）は、この既定Guardが有効な状態で実行する。
with unittest.mock.patch(_PATCH_TARGET, side_effect=_raise_if_real_client_constructed):
    ...  # 32.1〜32.6章の通常Scenarioをここで実行する
```

**自己生成経路を検証するScenario専用の局所的な差し替え**：「client引数省略時の遅延生成経路の確認」「from_env()正常系」等、意図的に`client=`を省略して自己生成経路（16.2章）そのものを検証するScenarioは、既定のAssertionError版Guardをそのscenarioの実行スコープ内でのみ、安全なFake Constructorへ局所的に上書きする。

```python
class _RecordingFakeOpenAIConstructor:
    """openai.OpenAI(...)の代わりに使う、実Clientを一切生成しない安全なFake。"""

    def __init__(self, fake_client):
        self.calls = []          # [{"api_key": ...}, ...] を記録
        self._fake_client = fake_client

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return self._fake_client  # 実openai.OpenAIは一度も構築されない


# 自己生成経路を検証するScenarioの内部でのみ、次のように局所的に上書きする。
fake_ctor = _RecordingFakeOpenAIConstructor(_FakeOpenAIClient(_FakeImagesResource(...)))
with unittest.mock.patch(_PATCH_TARGET, side_effect=fake_ctor):
    generator = OpenAIImageGenerator(api_key="test-api-key", client=None)
    generator.generate("正常なprompt")
    # fake_ctor.calls を検証し、api_key等が期待どおり渡されたことを確認する
```

**設計書へ明記する必須事項（継続審議の指摘に対応）**：

```text
patch target：           openai.OpenAI（_get_client()が参照するクラスと同一）
Guardの有効範囲：         E2Eファイル全体（既定：AssertionError版）。自己生成経路を
                          検証するScenarioのみ、そのScenarioの実行スコープに限定して
                          安全なFake Constructor版へ局所的に上書きする
AssertionError条件：      既定Guardが有効な状態で openai.OpenAI(...) が実際に
                          呼び出された場合（＝Fake Client注入を忘れた場合）
Fake経路を妨げないこと：  client=に_FakeOpenAIClientを注入するScenarioは
                          _get_client()の「if self._client is None」分岐へ
                          到達しないため、Guardの対象外であり一切妨げられない
patch解除方法：           unittest.mock.patchのwithブロックによる自動解除
                          （Python標準機能、明示的なteardown処理は不要）
実API keyを使わないこと： すべてのScenarioでAPI keyは"test-api-key"等の明示的な
                          ダミー値のみを使用する
実networkへ到達しないこと：Guard Bにより、たとえコードパスが誤って自己生成経路へ
                          入っても、本物のopenai.OpenAIが構築されることは
                          構造的にないため、実Client不在のまま実HTTPには到達しない
```

**AST自己検査（補助防御）**：32.7章のDependency（AST）と同様のAST解析手法を用い、E2Eファイル自身の構文木を解析して、`OpenAIImageGenerator(...)`の呼び出し箇所が原則として`client=`キーワード引数を伴っていることを静的に確認する（Guard Bの対象外である、意図的な自己生成経路検証Scenarioは除外リストで明示する）。これはGuard Bの代替ではなく、テストコード自体の可読性・意図の明確化を補助する第二の検査である（AD-31）。

### 31.5 GUARD-SELFTEST・GUARD-PATCH-RESTORE（Runtime Guard自己検証、Test Review 1 Finding FIND-3反映、Test Review 2 Finding TR2-M-1反映）

**Test Review 1 Finding FIND-3**は、Guard B自体が「意図的に呼び出せば実際に`AssertionError`を送出する」ことを直接検証するメタScenarioが存在しないことを指摘した。この対応として追加した`GUARD-SELFTEST`のみが32.10章のGUARDカテゴリ（Scenario数2）に対しID付きで存在しておらず、2件目のScenarioの目的・操作・期待値が追跡できないという指摘を**Test Review 2 Finding TR2-M-1**が受けた。本章は次の2件のScenarioをそれぞれ独立したIDで確定する。

```text
GUARD-SELFTEST：
    Runtime Guard（31.4章 Guard B）が、意図的な呼び出しに対して
    実際にAssertionErrorを送出することを直接検証する

GUARD-PATCH-RESTORE：
    Runtime GuardのpatchがScenario終了後に残留せず、
    openai.OpenAIが元のconstructorへ確実に復元されることを検証する
```

#### 31.5.1 GUARD-SELFTEST

```text
Scenario ID：GUARD-SELFTEST

目的：Runtime Guardが、openai.OpenAIの構築試行を実際に遮断し、
     固定した AssertionError を送出することを直接検証する
前提：既定のAssertionError版Guard（31.4章、_raise_if_real_client_constructed）を
     withブロックで適用済み
操作：patch適用スコープ内で、_get_client()を経由せず、
     openai.OpenAI(api_key="test-api-key") を直接呼び出す
期待：
    1. AssertionError が送出される（例外型の一致）
    2. 送出された例外のmessageが、31.4章 _raise_if_real_client_constructed()の
       固定messageと一致する（message内容の一致）
    実OpenAI Clientを一切生成しない
    実API keyを使わない（"test-api-key"等のダミー値のみ）
    実networkへ到達しない
```

```python
import unittest.mock
import openai

_PATCH_TARGET = "openai.OpenAI"


def guard_selftest() -> None:
    with unittest.mock.patch(
        _PATCH_TARGET, side_effect=_raise_if_real_client_constructed
    ):
        raised_type = None
        raised_message = None
        try:
            openai.OpenAI(api_key="test-api-key")
        except AssertionError as exc:
            raised_type = type(exc)
            raised_message = str(exc)
        # Assertion 1: 例外型が AssertionError であること
        assert raised_type is AssertionError
        # Assertion 2: messageが _raise_if_real_client_constructed() の固定messageと一致すること
        assert raised_message == (
            "OpenAIImageGenerator attempted to construct a real openai.OpenAI client "
            "during E2E execution. Every Scenario must inject client= explicitly "
            "(Architecture Review 1 Finding M-5)."
        )
    # withブロックを抜けた時点でpatchは自動解除される（Python標準機能）。
```

**重要事項（継続審議の指摘に対応）**：

```text
patchを適用してから意図的呼び出しを行う（patch前にopenai.OpenAIを呼ばない）
呼び出しに使うapi_keyは"test-api-key"等のダミー値のみ（実API keyを使わない）
withブロックにより、GUARD-SELFTEST自身の実行後もpatchは自動解除される
このScenarioはopenai.OpenAI(...)を直接呼び出す唯一の意図的なScenarioであり、
    実際にはpatch済みのダミーが呼ばれるだけであるため、実Clientは一切構築されず、
    実networkへも到達しない
```

**Assertion数え方（Test Review 2 Finding TR2-M-1反映）**：32.5.1章のERR-*マトリクスは「例外型」「reason」「message」「marker非露出」を別Assertionとして数えており、本設計書全体で例外型と例外messageは別Assertionとして扱う一貫方針を既に採用している。GUARD-SELFTESTもこの方針に合わせ、**例外型の一致（Assertion 1）とmessageの一致（Assertion 2）を別Assertionとして数える（1 Scenario／1 Case／2 Assertion）**。`check_raises_value_error()`（既存precedent、`tests/test_e2e_v6_10_0_ai_image_generation_contract_foundation.py` 70行）が型確認のみを1 Assertionとするのは、当該precedentがmessage内容そのものを検証していないためであり、message内容を独立した安全Contract（25.3章の固定文言等）として検証する箇所では、本設計書は一貫して型とmessageを分離してきた（32.5.1章）。GUARD-SELFTESTのmessageは秘密情報を含まない固定診断文字列であるため28章と矛盾しない。

#### 31.5.2 GUARD-PATCH-RESTORE

```text
Scenario ID：GUARD-PATCH-RESTORE

目的：Runtime GuardのpatchがScenario終了後に残留せず、
     後続Scenarioへ影響しないことを検証する
前提：修正前のopenai.OpenAIへの参照（original_constructor）を
     withブロック開始前に保持しておく
操作：GUARD-SELFTESTと同一のAssertionError版Guardをwithブロックで適用し、
     ブロック内ではconstructorの参照（identity）のみを取得する
     （このScenarioはwithブロック内でopenai.OpenAI(...)を実際に呼び出さない。
     呼び出すとGUARD-SELFTESTと同じくAssertionErrorが送出されてしまい、
     patch解除の検証という本Scenarioの目的から外れるため）
期待：withブロック終了後、openai.OpenAI is original_constructor が成立する
     （patchがwithブロックの外へ残留していないことのidentity比較による直接証明）
     実OpenAI Clientを一切呼び出さない
     実API keyを読まない
     実networkへ到達しない
```

```python
import unittest.mock
import openai

_PATCH_TARGET = "openai.OpenAI"


def guard_patch_restore() -> None:
    original_constructor = openai.OpenAI

    with unittest.mock.patch(
        _PATCH_TARGET, side_effect=_raise_if_real_client_constructed
    ):
        patched_constructor = openai.OpenAI
        # このスコープ内ではopenai.OpenAI(...)を実際に呼び出さない。
        # identity（is比較）のみを取得する。

    restored_constructor = openai.OpenAI
    # Assertion: withブロック終了後、元のconstructorへ復元されていること
    assert restored_constructor is original_constructor
    # 補助確認（Assertionとしては数えない）：
    # withブロック内では patched_constructor is not original_constructor
    # であることが前提だが、これはpatchライブラリの標準保証であり、
    # 本Adapter固有のContractではないため独立Assertionにはしない。
```

**Assertion数え方**：GUARD-PATCH-RESTOREは「patch解除後にconstructorが復元されていること」というidentity比較1点のみを本Adapter固有のContractとして検証する（**1 Scenario／1 Case／1 Assertion**）。withブロック内でのpatch適用自体（`patched_constructor is not original_constructor`）は`unittest.mock.patch`という標準ライブラリ自体の保証であり、本Adapterのプログラミング・configuration上のContractではないため、独立Assertionとして数えない（32.8章末尾の「テスト数を水増しせず、Contractの分岐と1:1対応させる」という方針と整合する）。GUARDカテゴリの正式カウントは31.5.3章および32.10章を参照する。

#### 31.5.3 GUARDカテゴリの正式カウント

```text
GUARD-SELFTEST：      1 Scenario／1 Case／2 Assertion（例外型・message、31.5.1章）
GUARD-PATCH-RESTORE： 1 Scenario／1 Case／1 Assertion（identity復元、31.5.2章）

GUARDカテゴリ合計：    2 Scenario／2 Case／3 Assertion
```

この2件のScenarioは31章のTest Double戦略に追加され、Scenario／Case／Assertion集計（32.10章）へ反映済みである。

### 31.6 Provider例外Fake構築Helper（Test Review 1 Finding FIND-1反映）

**Test Review 1 Finding FIND-1**は、32.5章のProvider Failure Scenario（`openai.AuthenticationError`等）を実行するために必要な「Fake Provider例外オブジェクトの構築方法」が設計書に存在しないことを指摘した。`openai-python`公式ソース（`src/openai/_exceptions.py`、採用version範囲`openai>=2.46.0,<3.0.0`）を直接確認し、次のとおり確定する。

#### 31.6.1 確認済みConstructor signature（公式ソース、推測なし）

```python
# OpenAIError(Exception)：独自の__init__を持たない（Exception標準実装）

# APIError(OpenAIError)
def __init__(self, message: str, request: httpx.Request, *, body: object | None) -> None:
    ...
    # message・requestは位置引数、bodyはキーワード専用
    # self.request / self.message / self.body / self.code / self.param / self.type を設定

# APIStatusError(APIError)
def __init__(self, message: str, *, response: httpx.Response, body: object | None) -> None:
    ...
    # message・response・bodyすべてキーワード専用（selfを除く）
    # 内部で super().__init__(message, response.request, body=body) を呼ぶため、
    # response.request が設定されていないと構築時にRuntimeErrorになる
    # self.response / self.status_code(=response.status_code) / self.request_id を設定

# BadRequestError / AuthenticationError / PermissionDeniedError / NotFoundError /
# ConflictError / UnprocessableEntityError / RateLimitError / InternalServerError
#     いずれもAPIStatusErrorのsubclassで独自__init__を持たない
#     （status_code: Literal[...] というクラス変数のみを持ち、APIStatusErrorの
#      __init__をそのまま継承する）

# APIConnectionError(APIError)
def __init__(self, *, message: str = "Connection error.", request: httpx.Request) -> None:
    ...
    # message・requestともキーワード専用。messageは既定値あり

# APITimeoutError(APIConnectionError)
def __init__(self, request: httpx.Request) -> None:
    ...
    # requestのみを受け付ける（位置引数）。messageパラメータは存在せず、
    # 内部で super().__init__(message="Request timed out.", request=request) に固定される
```

**重要な確認事項（ユーザー前提の問いへの回答）**：`AuthenticationError`等のサブクラスは`status_code: Literal[401]`のようなクラス変数を型注釈として持つが、これは静的型情報にすぎない。**直接constructorを呼び出す場合、`response`引数に埋め込んだ`status_code`の実際の値が、どの例外クラスがインスタンス化されるかに一切影響しない**（クラスの識別は呼び出したconstructor自体で確定する）。したがって、Fake構築時に渡す`httpx.Response`の`status_code`は診断上の一貫性のために正しい値（下記表）を用いるが、これが誤っていてもテストの正しさには影響しない。この点はSDK内部に「responseのstatus_codeを見て別クラスへ自動変換する」仕組みが存在しないことを意味し、直接constructor呼び出し方式の安全性を裏付ける。

#### 31.6.2 httpx Test-only Dependency Contract

```text
httpxは openai>=2.46.0,<3.0.0 のコア必須依存（pyproject.toml dependencies：
    "httpx>=0.23.0, <1"）であり、requirements.txtへhttpxを追加インストールしなくても、
    openaiのインストールによって自動的に利用可能になることをPyPI公式ページで確認済み

httpxはE2E Test Helper（tests/test_e2e_v6_11_0_openai_image_generation_adapter_foundation.py）
    内でのみimportする

src/openai_image_generation/（openai_image_generator.py・__init__.py）からは
    httpxを一切importしない（13章 Dependency Direction・32.7章 Dependency（AST）の
    禁止対象へhttpxを追加する必要はない。production codeはhttpxへ依存しないため）

requirements.txtへhttpxを直接追加しない（transitive dependencyとして扱う）

httpx.Request／httpx.Responseの構築はいずれもオブジェクト生成のみであり、実HTTP通信を
    一切発生させない（httpxがネットワークI/Oを行うのはClient経由でのsend()実行時のみで
    あり、Request／Responseオブジェクト単体の構築はデータクラス相当の操作にとどまる）
```

この扱いは既存Dependency Contract（13章）と矛盾しない。**Blocking Open Questionには該当しない。**

#### 31.6.3 Helper擬似コード

```python
import httpx
import openai


_TEST_URL = "https://example.invalid/v1/images/generations"


def _make_request() -> httpx.Request:
    """Fake Provider例外構築専用のhttpx.Request。オブジェクト生成のみであり
    実HTTP通信は発生しない。"""
    return httpx.Request(
        "POST",
        _TEST_URL,
        headers={"Authorization": "Bearer authorization-secret-marker"},
    )


def _make_api_status_error(error_type, *, status_code: int, message: str = "provider-secret-marker"):
    """APIStatusError系（AuthenticationError等8種）共通のFake構築Helper。
    error_type: openai.AuthenticationError 等、APIStatusErrorのsubclassを渡す。
    response.request が必須（APIStatusError.__init__内部でresponse.requestへ
    アクセスするため、未設定だとRuntimeErrorになる）。
    """
    response = httpx.Response(
        status_code,
        request=_make_request(),
        json={"error": {"message": "response-secret-marker"}},
    )
    return error_type(
        message,
        response=response,
        body={"error": {"message": "body-secret-marker"}},
    )


def _make_connection_error() -> "openai.APIConnectionError":
    return openai.APIConnectionError(
        message="connection-secret-marker",
        request=_make_request(),
    )


def _make_timeout_error() -> "openai.APITimeoutError":
    # APITimeoutError.__init__(self, request) はrequestのみを受け付ける。
    # messageパラメータは存在せず、SDK内部で"Request timed out."に固定される
    # （31.6.1章参照）。marker注入は request 側のヘッダーのみで行う。
    return openai.APITimeoutError(_make_request())


def _make_generic_api_error() -> "openai.APIError":
    # APIError.__init__(self, message, request, *, body)。message・requestは位置引数。
    return openai.APIError(
        "generic-secret-marker",
        _make_request(),
        body={"error": "body-secret-marker"},
    )
```

#### 31.6.4 Status code対応表

| Provider例外 | status_code | 備考 |
|---|---|---|
| `AuthenticationError` | 401 | |
| `PermissionDeniedError` | 403 | |
| `RateLimitError` | 429 | |
| `BadRequestError` | 400 | |
| `NotFoundError` | 404 | |
| `ConflictError` | 409 | |
| `UnprocessableEntityError` | 422 | |
| `InternalServerError` | 500 | |

31.6.1章で確認したとおり、この対応はconstructor呼び出しの正しさに影響しない診断上の一貫性のためのものである。

#### 31.6.5 Security Marker Contract

Fake例外へ意図的に埋め込むmarker文字列：

```text
provider-secret-marker（Provider例外自体のmessage）
response-secret-marker（httpx.Responseのjson body）
body-secret-marker（openai例外のbody引数）
authorization-secret-marker（httpx.RequestのAuthorizationヘッダー）
connection-secret-marker（APIConnectionErrorのmessage）
generic-secret-marker（APIErrorのmessage）
```

これらに加え、MSG系Scenario（32.6章）では次のmarkerも使用する。

```text
prompt-secret-marker（generate()呼び出し時のprompt自体に混入させるmarker）
api-key-secret-marker（Constructor呼び出し時のapi_key自体に混入させるmarker）
```

変換後の`OpenAIImageGenerationError`について、次のいずれからもmarkerへ到達できないことを確認する。

```text
str(error)
repr(error)
error.args
error.__dict__
error.__cause__
error.__context__
```

ただし、固定された安全なmessage（25.3章の固定文言）と`reason`（Enum値）自体は`error.args`・`str(error)`に含まれてよい（これらはSecret Markerではなく、25章で確定した安全な固定Contractの一部である）。この区別を明確にするため、marker非露出の確認は「markerという特定の文字列が含まれないこと」を検証するものであり、「例外に一切情報が含まれないこと」を意味しない。

---

## 32. E2E Test Strategy

詳細なScenario／Case／Assertion数の確定はTest Design（別工程）で行う。本章では検証すべきカテゴリと代表的なシナリオ名のみを記録する（v6.9.0・v6.10.0の「概要のみ記載し、まだtestは作成しない」という既存precedentを踏襲）。

### 32.1 Normal（正常系）

```text
正しいpromptでgenerate()が呼び出せる
OpenAI Clientへ正しいparameterが渡る（model / prompt / n=1 / size / quality / output_format / background=opaque）
response_format・moderation・stream等の未使用パラメータがkwargsに含まれないことの確認
client引数を明示注入した場合に with_options(timeout=timeout_seconds, max_retries=0) が
    呼ばれること（Architecture Review 1 Finding B-1反映、注入Client経路でも
    Retry／Timeout保証が及ぶことの直接検証）
client引数省略（自己生成）の場合も同様に with_options(timeout=timeout_seconds, max_retries=0)
    が呼ばれること
採用model（デフォルトのスナップショット文字列）が渡ることの確認
採用size／quality／output_formatのデフォルト値が渡ることの確認
constructor引数でsize／quality／output_formatを上書きした場合に上書き値が渡ることの確認
b64_jsonをstrict decodeしGeneratedImageが得られる
GeneratedImage.image_bytesがtype(...) is bytesであること
GeneratedImage.mime_typeがcanonical MIME（allowlist mapping経由）であること
ファイルI/O（open）が一切発生しないこと
```

### 32.2 Constructor／Configuration

```text
api_key未設定（空文字・空白のみ・str以外）
model不正（str以外・空文字）
size不正（allowlist外の値）
quality不正（allowlist外の値、autoを含む）
output_format不正（allowlist外の値）
timeout_seconds不正（0・負数・str・None）
bool timeout拒否（timeout_seconds=Trueを明示的に拒否）
client引数省略時の遅延生成経路の確認（実際にはFake経由、実HTTPなし）
client引数がwith_options()を実装していない場合にTypeErrorが送出されること
    （OpenAIImageGenerationErrorではないこと。Architecture Review 1 継続審議反映、16.2章）
from_env()正常（OPENAI_API_KEY設定済み、OPENAI_IMAGE_TIMEOUT_SECONDS未設定／設定済み）
from_env()異常（OPENAI_API_KEY未設定、OPENAI_IMAGE_TIMEOUT_SECONDSが不正な文字列・0以下）
```

### 32.3 Prompt

```text
str以外（int・None等）
str subclass（type() is str チェックによる拒否確認）
空文字
空白のみ
前後空白を含むが拒否されない正常系
改行（LF）を含む正常系
tabを含む正常系
carriage return（CR、\r\n形式の複数行を含む）を含む正常系（Architecture Review 1
    Finding M-3反映）
NUL文字を含む場合の拒否
NUL・tab・LF・CR以外のC0制御文字（例：\x01、\x1F）を含む場合の拒否（Architecture
    Review 1 Finding M-3反映、案B）
DEL（\x7F）を含む場合の拒否（同上）
32000文字を超える場合の拒否
32000文字ちょうどの境界値
正常な日本語prompt
正常な英語prompt
```

最終的に許可・拒否されるケースは18章のContractと一致させる。

### 32.4 Response

```text
response自体がNone・不正型
response.data欠落
data=None
data空（[]）
dataがlist以外
要素なし（0件、data=[]と同義だが明示的に確認）
複数要素（2件以上）
b64_json欠落（属性なし）
b64_json=None
b64_jsonがstr以外
空Base64（空文字）
不正Base64文字
padding不正
decode結果が空bytes
正常PNG bytes（strict decode成功、非空）
```

上記の異常系はいずれも`OpenAIImageGenerationError`かつ`reason=INVALID_RESPONSE`であることを確認する（Architecture Review 1 Finding M-4反映、23章・24章・25章）。

### 32.5 Provider Failure

```text
openai.AuthenticationError            → reason=AUTHENTICATION
openai.PermissionDeniedError          → reason=PERMISSION_DENIED
openai.RateLimitError                 → reason=RATE_LIMIT
openai.APITimeoutError                → reason=TIMEOUT
openai.APIConnectionError             → reason=CONNECTION
openai.BadRequestError（Content Policy拒否を含む想定） → reason=REQUEST_REJECTED
openai.NotFoundError／ConflictError／UnprocessableEntityError → reason=REQUEST_REJECTED
openai.InternalServerError            → reason=SERVER_ERROR
openai.APIError（上記以外のAPIError系） → reason=UNKNOWN
未知のException（SDK内部エラー相当）    → reason=UNKNOWN
```

いずれも`OpenAIImageGenerationError`という同一型で送出されることを確認する（25章、Architecture Review 1 Finding M-4反映）。具体的な例外から一般的な例外の順にcatchすること（`AuthenticationError`等の具体的subclassを`APIError`より先に判定すること）も確認する。**特に`APITimeoutError`は`APIConnectionError`のsubclassであるため、`APITimeoutError`のインスタンスが誤って`APIConnectionError`（`reason=CONNECTION`）の分岐に一致しないこと（正しく`reason=TIMEOUT`になること）を明示的に検証するScenarioを含める**（Architecture Review 2 Finding R2-m-1反映、`_classify_api_error()`の判定順序は29.2.1章）。

#### 32.5.1 Provider例外Scenario Matrix（Test Review 1 Finding FIND-1反映）

31.6章のFake構築Helperを用いた正式なScenario Matrixを次のとおり確定する。

| Scenario ID | Provider例外 | 構築方式（31.6章） | status_code | expected reason |
|---|---|---|---|---|
| ERR-AUTH | `AuthenticationError` | `_make_api_status_error` | 401 | `AUTHENTICATION` |
| ERR-PERM | `PermissionDeniedError` | `_make_api_status_error` | 403 | `PERMISSION_DENIED` |
| ERR-RATE | `RateLimitError` | `_make_api_status_error` | 429 | `RATE_LIMIT` |
| ERR-TIMEOUT | `APITimeoutError` | `_make_timeout_error` | — | `TIMEOUT` |
| ERR-CONN | `APIConnectionError` | `_make_connection_error` | — | `CONNECTION` |
| ERR-BADREQ | `BadRequestError` | `_make_api_status_error` | 400 | `REQUEST_REJECTED` |
| ERR-NOTFOUND | `NotFoundError` | `_make_api_status_error` | 404 | `REQUEST_REJECTED` |
| ERR-CONFLICT | `ConflictError` | `_make_api_status_error` | 409 | `REQUEST_REJECTED` |
| ERR-UNPROCESSABLE | `UnprocessableEntityError` | `_make_api_status_error` | 422 | `REQUEST_REJECTED` |
| ERR-SERVER | `InternalServerError` | `_make_api_status_error` | 500 | `SERVER_ERROR` |
| ERR-GENERIC | その他`APIError` | `_make_generic_api_error` | — | `UNKNOWN` |
| ERR-UNKNOWN-EXC | その他`Exception`（例：`RuntimeError("unexpected-marker")`） | 直接構築（SDK外の任意例外） | — | `UNKNOWN` |
| ERR-TIMEOUT-NOT-ABSORBED | `APITimeoutError`（差分確認専用） | `_make_timeout_error` | — | `TIMEOUT`（`CONNECTION`ではないことを明示確認） |

**同じreasonへmappingされる複数例外（`BadRequestError`／`NotFoundError`／`ConflictError`／`UnprocessableEntityError`が全て`REQUEST_REJECTED`）も、継承関係・constructor・status_codeが異なるため、個別Scenarioとして維持する**（1つの代表例に統合しない）。

各Case（ERR-TIMEOUT-NOT-ABSORBEDを除く12件）で、次を別Assertionとして確認する（原則6 Assertion／Case）。

```text
1. 例外型が OpenAIImageGenerationError であること
2. reason が期待Enumメンバーと一致すること
3. message が25.3章の固定文言と一致すること
4. exc.__cause__ is None であること
5. exc.__context__ is None であること
6. 31.6.5章のmarker（provider-secret-marker等）が str(exc)／repr(exc)／
   exc.args／exc.__dict__ のいずれにも含まれないこと
```

ただし4・5（`__cause__`／`__context__`確認）は、29.2章の制御フローが全Provider例外経路で完全に同一（`classify-then-raise-outside-except`）であるため、**代表4カテゴリ（CHAIN-APIERROR・CHAIN-OTHEREXC・CHAIN-B64・CHAIN-RESP）でのみ実施し、ERR-*の12 Caseでは type・reason・message・marker非露出の4 Assertionのみとする**（同一制御フローを12回重複検証することを避けるための意図的な設計判断。例外分類・制御フロー自体は29.2.1章、CHAIN代表4カテゴリの命名とカウント根拠は32.10章を参照）。ERR-TIMEOUT-NOT-ABSORBEDは`reason`が`CONNECTION`ではなく`TIMEOUT`であることのみを確認する1 Assertion Caseとする。

### 32.6 Security

```text
例外メッセージにAPI keyが含まれない
例外メッセージにprompt全文が含まれない
例外メッセージにBase64が含まれない
例外メッセージにimage bytesが含まれない
例外メッセージにprovider response全体が含まれない
OpenAIImageGeneratorのreprに秘密情報が含まれない（object既定reprの確認）
例外の__cause__がNoneであること
例外の__context__がNoneであること（29章の制御フローの効果を直接検証する重要なCase）
exc.reasonがOpenAIImageGenerationErrorReasonの固定メンバーのいずれかであり、
    Provider由来の動的な値（文字列結合等）を含まないこと（Architecture Review 1
    Finding M-4反映、25章）
Minimal Images Client Contract不足時のTypeErrorメッセージにAPI key・prompt等の
    秘密情報が含まれないこと（16.2章）
printが一切呼ばれないこと
loggingがimportされていないこと
```

### 32.7 Dependency（AST）

```text
標準ライブラリ + ai_image_generation + openai 以外への絶対importがないこと
wordpress_media / outputs / image_resolver / ArticleData / Workflow / Scheduler / Retry Runtime
    / anthropic / PIL / Pillow / requests へ依存しないこと
ai_image_generation からは GeneratedImage のみをimportし、AIImageGeneratorをimportしないこと（15章）
```

### 32.8 Side Effect（AST／実行時）

```text
open()呼び出しがないこと（AST）
print()呼び出しがないこと（AST）
loggingのimportがないこと（AST）
subprocessのimportがないこと（AST）
sleep（time.sleepを含む）のimportまたは呼び出しがないこと（AST）
実HTTPが発生しないこと（31.4章 Runtime Guard：openai.OpenAIをpatchし、無許可の
    実Client構築をAssertionErrorで即座に検出する二重防御。テスト作成者の注意力のみに
    依存しない構造的保証。Architecture Review 1 Finding M-5反映）
環境変数の変更がテスト前後で復元されること（`patch.dict(os.environ, {...}, clear=True)`
    による隔離・自動復元。Test Review 1 Finding FIND-5反映、17.1.1章）
```

**次の3点は別Contractであり、個別Assertionとして区別して検証する（Test Review 1指摘反映）**：

```text
n=1：kwargs（19章）にn=1が含まれることの確認（REQ-KWARGS-EXACT、32.1章）
images.generate()の呼び出し回数が1回であること：Fake Images Resourceの呼び出し
    記録（call_count等）が1であることの確認。内部retryループが存在しないことの
    直接的な証拠であり、n=1（送信するnパラメータの値）ともmax_retries=0
    （SDK自体の暗黙Retry無効化）とも異なる、Adapter自身のロジックに関する
    独立したContract
max_retries=0：with_options(max_retries=0)がClient使用直前に呼ばれることの確認
    （16.2章、CLIENT-*）
```

Backoff・sleepの不在はAST検証（`time.sleep`等のimportなし）で保証され、実行時の待機時間を計測する必要はない。

テスト数を水増しせず、18章〜30章で確定したContractの分岐と1:1対応させる（Contractに存在しない分岐のテストを追加しない）。

### 32.9 Regression Test Strategy（Test Review 1 Finding FIND-2反映）

**Test Review 1 Finding FIND-2**は、v6.9.0・v6.10.0の設計書には存在した「Regression Test Strategy」章が本設計書に存在せず、既存Regressionの明示的なベースライン数値が欠落していることを指摘した。`docs/CHANGELOG.md`（v6.10.0エントリ、424〜426行）を根拠文書として確認し、次のとおり確定する。

```text
既存Regression対象：v1.11.0〜v6.10.0
既存Regressionベースライン：1592/1592 PASS
    （内訳：v1.11.0〜v6.9.0 1514/1514 PASS ＋ v6.10.0新規E2E 78/78 PASS）
```

このベースラインは推測ではなく、`docs/CHANGELOG.md`のv6.10.0 Testedセクション（「新規E2E（78）＋Regression（1514）＝1592/1592 PASS」）に記載された正式な記録から特定した。

#### 32.9.1 Regression Contract

```text
1. 新規v6.11.0 E2E（tests/test_e2e_v6_11_0_openai_image_generation_adapter_foundation.py）を
   最初に単独実行する
2. 新規E2Eが全件PASSしない限り、既存Regressionの実行結果は本Releaseの合否判定に
   用いない（新規E2Eの失敗を既存Regressionの実行で覆い隠さないため）
3. 新規E2Eが全件PASSしたのち、既存Regression（v1.11.0〜v6.10.0）を実行する
4. 既存Regressionは1592/1592 PASSを維持しなければならない。1件でも失敗・エラー・
   終了コード非0が発生した場合、Releaseは不可とする
5. 全Suiteについて、終了コード0・意図しないstderr／stdout出力なし・Tracebackなし
   であることを確認する（v6.9.0・v6.10.0と同じ確認観点）
```

#### 32.9.2 Regression実行対象

v6.9.0・v6.10.0の設計書・CHANGELOG.mdには、既存Regressionを一括実行する専用Runner／scriptの存在は確認できなかった（`projects/03_game_content_ai/tests/`配下の個別`test_e2e_v*.py`ファイルを順次実行する運用を、v1.11.0以降の全Release（本文書執筆時点でCHANGELOG.mdに記録されている限り）が踏襲している）。したがって、本Releaseでも同じ運用方針（個別E2Eファイルを既存の正式記録に基づき列挙し、順次実行する）を継続する。

```text
既存Regression対象ファイル（1592/1592の内訳を構成する既存E2Eファイル群）は、
    docs/CHANGELOG.mdの各バージョンエントリ（v1.11.0〜v6.10.0）のTestedセクションから
    正式に特定する。本設計書はこの一覧を推測で列挙・断定しない
    （個別ファイル名の完全な列挙はTest Design／Release Review工程で
    docs/CHANGELOG.mdを参照して確定する）

少なくとも次を含むことをdocs/CHANGELOG.mdで確認済み：
    tests/test_e2e_v6_9_0_wordpress_media_upload_foundation.py（331 Assertion）
    tests/test_e2e_v6_10_0_ai_image_generation_contract_foundation.py（78 Assertion）

一括Runner／scriptが将来整備された場合は、そのcommandを優先する
```

#### 32.9.3 最終報告形式

Release Review時の最終報告は、既存precedent（v6.9.0・v6.10.0）と同一形式を踏襲する。

```text
新規E2E：X/X PASS（Xは32.10章で確定するAssertion数）
既存Regression：1592/1592 PASS（v1.11.0〜v6.10.0）
合計：(1592 + X)/(1592 + X) PASS
```

Scenario数・Case数とAssertion（check相当）数は異なる単位であり、この最終報告のX・1592はいずれもAssertion（既存precedentが用いる正式カウント単位）で表現する。

### 32.10 Scenario／Case／Assertion集計表（Test Review 1・Test Review 2・Implementation Finding IMP-DESIGN-1指摘反映、正式Test Inventory）

**数え方（v6.10.0 precedentを踏襲、Test Review 1で確定）**：

```text
Scenario：独立したID付きContract観点（例：CTOR-KEY-EMPTY、ERR-AUTH）
Case：Scenario内の入力バリエーション1件（forループの1要素、または個別採番）
Assertion：check／check_true／check_false／check_raises相当の独立した期待値1件。
    例外型・reason・message・__cause__・__context__・秘密marker非露出は
    原則として別Assertionとする（ただし__cause__／__context__はCHAIN-*の
    代表4 Scenarioでのみ検証し、他のraiseするScenarioでは重複させない。
    32.5.1章で理由を説明済み）
```

| Category | Scenario ID範囲 | Scenario数 | Case数 | Assertion数 |
|---|---|---:|---:|---:|
| Public API | PKG-* | 4 | 7 | 8 |
| Constructor | CTOR-* | 21 | 47 | 47 |
| from_env | ENV-* | 12 | 12 | 12 |
| Prompt | PROMPT-* | 16 | 24 | 25 |
| Request | REQ-* | 4 | 4 | 4 |
| Client Injection | CLIENT-* | 7 | 7 | 11 |
| Response | RESP-* | 13 | 13 | 39 |
| Base64 | B64-* | 7 | 7 | 19 |
| MIME | MIME-* | 4 | 4 | 4 |
| Provider errors | ERR-* | 13 | 13 | 49 |
| Exception chaining | CHAIN-* | 4 | 4 | 8 |
| Security messages | MSG-* | 3 | 3 | 3 |
| Runtime Guard | GUARD-* | 2 | 2 | 3 |
| Side effects | SIDE-* | 6 | 6 | 6 |
| Dependency | DEP-* | 3 | 6 | 6 |
| Protocol | PROTO-* | 2 | 2 | 2 |
| repr | REPR-* | 2 | 2 | 2 |
| **合計** | | **123** | **163** | **248** |

**Test Review 2 Finding TR2-M-1反映**：GUARD-*行のAssertion数は、Test Review 1時点では2（未確定の2件目Scenarioを含む暫定値）だったが、31.5章でGUARD-SELFTEST（1 Scenario／1 Case／2 Assertion：例外型・message）とGUARD-PATCH-RESTORE（1 Scenario／1 Case／1 Assertion：identity復元）をそれぞれID付きで確定した結果、GUARD-*のAssertion数は3（2＋1）に変わり、この時点で全体のAssertion合計は248から249へ変更となった。Scenario数（2）・Case数（2）はTest Review 1時点の値のまま変わっていない（2件のScenarioという数自体は正しく、内訳の追跡可能性のみが不足していたため）。

**Implementation Finding IMP-DESIGN-1反映**：その後、Implementation工程での実装照合により、CTOR行のsize allowlist件数が実際には7値であるにもかかわらず8値として集計されていたことが判明した（詳細は45章 Review History・45.8章 Finding対応表参照）。CTOR行をCase 48→**47**・Assertion 48→**47**へ訂正し、全体合計をCase 164→**163**・Assertion 249→**248**へ訂正した。全体Assertion合計が「249」から「248」へ変わった結果、Test Review 2時点の「248」（GUARD訂正前の暫定値）と数値としては偶然一致しているが、内訳（GUARD行の構成・CTOR行の構成）は異なるものであり、無関係な2つの訂正が数値上たまたま同じ248に着地したものである。

この表はTest Reviewerが31章〜32.9章の全Contractから独立に導出した正式値であり、`python -c`等による機械的な合計検証で123／163／248が算術的に正しいことを確認済みである。実装（Test Design）段階での合理的な追加Assertion（例：明示性向上のための補助check）による微増は許容されるが、本表がTest Review Approved時点のbaselineとして機能する。

**カテゴリごとの主要な数え方の根拠**：

```text
CTOR：size(7、Implementation Finding IMP-DESIGN-1反映。Test Review 5承認時点では
    誤って8と記載されていた)/quality(3)/output_format(3)のallowlistを全値展開して
    個別Caseとした（境界値のみでは全frozensetメンバーの受理を保証できないため）
PROMPT：C0制御文字（\x01〜\x08・\x0E〜\x1F、計26値）は範囲代表値＋境界
    （\x01・\x08・\x0B・\x0C・\x0E・\x1F・DEL、計7値）に圧縮した
    （8章の理由：同一の範囲判定ロジックを前提とするため、全26値の個別テストは
    Contract検証力を実質的に高めない）
ERR：12種のProvider例外＋差分確認1件＝13 Scenario。各12件は型／reason／
    message／marker非露出の4 Assertion、差分確認1件は1 Assertion
    （__cause__／__context__はCHAIN-*で代表確認するため重複させない）
CHAIN：29.2章の制御フローが全経路で同一であるため、代表4カテゴリ
    （APIError系・その他Exception・Base64異常・Response異常）のみで
    __cause__／__context__を確認する
GUARD：GUARD-SELFTEST（1 Scenario／1 Case／2 Assertion：例外型・message）＋
    GUARD-PATCH-RESTORE（1 Scenario／1 Case／1 Assertion：identity復元）＝
    2 Scenario／2 Case／3 Assertion（詳細は31.5.3章、Test Review 2 Finding
    TR2-M-1反映）
```

v6.9.0・v6.10.0で確立された`ast.Import` / `ast.ImportFrom`ノード解析によるDependency Guardパターンを最初から採用する（AD-27）。文字列検索によるimport検知は、`wordpress_media`のCode Reviewで「docstring中の自然文を誤検知する」という具体的な欠陥が既に判明しているため、本Releaseでは採用しない。

```text
対象ファイル：
    src/openai_image_generation/__init__.py
    src/openai_image_generation/openai_image_generator.py

検証内容：
    absolute importのトップレベルモジュール名が
        {"ai_image_generation", "openai", "base64", "binascii", "os", "typing", ...}
    の許可集合の部分集合であること
    禁止package（13章）への import が存在しないこと
    ai_image_generation からの相対（または絶対）importが GeneratedImage のみであること
```

---

## 34. Side Effect Test Strategy

```text
print() 呼び出しがないこと（ast.Call解析）
open() 呼び出しがないこと（ast.Call解析）
logging の import がないこと（ast.Import／ast.ImportFrom解析）
subprocess の import がないこと（同上）
time.sleep 等のsleep系呼び出し・importがないこと（同上、Rate Limit Contract 26章の「sleepしない」を構造的に保証する）
```

**Architecture Review 1 Finding M-5反映**：実HTTP防止は、31.4章のRuntime Guard（主防御：`openai.OpenAI`をpatchし、無許可の実Client構築を`AssertionError`で即座に検出する）とAST自己検査（補助防御：`OpenAIImageGenerator(...)`呼び出しが原則として`client=`を明示していることの静的確認）の二重防御によって構造的に保証する。「Client Injectionにより常にFakeへ差し替える」という運用上の意図（Architecture Design初版の記載）だけに依存させない。詳細な設計・擬似コード・patch対象・Guardの有効範囲は31.4章のとおり。

---

## 35. Compatibility

```text
既存production codeは無改修である：
    src/ai_image_generation/（v6.10.0、__init__.py / generated_image.py / ai_image_generator.py）
    src/wordpress_media/
    src/outputs/wordpress_output.py
    src/image_resolver.py
    src/outputs/base.py（ArticleData）
    既存記事生成Pipeline全体
    Workflow / Scheduler / Retry Runtime全体
    既存テストファイル一式
```

`requirements.txt`への`openai`追加は、本Architecture Designでは**予定**として記載するのみであり、本セッションでは実際に変更しない（14章「今回変更してよいファイル」制約）。新規独立packageの追加のみであり、既存の呼び出し元（現状ゼロ）にも影響しない。`AIImageGenerator` Protocolに対する初の構造的実装が生まれるが、Protocol自体（`typing.Protocol`定義）に変更はない。

---

## 36. In Scope

```text
src/openai_image_generation/__init__.py（実装Release時に作成予定）
src/openai_image_generation/openai_image_generator.py（同上）
OpenAIImageGenerator
OpenAIImageGenerationError
OpenAI Python SDK採否の決定（本文書内で確定：SDK採用）
OPENAI_API_KEY読込
from_env()
Constructor Contract
prompt validation
Image API generations endpoint（POST /v1/images/generations）
model設定（固定スナップショットデフォルト、上書き可）
size設定（allowlist）
quality設定（allowlist）
output_format設定（allowlist）
n=1固定
Timeout（constructor + 環境変数）
Base64 strict decode
GeneratedImage変換
provider例外の安全な変換
秘密情報漏えい防止
Client Injectionによるtestability
実HTTPなしE2E設計（Test Design詳細は別工程）
requirements.txt追加予定の定義（openai>=2.46.0,<3.0.0、実際の変更は次工程、Architecture Review 1 Finding M-2反映）
```

---

## 37. Out of Scope

```text
WordPressMediaUploaderとの接続
Generated Image → WordPress Media Upload Wiring
filename生成
拡張子生成
ArticleData変更
featured_media設定
image_resolver変更
WordPressOutput変更
既存記事生成Pipelineへの統合
Workflow統合
Scheduler統合
Retry Runtime統合
自動Retry
sleep／Backoff
複数画像生成（n>1）
画像編集（Image Edit API）
入力画像
マスク
Responses API
会話型画像生成
ストリーミング（stream / partial_images）
透明背景（background=transparent。gpt-image-2は非対応）
画像ファイル保存
画像リサイズ
画像圧縮後処理
Pillow導入
Prompt Builder
記事本文からのprompt生成
著作権判定
商標判定
キャラクター判定
月額費用上限管理
API残高取得
実OpenAI APIを使用するE2E
production Fake
既存ai_image_generation package変更
moderation設定の公開（APIデフォルトauto固定）
output_compression設定の公開
user パラメータの公開
Null Object Pattern（NullOpenAIImageGenerator等）
env変数によるmodel／size／quality／output_formatの変更
```

---

## 38. Risks

| Risk | Mitigation |
|---|---|
| OpenAI SDKの`max_retries`既定値（2）が「Retry非実装」方針と暗黙に矛盾する | `with_options(max_retries=0)`をClient使用直前に、Client Injection経路・自己生成経路の両方へ一律適用する（AD-15・AD-28、Architecture Review 1 Finding B-1反映により注入経路のギャップを解消） |
| Timeoutのデフォルト値（180秒）が公式ドキュメントの確定値に基づかない工学的判断である | 公式ガイド「Complex prompts may take up to 2 minutes to process」に対し50%のマージンを確保した（Architecture Review 1 Finding M-1反映）。環境変数による運用調整の余地も残す。実運用で不適切と判明した場合はFast Track候補として値のみ調整可能 |
| Client Injectionされた既存Clientが独自のRetry／Timeout設定を持っていた場合、Adapterの安全Contractが無効化される | `with_options(timeout=..., max_retries=0)`により、注入されたClientの設定に関わらず本Adapter経由の呼び出しでは常に上書きされる（AD-28、Architecture Review 1 Finding B-1反映） |
| `gpt-image-2-2026-04-21`スナップショットが将来OpenAI側で廃止される | 定数値の変更のみで追従可能な設計とし、Public API・Constructor Contractには影響しない（20.2章） |
| Provider例外の`request`/`body`属性がAPIキー・レスポンス全体を保持しうる | Exception Chaining Contract（29章）により`__cause__`・`__context__`双方を到達不能化 |
| `openai`SDKの正確な最小必要バージョンを確認できていない／上限未設定によるメジャーバージョン破壊的変更リスク | 現時点で確実に動作すると確認できた`openai>=2.46.0,<3.0.0`という互換範囲固定を採用し、下限の精密化はKnown Issueとして記録（41章、Architecture Review 1 Finding M-2反映） |
| Content Policy拒否時のエラーメッセージにprompt由来の内容が反映される可能性 | 25.3章で動的メッセージ内容を一切使わず、固定文言のみで例外を構成する |
| allowlist化したsize／qualityが将来のOpenAI側新値追加に追従できない | allowlistへの値追加はConstructor Contract非変更のためFast Track候補となる |
| NUL以外の制御文字の扱いがv6.10.0文書で明示されていない解釈依存部分である | 18.1章で解釈根拠を明記し、Architecture Reviewでの確認事項として44章へ明示 |

---

## 39. Trade-offs

```text
固定スナップショット採用により、品質改善の自動反映を放棄する（再現性を優先）
quality="medium"デフォルトにより、費用を抑える一方で一部記事では画質不足の可能性がある
size allowlist化（Provider数式の非再実装）により、将来の新サイズへは追従作業が必要になる
Timeout 180秒という工学的判断値は、公式の目安上限（2分）に対するマージンを加えたものだが、実際の生成時間分布に基づく統計的な検証を経ていない
単一例外＋reason Enum設計（OpenAIImageGenerationError）により、Provider例外の詳細な型情報そのものは引き続き呼び出し側から隠蔽される
Client Injectionのみに絞ったTest Double戦略により、unittest.mock.patchに慣れた既存開発者には初見の学習コストがある
```

---

## 40. Rejected Alternatives

| 案 | 却下理由 |
|---|---|
| `requests`による直接HTTP実装 | 11章で比較のうえSDK採用を決定。既存リポジトリの外部サービス連携パターン（公式SDK優先）との一貫性を優先 |
| モデルエイリアス（`gpt-image-2`）採用 | 20章。再現性・破壊的変化回避という既存プロジェクトの一貫方針と矛盾するため |
| `ImageGenerationRequest`風の複数フィールドをconstructorではなく都度の`generate()`引数として渡す設計 | Protocol Contract（`generate(self, prompt: str) -> GeneratedImage`）が`prompt`単一引数のみを許容しており、v6.10.0で確定済みのAIImageGenerator Contractを変更できない。model/size/quality等はconstructorで固定する設計とした |
| 例外の細分化（Rate Limit／Authentication／Timeout／Response別） | 25章。現時点で消費者が存在せず、区別して処理する具体的な理由を示せないため時期尚早と判断 |
| `size`/`quality`にOpenAI公式の`auto`値を許容する | 21章。Cost Control Contractが要求する費用の予測可能性と矛盾するため |
| `NullOpenAIImageGenerator`によるConfiguration First対応 | 31.3章。本Releaseに対応する機能フラグ付き消費者（Composition Root）が存在せず、時期尚早と判断。`from_env()`はfail-fastを採用 |
| `unittest.mock.patch`を主軸としたTest Double戦略 | 31.1章。Constructor Injectionという、より明示的で`wordpress_media`のPatch target問題を回避できる代替手段が存在するため |
| `ClaudeClient`型の「例外吸収＋print警告」パターン | 4章・28章。秘密情報・provider情報の漏えいリスク、および安全なFailure Contract不在という問題があり、ユーザー指示によっても明示的に不採用とされている |
| `response.output_format`からMIME typeを導出する設計 | 22章。「providerレスポンスから曖昧に推測する」ことを避けるため、自分がリクエストした`self._output_format`から決定的に導出する設計を採用 |
| `raise ... from None`のみによる例外チェーン対策 | 29章。`__context__`が構造的に残存することが判明したため、except節外でのraiseという制御フロー変更を追加で採用 |
| 単一例外・分類情報なし（Architecture Design初版の採用案） | 25章。Architecture Review 1 Finding M-4により、将来のいかなる消費者も固定メッセージ文字列の脆いパースに頼らざるを得ないことが指摘され、安全な`reason` Enumを追加する設計へ変更した |
| Timeoutデフォルト値120秒（Architecture Design初版の採用値） | 27.1章。公式ガイド「Complex prompts may take up to 2 minutes to process」（＝120秒）と同値であり安全マージンがゼロだったため、Architecture Review 1 Finding M-1により180秒へ変更した |
| Prompt Contract 案A（NULのみ拒否、Architecture Design初版の採用案） | 18.1章。Architecture Review 1 Finding M-3により、不正入力の早期拒否・将来のPrompt Builderへの防御という観点で劣ると指摘され、案B（tab／LF／CRのみ許可）へ変更した |
| `openai>=2.46.0`のみ・上限なし（Architecture Design初版の採用案） | 10.7章。Architecture Review 1 Finding M-2により、将来のメジャーバージョンアップによる無審査の破壊的変更リスクが指摘され、`openai>=2.46.0,<3.0.0`という互換範囲固定へ変更した |
| Client Injection時、内部生成経路のみ`max_retries=0`／`timeout`を保証し、注入経路は呼び出し側の責任とする設計（Architecture Design初版の採用案） | 16.2章。Architecture Review 1 Finding B-1により、Client Injectionが正式なProduction Constructor Contractである以上、この非対称性はGoal 6と矛盾すると指摘され、`with_options()`による一律強制へ変更した |
| `with_options()`未実装の注入Clientを`OpenAIImageGenerationError`（`reason=UNKNOWN`）へ変換する設計 | 16.2章。継続審議により、Interface不適合はProvider障害ではなくprogramming／configuration errorであると整理され、`TypeError`による即時fail-fastへ変更した |
| 実HTTP防止をテスト作成者の運用上の意図（「常にFakeへ差し替える」）のみに委ねる設計 | 31.4章・34章。Architecture Review 1 Finding M-5により、構造的な強制手段が存在しない点が指摘され、Runtime Guard（主防御）＋AST自己検査（補助防御）の二重防御へ変更した |

---

## 41. Known Issues

```text
openai SDKの正確な最小必要バージョンは未確認（10.7章）。現時点ではPyPIで動作確認できた
    openai>=2.46.0,<3.0.0 を互換範囲として暫定採用している（Architecture Review 1
    Finding M-2反映、下限はPyPI動作確認・上限はメジャーバージョン破壊的変更防止）。
    Implementation段階でより精密な下限が判明した場合は置き換えてよい

gpt-image-2-2026-04-21 スナップショットは将来OpenAI側で廃止されうる。廃止時は
    _DEFAULT_MODEL 定数値の更新Releaseが必要になる（20.2章）

response側の output_format / quality / size （レスポンスエコー）は本Adapterで
    読まない・検証しない。リクエストした値とレスポンスが乖離した場合も検知できない
    （22章）

output_compression パラメータは公開しない。output_format="jpeg"/"webp"を選択した
    場合もAPI既定の圧縮率（100）が暗黙に使用される

Timeoutデフォルト値（180秒）は、公式ガイドの目安上限（Complex prompts may take up to
    2 minutes to process）に対し50%のマージンを加えた工学的判断であり、実際の生成時間分布
    による統計的な検証を経ていない（27.1章、Architecture Review 1 Finding M-1反映）

（解消済み）NUL文字以外の制御文字（\x01〜\x08、\x0B〜\x1F、\x7F等）の許容・拒否は、
    Architecture Review 1 Finding M-3を受け、tab／LF／CRのみ許可しそれ以外は拒否する
    案Bへ変更した（18.1章）。v6.10.0設計書のContract自体は変更していない
    （v6.11 Adapter固有の追加制約として上乗せした）

1枚あたりの具体的な$費用は本文書に固定値として記載していない（10.8章）。
    運用時は公式料金計算ツールを都度参照する必要がある

n の上限値（複数画像生成時の最大値）は公式ドキュメントで確定値を確認できなかった。
    本Releaseはn=1固定のため実害はないが、将来n>1を検討する場合は改めて確認が必要
```

---

## 42. Future Extensions

```text
Generated Image → WordPress Media Upload Wiring（ROADMAP次候補C、本Adapter完成後）
Article → featured_media Wiring（ROADMAP次候補D）
Retry Runtime統合・再試行可否分類（責務整理後、26章・42章）
env変数によるmodel／size／quality／output_formatの上書き対応（運用上の必要性が
    具体化した時点でFast Track候補として検討）
output_compressionパラメータの公開
user パラメータによるエンドユーザー追跡
per-request Timeout（`client.images.generate(..., timeout=...)`、10.6章で存在を確認済みの
    request単位timeout引数）の採用検討
gpt-image-2スナップショットのバージョン更新Release（OpenAI側の廃止通知に応じて）
必要性が生じた場合のRate Limitヘッダ（Retry-After等）の安全な公開
```

順序は確定事項として固定しない。

---

## 43. Implementation Plan

**本Releaseでは実施しない。** 次はArchitecture Review Approved後の実装Releaseで作成される想定ファイルの一覧である。

**新規production code（未作成）**

```text
projects/03_game_content_ai/src/openai_image_generation/__init__.py
projects/03_game_content_ai/src/openai_image_generation/openai_image_generator.py
```

**新規テスト（未作成）**

```text
projects/03_game_content_ai/tests/test_e2e_v6_11_0_openai_image_generation_adapter_foundation.py
```

**変更予定（本Releaseでは未実施）**

```text
projects/03_game_content_ai/requirements.txt（openai>=2.46.0,<3.0.0 追加予定、Architecture Review 1 Finding M-2反映）
projects/03_game_content_ai/docs/ROADMAP.md（実装完了後）
projects/03_game_content_ai/docs/architecture.md（実装完了後）
projects/03_game_content_ai/docs/CHANGELOG.md（実装完了後）
```

**変更なし（既存無改修方針）**

```text
src/ai_image_generation/（全ファイル）
src/wordpress_media/（全ファイル）
src/outputs/wordpress_output.py
src/image_resolver.py
src/outputs/base.py（ArticleData）
既存記事生成Pipeline全体
Workflow / Scheduler / Retry Runtime全体
既存テストファイル一式
```

---

## 44. Review Checklist

Architecture Reviewでの確認を想定した自己点検項目（16章セルフレビューと対応）。

```text
[ ] v6.10.0 Contract（GeneratedImage／AIImageGenerator）と矛盾していないか
[ ] ai_image_generationの標準ライブラリ限定を破壊していないか（openai_image_generation側にのみopenai依存を閉じ込めているか）
[ ] 依存方向（OpenAI Adapter → ai_image_generation）が正しいか、逆方向依存がないか
[ ] OpenAI SDKとrequestsの比較が十分か（11章）
[ ] モデルalias／snapshotの選択理由があるか（20章）
[ ] prompt Contractがv6.10.0の既存文言と一致しているか、拡大解釈していないか（18章・18.1章）
[ ] Base64 decodeがstrict（validate=True）か（24章）
[ ] MIME typeが曖昧な推測に基づいていないか（22章）
[ ] Timeoutが無制限でないか、SDK既定のmax_retriesが無効化されているか（27章・AD-15）
[ ] Rate LimitとRetryの責務が分離されているか（26章）
[ ] API費用の暴発を防いでいるか（n=1固定・quality/sizeのallowlist、30章）
[ ] provider例外が漏えいしないか（25章・28章）
[ ] 例外チェーン（__cause__・__context__双方）が安全か（29章）
[ ] 実HTTPなしで全Contractをテストできる設計か（31章・32章）
[ ] In Scope／Out of Scopeが明確か（36章・37章）
[ ] C（WP Upload Wiring）・D（featured_media Wiring）が混入していないか（37章で明示的にOut of Scope）
[ ] 未確定事項がBlocking Open Questionとして明示されているか、または妥当な根拠で確定されているか（45.1章、Architecture Review 1で解消済み）
[x] NUL以外の制御文字の解釈（18.1章）が妥当か（Architecture Review 1 Finding M-3を受け案Bへ変更済み）
[ ] Client Injection経路でもwith_options(max_retries=0, timeout=...)が確実に適用されるか（16.2章、Architecture Review 1 Finding B-1反映）
[ ] Minimal Images Client Contract不足時にTypeErrorでfail-fastし、Provider Failureへ誤変換していないか（16.2章、継続審議反映）
[ ] OpenAIImageGenerationErrorのreason Enumが秘密情報を含まない安全な分類のみで構成されているか（25章、Architecture Review 1 Finding M-4反映）
[ ] reasonのメンバー名（REQUEST_REJECTED等）がHTTP実装詳細を漏らさない中立的な表現か（25.1章）
[ ] requirements.txt version constraint（openai>=2.46.0,<3.0.0）が互換範囲として妥当か（10.7章、Architecture Review 1 Finding M-2反映）
[ ] Timeoutデフォルト値（180秒）が公式の目安上限（2分）に対し十分なマージンを持つか（27.1章、Architecture Review 1 Finding M-1反映）
[ ] 実HTTP防止がRuntime Guard（主防御）＋AST自己検査（補助防御）の二重防御として実装可能な具体性を持つか（31.4章・34章、Architecture Review 1 Finding M-5反映）
[ ] Runtime GuardのFake経路（client=注入Scenario）が誤って巻き込まれない設計になっているか（31.4章）
[ ] openai>=2.46.0,<3.0.0という互換範囲が妥当か、下限の精密化がKnown Issueとして正しく位置づけられているか（41章）
```

---

## 45. Review History

```text
Architecture Design作成：2026-07-17（Claude Code）
    - v6.10.0（0b03148）のGit状態確認（HEAD一致、ahead/behind 0/0、Working Tree clean）を実施のうえ着手
    - development_workflow.md・release_start_checklist.md・architecture_release_template.md・
      ai_image_generation_contract_foundation.md（v6.10.0）・wordpress_media_upload_foundation.md（v6.9.0）を
      読了し、既存の設計書形式・Contract・Review履歴を踏まえて作成した
    - OpenAI公式ドキュメント（developers.openai.com）・PyPI・GitHub（openai-python）を
      WebSearch／WebFetchで直接調査し、10章 Official OpenAI API Findingsとして記録した

Architecture Review 1：2026-07-17（独立Architecture Reviewer、Claude Code別セッション）
    判定：Changes Required
    Blocking：
        B-1（16.2章・31章：Client Injection経路でmax_retries=0／timeout保証が及ばない）
    Major：
        M-1（27章：Timeoutデフォルト120秒が公式目安上限と同値で安全マージンゼロ）
        M-2（10.7章：requirements.txt version constraintに上限がない）
        M-3（18章：Prompt Contractの制御文字解釈、案Aより案Bが妥当）
        M-4（25章：Error Contractが安全な失敗分類情報を一切持たない）
        M-5（31章・34章：実HTTP防止がテスト作成者の注意力のみに依存）
    Minor：
        m-1（19.2章：request単位timeoutの存在に関する記載誤り）
        m-2（10.3章：quality許容値のモデル依存性の注記不足）
        m-3（10.7章：GitHub Issue #3114の知見の記載不足）
    指摘反映：Completed（本改訂で全Finding対応。45.2章 Finding対応表参照）

Architecture Review 2：2026-07-17（独立Architecture Reviewer、Claude Code別セッション）
    判定：Changes Required
    Blocking：
        なし
    Major：
        R2-M-1（27章：Timeout Contract表がClient構築時にtimeoutを設定するという
            旧メカニズムを記載しており、16.2章のwith_options()ベースの現行Contract
            と矛盾していた。B-1修正時に27章への反映が漏れていたことが原因）
    Minor：
        R2-m-1（25.3章・29.2章：_classify_api_error()の具体例外→一般例外の
            判定順序が擬似コードとして明示されていなかった）
    指摘反映：Completed（本改訂で全Finding対応。45.3章 Finding対応表参照）

Architecture Review 3：2026-07-17（独立Architecture Reviewer、Claude Code別セッション）
    判定：Approved
    Blocking：なし
    Major：なし
    Minor：なし
    Blocking Open Questions：なし

Test Review 1：2026-07-17（独立Test Reviewer、Claude Code別セッション）
    判定：Changes Required
    Blocking：
        なし
    Major：
        FIND-1（25.3章・29.2.1章・31章・32.5章：Provider例外Fake構築方法
            （httpx.Response／httpx.Request使用）が設計書に存在しなかった）
        FIND-2（設計書全体：Regression Test Strategy章・正式baseline数値
            （1592/1592、v1.11.0〜v6.10.0）が存在しなかった）
    Minor：
        FIND-3（31.4章：Runtime Guard自体の自己検証Scenarioがなかった）
        FIND-4（24章・24.1章・AD-20：空bytes分岐が実在入力では到達不能である旨の
            注記がなかった）
        FIND-5（17.1章・32.8章：環境変数の隔離・復元方法が具体的に示されていなかった）
    指摘反映：Completed（本改訂で全Finding対応。45.4章 Finding対応表参照）

Test Review 2：2026-07-17（独立Test Reviewer、Claude Code別セッション）
    判定：Changes Required
    Blocking：
        なし
    Major：
        TR2-M-1（31.5章・32.10章：GUARDカテゴリのScenario数が2と集計されていたが、
            本文中でID付きに定義されたScenarioはGUARD-SELFTEST1件のみで、
            2件目の目的・操作・期待値が追跡できなかった）
    Minor：
        TR2-m-1（9章AD-27・13章・31.4章・31.6.2章・15章：存在しない
            「33章 Dependency Test Strategy」への相互参照が5箇所残っていた）
    指摘反映：Completed（本改訂で全Finding対応。45.5章 Finding対応表参照）

Test Review 3：2026-07-17（独立Test Reviewer、Claude Code別セッション）
    判定：Changes Required
    Blocking：
        なし
    Major：
        なし
    Minor：
        TR3-m-1（45章：Architecture Review 2・Test Review 1の指摘反映文が、
            自身のFinding対応表ではない章番号（45.2章・45.3章）を参照していた）
    指摘反映：Completed（本改訂で全Finding対応。45.6章 Finding対応表参照）

Test Review 4：2026-07-17（独立Test Reviewer、Claude Code別セッション）
    判定：Changes Required
    Blocking：
        なし
    Major：
        なし
    Minor：
        TR4-m-1（32.5.1章：ERR-*代表4カテゴリ確認の参照先が、実際には内容の
            存在しない32.9章になっており、正しい参照先は32.10章だった）
        TR4-m-2（31.5.2章：GUARD-PATCH-RESTOREのAssertion数え方の説明文が、
            32.8章末尾にのみ存在する引用句をあたかも32.10章にあるかのように
            読める構文になっていた）
    指摘反映：Completed（本改訂で全Finding対応。45.7章 Finding対応表参照）

Test Review 5：2026-07-17（独立Test Reviewer、Claude Code別セッション）
    判定：Approved
    Blocking：
        なし
    Major：
        なし
    Minor：
        なし
    Blocking Open Questions：
        なし

Implementation：2026-07-17（実装担当者、Claude Code別セッション）
    Architecture Review 3（Approved）・Test Review 5（Approved）を受けて
    production code実装・requirements.txt更新に着手した。
    size Constructor Contractの実装照合中に、設計書内の記載間で矛盾を発見し、
    実装者の独自判断でContractを変更せず、その時点で作業を一時停止して報告した。
    詳細はIMP-DESIGN-1（下記）参照。

IMP-DESIGN-1：2026-07-17（実装担当者による発見、Claude Code別セッション）
    発見工程：Implementation
    Severity：Major相当
    問題：
        size allowlistの実体（21.1章`_ALLOWED_SIZES`のfrozenset literal、
        および10.3章 OpenAI公式調査結果の列挙）はいずれも7値であったが、
        9章ADR-6・AD-7・16.1章 Constructor検証Contract・32.10章 Test Inventory
        根拠の4箇所で「8値」「size(8)」と誤って記載されていた。
    影響：
        32.10章のCTOR行（Case・Assertion数）、および全体のScenario／Case／
        Assertion合計（Test Review 5承認時点では123／164／249）が、
        実際にContractとして実装可能な値と1件ずつずれていた。
    判断：
        7値（21.1章の既存frozenset literal、公式一次情報とも一致）を
        正式Contractとする。8個目のsize値は追加しない。production code
        （21.1章と同一の7値で実装済み）は変更しない。
        OpenAI Provider自体は一定条件を満たす任意のWIDTHxHEIGHTを
        サポートするが、本Adapterは予測可能性・Testabilityのため、
        その中の7値に閉じたallowlistのみを許可する（21.1章に区別を明記）。
    対応：
        9章ADR-6・AD-7・16.1章・32.10章の「8値」表記を「7値」へ訂正。
        32.10章CTOR行をCase 48→47・Assertion 48→47へ訂正。
        全体合計をScenario 123（不変）／Case 164→163／Assertion 249→248へ訂正。
    指摘反映：Completed（本改訂で対応。45.8章 Finding対応表参照）

Architecture Review 4：2026-07-17（独立Architecture Reviewer、Claude Code別セッション）
    種別：Focused Architecture Review（IMP-DESIGN-1対応確認）
    判定：Changes Required
    Blocking：
        なし
    Major：
        なし
    Minor：
        AR4-m-1（9.1章ADR-6・21.1章：Provider Capabilityの説明が
            「最大辺3840px以下・両辺16pxの倍数・長辺短辺比3:1以内」の3条件のみを
            記載しており、OpenAI公式ドキュメントが明記する4条件目
            「総ピクセル数655,360以上8,294,400以下」が欠落していた）
    Blocking Open Questions：
        なし
    指摘反映：Completed（本改訂で全Finding対応。45.9章 Finding対応表参照）

Architecture Review 5：2026-07-17（独立Architecture Reviewer、Claude Code別セッション）
    種別：Focused Architecture Review
    対象：IMP-DESIGN-1・AR4-m-1
    判定：Approved
    Blocking Findings：
        なし
    Major Findings：
        なし
    Minor Findings：
        なし
    Blocking Open Questions：
        なし
    確認結果：
        ・Provider Capabilityの公式4条件（9.1章ADR-6・10.3章・21.1章）が
          全対象章で一致
        ・代表7値のAdapter Contract（AD-7・16.1章・21.1章・32.10章）が
          全章で一致
        ・production codeの`_ALLOWED_SIZES`と設計書21.1章が一致
        ・8個目のsize値を追加しない判断は妥当
        ・Test Inventory（123／163／248）への影響は論理的に整合
    次工程：Focused Test Review 6

Test Review 6：2026-07-17（独立Test Reviewer、Claude Code別セッション）
    種別：Focused Test Review
    対象：IMP-DESIGN-1反映後の正式Test Inventory
    判定：Approved
    Blocking Findings：
        なし
    Major Findings：
        なし
    Minor Findings：
        なし
    Blocking Open Questions：
        なし
    正式Test Inventory：
        123 Scenario
        163 Case
        248 Assertions
    CTOR：
        21 Scenario
        47 Case
        47 Assertions
    次工程：Implementation再開

Implementation：2026-07-17（実装担当者、Claude Code別セッション）
    判定：Completed
    production package：
        src/openai_image_generation/__init__.py（新規）
        src/openai_image_generation/openai_image_generator.py（新規）
        正式設計書（16.1章・21.1章の7値size allowlist含む）との全文監査を実施し、
        一致を確認（production code自体の修正は不要だった。docstring内の
        Review状態コメントのみ最新化）
    requirements.txt：openai>=2.46.0,<3.0.0（追加済み、変更なし）
    新規E2E：
        tests/test_e2e_v6_11_0_openai_image_generation_adapter_foundation.py（新規）
        123 Scenario／163 Case／248 Assertion（32.10章の17カテゴリすべてと
        独立再計算で一致）
        248/248 PASS（終了コード0、警告なし、Tracebackなし、実HTTP・実課金なし）
    既存Regression：
        対象13ファイル（v1.11.0・v5.9.0〜v6.10.0、docs/CHANGELOG.md
        v6.10.0 Testedセクションに明記された正式ファイル一覧から特定。
        推測での列挙は行っていない）
        1592/1592 PASS（終了コードすべて0、警告なし、Tracebackなし）
    合計：1840/1840 PASS（248＋1592）
    実HTTP：なし
    実課金：なし
    既存package（ai_image_generation／wordpress_media／outputs／
        image_resolver.py等）：無改修（git diffで確認済み）
    Blocking Issue：なし

Code Review 1：2026-07-17（独立Code Reviewer、Claude Code別セッション）
    判定：Approved
    Blocking Findings：
        なし
    Major Findings：
        なし
    Minor Findings：
        なし
    Blocking Open Questions：
        なし
    確認結果：
        ・production codeが正式設計書と一致
        ・Public APIが3要素と一致
        ・size 7値Contractが一致
        ・新規E2E 123／163／248を再現
        ・新規E2E 248/248 PASS
        ・正式13ファイルRegression 1592/1592 PASS
        ・合計1840/1840 PASS
        ・Runtime Guard有効
        ・実HTTP／実課金なし
        ・Security Contract適合
        ・既存Runner／既存test無改修
    次工程：Documentation Integration

Documentation Integration：2026-07-17（Documentation Integration担当者、Claude Code別セッション）
    対象：ROADMAP.md・architecture.md・CHANGELOG.md・正式設計書
    確認結果：
        ・ROADMAP.mdのOpenAI Image Generation Adapter Foundation項目を
            未着手スタブから完了実績（Architecture Review 1〜5／Test Review 1〜6／
            Code Review 1、123／163／248、248/248、1592/1592、1840/1840、
            IMP-DESIGN-1解消済み）に更新
        ・architecture.mdにOpenAI Image Generation Adapter Foundation層セクションを
            追加（git diff --statで132 insertions／0 deletionsの純追加を確認）
        ・CHANGELOG.mdにv6.11.0エントリを追加（v6.10.0エントリの直前に挿入、
            既存フォーマットに準拠）
        ・IMP-DESIGN-1はAdded／Known Issueとしてではなく、Architecture Review 4〜5・
            Test Review 6で解消済みの設計訂正として全ファイルに一貫して記録
        ・Regressionベースラインはdocs/CHANGELOG.md v6.10.0 Testedセクションに基づく
            正式13ファイル（1592件）として記録（既存61ファイル全件・23ファイルの
            付随的既存失敗のいずれとも混同していない）
        ・8値／164 Case／249 Assertions／249/249／1841/1841等の旧値の残存なし
            （訂正前→訂正後の記述を除く）
        ・機械監査：architecture.mdのtrailing whitespace 29件・見出し重複22件は
            いずれも本Release編集前から存在（git show HEAD:...で原本71件を確認、
            git diff --statで純追加を確認）。新規挿入した129行を個別走査し
            trailing whitespaceゼロ、新規重複見出しゼロを確認
    結果：Completed

Release Review 1：2026-07-17（独立Release Reviewer、Claude Code別セッション）
    判定：Changes Required
    Blocking Findings：
        なし
    Major Findings：
        なし
    Minor Findings：
        RR1-m-1
    Blocking Open Questions：
        なし
    確認結果：
        ・Architecture Contractは正式設計書と一致
        ・新規E2E 248/248 PASSを再現
        ・正式Regression 1592/1592 PASSを再現
        ・合計1840/1840 PASS
        ・実HTTP／実課金なし
        ・Documentation Integrationの主要内容は整合
        ・最終段落にCode ReviewのStatus不整合を検出
    指摘反映：Completed（本改訂で対応。45.10章 Finding対応表参照）
    次工程：Focused Release Review 2

Release Review 2：2026-07-17（独立Release Reviewer、Claude Code別セッション）
    種別：Focused Release Review
    対象：RR1-m-1反映後の最終成果物
    判定：Approved
    Blocking Findings：
        なし
    Major Findings：
        なし
    Minor Findings：
        なし
    Blocking Open Questions：
        なし
    確認結果：
        ・RR1-m-1は実質解消
        ・ヘッダー、Document Information、Status、Review History、最終段落が整合
        ・Architecture Designからの逸脱なし
        ・Public API 3要素を維持
        ・size 7値Contractを維持
        ・Test Inventory 123／163／248を維持
        ・新規E2E 248/248 PASSを再現
        ・正式Regression 1592/1592 PASSを再現
        ・合計1840/1840 PASS
        ・実HTTP／実課金なし
        ・Security Contract適合
        ・変更範囲は承認済み範囲内
    最終判定：Release 6.11 commit・push可能
```

## 45.1 Blocking Open Questions

**Architecture Review 1により解消済み。** 当初のArchitecture Design初版が抱えていたBlocking Open Question（NUL以外の制御文字の扱い）は、Architecture Review 1のFinding M-3を受け、18.1章のとおり案B（tab／LF／CRのみ許可、他のC0制御文字とDELは拒否）へ確定した。経緯は次のとおり記録する。

```text
当初のBlocking Open Question：
    v6.10.0設計書12章のPrompt Contractは「NUL文字を拒否する」「改行とtabは許可する」
    の2点のみを明示しており、それ以外の制御文字（\x01〜\x08等）の可否を明示していない。

当初の推奨案（Architecture Design初版、Architecture Review 1で変更を指摘）：
    「Approved済み文書に明示のない拒否ルールを新規追加しない」という原則に基づき、
    NUL以外の制御文字は許可する（案A）。

Architecture Review 1（Finding M-3）の指摘：
    案Aはv6.10.0の文言と矛盾しないが、不正入力の早期拒否・将来のPrompt Builderへの
    防御・プロジェクト全体のfail-fast方針との整合という観点で、案B（tab・LF・CRのみ
    許可、他のC0制御文字とDELは拒否）の方が望ましいと指摘された。案C（すべての制御
    文字拒否）はv6.10.0が明示的に許可するtab／LFと矛盾するため却下された。

確定した結論（本改訂で反映）：
    案Bを採用する（18.1章、AD-18・AD-29）。v6.10.0本体のContractは変更せず、
    v6.11 Adapter固有の追加制約として上乗せする構成とした。

実装を開始してよいか：
    本文書の確定案（案B）を前提として実装を開始できる。Blocking Open Questionは
    残っていない。
```

## 45.2 Finding対応表（Architecture Review 1）

| Finding | Severity | 対応章 | 修正概要 | 状態 |
|---|---|---|---|---|
| B-1 | Blocking | 9章（ADR-17・AD-28）・16.2章・26章・30章・31章・32.1章・38章・40章 | Client Injection・自己生成いずれの経路も`with_options(timeout=..., max_retries=0)`を経由してのみClientを使用するよう強制。Minimal Images Client Contract不足は`TypeError`でfail-fast（Provider Failureとは区別） | Resolved |
| M-1 | Major | 9章（ADR-11）・10.2.1章・27章・38章・39章・40章・41章 | 公式ガイド「Complex prompts may take up to 2 minutes to process」の見落としを是正し、デフォルトTimeoutを120秒→180秒（50%マージン）へ変更 | Resolved |
| M-2 | Major | 9章（AD-30）・10.7章・13章・36章・38章・40章・41章・43章 | `openai>=2.46.0`（下限のみ）→`openai>=2.46.0,<3.0.0`（互換範囲固定）へ変更 | Resolved |
| M-3 | Major | 9章（ADR-18・AD-29）・18章・18.1章・32.3章・38章・40章・45.1章 | Prompt Contractの制御文字解釈を案A（NULのみ拒否）→案B（tab／LF／CRのみ許可、他は拒否）へ変更。Blocking Open Questionを解消 | Resolved |
| M-4 | Major | 9章（ADR-12・AD-16）・14章・23章・24章・25章・28章・29章・32.4〜32.6章・40章 | 単一例外・分類情報なしの設計へ、秘密情報を含まない`OpenAIImageGenerationErrorReason` Enumを追加。`reason`メンバー名の比較（`BAD_REQUEST`→`REQUEST_REJECTED`採用）も実施 | Resolved |
| M-5 | Major | 9章（AD-31）・31.4章・32.2章・32.8章・34章・40章 | 実HTTP防止を、Runtime Guard（`openai.OpenAI`のpatch、無許可の実Client構築を`AssertionError`で検出、主防御）＋AST自己検査（補助防御）の二重防御へ変更 | Resolved |
| m-1 | Minor | 10.6章・19.2章・27章 | 「request単位timeoutの存在を確認できなかった」という誤記を、「SDKに存在するが今回は不採用」という正確な記載へ訂正 | Resolved |
| m-2 | Minor | 10.3章 | quality許容値`standard`／`hd`がDALL-E-3専用でありgpt-image-2では無効である旨を注記 | Resolved |
| m-3 | Minor | 10.7章 | GitHub Issue #3114（`model`引数の緩い型・型チェッカーへの影響限定・本プロジェクトでの型チェッカー使用有無は断定しない旨）を追記 | Resolved |

実際に完了していないFindingは存在しない（全9件Resolved）。

## 45.3 Finding対応表（Architecture Review 2）

| Finding | Severity | 対応章 | 修正概要 | 状態 |
|---|---|---|---|---|
| R2-M-1 | Major | 27章・（横断整合確認：9章・10.6章・16.2章・19.2章・26章・30章・31章・32.1章・38章・40章・41章） | 27章のTimeout Contract表にあった「Client構築時にtimeoutを設定する」という旧メカニズムの記述を削除し、16.2章の現行Contract（自己生成・注入いずれの経路も使用直前に`with_options(timeout=..., max_retries=0)`を経由させる）と完全に一致する記述へ修正 | Resolved |
| R2-m-1 | Minor | 25.3章・29.2.1章（新設）・32.5章 | `_classify_api_error()`の判定順序（具体例外→一般例外、`APITimeoutError`を`APIConnectionError`より先に判定する必要がある点を含む）を実装可能な擬似コードとして29.2.1章へ新設し、25.3章・32.5章から参照する形へ整理 | Resolved |

実際に完了していないFindingは存在しない（Architecture Review 2の2件とも全件Resolved）。

## 45.4 Finding対応表（Test Review 1）

| Finding | Severity | 対応章 | 修正概要 | 状態 |
|---|---|---|---|---|
| FIND-1 | Major | 31.6章（新設）・25.3章・29.2.1章（参照追加）・32.5.1章（新設） | OpenAI公式ソース（`src/openai/_exceptions.py`）で確認したconstructor signatureに基づき、`httpx.Response`／`httpx.Request`を用いたProvider例外Fake構築Helper（`_make_api_status_error`／`_make_connection_error`／`_make_timeout_error`／`_make_generic_api_error`）を追加。httpxはTest-only dependencyであり既存Dependency Contractと矛盾しないことも明記 | Resolved |
| FIND-2 | Major | 32.9章（新設） | Regression Test Strategyを新設し、`docs/CHANGELOG.md`から特定した正式baseline（v1.11.0〜v6.10.0、1592/1592 PASS）を明記。Regression Contract・実行対象・最終報告形式も明記 | Resolved |
| FIND-3 | Minor | 31.5章（新設） | Runtime Guard自己検証Scenario（GUARD-SELFTEST）を追加 | Resolved |
| FIND-4 | Minor | 24.1.1章（新設） | AD-20（空bytes分岐）が実在する非空base64文字列では到達不能であることを明記し、`base64.b64decode`を直接patchする検証方式（patch target含む）を追加 | Resolved |
| FIND-5 | Minor | 17.1.1章（新設）・32.8章 | `unittest.mock.patch.dict(os.environ, {...}, clear=True)`による環境変数の隔離・自動復元方式を明記 | Resolved |

実際に完了していないFindingは存在しない（Test Review 1の5件とも全件Resolved）。32.10章に、本改訂を反映した正式なScenario／Case／Assertion集計表（123／164／248、Test Review 2でGUARD行の内訳確定に伴い249へ改訂）を新設した。

## 45.5 Finding対応表（Test Review 2）

| Finding | Severity | 対応章 | 修正概要 | 状態 |
|---|---|---|---|---|
| TR2-M-1 | Major | 31.5章（GUARD-SELFTEST／GUARD-PATCH-RESTOREへ再構成）・32.10章（GUARD行・合計値更新） | GUARDカテゴリの2 Scenarioを、31.5.1章 GUARD-SELFTEST（1 Scenario／1 Case／2 Assertion：例外型・message）・31.5.2章 GUARD-PATCH-RESTORE（1 Scenario／1 Case／1 Assertion：patch解除後のidentity復元）としてそれぞれID・目的・操作・期待値付きで明示。32.10章のGUARD行をAssertion数2→3へ、全体合計をAssertion248→249へ更新 | Resolved |
| TR2-m-1 | Minor | 9章AD-27・13章・15章（15.1章直前の段落）・31.4章・31.6.2章 | 存在しない「33章 Dependency Test Strategy」への相互参照5箇所を、実体である「32.7章 Dependency（AST）」への参照へ統一。新規の33章は作成せず、32.7章以降の既存章番号も変更していない | Resolved |

実際に完了していないFindingは存在しない（Test Review 2の2件とも全件Resolved）。

## 45.6 Finding対応表（Test Review 3）

| Finding | Severity | 対応章 | 修正概要 | 状態 |
|---|---|---|---|---|
| TR3-m-1 | Minor | 45章 | Architecture Review 2エントリの指摘反映文の参照先を45.2章→45.3章へ、Test Review 1エントリの指摘反映文の参照先を45.3章→45.4章へ訂正。Architecture Review 1（45.2章）・Test Review 2（45.5章）の正しい参照はそのまま維持 | Resolved |

実際に完了していないFindingは存在しない（Test Review 3の1件もResolved）。

## 45.7 Finding対応表（Test Review 4）

| Finding | Severity | 対応章 | 修正概要 | 状態 |
|---|---|---|---|---|
| TR4-m-1 | Minor | 32.5.1章 | ERR-*代表4カテゴリ確認の参照先「29.2.1章・32.9章参照」から、実体のない「32.9章」を削除し、例外分類・制御フローは29.2.1章、CHAIN代表4カテゴリの命名とカウント根拠は32.10章という形で参照先を明確化 | Resolved |
| TR4-m-2 | Minor | 31.5.2章 | GUARD-PATCH-RESTOREのAssertion数え方の説明から紛らわしい「32.10章」の前置きを削除し、引用句が32.8章末尾にあることを明確化。GUARDカテゴリの正式カウント参照先（31.5.3章・32.10章）は別文として明記 | Resolved |

実際に完了していないFindingは存在しない（Test Review 4の2件とも全件Resolved）。

## 45.8 Finding対応表（Implementation Finding）

| Finding | Severity | 対応章 | 修正概要 | 状態 |
|---|---|---|---|---|
| IMP-DESIGN-1 | Major相当 | 9章（ADR-6・AD-7）・16.1章・21.1章・32.10章 | size allowlistの実体（21.1章`_ALLOWED_SIZES`、7値）と、9章ADR-6・AD-7・16.1章・32.10章の「8値」表記との不一致を訂正。7値を正式Contractとして確定し（8個目は追加しない）、21.1章にProvider Capability（任意のWIDTHxHEIGHT）とv6.11.0 Adapter Contract（7値に閉じたallowlist）の区別を明記。32.10章のCTOR行（Case・Assertion）と全体合計（Scenario 123／Case 164→163／Assertion 249→248）を訂正 | Resolved |

実際に完了していないFindingは存在しない（IMP-DESIGN-1もResolved）。production code（`src/openai_image_generation/`）は21.1章の7値と一致した状態で実装済みであり、変更していない。

## 45.9 Finding対応表（Architecture Review 4）

| Finding | Severity | 対応章 | 修正概要 | 状態 |
|---|---|---|---|---|
| AR4-m-1 | Minor | 9.1章（ADR-6）・10.3章・21.1章 | Provider Capabilityの説明を、OpenAI公式ドキュメントが明記する4条件（最大辺3840px以下・幅と高さがともに16pxの倍数・長辺短辺比3:1以内・総ピクセル数655,360以上8,294,400以下、いずれも境界値含む）へ統一。10.3章（未修正のまま残っていた3条件のみの記載）も同様に訂正。21.1章では代表7値がこの4条件をすべて満たすことをread-onlyで検算済み。v6.11.0 Adapter Contract（`_ALLOWED_SIZES`の7値・auto不採用・custom size不採用）自体は変更していない | Resolved |

実際に完了していないFindingは存在しない（AR4-m-1もResolved）。

## 45.10 Finding対応表（Release Review 1）

| Finding | Severity | 対応箇所 | 修正概要 | 状態 |
|---|---|---|---|---|
| RR1-m-1 | Minor | 最終段落・Status・Review History | Code Review 1 Approved、Documentation Integration Completed、Release Review 1 Changes Required、Release Review 2 Pendingへ統一 | Resolved |

実際に完了していないFindingは存在しない（RR1-m-1もResolved）。

---

**本文書はArchitecture Design作成が完了し、Architecture Review 1〜5（Review 3・Review 5はApproved、Review 4はChanges Required→AR4-m-1反映済み）の指摘をすべて反映した状態である。Test Review 1〜6（Review 5・Review 6はApproved）の指摘もすべて反映した。Implementation（production code実装）着手時に判明したsize allowlist件数の矛盾（IMP-DESIGN-1）を受け、正式Test Inventoryを123／163／248へ訂正し、Provider Capabilityの説明を公式4条件へ統一した。この訂正内容はArchitecture Review 5・Test Review 6でいずれもApprovedとなった。Implementationはこれを受けて再開し、新規E2E（123 Scenario／163 Case／248 Assertion、248/248 PASS）・既存Regression（1592/1592 PASS）・合計（1840/1840 PASS）をすべて確認してCompletedとなった。Code Review 1はApproved、Documentation IntegrationはCompletedである。Release Review 1はRR1-m-1（最終段落のStatus不整合）によりChanges Requiredとなり、本Finding反映後のFocused Release Review 2はApprovedとなった。Architecture Review 5、Test Review 6、Code Review 1およびRelease Review 2はいずれもApprovedであり、ImplementationおよびDocumentation IntegrationはCompletedである。Blocking IssueおよびBlocking Open Questionはなく、Release 6.11はcommit・push可能な状態である。**
