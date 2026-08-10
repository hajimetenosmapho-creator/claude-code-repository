# Image Generation Fallback Observability Foundation（DI-5＋DEF-3）— Architecture Design

> **本設計書は Deferred Item DI-5（`docs/ROADMAP.md`「observability／logging」）および
> DEF-3（`docs/design/article_featured_media_runtime_wiring.md` §19「PROPAGATE 時の
> category 記録・構造化ログ・metrics」）を統合する Architecture Design である。**
> v6.19.0（Image Generation Fallback Policy）が定めた観測契約 O-1〜O-7（同設計書 §18.1）の
> うち、これまで console 出力（CONTINUE 時の1行のみ）に留まっていた fallback 発生・
> category・action・reason を、`ArticleLogEntry`（JSON Lines）へ構造化して記録する
> 基盤を確立する。

---

## 0. Status

| 項目 | 内容 |
|---|---|
| **工程** | Architecture Design（初版）→ Architecture Review 1（Changes Required）→ 最小改訂 → Architecture Review 2（**Approved with Suggestions**）→ Test Review／Implementation前Gate確認（**PASS**）→ Production Implementation → Code Review 1（Changes Required）→ 修正 → Code Review 2（**Approved with Suggestions**）→ Design doc最終整合・Documentation Integration → **Formal Regression（PASS）** → 本改訂（Formal Regression結果反映） |
| **Architecture Review 1** | Changes Required（Major 4／Minor 2／Suggestion 2）。指摘はいずれも最小改訂で反映済み（21章参照） |
| **Architecture Review 2** | **Approved with Suggestions**（Blocking 0／Major 0／Minor 0／Suggestion 2） |
| **Test Review／Implementation前Gate確認** | **PASS**（baseline v6.19〜v6.24、合計1628/1628 PASS実測） |
| **Production Implementation** | Completed（7ファイル。20章File Change Plan参照） |
| **New E2E** | Completed（`tests/test_e2e_v6_25_0_*.py`。既存6ファイルの更新を含む） |
| **限定回帰** | v6.19〜v6.25の関連7ファイルのみを対象に実測、合計**1792/1792 PASS**。**Formal Regression（正式Inventory全ファイル）ではない**（16.6節・21.3節参照。履歴として維持する） |
| **Formal Regression** | **PASS**（正式Inventory**28ファイル**（v1.11.0＋v5.9.0＋v6.0.0〜v6.25.0）、合計**4582/4582 PASS**、FAIL 0／SKIP 0、全ファイルexit code 0。うち新規v6.25.0：**128/128 PASS**。INV-1〜INV-7・R-5確認済み。実行は`.\venv\Scripts\python.exe`のみ使用。test実行後の`git status`は実行前と同一で想定外の差分なし。21.3節・16.6節参照） |
| **Code Review 1** | Changes Required（Blocking 0／Major 3／Minor 2／Suggestion 5）。Major-1〜3・Minor-1〜2はいずれも反映済み（18.1節・21.1節・21.2節参照）。Suggestion 5件（S-1〜S-5）は未対応のままDeferred |
| **Code Review 2** | **Approved with Suggestions**（Blocking 0／Major 0／Minor 1／Suggestion 5）。新規Minor（§0・§16.7の記述が実態と不整合だった点）は前回改訂で解消（21.3節参照）。Suggestion 5件（S-1〜S-5）は引き続きDeferred |
| **Release** | **未確定**（Formal Regression PASSまで完了したが、Release Review・人間の最終承認・commit/pushはいずれも本改訂時点では未実施であり、これらを経て確定する） |

**Design起票開始時のRepository状態**（本設計書の作成に着手する直前の時点）：
branch `main`、HEAD = `origin/main` = `7bea4963a21fa1eb2ad172e51d35c1aa72a11fa8`
（Release 6.24.0）、ahead／behind 0／0、Working Tree clean。

**現在（本改訂時点）の状態**：HEADは開始時点から変更なし（`7bea4963a21fa1eb2ad172e51d35c1aa72a11fa8`、
ahead／behind 0／0）。Architecture Design・Architecture Review 1／2・Test Review・
Production Implementation・New E2E・限定回帰・Code Review 1／2・Documentation
Integration・**Formal Regression（PASS）**はいずれも完了している（本節の各行参照）が、
**commitはまだ行っていない**。`git status --short`実測では、Production Code 7ファイル・
既存tests 6ファイル・`docs/ROADMAP.md`・`docs/CHANGELOG.md`・`docs/architecture.md`が
`modified`、本設計書と新規E2E（`tests/test_e2e_v6_25_0_*.py`）が`untracked`として存在する。
**Formal Regression実行後の`git status`は実行前と完全に同一であり、テスト実行による
想定外の差分は生じていない。**

**本工程（Formal Regression結果のDocumentation最小反映）で変更するファイル**：
本設計書・`docs/ROADMAP.md`・`docs/CHANGELOG.md`・`docs/architecture.md`の4件のみ。
Production Code・testsは無変更（実装済みの内容を変更せず、テストの再実行もしない）。
Release Review・人間の最終承認・commit・pushは本工程の対象外である。

**本設計はClaude Code単体の工程として、Architecture Design（3回の内部改訂）・
Architecture Review 1／2・Test Review／Implementation前Gate確認・Production
Implementation・Code Review 1／2をいずれも完了している。** Codexによる
セカンドオピニオンはArchitecture Review・Code Reviewの各段階で実施済み（該当章参照）。

---

## 1. Project Charter

### 1.1 目的

Release 6.9.0〜6.24.0 で整備された画像系Foundation群（`openai_image_generation`／
`wordpress_media`／`image_generation_fallback_policy`／`article_featured_media_runtime`
等）は、featured media 処理の失敗を `ImageGenerationFailureCategory`（5値）・
`ImageGenerationFallbackAction`（2値）へ安全に分類する仕組みを既に確立している
（v6.19.0）。しかし現在、この分類結果が永続化されるのは **CONTINUE 経路の console
出力1行のみ**（`main.py::_apply_featured_media_step()` L192）であり、PROPAGATE
経路（記事投稿を見送るケース）では固定文言のみが記録され、category・action・
reason のいずれも失われている（`main.py::_handle_featured_media_failure()` L229-237）。

本Releaseは、この観測の欠落を解消し、featured media fallback の発生・category・
action・reason を `ArticleLogEntry`（JSON Lines）へ安全に記録する基盤を確立する。

### 1.2 背景

- v6.19.0 設計書 §18.1 が観測契約 O-1〜O-7 を定義済み（fallback発生・category・
  action の記録を要求。§18.1 O-2／O-3）だが、実装は本Releaseまで先送りされてきた
  （§18.2「本Releaseは観測契約の定義のみ」）。
- v6.24.0 設計書 §2.2 D-3 が、reason を記録しなければ `UNKNOWN`／`INVALID_RESPONSE`
  の内訳（v6.24.0 で15値へ細分化済み）が運用データとして活かせないと明記している。
- `docs/architecture.md`・`docs/CHANGELOG.md` の複数箇所（DEF-6.22-1・DEF-6.23-2・
  v6.24.0 設計書 §5 N-1）が、WordPress側 CONTINUE 対象拡大の判断には「DI-5 の運用
  データと人間の明示承認」が前提であると明記しており、本Releaseはその前提条件を
  満たす最初のステップとなる。
- `article_featured_media_runtime_wiring.md`（v6.21.0）§19 DEF-3 が「PROPAGATE 時の
  category 記録・構造化ログ・metrics」を DI-5 へ明示的に引き継いでいる。

### 1.3 成功条件

- CONTINUE・PROPAGATE いずれの経路でも、featured media fallback の `category`・
  `action`・secret-free な `reason` が `ArticleLogEntry` へ記録される。
- 記録される情報は既知の分類ラベル（Enum の `.value`）のみであり、raw exception
  message・prompt・credential・Provider応答本文・HTTP情報・image bytes のいずれも
  含まない。
- `main.py` は `article_featured_media_runtime` 以外の画像系packageを一切import
  しない（既存の `GUARD-NO-OTHER-IMAGE-PACKAGE` 契約を維持）。
- fallback の category/action mapping・CONTINUE 対象4値・PROPAGATE の bare raise・
  exception identity・chaining はいずれも無変更。

### 1.4 非目的（Charter レベル）

- WordPress側 CONTINUE 対象拡大（DEF-6.22-1）は行わない。本Releaseはそのための
  「運用データを得る」ステップに留まる。
- metrics 集計・通知・閾値・circuit breaker（Retry Runtime 系列の既存 Deferred 群）
  は対象外。
- DI-9（Gate値 strict validation）・s-3／s-7（v6.24.0 設計書 §19.8 の残存
  Suggestion）は対象外。
- fallback の判断ロジック（`decide_image_generation_fallback()` の分類テーブル）
  自体の変更は行わない。

---

## 2. Context

v6.19.0 が定義した観測契約（`image_generation_fallback_policy_foundation.md`
§18.1）を引用する：

```text
O-1  fallback occurred:      Decision が返された事実そのもの。
O-2  fallback reason category: Decision.category（provider中立の5値）
O-3  action:                 Decision.action（2値、derived property）
O-4  retryable / non-retryable: 本Releaseでは表現しない（Q-6で確定）。
O-5  stage:                  category から間接的に判別できる範囲に留める。
O-6  provider:               表現しない（provider中立な語彙を保つため）。
O-7  article identifier:     本packageは扱わない。記事の識別はDI-4／DI-5の責務。
```

v6.24.0 設計書 §2.2 は次のとおり将来課題を明示している：

```text
D-3  将来 DI-5（reasonの構造化ログ／metrics記録）を実施しても、UNKNOWNと
     INVALID_RESPONSEの内訳が取れず、ORD-1の再評価に必要な運用データの粒度が
     不足する
```

本Releaseは O-1〜O-3 の実装と、D-3 が要求する reason 粒度の記録を統合して行う。

---

## 3. Current Architecture（Repository の事実）

### 3.1 CONTINUE 経路（現状）

`src/article_featured_media_runtime/article_featured_media_runtime.py` L118-128：

```python
try:
    applied_article = self._root.orchestrator.apply(article, prompt, filename)
except Exception as error:
    decision = decide_image_generation_fallback(error)
    if decision.action is ImageGenerationFallbackAction.PROPAGATE_ORIGINAL_ERROR:
        raise
    return ArticleFeaturedMediaRuntimeResult(
        article=article,
        status=ArticleFeaturedMediaRuntimeStatus.CONTINUED_WITHOUT_FEATURED_MEDIA,
        category=decision.category,
    )
```

`main.py` L182-193（`_apply_featured_media_step()`）は `result.category` を console
へ1行出力するのみで、ログへは記録しない。

