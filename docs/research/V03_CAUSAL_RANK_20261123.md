# MetroFlow V03: causal FIFO rank and actual preparation, 2026-11-23

## Scope and source
Current user authorizes ten interleaved theory/coding stages, a push after each,
constructive theory and implementation that remove real blockers, increasing
physical experiments, surgical model revision and a historical drift watchdog.
Base: `606b3ac6a899ba5b8b9ac064d82f609c7ff6cadf`;
remote `cosmosapjw-quantum/urban_traffic_demo`.
Working branch: `research/v03-causal-rank-20261123`.
Original root `0492364` PRD/spec and `6524500` constitution are historical
motivation; `docs/v1/PLAN.json` is the current execution authority.
No main merge, final acceptance or release is included.

## Stage 1 — baseline and drift boundary
Observed remote head equals the base commit. Existing source worktrees contain
unrelated edits and large untracked evidence, so this work uses an isolated
worktree. Baseline current-source uninterrupted Valley weekday seed7 100k prefix:
25650→25700 s (50 s), then `road_work:packet interval packing` rejects 25710 s.
Receipt: `artifacts/v03_weighted_fifo_20261121/C8_100K_REQUESTED_80S_FROM_25650.json`.
Required 4,940,342,832 B versus allowed 4,939,690,935 B.
Previous valid binary: 3,405,043,386 B, SHA256
`ac7a209c6adfd594c791d1ac4b5b33c6e013ae73b7b594e42121115c89bd8369`.
This is an older-start checkpoint continuation, not current-source time-zero
execution and not a completed city day.

Official denominator remains 21: 19 ACCEPTED/VERIFIED_SCOPED, 5 ACCEPTED,
V03 direct predecessors 3/3, historical current-source calendar preparation 3/3,
full original day runs 0/9. New research steps never increment V1 DAG counts.
The prepared inputs must be rebound after runtime source changes.

Original motivation: explain city topology→traffic→accessibility→lagged land-use
feedback for 100k resident stock, with temporal demand, heterogeneous purposes and
classes, bottlenecks, possible induced demand and Braess effects.
Protect mass/person/cargo accounting, FIFO/causal information, finite response,
explicit SI time/rate units, immutable checkpoints and original full demand.
Retain 8 GiB / 7200 s, original three cases and numerical tolerances.
A new representation must state whether it is byte-identical, scientifically
equivalent under stated assumptions, or a controlled approximation.

Drift observation: repeated exact constant-factor packing changes advanced only a
short congested prefix while logical parts reached 34,610,422 for ~1234 active
vehicles. This justifies examining a cumulative-rank measure representation.
It does not prove exact compression impossible. The old PLAN next-action text
predates subsequent evidence and will receive a narrow factual correction.

## Ten integrated stages and concrete outputs
1. Baseline, original-motivation comparison, isolated source and experiment limits.
2. Source diagnosis plus constructive cumulative-rank equations and falsifier.
3. Exact partial-remainder lifetime repair and behavioral red/green tests.
4. Original 25710 physical continuation, actual resource/ledger evidence.
5. Constructive FIFO cumulative-measure theorem and executable representation.
6. Nontrivial network/finite-response examples and implementation integration.
7. Increasing-duration experiments and measured scaling at matched observables.
8. Numerical convergence/replay and current full-input prerequisites.
9. One independent mathematical/implementation review and targeted corrections.
10. Source-bound readiness, drift assessment, reproducible handoff and final push.

At each stage append actual proof/commands/results below. Failed runs remain
failed; elapsed requested duration is never counted as completed physics.
Native subagents are actually dispatched for history, runtime diagnosis/repair
and constructive theory; shared source and publications remain parent-owned.
One bounded independent review pass is reserved for the integrated result.

## Resources
Observed workstation 5900X, ~31.25 GiB physical RAM, ~12 GiB available during
baseline, 6.8 GiB free on root filesystem. Do not run two large physics jobs in
parallel or delete historical checkpoints. Avoid duplicate 3.4 GiB files; use a
streaming/atomic checkpoint strategy when extending. Build/test jobs remain
bounded and scoped; full-repository CI stays deferred by existing user policy.

