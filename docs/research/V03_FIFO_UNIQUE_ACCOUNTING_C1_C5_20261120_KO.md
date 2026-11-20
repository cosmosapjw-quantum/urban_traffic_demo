# V03 Unique Accounting · C1–C5 coding research (2026-11-20)

Source parent c76e4712bac41b8c089844c842bc6ce55c782501. All new research runs in research/v03-fifo-unique-accounting-20261120. Frozen original native 100k city demand, FIFO, birth/route/clock and RSS ≤8GiB/internal budget 5242806391 bytes.

## C1. Non-mutating exact pointer identity census

Added RoadState::arc_backing_census() to original Rust road module as a diagnostic-only method. Enumerates packet owners in cells and pending and inserts (packet kind, Arc::as_ptr(Vec header) pointer identity) into a HashSet while accumulating per-owner Vec capacity payload bytes and each distinct backing's capacity once. This computes the integer identity owner_payload - unique_payload = duplicate_payload; unique allocation header allowance 96 bytes per distinct Arc is **diagnostic only, not an allocator-certified upper bound**. Nothing in the road-work admission, physical equation, native packet bytes or accounting thresholds is changed.

Exposed the census only via an explicit native whole-engine debug_state(state) call; it is NOT computed during every native road tick or release acceptance. This avoids a high-cardinality HashSet cost in the production physical time loop. Three test-first Rust cases were RED with E0599 (missing arc_backing_census), then GREEN: multiple aliases of same Uniform Arc counted once, equal-content but distinct Mixed allocations counted independently, zero-capacity distinct Arc still count as separate allocations and reporting control allowance. The source's original test-only shadow and earlier owner-counted debug_stats remain intact.

Fresh Cargo workspace library 84 passed (2 ignored optional benchmark cases), cargo check workspace --tests PASS, new native release build PASS, bounded original Python native road/packed interval/storage/kinetic tests 34 passed. No original full-day 9-run acceptance, and no performance extrapolation based on diagnostic unit test. Next C2 is actual 25,600 checkpoint read-only census; its source/native source hash must be measured after this stage is committed, and the previous runtime receipts must not be counted as the new binary's 3/3 preparation.
