"""Polygon-authoritative atlas access and finite slow growth (metres/persons)."""

from dataclasses import dataclass
from dataclasses import asdict
import hashlib
import json
import math
from .landscape import Polygon, inside, edges, polygon_clear, segment_clear
from ..restored_geometry import crossing, ground_profile
from ..restored_traffic import compile_traffic
from ..active_suffix.routing import Arc, destination_potential
from ..environment.landuse import apportion


@dataclass(frozen=True, slots=True)
class Access:
    block: str
    road_node: str
    points: tuple[tuple[float, float, float], ...]
    length_m: float
    speed_mps: float

    @property
    def node(self):
        return f"block:{self.block}"


@dataclass(frozen=True, slots=True)
class GrowthState:
    atlas_id: str
    epoch: int
    residents: tuple[int, ...]
    commissioned: tuple[str, ...] = ()
    offered: int = 0
    pending: int = 0
    built_m: float = 0.0


def atlas_identity(atlas):
    """Bind polygons AND geometry/stock; legacy rectangular masks are not authority."""
    data = (asdict(atlas.landscape), asdict(atlas.roadmap), [asdict(b) for b in atlas.blocks])
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def segment_inside(a, b, polygon):
    """Closed straight segment containment in a simple polygon, including concavity.

    Split at all boundary events, then test every open interval. This is not
    just an endpoint or sparsely sampled containment test.
    """
    if not inside(a, polygon) or not inside(b, polygon):
        return False
    delta = (b[0] - a[0], b[1] - a[1])
    den = delta[0] ** 2 + delta[1] ** 2
    if den == 0:
        return True
    cuts = {0.0, 1.0}
    for p, q in edges(polygon.points):
        hit = crossing(a, b, p, q)
        if hit is not None:
            cuts.add(max(0.0, min(1.0, hit[0])))
        for r in (p, q):
            u = ((r[0] - a[0]) * delta[0] + (r[1] - a[1]) * delta[1]) / den
            if 0 < u < 1 and abs((r[0] - a[0]) * delta[1] - (r[1] - a[1]) * delta[0]) < 1e-8:
                cuts.add(u)
    ss = sorted(cuts)
    return all(
        inside((a[0] + (lo + hi) / 2 * delta[0], a[1] + (lo + hi) / 2 * delta[1]), polygon)
        for lo, hi in zip(ss, ss[1:])
        if hi - lo > 1e-12
    )


def build_access(atlas):
    """Private access from an interior activity point to a real boundary node.

    Accesses are separate from the face-generating street graph. Existing
    residents are not moved to an arbitrary nearest-road centroid. Whole-block
    mask rejection is conservative. Road-road lateral clearances are not proved.
    """
    nodes = {n.id: n for n in atlas.roadmap.nodes}
    surface = {
        n for s in atlas.roadmap.sections if s.facility == "surface" for n in (s.start, s.end)
    }
    regions = atlas.landscape.water + atlas.landscape.protected
    accepted = []
    rejected = []
    for block in atlas.blocks:
        if block.housing_capacity + block.job_capacity == 0:
            continue
        if len(block.boundary) != len(set(block.boundary)):
            rejected.append((block.id, "nonsimple_boundary"))
            continue
        poly = Polygon(block.id, tuple(nodes[n].xyz[:2] for n in block.boundary))
        if not polygon_clear(poly.points, regions):
            rejected.append((block.id, "polygon_exclusion"))
            continue
        anchors = [block.xy] + [
            tuple(sum(p[k] for p in triple) / 3 for k in (0, 1))
            for triple in zip(
                poly.points, poly.points[1:] + poly.points[:1], poly.points[2:] + poly.points[:2]
            )
        ]
        anchor = next((p for p in anchors if inside(p, poly)), None)
        if anchor is None:
            rejected.append((block.id, "no_interior_anchor"))
            continue
        options = []
        for key in sorted(set(block.boundary) & surface):
            node = nodes[key]
            if node.layer != 0 or not segment_inside(anchor, node.xyz[:2], poly):
                continue
            if not segment_clear(anchor, node.xyz[:2], regions, 2.0):
                continue
            if math.dist(anchor, node.xyz[:2]) < 1e-6:
                continue
            pts, length, grade = ground_profile(atlas.landscape.terrain, (anchor, node.xyz[:2]))
            if grade > 0.12:
                continue
            options.append((length, key, pts, grade))
        if not options:
            rejected.append((block.id, "no_legal_access"))
            continue
        length, key, pts, grade = min(options)
        accepted.append(Access(block.id, key, pts, length, 5.0 / (1 + 3 * grade)))
    return tuple(accepted), tuple(rejected)


