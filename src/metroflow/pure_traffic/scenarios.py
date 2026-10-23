"""Small deterministic road networks used by the pure-Python CTM research lane."""

from __future__ import annotations

from dataclasses import dataclass, replace
import random
from typing import Literal

from metroflow.pure_traffic.ctm import (
    CTMConfig,
    CTMState,
    Incident,
    LinkSpec,
    MovementSpec,
    NetworkSpec,
    VehicleRequest,
    initialize_state,
)

__all__ = [
    "CTMScenario",
    "build_diamond_bottleneck_scenario",
    "build_priority_diverge_scenario",
    "build_weighted_merge_scenario",
]

NodePolicy = Literal["lexicographic", "weighted_fair"]
FIFOMode = Literal["strict", "movement"]


@dataclass(frozen=True, slots=True)
class CTMScenario:
    name: str
    network: NetworkSpec
    requests: tuple[VehicleRequest, ...]
    config: CTMConfig
    incidents: tuple[Incident, ...]
    initial_state: CTMState | None = None


def _preload_requests_at_first_link_exits(
    network: NetworkSpec,
    requests: tuple[VehicleRequest, ...],
    config: CTMConfig,
) -> CTMState:
    """Create a controlled queue initial condition for node-solver experiments."""

    state = initialize_state(network, requests, config)
    link_index = {link.link_id: index for index, link in enumerate(network.links)}
    cells = [[list(cell) for cell in link_cells] for link_cells in state.cells]
    admitted_ticks = [0] * len(requests)
    source_admissions = [0] * len(network.links)
    for request in requests:
        link_id = link_index[request.route[0]]
        cells[link_id][-1].append(request.vehicle_id)
        source_admissions[link_id] += 1
    return replace(
        state,
        cells=tuple(tuple(tuple(cell) for cell in link_cells) for link_cells in cells),
        admitted_ticks=tuple(admitted_ticks),
        released_count=len(requests),
        cumulative_source_admissions=tuple(source_admissions),
    )


def build_diamond_bottleneck_scenario(
    *,
    seed: int = 20261023,
    vehicles: int = 120,
    release_batch: int = 2,
    node_policy: NodePolicy = "weighted_fair",
    fifo_mode: FIFOMode = "movement",
    movement_age_priority: bool = True,
) -> CTMScenario:
    """Return a split-route urban corridor with a temporary upper-branch incident.

    Vehicles share an upstream approach, split over a short upper and longer lower
    route, merge into a capacity-limited downstream link, and then leave the network.
    The route sequence is deterministic but seed-dependent within each release tick.
    """

    if release_batch < 1:
        raise ValueError("release_batch must be positive")
    if vehicles < 0:
        raise ValueError("vehicles must be non-negative")

    network = NetworkSpec(
        links=(
            LinkSpec("in", "o", "s", 600.0, 2, 15.0, 5.0, 150.0, 1800.0),
            LinkSpec("upper_a", "s", "u", 450.0, 1, 15.0, 5.0, 150.0, 1200.0),
            LinkSpec("upper_b", "u", "m", 450.0, 1, 15.0, 5.0, 150.0, 1200.0),
            LinkSpec("lower_a", "s", "l", 600.0, 1, 15.0, 5.0, 150.0, 1100.0),
            LinkSpec("lower_b", "l", "m", 600.0, 1, 15.0, 5.0, 150.0, 1100.0),
            LinkSpec("out", "m", "d", 600.0, 1, 15.0, 5.0, 150.0, 720.0),
        ),
        movements=(
            MovementSpec("in", "upper_a", 1800.0),
            MovementSpec("in", "lower_a", 1800.0),
            MovementSpec("upper_a", "upper_b", 1200.0),
            MovementSpec("upper_b", "out", 1800.0),
            MovementSpec("lower_a", "lower_b", 1100.0),
            MovementSpec("lower_b", "out", 1800.0),
            MovementSpec("out", None, 720.0),
        ),
        coordinates={
            "o": (0.0, 0.0),
            "s": (1.0, 0.0),
            "u": (2.0, 0.75),
            "l": (2.0, -0.75),
            "m": (3.0, 0.0),
            "d": (4.0, 0.0),
        },
    )
    requests: list[VehicleRequest] = []
    for vehicle_id in range(vehicles):
        release_tick = vehicle_id // release_batch
        # Every consecutive pair is balanced across the two routes; seeded order
        # exposes strict-FIFO blocking without changing total route demand.
        pair_id = vehicle_id // 2
        pair_offset = vehicle_id % 2
        upper_first = random.Random(seed + pair_id).random() < 0.5
        upper = pair_offset == (0 if upper_first else 1)
        route = (
            ("in", "upper_a", "upper_b", "out")
            if upper
            else ("in", "lower_a", "lower_b", "out")
        )
        requests.append(VehicleRequest(vehicle_id, release_tick, route))
    return CTMScenario(
        name="diamond_bottleneck",
        network=network,
        requests=tuple(requests),
        config=CTMConfig(
            tick_seconds=10.0,
            node_policy=node_policy,
            fifo_mode=fifo_mode,
            movement_age_priority=movement_age_priority,
        ),
        incidents=(
            Incident(
                link_id="upper_a",
                start_tick=18,
                end_tick=42,
                capacity_multiplier=0.12,
                speed_multiplier=0.45,
            ),
        ),
    )


