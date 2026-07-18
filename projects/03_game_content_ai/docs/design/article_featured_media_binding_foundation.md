# Article Featured Media Binding Foundation — Architecture Design（v6.13.0）

作成日：2026-07-18
作成者：Claude Code（Architecture Designドラフト／Implementation／新規E2E作成／Code Review／Non-Blocking Finding修正／Formal Regression／Documentation Integration）／ChatGPT（Architecture Review：Approved）／ユーザー（最終承認：未実施）
状態：**Release Completed（Release Review Approved）**
分類：**Architecture Release**（development_workflow.md 6章・7章。新規独立package・新規Public API・新規Dependency方向の確立を伴うため）

---

## 0. Header

```text
Release：6.13
Version：v6.13.0
正式名称：Article Featured Media Binding Foundation
Classification：Architecture Release
Status：Release Completed（Documentation Integration Completed・Release Review Approved）
Architecture Design：Completed
Architecture Review状態：Approved（Blocking Issueなし、Critical 0件・Major 0件・
    Minor 2件（AR-m-1, AR-m-2）・Suggestion 2件（AR-S-1, AR-S-2）、
    いずれもNon-Blocking。4件とも本Implementation工程で正式設計書へ反映済み）
Production Implementation：Completed
New E2E：PASS（24シナリオ・Validation展開13ケース・123アサーション・123/123 PASS）
Code Review状態：Approved（Blocking Issueなし、Critical 0件・Major 0件・
    Minor 4件（CR-m-1, CR-m-2, CR-m-3, CR-m-4）・Suggestion 1件（CR-S-1）、
    いずれもNon-Blocking。CR-m-1／CR-m-2／CR-m-3は本Non-Blocking Finding修正工程で
    反映済み。CR-m-4（Implementation報告内の集計記載ミス、ファイル修正対象なし）・
    CR-S-1（dataclasses.fields()のvacuous pass耐性強化）はDeferred）
Formal Regression状態：PASS（正式対象16ファイル、既存15ファイル1931/1931 PASS＋新規
    v6.13 E2E 123/123 PASS＝総合2054/2054 PASS、FAIL 0・Warning 0・終了コード非0
    なし）
Documentation Integration状態：Completed（docs/ROADMAP.md・docs/architecture.md・
    docs/CHANGELOG.mdへ反映済み。Architecture変更なし、Blocking Issueなし）
Release Review状態：Approved（Critical 0件・Major 0件・Minor 0件・Suggestion 0件、
    Blocking Issueなし、Open Questionsなし。Architecture Designからの逸脱なし・
    Public Contract変更なし・Production Scope変更なし・Out of Scope混入なし。
    Release成果物7ファイル全体を承認）
```

### 0.1 Release名称の確定経緯

候補調査プロンプトが提示した暫定名称は次の2案だった。

```text
暫定名称：Media Upload Result Article Featured Media Wiring Foundation
短い代替名称：Article Featured Media Binding Foundation
```

本文書では**「Article Featured Media Binding Foundation」を正式名称として採用する**。理由：

1. Public APIの動詞（後述10章）を`bind_featured_media()`とする設計と名称が一致し、責務が名前から一意に読み取れる
2. 「Wiring」という語は、v6.12（Generated Image WordPress Media Upload Wiring Foundation）で「既存2 Foundation間の橋渡し」を指す語として既に使われている。本Releaseも性質としては橋渡し（`ArticleData` + `MediaUploadResult` → 新しい`ArticleData`）だが、候補調査で「Wiring」という語がProduction Runtimeへの接続（image_resolver改修・main.py接続等）を連想させる誤解を招いた経緯（Release 6.13候補調査 Finding M-1）があるため、本Releaseでは意図的に避ける
3. 「Media Upload Result」を名称冒頭に含めると名称が長くなり、`docs/ROADMAP.md`・`CHANGELOG.md`等の一覧表示で可読性が下がる。責務は「ArticleDataのfeatured_media」を確定させることであり、入力の一つ（`MediaUploadResult`）を名称に含める必然性は低い
4. 設計書ファイル名も、正式名称の責務に合わせて`article_featured_media_binding_foundation.md`とする（候補調査プロンプトが示した`media_upload_result_article_featured_media_wiring_foundation.md`から変更）

---

## 1. Purpose

`WordPressMediaUploader.upload()`（v6.9.0）の成功結果である`MediaUploadResult.media_id`を、既存の`ArticleData.featured_media_id`（v1.6.0で追加済みのfield）へ安全に反映するための、専用のstateless Binding機能を確立する。

本Releaseが確立するのは、次の純粋なContractのみである。

```text
ArticleData
MediaUploadResult
    ↓
Article Featured Media Binding
    ↓
MediaUploadResult.media_idがfeatured_media_idへ設定された新しいArticleData
```

## 2. Background

- `docs/ROADMAP.md:756-761`は、v6.12.0完了直後の次候補として「Article → featured_media Wiring」を記載している。
- `docs/design/generated_image_wordpress_media_upload_wiring_foundation.md`27.1節（908-929行目）は、v6.12.0が返す`MediaUploadResult.media_id`に依存する将来Release候補として「Release 6.13候補（仮）：Article → featured_media Wiring」を明記し、変更対象候補として`image_resolver.py` / `ArticleData` / `WordPressOutput`を挙げていた。
- 2026-07-18実施のRelease 6.13候補調査（本Architecture Designの直前工程）により、上記27.1節の想定とは異なり、**`ArticleData`・`WordPressOutput`のいずれも変更不要**であることが判明した。理由：
  - `ArticleData.featured_media_id: int`は既にv1.6.0（`docs/CHANGELOG.md`参照、`src/outputs/base.py:24`のコメント「v1.6.0 追加」）から存在するfieldである
  - `WordPressOutput.save()`（`src/outputs/wordpress_output.py:66-67`）は既に`if article.featured_media_id > 0: payload["featured_media"] = article.featured_media_id`という形でfeatured_media反映を完了済みである
  - 未解決なのは、「`MediaUploadResult.media_id`という値を、どうやってこの既存の`featured_media_id`fieldへ届けるか」という一点のみである
- 本Releaseは、この「届け方」だけを、既存Contractを一切変更せずに確立する専用Foundationである。

## 3. Current State

候補調査（`Release 6.13候補調査`、2026-07-18実施）で確認済みの事実を、本Architecture Design着手前に以下のファイルを再読して再確認した。

### 3.1 ArticleData（`src/outputs/base.py:12-25`）

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

- `@dataclass`（`frozen`指定なし）。mutableだが、既存コードでは一貫してフルキーワード構築で扱われている（`main.py:339-351`）。
- `featured_media_id: int = 0`は既存field。`0`は「アイキャッチなし」を表す。
- `src/outputs/__init__.py:1`により`from outputs import ArticleData`で公開されている。

### 3.2 WordPressOutput（`src/outputs/wordpress_output.py`）

```python
def save(self, article: ArticleData) -> SaveResult:
    ...
    if article.featured_media_id > 0:
        payload["featured_media"] = article.featured_media_id
```

（`wordpress_output.py:66-67`）featured_media反映は完了済み。本Releaseで変更しない。

### 3.3 MediaUploadResult（`src/wordpress_media/media_upload_result.py:7-21`）

```python
@dataclass(frozen=True)
class MediaUploadResult:
    media_id: int
    source_url: str | None
    mime_type: str | None
```

- `frozen=True`（immutable）。ただし`__post_init__`によるself-validationは**存在しない**（`GeneratedImage`との違い。15章で扱う）。
- `src/wordpress_media/__init__.py:8`により`from wordpress_media import MediaUploadResult`で公開されている。
- `media_id`が`featured_media`へ使用すべき値であることは、`WordPressOutput`の既存パターン（int値をそのまま`payload["featured_media"]`へ代入）と、フィールドdocstring（「WordPress Media Library上のID（1以上）」）の両方から確認済み。`source_url`は文字列でありfeatured_mediaには使用できない。

### 3.4 image_resolver（`src/image_resolver.py:28-49`）

```python
def resolve_media_id(item: NewsItem, default_media_id: int) -> int:
    if item.image_terms_confirmed:
        # 将来（v1.7.0）: アップロード済み画像のmedia_idをここで返す
        pass
    return default_media_id
```

