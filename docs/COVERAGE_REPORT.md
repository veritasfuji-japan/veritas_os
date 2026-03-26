# VERITAS OS — テストカバレッジレポート（改善版）

**最終更新日**: 2026-03-26  
**基準スナップショット**: 2026-03-24（CI） + 2026-03-26（security/memory focused再計測）  
**Python**: 3.12.3  
**OS**: Linux 6.14.0-1017-azure (Ubuntu)  
**テストフレームワーク**: pytest 9.0.2 / pytest-cov 7.1.0（CI）  
**CIカバレッジ基準**: `--cov-fail-under=85`

---

## 1. エグゼクティブサマリー

- **CI判定値（2026-03-24）**: **87%（term-missing）** → ✅ 基準達成（85%以上）
- **XML line_rate（同日）**: **89.3%**
- **CI相当テスト実行（2026-03-26, local）**: **5382 passed / 8 skipped / 0 failed**
- **security focused実測（2026-03-26, trace line-only）**:
  - `logging/encryption.py`: **95%**
  - `audit/trustlog_signed.py`: **97%**
  - `logging/trust_log.py`: **48%**
- **memory focused実測（2026-03-26, trace line-only）**:
  - `core/memory_store.py`: **99%**（`test_memory_store*` 系 266 passed）
  - `core/memory_storage.py`: **96%**（`test_memory_storage.py` + hardening 109 passed）
  - `core/memory.py`: **89%**（memory API/facade 系 177 passed）
- **テスト件数**: 1,768 → 4,350（**+2,582 / +146%**）
- **失敗テスト**: 4 → **0（全解消）**
- **コード規模**: 10,614 → 18,225 stmts（**+72%**）

> 解釈: コードベースが大幅拡大した中で、CI判定カバレッジを 87% に維持できている。

---

## 2. 計測条件と読み方（重要）

### 2.1 2種類の計測値

1. **CI全体値（2026-03-24）**
   - `pytest + pytest-cov`
   - branch coverage 有効
   - CI判定に使用される正規値
2. **focused再計測（2026-03-26, security）**
   - 標準ライブラリ `trace` による line-only coverage
   - 特定モジュールの改善確認用途
   - CI branch coverage と**直接比較不可**
3. **focused再計測（2026-03-26, memory_store周辺）**
   - 実行A: `test_memory_store.py` + `test_memory_store_core.py` + `test_memory_store_hardening.py` + `test_memory_store_reliability.py`
   - 実行B: `test_memory_storage.py` + `test_memory_store_hardening.py`
   - 実行C: `test_memory_core.py` + `test_memory_coverage.py` + `test_memory_branches.py` + `test_memory_decomposition.py`
   - 注: この実行環境では `pytest-cov` が未導入かつ外部取得不可のため、
     local では CI と同一フォーマットのカバレッジ再生成は未実施

### 2.2 term 87% と xml 89.3% の差

- coverageの集計軸（term-missing / xml / branch計算）差分による。
- **CI合否は 87%（term-missing）で判定**する。

### 2.3 production-like validation との関係（2026-03-26時点）

- `production` / `smoke` / `external` マーカーの検証は、coverage 判定用の
  `main.yml` とは分離された `production-validation.yml` で実施される。
- したがって、本レポートの CI カバレッジ値（`--cov-fail-under=85`）は
  **`-m "not slow"` の main CI 実行結果**を基準とし、production-like workflow の
  pass/fail とは集計母集団が異なる。
- `test-slow` は main CI の並列ジョブで実行されるが、coverage 収集は行わないため、
  カバレッジ率の母集団には含まれない。

---

## 3. 全体推移（CI基準）

| 指標 | 前回 (2026-02-12) | 今回 (2026-03-24) | 変化 |
|---|---:|---:|---:|
| 全体カバレッジ（term） | 89% | **87%** | -2pt |
| 全体カバレッジ（xml） | — | **89.3%** | — |
| ステートメント数 | 10,614 | 18,225 | +7,611 |
| ミス行数 | 1,664 | 1,957 | +293 |
| ブランチ数 | 3,530 | 5,672 | +2,142 |
| 部分カバレッジ分岐 | 580 | 714 | +134 |
| passed | 1,768 | **4,350** | +2,582 |
| failed | 4 | **0** | -4 |
| skipped | — | 3 | — |

> 補足: 見かけ上カバレッジ率は微減だが、コード増加率（+72%）を考慮すると品質維持は良好。

---

## 4. 重点5モジュール（改善実績）

