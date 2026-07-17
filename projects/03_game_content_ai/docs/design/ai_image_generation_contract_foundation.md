# AI Image Generation Contract Foundation — Architecture Design（v6.10.0）

作成日：2026-07-17
作成者：Claude Code（Architecture Design作成・Review指摘反映・Documentation）／ChatGPT（Architecture Review）／ユーザー（最終承認）
状態：**Design Freeze（Architecture Review 3 Approved・Test Review 2 Approved・Code Review 2 Approved・Release Review 1 Approved）／Release完了**
分類：**Architecture Release**（development_workflow.md 6章・7章。新規独立package・新規Public APIの確立を伴うため）
AI構成：GPT-5.6 Sol／推論：中程度

---

## 1. Release概要

外部API（OpenAI Images API等）を一切呼び出さない、Provider非依存の画像生成Contractのみを定義する独立Foundationを追加する。

```text
prompt（str）
    ↓
AIImageGenerator.generate()  ← Protocol（型・メソッドContractのみ）
    ↓
GeneratedImage（image_bytes / mime_type）
```

本Releaseは**Consumer-less Foundation**である。具象Generator実装（OpenAI等）・既存WordPress連携（`wordpress_media` / `WordPressOutput`）・記事生成Pipeline・`image_resolver.py`・`ArticleData`のいずれへも配線しない。

## 2. Release分類

**Architecture Release**（development_workflow.md 6章・7章）。新規独立package（`src/ai_image_generation/`）の追加、新規Public API（`GeneratedImage` / `AIImageGenerator`）の確立を伴うため、v6.3.0（Retry Metrics Foundation）以降一貫している「新規パッケージ追加はArchitecture Releaseに分類する」という既存precedentに合致する。Fast Track候補条件（development_workflow.md 7章、Layer変更なし等8項目）のうち「Layer変更なし」に明確に抵触するため、Fast Trackの余地はない。

## 3. Status

```text
Architecture Design：Completed
Architecture Review：Approved
Test Review：Approved
Implementation：Completed
Code Review：Approved
Release Review：Approved
```

## 4. Background（現状と背景）

Release 6.9（WordPress Media Upload Foundation）は、画像bytesをWordPress Media Libraryへアップロードする`WordPressMediaUploader.upload(image_bytes, filename, mime_type)`をConsumer-less Foundationとして確立した。しかし、その`image_bytes`を実際に生成する手段は現時点でプロジェクト内に存在しない。ROADMAP.mdは次候補として「AI Image Generation Foundation」を明示しているが、外部画像生成APIの選定・費用・レート制限は本Releaseの対象外とし、まず「画像生成要求と結果の最小Contract」だけを外部I/Oなしで確定させる段階分割を採用する。

既存4package（`wordpress_media` / `retry_notification` / `retry_notification_message` / `retry_alert`）を横断調査した結果：

- `retry_alert` / `retry_notification` / `retry_notification_message`の3packageは、単一メソッドのStateless Judgment/Value Building Onlyクラス＋frozen dataclass値オブジェクトという同型構成であり、独自例外を持たず標準`ValueError`のみを使用する。`typing.Protocol` / `abc.ABC`の使用例はない。
- `wordpress_media`のみ外部I/Oを伴うため、専用例外（`WordPressMediaUploadError`）・`from_env()`・状態を持つコンストラクタという異なる構造を持つ。
- 本Releaseは外部I/Oを持たないが、「複数Provider実装を将来受け入れるContract」という性質上、既存4packageのいずれとも完全には一致しない新規パターンとなる。

## 5. Problem Statement

記事のアイキャッチ画像をAIで生成する機能を将来追加するにあたり、OpenAI等の特定Providerへ直接結合した設計を最初に確定すると、Provider変更・複数Provider対応・テスト容易性のいずれにも手戻りが生じる。Provider実装に先立って、「画像生成要求（`prompt`）を受け取り、生成結果（`GeneratedImage`）を返す」という最小限のProvider非依存Contractを、外部I/Oを一切持たない形で先に固定する必要がある。

## 6. Goals

1. `prompt: str`を受け取り`GeneratedImage`を返す、という最小限のGenerator Contractを`typing.Protocol`として定義する
2. 生成結果Contract（`GeneratedImage`）を、後続の`WordPressMediaUploader.upload()`へ不自然なく渡せる形（`image_bytes` / `mime_type`）で定義する
3. WordPress固有の語彙（`filename`等）をAI Image Generation Domainへ漏らさない
4. Provider固有語彙（`size` / `quality` / `provider_options`等）をContractへ含めない
5. 現時点で消費者（具象Generator）が存在しない状態で、安全にContractのみを導入する（Foundation First）
6. 1 Release＝1目的を維持する

## 7. Non-Goals

21章 Out of Scopeに同じ。

## 8. Package Boundary

新規独立package：

```text
projects/03_game_content_ai/src/ai_image_generation/
├── __init__.py
├── generated_image.py       # GeneratedImage（frozen dataclass）
└── ai_image_generator.py    # AIImageGenerator（typing.Protocol）
```

`wordpress_media`・`outputs`のいずれの配下にも配置しない。理由：