### 3.2 PROPAGATE 経路（現状）

`main.py` L424-438：

```python
try:
    article = _apply_featured_media_step(featured_media_runtime, article)
except Exception:
    _handle_featured_media_failure(
        markdown_output, log_manager, article, saved_files,
        importance=importance, seo_title=seo_title,
        wp_public_url=wp_public_url, x_post_status=x_post_status,
    )
    wp_failed_count += 1
    continue
```

例外は変数へ束縛されず（`except Exception:`）、`_handle_featured_media_failure()`
（L196-237）は固定文言 `"featured media processing failed"` のみを
`log_manager.log_article()` へ渡す。category・action・reason はいずれも失われる。

### 3.3 `ArticleFeaturedMediaRuntimeResult`（現状、変更対象）

`article_featured_media_runtime.py` L44-58：

```python
@dataclass(frozen=True)
class ArticleFeaturedMediaRuntimeResult:
    article: ArticleData
    status: ArticleFeaturedMediaRuntimeStatus
    category: ImageGenerationFailureCategory | None = None
```

### 3.4 `image_generation_fallback_policy`（現状、reason 判定ロジック）

`image_generation_fallback_policy.py` L36-40（既存import）：

```python
from openai_image_generation import (
    OpenAIImageGenerationError,
    OpenAIImageGenerationErrorReason,
)
from wordpress_media import WordPressMediaUploadError
```

`WordPressMediaUploadErrorReason` は現状未import（`decide_image_generation_fallback()`
は WordPress 由来の例外を `.reason` を読まず一律 `MEDIA_UPLOAD_FAILED` へ写像するため。
L177-178）。両exception型はいずれも `.reason` 属性を持つ（`openai_image_generator.py`
L96-98、`wordpress_media_uploader.py` L60-66）。

### 3.5 `ArticleLogEntry`（現状、変更対象）

`src/logger/log_entry.py` L11-35。`to_json_line()` は `json.dumps(asdict(self))`
（L37-41）で全fieldを直列化する。

### 3.6 main.py の画像系package参照制約（既存、維持対象）

`tests/test_e2e_v6_21_0_article_featured_media_runtime_wiring.py` L601-619
`GUARD-NO-OTHER-IMAGE-PACKAGE` が、`main.py` の import root が
`article_featured_media_runtime` のみであり、`image_generation_fallback_policy`
を含む10個の低レベルpackageを一切importしないことを機械検証している。

---

## 4. Decision — Release 境界（DI-5 と DEF-3 を1 Release へ統合する）

DI-5（observability全般）と DEF-3（PROPAGATE時のcategory記録）は、実装上ほぼ
同一の変更（`ArticleFeaturedMediaRuntimeResult` の拡張・`ArticleLogEntry` の拡張・
`main.py` の except 節変更）を要求するため、**分離すると「CONTINUE のみ観測できる
半分だけの DI-5」という中途半端な状態になる**（v6.19.0 O-1〜O-3 は経路を限定して
いない）。したがって本Releaseで両者を統合し、DI-5 を単一 Release で完結させる。

---

## 5. Target Architecture

```
                    ┌─────────────────────────────────────────┐
                    │ image_generation_fallback_policy         │
                    │  - decide_image_generation_fallback()     │  ← 無改修（分類ロジック）
                    │  - extract_safe_reason()  【新規】         │  ← 新規（reason正規化）
                    └───────────────┬───────────────────────────┘
                                    │ article_featured_media_runtimeがimportする
                                    │ symbol数：既存3→4（7.1節。パッケージ自身の
                                    │ __all__は既存4→5、9章参照。両者は別カウント）
                    ┌───────────────▼───────────────────────────┐
                    │ article_featured_media_runtime             │
                    │  - ArticleFeaturedMediaRuntimeResult        │  ← observation field追加
                    │      (article, status, category, observation)
                    │  - FeaturedMediaFailureObservation 【新規】  │  ← category/action/reason
                    │  - ArticleFeaturedMediaRuntime.apply()      │  ← CONTINUE: observation構築
                    │  - ArticleFeaturedMediaRuntime               │
                    │      .classify_propagated_failure() 【新規】│  ← PROPAGATE: observation構築
                    └───────────────┬───────────────────────────┘
                                    │ import（唯一の画像系package参照）
                    ┌───────────────▼───────────────────────────┐
                    │ main.py                                    │
                    │  - _apply_featured_media_step()             │  ← 戻り値でobservation運搬
                    │  - _handle_featured_media_failure()         │  ← observation受け取り・ログ記録
                    │  - log_manager.log_article(...)             │  ← category/action/reason追加
                    └───────────────┬───────────────────────────┘
                                    │
                    ┌───────────────▼───────────────────────────┐
                    │ src/logger/log_entry.py                    │
                    │  - ArticleLogEntry                          │  ← 3field追加（flat schema）
                    └─────────────────────────────────────────────┘
```

責務境界：
- **`image_generation_fallback_policy`**：「CONTINUEかPROPAGATEか」の判断（無改修）＋
  「secret-freeなreason文字列への正規化」（新規）。いずれもstateless・副作用なし。
- **`article_featured_media_runtime`**：判断結果（Decision）と例外から observation
  （記録用スナップショット）を構築する唯一の場所。CONTINUE・PROPAGATE 双方の
  唯一のobservation生成経路。main.pyが参照してよい唯一の画像系Facade。
- **`main.py`**：observationをログへ橋渡しするのみ。低レベルpackageへの参照・
  reason判定ロジックの実装は一切持たない。

---

## 6. `FeaturedMediaFailureObservation` 契約

`src/article_featured_media_runtime/article_featured_media_runtime.py` へ新設。

```python
@dataclass(frozen=True)
class FeaturedMediaFailureObservation:
    """featured media処理失敗の観測用スナップショット。

    fallback判断（apply()内部のCONTINUE/PROPAGATE決定）には一切関与しない、
    読み取り専用の記録専用オブジェクト。raw exception・例外message・prompt・
    credential・Provider応答本文・image bytesのいずれも保持しない。
    """
    category: ImageGenerationFailureCategory
    action: ImageGenerationFallbackAction
    reason: str | None
```

- `category`／`action`：v6.19.0 の既存Enum値をそのまま保持（provider中立、
  secret-free。O-6 準拠）。
- `reason: str | None`：`extract_safe_reason()`（7章）の戻り値。**`None` は
  「reason情報が取得できなかった」ことを意味し、`"unknown"`（`OpenAIImageGenerationErrorReason.UNKNOWN.value`）のような正式に定義済みの
  reason値とは明確に区別される別状態**である（7.3節）。
- frozen dataclass。ミュータブルなfieldを持たない。
- `image_generation_fallback_policy`ではなく `article_featured_media_runtime`
  パッケージに配置する（8章・依存方向の根拠は7.1節参照）。

`ArticleFeaturedMediaRuntimeResult` の拡張（既存3fieldは無変更）：

```python
@dataclass(frozen=True)
class ArticleFeaturedMediaRuntimeResult:
    article: ArticleData
    status: ArticleFeaturedMediaRuntimeStatus
    category: ImageGenerationFailureCategory | None = None   # 既存・無変更
    observation: FeaturedMediaFailureObservation | None = None  # 新規・末尾追加
```

`category` fieldは後方互換のため意味・型とも維持し、既存consumer（本Release時点
では存在しないが、`RESULT-CATEGORY-DEFAULT-NONE`・`*-CATEGORY-NONE`系の既存テスト
群）への影響を最小化する。`observation` は `category`/`action`/`reason` の3値を
まとめて保持する新設fieldであり、CONTINUE時のみ非`None`（PROPAGATE時は
`apply()`が`Result`自体を返さずbare raiseするため、`observation`は
`classify_propagated_failure()`の戻り値として別途取得する。5.1節・8章参照）。

`module-private` な単一生成関数（CONTINUE／PROPAGATE 双方が使用する唯一の
observation構築箇所）：

```python
def _build_observation(
    decision: ImageGenerationFallbackDecision, error: Exception
) -> FeaturedMediaFailureObservation:
    """decisionとerrorから observation を1回だけ構築する。
    CONTINUE（apply()内部）とPROPAGATE（classify_propagated_failure()）の
    両方が使用する唯一の生成箇所（重複実装を避ける）。
    """
    return FeaturedMediaFailureObservation(
        category=decision.category,
        action=decision.action,
        reason=extract_safe_reason(error),
    )
```

---

## 7. `extract_safe_reason()` 契約

### 7.1 配置・依存方向

`src/image_generation_fallback_policy/image_generation_fallback_policy.py` へ
新規public関数として追加する。

**根拠**：
- 同packageは既に `OpenAIImageGenerationError`／`OpenAIImageGenerationErrorReason`
  （L36-39）・`WordPressMediaUploadError`（L40）をimport済みであり、
  `decide_image_generation_fallback()` は既に `error.reason` を分類根拠として
  読んでいる（L159, L164-172）。reason抽出は本packageの既存責務（provider中立な
  安全分類）の自然な延長であり、新しい依存方向を生まない。
- `WordPressMediaUploadErrorReason` のみ新規import（既存の `wordpress_media`
  importへの追加symbolであり、新しいpackage依存edgeではない）。
- `article_featured_media_runtime` は既に本packageから3symbol
  （`ImageGenerationFailureCategory`／`ImageGenerationFallbackAction`／
  `decide_image_generation_fallback`）をimport済み（L28-32）であり、4つ目の
  symbol `extract_safe_reason` を追加するのみ。`openai_image_generation`／
  `wordpress_media` への直接importは `article_featured_media_runtime` へ
  一切追加しない。

  **注意（Architecture Review Major-1対応）**：上記の「3symbol→4symbol」は
  `article_featured_media_runtime` が本packageから**importする** symbol数
  （import edge）であり、`image_generation_fallback_policy` パッケージ自身の
  `__all__`（package全体の公開symbol数）とは**別のカウント**である。
  `src/image_generation_fallback_policy/__init__.py` L18-23の実測により、
  同packageの`__all__`は既に**4symbol**（`ImageGenerationFailureCategory`／
  `ImageGenerationFallbackAction`／`ImageGenerationFallbackDecision`／
  `decide_image_generation_fallback`）であることを確認済みであり、
  `extract_safe_reason`追加後は**既存4→5symbol**となる（9章・18章 `COMPAT-V619`
  参照）。両者を混同しないこと。

### 7.2 実装契約

