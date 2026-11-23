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
| C3 | Exact representation invariants, stable computation, failure counterexamples | PENDING |
| C4 | Bounded execution ladder, recovered native baseline, build/resource setup | PENDING |
| C5 | Complete native producer-to-consumer implementation | PENDING |
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
