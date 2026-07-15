# Retry Notification Message Foundation — Architecture Design（v6.7.0）

作成日：2026-07-15
作成者：ChatGPT（Architecture Design・Architecture Review）／Claude Code（Documentation）
状態：**Design Freeze**

---

## 1. Overview

Release 6.7は、v6.6.0が確定させる`RetryNotificationDecision`（`status`のみ）を唯一の入力として、送信可能な固定Notification Message（`RetryNotificationMessage`）を構築する新規独立パッケージ`src/retry_notification_message/`を追加する。判定（Judgment）は一切行わず、既に確定した`status`を固定Message Value Objectへ変換するだけのValue Building Foundationである。

---

## 2. Background

`Metrics(v6.3.0) → Monitoring(v6.4.0) → Alert(v6.5.0) → Notification(v6.6.0)`という判定パイプラインは、v6.6.0時点で「通知すべきかどうか（`RetryNotificationStatus`：`NO_NOTIFICATION` / `NOTIFY`）」までを確定させた。しかし`RetryNotificationDecision`は`status`のみを保持し、実際に送信する本文（メッセージ）を一切持たない。v6.6.0設計書20章 Technical Debtは「Decision単体では『何を』『どこへ』通知すべきかの情報を持たないため、実際に送信可能にするには少なくとも2段階（Message生成・Channel選択）の後続Foundationが前提条件となる」と明記しており、本Releaseはその最初の段階にあたる。

---

## 3. Problem Statement

`RetryNotificationDecision`は判定結果（`status`）のみを表すドメインオブジェクトであり、これをそのまま外部へ送信することはできない。送信可能な形（人間が読めるメッセージ本文）へ変換する責務が、現在のArchitectureのどこにも存在しない。この責務を、後続のChannel選択・実送信（Sender）と混同せず、単一責務のFoundationとして切り出す必要がある。

---

## 4. Goals

- `RetryNotificationDecision`から、送信可能な固定Message Value Object（`RetryNotificationMessage`）を構築する
- Stateless・Deterministic・固定対応表というFoundation Firstの一貫した性質を継続する
- `NO_NOTIFICATION`と「Messageを生成できる状態」を明確に区別し、契約違反をFail Fastで検知する

## 5. Non-Goals

- 重大度（WARNING/CRITICAL）別のMessage内容の作り分け
- チャネル選択・実送信（Slack／メール等）
- Message抑制・重複排除・レート制限
- Runtime／Composition Root・CLIへの配線
- テンプレート化・Localization・外部Configuration

---

## 6. Release Classification

**Architecture Release**

- 新規Public API（`RetryNotificationMessage` / `RetryNotificationMessageBuilder`）の追加
- 新規パッケージ`src/retry_notification_message/`の追加（Layer変更）
- `retry_notification`への新規import（Dependency変更）

Fast Track候補条件（Public API変更なし等）に明確に抵触するため、Fast Trackの余地はない。

---

## 7. Current Architecture

```
RetryMetricsSnapshot
    ↓（RetryHealthEvaluator.evaluate）
RetryHealthReport
    ↓（RetryAlertEvaluator.evaluate）
RetryAlert
    ↓（RetryNotificationEvaluator.evaluate）
RetryNotificationDecision   ← v6.6.0時点の到達点。status（NO_NOTIFICATION/NOTIFY）のみを保持
```

4パッケージ（`retry_metrics` / `retry_monitoring` / `retry_alert` / `retry_notification`）はいずれも「消費者不在の先行実装」であり、`RetryCompositionRoot`・`scripts/run_retry_runtime.py`のいずれからもimportされていない。

---

## 8. Proposed Responsibility

Retry Notification Message Foundationは、既に確定した`RetryNotificationDecision`から、固定の通知Message Value Objectを構築する責務のみを持つ。

- Value Building（Judgmentではない。閾値判定を行わない）
- Stateless
- Deterministic
- 固定対応表
- 外部I/Oなし
- Runtime依存なし
- CLI依存なし
- Logger依存なし
- Channel／Sender非依存

---

## 9. Domain Model

```python
@dataclass(frozen=True)
class RetryNotificationMessage:
    body: str
```

