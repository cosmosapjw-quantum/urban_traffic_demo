# C8c: reuse original event storage for incoming Part payloads

Date: 2026-11-23 UTC. Source owner: v1_road.rs only.
Final road source SHA-256:
5b982c4a771ba156141941ec1fdfa49fd3bd9b7723049fae0ad62352e409cf24

## Trigger and decision

The original R8 100k, t=25720 to 25730, dt=10 s attempt still rejected
`transfer header reservation`: required 4,867,627,752 B,
budget 4,867,625,327 B, valid simulated advance zero. The 2,425 B excess
was not used as a credit or a changed cap.

Source inspection identified a separate physical duplication. A serviced
incoming Part stores tag, mass, birth-time mass, start and end that are
already present in its original EventRow. For the original intervals=true
path, the service loop assigns Part.a and Part.b from exactly that event's
start/end values before appending it. Only the route offset is independent.

The adopted representation removes that duplication. It does not aggregate
or recompute moments, discard events, change positive-mass filtering, or alter
the original FIFO or reduction order.

## Representation and resource formula

A serviced incoming row stores:

```rust
struct IncomingRowRef {
    event: u32,             // actual appended EventRow index
    offset_or_direct: u32,  // unchanged route offset
}
```

Its size is checked in tests: 8 B. Its four floating-point values are read
from the immutable source event as stored bits. tag is read from that event;
offset is copied directly. The existing independent Mark remains two f64,
16 B. Thus a full serviced slot changes from 40+16=56 B to 8+16=24 B.

A pending/direct row retains its original 40 B CompactIncomingPart in a
separate spill. The primary 8 B row uses event=u32::MAX and the direct spill
index. This costs 8 B extra per pending row while preserving one original
Part/Mark order index and aligned 128-row primary/Mark pages. Pending mass,
birth and optional endpoints remain the original full payload.

For observed fixed 128-row page counts P (primary and Mark) and D (direct
spill), raw payload bytes are

```
128 * (24 * P + 40 * D)
```

The work guard additionally includes:

- exact current descriptor capacity whenever headers are reserved/frozen;
- the conservative growth envelope outside those source boundaries;
- a 128 B allowance for every primary, Mark and spill page;
- both per-cell counter Vecs and their padding;
- observed incoming/Mark outer Vec capacities and allocation padding;
- simultaneous old/new descriptor overlap and the existing source-index
  projection scratch at header reservation.

Source-only counts project primary rows and pending spill rows before
physical appends. Every later census verifies actual row counts, page
capacities, representation and spill counts. Both page families are retired
only after the actual raw source and Mark containers are dropped.

No 8 GiB process cap, native pool cap, record limit, dt or V03 requirement
was changed. This is a physical storage representation change with
capacity-based admission, not an arbitrary credit.

## Event ownership and lifetime

ChunkedEvents now owns a distinct Arc<()> identity token. Each incoming
container holds a Weak token after its first serviced reference. Equal
EventRow values in another store do not satisfy the identity check.

Weak alone does not retain event data. IncomingPartView borrows both the
incoming container and the actual ChunkedEvents. Rust's reference lifetime
keeps event data alive through weighted-speed, latent and original combine
reads. The source token detects accidental store substitution even if the
ChunkedEvents owner itself moves.

The original source loop appends an EventRow before its incoming reference.
The saved index is events.len() immediately before that append, not the
conservative work.events projection. The insertion verifies exact tag,
mass/birth bits, finite interval bits and a real destination. A reference to
a missing row, sentinel event index, mismatched Part or different event store
is rejected.

The service event owner remains alive until all incoming source containers
have been consumed. No row-level Arc or copied mass/birth/time payload is
allocated. A Weak control block can outlive data in a rejected test case;
it cannot grant access to expired data.

The distinct event token allocation, its Arc control words and an additional
128 B allowance are included in event_store_shell_bytes. Both actual
storage_bytes and decode/append upper bounds inherit that complete shell.
R7's historical measured old-store size remains a historical receipt; the
new store has a slightly larger fixed shell.

## Eligibility and unchanged fallbacks

References are enabled only when the source is capped, intervals are enabled,
the original route/path/group registries satisfy the existing compact-domain
checks, and the configured event ceiling is below the reserved u32 code.

Uncapped, noninterval and wide-domain paths retain direct Part storage.
Standalone EventRow output and the checkpoint wire remain unchanged.
Compact event iteration, moment observation and checkpoint decoding still
return the original tuple fields and f64 bit patterns.

