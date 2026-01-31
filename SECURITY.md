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
