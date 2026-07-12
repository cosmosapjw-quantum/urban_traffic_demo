# Claim Ledger

Status: active source of truth
Last updated: 2026-07-12

This file is the compact project-level claim authority. The external-audit
version with evidence and falsifiers is:
`docs/audit/metroflow_external_audit_20260711/06_CLAIM_PROVENANCE.md`.

## Implemented

- Python 3.12 + NumPy baseline with optional Rust CPU and optional JAX extras.
- Synthetic typed road topology, connectivity repair, optional planar sidecar,
  six morphology grammars, zones, POIs, deterministic citizens/trips.
- NumPy point-queue/node flow arrays, reverse-Dijkstra routing, ranked-K
  candidates, path-size selection, event/cadence rerouting, active-agent pool.
- Exhaustive deterministic generated turn authority, route-tail per-turn/sink
  demand, fair sink/turn deficit allocation, fractional service/receiving carry,
  exact agent/queue token commit, final-link destination validation, and
  fail-closed finite/integral token metadata validation.
- Replay fingerprints bound to complete initial state, ordered controls, actual
  RNG key, and step count; per-tick queue-transition witnesses; measured
  benchmark/report surfaces; static/runtime diagnostic renderers; Rust parity
  kernels; and bounded GPU/NN experiments.

## Internally Verified

- Deterministic regression and replay contracts covered by local tests.
- Explicit optional backends fail closed; `auto` alone may fallback.
- Synthetic connectivity/morphology/accessibility gates pass their recorded
  fixture matrices.
- Isolated Rust kernels match their Python/NumPy fixtures.
- JAX frozen dense-flow chunks accelerate tested 4,096/16,384-link workloads.
- The seed-41 eager self-drive probe compiles 51,886 turns, completes all 15
  routable trips by tick 16, records one explicit no-route failure, and reaches
  zero active agents/queue mass with exact per-link agent/queue equality through
  20 ticks.
- Two fresh seed-41 20-tick replays produce the same canonical final-state
  fingerprint and replay telemetry; stale residual boundaries fail before run.
- Ten deterministic 64-tick generated runs close 158 trips as 148 completions
  and 10 classified no-route failures with zero observed link-level
  agent/queue delta. A seed-41 10k-population run closes 3,105 trips at tick 156
  in the local corrected-runtime measurement.
- Optional JAX dense-flow parity is restored after aligning its point-queue
  receiving and additive-delay equations with NumPy/Rust; the measured
  4,096/16,384-link maximum drift is below `1.6e-5`.

## Refuted Or Blocked

- At the frozen 2026-07-11 audit baseline, the integrated generated-city runtime
  was not self-driving. That result remains a historical negative control and is
  superseded only by the bounded 2026-07-12 remediation evidence above.
- Whole-runtime Rust routing is slower than baseline in the recorded eager
  smoke workload.
- The row-local cost-to-go MLP input hypothesis fails its relation-conflict gate.
- The fixed graph-aware model misses its accuracy gate and repeat determinism.
- The 65,536-link JAX dense-flow chunk exceeds the fixed drift gate.

## Not Validated

- Complete 100k-population integrated runtime behavior. A bounded seed-41 run
  reaches tick 128 in 226.09 s with 10,626 vehicles still active and therefore
  does not establish closure or operational throughput.
- Real-city road morphology, traffic flow, route choice, demand, or LUTI fit.
- Broad generated/event conservation and replay across arbitrary, long-running,
  incident, merge/diverge, reroute, and failure workloads.
- Physically calibrated link traversal, finite storage, spillback, or shockwave
  propagation in the active-agent point-queue runtime.
- A unified `SimulationState` traffic/accessibility/land-use feedback loop.
- Runtime JAX/GPU flow with realistic host mutation and checkpoints.
- Production neural-network inference or route authority.
- Independent artifact reproduction or redistribution under a root license.

## Forbidden

- External-data learning.
- NN, RL, or LLM as route-legality/state-mutation authority.
- Smoke/PNG/HTML artifacts presented as scientific validation.
- Silent fallback for an explicitly selected optional backend.
- Direct CSUR city-generator/compatibility claims or unlicensed source reuse.

## Promotion Rule

No backend or scientific claim may be promoted solely from parity, static atlas
classification, one smoke workload, or visual inspection. Functional closure,
deterministic invariants, a falsifiable measured probe, exact provenance, and
baseline fallback are required.
