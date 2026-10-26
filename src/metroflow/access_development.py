"""Slow, capacity-limited development at authored sites with physical frontage."""

from dataclasses import dataclass
from .environment.terrain import Rect
from .restored_city import RoadMap
from dataclasses import replace
import math
from .environment.terrain import overlaps, cell_slope
from .environment.landuse import apportion
from .frontage_growth import Site, grow_access
from .restored_traffic import compile_traffic
from .active_suffix.routing import Arc, destination_potential


@dataclass(frozen=True, slots=True)
class Plot:
    id: str
    footprint: Rect
    capacity: int
    residents: int = 0
    access_node: str | None = None
    opened_epoch: int | None = None

    @property
    def xy(self):
        r = self.footprint
        return ((r.xmin + r.xmax) / 2, (r.ymin + r.ymax) / 2)


@dataclass(frozen=True, slots=True)
class Jobs:
    node: str
    opportunities: float


@dataclass(frozen=True, slots=True)
class Development:
    city: RoadMap
    plots: tuple[Plot, ...]
    epoch: int = 0
    offered: int = 0
    pending: int = 0
    built_m: float = 0.0


def _integer(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _validate(state, newcomers, jobs, budget_m, max_roads, tau_s):
    if not all(
        _integer(x) for x in (newcomers, state.epoch, state.offered, state.pending, max_roads)
    ):
        raise ValueError("nonnegative integer population, epoch and road budget required")
    if not math.isfinite(budget_m) or budget_m < 0 or not math.isfinite(tau_s) or tau_s <= 0:
        raise ValueError("invalid length budget or accessibility time scale")
    if not math.isfinite(state.built_m) or state.built_m < 0:
        raise ValueError("invalid cumulative construction")
    nodes = {n.id: n for n in state.city.nodes}
    if not jobs or any(
        j.node not in nodes or not math.isfinite(j.opportunities) or j.opportunities <= 0
        for j in jobs
    ):
        raise ValueError("positive opportunities at existing nodes required")
    if len({p.id for p in state.plots}) != len(state.plots) or not state.plots:
        raise ValueError("nonempty unique development sites required")
    limit = state.city.terrain.n * state.city.terrain.spacing_m
    for i, p in enumerate(state.plots):
        r = p.footprint
        if (
            not p.id
            or not all(map(math.isfinite, (r.xmin, r.ymin, r.xmax, r.ymax)))
            or not 0 <= r.xmin < r.xmax <= limit
            or not 0 <= r.ymin < r.ymax <= limit
            or not _integer(p.capacity)
            or not _integer(p.residents)
            or p.residents > p.capacity
        ):
            raise ValueError("invalid site footprint or finite stock")
        if p.access_node is None:
            if p.residents or p.opened_epoch is not None:
                raise ValueError("unserved site cannot carry developed residents")
        elif (
            p.access_node not in nodes
            or nodes[p.access_node].layer != 0
            or math.dist(nodes[p.access_node].xyz[:2], p.xy) > 1e-7
            or not _integer(p.opened_epoch)
            or p.opened_epoch > state.epoch
        ):
            raise ValueError("access must be a materialized ground node at the site")
        for q in state.plots[:i]:
            s = q.footprint
            if max(r.xmin, s.xmin) < min(r.xmax, s.xmax) and max(r.ymin, s.ymin) < min(
                r.ymax, s.ymax
            ):
                raise ValueError("overlapping development footprints")
    if sum(p.residents for p in state.plots) + state.pending != state.offered:
        raise ValueError("population stock ledger mismatch")


def _land_reason(city, plot):
    t = city.terrain
    r = plot.footprint
    if any(overlaps(r, b) for b in t.water + t.protected):
        return "land_exclusion"
    d = t.spacing_m
    # Use entire intersected terrain patches: conservative, not a parcel grading plan.
    ix = range(int(r.xmin / d), min(t.n, math.ceil(r.xmax / d)))
    iy = range(int(r.ymin / d), min(t.n, math.ceil(r.ymax / d)))
    if any(cell_slope(t, i, j) > 0.10 for i in ix for j in iy):
        return "land_grade"
    return None


def _accessibility(city, origins, jobs, tau_s):
    """Frozen legal free-flow opportunities; no queue/signal equilibrium claim."""
    net = compile_traffic(city, signals=False)
    arcs = tuple(Arc(r.id, r.tail, r.head) for r in net.roads)
    costs = {r.id: r.length_m / r.free_speed_mps for r in net.roads}
    tables = {j.node: destination_potential(arcs, costs, j.node, net.allowed_turns) for j in jobs}
    outgoing = {n: tuple(r.id for r in net.roads if r.tail == n) for n in origins}
    ans = {}
    for n in origins:
        values = []
        for j in jobs:
            seconds = (
                0.0
                if n == j.node
                else min((tables[j.node][r] for r in outgoing[n]), default=math.inf)
            )
            values.append(j.opportunities * math.exp(-seconds / tau_s))
        ans[n] = math.fsum(values)
    return ans


def develop(state, newcomers, jobs, budget_m=900.0, max_roads=4, tau_s=600.0, admission_rule=None):
    """One slow epoch: occupy vacancies, then build only to serve waiting growth.

    Sites/capacities and job opportunities are authored inputs, not market output.
    Preserve incumbents. Recompute legal accessibility after each accepted road.
    A site near an existing road but lacking an explicit access node remains
    unresolved: no zero-cost teleport or automatic resident assignment.
    """
    jobs = tuple(jobs)
    _validate(state, newcomers, jobs, budget_m, max_roads, tau_s)
    city = state.city
    plots = list(state.plots)
    pending = state.pending + newcomers
    built = []
    rejected = {}
    used = 0.0
    epoch = state.epoch + 1

    def fill():
        nonlocal pending, plots
        indices = [
            i for i, p in enumerate(plots) if p.access_node is not None and p.residents < p.capacity
        ]
        if not indices or not pending:
            return
        scores = _accessibility(city, {plots[i].access_node for i in indices}, jobs, tau_s)
        caps = tuple(
            plots[i].capacity - plots[i].residents if scores[plots[i].access_node] > 0 else 0
            for i in indices
        )
        total = min(pending, sum(caps))
        if not total:
            return
        weights = tuple(cap * scores[plots[i].access_node] for i, cap in zip(indices, caps))
        for i, amount in zip(indices, apportion(total, caps, weights)):
            plots[i] = replace(plots[i], residents=plots[i].residents + amount)
        pending -= total

    fill()
    while pending and len(built) < max_roads and used < budget_m:
        best = None
        for i, p in sorted(enumerate(plots), key=lambda row: row[1].id):
            if p.access_node is not None or p.capacity == 0:
                continue
            reason = _land_reason(city, p)
            if reason:
                rejected[p.id] = reason
                continue
            proposal = grow_access(
                city,
                (Site(p.id, p.xy),),
                budget_m=budget_m - used,
                max_roads=1,
                admission_rule=admission_rule,
            )
            if not proposal.admitted:
                rejected[p.id] = dict(proposal.rejected).get(p.id, "no_frontage")
                continue
            _, node, join, length = proposal.admitted[0]
            score = _accessibility(proposal.city, {node}, jobs, tau_s)[node]
            if score <= 0:
                rejected[p.id] = "no_legal_job_access"
                continue
            value = min(pending, p.capacity) * score / length
            rank = (-value, p.id)
            if best is None or rank < best[0]:
                best = (rank, i, proposal, node, join, length, score)
        if best is None:
            break
        _, i, proposal, node, join, length, score = best
        city = proposal.city
        plots[i] = replace(plots[i], access_node=node, opened_epoch=epoch)
        used += length
        built.append(
            dict(
                epoch=epoch,
                site=plots[i].id,
                access_node=node,
                join_node=join,
                length_m=length,
                opportunity_score=score,
            )
        )
        rejected.pop(plots[i].id, None)
        fill()
    out = Development(
        city, tuple(plots), epoch, state.offered + newcomers, pending, state.built_m + used
    )
    _validate(out, 0, jobs, 0.0, 0, tau_s)
    ledger = dict(
        epoch=epoch,
        newcomers=newcomers,
        residents=sum(p.residents for p in plots),
        pending=pending,
        offered=out.offered,
        budget_m=budget_m,
        used_m=used,
        built=built,
        rejected=sorted(rejected.items()),
        jobs=[(j.node, j.opportunities) for j in jobs],
        accessibility="legal free-flow opportunity score; jobs are not assigned workers",
    )
    return out, ledger
