# Article Image Prompt Construction Foundation

## 0. Header／Status

```text
Release: v6.17.0
名称: Article Image Prompt Construction Foundation
分類: Architecture Release

Status:
  Architecture Design:      Completed
  Architecture Review 1:    Changes Required（Blocking 4・Non-Blocking 4）
  Architecture Amendment:   Completed（Blocking 4件すべてResolved）
  Architecture Review 2:    Approved with Suggestions（Blocking 0・Suggestion 3）
  Production Implementation: Completed（本文書と同時に実施）
  New E2E:                  Completed（本文書と同時に実施）
  Code Review:              Approved with Suggestions（Blocking 0・Major 0・Minor 3・Suggestion 3、
                             うちCR-1・CR-3はResolved、CR-2・CR-4〜CR-6はDeferred／Informational）
  Formal Regression:        Completed（正式Inventory20ファイル、既存19ファイル2508/2508 PASS
                             ＋Release 6.17新規136/136 PASS＝総合2644/2644 PASS。FAIL 0・
                             Warning 0・Traceback 0・終了コード非0なし・外部API実接続0）
  Documentation Integration: Completed（`docs/ROADMAP.md`／`docs/architecture.md`／
                             `docs/CHANGELOG.md`および本設計書を本工程で更新）
  Release Review:           Approved with Suggestions（Blocking 0・Major 0・Minor 1・
                             Suggestion 2。RR-M-1はResolved、RR-S-A・RR-S-Bは
                             Accepted／Informational。29章・29.1章・30章参照）

Release: Completed（Release Reviewを経て、Release 6.17として完了した）

新規E2E最終実績（CR-1・CR-3反映後、Current／Final Inventory）:
  43 Scenario・111 Case・136 Assertion、136/136 PASS・0 FAIL・exit code 0
  （Architecture Amendment直後の初回実績42 Scenario・109 Case・134 Assertionは
    Code Review Finding CR-3対応により更新済み。32章 Review Historyに履歴として記録）
```

本文書は、Architecture Design・Architecture Amendment・Architecture Review 2の
内容を完全統合したself-contained文書である。本文書単体で全Contractを確認できる。

---

## 1. Background

Release 6.10.0〜6.16.0で、AI画像生成からWordPress featured media設定に至る
一連のConsumer-less Foundationが整備された（AI Image Generation Contract／
OpenAI Image Generation Adapter／Generated Image WordPress Media Upload
Wiring／Article Featured Media Binding／Article Featured Media
Orchestration／Image Generation Configuration Gate／Generated Image
Filename Policy）。このうち`ArticleFeaturedMediaOrchestrator.apply(article,
prompt, filename)`は`prompt`を呼び出し側が供給する前提で設計されており
（`docs/design/article_featured_media_orchestration_foundation.md` §7
Out of Scope）、記事情報から実際にprompt文字列を構築する手段はRepository内
に存在しない。`src/article_featured_media_orchestration/article_featured_media_orchestrator.py:58-74`
の`apply(article, prompt, filename)`は`prompt`を呼び出し側から受け取るのみで、
`article`から`prompt`を導出する処理を一切含まない。また、
`src/ai_image_generation/`・`src/openai_image_generation/`・
`src/generated_image_wordpress_media/`・`src/article_featured_media/`・
`src/image_generation_config/`・`src/generated_image_filename_policy/`・
`src/ai/prompt_builder.py`のいずれにも、記事情報（`ArticleData`）から
画像生成用prompt文字列を構築するPublic APIは存在しない（各moduleを実読して
確認した事実であり、`src/ai/prompt_builder.py`の`PromptBuilder.build()`は
改善提案・リライト用のClaudeテキストプロンプト生成専用で対象外）。

## 2. Problem Statement

`ArticleFeaturedMediaOrchestrator.apply()`の`prompt`引数を、記事情報
（`ArticleData`）から決定論的に構築する手段が存在しない。この空白を埋めない
限り、将来のRuntime Wiringはpromptをハードコードするか手動で組み立てる以外
の選択肢を持たない。

## 3. Goals

- 記事のtitle・excerptから、`AIImageGenerator.generate(prompt)`および
  OpenAI Adapterのprompt validation contract（4章参照）と親和性の高い、
  決定論的なprompt文字列を構築するPublic APIを提供する。
- stateless・外部I/Oなし・provider非依存・WordPress非依存・
  environment非依存・日時／乱数／UUID／locale非依存を満たす。
- `main.py`・`image_resolver.py`・既存Runtime経路・
  `ArticleFeaturedMediaOrchestrator`の既存責務を一切変更しない
  （Runtime Zero Diff）。

## 4. Non-Goals

- filename生成（`generated_image_filename_policy`, v6.16.0の責務のまま）
- fallback／retry／idempotency／unused media cleanup
- 実際の画像生成API呼び出し
- Publish Composition Root／Runtime Wiring／Configuration Gate消費
- `article_body`全文のHTML／Markdown完全パース
- prompt injection semantic対策
- 詳細なvisual style／構図／配色指定
- 多言語翻訳・ローカライズ

---

## 5. Repository Evidence

以下はRepositoryを実読して確認した事実である（推測ではない）。

- `src/outputs/base.py:12-25` — `ArticleData`は11 field。title相当は
  `seo_title`、要約相当は`excerpt`（デフォルト`""`）。
- `main.py:99-119` — `_extract_excerpt()`が`article_body`から
  Markdown見出し・強調記法を除去し、最初の段落を最大150字に切り詰めて
  `excerpt`を生成する。API非呼び出し・ルールベース。
- `main.py:335, 347` — `excerpt`と`meta_description`は完全に同値
  （v1.4.0時点）。
- `src/outputs/wordpress_output.py:55-58` — `article_body`はWordPress
  `content`へそのまま渡され、この repository 内でHTML変換もエスケープも
  行われない。
- `src/openai_image_generation/openai_image_generator.py:45-94` —
  `_validate_prompt()`: `type(prompt) is not str`でstr型必須（v6.11.0時点の
  厳格な型判定）・非空白必須・32000字上限・`\t\n\r`以外の制御文字禁止。
- `src/article_featured_media_orchestration/article_featured_media_orchestrator.py:58-74`
  — `apply(article, prompt, filename)`は`prompt`を呼び出し側から受け取る
  のみで、`article`から導出しない。
- `src/ai/prompt_builder.py:19-59` — 既存`PromptBuilder.build()`は
  改善提案・リライト用のClaudeテキストプロンプト生成専用（別ドメイン）。
  未対応バージョン時に`print()`を実行する（本Foundationでは踏襲しない）。
- `docs/design/generated_image_filename_policy_foundation.md`
  （v6.16.0、直近precedent）:
  - §9.2相当（Alternative B不採用の判断）: `bind_featured_media()`が
    `ArticleData`全体を受け取るのは戻り値もArticleDataでなければならない
    ためであり、戻り値がstrである関数はこの事情に該当しない。narrow
    input（個別引数）を採用する。
  - AR-Minor-1: `title`・`mime_type`いずれも`isinstance(value, str)`で
    型検証し、`str` subclassを受理する（strはimmutableのためsubclass化
    の脅威が構造的に存在しないことを根拠とする）。
