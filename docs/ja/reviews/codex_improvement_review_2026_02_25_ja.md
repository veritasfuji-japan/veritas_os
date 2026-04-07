# CODEX 改善レビュー（2026-02-25, JP）

## 結論

現状の `Planner / Kernel / Fuji / MemoryOS` は、機能面では前回レビューから安定化しています。
ただし、**「堅牢性」と「責務境界の明確さ」** でまだ改善余地があります。
特に以下 3 点を優先すべきです。

1. 例外ハンドリングの粒度を上げ、障害検知を「握りつぶし型」から「観測可能型」へ移行する。
2. optional import（`try/except ImportError`）依存を減らし、モジュール責務を起動時に確定する。
3. `MemoryOS` の legacy pickle 移行経路を計画的に廃止する。

---

## レビュー観点（今回）

- 対象: `veritas_os/core/planner.py`, `veritas_os/core/kernel.py`, `veritas_os/core/fuji.py`, `veritas_os/core/memory.py`
- 評価軸:
  - 責務境界（Planner / Kernel / Fuji / MemoryOS の越境有無）
  - 障害時の安全性（fail-open / fail-closed）
  - セキュリティ露出（不正入力・依存解決・レガシー互換）
  - 保守性（可観測性・テスト容易性）

---

## 優先度つき改善提案

### P0（最優先）: broad exception の縮小

**観測**
- 4 モジュール全体で `except Exception` が広く使われています。特に Planner / Kernel / Fuji / MemoryOS で頻出です。

**リスク**
- 重大障害（想定外の型崩れ、I/O異常、データ破損兆候）が同じ扱いで丸められ、検知遅延が起きます。
- FUJI の安全判定・Kernel の制御経路で握りつぶしが起きると、監査時に根本原因追跡が難しくなります。

**提案**
- 主要経路から段階的に `except Exception` を削減し、以下へ分割:
  - `ValueError` / `TypeError`（入力異常）
  - `OSError`（I/O）
  - 依存モジュール固有例外
- 「フォールバック許容箇所」と「即時失敗箇所」を ADR で明確化する。

---

### P1: optional import の整理（責務境界の明確化）

**観測**
- `kernel.py` / `fuji.py` / `memory.py` で `try/except ImportError` による optional import が残っています。

**リスク**
- 実行環境により挙動が変わり、再現性が下がります。
- 「どの責務をどこまで保証するか」が実行時に揺れるため、境界が曖昧になります。

**提案**
- optional 機能を明示的な feature flag で切り替える（import 成否ではなく設定で制御）。
- 起動時に `capability manifest` を出力し、利用不可機能を運用で可視化する。
- 責務越境を避けるため、Kernel から見る外部能力をインターフェース（Protocol）で固定する。

---

### P1: Planner の正規化系ユーティリティ整理

**観測**
- Planner 内の正規化処理は丁寧ですが、同様の変換パターンが多数存在します。

**リスク**
- 将来の仕様追加時に一部経路だけ修正漏れが起きやすい。

**提案**
- `normalization` 専用モジュールへ抽出（Planner責務の範囲内で分離）。
- 型変換の失敗時ポリシー（default値採用/拒否）を統一テーブル化。

---

### P2: MemoryOS の legacy pickle 廃止を前倒し

**観測**
- `memory.py` は制限付きUnpickler・サイズ制限・期限付き移行を実装済みで、防御は進んでいます。

**セキュリティ警告（重要）**
- それでも pickle 経路は本質的に高リスクです。環境変数で有効化できる限り、攻撃面は残ります。

**提案**
- 廃止日を固定し、到達後はコードパスを完全削除する。
- 移行専用ツールを runtime から分離（オフライン one-shot バイナリ化）。
- `memory_model.pkl` ロード経路も同時に JSON/ONNX 等へ移行する。

---

### P2: Doctor 自動実行の運用ガード強化（Kernel）

**観測**
- 実行間隔制御・安全実行ファイル判定・ログFD制約は実装済みです。

**セキュリティ警告**
- `subprocess.Popen` 経路は権限境界の影響を受けやすく、運用ミス時の影響半径が大きいです。

**提案**
- 本番で `doctor` 自動起動をデフォルト無効にし、明示的 opt-in にする。
- seccomp/AppArmor 等のプロファイル下でのみ許可する運用基準を追加する。

---

## 責務境界に関する判定

- Planner: 「計画生成と正規化」に集中しており、大きな越境はない。
- Kernel: 調停責務に加え周辺ユーティリティを多く抱えており、肥大化傾向。
- Fuji: 安全判定責務は維持できているが、フォールバック分岐が増え複雑化。
- MemoryOS: 互換維持と安全化の両立で責務が増加。移行完了後の簡素化余地が大きい。

> 総評: **現時点で即時停止級の欠陥は見えないが、保守負債の蓄積速度が高い。**

---

## 実行計画（推奨）

1. スプリント1（P0）
   - broad exception マップ作成
   - 失敗分類（入力異常/I/O/依存）を導入
2. スプリント2（P1）
   - optional import を feature flag 駆動へ置換
   - Planner 正規化処理を分離
3. スプリント3（P2）
   - legacy pickle 完全廃止
   - doctor 自動実行ポリシーを本番運用基準に組み込み

---

## 監査メモ

- 本レビューは実装差分を伴わない「改善提案レビュー」です。
- 提案は **Planner / Kernel / Fuji / MemoryOS の責務を越える改変を要求しません**。
- セキュリティ上の残余リスク（pickle・subprocess・例外握りつぶし）は継続監視対象です。
