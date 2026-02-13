# VERITAS OS — テストカバレッジレポート

**測定日**: 2026-02-12
**Python**: 3.12.3
**テストフレームワーク**: pytest + pytest-cov
**ブランチカバレッジ**: 有効

## 全体サマリー

| 指標 | 前回 (2026-02-11) | 今回 (2026-02-12) |
|------|-------------------|-------------------|
| **全体カバレッジ** | **83%** | **89%** |
| ソースステートメント数 | 10,614 | 10,614 |
| ミスしたステートメント | ~1,900 | 1,664 |
| ブランチ数 | 3,530 | 3,530 |
| 部分カバレッジのブランチ | ~740 | 580 |
| テスト数 (passed) | 1,758 | 1,768 |
| テスト数 (failed) | 4 | 4 (既知: pytest-asyncio未インストール) |
| テストファイル数 | 87 | 87 |

> failed のテスト 4 件は `pytest-asyncio` 未インストールに起因する `test_integration_pipeline.py` の非同期テストの失敗で、カバレッジ計測には影響しません。

## モジュール別カバレッジ

### API モジュール

| モジュール | ステートメント | ミス | ブランチ | 部分 | カバレッジ |
|-----------|-------------|------|---------|------|-----------|
| `api/__init__.py` | 0 | 0 | 0 | 0 | 100% |
| `api/constants.py` | 30 | 0 | 2 | 0 | 100% |
| `api/telos.py` | 65 | 0 | 2 | 1 | 99% |
| `api/evolver.py` | 66 | 4 | 14 | 4 | 90% |
| `api/schemas.py` | 383 | 38 | 134 | 16 | 86% |
| `api/dashboard_server.py` | 88 | 20 | 18 | 4 | 75% |
| `api/server.py` | 799 | 196 | 236 | 46 | 74% |

### Core モジュール

| モジュール | ステートメント | ミス | ブランチ | 部分 | カバレッジ |
|-----------|-------------|------|---------|------|-----------|
| `core/decision_status.py` | 24 | 0 | 2 | 0 | 100% |
| `core/identity.py` | 24 | 0 | 12 | 0 | 100% |
| `core/logging.py` | 6 | 0 | 0 | 0 | 100% |
| `core/models/memory_model.py` | 61 | 0 | 14 | 0 | 100% |
| `core/rsi.py` | 30 | 0 | 0 | 0 | 100% |
| `core/time_utils.py` | 17 | 0 | 4 | 0 | 100% |
| `core/config.py` | 128 | 0 | 32 | 3 | 98% |
| `core/curriculum.py` | 86 | 2 | 26 | 1 | 97% |
| `core/evidence.py` | 51 | 1 | 16 | 1 | 97% |
| `core/kernel_stages.py` | 243 | 10 | 56 | 3 | 96% |
| `core/utils.py` | 113 | 6 | 50 | 1 | 96% |
| `core/affect.py` | 84 | 3 | 36 | 3 | 95% |
| `core/tools.py` | 141 | 3 | 46 | 7 | 95% |
| `core/adapt.py` | 138 | 4 | 56 | 7 | 94% |
| `core/self_healing.py` | 130 | 6 | 40 | 6 | 93% |
| `core/kernel_qa.py` | 123 | 8 | 44 | 5 | 92% |
| `core/planner.py` | 470 | 34 | 208 | 19 | 91% |
| `core/llm_client.py` | 221 | 18 | 92 | 11 | 91% |
| `core/strategy.py` | 100 | 6 | 28 | 5 | 91% |
| `core/sanitize.py` | 155 | 13 | 56 | 7 | 90% |
| `core/experiments.py` | 92 | 9 | 30 | 4 | 88% |
| `core/fuji_codes.py` | 81 | 6 | 20 | 6 | 88% |
| `core/debate.py` | 403 | 44 | 192 | 35 | 86% |
| `core/types.py` | 226 | 19 | 14 | 0 | 86% |
| `core/world.py` | 483 | 61 | 116 | 21 | 86% |
| `core/fuji.py` | 563 | 71 | 202 | 32 | 85% |
| `core/value_core.py` | 179 | 19 | 56 | 14 | 85% |
| `core/atomic_io.py` | 92 | 14 | 10 | 3 | 83% |
| `core/agi_goals.py` | 56 | 9 | 18 | 4 | 82% |
| `core/code_planner.py` | 157 | 24 | 36 | 11 | 81% |
| `core/kernel.py` | 547 | 97 | 172 | 27 | 81% |
| `core/reflection.py` | 39 | 9 | 14 | 1 | 81% |
| `core/critique.py` | 163 | 34 | 62 | 5 | 80% |
| `core/reason.py` | 119 | 19 | 36 | 11 | 78% |
| `core/__init__.py` | 42 | 8 | 10 | 4 | 77% |
| `core/memory.py` | 984 | 230 | 348 | 73 | 75% |
| `core/pipeline.py` | 1,614 | 463 | 600 | 135 | 68% |

