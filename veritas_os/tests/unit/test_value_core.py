# veritas_os/tests/test_value_core.py
import json
from pathlib import Path

from veritas_os.core import value_core


# ============
# 基本ユーティリティ
# ============
def test_to_float_and_clip01_basic():
    assert value_core._to_float(1) == 1.0
    assert value_core._to_float(" 2.5 ") == 2.5
    assert value_core._to_float(None, default=0.7) == 0.7
    assert value_core._to_float("xxx", default=0.9) == 0.9

    assert value_core._clip01(-1) == 0.0
    assert value_core._clip01(0.5) == 0.5
    assert value_core._clip01(5) == 1.0
    assert value_core._clip01("0.3") == 0.3
    assert value_core._clip01("xxx") == 0.0


def test_normalize_weights_empty_returns_default_copy():
    result = value_core._normalize_weights({})
    assert result == value_core.DEFAULT_WEIGHTS
    # コピーであること（同一オブジェクトではない）
    assert result is not value_core.DEFAULT_WEIGHTS


def test_normalize_weights_clips_values():
    w = {"ethics": 2.0, "user_benefit": -1.0}
    result = value_core._normalize_weights(w)
    assert 0.0 <= result["ethics"] <= 1.0
    assert 0.0 <= result["user_benefit"] <= 1.0


# ============
# ValueProfile load/save/update
# ============
def test_value_profile_load_creates_default_when_missing(tmp_path, 
monkeypatch):
    cfg_dir = tmp_path / "veritas_cfg"
    monkeypatch.setattr(value_core, "CFG_DIR", cfg_dir)
    monkeypatch.setattr(value_core, "CFG_PATH", cfg_dir / "value_core.json")

    prof = value_core.ValueProfile.load()
    # デフォルト + 正規化された重みになっていること
    assert set(prof.weights.keys()) == set(value_core.DEFAULT_WEIGHTS.keys())
    assert all(0.0 <= v <= 1.0 for v in prof.weights.values())
    assert value_core.CFG_PATH.exists()


def test_value_profile_save_writes_normalized(tmp_path, monkeypatch):
    cfg_dir = tmp_path / "veritas_cfg2"
    monkeypatch.setattr(value_core, "CFG_DIR", cfg_dir)
    monkeypatch.setattr(value_core, "CFG_PATH", cfg_dir / "value_core.json")

    prof = value_core.ValueProfile(weights={"ethics": 2.0, "user_benefit": 
-1.0})
    prof.save()

    assert value_core.CFG_PATH.exists()
    with value_core.CFG_PATH.open(encoding="utf-8") as f:
        data = json.load(f)
    w = data["weights"]
    assert 0.0 <= w["ethics"] <= 1.0
    assert 0.0 <= w["user_benefit"] <= 1.0


def test_value_profile_update_from_scores_moves_toward_scores(tmp_path, 
monkeypatch):
    cfg_dir = tmp_path / "veritas_cfg3"
    monkeypatch.setattr(value_core, "CFG_DIR", cfg_dir)
    monkeypatch.setattr(value_core, "CFG_PATH", cfg_dir / "value_core.json")

    prof = value_core.ValueProfile(weights={"ethics": 0.0})
    prof.update_from_scores({"ethics": 1.0}, lr=0.5)

    # 0→1 を lr=0.5 で更新 → 0.5 付近になるはず
    assert 0.4 <= prof.weights["ethics"] <= 0.6
    assert value_core.CFG_PATH.exists()


# ============
# heuristic_value_scores
# ============
def test_heuristic_value_scores_negative_words():
    s = value_core.heuristic_value_scores("これは犯罪と違法な行為です", 
{})
    assert s["ethics"] == 0.0
    assert s["legality"] == 0.0
    assert s["harm_avoid"] == 0.0


def test_heuristic_value_scores_risky_words():
    s = value_core.heuristic_value_scores("これはギャンブルや投機の話です", {})
    assert s["reversibility"] <= 0.4 + 1e-6
    assert s["reversibility"] >= 0.4 - 1e-6
    assert s["efficiency"] <= 0.5 + 1e-6
    assert s["efficiency"] >= 0.5 - 1e-6


def test_heuristic_value_scores_positive_and_autonomy_words():
    s = value_core.heuristic_value_scores("このレポートを報告して説明と検証を行う", 
{})
    assert s["truthfulness"] >= 0.9
    assert s["accountability"] >= 0.8

    s2 = value_core.heuristic_value_scores("自動・自律システムについて", 
{})
    assert s2["autonomy"] >= 0.7


