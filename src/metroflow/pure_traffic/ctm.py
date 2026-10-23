"""Pure-Python multi-commodity Cell Transmission Model research lane.

The module is intentionally self-contained and accelerator-free.  It couples a
triangular-fundamental-diagram CTM link model to a deterministic integer node
solver.  Vehicles remain discrete identities, link cells provide finite storage
and backward spillback, and all moves are committed simultaneously.

This is an opt-in research implementation.  It does not replace MetroFlow's
existing NumPy authoritative runtime.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from hashlib import sha256
import json
import math
from types import MappingProxyType
from typing import Literal, Mapping, Sequence

__all__ = [
    "CTMConfig",
    "CTMState",
    "Incident",
    "LinkSpec",
    "MovementSpec",
    "NetworkSpec",
    "SimulationResult",
    "SimulationSnapshot",
    "VehicleRequest",
    "initialize_state",
    "simulate",
    "step",
]

_EPS = 1.0e-9
NodePolicy = Literal["lexicographic", "weighted_fair"]
FIFOMode = Literal["strict", "movement"]
MovementKey = tuple[str, str | None]


@dataclass(frozen=True, slots=True)
class CTMConfig:
    tick_seconds: float = 10.0
    node_policy: NodePolicy = "weighted_fair"
    fifo_mode: FIFOMode = "movement"
    movement_age_priority: bool = True
    forced_cell_count_by_link: Mapping[str, int] = field(default_factory=dict)
    virtual_finish_cost_scale: int = 1_000
    waiting_cost_scale: int = 24

    def __post_init__(self) -> None:
        if not math.isfinite(self.tick_seconds) or self.tick_seconds <= 0.0:
            raise ValueError("tick_seconds must be finite and positive")
        if self.node_policy not in {"lexicographic", "weighted_fair"}:
            raise ValueError("node_policy must be lexicographic or weighted_fair")
        if self.fifo_mode not in {"strict", "movement"}:
            raise ValueError("fifo_mode must be strict or movement")
        if self.virtual_finish_cost_scale <= 0 or self.waiting_cost_scale < 0:
            raise ValueError("cost scales must be non-negative and virtual scale positive")
        cleaned: dict[str, int] = {}
        for link_id, count in dict(self.forced_cell_count_by_link).items():
            if not isinstance(count, int) or isinstance(count, bool) or count < 1:
                raise ValueError("forced cell counts must be positive integers")
            cleaned[str(link_id)] = count
        object.__setattr__(self, "forced_cell_count_by_link", MappingProxyType(cleaned))


@dataclass(frozen=True, slots=True)
class LinkSpec:
    link_id: str
    tail: str
    head: str
    length_m: float
    lanes: int
    free_speed_mps: float
    wave_speed_mps: float
    jam_density_veh_per_km_lane: float
    capacity_veh_per_hour_lane: float
    priority_weight: float = 1.0

    def __post_init__(self) -> None:
        if not self.link_id or not self.tail or not self.head:
            raise ValueError("link_id, tail, and head must be non-empty")
        if self.tail == self.head:
            raise ValueError("link tail and head must differ")
        for name, value in (
            ("length_m", self.length_m),
            ("free_speed_mps", self.free_speed_mps),
            ("wave_speed_mps", self.wave_speed_mps),
            ("jam_density_veh_per_km_lane", self.jam_density_veh_per_km_lane),
            ("capacity_veh_per_hour_lane", self.capacity_veh_per_hour_lane),
            ("priority_weight", self.priority_weight),
        ):
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive")
        if not isinstance(self.lanes, int) or isinstance(self.lanes, bool) or self.lanes < 1:
            raise ValueError("lanes must be a positive integer")


@dataclass(frozen=True, slots=True)
class MovementSpec:
    from_link: str
    to_link: str | None
    capacity_veh_per_hour: float
    priority_weight: float = 1.0
    green_cycle: tuple[bool, ...] = ()

    def __post_init__(self) -> None:
        if not self.from_link:
            raise ValueError("from_link must be non-empty")
        if self.to_link == self.from_link:
            raise ValueError("movement must change link or terminate at a sink")
        if not math.isfinite(self.capacity_veh_per_hour) or self.capacity_veh_per_hour <= 0.0:
            raise ValueError("movement capacity must be finite and positive")
        if not math.isfinite(self.priority_weight) or self.priority_weight <= 0.0:
            raise ValueError("movement priority_weight must be finite and positive")
        object.__setattr__(self, "green_cycle", tuple(bool(value) for value in self.green_cycle))

    def is_green(self, tick: int) -> bool:
        return not self.green_cycle or self.green_cycle[tick % len(self.green_cycle)]


@dataclass(frozen=True, slots=True)
class Incident:
    link_id: str
    start_tick: int
    end_tick: int
    capacity_multiplier: float = 1.0
    speed_multiplier: float = 1.0

    def __post_init__(self) -> None:
        if self.start_tick < 0 or self.end_tick <= self.start_tick:
            raise ValueError("incident tick interval must satisfy 0 <= start < end")
        for name, value in (
            ("capacity_multiplier", self.capacity_multiplier),
            ("speed_multiplier", self.speed_multiplier),
        ):
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be finite and in [0, 1]")

    def active(self, tick: int) -> bool:
        return self.start_tick <= tick < self.end_tick


@dataclass(frozen=True, slots=True)
class NetworkSpec:
    links: tuple[LinkSpec, ...]
    movements: tuple[MovementSpec, ...]
    coordinates: Mapping[str, tuple[float, float]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        links = tuple(self.links)
        movements = tuple(self.movements)
        if not links:
            raise ValueError("network must contain at least one link")
        link_ids = [link.link_id for link in links]
        if len(link_ids) != len(set(link_ids)):
            raise ValueError("link ids must be unique")
        link_by_id = {link.link_id: link for link in links}
        movement_keys: set[MovementKey] = set()
        for movement in movements:
            if movement.from_link not in link_by_id:
                raise ValueError(f"unknown movement source link {movement.from_link}")
            if movement.to_link is not None:
                if movement.to_link not in link_by_id:
                    raise ValueError(f"unknown movement destination link {movement.to_link}")
                source = link_by_id[movement.from_link]
                target = link_by_id[movement.to_link]
                if source.head != target.tail:
                    raise ValueError(
                        f"movement {movement.from_link}->{movement.to_link} is not topologically contiguous"
                    )
            key = (movement.from_link, movement.to_link)
            if key in movement_keys:
                raise ValueError(f"duplicate movement {key}")
            movement_keys.add(key)
        coords: dict[str, tuple[float, float]] = {}
        for node, pair in dict(self.coordinates).items():
            if len(pair) != 2 or not all(math.isfinite(float(value)) for value in pair):
                raise ValueError("coordinates must be finite (x, y) pairs")
            coords[str(node)] = (float(pair[0]), float(pair[1]))
        object.__setattr__(self, "links", links)
        object.__setattr__(self, "movements", movements)
        object.__setattr__(self, "coordinates", MappingProxyType(coords))


@dataclass(frozen=True, slots=True)
class VehicleRequest:
    vehicle_id: int
    release_tick: int
    route: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.vehicle_id, int) or isinstance(self.vehicle_id, bool):
            raise TypeError("vehicle_id must be an integer")
        if self.vehicle_id < 0 or self.release_tick < 0:
            raise ValueError("vehicle_id and release_tick must be non-negative")
        route = tuple(str(link_id) for link_id in self.route)
        if not route:
            raise ValueError("vehicle route must contain at least one link")
        object.__setattr__(self, "route", route)


@dataclass(frozen=True, slots=True)
class _LinkGeometry:
    cell_count: int
    cell_length_m: float
    jam_storage_veh: int
    capacity_veh_per_tick: float
    free_cfl: float
    wave_cfl: float


@dataclass(frozen=True, slots=True)
class CTMState:
    tick: int
    cells: tuple[tuple[tuple[int, ...], ...], ...]
    pending_by_link: tuple[tuple[int, ...], ...]
    route_positions: tuple[int, ...]
    admitted_ticks: tuple[int | None, ...]
    completed_ticks: tuple[int | None, ...]
    internal_residuals: tuple[tuple[float, ...], ...]
    entry_residuals: tuple[float, ...]
    exit_residuals: tuple[float, ...]
    movement_residuals: tuple[float, ...]
    virtual_finish_by_link: tuple[float, ...]
    movement_wait_ticks: tuple[int, ...]
    cumulative_movement_flow_tokens: tuple[int, ...]
    cumulative_source_admissions: tuple[int, ...]
    cumulative_sink_completions: tuple[int, ...]
    released_count: int
    mass_balance_error: int
    node_holding_events: int

    @property
    def active_count(self) -> int:
        return sum(len(cell) for link_cells in self.cells for cell in link_cells)

    @property
    def pending_count(self) -> int:
        return sum(len(queue) for queue in self.pending_by_link)

    @property
    def completed_count(self) -> int:
        return sum(value is not None for value in self.completed_ticks)


@dataclass(frozen=True, slots=True)
class SimulationSnapshot:
    tick: int
    released_count: int
    pending_count: int
    active_count: int
    completed_count: int
    link_occupancy_ratio: Mapping[str, float]
    link_cell_occupancy_ratio: Mapping[str, tuple[float, ...]]
    link_exit_queue: Mapping[str, int]
    cumulative_movement_flow: Mapping[MovementKey, int]
    cumulative_source_admissions: Mapping[str, int]
    cumulative_sink_completions: Mapping[str, int]
    mass_balance_error: int
    node_holding_events: int


@dataclass(frozen=True, slots=True)
class SimulationResult:
    final_state: CTMState
    snapshots: tuple[SimulationSnapshot, ...]
    fingerprint: str
    completed_travel_times_s: tuple[float, ...]
    cumulative_movement_flow: Mapping[MovementKey, int]
    node_holding_events: int


@dataclass(slots=True)
class _FlowEdge:
    to: int
    rev: int
    capacity: int


@dataclass(frozen=True, slots=True)
class _NodeAllocation:
    flow_by_movement: Mapping[int, int]
    service_sequence: tuple[int, ...]
    served_by_incoming: Mapping[int, int]
    holding_event: bool


def _network_indices(network: NetworkSpec) -> tuple[
    dict[str, int],
    dict[MovementKey, int],
    dict[str, tuple[int, ...]],
]:
    link_index = {link.link_id: index for index, link in enumerate(network.links)}
    movement_index = {
        (movement.from_link, movement.to_link): index
        for index, movement in enumerate(network.movements)
    }
    movements_by_node: dict[str, list[int]] = {}
    for index, movement in enumerate(network.movements):
        node = network.links[link_index[movement.from_link]].head
        movements_by_node.setdefault(node, []).append(index)
    return (
        link_index,
        movement_index,
        {node: tuple(indices) for node, indices in movements_by_node.items()},
    )


def _derive_geometry(link: LinkSpec, config: CTMConfig) -> _LinkGeometry:
    forced = config.forced_cell_count_by_link.get(link.link_id)
    if forced is None:
        ratio = link.length_m / (link.free_speed_mps * config.tick_seconds)
        cell_count = max(1, int(math.floor(ratio + _EPS)))
    else:
        cell_count = forced
    cell_length = link.length_m / cell_count
    free_cfl = link.free_speed_mps * config.tick_seconds / cell_length
    wave_cfl = link.wave_speed_mps * config.tick_seconds / cell_length
    if free_cfl > 1.0 + 1.0e-9 or wave_cfl > 1.0 + 1.0e-9:
        raise ValueError(
            f"CFL violation for link {link.link_id}: "
            f"v*dt/dx={free_cfl:.6g}, w*dt/dx={wave_cfl:.6g}"
        )
    jam_storage = max(
        1,
        int(
            math.floor(
                link.jam_density_veh_per_km_lane
                * link.lanes
                * cell_length
                / 1_000.0
                + _EPS
            )
        ),
    )
    capacity_tick = (
        link.capacity_veh_per_hour_lane * link.lanes * config.tick_seconds / 3_600.0
    )
    jam_density_veh_per_m = link.jam_density_veh_per_km_lane / 1_000.0
    triangular_capacity_vph_lane = (
        link.free_speed_mps
        * link.wave_speed_mps
        / (link.free_speed_mps + link.wave_speed_mps)
        * jam_density_veh_per_m
        * 3_600.0
    )
    if link.capacity_veh_per_hour_lane > triangular_capacity_vph_lane + 1.0e-6:
        raise ValueError(
            f"link {link.link_id} capacity exceeds its triangular-FD maximum "
            f"({link.capacity_veh_per_hour_lane:.6g} > {triangular_capacity_vph_lane:.6g})"
        )
    return _LinkGeometry(
        cell_count=cell_count,
        cell_length_m=cell_length,
        jam_storage_veh=jam_storage,
        capacity_veh_per_tick=capacity_tick,
        free_cfl=free_cfl,
        wave_cfl=wave_cfl,
    )


def _validate_requests(
    network: NetworkSpec,
    requests: Sequence[VehicleRequest],
    link_index: Mapping[str, int],
    movement_index: Mapping[MovementKey, int],
) -> tuple[VehicleRequest, ...]:
    ordered = tuple(sorted(requests, key=lambda request: request.vehicle_id))
    expected = tuple(range(len(ordered)))
    actual = tuple(request.vehicle_id for request in ordered)
    if actual != expected:
        raise ValueError("vehicle ids must be contiguous integers starting at zero")
    for request in ordered:
        for link_id in request.route:
            if link_id not in link_index:
                raise ValueError(
                    f"vehicle {request.vehicle_id} references unknown link {link_id}"
                )
        for source, target in zip(request.route, request.route[1:], strict=False):
            if (source, target) not in movement_index:
                raise ValueError(
                    f"vehicle {request.vehicle_id} route contains illegal movement "
                    f"{source}->{target}"
                )
        if (request.route[-1], None) not in movement_index:
            raise ValueError(
                f"vehicle {request.vehicle_id} final link {request.route[-1]} "
                "has no sink movement"
            )
    return ordered


def initialize_state(
    network: NetworkSpec,
    requests: Sequence[VehicleRequest],
    config: CTMConfig | None = None,
) -> CTMState:
    cfg = config or CTMConfig()
    link_index, movement_index, _ = _network_indices(network)
    ordered_requests = _validate_requests(network, requests, link_index, movement_index)
    geometries = tuple(_derive_geometry(link, cfg) for link in network.links)
    state = CTMState(
        tick=0,
        cells=tuple(
            tuple(() for _ in range(geometry.cell_count)) for geometry in geometries
        ),
        pending_by_link=tuple(() for _ in network.links),
        route_positions=tuple(0 for _ in ordered_requests),
        admitted_ticks=tuple(None for _ in ordered_requests),
        completed_ticks=tuple(None for _ in ordered_requests),
        internal_residuals=tuple(
            tuple(0.0 for _ in range(max(0, geometry.cell_count - 1)))
            for geometry in geometries
        ),
        entry_residuals=tuple(0.0 for _ in network.links),
        exit_residuals=tuple(0.0 for _ in network.links),
        movement_residuals=tuple(0.0 for _ in network.movements),
        virtual_finish_by_link=tuple(0.0 for _ in network.links),
        movement_wait_ticks=tuple(0 for _ in network.movements),
        cumulative_movement_flow_tokens=tuple(0 for _ in network.movements),
        cumulative_source_admissions=tuple(0 for _ in network.links),
        cumulative_sink_completions=tuple(0 for _ in network.links),
        released_count=0,
        mass_balance_error=0,
        node_holding_events=0,
    )
    _validate_state(network, ordered_requests, cfg, state, geometries)
    return state


def _incident_multipliers(
    link_id: str,
    tick: int,
    incidents: Sequence[Incident],
) -> tuple[float, float]:
    capacity = 1.0
    speed = 1.0
    for incident in incidents:
        if incident.link_id == link_id and incident.active(tick):
            capacity *= incident.capacity_multiplier
            speed *= incident.speed_multiplier
    return capacity, speed


def _quantize_target(target: float, residual: float) -> tuple[int, float]:
    if target <= 0.0:
        return 0, residual
    total = target + residual
    tokens = int(math.floor(total + 1.0e-12))
    next_residual = total - tokens
    if not -_EPS <= next_residual < 1.0 + _EPS:
        raise RuntimeError("flow residual escaped [0, 1)")
    return tokens, min(max(next_residual, 0.0), math.nextafter(1.0, 0.0))


def _quantize_capacity(
    raw_capacity: float,
    residual: float,
    *,
    active: bool,
) -> tuple[int, float]:
    """Quantize only the fractional rate; unused integer capacity is never banked."""

    if not active or raw_capacity <= 0.0:
        return 0, residual
    integer = int(math.floor(raw_capacity + _EPS))
    fraction = raw_capacity - integer
    total_fraction = residual + fraction
    carry = int(math.floor(total_fraction + 1.0e-12))
    next_residual = total_fraction - carry
    return integer + carry, min(
        max(next_residual, 0.0),
        math.nextafter(1.0, 0.0),
    )


def _movement_for_vehicle(
    request: VehicleRequest,
    route_position: int,
) -> MovementKey:
    current = request.route[route_position]
    if route_position == len(request.route) - 1:
        return current, None
    return current, request.route[route_position + 1]


def _strict_fifo_demands(
    exit_cell: Sequence[int],
    requests: Sequence[VehicleRequest],
    route_positions: Sequence[int],
    movement_index: Mapping[MovementKey, int],
) -> dict[int, list[int]]:
    if not exit_cell:
        return {}
    first_vehicle = exit_cell[0]
    first_key = _movement_for_vehicle(
        requests[first_vehicle],
        route_positions[first_vehicle],
    )
    first_movement = movement_index[first_key]
    vehicles: list[int] = []
    for vehicle_id in exit_cell:
        key = _movement_for_vehicle(
            requests[vehicle_id],
            route_positions[vehicle_id],
        )
        if movement_index[key] != first_movement:
            break
        vehicles.append(vehicle_id)
    return {first_movement: vehicles}


def _movement_fifo_demands(
    exit_cell: Sequence[int],
    requests: Sequence[VehicleRequest],
    route_positions: Sequence[int],
    movement_index: Mapping[MovementKey, int],
) -> dict[int, list[int]]:
    buckets: dict[int, list[int]] = {}
    for vehicle_id in exit_cell:
        key = _movement_for_vehicle(
            requests[vehicle_id],
            route_positions[vehicle_id],
        )
        buckets.setdefault(movement_index[key], []).append(vehicle_id)
    return buckets


def _add_flow_edge(
    graph: list[list[_FlowEdge]],
    source: int,
    target: int,
    capacity: int,
) -> None:
    forward_index = len(graph[source])
    reverse_index = len(graph[target])
    graph[source].append(_FlowEdge(target, reverse_index, capacity))
    graph[target].append(_FlowEdge(source, forward_index, 0))


def _max_bipartite_flow_value(
    incoming_capacity: Mapping[int, int],
    outgoing_capacity: Mapping[str | None, int],
    movement_capacity: Mapping[int, int],
    movement_source: Mapping[int, int],
    movement_target: Mapping[int, str | None],
) -> int:
    """Return the exact integer maximum throughput of one node.

    This is a small deterministic Dinic solve over a bipartite node graph.  It
    separates the primary holding-free objective (maximum feasible throughput)
    from the secondary fairness policy used to choose among maximum-flow tokens.
    """

    incoming = tuple(
        sorted(link_id for link_id, cap in incoming_capacity.items() if cap > 0)
    )
    outgoing = tuple(
        sorted(
            (key for key, cap in outgoing_capacity.items() if cap > 0),
            key=lambda key: (key is None, "" if key is None else key),
        )
    )
    active_movements = tuple(
        sorted(
            movement_id
            for movement_id, cap in movement_capacity.items()
            if cap > 0
            and incoming_capacity.get(movement_source[movement_id], 0) > 0
            and outgoing_capacity.get(movement_target[movement_id], 0) > 0
        )
    )
    if not incoming or not outgoing or not active_movements:
        return 0

    source = 0
    incoming_node = {
        link_id: 1 + position for position, link_id in enumerate(incoming)
    }
    outgoing_offset = 1 + len(incoming)
    outgoing_node = {
        key: outgoing_offset + position for position, key in enumerate(outgoing)
    }
    sink = outgoing_offset + len(outgoing)
    graph: list[list[_FlowEdge]] = [[] for _ in range(sink + 1)]

    for link_id in incoming:
        _add_flow_edge(
            graph,
            source,
            incoming_node[link_id],
            int(incoming_capacity[link_id]),
        )
    for movement_id in active_movements:
        _add_flow_edge(
            graph,
            incoming_node[movement_source[movement_id]],
            outgoing_node[movement_target[movement_id]],
            int(movement_capacity[movement_id]),
        )
    for key in outgoing:
        _add_flow_edge(
            graph,
            outgoing_node[key],
            sink,
            int(outgoing_capacity[key]),
        )

    total = 0
    while True:
        level = [-1] * len(graph)
        level[source] = 0
        queue: deque[int] = deque([source])
        while queue:
            u = queue.popleft()
            for edge in graph[u]:
                if edge.capacity > 0 and level[edge.to] < 0:
                    level[edge.to] = level[u] + 1
                    queue.append(edge.to)
        if level[sink] < 0:
            return total

        next_edge = [0] * len(graph)

        def send(u: int, amount: int) -> int:
            if u == sink:
                return amount
            while next_edge[u] < len(graph[u]):
                edge_index = next_edge[u]
                edge = graph[u][edge_index]
                if edge.capacity > 0 and level[edge.to] == level[u] + 1:
                    pushed = send(edge.to, min(amount, edge.capacity))
                    if pushed:
                        edge.capacity -= pushed
                        graph[edge.to][edge.rev].capacity += pushed
                        return pushed
                next_edge[u] += 1
            return 0

        while True:
            pushed = send(source, 1 << 60)
            if not pushed:
                break
            total += pushed


def _allocation_rank(
    *,
    network: NetworkSpec,
    config: CTMConfig,
    movement_id: int,
    source_link: int,
    served_by_incoming: Mapping[int, int],
    virtual_finish: Sequence[float],
    movement_wait: Sequence[int],
) -> tuple[float, int, float, int]:
    movement = network.movements[movement_id]
    if config.node_policy == "weighted_fair":
        fairness = virtual_finish[source_link] + (
            served_by_incoming.get(source_link, 0) + 1
        ) / network.links[source_link].priority_weight
    else:
        fairness = float(source_link)
    age_rank = -movement_wait[movement_id] if config.movement_age_priority else 0
    return (
        fairness,
        age_rank,
        -movement.priority_weight,
        movement_id,
    )


def _allocate_node(
    network: NetworkSpec,
    config: CTMConfig,
    node_movement_indices: Sequence[int],
    link_index: Mapping[str, int],
    movement_demands: Mapping[int, int],
    movement_caps: Mapping[int, int],
    sending_tokens: Mapping[int, int],
    receiving_tokens: Mapping[int, int],
    virtual_finish: Sequence[float],
    movement_wait: Sequence[int],
) -> _NodeAllocation:
    movement_source: dict[int, int] = {}
    movement_target: dict[int, str | None] = {}
    remaining_movement: dict[int, int] = {}
    remaining_incoming: dict[int, int] = {}
    remaining_outgoing: dict[str | None, int] = {}

    for movement_id in node_movement_indices:
        movement = network.movements[movement_id]
        source_link = link_index[movement.from_link]
        target_key = movement.to_link
        movement_capacity = min(
            movement_demands.get(movement_id, 0),
            movement_caps.get(movement_id, 0),
        )
        source_capacity = sending_tokens.get(source_link, 0)
        if target_key is None:
            target_capacity = movement_capacity
        else:
            target_capacity = receiving_tokens.get(link_index[target_key], 0)
        if movement_capacity <= 0 or source_capacity <= 0 or target_capacity <= 0:
            continue
        movement_source[movement_id] = source_link
        movement_target[movement_id] = target_key
        remaining_movement[movement_id] = movement_capacity
        remaining_incoming[source_link] = source_capacity
        if target_key is None:
            remaining_outgoing[target_key] = (
                remaining_outgoing.get(target_key, 0) + movement_capacity
            )
        else:
            remaining_outgoing[target_key] = target_capacity

    if not remaining_movement:
        return _NodeAllocation({}, (), {}, False)

    remaining_max = _max_bipartite_flow_value(
        remaining_incoming,
        remaining_outgoing,
        remaining_movement,
        movement_source,
        movement_target,
    )
    flow_by_movement: dict[int, int] = {}
    served_by_incoming: dict[int, int] = {}
    service_sequence: list[int] = []

    while remaining_max > 0:
        candidates = [
            movement_id
            for movement_id in remaining_movement
            if remaining_movement[movement_id] > 0
            and remaining_incoming.get(movement_source[movement_id], 0) > 0
            and remaining_outgoing.get(movement_target[movement_id], 0) > 0
        ]
        candidates.sort(
            key=lambda movement_id: _allocation_rank(
                network=network,
                config=config,
                movement_id=movement_id,
                source_link=movement_source[movement_id],
                served_by_incoming=served_by_incoming,
                virtual_finish=virtual_finish,
                movement_wait=movement_wait,
            )
        )
        selected: int | None = None
        selected_remaining_max = -1
        for movement_id in candidates:
            source_link = movement_source[movement_id]
            target_key = movement_target[movement_id]
            remaining_movement[movement_id] -= 1
            remaining_incoming[source_link] -= 1
            remaining_outgoing[target_key] -= 1
            next_max = _max_bipartite_flow_value(
                remaining_incoming,
                remaining_outgoing,
                remaining_movement,
                movement_source,
                movement_target,
            )
            remaining_movement[movement_id] += 1
            remaining_incoming[source_link] += 1
            remaining_outgoing[target_key] += 1
            if next_max == remaining_max - 1:
                selected = movement_id
                selected_remaining_max = next_max
                break
        if selected is None:
            raise RuntimeError(
                "maximum-throughput node solver could not identify a safe token"
            )
        source_link = movement_source[selected]
        target_key = movement_target[selected]
        remaining_movement[selected] -= 1
        remaining_incoming[source_link] -= 1
        remaining_outgoing[target_key] -= 1
        flow_by_movement[selected] = flow_by_movement.get(selected, 0) + 1
        served_by_incoming[source_link] = (
            served_by_incoming.get(source_link, 0) + 1
        )
        service_sequence.append(selected)
        remaining_max = selected_remaining_max

    holding_event = (
        _max_bipartite_flow_value(
            remaining_incoming,
            remaining_outgoing,
            remaining_movement,
            movement_source,
            movement_target,
        )
        > 0
    )
    return _NodeAllocation(
        flow_by_movement=MappingProxyType(flow_by_movement),
        service_sequence=tuple(service_sequence),
        served_by_incoming=MappingProxyType(served_by_incoming),
        holding_event=holding_event,
    )


def _release_requests(
    network: NetworkSpec,
    requests: Sequence[VehicleRequest],
    state: CTMState,
    link_index: Mapping[str, int],
) -> tuple[list[list[int]], int]:
    pending = [list(queue) for queue in state.pending_by_link]
    present = set(vehicle_id for queue in pending for vehicle_id in queue)
    present.update(vehicle_id for link_cells in state.cells for cell in link_cells for vehicle_id in cell)
    present.update(
        vehicle_id
        for vehicle_id, tick in enumerate(state.completed_ticks)
        if tick is not None
    )
    released = state.released_count
    for request in requests:
        if request.release_tick <= state.tick and request.vehicle_id not in present:
            pending[link_index[request.route[0]]].append(request.vehicle_id)
            present.add(request.vehicle_id)
            released += 1
    return pending, released


def step(
    network: NetworkSpec,
    requests: Sequence[VehicleRequest],
    config: CTMConfig,
    state: CTMState,
    *,
    incidents: Sequence[Incident] = (),
) -> tuple[CTMState, SimulationSnapshot]:
    link_index, movement_index, movements_by_node = _network_indices(network)
    ordered_requests = _validate_requests(network, requests, link_index, movement_index)
    geometries = tuple(_derive_geometry(link, config) for link in network.links)
    _validate_state(network, ordered_requests, config, state, geometries)

    pending, released_count = _release_requests(network, ordered_requests, state, link_index)
    pre_cells = [[list(cell) for cell in link_cells] for link_cells in state.cells]
    internal_residuals = [list(values) for values in state.internal_residuals]
    entry_residuals = list(state.entry_residuals)
    exit_residuals = list(state.exit_residuals)
    movement_residuals = list(state.movement_residuals)
    virtual_finish = list(state.virtual_finish_by_link)
    movement_wait = list(state.movement_wait_ticks)
    cumulative_movement = list(state.cumulative_movement_flow_tokens)
    cumulative_source = list(state.cumulative_source_admissions)
    cumulative_sink = list(state.cumulative_sink_completions)

    effective_capacity: list[float] = []
    effective_free_cfl: list[float] = []
    for link, geometry in zip(network.links, geometries, strict=True):
        capacity_multiplier, speed_multiplier = _incident_multipliers(
            link.link_id, state.tick, incidents
        )
        effective_capacity.append(geometry.capacity_veh_per_tick * capacity_multiplier)
        effective_free_cfl.append(geometry.free_cfl * speed_multiplier)

    internal_moves: dict[tuple[int, int], list[int]] = {}
    for link_id, (link_cells, geometry) in enumerate(zip(pre_cells, geometries, strict=True)):
        for boundary in range(geometry.cell_count - 1):
            upstream = link_cells[boundary]
            downstream = link_cells[boundary + 1]
            sending = min(
                effective_free_cfl[link_id] * len(upstream),
                effective_capacity[link_id],
            )
            receiving = min(
                effective_capacity[link_id],
                geometry.wave_cfl * (geometry.jam_storage_veh - len(downstream)),
            )
            target = max(0.0, min(sending, receiving))
            tokens, next_residual = _quantize_target(
                target, internal_residuals[link_id][boundary]
            )
            tokens = min(tokens, len(upstream), geometry.jam_storage_veh - len(downstream))
            internal_residuals[link_id][boundary] = next_residual
            if tokens:
                internal_moves[(link_id, boundary)] = list(upstream[:tokens])

    demand_buckets: dict[int, dict[int, list[int]]] = {}
    movement_demands: dict[int, int] = {}
    exit_sending_tokens: dict[int, int] = {}
    for link_id, link_cells in enumerate(pre_cells):
        exit_cell = link_cells[-1]
        if config.fifo_mode == "strict":
            buckets = _strict_fifo_demands(
                exit_cell, ordered_requests, state.route_positions, movement_index
            )
        else:
            buckets = _movement_fifo_demands(
                exit_cell, ordered_requests, state.route_positions, movement_index
            )
        demand_buckets[link_id] = buckets
        for movement_id, vehicles in buckets.items():
            movement_demands[movement_id] = len(vehicles)
        raw_sending = min(
            effective_free_cfl[link_id] * len(exit_cell),
            effective_capacity[link_id],
        )
        tokens, next_residual = _quantize_target(raw_sending, exit_residuals[link_id])
        exit_residuals[link_id] = next_residual
        exit_sending_tokens[link_id] = min(tokens, len(exit_cell))

    incoming_demand_by_link = [0] * len(network.links)
    for movement_id, demand in movement_demands.items():
        target = network.movements[movement_id].to_link
        if target is not None:
            incoming_demand_by_link[link_index[target]] += demand
    entry_receiving_tokens: dict[int, int] = {}
    for link_id, (link_cells, geometry) in enumerate(zip(pre_cells, geometries, strict=True)):
        raw_receiving = min(
            effective_capacity[link_id],
            geometry.wave_cfl * (geometry.jam_storage_veh - len(link_cells[0])),
        )
        active = incoming_demand_by_link[link_id] > 0 or bool(pending[link_id])
        if active:
            tokens, next_residual = _quantize_target(raw_receiving, entry_residuals[link_id])
            entry_residuals[link_id] = next_residual
        else:
            tokens = 0
        entry_receiving_tokens[link_id] = min(
            tokens, geometry.jam_storage_veh - len(link_cells[0])
        )

    movement_caps: dict[int, int] = {}
    for movement_id, movement in enumerate(network.movements):
        source_link = link_index[movement.from_link]
        target_link = link_index[movement.to_link] if movement.to_link is not None else None
        active = (
            movement_demands.get(movement_id, 0) > 0
            and exit_sending_tokens.get(source_link, 0) > 0
            and movement.is_green(state.tick)
            and (
                target_link is None
                or entry_receiving_tokens.get(target_link, 0) > 0
            )
        )
        raw_capacity = movement.capacity_veh_per_hour * config.tick_seconds / 3_600.0
        tokens, next_residual = _quantize_capacity(
            raw_capacity,
            movement_residuals[movement_id],
            active=active,
        )
        movement_residuals[movement_id] = next_residual
        movement_caps[movement_id] = min(tokens, movement_demands.get(movement_id, 0))

    allocated_flow: dict[int, int] = {}
    service_sequence_by_node: dict[str, tuple[int, ...]] = {}
    used_receiving = [0] * len(network.links)
    holding_events = 0
    for node in sorted(movements_by_node):
        allocation = _allocate_node(
            network=network,
            config=config,
            node_movement_indices=movements_by_node[node],
            link_index=link_index,
            movement_demands=movement_demands,
            movement_caps=movement_caps,
            sending_tokens=exit_sending_tokens,
            receiving_tokens=entry_receiving_tokens,
            virtual_finish=virtual_finish,
            movement_wait=movement_wait,
        )
        allocated_flow.update(allocation.flow_by_movement)
        service_sequence_by_node[node] = allocation.service_sequence
        if allocation.holding_event:
            holding_events += 1
        active_incoming = sorted(
            {
                link_index[network.movements[index].from_link]
                for index in movements_by_node[node]
                if movement_demands.get(index, 0) > 0
            }
        )
        if config.node_policy == "weighted_fair" and active_incoming:
            for link_id in active_incoming:
                weight = network.links[link_id].priority_weight
                virtual_finish[link_id] += allocation.served_by_incoming.get(link_id, 0) / weight
            minimum = min(virtual_finish[link_id] for link_id in active_incoming)
            for link_id in active_incoming:
                virtual_finish[link_id] -= minimum
        for movement_id in movements_by_node[node]:
            demand = movement_demands.get(movement_id, 0)
            flow = allocation.flow_by_movement.get(movement_id, 0)
            if demand <= 0:
                movement_wait[movement_id] = 0
            elif flow > 0:
                movement_wait[movement_id] = max(0, movement_wait[movement_id] - 1)
            else:
                movement_wait[movement_id] += 1
            target = network.movements[movement_id].to_link
            if target is not None:
                used_receiving[link_index[target]] += flow

    remaining_entry_tokens = [
        max(0, entry_receiving_tokens.get(link_id, 0) - used_receiving[link_id])
        for link_id in range(len(network.links))
    ]
    admitted_by_link: dict[int, list[int]] = {}
    for link_id, queue in enumerate(pending):
        count = min(len(queue), remaining_entry_tokens[link_id])
        if count:
            admitted_by_link[link_id] = list(queue[:count])
            del queue[:count]

    next_cells = [[list(cell) for cell in link_cells] for link_cells in pre_cells]
    # Remove all departures from their pre-step cells first.
    for (link_id, boundary), vehicles in internal_moves.items():
        count = len(vehicles)
        if next_cells[link_id][boundary][:count] != vehicles:
            raise RuntimeError("internal CTM FIFO selection drifted before commit")
        del next_cells[link_id][boundary][:count]

    selected_by_movement: dict[int, list[int]] = {index: [] for index in allocated_flow}
    for node, sequence in service_sequence_by_node.items():
        mutable_buckets: dict[int, list[int]] = {}
        for movement_id in movements_by_node[node]:
            source_link = link_index[network.movements[movement_id].from_link]
            vehicles = demand_buckets.get(source_link, {}).get(movement_id, [])
            mutable_buckets[movement_id] = list(vehicles)
        for movement_id in sequence:
            bucket = mutable_buckets[movement_id]
            if not bucket:
                raise RuntimeError("node solver served a movement without a vehicle token")
            selected_by_movement.setdefault(movement_id, []).append(bucket.pop(0))

    removed_from_exit: dict[int, set[int]] = {}
    for movement_id, vehicle_ids in selected_by_movement.items():
        source_link = link_index[network.movements[movement_id].from_link]
        removed_from_exit.setdefault(source_link, set()).update(vehicle_ids)
    for source_link, removed in removed_from_exit.items():
        next_cells[source_link][-1] = [
            vehicle_id
            for vehicle_id in next_cells[source_link][-1]
            if vehicle_id not in removed
        ]

    # Add internal cell arrivals.  These vehicles were in the upstream cell at
    # the pre-step state, so they cannot cross a second boundary this tick.
    for (link_id, boundary), vehicles in sorted(internal_moves.items()):
        next_cells[link_id][boundary + 1].extend(vehicles)

    route_positions = list(state.route_positions)
    admitted_ticks = list(state.admitted_ticks)
    completed_ticks = list(state.completed_ticks)
    # Node arrival order follows the fair token service sequence, not movement id.
    for node in sorted(service_sequence_by_node):
        cursor_by_movement: dict[int, int] = {}
        for movement_id in service_sequence_by_node[node]:
            cursor = cursor_by_movement.get(movement_id, 0)
            vehicle_id = selected_by_movement[movement_id][cursor]
            cursor_by_movement[movement_id] = cursor + 1
            movement = network.movements[movement_id]
            source_link = link_index[movement.from_link]
            if movement.to_link is None:
                completed_ticks[vehicle_id] = state.tick + 1
                cumulative_sink[source_link] += 1
            else:
                target_link = link_index[movement.to_link]
                route_positions[vehicle_id] += 1
                next_cells[target_link][0].append(vehicle_id)
            cumulative_movement[movement_id] += 1

    for link_id, vehicle_ids in sorted(admitted_by_link.items()):
        for vehicle_id in vehicle_ids:
            if admitted_ticks[vehicle_id] is not None:
                raise RuntimeError("vehicle admitted twice")
            admitted_ticks[vehicle_id] = state.tick + 1
            next_cells[link_id][0].append(vehicle_id)
            cumulative_source[link_id] += 1

    next_state = CTMState(
        tick=state.tick + 1,
        cells=tuple(tuple(tuple(cell) for cell in link_cells) for link_cells in next_cells),
        pending_by_link=tuple(tuple(queue) for queue in pending),
        route_positions=tuple(route_positions),
        admitted_ticks=tuple(admitted_ticks),
        completed_ticks=tuple(completed_ticks),
        internal_residuals=tuple(tuple(values) for values in internal_residuals),
        entry_residuals=tuple(entry_residuals),
        exit_residuals=tuple(exit_residuals),
        movement_residuals=tuple(movement_residuals),
        virtual_finish_by_link=tuple(virtual_finish),
        movement_wait_ticks=tuple(movement_wait),
        cumulative_movement_flow_tokens=tuple(cumulative_movement),
        cumulative_source_admissions=tuple(cumulative_source),
        cumulative_sink_completions=tuple(cumulative_sink),
        released_count=released_count,
        mass_balance_error=0,
        node_holding_events=state.node_holding_events + holding_events,
    )
    mass_error = _mass_balance_error(next_state)
    if mass_error != 0:
        raise RuntimeError(
            "vehicle conservation failed during atomic CTM commit: "
            f"accounted-released={mass_error}"
        )
    _validate_state(network, ordered_requests, config, next_state, geometries)
    snapshot = _snapshot(network, geometries, next_state)
    return next_state, snapshot


def _mass_balance_error(state: CTMState) -> int:
    accounted = state.pending_count + state.active_count + state.completed_count
    return accounted - state.released_count


def _validate_state(
    network: NetworkSpec,
    requests: Sequence[VehicleRequest],
    config: CTMConfig,
    state: CTMState,
    geometries: Sequence[_LinkGeometry],
) -> None:
    if state.tick < 0:
        raise ValueError("state tick must be non-negative")
    if len(state.cells) != len(network.links) or len(state.pending_by_link) != len(network.links):
        raise ValueError("state link axis mismatch")
    if len(state.route_positions) != len(requests):
        raise ValueError("state vehicle axis mismatch")
    if len(state.movement_residuals) != len(network.movements):
        raise ValueError("state movement axis mismatch")
    all_locations: list[int] = []
    for link_id, (link_cells, geometry) in enumerate(zip(state.cells, geometries, strict=True)):
        if len(link_cells) != geometry.cell_count:
            raise ValueError("state cell count mismatch")
        actual_link_id = network.links[link_id].link_id
        for cell in link_cells:
            if len(cell) > geometry.jam_storage_veh:
                raise ValueError(
                    f"link {actual_link_id} exceeds finite cell storage"
                )
            for vehicle_id in cell:
                if not 0 <= vehicle_id < len(requests):
                    raise ValueError("state contains unknown vehicle identity")
                route_position = state.route_positions[vehicle_id]
                if not 0 <= route_position < len(requests[vehicle_id].route):
                    raise ValueError("vehicle route position is out of range")
                expected_link_id = requests[vehicle_id].route[route_position]
                if expected_link_id != actual_link_id:
                    raise ValueError(
                        "active vehicle is not on its current route link: "
                        f"vehicle={vehicle_id} expected={expected_link_id} "
                        f"actual={actual_link_id}"
                    )
            all_locations.extend(cell)
        for vehicle_id in state.pending_by_link[link_id]:
            if not 0 <= vehicle_id < len(requests):
                raise ValueError("state contains unknown vehicle identity")
            if state.route_positions[vehicle_id] != 0:
                raise ValueError("pending vehicle must remain at route position zero")
            if requests[vehicle_id].route[0] != actual_link_id:
                raise ValueError(
                    "pending vehicle is queued at the wrong source link: "
                    f"vehicle={vehicle_id} expected={requests[vehicle_id].route[0]} "
                    f"actual={actual_link_id}"
                )
        all_locations.extend(state.pending_by_link[link_id])
    completed_ids = [
        vehicle_id
        for vehicle_id, tick in enumerate(state.completed_ticks)
        if tick is not None
    ]
    all_locations.extend(completed_ids)
    if len(all_locations) != len(set(all_locations)):
        raise ValueError("vehicle identity appears in more than one state compartment")
    if any(not 0 <= vehicle_id < len(requests) for vehicle_id in all_locations):
        raise ValueError("state contains unknown vehicle identity")
    for vehicle_id in all_locations:
        position = state.route_positions[vehicle_id]
        if not 0 <= position < len(requests[vehicle_id].route):
            raise ValueError("vehicle route position is out of range")
    for residual_group in (
        state.entry_residuals,
        state.exit_residuals,
        state.movement_residuals,
    ):
        if any(not -_EPS <= value < 1.0 + _EPS for value in residual_group):
            raise ValueError("fractional residual escaped [0, 1)")
    for values in state.internal_residuals:
        if any(not -_EPS <= value < 1.0 + _EPS for value in values):
            raise ValueError("internal residual escaped [0, 1)")
    mass_error = _mass_balance_error(state)
    if mass_error != state.mass_balance_error or mass_error != 0:
        raise ValueError(
            f"vehicle conservation failed: accounted-released={mass_error}"
        )


def _snapshot(
    network: NetworkSpec,
    geometries: Sequence[_LinkGeometry],
    state: CTMState,
) -> SimulationSnapshot:
    link_occupancy: dict[str, float] = {}
    cell_occupancy: dict[str, tuple[float, ...]] = {}
    exit_queue: dict[str, int] = {}
    for link, geometry, link_cells in zip(
        network.links, geometries, state.cells, strict=True
    ):
        ratios = tuple(len(cell) / geometry.jam_storage_veh for cell in link_cells)
        cell_occupancy[link.link_id] = ratios
        link_occupancy[link.link_id] = sum(len(cell) for cell in link_cells) / (
            geometry.jam_storage_veh * geometry.cell_count
        )
        exit_queue[link.link_id] = len(link_cells[-1])
    movement_flow = {
        (movement.from_link, movement.to_link): state.cumulative_movement_flow_tokens[index]
        for index, movement in enumerate(network.movements)
    }
    source_admissions = {
        link.link_id: state.cumulative_source_admissions[index]
        for index, link in enumerate(network.links)
    }
    sink_completions = {
        link.link_id: state.cumulative_sink_completions[index]
        for index, link in enumerate(network.links)
    }
    return SimulationSnapshot(
        tick=state.tick,
        released_count=state.released_count,
        pending_count=state.pending_count,
        active_count=state.active_count,
        completed_count=state.completed_count,
        link_occupancy_ratio=MappingProxyType(link_occupancy),
        link_cell_occupancy_ratio=MappingProxyType(cell_occupancy),
        link_exit_queue=MappingProxyType(exit_queue),
        cumulative_movement_flow=MappingProxyType(movement_flow),
        cumulative_source_admissions=MappingProxyType(source_admissions),
        cumulative_sink_completions=MappingProxyType(sink_completions),
        mass_balance_error=state.mass_balance_error,
        node_holding_events=state.node_holding_events,
    )


def _canonical_result_payload(
    network: NetworkSpec,
    requests: Sequence[VehicleRequest],
    config: CTMConfig,
    initial_state: CTMState,
    state: CTMState,
    snapshots: Sequence[SimulationSnapshot],
) -> dict[str, object]:
    return {
        "network": {
            "links": [
                {
                    name: getattr(link, name)
                    for name in LinkSpec.__dataclass_fields__
                }
                for link in network.links
            ],
            "movements": [
                {
                    "from_link": movement.from_link,
                    "to_link": movement.to_link,
                    "capacity_veh_per_hour": movement.capacity_veh_per_hour,
                    "priority_weight": movement.priority_weight,
                    "green_cycle": list(movement.green_cycle),
                }
                for movement in network.movements
            ],
        },
        "requests": [
            {
                "vehicle_id": request.vehicle_id,
                "release_tick": request.release_tick,
                "route": list(request.route),
            }
            for request in requests
        ],
        "config": {
            "tick_seconds": config.tick_seconds,
            "node_policy": config.node_policy,
            "fifo_mode": config.fifo_mode,
            "movement_age_priority": config.movement_age_priority,
            "forced_cell_count_by_link": dict(config.forced_cell_count_by_link),
            "virtual_finish_cost_scale": config.virtual_finish_cost_scale,
            "waiting_cost_scale": config.waiting_cost_scale,
        },
        "initial": {
            "tick": initial_state.tick,
            "cells": initial_state.cells,
            "pending": initial_state.pending_by_link,
            "route_positions": initial_state.route_positions,
            "admitted_ticks": initial_state.admitted_ticks,
            "completed_ticks": initial_state.completed_ticks,
            "released_count": initial_state.released_count,
            "cumulative_source_admissions": (
                initial_state.cumulative_source_admissions
            ),
        },
        "final": {
            "tick": state.tick,
            "cells": state.cells,
            "pending": state.pending_by_link,
            "route_positions": state.route_positions,
            "admitted_ticks": state.admitted_ticks,
            "completed_ticks": state.completed_ticks,
            "cumulative_movement_flow": state.cumulative_movement_flow_tokens,
            "mass_balance_error": state.mass_balance_error,
            "node_holding_events": state.node_holding_events,
        },
        "snapshots": [
            {
                "tick": snapshot.tick,
                "released": snapshot.released_count,
                "pending": snapshot.pending_count,
                "active": snapshot.active_count,
                "completed": snapshot.completed_count,
                "occupancy": dict(snapshot.link_occupancy_ratio),
                "cells": {
                    key: list(value)
                    for key, value in snapshot.link_cell_occupancy_ratio.items()
                },
                "movement": [
                    [source, target, value]
                    for (source, target), value in sorted(
                        snapshot.cumulative_movement_flow.items(),
                        key=lambda item: (item[0][0], "" if item[0][1] is None else item[0][1]),
                    )
                ],
            }
            for snapshot in snapshots
        ],
    }


def simulate(
    network: NetworkSpec,
    requests: Sequence[VehicleRequest],
    config: CTMConfig | None = None,
    *,
    ticks: int,
    incidents: Sequence[Incident] = (),
    initial_state: CTMState | None = None,
) -> SimulationResult:
    if not isinstance(ticks, int) or isinstance(ticks, bool) or ticks < 0:
        raise ValueError("ticks must be a non-negative integer")
    cfg = config or CTMConfig()
    ordered_requests = tuple(sorted(requests, key=lambda request: request.vehicle_id))
    if initial_state is None:
        state = initialize_state(network, ordered_requests, cfg)
    else:
        link_index, movement_index, _ = _network_indices(network)
        ordered_requests = _validate_requests(
            network,
            ordered_requests,
            link_index,
            movement_index,
        )
        geometries = tuple(_derive_geometry(link, cfg) for link in network.links)
        _validate_state(network, ordered_requests, cfg, initial_state, geometries)
        state = initial_state
    starting_state = state
    snapshots: list[SimulationSnapshot] = []
    for _ in range(ticks):
        state, snapshot = step(
            network,
            ordered_requests,
            cfg,
            state,
            incidents=incidents,
        )
        snapshots.append(snapshot)
    payload = _canonical_result_payload(
        network,
        ordered_requests,
        cfg,
        starting_state,
        state,
        snapshots,
    )
    fingerprint = sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
            "utf-8"
        )
    ).hexdigest()
    travel_times: list[float] = []
    for vehicle_id, completed_tick in enumerate(state.completed_ticks):
        admitted_tick = state.admitted_ticks[vehicle_id]
        if completed_tick is not None and admitted_tick is not None:
            travel_times.append((completed_tick - admitted_tick) * cfg.tick_seconds)
    movement_flow = {
        (movement.from_link, movement.to_link): state.cumulative_movement_flow_tokens[index]
        for index, movement in enumerate(network.movements)
    }
    return SimulationResult(
        final_state=state,
        snapshots=tuple(snapshots),
        fingerprint=fingerprint,
        completed_travel_times_s=tuple(travel_times),
        cumulative_movement_flow=MappingProxyType(movement_flow),
        node_holding_events=state.node_holding_events,
    )
