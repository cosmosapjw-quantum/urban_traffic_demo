"""M02: immutable physical city, face graph and directed transport contract.

SI metres. Polygon masks are authoritative. Profiles/turns/storage remain owned
by restored_traffic, not a second flow solver. Clearance is a centreline test,
not pavement/vehicle clearance certification; tunnels are unsupported.
"""

from collections import defaultdict
from dataclasses import asdict, dataclass, fields, is_dataclass
import hashlib
import json
import math

from ..environment.terrain import Terrain, Rect, validate_terrain
from ..restored_city import Junction, Section, RoadMap
from ..restored_geometry import (
    crossing,
    ground_profile,
    deck_profile,
    elevation,
    minimum_ground_gap,
)
from ..restored_traffic import TrafficNetwork, compile_traffic, structure_windows
from ..terrain_city.area_access import AreaAccess
from ..terrain_city.landscape import Landscape, Polygon, segment_clear, edges, polygon_clear
from ..terrain_city.network import Block


class CityContractError(ValueError):
    def __init__(self, status, reason):
        self.status, self.reason = status, reason
        super().__init__(f"{status}: {reason}")


def reject(reason, status="MODEL_ERROR"):
    raise CityContractError(status, reason)


@dataclass(frozen=True, slots=True)
class PortalRef:
    id: str
    block_id: str
    node_id: str


@dataclass(frozen=True, slots=True)
class FaceGraph:
    """Registered ground embedding only; elevated projections create no faces."""

    edges: tuple[tuple[str, str, str], ...]
    blocks: tuple[Block, ...]


@dataclass(frozen=True, slots=True)
class CitySnapshot:
    roadmap: RoadMap
    landscape: Landscape
    face_graph: FaceGraph
    transport_graph: TrafficNetwork
    portals: tuple[PortalRef, ...]
    requested_population: int
    unplaced_residents: int
    identity: str

    def to_dict(self):
        return dict(
            schema="metroflow_city_v1",
            roadmap=asdict(self.roadmap),
            landscape=asdict(self.landscape),
            blocks=[asdict(b) for b in self.face_graph.blocks],
            portals=[asdict(p) for p in self.portals],
            requested_population=self.requested_population,
            unplaced_residents=self.unplaced_residents,
            identity=self.identity,
        )

    def closure_links(self, failure_group):
        return tuple(
            w[0] for w in structure_windows(self.transport_graph, ((failure_group, 0.0, 1.0, 0.0),))
        )

    def reachable(self, origin, closed_groups=()):
        """Reachability on incoming-link states, respecting the same legal turns."""
        nodes = {n.id for n in self.roadmap.nodes}
        if origin not in nodes:
            reject("unknown reachability origin")
        groups = {b.failure_group for b in self.transport_graph.crosswalk if b.failure_group}
        if any(g not in groups for g in closed_groups):
            reject("unknown structure closure")
        closed = {
            b.link_id for b in self.transport_graph.crosswalk if b.failure_group in closed_groups
        }
        roads = {r.id: r for r in self.transport_graph.roads if r.id not in closed}
        turns = defaultdict(list)
        for a, b in self.transport_graph.allowed_turns:
            if a in roads and b in roads:
                turns[a].append(b)
        live = {r.id for r in roads.values() if r.tail == origin}
        stack = list(live)
        while stack:
            for key in turns[stack.pop()]:
                if key not in live:
                    live.add(key)
                    stack.append(key)
        return frozenset({origin} | {roads[k].head for k in live})

    def report(self):
        net = self.transport_graph
        stock = sum(b.residents for b in self.face_graph.blocks)
        groups = sorted(
            {b.failure_group for b in net.crosswalk if b.facility == "bridge" and b.failure_group}
        )
        bridge_effects = []
        for group in groups:
            binding = next(b for b in net.crosswalk if b.failure_group == group)
            origin = next(r.tail for r in net.roads if r.id == binding.link_id)
            before = self.reachable(origin)
            after = self.reachable(origin, (group,))
            bridge_effects.append(
                dict(
                    failure_group=group,
                    origin=origin,
                    affected_links=self.closure_links(group),
                    reachable_before=len(before),
                    reachable_after=len(after),
                    lost_nodes=sorted(before - after),
                    reachable_residents_after=sum(
                        b.residents
                        for b in self.face_graph.blocks
                        if any(n in after for n in b.boundary)
                    ),
                )
            )
        return dict(
            status="PHYSICAL_INFEASIBLE" if self.unplaced_residents else "PASS",
            identity=self.identity,
            nodes=len(self.roadmap.nodes),
            sections=len(self.roadmap.sections),
            directed_groups=len(net.roads),
            legal_turns=len(net.allowed_turns),
            face_edges=len(self.face_graph.edges),
            blocks=len(self.face_graph.blocks),
            block_area_m2=math.fsum(b.area_m2 for b in self.face_graph.blocks),
            max_grade=max((s.max_grade for s in self.roadmap.sections), default=0.0),
            storage_veh=math.fsum(r.storage_veh for r in net.roads),
            residents=stock,
            requested_population=self.requested_population,
            unplaced_residents=self.unplaced_residents,
            bridge_closures=bridge_effects,
            reachable_stock_definition="block residents with at least one reachable boundary node; not a trip assignment",
            geometry_scope="piecewise centreline intersections, 5m vertical separation; no pavement envelope certification",
        )