| モジュール | 前回 | 今回 | 増減 | Stmts | Miss | Branch | BrPart |
|---|---:|---:|---:|---:|---:|---:|---:|
| `core/pipeline.py` | 68% | **98%** | **+30pt** | 269 | 6 | 54 | 0 |
| `api/server.py` | 74% | **93%** | **+19pt** | 240 | 19 | 14 | 0 |
| `core/memory.py` | 75% | **94%** | **+19pt** | 629 | 27 | 168 | 21 |
| `core/kernel.py` | 81% | **94%** | **+13pt** | 451 | 21 | 168 | 15 |
| `core/fuji.py` | 85% | **90%** | **+5pt** | 455 | 35 | 142 | 20 |

**所見**:
- 優先5モジュールはすべて改善。
- `pipeline.py` / `server.py` は branch 100%（BrPart=0）で安定。

---

## 5. 低カバレッジ優先対象（80%未満のみ）

> 以下は **「現在 80% 未満」** のみ掲載（改善済みモジュールは除外）。

| 優先 | モジュール | Coverage | Miss | 改善余地 |
|---:|---|---:|---:|---|
| 1 | `core/memory_storage.py` | 56%（CI） / 96%（focused） | 36 | 永続化失敗・I/O異常分岐のCI統合 |
| 2 | `tools/web_search_security.py` | 59%（CI） / 95.3%（focused） | 53 | DNS/ソケット例外分岐の常時回帰テスト化 |
| 3 | `core/pipeline_response.py` | 68% | 17 | 例外整形・戻り値境界テスト |
| 4 | `core/pipeline_execute.py` | 73% | 21 | 実行順序・異常分岐の網羅 |
| 5 | `core/pipeline_gate.py` | 73% | 27 | deny系条件の境界網羅 |
| 6 | `core/pipeline_helpers.py` | 74% | 30 | ヘルパ分岐の入力境界テスト |
| 7 | `core/pipeline_contracts.py` | 74% | 28 | 契約検証の異常値テスト |
| 8 | `api/routes_decide.py` | 75% | 30 | ルーティング失敗・fallback |
| 9 | `api/rate_limiting.py` | 76% | 28 | burst境界・時刻依存分岐 |
| 10 | `core/pipeline_inputs.py` | 77% | 18 | 入力正規化の異常系 |
| 11 | `core/pipeline_policy.py` | 77% | 21 | policy競合と優先順位 |
| 12 | `core/fuji_policy.py` | 78% | 45 | rolloutとdeny優先分岐 |
| 13 | `core/pipeline_persist.py` | 78% | 25 | 保存失敗時の整合性 |
| 14 | `core/pipeline_retrieval.py` | 78% | 32 | 取得失敗・空結果分岐 |

---

## 6. 改善済みハイライト（2026-03-26時点）

- `compliance/report_engine.py`: 63% → **96%**
- `api/governance.py`: 69% → **97%**
- `core/memory_vector.py`: 39% → **99%**
- `core/memory_store.py`: 43%（CI） → **99%**（focused再計測で再確認） — `_normalize` 旧形式マイグレーション、search/cache/lifecycle 系の回帰を維持
- `core/memory_lifecycle.py`: 65%（CI） → **98%** — parse_expires_at/normalize_lifecycle/is_record_expired/cascade 全独立テスト追加
- `core/memory_compliance.py`: 94%（CI） → **100%** — is_record_legal_hold/should_cascade_delete_semantic 全分岐テスト追加
- focused再計測で高改善:
  - `logging/encryption.py`: **95%（security adversarial suite）**
  - `audit/trustlog_signed.py`: **97%（security adversarial suite）**
  - `tools/web_search_security.py`: **95.3%**

> 注意: 上記のうち focused 値は `trace` ベース。CI branch coverage での再確認を必須とする。

### 6.1 adversarial test 反映（2026-03-26）

- `logging/encryption.py` では以下の異常系を実測済み:
  - missing key
  - invalid key / wrong-length key
  - wrong key
  - corrupted ciphertext（HMAC/IV/body のビット反転含む）
  - truncated payload
  - malformed envelope
  - unsupported marker
  - plaintext fallback 不可（`append_trust_log` 側で `ENC:` 強制）
- `audit/trustlog_signed.py` への波及確認:
  - WORM hard-fail (`VERITAS_TRUSTLOG_WORM_HARD_FAIL=1`) 時に append を fail-closed
  - Transparency required (`VERITAS_TRUSTLOG_TRANSPARENCY_REQUIRED=1`) 時に anchor 失敗を fail-closed
  - 署名破壊/チェーン破壊の検知を adversarial テストで固定化