### Scripts モジュール

| モジュール | ステートメント | ミス | ブランチ | 部分 | カバレッジ |
|-----------|-------------|------|---------|------|-----------|
| `scripts/doctor.py` | 202 | 20 | 82 | 6 | 88% |
| `scripts/alert_doctor.py` | 125 | 75 | 40 | 5 | 37% |

### Tools モジュール

| モジュール | ステートメント | ミス | ブランチ | 部分 | カバレッジ |
|-----------|-------------|------|---------|------|-----------|
| `tools/__init__.py` | 13 | 0 | 6 | 0 | 100% |
| `tools/coverage_map_pipeline.py` | 221 | 13 | 82 | 7 | 93% |
| `tools/llm_safety.py` | 115 | 8 | 38 | 7 | 90% |
| `tools/web_search.py` | 231 | 25 | 100 | 16 | 86% |
| `tools/github_adapter.py` | 91 | 16 | 22 | 4 | 79% |

## テストファイル一覧 (テスト数 上位20)

| テストファイル | テスト数 | 対象モジュール |
|---------------|---------|---------------|
| `test_planner_coverage.py` | 86 | `core/planner.py` |
| `test_pipeline_coverage_boost2.py` | 71 | `core/pipeline.py` |
| `test_fuji_coverage.py` | 64 | `core/fuji.py` |
| `test_server_coverage.py` | 63 | `api/server.py` |
| `test_schemas_coverage.py` | 62 | `api/schemas.py` |
| `test_memory_coverage.py` | 60 | `core/memory.py` |
| `test_sanitize_pii.py` | 55 | `core/sanitize.py` |
| `test_api_server_extra.py` | 44 | `api/server.py` |
| `test_utils_coverage.py` | 43 | `core/utils.py` |
| `test_kernel_coverage.py` | 42 | `core/kernel.py` |
| `test_llm_client.py` | 37 | `core/llm_client.py` |
| `test_doctor_coverage.py` | 37 | `scripts/doctor.py` |
| `test_debate_extra.py` | 36 | `core/debate.py` |
| `test_kernel_core_extra.py` | 35 | `core/kernel.py` |
| `test_coverage_map_extra.py` | 33 | `tools/coverage_map_pipeline.py` |
| `test_kernel_stages.py` | 32 | `core/kernel_stages.py` |
| `test_config_coverage.py` | 31 | `core/config.py` |
| `test_web_search_extra.py` | 29 | `tools/web_search.py` |
| `test_fuji_core.py` | 28 | `core/fuji.py` |
| `test_kernel_stages_coverage.py` | 28 | `core/kernel_stages.py` |

## カバレッジ低位モジュール (80%未満)

| モジュール | カバレッジ | ステートメント | ミス | 改善の方向性 |
|-----------|-----------|-------------|------|-------------|
| `scripts/alert_doctor.py` | 37% | 125 | 75 | CLI実行パスのテスト追加 |
| `core/pipeline.py` | 68% | 1,614 | 463 | 最大モジュール。`run_decide_pipeline` 内の nested 関数テスト追加で大幅改善可能 |
| `api/server.py` | 74% | 799 | 196 | エンドポイント統合テスト追加 (pytest-asyncio 導入推奨) |
| `core/memory.py` | 75% | 984 | 230 | VectorMemory, MemoryStore の実行パステスト強化 |
| `api/dashboard_server.py` | 75% | 88 | 20 | ダッシュボードエンドポイントのテスト追加 |
| `core/__init__.py` | 77% | 42 | 8 | 初期化パスの網羅 |
| `core/reason.py` | 78% | 119 | 19 | 推論パスのエッジケーステスト追加 |
| `tools/github_adapter.py` | 79% | 91 | 16 | GitHub API モックテスト追加 |

## カバレッジ向上の推奨事項 (90%到達に向けて)

1. **`core/pipeline.py`** (68%) — 最大モジュール (1,614行)。非同期 `run_decide_pipeline` 内の nested 関数テスト追加で大幅改善可能。ミス 463行の削減が全体カバレッジに最も効果的。
2. **`core/memory.py`** (75%) — 984行中 230行がミス。VectorMemory, MemoryStore の実行パステスト強化。
3. **`api/server.py`** (74%) — エンドポイントの統合テスト追加 (pytest-asyncio 導入推奨)。196行のミス削減で大きな改善。
4. **`scripts/alert_doctor.py`** (37%) — 最低カバレッジ。CLI 実行パスのモックテスト追加。
5. **`core/kernel.py`** (81%) — 97行のミス。カーネル実行パスの分岐テスト強化。
6. **`core/debate.py`** (86%) — 44行のミス。ディベートロジックの分岐テスト追加。