保持するフィールドは`body`のみ。保持しないもの：`RetryAlert` / `RetryAlertLevel` / `RetryNotificationDecision` / `RetryNotificationStatus` / `title` / `channel` / `timestamp` / `reason` / `metrics` / `health report` / `template ID` / `localization情報`。

**Architecture Reviewの経緯**：初版では`level: RetryAlertLevel`と`body: str`を保持する案を提示したが、Architecture Reviewで「Messageへ`level`を保持することは将来Channel要件の先読みになる」「Release 6.6で意図的に残した重大度非保持の責務境界を実質的に変更する」との指摘を受け、`body`のみの最小構成へ修正した。重大度が必要な将来の消費者は、Release 6.6のTechnical Debt方針どおり、呼び出し元が保持する元の`RetryAlert`を参照する。

---

## 10. Message Builder

```python
class RetryNotificationMessageBuilder:
    def build(
        self,
        decision: RetryNotificationDecision,
    ) -> RetryNotificationMessage:
        ...
```

Builderは判断ロジックを持たない。`RetryNotificationEvaluator`が既に確定した`status`を、固定Message Value Objectへ変換するだけである。

**命名の判断根拠**：`Evaluator`（判定を含意）・`Factory`（複雑な生成ロジックの選択を含意）ではなく、「既存の確定値から値を組み立てる」という実体に最も正確な`Builder`を採用した。

---

## 11. Fixed Mapping

```
RetryNotificationStatus.NOTIFY
    → RetryNotificationMessage(
        body="Retry Runtimeで通知対象の状態が検出されました。詳細を確認してください。"
      )

RetryNotificationStatus.NO_NOTIFICATION
    → ValueError

未対応のRetryNotificationStatus相当値
    → ValueError
```

既存3 Evaluator（Monitoring/Alert/Notification）と同型の、既知値の網羅的分岐＋フォールバック禁止という設計方針を継承する。

---

## 12. NO_NOTIFICATION Semantics

以下4つの概念を明確に区別する。

```
Notification評価の正常結果として通知対象ではない   … RetryNotificationStatus.NO_NOTIFICATION（正常系の明示値）
≠
Messageを生成できる                              … Builderが呼び出せる状態か（契約の話）
≠
評価失敗                                          … Evaluator側でValueErrorとなる異常系
≠
未対応値                                          … Builder側でValueErrorとなる契約違反
```

`NO_NOTIFICATION`は`RetryNotificationEvaluator`にとって正常な明示値だが、`RetryNotificationMessageBuilder`にとっては「Messageを生成せよ」という要求自体が成立しない入力である。したがって`NO_NOTIFICATION`をBuilderへ渡すことは契約違反として`ValueError`で明示的に失敗させる。

---

## 13. WARNING／CRITICAL Semantics

`RetryAlertLevel.WARNING`・`RetryAlertLevel.CRITICAL`はいずれもv6.6.0の`RetryNotificationEvaluator`によって`NOTIFY`へ変換される。`RetryNotificationMessageBuilder`は`RetryNotificationDecision`のみを入力とし`RetryAlert`を一切知らないため、両者を区別できず、区別しない。WARNING由来かCRITICAL由来かにかかわらず、共通の固定Messageを生成する。

**Message本文の意味契約**：

```
通知対象状態の存在を伝える。
重大度、原因、時刻、対象、対応手順は表現しない。
```

「軽微」「重大」「緊急」等、特定の重大度を示唆する語彙は含めない（BuilderはWARNING/CRITICALのどちらに由来するか判別できないため、誤った緊急度を伝えるリスクを避ける）。**正確な文言（句読点・言い回し）自体は将来の互換性契約の対象外**とし、実装フェーズおよび将来のCode Reviewで調整してよい。ただし「重大度を示唆しない」という意味契約への違反は許容しない。

重大度別Messageは31章のFuture Candidateとして扱う。

---

## 14. Package Design

```
projects/03_game_content_ai/src/retry_notification_message/
    __init__.py
    retry_notification_message.py
    retry_notification_message_builder.py
```

