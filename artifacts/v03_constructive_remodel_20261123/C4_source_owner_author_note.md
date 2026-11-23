# C4: actual source-owner discovery and Journey parent reservation

Status: implementation verified by focused behavioral tests and one bounded Rust library gate. Production source frozen after this gate. No release build, native replacement, full-size physical run, commit, or push was performed by this lane.

## Scope and origin

Worktree: /home/cosmosapjw/worktrees/urban-traffic-v03-constructive-remodel-20261123
C3 test-only parent commit: 9ccdf5b97009aee2276a1e1355588ac542029289.
Authoritative proposal: C2_source_owner_discovery_proposal.md.
The original purpose remains a 100k-agent mesoscopic city with causal routing, physically valid mass/FIFO/delays, and a complete-day acceptance target. This change adjusts owner accounting only; it does not alter the physical model, demand, f64 order, checkpoint wire, caps, or release acceptance. Full-day progress credited here: 0.

The preceding full-size 25740 save and original-hourly recovery census failures are observed evidence from the prior loop. The original-hourly primary Journey subsite and internal failure clock remain unknown; the small fixture below identifies its own journey_prepare subsite and is not evidence that the large run failed there.

## Production change and memory argument

In v1_engine::snapshot_source_owners, the exact current/input event Arc identity is now inspected before admitting the road/stage pointer census. This is a constant-space Arc::ptr_eq plus a byte-size equality check. It is not a prediction that a future allocation will share storage.

Let F be unchanged fixed base plus call binding, W the unchanged maximum of sequential road/stage census upper bounds, and Ri,Rc,Ji,Jc,Ei,Ec the actual retained input/current owners. The discovery admission is now:

    F + Ri + Rc + Ji + Jc + Ei + Ec - delta_E + W

where delta_E = Ei only for the same live event Arc with equal measured bytes, otherwise zero. Both source handles exist at admission; no future clone has yet been constructed. Road and stage pair intersections remain uncredited until their fully admitted tables have run. Every registry capacity and the entire census scratch upper remain charged. The previously existing final snapshot owner formula still subtracts that same event pair only once, and final admission remains max(census phase, snapshot/validation phase). Independent equal-valued events receive no credit. Trace fields record the before/after owner sum and exact event credit.

In v1_journey::advance_owned_joint, prepare reserves the two actual road/event source owners using the already existing helpers from the following road phase:

    road_parent = Ri + Rc - verified_same_input_clock_road_payload
    event_parent = Ei + Ec - actual_current_input_Arc_overlap
    prepare_allowance = dynamic_pool - road_parent - event_parent

The source road witness expires at a changed road clock. Event identity is checked again against the currently committed backing each tick. No candidate/future decoder credit is taken. Without alias credits, replacing 2*max(Ri,Rc)+2*max(Ei,Ec) removes only the phantom-owner excess |Ri-Rc|+|Ei-Ec|. The candidate does not yet exist at this phase.

The local Journey policy remains exactly 3*max(retained_input, projected_dynamic)+scratch+65536. The original supplied Journey can retain a wider StageQueue registry Vec than its restored clone. The already measured original footprint is now bound via max(original,restored) to the retained_input field. This is a monotone tightening of every unchanged local 3J guard, with the standalone/no-source fallback preserved.

Only engine and Journey production changed; road source and all decoder/validator implementations are unchanged. These changes do not claim arbitrary unrelated snapshots are within the engine-owned budget.

## RED/GREEN evidence

Command for the six primary controls and, after the retained-capacity fixture was added, all seven:

    CARGO_TARGET_DIR=/home/cosmosapjw/worktrees/urban-traffic-v03-unique-accounting-20261120/target RUSTFLAGS='-C link-arg=-lpython3.12' cargo test --offline -p metroflow-rust --lib v03_source_discovery_c3_20261123 -- --nocapture

