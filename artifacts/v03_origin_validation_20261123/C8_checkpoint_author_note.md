# C8 checkpoint validation bridge — author note and source freeze

Date: 2026-11-23. Scope: the observed `journey_commit:checkpointability` rejection after the new streaming road validator had already completed. This is one bounded C7–C8 constructive repair within the existing loop; it is not a new physics theory result or a V03 acceptance PASS.

## Frozen source and verification

| File | SHA256 |
|---|---|
| `crates/metroflow-rust/src/v1_road.rs` | `01694c9ec17d06b43188a9d8e9d93a4dd099173533642e993631befa5ef3a939` |
| `crates/metroflow-rust/src/v1_journey.rs` | `30b2ed00af97eb97d3c40f91f627ccfdb08e3d1db2225f59bce1b344ed2be256` |
| `crates/metroflow-rust/src/v1_engine.rs` | `bf078c2d45fda2805531812b3f74a2955a0b4137098c2cc6fc959bf8743f4e93` |

The final source, including the engine constructor-owner argument and all three lifetime branches, passed:

```sh
CARGO_TARGET_DIR=/home/cosmosapjw/worktrees/urban-traffic-v03-unique-accounting-20261120/target \
RUSTFLAGS='-C link-arg=-lpython3.12' \
cargo test --offline -p metroflow-rust --lib -- --nocapture
```

Final evidence: [C8_checkpoint_final_lib.log](C8_checkpoint_final_lib.log), [exit](C8_checkpoint_final_lib.exit): **283 passed, 0 failed, 2 ignored; exit 0**. Test execution 0.23 s; the enclosing compile/test process reported 3.06 s. `git diff --check` completed successfully. Cargo is released and source is frozen for independent delta review/build. No commit/push was performed by this author.

Earlier logs are preserved as earlier states: RED 2 failures; first GREEN 2 passes; intermediate combined 280 passes/2 ignored; intermediate scoped 12 passes. The final library log is the authority for the frozen source, not those intermediate receipts.

## The actual failure and what was stale

The parent-run [C8_checkpointability_diagnostic.json](C8_checkpointability_diagnostic.json) used the previous frozen native and records one exact checkpointability rejection:

- required 6,448,942,576 B; unchanged dynamic pool 5,789,366,831 B;
- road decode scratch 1,114,353,504 B;
- old road-decode phase 2,554,844,816 B; later independent Journey/bundle phase 2,241,577,988 B;
- `validation_scratch` 489,255,344 B and `call_binding_reserve` 82,704,900 B;
- independent event decode upper 1,414,523,320 B; actual candidate events 1,178,536,680 B.

The obsolete term was **RoadDecodeBudget's 16 B/part plus 32 B/packet/cell validation reservation**, mirrored by `RoadState::checkpoint_decode_envelope`. The actual road validator now stores only expansion accumulators and charges their real capacity growth. The Journey whole-validation scratch is different: egress grouping, stage sums, active-tag maps and dense results still allocate it. This repair retains that whole-validation scratch.

The old future road owner also reused the current retained size. A SharedKeys state can be smaller than its wire-decoded representation, because the loader first reconstructs independent 24-byte CorePart rows. That underestimation is corrected rather than concealed by deleting the stale validation term.

Finally, the old future branch kept the pre-commit input/current states alive beside a hypothetical independent future decoder. That describes neither a fresh runtime nor the populated engine after the candidate replaces current. Deleting only the stale road scratch would still leave a reconstructed 6,135,675,748 B requirement under the old context (holding its old decoded-road value fixed); it would not resolve the recorded guard.

## New source-specific phase contract

The runtime contract in [NATIVE_RUNTIME_KO.md](../../docs/v1/NATIVE_RUNTIME_KO.md) requires fresh-runtime load/replay of a last valid checkpoint. The precommit guard now takes the maximum of three explicitly separate source-visible phases:

1. **Current source/candidate transition.** Original input, current and candidate road/Journey owners; actual input/current/candidate events; actual source/candidate overlap credits only when pointer identities were verified; the real whole-validation scratch after the already-reserved call binding; and the actual census scratch.
2. **Fresh road decode.** The unchanged standalone 3*decoded-road fallback, the measured streaming scratch (with the existing 64 KiB floor), and the actual empty constructor event carrier. New service events/Journey are not alive yet.
3. **Fresh decoded bundle.** The constructor's current road (actual `RuntimeStorage.initial_road` passed from the engine), its empty event carrier, independent decoded road, complete event decode upper, decoded Journey upper, and the real whole-bundle validation workspace. Road raw-packing/streaming scratch has already died.

The permanent initial snapshot, dense arrays, static model, worker allowances and call binding remain in the unchanged fixed reserve. Constructor current road in phase 3 is an additional live owner, distinct from that permanent initial snapshot. Fresh constructor Journey dynamic StageQueue/ReceiptHistory payloads are zero. The empty service carrier is measured through `ChunkedEvents::default().storage_bytes()`, not silently omitted.

Let D denote the independent decoded-road envelope, V the measured streaming scratch, E0 the empty event shell, R0 the actual constructor current-road size, Ed the independent event decode upper, Jd the decoded Journey upper, S the real bundle scratch and B the fixed call-binding reserve. The two fresh branches are:

- P_road = 3 D + max(V, 65536) + E0.
- P_bundle = R0 + E0 + D + Ed + Jd + max(S - B, 65536).

The production requirement is max(P_current, P_road, P_bundle). There is no future alias/compression credit. Historical arithmetic for the old precommit-owner/future-decode scenario is retained only under `cfg(test)` as provenance, not as the production interpretation.

