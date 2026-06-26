# 03 ゲームニュース記事生成AI

国内外のゲームニュースをRSSで自動収集し、Claude AIが重要度を判定・日本語記事下書き・SEOタイトル・X投稿文を生成して、Markdownファイルとして保存するツールです。

**ブログ名**：KAORUの部屋  
**ステータス**：v1.0.0 MVP完成

---

## 実装済み機能（v1.0.0）

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
# .env を開いて ANTHROPIC_API_KEY を設定する
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

## 今後の予定（v1.x 以降）

- WordPress REST API連携（生成記事の自動投稿）
- アイキャッチ画像URL取得（各ニュースサイトのOGP画像）
- Windowsタスクスケジューラによる定時自動実行
