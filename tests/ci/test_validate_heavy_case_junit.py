"""Fail-closed synthetic contract for later heavy-case execution/JUnit evidence.

The fixture simulates artifacts; it does not claim live parallel pytest runs.
"""

import json
import shutil
from xml.etree import ElementTree as ET

import pytest

from scripts.ci.collect_heavy_cases import make_collection_proof
from scripts.ci.partition_heavy_pytest_cases import HEAVY_MODULES
from scripts.ci.validate_heavy_case_junit import (
    junit_identity,
    verify_heavy_execution,
)

SOURCE_SHA = "a" * 40
ARTIFACT_PREFIX = "heavy-case-execution-shard-"


def _test_ids():
    return [
        f"{HEAVY_MODULES[0]}::test_case_{n:03d}[param-{n}]"
        for n in range(89)
    ] + [
        f"{HEAVY_MODULES[1]}::test_case_{n:03d}[param-{n}]"
        for n in range(76)
    ]


def _setup(tmp_path):
    cases = _test_ids()
    proof = make_collection_proof(cases, source_sha=SOURCE_SHA)
    proof_file = tmp_path / "collection.json"
    proof_file.write_text(json.dumps(proof), encoding="utf-8")
    root = tmp_path / "shards"
    root.mkdir()
    for plan in proof["manifests"]:
        index = plan["shard_index"]
        folder = root / f"{ARTIFACT_PREFIX}{index}"
        folder.mkdir()
        selected = plan["selected_nodeids"]
        outcomes = {n: "skipped" if n == cases[0] else "passed" for n in selected}
        manifest = {
            "schema_version": 1,
            "proof_kind": "PYTEST_EXECUTION_EVIDENCE",
            "source_sha": SOURCE_SHA,
            "shard_index": index,
            "shard_count": 8,
            "universe_sha256": plan["universe_sha256"],
            "selected_nodeids": list(selected),
            "reported_nodeids": list(reversed(selected)),
            "terminal_outcomes": outcomes,
        }
        (folder / "execution-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        tree = ET.Element("testsuites")
        suite = ET.SubElement(tree, "testsuite")
        for nodeid in reversed(selected):
            classname, name = junit_identity(nodeid)
            case = ET.SubElement(suite, "testcase", {
                "classname": classname, "name": name, "time": "0.2",
            })
            if outcomes[nodeid] == "skipped":
                ET.SubElement(case, "skipped")
        ET.ElementTree(tree).write(folder / "pytest.xml", encoding="utf-8")
    return proof_file, root


def _manifest(root, index=1):
    path = root / f"{ARTIFACT_PREFIX}{index}" / "execution-manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return path, data


def _junit(root, index=1):
    path = root / f"{ARTIFACT_PREFIX}{index}" / "pytest.xml"
    tree = ET.parse(path)
    return path, tree


def _check(proof_file, root):
    return verify_heavy_execution(proof_file, root, expected_sha=SOURCE_SHA)


def test_accepts_exact_full_eight_way_junit_reconciliation(tmp_path):
    collection, root = _setup(tmp_path)
    assert _check(collection, root) == (164, 1)


def test_junit_identity_uses_real_pytest_style_path_and_param_name():
    nodeid = f"{HEAVY_MODULES[0]}::test_example[param-0]"
    assert junit_identity(nodeid) == (
        HEAVY_MODULES[0].removesuffix(".py").replace("/", "."),
        "test_example[param-0]",
    )


@pytest.mark.parametrize("change,pattern", [
    ("missing_reported", "missing/foreign"),
    ("duplicate_reported", "empty/duplicate"),
    ("foreign_selected", "missing/foreign"),
    ("wrong_outcome", "invalid/missing terminal"),
    ("missing_outcome", "invalid/missing terminal"),
    ("wrong_sha", "wrong exact-checkout"),
    ("wrong_index", "wrong exact-checkout"),
    ("wrong_digest", "wrong exact-checkout"),
])
def test_rejects_bad_shard_manifest(tmp_path, change, pattern):
    proof, root = _setup(tmp_path)
    path, data = _manifest(root)
    if change == "missing_reported":
        data["reported_nodeids"].pop()
    elif change == "duplicate_reported":
        data["reported_nodeids"].append(data["reported_nodeids"][0])
    elif change == "foreign_selected":
        data["selected_nodeids"][0] = "tests/foreign.py::test_case"
    elif change == "wrong_outcome":
        first = next(iter(data["terminal_outcomes"]))
        data["terminal_outcomes"][first] = "failed"
    elif change == "missing_outcome":
        data["terminal_outcomes"].pop(next(iter(data["terminal_outcomes"])))
    elif change == "wrong_sha":
        data["source_sha"] = "b" * 40
    elif change == "wrong_index":
        data["shard_index"] = 3
    elif change == "wrong_digest":
        data["universe_sha256"] = "0" * 64
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match=pattern):
        _check(proof, root)


@pytest.mark.parametrize("change,pattern", [
    ("missing_case", "JUnit testcase ID/outcome mismatch"),
    ("duplicate_case", "duplicate JUnit"),
    ("foreign_case", "JUnit testcase ID/outcome mismatch"),
    ("skipped_mismatch", "JUnit testcase ID/outcome mismatch"),
    ("failure", "failing or errored"),
    ("error", "failing or errored"),
    ("negative_time", "invalid JUnit duration"),
    ("nan_time", "invalid JUnit duration"),
    ("unknown_root", "unexpected JUnit root"),
    ("malformed", "malformed JUnit"),
])
def test_rejects_junit_falsification(tmp_path, change, pattern):
    proof, root = _setup(tmp_path)
    path, tree = _junit(root)
    suite = tree.getroot().find(".//testsuite")
    case = suite.findall("testcase")[0]
    if change == "missing_case":
        suite.remove(case)
    elif change == "duplicate_case":
        import copy
        suite.append(copy.deepcopy(case))
    elif change == "foreign_case":
        case.set("name", "test_unaudited")
    elif change == "skipped_mismatch":
        if case.find("skipped") is not None:
            case.remove(case.find("skipped"))
        else:
            ET.SubElement(case, "skipped")
    elif change in {"failure", "error"}:
        ET.SubElement(case, change)
    elif change == "negative_time":
        case.set("time", "-0.1")
    elif change == "nan_time":
        case.set("time", "nan")
    elif change == "unknown_root":
        tree._setroot(ET.Element("not-junit"))
    elif change == "malformed":
        path.write_text("<testsuites>", encoding="utf-8")
    if change != "malformed":
        tree.write(path, encoding="utf-8")
    with pytest.raises(ValueError, match=pattern):
        _check(proof, root)


def test_rejects_missing_or_extra_shard_directory(tmp_path):
    proof, root = _setup(tmp_path)
    shutil.rmtree(root / f"{ARTIFACT_PREFIX}8")
    with pytest.raises(ValueError, match="missing, extra"):
        _check(proof, root)


def test_rejects_altered_collection_proof(tmp_path):
    proof, root = _setup(tmp_path)
    data = json.loads(proof.read_text(encoding="utf-8"))
    data["source_sha"] = "b" * 40
    proof.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="exact checkout"):
        _check(proof, root)