- `tests/test_e2e_v6_16_0_generated_image_filename_policy_foundation.py`
  — pytestを使わないflat script形式・`check()`系helper・AST静的解析
  （`get_import_details`／`get_call_lines`等）によるDependency Guardの
  precedentを確認した。

---

## 6. Alternatives

### Alternative A: `ArticleData`を直接受け取る

不採用。本Foundationの戻り値は`str`であり、`bind_featured_media()`の
ような「全体を受け取り全体を返す」変換責務に該当しない（5章の確立済み
判断パターンを適用）。`ArticleData`は11 fieldを持つが、本Foundationが
実際に必要とするのはtitle・excerpt相当の2文字列のみである。

### Alternative B: `title`・`excerpt`を個別引数で受け取る

**採用**。

### Alternative C: immutable builder/policy object

不採用。stateを要さず、既存`PromptBuilder`との概念混同リスクが高い。

### Alternative D（Architecture Amendmentで追加検討）: 完成prompt全体を
hard truncateする

不採用（Architecture Review 1 Finding AR-B-1）。固定suffixが途中切断
される可能性があり、Output Contract「固定指示を常に含む」と矛盾する
ため。

### Alternative E（Architecture Amendmentで追加検討）: excerptを全部
保持できない場合は常に全削除する

不採用（Architecture Review 1 Finding AR-B-2）。可能な限りexcerptを
保持する段階的配分（8章）の方が情報量の損失が小さく、実装の複雑度は
同程度であるため。

---

## 7. Architecture Decision

`construct_article_image_prompt(title: str, excerpt: str) -> str`という
module-level pure functionを、新規独立package
`article_image_prompt_construction`として追加する。`ArticleData`へは
依存しない（6章Alternative A不採用の理由による）。

---

## 8. Package Structure

```text
src/article_image_prompt_construction/
    __init__.py
    article_image_prompt_construction.py
```

---

## 9. Public API

```python
from article_image_prompt_construction import construct_article_image_prompt

def construct_article_image_prompt(title: str, excerpt: str) -> str:
    ...
```

- module-level pure function（Constructorなし、状態なし）
- stateless・deterministic・外部I/Oなし
- provider非依存・WordPress非依存・environment非依存・`ArticleData`非依存
- 戻り値は常に`str`

---

## 10. Input Contract

| 候補field | 使用 | 理由 |
|---|---|---|
| `article.seo_title` → `title`引数 | 使用 | 記事の確定タイトル。`main.py`で`generate_slug()`の入力としても使われている既存の「記事title相当」の自然な候補 |
| `article.excerpt` → `excerpt`引数 | 使用 | `_extract_excerpt()`により既にMarkdown除去済み・最大150字に切り詰め済みの短い要約 |
| `article.article_body` | 不使用 | 重要度Sで2000文字超、自由記述。`excerpt`が既に本文の代表短縮形として存在する |
| `article.meta_description` | 不使用 | `excerpt`と完全同値（v1.4.0時点）。二重依存を避け単一の権威あるfieldのみに依存する |
| `article.item`（NewsItem） | 不使用 | 編集前の外部ニュース原文。`seo_title`/`excerpt`は既に編集済みの公開用コンテンツ |
| `article.featured_image_url`／`slug`／`featured_media_id`／`publish_status`／`x_post`／`importance` | 不使用 | 画像のvisual内容と無関係 |

- `title`: str必須。空・空白のみは不可（正規化後判定）。`str` subclass受理。
- `excerpt`: str必須。空文字列は許容（title-onlyテンプレートへ収束）。
  `str` subclass受理。
- 個別引数のみを受け取り、`ArticleData`その他の複合型は受け取らない。

---

## 11. Plain Text Input Contract（Architecture Review 1 Finding AR-B-4）

- `title`／`excerpt`はplain text（構造化されていない自由文字列）を想定する。
- plain textであることの保証は**呼び出し側の責務**である。本Foundationは
  `ArticleData`型にも特定の生成経路（`_extract_excerpt()`等）にも依存しない
  ため、原理的にこれを検証できない。
- HTML／Markdownのsanitization（タグ除去・エンティティデコード等）は本
  Foundationの責務外（Non-Goal）。
- markupを含む文字列（例: `<script>alert(1)</script>`）が渡された場合でも、
  **意味解析や除去を一切行わず、単なる文字データとして正規化・埋め込み
  する**。本Foundationは文字列操作（`re.sub`、`str`の連結・スライス）のみを
  行い、`eval`・HTMLパーサ・テンプレートエンジンを一切使用しないため、
  埋め込まれた文字列がコードとして実行されることは構造的にない。
- 将来のComposition Root／Runtime Wiringは`ArticleData.seo_title`と
  `ArticleData.excerpt`を渡す想定である（16章 Integration Boundary）。
  ただしPublic API自体は`ArticleData`型にも、その生成経路にも依存しない。

---

## 12. 固定template literals

```python
_MAX_PROMPT_LENGTH = 1000

_PREFIX = "「"
_MID = "」というゲームニュース記事のアイキャッチ画像を生成してください。"
_EXCERPT_LABEL = "記事概要："
_EXCERPT_OPEN = "「"
_EXCERPT_CLOSE = "」。"
_SUFFIX = (
    "画像内に読める文字、透かし、UIやテキストの"
    "オーバーレイを含めないでください。"
)
_TRUNCATION_MARKER = "…"
```

| 定数 | 文字数（code point） |
|---|---|
| `_PREFIX` | 1 |
| `_MID` | 32 |
| `_EXCERPT_LABEL` | 5 |
| `_EXCERPT_OPEN` | 1 |
| `_EXCERPT_CLOSE` | 2 |
| `_SUFFIX` | 39 |
| `_TRUNCATION_MARKER` | 1 |
| `_FIXED_LEN_TITLE_ONLY`（`_PREFIX`+`_MID`+`_SUFFIX`） | 72 |
| `_FIXED_LEN_WITH_EXCERPT`（`_PREFIX`+`_MID`+`_EXCERPT_LABEL`+`_EXCERPT_OPEN`+`_EXCERPT_CLOSE`+`_SUFFIX`） | 80 |

上記の文字数はProduction実装から`.\venv\Scripts\python.exe`で実測し確認
済みである（推測ではない）。

**AR-M-2確定事項（全角／半角句読点）**: 句読点は全角（`「」`、`。`、`：`）
で統一する。日本語文中での表記慣習に合わせるため、全角コロン`：`を採用し
半角`:`は不採用とする。

**AR-M-3確定事項（「ロゴ禁止」表現の再検討）**: 固定suffixに「ロゴ」を
含めない。主目的はAI画像生成が意図せず描画してしまう文字化けテキスト・
透かし・UIオーバーレイの抑制であり、著作権・商標（ゲーム作品ロゴ等）を
抑制する意図ではない。「ロゴ」を明示的に含めると、ゲーム作品・メーカー・
プラットフォームを象徴する正当なvisual要素まで生成AIに抑制させてしまう
可能性があり、これは著作権・商標対策という別の（本Foundationのscope外の）
論点を無自覚に持ち込むことになるため、除外する。

