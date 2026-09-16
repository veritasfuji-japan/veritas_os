# SBOM Baseline

This directory stores baseline SHA256 hashes used by the nightly SBOM drift monitor.

## Expected baseline files
- `baseline/python.cdx.sha256`
- `baseline/node.cdx.sha256`

The nightly workflow generates **reproducible** CycloneDX output before hashing it.
This is required because normal CycloneDX output can include time- or random-based
values such as timestamps and serial numbers, which would make raw-file hashes drift
even when dependency inputs did not change.

The workflow pins its SBOM generators so a tooling upgrade does not silently change
the generated document shape:

- `cyclonedx-bom==7.3.1`
- `@cyclonedx/cyclonedx-npm@6.0.1`

To reproduce the same baseline inputs locally, use the same tool versions and
`--output-reproducible` option as the workflow, then generate hashes:

```bash
python -m pip install cyclonedx-bom==7.3.1
cyclonedx-py requirements --output-reproducible veritas_os/requirements.txt \
  --output-file security/sbom/python.cdx.json

pnpm dlx @cyclonedx/cyclonedx-npm@6.0.1 \
  --output-reproducible \
  --output-file security/sbom/node.cdx.json \
  --spec-version 1.5

sha256sum security/sbom/python.cdx.json > security/sbom/baseline/python.cdx.sha256
sha256sum security/sbom/node.cdx.json > security/sbom/baseline/node.cdx.sha256
```

> Update baselines only after verifying dependency changes are intentional and
> the generated SBOM artifacts correspond to the intended source revision.
