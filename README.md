# 個人用AIツール開発リポジトリ

個人で運用するAIツール群をまとめて管理するリポジトリです。
複数PC間での作業を想定し、GitHubで一元管理します。

## プロジェクト一覧

| # | プロジェクト | 概要 | ステータス |
|---|-------------|------|-----------|
| 01 | [WordPress ブログ記事作成AI](projects/01_wordpress_blog_ai/) | AIがブログ記事を自動生成・WordPress投稿 | 開発予定 |
| 02 | [YouTube → ブログ記事AI](projects/02_youtube_to_blog_ai/) | YouTube動画の内容をブログ記事化 | 開発予定 |
| 03 | [ゲームニュース収集AI](projects/03_game_content_ai/) | ゲーム関連ニュースを自動収集・整理 | 開発予定 |
| 04 | [投資・家計管理ツール](projects/04_finance_tool/) | 投資情報の追跡・家計データ管理 | 開発予定 |
| 05 | [救急活動記録・公文書作成AI](projects/05_emergency_docs_ai/) | 救急活動記録の作成・公文書テンプレート補助 | 開発予定 |

## リポジトリ構成

```
claude-code-repository/
├── projects/                      # 各AIツールのプロジェクト
│   ├── 01_wordpress_blog_ai/      # WordPress ブログ記事作成AI
│   │   ├── src/                   # ソースコード
│   │   ├── prompts/               # プロンプトテンプレート
│   │   └── tests/                 # テストコード
│   ├── 02_youtube_to_blog_ai/     # YouTube → ブログ記事AI
│   │   ├── src/
│   │   ├── prompts/
│   │   └── tests/
│   ├── 03_game_content_ai/        # ゲームニュース収集AI
│   │   ├── src/
│   │   ├── prompts/
│   │   └── tests/
│   ├── 04_finance_tool/           # 投資・家計管理ツール
│   │   ├── src/
│   │   ├── prompts/
│   │   └── tests/
│   └── 05_emergency_docs_ai/      # 救急活動記録・公文書作成AI
│       ├── src/
│       ├── prompts/
│       └── tests/
├── shared/                        # 複数プロジェクト共通のリソース
│   ├── utils/                     # 共通ユーティリティ関数
│   ├── config/                    # 共通設定ファイル
│   └── templates/                 # 共通テンプレート
├── docs/                          # ドキュメント・設計資料
├── scripts/                       # セットアップ・運用スクリプト
└── README.md
```

## セットアップ

### 必要な環境
- Python 3.11以上
- Claude Code CLI
- Git

### 初回セットアップ

```bash
# リポジトリのクローン
git clone https://github.com/<your-username>/claude-code-repository.git
cd claude-code-repository

# 環境変数の設定
cp shared/config/.env.example shared/config/.env
# .env ファイルにAPIキー等を設定する
```

> **注意:** `.env` ファイルは `.gitignore` で除外されています。APIキーをコミットしないよう注意してください。

## 開発方針

- 各プロジェクトは独立して動作できるよう設計する
- 共通処理は `shared/` にまとめて再利用する
- プロンプトはコードと分離して `prompts/` で管理する
- 機密情報（APIキー等）は `.env` で管理し、Gitには含めない

## ライセンス

個人利用のみ。無断転載・再配布禁止。
