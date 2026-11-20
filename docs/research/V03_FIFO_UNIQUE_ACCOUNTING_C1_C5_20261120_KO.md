# V03 Unique Accounting · C1–C5 coding research (2026-11-20)

Source parent c76e4712bac41b8c089844c842bc6ce55c782501. All new research runs in research/v03-fifo-unique-accounting-20261120. Frozen original native 100k city demand, FIFO, birth/route/clock and RSS ≤8GiB/internal budget 5242806391 bytes.

## C1. Non-mutating exact pointer identity census

Added RoadState::arc_backing_census() to original Rust road module as a diagnostic-only method. Enumerates packet owners in cells and pending and inserts (packet kind, Arc::as_ptr(Vec header) pointer identity) into a HashSet while accumulating per-owner Vec capacity payload bytes and each distinct backing's capacity once. This computes the integer identity owner_payload - unique_payload = duplicate_payload; unique allocation header allowance 96 bytes per distinct Arc is **diagnostic only, not an allocator-certified upper bound**. Nothing in the road-work admission, physical equation, native packet bytes or accounting thresholds is changed.

Exposed the census only via an explicit native whole-engine debug_state(state) call; it is NOT computed during every native road tick or release acceptance. This avoids a high-cardinality HashSet cost in the production physical time loop. Three test-first Rust cases were RED with E0599 (missing arc_backing_census), then GREEN: multiple aliases of same Uniform Arc counted once, equal-content but distinct Mixed allocations counted independently, zero-capacity distinct Arc still count as separate allocations and reporting control allowance. The source's original test-only shadow and earlier owner-counted debug_stats remain intact.

Fresh Cargo workspace library 84 passed (2 ignored optional benchmark cases), cargo check workspace --tests PASS, new native release build PASS, bounded original Python native road/packed interval/storage/kinetic tests 34 passed. No original full-day 9-run acceptance, and no performance extrapolation based on diagnostic unit test. Next C2 is actual 25,600 checkpoint read-only census; its source/native source hash must be measured after this stage is committed, and the previous runtime receipts must not be counted as the new binary's 3/3 preparation.

## C2. Source-locked original Valley 100k snapshot identity census

A new read-only Python runner tools/research/v03_unique_arc_census.py uses the newly compiled native whole engine, original 10s / 100k Valley input, same frozen matrix/driver identity and physical mass-ledger checks to load the original t=25300 and t=25600 binary checkpoints. It calls the Rust debug_state diagnostic only, **without advancing the physics or changing the work-budget gate**. It hashes the actual original local 25600 checkpoint and retains only small JSON output. Exact observed counts:

| Time [simulated s] | Road packet owners | Distinct Arc backing pointers | Source Part records | Owned & unique Vec payload bytes | Duplicate within ONE RoadState |
| 25300 | 2027 | 2027 | 155485 | 4975520 | 0 |
| 25600 | 158498 | 158498 | 8049883 | 257596256 | 0 |

The Rust census metadata allowance is 96×distinct Arc (194592 vs 15215808 bytes), explicitly **not** a universal malloc upper bound or measured RSS. The diagnostic confirms that the old per-owner Vec payload sum has NO duplication inside either of these two individual stored states. The possibility of sharing across separate input/current/candidate states remains unresolved; do not infer its absence from this measurement. The source-bound storage budget in the original failed 25600->25650 runs was not modified: 5242806391 native bytes, process ≤8GiB, full 24h 0/9.

Two independent Python tests verify the source/loaded native SHA, owner=unique identities, exact row counts, no altered resource budget, and the actual binary checkpoint SHA/size. Outcome: IMPLEMENTATION-VERIFIED_ONE_STATE_CENSUS and **REFUTED_AS_A_MECHANISM for single-state duplicate Arc payload in these two measured snapshots**. No causal claim yet about the actual failed tick or concurrent input/current/candidate overlaps. More source-conservative action: diagnose cross-state union identity and the packet interval packing's transient output-size budget before any admission change.


## C3. Cross-snapshot Arc union identity (read-only)

The original whole-native engine holds a supplied immutable snapshot together with the currently installed committed road state. Added RoadState::arc_backing_union(&[&RoadState]) which counts owner references, distinct pointer/type backing keys and exact duplicated Vec capacity within an **explicit finite list of simultaneously live RoadState references**. The existing per-state diagnostic now delegates to this general union with one reference and retains all its prior assertions. Added V1Road::arc_committed_snapshot_union(supplied) accessor and exposed this distinct two-state census only from the on-demand native debug_state interface; it is NEVER used in per-tick RoadWorkBudget or full-day resource admission.

Three RED→GREEN Rust tests compare (i) three RoadStates cloned from the same immutable packet, owners=3 and unique=1, (ii) two separately allocated identical contents, unique=2, (iii) empty and singleton unions. RED was recorded as E0599 missing method; after implementation fresh Rust workspace 87 passed, 2 ignored, Cargo check passed, compiled release native built successfully, and 32 original native V1 Python tests passed.

This proves exact payload-accounting identity for enumerated live references and supports measuring current/committed overlap. It does NOT include the newly allocated candidate, every in-flight event buffer or missing/untracked other retained snapshots and cannot justify reducing the original 5242806391-byte native cap by itself. The C2 25300/25600 one-state zero-duplicate result remains a valid **historic source-pinned measurement** under its original binary SHA; after recompiling C3 it must not be cited as a fresh native binary test without source recomputation. Next C4 runs the new interface against the same actual 100k Valley 25600 checkpoint, source/binary remeasured and checkpoint provenance pinned.


## C4. Actual source-bound committed/supplied RoadState ownership overlap

Using C3's newly compiled whole-native read-only diagnostic, loaded the identical original Valley 100k checkpoints at 25300 and 25600 seconds, verified original matrix/driver/mass ledgers and actual on-disk binary SHA, and queried current committed plus supplied immutable snapshot **without advancing physical time**.

At t=25300, one-state owner_count=2027, unique_backing_count=2027, unique payload=4975520 bytes; two-state owner_count=4054, unique_backing_count=2027, duplicate payload=4975520 bytes.

At t=25600, one-state owner_count=158498, unique_backing_count=158498, unique payload=257596256 bytes, physical Part record count=8049883; simultaneously committed plus supplied owner_count=316996, unique_backing_count=158498, owner payload=515192512, unique payload=257596256, duplicate payload=257596256 bytes.

**Interpretation:** the live committed/supplied pair shares every measured backing, while each individual RoadState has no internal duplicates. Hence the per-owner capacity across these two states overcounts the payload by 257596256 bytes. This is an implementation-verified integer identity for these *two enumerated owners*, NOT a reduction of the original RoadWorkBudget: a changing candidate, interval_retained/transient and incoming/EventRow scratch are not enumerated. The native 5242806391 byte limit, original process 8GiB cap, source calendar and physics remain unchanged. The prior C2 receipt was pinned to an older Rust binary; tests were restricted to its historical source evidence, while fresh C4 tests verify current live source and binary SHA. Independent C4 and C2 Python source-bound tests 4/4 passed.

**Falsifiable next step:** determine whether a conservative, non-fitted lower bound on Arc sharing *throughout the entire failed tick*, including changes in candidate and all in-flight allocations, can be applied without decreasing required capacity below actual simultaneous live bytes. Until such a proof and stress experiment, report RESOURCE_BLOCKED, not "corrected accounting" or a completed 25650 run.
