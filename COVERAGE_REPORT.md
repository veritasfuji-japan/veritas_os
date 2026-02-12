# VERITAS OS — テストカバレッジレポート

**測定日**: 2026-02-11  
**Python**: 3.12.3  
**テストフレームワーク**: pytest + pytest-cov  
**ブランチカバレッジ**: 有効

## 全体サマリー

| 指標 | 前回 (2026-02-11) | 今回 |
|------|-------------------|------|
| **全体カバレッジ** | **76%** | **83%** |
| ステートメント数 | 11,185 | 11,185 |
| ミスしたステートメント | 2,301 | ~1,650 |
| ブランチ数 | 3,696 | 3,696 |
| 部分カバレッジのブランチ | 741 | ~621 |
| テスト数 (passed) | 1,132 | 1,758 |
| テスト数 (failed) | 4 | 4 (既知: pytest-asyncio未インストール) |

> failed のテスト 4 件は `pytest-asyncio` 未インストールに起因する非同期テストの失敗で、カバレッジ計測には影響しません。

## 追加したテストファイル

| テストファイル | 対象モジュール | テスト数 |
|---------------|---------------|---------|
| `test_doctor_coverage.py` | `scripts/doctor.py` | 37 |
| `test_kernel_stages_coverage.py` | `core/kernel_stages.py` | 28 |
| `test_pipeline_coverage_boost2.py` | `core/pipeline.py` | 90 |
| `test_self_healing_coverage.py` | `core/self_healing.py` | 30 |
| `test_utils_coverage.py` | `core/utils.py` | 37 |
| `test_server_coverage.py` | `api/server.py` | 63 |
| `test_memory_coverage.py` | `core/memory.py` | 66 |
| `test_fuji_coverage.py` | `core/fuji.py` | 64 |
| `test_schemas_coverage.py` | `api/schemas.py` | 62 |
| `test_kernel_coverage.py` | `core/kernel.py` | 42 |
| `test_planner_coverage.py` | `core/planner.py` | 86 |
| `test_config_coverage.py` | `core/config.py` | 31 |

## カバレッジ向上の推奨事項 (85%到達に向けて)

1. **`core/pipeline.py`** — 最大モジュール (1,614行)。非同期 `run_decide_pipeline` 内の nested 関数テスト追加で大幅改善可能。
2. **`api/server.py`** — エンドポイントの統合テスト追加 (pytest-asyncio 導入推奨)。
3. **`core/kernel_stages.py`** — memory/world/debate モジュールとの統合パスのモック修正。
4. **`core/memory.py`** — VectorMemory, MemoryStore の実行パステスト強化。
