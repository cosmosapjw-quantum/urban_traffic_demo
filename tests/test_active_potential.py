from __future__ import annotations

import math
import random

import pytest

from metroflow.learning.active_potential import (
    RouteReservationAllocation,
    RouteReservationCandidate,
    allocate_route_local_reservations,
)


def _candidate(
    candidate_id: int,
    base_disutility: float,
    effective_capacity: float,
) -> RouteReservationCandidate:
    return RouteReservationCandidate(
        candidate_id=candidate_id,
        base_disutility=base_disutility,
        effective_capacity=effective_capacity,
    )


def _compositions(total: int, parts: int):
    if parts == 1:
        yield (total,)
        return
    for head in range(total + 1):
        for tail in _compositions(total - head, parts - 1):
            yield (head, *tail)


def _route_local_potential(candidates, counts, reservation_strength: float) -> float:
    return sum(
        candidate.base_disutility * count
        + reservation_strength
        * count
        * (count - 1)
        / (2.0 * candidate.effective_capacity)
        for candidate, count in zip(candidates, counts, strict=True)
    )


def test_equal_routes_split_odd_demand_by_at_most_one() -> None:
    result = allocate_route_local_reservations(
        candidates=(
            _candidate(10, 10.0, 50.0),
            _candidate(20, 10.0, 50.0),
        ),
        demand_count=101,
        reservation_strength=4.0,
    )

    assert result.candidate_ids == (10, 20)
    assert result.assigned_counts == (51, 50)
    assert sum(result.assigned_counts) == 101


def test_zero_reservation_strength_reduces_to_deterministic_baseline() -> None:
    result = allocate_route_local_reservations(
        candidates=(
            _candidate(9, 5.0, 1.0),
            _candidate(2, 5.0, 100.0),
            _candidate(7, 6.0, 100.0),
        ),
        demand_count=12,
        reservation_strength=0.0,
    )

    assert result.candidate_ids == (2, 7, 9)
    assert result.assigned_counts == (12, 0, 0)


def test_capacity_weighting_allocates_in_proportion_for_equal_base_costs() -> None:
    result = allocate_route_local_reservations(
        candidates=(
            _candidate(0, 0.0, 1.0),
            _candidate(1, 0.0, 2.0),
        ),
        demand_count=30,
        reservation_strength=1.0,
    )

    assert result.assigned_counts == (10, 20)


def test_dominant_route_bound_keeps_all_demand_on_first_route() -> None:
    result = allocate_route_local_reservations(
        candidates=(
            _candidate(3, 5.0, 100.0),
            _candidate(4, 20.0, 100.0),
        ),
        demand_count=40,
        reservation_strength=2.0,
    )

    assert result.assigned_counts == (40, 0)


def test_zero_demand_returns_zero_counts_and_base_marginals() -> None:
    result = allocate_route_local_reservations(
        candidates=(
            _candidate(3, 7.5, 4.0),
            _candidate(1, 2.5, 8.0),
        ),
        demand_count=0,
        reservation_strength=3.0,
    )

    assert result.candidate_ids == (1, 3)
    assert result.assigned_counts == (0, 0)
    assert result.next_marginal_disutilities == pytest.approx((2.5, 7.5))
    assert result.potential_value == 0.0


def test_result_is_permutation_invariant_and_fingerprint_reproducible() -> None:
    candidates = (
        _candidate(31, 3.0, 4.0),
        _candidate(11, 2.0, 3.0),
        _candidate(21, 2.5, 5.0),
    )

    forward = allocate_route_local_reservations(
        candidates=candidates,
        demand_count=23,
        reservation_strength=1.75,
    )
    reverse = allocate_route_local_reservations(
        candidates=tuple(reversed(candidates)),
        demand_count=23,
        reservation_strength=1.75,
    )
    repeated = allocate_route_local_reservations(
        candidates=candidates,
        demand_count=23,
        reservation_strength=1.75,
    )

    assert reverse == forward
    assert repeated == forward
    assert len(forward.fingerprint) == 64
    int(forward.fingerprint, 16)


