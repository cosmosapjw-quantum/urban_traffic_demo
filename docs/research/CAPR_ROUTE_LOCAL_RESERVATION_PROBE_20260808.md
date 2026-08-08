# CAPR Route-Local Reservation Probe — 2026-08-08

## Status

**Experiment-only implementation probe.** This document and the accompanying
module do not change route legality, candidate generation, traffic flow, active
agent movement, runtime defaults, or adaptive-policy authority.

Pinned design baseline:
`codex/runtime-closure-remediation@1c4222dc1bf07c9633c687d64e6332b0f5ac66ca`.

## Research question

Can a finite same-decision-epoch cohort be distributed over already legal
MetroFlow route candidates by a deterministic committed-load pressure term,
while preserving the present least-cost behavior when that pressure is zero?

The first coding slice answers only the route-local separable version of that
question.

## Mathematical contract

For candidate route `k`, let

- `b_k` be its finite base disutility in generalized travel-cost ticks;
- `K_k > 0` be a route-local effective reservation capacity in vehicles;
- `n_k` be its assigned integer vehicle count;
- `chi >= 0` be the reservation-pressure strength in cost ticks.

For total demand `N`, the discrete potential is

\[
\Phi(n)=\sum_k b_kn_k
+\frac{\chi}{2}\sum_k\frac{n_k(n_k-1)}{K_k},
\qquad \sum_k n_k=N.
\]

The next exposed marginal value is

\[
d_k(n_k)=b_k+\chi\frac{n_k}{K_k}.
\]

Because each candidate exposes a nondecreasing marginal sequence, repeatedly
selecting the smallest exposed marginal value chooses the globally smallest
`N` feasible slots and minimizes the separable integer potential. Candidate ID
is the deterministic tie-breaker.

This is a specialization of classical bottom-up algorithms for discrete
separable resource allocation. The greedy algorithm is not claimed as a new
mathematical method; its value here is an exact, auditable finite-agent bridge
for the project-specific CAPR closure.

## Implemented surface

`metroflow.learning.active_potential` provides:

- `RouteReservationCandidate`;
- `RouteReservationAllocation`;
- `allocate_route_local_reservations(...)`.

The result is canonicalized by candidate ID, checks all formula invariants,
conserves integer demand exactly, and carries a stable SHA-256 fingerprint.
Its declared authority is
`experiment_only_baseline_candidates`.

## Verified limits

- `chi = 0`: deterministic least-base-disutility selection, with ID tie-break;
- equal base cost and equal capacity: counts differ by at most one;
- equal base cost with capacities `1:2`: demand `30` allocates `10:20`;
- zero demand: zero counts and base next marginals;
- dominant-route bound: all demand remains on the lower-cost route;
- 10,000 deterministic random small cases: zero disagreement with exhaustive
  enumeration of the separable potential;
- fixed replay payload: identical across different `PYTHONHASHSEED` values.

## Explicit negative result

The same one-at-a-time greedy logic is **not** globally exact for a general
route-link incidence matrix. A preserved three-route, five-link, two-vehicle
counterexample gives

- naive shared-link greedy: counts `(1, 0, 1)`, potential
  `2.6389117077751303`;
- global integer optimum: counts `(0, 1, 1)`, potential
  `2.397989445656372`;
- strict gap: `0.2409222621187581`.

Therefore no general shared-link or system-optimal claim is authorized by this
module. A future shared-link lane must compare controlled convex/subgradient or
integer solvers and report an optimality gap when exact solution is unavailable.

## Prior-art boundary

The broader ingredients are established:

- route-overlap/path-size correction;
- route inertia and status-quo dependence;
- proactive rerouting designed to avoid the lemming effect;
- atomic congestion-game potentials;
- mean-field and multi-agent routing games;
- anticipatory route guidance and system-optimal path marginal cost;
- bottom-up discrete resource allocation;
- physics-informed route-assignment learning.

The project-specific research hypothesis is not any one ingredient. It is the
conjunction of exact baseline-owned legal candidates, causally lagged virtual
commitment, a transparent potential/Lyapunov contract, deterministic replay and
fallback, and a future prediction-only learner that cannot legalize routes or
mutate vehicle mass.

Selected primary references:

- Hoogendoorn-Lanser, van Nes & Bovy (2005), DOI
  `10.1177/0361198105192100104`.
- Qi et al. (2023), DOI `10.1016/j.tra.2022.11.013`.
- Bilgram et al. (2021), DOI `10.1177/03611981211000348`.
- Rosenthal (1973), DOI `10.1002/net.3230030104`.
- Kaufman, Smith & Wunderlich (1991), DOI `10.4271/912815`.
- Qian, Shen & Zhang (2012), system-optimal DTA with path marginal cost and
  spillback.
- Han et al. (2020), DOI `10.1016/j.trb.2020.02.004`.
- Zaporozhets (1997), DOI `10.1016/S0167-6377(97)00026-6`.
- Cabannes et al. (2021), arXiv:`2110.11943`.
- Ke et al. (2025), DOI `10.1016/j.trc.2025.105040`.

## Promotion boundary

This isolated module may be reviewed as an experiment substrate. Runtime
integration remains **on hold** until all of the following are available:

1. stable route identity derived from graph/version/OD/ordered link sequence,
   rather than refresh-local candidate rank;
2. a declared construction and validity test for route-local effective capacity;
3. shared-bottleneck comparison against an exact or gap-reporting oracle;
4. incident/recovery workloads showing reduced concentration or regret without
   worse completion, tail travel time, spillback, conservation or replay;
5. repository CI and independent diff review.