現状は`default_media_id`を返すのみのstub。本Releaseでは変更しない（10章）。

### 3.5 Runtime接続状況

`GeneratedImageWordPressMediaUploader` / `WordPressMediaUploader` / `MediaUploadResult` / `OpenAIImageGenerator` / `GeneratedImage`は、`tests/`・`docs/`以外の箇所（`main.py` / `src/pipeline/` / `src/ai/` / `src/outputs/`等）から一切参照されていないことをgrepで再確認した（Release 6.13候補調査で確認済みの事実を再現）。`ArticleData`と`GeneratedImage`が同一実行フロー内に存在する箇所は現状ゼロである。

## 4. Problem Statement

`MediaUploadResult`（Media Upload成功結果）を保持している呼び出し元が、これを`ArticleData.featured_media_id`へ反映する手段が、現状Public APIとして存在しない。これを行う唯一の方法は、呼び出し元が`article.featured_media_id = media_result.media_id`という直接mutationを自力で書くことだが、これは次の既存慣行に反する。

- `src/scheduler/scheduler_manager.py:10-12`：「`enable_job` / `disable_job`は既存Jobを`dataclasses.replace()`で複製し、`enabled`フィールドのみを変更したうえで`Repository.update()`に渡す（`SchedulerJob`を直接書き換えない。既存Jobオブジェクトの不変性を保つ設計）」
- `src/retry_queue/retry_queue_manager.py:19-20`、`src/retry_history/retry_history_manager.py:15-17`：「呼び出し元へ返す〇〇は常にコピー（`dataclasses.replace()`）であり、呼び出し元が書き換えても内部ストアには影響しない」

`ArticleData`は`frozen`ではないが、このプロジェクトには「mutableなdataclassであっても、更新は`dataclasses.replace()`による複製で行い、直接mutationしない」という一貫した既存Architecture慣行がある（`SchedulerJob`が代表例）。本Releaseはこの慣行を`ArticleData`へも適用する専用Foundationを提供する。

## 5. Release Goal

```text
ArticleData
MediaUploadResult
    ↓
Article Featured Media Binding
    ↓
MediaUploadResult.media_idがfeatured_media_idへ設定された新しいArticleData
```

必須要件（すべて満たす）：

```text
元のArticleDataを変更しない
新しいArticleDataを返す
media_result.media_idだけをfeatured_media_idへ反映する
ArticleDataのその他すべてのfieldを維持する
MediaUploadResult自体をArticleDataへ保持しない
source_urlをArticleDataへ新規反映しない
WordPressOutputを変更しない
ArticleData定義を変更しない
HTTP通信を行わない
Production Runtimeへ接続しない
```

## 6. In Scope

```text
MediaUploadResult.media_idを、既存ArticleData.featured_media_idへ反映する
    新しいArticleDataを返す、単一のPublic関数の追加
上記関数を公開する新規独立package（1package・1module・1 Public関数）の追加
上記関数のValidation Contract・Error Contract・State Contractの確立
```

## 7. Out of Scope

```text
OpenAIImageGenerator.generate()の呼び出し
GeneratedImageWordPressMediaUploader.upload()の呼び出し
WordPressMediaUploader.upload()の呼び出し（Media Upload実行そのもの）
main.pyへの接続
image_resolver.resolve_media_id()の変更
WordPressOutputの変更
OutputManagerの変更
Pipelineの変更
Composition Rootの変更
記事生成と画像生成の同一Runtime Flow接続
default_media_id fallback変更
Retry／重複Upload対策
重複投稿対策
Upload成功後の記事投稿失敗時の整合性
既存media ID再利用の判定
未使用Media cleanup
Logging
HTTP通信全般
```

これらは33章（Future Candidates）へ後続Release候補として引き継ぐ。番号・正式名称は本文書で確定しない。

## 8. Architecture Decision

| # | 内容 |
|---|---|
| AD-1 | 責務モデル：`ArticleData`と`MediaUploadResult`を受け取り、`featured_media_id`だけを置換した新しい`ArticleData`を返す、純粋なデータ変換のみ。Media Upload実行・画像生成・HTTP通信のいずれも行わない |
| AD-2 | Package配置：新規独立package`src/article_featured_media/`（Consumer-less Foundationとして導入、9章） |
| AD-3 | Public API形状：**module-level function**を採用する。Public classは採用しない（詳細は10.1節） |
| AD-4 | Constructor：不要（AD-3の帰結。module-level functionのためConstructor自体が存在しない） |
| AD-5 | 依存Contract：`outputs.ArticleData`と`wordpress_media.MediaUploadResult`のみに依存する。`wordpress_media.WordPressMediaUploader`（Uploader本体）・`generated_image_wordpress_media`・`ai_image_generation`・`openai_image_generation`のいずれにも依存しない（19章） |
| AD-6 | 複製方式：`dataclasses.replace()`を採用する（12章） |
| AD-7 | featured_media_id反映方式：`media_result.media_id`で決定的に上書きする。既存値（0／同一／異なる値）による分岐は行わない（14章） |
| AD-8 | Validation方式：article／media_resultの型検証（`isinstance`）に加え、`media_result.media_id`の値検証（bool除外・int・1以上）も行う（Option B採用、15章） |
| AD-9 | Error Contract：新規例外型を追加しない。すべて`ValueError`（固定message）とする（17章） |
| AD-10 | State Contract：module-level functionであるため、インスタンス状態は構造的に存在しない（18章） |
| AD-11 | Logging：追加しない |
| AD-12 | Retry：追加しない。Retry Runtimeへの接続もしない |
| AD-13 | Article本文への画像挿入・アイキャッチ画像設定・記事生成Pipelineへの統合：Out of Scope（7章） |
| AD-14 | `source_url` / `mime_type`：`ArticleData`へは一切反映しない。`media_result.media_id`のみを使用する |

## 9. Package Structure

```text
projects/03_game_content_ai/src/article_featured_media/
├── __init__.py
└── article_featured_media_binder.py   # bind_featured_media()
```

### 9.1 package名の検討

| 候補 | 却下／採用理由 |
|---|---|
| `media_upload_result_article_featured_media` | 依存2型の名前をそのまま連結すると長すぎ、既存package名（`generated_image_wordpress_media`等）と比べても可読性が下がる |
| `article_media_binding` | 「featured_media」というWordPress REST APIの実際のfield名（`wordpress_output.py:67`）との対応関係が名前から読み取れなくなる |
| `featured_media_binding` | 「Article」という起点が名前から読み取れず、`ArticleData`を変換する層であることが不明瞭になる |
| **`article_featured_media`（採用）** | `ArticleData`（Article）と`featured_media_id`（WordPressの`featured_media`）という2つの既存概念をそのまま連結しており、責務が名前から一意に読み取れる。候補調査プロンプトが提示した基準案の package候補と一致する |

### 9.2 module名の検討

`article_featured_media_binder.py`を採用する。既存precedentとして、`src/image_resolver.py`は`ImageResolver`というclassが存在しないにもかかわらず、module名を「解決する主体」を表す名詞（`resolver`）としている。本moduleも同様に、`Binder`というclassを持たない（10.1節）が、module名は「束縛を行う主体」を表す名詞（`binder`）とし、既存命名習慣と一貫させる。

## 10. Public API

```python
# src/article_featured_media/article_featured_media_binder.py
from dataclasses import replace

from outputs import ArticleData
from wordpress_media import MediaUploadResult


def bind_featured_media(article: ArticleData, media_result: MediaUploadResult) -> ArticleData:
    ...
```

```python
# src/article_featured_media/__init__.py
from .article_featured_media_binder import bind_featured_media

__all__ = [
    "bind_featured_media",
]
```

- Public import path：`from article_featured_media import bind_featured_media`
- 引数名：`article`（`ArticleData`）、`media_result`（`MediaUploadResult`）
- 戻り値型：`ArticleData`（新しいobject）
- Constructor：なし

### 10.1 stateless instance method／staticmethod／module-level functionの比較

