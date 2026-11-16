# Exact road-part growth: bounded next implementation

Status: code-derived analysis and measured `event_probe.json` plus the complete
`PART_LINEAGE_PROBE.json` checkpoint inspection by `INSPECT_PART_LINEAGE.py`. This is not a new physical
approximation, a successful full campaign, or permission to prune small masses.

## Observed state at 25,490 s

Source: `event_probe.json`, checkpoint SHA256
`d5d584ed47a9af4e2a77cedacf04c0b45a6899f9e534e2a76579ecc2e16bae6b`.
The probe stops at a numerical event-clock failure, not a memory-budget failure.

| Quantity | Measured value |
|---|---:|
| Journey entering / egress / internal / receipts | 2,165,555 / 275,061 / 66,692 / 168,819 |
| Journey dynamic storage estimate | 105,427,864 bytes |
| Road cell parts / packets | 2,313,316 / 45,715 |
| Road pending parts | 0 |
| Road Vec storage | 149,731,056 bytes |
| Service last-event rows | 795,851 |
| Road active vehicle mass | 362.615641633314 |
| Entering atoms generated / emitted in attempted tick | 158,000 / 141,712 |
| Road-step fraction of summed phase wall time | 83.3686798% |
| Peak process RSS | 1,085,800,448 bytes |

The road contains 50.603 parts per packet on average. Its mean mass per part is
approximately 0.00015675145 vehicles. These are finite-volume population
fractions, not millions of individual vehicles. Their size is not a criterion
for deleting them. The failing event still contains a positive mass
2.9421244717235964e-16; the separate event-clock correction owns that failure.

## Where rows arise and where equality is already used

`NativeJourneyCore::prepare` constructs each released leg/window increment in
original leg order, then one access row per declared law atom. Birth, delay and
weight participate in different readiness predicates. Equal leg identity alone
does not make these rows interchangeable. The persistent stage implementation
shares storage and skips wholly future blocks; it retains every logical row.

When ready rows become road offers, `V1Road::step_state` groups them by entrance,
then `combine` already combines exact `(tag, offset, a_bits, b_bits)` keys with
the original stable `fsum` order for both mass and birth first moment. Whole
journey source offers carry `None, None` entry intervals. Therefore many source
law atoms for one tag emitted in the same tick are already reduced at the road
entrance. The number 141,712 emitted stage atoms is not the number of distinct
new road parts after this reduction. That post-combine source count is not
present in the current JSON and must not be invented from it.

Inside a junction event, `portion` emits a served copy and, for partial service,
a remainder for every positive head part. The served copy receives that event's
entry interval. Different service intervals are distinct keys in `combine`.
Subsequently `interval_packets` collects all incoming interval endpoints. For
every consecutive endpoint pair it copies each covering part and evaluates
`mass * (b-a) / (pb-pa)` and the same expression for birth moment. This is an
explicit common refinement of overlapping intervals. Its output count is the
sum of coverage multiplicities across endpoint spans; it can greatly exceed
the incoming part count even when all keys are distinct. Both this refinement
and repeated partial service can increase route/offset recurrence downstream.

The existing exact-key combination therefore rules out the simple hypothesis
that all road growth is an uncollected list of identical source atoms. It does
not establish that the measured checkpoint has no duplicate rows: the streaming
inspector measures full-row duplicates within packets, across packets, and with
packet target included separately. A repeated tag/offset across packets is not
permission to merge: FIFO position, target, entry intervals and floating-point
operation history can differ.

## Small exact storage changes, ranked by implementation risk

1. **Pack optional finite entry times.** On the observed x86-64 target, `Part`
   contains four 8-byte scalar fields and two 16-byte `Option<f64>` fields:
   64 bytes. Valid entry times are finite and nonnegative (including a possible
   negative-zero bit pattern), so an otherwise invalid NaN bit pattern can
   represent `None` in an 8-byte wrapper without changing any valid time bits.
   A 48-byte part would save exactly 16 bytes per stored capacity row: 37,013,056
   bytes at this checkpoint, before any clone/work-buffer savings. The old
   optional-field codec can remain byte-for-byte unchanged. This is the
   smallest general representation change if the next run reaches the quota.
   Constructors/restores must reject invalid `Some(NaN/Inf)` before packing;
   comparisons must retain `Option<f64>` numeric equality/ordering, including
   `+0 == -0`, while combination keys keep the original raw bits. Deriving
   bitwise equality for the wrapper would be a semantic bug.