# ============
# evaluate（学習フラグあり/なし）
# ============
class _DummyProfileNoSave:
    def __init__(self):
        self.weights = value_core.DEFAULT_WEIGHTS.copy()
        self.updated = False

    def update_from_scores(self, scores, lr=0.02):
        self.updated = True

    def save(self):
        # 呼ばれない想定（必要ならダミー）
        pass


def test_evaluate_respects_no_learn_values(monkeypatch):
    dummy = _DummyProfileNoSave()

    # ValueProfile.load を差し替え
    monkeypatch.setattr(
        value_core.ValueProfile,
        "load",
        classmethod(lambda cls: dummy),
    )

    res = value_core.evaluate("テストクエリ", {"no_learn_values": True})
    assert isinstance(res, value_core.ValueResult)
    assert dummy.updated is False  # 学習されていない


class _DummyProfileWithSave:
    def __init__(self):
        self.weights = value_core.DEFAULT_WEIGHTS.copy()
        self.updated = False
        self.saved = False

    def update_from_scores(self, scores, lr=0.02):
        self.updated = True

    def save(self):
        self.saved = True


def test_evaluate_updates_when_learning_enabled(tmp_path, monkeypatch):
    dummy = _DummyProfileWithSave()

    cfg_dir = tmp_path / "veritas_cfg_eval"
    monkeypatch.setattr(value_core, "CFG_DIR", cfg_dir)
    monkeypatch.setattr(value_core, "CFG_PATH", cfg_dir / 
"value_core.json")

    monkeypatch.setattr(
        value_core.ValueProfile,
        "load",
        classmethod(lambda cls: dummy),
    )

    res = value_core.evaluate("コードを改善して最適化する", {})
    assert 0.0 <= res.total <= 1.0
    assert res.top_factors
    assert isinstance(res.rationale, str)
    assert dummy.updated is True


# ============
# update_weights
# ============
class _DummyProfileForUpdate:
    def __init__(self):
        self.weights = {"ethics": 0.5}
        self.saved = False

    def save(self):
        self.saved = True


def test_update_weights_uses_normalization(monkeypatch):
    dummy = _DummyProfileForUpdate()
    monkeypatch.setattr(
        value_core.ValueProfile,
        "load",
        classmethod(lambda cls: dummy),
    )

    result = value_core.update_weights({"ethics": 2.0, "user_benefit": 
10})
    assert dummy.saved is True
    assert 0.0 <= result["ethics"] <= 1.0
    assert 0.0 <= result["user_benefit"] <= 1.0


# ============
# rebalance_from_trust_log
# ============
class _DummyProfileForRebalance:
    def __init__(self):
        self.weights = {
            "truthfulness": 0.8,
            "accountability": 0.7,
            "efficiency": 0.6,
        }
        self.saved = False

    def save(self):
        self.saved = True


def test_rebalance_from_trust_log_handles_missing_file(tmp_path):
    # 存在しないパスでも例外なく終わること（print だけ）
    log_path = tmp_path / "no_such_log.jsonl"
    value_core.rebalance_from_trust_log(str(log_path))


def test_rebalance_from_trust_log_low_ema_increases_truth_and_accountability(
    tmp_path, monkeypatch
):
    dummy = _DummyProfileForRebalance()
    monkeypatch.setattr(
        value_core.ValueProfile,
        "load",
        classmethod(lambda cls: dummy),
    )

    log_path = tmp_path / "trust_log_low.jsonl"
    with log_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps({"score": 0.5}) + "\n")
        f.write(json.dumps({"score": 0.6}) + "\n")

    value_core.rebalance_from_trust_log(str(log_path))

    assert dummy.saved is True
    assert dummy.weights["truthfulness"] >= 0.8
    assert dummy.weights["accountability"] >= 0.7


def test_rebalance_from_trust_log_high_ema_increases_efficiency(tmp_path, 
monkeypatch):
    dummy = _DummyProfileForRebalance()
    monkeypatch.setattr(
        value_core.ValueProfile,
        "load",
        classmethod(lambda cls: dummy),
    )

    log_path = tmp_path / "trust_log_high.jsonl"
    with log_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps({"score": 0.95}) + "\n")
        f.write(json.dumps({"score": 0.98}) + "\n")

    value_core.rebalance_from_trust_log(str(log_path))

    assert dummy.saved is True
    assert dummy.weights["efficiency"] >= 0.6


