# Backend Core 精密レビュー（Planner / Kernel / Fuji / MemoryOS）

作成日: 2026-03-02  
対象: `veritas_os/core/planner.py`, `veritas_os/core/kernel.py`, `veritas_os/core/fuji.py`, `veritas_os/core/memory.py`, `veritas_os/memory/store.py`, `veritas_os/memory/index_cosine.py`

## 1. レビュー方法

- 静的読解（例外処理・I/O・ポリシーロード・サブプロセス起動経路）
- セキュリティ観点（権限・TOCTOU・ポリシーフェイルセーフ・情報漏えい）
- 既存テスト実行による回帰確認

## 2. 総合評価

- **重大な即時クラッシュ要因は未検出**。
- `Kernel` の `subprocess.Popen` 呼び出しは `shell=False` + 実行ファイル検証 + `O_NOFOLLOW` 対応で、既知の危険パターンを概ね回避できている。
- `Fuji`/`Planner`/`MemoryOS` はフォールバック設計が強い一方で、**「静かな失敗」(silent fallback / silent pass)** が監視性・運用安全性を下げる箇所が残る。

## 3. 主要指摘（優先度順）

### [High] F-01: Fuji ポリシーファイル障害時のサイレント既定値フォールバック

- 該当: `veritas_os/core/fuji.py` の `_load_policy()`
- 現状: YAML 読み込み失敗時に `_DEFAULT_POLICY` へ即時フォールバックするが、警告ログが出ない。
- リスク:
  - 運用者は「厳格カスタムポリシーが効いている」と誤認したまま、実際はデフォルトで稼働しうる。
  - セキュリティ運用上の**ポリシードリフト検知漏れ**につながる。
- 推奨:
  1. 例外発生時に warning/error ログを必須化（ファイルパス・例外型を含む）。
  2. オプションで `strict_policy_load=true` を用意し、失敗時に deny 側へ倒すモードを追加。

### [Medium] P-01: Planner の例外握りつぶしで可観測性低下

- 該当: `veritas_os/core/planner.py` の `generate_code_tasks()` 内、`except (AttributeError, TypeError, ValueError): pass`
- 現状: code planner 連携失敗時に純ロジック経路へフォールバックするが、失敗理由が残らない。
- リスク:
  - 品質劣化が徐々に進んでもアラートされず、原因調査時間が増える。
- 推奨:
  1. `logger.warning(..., exc_info=True)` で最小限の失敗記録を残す。
  2. 戻り値 `meta` に `planner_fallback_reason` を付加して後段分析を可能化。

### [Medium] M-01: Memory 保存先の環境変数注入による運用リスク

- 該当: `veritas_os/memory/store.py` の `VERITAS_MEMORY_DIR` 取り扱い
- 現状: 環境変数が設定されると任意パスをそのまま採用して `mkdir(parents=True, exist_ok=True)`。
- リスク:
  - 誤設定により機密性の低いディレクトリへデータ出力される可能性。
  - 共有ホスト環境では権限・監査設計次第でデータ露出面が増える。
- 推奨:
  1. 起動時に `resolved path` を監査ログへ出力。
  2. 本番モードでは許可ベース（allowlist prefix）チェックを導入。
  3. ディレクトリ作成時のパーミッションを明示（例: 0o700）する設定を検討。

## 4. 参考: 良好な実装点

- `Kernel` 側 doctor ログFDで `O_NOFOLLOW` を利用し、`fstat` で regular file 検証している。
- `Kernel` の doctor 起動は `shell=False` + 固定 argv + Python 実行ファイル検証があり、コマンドインジェクション耐性が高い。
- `MemoryOS` は pickle の runtime 読み込み無効化方針が明示されている。
- `Fuji` のホットリロードは lock + fd ベース読込で TOCTOU を抑制。

## 5. テスト結果

- `pytest -q veritas_os/tests/test_planner.py veritas_os/tests/test_kernel.py veritas_os/tests/test_fuji_core.py veritas_os/tests/test_memory_core.py`
- 結果: **96 passed**

## 6. 次アクション（責務境界を越えない範囲）

1. `Fuji` のポリシーロード失敗時ログ追加（責務: Fuji）。
2. `Planner` のフォールバック監視情報追加（責務: Planner）。
3. `MemoryOS` の保存先パス監査ログ＋本番時バリデーション（責務: MemoryOS）。