```python
from openai_image_generation import OpenAIImageGenerationError, OpenAIImageGenerationErrorReason
from wordpress_media import WordPressMediaUploadError, WordPressMediaUploadErrorReason  # Reason追加

_KNOWN_ERROR_TYPES = (OpenAIImageGenerationError, WordPressMediaUploadError)
_KNOWN_REASON_TYPES = (OpenAIImageGenerationErrorReason, WordPressMediaUploadErrorReason)


def extract_safe_reason(error: Exception) -> str | None:
    """error が allow-list 対象の既知 Exception 型であり、かつその .reason が
    allow-list 対象の既知 Reason Enum である場合のみ、その .value（str）を返す。
    str(error)／repr(error)／type(error).__name__は一切参照しない。

    未知の Exception 型に対しては .reason を一切読まない（Architecture Review
    Major-3対応：任意の Exception が.reason という名前の property／descriptor を
    独自に定義しており、そのgetterが例外を送出する可能性を排除するため、
    型確認を先に行う防御的順序を採用する）。
    """
    if not isinstance(error, _KNOWN_ERROR_TYPES):
        return None
    reason = getattr(error, "reason", None)
    if isinstance(reason, _KNOWN_REASON_TYPES):
        return reason.value
    return None
```

- **防御的順序（Architecture Review Major-3対応）**：まず`error`自体が
  `_KNOWN_ERROR_TYPES`（`OpenAIImageGenerationError`／`WordPressMediaUploadError`）
  のインスタンスであることを`isinstance`で確認し、**既知の例外型である場合のみ**
  `.reason`属性を読む。両型の`.reason`は単純な属性代入（`self.reason = reason`、
  `openai_image_generator.py` L96-98・`wordpress_media_uploader.py` L60-66）で
  あり`property`ではないことを実測確認済みだが、`extract_safe_reason(error: Exception)`
  は型注釈上あらゆる`Exception`を受け取りうるため、未知の`Exception`サブクラスが
  `.reason`という名前の`property`／descriptorを独自に定義し、そのgetterが例外を
  送出する可能性を型確認なしに排除できない。この順序（`isinstance(error, ...)`
  確認 → `.reason`取得 → `isinstance(reason, ...)`確認）により、未知の例外型に
  対しては`getattr`自体を一切実行しない。
- **allow-list方式**（deny-listではない）：`_KNOWN_ERROR_TYPES`・`_KNOWN_REASON_TYPES`
  のいずれも、2つの既知型のインスタンスである場合のみ処理を進める。v6.23.0が
  確立した positive allow-list方式（I-EXC-1）と同じ設計思想。
- **未知型・非Enum・属性欠落はすべて`None`**：`error`が`OpenAIImageGenerationError`／
  `WordPressMediaUploadError`のいずれでもない場合、`.reason`属性が存在しない
  場合、`.reason`が想定外の型（list/dict/文字列等）である場合、いずれも`None`。
- **str(error)／repr(error)／type(error).__name__は一切呼ばない**：`isinstance`と
  `getattr`のみを使用し、例外オブジェクトそのものの文字列化・クラス名参照を
  行わない。
- **新しい人工的なreason文字列を作らない**：`.value`をそのまま転記するのみ。
  例えば"TRANSIENT"のような独自ラベルは生成しない。
- **既存分類契約は変更しない**：`OpenAIImageGenerationErrorReason`（15値）・
  `WordPressMediaUploadErrorReason`（12値）のname/value/定義順、
  `decide_image_generation_fallback()`の分類ロジックはいずれも無改修。

### 7.3 `None` と 正式 `UNKNOWN` の区別

| 状態 | `observation.reason` の値 | 意味 |
|---|---|---|
| `error`が`OpenAIImageGenerationError`で`reason=OpenAIImageGenerationErrorReason.UNKNOWN` | `"unknown"` | **既知の、正式に定義済みのreason値**（provider adapterが分類できなかったことを示す正当な分類結果） |
| `error`が上記2型のいずれでもない、または`.reason`属性を持たない | `None` | **reason情報が取得できなかった**（観測不能。分類対象外の例外） |
| `error.reason`が想定外の型（例：文字列やlist） | `None` | 同上（防御的フォールバック） |

この区別は`FeaturedMediaFailureObservation.reason: str | None`という型設計その
ものによって保証され、`extract_safe_reason()`が両者を混同することはない。

### 7.4 ログ境界での正規化

`observation.reason`（`str | None`）を`ArticleLogEntry.featured_media_reason`
（`str`のみ許容）へ渡す際、呼び出し側（`main.py`）で
`observation.reason or ""`のように明示的に変換する（`article.publish_status.value`
と同様、呼び出し側での明示的な値取り出しパターンを踏襲）。**この変換はログ書き込み
という境界でのみ発生する処理であり、Runtime内部（`FeaturedMediaFailureObservation`）
では`None`と`"unknown"`の区別を最後まで保持する。**

---

## 8. CONTINUE／PROPAGATE data flow

### 8.1 CONTINUE 経路

```python
# article_featured_media_runtime.py::apply()
try:
    applied_article = self._root.orchestrator.apply(article, prompt, filename)
except Exception as error:
    decision = decide_image_generation_fallback(error)          # 既存・1回のみ
    if decision.action is ImageGenerationFallbackAction.PROPAGATE_ORIGINAL_ERROR:
        raise                                                    # 既存bare raise・無変更
    observation = _build_observation(decision, error)             # 新規（decisionを再利用）
    return ArticleFeaturedMediaRuntimeResult(
        article=article,
        status=ArticleFeaturedMediaRuntimeStatus.CONTINUED_WITHOUT_FEATURED_MEDIA,
        category=decision.category,                              # 既存field・後方互換維持
        observation=observation,                                  # 新規field
    )
```

`decide_image_generation_fallback()`は**1回のみ**呼ばれる（既存の呼び出しを
再利用し、observation生成のために再評価しない）。

main.py側（`_apply_featured_media_step()`）は`result.observation`を戻り値経由で
呼び出し元へ運ぶ（9.3節）。

### 8.2 PROPAGATE 経路

```python
# article_featured_media_runtime.py::ArticleFeaturedMediaRuntime（新規メソッド）
def classify_propagated_failure(self, error: Exception) -> FeaturedMediaFailureObservation:
    """PROPAGATE後、呼び出し側（main.py）がobservability目的で失敗を分類するための
    読み取り専用API。apply()内部のCONTINUE/PROPAGATE決定には一切関与しない。
    """
    decision = decide_image_generation_fallback(error)   # 新規・1回のみ（apply()内部の
                                                           # decisionとは独立した再構築。
                                                           # bare raiseによりDecisionが
                                                           # 呼び出し側へ運ばれないため
                                                           # 構造上必要）
    return _build_observation(decision, error)            # CONTINUEと同じhelper
```

```python
# main.py（記事ループ）
try:
    article = _apply_featured_media_step(featured_media_runtime, article)
except Exception as exc:                                  # 変更：例外を束縛（10章）
    observation = featured_media_runtime.classify_propagated_failure(exc)
    _handle_featured_media_failure(
        markdown_output, log_manager, article, saved_files,
        importance=importance, seo_title=seo_title,
        wp_public_url=wp_public_url, x_post_status=x_post_status,
        observation=observation,                            # 新規引数
    )
    wp_failed_count += 1
    continue
```

`decide_image_generation_fallback()`の呼び出し回数：CONTINUEは1回（既存の
み）、PROPAGATEはapply()内部で1回（bare raise前に破棄）＋`classify_propagated_failure()`で
1回（observability目的の再構築）＝合計2回。これは重複実装ではなく、
bare raiseがDecisionオブジェクトを呼び出し側へ運ばない構造上、PROPAGATE側で
observabilityを得るための最小限の再構築である。

### 8.3 例外の同一性・伝播

`classify_propagated_failure(error)`は`error`を読み取るのみで、変更（属性設定）・
再送出・wrapを一切行わない。`main.py`の`except Exception as exc:`ブロック内で
`exc`が再送出されることはなく（既存どおり`continue`で次記事へ進む）、
`ArticleFeaturedMediaRuntime.apply()`のbare raise契約自体にも変更はない。

### 8.4 main.py 記事ループ全体のdata flow（Architecture Review Major-4対応）

8.1節・8.2節はFacade側（`article_featured_media_runtime`内部）の変更に限定して
示した。ここでは`main.py`の記事ループ全体で`observation`がどのように初期化・
伝播・消費されるか、DISABLED／APPLIED／CONTINUE／PROPAGATEの4経路とWordPress
保存成否を横断する擬似コードで具体化する。

```python
for item in news_items:                                    # 記事ループの各反復
    # ... 記事生成・importance判定等（既存、無変更） ...

    featured_media_observation: FeaturedMediaFailureObservation | None = None
    # ↑ 各記事の反復ごとに毎回Noneへ再初期化する。前の記事の観測値が
    #   次の記事へ漏れないことを保証する唯一の箇所（ループ変数のスコープにより
    #   構造的に保証される。Test Strategy `NOLEAK-` 参照）。

    try:
        result = _apply_featured_media_step(featured_media_runtime, article)
        article = result.article
        # DISABLED時：result.observation は None のまま（8章、Result契約）
        # APPLIED時　：result.observation は None のまま（同上）
        # CONTINUED_WITHOUT_FEATURED_MEDIA時：
        #   result.observation は FeaturedMediaFailureObservation（非None）
        featured_media_observation = result.observation
    except Exception as exc:                                # PROPAGATE経路（10章）
        featured_media_observation = featured_media_runtime.classify_propagated_failure(exc)
        _handle_featured_media_failure(
            markdown_output, log_manager, article, saved_files,
            importance=importance, seo_title=seo_title,
            wp_public_url=wp_public_url, x_post_status=x_post_status,
            observation=featured_media_observation,
        )
        wp_failed_count += 1
        continue                                            # 次記事へ（既存、無変更）

    # ここへ到達するのは DISABLED／APPLIED／CONTINUED_WITHOUT_FEATURED_MEDIA の
    # いずれかの場合のみ（PROPAGATEはcontinueで既に次記事へ進んでいる）

    # ... 既存のWordPress保存フロー（save_all()・wp_result判定、無変更） ...

    log_manager.log_article(
        article=article,
        edit_url=edit_url,
        result=wp_result,                                   # 既存："success"/"failed"/"skipped"
        # ... 既存の引数群（無変更） ...
        featured_media_category=(
            featured_media_observation.category.value if featured_media_observation else ""
        ),
        featured_media_action=(
            featured_media_observation.action.value if featured_media_observation else ""
        ),
        featured_media_reason=(
            (featured_media_observation.reason or "") if featured_media_observation else ""
        ),
    )
```

**経路別のログ記録内容**：