def test_rebalance_from_trust_log_skips_invalid_rows(tmp_path, monkeypatch):
    dummy = _DummyProfileForRebalance()
    monkeypatch.setattr(
        value_core.ValueProfile,
        "load",
        classmethod(lambda cls: dummy),
    )

    log_path = tmp_path / "trust_log_mixed.jsonl"
    with log_path.open("w", encoding="utf-8") as f:
        f.write("not-json\n")
        f.write(json.dumps({"score": "oops"}) + "\n")
        f.write(json.dumps({"score": 0.9}) + "\n")

    value_core.rebalance_from_trust_log(str(log_path))

    assert dummy.saved is True


# ============
# append_trust_log
# ============
def test_append_trust_log_writes_jsonl(tmp_path, monkeypatch):
    """
    value_core.append_trust_log は正規の logging.trust_log.append_trust_log に委譲する。
    テストでは正規側のパスをモンキーパッチする。
    """
    from veritas_os.logging import trust_log as tl
    from veritas_os.logging import paths as log_paths

    log_jsonl = tmp_path / "trust_log.jsonl"
    log_json = tmp_path / "trust_log.json"

    monkeypatch.setattr(tl, "LOG_JSONL", log_jsonl)
    monkeypatch.setattr(tl, "LOG_JSON", log_json)
    monkeypatch.setattr(tl, "LOG_DIR", tmp_path)
    monkeypatch.setattr(log_paths, "LOG_JSONL", log_jsonl)

    value_core.append_trust_log(
        user_id="user123",
        score=1.5,  # クリップされるはず
        note="test-note",
        source="unit",
        extra={"foo": "bar"},
    )

    assert log_jsonl.exists()
    lines = log_jsonl.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1

    raw_line = lines[0]
    # If encryption is enabled, decrypt before parsing JSON
    if raw_line.startswith("ENC:"):
        from veritas_os.logging.encryption import decrypt
        raw_line = decrypt(raw_line)
    rec = json.loads(raw_line)

    assert rec["user_id"] == "user123"
    assert rec["score"] == 1.0  # 0..1 にクリップされている
    assert rec["note"] == "test-note"
    assert rec["source"] == "unit"
    assert rec["extra"]["foo"] == "bar"
    # ★ 正規trust_logに委譲されたため、sha256ハッシュチェーンも付与される
    assert "sha256" in rec
    assert rec["type"] == "trust_feedback"


# ============
# ValueResult 後方互換性
# ============
def test_value_result_backward_compat_positional():
    """既存コードが positional args で ValueResult を生成しても動作すること。"""
    r = value_core.ValueResult({"ethics": 0.9}, 0.8, ["ethics"], "test")
    assert r.scores == {"ethics": 0.9}
    assert r.total == 0.8
    assert r.top_factors == ["ethics"]
    assert r.rationale == "test"
    # 新フィールドはデフォルト
    assert r.contributions == {}
    assert r.applied_context == ""
    assert r.applied_policy == ""
    assert r.audit_trail == []


def test_value_result_new_fields():
    """新フィールドを設定して取得できること。"""
    r = value_core.ValueResult(
        scores={"ethics": 0.9},
        total=0.8,
        top_factors=["ethics"],
        rationale="test",
        contributions={"ethics": 0.855},
        applied_context="medical",
        applied_policy="strict",
        audit_trail=[{"action": "policy_floor", "key": "ethics"}],
    )
    assert r.contributions == {"ethics": 0.855}
    assert r.applied_context == "medical"
    assert r.applied_policy == "strict"
    assert len(r.audit_trail) == 1


# ============
# CONTEXT_PROFILES
# ============
def test_context_profiles_are_valid():
    """CONTEXT_PROFILES の全値が 0..1 であること。"""
    for domain, profile in value_core.CONTEXT_PROFILES.items():
        assert isinstance(domain, str)
        for k, v in profile.items():
            assert 0.0 <= v <= 1.0, f"{domain}.{k}={v}"


# ============
# POLICY_PRESETS
# ============
def test_policy_presets_are_valid():
    """POLICY_PRESETS の全値が 0..1 であること。"""
    for name, floors in value_core.POLICY_PRESETS.items():
        assert isinstance(name, str)
        for k, v in floors.items():
            assert 0.0 <= v <= 1.0, f"{name}.{k}={v}"