| 観点 | stateless instance method | staticmethod | module-level function（採用） |
|---|---|---|---|
| 依存の有無 | なし（`bind()`はConstructorへ注入する協調objectを持たない） | なし | なし |
| 既存precedent | `GeneratedImageWordPressMediaUploader`はConstructorで`media_uploader`を注入するため、instance methodが必然（依存を保持する必要があるため） | プロジェクト内に`@staticmethod`を採用したPublic APIのprecedentが見当たらない | `image_resolver.resolve_media_id(item, default_media_id) -> int`、`taxonomy_config.resolve_taxonomy(importance) -> tuple[...]`はいずれも依存を持たない変換処理をmodule-level functionとして実装している |
| 呼び出し時の余計な手順 | 呼び出し前に空のConstructor呼び出し（`ArticleFeaturedMediaBinder()`）が必要になり、何のためのobjectか呼び出し元コードから読み取りにくい | クラス自体の存在意義が薄く、`ClassName.method()`という間接参照が増えるだけ | `bind_featured_media(article, media_result)`と直接呼び出せ、依存注入の余地がないことが型シグネチャからも自明 |
| 7.1節の指示との整合 | 「Constructorが不要なら、request単位stateやdependencyを保持するためだけのConstructorを追加しないでください」という制約に抵触するリスクがある（空Constructorを持つclassになるため） | 同上（class自体が不要な間接層になる） | 制約に抵触しない。Constructorという概念自体が存在しないため、将来誤って state を持たせるリスクも構造的に排除できる |

**結論**：`resolve_media_id()` / `resolve_taxonomy()`という直接の既存precedentに倣い、依存注入の必要がない本機能はmodule-level functionとして実装する。候補調査プロンプト・本Architecture Designプロンプトが提示した基準案（`ArticleFeaturedMediaBinder`クラス＋`bind()`メソッド）からの変更点だが、次の理由により基準案からの「大きな逸脱」には当たらないと判断する。

```text
package名・Public Contract（入力2つ・戻り値1つ・Validation・Error・State Contract）は
    基準案から一切変更していない
変更しているのはPythonの呼び出し規約（class経由かfunction直接か）のみであり、
    Dependency Direction・Runtime Flow・Security Contractへの影響はない
基準案自体が「より適切なclass名、method名がある場合は変更してよい」と明記しており、
    かつ7.1節で三択の比較検討を明示的に指示している
既存2つの直接precedent（image_resolver.py／taxonomy_config.py）と一致させることで、
    プロジェクト全体の一貫性がむしろ高まる
```

Architecture Reviewで「基準案どおりclass形式を維持すべき」という判断がなされた場合は、`bind_featured_media()`を`ArticleFeaturedMediaBinder.bind()`（`__init__`なしの単純classまたは`@staticmethod`）へ機械的に置換するのみで、Contract自体への影響はない。

## 11. Runtime／Data Flow

```text
Caller（本Releaseでは未実装＝Consumer-less。将来のPipeline／Composition Root、33章）
  → bind_featured_media(article, media_result)
      1. isinstance(article, ArticleData) を検証。不適合なら ValueError（15章）
      2. isinstance(media_result, MediaUploadResult) を検証。不適合なら ValueError（15章）
      3. media_result.media_id の値を検証（bool除外・int・1以上）。不適合なら ValueError（15章）
      4. dataclasses.replace(article, featured_media_id=media_result.media_id) で
         新しいArticleDataを構築する
      5. 新しいArticleDataを返す
```

本Release自体はCallerを持たない（Consumer-less Foundation、Foundation First原則の継続）。`ArticleData`と`MediaUploadResult`を同一スコープで扱うCallerは、本Release完了時点でも依然として存在しない（33章）。

## 12. ArticleData Copy Contract

### 12.1 比較

| 方式 | 元object非破壊 | 全field維持 | 将来field追加への耐性 | 不要なobject複製 | 採用 |
|---|---|---|---|---|---|
| `dataclasses.replace()` | ○（新objectを返す） | ○（明示したfield以外は元の値をそのまま引き継ぐ） | ○（新fieldが増えても呼び出し側コードの変更不要） | なし（top-levelのみ複製、nested objectは参照共有） | **採用** |
| 全field明示したArticleData再構築 | ○ | △（`ArticleData`にfieldが増えるたびに本層のコードを追随させる必要がある） | ×（保守漏れリスク） | なし | 不採用 |
| `copy.copy()` | ○（shallow copy） | ○ | ○ | なし | 不採用（`featured_media_id`をcopy後に別途mutationする必要があり、「複製後に1回だけ許されるmutation」という例外を作ってしまう。`dataclasses.replace()`なら1呼び出しで完結する） |
| `copy.deepcopy()` | ○ | ○ | ○ | ×（`item: NewsItem`等のnested objectまで再帰的に複製し、不要なメモリ・CPUコストが発生する） | 不採用 |

### 12.2 採用理由（`dataclasses.replace()`）

```text
元objectを変更しない
全既存fieldを維持できる
将来ArticleData fieldが増えた場合にも、本層のコードを変更せずに追随できる
deep copyによる不要なobject複製を避けられる
featured_media_idだけを明示的に置換できる
既存precedent（scheduler_manager.py:10-12、retry_queue_manager.py:19-20、
    retry_history_manager.py:15-17）と一貫する
```

### 12.3 nested objectの扱い

`item: NewsItem`等のnested objectは、`dataclasses.replace()`の性質上、複製されず元のobject参照がそのまま新しい`ArticleData`へ引き継がれる（shallow）。本層はこれを意図的なContractとする。`NewsItem`自体は本層が変更対象とする値ではなく、deep copyする理由がないため。

### 12.4 禁止事項

```text
article.featured_media_id = ...（直接mutation）
setattr(article, ...)
article.__dict__の変更
元ArticleDataのmutation
根拠のないdeepcopyの使用
```

Production Codeは`dataclasses.replace()`の1回の呼び出しのみで新しい`ArticleData`を構築し、それ以外の代入・属性操作を行わない。

## 13. featured_media_id Binding Contract

```text
戻り値はArticleData
戻り値は元ArticleDataとは別object（同一値になる場合でも同一参照を返さない。
    dataclasses.replace()は呼び出しのたびに新しいobjectを生成するため、
    この性質はProduction Code側で追加の分岐を持たなくても自然に満たされる）
元ArticleDataは変更されない
featured_media_idだけがmedia_result.media_idへ置換される
その他fieldは既存値（object参照含む）を維持する
item等のnested objectはdeep copyしない（12.3節）
同じmedia_idが既にfeatured_media_idへ設定されている場合も、新しいArticleData
    objectを返す（値が変化しない場合の早期return・同一object返却という最適化は行わない。
    Public Contractを単純に保つため）
```

## 14. Existing featured_media_id Handling

入力`ArticleData.featured_media_id`が次のいずれであっても、挙動は同一とする。

```text
featured_media_id == 0
featured_media_id == media_result.media_id
featured_media_id > 0 かつ media_result.media_idと異なる
```

**採用方式：明示的な`bind`操作として、常に`media_result.media_id`で決定的に上書きする。**

### 14.1 比較

| 方式 | 内容 | 採用 |
|---|---|---|
| 常に新しいmedia_idで上書き | 既存値に関わらず`media_result.media_id`を設定する | **採用** |
| 同一の場合は許可し、異なる場合は拒否する | `featured_media_id > 0`かつ`media_result.media_id`と異なる場合に例外を送出する | 不採用 |
| 既存IDがある場合は常に拒否する | `featured_media_id > 0`なら常に例外を送出する | 不採用 |
| 既存IDを優先し変更しない | `featured_media_id > 0`なら`media_result`を無視する | 不採用 |

### 14.2 採用理由

```text
bind_featured_media()は呼び出し元が明示的に呼ぶ操作である。呼び出す時点で
    「このMediaUploadResultをこのArticleDataへ反映したい」という意図は
    既に呼び出し元側で確定している
既存値と新しい値の比較・拒否ロジックを本層に持たせると、「いつ拒否される
    べきか」という業務判断（例：Retry時の重複Upload防止方針）を本層が
    肩代わりすることになり、11章（Retry／Idempotency Boundary）で明確化する
    「本層はRetry判断を持たない」という責務境界と矛盾する
既存値のガードが必要な場合は、bind_featured_media()を呼ぶかどうかを
    呼び出し元（将来のCaller／Composition Root）が判断すればよく、
    本層のPublic Contractをそのために複雑化する必要はない
決定的な上書きにすることで、本層自体の振る舞いが単純かつ予測可能になり、
    E2Eでのテストケースが「既存値の3パターン × 常に同じ結果」という
    単純な構造になる
```