| 経路 | `featured_media_observation` | ログへ渡る3値 |
|---|---|---|
| DISABLED | `None` | `""` / `""` / `""` |
| APPLIED | `None` | `""` / `""` / `""` |
| CONTINUED_WITHOUT_FEATURED_MEDIA ＋ WordPress成功 | 非`None` | `category.value` / `action.value` / `reason or ""`（通常のsuccess系`log_article()`呼び出しへ同梱） |
| CONTINUED_WITHOUT_FEATURED_MEDIA ＋ WordPress失敗 | 非`None` | 同上（通常のfailed系`log_article()`呼び出しへ同梱） |
| PROPAGATE | 非`None`（`classify_propagated_failure()`の戻り値） | `category.value` / `action.value` / `reason or ""`（`_handle_featured_media_failure()`内の`log_article()`呼び出しへ同梱） |

**article間のリーク防止**：`featured_media_observation`はfor文の各反復内で
ローカル変数として`None`へ再初期化してから使用する。Pythonのスコープ規則上、
前の反復で設定された値が次の反復へ持ち越されることはない（変数自体は
ループ外で使い回されるが、各反復の先頭で必ず再代入されるため、値の意味上の
リークは発生しない）。この点をTest Strategy（16章）`NOLEAK-`として明示的に
検証する。

---

## 9. Public API／schema変更

| ファイル | 変更 |
|---|---|
| `src/image_generation_fallback_policy/image_generation_fallback_policy.py` | `extract_safe_reason()`新規追加。`WordPressMediaUploadErrorReason`のimport追加。`__all__`を**既存4→5シンボル**へ拡張（Architecture Review Major-1対応：既存`__all__`は`ImageGenerationFailureCategory`／`ImageGenerationFallbackAction`／`ImageGenerationFallbackDecision`／`decide_image_generation_fallback`の4symbol。実測：`__init__.py` L18-23） |
| `src/image_generation_fallback_policy/__init__.py` | `__all__`拡張（既存4→5シンボル、`extract_safe_reason`追加） |
| `src/article_featured_media_runtime/article_featured_media_runtime.py` | `FeaturedMediaFailureObservation`新設。`ArticleFeaturedMediaRuntimeResult`へ`observation`field追加。`_build_observation()`（module-private）追加。`ArticleFeaturedMediaRuntime.classify_propagated_failure()`追加 |
| `src/article_featured_media_runtime/__init__.py` | `__all__`を既存3→4シンボルへ拡張（`FeaturedMediaFailureObservation`追加。実測：`__init__.py` L18-22で既存3symbol確認済み） |
| `src/logger/log_entry.py` | `ArticleLogEntry`へ`featured_media_category: str = ""`／`featured_media_action: str = ""`／`featured_media_reason: str = ""`を末尾追加（既存18field・順序は無変更） |
| `src/logger/log_manager.py` | `LogManager.log_article()`**および`NullLogManager.log_article()`の双方**のシグネチャへ`featured_media_category: str = ""`／`featured_media_action: str = ""`／`featured_media_reason: str = ""`を追加（Architecture Review Major-2対応。9.2節参照） |
| `main.py` | `except Exception:`→`except Exception as exc:`。`_apply_featured_media_step()`の戻り値を`ArticleFeaturedMediaRuntimeResult`（既存型）そのままに変更し、呼び出し元で`result.article`／`result.observation`を個別に取り出す形へ変更（9.1節・9.3節）。`_handle_featured_media_failure()`へ`observation`引数追加。L455の`log_article()`呼び出しへ3引数追加 |

### 9.1 `_apply_featured_media_step()` の戻り値方式

**採用**：新しいtupleや専用main.py型を作らず、`ArticleFeaturedMediaRuntime.apply()`
が既に返している`ArticleFeaturedMediaRuntimeResult`を**そのまま**返す方式へ変更する。

```python
def _apply_featured_media_step(
    runtime: ArticleFeaturedMediaRuntime, article: ArticleData
) -> ArticleFeaturedMediaRuntimeResult:
    result = runtime.apply(article)
    if result.status is ArticleFeaturedMediaRuntimeStatus.CONTINUED_WITHOUT_FEATURED_MEDIA:
        print(f"    アイキャッチ画像なしで継続します（分類: {result.category.value}）")
    return result
```

呼び出し元（main.py記事ループ）は`result.article`を既存の`article`変数へ束縛し、
`result.observation`をログ記録用に保持する。これにより、`ArticleFeaturedMediaRuntimeResult`
という既存の公開型を戻り値の型として再利用でき、新しいmain.py固有の型を導入しない
（Public APIの重複を避ける）。

### 9.2 `NullLogManager`対応（Architecture Review Major-2対応）

`LOG_ENABLED=false`時、`LogManager.from_env()`（`log_manager.py` L34-57）は
`NullLogManager`を返す。現状の`NullLogManager.log_article()`（`log_manager.py`
L187-189）は次のシグネチャのみを受け付ける：

```python
def log_article(self, article=None, edit_url="", result="success", error_message="",
                wp_public_url="", x_post_status=None, x_post_url="", post_id=None) -> None:
    pass
```

`main.py`が本Releaseで常に`featured_media_category`／`featured_media_action`／
`featured_media_reason`をkeyword引数として`log_article()`へ渡す設計であるため、
**`NullLogManager.log_article()`も同3引数を受け付けるようシグネチャを拡張しなければ、
`LOG_ENABLED=false`時に`TypeError: log_article() got an unexpected keyword argument`
が発生する。**

```python
class NullLogManager:
    def log_article(self, article=None, edit_url="", result="success", error_message="",
                    wp_public_url="", x_post_status=None, x_post_url="", post_id=None,
                    featured_media_category: str = "", featured_media_action: str = "",
                    featured_media_reason: str = "") -> None:
        pass
```

**契約**：`LogManager.log_article()`と`NullLogManager.log_article()`は常に同一の
キーワード引数集合を受け付ける（既存の対称性、`log_manager.py` L97-107と
L187-189の既存の対応関係を維持）。`NullLogManager`側は何も行わない（no-op）
という既存契約を無変更のまま、受け付ける引数のみを拡張する。

この対応がないままでは、INV-6（Gate OFF／APPLIED／CONTINUE／PROPAGATE後の
記事処理・counter・loopが不変）が`LOG_ENABLED=false`という設定下で破れる
（記事ループが`TypeError`で停止しうる）ため、本節の対応はINV-6の前提条件
として必須である。

### 9.3 main.py 記事ループ全体のdata flow（Architecture Review Major-4対応）

8章のFacade側変更を踏まえ、main.py記事ループ全体で`observation`がどのように
初期化・伝播・消費されるかを擬似コードで具体化する（詳細は8.4節）。

---

## 10. JSON Lines 全記事への3キー追加と後方互換性

### 10.1 仕様変更の明示

`ArticleLogEntry.to_json_line()`は`json.dumps(asdict(self), ensure_ascii=False)`
（`log_entry.py` L37-41）で全fieldを直列化するため、fallback未発生の記事
（`ArticleFeaturedMediaRuntimeStatus.DISABLED`／`APPLIED`）を含む**全記事ログ行**に
新3キー（`featured_media_category`／`featured_media_action`／`featured_media_reason`）
が常時追加される（値は`""`）。**これは全記事のJSON Linesスキーマの変更であり、
本Releaseの正式な仕様変更として明記する。**

既存の`error_message: str = ""`（エラーなし時は空文字列）と同型の慣行に一致するため、
新しい種類の非対称は生じないが、「全行にキーが増える」という事実そのものは利用者へ
明示すべき仕様変更である。

### 10.2 既存consumerへの影響確認

**本節が保証する後方互換性は「確認済みRepository内consumerに対する後方互換」に
限定される。** 外部ツール・未知のstrict schema consumer（キー集合の完全一致検証や
snapshot比較を行うもの）に対する互換性は、その存在をRepository内で確認できない
ため保証の対象外であり、非互換となり得ることを明記する（Architecture Review
Suggestion-1対応）。

| consumer | 確認内容 | 影響（Repository内） |
|---|---|---|
| `src/analytics/analytics_manager.py::load_article_logs()`（L106-122） | `json.loads(line)`で辞書を素通し、schema検証なし | **影響なし** |
| `src/analytics/analytics_manager.py::build_analysis_record()`（L174-195） | `article.get(key, default)`方式でキー取得 | **影響なし**（未知キーは無視される） |
| `scripts/run_ai_improvement.py`等 | analytics_manager経由でdictアクセス | **影響なし** |
| `tests/test_e2e_v1_9_0_sns_foundation.py` L150-153 | `"key" in json_line`の部分文字列検査のみ | **影響なし** |

キー集合を厳密に検証するconsumer（本Repository内には現状存在しないことを確認済み）
やsnapshot比較を行う外部ツールが将来追加された場合は、この仕様変更の影響を受ける
可能性がある旨を21章（リスク R-4）に記録する。将来的なschema version導入
（`schema_version`フィールドの追加等）が必要になった場合は、そのタイミングで
別Releaseとして独立検討する（21章 D-3）。

---

## 11. Security／Secret-free契約

- `main.py`は`article_featured_media_runtime`のみを参照し続け、
  `image_generation_fallback_policy`／`openai_image_generation`／`wordpress_media`
  のいずれも一切importしない（`GUARD-NO-OTHER-IMAGE-PACKAGE`維持、12.1節）。
- `extract_safe_reason()`は`str(error)`／`repr(error)`／`type(error).__name__`を
  一切参照しない（7.2節）。
- `FeaturedMediaFailureObservation`はraw exception・prompt・credential・
  Provider応答本文・image bytesのいずれも保持しない（`category`／`action`／
  `reason`の3値のみ）。
- `classify_propagated_failure(error)`は`error`を読み取るのみで、変更・再送出・
  wrapを一切行わない。
- ログ書き込み時も`observation.category.value`／`observation.action.value`／
  `observation.reason or ""`という**plain str**のみを渡し、`ArticleLogEntry`／
  `log_article()`が非直列化可能な値を受け取ることを構造的に防止する（この構造的
  保証により、ログI/O失敗を防ぐための新規の広い`try/except`は不要となる。13.3節）。

---

## 12. Facade責務拡大の限定条件（`classify_propagated_failure()`）

以下の条件をすべて満たすことを確認し、採用する：

| 条件 | 確認結果 |
|---|---|
| `main.py`の`GUARD-NO-OTHER-IMAGE-PACKAGE`を維持する | **満たす**（main.pyは`featured_media_runtime`インスタンス経由でのみ呼び出す。低レベルpackageの直接importは発生しない） |
| bare raise／例外identity／message／chainingを不変に保つ | **満たす**（`classify_propagated_failure()`は`error`を読み取るのみ。`apply()`のbare raise契約には触れない） |
| stateを保持しない | **満たす**（`ArticleFeaturedMediaRuntime`インスタンスは`self._root`のみ保持。`classify_propagated_failure()`は引数のみに依存する純粋なメソッド） |
| I/Oなし | **満たす**（`decide_image_generation_fallback()`・`extract_safe_reason()`はいずれも副作用なし） |
| fallback policyそのものを変更しない | **満たす**（`decide_image_generation_fallback()`の分類テーブルは無改修） |
| observability専用の薄いFacade APIに限定する | **満たす**（判断結果の再構築のみ。新しい判断ロジックを持たない） |

