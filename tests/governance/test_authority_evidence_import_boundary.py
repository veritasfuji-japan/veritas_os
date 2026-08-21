"""Regression tests for the optional AuthorityEvidence crypto backend."""

from __future__ import annotations

import subprocess
import sys


def test_core_authority_import_does_not_require_cryptography() -> None:
    """Core governance imports must succeed when crypto imports are blocked."""
    script = """
import builtins
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name == 'cryptography' or name.startswith('cryptography.'):
        raise ModuleNotFoundError(name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
import veritas_os.governance.authority_evidence
print('ok')
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
