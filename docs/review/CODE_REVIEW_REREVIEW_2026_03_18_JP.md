# VERITAS OS 再評価レビュー（2026-03-18）

- 対象:
  - `docs/review/CODE_REVIEW_FULL_2026_03_16_AGENT_JP.md` の全文
  - 2026-03-18 時点の現行コードベース
- 方針:
  - 既存レビューの結論をそのまま再掲せず、**現行コードで裏取りできる事実**に限定して再評価する
  - Planner / Kernel / Fuji / MemoryOS の責務境界は変更対象にせず、現状の整合性を確認する
  - セキュリティ上の注意点は「実装済みの防御」と「まだ運用で踏み抜けるリスク」を分けて記述する

---

## 結論（再評価）

**総合評価: 88/100（実運用直前、ただし運用設定の厳格化が前提）**

- **バックエンド: 89/100**
  - `api/server.py` から周辺責務の分離がかなり進み、2026-03-16 時点レビューより保守性は改善している
  - 責務境界チェッカーは現状 pass しており、Planner / Kernel / Fuji / MemoryOS の越境依存は検出されなかった
  - 一方で `core/memory.py` と `core/fuji.py` は依然として大きく、長期保守では追加分割の価値が高い
- **フロントエンド: 86/100**
  - BFF・httpOnly cookie・trace_id 伝搬・CSP nonce/report-only の設計は継続して堅い
  - ただし **strict CSP は `VERITAS_ENV=production` では既定有効だが、`NODE_ENV=production` 単独では既定有効にならない**
  - `NODE_ENV=production` 単独強制は E2E 回帰を起こしたため採用せず、現行は warning + 明示 rollout のまま維持する

---

## 既存レビューからの主な再評価ポイント

### 1. `api/server.py` 巨大化リスクは「継続」だが、深刻度は一段下がった

2026-03-16 のレビューでは `api/server.py` の巨大化が主要懸念だった。現行コードでもファイル自体はまだ大きいが、起動ヘルス、CORS、lifespan、依存解決、Trust Log runtime などが別モジュールに切り出されているため、**単一ファイル集中リスクは実際に軽減している**。

再評価:
- 指摘は依然有効
- ただし「改善未着手」ではなく、**分割は着実に進行済み**
- 今の主懸念は `server.py` 単体よりも、`memory.py` / `fuji.py` の残サイズ

### 2. Auth fail-open リスクは以前よりかなり抑制された

既存レビューの警告は妥当だったが、現行コードでは以下の hardening が入っている。

- `VERITAS_ENV=prod|production` **または** `NODE_ENV=production` では強制的に `closed`
- 非本番でも `open` は `VERITAS_AUTH_ALLOW_FAIL_OPEN=true` を付けた明示許可制
- `open` を要求しても許可フラグがなければ警告付きで `closed` へフォールバック

再評価:
- **本番の auth store fail-open 余地はかなり小さくなった**
- ただし非本番に `VERITAS_AUTH_ALLOW_FAIL_OPEN=true` を残したまま昇格すると危険なので、環境棚卸しは必要

### 3. BFF の公開環境変数依存は、レビュー時点より厳格になっている

既存レビューでは `NEXT_PUBLIC_VERITAS_API_BASE_URL` 依存を警告していたが、現行コードでは次の fail-closed が入っている。

- `VERITAS_API_BASE_URL` は server-only 前提
- production 判定下で `NEXT_PUBLIC_VERITAS_API_BASE_URL` が残っていると警告だけでなく `null` を返す
- その結果、BFF route は `503 server_misconfigured` を返す

再評価:
- この領域は **「警告止まり」から「本番遮断」へ改善** している
- ただしデプロイ作業者が公開環境変数を残すと可用性事故として表面化するため、リリース前検証は必須

### 4. CSP については、既存レビュー文書との差分が残る

ここは要注意。

現行コードでは:
- `VERITAS_ENV=prod|production` の場合は strict nonce CSP を既定で有効化
- `NODE_ENV=production` 単独では strict を既定有効化しない
- 代わりに警告ログを出す

`NODE_ENV=production` 単独強制は試したが、frontend E2E で回帰したため採用を見送った。したがって、2026-03-16 文書内にある「`NODE_ENV=production` でも strict 強制」という記述系統は、**現行コードとは一致しない**。

