# 03 ゲームニュース記事生成AI

国内外のゲームニュースをRSSで自動収集し、Claude AIが重要度を判定・日本語記事下書き・SEOタイトル・X投稿文を生成して、Markdownファイルとして保存するツールです。

**ブログ名**：KAORUの部屋  
**ステータス**：v1.7.0 Publishing Automation Foundation（Release 1.1 開始）

---

## 実装済み機能

### v1.7.0 — Publishing Automation Foundation（2026-06-30 完了）★ Release 1.1

- **投稿ステータスの重要度別制御**（v1.7.0 追加）
  - `.env` の `PUBLISH_STATUS_S` / `PUBLISH_STATUS_A` で重要度ごとの WordPress 投稿ステータスを設定
  - `draft`（下書き）または `pending`（レビュー待ち）を選択可能
  - 未設定・不正値の場合は自動的に `draft` にフォールバック（Release 1.0 と同じ動作）
  - `pending` を設定すると WordPress 管理画面から「公開」ボタン1クリックで公開可能
- **`PublishStatus` Enum**（v1.7.0 追加）
  - タイプミス防止のため文字列ではなく Enum で管理
  - `DRAFT` / `PENDING` / `FUTURE` / `PUBLISH` の4値（`FUTURE` / `PUBLISH` は将来実装予定）
- **Validation 付き設定読み込み**（v1.7.0 追加）
  - 許可値外の設定値は WARNING ログを出力し `draft` に安全にフォールバック

### v1.6.0 — Image Pipeline（2026-06-30 完了）

- **デフォルトアイキャッチ画像の自動設定**（v1.6.0 追加）
  - WordPress メディアライブラリにアップロード済みの画像を `DEFAULT_MEDIA_ID` で指定
  - `.env` に `DEFAULT_MEDIA_ID=12345` を設定するだけで全記事に同じアイキャッチを自動設定
  - `0`（未設定）の場合はアイキャッチなしで投稿（v1.5.0 以前と同じ動作）
  - RSS・OGP 画像のアップロードは著作権リスクのため引き続き非対応
- **`resolve_media_id()` 追加**（v1.6.0 追加）
  - `image_resolver.py` に `resolve_media_id(item, default_media_id)` を追加
  - 将来（v1.7.0）の権利確認済み画像アップロードに対応した拡張ポイント設計

### v1.5.0 — Publishing Enhancement（2026-06-30 完了）

- **slug の自動生成と WordPress への設定**（v1.5.0 追加）
  - `src/slug_generator.py` が SEO タイトルの ASCII 英数字を抽出してケバブケース slug を生成
  - 例：`【速報】PS6はNintendo Switch型に？` → `ps6-nintendo-switch-20260630`
  - 英字が取れない場合は `article-YYYYMMDD` にフォールバック
  - WordPress 投稿 payload の `slug` フィールドに自動設定
  - Markdown YAML front matter にも記録
- **WordPress 投稿ログ改善**（v1.5.0 追加）
  - 投稿 ID・実際に使用された slug・編集 URL をコンソール表示
- **実行時間表示**（v1.5.0 追加）
  - 完了サマリーに `実行時間: XX.X秒` を表示

### v1.4.0 — SEO Foundation（2026-06-30 完了）

- **excerpt（抜粋）の自動生成と記録**（v1.4.0 追加）
  - 記事本文の先頭段落からMarkdown記法を除いてルールベースで生成（API追加なし）
  - WordPress投稿時に `excerpt` フィールドとして送信
  - Markdownファイルの YAML front matter に `excerpt` / `meta_description` として記録
- **ImageResolver 導入**（v1.4.0 追加）
  - `src/image_resolver.py` 新設（画像候補URL選択の責務を main.py から分離）
  - `resolve_featured_image(item)` が image_candidates の先頭URLを返す
  - v1.5.0以降でデフォルト画像・権利確認済み画像・AI生成画像への拡張に対応可能

### v1.3.0 — アイキャッチ画像URL抽出対応

- **RSSからアイキャッチ画像候補URLを自動抽出**（v1.3.0 追加）
  - `src/image_extractor.py` が media:thumbnail / enclosures / media:content を順に探索
  - 取得した画像URLは `NewsItem.image_candidates` に格納
  - Markdownファイルの末尾に `<!-- アイキャッチ候補: URL -->` として記録
  - 画像が見つからない場合はエラーなし・コメントなしで正常終了
  - 著作権リスクのためWordPressへの自動アップロードは行わない（v1.5.0 以降で検討）

### v1.2.0 — カテゴリ・タグ自動設定対応

- **WordPress投稿時のカテゴリ・タグ自動付与**（v1.2.0 追加）
  - カテゴリ：「ゲームニュース」を固定で付与
  - タグ：重要度に応じて自動設定（S→注目 / A→速報 / B→なし）
  - IDは `src/outputs/taxonomy_config.py` で一元管理（WordPressで確認したIDを設定）
  - ID未設定（0のまま）の場合はカテゴリ・タグを省略して投稿

### v1.1.0 — WordPress下書き投稿対応

- **WordPress REST API による下書き投稿**（v1.1.0 追加）
  - `.env` に WordPress設定を追加すると有効になる
  - 未設定の場合はMarkdown保存のみ動作（スキップされる）
  - 投稿状態は `draft`（下書き）固定（誤公開防止）
  - 認証：Application Password

