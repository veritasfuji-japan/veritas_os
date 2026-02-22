# Contributing to VERITAS

Thank you for your interest in contributing.

## Repository license model

This repository uses a two-tier licensing strategy:

- Tier1 (Core): proprietary (top-level `LICENSE`)
- Tier2 (Interface assets): open-licensed in selected directories

Please review `README.md` license matrix before contributing.

## Contribution policy by scope

### 1) Core (proprietary)

Directories and files covered only by the top-level proprietary license are not
open for general external contributions.

- Default policy: maintainers-only changes.
- Exceptional external contributions may be accepted only after explicit
  maintainer invitation and signed CLA.

### 2) Interface assets (open-licensed)

Contributions are welcome for interface-oriented directories (for example:
`spec/`, `sdk/`, `cli/`, `policies/examples/`) under the applicable
subdirectory license.

Contributors must use either:
- DCO sign-off (required for normal external PRs), and
- CLA when requested by maintainers for substantial legal/IP reasons.

## DCO (Developer Certificate of Origin)

By contributing, you certify that you have the right to submit your work under
the repository's applicable license terms.

Add this line to each commit message:

`Signed-off-by: Your Name <you@example.com>`

Use Git's `-s` flag:

```bash
git commit -s -m "Your commit message"
```

## CLA policy

Maintainers may request a Contributor License Agreement (CLA), especially for:
- Core-adjacent work
- major feature contributions
- legal/commercially sensitive changes

If a CLA is required, maintainers will provide instructions in the PR.

## Security reporting

Please do not open public issues for sensitive vulnerabilities.
Follow `SECURITY.md` for responsible disclosure.
