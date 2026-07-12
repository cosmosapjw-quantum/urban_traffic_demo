# Runtime Closure Remediation — 2026-07-12

## Status And Revision Boundary

This is a post-audit supplement. It does not replace or rewrite the hostile
2026-07-11 finding at source baseline
`96e54ca907babe6425212ac2e088615687549d72`. Audit delivery commit
`e428de848184f9b079e47f027f0b205c80b9d443` remains the reproducible negative
control in which generated active routes do not create turn demand.

This supplement applies only to a later revision that contains the remediation
code, its tests, and this file. In a delivery ZIP, the authoritative identity
is `packaged_commit` in `provenance/package_metadata.json`. If that commit does
not contain this supplement and the referenced tests, use the historical audit
verdict instead.

## Narrow Verdict Change

| Claim | 2026-07-11 baseline | 2026-07-12 remediation status |
|---|---|---|
| Generated routes create legal per-turn demand | `REFUTED AT BASELINE` | `IMPLEMENTED`; `INTERNALLY VERIFIED` on seed 41 |
| Realized turn flow advances the matching agents and queue mass | `REFUTED AT BASELINE` | `IMPLEMENTED`; `INTERNALLY VERIFIED` on seed 41 |
| Integrated runtime is a validated 100k-city traffic simulator | `NOT VALIDATED` | `NOT VALIDATED` |
| Traffic and morphology match an observed named city | `NOT VALIDATED` | `NOT VALIDATED` |
| `SimulationState` and legacy LUTI orchestration form one closed loop | split | still split |
| Source and artifacts may be redistributed | no authority established | still no authority established |

The remediation closes one functional blocker. It does not convert the project
from a research prototype into a scientifically or operationally validated
simulator.

## Implemented Remediation

The post-audit Python runtime now:

1. compiles deterministic turn authority from the finalized directed road
   topology, including explicit forbidden immediate returns;
2. derives per-turn and sink demand from active route positions before each
   flow solve;
3. solves point-queue link/turn flow with deterministic fractional source
   service and downstream receiving carry, with sink and internal turns in one
   deficit scheduler so sustained through demand cannot starve completion;
4. commits exact realized turn and sink tokens to the corresponding agents and
   queue mass; and
5. fails closed on absent, illegal, duplicate, or unsupported movement
   authority, receiving-token excess, or a final link whose endpoint differs
   from the agent destination; rejects missing, non-finite, negative, or
   non-integral runtime token authority before it can be overwritten; and
6. fingerprints replay-authoritative config, static routing inputs, and all
   dynamic state while excluding host timing diagnostics.

Free-flow travel time and capacity are normalized to the configured simulation
tick. The point-queue delay expression is additive in tick units. These are
functional and dimensional corrections, not a calibration result.

The principal implementation and regression surfaces are:

- `src/metroflow/city/turn_compiler.py`;
- `src/metroflow/sim/step.py`;
- `src/metroflow/sim/routing_runtime.py`;
- `src/metroflow/flow/engine.py`;
- `tests/test_turn_compiler.py`;
- `tests/test_runtime_flow_closure.py`;
- `tests/test_flow_units.py`;
- and `tests/test_runtime_replay_closure.py`.

## Bounded Internal Evidence

The revised deterministic self-drive probe was run with scenario seed 41 for
20 ticks. It reported:

| Observation | Result |
|---|---:|
| Generated trips | 16 |
| Compiled turn rows | 51,886 |
| Permitted turn rows | 45,544 |
| Completed trips | 15 |
| Explicit no-route failures | 1 |
| Active agents after tick 20 | 0 |
| Queue mass after tick 20 | 0.0 |
| Ticks with a failed runtime invariant | 0 |
| Maximum per-link agent/queue mass delta | 0.0 |
| Fresh 20-tick replay runs with equal final-state digest | 2/2 |

The first post-activation movement occurs on the next flow tick, and all 15
routable trips complete by tick 16. The no-route trip is accounted for as a
failure rather than disappearing from lifecycle totals.