- 画像生成とWordPress投稿・Media Uploadは別責務である
- 将来の複数Provider Adapter（OpenAI／Local／Other）から独立させる
- 既存`wordpress_media` / `WordPressOutput`へ依存しないFoundationとする

**循環import回避の検討**：`ai_image_generator.py`は`GeneratedImage`型を参照するため`generated_image.py`をimportするが、`generated_image.py`側は`ai_image_generator.py`を参照しない。依存は`ai_image_generator.py → generated_image.py`の一方向のみであり、循環importは構造的に発生しない。したがって`TYPE_CHECKING`ガードや文字列型注釈（forward reference）は不要と判断し、通常の`from .generated_image import GeneratedImage`のみを用いる（設計上の単純さを優先）。

## 9. Package root Public API

`src/ai_image_generation/__init__.py`から公開するのは次の2つのみとする。

```python
from .ai_image_generator import AIImageGenerator
from .generated_image import GeneratedImage

__all__ = [
    "GeneratedImage",
    "AIImageGenerator",
]
```

`ImageGenerationRequest`・`AIImageGenerationError`はいずれもexportしない（10章・11章参照）。利用側へ内部モジュールへの直接importを要求しない。

## 10. Public Model — GeneratedImage

```python
from dataclasses import dataclass, field


@dataclass(frozen=True)
class GeneratedImage:
    image_bytes: bytes = field(repr=False)
    mime_type: str

    def __post_init__(self) -> None:
        ...  # 13章 Validation Contract参照
```

契約：frozen／2フィールドのみ／フィールド順固定／`__post_init__`で構築時にfail-fast検証／Methodを追加しない。

`image_bytes` / `mime_type`は、後続の`WordPressMediaUploader.upload(image_bytes, filename, mime_type)`の引数名・型とそのまま対応しており、後続Wiringを不自然にしない。`filename`はWordPress固有の語彙であるため、`GeneratedImage`には含めない（14章）。

**repr Contract（Architecture Review 2反映）**：`image_bytes`は`field(repr=False)`によりdataclass標準reprから除外する。独自の`__repr__`は実装しない（`field(repr=False)`のみで目的を達成できるため）。

```text
repr()は正常に生成できる
mime_typeはreprに含まれてよい
image_bytesの値はreprに含まれない
```

目的：画像payloadを通常のdataclass reprへ出力しない／テスト失敗ログ等への画像bytes露出を防ぐ／巨大なreprを防ぐ／Security Contract（16章）と整合させる。これはTest Design（v6.10.0 Test Design案）で提示されたArchitecture Issue AI-1の解消である（34章参照）。

## 11. AIImageGenerator Contract

```python
from typing import Protocol


class AIImageGenerator(Protocol):
    def generate(self, prompt: str) -> GeneratedImage:
        ...
```

**採用形の確定理由（ChatGPT Architecture Review反映）**：

- `typing.Protocol`を採用し、`abc.ABC`は採用しない。Adapter実装側に継承を要求しない構造的型付け（Structural Typing）とすることで、Provider Adapterの実装負担を最小化する。
- `@runtime_checkable`は使用しない。本Contractの目的は静的な型契約であり、`isinstance()`検証を目的としたProduction API拡張は行わない。E2Eでは、Fakeの`generate()`を実際に呼び出し`GeneratedImage`が返ることを検証する方式を採る（`isinstance(fake, AIImageGenerator)`のような構造検査テストは行わない）。
- 引数は`prompt: str`のみの単純引数形式とし、`ImageGenerationRequest`のようなRequest Objectは導入しない（12章）。
- `AIImageGenerator`自体には入力検証コードを一切持たない。Protocolは型・メソッドシグネチャのContractのみを表現し、実行時検証は持てない（12章）。

**Public APIへ含めないもの（確定事項）**：

```text
ImageGenerationRequest
AIImageGenerationError
```

理由：
- Request Objectを必要とする複数入力（`size` / `quality`等）が、現時点でいずれの消費者にも存在しない
- 具象Generatorが存在せず、独自例外の送出元も存在しない
- 実際のFailure Contractは、外部API失敗を踏まえてOpenAI Image Generation Adapter Foundationで定義する方が自然
- 将来必要になる可能性だけを理由にPublic APIを増やさない

## 12. Prompt Contract

**重要な設計判断**：`typing.Protocol`は型・メソッドシグネチャのContractのみを表現でき、実行時の入力検証コードを持てない。したがって、本Releaseで**実装される保証**と、将来Adapterが**守るべきContract**を明確に分離する。

**今回実装するもの（production code）**：

```text
generate(prompt: str) -> GeneratedImage という型・メソッドContractのみ
```

`prompt`のValueError検証ロジックは、本Releaseのproduction codeに一切追加しない。

**設計書に記録する、将来Adapter向けPrompt Contract（今回は未実装）**：

```text
promptはstr型
非空
空白のみ不可
前後空白の自動stripはしない
NUL文字（\x00）を拒否する
改行（\n）とtab（\t）は許可する
最大長はProvider Adapter側で定義する（Provider非依存Contractとしては固定しない）
Moderation（内容の安全性判定）は行わない
著作権・商標判定は行わない
```

