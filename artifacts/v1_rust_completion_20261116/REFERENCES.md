# Exact delayed-source storage: narrow reference study

Date: 2026-11-16 UTC. Code inspected: `7b5e518f6c098ed831551da4e66d980addf80dd8`, `crates/metroflow-rust/src/v1_journey.rs`.
Scope: resolve stage-storage growth while retaining the current scientific transition. This note does not report a new simulation PASS.

The parent's measured blocker is 2,000,000 records at 25,380 s (07:03), with entering approximately 92.7% of outstanding records and no identified unretired-ready leak. Those measurements are supplied task context, not independently rerun here. Direct code inspection confirms that each release currently expands every delay atom into an Access row, while law contents are already interned with Arc.

## Decision

Implement **A: exact lazy delay-law batches** first. Consider **B: immutable release chunks plus a due index** only if batch scans or checkpoint copies remain dominant. Timing-wheel literature supports scheduling acceleration; it does not establish a reduction in the number of physical source cohorts or equivalence to this kernel. No faer operation is implicated by this storage problem.

### A. Lazy delay-law batches (derived design, not implementation-verified)

Store one batch per current release event:

`(leg, mass, born, hold, Arc<law_and_delay_index>, consumed_prefix)`.

The shared law retains its original atom order and original f64 values. A second immutable index sorts original atom indices by delay, breaking ties by original index. The cursor addresses that index, not the original law sequence. Discover the newly due prefix using the original predicate, then emit its indices in original atom order. Visit batches in original append order. The current validator does **not** require sorted delays; sorting the law itself or using an original-order cursor would change accepted behavior.

The logical expansion of a batch is the original-order subsequence of unconsumed atoms:
- mass: `mass * weight`;
- stored delay: `delay + hold`;
- ready: `born + (delay + hold) <= clock + 1e-10`;
- road-offer moment: `(mass * weight) * born`.

Preserve those f64 operations and association. Do not replace them with algebraically equivalent products, a mean delay, or aggregate moments. For egress batches preserve the exact multiplication chain already used for bus passengers; source mass for that branch is the computed `arrived * factor`. The initial entering/internal insertion, road-event insertion, bus insertion and freight insertion orders remain unchanged. Egress completion is still processed before internal completion.

If E expands each batch to its unconsumed original rows, a correctly implemented transition should satisfy `E(T_lazy(B)) = T_eager(E(B))`. This follows by induction only when due selection, emitted-row order, arithmetic, and state updates agree at every step. It is a design argument, not a completed proof or test result. Because IEEE addition with fixed finite operands is monotone, a delay-sorted index supports prefix selection; preserve existing input validation and explicitly test floating-point boundary cases.

Memory becomes O(B + sum K_unique) instead of O(sum K_per_batch) for B active release batches and K delay atoms. This removes the atom multiplier, not the OD-by-release-tick multiplier. Actual savings depend on atom count and struct size. Arc sharing is supported by Rust's ownership API [R3]; exact simulation equivalence is a separate obligation.

**Concrete counterexample:** valid law `[(10, 0.5), (0, 0.5)]` with born=hold=0 at clock=0 has its second atom ready. An original-order cursor that stops at the first atom drops that release until a later clock. The shared sorted index avoids this while preserving original emission order.

### B. Immutable chunks plus a due index (derived optional extension)

Store stable release proposals from a tick in an immutable shared chunk; keep batch cursors in a compact checkpointable structure. An exact-time index can identify which batches need examination. It must retain each absolute f64 readiness calculation and original batch/atom ordinal. After gathering due batches, restore original batch order before emitting atoms.

A wheel's bucket is an indexing hint only: recheck exact readiness, handle overflow beyond the wheel horizon, and never round, clamp, or reorder scientific timestamps. A calendar queue normally orders by timestamp, whereas this kernel scans existing insertion order at a tick; adopting chronological order directly can change FIFO offers and f64 additions. Carousel explicitly accepts less ordering within a timing-wheel slot than an exact calendar queue [R2]. Brown's O(1) result is experimental for specified priority-increment distributions, not a distribution-independent guarantee [R4].

