"""Physical-road profiles -> legal, aggregate, active-suffix transport.

The compiler owns direction/layer/turn semantics and declared engineering priors.
The unchanged active_suffix engine owns the homogeneous kinetic moment, finite
storage, mass cohorts and committed routes. No per-vehicle or per-lane state.
"""
from __future__ import annotations
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
import hashlib
from itertools import combinations
import json
import math

from .active_suffix import Road, Signal
from .restored_city import RoadMap

# Authored research priors: m/s, veh/(s lane), merge priority per incoming link.
# These are not calibrated capacities or jurisdictional road-design standards.
_PROFILES = {
    'local': (8.33, .45, 1.),
    'collector': (13.89, .50, 2.),
    'arterial': (16.67, .55, 3.),
    'expressway': (25., .60, 4.),
}
_JAM_PER_LANE_M = .12
_LATERAL_ACCEL_MPS2 = 2.


@dataclass(frozen=True, slots=True)
class LinkBinding:
    link_id: str
    section_id: str
    direction: int
    lanes: int
    facility: str
    failure_group: str | None
    curvature_per_m: float


@dataclass(frozen=True, slots=True)
class TrafficNetwork:
    roads: tuple[Road, ...]
    allowed_turns: frozenset[tuple[str, str]]
    conflicts: tuple[tuple[str, str], ...]
    crosswalk: tuple[LinkBinding, ...]
    map_fingerprint: str


def _curvature(points):
    """Maximum three-point circumcircle curvature of the xy polyline.

    Consecutive duplicate samples are removed for this diagnostic only. It is a
    declared finite-resolution curve surrogate, not a continuous design proof.
    """
    xy = []
    for p in points:
        if not xy or math.dist(p[:2], xy[-1]) > 1e-7:
            xy.append(p[:2])
    result = 0.
    for a, b, c in zip(xy, xy[1:], xy[2:]):
        den = math.dist(a, b)*math.dist(b, c)*math.dist(a, c)
        if den <= 1e-12:
            raise ValueError('folded or degenerate centreline')
        cross = (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
        result = max(result, 2.*abs(cross)/den)
    return result


def compile_traffic(city: RoadMap, signals: bool = True) -> TrafficNetwork:
    """Compile only declared directions; connect only registered endpoints.

    Ground junctions with >=3 incoming links get one-approach-at-a-time green
    28 s and clearance 2 s. Elevated mainlines are never signalized. This is
    conservative conflict separation, not optimized urban signal control.
    """
    nodes = {n.id: n for n in city.nodes}
    if len(nodes) != len(city.nodes) or not nodes:
        raise ValueError('empty or duplicate junction identifiers')
    sections = {s.id: s for s in city.sections}
    if len(sections) != len(city.sections) or not sections:
        raise ValueError('empty or duplicate section identifiers')
    roads, bindings = [], []
    for s in sorted(city.sections, key=lambda s: s.id):
        if s.start not in nodes or s.end not in nodes or s.start == s.end:
            raise ValueError('section endpoint identity')
        if (len(s.points) < 2 or any(len(p) != 3 or not all(map(math.isfinite, p)) for p in s.points)
                or not math.isfinite(s.length_m) or s.length_m <= 0
                or not math.isfinite(s.max_grade) or not 0 <= s.max_grade <= .12+1e-10):
            raise ValueError('invalid section geometry or grade')
        if s.points[0] != nodes[s.start].xyz or s.points[-1] != nodes[s.end].xyz:
            raise ValueError('section endpoint geometry mismatch')
        if s.hierarchy not in _PROFILES:
            raise ValueError('unsupported road hierarchy')
        if any(isinstance(n, bool) or not isinstance(n, int) or n < 0
               for n in (s.forward_lanes, s.backward_lanes)) or s.forward_lanes+s.backward_lanes == 0:
            raise ValueError('invalid directional lanes')
        layers = (nodes[s.start].layer, nodes[s.end].layer)
        if s.facility == 'ramp':
            expected = {'on_ramp': (0, 1), 'off_ramp': (1, 0)}.get(s.ramp_purpose)
            if expected is None or layers != expected or s.backward_lanes or s.forward_lanes != 1:
                raise ValueError('ramp direction, layers or purpose inconsistent')
        elif s.facility == 'mainline':
            if layers != (1, 1) or s.backward_lanes or s.forward_lanes < 1:
                raise ValueError('mainline must be one-way and elevated')
        elif s.facility in ('surface', 'bridge'):
            if layers != (0, 0):
                raise ValueError('ground section cannot exchange layers')
        else:
            raise ValueError('unsupported facility; no implicit tunnel implementation')
        curvature = _curvature(s.points)
        speed, capacity, priority = _PROFILES[s.hierarchy]
        if s.facility == 'ramp':
            speed, capacity, priority = 11.11, .45, 1.
        speed /= 1.+3.*s.max_grade
        if curvature > 1e-12:
            speed = min(speed, math.sqrt(_LATERAL_ACCEL_MPS2/curvature))
        for direction, lanes, u, v in ((0, s.forward_lanes, s.start, s.end),
                                        (1, s.backward_lanes, s.end, s.start)):
            if not lanes:
                continue
            key = f'{s.id}|{direction}'
            roads.append(Road(key, u, v, s.length_m, speed, capacity*lanes,
                              _JAM_PER_LANE_M*lanes*s.length_m, priority))
            bindings.append(LinkBinding(key, s.id, direction, lanes, s.facility,
                                        s.failure_group, curvature))
    by_link = {b.link_id: sections[b.section_id] for b in bindings}
    incoming, outgoing = defaultdict(list), defaultdict(list)
    for r in roads:
        incoming[r.head].append(r)
        outgoing[r.tail].append(r)
    turns = set()
    ground = {'surface', 'bridge'}
    for node, group in incoming.items():
        for a in group:
            sa = by_link[a.id]
            for b in outgoing.get(node, ()):
                sb = by_link[b.id]
                if a.tail == b.head:
                    continue
                if nodes[node].layer == 1:
                    allowed = ((sa.facility == sb.facility == 'mainline')
                               or (sa.ramp_purpose == 'on_ramp' and sb.facility == 'mainline')
                               or (sa.facility == 'mainline' and sb.ramp_purpose == 'off_ramp'))
                else:
                    allowed = ((sa.facility in ground and sb.facility in ground)
                               or (sa.ramp_purpose == 'off_ramp' and sb.facility in ground)
                               or (sa.facility in ground and sb.ramp_purpose == 'on_ramp'))
                if allowed:
                    turns.add((a.id, b.id))
    plans, conflicts = {}, []
    if signals:
        for node, group in sorted(incoming.items()):
            if nodes[node].layer != 0 or len(group) < 3:
                continue
            keys = sorted(r.id for r in group)
            for slot, key in enumerate(keys):
                plans[key] = Signal(30.*len(keys), 28., 30.*slot)
            conflicts.extend(combinations(keys, 2))
    roads = tuple(replace(r, signal=plans.get(r.id)) for r in sorted(roads, key=lambda r: r.id))
    payload = dict(contract='restored_directional_meso_v1', map=asdict(city),
                   roads=[asdict(r) for r in roads], turns=sorted(turns), conflicts=conflicts)
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'),
                                      allow_nan=False).encode()).hexdigest()
    return TrafficNetwork(roads, frozenset(turns), tuple(conflicts), tuple(bindings), digest)


