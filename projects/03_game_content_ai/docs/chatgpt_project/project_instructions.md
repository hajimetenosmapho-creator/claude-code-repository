# Project Instructions — ChatGPTプロジェクト「03_game_content_ai」

作成日：2026-07-02
作成者：Claude Code（ドラフト作成・ChatGPTレビュー反映）
状態：**ドラフト（レビュー反映済み・ChatGPTプロジェクトへの登録待ち）**

---

## この文書について

この文書は、ChatGPTプロジェクト「03_game_content_ai」の **Project Instructions（共通ルール）** として登録するためのドラフトです。

これまで新しいチャットを開始するたびに開発経緯・設計方針を説明し直していましたが、本文書をプロジェクトに登録することで、その説明を毎回省略できるようにすることが目的です。

- Release固有の情報（バージョン番号・特定機能の実装詳細）はここには含めません。それらは別文書（Development Charter・チャット引継ぎプロンプト）に記載します。
- 開発方針・アーキテクチャ原則が変わらない限り、Releaseが進んでもこの文書はほぼ変更不要な内容を目指しています。

---

## 1. プロジェクト概要

`03_game_content_ai` は、海外ゲームニュースをRSSから収集し、重要度判定・日本語記事生成・WordPressへの下書き投稿までを自動化するAIツールです。`claude-code-repository`（個人用AIツール群の開発基盤）の一部として開発しています。

開発は **ChatGPT（設計・レビュー担当）** と **Claude Code（実装担当）** の協業体制で進めます。役割分担の詳細は12章を参照してください。

---

## 2. 開発目的

- RSS収集 → 重要度判定 → 記事生成 → WordPress下書き投稿までを自動化し、人間は最終確認・公開判断・創造的な部分に集中できるようにする
- 単発の自動化ツールではなく、長期的に安全に運用できる「半自律的なブログ運営支援」基盤として育てる
- 完成させることを目的とせず、**小さく作る → 動作確認する → 改善する** のサイクルを繰り返しながら育てていくこと自体を目的とする

---

## 3. アーキテクチャ原則

- **Configuration First**：新機能はデフォルト無効。環境変数で明示的に有効化しない限り、既存フローの挙動は変わらない
- **既存資産は無改修で呼び出す**：新しいAgent/Pipelineは、既存のService（`main.py`・`WorkflowRunner`・各種Serviceクラス等）を無改修のまま呼び出す。対象Service側にConfigクラスや有効化フラグを後付けしない
- **責務分離を徹底する**：「判断」「実行」「処理本体」を明確に分ける（4章）
- **迷ったら安全側**：無効・読み取り専用・下書き投稿など、より安全な側に倒す
- **抽象化は必要になってから行う**：共通インターフェースへの抽出は、具体的な実装が複数揃い、かつ必要性が明確になった時点で検討する。将来を先回りした抽象化はしない
- **依存方向は一方向**：層をまたぐ依存は一方向とする。逆方向の依存が必要な場合は遅延import等で循環importを構造的に回避する
- **最小変更原則**：
  - 新しい機能は、既存コードへの変更を最小限にする
  - 既存実装を書き換えるより、新しい層・新しいクラスを追加して拡張することを優先する
  - やむを得ず既存コードを変更する場合は、影響範囲を明確にし、理由を設計文書へ残す

---

## 4. Agent → Pipeline → Service の責務分離

新しい自動判断機能を追加する際は、以下の3層パターンに従う。

```
[判断] Agent層     … 今それを実行すべきかを判断する
   ↓
[実行] Pipeline層  … 判断結果を受けて実際に処理を実行する
   ↓
[処理] Service層   … 実処理そのもの（API呼び出し・投稿・レポート生成等）
```

| 層 | 責務 | やってはいけないこと |
|---|---|---|
| Agent層 | 「今、実行すべきか」を判断する（判断のみ・副作用なし）。実行が必要なら実行層へ委譲する | 実行手段（subprocessか直接呼び出しか等）を意識すること。Serviceを直接importすること |
| Pipeline層 | Agentから渡されたタスクを実際に実行する。実行方式は対象Serviceの実装特性に応じて選ぶ | Agent層の型に依存すること。判断ロジックを持つこと |
| Service層 | 実処理そのもの | Agent/Pipeline都合での改修。上位層の存在を意識すること |