新規独立パッケージとする。既存`retry_notification`パッケージ（Judgment Only Foundation）へ追加する案も検討したが、Value BuildingとJudgmentという異なる性質の責務を1パッケージへ混在させないため、既存4パッケージが確立した「1 Foundation＝1責務＝1パッケージ」という前例に整合させる。

---

## 15. Dependency Direction

```
retry_notification_message
    ↓
retry_notification
    ↓
retry_alert
    ↓
retry_monitoring
    ↓
retry_metrics
```

**許可する直接依存**：`retry_notification_message → retry_notification`（参照可能な型：`RetryNotificationDecision` / `RetryNotificationStatus`）

**禁止する依存**：

- `retry_notification_message → retry_alert`
- `retry_notification_message → retry_monitoring`
- `retry_notification_message → retry_metrics`
- `retry_notification → retry_notification_message`（逆依存）
- Runtime系（`retry_composition` / `retry_runtime_*` / `RetryManager`）
- `RetryCompositionRoot`
- CLI（`scripts/`）
- Logger
- JSONL
- Channel／Sender（未着手だが将来的にも本Foundationからの依存は禁止）
- 外部pipライブラリ

**Architecture Reviewの経緯**：初版では`retry_notification_message → retry_alert`という直接依存を提示したが、「Message層がNotification Decisionを迂回する」「AlertからNotificationとMessageが分岐する構造になる」との指摘を受け、`retry_notification`のみへの直接依存（直前Layer限定という既存Architectureの一貫性）へ修正した。

---

## 16. Public API

```python
# retry_notification_message.py
@dataclass(frozen=True)
class RetryNotificationMessage:
    body: str
```

```python
# retry_notification_message_builder.py
class RetryNotificationMessageBuilder:
    def build(
        self,
        decision: RetryNotificationDecision,
    ) -> RetryNotificationMessage:
        ...
```

```python
# __init__.py
__all__ = [
    "RetryNotificationMessage",
    "RetryNotificationMessageBuilder",
]
```

固定Message文字列自体はPublic APIとしてexportしない。

---

## 17. Fail Fast Policy

| 入力・状態 | 方針 |
|---|---|
| NOTIFY | `RetryNotificationMessage`を返す |
| NO_NOTIFICATION | `ValueError` |
| 未対応Status相当値 | `ValueError` |
| 引数の型違反 | 既存Foundation同様、明示的`isinstance`検査なし |
| bodyの空文字 | productionで追加検査せず、固定値とE2Eで防止 |
| Message再代入 | `frozen dataclass`で禁止（`FrozenInstanceError`） |

`NO_NOTIFICATION`と未対応値は意味が異なる（前者は既知の正常値の契約違反的な誤用、後者は未知値そのもの）ため、E2Eでは別シナリオとして扱う。

---

## 18. Data Flow

```
RetryMetricsSnapshot
    ↓
RetryHealthReport
    ↓
RetryAlert
    ↓
RetryNotificationDecision
    ↓
RetryNotificationMessage
```

Message FoundationはNotification Decisionの直接の後続Layerである。

---

## 19. In Scope

- 新規`retry_notification_message`パッケージ
- `RetryNotificationMessage` / `RetryNotificationMessageBuilder`
- NOTIFYから固定Messageへの変換
- NO_NOTIFICATIONのFail Fast
- 未対応StatusのFail Fast
- Public API／`__all__`
- Dependency Direction（`retry_notification`のみへの依存）
- ASTベースArchitecture E2E
- Pipeline E2E
- Regression Strategy
- 本設計書
- `architecture.md` / `ROADMAP.md`更新案
- Release 6.6設計書Status記載漏れの是正方針（実施はRelease 6.7のDocumentation Updateフェーズ）

## 20. Out of Scope

`RetryAlert`入力、`RetryAlertLevel`のMessage保持、WARNING／CRITICAL別Message、Channel、Sender、Delivery、Slack／メール／Discord、外部I/O、Runtime／Scheduler Integration、`RetryCompositionRoot`変更、CLI Wiring、Suppression、Deduplication、Rate Limiting、Recovery通知、Notification履歴、timestamp、title、Localization、Template、外部Configuration、Logger、JSONL追加、既存production code変更。

---

## 21. E2E Test Strategy

