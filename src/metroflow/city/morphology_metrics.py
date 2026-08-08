"""Dependency-free morphometrics for generated physical street networks."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Protocol

from metroflow.map.road_geometry import RoadGeometryCatalog

__all__ = [
    "MeasurementSpec",
    "StreetNetworkMorphometrics",
    "UnmeasurableNetworkError",
    "compute_street_network_morphometrics",
]


class MeasurementSpec(str, Enum):
    """Which definition a measurement implements. There is no default.

    A boolean called `simplify_interstitial_nodes` could not say which of
    Boeing's two published statistics it meant, and the repo ended up computing
    neither: it contracted degree-2 chains like `H_o` but then fed the histogram
    one bearing per member edge like `H_w`, unweighted. Two callers read the same
    function under one name and got answers that disagreed on 8 of 30 verdicts.
    """

    BOEING_2019_HO = "BOEING_2019_HO"
    """OSMnx-parity: one endpoint-chord bearing per simplified edge, unweighted,
    self-loop bearings excluded. Verified against `osmnx==2.1.1` by
    `tests/test_morphology_oracle_parity.py`."""

    RUNTIME_COMPILED_DIAGNOSTIC = "RUNTIME_COMPILED_DIAGNOSTIC"
    """Every compiled node and centerline as-is, with no contraction. This is
    what the runtime metadata path has always reported; node spacing rather than
    morphology moves its degree and dead-end figures, so it is a diagnostic and
    must not be compared against the Boeing corpus."""


class UnmeasurableNetworkError(ValueError):
    """The network has no streets this specification can measure.

    Raised instead of returning a number. The prior code divided by
    `max(total, 1e-12)` and reported a circuity of 4e14 for a bare ring, which
    reads as a measurement and silently satisfies a `<= 1.3644` upper bound by
    being enormous rather than by being right.
    """


class _TopologyLike(Protocol):
    nodes: tuple[Any, ...]
    links: tuple[Any, ...]
    road_geometry: RoadGeometryCatalog | None


@dataclass(frozen=True, slots=True)
class StreetNetworkMorphometrics:
    orientation_entropy: float
    orientation_order: float
    median_segment_length_m: float
    circuity: float
    mean_node_degree: float
    dead_end_share: float
    four_way_share: float
    physical_segment_count: int
    measurement_spec: str = MeasurementSpec.RUNTIME_COMPILED_DIAGNOSTIC.value
    # Junction-free rings have no endpoint to anchor a chain, so OSMnx's
    # `simplify_graph` removes them outright. Matching that costs real street
    # length, and length that leaves a measurement without being reported is the
    # kind of silent loss this instrument exists to catch.
    dropped_ring_count: int = 0
    dropped_ring_length_m: float = 0.0
    orientation_bin_count: int = 36
    evidence_status: str = "diagnostic"

    def as_dict(self) -> Mapping[str, int | float | str]:
        return MappingProxyType(
            {
                "orientation_entropy": self.orientation_entropy,
                "orientation_order": self.orientation_order,
                "median_segment_length_m": self.median_segment_length_m,
                "circuity": self.circuity,
                "mean_node_degree": self.mean_node_degree,
                "dead_end_share": self.dead_end_share,
                "four_way_share": self.four_way_share,
                "physical_segment_count": self.physical_segment_count,
                "measurement_spec": self.measurement_spec,
                "dropped_ring_count": self.dropped_ring_count,
                "dropped_ring_length_m": self.dropped_ring_length_m,
                "orientation_bin_count": self.orientation_bin_count,
                "evidence_status": self.evidence_status,
            }
        )


def compute_street_network_morphometrics(
    topology: _TopologyLike,
    *,
    spec: MeasurementSpec,
) -> StreetNetworkMorphometrics:
    """Compute street morphometrics under an explicitly named specification.

    `spec` is required. The previous signature defaulted to a boolean, so a bare
    call silently chose a definition, and the two live call sites chose
    differently while comparing their results against the same reference corpus.
    """

    spec = MeasurementSpec(spec)
    geometry = topology.road_geometry
    if not isinstance(geometry, RoadGeometryCatalog):
        raise ValueError("road_geometry is required for street-network morphometrics")
    centerlines = tuple(geometry.centerlines)
    if not centerlines:
        raise ValueError("road_geometry must contain at least one centerline")

    if spec is MeasurementSpec.BOEING_2019_HO:
        segments, degree_by_node_id, dropped = _simplified_segments(topology, geometry)
    else:
        segments, degree_by_node_id, dropped = _compiled_segments(topology, geometry)
    dropped_ring_count, dropped_ring_length_m = dropped

    orientation_counts = [0] * 36
    lengths: list[float] = []
    straight_lengths: list[float] = []
    for arc_length_m, start, end, bearing_pairs in segments:
        for left, right in bearing_pairs:
            dx = float(right[0]) - float(left[0])
            dy = float(right[1]) - float(left[1])
            if math.hypot(dx, dy) <= 0.0:
                continue
            bearing = math.degrees(math.atan2(dx, dy)) % 360.0
            for value in (bearing, (bearing + 180.0) % 360.0):
                orientation_counts[int(((value + 5.0) % 360.0) // 10.0)] += 1
        straight = math.hypot(float(end[0]) - float(start[0]), float(end[1]) - float(start[1]))
        lengths.append(float(arc_length_m))
        if straight <= 0.0:
            # A self-loop contributes length with a zero chord. OSMnx's
            # `circuity_avg` does exactly this, so excluding it here would move
            # us away from the reference rather than toward it.
            continue
        straight_lengths.append(straight)
    if not lengths:
        raise UnmeasurableNetworkError(
            f"{spec.value} measured no streets in this network"
            + (
                f"; {dropped_ring_count} junction-free ring(s) totalling "
                f"{dropped_ring_length_m:.1f} m were removed, as OSMnx "
                "`simplify_graph` removes them"
                if dropped_ring_count
                else ""
            )
        )

    total_orientations = sum(orientation_counts)
    if total_orientations == 0:
        raise UnmeasurableNetworkError(
            f"{spec.value} found no orientable streets: every measured segment "
            "is a self-loop, whose bearing is undefined"
        )
    entropy = -sum(
        probability * math.log(probability)
        for count in orientation_counts
        if count
        for probability in (count / total_orientations,)
    )
    grid_entropy = math.log(4.0)
    maximum_entropy = math.log(36.0)
    orientation_order = 1.0 - (
        (entropy - grid_entropy) / (maximum_entropy - grid_entropy)
    ) ** 2
    orientation_order = min(max(orientation_order, 0.0), 1.0)

    straight_total = sum(straight_lengths)
    if straight_total <= 0.0:
        raise UnmeasurableNetworkError(
            f"{spec.value} cannot define circuity: every measured segment has a "
            "zero-length chord, so the denominator is zero"
        )

    degrees = tuple(degree_by_node_id.values())
    node_count = max(len(degrees), 1)
    return StreetNetworkMorphometrics(
        orientation_entropy=float(entropy),
        orientation_order=float(orientation_order),
        median_segment_length_m=float(statistics.median(lengths)),
        circuity=float(sum(lengths) / straight_total),
        mean_node_degree=float(sum(degrees) / node_count),
        dead_end_share=float(sum(degree == 1 for degree in degrees) / node_count),
        four_way_share=float(sum(degree == 4 for degree in degrees) / node_count),
        physical_segment_count=len(lengths),
        measurement_spec=spec.value,
        dropped_ring_count=dropped_ring_count,
        dropped_ring_length_m=float(dropped_ring_length_m),
    )


_PointM = tuple[float, float]
# One measured street: arc length in meters, chord endpoints, and the sub-segment
# endpoint pairs whose bearings enter the orientation histogram.
_Segment = tuple[float, _PointM, _PointM, tuple[tuple[_PointM, _PointM], ...]]


def _undirected_edges(
    topology: _TopologyLike,
    geometry: RoadGeometryCatalog,
) -> tuple[tuple[int, int, float], ...]:
    """Collapse directed link pairs into unique undirected physical segments."""

    link_by_id = {int(link.link_id): link for link in topology.links}
    seen_pairs: set[tuple[int, int, int]] = set()
    edges: list[tuple[int, int, float]] = []
    for assignment in geometry.assignments:
        link = link_by_id.get(int(assignment.link_id))
        if link is None:
            raise ValueError(f"geometry assignment references missing link {assignment.link_id}")
        left = min(int(link.src_node_id), int(link.dst_node_id))
        right = max(int(link.src_node_id), int(link.dst_node_id))
        geometry_id = int(assignment.geometry_id)
        key = (geometry_id, left, right)
        if key in seen_pairs:
            continue
        seen_pairs.add(key)
        edges.append((left, right, float(geometry.centerline(geometry_id).length_m)))
    return tuple(edges)


def _compiled_segments(
    topology: _TopologyLike,
    geometry: RoadGeometryCatalog,
) -> tuple[tuple[_Segment, ...], dict[int, int]]:
    """Measure every compiled node and centerline as-is."""

    degree_by_node_id = {int(node.node_id): 0 for node in topology.nodes}
    for left, right, _length_m in _undirected_edges(topology, geometry):
        degree_by_node_id[left] = degree_by_node_id.get(left, 0) + 1
        degree_by_node_id[right] = degree_by_node_id.get(right, 0) + 1

    segments = tuple(
        (
            float(centerline.length_m),
            centerline.points_m[0],
            centerline.points_m[-1],
            ((centerline.points_m[0], centerline.points_m[-1]),),
        )
        for centerline in geometry.centerlines
    )
    return segments, degree_by_node_id, (0, 0.0)


def _simplified_segments(
    topology: _TopologyLike,
    geometry: RoadGeometryCatalog,
) -> tuple[tuple[_Segment, ...], dict[int, int]]:
    """Contract degree-2 interstitial nodes, as OSMnx `simplify_graph` does.

    Chains between junctions or dead ends become a single measured street whose
    length is the summed arc length of its members. Interstitial and isolated
    nodes leave the measured node set entirely.
    """

    point_by_node_id = {
        int(node.node_id): (float(node.x), float(node.y)) for node in topology.nodes
    }
    edges = _undirected_edges(topology, geometry)

    compiled_degree: dict[int, int] = {}
    adjacency: dict[int, list[int]] = {}
    for index, (left, right, _length_m) in enumerate(edges):
        for node_id in (left, right):
            compiled_degree[node_id] = compiled_degree.get(node_id, 0) + 1
            adjacency.setdefault(node_id, []).append(index)

    segments: list[_Segment] = []
    degree_by_node_id: dict[int, int] = {}
    consumed: set[int] = set()

    def _other(edge_index: int, node_id: int) -> int:
        left, right, _length_m = edges[edge_index]
        return right if left == node_id else left

    def _emit(
        start_node_id: int,
        end_node_id: int,
        arc_length_m: float,
        members: list[int],
    ) -> None:
        start = point_by_node_id[start_node_id]
        end = point_by_node_id[end_node_id]
        # Boeing H_o: ONE bearing per simplified edge, from its endpoint chord --
        # not one per member edge, which is what made this metric depend on how a
        # polyline happened to be split. A self-loop's bearing is undefined, so it
        # contributes none, exactly as `osmnx.bearing._extract_edge_bearings`
        # skips `u == v`.
        bearing_pairs = () if start_node_id == end_node_id else ((start, end),)
        segments.append((arc_length_m, start, end, bearing_pairs))
        for node_id in (start_node_id, end_node_id):
            degree_by_node_id[node_id] = degree_by_node_id.get(node_id, 0) + 1

    # OSMnx `_is_endpoint` rule 3: a node is interstitial only when it has
    # exactly two DISTINCT neighbours and degree 2. Counting incidences alone
    # made both ends of a parallel pair look interstitial, so two roads between
    # one pair of junctions were contracted into a closed loop -- which is how a
    # dual carriageway became a zero-chord segment with circuity 4.66e14.
    neighbours: dict[int, set[int]] = {}
    for left, right, _length_m in edges:
        neighbours.setdefault(left, set()).add(right)
        neighbours.setdefault(right, set()).add(left)

    def _is_interstitial(node_id: int) -> bool:
        if node_id in neighbours.get(node_id, ()):  # rule 1: self-loop
            return False
        return compiled_degree.get(node_id, 0) == 2 and len(neighbours.get(node_id, ())) == 2

    anchors = sorted(node_id for node_id in compiled_degree if not _is_interstitial(node_id))
    for anchor in anchors:
        for start_edge in adjacency[anchor]:
            if start_edge in consumed:
                continue
            arc_length_m = 0.0
            members: list[int] = []
            previous_node_id = anchor
            edge_index = start_edge
            while True:
                consumed.add(edge_index)
                members.append(edge_index)
                arc_length_m += edges[edge_index][2]
                next_node_id = _other(edge_index, previous_node_id)
                if not _is_interstitial(next_node_id):
                    break
                onward = [
                    candidate
                    for candidate in adjacency[next_node_id]
                    if candidate not in consumed
                ]
                if not onward:
                    break
                edge_index = onward[0]
                previous_node_id = next_node_id
            _emit(anchor, next_node_id, arc_length_m, members)

    # Anything left is a ring of interstitial nodes with no endpoint to anchor a
    # chain. OSMnx's `simplify_graph` removes such a component outright -- a bare
    # 4-node ring goes to zero nodes and zero edges -- so matching the reference
    # means dropping it here too. It is counted and its length reported, because
    # street length leaving a measurement unannounced is precisely the class of
    # silent loss this instrument exists to detect.
    dropped_ring_count = 0
    dropped_ring_length_m = 0.0
    for index, (left, _right, _length_m) in enumerate(edges):
        if index in consumed:
            continue
        dropped_ring_count += 1
        previous_node_id = left
        edge_index = index
        while True:
            consumed.add(edge_index)
            dropped_ring_length_m += edges[edge_index][2]
            next_node_id = _other(edge_index, previous_node_id)
            onward = [
                candidate
                for candidate in adjacency[next_node_id]
                if candidate not in consumed
            ]
            if not onward:
                break
            edge_index = onward[0]
            previous_node_id = next_node_id

    return tuple(segments), degree_by_node_id, (dropped_ring_count, dropped_ring_length_m)
