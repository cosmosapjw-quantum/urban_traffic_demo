# V03 coding reconstruction — 2026-11-23

## C1: objective and preserved baseline

The user requests the complete coding C1–C10 track focused on the repeated V03 bottleneck. The source baseline is cd77044495598f4ddb28412f78241bd1eb98693c, which contains the completed theory R1–R10 and verified worktree cleanup. Production source is unchanged from 492e27618696df2514b088a64de450cf69746647. This coding track uses the existing latest checkout on a dedicated branch; the two retained worktrees and selected compressed recovery files remain.

The physical target remains the original release matrix: 100000 residents, full calendars, strict FIFO, legal routes, finite response, tagwise vehicle/person/cargo/residence accounting, 86400 s for three cases and three repeats, peak RSS <= 8 GiB and wall <= 7200 s. The original numeric tolerances and full-day admission criteria are fixed. The immediate falsifiable implementation target is an original full-demand transition beyond the known 25700 s valid checkpoint and its 25710 s resource failure, under the original limits, with matched behavioral/wire checks and a current-source provenance record. This is not an assertion that the whole release can be finished by a local optimization.

Existing evidence: 34610422 road composition rows across 631350 packets; two source products (composition × service and active composition × interval slabs). The S07 indexed-sweep charge is 5051633256 B against allowance 5025214575 B. Theoretical consumer maps and constructive routes are in V03_BOTTLENECK_RECONSTRUCTION_20261123.md. They are reused rather than re-audited. Existing successful prefix and compressed checkpoint are bound in artifacts/v03_causal_rank_20261123/S08_time_zero_prefix.json and artifacts/cleanup_20261123/RECOVERY_VERIFIED.json.

The first selected native boundary is persistent, exact event-history storage: preserve existing timed event pages across history retention and legacy decoding, avoid a giant flat event Vec at that boundary, and keep internal validation and legacy export streaming. The independent code trace must establish actual owners and guards. A second source/consumer representation change will be selected only from observed next-bottleneck evidence. A new controlled model, if used, must have a separate version and physical-error contract; it cannot silently become the original V03.

## Ten coding stages

| Stage | Deliverable | Status |
|---|---|---|
| C1 | Exact baseline, scope, original acceptance, experiment target | COMPLETE; BASELINE.json |
| C2 | Actual expression/data/producer/consumer map and implementation ownership | COMPLETE; V03_CODING_SOURCE_MAP_20261123.md |
| C3 | Exact representation invariants, stable computation, failure counterexamples | COMPLETE; exact codec and ownership contract below |
| C4 | Bounded execution ladder, recovered native baseline, build/resource setup | COMPLETE; recovered binary and observed behavioral RED |
| C5 | Complete native producer-to-consumer implementation | COMPLETE; exact history path and behavioral GREEN |
| C6 | Actual build, behavioral red/green, targeted native/Python regressions | PENDING |
| C7 | Full-demand original checkpoint continuation and physical ledger checks | PENDING |
| C8 | Increasing horizons, matched correctness/resource/replay experiments | PENDING |
| C9 | One independent review of changed scientific and runtime surfaces; repairs | PENDING |
| C10 | Final readiness/evidence, reusable latest checkpoint, exact next action | PENDING |

Each stage is committed and pushed separately. Stage completion describes the requested research work, not automatic V03 acceptance. Initial DAG: scoped-or-accepted 19/21, accepted 5/21; V03 BLOCKED; full-day 0/9.

## Drift watchdog for this turn

The original 0492364 PRD and 6524500 constitution define the map → traffic → accessibility → delayed development → demand objective. Bulk mesoscopic scaling, bottlenecks/bypass/induced demand, class/purpose/information, finite response and physical ledgers remain the scientific motivation. Exact IEEE event encoding may change storage without changing this objective. The changed-surface review must distinguish passive historical events from active completion ReceiptHistory and same-tick sinks. Their physical consumers remain intact. The historical blob identities and current PLAN 1.1.28 are recorded in BASELINE.json. No new DAG node or extra permission gate is introduced.

## C2 completed source map

The retained history owner is ServiceCheckpoint/NativeServiceCore in v1_journey.rs, not the physical completion ReceiptHistory. Road owns the exact time-run carrier and proposal; engine owns direct legacy decode/admission. Ownership: root v1_road.rs and run/test integration; bottleneck_anatomy v1_journey.rs and v1_engine.rs after the red fixture; other constructors supply read-only alternatives. The fixed codec preserves full event time bits and ordered sinks. Source product elimination remains a distinct obligation. Trace-count clarification: road-service incoming generation 17143679; pending additions 50728; total raw incoming 17194407; remaining live incoming at the actual indexed-sweep failure 16726314 after the first destination consumed 468093 rows. These scopes must not be conflated.

## C3: exact computational and ownership contract

The selected transformation is BYTE_IDENTITY of decoded logical rows and legacy checkpoint wire, and equality of all physical row operations. It is not a new closure. Write the event as e=(tag,source,destination,mass,start,end,birth). Compact registry indices are injective only in the checked u32 domain; the reserved destination value denotes None. Mass and birth bits are copied. Consecutive equal pairs of (start.to_bits(),end.to_bits()) share one dictionary entry. In particular +0 and -0 are different keys. The decoder returns the original ordered e exactly. Wide registries use the existing wide carrier, so no cast truncation is permitted.

