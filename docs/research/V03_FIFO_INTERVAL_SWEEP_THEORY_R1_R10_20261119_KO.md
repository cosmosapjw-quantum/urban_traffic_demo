# V03 FIFO interval sweep: Theory R1–R10 (2026-11-19)

Authority: original PLAN v1.1.26; current research parent 15d7546ade8b1ee6efe16f9a2a1b33cc1a1c2622. Isolated worktree research/v03-fifo-interval-sweep-20261119. Original V03 exact physical model, 100000 population per case, 86400-second day, 3 cities x 3 runs, 8 GiB per-process and 7200s wall contract stay protected. No hyperparameter fitted or new traffic coefficient selected.

## R1: Actual unfinished original scientific task
Reduce the avoidable O(n e) full input scans in original Rust exact time-interval packet construction, while preserving each physical Part, birth, route, interval time, event and checkpoint bit pattern. Do NOT claim this eliminates the observed packet genealogy doubling or clears the 0/9 full-day acceptance.

## R2: Primary project and literary provenance
Actual source crates/metroflow-rust/src/v1_road.rs: function interval_packets, and artifacts/v1_v03_workspace_20261117/ATTRIBUTION_KO.md. From Valley 25600->25650s previous trace: parts 5.63M->10.98M, packets 111k->210k, partial service copying whole composition. Bit-equal interval merges recover ~1.9% rows. Prior proportional merge census improved only ~1.01–1.08x packet count. These direct source observations are not equivalent to a mathematical impossibility theorem. Literature: Daganzo 1995, Cell Transmission Model Part II (https://its.berkeley.edu/publications/cell-transmission-model-part-ii-network-traffic), multi-commodity physical routing; Bar-Gera & Carey 2017, Representation requirements for perfect first-in-first-out verification in continuous flow dynamic models (https://www.sciencedirect.com/science/article/abs/pii/S0191261516305458) warns perfect FIFO representation can require unbounded flow element growth. Neither proves that this particular Rust optimization works.

## R3: Exact input/output contract
For each original Part row p: (tag,offset,mass,birth,pa,pb). Endpoints are finite f64. Edge vector is all pa and pb, sorted by f64::total_cmp and deduped using numeric f64 equality. Each consecutive edge pair [a,b] with b>a selects an original nonpoint input p iff pa<=a, pb>=b, pb>pa. It sets q.mass=p.mass*(b-a)/(pb-pa), q.birth=p.birth*(b-a)/(pb-pa), q interval=[a,b]; no physical approximations. Each point input pa=pb=a is emitted at a. Original stable input order is required before combine's key sorting / fsum.

## R4: Divergence and choice
A. Local adjacent same-density bit-equal merging: known insufficient for actual V03 growth.
B. Shared composition DAG and split factors: may improve row-storage constant but logical event count grows; must later test multiplication rounding.
C. Averaging time moments or changing to KCMB fixed-state closure: different physics, not an original V03 acceptance.
D. Selected: exact event-based interval selection via active indexed set, no changed physical formulas, same output ordering.
E. Native cumulative-flow link representation: separate future research; full temporal birth clock and route order equivalence unproved.

## R5: Derivations
Theorem S1 (sweep equality). Let e_i=a, e_(i+1)=b be consecutive sorted distinct finite endpoints containing every p.a,p.b. For nonpoint pa<pb, the predicate pa<=a && pb>=b is equivalent to pa<=a && pb>a: since pb is also an edge, there is no endpoint strictly between a and b. Hence activating a record at its start and removing at its end yields exactly the same interval active set on each nonempty [a,b]. At each a, point inputs pa=pb=a are treated separately, and all selected input indices are emitted in ascending original index. The equivalence requires finite endpoints and numeric comparisons, not arbitrary interval interpolation.

Theorem S2 (conditional IEEE bit equality). If selected Part input order is identical, the original combine's key grouping, tie ordering and fsum see the same sequence. Calling the unchanged q.mass=q.mass*(b-a)/(pb-pa) and q.birth=q.birth*(b-a)/(pb-pa) on the same selected input preserves each IEEE bit pattern on successful execution. The resulting original Packet order and serialization must be bit-identical. This is not a guarantee that the same resource-limit failure occurs at exactly the same point: the new index buffers have an extra scratch cost. Verify negative-zero and positive-zero endpoints, point overlaps and interval order explicitly.

Theorem S3 (work bound). With n original input rows, e<=2n unique endpoints and R sum of all output selected-row occurrences, the original repeated scan is O(n e+R). An index sweep with sorted events and ordered active indices is O(n log n+e log n+R) for selection, besides shared combine work and packing. Additional O(n) transient memory must be charged explicitly in the existing conservative native work budget. R may itself grow exponentially across physical simulation time, so neither this asymptotic improvement nor a fast microbenchmark solves the V03 24h packet explosion.

Theorem S4 (signed zero). Original sort uses total_cmp and dedup uses numeric equality, so -0.0 and +0.0 may coalesce into one edge. The event sweep must group them by numeric equality, not by 64-bit endpoint word. Input Part boundary payload signs remain unchanged in the checkpoint.

## R6: Counterexamples and reject criteria
Exact old scanning selection is the independent oracle; any difference in selected indices, packet time/birth, physical ledger or checkpoint SHA at source-identical physical horizon rejects the candidate. Also reject any physical-model parameter changes, silent mass deletion or weakened memory/time limits. Use negative-zero, point packets, overlapping intervals, random finite rational endpoint grids and adversarial source order. Resource accounting must cover active-set and sorted-index scratch rather than exempt them.

## R7: Planned experiments
Run the existing cargo 61 tests and V1 Python original road/interval/checkpoint regression suite. Add Rust independent original-scanning oracle and new sweep selector tests with observed behavioral RED before source implementation. After green run a bounded original Valley 100k input prefix with exact same matrix/parameters, using the original parent reference checkpoint SHA: 25300 seconds -> 7bcbd4e7eb04d8e0014524fa815a29c56b7873c5f3bb12c37a231caa648f32e1. Do not conflate a prefix with 24h acceptance. A separate bounded microbenchmark can compare algorithm time and scratch under varying input distributions.

## R8: Evidence gates
S1–S4 are DERIVED for finite valid records, and the implementation remains UNVERIFIED until tests. Source-representational packet count blowup remains BLOCKED; old DAG 19/21, three 100k calendars prepared 3/3, prior bounded replay 1/1, full-day runs 0/9. No status inflation by code compilation.

## R9: Code boundaries
Only isolated research-branch original Rust function interval_packets selection may change; physical class/route speed, time, branch, source, node gate and checkpoint serialization must not change. New indexed event selector must preserve original row order, avoid per-edge full scans, retain existing combine, use explicit accounted O(n) scratch. Negative benchmark or identity mismatch triggers rollback of candidate and preservation of failed evidence.

## R10: Publish
First theory commit+push with remote SHA readback, then implement code/test with RED/GREEN and push, then independently verify original physical prefix, memory/time and persist hashes/receipts in final commit and push. Original main and PR #41 remain unchanged. Next substantive science after this bounded slice is an original packet-provenance DAG or similar exact partial-service event representation, with independent real vs IEEE equivalence and temporal FIFO observables.
