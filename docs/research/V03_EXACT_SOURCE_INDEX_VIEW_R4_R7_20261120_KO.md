# V03-EXACT-SOURCE-INDEX-VIEW-01: FIFO-preserving interval view and physical alternatives

Authority: `docs/v1/PLAN.json` v1.1.26 and `scenarios/v1/release_matrix.json`; parent research commit `57432d4191ce834cb9a62679149c3926ce93933b`. This is an **isolated research** change, not a PLAN node status change, production merge or release.

## R4 / R5: constructive identity of interval split+combine

Consider an ordered source sequence of valid finite Parts
`P_i=(tag_i, offset_i, M_i, B_i, alpha_i, beta_i)`.
For a consecutive unique endpoint pair `[u,v]`, with `v>u`, original `IntervalActiveSweep` selects exactly the source indices
`I_uv={i | alpha_i<=u<v<=beta_i}` in increasing index order.
For every selected source index the legacy physical transform evaluates, in the original order,
`M'_i=fl(fl(M_i*(v-u))/(beta_i-alpha_i))` and
`B'_i=fl(fl(B_i*(v-u))/(beta_i-alpha_i))`;
then replaces the two interval endpoints by the bit representations of `u,v`.
Here `fl` denotes the concrete binary64 operation and *not* an algebraically reassociated real product. Retain original signed zero and subnormal behavior. `combine` filters `M'_i>0`, groups by `(tag,offset,u_bits,v_bits)`, and sums `M',B'` in original source-index order with the original native `sum` implementation.

Because `(u_bits,v_bits)` are constant over the group, the above key comparison reduces to `(tag,offset)`; an ordering by `(tag,offset,original_index)` gives the **same per-group sequence** as the old `combine`'s full key and tie order. Therefore `combine_interval_view` can form the filtered ordered index vector, group it, and compute exactly the original two `sum` iterators **without first allocating** a second vector of all split `Part` values. This is a source-order-preserving representation refactor, not coarsening, symbolic integration or a new dynamical closure.

The proof requires (i) the input source-index iterator is ascending and unique (established for `ActiveIndexBits`), (ii) every chosen index is valid and has positive finite interval width, (iii) `v>u`, and (iv) original Rust arithmetic operations are evaluated with the same binary64 semantics and reduction order. Point rows `alpha=beta` remain on the unchanged materialized path. Non-successful allocation/error paths and compiler/ABI changes are outside the bit-identical successful-output statement. Full-native scenario checkpoint byte identity still requires a separate source-bound end-to-end experiment.

## R6 / R7: conservative transient bound and discriminants

Let `r` be the number of currently active source rows for one nonpoint interval and `S=sizeof(Part)=48` bytes, `J=sizeof(usize)=8` bytes on the pinned x86_64 host. The previous upper charge for the split buffer, combine-index buffer and combined-output buffer was `(2S+J)r=104r` bytes; the new source-index view uses the index and combined output only, `(S+J)r=56r` bytes. The reduction in **that** transient row term is `Sr=48r`, i.e. `46.15%` of the row term. Point rows retain `104r`. All packet owners, retained physical rows, EventRow arrays, edge/index structures, source calendars, user numeric memory/time limits, event clocks, FIFO, route tags and native checkpoint wire format remain unchanged. No whole-process RSS or wall-time improvement follows from the structural expression alone. The interval set and repeated per-group floating operations still have real CPU cost.

The fixed 2026-11-20 source-bound predecessor reproduced Valley 100k 25600→25650 original output with SHA256 `89e3230b23b4423509f6036035e9b03c7299204b5d317cdb3f6226c5b0c53e8b` (historical native candidate, not current). Its 25650→25700 default attempt failed the **transfer candidates** source-bound work guard by 4,729 structural bytes in an earlier partial state. A different opt-in path reached the **indexed interval sweep** guard. Removing the interval temporary buffer cannot imply passage of the earlier transfer guard. Do not reinterpret a guard deficit as observed resident heap usage; no global 8 GiB bound has been changed.

Discriminating experiment sequence: compile source and run materialized vs view bitwise Rust oracles; rebuild current native extension; rerun original selected V1 bridge tests on that extension; if source+large local checkpoint is available and resources permit, run the same 100k Valley 25600→25650 and 25650→25700 bounded physical prefixes under **unchanged default** admission. Require identical checkpoint/ledger bits at completed times and report guard phase+terms for failure, actual resident peak RSS and elapsed wall. Source-bound old receipts are stale for a new source hash.

## Structural alternatives, kept separate

- **Exact FIFO track:** direct source-index interval view (current slice), then an immutable source-order marked event DAG or streamed EventRow/incoming consumer. Exact source-specific order, birth, time, route, f64 sequence and legacy serialization still have to be reproduced. Cloning aliases alone does not bound the number of distinct lineage fragments; total exact flattened output size can remain proportional to distinct physical rows.
- **Physically modified junction track:** partial FIFO through independently supportable turning pockets and physically specified mutual lane restrictions. Wright et al., *On node models for high-dimensional road networks*, Transportation Research B 105 (2017), 212–234, arXiv:1601.01054, develops lane-aware partial FIFO; geometric restrictions must not be arbitrary fitted bypass fractions.
- **Cumulative wave track:** continuous-time link-based kinematic waves with demand/supply and spillback; Han, Piccoli & Szeto, *Continuous-time link-based kinematic wave model* (2016) describes link-scale solution/DAE structure. Retains conservation under its junction assumptions, but discards original individual Part birth/order and is a distinct model.
- **Kinetic / KCMB track:** independently developed route/mode moment fields and geometric lane storage. Synthetic conserved network days support a bounded test, but the earlier explicit AB-versus-BA strict-FIFO counterexample refutes universal reconstruction of order from instantaneous unordered six moments. A queue-order overlay or spatially resolved state would be needed for that exactness claim; large-city empirical calibration and held-out predictive checks remain unresolved.

## Scientific status

DERIVED_CONDITIONAL: interval-view equivalence under source-index/order/IEEE conditions; 48 bytes per active span-row transient structural reduction. R7 finite binary64 tests and source-bound physical outcomes must be documented in the coding receipt. NOT CLAIMED: nine 86400s source-city acceptance runs, universal exact compressed-history feasibility, actual original-city speedup or source-valid production ready state. Existing PLAN implementation progress remains 19/21 scoped, direct predecessors 3/3, and full-day physical acceptance 0/9.