この判断はRetry時の重複Upload対策とは無関係である。本Releaseは`MediaUploadResult`を受け取るだけで、Upload自体を実行しない（24章）。

## 15. Validation Contract

### 15.1 article検証

```python
if not isinstance(article, ArticleData):
    raise ValueError("article must be an ArticleData")
```

### 15.2 media_result検証

```python
if not isinstance(media_result, MediaUploadResult):
    raise ValueError("media_result must be a MediaUploadResult")
```

**ValueError採用根拠（Architecture Review Finding AR-S-2反映）**：15.1節・15.2節の`isinstance`不正判定は、一般的なPython慣習では`TypeError`が採用されることもあるが、本層は既存Foundation precedentに合わせて`ValueError`を採用する。既存precedentとして、`src/generated_image_wordpress_media/generated_image_wordpress_media_uploader.py:28-29`（`GeneratedImageWordPressMediaUploader.upload()`）を実コードで再確認した。

```python
if not isinstance(image, GeneratedImage):
    raise ValueError("image must be a GeneratedImage")
```

これはPublic Boundaryにおける`isinstance`型不正を`ValueError`（`TypeError`ではない）として扱う直接のprecedentである。同様に`src/wordpress_media/wordpress_media_uploader.py`の`WordPressMediaUploader.__init__`・`_validate_image_bytes`・`_validate_filename`・`_validate_mime_type`（いずれも入力引数の`isinstance`不正を`ValueError`とする）とも整合する。本層の`article`・`media_result`検証（15.1節・15.2節）は、いずれも「呼び出し元がPublic関数へ渡した引数」を検証するPublic Boundary入力検証であり、上記precedent群と同一種のBoundaryに位置づけられるため、`TypeError`ではなく`ValueError`を採用する。

（`wordpress_media_uploader.py:181`の`media_id`検証が`ValueError`ではなく`WordPressMediaUploadError`（`RuntimeError`のsubclass）を送出する点については15.4節で扱う。あれは「呼び出し元が渡した引数」ではなく「外部WordPress REST APIレスポンスの解析結果」を検証するものであり、Boundaryの種類が異なるため、本層はそちらの例外型は参照しない。）

### 15.3 media_result.media_id検証

**Option Bを採用する**：`MediaUploadResult`であることの型検証に加え、`media_id`がbool除外のintかつ1以上であることも再検証する。

```python
if isinstance(media_result.media_id, bool) or not isinstance(media_result.media_id, int) or media_result.media_id < 1:
    raise ValueError("media_result.media_id must be a positive int")
```

### 15.4 Option A／Bの比較と採用理由

| 案 | 内容 | 採否 |
|---|---|---|
| A | `MediaUploadResult`であることだけを検証し、`media_id`の有効性は`MediaUploadResult`のContractを信頼する | 不採用 |
| B | `MediaUploadResult`であることに加え、`media_id`がboolではないintかつ1以上であることを再検証する | **採用** |

`GeneratedImageWordPressMediaUploader`（v6.12.0）が`image`の型のみを検証し、`image_bytes` / `mime_type`の内容検証を`GeneratedImage.__post_init__`へ完全委譲している（AD-7、`generated_image_wordpress_media_upload_wiring_foundation.md`236行目）のは、`GeneratedImage`が`@dataclass(frozen=True)`かつ`__post_init__`でself-validationを行うためであり、構築後の値の妥当性が型そのもので保証されている。

一方`MediaUploadResult`は`@dataclass(frozen=True)`だが`__post_init__`を持たず、**Public APIから直接、無効な値（`media_id=0` / `media_id=-1` / `media_id=True`等）で構築可能**である（`src/wordpress_media/media_upload_result.py`確認済み、候補調査Finding参照）。したがって`GeneratedImage`と同じ「型さえ合っていれば内容を信頼してよい」という論拠は`MediaUploadResult`には適用できない。本層のPublic Boundaryとして、`WordPressMediaUploader.upload()`内部のレスポンス検証（`wordpress_media_uploader.py:181`：`isinstance(media_id, bool) or not isinstance(media_id, int) or media_id < 1`）と同一の検証式を、同じ理由（bool は int のsubtypeであるためisinstance(x, int)だけではTrue/Falseを通過させてしまう）で採用する。

### 15.5 固定message一覧

```text
article must be an ArticleData
media_result must be a MediaUploadResult
media_result.media_id must be a positive int
```

## 16. Validation Order

```text
1. articleの型検証（15.1節）
2. media_resultの型検証（15.2節）
3. media_result.media_idの値検証（15.3節）
4. dataclasses.replace()による新しいArticleDataの生成
5. 戻り値の返却
```

複数の入力が同時に不正な場合、最初に検証を満たさなかった項目の例外のみが送出される（fail-fast、逐次検証）。例：`article`と`media_result`の両方が不正な型の場合、`article`の検証が先に行われるため`"article must be an ArticleData"`のみが送出され、`media_result`の検証には到達しない。これは`WordPressMediaUploader.upload()`（`_validate_image_bytes` → `_validate_filename` → `_validate_mime_type`の順次呼び出し）および`GeneratedImageWordPressMediaUploader.upload()`（image型検証 → capability検証の順）と同一の既存パターンである。

新規E2Eは、この順序をPublic Contractとして固定できるよう、「両方不正な入力」を与えた際に最初の項目の例外のみが送出されることを検証するScenarioを含める（25章）。

## 17. Error Contract

```text
article型不正の例外型：ValueError（固定message："article must be an ArticleData"）
media_result型不正の例外型：ValueError（固定message："media_result must be a MediaUploadResult"）
media_id値不正の例外型：ValueError（固定message："media_result.media_id must be a positive int"）
固定messageをPublic Contractとする：する（3種すべて完全一致でPublic Contract化する）
dataclasses.replace()由来の例外：ラップ・変換せず無変換伝播する。本層の入力検証
    （15章）を通過した時点でarticleは有効なArticleData・field名は既存field
    （featured_media_id）であるため、dataclasses.replace()自体が例外を送出する
    ことは通常起こり得ないが、Python runtimeが将来何らかの理由で例外を
    送出した場合でも、本層はそれをcatchしない・変換しない・ラップしない
```

原則（本層が遵守する既存precedent）：

```text
try／exceptを不要に追加しない
例外wrapperを作らない
raise ... from ... を使用しない
予期しないPython runtime例外を変換しない
credentialや入力objectのrepr／str表現をmessageへ含めない
    （article／media_resultのいずれもcredentialを保持しないが、念のため
     固定messageには型名の説明のみを含め、入力値そのものを埋め込まない）
```

`KeyboardInterrupt` / `SystemExit`は`BaseException`のsubtypeであり、本層は`Exception`のみを対象とした`except`を一切持たないため、これらを握りつぶすことはない（本層は`try`/`except`自体を持たない）。

## 18. State Contract

本層は**module-level function**として実装するため（10.1節）、インスタンス状態という概念自体が構造的に存在しない。Constructorも存在しないため、「Constructorが保持する状態」という懸念も発生しない。

### 18.1 禁止するstate（class形式へ変更された場合も含め、一般原則として明記）

```text
article
media_result
media_id
featured_media_id
戻り値ArticleData
例外object
request単位の一時値
```

### 18.2 Production Codeでの保証方法

```text
bind_featured_media()はmodule-level変数への書き込みを一切行わない
    （module-levelのmutable stateへの代入なし）
bind_featured_media()の関数本体は、global文・nonlocal文のいずれも使用しない
    （関数本体からmodule-levelスコープ・enclosingスコープへ書き込む経路を
     一切持たない、Architecture Review Finding AR-m-2反映）
関数内で生成した中間値（検証結果・新しいArticleData）はいずれも
    ローカル変数として扱われ、関数終了とともに破棄される
```

### 18.3 E2Eでの保証方法

