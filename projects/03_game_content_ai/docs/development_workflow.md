# Development Workflow v1.0 — 03_game_content_ai

**AI-Assisted Software Development Standard**

作成日：2026-07-14
作成者：ChatGPT（Architecture Design・Architecture Review）／Claude Code（Documentation）／ユーザー（最終承認・Design Freeze確定）
状態：**Design Freeze（Documentation Phase・ChatGPTレビュー待ち）**

---

## この文書について

`project_instructions.md`・`development_charter.md`・`ai_collaboration_guide.md`・`standard_workflow.md`（以下、まとめて「既存Architecture Process」）が既に定めている手続き・役割分担・思想はここでは繰り返しません。

本文書が新たに定めるのは、**「今回のReleaseに、既存Architecture Processをどの重さで適用するか」を決定する分類ルール**のみです。個々のレビュー観点・Git運用の手順・AIの役割分担の中身は、すべて既存文書側の記載を正とします。

本文書はDesign Freeze済みの内容をMarkdown化したものであり、本Documentation Phaseにおいて新しい設計判断は行っていません。

---

## 1. Purpose

品質を維持したまま開発速度を向上させることを目的とします。Fast Trackは品質を下げる制度ではなく、Architecture変更を伴わないReleaseについて、既存Architecture Processの手続き（成果物・レビュー量・ドキュメント量）を軽量化するための制度です。

## 2. Scope

- **対象**：`03_game_content_ai`のすべてのRelease（Architecture Release／Fast Track Release／Emergency Fix）
- **対象外**：他プロジェクト（`01_wordpress_blog_ai`・`02_youtube_to_blog_ai`・`04_finance_tool`・`05_emergency_docs_ai`）への適用。共通化は将来、複数プロジェクトの実績が揃った段階で改めて検討します（`development_charter.md` 14章と同じ姿勢）
- **対象外**：個々のレビュー観点（責務分離チェック・Configuration First確認等）の中身。これらは`project_instructions.md` 6章に従い、本文書では繰り返しません
- **本文書が規定するもの**：本Workflowは**Development Process（開発の進め方・手続き）のみ**を規定します。Architecture Standard・Coding Standard・Testing Standardなどの技術標準を置き換えるものではありません。技術標準の内容そのものは既存Architecture Process側（`project_instructions.md`等）の記載を正とし、本文書はそれらをどの重さで適用するか（9章 Required Deliverables）のみを決定します

## 3. Relationship with Existing Process

- 本文書は既存Architecture Process（Project Charter → Architecture Design → Architecture Review → 実装 → Test → Documentation）を**置き換えません**。既存の運用（Project Charter・Architecture Design・Architecture Review・Known Issue・CHANGELOG・ROADMAP）をそのまま継承し、その**上位ルール**として「どの重さで適用するか」を決定します。
- `project_instructions.md` 13章の文書優先順位における位置づけとしては、本文書は「3. AI Collaboration Guide / Standard Workflow」と同格の、Who／Whenの手続き層に相当します。ただし、この位置づけを正式に確定させるには`project_instructions.md` 13章および`docs/chatgpt_project/README.md`（「今後の更新方針」）の更新が必要です。この更新作業は本Documentation Phaseのスコープ外であり、`project_instructions.md` 11章に定める「運用ルール改定」として別途行うものとします。
- `standard_workflow.md`の補足には、既に「小規模な作業（typo修正・軽微なバグ修正等）では、2〜4・6〜8の一部を省略してよい。省略するかどうかはユーザーが判断する」という規定があります。本文書は、この**主観的な「小規模」判断を、Fast Track候補条件（7章）という客観的な基準に置き換えるもの**です。ただし本文書のFast Trackは、テスト・Regression・Git確認・Known Issue確認を省略の対象外としており、既存の補足規定より**厳格**な運用となります（軽量化対象は9章の通り、成果物・レビュー量・ドキュメント量に限定されます）。

### Hierarchy

```
Development Workflow（本文書）
        │  上位ルール：Releaseごとに「どの重さで適用するか」を決定する
        ▼
既存Architecture Process
（project_instructions.md／development_charter.md／
  ai_collaboration_guide.md／standard_workflow.md）
        │
        ├──▶ Architecture Standard（Project Charter／Architecture Design／
        │                            Architecture Reviewの中身）
        ├──▶ Coding Standard（project_instructions.md 3〜4章：
        │                      アーキテクチャ原則・責務分離）
        └──▶ Testing Standard（project_instructions.md 7章：テスト方針）
```

本文書はこれらの技術標準（Architecture Standard／Coding Standard／Testing Standard）の内容そのものには関与しません。関与するのは、Releaseの分類（6〜7章）に応じて、これらをどの成果物・レビュー量・ドキュメント量で適用するか（9章）のみです。

