# VERITAS コードレビュー報告書
## 3原則に基づく評価

**レビュー日**: 2026-01-30
**対象バージョン**: VERITAS OS v2.0
**レビュアー**: Claude Code Review

---

## 概要

VERITASの3つの核心原則に基づき、コードベース全体をレビューした。

| 原則 | 評価 | スコア |
|------|------|--------|
| 不変条件（再現性・監査性） | ✅ 優秀 | 9/10 |
| 境界設計（通す／止める） | ✅ 良好 | 8/10 |
| 責任分界 | ⚠️ 改善余地あり | 7/10 |

---

## 1. 不変条件（再現性・監査性）

### ✅ 優れている点

#### 1.1 TrustLog のハッシュチェーン設計 (logging.py, trust_log.py)

```
論文の式: hₜ = SHA256(hₜ₋₁ || rₜ)
```

**実装評価**: 完璧に論文準拠

```python
# logging.py:117-126
entry_json = _normalize_entry_for_hash(entry)
if prev_hash:
    combined = prev_hash + entry_json
else:
    combined = entry_json
entry["sha256"] = _sha(combined)
```

- `sha256_prev` と `sha256` フィールドを除外した正規化 → 再計算可能
- `sort_keys=True` で JSON 順序を固定 → 決定論的
- `verify_trust_log()` 関数で整合性検証可能 → 監査可能

#### 1.2 atomic_io による耐障害性 (atomic_io.py)

```python
# atomic_io.py:54-84
# 1. 同一ディレクトリに一時ファイル作成
# 2. os.fsync() でディスク書き込み保証
# 3. os.replace() で原子的リネーム
```

**不変条件**: 電源断・クラッシュ時も中間状態でファイルが壊れない

#### 1.3 時刻の一貫性 (UTC ISO8601)

```python
# logging.py:47-49
def iso_now() -> str:
    """ISO8601 UTC時刻（監査ログ標準フォーマット）"""
    return datetime.now(timezone.utc).isoformat()
```

**全モジュールで統一**: `timezone.utc` を使用し、ローカル時刻の曖昧さを排除

### ⚠️ 改善提案

#### 1.4 TrustLog の二重実装問題

**問題**: `core/logging.py` と `logging/trust_log.py` の2箇所に類似実装が存在

```
veritas_os/core/logging.py       → append_trust_log()
veritas_os/logging/trust_log.py  → append_trust_log()
```

**リスク**: どちらが正規かが曖昧、将来の不整合の温床

**推奨**:
```python
# core/logging.py は薄いラッパーにする
from veritas_os.logging.trust_log import append_trust_log as _append
def append_trust_log(entry: Dict[str, Any]) -> Dict[str, Any]:
    return _append(entry)
```

#### 1.5 request_id の生成タイミング

**現状**: 複数箇所で `uuid.uuid4().hex` を生成
```python
# kernel.py:783
req_id = ctx.get("request_id") or uuid.uuid4().hex
# pipeline.py でも同様
```

**推奨**: API エントリポイントで一度だけ生成し、全層で伝播させる「単一生成点」を設ける

---

## 2. 境界設計（通す／止める）

### ✅ 優れている点

#### 2.1 FUJI Gate の多層防御 (fuji.py)

```
┌─────────────────────────────────────────────────────┐
│  Layer 1: Keyword Blocking (BANNED_KEYWORDS)        │
│  Layer 2: LLM Safety Head (run_safety_head)         │
│  Layer 3: Policy Engine (_apply_policy)             │
│  Layer 4: Evidence Gate (min_evidence check)        │
│  Layer 5: PoC Mode Override (deny/hold強制)         │
└─────────────────────────────────────────────────────┘
```

**不変条件の強制** (fuji.py:674-686):
```python
# status == "deny" => decision_status == "deny" を強制
if status == "deny" and decision_status != "deny":
    decision_status = "deny"
    rejection_reason = rejection_reason or "policy_deny_coerce"

# decision_status == "deny" => rejection_reason必須を強制
if decision_status == "deny" and not rejection_reason:
    rejection_reason = "policy_or_poc_gate_deny"
```

