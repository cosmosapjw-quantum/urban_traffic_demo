# Road retained-static accounting

Baseline: `27e426f`, isolated `urban_traffic_runtime_budget` worktree. This change
adds `V1Road::static_storage_bytes() -> usize` and
`owned_storage_bytes() -> usize`. A separately authorized extension accounts
for service event/sink storage in the coupled road working quota. Neither
change alters physical updates, checkpoint row encoding, numerical tolerances,
or the completed campaign preserved in the original worktree.

The returned structural size is

`sizeof(V1Road) - sizeof(RoadState) + identity.capacity() + owned registry heap capacities`.

| Owned field | Included allocation |
| --- | --- |
| `identity` | String capacity in bytes; String header is in `sizeof(V1Road)` |
| `groups`, `classes` | Outer `Vec<Vec<f64>>` capacity plus every initialized inner vector's capacity |
| `paths`, `incoming` | Outer `Vec<Vec<usize>>` capacity plus every initialized inner vector's capacity |
| `signals`, `routes`, `windows` | Actual vector capacity multiplied by the compiler's element size |
| Scalar configuration, vector headers, diagnostic mutex | Inline `V1Road` size, excluding the inline `RoadState` |

All arithmetic saturates. Counts use capacity rather than length, so spare
reserved storage is included. Road paths are owned vectors, not shared `Arc`
allocations: interned paths are counted once in `paths`, while each route alias
still occupies its own entry in `routes`. Equal contents in different owned
vectors are separate allocations and are both counted.

`RoadState::retained_storage_bytes()` separately includes the state header,
actual Uniform/Mixed packet capacities, cell/source queues and ledgers, plus
its documented tree and per-buffer structural allowances. Subtracting the
inline `RoadState` above avoids charging that header twice when the engine
combines the two getters.

`RoadState::checkpoint_decode_envelope()` is a nonallocating pair `(R, V)` for
reload admission. `R` is retained structural storage plus
`sizeof(Part) * maximum_packet_part_count`. The decoder charges every raw
48-byte part before reading it; a Uniform packet then charges its new 32-byte
cores while that raw buffer is still live and subtracts the raw capacity only
after packing. Thus its cumulative decode counter never exceeds the final
decoded owner plus the largest raw packet. Fresh exact-capacity vectors are no
larger than the corresponding retained vectors, and the decoder's root,
per-buffer and latent-tree allowances match the retained getter.
`V = 16 * total_parts + 32 * (packets + cells)` matches the decoder's validation
increments. The phase coordinator must combine `3 * max(input, current, R) + V`
with other live owners; the getter itself assigns no quota and changes no codec.

Excluded scopes are construction-only lookup maps and temporary input copies;
motion, FIFO, transfer, interval splitting and packet-packing scratch; other
owners' immutable snapshots; service `last_events`; the engine's private Rayon
pool and thread stacks; Python wrappers; and allocator metadata. These are not
zero-cost claims. They require their existing owner/phase accounting and the
fixed process address-space limit. In particular, this getter is not a process
RSS measurement or an allocator-memory theorem, and it must not be substituted
for a construction peak estimate while construction is still in progress.

The constructor-only `bind_storage_identity(String)` refuses a nonempty or
advanced owner. Its caller must remeasure the final identity String capacity
after binding the new engine policy. It is not exposed through Python.

The internal `set_phase_storage_budget(bytes)` assigns the engine's remaining
combined dynamic allowance and derives the finite raw-part ceiling from it.
It performs no state scan and changes no identity or physical data; existing
phase preflight checks remain responsible for allocation admission. Too small
an allowance fails atomically as a resource error.
`clear_call_storage_accounting()` resets known call-input and service-event
metadata after public advance and before load/restore. The engine restores the
total dynamic allowance at those boundaries and separately counts the supplied
input bundle for final capture, so stale metadata cannot constrain a later
branch or checkpoint decode.

## Coupled service-event lifetime

`configure_service_event_accounting(input_bytes, max_tag_bytes)` fixes the
current call's input-event capacity, and
`set_service_event_current_bytes(current_bytes)` refreshes the committed event
capacity before each road proposal. A new call or explicit state installation
clears old context. The per-tick candidate does not clear it.

For `n` proposed event rows, let `c = 0` for `n = 0` and otherwise
`c = max(4, 2n)`. The additional working envelope counts:

- `3 * max(input_bytes, current_bytes, c * sizeof(EventRow))` plus three
  buffer-allocation allowances, covering input/current/proposed event buffers
  and the final snapshot lifecycle.
- `(c + n) * sizeof((String, f64, f64))` for the push-built sink vector and its
  service-finish clone, plus two copies of each tag payload and a 32-byte
  allocation allowance per String.
- 256 bytes per proposed event for the service sink `HashMap<&str, Vec<f64>>`,
  minimum mass-vector capacities and reduction scratch, plus fixed map/tag
  formatting allowance.

Every event is conservatively treated as a potential sink. The envelope
replaces the road's former two-copy event term when coupled context is active;
the two terms are not added together. Road packet/candidate storage remains
in the existing road base, while dense service-state copies belong to the
engine's fixed reserve. The engine's final capture/validation admission check
is a separate phase check, not another simultaneous allocation charged here.
These are explicit structural allowances rather than an exact hash-table or
allocator-memory theorem. The process limit still applies.

Validation: source field inventory checked against every field of `V1Road`;
`git diff --check` executed locally. Native compilation and the engine-level
retained/construction separation regression are delegated to the parent run;
no native PASS is claimed by this artifact.
