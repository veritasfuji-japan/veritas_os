# VERITAS OS — テストカバレッジレポート（改善版）

**最終更新日**: 2026-03-26  
**基準スナップショット**: 2026-03-24（CI） + 2026-03-26（web-search-security focused再計測）  
**Python**: 3.12.3  
**OS**: Linux 6.14.0-1017-azure (Ubuntu)  
**テストフレームワーク**: pytest 9.0.2 / pytest-cov 7.1.0（CI）  
**CIカバレッジ基準**: `--cov-fail-under=85`

---

## 1. エグゼクティブサマリー

- **CI判定値（2026-03-24）**: **87%（term-missing）** → ✅ 基準達成（85%以上）
- **XML line_rate（同日）**: **89.3%**
- **CI相当テスト実行（2026-03-26, local）**: **5382 passed / 8 skipped / 0 failed**
- **web-search-security focused実測（2026-03-26, trace line-only）**:
  - `tools/web_search_security.py`: **96%**
  - `tools/web_search.py`: **94%**
  - `tests`: `test_web_search_security.py` **100%** / `test_web_search_adversarial.py` **100%**
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
2. **focused再計測（2026-03-26, web-search-security）**
   - 標準ライブラリ `trace` による line-only coverage
   - `web_search_security.py` / `web_search.py` と adversarial test の改善確認用途
   - CI branch coverage と**直接比較不可**
3. **CI相当再計測の制約（2026-03-26, local）**
   - `pytest --cov ...` は `pytest-cov` 未導入で実行不可
   - `python -m coverage ...` は `coverage.py` 未導入で実行不可
   - 注: この実行環境では外部取得不可のため、local では CI と同一フォーマットのカバレッジ再生成は未実施

### 2.2 term 87% と xml 89.3% の差

- coverageの集計軸（term-missing / xml / branch計算）差分による。
- **CI合否は 87%（term-missing）で判定**する。

### 2.3 production-like validation workflow との関係（2026-03-26）

- `.github/workflows/production-validation.yml` で `@production` / `@smoke` / `@external` を**別workflow**として実行する構成が追加された。
- 本workflowは `--cov` を付けず、coverage gate（85%）にも参加しないため、**本レポートのCI coverage 判定値には直接影響しない**。
- `main.yml` 側の coverage 測定条件（`pytest -m "not slow" ... --cov-fail-under=85`）は維持されているため、coverage再現コマンド自体は据え置きとする。

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
| 2 | `core/pipeline_response.py` | 68% | 17 | 例外整形・戻り値境界テスト |
| 3 | `core/pipeline_execute.py` | 73% | 21 | 実行順序・異常分岐の網羅 |
| 4 | `core/pipeline_gate.py` | 73% | 27 | deny系条件の境界網羅 |
| 5 | `core/pipeline_helpers.py` | 74% | 30 | ヘルパ分岐の入力境界テスト |
| 6 | `core/pipeline_contracts.py` | 74% | 28 | 契約検証の異常値テスト |
| 7 | `api/routes_decide.py` | 75% | 30 | ルーティング失敗・fallback |
| 8 | `api/rate_limiting.py` | 76% | 28 | burst境界・時刻依存分岐 |
| 9 | `core/pipeline_inputs.py` | 77% | 18 | 入力正規化の異常系 |
| 10 | `core/pipeline_policy.py` | 77% | 21 | policy競合と優先順位 |
| 11 | `core/fuji_policy.py` | 78% | 45 | rolloutとdeny優先分岐 |
| 12 | `core/pipeline_persist.py` | 78% | 25 | 保存失敗時の整合性 |
| 13 | `core/pipeline_retrieval.py` | 78% | 32 | 取得失敗・空結果分岐 |
| 14 | `tools/web_search_security.py` | 59%（CI） / 96%（focused） | 53 | 改善済み（高強度 adversarial 回帰を継続） |

---

## 6. 改善済みハイライト（2026-03-26時点）

- `tools/web_search_security.py`: 59%（CI） → **96%**（focused再計測）
- `tools/web_search.py`: focused再計測 **94%**
- SSRF / DNS rebinding / confusable hostname / malformed URL の adversarial 回帰を 171件（`test_web_search_security.py` + `test_web_search_adversarial.py`）で再実測

> 注意: 上記のうち focused 値は `trace` ベース。CI branch coverage での再確認を必須とする。

### 6.1 adversarial test 反映（2026-03-26, web-search-security）

