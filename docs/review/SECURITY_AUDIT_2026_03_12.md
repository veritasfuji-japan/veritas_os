# VERITAS OS セキュリティ全監査報告書

**日付:** 2026-03-12
**監査者:** AI Security Architect
**対象:** TrustLog / MemoryOS / FUJI Gate・ValueCore・Safety
**スコープ:** 実装上の危険箇所の全洗い出しと修正設計

---

## 1. 危険箇所一覧

### 1.1 TrustLog / 監査ログ保存

| # | ファイル | 関数/クラス | 危険内容 | 具体的リスク | 優先度 |
|---|---------|------------|---------|------------|--------|
| T-01 | `veritas_os/logging/encryption.py:155-188` | `decrypt()` | **復号が未実装** — HMAC検証後に暗号文をそのまま返す | 暗号化を有効にしても読み出しが不可能。暗号化は一方通行で、データ復旧ができない。 | **Critical** |
| T-02 | `veritas_os/logging/encryption.py:104-110` | `_aes_encrypt_block()` | SHA256ベースのPRF擬似暗号であり、AESではない | 「AES-CBC暗号化」と称しながら実態はハッシュベースの非標準方式。暗号強度の保証がない。 | **Critical** |
| T-03 | `veritas_os/logging/encryption.py:124-126` | `encrypt()` | 鍵未設定時にplaintextをそのまま返す（identity function） | デフォルトで暗号化OFF。起動時警告なし。本番環境でplaintext運用が黙認される。 | **Critical** |
| T-04 | `veritas_os/logging/encryption.py:150-152` | `encrypt()` 例外ハンドラ | 暗号化失敗時にplaintextへサイレントフォールバック | 暗号化エラー時もデータは平文で書き出される。運用者に通知されない。 | **High** |
| T-05 | `veritas_os/logging/trust_log.py:31-38` | `_mask_pii` import | PII masking がimport失敗時にサイレント無効化 | sanitize モジュール不在でもシステムは稼働し続け、PIIが平文保存される。 | **High** |
| T-06 | `veritas_os/logging/trust_log.py:380-408` | `append_trust_log()` | メインTrustLogにPII redactionなし | `write_shadow_decide()` のみmask_piiを呼ぶ。本体の`append_trust_log()`では `query` フィールドが平文のまま保存される。 | **High** |
| T-07 | `veritas_os/logging/trust_log.py:416-424` | `append_signed_decision()` 呼出 | 署名付きTrustLogの書込み失敗がbest-effort | `except Exception` で握りつぶし。署名なしログだけが残り、改ざん検出が不可能になる。 | **High** |
| T-08 | `veritas_os/logging/rotate.py` | `_LAST_HASH_MARKER` | ハッシュチェーンの継続がマーカーファイル依存 | `.last_hash` ファイルが削除/改竄されると、ローテーション後のチェーン接続が破壊される。マーカー自体は平文・無署名。 | **Medium** |
| T-09 | `veritas_os/logging/trust_log.py:44-46` | `LOG_JSON`, `LOG_JSONL` | 信頼ログが二重ファイル（JSON + JSONL） + 署名付きJSONLで三重 | 3つのログが独立存在し、どれが権威的か不明。不整合発生時の検出・対処方針がない。 | **Medium** |
| T-10 | `veritas_os/logging/encryption.py:195-215` | `get_encryption_status()` | 暗号化ステータスが `"HMAC-SHA256 authenticated CBC-mode encryption"` と表記 | 実態はAESではなくSHA256-PRF。EU AI Act Art. 12準拠の主張に虚偽がある。 | **Medium** |

### 1.2 MemoryOS / pickle 残存

| # | ファイル | 関数/クラス | 危険内容 | 具体的リスク | 優先度 |
|---|---------|------------|---------|------------|--------|
| M-01 | `veritas_os/core/config.py:262` | `enable_memory_joblib_model` | capability flagが `default=True` のまま残存 | コード上は `joblib_load = None` で無効だが、設定値が `True` のまま残っており、将来の実装者が誤って有効化するリスク。 | **Medium** |
| M-02 | `veritas_os/core/memory.py:31` | `PICKLE_RUNTIME_BLOCK_DEADLINE` | 期限が `"2026-06-30"` で猶予期間中 | 明示的に「この日まで互換復帰の可能性あり」と解釈可能。完全除去への曖昧さが残る。 | **Medium** |

