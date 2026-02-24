# Security Policy

Thank you for helping keep VERITAS OS and its users safe.

## Supported Versions

This project is currently in active development.
Security fixes are provided for the latest version on the `main` branch.

| Version / Branch | Supported |
| --- | --- |
| `main` | ✅ |
| tags / releases | ⛔ (not maintained yet) |

## Reporting a Vulnerability

Please report security issues **privately**.

### Preferred: GitHub Private Vulnerability Reporting
Use GitHub's "Report a vulnerability" feature on the repository.

### Alternative: Email
If GitHub reporting is not available, email:　veritas.fuji@gmail.com

### What to include
- A clear description of the issue and impact
- Steps to reproduce / proof-of-concept (safe and minimal)
- Affected component/path and environment details
- Any suggested fix or mitigation (optional)

### Response expectations
- **Initial response:** within **7 days**
- **Status updates:** every **14 days** until resolution (or a clear decision)

### Coordinated disclosure
Please allow reasonable time to investigate and patch before public disclosure.
If the report is accepted, we will coordinate an advisory and a fix release.
If declined, we will explain why (e.g., not a security issue, out of scope, or cannot reproduce).

## Scope

### In scope
- Vulnerabilities in VERITAS OS source code in this repository
- Dependency vulnerabilities that affect runtime security

### Out of scope
- DoS from extremely large inputs without a practical exploit path
- Issues requiring compromised credentials or malicious admins
- Reports lacking reproducible details


## Automated Security Gates

The repository enforces automated gates to reduce the risk of introducing known vulnerabilities, secret leaks, and unsafe dependency drift.

### CI required checks
- **Dependency audit (Python):** `pip-audit -r veritas_os/requirements.txt`
- **Dependency audit (Node):** `pnpm audit --audit-level=high`
- **Secret scan:** `gitleaks` on every `push` and `pull_request`

These checks are configured as GitHub Actions workflows and should be treated as required status checks for merges into `main`.

### Developer local checks (pre-commit)
Install and enable local hooks:

```bash
python -m pip install pre-commit
pre-commit install
```

The repository uses pre-commit to run `gitleaks` before commits so secrets are blocked as early as possible.

### Nightly SBOM generation and drift monitoring
A nightly workflow generates CycloneDX SBOM files for Python and Node dependencies and compares their SHA256 hashes against baseline hashes stored under `security/sbom/baseline/`.

- Generated files:
  - `security/sbom/python.cdx.json`
  - `security/sbom/node.cdx.json`
- Drift indicators:
  - `security/sbom/python.cdx.sha256`
  - `security/sbom/node.cdx.sha256`

If hash drift is detected, the workflow emits warnings and uploads artifacts for review.

> **Security warning:** Without these automated gates, known vulnerable packages and accidental secret exposures can bypass manual review and reach production.