```text
Runtime Guard：同一(article, media_result)の組を複数回bind_featured_media()へ
    渡し、1回目の呼び出しが2回目の呼び出し結果へ一切影響しないことを確認する
    （25章）
AST Guard（module-level state）：article_featured_media_binder.py全体のASTを
    走査し、module-levelのAssign（関数定義・importを除く）が存在しないことを
    確認する（25章）
AST Guard（global／nonlocal、Architecture Review Finding AR-m-2反映）：
    bind_featured_media()の関数本体（ast.FunctionDefのbody）を走査し、
    ast.Global／ast.Nonlocalノードが1件も存在しないことを直接検証する。
    18.2節が主張する「global文・nonlocal文を使用しない」という保証は、
    module-levelのAssign検査（top-level文のみを対象とする）だけでは
    裏付けられない（関数本体内のglobal／nonlocal文はtop-level文ではないため）。
    このため、module-level Assign検査とは別に、関数本体を対象とした
    ast.Global／ast.Nonlocal検出を独立したGuardとして追加する（25.3節）
```

## 19. Dependency Direction

```text
許可：
article_featured_media → outputs（ArticleDataのみ）
article_featured_media → wordpress_media（MediaUploadResultのみ）
article_featured_media → standard library（dataclasses）

禁止：
article_featured_media → wordpress_media.WordPressMediaUploader（Uploader本体は使わない）
article_featured_media → generated_image_wordpress_media
article_featured_media → ai_image_generation
article_featured_media → openai_image_generation
article_featured_media → image_resolver
article_featured_media → ai（Agent層）
article_featured_media → pipeline
article_featured_media → workflow_engine
article_featured_media → scheduler
article_featured_media → retry_*（Retry Runtime全体）
article_featured_media → scripts
article_featured_media → main
article_featured_media → requests／urllib（HTTP通信は行わない）

逆依存禁止：
outputs → article_featured_media
wordpress_media → article_featured_media
```

```text
Dependency Diagram（Release 6.13後）

outputs                          wordpress_media
  └── ArticleData                  └── MediaUploadResult
              │                              │
              └──────────────┬───────────────┘
                              ▼
                  article_featured_media
                  └── bind_featured_media()
```

`outputs`と`wordpress_media`は、本Release後も相互に依存しない（現状どおり独立したleaf/サブグラフのまま）。新規package`article_featured_media`のみが両方をimportするCaller／Adapter側になる、という構造は候補調査で確認した既存Dependency Graph（`wordpress_media`・`ai_image_generation`は`outputs`から独立したサブグラフ）とも整合する。

### 19.1 循環importの有無

`outputs`・`wordpress_media`のいずれも`article_featured_media`をimportしないため、循環は発生しない。`article_featured_media`は両者から見て純粋な下流（Caller）にのみ位置する。

### 19.2 WordPress固有型のArticleData流入有無

流入しない。`ArticleData`定義（`src/outputs/base.py`）自体は本Releaseで一切変更しない（AD-2要件）。`MediaUploadResult`型そのものを`ArticleData`のfieldとして保持することもない（AD-14）。`bind_featured_media()`が返す新しい`ArticleData`が保持するのは、`MediaUploadResult.media_id`という`int`値のみである。

## 20. Reverse Dependency Guard

```text
確認事項：
outputs（base.py／wordpress_output.py）がarticle_featured_mediaをimportしていないこと
wordpress_media（media_upload_result.py／wordpress_media_uploader.py）が
    article_featured_mediaをimportしていないこと
```

確認方法（Architecture Review Finding AR-S-1反映、vacuous pass防止手順を明示）：新規E2Eにおいて、次の順序で検証する。

```text
1. 対象directory（src/outputs/, src/wordpress_media/）がそれぞれ存在することを確認する
2. 各directory配下の.pyファイル一覧を取得する
3. 各directoryについて、取得した.pyファイル一覧が1件以上であることを
   Assertionする（v6.12.0 Code Review継続Suggestion CR-S-1：「対象package
   directoryが将来空になった場合のvacuous pass耐性」と同種の弱点を、本Release
   では未然に防止する）
4. 手順3を通過した全.pyファイルをAST走査する
5. article_featured_mediaへの絶対import（import article_featured_media／
   from article_featured_media import ...）が存在しないことをAssertionする
```

本プロジェクトでは`outputs`・`wordpress_media`・`article_featured_media`はいずれも`src`直下のtop-level packageであり、`outputs`または`wordpress_media`配下のファイルから相対importによって`article_featured_media`へ到達する有効なpackage経路は存在しない（相対importは自パッケージ内の兄弟モジュールにしか到達できず、`src`直下の別のtop-level packageへは構造上到達できない）。そのため、本Guardでは実在する逆依存経路である絶対importを検査対象とする（相対importを別途検査しない理由：検査対象そのものが構造的に存在しないため。将来Repository構造が変わり相対importでの到達が可能になった場合は、本Guardの再設計が必要になる）。

手順3を欠いた場合、対象directoryが空（`.py`ファイル0件）であってもfor loopが0回実行されて「違反なし」と判定されてしまい、検証が実質的に何も確認しないまま通過する（vacuous pass）。本Releaseはこれを構造的に防止する。本Releaseは`outputs`・`wordpress_media`のいずれのファイルも変更しないため（Zero Diff、7章）、この検証は「変更していないことの確認」という性質を持つ。

## 21. Security

```text
credential読込：しない（環境変数・WordPress認証情報のいずれにもアクセスしない）
image bytes・その他機微情報：保持しない（article／media_resultのいずれの
    fieldも、そのまま参照するだけで、ログ・例外messageへ内容を埋め込まない）
例外messageへの入力値埋め込み：しない（17章の固定messageは型名の説明のみで、
    article／media_resultの値・repr・str表現を含まない）
```

## 22. Side Effects

以下をすべて禁止する（本層のProduction Codeはこれらのいずれも呼び出さない）。

```text
HTTP処理
WordPress REST API呼び出し
Media Upload
画像生成
Client生成
credential読込
Environment Variable読込
ファイルI/O
Logging
Retry
Scheduler
sleep
subprocess
永続化
WordPress Media削除
Article投稿
SNS投稿
Analytics処理
```

`bind_featured_media()`は、入力objectから新しい`ArticleData`を作って返すだけの純粋な関数である。

## 23. Logging Policy

追加しない。v6.9.0〜v6.12.0の一貫した方針（AD-13相当）を継承する。

## 24. Retry／Idempotency Boundary

本Release自体はMedia Uploadを実行しないため、次を直接解決しない（Out of Scope、7章）。

```text
重複Upload
重複投稿
Upload成功後の投稿失敗
WordPress側の未使用Media残存
Upload rollback
Retry checkpoint
idempotency（Runtime Wiring全体としての）
```

### 24.1 `bind_featured_media()`自体の決定性

```text
同じ(article, media_result)の組を複数回bind_featured_media()へ渡した場合、
    返される新しいArticleDataは常に値として同値になる
    （==比較で一致。featured_media_idはmedia_result.media_idで固定的に
     決まり、その他fieldは入力articleの値をそのまま引き継ぐため）
ただし、dataclasses.replace()は呼び出しのたびに新しいobjectを生成するため、
    object identity（is比較）は一致しない。本層はobject identityの一致を
    Public Contractとしない（13章と同一の考え方）
本層は外部状態（ファイル・環境変数・グローバル変数）を一切参照しないため、
    呼び出し回数・呼び出し順序に関わらず、同一入力に対する出力は常に同値である
```

将来のRuntime Wiring（Media Uploadの実行そのもの）における重複防止・整合性の課題は、本層の決定性とは別の論点であり、本層のBinding Contract自体はこれらの課題を解決しない。33章（Future Candidates）で後続Release候補として明示する。

## 25. E2E Test Strategy

想定新規E2Eファイル：`tests/test_e2e_v6_13_0_article_featured_media_binding_foundation.py`

**実行方式**：既存precedent（v6.9.0〜v6.12.0）と同様、`pytest`は使用せず、Pythonスクリプトとして直接実行し、`check()`系helperで結果を集計する方式を採用する。実行コマンドは`python projects/03_game_content_ai/tests/test_e2e_v6_13_0_article_featured_media_binding_foundation.py`とする。