実装Release（次工程）で以下を実施する想定。本文書はテスト方針の確定のみを行う。

### Domain Object

- `RetryNotificationMessage`がfrozen dataclassであること
- フィールドは`body`のみであること
- mutation不可（`FrozenInstanceError`）
- equality
- `body`が空でないこと
- package rootの`__all__`が2型のみであることの直接検証

### Builder

- `NOTIFY`から固定Message生成
- 固定Message本文の完全一致
- 同一入力で同一結果（決定性）
- 複数Builderインスタンス間で結果一致
- Builderに内部状態がないこと（`__dict__`が空）
- 独自`__init__`を持たないこと（`has_init_method`ユーティリティの再利用）
- `NO_NOTIFICATION`で`ValueError`
- 未対応Status相当値で`ValueError`
- 入力`RetryNotificationDecision`を変更しないこと

### Architecture（AST解析。文字列検索だけに依存しない）

- `retry_notification_message`から`retry_notification`への直接依存のみ許可
- `retry_alert`への直接依存禁止
- `retry_monitoring`への直接依存禁止
- `retry_metrics`への直接依存禁止
- `retry_notification`から`retry_notification_message`への逆依存禁止（`__init__.py`含む全productionモジュールを検査対象とする）
- 相対importは`level == 1`のみ許可、`level >= 2`禁止
- Runtime／CLI／Logger／JSONL／外部ライブラリ依存なし
- `open()`呼び出しなし

### Pipeline（手動Composition）

```
DEGRADED → WARNING → NOTIFY → 共通Message
UNHEALTHY → CRITICAL → NOTIFY → 共通Message
HEALTHY → NONE → NO_NOTIFICATION → Builderを呼ばない
```

Builder単体では：

```
NO_NOTIFICATION → ValueError
```

Pipelineの「Builderを呼ばない」（呼び出し元の責務）と、Builder単体のFail Fast（Builder自身の契約検証）を混同しない。

### Regression

- 既存Regression Suite（v5.9.0〜v6.6.0、ベースライン826/826 PASS）がベースライン件数のままPASSすること
- 既存Regressionテストファイル自体に意図しない変更がないこと
- 既存production codeの無改修確認は恒久E2Eには含めず、Release Review時に`git diff --name-status`で個別確認する
- Working Tree状態（git diff）は恒久E2Eへ含めない

---

## 22. Regression Strategy

- `retry_metrics` / `retry_monitoring` / `retry_alert` / `retry_notification`はいずれも無改修（本Releaseの変更対象は新規パッケージ`retry_notification_message`のみ）
- 既存Regression Suite（v5.9.0〜v6.6.0）をベースライン件数（826/826 PASS）で実行
- 終了コード0・FAILなし・警告なし

---

## 23. Compatibility

新規パッケージの追加のみであり、既存Public API（`retry_metrics` / `retry_monitoring` / `retry_alert` / `retry_notification`）への後方互換性への影響はない。本Foundationには現時点で消費者が存在しないため（Foundation First）、既存の呼び出し元への影響も発生しない。

## 24. Security

外部I/Oを持たず、固定文字列のみを扱うため、インジェクション・認証情報漏洩等のセキュリティリスクは想定されない。Message本文に動的な外部入力（ユーザー入力・外部API応答等）を埋め込まないため、文字列組み立てに起因する脆弱性のクラス自体が生じない。

## 25. Observability

CLI表示・Logger接続はいずれもOut of Scope（19章）。本Foundation自体はいかなる観測手段も持たない。これは意図的なNon-Goalであり、観測可能性はRetry Alert／Notification CLI Report Wiring Foundation（31章）へ委ねる。

---

## 26. Alternatives Considered

本Releaseは2回のArchitecture Reviewを経ている。

**1回目（Changes Required）で提示した案と却下理由**

| 論点 | 初版案 | 却下理由 |
|---|---|---|
| 入力 | `build(alert: RetryAlert)` | Message層がNotification Decisionを迂回し、Notification FoundationがMessage生成契約へ関与しなくなる。AlertからNotificationとMessageが分岐する構造になる |
| Domain Model | `RetryNotificationMessage(level: RetryAlertLevel, body: str)` | `level`保持は将来Channel要件の先読みであり、Release 6.6で意図的に残した重大度非保持の責務境界を実質的に変更する |
| Dependency | `retry_notification_message → retry_alert` | 直前Layerだけへ依存する既存Architectureの一貫性を崩す |

