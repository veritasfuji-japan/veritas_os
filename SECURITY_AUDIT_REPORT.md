# VERITAS OS セキュリティ監査レポート

**監査日**: 2026-03-12
**対象**: VERITAS OS リポジトリ全体
**監査者**: セキュリティアーキテクト / コード監査

---

## 総括

3領域にわたり **25件の危険箇所** を特定。うち **CRITICAL 7件 / HIGH 11件 / MEDIUM 7件**。
以下に全危険箇所の洗い出し結果と修正計画を示す。

---

## 領域1: TrustLog / 監査ログ保存

### [CRITICAL-01] 暗号化がオプション（デフォルトOFF）

| 項目 | 内容 |
|------|------|
| **ファイル** | `veritas_os/logging/encryption.py:113-126` |
| **問題** | `VERITAS_ENCRYPTION_KEY` 未設定時、`encrypt()` が恒等関数（平文そのまま返却）。大半のデプロイで暗号化無効。 |
| **影響** | 意思決定ログ（query, chosen, context）が平文 JSONL でディスク保存される |

```python
# encryption.py L126 — 暗号化キーがなければ平文をそのまま返す
def encrypt(plaintext: str) -> str:
    key = _get_key_bytes()
    if key is None:
        return plaintext  # ← 恒等関数
```

**修正計画**:
1. 起動時に `VERITAS_ENCRYPTION_KEY` 未設定の場合 **ERROR ログ + 強制 WARNING フラグ** を立てる
2. 本番モード (`VERITAS_ENV=production`) では暗号化キー未設定をハードエラーにする
3. 開発モード用に `VERITAS_ALLOW_PLAINTEXT_LOG=1` の明示的オプトイン方式に変更

---

### [CRITICAL-02] decrypt() が復号せず暗号文をそのまま返す

| 項目 | 内容 |
|------|------|
| **ファイル** | `veritas_os/logging/encryption.py:155-188` |
| **問題** | HMAC検証後、実際の復号処理がなく `return ciphertext` で暗号文をそのまま返している |
| **影響** | 暗号化ログの読み出し・監査・レポート出力が事実上不可能 |

```python
# encryption.py L184-188
logger.info("Encryption verification passed (HMAC valid)")
# NOTE: Full decryption requires the cryptography library for real AES.
return ciphertext  # ← 復号されていない!
```

**修正計画**:
1. `cryptography` ライブラリ (AES-GCM) を用いた実復号実装を追加
2. `decrypt()` が暗号文を返すことがないよう、復号失敗時は `DecryptionError` 例外を送出
3. ユニットテスト: `encrypt() → decrypt()` のラウンドトリップを検証

---

### [CRITICAL-03] 平文 JSONL への機密データ書き込み

| 項目 | 内容 |
|------|------|
| **ファイル** | `veritas_os/logging/trust_log.py:400-407`, `veritas_os/core/pipeline_persist.py:189`, `veritas_os/logging/dataset_writer.py:260` |
| **問題** | query, chosen, context 等の意思決定データが平文で JSONL に追記される |
| **影響** | ファイルシステムアクセスで意思決定履歴が完全に漏洩 |

**修正計画**:
1. `trust_log.py` の `append_trust_log()` で暗号化を必須化（暗号化キー未設定時はログ出力拒否 + エラー）
2. `pipeline_persist.py` のメタログにも同じ暗号化パスを適用
3. `dataset_writer.py` にフィールドレベル暗号化を導入（最低限 query, chosen を暗号化）

---

### [HIGH-04] Shadow Decide ファイルが平文 JSON

| 項目 | 内容 |
|------|------|
| **ファイル** | `veritas_os/logging/trust_log.py:444-484`, `veritas_os/api/server.py:2247-2254` |
| **問題** | ダッシュボード用 `logs/DASH/decide_*.json` に query, chosen が平文保存 |
| **影響** | 監査ログ本体を暗号化しても、Shadow ファイル経由で情報漏洩 |

**修正計画**:
1. Shadow Decide にも暗号化パスを適用
2. query フィールドは保存前に redact を通す
3. ダッシュボード読み出し時にオンデマンド復号する API を提供

---

### [HIGH-05] Redaction がデフォルト OFF

