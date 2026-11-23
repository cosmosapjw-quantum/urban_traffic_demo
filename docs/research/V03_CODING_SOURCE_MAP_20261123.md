# MetroFlow C2 — retained timed-event path and implementation boundary

2026-11-23. Author packet: `/root/bottleneck_anatomy`. One read-only source pass, reusing the previously established anatomy and S07/S08 receipts. No build, new simulation, large checkpoint decode, or remote mutation was performed for this note. The parent owns C1–C10 implementation and execution.

## Result and scope

The useful first implementation is to keep the already existing exact timed-event carrier alive as immutable service history, including when reading an old checkpoint. Connect that carrier to all internal consumers without an intermediate flat `Vec<EventRow>`. These are two coupled code slices: direct old-history decode/storage, and candidate/consumer retention through the whole native transition. Root selected this route after the source trace.

This changes representation, not the physical transition. It removes a measured old-history allocation that is large enough to matter at the first 25,710 s rejection. It does not reduce physical `Part` rows, source proportional-serve multiplicity, or active-row × interval output. The next complete tick is an empirical obligation, not implied by the first guard's counterfactual.

## Authority and identity

Read-only baseline checkout: `/home/cosmosapjw/urban_traffic_v03_bottleneck_theory_20261123`, HEAD `cd77044495598f4ddb28412f78241bd1eb98693c`; tracked worktree was clean at inspection. This is the current checkout; the previous causal-rank checkout was deleted. Source below is byte-identical to the previous native baseline at `492e27618696df2514b088a64de450cf69746647` and to the source used by S07/S08. A new implementation will require its own source/binary identity.

| Source | Git blob | SHA-256 |
|---|---|---|
| `crates/metroflow-rust/src/v1_road.rs` | `f2d2031e8710b57b6b1be430ece7695430c19eb3` | `f27ccbee4472472b5e59995de9bf64cc00a7cb042202d15b073ab5aad176983e` |
| `crates/metroflow-rust/src/v1_journey.rs` | `34a0e1fc2841a1dba29684c77e1c0e15aa69c5df` | `4d19e125e72137b0116e1b6119427061580ebb013b1fc8a1166d762c1b03bc83` |
| `crates/metroflow-rust/src/v1_engine.rs` | `d245c93936f8210db36cad88fab458b2dc9800cf` | `ea4986c416efef387fe2962d70b7f9ee241c6f414ce594ac493891632d869cda` |

Current `AGENTS.md` SHA-256: `d6447a84c49f4a673e6e0188cf18bd6296f650d8bb68f816f33521224fbcce60`. Current user coding request authorizes constructive repair, while original 100k / 24 h / 3 cases × 3 repeats / 8 GiB / 7,200 s targets stay fixed. Local success is not full acceptance.

`artifacts/v03_causal_rank_20261123/S07_original_continuation.json` SHA-256 `38e15baaf9555cd0c5fae2e55f6c51fbb3e04d9642acb690ad9597ed51e1e4b9`; `S08_time_zero_prefix.json` SHA-256 `a7bdfb8c5e016b39685b20a33ae8722ba69ad44ba252bbbcf3f586c5f0a4f79b`. Their native binary SHA-256 is `22a7cebc751b575521a8360ab7e235aa7fa6fa9e4d54c8ac8904b35e708ae57a`, with candidate source fingerprint `bea107c2888885966c901a0f30a6d7edcb50a24e5cbbbe31d3f8bf020536943d`.

## C2 mapping: physical quantities and passive event history

The road event is `(tag, source, destination, mass, start, end, birth)` (`v1_road.rs:69`). Tag and cell indices are discrete registry identities; `mass` is vehicle mass/amount and times are seconds. Optional destination `None` means a road sink. The event row is 64 bytes on the recorded x86_64 target. The physical road state and proportional-serve order remain unchanged. The map → traffic → accessibility → lagged development/future demand construction is preserved, including classes, purposes, finite response, and person/vehicle/cargo ledgers.

The road step builds events at `step_state` (`v1_road.rs:3499–4346`): head compositions around 3699–3716 determine destination fractions; proportional serves at 3911–4033 emit each affected row at 3984 and build incoming/mark data. `interval_packets` at 3171–3322 sorts/indexes incoming rows and combines active physical cores over intervals. This is the source of repeated physical row materialization. Changing retained event history leaves those computations and their numerical order unchanged.

