from dataclasses import dataclass
from math import log
from typing import Sequence, Tuple

from metroflow.core.contracts import validate_state_contract
from metroflow.core.state import WorldState


@dataclass(frozen=True)
class CandidatePath:
    path_id: int
    edge_ids: Tuple[int, ...]
    path_size: float = 1.0


@dataclass(frozen=True)
class GeneralizedCostWeights:
    free_flow_weight: float = 1.0
    queue_weight: float = 1.0
    density_weight: float = 0.0
    event_weight: float = 1.0
    turn_weight: float = 1.0


@dataclass(frozen=True)
class ReroutePolicy:
    eta_degradation_threshold: float = 0.20
    refractory_steps: int = 20


@dataclass(frozen=True)
class RouteChoice:
    path_id: int
    utility: float
    rerouted: bool


@dataclass(frozen=True)
class ODRouteEvaluationRequest:
    origin_id: str
    destination_id: str
    candidates: Tuple[CandidatePath, ...]
    k: int
    world: WorldState
    weights: GeneralizedCostWeights = GeneralizedCostWeights()


@dataclass(frozen=True)
class EvaluatedCandidateRoute:
    candidate: CandidatePath
    observed_cost: float
    utility: float


@dataclass(frozen=True)
class ODRouteChoiceResult:
    name: str
    origin_id: str
    destination_id: str
    path_id: int
    observed_cost: float
    utility: float
    rerouted: bool


def path_size_factor(lengths: Tuple[float, ...], usage_count: Tuple[int, ...]) -> float:
    total = sum(lengths)
    if total <= 0:
        return 1.0
    val = 0.0
    for L, n in zip(lengths, usage_count):
        val += (L / total) * (1.0 / max(n, 1))
    return max(val, 1e-12)


def generalized_cost(
    free_flow: float,
    queue_delay: float,
    event_delay: float = 0.0,
    turn_penalty: float = 0.0,
    weights: GeneralizedCostWeights | None = None,
) -> float:
    if min(free_flow, queue_delay, event_delay, turn_penalty) < 0.0:
        raise ValueError("generalized cost components must be non-negative.")
    if weights is None:
        weights = GeneralizedCostWeights()
    return (
        weights.free_flow_weight * free_flow
        + weights.queue_weight * queue_delay
        + weights.event_weight * event_delay
        + weights.turn_weight * turn_penalty
    )


def path_logit_utility(expected_cost: float, path_size: float, lambda_sigma: float, gamma_sigma: float) -> float:
    return -lambda_sigma * expected_cost + gamma_sigma * log(max(path_size, 1e-12))


def candidate_path_k(paths: Sequence[CandidatePath], k: int) -> Tuple[CandidatePath, ...]:
    if k <= 0:
        raise ValueError("k must be positive.")
    ordered = sorted(paths, key=lambda path: (path.path_id, path.edge_ids))
    return tuple(ordered[:k])


def choose_route(
    candidates: Sequence[CandidatePath],
    expected_costs: Sequence[float],
    *,
    k: int,
    lambda_sigma: float = 1.0,
    gamma_sigma: float = 1.0,
) -> RouteChoice:
    if len(candidates) != len(expected_costs):
        raise ValueError("expected_costs must align one-to-one with candidates.")

    ordered_pairs = sorted(
        zip(candidates, expected_costs, strict=True),
        key=lambda item: (item[0].path_id, item[0].edge_ids),
    )
    bounded_pairs = tuple(ordered_pairs[:k])

    best_path: CandidatePath | None = None
    best_utility: float | None = None
    for path, cost in bounded_pairs:
        utility = path_logit_utility(cost, path.path_size, lambda_sigma, gamma_sigma)
        if best_path is None or utility > best_utility or (
            utility == best_utility and path.path_id < best_path.path_id
        ):
            best_path = path
            best_utility = utility

    if best_path is None or best_utility is None:
        raise ValueError("At least one candidate path is required.")
    return RouteChoice(path_id=best_path.path_id, utility=best_utility, rerouted=False)


def should_reroute(
    hard_event_on_route: bool,
    eta_now: float,
    eta_ref: float,
    steps_since_last_reroute: int,
    policy: ReroutePolicy,
) -> bool:
    if hard_event_on_route:
        return True
    if eta_ref <= 0:
        return False
    degraded = eta_now > (1.0 + policy.eta_degradation_threshold) * eta_ref
    refractory_ok = steps_since_last_reroute >= policy.refractory_steps
    return degraded and refractory_ok


