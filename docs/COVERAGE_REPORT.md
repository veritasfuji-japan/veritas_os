# VERITAS OS — テストカバレッジレポート

**測定日**: 2026-03-24
**Python**: 3.12.3
**OS**: Linux 6.14.0-1017-azure (Ubuntu)
**テストフレームワーク**: pytest 9.0.2 + pytest-cov 7.1.0
**ブランチカバレッジ**: 有効 (.coveragerc で `branch = True`)
**CI カバレッジ基準**: 85% (`--cov-fail-under=85`)

## 全体サマリー

| 指標 | 前回 (2026-02-12) | 今回 (2026-03-24) | 増減 |
|------|-------------------|-------------------|------|
| **全体カバレッジ** | **89%** | **87% (term) / 89.3% (xml)** | ±0〜+0.3% |
| ソースステートメント数 | 10,614 | 18,225 | +7,611 (+72%) |
| ミスしたステートメント | 1,664 | 1,957 | +293 |
| ブランチ数 | 3,530 | 5,672 | +2,142 |
| 部分カバレッジのブランチ | 580 | 714 | +134 |
| テスト数 (passed) | 1,768 | 4,350 | **+2,582 (+146%)** |
| テスト数 (failed) | 4 | 0 | **-4 (全解消)** |
| テスト数 (skipped) | — | 3 | — |
| CI 基準 | — | ✅ パス (87% ≥ 85%) | — |

> **注**: term-missing 出力の 87% と coverage.xml の 89.3% の差は、branch coverage の計算方式の違いによるもの。CI は term-missing ベースの 87% で判定しており、`--cov-fail-under=85` をパスしている。

> **重要**: コードベースが 10,614 → 18,225 ステートメント (+72%) と大幅に増加したにもかかわらず、全体カバレッジは 87〜89% を維持。テスト数は 1,768 → 4,350 (+146%) と 2.5 倍に増加し、以前の 4 件の失敗テストもすべて解消された。

## 重点5モジュールの改善

| モジュール | 前回 (2026-02-12) | 今回 (2026-03-24) | 増減 | Stmts | Miss | Branch | BrPart | コメント |
|-----------|-------------------|-------------------|------|-------|------|--------|--------|---------|
| `core/pipeline.py` | 68% | **98%** | **+30%** | 269 | 6 | 54 | 0 | 大幅改善。リファクタリングと専用テスト追加の成果。ミス 463→6 行。Branch 100% 達成。 |
| `api/server.py` | 74% | **93%** | **+19%** | 240 | 19 | 14 | 0 | 大幅改善。エンドポイントテスト追加の成果。ミス 196→19 行。Branch 100% 達成。 |
| `core/memory.py` | 75% | **94%** | **+19%** | 629 | 27 | 168 | 21 | 大幅改善。VectorMemory/MemoryStore テスト強化の成果。ミス 230→27 行。 |
| `core/kernel.py` | 81% | **94%** | **+13%** | 451 | 21 | 168 | 15 | 大幅改善。分岐テスト強化の成果。ミス 97→21 行。 |
| `core/fuji.py` | 85% | **90%** | **+5%** | 455 | 35 | 142 | 20 | 改善。PII/ポリシーテスト追加の成果。ミス 71→35 行。 |

> **coverage.xml ベースの line_rate**: pipeline.py=97.8%, server.py=92.1%, memory.py=95.7%, kernel.py=95.3%, fuji.py=92.3%

### モジュール分割の効果

大規模モジュールの分割により保守性が向上した。

| 元モジュール | 前回行数 | 今回行数 | サブモジュール例 |
|-------------|---------|---------|---------------|
| `pipeline.py` | 1,614 | 269 | pipeline_gate, pipeline_execute, pipeline_persist, pipeline_helpers 等 |
| `server.py` | 799 | 240 | routes_decide, routes_memory, routes_governance, routes_trust 等 |
| `memory.py` | 984 | 629 | memory_vector, memory_store, memory_storage, memory_lifecycle 等 |

## カバレッジ低位モジュール (80%未満)

| モジュール | Stmts | Miss | Branch | BrPart | カバレッジ | xml line_rate |
|-----------|-------|------|--------|--------|-----------|--------------|
| `core/memory_vector.py` | 210 | 0 | 66 | 1 | **99%** | 100% |
| `core/memory_store.py` | 284 | 152 | 100 | 4 | 43% | 46.5% |
| `core/memory_storage.py` | 82 | 36 | 22 | 4 | 56% | 56.1% |
| `tools/web_search_security.py` | 148 | 53 | 54 | 3 | 59% | 64.2% |
| `compliance/report_engine.py` | 126 | 38 | 34 | 11 | 63% | 69.8% |
| `core/memory_lifecycle.py` | 86 | 25 | 42 | 16 | 65% | 70.9% |
| `logging/encryption.py` | 134 | 43 | 28 | 4 | 67% | 67.9% |
| `core/pipeline_response.py` | 56 | 17 | 20 | 5 | 68% | 69.6% |
| ~~`api/governance.py`~~ | ~~243~~ → 251 | ~~69~~ → 7 | 66 | 3 | ~~69%~~ → **97%** | 97.2% |
| `core/pipeline_execute.py` | 92 | 21 | 26 | 9 | 73% | 77.2% |
| `core/pipeline_gate.py` | 106 | 27 | 20 | 3 | 73% | 74.5% |
| `core/pipeline_helpers.py` | 137 | 30 | 46 | 7 | 74% | 78.1% |
| `core/pipeline_contracts.py` | 112 | 28 | 36 | 9 | 74% | 75.0% |
| `api/routes_decide.py` | 133 | 30 | 26 | 7 | 75% | 77.4% |
| `api/rate_limiting.py` | 123 | 28 | 30 | 3 | 76% | 77.2% |
| `core/pipeline_inputs.py` | 110 | 18 | 40 | 10 | 77% | — |
| `core/pipeline_policy.py` | 121 | 21 | 32 | 10 | 77% | — |
| `core/fuji_policy.py` | 220 | 45 | 68 | 7 | 78% | 79.5% |
| `core/pipeline_persist.py` | 190 | 25 | 54 | 16 | 78% | — |
| `core/pipeline_retrieval.py` | 184 | 32 | 66 | 18 | 78% | — |