**注記:** pickle自体のruntime loadingは `joblib_load = None`、`np.load(allow_pickle=False)`、CI checkスクリプトにより**適切にブロック済み**。上記は残存する設定上の曖昧さのみ。

### 1.3 FUJI Gate / ValueCore / Safety 判定

| # | ファイル | 関数/クラス | 危険内容 | 具体的リスク | 優先度 |
|---|---------|------------|---------|------------|--------|
| F-01 | `veritas_os/tools/llm_safety.py:389-403` | `run()` | **LLM失敗時にheuristicへfallback（fail-open的動作）** | `_heuristic_analyze()` は17個の禁止ワードと4つのPII regexだけ。LLM障害時にすべての巧妙な攻撃が素通りする。`ok=True` を返し続ける。 | **Critical** |
| F-02 | `veritas_os/tools/llm_safety.py:43-63` | `_BANNED`, `_SENSITIVE` | ヒューリスティックの網羅性が極めて低い | 禁止ワード17個 + センシティブ10個。完全部分文字列一致のみ。パラフレーズ、比喩、隠語、多言語表現、typo-squattingすべてを通過する。 | **Critical** |
| F-03 | `veritas_os/core/fuji.py:825-833` | `run_safety_head()` 例外ハンドラ | LLMエラー時のリスクフロアが0.30のみ | `max(fb.risk_score, 0.30)` では deny閾値（通常0.7-0.8）に届かず、安全性未確認のまま `allow` される。 | **Critical** |
| F-04 | `veritas_os/core/fuji.py:1287-1290` | `fuji_gate()` → `run_safety_head()` | Safety HeadがLLM単一障害点 | OpenAI API障害 → heuristic fallback → 0.30 risk → allow。Safety判定の信頼性がOpenAI可用性に直接依存。 | **High** |
| F-05 | `veritas_os/core/kernel.py:849-865` | FUJI gate 例外ハンドラ | FUJI評価自体の例外時は `deny` にフォールバック（fail-close） | これ自体は正しいが、`(TypeError, ValueError, RuntimeError)` のみをcatchしており、`OSError` や `TimeoutError` は未捕捉で上位に伝播する可能性がある。 | **Medium** |
| F-06 | `veritas_os/core/fuji.py:1320-1352` | `fuji_gate()` TrustLog書込 | FUJI結果のTrustLog記録にsafety_head_modelフィールドを含むが、rule vs LLM判定の区別が曖昧 | `safety_head_model: "heuristic_fallback"` と `"gpt-4.1-mini"` が混在するが、`decision_status` に判定ソースが直接紐付かない。監査時に「この deny は rule か LLM か」の判別にフィールド横断が必要。 | **High** |
| F-07 | `veritas_os/core/debate.py:876` / `veritas_os/core/kernel.py:788,795` / `veritas_os/core/planner.py:1073` | debate/kernel/planner | すべての判定結果に `"source": "openai_llm"` がハードコード | debate結果、planner結果が常に `openai_llm` と記録される。実際にはfallbackでローカル判定の場合もあり、監査ログが不正確。 | **High** |
| F-08 | `veritas_os/core/value_core.py:186` | `evaluate()` | ValueCoreのevaluateにfail-safe未設定 | ValueCore評価が例外を投げた場合の動作がevaluate内で定義されていない。呼び出し元依存。 | **Medium** |
| F-09 | `veritas_os/core/llm_client.py:88` | `LLM_MODEL` | デフォルトモデルが `gpt-4.1-mini` にハードコード | 環境変数未設定時にOpenAI固定。マルチプロバイダー対応を謳いながら実質OpenAI単一依存。 | **Medium** |

---

## 2. 根本問題の整理

### 2.1 なぜ危険か

#### TrustLog: 「監査可能」が成立していない

1. **暗号化が壊れている。** `encrypt()` は機能するが `decrypt()` は暗号文をそのまま返す。つまり暗号化を有効にするとデータが読めなくなるだけで、セキュリティ上の価値がない。さらに暗号アルゴリズム自体がAESではなくSHA256-PRFの非標準方式。
2. **Redactionがメインログに適用されていない。** `mask_pii` は shadow_decide のみに適用。本体の `append_trust_log()` にはユーザクエリが平文保存される。
3. **暗号化がopt-in。** `VERITAS_ENCRYPTION_KEY` 環境変数が未設定（デフォルト状態）ではすべて平文。起動時に警告すら出ない。
4. **三重ログの不整合。** `trust_log.json`、`trust_log.jsonl`、署名付きJSONL の3つが独立存在し、権威性の定義がない。

