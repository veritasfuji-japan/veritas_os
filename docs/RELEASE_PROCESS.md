# VERITAS OS — Release Process

## Overview

This document describes the release process for VERITAS OS, including how the
tiered CI/release validation model ensures governance readiness before a release
is promoted.

## Release Versioning

VERITAS OS uses semantic versioning: `vMAJOR.MINOR.PATCH` (e.g. `v2.1.0`).

- **Patch releases** (`v2.0.1`) — bug fixes, security patches, minor documentation updates
- **Minor releases** (`v2.1.0`) — new features, non-breaking API additions
- **Major releases** (`v3.0.0`) — breaking changes, major architecture changes

Pre-release tags: `v2.1.0-rc.1`, `v2.1.0-beta.1` also trigger the release gate.
Additionally, release preparation branches (`release/*`, `rc/*`) trigger the same
gate so maintainers can catch TrustLog production issues before tagging.

## How to Release

### 1. Ensure main branch CI passes

All Tier 1 checks must be green on the commit you intend to release:

```bash
# Verify main is green
gh run list --workflow=main.yml --branch=main --limit=3
```

### 2. Create and push a version tag

```bash
# Create annotated tag
git tag -a v2.1.0 -m "Release v2.1.0"

# Push tag — this automatically triggers release-gate.yml
git push origin v2.1.0
```

### 3. Monitor the Release Gate workflow

```bash
# Watch the release-gate workflow
gh run watch --workflow=release-gate.yml

# Or view in the Actions tab:
# https://github.com/veritasfuji-japan/veritas_os/actions/workflows/release-gate.yml
```

The release gate runs three parallel groups:

1. **Tier 1** (`governance-smoke` + `security-checks`) — fast, ~3-5 min
2. **Tier 2** (`trustlog-production-matrix` + `production-tests` + `docker-smoke` + `governance-report`) — ~10-15 min
3. **Final** (`release-readiness`) — 1 min summary gate

### TrustLog gating policy

`trustlog-production-matrix` enforces staged validation:

- `dev` profile: advisory on non-release refs, required on `release/*`, `rc/*`, `v*`
- `secure` profile: always required
- `prod` profile: always required

The matrix must pass before promotion because it covers:
KMS signer, S3 Object Lock mirror, unified verification, startup posture,
hard-fail semantics, and legacy verification compatibility.

### 4. Verify governance readiness

Once the workflow completes:

```bash
# Download the governance readiness report
gh run download --name release-governance-readiness-report \
  --workflow=release-gate.yml

# View the text summary
cat governance-readiness-report.txt

# Check the JSON summary
python3 -c "
import json
report = json.load(open('governance-readiness-report.json'))
print('Governance ready:', report['summary']['governance_ready'])
print('Blocking failures:', report['summary']['blocking_failures'])
"
```

A release is **governance-ready** when:

| Check | Where | Must be |
|-------|-------|---------|
| `release-readiness` job result | Release Gate workflow | `success` |
| `governance_ready` field | `governance-readiness-report.json` | `true` |
| `blocking_failures` count | `governance-readiness-report.json` | `0` |
| All Tier 1 jobs | Release Gate workflow | `success` |
| All Tier 2 jobs | Release Gate workflow | `success` |

### 5. Publish the release

Once the release gate passes, publish the GitHub release:

```bash
gh release create v2.1.0 \
  --title "v2.1.0" \
  --notes-file CHANGELOG.md \
  --draft
```

Attach the governance readiness report as a release asset:

```bash
gh release upload v2.1.0 governance-readiness-report.json
gh release upload v2.1.0 governance-readiness-report.txt
```

Publish when ready:

```bash
gh release edit v2.1.0 --draft=false
```

## Release Gate Failure: What To Do

If the release gate fails:

1. Look at the failing job(s) in the Actions tab
2. Download logs: `gh run view --log`
3. Fix the issue on `main`
4. Delete and re-create the tag:
   ```bash
   git tag -d v2.1.0
   git push --delete origin v2.1.0
   # fix the issue, push to main, then re-tag
   git tag -a v2.1.0 -m "Release v2.1.0"
   git push origin v2.1.0
   ```

**Do not** publish a GitHub release if the release-gate workflow failed.

## Manual Release Gate Trigger

To run the release gate manually against any branch or tag:

```bash
gh workflow run release-gate.yml --ref main
# With Tier 3 external tests:
gh workflow run release-gate.yml --ref v2.1.0 -f tier3_external=true
```

## CI Tier Summary

| What | Workflow | When | Blocks |
|------|----------|------|--------|
| Lint + security scripts + smoke | `main.yml` | Every PR | ✅ PR merge |
| Dependency CVE scan | `main.yml` | Every PR | ✅ PR merge |
| Unit tests (85% coverage) | `main.yml` | Every PR | ✅ PR merge |
| Frontend lint/test/E2E | `main.yml` | Every PR | ✅ PR merge |
| Production tests + Docker smoke | `release-gate.yml` | `v*` tag push | ✅ Release |
| TrustLog production matrix (`dev`/`secure`/`prod`) | `release-gate.yml` | `release/*`, `rc/*`, `v*` | ✅ Release candidate / release |
| Governance readiness report | `release-gate.yml` | `v*` tag push | ✅ Release |
| External/live tests | `release-gate.yml` | Manual only | ⚠️ Advisory |
| Long-running production validation | `production-validation.yml` | Weekly + manual | Advisory |
| SBOM generation | `sbom-nightly.yml` | Nightly | Advisory |
| CodeQL analysis | `codeql.yml` | PR + weekly | Advisory (Security tab) |
| Docker image publish | `publish-ghcr.yml` | Push to `main` | Advisory |

## Hotfix Process

For urgent security patches:

1. Create a fix branch from the affected tag
2. Apply and test the fix
3. Tag the hotfix release (`v2.0.1`)
4. The release gate runs automatically — do not skip it even for hotfixes
5. If Docker smoke is too slow for a critical hotfix, use `workflow_dispatch`
   with only the `governance-smoke` and `security-checks` jobs (Tier 1 minimum)

**Security note**: Never publish a release without the release gate passing.
The release gate is the enforcement mechanism for the VERITAS OS governance posture.
