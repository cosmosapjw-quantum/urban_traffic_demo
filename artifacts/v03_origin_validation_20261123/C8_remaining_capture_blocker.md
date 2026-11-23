# C8 remaining blocker: outer capture/validation

Read-only diagnosis, 2026-11-23. No native/source edits, Cargo execution, replay or additional full-size diagnostic was performed for this note.

## Established by the final-native receipt and source

[R8_final_frontier_25730_10s.json](R8_final_frontier_25730_10s.json) identifies source `78b49811dd84544e3c5dcd4281c3918fc41384fc1815941792a90ccc58bde3f7`, native `3bec7cd5cb788047c95a1f55464af9baed28699ace086bc8fd13fe342c2b08d5` and commit `64173178d11229825efc553c441f6f90c7541979`.

The normal, non-diagnostic call from 25730 to 25740 s reports **successful_ticks=1, failed_ticks=0**. Thus the internal coupled transition and its revised checkpointability gate completed. The subsequent error is:

```
native capture/validation storage budget exceeded:
required_bytes=6887244069, budget_bytes=6442450944
```

Excess: **444,793,125 B**. Whole-call wall time is 209.86881164298393 s; peak RSS is 4,997,935,104 B. No new NativeWholeState was returned normally, no output checkpoint was written, and the runner grants **0 new validated seconds**; its last returned/validated clock remains 25730 s.

In `NativeWholeEngine::advance`, this gate executes **after** `advance_owned_joint` returns but **before** `self.capture()` and `validate_bundle`. The error path uses `?` before those operations. Consequently the internal completed tick is not evidence that the returned whole bundle or a newly saved checkpoint passed outer validation. The runner's zero-credit classification is correct.

## What this unchanged gate counts

Sources: [v1_engine.rs](../../crates/metroflow-rust/src/v1_engine.rs), functions `storage_admission`, `capture_validation_real_owner_phase_bytes`, `capture_road_clone_credit`, `advance`, `capture`.

For the post-advance capture branch its requirement is:

```
base_fixed + max(call_binding, whole_validation_scratch)
+ input_road + 2*current_road - unique_current_road_payload_credit
+ input_journey + 2*current_journey
+ input_events + current_events
```

It retains the caller's original input Bundle, the newly committed native owners and the future capture's road/Journey shells. Road immutable payload is credited for the current-to-capture clone; service events share their Arc between committed state and capture, so only original-input/current event payloads are counted. Whole bundle validation still requires the real stage/egress/tag-map scratch.

This is a **full native-budget** gate (6,442,450,944 B), whereas the internal checkpointability gate uses the remaining dynamic pool after fixed reserves. The different denominators do not indicate a cap increase or bypass.

There is source-established conservatism in this expression: `NativeJourneyCore::checkpoint` returns `self.state.clone()`; StageQueue contains `Vec<Arc<Block>>`, and ReceiptHistory is `Option<Arc<Block>>`. Therefore the captured/current Journey share immutable stage/history payloads, while the helper still charges two full retained Journey sizes. It also has no source/current overlap credit analogous to the internal precommit gate. These are identifiable accounting directions, **not quantified relief or permission to remove the full second owner**: outer metadata, pointer registries, dense arrays and independent source allocations must remain charged.

The final normal receipt has `trace_mode=off`, so its exact `fixed_base`, scratch, individual owner sizes and captured-road credit were not recorded. Old-candidate trace terms must not be presented as measurements of this final failure. Peak RSS below the cap does not prove the structural gate is unnecessary: normal whole-bundle validation did not run, the exception path may create a recovery snapshot after the normal gate, and RSS is not the retained-capacity accounting metric.

## Hourly cadence: what it can and cannot change

The outer capture gate runs once per successful native call, not once per internal dt=10 s tick. A full original hourly call from 25200 to 28800 s would **not** return or invoke this outer gate at 25740 s; it still executes every internal per-tick guard. It must invoke outer capture at 28800 s, with the 25200 s input Bundle still live.

If a bounded time-zero hourly comparison deliberately ends at **25740 s**, its shortened final call from 25200 to 25740 s **still invokes this gate at 25740**. That comparison changes the retained input owner from 25730 to 25200; it does not bypass the final gate. Whether the smaller/older input offsets growth of current owners is unresolved until measured.

Thus the tick-return failure does not prove that the original hourly trajectory fails at the same physical time, nor does hourly cadence guarantee eventual success. Every original hour/final endpoint, plus the separate 43200 s same-engine save/load acceptance, remains subject to its actual unchanged guards.

## Minimal next measurement — not performed here

First use the already-planned original-cadence normal run and its exact final call endpoint to determine whether a whole returned/validated prefix exists. If the same outer gate remains, the smallest diagnostic is **one bounded record-only run of the same final source/native and chosen cadence**, preserving all caps, to collect existing `engine_admission:capture/validation` terms together with the preceding checkpointability terms. That would distinguish actual source/current ownership, clone credit and validation scratch before selecting any later surgical change. No such diagnostic or new repair is authorized/performed by this note.

Classification: the previously observed internal checkpointability obstruction is **implementation-verified as traversed in a normal 100k tick**; the current obstruction is an **unresolved outer execution-admission blocker**. It is not a physical/mathematical no-go or a V03 completion result. Drift verdict: **ALIGNED_WITH_OPEN_OBLIGATION**; scientific dynamics and all caps remain unchanged.

## Exact exception checkpoint semantics

The original call is not atomic across all of its internal ticks. For this specific outer capture-budget error, Rust `advance` returns through the admission `?` without restoring its original input. Its current native owners retain the last completed internal tick. The separate post-capture `validate_bundle` error branch attempts `restore(original_input)`; that branch was not reached by this failure.

[NativeWholeRuntime.advance](../../src/metroflow/v1/native_engine.py) catches the native error and sets `exc.checkpoint = self.native.snapshot()`. Rust `snapshot()` directly calls `capture()`, without the normal storage-admission/full-bundle validation sequence. [NativeReleaseDriver.advance](../../src/metroflow/v1/native_release_driver.py) then wraps that checkpoint as DriverState. Thus an exception can expose the latest internally committed clock rather than falling back to the original call-input clock; the exposed clock alone is not proof of a fully validated normal return.

The original [acceptance worker](../../tools/run_v1_local_acceptance.py) retrieves that exception checkpoint, obtains diagnostics, calls `driver.save(path, checkpoint)`, and only after successful saving assigns `simulated_s = checkpoint.time_s` and obtains `last_valid_report`. Native `save` first invokes `restore(state)`, which enforces its own resource admission; this can fail independently. The failure handler does not itself fresh-load the resulting file. A recovery snapshot, a saved/reported last-valid receipt and a separately validated fresh replay therefore have distinct evidence status. The actual original worker receipt must determine which clock is credited.

Source confirmation of cadence: `advance_measured` chooses `target=min(end,(floor(state.time_s/3600)+1)*3600)`. For the parent's actual 86400 s request, the relevant successful hourly boundary is 28800 s, not a shortened 25740 s return. No source patch or recovery action was attempted by this diagnostic lane.
