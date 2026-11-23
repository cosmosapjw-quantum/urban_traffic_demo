# C8: original-cadence source owners and prediction lifetime

## Observed physical baseline and diagnosis

Parent's original-hourly-cadence run started from time zero with the original100k Valley matrix, dt10 s, candidate source7e8b92020076e01283d532cf0e5825cb30167a533949e6bc6fd071f7b7d8cfe2 and nativebaa3e4ce4f775df5cf3973e749357cc2d5a29cefbf1683355638a0de5b6a5606. It committed t=25730 s, then stopped at the next tick's preflight: required6682798752 B, allowance5320948967 B. This differs from the old one-tick continuation's final validation failure because the owner lifetimes and optional interning are different. Parent independently verified exact whole wire bytes/SHA and physical ledger equality at25730 with the historical checkpoint; see R6_original_cadence_baseline_summary.json. The representation diagnosis does not posit a different traffic trajectory.

The actual baseline state reports56524868 parts,1003578 packets,1170142816 B of vector capacities and1085 latent entries. With the same1586 cells, the production retained-storage formula yields1203042688 B. The old work base charges three times that largest owner,3609128064 B, plus1808795776 B for32 B per input row,224628960 B for two future maximum-cell Part buffers, and offer/group allowances. The original call-input snapshot is an earlier, smaller source, not a third full copy of the largest current state. Its pointer-sharing witness expires after the first tick, correctly; no expired witness may be revived to obtain savings.

A restored checkpoint also interns exact keysets before use; continuous candidate interning can be deferred by its peak requirement. The baseline reports750710 Uniform packet owners and192393840 B of potential repeated-key payload. This latter number is a counterfactual diagnostic, not a claimed measured saving. Equal wire therefore does not imply equal live allocation identities or capacities.

## Implemented correction and lifetime argument

The source-aware path is limited to whole calls with an explicit original-snapshot capacity witness. NativeWholeEngine::advance now passes `state.value.road.retained_storage_bytes()` into advance_owned_joint; the road is bound through `bind_original_input_road_storage`. This uses the actual caller snapshot, including its Vec capacity slack, instead of inferring original capacity from the restored clone. The Journey local input-road charge also uses that measured value. The general standalone path remains available and keeps its original fallback.

Write R0 for the actual original caller owner, R for the current road owner and M=max(R0,R). The source-aware work base reserves R0+R+M for original/current/future-candidate owners. This keeps the full previous maximum-sized candidate allowance and all per-row, offer, incremental event/incoming/interval reservations. It only stops substituting M for the two already measured original/current owners. Pointer alias deductions remain the old separately established, clock-qualified deductions; source capacity measurement alone proves no alias. The fallback remains3M when the explicit whole-source capacity witness or current-owner identity is absent.

The two maximum-cell incoming-combine buffers do not exist during source preparation and motion prediction. `source_prediction_phase` excludes that future term only until all prediction outputs have been consumed. The pre-existing per-offer reserve still covers original offer Vec, grouping, combine and packed new source overlap. Existing per-row scan and group reserves cover prediction work. `retire_completed_motion_scan` ends the source-prediction phase and restores the complete future combine term before service/incoming processing. Later narrow transfer/no-combine phases retain their previous rules. This is a source/lifetime correction, not a changed cap or numerical operation.

## Actual RED/GREEN and regression evidence

Before changing the work-budget formula or phase selection, the new source-capacity measurement API and two real-owner tests were installed. The guard under test still used the original formula. Command:

```sh
CARGO_TARGET_DIR=/home/cosmosapjw/worktrees/urban-traffic-v03-unique-accounting-20261120/target RUSTFLAGS='-C link-arg=-lpython3.12' cargo test --offline -p metroflow-rust --lib v03_prediction_owner_20261123_tests -- --nocapture
```

C8_validation_preflight_red.log: two behavioral failures, exit101. A real10,000-row current RoadState with a separately held smaller original state failed the production proposal at tick preflight, required2005536 B versus1800000 B. A separately held original snapshot with a large actual packet-Vec capacity and a smaller current owner also failed its production preflight. These are allocated-owner fixtures, not arithmetic-only comparisons or compile failures.

After the work-budget correction, the same command and two test bodies passed: C8_validation_preflight_green.log, exit0,2passed. Additional targeted tests are in C8_validation_preflight_targeted.log: exit0,6passed. They establish:

- The smaller original/larger current scenario completes a full production road proposal and retains exact wire equality with the uncapped oracle.
- The larger original capacity is actually charged rather than reconstructed from the smaller restored/current owner.
- Without the explicit original capacity witness, the old standalone preflight still rejects the same2005536 B demand.
- A real shared payload with an expired source clock receives no source-sharing credit.
- The future combine reserve resumes at the prediction boundary, including checks of the actual production guard difference.
-64 actual source offers traverse preparation, combine, proposal and final validation with exact event f64 bits and checkpoint wire matching the uncapped oracle.

`git diff --check` passed. Before handing the decoder-helper regions to the checkpoint lane, v1_road.rs SHA was754774be124584c0883aa5024bbe88cd02c801d164e8403d5c8adf5413e92356; the engine-only input binding change SHA was7eb50137e058288cf5561551b2161187cdf866885368b9428b1eb7d089e1b794. These are intermediate source identities; final combined native identity must be recomputed after the decoder repair.

## Original-intent watchdog and boundary

This correction addresses the originally specified hourly call cadence rather than treating the research runner's one-tick lifetime as the acceptance campaign. The physical dt, resident stock, complete calendar, finite-response/FIFO dynamics, f64 operation sequence, event/wire data and resource limits are unchanged. The separate streaming-validator candidate already passed actual road/service/journey calculation at25740 but was rolled back at future checkpointability; that result is a preserved enabling result, not committed horizon credit. The full original-cadence and checkpointability effects of the combined source require the parent's subsequent bounded physical experiments.
