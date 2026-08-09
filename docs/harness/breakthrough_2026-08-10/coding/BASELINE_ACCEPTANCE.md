# Phase 1 Reproduction / Acceptance Baseline

DATE: 2026-08-10
STATUS: ACCEPTED_FROM_HASH_BOUND_CURRENT_EVIDENCE; LONG_GATES_NOT_RERUN

## Current Task B checkpoint

| Artifact | SHA-256 | Evidence |
|---|---|---|
| `src/metroflow/city/scalable_validation_receipts.py` | `5181eb4b03b87d91205a422a56183c14a59fc4299ce1cb83592244a4f07b4bdb` | current bytes |
| `tests/test_scalable_validation_receipts.py` | `434442e01ae29919fda8712b17b70b5f66a84d0b66996fbf59bea64f1c930f06` | current bytes |
| clean-room replay report | `2f63435a05dcb52232dc89ce9bfc4cbfeee2419944bc687ac40f7c88f5e9d9d5` | Slice 18, 177 focused passes |

The 177-pass result is accepted prior evidence from the replay receipt; it was
not rerun in this design-only coding loop.

## Accepted current defect signals

- Streaming sort uses `b"".join(emit(...))` per member/key. Two bounded 700 x
  65,536-character diagnostics measured about 46.1 MB peak, above the reviewed
  32 MiB contract. This is not the official raw-RSS 1M gate.
- `_Task5NetworkProjection` retained a caller nested list; mutation was observed
  as value `999` through the frozen record.
- A hostile mutated stored seal executed `__eq__` during lookup and propagated
  `AssertionError`.
- Current production has no non-test consumer/import of the receipt module.
- Both current serializers sort JSON encodings rather than the brief's normalized
  Python values. A bound probe yields `10,2` for numeric `2/10`; current-path
  agreement is therefore a shared defect, not reference authority.

## Separate Task 3B evidence blocker

- Walls: 27.502387543 s and 27.458000162 s, target `<20 s`.
- Profiled deficit: 7.531264014 s.
- Complete `_digest` elimination upper bound: 6.498666132 s, leaving
  21.032597882 s. Digest alone is insufficient.
- No non-overlapping capacity receipt exists; H-001 is `REOPEN_EVIDENCE`.

## Acceptance criterion for a future implementation

First reproduce each behavior-specific RED from a frozen complete manifest,
then rebuild the same behavior, preserve exact output/error oracles, satisfy the
official memory gate, complete six-style leaf equivalence, run required
software/scientific/reproducibility gates, and pass independent review.

Already-safe negative guards are recorded as regression GREEN, not fabricated
RED history. The immutable manifest and normalized-value vector packet are
separate from the append-only replay report.

## Skipped in this run

Official 1M memory/performance, six-style 180-leaf oracle, full Task B suite,
Task C, Task4/5 integration, G5 implementation, and traffic algorithms.
