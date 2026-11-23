# V03 coding reconstruction — 2026-11-23

## Final result

All ten requested coding reconstruction stages are complete and published individually on research/v03-coding-reconstruction-20261123. This is scoped research completion, not V03 release acceptance. The final source completes the original Valley checkpoint transition to25720 s; its fresh-from-zero path is independently verified through25710 s by complete wire and ledger equality. Current-source whole-calendar preparation is3/3. Original full-day completion remains0/9; V03 is BLOCKED.

The connected native changes are exact retained timed-event history, a compact timed incoming producer consumed directly without a decoded cell buffer, and a source-specific Uniform keyset workspace bound. Final checks are190 native tests passed (2 ignored),42 Python tests passed and16 finite old/new complete-state pairs, plus the4,011,233,450-byte original-city equality at25710. Later horizons, full-day repeats and large refined-dt acceptance remain unfulfilled. C8_COMPLETION.json, C9_COMPLETION.json and C10_RESEARCH_RECEIPT.json preserve the distinct claims and actual failures.

## C1: objective and preserved baseline

The user requests the complete coding C1–C10 track focused on the repeated V03 bottleneck. The source baseline is cd77044495598f4ddb28412f78241bd1eb98693c, which contains the completed theory R1–R10 and verified worktree cleanup. At entry, production source was unchanged from 492e27618696df2514b088a64de450cf69746647. This coding track uses the existing latest checkout on a dedicated branch; the two retained worktrees and selected compressed recovery files remain.

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
| C6 | Actual build, behavioral red/green, targeted native/Python regressions | COMPLETE; 180 Rust, 42 Python, matched old/new replay |
| C7 | Full-demand original checkpoint continuation and physical ledger checks | COMPLETE; original 25710 state valid, next source failure isolated |
| C8 | Increasing horizons, matched correctness/resource/replay experiments | COMPLETE; resumed25720, fresh25710 exact, three full-calendar preparations |
| C9 | One independent review of changed scientific and runtime surfaces; repairs | COMPLETE; fresh scoped review, no P0–P3 finding, original V03 still blocked |
| C10 | Final readiness/evidence, reusable latest checkpoint, exact next action | COMPLETE; PLAN1.1.29 validated, readiness and remaining owner/source blockers recorded |

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


## C6: actual regression and native binary binding

The complete Rust library suite exits 0: 180 passed, 0 failed, 2 explicitly ignored. The release budget_trace build exits 0 (22.82 s); the rebuilt extension SHA-256 is 676d1bd7a5b4ba43440f14f26d0e468df32ab983e3ef058114e25c95cd2d393a. The four affected Python suites (owner storage, native engine, whole driver, journey) exit 0: 42 passed in 1.97 s. Exact argv, environment, actual child return codes and logs are retained in the C6 artifacts. C6_PROVENANCE.json binds the clean production source, extension and replay script.

A separate-process old/new experiment uses the existing mixed road/bus fixture through 120 physical seconds under both legacy_records and bounded_bytes_v1. There are ten nonempty-event ticks in each lane. All eight sampled legacy checkpoint byte hashes and physical report tuples per policy agree between binaries. Batched evolution and fresh-engine restore at t=15 agree with the stepwise t=120 wire; retained earlier snapshots remain unchanged. The old bounded lane records 345 internal flat-event materialization guard calls, and the new lane has none. This finite compatibility experiment is not a speed benchmark or a large-city acceptance result. It verifies the connected internal path, not merely an isolated codec.

No equations, units, initial or boundary conditions, calendars or closure parameters changed. Exact storage claims are implementation-verified; the original full-demand continuation remains the next empirical gate. Original motivation and acceptance are preserved, including active completion history and same-tick sinks.


## C7: original full-demand transition completed; next source failure isolated

The new binary restores all 3,405,043,386 bytes of the original t=25700 checkpoint, verifies its SHA and exact full-wire re-export, and completes t=25710 under unchanged RLIMIT_AS=8GiB, original calendar/driver identity and numerical rules. The completed tick takes 30.644343209 s in the native kernel (segment including validation32.881780162 s). The complete restore/attempt/evidence campaign takes137.611017781 s with measured peakRSS4,245,573,632 B. This is one completed original physical tick, not merely a passing allocation guard.

