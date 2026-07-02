# AI Collaboration Guide — 03_game_content_ai

作成日：2026-07-02
作成者：Claude Code（ドラフト作成）
状態：**ドラフト（ChatGPTレビュー待ち）**

---

## この文書について

`project_instructions.md`（守るべきルール）・`development_charter.md`（開発思想）を補完する第3の文書として、**ChatGPTとClaude Codeという2つのAIがどう協業するか**に特化して整理したものです。

- 個々のルールの中身（Git運用の手順、レビュー工程の順序、設計判断の優先順位等）は前2文書に既にあるため、ここでは繰り返しません
- ここでは「その手順・判断を、ChatGPTとClaude Codeがどう分担し、どう連携するか」という**協業の運用面**のみを扱います
- Release固有の情報・特定のクラス名・バージョン番号は含みません

---

## 1. 基本理念

- ChatGPTとClaude Codeは、それぞれ得意領域が異なる2つのAIであり、上下関係ではなく**役割分担の関係**にある
- 最終的な意思決定者は人間（プロジェクト運営者）であり、AI同士の合意だけで重要な判断を完結させない
- 2つのAIの間で認識がずれた場合、どちらかが独断で進めるのではなく、人間を介して整合を取る

---

## 2. ChatGPTの役割

- 設計・アーキテクチャの検討（新機能を追加する際の構造の妥当性判断）
- 技術選定・比較検討（複数の実現方法がある場合の選択肢の整理）
- 各種文書（Project Charter・Architecture Design等）のレビュー
- リリース可否の判断
- 長期的な方向性・優先順位の決定

ChatGPTは基本的に**コードを直接書かない**。判断・レビュー・言語化を担う。

---

## 3. Claude Codeの役割

- 承認された設計に基づく実装・リファクタリング
- テストの作成・実行、動作確認
- Git操作（status確認・commit・push）
- ドキュメント（CHANGELOG・ROADMAP・design文書等）の更新
- 実装中に見つかった設計上の疑問点・矛盾点を、ChatGPTへのフィードバック事項として整理する

Claude Codeは基本的に**設計そのものを独断で確定させない**。Open Questionsがあれば実装を止め、確認を挟む。

---

## 4. 作業の流れ

一般的な作業は、以下のようにAIをまたいで進む。

```
1. 人間がChatGPTに相談・依頼
2. ChatGPTが設計・方針を整理（Charter / Architecture Design 等）
3. 人間が内容を確認し、Claude Codeへ引き継ぐ
4. Claude Codeが実装・テストを行う
5. 人間が動作・変更内容を確認する
6. 必要に応じてChatGPTへレビューを依頼する
7. 人間の承認を経てcommit・push・リリースへ進む
```

- ChatGPTとClaude Codeが直接やり取りすることはなく、**人間が仲介する**のが基本形である
- 小規模な作業（typo修正・軽微なバグ修正等）では、2〜6の一部を省略してよい。省略の判断は人間が行う

---

## 5. レビュー依頼タイミング

Claude Codeは、以下のタイミングで「ChatGPTへのレビュー依頼が必要な段階に来ている」ことを人間に伝える。

- 新しい機能・構造を追加する設計の骨子ができた時点（実装着手前）
- 実装中にProject Instructions／Development Charterで判断しきれない論点（Open Questions）に突き当たった時点
- Scope・Non Goalの解釈に迷いが生じた時点
- リリース前の最終確認が必要な時点

Claude Code自身がレビュー依頼の要否を判断して黙って進めることはしない。判断に迷う場面そのものが、レビュー依頼のシグナルである。

---

## 6. Claude Code終了タイミング

Claude Codeセッションを終了するタイミングの判断基準は `project_instructions.md`（10章）に従う。

本文書では、それに加えて協業上の観点を補足する。

- ChatGPTのレビュー待ちに入った場合（5章の依頼を出した後）、Claude Codeは新しい実装作業を先に進めず、レビュー結果の反映を待つ区切りとする
- レビュー待ちの間、Sessionを終了するか一時停止（Awaiting input）で保持するかは `project_instructions.md`（10章）の基準に従って人間が判断する。再開見込みが近い場合は一時停止で足り、都度の引継ぎプロンプト作成は不要である
- Sessionを終了する場合は、終了前に次にChatGPTへ何を確認してもらう必要があるかを人間に明示してから終える

---

## 7. セッション切替ルール

- ChatGPTセッションとClaude Codeセッションは別々の文脈を持つため、**両者の間の橋渡しは人間が行う**
- 橋渡しの際、Project Instructions／Development Charterに書かれている内容は改めて説明しない（11章のチャット引継ぎルールと同じ考え方）
- 橋渡しする内容は、直前の判断結果・次にやること・未解決の論点に限定する
- ChatGPT側での設計変更がClaude Codeでの実装に影響する場合は、変更内容を要約してからClaude Codeセッションに渡す（逆方向も同様）
- **`handoff_template.md` によるチャット引継ぎは、ChatGPTなど別ツール・別チャットへ橋渡しする場合にのみ用いる**。同一のClaude Code Session内で作業を再開できる場合（一時停止からの再開等）は、引継ぎプロンプトの作成を省略してよい

---

## 8. GitHub運用

- commit・pushの実行はClaude Codeが担当する（`project_instructions.md` 8章の手順に従う）
- ChatGPTはGitHub操作を直接行わない。レビュー対象がGitHub上のコード・PRである場合は、人間またはClaude Code経由で内容を共有する
- pushやリリースタグ付けなど、共有状態に影響する操作は、ChatGPTのレビューが完了し、人間の承認を得てからClaude Codeが実行する

---

## 9. トラブル時の対応

- Claude Codeが実装中に想定外の挙動・エラーに遭遇した場合、独自の判断で回避策（安全チェックの無効化等）を取らず、状況を正直に報告する（実測主義）
- ChatGPTとClaude Codeの判断が食い違う場合（例：ChatGPTが提示した設計が実装段階で成立しないと分かった場合）、Claude Codeはその場で設計を作り替えず、矛盾点を人間に報告し、ChatGPTへの再確認を挟む
- 障害・不具合の原因が過去のリリースにある場合、犯人探しではなく「今後どう防ぐか」を記録することを優先する（Development Charter 6章「技術的負債との向き合い方」と同じ姿勢）

---

## 10. モデル運用

- モデル運用の基本方針（Claude Code＝Sonnet標準、Fable 5は原則不使用）は `project_instructions.md`（12章）に従う。ここでは繰り返さない
- ChatGPT側のモデル選択（設計・レビュー用途）は本文書・PIいずれの対象外とし、都度の判断に委ねる
- モデル運用方針そのものを変更する場合は、`project_instructions.md`（12章）の改定として扱う

---

## Status

- [x] ドラフト作成（本文書、Claude Code作成）
- [ ] ChatGPTレビュー
- [ ] ChatGPTプロジェクトへの登録
