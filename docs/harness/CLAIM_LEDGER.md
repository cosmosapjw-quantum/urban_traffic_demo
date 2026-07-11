# Claim Ledger

Status: active source of truth
Last updated: 2026-07-11

This file is the compact project-level claim authority. The external-audit
version with evidence and falsifiers is:
`docs/audit/metroflow_external_audit_20260711/06_CLAIM_PROVENANCE.md`.

## Implemented

- Python 3.12 + NumPy baseline with optional Rust CPU and optional JAX extras.
- Synthetic typed road topology, connectivity repair, optional planar sidecar,
  six morphology grammars, zones, POIs, deterministic citizens/trips.
- NumPy point-queue/node flow arrays, reverse-Dijkstra routing, ranked-K
  candidates, path-size selection, event/cadence rerouting, active-agent pool.
- Replay fingerprints, measured benchmark/report surfaces, static/runtime
  diagnostic renderers, Rust parity kernels, and bounded GPU/NN experiments.

## Internally Verified

- Deterministic regression and replay contracts covered by local tests.
- Explicit optional backends fail closed; `auto` alone may fallback.
- Synthetic connectivity/morphology/accessibility gates pass their recorded
  fixture matrices.
- Isolated Rust kernels match their Python/NumPy fixtures.
- JAX frozen dense-flow chunks accelerate tested 4,096/16,384-link workloads.

## Refuted Or Blocked

- The integrated generated-city runtime is not self-driving: generated topology
  supplies no turn authority, initialized turn demand is zero, and active agents
  receive no outflow movement budget.
- Whole-runtime Rust routing is slower than baseline in the recorded eager
  smoke workload.
- The row-local cost-to-go MLP input hypothesis fails its relation-conflict gate.
- The fixed graph-aware model misses its accuracy gate and repeat determinism.
- The 65,536-link JAX dense-flow chunk exceeds the fixed drift gate.

## Not Validated

- Complete 100k-population integrated runtime behavior.
- Real-city road morphology, traffic flow, route choice, demand, or LUTI fit.
- Full-state replay conservation under a generated multi-hop workload.
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