> **現在の正しい理解:**
> - `VERITAS_ENV=production` を使う本番プロファイルなら strict CSP は既定有効
> - `NODE_ENV=production` だけでは互換モードが残り得る
> - その場合、ログ警告は出るが、実行自体は止まらない

---

## 現在の強み

### 1. 責務境界ガードがコードだけでなく検査スクリプトでも維持されている

Planner / Kernel / Fuji / MemoryOS の相互依存は、専用チェッカーで継続検証できる。今回の再評価でも pass を確認したため、アーキテクチャ方針が文書だけでなく運用可能な guardrail になっている。

### 2. MemoryOS の pickle 廃止方針は強い

Memory 関連では runtime で pickle/joblib を禁止し、CI 側にも検査スクリプトがある。これは RCE リスクに対してかなり明確な防御になっている。

### 3. BFF は server-only routing と権限ゲートの形が良い

- browser から backend API key を直接扱わない
- auth token → role → policy の順で制御する
- body size 上限と trace_id 伝搬がある
- misconfiguration 時は 503 fail-closed がある

この構成は、少なくとも「秘密情報露出」「無制限 proxy」「監査追跡不能」の典型事故を抑えやすい。

### 4. ライフサイクル/起動健全性/Trust Log 周りの分割は妥当

`startup_health.py`、`lifespan.py`、`trust_log_runtime.py`、`dependency_resolver.py` などへの抽出は、責務を越えずに `server.py` の変更衝突を減らす方向で、レビュー観点からも良い改善。

---

## 現在の弱み・残課題

### 1. `core/memory.py` と `core/fuji.py` はまだ大きい

責務分離は進んでいるが、`memory.py` と `fuji.py` は依然として大きい。現状の設計は保たれているものの、将来の仕様追加で再び密結合化するリスクがある。

### 2. CSP strict は「完全 fail-closed」とはまだ言い切れない

`VERITAS_ENV=production` を正しくセットすれば強いが、`NODE_ENV=production` 単独では警告止まりで互換モードが残る。このため、**コードの安全性より運用設定の正しさに依存する部分が残っている**。

### 3. BFF fail-closed は安全だが、設定事故時に 503 化する

これは設計として正しいが、可用性面では「環境変数ミスが即障害になる」ことを意味する。運用成熟度が低い環境では、セキュリティ改善がそのままデプロイ事故率上昇として見える可能性がある。

### 4. テスト密度は高いが、既存レビューの件数表現は古い可能性がある

現行確認ではフロントエンドは 153 tests pass を確認した。既存レビューにある件数表現は、現時点ではそのまま最新値として扱わないほうがよい。

---

## セキュリティ警告（運用必須）

1. **`VERITAS_ENV=production` を本番で必ず明示すること。**
   これがないと CSP strict の既定適用に乗らず、`NODE_ENV=production` 単独では互換モードが残る可能性がある。

2. **`NEXT_PUBLIC_VERITAS_API_BASE_URL` を production に残さないこと。**
   現行実装は fail-closed のため、残っていると BFF が 503 を返す。これは安全側だが、本番障害として顕在化する。

3. **`VERITAS_AUTH_ALLOW_FAIL_OPEN=true` を非本番限定に固定すること。**
   これは検証用の危険オプションであり、auth store 障害時の防御を弱める。

4. **pickle/joblib artifact を runtime 配置しないこと。**
   Runtime 側はブロックするが、配置自体が運用の不整合シグナルであり、必ず事前除去すべき。

---

## 優先度つき提案

### P0
- 運用 runbook に `VERITAS_ENV=production` 必須を明記し、デプロイ検証項目へ組み込む
- production 環境で `NEXT_PUBLIC_VERITAS_API_BASE_URL` が空であることをデプロイ前チェックに追加する
- `VERITAS_AUTH_ALLOW_FAIL_OPEN` の本番混入検知を CI / startup validation に追加することを検討する