このContractは、後続のOpenAI Image Generation Adapter Foundation等、具象Generatorを実装するReleaseが従うべき規約として記録するものであり、本Releaseの`AIImageGenerator` Protocol自体にはいかなる検証コードも伴わない。E2Eでも、Protocolが空文字列やNUL文字を拒否するかどうかのテストは行わない（それらは具象Adapterが存在する後続Releaseの責務であり、Protocol自体を検証する対象ではない）。

## 13. GeneratedImage Validation Contract

`GeneratedImage.__post_init__`で、構築時にfail-fastで検証する。

### image_bytes

```text
厳密にbytes型
非空必須
```

拒否：`str` / `bytearray` / `memoryview` / `None` / `bytes`のsubclass / 空bytes。

型検証は`type(value) is bytes`とし、`bytes`そのものだけを許可する（`isinstance(value, bytes)`は`bytearray` / `memoryview`は自然に除外するが、`bytes`のsubclassは許可してしまうため、「厳密にbytes型」という文章Contractを実装するには`type()`比較が必要。Code Review 1反映）。Release 6.9（`wordpress_media`）の`_validate_image_bytes`は`isinstance()`を用いているが、本Foundationは「厳密にbytes型」という独自のContractを持つため、`wordpress_media`とは異なる検証方式を採用する。

### mime_type

**canonical MIME正規表現をSource of Truthとして採用する（Architecture Review 2反映）**。Test Design（v6.10.0 Test Design案）で提示されたArchitecture Issue AI-2〜AI-5（Unicode制御文字の範囲未定義／`"image/"`単独の許可可否未定義／`"image//png"`の許可可否未定義／MIME parameter付き値の許可可否未定義）は、旧来の「`"image/"`で始まる」という緩いprefix検証と「制御文字なし」という曖昧な文言のみでは一意に解決できなかった。これを解消するため、`"image/"`prefixのみの検証を廃止し、次の正規表現を最終的なSource of Truthとする。

```python
_MIME_TYPE_PATTERN = re.compile(r"^image/[A-Za-z0-9][A-Za-z0-9._+-]*$")
```

Contract（すべてこの正規表現1本へ集約される）：

```text
厳密にstr型
非空
前後空白なし
ASCII文字のみ（Unicodeを含む文字は構造的に拒否される）
typeは小文字のimage
typeとsubtypeの区切りslashは1個
subtypeは非空
MIME parameter（; や = を含む付加情報）を含まない
自動stripしない
自動小文字化しない
```

検証順序（fail-fastで最初に該当した条件を`ValueError`とする）：

```python
import re

_MIME_TYPE_PATTERN = re.compile(r"^image/[A-Za-z0-9][A-Za-z0-9._+-]*$")


def __post_init__(self) -> None:
    if type(self.image_bytes) is not bytes:
        raise ValueError("image_bytes must be bytes")
    if len(self.image_bytes) == 0:
        raise ValueError("image_bytes must not be empty")

    if not isinstance(self.mime_type, str):
        raise ValueError("mime_type must be str")
    if not _MIME_TYPE_PATTERN.fullmatch(self.mime_type):
        raise ValueError("mime_type must match canonical image MIME type syntax (image/<subtype>)")
```

**Code Review 1反映（既存Contractとの整合修正）**：`image_bytes`の型検証は`isinstance(self.image_bytes, bytes)`ではなく`type(self.image_bytes) is not bytes`を用いる。本節冒頭の文章Contract「厳密にbytes型」は当初から変更していないが、`isinstance()`は`bytes`のsubclassを許可してしまうため、文章Contractと実装が一致していなかった。`type(x) is bytes`は`bytes`そのものだけを許可し、`bytes`のsubclassを含め、それ以外の型はすべて拒否する。これはArchitecture変更ではなく、既存Contractとの整合修正である。

`_MIME_TYPE_PATTERN.fullmatch()`は、非空・前後空白なし・ASCII限定・小文字`image`固定・slash1個・subtype非空・parameter非許可・制御文字（CR・LF・tab・NUL・DEL・その他ASCII制御文字）非許可のすべてを1つの正規表現で表現する。個別の`strip()`比較や制御文字ループ判定は不要となり、正規表現が唯一の判定根拠となる。

**許可例**：

```text
image/png
image/jpeg
image/webp
image/avif
image/svg+xml
image/x-icon
image/x-custom-format
image/vnd.example.format
```

**拒否例**（少なくとも次を拒否する）：

```text
None
整数
bytes
image/（subtypeなし）
image//png（区切りslashが2個）
image/png; charset=x（MIME parameter）
image/png;foo=bar（MIME parameter）
image/ png（空白混入）
Image/png（大文字始まり）
 image/png（前後空白）
image/png （前後空白）
text/plain（image/で始まらない）
application/json（image/で始まらない）
image/画像（Unicode文字を含む）
CR／LF／tab／NUL／DELを含む値
```

