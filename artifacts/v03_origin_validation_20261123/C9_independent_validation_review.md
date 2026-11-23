# C9 independent review — streaming state validation

Reviewer: `/root/validation_review` (distinct from implementation author). Scope: one read-only source/evidence pass; no production edits, Cargo reruns, or full-scale simulations. Review base `78d5e7e7e52e4db618a32ce3eca2e71f01b2433c`.

Reviewed current `crates/metroflow-rust/src/v1_road.rs` SHA-256, checked twice during review:
`b7a3fad3943da61c5ff72fba08d10ea9832d722f1442c161dfc8c244493361dc`.

## Findings

No current-task blocking defect was found in the reviewed diff. This is a source/evidence review of the validator revision; it is not a full-scale25740 s success claim.

1. **Numerical identity of each reduction.** `ValidationSum::push` preserves the original `sum` insertion operations, component ordering, magnitude swap, error-free-transform arithmetic, truncation, and nonzero append. `finish` preserves the same reverse reduction and round-to-even correction. Interleaving different independent accumulators changes their wall order, not the input order or operations of any accumulator. The original `sum` helper is unchanged.
2. **Original nested reductions are retained.** Cell occupancy remains `sum(packet -> sum(part mass))`; footprint occupancy remains the flattened ordered sum of mass times footprint; network mass retains cell occupancies and then that cell's pending-packet masses; residence retains cell order; class mass retains the original cell/pending/packet/part filtered order. The later class/global reductions retain ledger order. No `sum(m_i)*f` substitution or flattening of nested reductions was introduced.
3. **Physical predicates and tolerances are retained.** The same schema, finite/nonnegative values, packet order, storage, part/tag/suffix, birth/entry interval, record count, network/class/global mass and residence conditions remain. The `zip` over class sums has the same length because schema validation requires the ledger length to equal classes length and one sum is constructed per class. Resource rejection can occur at a different allocation point by design; this is not an assertion that every resource-failure message remains byte identical.
4. **Scratch accounting follows live capacity.** All class accumulators share one `ValidationScratch`. `live_bytes` includes their simultaneous partial capacities. A growth first checks current live bytes plus the full new requested capacity and32 B while the old allocation is still live. The new allocation's reported capacity is checked; replacing/dropping buffers removes the old charged capacity. The class-container capacity is also measured and charged. The implementation does not assume a universal constant number of expansion components. `checkpoint_vec` uses fallible `try_reserve_exact`.
5. **Owner fallback and scope are unchanged.** The bounded path still uses `3*max(state_retained,input_retained)`; the patch removes the actual row lists that previously required the row-count scratch allowance. The uncapped path still validates state and performs the same arithmetic, with fallible allocations. No new alias credit, demand reduction,6GiB/8GiB cap change, wire edit, or physical-kernel change appears in the diff. `v1_journey.rs` has no diff against the review base.

## Evidence inspected

The reviewer inspected the full production diff, original `sum`, `occupancy`, `occupied`, `checkpoint_vec`, `check_storage_limit`, all six added tests, trace-counter semantics, and these stored outputs:

- `C3_validation_red.log`: the unchanged-cap10000-row test fails with an actual `MemoryError`, required882920 B versus731048 B;0passed1failed.
- `C5_validation_green.log`: the same named test passes after the revision;1passed0failed. The test compares the full road wire before/after validation.
- `C6_validation_targeted.log`:6passed0failed. The arithmetic test compares130 deterministic supplied/generated input sequences to the original helper by exact f64 bits, including subnormals, ties, cancellation, signed zeros and nonfinite inputs. Other tests exercise growth overlap, simultaneous buffers, retained-input fallback, and malformed/over-budget states.
- `C6_validation_rust_library.log`:267passed0failed2ignored. The author receipt `C6_validation_revision.md` records actual commands and process exits101/0/0/0 for RED/GREEN/targeted/workspace runs. The reviewer read these records and did not present them as independently rerun experiments.

No additional full workspace rerun was warranted by the inspected diff. The parent owns full-scale checkpoint restoration and the next physical interval, where the broader coupled owner budget remains an empirical obligation.

## Telemetry interpretation

`validation.actual_peak_scratch_bytes` is a structural scratch-admission high-water value, including conservative shell/growth allowance. It is not a process RSS or allocator-instrumented heap measurement. `v1_trace::add` stores `(calls,sum,max)`; use its max component for the maximum observed validator high-water value, and do not report the sum component as simultaneous memory. No code change is required for the present validator decision; reports should preserve this meaning.

## Original-intent watchdog

`ALIGNED_WITH_OPEN_OBLIGATION`: removing a redundant materialized mass list advances mesoscopic feasibility while preserving the chosen finite-response FIFO state and its observational checks. This is implementation progress, not new background theory or V03 acceptance. Fullscale advancement and original hourly-call cadence must be measured separately from this scoped validator review.

`skill_context_used`: PhysMath Research Loop1.3.0 `SKILL.md` directly read; parent-supplied C6/C9 bounded independent-review contract, original-intent preservation, exact evidence/source identity and one-pass/no-recursion policies applied.