def _clearance(a, b, c, d, hit):
    u, v, _ = hit
    dx, dy = b[0] - a[0], b[1] - a[1]
    ex, ey = d[0] - c[0], d[1] - c[1]
    if abs(dx * ey - dy * ex) >= 1e-10:
        return abs(a[2] + u * (b[2] - a[2]) - c[2] - v * (d[2] - c[2]))
    den, other = dx * dx + dy * dy, ex * ex + ey * ey
    lo = max(
        0.0,
        min(
            ((c[0] - a[0]) * dx + (c[1] - a[1]) * dy) / den,
            ((d[0] - a[0]) * dx + (d[1] - a[1]) * dy) / den,
        ),
    )
    hi = min(
        1.0,
        max(
            ((c[0] - a[0]) * dx + (c[1] - a[1]) * dy) / den,
            ((d[0] - a[0]) * dx + (d[1] - a[1]) * dy) / den,
        ),
    )
    differences = []
    for t in (lo, hi):
        x, y = a[0] + t * dx, a[1] + t * dy
        q = ((x - c[0]) * ex + (y - c[1]) * ey) / other
        differences.append(a[2] + t * (b[2] - a[2]) - c[2] - q * (d[2] - c[2]))
    return 0.0 if differences[0] * differences[1] <= 0 else min(map(abs, differences))


def _self_crossings(section):
    if _straight(section.points):
        return
    segments = tuple(zip(section.points, section.points[1:]))
    for i, (a, b) in enumerate(segments):
        for c, d in segments[i + 2 :]:
            hit = crossing(a, b, c, d)
            if hit is not None and _clearance(a, b, c, d, hit) < 5.0 - 1e-6:
                reject(f"illegal self crossing {section.id}")


def _crossings(roadmap):
    """Spatial broad phase; exact piecewise-segment witnesses with vertical gap."""
    bucket = defaultdict(list)
    nodes = {n.id: n for n in roadmap.nodes}
    sections = roadmap.sections
    for i, s in enumerate(sections):
        xs, ys = [p[0] for p in s.points], [p[1] for p in s.points]
        cells = [
            (x, y)
            for x in range(math.floor(min(xs) / 400), math.floor(max(xs) / 400) + 1)
            for y in range(math.floor(min(ys) / 400), math.floor(max(ys) / 400) + 1)
        ]
        for j in sorted({j for c in cells for j in bucket[c]}):
            r = sections[j]
            common = {s.start, s.end} & {r.start, r.end}
            common_xy = [nodes[k].xyz[:2] for k in common]
            # Avoid unstable determinant division on collinear straight rays at a joint.
            if len(common) == 1 and _straight(s.points) and _straight(r.points):
                joint = common_xy[0]
                a = s.points[-1] if math.dist(s.points[0][:2], joint) < 1e-7 else s.points[0]
                b = r.points[-1] if math.dist(r.points[0][:2], joint) < 1e-7 else r.points[0]
                u, v = (a[0] - joint[0], a[1] - joint[1]), (b[0] - joint[0], b[1] - joint[1])
                det, dot = u[0] * v[1] - u[1] * v[0], u[0] * v[0] + u[1] * v[1]
                if dot <= 0 or abs(det) > 1e-12 * math.hypot(*u) * math.hypot(*v):
                    continue
            for a, b in zip(s.points, s.points[1:]):
                for c, d in zip(r.points, r.points[1:]):
                    if (
                        max(a[0], b[0]) < min(c[0], d[0]) - 1e-8
                        or max(c[0], d[0]) < min(a[0], b[0]) - 1e-8
                        or max(a[1], b[1]) < min(c[1], d[1]) - 1e-8
                        or max(c[1], d[1]) < min(a[1], b[1]) - 1e-8
                    ):
                        continue
                    hit = crossing(a, b, c, d)
                    if hit is None:
                        continue
                    u, v, xy = hit
                    if any(math.dist(xy, p) < 1e-6 for p in common_xy):
                        continue
                    gap = _clearance(a, b, c, d, hit)
                    if gap < 5.0 - 1e-6:
                        reject(f"illegal crossing {s.id}/{r.id}, clearance {gap:g} m")
        for c in cells:
            bucket[c].append(i)


