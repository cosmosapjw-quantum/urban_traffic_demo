# KCMB Adaptive FIFO · 코딩 C1–C10: 물리적 동등성·성능·수용 범위

기준일: 2026-11-19 (Asia/Seoul). 원래 V1 Release solver와 물리적으로 구별되는 **opt-in KCMB ordered route fluid** 연구단위. 권위 부모 커밋 `61c6c73a715b61a7fbcf91dc3b4528ba2ca6518a`. 연결 이론 `docs/research/KCMB_ADAPTIVE_FIFO_THEORY_R1_R10_20261119_KO.md` (먼저 원격에 게시한 theory 단계 `5e1b2c9df475806e1c80bc4480be326edea3bc63`).

## C1 목적·기준

이번 bounded objective는 **수학적으로 동등한 eligible FIFO run 분할에 따라 수송량이 달라지는 오류를 제거한 뒤, 잃어도 되는 순서정보만 축약**하는 것이다. 새로운 근사가 허용되지 않은 시간 binning, per-route temporal inversion, 수요 삭제, hidden fallback은 금지한다. 원래 V1/PR #41 및 `docs/v1/PLAN.json`은 건드리지 않는다. Original V03 3 cities × 3 repeats × 24h: `0/9 COMPLETED; BLOCKED`를 그대로 둔다.

## C2 Definition → equations → code

- Physical state per directed link-route `Y_ia=(m0,m1,j0,j1,z0,z1)` [veh] and ordered runs `(route_id,mass_veh,ready_tick)`.
- `KCMBClass` switching `alpha,nu[1/s]`, response `tau[s]`, route `U[m/s]`. Frozen local moment semigroup `Phi_dt` is unchanged.
- Sender `S_ia = min(M_ia, dt U_a/L_i × (j0+j1))` with per-link `sum_a S_ia ≤ C_i dt`.
- An incoming link's **maximal currently eligible homogeneous route prefix** `H_ia = Σ_{runs in head block} mass` defines competing node demand
  `d_ia = min(H_ia,S_ia_remaining,G_ia_remaining)`.
- Node weighted progressive filling enforces receiving `Σflow≤C_j dt` [veh] and `Σb_a flow≤R_j^m` [metres] from the **same pre-step state**. Actual allotted mass is removed from the FIFO prefix, oldest first.
- Coalescence uses only `run[k].route == run[k+1].route` and both `ready_tick≤current_tick`; sum masses and keep the older already-eligible timestamp. Never merge across route, future readiness, lane, physical law or ingress tie.
- Exact real-arithmetic statement and partition-invariant proof: theory R5:E2–E4. Float numerical allowance: existing `1e-12veh` max charged per tiny completion event, and bounded mass ledger tolerances.

## C3 numerical discretization and errors

The original six-moment exact-frozen generator and first-order finite-volume step remain unchanged. **The new change is an error in representing node candidate demand, not a new macroscopic PDE or invented kinetic law.**

The previous code's `min(first_run_mass, S_remaining, signal_budget)` made weighted merge priorities depend on run partition. Replace the first term by `Σ mass` over the full eligible contiguous SAME route prefix. Node completion removes flow from successive head runs. This is representation-invariant under the assumptions of theory E2. Branch/physics version changes from `kcmb_ordered_route_runs_v1` to `kcmb_ordered_route_runs_v2_eligible_prefix`; new adaptive checkpoint has `kcmb_adaptive_eligible_fifo_v1`. Old V1 physical solver never changes.

## C4 computational resource and execution path

Persistent state remains `O(6 N_links K_routes + 3K + 3 B)` representation elements with `B` user-selected run budget. In the adaptive mode, transient expanded run budget is `min(100000,B+max(8,min(10000,2N(K+1))))` and can produce an explicit fail-closed `FIFOQueueBudgetError` even if a hypothetical later compression could fit. This conservative guard prevents unbounded memory. The nonadaptive corrected reference remains available separately.

A formerly eligible run never becomes ineligible as time advances, so eligible homogeneous coalescence can be performed after all incoming source/node transfers. It preserves route output and original 6-moment physical observables; recording historical individual arrival timestamps is not part of the observation algebra.

## C5 executable feature

**Modified** `src/metroflow/v1/kcmb_ordered_fifo.py`: original opt-in ordered FIFO `step` now evaluates full eligible same-route head mass in node priority allocation and consumes it transactionally; updates model version. This source's original FIFO tests still run.

**New** `src/metroflow/v1/kcmb_adaptive_fifo.py`: `CertifiedAdaptiveFIFO`, `initial_profile`, `step`, `_coalesce`, strict persistent run budget, distinct model_id and JSON checkpoint/restore. Data invalidity and budget overflow fail without modifying the input snapshot. It can select Python or existing Rust native node allocator, but the overall ordered stepping loop remains Python.

**New** `tests/research/test_kcmb_partition_invariance_20261119.py`, `test_kcmb_adaptive_fifo_20261119.py` and `tools/research/bench_kcmb_adaptive_fifo.py`.

## C6 observed behavioral red–green

