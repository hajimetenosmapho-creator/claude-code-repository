# ＜vX.X.0 ＿＿＿＿ Foundation／Integration 等＞ 設計書（Project Charter / Architecture Design）

作成日：＜YYYY-MM-DD＞
作成者：ChatGPT（Architecture Design・Architecture Review）／Claude Code（Implementation・Test・Documentation）／ユーザー（最終承認）
状態：＜ドラフト作成 → ChatGPTレビュー → 実装中 → 実装完了・確定＞
分類：Architecture Release（[development_workflow.md](../development_workflow.md) 6章）

> 本テンプレートは[development_workflow.md](../development_workflow.md)のRequired Deliverables（9章）に基づく、Architecture Release用の成果物一式です。個々のレビュー観点は`project_instructions.md` 6章に従います。

---

## 1. Project Charter

### 1.1 目的

＜このReleaseで何を実現するか＞

### 1.2 背景

＜なぜ今このReleaseが必要か。関連する既存Known Issue・前Releaseからの継続課題があれば記載＞

### 1.3 Non-Goal（本Releaseで実施しないこと）

＜スコープ外として明示的に線引きする項目を列挙＞

---

## 2. Fast Track Checklist該当確認

[development_workflow.md](../development_workflow.md) 7章の条件のうち、本Releaseが**満たさない**項目（＝Architecture Releaseに分類される理由）を明記する。

| 条件 | 該当有無 | 該当する場合の内容 |
|---|---|---|
| Public API変更 | ＜あり／なし＞ | ＜内容＞ |
| Constructor変更 | ＜あり／なし＞ | ＜内容＞ |
| Composition Root変更 | ＜あり／なし＞ | ＜内容＞ |
| Layer変更 | ＜あり／なし＞ | ＜内容＞ |
| Dependency変更 | ＜あり／なし＞ | ＜内容＞ |
| 永続化変更 | ＜あり／なし＞ | ＜内容＞ |
| Event変更 | ＜あり／なし＞ | ＜内容＞ |
| 外部I/O変更 | ＜あり／なし＞ | ＜内容＞ |

---

## 3. Architecture Design

### 3.1 配置・命名

＜新規パッケージ・クラス名とその根拠。既存の命名規則との整合性＞

### 3.2 Scope（対象）

＜変更対象ファイル・新規作成ファイルの一覧＞

### 3.3 採用案・却下案

＜検討した実装方針の選択肢と、採用しなかった理由＞

### 3.4 トレードオフ

＜採用案が持つ制約・妥協点＞

### 3.5 Known Issues

＜本Release時点で判明している未解決の問題。既存のKnown Issue番号体系（CHANGELOG.md）を踏襲する＞

### 3.6 Technical Debt

＜先送りした判断とその理由（`development_charter.md` 6章の3条件：可視化・理由説明・将来の解消見通し）＞

### 3.7 Future Candidates

＜次Release以降で検討する拡張候補＞

---

## 4. Architecture Review記録

- レビュー担当：ChatGPT
- レビュー日：＜YYYY-MM-DD＞
- 指摘事項と対応：＜箇条書き＞
- Open Questions（未確定の論点）：＜あれば列挙。解消するまで実装に進まない＞
- 承認：＜承認／要修正＞

---

## 5. Code Review記録

- レビュー担当：ChatGPT
- レビュー日：＜YYYY-MM-DD＞
- 指摘事項と対応：＜箇条書き＞

---

## 6. Test Review記録

- E2Eテスト：＜ファイル名・件数・結果（実測）＞
- 既存回帰テスト：＜対象ファイル一覧・件数・結果（実測）＞
- 実測できなかった項目：＜あれば「確認できませんでした」と正直に記載＞

---

## 7. Release Review記録

- レビュー担当：ChatGPT
- 判断：＜Release可／不可＞
- 人間の最終承認：＜承認日＞

---

## 8. CHANGELOG／ROADMAP反映チェック

- [ ] `CHANGELOG.md`へAdded／Changed／Note／Testedを記載した
- [ ] `ROADMAP.md`へ該当バージョンのチェックリストを追加した
- [ ] アーキテクチャに新しい層・新しいパターンを追加した場合、`architecture.md`を更新した
- [ ] 新規Known Issueがあれば`CHANGELOG.md`のKnown Issuesセクションへ記録した

---

## Status

- [ ] ドラフト作成
- [ ] ChatGPTレビュー（Project Charter Review／Architecture Review）
- [ ] 実装完了
- [ ] Code Review完了
- [ ] Test Review完了
- [ ] Release Review完了
- [ ] commit／push完了