2. **Hoist one exact entry interval into each homogeneous packet.** In a whole
   engine run from empty state with entry intervals enabled, every packet
   produced by `interval_packets` has one common point or span. `portion`
   preserves that property. Source admission creates one common `(end,end)`
   point. Thus stored packet rows can use `(tag,offset,mass,birth)` while their
   interval is stored once. The inspector measured a 100% common-interval
   ratio in this checkpoint. The row payload saving is 74,026,112
   bytes before extra packet headers; a simple 24-byte extra header gives an
   indicative net 72,928,952 bytes. This is a layout estimate, not a measured
   compiled representation. Legacy restore accepts heterogeneous packets, so
   it needs an exact mixed-row fallback. Iterators must expose the same original
   row order and f64 values without expanding all rows into another hot-path
   allocation. Arithmetic and reduction order remain unchanged.

3. **Share immutable packet payloads between snapshots and unchanged survivors.**
   `clone_packet` currently copies every part in motion prediction and snapshot
   paths. An immutable shared payload can avoid copies when a packet is neither
   served nor changed. This reduces transient memory and copying, but does not
   reduce logical interval multiplicity. It should be measured separately from
   packed fields, with known input-snapshot lifetime included in byte guards.

These changes improve storage of the existing rows. They do not prove that an
entire day fits the fixed resource ceiling. Packing optional times alone gives
only a constant-factor improvement. If interval multiplicity remains the actual
limiter, a shared interval/template representation is the larger next step.

## Why deferred interval templates are not a trivial algebraic rewrite

A template could reference the original incoming rows plus an interval slice
instead of materializing each span. However, each row's binary64 result must be
reconstructed with the original `(mass * width) / original_width` operations.
Replacing them by `mass * (width/original_width)`, combining later scaling
factors, or deriving a mass from cumulative fractions can change rounding.
Partial service then applies further ordered multiplications to the already
rounded split mass and birth moment. Exact replay needs either stored resulting
scalars or an expression history that replays every operation in order. Stable
output iteration and every original `fsum` input sequence also remain required.
This larger representation is therefore not yet implementation-verified and
should not precede the concrete whole-run quota/timing evidence.

## Required checks for an implemented representation change

Use the occupied legacy checkpoint as the interchange baseline; compare saved
bytes, per-event output, complete scientific reports, and 1/2/4-worker restart
results. Include heterogeneous restored packets, `None` and finite intervals,
negative zero, same-tag distinct times, partial service and malformed optional
times. Recompute byte guards using actual compiled sizes and buffer capacities.
Retain raw logical part counts and failure checkpoints. Do not substitute lower
reported record counts for lower allocated storage.

## Completed streaming inspection

The actual host inspected all 312,081,652 checkpoint bytes in 11.925 s. Its SHA256
matches the probe's saved checkpoint exactly. All capped key sets remained
complete, so the following duplicate counts are exact for their stated scope.

| Observation | Result |
|---|---:|
| Packets with bit-identical common intervals | 45,715 / 45,715 |
| Mixed-interval packets | 0 |
| Duplicate exact combine keys inside packets | 0 |
| Duplicate complete part rows inside packets | 0 |
| Duplicate complete part rows across packets in the same cell | 0 |
| Duplicate complete part rows plus identical target in the same cell | 0 |
| Distinct `(tag,offset)` keys, summed per cell | 413,104 |
| Further rows repeating a cell's `(tag,offset)` | 1,900,212 (82.1423%) |
| Adjacent packets with bit-identical targets | 42,863 |
| Point-interval / positive-width-interval parts | 222,642 / 2,090,674 |
| Road rows with mass below 1e-12 | 861,262 (37.2306%) |
| Total mass of those small road rows | 2.676333772448689e-8 vehicles |

There are no entering-stage rows with mass below 1e-8 at this checkpoint, while
small downstream fractions are numerous. This supports downstream splitting as
the practical growth mechanism. It is not a complete trace of every historical
source offer and does not identify each small fraction's exact ancestor. The
inspection found 21,807 duplicate full rows within contiguous internal-stage
leg/birth groups and 24 in egress, but zero in entering. These internal duplicates
can be legitimate repeated law atoms: collapsing their repeated additions into
one multiplied mass would change the original completion/receipt sequence. They
are also too small a share of total storage to explain the road growth.