## 4. Philosophy

- 品質を維持したまま開発速度を向上させる
- Fast Trackは品質を下げる制度ではない
- 変更量ではなく設計リスクで分類する
- 判断に迷った場合はArchitecture Releaseを選択する

## 5. Terminology (Glossary)

Fast Track候補条件（7章）で用いる用語を定義します。定義に迷う余地がある場合は、Philosophy（4章）の「迷った場合はArchitecture Release」に従い、広め（Architecture Release側）に解釈します。

| 用語 | 定義 |
|---|---|
| **Public API** | 他パッケージ・外部スクリプト（`scripts/`配下等）から呼び出される公開関数・クラス・メソッドのシグネチャまたは戻り値の型 |
| **Constructor変更** | 既存クラスの`__init__`シグネチャの変更（引数の追加・削除・型変更を含む）。既存呼び出し元への後方互換性の有無に関わらず、シグネチャ自体の変更を指す |
| **Composition Root** | 各層のインスタンスを実際に生成・配線する起点となるモジュール（例：`src/retry_composition/retry_composition_root.py`）。新しい配線判断の追加・既存配線の変更はComposition Root変更に該当する |
| **Layer** | Agent層／Pipeline層／Service層（`project_instructions.md` 4章）に代表される責務境界。新しい層の追加、または既存層の責務変更はLayer変更に該当する |
| **Dependency変更** | 新しい外部パッケージ（pip等）の追加、または`src/`配下パッケージ間の新しいimport関係の追加・削除（例：v3.8.0で`retry_engine`が`scheduler`を新規importした変更） |
| **永続化変更** | ファイル・DB等、プロセス終了後も保持されるデータの保存先・スキーマ・保存方式の変更。既存の永続化方式（例：JSON Lines形式のログ出力）を踏襲した記録項目の追加はFast Track対象例（Logging）に含まれるが、新しい保存先・保存方式を追加する場合は永続化変更に該当する |
| **Event変更** | パッケージ間で受け渡しされるイベント型（例：`SchedulerEvent`）の新規追加、または既存イベント型のフィールド変更 |
| **外部I/O** | ネットワーク越しの外部サービス呼び出し（WordPress REST API・Search Console・Google Analytics・Claude API等）の新規追加、または既存呼び出し先の変更。ファイルシステムへのログ出力は外部I/Oに含めない |
| **Design Summary** | Fast Trackにおいて、Project Charter・Architecture Designの代わりに作成する簡潔な設計記録。目的・変更範囲・Fast Track候補条件のチェック結果を簡潔にまとめる |
| **Design Freeze** | 設計判断がChatGPTのArchitecture Reviewを経て確定し、以後の変更を伴わない状態 |
| **Escalation** | Fast Track開始後にArchitecture変更に該当することが判明した場合に、分類をArchitecture Releaseへ切り替える手続き（8章） |

## 6. Release Classification

| 分類 | 概要 |
|---|---|
| **Architecture Release** | 新Subsystem・Public API変更・Composition Root変更・Layer変更・Dependency変更・Design Pattern変更・責務変更・永続化変更・外部サービス変更・Roadmap変更を伴うRelease |
| **Fast Track Release** | Architecture変更を伴わないRelease。対象例：CLI、Logging、配線、Dry Run、Loop、Known Issue解消、小規模Refactoring、テスト追加、ドキュメント更新 |
| **Emergency Fix** | Productionで通常Releaseを待てない障害への即時対応のみ。年間数回程度を想定する例外的な分類 |

対象例は理解を助けるための例示であり、分類そのものを決定するものではありません。対象例に該当していても、7章のFast Track候補条件をすべて満たさない限りFast Trackにはなりません。

## 7. Release Classification Rule

- 分類は**変更量ではなく設計リスク**で行う
- **Fast Track候補条件**（すべて満たした場合のみFast Track候補）：
  1. Public API変更なし
  2. Constructor変更なし
  3. Composition Root変更なし
  4. Layer変更なし
  5. Dependency変更なし
  6. 永続化変更なし
  7. Event変更なし
  8. 外部I/O変更なし
- 最終分類は**設計担当AIによるArchitecture Review後**に確定する。Claude Codeの自己判断のみで最終確定しない
- 判断に迷う場合はArchitecture Releaseを選択する

## 8. Escalation Rule

Fast Track開始後に、実装中またはレビュー中に7章の条件のいずれかへ抵触することが判明した場合、Architecture Releaseへ昇格する。

**手順**：

