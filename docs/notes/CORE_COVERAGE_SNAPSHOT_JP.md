# コア部分カバレッジ・スナップショット

最終更新: 2026-03-06（再測定）

このメモは、コア責務（Planner / Kernel / Fuji / MemoryOS）について、
この環境で再実行したテストを `trace` で計測した結果です。

## 再測定結果（trace ベース）

| 責務 | 対象モジュール | カバレッジ |
|---|---|---:|
| Planner | `core/planner.py` | 95% |
| Kernel | `core/kernel.py` | 92% |
| Fuji Gate | `core/fuji.py` | 88% |
| MemoryOS | `core/memory.py` | 81% |

## 実行コマンド

```bash
python3 -m trace --count --summary --missing --module pytest -q veritas_os/tests -k 'planner or kernel or fuji or memory' > /tmp/trace_summary.txt 2>&1
python3 -m trace --count --summary --missing --module pytest -q veritas_os/tests/test_memory_coverage.py veritas_os/tests/test_memory_extra_v2.py veritas_os/tests/test_memory_advanced.py > /tmp/trace_memory.txt 2>&1
```

## 補足

- `pytest-cov` / `coverage.py` はこの環境で追加インストール不可（Proxy/Tunnel 制約）だったため、標準ライブラリ `trace` を代替利用しました。
- `trace` と `pytest-cov` では集計方法が異なるため、`docs/COVERAGE_REPORT.md` の値とは一致しない可能性があります。
- セキュリティ観点: 依存取得が制限された環境では、通常のCIと同一条件でのカバレッジ退行検知が遅れるリスクがあります。
