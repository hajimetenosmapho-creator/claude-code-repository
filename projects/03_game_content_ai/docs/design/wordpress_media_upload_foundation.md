# WordPress Media Upload Foundation — Architecture Design（v6.9.0）

作成日：2026-07-15
作成者：Claude Code（Architecture Designドラフト・Review指摘反映・Documentation）／ChatGPT（Architecture Review）／ユーザー（最終承認）
状態：**Design Freeze**
分類：**Architecture Release**（development_workflow.md 6章・7章。新規独立package・新規Public API・新規Dependency方向の確立を伴うため）

---

## 1. Release概要

WordPress REST API（`POST /wp-json/wp/v2/media`）へ画像バイナリをアップロードし、`media_id`を取得するだけの独立Foundationを追加する。

```text
image_bytes（呼び出し元が既に保持するバイナリ）
    ↓
WordPressMediaUploader.upload()
    ↓
MediaUploadResult（media_id / source_url / mime_type）
```

本Releaseは**Consumer-less Foundation**である。既存の記事投稿Pipeline（`WordPressOutput`）・アイキャッチ解決処理（`image_resolver.py`）・`ArticleData`・AI画像生成のいずれへも配線しない。

## 2. Release分類

**Architecture Release**（development_workflow.md 6章・7章）。新規独立package（`src/wordpress_media/`）の追加、新規Public API・新規例外型の確立を伴うため、v6.3.0（Retry Metrics Foundation）以降一貫している「新規パッケージ追加はArchitecture Releaseに分類する」という既存precedentに合致する。

## 3. Status

```text
Architecture Design：Completed
Architecture Review：Approved
Test Review：Approved
Code Review：Approved
Implementation：Completed
Release Review：Approved
```

## 4. 現状と背景（現行実装調査結果）

Architecture Design着手前に、既存WordPress連携コードを実読し、以下を確認済みである。

- `WordPressOutput.save()`（`src/outputs/wordpress_output.py`）は`requests.post(endpoint, json=payload, auth=(username, app_password), timeout=30)`というJSON送信パターンを使用している。WordPress Media API（`/wp-json/wp/v2/media`）はJSONではなく**画像の生バイナリをリクエストボディへ直接乗せる**別形式のため、`json=`パターンはそのまま流用できない。
- 認証は`auth=(username, app_password)`というHTTP Basic認証のタプルのみで、Media APIでも同一の認証情報が使える見込みである。
- `WordPressOutput.from_env()`は不足環境変数があっても例外を出さず、空文字のまま`WordPressOutput`を生成する（有効性判定は呼び出し側の`is_available()`に委ねるNull許容方式）。プロジェクト全体（`publishing_config.py` / `src/ai/claude_client.py`等）を横断調査した結果、**`from_env()`が不足値を検出して例外を送出する既存precedentはプロジェクト内に1件も存在しない**ことを確認した。本Foundationの「from_env()で不足値を明確に検出する」という方針は、既存precedentへの整合ではなく、本Foundation固有の新規Architecture Decisionである（AD-6）。
- 既存`SaveResult`（`src/outputs/save_result.py`）は投稿結果向けの構造（`post_id` / `slug` / `permalink`等）であり、Media Upload結果には適合しない。
- テストは`tests/test_e2e_v1_11_0_save_result.py`で`unittest.mock.patch("requests.post", return_value=mock_response)`によりWordPress APIをモックする既存パターンが確立されており、本Foundationでも流用可能である。
- `wordpress_media`という名称の既存コードはプロジェクト内に存在せず、完全新規実装である。

## 5. Design Goal

1. 画像bytesをWordPress Media Libraryへアップロードし`media_id`を取得できるようにする
2. 既存WordPress連携（`WordPressOutput`）・記事生成Pipeline・`image_resolver.py`・`ArticleData`へ一切影響を与えない
3. 将来のAI画像生成・Wiring Releaseが`upload()`を呼び出すだけで済む状態にする
4. 入力を自動修正せず、不正値はfail-fastで拒否する
5. 認証情報・画像バイナリ・レスポンス生データをPublic APIや例外へ漏らさない
6. Foundation Firstを維持する（消費者不在の先行実装として安全に導入する）
7. 1 Release＝1目的を維持する

