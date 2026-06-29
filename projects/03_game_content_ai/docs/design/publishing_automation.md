# v1.7.0 Publishing Automation 設計書

作成日：2026-06-30
対象バージョン：v1.7.0
対象 Epic：Release 1.1 — Epic 1 Publishing Automation
ステータス：Draft（設計フェーズ）

---

## 1. Goal

WordPress 投稿時の公開ステータスを、ニュース重要度・設定値に応じて制御できるようにする。

現在（v1.6.0）は全記事が `status: "draft"` のハードコードになっており、重要度による制御ができない。
v1.7.0 では、重要度ごとの投稿ステータス（`draft` / `pending`）を `.env` で設定可能にし、
将来の予約投稿・自動公開への拡張基盤を整備する。

---

## 2. Background

### 現状の問題点

```python
# src/outputs/wordpress_output.py（v1.6.0 時点）
payload = {
    "title": article.seo_title,
    "content": article.article_body,
    "status": "draft",   # ← 全記事がこの1行でハードコードされている
    ...
}
```

- 重要度 S（PS6・Nintendo Switch 後継機など）でも、重要度 A の通常記事でも、同じ `draft` になる
- 「S評価記事はすぐ確認したい」「A評価は後でまとめて確認」といった運用分けができない
- WordPress の `pending`（レビュー待ち）機能を活かせていない

### v1.7.0 が解決すること

| Before（v1.6.0） | After（v1.7.0） |
|-----------------|----------------|
| 全記事が `draft` 固定 | 重要度別にステータスを `.env` で設定可能 |
| 設定変更にはコード修正が必要 | `.env` 1行の変更で動作が変わる |
| 将来の予約投稿への拡張が困難 | 拡張ポイントが明確に設計されている |

---

## 3. Scope

v1.7.0 で実装する範囲。

### 実装対象

| 対象 | 内容 |
|------|------|
| `src/publishing_config.py` | 新規作成。`PublishingConfig` dataclass と `resolve_status()` を実装 |
| `src/outputs/base.py` | `ArticleData` に `publish_status: str = "draft"` フィールドを追加 |
| `src/outputs/wordpress_output.py` | `"status": "draft"` のハードコードを `article.publish_status` に置換 |
| `main.py` | `PublishingConfig.from_env()` の呼び出しと `resolve_status()` の連携 |
| `.env.example` | `PUBLISH_STATUS_S` / `PUBLISH_STATUS_A` の設定例を追加 |

### 許可するステータス値（v1.7.0）

| 値 | WordPress での意味 |
|----|--------------------|
| `draft` | 下書き（デフォルト、Release 1.0 と同じ動作） |
| `pending` | レビュー待ち（編集者がワンクリックで公開できる状態） |

---

## 4. Non Goal

v1.7.0 では実装しないこと。

| 項目 | 理由 |
|------|------|
| `status: "publish"` による即時自動公開 | 誤公開リスクが高い。Release 2.0 以降で設計 |
| `status: "future"` による予約投稿 | `date` パラメータ計算が必要。v1.7.0 では拡張設計のみ |
| 公開スケジュールの自動計算 | 上記と同様 |
| SNS 自動投稿 | Release 1.1 Epic 3（v1.9.0）の対象 |
| Google Analytics / Search Console 連携 | Release 1.1 Epic 4（v1.10.0）の対象 |
| WordPress 以外への投稿 | スコープ外 |

---

## 5. User Workflow

### Before（v1.6.0）

```
1. main.py を実行する
2. 全記事が WordPress の「下書き」として保存される
3. WordPress 管理画面を開き、記事を1件ずつ確認する
4. 公開したい記事の「ステータス」を手動で変更して公開する
   ─ 重要なS評価記事も、通常のA評価記事も、同じ手順を踏む必要がある
```

### After（v1.7.0）

```
1. .env に設定を行う
   PUBLISH_STATUS_S=pending   ← S評価記事はレビュー待ちにする
   PUBLISH_STATUS_A=draft     ← A評価記事は従来通り下書き

2. main.py を実行する
   → S評価記事 → WordPress の「レビュー待ち」として投稿（ダッシュボードに通知が出る）
   → A評価記事 → WordPress の「下書き」として投稿

3. WordPress 管理画面を開く
   → 「レビュー待ち」欄にS評価記事が並んでいる
   → 記事を確認し、「公開」ボタンをクリックするだけで公開完了

メリット：
  - S評価の重要記事が一目でわかる
  - 「公開」ボタン1回で済む（ステータス変更 + 公開が不要）
  - A評価記事は従来通りゆっくり確認できる
```

---

## 6. System Workflow

