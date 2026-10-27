"""Explicit demand-independent synthetic fixed fleet and road-node depot.

The geometric-rank ring is a declared construction prior in the city's local
coordinate frame. Each corridor/departure is one independent vehicle, never a
claim that one bus can serve several runs. Unserved passenger OD stays pending
in the service consumer. The depot is a registered road door, not an inferred
warehouse or an additional freight-origin travel model.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from collections.abc import Mapping

from .city import reject
from .release_services import BusCorridor, compile_service_plan


@dataclass(frozen=True, slots=True)
class InventoryPolicy:
    max_stops: int = 4
    departures_s: tuple[float, ...] = (21600., 32400., 43200., 54000., 64800., 75600.)
    capacity_persons: float = 40.0
    dwell_s: float = 20.0
    max_runs: int = 20000

    def __post_init__(self):
        if (isinstance(self.max_stops, bool) or not isinstance(self.max_stops, int)
                or not 2 <= self.max_stops <= 32):
            reject('fixed inventory requires 2..32 geometric stops')
        if (isinstance(self.max_runs, bool) or not isinstance(self.max_runs, int)
                or self.max_runs < 1):
            reject('positive fixed fleet run budget required')
        if not isinstance(self.departures_s, (tuple, list)):
            reject('finite explicit tuple/list of fixed departures required')
        if len(self.departures_s) > self.max_runs:
            reject('fixed departures exceed fleet run budget', 'BLOCKED_RESOURCE')
        departures = tuple(self.departures_s)
        if (not departures or any(isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t)
                                  or not 0 <= t < 86400 for t in departures)
                or any(a >= b for a, b in zip(departures, departures[1:]))):
            reject('unique increasing fixed departures within one day required')
        if (isinstance(self.capacity_persons, bool) or isinstance(self.dwell_s, bool)
                or not isinstance(self.capacity_persons, (int, float))
                or not isinstance(self.dwell_s, (int, float))
                or not math.isfinite(self.capacity_persons) or self.capacity_persons <= 0
                or not math.isfinite(self.dwell_s) or self.dwell_s < 0):
            reject('finite positive fleet capacity and nonnegative dwell required')
        object.__setattr__(self, 'departures_s', departures)


@dataclass(frozen=True, slots=True)
class ReleaseInventory:
    city_identity: str
    policy: InventoryPolicy
    # (block id, node id); ordering follows the declared geometric prior.
    stops: tuple[tuple[str, str], ...]
    corridors: tuple[BusCorridor, ...]
    depot_block_id: str
    identity: str

    @property
    def physical_run_vehicles(self):
        return len(self.corridors)


def build_inventory(city, policy=None):
    """Construct and validate a finite directed stop ring without reading OD.

    The southwestern geometric rank is the depot. Stop ranks span the sorted
    registry including both endpoints. Shared physical nodes count once;
    representative blocks are selected by their boundary geometry. Full legal
    routes are validated by the same service compiler used for execution.
    """
    if policy is None:
        policy = InventoryPolicy()
    elif isinstance(policy, Mapping):
        try:
            policy = InventoryPolicy(**policy)
        except TypeError as exc:
            reject(f'invalid fixed inventory policy: {exc}')
    if not isinstance(policy, InventoryPolicy):
        reject('typed or explicit mapping inventory policy required')
    nodes = {n.id: n for n in city.roadmap.nodes}
    blocks = {b.id: b for b in city.face_graph.blocks}
    portals = {}
    for p in city.portals:
        if p.block_id not in blocks or p.node_id not in nodes or nodes[p.node_id].layer != 0:
            reject('fixed inventory requires registered block ground doors')
        if p.node_id not in blocks[p.block_id].boundary:
            reject('fixed inventory door must lie on its actual block boundary')
        portals.setdefault(p.block_id, []).append(p)
    unique_nodes = {}
    physical_keys = {}
    for block_id, options in portals.items():
        door = min(options, key=lambda p: nodes[p.node_id].xyz)
        block = blocks[block_id]
        key = (nodes[door.node_id].xyz,
               tuple(sorted(nodes[k].xyz for k in block.boundary)))
        if key in physical_keys and physical_keys[key] != block_id:
            reject('ambiguous duplicate physical stop block geometry')
        physical_keys[key] = block_id
        candidate = (key, block_id, door.node_id)
        previous = unique_nodes.get(door.node_id)
        if previous is None or key < previous[0]:
            unique_nodes[door.node_id] = candidate
    candidates = sorted(unique_nodes.values(), key=lambda x: x[0])
    count = min(policy.max_stops, len(candidates))
    if count < 2:
        reject('fixed fleet requires at least two distinct registered road doors', 'PHYSICAL_INFEASIBLE')
    selected = tuple(candidates[i * (len(candidates)-1) // (count-1)] for i in range(count))
    stops = tuple((block_id, node_id) for _, block_id, node_id in selected)
    runs = count * len(policy.departures_s)
    if runs > policy.max_runs:
        reject('fixed fleet run budget exceeded; no inventory dropped', 'BLOCKED_RESOURCE')
    corridors = tuple(
        BusCorridor(f'fixed-ring:{i}:{j}', a[0], b[0], departure,
                    policy.capacity_persons, policy.dwell_s)
        for i, (a, b) in enumerate(zip(stops, stops[1:] + stops[:1]))
        for j, departure in enumerate(policy.departures_s)
    )
    # With no request legs, validation cannot size the fleet from demand.
    compile_service_plan(city, (), corridors, depot_block_id=stops[0][0],
                         max_runs=policy.max_runs)
    payload = dict(schema='geometric_rank_directed_ring_v1', city_identity=city.identity,
                   policy=asdict(policy), stops=stops,
                   corridors=[asdict(c) for c in corridors], depot_block_id=stops[0][0])
    identity = hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()
    return ReleaseInventory(city.identity, policy, stops, corridors, stops[0][0], identity)