#### 2.2 Policy as Code (fuji_default.yaml)

```yaml
categories:
  self_harm:
    max_risk_allow: 0.05      # 5%超えたら即deny
    action_on_exceed: "deny"
  PII:
    max_risk_allow: 0.20
    action_on_exceed: "human_review"
```

**VERITASらしさ**:
- しきい値が YAML で宣言的に定義 → 監査可能
- カテゴリごとに異なるアクション → きめ細かい境界制御

#### 2.3 PII サニタイズの堅牢性 (sanitize.py)

```python
# 多層検出パターン（優先順位付き）
self._patterns: List[tuple] = [
    ("url_credential", ..., 0.95),  # 最高優先
    ("email", ..., 0.90),
    ("credit_card", ..., 0.85),     # Luhnチェック付き
    ("my_number", ..., 0.80),       # チェックデジット検証
    ...
]
```

**境界設計**:
- 信頼度 (confidence) 付きで検出 → 誤検出時の判断材料
- チェックサム検証 → 偽陽性を削減
- 重複範囲の除外 → 二重マスク防止

### ⚠️ 改善提案

#### 2.4 Safety Head フォールバックの境界が甘い

**現状** (fuji.py:300-336):
```python
def _fallback_safety_head(text: str) -> SafetyHeadResult:
    # キーワードマッチのみ
    hits = [w for w in BANNED_KEYWORDS if w in t]
```

**問題**:
- LLM Safety Head が落ちた時のフォールバックが単純なキーワードマッチのみ
- `safety_head_error` カテゴリが追加されるが、リスクスコアは0.05のまま開始

**推奨**:
```python
# エラー時はベースリスクを上げる
def _fallback_safety_head(text: str) -> SafetyHeadResult:
    risk = 0.30  # 0.05 → 0.30 (不確実性を反映)
```

#### 2.5 境界判定の分散

**現状**:
- `kernel.py` でも FUJI Gate を呼ぶ
- `pipeline.py` でも FUJI Gate を呼ぶ
- 二重呼び出しの可能性（スキップフラグで対処中）

**推奨**: 「FUJI Gate は Pipeline でのみ呼ぶ」という責任の明確化

---

## 3. 責任分界

### ✅ 優れている点

#### 3.1 モジュール分割

```
core/
├── kernel.py      → オーケストレーション（意思決定の統合）
├── pipeline.py    → API層との接続（FastAPI対応）
├── fuji.py        → 安全ゲート（通す/止める判定）
├── debate.py      → 多視点評価（Pro/Con/Third-party）
├── planner.py     → 計画生成（ステップ分解）
├── evidence.py    → 証拠収集（Memory/Web/World）
├── value_core.py  → 価値評価（Telos Score計算）
└── memory.py      → 長期記憶（Episodic/Semantic）
```

**VERITASらしさ**: 各モジュールが単一責任を持ち、疎結合

#### 3.2 TypedDict による型定義 (types.py)

```python
class FujiDecisionDict(TypedDict, total=False):
    status: FujiInternalStatus           # allow|warn|human_review|deny
    decision_status: FujiDecisionStatus  # allow|hold|deny
    rejection_reason: Optional[str]
    ...
```

**境界の明確化**:
- 内部状態 (`status`) と外部状態 (`decision_status`) を分離
- Protocol による構造的部分型 → インターフェース契約

### ⚠️ 改善提案

#### 3.3 kernel.py の肥大化

**現状**: `kernel.py` は 1458 行で、以下を全て担当:
- Simple QA 処理
- Knowledge QA 処理
- Intent 検出
- Options スコアリング
- DebateOS 呼び出し
- MemoryOS 連携
- World Model 連携
- Persona 学習
- AGI Goals 調整

**問題**: 単一ファイルに過剰な責任が集中

**推奨**: 責任ごとにファイル分割
```
core/
├── kernel.py           → オーケストレーションのみ（100行程度）
├── kernel_qa.py        → Simple QA / Knowledge QA
├── kernel_intent.py    → Intent検出・Options生成
├── kernel_scoring.py   → スコアリングロジック
└── kernel_hooks.py     → Persona/AGI Goals更新
```

