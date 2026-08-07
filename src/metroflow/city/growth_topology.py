"""Stable identity for grown streets, so geometry stops defining topology.

The generator used to record a junction by placing two vertices at the same
coordinates and trusting a later pass to notice. It did not: `_branch_pass`
interpolated a branch anchor inside a parent segment and never inserted it into
the parent's polyline, while the compiler derived junctions only from vertices
whose coordinates rounded into the same 1 m cell. Both children registered the
anchor and the parent did not, losing 24.4% of the edge set on a map the
morphology envelope happily accepted.

An earlier repair -- snapping a contact to the true projection on the target
segment -- made it worse, because the compiler matched shared coordinates and a
mid-segment contact left the target with no matching point. The lesson is that
"remember to keep the two representations in step" is not a design. Here a
junction is a node id, minted where the junction is created, and shared by
everything incident to it; a split inserts that id into the street it splits, in
the same call. The compiler consumes incidence and never compares coordinates.

Two consequences worth stating:

- Every polyline vertex is a node. That is not the same as every vertex being a
  junction: a junction is a node more than one street is incident to, or a
  street's endpoint. Interior vertices remain geometry.
- Positions are addressed by ARC LENGTH, never by (segment index, offset). Arc
  length is invariant under splitting, so an anchor computed before a mutation
  still means the same place afterwards. Positional indices do not, which is the
  instability that made the old `vertex_owner` bookkeeping fragile.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Sequence

__all__ = [
    "CoincidentNodeError",
    "NodeId",
    "StreetId",
    "StreetTopologyBuilder",
    "WELD_TOLERANCE_M",
]

NodeId = int
StreetId = int

PointM = tuple[float, float]

# Two positions closer than this are the same junction. It is bounded geometry
# mutation, and declared as such: an arriving street's terminus can be placed up
# to this far from its true projection. That is the same class of error as the
# 0.8 m coordinate merge it replaces, 3.2x smaller and deliberate rather than
# incidental.
WELD_TOLERANCE_M = 0.25


class CoincidentNodeError(ValueError):
    """Two distinct nodes occupy the same point.

    The compiler no longer merges by coordinate, so nothing downstream will
    quietly reconcile these. Left alone they are two unlinked junctions on top of
    each other -- structurally the defect this module exists to remove, arrived
    at from the other direction.
    """


@dataclass(slots=True)
class _Street:
    street_id: StreetId
    node_ids: list[NodeId]
    # Grade. Two streets that share a coordinate on DIFFERENT layers cross; they
    # do not meet. Without this the coincidence invariant would make grade
    # separation unrepresentable, and RAMP and BRIDGE are exactly what the
    # generator still has to grow.
    layer: int = 0
    metadata: dict = field(default_factory=dict)


class StreetTopologyBuilder:
    """Mints node and street ids, and records incidence as it happens."""

    def __init__(self) -> None:
        self._points: list[PointM] = []
        self._incident: list[set[StreetId]] = []
        self._streets: list[_Street] = []

    # --- construction ------------------------------------------------------

    def open_street(
        self,
        *,
        points: Sequence[PointM],
        start_node_id: NodeId | None = None,
        layer: int = 0,
        metadata: dict | None = None,
    ) -> StreetId:
        """Create a street through `points`, optionally starting at a known node.

        Passing `start_node_id` is how a branch binds to the junction its parent
        was split at: the child does not create a second node at the same place,
        it reuses the one that already exists.
        """

        if len(points) < 2:
            raise ValueError("a street needs at least two points")

        street_id = len(self._streets)
        node_ids: list[NodeId] = []
        for index, point in enumerate(points):
            if index == 0 and start_node_id is not None:
                self._require_node(start_node_id)
                node_ids.append(start_node_id)
                continue
            node_ids.append(self._mint_node(point))

        self._streets.append(
            _Street(street_id, node_ids, int(layer), dict(metadata or {}))
        )
        for node_id in node_ids:
            self._incident[node_id].add(street_id)
        return street_id

    def extend_street(self, street_id: StreetId, point: PointM) -> NodeId:
        street = self._require_street(street_id)
        node_id = self._mint_node(point)
        street.node_ids.append(node_id)
        self._incident[node_id].add(street_id)
        return node_id

    def extend_street_to_node(self, street_id: StreetId, node_id: NodeId) -> NodeId:
        """Terminate a street ON an existing node, rather than beside it.

        Without this, `contact()` is inert: it splits the target correctly and
        the arriving tip still ends at its own separate vertex a few centimetres
        away, so the two streets are drawn meeting and remain unconnected. That
        is the defect this module exists to remove, so the API has to make
        finishing on a node possible.
        """

        street = self._require_street(street_id)
        self._require_node(node_id)
        if street.node_ids[-1] == node_id:
            return node_id
        street.node_ids.append(node_id)
        self._incident[node_id].add(street_id)
        return node_id

    # --- splitting ---------------------------------------------------------

    def split_at_arc_length(self, street_id: StreetId, arc_length_m: float) -> NodeId:
        """Return the node at `arc_length_m` along the street, creating it if needed.

        Idempotent: arc length is split-invariant, so a repeated call resolves to
        the same point, finds the vertex already there and returns it. That is
        what lets both siblings of one branch anchor bind to a single junction
        without either of them knowing about the other.
        """

        street = self._require_street(street_id)
        arc_length_m = float(arc_length_m)
        if not math.isfinite(arc_length_m) or arc_length_m < 0.0:
            raise ValueError(f"arc_length_m must be finite and >= 0, got {arc_length_m!r}")

        total = self.arc_length_of(street_id)
        if arc_length_m > total + WELD_TOLERANCE_M:
            raise ValueError(
                f"arc_length_m {arc_length_m} exceeds street {street_id} length {total}"
            )

        travelled = 0.0
        for index in range(len(street.node_ids) - 1):
            left = self._points[street.node_ids[index]]
            right = self._points[street.node_ids[index + 1]]
            span = math.dist(left, right)
            if span <= 0.0:
                continue
            # Advance on the segment's own extent, not on a tolerance-shifted
            # one. Comparing against `arc_length_m - WELD_TOLERANCE_M` meant a
            # street built from sub-tolerance segments never satisfied the
            # condition, so every request fell out of the loop and returned the
            # far end regardless of what was asked for.
            if travelled + span < arc_length_m:
                travelled += span
                continue

            remainder = arc_length_m - travelled
            # Both weld checks can hold at once when span <= 2 * tolerance.
            # Returning the first match handed back the left vertex even when
            # the request was nearer the right one, so choose by distance.
            left_close = remainder <= WELD_TOLERANCE_M
            right_close = span - remainder <= WELD_TOLERANCE_M
            if left_close and right_close:
                nearer = index if remainder <= span - remainder else index + 1
                return street.node_ids[nearer]
            if left_close:
                return street.node_ids[index]
            if right_close:
                return street.node_ids[index + 1]

            ratio = remainder / span
            point = (
                left[0] + ratio * (right[0] - left[0]),
                left[1] + ratio * (right[1] - left[1]),
            )
            node_id = self._mint_node(point)
            street.node_ids.insert(index + 1, node_id)
            self._incident[node_id].add(street_id)
            return node_id

        return street.node_ids[-1]

    def contact(
        self,
        street_id: StreetId,
        *,
        point: PointM,
        tolerance_m: float,
    ) -> NodeId | None:
        """Bind `point` onto a street at its true projection, or return None.

        The projection is inserted into the target's own polyline, so the target
        genuinely passes through the junction. Snapping to the target's nearest
        existing vertex instead -- the old behaviour -- moved 98.6% of contacts
        by up to 64.8 m and wrote that error into the compiled link's length.
        """

        street = self._require_street(street_id)
        best: tuple[float, float] | None = None
        travelled = 0.0
        for index in range(len(street.node_ids) - 1):
            left = self._points[street.node_ids[index]]
            right = self._points[street.node_ids[index + 1]]
            span = math.dist(left, right)
            if span <= 0.0:
                continue
            distance, along = _project(point, left, right)
            if best is None or distance < best[0]:
                best = (distance, travelled + along)
            travelled += span

        if best is None or best[0] > float(tolerance_m):
            return None
        return self.split_at_arc_length(street_id, best[1])

    # --- queries -----------------------------------------------------------

    def point_of(self, node_id: NodeId) -> PointM:
        self._require_node(node_id)
        return self._points[node_id]

    def node_ids_of(self, street_id: StreetId) -> tuple[NodeId, ...]:
        return tuple(self._require_street(street_id).node_ids)

    def points_of(self, street_id: StreetId) -> tuple[PointM, ...]:
        return tuple(self._points[node_id] for node_id in self._require_street(street_id).node_ids)

    def incident_street_ids(self, node_id: NodeId) -> tuple[StreetId, ...]:
        self._require_node(node_id)
        return tuple(sorted(self._incident[node_id]))

    def arc_length_of(self, street_id: StreetId) -> float:
        points = self.points_of(street_id)
        return sum(math.dist(a, b) for a, b in zip(points, points[1:]))

    def metadata_of(self, street_id: StreetId) -> dict:
        return self._require_street(street_id).metadata

    @property
    def street_ids(self) -> tuple[StreetId, ...]:
        return tuple(street.street_id for street in self._streets)

    @property
    def node_count(self) -> int:
        return len(self._points)

    def junction_node_ids(self) -> tuple[NodeId, ...]:
        """Nodes where the graph actually branches: shared, or a street's end."""

        endpoints = {
            node_id
            for street in self._streets
            for node_id in (street.node_ids[0], street.node_ids[-1])
        }
        return tuple(
            sorted(
                node_id
                for node_id in range(len(self._points))
                if len(self._incident[node_id]) > 1 or node_id in endpoints
            )
        )

    # --- invariants --------------------------------------------------------

    def layers_of(self, node_id: NodeId) -> frozenset[int]:
        """Grades the streets through this node occupy."""

        self._require_node(node_id)
        return frozenset(self._streets[street_id].layer for street_id in self._incident[node_id])

    def assert_no_coincident_nodes(self, *, tolerance_m: float = WELD_TOLERANCE_M) -> None:
        """Fail loudly rather than let two junctions stack at one location.

        Only within a grade. Two nodes at the same coordinate on different
        layers are a bridge over a road: they cross and do not meet, and
        collapsing them would be the opposite error to the one this guards.
        """

        cell = max(float(tolerance_m), 1e-9)
        buckets: dict[tuple[int, int], list[NodeId]] = {}
        for node_id, (x, y) in enumerate(self._points):
            key = (math.floor(x / cell), math.floor(y / cell))
            layers = self.layers_of(node_id)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for other in buckets.get((key[0] + dx, key[1] + dy), ()):
                        if math.dist(self._points[other], (x, y)) > tolerance_m:
                            continue
                        if not (layers & self.layers_of(other)):
                            continue  # grade-separated crossing, not a junction
                        raise CoincidentNodeError(
                            f"nodes {other} and {node_id} are both at "
                            f"{self._points[other]!r} on layer(s) "
                            f"{sorted(layers & self.layers_of(other))}; "
                            "a junction must be one node"
                        )
            buckets.setdefault(key, []).append(node_id)

    # --- internals ---------------------------------------------------------

    def _mint_node(self, point: PointM) -> NodeId:
        node_id = len(self._points)
        self._points.append((float(point[0]), float(point[1])))
        self._incident.append(set())
        return node_id

    def _require_node(self, node_id: NodeId) -> None:
        if not 0 <= node_id < len(self._points):
            raise ValueError(f"unknown node id {node_id!r}")

    def _require_street(self, street_id: StreetId) -> _Street:
        if not 0 <= street_id < len(self._streets):
            raise ValueError(f"unknown street id {street_id!r}")
        return self._streets[street_id]