**title-only／title+excerptで異なるtemplateを維持する理由**: excerpt不在
時に不自然な空欄表現（`記事概要：「」。`等）を避けるため。

**title-only template**（title="世界的人気ゲームの新作が発表"の場合の
exact literal）:

```text
「世界的人気ゲームの新作が発表」というゲームニュース記事のアイキャッチ画像を生成してください。画像内に読める文字、透かし、UIやテキストのオーバーレイを含めないでください。
```

**title+excerpt template**（excerpt末尾に句点なしの場合、
excerpt="発売日や対応プラットフォームが明らかになった"のexact literal）:

```text
「世界的人気ゲームの新作が発表」というゲームニュース記事のアイキャッチ画像を生成してください。記事概要：「発売日や対応プラットフォームが明らかになった」。画像内に読める文字、透かし、UIやテキストのオーバーレイを含めないでください。
```

---

## 13. 句点重複の扱い（Architecture Review 2 Suggestion AR2-S-3で固定確認）

excerpt末尾が既に句点（`。`）で終わる場合でも、本Foundationは条件分岐で
これを検出・除去しない。`_EXCERPT_CLOSE = "」。"`は常に無条件で付与される
のみであり、excerpt自体の内容を判定・加工しない。

excerpt="発売日や対応プラットフォームが明らかになった。"（末尾に句点あり）
の場合のexact literal:

```text
「世界的人気ゲームの新作が発表」というゲームニュース記事のアイキャッチ画像を生成してください。記事概要：「発売日や対応プラットフォームが明らかになった。」。画像内に読める文字、透かし、UIやテキストのオーバーレイを含めないでください。
```

`。」。`のように句点が連続する見た目になることを**既知の許容事項として
固定する**。意味的な破綻はなく、画像生成promptとしての可読性に実質的な
影響はないと判断し、条件分岐による複雑化を避けた設計判断である。
**Production Implementationにおいて、この重複を回避する独自ロジックを
追加してはならない。**

---

## 14. Output Contract

- 出力言語: 日本語固定（`title`/`excerpt`自体が日本語であるため。翻訳
  責務はscope外）。
- 最大長: 1000文字（15章根拠）。
- 出力が空文字になる可能性: なし（titleが必須かつblankを拒否するため
  保証される）。
- 先頭・末尾空白: 全returnパスに`.strip()`を適用し保証（内部fieldは
  正規化済みで前後空白を持たないため、安全網として機能）。
- 改行形式: 常に単一行（正規化段階で`\n`等は半角spaceへ置換済み。固定
  literal定数はいずれも改行を含まない）。
- 固定suffix（`_SUFFIX`）は常に完全な形で含まれる（15章Truncation
  Contractにより構造的に保証、Architecture Review 1 Finding AR-B-1解消）。
- 同一入力から同一出力を保証する（決定論的、乱数・日時・UUID・環境変数・
  localeを一切参照しない）。

---

## 15. Truncation Contract（Architecture Review 1 Finding AR-B-1／AR-B-2解消）

完成済みprompt文字列全体へのhard truncateは行わない。固定部分
（prefix／mid／excerpt label／excerpt括弧／suffix）は常に完全に保持し、
可変部分であるtitle／excerptのみをbudget内へ収める。

```python
_FIXED_LEN_TITLE_ONLY = (
    len(_PREFIX)
    + len(_MID)
    + len(_SUFFIX)
)  # = 72

_FIXED_LEN_WITH_EXCERPT = (
    len(_PREFIX)
    + len(_MID)
    + len(_EXCERPT_LABEL)
    + len(_EXCERPT_OPEN)
    + len(_EXCERPT_CLOSE)
    + len(_SUFFIX)
)  # = 80


def _fit(text: str, budget: int) -> str:
    """textをbudget code point以内へ収める。収まる場合はそのまま返す。
    収まらない場合は末尾を切り詰め、_TRUNCATION_MARKER（1 code point）を
    budgetへ含めて付与する。budget <= 0の場合は空文字を返す。"""
    if budget <= 0:
        return ""
    if len(text) <= budget:
        return text
    if budget == 1:
        return _TRUNCATION_MARKER
    return text[: budget - len(_TRUNCATION_MARKER)] + _TRUNCATION_MARKER


def _assemble_title_only(normalized_title: str) -> str:
    title_budget = _MAX_PROMPT_LENGTH - _FIXED_LEN_TITLE_ONLY  # = 928
    fitted_title = _fit(normalized_title, title_budget)
    return (_PREFIX + fitted_title + _MID + _SUFFIX).strip()
```

**main functionの処理順序**:
1. title／excerptをValidation・Normalization（17章）
2. excerptが正規化後も空ならtitle-only（`_assemble_title_only`）
3. excerptありの場合、with-excerpt固定長（80）を除いた可変budget
   （= 920）を算出
4. titleを可変budget内へ優先してfit（`_fit(normalized_title, 920)`）
5. 残りbudget（`920 - len(fitted_title)`）へexcerptをfit
6. excerptが1文字も入らない場合（`remaining <= 0`または`_fit`結果が
   空文字）のみ、`_assemble_title_only(normalized_title)`で
   **title-only budget（928）を用いて改めてtitleをfitし直す**
   （with-excerpt側で切り詰めたtitleを使い回さない。より大きなbudgetの
   中で再度fitすることで、不要な過剰truncationを避ける）
7. excerptが入る場合はexcerpt付きtemplateを構築
8. `_SUFFIX`は全return pathで`_fit()`の対象に一切含まれず、無条件かつ
   完全な形で連結される
9. 完成prompt全体へのスライス（hard truncate）は一切行わない

**配分の優先順位**: titleを優先確保し、残りをexcerptへ割り当てる。
理由: titleは必須field（空白不可）であり記事の中心情報、excerptは任意の
補足情報という10章での位置づけと整合する。個別の最低保証文字数
（title最低保証／excerpt最低保証）は設けない。「fixed部分を除いた残り
全budget」を上限としてtitleをそのまま使うため、実質的に非常に大きな
実効最低保証が自然に成立し、個別定数を追加するとalgorithmが複雑化する
ため採用しない。

**truncation marker**: `…`（U+2026、1 code point）。切り詰められた
ことを示す。marker自体もbudget消費対象とし、`len(output) <= 1000`を
例外なく保証する。

**測定単位**: Python `str`の`len()`／スライスによるcode point単位。
grapheme cluster単位ではない（結合文字・絵文字ZWJ列を分断する可能性が
あることは19章Risksに明記する）。

**具体的literal例（境界値、Production実装から実測・確認済み）**:

例1（excerpt truncation）: `title="テスト"`, `excerpt="あ" * 2000`
```text
fitted_title = "テスト"（3文字、truncationなし）
remaining = 920 - 3 = 917
fitted_excerpt = "あ"*916 + "…"（917文字）
len(output) = 1+3+32+5+1+917+2+39 = 1000（ちょうど上限）
```

例2（title-only truncation）: `title="あ" * 2000`, `excerpt=""`
```text
fitted_title = "あ"*927 + "…"（928文字）
len(output) = 1+928+32+39 = 1000（ちょうど上限）
```

