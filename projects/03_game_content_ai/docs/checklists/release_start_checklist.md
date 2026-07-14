# Release開始時チェックリスト

Session開始時、実装着手前に確認する。[development_workflow.md](../development_workflow.md) 15章 Stop Conditionsに該当する項目が1つでもあれば、作業を停止し人間に報告する。

---

## 1. git status

- [ ] `git status`を実行し、Working Treeがcleanであることを確認した
- [ ] cleanでない場合：未コミットの変更が自分の意図しないものでないか確認し、人間に報告してから先へ進む

## 2. origin/main同期

- [ ] `git fetch origin`を実行した
- [ ] ローカルの`main`が`origin/main`と同期済み（ahead/behindがない）であることを確認した
- [ ] 同期していない場合：`git pull origin main`で取り込み、コンフリクトの有無を確認した

## 3. Working Tree

- [ ] 現在のブランチが`main`であることを確認した
- [ ] `git log --oneline -1`で最新commitを確認し、直前のSession終了時点の想定commitと一致することを確認した
- [ ] 一致しない場合：作業を停止し、差分の内容を人間に報告する

## 4. Release分類

- [ ] 今回のReleaseが「Productionで通常Releaseを待てない障害」に該当するか確認した（該当する場合は`emergency_fix_template.md`を使用し、以下の項目は事後対応でよい）
- [ ] 該当しない場合：[development_workflow.md](../development_workflow.md) 7章のFast Track候補条件（8項目）を確認した
- [ ] 8項目すべてを満たす場合：Fast Track Release（`fast_track_release_template.md`を使用）
- [ ] 1項目でも満たさない、または判断に迷う場合：Architecture Release（`architecture_release_template.md`を使用）

## 5. AI構成確認

- [ ] 今回のReleaseに必要なChatGPTレビュー（Architecture Review／簡易Review）の依頼タイミングを確認した（[development_workflow.md](../development_workflow.md) 11章、`ai_collaboration_guide.md` 5章）
- [ ] 前Sessionからの引き継ぎ事項・Open Questionsが残っていないか確認した（残っている場合は解消するまで実装に進まない）

## 6. Fast Track Checklist

Fast Trackに分類する場合のみ、[development_workflow.md](../development_workflow.md) 10章のFast Track Checklistをこの時点で実施し、`fast_track_release_template.md`の1.3節へ結果を転記する。

- [ ] Public API変更がないことを確認した
- [ ] Constructor変更（シグネチャ変更）がないことを確認した
- [ ] Composition Root変更がないことを確認した
- [ ] Layer変更（責務境界の変更）がないことを確認した
- [ ] Dependency変更（新規import・pip追加・既存import削除）がないことを確認した
- [ ] 永続化変更（新しい保存先・スキーマ変更）がないことを確認した
- [ ] Event変更（イベント型の新規追加・フィールド変更）がないことを確認した
- [ ] 外部I/O変更（新規外部サービス呼び出し・既存呼び出し先変更）がないことを確認した

---

## 完了後

上記すべてを確認したら、該当するテンプレート（`architecture_release_template.md` / `fast_track_release_template.md` / `emergency_fix_template.md`）の作成に進む。
