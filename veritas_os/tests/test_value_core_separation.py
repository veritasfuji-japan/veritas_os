import json

from veritas_os.core import value_core


def test_default_separation():
    assert "ethics" in value_core.DEFAULT_NORMATIVE_WEIGHTS
    assert "legality" in value_core.DEFAULT_NORMATIVE_WEIGHTS
    assert "最小ステップで前進する" not in value_core.DEFAULT_NORMATIVE_WEIGHTS
    assert "mvpコードを進める" not in value_core.DEFAULT_NORMATIVE_WEIGHTS
    assert "サウナ控め" not in value_core.DEFAULT_NORMATIVE_WEIGHTS
    assert "minimal_steps" in value_core.DEFAULT_OPERATIONAL_PREFERENCES


def test_legacy_split_mapping():
    split = value_core._split_value_settings({
        "ethics": 0.9,
        "最小ステップで前進する": 0.6,
        "サウナ控め": 0.3,
    })
    assert split["normative_weights"]["ethics"] == 0.9
    assert split["operational_preferences"]["minimal_steps"] == 0.6
    assert split["personal_preferences"]["sauna_less"] == 0.3
    assert "サウナ控め" not in split["normative_weights"]


def test_save_format_v2(tmp_path, monkeypatch):
    monkeypatch.setattr(value_core, "CFG_DIR", tmp_path)
    monkeypatch.setattr(value_core, "CFG_PATH", tmp_path / "value_core.json")
    prof = value_core.ValueProfile.load()
    prof.save()
    data = json.loads((tmp_path / "value_core.json").read_text(encoding="utf-8"))
    assert data["schema_version"] == "value_core.v2"
    assert "normative_weights" in data
    assert "operational_preferences" in data
    assert "personal_preferences" in data
    assert "weights" not in data


def test_evaluate_excludes_operational_personal(monkeypatch):
    class _Dummy:
        def __init__(self):
            self.normative_weights = value_core.DEFAULT_NORMATIVE_WEIGHTS.copy()
            self.operational_preferences = value_core.DEFAULT_OPERATIONAL_PREFERENCES.copy()
            self.personal_preferences = {}

        def update_from_scores(self, scores, lr=0.02):
            return None

    dummy = _Dummy()
    monkeypatch.setattr(value_core.ValueProfile, "load", classmethod(lambda cls: dummy))
    res = value_core.evaluate("実装を進める", {
        "no_learn_values": True,
        "value_scores": {"サウナ控め": 1.0, "mvpコードを進める": 1.0},
        "personal_preferences": {"sauna_less": 1.0},
    })
    assert "サウナ控め" not in res.scores
    assert "mvpコードを進める" not in res.scores
    assert "サウナ控め" not in res.top_factors
    assert "サウナ控め" not in res.contributions
    assert "mvpコードを進める" not in res.contributions


def test_update_from_scores_normative_only(tmp_path, monkeypatch):
    monkeypatch.setattr(value_core, "CFG_DIR", tmp_path)
    monkeypatch.setattr(value_core, "CFG_PATH", tmp_path / "value_core.json")
    prof = value_core.ValueProfile.load()
    prof.update_from_scores({"ethics": 0.2, "サウナ控め": 1.0}, lr=0.5)
    assert "サウナ控め" not in prof.normative_weights


def test_update_weights_backward_compatible(monkeypatch):
    class _Dummy:
        def __init__(self):
            self.normative_weights = value_core.DEFAULT_NORMATIVE_WEIGHTS.copy()
            self.operational_preferences = value_core.DEFAULT_OPERATIONAL_PREFERENCES.copy()
            self.personal_preferences = {}

        @property
        def weights(self):
            return {
                **self.normative_weights,
                **self.operational_preferences,
                **self.personal_preferences,
            }

        def save(self):
            return None

    dummy = _Dummy()
    monkeypatch.setattr(value_core.ValueProfile, "load", classmethod(lambda cls: dummy))
    merged = value_core.update_weights({"ethics": 0.8, "最小ステップで前進する": 0.7})
    assert dummy.normative_weights["ethics"] == 0.8
    assert dummy.operational_preferences["minimal_steps"] == 0.7
    assert "ethics" in merged


def test_legacy_profile_weights_only_still_works(monkeypatch):
    class _LegacyOnly:
        def __init__(self):
            self.weights = value_core.DEFAULT_WEIGHTS.copy()

        def update_from_scores(self, scores, lr=0.02):
            return None

    legacy = _LegacyOnly()
    monkeypatch.setattr(value_core.ValueProfile, "load", classmethod(lambda cls: legacy))
    result = value_core.evaluate("テスト", {"no_learn_values": True})
    assert 0.0 <= result.total <= 1.0


def test_update_weights_partial_update_preserves_values(tmp_path, monkeypatch):
    monkeypatch.setattr(value_core, "CFG_DIR", tmp_path)
    monkeypatch.setattr(value_core, "CFG_PATH", tmp_path / "value_core.json")
    profile = value_core.ValueProfile.load()
    profile.normative_weights["truthfulness"] = 0.11
    profile.save()
    value_core.update_weights({"ethics": 0.8})
    loaded = value_core.ValueProfile.load()
    assert loaded.normative_weights["ethics"] == 0.8
    assert loaded.normative_weights["truthfulness"] == 0.11


def test_default_weights_include_legacy_japanese_keys():
    assert "最小ステップで前進する" in value_core.DEFAULT_WEIGHTS
    assert "mvpコードを進める" in value_core.DEFAULT_WEIGHTS
    assert "サウナ控め" in value_core.DEFAULT_WEIGHTS
    assert "最小ステップで前進する" not in value_core.DEFAULT_NORMATIVE_WEIGHTS


def test_v2_personal_preferences_preserved(tmp_path, monkeypatch):
    monkeypatch.setattr(value_core, "CFG_DIR", tmp_path)
    monkeypatch.setattr(value_core, "CFG_PATH", tmp_path / "value_core.json")
    profile = value_core.ValueProfile(
        normative_weights=value_core.DEFAULT_NORMATIVE_WEIGHTS.copy(),
        operational_preferences=value_core.DEFAULT_OPERATIONAL_PREFERENCES.copy(),
        personal_preferences={"sauna_less": 0.3},
    )
    profile.save()
    loaded = value_core.ValueProfile.load()
    assert loaded.personal_preferences["sauna_less"] == 0.3