def _straight(points):
    a, b = points[0], points[-1]
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    if length <= 0:
        return False
    values = [((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (length * length) for p in points]
    return (
        all(abs((p[0] - a[0]) * dy - (p[1] - a[1]) * dx) <= 1e-8 * length for p in points)
        and all(-1e-10 <= v <= 1.0 + 1e-10 for v in values)
        and all(v >= u - 1e-10 for u, v in zip(values, values[1:]))
    )


def _unique(items, label):
    ids = [x.id for x in items]
    if any(not isinstance(k, str) or not k for k in ids) or len(set(ids)) != len(ids):
        reject(f"invalid/duplicate {label} identity")


def _immutable(value):
    if isinstance(value, tuple):
        for item in value:
            _immutable(item)
    elif is_dataclass(value) and value.__dataclass_params__.frozen:
        for field in fields(value):
            _immutable(getattr(value, field.name))
    elif type(value) not in (str, int, float, bool, type(None)):
        reject("physical snapshot inputs must be deeply immutable tuple registries")


def compile_city(
    roadmap,
    landscape=None,
    blocks=(),
    portals=(),
    *,
    requested_population=None,
    unplaced_residents=0,
    group_budget=10000,
):
    """Validate physical inputs, then reuse the directional compiler unchanged."""
    if (
        isinstance(group_budget, bool)
        or not isinstance(group_budget, int)
        or not 1 <= group_budget <= 10000
    ):
        reject("directional group budget must be in [1,10000]")
    try:
        blocks, portals = tuple(blocks), tuple(portals)
        _immutable(roadmap)
        _immutable(blocks)
        _immutable(portals)
        validate_terrain(roadmap.terrain)
        _unique(roadmap.nodes, "node")
        _unique(roadmap.sections, "section")
        nodes = {n.id: n for n in roadmap.nodes}
        if any(
            n.layer not in (0, 1)
            or not isinstance(n.layer, int)
            or isinstance(n.layer, bool)
            or len(n.xyz) != 3
            or not all(map(math.isfinite, n.xyz))
            for n in roadmap.nodes
        ):
            reject("invalid node coordinates/layer")
        for s in roadmap.sections:
            if any(
                isinstance(n, bool) or not isinstance(n, int) or n < 0
                for n in (s.forward_lanes, s.backward_lanes)
            ):
                reject("invalid lanes")
        groups = sum((s.forward_lanes > 0) + (s.backward_lanes > 0) for s in roadmap.sections)
        if groups > group_budget:
            reject(f"directional groups {groups} exceed budget {group_budget}", "BLOCKED_RESOURCE")
        net = compile_traffic(roadmap, signals=False)
        if landscape is None:

            def polygons(rects, prefix):
                return tuple(
                    Polygon(
                        f"{prefix}:{i}",
                        ((r.xmin, r.ymin), (r.xmax, r.ymin), (r.xmax, r.ymax), (r.xmin, r.ymax)),
                    )
                    for i, r in enumerate(rects)
                )

            landscape = Landscape(
                "restored_rectangle_authority",
                0,
                roadmap.terrain,
                polygons(roadmap.terrain.water, "water"),
                polygons(roadmap.terrain.protected, "protected"),
            )
        _immutable(landscape)
        if landscape.terrain != roadmap.terrain:
            reject("landscape and road terrain differ")
        # Canonical tuple registries ensure input-list order is not a model choice.
        roadmap = RoadMap(
            roadmap.style,
            roadmap.terrain,
            tuple(sorted(roadmap.nodes, key=lambda n: n.id)),
            tuple(sorted(roadmap.sections, key=lambda s: s.id)),
            tuple(sorted(roadmap.rejected)),
        )
        for region in landscape.water + landscape.protected:
            AreaAccess(region.points)
        for s in roadmap.sections:
            if s.failure_group is not None and (
                not isinstance(s.failure_group, str) or not s.failure_group
            ):
                reject("invalid physical failure_group")
            if s.facility != "surface" and not s.failure_group:
                reject("structure requires a physical failure_group")
            xy = tuple(p[:2] for p in s.points)
            if any(
                not (0 <= p[0] <= landscape.size_m and 0 <= p[1] <= landscape.size_m) for p in xy
            ):
                reject("section outside terrain")
            if s.facility == "surface":
                if any(abs(p[2] - elevation(roadmap.terrain, *p[:2])) > 1e-7 for p in s.points):
                    reject("surface elevation differs from authoritative terrain")
                _, length, grade = ground_profile(
                    roadmap.terrain, (xy[0], xy[-1]) if _straight(s.points) else xy
                )
            else:
                _, length, grade = deck_profile(s.points)
            if not math.isclose(length, s.length_m, rel_tol=1e-6, abs_tol=1e-6):
                reject("section length inconsistent with its geometry")
            if not math.isclose(grade, s.max_grade, rel_tol=1e-6, abs_tol=1e-8):
                reject("section grade inconsistent with its geometry")
            _self_crossings(s)
            if s.facility != "surface":
                gap = minimum_ground_gap(roadmap.terrain, s.points)
                if gap < -1e-8 or (s.facility == "mainline" and gap < 5.0 - 1e-6):
                    reject("buried or insufficient-clearance deck", "PHYSICAL_INFEASIBLE")
            width = (3.5 * (s.forward_lanes + s.backward_lanes) + 2.0) / 2
            for a, b in zip(xy, xy[1:]):
                if not segment_clear(a, b, landscape.protected, width):
                    reject("road footprint intersects protected polygon", "PHYSICAL_INFEASIBLE")
                if s.facility in ("surface", "ramp") and not segment_clear(
                    a, b, landscape.water, width
                ):
                    reject("road footprint intersects water polygon", "PHYSICAL_INFEASIBLE")
        _crossings(roadmap)
        blocks = tuple(sorted(blocks, key=lambda b: b.id))
        _unique(blocks, "block")
        ground_pairs = {
            frozenset((s.start, s.end))
            for s in roadmap.sections
            if s.facility in ("surface", "bridge")
        }
        for b in blocks:
            if (
                not all(map(math.isfinite, (*b.xy, b.area_m2, b.perimeter_m)))
                or len(b.xy) != 2
                or b.area_m2 <= 0
                or b.perimeter_m <= 0
            ):
                reject("invalid block geometry")
            if any(k not in nodes or nodes[k].layer != 0 for k in b.boundary):
                reject("face graph requires registered ground boundary nodes")
            if len(b.boundary) < 3 or any(
                frozenset((a, c)) not in ground_pairs for a, c in edges(b.boundary)
            ):
                reject("face boundary lacks registered ground section")
            points = tuple(nodes[k].xyz[:2] for k in b.boundary)
            area = 0.5 * math.fsum(a[0] * c[1] - c[0] * a[1] for a, c in edges(points))
            perimeter = math.fsum(math.dist(a, c) for a, c in edges(points))
            if not math.isclose(perimeter, b.perimeter_m, rel_tol=1e-8, abs_tol=1e-5):
                reject("block perimeter inconsistent with boundary")
            if b.housing_capacity or b.job_capacity:
                AreaAccess(points)
                if not polygon_clear(points, landscape.water + landscape.protected):
                    reject("developed face intersects exclusion polygon", "PHYSICAL_INFEASIBLE")
            if not math.isclose(area, b.area_m2, rel_tol=1e-8, abs_tol=1e-5):
                reject("block area inconsistent with boundary")
            if any(
                isinstance(v, bool) or not isinstance(v, int) or v < 0
                for v in (b.residents, b.jobs, b.housing_capacity, b.job_capacity)
            ):
                reject("nonnegative integer block stocks required")
            if b.residents > b.housing_capacity or b.jobs > b.job_capacity:
                reject("block stock exceeds capacity", "PHYSICAL_INFEASIBLE")
        portals = tuple(sorted(portals, key=lambda p: p.id))
        _unique(portals, "portal")
        for p in portals:
            if (
                p.block_id not in {b.id for b in blocks}
                or p.node_id not in nodes
                or nodes[p.node_id].layer != 0
            ):
                reject("portal requires registered block and ground node")
        placed = sum(b.residents for b in blocks)
        requested_population = (
            placed + unplaced_residents if requested_population is None else requested_population
        )
        if (
            any(
                isinstance(v, bool) or not isinstance(v, int) or v < 0
                for v in (requested_population, unplaced_residents)
            )
            or requested_population != placed + unplaced_residents
        ):
            reject("population ledger inconsistent")
        faces = FaceGraph(
            tuple(
                (s.id, s.start, s.end)
                for s in roadmap.sections
                if s.facility in ("surface", "bridge")
            ),
            blocks,
        )
        # Recompile canonical registry; the fingerprint includes turns and engineering priors.
        net = compile_traffic(roadmap, signals=False)
        landscape = Landscape(
            landscape.kind,
            landscape.seed,
            landscape.terrain,
            tuple(sorted(landscape.water, key=lambda p: p.name)),
            tuple(sorted(landscape.protected, key=lambda p: p.name)),
        )
        payload = dict(
            schema="metroflow_city_v1",
            roadmap=asdict(roadmap),
            landscape=asdict(landscape),
            blocks=[asdict(b) for b in blocks],
            portals=[asdict(p) for p in portals],
            requested_population=requested_population,
            unplaced_residents=unplaced_residents,
            transport_fingerprint=net.map_fingerprint,
        )
        identity = hashlib.sha256(
            json.dumps(payload, sort_keys=True, allow_nan=False).encode()
        ).hexdigest()
        return CitySnapshot(
            roadmap,
            landscape,
            faces,
            net,
            portals,
            requested_population,
            unplaced_residents,
            identity,
        )
    except CityContractError:
        raise
    except (ValueError, KeyError, TypeError, OverflowError) as exc:
        raise CityContractError("MODEL_ERROR", str(exc)) from exc


def load_city(data, *, group_budget=10000):
    """Read a V1 snapshot or the existing atlas JSON. Never trust derived graphs."""

    def terrain(d):
        return Terrain(
            d["n"],
            d["spacing_m"],
            tuple(d["heights_m"]),
            tuple(Rect(**r) for r in d.get("water", ())),
            tuple(Rect(**r) for r in d.get("protected", ())),
            tuple(d.get("bridge_rows", ())),
        )

    try:
        r, landscape_data = data["roadmap"], data["landscape"]
        road = RoadMap(
            r["style"],
            terrain(r["terrain"]),
            tuple(Junction(n["id"], tuple(n["xyz"]), n["layer"]) for n in r["nodes"]),
            tuple(
                Section(**(s | {"points": tuple(tuple(p) for p in s["points"])}))
                for s in r["sections"]
            ),
            tuple(tuple(x) for x in r.get("rejected", ())),
        )
        land = Landscape(
            landscape_data["kind"],
            landscape_data["seed"],
            terrain(landscape_data["terrain"]),
            tuple(
                Polygon(p["name"], tuple(tuple(v) for v in p["points"]))
                for p in landscape_data["water"]
            ),
            tuple(
                Polygon(p["name"], tuple(tuple(v) for v in p["points"]))
                for p in landscape_data["protected"]
            ),
        )
        blocks = tuple(
            Block(**(b | {"boundary": tuple(b["boundary"]), "xy": tuple(b["xy"])}))
            for b in data["blocks"]
        )
        summary = data.get("summary", data)
        city = compile_city(
            road,
            land,
            blocks,
            tuple(PortalRef(**p) for p in data.get("portals", ())),
            requested_population=summary.get("requested_population"),
            unplaced_residents=summary.get("unplaced_residents", 0),
            group_budget=group_budget,
        )
        if "schema" in data and data["schema"] != "metroflow_city_v1":
            reject("unsupported city schema")
        if data.get("identity", city.identity) != city.identity:
            reject("snapshot identity mismatch")
        return city
    except CityContractError:
        raise
    except (ValueError, KeyError, TypeError, OverflowError) as exc:
        raise CityContractError("MODEL_ERROR", str(exc)) from exc


def iter_validation_matrix():
    """The six authored 8km city cases x seeds 7/17/41, resolution 42."""
    from ..terrain_city.network import generate

    cases = (
        ("planned_plain", "planned", "flat"),
        ("polycentric_river", "polycentric", "river"),
        ("radial_plain", "radial", "flat"),
        ("coastal_port", "polycentric", "coast"),
        ("valley_city", "corridor", "valley"),
        ("lake_city", "polycentric", "lake"),
    )
    for name, style, terrain in cases:
        for seed in (7, 17, 41):
            try:
                atlas = generate(style, terrain, 8000.0, 42, seed)
                snapshot = load_city(json.loads(json.dumps(asdict(atlas), allow_nan=False)))
                restored = load_city(json.loads(json.dumps(snapshot.to_dict(), allow_nan=False)))
                if restored.identity != snapshot.identity:
                    reject("JSON roundtrip changed identity")
                yield dict(case=name, seed=seed, **snapshot.report())
            except CityContractError as exc:
                yield dict(case=name, seed=seed, status=exc.status, reason=exc.reason)


def validation_matrix():
    return list(iter_validation_matrix())
