"""Opt-in interval-rate transport retaining activity, node allocation and routes.

An inflow r on [a,b) reaches the exit on [a+tau,b+tau). tau is frozen at
entry from the inherited active moment. No per-car data, tick rounding or
instantaneous discharge of an entire future interval is used. Rates, not
individual cars, are advanced. Congested mixed queues and finite-space supply
remain an explicit finite-step approximation, NOT a full LWR/FIFO solver.
"""

from dataclasses import dataclass, fields, asdict
import hashlib
import json
import math
from .engine import Model, State, _path, _collect
from .common import BudgetExceeded, _factor, _signal_green
from .kinetic import relax_activity, relax_choice
from .routing import candidate_paths, destination_potential
from .node import allocate


@dataclass(frozen=True, slots=True)
class RateInterval:
    start_s: float
    end_s: float
    rate_veh_s: float
    suffix: int

    @property
    def mass(self):
        return (self.end_s - self.start_s) * self.rate_veh_s


@dataclass(frozen=True, slots=True)
class IntervalState(State):
    time_s: float = 0.0
    interval_merges: int = 0
    entry_activity: tuple[float, ...] = ()
    next_bulk_s: float = 0.0
    calendar_cdf_error_veh: float = 0.0
    calendar_moment_error_veh_s: float = 0.0


def canonical_intervals(events, with_error=False):
    """Add overlapping rates, then coalesce numerically equal adjacent rates.

    Mass is preserved, not pruned. The 1e-12 relative rate threshold and eight
    ulps of time only absorb floating arithmetic differences. Every approximate
    merge accumulates a conservative cumulative-count error and first-moment
    change. These bounds are on this representation, not a nonlinear-flow theorem.
    """
    groups = {}
    for k, e in enumerate(events):
        if not (
            math.isfinite(e.start_s)
            and math.isfinite(e.end_s)
            and math.isfinite(e.rate_veh_s)
            and e.end_s > e.start_s
            and e.rate_veh_s > 0
        ):
            raise ValueError("invalid interval")
        changes = groups.setdefault(e.suffix, {})
        changes.setdefault(e.start_s, []).append((k, e.rate_veh_s))
        changes.setdefault(e.end_s, []).append((k, None))
    out = []
    count_error = 0.0
    moment_error = 0.0
    for sid, changes in sorted(groups.items()):
        active = {}
        times = sorted(changes)
        for i, t in enumerate(times[:-1]):
            for k, rate in changes[t]:
                if rate is None:
                    active.pop(k, None)
                else:
                    active[k] = rate
            end = times[i + 1]
            rate = math.fsum(active.values())
            if rate <= 0:
                continue
            new = RateInterval(t, end, rate, sid)
            if out and out[-1].suffix == sid:
                last = out[-1]
                eps = 8 * math.ulp(max(1.0, abs(t), abs(last.end_s)))
                if abs(last.end_s - t) <= eps and abs(last.rate_veh_s - rate) <= 1e-12 * max(
                    last.rate_veh_s, rate
                ):
                    mass = math.fsum((last.mass, new.mass))
                    average = mass / (end - last.start_s)
                    merged = RateInterval(last.start_s, end, average, sid)

                    def cumulative(p, x):
                        return p.rate_veh_s * max(0.0, min(x, p.end_s) - p.start_s)

                    error = max(
                        abs(
                            math.fsum(
                                (cumulative(last, x), cumulative(new, x), -cumulative(merged, x))
                            )
                        )
                        for x in (last.start_s, last.end_s, t, end)
                    )
                    count_error += error
                    # First moment is evaluated about a local origin to avoid cancellation.
                    origin = last.start_s
                    moment_error += abs(
                        math.fsum(
                            (
                                last.mass * ((last.start_s + last.end_s) / 2 - origin),
                                new.mass * ((t + end) / 2 - origin),
                                -merged.mass * ((origin + end) / 2 - origin),
                            )
                        )
                    )
                    out[-1] = merged
                    continue
            out.append(new)
    result = tuple(out)
    return (result, count_error, moment_error) if with_error else result