**MIME個別形式の許可リストは固定しない**。`image/png` / `image/jpeg` / `image/webp`のような既知3形式だけに限定せず、canonical正規表現を満たす未知のsubtype（例：`image/x-custom-format`）も許可する。特定3形式への限定はWordPress側の実務的制約であり、Provider非依存Domainの本質的な制約ではないと判断したため（Media Upload Wiring段階でWordPress側の実際の受理可否を別途検証する）。ただし、canonical構文自体（slash1個・subtype非空・parameter非許可・ASCII限定）は本Releaseで厳密に強制する。

## 14. GeneratedImageに含めないField

次はいずれも含めない。

```text
filename
filename_extension
width
height
provider
model
usage
revised_prompt
size
quality
output_format
metadata
provider_options
```

理由：

- 現在のConsumerが必要としていない（現時点でいずれの消費者にも存在しない）
- `filename`はWordPress Media Upload Wiring側の責務であり、AI Image Generation Domainへ漏らさない
- `filename_extension`は`mime_type`との二重状態を避けるため含めない。拡張子導出が必要になった場合は、後続のMedia Upload Wiring Releaseが`mime_type`から決定的に導出する
- `provider` / `model` / `usage` / `revised_prompt` / `provider_options`等のProvider固有情報をDomain Contractへ漏らさない
- `size` / `quality` / `output_format`はRequest Object不採用（11章）と対をなす判断であり、現時点で消費者が存在しない

## 15. Failure Contract

```text
GeneratedImage構築時の入力不正：ValueError
```

Protocol（`AIImageGenerator.generate()`）呼び出し時の実行失敗については、具象実装が本Releaseに存在しないため定義しない。独自例外（`AIImageGenerationError`等）は今回導入しない。後続のOpenAI Image Generation Adapter Foundationにおいて、実際の外部API失敗（Timeout・Rate Limit・認証エラー等）を踏まえて設計する。

## 16. Security Contract

本Releaseのproduction codeは外部API・秘密情報・HTTP responseを一切扱わない。ただし、Security Contractは本Releaseにも明確に適用する（Architecture Review 2反映）。

**本Releaseへ適用されるSecurity Contract**：

```text
GeneratedImageはimage_bytesを保持する
ただしimage_bytesはreprへ含めない（10章、field(repr=False)）
logging／printは実装しない
画像bytesを例外メッセージへ含めない（GeneratedImage構築時のValueErrorは
固定メッセージのみとし、image_bytesの値そのものを埋め込まない）
```

**将来Adapter向け設計ガイダンス**（後続のOpenAI Image Generation Adapter Foundation等が従うべき指針）：

将来の例外・Result・ログへ含めてはいけないもの：

```text
prompt全文
image_bytes
Base64画像
API key
認証情報
provider response全体
```

本Releaseは`logging` / `print`のいずれも実装しない。

## 17. Side Effect／I/O Contract

許可される外部I/O：**なし**。

禁止：HTTP通信／ファイル読込／ファイル書込／Path操作／一時ファイル／URLダウンロード／画像加工／ログ出力／標準出力／標準エラー出力／`subprocess`。

## 18. Dependency Direction

```text
許可：
ai_image_generation → Python standard library のみ（typing, dataclasses等）

禁止：
ai_image_generation → wordpress_media
ai_image_generation → outputs
ai_image_generation → image_resolver
ai_image_generation → ArticleData
ai_image_generation → Workflow
ai_image_generation → Scheduler
ai_image_generation → Retry Runtime
ai_image_generation → requests
ai_image_generation → openai
ai_image_generation → anthropic
ai_image_generation → Pillow
ai_image_generation → 外部HTTPライブラリ全般
```

E2EのDependency Guardは、Release 6.9（Code Review反映）と同様に、ソース文字列検索ではなく`ast.Import` / `ast.ImportFrom`ノード解析で禁止importを検知する。既存側から`ai_image_generation`への新規importも本Releaseでは行わない（Wiringは対象外）。

## 19. Compatibility

既存production codeは無改修である：`wordpress_media` / `WordPressOutput` / `image_resolver.py` / `ArticleData` / 記事生成Pipeline / Workflow / Scheduler / Retry Runtime。すべて既存動作を維持する。新規独立packageの追加のみであり、既存の呼び出し元（現状ゼロ）にも影響しない。

## 20. In Scope

```text
src/ai_image_generation/__init__.py
src/ai_image_generation/generated_image.py
src/ai_image_generation/ai_image_generator.py
GeneratedImage
AIImageGenerator
GeneratedImageの入力検証（__post_init__）
Public API export（__all__）
標準ライブラリのみへの依存
Consumer-less Foundation
新規E2E Test（外部I/Oなし）
AST Dependency Guard
正式Architecture Design文書（本文書）
実装後のROADMAP／architecture／CHANGELOG統合方針
```

## 21. Out of Scope

```text
ImageGenerationRequest
AIImageGenerationError
OpenAI SDK
OpenAI Images API
HTTP通信
API key
モデル名
料金計算
Rate Limit
Retry
Timeout
Base64解析
URL download
一時ファイル
ファイル保存
Pillow
画像リサイズ
画像圧縮
画像形式変換
複数画像生成
画像選択
再生成ループ
prompt自動生成
記事本文からのprompt生成
Moderation API
著作権判定
商標判定
WordPressMediaUploader呼び出し
Media Library upload
ArticleData変更
image_resolver.py変更
WordPressOutput変更
featured_media設定
既存投稿Pipeline変更
Workflow統合
Scheduler統合
Retry Runtime統合
SNS Integration
promptの実行時ValueError検証
```

