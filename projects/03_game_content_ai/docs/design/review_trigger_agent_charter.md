# Project Charter — Release 2.5「Review Trigger Agent Foundation」

作成日：2026-07-02
状態：ドラフト（Claude Code作成、ChatGPTレビュー前）
対象Service：`AiPublishReviewService`（v1.19.0）のみ

---

## 1. Goal

`AiPublishService`（WordPress下書き投稿）が完了した後の**公開前レビューレポート生成**（`AiPublishReviewService`、v1.19.0）を「今実行すべきか」判断するAgent、**`ReviewTriggerAgent`**を追加する。News Agent（v2.2.0）・Workflow Trigger Agent（v2.3.0）・Publish Trigger Agent（v2.4.0）と同じ「Agent（判断）→ Pipeline（実行）→ 対象Service」パターンの4例目として構築する。

```
ReviewTriggerAgent   （判断：レビューレポートを今生成すべきか）
      ↓
ReviewPipelineRunner （実行：生成する）
      ↓
AiPublishReviewService（既存のサービス、v1.19.0、無改修）
```

---

## 2. Background

- `AiPublishReviewService`は`outputs/ai_publishes/`（投稿結果JSON）を読み込み、`outputs/ai_publish_reviews/`（レビューJSON）と`outputs/ai_publish_review_reports/`（Markdownレポート）を生成する**非破壊・読み取り確認のみ**のService。WordPress書き込み・Claude API呼び出しは一切行わない。
- 現状は`scripts/run_ai_publish_review.py`による**手動実行**が唯一の実行経路。「WordPress下書き投稿があったのに、レビューレポートが生成されないまま放置される」リスクがある。
- 他3つのTrigger Agentが対象としたService（`main.py` / `WorkflowRunner` / `AiPublishService`）は、いずれも独自の`Config`クラスと`is_ready()`（または相当の有効化条件）を持っていた。**`AiPublishReviewService`にはそれが存在しない**（`Config`クラスなし、常時実行可能、`from_paths()`のみで構築）。この違いはGate設計（6章参照）に影響するため、Architecture Designフェーズで扱う。

---

## 3. Scope

### 実装対象（想定、Architecture Designで確定）

- `ReviewTriggerAgentConfig`：判断・実行双方の設定値
- `ReviewPipelineRunner`（`src/pipeline/`）：`AiPublishReviewService.run()`を直接呼び出す実行層
- `ReviewTriggerAgent`（`BaseAgent`継承）：`decide()` / `act()` / `name()`
- `AgentManager.from_config()`への DI 追加
- `scripts/run_review_trigger_agent.py`：手動実行用CLIエントリ

### 対象外（今回のRelease 2.5では扱わない）

- `ImprovementReviewService`（v1.15.0）・`RewriteReviewService`（v1.17.0）は対象外。ただし将来これらへ拡張する余地は設計上残す（4章）
- `AiPublishReviewService`本体・`AiPublishReviewRepository`・`AiPublishReviewReportBuilder`の改修
- `review_status`（PENDING固定）を人が更新する機能（v1.19.0のFuture Extension、Release 2.5の対象外）
- `.env.example`のドキュメント負債解消（v2.4.0ドキュメント整備時に判明。別タスク候補として記録済み、Release 2.5には混ぜない）

---

## 4. Non Goal

- ReviewTriggerAgentはAiPublishReviewService本体の責務を変更しない
- WordPressへの書き込みは一切発生しない（対象Service自体が読み取り専用のため、他3Agentより安全側に倒しやすい）
- 複数Review系Service（Improvement/Rewrite/Publish）を横断的に判断する汎用Agentは今回作らない。まずは`AiPublishReviewService`単体で3層パターンを確立し、拡張性は「将来同じ形をコピーして追加できる」レベルに留める（抽象化・共通化はまだ行わない）

---

## 5. Success Criteria（Architecture Design以降で検証）

- `AI_AGENT_ENABLED=false`（デフォルト）で挙動が一切変わらないこと
- Gate設計（2段 or 3段）を明確にした上で、デフォルト無効から始めること
- `dry_run=True`で`AiPublishReviewService.run()`が構造的に起動しないこと
- 既存の`NewsAgent` / `WorkflowTriggerAgent` / `PublishTriggerAgent`・対象Service本体が無改修であること
- E2Eテスト全PASS・既存回帰（v2.0.0/v2.2.0/v2.3.0/v2.4.0）全PASS

---

## 6. Open Questions（Architecture Designフェーズで決定）

1. **Gate方式**：`AiPublishReviewService`に`is_ready()`がないため、他Agentのような「既存Configのis_ready()を3段目として再利用」ができない。`ReviewTriggerAgentConfig`独自の`enabled`フラグのみの二重ゲート（`AI_AGENT_ENABLED` × `REVIEW_TRIGGER_AGENT_ENABLED`）にするか、何らかの形で三重ゲートに寄せるかを設計する
2. **`decide()`の判断材料**：他Agentは「前回実行からの経過時間（mtime）」方式だったが、`AiPublishReviewService`は入力（`outputs/ai_publishes/`）に対する出力（`outputs/ai_publish_review_reports/`）という構造のため、「時間間隔」に加えて「未レビューの投稿結果があるか」を見る方式も選択肢に入る。ただしPublish Trigger Agent設計時に「Agentが対象Serviceのデータ構造を直接見に行かない」方針を採ったため、同じ制約の中でどう判断するかを検討する
3. 将来のImprovement/Rewrite Review拡張時に、今回の設計がどこまで再利用できるかの見立て（抽象化はしないが、命名・構造だけは意識する）

---

## 7. Status

- [x] Project Charter ドラフト作成（本ドキュメント）
- [ ] ChatGPTレビュー
- [ ] Architecture Design
- [ ] Architecture Review
- [ ] 実装開始