class IntervalModel(Model):
    """The inherited Model prepares routes; its discrete step is never called.

    dt_s is a maximum integration step AND the fixed entry-activity update period.
    Transport events split steps but do not refresh the entry-delay snapshot. Available
    receiving space is computed from pre-step occupancy, a conservative supply
    closure with an O(dt) saturation error, explicitly not exact spillback waves.
    """

    def initial(self):
        s = super().initial()
        return IntervalState(
            **{f.name: getattr(s, f.name) for f in fields(State)},
            entry_activity=s.activity,
            next_bulk_s=self.cfg.dt_s,
        )

    def _end_time(self, state, stop_s):
        t = state.time_s
        end = min(t + self.cfg.dt_s, t + min(r.length_m / r.free_speed_mps for r in self.roads))
        if stop_s is not None:
            if not math.isfinite(stop_s) or stop_s <= t:
                raise ValueError("invalid stopping time")
            end = min(end, stop_s)
        events = [state.next_bulk_s]
        for d in self.demands:
            events.extend((d.start_s, d.end_s))
        for _, a, b, _ in self.windows:
            events.extend((a, b))
        for p in state.transit:
            events.extend((p.start_s, p.end_s))
        if state.last_choice_s >= 0:
            events.append(state.last_choice_s + self.cfg.route_refresh_s)
        for r in self.roads:
            s = r.signal
            if s is None:
                continue
            n = math.floor((t - s.offset_s) / s.cycle_s)
            for k in (n, n + 1):
                events.extend((s.offset_s + k * s.cycle_s, s.offset_s + k * s.cycle_s + s.green_s))
        # This is a boundary comparison tolerance, not interval merging or mass pruning.
        epsilon = 8 * math.ulp(max(1.0, abs(t)))
        return (
            min((x for x in events if x > t + epsilon), default=end)
            if not events
            else min([end] + [x for x in events if x > t + epsilon])
        )

    def _choices(self, state, table, roots, costs, factors, t):
        cfg = self.cfg
        index = {(s.road, s.next_id): s.id for s in table.values()}
        next_id = state.next_suffix_id
        refresh = (
            state.last_choice_s < 0
            or t - state.last_choice_s >= cfg.route_refresh_s - 1e-9
            or factors != state.last_factors
        )
        if not refresh:
            return (
                state.choice,
                state.last_choice_s,
                next_id,
                state.route_solves,
                state.routing_repairs,
                state.cache_evictions,
                state.max_cached_route_regret_s,
                state.max_pre_repair_route_regret_s,
                state.route_repair_expansions,
            )
        potentials = {
            d: destination_potential(self.arcs, costs, d, self.turns)
            for d in sorted({x.destination for x in self.demands})
        }
        shares = []
        repairs = state.routing_repairs
        evictions = state.cache_evictions
        regret = state.max_cached_route_regret_s
        pre = state.max_pre_repair_route_regret_s
        expansions = state.route_repair_expansions
        for od, d in enumerate(self.demands):
            group = roots[od]
            prior = list(state.choice[od])
            paths = [_path(table, sid) for sid in group]
            c = tuple(math.fsum(costs[self.roads[i].id] for i in p) for p in paths)
            best = min(
                (potentials[d.destination][r.id] for r in self.roads if r.tail == d.origin),
                default=math.inf,
            )
            finite = any(math.isfinite(x) for x in c)
            if math.isfinite(best) and finite:
                pre = max(pre, max(0.0, min(c) - best))
            need = math.isfinite(best) and (
                not finite or min(c) - best > cfg.route_regret_budget_s + 1e-9
            )
            if need and cfg.adaptive_routes:
                found = candidate_paths(
                    self.arcs,
                    costs,
                    d.origin,
                    d.destination,
                    1,
                    cfg.path_expansion_budget,
                    self.turns,
                )
                expansions += found.expanded
                if found.truncated or not found.paths:
                    raise BudgetExceeded("shortest-route search bound")
                path = tuple(self.index[e] for e in found.paths[0])
                if path not in paths:
                    sid, next_id = self._intern(table, index, path, next_id)
                    if len(group) < cfg.max_routes_per_od:
                        group.append(sid)
                        paths.append(path)
                        prior.append(0.0)
                    else:
                        k = max(range(len(group)), key=lambda k: (c[k], group[k]))
                        group[k] = sid
                        paths[k] = path
                        prior[k] = 0.0
                        evictions += 1
                    repairs += 1
                    c = tuple(math.fsum(costs[self.roads[i].id] for i in p) for p in paths)
                    finite = True
                if min(c) - best > cfg.route_regret_budget_s + 1e-8:
                    raise BudgetExceeded("route regret bound")
            if math.isfinite(best) and not finite:
                raise BudgetExceeded("detour outside fixed cache")
            if math.isfinite(best):
                regret = max(regret, max(0.0, min(c) - best))
            counts = {e: sum(e in p for p in paths) for p in paths for e in p}
            sizes = tuple(
                math.fsum(self.roads[e].length_m / counts[e] for e in p)
                / math.fsum(self.roads[e].length_m for e in p)
                for p in paths
            )
            response = cfg.route_refresh_s if state.last_choice_s < 0 else t - state.last_choice_s
            shares.append(
                relax_choice(prior, c, response, cfg.route_response_s, cfg.temperature_s, sizes)
            )
        return (
            tuple(shares),
            t,
            next_id,
            state.route_solves + len(potentials),
            repairs,
            evictions,
            regret,
            pre,
            expansions,
        )

    def step(self, state, stop_s=None):
        try:
            return self._interval_step(state, stop_s)
        except BudgetExceeded as exc:
            exc.checkpoint = state
            raise

    def _interval_step(self, state, stop_s):
        t = state.time_s
        end = self._end_time(state, stop_s)
        h = end - t
        cfg = self.cfg
        if h <= 0:
            raise ArithmeticError("nonprogressing interval clock")
        table = {s.id: s for s in state.suffixes}
        roots = [list(g) for g in state.source_roots]
        occ, waiting = self.occupancy(state)
        # Delay uses a declared lagged bulk-activity snapshot, refreshed every dt_s.
        # Transport event boundaries do not change the cohort delay within that period.
        running = [
            r.length_m / (r.free_speed_mps * state.entry_activity[i])
            for i, r in enumerate(self.roads)
        ]
        factors = tuple(_factor(r.id, (t + end) / 2, self.windows) for r in self.roads)
        service = {
            i: r.capacity_veh_s * factors[i] * float(_signal_green(r.signal, (t + end) / 2))
            for i, r in enumerate(self.roads)
        }
        receive = {
            i: min(r.capacity_veh_s * factors[i], max(0.0, r.storage_veh - occ[i]) / h)
            for i, r in enumerate(self.roads)
        }
        costs = {}
        for i, r in enumerate(self.roads):
            duty = r.signal.green_s / r.signal.cycle_s if r.signal else 1.0
            rate = r.capacity_veh_s * factors[i] * duty
            red = (
                (r.signal.cycle_s - r.signal.green_s) ** 2 / (2 * r.signal.cycle_s)
                if r.signal
                else 0.0
            )
            costs[r.id] = running[i] + waiting[i] / rate + red if rate > 0 else math.inf
        (choice, last, next_id, solves, repairs, evictions, regret, pre, expansions) = (
            self._choices(state, table, roots, costs, factors, t)
        )
        queues = dict(state.queues)
        arrival = {}
        for p in state.transit:
            overlap = max(0.0, min(end, p.end_s) - max(t, p.start_s))
            if overlap > 0:
                arrival[p.suffix] = arrival.get(p.suffix, 0.0) + p.rate_veh_s * overlap / h
        released_rates = [
            d.rate_veh_s * max(0.0, min(end, d.end_s) - max(t, d.start_s)) / h for d in self.demands
        ]
        # With frozen rates, a depleted queue is another physical event. Do not
        # spread a small queue over an arbitrary whole dt at subcapacity flow.
        for refinement in range(32):
            receive = {
                i: min(r.capacity_veh_s * factors[i], max(0.0, r.storage_veh - occ[i]) / h)
                for i, r in enumerate(self.roads)
            }
            tolerance = max(
                1e-12, 16 * math.ulp(max(1.0, abs(t))) * max(service.values(), default=0.0)
            )
            ready = {}
            for sid in set(queues) | set(arrival):
                q = queues.get(sid, 0.0)
                i = table[sid].road
                backlog = service[i] * q / waiting[i] if q > tolerance else q / h
                ready[sid] = arrival.get(sid, 0.0) + backlog
            movements = {}
            for sid, rate in sorted(ready.items()):
                if rate <= 0:
                    continue
                part = table[sid]
                i = part.road
                j = table[part.next_id].road if part.next_id != -1 else -1
                movements.setdefault(self.roads[i].head, {}).setdefault((i, j), []).append(sid)
            outflow = [0.0] * len(self.roads)
            inflow = [0.0] * len(self.roads)
            served = {}
            sink = 0.0
            for _, groups in sorted(movements.items()):
                demand = {m: math.fsum(ready[s] for s in ids) for m, ids in groups.items()}
                sending = {i: service[i] for i, _ in groups}
                supply = {
                    j: receive[j] if j >= 0 else math.fsum(sending.values()) for _, j in groups
                }
                flows = allocate(
                    demand, sending, supply, {i: self.roads[i].priority for i in sending}
                )
                for (i, j), amount in flows.items():
                    total = demand[(i, j)]
                    for sid in groups[(i, j)]:
                        rate = ready[sid] if amount >= total else amount * ready[sid] / total
                        served[sid] = rate
                        outflow[i] += rate
                        if j < 0:
                            sink += rate
                        else:
                            inflow[j] += rate
            # The source reservoir uses the same depletion rule. Current arrivals
            # are not backdated to the beginning of the slice.
            backlog_totals = {}
            for od, group in enumerate(roots):
                for sid, share in zip(group, choice[od]):
                    i = table[sid].road
                    backlog_totals[i] = backlog_totals.get(i, 0.0) + state.pending[od] * share
            candidates = []
            totals = {}
            for od, group in enumerate(roots):
                for sid, share in zip(group, choice[od]):
                    i = table[sid].road
                    q = state.pending[od] * share
                    backlog = (
                        self.roads[i].capacity_veh_s * factors[i] * q / backlog_totals[i]
                        if q > tolerance
                        else q / h
                    )
                    rate = released_rates[od] * share + backlog
                    if rate > 0:
                        candidates.append((od, sid, rate))
                        totals[i] = totals.get(i, 0.0) + rate
            admissions = []
            source_out = [0.0] * len(state.pending)
            for od, sid, wanted in candidates:
                i = table[sid].road
                rate = wanted * min(1.0, max(0.0, receive[i] - inflow[i]) / totals[i])
                admissions.append((od, sid, rate))
                source_out[od] += rate
            limit = h
            for sid, q in queues.items():
                excess = served.get(sid, 0.0) - arrival.get(sid, 0.0)
                if q > tolerance and excess > 0:
                    limit = min(limit, q / excess)
            for od, q in enumerate(state.pending):
                excess = source_out[od] - released_rates[od]
                if q > tolerance and excess > 0:
                    limit = min(limit, q / excess)
            if limit >= h * (1.0 - 1e-11):
                break
            h = limit
            end = t + h
        else:
            raise BudgetExceeded("queue-depletion coupling bound")
        newq = {}
        for sid in ready:
            remain = queues.get(sid, 0.0) + h * (arrival.get(sid, 0.0) - served.get(sid, 0.0))
            if remain < -1e-9:
                raise ArithmeticError("negative exit queue")
            if remain > 0:
                newq[sid] = remain
        future = [
            RateInterval(max(end, p.start_s), p.end_s, p.rate_veh_s, p.suffix)
            for p in state.transit
            if p.end_s > end
        ]
        for sid, rate in served.items():
            nxt = table[sid].next_id
            if nxt != -1 and rate > 0:
                j = table[nxt].road
                future.append(RateInterval(t + running[j], end + running[j], rate, nxt))
        pending = [
            max(0.0, q + h * (a - b)) for q, a, b in zip(state.pending, released_rates, source_out)
        ]
        admitted = h * math.fsum(source_out)
        for od, sid, rate in admissions:
            if rate > 0:
                i = table[sid].road
                future.append(RateInterval(t + running[i], end + running[i], rate, sid))
        packed, cdf_error, moment_error = canonical_intervals(future, with_error=True)
        retained = _collect(table, roots, newq, packed)
        if len(packed) > cfg.event_budget:
            raise BudgetExceeded("interval calendar bound")
        if len(retained) > cfg.max_live_suffixes:
            raise BudgetExceeded("live suffix pool bound")
        released = h * math.fsum(released_rates)
        completed = h * sink
        resident = state.released - state.completed
        # Exact system residence integral for declared piecewise-constant flows.
        area = resident * h + (released - completed) * h / 2
        activity = tuple(
            relax_activity(
                state.activity[i],
                cfg.restart_rate_s,
                cfg.background_stop_rate_s + cfg.interaction_rate_s * (occ[i] / r.storage_veh) ** 2,
                h,
            )
            for i, r in enumerate(self.roads)
        )
        refresh_bulk = end >= state.next_bulk_s - 8 * math.ulp(max(1.0, abs(end)))
        entry_activity = activity if refresh_bulk else state.entry_activity
        next_bulk = state.next_bulk_s + cfg.dt_s if refresh_bulk else state.next_bulk_s
        nxt = IntervalState(
            calendar_cdf_error_veh=state.calendar_cdf_error_veh + cdf_error,
            calendar_moment_error_veh_s=state.calendar_moment_error_veh_s + moment_error,
            entry_activity=entry_activity,
            next_bulk_s=next_bulk,
            tick=state.tick + 1,
            time_s=end,
            pending=tuple(max(0.0, x) for x in pending),
            queues=tuple(sorted(newq.items())),
            transit=packed,
            activity=activity,
            choice=choice,
            source_roots=tuple(tuple(g) for g in roots),
            suffixes=tuple(retained.values()),
            next_suffix_id=next_id,
            last_choice_s=last,
            last_factors=factors,
            released=state.released + released,
            admitted=state.admitted + admitted,
            completed=state.completed + completed,
            vehicle_seconds=state.vehicle_seconds + area,
            link_outflow=tuple(a + h * b for a, b in zip(state.link_outflow, outflow)),
            link_visits=state.link_visits + len(self.roads),
            route_solves=solves,
            cohort_slots_visited=state.cohort_slots_visited + len(state.transit),
            max_cached_route_regret_s=regret,
            max_pre_repair_route_regret_s=pre,
            routing_repairs=repairs,
            route_repair_expansions=expansions,
            cache_evictions=evictions,
            suffixes_collected=state.suffixes_collected + len(table) - len(retained),
            interval_merges=state.interval_merges + len(future) - len(packed),
        )
        now_occ, _ = self.occupancy(nxt)
        error = nxt.released - nxt.completed - math.fsum(nxt.pending) - math.fsum(now_occ)
        if abs(error) > 1e-8 * max(1.0, nxt.released):
            raise ArithmeticError(f"mass ledger {error}")
        if any(
            x > r.storage_veh + 1e-8 * max(1.0, r.storage_veh) for x, r in zip(now_occ, self.roads)
        ):
            raise ArithmeticError("finite storage exceeded")
        return nxt

    def fingerprint(self, state):
        payload = dict(
            contract="active_interval_rate_v1",
            roads=[asdict(r) for r in self.roads],
            demands=[asdict(d) for d in self.demands],
            config=asdict(self.cfg),
            state=asdict(state),
            turns=sorted(self.turns) if self.turns is not None else None,
            windows=self.windows,
            conflicts=self.conflicts,
        )
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()
