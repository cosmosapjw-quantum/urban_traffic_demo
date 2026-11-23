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