## 22. E2E Test Strategy（概要）

詳細なScenario設計はTest Design（別工程）で確定する。本章では検証すべきカテゴリのみを記録する。まだtestは作成しない。

```text
PKG：
  package import
  Public API export（GeneratedImage / AIImageGeneratorの2つのみ）
  __all__の集合一致

GI：
  GeneratedImage正常構築
  frozen dataclassであること（再代入不可）
  等価性（同一値での比較）
  repr()を正常に呼び出せる
  reprにmime_typeが含まれる
  reprにimage_bytesの値が含まれない（field(repr=False)のContract確認）
  未知だが構文的に正しいimage/*サブタイプを許可する（許可リスト非固定の確認）
  image_bytes型検証（bytes以外を拒否。type(value) is bytesによる厳密検証のため、
  bytesのsubclassも拒否することを含む）
  image_bytes非空検証
  mime_type型検証（str以外を拒否）
  mime_typeがcanonical正規表現（^image/[A-Za-z0-9][A-Za-z0-9._+-]*$）を
  満たさない場合の拒否。少なくとも次を含む：
      image/（subtypeなし）
      image//png（区切りslashが2個）
      image/png; charset=x（MIME parameter）
      image/png;foo=bar（MIME parameter）
      image/ png（空白混入）
      Image/png（大文字始まり）
      前後空白混入
      text/plain／application/json（image/で始まらない）
      Unicodeを含む値（例：image/画像）
      CR／LF／tab／NUL／DELを含む値

PROTO：
  AIImageGeneratorがtyping.Protocolとして定義されていること
  @runtime_checkableではないこと
  test file内Fakeがgenerate(prompt)を実装できること（構造的適合）
  Fakeへpromptがそのまま渡り、GeneratedImageが返ることを確認する
  Fakeをproduction package（src/ai_image_generation/）へ置いていないことの確認

DEP（AST：ast.Import／ast.ImportFrom解析）：
  standard library以外へのproduction dependencyがないこと
  禁止package（wordpress_media/outputs/image_resolver/ArticleData/Workflow/
  Scheduler/Retry Runtime/requests/openai/anthropic/Pillow）への
  importがないこと
  外部HTTPライブラリへのimportがないこと

SIDE（AST：print()／open()はast.Call解析、logging／subprocessは
  ast.Import／ast.ImportFrom解析）：
  print()呼び出しがないこと
  open()呼び出しがないこと
  loggingのimportがないこと
  subprocessのimportがないこと
```

**注意事項（E2Eで行わないこと）**：

```text
@runtime_checkableを使用したisinstance(fake, AIImageGenerator)検証は行わない
Protocolがprompt入力値（空文字・NUL等）を検証するという誤ったテストは作らない
```

実装環境や外部Providerへの通信は行わない（本Release自体が外部I/Oを持たないため、モック化の対象自体が存在しない）。Working Tree／`git diff`状態は恒久E2Eへ含めない。

## 23. Regression Strategy

```text
既存Regression：v1.11.0〜v6.9.0（前回報告時点の合計 1514/1514 PASS）
```

次を確認する：ベースライン件数不変・FAILなし・終了コード0・警告なし・Tracebackなし・既存Regressionファイル無改修。既存production code無改修の確認は、Release Review時に`git diff --name-status` / `git status --short`で行う（恒久E2EへGit状態を含めない）。

## 24. Documentation Strategy

Release 6.10で更新予定の文書：

```text
projects/03_game_content_ai/docs/design/ai_image_generation_contract_foundation.md（本文書）
projects/03_game_content_ai/docs/architecture.md
projects/03_game_content_ai/docs/ROADMAP.md
projects/03_game_content_ai/docs/CHANGELOG.md
```

本工程（Architecture Design）では、新規設計書（本文書）のみを作成する。`architecture.md` / `ROADMAP.md` / `CHANGELOG.md`の更新は、Architecture Review Approved後、実装完了後のDocumentation Update工程で行う。

## 25. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| `@runtime_checkable`不使用のため、将来Adapterが`generate()`のシグネチャを誤って実装しても実行時には検出されない | E2EでFakeの`generate()`を実際に呼び出し`GeneratedImage`が返ることを検証する。型チェッカー（mypy等）の運用は将来的な補完手段として別途検討する |
| Public APIを2型に限定した結果、将来Adapterごとに異なる例外設計・入力検証設計になり一貫性が失われる可能性 | Security Contract（16章）とPrompt Contract（12章）を本Releaseから文書化し、将来Adapter Foundationが従うべき指針として残す |
| `mime_type`に個別形式の許可リストを持たないため、canonical構文（`^image/[A-Za-z0-9][A-Za-z0-9._+-]*$`）を満たす限り`"image/x-completely-invalid"`のような意味的に無効な値も通過する（構造的に不正な値`"image/"` `"image//png"` `"image/png; charset=x"`等はAD-7改訂により拒否される） | 実際のMedia Upload Wiring段階で、WordPress側が受理するMIME種別との整合を別途検証する |
| Prompt Contract（12章）が今回のproduction codeで一切検証されないため、具象Adapter側の実装漏れリスクが残る | Contractを設計書へ明記し、後続Adapter FoundationのArchitecture Reviewで検証実装の有無を確認する |

