# V03 continuation: exact ordered interval and native backend
Both original V03 bottleneck research and Rust-only migration are authorized. Baseline 40a5a1d22ca5bbc8825d8bd78c7af288fe6b1396; current valid 25660s, separate historical 25720s identity. Preserve finite-response closure, legal FIFO, marks, time and conservation, original 3x3 full-day requirement, 6 GiB internal and 8 GiB RSS/address limits, 7200s wall. No approximation substituted for acceptance. Fixed 15-group census. Python only explicit oracle tests; scientific measurement Rust.

## R1–R10: original V03 blocker research (scoped, concurrent with migration)

### R1 — bind the original question and identity
The original goal is an executable coupled-city simulation, not a compressed
surrogate traffic law. Use the frozen Valley weekday seed7 manifest
2088b2df7a0bb0503adea24bfcdec196758171d5d52f64f42b03269dcb008bd3
and the previously verified 25660-s checkpoint. Preserve the original
6 GiB accounting and 8 GiB RSS/address-space ceilings. No change to the
release acceptance horizon or 3-city, 3-repeat requirement.
The historical 25720/25730 resource failure of another source/model identity
is a separate experiment, not a matched comparator.

### R2 — literature and limitation of transfer
C. F. Daganzo, The Cell Transmission Model: Network Traffic (1994 preprint),
https://escholarship.org/uc/item/9pz309w7 : destination/time-of-entry
disaggregation, FIFO diverges, and parallel network decomposition.
Bar-Gera and Carey (2017), Representation requirements for perfect FIFO,
https://scispace.com/papers/representation-requirements-for-perfect-first-in-first-out-4zrcgrs1c8
(abstract-level evidence); Rust Arc pointer identity:
https://doc.rust-lang.org/std/sync/struct.Arc.html .
The literature motivates preservation of traffic order and provenance;
it does not prove correctness of the new wire format.

### R3 — mechanism
A row is (tag,offset,mass,birth,a,b). In each packet the two interval
endpoints may be common. For shared-key packets, the sequence
K=((tag_i,offset_i)) is immutable and may be physically shared while
M=((mass_i,birth_i)) remains independent. Distinguish physical Arc
allocation identity from value equality. Allocation aliases are not
identical to logical vehicle owners. Event and journey owners remain
independent of road packet storage.

### R4 — competing hypotheses and choice
Approximate coalescing by mass/birth moments may reduce state count but can
change time-of-entry and turning order. Even two unit-mass packets with
birth moment zero and supports [0,1] and [1,2] have distinct cumulative
arrival at t=0.5. Equal first moments are insufficient. Similarly, although
m*(r/d) and (m*r)/d agree over the reals (d>0), they need not have equal
binary64 evaluations. Do not factor or reorder the established split or
reduction expressions. Choose a reversible representation and checked
streaming validation, not a new closure or a hidden sampling rule.

### R5 — constructive exactness
Define E1 as legacy row expansion, E2 as MFWHOLE2 road encoding and D2
as its decoder. The queue-local dictionary is the immediately preceding
explicit shared-key declaration (Uniform/Mixed do not reset it). Induction
on queue packet order: the first shared declaration writes all keys;
a back-reference can only be emitted for Arc::ptr_eq with this live
declaration; the decoder restores the same ordered keys and the independent
moment vector. Every uniform or mixed row and every packed endpoint retains
its exact bits. Thus E1(D2(E2(S)))=E1(S) for admissible encoded states;
v2 byte equality across different allocation graphs is not claimed.
The rest of the whole checkpoint is unchanged v1 service/journey encoding.
Checked finite expansions preserve the former packet-mass nested reduction,
flat occupied-length reduction, and per-class order; overflow is rejected,
not made into an infinite or NaN ledger.

### R6 — owner/scratch expression and admissible scope
For packet i with n_i rows, a mixed representation charges 48 n_i bytes,
uniform charges 24 n_i, shared charges 16 n_i plus 8 n_i + 96 when
a new key owner must be decoded. Add outer cell/queue/packet and ledger
metadata. This is the decoder's structural accounting, not an allocator
RSS theorem. No credit for arbitrary nonadjacent or cross-queue sharing.
For P packets across both road and pending queues and C cells, the compact
validation workspace bound is 2 MiB + 64 P + 32 C bytes. Expansions cap
4096 terms; bounded finite accumulators and pointer-census metadata replace
the prior row-count-proportional validation reservation. The legacy mode
keeps its established admission contract; its historical decoded-owner
estimate may undercount uninterned shared-key expansion.

### R7 — actual exact computation
C02: same original25660 input, same one-tick horizon25670, old/new outputs
exactly equal. C03/C04: compact wire roundtrip, invalid record rejection,
original small fixture and full original loaded25670 v1-to-v2-to-v1
SHA256 equality. C05/C06: checked streaming validation and computed
codec envelope test including mixed and cross-queue aliases.
The real output has 2210069010 bytes in v1 and 1191094722 bytes in v2.
C08: actual ready FIFO head suffix with declared equal owner/class, common
prefix, common terminal link and legal turns changes the subsequent physical
destination; owner mismatch and illegal turn rejected, ledgers and bits
unchanged at transition. This is not a production journey-owner integration.

### R8 — quantitative discrimination
At25690 C09 strict recovery: 29808444 road rows, 545540 cell packets,
compact decoded owner559851152 bytes, compact scratch37062464 bytes;
historical legacy scratch formula494443136 bytes on the same state.
The scratch reduction is structural and not a measured whole-process
memory saving. The historical25730 failure requires scratch <=487931679
with all other recorded owner terms fixed; the new formula suggests
a possible route but historical owner lifetimes, identity and actual decoder
must be replayed before declaring that failure resolved. Do not extrapolate
from the different current identity or equate file size with RAM.

### R9 — audit boundaries
No physical approximation, budget increase, hidden record deletion, or
guard observe-mode bypass. The proposed exact representation changes the
wire schema intentionally, so manifest binding and binary provenance must
remain explicit. New codec is opt-in; original v1 export remains available.
C07 extended-real cost syntax "+inf" is distinct from null/NaN/negative
infinity. C08 remains a road-level checked transaction; actual live variant
routing needs canonical journey binding, causal observations and atomic
whole-world commit. No theorem about arbitrary suffix selection is asserted.

### R10 — convergence criterion
Retain the new codec and streaming validation, because exact logical
roundtrip and actual loaded execution are established within scope.
Next: match fresh 25720/25730 continuation under the same identity,
profile actual growth of packet and event owner lifetime, compact service
event representation with versioned wire if needed, and evaluate runtime
and refinement before 3x3 full-day acceptance. Rust-only migration and
scientific release acceptance use independent metrics. Full-day acceptance
remains 0/9 until the required runs actually finish.

## Current strict native continuation
From25660 to25670: exact matched legacy checkpoint on prior and new
inline expansion executable. From25670 to25690: v2 execution succeeded
under the unchanged accounting/RSS/AS caps. From25690 to25710: C07
executable, native compact owner/scratch projection active, strict record
trace, 159.696294319s wall, 3551391744B peak RSS, 2114614050B v2 checkpoint.
At25710 the largest recorded guard ratio is road_work:entry interval split
3952516364 / 5038399871 = 0.784478498; checkpointability requires
4266696484 / 5788793063, with road_decode_scratch49371904. The bottleneck
has shifted to ordered entry intervals and concurrent physical owners.
A one-tick wall-time improvement was not established. Full-run wall cap,
full-day 3x3 acceptance and historical distinct-identity blocker are not
changed.