def deterministic_reroute(
    current_path_id: int,
    candidates: Sequence[CandidatePath],
    expected_costs: Sequence[float],
    *,
    hard_event_on_route: bool,
    eta_now: float,
    eta_ref: float,
    steps_since_last_reroute: int,
    policy: ReroutePolicy,
    k: int,
) -> RouteChoice:
    current_exists = any(path.path_id == current_path_id for path in candidates)
    reroute = should_reroute(
        hard_event_on_route=hard_event_on_route,
        eta_now=eta_now,
        eta_ref=eta_ref,
        steps_since_last_reroute=steps_since_last_reroute,
        policy=policy,
    )
    if not reroute and current_exists:
        return RouteChoice(path_id=current_path_id, utility=0.0, rerouted=False)

    choice = choose_route(candidates, expected_costs, k=k)
    return RouteChoice(path_id=choice.path_id, utility=choice.utility, rerouted=True)


def _validate_od_route_request(request: ODRouteEvaluationRequest) -> None:
    validate_state_contract(request.world)

    if not isinstance(request.origin_id, str) or not request.origin_id.strip():
        raise ValueError("origin_id must be a non-empty explicit identifier.")
    if not isinstance(request.destination_id, str) or not request.destination_id.strip():
        raise ValueError("destination_id must be a non-empty explicit identifier.")
    if request.k <= 0:
        raise ValueError("k must be positive.")
    if not request.candidates:
        raise ValueError("At least one candidate route is required.")

    for candidate in request.candidates:
        if not candidate.edge_ids:
            raise ValueError("Candidate routes must include at least one edge id.")
        if candidate.path_size <= 0.0:
            raise ValueError("Candidate path_size must be positive.")
        for edge_id in candidate.edge_ids:
            if edge_id < 0 or edge_id >= request.world.graph.num_edges:
                raise ValueError("Candidate edge ids must reference valid graph edges.")


def validate_od_route_request(request: ODRouteEvaluationRequest) -> None:
    _validate_od_route_request(request)


def _evaluate_candidate_routes(
    request: ODRouteEvaluationRequest,
    *,
    lambda_sigma: float = 1.0,
    gamma_sigma: float = 1.0,
) -> Tuple[EvaluatedCandidateRoute, ...]:
    _validate_od_route_request(request)

    evaluated = []
    for candidate in request.candidates:
        observed_cost = sum(request.world.traffic.edge_travel_time[edge_id] for edge_id in candidate.edge_ids)
        weighted_cost = generalized_cost(observed_cost, 0.0, weights=request.weights)
        utility = path_logit_utility(weighted_cost, candidate.path_size, lambda_sigma, gamma_sigma)
        evaluated.append(
            EvaluatedCandidateRoute(
                candidate=candidate,
                observed_cost=observed_cost,
                utility=utility,
            )
        )

    ordered = sorted(
        evaluated,
        key=lambda evaluated_candidate: (
            evaluated_candidate.candidate.path_id,
            evaluated_candidate.candidate.edge_ids,
        ),
    )
    return tuple(ordered[: request.k])


def evaluate_od_route_request(
    request: ODRouteEvaluationRequest,
    *,
    lambda_sigma: float = 1.0,
    gamma_sigma: float = 1.0,
) -> ODRouteChoiceResult:
    bounded_candidates = _evaluate_candidate_routes(
        request,
        lambda_sigma=lambda_sigma,
        gamma_sigma=gamma_sigma,
    )

    best_choice: EvaluatedCandidateRoute | None = None
    for evaluated_candidate in bounded_candidates:
        if best_choice is None or evaluated_candidate.utility > best_choice.utility or (
            evaluated_candidate.utility == best_choice.utility
            and evaluated_candidate.candidate.path_id < best_choice.candidate.path_id
        ):
            best_choice = evaluated_candidate

    if best_choice is None:
        raise ValueError("At least one candidate route is required.")

    return ODRouteChoiceResult(
        name="od_route_choice",
        origin_id=request.origin_id,
        destination_id=request.destination_id,
        path_id=best_choice.candidate.path_id,
        observed_cost=best_choice.observed_cost,
        utility=best_choice.utility,
        rerouted=False,
    )


def evaluate_od_route_set(
    world: WorldState,
    *,
    origin_id: str,
    destination_id: str,
    candidates: Sequence[CandidatePath],
    k: int,
    weights: GeneralizedCostWeights | None = None,
    lambda_sigma: float = 1.0,
    gamma_sigma: float = 1.0,
) -> ODRouteChoiceResult:
    request = ODRouteEvaluationRequest(
        origin_id=origin_id,
        destination_id=destination_id,
        candidates=tuple(candidates),
        k=k,
        world=world,
        weights=GeneralizedCostWeights() if weights is None else weights,
    )
    return evaluate_od_route_request(
        request,
        lambda_sigma=lambda_sigma,
        gamma_sigma=gamma_sigma,
    )