1. Merge with two incoming roads and one receiving road. **Same kinetic state, same route and readiness**, but A=2veh represented as one run or two runs. Parent code: (A,B)=(0.075,0.075) vs (0.042857142857,0.107142857143) veh/step at receiving cap 0.3veh/s and dt0.5s. The 8 combinations of Python/Rust node × 4 receiving caps failed before change; all passed after changing node candidate to eligible-prefix total.
2. Adaptive `CertifiedAdaptiveFIFO.step` was initially a behavioral NotImplementedError: 7 tests failed, then new implementation + source revision passed. Future-ready runs and mixed-route alternation do not merge.
3. Baseline `OrderedKCMBBoundedNetwork` and new certified representation are compared on identical topology, demand, signals, exact kin moments. Random signal parity, arbitrary splitting into three eligible segments, memory budget, checkpoint and 240-step mixed-route tests stay within numerical acceptance.
4. Source migration is versioned: previously posted old ordered model checkpoint identity differs from v2; adaptive checkpoints are not accepted by ordered model or vice versa.
5. One performance-only refactor removed redundant state checks and unnecessary object copies on no-op coalescence. No revised physics or behavior in this refactor; all focused regressions rerun.

## C7 physical and mathematical validation

- Kinetic `Y_ia` is identical under split/merge (6-component parent state). Class-specific external demand, pending, finished and physical metres cap unchanged.
- Current t eligible prefixes have the same total mass for any segmentation; local weighted junction solver sees identical count/metres requests and priorities; by finite node-round induction, receives/turn outputs agree. Coalescence only changes redundant READY labels for adjacent same-route runs, so future event/flux observables remain identical.
- Alternating A/B micro order is strictly preserved: the user-provided route-level spatial order changes turn output in red-vs-green experiment, and compression does not confuse them. Temporal source pending before admission and within-tick per-vehicle event order are **not reconstructed**.
- Strict maximum memory is conditional: when the ordered sequence of different routes exceeds B, output is blocked rather than approximated. This does not prove full city throughput or actual microscopic safety.

## C8 matched-resource benchmark, five repetitions

**Matched scenario (both algorithms solve corrected FIFO v2 physics):** homogeneous 1-route road, length 1000m, dt1s, 320 steps, 240 arrivals of 0.1 vehicle each, initial red output followed by green; and negative-control alternating A/B route scenario 280 steps. Observed numerical state and every route-turn flux agreed exactly (maximum difference 0 in serialized reference test). Each backend comparison alternates within-tick execution order; five repeat processes alternate Python/Rust process order.

| Scenario | Backend | Ordered/Adaptive total-step speed ratio, median of 5 | Peak runs (old/new) |
|---|---|---:|---|
| Homogeneous backlog | Python-node | 1.0593× | 240/101 |
| Homogeneous backlog | Rust-node | 1.0628× | 240/101 |
| Alternating routes | Python-node | 0.9519× | 279/279 |
| Alternating routes | Rust-node | 0.9435× | 279/279 |

Homogeneous maximum run count reduction `(240-101)/240=57.9%`; sampled peak checkpoint bytes from 9,895 to 4,373 (55.8% reduction). Alternating negative-control yields no run reduction and a 5–6% time overhead. No correctness/latency benefit is asserted when no coalescence is possible.

**Interpretation:** This yields a genuine **localized memory and modest CPU benefit** under long homogeneous queues, not universal speed improvement; a limited site can be slower. It is measured on a same-physics KCMB fixture, not the original packet V1, original 100k demand campaign, or measured traffic. Original V03 24h acceptance remains NOT_RUN/BLOCKED. Under `max_runs=B`, baseline could overflow while adaptive continues only in cases of certified redundant eligible runs; alternating routes still fail closed.

## C9 finite adversarial review

- **S1 mathematical:** coalescence across different route, ready_tick in future, lane geometry or class law invalidates proof. Code skips these; tests assert source red/green inversion remains.
- **S2 implementation:** physically same prefix with 2+ fragments previously changed junction priority. Corrected in opt-in ordered source; physical version bumped and regression added.
- **S3 numerical:** aggregate prefix floating sum, repeated physical allocation, and small completion charges can differ by rounding; all scope assertions use explicit mass tolerance and receipt. The test checks quantitative physical observables, not byte identity.
- **S4 resources:** expanded transient state must not be silently written through capped persistent checkpoint. The adapter checks both with typed failure and unchanged checkpoint. Performance trade-off was empirically measured including negative case.
- **S5 observational:** only deterministic route-linked KCM moment/flux observables. Real per-vehicle motion, turn-pocket geometry, entropy/invariant-node, LWR convergence for full network and field-data calibration remain NOT_MEASURED or UNRESOLVED.

## C10 decision and next implementation stage

`SCOPED_ADAPTIVE_FIFO_CERTIFIED_FOR_DECLARED_OBSERVABLES` if final selected regression and numerical/provenance receipts PASS. `NOT_V03_RELEASE`, `NOT_EMPIRICALLY_VALIDATED`. Native subagent capability unavailable in this host; direct tool serial implementation, source diff and independent tests only, no simulated delegation.

Next useful bounded work: partition the real road map into physical turning pockets and mixed-lane sections; enable adaptive compression only under declared lane topology and measured queue-order relevance. Compare original V1 vs KCMB only on carefully matched observables, not byte-exact physical identity. Use matched observed inD/UTD19 data, explicitly calibrated map-match/time windows, then cross-day holdout. Do not inflate the DAG or repeat full earlier audits.

Stage release: previous audit–theory–coding–network–ordered commits were separately pushed with exact GitHub SHA readback. This theory R1–R10 at `5e1b2c9...`, coding C1–C5 at `8dcff047...` are already pushed; C6–C10 receipt and final report commit are pushed after successful final tests. No PR merge, push to main or release-tag mutation.