# ============
# evaluate: context-aware (domain)
# ============
def test_evaluate_with_domain_medical_boosts_weights(monkeypatch):
    """domain=medical で harm_avoid/truthfulness の重みが引き上げられること。"""
    dummy = _DummyProfileNoSave()
    monkeypatch.setattr(
        value_core.ValueProfile,
        "load",
        classmethod(lambda cls: dummy),
    )

    res = value_core.evaluate("テスト", {"domain": "medical", "no_learn_values": True})
    assert res.applied_context == "medical"
    assert "[domain=medical]" in res.rationale
    # audit_trail にコンテキスト重み変更が含まれるかどうか
    assert isinstance(res.audit_trail, list)


def test_evaluate_with_unknown_domain_ignored(monkeypatch):
    """未知の domain が無視されること。"""
    dummy = _DummyProfileNoSave()
    monkeypatch.setattr(
        value_core.ValueProfile,
        "load",
        classmethod(lambda cls: dummy),
    )

    res = value_core.evaluate("テスト", {"domain": "unknown_domain", "no_learn_values": True})
    assert res.applied_context == ""
    assert "[domain=" not in res.rationale


def test_evaluate_domain_safety_raises_harm_avoid_weight(monkeypatch):
    """domain=safety で harm_avoid 重みが profile 値に引き上げられること。"""
    # harm_avoid の DEFAULT_WEIGHTS = 0.95, CONTEXT_PROFILES["safety"]["harm_avoid"] = 1.0
    dummy = _DummyProfileNoSave()
    monkeypatch.setattr(
        value_core.ValueProfile,
        "load",
        classmethod(lambda cls: dummy),
    )

    res = value_core.evaluate("テスト", {"domain": "safety", "no_learn_values": True})
    assert res.applied_context == "safety"
    # audit_trail に harm_avoid の引き上げ記録があること
    context_entries = [e for e in res.audit_trail if e["action"] == "context_weight"]
    harm_entries = [e for e in context_entries if e["key"] == "harm_avoid"]
    assert len(harm_entries) == 1
    assert harm_entries[0]["new"] == 1.0


# ============
# evaluate: policy-aware
# ============
def test_evaluate_with_policy_strict_enforces_floors(monkeypatch):
    """policy=strict でネガティブワードによるスコア0が下限まで引き上げられること。"""
    dummy = _DummyProfileNoSave()
    monkeypatch.setattr(
        value_core.ValueProfile,
        "load",
        classmethod(lambda cls: dummy),
    )

    # 犯罪 triggers NEG_WORDS → ethics=0, legality=0, harm_avoid=0
    # But policy=strict should floor them to 0.9, 0.9, 0.9
    res = value_core.evaluate("犯罪について", {"policy": "strict", "no_learn_values": True})
    assert res.applied_policy == "strict"
    assert "[policy=strict]" in res.rationale
    assert res.scores["ethics"] >= 0.9
    assert res.scores["legality"] >= 0.9
    assert res.scores["harm_avoid"] >= 0.9

    # audit_trail に policy_floor が記録されていること
    floor_entries = [e for e in res.audit_trail if e["action"] == "policy_floor"]
    assert len(floor_entries) >= 3  # ethics, legality, harm_avoid


def test_evaluate_with_policy_balanced_no_changes(monkeypatch):
    """policy=balanced は空のフロアなので何も変えないこと。"""
    dummy = _DummyProfileNoSave()
    monkeypatch.setattr(
        value_core.ValueProfile,
        "load",
        classmethod(lambda cls: dummy),
    )

    res = value_core.evaluate("テスト", {"policy": "balanced", "no_learn_values": True})
    assert res.applied_policy == "balanced"
    floor_entries = [e for e in res.audit_trail if e["action"] == "policy_floor"]
    assert len(floor_entries) == 0


def test_evaluate_with_unknown_policy_ignored(monkeypatch):
    """未知の policy が無視されること。"""
    dummy = _DummyProfileNoSave()
    monkeypatch.setattr(
        value_core.ValueProfile,
        "load",
        classmethod(lambda cls: dummy),
    )

    res = value_core.evaluate("テスト", {"policy": "nonexistent", "no_learn_values": True})
    assert res.applied_policy == ""
    assert "[policy=" not in res.rationale