### P0対応（2026-03-18 実施）
- `veritas_os/api/startup_health.py` に `validate_startup_security_flags()` を追加し、起動時に高リスク環境変数を検証するようにした。
- `VERITAS_ENV=prod|production` で `VERITAS_AUTH_ALLOW_FAIL_OPEN=true` が混入していた場合、`RuntimeError` を送出して fail-fast する。
- 同じく production で `NEXT_PUBLIC_VERITAS_API_BASE_URL` が設定されていた場合も `RuntimeError` を送出して fail-fast する。
- 非本番でこれらの危険フラグが使われた場合は、挙動を変えず `[SECURITY]` 警告ログを残す。
- `veritas_os/tests/test_api_startup_health.py` に回帰テストを追加し、非本番 warning / 本番 fail-fast の両方を固定した。
- `frontend/middleware.ts` から `x-veritas-nonce` レスポンスヘッダーを削除し、CSP nonce をブラウザへ再露出しないようにした。
- `frontend/middleware.test.ts` を更新し、nonce は内部の `x-nonce` リクエストヘッダー経由でのみ伝搬し、レスポンスヘッダーへは露出しないことを固定した。
- `NODE_ENV=production` 単独で strict CSP を自動強制する案は frontend E2E 回帰を起こしたため採用しなかった。現行は `VERITAS_ENV=production` または `VERITAS_CSP_ENFORCE_NONCE=true` の明示 rollout を維持する。
- `frontend/middleware.test.ts` では `NODE_ENV=production` 単独では warning-only に留まることを固定し、将来の不用意な fail-closed 変更で UI を壊さないようにした。
- `veritas_os/api/startup_health.py` に `NODE_ENV=production` かつ `VERITAS_ENV!=production` の警告を追加し、backend 起動時にも frontend CSP の運用依存を可視化した。
- `veritas_os/tests/test_api_startup_health.py` に回帰テストを追加し、`NODE_ENV=production` 単独では fail-fast せず、明示 warning が残ることを固定した。
- `docs/operations/ENTERPRISE_SLO_SLI_RUNBOOK_JP.md` に本番デプロイ前の P0 セキュリティ確認項目を追加し、`VERITAS_ENV=production` 必須・`NEXT_PUBLIC_VERITAS_API_BASE_URL` 禁止・`VERITAS_AUTH_ALLOW_FAIL_OPEN` 禁止を runbook に明記した。

**セキュリティ警告:**
- この変更は backend startup で検知できる環境変数に限ったガードであり、フロント単体デプロイ経路の誤設定まで完全に代替するものではない。
- `VERITAS_AUTH_ALLOW_FAIL_OPEN=true` は引き続き危険フラグであり、検証用環境以外では設定しないこと。
- `NEXT_PUBLIC_VERITAS_API_BASE_URL` は production に残すと情報露出と可用性事故の両方を招くため、デプロイ設定から除去すること。
- CSP nonce は秘密値であるため、レスポンスヘッダーやクライアント到達可能なデバッグ出力へ再露出しないこと。nonce を漏らすと strict CSP の防御効果を弱める。
- `NODE_ENV=production` 単独で strict CSP を強制すると UI が壊れる経路が残っているため、必ず `VERITAS_ENV=production` と段階的 rollout 手順に従うこと。

### P1
- `core/memory.py` の追加分割（Evidence / lifecycle / security 以外の残責務）
- `core/fuji.py` の追加分割（policy application / decision assembly / telemetry 周辺の局所化）

### P1対応（2026-03-19 追加実施）
- `veritas_os/core/memory_helpers.py` を新設し、`memory.py` に残っていた純粋関数ベースの整形処理を分離した。
- 分離対象は Memory Distill prompt 組み立て / episodic 抽出 / LLM response text 抽出 / semantic doc 組み立て / vector rebuild document 変換で、MemoryOS の storage / vector access / llm orchestration の責務は `memory.py` 側に維持した。
- `veritas_os/core/memory.py` 側は既存 private API (`_build_distill_prompt`) を互換 wrapper として残し、Planner / Kernel / Fuji との境界や呼び出し契約を変えずにファイル肥大だけを抑えた。
- `veritas_os/tests/test_memory_helpers.py` を追加し、抽出した helper のフィルタ条件・response 互換・metadata 維持を直接固定した。

### P1対応（2026-03-19 追補実施）
- `veritas_os/core/memory_search_helpers.py` を新設し、`memory.py` に残っていた検索結果の純粋整形処理を分離した。
- 分離対象は vector search payload の候補抽出 / `user_id` ベースの hit 絞り込み / `(text, user_id)` 単位の去重 / KVS search payload の正規化で、MemoryOS の実 I/O・vector access・fallback 制御は `memory.py` 側に維持した。
- `veritas_os/core/memory.py` 側は既存 private API (`_dedup_hits`) を互換 wrapper として残し、Planner / Kernel / Fuji / MemoryStore の責務境界を変えずに `search()` 周辺の肥大だけを抑えた。
- `veritas_os/tests/test_memory_search_helpers.py` を追加し、複数 payload 形状の互換・shared hit の user filter・去重順序・KVS 正規化を直接固定した。