def test_reported_potential_matches_the_scientific_contract() -> None:
    candidates = (
        _candidate(5, 1.25, 2.0),
        _candidate(1, 2.0, 7.0),
        _candidate(8, 0.75, 1.5),
    )
    result = allocate_route_local_reservations(
        candidates=candidates,
        demand_count=19,
        reservation_strength=2.25,
    )
    canonical = tuple(sorted(candidates, key=lambda candidate: candidate.candidate_id))

    assert sum(result.assigned_counts) == result.demand_count
    assert result.potential_value == pytest.approx(
        _route_local_potential(
            canonical,
            result.assigned_counts,
            result.reservation_strength,
        ),
        abs=1.0e-12,
    )
    assert result.next_marginal_disutilities == pytest.approx(
        tuple(
            candidate.base_disutility
            + result.reservation_strength
            * count
            / candidate.effective_capacity
            for candidate, count in zip(
                canonical,
                result.assigned_counts,
                strict=True,
            )
        ),
        abs=1.0e-12,
    )


def test_random_small_instances_match_exhaustive_global_minimum() -> None:
    rng = random.Random(20260808)

    for _ in range(1_500):
        route_count = rng.randint(2, 5)
        demand_count = rng.randint(0, 10)
        reservation_strength = rng.random() * 5.0
        candidates = tuple(
            _candidate(
                candidate_id=100 + index,
                base_disutility=rng.random() * 10.0,
                effective_capacity=0.2 + rng.random() * 5.0,
            )
            for index in range(route_count)
        )
        result = allocate_route_local_reservations(
            candidates=candidates,
            demand_count=demand_count,
            reservation_strength=reservation_strength,
        )
        exact_minimum = min(
            _route_local_potential(candidates, counts, reservation_strength)
            for counts in _compositions(demand_count, route_count)
        )

        assert result.potential_value == pytest.approx(exact_minimum, abs=1.0e-10)
        assert sum(result.assigned_counts) == demand_count
        assert all(count >= 0 for count in result.assigned_counts)