## 26. Alternatives Considered

本Releaseの初期提案（チャットベースのArchitecture Design案）に対するChatGPT Architecture Reviewで「Changes Required」を受け、以下の3案を比較のうえ確定した。

| # | 案 | 概要 |
|---|---|---|
| 1 | Request Object＋Protocol | `ImageGenerationRequest(prompt, size, quality, output_format)`を`AIImageGenerator.generate()`の引数とする |
| 2 | 単純引数＋Protocol | `generate(self, prompt: str) -> GeneratedImage`のみ |
| 3 | 具象Service Contractのみ | `Protocol`／`ABC`を定義せず、規約を文書のみで表現する |

| 観点 | 案1 | 案2 | 案3 |
|---|---|---|---|
| 現在の必要性 | `prompt`以外に消費者なし | `prompt`のみで要求を満たす | 満たすが型契約なし |
| Provider非依存性 | `size`/`quality`/`output_format`がProvider語彙の漏洩リスク | 高い | 高いが型で保証されない |
| 過剰抽象化 | 未使用fieldを含み禁止方針（本文書14章）に抵触 | 低い | 最も低いが型Contract不在 |
| API安定性 | 未使用field分、将来の変更対象が広い | 必要最小限 | 型自体がなく議論の土台が弱い |
| 既存プロジェクトとの整合 | 直接の先例なし | 直接の先例なし（ただしROADMAP記載のv4.5.0 `RetryDecisionPolicy`がProtocol使用の先例） | retry_alert等4packageの表面的パターンと最も一致 |

**確定（ChatGPT Architecture Review反映）**：案2（単純引数＋Protocol）を採用する。`ImageGenerationRequest`（案1）は複数入力を必要とする具象消費者が存在しない現時点では過剰抽象化と判断し、不採用とした。案3（Protocolなし）は、本Releaseが「複数Provider実装を将来受け入れるContract」を目的とする以上、最低限の型契約（Protocol）を持たないことは目的と矛盾すると判断し、不採用とした。

## 27. Technical Debt

```text
promptの実行時検証（非空・NUL拒否等）は本Releaseでは未実装
GeneratedImageのmime_typeに個別形式（png/jpeg/webp等）の許可リストがなく、
canonical構文を満たす任意の"image/*"文字列（例：image/x-completely-invalid）
を構造的に受理する
GeneratedImageからfilenameを導出する手段（拡張子マッピング含む）が未定義
複数Provider Adapterが実際に揃った際のFailure Contract統一方針が未定義
```

## 28. Known Issues

```text
promptの実行時入力検証はAdapter未実装のため未提供
prompt最大長はProvider Adapterで定義予定
独自実行例外はAdapter Foundationで定義予定
MIME typeはcanonical正規表現（image/<subtype>）による構文検証のみで、
個別形式（png/jpeg/webp等）の許可リストは導入していない
filename生成はMedia Upload Wiringで対応予定
外部API Adapter未実装
Media Upload Wiring未実装
featured_media Wiring未実装
```

## 29. Future Extensions

```text
OpenAI Image Generation Adapter Foundation
必要に応じたLocal／Other Provider Adapter
Generated Image → WordPress Media Upload Wiring
Article → featured_media Wiring
必要性が生じた場合のImageGenerationRequest導入
Adapter実装時のAIImageGenerationError追加
```

順序は確定事項として固定しない。

## 30. Open Questions

```text
本文書提出時点で未解決のOpen Questionなし
```

Test Design（v6.10.0 Test Design案）で提示された5件のArchitecture Issueは、本改訂で以下の通りすべて解消済みである（Open Questions／Known Issuesへ未解決のまま残していない）。

```text
AI-1（GeneratedImage.__repr__とSecurity Contractの関係） → AD-13で解消
      image_bytesをfield(repr=False)でreprから除外する設計を採用
AI-2（mime_type制御文字の範囲、Unicode C1／Cf category） → AD-7改訂で解消
      canonical正規表現（ASCII限定）採用によりUnicode文字は構造的に拒否
AI-3（"image/"単独の許可可否） → AD-7改訂で解消（拒否と確定）
AI-4（"image//png"の許可可否） → AD-7改訂で解消（拒否と確定）
AI-5（MIME parameter付き値の許可可否） → AD-7改訂で解消（拒否と確定）
```

次回Architecture Reviewでの追加指摘の有無は、本文書提出後に確定する。

## 31. Architecture Decision Summary