## Stage 2 — actual source lifetime and constructive FIFO coordinate
Source diagnosis at base606b3ac: `pack_parts_with_live_descriptors` is called
by road-head remainder (v1_road.rs:3925) and pending remainder (:4063), both
before the first `combine_chunked_parts` (:4117). Its call to generic
`pack_parts` (:967) reintroduces the future combine reserve under label
`packet interval packing`. Thus the failing label is not evidence that the
interval sweep is live. Correct only these two remainder call sites.
Charge the actual raw Part Vec capacity AND new packed CorePart allocation;
retain the full reserve for real interval/sweep/cell phases. The old maximum
cell has 1,410,562 rows, hence future scratch = 2*48*1,410,562 =
135,413,952 B. No byte cap or physical formula changes.

A three-case behavioral RED was run using the existing packing API before
production edits: actual admission refused, exact raw+packed boundary refused,
Mixed fallback did not charge raw buffer. It compiled and exited101 (0/3);
this is a behavioral failure, not a missing-symbol test. Full log retained
outside the repo until the source/results are committed together in stage3.

Constructive coordinate (under development): for a FIFO entrance measure with
cumulative vehicle rank u in [0,A(t)], let p_c(u)>=0, sum_c p_c(u)=1 denote
route/class fractions and b_c(u) birth-time density. Define
M_c(q)=integral_0^q p_c(u) du and B_c(q)=integral_0^q b_c(u) du.
If departures D(t) are nondecreasing with D(t)<=E(t)<=A(t), where E is the
finite-motion eligible rank frontier, service on [t0,t1] reads
M_c(D(t1))-M_c(D(t0)) and B_c(D(t1))-B_c(D(t0)).
These differences telescope across arbitrary service subdivisions; physical
FIFO is the prefix restriction, not the list of historical split operations.
The representation retains ordered piecewise composition, unlike a global
moment closure. Immutable prefix blocks and a cursor can preserve exact
specified piecewise densities while keeping stored rows independent of the
number of subdivisions. Floating arithmetic and general network junction
sensitivity remain separate obligations.

Original-history audit read root0492364 PRD/spec/design and6524500 constitution:
the target is explanatory map–traffic–accessibility–lagged-development coupling,
not a mandate for one specific packet array layout or every IEEE sum order.
Current PLAN already distinguishes physical equivalence from byte identity.
This turn's authorized model revision therefore permits an explicit alternative
with its own error/validity domain, preserving the original solver as reference.
No new alternative counts as original V03 day evidence.

WolframLanguage independently evaluated integral_a^b x dx-(b-a)(a+b)/2 to0.
WolframContext returned internal error; no result was inferred from that call.

## Stage 3 — exact source remainder repair
Dedicated source-remainder preflight excludes only future combine scratch while
charging real raw capacity plus packed allocation. Mixed fallback is checked too.
Actual behavioral RED exit101 (0 passed/3 failed), identical GREEN exit0 (3/3),
source road regression exit0 (105 passed, 2 existing ignored benchmarks).
Parent reviewed the complete diff; true interval/split guards remain unchanged.
Verbatim checks: artifacts/v03_causal_rank_20261123/S03_remainder_red_green.log.
No original 25710 advancement is claimed until stage4 actually executes it.

## Stage 4 — original 100k falsifier and route revision
Built release binary successfully; 45 original native Python tests passed.
Current binary restored original25700 state, matched its full3,405,043,386-byte
wire hash and all three ledgers. The previous source-remainder packing guard
was crossed, but the next transfer guard rejects required5,025,270,048B versus
allowed5,025,214,575B. Actual additional physical time=0s, not10s.
Wall53.444211534s, peakRSS4,331,716,608B. V03 remains19/21 and0/9.
This falsifies the sufficiency of the lifetime repair for a complete tick.
It motivates actual representation reduction rather than another arbitrary
guard credit: common event times and immutable head compositions are candidates.
Reusable runner tools/research/run_v03_prefix.py keeps full matrix and source
bindings, reports partial native ticks, and hashes native checkpoint wire
through a FIFO; optional lossless gzip saves disk without changing wire bytes.
Result: artifacts/v03_causal_rank_20261123/S04_original_continuation.json.

## Stage 5 — constructive conservation/causality and controlled closure
Proved source-aligned rank-cursor equivalence over real/rational arithmetic,
per-tag mass/birth conservation and causal eligibility Q<=E<=M.
Proved sharp block commodity-prefix error h*p*(1-p)<=h/4; fixed blocks of
mass<=delta give delta/4 prefix and delta/2 interval error independent of
service subdivision count. Birth first-moment error is h*range(birth)/4.
The bound is for fixed service, not coupled city trajectory or instantaneous
head rates. Finite-response common-speed eligibility remains an explicit
physical law; global LWR replacement is not assumed. Full proofs and original
source mapping: V03_CAUSAL_FIFO_THEOREMS_20261123.md.
Actual exact-rational checks: 3000 source split identities and20480 binary-profile
prefix checks, sharp equality witness, stopped eligibility rejection, exit0.
The previous unary lineage shadow was re-read and is explicitly reused as prior
art; a generic lazy DAG is not presented as a new result.