1. 抵触に気づいた時点で実装作業を中断する（新しい変更を積み増さない）
2. 抵触した条件と理由をユーザーへ報告する
3. 作成済みのDesign Summaryを土台に、不足するProject Charter・Architecture Designを追加作成する
4. ChatGPTへArchitecture Review（簡易レビューではなく通常のArchitecture Review）を依頼する
5. 承認後、Architecture Releaseとして残りの工程（Code Review以降）を進める
6. 昇格した事実と理由を、CHANGELOG.mdのKnown Issuesまたは該当Release記録に残す（既存のKnown Issue記録慣習を踏襲する）

降格（Architecture Release → Fast Track）の手続きは本文書では定義しない。分類の変更が必要になった場合は、その都度Architecture Reviewを通じて判断する。

## 9. Required Deliverables

| 成果物 | Architecture Release | Fast Track | Emergency Fix |
|---|---|---|---|
| Project Charter | 必須 | 不要（Design Summaryで代替） | 不要（事後に正式化） |
| Architecture Design | 必須 | 不要（Design Summaryで代替） | 不要（事後に正式化） |
| Design Summary | 不要 | 必須 | 復旧後に作成 |
| ChatGPT Architecture Review | 必須（フル） | 必須（Design Summary対象の簡易レビュー） | 復旧後に実施 |
| Code Review | 必須 | 必須 | 復旧後、可能な範囲で実施 |
| E2Eテスト | 必須 | 必須 | 可能な範囲で実施（復旧を優先） |
| 既存回帰テスト（Regression） | 必須 | 必須 | 可能な範囲で実施（復旧を優先） |
| Known Issue確認 | 必須 | 必須 | 可能な範囲で実施 |
| Git確認（status／origin同期／diff） | 必須 | 必須 | 必須 |
| CHANGELOG／ROADMAP更新 | 必須（詳細） | 必須（簡潔） | 必須（インシデント記録として） |
| Release Review | 必須 | 必須 | 復旧後に正式Releaseとして実施 |

Fast Trackで軽量化されるのは**成果物・レビュー量・ドキュメント量**のみであり、テスト・Regression・Git確認・Known Issue確認は省略しません。

## 10. Fast Track Checklist

- [ ] Public API変更がないことを確認した
- [ ] Constructor変更（シグネチャ変更）がないことを確認した
- [ ] Composition Root変更がないことを確認した
- [ ] Layer変更（責務境界の変更）がないことを確認した
- [ ] Dependency変更（新規import・pip追加・既存import削除）がないことを確認した
- [ ] 永続化変更（新しい保存先・スキーマ変更）がないことを確認した
- [ ] Event変更（イベント型の新規追加・フィールド変更）がないことを確認した
- [ ] 外部I/O変更（新規外部サービス呼び出し・既存呼び出し先変更）がないことを確認した
- [ ] 上記すべてを満たしている（1つでも満たさない場合はArchitecture Release、または8章Escalation Ruleへ）
- [ ] Design Summaryを作成した
- [ ] ChatGPTのArchitecture Review（簡易）を受けた

## 11. AI Roles

本文書は`ai_collaboration_guide.md`の役割分担をそのまま継承します。役割の詳細は同文書を参照し、ここでは繰り返しません。

- 設計担当AI（現在はChatGPT）：設計・アーキテクチャ検討、Architecture Review、Release可否判断
- Claude Code：実装、テスト、Git操作、ドキュメント更新
- 人間：最終承認者

Fast Track・Architecture Releaseいずれにおいても、「設計判断の最終承認は設計担当AIによるArchitecture Review、公開・commit・pushの最終承認は人間」という二段階承認構造は変わりません。AI名（設計担当AI／Claude Code）は役割名として扱い、将来モデルが変わっても本Workflowの構造自体は変わらないものとします（`project_instructions.md` 12章と同じ考え方）。

## 12. Claude Code Operational Rules

- 「1 Session = 1 Release」を基本の目安とする（`project_instructions.md` 10章と同じ、強制ルールではない）
- Commit・Pushの実行はClaude Codeが担当するが、実行判断は人間の承認を経てから行う（`project_instructions.md` 8章）
- Fast Track候補条件のセルフチェック（7章・10章）は実装着手前に行い、結果をDesign Summaryへ記録する
- 実装中にFast Track条件への抵触に気づいた場合は、8章Escalation Ruleに従う
- Claude Codeは分類を最終確定させない。最終分類は設計担当AIによるArchitecture Review後に確定する（`project_instructions.md` 6章と同じ二段階承認構造）

## 13. Git Operational Rules

- Release開始時：`git status` → `git fetch` / `git pull` → ブランチ確認 → 最新commit確認（既存運用を継承。`project_instructions.md` 8章）
- Working Treeがclean・mainブランチ・origin/mainと同期済みであることを確認してから作業を開始する
- 確認事項が想定と一致しない場合は作業を停止し、人間に報告する（15章 Stop Conditions）
- Push前チェック（`project_instructions.md` 8章）を維持する：Working Tree clean／ブランチ正しい／テスト成功／機密情報（`.env`・APIキー・パスワード・個人情報・PC固有設定ファイル）が含まれていない
- Fast Track・Architecture Releaseいずれも、このGit運用ルールを省略しない

