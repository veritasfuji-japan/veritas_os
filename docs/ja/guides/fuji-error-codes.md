# FUJI Standard Codes (F-1xxx〜F-4xxx)

## コード範囲とレイヤー

FUJI Standard Codes は `F-1xxx` から `F-4xxx` までの範囲で、先頭の数字が思考レイヤーを表します。

| レイヤー | コード範囲 | 意味 |
| --- | --- | --- |
| Data & Evidence | F-1xxx | データと証拠の整合性 |
| Logic & Debate | F-2xxx | 推論・議論の整合性 |
| Value & Policy | F-3xxx | 価値優先度・ポリシー適合 |
| Safety & Security | F-4xxx | セキュリティ・安全上のリスク |

## 新しいコードの追加方法

1. `veritas_os/core/fuji_codes.py` の `FUJI_REGISTRY` にエントリを追加します。
2. コードは正規表現 `^F-[1-4]\d{3}$` に一致する必要があります。
3. `FujiError` と `FujiFeedback` を必ず定義し、`layer`/`severity`/`blocking`/`feedback.action` を明示します。
4. 追加後は `validate_fuji_code` とテストを更新し、CIで確認します。

## severity / blocking / action の意味

- **severity**
  - `LOW`: 軽微、修正推奨
  - `MEDIUM`: 明確なリスクあり
  - `HIGH`: 重大なリスク（必ず `blocking=True`）
- **blocking**
  - `True`: FUJI Gate が拒否を返すべき状況
  - `False`: 修正/補完で継続可能
- **feedback.action**
  - `RE-DEBATE`: 再討議
  - `RE-CRITIQUE`: 再批判
  - `REQUEST_EVIDENCE`: 根拠要求
  - `REWRITE_PLAN`: 計画の再構成
  - `HUMAN_REVIEW`: 人間レビュー

## REJECTED 応答例

### F-2101 (Critique Unresolved)

```json
{
  "status": "REJECTED",
  "gate": "FUJI_SAFETY_GATE_v2",
  "error": {
    "code": "F-2101",
    "message": "Critique Unresolved",
    "detail": "Critiqueで指摘されたリスクがPlanに反映されていません。",
    "layer": "Logic & Debate",
    "severity": "HIGH",
    "blocking": true
  },
  "feedback": {
    "action": "RE-DEBATE",
    "hint": "指摘されたリスクを反映した上で議論を再実行し、修正案を提示してください。"
  },
  "trust_log_id": "TL-20250101-0001"
}
```

### F-3001 (ValueCore Mismatch)

```json
{
  "status": "REJECTED",
  "gate": "FUJI_SAFETY_GATE_v2",
  "error": {
    "code": "F-3001",
    "message": "ValueCore Mismatch",
    "detail": "優先価値より別価値を優先しておりポリシー違反です。",
    "layer": "Value & Policy",
    "severity": "HIGH",
    "blocking": true
  },
  "feedback": {
    "action": "REWRITE_PLAN",
    "hint": "優先価値（例: 安全性）を最上位に置いた計画へ修正してください。"
  },
  "trust_log_id": "TL-20250101-0002"
}
```

### F-4003 (Sensitive Info Leak Risk)

```json
{
  "status": "REJECTED",
  "gate": "FUJI_SAFETY_GATE_v2",
  "error": {
    "code": "F-4003",
    "message": "Sensitive Info Leak Risk",
    "detail": "個人情報/機密情報の漏洩リスクがあります。",
    "layer": "Safety & Security",
    "severity": "MEDIUM",
    "blocking": true
  },
  "feedback": {
    "action": "REWRITE_PLAN",
    "hint": "個人情報を削除またはマスクし、安全な範囲に修正してください。"
  },
  "trust_log_id": "TL-20250101-0003"
}
```