## Stage 6 — exact event-time carrier and optional rank adapter
Implemented actual transient event compression:32B row payload plus one16B
bit-preserving time pair per consecutive run, both in4096-slot pages.
For N rows and K time runs, payload=32B*ceil(N/B)+16B*ceil(K/B),B=4096.
Both descriptor vectors and carrier metadata are charged; total descriptors
can be larger for all-distinct times, so only payload nonincrease is universal.
All input/current service history owners remain charged. Source event order,
mass/birth arithmetic, signed-zero times and checkpoint wire are unchanged.
Fresh review detected old96B metadata allowances below the new120B carrier;
corrected source envelope to actualsizeof and flatten to120+24=144B.
Behavioral RED/GREEN cover time-run allocation, bit reconstruction, input/current
history ownership and zero-row metadata. Final scoped Rust111passed,2existing
ignored; Python45native tests and19rank/sampler tests passed. Release build
exit0; copied native binarySHA25622a7cebc751b575521a8360ab7e235aa7fa6fa9e4d54c8ac8904b35e708ae57a.

Optional src/metroflow/v1/fifo_rank.py implements immutable shared-root rank
spans, exactFraction and separately labelled collapsedbinary64 arithmetic,
explicit eligibility and precision failures. It is not wired into native
production. New rows are materialized only by explicit iteration. Actual
complete source heads at25700 were extracted from the SHA-bound native
checkpoint:464,454,442rows, cells466,908,751. Future split fractions remain
an explicitly designed local experiment, not observed native history.

Background theory now includes fixed-service causal transport stability:
D_E(t)=C(t)+inf_(s<=t)(E(s)-C(s)), and ||D_E-D_Etilde||inf<=epsilon for the
same externally fixed C in an initially empty work-conserving fluid server.
Composition output error is at mostepsilon+delta/4 on a shared mass domain.
Actual exact-rational tests:96arrival-pair cases,193independent queue-balance
matches,4077exact output breakpoints, interior drain kink at3/2, changed-C
negative control. Head-dependent junction/network feedback remains unproved.
The proof review also corrected the block-count construction (delta grid plus
bounded mandatory boundaries), empty eligibility, actual source readiness
1e-10s tolerance and executed clamp/snap fraction conventions. These are
mathematical/source corrections, not relaxed V03 acceptance thresholds.

## Stage 7 — actual failure progression and increasing source-head workload
Clean stage6 binary restored original25700 checkpoint and reproduced full wire
and ledger exactly. The actual road transfer emitted17,429,035rows in206,999
exact time runs: carrierpayload561,184,768B,275,578,880B less than former48B
row pages. All258,538transfer guards passed. The subsequent indexed sweep
preflight still rejects5,051,633,256B against5,025,214,575B (excess26,418,681B).
Actual physical advance remains0s; wall55.979972184s,RSS4,324,171,776B.
This resolves the previous transfer-candidate refusal, not the entire25710tick.
No further speculative guard-credit adjustment follows this failure.
Receipt:S07_original_continuation.json. The full timezero run is the next
experiment, to establish source-bound physical horizons rather than relying
only on historical checkpoint continuation.

Original complete464-row head, synthetic half-service schedule, retained one
immutable snapshot per1000splits, Pythontracemalloc active for BOTH methods:
|Splits|Eager wall s|Rank wall s|Eager peak B|Rank peak B|
|---:|---:|---:|---:|---:|
|1000|0.476278680|0.019890662|105540|54092|
|10000|5.004362372|0.177857678|577916|54908|
|100000|50.654629108|1.748325649|5301132|62844|
At100k maximum per-key mass difference1.249174375e-14vehicle units; birth
first-moment difference1.990514420e-10vehicle-seconds. All three levels satisfy
explicit adapter checks. These are not the city's residence acceptance test.
100k eager constructs46,400,464row payloads; rankservice creates0newrowpayloads
and shares the actual source, then explicitly expands final rows. Incremental
tracemalloc excludes the common source root; timings include instrumentation.
The native physics run and this small Python microbenchmark overlapped; ratios
are descriptive scoped measurements, not uncontended native speed forecasts.
The result constructs a solution to repeated-remainder materialization for a
fixed source head, while native merge/head consumers remain a separate step.