| # | 内容 |
|---|---|
| AD-1 | Package配置：`src/ai_image_generation/`独立package |
| AD-2 | Public API：`GeneratedImage`と`AIImageGenerator`の2型のみ（`ImageGenerationRequest` / `AIImageGenerationError`は今回含めない） |
| AD-3 | Generator Contract形式：`typing.Protocol`（`abc.ABC`不採用、`@runtime_checkable`不使用） |
| AD-4 | Generator入力：単純引数`prompt: str`（Request Object不採用） |
| AD-5 | Prompt実行時検証：本Releaseでは実装しない。型・メソッドContractのみとし、実行時検証規約は将来Adapter向けGuidanceとして文書記録のみ行う |
| AD-6 | GeneratedImage検証：`__post_init__`で`image_bytes` / `mime_type`双方をfail-fast検証 |
| AD-7 | mime_type Contract：**（Architecture Review 2改訂）** canonical正規表現`^image/[A-Za-z0-9][A-Za-z0-9._+-]*$`をSource of Truthとして採用。旧`"image/"`prefixのみの検証を廃止し、`"image/"`単独・`"image//png"`・MIME parameter付き値・Unicode文字を含む値をいずれも構造的に拒否する。個別形式（png/jpeg/webp等）の許可リストは引き続き導入しない |
| AD-8 | GeneratedImageに含めないfield：`filename` / `filename_extension` / `width` / `height` / `provider` / `model` / `usage` / `revised_prompt` / `size` / `quality` / `output_format` / `metadata` / `provider_options` |
| AD-9 | Failure Contract：`GeneratedImage`構築時の入力不正のみ`ValueError`、専用例外は今回導入しない |
| AD-10 | Dependency Contract：標準ライブラリのみ許可、他の全package・全外部ライブラリを禁止 |
| AD-11 | Fake配置：production packageへ配置しない（test file限定） |
| AD-12 | 循環import：`ai_image_generator.py → generated_image.py`の一方向依存のみのため、`TYPE_CHECKING`等の特別な型注釈方式は不要と判断 |
| AD-13 | repr Contract：`GeneratedImage.image_bytes`を`field(repr=False)`でreprから除外する。独自`__repr__`は実装しない。`mime_type`はreprに含まれてよい（Test Design AI-1の解消） |
| AD-14 | image_bytes型検証：**（Code Review 1改訂）** `type(self.image_bytes) is not bytes`を採用し、`bytes`そのものだけを許可する。`isinstance()`は`bytes`のsubclassを許可してしまい「厳密にbytes型」という文章Contractと不一致だったため、既存Contractとの整合修正として`type()`比較へ変更した。`wordpress_media._validate_image_bytes`（`isinstance()`使用）とは意図的に異なる検証方式である |

## 32. Implementation File Plan

**新規production code**（Architecture Review・Test Review承認後に作成）

```text
projects/03_game_content_ai/src/ai_image_generation/__init__.py
projects/03_game_content_ai/src/ai_image_generation/generated_image.py
projects/03_game_content_ai/src/ai_image_generation/ai_image_generator.py
```

**新規テスト**（同上）

```text
projects/03_game_content_ai/tests/test_e2e_v6_10_0_ai_image_generation_contract_foundation.py
```

**変更なし（既存無改修方針）**

```text
src/wordpress_media/（全ファイル）
src/outputs/wordpress_output.py
src/image_resolver.py
src/outputs/base.py（ArticleData）
既存記事生成Pipeline全体
Workflow / Scheduler / Retry Runtime全体
既存テストファイル一式
requirements.txt
.env関連
```

## 33. Acceptance Criteria

```text
新規packageのみでproduction機能が完結する
既存production codeを変更しない
既存testを変更しない
Public APIがGeneratedImageとAIImageGeneratorの2つだけである
外部dependencyがない（標準ライブラリのみ）
外部I/Oがない
GeneratedImage.image_bytesがreprへ含まれない
mime_typeがcanonical MIME正規表現（^image/[A-Za-z0-9][A-Za-z0-9._+-]*$）を満たす
不正MIME構文がValueErrorで拒否される
新規E2Eが全PASSする
既存Regressionが全PASSする
Architecture Reviewが承認される
Test Reviewが承認される
Code Reviewが承認される
Release Reviewが承認される
```

## 34. Review History

