# MetroFlow C9 independent review — 2026-11-23

## Verdict

**Caution — no evidence-supported new correctness finding in the bounded changed-code review.** Latest reviewed production commit: `bec506abb5247e76e8f74e2846eedf9e1c5c501a`. The completed main review at `66128cd142f555470c22b27e8843a9d31fd834aa` is preserved below; the final section adds only the concrete source-specific keyset-allocation correction requested after its next resource failure. The retained event representation, timed incoming producer, direct timed consumer, and this allocation-bound correction preserve the inspected row/order/arithmetic contracts. Actual source-bound logs and independently recomputed replay comparisons support scoped implementation verification.

**Original V03 acceptance remains BLOCKED.** This report does not approve a 24-hour run, the nine-run release matrix, or a large continuation of the latest keyset-bound candidate. No new code defect was inferred merely from an earlier guard failure; the resource results and subsequent source changes are recorded separately below.

## Review boundary

This is one bounded, independent, read-only review by `/root/c9_fresh_review`. It covers the native representation changes relative to `cd77044495598f4ddb28412f78241bd1eb98693c` on `research/v03-coding-reconstruction-20261123`, initially at `9c02161cde99c7fce378d805ac179fd1689e01b1`, with only the concrete direct-consumer delta subsequently inspected at final production commit `66128cd142f555470c22b27e8843a9d31fd834aa`. The original event/producer review was not recursively restarted.

The reviewer did not edit repository files, build native code, launch a simulation, touch the running continuation, or spawn another reviewer. The only reviewer-created artifact is this report in local scratch; root owns persistence and any repair/publication. Existing logs were inspected rather than represented as newly run tests. Independent computations consisted of source/binary hash verification, replay-data comparison, ledger comparison, and integer allocation checks.

## Authority and invariant scope

Read `AGENTS.md`, the changed native sources and affected callers/consumers, `docs/research/V03_CODING_RECONSTRUCTION_20261123.md`, the source-map note, and the unchanged release matrix. Historical motivation was checked against `0492364:docs/PRD.md`, `0492364:specs/001-metroflow/spec.md`, and `6524500:memory/constitution.md`. Confirmed PRD blob `f8cc371410ca0e24b0947cda3d6772787efddc7a` and constitution blob `7c78e214c9558bcb1023854e55025f1c554aadee`.

The original target remains 100,000 residents, full calendars, strict FIFO, legal routes, finite response, physical vehicle/person/cargo/residence ledgers, 86,400 physical seconds, three cases × three repeats, peak RSS at most 8,589,934,592 B, and wall time at most 7,200 s. The release matrix SHA-256 is `1eb90b60d260feff915b785ed4d425dde0bcc1601ad3ad8200640c73d765655a`. Nothing inspected authorizes a tolerance, population, demand, or resource-limit relaxation. The original 100k mesoscopic traffic/accessibility/development objective is preserved; exact in-memory storage changes do not introduce a new traffic closure.

## Initial source and executable identity

At the first completed source verification, HEAD was exactly `9c02161cde99c7fce378d805ac179fd1689e01b1`. The worktree had only the ongoing continuation log/restore directory as untracked items. All 21 Rust-file hashes listed in `C8_BINARY_SOURCE_BINDING.json` matched actual files; the active native extension also matched its recorded SHA-256.

| Artifact | SHA-256 at the initial reviewed candidate |
|---|---|
| `v1_road.rs` | `cf2d6df0f71a37c0782d34140aafdada8cccbe4c0c06b9bd865f75a45efccc2b` |
| `v1_journey.rs` | `a3a6065f4f5052c5a97e223d9117d9d5214458b3b0db3a1b0c8ddf51b7f08495` |
| `v1_engine.rs` | `73ffa91524196238ed4a31875f395d479e1ac302a1bf91b2366b700c8fa0443e` |
| `v1_journey_retained_event_tests.rs` | `b6679a090e2f14d5664acd99253255e42877f8076360269d6094ac199029c344` |
| `v1_timed_incoming.rs` | `fdfc781e18841efeab7add15bfa506980e406cc4db83bc1f76d38782c61b09af` |
| `native_binding/_metroflow_rust.so` | `ddc0a92b074422786d906b69b5941cbd6271563d987f8502ea4e1c6b5d21f9a6` |

