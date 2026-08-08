"""Experiment-only route-local active-potential reservation allocation.

The allocator in this module operates only on caller-supplied legal route
candidates.  It does not create routes, authorize turns, mutate simulation
state, or replace MetroFlow's deterministic routing authority.

Its exact optimality claim is deliberately narrow: the route-local separable
potential defined in ``SCIENTIFIC_CONTRACT.md``.  General shared-link coupling
requires a different solver and is outside this module's validity regime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from heapq import heapify, heappop, heappush
import json
import math
import operator
from typing import Iterable

__all__ = [
    "ACTIVE_POTENTIAL_SCHEMA_VERSION",
    "ACTIVE_POTENTIAL_RUNTIME_AUTHORITY",
    "RouteReservationAllocation",
    "RouteReservationCandidate",
    "allocate_route_local_reservations",
]

ACTIVE_POTENTIAL_SCHEMA_VERSION = 1
ACTIVE_POTENTIAL_RUNTIME_AUTHORITY = "experiment_only_baseline_candidates"


@dataclass(frozen=True, slots=True)
class RouteReservationCandidate:
    """One already-legal route candidate for the reservation experiment.

    ``base_disutility`` and the global reservation strength use generalized
    travel-cost ticks. ``effective_capacity`` is a positive vehicle count.
    """

    candidate_id: int
    base_disutility: float
    effective_capacity: float

    def __post_init__(self) -> None:
        candidate_id = _require_nonnegative_integer(
            self.candidate_id,
            name="candidate_id",
        )
        base_disutility = _require_finite_float(
            self.base_disutility,
            name="base_disutility",
        )
        effective_capacity = _require_finite_float(
            self.effective_capacity,
            name="effective_capacity",
        )
        if effective_capacity <= 0.0:
            raise ValueError("effective_capacity must be > 0")
        object.__setattr__(self, "candidate_id", candidate_id)
        object.__setattr__(self, "base_disutility", base_disutility)
        object.__setattr__(self, "effective_capacity", effective_capacity)


@dataclass(frozen=True, slots=True)
class RouteReservationAllocation:
    """Canonical deterministic output of route-local reservation allocation."""

    candidate_ids: tuple[int, ...]
    base_disutilities: tuple[float, ...]
    effective_capacities: tuple[float, ...]
    assigned_counts: tuple[int, ...]
    next_marginal_disutilities: tuple[float, ...]
    demand_count: int
    reservation_strength: float
    potential_value: float
    runtime_authority: str = ACTIVE_POTENTIAL_RUNTIME_AUTHORITY
    schema_version: int = ACTIVE_POTENTIAL_SCHEMA_VERSION
    fingerprint: str = field(default="")

    def __post_init__(self) -> None:
        candidate_ids = tuple(
            _require_nonnegative_integer(value, name="candidate_ids")
            for value in self.candidate_ids
        )
        if not candidate_ids:
            raise ValueError("candidate_ids must not be empty")
        if len(set(candidate_ids)) != len(candidate_ids):
            raise ValueError("candidate_ids must be unique")
        if candidate_ids != tuple(sorted(candidate_ids)):
            raise ValueError("candidate_ids must be in canonical ascending order")

        base_disutilities = tuple(
            _require_finite_float(value, name="base_disutilities")
            for value in self.base_disutilities
        )
        effective_capacities = tuple(
            _require_finite_float(value, name="effective_capacities")
            for value in self.effective_capacities
        )
        if any(value <= 0.0 for value in effective_capacities):
            raise ValueError("effective_capacities must be > 0")
        assigned_counts = tuple(
            _require_nonnegative_integer(value, name="assigned_counts")
            for value in self.assigned_counts
        )
        next_marginals = tuple(
            _require_finite_float(value, name="next_marginal_disutilities")
            for value in self.next_marginal_disutilities
        )

        width = len(candidate_ids)
        for name, values in (
            ("base_disutilities", base_disutilities),
            ("effective_capacities", effective_capacities),
            ("assigned_counts", assigned_counts),
            ("next_marginal_disutilities", next_marginals),
        ):
            if len(values) != width:
                raise ValueError(f"{name} must match candidate_ids length")

        demand_count = _require_nonnegative_integer(
            self.demand_count,
            name="demand_count",
        )
        if sum(assigned_counts) != demand_count:
            raise ValueError("assigned_counts must sum exactly to demand_count")
        reservation_strength = _require_finite_float(
            self.reservation_strength,
            name="reservation_strength",
        )
        if reservation_strength < 0.0:
            raise ValueError("reservation_strength must be >= 0")
        potential_value = _require_finite_float(
            self.potential_value,
            name="potential_value",
        )
        expected_marginals = tuple(
            base
            + reservation_strength * count / capacity
            for base, capacity, count in zip(
                base_disutilities,
                effective_capacities,
                assigned_counts,
                strict=True,
            )
        )
        if any(
            not math.isclose(actual, expected, rel_tol=1.0e-12, abs_tol=1.0e-12)
            for actual, expected in zip(
                next_marginals,
                expected_marginals,
                strict=True,
            )
        ):
            raise ValueError(
                "next_marginal_disutilities are inconsistent with the allocation"
            )
        expected_potential = sum(
            base * count
            + reservation_strength
            * count
            * (count - 1)
            / (2.0 * capacity)
            for base, capacity, count in zip(
                base_disutilities,
                effective_capacities,
                assigned_counts,
                strict=True,
            )
        )
        if not math.isclose(
            potential_value,
            expected_potential,
            rel_tol=1.0e-12,
            abs_tol=1.0e-12,
        ):
            raise ValueError("potential_value is inconsistent with the allocation")
        runtime_authority = str(self.runtime_authority)
        if runtime_authority != ACTIVE_POTENTIAL_RUNTIME_AUTHORITY:
            raise ValueError("runtime_authority does not match the experiment contract")
        schema_version = operator.index(self.schema_version)
        if schema_version != ACTIVE_POTENTIAL_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must be {ACTIVE_POTENTIAL_SCHEMA_VERSION}"
            )

        payload = {
            "assigned_counts": assigned_counts,
            "base_disutilities": base_disutilities,
            "candidate_ids": candidate_ids,
            "demand_count": demand_count,
            "effective_capacities": effective_capacities,
            "next_marginal_disutilities": next_marginals,
            "potential_value": potential_value,
            "reservation_strength": reservation_strength,
            "runtime_authority": runtime_authority,
            "schema_version": schema_version,
        }
        expected_fingerprint = _fingerprint_payload(payload)
        supplied_fingerprint = str(self.fingerprint).strip()
        if supplied_fingerprint and supplied_fingerprint != expected_fingerprint:
            raise ValueError("fingerprint does not match allocation contents")

        object.__setattr__(self, "candidate_ids", candidate_ids)
        object.__setattr__(self, "base_disutilities", base_disutilities)
        object.__setattr__(self, "effective_capacities", effective_capacities)
        object.__setattr__(self, "assigned_counts", assigned_counts)
        object.__setattr__(self, "next_marginal_disutilities", next_marginals)
        object.__setattr__(self, "demand_count", demand_count)
        object.__setattr__(self, "reservation_strength", reservation_strength)
        object.__setattr__(self, "potential_value", potential_value)
        object.__setattr__(self, "runtime_authority", runtime_authority)
        object.__setattr__(self, "schema_version", schema_version)
        object.__setattr__(self, "fingerprint", expected_fingerprint)


def allocate_route_local_reservations(
    *,
    candidates: Iterable[RouteReservationCandidate],
    demand_count: int,
    reservation_strength: float,
) -> RouteReservationAllocation:
    """Minimize the finite route-local separable reservation potential.

    The implementation exposes one non-decreasing marginal sequence per route
    and selects the globally smallest next sequence element.  The result is
    therefore an exact integer minimizer for the route-local potential.  It is
    not a solver for arbitrary shared-link route coupling.
    """

    candidate_values = tuple(candidates)
    if not candidate_values:
        raise ValueError("candidates must not be empty")
    if not all(
        isinstance(item, RouteReservationCandidate) for item in candidate_values
    ):
        raise TypeError("candidates must contain RouteReservationCandidate values")
    canonical = tuple(sorted(candidate_values, key=lambda item: item.candidate_id))
    candidate_ids = tuple(item.candidate_id for item in canonical)
    if len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError("candidate IDs must be unique")

    demand = _require_nonnegative_integer(demand_count, name="demand_count")
    strength = _require_finite_float(
        reservation_strength,
        name="reservation_strength",
    )
    if strength < 0.0:
        raise ValueError("reservation_strength must be >= 0")

    counts = [0] * len(canonical)
    heap = [
        (item.base_disutility, item.candidate_id, index)
        for index, item in enumerate(canonical)
    ]
    heapify(heap)

    for _ in range(demand):
        _marginal, _candidate_id, index = heappop(heap)
        counts[index] += 1
        candidate = canonical[index]
        next_marginal = (
            candidate.base_disutility
            + strength * counts[index] / candidate.effective_capacity
        )
        if not math.isfinite(next_marginal):
            raise OverflowError("next marginal disutility became non-finite")
        heappush(heap, (next_marginal, candidate.candidate_id, index))

    assigned_counts = tuple(counts)
    next_marginals = tuple(
        item.base_disutility
        + strength * count / item.effective_capacity
        for item, count in zip(canonical, assigned_counts, strict=True)
    )
    potential_value = sum(
        item.base_disutility * count
        + strength
        * count
        * (count - 1)
        / (2.0 * item.effective_capacity)
        for item, count in zip(canonical, assigned_counts, strict=True)
    )
    if not math.isfinite(potential_value) or not all(
        math.isfinite(value) for value in next_marginals
    ):
        raise OverflowError("route-local reservation result became non-finite")

    return RouteReservationAllocation(
        candidate_ids=candidate_ids,
        base_disutilities=tuple(item.base_disutility for item in canonical),
        effective_capacities=tuple(item.effective_capacity for item in canonical),
        assigned_counts=assigned_counts,
        next_marginal_disutilities=next_marginals,
        demand_count=demand,
        reservation_strength=strength,
        potential_value=potential_value,
    )


def _require_nonnegative_integer(value: object, *, name: str) -> int:
    if isinstance(value, bool):
        raise TypeError(f"{name} must be an integer, not bool")
    try:
        integer = operator.index(value)
    except TypeError as exc:
        raise TypeError(f"{name} must be an integer") from exc
    if integer < 0:
        raise ValueError(f"{name} must be >= 0")
    return int(integer)


def _require_finite_float(value: object, *, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{name} must be a real number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def _fingerprint_payload(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
