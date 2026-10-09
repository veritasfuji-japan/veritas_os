"""Validate immutable slow-suite timing evidence before shard design."""

from pathlib import Path

import pytest

from scripts.ci.validate_pytest_slow_junit import validate_junit


def _write(tmp_path: Path, xml: str) -> Path:
    path = tmp_path / "slow.xml"
    path.write_text(xml, encoding="utf-8")
    return path


def test_slow_junit_accepts_executed_tests_with_skips(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        '<testsuites><testsuite tests="3" skipped="1" errors="0" failures="0">'
        '<testcase classname="tests.one" name="ok1" time="1.125"/>'
        '<testcase classname="tests.one" name="ok2" time="0.250"/>'
        '<testcase classname="tests.two" name="skip" time="0.0">'
        '<skipped message="optional dependency"/></testcase>'
        "</testsuite></testsuites>",
    )
    assert validate_junit(path) == (2, 1, 1.375)


@pytest.mark.parametrize(
    ("xml", "error"),
    [
        ("<testsuites/>", "no testcases"),
        (
            '<testsuite><testcase name="only_skip" time="0">'
            "<skipped/></testcase></testsuite>",
            "no executed",
        ),
        (
            '<testsuite><testcase name="bad" time="0">'
            "<failure/></testcase></testsuite>",
            "failing or errored",
        ),
        (
            '<testsuite><testcase name="error" time="0">'
            "<error/></testcase></testsuite>",
            "failing or errored",
        ),
        ('<testsuite><testcase name="bad" time="-1"/></testsuite>', "negative"),
        ('<testsuite><testcase name="bad" time="nan"/></testsuite>', "non-finite"),
        ('<testsuite><testcase name="bad" time="inf"/></testsuite>', "non-finite"),
        ('<testsuite><testcase name="bad" time="oops"/></testsuite>', "invalid duration"),
        ('<testsuite><testcase name="bad"/></testsuite>', "non-finite"),
        ("<invalid/>", "unsupported JUnit root"),
    ],
)
def test_slow_junit_rejects_untrustworthy_evidence(
    tmp_path: Path, xml: str, error: str
) -> None:
    with pytest.raises(ValueError, match=error):
        validate_junit(_write(tmp_path, xml))


def test_slow_junit_rejects_missing_and_malformed_file(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unreadable"):
        validate_junit(tmp_path / "missing.xml")
    with pytest.raises(ValueError, match="unreadable"):
        validate_junit(_write(tmp_path, "<testsuite>"))