`Service` (`v1_journey.rs:25`) is the physical run/person/freight/car state. `ServiceCheckpoint` (`:26`) is `(Service, Arc<Vec<EventRow>>)`. In particular, `Service.1` is the person state; `ServiceCheckpoint.1` is the observational event history. They must not be conflated.

The exact prior-history read sites were searched using `rg -n -F last_events crates/metroflow-rust/src`. They are storage accounting (`:429`, `:1434–1441`, `:1528–1531`), immutable snapshot/rollback (`:472`, `:476`), checkpoint writer (`:513–523`), explicit Python publication (`road_events`, `:719`), and initialization/replacement (`:702`, `:725`, `:1748`), plus ownership unit tests. Engine validation reads `b.service.1.iter()` (`v1_engine.rs:1127–1135`); debug export reads its length (`:1564`). No previous `last_events` values are read by `NativeServiceCore::prepare` (`v1_journey.rs:731–788`) or `finish` (`:790–844`).

The current tick is different: `advance_owned_joint` obtains events at `:1550–1552`, filters destination-None rows in original order at `:1614–1621`, calls `service.finish(end, sinks.clone())` at `:1626`, and `journey.finish` at `:1655`. Each sink retains tag, mass and end time. They are physical inputs to this tick's service/journey completion and egress construction. The replacement must decode them exactly in order, not aggregate tag rows or discard event end times. Physical `ReceiptHistory` and dwell eligibility remain untouched (`eligible` at `:871–875`, history threshold logic in `v1_history.rs`).

Thus, on a common admissible resource domain, exact decoding of retained history preserves future physical evolution. Resource admission and publication can still depend on the representation. This proof does not license arbitrary event deletion, changed wire output, or treating physical receipt histories as passive.

## Actual allocation arithmetic

The existing timed carrier (`v1_road.rs:480–608`) stores each logical row in 32 bytes plus a 16-byte `(start_bits, end_bits)` pair per consecutive time run. Bit equality, not numerical equality, defines a run. Fixed page size is B = 4096. If E is row count and K is time-run count, its payload capacity is

`M_payload(E,K) = 32 B ceil(E/B) + 16 B ceil(K/B)`.

This excludes descriptors, the carrier object, Arc control block and allocator/accounting padding; actual guard credit must include these. `physical_capacity_bytes()` at `:527–534` and `descriptor_capacity()` at `:522–525` expose actual capacities. The current projection at `:637–647` separately includes descriptor allowance and 192 bytes of metadata.

| Existing measured history | E | K | Flat payload, bytes | Timed payload, bytes | Payload difference, bytes |
|---|---:|---:|---:|---:|---:|
| S08 retained history at 25,700 s | 14,432,257 | 179,947 | 923,664,448 | 464,781,312 | 458,883,136 |
| S07 candidate for attempted 25,710 s | 17,429,035 | 206,999 | 1,115,458,240 | 561,184,768 | 554,273,472 |

The old flat retained structural charge is 923,664,576 bytes including its existing 128-byte nonempty allocation padding. S08 has 3524 event pages and 44 time pages; S07 has 4256 and 51. These are bounded calculations from recorded counts, not a benchmark of the new code.

S07 first rejected guard was 5,051,633,256 bytes against a dynamic phase allowance of 5,025,214,575: excess 26,418,681. Subtracting only the old-history payload difference gives a counterfactual 4,592,750,120 bytes, leaving 432,464,455 before the metadata delta. This is evidence of leverage at that guard, not proof of tick success. Even zeroing the 13,723,920-byte index extra would leave 12,694,761 bytes over the original allowance, so optimizing only that index is insufficient.

S07 recorded 34,610,422 cell part rows (`trace.counters["tick.cell_parts"]` sum), 631,350 cell packets (`trace.counters["tick.cell_packets"]` sum), and 258,022 serves (`trace.counters["xfer.serve_rows"]` call count). These are different storage objects. Served road-transfer incoming is 17,143,679 (`trace.counters["xfer.serve_incoming_rows"]` sum; also `trace.sites["road_actual:transfer buffers"].terms_at_max.incoming_len`). Pending admission contributes 50,728 (`trace.counters["pending.rows"]` sum). Their sum 17,194,407 is the full raw incoming count at the maximum transfer-candidates guard (`trace.sites["road_work:transfer candidates"].terms_at_max.incoming_rows`). After the first source cell's 468,093 raw rows are released, 16,726,314 raw rows remain at the actual failed indexed guard (`trace.sites["road_work:indexed sweep preflight"].terms_at_max.incoming_rows`). Thus 17,143,679 and 17,194,407 describe different scopes; neither is the remaining raw row count at the failure itself.