Line references in the following initial-review sections refer to that commit, not a later edited worktree.

## Retained event history: reviewed behavior

**No new correctness finding in the inspected retained-event path.** This conclusion is bounded to the stated source and evidence, not an original V03 acceptance verdict.

- `v1_road.rs:465–502, 585–641`: tag/source/destination conversions are checked; `u32::MAX` is reserved for destination `None`. Mass and birth are copied, and start/end time-run keys use `to_bits`/`from_bits`, preserving signed zero. Append order is unchanged. The wide carrier remains available, selected when registry/budget eligibility fails (`2993–3004`), and the decoder receives that eligibility rather than truncating wide input.
- `v1_road.rs:548–579`: retained costs include actual descriptor capacities, page payload, per-page allocation allowance, carrier, and Arc allowance. Streaming decoder projection is constant-time per event and includes conservative descriptor growth plus the added retained overhead. This avoids rescanning all previously decoded pages on every append.
- `v1_journey.rs:471–525, 527–625`: snapshots clone the Arc; legacy serialization iterates logical rows without a flat internal event vector. Decode builds a local carrier under the logical count and byte limits, checks finite/nonnegative numeric fields, and returns a candidate. The explicit public `road_events()` publication still constructs its requested Vec.
- `v1_engine.rs:1755–1851`: malformed data, trailing bytes, sequential storage admission, and cross-owner event binding are checked before installation. `validate_bundle` at `1120–1137` still checks event indices, positive mass, ordered clocks, and event end relative to owner time.
- `v1_journey.rs:1455–1462, 1539–1566, 1631–1683, 1764–1783`: call-input history remains alive and only `Arc::ptr_eq` permits shared input/current accounting. Same-tick sink rows keep their original order, mass, and end time and still feed service/journey completion. Active `ReceiptHistory` was not replaced. Road candidate/history installation occurs after successful coupled finish/admission; errors restore service/journey state and leave the road candidate uninstalled.
- `v1_road.rs:3142–3215`: standalone APIs retain explicit flat output and its coexistence guard. Native proposals keep the carrier and pass its actual retained bytes into the same post-road keyset interning path; interning finishes before installing the candidate.

## Timed incoming producer and initial materialized consumer

**No new bit/order or transaction defect identified in the inspected producer.** Its applicability is the bounded interval path with checked tag/offset registries, not every source shape.

`v1_road.rs:4076–4215` fixes `local_mid`, start/end, and the immutable `Motion` within one serve. Speed is `m.sample(local_mid).1`. Latent depends on `k` through class parameters and `m.hazards[&k]`/`m.initial[&k]`, so one cached control per used class is valid for that serve. The cache resets at each serve. The original per-row fraction, mass/birth transform, offset advancement, ledger operations, and endpoint rewriting remain in place. Pending controls at `4344–4397` are similarly class-constant within one pending packet and preserve source append order. Debug assertions are additional checks; the constancy claim follows from the inspected expressions.

The new module stores 32-byte rows and 32-byte controls under compile-time size assertions. Both compact numeric fields use checked conversions. Row append verifies control existence and endpoint bit equality. Its append-only table remains alive across destination cells. `Pages<T>` allocates exact 128-row pages and explicitly replaces descriptor vectors at capacities 4, 8, 16, etc.; old and replacement descriptors are both represented in its projected peak. Fallible allocations occur before committed owner installation.

For a cell with `p` pages, the growing descriptor peak is bounded by `3p + 1` slots: the first allocation needs four slots, and later growth from `q/2` to `q` occurs at `p = q/2 + 1`, giving `3q/2 <= 3p`. Summing over cells gives `3P + cells`. This matches `timed_incoming_page_charge`; an independent integer check over page counts 1 through 1,048,576 found no violation. Actual descriptor capacities are frozen only after all appends and counted until each owning cell is dropped.

At the initial candidate, `v1_road.rs:4420–4480` charges both encoded source and decoded Part/Mark pages before materializing one destination, computes weighted speed and class moments in original source order, calls the unchanged indexed combine, and physically drops all three cell owners before releasing its charged rows/descriptors. The shared control table survives until the last consumer and is dropped before final state validation (`4547–4557`). This lifetime accounting is why the new failure is a genuine resource result rather than permission to subtract the decoded buffer while still retaining it.

## Inspected execution evidence

