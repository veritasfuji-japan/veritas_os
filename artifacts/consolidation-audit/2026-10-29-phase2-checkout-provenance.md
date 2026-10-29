# Phase 2 generated audit checkout provenance

The Phase 2 generator analyzes the current filesystem. Its historical
`source_main=52752dbf766d9994f2f3267af47e904748d347a6` identifies the original
Phase 2 baseline, not the source analyzed by a new invocation. The September
baseline/report and frozen proof anchor remain historical records.

New generated reports retain that field and format version, and add
`observed_checkout`:

| Field | Meaning |
| --- | --- |
| `tested_sha` | Actual repository `HEAD`, including detached PR merge checkouts |
| `head_tree_sha` | Committed tree referenced by that HEAD; not an index or dirty-worktree digest |
| `worktree_dirty` | Whether Git reports staged, unstaged, deleted or non-ignored untracked files before output is written |

The generator invokes Git at its own repository root, independently of caller
CWD or CI environment metadata. Missing Git, missing/unborn repositories and
repository-root mismatches fail generation instead of substituting the baseline
or an environment-provided SHA. It observes the same metadata again after
scanning and refuses a report if the observations differ.

The workflow additionally compares `tested_sha` with both actual `HEAD` and
`GITHUB_SHA`, compares `head_tree_sha` with `HEAD^{tree}`, and requires the
recorded pre-output worktree state to be clean. On PRs the tested merge SHA may
differ from the PR head SHA. Writing the output creates an untracked file; this
does not retroactively change the recorded pre-output state. A later invocation
with that non-ignored file already present reports a dirty worktree.

Run locally with output outside the checkout to avoid introducing that file:

```bash
python scripts/audit_large_consolidation_phase2.py --output /tmp/phase2-audit.json
```

## Limits

This is Git metadata provenance, not a content attestation or an atomic snapshot.
A dirty report cannot identify all analyzed bytes by its HEAD/tree pair. Git
ignores ignored files for dirtiness, while the existing filesystem scanner can
read ignored files outside its explicit exclusions. Equal observations cannot
detect all concurrent edits, including edits while already dirty, transient
changes or changes to ignored files. Use a controlled, clean checkout for CI;
do not treat these fields as proof of an immutable filesystem or complete
dependency/consumer coverage. The static audit still grants no deletion or
execution authority and does not expand the controlled execution proof.

## Regression evidence

Before this correction, an audit of main `f48d7ff8d34997e853365e20729694e11d221bb2`
reported only historical `source_main` and no observed checkout identity.
Focused regressions use temporary real Git repositories to check detached HEAD,
new commits, local change states, missing identity, a clean-to-dirty transition
during scanning, and the CLI's pre-output observation. Existing historical
baseline and dependency/classification guards remain in place.
