"""Active-moment/delay-queue mesoscopic network: vehicle-equivalent masses."""

from __future__ import annotations
from dataclasses import dataclass
import math
from dataclasses import asdict


@dataclass(frozen=True, slots=True)
class Signal:
    cycle_s: float
    green_s: float
    offset_s: float = 0.0


@dataclass(frozen=True, slots=True)
class Road:
    id: str
    tail: str
    head: str
    length_m: float
    free_speed_mps: float
    capacity_veh_s: float
    storage_veh: float
    priority: float = 1.0
    signal: Signal | None = None


@dataclass(frozen=True, slots=True)
class Demand:
    origin: str
    destination: str
    start_s: float
    end_s: float
    rate_veh_s: float


@dataclass(frozen=True, slots=True)
class Config:
    dt_s: float = 1.0
    restart_rate_s: float = 0.2
    background_stop_rate_s: float = 0.0
    interaction_rate_s: float = 0.2
    temperature_s: float = 15.0
    route_response_s: float = 60.0
    route_refresh_s: float = 15.0
    paths_per_od: int = 3
    path_expansion_budget: int = 2000
    event_budget: int = 100000
    adaptive_routes: bool = False
    max_routes_per_od: int = 8
    route_regret_budget_s: float = 15.0
    max_live_suffixes: int = 4096


class BudgetExceeded(RuntimeError):
    """Computation bound; last valid immutable state is retained."""


def _signal_green(sig: Signal | None, t: float) -> bool:
    return sig is None or (t - sig.offset_s) % sig.cycle_s < sig.green_s


def _factor(road_id, t, windows):
    ans = 1.0
    for link, start, end, value in windows:
        if link == road_id and start <= t < end:
            ans *= value
    return ans


def _eligible_seconds(road, t, dt, windows, signal=True):
    """Integrate joint signal*incident availability, not the product of means."""
    cuts = {t, t + dt}
    for link, start, end, _ in windows:
        if link == road.id:
            if t < start < t + dt:
                cuts.add(start)
            if t < end < t + dt:
                cuts.add(end)
    sig = road.signal if signal else None
    if sig is not None:
        lo = math.floor((t - sig.offset_s) / sig.cycle_s) - 1
        hi = math.ceil((t + dt - sig.offset_s) / sig.cycle_s) + 1
        for n in range(lo, hi + 1):
            for at in (
                sig.offset_s + n * sig.cycle_s,
                sig.offset_s + n * sig.cycle_s + sig.green_s,
            ):
                if t < at < t + dt:
                    cuts.add(at)
    cuts = sorted(cuts)
    return math.fsum(
        (b - a) * _factor(road.id, (a + b) / 2, windows)
        for a, b in zip(cuts, cuts[1:])
        if _signal_green(sig, (a + b) / 2)
    )


def _validate(roads, demands, cfg, horizon, windows, conflicts):
    if not roads or len({r.id for r in roads}) != len(roads):
        raise ValueError("empty/duplicate road graph")
    if not demands or horizon <= 0 or not math.isfinite(horizon):
        raise ValueError("invalid demand/horizon")
    for road in roads:
        if road.tail == road.head:
            raise ValueError("self-loop road not allowed")
        if any(
            not math.isfinite(x) or x <= 0
            for x in (
                road.length_m,
                road.free_speed_mps,
                road.capacity_veh_s,
                road.storage_veh,
                road.priority,
            )
        ):
            raise ValueError("road units/limits must be finite positive")
        s = road.signal
        if s is not None and (
            not all(math.isfinite(x) for x in (s.cycle_s, s.green_s, s.offset_s))
            or s.cycle_s <= 0
            or not 0 <= s.green_s <= s.cycle_s
        ):
            raise ValueError("invalid signal interval")
    if (
        cfg.dt_s <= 0
        or cfg.restart_rate_s <= 0
        or cfg.interaction_rate_s < 0
        or cfg.background_stop_rate_s < 0
    ):
        raise ValueError("invalid kinetic time/rates")
    if cfg.route_refresh_s <= 0 or cfg.route_response_s <= 0 or cfg.temperature_s < 0:
        raise ValueError("invalid routing scales")
    if not all(math.isfinite(x) for x in asdict(cfg).values()):
        raise ValueError("nonfinite config")
    if cfg.paths_per_od < 1 or cfg.path_expansion_budget < 1 or cfg.event_budget < 1:
        raise ValueError("invalid computation budget")
    if cfg.max_live_suffixes < 1:
        raise ValueError("invalid suffix budget")
    if cfg.max_routes_per_od < cfg.paths_per_od or cfg.route_regret_budget_s < 0:
        raise ValueError("invalid adaptive route budget")
    for d in demands:
        if (
            not all(math.isfinite(x) for x in (d.start_s, d.end_s, d.rate_veh_s))
            or d.start_s < 0
            or d.end_s <= d.start_s
            or d.rate_veh_s < 0
            or d.origin == d.destination
        ):
            raise ValueError("invalid aggregate demand schedule")
    rd = {r.id: r for r in roads}
    for link, a, b, f in windows:
        if (
            link not in rd
            or not (0 <= a < b and 0 <= f <= 1)
            or not all(math.isfinite(x) for x in (a, b, f))
        ):
            raise ValueError("invalid capacity window")
    for i, j in conflicts:
        if i not in rd or j not in rd:
            raise ValueError("unknown signal conflict link")
        a, b = rd[i].signal, rd[j].signal
        if a is None or b is None:
            raise ValueError("declared conflicts require explicit signal plans")
        if a.cycle_s != b.cycle_s:
            raise ValueError("conflict validation supports a common cycle only")
        T = a.cycle_s
        cuts = {0.0, T}
        for sig in (a, b):
            cuts.add(sig.offset_s % T)
            cuts.add((sig.offset_s + sig.green_s) % T)
        cuts = sorted(cuts)
        if any(
            _signal_green(a, (x + y) / 2) and _signal_green(b, (x + y) / 2)
            for x, y in zip(cuts, cuts[1:])
        ):
            raise ValueError("conflicting green intervals")