This evidence is `INTERNALLY VERIFIED`: it is supported by repository tests and
a deterministic developer probe. It is not an independent reproduction, a
scale benchmark, a statistical validation sample, or proof for arbitrary
networks and event schedules. See the two revision-specific commands in
[07 Reproduction And External Review](07_REPRODUCTION_AND_EXTERNAL_REVIEW.md).

The canonical runtime digest changes when service, receiving, or turn residuals,
sink flow, demand lifecycle, active-agent state, compiled turn authority, or
runtime config changes. A stale initial boundary is rejected before replay.
Two fresh seed-41 20-tick runs produced the same final-state fingerprint and
replay telemetry. This closes exact replay only for the bounded test surface;
it is not cross-platform attestation or broad event-workload coverage.

The current remediation environment did not provide JAX, a built
`_metroflow_rust` extension, or Cargo. The dependency-neutral Python suite and
explicit absence guards were exercised, but the changed Rust point-queue unit
test was not compiled or run here. A Rust-toolchain delivery gate remains
mandatory.

## Remaining Model And Product Limits

### Agent time and position are still coarse

An active agent advances by at most one realized route turn per simulation
tick. `progress_01` is not a calibrated continuous position within a link, and
the current agent traversal rule does not establish physical sub-link travel
kinematics. Passing the small probe therefore does not establish realistic
travel-time distributions.

### The flow model is a point queue

The remediated receiving rule treats capacity as a service rate. Links do not
have finite vehicle storage, spatial queue length, backward shock propagation,
or spillback that blocks an upstream link. Queue mass may accumulate without a
physical storage ceiling. This is an intentional model ceiling, not a complete
mesoscopic traffic representation.

### Rust does not yet own the per-turn agent contract

The optional Rust active-agent ABI does not implement the new exact per-turn
movement-token contract. Selecting that unsupported path fails closed; the
authoritative remediated agent commit remains in Python. Rust parity or speed
claims must not be inferred from the Python closure probe.

### Turn authority has a measured generation cost

In the seed-41 developer measurement, exhaustive incoming-by-outgoing turn
compilation added approximately 30% to generation time and approximately
17–22 MB of resident memory. This is a local, environment-dependent
measurement, not a stable benchmark. It must be rerun with locked dependencies
and retained raw measurements before making scale or performance claims.

### LUTI integration remains split

`SimulationState` owns the remediated routing/agent/flow path, while
accessibility and land-use evolution remain in the legacy `WorldState`
orchestrator. The remediation does not establish the promised closed
city-to-demand-to-traffic-to-accessibility-to-land-use loop.

### Scientific and distribution authority remain open

There is still no named-city calibration, observed traffic validation,
held-out morphology validation, or external reproduction. The repository still
has no root license and incomplete donor/import ancestry. The
[no-license notice](NO_LICENSE_NOTICE.md) remains controlling: an integrity ZIP
is not a license grant.

## Acceptance Consequences

The audit acceptance order remains unchanged. The seed-41 probe and paired
replay are sufficient to reopen scale and backend-parity work; they are not
sufficient to declare those workstreams complete. Before any 100k-city or
accelerator claim, require at minimum:

1. broader generated multi-hop conservation and failure-path coverage;
2. full-state deterministic replay across broader incident, merge/diverge,
   reroute, failure, and long-run workloads;
3. explicit physical semantics or a clearly bounded abstraction for agent
   traversal time and position;
4. refreshed copy-inclusive NumPy/Rust/accelerator benchmarks at controlled
   scale; and
5. independent observed-data calibration and validation for any scientific
   city claim.

Historical PNG, HTML, benchmark, and evidence-snapshot artifacts remain
diagnostics for their recorded revisions. They are not upgraded by this source
change.

## Packaging Rule

Do not overwrite the historical `e428de848184` delivery or its SHA-256 sidecar.
Build any remediated ZIP from a clean, non-shallow, committed revision with
`tools/build_external_audit_bundle.py`. Confirm that the new ZIP includes this
file under `reports/`, names its later `packaged_commit`, passes all manifests
and checksums, and retains the historical commit in the all-ref git bundle.