---

## 7. セキュリティ観点の重点（要警戒）

### 7.1 `logging/encryption.py`（改善済み）

- security adversarial suite で line coverage は **95%**（trace実測）。
- secure-by-default / fail-closed の主要経路（鍵欠落・鍵不正・復号失敗・平文フォールバック拒否）は回帰テスト化済み。
- 残課題は CI branch coverage での再検証（local は pytest-cov 不可のため未実施）。

### 7.2 `logging/trust_log.py`

- `logging/encryption.py` 改善の反面、`trust_log.py` は focused実測で **48%**。
- 主な未カバー帯はローテーション回復経路、I/O 障害、巨大ログ終端復旧など運用障害系。
- ここは hash-chain 継続性と fail-closed 書き込み保証に直結するため、次の重点対象とする。

### 7.3 `tools/web_search_security.py`

- DNS解決不能時のfail-closedやソケット分岐は、**SSRF防御の最終線**。
- ネットワーク例外注入テストの回帰監視を継続すべき。

### 7.4 `core/memory_store.py`

- memory_store focused再計測では **99%**（line-only, trace）を維持。
- ただし `memory.py` 主体の実行では `memory_store.py` は 46–53% に落ちるため、モジュール横断経路での実行依存が残る。
- 保存失敗時の部分成功抑止は整合性に直結。
- `put_episode` 周辺は、書き込み失敗時に**必ずロールバック/同期抑止**を検証する。

---

## 8. 直近アクションプラン（次スプリント）

1. **CI再計測の一本化**
   - focused改善済み3モジュール（encryption/trustlog_signed/web_search_security）を、CI coverageレポートに反映確認。
2. **80%未満モジュールの段階的解消**
   - 目標: 次回で「80%未満モジュール数」を半減。
3. **セキュリティ異常系テストの固定化**
   - 暗号・SSRF・永続化不整合を nightly 回帰セットへ昇格。
4. **品質ゲート強化（提案）**
   - 総合85%に加え、critical modules の下限（例: 90%）を設定。

---

## 9. 再現コマンド（CI相当）

```bash
cd /home/runner/work/veritas_os/veritas_os

pip install pytest pytest-cov httpx pydantic fastapi numpy

OPENAI_API_KEY=DUMMY_FOR_CI \
VERITAS_API_KEY=DUMMY_FOR_CI \
PYTHONUNBUFFERED=1 \
python -m pytest -q veritas_os/tests \
  --cov=veritas_os \
  --cov-config=veritas_os/tests/.coveragerc \
  --cov-report=term-missing \
  --cov-report=xml:coverage.xml \
  --cov-report=html:coverage-html \
  -m "not slow" \
  --durations=20 \
  --tb=short
```

> 注: `production-validation.yml` 側の `pytest -m "production or smoke"` および
> `pytest -m external` は本 coverage 値の再現コマンドではない（別目的の検証）。

---

## 10. 変更履歴（本ドキュメント）

- 2026-03-26: production-like validation 分離に伴う注記を追加。
  - `production-validation.yml` は main coverage 判定から分離される点を明記。
  - `test-slow` は main CI で実行されるが coverage 母集団に含めない点を追記。
  - 再現コマンド節に「production/smoke/external は coverage 再現対象外」の注記を追加。
- 2026-03-26: memory_store 周辺を実測で再更新。
  - CI相当コマンドは `pytest-cov` 未導入で実行不可（Proxy/Tunnel 制約）を再確認。
  - focused再計測（trace）で `core/memory_store.py` 99%、`core/memory_storage.py` 96%、`core/memory.py` 89% を反映。
  - `core/memory_storage.py` の focused 値を 96.9% → 96% に補正（実測値へ揃え込み）。
- 2026-03-26: 構成を再編し、以下を是正。
  - 「80%未満」セクションに混入していた 99% モジュールを除外。
  - CI値とfocused値の目的・比較可否を明確化。
  - セキュリティ上の未到達分岐を独立セクション化。
  - 次アクションを優先順で整理。
- 2026-03-26: security adversarial 実測を反映。
  - `logging/encryption.py` は focused実測 95% のため低位表から除外。
  - `audit/trustlog_signed.py` の fail-closed（WORM/Transparency必須）検証を明記。
  - `logging/trust_log.py` を次の低位セキュリティ重点として追記。
