# Backend Core 精密再レビュー（Planner / Kernel / Fuji / MemoryOS）

作成日: 2026-03-02  
対象: `veritas_os/core/planner.py`, `veritas_os/core/kernel.py`, `veritas_os/core/fuji.py`, `veritas_os/memory/store.py`

## 1. レビュー方針

- 既存の精密レビュー指摘（F-01 / P-01 / M-01）について、実装反映状況を再検証。
- セキュリティ観点（fail-safe・パス制約・サブプロセス安全性・監査性）を重点確認。
- 責務境界（Planner / Kernel / Fuji / MemoryOS）を越えない改善余地のみ抽出。

## 2. 結論（要約）

- **前回の主要指摘は概ね反映済み**。
  - Planner: フォールバック理由の記録と warning ログが実装済み。
  - Fuji: YAML ポリシーロード失敗時の可観測ログと strict モードが実装済み。
  - MemoryOS: 保存先ディレクトリの監査ログ、production allowlist、`0o700` 作成が実装済み。
- Kernel の doctor 自動起動は、引き続き `shell=False`・固定 argv・`O_NOFOLLOW` を維持し、主要な実行経路リスクは低い。

## 3. 詳細評価

### 3.1 Planner

- `generate_code_tasks()` の code planner 経路失敗時、`planner_fallback_reason` を保持し、`logger.warning(..., exc_info=True)` で原因を観測可能化している。
- これにより silent fallback の運用リスクは大きく低減。
- 追加改善案（低優先）:
  - 監視基盤で `planner_fallback_reason` の集計メトリクスを作ると、回帰検知速度がさらに上がる。

### 3.2 Fuji

- `_load_policy()` / `_load_policy_from_str()` で YAML 例外を拾い、`_fallback_policy()` を経由して理由付きログを出力する設計になっている。
- `VERITAS_FUJI_STRICT_POLICY_LOAD` 有効時は fail-closed（deny 側）として振る舞えるため、セキュリティ運用に適した形。
- 追加改善案（低優先）:
  - strict モードの有効/無効状態を起動時に 1 回だけ INFO 出力すると運用把握が容易。

### 3.3 MemoryOS

- `_resolve_memory_dir()` で resolved path を INFO 出力し、production では allowlist prefix を必須化。
- `HOME_MEMORY.mkdir(mode=0o700, ...)` が導入され、ディレクトリ権限は改善済み。
- **セキュリティ警告（運用注意）**:
  - 非 production プロファイルでは allowlist 制約が効かないため、ステージング/開発環境で `VERITAS_MEMORY_DIR` を誤設定すると、意図しない場所に機微データを書き出す可能性は残る。
  - 対応策として、ステージングでも `VERITAS_ENV=production` 相当のガードを有効化する運用を推奨。

### 3.4 Kernel

- doctor 自動起動の安全策（confinement 要求、rate limit、`shell=False`、固定コマンド、log fd 検証）は維持。
- 現時点で責務内の重大欠陥は未検出。
- 追加改善案（低優先）:
  - `extras["doctor"]` の skip 理由を継続的に可視化（ダッシュボード化）すると運用障害解析が速くなる。

## 4. 優先度付きアクション（再レビュー時点）

1. **運用**: ステージングを含む常設環境で Memory 保存先ガード（allowlist）を有効化。
2. **監視**: Planner fallback reason と doctor skip reason の集計を追加。
3. **文書**: Fuji strict policy load の推奨設定を運用 Runbook に明記。

## 5. 実行確認

- `pytest -q veritas_os/tests/test_planner.py veritas_os/tests/test_fuji_core.py veritas_os/tests/test_memory_store.py veritas_os/tests/test_kernel.py`
- 結果: pass（ローカル実行）