def build_weighted_merge_scenario(
    *,
    vehicles_per_approach: int = 30,
    node_policy: NodePolicy = "weighted_fair",
) -> CTMScenario:
    """Return a saturated 2:1 priority merge with a preloaded queue."""

    network = NetworkSpec(
        links=(
            LinkSpec(
                "a",
                "oa",
                "m",
                150.0,
                2,
                15.0,
                5.0,
                200.0,
                1800.0,
                priority_weight=2.0,
            ),
            LinkSpec(
                "b",
                "ob",
                "m",
                150.0,
                2,
                15.0,
                5.0,
                200.0,
                1800.0,
                priority_weight=1.0,
            ),
            LinkSpec("out", "m", "d", 450.0, 1, 15.0, 5.0, 200.0, 1080.0),
        ),
        movements=(
            MovementSpec("a", "out", 3600.0),
            MovementSpec("b", "out", 3600.0),
            MovementSpec("out", None, 1080.0),
        ),
        coordinates={
            "oa": (0.0, 0.65),
            "ob": (0.0, -0.65),
            "m": (1.0, 0.0),
            "d": (2.2, 0.0),
        },
    )
    requests: list[VehicleRequest] = []
    for offset in range(vehicles_per_approach):
        requests.append(VehicleRequest(len(requests), 0, ("a", "out")))
        requests.append(VehicleRequest(len(requests), 0, ("b", "out")))
    config = CTMConfig(
        tick_seconds=10.0,
        node_policy=node_policy,
        fifo_mode="movement",
        movement_age_priority=False,
    )
    request_tuple = tuple(requests)
    return CTMScenario(
        name="weighted_merge",
        network=network,
        requests=request_tuple,
        config=config,
        incidents=(),
        initial_state=_preload_requests_at_first_link_exits(
            network,
            request_tuple,
            config,
        ),
    )


def build_priority_diverge_scenario(
    *,
    vehicles_per_turn: int = 20,
    movement_age_priority: bool = True,
) -> CTMScenario:
    """Return a shared approach where movement priority can starve one turn."""

    network = NetworkSpec(
        links=(
            LinkSpec("approach", "o", "j", 150.0, 2, 15.0, 5.0, 200.0, 180.0),
            LinkSpec("major", "j", "h", 300.0, 1, 15.0, 5.0, 200.0, 1800.0),
            LinkSpec("minor", "j", "l", 300.0, 1, 15.0, 5.0, 200.0, 1800.0),
        ),
        movements=(
            MovementSpec("approach", "major", 1800.0, priority_weight=4.0),
            MovementSpec("approach", "minor", 1800.0, priority_weight=1.0),
            MovementSpec("major", None, 1800.0),
            MovementSpec("minor", None, 1800.0),
        ),
        coordinates={
            "o": (0.0, 0.0),
            "j": (1.0, 0.0),
            "h": (2.0, 0.65),
            "l": (2.0, -0.65),
        },
    )
    requests: list[VehicleRequest] = []
    for _ in range(vehicles_per_turn):
        requests.append(VehicleRequest(len(requests), 0, ("approach", "major")))
        requests.append(VehicleRequest(len(requests), 0, ("approach", "minor")))
    config = CTMConfig(
        tick_seconds=10.0,
        node_policy="weighted_fair",
        fifo_mode="movement",
        movement_age_priority=movement_age_priority,
    )
    request_tuple = tuple(requests)
    return CTMScenario(
        name="priority_diverge",
        network=network,
        requests=request_tuple,
        config=config,
        incidents=(),
        initial_state=_preload_requests_at_first_link_exits(
            network,
            request_tuple,
            config,
        ),
    )
