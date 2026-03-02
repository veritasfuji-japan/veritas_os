# Backend Core 再レビュー（Planner / Kernel / Fuji / MemoryOS）

作成日: 2026-03-02  
対象: `veritas_os/core/planner.py`, `veritas_os/core/kernel.py`, `veritas_os/core/fuji.py`, `veritas_os/memory/store.py`

## 1. 再レビュー観点

- 前回指摘（F-01 / P-01 / M-01）の反映確認
- セキュリティ観点（フェイルセーフ、監査ログ、設定誤り耐性）
- 既存回帰テスト実行

## 2. 総評

前回の主要指摘 3 件は、**いずれも改善が確認できる状態**です。  
特に Fuji のポリシーロード失敗時に warning/error が明示化され、strict モード時に deny 側へ倒す実装が追加されたことで、運用時の「気づけないポリシードリフト」リスクは大幅に低減しています。

## 3. 指摘項目の再判定

### F-01（Fuji）: ポリシーファイル障害時サイレントフォールバック

- **再判定: 対応済み**
- 確認内容:
  - `_fallback_policy()` で理由・パス・例外型・strict フラグを warning 出力。
  - `VERITAS_FUJI_STRICT_POLICY_LOAD` 有効時は `_STRICT_DENY_POLICY` を返却し、error ログを出力。
  - `_load_policy()` / `_load_policy_from_str()` の YAML 失敗経路が `_fallback_policy()` 経由に統一。
- 効果:
  - ポリシー障害の可観測性を確保。
  - strict 運用で fail-safe（deny）を保証。

### P-01（Planner）: 例外握りつぶしによる可観測性低下

- **再判定: 対応済み**
- 確認内容:
  - `generate_code_tasks()` で code planner 失敗時に `logger.warning(..., exc_info=True)` を出力。
  - `planner_fallback_reason` を `meta` に格納。
- 効果:
  - フォールバック発生時の原因追跡が可能。
  - 監視メトリクス化（fallback reason 集計）の下地が整備。

### M-01（MemoryOS）: `VERITAS_MEMORY_DIR` の運用リスク

- **再判定: 対応済み（条件付き）**
- 確認内容:
  - `_resolve_memory_dir()` で解決後パスを info ログ出力。
  - `VERITAS_ENV=production` 時は `VERITAS_MEMORY_DIR_ALLOWLIST` を必須化し、prefix 不一致なら default へフォールバック。
  - `HOME_MEMORY.mkdir(mode=0o700, ...)` で作成権限を明示。
- 効果:
  - 誤設定時に安全側へ倒れる挙動を確保。
  - 保存先監査性が向上。

## 4. 追加セキュリティ警告（要運用ルール）

> ユーザー指示に基づく明示警告。

1. `VERITAS_ENV=production` を設定しない環境では allowlist 検証が有効化されません。  
   本番相当環境で環境変数が未設定だと、防御が弱いモードのまま運用されるリスクがあります。

2. `VERITAS_MEMORY_DIR_ALLOWLIST` の prefix 設計を誤ると、意図しないディレクトリを許可する可能性があります。  
   例: 上位すぎる共通ディレクトリを許可してしまうケース。

3. Fuji strict モード（`VERITAS_FUJI_STRICT_POLICY_LOAD=1`）未使用時は、障害時にデフォルトポリシーへフォールバックします。  
   セキュリティ厳格運用では strict モードを推奨します。

## 5. 回帰テスト結果

- 実行コマンド:  
  `pytest -q veritas_os/tests/test_planner.py veritas_os/tests/test_kernel.py veritas_os/tests/test_fuji_core.py veritas_os/tests/test_memory_core.py`
- 結果: **99 passed**

## 6. 結論

- 前回レビューの高/中優先指摘は、現時点で解消済みと判定します。
- 次の改善は実装よりも運用ガード（環境変数の本番標準化、ログ監視ルール化）を優先するのが妥当です。
