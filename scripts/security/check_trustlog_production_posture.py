#!/usr/bin/env python3
"""Check TrustLog production security posture from environment variables."""

from __future__ import annotations

from os import environ

from veritas_os.security.trustlog_production_posture import _env_true
from veritas_os.security.trustlog_production_posture import check_trustlog_production_posture


def main() -> int:
    """Run the TrustLog production posture checker as a CLI."""
    result = check_trustlog_production_posture(dict(environ))

    if result.passed and not result.warnings:
        print("TrustLog production posture check passed.")
        return 0

    if result.passed and result.warnings:
        print("TrustLog production posture check passed with warnings.")
        print("Warnings:")
        for warning in result.warnings:
            print(f"- {warning}")
        return 0

    print("TrustLog production posture check failed.")
    print("Failures:")
    for failure in result.failures:
        print(f"- {failure}")
    if result.warnings:
        print("Warnings:")
        for warning in result.warnings:
            print(f"- {warning}")
    print("Remediation:")
    print("- Set VERITAS_TRUSTLOG_BACKEND=postgresql")
    print("- Configure VERITAS_DATABASE_URL or DATABASE_URL")
    print("- Configure VERITAS_ENCRYPTION_KEY")
    print("- Set VERITAS_TRUSTLOG_SIGNER_BACKEND=aws_kms")
    print("- Configure VERITAS_TRUSTLOG_KMS_KEY_ID")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
