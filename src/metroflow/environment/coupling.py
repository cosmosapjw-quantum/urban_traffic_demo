"""Physical environment adapter and bounded active-suffix transport probes.

All physics is a declared research recipe, not calibrated city engineering.
Topology and urban stocks are frozen during each fast traffic run.
"""

from dataclasses import replace
from itertools import combinations
import math
from ..active_suffix import Road, Signal, Config, Model, BudgetExceeded


def road_physics(city):
    """Two directed roads per centreline, grade-dependent speed and finite storage.

    12/(1+3*|grade|) m/s; 0.5 veh/s per direction (bridge 0.7);
    0.12 veh/m storage per direction. At degree>=3 a single incoming approach
    receives green28 s + all-red2 s; conflicts are declared pairwise.
    No traffic-light optimization or bridge structural validation is claimed.
    """
    roads = []
    for e in city.network.links:
        for number, (u, v) in enumerate(((e.u, e.v), (e.v, e.u))):
            roads.append(
                Road(
                    e.id + f"|{number}",
                    u,
                    v,
                    e.length_m,
                    12.0 / (1 + 3 * e.grade),
                    0.7 if e.kind == "bridge" else 0.5,
                    0.12 * e.length_m,
                )
            )
    heads = {}
    for r in roads:
        heads.setdefault(r.head, []).append(r.id)
    signals = {}
    conflicts = []
    for node, group in sorted(heads.items()):
        if len(group) < 3:
            continue
        group = sorted(group)
        for slot, key in enumerate(group):
            signals[key] = Signal(30.0 * len(group), 28.0, slot * 30.0)
        conflicts.extend(combinations(group, 2))
    return tuple(
        replace(r, signal=signals.get(r.id)) for r in sorted(roads, key=lambda r: r.id)
    ), tuple(conflicts)


def run_commute(
    city,
    plan,
    horizon_s,
    config=Config(
        dt_s=5.0,
        route_refresh_s=30.0,
        paths_per_od=2,
        adaptive_routes=True,
        max_routes_per_od=4,
        event_budget=12000,
    ),
):
    """Run bounded aggregate transport and report NOT_RELEASED separately.

    Local trips and non-car modes stay in their own planning ledger. They are
    never reported as completed road trips. Mean journey time is available only
    after the entire road-demand schedule has been released and cleared.
    """
    if not math.isfinite(horizon_s) or horizon_s <= 0 or config.dt_s <= 0:
        raise ValueError("invalid observation horizon")
    steps = round(horizon_s / config.dt_s)
    if steps < 1 or abs(steps * config.dt_s - horizon_s) > 1e-9 * max(1.0, horizon_s):
        raise ValueError("horizon must be an integer number of time steps")
    if not plan.demands:
        raise ValueError("no interzonal road demand; use planning ledger only")
    roads, conflicts = road_physics(city)
    model = Model(roads, plan.demands, config, conflicts=conflicts)
    state = model.initial()
    peak_suffix = len(state.suffixes)
    peak_events = 0
    mass_error = 0.0
    storage_ratio = 0.0
    history = []
    reason = None
    for _ in range(steps):
        try:
            state = model.step(state)
        except BudgetExceeded as exc:
            state = exc.checkpoint
            reason = str(exc)
            break
        occ, _ = model.occupancy(state)
        mass_error = max(
            mass_error,
            abs(state.released - state.completed - math.fsum(state.pending) - math.fsum(occ)),
        )
        storage_ratio = max(storage_ratio, max(n / r.storage_veh for n, r in zip(occ, model.roads)))
        peak_suffix = max(peak_suffix, len(state.suffixes))
        peak_events = max(peak_events, len(state.transit))
        if state.tick % max(1, round(60 / config.dt_s)) == 0:
            history.append(
                dict(
                    time_s=state.tick * config.dt_s,
                    completed=state.completed,
                    active=math.fsum(occ),
                    pending=math.fsum(state.pending),
                )
            )
    occupied, _ = model.occupancy(state)
    active = math.fsum(occupied)
    pending = math.fsum(state.pending)
    planned = math.fsum((d.end_s - d.start_s) * d.rate_veh_s for d in plan.demands)
    not_released = planned - state.released
    tol = 1e-8 * max(1.0, planned)
    if not_released < -tol:
        raise ArithmeticError("released beyond planned demand")
    all_released = state.tick * config.dt_s >= max(d.end_s for d in plan.demands) - 1e-10
    cleared = all_released and active + pending <= tol and not reason
    report = dict(
        status="BLOCKED_RESOURCE" if reason else "CLEARED_SCOPED" if cleared else "HORIZON_REACHED",
        blocker=reason,
        resident_stock=city.population,
        job_stock=city.jobs,
        districts=len(plan.areas),
        directed_roads=len(roads),
        demand_schedules=len(plan.demands),
        planning_ledger=dict(plan.ledger),
        time_s=state.tick * config.dt_s,
        planned_network_vehicles=planned,
        not_yet_released=max(0.0, not_released),
        released=state.released,
        completed=state.completed,
        active=active,
        pending=pending,
        mean_network_journey_s=state.vehicle_seconds / state.completed
        if cleared and state.completed > 0
        else None,
        max_mass_error=mass_error,
        max_storage_ratio=storage_ratio,
        peak_live_suffixes=peak_suffix,
        peak_arrival_records=peak_events,
        route_repairs=state.routing_repairs,
        estimated_cache_regret_s=state.max_cached_route_regret_s,
        per_car_records=0,
        fingerprint=model.fingerprint(state),
        trace=history,
    )
    return report, state
