# R2 model history map: marked rank profiles and conservative merge lift

## Scope and evidence contract

Baseline: **90bfca2c2ddf081cbdf40d11b95ff820837d03b5**. Branch: research/v03-constructive-remodel-20261123. This is bounded primary R1–R4 work, not independent review. Skills applied: physmath-research-loop 1.3.0 SKILL / POLICY_INTEGRATION / THEORY_LOOP and mathbox research-program 4.0.0. One exact construction run plus one bounded multi-input check; no native, Cargo, PLAN, caps or campaign edits.

Status: source history SOURCE_INSPECTED; algebra DERIVED; exact examples EXACT_RATIONAL_CHECKED; persistent native profiles NOT_IMPLEMENTED; multi-link complexity UNRESOLVED. Single-source prefix, inverse service clock and route delay theory are existing work, not new results here. The addition is profile-preserving view composition and explicit conservative multi-input merge / partition covariance. No global novelty claim.

## 1. Origin and current protected meaning

| Inspected source | Original purpose | Consequence |
|---|---|---|
| 049236458fdb5a7e327b0e494ab5f5cc3ad25b61:docs/PRD.md | Explainable roughly 100k city; generation → transport → accessibility → development; bulk mesoscopic transport | Fast transport need not store one vehicle object per resident. Demand, routes, effects and causal lag must survive. |
| Same:docs/TRAFFIC_DYNAMICS_DESIGN.md | Destination/path/behavior commodities; nonnegative stock; sending/receiving/storage; deterministic multirate update | Keep commodity information used by downstream constraints, units and conservation. |
| Same:docs/RESEARCH_SYNTHESIS.md | Only active trips in fast loop; explainability and delayed feedback; lane-level microscopic default deferred | Marked continuum profiles fit original intent. Materialized row count is not a scientific observable. |
| 65245008af2387a8ce56e72d54a198394de3eee2:memory/constitution.md | Immutable WorldState, units, replay, multirate scheduler, invalidation, baseline fallback | Immutable views are eligible; physical equivalence and exact replay remain separate obligations. |
| 3d83db01e9d028578de857ab66d98bf7964a5e3c:docs/research/ACTIVE_MESO_DESIGN_20261024.md | Destination-directed active agents reduced to stopped/moving cohort mass without pairwise/per-car tracking | Vehicle-equivalent mass is a measure. Preserve class, destination and finite-response meaning. |

Active-meso uses real mass and frozen-rate two-state dynamics:
\[
\dot f_1=\alpha f_0-\beta f_1,\qquad \dot f_0=-\dot f_1.
\]
Its early reduction explicitly loses individual history/lane micro-FIFO. Later PacketNetwork strengthens packet order; the earlier limitation is not permission to discard today's contract.

Baseline docs/v1/PLAN.json version 1.1.26 selects PacketNetwork. C_IDENTITY separates bytes from physical equivalence; C_EQUIVALENCE requires a defined quotient and observable factorization; C_OBSERVATION separates first moments and incomplete populations. V03 gates remain unchanged.

Baseline docs/v1/t04/TRANSPORT_KO.md and docs/research/symmetry_observables_20261025/TRAFFIC_KO.md require exchangeable mixing on the same boundary interval, FIFO across historical intervals, proportional partial-head service, original birth moments and observation IDs without physical priority. Birth first moments alone do not identify microscopic birth distributions or p95.

Native correspondence at baseline crates/metroflow-rust/src/v1_road.rs:
- Part stores tag, route offset, mass, birth and boundary endpoints; Packet stores target and Parts.
- Readiness uses Motion::passage(target minus shared displacement).
- Incoming target equals updated shared displacement plus fixed group length; all packets entering at the same numerical boundary share it.
- With fixed positive length and nonnegative displacement, targets are nondecreasing across admission.
- interval_packets preserves incoming time-boundary changes. A rank representation must preserve equivalent time/readiness information.

A rank profile can retain active-meso shared-motion meaning. It does not replace finite-response motion or establish that motion correct.

## 2. Prior routes: attribution, not reinvention