## 14. Session Rules

`project_instructions.md` 10章「セッション運用」をそのまま継承し、本章では繰り返しません。本文書固有の補足のみを以下に記します。

- Release分類（Architecture Release／Fast Track／Emergency Fix）は、Session開始時に確定させることを目安とする。Session途中で8章Escalation Ruleが発動した場合はその限りではない
- Documentation Phase・Architecture Review Phaseなど、実装を伴わないSessionでは「1 Session = 1 Release」の対応を求めない（本Session自体がその一例）

## 15. Stop Conditions

以下のいずれかに該当する場合、Claude Codeは作業を停止し、人間に報告する。

- `git status`がcleanでない、または最新commitが想定と不一致
- 現在のブランチが`main`でない
- `origin/main`との同期が取れていない
- Fast Track候補条件のいずれかに抵触することが判明したが、8章Escalation Ruleの手順が完了していない
- Design Freeze済みの内容と、実装しようとしている内容に相違がある
- ChatGPTのArchitecture Reviewが未完了のまま、Fast Track／Architecture Releaseいずれかの実装に着手しようとしている
- 機密情報（`.env`・APIキー・パスワード・個人情報等）がGit操作対象に含まれている

## 16. Workflow Versioning

- 本文書はv1.0として登録する。バージョン表記は文書冒頭に記載する
- 本文書自体の変更は、本Workflowが定めるRelease Classification Rule（7章）に従って分類する（本Workflow自身への自己適用）
- 本文書のバージョン更新は、`project_instructions.md` 11章「運用ルール改定」の手順（ドラフト作成 → ChatGPTレビュー）を経て確定する
- 変更履歴は本文書のStatusセクション、または`CHANGELOG.md`への記載により追跡する

---

## Appendix A. Representative Examples

以下は理解を助けるための参考例です。本Workflow導入前（v1.1.0〜v5.9.0）の実績から抜粋したものであり、当時これらのReleaseが本Workflowに基づいて正式に分類されていたわけではありません。

**Architecture Release相当の実績例**

- v3.8.0 Retry Engine Event Consumption：`retry_engine`が`scheduler`を新規importした（Dependency変更）
- v4.6.0 Retry Enqueue Trigger Foundation：新規Subsystem（`retry_enqueue_trigger`パッケージ）の追加
- v5.1.0 Retry Composition Root Foundation：新規Composition Root（`RetryCompositionRoot`）の新設

**Fast Track相当の実績例**

- v1.8.0 Logging Foundation：既存の永続化方式（JSON Lines）を踏襲したログ出力の追加
- 各種`scripts/`のCLIオプション追加（`--dry-run`等）

**Emergency Fix例**

- 本プロジェクトでは2026-07-14時点で発生実績なし

## Appendix B. Release Decision Flow

```
[Session開始]
     │
     ▼
git status / git log 確認 ── 不一致 ──▶ [停止・報告]（15章 Stop Conditions）
     │ 一致
     ▼
Productionで通常Releaseを待てない障害か？
     │
     ├─ Yes ─▶ [Emergency Fix]
     │            │
     │            ▼
     │         即時対応・復旧
     │            │
     │            ▼
     │         復旧後、通常Release/Architecture Releaseで正式整理（9章）
     │
     └─ No
          │
          ▼
     Fast Track候補条件（7章）をすべて満たすか？
          │
          ├─ Yes ─▶ [Fast Track Release]
          │            │
          │            ▼
          │         Design Summary作成
          │            │
          │            ▼
          │         ChatGPT簡易Architecture Review
          │            │
          │            ▼
          │         実装中にArchitecture変更が判明？
          │            │
          │            ├─ Yes ─▶ [Escalation Rule（8章）] ─▶ Architecture Releaseへ
          │            │
          │            └─ No ──▶ Code Review → Test Review → Release Review
          │                        → commit → push → CHANGELOG/ROADMAP更新
          │
          └─ No／判断に迷う ─▶ [Architecture Release]
                                  │
                                  ▼
                              Project Charter作成
                                  │
                                  ▼
                              Architecture Design作成
                                  │
                                  ▼
                              ChatGPT Architecture Review
                                  │
                                  ▼
                              Code Review → Test Review → Release Review
                                  → commit → push → CHANGELOG/ROADMAP更新
```

---

## Status

- [x] Design Freeze反映（本文書、Claude Code作成）
- [ ] ChatGPTレビュー
- [ ] `project_instructions.md` 13章・`docs/chatgpt_project/README.md`への登録（別セッションで「運用ルール改定」として実施）