例3（title極端に長い場合のfallback、with-excerpt budgetでexcerptが
1文字も入らない）: `title="い" * 2000`, `excerpt="のテスト"`
```text
with-excerpt budget（920）内でtitleが920文字使い切り、excerpt用残り
budgetが0以下になるため、excerptは1文字も入らない
→ title-only templateへfallbackし、title-only budget（928）で
  titleを再fit
fitted_title = "い"*927 + "…"（928文字、920ではなく928で再fitされて
  いることを確認）
len(output) = 1+928+32+39 = 1000（ちょうど上限）
```

---

## 16. Integration Boundary

将来のRuntime Wiring／Composition Rootが
`prompt = construct_article_image_prompt(article.seo_title, article.excerpt)`
を呼び出し、`ArticleFeaturedMediaOrchestrator.apply(article, prompt,
filename)`の`prompt`引数として供給することを想定する。Composition
Root・Runtime Wiring自体は本Foundationでは設計・実装しない。

---

## 17. Validation Contract

**Validation Order**（6ステップで確定）:
1. title型検証（`isinstance(title, str)`）
2. title正規化（`_normalize`）
3. 正規化後titleのblank判定
4. excerpt型検証（`isinstance(excerpt, str)`）
5. excerpt正規化（`_normalize`）
6. prompt構築（15章のTruncation Contractを含む）

titleの型・空白検証が両方完了してからexcerptの型検証に進む
（`article_featured_media_orchestrator.py`の`article→prompt→filename`
逐次検証パターンを踏襲）。

- accepted types: `str`のみ。`isinstance()`採用によりstr subclassは
  受理する（5章・v6.16.0 AR-Minor-1 precedent踏襲）。
- excerptは空文字を許容する（blank-check自体を行わない）。空白のみの
  excerptは正規化後に空文字となり、title-only templateへ暗黙に収束する
  （エラーにはしない、graceful degradation）。
- 非常に長いtitle／excerptは例外を発生させない（15章truncation contract
  で吸収する）。

---

## 18. Error Contract

| # | 検証対象 | 条件 | 例外 | メッセージ（固定literal） |
|---|---|---|---|---|
| 1 | title | `isinstance(title, str)`不成立 | `ValueError` | `"title must be a str"` |
| 2 | title(正規化後) | 正規化後が空文字 | `ValueError` | `"title must not be blank"` |
| 3 | excerpt | `isinstance(excerpt, str)`不成立 | `ValueError` | `"excerpt must be a str"` |

例外messageにtitle/excerptの実値を一切含めない（入力値がmessageへ混入
しないことをSecurity Contractとして保証する、20章）。

---

## 19. Normalization Contract

```python
import re

_CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")
_WHITESPACE_PATTERN = re.compile(r"\s+")


def _normalize(value: str) -> str:
    cleaned = _CONTROL_CHAR_PATTERN.sub(" ", value)
    cleaned = _WHITESPACE_PATTERN.sub(" ", cleaned)
    return cleaned.strip()
```

**保証範囲**（Architecture Review 1 Finding AR-B-3で正確化済み）:

| カテゴリ | 対象 | 扱い | 保証 |
|---|---|---|---|
| 制御文字（ASCII C0 + DEL） | `\x00-\x08`, `\x0B`, `\x0C`, `\x0E-\x1F`, `\x7F` | 半角space 1個へ置換 | **保証する** |
| `\t` `\n` `\r` | ASCII水平タブ・改行・復帰 | `\s+`により半角space 1個へ収束 | **保証する** |
| Python正規表現`\s+`に一致する空白 | ASCII空白＋Unicode空白（全角スペースU+3000等を含む） | 連続する空白を半角space 1個へ収束 | **保証する**（Production実装から実測確認済み） |
| Zero-width space（U+200B等） | ゼロ幅スペース | 対象外 | **保証しない**（実測確認済み、除去されずそのまま出力に残存する） |
| Unicode format characters（Cf category: ZWNJ／ZWJ／soft hyphen等） | - | 対象外 | **保証しない** |
| Bidi control characters（U+200E, U+200F, U+202A-202E, U+2066-2069等） | - | 対象外 | **保証しない** |
| その他の不可視Unicode文字（結合文字・variation selector等） | - | 対象外 | **保証しない** |

`unicodedata`モジュールは使用しない（21章Dependency Contract）。したがって
上記「保証しない」区分に該当する文字は、入力に含まれていた場合、正規化
されずそのまま出力へ埋め込まれる可能性がある。

「制御文字」「空白文字」「不可視Unicode文字」は異なるカテゴリであり、
混同しない。制御文字と空白文字は正規表現で機械的に検出・置換できる
有限集合。不可視Unicode文字はUnicode文字プロパティに基づく分類であり、
`unicodedata`なしでは網羅的検出が原理的に不可能なため、保証範囲外と
明記する。

---

## 20. Security Contract

- state非保持: pure functionであり、module levelのmutable stateを
  一切持たないため構造的に満たされる。
- print／logging禁止: 一切実装しない（既存`PromptBuilder`が不正
  バージョン時に`print()`する点との明確な差別化）。
- 例外messageへの入力内容非包含: 18章の3つの固定メッセージはいずれも
  title／excerptの実値を一切埋め込まない固定literal。
- HTML内情報の特別除去: Non-Goal（11章 Plain Text Input Contract）。
- prompt injection semantic対策: 明確にscope外。本Foundationは画像生成
  API向けのテキストpromptを構築するのみであり、悪意ある文字列パターン
  の意味的検出・除去は行わない。実施するのは19章の機械的な制御文字
  除去・長さ上限のみであり、真のprompt injection対策としては不十分で
  あることを19章Risksに明記する。
- 制御文字・不可視文字: 19章のとおり。

---

## 21. Dependency Contract

| 候補 | 可否 | 理由 |
|---|---|---|
| `re` | **許可** | 空白・制御文字の正規化に必要な唯一の標準ライブラリ依存 |
| `html` | 禁止 | HTMLエンティティのデコード等が必要なfieldを扱わない |
| `hashlib` | 禁止 | titleは必須・非空を検証済みであり、hash fallback機構は不要 |
| `dataclasses` | 禁止 | 戻り値は`str`であり、値オブジェクトを返す設計ではない |
| `typing`（明示import） | 禁止 | 組み込み型注釈（`str`, `-> str`）のみで十分 |
| `unicodedata` | 禁止 | 19章のとおり、不可視Unicode文字の網羅的検出を行わない設計判断のため |
| `pathlib` | 禁止 | ファイルI/Oを行わない |
| `subprocess` | 禁止 | 外部プロセスを起動しない |
| `importlib`／動的import | 禁止 | 静的import以外を使用しない |