## 6. Non-Goals

9章 Out of Scopeに同じ。

## 7. Package Boundary

新規独立package：

```text
projects/03_game_content_ai/src/wordpress_media/
├── __init__.py
├── media_upload_result.py       # MediaUploadResult（frozen dataclass）
└── wordpress_media_uploader.py  # WordPressMediaUploader + WordPressMediaUploadError
```

`src/outputs/`には配置しない。理由：

- WordPress記事投稿とは別のMedia Upload責務である
- 将来のAI画像生成・`featured_media` Wiringから独立させる
- 既存`WordPressOutput`へ依存しないFoundationとする
- 逆依存を防ぐ

`WordPressMediaUploadError`は独立ファイルへ分けず、`wordpress_media_uploader.py`内に定義する（唯一の送出元であり、不要なファイル分割を避けるため）。

## 8. Package root Public API

`src/wordpress_media/__init__.py`から公開するのは次の3つのみとする。

```python
from .media_upload_result import MediaUploadResult
from .wordpress_media_uploader import (
    WordPressMediaUploadError,
    WordPressMediaUploader,
)

__all__ = [
    "MediaUploadResult",
    "WordPressMediaUploadError",
    "WordPressMediaUploader",
]
```

利用側へ内部モジュール（`media_upload_result` / `wordpress_media_uploader`）への直接importを要求しない。

## 9. Public Model

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class MediaUploadResult:
    media_id: int
    source_url: str | None
    mime_type: str | None
```

契約：frozen／3フィールドのみ／フィールド順固定／成功時のみ生成／HTTPライブラリ詳細を保持しない／Methodを追加しない。

含めないもの：`success` / `error_message` / `raw_response` / `requests.Response` / `status_code` / `filename`。

理由：成功時のみResultを返すため`success`は不要（失敗は例外で表現する）。HTTPライブラリ詳細をPublic Modelへ漏らさない。`raw_response`保持は過剰責務。

`source_url` / `mime_type`が`str | None`である理由：WordPressレスポンスにキー自体が**存在しない**場合は異常（21章でエラー）とするが、キーが存在し値がJSON `null`の場合はそのまま`None`を許容するという区別を型で表現するため。

## 10. Public Exception

```python
class WordPressMediaUploadError(RuntimeError):
    pass
```

専用例外はこの1種類のみ。過剰な例外階層は作らない。

## 11. WordPressMediaUploader Public API

```python
class WordPressMediaUploader:
    def __init__(
        self,
        site_url: str,
        username: str,
        app_password: str,
    ) -> None:
        ...

    @classmethod
    def from_env(cls) -> "WordPressMediaUploader":
        ...

    def upload(
        self,
        image_bytes: bytes,
        filename: str,
        mime_type: str,
    ) -> MediaUploadResult:
        ...