**代替案との比較**（いずれも不採用）：
- main.pyから`image_generation_fallback_policy`を直接呼び出す案 →
  `GUARD-NO-OTHER-IMAGE-PACKAGE`に抵触するため不採用。
- 例外オブジェクトへ`category`/`action`属性を付与する案 → bare raise契約
  （「元例外を無変換で再送出する」）を汚染するため不採用。
- main.py側で独自にreason判定ロジックを再実装する案 → ロジックの重複実装に
  なるため不採用。

---

## 13. Configuration／Fail Safe Logging

### 13.1 環境変数

本Releaseは新規の環境変数を追加しない。既存の`LOG_ENABLED`／`LOG_DIR`
（`log_manager.py` L47-57）・`AI_IMAGE_GENERATION_ENABLED`（Gate、無関係）は
いずれも無変更。

### 13.2 ログI/O失敗時の扱い

既存`LogManager._append()`（`log_manager.py` L65-71）が`OSError`を捕捉し
警告表示のみで処理継続する既存のFail Safe機構をそのまま踏襲する。

### 13.3 新規の広い`try/except`を追加しない

`_handle_featured_media_failure()`内の`log_manager.log_article()`呼び出し全体を
新たに`try/except Exception`で包む設計は**採用しない**。理由：

- 既存コードは`markdown_output.save()`のみを意図的にcatchしており（`main.py`
  L217-220）、`log_article()`呼び出しは無保護（L229-237）。ここを包括catchすると、
  taxonomy解決失敗・属性参照エラー等の**既存のprogramming errorまで新たに
  握り潰す**ことになり、本Releaseの観測追加を超えたRuntime挙動変更になる。
- `observation.category.value`／`observation.action.value`／`observation.reason or ""`
  はいずれも既に`str`型として構築済みであり（11章）、`ArticleLogEntry`の
  `to_json_line()`（`json.dumps`）が`TypeError`を送出する主要な経路を**構造的に
  排除する**。したがって新規の広い`try/except`による防御的処置は不要と判断する。
- 実ファイル書き込み失敗（`OSError`）は既存`_append()`の処理で十分にカバーされる。

**不変条件**：新規観測処理の失敗が、fallback action・元例外の同一性・伝播・
`wp_failed_count`等の集計を変更してはならない。ログ呼び出しは常にこれら3つが
確定した後に行う（既存の呼び出し順序を維持する）。

---

## 14. 不変条件（v6.25個別定義）

v6.24.0のRuntime Action Zero Diff（Z-1〜Z-8）は過去Releaseの成立事実として
**変更しない**。v6.25では新しいZero Diff名称を作らず、以下を個別の不変条件として
定義する。

各INVは「対象ファイル差分なし」という消極的根拠だけでなく、実装後にどの
E2E／既存guard／回帰確認で機械的に検証するかを次の対応表で具体化する
（Architecture Review Minor-2対応）。

| # | 不変条件 | 差分根拠（補助証拠） | 実装後の検証手段（主証拠） |
|---|---|---|---|
| INV-1 | category/action mappingが不変（`_ACTION_BY_CATEGORY`は無改修） | `image_generation_fallback_policy.py`のdiffが分類テーブル部分に及ばないこと | 既存`test_e2e_v6_19_0_image_generation_fallback_policy_foundation.py`の全数検査ループ（category/action対応表）が新規実行でも既存値のまま全件PASSすること |
| INV-2 | CONTINUE対象4値が不変（`_CONTINUABLE_REASONS`は無改修） | 同上 | 同ファイルのCONTINUE対象4値検査（`_CONTINUABLE_REASONS`の内容比較）が新規実行でもPASSすること。新設`Z-8`相当の既存guard（`_CONTINUABLE_REASONS`比較）を回帰させる |
| INV-3 | exception messageが不変 | `openai_image_generation`／`wordpress_media`のmessage生成箇所は本Release対象外 | 既存`test_e2e_v6_11_0_*.py`／`test_e2e_v6_22_0_*.py`のmessage文字列凍結検査（既存Z-4相当）が新規実行でもPASSすること |
| INV-4 | bare raise／object identity／chainingが不変 | `classify_propagated_failure()`は`error`を読み取るのみで再送出・変換を行わない（8.3節） | 新規E2E`PROPAGATE-OBS-`（16.1節）で、`classify_propagated_failure()`呼び出し前後で例外オブジェクトの`id()`が不変であること・`__cause__`/`__context__`が新設フィールドにより変化しないことを直接検査する |
| INV-5 | GeneratedImage／MediaUploadResult／ArticleData bindingが不変 | 本Releaseは生成・upload・binding経路に一切触れない | 既存`test_e2e_v6_14_0_*.py`（Orchestration）・`test_e2e_v6_20_0_*.py`（APPLIED経路）のAPPLIED時アサーションが新規実行でもPASSすること |
| INV-6 | Gate OFF／APPLIED／CONTINUE／PROPAGATE後の記事処理・counter・loopが不変 | `wp_failed_count`加算・`continue`・保存フロー順序は無改修 | 新規E2E`CONTINUE-WP-SUCCESS-`／`CONTINUE-WP-FAILURE-`／`APPLIED-`／`DISABLED-`／`PROPAGATE-`（16.2節）の6経路で、`wp_failed_count`／`wp_success_count`／`wp_skipped_count`の増減とMarkdown保存・次記事への`continue`到達を直接検査する。`NULLLOG-`（16.4節）で`LOG_ENABLED=false`下でも同様に検査する |
| INV-7 | raw secret／exception情報が非記録 | 7章・11章 | 新規E2E`SECRET-FREE-`（16.1節）・既存`test_e2e_v6_20_0_*.py` L734-746 `SEC-NO-EXC-MESSAGE-IN-*`（18章）が、新設`observation`field導入後も引き続きPASSすることを実測確認する |

**main.pyバイト単位無変更（v6.24のZ-3相当）はv6.25では成立しない**ことを明記する。
これはv6.24というRelease時点でZ-3が成立していたという記録を書き換えるものでは
なく、v6.25という別Releaseにおいて`main.py`・`article_featured_media_runtime`
双方に変更が及ぶことにより新たに不成立となるという事実である。

---

## 15. Scope／Out of Scope

### 15.1 Scope（含める）

- DI-5：failure reasonの観測・ログ化
- DEF-3：PROPAGATE時のcategory/action観測の統合
- reason observabilityに必要な最小限のruntime／result／schema変更

### 15.2 Out of Scope

| 項目 | 理由 |
|---|---|
| DI-9（Gate値 strict validation） | 別のRuntime契約変更であり、本Releaseの関心（観測）と独立 |
| s-3／s-7（v6.24.0設計書§19.8の残存Suggestion） | 既存E2Eの重複整理であり、観測機能の完成に不要。将来のテストスイート再実行を伴うReleaseで併せて整理する |
| WordPress側CONTINUE対象拡大（DEF-6.22-1） | action集合を変更する別Policy Release。本Releaseはその判断に必要な運用データを得るための前提ステップに留まる |
| metrics集計・通知・閾値・circuit breaker | Retry Runtime系列の既存Deferred群であり無関係 |
| Publish Composition Root Foundation（DI-8）等の無関係なrefactor | 本Releaseのobservability追加と無関係 |
| `decide_image_generation_fallback()`本体の分類ロジック変更 | INV-1・INV-2により明示的に不変とする |

---

## 16. Test Strategy

### 16.1 新規E2E（想定scenario prefix）

| prefix | 検証内容 |
|---|---|
| `OBSERVATION-` | `FeaturedMediaFailureObservation`のfrozen性・field構成（`category`/`action`/`reason`）・不変条件 |
| `REASONNORM-` | `extract_safe_reason()`のallow-list判定（既知2型のみ`.value`を返す、それ以外は`None`）。7.2節の防御的順序（Architecture Review Major-3対応）に対応し、`.reason`アクセス前に`isinstance(error, _KNOWN_ERROR_TYPES)`を必ず経由することの検証、未知の`Exception`サブクラス（`.reason`属性を持たない、または持つが未知型）に対して属性アクセス自体が発生しない陰性対照を含む |
| `CONTINUE-OBS-` | CONTINUE経路で`decision`が1回のみ評価され、`observation`が正しく`Result`へ格納されること |
| `PROPAGATE-OBS-` | PROPAGATE経路で`classify_propagated_failure()`が正しく`observation`を返すこと。`decide_image_generation_fallback()`の呼び出し回数（apply()内部1回＋本メソッド1回）が設計どおりであること |
| `LOGFIELD-` | `ArticleLogEntry`への3フィールド追加が既存フィールドの型・順序・デフォルト値を変えないこと |
| `SCHEMA-COMPAT-` | 既存consumer（`analytics_manager.py`）が新フィールドを無視して従来どおり動作すること（10.2節の限定：Repository内consumerに対する検証であることを明記） |
| `DEDUP-` | 1記事につき`log_article()`が正確に1回だけ呼ばれること（既存の`continue`による排他性の回帰確認） |
| `SECRET-FREE-` | 新3フィールドの値が常に`str`かつ既知の値のいずれかであり、例外message・prompt・credential等の断片を含まないこと |
| `SEC-NO-STR-EXC`／`SEC-NO-REPR-EXC`／`SEC-NO-TYPENAME-EXC`／`SEC-NO-RAW-EXC-TO-LOGENTRY`／`SEC-NO-EXC-MUTATION`／`SEC-EXC-USAGE-ALLOWLIST` | 17.2節のguard精緻化に対応する新規陽性・陰性対照（Architecture Review Suggestion-2対応。具体化は16.5節参照） |
| `NOIMPACT-` | `image_generation_fallback_policy`の分類テーブル・`_CONTINUABLE_REASONS`・`openai_image_generation`／`wordpress_media`が無改修であることの機械検証 |
| `NULLLOG-` | `LOG_ENABLED=false`時に`NullLogManager.log_article()`が新3引数を受け取ってもno-opのまま`TypeError`を送出しないこと（Architecture Review Major-2対応。9.2節参照） |
| `NOLEAK-` | 前記事の`featured_media_observation`が次記事のログ記録へ漏れないこと（8.4節参照） |

### 16.2 main.py記事ループの経路別E2E（Architecture Review Major-4対応）

