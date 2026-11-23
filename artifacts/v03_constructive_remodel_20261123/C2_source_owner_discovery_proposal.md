# C2–C3 proposal: prove allocation-free source sharing before discovery

## Authority, baseline and stage boundary

New user-authorized ten-stage constructive-remodel loop. Worktree `/home/cosmosapjw/worktrees/urban-traffic-v03-constructive-remodel-20261123`, branch `research/v03-constructive-remodel-20261123`; initial base `90bfca2c2ddf081cbdf40d11b95ff820837d03b5`, R1 checkpoint `b5f61d61a0038dd4fbfcf75d859d2965a8064b33`. Protected runtime baseline source `e6a49b7c0cd598ff480a1d3a421fa9e8ae57f227c311d514556a394f137b29db`, native `6a6d48c8986ce1ffe1108afa145707b556345f0e7572c7c4f34e7e64b19da808`.

Skill context actually read: PhysMath Research Loop 1.3.0 SKILL.md, CODING_LOOP.md C2–C5 contracts, POLICY_INTEGRATION.md and SUBAGENT_MODE.md; superpowers systematic-debugging. This lane is C2 source mapping/C3 constructive resource design, then focused behavioral RED on unchanged production. No production mutation, release build or full physical run is authorized by this note. Parent owns production approval, runner, commits and the one later independent review.

Origin watchdog: preserve the explanatory mesoscopic city, causal routing and day/recovery goal. This resource repair does not establish a new physical theory or full-day acceptance. It preserves current 100k demand, dt, FIFO/f64/wire and 6 GiB native/8 GiB process limits. Newly authorized model exploration remains a separately identified research construction.

## Established observations and exact source anchors

1. `R8c_frontier_25730_10s.json` records a returned, ledger-validated 25740 state, followed by SAVE_VALID_PREFIX failure: snapshot census 6,807,602,661 > 6,442,450,944 B. No durable 25740 file exists.
2. Final original 86400-request hourly attempt first failed with `native journey stored/working byte budget`; exception-save then failed census 7,221,056,145 > 6,442,450,944 B. Durable progress remained 25200. The exact failed internal clock and Journey subsite/terms were not persisted and remain UNKNOWN.
3. Current `v1_engine.rs:1251–1312` computes input/current retained owners and preflights their uncredited sum plus the census. It only checks `service.shares_event_arc(&input.service.1)` at line 1298, after the census has already been admitted and run. This identity test itself is allocation-free.
4. `v1_engine.rs:1508–1534` shows restore clones exactly the supplied source after admission; capture clones current road/service/journey. `advance` at 1650–1719 returns that capture. `save` at 2070 restores its supplied state. Both observed failing saves therefore receive a just-captured current snapshot. Actual event Arc identity can be tested immediately, without inferring it from clock or value equality.
5. `v1_journey.rs:1899–1910` reserves `2*max(R_input,R_current)+2*max(E_input,E_current)` before Journey prepare. Only input/current road and event owners exist there. The candidate road has not been proposed; the Journey candidate is covered by the separate local guard.
6. `v1_journey.rs:482–513` defines that unchanged local guard as `3*max(J_retained,J_projected)+scratch+65536`. Prepare calls it before cloning/proposals (2406), before offers (2459), and before projected stage growth (2477); finish has further projected stage/history checks. A shared error string does not establish which call failed in the original run.
7. Road/stage discovery already operates on immutable Arc pointer identities. `v1_road.rs:1900–1943` sizes one road HashMap by backing occurrences; `v1_journey.rs:275–371` bounds the stage HashMap and target-clone sharing. Their previous C8c review is reused.

## Chosen coherent production change, pending RED/parent approval

Use a two-step ownership proof: (A) establish all already available allocation-free identity facts, then (B) admit and execute variable-size discovery using the resulting actual-source upper bound. No prospective clone/decoder saving may finance step B.

Let F be the unchanged fixed base plus call-binding reserve; R, J, E denote actual source capacities for input I and current C; W is the existing conservative sequential census workspace upper. Define

`delta_E = E_I if Arc::ptr_eq(events_I,events_C) and E_I == E_C, else 0`.

The current discovery preflight is

`U_old = F + R_I + R_C + J_I + J_C + E_I + E_C + W`.

The proposed discovery preflight is

`U_discovery = U_old - delta_E`.

Proof: equal live Arc allocation identity means the two event handles own one immutable allocation; their equal measured storage is charged once. This proof uses no HashMap, clone, future decode, equality of contents or cached clock witness. All road/Journey owners remain fully charged while the census is built. All table capacities, control/allocator padding and actual-capacity checks stay present. The event pair credit then enters the existing final snapshot-owner equation exactly once, as it already does today; it is not subtracted a second time from that equation. Final admission remains max(discovery phase, snapshot/validation phase), with the same total cap.