- 実測コマンド: `pytest -q test_web_search_security.py test_web_search_adversarial.py` → **171 passed**
- 追加済み adversarial 観点（回帰固定化済み）:
  - **NFKC confusable**（fullwidth host/文字、互換文字）
  - **homoglyph hostname**（Cyrillic/Greek 混在）
  - **trailing dot**（`example.com.` / `...`）
  - **internal TLD**（`.internal`, `.corp`, `.lan`, `.private` など）
  - **embedded credentials**（`user@host`, `user:@host`）
  - **rebinding mismatch**（DNS結果の差分検知）
  - **malformed URL**（`file:`, `javascript:`, `data:`, 空URL/空host）
  - **allowlist boundary**（suffix偽装拒否、exact/subdomainのみ許可）
- 文章評価:
  - SSRF は「private/local host + malformed scheme + embedded credentials」の多層拒否がテストで確認された。
  - DNS rebinding は request-time 再解決との差分検知で fail-closed を確認した。
  - confusable/homoglyph は NFKC + non-LDH 判定 + Unicodeエラー時ブロックで防御を確認した。

---

## 7. セキュリティ観点の重点（要警戒）

### 7.1 `tools/web_search_security.py`（改善済み）

- focused実測で line coverage は **96%**（trace）。
- DNS解決不能時の fail-closed・ソケット例外・Unicode/IDNAエラー時ブロックは回帰テストで確認済み。
- CI branch coverage では依然 59%（2026-03-24）であるため、CI側への同等 adversarial セット統合は継続課題。

### 7.2 `tools/web_search.py`

- focused実測で **94%**（trace）。
- retrieval poisoning対策（NFKC/可視化不可文字/URLエンコード/Base64/leetspeak）の adversarial テスト経路を実測済み。
- 残課題は CI branch coverage での再確認（localでは pytest-cov 未導入）。

---

## 8. 直近アクションプラン（次スプリント）

1. **CI再計測の一本化**
   - web-search-security focused測定（96%/94%）を CI coverage レポートに反映確認。
2. **80%未満モジュールの段階的解消**
   - CI branch coverage で 80% 未満のモジュール数を継続削減。
3. **セキュリティ異常系テストの固定化**
   - SSRF・DNS rebinding・malformed URL を nightly 回帰セットへ昇格。
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

### 9.1 参考: production-like validation（coverage外）

> 以下は coverage 集計用ではなく、運用系の本番相当検証を行うための補助コマンド。

```bash
# Separate workflow と同等のローカル実行（coverage には加算しない）
python -m pytest -q veritas_os/tests -m "production or smoke" --durations=20 --tb=short

# slow テストの分離実行（main.yml の test-slow 相当）
python -m pytest -q veritas_os/tests -m slow --durations=20 --tb=short
```

---

## 10. 変更履歴（本ドキュメント）

- 2026-03-26: 80%未満モジュール改善のうち、`pipeline/fuji_policy` 経路の回帰テストを増強。
  - 追加テスト: `test_pipeline_fuji_policy_paths.py`（9件）
  - 追加観点:
    - fail-closed FUJI precheck ペイロード契約
    - `stage_fuji_precheck` の未知ステータス正規化 / NaN リスク fail-closed
    - `stage_gate_decision` の Debate `risk_delta` 異常値分岐
    - 高リスクかつ低 telos の reject 分岐
    - `fuji_policy` の絶対パス逸脱フォールバック
    - YAML parse error フォールバック
    - action precedence 異常値の fail-closed 優先
    - policy hot reload の missing path / reload 経路
  - ローカル実行結果: `python -m pytest -q veritas_os/tests/test_pipeline_fuji_policy_paths.py` → 9 passed
- 2026-03-26: web-search-security 周辺を実測で再更新。
  - CI相当コマンドは `pytest-cov` / `coverage.py` 未導入で local 実行不可を再確認。
  - focused再計測（trace）で `tools/web_search_security.py` 96%、`tools/web_search.py` 94% を反映。
  - adversarial 回帰 171件（`test_web_search_security.py` + `test_web_search_adversarial.py`）の実行結果を反映。
  - 低位モジュール表の `tools/web_search_security.py` を「改善中」から「改善済み（回帰継続）」へ更新。
- 2026-03-26: production-like validation 分離に伴う注記を追加。
  - `production-validation.yml` は coverage gate 非対象であり、本レポートの CI coverage 判定値へ直接影響しない点を明記。
  - `main.yml` の coverage 再現条件（`-m "not slow"` + `--cov-fail-under=85`）は不変であることを追記。
  - 参考情報として、coverage 外の `production or smoke` / `slow` 分離実行コマンドを付記。