A short decoded last event page followed by later appends is supported by a
checked general-index fallback. Fresh original service candidates retain
the fixed 4096-row O(1) lookup path.

## Narrow pre-existing uncapped compatibility correction

The new full-tick comparison actually executed the previous uncapped direct
oracle, exposing a separate pre-existing failure:
`interval source may not replace live precombine descriptor budget`.

Uncapped work does not construct the optional descriptor accounting registry.
Two helpers now bypass only their storage-lifetime guard when limit=None:

- with_completed_source_interval executes its original operation;
- require_completed_interval_cell_slot returns its uncapped success.

Physical input checks, splitter operations and numerical checks still execute.
The capped descriptor/phase conditions remain unchanged. This is separate
from the event-reference resource RED. Its observed failure is preserved in
C8c_rust_partial_legacy_failure.log.

## Actual verification

Common environment:

```bash
cd /home/cosmosapjw/worktrees/urban-traffic-v03-event-store-moment-envelope-20261123
CARGO_TARGET_DIR=/home/cosmosapjw/worktrees/urban-traffic-v03-unique-accounting-20261120/target \
RUSTFLAGS='-C link-arg=-lpython3.12' \
cargo test --offline --workspace --lib <filter> -- --nocapture
```

1. Before implementation, a real original 10,000-row service transfer through
   propose_owned_step failed at transfer candidates with
   required=2,301,864 B against unchanged cap=2,300,000 B.
   **1 test executed, 1 failed, exit 101**.
   C8c_rust_red.log.

2. The identical physical fixture passed after implementation:
   **1 passed, exit 0**; candidate time=1 s, 10,000 original events and
   unchanged source time=0 s.
   C8c_rust_first_green.log.

3. New scoped suite:
   **7 passed, 0 failed, exit 0**.
   C8c_rust_green.log.
   It covers event and incoming page boundaries, four-f64 bit preservation,
   direct spill order and original combine output; actual per-cell projected
   and physical page/descriptor counts through release; actual event indices
   under conservative overprojection; wrong/expired/mismatched source
   rejection; independent decode and token overhead; fallback paths; and a
   complete partial-service plus pending physical tick with unchanged input
   wire and byte-identical final road wire against the uncapped direct path.

4. Whole workspace library command (same environment, no filter):
   cargo test --offline --workspace --lib -- --nocapture
   Initial combined execution: **250 passed, 1 failed, 2 ignored, exit 101**.
   All road tests passed. The separate v1_journey owner-census capacity test
   failed at block_count=1 in v1_journey.rs:3128.
   C8c_rust_full.log. Journey source during that run:
   ae8ed6dab7f5ee3f3ce95f4ee09143222539189ffb9c2d92c9484030f5cc5d5c.
   The journey owner has the shared target to correct and verify that
   independent failure; final combined evidence will be appended.

5. git diff --check passed at the road handoff. Existing compiler warnings
   remain; no full repository CI was run.

## Handoff and remaining physical evidence

Only v1_road.rs and these C8c test/verification artifacts were edited by this
worker. No commit/push, native .so copy, release build or original heavy run
was performed. The shared cargo target was handed to the journey owner after
the combined library execution.

The original 100k service/spill mix, actual total byte reduction, runtime,
next valid physical tick and subsequent blocker are still to be measured by
the parent's source-pinned original run. The 32 B serviced-slot reduction
is structural; it is not yet a claimed original-run RSS reduction or a V03
full nine-run success.

## Final combined verification received and checked

The journey owner corrected its single-table minimum HashMap capacity
allowance and reran the actual scoped and full library checks. The event-backed
road source remained byte-identical at the SHA above.

- Journey source SHA-256:
  c95c17aeada5d526f7dcf7ce2406ac68f70c6ba12b00aa70db46ccdcbff58a4a.
- C8b_rust_scoped.log and C8b_rust_scoped_receipt.json:
  7 passed, 0 failed, exit 0.
- C8b_rust_library.log and C8b_rust_library_receipt.json:
  **251 passed, 0 failed, 2 ignored, exit 0**.
- The final library log includes all seven event-backed incoming tests and
  all seven journey owner-census tests. This worker read that actual log and
  independently rechecked both source SHA-256 values and git diff --check.
- Shared cargo target has been released. No further source mutation is
  needed before the parent's review/commit/release/original physical run.
