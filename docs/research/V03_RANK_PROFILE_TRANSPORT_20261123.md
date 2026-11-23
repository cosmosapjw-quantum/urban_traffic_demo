# Marked FIFO rank transport: conservative merge and bounded representation experiment

Date: 2026-11-23. Research module: src/metroflow/v1/rank_profile_transport.py.
Historical source baseline: 90bfca2c2ddf081cbdf40d11b95ff820837d03b5.
Contract/history: artifacts/v03_constructive_remodel_20261123/R4_rank_contract.md and R2_model_history_map.md.

## Result and scope

The implemented exact-rational module replaces repeated copying of a fixed heterogeneous marked profile with immutable rank restrictions. It retains every internal composition, original birth-moment, boundary-time and readiness change. A conservative multi-input lift constructs a new downstream profile under declared exchangeable same-boundary mixing. This is an integrated Python research reference, not the selected Rust V03 solver or a claim of native f64/checkpoint identity.

The first scoped run passes nine behavior tests. Increasing-cut experiments agree exactly with an independent mutable proportional-head oracle and with a direct analytic exit-moment formula. At 32,000 cuts the view implementation retains about 24.28MB of traced session allocations versus 76.64MB for materialized rows. Construction is faster; observing every output is slower. Repeated phase-shifted merges grow true profile knots from 2 to 259 after eight levels. Both the positive result and remaining complexity are exposed.

The single-source prefix and inverse-service machinery existed in the 2026-11-21/22 project work. It is reused with attribution. The present additional contribution is an explicit multi-input conservative map, heterogeneous profile-preserving views, a reusable checked API and actual representation/merge-growth measurements. No claim of worldwide theorem novelty.

## 1. Physical variables and retained information

The state coordinate z is admitted vehicle-equivalent mass [veh], not a vehicle ID. A component mark identifies all future route/class and observation distinctions required by consumers. Given source segments k with total mass \(M_k>0\), component masses \(m_{kg}\ge0\) and original birth moments \(b_{kg}\) [veh·s], define cumulative measures:
\[
F_g(z)=\int_0^z p_g(u)\,du,\quad
B_g(z)=\int_0^z h_g(u)\,du,\quad
p_g=\frac{m_{kg}}{M_k},\quad h_g=\frac{b_{kg}}{M_k}
\]
on the corresponding source rank segment.

Thus F has units veh, B veh·s, p is dimensionless and h has units s. Birth moments carry original source clocks; they are never overwritten by the arrival time at a later node. A first moment does not reconstruct microscopic birth-time support or quantiles. Source birth admissibility is a supplied physical assumption; the module cannot prove an unavailable underlying birth distribution from a moment.

A RankSegment also carries:
- optional ready_target [m], constant on that declared admission segment;
- optional boundary=(start,end) [s], an affine boundary-clock map over the segment.

Unknown values remain None. Requested readiness/boundary verification fails closed when its metadata is absent. Positive-speed assumptions are not used in the rank algebra.

The original active-meso shared displacement s(t) and response dynamics remain external. If targets Y are nondecreasing:
\[
R(t)=\sup\{z:Y(z)\le s(t)\}
\]
is the ready prefix. Native node capacity, receiving/storage, class latent response, route rerouting, immutable transaction/checkpoint semantics and common-motion integration are not inferred by this module.

## 2. Exact service and immutable views

A profile owns a tuple of immutable source segments. A RankView owns only parent, lower rank and upper rank. A partial service takes a restriction rather than copying each mark:
\[
\Delta m_g=F_g(b)-F_g(a),\qquad
\Delta b_g=B_g(b)-B_g(a).
\]
Adjacent views of the same parent concatenate as \([a,b]\cup[b,c]=[a,c]\). Their different internal compositions remain represented. This is not replacing them by a homogeneous mean.

Conservation and exact subdivision follow from telescoping differences. Equality to the earlier proportional-head model holds in real arithmetic when both consume the same scalar service and every actual composition/readiness/node-law knot is respected. It does not prove that arbitrary retiming of a coupled traffic solver gives the same service.

ServiceWindow is a finite nonnegative constant-rate interval. serve_windows returns one TimedView per positive service window and rejects overlap, out-of-order clocks, overservice and requested-but-incomplete service. It deliberately does not invent a capacity or ready clock.

