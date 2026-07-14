# ＜vX.X.0 ＿＿＿＿＞ Design Summary（Fast Track）

作成日：＜YYYY-MM-DD＞
作成者：ChatGPT（簡易Review）／Claude Code（Implementation・Test・Documentation）／ユーザー（最終承認）
状態：＜ドラフト作成 → ChatGPT簡易レビュー → 実装中 → 実装完了・確定＞
分類：Fast Track Release（[development_workflow.md](../development_workflow.md) 6章）

> 本テンプレートは[development_workflow.md](../development_workflow.md)のRequired Deliverables（9章）に基づく、Fast Track用の成果物一式です。Project Charter・Architecture Designの代わりに、本Design Summaryを作成します。テスト・Regression・Git確認・Known Issue確認は省略しません。

---

## 1. Design Summary

### 1.1 目的

＜このReleaseで何を実現するか（簡潔に）＞

### 1.2 変更範囲

＜変更対象ファイル・新規作成ファイルの一覧＞

### 1.3 Fast Track Checklist結果

[development_workflow.md](../development_workflow.md) 10章のチェックリストを実施した結果を記録する。

- [ ] Public API変更がないことを確認した
- [ ] Constructor変更（シグネチャ変更）がないことを確認した
- [ ] Composition Root変更がないことを確認した
- [ ] Layer変更（責務境界の変更）がないことを確認した
- [ ] Dependency変更（新規import・pip追加・既存import削除）がないことを確認した
- [ ] 永続化変更（新しい保存先・スキーマ変更）がないことを確認した
- [ ] Event変更（イベント型の新規追加・フィールド変更）がないことを確認した
- [ ] 外部I/O変更（新規外部サービス呼び出し・既存呼び出し先変更）がないことを確認した
- [ ] 上記すべてを満たしている

いずれか1つでも満たさない場合は、この場で作業を中断し、[development_workflow.md](../development_workflow.md) 8章 Escalation Ruleに従ってArchitecture Releaseへ切り替える（本テンプレートではなく`architecture_release_template.md`を使用する）。

---

## 2. 実装概要

＜実施した変更内容の要約。詳細はコード・Git履歴を参照する前提で、「なぜそうしたか」を中心に記載＞

---

## 3. ChatGPT簡易Review記録

- レビュー担当：ChatGPT
- レビュー日：＜YYYY-MM-DD＞
- レビュー対象：本Design Summaryのみ（Project Charter・Architecture Design相当の詳細レビューは行わない）
- 指摘事項と対応：＜箇条書き。なければ「なし」＞
- 承認：＜承認／要修正＞

---

## 4. Code Review記録

- レビュー担当：ChatGPT
- レビュー日：＜YYYY-MM-DD＞
- 指摘事項と対応：＜箇条書き＞

---

## 5. Test Review記録

- E2Eテスト：＜ファイル名・件数・結果（実測）＞
- 既存回帰テスト：＜対象ファイル一覧・件数・結果（実測）＞
- 実測できなかった項目：＜あれば「確認できませんでした」と正直に記載＞

---

## 6. Escalation判定

- 実装中にArchitecture変更（1.3のいずれかの条件）が判明したか：＜なし／あり＞
- 「あり」の場合：[development_workflow.md](../development_workflow.md) 8章の手順に従い、`architecture_release_template.md`へ移行した記録を残す

---

## 7. Release Review記録

- レビュー担当：ChatGPT
- 判断：＜Release可／不可＞
- 人間の最終承認：＜承認日＞

---

## 8. CHANGELOG／ROADMAP反映チェック

- [ ] `CHANGELOG.md`へ簡潔な記載（Added／Changed／Tested）を行った
- [ ] `ROADMAP.md`へ該当バージョンのチェックリストを追加した
- [ ] 新規Known Issueがあれば`CHANGELOG.md`のKnown Issuesセクションへ記録した

---

## Status

- [ ] ドラフト作成
- [ ] ChatGPT簡易レビュー
- [ ] 実装完了
- [ ] Code Review完了
- [ ] Test Review完了
- [ ] Release Review完了
- [ ] commit／push完了
