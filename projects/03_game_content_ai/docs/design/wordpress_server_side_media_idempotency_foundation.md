# WordPress Server-Side Media Idempotency Foundation — Architecture Design（Release 6.38.0）

## 0. Status

- **Status: ARCHITECTURE RE-REVIEW APPROVED（Amendment A18・Review #26：APPROVED、Blocking 0／Major 0／Minor 2。設計文書の内部整合性とsource上の事実の判定であり、runtime（実環境）の項目は未検証・実装未着手。Architecture Human Gate（21章の5論点）は、ユーザーが個別にACCEPT済み（2026-10-07）。Implementation Start Validation・Production実装・`git tag`は別のHuman Gate）。**
  - **経緯**：A13テキストに対するCodex High独立再レビュー（Review #21）は**APPROVED**で、commit `2513ae5`のdocs-only checkpointとして確定した。その後の**Implementation Start Validation（2026-10-06、WordPress 7.1.1 tag sourceのread-only確認）で、承認済みArchitectureの前提誤り（U-18・U-2・U-19。17.5節）が判明した**。**Review #21のAPPROVEDは、設計文書の内部整合性の判定であり、未検証前提を確認済みとするものではなかった**ため、承認は現行本文には及ばない。A14が12章を再設計し、A14に対するReview #22（NOT APPROVED、Blocking 1／Major 3／Minor 2）の指摘にA15が、A15に対するReview #23（NOT APPROVED、Blocking 1／Major 4／Minor 1）の指摘にA16が、A16に対するReview #24（NOT APPROVED、Blocking 0／Major 2／Minor 1）の指摘にA17が、A17に対するReview #25（NOT APPROVED、Blocking 0／Major 2／Minor 1）の指摘にA18が対応した。A18に対するReview #26は**APPROVED**（Blocking 0／Major 0／Minor 2）で、Minor 2件（V-16の記述、現在地表記）は文書の同期のみで対応した（契約・ID・scope・テスト・台帳の内容は変更していない）。このAPPROVEDは、設計文書の内部整合性と、canonical・auxiliary sourceのsource上の事実への照合の判定であり、runtime（実環境）の項目を確認済みとするものではない（17.6節。Review #21のAPPROVEDが後に前提誤りで覆された経緯と同じ限界）。**Release scope（Consumer-less Foundation、Python integration・production deploymentはOut of Scope）は変更していない**。MVP COMPLETE（v6.35）は再オープンしない。
  - A1テキストに対するCodex High独立レビュー（Review #9）は**NOT APPROVED**（Blocking 0／Major 7／Minor 1／Suggestion 1）であった。A2は同Findings（M1〜M7＋Minor＋Suggestion）への最小修正であり、A1の骨格は維持している。
  - A2テキストに対するCodex High独立再レビュー（Review #10）は**NOT APPROVED**（Blocking 2（B1・B2）／Major 3（M-A〜M-C）／Minor 3（N1〜N3）／Suggestion 0）であった。Review #10は、Review #9のM1・M2・M6・M7・Minorを閉じたと判定し、M3・M4・M5・Suggestionを部分的closureとした。A3はReview #10のFindingsへの最小修正であり、A2の骨格は維持している。
  - A3テキストに対するCodex High独立再レビュー（Review #11）は**NOT APPROVED**（Blocking 0／Major 5（M1〜M5）／Minor 2／Suggestion 0）であった。A4はReview #11のFindingsへの最小修正であり、A3の骨格は維持している。
  - A4テキストに対するCodex High独立再レビュー（Review #12）は**NOT APPROVED**（Blocking 1（A4-B1）／Major 2（A4-M1・A4-M2）／Minor 3／Suggestion 0）であった。Review #12は、Review #11のM3・M4・M5・N1・N2を閉じたと判定し、M1・M2を部分的closureとした。A5はReview #12のFindingsへの最小修正であり、A4の骨格は維持している。
  - A5テキストに対するCodex High独立再レビュー（Review #13）は**NOT APPROVED**（Blocking 0／Major 3（M1〜M3）／Minor 0／Suggestion 0）であった。Review #13は、Review #12の全Findings（A4-B1・A4-M1・A4-M2・Minor 3件）を閉じたと判定した。A6はReview #13のFindingsへの最小修正であり、A5を維持している。
  - A6テキストに対するCodex High独立再レビュー（Review #14）は**NOT APPROVED**（Blocking 1（B1）／Major 1（M1）／Minor 1（N1）／Suggestion 0）であった。Review #14は、Review #13のM3を閉じ、M1・M2を部分的closureとした。A7はReview #14のFindingsへの最小修正であり、A6を維持している。
  - A7テキストに対するCodex High独立再レビュー（Review #15）は**NOT APPROVED**（Blocking 1（B1）／Major 2（M1・M2）／Minor 1（N1）／Suggestion 0）であった。Review #15は、Review #14のM1・N1を閉じ、B1を部分的closureとした。A8はReview #15のFindingsへの修正であり、**A7のresponse-class 3-way dispatchを廃止し、authoritative outcome marker方式へ置換した**（A7を基礎とするが、B1は設計方針の変更を伴う）。A8テキストに対する再レビュー（Review #16）は未実施。
  - A8テキストに対するCodex High独立再レビュー（Review #16）は**NOT APPROVED**（Blocking 1（B1）／Major 1（M1）／Minor 2（N1・N2）／Suggestion 0）であった。Review #16は、Review #15のM1・M2・N1を閉じ、B1を部分的closureとした。A9はReview #16のFindingsへの最小修正であり、A8を維持している（B1は案Bを採用）。
  - A9テキストに対するCodex High独立再レビュー（Review #17）は**NOT APPROVED**（Blocking 1（B1）／Major 1（M1）／Minor 0／Suggestion 0）であった。Review #17は、Review #16のM1・N1・N2を閉じ、B1を部分的closureとした。A10はReview #17のFindingsへの修正であり、A9を維持している（Finalizerの適用runtime失敗の契約を12章だけに正本化し、他章は参照のみに整理）。A10テキストに対する再レビュー（Review #18）は未実施。
  - A10テキストに対するCodex High独立再レビュー（Review #18）は**NOT APPROVED**（**Blocking 0**／Major 2（M1・M2）／Minor 2（N1・N2）／Suggestion 0）であった。Review #18は、Review #17のM1を閉じ、B1を部分的closureとした。A11はReview #18のFindingsへの最小修正であり、A10を維持している。A11テキストに対する再レビュー（Review #19）は未実施。
  - A11テキストに対するCodex High独立再レビュー（Review #19）は**NOT APPROVED**（**Blocking 0**／Major 1（M1）／Minor 0／Suggestion 0）であった。Review #19は、Review #18のM2・N1・N2を閉じ、M1を部分的closureとした。A12はReview #19のMajor M1だけへの修正であり、A11を維持している。A12テキストに対する再レビュー（Review #20）は未実施。
  - A12テキストに対するCodex High独立再レビュー（Review #20）は**NOT APPROVED**（**Blocking 0**／Major 1（M1）／Minor 1／Suggestion 0）であった。Review #20は、Review #19のM1を部分的closureとした。A13はReview #20のM1・Minorだけへの修正であり、新しい設計判断・scope変更を含まない。A13テキストに対する再レビュー（Review #21）は未実施。
  - 旧Draftの「ARCHITECTURE APPROVED」は**撤回**した。理由：(a) 承認の根拠とされたRound 1〜13／Codex計8回のレビューは会話上でのみ実施され、repo内に再現可能な証跡が存在しない、(b) Amendment A1で設計の中核（idempotency identity・PROCESSING/CONFIRMED状態機械・DB epoch保証範囲・Scope）を実質的に変更したため、旧承認は現行本文には及ばない。
  - Production code（`src/` / `scripts/` / `tests/` / `wordpress/` 配下を含む）は本書作成時点で一切実装されていない。
- **Amendment A1（2026-10-06）**：本書は旧Draft（2026-09-22版、Round 1〜13統合）を破棄せず、以下を修正した版である。変更点の一覧は**24章**に集約する。
  1. Status撤回・Re-review Required化（本章）
  2. Scope/Goalの再定義：6.38は**Consumer-less Foundation**（2章・3章）
  3. Current Architectureの反映：v6.32のwrite-ahead/fail-closed/`HUMAN_REVIEW_REQUIRED`配線済みを前提とした問題の再定義（1章）
  4. Idempotency identityの再定義：image bytes digest・`attempt_ordinal`・`root_run_id`をkeyに使わない（7.4〜7.6節）
  5. PROCESSING/CONFIRMEDの厳密化（10章）
  6. Python HRRとの互換性（23章）
  7. Stable Authoritative DB Epochの保証範囲限定（6章）
  8. Draft内矛盾の解消：実確認済み／自己記録／未確認の分離（17章）、テスト責務の3層分離（15章）
- **Amendment A2（2026-10-06）**：Review #9（A1）のFindingsへの最小修正。変更点は**24章（24.2節）**に集約する。
  - M1：25章のレビュアー宛て命令文を撤回し、非拘束の記述へ書き直し（A4でさらに「設計判断・検証の対応表」へ置き換え）
  - M2：既存Pythonの`article_identity`がattempt-scopedであることを正確に記載（1.2・7.5節）、stable identity sourceをIntegration Releaseの必須preconditionとして明記（7.7節）
  - M3：claim前／claim後のHTTP・error contractを一義化（8.3節）
  - M4：3接続の同一authoritative binding（9.3節）
  - M5：closed allowlistを設計時点で確定（8.1節）
  - M6：multisiteの実行時fail-closed契約（5.5節）
  - M7：DB restart後のdurability検証シナリオ（15章 T-25）
  - Minor：C6を分離（10.6節）／Suggestion：`claim_token`の仕様（7.8節）
- **Amendment A3（2026-10-06）**：Review #10のFindingsへの最小修正。変更点は**24章（24.3節）**に集約する。
  - B1：`gca_claim_state = none`を「identity未消費の証拠」とする定義を撤回。`none`は「この requestはclaimを確立せずCoreも呼んでいない」だけを示し、`gca_claim_state`はretry authorizationではない（8.3節）
  - B2：claim確立後は`none`へ戻らない。post-claimのBinding／Epoch再確認失敗は`PROCESSING`を保持し409 `processing`。pre-claimのみ503 `none`（9.3節 R1／R2／R3）
  - M-A：成功応答（201／200）とerror応答の形を一義化（8.3節「応答の形」、12章）
  - M-B：claim前body size上限を33,554,432バイトに確定し、導出・根拠・413を定義（8.1節）
  - M-C：claim確立後〜Core呼出前の捕捉可能な内部障害を8.3節の表・10.6節（C1a／C1b）・テスト（T-28）へ追加
  - N1：`claim_token`を`random_bytes(32)`相当＝ちょうど256bit＝64桁hex＝`CHAR(64)`に厳密化（7.8節）
  - N2：255文字filename上限を「現行Uploaderと同一」とした誤記を削除し、plugin独自contractと明記（8.1節）
  - N3：MVP RoadmapのImplementation Start Validation対象をU-1〜U-16へ更新
- **Amendment A4（2026-10-06）**：Review #11のFindingsへの最小修正。変更点は**24章（24.4節）**に集約する。
  - M1：応答表の不足2ケースを追加（`INSERT`がACK済みだがaffected rows≠1かつduplicate-keyでない→503 `gca_idempotency_claim_indeterminate`／`unknown`。`CONFIRMED` duplicateでMedia Verificationが完遂不能→503／`confirmed`、欠落確定→409／`confirmed_inconsistent`、いずれもCore再実行禁止）（8.3・10.2・10.3・10.6節、T-31・T-32）
  - M2：初回201・replay 200とも同一のcanonical payload（`id`／`source_url`／`mime_type`／`slug`／`gca_claim_state`の5 field）。Core response全文は透過・永続化しない。snapshotは4項目のみ（8.3・12章、V-10）
  - M3：32 MiB上限をplugin独自v1 policyとし、「現行／正規画像をすべて受理できる」保証を削除。正当な入力でも超過すれば413で拒否されうることを明記（8.1節、V-9）
  - M4：MVP Roadmapのgate記述を、特定のAmendment番号・固定件数に依存しない条件へ更新
  - M5：旧25章のメタ記述を削除し、設計判断・検証の対応表へ置き換え
  - N1：8.1節の`claim_state`表記を`gca_claim_state`へ統一／N2：現行filename生成contractから最大長（65文字）を算出し、「未確認」の記述を削除（8.1節、V-8）
- **Amendment A5（2026-10-06）**：Review #12のFindingsへの最小修正。変更点は**24章（24.5節）**に集約する。
  - A4-B1：finalizationの所有者と順序を統一。**route callbackが**Core成功→4項目検証→snapshot保存→`CONFIRMED`化（durable ACK確認）→success responseを担い、**`rest_pre_echo_response`のFinalizerは、state変更・検証・DB保存・DB読取りを一切せず、永続化済みsnapshotからcanonical 5-field payloadへ全置換するだけ**（10.4・12章、T-16・T-34。**A6で、置換の対象をdataに加えHTTP statusにも拡張し、request-local contextの束縛を追加**）**（A14で、投影hookは`rest_pre_echo_response`から`rest_post_dispatch`へ変更。当時の「`rest_pre_echo_response`でstatusを置換する」前提は偽と判明し撤回。現行は12.1節）**。Core成功後のsnapshot validation failure（`source_url`欠落・不正等）を8.3節の応答表・crash table（C10）に追加（T-33）
  - A4-M1：Goal G2を修正し、「Python側にidempotency結果・claim stateを持たせない」と「stable identityのdurable保持（Integration Release）」を明確に分離（3章）
  - A4-M2：T-23eを、R1・R2通過後のR3でのBinding mismatch fault injectionとして到達可能に修正。静的な別schema構成はT-23f（R1で503 `none`・claim 0）として分離（15章）
  - Minor：用語集の`gca_claim_state`への統一（4章）／23章の503 `confirmed`にC9を追加／T-29 L3の前提条件（下位層body上限を上限+1バイトより大きく設定できたことのevidence）（15章、U-16）
- **Amendment A6（2026-10-06）**：Review #13のFindingsへの最小修正。変更点は**24章（24.6節）**に集約する。
  - M1：**Finalizerをcanonical success responseの最終所有者**とし、**dataとHTTP statusの両方**を置換（first success＝201、confirmed replay＝200）。request-local contextを**plugin-private・write-once**とし、exact requestのinstance identity・idempotency identity・success mode・expected status・durable snapshotに束縛。Finalizerは束縛を確認してから置換し、missing／不一致／不正ならcanonical successを返さずfail-closed。**偶発的なcontext混入の防止であり、co-resident malicious codeは脅威モデルに加えない**（12章、10.4・11.2・8.3節、T-16・T-30・T-34、C5、U-18）
  - M2：T-22の「claim後はすべて409」という旧一般化を削除し、8.3節の正本応答表に従うmatrix testへ変更（PROCESSING系＝409 `processing`、ACK曖昧＝503 `unknown`、Finalizer failure＝503 `confirmed`、`CONFIRMED` duplicateのVerification不能＝503 `confirmed`、confirmed inconsistency＝409 `confirmed_inconsistent`を明示）（15章）**（A9で、「Finalizer failure＝503 `confirmed`」は廃止。Finalizerの適用runtime失敗の挙動は12章の保証境界が正本。A10で、A9の「`gca_claim_state`を欠く応答」という記述も廃止。24.9節・24.10節）**
  - M3：18章から、実装後でなければ確認できないL1 golden-vector実装適合を削除し、20章の実装フェーズgateへ移動。18章は実装前に確認可能なarchitecture／environment／source前提のみに限定（18章・20章）
- **Amendment A7（2026-10-06）**：Review #14のFindingsへの最小修正。変更点は**24章（24.7節）**に集約する。
  - B1：**Finalizerの発動判定を、contextの有無ではなくresponse classで規定**（GCA-tagged requestの最終応答に対する3分岐）。**class A＝2xx**：valid success contextを必須とし、valid→canonical payload＋201／200、欠落・不一致・不正→canonical success禁止・503 `unavailable`／`confirmed`（E9）。**class B＝non-2xxで8.3節のcanonical error**：success contextを要求せずそのまま通す。**class C＝non-2xxでcanonical errorとして検証できない**：503 `unavailable`／`unknown`（E5）へfail-closed（retry authorizationではない）。12章・8.3節・10.6節C5・T-22・T-34（c1・d）を同期
  - M1：23章とD-4に残っていた「claim後の失敗はすべて409 `processing`」という旧一般化を削除し、claim後も8.3節の正本matrixに従い409 `processing`／503 `unknown`／503 `confirmed`／409 `confirmed_inconsistent`等があり得ることへ統一
  - N1：全canonical errorについて、固定message文字列を8.3節に正本化。status・error code・message・`gca_claim_state`の組合せを閉集合（E1〜E9）として定義し、T-22で完全一致を検証。自由文・Core由来messageは外部へ透過しない
  - **（A8で置換）上記のB1のresponse class分岐（class A／B／C）は、A8で廃止され、authoritative outcome marker方式に置き換えられた**。現行の規範は12章・8.3節であり、A7の分岐の記述は履歴としてのみ残る
- **Amendment A8（2026-10-06）**：Review #15のFindingsへの修正。変更点は**24章（24.8節）**に集約する。
  - B1：**A7のresponse-class 3-way dispatchを廃止**。plugin control path（ラップしたpermission_callbackとroute callback。**A16で、permission_callbackは置換せずmarkerに関与させない方式へ変更。control pathはroute callbackだけ**）が、各GCA requestについて**plugin-private・write-once・request-localのauthoritative outcome marker**（`SUCCESS_FIRST`／`SUCCESS_REPLAY`／`E1`〜`E9`）を確定し、**Finalizerはpre-Finalizerの応答のstatus・data・種別を判断材料にせず、markerだけから最終response（statusとdata）を新規構築・完全置換**する。`SUCCESS_FIRST`はdurable ACK後のみ、`SUCCESS_REPLAY`はVerification成功後のみ設定。markerはexact request instanceに束縛し、二重設定・欠落・不正・別request markerはE5へfail-closed。pre-Finalizerのcallbackがsuccess↔error・1xx／3xx・任意bodyへ変更しても、valid markerから復元（12章・8.3節・10.4節・C5／C5b・T-07・T-16・T-22・T-34）
  - M1：`X-GCA-Identity-Schema`のclient供給値の不一致を**E1／400に統一**。server内部のschema／DB／epoch／configurationの不一致は**E4／503**として区別（6.5・7.4・8.2・8.3節、T-09・T-18）
  - M2：Finalizerが**markerからresponseを新規構築**し、成功＝ちょうど5 key、error＝ちょうど3 key（`data`はちょうど2 key）の**exact key setだけ**を出力する契約とした。incoming responseのkey集合の判定に依存しない。余分なfieldが最終responseに残らないことをT-22(11)・T-34(d5)で検証
  - N1：1xx／3xxを含むpre-Finalizer statusの改変をT-34(d)で検証（valid markerあり→markerのcanonical outcomeへ復元、marker無し・不正→E5）
- **Amendment A9（2026-10-06）**：Review #16のFindingsへの最小修正。変更点は**24章（24.9節）**に集約する。
  - B1（**案Bを採用**）：valid markerからのcanonical response選択・構築を、**totalかつ一意**とし、markerはFinalizerの動作で変更しない。**Finalizerによる応答への「適用そのもの」のruntime失敗では、E9へのfallbackを試みず、canonical responseを保証しない**（durable claim・markerは不変。clientはretry可否をその応答だけから判断しない）。**（A10で訂正：A9の「`gca_claim_state`を欠くnon-canonical／transport／runtime failureとして扱う」は、強制できない主張のため廃止。応答内容は未定義で、挙動は12章の保証境界が唯一の正本）****E9は、plugin control pathが`E9` markerを明示的に設定する場合（`CONFIRMED` duplicateのVerification不能）に限定**。A6〜A8の「Finalizer failure→E9／confirmed」は廃止（12章・8.3節・C5・T-07・23章・D-4・D-20・R-17・R-18。R-20を追加）。U-18は、適用能力を実装開始前に確認する前提として維持
  - M1：T-22(4)を、marker欠落・不正・二重設定・別request・束縛不一致→E5、valid E9 marker→E9、valid markerからの構築は失敗しない、Finalizer適用runtime failureはcanonical E1〜E9 oracleの対象外（T-07で別ケースとして検証・記録。**A12でT-07は手順形式に変更され、現行の検証方法はT-07を参照**）、へ同期（15章）
  - N1：D-17・R-5の未検証範囲をU-1〜U-19へ同期／N2：用語集のFinalizerを「全GCA outcomeについてmarkerからcanonical HTTP responseを構築・適用する最終投影層（durable state変更・DB I/Oなし）」へ同期し、authoritative outcome markerの用語を追加（4章）
- **Amendment A10（2026-10-06）**：Review #17のFindingsへの修正。変更点は**24章（24.10節）**に集約する。
  - B1：**Finalizerの適用runtime失敗の契約を12章だけに正本化**し、他章（8.3節・10.6節C5・T-07・23章・D-4・D-20・R-17・R-20・Roadmap）は参照のみとして、重複した言い換えを削除。挙動・保証・outcome別のstateは12章を参照（本項では再記述しない。A11で、12章以外の再記述をさらに削除）。A9の「`gca_claim_state`を欠く応答として扱う」は廃止（強制できない主張のため）
  - M1：残存していた旧「Finalizer failure→503 `confirmed`」の記述（8.3節のerror形状・契約#3、23章、Roadmap／Change Record、その他）を削除・訂正し、grepで確認
- **Amendment A11（2026-10-06）**：Review #18のFindingsへの最小修正。変更点は**24章（24.11節）**に集約する。
  - M1：Finalizerの適用runtime failureの**唯一の正本を12章のみ**とし、8.3節・C5・23章・D-4・D-20・R-17・R-20・ROADMAP・MVP_COMPLETION_ROADMAPから、適用失敗時のoutcome別state・recoveryの説明を削除して、「12章に従う」旨の参照のみに整理。R-17の「E5でも`CONFIRMED`不変・replay可能」と読める記述を削除
  - M2：T-07を精密化（E1〜E4の既存claimはなし／`PROCESSING`／`CONFIRMED`のいずれもありうる。適用失敗の前後で既存のdurable stateが不変で、後続requestはその状態に応じた通常の処理になる。**層分離**：request-local内部状態（marker不変・write-once等）はL1／L2、durable DB stateと後続requestの挙動はL3、**L3から非公開markerを直接観測する前提は禁止**）。12章の表も同じstate分類に同期
  - N1：T-32のE8経路を修正（明示的な修復が完了するまで409 `confirmed_inconsistent`を維持。Binding・Verificationの環境が回復しただけでは200 replayにならない）／N2：26章の見出しを更新
- **Amendment A12（2026-10-06）**：Review #19のMajor M1だけへの修正。変更点は**24章（24.12節）**に集約する。
  - M1：Finalizerの適用runtime failureの契約を12章だけに完全に一本化。12章の表の各行に**識別子（F-1〜F-6）**を付与（契約内容は変更しない）。C11・T-22から適用failureの記述を削除して12章 F-* への参照のみとし、T-07は契約を再掲せず「F-*ごとに事前状態を用意→適用failureを注入→観測がF-*と一致」という形式へ変更。T-07固有の責務（marker内部状態＝L1／L2、durable DB state・後続request＝L3、L3からprivate markerを直接観測しない）のみを残す。ROADMAP・MVP_COMPLETION_ROADMAPから具体的な契約内容を削除し、12章への参照とArchitecture statusのみにした
- **Amendment A13（2026-10-06）**：Review #20のM1・Minorだけへの修正（新しい設計判断・scope変更なし）。変更点は**24章（24.13節）**に集約する。
  - M1：R-10の「claim後の失敗は一律409 `processing`」という旧一般化を削除し、claim確立後のHTTP outcomeは8.3節の正本matrixに従う（Finalizerの適用runtime failureは12章の保証境界に従う）という参照のみとした。全文で、claim後を409へ一般化する同義表現・古い版表記・8.3節／12章と競合する再記述を確認した
  - Minor：26章の見出しを現行Amendmentへ更新
- **Amendment A14（2026-10-06）**：Implementation Start Validationで判明した設計前提の誤り（U-18・U-2・U-19）の訂正。変更点は**24章（24.14節）**。**scope変更なし**。契約の正本は**12章**（12.1〜12.5節）。
- **Amendment A15（2026-10-06）**：Review #22（A14、NOT APPROVED）のB1／M1〜M3／N1・N2への修正。変更点は**24章（24.15節）**。**scope変更なし**。**（A16で、A15のpermission phase（PP）とPE-3は廃止）**。
- **Amendment A16（2026-10-06）**：Review #23（A15、NOT APPROVED）のB-01／M-01〜M-04／N-01への修正。変更点は**24章（24.16節）**。**scope変更なし**。`permission_callback`をmarkerから切り離し、side-effect safetyと投影を分離した。契約の正本は**12章**（SP・CS・B・BT・X）。
- **Amendment A17（2026-10-07）**：Review #24（A16、NOT APPROVED、Blocking 0／Major 2（M-A16-01・M-A16-02）／Minor 1（N-A16-01））への修正。変更点は**24章（24.17節）**。**scope変更なし。WordPress source evidenceの追加・取得・repo保存は行っていない**。method境界（effective method基準）を**12.1節 MO-1〜MO-4**として12章に正本化し、テスト節・索引・リスクの再記述を12章の識別子による参照のみへ整理し、台帳・見出しをA17現在へ同期した。Review #24で独立に照合できなかったsource依存の主張は**verifiedに格上げせず、validation-required（17.6節）**としてImplementation Start Validation（18章）に残す。契約の正本は**12章**。
- **Amendment A18（2026-10-07）**：Review #25（A17、NOT APPROVED、Blocking 0／Major 2（M-25-01・M-25-02）／Minor 1（N-25-01））への修正。変更点は**24章（24.18節）**。**scope変更なし**。Review #25でCLOSEDとなったA17の項目（M-A16-01・M-A16-02・N-A16-01）は再変更していない。`rest_post_dispatch`の**4つのcall-site（12.1節 RD-1〜RD-7）**の分類と、**`status_header`filter（12.3節 X-11）**のtopology・契約を12章に正本化し、`status_header()`の本体が供給sourceに存在することへ訂正し（V-16）、dispatch文脈別のテスト（T-37）を拡張した。**source確認だけでruntimeの項目をPASSにしない**（17.6節）。契約の正本は**12章**。
- Baseline（Architecture checkpoint `f719908`時点。ACCEPT記録（21章）の追記前）: branch `main`, HEAD=origin/main=`f7199083308672c24c7b2595ced251be53376f3c`（**Architecture checkpoint**：A14〜A18・Review #26 APPROVED・post-review docs syncをdocs-onlyで含み、**commit・push済み**）。その親は`2513ae557ca3169ad61906e2cfcba9849a1d8a3c`（A13のdocs-only checkpoint。さらにその親はRelease 6.37.0完了時点の`5974caf86d09e5e6c306a0b4e7f2002eb97ebb4b`）。**A14〜A18の変更（本書・`docs/ROADMAP.md`・`docs/MVP_COMPLETION_ROADMAP.md`）は、`f719908`でcommit・push済み**。`src/`・`tests/`・`scripts/`・`wordpress/`は変更していない。
- **旧レビュー履歴の扱い（Historical self-recorded context）**：

  | # | 対象累積Round | 記録されたVerdict | Blocking | Major | Minor |
  |---|---|---|---|---|---|
  | 1 | Round 1〜2（初期案） | NOT APPROVED | 4 | 4 | — |
  | 2 | Round 1〜5 | NOT APPROVED | 2 | 4 | — |
  | 3 | Round 1〜6 | NOT APPROVED | 0 | 4 | — |
  | 4 | Round 1〜8 | NOT APPROVED | 2 | 5 | — |
  | 5 | Round 1〜10 | NOT APPROVED | 0 | 2 | 1 |
  | 6 | Round 1〜11 | NOT APPROVED | 1 | 2 | 1 |
  | 7 | Round 1〜12 | NOT APPROVED | 0 | 1 | 0 |
  | 8 | Round 1〜13 | APPROVED（旧Draft本文に対して） | 0 | 0 | 0 |

  上表は**historical self-recorded context**であり、本書の現行内容の承認・根拠として扱わない。repo内で確認できない回数・Verdictは「過去にそう記録された」という履歴情報にとどめる。

  A1以降のレビュー（`codex-readonly-review` wrapper経由、Codex High）：

  | # | 対象 | Verdict | Blocking | Major | Minor | Suggestion |
  |---|---|---|---|---|---|---|
  | 9 | Amendment A1テキスト | NOT APPROVED | 0 | 7（M1〜M7） | 1 | 1 |
  | 10 | Amendment A2テキスト | NOT APPROVED | 2（B1・B2） | 3（M-A〜M-C） | 3（N1〜N3） | 0 |
  | 11 | Amendment A3テキスト | NOT APPROVED | 0 | 5（M1〜M5） | 2 | 0 |
  | 12 | Amendment A4テキスト | NOT APPROVED | 1（A4-B1） | 2（A4-M1・A4-M2） | 3 | 0 |
  | 13 | Amendment A5テキスト | NOT APPROVED | 0 | 3（M1〜M3） | 0 | 0 |
  | 14 | Amendment A6テキスト | NOT APPROVED | 1（B1） | 1（M1） | 1（N1） | 0 |
  | 15 | Amendment A7テキスト | NOT APPROVED | 1（B1） | 2（M1・M2） | 1（N1） | 0 |
  | 16 | Amendment A8テキスト | NOT APPROVED | 1（B1） | 1（M1） | 2（N1・N2） | 0 |
  | 17 | Amendment A9テキスト | NOT APPROVED | 1（B1） | 1（M1） | 0 | 0 |
  | 18 | Amendment A10テキスト | NOT APPROVED | **0** | 2（M1・M2） | 2（N1・N2） | 0 |
  | 19 | Amendment A11テキスト | NOT APPROVED | **0** | 1（M1） | 0 | 0 |
  | 20 | Amendment A12テキスト | NOT APPROVED | **0** | 1（M1） | 1 | 0 |
  | 21 | Amendment A13テキスト | **APPROVED**（設計文書の内部整合性。Implementation Start Validationで前提誤りが判明、下記） | 0 | 0 | 0 | 0 |
  | — | Implementation Start Validation（2026-10-06、7.1.1 tag source） | **前提誤りを検出（U-18・U-2・U-19がFAIL）** | — | — | — | — |
  | 22 | Amendment A14テキスト | NOT APPROVED | **1（B1）** | 3（M1〜M3） | 2（N1・N2） | 0 |
  | 23 | Amendment A15テキスト | NOT APPROVED | **1（B-01）** | 4（M-01〜M-04） | 1（N-01） | 0 |
  | 24 | Amendment A16テキスト | NOT APPROVED | **0** | 2（M-A16-01・M-A16-02） | 1（N-A16-01） | 0 |
  | 25 | Amendment A17テキスト | NOT APPROVED | **0** | 2（M-25-01・M-25-02） | 1（N-25-01） | 0 |
  | 26 | Amendment A18テキスト | **APPROVED**（設計文書の内部整合性とsource上の事実。runtime項目は未検証） | **0** | **0** | 2（文書の同期のみ。docs syncで対応） | 0 |

  Review #9〜#26の出力はwrapper実行時のセッション出力であり、repo内には保存されていない（historical contextとして要旨のみ19章に記録する）。
- 本書は**設計書であり実装物ではない**。18章「Implementation Start Validation Checklist」および20章のGateを満たさない限り、実装フェーズには進めない契約とする。
- 本Releaseに先立ち、クライアント側にローカル耐久状態を持たせる方式（Draft v8〜v18）、続いて「Simplification Pivot」（Named Mutex + resolver-first）を検討したが保留・棄却した。この経緯は22章に要約する（historical self-recorded）。

---

## 1. Background / Current Architecture / Problem Statement

### 1.1 Background

`src/wordpress_media/wordpress_media_uploader.py` は、WordPress Media REST API（`POST /wp-json/wp/v2/media`）へ画像バイト列をraw bodyでアップロードし `MediaUploadResult`（`media_id` / `source_url` / `mime_type`）を返す薄いクライアントである（v6.9.0）。このクライアントはidempotency metadataを一切送らず、ネットワーク断・タイムアウト・プロセスクラッシュなど「アップロード自体は成功したがクライアントがその成功を確認できない」状況に対してWordPress側に重複抑止の仕組みがない。ROADMAP上ではDI-6（Media Upload Retry／Idempotency Foundation）として追跡され、v6.28.0で記事単位のクライアント側state Foundationが完了し、v6.32でwrite-ahead配線が完了したが、**WordPress側の重複抑止**は未解決のまま残っている。

### 1.2 Current Architecture（baseline `5974caf`、本Amendmentで**repo内コード読取りにより確認**した事実）

| 層 | 現状 | 根拠 |
|---|---|---|
| `wordpress_media` | raw-body POST、`Content-Disposition`にfilenameのみ付与、timeout 30秒。idempotency key／GCAタグ／digestは送らない。応答の`id`・`source_url`・`mime_type`をparseする。5xxは`SERVER_ERROR`に分類。 | `wordpress_media_uploader.py` |
| `generated_image_wordpress_media` | `GeneratedImage`の`image_bytes`／`mime_type`を`upload()`へ渡すだけの薄いWiring層。 | `generated_image_wordpress_media_uploader.py` |
| featured media runtime／orchestrator | `image_generator.generate(prompt)` → `media_uploader.upload()`の順で、**upload試行のたびに画像を新規生成する**。画像bytesは試行間で安定しない。 | `article_featured_media_orchestrator.py:72-73` |
| `article_media_upload_state`（v6.28.0） | `ArticleMediaUploadRecord.article_identity`をキーとする2値state（`ATTEMPT_STARTED`／`UPLOAD_CONFIRMED`）。`ATTEMPT_STARTED`への再startはfail-closed。**現行の本番配線では、このキーに`SideEffectOperationIdentity.as_store_key()`の値（`root_run_id:attempt_ordinal:media_upload:news_step:article.slug`）が渡される。名称は`article_identity`だが、実体は`root_run_id`と`attempt_ordinal`を含む attempt-scoped な値であり、記事単位の安定identityではない**（A2で訂正。A1は「記事単位」と誤記していた）。 | `article_media_upload_state_manager.py`、`media_upload_safety_coordinator.py:441-448`、`side_effect_operation_identity.py:47-58` |
| `side_effect_safety`（v6.32） | upload直前に`record_attempted()`（IO_ARMED durable ACK）を確認してからI/Oへ進む。`record_confirmed()`はmain.pyのみが呼ぶ。identityは`root_run_id:attempt_ordinal:media_upload:news_step:article.slug`。 | `media_upload_write_ahead_capability.py`、`side_effect_operation_identity.py`、`main.py:285-345` |
| `protected_operation_manifest` | write-ahead呼び出しより先にmanifestへ登録し、durable ACK未確認ならfail-closed。 | `main.py:299-306` |
| retry lineage／executor | `IO_ARMED + ATTEMPTED`のまま残ったoperationは`HUMAN_REVIEW_REQUIRED`へ導かれ、自動retryは遮断される。 | `main.py:341-344`、`retry_lineage_disposition.py:23` |

### 1.3 Problem Statement（Amendment A1で再定義）

旧Draftは「Retry機構がこの呼び出しを再試行しうる」ことを動機としていたが、これは**v6.32配線後の現状とは一致しない**。v6.32以降、Python側では**自動retryによる重複uploadはfail-closed／`HUMAN_REVIEW_REQUIRED`で既に遮断されている**。

6.38が解くべき問題は次のとおりである。

- **P1（本質）**：WordPress側には重複抑止が存在しない。Python側のdurable stateを経由しないあらゆる再POST（manual recovery後の再実行、`HUMAN_REVIEW_REQUIRED`解除後の再実行、state dirの喪失／別マシン実行、将来のtooling）は、同一論理メディアでも新しいattachmentを作る。
- **P1の補足（A2）**：現行Pythonには、再試行・再起動をまたいで安定な「記事／コンテンツ単位のidentity」の供給元が存在しない（1.2節）。したがって6.38のserver-side境界が実際に重複を抑止するには、将来のIntegration Releaseがそのような供給元を別途定義・永続化する必要がある（7.7節）。6.38自身はその供給元を実装しない。
- **P2**：Python側のfail-closedは「永久に人手へ送る」か「重複を許容して再実行する」の二択しか持たない。WordPress側にauthoritativeな重複抑止があれば、将来のmanual recoveryが「安全に再実行できるか」をWordPress側の事実で判断できる。
- **非目標**：自動retryの重複防止（既にv6.32で遮断済み）。Python側のHRR／write-ahead契約の変更。

したがって6.38の価値は「manual recovery後を含む、WordPress側のauthoritativeなserver-side duplicate suppression境界の確立」であり、単独では**消費者のいないFoundation**である（2章）。

---

## 2. Scope

6.38は、WordPress側（PHP plugin）にauthoritativeなserver-side idempotency境界を作る**Consumer-less Foundation**である。GCA-taggedリクエストを送るclientが（6.38時点では）存在しないため、6.38単体では本番トラフィックの挙動は一切変化しない（Zero-Diff）。

### In Scope（v1）

1. WordPress plugin `wordpress/gca-media-idempotency/`（未実装、本書の設計に基づく。**repoへの配置のみ。本番環境へのdeployは含まない**）
2. `/wp/v2/media` Native Core Routeのラップ（callback置換）による、GCA-taggedリクエストへの重複防止付与
3. Claims Tableによるat-most-once authorization（`INSERT`勝者判定、`PROCESSING`／`CONFIRMED`の2状態）
4. 物理的に分離された3種のDB接続（Claims Connection／Media Verification Connection／Core既存`$wpdb`）
5. GCA wire contract（request header・validation・closed allowlist、8.2節）
6. Logical identity contract（7.4〜7.6節）
7. Epoch（有効性境界）の定義と、**検出可能な**epoch mismatchのfail-closed（6章）
8. Provenance検証（5-way ID equality）とGCA Final Response Finalizer
9. single authoritative ingressにおけるkill switch・drain protocol
10. 非GCAリクエストに対するZero-Diff
11. テスト設計（15章：L1 static／L2 unit／L3 staging fault matrixの責務分離）。L1のうちPythonで書けるものは実装フェーズの成果物とする

### Out of Scope（v1、明示的除外）

- **Python client integration**（`WordPressMediaUploader`／`GeneratedImageWordPressMediaUploader`の変更、idempotency metadataの送出、digestやrevisionの導出）
- **stable article/content identity sourceの定義・実装・永続化**（再試行・再起動をまたいで不変なidentityの供給元）。後続Integration Releaseの**必須precondition**（7.7節）であり、6.38では実装しない
- **`main.py`／Retry／HRR／`side_effect_safety`／`article_media_upload_state`／`protected_operation_manifest`への配線・変更**（Zero-Diff）
- **production deployment**（plugin有効化・本番WordPressへの導入・GCA-taggedトラフィックの本番投入）。本番導入は別Releaseかつ別Human Gate
- **automatic orphan cleanup**（孤立attachment／孤立ファイルの検出・削除）
- **DB rollback／restore／lossy failoverをまたぐ完全保証**（6章。保証しないことを明記する）
- **外部epoch anchor**（DB外にepoch/claimの継続性を固定する機構）
- stale claim（`PROCESSING`）の自動reclaim・自動recovery（禁止、10.5節）
- manual reconciliation tooling／Human Recovery UI／運用ツール（Future）
- multisite対応（fail-closedで明示的に非対応）
- multi-node ingress／load balancer／autoscaling環境（production enable禁止）
- 既存Retry Lineage／HRR（`retry_lineage`／`side_effect_safety`系列）機構への変更（Zero-Diff）

---

## 3. Goals / Non-Goals

### Goals

- G1. Valid Epoch + approved trusted WordPress environment + single authoritative ingress + **Stable Authoritative DB Epoch内**、という4条件がすべて成立する範囲で、GCA-taggedメディアアップロードの**同一logical identityに対するCore media execution authorizationをat-most-once**に保証する。
- G2. **idempotencyの結果（claimがどうなったか）とclaim状態**については、Python側に状態を持たせず（複製・同期を前提とせず）、WordPress自身をsource of truthとする。**これは、将来のIntegration Releaseが「何を同一とみなすか」を決めるstable identityをdurableに保持する必要がある（7.7節）ことと矛盾しない**：両者は別の状態である。(a)**identity**（`article_identity`／`content_revision`の供給元）＝Python側（Integration Release）の責務で、永続化が必須。(b)**結果・claim状態**（`PROCESSING`／`CONFIRMED`、media ID）＝WordPress側が権威で、Python側は複製・同期しない。6.38はPython側にいかなる状態も追加しない（Out of Scope）。
- G3. 非GCAリクエストについて、Core Native実装とrequest/response双方でbehaviorally equivalentであることを維持する（Zero-Diff、14章）。
- G4. 「検出できないケース」を偽装せず、境界を正直にnarrowし、境界を越えた**と判明または疑われる**場合はHuman Gate配下の再検証を要求する（6章）。
- G5. crash safety：claim確立前のcrashはmediaゼロ。claim確立後のcrash・ambiguousは`PROCESSING`を残して**fail-closed**する（重複authorizationより永久ブロックを選ぶ）。保証の本質は「同一logical identityに対するat-most-once authorization」であり、「必ず1件作られる」ことではない（10章）。

### Non-Goals

- N1. multi-node／分散ingress環境のサポート。
- N2. 任意の敵対的co-resident PHPコードに対する防御（trusted environment前提）。
- N3. stale claimの自動reclaim・自動再実行（`PROCESSING`は不可逆）。
- N4. WordPress Core自体のバグ・トランザクション不整合への防御。
- N5. DB rollback／restore／lossy failoverをまたぐ重複防止（6章）。
- N6. 自動retryの重複防止そのもの（v6.32で遮断済み、1.3節）。

---

## 4. 用語・キー概念

| 用語 | 定義 |
|---|---|
| **GCA-tagged request** | `X-GCA-*` headerを1つでも含むMediaアップロードリクエスト（8.2節）。識別はheaderの存在のみで行い、不正なGCA-taggedは非GCAへfallbackしない。 |
| **Valid Epoch** | §5.3の前提条件がすべて成立している状態。1つでも崩れればEpoch invalid＝production enable禁止。 |
| **Stable Authoritative DB Epoch** | Claims Tableを保持するDBが、同一のauthoritativeなDBとして**committed履歴を連続して保持している期間**。rollback／restore／lossy failoverで連続性が切れたと判明または疑われた時点でEpochは終了し、Human Gate配下の再検証を要する（6章）。 |
| **logical identity** | `(identity_schema_version, article_identity, media_role, content_revision)`の組。image bytes・attempt・runに依存しない（7.4節）。 |
| **idempotency_key** | logical identityから導出される64桁hex。Claims Tableの一意制約対象（7.4節）。 |
| **Claims Table / Claims Connection** | at-most-once authorizationの勝者を`INSERT`で決定する専用テーブルと、それ専用の物理的に分離されたDB接続。 |
| **Media Verification Connection** | Core既存`$wpdb`・Claims Connectionのいずれとも異なる第3のwriter-pinned DB接続。永続化済みattachment状態の独立確認専用。 |
| **PROCESSING** | claimがwinnerとして確立した状態（durable、不可逆）。Core media executionの唯一の認可。 |
| **CONFIRMED / CONFIRMED snapshot** | Provenance検証（5-way ID equality含む）を経て、当該claimに対応するattachmentが永続化されたと確定した状態、およびそのimmutableスナップショット（id／source_url／mime_type／slug）。 |
| **Provenance（補助証跡）** | `rest_after_insert_attachment`の発火。偽造不能な証跡ではなく補助的corroboration（§11.1）。 |
| **GCA Final Response Finalizer** | authoritative outcome markerからcanonical responseを構築して返す、最終の投影層。**投影位置・対象・構築・header・投影後の境界は12章が正本**（A14で`rest_post_dispatch`へ変更）。durable stateの変更・DB I/Oは行わない。 |
| **authoritative outcome marker** | plugin control path（12.4節。GCA requestの全経路を網羅しない）が、到達した各GCA requestについて出口でちょうど1回確定する、plugin-private・write-once・request-localの状態。outcomeは`SUCCESS_FIRST`／`SUCCESS_REPLAY`／`E1`〜`E9`。exact request instanceに束縛し、成功系はidempotency_keyとdurable snapshotを保持する（12章）。 |
| **attempt-scoped identity** | Python側`SideEffectOperationIdentity`（`root_run_id:attempt_ordinal:...`）、およびその`as_store_key()`値（`ArticleMediaUploadRecord.article_identity`として渡される値を含む）。**server-side identityとは別物**であり、そこから導出してはならない（7.5・7.7節）。 |
| **stable identity source** | 再試行・再起動をまたいで不変なdurable article/content identityの供給元。**現行Pythonには存在せず、後続Integration Releaseが定義・永続化する**（7.7節）。 |
| **gca_claim_state** | GCA応答に付与する、このrequestが確立・観測したclaimの状態を示す診断field（`none`／`processing`／`unknown`／`confirmed`／`confirmed_inconsistent`、8.3節）。 |
| **Authoritative Binding** | Claims Connection・Media Verification Connection・Core `$wpdb`が、同一のauthoritative writer・DB/schema・WordPress site・table prefix・Epochを指していることの規範的前提（9.3節）。 |

---

## 5. 保証境界（Guarantee Boundary）／脅威モデル

### 5.1 最終的な保証

> Valid Epoch **かつ** approved trusted WordPress environment **かつ** single authoritative ingress deployment **かつ** Stable Authoritative DB Epoch内の、GCA-taggedメディアワークについてのみ、同一logical identityに対するCore media execution authorizationをat-most-onceに保証する。

- 保証は**GCA-taggedワークに限定**される（非GCAは対象外、Zero-Diffで挙動は不変）。
- 保証は**authorizationのat-most-once**であり、メディアが必ず1件作られること・失敗が自動回復することは含まない。
- 保証は**供給されたlogical identityに対して**成立する。現実世界の同一メディアの重複を実効的に抑止できるかは、Integration Releaseが安定なidentity sourceを供給すること（7.7節）に依存し、server側はその安定性を検証できない。
- 保証は**client-visible ID = response ID = provenance ID = Media Verification ID = CONFIRMED snapshot ID**という5-way equalityを最終的な正しさの定義とする（§11.2）。
- Stable Authoritative DB Epochの外（6章）では保証しない。

### 5.2 脅威モデル（Trusted WordPress Environment）

- co-resident PHPコード（他plugin・mu-plugin等）を敵対的主体として扱わない。インストール済みplugin一式は既知・vetted済みであることを前提とする。
- Core REST callbackの外側でattachmentを作成するケース（直接`wp_insert_attachment()`、WP-CLI、admin-ajax等）はv1のthreat model外。
- 敵対的環境（未知pluginが動的にインストールされうる環境等）での使用は想定しない。

### 5.3 Epoch前提（Valid Epochの構成要素）

以下のいずれかが承認値から外れた（drift）時点で、Epochはinvalidとなり、production enableは禁止される：

1. WordPress Core version（固定・pinned）
2. approved plugin set（固定）
3. `/wp/v2/media` route handlerのfingerprint（wrapされたCore callbackであることの確認。`allow_batch`の値を含む、12.5節 BT-3）
4. pre-callback filter topology：`rest_pre_dispatch` / `rest_request_before_callbacks` / `rest_dispatch_request` /（A18）`rest_request_from_url`（扱いは**12.1節 RD-6**が正本）
5. post-callback filter topology：一覧と扱いは**12.1節 P-4・12.3節 X-***が正本（`rest_request_after_callbacks` / `rest_post_dispatch` / `rest_pre_serve_request` / `rest_pre_echo_response` / `rest_json_encode_options` / `rest_envelope_response` /（A18）`status_header`（**12.3節 X-11**））
6. **DB continuity anchor（6章）の検出可能な不一致が存在しないこと**
7. **Authoritative Binding（9.3節）が成立していること**（3接続が同一のwriter・DB/schema・site・table prefix・Epochを指す）
8. **single-siteであることの積極的な確認（5.5節）**

**既知の残存限界**：登録callbackの集合を静的に照合する方式は、常に登録されているが特定条件下でのみ挙動を変えるconditional callbackを検出できない可能性がある。この限界は「検出する」のではなく「そのような構成をEpoch invalidとして扱う」という契約上の宣言で扱う（17章Known Limitations、15章 T-14）。

### 5.4 Single-Ingress制約

- v1は単一のauthoritative ingress deploymentのみをサポートする。multi-node／autoscaling環境ではproduction enableを禁止する。
- 「multi-node membership管理という難問を解く」のではなく「問題設定自体をscopeから除外する」。

### 5.5 Multisite除外（Amendment A2で実行時fail-closed契約を追加）

- WordPress multisiteは非対応とし、**実行時に検出してfail-closed**する。「非対応と書くだけ」では足りないため、次を契約とする。
  1. **積極的確認**：plugin起動時およびGCA-taggedリクエストごとの**claim確立前**（claim `INSERT`より前、10.2節#2）に、single-siteであることを**積極的に確認**する。確認条件は、`is_multisite()`が利用可能で、かつ**厳密に`false`を返す**こと。加えて、`MULTISITE`／`SUBDOMAIN_INSTALL`定数が定義されていて真値の場合、`$wpdb->base_prefix !== $wpdb->prefix`の場合、現在のblog IDが単一siteの値でない場合は、multisiteの兆候としてfail-closedにする（冗長な防御。いずれも「真なら拒否」であり、確認用の関数が使えない・例外を投げる・値が不定のときは**確認不能として拒否**する）。
  2. **確認不能でも実行しない**：multisiteと判定された場合、確認手段が利用不能の場合、確認中に例外が発生した場合のいずれも、claimを作らずCoreを呼ばない。HTTP 503 `gca_idempotency_unavailable`、`gca_claim_state = none`（8.3節）。**claim確立後の再確認（9.3節 R2）で同じ確認が失敗した場合は、claimを保持したまま（`PROCESSING`）Coreを呼ばず、409 `processing`**とする（`none`へ戻らない）。
  3. **Epoch preconditionへの組込み**：5.3節#8。plugin enable時にも同じ確認を行い、成立しなければenableしない。
  4. **非GCAリクエスト**には影響しない（Zero-Diff）。multisite環境でpluginが有効化されていても、非GCAリクエストはCore Native挙動のまま。
  5. 検証：L1（確認がclaim前に位置し、確認不能時に拒否側へ倒れる静的構造）、L2（`is_multisite()`が真／関数欠落／例外のstubでclaim 0・Core 0）、L3（multisite構成での拒否確認）。15章 T-24。
  6. `is_multisite()`等の関数セマンティクス自体は未検証（17章 U-15）。上記の冗長な真値判定は、その未検証を前提に「拒否側へ倒す」ために置く。

---

## 6. Stable Authoritative DB Epoch（保証範囲の限定、Amendment A1で全面改訂）

### 6.1 方法論

本設計は、完全には検出不可能な問題（DB continuity、route/plugin topology drift、filter topology、multi-node ingress membership）に対し、共通して次のパターンを適用する：

1. 「完全な検出」を目指す高度な機構を作らない。
2. 保証の適用範囲（Valid Epoch／Stable Authoritative DB Epoch）を明示的かつ正直にnarrowし、範囲外を「保証対象外」と宣言する。
3. Epoch境界を越えたと**判明または疑われる**イベントでは、production enableを止め、Human Gate配下で再検証する。
4. 可能な箇所では、検出に頼らず**構造的にリスクを排除**する（route callback自体の置換、multisite/multi-ingressのscope除外）。

### 6.2 保証範囲（Guarantee Matrix）

| シナリオ | 保証 | 備考 |
|---|---|---|
| 通常運用（同一DB・committed履歴が連続） | **保証する** | at-most-once authorization |
| PHP/PHP-FPM workerのcrash・timeout・kill（claim確立前後を問わず） | **保証する** | claim確立後は`PROCESSING`が残りfail-closed（重複はしないが、以降ブロックされる） |
| DB serverの正常再起動・`mysqld`異常終了（**ACK済み**commitがdurable） | **保証する（条件付き）** | durability設定の前提（6.4節）が満たされる場合。ACK未受領のcommitは残る場合も残らない場合もあり、どちらでも重複しない（10.6節C6）。staging fault matrix T-25で確認 |
| OS全体のクラッシュ・電源断・ストレージ障害 | **保証しない** | T-25で再現・検証できないため、保証対象外 |
| **DB rollback／PITR restore／snapshot restore** | **保証しない** | claim行ごと過去へ戻るため、既にCore実行済みのidentityが未claimに戻りうる（6.3節） |
| **lossy failover**（非同期replica昇格、durability設定不備でのcommit喪失 等） | **保証しない** | 同上 |
| 外部epoch anchorによる検出 | **提供しない（Out of Scope）** | 将来Release候補 |

### 6.3 同一DB内markerだけではrollbackを検出できない（明記）

Claims Tableと同じDB内に置いたmarker（`store_generation_id`、dual-location anchorを含む）は、DB rollback／restoreの際に**claim行と同時に過去の値へ戻る**ため、marker単体ではrollback・restoreを検出できない。したがって：

- 旧Draft §7.2の「dual-location anchorによる継続性検証」は、**rollback検出の保証としては採用しない**（撤回）。
- anchorは「**検出可能なepoch mismatchのみ**をfail-closedにする」ための補助情報として残す（6.5節）。
- rollback／restore／lossy failoverが**発生した事実を運用者が把握した場合**は、本機構に頼らず、Human Gate配下でEpochを終了し、再検証を経ずにGCA-taggedトラフィックを再開しない（運用契約。16章）。

### 6.4 Durability前提（enable時に確認する宣言）

「DB正常再起動でcommitがdurable」という保証は、少なくとも次の前提に依存する。enable時にbest-effortで読取り・記録し、承認値と異なればEpoch invalid（production enable禁止）とする。**これらはenable時点の宣言であり、runtime中のdriftを原子的に検出する機構ではない**。

- Claims Tableが InnoDB であること
- `innodb_flush_log_at_trx_commit = 1`
- `sync_binlog = 1`（binlog有効時）
- Claims Connectionが`autocommit = 1`、`in_transaction = 0`であること（9.1節と同型のSELECT直前確認）

具体的な変数名・取得可否は18章のImplementation Start Validationで対象MySQL/MariaDB環境に対して確認する（未確認、17章）。

**設定値の確認は、durabilityの実証の代替にならない**（A2）。「ACK済みcommitがDB再起動後も残る」ことは、設定値の読取り（T-09）ではなく、実DBを再起動して確認するstaging fault matrix（15章 T-25）で証明する。T-25はprocess crash相当（`mysqld`の異常終了）までを対象とし、OS全体のクラッシュ・電源断・ストレージ層の障害は対象外（検証できないため保証もしない、6.2節の「保証しない」側）。

### 6.5 検出可能なepoch mismatch（fail-closedにする範囲）

次のいずれかを**検出した場合に限り**、fail-closedする。**claim確立前に検出した場合**は、claim確立もreplayも行わない（503 `none`、row/mediaを作らない）。**claim確立後に検出した場合**は、claimを取り消さず`PROCESSING`を保持し、Core呼出前なら呼ばず、409 `processing`とする（9.3節 R2／R3、`none`へ戻らない）。duplicate経路では503 `unknown`。

1. **サーバー内部の**claims schema version（Claims Table・anchorが記録するschema version）の不一致、およびserver内部のschema／DB／epoch／configurationの不一致（**clientが供給した`X-GCA-Identity-Schema`の値が対応schemaと一致しない場合は、Epoch mismatchではなく、client供給値の要求不正としてE1／400で拒否する**。7.4節・8.2節。A8）
2. 2か所に格納したanchor（`store_generation_id`）が互いに不一致（部分restoreの検出）
3. anchorが存在するのにClaims Tableが欠落／再作成されている、または逆（anchor欠落でClaims行が存在）
4. 記録済みの`@@server_uuid`（取得可能な場合）が現在値と不一致（別serverへのfailover/restoreの検出。**同一server_uuidへのrestoreは検出できない**）
5. 6.4節のdurability前提が承認値と不一致（enable時）
6. 5.3節の#1〜#5のEpoch driftが検出された場合
7. **Authoritative Binding（9.3節）の不一致・確認不能**（3接続のBinding Fingerprintが一致しない、またはFingerprintをanchorに記録された値と照合できない）
8. **multisiteの検出・確認不能**（5.5節）

検出できないものは検出できないものとして17章に残す。**「検出できなかったこと」を「問題がないこと」と解釈してはならない。**

---

## 7. Schema / Claims Lifecycle

### 7.1 Claims Table（概念設計）

- 1 logical identityにつき最大1行。`idempotency_key`に一意制約。winner判定は**`INSERT`のaffected-row数が厳密に1**であることのみを根拠とする。
- 主要カラム（概念）：`idempotency_key`（UNIQUE）／`identity_schema_version`／`article_identity`／`media_role`／`content_revision`（診断用に平文保存）／`state`（`PROCESSING`|`CONFIRMED`）／`claim_token`（winnerのみが知るランダム値。CONFIRM時のguard。仕様は7.8節）／`created_at`（UTC）／`confirmed_at`／`media_id`／snapshot（`media_id`と`source_url`／`mime_type`／`slug`の**4項目のみ**。Core responseの他のfieldは**保存しない**、8.3節・12章）／`diagnostic_content_digest`（任意、7.6節）／anchor参照。
- lifecycle状態は**`PROCESSING` → `CONFIRMED`の2状態のみ**。claim行の生成＝`PROCESSING`の確立であり、旧Draftの`CLAIMED`は`PROCESSING`へ統合した（`CLAIMED`と`PROCESSING`を分けても安全性は増えず、遷移間のcrash windowが増えるだけのため。24章）。
- `DELETE`および`PROCESSING→CONFIRMED`以外の`UPDATE`は、plugin codeに**存在しない**こと（reclaim・reset・再利用の不在。15章のL1 static検査対象）。

### 7.2 Claim Store Continuity Anchor（役割を限定）

- `store_generation_id`を2か所に格納し、**6.5節の検出可能なmismatchのみ**を扱う。rollback検出の保証ではない（6.3節）。
- `identity_schema_version`により、logical identity導出ロジックの将来変更に対する互換性境界を明示する。

### 7.3 Dedicated Endpoint Authorization

- GCA用capability（例：`gca_media_idempotency_upload`）を新設し、Phase 1 authorizationをこのcapabilityの有無で判定する。権限不足は403、claimを作らない。**（A16）判定の位置は、route callbackの先頭（claimより前）。Coreの`permission_callback`は置換せず、markerに関与しない（12.4節）。**

### 7.4 Logical Identity Contract（Amendment A1で全面置換）

旧Draftの「image bytes由来の`content_identity_digest`をkeyにする」契約は**撤回**する。理由：画像は`upload()`のたびに再生成される（1.2節）ためbytes digestは試行間で安定せず、重複抑止というRelease目的を達成できない。また`attempt_ordinal`・`root_run_id`は試行ごとに変わる（Python側attempt-scoped identity）ため、keyに含めると再実行ごとに別claimになり目的に反する。

**keyに使ってはならない値**：image bytes／そのdigest、`attempt_ordinal`、`root_run_id`、`member_run_id`、timestamp、乱数。

**LP encoding**：`LP(field)` = `field`のUTF-8バイト列長（4byte unsigned big-endian）+ そのバイト列。

**入力field（すべて必須、server側は意味を解釈しない opaque値として形式検証のみ行う）**

| field | 意味 | 形式検証 |
|---|---|---|
| `identity_schema_version` | 固定定数`"GCA-MEDIA-LOGICAL-IDENTITY-V1"` | 完全一致。**clientが供給した`X-GCA-Identity-Schema`の値が、対応するschemaと一致しない場合は、claim確立前に400・E1（`gca_claim_state = none`、8.3節）で拒否する**（client供給値の要求不正。A8で統一）。**server内部のschema／DB／epoch／configurationの不一致（claims schema versionの不一致を含む）は、E4（503、`none`）として区別する**（6.5節#1） |
| `article_identity` | **記事ごとに安定した**識別子（呼び出し側が供給）。試行・run・画像に依存しない。**現行Pythonには供給元が存在せず、後続Integration Releaseが定義・永続化する（7.7節）。既存のattempt-scoped identity・`as_store_key()`値から導出してはならない。** | `[A-Za-z0-9._:-]{1,128}` |
| `media_role` | 記事内でのメディアの役割。v1は閉集合`{"featured_media"}`のみ。 | 閉集合外は拒否 |
| `content_revision` | 当該記事の**内容リビジョン**を表すopaque token（7.6節）。 | `[A-Za-z0-9._-]{1,64}` |

```
idempotency_key = hex(SHA256(
    LP("GCA-MEDIA-IDEMPOTENCY-KEY-LOGICAL-V1")
 || LP(identity_schema_version)
 || LP(article_identity)
 || LP(media_role)
 || LP(content_revision)
))
requested_slug = "gca-media-v1-" + idempotency_key      // 64桁hex全体、切り詰めなし
```

- `requested_slug`は、永続化済み`post_name`が完全一致すべき要求値（§9.2）。クライアント供給のslugは信頼しない。
- **validation／fail-closed**：いずれかのfieldが欠落・形式違反・閉集合外の場合、claim確立前に400で拒否する（claim行を作らない、不正入力に対するfallback・デフォルト値解釈を行わない）。key導出中のencoding／digest計算エラーも作業ゼロでfail-closed。
- 旧Draftのkey定数（`GCA-MEDIA-IDEMPOTENCY-KEY-V1`／`GCA-CONTENT-IDENTITY-DIGEST-V1`）は**未実装のまま撤回**した。移行・互換の必要はない。

### 7.5 責務分離（identityを混同しない）（Amendment A2で訂正）

| identity | 所有者 | 粒度 | 用途 | 6.38での扱い |
|---|---|---|---|---|
| **attempt-scoped identity**（`SideEffectOperationIdentity`：`root_run_id:attempt_ordinal:media_upload:news_step:article.slug`） | Python `side_effect_safety`（v6.32） | **試行ごと**（`root_run_id`・`attempt_ordinal`を含む） | write-ahead／fail-closed／HRR判定 | **不変（Zero-Diff）。server側は参照しない** |
| **upload-stateキー**（`ArticleMediaUploadRecord.article_identity`） | Python `article_media_upload_state`（v6.28.0） | **試行ごと**。現行の本番配線では`identity.as_store_key()`、すなわち上記attempt-scoped identityの文字列そのものが渡される（`media_upload_safety_coordinator.py:441-448`）。名称は`article_identity`だが**記事単位の安定identityではない** | クライアント側の`ATTEMPT_STARTED`／`UPLOAD_CONFIRMED`state | **不変。server側は参照しない** |
| **server-side logical identity**（本書7.4節） | WordPress plugin（本Release） | 記事×役割×内容リビジョン（**呼び出し側が安定に供給する前提**） | WordPress側のduplicate suppression | 本Releaseで定義。供給元は実装しない（7.7節） |

- A1はupload-stateキーを「記事単位で、attempt identityとは独立」と記載していたが、これは**誤り**であった（A2で訂正）。現行Pythonには、再試行・再起動をまたいで安定な記事／コンテンツidentityの供給元は存在しない。`article.slug`は`as_store_key()`の一要素（`operation_instance_key`）として使われているが、記事再生成をまたいで変化しうるか否かは**6.38では未確認**であり、安定identityの根拠として使わない（17章）。
- 上記identityは**互いから導出しない／互いを導出元にしない**。server側のlogical identityはPythonのどのstateからも読み取らず、Pythonのどのstateもserver側stateを読み取らない（6.38では接続しない、23章）。


### 7.6 Content Revisionの扱い

- `content_revision`は「同じ記事内容に対しては同じ値、メディアを新しく作ってよい内容変更があったときだけ別の値」を表すopaque tokenであり、**呼び出し側の明示的な判断で変更される**。
- **同一`(article_identity, media_role, content_revision)`**：画像bytesが再生成により異なっていても同一logical identity。`CONFIRMED`なら既存mediaをreplayし、画像を再度作成・アップロードしない。`PROCESSING`ならfail-closed。
- **別`content_revision`**：別logical identityとして新規claimを許可する。過去revisionのclaim・mediaは削除・supersedeされず、server側に「最新revision」の概念を持たせない（順序比較・置換を行わない）。
- **image bytes digestは、必要な場合に限り診断メタデータ（`diagnostic_content_digest`、任意header、64桁小文字hex）としてclaim行へ保存してよい**。key・認可判定・replay判定には**一切使わない**。replay時に診断digestが異なっていても結果は変わらない。保存は最初のclaim `INSERT`時のみ（immutable）。
- `content_revision`の**供給方法・変更条件はIntegration Releaseの責務**であり、6.38では決めない。ただし「AI生成で非決定的な記事テキスト等から毎試行異なる値を導出する」実装は重複抑止を無効化するため禁止する旨を、Integration Releaseの必須precondition（7.7節）として規定する。

### 7.7 Stable Identity Source Prerequisite（Integration Releaseの必須precondition、Amendment A2で追加）

6.38は、server側のlogical identity契約（7.4節）と境界（claims・状態機械）のみを定義し、**stable identity sourceを実装しない**。重複抑止が現実のメディアに対して実効性を持つためには、後続のIntegration Releaseが次を**必須preconditionとして満たす**ものとする。満たされない場合、Integration Releaseはserver側へGCA-taggedリクエストを送出してはならない。

1. **定義と永続化**：再試行・再起動・プロセス再開・（必要なら）別マシン実行をまたいで**不変な**durable article/content identityを、**Integration Release自身が定義し、durableに永続化**する。永続化は、最初のside effect（Python側のwrite-ahead `IO_ARMED`・server側claim）より**前**に完了し、crash後に同じ値を読み出せること。
2. **導出元の制限（禁止事項）**：次から**導出してはならない**。
   - 既存のattempt-scoped identity、およびその`as_store_key()`値（`root_run_id`・`attempt_ordinal`・`member_run_id`・`effect_site`を含む）
   - `ArticleMediaUploadRecord.article_identity`として現行配線で渡される値
   - 記事再生成のたびに変化しうる値（AI生成のtitle・本文・slug等。安定性が実証されない限り）
   - 画像bytes・そのdigest
3. **`content_revision`**：同様にdurableに永続化し、変更条件（いつ新しいrevisionとするか）をIntegration Releaseが明示的に定義する。非決定的なAI出力から試行ごとに異なる値を導出してはならない（7.6節）。
4. **供給契約**：上記の値を、8.2節のwire contract（`X-GCA-Article-Identity`／`X-GCA-Content-Revision`）でserver側へ供給する。
5. **受け入れ条件（Integration Releaseで検証）**：同一論理記事について、(a)通常のretry、(b)プロセス再起動、(c)画像の再生成、(d)記事テキストの再生成が起きても同一の`article_identity`・`content_revision`が供給されること。
6. **6.38での位置づけ**：server側はこの安定性を**検証できない**（opaque値として形式検証のみ）。したがって、6.38のserver側保証は「供給された値に対するat-most-once」にとどまり（5.1節）、現実のメディア重複の実効的な抑止はこのpreconditionの充足に**条件付き**である。6.38のCompletion（20章）は、このpreconditionの充足を主張しない。

### 7.8 `claim_token`の仕様（Amendment A2で追加）

- **生成**：暗号論的に安全な乱数生成器（PHPの`random_bytes(32)`相当のCSPRNG）で、**ちょうど32バイト（exactly 256 bits）**を生成する（32バイトを超える長さ・未満の長さは規範に反する。A3で「以上」から厳密化）。`wp_generate_password()`・`mt_rand()`・時刻・連番・`idempotency_key`や他のfieldからの導出は**禁止**。CSPRNGが利用不能・失敗した場合は、claimを作らずfail-closed（503、`gca_claim_state = none`）。
- **保存形式・長さ**：32バイトの小文字hex表現＝**ちょうど64桁**（`CHAR(64)`、`[0-9a-f]{64}`、NOT NULL）。32バイト（256bit）と64桁hexと`CHAR(64)`は**1対1に一致**する。claimごとに新規生成し、再利用しない。
- **非公開**：`claim_token`は、HTTP応答（成功・errorの`data`を含む）、ログ、診断出力、例外メッセージ、`diagnostic`系のfield、Finalizerの出力、テストのgolden値のいずれにも**露出してはならない**。当該requestのメモリ内とClaims Tableの行内にのみ存在する。
- **使用**：`PROCESSING→CONFIRMED`のguarded `UPDATE`の`WHERE`句（パラメータ化クエリ）でのみ用いる。`CONFIRMED`確定後もrowに残してよい（追加の`UPDATE`を作らない、7.1節）。
- **検証**：L1（token変数をログ・応答構築に渡す箇所がsource上に存在しないことの静的検査、生成が`random_bytes`系であること）、L2（応答・error・captureしたログにtokenが含まれない、CSPRNG失敗時にclaim 0）。15章 T-26。

---

## 8. Native Route Wrapper

- `/wp/v2/media`のNative Core Route（`WP_REST_Attachments_Controller::create_item`）を、**composable filterによる傍受ではなく、route callback自体の置換**（`rest_endpoints` filter経由の既存登録route callbackの差し替え）によってラップする。
- wrapされたcallbackはCore自身の`create_item`へ処理を委譲する（Core media executionを代替・再実装しない）。
- handler fingerprint（実際に呼び出される関数が承認済みCore実装であること）はEpoch preconditionの一部（5.3節#3）。
- **（A14・A15・A16）** route callbackの置換時の`allow_batch`の扱いは12.5節 BT-3、control path（route callbackだけ）の網羅範囲と`permission_callback`の分離は12.4節（B-*）が正本。`permission_callback`・Core `args`は6.38では変更しない。

### 8.1 GCA Request Closed Allowlist（Amendment A2で設計時点に確定。**実装時の追加・変更・解釈による拡張を禁止**）

GCA-tagged `POST /wp/v2/media`は、下表の**許可集合に完全に含まれる要素のみ**を受理する。許可集合外の要素が**1つでも**存在すれば、**claim確立（`INSERT`）より前に**400 `gca_idempotency_invalid_request`（`gca_claim_state = none`、8.3節）で拒否し、claim行を作らず、Coreを呼ばない。許可集合の変更は、本書の改訂（Architecture Review＋Human Gate）を経る場合に限る。

**判定の方式は「許可集合に含まれないものはすべて拒否」であり、Core側のparameter一覧が何であるか（未検証、17章）に依存しない。** 以下の「拒否対象」欄は説明のための例示であり、網羅リストではない。

| 要素 | 許可（これ以外はすべて拒否） | 拒否対象の例（網羅ではない） |
|---|---|---|
| HTTP method | `POST`のみ（**effective method**基準。12.1節 MO-1） | なし（effective methodがPOSTでないrequestは、本allowlistの判定対象ではなく、wrapped CREATABLE callbackに到達しない。12.1節 MO-2・12.4節 B-4） |
| route | `/wp/v2/media`（`/wp-json/`経由）の**完全一致** | `?rest_route=`によるroute指定、`/wp/v2/media/<id>`等の他route（これらはそもそも本wrapperの対象外で、本pluginは関与しない） |
| **query parameter** | **空集合**（1つも許可しない） | `_method`／`_envelope`／`_embed`／`_fields`／`_jsonp`／`_wpnonce`／`context`／`force`／`url`／`slug`／`title`／`alt_text`／`caption`／`description`／`status`／`date`／`date_gmt`／`author`／`post`／`meta`／`template`／`comment_status`／`ping_status` 等 |
| **body形式・サイズ** | **raw binary**（direct upload）のみ。bodyは**非空**、かつ**1バイト以上33,554,432バイト（32 MiB）以下**、かつ下記`Content-Type`のいずれか（上限の導出は下記「body size contract」） | `multipart/form-data`／`application/x-www-form-urlencoded`／`application/json`、body parameterとして渡される上記の全parameter |
| `Content-Type` | **完全一致**で`image/png`／`image/jpeg`／`image/webp`のいずれか（parameter付き不可） | 上記以外のすべて |
| `Content-Disposition` | 必須。`attachment; filename="<name>"`の形式のみ。`<name>`は`^[A-Za-z0-9][A-Za-z0-9._-]*$`に完全一致し、かつ**255文字以下**（この長さ上限は**本pluginが独自に課すv1 contract**。現行`WordPressMediaUploader`は文字種の正規表現のみを検証し、長さ制限を持たない。下記「filename contract」） | `filename*=`等の拡張記法、パス区切り、制御文字、複数のfilename |
| `X-GCA-*` header | **8.2節の5種のみ**（`X-GCA-Identity-Schema`／`X-GCA-Article-Identity`／`X-GCA-Media-Role`／`X-GCA-Content-Revision`／`X-GCA-Content-Diagnostic-Digest`。最後のみ任意） | 上記以外の`X-GCA-`で始まるheader、同一headerの重複 |
| method override control | **禁止**：`X-HTTP-Method-Override` headerおよびquery parameter `_method`は許可集合に含まれない。**effective POSTでwrapped CREATABLE callbackに到達したrequestに存在すればE1**（境界は12.1節 MO-3。effective methodがPOSTでないrequestは対象外、MO-2） | `X-HTTP-Method-Override`、`_method`（`_method`は上のquery parameter行にも含まれる） |
| 認証header等のその他のheader | Application Password等の認証、`Content-Length`、`Host`、`User-Agent`、`Accept`、proxy由来のheader等は**検査対象外**（通過させる） | — |

**body size contract（A3で確定、A4で保証の範囲を訂正。実装時決定への先送りを禁止）**

- **固定上限：33,554,432バイト（32 MiB）**。これは**本pluginが独自に課すv1 policy**であり、WordPress／PHP／web serverの上限（`upload_max_filesize`・`post_max_size`・`client_max_body_size`・`memory_limit`等。いずれも対象環境の値は**未検証**、17章 U-16）を示すものではない。環境側の上限が小さければ、環境側が先にrejectする（pluginに到達しない。その応答は`gca_claim_state`を欠くため、8.3節 契約#4のとおり結果不明として扱う）。
- **この上限は、現行の画像生成契約が出力しうる画像、または「正規の画像」のすべてを受理することを保証しない**（A4で、A3の「拒否しない上限として導出される」という記述を**削除**した）。理由：現行の`OpenAIImageGenerator`は、base64 decode後のbytesについて**非空であること以外**（サイズ・寸法・bit depth・metadata・エンコード方式）を検証せず（`openai_image_generator.py:222-241`）、`GeneratedImage`も非空のbytesとmime形式しか検証しない（`generated_image.py:26-37`）。したがって、**正当な入力であっても32 MiBを超えれば、claim前に413で拒否されうる**。これは仕様であり、本Releaseの欠陥ではない。
- **選定の目安（保証ではない）**：現行の許可出力寸法の最大3840×2160（`_ALLOWED_SIZES`、8,294,400 px）を8bit RGBAで無圧縮とした場合に概ね相当するバイト数（約33.2 MB）を、一般的な画像に対して十分に大きい上限として選んだ。この目安は、上限以下であればすべて受理されること、上限を超える正当な画像が存在しないことの**いずれも主張しない**。
- 上限を変更する場合は、本書の改訂（Human Gate承認を含む）による。実装時に変更しない。
- **測定**：pluginが実際に受信したbodyのバイト長（`strlen`相当）で判定する。`Content-Length`が存在する場合は、それも上限以下であることを要し、受信bodyの長さと不一致なら400で拒否する。上限超過は**claim確立前**（10.2節#1）に**413 `gca_idempotency_payload_too_large`、`gca_claim_state = none`**で拒否し、claim行を作らず、Coreを呼ばない。**下限は1バイト**（空bodyは400）。
- **検証**：L1（上限定数が33,554,432であること、検査がclaim `INSERT`より前に位置すること）、L2（上限ちょうどは受理経路へ進み、上限+1バイトは413・claim 0・Core 0。空bodyは400）、L3（実環境で上限超過がclaim前に拒否され、Claims Tableに行が作られず、attachmentが増えないこと）。15章 T-29。

**filename contract（A3で明確化、A4で現行生成contractから最大長を算出）**

- 文字種（`^[A-Za-z0-9][A-Za-z0-9._-]*$`）は、現行`WordPressMediaUploader`の検証（`wordpress_media_uploader.py:18, 85-89`）と同一である。
- **255文字以下という長さ上限は、本pluginの独自contract**であり、現行Uploaderには存在しない。
- **現行の生成filenameの最大長（算出、V-8）**：現行runtimeは`generate_image_filename(article.seo_title, mime_type)`でfilenameを生成する（`article_featured_media_runtime.py:151`）。`generated_image_filename_policy.py`から次のとおり算出できる。
  - slug部分：ASCII化・小文字化・`-`区切りの後、**60文字を超える場合は60文字以下に切り詰める**（`:17-24`）。したがって**最大60文字**。文字種は`[a-z0-9-]`（先頭・末尾の`-`は除去）で、上記regexに適合する。
  - slugが空の場合のfallback：`"generated-image-"`（16文字）＋sha256先頭8桁hex（8文字）＝**24文字**（`:27-29`）。
  - 予約デバイス名の回避：予約名（最大4文字）に`-image`を付加＝**最大10文字**（`:32-40`）。
  - 拡張子：`.`＋`png`／`jpg`／`webp`（`gif`は本pluginのallowlist外で、現行generatorも出力しない）＝**最大5文字**（`:56-70`）。
  - **最大filename長 = 60 + 5 = 65文字**。これは255文字**未満**である。よって、現行の`generate_image_filename()`が生成するfilenameは、本pluginの255文字上限に**抵触しない**（コードから算出した事実。「未確認」の記述は削除した）。
- ただし本pluginの上限は、`generate_image_filename()`以外の経路で生成されたfilenameには適用されうる（その場合は400で拒否される、仕様）。

- 現行Python clientが送る内容（raw body、`Content-Type`＝`image/png`／`image/jpeg`／`image/webp`のいずれか、`Content-Disposition`のfilename、query parameterなし）は、`X-GCA-*`を付与すれば本allowlistのうち**filename・Content-Type・query parameter**に適合する。**bodyサイズについては、32 MiBを超える画像は拒否されうる**（上記body size contract。Python側の変更自体は6.38のOut of Scope）。
- **`url`パラメータ・`create_item_from_url()`経路は、query parameter空集合のため構造的に拒否される**（個別の特例は設けない）。
- 本ルールは**安全側の保守的規則であり、「WordPress 7.1.0で`create_item_from_url()`が新設された」という過去記録（17章 S-1）の真偽に依存しない**。
- **サーバーがslugを指定する機構**：`slug`はclient供給を許可しない（上表）。server側が導出した`requested_slug`をCoreへ渡す機構（request parameterへの注入等）は設計上の前提であり、Coreが`slug`を尊重するかは**未検証**（17章 U-14）。尊重されない場合はCONFIRM条件（9.2節の`post_name`完全一致）が常に不成立となり、**fail-closedに倒れる**（実装開始前のValidationで確認、18章）。
- **（A14・A15・A17）** 本allowlistのE1が返る範囲は、**effective methodの境界（12.1節 MO-1〜MO-4）**と、Core自身の引数検証が先に失敗するrequest（12.4節 B-6）を含めて、**12章が正本**。claim・Core `create_item`呼出に関する安全性は12.1節 SP-1・12.4節に従う（検証はT-17・T-36）。
- **未検証の前提（17章 U-13）**：上記「検査対象外」のheaderが`create_item`の挙動を変えないこと。実装開始前に対象Core versionで確認し、変えうるheaderが見つかった場合は本表を改訂する（実装時の判断で拡張しない）。

### 8.2 GCA Wire Contract（Amendment A1で追加。8.1・8.3節と整合。形式の確定は21章のArchitecture Gateによる）

Python integrationが存在しない6.38では、serverが受理するwire contractを先に定義しておく必要がある。

| header | 必須 | 内容 |
|---|---|---|
| `X-GCA-Identity-Schema` | 必須 | `GCA-MEDIA-LOGICAL-IDENTITY-V1` |
| `X-GCA-Article-Identity` | 必須 | 7.4節`article_identity` |
| `X-GCA-Media-Role` | 必須 | 7.4節`media_role` |
| `X-GCA-Content-Revision` | 必須 | 7.4節`content_revision` |
| `X-GCA-Content-Diagnostic-Digest` | 任意 | 7.6節、64桁小文字hex、診断専用 |

- **GCA-tagged判定**：`X-GCA-`で始まるheaderが**1つでも存在**すれば、GCA-taggedとして扱い、必須headerがすべて揃い形式が正しい場合のみ受理する。1つでも欠落・不正なら**400でfail-closed**し、非GCA経路へfallbackしない。**`X-GCA-Identity-Schema`の値が、対応するschema（`GCA-MEDIA-LOGICAL-IDENTITY-V1`）と一致しない場合も、client供給値の不備として400・E1で拒否する**（A8。server内部のschema等の不一致はE4）。
- 現行Python clientはこれらのheaderを送らないため、非GCAとして従来どおりCore Native挙動で処理される（Zero-Diff）。
- 応答のHTTP status・error codeは**8.3節で一義的に定義**する（A1の暫定記述は置き換えた）。

### 8.3 HTTP Status／Error Code Contract（Amendment A2で全面確定）

**原則**：(1) **`gca_claim_state`は、「このrequest自身がclaimについて何を確立・観測したか」だけを表す診断情報である**。過去のrequestによる既存claimの有無・identityの消費有無については**何も保証しない**。(2) `gca_claim_state`は、**client側のretry authorization（再送してよい／してはならないの許可・根拠）ではない**。再送の可否は、Integration Releaseが自身のdurable stateとserver側のfail-closed（duplicateは常に新規mediaを作らない）に基づいて判断する。(3) claim確立前の失敗とclaim確立後の失敗を明確に分離する。**claim確立後は、いかなる失敗でも`none`へ戻らない**（B2）。(4) claim確立後に`PROCESSING`が残りうる結果は、通常の設定不備・要求不正と**誤認されない**fail-closed応答に**正規化**し、Core由来のstatus・code・messageを**透過しない**。(5) 応答形式は下記の「応答の形」に従い一義的に定義する。

`gca_claim_state`の値（**A3で再定義**。A2の「`none`＝identity未消費の証拠」は**撤回**した）：
- `none`：**この requestは、claim確立（`INSERT`の発行）を行っておらず、Coreも呼んでいない**（したがって、この requestがmediaを作成していない）。**過去のrequestが作ったclaimの有無・identityの消費有無は一切示さない**（duplicateの場合も、claim確立前の検査で失敗すれば`none`になりうる）。「identityが未消費である」ことの証拠として扱ってはならない。
- `processing`：この requestがclaimを確立してwinnerとなったが`CONFIRMED`に至っていない、または、この requestが既存の`PROCESSING` rowを観測した。identity消費済み。自動回復しない。
- `unknown`：この requestは、claimが存在するか、またはその状態を**確定できなかった**（claim／CONFIRMのACK曖昧、duplicate-key後のrow読取り失敗、等）。**`processing`と同等に扱う**（消費済みの可能性がある）。
- `confirmed`：この requestがclaimを`CONFIRMED`として確立または観測した。
- `confirmed_inconsistent`：`CONFIRMED` rowを観測したが、attachmentの存在・slug照合が取れない。

**応答の形（A3で一義化、A4で成功payloadを確定）**

**適用範囲（A16）**：本節の形（成功payload・error body・exact key・status）の保証範囲は、**12.1節 CS-1に限る**。投影に到達しない・投影の対象でない・投影後の保証外の応答については、本節の形・閉集合を主張しない。
- **成功（201 first success／200 confirmed replay）**：**初回成功とreplayで、同一のcanonical payloadを返す**。
  ```
  {"id": <int>, "source_url": <string>, "mime_type": <string>, "slug": <string>, "gca_claim_state": "confirmed"}
  ```
  - **この5つのfieldのみ**とし、他のfieldは含めない。**HTTP statusは、first success＝201、confirmed replay＝200**であり、201と200の区別はHTTP statusのみ。**statusとdataの確定（投影）は12章が正本**（P-3・CS-1）。
  - **Core responseの全文は、初回成功時も透過しない**。**full Core media JSONは永続化せず、replayもしない**。
  - **payloadの生成元は、永続化されたsnapshot（`id`／`source_url`／`mime_type`／`slug`の4項目のみ）**である（Core responseから直接構築しない）。snapshotの検証・保存・`CONFIRMED`化の順序は10.4節、Finalizerの責務は12章が正本。replayは保存済みsnapshotから同じ構築を行う。よって初回とreplayは、同一の入力から同一の形・値になる。
  - **現行`WordPressMediaUploader`との互換根拠**（`wordpress_media_uploader.py:245-293`）：応答はdictであること、`id`が正のint（boolは不可）、`source_url`と`mime_type`の**キーが存在**し、各値がstrまたはNoneであることのみを検証し、`MediaUploadResult(media_id, source_url, mime_type)`を返す。canonical payloadはこの3項目をすべて満たし、`slug`と`gca_claim_state`は無視される。したがって現行clientは変更なしでこのpayloadを受理できる。**GCA成功応答はCore Nativeの形ではない**（意図的。GCA-taggedリクエストにのみ適用され、非GCAはZero-Diff）。他のCore fieldに依存するclientは本contractの対象外（R-15）。
  - **限界**：`source_url`は、初回成功時にCore responseの値を検証のうえsnapshotへ保存した値であり、replayは**その時点の値**を返す（現在のURLを再計算しない）。DBでの`source_url`の独立検証は6.38では行わない（17章 U-17）。
- **error（4xx／5xx）**：**WP_Error形式**のJSON `{"code": <error code>, "message": <下記canonical error表の固定message>, "data": {"status": <HTTP status>, "gca_claim_state": <値>}}`。`confirmed_inconsistent`（409 `gca_idempotency_media_missing`）・`E9` markerの`confirmed`（503）・`unknown`・`processing`・`none`のいずれもこの形で、`gca_claim_state`は`data`配下に置く。**成功応答とerror応答で`gca_claim_state`の位置が異なる**（成功＝top-level、error＝`data`配下）ことを契約とする。

**応答表（eligible GCA POST（12.1節 P-2）が12章の投影に到達した場合の網羅。この表の範囲は12.1節 CS-1に従い、範囲外の応答（投影前の終了、eligibleでないrequest、投影後のCore／serverの作用）については、本表の閉集合を主張しない）**

| 時点 | 条件 | HTTP | error code | `gca_claim_state` |
|---|---|---|---|---|
| **claim前** | header欠落・形式違反、allowlist外の要素、body形式／Content-Type不正、body空、cheapな決定的拒否（8.1節、10.2節#1） | 400 | `gca_idempotency_invalid_request` | `none` |
| **claim前** | **bodyサイズが8.1節の固定上限を超過**（8.1節「body size contract」） | **413** | `gca_idempotency_payload_too_large` | `none` |
| **claim前** | capability不足 | 403 | `gca_idempotency_forbidden` | `none` |
| **claim前** | Epoch invalid、**pre-claim Binding不一致／確認不能（9.3節 R1）**、multisite／確認不能（5.5節）、接続契約違反（9.1節）、`claim_token`のCSPRNG失敗（7.8節）、`INSERT`を**発行する前**の基盤障害 | 503 | `gca_idempotency_unavailable` | `none` |
| **claim境界** | `INSERT`の**ACKが曖昧**（接続断・timeout等で、`INSERT`が発行された後に結果不明） | 503 | `gca_idempotency_unavailable` | `unknown` |
| **claim境界** | `INSERT`が一意制約違反以外のerror（結果が確定しない） | 503 | `gca_idempotency_unavailable` | `unknown` |
| **claim境界**（A4追加） | `INSERT`が**エラーなく完了（ACK済み）**したが、**affected rowsが1ではない**（0・2以上・取得不能）、かつ**一意制約違反（duplicate-key）でもない**。**claim成立を断定しない**（rowの有無・状態を確定できない）。**Coreは呼ばず、再`INSERT`もしない** | 503 | `gca_idempotency_claim_indeterminate`（専用の固定error code） | `unknown` |
| **claim後・Core呼出前**（A3追加） | winnerとしてclaim確立後、**Coreを呼ぶ前**の**捕捉可能な内部障害**：例外・メモリ不足等のcatchable error、**post-claim Binding／Epoch再確認（9.3節 R2）の失敗**、multisite再確認の失敗 等。**Coreは呼ばない** | **409** | `gca_idempotency_in_progress` | `processing` |
| **claim後・Core呼出後** | winnerが`CONFIRMED`確定前に失敗：Coreの`WP_Error`（**Core由来のstatusが4xxでも5xxでも**）、Coreの例外、response ID／provenance ID／Verification IDの不一致（11.2節）、provenance 0回／複数回、**Verification直前のBinding／Epoch再確認（9.3節 R3）の失敗**、Verification失敗、`CONFIRMED`への`UPDATE`が**確定的に**失敗 | **409** | `gca_idempotency_in_progress` | `processing` |
| **claim後・Core成功後**（A5追加） | **Coreは成功を返したが、snapshot 4項目の検証（10.4節 手順3）に失敗**：`source_url`が欠落・非str・空、`mime_type`（DBの`post_mime_type`）が許可3種以外、`slug`（DBの`post_name`）が`requested_slug`と不一致、`id`が正のintでない、等。**snapshotを保存せず`CONFIRMED`にしない**。Coreの再実行は禁止 | **409** | `gca_idempotency_in_progress` | `processing` |
| **claim後** | `CONFIRMED`への`UPDATE`の**ACKが曖昧** | 503 | `gca_idempotency_unavailable` | `unknown` |
| **duplicate** | row=`PROCESSING` | 409 | `gca_idempotency_in_progress` | `processing` |
| **duplicate** | row=`CONFIRMED`、Binding再確認OK、Media Verification完遂・attachment・slug照合OK | 200（replay、Finalizer経由・canonical payload） | — | `confirmed` |
| **duplicate** | row=`CONFIRMED`、Binding再確認OK、Media Verificationが**完遂し**、attachmentが**欠落または照合不一致と確定** | 409 | `gca_idempotency_media_missing` | `confirmed_inconsistent` |
| **duplicate**（A4追加） | row=`CONFIRMED`、Binding再確認OKだが、**Media Verification自体が完遂できない**（DB／I/O／接続の障害、timeout等）。attachmentの有無を**確定できない**。**Coreは呼ばない（再実行禁止）** | 503 | `gca_idempotency_unavailable` | `confirmed` |
| **duplicate** | row読取り失敗、epoch invalid、binding不一致、duplicate-key直後にrowが不在 | 503 | `gca_idempotency_unavailable` | `unknown`（rowの有無を確認できないため） |
| **初回成功** | 10.4節の手順1〜4がすべて成功（snapshot保存・`CONFIRMED`化のdurable ACK確認済み）し、**marker＝SUCCESS_FIRST**が設定され、Finalizerがmarkerから構築・置換に成功 | 201 | — | `confirmed` |
| **marker欠落・不正等**（A8、A9で整理） | **markerが欠落・不正・二重設定・別requestのmarker・束縛不一致**（適用範囲は12.1節 P-2・12.4節 B-*、構築は12.1節 P-3が正本）。**identity未消費を意味せず、retry authorizationでもない** | 503 | `gca_idempotency_unavailable`（E5） | `unknown` |
| **Finalizerの適用runtime failure** | Finalizerの適用runtime failureの保証境界は12章に従う（本表では定義しない） | （定義しない） | （定義しない） | （定義しない） |

**最終responseの決定規則**：投影の規則（構築・対象・範囲）は**12章が正本**（A7のresponse classによる分岐は廃止）。上記の各行の「HTTP／error code／`gca_claim_state`」は、marker outcomeに対応するcanonical responseの**内容**を示す（CS-1の範囲内）。

**canonical error表（Amendment A7で正本化。status・error code・message・`gca_claim_state`の組合せの閉集合）**

**CS-1（12.1節）の範囲内で**、errorとして返してよい組合せは、**次の表のE1〜E9のみ**である。messageは**固定のASCII文字列**で、**表と完全一致**でなければならない。**自由文・Core由来のmessage・内部情報・動的な値（ID、path、例外文）を含めてはならず、外部へ透過しない**。`data.status`は`HTTP`列と同じ値、`data`に含めるのは`status`と`gca_claim_state`のみ。

| ID | HTTP | error code | message（完全一致） | `gca_claim_state` | 該当する応答表の行 |
|---|---|---|---|---|---|
| E1 | 400 | `gca_idempotency_invalid_request` | `The idempotent media request is invalid.` | `none` | claim前の要求不正（**client供給の`X-GCA-Identity-Schema`値が対応schemaと不一致の場合を含む**） |
| E2 | 413 | `gca_idempotency_payload_too_large` | `The media payload exceeds the idempotent upload size limit.` | `none` | claim前のbodyサイズ超過 |
| E3 | 403 | `gca_idempotency_forbidden` | `The idempotent media upload is not permitted.` | `none` | claim前の**GCA capability不足**（route callback先頭で確定、12.4節。Coreの権限拒否はE3でなくE5、B-9） |
| E4 | 503 | `gca_idempotency_unavailable` | `The idempotency service is unavailable.` | `none` | claim前の**server内部の**schema／DB／epoch／configuration不一致、Epoch／Binding／multisite／接続契約／CSPRNG／`INSERT`発行前の基盤障害 |
| E5 | 503 | `gca_idempotency_unavailable` | `The idempotency service is unavailable.` | `unknown` | claim境界のACK曖昧・非duplicateのerror、claim後の`UPDATE`のACK曖昧、duplicate経路のrow読取り失敗等、**およびFinalizerのmarker欠落・不正・二重設定・別request・束縛不一致（12章）** |
| E6 | 503 | `gca_idempotency_claim_indeterminate` | `The idempotency claim state could not be determined.` | `unknown` | `INSERT`がACK済みでaffected rows≠1かつduplicate-keyでない |
| E7 | 409 | `gca_idempotency_in_progress` | `The idempotent media request is in progress or requires manual review.` | `processing` | claim後の`PROCESSING`系の失敗、duplicateのrow=`PROCESSING` |
| E8 | 409 | `gca_idempotency_media_missing` | `The confirmed media could not be verified.` | `confirmed_inconsistent` | `CONFIRMED` duplicateでattachment欠落・不一致が確定 |
| E9 | 503 | `gca_idempotency_unavailable` | `The idempotency service is unavailable.` | `confirmed` | **E9は、plugin control pathが`E9` markerを明示的に設定する場合に限る**：`CONFIRMED` duplicateでMedia Verificationが完遂不能（DB／I/O障害等、10.3節・C9）。（Finalizerの適用runtime failureの保証境界は12章に従う） |

- 応答表の各errorの行は、上記E1〜E9のいずれかに**ちょうど1つ**対応する。**CS-1の範囲内では**、表に無い組合せ（例：409と`none`、400と`processing`、503・`unavailable`と`confirmed_inconsistent`）は存在しない。
- 同一のerror code・messageが複数のstateで使われる（E4・E5・E9は同一のcodeとmessageで、`gca_claim_state`のみが異なる）。stateは`data.gca_claim_state`で区別し、messageでは区別しない。
- 本表のE1〜E9は、12章の投影がmarker outcomeから構築するresponseの**内容の正本**である（構築の規則・exact-keyは12章。CS-1の範囲内）。

**契約（規範）**
1. **claim後のCore非success（`WP_Error`含む、4xx・5xxを問わず）は、Coreのstatus・code・message・dataを一切応答へ転記せず、一律に409 `gca_idempotency_in_progress`（`processing`）へ正規化する。** Core由来の400／413／415等が「要求不正（再送で直る）」と誤認されることを防ぐ。Coreの元のerror情報は、secret・claim_token・内部pathを含まない範囲でserver側ログにのみ記録してよい。**この規則は「Coreの非successの扱い」に限る。claim確立後の失敗が常に409になるという意味ではない**（claim後でも、ACK曖昧の503 `unknown`、`E9` markerによる`CONFIRMED` duplicateのVerification不能の503 `confirmed`、confirmed inconsistencyの409 `confirmed_inconsistent`等がある。**応答の正本は上記の応答表とcanonical error表**）。
2. **400・403・413は常に`gca_claim_state = none`**であり、**claim確立前（`INSERT`発行前）にしか返さない**。claim確立後（`INSERT`のwinnerになった後）は、**いかなる失敗でも`none`・400・403・413を返してはならない**（B2）。
3. 409は「この requestがclaimを確立済み、または既存の`PROCESSING`／不整合`CONFIRMED` rowを観測した」ことを意味し、503は「基盤障害・結果不明（`E9` markerによる`CONFIRMED` duplicateのVerification不能を含む）」を意味する（`gca_claim_state`で区別する）。**Finalizerの適用runtime失敗の挙動は、本節では定義せず、12章の保証境界に従う**。
4. **`gca_claim_state = none`は、「この requestはclaimを確立せずCoreも呼んでいない」ことだけを示す。過去のrequestが作成したclaimの有無・identityの消費有無を示さず、「未消費」の証拠として扱ってはならない**（B1。duplicateのrequestでも、claim確立前の検査で失敗すれば`none`になりうる）。`gca_claim_state`を欠く応答（proxy・web server・WAF・PHPのfatal由来の応答、transport error・timeoutを含む）は、**この requestの結果が不明**として扱い、やはり消費有無を示さない。**`gca_claim_state`はretry authorizationではない**（原則(2)）。**Finalizerの適用runtime failureの保証境界は12章に従う**（本契約では定義しない）。
5. 応答bodyに含めてよいのは、error応答では`code`／`message`（**canonical error表E1〜E9の固定message、完全一致**）／`data.status`／`data.gca_claim_state`のみ、成功応答ではcanonical payloadの5 field（`id`／`source_url`／`mime_type`／`slug`／`gca_claim_state`）のみ（「応答の形」参照）。`claim_token`・`idempotency_key`・Claims Tableの内容・Core responseの上記以外のfield・Core内部情報・DB情報を含めてはならない。
6. 現行Python clientは409を`REQUEST_REJECTED`、503を`SERVER_ERROR`に分類する。この分類と`gca_claim_state`の写像は**Integration Releaseの責務**（6.38では実装しない、23章）。
7. **duplicate経路でのBinding再確認とMedia Verificationの区別（A4）**：`CONFIRMED` rowを観測した**後**にBinding再確認（9.3節）が失敗・確認不能な場合は、**row読取り自体の信頼性（正しいDBを読んだか）が確認できない**ため、`gca_claim_state = unknown`（503）とする。Binding再確認が成功した**後**にMedia Verificationが完遂できない場合は、`CONFIRMED` rowは信頼できる観測であるため`confirmed`（503）とし、attachmentの欠落が**確定**した場合のみ`confirmed_inconsistent`（409）とする。**いずれの場合もCoreを再実行しない**（`CONFIRMED`のidentityに対するCore呼出は常に禁止）。
8. **`INSERT`のACK済みだがaffected rowsが1でも一意制約違反でもない**場合（A4）：claim成立を断定せず、`gca_claim_state = unknown`・503・専用code`gca_idempotency_claim_indeterminate`とし、Coreを呼ばず再`INSERT`しない。後続のrequestがrowを観測して確定する（10.6節 C6e）。

このcontractの検証：L1（応答表・canonical error表の定数（status・code・message・`gca_claim_state`の組）が閉じていること、claim後経路でCore error情報を転記するコードが存在しないことの静的検査）、L2（各行の網羅、**canonical error表の各組のmessage完全一致**、Core 4xx／5xx注入でもCore由来のstatus・code・messageが応答に現れないこと）、L3（実Coreでの再現）。15章 T-22。

---

## 9. DB接続の分離設計

v1は3種類の、物理的に分離されたDB接続を用いる：

1. **Core既存の`$wpdb`**：WordPress Core自身が用いる既存接続。触れず既存のまま利用する。
2. **Claims Connection**：Claims Tableの`INSERT`（winner判定）・`CONFIRMED`への`UPDATE`・duplicate時のrow読取り専用の独立接続。
3. **Media Verification Connection**：CoreがDBへattachmentを永続化したことを、Claims ConnectionともCore `$wpdb`とも異なる第3の接続から独立に確認する、writer-pinned接続。

### 9.1 接続契約

Claims Connection・Media Verification Connectionとも、**SELECT／INSERT／UPDATEの直前**に、その接続上で次を確認する：

- InnoDB engine
- `transaction_isolation = READ-COMMITTED`（またはそれより厳格）
- `autocommit = 1`
- `in_transaction = 0`

これにより、未コミットトランザクション由来のdirty readと、claimのdurability曖昧性を排除する。

### 9.2 永続化状態の照合

- `CONFIRMED`への遷移には、Media Verification Connectionから読み取った**永続化済み`post_name`が`requested_slug`と完全一致**することを要件とする（filterableなREST応答ではなくDB永続化状態を根拠とする）。Coreが`wp_unique_post_slug`で別slugへ変更した場合も、完全一致要件により検出される。照合クエリは、9.3節で束縛された**同一schemaの`{prefix}posts`**に対して、`post_type = 'attachment'`・`ID`・`post_name`を条件とし、あわせて永続化済みの`post_mime_type`を読み取る（A4：snapshotの`mime_type`の根拠、12章）。

### 9.3 Authoritative Binding Contract（Amendment A2で追加、規範的precondition）

per-connectionのtransaction確認（9.1節）だけでは、3本の接続が**同じ書き込み先**を指していることを証明しない。別DB・別schema・別site・別prefixを指す接続が、たまたまIDとslugが一致するrowを返せば、偽の`CONFIRMED`が成立しうる。これを防ぐため、次を**規範的preconditionとして契約**する。

1. **配置**：Claims Table（`{prefix}gca_media_claims`）は、**WordPress本体のテーブル（`{prefix}posts`等）と同一のDB・schema・table prefixに置く**。別DBへの分離は許可しない（6.3節のとおり、同一DB内の継続性としてEpochを定義するため）。
2. **Binding Fingerprint**：3接続それぞれから、次の組を取得する。
   - writerであること：`@@read_only = 0`（かつ`@@super_read_only = 0`が取得可能な場合はそれも）
   - DB server identity：`@@server_uuid`（取得可能な場合）
   - DB／schema名：`DATABASE()`
   - table prefix：Claims／Verification接続が使う`{prefix}`と、Coreの`$wpdb->prefix`
   - site：single-site確認（5.5節）、およびblog IDが単一siteの値であること
   - Epoch：anchor（7.2節）に記録した`store_generation_id`
   
   Coreの`$wpdb`側は、**プロパティ・定数の参照**（`$wpdb->prefix`・`DB_NAME`等）を基本とし、`@@server_uuid`等の取得に読取り専用のSELECT 1本を要する場合のみ、それを許可する。この読取り専用SELECTが許容されるかは**未検証**（17章 U-8）。許容されない／取得不能な項目は「確認不能」として扱う（下記4）。
3. **一致条件**：3接続のFingerprintが**すべての項目で一致**し、かつanchorに記録された値と一致すること。
4. **確認不能・不一致は拒否**：1項目でも不一致、または取得不能（クエリ失敗・権限なし・値がNULL等）の場合は、**Core実行（または`CONFIRMED`化）に進まず**fail-closedする。「確認できなかった」を「一致した」と解釈しない。**失敗時の応答は、確認点（下記5）によって異なる**（claim確立後は`none`へ戻らない、B2）。
5. **確認点と、失敗時の挙動（A3で確定）**：確認はplugin enable時と、GCA-taggedリクエストごとの次の**3点**で行う。同一request内で結果をキャッシュしてよいが、確認点Rごとに**再取得**し、requestをまたいでキャッシュしない。

   | 確認点 | 時点 | 失敗時の挙動 |
   |---|---|---|
   | **R1（pre-claim）** | claim `INSERT`の**発行前**（10.2節#2） | **claimを作らず、Coreを呼ばない**。503 `gca_idempotency_unavailable`、`gca_claim_state = none`（8.3節） |
   | **R2（post-claim・pre-Core）** | claim確立（winner）の**後、Coreを呼ぶ前**（claimとCoreの間のdrift・failoverを検出するため） | **`PROCESSING`を保持**し（claimを取り消さない・削除しない）、**Coreを呼ばない**。409 `gca_idempotency_in_progress`、`gca_claim_state = processing`。**`none`へ戻らない** |
   | **R3（post-Core・pre-Verification）** | Coreが返した後、Verification（9.2節）の**直前**（Verification接続のFingerprintを再確認） | **`PROCESSING`を保持**し、`CONFIRMED`にしない。409 `gca_idempotency_in_progress`、`gca_claim_state = processing`。**`none`へ戻らない** |

   - **duplicateの経路**（`INSERT`が一意制約違反）：duplicate-keyを観測した**後**にBinding／Epochの再確認や row読取りが失敗した場合は、既存rowの**状態を確定できない**ため、**503 `gca_idempotency_unavailable`、`gca_claim_state = unknown`**（10.3節）。この経路でもCoreは呼ばず、再`INSERT`しない。
   - **一般則**：`INSERT`のwinnerになった後は、Core呼出の前後を問わず、Binding／Epoch／multisiteの再確認が失敗しても、**claimを取り消さず（`PROCESSING`を保持）、応答は409 `processing`（またはACK曖昧の503 `unknown`）**とする（**この規則の対象は、上記のBinding／Epoch／multisiteの再確認の失敗**であり、claim後の応答全体の正本は8.3節の応答表とcanonical error表）。`none`・400・403・413を返してはならない（8.3節 契約#2）。
6. **L2／L3検証**（15章 T-23、A3でpre-claim／post-claim／duplicateに分割）：L2（接続fakeのFingerprintを項目ごとに食い違わせ／取得不能にする：R1失敗→claim 0・Core 0・503 `none`、R2失敗→`PROCESSING`・Core 0・409 `processing`、R3失敗→`PROCESSING`・`CONFIRMED`なし・409 `processing`、duplicate経路の失敗→Core 0・503 `unknown`）、L3（Verification接続を**別schemaへ向け、そこにID・slugがたまたま一致するrowを置く**構成で、`CONFIRMED`にならず`PROCESSING`のままとなること。および、別prefix・read-only接続・別server_uuid構成での拒否）。

---

## 10. Claim / State Machine / Crash Boundary（Amendment A1で全面改訂）

### 10.1 状態機械

```
        (claim INSERT 勝者, affected rows = 1, durable)
 absent ───────────────────────────────────────────────▶ PROCESSING
                                                            │
        (検証通過 + guarded UPDATE, affected rows = 1)      │
 CONFIRMED ◀────────────────────────────────────────────────┘
```

- 状態は`PROCESSING`と`CONFIRMED`のみ。**他の遷移（`PROCESSING`→absent、`CONFIRMED`→任意）は存在しない。**

### 10.2 Atomic claim条件（Core実行の前提）

Coreの`create_item`を呼ぶのは、次の**すべて**が成立した場合のみ：

1. GCA-taggedとして完全に有効（8.2節）、capability保有（7.3節）、parameter allowlist通過（8.1節）。**cheapな決定的拒否（content-type許可・body非空・8.1節の固定サイズ上限33,554,432バイト）はclaim前に完了させる**（確定的に失敗する要求でlogical identityを消費しないため）。
2. Valid Epoch（6.5節の検出可能なmismatchなし）、**Authoritative Binding成立（9.3節）**、**single-siteの積極的確認（5.5節）**。いずれも確認不能なら不成立として扱う。
3. Claims Connectionが9.1節の接続契約を満たす。
4. `claim_token`をCSPRNGで生成できた（7.8節）。
5. `INSERT … state='PROCESSING', claim_token=<random>`の**affected rowsが厳密に1**で、autocommitによるcommit ACKを受領した。

上記のいずれかが満たされない・曖昧な場合はCoreを**呼ばない**（作業ゼロ）。`INSERT`のACKが曖昧（接続断・timeout等）な場合、rowが存在するか不明であるが、**再`INSERT`もCore実行も行わず**fail-closedする（rowが実在すれば`PROCESSING`のまま残る。これはat-most-onceのコストとして受容する）。応答は8.3節の表に従い、`INSERT`発行**前**の失敗は`gca_claim_state = none`、発行**後**でACK不明なら`unknown`とする。

**`INSERT`の結果の分類（A4で網羅化）**：`INSERT`の結果は次の3つに分かれ、それ以外はない。(a) **affected rowsがちょうど1**（エラーなし）→ winner（上記#5）。(b) **一意制約違反（duplicate-key）** → duplicateとして10.3節。(c) **上記のいずれでもない**（エラーなしで完了したがaffected rowsが0・2以上・取得不能、または一意制約違反以外のerror、またはACK曖昧）→ **claim成立を断定せず**、Coreを呼ばず、再`INSERT`もせず、503・`gca_claim_state = unknown`（affected rowsが1でなくエラーもない場合は専用code `gca_idempotency_claim_indeterminate`、それ以外は`gca_idempotency_unavailable`、8.3節）。(c)でrowが実在した場合は`PROCESSING`のまま残り、後続requestが観測して確定する（10.6節 C6a・C6e）。

**claim確立後〜Core呼出前の手順（A3で追加）**：winnerとして`INSERT`のACKを受領した**後**は、Coreを呼ぶ前に9.3節のR2（Binding／Epoch／multisiteの再確認）を行う。R2の失敗、およびこの区間で発生した**捕捉可能な内部障害**（例外、メモリ不足等のcatchable error、応答構築の失敗）は、いずれも**`PROCESSING`を保持**し、**Coreを呼ばず**、**409 `gca_idempotency_in_progress`（`processing`）**で応答する（8.3節「claim後・Core呼出前」行）。この区間でclaimを削除・取消・`none`へ戻すことはしない。PHP自体の異常終了（応答を返せない）の場合は、transport errorとなり、10.6節のC1のとおり`PROCESSING`が残る。

### 10.3 Duplicate request（`INSERT`が勝者にならなかった場合）

duplicate-key（一意制約違反）の場合のみ、既存rowを読み取って次のとおり処理する。**いずれの場合もCoreの`create_item`は呼ばず、新規mediaを作らない。**

| 既存row状態 | 動作 |
|---|---|
| `CONFIRMED` | CONFIRMED snapshotをreplayする。replay前にBinding再確認（9.3節。**失敗・確認不能の場合は503 `unknown`**、Coreは呼ばない）を行い、Media Verification Connectionでattachmentの存在と`post_name == requested_slug`を再確認する。一致すれば、**marker＝`SUCCESS_REPLAY`を設定**（設定条件・保持物は12章 marker表）し（responseの構築は12章、内容は8.3節）、Verificationが完遂し不一致・欠落と**確定**した場合は409 `gca_idempotency_media_missing`（`confirmed_inconsistent`、新規作成しない）、**Verification自体が完遂できない場合（DB／I/O障害等）は503 `gca_idempotency_unavailable`（`confirmed`）**。いずれの場合もCoreは呼ばない。**画像bytes・mime・filename・診断digestが初回と異なっていても既存mediaを返し、再生成・再uploadを要求しない**。 |
| `PROCESSING` | **新規mediaを作らずfail-closed**：409 `gca_idempotency_in_progress`（`processing`）。待機・polling・自動promoteは行わない（同時実行中の勝者か、crash後のstale `PROCESSING`かを区別しない）。 |
| row読取り失敗／epoch invalid／binding不一致／row不在（duplicate-key直後に消えた等） | 503 `gca_idempotency_unavailable`（`unknown`、rowの有無を確認できないため）。再`INSERT`しない。 |
### 10.4 勝者の完了処理（`PROCESSING → CONFIRMED`）

**finalizationの所有者と順序（Amendment A5で統一。ここが正本）**

**所有者**：状態の検証・保存・`CONFIRMED`化は、**route callback（wrapper）が単独で行う**（SP-1）。Finalizerの責務は12章が正本。

**route callbackの順序（この順序でのみ成功応答を返せる）**

1. **Core成功**：Coreの`create_item`を**1回だけ**呼び、成功応答を受ける。
2. **Provenance・Verification**：Provenance（11.1節：同一Requestオブジェクト・`creating === true`・exactly-once）と、Media Verification（9.2節。直前にR3、9.3節）で、**Core response ID＝provenance ID＝Verification ID**を確認し、永続化済みの`post_name`／`post_mime_type`を読み取る。
3. **snapshot 4項目の検証**：`id`（上記の一致した正のint）、`slug`（Verificationで読み取った`post_name`が`requested_slug`と完全一致）、`mime_type`（Verificationで読み取った`post_mime_type`が8.1節の許可3種のいずれか）、`source_url`（Core responseの値で非空のstr）。**1項目でも満たされなければ、snapshotを保存せず`CONFIRMED`にせず**、`PROCESSING`を保持して**409 `processing`**（8.3節「claim後・snapshot検証失敗」行、C10）。
4. **snapshot保存と`CONFIRMED`化**：`UPDATE … SET state='CONFIRMED', media_id=?, snapshot=?(4項目) WHERE idempotency_key=? AND state='PROCESSING' AND claim_token=?`を**1回のUPDATE**で行い、affected rowsが厳密に1であり、かつ**durable ACKを確認**する。確定的な失敗は409 `processing`（C7）、ACK曖昧は503 `unknown`（C8）。
5. **marker＝SUCCESS_FIRSTの設定**：手順1〜4がすべて成功した場合**のみ**、route callbackは`SUCCESS_FIRST`のmarkerを設定する（設定条件・内容・規則は12章 marker表・marker確定規則(4)）。最終responseの構築は12章（P-3）。

**途中失敗の扱い**：手順1〜4のいずれかが失敗した場合は、`PROCESSING`を保持したまま、8.3節の表に従い**409 `processing`**（ACK曖昧のみ503 `unknown`）で応答する。**success扱い（2xxの返却、またはcanonical payloadの構築）を禁止**する。Core由来のstatus・messageは透過しない。

**Finalizerの役割**：12章が正本（本節は再定義しない）。

### 10.5 Stale `PROCESSING`のautomatic reclaim禁止

- `PROCESSING`のrowを**自動で解除・再claim・再実行・自動promote（Media Verificationで見つかったからという理由での`CONFIRMED`化を含む）しない**。時間経過（TTL）による失効も設けない。
- 理由：`PROCESSING`が「Core実行前のcrash」か「Core実行後のcrash」かをserverは区別できない。区別できない状態から自動で再実行すれば重複authorizationになりうる。
- 解消は**manual reconciliation（Future／Out of Scope）**のみ。6.38はそのために必要な診断情報（`article_identity`／`media_role`／`content_revision`／`created_at`／`state`）をclaim行に残す責務だけを負い、tool自体は作らない。

### 10.6 Crash boundary・ambiguous outcome一覧

| # | 時点 | durable状態 | media | 当該request／同一identityのduplicateの応答（8.3節） | 解消 |
|---|---|---|---|---|---|
| C0 | claim `INSERT`前 | row無し | 無し | 通常の新規claim | 不要 |
| **C1a** | `INSERT`確立後〜Core呼出前の**捕捉可能な内部障害**（例外・メモリ不足等のcatchable error、R2（9.3節）の失敗）。**Coreは呼ばない** | `PROCESSING`（保持。取消・削除しない） | 無し | 当該requestは**409 `gca_idempotency_in_progress`（`processing`）**（8.3節「claim後・Core呼出前」行）。`none`へ戻らない。duplicateは409 `processing` | manual（Future） |
| **C1b** | `INSERT`確立後〜Core呼出前の**PHP異常終了**（kill／fatal等で応答を返せない。**crash before side effect**） | `PROCESSING` | 無し | 当該requestはtransport error（応答なし）。duplicateは409 `processing` | manual（Future） |
| C2 | Core実行中（途中でcrash／timeout／fatal） | `PROCESSING` | 部分的に存在しうる（orphan） | 同上。Core由来のerrorは透過しない | manual（orphan cleanupはOut of Scope） |
| C3 | Core成功後〜`CONFIRMED`確定前（**crash/timeout after side effect before CONFIRMED**） | `PROCESSING` | **存在** | 同上。duplicateは409（自動promoteしない） | manual |
| C4 | `CONFIRMED`確定後〜応答返却前（ACK喪失含む） | `CONFIRMED` | 存在 | duplicateはreplay（200、`confirmed`） | 自動（duplicate replay） |
| C5 | Finalizerの適用runtime failure。**保証境界は12章に従う（本表では定義しない）** | （12章に従う） | （12章に従う） | （12章に従う） | （12章に従う） |
| **C5b**（A8追加、A14で参照を更新） | **marker欠落・不正・二重設定・別requestのmarker・束縛不一致**（route callbackに到達しなかったGCA request（12.4節 B-*）を含む）。**`CONFIRMED`の有無はmarkerからは確認できない** | 不明（claimを確立していた場合は`PROCESSING`／`CONFIRMED`のいずれもありうる） | 不明 | 当該requestは503 `unknown`（E5）。**canonical successを返さない**。pre-Finalizerの応答がsuccess（2xx）に見えても、markerが無ければE5へ置換する（Finalizerの適用runtime failureの保証境界は12章に従う） | 後続duplicateの観測で確定（identity消費の有無は示さない） |
| **C6a** | **original request**のclaim `INSERT`のACKが曖昧（接続断・timeout・発行後の結果不明） | **不明**（commit済み／rollback済み／遅延commitのいずれもありうる。一意制約により**高々1行**） | 無し（当該requestはCoreを**呼ばない**） | 当該requestは503 `unknown`。当該requestは**再`INSERT`もCore実行もしない** | 後続requestの観測（C6b／C6c）で確定 |
| **C6b** | C6aの**後続request**：rowが**commit済み**（`PROCESSING`） | `PROCESSING`（mediaは無し） | 無し | 後続requestは409 `processing`（duplicate、rowを観測したため）。**C6aのoriginal requestはCoreを実行していないが、identityは消費されたまま**（manualを要する） | manual（Future）。at-most-onceのコストとして受容 |
| **C6c** | C6aの**後続request**：rowが**存在しない**（rollback済み／未commit） | row無し | 無し | 後続requestは**新規claimに正当に勝てる**（C0と同じ通常経路）。**遅延commitの可能性**：後続requestのclaimの**後**にoriginalの`INSERT`が遅れて到達しても、一意制約により後者は失敗し行は高々1つで、original側のPHPは既にCoreを実行しない（ACK不明でfail-closed済み）ため、二重実行は起きない | 自動（後続requestが通常処理） |
| C6d | claim時にClaims DBへ**到達不能**（`INSERT`発行前に確定的に失敗） | row無し（発行していない） | 無し | 503 `none`（この requestは`INSERT`を発行しておらずCoreも呼んでいない。過去のrequestによる消費の有無は示さない） | 回復後に再送された requestは通常処理される（再送の可否判断はIntegration Releaseの責務） |
| **C6e**（A4追加） | `INSERT`が**エラーなくACK済み**だが、**affected rowsが1でなく**（0・2以上・取得不能）、**duplicate-keyでもない** | **不明**（rowが存在するか、存在するならどの状態かを断定できない。一意制約により高々1行） | 無し（当該requestはCoreを**呼ばない**） | 当該requestは503 `gca_idempotency_claim_indeterminate`（`unknown`）。再`INSERT`もCore実行もしない。後続requestはrowを観測する：commit済みなら409 `processing`（C6b）、不在なら新規claimに勝てる（C6c） | 後続requestの観測で確定 |
| **C9**（A4追加） | `CONFIRMED`の**duplicate**で、claim読取りは成功しBinding再確認もOKだが、**Media Verificationが完遂できない**（DB／I/O障害等） | `CONFIRMED`（不変） | 存在（有無は確認できない） | 503 `gca_idempotency_unavailable`（`confirmed`）。Coreは呼ばない（再実行禁止）。attachmentの欠落が**確定**した場合のみ409 `gca_idempotency_media_missing`（`confirmed_inconsistent`） | 自動（Verification回復後のreplay）または、欠落確定ならmanual |
| C7 | R3（9.3節）の失敗／Verification Connection失敗／`CONFIRMED`への`UPDATE`が**確定的に**失敗（Core成功後） | `PROCESSING` | 存在 | 当該requestは409 `processing`。duplicateは409 | manual |
| C8 | `CONFIRMED`への`UPDATE`の**ACKが曖昧**（Core成功後） | `CONFIRMED`か`PROCESSING`か不明 | 存在 | 当該requestは503 `unknown`。後続duplicateは、commit済みならreplay（200）、未commitなら409 | 後続duplicateの観測で確定 |
| **C10**（A5追加） | **Coreは成功を返した後、snapshot 4項目の検証（10.4節 手順3）に失敗**（`source_url`の欠落・不正、`mime_type`が許可外、`slug`不一致、`id`不正 等）。snapshotを**保存せず**、`CONFIRMED`にしない | `PROCESSING`（保持） | **存在**（Coreが作成済み） | 当該requestは**409 `gca_idempotency_in_progress`（`processing`）**。success扱い（2xx・canonical payload構築）は禁止。duplicateは409 | manual（自動promote・Core再実行なし） |
| **C11**（A5追加） | `CONFIRMED`化のdurable ACK確認**後**〜応答返却前の、**Finalizerの適用runtime failure以外**の障害（例：応答を返す前のPHPの異常終了。Finalizerの適用runtime failureは、12章 F-* に従い、本行では扱わない） | `CONFIRMED` | 存在 | 応答を返せなければtransport error。`CONFIRMED`はdurable ACK確認済みで、duplicateはreplay（200）できる | 自動（duplicate replay） |

- **Coreが非successを返した場合（`WP_Error`含む）も、`PROCESSING`を残す**（deterministicなCore拒否でもlogical identityが消費される）。10.2節#1でcheapな決定的拒否をclaim前に寄せるのはこのコストを減らすためである。「Media Verificationで不在を確認できた確定的失敗に限りclaimを解放してよいか」は**6.38では採用しない**（reclaimの一形態であり、orphanファイルの存在を排除できないため）。この判断は25章（設計判断の索引）に記載する。
- クライアント切断・PHP `max_execution_time`によるC2/C3の発生を減らすため、GCA経路では`ignore_user_abort(true)`相当の継続実行を要件候補とするが、WordPress実環境での有効性は**未確認**（17章 U-12、L3で確認）。

### 10.7 CONFIRM ACK曖昧性（旧Draft §10の維持）

- `CONFIRMED`への`UPDATE`のcommit ACKが失われた・曖昧な場合（C8）、当該requestは503 `gca_idempotency_unavailable`（`unknown`）で失敗させる。同一requestでのreconnect-and-recoverは行わない。durableに`CONFIRMED`済みであれば後続のduplicateがsnapshotをreplayし、未commitなら`PROCESSING`としてmanual（C7相当）。「元のrequestとreplayの両方が自らauthoritativeだと誤認するwindow」は構造的に排除される。

---

## 11. Provenance と 5-way ID Equality

### 11.1 Provenanceの位置づけ（補助証跡）

- `rest_after_insert_attachment`の発火は、**認証済み・偽造不能な証跡としては扱わない**（同一requestオブジェクトを保持するin-processコードは再帰的・独立に発火させうる）。
- CONFIRMへの遷移には、同一の`WP_REST_Request`オブジェクト・`creating === true`・acceptedな発火が**厳密に1回**、をすべて要求する（0回・複数回はCONFIRM失敗＝`PROCESSING`のまま）。

### 11.2 5-way ID Equality（最終不変条件）

```
client-visible ID = response ID = provenance ID = Media Verification ID = CONFIRMED snapshot ID
```

いずれか1つでも不一致の場合、CONFIRMは失敗する（fail-closed）。

**検証の位置（A5）**：`CONFIRMED`化の**前**（10.4節 手順2）に確認できるのは、`response ID`（Core response）・`provenance ID`・`Media Verification ID`・（保存する）`CONFIRMED snapshot ID`の一致である。**`client-visible ID`は、12章の投影が、markerのsnapshotだけから構築することで、構成上snapshot IDと一致する**（構築・markerの確認・fail-closedの規則は12章が正本。保証の範囲はCS-1）。この構成上の一致は、post-callbackでの応答改変とmarker不整合を注入するL3（T-16・T-34）、および最終的なclient-visible JSONとHTTP statusの照合（T-30）で確認する。

---

## 12. GCA Final Response Finalizer（post-callback応答保全）

pre-callback filter topologyだけでなく、Core callback**返却後**の応答改変が11.2節のID equalityを事後的に破りうるため、次を要件とする。**本章が、応答の投影（status・data・response headersの確定）、投影後の改変点、control pathの網羅範囲、batchの扱いの唯一の正本である**（Amendment A14）。他の章・表・テスト・Roadmapは、本章の識別子（O-*・P-*・MO-*・RD-*・CS-1・SP-*・H-*・X-*・B-*・BT-*・F-*）で参照するのみで、内容を再記述しない。**marker・control path・投影・method境界・call-site・投影後のtopology・nested／batchの境界の唯一の正本は本章**（A16・A17・A18）。

**A14の訂正（Implementation Start Validation、2026-10-06）**：A13までの前提（`rest_pre_echo_response`でのstatus置換、Finalizer後の改変点ゼロ、control pathによるGCA requestの網羅）は、WordPress 7.1.1のsourceで**偽と判明し撤回**した（V-11〜V-13。現行契約は12.1〜12.5節）。

1. **post-callback filter topologyもEpochへbind**（5.3節#5。対象は12.3節 X-4・X-6・X-7、およびP-4）。
2. **GCAリクエストではmanual serving（`rest_pre_serve_request`による短絡）を禁止**（12.3節 X-4）。
3. **GCAリクエストでは`_envelope` / `_embed` / `_fields` / `_jsonp`等のresponse-shapingパラメータを禁止**（8.1節のallowlist。Coreがplugin後に作用する範囲の扱いは12.3節 X-1・X-5・X-8）。
4. **GCA Final Response Finalizer と authoritative outcome marker（Amendment A8で全面改訂。A7のresponse-class 3-way dispatchは廃止。A14で投影hookを`rest_post_dispatch`へ変更）**：承認済みの`rest_post_dispatch`filterの**最後のcallback**（priorityは最大、P-4）として新設する。
   - **原則**：**最終応答の唯一の根拠は、plugin-private・write-onceの authoritative outcome marker である**。Finalizerは、pre-Finalizerの応答（Coreまたは他のcallbackが作った応答）の**status・data・種別を判断材料にせず、透過も分類もしない**。**markerだけから最終responseを新規に構築し、新しい`WP_REST_Response`を返すことで、HTTP status・data・response headersを完全置換する**（P-3）。
   - **対象**：**投影eligibility（12.1節 P-2、PE-1〜PE-3）を満たすrequestだけ**。それ以外（非GCA、他route、effective methodがPOST以外のrequest（MO-2）等）には作用しない（Zero-Diff）。
   - **plugin control path（markerの設定主体。A16で単純化）**：本pluginが`rest_endpoints`で置換した**route callbackだけ**（8章。GCA capability判定（7.3節）・validation・allowlist・body size・Epoch／Binding／multisite・claim・Core呼出・Verification・snapshot保存・`CONFIRMED`化のすべて）。**`permission_callback`は置換せず（Coreのまま）、markerに一切関与しない**（12.4節）。route callbackに到達した各GCA POSTについて、markerをその出口でちょうど1回確定する。**route callbackに到達しない経路の一覧と扱いは12.4節 B-*が正本**。**side-effect safetyと投影の分離は12.1節 SP-1〜SP-3が正本**。
   - **marker（A8）**：次を持つ、**request-local**（新しいdurable stateではない）・**plugin-private**・**write-once**の状態。(a)**exact `WP_REST_Request`オブジェクトのinstance identity**（同一instanceへの束縛。値の等価ではない）、(b)**outcome**、(c)outcomeがsuccessの場合のみ、**idempotency_key**と**durable snapshot**（`id`／`source_url`／`mime_type`／`slug`の4項目のみ）。

     | outcome | 設定する時点（これより前には設定しない） | marker内の保持物 | Finalizerが構築する最終response |
     |---|---|---|---|
     | **SUCCESS_FIRST** | 10.4節 手順4の**`CONFIRMED`への`UPDATE`のdurable ACKを確認した後のみ** | idempotency_key、**durable snapshot**（ACK済み） | **canonical 5-field payload＋HTTP 201** |
     | **SUCCESS_REPLAY** | 10.3節の**`CONFIRMED` rowの読取り・Binding再確認・Media Verificationがすべて成功した後のみ** | idempotency_key、**durable snapshot**（読取り済み） | **canonical 5-field payload＋HTTP 200** |
     | **E1〜E9** | そのerrorを決定した**decision point**（8.3節の応答表の各行の判定点） | outcome（E-id）のみ | **canonical error表（8.3節）の該当行**を、固定のHTTP status・error code・message・`gca_claim_state`で構築 |

   - **markerの確定規則**：(1)**単一の出口で、ちょうど1回**設定する。(2)**二重設定・欠落・不正（outcomeが許可集合外、束縛requestが異なる、success outcomeでidempotency_key・snapshotが欠落または型不正、等）・別requestのmarker**は、いずれも**E5（503 `gca_idempotency_unavailable`／`unknown`）へfail-closed**する。(3)markerの設定後に、controlの内部で別のoutcomeを設定しようとした場合も、(2)の二重設定として扱う。(4)**SUCCESS_FIRSTは、10.4節 手順4のdurable ACK確認前には設定できない**（success responseを返せる経路の下限）。**(5)（A16）`permission_callback`は、markerを作成・変更しない。** markerを確定するのは、route callbackだけである（12.4節）。
   - **Finalizerの確認と構築（DB I/Oなし）**：置換の前に、(1)markerが存在する、(2)`rest_post_dispatch`に渡された**第3引数のrequest**が、markerに束縛されたinstanceと**同一**である（P-5）、(3)outcomeが`SUCCESS_FIRST`／`SUCCESS_REPLAY`／`E1`〜`E9`のいずれかである、(4)successの場合、markerのidempotency_keyが、そのrequestの`X-GCA-*` header（8.2節）から**再導出した**keyと一致し、snapshotが4項目を持ち型が正しい（`id`が正のint、他は非空のstr。**型の確認のみで、DB照合・許可集合の判定は行わない**）、を確認する。満たされなければ**E5へfail-closed**。確認後、**markerからresponseを新規に構築**し、**新しい`WP_REST_Response`をfilterの戻り値として返す**ことで、HTTP status・data・response headersを**完全置換**する（受け取ったresponse objectは変更・再利用しない。P-3）。
   - **exact-key contract（A8、Review #15 M2）**：Finalizerが出力するresponseは、**許可されたexact key setだけ**を持つ。**success**＝top-levelが`id`／`source_url`／`mime_type`／`slug`／`gca_claim_state`の**ちょうど5 key**。**error**＝top-levelが`code`／`message`／`data`の**ちょうど3 key**で、`data`は`status`／`gca_claim_state`の**ちょうど2 key**。pre-Finalizerの応答に**余分なtop-level fieldや`data`のfieldがあっても、最終responseには残らない**（既存responseを引き継がず、新規構築するため）。**incoming responseのkey集合の判定には依存しない**。
   - **pre-Finalizerの応答の改変に対する復元（A8、Review #15 B1・N1）**：pre-Finalizerのcallbackが、応答を**success→error、error→success、1xx／3xx、任意のbody・status**へ変更していても、**valid markerがあれば、markerのcanonical outcomeへ復元する**。**marker無し・不正ならE5へfail-closed**する。この復元は、応答の内容・statusにも、2xxであることにも依存しない。
   - **markerの性質と脅威モデル**：markerは**新しいdurable stateではなく、request-local**である。plugin内部にのみ保持し、filter・action・global・他pluginから読み書きできる経路を設けない。**暗号署名や新規の永続状態は設けない**。**偶発的な応答の改変・混入・取り違え（承認済みpluginやcallbackによる応答の書き換えを含む）への耐性が目的**であり、**co-resident malicious codeを脅威モデルへ追加しない**（5.2節は不変）。
   - **route callbackに到達しないGCA request**（12.4節 B-*）のうち、**投影eligibility（P-2）を満たし、投影に到達するもの**は、**markerが無い**ため、**推測でE1／E3等へ分類せず、E5へfail-closed**する（R-19）。投影eligibilityを満たさないものは、投影されない（B-*）。
   - **Finalizerは、state変更・snapshotの意味検証（DB照合・許可集合の判定）・DB保存・DB読取り（I/O）のいずれも行わない**。snapshotの4項目の検証、snapshotの保存、`CONFIRMED`への更新は、**すべてroute callback（plugin control path）が、marker設定の前に完了させる**（10.4節。順序と所有者の正本）。
   - **valid markerからのcanonical response選択・構築は、totalかつ一意（A9）**：**valid marker（確認(1)〜(4)を満たす）に対しては、`SUCCESS_FIRST`→canonical 5-field payload＋201、`SUCCESS_REPLAY`→canonical 5-field payload＋200、`E1`〜`E9`→canonical error表の該当行、という1つのcanonical responseが、失敗なく一意に選択・構築される**（入力はmarkerのみの純粋な関数で、DB I/Oも外部状態も参照しない）。**markerは、Finalizerの動作によって変更されない**（write-once。Finalizer failureによるmarker outcomeの遷移は存在しない）。
   - **marker不正の場合**：markerが欠落・不正・不一致・二重設定の場合は、**E5（503 `unknown`）**とし、statusとdataの両方を置換する（上記の確認(1)〜(4)の不成立）。**この場合にのみ、Finalizerは、marker以外の根拠でE5を出す**（E5は、markerを持たない固定のcanonical responseである）。
   - **Finalizerの適用runtime失敗の保証境界（Amendment A10。本項が唯一の正本であり、他の章・表・テスト・リスク・Roadmapは、ここを参照するのみで、この挙動を再定義しない。A6〜A8の「Finalizer failure→E9／confirmed」、およびA9の「`gca_claim_state`を欠く応答として扱う」という記述は、A10で廃止）**：
     - **定義**：valid markerからのcanonical response（またはE5）の選択・構築は成功しているが、それを**投影として返す（P-3）こと、または投影後のCore／serverによる送出（12.3節のX-*のうち、境界と定めたもの）が、runtime上失敗した場合**（投影用の`WP_REST_Response`を構築・返却できない、返却したresponseがstatus・headersとして送出されない、Finalizer内で例外が発生する、JSON encodeが失敗する（X-7）、等）。
     - **保証しないこと（すべて）**：適用失敗の後に**実際にclientへ送られるresponseの内容は未定義**である。**canonicalであること、non-canonicalであること、`gca_claim_state`を含む／含まないこと、pre-Finalizerの元のresponse（部分的に適用されたものを含む）が残ること**のいずれも保証しない。
     - **clientの扱い**：**clientは、そのresponseだけから、claim state・identityの消費有無・retry可否を判断してはならない**。
     - **E9へのfallbackを試みない**。**markerおよびdurable stateは、Finalizerの失敗によって変更しない**。
     - **適用失敗後のdurable stateは、marker outcomeごとに次のとおり**（各outcomeが示す状態であり、Finalizerの失敗では変わらない。後続のduplicate requestでの確認は、各行に記した範囲に限る。**全outcomeについて「`CONFIRMED`不変」「replay可能」とは言わない**）：

       | ID | marker outcome | 適用失敗後のdurable state | 後続のduplicate requestでの確認 |
       |---|---|---|---|
       | **F-1** | `SUCCESS_FIRST`／`SUCCESS_REPLAY` | **`CONFIRMED`**（durable。`SUCCESS_FIRST`はdurable ACK確認後、`SUCCESS_REPLAY`は`CONFIRMED` row読取り・Verification成功後にのみ設定されるため） | 後続のduplicateは、通常どおり`CONFIRMED`を観測し、Verificationが成功すればreplay（200） |
       | **F-2** | `E8` | **`CONFIRMED`だが、attachment欠落・不一致が確定**している状態 | 後続のduplicateは、**明示的な修復が完了するまで409 `confirmed_inconsistent`（E8）が維持される**（Binding・Verificationの環境が回復しただけでは、200 replayにならない） |
       | **F-3** | `E9` | **`CONFIRMED`だが、Verificationが未完遂**の状態 | 後続のduplicateは再度Verificationを試みる（成功すれば200 replay、attachment欠落・不一致が確定すればE8、未完遂のままならE9） |
       | **F-4** | `E7` | **`PROCESSING`**（自動回復しない） | 後続のduplicateは409 `processing` |
       | **F-5** | `E5`／`E6` | **不確定**（claimの有無・状態を確定できない。marker欠落・不正によるE5を含む。この場合、`CONFIRMED`が不変であるとは言えない） | 後続のrequestがrowを観測して確定する（row無し／`PROCESSING`／`CONFIRMED`のいずれか。row無しなら新規claimに勝てる） |
       | **F-6** | `E1`〜`E4` | **この requestが新しいclaimを作らなかった**、というだけの経路。**既存のclaimは、なし／`PROCESSING`／`CONFIRMED`のいずれもありうる**（過去のrequestのclaimの有無は、この outcomeからは分からない） | **既存のdurable stateが、適用失敗の前後で変化しない**。後続のrequestは、**その既存の状態に応じた通常の処理**になる（なし→新規claim、`PROCESSING`→409 `processing`、`CONFIRMED`→replayまたはE8／E9） |

     - **検証・記録（A12）**：T-07が、上記の表の**F-1〜F-6ごとに**検証する（検証の方法と層はT-07が定める）。**他の章・表・テスト・Roadmapは、本章の識別子（F-1〜F-6）で参照するのみで、表の内容（state・recovery・応答）を再記述しない**。**応答の内容についてはoracleを持たない**（canonical E1〜E9 oracle（T-22）の対象外）。
     - **前提と位置づけ**：「適用の能力」（返したresponse objectによるstatus・headersの確定、request instanceの同一性、直接送出headerの除去）は、**U-18・U-20として、実装開始前のValidation（18章）で確認する前提**とする。**A13までの前提（`rest_pre_echo_response`でのstatus置換）は、sourceで偽と判明し撤回した（V-11）**。確認できない場合は、本書を改訂する（実装時に束縛を緩めない）。前提が成立する環境での実行時の適用失敗は、**欠陥・障害**として扱う（R-20）。
   - **`gca_claim_state = confirmed`（E9）の根拠（A9）**：**E9は、plugin control pathが`E9` markerを明示的に設定する場合にのみ**返る（例：`CONFIRMED` duplicateでMedia Verificationが完遂不能、10.3節・C9）。Finalizerが独自にE9を選ぶことは無い。A7の「GCA-taggedの2xx応答はdurableなconfirmed successを意味する」という前提は**A8で廃止**済み（R-18を解消）。
   - **Finalizer（投影）の後にも改変点が存在する**（**「Coreがそれ以降JSON encode／echoのみ」「改変点ゼロ」という旧前提は、7.1.1 sourceで偽と判明し撤回**）。どれを禁止・検証・許容・保証外とするかは**12.3節（X-*）が正本**。approved plugin setの登録状況に依存する項目は、exact deployment versionで検証・bindする（18章。未確認、U-2）。

### 12.1 WordPress Coreの実行順序と、投影の位置（Amendment A14、正本）

**根拠**：WordPress **7.1.1 tag**の公開source（`class-wp-rest-server.php`等の行番号。V-11）。**規範の前提とするのは、本節が引用する7.1.1のcall-site（行）の事実だけ**である（他versionとの同一性は前提としない）。**デプロイ先のWordPress versionは未pin（U-11）であり、本節はsource上の事実であって、実環境（実行時）で検証したものではない**。**`status_header()`の本体は、canonical source（provenanceはV-16。commit `a940fbc1…`）の`functions.php:1463-1492`に存在する**（A18で訂正。call-siteは`set_status()`内の`:1910`。status line段階のfilterはX-11）。**ただしこれもsource上の事実であり、実行時（PHP／SAPI）は未検証**（U-20）。

| ID | Coreの処理（`serve_request`・`dispatch`・`respond_to_request`の順） | 本設計での位置づけ |
|---|---|---|
| **O-1** | `serve_request`冒頭：他のdispatch中なら`false`で終了（`:288-290`）。`rest_jsonp_enabled`・`_jsonp`の判定、transport header（`Content-Type`・`X-Robots-Tag`・`Link`・`X-Content-Type-Options`）の送出（`:316-337`）。`_jsonp`が無効・不正なら`rest_callback_disabled`／`rest_callback_invalid`（400）を出力して**終了**（`:360-370`） | **`rest_post_dispatch`に到達しない**（B-1） |
| **O-2** | `$request`を生成（`:376`）。以降、`dispatch`・各filterに**同じ変数**が渡る。`_method`／`X-HTTP-Method-Override`によるmethod変更（`:386-393`） | marker束縛の対象instance（P-5） |
| **O-3** | `check_authentication`（`rest_authentication_errors`、`:438-441`）。エラーなら`dispatch`しない | B-2 |
| **O-4** | `dispatch`：`rest_pre_dispatch`（`:1079`、非空で短絡）→ route・method照合（`:1096`、不一致は`rest_no_route`）→ handler呼出可否（`:1106`）→ **Core自身の引数検証・sanitize**（`has_valid_params`／`sanitize_params`、`:1115-1123`）。失敗は`$error`として`respond_to_request`へ渡る | B-3・B-4・B-5・B-6 |
| **O-5** | `respond_to_request`：`rest_request_before_callbacks`（`:1256`）→ **`permission_callback`**（`:1259-1260`。**それ以前にWP_Errorがあれば呼ばれない**）→ `rest_dispatch_request`（`:1287`、非nullで短絡）→ **route callback**（`:1293`）→ `rest_request_after_callbacks`（`:1318`） | **plugin control path＝route callbackだけ**。`permission_callback`はCore標準で、markerに関与しない（12.4節）。短絡・error時はroute callbackに到達しない（B-5〜B-9） |
| **O-6** | **`rest_post_dispatch`**（`:464`。top-levelのcall-site＝RD-1。**このhookの適用箇所は4つあり、他はRD-2〜RD-4**）。既定callback：`rest_send_allow_header`・`rest_filter_response_fields`（`rest-api.php:253-254`、priority 10）、および`_wp_connectors_rest_settings_dispatch`（`connectors.php:753`、priority 10。`/wp/v2/settings`のみに作用。**A18で追記**。V-16）。`rest_send_allow_header`は、responseのmatched route（`:1326`で設定）の全handlerの`permission_callback`を呼ぶ（`rest-api.php:883-916`）。**filterの戻り値（`WP_HTTP_Response`）が、以降のresponseとして使われる** | **本設計の投影位置（Finalizer）** |
| **O-7** | `_envelope`（`$_GET['_envelope']`）なら、responseをenvelopeで包む（`:467-470`、`envelope_response`は`body`／`status`／`headers`を持つ新responseを作る） | X-1 |
| **O-8** | **`send_headers($result->get_headers())`**（`:473-474`）と、**`set_status($code)`**（`:476-477`。`set_status()`は`status_header($code)`を呼ぶ。**`status_header()`の呼出は`:1910`、本体は`functions.php:1463-1492`で、status line文字列に作用する`status_header`filterを含む（`:1486`）**）：**HTTP statusとresponse objectのheadersの送出（確定）** | P-1。X-2・**X-11** |
| **O-9** | `rest_send_nocache_headers`（`:487`）、no-cache header（`:493-501`） | X-3（transport） |
| **O-10** | `rest_pre_serve_request`（`:516`。既定callback：`rest_send_cors_headers`・`_oembed_rest_pre_serve_request`）。`true`なら「配信済み」としてbodyを出力しない。`HEAD`はここで終了（`:519-521`） | X-4 |
| **O-11** | `response_to_data`（`:525`）：`_embed`の展開、**responseに`links`があれば`_links`をdataへ追加** | X-5 |
| **O-12** | **`rest_pre_echo_response`**（`:539`）。**引数は`response_to_data`後のdata「配列」であり、`WP_REST_Response`ではない。statusはO-8で送出済み** | X-6。**本設計はここにFinalizerを置かない** |
| **O-13** | `wp_json_encode`（`rest_json_encode_options`、`:266`・`:546`）。失敗時は`set_status(500)`＋`rest_encode_error`（`:550-559`）。`_jsonp`ならwrapして`echo`（`:562-565`） | X-7・X-8 |

- **P-1（投影の位置）**：応答の**status・data・response headersを確定する投影**は、**O-6（`rest_post_dispatch`）**で行う。理由：O-6のfilterは`WP_HTTP_Response`を受け取り、**返したobjectがO-8でstatus・headersとして送出される**（`:464`→`:473-477`。status送出の実体は`set_status()`経由の`status_header()`、`:1910`）。O-12（`rest_pre_echo_response`）はdata配列しか受け取らず、statusはO-8で送出済みのため、**status・response headersを確定する位置ではない**。A13までの「`rest_pre_echo_response`でstatusを置換する」方式は**撤回**した。
- **P-2（投影eligibility。A15で定義、A16で改訂）**：次の**すべて**を満たすrequestだけが、投影の対象（**eligible GCA POST**）である。**(PE-1)** `$request->get_route()`が`/wp/v2/media`に**完全一致**する。**(PE-2)** `X-GCA-`で始まるheaderを**1つ以上**持つ（8.2節）。**(PE-3)** **effective methodが`POST`**（判定の基準はMO-1）。**PE-1〜PE-3のいずれかを満たさないrequestには、Finalizerは作用しない**（Zero-Diff）。**top-level originの判定には依存しない**：A15の「`is_dispatching()`によるtop-levelの識別」は**廃止**した（`is_dispatching()`は、dispatch stackが空でないことしか示さず、top-level originやside-effect safetyの可否の証明にならないため。U-22は廃止）。投影の入力は、PE-1〜PE-3とmarkerだけである。
- **MO-1（method判定の基準。A17で定義）**：本pluginのwrapped CREATABLE callbackと投影（P-2）の対象になるか否かは、**effective method**（`$request->get_method()`。O-2の`_method`・`X-HTTP-Method-Override`によるmethod変更の**結果**を含む）だけで判定する。元のHTTP methodや、overrideの有無そのものでは判定しない。
- **MO-2（effective methodがPOSTでないrequest）**：effective methodがPOSTでないrequest（POSTがGET等へoverrideされた場合を含む。GET／HEAD／OPTIONS／PUT／PATCH／DELETE）は、**wrapped CREATABLE callbackにも投影にも入らず、Core Nativeのpath**（12.4節 B-4）として扱う。**claim・marker・canonical E1〜E9・wire closed-set（CS-1）を保証しない**。**side-effect create pathには入らない**（claim・Core `create_item`呼出は発生しない。SP-1）。
- **MO-3（effective POSTでoverride controlを伴うrequest）**：effective methodがPOSTで、wrapped CREATABLE callbackに到達したGCA-tagged requestに、`_method`（query parameter）または`X-HTTP-Method-Override`（header）が存在する場合は、**plugin allowlist violation（8.1節）としてE1**とする（route callbackが、claimより前に判定する。E1の内容は8.3節）。overrideの値がPOSTを指す場合も同じである。
- **MO-4（一般化の禁止）**：「method overrideを伴うrequestは常にE1」とは規定しない。overrideの結果がPOSTでないrequestはMO-2であり、E1にならない。MO-3のE1は、effective POSTでwrapped CREATABLE callbackに到達したrequestに限る。
- **CS-1（canonical保証の範囲。A15で定義、A16で改訂）**：**(a)投影の出力**：**eligible GCA POST（P-2）が`rest_post_dispatch`に到達し、P-3が成功した場合に限り**、Finalizerが返すresponseは、8.3節の応答表・canonical error表（E1〜E9）・exact key setに一致する。**(b)HTTP wire**：clientが受信するHTTP status・headers・bodyが(a)と一致するのは、そのresponseがO-6→O-8の主経路で、**そのrequestのHTTP応答として直接送出される場合**に限り、かつX-*の【保証外】【境界】を除く（本設計は、dispatchがtop-levelであることを**判定せず、証明もしない**。nested（`/batch/v1`の子request等）のresponseは外側のresponseの一部であり、wire保証外）。**(c)範囲外**で閉集合・exact keyを主張しない：投影の前に終了するrequest（B-1）、投影eligibilityを満たさないrequest（effective methodがPOSTでないrequest（MO-2・B-4）、RD-2・RD-4のstock request等）、投影が行われない文脈（内部`rest_do_request()`等、SP-3）、投影後のCore／serverの作用（X-1・X-8・X-9）、投影の適用runtime失敗（F-*）。範囲外でも、claim・Core呼出に関する安全性（SP-1）とF-*のdurable stateの境界は、それぞれの節に従う。
- **SP-1（side-effect safetyの帰属。A16で定義）**：**claim・`PROCESSING`・Core `create_item`呼出・`CONFIRMED`化のidempotency safetyは、route callbackだけが適用し、dispatchの文脈（top-level、内部`rest_do_request()`、`/batch/v1`の子request）に依存しない**。route callbackに到達したGCA POSTには、常に同じ安全性が適用される。`is_dispatching()`その他のdispatch文脈の判定を、claim・Core実行の可否に用いない。
- **SP-2（投影の帰属）**：`rest_post_dispatch`の投影は**HTTP応答の正準化専用**であり、side-effect safetyの条件ではない。
- **SP-3（投影が行われない文脈）**：**内部の`rest_do_request()`**（`dispatch()`を直接呼び、`rest_post_dispatch`を通らない。`rest-api.php:603-616`。**RD-4のpreloadは、`rest_do_request()`の後に`rest_post_dispatch`を明示的に適用する別のcall-site**）等、`rest_post_dispatch`に到達しないrequestでは、**canonical HTTP投影を保証しない**が、**SP-1のidempotency safetyは保証する**。route callbackの戻り値の内容は、投影が行われない文脈では保証外（canonicalでない）。
- **P-3（構築）**：Finalizerは、markerからcanonical response（`SUCCESS_FIRST`／`SUCCESS_REPLAY`／`E1`〜`E9`）を**新しい`WP_REST_Response`**として構築して**返す**。(a)dataはcanonical payload（exact 5 key）またはcanonical error body（exact 3 key・`data`は2 key）、(b)statusは固定値、(c)**response headersを持たせない**（H-1・H-3）、(d)**linksを持たせない**（O-11で`_links`が追加されず、key setがexactになる）。**返す値は`WP_HTTP_Response`でなければならない**（O-8が`get_headers()`・`get_status()`を呼ぶ）。受け取った`$result`は変更・再利用しない。O-6の既定callback（`rest_send_allow_header`・`rest_filter_response_fields`・`_wp_connectors_rest_settings_dispatch`）は、投影の前に旧responseへ作用するだけで、投影後のresponseには作用しない。
- **P-4（priority）**：Finalizerは`rest_post_dispatch`の**最大priority**で登録する。同hookで、Finalizerより**後に実行され、応答を変更しうる**callback（同priorityで後に登録されたもの、またはより大きいpriorityのもの）が存在しないことを、Epoch topology（5.3節#5）とapproved plugin set（U-10）で検証する。**この検証は、同一hookであるため、全call-site（RD-1〜RD-4）に共通**（A18）。
- **P-5（instance束縛）**：O-6の**第3引数**`$request`が、O-2で生成されcontrol pathへ渡されたrequestと**同一instance**であること。source上、通常の単発requestでは同一変数が`:376`→`:441`→`:464`と渡る。cloneは`/batch/v1`の`rest_pre_dispatch`用（`:1860`）のみ。**他のcall-site（RD-2〜RD-4）の同一変数の経路はRD-*の表**（A18）。**実行時の成立は未検証**（U-18）。
- **成立しない場合**：U-18・U-20が実環境で成立しない場合は、**別方式を実装時に選ばず**、本書を改訂する（Architecture Review＋Human Gate）。

**`rest_post_dispatch`の全call-site（RD-1〜RD-4。Amendment A18、正本）**：7.1.1における`rest_post_dispatch`の**適用箇所は次の4つ**であり、**同一のhook・同一のFinalizer（P-4）が4箇所すべてで呼ばれる**（Coreの既定登録は、`rest-api.php:253-254`の2つと、`connectors.php:753`の1つ（`_wp_connectors_rest_settings_dispatch`。routeが`/wp/v2/settings`のrequestにだけ作用し、それ以外は何もしない。`connectors.php:698-700`）。4箇所以外にないことの確認はV-16）。**行番号はcanonical sourceのもの**（provenanceはV-16）。

| ID | call-site | requestの構築・method・instance | 呼出条件 | eligibility・投影・保証 |
|---|---|---|---|---|
| **RD-1** | `class-wp-rest-server.php:464`（`serve_request`。top-level。O-6） | `$request`は`:376`で生成。methodは`REQUEST_METHOD`。**`_method`（`$_GET`）・`X-HTTP-Method-Override`のoverrideを解釈するのは`serve_request()`だけ**（`:386-395`）。`:376`→`:441`→`:464`で同一変数（P-5） | top-levelのHTTP request（B-1の早期終了を除く） | **本章の既存のcontractどおり**（P-2・P-3・CS-1・MO-*・B-*）。投影の対象はeligible GCA POSTのみ |
| **RD-2** | `class-wp-rest-server.php:824`（`embed_links`内） | `WP_REST_Request::from_url($item['href'])`（`:803`）。**構築methodは常に`GET`**（`class-wp-rest-request.php:1083`）。**`rest_request_from_url`filter（同`:1096`）が返す値が、falsy以外ならそのままrequestとして使われる**（server`:804`）。`context=embed`が付く（`:809-812`）。`$this->dispatch($request)`（`:821`）→`:824`で同一変数 | `_embed`が有効で、responseの`links`に`embeddable`なitemがあるとき（`response_to_data`、`:598-606`）のみ。**当該responseの一部（`_embedded`）になり、独立したHTTP応答ではない** | stockではPE-3を満たさない（MO-2）→**RD-5のno-op**。embeddedのresponseはnestedで、CS-1(b)の保証外。GCA POSTは`_embed`をallowlistで拒否し（8.1節）、投影後のresponseはlinksを持たない（P-3、X-5）ため、GCA responseからのembedは生じない。`rest_request_from_url`のcallbackがroute・header・method・型を変えうる点は**RD-6** |
| **RD-3** | `class-wp-rest-server.php:1894`（`serve_batch_request_v1`） | `$single_request`は`:1753`で生成。methodは`$args['method'] ?? 'POST'`。**batch子ではoverrideを解釈しない**。`rest_pre_dispatch`にはcloneを渡す（`:1860-1866`）が、`respond_to_request`（`:1889`）と`:1894`には**同一の`$single_request`** | `/batch/v1`の子request（`allow_batch`検証の失敗も、`$error`として`respond_to_request`を経て`:1894`に至る） | **BT-1〜BT-4に従う**。子responseは外側の207の一部で、CS-1(b)の保証外。route callbackに到達する構成はBT-3によりEpoch invalid。到達した場合もSP-1 |
| **RD-4** | `rest-api.php:3033`（`rest_preload_api_request`） | `new WP_REST_Request($method, …)`（`:3023`）。**methodは`GET`または`OPTIONS`のみ**（`:2994-3002`）。`rest_do_request($request)`（`:3029`。`rest_post_dispatch`を通らない。SP-3）の後に、**`200 === $response->status`のときだけ**`rest_post_dispatch`を明示的に適用（`:3030-3033`）。`:3023`→`:3029`→`:3033`で同一変数 | ページへのREST preload（管理画面等）の内部request | PE-3を満たさない（MO-2）→**RD-5のno-op**。CS-1の範囲外。claim・Core `create_item`呼出は発生しない（GET／OPTIONSのCore Native） |

- **RD-5（全call-site共通のFinalizerの安全なno-op。A18）**：`rest_post_dispatch`は**globalなfilter**であり、**RD-2・RD-4でもFinalizerは呼ばれる**。これらを「存在しない経路」としては扱わない。Finalizerは、**最初に**eligibility（P-2のPE-1〜PE-3）だけを判定し、**満たさなければ、受け取った`$result`をそのまま返す**（変更・再利用・marker参照・DB I/Oのいずれも行わない。Zero-Diff）。**第3引数が`WP_REST_Request`のinstanceでない場合も、eligibleでないものとして同様に何もしない**（`rest_request_from_url`filterは任意の値を返しうるため）。eligibleと判定された場合は、call-siteを問わず、markerの確認（P-3・P-5、12.4節の「marker無し→E5」）に進む。**eligibilityは、filter呼出時点のrequestの状態に対して判定する**。
- **RD-6（request-affecting hookのtopology検証。A18）**：approved plugin set・Epoch topology（5.3節#4・#5）で、次を検証対象にする：`rest_request_from_url`（RD-2のrequestのroute・header・method・型を変えうる）、既存の`rest_pre_dispatch`・`rest_request_before_callbacks`・`rest_dispatch_request`、および各call-siteで、dispatch中にrequest objectを変更しうるcallback（requestは同一instanceで渡る）。**登録の有無・priority・callbackを確認し、GCA対象でないrequestをeligibleな形（PE-1〜PE-3）へ変えうるcallbackが存在する構成、および確認不能の構成は、unsupported topologyとしてEpoch invalid（production enable禁止）**とする（fail-closed）。conditional callbackは静的に検出できない可能性がある（5.3節の既知の限界、T-14と同じ）。**実行時の実際の挙動はruntime-only**（U-2・U-18）。
- **RD-7（call-siteの網羅）**：RD-1〜RD-4以外の適用箇所が7.1.1にないことはV-16。**他versionでの同一性は前提としない**。**新しいcall-siteが現れた場合（version差・plugin）は、本書を改訂する**（実装時にFinalizerの条件を変えない）。

### 12.2 Response header契約（A14）

投影後に**clientが受信するresponse header**は、次の3区分に分ける。区分の判断は、**そのheaderを誰がどの時点で送出するか**による。

| ID | 区分 | 契約 |
|---|---|---|
| **H-1** | **Core media responseに由来するheader**：(a)`WP_REST_Response`のheadersとして保持されるもの（例：`Location`。`create_item`が付与、`attachments-controller:637`）、(b)Coreが`create_item`の**実行中に`header()`で直接送出**するもの（7.1.1では`X-WP-Upload-Attachment-ID`、`:619`。`wp_is_serving_rest_request()`のときのみ） | **最終responseに含めない（禁止）**。(a)は、投影が**headersを持たない新しい`WP_REST_Response`**を返すこと（P-3）で除去される。(b)は**response objectに載らず、投影の置換では除去されない**ため、**Finalizerが、直接送出されたheaderを除去する**（`header_remove`相当）。除去の対象は、**route callbackがCore呼出の前後で`headers_list()`の差分を記録し、Coreの実行中に追加された直接送出header名**とする（既知の該当は`X-WP-Upload-Attachment-ID`のみ）。**全outcomeに適用**する（`SUCCESS_FIRST`も含む。canonical payloadの`id`と別経路でattachment IDを運ばせない）。成立の前提は**U-20**（実行時の除去可否は未検証） |
| **H-2** | **transport／server／CORS／no-cache header**：Core／serverが、応答の内容とは別に送出するもの（`Content-Type`・`X-Robots-Tag`・`Link`（API root）・`X-Content-Type-Options`（O-1）、no-cache（O-9）、`Access-Control-*`・`Vary`（O-10の`rest_send_cors_headers`）、web server・proxy由来のheader） | **本契約の対象外**：pluginは**追加・除去・存在の保証をしない**。ただし、**attachment ID・claim・outcomeの情報を運ばない**こと（approved plugin setのhook登録で検証、P-4・X-4・U-10）。`Allow`（`rest_send_allow_header`）は、O-6でresponse objectへ付くため、**投影で置換され存在しない**（保証対象外） |
| **H-3** | **本pluginが付与するresponse header** | **v1では付与しない（空集合）**。outcomeは**bodyだけ**で表す |

- **header契約の検証**：T-35。
- **現行Python clientとの互換**：現行Uploaderはbodyの`id`／`source_url`／`mime_type`のみをparseし（V-1・V-10）、headerを参照しない。

### 12.3 投影後の改変点と、その扱い（Amendment A14、正本）

投影（O-6）の**後**にも、応答に作用する点が存在する。区分：**【禁止】**＝requestの段階で拒否（8.1節allowlist、E1・claim前）またはEpoch invalid。**【検証】**＝approved plugin set・Epoch topology・Validation（18章）・L3で確認（未検証の前提を含む）。**【許容】**＝transportであり、outcomeの意味を変えない。**【境界】**＝12章 F-*の保証境界に従う。**【保証外】**＝canonical shape・statusを保証しない（ただしclaim・Core呼出を伴わないことは別に示す）。

| ID | 改変・作用点（O-*） | 区分 | 契約 |
|---|---|---|---|
| **X-1** | `_envelope`（O-7）、および`envelope_response()`内の**`rest_envelope_response`filter**（`:861-885`、filter適用は`:882`。投影の後に、envelope化された値を変更しうる） | 【禁止】＋【検証】＋【保証外】 | 8.1節のallowlist（query parameter空集合）でE1・`none`・**claim前**に拒否する。ただし、**Coreが投影後の応答をenvelopeで包む**ため、当該requestの最終bodyはcanonicalでない（保証外、CS-1(b)）。**`rest_envelope_response`はenvelope経路でのみ作用し**、approved plugin setに、GCA対象でこのfilterを登録するcallbackが存在しないことをtopologyで検証する（`_envelope`を伴わないrequestには作用しない）。**claim・Core呼出は無い**。**canonical 5-field payload（`gca_claim_state="confirmed"`を含む）を持たない2xx応答を、Integration Releaseは成功として扱ってはならない**（23章はこの規則を参照するのみ） |
| **X-2** | status・response object headersの送出（O-8） | 【許容】 | 投影objectのstatus・headers（空、H-1・H-3）が送出される（P-1。**status lineの文字列は、この中でX-11のfilterを経る**）。ここが**保証の確定点**（numericなstatus codeについて） |
| **X-3** | no-cache header（O-9）・CORS／transport header（O-1・O-10） | 【許容】 | H-2。outcomeの意味を変えない |
| **X-4** | `rest_pre_serve_request`（O-10） | 【検証】 | **approved plugin setに、GCA対象で`true`を返す（bodyの配信を代替する）callbackが存在しない**こと（12章 要件2）。Core既定の`rest_send_cors_headers`は【許容】（H-2）。`_oembed_rest_pre_serve_request`は**route `/oembed/1.0/embed`かつGET**にのみ作用する（`embed.php`、7.1.1）ため、対象（`/wp/v2/media`）には作用しない。HEADはbodyを出力しない（【保証外】、非POST） |
| **X-5** | `response_to_data`・`_embed`・`_links`の追加（O-11） | 【禁止】＋構造 | `_embed`はallowlistでE1。**投影objectがlinksを持たない**ため、`_links`は追加されず、key setはexactのまま（P-3） |
| **X-6** | `rest_pre_echo_response`（O-12） | 【検証】 | **approved plugin setに、GCA対象のdata配列を変更するcallbackが存在しない**こと。**本pluginは、このhookにFinalizerを置かない**。このhookはstatus・response headersを変更できない（O-8で送出済み）。data改変の有無は、topology検証とT-35・T-38（承認済みset上のL3）で確認する |
| **X-7** | JSON encode（`rest_json_encode_options`、O-13）・encode失敗 | 【検証】＋【境界】 | `rest_json_encode_options`にGCA対象へ作用するcallbackが存在しないこと（topology）。**`_pretty`等のquery parameterはallowlistで禁止**（空白のみ変更しうるが、claim前に拒否）。**encode失敗（`:550-559`、`set_status(500)`＋`rest_encode_error`）は、12章 F-*の「適用runtime失敗」に含める【境界】**（応答の内容は未定義、marker・durable stateは不変） |
| **X-8** | JSONP（`_jsonp`・`rest_jsonp_enabled`、O-1・O-13） | 【禁止】＋【保証外】 | `_jsonp`はallowlistでE1・claim前に拒否。ただしCoreがJSONP wrapで包むため、最終bodyはcanonicalでない（保証外、X-1と同様）。`_jsonp`が無効・不正な場合はO-1で**早期終了**（B-1） |
| **X-9** | HEAD（O-10）・204（`:542`） | 【保証外】 | HEADは投影対象外（PE-3）で、bodyを出力しない。204は、投影が204を構築しないため該当しない |
| **X-10** | PHPのfatal・`exit`・出力バッファ・接続断・web serverの打切り | 【境界】 | 応答を返せない場合は10.6節 C4・C11（transport error）。投影の後に起きた場合は、12章 F-*の境界 |
| **X-11**（A18） | **`status_header`filter**（`functions.php:1486`）。O-8の`set_status($code)`（`:477`）→`status_header($code)`（`:1910`→`functions.php:1463-1492`）の**中で、status line文字列に作用する**。流れ：`get_status_header_desc($code)`（`:1373-1449`、`global $wp_header_to_desc`。8.3節のcanonical status（200／201／400／403／409／413／503）はすべて記述を持つ）→`wp_get_server_protocol()`（`load.php:15`）→`$status_header = "$protocol $code $description"`（`:1473`）→**`apply_filters('status_header', $status_header, $code, $description, $protocol)`（`:1486`）**→`!headers_sent()`なら`header($status_header, true, $code)`（`:1489-1490`）。記述が空なら何も送出せず返る（`:1468-1470`） | 【検証】＋【保証外】＋【境界】 | **numericなstatus codeとstatus line文字列を区別する**：投影が確定するのは**numericなstatus code**（P-3(b)。`$result->get_status()`、`:476`）で、これは`header()`の**第3引数**として別に渡される（`:1490`）。filterが変えうるのは**status line文字列**（`$status_header`）である。このfilterは**requestもresponseも受け取らない**global filterで、GCA対象だけに限定できない。**approved plugin setに、`status_header`filterを登録するcallbackが存在しない**（7.1.1の`src/`には、Core既定の登録はない。V-16）ことを、登録の有無・priority・callbackとして検証する（RD-6と同じtopology検証）。**登録のあるplugin、および確認不能の構成は、unsupported topologyとしてEpoch invalid（5.3節#5、production enable禁止）**とする（fail-closed）。本pluginは、status lineの書換えを検出も補正もしない。実行時にstatus lineが書き換わった場合、**wire上のstatus line文字列は保証外**（canonicalなnumeric statusが実際に反映されるかは、`header()`の第3引数・PHP／SAPIの挙動に依存し、**runtime-only**＝U-20）。`headers_sent()`が真の場合はstatusが送出されない（X-10の【境界】）。**source上の確認だけで、runtimeの成立とはしない** |

- **approved plugin／hook topologyとの関係**：X-1（`rest_envelope_response`）・X-4・X-6・X-7・**X-11（`status_header`）**、P-4、**RD-6（`rest_request_from_url`等）**は、**approved plugin set（U-10）のhook登録状況に依存**する。co-resident pluginは敵対的主体としない（5.2節）。登録callbackの静的照合は、conditional callbackを検出できない（5.3節の既知の限界、T-14）。したがって、**最終的な実HTTP status・headers・bodyは、承認済みset上でL3（T-35・T-38）で確認する**（未検証）。
- **投影より前の改変**（O-5の`rest_request_after_callbacks`等、およびO-6の既定callback）は、**valid markerからの新規構築で打ち消される**（上記4。T-34(d)）。

### 12.4 plugin control pathの網羅範囲（Amendment A14・A15・A16、正本）

**control path（markerを確定する主体）は、本pluginが置換したroute callbackだけ**である（A16。A15までの「ラップした`permission_callback`」は廃止）。**`permission_callback`は置換せず、Coreのまま**（Coreの権限判定が、認証・Core標準の権限を評価する）。**`permission_callback`は純粋な判定であり、markerの作成・変更・phaseの管理を一切行わない**。したがって、`rest_send_allow_header`（O-6）等によるpermission_callbackの呼出回数・契機は、markerに影響しない。**A15のPP-1〜PP-6（permission phase）は廃止**した（Review #23 B-01：filter chainの途中の値と最終値の差、例外時のdisarm漏れ等、callbackの実行順序に依存する識別は、他pluginの登録状況で崩れるため）。

**GCA capability判定（7.3節）の位置（A16）**：route callbackの**先頭**（claim・Core呼出より前）で行い、不足は**E3**（403・`none`）のmarkerを確定する（claim 0・Core 0）。**E3は、Coreの`permission_callback`を通過したrequest（認証済みでCore標準の権限を持つ）が、GCA capabilityだけを欠く場合にのみ到達しうる**。Coreの`permission_callback`が拒否するrequestは、route callbackに到達せず（B-9）、E3にならない。

7.1.1 sourceでは、route callbackは**GCA requestの全経路から到達されるわけではない**（V-13）。次の経路は、**route callbackに到達せず、plugin自身がmarkerを確定できない**。

| ID | route callbackに到達しない経路 | source（7.1.1） | 投影（eligible GCA POST＝P-2のPE-1〜PE-3のときのみ） |
|---|---|---|---|
| **B-1** | `serve_request`の早期終了（`_jsonp`が無効・不正、他のdispatch中） | `:288-290`・`:360-370` | **`rest_post_dispatch`に到達しない**（応答はCore自身のもの） |
| **B-2** | `check_authentication`のエラー（認証失敗等） | `:438-441` | 到達する。eligibleならmarker無し→E5 |
| **B-3** | `rest_pre_dispatch`による短絡（他plugin、およびCore既定の`rest_handle_options_request`によるOPTIONS） | `:1079-1093` | 到達する。eligibleならmarker無し→E5（OPTIONSはPE-3を満たさず投影対象外） |
| **B-4** | **effective methodがPOSTでない**（MO-1・MO-2）：(a)handlerが無いmethod（PUT／PATCH／DELETE等）→`rest_no_route`、(b)**GET／HEAD**（HEADはGET handlerへfallback）、およびPOSTが`_method`・`X-HTTP-Method-Override`でGETへoverrideされた場合 → **`/wp/v2/media`のREADABLE handler（Core標準の読取りcallback）が実行される**。route`/wp/v2/media`はREADABLEとCREATABLEの両handlerを持つ。**effective POSTのままwrapped CREATABLE callbackに到達するoverride付きrequestはB-4ではなく、MO-3** | `:386-394`・`:1096-1102`・`:1153-1223`、`posts-controller:73-93` | **PE-3を満たさず、投影対象外**（MO-2。Core Native path） |
| **B-5** | handlerが呼出不能（`rest_invalid_handler`） | `:1106-1112` | 到達する。eligibleならmarker無し→E5 |
| **B-6** | **Core自身の引数検証・sanitizeの失敗**（routeの`args`に対する`has_valid_params`／`sanitize_params`）。`$error`が`respond_to_request`へ渡され、`permission_callback`も route callbackも呼ばれない | `:1115-1123`・`:1259` | 到達する。eligibleならmarker無し→E5（**plugin自身のallowlistのE1には到達しない**） |
| **B-7** | `rest_request_before_callbacks`が`WP_Error`を返す | `:1256-1259` | 到達する。eligibleならmarker無し→E5 |
| **B-8** | `rest_dispatch_request`が非nullを返す（route callbackは実行されない） | `:1287-1291` | 到達する。eligibleならmarker無し→E5 |
| **B-9** | **Coreの`permission_callback`が拒否**（未認証、Core標準の権限不足。`rest_forbidden`） | `:1259-1270` | 到達する。eligibleならmarker無し→E5（**E3ではない**） |

- **契約**：eligible GCA POSTがB-2・B-3・B-5〜B-9で投影に到達した場合は、**markerが無く、E5（503 `unknown`）へfail-closed**する。**plugin自身がauthoritative markerを確定できなかった経路を、推測でE1／E3等のcanonical errorへ分類しない**。B-1・B-4・B-3のOPTIONSは、投影の対象外である。
- **claim・Core呼出との関係**：claimの生成とCore呼出は**route callbackだけ**が行う（10.2節、SP-1）。B-1〜B-9ではroute callbackが実行されないため、**当該requestはclaimを確立せず、Coreの`create_item`も呼んでいない**。ただしE5は`unknown`であり、**identity未消費・再送許可を意味しない**（8.3節 原則(1)・(2)）。
- **帰結（R-19）**：認証失敗（B-2）、Core権限の拒否（B-9）、Coreの引数検証の失敗（B-6）は、Core Nativeの401／403／400ではなく**E5**になる。Core `args`は6.38では**変更しない**。**E1になるのは、route callbackに到達した後のallowlist・validation違反に限る**。
- **検証**：U-19、T-36。

### 12.5 `/batch/v1`と内部dispatchの扱い（Amendment A14・A15・A16、正本）

- **BT-1（保証の分離。A16で改訂）**：**idempotency safety（SP-1）は、route callbackに到達したGCA POSTのすべてに適用する**（dispatch文脈を問わない）。**canonical HTTP投影の保証（CS-1）は、そのresponseが直接HTTP応答として送出される場合に限る**。`/batch/v1`の子request、内部`rest_do_request()`等のnested／非投影の文脈は、**HTTP投影の保証対象外**（SP-3）。**dispatch文脈の判定（`is_dispatching()`等）は、claim・Core実行の可否にも投影の可否にも用いない**。
- **BT-2（Core上の可否）**：7.1.1では、`WP_REST_Attachments_Controller`が`protected $allow_batch = false;`（`attachments-controller:35`）とし、親の`WP_REST_Posts_Controller`の既定`array('v1' => true)`（`posts-controller:48`）を上書きする。`serve_batch_request_v1`は`allow_batch['v1']`が真でないrouteを`rest_batch_not_allowed`（400）で拒否する（`:1795-1808`）。したがって、**Core登録のままの`POST /wp/v2/media`は、batchでdispatchされない**（source上の事実。実行時は未検証、U-21）。
- **BT-3（置換時の維持）**：本pluginは、route callbackを置換する際に、**`allow_batch`を設定・変更しない（Coreの値＝偽を維持）**。handler fingerprint（5.3節#3）は`allow_batch`が偽であることを含み、変化した場合はEpoch invalid（claim前に拒否、T-09）。
- **BT-4（子request・内部dispatchの扱い。A16で改訂）**：(a)**batchの子request**は、`allow_batch`検証が失敗した場合も`respond_to_request`を経て`rest_post_dispatch`（`:1889-1894`）を通り、P-2のPE-1〜PE-3を満たせば投影されうる。**ただしそのresponseは外側のresponse（207）の一部であり、HTTP wire保証外**（CS-1(b)）。子requestがroute callbackに到達しうるのは`allow_batch`が有効化された構成のみで、BT-3によりEpoch invalid（claim前に拒否）。到達した場合も**SP-1が適用される**（call-site分類はRD-3）。(b)**内部`rest_do_request()`**：SP-3。
- **検証**：U-21、T-37。

---

## 13. Ingress Kill Switch / Single-Ingress運用

### 13.1 Planned Break（計画的メンテナンス）

1. ingress blockingを発動する 2. 既存keep-alive接続・queued requestをdrainする 3. PHP側でGCA-taggedのin-flight処理がゼロであることを確認する 4. maintenanceモードへ移行する

### 13.2 Unplanned Break

- Epoch latchの即時無効化（reactive disable）だけでは既にfork済みのPHP-FPM workerを止められないため、これのみに依拠しない。ingress自体をblockし、in-flight workerの自然終了・queue drainを経て安全にproduction disableへ至る明示的なquiesce手順を要する。

### 13.3 Ingress Epoch Revocation

- header-only・URL非依存のblockingと、generationベースの「各nodeがacknowledgeしたことを確認するbarrier」を組み合わせたprotocol。v1はsingle authoritative ingressのみのため、multi-node membership raceはtopology自体の除外により発生しない。

---

## 14. Zero-Diff（非GCAリクエスト）

- GCA-taggedでないリクエストについては、本pluginのwrapperがCore Native実装とrequest/response双方でbehaviorally equivalentであることを要件とする。
- Finalizer・kill switch等の機構はGCA-taggedリクエストにのみ作用する。
- **6.38時点で本番投入されるGCA-taggedトラフィックは存在しない**（Python側が送出しないため）。したがって6.38のZero-Diffは、plugin未deploy（Out of Scope）かつPython側無改修の二重の意味で成立する。
- Python側（`src/`・`main.py`・`scripts/`）は6.38で一切変更しない。

---

## 15. テスト設計（Amendment A1で全面改訂）

### 15.1 責務の3層分離（ローカル環境前提）

**ローカル環境には PHP／MySQL／WordPress stagingが存在しない**（Amendment A1時点で`php`コマンド・`wordpress/`ディレクトリの不在を確認済み）。このため、検証責務を次の3層に分離し、各層で**何が証明でき何が証明できないか**を明記する。

| 層 | 実行場所 | 証明できること | 証明できないこと |
|---|---|---|---|
| **L1 Static／Contract** | 本repoのローカル環境（Python E2E形式、既存のFormal Regression慣習に従う） | key導出のgolden vector（Python参照実装）、禁止入力（`attempt_ordinal`・`root_run_id`・image bytes）がkey導出ソースに現れないこと、`DELETE`／`PROCESSING→CONFIRMED`以外の`UPDATE`がplugin sourceに存在しないこと、replay分岐から`create_item`呼出が構造上到達しないこと、wire contractの定数・closed allowlistの存在、設計書の契約整合 | PHPの実行時挙動、DBの並行性・durability |
| **L2 Unit（PHP）** | PHP＋PHPUnit（および`$wpdb`／Claims storeのin-memory fake）が使える環境（**ローカルには現状なし**。人手または別環境） | 状態機械の遷移、duplicate分岐、error→HTTP写像、Finalizer失敗時の挙動、fault injection（fakeでのACK曖昧・DB例外）、Core `create_item`呼出回数の計数 | 実MySQLの`INSERT`競合・isolation・durability、実WordPress Coreとの結合 |
| **L3 Staging fault matrix** | 実WordPress＋実MySQL staging（人手実施、証跡を記録） | 実DBでの`INSERT`競合、並行duplicate、PHP kill／timeout、実Coreとの結合、no-duplicate-attachment invariantのDB上での確認、非GCAのZero-Diff | 本番環境での挙動（本番投入はOut of Scope） |

- **6.38のCompletionは、L2およびL3のevidenceが（人手環境で）得られるまで主張しない**。L1のみがPASSした状態は「Foundation設計・静的契約が成立」にとどまり、完了ではない（20章）。
- L1にPythonで追加するE2Eは`tests/`配下の新規ファイルとなるため、`tests/zero_diff_guard_registry.py`への自己登録（`RELEASE_ORDER`への`"v6.38.0"`追記と`_TEST_CHANGE_CONTRIBUTIONS`登録、`[KI]`の教訓）を実装フェーズの作業に含める（17章 V-6、26章）。

### 15.2 必須テストシナリオ

| ID | シナリオ | 層 | 期待結果（要旨） |
|---|---|---|---|
| T-01 | **first request**（GCA-tagged、row無し） | L2, L3 | claim `INSERT`が勝者→Core 1回→検証→`CONFIRMED`→201。attachment 1件、`post_name == requested_slug` |
| T-02 | **CONFIRMED replay** | L2, L3 | duplicateは`create_item`を呼ばず200＋同一`id`／`source_url`／`mime_type`／`slug`。attachment増加なし |
| T-03 | **concurrent duplicate**（同時N request、同一logical identity） | L3（L2はfake競合） | 勝者は高々1。敗者は409または（勝者CONFIRMED後なら）replay。Core呼出総数≦1、attachment≦1 |
| T-04 | **PROCESSING duplicate** | L2, L3 | 409 `gca_idempotency_in_progress`。Core呼出0、attachment増加なし。待機・自動promoteなし |
| T-05 | **crash before side effect**（claim確立後・Core前）：(a)PHP異常終了（C1b）、(b)捕捉可能な内部障害の注入（C1a、T-28） | L2（fault）, L3（PHP kill） | `PROCESSING`が残りmediaなし。(a)は応答なし、(b)は409 `processing`。duplicateは409。自動reclaimされない |
| T-06 | **crash/timeout after side effect before CONFIRMED** | L2（fault）, L3 | `PROCESSING`＋mediaあり。duplicateは409。自動promote・新規作成なし |
| T-07 | **Finalizerの適用runtime failureの検証（F-*ごと）**。**契約の内容は、12章のF-1〜F-6が唯一の正本であり、本行は再掲しない。本行が定めるのは、検証の手順と層のみ**。**手順（12章のF-1〜F-6の各行について）**：(1)当該F-*が対象とするmarker outcomeに必要な**事前状態**を用意する。**F-6（E1〜E4）では、既存claimを、なし／`PROCESSING`／`CONFIRMED`の3通りに分けて用意する**。(2)Finalizerの**適用runtime failureを注入**する（注入する失敗の種類は、12章の「適用runtime失敗」の定義による）。(3)**観測結果が、当該F-*の記述と一致する**ことを検証する。**別に**：marker欠落・不正等の注入はT-34(c)、valid markerからの選択・構築が総和かつ一意であること（12章）の確認はL1／L2で行う | 下記の**層分離（T-07固有の責務）**のとおり | **oracleは、12章のF-*との一致のみ**。**応答の内容についてはoracleを持たない**（T-22の対象外）。**層分離（T-07固有の責務）**：**【L1／L2】** request-local・非公開のmarker内部状態（適用失敗の前後での不変・write-once・Finalizerがmarkerを変更しないこと）。**【L3】** durable DB state、および後続のrequestの挙動のみ。**L3から、非公開のprivate markerを直接観測することは前提にしない（禁止）** |
| T-08 | **DB unavailable**（claim時／Verification時／`UPDATE`時） | L2（fault）, L3 | `INSERT`発行前：Core 0・503 `none`。`INSERT` ACK曖昧：Core 0・503 `unknown`（C6a）。Core後のVerification失敗／`UPDATE`確定失敗：`PROCESSING`のまま409 `processing`（C7）。`UPDATE` ACK曖昧：503 `unknown`（C8）。いずれも再`INSERT`しない |
| T-09 | **detectable epoch mismatch**（**server内部の**schema version（claims schema version）／anchor不一致／`server_uuid`不一致／durability**設定値**の前提不一致／topology drift。Binding・multisiteはT-23・T-24、durabilityの**実証**はT-25） | L2, L3 | **claim確立前に検出**した場合は、claim・replayとも行わず503 `none`。row・mediaを作らない。（claim確立後に検出した場合は`PROCESSING`保持・409 `processing`、T-23b／T-23c） |
| T-10 | **regenerated／different image bytes with same logical key** | L2, L3 | `CONFIRMED`なら既存mediaをreplay（再生成・再upload要求なし）。`PROCESSING`なら409。診断digest差異は結果に影響しない |
| T-11 | **different content revision**（同一article・role、別`content_revision`） | L2, L3 | 別logical identityとして新規claim・新規media。旧revisionのclaim/mediaは不変 |
| T-12 | **no duplicate attachment invariant** | L2（計数）, L3（DB照会） | 全シナリオを通じ、各`idempotency_key`について Core `create_item`呼出≦1 かつ `post_name == requested_slug`のattachment≦1 |
| T-13 | 旧Draftの継続項目：Media Verificationの`READ UNCOMMITTED`下dirty read fault注入／Core側rollback後に`CONFIRMED`が残存しない | L2（fault）, L3 | 9.1節の接続契約により拒否／`PROCESSING`のまま |
| T-14 | conditional short-circuit構成（常時登録・条件付き発火）をEpoch invalidと判定できるか | L3 | 5.3節の既知限界の確認（検出不能ならその旨を記録） |
| T-15 | `rest_after_insert_attachment`の0回／複数回発火、5-way ID mismatch注入 | L2, L3 | CONFIRM失敗（`PROCESSING`のまま） |
| T-16 | post-callback改変（`rest_request_after_callbacks`、および`rest_post_dispatch`でFinalizerより前に実行されるfilter）による、**応答dataの改変（ID含む）と、HTTP statusの改変（例：201→200、200→201、2xx→他）の両方**、manual serving試行（Finalizerより後の作用点は12.3節 X-*、T-38） | L3 | **oracleは12.1節 P-1・P-3・CS-1、12.3節 X-4、11.2節の5-way ID equality（client-visible ID＝snapshot ID）のみ**（復元の規則・期待されるresponseの内容は12章が正本であり、本行は再記述しない）。実際に受信するHTTP status・headersの確認はT-35 |
| T-17（A17で改訂） | `url`／allowlist外のquery parameter・body形式・`Content-Type`・未定義の`X-GCA-*`（8.1節の表の各行）。**method override control（8.1節の該当行）は、次の2つの入力に分けて検証する**：**(a)** effective POSTのまま、`_method`または`X-HTTP-Method-Override`を伴うGCA-tagged request、**(b)** override後のeffective methodがPOSTでないrequest（POST→GET等） | L1（allowlist定数が8.1節の表と一致することの検査。method override controlの行を含む）, L2, L3 | oracleは**8.1節・8.3節の該当contract**（E1の内容は8.3節）のみ。**(a)は12.1節 MO-3、(b)は12.1節 MO-2・12.4節 B-4・12.1節 CS-1**に従う（本行は期待結果を再記述しない）。`create_item_from_url()`到達0（8.1節）。Coreの引数検証が先に失敗する入力は12.4節 B-6（E1とB-6の分岐はT-36で確認）。claim・Core呼出に関する安全性は12.1節 SP-1・12.4節に従う |
| T-18 | GCAヘッダ欠落・不正（部分的な`X-GCA-*`）、**および`X-GCA-Identity-Schema`のclient供給値が対応schemaと不一致（A8）** | L1, L2, L3 | **400・E1（`gca_idempotency_invalid_request`）・`none`**（Epoch invalid・E4ではない）。非GCAへfallbackしない。claim 0。**server内部のschema／DB／epoch／configurationの不一致（T-09）はE4（503・`none`）であり、E1と区別される** |
| T-19 | planned break／unplanned break手順の実地確認 | L3 | 13章どおり |
| T-20 | 非GCAリクエストのbehavioral equivalence（Zero-Diff） | L3 | Core Nativeと一致 |
| T-21 | key導出golden vector／禁止入力不在／reclaim経路不在（static） | L1 | 7.4・7.1・10.5節の静的契約が成立 |
| T-22 | **HTTP matrix test（A6で、旧「claim後はすべて409」という一般化を削除し、8.3節の正本応答表に従うmatrix testへ変更。A15・A16：対象は、eligible GCA POST（12.1節 P-2）が投影に到達する場合＝CS-1の範囲に限る）**：8.3節の応答表の**全行**を、行ごとに(条件を注入 → HTTP status・error code・`gca_claim_state`・Core呼出回数)で検証する。少なくとも次を含む。(1)**PROCESSING系**（claim確立後・Core呼出前の捕捉可能な内部障害、Coreの4xx／5xx／例外／`WP_Error`、response・provenance・Verification IDの不一致、R2／R3の失敗、snapshot検証失敗、`UPDATE`の確定的失敗、既存`PROCESSING` rowのduplicate）→ **409 `gca_idempotency_in_progress`・`processing`**。(2)**ACK曖昧**（claim `INSERT`のACK曖昧、`CONFIRMED`への`UPDATE`のACK曖昧）→ **503 `gca_idempotency_unavailable`・`unknown`**。(3)**`INSERT`がACK済みでaffected rows≠1かつduplicate-keyでない** → 503 `gca_idempotency_claim_indeterminate`・`unknown`。(4)**marker関連の行（A17で参照へ整理）**：8.3節の応答表の「marker欠落・不正等」行とE9行（応答の内容は8.3節。marker確定規則・構築は12章が正本であり、本行は再記述しない）。**Finalizerの適用runtime failureは、本テスト（T-22）の対象外**で、**12章 F-\*の保証境界に従い、T-07で検証する**。(5)**`CONFIRMED` duplicateでMedia Verificationが完遂不能** → **503 `gca_idempotency_unavailable`・`confirmed`**。(6)**confirmed inconsistency**（Verificationが完遂し欠落・不一致と確定）→ **409 `gca_idempotency_media_missing`・`confirmed_inconsistent`**。(7)claim前の拒否（400／403／413／503 `none`）。(8)first success＝201・confirmed replay＝200（`confirmed`）。(9)**canonical error表（E1〜E9）の全9組**について、返された応答の**HTTP status・error code・message・`gca_claim_state`・`data.status`が表と完全一致**（messageは固定ASCII文字列の完全一致）。(10)**Finalizerのmarker駆動の構築（A8。A7のresponse class分岐は廃止）**：marker outcomeごとに、12章 marker表・12.1節 P-3に従い最終responseが構築されること（期待値は12章が正本であり、本行は再記述しない）。(11)**exact-key contract（A8）**：12章のexact-key contractに従う（CS-1の範囲内） | L1（応答表の閉集合・Core error転記コード不在・表の行と定数の一致）, L2（行ごとの条件注入）, L3 | **各行が、8.3節の表の指定どおり**。Coreのstatus・code・messageが応答に現れない。**400／403／413は`none`でありclaim確立前にのみ返り、claim確立後に`none`・400・403・413が返る経路が存在しない**。応答bodyに`claim_token`・`idempotency_key`が含まれない。**表に無い応答の組合せが返らない**（閉集合。**CS-1の範囲内に限る**。範囲外の応答は、T-36・T-37・T-38が扱い、本テストの閉集合の対象ではない）。**自由文・Core由来のmessageが応答に現れない** |
| T-23 | **Authoritative Binding**（9.3節、A3で確認点ごとに分割）：3接続のFingerprint（writer・`server_uuid`・DB/schema・table prefix・site・Epoch）を項目ごとに不一致／取得不能にする | L2（fake）, L3 | 下記T-23a〜T-23fのとおり。**claim確立後は`none`へ戻らない** |
| T-23a | **R1（pre-claim）**失敗 | L2, L3 | 503 `gca_idempotency_unavailable`・`gca_claim_state = none`・claim 0（`INSERT`未発行）・Core 0 |
| T-23b | **R2（post-claim・pre-Core）**失敗（claim確立後にFingerprintを食い違わせる） | L2, L3 | `PROCESSING` rowが残る・Core 0・409 `gca_idempotency_in_progress`（`processing`）。`none`・503を返さない |
| T-23c | **R3（post-Core・pre-Verification）**失敗 | L2, L3 | `PROCESSING`のまま・`CONFIRMED`にならない・409 `processing`。mediaは存在しうる（C7） |
| T-23d | **duplicate経路**：duplicate-key観測後のBinding再確認／row読取り失敗 | L2, L3 | 503 `unknown`・Core 0・再`INSERT`なし |
| T-23e | **R3でのBinding mismatch（fault injection、A5で到達可能に修正）**：**R1・R2は通過させる**（Verification接続は、R1・R2のFingerprint確認の時点では正しいschemaを指している）。**Core成功後、R3（Verification直前の再確認）の時点で**、Verification接続の指す先（schema／prefix／writer／`server_uuid`のいずれか）だけを、fault injectionで別のものへ切り替える。切替先の別schemaには、**ID・slugが偶然一致するrow**を置く。（静的に別schemaを指す構成は、R1で拒否されclaimが作られないため、本テストの対象外。T-23fを参照） | L2（fault injection）, L3（接続の切替をテスト用フックで注入できる範囲） | **`PROCESSING` rowが残る**・**`CONFIRMED`にならない（偽の`CONFIRMED`なし）**・**409 `gca_idempotency_in_progress`（`processing`）**。別schemaに一致するrowがあっても、それを根拠にsnapshotを保存しない。別prefix・read-only接続・別`server_uuid`への切替でも同じ |
| T-23f | **静的な別schema構成（pre-claim）**：Verification接続が**最初から**別schema／別prefix／read-only接続／別`server_uuid`を指している（ID・slugが偶然一致するrowを置いても同じ） | L2, L3 | **R1で拒否**：503 `gca_idempotency_unavailable`・`gca_claim_state = none`・**claim 0**・Core 0。Claims Tableに行が作られない |
| T-24 | **multisite fail-closed**：`is_multisite()`が真／関数欠落／例外、`MULTISITE`系定数の真値、`base_prefix`≠`prefix`（5.5節） | L1（確認がclaim前に位置し拒否側へ倒れる静的構造）, L2（stub）, L3（multisite構成） | 503 `none`・claim 0・Core 0。確認不能でも実行しない。非GCAリクエストは影響を受けない |
| T-25 | **durability／DB restart**：(a)claim `INSERT`のACK受領**後**にDB serverを再起動、(b)`CONFIRMED`への`UPDATE`のACK受領**後**にDB serverを再起動、(c)claim後〜`CONFIRMED`前に`mysqld`を異常終了（kill）。再起動はservice restartと強制終了の両方。設定値の確認（T-09）では代替しない（6.4節） | **L3のみ**（実DB。L2のfakeでは証明できない） | (a)再起動後も`PROCESSING`rowが残り、同一identityのduplicateは409 `processing`でCore 0。(b)再起動後も`CONFIRMED`rowとsnapshotが残り、duplicateは200 replayで同一`id`／`source_url`／`mime_type`／`slug`、attachment増加なし。(c)ACK済みのclaimは残る。ACK未受領のcommitは残っても残らなくてもよいが、**どちらでも二重実行・attachment重複は起きない**。OS全体のクラッシュ・電源断は対象外（6.4節） |
| T-26 | **`claim_token`**：CSPRNG生成・**ちょうど32バイト＝64桁hex＝`CHAR(64)`**・非露出（7.8節） | L1（`random_bytes(32)`系の使用・log／応答へtokenを渡す箇所の不在・列定義が`CHAR(64)`であること）, L2（生成されたtokenが`[0-9a-f]{64}`であること、応答・error・ログcaptureにtokenが無い、CSPRNG失敗時にclaim 0・503 `none`） | token露出なし、長さ・形式が列定義と一致、生成失敗はfail-closed |
| T-27 | **C6の分離**（10.6節）：(a)original requestの`INSERT` ACK曖昧→503 `unknown`・Core 0・再`INSERT`なし、(b)後続requestでrowがcommit済み→409 `processing`、(c)後続requestでrowが不在→新規claimに勝つ、(d)originalの`INSERT`が後続のclaimの**後**に遅延到達→一意制約により失敗、行は高々1、二重Core実行なし | L2（fault・遅延commitのfake）, L3（接続断を注入） | 各ケースで規定どおり。Core呼出総数≦1、attachment≦1（T-12） |
| T-28 | **claim後・Core呼出前の捕捉可能な内部障害**（10.2節、8.3節、C1a）：claim確立のACK後、Core呼出前に、例外・メモリ不足相当・応答構築失敗・R2失敗を注入する | L2（fault注入）, L3（可能な範囲） | **Core呼出0**、`PROCESSING` rowが保持され（削除・取消されない）、応答は409 `gca_idempotency_in_progress`（`processing`）。`none`・503 `none`・400・403・413ではない。同一identityのduplicateは409 `processing` |
| T-29 | **body size contract**（8.1節）：空body、上限ちょうど（33,554,432バイト）、上限+1バイト、`Content-Length`と受信長の不一致 | L1（上限定数・検査位置がclaim `INSERT`より前）, L2, L3 | 空bodyは400 `none`。上限ちょうどは受理経路へ進む。上限+1は**413 `gca_idempotency_payload_too_large`・`none`・claim 0・Core 0**。不一致は400。いずれもClaims Tableに行が作られずattachmentが増えない。**32 MiBを超える正当な画像が413で拒否されうることは仕様であり、受理保証が無いことの確認として期待結果に含める**（8.1節）。**L3の前提条件（A5）**：下位層のbody上限（WordPress／PHPの`upload_max_filesize`・`post_max_size`・`memory_limit`、web serverの`client_max_body_size`等）を、**テストに使う上限+1バイト（33,554,433バイト）のbodyよりも大きく**設定でき、その設定が有効であることを**evidenceとして記録**する（U-16）。**下位層がそのbodyを先にrejectする構成（pluginに到達しない構成）は、plugin 413の証明として扱わない**（`gca_claim_state`を欠く応答であり、その場合はL3 evidenceとして不成立で、下位層の設定を修正して再実施する） |
| T-30 | **応答の形とclaim_stateの意味**（8.3節。**検証の対象は、12.1節 CS-1の範囲に限る**。範囲外の応答の形・閉集合は、本テストの対象外）：(a)初回201・replay 200のstatusと、成功JSONの形（8.3節のcanonical payload）、Core responseの他fieldが含まれないこと、snapshotが構築元であること、現行`WordPressMediaUploader`のparse契約を満たすこと（Python側の既存parse関数に対するL1契約検査）、(b)error応答がWP_Error形式で`data.gca_claim_state`を持つこと（8.3節の各行）、(c)**既存の`CONFIRMED` claimがあるidentityのduplicateが、claim確立前の検査（R1・capability・body size等）で失敗した場合に`none`を返しうること**（`none`が「identity未消費」を意味しないことの確認） | L1（応答表の閉集合・shape定数）, L2, L3 | (a)(b)は規定どおり。(c)は`none`でも`CONFIRMED` rowが不変であることを確認し、`none`をretry authorizationとして扱うコードがplugin側にも契約文書にも存在しない（L1：設計書・応答定数に「`none`＝未消費」と読める記述がない） |
| T-31 | **`INSERT`がACK済みだがaffected rowsが1でなく、duplicate-keyでもない**（8.3節、10.2節(c)、C6e）：affected rowsが0・2・取得不能の各注入 | L2（fault注入）, L3（可能な範囲） | **Core呼出0**、再`INSERT`なし、503 `gca_idempotency_claim_indeterminate`・`gca_claim_state = unknown`。**claim成立を断定する応答（`processing`・`confirmed`）を返さない**。後続requestはrowが存在すれば409 `processing`、不在なら新規claimに勝てる。Core呼出総数≦1（T-12） |
| T-32 | **`CONFIRMED` duplicateのMedia Verification**（8.3節、10.3節、C9）：(a)attachmentが欠落／`post_name`不一致と**確定**、(b)Verification自体がDB／I/O／接続障害・timeoutで**完遂できない**、(c)claim読取り成功後のBinding再確認失敗 | L2（fault注入）, L3 | (a)409 `gca_idempotency_media_missing`・`confirmed_inconsistent`。(b)503 `gca_idempotency_unavailable`・`confirmed`。(c)503・`unknown`。**いずれも`create_item`呼出0・新規attachment 0・`CONFIRMED` rowは不変**。**回復後の挙動は分岐ごとに異なる（A11）**：(b)Verification環境の回復後は、attachmentが整合していれば200 replay（欠落・不一致が確定すれば(a)のE8）。(c)Binding再確認が回復し、attachmentが整合していれば200 replay。**(a)のE8経路は、attachment欠落・不一致が確定した状態であり、明示的な修復が完了するまで、後続のduplicateは409 `gca_idempotency_media_missing`・`confirmed_inconsistent`を維持する。Binding・Verificationの環境が単に回復しただけでは、200 replayにならない**（修復の手段・tool自体は6.38のOut of Scope） |
| T-33 | **Core成功後のsnapshot 4項目の検証失敗**（10.4節 手順3、8.3節、C10）：Coreは成功を返すが、(a)`source_url`が欠落、(b)`source_url`が非str・空、(c)DBの`post_mime_type`が許可3種以外、(d)DBの`post_name`が`requested_slug`と不一致、(e)`id`が正のintでない、を注入 | L2（fault注入）, L3（可能な範囲） | **snapshotを保存せず`CONFIRMED`にならない**。`PROCESSING`を保持し、応答は**409 `gca_idempotency_in_progress`（`processing`）**。2xxとcanonical payloadを返さない。Core再実行0。同一identityのduplicateは409。Core呼出総数≦1（T-12） |
| T-34 | **finalizationの順序・所有者・outcome markerからの復元**（10.4節、12章、A8で全面改訂）：(a)手順1〜4の各段階（Core成功後のVerification失敗、snapshot検証失敗、`UPDATE`の確定的失敗、`UPDATE`のACK曖昧）で障害を注入、(b)Finalizerに接続した全DB接続のfakeを置き、呼出回数を数える、(c)**markerの不整合を注入する**：(c1)**marker欠落**（12.4節 B-*のeligibleな経路）、(c2)markerに束縛されたinstanceと異なるrequest（値は等価だが別instance）、(c3)success markerの`idempotency_key`が、requestの`X-GCA-*` headerから再導出したkeyと異なる、(c4)outcomeが許可集合（`SUCCESS_FIRST`／`SUCCESS_REPLAY`／`E1`〜`E9`）外、(c5)success markerのsnapshotの項目欠落・型不正（例：`id`が正のintでない）、(c6)markerの二重設定（success後にerror、error後に別のerror、等）、(c7)形式は正しいが別requestのmarkerへの差替え、(d)**pre-Finalizerの応答の改変（A8。valid markerがある場合）**：pre-Finalizerのcallbackが最終応答を、(d1)**success→error**（201／200→409等）、(d2)**error→success**（E1〜E9のいずれか→200／201と任意のbody）、(d3)**1xx**、(d4)**3xx**、(d5)**任意のbody・status・余分なtop-level fieldや`data`のfieldの付与**、(d6)canonical errorの**statusだけ**の書換え、(d7)空body・非JSON相当のbody、へ変更する | L1（Finalizerのsourceに`INSERT`／`UPDATE`／`SELECT`等のDB呼出・snapshotの意味検証ロジックが存在しない静的検査、**Finalizerがpre-Finalizerの応答のstatus・dataを判断材料として読まない（読取り箇所が無い）静的検査**、markerのwrite-once・plugin-private構造の静的検査）, L2, L3 | **oracleは12章のみ**（本行は、期待値・outcome・response・stateを再定義しない。A17）：(a)10.4節 手順1〜5と12章 marker表（SUCCESS_FIRSTの設定条件）、(b)12章「Finalizerは…DB I/Oを行わない」の項、(c1〜c7)12章 marker確定規則(2)とFinalizerの確認(1)〜(4)、(d1〜d7)12章「pre-Finalizerの応答の改変に対する復元」とexact-key contract（CS-1の範囲内）。**悪意あるcodeへの耐性は検証対象外**（5.2節、12章 markerの性質） |
| T-35（A14追加） | **投影機構とresponse header契約**（oracleは12.1節 P-1〜P-5・12.2節 H-1〜H-3・12.3節 X-11（status line））：eligible GCA POSTの**各outcome**（`SUCCESS_FIRST`・`SUCCESS_REPLAY`・`E1`〜`E9`）について、**clientが実際に受信したHTTP応答**（status・response headers・body）を観測する。H-1の対象headerが存在する状況（Core呼出を伴う`SUCCESS_FIRST`等）を作る | L1（登録位置・返却objectの構造・直接送出headerの除去と差分記録の存在の静的検査）, L2（filter chainのfake、`rest_send_allow_header`による呼出を含む）, L3（実HTTP応答の観測） | 受信応答が12.1節 P-3・12.2節 H-1〜H-3と一致する（status・body・header）。**U-18・U-20が成立しない場合は本テストが成立せず、実装を進めずに本書を改訂する** |
| T-36（A16で改訂、A17で参照へ整理） | **route callbackに到達しない経路（12.4節 B-1〜B-9）、method境界（12.1節 MO-1〜MO-4）、permission_callbackの分離**：B-1〜B-9の各経路を注入する（B-4は、GET・HEAD・OPTIONS・POSTからGETへのoverride・PUT等。B-6は、Coreの引数検証が先に失敗する入力と、Coreを通過してallowlistが拒否する入力の両方。B-9は、未認証およびCore権限不足のuser。GCA capabilityだけを欠くuser）。**method境界として、(M-a)effective POSTのままoverride control（`_method`または`X-HTTP-Method-Override`）を伴うGCA-tagged request（MO-3）、(M-b)override後のeffective methodがPOSTでないrequest（MO-2）を注入する**。`permission_callback`の呼出回数・契機を変えて（`rest_send_allow_header`を含む）、markerの有無を観測する | L1（`permission_callback`の置換・markerへのアクセスが無い静的検査、GCA capability判定がroute callbackの先頭でclaimより前にある静的検査）, L2（各経路の注入）, L3 | **oracleは12.4節（B-1〜B-9・契約・帰結）、12.1節 MO-1〜MO-4・SP-1・CS-1のみ**（本行は、期待値・outcome・response・stateを再定義しない。A17）。各入力が、どのcontract IDに該当するかを観測して一致を検証する。permission_callbackの呼出回数・契機がmarkerを変えないこと（12.4節） |
| T-37（A16で改訂、A17で参照へ整理、A18でdispatch文脈の変種を追加） | **dispatch文脈別の、side-effect safety・投影・method境界の検証（12.1節 SP-1〜SP-3・MO-1〜MO-4・RD-1〜RD-7、12.5節 BT-1〜BT-4）**：同一のGCA POST（`X-GCA-*`付き、route `/wp/v2/media`）を、次の**5つのdispatch文脈**で実行し、(i)effective method、(ii)route callbackへの到達、(iii)claim・Core呼出・`CONFIRMED`化、(iv)Finalizerの作用（no-opか否か）、(v)投影の有無を観測する：**(C1)top-levelのHTTP request（RD-1）**、**(C2)内部`rest_do_request()`**、**(C3)`/batch/v1`の子request（RD-3。`allow_batch`を有効化したテスト構成を含む）**、**(C4)embed sub-request（RD-2。`_embed`で`embeddable`なlinkを持つresponseを返すrouteを使う）**、**(C5)preload（RD-4）**。**method override control（`_method`・`X-HTTP-Method-Override`）は、(C1)では実際のHTTP（`$_GET`・`$_SERVER`）として与え、(C2)〜(C5)では構築したrequest objectのquery parameter・headerとして（`serve_request()`を通さずに）与える**。methodは、(C1)が`REQUEST_METHOD`とoverride後、(C2)が構築時の値、(C3)がbatch dataのmethod、(C4)(C5)が構築methodである。加えて、**`rest_request_from_url`にテスト用callbackを登録し、(C4)のrequestのroute・header・method・型を変える構成**を含める。route handlerの`allow_batch`の値を観測する | L1（claim・Core実行の判定にdispatch文脈の判定が使われていない静的検査、Finalizerがeligibility判定を最初に行い、eligibleでないとき`$result`を変更・参照しない静的検査）, L2, L3 | **oracleは12.1節 SP-1〜SP-3・MO-1〜MO-4・CS-1・RD-1〜RD-7、12.5節 BT-1〜BT-4のみ**（本行は、期待値・outcome・response・stateを再定義しない。A17・A18）。文脈・method／override controlの組合せごとに、どのcontract IDが該当するかを観測して一致を検証する |
| T-38（A14追加、A15でT-38へ改番、A18で拡張） | **投影後の改変点とtopology**（oracleは12.3節 X-1〜X-11、12.1節 RD-6）：approved setへ、各作用点に作用するcallbackを（テスト用に）登録した構成（**`status_header`filterのcallback（status lineを書き換えるものを含む）、`rest_request_from_url`のcallbackを含む**）、およびresponse-shapingのquery parameterを付与したrequest。**`status_header`filterの登録が無い構成と、あるplugin／確認不能の構成の両方**を用意する | L1（topology検査の対象一覧が12.3節・12.1節 RD-6と一致）, L2, L3 | 12.3節の区分どおり（【禁止】【検証】【許容】【境界】【保証外】）、**unsupported topologyの扱いは12.3節 X-11・12.1節 RD-6**。conditional callbackは検出できない可能性がある（T-14と同じ限界）。X-7のencode失敗は12章 F-*の境界（T-07）。**source確認だけではruntimeの成立としない（U-2・U-20）** |

---

## 16. Deployment / Runbook制約

- **6.38はproduction deploymentを含まない**。以下は将来の導入Release／運用向けの制約として記録する。
- v1はsingle authoritative ingress deploymentのみ。multi-node環境ではproduction enableを禁止する。
- WordPress Core version・plugin setはpinned。更新時はEpoch再検証（18章相当）を経る。auto-updateはproductionで無効化または厳格な監視下に置く。
- **DB rollback／restore／failover（lossy含む）を実施した、または疑われる場合は、GCA-taggedトラフィックを止め、Human Gate配下でEpochを終了・再検証してから再開する**（6.3節）。
- periodic external health-check（route registry・callback topology）はdefense-in-depthであり、atomicなsafety fenceとしては主張しない。

---

## 17. Verification Status Ledger / Known Limitations（Amendment A1で再構成）

旧Draftは「WordPress 7.1.1公式sourceを照合済み」（旧§8.1）と「Core sourceへの直接アクセスがなく検証できていない」（旧§17）を同時に述べていた。本章は、主張を**確認状態**で分離して矛盾を解消する。

### 17.1 実確認済み（Amendment A1、2026-10-06、repoのコード・ファイルを直接読取り／コマンド実行）

| ID | 事実 | 確認方法 |
|---|---|---|
| V-1 | `WordPressMediaUploader`はraw-body POST、idempotency metadataを送らない、応答`id`／`source_url`／`mime_type`をparse | `wordpress_media_uploader.py`読取り |
| V-2 | orchestratorは`generate()`→`upload()`の順で、upload試行ごとに画像を再生成する | `article_featured_media_orchestrator.py:72-73` |
| V-3 | v6.32のwrite-ahead（`record_prepared`→`record_attempted`→`record_confirmed`）・manifest登録・`HUMAN_REVIEW_REQUIRED` dispositionがmain.pyに配線済み。attempt-scoped identityに`attempt_ordinal`が含まれる | `main.py:243-345`、`side_effect_operation_identity.py`、`retry_lineage_disposition.py` |
| V-4 | ローカル環境に`php`・`composer`・`mysql`が無く、repoに`wordpress/`ディレクトリが存在しない | `which`、`ls` |
| V-5 | `article_media_upload_state`は2値state・`ATTEMPT_STARTED`再startはfail-closed | `article_media_upload_state_manager.py` |
| V-7 | **（A2追加・A1の誤記訂正）`ArticleMediaUploadRecord.article_identity`には、現行の本番配線で`SideEffectOperationIdentity.as_store_key()`（`root_run_id:attempt_ordinal:media_upload:news_step:article.slug`）が渡される。したがって実体はattempt-scopedであり、再試行をまたいで安定な記事identityの供給元は現行Pythonに存在しない** | `media_upload_safety_coordinator.py:441-448`、`side_effect_operation_identity.py:47-58`、`main.py:285-291` |
| V-8 | **（A2追加、A3で訂正）** 現行Python clientのfilename検証は文字種の正規表現`^[A-Za-z0-9][A-Za-z0-9._-]*$`**のみで、長さ制限は無い**。画像mimeは`image/png`／`image/jpeg`／`image/webp`の3種（8.1節のallowlistと整合）。255文字上限は本pluginの独自contract。**（A4）現行runtimeが生成するfilename（`generate_image_filename()`）の最大長は、コードから65文字と算出できる**（slug部分最大60＋`.`＋拡張子最大4。fallback basenameは24文字、予約名回避は最大10文字）。したがって現行の生成filenameは255文字上限に抵触しない（8.1節 filename contract） | `wordpress_media_uploader.py:18, 85-89`、`article_featured_media_runtime.py:151`、`generated_image_filename_policy.py:11-29, 43-70`、`openai_image_generator.py:34-36` |
| V-9 | **（A3追加、A4で訂正）** 現行のimage generation契約が許す出力寸法は最大3840×2160（`_ALLOWED_SIZES`）。現行コードにアップロードbodyのサイズ上限は存在せず、**`OpenAIImageGenerator`はbase64 decode後のbytesについて非空であること以外（サイズ・寸法・bit depth・metadata・エンコード方式）を検証せず、`GeneratedImage`も非空のbytesとmime形式のみを検証する**。Uploaderもbytesの非空のみ検証する。したがって、32 MiBを超える正当な画像がclient側で止められることなくpluginの413に到達しうる | `openai_image_generator.py:25-29, 222-241`、`generated_image.py:26-37`、`wordpress_media_uploader.py:78-82` |
| V-10 | **（A4追加）** 現行`WordPressMediaUploader`の成功応答parseは、dict／`id`が正のint（boolは不可）／`source_url`・`mime_type`のキー存在かつstrまたはNone、のみを検証し、他のfieldは参照しない。したがって8.3節のcanonical payload（5 field）を変更なしで受理できる | `wordpress_media_uploader.py:245-293` |
| V-6 | `tests/zero_diff_guard_registry.py`の`RELEASE_ORDER`は`v6.36.0`止まり。v6.37.0は新規testファイルを追加せず（既存test 1件のみ変更）、`PROTECTED_PATHS`にも触れていないため、registry追記が不要であったと**整合的に説明できる**（回帰も`[KI-36]`以外に記録なし）。ただし「意図的に未登録とする」旨の明示記述は見つからなかった。6.38と無関係（6.38は影響を受けうる点のみ26章に記録） | registry・CHANGELOG・`git diff 813ba37 5974caf`の読取り |
| V-11 | **（A14追加、A15・A16・A18で訂正。Implementation Start Validation 2026-10-06）** WordPress **7.1.1 tag**の公開sourceの**実行順序**の確認。**内容の正本は12.1節 O-1〜O-13**（本行は確認記録のみ）。結論：A13までの前提「`rest_pre_echo_response`でHTTP statusを置換できる」は偽。status送出は`set_status()`（`:477`）が`status_header()`を呼ぶ（call-site`:1910`）。**`status_header()`の本体は、canonical source（V-16）の`functions.php:1463-1492`に存在する（A18で訂正。status line段階のfilterはX-11）**。**他version（7.1.2等）との同一性は、repo内で再現できるevidenceが無いため、Architectureの前提としない（Validation時の観測としてのみ記録）**。デプロイ先versionは未pin（U-11）、実行時は未検証 | `wordpress-develop` 7.1.1 tagの`class-wp-rest-server.php`・`rest-api.php`・`embed.php`等の取得・読取り（公開tagの行を引用） |
| V-12 | **（A14追加）** Core media response由来のheader、`rest_send_allow_header`・`rest_send_cors_headers`、`response_to_data`の`_links`の確認。**内容の正本は12.1節 O-6・O-11、12.2節 H-1〜H-3** | 同上（`attachments-controller:614-637`、`rest-api.php:805-821・883-916`） |
| V-13 | **（A14追加、A16で更新）** route callbackに到達しない経路、および`/wp/v2/media`のREADABLE／CREATABLE両handler（`posts-controller:73-93`）の確認。**内容の正本は12.4節 B-1〜B-9** | 同上（`server:1115-1126・1256-1270`） |
| V-14 | **（A14追加、A16で更新）** `allow_batch`の宣言（`attachments-controller:35`、`posts-controller:48`）、batch検証（`server:1795-1808`）、batch子requestの`rest_post_dispatch`（`:1889-1896`）、内部`rest_do_request()`（`rest-api.php:603-616`）の確認。**内容の正本は12.1節 SP-1〜SP-3、12.5節 BT-1〜BT-4** | 同上 |
| V-15 | **（A14追加）** S-1に関する7.1.1の事実：`url`引数（`attachments-controller:310`）、`create_item`の`url`分岐（`:543`）、`create_item_from_url`（`:654`、`@since 7.1.0`）。`rest_after_insert_attachment`は`:610`で発火し、その後も`wp_after_insert_post`・`wp_generate_attachment_metadata`が続く（`:612-630`、U-3）。`slug`は`prepare_item_for_database`で`post_name`へ反映される（`posts-controller:1390`。ただし最終的な`post_name`は実行時にCoreが一意化しうる、U-14）。`is_multisite()`は`MULTISITE`・`SUBDOMAIN_INSTALL`・`VHOST`・`SUNRISE`定数で判定する（`load.php`、U-15）。`WP_REST_Request::get_header`は正規化したheader名で取得する（`class-wp-rest-request.php:213`、U-9。proxy／WAFの除去は環境依存） | 同上 |
| V-16 | **（A18追加）** canonical sourceのprovenanceと、call-site・hookの網羅確認。**内容の正本は12.1節 RD-1〜RD-7、12.3節 X-11**（本行は確認記録のみ）。(1)**provenance**：`https://github.com/WordPress/wordpress-develop.git`のtag `7.1.1`（lightweight tag）、commit `a940fbc1e63a7e24d31a28e707e545ad4873cb84`（`git ls-remote`と、公式tagアーカイブ（`codeload.github.com/WordPress/wordpress-develop/tar.gz/refs/tags/7.1.1`、sha256 `21132b657a006ea9d065d789aee98617edf342049cbeb7699f3bbfdcc775ae0f`）のtar headerのcommitが一致）。(2)**供給evidence 14ファイル**（`functions.php`・`class-wp-http-response.php`・`plugin.php`・`class-wp-hook.php`を含む）が、tagアーカイブの同名ファイルとbyte一致（sha256照合）。(3)**網羅確認**：tagアーカイブの`src/`（3793ファイル）全体を走査し、`rest_post_dispatch`の**適用（`apply_filters`）はRD-1〜RD-4の4箇所だけ**、Coreの既定**登録**は`rest-api.php:253-254`と`connectors.php:753`の3つ。`status_header`filterの**適用は`functions.php:1486`の1箇所だけで、Core既定の登録はない**。`rest_request_from_url`の**適用は`class-wp-rest-request.php:1096`の1箇所だけで、Core既定の登録はない**。(4)**evidenceの範囲**：`connectors.php`は、**canonical evidence（14ファイル）には含まれない**。**auxiliary evidence**（repo外。全tree（アーカイブ全6,090ファイル）の検索結果・manifest・`connectors.php`・provenance）が供給しており、**hash・provenance検証済み**（`connectors.php`はgit blob `7433203a…`とbyte一致）。**Review #26で、Codexが両evidence rootを読み、(3)の網羅主張をsource照合した**（Review #25の時点では、(3)はcanonical evidenceだけからは再現できなかった）。evidenceとアーカイブはrepo外にあり、repoには保存しない。**他version（7.1.2等）の同一性は前提としない**。デプロイ先versionは未pin（U-11）、**実行時は未検証** | 公式tagアーカイブの走査（read-only）、`git ls-remote`、sha256照合（2026-10-07） |

### 17.2 自己記録（historical self-recorded、repo内では再現不能・本Amendmentでは未検証）

| ID | 主張 | 扱い |
|---|---|---|
| S-1 | 「WordPress 7.1.1公式sourceの照合（旧Phase B）で、`create_item()`が`url`指定時に`create_item_from_url()`（7.1.0新設）へ分岐することが判明した」 | **（A14）7.1.1 tag sourceで確認された**（V-15）。ただし**デプロイ先versionが未pin（U-11）のため、デプロイ先でも成立するとは限らない**。8.1節の`url`禁止・closed allowlistは、S-1の真偽に依存しない保守的規則であり、結論は変わらない |
| S-2 | Round 1〜13／Codex計8回レビュー／各回の指摘と是正 | historical contextとしてのみ記録（0章）。現行本文の承認根拠ではない |
| S-3 | pre-callback 3種・post-callback 4種のfilter列挙が対象Core versionの完全な集合である | **（A14・A15）post-callback側は誤りと判明**：「4種で完全」ではない（改変点の一覧は12.3節 X-*が正本）。pre-callback側の3種は7.1.1で確認（V-11、U-1）。デプロイ先versionでの確認は未了 |
| S-4 | 対象WordPress versionが「7.1.1」である | **pinされていない**。deploy対象の正確なversionは未確定（U-11） |

### 17.3 未確認（実装前に18章で確認・pinする）

| ID | 未確認事項 |
|---|---|
| U-1 | pre-callback filter（`rest_pre_dispatch`／`rest_request_before_callbacks`／`rest_dispatch_request`）の発火順序・引数・短絡点の完全性 |
| U-2 | **（A14・A15・A18で改訂）** 12.3節の投影後の改変点（X-1〜X-11。**X-11＝`status_header`filter**）が、対象Core versionで列挙どおりであること、およびapproved plugin setのhook登録状況（**`status_header`・`rest_request_from_url`を含む**。12.1節 RD-6）が、12.1節 P-4・12.3節 X-1・X-4・X-6・X-7・X-11の【検証】を満たすこと。**旧前提「Finalizer後に応答を変更できる箇所がゼロ」は偽と判明し撤回した（V-11）** |
| U-3 | `rest_after_insert_attachment`の発火タイミング（Core側でこの後もmetadata処理が継続すること） |
| U-4 | `WP_REST_Attachments_Controller::create_item`のシグネチャ・戻り値契約 |
| U-5 | `rest_endpoints` filterによるroute callback置換が対象Coreで意図通り機能すること |
| U-6 | `_envelope`／`_embed`／`_fields`等の処理経路 |
| U-7 | 対象MySQL/MariaDBでの`transaction_isolation`／`autocommit`／`in_transaction`／durability変数（`innodb_flush_log_at_trx_commit`・`sync_binlog`）・`@@server_uuid`の確認手段の実装可否 |
| U-8 | 3種の独立DB接続（`$wpdb`と別のmysqli等）をplugin内で安全に確立できること。および、9.3節のBinding Fingerprint取得のために、Core `$wpdb`側で読取り専用SELECT（`@@server_uuid`等）を1本発行してよいか／プロパティ・定数参照だけで足りるか |
| U-9 | `WP_REST_Request::get_header`による`X-GCA-*` header取得、およびproxy／WAFによるheader除去の有無 |
| U-10 | approved plugin setの確定 |
| U-11 | 対象WordPress Core versionの確定・pin |
| U-12 | GCA経路での`ignore_user_abort`相当の継続実行がWordPress実環境で有効か |
| U-13 | 8.1節で「検査対象外」とした一般header（認証・`Content-Length`・`Host`・proxy由来等）が`create_item`の挙動を変えないこと。変えうるheaderが見つかった場合は8.1節を改訂する |
| U-14 | server導出の`requested_slug`をCoreへ渡す機構（request parameterへの注入等）と、Coreがattachmentの`post_name`としてそれを尊重すること。尊重されない場合は9.2節のCONFIRM条件が常に不成立となりfail-closed |
| U-15 | `is_multisite()`・`MULTISITE`／`SUBDOMAIN_INSTALL`定数・`$wpdb->base_prefix`・blog IDの、対象Core versionでのセマンティクスと、single-site確認として使えること（5.5節） |
| U-18 | **（A6追加、A8で更新、A14で全面改訂、A18で更新）** 12.1節 P-1・P-3・P-4・P-5（`rest_post_dispatch`での投影：同一instance、返したresponseの反映、最大priority、返却値の型）が、対象version・approved plugin setで成立すること。**（A18）これは4つのcall-site（RD-1〜RD-4）すべてについて確認する（各call-siteの同一instance・Finalizerのno-op（RD-5））**。**旧前提（`rest_pre_echo_response`でのstatus置換）は偽と判明し撤回**（V-11）。満たされない場合は、別方式を実装時に選ばず、本書を改訂する。**7.1.1 source上の成立は、実行時で未検証** |
| U-19 | **（A8追加、A14・A15・A16で改訂）** 12.4節のB-1〜B-9の範囲（route callbackに到達しない経路と、投影の有無）が、対象versionとapproved plugin setで成立すること。**旧前提（control pathがGCA requestを網羅する）は偽と判明し撤回**（V-13）。**A15のpermission phase（PP-*）は、A16で廃止**。成立しない場合は、別方式を実装時に選ばず、本書を改訂する |
| U-20 | **（A14追加、A18で更新）** 12.2節 H-1(b)の直接送出headerの除去が、対象のPHP／SAPIで成立すること（`header_remove`相当、`headers_list()`差分）。**投影のresponse object置換では除去されない**。**（A18）あわせて、12.3節 X-11：`header($status_header, true, $code)`（`functions.php:1490`）が、numericなstatus codeを第3引数どおりに反映すること、`status_header`filterによるstatus line文字列の書換えが実際のstatusに与える影響（対象のPHP／SAPI）、`headers_sent()`が真のときの挙動**。runtime-only |
| U-21 | **（A14追加）** 12.5節 BT-2・BT-3（`allow_batch`が偽、置換後も偽、approved plugin setが有効化しない）が、対象versionで成立すること（7.1.1 source上は成立、V-14） |
| U-22 | **（A15追加、A16で廃止。A17で明確化）** 旧PE-3（`is_dispatching()`によるtop-levelの識別）は廃止した。**廃止済み・non-actionable gap（欠番として記録のみ）であり、active validation inputではない**。現行の確認対象は**U-1〜U-21**である |
| U-17 | **（A4追加）** 初回成功時にCore responseの`source_url`を検証のうえsnapshotへ保存する方式（12章）について、`source_url`がCoreによってどのように決まり（`wp_get_attachment_url`等）、対象環境のplugin（CDN／offload等）で変わりうるか。snapshotの`source_url`はreplay時にその時点の値を返す（現在のURLを再計算しない）。DBでの独立検証は6.38では行わない |
| U-16 | **（A3追加）** 対象環境のPHP／web serverのbody関連上限（`upload_max_filesize`・`post_max_size`・`client_max_body_size`・`memory_limit`等）が、8.1節のplugin固定上限33,554,432バイトを受理できるか。環境側が小さければ環境側が先にrejectし（plugin非到達、`gca_claim_state`を欠く応答）、pluginの上限は意味を持たない。**pluginの固定上限は環境の上限を変更しない**。また、上限ちょうどのbodyを`memory_limit`内で読み取れること。**（A5）さらに、T-29のL3（上限+1バイト＝33,554,433バイトで、plugin自身の413を確認する）の前提として、下位層（WordPress／PHP／web server）のbody上限を、その33,554,433バイトのbodyよりも大きく設定でき、設定が有効であることを確認・記録する**。下位層が先にrejectする構成は、plugin 413の証明として扱わない |

### 17.4 Known Limitations（正直な開示）

- 5.3節の「常時登録・条件付き発火」callbackは静的topology fingerprintでは検出できない可能性がある。
- **6章のとおり、DB rollback／restore／lossy failoverをまたぐ保証はしない。同一DB内markerではrollbackを検出できない。**
- `PROCESSING`は自動回復しない。claim確立後のcrash・曖昧な障害・Coreの決定的拒否は、logical identityを消費したまま人手対応を要する（at-most-onceの代償）。
- orphan attachment／orphan fileの検出・削除は提供しない。
- 再試行をまたいで安定なarticle／content identityの供給元は現行Pythonに存在せず（V-7）、6.38もこれを実装しない。server側保証は供給された値に対するものにとどまる（7.7節）。
- OS全体のクラッシュ・電源断・ストレージ障害に対するdurabilityは検証・保証しない（6.4節・T-25）。
- N1〜N6（3章）の各非対応事項。
- **（A14・A15・A17）** control pathの網羅範囲は12.4節（R-19）、method境界は12.1節 MO-*、投影後の作用点は12.3節、canonical保証の範囲は12.1節 CS-1、`/batch/v1`は12.5節が正本。**Review #24で独立に照合できなかったsource依存の主張は17.6節**（verifiedではなくvalidation-required）。

### 17.5 Implementation Start Validation（2026-10-06）の結果と、A18現在のU-ledgerの状態

**方法**：WordPress **7.1.1 tag**のsource（GitHub `wordpress-develop`）の取得・読取り（read-only）。ローカルに`php`・`mysql`・`composer`・`docker`・WordPress本体は無く、**実行時の検証は一切行っていない**。デプロイ先のWordPress versionは未pin（U-11）。**規範の前提とするのは、7.1.1 tagの引用したcall-siteだけ**で、他version（7.1.2等）との同一性は、repo内で再現できるevidenceが無いため前提としない（Validation時の観測として、7.1.1と7.1.2のREST core 4ファイルが一致したと記録されているが、前提ではない）。**「source確認」は、デプロイ先でも成立することを意味しない**。

| ID | 状態 | 残る前提・次の確認 |
|---|---|---|
| U-1 | source確認（7.1.1。順序と短絡点は12.1節 O-4・O-5、12.4節 B-*） | デプロイ先versionでの再確認（U-11）、approved setの登録状況 |
| U-2 | **旧前提は偽（FAIL）**→A14で12.3節 X-*として再設計。**A18でX-11（`status_header`filter）・12.1節 RD-6（`rest_request_from_url`）を追加** | topologyの実登録確認（approved set、U-10。`status_header`・`rest_request_from_url`を含む）、L3（T-35・T-38） |
| U-3 | source確認（`:610`発火、以後`:612-630`が継続） | デプロイ先version |
| U-4 | source確認（`create_item($request)`、`WP_REST_Response`／`WP_Error`、201＋`Location`＋直接header） | デプロイ先version |
| U-5 | source確認（`rest_endpoints`は`get_routes`で適用、`:974`） | 実行時の置換、handler fingerprint |
| U-6 | source確認（`_envelope`・`_embed`・`_jsonp`・`_method`はserver側、`_fields`は`rest_post_dispatch`の既定filter） | デプロイ先version |
| U-7 | **BLOCKED**（MySQL／MariaDBなし） | 対象DBでの確認手段 |
| U-8 | **BLOCKED**（PHP・DBなし） | 独立3接続の確立、Core `$wpdb`側の読取りSELECTの可否 |
| U-9 | header取得はsource確認（`get_header`）。**proxy／WAFによる除去はBLOCKED** | 実環境経路での確認 |
| U-10 | **BLOCKED**（approved plugin setが未確定） | plugin setの確定・固定 |
| U-11 | **BLOCKED**（デプロイ先versionが不明） | version確定・pin |
| U-12 | **BLOCKED**（実環境が必要） | `ignore_user_abort`相当の有効性 |
| U-13 | **UNVERIFIED**（一般headerが`create_item`に与える影響を網羅的には分析していない） | source分析・実環境 |
| U-14 | **PARTIAL**（`slug`→`post_name`への反映はsource確認。一意化による変更は実行時にのみ判明） | 実環境（T-01） |
| U-15 | **PARTIAL**（`is_multisite()`の意味はsource確認。`$wpdb->base_prefix`・blog IDは未確認） | 残項目の確認 |
| U-16 | **BLOCKED**（PHP／web serverの実環境が必要） | body上限・`memory_limit`の確認 |
| U-17 | **UNVERIFIED**（`source_url`の決まり方・CDN／offload） | source分析・実環境 |
| U-18 | **旧前提は偽（FAIL）**→A14で再設計（12.1節）。新設計は**source上成立**（7.1.1）、**実行時は未検証**。**A18で4つのcall-site（RD-1〜RD-4）へ範囲を明確化** | 実環境での確認（T-35・T-37） |
| U-19 | **旧前提は偽（FAIL）**→A14・A16で再設計（12.4節 B-*）。**source上成立**（7.1.1）、**実行時は未検証** | デプロイ先version・approved setでの再確認（T-36） |
| U-22 | **廃止済み（A16）・non-actionable gap**。active validation inputに含めない（現行はU-1〜U-21） | — |
| U-20（A14新設） | **UNVERIFIED**（直接送出headerの除去可否は、PHP／SAPIでの実行が必要） | 実環境（T-35） |
| U-21（A14新設） | source上成立（7.1.1。`allow_batch`は偽）、**実行時は未検証** | デプロイ先version・approved set（T-37） |
| CSPRNG（18章） | **BLOCKED**（対象PHPを実行できない） | 対象PHPでの確認 |

### 17.6 Review #24で独立にsource照合できなかった主張（Amendment A17）

Review #24（Codex High）は、**ローカルにWordPress 7.1.1のsourceが存在せず**、ネットワークも使えなかったため、下表の主張を**独立にsource照合できなかった**。**A17は、source evidenceの追加・取得・repo保存を行わない**（A17の目的は内部契約の整合性修正に限る）。したがって、下表は**verifiedに格上げしない**。**architecture assumption／validation-required**として扱い、**Implementation Start Validation（18章）に残す**。V-11〜V-15の「source確認」は、2026-10-06のValidation時の観測の記録であり、**repo内に再現可能なevidenceを保存していない**（17.5節、N-01）。成立しない場合は、実装時に別方式を選ばず、本書を改訂する（U-18・U-19の既存の規則）。

| 主張（正本の位置） | 区分 | 確認の位置 |
|---|---|---|
| O-1〜O-13の呼び出し順序（12.1節） | architecture assumption／validation-required | 18章、U-1・U-2・U-18 |
| P-5 request-instance identity（12.1節） | 同上 | 18章、U-18 |
| B-1〜B-9のrouting／authentication／validationの順序（GET／HEAD／OPTIONS／method overrideの扱いを含む。12.4節、12.1節 MO-1〜MO-4） | 同上 | 18章、U-19、T-17・T-36 |
| SP-3の内部`rest_do_request()`の挙動（12.1節） | 同上 | 18章、T-37 |
| BT-2・BT-4の`/batch/v1`と`allow_batch=false`（12.5節） | 同上 | 18章、U-21、T-37 |
| `status_header()`のcall-site（`:1910`。**A18：本体は`functions.php:1463-1492`にあり、source上確認済み**。status line段階のfilterはX-11） | 同上（本体のsource確認はV-16。**実行時のstatus line・numeric statusの扱いはruntime-only**） | 18章、V-11・V-16、U-20 |

**（A18）Review #25の結果**：Review #25（Codex High）は、canonical source（V-16）を読み、上表のsource上の事実を**確認した**（`status_header()`の本体は上表のとおり訂正）。**確認はsource上の事実に限り、runtime（実環境）の項目は未検証のまま**であり、Implementation Start Validationのruntime項目をPASSにしない。デプロイ先versionでの再照合は未了（U-11）。

---

## 18. Implementation Start Validation Checklist

実装フェーズ開始前に、対象デプロイ環境の**正確なWordPress Core version**に対して以下をsource照合し、結果をpinすること。1項目でも未確認のまま実装を開始しない。（旧Draftの全項目を維持し、Amendment A1で★を追加）

**本章の範囲（Amendment A6で明確化）**：本章は、**実装の開始前に確認できる**architecture・environment・source（WordPress Core／PHP／MySQL）の前提のみを列挙する。**実装が存在しなければ確認できない適合検証**（例：実装されたkey導出がidentity contract（7.4節）と一致することのL1 golden-vector検証）は、本章に含めず、**20章の実装フェーズのgate**で扱う（A5までは本章に含まれており、実装開始のgateが循環していた。A6で20章へ移した）。

- [ ] ★ 対象WordPress Core versionの確定とpin（U-11）
**（Amendment A14〜A17）Implementation Start Validationの実施結果（2026-10-06）は17.5節。結果：U-18・U-2・U-19の旧前提が偽（FAIL）と判明し、12章をA14で再設計し、A15〜A17で修正した（現行はA17。確認対象はU-1〜U-21で、U-22は廃止済み）。Review #24で独立に照合できなかったsource依存の主張（17.6節）も本チェックリストに残る。本チェックリストの項目は、すべて未完了（`[ ]`）のまま、デプロイ先versionでの確認を要する（source確認は、デプロイ先での成立を意味しない）。**

- [ ] ★ S-1（`create_item_from_url()`分岐）のsource照合（U-4関連。誤りでも8.1節は有効。**7.1.1 sourceで確認済み（V-15）。デプロイ先versionで再確認する**）
- [ ] pre-callback filter 3種の発火順序・引数・タイミング、および短絡点の完全性（U-1。12.1節 O-4・O-5、12.4節 B-*。7.1.1 sourceで確認済み、デプロイ先versionで再確認する）
- [ ] 投影後の改変点の完全性とapproved plugin setのhook登録状況（U-2。12.3節 X-*（**X-11 `status_header`を含む**）、12.1節 P-4・RD-6）
- [ ] `rest_after_insert_attachment`の発火タイミング（U-3）
- [ ] **投影位置と投影eligibility（A14・A15・A16）**：12.1節 P-1〜P-5の前提（U-18）。**source・登録状況からの実装前の確認**。実機での確認は、実装後のT-35・T-37のL3＝20章。**旧項目（`rest_pre_echo_response`でのstatus置換）は偽と判明し撤回**
- [ ] ★★★★★（A14）Core media response由来headerの除去（12.2節 H-1(b)、U-20）
- [ ] ★★★★★（A14）`/batch/v1`の非到達（12.5節 BT-2・BT-3、U-21）
- [ ] `WP_REST_Attachments_Controller::create_item`のシグネチャ・戻り値契約（U-4）
- [ ] `rest_endpoints` filterによるroute callback置換（U-5）
- [ ] `_envelope`／`_embed`／`_fields`等の処理経路（U-6）
- [ ] ★ `$wpdb`とは独立な2接続（Claims／Media Verification）の確立方法と、`READ-COMMITTED`／`autocommit`／`in_transaction`／durability変数／`@@server_uuid`の確認手段（U-7・U-8）
- [ ] ★ `X-GCA-*` headerの取得可否・中継経路でのheader除去有無（U-9）
- [ ] ★ GCA経路の継続実行（`ignore_user_abort`相当）の有効性（U-12）
- [ ] approved plugin setの確定・固定（U-10）
- [ ] ★★（A2）8.1節closed allowlistの前提確認：`create_item`の挙動を変えうる一般headerの有無（U-13）、server導出slugの注入機構とCoreによる尊重（U-14）。allowlist自体は設計済みであり、**確認結果によって実装時に拡張・解釈変更せず**、変更が必要なら本書を改訂する
- [ ] ★★（A2）9.3節Binding Fingerprintの各項目の取得手段、およびCore `$wpdb`側の読取り専用SELECTの可否（U-8）
- [ ] ★★（A2）5.5節single-site確認の関数・定数のセマンティクス（U-15）
- [ ] ★★（A2）`random_bytes(32)`相当のCSPRNGが対象PHP環境で利用可能であること（7.8節）
- [ ] ★★★（A3）8.1節body size contractの環境前提（U-16）：対象のPHP／web server上限と`memory_limit`が、固定上限33,554,432バイトを扱えること。**上限値そのものは変更せず、環境側の制約が見つかった場合は本書を改訂する**（実装時に上限を変更しない）。**（A5）T-29のL3の前提条件として、対象環境の下位層（WordPress／PHP／web server）のbody上限を33,554,433バイトより大きく設定できること、およびその設定が有効であること（pluginが無い状態でも、そのサイズのbodyが下位層でrejectされず、WordPress標準の経路へ到達すること）のevidenceを得る**（実装前に確認できる環境前提。T-29のL3実施自体は20章の実装フェーズ）。得られない場合、plugin 413のL3 evidenceは不成立として扱う
- [ ] ★★★★★（A8、A14・A16で改訂）12.4節 B-1〜B-9（U-19）。**source・登録状況からの実装前の確認。旧前提（control pathがGCA requestを網羅する）は偽と判明し撤回**
- [ ] ★★★★★（A17）**Review #24で独立に照合できなかった主張（17.6節）**：O-1〜O-13、P-5、B-1〜B-9（GET／HEAD／OPTIONS／method overrideの扱い、12.1節 MO-*が前提とするO-2のmethod変更を含む）、SP-3、BT-2・BT-4（`allow_batch=false`）、`status_header()`のcall-siteを、対象versionのsourceで独立に照合する。**A17はsource evidenceを追加していない**ため、verifiedではなくvalidation-requiredとして残る（**A18：canonical sourceでの照合はReview #25とV-16で行われた。デプロイ先versionでの再照合と、実行時の確認は未了のまま残る**）
- [ ] ★★★★★（A18）**`rest_post_dispatch`の全call-site（12.1節 RD-1〜RD-4）、`status_header`filter（12.3節 X-11）、`rest_request_from_url`（RD-6）**：approved plugin set・対象versionで、(a)4つのcall-site以外が無いこと（RD-7）、(b)`status_header`・`rest_request_from_url`のcallback登録の有無・priority・callback（登録のあるplugin・確認不能はunsupported topology）、(c)各call-siteのrequestの同一instance・Finalizerのno-op（RD-5）、(d)実行時のstatus code・status lineの扱い（U-20）を確認する。**source確認だけでruntimeのPASSとしない**
- [ ] ★★★★（A4）`source_url`の決まり方とsnapshot保存・replayの整合（U-17）：初回成功時のCore responseの`source_url`が、対象環境で安定した値であること（CDN／offload等のpluginの影響を含む）

---

## 19. Independent Review History

- **Historical self-recorded（旧Draft、0章の表）**：Review #1〜#8。各回の要旨（旧Draft記録）：#1 `attachment_id`キー規約不一致等／#2 Phase-2 DBトランザクション安全性／#3 dirty read・slug検証がfilterable応答に依拠・CONFIRM ACK喪失時の矛盾／#4 `rest_dispatch_request`短絡・Epoch latch原子性／#5 isolation level未検証・ingress barrier／#6 pre-callback短絡filter・provenance偽造可能性・node membership／#7 post-callback応答改変／#8 旧Draft本文に対しBlocking 0／Major 0／Minor 0。**これらはrepo内で検証できず、Amendment A1で設計の中核が変わったため、現行本文の承認ではない。**
- **Review #9（Amendment A1テキスト、`codex-readonly-review` wrapper経由、Codex High）：NOT APPROVED（Blocking 0／Major 7／Minor 1／Suggestion 1）。** 要旨（historical record、出力自体はrepo内に保存されていない）：
  - M1：25章がレビュアー宛ての命令文を含んでいた → A2で非拘束の記述へ書き直し
  - M2：`ArticleMediaUploadRecord.article_identity`をattempt-scopedと識別しておらず、安定identity sourceの定義が不足 → A2で訂正（1.2・7.5節）、7.7節で必須preconditionを明記
  - M3：claim後のHTTP契約が曖昧（Core 4xxが設定不備と誤認されうる） → A2で8.3節に確定
  - M4：3接続が同一のwriter・DB・site・prefix・epochを指すことの規範が無い → A2で9.3節を追加
  - M5：closed allowlistの中身が実装に先送りされていた → A2で8.1節に確定
  - M6：multisiteの強制箇所・検証が無い → A2で5.5節に実行時fail-closed契約を追加
  - M7：DB restart後のdurabilityを試すテストが無い → A2でT-25を追加
  - Minor：C6を分離（10.6節）／Suggestion：`claim_token`仕様（7.8節）
- **Review #10（Amendment A2テキスト、`codex-readonly-review` wrapper経由、Codex High）：NOT APPROVED（Blocking 2／Major 3／Minor 3／Suggestion 0）。** Review #9のclosure判定：M1・M2・M6・M7・Minor＝CLOSED、M3・M4・M5・Suggestion＝PARTIALLY CLOSED。要旨（historical record、出力自体はrepo内に保存されていない）：
  - B1：`gca_claim_state = none`を「identity未消費の証拠」と定義していたが、duplicateのrequestでもclaim確立前の検査（validation・capability・Epoch／Binding／multisite・CSPRNG・`INSERT`発行前のDB障害）で失敗すれば`none`を返しうるため、消費済みidentityを「未消費」と報告しうる → A3で`none`の定義を撤回・再定義（8.3節）
  - B2：Verification直前のBinding再確認（post-Core）の失敗規則が「claim 0・Core 0・503 `none`」と書かれ、post-claimの409 `processing`規則と矛盾 → A3で確認点をR1／R2／R3に分け、claim確立後は`none`へ戻らないことを規範化（9.3節）
  - M-A：成功応答がWP_Error形式と矛盾し、成功時の`gca_claim_state`の位置が未定義 → A3で成功＝top-level、error＝`data`配下と一義化（8.3節）
  - M-B：claim前のbody size上限が未決 → A3で33,554,432バイトを確定（8.1節）
  - M-C：claim確立後〜Core呼出前の捕捉可能な内部障害が応答表に無い → A3で行を追加（8.3節、10.6節C1a、T-28）
  - Minor N1（`claim_token`の長さと`CHAR(64)`の不一致）／N2（255文字filename上限を現行Uploaderと同一とした誤記）／N3（MVP Roadmapの確認対象がU-1〜U-12のまま）→ A3で修正
- **Review #11（Amendment A3テキスト、`codex-readonly-review` wrapper経由、Codex High）：NOT APPROVED（Blocking 0／Major 5／Minor 2／Suggestion 0）。** Review #10のclosure判定：B1・B2・M-C・N1・N2・N3＝CLOSED、M-A＝PARTIALLY CLOSED、M-B＝CLOSED（選定は妥当。ただし根拠の記述に別Finding）。要旨（historical record、出力自体はrepo内に保存されていない）：
  - M1：応答表が網羅的でなかった（`INSERT`がACK済みだがaffected rowsが1でなくduplicate-keyでもないケース、`CONFIRMED` duplicateでclaim読取り成功後にMedia Verificationが完遂できないケース） → A4で8.3節・10.2節・10.6節（C6e・C9）・T-31・T-32を追加
  - M2：成功応答の「通常のCore media JSON」のうち、claimに永続化されるのは4項目のみで、replayで返す他のfieldの出どころが未定義 → A4で、初回・replayとも同一のcanonical payload（5 field）に統一し、Core response全文は透過・永続化しないと確定（8.3・12章）
  - M3：32 MiB上限が現行の正規出力をすべて受理するという記述に根拠が無い（現行generatorは非空以外を検証しない） → A4で保証の記述を削除し、plugin独自v1 policyとして、正当な画像でも413で拒否されうることを明記（8.1節）
  - M4：MVP Roadmapのgate記述が古い（A1承認の要求、「必須12件」） → A4で特定のAmendment番号・固定件数に依存しない条件へ更新
  - M5：旧25章に、レビューの方法・解釈・結論に関するメタ記述が残っていた → A4で25章を設計判断・検証の対応表へ置き換え、メタ記述を削除
  - Minor：8.1節の`claim_state`表記の不統一（`gca_claim_state`へ統一）／filename最大長を「未確認」としていたが、現行filename生成contractから65文字と算出可能 → A4で修正
- **Review #12（Amendment A4テキスト、`codex-readonly-review` wrapper経由、Codex High）：NOT APPROVED（Blocking 1／Major 2／Minor 3／Suggestion 0）。** Review #11のclosure判定：M3・M4・M5・N1・N2＝CLOSED、M1・M2＝PARTIALLY CLOSED。要旨（historical record、出力自体はrepo内に保存されていない）：
  - A4-B1：初回成功時のfinalizationが自己矛盾（10章は「`CONFIRMED`化とsnapshot保存はFinalizerの前」、8章・12章は「4項目の検証とsnapshot保存はFinalizerの仕事」、T-16は「Finalizerが永続化済みsnapshotを復元」）。また、Core成功後に`source_url`が欠落・不正な場合の失敗が、8.3節の応答表とC7に無い → A5で所有者（route callback）と順序（10.4節）を一本化し、Finalizerは全置換のみに限定（12章）。応答表・C10・T-33を追加
  - A4-M1：Goal G2（Python側に耐久状態を持たせない）が、stable identityのdurable保持（7.7節）と矛盾して読める → A5でG2を、結果・claim stateとidentityに分離して修正
  - A4-M2：T-23eが静的な別schemaを指す構成だと、R1で拒否されclaimが作られず、期待結果（`PROCESSING` row保持）に到達しない → A5でR3でのfault injectionへ修正、静的構成はT-23fへ分離
  - Minor：用語集の`claim_state`の残り／23章の503 `confirmed`がC9を含まない／T-29のL3前提（下位層のbody上限）の不足 → A5で修正
- **Review #13（Amendment A5テキスト、`codex-readonly-review` wrapper経由、Codex High）：NOT APPROVED（Blocking 0／Major 3／Minor 0／Suggestion 0）。** Review #12の全Findings（A4-B1・A4-M1・A4-M2・Minor 3件）＝CLOSED。要旨（historical record、出力自体はrepo内に保存されていない）：
  - M1：Finalizerが置換するのはdataのみでHTTP status（201／200）を置換せず、信頼するrequest-local snapshot（context）に完全性の束縛が無い。pre-Finalizerのcallbackがstatusを変えたり、形式の正しい別contextへ差し替えたりしても検出できない → A6でFinalizerをcanonical success responseの最終所有者とし、dataとstatusの両方を置換、contextをplugin-private・write-onceとして5要素に束縛（12章）
  - M2：必須T-22が「claim後はすべて409（ACK曖昧のみ503）」と書かれ、T-07・T-32・応答表（Finalizer failure・confirmed duplicateのVerification不能は503 `confirmed`、confirmed inconsistencyは409）と矛盾 → A6でT-22を応答表に従うmatrix testへ変更
  - M3：実装開始前に完了すべき18章が、実装後でなければ確認できないL1 golden-vector適合を含み、gateが循環 → A6で20章の実装フェーズgateへ移動
- **Review #14（Amendment A6テキスト、`codex-readonly-review` wrapper経由、Codex High）：NOT APPROVED（Blocking 1／Major 1／Minor 1／Suggestion 0）。** Review #13のclosure判定：M3＝CLOSED、M1・M2＝PARTIALLY CLOSED。要旨（historical record、出力自体はrepo内に保存されていない）：
  - B1：Finalizerは「successの context が失われた」ことと「error経路でcontextが意図的に無い」ことを区別できない。contextはsuccess時にのみ作られ、Finalizerはconfirmed／replayのcontextがあるときにのみ作用するとされる一方、context欠落は503 `confirmed`にするとされており、すべてのGCA requestに適用すると正当なerrorを誤り、contextを発動条件にすると欠落が検出不能になる → A7でFinalizerの発動判定をresponse class（2xx／canonical error／その他non-2xx）で規定（12章）
  - M1：旧一般化「claim後の失敗はすべて409 `processing`」が、23章と設計判断の索引（D-4）に残り、応答表の503 `unknown`・503 `confirmed`と矛盾 → A7で削除し、応答表・canonical error表が正本であることへ統一
  - N1：error messageを固定文言とするが、正準な文字列とtest oracleが無い → A7でcanonical error表（E1〜E9）に固定message文字列を正本化し、T-22で完全一致を検証
- **Review #15（Amendment A7テキスト、`codex-readonly-review` wrapper経由、Codex High）：NOT APPROVED（Blocking 1／Major 2／Minor 1／Suggestion 0）。** Review #14のclosure判定：M1・N1＝CLOSED、B1＝PARTIALLY CLOSED。要旨（historical record、出力自体はrepo内に保存されていない）：
  - B1：A7のresponse-class分岐は網羅的だが、意味として成り立たない。durable successの応答が2xx以外へ変えられるとclass B／Cとして扱われ、canonical successの復元要求に反する。逆に、pre-callbackの短絡やerrorが2xxへ変えられるとsuccess contextが無く、503 `confirmed`と誤って応答する。トポロジの確認だけでは足りず、信頼できるroute-outcome markerまたは同等の強制可能な契約が必要 → A8でresponse classによる分岐を廃止し、authoritative outcome markerだけから最終responseを構築する方式へ置換（12章）
  - M1：`X-GCA-Identity-Schema`の不一致に、E1（400）とE4（503）の2つの正準の結果が併存 → A8でclient供給値の不一致をE1に統一し、server内部の不一致をE4として区別
  - M2：class Bの判定がE1〜E9の組と`data.status`のみで、top-levelと`data`のkey集合を確認しない → A8でmarkerから応答を新規構築し、exact key setだけを出力する契約とした（判定自体が不要）
  - Minor N1：class Cが1xxと3xxを含むが、必須テストが3xxのみ → A8でT-34(d3)(d4)に1xx・3xxを追加
- **Review #16（Amendment A8テキスト、`codex-readonly-review` wrapper経由、Codex High）：NOT APPROVED（Blocking 1／Major 1／Minor 2／Suggestion 0）。** Review #15のclosure判定：M1・M2・N1＝CLOSED、B1＝PARTIALLY CLOSED。要旨（historical record、出力自体はrepo内に保存されていない）：
  - B1：Finalizerの失敗の契約が自己矛盾。valid `SUCCESS_*` markerは201／200のcanonical responseに一意に対応しwrite-onceだが、Finalizerが応答を置換できない場合は、同じ応答のstatusとdataを置換してE9を出す必要があり、第2の仕組みもE9 markerへの遷移も定義されていない。C5・T-07が実装不能で、「markerだけで応答が一意に決まる」という不変条件が成り立たない → A9で案Bを採用：選択・構築をtotalかつ一意とし、適用そのものの失敗はE9へfallbackせずcanonical responseを保証しない
  - M1：必須T-22(4)が、marker・context欠落・束縛不一致・不正・置換失敗のすべてをE9／`confirmed`とする旧い期待を保つ → A9で同期
  - Minor N1：D-17・R-5がU-1〜U-18のまま（U-19が抜けている）／N2：用語集のFinalizer定義が12章と不整合 → A9で同期
- **Review #17（Amendment A9テキスト、`codex-readonly-review` wrapper経由、Codex High）：NOT APPROVED（Blocking 1／Major 1／Minor 0／Suggestion 0）。** Review #16のclosure判定：M1・N1・N2＝CLOSED、B1＝PARTIALLY CLOSED。要旨（historical record、出力自体はrepo内に保存されていない）：
  - B1：適用失敗の境界が保証できない内容を保証している。(1)適用が失敗した時点で、出力された応答が`gca_claim_state`を持たないこと、canonicalに見えないことを保証できない（部分的に適用された応答や元の応答が含みうる）、(2)C5・T-07が全valid marker（E1〜E9）に「`CONFIRMED`不変・次のduplicateがreplay（200）」を要求しているが、E1〜E4はclaimが無いことがあり、E5・E6は不確定、E7は`PROCESSING`で、oracleと回復の主張が成り立たない → A10で12章を唯一の正本とし、応答内容は未定義へ弱め、outcome別のdurable-state oracleへ修正
  - M1：規範部分に「Finalizer failure→503 `confirmed`」の割当てが残存（8.3節のerror形状・契約#3、23章、Roadmap／Change Record）→ A10で削除・訂正
- **Review #18（Amendment A10テキスト、`codex-readonly-review` wrapper経由、Codex High）：NOT APPROVED（Blocking 0／Major 2／Minor 2／Suggestion 0）。** Review #17のclosure判定：M1＝CLOSED、B1＝PARTIALLY CLOSED。要旨（historical record、出力自体はrepo内に保存されていない）：
  - M1：12章は、A10が主張した「唯一の正本」になっていない。参照のみのはずの節・表・テスト・索引・リスク・Roadmapに、適用失敗の契約が再記述されて残り、既に矛盾を生んでいる（R-17の「E5でも`CONFIRMED`不変・replayで回復」と、C5b・12章の「claimの有無は不確定」との矛盾）→ A11で、12章以外を参照のみに整理
  - M2：T-07にE1〜E4向けの正確なoracleと層の割当てが無い。E1〜E4は「このrequestが新しいclaimを作らなかった」だけを意味し、既存のclaim（`PROCESSING`／`CONFIRMED`）があり得る。またmarkerの不変（request-localの非公開状態）をL3に割り当てているが、L3から観測する手段が無い → A11でT-07を精密化・層分離
  - Minor N1：T-32が3分岐すべてで回復後の200 replayを期待しているが、E8は明示的な修復が必要／N2：26章の見出しが古い → A11で修正
- **Review #19（Amendment A11テキスト、`codex-readonly-review` wrapper経由、Codex High）：NOT APPROVED（Blocking 0／Major 1／Minor 0／Suggestion 0）。** Review #18のclosure判定：M2・N1・N2＝CLOSED、M1＝PARTIALLY CLOSED。要旨（historical record、出力自体はrepo内に保存されていない）：
  - M1：Finalizerの適用runtime failureの境界が、まだ12章のみで定義されていない。C11、T-07、T-22、およびROADMAPに、再記述が残る。現在は12章と一致するが、純粋な参照ではなく、以前に矛盾を生んだ重複が残っている → A12で、12章の表に識別子（F-1〜F-6）を付与し、他は識別子による参照のみに整理
- **Review #20（Amendment A12テキスト、`codex-readonly-review` wrapper経由、Codex High）：NOT APPROVED（Blocking 0／Major 1／Minor 1／Suggestion 0）。** Review #19のM1＝PARTIALLY CLOSED（F-1〜F-6の分類は完全・一元化、C11・T-07・T-22・両Roadmapは参照のみになった）。要旨（historical record、出力自体はrepo内に保存されていない）：
  - M1：26章のR-10が「claim後の失敗は一律409 `processing`へ正規化」と広く書いたままで、8.3節の正本matrix（claim後の503 `unknown`／`confirmed`を含む）と矛盾し、12章が応答内容を未定義とするFinalizerの適用失敗にも409を割り当てうる。以前に閉じた「claim後はすべて409」の再発 → A13でR-10を、8.3節の正本matrixへの参照のみに訂正
  - Minor：26章の見出しが「Amendment A11時点」のまま → A13で更新
- **Review #21（Amendment A13テキスト、`codex-readonly-review` wrapper経由、Codex High）：APPROVED（Blocking／Major／Minor／Suggestion＝0）。** Review #20のM1・Minor＝CLOSED。要旨（historical record、出力自体はrepo内に保存されていない）：R-10が8.3節の正本matrixへの参照のみになり、26章の見出しがA13になった。claim後を409へ一般化する記述は規範部分に残っていない。**このAPPROVEDは、設計文書の内部整合性の判定であり、WordPress・PHP・MySQLの未検証前提（U-1〜U-19）を確認済みとしたものではない**。commit `2513ae5`でdocs-only checkpointとして確定した。
- **Implementation Start Validation（2026-10-06）**：18章に従い、WordPress 7.1.1 tag sourceをread-onlyで確認した（実行時の検証は無し）。**設計前提の誤りを3件検出**：U-18（status置換）・U-2（Finalizer後の改変点ゼロ）・U-19（control pathの網羅）がいずれも偽（V-11〜V-13、17.5節）。あわせて、Core media response由来headerの残存、`permission_callback`の複数回呼出、`/batch/v1`の未整理を検出した。**Implementation Start Readiness＝NOT READY、Architecture Amendment必要＝YES** → **A14**で12章を再設計。
- **Review #22（Amendment A14テキスト、`codex-readonly-review` wrapper経由、Codex High）：NOT APPROVED（Blocking 1／Major 3／Minor 2／Suggestion 0）。** 取得済みの7.1.1 sourceを読み、実行順序O-1〜O-13を実質的に検証した。U-18＝解消（設計上）、U-2・U-19＝部分的に解消。要旨（historical record、出力自体はrepo内に保存されていない）：
  - B1：B-5・B-6・B-7では、`rest_send_allow_header`が本pluginのラップした`permission_callback`を**初めて**呼ぶ（再呼出ではない）ため、M-5（再呼出でmarkerを書かない）では、E3等のmarkerが設定されうる → A15で、permission phase（12.4節 PP-1〜PP-6）を定義
  - M1：8.3節・T-22の閉集合と、X-1・X-8・B-1の非canonical応答の許容が矛盾 → A15で、CS-1（12.1節）に範囲を限定
  - M2：batchのsub-requestが`/wp/v2/media`＋`X-GCA-` headerのままFinalizerの対象になる → A15で、投影eligibility（P-2、PE-3の`is_dispatching()`）を定義
  - M3：12章の契約が8.3・15.2・25・26・変更ログで再記述されている（単一正本の違反）→ A15で、IDによる参照のみへ整理
  - N1：`status_header()`の行番号の誤り／N2：`rest_envelope_response`が改変点の一覧に無い → A15で訂正
- **Review #23（Amendment A15テキスト、`codex-readonly-review` wrapper経由、Codex High）：NOT APPROVED（Blocking 1／Major 4／Minor 1／Suggestion 0）。** Review #22の closure：M2・N1・N2＝CLOSED、B1・M1＝PARTIALLY CLOSED、M3＝OPEN。要旨（historical record、出力自体はrepo内に保存されていない）：
  - B-01：A15のpermission phase（arm／consume／disarm）は、filter chainの途中の値とCoreが判定する最終値の差、armの間の別callbackによる呼出、例外時のdisarm漏れにより、primary permission評価を確実に識別できない → A16で、`permission_callback`をmarkerから完全に切り離し、PPを廃止
  - M-01：`is_dispatching()`はtop-level originを証明せず、内部`rest_do_request()`はcontrol pathを実行しながら`rest_post_dispatch`を通らない → A16で、side-effect safety（SP-1）と投影を分離し、PE-3（top-level識別）・U-22を廃止
  - M-02：`/wp/v2/media`のREADABLE handlerにGET／HEAD／overrideが一致する経路がB-*にない → A16で、B-4を改訂、PE-3＝effective method POSTへ
  - M-03：8.3節のexact-body・T-30の閉集合が、CS-1に限定されていない → A16で、CS-1へ限定
  - M-04：12章以外に契約の再記述が残る → A16で、12章の識別子による参照のみへ整理
  - N-01：`status_header()`の関数本体と7.1.2同一性は、再現可能なevidenceが無いのに前提としている → A16で、前提から外した
- **Review #24（Amendment A16テキスト、`codex-readonly-review` wrapper経由、Codex High）：NOT APPROVED（Blocking 0／Major 2／Minor 1／Suggestion 0）。** Review #23のclosure判定：B-01・M-01・M-03・N-01＝CLOSED、M-02・M-04＝PARTIALLY CLOSED。要旨（historical record、出力自体はrepo内に保存されていない）。**Codexはローカルに7.1.1 sourceを持たず、O-1〜O-13・P-5・B-1〜B-9・SP-3・BT-2／BT-4・`status_header()`のcall-siteを独立に照合できなかった**（17.6節）：
  - M-A16-01：method overrideの契約が内部矛盾。8.1節・T-17は「override requestはE1／400」、B-4・T-36は「POSTからGET等へのoverrideはwrapped POST callbackと投影を迂回しCore Native」と定めており、必須テストの期待値が両立せず、wire contractを実装できない → A17で、effective method基準（12.1節 MO-1〜MO-4）に統一
  - M-A16-02：Review #23 M-04が未解消。12章が正本と定めるmarker・control path・projection・batch／internal dispatchの結果を、T-34・T-36・T-37が再記述している → A17で、テスト節を「どのcontract IDを、どのscenarioで検証するか」のみにし、期待値・状態遷移・response semanticsは12章のID参照のみへ整理
  - Minor N-A16-01：A16の記録が一部未同期（D-17がU-1〜U-22のまま、17.5節の見出しと18章の注記がA14／A15表記のまま）→ A17で同期
- **Review #25（Amendment A17テキスト、`codex-readonly-review` wrapper経由、Codex High。canonical WordPress 7.1.1 source evidenceをread-onlyで照合）：NOT APPROVED（Blocking 0／Major 2／Minor 1／Suggestion 0）。** Review #24のclosure判定：M-A16-01・M-A16-02・N-A16-01＝CLOSED。Codexはevidence directoryを読み、14ファイルが`SHA256SUMS`と一致したと報告した。要旨（historical record、出力自体はrepo内に保存されていない）：
  - M-25-01：設計が、Coreの`rest_post_dispatch`のcall-siteをすべて扱っていない。12章はtop-levelとbatch子を扱うが、`embed_links()`（server:824）とREST preload（rest-api.php:3033）を扱わない。stockのrequestはGET／OPTIONSでeligibleでないが、globalなFinalizerは実行され、approved hookがrequest objectに影響しうる → A18で、4つのcall-siteを12.1節 RD-1〜RD-7に分類し、Finalizerの安全なno-opと、request-affecting hookのtopology検証を規定
  - M-25-02：post-projectionのtopologyと検証台帳が、供給されたsourceと食い違う。`status_header()`の本体は`functions.php:1463-1492`に存在し、header送出前の`status_header`filterを含む。X-*・U-2・V-11・T-38・topology検査に、このfilterが無い → A18で、本体の存在へ訂正し、12.3節 X-11・U-2・U-20・V-11・V-16・T-38・18章を同期
  - Minor N-25-01：T-17／T-36が、method／overrideのmatrixを、内部`rest_do_request()`・batch子のdispatchと掛け合わせていない → A18で、T-37にdispatch文脈の変種（C1〜C5）を追加
- **Review #26（Amendment A18テキスト、`codex-readonly-review` wrapper経由、Codex High。canonical・auxiliaryのWordPress 7.1.1 source evidenceをread-onlyで照合）：APPROVED（Blocking 0／Major 0／Minor 2／Suggestion 0）。** Review #25のM-25-01・M-25-02・N-25-01＝CLOSED、Review #24のclosureにregressionなし。Codexは両evidence rootを読み、canonical 14／14・auxiliary 10／10のファイルが各`SHA256SUMS`と一致したと報告した。要旨（historical record、出力自体はrepo内に保存されていない）：
  - 新規のBlocking／Majorはなし。runtime（デプロイ先version・approved plugin topology・実行時のinstance・PHP／SAPI・L2／L3等）は、source確認だけではPASSにしない（17.6節）
  - Minor（文書の同期のみ。契約は変えない）：(1)V-16が「`connectors.php`は供給evidenceに含まれない」とのみ書き、canonicalとauxiliaryの区別が無い、(2)U-ledgerの見出しが「A17現在」のまま、およびMVP Roadmapのcurrent statusの日付が2026-10-06のまま → **Review #26 APPROVED後のdocs sync**で、(1)(2)を同期（契約・ID・scope・テスト・台帳の内容は変更していない。24.18節の補記）
  - **このAPPROVEDは、設計文書の内部整合性とsource上の事実の判定であり、Implementation Start Validationのruntime項目を確認済みとするものではない**。Human Gate（21章）の承認、commit、pushは別途要する

---

## 20. Definition of Done

Architecture Gate（実装開始前）：
- [x] 最新のArchitecture Design（本書の現行版）が、独立Architecture Reviewで`APPROVED`（Blocking 0／Major 0）に到達する（特定のAmendment番号には依存しない。Amendmentを重ねた場合は、その時点の最新版が対象）**（Review #26で到達、2026-10-07。以降のdocs syncは契約不変）**
- [ ] 18章のImplementation Start Validation Checklistを完了し、結果をpinする
- [x] Human Gate（21章）の承認を得る**（5論点を個別にACCEPT、2026-10-07。21章の「ACCEPT記録」）**

実装フェーズ：
- [ ] `wordpress/gca-media-idempotency/`を新設し、本書の設計に基づき実装する（**repoへの配置のみ。本番deployは含まない**）
- [ ] **Logical identity contract（7.4節）のL1 golden-vector実装適合（A6で18章から移動）**：実装されたserver-side key導出が、identity contractと**一字一句一致**することを、L1 golden vector（Python参照実装）で確認する。対象は、`identity_schema_version`定数、`article_identity`／`media_role`／`content_revision`の形式検証、LP encoding、`idempotency_key`導出、`requested_slug`（`"gca-media-v1-" + idempotency_key`、64桁hex全体、切り詰めなし）、およびfail-closed条件。**実装が存在して初めて確認できるため、実装開始前のgate（18章）には含めない**（T-21）
- [ ] L1 Static／Contract E2E（Python）をPASSさせ、`tests/zero_diff_guard_registry.py`へ自己登録する（6.37.0が`RELEASE_ORDER`未登録である点の整理を含む。26章）
- [ ] L2 PHP unit結果を、PHP実行可能な環境で取得し記録する
- [ ] L3 Staging fault matrix（15章でmandatoryと定義された全validation scenario（現行版ではT-01〜T-38。件数・範囲は15章が正本）のL3対象。**T-25のDB restart durability検証を含む**）を実環境で実施し、証跡を記録する。**L2／L3のevidenceが得られない場合、6.38は「Foundation実装済み・実環境検証待ち（production activation不可）」として完了を限定的に宣言し、完了とは主張しない**
- [ ] Python側（`src/`・`main.py`・`scripts/`）の無改修をZero-Diffで確認する
- [ ] 非GCAリクエストのZero-Diff（T-20）を確認する
- [ ] Formal Regression（既存Inventory）に回帰がないこと
- [ ] `docs/CHANGELOG.md`へ実装完了エントリを追記する（Architecture Gate完了時点では追記しない）

---

## 21. Human Gate Checklist

- 本書はArchitecture Design段階の成果物であり、Production code実装・`git commit`・`git push`・`git tag`はいずれも別途のHuman Gate承認を要する（Global Development Gates準拠）。
- Architecture Gateとしてユーザーが個別にACCEPTすべき論点（独立Architecture Reviewが`APPROVED`した後）：
  1. 6.38を**Consumer-less Foundation**とし、Python integration・production deploymentを別Releaseに分けること（2章）
  2. logical identity＝`article_identity`＋`media_role`＋`content_revision`（image bytes・attempt・runを使わない）（7.4節）、およびstable identity sourceをIntegration Releaseの必須preconditionとして6.38では実装しないこと（7.7節）
  3. `PROCESSING`の自動reclaim禁止と、Core拒否・曖昧障害でidentityが消費されるコストの受容（10章）
  4. DB rollback／restore／lossy failoverを保証しないこと、外部epoch anchorをOut of Scopeとすること（6章）
  5. L2／L3 evidenceが得られるまで完了を主張しないこと（15.1節・20章）
**Architecture Human Gate ACCEPT記録（2026-10-07）**：ユーザーが、上記の5論点を**個別にACCEPT**した。ACCEPT時点の設計書は、Amendment A18・Review #26 APPROVED・Architecture checkpoint `f719908`である。

| # | ACCEPTした内容（ユーザーの文言の要旨） | 正本 |
|---|---|---|
| 1 | Release 6.38.0を**Consumer-less Foundation**とし、Python integrationとproduction deploymentを別Releaseへ分離する | 2章 |
| 2 | logical identityを`article_identity + media_role + content_revision`とし、image bytes・attempt・runを使用しない。stable identity sourceは後続Integration Releaseの**必須precondition**とし、6.38では実装しない | 7.4・7.7節 |
| 3 | `PROCESSING`の**自動reclaimを行わず**、Core拒否や曖昧な障害でidentityが消費されたままになる運用コストを受容する | 10章 |
| 4 | DB rollback／restore／lossy failoverを**保証せず**、外部epoch anchorをOut of Scopeとする | 6章 |
| 5 | L2／L3 evidenceが得られるまで、Release 6.38.0の**完全な完了を主張しない** | 15.1節・20章 |

- **ACCEPTの範囲**：上記は設計判断の承認であり、**設計の内容（契約・scope・ID・テスト・台帳）は変更しない**。Review #26は設計の内部整合性とsource上の事実の判定であり、本ACCEPTはそれとは別のHuman Gateである。20章の「Human Gate（21章）の承認を得る」に対応する。
- **ACCEPTしていないもの（別のHuman Gateとして残る）**：**Implementation Start Validation（18章）の完了と結果のpin**、**Production codeの実装開始**、`git tag`、production deployment。**本ACCEPTは、Implementation Start Validationのruntime項目をPASSにするものではなく、実装開始の許可でもない**。
- **Git操作の位置づけ**：Architecture checkpoint（A14〜A18・Review #26 APPROVED・post-review docs sync）は、commit `f719908`としてcommit・push済みである。**本ACCEPT記録は、その`f719908`の後に追加された記録である。** 今後のGit操作（`git commit`・`git push`・`git tag`等）は、Global Development Gatesに従い、**必要なHuman Gateを個別に経る**（本ACCEPTは、それらの承認を含まない）。

---

## 22. Rejected Alternatives

### 22.1 クライアント側ローカル耐久状態方式（Draft v8〜v18）（historical self-recorded）

18ラウンドにわたり、クライアント（Python）側にファイルベースの耐久状態・世代アンカーを持たせる方式を検討したが、プロセスクラッシュ・複数マシン実行系列をまたぐ「真のsource of truth」をクライアント側に確立できず保留した。

### 22.2 Simplification Pivot（Named Mutex + resolver-first）（historical self-recorded）

Win32 Named Mutexによる排他とGET-then-POSTのresolver-first方式へ簡素化した案を検討したが、Codex独立レビューでBlocking判定を受け棄却した。

### 22.3 WordPress server-side idempotency（採用）

WordPress自身をsource of truthとするserver-side方式を採用する。

### 22.4 image bytes digestをidentity keyにする方式（Amendment A1で棄却）

画像が`upload()`のたびに再生成されるため、bytes由来のkeyは試行間で一致せず重複抑止にならない（7.4節）。診断メタデータ用途にのみ残す。

### 22.5 attempt-scoped identity（`root_run_id`／`attempt_ordinal`）をserver keyに含める方式（Amendment A1で棄却）

再実行ごとに別claimになり、Release目的に反する（7.4節）。

### 22.6 stale `PROCESSING`のTTL／自動reclaim／Media Verificationによる自動promote（Amendment A1で棄却）

`PROCESSING`がCore実行前か後かをserverは区別できず、自動で再実行・昇格すれば重複authorizationまたは誤った`CONFIRMED`になりうる（10.5節）。

### 22.7 同一DB内marker／dual anchorによるrollback検出の保証（Amendment A1で撤回）

markerはclaim行と同時にrollbackされるため検出保証にならない（6.3節）。検出可能なmismatchのfail-closedにのみ用いる。

---

## 23. Python HRR／既存Safety Layerとの互換性（Amendment A1で追加）

### 23.1 原則

- **server-side状態機械（`PROCESSING`／`CONFIRMED`）とPython側HRR（`HUMAN_REVIEW_REQUIRED`）、write-ahead状態（`PREPARED`／`IO_ARMED`／`CONFIRMED_SUCCESS`）は別物**である。状態名が似ていても、同一視・自動同期・相互参照をしない。
- **6.38ではこれらを接続しない**。server側はPythonのstateを読み書きせず、Python側もserver側stateを参照しない。接続は**将来のIntegration Release**で、別途Architecture Review・Human Gateを経て行う。

### 23.2 概念対応（非拘束・Integration Releaseの設計材料）

| server側の結果（8.3節） | 意味 | Integration Releaseで検討すべきPython側の扱い（6.38では実装しない） |
|---|---|---|
| 201（初回成功）／200（replay）、`gca_claim_state = confirmed` | media確定 | `record_confirmed`相当へ進める候補 |
| 409 `gca_idempotency_in_progress`（E7）、`processing` | `PROCESSING`（claim後の**`PROCESSING`系の失敗**：Core非success・検証失敗・snapshot検証失敗・R2／R3の失敗・`UPDATE`の確定的失敗等、および既存`PROCESSING` rowのduplicate。進行中かstaleかは区別不能）。**claim後の失敗がすべてこの行になるわけではない**（ACK曖昧は503 `unknown`、`E9` markerによる`CONFIRMED` duplicateのVerification不能は503 `confirmed`、marker欠落・不正は503 `unknown`、confirmed inconsistencyは409 `confirmed_inconsistent`。応答の正本は8.3節の応答表とcanonical error表。**Finalizerの適用runtime失敗の挙動は12章の保証境界に従い、本表では定義しない**） | 自動retryせず`HUMAN_REVIEW_REQUIRED`相当へ送る候補。**設定不備や要求不正として扱ってはならない** |
| 409 `gca_idempotency_media_missing`、`confirmed_inconsistent` | `CONFIRMED`だがattachment不整合 | `HUMAN_REVIEW_REQUIRED`相当 |
| 503 `gca_idempotency_unavailable`、`unknown`／`confirmed` | 結果不明（claim／`CONFIRMED`化のACK曖昧、`INSERT`のaffected rows≠1）／`confirmed`：**`CONFIRMED`のduplicateでMedia Verificationが完遂できない（`E9` marker、DB／I/O障害等、C9）**。Finalizerの適用runtime failureの保証境界は12章に従う（本行では定義しない） | 結果不明として扱い、write-ahead済み（`IO_ARMED`）なら既存fail-closedを維持 |
| 503、`none` | claim確立前の基盤障害・epoch invalid・pre-claim binding不一致・multisite。**この requestはclaimを確立せずCoreも呼んでいない**（この requestはmediaを作っていない） | **過去のrequestによるclaim・消費の有無は示さない**。`none`を「identity未消費」「再送してよい」の根拠にしてはならない。再送の可否はIntegration Releaseのdurable stateとserver側のfail-closed（duplicateは新規mediaを作らない）で判断する |
| 400／403／413、`none` | 要求不正・権限不足・body size超過（claim確立前に拒否） | 設定・要求の不備として扱ってよいが、**identityの消費有無までは示さない** |
| `gca_claim_state`を欠く応答、transport error・timeout | この requestの結果が不明 | **消費済みの可能性があるものとして扱う**。消費有無は示されない（8.3節 契約#4）。Finalizerの適用runtime failureの保証境界は12章に従う（本行では定義しない） |

- 注意：現行Python clientは409を`REQUEST_REJECTED`（4xx）、413を`PAYLOAD_TOO_LARGE`、503を`SERVER_ERROR`（5xx）に分類する。HTTP statusだけでは消費有無を判定できず、`gca_claim_state`も**この requestが確立・観測した事実の診断にとどまり、retry authorizationではない**（8.3節 原則(2)）。この分類・`gca_claim_state`とHRR判定の写像、およびretryの可否判断は**Integration Releaseの責務**（6.38では実装しない）。
- **（A14・A15）canonical保証の範囲外の応答**（12.1節 CS-1）の扱いは12.3節 X-1に従う（成功として扱わない）。認証失敗・Core引数検証の失敗がE5になりうる点は12.4節・R-19。
- 6.38時点でGCA-taggedトラフィックは存在しないため、server側の`PROCESSING`がPython HRRと食い違って見える状況は本番では発生しない。

---

## 24. Amendment A1 Change Log（2026-10-06）

| # | 旧Draft | Amendment A1 |
|---|---|---|
| 1 | Status：ARCHITECTURE APPROVED | **撤回**。Architecture Re-review Required。旧Round／Codex回数はhistorical self-recorded context |
| 2 | Scope：Python統合のみOut of Scope、deploymentの扱い不明確 | Consumer-less Foundationと再定義。Python client integration／main.py・Retry・HRR配線／production deployment／orphan cleanup／DB rollback保証／外部epoch anchorをOut of Scope |
| 3 | Background：「Retryが再試行しうる」 | v6.32配線済み（write-ahead／fail-closed／HRR）を反映し、問題を「manual recovery後を含むWordPress側duplicate suppression不足」に再定義（1章） |
| 4 | Identity：image bytes由来`content_identity_digest`をopaque受領 | **撤回**。`article_identity`＋`media_role`＋`content_revision`＋schema version。bytes・attempt・runをkeyに使わない。診断digestは任意・非gate（7.4〜7.6節） |
| 5 | 状態：`CLAIMED→PROCESSING→CONFIRMED`、PROCESSING duplicateの動作未定義 | `PROCESSING`／`CONFIRMED`の2状態に簡素化。atomic claim条件・duplicate動作・crash boundary表・自動reclaim禁止を定義（10章） |
| 6 | HRR：Out of Scopeの1行のみ | server状態機械とPython HRRを別物と明記、6.38では非接続、概念対応表を設計材料として追加（23章） |
| 7 | DB continuity：dual-location anchorによる継続性検証 | **保証範囲を限定**。同一DB内markerではrollback検出不能と明記。rollback／restore／lossy failoverは保証対象外。検出可能なmismatchのみfail-closed（6章） |
| 8 | §8.1「7.1.1 source確認済み」と§17「検証できていない」が矛盾 | 実確認済み／自己記録／未確認に分離（17章）。8.1節の規則はS-1の真偽に非依存と明記。テスト責務をL1/L2/L3に分離（15章） |
| 9 | wire contract未定義（「GCA-tagged識別は実装フェーズで確定」） | `X-GCA-*` header contractを提案（8.2節。確定は21章のArchitecture Gate） |
| 10 | テスト17項目 | T-01〜T-21（必須12項目を含む）、層ごとの責務明記（15章） |
| 11 | 「Working Tree clean」 | 訂正（0章） |

### 24.2 Amendment A2 Change Log（2026-10-06、Review #9のFindingsへの最小修正）

A1の骨格（Consumer-less Foundation／logical identity／`PROCESSING`・`CONFIRMED`の2状態／Stable Authoritative DB Epoch限定／L1-L2-L3分離）は**変更していない**。

| Finding | A1の問題 | A2の修正（節） |
|---|---|---|
| M1 | 25章がレビュアー（Codex）宛ての命令文を含む | 25章を非拘束の記述へ書き直し。レビュアーへの指示・依頼の文言を削除（A4でさらに設計判断の索引へ置き換え） |
| M2 | upload-stateキー（`ArticleMediaUploadRecord.article_identity`）を記事単位と誤記。実体は`as_store_key()`由来のattempt-scoped。安定identity sourceの定義が弱い | 1.2・7.5節を訂正、V-7を追加。7.7節に、Integration Releaseの**必須precondition**（durable永続化・導出元の禁止・受け入れ条件）を追加。6.38は実装しない |
| M3 | claim後のCore結果（4xx含む）の応答が未定義で、400／403と混同されうる | 8.3節に応答表を確定。claim前（`none`）とclaim後（`processing`／`unknown`）を分離、`gca_claim_state`を導入、Core由来statusの透過を禁止。10.6節・23章・T-22を整合 |
| M4 | 3接続が同一のwriter・DB・site・prefix・epochを指すことの規範が無い | 9.3節（Authoritative Binding Contract）を追加。5.3節#7、6.5節#7、10.2節に組込み。T-23 |
| M5 | allowlistの中身が実装時決定 | 8.1節に許可集合を確定（query parameter空集合、raw body、`Content-Type`3種、`Content-Disposition`形式、`X-GCA-*`5種のみ）。実装時の拡張・解釈変更を禁止 |
| M6 | multisiteの検出・強制・検証が無い | 5.5節に実行時の積極確認・確認不能時の拒否を追加。5.3節#8、T-24、U-15 |
| M7 | durability検証が設定値確認（T-09）のみ | T-25（claim／`CONFIRMED`のcommit後のDB再起動・`mysqld`異常終了、L3のみ）を追加。6.2・6.4節を整合 |
| Minor | C6が1行で、original requestと後続requestの区別が無い | 10.6節のC6をC6a〜C6dに分離、C8を追加。T-27 |
| Suggestion | `claim_token`の仕様が無い | 7.8節（CSPRNG・256bit・`CHAR(64)`・非露出）。T-26 |

### 24.3 Amendment A3 Change Log（2026-10-06、Review #10のFindingsへの最小修正）

A2の骨格（Consumer-less Foundation／logical identity／`PROCESSING`・`CONFIRMED`の2状態／claim前後のHTTP contract／Authoritative Binding／closed allowlist／multisite fail-closed／DB restart durability test）は**変更していない**。

| Finding | A2の問題 | A3の修正（節） |
|---|---|---|
| B1 | `gca_claim_state = none`を「identity未消費の証拠」と定義。duplicateでもclaim確立前の検査失敗で`none`になりうるため、消費済みidentityを未消費と報告しうる | **定義を撤回**。`none`は「この requestがclaimを確立せずCoreも呼んでいない」だけを示す。過去のrequestによる消費の有無は保証しない。`gca_claim_state`はretry authorizationではない。各stateの意味を再定義（8.3節）、23章・C6d・T-30を同期 |
| B2 | post-Core Verification前のBinding再確認失敗を「claim 0・Core 0・503 `none`」と規定（claim後の409 `processing`規則と矛盾） | 確認点をR1（pre-claim）／R2（post-claim・pre-Core）／R3（post-Core・pre-Verification）に分割。**claim確立後は`none`へ戻らず**、R2・R3の失敗は`PROCESSING`を保持して409 `processing`。pre-claim（R1）のみ503 `none`。duplicate経路は503 `unknown`（9.3節、5.5節、10.2節）。T-23をa〜eに分割 |
| M-A | 成功応答（media JSON）とWP_Error形式の契約が矛盾、成功時の`gca_claim_state`の位置が未定義 | 成功（201／200）＝media JSON＋top-level `gca_claim_state="confirmed"`のみ追加、error＝WP_Error形式の`data.gca_claim_state`。各stateのshapeを明記（8.3節「応答の形」、12章、T-30） |
| M-B | claim前のbody size上限が未決 | **33,554,432バイト（32 MiB）に固定**。現行契約（最大3840×2160）からの導出と、plugin独自v1上限であることを記録。超過は413 `gca_idempotency_payload_too_large`（`none`・claim 0・Core 0）。U-16を追加（8.1節、10.2節、T-29） |
| M-C | claim後・Core呼出前の捕捉可能な内部障害が応答表に無い | 8.3節の表に行を追加（409 `processing`、Core 0、`PROCESSING`保持）。10.6節のC1をC1a／C1bに分離。T-05・T-28 |
| N1 | `claim_token`が「32バイト以上」だが列は`CHAR(64)` | `random_bytes(32)`相当・ちょうど256bit・64桁hex・`CHAR(64)`を規範化（7.8節、T-26） |
| N2 | 255文字上限を「現行Uploaderと同一」と誤記 | 誤記を削除。長さ上限はplugin独自contractと明記し、現行Uploaderは文字種regexのみであること、現行clientの全filenameが255文字以下かは未確認であることを記録（8.1節、V-8） |
| N3 | MVP Roadmapの確認対象がU-1〜U-12のまま | U-1〜U-16へ更新（MVP_COMPLETION_ROADMAP.md 6.38節） |

### 24.4 Amendment A4 Change Log（2026-10-06、Review #11のFindingsへの最小修正）

A3の骨格（`gca_claim_state`の定義・R1／R2／R3・claim後の`PROCESSING`保持・body size上限の固定・filename contract等）は**変更していない**。

| Finding | A3の問題 | A4の修正（節） |
|---|---|---|
| M1 | 「網羅」とした応答表に、(a)`INSERT`がACK済みだがaffected rows≠1かつduplicate-keyでない、(b)`CONFIRMED` duplicateでclaim読取り成功後にMedia Verificationが失敗、の2ケースが無い | (a)503 `gca_idempotency_claim_indeterminate`／`unknown`、Core 0、再`INSERT`なし。(b)欠落確定→409／`confirmed_inconsistent`、Verification完遂不能→503／`confirmed`。Core再実行禁止。8.3節（表・契約#7・#8）、10.2節（INSERT結果の3分類）、10.6節（C6e・C9）、T-31・T-32 |
| M2 | 成功応答が「通常のCore media JSON」だが、永続化は4項目のみでreplayの他fieldの出どころが未定義 | full Core media JSONは永続化・replayしない。snapshotは4項目のみ。初回201・replay 200とも同一のcanonical payload（5 field）を、**保存済みsnapshotから**構築。Core response全文は初回も透過しない。4項目の検証・snapshot保存・payload構築の順序を規定（8.3節「応答の形」、12章。**A4時点の「Finalizerが検証・保存」という所有者の記述はA5で訂正し、route callbackが所有者**。24.5節）。現行Uploaderとの互換根拠（V-10）。U-17（`source_url`） |
| M3 | 32 MiBが「現行契約の正規出力をすべて受理する」と読める記述（根拠不十分） | **保証の記述を削除**。plugin独自v1 policyと明記し、現行generatorは非空以外を検証しないため正当な入力でも32 MiB超なら413で拒否されうることを明記。上限値・claim前413・T-29は維持（8.1節、V-9） |
| M4 | MVP Roadmapのgate記述が古い（A1承認の要求、「必須12件」） | 「最新のArchitecture Designが独立ReviewでAPPROVED」「設計書でmandatoryと定義された全validation scenarioの完了」へ更新（20章、MVP_COMPLETION_ROADMAP.md 6.38節） |
| M5 | 25章に、レビューの方法・解釈・結論に関するメタ記述が残っていた | 25章を「設計判断・検証の対応表」（D-1〜D-17）へ置き換え。reviewer／toolへの指示と解釈できる記述を削除 |
| N1 | 8.1節の`claim_state`表記 | `gca_claim_state`へ統一 |
| N2 | filename最大長を「未確認」としていた | 現行filename生成contractから最大65文字と算出（60＋5）。「未確認」を削除（8.1節、V-8） |

### 24.5 Amendment A5 Change Log（2026-10-06、Review #12のFindingsへの最小修正）

A4の骨格（canonical 5-field payload・応答表の閉集合・`gca_claim_state`の定義・R1／R2／R3・32 MiB policy・Roadmap Gate等）は**変更していない**。

| Finding | A4の問題 | A5の修正（節） |
|---|---|---|
| A4-B1 | finalizationの所有者・順序が章により矛盾（10章：`CONFIRMED`化・snapshot保存はFinalizerの前／8章・12章：検証・保存はFinalizer／T-16：Finalizerが永続化済みsnapshotを復元）。Core成功後の`source_url`欠落・不正が応答表・C7に無い | **所有者をroute callbackに一本化**し、順序を「1.Core成功→2.Provenance・Verification→3.snapshot 4項目の検証→4.snapshot保存と`CONFIRMED`化（durable ACK確認）→5.success response」に確定（10.4節）。途中失敗は`PROCESSING`保持・409 `processing`、success扱い禁止。**Finalizerは、state変更・検証・DB保存・DB読取りを一切せず、永続化済みsnapshotからcanonical 5-field payloadへ全置換するだけ**（12章）。11.2節に5-way equalityの検証位置を追記。8.3節の応答表に「claim後・Core成功後（snapshot検証失敗）」行、10.6節にC10（snapshot検証失敗）・C11を追加。T-16・T-07を整合、T-33（検証失敗）・T-34（順序・所有者）を追加 |
| A4-M1 | Goal G2「Python側に耐久状態を持たせない」が、7.7節（Integration Releaseがstable identityをdurableに保持）と矛盾して読める | G2を修正：idempotencyの**結果・claim state**（WordPress側が権威、Python側は複製・同期しない）と、**identity**（`article_identity`／`content_revision`の供給元、Integration Releaseの責務で永続化が必須）を別の状態として分離（3章） |
| A4-M2 | T-23eが静的な別schema構成だと、R1で拒否されclaimが作られないため、期待結果（`PROCESSING` row保持・409 `processing`）に到達できない | T-23eを、**R1・R2を通過させ、Core成功後のR3の時点でのみBinding mismatchを注入するfault injection**に修正（期待：`PROCESSING` row保持・`CONFIRMED`化なし・409 `processing`）。静的な別schema構成はT-23f（R1で503 `none`・claim 0）として分離（15章） |
| Minor 1 | 用語集に`claim_state`の旧表記 | `gca_claim_state`へ統一（4章） |
| Minor 2 | 23章が503 `confirmed`をFinalizer失敗としてのみ説明し、C9が無い | 503 `confirmed`に、Finalizerの全置換失敗（C5）と`CONFIRMED` duplicateのVerification完遂不能（C9）の両方を記載（23.2節） |
| Minor 3 | T-29のL3（plugin 413）が、下位層のbody上限の設定を前提にしていない | T-29のL3に、下位層（WordPress／PHP／web server）のbody上限を33,554,433バイトより大きく設定でき、設定が有効であることのevidenceを前提条件として追加。下位層が先にrejectする構成はplugin 413の証明として扱わない。U-16・18章のチェックリストも整合（15章、17章） |

### 24.6 Amendment A6 Change Log（2026-10-06、Review #13のFindingsへの最小修正）

A5の骨格（route callbackがvalidate→snapshot保存→`CONFIRMED`化のdurable ACK→success、Finalizerはroute callbackの完了後の機械的置換、canonical 5-field payload、R1／R2／R3等）は**変更していない**。

| Finding | A5の問題 | A6の修正（節） |
|---|---|---|
| M1 | Finalizerが置換するのはdataのみで、必須のHTTP status（201／200）を置換しない。信頼するrequest-local snapshotに完全性の束縛が無く、pre-Finalizerのcallbackによるstatus変更や、形式の正しい別contextへの差替えを検出できない | **Finalizerをcanonical success responseの最終所有者**とし、**dataとHTTP statusの両方を置換**（first success＝canonical 5-field payload＋201、confirmed replay＝＋200）。request-local contextを**plugin-private・write-once**とし、**exact `WP_REST_Request`のinstance identity／server-sideのidempotency identity／success mode（first・replay）／expected HTTP status／durable snapshot**に束縛。Finalizerは置換の前に束縛を確認し（context存在・request instance同一・`X-GCA-*`から再導出したkeyとの一致・modeとstatusの整合・snapshotの型）、missing／不一致／不正ならcanonical successを返さず503 `confirmed`でfail-closed（status・dataとも置換）。**偶発的なcontext混入の防止であり、co-resident malicious codeは脅威モデルに加えない。暗号署名・新規の永続状態は設けない**（12章）。10.4節・11.2節・8.3節・C5・T-07・T-16・T-30・T-34（c1〜c7）を同期。U-18を追加 |
| M2 | 必須T-22が「claim後はすべて409（ACK曖昧のみ503）」と書かれ、T-07・T-32・応答表（Finalizer failure＝503 `confirmed`、`CONFIRMED` duplicateのVerification不能＝503 `confirmed`、confirmed inconsistency＝409）と矛盾 | **旧一般化を削除**し、T-22を8.3節の正本応答表に従う**matrix test**（全行を条件注入→status／error code／`gca_claim_state`／Core呼出回数で検証）へ変更。PROCESSING系＝409 `processing`、ACK曖昧＝503 `unknown`、Finalizer failure＝503 `confirmed`、`CONFIRMED` duplicateのVerification不能＝503 `confirmed`、confirmed inconsistency＝409 `confirmed_inconsistent`を明示（15章） |
| M3 | 実装開始前に完了すべき18章が、実装後でなければ確認できないL1 golden-vector実装適合を含み、gateが循環 | 該当項目を18章から削除し、**20章の実装フェーズgate**へ移動（T-21）。18章の範囲を「実装前に確認可能なarchitecture・environment・source前提」に限定する旨を明記。18章の他の項目のうち、Finalizer登録後の確認を含むものと、T-29のL3前提を、実装前に確認できる形（source・登録状況・環境）へ書き換え（18章、20章） |

### 24.7 Amendment A7 Change Log（2026-10-06、Review #14のFindingsへの最小修正）

A6の骨格（Finalizerがdataとstatusの両方を置換・request-local contextの5要素束縛・route callbackの順序と所有者・T-22のmatrix test化・18章と20章のgate分離）は**変更していない**。

| Finding | A6の問題 | A7の修正（節） |
|---|---|---|
| B1 | Finalizerが、「successのcontextが失われた」ことと「error経路でcontextが意図的に無い」ことを区別できない（contextはsuccess時にのみ作られ、Finalizerはconfirmed／replayのcontextがあるときにのみ作用する一方、context欠落は503 `confirmed`とされていた）。応答表とT-34(c1)が実装不能 | **発動判定をcontextの有無ではなくresponse classで規定**。GCA-tagged requestの最終応答に対し、**class A（2xx）**：valid success contextを必須、valid→canonical 5-field payload＋first＝201／replay＝200、欠落・不一致・不正→canonical success禁止・503 `unavailable`／`confirmed`（E9）。**class B（non-2xxで、canonical error表E1〜E9のいずれかに完全一致）**：contextを要求せずそのまま通す。**class C（non-2xxでcanonical errorとして検証できない）**：503 `unavailable`／`unknown`（E5）へfail-closed（identity未消費を意味せず、retry authorizationでもない）。context欠落は「2xxなのにvalid success contextが無い」ことでのみ検出し、error応答のcontext無しは正常（12章、8.3節、C5、T-22(10)、T-34(c1)・(d)）。R-18を追加 **（この分岐は、A8で廃止・置換された。24.8節）** |
| M1 | 23章とD-4に旧一般化「claim後の失敗はすべて409 `processing`」が残り、応答表の503 `unknown`・`confirmed`と矛盾 | 23章の該当行とD-4を、応答表・canonical error表が正本であり、claim後でも409 `processing`／503 `unknown`／503 `confirmed`／409 `confirmed_inconsistent`があり得ることへ統一。8.3節の契約#1・10.2節の一般則にも「この規則の対象」を明記（8.3節、10.2節、23章、25章） |
| N1 | error messageは固定文言とされるが、正準な文字列とtest oracleが無く、応答body契約が閉じていない | **canonical error表（E1〜E9）を8.3節に正本化**：status・error code・message（固定ASCII文字列）・`gca_claim_state`の組合せの閉集合。自由文・Core由来messageは透過しない。T-22で全9組のmessage完全一致を検証。Finalizerのclass B判定もこの表の完全一致で行う（8.3節、T-22）（**このclass B判定はA8で廃止**） |

### 24.8 Amendment A8 Change Log（2026-10-06、Review #15のFindingsへの修正）

A7の基盤（canonical error表E1〜E9・固定message・exact-key・route callbackの順序と所有者・18章と20章のgate分離等）は**維持**した。B1は設計方針の変更（response class分岐の廃止）を伴う。

| Finding | A7の問題 | A8の修正（節） |
|---|---|---|
| B1 | response class分岐は網羅的だが、意味として成り立たない。durable successの応答が2xx以外へ変えられるとclass B／Cとして扱われcanonical successを復元できない。逆に、pre-callbackの短絡・errorが2xxへ変えられるとsuccess contextが無く、503 `confirmed`と誤って応答する。R-18は部分的な認識にとどまる | **response-class 3-way dispatchを廃止**。plugin control path（ラップした`permission_callback`とroute callback）が、各GCA requestについて**plugin-private・write-once・request-localのauthoritative outcome marker**（`SUCCESS_FIRST`／`SUCCESS_REPLAY`／`E1`〜`E9`）を、出口でちょうど1回確定する。**Finalizerはpre-Finalizerの応答のstatus・data・種別を判断材料にせず、markerだけから最終response（statusとdata）を新規構築・完全置換する**。`SUCCESS_FIRST`は`CONFIRMED`のdurable ACK後のみ、`SUCCESS_REPLAY`は`CONFIRMED` row読取り・Binding再確認・Verification成功後のみ設定し、いずれもdurable snapshotを保持。E系はそのdecision pointで設定（route到達前のvalidation／capability／environment failureもcontrol pathが設定）。markerはexact request instanceに束縛、二重設定・欠落・不正・別request markerはE5へfail-closed。markerは新しいdurable stateではない。co-resident malicious codeは脅威モデル外のまま。pre-Finalizerのcallbackがsuccess→error、error→success、1xx／3xx、任意bodyへ変更してもmarkerから復元（12章、8.3節、10.3・10.4節、C5・C5b、T-07・T-16・T-22(10)(11)・T-34）。**R-18を解消**（「2xx＝durable confirmed」前提を廃止）。R-19（control pathに到達しないGCA request＝E5）・U-19を追加 |
| M1 | `X-GCA-Identity-Schema`の不一致に、E1（400）とE4（503）の2つの結果が併存 | client供給値の不一致は**E1／400に統一**。server内部のschema／DB／epoch／configurationの不一致は**E4／503**として区別（6.5・7.4・8.2・8.3節、T-09・T-18、D-23） |
| M2 | class Bの判定がE1〜E9の組と`data.status`のみで、top-levelと`data`のkey集合を確認しない | Finalizerが**markerからresponseを新規構築**し、**許可されたexact key set（成功＝ちょうど5 key、error＝ちょうど3 key・`data`はちょうど2 key）だけ**を出力する契約とした（12章）。incoming responseのkey集合の判定に依存せず、余分なfieldは最終responseに残らない。T-22(11)・T-34(d5)で検証 |
| N1 | class Cの1xx・3xxのうち、必須テストが3xxのみ | T-34(d3)(d4)に1xx・3xxを追加。valid markerがあればmarkerのcanonical outcomeへ復元し、marker無し・不正ならE5へfail-closed |

### 24.9 Amendment A9 Change Log（2026-10-06、Review #16のFindingsへの最小修正）

A8のmarker方式（plugin-private・write-once・request-localのauthoritative outcome marker、markerだけからの新規構築、exact-key contract、E1／E4の分離等）は**維持**した。

| Finding | A8の問題 | A9の修正（節） |
|---|---|---|
| B1 | Finalizerの失敗の契約が自己矛盾：valid `SUCCESS_*` markerは201／200に一意に対応しwrite-onceだが、Finalizerが応答を置換できない場合は同じ応答をE9へ置換するとされ、第2の仕組みもmarker遷移も未定義。C5・T-07が実装不能 | **案Bを採用**。valid markerからのcanonical response（`SUCCESS_FIRST`→success＋201、`SUCCESS_REPLAY`→success＋200、`E1`〜`E9`→表の該当行）の**選択・構築は、totalかつ一意**（markerのみの純粋な関数）で、**markerはFinalizerの動作で変更しない**。**Finalizerによる応答への「適用そのもの」のruntime失敗**は、**E9へのfallbackを試みず、canonical responseを保証せず、`gca_claim_state`を欠くnon-canonical／transport／runtime failureとして扱う**（8.3節 契約#4）。durable claim・markerは不変、clientはretry可否をその応答だけから判断しない。**E9は、plugin control pathが`E9` markerを明示的に設定する場合（`CONFIRMED` duplicateのVerification不能）のみ**。「Finalizer failure→E9／confirmed」を8.3節の応答表・E9の用途・12章・C5・T-07・23章・D-4・D-20・R-17・R-18から削除・訂正。U-18（適用能力の実装前確認）は維持。R-20を追加 **（A10で訂正：「`gca_claim_state`を欠くnon-canonical…として扱う」は廃止。24.10節）** |
| M1 | 必須T-22(4)が「marker・context欠落・束縛不一致・不正・置換失敗のすべてがE9／`confirmed`」という旧い期待を保つ | T-22(4)を、marker欠落・不正・二重設定・別request・束縛不一致→E5／`unknown`、valid `E9` marker→E9／`confirmed`、valid markerからの構築は失敗しない、**Finalizerの適用runtime failureはcanonical E1〜E9 oracleの対象外でT-07の別ケースで検証・記録（A12でT-07は手順形式に変更。現行の検証方法はT-07を参照）**、へ同期（15章） |
| N1 | D-17・R-5がU-1〜U-18のまま | U-1〜U-19へ同期 |
| N2 | 用語集のFinalizer定義が12章と不整合 | 「全GCA outcomeについて、authoritative markerからcanonical HTTP responseを構築・適用する最終投影層。durable state変更・DB I/Oなし」へ同期。authoritative outcome markerの用語を追加（4章） |

### 24.10 Amendment A10 Change Log（2026-10-06、Review #17のFindingsへの修正）

A9の骨格（valid markerからのcanonical response選択・構築はtotalかつ一意、markerはFinalizerで変更しない、E9へのfallbackなし、E9はE9 markerのみ）は**維持**した。

| Finding | A9の問題 | A10の修正（節） |
|---|---|---|
| B1 | 適用失敗の境界が、保証できない内容を保証している：(1)適用失敗後の応答が`gca_claim_state`を欠くこと・canonicalに見えないことは、部分適用や元の応答の残存により保証できない、(2)C5・T-07が全valid marker（E1〜E9）に「`CONFIRMED`不変・replay可能」を要求（E1〜E4はclaim無し、E5・E6は不確定、E7は`PROCESSING`）。同一契約が10か所以上で言い換えられ、直し漏れが矛盾を生んだ | **12章を唯一の正本**とし（「Finalizerの適用runtime失敗の保証境界」）、他章は参照のみに整理。**適用失敗後の応答内容は未定義**（canonical／non-canonical・`gca_claim_state`の有無・元のresponseの残存を保証しない）、clientはそのresponseだけからstate・retry可否を判断しない、marker・durable stateは不変。**outcome別のdurable state**：`SUCCESS_FIRST`／`SUCCESS_REPLAY`／`E8`／`E9`＝`CONFIRMED`系（後続duplicateで状態確認・replay）、`E7`＝`PROCESSING`、`E5`／`E6`＝不確定、`E1`〜`E4`＝claim未作成。C5・T-07をoutcome別oracleへ修正し、「全markerで`CONFIRMED`不変・replay可能」を削除。8.3節の応答表の該当行・契約#4、10.6節のC5・C5b・C11、23章、D-4・D-20、R-17・R-20を、12章への参照へ置換。A9の「`gca_claim_state`を欠く応答として扱う」は廃止（12章・15章・17章・Roadmap） |
| M1 | 規範部分に「Finalizer failure→503 `confirmed`」の割当てが残存（8.3節のerror形状、契約#3、23章）。Roadmap／Change Recordにも保証できない主張 | 8.3節のerror形状（`E9` markerの`confirmed`）、契約#3（`E9` markerを含む「結果不明」。Finalizerの適用失敗は12章に従う）、23章の2行を訂正。Roadmap／Change Recordの記述を訂正。grepで規範部分に旧記述が残らないことを確認（履歴の記述は「A10で廃止」と明示） |

### 24.11 Amendment A11 Change Log（2026-10-06、Review #18のFindingsへの最小修正）

A10の骨格（Finalizerの適用runtime failureの保証境界を12章に置く、応答内容は未定義、marker・durable stateは不変、E9へのfallbackなし）は**維持**した。

| Finding | A10の問題 | A11の修正（節） |
|---|---|---|
| M1 | 12章が「唯一の正本」になっていない。8.3節・C5・T-07・索引・リスク・Roadmapに、適用失敗時のoutcome別stateやrecoveryの再記述が残り、R-17（「E5でも`CONFIRMED`不変・replayで回復」）とC5b・12章（claimの有無は不確定）が矛盾 | **12章以外から、outcome別のstate・recoveryの説明を削除**し、「Finalizerの適用runtime failureの保証境界は12章に従う」という参照のみへ整理：8.3節の応答表の行・E9行・契約#4、C5（全列を「12章に従う」）・C5b・C11、23章の2行、D-4・D-20、R-17（「E5でも`CONFIRMED`不変・replay可能」と読める記述を削除）・R-20、`ROADMAP.md`、`MVP_COMPLETION_ROADMAP.md`（6.38節のStatus・v1.6の説明・Change Record。履歴の累積的な再記述も圧縮）。12章の表のみがoutcome別のstateを定義する |
| M2 | T-07にE1〜E4向けの正確なoracleと層の割当てが無い（E1〜E4は「このrequestが新しいclaimを作らなかった」だけを意味し、既存claimはなし・`PROCESSING`・`CONFIRMED`のいずれもありうる）。marker不変をL3に割り当てているが、L3から観測する手段が無い | T-07を精密化：(a8)E1〜E4では**既存claimを、なし／`PROCESSING`／`CONFIRMED`の3通りに分けて事前に用意**し、適用失敗の前後で既存のdurable stateが不変で、後続requestがその状態に応じた通常の処理（なし→新規claim、`PROCESSING`→409 `processing`、`CONFIRMED`→replayまたはE8／E9）になることを検証。**層分離**：【L1／L2】request-local・非公開のmarker不変・write-once・Finalizerがmarkerを変更しないこと・純粋な関数でDB I/Oを持たないこと、【L3】durable DB stateと後続requestの挙動のみ。**L3から非公開markerを直接観測する前提は禁止**。SUCCESS_FIRST／SUCCESS_REPLAY／E8／E9／E7／E5／E6を12章のstate分類に従って個別化。12章の表（E1〜E4の行、E8・E9の行の分離）も同期（12章・15章） |
| N1 | T-32が3分岐すべてで「回復後のreplayは200」を期待。E8（attachment欠落・不一致が確定）は明示的な修復が必要 | T-32を分岐ごとに修正：E8は明示的な修復が完了するまで409 `confirmed_inconsistent`を維持（環境が回復しただけでは200 replayにならない）。(b)(c)は環境の回復後、attachmentが整合していれば200 replay（15章） |
| N2 | 26章の見出しが「Amendment A9時点」のまま | 「Amendment A11時点」へ更新（26章） |

### 24.12 Amendment A12 Change Log（2026-10-06、Review #19のMajor M1だけへの修正）

A11の骨格（12章がFinalizerの適用runtime failureの唯一の正本、T-07の層分離、E8の修復境界）は**維持**した。契約の内容は変更していない。

| Finding | A11の問題 | A12の修正（節） |
|---|---|---|
| M1 | 12章が唯一の正本になっていない。C11が、Finalizerの置換を含む時間帯に`CONFIRMED`とreplay回復を独立に割り当て、T-07が応答・marker／state・outcome別の後続の確認を繰り返し、T-22が未定義応答・E9 fallbackなしを繰り返し、ROADMAPが同趣旨を要約。現在は12章と一致するが、純粋な参照ではない | **12章の表の各行に識別子F-1〜F-6を付与**（契約内容は不変）。**C11**から適用failureの記述を削除し、適用failure以外の障害のみを扱う行にして「適用failureは12章 F-* に従い本行では扱わない」とした。**T-22**から適用failureの説明を削除し「T-22の対象外。12章 F-*に従い、T-07で検証」のみ。**T-07**は契約を再掲せず、「F-*ごとに、(1)事前状態を用意（F-6はなし／`PROCESSING`／`CONFIRMED`の3通り）、(2)適用failureを注入、(3)観測結果が当該F-*と一致することを検証」という手順の形式とし、T-07固有の責務（【L1／L2】marker内部状態、【L3】durable DB stateと後続request、L3からprivate markerを直接観測しない）のみを残した。**ROADMAP.md**は履歴の累積記述を圧縮し、契約の具体的内容を削除して、12章への参照とArchitecture statusのみにした。MVP_COMPLETION_ROADMAPのStatus・Change Recordも同様 |

### 24.13 Amendment A13 Change Log（2026-10-06、Review #20のM1・Minorだけへの修正）

新しい設計判断・scope変更は行っていない。A12を維持した。

| Finding | A12の問題 | A13の修正（節） |
|---|---|---|
| M1 | 26章のR-10が「claim後の失敗を一律409 `processing`へ正規化する」と広く書かれ、8.3節の正本matrix（claim後の503 `unknown`／`confirmed`を含む）と矛盾。12章が応答内容を未定義とするFinalizerの適用失敗にも409を割り当てうる（以前に閉じた「claim後はすべて409」の再発） | R-10を「claim確立後のHTTP outcomeは8.3節の正本matrixに従う」という参照のみに訂正。Finalizerの適用runtime failureは12章の保証境界に従う（26章）。**全文の確認**：「すべて409」「常に409」「一律409」等の一般化、claim後を409へ一般化する同義表現、古い`Amendment A*時点`の版表記、8.3節・12章と競合する再記述をgrepで確認し、規範部分に残っていたのはR-10と26章の見出しのみで、他は履歴（変更ログ）または旧一般化を否定する記述（D-4・8.3節契約#1など）であることを確認した |
| Minor | 26章の見出しが「Amendment A11時点」のまま | 現行Amendment（A13）へ更新（26章） |

### 24.14 Amendment A14 Change Log（2026-10-06、Implementation Start Validationで判明した設計前提の誤りの訂正）

**契機**：A13（Review #21 APPROVED、commit `2513ae5`）に対し、18章のImplementation Start Validationを7.1.1 tag sourceで実施し、**承認済みArchitectureの前提誤り**（U-18・U-2・U-19）を検出した（19章）。**Release scope・MVP COMPLETEは変更していない**。

| 項目 | A13の問題 | A14の修正（節） |
|---|---|---|
| 1. Final projection（U-18） | 投影を`rest_pre_echo_response`に置く前提が偽 | 12.1節（O-*・P-1〜P-5）へ再設計。用語集・5.3節・10.4節・T-16・D-18・D-20・R-17・R-18を同期 |
| 2. Header契約 | Core media response由来headerの扱いが未定義 | 12.2節（H-1〜H-3）。U-20、T-35 |
| 3. 投影後の改変点（U-2） | 「Finalizer後に改変点ゼロ」が偽 | 12.3節（X-1〜X-10）。S-3を訂正。T-38 |
| 4. Marker／control path（U-19） | control pathが全経路を網羅するという前提が偽 | 12.4節（B-1〜B-8）。M-5。T-17・T-34(c8)・T-36 |
| 5. Batch | 設計に無い | 12.5節（BT-1〜BT-4）。U-21 |
| 6. Ledger／Checklist | U-18・U-2・U-19が旧前提のまま | V-11〜V-15、S-1・S-3、U-2・U-18・U-19の改訂、U-20・U-21、17.5節、18章の同期 |
| 7. Single-source | — | 12章を正本とし、他章は識別子で参照（A15でさらに整理） |

### 24.15 Amendment A15 Change Log（2026-10-06、Review #22のB1／M1〜M3／N1・N2への修正）

**契機**：A14テキストに対するReview #22（NOT APPROVED、Blocking 1／Major 3／Minor 2）。A14を基礎とし、新しい設計判断・scope変更は行っていない。**契約の内容は12章が正本であり、本ログは、何を変更したかを識別子で示すのみ**。

| Finding | 修正（正本の位置） |
|---|---|
| B1 | permission_callbackのphase：**PP-1〜PP-6**を新設（12.4節）**（A16で廃止。24.16節）**。M-5を、PP-*への参照へ整理（12章 marker確定規則）。**B-1〜B-8の表**に、permission_callbackの呼出（primary／passive）の列を追加。T-36を改訂（B-5〜B-7がpassive呼出でE3等へ変化しないこと）。U-19を改訂 |
| M1 | **CS-1**を新設（12.1節）。8.3節の応答表・canonical error表・T-22・T-34の閉集合／exact-keyの範囲をCS-1に同期 |
| M2 | **投影eligibility（P-2、PE-1〜PE-3）**を新設（12.1節）。BT-1・BT-4を改訂（12.5節）。**U-22**を新設。T-37を新設 |
| M3 | 8.3節・5.3節・8章・8.1節・用語集・17章（V-11〜V-14、S-3、U-*）・18章・19章・24.14・25章・26章・0章・Roadmapの再記述を、12章の識別子による参照のみへ整理 |
| N1 | `set_status()`（`:477`）と`status_header()`の呼出（`:1910`）を区別（12.1節 O-8・P-1、V-11） |
| N2 | `rest_envelope_response`（`:861-885`）を12.3節 X-1へ追加 |
| 台帳・テスト | T-35〜T-38（旧T-37→T-38へ改番）、U-22の新設（A16で廃止）、20章・両Roadmapの範囲更新 |

### 24.16 Amendment A16 Change Log（2026-10-06、Review #23のB-01／M-01〜M-04／N-01への修正）

**契機**：A15テキストに対するReview #23（NOT APPROVED、Blocking 1／Major 4／Minor 1）。A15を基礎とし、新しい設計判断・scope変更は行っていない（ただし、B-01・M-01の解消のために、**permission_callbackを置換しない**こと、**GCA capability判定をroute callbackの先頭へ置く**こと、**PE-3をeffective method POSTへ変更し、top-level識別を廃止する**ことを、設計の簡素化として採用した）。**契約の内容は12章が正本であり、本ログは変更点を識別子で示すのみ**。

| Finding | 修正（正本の位置） |
|---|---|
| B-01 | **PP-1〜PP-6（permission phase）を廃止**。`permission_callback`は置換せずCoreのまま、markerに関与しない。control pathは**route callbackだけ**（12章、12.4節）。**GCA capability判定をroute callbackの先頭へ**（E3は、Core権限を通過したuserのGCA capability不足に限定。Coreの権限拒否はB-9でE5）。B-1〜B-9・T-36・T-34(c8)の削除・V-13・U-19を同期 |
| M-01 | **SP-1〜SP-3**を新設（12.1節）：idempotency safetyはdispatch文脈に依存せずroute callbackが適用、投影はHTTP正準化専用、投影が行われない文脈（内部`rest_do_request()`）でも安全性は保証。**PE-3（`is_dispatching()`によるtop-level識別）とU-22を廃止**。BT-1・BT-4を改訂（12.5節）。T-37を改訂 |
| M-02 | **PE-3＝effective methodがPOST**（12.1節 P-2）。B-4を改訂：READABLE handlerへ一致するGET／HEAD／overrideの経路を追加し、投影対象外とした（12.4節）。T-36 |
| M-03 | 8.3節の応答の形の冒頭に適用範囲（CS-1）を追加。T-30の対象をCS-1の範囲に限定。T-22・T-34も同様 |
| M-04 | 8.3節・10.4節・11.2節・D-18・D-20・D-22・T-16・T-30・T-34・T-36・T-37の再記述を、12章への参照へ整理 |
| N-01 | `status_header()`の関数本体と、7.1.2との同一性を、Architectureの前提から外した（V-11、12.1節、17.5節）。規範の前提は、7.1.1 tagの引用したcall-siteだけ |
| 台帳 | U-19の改訂、U-22の廃止、T-36・T-37の改訂、17.5節・18章・両Roadmap（U-1〜U-21、T-01〜T-38）の同期 |

### 24.17 Amendment A17 Change Log（2026-10-07、Review #24のM-A16-01／M-A16-02／N-A16-01への修正）

**契機**：A16テキストに対するReview #24（NOT APPROVED、Blocking 0／Major 2／Minor 1）。A16を基礎とし、**対象はReview #24の3 Findingだけ**。scope変更・新しいテスト（T-ID）の追加・WordPress source evidenceの追加は行っていない。method境界の確定内容は、A17の作業指示で定めたものである。**契約の内容は12章が正本であり、本ログは変更点を識別子で示すのみ**。

| Finding | 修正（正本の位置） |
|---|---|
| M-A16-01 | **MO-1〜MO-4を12.1節に新設**（effective method基準・effective non-POSTはCore Native・effective POSTでのoverride controlはE1・一般化の禁止）。**8.1節の表（HTTP method行・method override control行・末尾の注）、12.1節 P-2のPE-3・CS-1(c)、12.4節 B-4、T-17・T-36**を、MO-*への参照へ同期。「method override requestは常にE1」という一般化を削除 |
| M-A16-02 | **T-34・T-36・T-37**から、marker・E-code・projection・batch／internal dispatchの期待結果の再記述を削除し、oracleを12章の識別子のみとした。**同種の再記述を再点検し、T-16・T-22(4)(10)(11)・8.3節のmarker欠落行・10.3節・10.4節 手順5・D-4・R-18・R-19**も、12章の識別子による参照へ整理した（8.3節の応答表・canonical error表は、E1〜E9の内容の正本として維持） |
| N-A16-01 | **D-17**をU-1〜U-21へ同期（U-22は廃止済み・non-actionable gapで、active validation inputに含めない。17章 U-22・17.5節の表にも明記）。**17.5節の見出し**、**18章の注記**、**26章の見出し・R-5**をA17現在へ同期。**Roadmap・status・change log**のAmendment番号をA17へ同期（過去のA14／A15の記述は、historical recordとして残し、current statusと区別した） |
| source依存の主張 | **17.6節を新設**：Review #24で独立に照合できなかった主張を、verifiedへ格上げせず、architecture assumption／validation-requiredとして明示。**18章のチェックリストに項目を追加**し、Implementation Start Validation gateに残した |

### 24.18 Amendment A18 Change Log（2026-10-07、Review #25のM-25-01／M-25-02／N-25-01への修正）

**契機**：A17テキストに対するReview #25（NOT APPROVED、Blocking 0／Major 2／Minor 1）。**対象はReview #25の3 Findingだけ**。scope変更・新しいT-IDの追加・Review #25でCLOSEDとなったA17項目（M-A16-01・M-A16-02・N-A16-01）の再変更は行っていない。**契約の内容は12章が正本であり、本ログは変更点を識別子で示すのみ**。

| Finding | 修正（正本の位置） |
|---|---|
| M-25-01 | **12.1節 RD-1〜RD-7を新設**：`rest_post_dispatch`の4つのcall-site（top-level／embed／batch子／preload）の分類、全call-site共通のFinalizerの安全なno-op（RD-5。eligibleでない・第3引数が`WP_REST_Request`でないときは`$result`をそのまま返す）、request-affecting hook（`rest_request_from_url`等）のtopology検証とunsupported topology（RD-6）、call-site網羅の根拠と改訂条件（RD-7）。**P-4・P-5・CS-1(c)・SP-3・BT-4・O-6・5.3節#4・12.3節の注・U-18・T-37**を同期 |
| M-25-02 | **`status_header()`の本体が`functions.php:1463-1492`に存在する**ことへ訂正（12.1節の根拠・O-8・V-11・17.6節）。**12.3節 X-11を新設**（`status_header`filter、numeric statusとstatus line文字列の区別、topology検証、unsupported topology＝Epoch invalid、wire上のstatus lineは保証外、runtime-only）。**5.3節#5・X-2・U-2・U-20・T-35・T-38・18章**を同期。Core既定の`rest_post_dispatch`callbackに`connectors.php:753`があることを追記（O-6・P-3） |
| N-25-01 | **T-37にdispatch文脈の変種（C1〜C5：top-level HTTP／内部`rest_do_request()`／batch子／embed／preload）**を追加。method／override controlを、文脈ごとのsource上の扱い（`serve_request()`だけがoverrideを解釈する）に合わせて与える。oracleはMO-*・SP-*・BT-*・CS-1・RD-*のID参照のみ |
| 台帳 | **V-16を新設**（provenance、evidence 14ファイルとtagアーカイブのbyte一致、`src/`全体の走査によるcall-site・hookの網羅確認とその限界）。17.6節に、Review #25の結果とruntime未検証の明記を追加。D-30・R-5・R-21・26章の見出しを同期。**U-1〜U-21（U-22は廃止済み）・T-01〜T-38の範囲は変更していない** |

**補記（Review #26 APPROVED後のdocs sync。2026-10-07）**：Review #26（APPROVED、Minor 2）への対応は**文書の同期のみ**で、**契約・ID・scope・テスト・台帳の内容は変更していない**。(1)**V-16(4)**を、canonical evidence（14ファイル）に`connectors.php`が含まれないこと、auxiliary evidenceが供給して検証済みであること、Review #26でCodexが両evidence rootをreadして(3)をsource照合したこと、に同期。(2)**現在地表記**：17.5節の見出しを「A18現在」へ、MVP Roadmapのcurrent statusの日付を2026-10-07へ同期。0章のStatus・Review表・19章・両Roadmapのstatusを「Review #26 APPROVED」へ同期（履歴としてのA14〜A17の記述は維持）。**このAPPROVEDは、設計文書の内部整合性とsource上の事実の判定であり、runtime項目は未検証**（17.6節）。

**補記（Architecture Human Gate ACCEPT記録。2026-10-07）**：ユーザーが21章の5論点を個別にACCEPTした。記録は**21章の「ACCEPT記録」**、0章のStatus、20章のArchitecture Gate（「Human Gate（21章）の承認を得る」と、Review #26で到達した「APPROVED」の2項目をチェック）、両Roadmapのstatusに反映した。あわせて、**`f719908`でcommit・push済みとなった現在地**に合わせ、**0章のBaseline**と**21章末尾**の「未commit」という現在地表記を同期した（履歴としての旧記述は変更していない）。**設計の契約・scope・ID・テスト・台帳の内容は変更していない**。ACCEPTは、Implementation Start Validationのruntime項目のPASSでも、実装開始の許可でもない。

---

## 25. 設計判断・検証の対応表（Decision／Validation Index）

本章は、本書の主要な設計判断と、その根拠・検証箇所の対応表である。内容の正本は各節であり、本章は索引にとどまる。

| # | 設計判断 | 正本の節 | 検証（テスト・台帳・チェックリスト） |
|---|---|---|---|
| D-1 | logical identityは`article_identity`＋`media_role`＋`content_revision`＋schema version。image bytes・`attempt_ordinal`・`root_run_id`をkeyにしない | 7.4・7.6節 | T-10・T-11・T-21 |
| D-2 | stable identity sourceはIntegration Releaseの必須precondition。6.38は実装しない | 7.5・7.7節、V-7 | Integration Releaseで検証（R-1） |
| D-3 | 状態は`PROCESSING`／`CONFIRMED`の2つ。`INSERT`のwinnerのみがCoreを呼ぶ。stale `PROCESSING`の自動reclaimを禁止 | 10.1〜10.5節 | T-01〜T-08・T-12 |
| D-4 | claim後の失敗は`none`へ戻らない。**応答は8.3節の応答表・canonical error表（E1〜E9）が正本**であり、「claim後の失敗はすべて409」とは規定しない。marker・Finalizerの適用runtime failureの契約は12章に従う | 8.3・10.2・10.6節、12章 | T-22・T-27・T-28・T-31 |
| D-5 | `gca_claim_state`は診断情報であり、identity未消費の証拠でもretry authorizationでもない | 8.3節 | T-30 |
| D-6 | 成功応答は、初回・replayとも同一のcanonical payload（5 field）。Core response全文は透過・永続化しない | 8.3・12章、V-10 | T-30 |
| D-7 | `CONFIRMED` duplicateはCoreを再実行しない。Verification完遂不能は503 `confirmed`、欠落確定は409 `confirmed_inconsistent` | 8.3・10.3節、C9 | T-32 |
| D-8 | Authoritative Binding（R1／R2／R3）。不一致・確認不能はfail-closed | 9.3節 | T-23a〜T-23f |
| D-9 | closed allowlist（query parameter空集合、raw body、`Content-Type`3種等）を設計時点で確定 | 8.1節 | T-17・T-18 |
| D-10 | body size上限は33,554,432バイトのplugin独自v1 policy。正当な画像でも超過すれば413で拒否されうる | 8.1節、V-9 | T-29 |
| D-11 | filenameは文字種regex＋255文字以下（plugin独自）。現行生成filenameの最大長は65文字 | 8.1節、V-8 | T-17 |
| D-12 | multisiteは実行時に積極確認し、確認不能なら実行しない | 5.5節 | T-24 |
| D-13 | 保証範囲はStable Authoritative DB Epoch内に限定。rollback／restore／lossy failoverは保証しない。同一DB内markerでrollbackを検出できない | 6章 | T-09・T-25 |
| D-14 | `claim_token`はCSPRNGで生成するちょうど32バイト（64桁hex、`CHAR(64)`）。非露出 | 7.8節 | T-26 |
| D-15 | 6.38はPython HRR・write-ahead・`article_media_upload_state`と接続しない。Consumer-less Foundation | 2章・23章 | Integration Releaseで検証 |
| D-16 | テスト責務をL1／L2／L3に分離。L2／L3のevidenceが得られるまで完了を主張しない | 15章・20章 | — |
| D-17 | 未検証のWordPress／PHP／MySQL事実は17章の台帳で分離し、18章のImplementation Start Validationで確認・pinする | 17・18章 | S-1・U-1〜U-21（U-22は廃止済みで対象外。17.6節の未照合の主張を含む） |
| D-18 | finalizationの所有者はroute callback（状態の検証・保存・`CONFIRMED`化）。Finalizerの責務は12章 | 10.4・12章 | T-16・T-33・T-34・T-35 |
| D-20 | 最終responseの根拠はauthoritative outcome marker。marker・投影・適用runtime failureの契約は12章 | 12章 | T-07・T-16・T-34 |
| D-22 | errorの組合せはcanonical error表（8.3節）が内容の正本。適用範囲はCS-1（12.1節）。**A7のresponse class 3分岐は廃止** | 8.3・12章 | T-22・T-34 |
| D-23 | `X-GCA-Identity-Schema`のclient供給値の不一致はE1（400・`none`）。server内部のschema／DB／epoch／configurationの不一致はE4（503・`none`）。両者を区別する | 7.4・6.5・8.2・8.3節 | T-09・T-18 |
| D-21 | 実装開始前のgate（18章）は、実装前に確認できるarchitecture／environment／source前提のみ。実装後でなければ確認できない適合検証（L1 golden vector等）は20章の実装フェーズgate | 18・20章 | — |
| D-19 | idempotencyの結果・claim state（WordPress側が権威）と、stable identity（Python側Integration Releaseが永続化）は別の状態 | 3章（G2）・7.7節 | Integration Releaseで検証 |
| D-24（A14・A15・A16） | 最終responseの**投影位置・eligibility・canonical保証の範囲、side-effect safetyと投影の分離** | 12.1節（O-*・P-*・CS-1・SP-*） | T-16・T-35・T-37、U-18 |
| D-25（A14） | Core media response由来headerの扱い | 12.2節（H-*） | T-35、U-20 |
| D-26（A14） | 投影後の改変点の扱い | 12.3節（X-*） | T-38、U-2 |
| D-27（A14・A16） | control path（route callbackだけ）の網羅範囲、unmarkedの扱い、permission_callbackの分離 | 12.4節（B-*） | T-34・T-36、U-19 |
| D-28（A14・A15・A16） | batch・内部dispatchの扱い | 12.5節（BT-*）・12.1節 SP-* | T-37、U-21 |
| D-30（A18） | `rest_post_dispatch`の全4 call-siteの分類（RD-1〜RD-4）、Finalizerの安全なno-op（RD-5）、request-affecting hookと`status_header`filterのtopology検証とunsupported topology（RD-6・X-11）。numeric statusとstatus line文字列の区別。source確認だけでruntimeをPASSにしない | 12.1節（RD-*）、12.3節 X-11、17.6節・V-16 | T-35・T-37・T-38、U-2・U-18・U-20 |
| D-29（A17） | method境界：effective method基準。effective non-POSTはCore Native（MO-2）、effective POSTでのoverride controlはE1（MO-3）。「override requestは常にE1」とは規定しない（MO-4） | 12.1節（MO-*）、8.1節、12.4節 B-4 | T-17・T-36、U-19 |

---

## 26. 未解決リスク（Amendment A18時点）

- **R-1（最重要、A2で更新）**：現行Pythonには、再試行をまたいで安定な`article_identity`・`content_revision`の供給元が**存在しない**（V-7：upload-stateキーはattempt-scopedの`as_store_key()`値）。供給側が試行ごとに値を変えると重複抑止は無効化される。**Integration Releaseの必須precondition（7.7節）**として定義・永続化を要求し、6.38では実装しない。したがって6.38単独では、現実のメディア重複の実効的抑止は達成されない（server側のat-most-onceは供給された値に対してのみ成立）。
- **R-2**：`PROCESSING`の自動回復を持たないため、Core拒否・crash・ACK曖昧でidentityが消費され、manual reconciliation（Future）が存在しない間は人手でDBを直接確認する運用になる。
- **R-3**：ローカルにPHP／MySQL／WordPress stagingが無く、L2／L3のevidenceは人手環境に依存する。
- **R-4**：6章の保証範囲外（rollback／restore／lossy failover）は、運用上の発生を検出する手段がない（運用契約のみ）。
- **R-5（A14・A15・A16・A17・A18で更新）**：S-1・U-1〜U-21が、**デプロイ先versionでは未確認**（7.1.1 sourceでの確認は17.5節。**実行時は未検証**）。**（A17）Review #24で独立にsource照合できなかった主張（17.6節）は、verifiedではなくvalidation-requiredとして残る**（A17はsource evidenceを追加していない）。**（A18）canonical sourceでのsource上の確認はReview #25・V-16で行われたが、デプロイ先versionでの再照合と、実行時（PHP／SAPI・approved plugin set）の確認は未了**。A13までの前提のうちU-18・U-2・U-19は偽と判明し、A14〜A16で再設計した。12章の前提の実行時の成立（U-18・U-19・U-20・U-21）は残る。
- **R-6**：`tests/zero_diff_guard_registry.py`の`RELEASE_ORDER`が`v6.36.0`止まり（V-6）。6.38でL1 E2E（新規testファイル）を追加する際、`v6.38.0`を直接追記するのか`v6.37.0`を先に整理するのかは、実装フェーズのHuman Gateで決める。6.37.0が未登録のまま回帰が`[KI-36]`以外で失敗していない事実は確認済みだが、「意図的」とする明示記述は無い。
- **R-7（A2で更新）**：wire contract（8.2節）・allowlist（8.1節）・HTTP／error contract（8.3節）はA2で設計時点に確定したが、**未検証のWordPress事実（U-13・U-14）に依存する前提**を含む。実装開始前Validation（18章）で確認し、結果により変更が必要な場合は実装時に拡張せず本書を改訂する。
- **R-9（A2）**：9.3節のBinding Fingerprint取得手段（特にCore `$wpdb`側で読取り専用SELECTを発行できるか、U-8）が実環境で成立しない場合、一部項目が「確認不能」となりclaimを一切作れなくなる（fail-closedの代償）。
- **R-10（A2、A13で訂正）**：claim確立後のHTTP outcomeは**8.3節の正本matrix（応答表・canonical error表）に従う**（本項は応答を再定義しない）。リスクとして残るのは、claimを確立した後のCoreの決定的拒否（再送で直る類）も、8.3節の表に従って「identity消費済み」として扱われ、人手対応を要しうること。10.2節#1のcheapな事前拒否で頻度を下げるが、ゼロにはならない。Finalizerの適用runtime failureは12章の保証境界に従う。
- **R-11（A2）**：T-25はprocess crash相当までであり、OS全体のクラッシュ・電源断・ストレージ障害は検証・保証しない。
- **R-12（A3）**：`gca_claim_state`はこの requestが確立・観測した事実の診断にとどまり、消費有無・retry可否を示さない（8.3節）。したがって、Integration Releaseは`gca_claim_state`だけではretry可否を判断できず、自身のdurable stateとserver側のduplicate応答（409 `processing`等）に依存する。この判断設計はIntegration Releaseの責務であり、6.38では解決しない。
- **R-13（A3、A4で更新）**：body size上限（33,554,432バイト）はplugin独自のv1 policyであり、**正当な画像を受理することを保証しない**（現行generatorは非空以外を検証しないため、32 MiB超の正当な画像は413で拒否されうる、8.1節）。対象環境のPHP／web server上限が小さければ環境側が先にrejectしてpluginに到達しない（U-16）。環境側のreject応答は`gca_claim_state`を欠く。filenameについては、現行の生成filenameが最大65文字で255文字上限に抵触しないことを算出済み（V-8）。
- **R-17（A5、A6、A8、A14・A15で更新）**：投影の契約は12章が正本（本項は再定義しない）。A13までの前提（`rest_pre_echo_response`でのstatus置換）は偽と判明し撤回した（V-11）。**残る依存（実行時は未検証）**：U-18・U-20、投影後の改変点とapproved plugin set（U-2）。満たされない場合は、別方式を実装時に選ばず、本書を改訂する。marker束縛は**偶発的な応答改変・混入の防止**にとどまり、co-resident malicious codeに対する耐性は主張しない（5.2節の脅威モデルは不変）。marker欠落・不正の経路（E5）の実環境での挙動は、L3（T-16・T-34）で確認する。Finalizerの適用runtime failureの保証境界は12章に従う（R-20）。
- **R-18（A7、A8で解消）**：A7では「GCA-taggedの2xx応答はdurable ACK確認済みの成功を意味する」という前提に依存していたが、**A8でauthoritative outcome marker方式へ置換し、この前提を廃止した**。`confirmed`（E9）は、**plugin control pathが明示的に設定する`E9` marker**（`CONFIRMED` duplicateでMedia Verificationが完遂不能な場合。A9）を根拠とし、pre-Finalizerの応答の内容・statusには依存しない（A9で、Finalizer自身の失敗にE9を割り当てる契約は廃止）。pre-Finalizerの応答の改変への対処は12章が正本（T-34(d)）。**残る依存**は、markerの束縛（requestが同一instanceであること、U-18）と、投影位置`rest_post_dispatch`での返却responseの反映（U-18。A14で`rest_pre_echo_response`から変更）、およびmarkerを設定するcontrol pathが**網羅しない範囲**（U-19、12.4節）であり、いずれも実装開始前Validation（18章）に分離した。
- **R-20（A9、A10、A11で整理）**：Finalizerの適用runtime failureの**保証境界は12章に従う**（本項は挙動を再定義しない）。リスクとして残るのは、適用の能力（U-18）が実装開始前に確認できても、**実行時の失敗の頻度・原因は実環境で初めて分かる**こと。検証は、T-07（層分離を含む）による。
- **R-19（A8、A14・A16・A17で更新）**：route callbackに到達しないGCA requestの扱いは12.4節 B-*が正本（結果は12.4節「帰結（R-19）」、claim・Core呼出との関係も12.4節）。**リスクとして残るのは、Core Nativeの401／403／400に相当する経路の応答がCore Nativeの形にならず、運用上の診断が難しくなること**（Python側の分類への影響はIntegration Releaseの責務、23章）。範囲はU-19で確認する。
- **R-21（A14・A15・A16・A18）**：canonical保証の範囲は12.1節 CS-1、`rest_post_dispatch`の全call-siteは12.1節 RD-*、投影後の作用点（`status_header`filterを含む）は12.3節、batch・内部dispatchは12.5節・12.1節 SP-*が正本。投影後の改変の有無はapproved plugin setの登録状況と実環境（L3）に依存し、conditional callbackは静的に検出できない可能性がある（5.3節）。直接送出headerの除去（U-20）は実行時にのみ確認できる。
- **R-15（A4）**：GCA成功応答はcanonical payload（5 field）でありCore Nativeの応答形ではない。他のCore field（`link`／`media_details`等）に依存するclientは対象外。現行`WordPressMediaUploader`は`id`／`source_url`／`mime_type`のみを使うため互換（V-10）。
- **R-16（A4）**：snapshotの`source_url`は初回成功時の値で、replayは再計算しない。CDN／offload等のplugin、またはsite URLの変更により、replay時点の現在のURLと異なりうる（U-17）。
- **R-14（A3）**：R2（claim確立後・Core呼出前）の再確認失敗は`PROCESSING`を保持して409とするため、drift・failoverの検出がidentityの消費を伴う。再確認の厳格さと、人手対応が必要になる頻度のトレードオフがある（R-10と同型）。
- **R-8**：`ignore_user_abort`相当の継続実行（U-12）が実環境で効かない場合、C2／C3の発生頻度が上がる。