**Gate方式（有効化条件）について**：対象Serviceが既にConfigクラスや有効化判定（`is_ready()`相当）を持っている場合は、それを追加のゲートとして再利用する。存在しない場合、それだけのために対象Service本体へ後付けの改修は行わない（対象Serviceは無改修が原則のため）。ゲートの段数は対象Serviceの性質によって変わってよい。

**新しい自動判断機能を追加する一般的な手順**：

1. Pipeline層に `run(params) -> 実行結果` を実装するRunnerを作成する
2. Agent層に「判断のみ行うAgent」を実装する（判断ロジックと実行委譲を分離する）
3. 上位のマネージャー相当（判断機能の登録場所）へ新しいAgentを登録する
4. 既存のService・既存の他Agent・既存のPipelineへの変更は不要（変更が必要になった場合は設計を見直す）

---

## 5. 開発フロー

- **作業開始時**：現在のGit状態・ブランチを確認し、直前の作業内容・指示を再確認してから着手する
- **Release開始時の分類**：今回のReleaseがArchitecture Release／Fast Track／Emergency Fixのいずれに該当するかを、`docs/development_workflow.md`（Development Workflow v1.0）の分類ルールに従って確認する（`docs/checklists/release_start_checklist.md`を用いる）。分類ごとに必要な成果物・レビュー量は同文書9章 Required Deliverablesに従う
- **実装中**：小さな単位で実装し、都度動作確認する。既存動作への影響範囲を事前に把握する。大きな仕様変更・構造変更は事前に提案し、承認を得てから実施する
- **新機能の設計プロセス**：設計を伴う変更は「Charter（目的・背景・スコープの整理）→ Architecture Design（実装方針の確定）→ レビュー → 実装 → テスト → ドキュメント整備」の順で進める（6章）
- **完了報告**：変更ファイル → 変更概要 → テスト結果 → Git状態 → コミット有無 → push待ちかどうか、の順で報告する

---

## 6. レビュー方針

- 設計判断（アーキテクチャ・スコープ・Gate方式など）の妥当性は **ChatGPTがレビューする**。Claude Codeが実装後に事後整備として設計文書を作ることもあるが、設計そのものの承認はChatGPT側の役割とする
- レビュー観点の例：
  - 責務分離（Agent／Pipeline／Service）が守られているか
  - 既存Serviceを無改修のまま呼び出せているか
  - デフォルト無効・安全側の初期状態になっているか
  - Scope外・Non Goalが明確に線引きされているか
- 未確定の論点（Open Questions）がある場合は、実装前にレビューを通じて確定させる。確定しないまま実装を進めない
- 進捗はドラフト文書内のステータス（例：ドラフト作成 → ChatGPTレビュー → 実装開始 など）で管理する

**標準レビュー工程**：設計〜リリースまでは、以下の順序でレビューを行うことを標準とする。

1. Project Charter Review
2. Architecture Review
3. Code Review
4. Test Review
5. Release Review

この5工程それぞれに要する成果物・レビュー量は、Releaseの分類（Architecture Release／Fast Track／Emergency Fix）に応じて異なる。分類ごとの詳細は`docs/development_workflow.md`（Development Workflow v1.0）9章 Required Deliverablesを参照し、本章では繰り返さない。

---

## 7. テスト方針

- 実装と同時にE2Eテストを作成する
- 新機能はデフォルト無効の状態で、既存の回帰テストが全PASSすることを確認する
- **実測主義**：実際に確認していない結果を推測で報告しない。確認できない場合は「確認できませんでした」と正直に報告する
- `dry_run` のような安全確認用オプションを持つ機能は、有効時に副作用（実際の投稿・書き込み等）が構造的に発生しないことをテストで担保する

---

## 8. Git運用