8.4節のdata flowに対応し、少なくとも以下6経路をE2Eとして検証する。

| # | シナリオ | 検証内容 |
|---|---|---|
| 1 | `CONTINUE-WP-SUCCESS-` | CONTINUE経路＋WordPress保存成功：`result.observation`が非`None`のまま通常の成功系`log_article()`呼び出しへ`category`/`action`/`reason`が渡ること |
| 2 | `CONTINUE-WP-FAILURE-` | CONTINUE経路＋WordPress保存失敗：同上の値が失敗系`log_article()`呼び出しへも正しく渡ること |
| 3 | `APPLIED-` | APPLIED経路：`result.observation`が`None`のまま、ログの3フィールドが`""`になること |
| 4 | `DISABLED-` | DISABLED経路：同上（`observation`が`None`、ログの3フィールドが`""`） |
| 5 | `PROPAGATE-` | PROPAGATE経路：`classify_propagated_failure()`の戻り値が`_handle_featured_media_failure()`経由でログへ正しく渡ること。既存の`markdown`単独保存・`wp_failed_count`加算・`continue`（run継続）が無変更であること |
| 6 | `NULLLOG-` | `LOG_ENABLED=false`（`NullLogManager`使用）でも上記1〜5のいずれの経路でも`TypeError`が発生しないこと |

### 16.3 Major-3対応：`extract_safe_reason()`の防御的順序に関する陰性対照

`REASONNORM-`の一部として、以下を明示的に検証する：

- 既知2型（`OpenAIImageGenerationError`／`WordPressMediaUploadError`）のいずれでもない任意の`Exception`サブクラスに対し、`.reason`属性へのアクセス自体が発生しないこと（`isinstance`確認が先に行われ、`getattr`到達前にリターンすること）
- `.reason`という名前のpropertyを持ち、そのgetterが例外を送出するテスト専用のダミー例外型を用意し、それが既知2型のいずれでもない場合に`extract_safe_reason()`が例外を伝播させずに`None`を返すこと

### 16.4 Major-2対応：`NullLogManager`のE2E

- `LogManager.log_article()`と`NullLogManager.log_article()`が同一のキーワード引数集合を受け付けることをsignature比較で検証する
- `LOG_ENABLED=false`環境下で16.2節の6経路すべてが正常終了すること

### 16.5 Suggestion-2対応：guard自体の陰性対照

17.2節の6guard（`SEC-NO-STR-EXC`等）それぞれについて、意図的にSEC-2/SEC-3違反を
含む最小fixture（`str(exc)`を出力するmain.py風の断片等）を用いた陽性対照（違反を
正しく検出すること）と、正常な`main.py`実装に対する陰性対照（誤検出しないこと）
の両方をTest Strategyへ含める。

### 16.6 既存Regression

v6.9.0〜v6.24.0の全E2Eファイル（正式Inventory27ファイル・4418アサーション、
Release 6.24.0時点）が引き続きPASSすること。特に18章に列挙する既存guard5件は
本Releaseで確実に更新を要する。

**実測結果（限定回帰、履歴として維持）**：Production Implementation完了後、
v6.19〜v6.25の関連7ファイルを対象に限定回帰を実施し、合計**1792/1792 PASS**を
実測した（内訳：v6.19=273／v6.20=200／v6.21=170／v6.22=324／v6.23=345／
v6.24=352／v6.25=128）。**これは正式Inventory全ファイル全体を対象とする
Formal Regressionではなく、本Releaseが変更した範囲に限定した回帰である。**

**実測結果（Formal Regression、確定）**：`.\venv\Scripts\python.exe`のみを
使用し、正式Inventory**28ファイル**（v1.11.0＋v5.9.0＋v6.0.0〜v6.25.0。
v6.24.0時点の27ファイル＋v6.25.0新規1ファイル）を全件実行し、
合計**4582/4582 PASS**（FAIL 0／SKIP 0、全ファイルexit code 0）を実測した。
うち新規v6.25.0は**128/128 PASS**。旧27ファイル分の実測値は**4454/4454**
（4582−128）であり、Release 6.24.0時点の文書記録値**4418**との差分**+36**は、
限定回帰で既に文書化済みの構造的増分（v6.19 +1／v6.20 +2／v6.21 +23／
v6.22 +0／v6.23 +4／v6.24 +6＝36）と完全に一致する。INV-1〜INV-7・R-5
（`test_e2e_v6_20_0_*.py`のSEC節が`observation`field導入後もPASSすること）は
いずれも本Formal Regression実測で確認済みである。実行後の`git status`は
実行前と完全に同一であり、テスト実行による想定外の差分は生じていない。

### 16.7 テスト実行

**Production Implementation・New E2E・限定回帰（v6.19〜v6.25、1792/1792
PASS）・Formal Regression（正式Inventory28ファイル、4582/4582 PASS）は
いずれも完了している**（0章参照）。残るは人間によるRelease Review・
最終承認・commit・pushであり、これらは本工程（Formal Regression結果の
Documentation最小反映）の対象外である（21.3節参照）。

---

## 17. `LOOP-HANDLER-NO-BINDING` の精緻化方針

### 17.1 本来のsecurity invariant

`tests/test_e2e_v6_21_0_article_featured_media_runtime_wiring.py` L668-675
`LOOP-HANDLER-NO-BINDING`は現在、main.pyのexceptハンドラが例外を変数へ束縛
しないこと（`_handler.name is None`）を検査している。これは`article_featured_media_runtime_wiring.md`
§11 SEC-2／SEC-3（`str(error)`を出力しない・class名を出力しない）の**構造的
保証の一手段**として採用された実装詳細であり、SEC-2／SEC-3そのものの定義
（「`str(error)`／class名をconsole・log・reportへ出力しない」）は「束縛しない
こと」自体を要求していない。

### 17.2 精緻化後のguard（positive allow-list方式）

束縛はするが（`except Exception as exc:`）、SEC-2／SEC-3が禁じる具体的操作が
一切存在しないことを機械検証する、v6.23.0 I-EXC-1・v6.24.0 I-VAL-1と同型の
positive allow-list方式へ転換する：

| guard | 検査内容 |
|---|---|
| `SEC-NO-STR-EXC` | 束縛名（`exc`）に対し`str(exc)`が呼ばれていないこと |
| `SEC-NO-REPR-EXC` | `repr(exc)`が呼ばれていないこと |
| `SEC-NO-TYPENAME-EXC` | `type(exc).__name__`／`exc.__class__.__name__`が参照されていないこと |
| `SEC-NO-RAW-EXC-TO-LOGENTRY` | `exc`自体（オブジェクト）が`ArticleLogEntry(...)`／`log_article(...)`の引数として渡されていないこと |
| `SEC-NO-EXC-MUTATION` | `exc`への属性代入（`setattr(exc, ...)`／`exc.xxx = ...`）が存在しないこと |
| `SEC-EXC-USAGE-ALLOWLIST` | `exc`の唯一の許可された使用形が`classify_propagated_failure(exc)`の引数位置であること（positive allow-list。それ以外の使用を検出したら違反） |

この精緻化は**security保証を弱めない**。従来「束縛なし」という強い構造的制約で
担保していたものを、「束縛はするが、漏洩し得る具体的操作がいずれも存在しない」
という同等以上に精密な機械検証へ置き換える。

---

## 18. 更新が必要な既存guard

実測確認済みの影響一覧：

| ファイル・箇所 | guard | 現状 | 対応 |
|---|---|---|---|
| `test_e2e_v6_20_0_*.py` L372-377 | `RESULT-FIELDS` | field名を`("article","status","category")`と完全一致検査 | 期待値を`("article","status","category","observation")`へ更新 |
| 同 L285-286 | `API-ALL-EXACT`（`article_featured_media_runtime`） | `__all__`3シンボル検査 | 期待値を4シンボル（`FeaturedMediaFailureObservation`追加）へ更新 |
| 同 L1049-1050 | `COMPAT-V619`（`image_generation_fallback_policy.__all__`） | `__all__`不変検査（**実測4シンボル**：`ImageGenerationFailureCategory`／`ImageGenerationFallbackAction`／`ImageGenerationFallbackDecision`／`decide_image_generation_fallback`。`__init__.py` L18-23で確認済み） | 期待値を**5シンボル**（`extract_safe_reason`追加）へ更新（Architecture Review Major-1対応） |
| 同 L378-379 | `RESULT-CATEGORY-DEFAULT-NONE` | `dataclasses.fields(...)[2]`でcategory field取得 | **影響なし**（`observation`は末尾＝インデックス3に追加されるため、既存の`[2]`参照は`category`のまま）。ただし`observation`のデフォルト値検査（インデックス3）を新規追加すべき |
| 同 L734-746 | `SEC-NO-EXC-MESSAGE-IN-*`（repr/str/asdict） | `RATE_LIMIT`reasonを使いCONTINUE経路の秘密非漏洩を実証 | コード変更は不要。新設`observation`fieldの内容（`reason="rate_limit"`）を含めても引き続きPASSすることを実測確認する |
| `test_e2e_v6_21_0_*.py` L668-675 | `LOOP-HANDLER-NO-BINDING` | `_handler.name is None`を検査 | 17章の精緻化guard群へ置換 |
| 同 L601-619 | `GUARD-NO-OTHER-IMAGE-PACKAGE` | main.pyの画像系package参照禁止リスト | **無変更のままPASSする想定**（本設計はこのguardに触れない） |
| 同 L285・L297-302 | `_HANDLER_KWARGS`／呼び出しヘルパー | `_handle_featured_media_failure()`への固定kwargs辞書 | `observation`引数を含む新規テストケースを追加 |
| 同 L275-282 | `run_apply_step_capturing_stdout` | `_apply_featured_media_step()`戻り値を`article`単体として受け取る | 戻り値が`ArticleFeaturedMediaRuntimeResult`になることに伴うテストヘルパー・アサーションの更新 |
| （新規） | `NullLogManager.log_article()`のsignature | 既存guardなし（新規追加が必要） | `LogManager.log_article()`と`NullLogManager.log_article()`が同一キーワード引数集合を受け付けることを検査する新規guardを追加する（Architecture Review Major-2対応。16.4節参照） |

### 18.1 GR-9由来：v6.19・v6.22・v6.23・v6.24の更新（Code Review Major-3対応）

上記に加え、実装工程（Production Implementation）で以下4ファイルの更新が
**必然的に発生した**ことを事後的に記録する。これらはいずれも本Releaseが
`src/image_generation_fallback_policy`（`__init__.py`含む）・
`src/article_featured_media_runtime`（`__init__.py`含む）・`src/logger`へ
正当に触れることに伴い、各Releaseが確立した既存の「GR-9：保護対象パスへ
触れるReleaseは、それ以前に存在するすべてのbaseline固定guardのallow-listを
更新する」という恒久ルールから直接導かれる、当初のArchitecture Design／
Test Reviewでは個別に予見していなかったが正当な変更である。