Evidence paths below are relative to `artifacts/v03_coding_reconstruction_20261123/`.

| Evidence | Independently inspected result | Scope |
|---|---|---|
| `C4_RETAINED_EVENT_RED.log/json` | Actual Rust test failure: 4,194,432 retained B against a 3,145,728 B ceiling; legacy wire test passed | Meaningful representation/resource RED, not environment failure |
| `C5_RETAINED_EVENT_GREEN.log/json` | Same retained-history behavior plus added decode-budget and wide-index tests: 4 passed | Codec/direct legacy decoder |
| `C6_native_tests.log`, build/test/provenance JSON | 180 passed, 2 ignored; release build completed | Retained-event implementation before incoming change |
| `C8_NATIVE_TESTS_FINAL.log`, `C8_BUILD_TESTS.json` | 188 passed, 2 ignored; final initial-candidate release build completed | Includes 6 timed-carrier tests, 2 workspace/lifetime tests, retained append bounds |
| `C8_PYTHON_REGRESSIONS.log/json` | 42 affected Python tests passed | Owner storage, engine, whole driver, journey |
| `C6_old_replay.json` vs `C8_small_replay.json` | Directly compared complete `states` arrays: all 8 sampled states per policy equal, including checkpoint SHA/size and physical report fields | 1, 3, 5, 10, 15, 30, 60, 120 s; both policies |
| Replay script and actual trace | Batched/fresh-engine-restart wire equality asserted, immutable prior snapshots checked; bounded lane trace contains timed incoming controls/rows | Confirms connected path is exercised, not just an isolated storage fixture |

The recorded C8 Rust log SHA-256 is `c24d8e98d446d0e161fe9e3af04bdc4042396910f273b49c9033da9e36ded9b9`; the C8 release log is `529929bce198fef18446b4fe955a0521af14444bba769323693a65a2cefd198b`; the Python regression log is `141870e2758f7df8e0c7dcc6154d77a3af4130330139cac09b268e3c51d6732b`.

These tests do not establish equality over every possible city/calendar or successful full-day execution. The tiny replay has a maximum eight event rows per tick, so page-boundary coverage comes from the explicit codec/carrier tests, not from that replay. The timed representation is workload-dependent: sparse control pages can make payload larger in a tiny fixture; no universal compression factor follows from its field sizes.

## Original continuation results and limits

`C7_original_continuation.json` records one valid original full-demand step from 25700 to 25710 s, original checkpoint full-wire roundtrip equality, and then a transfer-candidates resource failure at 25720 s. The valid checkpoint raw SHA is `64b77baece5ba45fa0928d59b58d9f8f9fc2178bcd93542b05264736978733fe`. This is evidence for the retained-event slice, not for the subsequent timed incoming candidate.

The initial candidate's `C8_timed_incoming_continuation.json` appeared during review and was read without touching the process. It records:

- status `BLOCKED_RESOURCE`, start/completed time 25710 s, zero newly completed horizons;
- failure before cell materialization at 25720 s: required 4,959,061,048 B, allowance 4,952,574,903 B, excess 6,486,145 B;
- unchanged original process cap 8,589,934,592 B, `trace_mode=record`, measured peak RSS 3,882,655,744 B, and elapsed campaign 171.724927542964 s;
- previous checkpoint full-wire roundtrip exact; previous and completed ledger objects independently compare equal after failure;
- 19,989,328 incoming logical rows, 251,957 controls, and 156,814 row pages. Formula and measured payload agree: row payload 642,310,144 B + control payload 8,065,024 B = 650,375,168 B, compared with legacy Part/Mark payload 1,124,042,752 B, saving 473,667,584 B;
- the first decoded-cell allowance is 33,243,808 B, which really coexists with encoded storage at that candidate.

This result does not show a new numerical error, dropped physical mass, incorrect rejection, or new regression relative to the previously blocked 25720 transition. It does show that source compression alone did not complete the next tick. The original V03 release remains blocked, full-day 0/9 and scoped-or-accepted DAG 19/21. Source provenance explicitly reports `current_source_from_time_zero_verified=false`; a resumed checkpoint plus finite matched replay is not a full fresh-source city run from time zero.

## Final direct-consumer delta

