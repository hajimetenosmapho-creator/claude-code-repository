# Release 2.8 Project Charter

## Execution History Foundation

## 1. Release目的

Release 2.8 では、Workflow Engine の実行履歴を管理する基盤を実装する。

Release 2.7 で Scheduler から Workflow Engine を通じて各 Agent を直列実行する基盤が整備された。

一方で、現時点では以下の情報を体系的に保持する仕組みが不足している。

* Workflow がいつ開始されたか
* Workflow がいつ終了したか
* Workflow が成功したか失敗したか
* 各 Step がどの順番で実行されたか
* 各 Step の実行結果
* エラー発生箇所
* 実行時間
* 将来的な監視・再実行・分析に必要な履歴情報

そのため、本 Release では Workflow 実行履歴を保存・参照できる最小基盤を構築する。

## 2. 背景

Release 2.x では、以下の基盤が順次整備された。

* Automation Foundation
* News Agent Foundation
* Workflow Trigger Agent Foundation
* Publish Trigger Agent Foundation
* Review Trigger Agent Foundation
* Scheduler Agent Foundation
* Workflow Engine Foundation

これにより、Scheduler から Workflow Engine を起動し、NewsAgent、ReviewTriggerAgent、PublishTriggerAgent を順番に実行する構成が成立した。

次の段階では、実行された Workflow の状態を記録し、運用時に確認できる仕組みが必要となる。

Execution History Foundation は、今後の以下の機能の前提基盤となる。

* Workflow Monitor
* Retry Engine
* Metrics Foundation
* Dashboard Foundation
* Error Analysis
* AI Improvement Platform との連携

## 3. Scope

本 Release で対象とする範囲は以下とする。

### 実装対象

* Execution History 用パッケージの新規作成
* Workflow 実行履歴モデル
* Step 実行履歴モデル
* Event 実行履歴モデル
* ExecutionHistoryManager
* ExecutionHistoryStore
* JSON ファイルベースの保存実装
* Workflow Engine からの履歴記録連携
* 実行履歴確認用スクリプト
* 単体テスト
* E2Eテスト
* 関連ドキュメント更新

## 4. Out of Scope

本 Release では以下は対象外とする。

* Retry Engine の実装
* Web Dashboard の実装
* Slack / Discord / LINE 通知
* DB 永続化
* 詳細なメトリクス分析
* APIコスト集計
* Claude API 使用量集計
* 並列 Workflow 実行管理
* 履歴検索 UI
* 履歴削除・アーカイブ機能

これらは後続 Release の対象とする。

## 5. 成果物

本 Release の成果物は以下とする。

* `src/execution_history/` パッケージ
* Workflow 実行履歴データモデル
* Step 実行履歴データモデル
* Event 履歴データモデル
* ExecutionHistoryManager
* JSON Store 実装
* Workflow Engine との連携
* `scripts/show_execution_history.py`
* テストコード
* E2Eテスト
* CHANGELOG 更新
* ROADMAP 更新
* architecture.md 更新

## 6. 想定ディレクトリ構成

```text
src/execution_history/
├── __init__.py
├── execution_history_config.py
├── execution_history_event.py
├── workflow_execution_record.py
├── step_execution_record.py
├── execution_history_store.py
├── json_execution_history_store.py
└── execution_history_manager.py

scripts/
└── show_execution_history.py

tests/
└── test_execution_history_foundation.py
```

## 7. 成功条件

Release 2.8 の成功条件は以下とする。

* Workflow 実行開始時に履歴が作成される
* Workflow 実行終了時に成功・失敗が記録される
* 各 Step の開始・終了・成功・失敗が記録される
* エラー発生時にエラー情報が記録される
* JSON ファイルとして履歴が保存される
* 保存された履歴をスクリプトで確認できる
* 既存 Workflow Engine の動作を壊さない
* 既存テストがすべて PASS する
* 新規テストが PASS する
* origin/main に push 可能な状態まで整理できる

## 8. 設計方針

設計方針は以下とする。

* 既存 Workflow Engine への変更は最小限にする
* 履歴管理は独立パッケージとして分離する
* 将来的な DB 化を見据え、Store インターフェースを分ける
* 初期実装は JSON ファイル保存とする
* テストしやすい dataclass 中心の設計にする
* 失敗時にも履歴が残る構成にする
* 実行結果と実行履歴を混同しない
* Monitoring / Retry / Metrics の前提として拡張しやすくする

## 9. リスク

想定されるリスクは以下とする。

* Workflow Engine と History Manager の責務が混ざる
* 履歴データが肥大化する
* エラー時に履歴保存まで失敗する
* JSON 保存形式が後続機能の制約になる
* 既存テストへの影響が出る

## 10. リスク対策

* Workflow Engine は実行制御に集中させる
* ExecutionHistoryManager に履歴管理責務を集約する
* Store インターフェースを定義し、保存方式を差し替え可能にする
* 初期保存項目は最小限にする
* 例外発生時も finally 相当で履歴確定処理を行う
* 既存 E2E テストを必ず実行する

## 11. 完了定義

以下を満たした時点で Release 2.8 完了とする。

* Project Charter 作成完了
* Architecture Design 作成完了
* Architecture Review 実施完了
* 実装完了
* 単体テスト PASS
* E2Eテスト PASS
* CHANGELOG 更新
* ROADMAP 更新
* architecture.md 更新
* git status clean
* commit 完了
* origin/main へ push 完了