The road vehicle amount was 778.5767388933845, while journey active amount was 1234.1174136872016; the latter has a different scope. Counts of rows are representation counts, not physical vehicle count. Retained compression does not alter these row-producing mechanisms. The recorded wall time 55.97997 s and RSS 4,324,171,776 bytes belong to the old failed tick; no timing or RSS prediction for the new implementation is claimed.

Wire remains legacy `MFWHOLE1`. The event section is `8 + 64 E − 8 Z` bytes for Z sink events (destination absent). For the S07 candidate, Z = 285,356 and that section would be 1,113,175,400 bytes. Streaming encoded rows into that same wire does not reduce file bytes; it avoids the large in-memory flat event array. It also avoids allocating 1,115,458,240 candidate flat bytes while encoded pages are still alive in `into_flat_checked` (`:597–608`).

## Minimal file ownership and API contract

No new carrier module or `lib.rs` change is needed. The carrier is already in `v1_road.rs`; expose it at crate scope and keep its fields private. The parent can own that file, while this child can own `v1_journey.rs` and `v1_engine.rs` when explicit edit ownership is assigned.

Road-owned surface:

- Expose `ChunkedEvents` plus `new`, `len`, `iter`, `push_checked`, and a structural retained-storage byte method. The iterator yields original `EventRow` values in order without allocation. Constructor/domain selection must preserve wide `usize` rows.
- Change only `propose_owned_step` (`:3028–3035`; one actual caller at journey `:1550`) to return `(RoadState, ChunkedEvents)`. Keep standalone `owned_step` (`:3018`) and its explicit flat public result compatible.
- Split exact keyset interning out of `materialize_event_after_road` (`:2950–3015`). The encoded proposal must still run keyset interning and charge live encoded candidate pages; it cannot reuse the old assumption that pages died at flatten.
- Expose an exact pre-append capacity bound suitable for checkpoint decoding, including descriptor growth. Current `projected_candidate_bytes(1,start,end)` can supply a bound in compressed mode, but structural carrier/Arc accounting must be included consistently. Keep public materialization guarded for page-plus-flat coexistence.

Journey-owned surface:

- Change `ServiceCheckpoint` and `NativeServiceCore.last_events` to `Arc<ChunkedEvents>`. Empty history, snapshots, rollback and replacement keep Arc-only sharing. Do not add a deep `Clone` implementation used by snapshots.
- Replace flat-storage byte formulas at `service_event_storage_bytes`, `event_storage_bytes`, call-input/current accounting and candidate accounting with physical capacity plus metadata.
- Decode each legacy event row directly into the carrier in `read_state` (`:527–602`), checking each proposed byte allocation before append. This must happen on initial load so the old history is already compact before the 25,710 s road step. There is only one production caller: engine `:1805`.
- Pass known registry compact eligibility from engine; current road eligibility (`v1_road.rs:2835–2840`) requires tag and cell registries < `u32::MAX`. A `u32::MAX` destination is reserved for None. Preserve a wide carrier when source domain cannot fit; never truncate indices. Invalid imported binding is still rejected. Time-run index overflow must remain explicit.
- Stream `iter()` for checkpoint write, sink extraction and explicit Python export. The export may deliberately construct its requested Vec; it must not be used as an internal helper. Preserve full row order and IEEE payload bits.

Engine-owned surface:

- `validate_bundle` already uses `.iter()`, so switching iterator item from borrowed tuple to copied tuple should require no physical logic change.
- `load` (`:1788–1805`) currently derives an event row cap using remaining bytes / 3 / 64 and calls the flat decoder. Separate logical row limit from structural carrier byte limit. `self.event_limit` remains a logical guard; capacity admission must use actual encoded/wide pages and metadata, including old resident history and transient growth. Do not silently credit unknown compression.
- After direct decode, continue using actual `service_event_storage_bytes` for journey decode and full storage admission (`:1806–1827`). Capture/restore must preserve Arc ownership.

