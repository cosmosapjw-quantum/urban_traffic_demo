# PR61 Review Record

Status: approved
Date: 2026-07-13

## /review-spec

The explicit config, derived storage, link progress, exit-ready demand, source
and downstream spillback, pause/replay, benchmark/UI provenance, and invariant
contracts are implemented. `point_queue_v1` remains the default; spatial mode
requires the NumPy baseline and fails closed for unsupported combinations.

## /review-code

Finding loop 1: the initial source-full test injected queue mass without a
resident agent, so it could pass admission assertions while violating the
runtime vehicle authority. The fixture now admits one real trip, introduces a
second pending trip, and verifies the full invariant report. A dedicated
finite-storage invariant now detects missing, malformed, or exceeded storage.

Finding loop 2: new telemetry fields existed on the dataclass but were absent
from `as_dict`, so replay comparisons silently omitted model/progress/spillback
provenance. Serialization, benchmark result, UI snapshot/stream, and static-map
metadata now preserve `traffic_model`; targeted consumer regressions pass.

Finding loop 3: an agent already waiting at progress 1.0 was counted as
"progressed" on every tick. The counter now records only a strict progress
increase, and physical-progress time is included in the parent active-agent
stage. No findings remain.

## /review-drift

Question: Does one tick still mean one whole link, or is physical length/speed
now an actual runtime constraint with finite receiving storage?

Evidence: 12 targeted tests cover derived storage, competing turns, physical
travel time, no same-tick movement, completion, source/downstream spillback,
finite-storage invariant, pause, replay, fingerprint, and benchmark metadata.
The related 135-test suite and full 759-test repository gate pass. Fresh imports
load no JAX, torch, or Rust extension.

Inference: link length and speed now constrain movement only in an explicit
coarse spatial mode, while deterministic NumPy state/token authority and the
default point queue remain intact.

Counterevidence checked: invalid mass fixtures, multi-incoming storage races,
early demand, same-tick allocation movement, exit-wait counter inflation,
queue/storage excess, hidden backend fallback, replay omission, import cycles,
point-queue regression, and smoke-to-validation claim inflation.

Decision: approve PR61 as structural simulation substrate. Do not claim
calibrated traffic, shockwaves, lane behavior, 100k closure, or default
promotion.

Falsifier: early turn demand, queue above storage, hidden fallback, mass/token
divergence, nondeterministic slot order, or point-queue regression.

Next action: PR62 measures morphology/plausibility across the fixed 30-map
matrix; PR63 separately measures scale and runtime cost.

## Gates

- targeted: `12 passed in 1.49s`
- related runtime/UI/backend: `135 passed in 46.69s`
- full repository: `759 passed in 503.97s`
- Ruff and diff check: passed
