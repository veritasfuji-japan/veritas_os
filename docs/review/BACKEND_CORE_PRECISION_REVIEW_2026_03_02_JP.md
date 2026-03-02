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


---

## 7. 再精密レビュー追記（2026-03-02 / Codex）

### 7.1 対象ファイル（追加読解）

- `veritas_os/core/planner.py`
- `veritas_os/core/kernel.py`
- `veritas_os/core/fuji.py`
- `veritas_os/core/memory.py`
- `veritas_os/memory/store.py`

### 7.2 追加所見（責務境界内）

- **Planner**
  - 以前の懸念だったフォールバック理由の不可視化は、`planner_fallback_reason` 付与と warning ログで改善済み。
  - JSON 抽出や decode 試行回数に上限が入り、LLM 出力起因の CPU 逼迫リスクは抑制されている。
- **Kernel**
  - doctor 自動起動は `shell=False` / 実行ファイル検証 / ログFD安全オープン（`O_NOFOLLOW` 利用可能時）で強化済み。
  - レート制限とアクティブプロセス追跡で高頻度起動時の資源圧迫を抑制できる。
- **Fuji**
  - ポリシーロード失敗時の warning/error ログ、および strict deny モード (`VERITAS_FUJI_STRICT_POLICY_LOAD`) が実装済み。
  - 以前の「サイレント既定値フォールバック」問題は是正方向。
- **MemoryOS**
  - `VERITAS_MEMORY_DIR` 監査ログ・本番 allowlist・`mkdir(0o700)` が入り、保存先設定リスクは低減。
  - pickle runtime ロード廃止方針は維持されており、任意コード実行面の回避として妥当。

### 7.3 セキュリティ警告（運用上の残余リスク）

1. **[Warning] 本番で allowlist 未設定時の運用劣化リスク**
   - `VERITAS_ENV=production` かつ `VERITAS_MEMORY_DIR_ALLOWLIST` 未設定の場合、既定パスへフォールバックする。
   - 安全側ではあるが、意図した永続先が使われず監査・バックアップ運用にギャップを作る可能性があるため、デプロイ時に必ず allowlist を明示設定すること。

2. **[Warning] Fuji YAML 無効時のポリシー更新反映漏れリスク**
   - capability 設定や依存不足により YAML policy が無効化されると built-in policy で動作する。
   - strict 運用が必要な環境では `VERITAS_CAP_FUJI_YAML_POLICY=1` と依存関係整備をセットで必須化すべき。

### 7.4 結論

- Planner / Kernel / Fuji / MemoryOS の責務を越える変更なしで、主要な過去指摘は概ね改善済み。
- 現時点の優先課題は「コード欠陥」よりも「本番設定の明示化（allowlist / strict policy）」である。