**禁止依存**（Consumer-less Foundation、明記）:
```text
article_image_prompt_construction → outputs（ArticleDataを含む）
article_image_prompt_construction → ai_image_generation
article_image_prompt_construction → openai_image_generation
article_image_prompt_construction → generated_image_wordpress_media
article_image_prompt_construction → article_featured_media
article_image_prompt_construction → article_featured_media_orchestration
article_image_prompt_construction → image_generation_config
article_image_prompt_construction → generated_image_filename_policy
article_image_prompt_construction → wordpress_media
article_image_prompt_construction → ai（ai.prompt_builder を含む）
article_image_prompt_construction → os / logging / hashlib / subprocess /
    importlib（動的import） / unicodedata / pathlib /
    ネットワーク・ファイルI/O一切 / 環境変数参照
image_resolver.py / main.py / 記事生成Pipeline / Workflow / Scheduler /
    Retry Runtime / Composition Root / scripts配下全体 → 依存されない
    （Consumer-less、既存コードから一切参照されない）
```

module-level mutable stateは作らない（`global`／`nonlocal`は使用せず、
module-level定数はいずれも1回のみ代入される）。

---

## 22. Runtime Zero Diff

```text
無改修（変更ゼロ）を維持する既存コード:
main.py
src/image_resolver.py
src/article_featured_media_orchestration/article_featured_media_orchestrator.py
src/article_featured_media/article_featured_media_binder.py
src/ai_image_generation/*
src/openai_image_generation/*
src/generated_image_wordpress_media/*
src/generated_image_filename_policy/*
src/image_generation_config/*
src/wordpress_media/*
src/ai/prompt_builder.py
src/outputs/*
src/pipeline/*
src/ai/ai_publish_service.py
docs/ROADMAP.md / docs/architecture.md / docs/CHANGELOG.md
```

本Foundationは新規独立package（`src/article_image_prompt_construction/`）
を追加するのみで、上記いずれのファイルからもimportされず
（Consumer-less）、上記いずれのファイルへも変更を加えない。外部API
呼び出し・環境変数読み取り・ファイルI/O・ネットワークI/Oは一切発生しない。

**Runtime Zero Diff Verification方針**（Architecture Review 1 Finding
AR-M-4で確定）: Runtime Zero Diffは自動E2Eテスト内でGit状態や`git diff`
へ依存する形では検証しない。新規E2Eでは、`main.py`／`image_resolver.py`
の**現在のソーステキスト**が新規package名を参照していないことを静的
テキスト検索で確認する（v6.16.0 `RUNTIME-1`と同型の手法）。実際に
既存ファイルへ差分が生じていないこと（`git diff`）自体は、Code
Review／Release Review工程内の手続きとして別途確認する（23章）。

---

## 23. Test Strategy

新規E2E: `tests/test_e2e_v6_17_0_article_image_prompt_construction_foundation.py`

pytestを使わないflat script形式・`check()`系helper・AST静的解析による
Dependency Guardという、v6.9.0〜v6.16.0のprecedentを踏襲する。

### 23.1 E2E／contract testで検証するもの

Public import・`__all__`・signature、正常系exact literal（title-only／
title+excerpt／excerpt末尾句点あり無し／句点重複許容）、Normalization
（制御文字／`\n`／`\r`／`\t`／連続空白／全角空白／前後空白／zero-width
spaceが保証対象外であることの確認／HTML・Markdown非解析の確認）、
Validation／Error（型不正／空title／whitespace-only title／空excerpt／
whitespace-only excerpt／Validation Order／exact `ValueError`／exact
message／入力値の非混入）、Truncation（excerpt部分truncation／title
部分truncation／title-onlyへのfallbackとbudget再fit／marker付与／
marker のbudget算入／出力ちょうど1000文字／出力が1000文字を超えない／
固定suffix完全保持）、Invariants（非空／strip済み／改行・CR・tabなし／
deterministic／max length）、AST Guard（importが`re`のみ／既存package
非依存／print・logging禁止／eval・exec禁止／module-level mutable state
なし／Reverse Dependency Guard／Runtime Zero Diff静的確認）。

### 23.2 Review／Git工程で確認するもの（自動E2Eには含めない）

`main.py`／`image_resolver.py`／`ArticleFeaturedMediaOrchestrator`／
既存Runtime moduleが無変更であること（`git diff`確認）、変更ファイル
一覧の確認（新規追加ファイルのみであること）、Working Tree状態の確認。

**Test期待値の作成方針（Architecture Review 2 Suggestion AR2-S-1）**:
Testでは、Production moduleのprivate定数（`_SUFFIX`等）やprivate
helper（`_fit`／`_normalize`等）をimport・呼び出しして期待値を動的
生成しない。本設計書で確定した固定template literal・固定エラー
メッセージ・固定truncation境界値を、Test側で独立したliteralとして
直接記載する。

---

## 24. Formal Regression Strategy（実績反映済み）

**方針**: v6.16.0完了時点の累積Regression Inventory（19ファイル、
`v1.11.0・v5.9.0・v6.0.0〜v6.16.0`、2508/2508 PASS）をbaselineとして
継続する「累積Regression Inventory方式」を踏襲し、新規E2E
（`test_e2e_v6_17_0_*.py`）を1ファイル追加した20ファイルを正式Inventoryと
する。`tests/`配下の全E2E（68件以上）を無差別実行するのではなく、正式
Inventoryの20ファイルのみを`.\venv\Scripts\python.exe`で1ファイルずつ
個別実行する（一括`pytest`実行はしない）。

**実績（2026-07-21実施）**:

```text
正式Inventory：20ファイル
実行順序：v1.11.0 → v5.9.0 → v6.0.0 → v6.1.0 → v6.2.0 → v6.3.0 → v6.4.0 →
    v6.5.0 → v6.6.0 → v6.7.0 → v6.8.0 → v6.9.0 → v6.10.0 → v6.11.0 →
    v6.12.0 → v6.13.0 → v6.14.0 → v6.15.0 → v6.16.0 → v6.17.0

既存19ファイル（v1.11.0〜v6.16.0）：2508/2508 PASS
  （Release 6.16完了時点baseline 2508/2508と完全一致、drift・回帰なし）
Release 6.17新規E2E：136/136 PASS
総合：2644/2644 PASS（事前期待値2508+136=2644と完全一致）

FAIL：0
Warning：0（DeprecationWarning等のPython warning classパターンで全20
    ファイルのログを機械確認し0件）
Traceback出力：0件
終了コード非0：0ファイル
外部API実接続：0件（`OPENAI_API_KEY`等いずれも未設定のまま全20ファイルが
    正常終了）
`.\venv\Scripts\python.exe -m pip check`：成功（No broken requirements found）
```

**Environment残留**: Git追跡対象の残留なし（`git status --porcelain
--untracked-files=all`をFormal Regression実行前後で比較し完全一致を確認）。
Formal Regression中、`.gitignore`対象の既存runtime log
`.run/retry_runtime_log.jsonl`は正式E2E（retry_runtime系）の想定内動作
として更新されたが、これはRelease 6.17以前から存在する既知の挙動であり、
Release 6.17固有の残留・Git状態変化ではない。

**Scenario／Case集計について**: Scenario／CaseのCase ID表記規約は
v1.11.0〜v6.8.0（旧`=== Scenario N ===`形式・colon区切りcase表記）と
v6.9.0〜v6.17.0（`[XXX] header`＋`XXX-Na.`形式）とで過去に複数回進化して
おり、全20ファイルで統一的に再集計できる共通の機械的定義が存在しない。
したがって、Formal Regression全体の総Scenario／総Caseは算出しない。
全Inventory共通で信頼できる正式な回帰判定軸はAssertion／PASS数である
（Release 6.17新規E2E単体のScenario/Case（43／111）は17章・32章に記録
済み）。