For B=4096 rows/page, E logical events and K consecutive time runs, exact page payload is
M(E,K)=32 B ceil(E/B)+16 B ceil(K/B).
The retained charge adds actual outer Vec capacities, carrier/Arc metadata and page allocation allowances. A decode append must reserve against a conservative bound before allocating the next row/time page and its descriptor. Logical row count, physical storage bytes and wire bytes remain different quantities. Empty history, 4095/4096/4097 boundaries, all-distinct times, repeated times, signed zero, and wide indices are explicit cases.

The representation equation is decode(encode(events))=events. If H is stored history, X the active road/service/journey state and F the original transition, the encoded state update is (X,H_encoded) -> (F(X,decode(H_encoded)), encode(H_new)) on the common admissible domain. Source tracing establishes that previous observational H is not used by physical prepare/finish, but current-tick decoded sink events and active ReceiptHistory are used. Their tag, mass, end clock and order remain original. Validation/export/admission are real consumers and must be converted too. No event deletion or aggregation is authorized by this identity.

The road proposal returns the encoded carrier directly. Public standalone APIs keep their explicit Vec output, with page-plus-flat coexistence budgeted. Continuous keyset interning is moved into a common postroad helper parameterized by actual live candidate-event bytes; it still occurs before installing the candidate. Input/current event histories are counted once only when Arc::ptr_eq proves shared allocation. Two distinct histories in a multi-tick call remain two charged owners.

Error classification: the codec adds no truncation, interpolation, solver or floating arithmetic error. Original finite-response and f64 errors remain. A codec bit mismatch is an implementation error; an actual resource rejection is a resource result, not physical congestion or no-go. Metadata-only changes to source provenance do not waive raw checkpoint/hash checks.

A source-product followup must preserve intermediate IEEE operations. Combining scale factors is invalid: (0.1*0.3)*0.7 and 0.1*(0.3*0.7) can differ. Deferred incoming needs the original transformed key and source-order reduction, including its fsum barrier. An eager final interval output would remain a separate scaling issue. The held-characteristic flux-mean mark alternative is a model version, not part of this exact codec implementation.

C3 acceptance examples: legacy wire decode/re-encode byte identity; resource fixture with 65536 repeated-time rows must use less than 48 bytes per logical row including structural costs; original flat storage exceeds that bound. Test its failing behavior before production edits. Preserve wide fallback and malformed-input failure/rollback. Actual original checkpoint and increasing-horizon experiments will decide how far the new representation resolves the sequential bottleneck.

## C4: executable resource plan and observed RED

The original native extension was recovered from the verified selective archive into this checkout's native_binding. Its SHA-256 remains 22a7cebc751b575521a8360ab7e235aa7fa6fa9e4d54c8ac8904b35e708ae57a. The preserved baseline binary is also kept under retained_recovery_20261123/baseline_native. Imports succeed using the retained primary Python 3.12.13 environment; explicit PYTHONPATH selects this checkout. Cargo/rustc 1.99.0 and offline cached dependencies are available. The observed machine has 33,549,762,560 bytes RAM; execution uses measured availability, not the historical 64 GB hardware target.

The new native regression was executed before any production change:
cargo test --offline --workspace --lib retained_timed_event_history_contract_tests -- --nocapture
with CARGO_BUILD_JOBS=2, CARGO_INCREMENTAL=0 and RUSTFLAGS='-C link-arg=-lpython3.12'.
Actual cargo exit 101: legacy wire/IEEE/page-boundary test passed; the storage test failed with retained_bytes=4194432 against ceiling 3145728. This is the intended behavior/resource RED, not an import or compilation failure. Full log/argv/environment are in C4_RETAINED_EVENT_RED.log/json.

Execution dependencies: (1) root exposes road carrier and byte-bound helpers; (2) child integrates service history and engine decoding on disjoint files; (3) root builds and runs the same RED command to GREEN plus native owner/service regressions; (4) rebuild release budget_trace binary and bind it to clean committed source; (5) attempt original25700 -> 25710; (6) extend completed physical horizons to 25720/25750/25800 only after valid checkpoints, or repair the newly identified source lifetime before continuing; (7) fresh-source and fresh-process replay at the largest justified prefix. One native campaign runs at a time. Build jobs=2, native/BLAS/OpenMP workers=1; new run subprocess wall cap <=1800s, original 8GiB process cap unchanged. The full-day7200s criterion remains a separate unfulfilled release target.

The former S07 failed tick and S08 time-zero prefix have unchanged source/binary/input identities and are reused as baseline evidence. The actual new transition, RSS, event/history storage, checkpoint bits, physical ledgers and complete elapsed seconds must be newly measured. A first guard passing is not a complete tick. Source-row growth remains an explicit followup if the next result points to it.

## C5: native vertical slice implemented

The complete native path now retains Arc<ChunkedEvents>: road proposal -> current-tick sinks -> immutable service history -> engine validation/storage -> legacy writer, plus direct legacy read into the carrier. The public standalone road Vec API remains explicit. All original row arithmetic and ordered sink consumers are retained. Keyset interning now receives the actual encoded candidate-event cost and still runs after road temporaries expire. Decoder append checks are constant-time; snapshots preserve Arc identity; wide registries retain a wide representation.

The identical C4 Cargo command now exits 0: four tests pass, including the formerly failing repeated-time history cost condition, legacy byte/IEEE roundtrip across page boundaries, decode-budget rollback and wide-index preservation. Actual command/log and complete Rust file hashes are C5_RETAINED_EVENT_GREEN.json/log. Parent read the child journey/engine diff and integrated the road changes. Native whole-prefix and resource campaigns remain C6–C8 work, not implied by this component result.