#### FUJI Gate: 「Safety」が LLM 単一障害点に依存

1. **LLM障害時のfallbackが弱すぎる。** heuristicは禁止ワード17個のexact matchのみ。リスクフロアは0.30で、deny閾値に届かない。「LLMが落ちた = 安全性チェックが実質無効」という状態。
2. **deterministicルールが不十分。** Policy Engineは `_apply_policy()` で閾値ベースの判定を行うが、入力のリスクスコア自体がLLM依存。LLMが `risk=0.05` を返せば Policy Engine も通過させる。
3. **監査ログ上のソース混在。** `"source": "openai_llm"` がハードコードされており、heuristic fallback時でもLLM判定と記録される場合がある。FUJI側は `safety_head_model` で区別するが、debate/planner/kernel層では区別されない。

### 2.2 なぜ「監査可能」「AI Safety」の主張と矛盾するか

| 主張（README / docs） | 実装の実態 | 矛盾 |
|----------------------|-----------|------|
| 「tamper-evident audit trails」 | ハッシュチェーンは実装済みだが、署名付きログはbest-effort。署名失敗時は無署名ログのみ残る | 改ざん「検出」はできるが「防止」はできない。署名なしログは改ざんし放題 |
| 「Encryption at rest」 | decrypt()が暗号文を返す。暗号方式はAESではなくSHA256-PRF | 暗号化は有効にできるが復号できない。アルゴリズム名称も虚偽 |
| 「PII masking before persisting」 | shadow_decide のみ。main trust_log は平文 | READMEの推奨事項が実装されていない |
| 「Safety & compliance enforced by FUJI Gate」 | LLM障害時はheuristic(17ワード)にfallback。risk floor=0.30→allow | LLM不在でSafety判定が実質無効化される |
| 「deterministic, safety-gated pipeline」 | Safety HeadのリスクスコアがLLM依存。deterministicなのはPolicy Engineの閾値判定のみ | 入力が非決定的なのに出力だけ決定的でも意味がない |
| 「Production Ready (98%)」(`veritas_os/README.md`) | 暗号化壊れ、PII漏洩、Safety fallback不足 | 同リポジトリのREADME.mdは「In Development」。矛盾する主張が共存 |
| 「EU AI Act Art. 12 compliant」 | opt-in暗号化、壊れたdecrypt、非標準暗号方式 | コンプライアンス主張の根拠が技術的に成立していない |

---

## 3. 修正設計

### 3.1 TrustLog の修正

#### 3.1.1 暗号化の修正 (`encryption.py`)

**方針:** SHA256-PRFを廃止し、`cryptography` ライブラリの Fernet (AES-128-CBC + HMAC-SHA256) に完全移行。

```
変更点:
1. _aes_encrypt_block() を削除
2. encrypt() → Fernet.encrypt() に置換
3. decrypt() → Fernet.decrypt() に置換（実際に復号する）
4. is_encryption_enabled() は維持
5. generate_key() → Fernet.generate_key() に置換
6. 暗号化失敗時のplaintext fallbackを削除（fail-close）
```

**新規追加:**
- 起動時チェック: `VERITAS_ENCRYPTION_KEY` 未設定時に WARNING ログ + `get_encryption_status()` に「non-compliant」フラグ
- `VERITAS_REQUIRE_ENCRYPTION=true` 環境変数: 設定時は鍵なしで起動拒否

**互換性影響:**
- 既存の `ENC:` プレフィックス付きデータは旧方式で暗号化されており、復号不可（元々復号できなかったため実質影響なし）
- migration: 旧暗号化データは破棄して再生成（元々読めないため）

#### 3.1.2 PII Redaction の強制 (`trust_log.py`)

**方針:** `append_trust_log()` にredactionを追加。opt-outではなくopt-in-to-raw。

```
変更点:
1. append_trust_log() 内で entry["query"] に mask_pii を適用
2. mask_pii import失敗時は query フィールドを "[REDACTED:sanitize_unavailable]" に置換（fail-close）
3. VERITAS_TRUSTLOG_RAW_QUERY=true 設定時のみ平文保存を許可（明示的opt-in）
```

**互換性影響:** queryフィールドがマスクされるため、trust_log.jsonlから生のクエリを読む処理（adapt.py等）に影響。adapt.pyはchosenフィールドを読むので影響軽微。

