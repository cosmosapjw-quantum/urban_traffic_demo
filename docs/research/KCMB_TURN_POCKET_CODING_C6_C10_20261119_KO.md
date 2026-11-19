# KCMB physical turning pockets · 코딩 C6–C10 과학 검증 및 단계 인계

Date: 2026-11-19 KST. Research-only opt-in physical model. Parent source 6e691bd7d29476db62a7cc69e00e5ede367ce03e; theory stage fdad9d963d9720dc12ebe29bac0e0e582ce2acf6; C1–C5 code stage 00bd29a1a630372ea1539be1abe02b9c39185b42. Original V1 draft PR #41 remains 0b9caa8cc60a3ba087722e0360b997c5dfb61d62, not changed.

## C6 Implementation validation and repairs

**Behavioral RED → GREEN:** The public import failed without the new code; after implementation 11 initial tests passed. An adversarial test subsequently found that independent_turn physical policy was accidentally accepted by the new compiler although the ordered-run engine demands single-lane shared_head. This test failed before adding an explicit semantic guard, then 14 new tests passed. This was a physical-policy error, not a formatting issue.

**Selected regression**: 14 new turning-pocket cases plus 208 prior KCMB/CTM/V1 checks yielded 222 passed. Rust with explicit Python3.12 linking flags reported 61 unit tests passed. Cargo workspace check and Python bytecode compilation executed successfully. New feature is a pure Python topology adapter using pre-existing optional Python/Rust node allocator; no new low-level native extension and no change to production default.

## C7 Physical validation and derived limits

Theory P1–P4 addresses physically declared lane-metres, route conservation, conditional FIFO, discrete earliest travel time and bounded state.

- Original shared one-lane approach 100m contains 100 lane-metres. Compiled physical approach: upstream 70m ×1 lane plus 2 dedicated pockets each 30m ×1 lane, giving 130 lane-metres. Additional 30 lane-metres is an explicitly declared road widening, not byte-exact equivalence to the old geometry.
- When a B vehicle mass has reached its own turning pocket, it can flow under A red and B green despite another A vehicle mass being stuck in A pocket. In contrast, when shared upstream has an A head blocked by a jam-filled red A pocket, B behind A cannot enter its otherwise empty independent B pocket.
- A mixed single pocket with one lane preserves full ordered FIFO blocking when A is red and at its head; it has zero added lane-metres.
- Source birth cannot be traversed across upstream and pocket in a single timestep. At fixed positive U, the minimum link eligibility of the split link differs from the original single link by 0 or dt due to ceil quantization, even before queues, so same travel-time trajectories are not claimed.
- Source route labels and physical driver-class constants are unchanged. Invalid topology, wrong physical policy, missing/duplicate pockets, two-lane shared upstream mapped as a strict one-run queue, too-short pocket violating CFL, checkpoint model mismatch, wrong physical lane length and missing route assignments are refused.
- Real pocket lengths, lane counts and signal phases must be supplied from legitimate map/field data; synthetic names do not authorize inferring real geometry.

## C8 Quantitative synthetic simulation and resource sensitivity

Identical offered mass and green/red signal schedule in 180 steps with dt=0.5s: 0.25 vehicle-equivalents/route/step until tick110, then 0 new arrivals; left red until tick110, right green. The 3 *different physical geometries* are: unsplit one-lane 100m approach (3 links), 70m shared upstream plus a mixed 30m pocket (4 links), and 70m upstream plus two independent 30m pockets (5 links, +30 lane-metres).

At tick110, before left becomes green, cumulative B completions were:
coarse one-lane = 0; one mixed turning pocket = 0; two independent turning pockets = 5.611092185827814 vehicle-equivalents. This is a synthetic conditional physics sensitivity, not a measurement of actual urban traffic.

Five separate sequentially executed runs per backend and each geometry, alternating Python/Rust process execution order. Median time over 180 steps [seconds]:

| Physical geometry | Python-node | Rust-node | Python/Rust ratio |
|---|---:|---:|---:|
| one-lane unsplit | 0.047299 | 0.040878 | 1.157 |
| one mixed pocket | 0.071037 | 0.060899 | 1.166 |
| two separate pockets | 0.065913 | 0.054066 | 1.219 |

Same-geometry Python/Rust outputs agree within checked numerical budgets and mass ledger residuals are below 1e-8veh. Across-geometry results are NOT a code-speedup comparison: models have different physical topology, capacity and state size. State moment scalar counts for 3/4/5 links with 2 routes are 42/54/66 plus bounded route-run records. Whole Python/Rust process RSS is distinct from scalar state counts and no metropolitan-scale throughput/RSS speed claim is made.

Raw evidence: artifacts/kcmb_turn_pocket_20261119, one JSON for each geometry+backend and 5-repeat records, plus FIVE_REPEAT_GEOMETRY_COMPARISON.json and test/build logs.

## C9 Adversarial limits and outcome

The physical-model compiler assumes ONE shared upstream lane with a fully ordered link queue. Multi-lane upstream vehicle overtaking, dynamic lane changes and within-tick actual vehicle ordering are not reconstructed. Existing six kinetic moments remain aggregated over route, not per vehicle. Unknown per-lane initial positions mean a generic old checkpoint cannot be migrated losslessly to the split pocket geometry. Synthetic pocket layout names and capacities are explicit input assumptions, not a map-matched ground truth.

No global network node-invariant entropy or collision-free microscopic car-following theorem is established. Initial lane group assignments require real topology; correctness of code does not confer empirical realism. Upstream PR41 V03 100k inhabitants / 3 cities ×3 daily runs has not been executed with this new model and is still BLOCKED 0/9.

## C10 Decision, reproducibility and publication

SCOPED_TURN_POCKET_GEOMETRY_VERIFIED applies only to the bounded physical topology compiler, its conditional lemmas and same-model synthetic tests. Real inD/UTD19, OpenDRIVE topology and field observation validation are NOT_MEASURED. Full GitHub PR creation, merges and main changes are NOT_REQUESTED/NOT_RUN.

Deliver: source src/metroflow/v1/kcmb_turn_pockets.py; tests tests/research/test_kcmb_turn_pockets_20261119.py; reference tools/research/bench_kcmb_turn_pockets.py; this report plus verified hashes and actual C10_RESEARCH_RECEIPT.json. Final C6–C10 commit must be individually pushed after tests and followed by exact remote SHA readback.

Next minimal scientific step: connect a real mapped approach's physical lanes, pocket lengths and signal phases, then evaluate FIFO blocking, B throughput, shock speed and travel-time distribution under separate-day calibration/holdout. Generalize to multi-lane upstream and real lane-change interaction only when geometry/data justify it. Avoid widening the production V03 acceptance contract or retroactively altering previous research claims.
