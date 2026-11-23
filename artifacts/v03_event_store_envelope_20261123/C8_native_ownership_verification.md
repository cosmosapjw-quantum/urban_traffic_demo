# C8: frozen queue ownership and restore-clock proof

Date: 2026-11-23 UTC. Worktree:
`/home/cosmosapjw/worktrees/urban-traffic-v03-event-store-moment-envelope-20261123`.

## Actual blocker evidence and scope

R6's original 100k, dt=10 s, trace-off request from t=25720 failed at
`transfer candidates`: required 4,867,625,496 B against 4,867,625,327 B.
This is an admission failure, not successful physical progress.
The 169 B difference is not a justified numerical credit.

Parent's separate R7 record-mode diagnostic measured:
- full road work source base: 3,565,321,424 B;
- actual phase base after existing motion/combine lifetime adjustments:
  1,901,806,568 B;
- events: 1,772,443,240 B;
- raw incoming page allowance: 925,609,136 B;
- diagnostic source capacity: 267,874,816 B;
- source and retained input each 865,303,248 B;
- first source/committed Arc overlap: 794,297,808 B.

The different record-mode peak is not a performance comparison: its live
diagnostic source storage is additional. Original event-store savings were
separately observed by the parent. None of these scalar receipts proves a
particular frozen-queue saving before the revised native run.

## Source lifetime proof

1. `step_state` creates `out.cells[*].packets` empty.
2. Predictions call `clone_packet` from the immutable supplied RoadState.
   Each cloned PacketParts holds identical immutable Arc backing storage;
   physical packet/Vec shells remain separate and remain charged.
3. A queue record with readiness exactly positive infinity cannot enter
   `heads`: `EventClock::after_ready(+infinity)` is true for every finite
   ordinary or compensated event clock.
4. Such a record cannot enter served-row iteration or remainder packing.
   At the survivor boundary the original queue packet is moved, unchanged,
   into `out.cells[*].packets`. Later entering packets are appended; they
   do not mutate these source survivors.
5. Therefore every pointer-confirmed backing shared between the source
   and such a queue record stays shared with the working candidate for
   the entire remaining RoadWorkBudget lifetime.
6. Deduct only actual data Vec capacities for distinct (layout, Arc pointer)
   witnesses. Repeated SharedKeys or whole-payload Arc clones count once.
   Equal contents in independent allocations establish no credit.
7. The witness census uses one temporary descriptor per matching packet
   backing. Requested and observed capacity plus a 128 B allocation allowance
   and Vec shell are checked before any credit. Sorting is in place; the
   descriptor Vec is dropped before installing the credit.
8. The source/committed restore-time overlap is a separate pair. It now
   requires the existing original source witness at the same physical clock.
   A self comparison after another tick is not accepted. The experimental
   environment flag cannot create or prolong this witness.

This is a lower bound on duplicated payload inside the existing structural
work allowance. It does not change RLIMIT_AS, policy caps, dt, simulation
arithmetic, packets, routes, source data, serialized fields or iteration order.
It is not an allocator/RSS theorem.

## Implementation

Only `crates/metroflow-rust/src/v1_road.rs` changed in C8.

- Added pointer-only matching-backing visitor for Uniform, SharedKeys and
  wide Mixed storage.
- Added `witness_frozen_queue_owners` after prediction/motion scan ownership
  has settled and before any service.
- Added a scalar credit to the existing work guard and record-mode field
  `frozen_queue_source_payload_credit`.
- Tightened original input pair eligibility to the preexisting restore-clock
  witness. Standalone paths without such a witness receive no input-pair
  credit. First original whole-engine tick retains its verified pair;
  subsequent ticks conservatively receive zero until separately proven.
- No change to EventRow counts, positive-mass filtering, event representation,
  record limits, sink behavior, FIFO, mass/birth arithmetic or checkpoint wire.

## Actual verification

Common build environment:

```bash
cd /home/cosmosapjw/worktrees/urban-traffic-v03-event-store-moment-envelope-20261123
CARGO_TARGET_DIR=/home/cosmosapjw/worktrees/urban-traffic-v03-unique-accounting-20261120/target \
RUSTFLAGS='-C link-arg=-lpython3.12' \
cargo test --offline --workspace --lib <filter> -- --nocapture
```

- Before implementation, filter
  `later_tick_cannot_reuse_original_restore_clock_arc_overlap`:
  **1 test executed, 1 failed, process exit 101**.
  Existing base remained 748,904 B instead of the expected 850,280 B:
  the 101,376 B restore-clock witness had incorrectly survived.
  Evidence: `C8_rust_red.log`.
- An intermediate compile attempted the new field before three old test
  constructors were updated. It exited 101 with three E0063 missing-field
  errors. This is an implementation iteration, not a behavior RED.
  Evidence: `C8_rust_compile_first.log`.
- Filter `v03_frozen_queue_source_ownership_20261123_tests`:
  **6 passed, 0 failed, process exit 0**.
  Evidence: `C8_rust_green.log`.
- `cargo test --offline --workspace --lib --quiet` with the same environment:
  **237 passed, 0 failed, 2 ignored, process exit 0**.
  Evidence: `C8_rust_full.log`.
- `git diff --check`: exit 0.

The six scoped tests cover expired restore proof; same-value independent
allocations and finite/negative-infinite readiness refusal; duplicate
SharedKeys and wide capacity; scratch-before-credit and exact cap/+1 B
rejection; a complete physical tick's original EventRow bit order, unchanged
input wire, candidate wire against the uncapped path, and survivor Arc
identity; ordinary and compensated finite-clock exclusion of +infinity.

Existing compiler warnings remain. Full repository CI was not run.

## Remaining physical test and explicit limits

The Rust implementation is ready for the parent's source commit, release
build, and original trace-off 100k request at t=25720. No native .so was
copied, no original heavy process launched, and no commit/push made by this
worker. Shared cargo target is released.

The actual original frozen-backings byte count and ability to finish the
next original physical interval remain unverified until that run.
Finite ready >= dt is intentionally excluded: tolerance and compensated
clock comparison require a separate boundary proof. Prediction already
maps packets beyond its motion reach to +infinity, so no large omitted
finite-ready set is asserted. This change does not resolve all possible
later incoming/splitting/snapshot admission constraints or certify the full
nine-run V03 contract.