```
main.py
  │
  ├─ 起動時
  │    └─ PublishingConfig.from_env()
  │         └─ PUBLISH_STATUS_S, PUBLISH_STATUS_A を読み込む
  │              └─ 許可値以外は "draft" にフォールバック（安全設計）
  │
  └─ 記事ループ（各記事について）
       │
       ├─ generate_article() / generate_seo_title() / generate_x_post()
       │
       ├─ config.resolve_status(importance: str) → publish_status: str
       │    ├─ "S" → config.status_s（例: "pending"）
       │    ├─ "A" → config.status_a（例: "draft"）
       │    └─ それ以外 → "draft"
       │
       ├─ ArticleData(
       │    ...
       │    publish_status = publish_status,   ← v1.7.0 追加
       │  )
       │
       └─ OutputManager.save_all(article)
            └─ WordPressOutput.save(article)
                 └─ payload["status"] = article.publish_status   ← v1.7.0 変更
```

---

## 7. Module Design

### 新規モジュール：`src/publishing_config.py`

```python
"""
投稿ステータスを重要度に応じて解決するモジュール。

v1.7.0: draft / pending をサポート。
将来（v1.x.0）: future + date による予約投稿に対応予定。
"""
import os
from dataclasses import dataclass

ALLOWED_STATUSES = {"draft", "pending"}


@dataclass
class PublishingConfig:
    """
    投稿ステータス設定。.env から読み込む。
    未設定の場合はすべて "draft"（Release 1.0 互換）。
    """
    status_s: str = "draft"   # S評価記事の投稿ステータス
    status_a: str = "draft"   # A評価記事の投稿ステータス

    @classmethod
    def from_env(cls) -> "PublishingConfig":
        """環境変数から設定を読み込む。許可値以外は "draft" にフォールバック。"""
        raw_s = os.getenv("PUBLISH_STATUS_S", "draft").lower().strip()
        raw_a = os.getenv("PUBLISH_STATUS_A", "draft").lower().strip()

        status_s = raw_s if raw_s in ALLOWED_STATUSES else "draft"
        status_a = raw_a if raw_a in ALLOWED_STATUSES else "draft"

        if raw_s not in ALLOWED_STATUSES:
            print(f"  [警告] PUBLISH_STATUS_S='{raw_s}' は無効です。'draft' を使用します。")
        if raw_a not in ALLOWED_STATUSES:
            print(f"  [警告] PUBLISH_STATUS_A='{raw_a}' は無効です。'draft' を使用します。")

        return cls(status_s=status_s, status_a=status_a)

    def resolve_status(self, importance: str) -> str:
        """
        重要度から投稿ステータスを解決する。

        Args:
            importance: "S" / "A" / "B"

        Returns:
            str: WordPress に送る status 値（"draft" または "pending"）
        """
        if importance == "S":
            return self.status_s
        if importance == "A":
            return self.status_a
        return "draft"
```

### 変更モジュール：`src/outputs/base.py`（`ArticleData`）

```python
@dataclass
class ArticleData:
    ...（既存フィールド）
    publish_status: str = "draft"   # WordPress 投稿ステータス（v1.7.0 追加）
```

### 変更モジュール：`src/outputs/wordpress_output.py`

```python
# Before（v1.6.0）
payload = {
    ...
    "status": "draft",                   # ← ハードコード
    ...
}

# After（v1.7.0）
payload = {
    ...
    "status": article.publish_status,    # ← ArticleData から取得
    ...
}
```

### 変更モジュール：`main.py`

```python
# 起動時に1回だけ初期化（api_key 取得直後）
publishing_config = PublishingConfig.from_env()

# 記事ループ内（excerpt / slug / featured_image 生成の後）
publish_status = publishing_config.resolve_status(importance)
article = ArticleData(
    ...
    publish_status=publish_status,   # v1.7.0 追加
)
```

---

## 8. Data Model

### `PublishingConfig` dataclass

| フィールド | 型 | デフォルト | 意味 |
|-----------|-----|-----------|------|
| `status_s` | `str` | `"draft"` | S評価記事の WordPress 投稿ステータス |
| `status_a` | `str` | `"draft"` | A評価記事の WordPress 投稿ステータス |

### `ArticleData` への追加フィールド

| フィールド | 型 | デフォルト | 意味 |
|-----------|-----|-----------|------|
| `publish_status` | `str` | `"draft"` | WordPress に送る `status` 値 |

### WordPress 投稿ステータス対応表（v1.7.0 対応範囲）

