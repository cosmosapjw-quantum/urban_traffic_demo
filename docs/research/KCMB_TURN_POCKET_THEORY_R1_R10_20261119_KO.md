# KCMB physical turning-pocket model · 병행 이론 루프 R1–R10

Date: 2026-11-19 KST. Status: scoped theory for an opt-in geometry-aware KCMB traffic approximation. Parent SHA: 6e691bd7d29476db62a7cc69e00e5ede367ce03e. Upstream authoritative V1 draft PR #41 head: 0b9caa8cc60a3ba087722e0360b997c5dfb61d62. The original main, original packet solver, V03 acceptance gates and pending local changes are protected.

## R1 Goal
Microscopic finite-response and two-state Markov traffic control must meet macroscopic conservation and physically located lane supply constraints. The previous KCMB ordered-run model has only a *shared_head* or *independent_turn* global closure. Next bounded scientific goal: add explicit finite-length turning pocket geometry to resolve the observed physical case where red-turn traffic blocks a shared upstream queue but does not block traffic **already occupying an independent pocket**.

## R2 Evidence and background
Primary literature: M. Gao, *A Node Model Capturing Turning Lane Capacity and Physical Queuing for the Dynamic Network Loading Problem* (2012), DOI 10.1155/2012/542459: node modeling should distinguish directional turning-lane queues instead of imposing global FIFO across all lanes. Wright, Gomes and Horowitz (2017), *On node models for high-dimensional road networks*, Transportation Research B: partial FIFO depends on lane/access geometry. Bar-Gera & Carey (2022), DOI 10.1016/j.trb.2022.04.002: perfect FIFO can require substantial computation. These are modeling precursors, not proof of KCMB's empirical accuracy or global entropy invariant property. Source: src/metroflow/v1/kcmb_network.py, kcmb_ordered_fifo.py, kcmb_adaptive_fifo.py and the parent physics documents.

## R3 Definitions, conventions and assumptions
Single explicitly shared *upstream one-lane* approach segment A with length L_s [m], width 1 lane, flow cap C_A [veh/s], backward wave w_A [m/s]. Last L_p>0 [m] of the original approach is divided into G physical turning-pocket lane groups P_g, each with declared positive integer lane count n_g and capacity C_g [veh/s]. The original link length L=L_s+L_p; upstream geometry has 1 lane, while the turning region can flare to sum_g n_g lanes, a physically different cross section. All parameters are user-supplied, never inferred from network naming or destination alone.

Every immutable KCMB route a that traverses A is assigned to **exactly one** named pocket. A shared pocket can contain several routes and then uses the prior ordered-run within-pocket FIFO. In a dedicated pocket, all routes have the declared pocket access. Each pocket's route class retains its own U_a [m/s], footprint b_a [m/veh], Markov rates alpha_a, nu_a [s^-1] and response tau_a [s]. dt [s] obeys each split link's CFL: dt max(U_a,w_link)/L_segment <= 1. No exact per-vehicle velocity/position, real lane change trajectory or empirical geometric map match is assumed.

Original path ...→A→downstream is replaced by ...→A_shared→P_g→downstream, using a new synthetic virtual node at pocket entry. All route names and physics parameters remain unchanged; downstream links unchanged. The compiler rejects unknown, duplicate, unassigned or illegally overlapping route-group definitions. No checkpoint migration is possible automatically when the original link's internal lane residence history is unknown.

## R4 Alternatives and selection
A. Global shared_head on original unsplit link: over-blocks other turn lanes after vehicles have already separated.
B. Global independent_turn on original link: allows B vehicles to bypass an A-leading blockage even when they remain in the same shared lane.
C. **Selected:** explicitly split physical approach into shared one-lane upstream and G finite pockets; use existing certified adaptive FIFO on the transformed network. The split induces a new spatial-resolution approximation with a known free-flow quantization penalty.
D. Fully lane-resolved microscopic lane-changing: stronger geometric fidelity, but requires observed lane and gap/driver distributions and more state.
E. Invariant entropy node/second-order kinetic continuum: future alternative, not claimed as achieved by C.

## R5 Constructive derivation and proofs

**Lemma P1: Physical lane-metres accounting.** Original approach's registered storage is one lane × (L_s+L_p) = L_s+L_p [lane·m]. The declared new storage is L_s + L_p sum_g n_g [lane·m]. Thus exactly
ΔS_lane-metres = (sum_g n_g - 1)L_p.
This is neither double-counting nor exact preservation of the *old geometry*: if the pocket region has more physical lanes, its declared extra storage is a model input. For route class a, occupied metres are b_a M_ia; the downstream receiver limits each pocket to its declared n_g L_p and the original shared part to L_s. Proof: segment area of independent lane groups is additive; all receiving constraints use one physical segment's dedicated resource. □

