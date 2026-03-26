# VERITAS OS — テストカバレッジレポート（改善版）

**最終更新日**: 2026-03-26  
**基準スナップショット**: 2026-03-24（CI） + 2026-03-26（focused再計測・ローカル再実測）  
**Python**: 3.12.3  
**OS**: Linux 6.14.0-1017-azure (Ubuntu)  
**テストフレームワーク**: pytest 9.0.2 / pytest-cov 7.1.0（CI）  
**CIカバレッジ基準**: `--cov-fail-under=85`

---

## 1. エグゼクティブサマリー

- **CI判定値（2026-03-24）**: **87%（term-missing）** → ✅ 基準達成（85%以上）
- **XML line_rate（同日）**: **89.3%**
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
2. **focused再計測（2026-03-26, ローカル）**
   - 標準ライブラリ `trace` による line-only coverage
   - `memory_store*` / `memory_storage` / `memory_core` 系テストを中心に再実測
   - CI branch coverage と**直接比較不可**
3. **CI相当コマンド実行可否（2026-03-26, ローカル）**
   - `pytest-cov` 未導入のため `--cov` オプションは実行不可（pytest引数エラー）
   - 代替として `pytest -q veritas_os/tests -m "not slow" --durations=20 --tb=short` を実行し、
     回帰健全性（5,382 passed / 8 skipped）を確認

### 2.2 term 87% と xml 89.3% の差

- coverageの集計軸（term-missing / xml / branch計算）差分による。
- **CI合否は 87%（term-missing）で判定**する。

### 2.3 2026-03-26 実測ログ（抜粋）

- focused（memory系サブセットA）:
  - `core/memory_store.py`: **53%**
  - `core/memory.py`: **75%**
  - `core/memory_storage.py`: **96%**
  - 実行テスト: 407 passed / 5 skipped
- focused（memory_store専用サブセットB）:
  - `core/memory_store.py`: **99%**
  - 実行テスト: 266 passed
- CI相当（coverageなし健全性確認）:
  - 実行テスト: **5,382 passed / 8 skipped**

> 解釈: `trace` は line-only かつテスト集合依存のため、A/B の値は「改善寄与の切り出し確認」として扱う。

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
| 1 | `core/memory_storage.py` | 56%（CI） / 96.0%（focused, 2026-03-26再実測） | 36 | 永続化失敗・I/O異常分岐のCI統合 |
| 2 | `tools/web_search_security.py` | 59%（CI） / 95.3%（focused） | 53 | DNS/ソケット例外分岐の常時回帰テスト化 |
| 3 | `logging/encryption.py` | 67%（CI） / 88.0%（focused） | 43 | 暗号バックエンド障害時のfail-closed経路を強化 |
| 4 | `core/pipeline_response.py` | 68% | 17 | 例外整形・戻り値境界テスト |
| 5 | `core/pipeline_execute.py` | 73% | 21 | 実行順序・異常分岐の網羅 |
| 6 | `core/pipeline_gate.py` | 73% | 27 | deny系条件の境界網羅 |
| 7 | `core/pipeline_helpers.py` | 74% | 30 | ヘルパ分岐の入力境界テスト |
| 8 | `core/pipeline_contracts.py` | 74% | 28 | 契約検証の異常値テスト |
| 9 | `api/routes_decide.py` | 75% | 30 | ルーティング失敗・fallback |
| 10 | `api/rate_limiting.py` | 76% | 28 | burst境界・時刻依存分岐 |
| 11 | `core/pipeline_inputs.py` | 77% | 18 | 入力正規化の異常系 |
| 12 | `core/pipeline_policy.py` | 77% | 21 | policy競合と優先順位 |
| 13 | `core/fuji_policy.py` | 78% | 45 | rolloutとdeny優先分岐 |
| 14 | `core/pipeline_persist.py` | 78% | 25 | 保存失敗時の整合性 |
| 15 | `core/pipeline_retrieval.py` | 78% | 32 | 取得失敗・空結果分岐 |

---

## 6. 改善済みハイライト（2026-03-26時点）

- `compliance/report_engine.py`: 63% → **96%**
- `api/governance.py`: 69% → **97%**
- `core/memory_vector.py`: 39% → **99%**
- `core/memory_store.py`: 43%（CI） → **99%**（`test_memory_store*` focused） — `_normalize` 旧形式マイグレーションの型安全化、search/cache/lifecycle 全分岐網羅
  - 補足: `memory_core` まで含めた広域focusedでは 53%（line-only）であり、計測対象セット差分が大きい
- `core/memory_lifecycle.py`: 65%（CI） → **98%** — parse_expires_at/normalize_lifecycle/is_record_expired/cascade 全独立テスト追加
- `core/memory_compliance.py`: 94%（CI） → **100%** — is_record_legal_hold/should_cascade_delete_semantic 全分岐テスト追加
- focused再計測で高改善:
  - `logging/encryption.py`: **88.0%**
  - `tools/web_search_security.py`: **95.3%**

> 注意: 上記のうち focused 値は `trace` ベース。CI branch coverage での再確認を必須とする。

---

## 7. セキュリティ観点の重点（要警戒）

### 7.1 `logging/encryption.py`

- 未到達には、暗号バックエンド切替例外や不正envelope処理が含まれる。
- ここが欠けると、**誤設定時のfail-open（平文許容）リスク**につながる。

### 7.2 `tools/web_search_security.py`

- DNS解決不能時のfail-closedやソケット分岐は、**SSRF防御の最終線**。
- ネットワーク例外注入テストの回帰監視を継続すべき。

### 7.3 `core/memory_store.py`

- 保存失敗時の部分成功抑止は整合性に直結。
- `put_episode` 周辺は、書き込み失敗時に**必ずロールバック/同期抑止**を検証する。

---

## 8. 直近アクションプラン（次スプリント）

1. **CI再計測の一本化（最優先）**
   - focused改善済みモジュール（memory_store/memory_storage/encryption/web_search_security）を、`pytest-cov` 有効環境で branch coverage 再確認。
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

---

## 10. 変更履歴（本ドキュメント）

- 2026-03-26: 構成を再編し、以下を是正。
  - 「80%未満」セクションに混入していた 99% モジュールを除外。
  - CI値とfocused値の目的・比較可否を明確化。
  - セキュリティ上の未到達分岐を独立セクション化。
  - 次アクションを優先順で整理。
- 2026-03-26: `memory_store.py` 完了後のローカル再実測を反映。
  - CI相当コマンドの実行可否（`pytest-cov` 未導入）を明記。
  - `trace` による focused A/B 実測値（memory_store/memory/memory_storage）を追記。
  - `core/memory_storage.py` の focused 値を 96.0% に更新。
  - memory_store は「focused条件依存で 53% / 99% の両観測」を注記。