At 2026-11-23 13:19:04 UTC the remote checkout was exactly `66128cd142f555470c22b27e8843a9d31fd834aa`, with no tracked source modification. The only untracked files were the active direct-continuation log and its restore directory. The final delta modifies only `v1_road.rs` and `v1_timed_incoming.rs` in native source.

| Final artifact | Independently measured SHA-256 |
|---|---|
| `v1_road.rs` | `fec553a8a166bb37d2653da12faaa95ca4d1c016f56add70b69bf3f9928cf4bd` |
| `v1_timed_incoming.rs` | `9a2c841f77079a79c5e20421b7d7811ddcd4cf02bb88dcd27045b6aebadce328` |
| `native_binding/_metroflow_rust.so` | `f323db6e99a3b8956ad6cc47b6443a2c96c9f04b182ac444e5f219f4557a2de0` |
| `C8_DIRECT_BINARY_SOURCE_BINDING.json` | `cd953a996ad0bc9164759495fb03ae9a9b3ac710ef996a3c78fc4b1d54a6658d` |
| `C8_direct_small_replay.json` | `a29ece28db2ea80b8e6ccfcffc89346bbfa848fd6d3e81a31d1d35a6578fe9be` |

All 21 source entries in the final binding were independently rehashed and matched. The remaining three changed-source file hashes in the initial table stay unchanged. The older blocked materialization receipt is retained with SHA-256 `691ab0d95470cb7c8f0c897dd3d68ed6748d3b86e775d0e9ed0aa88db9639bd5`.

**Direct consumer correctness and ownership, final-source line references:**

- `v1_timed_incoming.rs:294–329` adds O(1) indexed access using the existing page lookup and original shared control table; `iter()` delegates to it. It returns one copied Part/Mark tuple without heap allocation. The combine indices are derived from `0..len`; stored control IDs were checked on append. The added indexed-access assertions cover out-of-order reads, 127/128/129 boundaries, and the partial final page against both the original rows and sequential iteration.
- `v1_road.rs:2358–2398` extracts `combine_indexed_parts(len, get)` and makes the legacy chunked wrapper delegate to it. In an independent textual computation, the complete final function body equals the old function body after only `parts.len()` → `len`, `parts.get(...)` → `get(...)`, and whitespace normalization. Thus the exact grouping key, original-index tie breaker, distinct mass and birth `sum()` barriers, and final canonical sort are unchanged. This is stronger evidence than a renamed helper or a verbal equivalence claim.
- `v1_road.rs:4411–4480` consumes timed rows directly for diagnostic census, weighted speed, and class moments. Survivor rows still precede received rows in each class sequence. All received rows remain in their original append order. Direct combine is preflighted under the full existing base allowance before its index/output allocation. The wide/unbounded/noninterval lane retains the legacy Part/Mark path.
- `v1_road.rs:2334–2354, 4462–4479` keeps compressed source rows alive through every indexed combine read, then drops their owner before decrementing logical-row/page/descriptor accounting. The control table stays charged across all cells and is dropped at the existing final validation boundary. The removed materialization allowance corresponds to removed whole-cell Part/Mark allocations, not to a change in limits or a fictitious early release. The legacy carrier shell arrays remain empty in the timed lane; they do not hold hidden rematerialized payloads.
- The final workspace tests compare direct and materialized-oracle combined Part fields bitwise across pages and require the source charge to remain until all direct combine reads finish. The previous encoded-plus-decoded test is appropriately replaced because the full decoded owner is no longer part of production.

**Final evidence read:** `C8_DIRECT_CHECKS.json` records actual exit code zero for Rust tests, release build, 42 Python regressions, and the finite replay. Actual logs show 188 Rust tests passed with the same two ignored tests, and 42 Python tests passed. SHA-256: Rust log `a4fc11438044a88795444569c7e45fa83acf72f60c694c600bab8290abd999ab`; release log `5dcf8c123f85ff2e99922a9af827c72af5e6cc1c39e2a46f5fbfaeb74a5baab9`; Python log `47cfebd8fa238ea21e9e399ee28a38653c4f7c40a5898b3c98c8fccbd52a68f5`.

The reviewer independently compared `C6_old_replay.json` with final `C8_direct_small_replay.json`: all eight complete state records per policy match, including wire size/hash and physical fields. Both lanes retain batch/restart equality and immutable-snapshot assertions; each has ten nonempty-event ticks. The bounded lane's timed-incoming trace is present, so the final direct path is exercised. The final replay names the measured final native binary hash above.