**2回目（Approved）で確定した修正**

- 入力を`build(decision: RetryNotificationDecision)`へ変更
- Domain Modelを`RetryNotificationMessage(body: str)`のみへ縮小
- Dependencyを`retry_notification_message → retry_notification`のみへ限定

**その他検討した入力設計案**（1回目レビュー前の内部検討）

| 案 | 却下理由 |
|---|---|
| `build(alert: RetryAlert, decision: RetryNotificationDecision)` | AlertとDecisionの不整合入力（例：`level=NONE`かつ`status=NOTIFY`）を型として許してしまい、事後検証コードが必要になる。最終的にDecision単独入力を採用したことで、この問題は型として発生し得ない構造になった |
| `RetryNotificationDecision`へ重大度フィールドを追加 | Design Freeze済み・commit済みのv6.6.0 Public APIの変更となり、スコープ逸脱 |

---

## 27. Rejected Designs

| # | 却下した設計 | 理由 |
|---|---|---|
| 1 | Message＝固定文字列（Domain Objectなし） | 既存4 Foundation全てがfrozen dataclassでラップする慣習と非対称 |
| 2 | Message＝title＋body | テンプレート・Localizationを導入しない前提でYAGNI |
| 3 | Message種別Enumの新設 | `RetryAlertLevel`との実質1:1写像で語彙重複、分岐の意図がない |
| 4 | `RetryNotificationMessageEvaluator`命名 | 「判定」ではなく「値の組み立て」が実体と乖離 |
| 5 | `RetryNotificationMessageFactory`命名 | 単一型生成に対しGoF Factoryパターンの含意が過大 |
| 6 | 重大度別（WARNING/CRITICAL）Message | `RetryNotificationDecision`のみを入力とする設計上、Builderは重大度を判別できない。Future Candidateへ送付 |
| 7 | NO_NOTIFICATIONで`None`返却 | Total Function契約に反する（v6.6.0却下案と同型） |
| 8 | 既存`retry_notification`パッケージへ追加 | Judgment Only Foundationという既存の性格付けを崩す |

---

## 28. Risks

- Package数の増加（本Releaseで5パッケージ目）。Channel・Senderも同型パターンを踏襲すると7パッケージまで増える見込みで、Package命名・配置のガバナンス方針が未確立（29章Technical Debtに記録し、本Releaseでは新規ルール化しない）
- 「NOTIFYの場合のみBuilderを呼ぶ」という呼び出し契約はコード上の型では強制できず、ドキュメントとFail Fast例外に依存する。将来のRuntime Wiring実装時に呼び出し順序を誤るリスクが残る（実害はFail Fastで即座に検知されるため限定的）
- 固定Message文言の日本語表現の妥当性は本文書で確定させておらず、実装・Code Reviewフェーズでの調整余地を残す

## 29. Technical Debt

1. Messageは重大度を保持しない
2. 重大度が必要な消費者は元の`RetryAlert`を参照する必要がある
3. WARNING／CRITICALは共通Messageになる
4. title、timestamp、reason、対象情報を持たない
5. 重大度別Message導入時は入力契約またはComposition再検討が必要
6. Package数が増加しており、Channel／Sender追加時にPackage Governance確認が必要（本Releaseでは新規ルール化せず、Technical Debtとして記録するのみ）

## 30. Known Issues

実装完了後の既存Regression Suite（v5.9.0〜v6.6.0、826/826 PASS）にベースライン差分は発生していない（新規Known Issueなし。2026-07-15時点の最新は引き続き`[KI-29]`、解消済み）。

## 31. Future Candidates

- Retry Notification Channel Foundation
- Retry Notification Delivery／Sender Foundation
- Retry Alert／Notification Message CLI Report Wiring Foundation
- Severity-aware Message Foundation
- Message Template Foundation
- Localization
- Runtime／Scheduler Integration
- Suppression
- Deduplication
- Rate Limiting