@pytest.mark.parametrize(
    ("candidate_id", "base_disutility", "effective_capacity", "message"),
    (
        (-1, 1.0, 1.0, "candidate_id"),
        (True, 1.0, 1.0, "candidate_id"),
        (1, math.nan, 1.0, "base_disutility"),
        (1, math.inf, 1.0, "base_disutility"),
        (1, 1.0, 0.0, "effective_capacity"),
        (1, 1.0, -1.0, "effective_capacity"),
        (1, 1.0, math.inf, "effective_capacity"),
    ),
)
def test_invalid_candidate_fields_fail_closed(
    candidate_id,
    base_disutility: float,
    effective_capacity: float,
    message: str,
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        RouteReservationCandidate(
            candidate_id=candidate_id,
            base_disutility=base_disutility,
            effective_capacity=effective_capacity,
        )


def test_non_candidate_values_fail_closed_with_a_typed_error() -> None:
    with pytest.raises(TypeError, match="RouteReservationCandidate"):
        allocate_route_local_reservations(
            candidates=(object(),),
            demand_count=1,
            reservation_strength=1.0,
        )


def test_allocation_rejects_a_potential_inconsistent_with_its_counts() -> None:
    with pytest.raises(ValueError, match="potential_value"):
        RouteReservationAllocation(
            candidate_ids=(1,),
            base_disutilities=(2.0,),
            effective_capacities=(4.0,),
            assigned_counts=(3,),
            next_marginal_disutilities=(3.5,),
            demand_count=3,
            reservation_strength=2.0,
            potential_value=999.0,
        )


def test_allocation_rejects_marginals_inconsistent_with_its_counts() -> None:
    with pytest.raises(ValueError, match="next_marginal_disutilities"):
        RouteReservationAllocation(
            candidate_ids=(1,),
            base_disutilities=(2.0,),
            effective_capacities=(4.0,),
            assigned_counts=(3,),
            next_marginal_disutilities=(999.0,),
            demand_count=3,
            reservation_strength=2.0,
            potential_value=7.5,
        )


def test_allocation_rejects_a_supplied_fingerprint_mismatch() -> None:
    with pytest.raises(ValueError, match="fingerprint"):
        RouteReservationAllocation(
            candidate_ids=(1,),
            base_disutilities=(2.0,),
            effective_capacities=(4.0,),
            assigned_counts=(3,),
            next_marginal_disutilities=(3.5,),
            demand_count=3,
            reservation_strength=2.0,
            potential_value=7.5,
            fingerprint="0" * 64,
        )


def test_duplicate_candidate_ids_fail_closed() -> None:
    with pytest.raises(ValueError, match="unique"):
        allocate_route_local_reservations(
            candidates=(
                _candidate(4, 1.0, 1.0),
                _candidate(4, 2.0, 2.0),
            ),
            demand_count=1,
            reservation_strength=1.0,
        )


@pytest.mark.parametrize("demand_count", (-1, 1.5, True))
def test_invalid_demand_fails_closed(demand_count) -> None:
    with pytest.raises((TypeError, ValueError), match="demand_count"):
        allocate_route_local_reservations(
            candidates=(_candidate(0, 1.0, 1.0),),
            demand_count=demand_count,
            reservation_strength=1.0,
        )


@pytest.mark.parametrize("reservation_strength", (-1.0, math.nan, math.inf))
def test_invalid_reservation_strength_fails_closed(reservation_strength: float) -> None:
    with pytest.raises(ValueError, match="reservation_strength"):
        allocate_route_local_reservations(
            candidates=(_candidate(0, 1.0, 1.0),),
            demand_count=1,
            reservation_strength=reservation_strength,
        )


def test_empty_candidate_set_fails_closed_even_for_zero_demand() -> None:
    with pytest.raises(ValueError, match="candidates"):
        allocate_route_local_reservations(
            candidates=(),
            demand_count=0,
            reservation_strength=0.0,
        )


def _shared_link_potential(counts, base, strength, incidence, capacities) -> float:
    committed = [
        sum(incidence[link][route] * counts[route] for route in range(len(counts)))
        for link in range(len(incidence))
    ]
    return sum(base[route] * counts[route] for route in range(len(counts))) + strength * sum(
        load * (load - 1) / (2.0 * capacity)
        for load, capacity in zip(committed, capacities, strict=True)
    )


def _naive_shared_link_greedy(demand, base, strength, incidence, capacities):
    route_count = len(base)
    counts = [0] * route_count
    committed = [0] * len(incidence)
    for _ in range(demand):
        marginal = [
            base[route]
            + strength
            * sum(
                incidence[link][route] * committed[link] / capacities[link]
                for link in range(len(incidence))
            )
            for route in range(route_count)
        ]
        chosen = min(range(route_count), key=lambda route: (marginal[route], route))
        counts[chosen] += 1
        for link in range(len(incidence)):
            committed[link] += incidence[link][chosen]
    return tuple(counts)


def test_shared_link_counterexample_blocks_an_invalid_general_optimality_claim() -> None:
    demand = 2
    incidence = (
        (1, 0, 0),
        (1, 0, 1),
        (1, 1, 0),
        (0, 0, 1),
        (0, 0, 1),
    )
    base = (
        0.5400489879804283,
        1.3456969869024529,
        1.052292458753919,
    )
    strength = 2.9467983940688183
    capacities = (
        1.9072078528609808,
        2.8156718222991697,
        2.4737957822787497,
        2.227403965153344,
        0.8751301023982162,
    )
    greedy_counts = _naive_shared_link_greedy(
        demand,
        base,
        strength,
        incidence,
        capacities,
    )
    exact_candidates = (
        (
            counts,
            _shared_link_potential(counts, base, strength, incidence, capacities),
        )
        for counts in _compositions(demand, len(base))
    )
    exact_counts, exact_value = min(exact_candidates, key=lambda item: item[1])
    greedy_value = _shared_link_potential(
        greedy_counts,
        base,
        strength,
        incidence,
        capacities,
    )

    assert greedy_counts == (1, 0, 1)
    assert exact_counts == (0, 1, 1)
    assert greedy_value > exact_value + 0.24
