# Metroflow External Audit Packet

Audit date: 2026-07-11
Source baseline: `96e54ca907babe6425212ac2e088615687549d72`
Audit posture: hostile, evidence-gated, no scientific-validation presumption

> **Historical scope and 2026-07-12 remediation notice:** The executive
> verdict and critical findings below describe the frozen 2026-07-11 source
> baseline. The audit delivery commit `e428de848184f9b079e47f027f0b205c80b9d443`
> also retains that result as negative evidence. Post-audit code now closes the
> small-probe turn-demand blocker in the Python runtime, but only at the
> `INTERNALLY VERIFIED` level. Read
> [10 Runtime Closure Remediation](10_RUNTIME_CLOSURE_REMEDIATION_20260712.md)
> before treating this packet as a statement about a later packaged revision.
> The remediation is not 100k-scale, empirical, LUTI, licensing, or independent
> validation.

## Executive Verdict

Metroflow is a substantial deterministic **research prototype and architecture
laboratory**, not yet a validated 100k-city traffic simulator. It has credible
substrate in synthetic network generation, NumPy flow arrays, reverse-Dijkstra
routing, replay fingerprints, optional Rust kernels, diagnostic visualization,
and bounded GPU/NN experiments. Its strongest engineering practice is that
failed experiments are normally retained as negative evidence instead of being
tuned into success.

At the audited baseline, the main product claim was not closed. The integrated
`SimulationState` path does not produce turn demand from active routes. A
three-tick functional probe activates trips and seeds source queues, but
`turn_demand`, outflow, and movement remain zero. The default initializer also
creates no eager trips, and accessibility/land-use evolution remains in the
legacy `WorldState` orchestrator rather than the integrated runtime spine.
Therefore that source baseline does not execute the promised complete
city-to-demand-to-traffic-to-LUTI loop.

The package is suitable for an external code/design audit. It is **not** an
independently reproduced performance package or empirical urban-model
validation package. The repository has one recorded author, no CI workflow,
unpinned dependencies, incomplete pre-import/donor ancestry, and no root
license. Those limitations are explicit rather than hidden.

## Critical Findings

1. **Integrated traffic closure was missing at the audited baseline.** Active
   trips did not populate node turn demand, so the authoritative runtime could
   not self-drive vehicles. The bounded 2026-07-12 remediation status is
   documented separately.
2. **The two runtime spines are semantically split.** `SimulationState` owns the
   new flow/routing/agent path; `WorldState` owns accessibility and land-use.
3. **City generation has become a monolith.** `generator_v2.py` has 5,654 lines
   and its largest function has about 4,338 lines, making morphology changes
   difficult to reason about or independently test.
4. **The validation ceiling is synthetic and internal.** Morphology, access,
   replay, parity, and benchmark gates are useful regression evidence, but no
   named-city calibration or observed traffic validation exists.
5. **Redistribution authority is unresolved.** There is no root license, and
   the imported starting bundle/donor ancestry is incomplete.

## Packet Contents

- [01 Origin And Motivation](01_ORIGIN_AND_RESEARCH_MOTIVATION.md)
- [02 Development History](02_DEVELOPMENT_HISTORY.md)
- [03 Architecture And Algorithms](03_ARCHITECTURE_AND_ALGORITHMS.md)
- [04 Experiments, Failures, And Results](04_EXPERIMENTS_FAILURES_AND_RESULTS.md)
- [05 Adversarial Technical Audit](05_ADVERSARIAL_TECHNICAL_AUDIT.md)
- [06 Claim Provenance](06_CLAIM_PROVENANCE.md)
- [07 Reproduction And External Review](07_REPRODUCTION_AND_EXTERNAL_REVIEW.md)
- [08 Source And Artifact Index](08_SOURCE_AND_ARTIFACT_INDEX.md)
- [09 Review Closure](09_REVIEW_CLOSURE.md)
- [10 Runtime Closure Remediation](10_RUNTIME_CLOSURE_REMEDIATION_20260712.md)
- [Evidence snapshot](evidence_snapshot.json)
- [No-license notice](NO_LICENSE_NOTICE.md)

## Claim Vocabulary

| Label | Meaning |
|---|---|
| `IMPLEMENTED` | Code or document substrate exists at the audited revision. |
| `INTERNALLY VERIFIED` | A repository test or deterministic probe supports it. |
| `DERIVED` | Inference from cited implementation and measurements. |
| `SPECIFIED` | A contract or intended behavior exists; execution is not implied. |
| `PROPOSED` | Future work or hypothesis. |
| `NOT VALIDATED` | Evidence is insufficient for the stronger interpretation. |
| `FORBIDDEN` | Project governance explicitly excludes the behavior. |
| `DEPRECATED` | Historical direction retained as negative evidence. |

## Reading Order For An External Auditor

1. Read this historical verdict, the remediation supplement, and the claim
   ledger before reading performance tables.
2. Re-run the baseline and current small self-drive probes in the reproduction
   guide at their stated revisions.
3. Inspect `sim.step`, `flow.engine`, and `sim.routing_runtime` together.
4. Treat all PNG/HTML artifacts as diagnostics, never validation evidence.
5. Verify the git bundle and checksums before relying on chronology.
6. Resolve licensing/provenance before redistributing source or artifacts.

When built after these files are committed, the ZIP contains the tracked
repository snapshot, a full all-ref git bundle, commit/ref listings,
environment inventory, integrity manifests, and this report set.
`tools/build_external_audit_bundle.py` is the authoritative builder. The ZIP
and its SHA-256 sidecar are delivery artifacts, not tracked source claims.