transport_moments visits every semantic knot inside each timed view. During a constant-rate service interval,
\[
T(z)=t_0+\frac{z-z_0}{q},\qquad
E_g=\int T(z)p_g(z)\,dz.
\]
The integral on each affine piece is exact by the mean endpoint clock. Per-mark residence moment is \(E_g-B_g\). This is total experienced residence of the supplied served population; an incomplete or tail subview is not labelled the overall population.

If boundary verification is requested, actual exit clock must not precede the affine entry clock at either end of each piece. Because their difference is affine, endpoint inequalities imply the inequality throughout. With an additional declared nondecreasing displacement callable, each piece must have crossed its ready target by its first served clock. Sampled endpoint monotonicity checks reject inconsistent supplied values; the callable's global monotonicity is a caller assumption, not certified from finitely many evaluations.

Without displacement, readiness_checked is false. Without boundary checking, boundary_checked is false. These flags are observations of the checks actually requested.

## 3. Conservative multi-input lift

Assume continuous piecewise-affine cumulative incoming flows \(A_j(t)\), nonnegative rates, FIFO within every upstream stream, immutable marked profiles \(F_{jg},B_{jg}\), and no internal reassignment of a route mark. The same physical boundary interval uses the selected exchangeable mixture.

Define
\[
W(t)=\sum_j A_j(t),\quad
C_g(t)=\sum_j F_{jg}(A_j(t)),\quad
K_g(t)=\sum_j B_{jg}(A_j(t)).
\]
A generalized inverse \(\tau(z)\) of W gives
\[
F_g^{in}(z)=C_g(\tau(z)),\quad B_g^{in}(z)=K_g(\tau(z)).
\]
On intervals of positive total flux,
\[
\partial_z F_g^{in}
=\frac{\sum_jq_jp_{jg}(A_j)}{\sum_jq_j},\qquad
\partial_z B_g^{in}
=\frac{\sum_jq_jh_{jg}(A_j)}{\sum_jq_j}.
\]

These fractions are nonnegative and sum to one. Every downstream component increment is the sum of incoming component increments. A plateau of W forces every nondecreasing A_j to be constant, so inverse ambiguity cannot affect C or K. The map \(A_j(\tau(z))\) is nondecreasing: each downstream prefix consumes upstream prefixes. It does not claim individual lane order between simultaneous fractions.

### Event partition covariance and its boundary

Within one constant-source-law interval, the downstream marked profile is affine. Subdividing it and concatenating its restrictions preserves the same measure; across a true source-law change the changed segment remains. The implementation performs exact adjacent coalescence only if:
1. every mark mass per total mass is identical;
2. every birth moment per total mass is identical;
3. ready targets are identical;
4. boundary clocks are contiguous and have the same affine slope.

No tolerance or averaging permits a merge. This local proportional-law recognition is old machinery used to eliminate redundant numerical subdivisions; the heterogeneous parent/view representation is the complementary new structure.

A target_at_end callback explicitly assigns the downstream segment's readiness target at its declared admission endpoint. If changing numerical partitions changes those endpoint targets, readiness is a changed discretization. The tests demonstrate that profile mass/birth can remain equal while ready prefixes change. Therefore partition covariance is claimed only for the same readiness/boundary law, not every callback and partition combination.

Atom/tie policies beyond continuous TimedView streams are not implemented. Input physical service histories are supplied; merge_streams validates stream order/contiguous rank but does not solve upstream capacity or certify upstream motion. Call transport_moments with the appropriate known metadata/displacement if input physical validity must be checked.

## 4. API and composition