#### 3.1.3 ログ統合

**方針:** 三重ログを段階的に統合。

```
Phase 1: trust_log.json（配列形式）を廃止。trust_log.jsonl のみにする。
Phase 2: 署名付きログを trust_log.jsonl の各エントリに統合（エントリ内に signature フィールドを追加）。
Phase 3: trustlog_signed.py のスタンドアロンファイルを廃止。
```

### 3.2 pickle の除去

**方針:** 既に実質ブロック済み。残存する曖昧さのみ除去。

```
変更点:
1. config.py: enable_memory_joblib_model のデフォルトを False に変更
2. memory.py: PICKLE_RUNTIME_BLOCK_DEADLINE を削除し、無期限ブロックに変更
3. memory.py: _warn_for_legacy_pickle_artifacts() のログレベルをERROR→CRITICALに昇格し、
   VERITAS_PICKLE_BLOCK_STRICT=true 時は起動を中断するオプション追加
```

**互換性影響:** なし。既にruntime loadingは無効。設定値の変更のみ。
**migration:** 不要。

### 3.3 FUJI / ValueCore の二層化

**方針:** Safety判定を「Deterministic Layer（ルールベース、常時稼働）」と「LLM Layer（補強、オプション）」に明確分離。

#### 3.3.1 Deterministic Layer の強化

```
変更点:
1. llm_safety.py の _heuristic_analyze() を本格的なルールエンジンに拡張:
   - 禁止パターンをYAML外部ファイル化（現行17ワード → 数百パターン）
   - 正規表現ベースの複合パターンマッチ追加
   - Unicode正規化（NFKC）後のマッチング
   - カテゴリ別の閾値設定

2. fuji.py の fuji_core_decide() にLLM非依存のリスクフロア導入:
   - deterministicルールでillicit検出時 → risk >= 0.70（deny閾値到達）
   - deterministicルールでPII検出時 → risk >= 0.50
   - LLM unavailable時 → risk += 0.20 のペナルティ（現行0.30→0.50以上に）
```

#### 3.3.2 LLM Layer のfail-safe強化

```
変更点:
1. llm_safety.py run():
   - LLM失敗時に ok=True を返さない → ok=False, fallback=True を返す
   - 呼び出し元が fallback を検知して追加ペナルティを適用

2. fuji.py run_safety_head():
   - LLMエラー時のリスクフロアを 0.30 → 0.50 に引き上げ
   - stakes >= 0.7 の場合はリスクフロアを 0.70（deny強制）に設定

3. kernel.py FUJI gate 例外ハンドラ:
   - catch対象に OSError, TimeoutError を追加
```

#### 3.3.3 監査ログの判定ソース明確化

```
変更点:
1. debate.py / kernel.py / planner.py:
   - "source": "openai_llm" のハードコードを削除
   - 実際のプロバイダー名を動的に設定: llm_client.LLM_PROVIDER を使用
   - fallback時は "source": "deterministic_fallback" を明記

2. fuji.py TrustLog記録:
   - "judgment_source" フィールドを追加: "llm" | "heuristic" | "deterministic_rule"
   - "llm_available" フィールドを追加: true | false
```

### 3.4 互換性影響まとめ

| 変更 | 破壊的変更 | 影響範囲 | migration |
|------|-----------|---------|-----------|
| encryption.py → Fernet | あり（暗号方式変更） | 既存ENC:データ読み出し不可（元々不可） | 不要（旧データは復号できなかった） |
| trust_log.py PII redaction | あり（queryフィールド変更） | queryを直接読む処理 | adapt.py等の確認必要 |
| trust_log.json廃止 | あり | trust_log.jsonを直接読むコード | `load_trust_log()` の戻り値をJSONL読み出しに統一 |
| config enable_memory_joblib_model | なし（default変更のみ） | なし | 不要 |
| heuristic強化 | なし（stricterなだけ） | false positiveが増加する可能性 | 閾値チューニング必要 |
| LLM failureリスクフロア変更 | あり（0.30→0.50） | LLM障害時にholdされる判定が増加 | オペレーション周知 |
| sourceフィールド値変更 | あり | "openai_llm"を前提としたテスト・ダッシュボード | テスト修正、ダッシュボード修正 |

---

## 4. 実装順序

### Task 2: TrustLog 暗号化修正 (Critical)