### 25.1 独立Scenario候補

```text
Public import：`from article_featured_media import bind_featured_media`が
    成功すること
Public関数の存在とsignature：引数名（article, media_result）・戻り値型が
    Contractどおりであること

正常系：
    ArticleData（featured_media_id=0）とMediaUploadResult（media_id=123）を
        与え、戻り値のfeatured_media_idが123であること
    戻り値がArticleDataであること
    戻り値が入力articleとは別object（is比較でFalse）であること
    入力article自体（featured_media_id含む全field）が変更されていないこと
        （呼び出し前後でarticleの各fieldを比較）
    featured_media_id以外の全field（item, importance, seo_title, article_body,
        x_post, featured_image_url, excerpt, meta_description, slug,
        publish_status）が戻り値へそのまま引き継がれていること
    item（NewsItem）が戻り値でも入力articleと同一object参照であること
        （is比較でTrue、12.3節のshallow copy Contractの確認）

既存featured_media_idパターン（14章、常に上書き）：
    featured_media_id == 0 から bind した場合 → media_result.media_idに置換される
    featured_media_id == media_result.media_id から bind した場合 →
        同じ値のまま（かつ新しいobjectであることをis比較で確認）
    featured_media_id > 0 かつ media_result.media_idと異なる場合から bind
        した場合 → media_result.media_idへ上書きされる（拒否されない）

Validation：
    articleがArticleDataでない場合 → ValueError（固定message完全一致）
    media_resultがMediaUploadResultでない場合 → ValueError（固定message完全一致）
    media_result.media_idがboolの場合（True/False） → ValueError（固定message完全一致）
    media_result.media_idがintでない場合（str／float／None等） → ValueError（固定message完全一致）
    media_result.media_idが0の場合 → ValueError（固定message完全一致）
    media_result.media_idが負数の場合 → ValueError（固定message完全一致）

Validation Order：
    articleとmedia_resultの両方が不正な型の場合、articleの検証由来の
        ValueError（"article must be an ArticleData"）のみが送出されること
    articleが正当でmedia_resultが不正な型の場合、media_result型検証由来の
        ValueErrorが送出されること
    articleとmedia_resultがいずれも正当な型だがmedia_result.media_idが
        不正な場合、media_id値検証由来のValueErrorが送出されること

例外Security：
    3種の例外いずれも、message中にarticle／media_resultの値・repr・str表現
        （例：NewsItemの内容、seo_titleの文字列そのもの等）を含まないこと

State非保持（18章）：
    同一(article, media_result)を複数回渡しても、1回目の呼び出しが2回目の
        呼び出し結果に影響しないこと（連続呼び出しの独立性）
    不正な入力で1回失敗させた直後に正当な入力で呼び出しても、1回目の失敗が
        2回目の結果へ影響しないこと

Side Effect非存在：
    HTTP呼び出しが一切発生しないこと（requests等をpatchし、呼び出し0回を確認、
        またはAST Guardでrequests/urllib importが存在しないことを確認）
    Environment Variable読込が発生しないこと（os.environ／os.getenvを
        AST Guardで検出）
    ファイルI/Oが発生しないこと（open()呼び出しをAST Guardで検出）
    Logging呼び出しが発生しないこと（logging importをAST Guardで検出）
    print()呼び出しが発生しないこと（AST Guardで検出）
    subprocess／sleep呼び出しが発生しないこと（AST Guardで検出）

Dependency Direction：
    article_featured_media_binder.pyのimportがoutputs（ArticleDataのみ）・
        wordpress_media（MediaUploadResultのみ）・標準ライブラリに限られること
        （AST Guard）
    禁止import（generated_image_wordpress_media, ai_image_generation,
        openai_image_generation, image_resolver, ai, pipeline, workflow_engine,
        scheduler, retry_*, scripts, main, requests, urllib）が存在しないこと

Reverse Dependency（Architecture Review Finding AR-S-1反映）：
    src/outputs/・src/wordpress_media/それぞれについて、走査対象の.pyファイル
        一覧が1件以上であることを先にAssertionしたうえで（vacuous pass防止）、
        article_featured_mediaをimportしていないことをAST Guardで確認する
        （20章）

Runtime非接続の確認（Zero Diff Policyの裏付け、26章）：
    main.py・src/image_resolver.py・src/outputs/wordpress_output.pyの
        いずれもarticle_featured_mediaをimportしていないこと
        （本Release自体が生成した新規ファイルであるため、既存ファイル側の
         これらのimportは本Releaseの実装によって発生しようがないが、
         Zero Diff Policyの成立を裏付ける確認として実施する）
```

### 25.2 採用しないScenario

```text
「同一featured_media_idからのbind」と「異なる既存featured_media_idからの
    bind」は、14章のContract（常に決定的上書き、既存値による分岐なし）の
    もとでは同一の処理経路（無条件上書き）をたどるため、個別のAssertion
    水増しは行わず、上記「既存featured_media_idパターン」の3ケース
    （0／同一／異なる）で必要十分とする
copy.deepcopyの明示的な非使用を確認するScenario：nested object（item）の
    参照が入力articleと戻り値で一致すること（is比較）を確認するScenarioに
    包含されるため、独立Scenarioとしては追加しない
```

### 25.3 AST／Source Guard方針

State非保持とSide Effect非存在は、v6.9.0〜v6.12.0の既存precedent（`ast.Import` / `ast.ImportFrom` / `ast.Call`によるDependency Guard・Side Effect Guard）に倣い、AST解析で機械的に検証する。

```text
採用するGuard：
    module-levelのAssign文が存在しないこと（18.3節、State Contract）
    bind_featured_media()の関数本体にast.Global（global文）が存在しないこと
        （18.3節、Architecture Review Finding AR-m-2反映）
    bind_featured_media()の関数本体にast.Nonlocal（nonlocal文）が存在しないこと
        （18.3節、Architecture Review Finding AR-m-2反映）
    禁止import（requests, urllib, os, logging, subprocess）が存在しないこと
    open() / print() / sleep()呼び出しが存在しないこと
    Dependency Direction（19章）で許可されたimport以外が存在しないこと

採用しないGuard：
    dataclasses.replace()の使用そのものを固定するGuard（実装がreplace()を
        使うことを唯一の手段として固定しない。12章で述べたContract
        （元object非mutation・全field維持）さえ満たせば、実装手段の変更
        （例：将来のPython versionでの別の複製手段への切り替え）を
        妨げるべきではないため）
    article入力objectへの属性Assign禁止をAST Guardで検証すること
        （article自体は本層が生成したobjectではなく、本層のソースコード内に
         article.xxx = ...という代入文が存在しないことはAST Guardで
         検証可能だが、より直接的で実装非依存な確認方法として、
         「呼び出し前後でarticleの全fieldが変化しないこと」という
         振る舞いベースのRuntime Guard（25.1節）を優先する。AST Guardは
         補助的に、本層のソース内にself／article等への属性代入・
         setattr呼び出しが存在しないことの確認として追加してもよいが、
         必須Contractとはしない）
```

## 26. Regression Test Strategy

正式Regressionの基準は、Release 6.12完了時点の`docs/CHANGELOG.md`記載の実測値を参照する。

```text
Release 6.12完了時点の正式Regression：
    対象：15ファイル
    総合：1931/1931 PASS

Release 6.13実装後に想定するもの：
    Release 6.12までの正式Regression（15ファイル、1931件）：1931/1931 PASS維持
    Release 6.13新規E2E：全PASS
    Warning：0件
    終了コード非0：0ファイル
    実行対象合計：16ファイル（既存15ファイル＋新規v6.13.0 E2E 1ファイル）
```

本Architecture Design工程ではテストを実行しない（22章に定めるとおり、正式Regression実行・新規E2E実装はいずれも実装工程の責務である）。

### 26.1 Formal Regression実績（Formal Regression工程実施、Documentation Integration工程で反映）

```text
正式対象：16ファイル（既存15ファイル＋新規v6.13.0 E2E 1ファイル）
既存15ファイル：1931/1931 PASS（Baseline維持、新規差分なし）
新規v6.13 E2E：123/123 PASS
総合：2054/2054 PASS
FAIL：0
Warning：0
終了コード非0：0
実HTTP・実credential読込・実課金：いずれもなし
```