**判定**: Completed（正式Inventory20ファイル全実行・全終了コード0・全
Assertion PASS・FAIL 0・Warning 0・対象外ファイル混入なし・既存E2E
無改修）。

---

## 25. Documentation Integration Plan（Completed）

```text
docs/ROADMAP.md      → v6.17.0 Entry追加（本Foundationの実装記録。Release
                        Reviewが未実施であることを明記し、v6.16.0以前の
                        「Release Review Approved・Release Completed」表現
                        とは区別） → 反映済み
docs/architecture.md → 新規節「Article Image Prompt Construction
                        Foundation層」追加（Purpose／Package Boundary／
                        Public API／Validation・Normalization Contract／
                        Template／Truncation Contract／Dependency
                        Direction／Security／State Contract／Integration
                        Boundary／Test・Review・Regression実績／Out of
                        Scope・Future Extension） → 反映済み
docs/CHANGELOG.md    → `## [v6.17.0]`Entry追加（Added／Public API／
                        Contract概要／Tested／Review状態。Release Review
                        は未実施のためApprovedと記載しない） → 反映済み
本設計書              → Status／Formal Regression実績（24章）／
                        Documentation Integration Plan（本章）／Review
                        History（32章）を本工程で更新 → 反映済み
```

Historical Record（v1.11.0〜v6.16.0の既存Entry）はいずれも変更していない。

**Documentation Integration Finalize（Release Review Approved反映、追加実施）**:
Release Review Approved with Suggestions判定を受け、上記3文書のv6.17.0
Entryにおける「Release Reviewは未実施」「Release：Not Completed」という
一時表現を、「Release Review Approved with Suggestions」「Release：
Completed」へ更新した（Historical Record・数値・Public API・Contractは
無変更）。本設計書もStatus・29.1章・30章・本章・32章を同時に最終化した。

---

## 26. Risks

- excerptが既に句点で終わる場合、`「...。」。`のように句点が連続する
  見た目になる（13章）。意味的破綻はないが、条件分岐で回避する複雑化を
  避けるため許容する設計判断とした。
- `_fit()`のcode point単位切り詰めは、結合文字・絵文字ZWJ列（複数code
  point合成）を分断する可能性がある。実際のtitle/excerptにこうした
  複雑な絵文字が含まれる頻度は低いと考えられるが、保証はしない。
- Zero-width space等の不可視Unicode文字は正規化されず出力に残存しうる
  （19章）。これらが後段のOpenAI Adapterでどう扱われるかは本Foundation
  の検証範囲外。
- 固定template文言が実際の画像生成品質にどう影響するかは、実際のAPI
  呼び出しを行わない本Foundationでは検証できない。
- prompt injection的な悪意ある入力への防御は機械的な範囲（制御文字除去・
  長さ上限）に留まる。

## 27. Open Questions

| ID | 内容 | Blocking/Non-Blocking |
|---|---|---|
| OQ-1 | excerpt末尾句点の重複表示（`。」。`）を、将来的に条件分岐で解消すべきか | Non-Blocking（Architecture Review 2で意図的許容事項として確認済み、13章） |
| OQ-2 | 絵文字ZWJ列の分断リスクへの対応要否 | Non-Blocking。実運用データでの発生頻度を見てから判断可能 |
| OQ-3 | 将来Runtime Wiring Foundationでの実際の呼び出し方（Composition Root設計） | Non-Blocking（scope外、16章） |

Blocking Open Questionはない。

## 28. Deferred Items（Future Candidates）

- Publish Composition Root Foundation
- Article Featured Media Runtime Wiring
- Image Generation Fallback Policy
- Media Upload Retry／Idempotency Foundation
- WordPress Unused Media Cleanup Foundation
- 詳細なvisual style／art direction拡張（本Foundationのtemplateを拡張
  する形）

---

## 29. Architecture Review Findings

| ID | 指摘内容 | 区分 |
|---|---|---|
| AR-B-1 | 完成promptのhard truncateにより固定suffixが途中切断されうる | Blocking |
| AR-B-2 | excerpt全削除方式が過度に保守的（可能な限りexcerptを保持すべき） | Blocking |
| AR-B-3 | Security Contractが「不可視文字をすべて除去」と過大表現している | Blocking |
| AR-B-4 | plain text入力責務（呼び出し側責務）が明記されていない | Blocking |
| AR-M-1 | `MAX_PROMPT_LENGTH=1000`の根拠整理（provider上限への依存を減らす） | Non-Blocking |
| AR-M-2 | 固定template文面（全角/半角・句読点重複）の確定 | Non-Blocking |
| AR-M-3 | 「ロゴ禁止」表現の再検討 | Non-Blocking |
| AR-M-4 | Runtime Zero Diff TestがGit状態に依存している | Non-Blocking |
| AR2-S-1 | Test期待値でProduction private定数を使用しない | Suggestion |
| AR2-S-2 | 正式設計書を完全統合されたself-contained文書にする | Suggestion |
| AR2-S-3 | excerpt末尾句点重複を意図的な許容事項として固定する | Suggestion |

**Code Review Findings**（Code Review：Approved with Suggestions、Blocking 0・Major 0・Minor 3・Suggestion 3）:

| ID | 指摘内容 | 区分 |
|---|---|---|
| CR-1 | Background付近が「Release 6.17 Repository Survey」という、docs/配下に永続化されていない外部参照を引用しており、self-containedness（AR2-S-2）にわずかな欠落がある | Minor |
| CR-2 | `_fit()`の`budget == 1`専用分岐が、一般式でも同一出力を生成するため意味的に冗長（動作影響なし） | Minor |
| CR-3 | 新規E2Eに、title／excerptへ`\r`を実際の入力として渡し正規化を確認するCaseが存在しない（設計書は`\r`を保証範囲として明記） | Minor |
| CR-4 | AST Guardの`get_call_lines`がalias経由の間接呼び出し（例：`from builtins import print as p; p(...)`）を検出できない（現Productionには該当コードなし） | Suggestion |
| CR-5 | Test側のtruncation期待値（916／927等の数値）が、Productionと同じbudget算術的前提を手動で共有している（Production呼び出しはなくAR2-S-1準拠） | Suggestion |
| CR-6 | `STATE-AST-2`が同一名の再代入検査のみで、将来module-levelへ可変コンテナが追加された場合のin-place変更までは検出できない（現Productionには可変コンテナなし） | Suggestion |

## 29.1 Release Review Findings

Release Review：**Approved with Suggestions**（Blocking 0・Major 0・Minor 1・Suggestion 2）。Release ReviewはPublic API・固定literal・Validation/Error/Normalization/Truncation/Dependency/Security Contract・Runtime Zero Diff・新規E2E独立再実行・Formal Regression実績・文書間整合・Historical Record論点をProduction Code／文書の直接精査で検証した。

| ID | Severity | 対象 | 確認済み事実 | 影響 | Resolution | Blocking |
|---|---|---|---|---|---|---|
| RR-M-1 | Minor | `docs/ROADMAP.md` v6.17.0 Entry | Release Review Approved前の時点で、`[x]`チェックボックスと「Release Reviewは未実施であり、本Entry時点でRelease 6.17は未完了である」という一時表現が併存していた（`[x]`＝実装完了はv6.10.0〜v6.13.0 precedentと整合するが、直近3世代v6.14.0〜v6.16.0は`[x]`とRelease Completedを対にしている） | 一時状態としては誤導性なし。Release Review Approved後に放置すると直近precedentとの表記不一致が残存する | **Resolved**（本Documentation Integration Finalizeにより、ROADMAPの当該Entryを「Release Review Approved with Suggestions、Release Completed」形式へ更新した） | No |
| RR-S-A | Suggestion | `docs/architecture.md` v6.16.0節 Future Extension | v6.16.0 precedent（v6.15.0節への同種更新）は実装済みポインタを括弧外の独立文＋節内相互参照「（本節末尾の◯◯層を参照）」で記載していたが、v6.17.0 Documentation Integrationでの当該更新は括弧内・相互参照なしで記載した | 意味は同等。読者の節間移動がわずかに不便な程度 | **Accepted / No Change Required**（意味が正確で文書構造に問題がないため、書式変更は今回のcommit前必須修正としない） | No |
| RR-S-B | Suggestion | Release Review時のprecedent確認方法 | Release Reviewの初期指示で言及された「Release 6.16のRR-S-1判断」はRepository内に存在しない（全文検索で得られる`RR-S-1`はすべて`CRR-S-1`の部分一致）。実際のprecedentはv6.16.0 commit `f0c1d07`の実差分、および同commitの正式設計書Release Review記録（Historical Record非改変の定義：完了済みReleaseのPASS件数・Review判定・Known Issueの不改変であり、Future Extension前方参照リストの更新は含まれない）から確認された | 本Releaseの成果物には影響なし。将来のRelease Reviewでprecedent誤解が再生産されうる | **Informational**（今後のRelease ReviewではFinding IDの記憶ではなく、Repository実差分と正式Review記録を根拠とすることを推奨する） | No |

## 30. Finding Resolution Matrix

| ID | 指摘内容 | 修正内容 | Contract反映箇所 | 区分 | Resolution Status |
|---|---|---|---|---|---|
| AR-B-1 | 完成promptのhard truncateにより固定suffixが途中切断されうる | 固定部分を`_fit()`の対象から除外し、可変部分のみ個別に切り詰める方式へ変更 | 15章 Truncation Contract | Blocking | **Resolved** |
| AR-B-2 | excerpt全削除方式が過度に保守的 | title優先確保→excerpt文字単位truncation→1文字も入らない場合のみtitle-only収束、という段階的配分へ変更 | 15章 | Blocking | **Resolved** |
| AR-B-3 | 「不可視文字を全除去」という過大表現 | 制御文字/空白文字/不可視Unicode文字を区別し、`unicodedata`非使用による保証対象外範囲を明記 | 19章 Normalization Contract | Blocking | **Resolved** |
| AR-B-4 | plain text入力責務が未記載 | Plain Text Input Contractを新設し、呼び出し側責務・markup非解釈を明記 | 11章 | Blocking | **Resolved** |
| AR-M-1 | MAX_PROMPT_LENGTH根拠がprovider上限に依存しすぎ | 主根拠をFoundation自身のscope限定・予測可能性・Test容易性へ再整理、provider上限は副次的整合性として降格 | 14章 Output Contract | Non-Blocking | **Resolved** |
| AR-M-2 | 固定template文面（全角/半角・句読点重複）が未確定 | 全角句読点で統一、excerpt末尾句点は無条件付与（条件分岐なし）で確定 | 12章 | Non-Blocking | **Resolved** |
| AR-M-3 | 「ロゴ禁止」が著作権/商標論点を持ち込む懸念 | 「ロゴ」を除いた文面を採用、目的を意図しない文字描画抑制に限定 | 12章 | Non-Blocking | **Resolved** |
| AR-M-4 | Runtime Zero Diff TestがGit状態に依存 | Test StrategyをE2E/contract test対象とReview/Git工程対象に分離 | 22章・23章 | Non-Blocking | **Resolved** |
| AR2-S-1 | Test期待値でProduction private定数を使用しない | 新規E2Eでは、Production moduleのprivate定数・helperをimport・呼び出しせず、独立したTest側literalで期待値を構成 | 23章・新規E2E実装 | Suggestion | **Resolved** |
| AR2-S-2 | 正式設計書をself-contained文書にする | 本文書自体をArchitecture Design・Amendment・Review 2の完全統合版として作成 | 本文書全体 | Suggestion | **Resolved** |
| AR2-S-3 | excerpt末尾句点重複を意図的な許容事項として固定する | 13章として明文化し、Production側で独自に重複回避しないことを明記 | 13章 | Suggestion | **Resolved** |
| CR-1 | Background付近の外部Survey参照によりself-containednessが不足 | 外部参照表現を削除し、`article_featured_media_orchestrator.py:58-74`等のRepository内直接事実へ置き換え | 1章 Background | Minor | **Resolved** |
| CR-2 | `_fit()`の`budget == 1`分岐が冗長 | 今回は対応しない（Production Code変更はCode Review後の別工程判断とする） | 15章 | Minor | **Accepted / No Change Required** |
| CR-3 | `\r`を実入力とするNormalization Caseの欠落 | 新規E2EへScenario WS-4（`\r`を実入力とするexact literal Case）を追加 | 32章 Review History・新規E2E（WS-4） | Minor | **Resolved** |
| CR-4 | AST Guardのalias経由呼び出し検出漏れ | 今回は対応しない | 新規E2E（AST Guard） | Suggestion | **Deferred** |
| CR-5 | Test truncation期待値の算術的前提共有 | 今回は対応しない（情報開示のみで十分と判断） | 新規E2E（TRUNC-1〜3） | Suggestion | **Informational** |
| CR-6 | `STATE-AST-2`の可変コンテナ検出範囲 | 今回は対応しない | 新規E2E（STATE-AST-2） | Suggestion | **Deferred** |
| RR-M-1 | ROADMAP v6.17.0 Entryの`[x]`とRelease未実施表現の一時併存 | ROADMAPをRelease Review Approved with Suggestions／Release Completed表現へ更新 | `docs/ROADMAP.md` v6.17.0 Entry | Minor | **Resolved** |
| RR-S-A | architecture.md実装済みポインタの記載形式が過去precedentとわずかに異なる | Historical Record（v6.16.0節Future Extension更新）を維持し、書式変更は行わない | `docs/architecture.md` v6.16.0節 | Suggestion | **Accepted / No Change Required** |
| RR-S-B | Release Review時のprecedent確認方法（Finding ID記憶の限界） | 将来のReviewではRepository実差分と正式Review記録を根拠とすることを推奨として記録 | 本章・29.1章 | Suggestion | **Informational** |

**Blocking Findingはすべて Resolved である。Code Review Minor Finding（CR-1・CR-3）・Release Review Minor Finding（RR-M-1）もResolvedである。**

---

## 31. Architecture Review Checklist

```text
[x] 固定suffixが途中切断されないことがTruncation Contractで構造的に
    保証されている（AR-B-1、15章）
