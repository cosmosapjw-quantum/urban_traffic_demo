# KCMB turning pockets · 코딩 단계 C1–C5

Date 2026-11-19 (KST). Research-only opt-in physical model; no existing production/default replacement. Parent 6e691bd7d29476db62a7cc69e00e5ede367ce03e; associated theory stage fdad9d963d9720dc12ebe29bac0e0e582ce2acf6, published separately.

## C1 Source and boundary
Target: cosmosapjw-quantum/urban_traffic_demo. Original authoritative V1 draft PR #41 0b9caa8cc60a3ba087722e0360b997c5dfb61d62. New isolated worktree /home/cosmosapjw/worktrees/urban-traffic-kcmb-pocket-20261119, branch research/kcmb-turn-pocket-20261119. Baseline adaptive FIFO selected tests before changes: 44 passed. Original V1 v1_road.rs, packet_network.py, main/PLAN, all old research branches and original root uncommitted state remain protected. V03 24h 3×3 campaign 0/9 and BLOCKED unchanged.

## C2 Mapping the physics
A single shared one-lane approach (length L, capacity C_A, backward wave w) is split into a shared upstream segment of length L_s=L-L_p and a *user-declared* group of G finite turning pockets of length L_p. Each pocket has explicit integer physical lanes n_g, capacity C_g [veh/s], and assigned immutable route names. The assigned routes keep their KCMBClass with existing dimensionless u=v/U and 6 conditional moments, so the microscopic/kinetic generator is not rewritten.

Original route (...,approach,downstream) -> (...,approach,pocket_g,downstream). No route-label changes. The approach head becomes a synthetic virtual pocket-entry node; each pocket's tail is that node and head is the original junction. Every route must belong to exactly one pocket. A mixed pocket shares exact ordered FIFO across its assigned routes; dedicated pockets have separate head queues and independent output signal gates. The original head is strictly one physical upstream lane for a defensible queue-order rule. Lane change inside the shared segment is not modeled.

Physical lane-metres changed by Δ=(sum_g n_g-1)L_p; this explicitly declared road widening is not a conservation violation. Class occupied length is b_a M_a [m], and each pocket's own receiving length limit is n_g L_p. A separate lossless geometry mapping is impossible for prior snapshots lacking per-lane vehicle positions; only new model state and explicitly supplied initial profile are accepted. All CFL constraints are validated on each new segment. Explicit names/units/route assignment are required, no inferred topology.

## C3 Numerical and approximation error
The compiler itself does not approximate a numerical array. It creates a **physically distinct graph** for the previous CertifiedAdaptiveFIFO algorithm with the same kinetic moment generator and finite-volume node step. The spatial splitting changes free-flow eligibility to dt[ceil(L_s/(Udt))+ceil(L_p/(Udt))], which is greater than or equal to the old one-link eligibility and differs by at most dt at constant U (no extra congestion). It changes the number of local receiving buffers and may delay/jam differently; this is not a bit-equivalent optimizer. It leaves network source birth history and class/route event contracts as in the previous kernel.

## C4 Bounded execution and dependencies
New source touches only src/metroflow/v1/kcmb_turn_pockets.py; tests live in tests/research/test_kcmb_turn_pockets_20261119.py. The runtime depends only on existing KCMB link/route immutable structs, no new Rust bindings or global scheduler. If the base graph has E physical links and K immutable routes, G new pocket groups increase total links to E+G, with existing adaptive runtime's 6(E+G)K+3K moment entries and max B ordered runs. No automatic snapshot migration. Malformed lane data, duplicate or missing route assignments, illegal clock resolution, 2-lane shared approach misrepresented as strict FIFO, invalid lane_policy, or new node/link name collision is fail-closed at construction.

## C5 Implemented feature and behavioral tests
New PocketGroup(name, routes, lanes, capacity_veh_per_s), TurnPocketLayout(approach,pocket_length_m,groups), PocketGeometryLedger and CompiledPocketNetwork, compiled using compile_turn_pockets(config,layout) -> physically valid independent KCMBNetworkConfig. Consumers instantiate CertifiedAdaptiveFIFO(compiled.config,backend="python"|"rust",max_runs=B) explicitly.

The new test-first public import failed before module implementation. The resulting code passed the new scoped tests for: route/source identity, physical lane-metre ledger, no widening mixed pocket, physically independent B turn with A red, backpressure from full A pocket blocking B behind A in the shared lane, no same-step vehicle teleportation, negative geometry, split-cell CFL, config immutability and model-ID checkpoint mismatch, random signal/lane mass conservation, Python–Rust node parity, and preventing silent import of independent_turn as shared_head.

## C5 stage stop
Once baseline+new scoped unit/integration tests and static code checks pass, commit and push the source+tests+this report. Then separately C6–C10 will perform resource/fidelity benchmarks, adversarial review, final targeted regression, receipts and a new push. Real observation comparison (inD/UTD19) is not simulated; existing V03 acceptance is unchanged.
