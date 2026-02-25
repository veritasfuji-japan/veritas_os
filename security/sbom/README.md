# SBOM Baseline

This directory stores baseline SHA256 hashes used by the nightly SBOM drift monitor.

## Expected baseline files
- `baseline/python.cdx.sha256`
- `baseline/node.cdx.sha256`

Generate and refresh baseline hashes with:

```bash
sha256sum security/sbom/python.cdx.json > security/sbom/baseline/python.cdx.sha256
sha256sum security/sbom/node.cdx.json > security/sbom/baseline/node.cdx.sha256
```

> Update baselines only after verifying dependency changes are intentional.
