# Journey/service retained allocation coverage

Implementation location: isolated `urban_traffic_runtime_budget` worktree,
baseline `27e426fc64452ae2492828653f94f2506b8881fc`. The separately running campaign
checkout is not modified by this work.

The old constructor estimate remains a construction-admission observation. The
following getters describe actual retained native allocation structure so that
the engine need not subtract construction peak assumptions again before assigning
runtime budgets. These are conservative structural estimates, not measured RSS
or a theorem about a particular allocator's total overhead.

| API | Included heap storage | Excluded storage / owner |
|---|---|---|
| `NativeJourneyCore::static_storage_bytes()` | Actual capacities of leg/bus/freight metadata Vecs; owned leg Strings; route-index HashMap table and owned keys; each unique Arc profile/law object and its Vec payload | Inline core headers: engine; dense arrays: dense getter; stages/receipt blocks: existing dynamic getter; transient constructor interning maps: constructor admission |
| `journey_dense_storage_bytes(&Journey)` | Released, completed, original-birth vectors; dense ReceiptHistory pointer vector | Stage registries/blocks and receipt payloads: existing dynamic getter |
| `NativeServiceCore::static_storage_bytes()` | Bus/person/source declaration Vecs; bus IDs and schedule Vecs; freight/car IDs; run-to-person index registry and child Vecs | Dense mutable state and last-event rows |
| `service_dense_storage_bytes(&Service)` | Run, passenger, released, completed, car-state Vec capacities | Last events: event getter |
| `service_event_storage_bytes(&ServiceCheckpoint)` / `NativeServiceCore::event_storage_bytes()` | Actual EventRow Vec capacity | Sink Strings and temporary grouping: road working envelope |
| `NativeJourneyCore::validation_scratch_bytes(&Journey)` | Egress grouping map and per-leg value Vec growth; bus/freight maps; sequential largest-profile clone/sort and one fsum buffer | Engine's own validation maps; parallel worker scratch; dense snapshot copies |
| `NativeJourneyCore::per_worker_scratch_bytes()` | Largest-profile clone/sort capacity plus 64 KiB scalar/expansion reserve | Caller multiplies by actual native worker count |
| `NativeServiceCore::prepare_scratch_bytes()` | Static-count source/bus offers, formatted labels, offer-buffer growth, physical conversion, eligibility and boarding-key workspace | Dense state snapshots; dynamic journey source offers |

Every nonempty Vec/String buffer includes 128 bytes of allocator padding. Arc
storage includes the two reference counters, the heap Vec object, its payload
capacity and independent allocation padding. Deduplication uses `Arc::as_ptr`,
the address of the heap Vec object, not the address of its elements. Distinct
empty Arcs therefore remain distinct allocations. Profiles and laws are counted
once across all journey legs and bus/freight metadata; the engine counts only
its own profile-Arc registry buffer, not those shared payloads a second time.

Retained HashMap accounting uses its actual usable capacity and a conservative
two-bucket multiplier plus control-byte allowance. A fresh map's scratch bound
uses four buckets per possible distinct entry to cover growth slack and minimum
table size. Egress value buffers charge `2*rows + 4*distinct_groups` floats plus
per-allocation padding; this covers both geometric growth and short Vec minimum
capacity. These layout estimates are explicitly implementation policy.

The known dense-state envelope is four journey copies and six service copies.
This covers initial/input/current/candidate journey states and service rollback
plus before/after arrays passed to journey finish. On engine post-validation
failure, the result bundle must be dropped before restoring an input state;
otherwise the fallback temporarily creates another dense clone. Unrelated
caller-retained snapshots remain subject to the process resource ceiling.

Dense capacity is not a serialized scientific property. In the legacy direct
`NativeJourneyCore.restore` API, collecting a `Vec<Vec<Receipt>>` into the smaller
`Vec<ReceiptHistory>` can reuse the original allocation in place. The two-leg
test observed 576 bytes before restore and 608 afterwards: the 24-byte outer
elements' allocation can become capacity six for 8-byte history pointers. The
actual-capacity getter correctly reports this difference. The opaque whole
engine does not use that Python-row conversion: its constructor uses fixed-size
dense Vecs, binary decoding reserves each declared count, and bundle cloning
copies each Vec's length. Capacity changes in a future whole-engine boundary
must be included in admission instead of assuming that equal checkpoint rows
imply equal allocation footprints.

At coupled-call start, the road service-event envelope receives the input
`last_events` capacity and maximum route-tag String capacity. Before each road
proposal it receives the current last-event capacity. The road owner combines
these known buffers with newly proposed events, sink String copies and the
service sink-group map before allocation. Dense service copies are already in
the fixed engine envelope and are not charged again as events.

No source measures, arithmetic operations, transition order, event order or
serialized physical state are changed by these getters and accounting calls.
ReceiptHistory raw rows and serialized payload remain unchanged. Two per-block
byte-accounting caches additionally bound fresh decoding; their own retained
bytes are included by the existing allocation-size calculation.