def _project(point: PointM, left: PointM, right: PointM) -> tuple[float, float]:
    """Distance from `point` to the segment, and how far along the foot lies."""

    dx = right[0] - left[0]
    dy = right[1] - left[1]
    span = dx * dx + dy * dy
    if span <= 0.0:
        return math.dist(point, left), 0.0
    ratio = ((point[0] - left[0]) * dx + (point[1] - left[1]) * dy) / span
    ratio = min(max(ratio, 0.0), 1.0)
    foot = (left[0] + ratio * dx, left[1] + ratio * dy)
    return math.dist(point, foot), ratio * math.sqrt(span)


def iter_chains(
    builder: StreetTopologyBuilder,
    street_ids: Iterable[StreetId] | None = None,
) -> list[tuple[StreetId, tuple[NodeId, ...]]]:
    """Split each street into junction-to-junction chains, by incidence only.

    No coordinate comparison anywhere: a chain ends where another street is
    incident, which is recorded, not inferred.
    """

    junctions = set(builder.junction_node_ids())
    chains: list[tuple[StreetId, tuple[NodeId, ...]]] = []
    for street_id in builder.street_ids if street_ids is None else street_ids:
        node_ids = builder.node_ids_of(street_id)
        current = [node_ids[0]]
        for node_id in node_ids[1:]:
            current.append(node_id)
            if node_id in junctions and len(current) >= 2:
                chains.append((street_id, tuple(current)))
                current = [node_id]
        if len(current) >= 2:
            chains.append((street_id, tuple(current)))
    return chains