[x] excerpt保持を優先する段階的配分がRepository上の既存precedentと
    整合している（AR-B-2、15章）
[x] Security Contractが「保証する範囲」と「保証しない範囲」を区別して
    記載している（AR-B-3、19章）
[x] Plain Text Input Contractにより呼び出し側責務が明記されている
    （AR-B-4、11章）
[x] MAX_PROMPT_LENGTH根拠がprovider上限に過度に依存していない
    （AR-M-1、14章）
[x] 固定template literalがTestへそのまま記載可能な形で確定している
    （AR-M-2、12章）
[x] 固定suffixが著作権/商標論点を持ち込んでいない（AR-M-3、12章）
[x] Test StrategyがGit状態に依存するE2Eを含まない（AR-M-4、22-23章）
[x] Public API・Dependency Contract・ArticleData非依存の判断が一貫して
    維持されている（7章・21章）
[x] Testが Production private定数／helperに依存していない（AR2-S-1）
[x] 正式設計書がself-containedである（AR2-S-2、本文書自体）
[x] excerpt末尾句点重複が明文化された許容事項である（AR2-S-3、13章）
```

## 32. Review History

```text
Architecture Design: Completed
  - Public API・package名・ArticleData非依存の判断を確定。

Architecture Review 1: Changes Required
  - Blocking: AR-B-1, AR-B-2, AR-B-3, AR-B-4（4件）
  - Non-Blocking: AR-M-1, AR-M-2, AR-M-3, AR-M-4（4件）

