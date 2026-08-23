# Claim-Evidence Ledger

Statuses are intentionally asymmetric: VALIDATED is limited to the exact evidence surface; NEGATIVE_RESULT preserves a failed or incomplete result; FORBIDDEN marks an inference the evidence cannot support.

| ID | Claim | Status | Evidence | Boundary |
| --- | --- | --- | --- | --- |
| C-01 | The six sample maps and 18 measurements bind to source tree 622dbe3779. | VALIDATED | source_receipt.json, sample_manifest.json, scientific fingerprint | Identity/provenance only. |
| C-02 | The held-out inventory contains exactly 18 scored attempts and no skips. | VALIDATED | heldout_morphology_results.json and package checker | Completeness of this fixed matrix only. |
| C-03 | All 18 cases reproduced their deterministic network fingerprint. | VALIDATED | deterministic_replay check in every result case | Same-code deterministic replay; not historical environment replay. |
| C-04 | Five non-grid styles satisfy their stated structural checks on all three held-out seeds. | VALIDATED | 15 passing non-grid cases and their direct witnesses | Seed-held-out structural morphology only. |
| C-05 | grid_core satisfies its held-out axis-alignment contract. | NEGATIVE_RESULT | 0/3 grid_core cases pass axis_aligned_grid_core | Failure cause remains contested; threshold is frozen. |
| C-06 | The full six-style held-out protocol passes. | NEGATIVE_RESULT | 15/18 overall, verdict FAIL | Do not average away the failed style. |
| C-07 | The generated networks reproduce real-city morphology on fresh external cities. | FORBIDDEN | No fresh OSM holdout was executed; MF-014, MF-026, MF-035 | NOT fresh-OSM empirical validation. |
| C-08 | The compatibility style implements organic street-network topology. | FORBIDDEN | MF-012; only curvilinear connector embedding is tested | Use the public warped-grid label. |
| C-09 | Traffic-functional validity was established. | NEGATIVE_RESULT | MF-036; one development probe lastfailed, no durable result matrix | Traffic-functional validation was not completed. |
| C-10 | The traffic algorithms are complete or production-valid. | FORBIDDEN | User claim boundary and MF-009, MF-011, MF-030, MF-036 | Functionality is the next target; completeness is explicitly out of scope. |
| C-11 | scalable_synthetic_v2 is ready to replace the runtime default. | FORBIDDEN | MF-014, MF-029, MF-030, MF-033, MF-035, MF-036 | runtime-default promotion remains blocked. |
| C-12 | PR #17 exact-head and synthetic-merge implementation gates passed. | VALIDATED | pr17_remote_receipt.json and two successful ci gate jobs | Remote software evidence; not scientific promotion. |

## Promotion decision

The structural milestone in merged PR #17 remains valid. The new seed-held-out experiment is a 15/18 **NEGATIVE_RESULT** because grid_core failed all three seeds. Fresh empirical morphology, traffic-functional validity, traffic-algorithm completeness, and runtime-default promotion are **FORBIDDEN** interpretations of this package.