The vehicle residual released-active-completed is -4.263256414560601e-14 vehicles; the person residual is 5.684341886080802e-14 persons. Requested-released-pending is zero for both; cargo is zero in this selected case. Engine validation and the driver population/ledger checks pass before saving the completed state. The new raw checkpoint is4,011,233,450 B, SHA64b77baece5ba45fa0928d59b58d9f8f9fc2178bcd93542b05264736978733fe; the compressed reusable copy is865,480,229 B. Active physical completion history, route/source tags and FIFO remain original.

At the formerly failing indexed-sweep guard, the actual charge falls from5,051,633,256 to4,592,964,400 B: a source-bound reduction of458,668,856 B. The completed tick retains17,429,035 event rows in561,521,000 B including structural costs. This verifies the constructive codec benefit in the actual whole native path. No speedup ratio is inferred from comparing an old failed attempt with a new completed tick.

The requested next horizon t=25720 fails earlier, at transfer candidates:4,921,327,872 B required against4,921,274,823 B available;16,426,959 live incoming rows have been generated at that point. The first tick grows road composition rows34,610,422 ->40,717,830 (+17.6462%). Thus the source product remains the bottleneck. A by-class reduction or combined-vector reduction happens after this failure and cannot justify a credit here. C8 must act on the incoming producer representation or actual immutable source owners, preserving ordered IEEE operations and original physical demand. Horizons50/100 s were requested but were not executed. V03 remainsBLOCKED; full-day0/9; scoped-or-acceptedDAG19/21.


## C8 source producer reconstruction (implementation checkpoint)

The C7 next failure is addressed at the actual incoming producer. In the bounded interval path with checked compact registry indices, an incoming row is now32 B (tag,offset,control ID,mass,birth); a shared append-only32 B control stores the exact endpoint, speed and latent bits. Within one road serve, Motion and local_mid are held, speed is common and latent is class-specific; one control per used class is sufficient. Pending marks obey the analogous class-constant rule. All original fraction, midpoint, mass/birth, route-offset and per-row physical ledger operations stay in place. Noninterval/unbounded/wide sources retain the old carrier.

If P is the total number of128-row incoming pages and H the number of controls, the payload changes from56*128*P to32*128*P+32*128*ceil(H/128). Actual page/header growth and allocation allowances are separate. This is a representation identity, not a new physical closure or an altered sum. A single destination is decoded into the old Part+Mark sequence before the unchanged ordered mark reductions, combine and interval consumer. Encoded and decoded cell owners are both charged until both are actually dropped. The control table stays charged until every cell finishes and is explicitly dropped before final state validation. No base allowance or acceptance cap is reduced to force passage.

Source implementation and connected tests pass:188 Rust library tests (2 pre-existing ignored),42 affected Python tests, and16 old/new finite checkpoint/physical state pairs with batch and restart equality. Descriptor growth, signed zero, subnormals, compact-domain rejection, move/drop ownership and encoded+decoded coexistence are covered. The rebuilt extension isddc0a92b074422786d906b69b5941cbd6271563d987f8502ea4e1c6b5d21f9a6. Large native continuation and fresh-source replay are still pending at this implementation checkpoint.


### C8 observed consumer obstruction and surgical revision

The first timed-producer campaign restored the t=25710 checkpoint with exact wire/ledger identity. It generated all19,989,328 incoming rows using251,957 controls:650,375,168 B of timed payload versus1,124,042,752 B for the same logical pages in the old Part+Mark format, a473,667,584 B structural payload saving. This is a same-row representation comparison; it is not a measured full-run RSS difference. Sparse control pages can cost more on tiny inputs.

The run still completed no new tick: one-cell materialization required4,959,061,048 B against4,952,574,903 B (+6,486,145 B). Its actual receipt is preserved as C8_timed_incoming_continuation.json, statusBLOCKED_RESOURCE; it must not be reported as25720 success. This new diagnosis led directly to removing the decoded cell buffers altogether. The physical weighted speed and class input moments now iterate the timed source directly. A single combine_indexed_parts(len,get) implementation preserves the original key, source-index tie order, separate mass/birth sum barriers and final total ordering for both carriers. The timed source remains charged until all these reads finish; only then is its actual owner dropped and accounting released. No numerical operation, base credit, resource cap or original physical input was changed.