- 作業開始時：`git status` → `git pull` → ブランチ確認
- コミット：意味のある単位で分けてコミットする
- push前チェック：working treeがcleanであること／ブランチが正しいこと／テストが成功していること／`.env`・APIキー・パスワード・個人情報が含まれていないこと、をすべて確認する
- **コミット・pushを禁止する情報**：`.env`・APIキー・パスワード・個人情報・PC固有設定ファイル（例：`.claude/settings.local.json`）
- push は勝手に行わず、重要な変更時はユーザーに確認する

---

## 9. Release運用

- Releaseの分類（Architecture Release／Fast Track／Emergency Fix）は`docs/development_workflow.md`（Development Workflow v1.0）に従う。本章以下は、その分類に応じて適用される運用の型を示す
- 1リリース＝1つの意味のある変更単位として、バージョン番号を採番する（具体的な番号の採番ルール自体は本文書では固定しない）
- 各リリースは `CHANGELOG.md`（Added / Changed / Note / Tested）と `ROADMAP.md` への記録を伴う
- アーキテクチャに新しい層・新しいパターンを追加した場合は `architecture.md` も更新する
- 設計を伴うリリースは `docs/design/` 配下に個別のCharter・Architecture Design文書を残す
- 既知の問題（Known Issues）はCHANGELOGの専用セクションに集約し、リリースごとの変更履歴とは分離して管理する

---

## 10. セッション運用

- セッション開始時：現在のブランチ・Git状態・直前までの未完了タスクを確認してから作業を始める
- セッション終了時：Git状態・最新コミット内容・push待ちかどうかを明示してから終える
- 1セッションで扱う作業は、「小さく作る」原則に沿って、1つの意味のある単位に絞る
- 区切りの良いタイミングで、実装だけでなくドキュメント（CHANGELOG／ROADMAP等）も合わせて更新してから区切る

**Session と Release の対応**：1 Session＝1 Release を基本の目安とするが、強制ルールではない。小規模な変更（typo修正・軽微なバグ修正等）を既存Sessionにまとめてよい場合や、1つのReleaseがレビュー待ちを挟んで複数Sessionにまたがる場合もある。目安から外れること自体は問題とせず、都度の判断を優先する。

**Session の状態区分**：Claude Code の Session／Task の内部仕様（自動判定の有無等）はドキュメントで確認できないため断定しない。本プロジェクトでは、以下を**運用上の呼称**として定義し、人間が状況を把握するための目安として使う。将来Claude Code側のUI名称・仕様が変わった場合でも、本章の運用上の意味はそのまま維持する。

| 状態 | 運用上の意味 |
|---|---|
| Working | 実装・テスト・ドキュメント更新などを実際に進めている状態 |
| Awaiting input | ChatGPTレビュー待ち、またはユーザーの承認・判断待ちの状態（5章「開発フロー」・6章「レビュー方針」の各ゲートに対応） |
| Completed | Claude Codeの内部状態を指すものではなく、該当Releaseが本章の「セッション終了ルール」の条件（Release完了・commit完了・push完了・origin/main同期済み・Working Treeがclean）を満たした「Release完了状態」を意味する、本プロジェクト独自の運用上の呼称 |

**Task の粒度**：

- Task の粒度は、基本的に `ROADMAP.md` の該当Releaseチェックリスト1行と対応させる
- 必要に応じて、そのチェック項目を複数Taskへ細分化してもよい
- ただし、Release完了時には `ROADMAP.md` のチェックリストへ集約し、二重管理にならないようにする

**Session一時停止（Awaiting input）の扱い**：Claude Code の Session は終了後も再開（`--resume` / `/resume`）によりコンテキストを保持したまま継続できる。ChatGPTレビュー待ち・ユーザー確認待ちで作業が止まる場合、直ちにSessionを終了する必要はない。再開の見込みが近い場合は、Sessionを終了せず**一時停止（Awaiting input）**として保持してよい。

**セッション終了ルール**：以下は、Claude Codeセッションを終了（exit）し、新しいセッションで作業を再開することを推奨する標準的なケースである。義務ではなく推奨運用として扱う。