**セキュリティ警告:**
- `extract_summary_text()` の helper 化は LLM 応答の解釈を整理しただけであり、モデル出力の安全性や prompt injection 耐性を新たに保証する変更ではない。
- `build_vector_rebuild_documents()` は traceability 用 metadata を維持するが、元データに不要な機微情報が入っていればそのまま index 対象になるため、投入前のデータ最小化は引き続き必要。
- `memory_search_helpers.py` への分離は検索結果の整形責務を明確化しただけであり、cross-user data 混入を根本解決する access control 変更ではない。`filter_hits_for_user()` は既存 fail-closed 仕様を維持するための整理であり、上位の認可ロジックは引き続き必須。

### P1対応（2026-03-19 追加実施・3）
- `veritas_os/core/memory_summary_helpers.py` を新設し、`memory.py` と `memory_store.py` に残っていた Planner 向け summary の純粋整形処理を共通化した。
- 分離対象は summary fallback 文言 / timestamp 正規化 / text truncate / tag 付き箇条書き組み立てで、MemoryOS の検索 I/O・KVS fallback・Planner 呼び出し契約は変更していない。
- `veritas_os/core/memory.py` と `veritas_os/core/memory_store.py` は `build_planner_summary()` を呼ぶ薄い wrapper に整理し、責務境界を変えずに `summarize_for_planner()` 周辺の重複と肥大だけを抑えた。
- `veritas_os/tests/test_memory_summary_helpers.py` を追加し、no-hit fallback・timestamp 互換・長文 truncate の既存整形契約を直接固定した。

**セキュリティ警告:**
- 今回の変更は Planner 向け summary の表示整形責務を抽出しただけであり、MemoryStore の認可・search filter・cross-user isolation を強化する変更ではない。上位の `user_id` ベース fail-closed 制御は引き続き必須。
- summary へ出す `text` / `tags` は既存検索結果をそのまま整形するため、保存前のデータ最小化や機微情報の抑制が不十分な場合、要約表示にも同じ情報が現れる点は変わらない。

### P1対応（2026-03-19 追加実施・2）
- `veritas_os/core/memory_store_helpers.py` を新設し、`memory.py` に残っていた MemoryStore の純粋整形処理を分離した。
- 分離対象は recent record の substring filter / fallback 類似度計算 / KVS fallback search hit 組み立てで、MemoryOS の実ストレージ I/O・erase/retention・vector fallback 制御は `memory.py` 側に維持した。
- `veritas_os/core/memory.py` 側は既存 private API (`_simple_score`) を互換 wrapper として残し、`MemoryStore.search()` の入出力契約を変えずに KVS fallback 周辺の肥大だけを抑えた。
- `veritas_os/tests/test_memory_store_helpers.py` を追加し、recency filter・substring match・user/kind fail-closed filter・score 安定性を直接固定した。

### P1対応（2026-03-19 追加実施・Memory compliance 重複解消）
- `veritas_os/core/memory.py` の `MemoryStore.erase_user()` から、すでに `veritas_os/core/memory_compliance.py` に実装済みだった user erase planning / legal hold 保護 / semantic cascade / audit record 生成の重複実装を除去した。
- `MemoryStore.erase_user()` は共有 helper `erase_user_data()` を呼ぶ薄い永続化 wrapper に整理し、MemoryOS の storage 保存責務だけを `memory.py` 側へ残した。
- `veritas_os/tests/test_memory_core.py` に回帰テストを追加し、`erase_user()` が共有 compliance helper を経由して削除計画を立てることを固定した。

**セキュリティ警告:**
- 今回の helper 分離は MemoryStore の検索整形責務を明確化しただけであり、cross-user access control や retention policy enforcement を強化する変更ではない。上位の認可と既存 lifecycle 制御は引き続き必須。
- `build_kvs_search_hits()` は既存の `user_id` / `kind` / `min_sim` fail-closed filter を保持するが、元レコードに過剰な機微情報を保存していれば検索ヒットの `text` と `meta` にそのまま現れるため、保存前のデータ最小化は継続して必要。

**セキュリティ警告:**
- 今回の変更は erase 処理の共有実装へ統一した保守性改善であり、legal hold 判定条件や audit retention のポリシー自体を強化するものではない。運用上は `reason` / `actor` の監査品質と audit record 保全を引き続き担保する必要がある。