**Lemma P2: Route conservation and conditional FIFO.** Assume an original route path is contiguous and nonself-repeating, and each crossing route a has one pocket group g(a). After replacing A by A_shared→P_g(a), the resulting path is contiguous. Its single route label is unchanged in all link–route kinetic moments and ordered-run records. Within the shared physical segment and each individual pocket the old ordered FIFO algorithm serves only the existing head prefix. A red movement P_A→dest_A cannot directly block green B movement P_B→dest_B if they use separate pocket links and B's sending/receiving budgets are positive. If A-leading vehicles occupy shared A and P_A is full, then shared FIFO blocks B behind A even if P_B has vacancy. Proof: path's new virtual node precisely joins the shared head to all pocket tails, and each pocket has a disjoint physical sending/receiving ledger. The route-only red constraint is downstream of the pocket, while the old head-prefix rule is still enforced in the common shared segment. Induction over the conservative node transfers yields route conservation and no same-step teleportation. □

**Lemma P3: Discrete free-flow delay perturbation.** Ignoring new signal/storage queues and using constant positive class free-flow speed U, old one-link eligibility is t_old=dt ceil((L_s+L_p)/(U dt)); split-link eligibility for serial transit is t_split=dt[ceil(L_s/(U dt))+ceil(L_p/(U dt))]. The identity ceil(x)+ceil(y)-ceil(x+y)∈{0,1} for positive x,y gives 0≤t_split-t_old≤dt. This *quantized* latency is a physical-model discretization artifact, not exact equality of the old and new travel time or a bound on congested travel time. □

**Lemma P4: No dynamic packet genealogy introduced.** If original fixed network has E directed links, K route classes and user-defined ordered run budget B, one split replaces the original link by 1 shared link and G pocket links. The new bulk state has at most 6(E+G)K+3K scalar slots and the ordered-run auxiliary state at most 3B fields (apart from fixed link/node metadata). Without routing changes this is O((E+G)K+B); if the user permits an unbounded number of pockets, the theorem does not give a uniform resource bound. Any infeasible exact ordered run representation fails closed. Proof: count fixed array slots and explicit run budget, not vehicles or source-event rows. □

**No stronger theorem claimed:** The generic node allocator is not proven an invariant entropy Riemann solver. A shared upstream lane is modeled with one FIFO run queue; multi-lane upstream arrangements or lane-changing behavior require a different law. Field realism requires real turning-pocket lengths, lane counts, signal timings and observed travel-time/queue data.

## R6 Adversarial examples and acceptance
1. Split A/B pockets; B already in its pocket, red A pocket output, green B output: B must flow despite A red.
2. Same A/B order still in shared upstream; A pocket is full and red; B behind A cannot enter its pocket (no premature bypass).
3. Compare lane-metres: one-lane approach of length 100m and 30m pockets with two separate 1-lane pocket groups -> 70 + 30×2=130 lane·m. This is a physically declared widening by 30 lane·m, not silent invented capacity.
4. Reject incomplete/duplicate pocket assignment, zero/negative lanes or lengths, name collisions, unrealistic CFL, 2-lane upstream falsely certified as single-lane strict FIFO.
5. Don’t initialize a new split geometry by reinterpreting a pre-existing old queue snapshot without observed positions; create a new state or explicitly mapped profile only.

## R7 Prototype physical tests
Use opt-in compiled config and CertifiedAdaptiveFIFO, with the same kinetic six-moment physics and Rust/Python node selection. Test exact route/pocket path identities, targeted red/green vs shared-upstream spillback, repeated random signal mass/footprint/clock bounds, checkpoint identity, model distinction, link count scaling, and withheld geometry. Compare same-model physical output across Python/Rust backend.

## R8 Admission
P1–P4 derived under the stated scope; no data-driven calibration or map-matched road data performed. The new compilation changes geometry and resolution. Its theoretical correctness is therefore conditional, not identity with original V1 or the original one-link KCMB. The old V03 3 cities×3 runs×24h remains BLOCKED 0/9.

## R9 Code contract and model ID
Provide new module src/metroflow/v1/kcmb_turn_pockets.py with immutable PocketGroup and PocketLayout and a compile_turn_pockets(config,layout) pure function returning a compiled KCMBNetworkConfig plus physical geometry ledger. The runtime remains explicit CertifiedAdaptiveFIFO(compiled.config,backend="python"|"rust",max_runs=B). Preserve original source, PR, main, acceptance, and checkpoint types. Use a different model_id automatically because the physical graph differs; separate compiled scheme version and declared assumptions retained in returned manifest.

## R10 Durability
Theory stage commit/push first with SHA readback; coding stage only after actual behavioral red/green and checks; numerical/evidence stage committed and pushed after scoped tests and measured resource/cost verification. A future session shall not reinterpret this as real-city 24h/empirical acceptance. Next track: derive lane-group assignments from actual OSM/OpenDRIVE or inD intersection geometry and compare queue discharge/turn blocking against observations on matched site/time windows.