## テスト強化の成果

1. **テスト数 2.5 倍増**: 1,768 → 4,350 テスト (+2,582)
2. **失敗テスト全解消**: 4 → 0 (pytest-asyncio 関連の問題を解決)
3. **重点5モジュール全改善**:
   - `pipeline.py`: 68% → **98%** (+30%)
   - `server.py`: 74% → **93%** (+19%)
   - `memory.py`: 75% → **94%** (+19%)
   - `kernel.py`: 81% → **94%** (+13%)
   - `fuji.py`: 85% → **90%** (+5%)
4. **コードベースのリファクタリング**: 大規模モジュールの分割により保守性向上
5. **全体カバレッジ維持**: コードベース 72% 増にもかかわらず 87〜89% を維持
6. **CI 基準超過**: `--cov-fail-under=85` を 87% でパス

## カバレッジ向上の推奨事項 (次の改善に向けて)

| 優先 | モジュール | 現在 | Miss 行 | 改善インパクト | 推奨アクション |
|------|-----------|------|---------|--------------|--------------|
| 1 | `core/memory_store.py` | 43% | 152 | 高 (152 行回収可能) | VectorMemory/MemoryStore の実行パステスト追加。search/get/delete メソッドのテスト。 |
| ~~2~~ | ~~`core/memory_vector.py`~~ | ~~39%~~ → **99%** | ~~116~~ → 0 | ✅ **改善済** | テスト追加により全ステートメント網羅。ブランチも 66/66 の 65 をカバー (BrPart=1)。 |
| ~~2~~ | ~~`api/governance.py`~~ | ~~69%~~ → **97%** | ~~69~~ → 7 | ✅ **改善済** | four-eyes approval・policy CRUD・history append/trim・callback hot-reload・updated_by sanitization のテスト追加。62 行回収。 |
| 3 | `tools/web_search_security.py` | 59% | 53 | 中 (53 行回収可能) | URL 検証・セキュリティチェックのエッジケーステスト追加。 |
| 4 | `core/fuji_policy.py` | 78% | 45 | 中 (45 行回収可能) | ポリシーロールアウト・検証ロジックのブランチテスト追加。 |
| 5 | `logging/encryption.py` | 67% | 43 | 中 (43 行回収可能) | 暗号化・復号のエッジケース (鍵不正、データ破損) テスト追加。 |
| 6 | `compliance/report_engine.py` | 63% | 38 | 中 (38 行回収可能) | EU AI Act コンプライアンスレポート生成のテスト追加。 |
| 7 | `core/memory_storage.py` | 56% | 36 | 中 (36 行回収可能) | ストレージ永続化のテスト追加。ファイル I/O のモックテスト。 |
| 8 | `core/pipeline_retrieval.py` | 78% | 32 | 中 (32 行回収可能) | 検索・取得パスの分岐テスト追加。 |
| 9 | `core/pipeline_helpers.py` | 74% | 30 | 中 (30 行回収可能) | ヘルパー関数の分岐テスト追加。 |

> **合計**: TOP 9 の改善で最大 **498 行** のミスを回収可能。`memory_vector.py` は改善済み (39% → 99%, 116 行回収)。`governance.py` は改善済み (69% → 97%, 62 行回収)。

## 制約・注意点

1. **フルスイート実行**: `not slow` マーク付きテストのみ実行 (CI 相当)。slow テストは除外されている。
2. **前回比較の注意**:
   - 前回レポート (2026-02-12) と今回 (2026-03-24) ではコードベースの構造が大きく変更されている (モジュール分割、リファクタリング)
   - 前回の pipeline.py (1,614行) と今回の pipeline.py (269行) は同名だが実質的に異なるモジュール
   - 同様に server.py (799→240行)、memory.py (984→629行) も分割されている
   - そのため、カバレッジ率の直接比較は参考値として扱うこと
3. **term-missing vs xml の差**: term-missing の 87% と coverage.xml の 89.3% は branch coverage の計算方式の違いによる。CI 判定は term-missing ベース
4. **環境差**: CI は Python 3.11/3.12 のマトリクスで実行するが、今回は 3.12.3 のみで実行
5. **外部依存**: `OPENAI_API_KEY` と `VERITAS_API_KEY` はダミー値で実行。実 API 呼び出しはモックされている

### coverage 再現コマンド

```bash
cd /home/runner/work/veritas_os/veritas_os

# 依存関係インストール
pip install pytest pytest-cov httpx pydantic fastapi numpy

# CI 相当の coverage 計測
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
