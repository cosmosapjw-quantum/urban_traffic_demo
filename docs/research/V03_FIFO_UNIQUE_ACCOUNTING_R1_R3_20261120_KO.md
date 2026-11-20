# V03-FIFO-UNIQUE-ACCOUNTING-01: source-locked theory and code

Parent SHA c76e4712bac41b8c089844c842bc6ce55c782501; isolated research/v03-fifo-unique-accounting-20261120 branch. Authority docs/v1/PLAN.json v1.1.26, unchanged original main, PR41 and physical model. Release: 100000 residents/city, 86400s/day, 3 cities x3 repetitions, 8GiB process cap, original internal road-work cap 5242806391 bytes, 10s step. No fitted coefficients or reduction of original transport demand.

## R1. Exact measured failure and hypotheses

Original source crates/metroflow-rust/src/v1_road.rs: PacketParts Uniform holds Arc<Vec<CorePart>>; Mixed holds Arc<Vec<Part>>. RoadState::debug_stats counts packet.parts.allocated_bytes once PER OWNER even if Arc owners share the identical allocation. The work-budget formula charges max(retained current, retained input) times 3, plus event, incoming, retained/transient interval and extra. Thus owner-counted bytes may conservatively overestimate physical retained backing, but the original work budget also needs headroom for other live states and scratch.

Source-locked actual 100k Valley 25600->25650 tests from the same initial checkpoint SHA 75bae0ea200a0bd3fd0842770efd0cecec9ce6297179149db88f77ded91b134d:
- old non-Arc FAILED_BudgetExceeded: native required 5242810432, budget 5242806391, excess 4041 bytes; peak RSS 3640336384 bytes and elapsed 52.976s.
- Arc FAILED_BudgetExceeded: required 5242811264, same budget, excess 4873 bytes; peak RSS 3273211904 bytes and elapsed 53.127s.
Neither reached 25650, so checkpoint/ledger at 25650 unverified. Actual process RSS did not exceed 8GiB. Hypotheses to discriminate: duplicated Arc owners inflate a particular structural estimate; packet genealogy creates distinct allocations anyway; scratch/events dominate; and crossing a conservative internal bound is distinct from actual system OOM.

## R2. Exact unique allocation accounting lemma

For a finite set S of simultaneously live packet OWNERS and each p in S, let a(p) be the allocation identity from Arc pointer identity, B_a=Vec capacity(a)*element-size(a) [bytes]. Define n_a as number of owners that reference a. Then

Owner-summed O = sum_p B_{a(p)} = sum_a n_a B_a.
Unique-payload U = sum_a B_a.
Difference D = O-U = sum_a (n_a-1) B_a >= 0.

Proof: partition the finite owner multiset by allocation pointer identity, count each same backing once in U and n_a times in O. Distinct Arcs whose payload bytes are identical must remain different allocations; an empty Arc with Vec capacity zero still needs its Arc header allocation. This is exact for the stated Vec capacity payload and the enumerated owner set, NOT an exact process RSS estimate or a bound on all allocator metadata. Across current/input/candidate simultaneously live RoadStates, de-duplicate identities across the union and add each independent state shell, Vec owner slot, Arc control block, free-list reserve and working buffer.

Conditional bound: if at most three complete RoadState snapshots coexist and each corrected per-state accounting C_i upper-bounds all state payload+metadata, then sum_i C_i <= 3 max_i C_i, and the unique union <= sum_i C_i. This follows from elementary nonnegative inequalities; it requires proving the actual lifetime/capacity assumptions for the phase and accounting separately for incoming, events, interval_retained, interval_transient and extra. Therefore this lemma does NOT authorize reducing the original storage budget check yet.

## R3. Computer-science/physical semantics and falsifiers

Arc::ptr_eq or Arc::as_ptr identifies actual shared backing, unlike comparing Part payload values. Official Rust reference: https://doc.rust-lang.org/std/sync/struct.Arc.html . Every original Part remains (tag,offset,mass,birth,entry-times), and original FIFO/junction/kinetic rates and IEEE operation order remain frozen. Persistent packet-sharing gives no universal guarantee of bounded memory with distinct time-interval genealogy or full-network FIFO; related strict cohort bundle theory: H. Bar-Gera and M. Carey (2017), https://doi.org/10.1016/j.trb.2017.02.002.

Falsifiable probes: count distinct Arc backing pointers and owner-multiplicity at t=25600; validate per-owner sum equals legacy debug_stats payload contribution; measure unique bytes and potential difference. Snapshot alias observed only in input/committed/candidate but not one snapshot would favor a cross-state treatment, whereas numerous genuinely distinct Part roots and large transient/event buffers would limit improvement. No gate alteration until source-verified, adversarial tests and physical source-bound trials establish a conservative new upper envelope. Default V03 remains 19/21 scoped, full calendars 3/3 on parent branch, full day 0/9 BLOCKED.


## R4. Exact structural native-work decomposition at failure (derived + directly measured)

Existing v1_trace::guard is enabled by METROFLOW_BUDGET_TRACE=record, which does NOT change its original physical or budget decision. The observed failed C5 original 100k Valley 25600->25650 replay has RoadWorkBudget::require(required, phase='packet interval packing') and exact source formula:

required = base + event_bytes + incoming_rows × 2 × (sizeof(Part)+sizeof(Mark)) + interval_retained + interval_transient + extra.

On x86_64 this exact native struct identity has sizeof(Part)=48, sizeof(Mark)=32, so incoming row charge=160 bytes/row. Actual terms at the exceeded guard:
- base 1,980,005,976 bytes (37.77%).
- event_bytes 2,047,480,928 bytes (39.05%).
- incoming_rows=6,751,471, charged 1,080,235,360 bytes (20.60%).
- interval_retained 131,126,880 bytes (2.501%).
- interval_transient 3,955,912 bytes (0.075%).
- extra 6,208 bytes.
Their exact integer sum is 5,242,811,264 bytes, against the unchanged internal budget 5,242,806,391 bytes, excess 4,873 bytes. Wolfram Language and independent Python integer arithmetic both reproduced the sum. This is a structural resource-check equation, not an equation for actual RSS; event_bytes and base are conservative concurrent owner/scratch envelopes, not measured resident heap.

The trace also reports 498,636 packet-packing guard calls and 836,307 entry interval split guard calls in this bounded failure, 44,852 partial-service events and 23,901,798 split output row occurrences; these are actual counters under record tracing, not complete V03 full-day rows. They support that the distinct lineage and output materialization paths remain active. Even proving safe deduplication of 257,596,256 bytes from two live Arc-backed snapshots would NOT by itself prove that the 2.05GB event and 1.08GB incoming structural reserves are physically eliminable or that 25,650 can complete with a fixed resource gate.
