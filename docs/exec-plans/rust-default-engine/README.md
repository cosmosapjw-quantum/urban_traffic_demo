# Rust Default Engine Compiled Package

This directory is the execution authority for the planned whole-engine Rust migration.

## Status

- Source audited: `main@01c80b432344f94209daaa198bb1eb007839fc7f`
- Source tree: `13ab0dd317d2581b83aba2d8b7763ef644dd30fb`
- Current implementation readiness: `BLOCKED_BY_PREDECESSOR_DAG`
- Required existing predecessor: `MAP-PR-011`
- First Rust implementation node: `RUST-PR-001`
- Rust default switch: only `RUST-PR-015`
- Final fresh-context audit: `RUST-PR-016`

The package itself may be reviewed/merged before MAP-PR-011. No Rust implementation PR may start early.

## Files

- `RUST_ENGINE_ARCHITECTURE_CONTRACT_V1.json`
- `AUDIT_COMPILED_EXEC_PLAN_V1.json`
- `RUST_ENGINE_P0_P1_THREAT_CATALOGUE_V1.json`
- `RUST_ENGINE_INVARIANT_TEST_MATRIX_V1.json`
- `RUST_ENGINE_FRESH_CONTEXT_REVIEW_CONTRACT_V1.json`
- `RUST_ENGINE_EVIDENCE_BUNDLE_SCHEMA_V1.json`
- `EVIDENCE_BUNDLE_TEMPLATE_V1.json`
- `CODEX_HANDOFF_PROMPT.md`
- `SOURCE_AUDIT_RECEIPT_V1.json`
- `PACKAGE_MANIFEST_V1.json`

Human audit:

- `docs/audit/RUST_DEFAULT_ENGINE_ADVERSARIAL_AUDIT_20260824.md`

Tools:

- `python tools/validate_rust_default_engine_plan.py --check`
- `python tools/validate_rust_default_engine_plan.py --check-readiness RUST-PR-001`
- `python tools/materialize_rust_default_engine_pr.py --pr-id RUST-PR-001 --base-sha <40-hex>`
- `python tools/verify_rust_default_engine_evidence.py --contract <path> --evidence <path>`

## Non-negotiable workflow

1. Complete existing MAP DAG through MAP-PR-011.
2. Materialize one exact-base contract.
3. Implement one PR only.
4. Produce raw evidence bundle.
5. Run fresh-context audit-only review.
6. P0=0, P1=0, unresolved=0.
7. Merge.
8. Start the next PR.

Do not use this package to claim measured speedup, scientific traffic validity, or current Rust-default readiness.
