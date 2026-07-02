# docs/chatgpt_project/

作成日：2026-07-02
作成者：Claude Code

Version : 1.0
Created : 2026-07-02
Current Status : Stable

---

## このディレクトリの目的

ChatGPTプロジェクト「03_game_content_ai」に登録するための運用基盤文書一式を管理するディレクトリです。

これまでは新しいチャットを開始するたびに開発経緯・設計方針・協業ルールを説明し直していましたが、これらの文書をChatGPTプロジェクトに登録することで、その説明を省略し、**セッション固有の情報だけを引き継げばよい状態**を作ることを目的としています。

---

## 各文書の役割

| 文書 | 役割 | 変更頻度の想定 |
|---|---|---|
| [`project_instructions.md`](./project_instructions.md) | 守るべきルール（What）。プロジェクト概要・アーキテクチャ原則・Agent/Pipeline/Serviceの責務分離・開発フロー・レビュー方針・テスト方針・Git運用・Release運用・セッション運用・チャット引継ぎルール・AIモデル運用ポリシー・文書の優先順位 | 低 |
| [`development_charter.md`](./development_charter.md) | 開発思想（Why）。プロジェクトビジョン・開発理念・品質方針・設計判断の原則・スコープ管理・技術的負債・リファクタリング・拡張性・リリース/ドキュメント/レビューに関する考え方・意思決定原則 | 最も低い |
| [`ai_collaboration_guide.md`](./ai_collaboration_guide.md) | ChatGPTとClaude Codeの協業ルール（Who／どう連携するか）。役割分担・作業の流れ・レビュー依頼タイミング・セッション終了/切替・GitHub運用・トラブル対応・モデル運用 | 低 |
| [`standard_workflow.md`](./standard_workflow.md) | 1開発サイクルの標準的な進行手順（When）。セッション開始から新チャット引継ぎまでの13工程と、工程ごとのChatGPT／Claude Code／ユーザーの担当 | 低 |
| [`handoff_template.md`](./handoff_template.md) | チャット引継ぎ用テンプレート。セッション固有の7項目のみを埋めて新しいチャットに貼り付ける | 更新不要（テンプレート） |

各文書はそれぞれの役割にのみ内容を閉じ、他文書がカバーする内容は繰り返さず参照する形を取っています（例：`ai_collaboration_guide.md`のGit運用・モデル運用は`project_instructions.md`側の該当章を参照するのみ）。

---

## 文書の優先順位

複数の文書・指示が矛盾した場合は、以下の順で上位文書を優先します（詳細は`project_instructions.md` 13章）。

1. Project Instructions
2. Development Charter
3. AI Collaboration Guide / Standard Workflow
4. Architecture Design / Project Charter（`docs/design/`配下、リリース単位の個別設計）
5. チャット引継ぎ（`handoff_template.md`ベース）
6. 現在チャットでの個別指示

1・2が根本規範（What／Why）、3がそこから派生する協業・進行手順（Who／When）、4がリリース単位の個別設計、5・6がセッション単位の情報という位置づけです。

---

## 今後の更新方針

- 各文書はChatGPTプロジェクトへ登録後、内容と運用実態にずれが生じたと感じた時点で見直す（`development_charter.md` 10章「ドキュメントポリシー」と同じ「生きた文書」の考え方に従う）
- Release固有の情報・特定のクラス名・バージョン番号は、これらの文書には含めない。該当情報は`docs/design/`配下の個別文書や`CHANGELOG.md`に記載する
- 開発方針・アーキテクチャ原則・協業ルールそのものを変更する場合は、通常のRelease作業とは別に「運用ルール改定」として明示的にドラフト作成 → ChatGPTレビューのプロセスを踏む（`project_instructions.md` 11章）
- 新しい運用文書を追加する場合は、本READMEの「各文書の役割」表と「文書の優先順位」（および`project_instructions.md` 13章）の両方を更新する