```

## 12. Constructor Contract

直接Constructorでもfail-fast validationを行う。

以下は`ValueError`とする：

```text
site_url / username / app_password がstrではない
site_url / username / app_password が空
site_url / username / app_password が空白のみ
```

`site_url`のみ次で正規化する：

```python
normalized_site_url = site_url.strip().rstrip("/")
```

正規化後に空となる場合も`ValueError`とする。URL scheme／hostの厳密な構文検証はOut of Scope。

`username` / `app_password`は、空白のみかどうかの判定に`strip()`を使うが、保存値そのものをFoundation側で勝手にstripしない（呼び出し元が渡した値をそのまま保持する）。

例外メッセージには、無効な**フィールド名のみ**を含め、`username` / `app_password`の値は含めない。

## 13. from_env Contract

使用する環境変数（新規追加なし）：

```text
WP_SITE_URL
WP_USERNAME
WP_APP_PASSWORD
```

不足・空文字・空白のみの場合は`ValueError`とし、例外には**不足した環境変数名のみ**を含め、値は含めない。取得値はConstructorへ渡し、Constructor Validation（12章）も通過させる（二重検証）。

禁止：`load_dotenv` / `python-dotenv`追加 / `.env`読込。

## 14. Upload Input Contract

すべてHTTP通信（`requests.post()`）より前に検証し、不正時は`ValueError`を送出して`requests.post()`を一切呼び出さない。暗黙変換は行わない。

### image_bytes

```text
bytes型のみ許可
空bytes禁止
```

拒否：`str` / `bytearray` / `memoryview` / `None` / その他の型。

### filename

filenameはPathではなく、安全な純粋ファイル名として扱う。

```python
_FILENAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
```

許可例：`article-image.png` / `game_news_001.webp` / `thumbnail-01.jpg`

拒否例：空文字列／空白のみ／`../image.png`／`folder/image.png`／`folder\image.png`／`"image".png`／`image\r\nInjected.png`／`画像.png`／`_hidden.png`／`-image.png`

Unicode filename・RFC 5987の`filename*=`対応・自動サニタイズ・basename抽出はOut of Scope（正規表現1本で全拒否条件を満たし、追加のエスケープ処理を不要にする設計とする）。

### mime_type

```text
str型
空ではない
空白のみではない
mime_type == mime_type.strip()（前後空白があれば拒否。自動trimしない）
制御文字を含まない（\r・\n・NUL・DELを含む）
```

`ValueError`となる例：`" image/png"` / `"image/png "` / `"image/png\r\nInjected"`

MIME許可リスト・拡張子との一致・Magic Number検査はOut of Scope。

## 15. HTTP Request Contract

```python
endpoint = f"{self.site_url}/wp-json/wp/v2/media"

response = requests.post(
    endpoint,
    data=image_bytes,
    headers={
        "Content-Type": mime_type,
        "Content-Disposition": f'attachment; filename="{filename}"',
    },
    auth=(self.username, self.app_password),
    timeout=30,
)
```

- filenameは14章の正規表現通過済みのため、引用符・改行を含みえないことが保証され、追加エスケープなしでヘッダーへ安全に埋め込める。
- 禁止：`json=` / `files=`（multipart/form-data） / Base64 / URL入力 / Path入力
- `site_url`は既存`WordPressOutput`と同じ`rstrip("/")`規約（12章）で二重スラッシュを防ぐ
- Timeout：既存`WordPressOutput`が`timeout=30`を採用済みであることを踏まえ、本Foundationも同じ30秒を採用する（新規導入ではなく既存precedentの踏襲、AD-7）
- 成功判定：`200 <= response.status_code < 300`。`response.ok`には依存しない（AD-17）

## 16. Processing Order

処理順を固定する：

```text
1. 入力検証（image_bytes / filename / mime_type）
2. requests.post()
3. requests.RequestException → WordPressMediaUploadErrorへ変換
4. HTTP statusが2xxか判定
5. response.json()
6. JSON objectか判定
7. 必須フィールド検証（id / source_url / mime_type）
8. MediaUploadResult生成
```

## 17. Success Response Contract

成功レスポンスJSONはobjectである必要がある。

| フィールド | 契約 |
|---|---|
| `id` | キー必須／`bool`を除く`int`／1以上（WordPressの自動採番IDは1始まりのため、0以下は異常値として扱う） |
| `source_url` | キー必須／`str`または`None`（値が存在せずキー自体が欠落している場合はエラー） |
| `mime_type` | キー必須／`str`または`None`（同上） |

それ以外の型は`WordPressMediaUploadError`。追加のレスポンス項目は無視する。成功系の`response.json()`が失敗（decode failure）した場合も`WordPressMediaUploadError`。

## 18. Failure Contract

| ケース | 例外 |
|---|---|
| 入力不正（14章） | `ValueError` |
| `requests.RequestException`（接続失敗・Timeout等） | `WordPressMediaUploadError`（固定Public message、元例外全文は連結しない） |
| 非2xxレスポンス | `WordPressMediaUploadError`（HTTP status必須、安全に取得できる場合のみWordPress側`code`/`message`を付加） |
| レスポンスJSON decode失敗 | `WordPressMediaUploadError` |
| レスポンスがJSON object以外 | `WordPressMediaUploadError` |
| `id`欠落／型不正／0以下 | `WordPressMediaUploadError` |
| `source_url` / `mime_type`キー欠落／型不正 | `WordPressMediaUploadError` |

**`requests.RequestException`**：

```python
raise WordPressMediaUploadError(
    "WordPress Media APIへの通信に失敗しました"
) from exc
```

元例外の全文をPublic messageへ連結せず、例外チェーン（`from exc`）のみで保持する。

**非2xxレスポンス**：HTTP status codeを必ず含める。加えて、レスポンスが安全にJSON objectとしてパースでき、`code` / `message`が`str`型の場合のみ、以下の制限付きで使用する。

```text
code：最大100文字
message：最大200文字
```

改行・タブ・制御文字は空白へ正規化する。JSONでない場合、objectでない場合、`code` / `message`が`str`でない場合は、それらを例外へ含めずHTTP statusのみを使用する。

**禁止**：`response.text`直接埋め込み・`response.content`直接埋め込み・`username`埋め込み・`app_password`埋め込み・`image_bytes`埋め込み・`auth`タプル埋め込み。

## 19. Security Contract

以下を例外・ログ・Resultへ含めない：

```text
username
app_password
auth tuple
image_bytes
response.text
response.content
```

本Foundationは`print()` / `logging`のいずれも行わない。

## 20. Side Effect／I/O Contract

許可される外部I/O：`requests.post()`によるHTTP通信のみ。

禁止：ファイル読込／ファイル書込／Path操作／一時ファイル／URLダウンロード／画像加工／ログ出力／標準出力／標準エラー出力／`subprocess`。

## 21. Dependency Direction

```text
許可：
wordpress_media → standard library
wordpress_media → requests