- C3_source_discovery_valid_RED.log / .exit: unchanged production, exit 101, 3 genuine behavioral failures and 3 passing controls. Actual capture and save reject census 77,123,790 B at the fixed 76,959,514 B cap. The actual event backing is 328,552 B. Final snapshot/validation is 76,532,446 B and unchanged Journey validator floor is 76,802,142 B, both below that cap. The cap is independently computed from the old uncredited expression and does not depend on the corrected production result.
- The two-tick coupled Journey fixture rejects specifically at journey_prepare: dynamic pool 11,377,428 B, unchanged local 3J+prepare scratch 10,882,840 B, old parent reservation 658,864 B, actual initial event alias 328,552 B. The second tick uses a different event Arc from the input. Its high-cap full-wire oracle is byte-equal to the corrected bounded run.
- Independent equal-valued event Arcs still reject at the same census cap; one byte below the truly witnessed census also still rejects before cloning.
- A separate independently decoded fresh checkpoint passes the original load/restore/whole-bundle validation and yields identical complete wire.
- C3_original_retained_valid_RED.log / .exit: unchanged production, exit 101. A valid real 2304-row, nine-block source has 75,856 B versus the restored clone's 75,800 B. After actual coupled-call binding, prepare incorrectly passes a clone-only unchanged-3J allowance of 293,024 B; the regression expects the original retained floor to reject. This is a real admission-behavior RED.
- C4_source_discovery_GREEN.log / .exit: exit 0, all 7 pass, 0.29 s test execution. The original capture/save cap and coupled Journey pool remain exactly the RED values. Capture/save and two-tick full-wire comparisons pass. The source-capacity negative now rejects at the unchanged local guard before pending allocation.
- C4_source_discovery_LIB.log / .exit: exit 0, 299 passed, 2 existing ignored, 0 failed; 0.41 s test execution. This was the single bounded whole-library gate, not full CI.
- git diff --check: exit 0.

Setup failures are preserved and excluded from behavioral credit:
1. C3_source_discovery_RED.log initially had two genuine behavioral failures plus a capture fixture assertion because its validation scratch exceeded the chosen fixture cap. The fixture's already-reserved call binding was corrected before the valid RED.
2. C3_original_retained_RED.log initially rejected an invalid time-zero released state before the owner test. Its clock/birth moments were corrected before C3_original_retained_valid_RED.log.

## Frozen source identity

- crates/metroflow-rust/src/v1_engine.rs: 6b4b0472bbb4e2d7867e79c8e3f81126f6697246d8d9cb05682688b240ca6e4f
- crates/metroflow-rust/src/v1_journey.rs: 718b11d566b660e7bfddcfa9bb82485635f89bd577f8972345cdbde21e46e76d
- crates/metroflow-rust/src/v1_road.rs (unchanged): e6cc7627cb74497fb5a108897df860e8a3da5567c121ad73a601a3cf2346e617

Cargo is released. Root owns the single independent changed-surface review, commit/push, final release build, .so copy/hash, and actual full-size experiments. A normal-feature release build can be run from this worktree with:

    CARGO_TARGET_DIR=/home/cosmosapjw/worktrees/urban-traffic-v03-unique-accounting-20261120/target RUSTFLAGS='-C link-arg=-lpython3.12' cargo build --offline --release -p metroflow-rust

Expected build artifact: /home/cosmosapjw/worktrees/urban-traffic-v03-unique-accounting-20261120/target/release/lib_metroflow_rust.so. This command was not executed by this lane. No budget_trace feature or observe-mode execution is requested.

## Remaining claim boundary

The implementation proves removal of the identified false owner duplication in actual capture/save and coupled-prepare fixtures while preserving real budget rejection. It does not establish that a 100k-agent 25740 save, later native tick, original-hourly run, or full day now succeeds; those need the root's frozen-final-native experiments. No bounded multi-pass census was implemented, because the demonstrated mechanism was a zero-allocation event identity already available before the census. Genuine future working-set frontiers remain allowed to reject under the same caps.
