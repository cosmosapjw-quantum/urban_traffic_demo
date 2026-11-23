# C8c: concrete capture/restore snapshot owner accounting

Status: source frozen after bounded behavioral and library validation. Independent delta review is a separate artifact. No production-scale physical run, commit, push, native build or main-worktree source modification was performed in this author lane.

## Scope and observed blocker

Base: `64173178d11229825efc553c441f6f90c7541979` in isolated worktree `/home/cosmosapjw/worktrees/urban-traffic-v03-origin-capture-fix-20261123`.

Root's preserved main-native evidence motivating this correction:

- Final frontier 25730→25740: one internal tick succeeded, but return capture/validation required 6,887,244,069 B against the unchanged 6,442,450,944 B cap. Returned/ledger-validated/durable credit remained zero for that attempt.
- Final 40 s staircase: all four returned ticks were ledger-validated through 25730; final `save` then required 6,513,265,473 B against that same cap. No final durable wire from this 40 s attempt.
- The original 86400 s hourly attempt subsequently exited 1. Its first error was the Journey stored/working budget; exception-save then hit capture admission at 7,611,271,961 B. Last durable progress was 25200; the internal failure clock was not established by that receipt. Raw main `R8_pre_capture_original_hourly.log/.time/.exit` remain authoritative. This correction does not claim to solve the first Journey error or retroactively credit an unpublished internal state.

The change addresses the shared capture/restore owner mechanism, rather than selecting separate thresholds for these observations. No cap, demand, physics, dt, FIFO, f64 arithmetic, tolerance, wire format, decoder validation, or error-path checkpoint selection is changed.

## Source owner proof

Let I be the supplied immutable Bundle and C the current native owners. The exact planned clone target T is C for capture and I for restore. The supplied original and current owners stay live during cloning. For road, the conservative charge is:

`R(I) + R(C) + R(T) - P_road(I,C) - P_road(T,clone(T))`.

All R values are measured from their actual source capacities before cloning. Road pair credit is a freshly computed unique intersection of live Arc backing identities, keyed by layout kind and Arc pointer. Equality of values, model identity, clock or byte count never creates road credit. Target-clone credit is the unique immutable payload of the exact source that Clone shares. Packet shells, per-cell/pending registries, latent maps, Arc/control/allocator allowances and spare capacities remain conservatively charged. Repeated SharedKeys are credited once per pair; retained-storage accounting already deduplicates their key allocation within one owner. A three-way shared payload receives exactly two pair credits and therefore retains one payload charge.

Journey uses the corresponding source sum:

`J(I) + J(C) + J(T) - P_stage(I,C) - P_stage(T,clone(T)) - H(T)`.

StageQueue Clone shares immutable blocks and creates its own pointer registry. Only immutable row payload capacities are credited; block headers and registry capacities remain conservative. ReceiptHistory Clone is an Option<Arc<Block>> clone: it creates no dynamic history chain, and the whole target history chain H(T) remains shared. The outer per-leg vector is covered by the unchanged fixed dense reserve. No cross-source history-prefix credit is inferred; distinct input/current history owners are still conservatively charged even when they may share prefixes.

Service events charge `E(I) + E(C) - P_event(I,C)`. A planned checkpoint/rollback clones Arc<ChunkedEvents> itself, without a third event backing. The pair credit requires `Arc::ptr_eq` and equal measured storage; distinct event Arcs remain fully charged.

The new central `NativeWholeEngine::snapshot_source_owners` is used by both existing Some(input) capture/validation and restore admission. Input-none decoded-bundle validation and the unknown-source fallback retain their existing formulas. Independently decoded future owners receive no alias credit; a real already-decoded Bundle used by restore is handled only through its then-live pointer identities.

## Census phases and allocation discipline

Before either added pointer census is allocated, the engine admits:

`fixed base + call binding + uncredited two-live-owner sum + max(road census upper, stage census growth upper)`.