禁止：
wordpress_media → WordPressOutput
wordpress_media → image_resolver
wordpress_media → ArticleData
wordpress_media → Workflow
wordpress_media → Scheduler
wordpress_media → Retry Runtime
```

既存側から`wordpress_media`へのimportも本Releaseでは行わない（Wiringは対象外）。

## 22. Compatibility

既存production codeは無改修である：`WordPressOutput` / `image_resolver.py` / `ArticleData` / 記事生成Pipeline / Workflow / Scheduler / Retry Runtime。すべて既存動作を維持する。新規独立packageの追加のみであり、既存の呼び出し元（現状ゼロ）にも影響しない。

## 23. In Scope

```text
src/wordpress_media/__init__.py
src/wordpress_media/media_upload_result.py
src/wordpress_media/wordpress_media_uploader.py
MediaUploadResult
WordPressMediaUploader
WordPressMediaUploadError
新規E2E Test
正式Architecture Design文書（本文書）
```

## 24. Out of Scope

```text
AI画像生成
画像生成プロンプト
Path入力
URL入力
画像ダウンロード
画像ファイル保存
一時ファイル
画像リサイズ
画像圧縮
画像形式変換
EXIF処理
featured_media設定
ArticleData変更
image_resolver.py変更
WordPressOutput変更
既存投稿Pipeline変更
Workflow統合
Scheduler統合
Retry統合
Rate Limit
Deduplication
Cache
実WordPress E2E
Media削除
Media更新
Alt text設定
Caption設定
Description設定
SNS画像
Unicode filename
RFC 5987 filename*
filename自動サニタイズ
Pathからのbasename抽出
URL scheme／host厳格検証
MIME許可リスト
Magic Number検査
```

---

## 25. E2E Test Strategy（概要）

詳細なScenario設計はTest Design（別文書工程）で確定する。本章では検証すべきカテゴリのみを記録する。

```text
Public Model Contract
Package root Public API
Constructor Contract
from_env Contract
Upload Input Validation（image_bytes / filename / mime_type）
HTTP Request Contract
Success Response Contract
Failure Contract（RequestException / Non-2xx / JSON不正）
Security Contract
Dependency Direction
Scope Guard
Side Effect Guard
Backward Compatibility
```

実WordPress環境への通信は行わない。`requests.post()`をFake／Mock化する。Working Tree／`git diff`状態は恒久E2Eへ含めない。

## 26. Regression Test Strategy

```text
既存Regression：v5.9.0〜v6.8.0
ベースライン：1140/1140 PASS
```

次を確認する：ベースライン件数不変・FAILなし・終了コード0・警告なし・Tracebackなし・既存Regressionファイル無改修。既存production code無改修の確認は、Release Review時に`git diff --name-status` / `git status --short`で行う（恒久E2EへGit状態を含めない）。

## 27. Documentation Strategy

Release 6.9で更新予定の文書：

```text
projects/03_game_content_ai/docs/design/wordpress_media_upload_foundation.md（本文書）
projects/03_game_content_ai/docs/architecture.md
projects/03_game_content_ai/docs/ROADMAP.md
projects/03_game_content_ai/docs/CHANGELOG.md
```

本工程（Architecture Design）では、新規設計書（本文書）のみを作成する。`architecture.md` / `ROADMAP.md` / `CHANGELOG.md`の更新は実装完了後のDocumentation Update工程で行う。

## 28. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| WordPress側のMedia Endpoint固有の挙動（プラグインによる無効化・nonce要求等）が実装時に判明する | Architecture Reviewでは一般的なWordPress REST API仕様を前提とし、実装時に想定外の挙動が判明した場合はImplementation段階で報告し、必要ならAI構成を「高い」へ引き上げて再設計する |
| filename正規表現が将来の正当なファイル名を過剰に拒否する | v1では意図的にASCII安全文字へ限定する方針とし、拡張が必要になった時点で別Releaseとして検討する（Unicode対応はOut of Scope） |
| Content-Disposition／Content-Typeヘッダーインジェクション | filename／mime_typeを正規表現・制御文字チェックで検証してからヘッダーへ埋め込み、追加のエスケープ処理には依存しない設計とする |
| 例外メッセージからの情報漏洩 | `response.text` / `response.content` / 認証情報 / 画像バイナリを一切例外へ含めず、安全にパースできた`code`/`message`のみを長さ制限・制御文字正規化のうえで使用する |
| 将来Wiring時の重複実装 | `image_resolver.py` / `WordPressOutput`への配線判断は本Releaseの対象外とし、Future Extensionsとして明示的に持ち越す |

## 29. Alternatives Considered

| 案 | 却下理由 |
|---|---|
| `src/outputs/`内へ配置 | WordPress記事投稿とは別責務であり、将来のAI画像生成・Wiringから独立させるため独立packageを選択 |
| Path入力を受け付ける | Foundation責務へファイルシステムI/Oを含めない方針とし、将来AI画像生成結果を一時ファイルなしで直接渡せるようbytes入力に限定 |
| multipart/form-data（`files=`）形式 | WordPress REST APIは生バイナリボディ＋Content-Dispositionヘッダーでも受理可能であり、既存`WordPressOutput`の`requests.post()`利用パターンとの一貫性を優先 |
| `MediaUploadResult`に`success`/`error_message`を含める | 成功時のみResultを返す設計とし、失敗は例外で一元的に表現する方が呼び出し側の分岐が単純になる |
| `requests.RequestException`をそのまま伝播 | 呼び出し側に`requests`ライブラリの知識を要求しない設計を優先し、`WordPressMediaUploadError`への変換を採用 |
| filenameの自動サニタイズ・basename抽出 | 入力を自動修正するとエラーの発見が遅れるため、fail-fastで拒否する方針を優先 |
| MIME自動推測（`mimetypes.guess_type()`等） | v1では単純さを優先し、呼び出し側の明示指定のみとした |

## 30. Technical Debt

```text
Path／URL入力アダプタ未実装
MIME許可一覧・拡張子検証未実装
ファイルサイズ上限未検討
Media削除・更新・Alt text・Caption・Description設定未実装
ArticleData／WordPressOutput／image_resolver.pyへのWiring未実装
Unicode filename対応未実装
RFC 5987 filename*未対応
```

## 31. Open Questions

```text
Architecture Design段階で未解決のOpen Questionなし
```

## 32. Architecture Decision Summary

| # | 内容 |
|---|---|
| AD-1 | Package配置：`src/wordpress_media/`独立package（`src/outputs/`には配置しない） |
| AD-2 | 入力Contract：`image_bytes: bytes` / `filename: str` / `mime_type: str`（Path・URL非対応） |
| AD-3 | Result Contract：成功時のみ`MediaUploadResult(media_id, source_url, mime_type)` |
| AD-4 | Failure Contract：入力不正は`ValueError`、それ以外（通信・HTTP・レスポンス不正）は`WordPressMediaUploadError` |
| AD-5 | MIME Contract：呼び出し側が明示指定、自動推測・検証なし |
| AD-6 | `from_env()`の失敗検出：プロジェクト内に前例がないため新規決定。不足時`ValueError`（パッケージ内Validation規約と統一） |
| AD-7 | Timeout：既存`WordPressOutput`と同じ30秒を採用（新規導入ではなく既存踏襲） |
| AD-8 | `id`検証：`bool`除外・`int`型必須・1以上必須（0以下は異常値） |
| AD-9 | （AD-14により置換）例外メッセージの安全化方針 |
| AD-10 | 例外クラス分割：`WordPressMediaUploadError`を`wordpress_media_uploader.py`内に定義し、別ファイルへ分割しない |
| AD-11 | filename Header Safety Contract：正規表現`^[A-Za-z0-9][A-Za-z0-9._-]*$`によるASCII安全文字限定。不一致は`ValueError` |
| AD-12 | Constructor Validation Contract：`__init__` / `from_env()`双方で型・非空検証をfail-fast実施。無効フィールド名のみ例外に含める |
| AD-13 | Runtime Type Validation Contract：`image_bytes`は`bytes`型のみ、`filename` / `mime_type`は`str`型のみを受理し、`bytearray` / `memoryview` / 暗黙変換は行わない |
| AD-14 | Safe Error Message Contract：`response.text`直接埋め込みを廃止し、安全にパース済みの`code`（最大100字）/`message`（最大200字、制御文字正規化）のみを使用。`RequestException`は固定安全メッセージ＋例外チェーンのみ |
| AD-15 | Package root Public APIは`MediaUploadResult` / `WordPressMediaUploadError` / `WordPressMediaUploader`の3種類のみ |
| AD-16 | mime_type前後空白は自動修正せず拒否（`mime_type == mime_type.strip()`を要求） |
| AD-17 | HTTP成功判定は`200 <= response.status_code < 300`（`response.ok`に依存しない） |

## 33. Implementation File Plan

**新規production code**（実装Release承認後に作成）

```text
projects/03_game_content_ai/src/wordpress_media/__init__.py
projects/03_game_content_ai/src/wordpress_media/media_upload_result.py
projects/03_game_content_ai/src/wordpress_media/wordpress_media_uploader.py
```

**新規テスト**（同上）

```text
projects/03_game_content_ai/tests/test_e2e_v6_9_0_wordpress_media_upload_foundation.py
```

**変更なし（既存無改修方針）**

```text
src/outputs/wordpress_output.py
src/image_resolver.py
src/outputs/base.py（ArticleData）
既存記事生成Pipeline全体
Workflow / Scheduler / Retry Runtime全体
既存テストファイル一式
```

---

## 34. Review History

```text
Architecture Review 1：Changes Required
    指摘4件：
    1. Header値の安全性（filename／mime_typeのヘッダーインジェクション対策）
    2. Constructor Validation（直接指定時のfail-fast検証が未定義）
    3. Runtime Type Validation（upload()引数の実行時型検証が未定義）
    4. Safe Error Message Contract（response.textの直接埋め込みリスク）
    状態：4件とも Resolved

