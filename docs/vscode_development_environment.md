# VS Code 開発環境ガイド v1.0

作成日：2026-06-27

---

## 1. 目的

このドキュメントは、今後PCを追加・買い替えした場合でも、同じ開発環境を再現できるようにするためのものです。

新しいPCでもこのガイドの手順通りにセットアップすれば、すぐに開発を始められる状態を目指します。

---

## 2. 現在インストール済みの VS Code 拡張機能

以下の拡張機能をインストールしてください。

| 拡張機能名 | 拡張機能ID |
|---|---|
| Claude Code for VS Code | anthropic.claude-code |
| Python | ms-python.python |
| Pylance | ms-python.vscode-pylance |
| Python Debugger | ms-python.debugpy |
| Python Environments | ms-python.python-environment-manager |
| Japanese Language Pack for Visual Studio Code | ms-ceintl.vscode-language-pack-ja |
| Markdownlint | davidanson.vscode-markdownlint |
| Error Lens | usernamehw.errorlens |
| GitLens | eamodio.gitlens |

---

## 3. 拡張機能ごとの役割

### Claude Code for VS Code
AIアシスタント「Claude」をVS Code内で使えるようにする拡張機能です。コードの作成・修正・説明をClaude Codeに依頼できます。このプロジェクトの開発の中心的なツールです。

### Python
PythonのプログラムをVS Codeで動かすための基本拡張機能です。Pythonをインストールした後、この拡張機能を入れることでVS Codeがプログラムを認識できるようになります。

### Pylance
Pythonのコードを書くときに、ミスを事前に教えてくれたり、単語の補完をしてくれたりする拡張機能です。コーディングのスピードと正確さが上がります。

### Python Debugger
プログラムが思い通りに動かないとき、どこで問題が起きているかを一行ずつ確認（デバッグ）できる拡張機能です。エラーの原因を特定するときに役立ちます。

### Python Environments
複数のPython環境（仮想環境）を管理するための拡張機能です。プロジェクトごとに独立した環境を用意することで、ライブラリのバージョン違いによるトラブルを防げます。

### Japanese Language Pack for Visual Studio Code
VS CodeのメニューやUIを日本語に切り替える拡張機能です。英語が苦手でも使いやすくなります。

### Markdownlint
Markdownファイル（`.md`）を書くときに、書き方のルール違反を教えてくれる拡張機能です。設計資料やドキュメントを整った形式で書くために使います。

### Error Lens
プログラムのエラーや警告を、コードの右側にインライン表示してくれる拡張機能です。問題箇所がひと目でわかりやすくなります。

### GitLens
Gitの履歴情報をVS Code内で確認できる拡張機能です。「このコードをいつ・誰が・なぜ変更したか」をエディタ上で直接確認できます。

---

## 4. 今は不要な拡張機能

以下の拡張機能は現時点では使用しないため、インストール不要です。ただし、将来的に必要になった場合は「7. 今後追加を検討するもの」を参照して導入してください。

| 拡張機能名 | 理由 |
|---|---|
| GitHub Pull Requests | 現時点ではPull Request運用をしていない |
| Container Tools | Docker未使用のため不要 |
| GitHub Copilot | Claude Codeで代替しているため不要 |

---

## 5. 推奨運用

### 作業開始時
```
git pull
```
リモートリポジトリ（GitHub）の最新状態を取得します。他のPCで作業した内容や過去の変更を取り込むために行います。

### 作業前
```
git status
```
現在どのファイルが変更されているかを確認します。作業を始める前に、変更状態をクリーンにしておくと安全です。

### 作業終了時
```
git status           # 変更ファイルを確認
git add .            # 変更をステージング（コミット準備）
git commit -m "..."  # 変更内容をコミット（記録）
git push origin main # GitHubへ送信
```

### 絶対に守るルール

- **`.env` ファイルは絶対にコミットしない**
  APIキーやパスワードが入っているため、GitHubに上がると悪用される危険があります。

- **APIキーやパスワードは画面共有・スクリーンショットに写さない**
  オンライン通話中や画像として保存するときに、誤って漏れることを防ぎます。

---

## 6. Claude Code と ChatGPT の役割分担

この開発では、Claude Code と ChatGPT をそれぞれ得意な分野で使い分けます。

### ChatGPT の担当
- **設計**：機能の仕様・構成を決める
- **プロジェクト管理**：優先順位・スケジュールを整理する
- **レビュー**：完成したコードや文書の品質確認
- **リリース判断**：公開・運用開始のタイミングを判断する

### Claude Code の担当
- **実装**：実際にコードを書く
- **テスト**：動作確認・バグ修正
- **Git操作**：コミット・プッシュなどのバージョン管理
- **ファイル編集**：ファイルの作成・修正・削除

---

## 7. 今後追加を検討するもの

以下は現時点では導入しませんが、開発が進んだタイミングで追加を検討してください。

### GitHub Pull Requests
- **導入タイミング**：Pull Request運用を本格化した場合
- **何ができるか**：VS Code内でPull Requestの作成・レビュー・マージができるようになります

### Container Tools
- **導入タイミング**：Dockerを使う開発を始めた場合
- **何ができるか**：Dockerコンテナの管理をVS Codeから行えるようになります

### GitHub Copilot
- **導入タイミング**：Claude Code以外の補助が必要になった場合
- **何ができるか**：GitHubが提供するAIコード補完ツールです。Claude Codeと並行して使うことも可能です