上記は26章冒頭の想定どおりの結果であり、Release 6.12完了時点の正式Regression（15ファイル・1931/1931 PASS）はBaselineとして完全に維持された。

## 27. Acceptance Criteria

```text
[ ] bind_featured_media()がPublic importできる
[ ] article・media_resultの2引数を受け取り、ArticleDataを返す
[ ] 元のarticleが変更されない（全fieldが呼び出し前後で不変）
[ ] 戻り値が入力articleとは別objectである
[ ] featured_media_idのみがmedia_result.media_idへ置換される
[ ] featured_media_id以外の全fieldが既存値のまま引き継がれる
[ ] item（NewsItem）が同一object参照のまま引き継がれる（deep copyしない）
[ ] 既存featured_media_id（0／同一／異なる）のいずれからでも決定的に
    media_result.media_idへ上書きされる
[ ] article型不正・media_result型不正・media_id値不正（bool・非int・0以下）
    がいずれもValueError（固定message）を送出する
[ ] Validation Orderが16章のとおり確定している
[ ] 本層がHTTP通信・credential読込・Environment Variable読込・ファイルI/O・
    Logging・subprocess・sleepのいずれも行わない
[ ] 本層がoutputs（ArticleDataのみ）・wordpress_media（MediaUploadResultのみ）・
    標準ライブラリ以外へ依存しない
[ ] outputs・wordpress_mediaのいずれもarticle_featured_mediaへ逆依存しない
[ ] 循環importが発生しない
[ ] ArticleData定義（src/outputs/base.py）が無変更である
[ ] WordPressOutput（src/outputs/wordpress_output.py）が無変更である
[ ] image_resolver.py・main.pyが無変更である
[ ] 新規E2E（tests/test_e2e_v6_13_0_article_featured_media_binding_foundation.py）
    が全PASSする
[ ] 既存正式Regression（15ファイル・1931件）が維持される
```

## 28. Alternatives Considered

### Alternative A：ArticleDataを直接mutation

```python
article.featured_media_id = media_result.media_id
```

不採用。理由：

```text
入力objectへSide Effectが発生する
呼び出し元が保持するArticleDataも変更されてしまう
再利用・テスト時の予測可能性が低下する
Foundationとしての純粋性（参照透過性）が低下する
scheduler_manager.py等の既存慣行（4章）に反する
```

### Alternative B：ArticleDataへMediaUploadResultを追加

不採用。理由：

```text
outputs層へWordPress固有型（MediaUploadResult）が流入する
既存ArticleData Public Contract（field構成）の変更が必要になる
outputs → wordpress_mediaという逆依存が発生する
既存E2E（ArticleDataのfield構成を固定しているもの）への影響が発生する
候補調査（Release 6.13候補調査）で「ArticleDataへMediaUploadResult自体を
    保持させない」ことが確認済み事項として明記されている
```

### Alternative C：WordPressOutput.save()へMediaUploadResultを追加

不採用。理由：

```text
既存Public API（save(article: ArticleData) -> SaveResult）の変更が必要になる
payload構築責務とBinding責務が同一メソッド内に混在する
既存E2E（WordPressOutput.save()のsignatureを固定しているもの）への
    Regression範囲が拡大する
```

### Alternative D：resolve_media_id()内部でUpload

不採用。理由：

```text
image_resolverへHTTP Side Effectが混入する
Uploaderの依存注入が新たに必要になる
既存stub責務（v1.6.0時点の設計）を大きく変更することになる
Runtime WiringまでScopeが拡大し、本Foundationの単一責務を超える
```

### Alternative E：main.pyで直接ArticleDataを変更

不採用。理由：

```text
Foundationとして分離できない
main.py（Pipeline全体）への変更が避けられない
テストが困難になる（main.py全体のセットアップが必要になる）
Composition Rootへの責務集中を招く
```

### Alternative F：WordPressPostRequest model導入

不採用。理由：

```text
既存Contract（ArticleData.featured_media_id + WordPressOutput）だけで
    対応可能であり、新規Request modelを導入する必然性がない
過剰設計（YAGNI）
既存WordPressOutput API変更の可能性を伴う
Release Scopeが本来の目的（Bindingのみ）を超えて拡大する
```

## 29. Rejected Alternatives

（28章の6案に同じ。加えて、10.1節で検討したPublic API形状の却下案を以下に記す）

| 案 | 却下理由 |
|---|---|
| `ArticleFeaturedMediaBinder`クラス＋`bind()`インスタンスメソッド（Constructor空実装） | 依存を注入する必要がなく、空のConstructorを持つclassは「request単位stateや
dependencyを保持するためだけのConstructor」に該当しうる。既存precedent（`image_resolver.py`・`taxonomy_config.py`）がmodule-level functionを一貫して採用しているため、これに合わせた（10.1節） |
| `@staticmethod`を持つクラス | クラス自体が状態も抽象化も提供せず、`ClassName.method()`という間接参照が増えるだけで実利がない |
| `MediaUploader` Protocol等の抽象化を新設し、本層をその実装として位置づける | 本層はUploaderを扱わない（Media Upload自体を実行しない、AD-1・AD-5）。Protocol化の対象がそもそも存在しない |

## 30. Risks

```text
本層のPublic Contract（bind_featured_media）を、将来のRuntime Wiring
    （Media Upload実行を含むCaller）が正しい順序・タイミングで呼び出す
    という前提に依存している。呼び出し忘れ・二重呼び出し等はCaller側の
    実装品質に依存し、本層自身では防げない（Foundation Firstの性質上の
    制約であり、既存v6.9.0〜v6.12.0とも共通のリスク）
14章の「常に決定的上書き」方針は、将来Callerが誤って古いMediaUploadResult
    （例：Retryで再生成された無効なmedia_id）を渡した場合でも防御しない。
    本層は「渡された値をそのまま反映する」ことのみを保証し、渡された値の
    ビジネス的な正しさまでは保証しない
```

## 31. Known Issues

なし（本Architecture Design時点で確認されたKnown Issueはない）。

## 32. Open Questions

```text
なし
```

候補調査（Release 6.13候補調査）で提起されたOpen Questions（画像生成呼び出しのタイミング、Retry時の重複Upload対策、resolve_media_id()への依存注入方式）は、いずれも本Release（Binding Contractのみ）のScope外であり、33章（Future Candidates）で後続Release側の論点として引き継ぐ。本層自体のPublic Contract（Package／Class／API形状・Validation・Error・State・Dependency Direction・既存featured_media_id扱い）については、本文書内ですべて確定できたと判断する。

## 33. Future Candidates

以下は、本Release完了後の別Releaseで検討する候補である。番号・正式名称は本文書で確定しない。

```text
AI画像生成Runtime Wiring
    （OpenAIImageGenerator.generate()を実際に呼び出す経路の確立）

生成画像Media Upload Runtime Wiring
    （GeneratedImageWordPressMediaUploader.upload()を実際に呼び出す経路の確立）

MediaUploadResult → ArticleData BindingのRuntime接続
    （本Release（bind_featured_media()）を実際に呼び出すCaller／
     Composition Root／Pipelineの追加。image_resolver.py・main.pyへの
     変更を伴う可能性がある）

Upload成功後の記事投稿失敗時の整合性
    （WordPress側に残る未使用Mediaの扱い、ロールバック方針の確立）

Retry時の重複Upload対策
    （24章で確認したとおり、現在のRetry機構はmain.py subprocess単位の
     粗粒度な再実行であり、Media単位のidempotencyを持たない）

既存media ID再利用
    （同一画像・同一記事に対する再アップロード回避の判定方式）

未使用Media cleanup
    （孤立したWordPress Mediaオブジェクトの検出・削除方針）
```

## 34. Implementation File Plan

```text
新規（Production Code、実装工程で作成。本Architecture Design工程では作成しない）：
    projects/03_game_content_ai/src/article_featured_media/__init__.py
    projects/03_game_content_ai/src/article_featured_media/article_featured_media_binder.py

新規（Test、実装工程で作成。本Architecture Design工程では作成しない）：
    projects/03_game_content_ai/tests/test_e2e_v6_13_0_article_featured_media_binding_foundation.py

変更：
    なし

削除：
    なし
```

