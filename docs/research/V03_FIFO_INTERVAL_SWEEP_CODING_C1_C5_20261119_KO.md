# V03 exact interval sweep C1–C5: new physical Rust candidate, proof and red/green

Date: 2026-11-19 KST. Separate worktree research/v03-fifo-interval-sweep-20261119, parent 15d7546ade8b1ee6efe16f9a2a1b33cc1a1c2622; R1–R10 source e868f1c11eef048df99a6713391523ed3abaeb88 already pushed and remote-verified. This is a candidate replacement for the original entry-interval **selection algorithm only**, not a new vehicle kinetics/flow/hazard model.

## C1 Source/acceptance
The original V03 is BLOCKED on exact FIFO interval packet genealogy in congestion. Official 21-node DAG 19/21 scoped complete, original 3×100k full calendar construction 3/3 in the PARENT binary, full 3-city×3×24h release 0/9; acceptance requires original 8GiB process RSS, 7200s wall, exact clocks, ledgers and all requested repetitions. This branch recompiles a different native binary, so PARENT prepare receipts are STALE for THIS binary and cannot be credited as 3/3 without fresh executions.

## C2 Constructive derivation
The old interval_packets loop scans every Part for each unique time edge a, with point predicate pa==pb==a and interval predicate pa<=a && pb>=b && pb>pa, b is the next unique edge. Under finite valid endpoints, pb>a implies pb>=b, because b is the next endpoint in the global input list. An index sweep inserting each [pa,pb) at its start and retiring at its end yields the same selected source indices. Use numeric equality for signed ±0 grouping; preserve original source indices ascending, and therefore keep combine's exact fsum grouping order.

## C3 Implementation and numeric semantics
Introduced private IntervalActiveSweep in crates/metroflow-rust/src/v1_road.rs. It pre-sorts start/end/point event records with exact f64::total_cmp and stable secondary original index, stores active source indices in a Rust BTreeSet, and outputs eligible point indices ascending. Old interval_packets now uses this index set and still calls the exact original split expressions:
q.mass = q.mass * (b-a) / (pb-pa);
q.birth = q.birth * (b-a) / (pb-pa).
Target time, interval flags, pack_parts, combine, physical road state and checkpoint wire schema are unchanged.

Additional event-index scratch is charged against the original RoadWorkBudget as a conservative per-input-row upper working allowance, including sorted event indices, point cursor and active ordered set. This source checks native 8GiB process limit separately; conservative workspace accounting is not an allocator metadata theorem. No numerical tolerance is weakened. If this additional scratch makes resource-bound progress worse at full congestion, it is a negative performance outcome.

## C4 Test-first evidence and independent finite oracle
Before defining IntervalActiveSweep, native cargo tests failed with E0433 (undefined selector). After implementation, an independent old quadratic selection oracle agreed with new active indices on finite point/nonpoint rows, signed ±0, changed input order, 1/2/5/17/64/256/700 seeded random rows. An independent old split+combine oracle was added and compared final per-row IEEE mass/birth/time payloads, not merely total mass. The test preserves selected-row order, and all new checked Rust tests passed.

Native cargo workspace lib: 64 passed (the original 61 plus three new executable checks for selection indices and full split+combine IEEE payloads), one optional microbenchmark ignored in the regular test suite. Scoped Python native V1/kinetic/authoritative plan checks: 104 passed, excluding three old binary-provenance tests which refer to the previous native SHA; a new explicit test confirms that their 3-city receipts must be marked stale on this new binary. Added explicit test proving the previous 3-city prepared receipts are stale for the new native SHA, with 0/3 scoped credit until fresh preparation for this compiled kernel. Original main/PLAN/PR41 remain untouched.

## C5 Selector microbenchmark and limitations
A release-mode opt-in ignored Rust benchmark constructed 5,000 finite Part rows with 121 unique interval edges and compared ONLY selection costs across four deterministic repeats. Original repeated scans total 4,093,408 ns; new event sweep selection total 2,803,415 ns, ratio 1.460. This is a narrow inner-selector benchmark and does NOT imply 1.46× V03 whole-code speed or lower total RSS. The algorithm still constructs every logical time-segment output row, so packet doubling is not cured. Original physical 25,300s checkpoint bit comparison is not yet executed on this new native binary, and production acceptance remains blocked pending stage C6–C10.

## Stage end / next
After selected validation commit and push this source/test/report to the isolated research branch and re-read its remote SHA. Then execute actual original 100k Valley prefix with the new binary, compare native checkpoint hashes against the previous bit-identical source baseline and measure wall/RSS; refresh full calendar prep source identity where feasible. If output differs, retain the counterexample and reject/restore the candidate. The first meaningful V03 scientific obligation after this speed-only slice remains exact temporal packet genealogy redesign, not arbitrary fitted parameter adjustment.