| Existing route | Evidence | Limited conclusion |
|---|---|---|
| Constant composition plus scalar mass; proportional neighboring merge | artifacts/v1_v03_workspace_20261117/ATTRIBUTION_KO.md | About 1.01–1.08× packet reduction in tested samples; different heads interleave. Not a new proposal. |
| Bit-identical Part/key and interval-density merge | Same attribution | Existing same-key combination; equal density uncommon. Exact operation/wire preservation remains distinct. |
| Ordered cohort mass/birth prefix | docs/research/V03_FIFO_COHORT_MOMENT_R1_R10_C1_C10_20261121_KO.md | Prefix definitions below are inherited. |
| Time-dependent service, inverse exit clock, route delay | docs/research/V03_DYNAMIC_FIFO_AGE_R1_R10_C1_C10_20261122_KO.md, R3–R5 | \(N_r(s),H_r(s),T(z)\) and \(\int[T(z)p_r(z)-b_r(z)]dz\) already exist. |
| Source-fixed censored quantiles / clock stability | docs/research/V03_FIFO_QUANTILE_SOURCE_INDEX_R1_R10_20261122_KO.md | Observer alone neither fixes row growth nor reconstructs unavailable microscopic births. |
| Native actual-owner resource accounting | Prior V03 stages/current source | Real implementation repair, distinct from transport-state reformulation. |

The 20261117 attribution reports 25,600→25,650 partial-head service adding about 7.21M rows and interval splitting about 2.07M. Packet count rises roughly 21k→210k from 25,450→25,650 while head width is roughly stable. This identifies repeated materialization as a target. It does not prove every exact representation must grow likewise. Guard-bypassed diagnostics are not accepted V03 executions; universal no-solution language is not adopted.

## 3. Heterogeneous profile-preserving rank views

Let \(z\in[0,A(t)]\) be cumulative admitted mass [veh] in selected FIFO order. Retain
\[
F_g(z)=\text{component mass in }[0,z],\quad
B_g(z)=\text{original birth moment in }[0,z].
\]
Units: \(F\) veh, \(B\) veh·s, \(F'\) dimensionless, \(B'\) s. Mark g includes route suffix, class and observations required by consumers. Keep readiness \(Y(z)\) [m] and boundary-time profile/breakpoints. F,B alone are not claimed sufficient for native state.

Within packet k:
\[
F'_g=m_{kg}/M_k,\qquad B'_g=b_{kg}/M_k.
\]
These are inherited prefix definitions. For admissible nondecreasing service \(D(t)\le A(t)\), queue state is restriction \([D(t),A(t)]\), while service \([d_0,d_1]\) emits
\[
\Delta m_g=F_g(d_1)-F_g(d_0),\quad
\Delta b_g=B_g(d_1)-B_g(d_0).
\]
This is proportional head service on each source interval.

**Structural proposition, DERIVED:** views \([a,b]\), \([b,c]\) of the same immutable profile parent can concatenate to \([a,c]\), retaining internal composition/time/readiness knots. Proportionality across b is unnecessary.

Proof: measure restrictions add because differences telescope. An event consumer stopping at all actual profile/readiness/node-law knots reproduces the same real-arithmetic prefix outputs for the same scalar service, by induction over appends and service events. Arbitrary solver rebatched service is not covered.

This differs from the old constant-composition merge: heterogeneous profiles remain inside the parent. It removes the representational requirement to copy all component rows on every cut. It does not erase semantic knots or prove native performance.

With shared displacement s [m], readiness is representable as
\[
R(t)=\sup\{z\le A(t):Y(z)\le s(t)\},\quad D(t)\le R(t).
\]
Parent finite-response work supplies s. This profile identity assumes no uniform positive speed.

## 4. Constructive multi-input merge lift

Existing fixed-source prefix theory does not itself specify downstream profiles from interleaving upstreams.

Domain: continuous piecewise-affine arrivals \(A_j(t)\), nonnegative rates, immutable profiles \(F_{jg},B_{jg}\), upstream FIFO, no route reassignment within merge. Same-boundary flux follows selected exchangeable mixing; all source-law knots remain. Atomic arrivals need an explicit tie convention and are absent from this example.