This extension reduces repeated scans and permits sharing of immutable payloads across transactional snapshots. A timing wheel alone still holds outstanding references and does not remove the atom multiplier. Build it only after measurements show the simpler batch representation needs it.

## Contracts and acceptance checks

1. Compare eager versus lazy expansion and ordered offers on unsorted laws, duplicate delays, zero delay, a parent hold, partially consumed batches, and several simultaneous releases. Compare f64 bits where existing contracts require byte identity.
2. Keep parent-return eligibility evaluated from the pre-tick committed state. Completion clocks remain `max(t, born + stored_delay)`; preserve receipt order and cumulative additions.
3. Birth mass alone is insufficient. Two cohorts with mass 0.5 at births 0 and 2 have the same total mass and birth moment as mass 1 at birth 1. With delay 1 and clock 1.5 the first representation releases 0.5 and the second releases zero. Thus mass/first-moment aggregation does not preserve the delay CDF or FIFO effects.
4. Retire fully consumed batches and release chunk references. Verify each original atom appears exactly once and failed prepare/finish leaves the last committed state intact.
5. Version checkpoint format if representation changes. Serialize law identity/content binding, batch scalars, original ordinal and cursor. Reconstruct or validate the deterministic delay index. Resume from a partially consumed unsorted law and compare future outputs; do not silently reinterpret old checkpoints.
6. Distinguish logical remaining atom count from allocated batch count/bytes. The current `record_counts()` reports physical Vec rows and feeds record accounting. Merely compressing storage but continuing to enforce the cap against expanded atoms leaves the blocker; silently relabeling a scientific cap would also be wrong. Document the resource measure, preserve both diagnostics and retain a separately justified physical-memory guard.
7. Checkpoint/snapshot APIs that eagerly re-expand every atom can erase the memory benefit. Keep external compatibility explicit and measure any expansion boundary.

## Evidence and limits

| ID | Primary source | What it supports |
|---|---|---|
| R1 | Varghese & Lauck, 1987, [ACM DOI](https://dl.acm.org/doi/10.1145/41457.37504), [original paper PDF](https://www.cs.columbia.edu/~nahum/w6998/papers/sosp87-timing-wheels.pdf) | Timing wheels index timers by clock granularity; bounded-range operations can be constant time. The paper separately measures space and latency. It does not prove this simulator's equivalence. |
| R2 | Saeed et al., 2017, [Carousel author PDF](https://saeed.github.io/files/carousel-sigcomm17.pdf) | Section 5.1.2 distinguishes exact within-slot timestamp order from the weaker order acceptable to its traffic shaper. Its memory discussion counts outstanding references. |
| R3 | Rust standard library, [Arc documentation](https://doc.rust-lang.org/std/sync/struct.Arc.html) | Arc clones share a heap allocation; make_mut clones on write when needed. Shared ownership does not by itself make mutable contents thread-safe. |
| R4 | Brown, 1988, [Calendar queues, ACM](https://dl.acm.org/doi/10.1145/63039.63045) | Calendar queues are a future-event priority queue; reported constant-time behavior is empirical for the tested distributions. |

SciSpace discovery surfaced Bar-Gera & Carey (2017), *Representation requirements for perfect first-in-first-out verification in continuous flow dynamic models*: [SciSpace discovery](https://scispace.com/papers/representation-requirements-for-perfect-first-in-first-out-4zrcgrs1c8?utm_source=chatgpt&utm_medium=tool), [primary DOI](https://doi.org/10.1016/j.trb.2017.02.002). The DOI fetch returned bibliography/metadata but no theorem text. It is retained as a relevant follow-up, not invoked as proof of a specific sufficiency theorem. SciSpace's hybrid packet/fluid papers describe approximations; they do not justify silently substituting a new closure for the existing kernel.

Searches used Exa, SciSpace and Parallel. Exact requests, result URLs, evidence levels and one failed guessed publisher-path fetch are in REFERENCES.json. Primary evidence above was read through search excerpts and/or extraction. One Parallel extraction returned 404 for that guessed publisher path; the valid DOI was found independently. No feedback was sent to Parallel.