class Growth:
    """Immutable slow stock, fixed footprints/capacities, budgeted private access.

    Inherited population persists even when its access is unresolved. Only new
    residents use the newly commissioned gates. Selected job endpoints are a
    declared inherited facility scenario; their access length is reported apart
    from new residential-access construction. This is not a housing market.
    """

    def __init__(self, atlas, attractor_ids, tau_s=600.0):
        if not math.isfinite(tau_s) or tau_s <= 0:
            raise ValueError("invalid accessibility time")
        self.atlas = atlas
        self.identity = atlas_identity(atlas)
        access, self.rejected = build_access(atlas)
        self.access = {a.block: a for a in access}
        self.blocks = tuple(atlas.blocks)
        self.indices = {b.id: i for i, b in enumerate(self.blocks)}
        self.attractors = tuple(attractor_ids)
        if not self.attractors or len(set(self.attractors)) != len(self.attractors):
            raise ValueError("unique accessible job attractors required")
        if any(
            k not in self.access or self.blocks[self.indices[k]].jobs <= 0 for k in self.attractors
        ):
            raise ValueError("job attractor has no admitted physical access or jobs")
        self.network = compile_traffic(atlas.roadmap, signals=False)
        arcs = tuple(Arc(r.id, r.tail, r.head) for r in self.network.roads)
        costs = {r.id: r.length_m / r.free_speed_mps for r in self.network.roads}
        outgoing = {a.road_node: [] for a in access}
        for r in self.network.roads:
            if r.tail in outgoing:
                outgoing[r.tail].append(r.id)
        tables = {
            k: destination_potential(
                arcs, costs, self.access[k].road_node, self.network.allowed_turns
            )
            for k in self.attractors
        }
        self.times = {}
        self.weights = {}
        self.scores = {}
        for a in access:
            times = []
            weights = []
            for k in self.attractors:
                dest = self.access[k]
                middle = (
                    0.0
                    if a.road_node == dest.road_node
                    else min((tables[k][r] for r in outgoing[a.road_node]), default=math.inf)
                )
                value = (
                    0.0
                    if a.block == k
                    else a.length_m / a.speed_mps + middle + dest.length_m / dest.speed_mps
                )
                times.append(value)
                weights.append(self.blocks[self.indices[k]].jobs * math.exp(-value / tau_s))
            self.times[a.block] = tuple(times)
            self.weights[a.block] = tuple(weights)
            self.scores[a.block] = math.fsum(weights)

    def initial(self):
        return GrowthState(self.identity, 0, tuple(b.residents for b in self.blocks))

    def _check(self, state):
        if state.atlas_id != self.identity:
            raise ValueError("atlas identity changed; no state hot-swap")
        ints = (state.epoch, state.offered, state.pending) + state.residents
        if any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in ints):
            raise ValueError("invalid integer stock")
        if len(state.residents) != len(self.blocks) or len(set(state.commissioned)) != len(
            state.commissioned
        ):
            raise ValueError("invalid development state shape")
        if not math.isfinite(state.built_m) or state.built_m < 0:
            raise ValueError("invalid construction ledger")
        if any(k not in self.access for k in state.commissioned):
            raise ValueError("unknown commissioned access")
        if any(
            not b.residents <= n <= b.housing_capacity for b, n in zip(self.blocks, state.residents)
        ):
            raise ValueError("incumbent or finite capacity violated")
        if (
            sum(state.residents) - sum(b.residents for b in self.blocks) + state.pending
            != state.offered
        ):
            raise ArithmeticError("growth stock ledger")
        if (
            abs(state.built_m - math.fsum(self.access[k].length_m for k in state.commissioned))
            > 1e-7
        ):
            raise ArithmeticError("access length ledger")

    def step(self, state, newcomers, budget_m=500.0, max_new_access=3):
        self._check(state)
        if any(
            isinstance(v, bool) or not isinstance(v, int) or v < 0
            for v in (newcomers, max_new_access)
        ):
            raise ValueError("nonnegative integer growth/access budget")
        if not math.isfinite(budget_m) or budget_m < 0:
            raise ValueError("invalid length budget")
        residents = list(state.residents)
        commissioned = list(state.commissioned)
        pending = state.pending + newcomers
        used = 0.0
        built = []

        def fill():
            nonlocal pending
            ids = [self.indices[k] for k in commissioned if self.scores[k] > 0]
            if not ids or not pending:
                return
            caps = tuple(self.blocks[i].housing_capacity - residents[i] for i in ids)
            total = min(pending, sum(caps))
            if not total:
                return
            weights = tuple(cap * self.scores[self.blocks[i].id] for cap, i in zip(caps, ids))
            for i, x in zip(ids, apportion(total, caps, weights)):
                residents[i] += x
            pending -= total

        fill()
        while pending and len(built) < max_new_access:
            candidates = []
            for k, a in self.access.items():
                i = self.indices[k]
                cap = self.blocks[i].housing_capacity - residents[i]
                if (
                    k in commissioned
                    or cap <= 0
                    or self.scores[k] <= 0
                    or a.length_m > budget_m - used + 1e-9
                ):
                    continue
                candidates.append((-min(pending, cap) * self.scores[k] / a.length_m, k))
            if not candidates:
                break
            _, key = min(candidates)
            commissioned.append(key)
            built.append(key)
            used += self.access[key].length_m
            fill()
        out = GrowthState(
            self.identity,
            state.epoch + 1,
            tuple(residents),
            tuple(commissioned),
            state.offered + newcomers,
            pending,
            state.built_m + used,
        )
        self._check(out)
        return out, dict(
            epoch=out.epoch,
            new_access=built,
            used_m=used,
            placed_new=sum(out.residents) - sum(state.residents),
            pending=out.pending,
            total_residents=sum(out.residents),
            newcomers=newcomers,
            inherited_job_access_m=math.fsum(self.access[k].length_m for k in self.attractors),
        )