The same source-owner principle corrects Journey's parent reservation before prepare:

`P_old = 2 max(R_I,R_C) + 2 max(E_I,E_C)`

`P_new = R_I + R_C - delta_R + E_I + E_C - delta_E`.

Here delta_R is only the existing source-clock-qualified road witness from `preproposal_road_source_owner_bytes`; on a changed clock it is zero. delta_E is a fresh live Arc comparison against `call_input_events`. These existing helpers already implement the needed source proof at the immediately following road phase. Reuse them at the earlier Journey prepare phase. With zero credits, the removed excess is exactly `abs(R_I-R_C)+abs(E_I-E_C)`: two actual owners are no longer both replaced by the larger owner. This changes the parent reservation, not the local WORKING_COPIES=3 rule. Every local Journey projected-capacity, scratch, validation and standalone decoder guard remains unchanged.

The concrete original-hourly risk is a small original 25200 snapshot coexisting with a populated current owner; the max substitution can substantially overreserve that phase. This is a derived source mismatch and a testable mechanism, not a claim that the unavailable original failure subsite or byte split has been measured. Check local retained-input binding against the already supplied actual original Journey capacity; never introduce a clone-capacity underestimate while adopting concrete parent owners.

## Bounded-census alternative and stop condition

The observed defect does not require a new allocator or global ownership registry. The first implementation should retain the existing preadmitted road/stage tables, with the event identity established before allocation. A workspace redesign is justified only if a focused fixture or the newly admitted phase demonstrates actual census workspace, rather than a known duplicate event owner, as the remaining blocker.

If needed within this same discovery objective, the conservative alternative is one fixed-capacity table bounded by remaining admitted scratch, processing deterministic disjoint `(layout kind, Arc pointer)` prefix partitions. A leaf inserts unique target identities without growth, scans the other owner and consumes each match once; oversized leaves split by actual key bits. A fixed depth-bounded task stack and one table bound peak memory; partitions are disjoint, so SharedKeys are credited once per pair. Hash/value equality never proves alias. This trades repeated scans for bounded memory, and needs a real timing/space fixture before selection. It is not authorization for another resource-guard chase. If the known live-owner upper still exceeds the cap, preserve the explicit unresolved conservative rejection; do not call it physical impossibility.

The existing retained-size accessor's internal SharedKeys diagnostic HashSet is a known C8c limitation. This proposal does not quietly claim to make all historic size queries allocation-free or launch an unrelated cache redesign.

## C3 smallest behavioral RED/verification plan

All initial RED tests execute unchanged production guards. No full-size input or .so rebuild is needed.

- Actual capture/zero-step advance and actual save: a real road-generated event batch, nonempty delayed egress/internal StageQueues and ReceiptHistory. Choose one fixed cap above the unchanged 3J validator and final shared-owner phase, but below the old uncredited census. The old code must fail specifically at snapshot census; later GREEN uses identical fixture/cap and compares full checkpoint bytes.
- Distinct-but-equal events: independently allocated valid owners under that cap still reject. The same actual Arc may remain shared across clock changes; no clock/value-based credit is admitted.
- Meaningful lower cap: one byte below the corrected source/census requirement still rejects before the table allocation.
- Journey prepare: a valid populated coupled fixture with a call-input event Arc retained across a subsequent tick. Its unmodified local 3J+proposal/offer scratch fits after actual parent source charging. The unchanged full `advance_owned_joint` path must fail the old parent allocation and later pass the same cap, with a high-cap full-wire oracle. Include the next tick after events become distinct/empty so the original retained source is still charged.
- Fresh restore: fresh constructor owners plus independently decoded events receive no prospective alias credit; existing load/validate/restore and full wire remain required. Reuse prior malformed-wire/ledger tests in the bounded gate.

First RED command after writing the test-only module:

```sh
CARGO_TARGET_DIR=/home/cosmosapjw/worktrees/urban-traffic-v03-unique-accounting-20261120/target RUSTFLAGS='-C link-arg=-lpython3.12' cargo test --offline -p metroflow-rust --lib v03_source_discovery_c3_20261123 -- --nocapture
```

At this proposal checkpoint the new tests are NOT_RUN. Fixture setup/import/compile failures will not be labeled behavioral RED. Production remains unchanged until the parent reads the proposal and genuine RED results. Stop after one coherent change, targeted GREEN, bounded library gate and one independent changed-surface review; actual release-scale effects require later root-owned experiments.
