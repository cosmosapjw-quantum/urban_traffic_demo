# C2–C6: streaming validation of the original finite-response FIFO state

Base: `78d5e7e7e52e4db618a32ce3eca2e71f01b2433c`.
Changed production file: `crates/metroflow-rust/src/v1_road.rs`.
Frozen file SHA-256: `b7a3fad3943da61c5ff72fba08d10ea9832d722f1442c161dfc8c244493361dc`.
Author lane: `/root/validation_revision`; no commits/pushes or full-scale horizon runs performed by this lane. Parent owns publication and physical-run admission.

## Observed defect and constructive correction

The preceding real Valley 100k continuation failed at attempted t=25740 s, after112.460139715 s of road work, at `phase=state validation workspace`, required5435700144 B versus5297903399 B. Its last valid t=25730 s checkpoint and failed-run receipt remain unchanged in `artifacts/v03_event_store_envelope_20261123/R8e_original_100k_25730_requested_20s.json`.

`step_state` invokes `check_state(&out)` after the road proposal is constructed. The validator previously retained every part mass in a per-class `Vec<f64>`, every cell occupancy/pending packet mass in another Vec, and every cell residence in a third Vec, solely to feed the existing expansion sum afterward. The guard reserved `3*max(state_retained,input_retained) +16*parts +32*(packets+cells)`. The old source also performs a subsequent3*max candidate guard. This is an implementation scratch bottleneck; it is not an actual allocator OOM or a mathematical obstruction to the traffic model.

The revised validator feeds the same values, in the same order for each reduction, directly to `ValidationSum`. Its insertion and final round-to-even operations are copied from the unchanged original `sum` helper. Class, network, residence, nested packet/cell occupancy, footprint and class/global sums use this mechanism. No physical evolution or predicate/tolerance changes were made. The change removes actual O(part-count) materialized mass vectors instead of merely reducing their accounting.

`ValidationScratch` retains the original3*max owner fallback for bounded and standalone paths. It charges the class-accumulator vector and conservative shell allowance, plus all simultaneously live expansion-buffer capacities. Before any expansion buffer grows, it admits the existing live allocations plus the entire prospective new allocation and32 B; afterward it accounts the observed capacity. No fixed mathematical bound on the number of expansion components, false pointer alias or arbitrary byte credit is assumed. Opaque allocator metadata remains outside structural accounting and inside the unchanged process cap. The measured allocator-provided Vec capacity is checked before the new owner is retained.

## Behavioral RED and identical GREEN

Command (both runs):

```sh
CARGO_TARGET_DIR=/home/cosmosapjw/worktrees/urban-traffic-v03-unique-accounting-20261120/target RUSTFLAGS='-C link-arg=-lpython3.12' cargo test --offline -p metroflow-rust --lib validator_streams_rows_at_unchanged_retained_owner_allowance -- --nocapture
```

The fixture contains10,000 valid original homogeneous Part rows. The allowed bytes are exactly `3*retained+8192=731048`; owner accounting is unchanged. The existing validator's required882920 B exceeds that cap; the test fails with its real MemoryError. `C3_validation_red.log`: process exit101,0passed1failed. No import/build failure is called behavioral RED.

After the implementation, the identical command passes. The test also serializes the full road wire before/after validation and asserts exact equality. `C5_validation_green.log`: process exit0,1passed. This GREEN was rerun after all source changes.

## Numerical, malformed-state and budget checks

```sh
CARGO_TARGET_DIR=/home/cosmosapjw/worktrees/urban-traffic-v03-unique-accounting-20261120/target RUSTFLAGS='-C link-arg=-lpython3.12' cargo test --offline -p metroflow-rust --lib v03_validation_stream_20261123_tests -- --nocapture
```

`C6_validation_targeted.log`: exit0,6passed. The checks cover:

-130 supplied/generated sequences against the unchanged materialized `sum`, comparing exact f64 bits, including cancellation, ties, signed zeros, subnormals, broad exponent ranges and nonfinite values.
-Actual old/new growth: a4-double old buffer plus8-double new buffer plus32 B requires128 B;96 B rejects before allocation,128 B admits, and dropping a sum releases its charged capacity.
-Two simultaneous class buffers cannot independently spend the same remaining allowance.
-The original3*max input-owner fallback still rejects a cap below3,000,000 B when retained input is1,000,000 B (actual required3000320 B includes fixed scratch).
-Cell, network, class ledger defects; nonfinite packet target; original record-budget violation; invalid homogeneous birth moment remain rejected.

Workspace library verification:

```sh
CARGO_TARGET_DIR=/home/cosmosapjw/worktrees/urban-traffic-v03-unique-accounting-20261120/target RUSTFLAGS='-C link-arg=-lpython3.12' cargo test --offline --workspace --lib
```

`C6_validation_rust_library.log`: exit0,267passed0failed2ignored. This is scoped library verification, not the user-deferred complete repository CI. `git diff --check -- crates/metroflow-rust/src/v1_road.rs` exited0.

## Call cadence and original-intent watchdog

The original acceptance CLI at `tools/run_v1_local_acceptance.py` advances to hourly boundaries, while the research continuation runner calls one10 s tick at a time. In `v1_journey.rs::advance_joint`, the supplied input Road/Journey/event snapshot remains live across the complete native call. Its input/current shared-road witness is tied to the restore-time physical clock and expires after the first tick. Therefore a failed one-tick checkpoint continuation does not establish that the original hourly campaign fails at the same point, and a one-tick success does not establish full-hour admission. The physical dt remains10 s in both. Parent experiments must bind cadence explicitly.

Original-intent contribution: validation continues checking the same mass, residence, route suffix, birth/entry interval, storage and finite-response FIFO state while eliminating an auxiliary row list. The traffic population, source calendar, model, event observations, checkpoint format, f64 kernel and acceptance thresholds are preserved. This lane contributes implementation progress toward the original mesoscopic feasibility objective; it is not the required new background-theory result.

## Remaining exact obligation

No full-scale25740 s execution result is claimed here. Parent must commit the native source, build the release extension from that source, admit the exact25730 checkpoint under a narrow cross-native contract, verify full wire/ledger restoration and execute the next original-demand interval under6 GiB native/8 GiB process limits. If another phase blocks, preserve its precise failure and last valid prefix; do not infer a global no-go or relax caps.

A source-aware owner rewrite was investigated but not added: `paired_shared_payload_lower_bound` currently constructs a HashMap census despite an older allocation-free comment. Introducing that helper into the validation phase without admitting its actual scratch would not be justified. The present patch needs no new alias accounting.