The direct-consumer revision again passes188 Rust tests,42 affected Python tests and16 old/new finite wire/physical state pairs including batch/restart. New source access tests cover nonsequential indices and page boundaries, and workspace tests enforce source charging until direct combine finishes. Its rebuilt binary SHA isf323db6e99a3b8956ad6cc47b6443a2c96c9f04b182ac444e5f219f4557a2de0. The next large experiment is a new run with this revised source, not a repeated identical failing input/code pair.


### C8 source-specific keyset workspace correction

The direct-consumer campaign passes source generation and interval consumption, but the post-road keyset allocation rejects the still-uncommitted25720 candidate:5,306,343,016 B required against4,952,574,903 B. The completed state remains25710; C8_direct_continuation.json preserves this failure. The candidate has47,855,028 rows classified by debug_stats as uniform, a statistic that includes both Uniform and already-SharedKeys rows.

Actual intern_exact_keysets allocation is more specific: new canonical keys allocate at most8 B per Uniform row and new moments at most16 B per Uniform row. Existing SharedKeys only clone/replace a key Arc and retain their moment Arc. Thus the conservative additional row workspace is24*N_Uniform, while the complete retained-owner sum, old and candidate events,512 B metadata for EVERY packet, and96 B fixed allowance remain. The code now counts only source variants that actually allocate new row payload. It neither skips interning nor changes caps or physical values. Tests demonstrate exact logical bits and preservation of pre-existing SharedKeys moment allocation identity through interning.

The corrected source passes190 Rust tests (2 unchanged ignored),42 affected Python tests and16 old/new finite full-state comparisons. Binary SHA96e8e20ab30b2345223d326225abfab274997b5269e262bda9be74893fd32b8c. The research runner also accepts explicit completed-state comparison receipts, checking full wire, physical ledger, original matrix, driver and requested absolute horizon; this enables a later time-zero run to compare earlier successful checkpoints without creating duplicate raw files. Actual corrected large-horizon results remain to be measured.

## C8 completed experiments and measured limits

C8 is complete as a coding research stage. The final production commit is bec506abb5247e76e8f74e2846eedf9e1c5c501a, candidate source SHA796849f703f909911dc8c4968252e27189f21cd4dafab3e700bbb27d8c7d1f3d and native SHA96e8e20ab30b2345223d326225abfab274997b5269e262bda9be74893fd32b8c. C8_COMPLETION.json binds the actual receipts, commands, test logs, preparation and source identities. V03 remains BLOCKED.

| Candidate and initial state | Last completed physical time | Campaign wall seconds | Peak RSS bytes | Next observed result |
|---|---:|---:|---:|---|
| Retained events; original25700 checkpoint | 25710 | 137.611 | 4,245,573,632 | transfer candidates at25720 |
| Timed producer + cell materialization;25710 checkpoint | 25710 | 171.725 | 3,882,655,744 | cell materialization at25720 |
| Direct timed consumer;25710 checkpoint | 25710 | 143.764 | 4,406,870,016 | keyset workspace at25720 |
| Source-specific keyset bound;25710 checkpoint | 25720 | 186.312 | 4,410,376,192 | transfer candidates at25730 |
| Final code from time zero | 25710 | 321.272 | 4,271,484,928 | direct combine at25720 |

Campaign wall includes construction/restoration, attempted transitions and evidence/checkpoint work; it is not pure simulation time or a matched speed benchmark. The successful25720 native tick is30.508662402 s, and its complete segment is32.707335195 s. The fresh0-to25710 segment is262.514087812 s across2571 completed ticks. No full-day wall estimate is extrapolated from these different segments.

In the successful resumed25720 transition,21,574,847 Uniform rows can create new key/moment payload;26,280,181 already-SharedKeys rows cannot. Correcting only that source-specific allocation count removes630,724,344 B of nonexistent extra workspace from the bound, reducing the keyset requirement to4,675,618,672 B below4,952,574,903 B. All retained owners, events, per-packet metadata and the original ceiling remain charged. This is a source-derived accounting correction, not an RSS reduction claim. The complete original physical transition then succeeds, with the existing engine and ledger checks. The valid25720 checkpoint expands to4,677,350,066 B, SHA447570b8721b17fa19edf159bc4c474cfd6ad41dc936ab0b0114d902e36f0bf9, and is retained compressed as C8_keyset_continuation.final.bin.gz.

