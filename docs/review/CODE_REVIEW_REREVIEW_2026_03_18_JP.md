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
  - ただし **デプロイ metadata の正系は引き続き `VERITAS_ENV=production` であり、`NODE_ENV=production` 単独は誤設定警告対象**
  - 2026-03-18 の今回改善で、`NODE_ENV=production` 単独でも strict nonce CSP を自動強制するようにし、`unsafe-inline` が残る余地は塞いだ

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

### 4. CSP については、既存レビュー文書との差分が今回改善でさらに縮まった

ここは要注意。

現行コードでは:
- `VERITAS_ENV=prod|production` の場合は strict nonce CSP を既定で有効化
- `NODE_ENV=production` 単独でも strict nonce CSP を自動強制
- ただし `VERITAS_ENV=production` が欠けている場合は、デプロイ profile の不整合として警告ログを出す

つまり、2026-03-16 文書内にある「`NODE_ENV=production` でも strict 強制」という記述は、**今回改善後の現行コードでは一致する状態に戻った**。ただし警告の意味は「strict が無効」という意味ではなく、「本番 profile の宣言が不完全」という意味に変わっている。

> **現在の正しい理解:**
> - `VERITAS_ENV=production` を使う本番プロファイルなら strict CSP は既定有効
> - `NODE_ENV=production` だけでも strict CSP は自動強制される
> - その場合、ログ警告は「互換モード残留」ではなく「本番 profile 宣言不足」の検知として出る

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

### 2. CSP strict は強化されたが、運用 profile の明示責務は残る

今回改善で `NODE_ENV=production` 単独でも strict nonce CSP を自動強制するため、`unsafe-inline` が残る経路は主要導線から除去された。一方で、`VERITAS_ENV=production` を明示しない deployment は backend / frontend の運用 profile 整合性を読み取りにくくするため、**安全性そのものよりも運用監査性の観点で弱みが残る**。

### 3. BFF fail-closed は安全だが、設定事故時に 503 化する

これは設計として正しいが、可用性面では「環境変数ミスが即障害になる」ことを意味する。運用成熟度が低い環境では、セキュリティ改善がそのままデプロイ事故率上昇として見える可能性がある。

### 4. テスト密度は高いが、既存レビューの件数表現は古い可能性がある

現行確認ではフロントエンドは 153 tests pass を確認した。既存レビューにある件数表現は、現時点ではそのまま最新値として扱わないほうがよい。

---

## セキュリティ警告（運用必須）

1. **`VERITAS_ENV=production` を本番で必ず明示すること。**
   これがない場合でも `NODE_ENV=production` なら strict CSP は自動適用されるが、profile 不整合警告が出続け、運用監査性が落ちる。

2. **`NEXT_PUBLIC_VERITAS_API_BASE_URL` を production に残さないこと。**
   現行実装は fail-closed のため、残っていると BFF が 503 を返す。これは安全側だが、本番障害として顕在化する。

3. **`VERITAS_AUTH_ALLOW_FAIL_OPEN=true` を非本番限定に固定すること。**
   これは検証用の危険オプションであり、auth store 障害時の防御を弱める。

4. **`NODE_ENV=production` を使うデプロイでも `VERITAS_ENV=production` を明示すること。**
   現在は strict CSP が自動強制されるため即座に緩むことはないが、警告のない正規プロファイルへ寄せて監査可能性を維持すべき。

5. **pickle/joblib artifact を runtime 配置しないこと。**
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
- `frontend/middleware.ts` の CSP 判定を強化し、`NODE_ENV=production` 単独でも strict nonce CSP を自動強制するようにした。これにより、`VERITAS_ENV` の設定漏れがあっても `script-src 'unsafe-inline'` が本番相当実行で残らない。
- 同時に警告文言を見直し、警告の意味を「strict 未適用」ではなく「`VERITAS_ENV=production` が欠けた profile 不整合検知」に変更した。
- `frontend/middleware.test.ts` に `NODE_ENV=production` 単独で strict CSP が有効になる回帰テストを追加し、警告発火時にも `unsafe-inline` が含まれないことを固定した。
- `docs/operations/ENTERPRISE_SLO_SLI_RUNBOOK_JP.md` に本番デプロイ前の P0 セキュリティ確認項目を追加し、`VERITAS_ENV=production` 必須・`NEXT_PUBLIC_VERITAS_API_BASE_URL` 禁止・`VERITAS_AUTH_ALLOW_FAIL_OPEN` 禁止を runbook に明記した。

**セキュリティ警告:**
- この変更は backend startup で検知できる環境変数に限ったガードであり、フロント単体デプロイ経路の誤設定まで完全に代替するものではない。
- `VERITAS_AUTH_ALLOW_FAIL_OPEN=true` は引き続き危険フラグであり、検証用環境以外では設定しないこと。
- `NEXT_PUBLIC_VERITAS_API_BASE_URL` は production に残すと情報露出と可用性事故の両方を招くため、デプロイ設定から除去すること。
- CSP nonce は秘密値であるため、レスポンスヘッダーやクライアント到達可能なデバッグ出力へ再露出しないこと。nonce を漏らすと strict CSP の防御効果を弱める。
- `NODE_ENV=production` 単独でも strict nonce CSP は自動適用されるが、`VERITAS_ENV=production` が欠けたまま運用すると profile 監査・障害切り分けの一貫性を損なう。デプロイ定義は引き続き是正すること。

### P1
- `core/memory.py` の追加分割（Evidence / lifecycle / security 以外の残責務）
- `core/fuji.py` の追加分割（policy application / decision assembly / telemetry 周辺の局所化）

### P2
- レビュー文書群の棚卸しを行い、**現行コードと不一致の過去レビュー記述**を「履歴」と「現行判断」に分離する
- 既存の豊富なテストに対し、運用設定の誤りを検知する smoke check を増やす

---

## 最終判定

VERITAS OS は、2026-03-16 時点レビューよりも **セキュリティ hardening と責務分離がさらに前進している**。特に以下は前向きに評価できる。

- auth store failure mode の fail-closed 強化
- BFF API base URL の production fail-closed 化
- `server.py` からの周辺責務分離の継続
- boundary / pickle guard の CI 実行可能性

一方で、現行コード基準で最も重要な注意点は次の 2 つである。

1. **strict CSP 自体は `NODE_ENV=production` 単独でも自動強制されるが、正規の本番 profile は依然として `VERITAS_ENV=production` で明示すべき**
2. **過去レビュー文書の一部記述は、警告の意味や前提条件の読み替えが必要**

したがって現在の総評は、

> **「実運用直前レベル。ただし、安全性の最終品質は本番プロファイル設定の厳格運用に依存する」**

である。