### v1.0.0 — MVP

- 国内外16サイトのRSSからゲームニュースを自動収集
- キーワードフィルターによる事前スクリーニング（Claude API使用量を削減）
- Claude AIによる重要度判定（S / A / B / なし）
- 重要度に応じた記事下書きの自動生成
  - S評価：2000文字以上の詳細記事
  - A評価：800〜1500文字の通常記事（最大5件）
  - B評価：記事化しない（候補ファイルに保存）
- SEOタイトルの自動生成
- X（旧Twitter）投稿文の自動生成
- `output/` フォルダへのMarkdownファイル保存

---

## 対応RSSサイト（16サイト）

### 日本語

| サイト | 言語 |
|--------|------|
| 4Gamer | 日本語 |
| Game*Spark | 日本語 |

### 公式

| サイト | 言語 |
|--------|------|
| PlayStation公式 | 日本語 |
| Nintendo公式 | 日本語 |
| Xbox公式 | 英語 |
| Steam | 日本語 |

### 総合英語

| サイト | 言語 |
|--------|------|
| IGN | 英語 |
| GameSpot | 英語 |
| Eurogamer | 英語 |
| Gematsu | 英語 |
| VGC | 英語 |
| Insider Gaming | 英語 |
| PC Gamer | 英語 |

### プラットフォーム特化

| サイト | 言語 |
|--------|------|
| Nintendo Life | 英語 |
| Push Square | 英語 |
| Pure Xbox | 英語 |

---

## セットアップ

```bash
# 仮想環境を作成・有効化
python -m venv venv
venv\Scripts\activate   # Windows

# 依存パッケージをインストール
pip install -r requirements.txt

# 環境変数の設定
copy .env.example .env
# .env を開いて以下を設定する
#   ANTHROPIC_API_KEY  … Claude API キー（必須）
#   WP_SITE_URL        … WordPressサイトURL（WordPress投稿を使う場合）
#   WP_USERNAME        … WordPressユーザー名（WordPress投稿を使う場合）
#   WP_APP_PASSWORD    … Application Password（WordPress投稿を使う場合）
```

> **注意：** `.env` ファイルは `.gitignore` で除外されています。APIキーをコミットしないよう注意してください。

---

## 実行方法

```bash
# 通常動作（S全件 + A最大5件）
python main.py

# テスト用：先頭N件のみ生成
python main.py --max-articles 3
```

生成されたMarkdownファイルは `output/` フォルダに保存されます。

---

## 今後の予定

### v1.8.0 — Logging Foundation（Release 1.1 — Epic 2）

- 実行ログ・エラーログのファイル出力
- 投稿履歴・AI判定履歴の記録

### v1.9.0 — SNS Foundation（Release 1.1 — Epic 3）

- X投稿URLの保存・投稿履歴管理・将来のAPI連携設計

### v1.10.0 — Analytics Foundation（Release 1.1 — Epic 4）

- Search Console / Google Analytics 連携設計

### v2.0 — AI Blog Operator

- Windowsタスクスケジューラによる定時自動実行
- 重要度別の公開制御（S→公開・A→予約・B→下書き）
- 半自律的なブログ運営支援

---

## Release 2.x（Agent / Scheduler / Workflow Engine、2026-07-02時点）

> **注意**：本README本体（上記セクション）はv1.7.0時点の内容のまま更新が追いついていません（既知の文書負債）。v1.8.0以降〜Release 2.x（Agent Foundation・Scheduler・Workflow Engine等）の詳細は`docs/CHANGELOG.md` / `docs/ROADMAP.md` / `docs/architecture.md` / `docs/design/`配下の各設計書を参照してください。

Release 2.xでは、`main.py`による通常実行に加えて、「今この処理を実行すべきか」を判断してから実行するAgent層（`src/ai/`）・実行層（`src/pipeline/`）・判定層（`src/scheduler/`）・オーケストレーション層（`src/workflow_engine/`）が段階的に追加されています。いずれもデフォルト無効（Configuration First）で、`main.py`の通常実行には影響しません。

- **Workflow Engine（v2.7.0）**：Scheduler → Workflow Engine → NewsAgent → ReviewTriggerAgent → PublishTriggerAgentの順で自動実行する基盤。`./venv/Scripts/python.exe scripts/run_workflow_engine.py`で手動実行できます（`--dry-run` / `--job-id`対応）
  - `AI_AGENT_ENABLED=true` かつ `WORKFLOW_ENGINE_ENABLED=true` が前提条件（二重ゲート）
  - 固定・最小限（1件のみ）のデモJobのみを扱います（複数Job登録・設定ファイル化は未対応）
  - **`scripts/run_news_agent.py`等、既存のAgent系scriptと同時実行しないでください**（`decide()`から`act()`完了までロック機構がなく、同時実行するとNews収集・レビューレポート生成・WordPress下書き投稿などが二重に発生するおそれがあります）
  - 詳細・設計判断は`docs/architecture.md`「Workflow Engine層」・`docs/design/workflow_engine_foundation.md`を参照

この節はRelease 2.7時点の要点のみをまとめたものです。README全体の刷新（v1.8.0〜v2.6.0分の反映）は別タスクとして今後検討します。
