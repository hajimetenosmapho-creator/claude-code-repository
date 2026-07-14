# ＜Emergency Fix＿＿＿＿＞ インシデント記録

作成日：＜YYYY-MM-DD＞
作成者：Claude Code（即時対応）／ユーザー（承認）／ChatGPT（事後Review）
状態：＜対応中 → 復旧済み → 事後正式化待ち → 正式化完了＞
分類：Emergency Fix（[development_workflow.md](../development_workflow.md) 6章）

> Emergency Fixは「Productionで通常Releaseを待てない障害」への即時対応にのみ用いる例外的な分類です（年間数回程度を想定）。復旧後は必ず、通常ReleaseまたはArchitecture Releaseとして正式整理します（[development_workflow.md](../development_workflow.md) 9章）。

---

## 1. インシデント概要

- 発生日時：＜YYYY-MM-DD HH:MM＞
- 発見経緯：＜どのように気づいたか＞
- 症状：＜何が起きているか＞
- 影響範囲：＜どの機能・どのデータ・どの外部サービス連携に影響するか＞
- 「Productionで通常Releaseを待てない」と判断した理由：＜具体的に記載＞

---

## 2. 即時対応内容

- 対応内容：＜実施した変更・操作の内容＞
- 対応時に確認したこと：＜git status／Working Tree／機密情報混入の有無など、[development_workflow.md](../development_workflow.md) 13章のGit運用ルールは省略しない＞
- 対応中に実施できたテスト：＜実施した範囲を実測で記載。実施できなかった場合はその旨を正直に記載＞

---

## 3. 復旧確認

- 復旧確認日時：＜YYYY-MM-DD HH:MM＞
- 復旧確認方法：＜どのように復旧を確認したか（実測）＞
- 復旧後の残存リスク：＜あれば記載＞

---

## 4. 暫定対応の限界・既知のリスク

＜即時対応が正式なArchitecture Process（Project Charter → Architecture Design → Architecture Review）を経ていないことにより生じている暫定性・リスクを明記する＞

---

## 5. 事後正式化計画

- 正式化方法：＜通常Release／Architecture Releaseのいずれで整理するか＞
- 正式化予定時期：＜目安＞
- 正式化時に実施すること：
  - [ ] Project Charter・Architecture Designの事後作成
  - [ ] ChatGPTによるArchitecture Review
  - [ ] 未実施だったE2Eテスト・既存回帰テストの実施
  - [ ] Code Review／Release Review

---

## 6. Known Issue登録

- [ ] `CHANGELOG.md`のKnown Issuesセクションへ、本インシデントの内容と暫定対応である旨を記録した

---

## 7. CHANGELOG記録

- [ ] `CHANGELOG.md`へインシデント記録として記載した（正式なRelease記録は事後正式化時に別途行う）

---

## Status

- [ ] 対応中
- [ ] 復旧済み
- [ ] Known Issue登録済み
- [ ] 事後正式化計画を人間へ報告済み
- [ ] 事後正式化完了（`architecture_release_template.md`または通常Releaseで整理済み）
