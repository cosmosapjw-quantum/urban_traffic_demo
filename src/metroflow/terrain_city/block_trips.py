"""Incremental occupants -> generic one-way visit masses -> real access routes.

Job counts are destination attractiveness, NOT new worker-to-job assignments.
This is an explicitly declared travel scenario, not empirical trip generation.
"""

from dataclasses import dataclass, replace as replace, asdict
from collections import defaultdict
from itertools import combinations as combinations
import hashlib
import json
import math
from ..active_suffix.common import Road, Signal
from ..active_suffix.routing import Arc, candidate_paths
from ..ordered_lane import Lane
from ..ordered_network import Group, Route, Network


@dataclass(frozen=True, slots=True)
class VisitPlan:
    identity: str
    groups: tuple[Group, ...]
    routes: tuple[Route, ...]
    amounts: tuple[tuple[str, float], ...]
    ledger: tuple[tuple[str, float], ...]
    road_paths: tuple[tuple[str, tuple[str, ...]], ...]


def plan_visits(
    growth,
    before,
    after,
    trips_per_new_resident=0.2,
    car_person_share=0.6,
    persons_per_car=1.2,
    max_routes=128,
    interaction_rate=0.2,
):
    growth._check(before)
    growth._check(after)
    values = (trips_per_new_resident, car_person_share, persons_per_car, interaction_rate)
    if (
        not all(map(math.isfinite, values))
        or trips_per_new_resident < 0
        or not 0 <= car_person_share <= 1
        or persons_per_car < 1
        or interaction_rate < 0
    ):
        raise ValueError("invalid person/vehicle/rate scales")
    if not isinstance(max_routes, int) or isinstance(max_routes, bool) or max_routes < 1:
        raise ValueError("invalid route budget")
    delta = tuple(b - a for a, b in zip(before.residents, after.residents))
    if after.epoch <= before.epoch or any(x < 0 for x in delta):
        raise ValueError("positive slow-time interval, no hidden relocation")
    if any(growth.blocks[i].id not in after.commissioned for i, d in enumerate(delta) if d):
        raise ValueError("new residents lack commissioned access")
    records = []
    local = 0.0
    scale = trips_per_new_resident * car_person_share / persons_per_car
    for i, extra in enumerate(delta):
        if not extra or not scale:
            continue
        origin = growth.blocks[i].id
        ws = growth.weights[origin]
        total = math.fsum(ws)
        if total <= 0:
            raise ValueError("no reachable visit destination")
        for target, weight in zip(growth.attractors, ws):
            amount = extra * scale * weight / total
            if amount <= 0:
                continue
            if origin == target:
                local += amount
            else:
                records.append((origin, target, amount))
    if len(records) > max_routes:
        raise ValueError("route budget exceeded; no trips dropped")
    roads = {r.id: r for r in growth.network.roads}
    bindings = {b.link_id: b for b in growth.network.crosswalk}
    turns = set(growth.network.allowed_turns)
    endpoints = {x for o, d, _ in records for x in (o, d)}
    public_in = defaultdict(list)
    public_out = defaultdict(list)
    for r in roads.values():
        public_in[r.head].append(r.id)
        public_out[r.tail].append(r.id)
    for key in sorted(endpoints):
        a = growth.access[key]
        out_id = f"private:{key}:out"
        in_id = f"private:{key}:in"
        roads[out_id] = Road(
            out_id, a.node, a.road_node, a.length_m, a.speed_mps, 0.25, 0.12 * a.length_m
        )
        roads[in_id] = Road(
            in_id, a.road_node, a.node, a.length_m, a.speed_mps, 0.25, 0.12 * a.length_m
        )
        turns.update((out_id, r) for r in public_out[a.road_node])
        turns.update((r, in_id) for r in public_in[a.road_node])
    for o in endpoints:
        for d in endpoints:
            if o != d and growth.access[o].road_node == growth.access[d].road_node:
                turns.add((f"private:{o}:out", f"private:{d}:in"))
    arcs = tuple(Arc(r.id, r.tail, r.head) for r in roads.values())
    costs = {r.id: r.length_m / r.free_speed_mps for r in roads.values()}
    route_list = []
    amounts = []
    used = set()
    for o, d, amount in records:
        found = candidate_paths(
            arcs, costs, growth.access[o].node, growth.access[d].node, 1, 20000, frozenset(turns)
        )
        if found.truncated or not found.paths:
            raise ValueError("legal visit route unresolved")
        path = found.paths[0]
        tag = f"{before.epoch}:{after.epoch}:{o}>{d}"
        route_list.append(Route(tag, path))
        amounts.append((tag, amount))
        used.update(path)
    # Restore a conservative full-topology phase plan, including new accesses.
    # Used-route subsetting does not shorten cycles by removing empty approaches.
    incoming = defaultdict(list)
    for r in roads.values():
        incoming[r.head].append(r.id)
    signals = {}
    for keys in incoming.values():
        if len(keys) < 3:
            continue
        for slot, key in enumerate(sorted(keys)):
            signals[key] = Signal(30.0 * len(keys), 28.0, 30.0 * slot)
    groups = []
    for key in sorted(used):
        r = roads[key]
        lanes = bindings[key].lanes if key in bindings else 1
        # One reference shared lane per direction, NOT full-FIFO for every real lane.
        physics = Lane(
            r.length_m,
            r.free_speed_mps,
            r.capacity_veh_s / lanes,
            r.capacity_veh_s / lanes,
            r.storage_veh / lanes,
            interaction_rate=interaction_rate,
        )
        groups.append(Group(key, r.tail, r.head, physics, r.priority, signals.get(key)))
    residents = sum(delta)
    persons = residents * trips_per_new_resident
    vehicles = persons * car_person_share / persons_per_car
    network = math.fsum(x[1] for x in amounts)
    if abs(vehicles - network - local) > 1e-10 * max(1.0, vehicles):
        raise ArithmeticError("visit ledger")
    ledger = dict(
        new_residents=residents,
        person_trips=persons,
        noncar_person_trips=persons * (1 - car_person_share),
        car_person_trips=persons * car_person_share,
        vehicle_trips=vehicles,
        network_vehicle_trips=network,
        unresolved_same_block_vehicle_trips=local,
    )
    payload = (
        growth.identity,
        asdict(before),
        asdict(after),
        values,
        [asdict(r) for r in route_list],
        amounts,
    )
    identity = hashlib.sha256(
        json.dumps(payload, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()
    return VisitPlan(
        identity,
        tuple(groups),
        tuple(route_list),
        tuple(amounts),
        tuple(sorted(ledger.items())),
        tuple((r.tag, r.groups) for r in route_list),
    )


def simulate_visits(plan, duration_s=60.0, horizon_s=2400.0, dt_s=1.0, record_budget=20000):
    if not plan.routes:
        raise ValueError("no interblock road demand; inspect the local ledger")
    if not all(math.isfinite(x) and x > 0 for x in (duration_s, horizon_s, dt_s)):
        raise ValueError("invalid observation interval")
    if any(abs(x / dt_s - round(x / dt_s)) > 1e-9 for x in (duration_s, horizon_s)):
        raise ValueError("source and observation boundaries must align")
    net = Network(plan.groups, plan.routes, dt_s=dt_s, record_budget=record_budget)
    state = net.initial()
    history = []
    exits = []
    peak = 0
    max_error = 0.0
    max_storage = 0.0
    for _ in range(round(horizon_s / dt_s)):
        offered = (
            tuple(
                (tag, amount * min(dt_s, max(0.0, duration_s - state.time_s)) / duration_s)
                for tag, amount in plan.amounts
            )
            if state.time_s < duration_s
            else ()
        )
        state, events = net.step(state, offered)
        exits.extend(asdict(e) for e in events if e.destination is None)
        occupancy = math.fsum(s.occupancy for s in state.lanes)
        pending = math.fsum(p.mass for p in state.pending)
        max_error = max(max_error, abs(state.released - state.completed - occupancy - pending))
        max_storage = max(
            max_storage,
            max(s.occupancy / g.physics.storage for g, s in zip(net.groups, state.lanes)),
        )
        peak = max(peak, len(state.pending) + sum(len(s.inside) for s in state.lanes))
        if round(state.time_s / dt_s) % max(1, round(60 / dt_s)) == 0:
            history.append(
                dict(
                    time_s=state.time_s,
                    completed=state.completed,
                    active=occupancy,
                    pending=pending,
                )
            )
        if state.time_s >= duration_s and occupancy + pending <= 1e-9 * max(1.0, state.released):
            break
    clear = state.time_s >= duration_s and occupancy + pending <= 1e-9 * max(1.0, state.released)
    road_residence = math.fsum(s.network_vehicle_seconds for s in state.lanes)
    report = dict(
        status="CLEARED_SCOPED" if clear else "HORIZON_REACHED",
        plan_identity=plan.identity,
        end_s=state.time_s,
        release_interval_s=duration_s,
        dt_s=dt_s,
        groups=len(net.groups),
        routes=len(plan.routes),
        planned_network_vehicles=math.fsum(m for _, m in plan.amounts),
        released=state.released,
        completed=state.completed,
        active=occupancy,
        pending=pending,
        mean_journey_s=state.system_vehicle_seconds / state.completed if clear else None,
        road_vehicle_seconds=road_residence,
        source_wait_seconds=state.source_wait_seconds,
        transfer_hold_seconds=state.transfer_hold_seconds,
        system_vehicle_seconds=state.system_vehicle_seconds,
        max_mass_error=max_error,
        max_storage_ratio=max_storage,
        peak_cohort_records=peak,
        per_car_records=0,
        ledger=dict(plan.ledger),
        trace=history,
        completed_events=exits,
        scope="generic visits from growth increment; one shared reference lane per used direction; fixed routes/free-flow planning; unchanged activity closure",
    )
    return report, state