| `status` 値 | WordPress の挙動 | v1.7.0 |
|------------|-----------------|--------|
| `draft` | 下書きとして保存 | ✅ 対応 |
| `pending` | レビュー待ちキューに追加 | ✅ 対応 |
| `future` | 指定日時に自動公開 | ❌ 将来実装（`date` パラメータが必要） |
| `publish` | 即時公開 | ❌ 非対応（誤公開リスク回避） |

---

## 9. Directory Structure

```
projects/03_game_content_ai/
├── main.py                          ← MODIFIED（PublishingConfig 連携）
├── .env.example                     ← MODIFIED（PUBLISH_STATUS_S/A を追加）
├── docs/
│   └── design/
│       └── publishing_automation.md ← この設計書（NEW）
└── src/
    ├── publishing_config.py         ← NEW（PublishingConfig dataclass）
    ├── image_resolver.py
    ├── slug_generator.py
    ├── image_extractor.py
    ├── collector.py
    ├── keyword_filter.py
    ├── duplicate_filter.py
    ├── importance_judge.py
    ├── article_generator.py
    ├── seo_title_generator.py
    ├── x_post_generator.py
    └── outputs/
        ├── base.py                  ← MODIFIED（publish_status フィールド追加）
        ├── wordpress_output.py      ← MODIFIED（"status" ハードコード削除）
        ├── markdown_output.py       （変更なし）
        ├── manager.py               （変更なし）
        ├── taxonomy_config.py       （変更なし）
        └── __init__.py              （変更なし）
```

---

## 10. Configuration Design

### `.env.example` への追記内容

```bash
# ─────────────────────────────────────────
# Publishing Automation（v1.7.0 追加）
# ─────────────────────────────────────────
# 重要度ごとの WordPress 投稿ステータスを設定します。
# 選択肢: draft（下書き） | pending（レビュー待ち）
# 未設定・無効値の場合はすべて draft として動作します（Release 1.0 と同じ）。
#
# 設定例（S評価をレビュー待ちにする場合）:
#   PUBLISH_STATUS_S=pending
#   PUBLISH_STATUS_A=draft
PUBLISH_STATUS_S=draft
PUBLISH_STATUS_A=draft
```

### Configuration First の設計意図

| 設定パターン | 動作 | ユースケース |
|-------------|------|-------------|
| 未設定（デフォルト） | 全記事 `draft` | Release 1.0 と完全互換 |
| `PUBLISH_STATUS_S=pending` | S→レビュー待ち / A→下書き | S評価を優先確認したいとき |
| `PUBLISH_STATUS_S=pending` `PUBLISH_STATUS_A=pending` | 全記事レビュー待ち | 全記事を必ず確認してから公開するとき |
| 許可値以外（例: `publish`） | `draft` にフォールバック（警告あり） | 設定ミスからの保護 |

---

## 11. WordPress Integration

### REST API payload の変更

変更箇所は `src/outputs/wordpress_output.py` の1行のみ。

```python
# v1.6.0（変更前）
payload = {
    "title": article.seo_title,
    "content": article.article_body,
    "status": "draft",                # ← ハードコード（削除）
    "excerpt": article.excerpt,
    "slug": article.slug,
}

# v1.7.0（変更後）
payload = {
    "title": article.seo_title,
    "content": article.article_body,
    "status": article.publish_status, # ← ArticleData から取得
    "excerpt": article.excerpt,
    "slug": article.slug,
}
```

### コンソールログへの追記

`WordPressOutput.save()` 内のログに `publish_status` を追加する。

```python
print(f"      投稿ID  : {post_id}")
print(f"      slug    : {actual_slug}")
print(f"      ステータス: {article.publish_status}")   # ← v1.7.0 追加
print(f"      編集URL : {edit_url}")
```

### WordPress `pending` ステータスの挙動

- 投稿は「レビュー待ち」として保存される
- 一般公開はされない（`draft` と同様に非公開）
- WordPress 管理画面の「レビュー待ち」リストに表示される
- 「公開」ボタン1クリックで即座に公開可能
- 誤公開リスクが `draft` と変わらない（人間の操作が必要）

---

## 12. Error Handling

### 設定値エラー

| ケース | 挙動 |
|--------|------|
| `PUBLISH_STATUS_S` 未設定 | `"draft"` として動作（サイレント） |
| `PUBLISH_STATUS_S=publish` など許可値以外 | `"draft"` にフォールバック + 警告メッセージをコンソールに出力 |
| 空文字 `PUBLISH_STATUS_S=` | `"draft"` にフォールバック |

### WordPress API エラー

- `status=pending` 送信時に WordPress が拒否した場合は、既存の `RuntimeError` 処理に委ねる
- `WordPressOutput` は `status` 値の WordPress 側での有効性を事前チェックしない
  （WordPress は無効な `status` 値の場合 400 エラーを返す）