| ファイル | 更新内容 | 理由 |
|---|---|---|
| `test_e2e_v6_19_0_image_generation_fallback_policy_foundation.py` | `API-ALL-EXACT`を5シンボルへ、`DEP-ISINSTANCE-TARGETS-LIMITED`の許可型集合へ`WordPressMediaUploadErrorReason`を追加 | `extract_safe_reason()`が`image_generation_fallback_policy.__all__`を4→5へ拡張し、かつ新規に`WordPressMediaUploadErrorReason`へのisinstance判定を導入するため |
| `test_e2e_v6_22_0_wordpress_media_upload_failure_reason_classification_foundation.py` | `COMPAT-V619`／`COMPAT-V620`の期待値更新、`_allowed_source_changes`へ3パス追加、`_allowed_test_changes`へ新規v6.25 E2E追加 | 同ファイルが`image_generation_fallback_policy`・`article_featured_media_runtime`両方の`__all__`不変を検査するCOMPAT節と、GR-9のNOIMPACT allow-list機構を持つため |
| `test_e2e_v6_23_0_openai_image_generation_api_rejection_reason_classification_foundation.py` | `COMPAT-POLICY-ALL`の期待値更新、`_allowed_source_changes`へ3パス追加（GR-6のequality検査対象にも含める）、`_allowed_test_changes`へv6.20・v6.25追加 | 同ファイルのGR-6「新Release側はequalityで検証する」方式により、`_allowed_source_changes`の各エントリはcontainmentだけでなくcoverage／equalityも検査されるため、新規3パスを過不足なく登録する必要があった |
| `test_e2e_v6_24_0_openai_image_generation_unknown_and_invalid_response_reason_refinement_foundation.py` | `COMPATAPI-POLICY-ALL`の期待値更新、`POLICYFILE-DIFF-EMPTY`／`POLICYFILE-AST-EQUAL`の縮小（21.1節参照）、`_allowed_source_changes`へ3パス追加、`_allowed_test_changes`へv6.20・v6.25追加 | 同ファイルが`image_generation_fallback_policy`のwhole-file無変更を独自に保証していたため（21.1節でMinor-2として詳述） |

いずれのファイルも変更後、限定回帰（v6.19〜v6.25、合計1792/1792 PASS。
Formal Regressionではない）で実測確認済みである。File Change Plan（20章）へも反映する。

---

## 19. Compatibility

- `ArticleFeaturedMediaRuntimeResult`の既存3field（`article`/`status`/`category`）
  は型・意味・デフォルト値とも無変更。`observation`は末尾optional field。
- `ArticleLogEntry`の既存18fieldは型・順序・デフォルト値とも無変更。新3fieldは
  末尾optional field（デフォルト`""`）。**ただし全記事のJSON Linesキー集合は
  変化する。この後方互換性は「確認済みRepository内consumerに対して」のみ
  保証され、外部・未知のstrict schema consumerには非互換となり得る**（10.2節、
  Architecture Review Suggestion-1対応）。
- `image_generation_fallback_policy`の既存4シンボル（`decide_image_generation_fallback()`・
  `ImageGenerationFailureCategory`・`ImageGenerationFallbackAction`・
  `ImageGenerationFallbackDecision`）は**意味・signatureとも無変更**。ただし
  同packageの公開symbol集合（`__all__`）は`extract_safe_reason`の追加により
  **4→5へ拡張される**（「既存public APIは無変更」ではなく「既存シンボルは
  不変、公開集合は1シンボル追加」と区別する。Architecture Review Major-1対応）。
- `NullLogManager.log_article()`のno-op契約（何も行わない）は無変更。ただし
  受け付ける引数集合は`LogManager.log_article()`と対称に拡張される（9.2節、
  Architecture Review Major-2対応）。
- `main.py`の`GUARD-NO-OTHER-IMAGE-PACKAGE`契約は維持（12章）。

---

## 20. File Change Plan

| ファイル | 変更種別 |
|---|---|
| `src/image_generation_fallback_policy/image_generation_fallback_policy.py` | 変更（追加のみ） |
| `src/image_generation_fallback_policy/__init__.py` | 変更（`__all__`拡張） |
| `src/article_featured_media_runtime/article_featured_media_runtime.py` | 変更（追加のみ） |
| `src/article_featured_media_runtime/__init__.py` | 変更（`__all__`拡張） |
| `src/logger/log_entry.py` | 変更（追加のみ） |
| `src/logger/log_manager.py` | 変更（追加のみ） |
| `main.py` | 変更（except節束縛化・helper戻り値／シグネチャ拡張） |
| `tests/test_e2e_v6_20_0_article_featured_media_runtime_foundation.py` | 変更（`RESULT-FIELDS`／`API-ALL-EXACT`更新） |
| `tests/test_e2e_v6_20_0_*.py`（`COMPAT-V619`該当箇所） | 変更（期待値更新） |
| `tests/test_e2e_v6_21_0_article_featured_media_runtime_wiring.py` | 変更（`LOOP-HANDLER-NO-BINDING`精緻化・helper呼び出し更新・`MDOK-OBS-`追加。Code Review Major-2対応） |
| `tests/test_e2e_v6_19_0_image_generation_fallback_policy_foundation.py` | 変更（GR-9対応、18.1節参照。Code Review Major-3対応） |
| `tests/test_e2e_v6_22_0_wordpress_media_upload_failure_reason_classification_foundation.py` | 変更（GR-9対応、18.1節参照。Code Review Major-3対応） |
| `tests/test_e2e_v6_23_0_openai_image_generation_api_rejection_reason_classification_foundation.py` | 変更（GR-9対応、18.1節参照。Code Review Major-3対応） |
| `tests/test_e2e_v6_24_0_openai_image_generation_unknown_and_invalid_response_reason_refinement_foundation.py` | 変更（GR-9対応・`POLICYFILE-*`guard縮小、18.1節・21.1節参照。Code Review Major-3・Minor-2対応） |
| `tests/test_e2e_v6_25_0_*.py`（新規） | 新規作成（16.1〜16.5節の新規scenario prefix、`NullLogManager`signature検査・防御的順序陰性対照に加え、`main.main()`をmonkeypatchのうえ実行するbehavioral E2E（Code Review Major-1対応）・SEC guard6件の陽性/陰性対照＋実main.py cross-check（Minor-1対応）を含む） |
| `docs/ROADMAP.md`／`docs/CHANGELOG.md`／`docs/architecture.md` | 変更（Documentation Integrationで実施済み。Release 6.25.0の反映内容・限定回帰・Formal Regression結果を記録） |

**本節はArchitecture Design時点では「将来の実行予定」として記録されたが、
現時点（Release Review後）ではすべて実行済みである。** Production
Implementation・Documentation Integrationはいずれも完了しており、上記
File Change Planに列挙した全ファイルが実際に変更されている。本設計書
自身も本節を含め複数回改訂されている（Design doc最終整合・Formal
Regression結果反映・Release Review Minor-1対応など）。

**確定したcommit対象Inventoryは以下の18ファイルである**（Formal
Regression完了時点の`git status`実測、0章参照）。

- 変更（modified）16件：Production 7件（`main.py`・`src/image_generation_fallback_policy/`2件・
  `src/article_featured_media_runtime/`2件・`src/logger/`2件）＋既存tests 6件
  （v6.19／v6.20／v6.21／v6.22／v6.23／v6.24）＋docs 3件（`ROADMAP.md`／
  `CHANGELOG.md`／`architecture.md`）
- 新規（untracked）2件：本設計書・`tests/test_e2e_v6_25_0_*.py`

**Release Review（Approved with Suggestions、Blocking 0／Major 0／Minor 1／
Suggestion 2）で検出したMinor-1（本節が「design doc 1件のみ変更」「ROADMAP等は
未変更」「将来実施予定」という陳腐化した記述のまま据え置かれ、実態と矛盾していた
点）は、本改訂で本節を現状へ更新し解消した。** Suggestion 2件（S-1：
`_ScenarioRuntime`のobservation構築式重複、S-2：GR-9 allow-list更新の5ファイル
波及）はいずれも非ブロッキングのままDeferredとする。

---

## 21. リスク・Deferred

**Architecture Review（1回目）で検出されたMajor 4件・Minor 2件・Suggestion 2件は、
本改訂（最小改訂）で以下のとおり反映済みである。**

| # | 内容 | 分類 | 本改訂での対応状況 |
|---|---|---|---|
| R-1 | `classify_propagated_failure()`という新規publicメソッド追加が、v6.20/v6.21で確立された「Facadeの責務は`apply()`のみ」という設計思想を拡張することの是非 | Architecture Reviewでの人間判断事項 | **未解消**（設計方針自体は12章のとおり。人間の最終承認が必要） |
| R-2 | `image_generation_fallback_policy.__all__`の4→5拡張が、同packageの「fallback判断ロジックのみを扱う」という既存の責務範囲説明（docstring）との整合 | Production Implementation時にdocstring更新を要する | **数値誤記のみ訂正済み**（Major-1対応、7.1節・9章・18章）。docstring更新自体はProduction Implementation時に実施 |
| R-3 | `17章`のguard精緻化の具体的AST実装方針 | Test Review対象 | **未解消**（Test Review対象のまま。16.5節でguard自体の陰性対照を追加） |
| R-4 | JSON Linesのキー集合変化が、将来追加されうる厳密schema検証consumerやsnapshot比較ツールに与える影響 | 現時点では該当consumer不在（10.2節で確認済み）。将来のconsumer追加時に再評価 | **限定表現へ修正済み**（Suggestion-1対応、10.2節・19章） |
| R-5 | `test_e2e_v6_20_0_*.py` SEC節（L734-746）が新設`observation`field導入後も実際にPASSすることの実測確認 | Production実装前Gate確認で実施 | **未解消**（実測はProduction実装前Gate確認で実施） |
| R-6（新規） | `extract_safe_reason()`の防御的順序（`isinstance`確認→`.reason`取得）が実装時に正しく維持されるか | Test Review対象（Major-3対応） | 7.2節へ実装方針を反映済み。実装後のAST/挙動検証はTest Review・Production実装前Gate確認で実施 |
| R-7（新規） | `NullLogManager.log_article()`のsignature拡張漏れがProduction Implementation時に再発しないか | Test Review対象（Major-2対応） | 9.2節・18章へ変更対象として明記済み。新規guard（18章「（新規）」行）で機械検証する |
| R-8（新規） | main.py記事ループの`observation`初期化・伝播の擬似コード（8.4節）が、実装時に厳密に踏襲されるか | Production Implementation時の確認事項（Major-4対応） | 8.4節へ具体的擬似コードを追加済み。実装後は16.2節の6経路E2Eで検証 |
| D-1（Deferred） | reason allow-listの拡張（将来Providerが追加された場合の対応方針） | 将来Release。本Releaseの2 Reason Enum型限定は現行Provider構成（OpenAI／WordPress）を前提とする | 変更なし |
| D-2（Deferred） | WordPress側CONTINUE対象拡大（DEF-6.22-1）の正式再評価 | 本Release完了後、運用データが蓄積された時点で人間が判断する | 変更なし |
| D-3（Deferred、新規） | JSON Linesのschema version導入（`schema_version`フィールド等）による外部consumer互換性の明示的な保証 | 将来Release。外部・未知consumerとの互換性が実運用上の課題として顕在化した場合に独立検討する（Suggestion-1対応） | 新規追加 |

