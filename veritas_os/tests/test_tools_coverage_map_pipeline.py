# veritas_os/tests/test_tools_coverage_map_pipeline.py
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import veritas_os.tools.coverage_map_pipeline as m


def _make_fake_pipeline_file(base_dir: Path) -> Path:
    """
    m.TARGET_SUFFIX (= 'veritas_os/core/pipeline.py') で endswith できる
    “それっぽい実ファイルパス” を base_dir 配下に作る。
    """
    p = base_dir / "veritas_os" / "core" / "pipeline.py"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "\n".join(
            [
                "class C:",
                "    def m(self):",
                "        x = 1",
                "        return x",
                "",
                "async def af():",
                "    return 2",
                "",
                "def f():",
                "    y = 3",
                "    return y",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return p


def _make_cov_json(base_dir: Path, target_fp: Path) -> Path:
    """
    coverage.json は一般に絶対パスが入るので、str(target_fp) を使う。
    """
    cov = {
        "files": {
            str(target_fp): {
                "missing_lines": [2, 3, 9],  # 適当でOK（main が集計するだけ）
                "missing_branches": [[10, -1], [11, 0], [12, 13]],
                "executed_branches": [[1, 2]],
            }
        }
    }
    cov_path = base_dir / "coverage.json"
    cov_path.write_text(json.dumps(cov), encoding="utf-8")
    return cov_path


def test_load_cov_and_find_target_file(monkeypatch, tmp_path: Path):
    target_fp = _make_fake_pipeline_file(tmp_path)
    cov_path = _make_cov_json(tmp_path, target_fp)

    monkeypatch.setattr(m, "COV_JSON", cov_path)

    cov = m.load_cov()
    assert isinstance(cov, dict)

    fp = m.find_target_file(cov)
    assert fp.endswith(m.TARGET_SUFFIX)
    assert fp == str(target_fp)


def test_find_target_file_not_found_raises():
    cov = {"files": {"/tmp/something_else.py": {}}}
    with pytest.raises(SystemExit) as e:
        m.find_target_file(cov)
    assert "Target not found" in str(e.value)


def test_index_defs_and_owner_basic():
    src = "\n".join(
        [
            "class A:",
            "    def m1(self):",
            "        return 1",
            "",
            "    async def am(self):",
            "        return 2",
            "",
            "def top():",
            "    return 3",
            "",
        ]
    )
    tree = ast.parse(src)
    defs = m.index_defs(tree)

    # 関数が拾えている（class.method 形式になる）
    names = [d[0] for d in defs]
    assert "A.m1" in names
    assert "A.am" in names
    assert "top" in names

    # owner の分岐（範囲内ならその名前、外なら module-level）
    assert m.owner(defs, 2) == "A.m1"         # line2 は m1 定義行＝m1 の中
    assert m.owner(defs, 8) == "top"          # line8 は top 定義行
    assert m.owner(defs, 999) == "<module-level>"


def test_main_smoke_prints_summary(monkeypatch, tmp_path: Path, capsys):
    target_fp = _make_fake_pipeline_file(tmp_path)
    cov_path = _make_cov_json(tmp_path, target_fp)

    # COV_JSON を tmp の coverage.json に差し替え
    monkeypatch.setattr(m, "COV_JSON", cov_path)

    # main 実行
    m.main()
    out = capsys.readouterr().out

    # 主要出力が出ていることを確認
    assert f"[pipeline] file={str(target_fp)}" in out
    assert "[pipeline] missing_lines=" in out
    assert "missing_branches=" in out

    # missing exit arcs の分岐も踏めている（to=-1/0）
    assert "[missing exit arcs]" in out
    assert ("-> -1" in out) or ("-> 0" in out)


def test___main___entrypoint_executes_isolated(tmp_path: Path):
    """
    coverage_map_pipeline.py の
      if __name__ == "__main__": main()
    を “実際にスクリプトとして実行” して踏む。

    重要:
      - 実repo直下に coverage.json を置かない（= repo汚染しない）
      - tmp 配下に “ミニプロジェクト” を作って `python -m ...` する
      - coverage_map_pipeline.py の ROOT は __file__.parents[2] なので、
        tmp_proj/veritas_os/tools/coverage_map_pipeline.py を用意すると ROOT=tmp_proj になる
    """
    tmp_proj = tmp_path / "proj"
    pkg_tools = tmp_proj / "veritas_os" / "tools"
    pkg_core = tmp_proj / "veritas_os" / "core"
    pkg_tools.mkdir(parents=True, exist_ok=True)
    pkg_core.mkdir(parents=True, exist_ok=True)

    # package 化
    (tmp_proj / "veritas_os" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_proj / "veritas_os" / "tools" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_proj / "veritas_os" / "core" / "__init__.py").write_text("", encoding="utf-8")

    # 対象モジュールを tmp 側へコピー（依存を持たせない）
    module_file = Path(m.__file__).resolve()
    (pkg_tools / "coverage_map_pipeline.py").write_text(
        module_file.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    # tmp_proj 配下に fake pipeline と coverage.json を作る（ROOT=tmp_proj になる）
    target_fp = _make_fake_pipeline_file(tmp_proj)
    _make_cov_json(tmp_proj, target_fp)

    env = dict(os.environ)
    env["PYTHONPATH"] = str(tmp_proj) + (":" + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")

    r = subprocess.run(
        [sys.executable, "-m", "veritas_os.tools.coverage_map_pipeline"],
        cwd=str(tmp_proj),
        env=env,
        capture_output=True,
        text=True,
    )

    assert r.returncode == 0, r.stderr
    assert "[pipeline]" in r.stdout
    assert "missing_lines=" in r.stdout