---

## 13. Logging との関係

v1.8.0（Logging Epic）との設計上の整合性。

### v1.7.0 時点での対応

- 既存の `print()` ベースのコンソールログに `publish_status` の値を追記する
- `投稿ステータス: pending` などの形式で出力する

### v1.8.0 への引き継ぎ内容

v1.8.0 の Logging 実装時に、以下をログに記録する設計とする。

| ログ項目 | v1.7.0 | v1.8.0 |
|---------|--------|--------|
| publish_status | コンソール出力のみ | ログファイルに記録 |
| 設定値（PUBLISH_STATUS_S/A） | 警告時のみコンソール | 起動時にログ記録 |
| 投稿ステータスの変更履歴 | 未対応 | 投稿 ID + status をログ記録 |

---

## 14. Future Extensions

### Phase 2：予約投稿（`status: "future"`）

WordPress の予約投稿機能を使う場合、`date` パラメータが必要。

```python
# 将来の実装イメージ
payload["status"] = "future"
payload["date"] = "2026-07-01T09:00:00"  # サイトのタイムゾーンで指定
```

追加が必要な要素：

| 要素 | 内容 |
|------|------|
| `PUBLISH_SCHEDULE_TIME` | 予約投稿の時刻（例: `09:00`）|
| `PUBLISH_SCHEDULE_OFFSET_DAYS` | 何日後か（例: `1` = 翌日） |
| `ScheduleResolver` | `(config, now) -> datetime` を計算するクラス |
| `ArticleData.scheduled_at` | ISO 8601 形式の予約日時（空文字 = 予約なし） |

この拡張は `PublishingConfig` に `schedule_time` / `schedule_offset_days` フィールドを追加し、`ScheduleResolver` を別モジュールとして実装することで対応できる。

### Phase 3：承認ゲート付き自動公開（Release 2.0）

```
main.py 実行
  → 記事生成
  → pending 投稿（WordPress）
  → Slack / Discord に通知（「確認してください」）
  → 人間が承認
  → 自動公開
```

---

## 15. Definition of Done

v1.7.0 実装完了の判定基準。

### コード

- [ ] `src/publishing_config.py` 新規作成
  - [ ] `PublishingConfig` dataclass（`status_s`, `status_a` フィールド）
  - [ ] `from_env()` classmethod（許可値以外は `"draft"` にフォールバック）
  - [ ] `resolve_status(importance: str) -> str` メソッド
  - [ ] 不正値入力時の警告メッセージ出力
- [ ] `src/outputs/base.py`
  - [ ] `ArticleData.publish_status: str = "draft"` 追加
- [ ] `src/outputs/wordpress_output.py`
  - [ ] `"status": "draft"` のハードコードを `"status": article.publish_status` に変更
  - [ ] コンソールログに `publish_status` の値を追加
- [ ] `main.py`
  - [ ] `from publishing_config import PublishingConfig` 追加
  - [ ] `publishing_config = PublishingConfig.from_env()` を起動時に1回呼び出す
  - [ ] 記事ループ内で `publish_status = publishing_config.resolve_status(importance)` を呼ぶ
  - [ ] `ArticleData(..., publish_status=publish_status)` に設定
- [ ] `.env.example`
  - [ ] `PUBLISH_STATUS_S=draft` / `PUBLISH_STATUS_A=draft` を追記

### テスト

- [ ] E2E テスト①：`PUBLISH_STATUS_S=draft`（デフォルト）
  - WordPress API で `featured_status == "draft"` を確認
  - Release 1.0 互換確認
- [ ] E2E テスト②：`PUBLISH_STATUS_S=pending`
  - WordPress API で該当投稿の `status == "pending"` を確認
- [ ] E2E テスト③：`PUBLISH_STATUS_S=publish`（不正値）
  - コンソールに警告が出力される
  - WordPress には `"status": "draft"` が送信される
- [ ] API 呼び出し回数変化なし（1記事あたり 3回）

### ドキュメント

- [ ] `docs/CHANGELOG.md` に v1.7.0 エントリーを追加
- [ ] `docs/ROADMAP.md` の v1.7.0 を完了マークに更新
- [ ] `docs/architecture.md` に `publishing_config.py` と `publish_status` フィールドを追記
- [ ] `README.md` に v1.7.0 機能を追記

### リリース

- [ ] git commit 完了
- [ ] git push 完了
- [ ] working tree clean
- [ ] API 呼び出し回数変化なし
- [ ] Release 1.0 互換維持（`PUBLISH_STATUS_S=draft` 時に動作変化なし）