# ============
# evaluate: contributions (explainability)
# ============
def test_evaluate_returns_contributions(monkeypatch):
    """contributions が scores × weights の各因子寄与を持つこと。"""
    dummy = _DummyProfileNoSave()
    monkeypatch.setattr(
        value_core.ValueProfile,
        "load",
        classmethod(lambda cls: dummy),
    )

    res = value_core.evaluate("テスト", {"no_learn_values": True})
    assert isinstance(res.contributions, dict)
    assert len(res.contributions) > 0
    # 各 contribution は score * weight
    for k, c in res.contributions.items():
        assert isinstance(c, float)
        assert 0.0 <= c <= 1.0


def test_evaluate_contributions_sum_to_total(monkeypatch):
    """contributions の平均が total と一致すること。"""
    dummy = _DummyProfileNoSave()
    monkeypatch.setattr(
        value_core.ValueProfile,
        "load",
        classmethod(lambda cls: dummy),
    )

    res = value_core.evaluate("テスト", {"no_learn_values": True})
    avg = sum(res.contributions.values()) / len(res.contributions)
    # total は _clip01(avg) なので、avg <= 1.0 なら total == avg
    if avg <= 1.0:
        assert abs(res.total - avg) < 1e-4
    else:
        assert res.total == 1.0


# ============
# _build_rationale: explainability
# ============
def test_build_rationale_includes_numeric_factors():
    """rationale に数値内訳が含まれること。"""
    r = value_core._build_rationale(
        top=["ethics", "legality", "harm_avoid"],
        contribs={"ethics": 0.9, "legality": 0.85, "harm_avoid": 0.8},
        weights={"ethics": 0.95, "legality": 0.95, "harm_avoid": 0.95},
        scores={"ethics": 0.95, "legality": 0.9, "harm_avoid": 0.85},
        applied_context="",
        applied_policy="",
    )
    assert "主要因子:" in r
    assert "ethics(" in r
    assert "倫理面を重視しました" in r
    assert "法的な安全性を考慮しました" in r


def test_build_rationale_with_context_and_policy():
    """context/policy が rationale に含まれること。"""
    r = value_core._build_rationale(
        top=["efficiency"],
        contribs={"efficiency": 0.5},
        weights={"efficiency": 0.6},
        scores={"efficiency": 0.8},
        applied_context="financial",
        applied_policy="strict",
    )
    assert "[domain=financial]" in r
    assert "[policy=strict]" in r


def test_build_rationale_fallback_when_no_top_match():
    """top に ethics/legality/user_benefit がない場合 fallback メッセージが出ること。"""
    r = value_core._build_rationale(
        top=["efficiency", "autonomy"],
        contribs={"efficiency": 0.5, "autonomy": 0.4},
        weights={"efficiency": 0.6, "autonomy": 0.6},
        scores={"efficiency": 0.8, "autonomy": 0.7},
        applied_context="",
        applied_policy="",
    )
    assert "全体のバランスを見て判断しました" in r


# ============
# evaluate: combined context + policy
# ============
def test_evaluate_combined_domain_and_policy(monkeypatch):
    """domain + policy を同時に指定した場合、両方が適用されること。"""
    dummy = _DummyProfileNoSave()
    monkeypatch.setattr(
        value_core.ValueProfile,
        "load",
        classmethod(lambda cls: dummy),
    )

    res = value_core.evaluate(
        "犯罪について",
        {"domain": "legal", "policy": "strict", "no_learn_values": True},
    )
    assert res.applied_context == "legal"
    assert res.applied_policy == "strict"
    assert "[domain=legal]" in res.rationale
    assert "[policy=strict]" in res.rationale
    # strict policy floors applied
    assert res.scores["ethics"] >= 0.9
    # legal context weight applied
    ctx_entries = [e for e in res.audit_trail if e["action"] == "context_weight"]
    assert any(e["domain"] == "legal" for e in ctx_entries)


# ============
# evaluate: audit_trail structure
# ============
def test_evaluate_audit_trail_structure(monkeypatch):
    """audit_trail エントリの構造が正しいこと。"""
    dummy = _DummyProfileNoSave()
    monkeypatch.setattr(
        value_core.ValueProfile,
        "load",
        classmethod(lambda cls: dummy),
    )

    res = value_core.evaluate(
        "犯罪について",
        {"domain": "safety", "policy": "strict", "no_learn_values": True},
    )
    for entry in res.audit_trail:
        assert "action" in entry
        assert entry["action"] in ("policy_floor", "context_weight")
        assert "key" in entry
        assert "old" in entry
        assert "new" in entry
        assert isinstance(entry["old"], float)
        assert isinstance(entry["new"], float)