Using the old diagnostic's actual current owners/credits, the new **current transition** expression reconstructs 5,050,498,676 B, a margin of 738,868,155 B. The conservative version retaining future event upper in that phase reconstructs 5,286,485,316 B. These are arithmetic reconstructions from the old diagnostic, **not new native execution measurements**. New independent D and final runtime peak must be measured by the parent-run frozen-native experiment.

## Independent road decode and optional interning

The future road envelope mirrors fresh wire allocation:

- RoadState, cell/pending/ledger vectors, tree-entry/root allowances and packet metadata;
- 24 B per uniform row, 48 B per mixed row, independently per packet even if present payloads share Arcs/keys;
- one largest raw Part packet as overlap during raw-to-Core packing;
- the measured expansion scratch, obtained by revalidating the candidate's unchanged f64 sequence.

The decoder no longer reserves the removed materialized validation arrays. It still enforces the original 3*max owner admission before row construction; the streaming validator independently admits every accumulator growth and old/new expansion-buffer overlap. Its schema, finite/positive mass, order, route suffix, interval, record-budget and conservation predicates remain unchanged.

Exact ordered-keyset interning remains optional. Before starting it, the loader charges all new key/moment payloads and metadata. With R bounding each known old/source road owner, decoded owner D0 and interner workspace W, admission is:

max(3 max(D0,R), D0 + 2 R + W).

Thus the original three-owner admission floor remains, while the interner's actual phase contains exactly one decoded owner, at most two retained source owners, and its own work. No anticipated savings are deducted. If this does not fit, the already-validated independent road state is returned; if it fits, the original exact interner runs and the state is validated again.

W = 24*N_uniform + 1024*N_packets + 65536 is a structural upper envelope on this native layout, not an allocator/RSS theorem. Its payload part includes all 8-byte key rows and all 16-byte moment rows concurrently with charged old payloads. The metadata term covers both growing Vecs, the key lookup table, unique-backing set, moment table, lookup-bucket Vecs, Arc controls, and serial old/new backing growth. On this 64-bit layout, allowing 64-byte lookup slots and 32-byte slots for the other two tables, under their load-factor/power-of-two growth, plus conservative Vec/Arc allowances remains below 1024 bytes per packet; 64 KiB covers minimum capacities/alignment/fixed overhead. The 8 GiB process limit remains the independent physical limit.

For a decoded independent group of k>=2 uniform packets with n>=16 identical keys, the retained payload saving is 8*(k-1)*n bytes, while the additional charged key/control allowance is 96 bytes. Therefore the charged final owner cannot grow: even k=2,n=16 saves at least 32 bytes after that allowance. This justifies using the full uninterned owner as the future upper; the guard never needs to assume successful compression.

## Behavioral evidence

The new tests run the actual serializer/decoder/validator, not only budget arithmetic.

| Check | Observed result |
|---|---|
| 64 packets x 256 parts, unchanged cap | Old decoder rejected required 1,250,280 B against cap 1,242,248 B; frozen decoder succeeds at that same cap. |
| Full wire equality | All 1,049,848 serialized bytes, including signed-zero f64 values and row order, reproduce exactly. |
| Shared-key expansion | Current interned owner 270,136 B versus independent owner 399,064 B; old estimate 282,424 B was too small; new decode upper 411,352 B includes 12,288 B raw-packet overlap. |
| Actual streaming witness | Candidate and fresh decoded validation both use 416 B peak expansion workspace; obsolete reservation was 264,224 B. |
| Optional intern allowed | Full workspace and owner bounds fit; original SharedKeys representation is produced and wire is unchanged. |
| Optional intern deferred | 1024 packets x 16 parts: independent owner 475,864 B, cap 1,438,088 B, workspace upper 1,507,328 B; decoder succeeds without starting interning, wire unchanged. |
| Malformed checkpoints | Invalid cell ledger, class ledger and NaN packet target are still rejected; old target owner serializes identically before/after rejection. |
| Standalone owner fallback | A retained source of 1,000,000 B with cap 2,999,999 B still rejects at required 3,000,000 B. |
| Phase arithmetic | Future event/Journey and real bundle scratch remain fully charged in phase 3; neither their absence during road decoding nor expired road scratch during bundle validation is miscounted. |

The final suite also includes the other author's six source/lifetime preprediction regressions and the prior IEEE, FIFO, streaming, source-identity and decoder tests.

## Limits, next measurement and drift watchdog

Status is **implementation-verified**, with full-size physical acceptance **pending** at this source freeze. This author grants zero new physical seconds, zero new full-day runs and no V03 completion credit from unit tests or the arithmetic reconstruction.

The 43200 s save/load in the same populated engine remains a mandatory **OPEN** V03 acceptance obligation. The fresh-runtime guarantee does not claim arbitrary warm-engine/user-retained-snapshot coverage. Actual `NativeWholeEngine::load` source-owner, decoder, service, Journey, bundle validation and restore guards remain enforced; the parent will execute independent fresh restore of the saved frozen-native checkpoint and original hourly-cadence experiments.

Drift verdict: **ALIGNED_WITH_OPEN_OBLIGATION**. The repair supports the original explainable mesoscopic city's actual day-scale execution by removing a stale materialization reservation and assigning memory to real source lifetimes. It changes no demand, finite-response law, FIFO/interval transport, route identity, f64 wire values, tolerance, dt or resource cap. Exact checkpoint representation remains an execution contract, not the original scientific objective and not a substitute for physical progress. The historical motivation is already recorded in [METROFLOW_ORIGINAL_INTENT_WATCHDOG.md](../../docs/research/METROFLOW_ORIGINAL_INTENT_WATCHDOG.md); this bounded repair does not reopen another audit loop.