| 項目 | 内容 |
|------|------|
| **ファイル** | `veritas_os/core/fuji.py:316-318` |
| **問題** | `audit.redact_before_log` のデフォルトが `False`。PII がそのまま記録される。 |
| **影響** | 個人情報保護法・GDPR 違反リスク |

```python
# fuji.py L317
if not audit_cfg.get("redact_before_log", False):  # デフォルト False
    return text  # マスクなしで返却
```

**修正計画**:
1. デフォルトを `True` に変更: `audit_cfg.get("redact_before_log", True)`
2. `person_name_jp` のデフォルトも `True` に変更（現在 `False`）
3. Redaction 除外は明示的オプトアウト (`redact_before_log: false`) のみ許可

---

### [HIGH-06] PII マスキングが不完全（フォールバック regex）

| 項目 | 内容 |
|------|------|
| **ファイル** | `veritas_os/core/utils.py:326-341` |
| **問題** | フォールバック regex はメール・電話のみ。住所、氏名、クレジットカード、API トークンは未対応 |
| **影響** | sanitize モジュール読込失敗時に PII 漏洩 |

**修正計画**:
1. フォールバック regex にクレジットカード番号、日本住所、マイナンバーパターンを追加
2. sanitize モジュール読込失敗時に WARNING ログを出力
3. フォールバック発動をメトリクスとして記録

---

### [HIGH-07] ハッシュチェーンのみで改ざん検出（認証なし）

| 項目 | 内容 |
|------|------|
| **ファイル** | `veritas_os/logging/trust_log.py:331-397` |
| **問題** | SHA-256 ハッシュチェーンは改ざん「検知」はできるが、攻撃者が全チェーンを再計算すれば偽造可能 |
| **影響** | 監査証跡の信頼性が暗号学的に不十分 |

**修正計画**:
1. Signed TrustLog (`trustlog_signed.py`) を必須化（best-effort → mandatory）
2. 署名失敗時は `append_trust_log()` 自体を失敗させる（fail-close）
3. 定期的な外部タイムスタンプ局 (TSA) との連携オプション追加

---

### [HIGH-08] Signed TrustLog が best-effort

| 項目 | 内容 |
|------|------|
| **ファイル** | `veritas_os/logging/trust_log.py:416-424` |
| **問題** | `append_signed_decision()` が例外を catch して `logger.warning` のみ。署名なしログが正常扱いされる |
| **影響** | 署名失敗を気づかないまま運用継続 → 監査証跡の認証が欠落 |

```python
# trust_log.py L418-424
try:
    append_signed_decision(entry)
except Exception:
    logger.warning("append_signed_decision failed; continuing with legacy trust log", ...)
```

**修正計画**:
1. 本番モードでは署名失敗を致命エラーに昇格
2. 署名スキップ回数のカウンタを導入し、閾値超過でアラート発火
3. `decision_status` に `"signature_missing": true` フラグを付与

---

### [HIGH-09] 秘密鍵が平文でファイル保存

| 項目 | 内容 |
|------|------|
| **ファイル** | `veritas_os/security/signing.py:81-85` |
| **問題** | Ed25519 秘密鍵が Base64 平文で保存（`0o600` パーミッションのみ） |
| **影響** | ファイルシステムアクセスで署名偽造が可能 |

**修正計画**:
1. OS キーストア（Linux: kernel keyring / macOS: Keychain）への対応を追加
2. ファイル保存時はパスフレーズ付き暗号化（PKCS#8）を使用
3. 環境変数 `VERITAS_SIGNING_KEY` からの直接読込にも対応

---

## 領域2: MemoryOS / pickle 残存

### [CRITICAL-04] テストコードに pickle.dump が残存

| 項目 | 内容 |
|------|------|
| **ファイル** | `veritas_os/tests/test_memory_vector.py:59-66` |
| **問題** | テストヘルパー `_write_legacy_pickle()` が `pickle.dump()` を使用。CI 環境で pickle ファイルを生成 |
| **影響** | テスト経由で pickle ファイルがリポジトリやCI成果物に混入するリスク |

```python
# test_memory_vector.py L65-66
with open(path, "wb") as f:
    pickle.dump(payload, f)
```

**修正計画**:
1. テストヘルパーをモック化し、実際の pickle ファイルを生成しない方式に変更
2. pickle import をテストファイルから除去
3. CI に pickle ファイル生成を検出するガードを追加