The final-code time-zero run independently reproduces all4,011,233,450 bytes of the25710 checkpoint and its complete physical ledger, SHA64b77baece5ba45fa0928d59b58d9f8f9fc2178bcd93542b05264736978733fe. Its next25720 transition is nevertheless resource-blocked: direct combine requires4,925,982,264 B against4,850,460,087 B. The resumed path's corresponding requirement is4,925,817,240 B against4,952,574,903 B. Therefore25720 is verified by checkpoint resume, while continuous execution from zero is verified through25710 only. The runner's planned second reference comparison at25720 was unmet; the orchestration assertion and actual valid prefix are preserved in C8_FINAL_VALIDATION_OUTCOME.json. This is not a numerical mismatch or a completed fresh25720 run.

The allowance delta is102,114,816 B; the road requirement delta is only165,024 B. The same shared dynamic total is5,789,366,871 B. Source tracing reduces the allowance difference to three times a34,038,272 B difference in the maximum retained/current/pending journey stage-plus-history structural cost. The present trace does not expose which max input owns that difference. This owner is UNRESOLVED, not attributed to road packet slack without evidence. Comparing a trace aggregate maximum from the later25730 attempt to the25720 attempt would mix scopes.

The resumed run next fails at25730 transfer candidates: required4,833,535,616 B against4,833,535,143 B. The473 B excess is only the first incremental guard crossing; it is not the full memory deficit for finishing that tick. Permanent road composition rows grow34,610,422 ->40,717,830 ->47,855,028 at25700/25710/25720. The exact transient representations and source-specific allocation fix remove real obstructions, but do not eliminate the composition-times-service or composition-times-interval products.

After the fresh-run limitation was recorded, the original preparation CLI ran separately on the same clean source and binary. All three complete calendars are prepared under the original8GiB process limit, with100000 resident stock each:

| Case | Calendar legs | Preparation wall seconds | Peak RSS bytes | Physical simulation seconds |
|---|---:|---:|---:|---:|
| River weekday s17 | 5,093,765 | 69.509 | 2,177,441,792 | 0 |
| Coastal weekend s41 | 2,449,750 | 39.722 | 1,119,133,696 | 0 |
| Valley weekday s7 | 918,450 | 21.024 | 450,281,472 | 0 |

Total calendar legs are8,461,965. Preparation3/3 is not full-day completion0/9; calendar person-trip quantities also are not resident stock. The final source passes190 Rust tests (2 ignored),42 Python tests and16 old/new complete finite wire-and-physical records with batch/restart equality. These checks do not substitute for the uncompleted large fresh25720 comparison, refined-dt study or original three-repeat full-day release.

Drift watchdog: no population, departure calendar, route legality, FIFO boundary, finite-response law, physical ledger, numeric tolerance or release limit changed. The source sharing and direct consumer preserve original ordered operations, so no model variant was silently introduced. The original coupled urban objective remains intact; current progress is implementation-verified exact representation and scoped physical execution, while full-scale completion remains resource-blocked.

## C9: independent changed-code review completed

One fresh independent reviewer inspected the actual changed native surfaces and source/binary bindings. Actual new materialization and keyset failures prompted narrow reviews of the resulting repairs in the same report, not a recursive review tree. The final reviewed production commit is bec506abb5247e76e8f74e2846eedf9e1c5c501a. The reviewer found no supported new P0, P1, P2 or P3 defect in that scope, independently compared all16 complete finite old/new state records, and checked the190-pass native/42-pass Python evidence. The retained-history semantics, active completion history, exact timed controls, source liveness, page/header bounds, direct ordered combine and Uniform-only new keyset payload bound were explicitly inspected.

The full report is V03_CODING_C9_REVIEW_20261123.md, SHAaa304a0aa52f8bc13e8fbfbe8f2347ca2ff234bc62b6410dae801df0b9d90d5a. C9_COMPLETION.json binds the final reviewed source and root's separately recorded C8 experiment supplement. The reviewer did not certify the subsequently completed large25720 continuation or fresh time-zero campaign; those conclusions come from the actual root-run receipts in C8. No further code edit or new test/permission gate was requested. Original V03 remains BLOCKED, and the uncompleted fresh25720 comparison and nine full-day runs remain explicit limitations.

## C10: final readiness, authority and concrete continuation

The requested coding track is10/10. The execution authority is now PLAN1.1.29. Actual render, validate and next commands all exit0; validation reports VALID_PLAN_NOT_RELEASE with21 nodes and V03 as next. C10_PLAN_VALIDATION.json binds the exact plan and command outputs. Node statuses, original requirements, numerical contracts and release gates are unchanged.