| API | Meaning |
|---|---|
| MarkedMass(mark, mass, birth_moment) | Exact component amount; zero mass requires zero birth moment |
| RankSegment(parts, ready_target=None, boundary=None) | Piecewise constant marked composition and target; affine boundary clock |
| RankProfile(segments).view(start=0,end=None) | Immutable parent and absolute rank restriction |
| RankView.subview(start,end) | Relative restriction inside an existing view |
| RankView.iter_pieces() | Actual internal profile knots and clipped boundary metadata |
| RankView.moments() | Exact component mass/birth measure over a view |
| concat_adjacent(views) | Identity-checked same-parent contiguous view concatenation |
| RankProfile.ready_prefix(displacement) | Exact known target frontier; unknown metadata errors |
| serve_windows(view,schedule,require_complete=False) | Exogenous scalar FIFO service without node solver |
| transport_moments(slices,displacement=None,check_boundary=True) | Exact mass, birth, exit and residence, plus actual check flags |
| merge_streams(streams,target_at_end=None) | Conservative same-boundary multi-input profile, retaining true knots |
| representation_stats(views) | Unique profile/segment/mark object owners, view count and profile DAG depth |

transport_moments returns TransportMoments. Its as_dict() maps mark to frozen MarkTransport with mass, birth_moment, exit_moment and residence. Input numerical scalars must be int or Fraction. Implicit float conversion is rejected; f64 callers must make any exact-binary or approximate rational conversion explicit.

To couple the parent's finite-response service on the last 5 veh, take profile.view(profile.mass − 5), construct the physically obtained ServiceWindows, call serve_windows, then call transport_moments with the declared displacement and preserved boundary metadata. This uses the same original birth moment while restricting the observation population to those final 5 veh. Arrival/readiness and capacity are separate physical obligations.

The representation is intentionally a flat profile plus views. profile_dag_depth=1 and view_profile_depth=2 count profile graph layers, not every Python implementation object. Merge materializes the next true profile; no claim is made for an unimplemented deep expression DAG.

## 5. Scoped tests and actual experiments

Tests: tests/research/test_v03_rank_profile_transport_20261123.py.
Primary command: PYTHONPATH=src python3 -m pytest -q tests/research/test_v03_rank_profile_transport_20261123.py.
Observed: **9 passed in 0.23s**, exit 0. Raw: R5_rank_primary_tests.txt.

Behavior checks cover independent mutable-head mass/birth/exit comparison with stopped service; heterogeneous views; affine boundary clipping; missing metadata refusal; conservative multi-input merge and exact refinement; the callback readiness counterexample; repeated phase-shifted knot growth; tail-population composition; invalid exact inputs and invalid service/order. Import success is not counted as a behavior RED, and no test-first failure is claimed for this module.

Experiment driver: tools/research/v03_rank_profile_experiment_20261123.py.
Each case runs in a fresh Python process, preserving separate process wall/RSS. Both representations use the same profile, eight marks, schedule and exact direct formula \(T(z)=10+z\). Output construction and all-output observation are measured separately. tracemalloc includes generated inputs, schedules and outputs, excluding import-time allocations; RSS includes the whole process and tracemalloc bookkeeping, so it is not an uninstrumented production-memory measurement. This is a controlled synthetic Python comparison, not Rust/native throughput.

### Initial cut ladder

| Cuts | View build / all-output observation [s] | Materialized build / observation [s] | Traced retained after build: views / rows [bytes] | Peak RSS: views / rows [bytes] |
|---:|---:|---:|---:|---:|
| 1,000 | 0.038624 / 0.178945 | 0.140227 / 0.111730 | 648,694 / 2,216,486 | 26,943,488 / 33,325,056 |
| 8,000 | 0.364982 / 1.618425 | 1.485652 / 0.968118 | 5,788,014 / 18,952,030 | 43,405,312 / 94,359,552 |
| 32,000 | 1.606110 / 7.487542 | 6.884754 / 4.183897 | 24,282,846 / 76,637,798 | 115,437,568 / 307,560,448 |

All cases preserve exact per-mark mass, birth and exit moments. For 32,000 cuts: views retain one profile, three segments and 24 original mark objects, plus 32,000 views. The materialized representation stores 32,001 partial packets and 256,008 distinct output mark tuples. Same-parent views can concatenate, but that does not erase the parent's three essential profile segments.

The build saving is real in this fixture. An observer requiring every cut's marks still pays to query them; its measured cost is higher for views here. Only total build-plus-observe comparisons are meaningful for that workload. No universal speedup or all-day extrapolation follows.

### Repeated multi-input growth

Each level merges two uniformly served copies of the preceding profile with a rational phase shift. Both copy the cohort measure, so mass and number of source streams grow; this is not a fixed-demand city experiment. Each output prefix is independently compared to the two-source cumulative inverse and sequential original row restriction.