### P1対応（2026-03-19 追加実施・MemoryStore 本体重複解消）
- `veritas_os/core/memory.py` に残っていた `MemoryStore` 本体の重複実装を除去し、共有実装 `veritas_os/core/memory_store.py` を再エクスポートする構成へ統一した。
- これにより、MemoryOS の KVS lifecycle / compliance / summary / search fallback の実装ドリフト源を 1 箇所へ集約しつつ、既存の `memory.MemoryStore` API と `_LazyMemoryStore` 契約は維持した。
- `veritas_os/tests/test_memory_core.py` に回帰テストを追加し、`memory.py` が shared `MemoryStore` / retention constants をそのまま再利用していることを固定した。
- 追補として、`veritas_os/core/memory.py` から shared `MemoryStore` へ渡す `locked_memory` を互換 wrapper で再配線し、既存テスト/monkeypatch が `memory.locked_memory` を差し替える前提を壊さないように補正した。
- `veritas_os/tests/test_memory_core.py` に互換回帰テストを追加し、`memory.locked_memory` を patch した場合でも `MemoryStore._save_all()` が fail-closed で `False` を返すことを固定した。

**セキュリティ警告:**
- 今回の変更は `MemoryStore` 実装の単一化によって lifecycle / legal hold / user filter の drift リスクを下げる保守性改善であり、cross-user isolation や検索認可の新規強化ではない。上位の `user_id` ベース fail-closed 制御は引き続き必須。
- shared 実装へ統一したことで、将来 `memory_store.py` 側に不備を入れると `memory.py` 経由の呼び出しも同時に影響を受けるため、MemoryOS の永続化変更時は回帰テストを必ず維持すること。


### P1対応（2026-03-18 追加実施）
- `veritas_os/core/fuji_helpers.py` を新設し、`fuji.py` に残っていた小粒だが横断利用される helper 群を分離した。
- 分離対象は `safe_nonneg_int` / `resolve_trust_log_id` / TrustLog redaction / low-evidence followup 構築 / high-risk context 判定 / FUJI code 選択 / text normalization で、FUJI の責務境界は変更していない。
- `veritas_os/core/fuji.py` 側は互換性維持のため既存の private 名 (`_safe_nonneg_int` など) を alias し、既存テストや呼び出し側を壊さずにファイル肥大だけを抑えた。
- `veritas_os/tests/test_fuji_helpers.py` を追加し、抽出した helper の重要挙動を直接固定した。

**セキュリティ警告:**
- `normalize_injection_text` や TrustLog redaction は防御の一層に過ぎず、これだけで prompt injection や PII 漏えいを完全に防げるわけではない。
- 今回の分割は保守性改善であり、既存の policy / safety head / trust log の enforcement 強度を上げる変更ではない。運用上の CSP / auth / 公開環境変数ガードは引き続き必須。

### P1対応（2026-03-19 追加実施・FUJI policy 重複解消）
- `veritas_os/core/fuji.py` から、すでに `veritas_os/core/fuji_policy.py` へ抽出済みだった policy load / hot reload / `_apply_policy` / blocked keyword 解決の重複実装を除去し、共有モジュールを参照する薄い互換 wrapper に整理した。
- これにより `fuji.py` と `fuji_policy.py` の policy state が二重化しないようにしつつ、既存テストや互換 API (`fuji.reload_policy()`, `fuji._load_policy()`) は維持した。
- `veritas_os/tests/test_fuji_core.py` に回帰テストを追加し、`fuji.reload_policy()` が共有 policy モジュールの更新結果へ追従することを固定した。
- 追補として、CI で参照されていた後方互換 private API (`_normalize_injection_text`, `_build_runtime_patterns_from_policy`) を `fuji.py` 側へ alias として戻し、shared implementation へ委譲する形で回帰を解消した。
- さらに、`fuji.py` 側の import-time YAML capability check / fallback logging / hot-reload 監視状態 (`_POLICY_MTIME`) も互換 wrapper として維持し、既存 capability test・policy load test・hot reload test を壊さない形へ補正した。
- 実測で `veritas_os/core/fuji.py` は 1434 行から 982 行へ縮小し、P1 の残課題だった FUJI 側の肥大を責務境界を変えずに圧縮した。