---

### [MEDIUM-05] レガシー pickle パスの検出がワーニングのみ

| 項目 | 内容 |
|------|------|
| **ファイル** | `veritas_os/core/memory.py:52-84, 231-237, 580-585` |
| **問題** | `.pkl` ファイル検出時に `logger.error` で警告するが、起動は続行。デッドラインは 2026-06-30 |
| **影響** | 2026-06-30 以降もデッドラインの強制がコード上で実装されていない |

**修正計画**:
1. デッドライン到達後は `.pkl` 検出時にハードエラー（`SystemExit` or 起動拒否）
2. `_warn_for_legacy_pickle_artifacts()` を `_block_legacy_pickle_artifacts()` に改名し、デッドライン後は例外送出
3. デッドライン前でも `VERITAS_BLOCK_PICKLE_NOW=1` で即時ブロック可能にする

---

### [MEDIUM-06] env 変数で pickle 移行をオプトイン可能

| 項目 | 内容 |
|------|------|
| **ファイル** | テスト: `test_memory_vector.py:289-307` (環境変数 `VERITAS_MEMORY_ALLOW_PICKLE_MIGRATION`) |
| **問題** | `VERITAS_MEMORY_ALLOW_PICKLE_MIGRATION=1` を設定すると pickle からの移行パスが有効になる可能性 |
| **影響** | 攻撃者が環境変数を制御できる場合、pickle デシリアライズを有効化できる |

**修正計画**:
1. この環境変数を完全に廃止
2. 移行はオフラインスクリプト (`scripts/security/check_runtime_pickle_artifacts.py`) に限定
3. ランタイムでの pickle 読込パスを全て削除

---

### [MEDIUM-07] VectorMemory がレガシー .pkl パスを意識し続けている

| 項目 | 内容 |
|------|------|
| **ファイル** | `veritas_os/core/memory.py:231-237` |
| **問題** | `_load_index()` がまだ `.pkl` 拡張子の存在をチェックし、分岐ロジックを持っている |
| **影響** | コードパス上に pickle 関連ロジックが残存し、将来の誤用リスク |

**修正計画**:
1. `.pkl` チェック分岐を削除し、JSON 形式のみをサポート
2. `.pkl` ファイルが存在する場合は起動時に明確なエラーメッセージで停止

---

### [LOW] joblib_load = None の残存

| 項目 | 内容 |
|------|------|
| **ファイル** | `veritas_os/core/memory.py:97` |
| **問題** | `joblib_load = None` が後方互換 shim として残存 |

**修正計画**: このシンボルを完全に削除。利用箇所がないことを確認済み。

---

## 領域3: FUJI Gate / ValueCore / Safety 判定

### [CRITICAL-05] LLM 安全性判定の失敗時に heuristic で `ok=True` を返す

| 項目 | 内容 |
|------|------|
| **ファイル** | `veritas_os/tools/llm_safety.py:389-406` |
| **問題** | OpenAI API 障害時、ヒューリスティック分析にフォールバックし `ok=True` で返却。例外種別を区別しない |
| **影響** | API 障害時に危険なコンテンツが `ok` として通過する可能性 |

```python
# llm_safety.py L389-406
try:
    return _analyze_with_llm(...)
except Exception as e:
    fb = _heuristic_analyze(text)
    fb["ok"] = True  # ← 常に ok
    fb.setdefault("raw", {})["llm_error"] = "LLM safety head unavailable"
    return fb
```

**修正計画**:
1. `ok=True` の自動設定を削除。ヒューリスティック結果のリスクスコアに基づいて判定
2. 例外を分類: `AuthenticationError` → ハードエラー、`RateLimitError` → リトライ、`APIConnectionError` → fail-close
3. フォールバック結果に `"degraded": true` フラグを必ず付与

---

### [CRITICAL-06] Debate LLM 障害時に最初の選択肢を無条件返却

| 項目 | 内容 |
|------|------|
| **ファイル** | `veritas_os/core/debate.py:760-770, 888-890` |
| **問題** | LLM 呼び出しまたは応答パース失敗時、`_fallback_debate(base_options)` が最初の選択肢を返す |
| **影響** | 安全でない選択肢が先頭にある場合、LLM 障害で自動選択される |