No prospective pointer credit finances this preflight. No prospective clone exists yet. Road reserves one HashMap for the counted backing occurrences with try_reserve, then checks its actual capacity against the admitted upper before insertion. The existing stage census bounds both old and new tables during growth and checks its measured final capacity. Road and stage tables are dropped before the next census/clone/validation phase, so their simultaneous upper is the maximum, not their sum.

Final admission is the maximum of that census phase and the snapshot owner charge plus the unchanged validation/call-binding workspace. This preserves current owners until their real replacement; it does not assume early destruction.

The HashMap padding is the repository's conservative current-standard-library structural model, not an allocator-independent RSS theorem. Actual source retained-size accessors already perform their existing internal diagnostics; this patch preflights its newly introduced pointer tables and does not claim to redesign all historic measurement allocations. The external process-memory acceptance obligation remains unchanged.

## Behavioral evidence and fixture provenance

The first three preserved logs named `C8c_RED*` are fixture construction failures, not behavioral RED: an invalid birth moment in the initial attempt, followed by an empty-event assumption before actual characteristic outflow. They remain raw evidence and are excluded from repair credit.

The corrected fixture uses 8192 real road tags, actual road-generated event rows, an internal StageQueue with 4096 rows, and nonempty ReceiptHistory. It advances the small road only until the first real event batch (bounded by 20 steps), binds Journey to that actual clock, and passes whole-bundle ledger validation before installing the tested cap. The original Journey 3J validator floor is retained and fits the selected test caps.

| Actual operation | Same cap, B | Old code behavioral RED | Corrected code GREEN |
|---|---:|---|---|
| Native zero-step advance, including restore, capture and whole validation | 84,594,070 | required 84,991,238; rejected | passed |
| Native save, including restore admission | 84,397,174 | required 84,991,166; rejected | passed |

`C8c_behavioral_RED.log/.exit`: two actual gate failures, exit 101. `C8c_behavioral_GREEN.log/.exit`: the same two fixtures and caps pass, exit 0. Journey dynamic storage was 3,430,912 B and service event storage 328,552 B. The save test compares the entire high-cap and bounded-cap checkpoint byte vectors in the corrected runtime; all 1,049,076 bytes agree. This is exact full-wire equality across those two admission settings, not a claim that a new physical simulation was completed.

`C8c_scoped.log/.exit`: 7 passed, 0 failed. Additional bounded regressions cover an actual one-step advance to a different clock with freshly witnessed surviving stage blocks and different event ownership; independently allocated equal payloads receiving zero pair credit; rejection at the pre-census bound; the unchanged missing-source legacy floor; original input spare packet capacity remaining charged even when its clone has less capacity; and unique shared-key credits across repeated packets.

`C8c_final_lib.log/.exit`: exit 0, 292 passed, 0 failed, 2 ignored, 0 filtered. This includes the existing malformed checkpoint/ledger rejection and original source-owner/decoder regressions. `git diff --check` completed without output. No optional additional matrix was run after this gate.

## Freeze and remaining acceptance

- `v1_road.rs`: `e6cc7627cb74497fb5a108897df860e8a3da5567c121ad73a601a3cf2346e617`
- `v1_journey.rs`: `bdae60a4f7110d21c148430e31e22c816c6fa7c27cb9ac056985ab7ffc7b6740`
- `v1_engine.rs`: `ddc0e42ea5396c64564a822a858b7fbd652be311a2082bfb908eefe0146287db`

The source and Cargo were released to the root and independent reviewer immediately after the final gate, before this note was written. See `C8c_freeze.json` for file/log identities.

Implementation-verified: the two actual small capture/save operations that failed under the same cap now succeed; full-wire equality and the stated source/census edge cases pass. Derived: the immutable-owner counting argument above. Unresolved: release-scale 40 s durable retry, the next frontier, independent fresh restore on the integrated final native, original-hourly first Journey budget, and mandatory 43200 same-engine resume. No claim is made about their outcomes before root's actual receipts.

Origin/drift watchdog: this engineering correction serves the original concrete 100k-resident day/replay/recovery obligation while preserving its physical state and raw receipt semantics. It creates no new physical theorem and adds no V03 node or physical time credit by itself. Root's separate theoretical result and release readiness ledger retain their independent evidence requirements.