### 21.1 v6.24 `POLICYFILE-*`guardの縮小とその根拠（Code Review Minor-2対応）

`test_e2e_v6_24_0_*.py`は元々、`image_generation_fallback_policy.py`が
baselineからwhole-fileで無変更（`POLICYFILE-DIFF-EMPTY`：diffが空・
`POLICYFILE-AST-EQUAL`：ファイル全体のAST等価）であることを保証していた。
本Release（v6.25.0）は`extract_safe_reason()`追加のため同ファイルへ
正当に変更を加えるので、このwhole-file保証は維持できない。

**縮小内容**：
- `POLICYFILE-DIFF-EMPTY`：差分が完全に空であることの検査から、差分が
  `image_generation_fallback_policy.py`・`__init__.py`の2ファイルのみに
  限定される（allow-list containment）検査へ変更した。
- `POLICYFILE-AST-EQUAL`：whole-file AST等価から、
  `decide_image_generation_fallback()`関数**単体**のAST等価検査へ縮小した
  （v6.23／v6.24が`_classify_api_error()`に対して既に採用している
  関数スコープAST等価という既存precedentと同型）。

**縮小によって保護対象外になった要素と、代替guardによる残存保証**：

| 保護対象外になった要素 | 代替guardによる保証 |
|---|---|
| `_ACTION_BY_CATEGORY`（category→action写像） | v6.25新規`NOIMPACT-ACTION-BY-CATEGORY`が実値の完全一致を検査 |
| `_CONTINUABLE_REASONS`（CONTINUE対象4値） | v6.25新規`NOIMPACT-CONTINUABLE-REASONS`が実値の完全一致を検査 |
| Enum定義数・`ImageGenerationFallbackDecision`のfield構成 | v6.23の`COMPAT-CATEGORY-5`／`COMPAT-ACTION-2`／`COMPAT-DECISION-FIELDS`が別途保証 |
| 分類ロジック全体の入出力対応表 | v6.19の全reason網羅テスト（273 assertion）が別途保証 |

したがって、本縮小は「保証を弱める」ものではなく、「whole-fileという広すぎる
検査単位を、実際に変更されない核心部分（分類ロジック本体）へ絞り込み、
広く失われた分を複数の既存guardの組み合わせで代替的にカバーする」という
再配分であることを確認した。Code Review（Codex＋Claude照合）で、この
代替カバレッジが実際に機能していることを限定回帰で実測確認済み（1792/1792 PASS。
Formal Regressionではない）。

### 21.2 Code Review指摘の解消状況

| ID | 内容 | 解消内容 |
|---|---|---|
| Major-1 | Design §16.2のbehavioral E2E（INV-6の主証拠）が未実装だった | `tests/test_e2e_v6_25_0_*.py`へ`RUNTIME-E2E-`セクションを新設。`main.main()`を全依存monkeypatchのうえ実行し、CONTINUE-WP-SUCCESS／CONTINUE-WP-FAILURE／APPLIED／DISABLED／PROPAGATE／NULLLOGの6経路をcounter（`ExecutionLogEntry`経由）・Markdown保存回数・loop継続・observation内容・記事間NOLEAKを含めbehavioralに検証する（16.2節） |
| Major-2 | `_handle_featured_media_failure()`のobservation非None経路がv6.21でbehavioral検証されていなかった | `tests/test_e2e_v6_21_0_*.py`へ`MDOK-OBS-`セクションを追加し、category/action/reasonが`log_article()`へ正しく渡ることと、observation省略時（`None`）は引き続き3フィールドとも`""`になることを検証 |
| Major-3 | GR-9由来のv6.19/v6.22/v6.23/v6.24更新が設計書に記録されていなかった | 18.1節へ4ファイルの更新内容と理由を追記、20章File Change Planへ反映 |
| Minor-1 | SEC guard6件中1件のみ自己検証されていた | `tests/test_e2e_v6_25_0_*.py`のSEC-GUARD節を6guard全件の陽性・陰性対照へ拡張し、さらに実main.pyへのcross-check（v6.21.0本体guardとの相互検証）を追加 |
| Minor-2 | v6.24 `POLICYFILE-*`guard縮小の根拠が未記録だった | 本節（21.1節）へ縮小内容・代替guardによる残存保証を記録 |

Suggestion 5件（S-1〜S-5）は本改訂では対応しない（次にtestsへ触れるReleaseで
併合検討する）。

### 21.3 Code Review 2（Closure Review）の結果と反映

Code Review 1で反映したMajor-1〜3・Minor-1〜2（21.2節）を対象に、Code Review 2
（Codex＋Claude照合によるclosure review）を実施し、**Verdict：Approved with
Suggestions（Blocking 0／Major 0／Minor 1／Suggestion 5）**を得た。Major-1〜3・
Minor-1〜2はいずれも実装・design doc記述ともにClosedと確認された。

**新規Minor（本節で解消）**：本設計書§0の状態記述（プローズ部分）および
§16.7が、Production Implementation・限定回帰の完了後も「Production Code・
testsはいずれも無変更」「本工程ではテストを一切実行していない」という
Architecture Design段階の記述のまま据え置かれ、§0の状態テーブル（Production
Implementation: Completed等）と矛盾していた。**本改訂（Design doc最終整合＋
Documentation Integration）で§0・§16.7の記述を現状へ更新し解消した。**

Suggestion 5件（S-1〜S-5）はCode Review 2でも非ブロッキングのまま据え置かれ、
**Deferredとして維持する**（次にtestsへ触れるReleaseで併合検討する。21.2節と
同じ扱い）。

**限定回帰とFormal Regressionの区別（本節で明記、履歴として維持）**：本Releaseを
通じて実測した1792/1792 PASSは、v6.19〜v6.25の関連ファイルのみを対象とした
**限定回帰**であり、**正式Inventory全ファイルを対象とするFormal Regressionでは
ない**。本節記載の時点ではFormal Regressionは未実施であったが、その後
21.4節のとおり実施しPASSした。

### 21.4 Formal Regression（確定結果）

Design doc最終整合＋Documentation Integration完了後、`.\venv\Scripts\python.exe`
のみを使用して正式Inventory**28ファイル**（v1.11.0＋v5.9.0＋v6.0.0〜v6.25.0）を
全件実行し、以下を確定した。

- **合計4582/4582 PASS、FAIL 0、SKIP 0、全28ファイルexit code 0**
- 新規v6.25.0：**128/128 PASS**
- 旧27ファイル分：**4454/4454 PASS**（4582−128）。Release 6.24.0時点の
  文書記録値4418との差分+36は、限定回帰で文書化済みの構造的増分
  （v6.19 +1／v6.20 +2／v6.21 +23／v6.22 +0／v6.23 +4／v6.24 +6＝36）と一致
- **INV-1〜INV-7・R-5（`test_e2e_v6_20_0_*.py`のSEC節）はいずれも確認済み**
- テスト実行後の`git status`は実行前と完全に同一。想定外の差分なし
- Production Code・testsは本Formal Regression工程・本Documentation最小反映
  工程のいずれでも変更していない

**限定回帰（1792/1792）とFormal Regression（4582/4582）はいずれも実施した
異なる工程の記録として、両方とも履歴に残す。** 残る未完了事項は人間による
Release Review・最終承認・commit・pushのみである（0章参照）。

---

## 22. Architecture Review／Implementation Gate 条件

Architecture Reviewでの承認を経て次工程（Production Implementation）へ進む
ための必須確認事項：

- [ ] `FeaturedMediaFailureObservation`・`extract_safe_reason()`の配置・依存方向（6章・7.1節）が妥当と承認されること
- [ ] `classify_propagated_failure()`によるFacade責務拡大（12章）が承認されること
- [ ] `17章`のguard精緻化方針（positive allow-list化）がsecurity保証を弱めないと承認されること
- [ ] `18章`に列挙した既存guard5件の更新方針が承認されること
- [ ] JSON Linesスキーマ変更（10章）の後方互換性評価が承認されること
- [ ] `14章`の個別不変条件（INV-1〜INV-7）およびmain.pyバイト単位無変更の不成立が承認されること
- [ ] Test Strategy（16章）が新規E2E・既存Regressionの両面で十分と判断されること

Production Implementation開始前に、Architecture Review・Test Review（17章guard
精緻化のAST実装方針を含む）を完了させることを必須Gateとする。

---

## 23. 参照

- `docs/ROADMAP.md`（DI-5・DI-9・DEF-6.22-1・DEF-6.23-2・v6.9.0〜v6.24.0 Entry群）
- `docs/CHANGELOG.md`（`[v6.24.0]`Entry、Deferred一覧）
- `docs/architecture.md`（DI-5・DI-6〜DI-9関連記述）
- `docs/design/image_generation_fallback_policy_foundation.md`（v6.19.0、§18.1観測契約 O-1〜O-7）
- `docs/design/article_featured_media_runtime_wiring.md`（v6.21.0、§19 DEF-3、§11 SEC-2／SEC-3）
- `docs/design/article_featured_media_composition_root_foundation.md`（v6.18.0、DI-5の想定実装先の記述）
- `docs/design/openai_image_generation_unknown_and_invalid_response_reason_refinement_foundation.md`（v6.24.0、§2.2 D-3、Z-1〜Z-8定義、§19.8 Suggestion s-1〜s-7）
- `src/image_generation_fallback_policy/image_generation_fallback_policy.py`
- `src/article_featured_media_runtime/article_featured_media_runtime.py`
- `src/logger/log_entry.py`／`src/logger/log_manager.py`
- `main.py`
- `tests/test_e2e_v6_20_0_article_featured_media_runtime_foundation.py`
- `tests/test_e2e_v6_21_0_article_featured_media_runtime_wiring.py`
