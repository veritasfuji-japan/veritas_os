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
  - そのため、運用で `VERITAS_ENV` を設定し忘れると script-src に `unsafe-inline` が残る余地がある

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

### 4. CSP については、既存レビュー文書の一部は現行コードとズレている

ここは要注意。

現行コードでは:
- `VERITAS_ENV=prod|production` の場合は strict nonce CSP を既定で有効化
- `NODE_ENV=production` 単独では strict を既定有効化しない
- 代わりに警告ログを出す

つまり、2026-03-16 文書内にある「`NODE_ENV=production` でも strict 強制」という記述系統は、**現行コードとは一致しない**。この点はレビューの読み手が誤解しやすいため、最新判断では以下が正しい。

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

1. **CSP strict は `VERITAS_ENV=production` に依存しており、`NODE_ENV=production` 単独では既定強制ではない**
2. **過去レビュー文書の一部記述は現行実装と完全には一致しない**

したがって現在の総評は、

> **「実運用直前レベル。ただし、安全性の最終品質は本番プロファイル設定の厳格運用に依存する」**

である。
