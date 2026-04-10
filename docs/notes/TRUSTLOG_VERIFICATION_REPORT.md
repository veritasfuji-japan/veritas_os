# TrustLog実装検証レポート

**検証日**: 2025年11月30日  
**対象**: trust_log.py, verify_trust_log.py, dataset_writer.py, generate_report.py

---

## 2026-04 Unified verifier update

### Stable API

- `veritas_os.audit.trustlog_verify.verify_full_ledger(path, max_entries=None)`
- `veritas_os.audit.trustlog_verify.verify_witness_ledger(entries, verify_signature_fn)`
- `veritas_os.audit.trustlog_verify.verify_trustlogs(full_log_path, witness_entries, verify_signature_fn, max_entries=None)`

### Stable CLI

```bash
python -m veritas_os.scripts.verify_trust_log --json
python -m veritas_os.scripts.verify_trust_log --full-log /path/to/trust_log.jsonl --witness-log /path/to/trustlog.jsonl
```

CLI / API summary fields:
- `total_entries`
- `valid_entries`
- `invalid_entries`
- `chain_ok`
- `signature_ok`
- `linkage_ok`
- `mirror_ok`
- `last_hash`
- `detailed_errors`

### Compatibility behavior

- Legacy witness entries without `full_payload_hash` or `mirror_receipt` remain valid.
- `full_payload_hash` is validated only when present (must be SHA-256 hex).
- `mirror_receipt` structure is validated only when present.
- Existing APIs (`verify_trust_log`, `verify_trustlog_chain`) continue to work and now reuse shared verification logic.

---

## 📊 論文記載との整合性

### 論文の記述 (Section 2.3)

```
Each decision produces a JSON record rₜ.

VERITAS stores:
hₜ = SHA256(hₜ₋₁ || rₜ)

This implementation exists in the public codebase and provides:
• immutability
• tamper detection
• auditability
```

---

## ✅ 実装検証

### 1. trust_log.py の実装

#### SHA-256計算（論文の式の実装）

```python
def _compute_sha256(payload: dict) -> str:
    """
    entry 用の SHA-256 ハッシュを計算する。
    - dict を key でソートして JSON 化
    - それを UTF-8 でエンコードして sha256 に通す
    """
    try:
        s = json.dumps(payload, sort_keys=True, 
                      ensure_ascii=False).encode("utf-8")
    except Exception:
        s = repr(payload).encode("utf-8", "ignore")
    return hashlib.sha256(s).hexdigest()
```

**評価**: ✅ 正確な実装

#### ハッシュチェーン実装

```python
def append_trust_log(entry: dict) -> None:
    # ---- 直前ハッシュの取得 ----
    items = _load_logs_json()
    sha256_prev = None
    if items:
        last = items[-1]
        sha256_prev = last.get("sha256")  # hₜ₋₁

    entry["sha256_prev"] = sha256_prev
    
    # 自分自身のハッシュを計算
    hash_payload = dict(entry)
    hash_payload.pop("sha256", None)
    entry["sha256"] = _compute_sha256(hash_payload)  # hₜ = SHA256(rₜ)
```

**数式との対応**:
- `sha256_prev` = hₜ₋₁
- `entry` = rₜ (decision record)
- `entry["sha256"]` = hₜ

**評価**: ⚠️ **実装に問題あり**

---

## 🔴 重大な問題発見

### 問題1: ハッシュチェーンの不完全性

**論文の式**:
```
hₜ = SHA256(hₜ₋₁ || rₜ)
```

**期待される実装**:
```python
# hₜ₋₁ と rₜ を連結してハッシュ化
payload = f"{sha256_prev}{json.dumps(entry)}"
entry["sha256"] = hashlib.sha256(payload.encode()).hexdigest()
```

**実際の実装**:
```python
# rₜ のみをハッシュ化（hₜ₋₁ を含まない）
hash_payload = dict(entry)  # rₜ
hash_payload.pop("sha256", None)
entry["sha256"] = _compute_sha256(hash_payload)  # SHA256(rₜ) のみ
```

**問題点**:
- `sha256_prev`はentryに**含まれるだけ**で、ハッシュ計算に**使われていない**
- これはブロックチェーンの「チェーン」になっていない
- 改ざん検知が不完全

**影響**:
- エントリ単体の改ざんは検知可能 ✅
- 順序の入れ替えは検知**不可能** ❌
- エントリの削除は検知**困難** ❌

---

## 🔧 修正案

### 修正版 trust_log.py

