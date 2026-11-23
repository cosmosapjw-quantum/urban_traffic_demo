# C8e — checked 40-byte event storage and unchanged generic decoder admission

Date: 2026-11-23. Scope: `crates/metroflow-rust/src/v1_road.rs` and this verification record. This is the physical event representation repair within R8. The separate C8d checkpoint decoder lifetime repair is in `v1_journey.rs`; the final combined library run includes both changes.

## Result and exact source identity

**Implementation-verified:** eligible event payloads now occupy 40 bytes per allocated row, with the existing 48-byte compact and 64-byte original representations retained for wider codes. The independent service decoder, unchanged checkpoint wire, incoming event references, original row order and four stored f64 values are exercised by the scoped and combined tests below. The 10,000-row bounded physical fixture now completes under the same 2,000,000-byte cap that the previous source actually rejected.

- Frozen road SHA-256: `e25adb5d6c5d7bdb1202f6c529f5b7a3b1a23334f8f63b9fbb9780e81277db2d`.
- Combined journey SHA-256: `2d3397ff500fbb9e96a9ae04343f7638c037974bd652583761e84996009fff35`.
- Final combined library: **261 passed, 0 failed, 2 ignored; process exit 0**.
- `git diff --check`: exit 0.
- No release build, shared-object replacement, original 100k experiment, commit or push was performed by this worker. The shared Cargo target and frozen source were returned to the parent after verification.

The original t=25720 checkpoint's next accepted tick remains an experimental question for the parent's new-source execution. The bounded fixture is not counted as a V03 planned node or an accepted original tick.

## Representation and admission contract

| Tier | Code representation | Payload bytes per row | Selection |
| --- | --- | ---: | --- |
| Narrow | tag u32, source u16, destination u16; None=65535 | 40 | Every row code is exactly representable; destination Some(65535) is excluded |
| Standard compact | Existing u32 codes and existing None sentinel | 48 | Compact codes fit but the narrow row does not |
| Original | Existing usize / Option representation | 64 | Original noncompact path, including wide registries |

`NarrowEventRow` is `repr(C)` and contains the same four f64 fields. Compression copies these values without numerical conversion, recomputation, reordering or aggregation. Source 65535 is representable because the source has no None sentinel. Destination Some(65535) instead selects the standard tier, preserving its distinction from None. Tag and source overflow do not silently truncate.

`CompactEventPage` is a single ordered enum descriptor containing either a narrow Vec or a standard Vec. A page starts in the representation selected by its first actual row. If a later row needs wider codes, only the current narrow page is promoted to a standard page of the same row capacity. The previous payload coexists with its replacement during this promotion; earlier pages, logical indices and event order stay unchanged. A later new page may again be narrow. The original wide event mode remains separate.

The C8c incoming references still use actual `events.len()` before append, not projected event counts. `IncomingPartView` borrows the event data; the existing Weak token checks source identity and does not claim to keep event payload alive. Narrow-to-standard promotion preserves index semantics and f64 bits. The source token allocation and its control-block allowance remain charged.

## Actual storage versus conservative future decode admission

The actual compact payload is the sum of each page's actual row capacity times its own 40- or 48-byte row size. The actual enum descriptor is 32 bytes on this tested x86-64 target; the previous Vec descriptor was 24 bytes. Actual descriptor capacity, per-page allocation allowances and the existing event shell/token allocations are included. Therefore the payload reduction is not reported as an identical total storage reduction.

`event_store_upper_bytes` charges the shell, row payload, 128 bytes per page, conservative descriptor reallocation overlap `3 * (pages + 1) * descriptor_size`, and another 256 bytes. When compact row codes have not been proved narrow, it also admits the simultaneous old narrow payload during one-page promotion: `min(rows, 4096) * 40` bytes. Append admission rounds the allocated row capacity up to complete 4096-row pages; checkpoint decoding can allocate the final page to its exact remaining wire-row count.

There are two deliberately different admissions:

1. Road generation with the verified registry condition `groups.len() <= 65535` plus the existing compact eligibility uses the 40-byte payload bound. All generated source and destination indices then fit the narrow representation, so no promotion allowance is needed for this proved path.
2. **Future independent decoding keeps the generic 48/64-byte bound.** The native loader selects its row ceiling before it observes payload codes. `ChunkedEvents::decode_storage_upper_bytes()` therefore delegates to the same generic `decoded_event_store_upper_bytes()` used by that loader, even when every stored page happens to be narrow. It does not promise a 40-byte future admission that the real loader would reject before reading its first row. Unknown-source promotion scratch remains included.