At the evidence cutoff, `C8_direct_continuation.json` did not yet exist. The reviewer did not wait for, interrupt, restart, or make an acceptance claim about that campaign. Root should attach its actual result to the final C8/C10 packet, preserving any last valid checkpoint and the exact failing phase if it blocks. A later campaign outcome does not retroactively turn the older blocked run into a successful tick.

## Findings by severity

- **P0:** None identified in the reviewed delta.
- **P1:** None identified in the reviewed delta.
- **P2:** None identified in the reviewed delta.
- **P3:** None identified in the reviewed delta.
- **Nitpicks:** None reported.

This is an explicit no-finding result with the limits above. The earlier observed materialization failure is a resource/scaling limitation with a concrete subsequent source change, not an established corruption or scientific-model defect. The pre-existing physical packet-row growth and incomplete 24-hour matrix remain unresolved. The review does not establish a general no-go theorem, a global memory bound for every city, or a performance speedup.

## Validation limits and handoff

No additional test is demanded solely to mirror the extracted helper. Existing legacy combine tests, carrier boundary/bit tests, new indexed-access/source-lifetime checks, actual native/Python suites, and the independently compared connected finite replay support the changed-code conclusion. The outstanding actual direct-continuation result and original release matrix are execution obligations, not substitutes for a code repair finding.

Read-only review is complete at the requested boundary. No new corrective source edit is required by this review. The parent owns C8 continuation interpretation and C10 reporting/persistence; it should keep full-day acceptance, fresh-source provenance, and finite representation checks explicitly separate.

### Review gate and checkpoint

- Review source: `/root/c9_fresh_review`, one independent bounded pass plus the concrete final consumer delta.
- Changed-code review gate: **PASS within the inspected scope**, with no unresolved new blocker identified.
- Original V03 release acceptance: **BLOCKED**; nine-run/full-day proof is absent and outside this scoped review.
- Active sequence/current skill: C9 / `change-review`.
- Completed: exact source/diff trace, current source/binary binding checks, actual log inspection, independent finite replay comparison, owner/rollback review, final direct-consumer delta review.
- Next required skill for this reviewer: none; review-only task is complete.
- Action: stop at the parent-requested review boundary.
- Parent handoff: incorporate this report, inspect the actual direct-continuation receipt, and report C8/C10 with unchanged original acceptance and preserved failure evidence.
- Next / upcoming task for this reviewer: none — bounded review complete.

## Narrow addendum: source-specific keyset workspace

### Trigger, scope, and identity

After the main review closed, the concrete `C8_direct_continuation.json` result became available. Root requested a narrow check of the newly reached post-road allocation guard and its correction. This addendum does not reopen the completed event/producer/consumer review or introduce another reviewer.

The direct-consumer candidate completed its road candidate/interval processing but failed at `continuous keyset allocation`: required 5,306,343,016 B versus 4,952,574,903 B available. The retained valid coupled state remained 25710 s, with no newly completed horizon. Receipt SHA-256: `a250e278ad104a71f3765ee28a1640f672dd08a27645656995fba4e52eb6d5ba`. Its guard trace records 47,855,028 aggregate `uniform_parts`, 859,335 packet owners, full road-owner sum 2,503,421,112 B, old event bytes 561,521,000 B, and candidate event bytes 652,900,616 B. Reaching the post-road guard is not a completed coupled physical tick.

At 2026-11-23 13:25:50 UTC, the exact inspected HEAD was `bec506abb5247e76e8f74e2846eedf9e1c5c501a`. The native delta from the prior reviewed commit changes only `v1_road.rs`: a source census, its guard argument/trace fields, and two tests. Road source SHA-256 is `65491f4d182dbc6fd6890db6bb23059531fe7d7aff797418d9e52ee80c9690eb`; active extension SHA-256 is `96e8e20ab30b2345223d326225abfab274997b5269e262bda9be74893fd32b8c`. All 21 entries in `C8_KEYSET_BINARY_SOURCE_BINDING.json` were independently rehashed and matched. That binding's SHA-256 is `9bac2d356414d778a56bb621440b47cf12b61f823e56cd9fdc52c031fe54aa68`.