```python
def append_trust_log(entry: dict) -> None:
    """
    決定ごとの監査ログ（軽量）を JSONL + JSON に保存。
    論文の式に従った実装: hₜ = SHA256(hₜ₋₁ || rₜ)
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # ---- 直前ハッシュの取得 ----
    items = _load_logs_json()
    sha256_prev = None
    if items:
        last = items[-1]
        sha256_prev = last.get("sha256")

    # 元 entry を壊さないようにコピー
    entry = dict(entry)
    entry.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    entry["sha256_prev"] = sha256_prev

    # ✅ 修正: hₜ₋₁ || rₜ をハッシュ化
    hash_payload = dict(entry)
    hash_payload.pop("sha256", None)
    
    # rₜ を JSON化
    entry_json = json.dumps(hash_payload, sort_keys=True, ensure_ascii=False)
    
    # hₜ₋₁ || rₜ を結合
    if sha256_prev:
        combined = sha256_prev + entry_json
    else:
        combined = entry_json
    
    # SHA-256計算
    entry["sha256"] = hashlib.sha256(combined.encode("utf-8")).hexdigest()

    # ---- JSONL に1行追記 ----
    with open_trust_log_for_append() as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # ---- JSON(配列) を更新 ----
    items.append(entry)
    if len(items) > MAX_JSON_ITEMS:
        items = items[-MAX_JSON_ITEMS:]

    _save_json(items)
```

---

## ✅ verify_trust_log.py の検証

### 現在の実装

```python
def main():
    prev_hash = None
    for i, entry in enumerate(iter_entries(), 1):
        sha_prev = entry.get("sha256_prev")
        sha_self = entry.get("sha256")

        # prev チェック
        if sha_prev != prev_hash:
            print(f"[NG] line {i}: sha256_prev mismatch")
            return

        # 自分自身の hash 検証
        payload = dict(entry)
        payload.pop("sha256", None)
        calc = _compute_sha256(payload)
        if calc != sha_self:
            print(f"[NG] line {i}: sha256 invalid")
            return

        prev_hash = sha_self

    print("[OK] trust_log.jsonl: all entries valid")
```

**評価**: ⚠️ **現在の不完全な実装を検証している**

### 修正版 verify_trust_log.py

```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Trust Log Verifier - 論文の式に準拠

検証内容:
1. sha256_prev の連続性（チェーン検証）
2. hₜ = SHA256(hₜ₋₁ || rₜ) の正しさ
"""

import json
import hashlib
from pathlib import Path
from veritas_os.logging.paths import LOG_DIR

LOG_JSONL = LOG_DIR / "trust_log.jsonl"


def compute_hash(prev_hash: str | None, entry: dict) -> str:
    """
    論文の式に従ったハッシュ計算: hₜ = SHA256(hₜ₋₁ || rₜ)
    """
    payload = dict(entry)
    payload.pop("sha256", None)
    payload.pop("sha256_prev", None)
    
    entry_json = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    
    if prev_hash:
        combined = prev_hash + entry_json
    else:
        combined = entry_json
    
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def iter_entries():
    with open(LOG_JSONL, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def main():
    print("🔍 Trust Log Verification")
    print("=" * 60)
    print(f"File: {LOG_JSONL}")
    print()
    
    if not LOG_JSONL.exists():
        print("❌ trust_log.jsonl not found")
        return 1
    
    prev_hash = None
    total = 0
    errors = []
    
    for i, entry in enumerate(iter_entries(), 1):
        total = i
        sha_prev = entry.get("sha256_prev")
        sha_self = entry.get("sha256")
        
        # 1. チェーン連続性の検証
        if sha_prev != prev_hash:
            errors.append({
                "line": i,
                "type": "chain_break",
                "expected_prev": prev_hash,
                "actual_prev": sha_prev,
            })
        
        # 2. ハッシュ値の検証（論文の式に従う）
        calc_hash = compute_hash(sha_prev, entry)
        if calc_hash != sha_self:
            errors.append({
                "line": i,
                "type": "hash_mismatch",
                "expected": calc_hash,
                "actual": sha_self,
            })
        
        prev_hash = sha_self
    
    print(f"Total entries: {total}")
    print()
    
    if errors:
        print(f"❌ Verification FAILED ({len(errors)} errors)")
        print()
        for err in errors[:5]:  # 最初の5件だけ表示
            print(f"Line {err['line']}: {err['type']}")
            if err['type'] == 'chain_break':
                print(f"  Expected prev: {err['expected_prev']}")
                print(f"  Actual prev:   {err['actual_prev']}")
            else:
                print(f"  Expected hash: {err['expected']}")
                print(f"  Actual hash:   {err['actual']}")
            print()
        
        if len(errors) > 5:
            print(f"... and {len(errors) - 5} more errors")
        
        return 1
    else:
        print("✅ Verification PASSED")
        print(f"All {total} entries are valid")
        print("Hash chain is intact")
        return 0


if __name__ == "__main__":
    exit(main())
```