```text
Architecture Review 1（チャットベース初期提案に対するReview）：Changes Required
    指摘反映（本文書での対応）：
    1. Public APIをGeneratedImageとAIImageGeneratorの2つへ縮小
       （ImageGenerationRequest・AIImageGenerationErrorを除外） → 9, 11章
    2. 設計案を単純引数＋Protocolへ確定（Request Object不採用） → 26章
    3. Prompt Contractは型／メソッドContractのみ実装し、実行時検証は
       将来Adapter Foundationへ委譲する方針を明記 → 12章
    4. GeneratedImageのmime_type検証を"image/"prefixチェックへ限定し、
       個別形式の許可リスト固定を不採用とした → 13章
    5. @runtime_checkable不使用を明記し、isinstance()検証を目的とした
       Public API拡張を行わない方針を明記 → 11章
    6. GeneratedImageに含めないfieldを明示列挙 → 14章
    7. Acceptance Criteriaの「既存docs無変更」という記載が、実装後の
       ROADMAP／architecture／CHANGELOG更新方針と矛盾していたため、
       「既存production code・既存testは変更しない」という趣旨へ修正 → 33章
    状態：反映済み（本文書に統合）

Architecture Review 2（Test Design案と同時提出分に対するReview）：Changes Required
    Test Design自体の方向性は適切と評価されたが、Test Designで発見された
    Architecture Issue 5件を正式設計書へ反映する必要があると指摘された。
    指摘反映（本文書での対応）：
    1. AI-1：GeneratedImage.image_bytesをfield(repr=False)でreprから除外
       する設計へ変更。独自__repr__は実装しない → 10章, 16章, AD-13
    2. AI-2：mime_type制御文字（Unicode C1／Cf category含む）の範囲未定義を
       解消。canonical正規表現の採用によりASCII以外の文字を構造的に拒否
       → 13章, AD-7
    3. AI-3：`"image/"`単独の値は拒否と確定 → 13章, AD-7
    4. AI-4：`"image//png"`のような区切りslash複数値は拒否と確定
       → 13章, AD-7
    5. AI-5：`"image/png; charset=x"`等のMIME parameter付き値は拒否と確定
       → 13章, AD-7
    その他反映：
    - Security Contract（16章）へ、本Release自体に適用される具体的規約
      （image_bytes非repr化・非logging・非print・例外への非露出）を追加
    - E2E Test StrategyのGIカテゴリへrepr関連・MIME構文異常系Scenarioを
      追加、PROTOカテゴリへ@runtime_checkable非使用の明示とprompt
      pass-through確認を追加（22章）
    - Acceptance Criteriaへrepr Contract・MIME正規表現Contract関連の
      3項目を追加（33章）
    状態：5件とも Resolved（本文書に統合）

Architecture Review 3（本文書改訂版に対するReview）：Approved
    AI-1〜AI-5の反映内容（10章・13章・16章・22章・33章・AD-7・AD-13）が
    承認された。

Test Review 1（初回Test Design案に対するReview、Architecture Review 2と
同時実施）：Changes Required
    Test Design自体の方向性は適切と評価されたが、Test Designで発見された
    Architecture Issue（AI-1〜AI-5）が正式設計書へ未反映であったため、
    Architecture Review 2の指摘と合わせてChanges Requiredとされた。
    状態：Architecture Review 2での指摘反映（本文書改訂）と合わせてResolved

Test Review 2（修正版Test Design案に対するReview、Architecture Review 3と
同時実施）：Approved
    37 Scenario／69 Case／約77 Assertion見積りのTest Design
    （PKG5・GI正常系12・GI異常系9〔27 Case〕・PROTO4・DEP3・SIDE4）が
    承認された。

Code Review 1：Changes Required
    指摘（Blocking Issue 1件）：
        承認済みContractの「image_bytesは厳密にbytes型」と、production codeの
        isinstance()実装が一致していなかった（isinstance()はbytesのsubclassを
        許可してしまう）。
    対応：
        - `generated_image.py`の型検証を`isinstance(self.image_bytes, bytes)`
          から`type(self.image_bytes) is not bytes`へ変更（13章, AD-14）
        - 新規E2Eへbytes subclass拒否Case（GI-IB-TYPE内）を追加
        - 本設計書13章のサンプルコード・拒否例・22章E2E Test Strategyを
          type()比較へ整合修正
    状態：production・E2E・設計書とも反映済み。次回Code Review待ち
    （Architecture変更ではなく、既存Contractとの整合修正として扱う）

Code Review 2：Approved
    Code Review 1の指摘だったimage_bytes厳密型Contractの不一致が解消済みであることを確認。
        production code：`isinstance(self.image_bytes, bytes)`から
            `type(self.image_bytes) is not bytes`へ修正済み
        E2E：bytes subclass拒否Case（GI-IB-TYPE内）追加済み
        新規E2E：37 Scenario／70 Case／78 Assertion、78/78 PASS、0 FAIL
        Regression：1514/1514 PASS
    Blocking Issueなし。

Release Review 1：Approved
    確認内容：
        Architecture Designからの逸脱：なし
        新規E2E：37 Scenario／70 Case／78 Assertion、78/78 PASS、0 FAIL
        Regression：1514/1514 PASS
        新規E2E込み：1592/1592 PASS
        Documentation Integration：ROADMAP／architecture／CHANGELOG整合済み
        Blocking Issue：なし
    状態：Approved（Release完了）
```

本文書はArchitecture Review・Test Review・Code Review・Release Reviewのすべてに承認済み（Architecture Review 3 Approved・Test Review 2 Approved・Code Review 2 Approved・Release Review 1 Approved）である。Code Review 1で指摘された「image_bytesは厳密にbytes型」というContractとisinstance()実装との不一致は、`type(value) is bytes`への修正とbytes subclass拒否E2E追加により解消し、Code Review 2でApprovedとなった。ROADMAP.md／architecture.md／CHANGELOG.mdへのDocumentation Integrationを実施し、新規E2E（37 Scenario／70 Case／78 Assertion、78/78 PASS）・既存Regression（v1.11.0〜v6.9.0、1514/1514 PASS、新規E2E込み合計1592/1592 PASS）とも完全PASSを確認した。Architecture Designからの逸脱はなく、Release Review 1でApprovedとなり、Release v6.10.0「AI Image Generation Contract Foundation」は正式完了した。