The research runner's separately mentioned optional comparison-receipt handling is outside this narrowly assigned native delta. No new physical runner outcome or fresh-from-zero result is certified here.

### Source-based bound

The source distinction is supported by `intern_exact_keysets`, not by a compression assumption:

1. The first-pass `Uniform` branch may allocate one canonical key vector, containing two `u32` fields per row: 8 B/row. A previously existing `SharedKeys` representative uses `keys.clone()` and allocates no new key-row payload.
2. The mutation-pass `Uniform` branch may allocate one moment vector containing two `f64` fields per row: 16 B/row. The memo keyed by old backing pointer may share this new vector across aliases. Counting all Uniform packet lengths remains conservative even without taking that sharing credit.
3. The mutation-pass `SharedKeys` branch only reassigns a key Arc when necessary. It leaves the existing moment Arc intact. A replacement canonical key that originated in a Uniform group is already covered by step 1.
4. `Mixed` packets get no new key/moment payload from this operation. All variants still participate in the retained-owner and per-packet metadata terms as before.

For `U = sum(length of each PacketParts::Uniform owner)`, the new row-payload bound is therefore `(8 + 16) U = 24 U` B. The helper `keyset_allocation_row_count` at final `v1_road.rs:1327` uses a saturating sum over both cell and pending packets, counting exactly Uniform and excluding SharedKeys/Mixed. The call at `3173` substitutes only this count for `stats.uniform_parts`, which also counts existing SharedKeys. It preserves the full retained-owner sum, old/current event accounting, candidate event bytes, `512 * ALL packet owners`, and the existing 96 B fixed allowance. The original byte ceiling is unchanged.

The reviewer independently extracted function bodies and confirmed both `intern_exact_keysets` and `postroad_continuous_keyset_peak_event_bytes` are byte-identical to the prior reviewed candidate. There is no new mutation, equality shortcut, changed floating-point operation, skipped interning step, or lower physical acceptance limit. This corrects an existing conservative allocation estimate that became the next empirical blocker; it does not erase any still-live owner from the accounting.

### Actual evidence and verdict

The two new tests at `v1_road.rs:7541` and `7565` cover a 4097-row mixed Uniform/SharedKeys case and an all-SharedKeys case. The former verifies the precise removed payload term, retains the original row bits/order, and checks `Arc::ptr_eq` for the pre-existing moment backing after interning. The latter preserves the packet metadata allowance even when no new row payload is allocated. Existing native tests continue to exercise the unchanged interning implementation.

Actual `C8_KEYSET_NATIVE_TESTS.log/json` shows **190 passed, 0 failed, 2 ignored**. The release build completed with exit code zero. `C8_KEYSET_PYTHON_TESTS.log` shows **42 passed**. The reviewer independently compared `C6_old_replay.json` against `C8_keyset_small_replay.json`: all eight complete state records per policy remain equal, including checkpoint wire hash/size and physical fields; batch, restart, and immutable-snapshot assertions remain true. The final replay records the measured native hash above.

Evidence SHA-256:

- Native test log: `eea4aaedc2e252ffb27d800dafc0a5937b1a519731b0001dfe29fa4fbe451da7`.
- Release build log: `a6977b4af544cace2fd9261b5f31d436c8881f9f6a6805a5f6d67a8372abf9f3`.
- Python test log: `2d9c6d825f5261c6b8d930ecbf71d58fcb98d8fa7bab08cbc00740ddbb5e846e`.
- Final finite replay: `e862bb28d696a934488b8e07049adcb1237945412df6d98d98c5facd955b9bf6`.

**Addendum finding: none.** No new P0–P3 defect is supported by this delta. The source-specific payload bound is justified under the same metadata allowance and retained-owner contract, and the observed bit/ownership behavior remains unchanged. No further code edit or new test gate is required by this addendum.

The upcoming `C8_keyset_continuation.json` and any fresh-from-zero comparison belong to root's C8/C10 execution packet. This review makes no claim that the revised guard passes a full original tick or the release matrix before those results exist. Original V03 remains BLOCKED, 24-hour 0/9, scoped-or-accepted DAG 19/21.

Read-only boundary and checkpoint remain unchanged: no repository/source mutation or native experiment by the reviewer; only this report was updated. Changed-code review gate remains **PASS within the inspected scope**. Next / upcoming task for this reviewer: **none — requested narrow addendum complete**.