An exact deduplication pass on road full rows would therefore save nothing in
this checkpoint. The common-interval field repetition, however, is present in
every packet and can be removed from storage without merging any logical row.

## Equal targets do not justify merging packet boundaries

The measured 42,863 equal-target adjacencies are a consequence of several entry
interval packets being placed at the same cell target in one tick. The future
solver still processes them in FIFO order. At least three distinctions survive:

1. Different head destination/class mixtures give different node rates. Merging
   the mixtures introduces later destinations into the current FIFO head.
2. Even identical mixtures can create different head-depletion event boundaries.
   Current downstream marks sample motion speed and latent state at each
   event's midpoint. These samples are nonlinear functions of time.
3. Original served and remainder masses, first moments, free/storage debits,
   reductions, and event rows are evaluated in the original event order.
   Merging changes that floating-point computation even in a degenerate case
   where continuous-flow totals agree in real arithmetic.

For the second distinction, use the implemented latent form
`p(t)=p_star+(p0-p_star)*exp(-lambda*t)`. Two consecutive equal-mass heads served
at the same constant rate over `[0,1]` and `[1,2]` sample `p(0.5)` and `p(1.5)`.
A merged head samples `p(1)`. For `p0=0`, `p_star=1`, `lambda=1`, the two-head
weighted latent is 0.5851695900694684 and the merged value is
0.6321205588285577. The difference 0.04695096875908922 is a real-arithmetic
quadrature difference, not a reassociation error that can be presumed within
the old numerical tolerance. This independently evaluated formula is recorded
in `PART_LINEAGE_SUMMARY.json`; it is not represented as a full road-run test.

Consequently neither equal targets nor proportional route mixtures establish
general future-kernel equivalence. A safe factorization must retain the original
packet boundaries, per-packet row sequence and event depletion schedule.

## What consumes stored entry intervals

| Consumer | Use of existing `a,b` |
|---|---|
| `combine` | Exact bit-key grouping and canonical order |
| `interval_packets` | Incoming endpoints, interval coverage, original split multiplications/divisions |
| Motion, occupancy, distance, node-rate calculation | No direct use; these read target, ordered heads, tag/class, mass and cell state |
| `portion` | Copies existing interval metadata while multiplying mass and birth in order |
| Forward road transfer with intervals enabled | Replaces old metadata by the new event's start/end |
| Source admission with intervals enabled | Replaces metadata by the admission `(end,end)` point |
| Checkpoint validation, serialization and legacy snapshot | Observes and preserves the original optional values |

This permits the following bounded representation change after the smaller
packed-option step: keep `Part` as the transient split/combine type, but store
packets using `Uniform { interval, rows: Vec<CorePart> }` or
`Mixed(Vec<Part>)`. `CorePart` contains the unchanged tag, offset, mass and birth.
The iterator yields the same part values by value; it does not allocate an
expanded vector. `Packet::from_parts` selects uniform storage only when both
optional interval bit patterns are identical, preserving signed-zero bits.
The mixed variant keeps every legacy restored packet valid. Packet boundaries
and row count/order do not change. The split/combine implementation can remain
on the existing transient part type.

The equivalence argument is representation-level: decoding each stored row
returns exactly its previous field bits; each arithmetic kernel receives the
same ordered arguments and executes the same operations and branches. It does
not appeal to floating-point associativity or model tolerances. Allocation
failure thresholds and storage diagnostics deliberately change to the actual
new layout. A compiled implementation and occupied-checkpoint replay are still
required before claiming implementation-verified equivalence.

The next actual probe, `numeric_resume_t1.json`, reached 25,520 s and stopped at
`entry interval split`: required 1,342,245,688 bytes against the road's assigned
1,342,231,185-byte structural quota, with measured process RSS 1,585,893,376
bytes. That is distinct from exhausting the global 8-GiB process ceiling. The
fixed road/journey quota split and conservative workspace charge need to be
reported as implementation policy; any reallocation must keep the total bound
and concurrent-owner accounting explicit.