## One dynamic pool with phase-specific allowances

The coupled loop accepts an optional total dynamic budget; the legacy direct
Python wrapper passes `None`. Its admission scopes are:

- Journey preparation: subtract two times the larger known input/current road
  allocation and two times the larger input/current event allocation. The
  journey guard accounts its own three owners and proposal/offer workspaces.
- Road proposal: subtract three times the maximum input/current/pending journey
  dynamic allocation. The road envelope includes its owners, generated events,
  sinks and service grouping workspaces.
- Journey finish: after road workspaces and the service sink-map clone drop,
  subtract three times the maximum input/current/candidate road allocation,
  three times the maximum input/current/new event allocation, and actual
  remaining sink Vec/String capacity. The journey guard accounts its new
  stage/history allocations.

Subtraction is checked and produces a resource error before the corresponding
phase. A failure after service finish still restores the previous service state,
discards the pending journey, and leaves the road candidate uncommitted. Phase
allowance setters are nonphysical metadata and do not clone or validate state.
Explicit engine boundaries clear stale call-input accounting before a new
branch/load; internal phase setters retain the current call-input charge.

Dynamic journey offers charge original/reallocated Vec growth, physical offer
conversion and generated-label allocation padding. The fixed service preparation
reserve covers the additional static-count bus/freight/car offers before the road
proposal preflight. The total pool replaces an arbitrary persistent owner split;
it does not raise the total memory ceiling.

## Focused verification

`tests/v1/test_native_retained_accounting.py` adds seven tests:

- Four references to one shared law grow the estimate by exactly one payload;
  a different law adds another payload and its object/control allowance.
- Equal profiles in distinct input lists are interned and charged once.
- Static, dense and dynamic journey storage retain separate lifetimes through
  transitions and restore.
- Independently owned freight/car Strings are each charged, while dense/event
  storage is unchanged by their lengths.
- A filtered StageQueue's canonical decode envelope covers every fresh
  row-append preflight and final allocation.
- Receipt histories forked on every append retain a decode envelope covering
  fresh replay, despite copy-on-write changes to expansion-vector slack.
- Many independent histories charge the sum of final decoded storage plus only
  one largest sequential decoder workspace, including advance/restore cache
  lifetime checks.

Local source checks: `git diff --check` and Python test compilation passed.
The first isolated native run exposed the invalid test assumption that dense
capacity must survive legacy row restore unchanged; the test now checks exact
physical snapshot, static ownership and empty dynamic payload instead.
Native build/test results must be taken from the root agent's isolated-worktree
build and test log; no native PASS is inferred from source inspection.

## Last-valid states must remain checkpointable

The first native resource-failure test found a state accepted by tick-local
guards that could be saved but rejected by a fresh decoder/whole validator.
Whole-engine finish now defers its final commit. `mem::replace` moves the old
journey and cached receipt counts/bytes into a rollback stash while the proposed
state is checked against the common whole-validation and decode envelope. It
adds no dense clone. On failure, that stash is moved back and the service owner
uses its existing rollback state; the road candidate is still uncommitted. On
success, road, event and journey owners finalize in the same infallible section.
Direct legacy Python finish keeps its original immediate-commit behavior.

The canonical precommit envelope takes three times each owner's largest known
input/current/candidate/fresh-decode footprint, plus the maximum of whole-map
validation scratch beyond the already reserved call binding, road decode
validation scratch, and the journey decoder's 64-KiB reserve. Decode and whole
validation occur in separate phases, so those scratch terms are maximized,
rather than summed. The engine delegates whole-validation scratch to the same
helper; the two paths must not silently drift apart.

Stage decode estimates depend only on row count: fresh 256-row blocks,
power-of-two tail capacity, geometric pointer registry capacity, and the largest
append preflight. Receipt decoding keeps the same raw 64-row partition. Its
global prefix expansion is cloned and updated before every append, then assigned
after copy-on-write, so its allocation is determined by raw row order. A fresh
decoder can retain more block-local expansion slack than frequent COW clones;
that slack is bounded by one component per block row. Each block caches both
the final decoded capacity upper bound and the maximum prefix append-preflight
bound. Since histories are decoded sequentially, Journey charges the sum of
final decoded capacities plus the maximum single-history working-minus-final
delta, rather than summing all histories' temporary decoder workspaces. The
final-capacity sum updates per appended row; the delta is a conservative
monotone maximum within the current call. Restore/install recomputes the current
sum and maximum during its existing history pass, and deferred rollback restores
both cached values. This avoids another scan of millions of history slots at
every tick and does not introduce a heap index of historical maxima.

The root's actual R2 native release build and seven targeted tests (including
same-budget save/fresh-load/replay after resource failure) passed before this
last sequential-workspace tightening. The final tightened source requires its
own native test run; the earlier PASS is not attributed to untested changes.
