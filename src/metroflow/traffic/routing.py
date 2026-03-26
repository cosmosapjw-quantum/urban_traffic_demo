from dataclasses import dataclass
from math import log
from typing import Tuple


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


def path_size_factor(lengths: Tuple[float, ...], usage_count: Tuple[int, ...]) -> float:
    total = sum(lengths)
    if total <= 0:
        return 1.0
    val = 0.0
    for L, n in zip(lengths, usage_count):
        val += (L / total) * (1.0 / max(n, 1))
    return max(val, 1e-12)


def generalized_cost(free_flow: float, queue_delay: float, event_delay: float = 0.0, turn_penalty: float = 0.0) -> float:
    return free_flow + queue_delay + event_delay + turn_penalty


def path_logit_utility(expected_cost: float, path_size: float, lambda_sigma: float, gamma_sigma: float) -> float:
    return -lambda_sigma * expected_cost + gamma_sigma * log(max(path_size, 1e-12))


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
