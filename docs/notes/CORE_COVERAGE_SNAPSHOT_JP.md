# コア部分カバレッジ・スナップショット

最終更新: 2026-03-06

このメモは、`docs/COVERAGE_REPORT.md` の計測結果から、
コア責務（Planner / Kernel / Fuji / MemoryOS）に関係するモジュールのみを抜粋したものです。

## コア責務ごとのカバレッジ

| 責務 | 対象モジュール | カバレッジ |
|---|---|---:|
| Planner | `core/planner.py` | 91% |
| Kernel | `core/kernel.py` | 81% |
| Fuji Gate | `core/fuji.py` | 85% |
| MemoryOS | `core/memory.py` | 75% |

## 補足

- 参照元は `docs/COVERAGE_REPORT.md` のスナップショット値です。
- この環境では、`uv run ... --with pytest-cov` 実行時に PyPI 接続エラー（`https://pypi.org/simple/fastapi/` への到達失敗）が発生したため、
  新規の再計測は未実施です。
- セキュリティ観点: 依存取得不能の状態では、未検証の依存更新や差分に対するカバレッジ退行を即時検知できないリスクがあります。