def structure_windows(network: TrafficNetwork, failures=()) -> tuple:
    """Expand a physical structure event to ALL bound directions and sections.

    Each failure is (failure_group, start_s, end_s, capacity_fraction). No link
    is removed and no in-flight mass is deleted. Closed committed traffic waits.
    """
    groups = defaultdict(list)
    for binding in network.crosswalk:
        if binding.failure_group is not None:
            groups[binding.failure_group].append(binding.link_id)
    windows = []
    for group, start, end, factor in failures:
        if group not in groups:
            raise ValueError(f'unknown structure failure group: {group}')
        if (not all(map(math.isfinite, (start, end, factor)))
                or not 0 <= start < end or not 0 <= factor <= 1):
            raise ValueError('invalid physical failure time/fraction')
        windows.extend((key, start, end, factor) for key in sorted(groups[group]))
    return tuple(sorted(windows))


def run_layered(network: TrafficNetwork, demands, horizon_s: float, config=None,
                failures=(), snapshot_period_s: float = 60.) -> tuple[dict, object]:
    """Bounded active-mesoscopic run with explicit non-completion and failures.

    Vehicle seconds count source waiting as well as network residence. Mean
    journey time is reported only after every scheduled vehicle has cleared.
    Initialization-budget failure has no state; later failure returns the last
    valid immutable state. The core update is reused without a physics rewrite.
    """
    from .active_suffix import Config, Model, BudgetExceeded
    config = config or Config(dt_s=5., route_refresh_s=30., paths_per_od=2,
                              adaptive_routes=True, max_routes_per_od=4,
                              max_live_suffixes=12000, event_budget=24000)
    if (not math.isfinite(horizon_s) or horizon_s <= 0
            or not math.isfinite(config.dt_s) or config.dt_s <= 0
            or not math.isfinite(snapshot_period_s) or snapshot_period_s <= 0):
        raise ValueError('invalid observation clock')
    steps = round(horizon_s/config.dt_s)
    if steps < 1 or abs(steps*config.dt_s-horizon_s) > 1e-9*max(1., horizon_s):
        raise ValueError('horizon must be an integer number of ticks')
    demands = tuple(demands)
    windows = structure_windows(network, failures)
    planned = math.fsum((d.end_s-d.start_s)*d.rate_veh_s for d in demands)
    base = dict(map_fingerprint=network.map_fingerprint,
                directed_roads=len(network.roads), legal_turns=len(network.allowed_turns),
                demand_schedules=len(demands), planned_network_vehicles=planned,
                physical_failures=tuple(failures), affected_link_windows=windows,
                per_car_records=0, kinetic_core='shared_committed_suffix_v1')
    try:
        model = Model(network.roads, demands, config, allowed_turns=network.allowed_turns,
                      capacity_windows=windows, conflicts=network.conflicts)
        state = model.initial()
    except BudgetExceeded as exc:
        return base | dict(status='BLOCKED_RESOURCE_INITIALIZATION', blocker=str(exc),
                           time_s=0., trace=[], checkpoint_available=False,
                           mean_network_journey_s=None), None
    peaks = [0.]*len(model.roads)
    max_mass_error = 0.
    peak_suffixes, peak_arrivals = len(state.suffixes), 0
    history, snapshots = [], []
    reason = None
    stride = max(1, round(snapshot_period_s/config.dt_s))
    for _ in range(steps):
        try:
            state = model.step(state)
        except BudgetExceeded as exc:
            state = exc.checkpoint
            reason = str(exc)
            break
        occupancy, waiting = model.occupancy(state)
        peaks = [max(a, b) for a, b in zip(peaks, occupancy)]
        error = state.released-state.completed-math.fsum(state.pending)-math.fsum(occupancy)
        max_mass_error = max(max_mass_error, abs(error))
        peak_suffixes = max(peak_suffixes, len(state.suffixes))
        peak_arrivals = max(peak_arrivals, len(state.transit))
        if state.tick % stride == 0 or state.tick == steps:
            history.append(dict(time_s=state.tick*config.dt_s, released=state.released,
                                completed=state.completed, active=math.fsum(occupancy),
                                pending=math.fsum(state.pending), queued=math.fsum(waiting)))
            snapshots.append(dict(time_s=state.tick*config.dt_s,
                                  occupancy_veh=occupancy, waiting_veh=waiting))
    occupancy, waiting = model.occupancy(state)
    active, pending = math.fsum(occupancy), math.fsum(state.pending)
    tol = 1e-8*max(1., planned)
    unreleased = planned-state.released
    if unreleased < -tol:
        raise ArithmeticError('released mass exceeds schedule')
    all_released = state.tick*config.dt_s >= max(d.end_s for d in demands)-1e-10
    cleared = all_released and active+pending <= tol and reason is None
    report = base | dict(
        status='BLOCKED_RESOURCE' if reason else 'CLEARED_SCOPED' if cleared else 'HORIZON_REACHED',
        blocker=reason, checkpoint_available=True, time_s=state.tick*config.dt_s,
        not_yet_released=max(0., unreleased), released=state.released, completed=state.completed,
        active=active, pending=pending,
        mean_network_journey_s=state.vehicle_seconds/state.completed if cleared and state.completed > 0 else None,
        max_mass_error=max_mass_error,
        max_storage_ratio=max(p/r.storage_veh for p, r in zip(peaks, model.roads)),
        peak_live_suffixes=peak_suffixes, peak_arrival_records=peak_arrivals,
        route_repairs=state.routing_repairs, route_solves=state.route_solves,
        estimated_cache_regret_s=state.max_cached_route_regret_s,
        min_activity=min(state.activity), max_activity=max(state.activity),
        fingerprint=model.fingerprint(state), trace=history, snapshots=snapshots,
        road_ids=[r.id for r in model.roads],
        final_occupancy_veh=occupancy, peak_occupancy_veh=peaks,
        cumulative_link_outflow_veh=list(state.link_outflow),
    )
    return report, state
