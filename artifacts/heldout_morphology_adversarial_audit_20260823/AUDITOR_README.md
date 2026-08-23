# External Auditor Entry Point

This directory is a self-contained report/evidence package for the 2026-08-23
MetroFlow seed-held-out morphology audit. Start with `REPORT.md` or `metroflow-heldout-morphology-adversarial-audit-20260823.pdf`.

MetroFlow is **single-developer personal research code**. "Adversarial" means
**skeptical scientific and code review**, not a hostile-operator threat model.
Hashes and manifests are reproducibility and accidental-corruption receipts;
this package makes **no security or tamper-resistance claim**.

## Fast verification

From repository root:

```bash
.venv/bin/python tools/build_heldout_morphology_adversarial_report.py --check
.venv/bin/python -m pytest tests/test_heldout_morphology_adversarial_report.py -q
sha256sum artifacts/heldout_morphology_adversarial_audit_20260823/evidence/*
pdfinfo artifacts/heldout_morphology_adversarial_audit_20260823/metroflow-heldout-morphology-adversarial-audit-20260823.pdf
pdftotext artifacts/heldout_morphology_adversarial_audit_20260823/metroflow-heldout-morphology-adversarial-audit-20260823.pdf - | grep -E '15/18|MF-043|runtime-default'
```

To reproduce the negative scientific result and SVG authorities from an exact
checkout without relying on the author's paths:

```bash
PACKAGE=$PWD/artifacts/heldout_morphology_adversarial_audit_20260823
python "$PACKAGE/evidence/heldout_morphology_reproducer.py" \
  --repository /path/to/checkout-at-e1979df \
  --package-dir "$PACKAGE" --check-validation
python "$PACKAGE/evidence/heldout_morphology_reproducer.py" \
  --repository /path/to/checkout-at-e1979df \
  --package-dir "$PACKAGE" --check-samples
```

A successful reproduction command reports `scientific verdict=FAIL` and exits
zero. The FAIL is the frozen experimental outcome, not a reproduction error.

PDF rebuilding requires the pinned report-only packages and does not touch the
repository runtime environment:

```bash
python3.12 -m venv /tmp/metroflow-report-pdf-venv
/tmp/metroflow-report-pdf-venv/bin/pip install \
  reportlab==5.0.1 pillow==12.3.0 pypdf==6.16.1 pdfplumber==0.11.10
/tmp/metroflow-report-pdf-venv/bin/python \
  tools/build_heldout_morphology_adversarial_report.py --build
```

The PDF builder uses ReportLab invariant mode. Rebuilds with the pinned stack
must be byte-identical. `--build` consumes frozen JSON/maps; it does not generate
a city, change a threshold, fetch OSM, or execute traffic.

## Evidence roles

- `EVIDENCE_MANIFEST.json`: hashes and byte sizes for every package file except itself.
- `evidence/heldout_morphology_results.json`: complete 18-case authority.
- `evidence/heldout_morphology_validator.py`: byte-frozen original measurement definition; its historical author paths are not the portable entry point.
- `evidence/heldout_morphology_reproducer.py`: explicit-checkout/package, read-only portable entry point that preserves the frozen validator hash.
- `evidence/sample_manifest.json`: six map source/fingerprint/file bindings.
- `FAILURE_INVENTORY.json`: exact MF-001..MF-043 machine inventory.
- `CLAIM_EVIDENCE_LEDGER.md`: allowed and forbidden inferences.
- `maps/*.svg`: vector authorities; `maps/*.png`: digest-bound previews.

## Non-negotiable interpretation

The result is FAIL at 15/18 because grid_core failed all three held-out seeds.
This is seed-held-out structural morphology, NOT fresh-OSM empirical validation.
Traffic-functional validation was not completed, traffic algorithms remain a
research target, and runtime-default promotion remains blocked.