**対象:** `veritas_os/logging/encryption.py`
**理由:** decrypt()が壊れている状態は「データ損失」リスク。暗号化を有効にした環境では既にデータが読めない可能性がある。最優先で修正。

作業内容:
1. `cryptography` パッケージを requirements.txt に追加
2. encrypt/decrypt を Fernet ベースに書き換え
3. `_aes_encrypt_block()` のSHA256-PRFを削除
4. 暗号化失敗時のplaintext fallbackを削除
5. 起動時の暗号化ステータス警告を追加
6. テスト: encrypt→decrypt の往復テスト

### Task 3: TrustLog PII Redaction + ログ統合 (High)

**対象:** `veritas_os/logging/trust_log.py`
**理由:** T-06（PII平文保存）はデータ保護規制違反に直結。暗号化修正の次に対処。

作業内容:
1. `append_trust_log()` に mask_pii 適用を追加
2. mask_pii 不在時の fail-close 実装
3. trust_log.json（配列）の廃止準備
4. 署名付きログとの統合設計

### Task 4: FUJI Safety 二層化 (Critical)

**対象:** `veritas_os/tools/llm_safety.py`, `veritas_os/core/fuji.py`
**理由:** F-01（LLM障害時fail-open）はSafety根幹の問題。暗号化・redactionの後に着手するのは、ログ修正が先にないと修正後の動作を正しく監査できないため。

作業内容:
1. `_heuristic_analyze()` をYAML駆動のルールエンジンに拡張
2. LLM failure時のリスクフロア引き上げ（0.30→0.50、high-stakesは0.70）
3. `run_safety_head()` のfallback処理を厳格化
4. kernel.py の例外catchを拡大

### Task 5: 監査ログ正確性 + 設定クリーンアップ (High)

**対象:** `veritas_os/core/debate.py`, `kernel.py`, `planner.py`, `config.py`, `memory.py`
**理由:** 監査ログの信頼性はTask 2-4の修正を検証するために必要だが、先行修正が安定してからの方がテストしやすい。

作業内容:
1. `"source": "openai_llm"` ハードコードの除去
2. `judgment_source` フィールドの追加
3. pickle関連のconfigクリーンアップ
4. テスト修正

---

### 実装順序の根拠

```
Task 2 (暗号化) → Task 3 (Redaction) → Task 4 (Safety二層化) → Task 5 (監査ログ)
```

1. **Task 2が最優先:** decrypt()の破壊は即座に修正が必要。暗号化を有効にしている環境ではデータアクセス不能の可能性。
2. **Task 3が次:** PII保護はGDPR/個人情報保護法の観点で法的リスク。暗号化修正後にログフォーマットを安定させる。
3. **Task 4はその次:** Safety fallbackの強化はシステムの安全性根幹だが、修正の監査にはまずログが信頼できる状態である必要がある。
4. **Task 5は最後:** 他のTaskの修正を正しく記録するためのログ正確性向上。他のTaskが安定してから着手。

---

## Appendix: docs と実装の不一致一覧

| 文書 | 主張 | 実装 | ステータス |
|------|------|------|-----------|
| README.md | 「Force PII masking before persisting TrustLog/Memory」 | shadow_decide のみ。main trust_log は未適用 | **不一致** |
| README.md | 「Encryption at rest (optional)」 | opt-inだが、decrypt()が壊れている | **不一致（機能しない）** |
| veritas_os/README.md | 「Production Ready (98%)」 | README.md は「In Development」、SECURITY.md は「currently in active development」 | **矛盾** |
| eu_ai_act_compliance_review.md | 「Fernetベース静止暗号化サポート」 | FernetではなくSHA256-PRFベース | **虚偽** |
| eu_ai_act_compliance_review.md | 「Article 12: ✅ 準拠」 | 暗号化壊れ、PII未redact | **不一致** |
| docs/notes/TRUSTLOG_VERIFICATION_REPORT.md | 「🔴 sha256_prevがハッシュ計算に使用されていない」 | trust_log.py:390 で sha256_prev を結合している（**修正済み**） | **一致（修正完了）** |
| eu_ai_act/risk_assessment.md | 「RR-05: OpenAI API availability → 許容」理由:「意思決定支援であり自律決定ではない」 | FUJI Safety Headが完全にLLM依存。heuristic fallbackは17ワードのみ | **過小評価** |
| MEMORY_PICKLE_MIGRATION.md | 「Runtimeでのpickle読み込みは禁止」 | 実装と一致。ただし deadline が残存 | **概ね一致** |