順序は確定事項として固定せず、Release 6.7完了後に改めて比較する。

---

## 32. Documentation Update Plan

**Design Freezeフェーズ（Release 6.7 Architecture Design）で更新済み**：本設計書（新規）、`docs/architecture.md`、`docs/ROADMAP.md`（いずれも設計内容の反映）

**実装・Test Review・Code Review・Regression完了後（Release 6.7 Documentation Updateフェーズ）で更新済み**：

- `docs/CHANGELOG.md`へのv6.7.0完了記録
- `docs/architecture.md`のv6.7.0セクションを実装完了状態へ更新
- `docs/ROADMAP.md`のv6.7.0項目を実装完了状態へ更新
- `docs/design/retry_notification_foundation.md`のStatus章修正（Release 6.6完了実績に基づく記載漏れの是正。Release 6.6の設計内容変更ではなく、Known Issue追加も不要）
- 本設計書のStatus／Definition of Done（33章）を実績に合わせて更新

**未実施（最終Release Reviewフェーズ）**：commit／push（人間承認後）

---

## 33. Definition of Done

- [x] `src/retry_notification_message/`実装完了（2ファイル＋`__init__.py`）
- [x] 新規E2Eテスト全PASS（21シナリオ・117アサーション・117/117 PASS、終了コード0、警告なし）
- [x] 既存Regression Suite（v5.9.0〜v6.6.0）がベースライン件数（826/826）のまま全件PASSする
- [x] 既存Regressionテストファイルに意図しない変更がない
- [x] 依存方向テスト（AST解析、`retry_notification_message → retry_notification`のみ・逆依存なし・Alert/Monitoring/Metrics/Runtime系への非import確認）PASS
- [x] 本設計書作成・ChatGPT Architecture Review（1回目「Changes Required」・指摘反映・2回目「Approved」）・Design Freeze
- [x] 人間の実装承認
- [x] Test Review（Approved）
- [x] Code Review（Approved。Public API検査が`__all__`の集合一致のみでは名前空間全体の想定外露出を保証できない点を1件発見し、E2Eテストへ`hasattr()`検査を追加して解消。production code修正なし）
- [x] `docs/CHANGELOG.md`反映
- [x] `docs/architecture.md`反映
- [x] `docs/ROADMAP.md`反映
- [x] `docs/design/retry_notification_foundation.md` Status章修正
- [ ] Release Reviewにおいて`git diff --name-status` / `git status --short`で既存コード無改修を確認（最終Release Review待ち）
- [ ] commit／push（人間承認後）

---

## 34. Design Freeze

このArchitecture Designは、ChatGPT Architecture Reviewを2回経て確定した。

- **1回目「Changes Required」**：入力設計（`RetryAlert`単独入力）・Domain Model（`level`保持）・Dependency方向（`retry_alert`への直接依存）の3点について修正指摘を受けた
- **修正内容**：入力を`RetryNotificationDecision`単独へ、Domain Modelを`body`のみへ、Dependencyを`retry_notification`のみへの直接依存へ、それぞれ修正した
- **2回目「Approved」**：修正内容が承認され、Design Freezeが確定した

Release 6.7の実装は、このDesign Freezeされた設計に従う。

実装中に以下の変更が必要になった場合は、実装を停止してArchitecture Reviewへ戻る。

- Public API変更
- `RetryNotificationMessage`のフィールド変更
- import依存方向変更
- 実送信や外部I/Oの追加
- Runtime／Composition Rootへの接続
- 重大度別Message・Suppression等の追加
- 既存production codeの変更

**2026-07-15追記（実装・Test Review・Code Review・Regression完了）**：本Design Freezeからの逸脱は発生しなかった。上記のいずれの変更（Public API・フィールド・import方向・外部I/O・Runtime接続・重大度別Message・既存production code変更）も生じておらず、Architecture Reviewへの差し戻しは発生していない。新規E2E（21シナリオ・117アサーション・117/117 PASS）・既存Regression（v5.9.0〜v6.6.0、826/826 PASS、合計943/943 PASS）とも完全PASSし、Test Review「Approved」・Code Review「Approved」を得た。