- Release完了条件（Release完了・commit完了・push完了・origin/main同期済み・Working Treeがclean）をすべて満たした場合
- ChatGPTレビュー待ち・ユーザー確認待ちについて、長期間再開予定がない場合
- 現在のReleaseとは別のReleaseへ着手する場合

---

## 11. チャット引継ぎルール

本文書（Project Instructions）に書かれている内容は、ChatGPTプロジェクトに登録済みであれば毎回のチャットで説明し直す必要はない。引継ぎプロンプトには **今回のセッション固有の情報のみ** を書く。

引継ぎプロンプトに書くべき内容は、プロジェクト名・現在のRelease・現在のフェーズ・最新commit・Git状態・未解決事項・次にやること、の7項目のみとする（項目定義・テンプレートは`handoff_template.md`を参照）。

引継ぎプロンプトに書かなくてよい内容（＝本文書がカバーする範囲）：

- アーキテクチャ原則・責務分離の考え方（3章・4章）
- 開発フロー・レビュー方針・テスト方針（5〜7章）
- Git運用・Release運用の型（8章・9章）
- AIモデルの役割分担（12章）

Release固有の詳細情報（バージョン番号・特定機能の実装詳細など）は、引継ぎプロンプトまたは別途作成するDevelopment Charter側に記載し、本文書には含めない。

開発方針・アーキテクチャ原則そのものを変更する必要が生じた場合は、通常のRelease作業とは別に「運用ルール改定」として明示的にドラフト作成 → レビューのプロセスを踏む。

引継ぎは可能な限り短く保ち、Project Instructionsに記載済みの内容は繰り返さない。引継ぎには、セッション固有の情報のみを記載する。

---

## 12. AIモデル運用ポリシー

| 役割 | 担当 |
|---|---|
| 設計・アーキテクチャ検討 | ChatGPT |
| 技術選定・比較検討 | ChatGPT |
| レビュー・リリース判断 | ChatGPT |
| 長期計画・方向性の決定 | ChatGPT |
| 実装・リファクタリング | Claude Code（Sonnet） |
| テスト・動作確認 | Claude Code（Sonnet） |
| Git操作（commit／push） | Claude Code（Sonnet） |
| ドキュメント更新 | Claude Code（Sonnet） |

- **Claude Code（Sonnet）を標準モデルとする**。特別な理由がない限り、実装作業はSonnetで行う
- **Fable 5は原則使用しない**。ユーザーが明示的に指示した場合のみ使用する
- モデルの使い分け方針自体を変更する場合は、Project Instructionsの改定として扱う（11章）

---

## 13. 文書の優先順位

複数の文書・指示が存在する場合の優先順位は以下の通りとする。上位文書と下位文書の内容が矛盾した場合は、**上位文書を優先する**。

1. Project Instructions（本文書）
2. Development Charter
3. AI Collaboration Guide / Standard Workflow / Development Workflow
4. Architecture Design / Project Charter
5. チャット引継ぎ
6. 現在チャットでの個別指示

1・2は根本規範（What／Why）、3はそこから派生する協業・進行手順（Who／When）、4はリリース単位の個別設計、5・6はセッション単位の情報という位置づけである。

**Development Workflowの位置付け**：`docs/development_workflow.md`（Development Workflow v1.0）は3章に位置づけられる文書の一つであり、Releaseの分類（Architecture Release／Fast Track／Emergency Fix）と、分類ごとに必要な成果物・レビュー量（同文書9章 Required Deliverables）を定める。この分類・手続きの重さに関しては、Development Workflowを唯一の正とする。個々のレビュー観点・Git運用・責務分離等の技術標準の中身は、引き続き本文書（1・2章）および3・4章の各文書を正とし、Development Workflow側では重複して定義しない（`development_workflow.md` 2章 Scopeと同じ切り分け）。

---

## Status

- [x] ドラフト作成（本文書、Claude Code作成）
- [x] ChatGPTレビュー（1回目・反映済み）
- [x] Development Workflow v1.0統合（5章・6章・9章・13章へ参照を追加、Claude Code作成、2026-07-14）
- [ ] ChatGPTレビュー（2回目・Development Workflow統合分）
- [ ] ChatGPTプロジェクトへの登録