| Scope | Achieved / required | Meaning |
|---|---:|---|
| Requested coding reconstruction | 10 / 10 | Actual implementation, failed/successful experiments, review and publication stages |
| DAG scoped implementation or accepted nodes | 19 / 21 (90.48%) | Receipt-bound VERIFIED_SCOPED or ACCEPTED; not release acceptance |
| Finally accepted DAG nodes | 5 / 21 (23.81%) | Existing accepted nodes; no promotion from these experiments |
| V03 dependency nodes P01/V01/V02 | 3 / 3 | Scoped dependency evidence is present |
| Latest-source complete-calendar preparations | 3 / 3 |100000 resident stock each;8,461,965 planned legs total; simulation0s |
| Original full-day matrix | 0 / 9 |86400s each,3 cases×3 repeats, original8GiB and7200s |
| Latest-source Valley continuous from zero | 25710 s |Complete wire and physical ledger matched at25710 |
| Latest-source Valley checkpoint resume | 25720 s |One complete extra tick from the verified25710 checkpoint |

The original25700 recovery,25710 checkpoint and latest25720 compressed checkpoint remain available. Fresh and C7 copies of the identical25710 gzip were independently streamed through SHA-256 and consolidated by an atomic hard-link replacement. Both receipt paths and all compressed bytes remain unchanged;865,484,800 exclusive allocated bytes were released. C10_STORAGE_CONSOLIDATION.json records the operation. No new worktree was created; the previously retained two remain.

The immediate next native diagnostic is bounded to the journey road-allowance boundary and journey decode/restore boundary: record each input/current/pending stage/history cost, capacities and argmax. The102,114,816 B allowance difference is already attributed algebraically to3 times a34,038,272 B journey maximum difference, but the responsible actual owner is unresolved. Correct only demonstrated lifetime/capacity mismatch or implement an exact canonical paged carrier, with transient coexistence charged. Equal checkpoint wire alone does not establish equal allocation layout.

The larger constructive continuation is persistent immutable source/ordered-scale/interval-span storage integrated with its real weighted-moment, ordered-combine, interval and checkpoint consumers. It must avoid rebuilding all composition rows per service or interval while retaining the original sequential IEEE factors, per-stage positive-mass tests, source keys and fsum barriers. This is a proposed next implementation, not a claimed completed native feature or a universal complexity result. Re-test the new source at the unmet fresh25720 comparison and the next original25730 tick before increasing later horizons. A controlled closure remains a separately versioned research option requiring coupled-observable error evidence; it is not an implicit change to original V03.

History watchdog reuses the original0492364 PRD/spec and6524500 constitution blobs, bound in C10_RESEARCH_RECEIPT.json. The coupled map/traffic/accessibility/development/demand motivation, finite response, legal FIFO routes and physical ledgers are preserved. The remaining limitation is representational growth and resource admission, not evidence of physical impossibility. Full CI/main integration and release remain deferred under the current execution policy.

### Stage publication provenance

Each stage has its own published completion commit. C8 also has three source-repair commits because actual successive failures required further code changes before its experiment closure.

| Stage | Completion commit |
|---|---|
| C1 | 90be3dd364c4483a0787dd93aec45af8ab3d0494 |
| C2 | dbd4fb9b3af7cb66cfaa2e00b4da7d8ea1d5f568 |
| C3 | 791ad4df3d2c4155f9b680ffb6d9729799924166 |
| C4 | 9f199e6626edd71a7bd0b354e213f3598ed65ef9 |
| C5 | 6568887e0d974bc700b7002efe30a3ed25bae76d |
| C6 | 70325da301b5207f434c921411b8052aafa0a43f |
| C7 | 7154fc75b7062425f2d892b2f9c601ad25956487 |
| C8 | 0bbac143444fc16978433a5d2e316fcf97542be9 |
| C9 | 25f30d15f4a6ed6645a429a0868ee6b56078a49f |
| C10 | The commit containing this final section and C10_RESEARCH_RECEIPT.json; exact remote SHA recorded after push in the session and response |

C8 intermediate source repairs:9c02161cde99c7fce378d805ac179fd1689e01b1 (timed producer),66128cd142f555470c22b27e8843a9d31fd834aa (direct consumer),bec506abb5247e76e8f74e2846eedf9e1c5c501a (source-specific keyset allocation). These changes remain on the research branch; no main merge or full-release certification is implied.