**修正計画**:
1. フォールバック時は全選択肢に `"needs_human_review": true` を付与
2. LLM 障害の場合は FUJI Gate で `hold` 判定に強制
3. フォールバック発動を audit log に明記

---

### [CRITICAL-07] TrustLog 書込失敗が黙殺される

| 項目 | 内容 |
|------|------|
| **ファイル** | `veritas_os/core/fuji.py:1321-1352` |
| **問題** | TrustLog 書込例外を catch して `reasons` に追記するのみ。意思決定は続行される |
| **影響** | 監査証跡なしで意思決定が実行される（コンプライアンス違反） |

```python
# fuji.py L1351-1352
except (TypeError, ValueError, OSError, RuntimeError) as e:
    reasons.append(f"trustlog_error:{repr(e)[:80]}")
```

**修正計画**:
1. 本番モードでは TrustLog 書込失敗時に意思決定を `deny` にフォールバック
2. 書込リトライ（最大3回）を実装
3. 全リトライ失敗時はアラート発火 + 意思決定を `hold` に強制

---

### [HIGH-10] SafetyHead の LLM/heuristic 判定が監査ログで不明瞭

| 項目 | 内容 |
|------|------|
| **ファイル** | `veritas_os/core/fuji.py:1343-1378` |
| **問題** | `safety_head_model` フィールドが `meta` に埋没。`decision_status` から判定経路が判別不能 |
| **影響** | 監査時に LLM 判定と heuristic 判定を区別できない |

**修正計画**:
1. トップレベルに `"judgment_source": "llm" | "heuristic_fallback" | "deterministic"` フィールドを追加
2. `SafetyHeadResult` に `is_fallback: bool` 属性を追加
3. ヒューリスティックフォールバック時は `categories` に `"heuristic_fallback"` を明示的に含める

---

### [HIGH-11] SafetyHead の例外捕捉が不完全

| 項目 | 内容 |
|------|------|
| **ファイル** | `veritas_os/core/fuji.py:825-833` |
| **問題** | `TypeError, ValueError, RuntimeError, OSError` の4種のみ捕捉。`httpx.NetworkError`, `asyncio.TimeoutError` 等が漏れる |
| **影響** | 未捕捉例外で意思決定パイプライン全体がクラッシュ |

**修正計画**:
1. `Exception` を捕捉し、例外種別に応じたハンドリングを実装
2. ネットワークエラーとパースエラーを分離してログ記録
3. 未知の例外は `risk_score = 1.0` で fail-close

---

### [HIGH-12] API キー未設定で RuntimeError（fail-open ではないが不親切）

| 項目 | 内容 |
|------|------|
| **ファイル** | `veritas_os/tools/llm_safety.py:241-246` |
| **問題** | API キーがない場合 `RuntimeError` が発生。上位の `except Exception` で `ok=True` のヒューリスティックに到達 |
| **影響** | API キー設定忘れが黙ってヒューリスティックモードになる |

**修正計画**:
1. 起動時の healthcheck で API キー設定を検証
2. API キー未設定時は `_llm_available()` が `False` を返すようにし、明確にヒューリスティックモードを宣言
3. 本番モードでは API キー未設定をハードエラーに

---

### [HIGH-13] ValueCore のウェイト変更が監査されない

| 項目 | 内容 |
|------|------|
| **ファイル** | `veritas_os/core/value_core.py:116-127, 260-263` |
| **問題** | `update_from_scores()` によるオンライン学習で価値重みが変更されるが、変更差分が audit log に記録されない |
| **影響** | ValueCore の重み変遷が追跡不能。異常な重み変化を検出できない |

**修正計画**:
1. `update_from_scores()` にウェイト変更前後の diff を TrustLog に記録する処理を追加
2. 重み変更幅に閾値を設定し、大幅変更時にアラート発火
3. `value_core.json` のロード時にデフォルト vs 保存済みを audit log に記録

---

### [HIGH-14] ValueCore の save 失敗でデフォルトに巻き戻る

| 項目 | 内容 |
|------|------|
| **ファイル** | `veritas_os/core/value_core.py:99-105` |
| **問題** | `save()` 失敗 → 次回 `load()` でファイルなし → `DEFAULT_WEIGHTS` にサイレントリバート |
| **影響** | カスタマイズされた価値体系が失われ、デフォルトで運用される |

