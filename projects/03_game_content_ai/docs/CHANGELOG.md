# CHANGELOG

このファイルはプロジェクトの変更履歴を記録します。
フォーマットは [Keep a Changelog](https://keepachangelog.com/ja/) に準拠。

---

## [v1.0] - 2026-06-26

### Added

- Steam News フィード追加（`https://store.steampowered.com/feeds/news/?l=japanese`）
  - 「公式」カテゴリに追加（PlayStation公式・Nintendo公式・Xbox公式・Steam）
  - 合計16サイトからのRSS収集に対応
- RSS取得サマリー表示（カテゴリ別の取得件数・成否を一覧表示）
  - `FeedStats` データクラスによる取得結果の構造化
  - `FEED_GROUPS` によるカテゴリ別グルーピング
  - 取得合計・フィルター通過・重複除去後・記事生成の件数を末尾に表示

---

## [v0.9] - 2026-06-26

### Added

- RSSニュース取得（15サイト対応）
  - 日本語：4Gamer、Game\*Spark
  - 公式：PlayStation公式、Nintendo公式、Xbox公式
  - 総合英語：IGN、GameSpot、Eurogamer、Gematsu、VGC、Insider Gaming、PC Gamer
  - プラットフォーム特化：Nintendo Life、Push Square、Pure Xbox
- キーワードフィルター（API節約のための事前スクリーニング）
- Claude APIによる重要度判定（S / A / B / なし）
- 日本語記事下書き生成
- SEOタイトル生成
- X（旧Twitter）投稿文生成
- Markdownファイル保存（output/ フォルダ）
- 重複ニュース排除（`duplicate_filter.py`、URLの正規化付き）

### Fixed

- JSON抽出処理を正規表現ベースに変更し、APIレスポンス形式の変化に対応
- Windows環境でのUTF-8文字コード問題を修正（起動時にstdout/stderrを設定）
