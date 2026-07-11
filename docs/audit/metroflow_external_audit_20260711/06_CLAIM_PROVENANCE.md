# Claim Provenance Ledger

This ledger states what an external reviewer may and may not infer at source
baseline `96e54ca`. A passing test means internal verification, not empirical
validation.

| Claim | State | Evidence | Boundary / falsifier |
|---|---|---|---|
| Python 3.12 + NumPy is the default authority | IMPLEMENTED | `pyproject.toml`, `SimulationConfig` | fresh base-only install must import/run |
| JAX and Torch are optional extras | IMPLEMENTED | `pyproject.toml`, import-firewall tests | core import loads either package |
| Rust CPU kernels exist for edge/flow/routing/reroute/agents | IMPLEMENTED | `crates/metroflow-rust`, wrapper tests | extension export/parity failure |
| Explicit optional backends fail closed; `auto` may fallback | INTERNALLY VERIFIED | backend tests | explicit unavailable silently falls back |
| Generated topology is weakly connected after repair | INTERNALLY VERIFIED | connectivity tests/metadata | multi-seed disconnected output |
| Explicit planar mode removes proper crossings in audited fixture | INTERNALLY VERIFIED | seed-44 artifact/tests | same fixture retains a crossing |
| Six morphology styles are structurally distinct | INTERNALLY VERIFIED | morphology gate matrix | deterministic metrics/geometry collapse |
| Generated maps are realistic cities | NOT VALIDATED | visual artifacts are schematic | observed-city calibrated comparison required |
| Morphology POI/zone placement preserves tested reachability | INTERNALLY VERIFIED | six-style, three-seed audit | inaccessible audited pair |
| Morphology placement improves travel demand realism | NOT VALIDATED | no demand experiment | calibrated OD comparison required |
| Reverse Dijkstra is route-label authority | IMPLEMENTED | routing code/tests | legality/parity regression |
| Ranked K and path-size selection are deterministic | INTERNALLY VERIFIED | routing/replay tests | seed-stable candidate mismatch |
| Integrated runtime drives generated trips through turns | **REFUTED AT BASELINE** | three-tick self-drive probe | fixed by route-derived turn demand and movement proof |
| Runtime is immutable | SPECIFIED, NOT ENFORCED | replacement APIs | direct array/dict mutation succeeds |
| Runtime replay is deterministic | INTERNALLY VERIFIED, LIMITED | replay tests | full-state digest or conservation mismatch |
| Accessibility/LUTI is integrated into `SimulationState` | NOT IMPLEMENTED | only legacy orchestrator wires it | multirate trajectory test required |
| Whole-runtime Rust routing accelerates execution | REFUTED FOR TESTED WORKLOAD | 26.70 s Rust vs 8.02 s baseline | new copy-inclusive workload evidence |
| JAX accelerates frozen dense-flow chunks | INTERNALLY MEASURED | PR47 artifact | fresh reproduction or synchronization cost |
| JAX dense flow is safe as a runtime backend | NOT VALIDATED | host mutation/replay unmeasured; 65k drift failure | integrated checkpoint/replay gate |
| Row-local cost-to-go MLP is admissible | DEPRECATED / REJECTED | 69.073% conflict | new input hypothesis, not threshold tuning |
| Fixed graph model improves held-out cost-to-go | REFUTED FOR TESTED MODEL | ratio 1.0581, 0/3 | owner-authorized new model hypothesis |
| Graph context is universally useless | NOT SUPPORTED | one model was tested | broader experiments could falsify |
| Current optional surrogate is a production NN | NOT SUPPORTED | simple experimental baseline | trained/versioned model evidence |
| Simulator supports 100k integrated operation | SPECIFIED, NOT VALIDATED | PRD/config target | closed long-run benchmark required |
| Traffic equations match observed traffic | NOT VALIDATED | synthetic point-queue tests only | calibrated field-data study required |
| Artifacts are scientific validation | FORBIDDEN | guardrails/ledger | independent empirical protocol required |
| CSUR code is a city-layout generator used by Metroflow | FORBIDDEN / FALSE | source provenance review | none within current source policy |
| Offline OSM XML can be imported for reference | IMPLEMENTED | OSM adapter/tests | parser/provenance regression |
| External-data learning is used | FORBIDDEN and absent by policy | AGENTS/constitution | runtime fetch/training input appears |
| Repository history proves original donor authorship | NOT SUPPORTED | history starts with imported bundle | upstream signed provenance required |
| Repository can be redistributed under a known license | NOT SUPPORTED | no root license | owner license decision required |

## Claim Discipline

Future reports should use the smallest valid statement:

- parity is not validation;
- deterministic replay is not empirical accuracy;
- a morphology regression gate is not city realism;
- a device-resident microbenchmark is not runtime acceleration;
- a failed fixed NN model is not a universal impossibility result;
- a passing local suite is not independent reproduction.

## Missing Provenance

PR47 and PR51 have canonical result summaries, but current manifests do not
preserve all raw arrays/predictions/weights, complete environment locks,
independent attestations, and checksums needed to reconstruct every metric from
first principles. PR47 also lacks a bundle-level manifest matching the later
audit standard. PR49/PR51 arithmetic can be recomputed from retained summaries,
but provenance is still author-local.

Once built from a clean committed revision, the external-audit ZIP improves
source/history integrity for that snapshot; it cannot retroactively add
independent preregistration or artifact ancestry.