Architecture Review 2：Approved

Test Review 1：Changes Required
    指摘8件：
    1. Scenario／Case／Test Pointの混在
    2. Test Runner（pytest／monkeypatch）が未確定
    3. requests.postのMock Patch targetが不明確
    4. JSON Decode Failure Contractがjson.JSONDecodeErrorへ過度に依存
    5. Non-2xxのcode／message個別採用が不足
    6. sanitize／truncateの処理順序が未確定
    7. Security Scenarioの重複
    8. Compatibility／RegressionがE2E Scenario数に混在
    状態：8件とも Resolved

Test Review 2：Changes Required
    指摘3件：
    1. DEP-2が許可されたrequests.postも禁止するNetwork Contractになっていた
    2. Success Response Failure（SRF系）にSafe Failure Test Pointが不足
    3. import形式（`import requests`）がSource of Truth外のContractとして扱われていた
    状態：3件とも Resolved

Test Review 3：Approved（48 Scenario／115 Case／約215〜250 Assertion見積りで確定）

Code Review：Approved
    指摘1件：
    - DEP-1（禁止import Contract）が単純文字列検索であり、production codeのdocstring等の
      自然文中の単語（`image_resolver` / `ArticleData`）を誤検知する構造的脆弱性があった
      （実際に発生済み）
    修正：
    - production codeのdocstring表現を調整（Contract変更なし）
    - E2EのDEP-1を、`ast.Import` / `ast.ImportFrom`ノード解析による禁止import検知へ置き換え
    結果：
    - 新規E2Eは336アサーションから331アサーションへ整理（48 Scenario維持）
    - 331/331 PASS、production code自体への追加修正なし
    状態：Resolved

