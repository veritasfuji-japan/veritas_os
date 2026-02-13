# VERITAS OS 全コードレビュー（2nd Rewrite）

**Date**: 2026-02-10  
**Scope**: `veritas_os/` 全 Python 実装 + ルート運用設定  
**Review Mode**: 静的精読 + 実行可能な範囲の検証

---

## 0. サマリ

- `veritas_os` 配下の Python ファイルは **160 files**（`api=7, core=37, memory=5, tools=5, logging=5, scripts=23, tests=77`）。
- 既存で改善済みの項目（一部 DoS 対策・セキュリティヘッダー・atomic 書き込み）は確認。
- ただし、運用上のセキュリティリスクとして以下を継続警告。
  1. scripts の弱い API キーフォールバック（`test-key` / `dev-key`）
  2. body size 制限の `Content-Length` 依存
  3. legacy pickle migration 経路の残存

---

## 1. 実施ログ

### 1.1 実行コマンド
1. `PYENV_VERSION=3.12.12 python - <<'PY' ...`（Python ファイル数集計）
2. `rg -n "TODO|FIXME|...|pickle|Content-Length|..." veritas_os -g '!**/tests/**'`
3. `python -m pytest -q`
4. `PYENV_VERSION=3.12.12 python -m pytest -q`
5. `PYENV_VERSION=3.12.12 python -m pip install -r veritas_os/requirements.txt`

### 1.2 結果
- 3 は失敗（`.python-version=3.12.7` が環境未導入）。
- 4 は依存不足（`fastapi`, `requests` 等）で collection error。
- 5 はプロキシ/ネットワーク制約で失敗。
- よって、今回は **静的レビュー中心**。

---

## 2. 主要指摘（Severity）

## [HIGH] H-1: scripts の弱いデフォルトAPIキー

### 対象
- `veritas_os/scripts/decide_plan.py`
- `veritas_os/scripts/bench.py`

### 観測
- `VERITAS_API_KEY` 未設定時にそれぞれ `"test-key"` / `"dev-key"` を利用。

### セキュリティ警告
- 検証スクリプトが本番近傍へ流用された場合、認証が実質弱体化。
- 設定ミスを fail-fast できず、誤運用を見逃す。

### 推奨（責務内）
- APIキー未設定時は即終了へ変更。
- README 実行例に「必須 env」を明示。

---

## [HIGH] H-2: `Content-Length` 依存の body size 制限

### 対象
- `veritas_os/api/server.py` `limit_body_size` middleware

### 観測
- `Content-Length` 前提で 413/400 判定を実施。

### セキュリティ警告
- `Transfer-Encoding: chunked` 等でヘッダー未提供ケースの網羅性が弱い。
- 結果として、メモリ/CPU 消費型 DoS 防御の取りこぼし余地がある。

### 推奨（責務内）
- ASGI受信ストリームで実測バイト上限を追加。
- reverse proxy 側上限と二重化（多層防御）。

---

## [MEDIUM] M-1: legacy pickle migration 経路の残存

### 対象
- `veritas_os/core/memory.py`
- `veritas_os/memory/index_cosine.py`

### 観測
- 制限付きUnpickler + env flag で緩和されているが、移行経路は残存。

### セキュリティ警告
- 環境変数運用ミス + 不正入力ファイルの組み合わせで攻撃面を残す。

### 推奨（責務内）
- pickle 受理の sunset date を定義。
- 廃止まで migration 実行時監査ログを強化。

---

## [MEDIUM] M-2: Python バージョン再現性

### 対象
- `.python-version`

### 観測
- `3.12.7` 指定と実行環境の不一致により初期起動失敗。

### リスク
- 開発/CI の初動失敗による検証遅延。

### 推奨
- CI と同一の実在バージョンへ統一。

---

## 3. 境界条件チェック（Planner / Kernel / Fuji / MemoryOS）

- **Planner**: 挙動変更提案なし。入力/出力境界の安全性観点のみ。
- **Kernel**: subprocess 実行は `shell=False` 確認。責務越境変更提案なし。
- **Fuji**: policy reload 周辺は現行設計尊重。運用制約の提案のみ。
- **MemoryOS**: pickle sunset は memory モジュール内で完結する計画として提案。

---

## 4. 優先アクション

### P0
1. scripts の API キー fail-fast 化
2. body size 制御の多層化（ASGI stream + proxy）

### P1
3. legacy pickle migration の段階的停止計画

### P2
4. `.python-version` / CI 実行環境の統一

---

## 5. 補足

- 本レビューは「現時点コードの再読結果」。
- ネットワーク制約解消後に full test を再実施推奨。
