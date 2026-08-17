# Task C Integration Plan — Stable Capture C Seams

DATE: 2026-08-17
STATUS: FROZEN_DOCS_FIRST_PLAN

## 1. Scope & Seam Definition

Task C integrates stable validation receipt capture and verified source snapshot into `src/metroflow/city/scalable_authority.py`:

1. `_capture_verified_task5_source_snapshot_from_receipt(network, blocks, compiled)`
   - Looks up `network`, `blocks`, and `compiled` receipts from `scalable_validation_receipts`.
   - Validates fingerprint match against source objects.
   - Returns immutable `_VerifiedTask5SourceSnapshot`.

2. `_capture_stable_static_validation_receipt(authority, snapshot)`
   - Builds `_ValidationReceipt` for the `static` stage with `_STATIC_SEAL_SCHEMA`.
   - Registers receipt via `_register_validation_receipt(receipt)`.
   - Returns registered `_ValidationReceipt`.

## 2. TOCTOU & ABA Limits

- Fingerprints and schema versions are verified at capture time before receipt registration.
- Once registered, receipts in `scalable_validation_receipts` are immutable (`frozen=True, slots=True`).
- Idempotent re-registration allows same fingerprint, rejects differing fingerprint (fail-closed against ABA).

## 3. Registration Ownership

- Task 5 `build_scalable_static_authority` or external harness orchestrator owns registration of Task 5 receipts.
- Pure simulation runtime remains independent; receipts module is an optional validation sidecar.

## 4. Code Budget

- Source diff budget: <= 120 lines in `src/metroflow/city/scalable_authority.py`.
- Test diff budget: <= 150 lines in `tests/test_scalable_authority.py`.