Architecture Amendment: Completed
  - AR-B-1〜4: Resolved（Truncation Contract再設計・Security Contract
    正確化・Plain Text Input Contract新設により解消）
  - AR-M-1〜4: Resolved（根拠整理・template確定・suffix文言確定・
    Test Strategy区分整理により解消）
  - Blocking Finding残数: 0

Architecture Review 2: Approved with Suggestions
  - Blocking: 0
  - Suggestion: AR2-S-1, AR2-S-2, AR2-S-3（3件）

Production Implementation: Completed
  - AR2-S-1〜3を反映して実施。src/article_image_prompt_construction/
    を新規作成。既存ファイルは無変更。

New E2E: Completed
  - tests/test_e2e_v6_17_0_article_image_prompt_construction_foundation.py
    を新規作成し、.\venv\Scripts\python.exe で実行。42 Scenario・109 Case・
    134 Assertion、134/134 PASS・0 FAIL・exit code 0を確認。

Code Review: Approved with Suggestions
  - Blocking: 0・Major: 0・Minor: 3（CR-1, CR-2, CR-3）・
    Suggestion: 3（CR-4, CR-5, CR-6）
  - CR-1: Resolved（Background付近の外部Survey参照を、
    article_featured_media_orchestrator.pyの直接事実引用へ置換）
  - CR-3: Resolved（新規E2EへScenario WS-4を追加し、\rを実入力とする
    Normalization Caseを新設）
  - CR-2: Accepted / No Change Required（_fit()のbudget==1分岐、
    動作影響なしのため今回は変更しない）
  - CR-4: Deferred（AST Guardのalias経由呼び出し検出、現Productionには
    該当コードなし）
  - CR-5: Informational（Test truncation期待値の算術的前提共有、
    Production呼び出しはなくAR2-S-1準拠）
  - CR-6: Deferred（STATE-AST-2の可変コンテナ検出範囲、現Productionには
    可変コンテナなし）
  - CR-1・CR-3反映後の新規E2E再実行: 43 Scenario・111 Case・136 Assertion、
    136/136 PASS・0 FAIL・exit code 0を確認。

Formal Regression: Completed
  - 正式Inventory20ファイル（既存19ファイル：v1.11.0・v5.9.0・
    v6.0.0〜v6.16.0＋Release 6.17新規1ファイル）を個別実行。
  - 既存19ファイル：2508/2508 PASS（Release 6.16 baseline完全維持）
  - Release 6.17新規：136/136 PASS
  - 総合：2644/2644 PASS・FAIL 0・Warning 0・Traceback 0・終了コード
    非0なし・外部API実接続0・`pip check`成功
  - `.run/retry_runtime_log.jsonl`（.gitignore対象、既存retry_runtime
    E2Eの想定内動作）以外のGit状態変化なし

Documentation Integration: Completed
  - docs/ROADMAP.md・docs/architecture.md・docs/CHANGELOG.mdへv6.17.0
    Entryを追加。Historical Record（v1.11.0〜v6.16.0の既存Entry）は
    いずれも無変更。
  - 本設計書のStatus・24章 Formal Regression実績・25章 Documentation
    Integration Plan・本章を本工程で更新。

Release Review: Approved with Suggestions
  - Blocking 0・Major 0・Minor 1（RR-M-1）・Suggestion 2（RR-S-A, RR-S-B）
  - Public API・固定literal・Validation/Error/Normalization/Truncation/
    Dependency/Security Contract・Runtime Zero Diffを、Production Code・
    正式設計書の直接精査（AST解析・ソース直読を含む）で独立検証。
  - 新規E2Eを独立再実行し、43 Scenario・111 Case・136 Assertion、
    136/136 PASS・0 FAIL・0 Warning・0 Traceback・exit code 0を再確認。
  - Formal Regression実績（20ファイル・2644/2644 PASS）が
    docs/design・docs/ROADMAP.md・docs/architecture.md・
    docs/CHANGELOG.mdの4文書間で一致することを確認。
  - Historical Record論点：v6.16.0節Future Extensionの実装済みポインタ
    追記は、v6.16.0 commit（f0c1d07）がv6.15.0節へ行った同型の更新を
    precedentとして是認されており、現状維持（案A）を採用。Findingとしない。
  - RR-M-1: Resolved（ROADMAP v6.17.0 Entryを本Documentation Integration
    Finalizeで「Release Review Approved with Suggestions、Release
    Completed」表現へ更新）
  - RR-S-A: Accepted / No Change Required
  - RR-S-B: Informational
  - Release成果物7ファイル全体を承認。

Documentation Integration Finalize（Release Review Approved反映）: Completed
  - 本設計書Status・29.1章 Release Review Findings・30章 Finding
    Resolution Matrix・本章を更新。
  - docs/ROADMAP.md・docs/architecture.md・docs/CHANGELOG.mdのRelease
    Review／Release状態表現を「Approved with Suggestions」／
    「Completed」へ最終化。

Release: Completed
```

---

## 33. Implementation Handoff

新規ファイル:
```text
docs/design/article_image_prompt_construction_foundation.md（本文書）
src/article_image_prompt_construction/__init__.py
src/article_image_prompt_construction/article_image_prompt_construction.py
tests/test_e2e_v6_17_0_article_image_prompt_construction_foundation.py
```

変更ファイル: なし
削除ファイル: なし

`__init__.py`はPublic APIとして`construct_article_image_prompt`のみを
`__all__`でexportする。実装moduleは本文書12章・15章・17-21章の
Contractと完全に一致させる。