Define
\[
W(t)=\sum_j A_j(t),\quad C_g(t)=\sum_j F_{jg}(A_j(t)),\quad K_g(t)=\sum_j B_{jg}(A_j(t)).
\]
For generalized inverse \(\tau\) of W with consistent endpoints:
\[
F^{in}_g(z)=C_g(\tau(z)),\qquad B^{in}_g(z)=K_g(\tau(z)).
\]

**Proposition, DERIVED: conservation, causal upstream order and partition covariance.**
Where \(q=W'>0\),
\[
\frac{dF^{in}_g}{dz}=\frac{\sum_j q_jF'_{jg}(A_j)}{\sum_jq_j},\qquad
\frac{dB^{in}_g}{dz}=\frac{\sum_j q_jB'_{jg}(A_j)}{\sum_jq_j}.
\]
1. Fractions remain nonnegative and sum to one: \(\sum_gF^{in}_g(z)=z\). Component/birth increments sum upstream increments.
2. On a W plateau every nondecreasing \(A_j\) is constant; C,K are constant, so inverse ambiguity cannot change the measure.
3. \(A_j(\tau(z))\) is nondecreasing: downstream prefixes consume only upstream prefixes. This is upstream FIFO, not individual order among simultaneous fractions.
4. On constant-slope source intervals the resulting profile is affine. Numerical subdivision restricts that same measure; recombination telescopes. Actual source-law changes remain distinct. Partition covariance therefore does not license homogeneous averaging.

This supplies a positive construction: compose cumulative arrival maps, retain real profile knots and restrict the result for later service. Persistent expression DAGs could avoid repeated expansion. Multi-link expression growth and query cost remain open.

### Exact two-input example

Marks: (U:red,U:blue,V:red,V:blue). Birth clocks: (1,2,0,3) s. On t=[4,5], rates (1,0,1/4,3/4) veh/s; on [5,6], (0,2,1/4,3/4).

| Downstream rank [veh] | Mark masses [veh] | Birth moments [veh·s] |
|---|---|---|
| [0,2] | (1,0,1/4,3/4) | (1,0,0,9/4) |
| [2,5] | (0,2,1/4,3/4) | (0,4,0,9/4) |

Prefix 1 veh has masses (1/2,0,1/8,3/8), hence red \(5/8\). Global homogeneous composition gives \(3/10\); exact error \(13/40\) veh. Final totals alone fail to determine FIFO prefix composition.

The script compares two original intervals, six refined intervals at times (4,17/4,19/4,5,41/8,11/2,6), and direct cumulative inversion. All 408 mass/birth scalar comparisons at 51 ranks \(z=i/10\) agree; sampled upstream prefix order agrees. Algebra supplies the general proposition, not finite sample count.

## 5. Identity contracts

| Contract | Required invariant | Status |
|---|---|---|
| Native exact operation / bytes / wire | Original Part order, f64 arithmetic graph, checkpoint encoding | NOT ESTABLISHED. Prefix subtraction/reassociation can round differently. No V03 switch. |
| Real-arithmetic semantic profile | Same marked mass/birth/time/readiness and same scalar node service | DERIVED in declared domain; exact bounded checks pass. |
| Controlled profile coarsening | Explicit error measure and threshold for changed profiles | Different model. Counterexamples reject unqualified homogeneous averaging only. No coarsening adopted. |

Native equivalence cannot follow from symbolic algebra or equal final totals. Replacement requires complete consumer mapping, numerical stability/error contract, checkpoint decisions and original-source comparisons.

## 6. Executed calculation receipts

Primary: python3 artifacts/v03_constructive_remodel_20261123/rank_profile_exact.py.
- Exit 0; MODEL_RANK_RUN.txt stores command/stdout/stderr/process wall.
- Three heterogeneous profiles, ten 1s service windows, capacity 2 veh/s, two zero-service windows.
- Mutable proportional-head oracle and immutable profile restrictions agree in 70 scalar comparisons.
- Final mass (5,5) veh; birth (5/2,5/2) veh·s.
- Exit (701/16,2129/48) veh·s; residence (661/16,2009/48) veh·s.
- Eight nonzero views concatenate to [0,10], retaining three heterogeneous profiles; no proportional neighboring pair.
- Homogeneous first-prefix red error \(1/6\) veh.
- Internal wall 0.0006690550071652979 s, not a traffic benchmark.

Bounded second: python3 artifacts/v03_constructive_remodel_20261123/rank_merge_exact.py.
- Exit 0; MODEL_RANK_MERGE_RUN.txt stores command/stdout/stderr/process wall.
- Two upstreams, four marks; two true intervals versus six numerical subintervals.
- 51 query ranks, 408 exact mass/birth comparisons plus direct inversion.
- Final mass (1,2,1/2,3/2) veh; birth (1,4,0,9/2) veh·s.
- Internal wall 0.00556708499789238 s; no native performance interpretation.

Machine-readable results: MODEL_RANK_CALC.json and MODEL_RANK_MERGE_CALC.json, each binding source script SHA256.

## 7. First unresolved implication

Repeated multi-link merges may create many essential knots or large expression DAGs. Diverge turn fractions depend on local profile derivatives; their next change can alter weighted progressive filling. Ignoring knots changes physics; expanding all knots may recover current cost. This is the next implementation discriminator, not a hidden solved assumption.

Next bounded implementation: immutable views with exact prefix queries and semantic-knot iteration, consuming the same service events as a materialized oracle. Measure owners, queried knots, DAG depth and wall as cuts/merges increase; include nonproportional inputs. Fewer views must not be reported as fewer essential profile knots.

The candidate is orthogonal to the parent's finite-response stop-go model: that work constructs motion/readiness/service, this work transports conserved route/birth marks under those clocks. Joint conclusions require both hypotheses. No production edits by this child.

## 8. Origin drift watchdog

**ALIGNED_WITH_OPEN_OBLIGATION.** Preserved: bulk mesoscopic mass, destination/class, SI units, causal order, immutable-state meaning, conservation, original birth clocks, selected boundary exchangeability and lagged city feedback.

Historical correction: proportional sharing and single-source inverse-service theory are earlier work, explicitly credited. Addition: heterogeneous profile views and derived/calculated conservative multi-input merge with partition covariance.

Open: finite-response/network integration, f64/wire equivalence or versioned numerical contract, multi-link complexity, real100k experiments, 24h/RSS evidence. No readiness increment, timestep/cap/resident/matrix relaxation or completed blocker claim follows from these examples.

Surgical direction: address repeated materialization while preserving physical information, instead of interpreting another finite constant-factor gain as an all-day solution.

## 9. Inspected source identities

| Commit | Repository-relative path | Git blob |
|---|---|---|
| 049236458fdb5a7e327b0e494ab5f5cc3ad25b61 | docs/PRD.md | f8cc371410ca0e24b0947cda3d6772787efddc7a |
| Same | docs/RESEARCH_SYNTHESIS.md | 5f754d1061b965abafe46e92afebd324348c0390 |
| Same | docs/TRAFFIC_DYNAMICS_DESIGN.md | e76ce40b9f0d56c165cad042744ebf7e47cf8c04 |
| 65245008af2387a8ce56e72d54a198394de3eee2 | memory/constitution.md | 7c78e214c9558bcb1023854e55025f1c554aadee |
| 3d83db01e9d028578de857ab66d98bf7964a5e3c | docs/research/ACTIVE_MESO_DESIGN_20261024.md | 7809f9d5c8dcc9fc542fc668d4d34c059a0bde3a |
| Baseline90bfca2 | docs/v1/PLAN.json | 04be41e3f603a9d4be41cda53a2ebdb31da31f35 |
| Same | docs/v1/t04/TRANSPORT_KO.md | d3ce6ffa2585ca3a16f0bc8e7e65e269cf19ad31 |
| Same | docs/research/symmetry_observables_20261025/TRAFFIC_KO.md | 2e2011264dee7e223280146d4fbd9a3047e9b6d2 |
| Same | artifacts/v1_v03_workspace_20261117/ATTRIBUTION_KO.md | b12b9b699d29a333d6ae1b61211f76faf5d6a0b5 |
| Same | crates/metroflow-rust/src/v1_road.rs | 7ca09c394bf1afc174007c6eff66959eb46ef3eb |

External literature cited in historical notes was not reverified or used here for priority claims. The construction is self-contained.