**セキュリティ警告:**
- 今回の変更は FUJI の policy state 重複を除去してドリフトを減らす保守性改善であり、policy 内容そのものの強化や prompt injection / PII 判定ロジックのしきい値変更は行っていない。
- `VERITAS_FUJI_POLICY` や strict policy-load の運用ミスに対する fail-closed / fallback の安全性は、引き続き `fuji_policy.py` 側の shared loader 実装に依存するため、運用時は YAML policy の配置・権限・監査を継続すること。

### P2
- レビュー文書群の棚卸しを行い、**現行コードと不一致の過去レビュー記述**を「履歴」と「現行判断」に分離する
- 既存の豊富なテストに対し、運用設定の誤りを検知する smoke check を増やす

### P2対応（2026-03-18 追加実施）
- `setup.sh` が生成する `.env` テンプレートから旧公開環境変数 `NEXT_PUBLIC_API_BASE_URL` を除去し、server-only の `VERITAS_API_BASE_URL` を既定出力に変更した。
- `scripts/quality/check_deployment_env_defaults.py` を追加し、operator 向けテンプレート（現時点では `.env.example` と `setup.sh`）に危険/旧式の環境変数が残っていないかを smoke check できるようにした。
- 同チェックは `NEXT_PUBLIC_API_BASE_URL` / `NEXT_PUBLIC_VERITAS_API_BASE_URL` / `VERITAS_AUTH_ALLOW_FAIL_OPEN=true` を禁止し、BFF の server-only 前提がテンプレートから崩れていないことを確認する。
- `veritas_os/tests/test_check_deployment_env_defaults.py` を追加し、旧公開環境変数の検知・必須 token 欠落の検知・現行 repo テンプレートの pass を固定した。
- `.env.example` と `setup.sh` に production hardening コメントを追加し、`VERITAS_ENV=production` を本番で明示設定する運用前提をテンプレート自体へ埋め込んだ。
- `scripts/quality/check_deployment_env_defaults.py` を拡張し、operator 向けテンプレートに `VERITAS_ENV=production` の明示 guidance が残っていることも smoke check するようにした。
- `veritas_os/tests/test_check_deployment_env_defaults.py` に回帰テストを追加し、production profile guidance が欠落した場合に検知できることを固定した。

### P2対応（2026-03-19 追加実施）
- `.github/workflows/main.yml` の lint job に `python scripts/quality/check_deployment_env_defaults.py` を追加し、operator 向けテンプレートの危険な env default が PR/merge 時に継続検知されるようにした。
- 同じく lint job に `python scripts/security/check_runtime_pickle_artifacts.py` を追加し、レビュー文書と運用手順で前提化していた「pickle/joblib runtime 混入の CI 検知」を workflow 上でも実際に強制した。
- これにより、これまで「スクリプトは repo にあるが CI wiring が見えにくい」状態だった deployment hardening / runtime artifact guard を、既存の fast-fail セキュリティゲートへ統合した。

**セキュリティ警告:**
- この smoke check は operator 向けテンプレートの既定値を守るものであり、実際のデプロイ基盤（Secrets Manager / CI variables / hosting dashboard）に直接投入された危険値までは自動で是正しない。
- `VERITAS_AUTH_ALLOW_FAIL_OPEN=true` は依然として危険フラグであり、テンプレートから消えていても運用環境へ手動設定すれば防御が弱まる。backend startup fail-fast とあわせて継続監査が必要。
- `VERITAS_ENV=production` の guidance 追加は運用ミスを減らすための静的ガードであり、frontend 単体配備や外部ホスティング UI 上での値注入忘れまで自動修復するものではない。
- GitHub Actions を通らないローカル実行や外部署名済み artifact の持ち込みには別途統制が必要であり、この CI 追加だけで supply-chain / runtime artifact 混入リスクが完全に解消されるわけではない。

---

## 最終判定

VERITAS OS は、2026-03-16 時点レビューよりも **セキュリティ hardening と責務分離がさらに前進している**。特に以下は前向きに評価できる。

- auth store failure mode の fail-closed 強化
- BFF API base URL の production fail-closed 化
- `server.py` からの周辺責務分離の継続
- boundary / pickle guard の CI 実行可能性

一方で、現行コード基準で最も重要な注意点は次の 2 つである。

1. **CSP strict は `VERITAS_ENV=production` に依存しており、`NODE_ENV=production` 単独では既定強制ではない**
2. **過去レビュー文書の一部記述は現行実装と完全には一致しない**

したがって現在の総評は、

> **「実運用直前レベル。ただし、安全性の最終品質は本番プロファイル設定の厳格運用に依存する」**

である。