#### 3.4 Pipeline と Kernel の責任重複

**現状**:
```python
# pipeline.py
if not ctx.get("_pipeline_evidence"):
    evidence = gather_evidence(...)  # Pipeline が収集

# kernel.py
if not pipeline_evidence:
    mem_evs = mem_core.get_evidence_for_decision(...)  # Kernel も収集
```

**問題**:
- 両者が `_skip_reasons` フラグで二重実行を防いでいるが、本来は責任が明確なら不要
- フラグ依存の設計は脆弱

**推奨**:
- **Pipeline**: リクエスト検証、レート制限、ログ記録、レスポンス整形
- **Kernel**: 純粋な意思決定ロジック（外部I/Oなし）
- **Evidence/Memory/World**: 外部データ取得（Kernelから呼び出し可能なサービス層）

#### 3.5 try/except の過剰使用

**現状** (pipeline.py の冒頭):
```python
try:
    from . import kernel as veritas_core
except Exception as e:
    veritas_core = None
    _warn(f"[WARN] kernel import failed: {repr(e)}")
```

**意図**: インポート時のクラッシュを防ぐ（ISSUE-4 対応）

**問題**:
- 本来存在すべきモジュールがないことを隠蔽
- 「kernel がない Pipeline」は意味をなさない

**推奨**:
- **必須モジュール**: インポート失敗は即例外（早期発見）
- **オプショナルモジュール**: try/except で吸収（明示的に `Optional` とする）

```python
# 必須
from . import kernel as veritas_core  # 失敗したら落ちてOK

# オプショナル（明示）
try:
    from . import strategy as strategy_core
except ImportError:
    strategy_core = None  # StrategyOS は optional
```

---

## 4. 総合評価と推奨アクション

### 4.1 VERITASらしさ評価

| 観点 | 評価 |
|------|------|
| 監査可能性 | ✅ TrustLog のハッシュチェーンは論文準拠で優秀 |
| 再現性 | ✅ JSON 正規化、UTC 時刻統一、atomic I/O |
| 境界明確性 | ✅ FUJI Gate の多層防御、Policy as Code |
| 不変条件強制 | ✅ deny → rejection_reason 必須の強制 |
| 責任分離 | ⚠️ kernel.py の肥大化、Pipeline/Kernel の責任重複 |

### 4.2 推奨アクション（優先順）

1. **[高] TrustLog 実装の統一**
   - `core/logging.py` は `logging/trust_log.py` へのラッパーに
   - 「正規のTrustLog」を一箇所に集約

2. **[高] Kernel の分割**
   - QA処理、Intent検出、スコアリングを別ファイルに
   - kernel.py は純粋なオーケストレーションのみに

3. **[中] Safety Head フォールバックのリスク引き上げ**
   - LLM エラー時のベースリスクを 0.05 → 0.30 へ

4. **[中] 必須/オプショナルモジュールの明確化**
   - Pipeline.py の try/except を整理
   - 必須モジュール失敗は即座にエラー

5. **[低] Pipeline/Kernel の責任再定義**
   - Pipeline = リクエスト/レスポンス処理
   - Kernel = 純粋な意思決定（外部I/Oなし）

---

## 5. 結論

VERITASは「不変条件」と「境界設計」において**非常に優れた実装**を持つ。特に:

- **TrustLog のハッシュチェーン**: 論文の式に完全準拠し、改竄検知が可能
- **FUJI Gate の多層防御**: キーワード→LLM→ポリシー→エビデンスの階層構造
- **Policy as Code**: YAML による宣言的なセキュリティポリシー

一方、「責任分界」については**改善の余地**がある:

- **kernel.py の肥大化**: 1458行に過剰な責任が集中
- **Pipeline/Kernel の重複**: 二重実行防止フラグによる暫定対処

これらを改善することで、VERITASは「AGI安全性の参照実装」としてより堅牢になる。

---

**レビュー完了**