Only pointer-identical input/current histories can be counted once. Within a multi-tick call, `call_input_events` survives every tick. After one commit, current history differs from input and both can remain live. Preserve `Arc::ptr_eq` and charge the two real allocations. Immutable sharing already exists for flat histories; the new saving is encoded physical storage, not invented extra aliasing.

## Meaningful tests and next execution

Existing tests to reuse after integration:

- Rust `exact_event_time_run_tests`: repeated time pairs, append projection, original input/current bytes, distinct IEEE bits and page boundaries. `exact_paged_event_candidate_tests` preserves tuple bits/order. `exact_compact_candidate_event_tests::wide_default_legacy_event_rows_remain_valid_without_truncation` protects the wide domain.
- Rust `event_snapshot_arc_ownership_tests::{captured_snapshots_and_committed_service_share_event_backing,replacing_event_backing_preserves_previous_immutable_snapshot}`; adapt fixtures to the carrier, preserving the assertions.
- Python `tests/v1/test_native_owner_storage.py::test_native_binary_roundtrip_is_byte_exact_for_active_and_receipt_states` and `test_invalid_native_checkpoint_does_not_replace_current_owner_state`.
- `tests/v1/test_native_engine.py::test_native_whole_mixed_initial_progress_branch_and_restart`, `test_native_whole_assignment_preserves_fsum_at_large_dynamic_range`.
- `tests/v1/test_native_whole_driver.py::test_driver_checkpoint_restarts_in_fresh_runtime_and_preserves_old_snapshot`.
- `tests/v1/test_native_journey.py::test_native_service_proportional_boarding_partial_sink_and_dwell`, `test_native_egress_preserves_whole_journey_delay`, `test_native_service_bad_finish_preserves_committed_state`.

Add only concrete missing coverage: legacy wire → direct encoded decode → byte-identical wire with nonempty mixed sink/nonsink data; signed-zero time bits and pages 4095/4096/4097; nonempty input/current histories across two ticks in one call versus separate calls; decode budget failure leaves the old committed owner intact; internal whole transition does not invoke flat materialization. A fixture with nontrivial journey sinks checks that the observer/current-tick boundary was implemented correctly.

Then root should run the unchanged original 25,700 s checkpoint through a complete attempted 25,710 s tick with rebuilt binary provenance and fixed limits. Record all resulting guards, complete-tick ledgers and checkpoint writability. If a later source/consumer guard becomes the blocker, preserve it as the next concrete failure and repair that source path. Do not call 25,710 s solved just because the initial indexed guard passes. No extrapolation of local growth to a 24 h acceptance claim is justified.

## Evidence status and commands

Source/caller mapping and old receipt values: established from exact read-only sources. Integer allocation formulas: derived and calculator checked. New compressed persistent implementation, full-tick success, timing and memory savings: NOT_RUN in this packet. Original full-day acceptance remains unresolved.

Latest bounded read used Remote Desktop Commander on device `edd1b263-56a0-4391-8a2a-677dd00eabf5` with `python3` to read exact file line ranges and `subprocess.run(['rg','-n','-F', pattern, 'crates/metroflow-rust/src'], cwd=repo)` for `service.read_state`, `last_events`, `propose_owned_step` and `fn push_checked`. It did not import native modules or checkpoints. Numeric checks evaluated the explicit integer page formulas above. Earlier anatomy files retain the broader source extracts and history: `metroflow_theory_anatomy.md` and `metroflow_theory_anatomy_evidence.json`.

## skill_context_used

PhysMath Research Loop **1.3.0**, package `skill://plugins_6acdfbba921881919e0c17843706aef4/physmath-research-loop`. Read main `SKILL.md`, selected C2 definition in `references/CODING_LOOP.md`, and `references/POLICY_INTEGRATION.md`.

Selected-stage excerpt: “C2: Map theory formulas, normalization, time variables, IC/BC and closure to exact code functions and data inputs. Check source revision and authority first.” The skill's bounded-pass excerpt is “Use one production/verification pass and at most one risk-justified fresh-context review, not a recursive reviewer tree.” Integrated policy requires checkpoint reuse, typed identity, unchanged user-locked tolerance, and the smallest test that can falsify changed behavior. This note applies those instructions to the parent-assigned C2 packet; it does not assert completion of other C stages.
