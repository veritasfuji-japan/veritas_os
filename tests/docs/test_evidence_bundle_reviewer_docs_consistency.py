from scripts.quality import check_evidence_bundle_reviewer_docs as checker


def test_collect_missing_links_reports_each_missing_link(tmp_path, monkeypatch):
    source = tmp_path / "technical-proof-pack.md"
    source.write_text(
        "See evidence-bundle-reviewer-checklist.md only.", encoding="utf-8"
    )
    monkeypatch.setattr(checker, "REPO_ROOT", tmp_path)

    problems = checker.collect_missing_links(
        {source: source.read_text(encoding="utf-8")},
        (source,),
        (
            "evidence-bundle-reviewer-checklist.md",
            "evidence-bundle-signature-verification.md",
        ),
    )

    assert problems == [
        "technical-proof-pack.md: missing link: "
        "evidence-bundle-signature-verification.md"
    ]


def test_boundary_phrase_check_normalizes_case_and_wrapped_lines(
    tmp_path, monkeypatch
):
    source = tmp_path / "third-party-review-readiness.md"
    source.write_text(
        "Trusted public keys must come from an out-of-band\n"
        "reviewer/operator trust channel.",
        encoding="utf-8",
    )
    monkeypatch.setattr(checker, "REPO_ROOT", tmp_path)

    problems = checker.collect_missing_boundary_phrases(
        {source: source.read_text(encoding="utf-8")},
        (source,),
        (
            "trusted public keys must come from an out-of-band "
            "reviewer/operator trust channel",
        ),
    )

    assert problems == []


def test_readme_entrypoint_fails_when_no_readme_links_to_verification_docs(
    tmp_path, monkeypatch
):
    readme = tmp_path / "README.md"
    docs_readme = tmp_path / "docs/en/README.md"
    docs_readme.parent.mkdir(parents=True)
    readme.write_text("No reviewer docs here.", encoding="utf-8")
    docs_readme.write_text("No reviewer docs here either.", encoding="utf-8")
    monkeypatch.setattr(checker, "REPO_ROOT", tmp_path)

    problems = checker.collect_missing_readme_entrypoint(
        {
            readme: readme.read_text(encoding="utf-8"),
            docs_readme: docs_readme.read_text(encoding="utf-8"),
        },
        (readme, docs_readme),
        ("evidence-bundle-signature-verification.md",),
    )

    assert problems == [
        "README.md, docs/en/README.md: missing reachable Evidence Bundle "
        "verification docs link (expected one of: "
        "evidence-bundle-signature-verification.md)"
    ]


def test_current_evidence_bundle_reviewer_docs_are_consistent():
    assert checker.validate_evidence_bundle_reviewer_docs() == []