**修正計画**:
1. `save()` 失敗時にエラーログ + リトライ
2. バックアップファイル (`value_core.json.bak`) を保持
3. load 時にデフォルトフォールバック発生を WARNING ログで出力

---

### [MEDIUM-08] Reason 生成の LLM 失敗で空文字を返す

| 項目 | 内容 |
|------|------|
| **ファイル** | `veritas_os/core/reason.py:160-169` |
| **問題** | LLM エラー時に `{"text": "", "source": "error"}` を返却。呼び出し元が空文字を無視する可能性 |

**修正計画**:
1. 空文字の代わりにテンプレートベースのフォールバック理由文を生成
2. `source: "error"` を呼び出し元で検知し、意思決定に反映

---

### [MEDIUM-09] PoC モードのオーバーライドが audit に不明瞭

| 項目 | 内容 |
|------|------|
| **ファイル** | `veritas_os/core/fuji.py:1156-1205` |
| **問題** | PoC モードが policy engine の結果をオーバーライドするが、audit log での区別が `meta.poc_mode` のみ |

**修正計画**:
1. PoC モードオーバーライド時は `decision_status` に明示的なプレフィクス（例: `poc_hold`）を付与
2. `policy_action_pre_poc` と最終結果の差分を top-level フィールドに昇格

---

### [MEDIUM-10] deterministic rule が heuristic 頼り

| 項目 | 内容 |
|------|------|
| **ファイル** | `veritas_os/tools/llm_safety.py` (heuristic_analyze), `veritas_os/core/fuji.py:839-954` |
| **問題** | deterministic policy engine は SafetyHead の出力に依存。SafetyHead が heuristic fallback の場合、keyword マッチのみでリスク判定 |
| **影響** | 巧妙な表現の危険コンテンツを keyword マッチでは検出不能 |

**修正計画**:
1. ヒューリスティック分析のキーワードリストを拡充
2. ヒューリスティックモード時は自動的に `risk_score` に +0.15 のペナルティを加算
3. ヒューリスティックモードが一定時間続く場合、運用チームにアラート通知

---

## 修正優先度マトリクス

| 優先度 | ID | 修正内容 | 想定工数 |
|--------|----|----------|----------|
| **P0 (即時)** | CRITICAL-01,03 | 暗号化必須化 + 平文書込防止 | 中 |
| **P0 (即時)** | CRITICAL-02 | decrypt() の実復号実装 | 中 |
| **P0 (即時)** | CRITICAL-05,06 | LLM 障害時 fail-safe 強化 | 中 |
| **P0 (即時)** | CRITICAL-07 | TrustLog 書込失敗時の fail-close | 小 |
| **P1 (1週間)** | HIGH-05,06 | Redaction デフォルト ON + PII パターン拡充 | 中 |
| **P1 (1週間)** | HIGH-07,08 | Signed TrustLog 必須化 | 大 |
| **P1 (1週間)** | HIGH-10,11 | 監査ログの判定経路明確化 + 例外捕捉修正 | 中 |
| **P1 (1週間)** | HIGH-12,13,14 | API キー検証 + ValueCore 監査 | 中 |
| **P2 (2週間)** | MEDIUM-05,06,07 | pickle 完全廃止 | 小 |
| **P2 (2週間)** | MEDIUM-08,09,10 | フォールバック改善 + PoC 監査明確化 | 中 |
| **P2 (2週間)** | CRITICAL-04 | テストからの pickle 除去 | 小 |
| **P3 (1ヶ月)** | HIGH-04,09 | Shadow ファイル暗号化 + 秘密鍵保護 | 大 |

---

## 修正設計原則

1. **Fail-Close**: セキュリティ機能の障害時は「拒否」をデフォルトにする
2. **Explicit Opt-Out**: 危険な設定（平文ログ、pickle 許可）は明示的オプトアウトのみ
3. **Audit Completeness**: 全意思決定に判定経路（LLM/heuristic/deterministic）を明記
4. **Defense in Depth**: 暗号化 + 署名 + redaction の三重防御
5. **No Silent Degradation**: フォールバック発動を必ずログ + メトリクスに記録