---

## 📊 dataset_writer.py の検証

### 現在の実装

```python
def _sha256_dict(d: Dict[str, Any]) -> str:
    try:
        s = json.dumps(d, ensure_ascii=False, sort_keys=True)
    except Exception:
        s = str(d)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()
```

**評価**: ✅ 単純なハッシュ計算は正しい

**用途**: 
- リクエスト/レスポンスのハッシュ計算
- TrustLogとは**別の目的**（データセット記録用）

**問題なし**: dataset_writer.pyはTrustLogのチェーン機能とは独立

---

## 🎯 まとめ

### 問題の重大度

| 問題 | 重大度 | 影響 | 修正難易度 |
|------|--------|------|-----------|
| **ハッシュチェーン不完全** | 🔴 HIGH | 論文記載と不一致 | EASY |
| verify_trust_log.py | 🟡 MEDIUM | 検証が不完全 | EASY |

### 修正の優先度

#### Priority 1: trust_log.py の修正（必須）

**理由**:
1. 論文の式 `hₜ = SHA256(hₜ₋₁ || rₜ)` と不一致
2. 学術的正確性に関わる
3. 改ざん検知が不完全

**所要時間**: 30分

**影響範囲**: 
- 既存ログは無効になる（再生成が必要）
- APIの動作には影響なし

#### Priority 2: verify_trust_log.py の更新

**理由**:
- 修正後のロジックに対応する検証が必要

**所要時間**: 30分

---

## 🔧 完全な修正版ファイル

### 1. trust_log_fixed.py

完全版は別ファイルで提供します。

主な変更点:
```python
# 旧実装（不完全）
entry["sha256"] = _compute_sha256(hash_payload)

# 新実装（論文準拠）
entry_json = json.dumps(hash_payload, sort_keys=True, ensure_ascii=False)
combined = (sha256_prev or "") + entry_json
entry["sha256"] = hashlib.sha256(combined.encode("utf-8")).hexdigest()
```

### 2. verify_trust_log_fixed.py

完全版は別ファイルで提供します。

---

## 📝 論文への影響

### 現在の状況

**論文記載**: 
```
hₜ = SHA256(hₜ₋₁ || rₜ)
This implementation exists in the public codebase
```

**実装**: 部分的に不一致 ⚠️

### 推奨対応

#### Option 1: 実装を修正（推奨）

- trust_log.py を修正
- verify_trust_log.py を更新
- 論文記載はそのまま（正しい式）

**メリット**:
- 論文と実装が完全一致
- 学術的に正確

**デメリット**:
- 既存ログが無効になる

#### Option 2: 論文を修正

論文の式を実装に合わせる：

```
# 現在の実装に合わせた記述
hₜ = SHA256(rₜ)
prev_hash = hₜ₋₁ (stored but not in hash)
```

**メリット**:
- 実装変更不要

**デメリット**:
- ハッシュチェーンの利点を失う
- 学術的価値が下がる

---

## 💡 推奨アクション

### 今すぐ実施

```bash
# 1. バックアップ
cp veritas_os/logging/trust_log.py veritas_os/logging/trust_log.py.backup

# 2. 修正版を適用
cp trust_log_fixed.py veritas_os/logging/trust_log.py
cp verify_trust_log_fixed.py scripts/verify_trust_log.py

# 3. 既存ログを退避
mv scripts/logs/trust_log.jsonl scripts/logs/trust_log.jsonl.old
mv scripts/logs/trust_log.json scripts/logs/trust_log.json.old

# 4. 新規ログで再開
# （次回 /v1/decide 実行時に自動生成）

# 5. 検証テスト
python scripts/verify_trust_log.py
```

### 論文対応

**v1.1で明記**:
```
Section 2.3:

The hash chain is implemented as:
  hₜ = SHA256(hₜ₋₁ || rₜ)

where || denotes string concatenation.

Implementation:
  combined = prev_hash + json.dumps(entry)
  current_hash = SHA256(combined)
```

---

## 結論

1. **重要な実装の不一致を発見** ❌
2. **修正は容易**（30分程度） ✅
3. **論文の正確性向上に貢献** ✅
4. **学術的厳密性が向上** ✅

修正版ファイルを提供します。
