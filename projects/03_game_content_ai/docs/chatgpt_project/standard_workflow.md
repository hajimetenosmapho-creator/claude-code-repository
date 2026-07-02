# Standard Workflow — 03_game_content_ai

作成日：2026-07-02
作成者：Claude Code（ドラフト作成）
状態：**ドラフト（ChatGPTレビュー待ち）**

---

## この文書について

`project_instructions.md`（守るべきルール）・`ai_collaboration_guide.md`（協業の役割分担）で個別に定めた内容を、**1回の開発サイクルの流れ**として一本化したものです。

- 各工程の中身のルール（レビュー観点、Git運用手順等）はここでは繰り返しません。前2文書を参照してください
- ここでは「どの順番で」「誰が」「何を」行うかのみを扱います
- Release固有の情報は含みません

「6. Code Review」「7. Test Review」「8. Release Review」に加え、「2. Project Charter」「3. Architecture Design」に対する確認が、`project_instructions.md`（6章）の標準レビュー工程（Project Charter Review → Architecture Review → Code Review → Test Review → Release Review）に対応します。本文書では「4. ChatGPTレビュー」として、Project CharterとArchitecture Designをまとめて確認する工程を表しています。

---

## 標準運用フロー

| # | 工程 | 内容 | ChatGPT | Claude Code | ユーザー |
|---|---|---|---|---|---|
| 1 | セッション開始 | 新しいチャットで作業を始める | – | Git状態・ブランチを確認 | 引継ぎプロンプトを提示し、作業を依頼する |
| 2 | Project Charter | 目的・背景・スコープを整理する | 作成する | – | 依頼し、内容を確認する |
| 3 | Architecture Design | 実装方針を確定する | 作成する | 技術的な制約・実現性の所見を提供する（必要時） | 内容を確認する |
| 4 | ChatGPTレビュー | Project Charter・Architecture Designの妥当性を確認する（Project Charter Review／Architecture Review） | レビューを実施する | – | レビュー結果を確認し、実装可否を判断する |
| 5 | Claude Code実装 | 承認された設計に基づいて実装する | – | 実装・E2Eテスト作成を行う | 進捗・疑問点の共有を受ける |
| 6 | Code Review | 実装内容を確認する | レビューを実施する | 指摘への対応・修正を行う | レビュー依頼・最終確認を行う |
| 7 | Test Review | テスト結果を確認する | レビューを実施する | テストを実行し、結果を実測で報告する | 結果を確認する |
| 8 | Release Review | リリース可否を判断する | 最終レビュー・可否判断を行う | – | 承認する |
| 9 | commit | 変更を記録する | – | 意味のある単位でcommitする | 内容を確認する |
| 10 | push | 変更を共有状態へ反映する | – | push前チェックを行い実行する | 重要な変更時は事前に承認する |
| 11 | ドキュメント更新 | CHANGELOG・ROADMAP等を最新化する | – | 更新する | 確認する |
| 12 | セッション終了 | 区切りをつける | – | 終了条件（Release完了・commit完了・push完了・origin/main同期済み・Working Treeがclean）を確認し報告する | 終了を判断する |
| 13 | 新チャット引継ぎ | 次のセッションへ引き継ぐ | – | 引継ぎ内容の整理を支援する（必要時） | `handoff_template.md`を用いて新しいチャットを開始する |

---

## 補足

- 小規模な作業（typo修正・軽微なバグ修正等）では、2〜4・6〜8の一部を省略してよい。省略するかどうかはユーザーが判断する（`ai_collaboration_guide.md` 4章と同じ考え方）
- ChatGPTとClaude Codeが直接やり取りすることはなく、各工程はユーザーを介して橋渡しされる
- 4章（ChatGPTレビュー）で未確定の論点（Open Questions）が残っている場合、5章（Claude Code実装）には進まない

---

## Status

- [x] ドラフト作成（本文書、Claude Code作成）
- [ ] ChatGPTレビュー
- [ ] ChatGPTプロジェクトへの登録