Release Review：Approved
    Architecture整合・Public API・HTTP Contract・Security Contract・Test Design整合
    （48 Scenario／331 Assertion実測）・Backward Compatibility（既存WordPressOutput／
    image_resolver.py／ArticleData／既存Pipeline／既存test無改修）をいずれも確認し、
    新規E2E 331/331 PASS・Regression 1183/1183 PASS（v1.11.0 43/43＋v5.9.0〜v6.8.0
    1140/1140）・合計1514/1514 PASSを確認した。
```

## 35. Review指摘反映一覧

| Review指摘 | 修正内容 | 反映章 | 状態 |
|---|---|---|---|
| Header値の安全性が未確定 | filename／mime_typeの構文安全契約（正規表現・制御文字禁止）を確定 | 14, 15, 32(AD-11) | Resolved |
| Constructor直接指定が未検証 | `__init__` / `from_env()`双方にfail-fast validationを追加 | 12, 13, 32(AD-12) | Resolved |
| Public入力の実行時型検証が未定義 | `bytes` / `str`の厳格型検証を追加、暗黙変換なし | 14, 32(AD-13) | Resolved |
| response.textの例外埋め込みリスク | safe parsed error fields（`code`/`message`、長さ制限・正規化）のみ使用 | 18, 32(AD-14) | Resolved |
| Scenario／Case／Test Point混在（Test Review 1） | 3階層（Scenario／Case／Test Point）へ再構成 | Test Design | Resolved |
| Test Runner未確定（Test Review 1） | 既存`check()`ベースE2Eへ統一、環境変数は標準ライブラリのみの`patched_environ`で復元 | Test Design, 実装 | Resolved |
| Mock Patch target不明確（Test Review 1） | `wordpress_media.wordpress_media_uploader.requests.post`へ確定、`import requests`契約と対応づけ | Test Design, 実装 | Resolved |
| JSON Decode例外型への過度な依存（Test Review 1） | `response.json()`が`ValueError`を送出、という一般契約へ変更 | 17, 19, 実装 | Resolved |
| Non-2xx code／message個別採用不足（Test Review 1・2） | 有効な方を個別採用する契約へ変更 | 18, 実装 | Resolved |
| sanitize／truncate順序未確定（Test Review 1） | 正規化後に長さ制限を適用する順序へ固定 | 18, 実装 | Resolved |
| Security Scenario重複（Test Review 1） | 各Failure Scenarioの共通Test Pointへ統合 | Test Design, 実装 | Resolved |
| Compatibility／Regression混在（Test Review 1） | 新規E2E／Release Review Checklist／Regression Execution Planへ分離 | Test Design | Resolved |
| DEP-2がrequests.postも禁止（Test Review 2） | `requests.post`のみ許可する許可外I/O Guardへ変更 | 実装, E2E | Resolved |
| SRF系Safe Failure Test不足（Test Review 2） | 秘密値・生レスポンス・不正値非露出の共通Test Pointを追加 | 実装, E2E | Resolved |
| import形式のContract化（Test Review 2） | Public ContractではなくTestability Constraintへ整理 | E2E | Resolved |
| DEP-1の単純文字列検索が誤検知（Code Review） | AST（`ast.Import`/`ast.ImportFrom`）解析へ置き換え | E2E | Resolved |

16件すべて`Resolved`。
