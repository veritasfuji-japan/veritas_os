# VERITAS OS — テストカバレッジレポート

**測定日**: 2026-02-12
**Python**: 3.12.7
**テストフレームワーク**: pytest 9.0.2 + pytest-cov 7.0.0
**ブランチカバレッジ**: 有効

## 全体サマリー

| 指標 | 前回 (2026-02-11) | 今回 (2026-02-12) |
|------|-------------------|-------------------|
| **全体カバレッジ** | **83%** | **92%** |
| ステートメント数 | 11,185 | 24,502 |
| ミスしたステートメント | ~1,650 | 2,033 |
| テスト数 (passed) | 1,758 | 1,762 |
| テスト数 (failed) | 4 | 4 (既知: pytest-asyncio未インストール) |

> failed の 4 件は `pytest-asyncio` 未インストールに起因する非同期テストの失敗で、カバレッジ計測には影響しません。

## ソースファイル別カバレッジ

### api/

| ファイル | ステートメント | ミス | カバレッジ |
|----------|--------------|------|-----------|
| `api/__init__.py` | 0 | 0 | 100% |
| `api/constants.py` | 30 | 0 | 100% |
| `api/dashboard_server.py` | 88 | 20 | 77% |
| `api/evolver.py` | 66 | 4 | 94% |
| `api/schemas.py` | 383 | 38 | 90% |
| `api/server.py` | 799 | 196 | 75% |
| `api/telos.py` | 65 | 0 | 100% |

### core/

| ファイル | ステートメント | ミス | カバレッジ |
|----------|--------------|------|-----------|
| `core/__init__.py` | 42 | 8 | 81% |
| `core/adapt.py` | 138 | 4 | 97% |
| `core/affect.py` | 84 | 3 | 96% |
| `core/agi_goals.py` | 56 | 9 | 84% |
| `core/atomic_io.py` | 92 | 14 | 85% |
| `core/code_planner.py` | 157 | 24 | 85% |
| `core/config.py` | 128 | 0 | 100% |
| `core/critique.py` | 163 | 34 | 79% |
| `core/curriculum.py` | 86 | 2 | 98% |
| `core/debate.py` | 403 | 44 | 89% |
| `core/decision_status.py` | 24 | 0 | 100% |
| `core/evidence.py` | 51 | 1 | 98% |
| `core/experiments.py` | 92 | 9 | 90% |
| `core/fuji.py` | 563 | 71 | 87% |
| `core/fuji_codes.py` | 81 | 6 | 93% |
| `core/identity.py` | 24 | 0 | 100% |
| `core/kernel.py` | 534 | 92 | 83% |
| `core/kernel_qa.py` | 123 | 8 | 93% |
| `core/kernel_stages.py` | 243 | 10 | 96% |
| `core/llm_client.py` | 221 | 18 | 92% |
| `core/logging.py` | 6 | 0 | 100% |
| `core/memory.py` | 984 | 228 | 77% |
| `core/models/memory_model.py` | 61 | 0 | 100% |
| `core/pipeline.py` | 1,614 | 463 | 71% |
| `core/planner.py` | 470 | 34 | 93% |
| `core/reason.py` | 119 | 19 | 84% |
| `core/reflection.py` | 39 | 9 | 77% |
| `core/rsi.py` | 30 | 0 | 100% |
| `core/sanitize.py` | 155 | 13 | 92% |
| `core/self_healing.py` | 130 | 6 | 95% |
| `core/strategy.py` | 100 | 6 | 94% |
| `core/time_utils.py` | 17 | 0 | 100% |
| `core/tools.py` | 141 | 3 | 98% |
| `core/types.py` | 226 | 19 | 92% |
| `core/utils.py` | 113 | 6 | 95% |
| `core/value_core.py` | 179 | 19 | 89% |
| `core/world.py` | 483 | 60 | 88% |

### scripts/

| ファイル | ステートメント | ミス | カバレッジ |
|----------|--------------|------|-----------|
| `scripts/doctor.py` | 202 | 20 | 90% |

### tools/

| ファイル | ステートメント | ミス | カバレッジ |
|----------|--------------|------|-----------|
| `tools/__init__.py` | 13 | 0 | 100% |
| `tools/coverage_map_pipeline.py` | 221 | 13 | 94% |
| `tools/github_adapter.py` | 91 | 16 | 82% |
| `tools/llm_safety.py` | 115 | 8 | 93% |
| `tools/web_search.py` | 231 | 25 | 89% |

## カバレッジが低いモジュール (80%未満)

| ファイル | カバレッジ | ミス行数 | 改善ポイント |
|----------|-----------|---------|-------------|
| `core/pipeline.py` | 71% | 463 | 最大モジュール (1,614行)。非同期 `run_decide_pipeline` 内の nested 関数テスト追加で大幅改善可能 |
| `api/server.py` | 75% | 196 | エンドポイントの統合テスト追加 (pytest-asyncio 導入推奨) |
| `api/dashboard_server.py` | 77% | 20 | ダッシュボード関連のルートテスト追加 |
| `core/memory.py` | 77% | 228 | VectorMemory, MemoryStore の実行パステスト強化 |
| `core/reflection.py` | 77% | 9 | 小規模モジュール。少数のテスト追加で 100% 到達可能 |
| `core/critique.py` | 79% | 34 | 批評ロジックの分岐テスト追加 |

## カバレッジ向上の推奨事項 (95%到達に向けて)

1. **`core/pipeline.py`** (71%, 463行ミス) — 最もインパクトが大きい。非同期パイプラインのテスト追加で全体カバレッジを大幅に引き上げ可能。
2. **`core/memory.py`** (77%, 228行ミス) — VectorMemory・MemoryStore の統合パスをテストすることで改善。
3. **`api/server.py`** (75%, 196行ミス) — pytest-asyncio 導入により FastAPI エンドポイントの統合テストが可能に。
4. **`core/kernel.py`** (83%, 92行ミス) — カーネルの decide/execute 分岐のテスト強化。
5. **`core/fuji.py`** (87%, 71行ミス) — 残りのエッジケースとエラーハンドリング分岐をカバー。