## 35. Review Checklist

21章（Architecture Designセルフレビュー）の全項目を、本文書内の該当章と突き合わせて確認した。

```text
[x] Release GoalがMediaUploadResult → ArticleData Bindingだけに限定されている（5章）
[x] ArticleData定義変更を要求していない（3.1節・7章・27章）
[x] WordPressOutput変更を要求していない（3.2節・7章・27章）
[x] image_resolver変更を要求していない（3.4節・7章）
[x] main.py変更を要求していない（7章）
[x] 画像生成をScopeへ含めていない（7章）
[x] Media Upload実行をScopeへ含めていない（7章）
[x] HTTP Side Effectがない（22章）
[x] 元ArticleData非mutationが明記されている（5章・12章・13章）
[x] 新しいArticleDataを返すContractが明記されている（10章・13章）
[x] media_idだけをfeatured_media_idへ反映する（13章）
[x] source_urlをfeatured_mediaへ使用しない（3.3節・AD-14）
[x] Dependency Directionが一方向（19章）
[x] 循環importがない（19.1節）
[x] validation順序が確定している（16章）
[x] 例外Contractが確定している（17章）
[x] 既存featured_media_idの扱いが確定している（14章）
[x] State非保持が明記されている（18章）
[x] Retry／重複UploadがOut of Scope（7章・24章）
[x] Future Runtime Wiringが分離されている（33章）
[x] E2E Test StrategyがContractを直接検証している（25章）
[x] Regression基準がRelease 6.12記録と一致している（26章：1931/1931 PASS基準）
```

矛盾は確認されなかった。

## 36. Review History

```text
2026-07-18: Claude Code（Architecture Designドラフト初版作成）。
    Architecture Review・Code Review・Release Reviewはいずれも未実施。

2026-07-18: Architecture Review（Claude Codeによる独立Review）：Approved。
    Blocking Issueなし。Critical 0件・Major 0件・Minor 2件（AR-m-1：7章・11章・
    24章の「13章（Future Candidates）」誤参照3箇所＋独立検索で追加発見した
    11章の同種誤参照1箇所、計4箇所。AR-m-2：State Contract E2E Guardが
    module-levelのAssign検査のみでglobal文・nonlocal文（関数本体内）を
    検出しない）・Suggestion 2件（AR-S-1：Reverse Dependency Guardのvacuous
    pass耐性、v6.12 Code Review継続Suggestion CR-S-1と同種。AR-S-2：
    ValueError採用根拠の precedent引用不足）。いずれもNon-Blocking。

2026-07-18: Implementation＋新規E2E作成（Claude Code）。
    Architecture Review Finding AR-m-1・AR-m-2・AR-S-1・AR-S-2を本文書へ反映
    （0.1節は変更なし、7章・11章・24章の章参照修正、18.2節・18.3節・25.3節へ
    ast.Global／ast.Nonlocal検出Guardを追加、20章・25.1節へReverse Dependency
    Guardのvacuous pass防止手順を追加、15章へValueError採用根拠のprecedent
    引用を追加）。Production Code（src/article_featured_media/__init__.py,
    article_featured_media_binder.py）と新規E2E
    （tests/test_e2e_v6_13_0_article_featured_media_binding_foundation.py、
    24 Scenario・123 Assertion）を作成し、新規E2E単独実行で123/123 PASS・
    終了コード0・Warning／Traceback 0件を確認した。Formal Regression（既存
    15ファイル1931件との合算実行）は本工程では実施していない（Code Review
    Approved後の別工程）。Code Reviewは未実施のため、Code Review状態は
    Not Startedのまま変更していない。

2026-07-18: Code Review（Claude Codeによる独立Review）：Approved。Blocking
    Issueなし。Critical 0件・Major 0件・Minor 4件（CR-m-1：32章Open Questionsに
    AR-m-1未反映の「13章（Future Candidates）」誤参照が1箇所残存。CR-m-2：20章が
    Reverse Dependency Guardについて相対importも検出すると記載していたが、実際の
    E2E（DEP-2）は絶対importのみを検査。CR-m-3：E2E DEP-1のFORBIDDEN_EXACTに
    設計書19章・25.1節が明記する`scripts`が含まれていない。CR-m-4：Implementation
    報告内の「forループcase数：11」という記載が実際の合計13と不一致。ファイル
    修正対象なし）・Suggestion 1件（CR-S-1：FIELD-1／MUT-1のdataclasses.fields()
    利用箇所にfields一覧非空Assertionがない、vacuous pass耐性強化の余地）。
    いずれもNon-Blocking。

2026-07-18: Code Review Non-Blocking Finding修正（Claude Code）。CR-m-1（32章の
    誤参照「13章」を「33章」へ修正、他に同種誤参照が残っていないことを確認）・
    CR-m-2（20章のReverse Dependency Guard記述を、本プロジェクトのsrc直下
    top-level package構造を根拠として絶対importのみを検査する記述へ修正。
    相対importでの到達経路が構造的に存在しないことを明記し、AR-S-1のvacuous
    pass防止5手順は維持）・CR-m-3（E2EのDEP-1 FORBIDDEN_EXACTへ`"scripts"`を
    追加）を反映した。CR-m-4（報告内の集計記載ミスのみで対象ファイルなし）・
    CR-S-1（Non-Blocking Suggestion）は今回対応せずDeferredのまま維持する。
    修正後、新規E2Eを単独再実行し123/123 PASS・終了コード0を維持することを
    確認した（`scripts`追加はDEP-1の集合メンバーシップ判定にのみ影響し、
    forループの反復回数自体を増やす変更ではないため、Assertion総数は123のまま
    変化しない）。Production Code・Public API・Validation・Architecture Contract・
    既存E2E・統合文書はいずれも変更していない。

2026-07-18: Formal Regression（Claude Code）：PASS。正式対象16ファイル（既存15
    ファイル＋新規v6.13.0 E2E）を実行順序どおり実行し、既存15ファイル1931/1931
    PASS（Baseline維持、新規差分なし）＋新規v6.13 E2E 123/123 PASS＝総合
    2054/2054 PASS。FAIL 0・Warning 0・終了コード非0 0・実HTTP／実credential
    読込／実課金いずれもなし。Blocking Issueなし。

2026-07-18: Documentation Integration（Claude Code）：Completed。本文書の
    Header・Review History・26.1節（Formal Regression実績）を更新するとともに、
    `docs/ROADMAP.md`（v3.x以降の候補セクションへ`[x]` Article Featured Media
    Binding Foundation実績・後続候補`Article Featured Media Runtime Wiring`を
    追加）・`docs/architecture.md`（`article_featured_media` component節を新設、
    Consumer-less Foundation・Runtime未接続を明記）・`docs/CHANGELOG.md`
    （`## [v6.13.0]`Entryを新規追加、Added／Public API／Architecture・Behavior／
    Tested／Scopeを記載）へ反映した。過去Release（v1.11.0〜v6.12.0）の記録は
    いずれも変更していない。Architecture変更なし、Blocking Issueなし。

2026-07-18: Release Review（Claude Codeによる独立Review）：Approved。Critical
    0件・Major 0件・Minor 0件・Suggestion 0件、Blocking Issueなし、Open
    Questionsなし。Architecture Design・Architecture Review・Production
    Implementation・New E2E・Code Review・Architecture Review／Code Review
    Finding反映・Formal Regression・Documentation Integration・文書間整合・
    Historical Recordのすべてを横断確認し、いずれも適合と判定した。Release
    成果物7ファイル（正式設計書1・Production 2・新規E2E 1・統合文書3）を承認。
    Architecture Designからの逸脱・Public Contract変更・Production Scope
    変更・Out of Scope混入はいずれもなし。
```

---

（本文書はArchitecture Design・Architecture Review Approved・Production Implementation Completed・New E2E Completed・Code Review Approved（Non-Blocking Finding CR-m-1/CR-m-2/CR-m-3反映済み、CR-m-4／CR-S-1はDeferred）・Formal Regression PASS（2054/2054）・Documentation Integration Completed・Release Review Approvedをもって、Release 6.13として完了した。）