For the historical 20,270,113-row source store, `8 * 20,270,113 = 162,160,904` bytes is the derived payload reduction if all allocated rows are narrow and their capacities are otherwise unchanged. Additional descriptor width changes the total. This is a representation calculation, not a measured new-source original checkpoint receipt; the parent will measure the new store. The earlier measured 973,795,992-byte C8c source store and the older R7 973,795,840-byte store remain historical values with their original source identities.

## Actual RED and GREEN evidence

All commands ran in `/home/cosmosapjw/worktrees/urban-traffic-v03-event-store-moment-envelope-20261123`, with:

```bash
CARGO_TARGET_DIR=/home/cosmosapjw/worktrees/urban-traffic-v03-unique-accounting-20261120/target \
RUSTFLAGS='-C link-arg=-lpython3.12' \
cargo test --offline --workspace --lib <filter> -- --nocapture
```

The final full command omits `<filter>`. The tests are real library execution against production storage and decoder paths.

| Evidence | Selection / result | Exit | Log |
| --- | --- | ---: | --- |
| Initial calibration | Two narrow tests; payload test failed, physical fixture at 2.1 MB passed | 101 | `C8e_rust_red.log` |
| Strict RED, before representation change | Two narrow tests; both failed | 101 | `C8e_rust_red_strict.log` |
| Scoped GREEN | `narrow_`: 12 passed, 0 failed | 0 | `C8e_rust_green.log` |
| First combined run, preserved | 260 passed, 1 failed, 2 ignored | 101 | `C8e_rust_library_first_failure.log` |
| Final combined run | 261 passed, 0 failed, 2 ignored | 0 | `C8e_rust_library.log` |

The calibration's 2.1 MB physical fixture was not a RED and is not presented as one. The strict 2.0 MB fixture was fixed before implementing the new representation. On the old source its actual road execution failed at `phase=transfer candidates`, `required_bytes=2024048`, `budget_bytes=2000000`. On the new source the same 10,000-row fixture completes one second with 10,000 events; the original input clock stays zero. The other strict RED observed actual decoded payload 960,528 bytes against the proposed 800,440-byte narrow bound for 20,011 rows.

The four new `v03_narrow_event_tier_20261123_tests` cover exact sizes and sentinel/overflow boundaries; mixed-page promotion with existing incoming references; actual NativeServiceCore wire write/read/re-encode for narrow, standard and wide paths; and generic decoder/append bounds including promotion overlap. The actual decoder accepts the exact row ceiling and rejects the one-row-smaller limit. Existing incoming reference tests also run in the final suite, including source identity rejection, pending/direct spill, page boundaries, conservative event-counter overprojection and wire equality of the bounded path against the existing uncapped physical oracle.

The first full run exposed one obsolete exact size expectation in `exact_event_page_live_capacity_contract_tests`: it expected 48 bytes per row for a fixture whose tag/source/destination indices all fit the newly selected narrow tier. The log is preserved. The corrected test is named `physical_page_chunk_capacity_matches_checked_narrow_tier`; it first verifies that every compact page is Narrow and then requires the exact `allocated_rows * size_of::<NarrowEventRow>()` payload equality. It does not replace the equality with a looser inequality. The other preexisting narrow-compatible 3-page storage fixture was updated to the same exact 40-byte representation expectation. The final combined command ran once after this concrete correction and passed, PID 3938354, exit 0.

The combined log explicitly includes all four C8d sequential-checkpoint-decoder lifetime tests and all seven C8b road-phase Journey ownership census tests. Their source remained at the journey SHA above. No redundant second full library run is needed for those tests.

## Limits and handoff

This change reduces real retained event payload. It does not add an arbitrary cap credit, alter either native or process caps, reduce original demand or the planned 10-second step, drop events, change FIFO, change the serialized wire, or claim that source and candidate event arrays are shared when they are not. The generic future decoder guard remains conservative even when actual payload is narrow.

The parent owns the original trace-off 10-second execution and subsequent 20/40-second escalation, checkpoint receipt analysis, final V03 readiness accounting and stage push. Full-original acceptance, elapsed time and peak RSS must be taken from those new-source receipts, not inferred from the bounded RED/GREEN result.