| Levels | Essential output segments | Output mass [veh] | Accumulated merge wall [s] | Retained traced state/receipt [bytes] |
|---:|---:|---:|---:|---:|
| 1 | 5 | 4 | 0.000718 | 5,754 |
| 2 | 7 | 8 | 0.002441 | 9,378 |
| 4 | 19 | 32 | 0.009121 | 29,070 |
| 6 | 67 | 128 | 0.031728 | 100,330 |
| 8 | 259 | 512 | 0.125116 | 409,634 |

All retained output segments are essential under the complete supported mark/birth/readiness/boundary law. The flat profile depth remains one, so the growth cannot be concealed as an unreported DAG. Every level checks five exact downstream prefixes against an independent upstream cumulative calculation.

Raw reports and per-process receipts: artifacts/v03_constructive_remodel_20261123/R7_rank_experiments.json and R7_rank_cuts_*/R7_rank_merges_* files. The completed larger 128,000-cut / 10–12-merge-level extension is recorded in R7_rank_expanded_experiments.json and summarized below.

## 6. What this resolves and what remains

**Constructive resolution in the reference domain:** partial service of a fixed heterogeneous source no longer requires copying its component rows into every output packet. Immutable views preserve causal order and exact original birth observables; multi-input exchangeability has an explicit measure map rather than a heuristic global average. The positive effect is measured on real allocated objects.

**Remaining implication:** repeated genuinely different merges create essential profile complexity. A full native consumer must also use each local derivative/knot when node constraints change. Ignoring those knots changes the selected physics; eagerly enumerating all may restore the prior cost. This finite example is evidence for a specific failure mechanism, not a theorem that every representation or controlled closure fails.

**Identity limits:** no equivalence to native f64 reduction order or checkpoint wire is claimed. No full native capacity/storage, latent motion, routing or world-state adapter is implemented. No real original 100k city or V03 24h accepted run follows from these research oracles. The native execution/readiness ledger remains the parent's separate authority.

## 6A. Completed expanded ladder

All expanded workers exited 0. The 128,000-cut view process took 37.392284s and the materialized process 49.441568s, including setup/observation/measurement. Internal measured work:

| Mode | Build [s] | All-output observation [s] | Retained traced after build [bytes] | Peak RSS [bytes] | Output representation |
|---|---:|---:|---:|---:|---|
| views | 6.414145 | 27.069267 | 98674526 | 385904640 | 128000 views; 3 essential segments, 24 source marks |
| materialized | 26.071769 | 16.968099 | 307699302 | 1159786496 | 1024008 distinct output mark rows |

All per-mark mass, birth and exit moments remain exactly equal. Build-plus-observe ratio (materialized/views) is 1.2854; retained traced ratio is 3.1183. These are measured fixture ratios, not universal or native speedups.

| Merge levels | Essential segments | Accumulated merge wall [s] | Retained traced state/receipt [bytes] | Peak RSS [bytes] |
|---:|---:|---:|---:|---:|
| 10 | 1027 | 0.498610 | 1643214 | 36515840 |
| 12 | 4099 | 2.009545 | 6638322 | 71860224 |

Repeated merge growth is therefore a measured remaining limitation even while cut-induced row materialization is reduced. Total process runtimes rose from approximately 0.37–0.41s at 1,000 cuts to 37.39–49.44s at 128,000 cuts; every comparison consumed the same declared service history within its size pair.

## 7. Origin drift watchdog

ALIGNED_WITH_OPEN_OBLIGATION. The reference preserves original bulk active-mesoscopic intent, explicit units, destination/class marks, causal prefix service, original birth clocks and an immutable state representation. It does not substitute vehicle IDs, remove demand, relax capacity, or replace old-state admission by same-tick feedback.

Earlier proportional merging and single-source inverse-service theory remain credited. The new construction is tied to an actual repeated-materialization blocker, with retained complexity and observer cost exposed. The scientific model remains explainable through marked conservation and FIFO rather than merely improved guard accounting. Current open obligations are native consumer mapping, a numerical/wire decision, coupled physical validation and original full-day resource evidence.
