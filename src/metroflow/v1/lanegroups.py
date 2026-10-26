"""M02 direction/turn graph to explicit pooled or independent PacketNetwork lanes."""

from collections import defaultdict
from dataclasses import dataclass, replace
import hashlib
import json
import math

from ..ordered_lane import Lane
from ..ordered_network import Group
from ..packet_network import PacketNetwork
from ..restored_traffic import structure_windows
from .city import reject
from .nodes import validate_signal_conflicts
from .kinetics import ClassMass, KineticEnvironment, compile_bulk


@dataclass(frozen=True, slots=True)
class LanePartition:
    id: str
    link_id: str
    lanes: int
    successors: tuple[str, ...] | None = None  # outgoing physical link IDs

    def __post_init__(self):
        if (
            not self.id
            or not self.link_id
            or isinstance(self.lanes, bool)
            or not isinstance(self.lanes, int)
            or self.lanes < 1
        ):
            reject("positive integer lanes and explicit partition IDs required", "CONTRACT_ERROR")
        if self.successors is not None:
            object.__setattr__(self, "successors", tuple(self.successors))
            if len(set(self.successors)) != len(self.successors):
                reject("duplicate partition turn permission", "CONTRACT_ERROR")


@dataclass(frozen=True, slots=True)
class LaneGroupContract:
    city_identity: str
    groups: tuple[Group, ...]
    allowed_turns: frozenset[tuple[str, str]]
    partitions: tuple[LanePartition, ...]
    spaces_m: tuple[tuple[str, float], ...]
    windows: tuple
    conflicts: tuple[tuple[str, str], ...]


def compile_lanegroups(
    city,
    partitions=(),
    *,
    signals=None,
    conflicts=(),
    failures=(),
    dt_s=1.0,
    signal_event_budget=100000,
):
    """Partition every directional link's actual lanes once, without duplication.

    Unspecified links are pooled shared groups. Multiple partitions of a link
    mean physically independent lane subsets, not virtual duplicate capacity.
    Signals/conflicts are declared inputs; IDs never invent phase priority.
    """
    net = city.transport_graph
    roads = {r.id: r for r in net.roads}
    bindings = {b.link_id: b for b in net.crosswalk}
    parts = tuple(partitions)
    if len({p.id for p in parts}) != len(parts) or any(p.link_id not in roads for p in parts):
        reject("unique partitions must bind registered directional links", "CONTRACT_ERROR")
    per = defaultdict(list)
    for p in parts:
        per[p.link_id].append(p)
    for key, binding in bindings.items():
        if key not in per:
            per[key] = [LanePartition(key, key, binding.lanes)]
        if sum(p.lanes for p in per[key]) != binding.lanes:
            reject("partition lane counts must exactly cover the physical link", "CONTRACT_ERROR")
    parts = tuple(sorted((p for values in per.values() for p in values), key=lambda p: p.id))
    if len({p.id for p in parts}) != len(parts):
        reject("partition ID collides with another physical link", "CONTRACT_ERROR")
    signals = dict(signals or {})
    if any(k not in {p.id for p in parts} for k in signals):
        reject("signal binds unknown lane group", "CONTRACT_ERROR")
    groups = []
    spaces = []
    turns = set()
    for p in parts:
        road, binding = roads[p.link_id], bindings[p.link_id]
        fraction = p.lanes / binding.lanes
        # Legacy numeric storage field is not physical authority in this mode.
        lane = Lane(
            road.length_m,
            road.free_speed_mps,
            road.capacity_veh_s * fraction,
            road.capacity_veh_s * fraction,
            max(1.0, road.storage_veh * fraction),
        )
        groups.append(
            Group(p.id, road.tail, road.head, lane, road.priority * fraction, signals.get(p.id))
        )
        spaces.append((p.id, road.length_m * p.lanes))
        legal = {b for a, b in net.allowed_turns if a == p.link_id}
        selected = legal if p.successors is None else set(p.successors)
        if not selected <= legal:
            reject("lane partition grants an illegal physical turn", "CONTRACT_ERROR")
        turns.update((p.id, q.id) for q in parts if q.link_id in selected)
    conflicts = tuple(tuple(x) for x in conflicts)
    validate_signal_conflicts(groups, conflicts, dt_s, signal_event_budget)
    physical = structure_windows(net, failures)
    windows = tuple(sorted((p.id, a, b, f) for key, a, b, f in physical for p in per[key]))
    return LaneGroupContract(
        city.identity, tuple(groups), frozenset(turns), parts, tuple(spaces), windows, conflicts
    )


def packet_model(
    contract,
    routes,
    vehicle_classes,
    *,
    dt_s=1.0,
    record_budget=10000,
    event_budget=10000,
    standing_gap_m=0.0,
    motion=None,
    preserve_entry_intervals=False,
):
    """Routes explicitly choose group IDs; no turn reallocation or lane guessing."""
    validate_signal_conflicts(contract.groups, contract.conflicts, dt_s)
    model = PacketNetwork(
        contract.groups,
        tuple(routes),
        dt_s,
        contract.windows,
        record_budget,
        contract.allowed_turns,
        vehicle_classes=vehicle_classes,
        space_capacities_m=dict(contract.spaces_m),
        standing_gap_m=standing_gap_m,
        event_budget=event_budget,
        motion=motion,
        preserve_entry_intervals=preserve_entry_intervals,
    )
    model.identity = hashlib.sha256(
        json.dumps(
            dict(
                parent=model.identity,
                city=contract.city_identity,
                turns=sorted(contract.allowed_turns),
                conflicts=contract.conflicts,
            ),
            sort_keys=True,
        ).encode()
    ).hexdigest()
    return model


def lane_bulk_inputs(model, state, group_id, *, speed_mps, latent_by_class=None):
    """Feed real packet class masses to T02; motion integration belongs to T04.

    The caller supplies current common speed and optional class p/rate templates.
    Admission reserves standing gap; T02 still uses the full physical lane length.
    """
    model.check(state)
    if not model.physical_storage or group_id not in model.index:
        reject("class-aware registered lane group required", "CONTRACT_ERROR")
    i = model.index[group_id]
    cell = model.groups[i]
    masses = defaultdict(list)
    registry = {c.name: c for c in model.vehicle_classes.values()}
    for packet in state.cells[i].packets:
        for p in packet.parts:
            masses[model.vehicle_classes[p.tag].name].append(p.mass)
    templates = dict(latent_by_class or {})
    if any(
        k not in registry or not isinstance(v, ClassMass) or v.vehicle != registry[k]
        for k, v in templates.items()
    ):
        reject("latent template must match physical class registry", "CONTRACT_ERROR")
    classes = tuple(
        replace(templates.get(k, ClassMass(registry[k], 1.0)), mass_veh=math.fsum(v))
        for k, v in sorted(masses.items())
    )
    bulk = compile_bulk(classes, speed_mps=speed_mps, time_s=state.time_s)
    space = model.space_capacities_m[group_id]
    return bulk, KineticEnvironment(space, cell.physics.speed_mps, state.time_s)
