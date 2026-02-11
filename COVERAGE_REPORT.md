# VERITAS OS — テストカバレッジレポート

**測定日**: 2026-02-11  
**Python**: 3.12.3  
**テストフレームワーク**: pytest + pytest-cov  
**ブランチカバレッジ**: 有効

## 全体サマリー

| 指標 | 値 |
|------|-----|
| **全体カバレッジ** | **76%** |
| ステートメント数 | 11,185 |
| ミスしたステートメント | 2,301 |
| ブランチ数 | 3,696 |
| 部分カバレッジのブランチ | 741 |
| テスト数 (passed) | 1,132 |
| テスト数 (failed) | 4 |

> failed のテスト 4 件は `pytest-asyncio` 未インストールに起因する非同期テストの失敗で、カバレッジ計測には影響しません。

## モジュール別カバレッジ

### カバレッジ 100%

| モジュール | Stmts | Miss | Branch | BrPart | Cover |
|-----------|-------|------|--------|--------|-------|
| `api/constants.py` | 30 | 0 | 2 | 0 | 100% |
| `core/decision_status.py` | 24 | 0 | 2 | 0 | 100% |
| `core/identity.py` | 24 | 0 | 12 | 0 | 100% |
| `core/logging.py` | 6 | 0 | 0 | 0 | 100% |
| `core/models/memory_model.py` | 61 | 0 | 14 | 0 | 100% |
| `core/rsi.py` | 30 | 0 | 0 | 0 | 100% |
| `core/time_utils.py` | 17 | 0 | 4 | 0 | 100% |

### カバレッジ 90%–99%

| モジュール | Stmts | Miss | Branch | BrPart | Cover |
|-----------|-------|------|--------|--------|-------|
| `api/telos.py` | 65 | 0 | 2 | 1 | 99% |
| `core/curriculum.py` | 86 | 2 | 26 | 1 | 97% |
| `core/evidence.py` | 51 | 1 | 16 | 1 | 97% |
| `core/tools.py` | 141 | 3 | 46 | 7 | 95% |
| `core/affect.py` | 84 | 3 | 36 | 3 | 95% |
| `core/adapt.py` | 138 | 4 | 56 | 7 | 94% |
| `memory/index_cosine.py` | 100 | 7 | 24 | 1 | 94% |
| `tools/coverage_map_pipeline.py` | 219 | 12 | 80 | 6 | 93% |
| `core/critique.py` | 139 | 11 | 54 | 4 | 92% |
| `core/kernel_qa.py` | 123 | 8 | 44 | 5 | 92% |
| `core/strategy.py` | 100 | 6 | 28 | 5 | 91% |
| `api/dashboard_server.py` | 72 | 5 | 14 | 3 | 91% |
| `core/llm_client.py` | 221 | 18 | 92 | 11 | 91% |
| `core/sanitize.py` | 155 | 13 | 56 | 7 | 90% |
| `api/evolver.py` | 66 | 4 | 14 | 4 | 90% |
| `tools/llm_safety.py` | 115 | 8 | 38 | 7 | 90% |

### カバレッジ 80%–89%

| モジュール | Stmts | Miss | Branch | BrPart | Cover |
|-----------|-------|------|--------|--------|-------|
| `core/experiments.py` | 92 | 9 | 30 | 4 | 88% |
| `core/fuji_codes.py` | 81 | 6 | 20 | 6 | 88% |
| `logging/trust_log.py` | 200 | 19 | 54 | 11 | 88% |
| `core/debate.py` | 403 | 44 | 192 | 35 | 86% |
| `core/world.py` | 483 | 61 | 116 | 21 | 86% |
| `tools/web_search.py` | 231 | 25 | 100 | 16 | 86% |
| `logging/rotate.py` | 69 | 6 | 18 | 6 | 86% |
| `core/value_core.py` | 179 | 19 | 56 | 14 | 85% |
| `core/types.py` | 234 | 23 | 14 | 0 | 85% |
| `memory/embedder.py` | 21 | 2 | 6 | 2 | 85% |
| `logging/dataset_writer.py` | 162 | 25 | 56 | 9 | 84% |
| `core/code_planner.py` | 151 | 19 | 34 | 10 | 83% |
| `core/atomic_io.py` | 92 | 14 | 10 | 3 | 83% |
| `core/agi_goals.py` | 56 | 9 | 18 | 4 | 82% |
| `core/reflection.py` | 39 | 9 | 14 | 1 | 81% |
| `logging/paths.py` | 70 | 12 | 22 | 6 | 80% |

### カバレッジ 70%–79%

| モジュール | Stmts | Miss | Branch | BrPart | Cover |
|-----------|-------|------|--------|--------|-------|
| `core/config.py` | 128 | 20 | 32 | 11 | 79% |
| `tools/github_adapter.py` | 91 | 16 | 22 | 4 | 79% |
| `core/reason.py` | 119 | 19 | 36 | 11 | 78% |
| `memory/engine.py` | 12 | 0 | 10 | 5 | 77% |
| `memory/store.py` | 172 | 36 | 54 | 16 | 77% |
| `core/planner.py` | 470 | 94 | 208 | 49 | 76% |
| `core/kernel.py` | 534 | 128 | 168 | 33 | 75% |
| `api/schemas.py` | 383 | 77 | 134 | 36 | 72% |
| `core/fuji.py` | 563 | 142 | 202 | 38 | 70% |
| `core/memory.py` | 984 | 269 | 348 | 79 | 70% |

### カバレッジ 70% 未満

| モジュール | Stmts | Miss | Branch | BrPart | Cover |
|-----------|-------|------|--------|--------|-------|
| `api/server.py` | 799 | 229 | 236 | 66 | 69% |
| `core/pipeline.py` | 1,614 | 522 | 600 | 146 | 65% |
| `core/self_healing.py` | 130 | 39 | 40 | 12 | 65% |
| `core/utils.py` | 113 | 38 | 50 | 3 | 65% |
| `core/kernel_stages.py` | 243 | 110 | 56 | 8 | 56% |
| `scripts/doctor.py` | 200 | 155 | 80 | 3 | 19% |

## カバレッジ向上の推奨事項

1. **`scripts/doctor.py` (19%)** — 最もカバレッジが低いモジュール。診断スクリプトのテスト追加が最優先。
2. **`core/kernel_stages.py` (56%)** — カーネルステージ処理の未テスト部分が多い。
3. **`core/pipeline.py` (65%)** — 最大のモジュール（1,614 ステートメント）。影響範囲が広いためテスト強化を推奨。
4. **`api/server.py` (69%)** — API エンドポイントのテスト補強が必要。
5. **`core/self_healing.py` (65%)** — 自己修復ロジックの境界条件テスト追加を推奨。
