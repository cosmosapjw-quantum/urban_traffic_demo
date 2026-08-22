"""Deterministic offline OSM XML import into Metroflow-owned map contracts."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from dataclasses import dataclass, field
from numbers import Real
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, MutableMapping
from xml.etree import ElementTree

from metroflow.city.graph import (
    Node,
    RoadClass,
    RoadLink,
    validate_road_network_topology,
)
from metroflow.map.road_geometry import (
    CenterlineSource,
    LinkGeometryAssignment,
    RoadCenterline,
    RoadGeometryCatalog,
)
from metroflow.map.section_compiler import RoadSectionCatalog, compile_road_sections

__all__ = [
    "OSMImportConfig",
    "OSMImportResult",
    "UnsupportedOSMTagError",
    "import_osm_xml_file",
    "import_osm_xml_text",
]

_EARTH_RADIUS_M = 6_371_008.8
_HIGHWAY_CLASS = {
    "motorway": RoadClass.EXPRESSWAY,
    "trunk": RoadClass.EXPRESSWAY,
    "primary": RoadClass.ARTERIAL,
    "secondary": RoadClass.COLLECTOR,
    "tertiary": RoadClass.COLLECTOR,
    "residential": RoadClass.LOCAL,
    "unclassified": RoadClass.LOCAL,
    "living_street": RoadClass.LOCAL,
    "service": RoadClass.LOCAL,
    "road": RoadClass.LOCAL,
    "motorway_link": RoadClass.RAMP,
    "trunk_link": RoadClass.RAMP,
    "primary_link": RoadClass.RAMP,
    "secondary_link": RoadClass.RAMP,
    "tertiary_link": RoadClass.RAMP,
}
_LANE_TAGGING_POLICIES = frozenset({"strict", "osm_wiki"})
_LANE_INTERPRETATION_KINDS = (
    "single_track_two_way",
    "oneway_contraflow_ignored",
    "partial_directional",
)
_DEFAULT_SPEED_MPS = {
    RoadClass.LOCAL: 40.0 / 3.6,
    RoadClass.COLLECTOR: 50.0 / 3.6,
    RoadClass.ARTERIAL: 60.0 / 3.6,
    RoadClass.EXPRESSWAY: 100.0 / 3.6,
    RoadClass.RAMP: 60.0 / 3.6,
}


class UnsupportedOSMTagError(ValueError):
    """A recognized OSM tag pattern that this importer cannot represent."""

    def __init__(self, reason_code: str, message: str) -> None:
        self.reason_code = reason_code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class OSMImportConfig:
    """Offline import controls with all spatial values expressed in meters."""

    simplify_tolerance_m: float = 0.0
    clip_bounds_m: tuple[float, float, float, float] | None = None
    capacity_veh_per_lane_per_tick: float = 1.0
    lane_tagging_policy: str = "strict"
    """How to read lane tags that are valid OSM but ambiguous to a strict reader.

    `strict` (default) preserves the specified fail-closed contract. `osm_wiki`
    additionally interprets three documented tagging patterns - single-track
    two-way streets, contraflow lanes on one-way streets, and partially tagged
    directions - which together block 6 of 7 real city extracts. Genuinely
    contradictory or unparseable tags still fail closed under both policies, and
    every interpretation is counted in the result metadata.
    """

    def __post_init__(self) -> None:
        if str(self.lane_tagging_policy) not in _LANE_TAGGING_POLICIES:
            raise ValueError(
                "lane_tagging_policy must be one of "
                f"{sorted(_LANE_TAGGING_POLICIES)}"
            )
        tolerance = _strict_real(self.simplify_tolerance_m, "simplify_tolerance_m")
        capacity = _strict_real(
            self.capacity_veh_per_lane_per_tick,
            "capacity_veh_per_lane_per_tick",
        )
        if not math.isfinite(tolerance) or tolerance < 0.0:
            raise ValueError("simplify_tolerance_m must be finite and >= 0")
        if not math.isfinite(capacity) or capacity <= 0.0:
            raise ValueError(
                "capacity_veh_per_lane_per_tick must be finite and > 0"
            )
        bounds = _normalize_clip_bounds(self.clip_bounds_m)
        object.__setattr__(self, "simplify_tolerance_m", tolerance)
        object.__setattr__(self, "clip_bounds_m", bounds)
        object.__setattr__(self, "capacity_veh_per_lane_per_tick", capacity)


@dataclass(frozen=True, slots=True)
class OSMImportResult:
    """Normalized reference topology and typed static geometry."""

    nodes: tuple[Node, ...]
    links: tuple[RoadLink, ...]
    road_geometry: RoadGeometryCatalog
    road_sections: RoadSectionCatalog
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        nodes = tuple(self.nodes)
        links = tuple(self.links)
        if any(not isinstance(node, Node) for node in nodes):
            raise TypeError("nodes must contain Node instances")
        if any(not isinstance(link, RoadLink) for link in links):
            raise TypeError("links must contain RoadLink instances")
        if not isinstance(self.road_geometry, RoadGeometryCatalog):
            raise TypeError("road_geometry must be a RoadGeometryCatalog")
        if not isinstance(self.road_sections, RoadSectionCatalog):
            raise TypeError("road_sections must be a RoadSectionCatalog")
        object.__setattr__(self, "nodes", nodes)
        object.__setattr__(self, "links", links)
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    @property
    def fingerprint(self) -> str:
        return _sha256_json(
            {
                "nodes": [
                    {
                        "node_id": node.node_id,
                        "x": node.x,
                        "y": node.y,
                        "kind": node.kind.value,
                    }
                    for node in self.nodes
                ],
                "links": [
                    {
                        "link_id": link.link_id,
                        "src_node_id": link.src_node_id,
                        "dst_node_id": link.dst_node_id,
                        "road_class": link.road_class.value,
                        "length_m": link.length_m,
                        "free_flow_speed_mps": link.free_flow_speed_mps,
                        "capacity_veh_per_tick": link.capacity_veh_per_tick,
                        "lanes": link.lanes,
                        "physical_road_id": link.physical_road_id,
                    }
                    for link in self.links
                ],
                "road_geometry_fingerprint": self.road_geometry.fingerprint,
                "road_section_fingerprint": self.road_sections.fingerprint,
                "metadata": dict(self.metadata),
            }
        )


@dataclass(frozen=True, slots=True)
class _OSMNode:
    source_id: int
    lat_deg: float
    lon_deg: float


@dataclass(frozen=True, slots=True)
class _OSMWay:
    source_id: int
    node_refs: tuple[int, ...]
    tags: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class _PhysicalSegment:
    source_way_id: int
    part_index: int
    fragment_index: int
    points_m: tuple[tuple[float, float], ...]
    road_class: RoadClass
    lanes_forward: int
    lanes_backward: int
    speed_mps: float
    layer: int
    start_node_identity: tuple[object, ...]
    end_node_identity: tuple[object, ...]


def import_osm_xml_file(
    path: str | Path,
    *,
    config: OSMImportConfig | None = None,
) -> OSMImportResult:
    """Read exactly one caller-supplied local OSM XML file."""

    source_path = Path(path)
    source_bytes = source_path.read_bytes()
    try:
        text = source_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("OSM XML file must be UTF-8 encoded") from exc
    return _import_osm_xml_text(
        text,
        config=config,
        source_name=source_path.name,
        source_sha256=hashlib.sha256(source_bytes).hexdigest(),
    )


def import_osm_xml_text(
    xml_text: str,
    *,
    config: OSMImportConfig | None = None,
    source_name: str = "<memory>",
) -> OSMImportResult:
    """Parse caller-owned OSM XML text without network or optional packages."""

    if not isinstance(xml_text, str):
        raise TypeError("xml_text must be a string")
    return _import_osm_xml_text(
        xml_text,
        config=config,
        source_name=source_name,
        source_sha256=hashlib.sha256(xml_text.encode("utf-8")).hexdigest(),
    )


def _import_osm_xml_text(
    xml_text: str,
    *,
    config: OSMImportConfig | None,
    source_name: str,
    source_sha256: str,
) -> OSMImportResult:
    if "<!DOCTYPE" in xml_text.upper():
        raise ValueError("OSM XML document type declarations are not allowed")
    resolved_config = config if config is not None else OSMImportConfig()
    if not isinstance(resolved_config, OSMImportConfig):
        raise TypeError("config must be an OSMImportConfig")
    nodes_by_source_id, all_ways, source_version = _parse_osm_xml(xml_text)
    included_ways = tuple(
        way
        for way in all_ways
        if way.tags.get("highway", "") in _HIGHWAY_CLASS
    )
    if not included_ways:
        raise ValueError("OSM XML contains no supported drivable highway ways")
    _validate_way_node_references(included_ways, nodes_by_source_id)

    referenced_node_ids = sorted(
        {node_id for way in included_ways for node_id in way.node_refs}
    )
    unwrapped_lon_by_source_id = _unwrap_longitudes(
        tuple(nodes_by_source_id[node_id] for node_id in referenced_node_ids)
    )
    origin_lat_deg = sum(
        nodes_by_source_id[node_id].lat_deg for node_id in referenced_node_ids
    ) / len(referenced_node_ids)
    origin_lon_deg = sum(
        unwrapped_lon_by_source_id[node_id] for node_id in referenced_node_ids
    ) / len(referenced_node_ids)
    projected_by_source_id = {
        node_id: _project_equirectangular(
            nodes_by_source_id[node_id],
            unwrapped_lon_deg=unwrapped_lon_by_source_id[node_id],
            origin_lat_deg=origin_lat_deg,
            origin_lon_deg=origin_lon_deg,
        )
        for node_id in referenced_node_ids
    }
    shared_node_ids = _shared_node_ids(included_ways)
    lane_interpretations: dict[str, int] = {key: 0 for key in _LANE_INTERPRETATION_KINDS}
    physical_segments = _build_physical_segments(
        ways=included_ways,
        projected_by_source_id=projected_by_source_id,
        shared_node_ids=shared_node_ids,
        config=resolved_config,
        interpretations=lane_interpretations,
    )
    if not physical_segments:
        raise ValueError("OSM import produced no geometry after clipping")
    nodes, links, geometry = _compile_typed_topology(
        physical_segments,
        capacity_veh_per_lane_per_tick=(
            resolved_config.capacity_veh_per_lane_per_tick
        ),
    )
    report = validate_road_network_topology(nodes=nodes, links=links)
    if not report.ok:
        raise ValueError(f"OSM topology compilation failed: {report.summary()}")
    sections = compile_road_sections(links=links, road_geometry=geometry)
    metadata = {
        "source_name": str(source_name),
        "source_format": f"osm_xml_{source_version}",
        "source_sha256": source_sha256,
        "reference_only": True,
        "network_access": False,
        "projection": "local_equirectangular",
        "projection_origin_lat_deg": origin_lat_deg,
        "projection_origin_lon_deg": origin_lon_deg,
        "longitude_unwrapped": True,
        "simplify_tolerance_m": resolved_config.simplify_tolerance_m,
        "clip_bounds_m": resolved_config.clip_bounds_m,
        "capacity_veh_per_lane_per_tick": (
            resolved_config.capacity_veh_per_lane_per_tick
        ),
        "lane_tagging_policy": resolved_config.lane_tagging_policy,
        "lane_interpretation_counts": dict(lane_interpretations),
        "source_node_count": len(nodes_by_source_id),
        "source_way_count": len(all_ways),
        "included_way_count": len(included_ways),
        "skipped_way_count": len(all_ways) - len(included_ways),
        "shared_source_node_count": len(shared_node_ids),
        "split_physical_road_count": len(physical_segments),
        "compiled_node_count": len(nodes),
        "compiled_link_count": len(links),
        "road_geometry_fingerprint": geometry.fingerprint,
        "road_section_fingerprint": sections.fingerprint,
    }
    return OSMImportResult(
        nodes=nodes,
        links=links,
        road_geometry=geometry,
        road_sections=sections,
        metadata=metadata,
    )


def _parse_osm_xml(
    xml_text: str,
) -> tuple[dict[int, _OSMNode], tuple[_OSMWay, ...], str]:
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as exc:
        raise ValueError(f"invalid OSM XML: {exc}") from exc
    if _local_name(root.tag) != "osm":
        raise ValueError("OSM XML root element must be <osm>")
    version = str(root.attrib.get("version", "")).strip()
    if version != "0.6":
        raise ValueError(f"unsupported OSM XML version {version!r}; expected '0.6'")

    nodes: dict[int, _OSMNode] = {}
    ways: dict[int, _OSMWay] = {}
    for child in root:
        name = _local_name(child.tag)
        if name == "node":
            node_id = _parse_source_id(child.attrib.get("id"), "node id")
            if node_id in nodes:
                raise ValueError(f"duplicate OSM node id {node_id}")
            lat = _parse_coordinate(child.attrib.get("lat"), "node latitude")
            lon = _parse_coordinate(child.attrib.get("lon"), "node longitude")
            if lat < -90.0 or lat > 90.0 or lon < -180.0 or lon > 180.0:
                raise ValueError(f"OSM node {node_id} has out-of-range coordinates")
            nodes[node_id] = _OSMNode(node_id, lat, lon)
        elif name == "way":
            way_id = _parse_source_id(child.attrib.get("id"), "way id")
            if way_id in ways:
                raise ValueError(f"duplicate OSM way id {way_id}")
            refs: list[int] = []
            tags: dict[str, str] = {}
            for item in child:
                item_name = _local_name(item.tag)
                if item_name == "nd":
                    refs.append(_parse_source_id(item.attrib.get("ref"), "node ref"))
                elif item_name == "tag":
                    key = item.attrib.get("k")
                    value = item.attrib.get("v")
                    if key is None or value is None:
                        raise ValueError(f"OSM way {way_id} contains an incomplete tag")
                    if key in tags:
                        raise ValueError(f"OSM way {way_id} repeats tag {key!r}")
                    tags[str(key)] = str(value)
            ways[way_id] = _OSMWay(
                source_id=way_id,
                node_refs=tuple(refs),
                tags=MappingProxyType(tags),
            )
    return nodes, tuple(ways[way_id] for way_id in sorted(ways)), version


def _validate_way_node_references(
    ways: tuple[_OSMWay, ...],
    nodes_by_source_id: Mapping[int, _OSMNode],
) -> None:
    for way in ways:
        if len(way.node_refs) < 2:
            raise ValueError(f"OSM way {way.source_id} must reference at least two nodes")
        for node_id in way.node_refs:
            if node_id not in nodes_by_source_id:
                raise ValueError(
                    f"OSM way {way.source_id} has missing node reference {node_id}"
                )
        if any(left == right for left, right in zip(way.node_refs, way.node_refs[1:])):
            raise ValueError(
                f"OSM way {way.source_id} contains consecutive duplicate node refs"
            )


def _shared_node_ids(ways: tuple[_OSMWay, ...]) -> frozenset[int]:
    way_ids_by_node: dict[int, set[int]] = {}
    occurrence_count: Counter[int] = Counter()
    for way in ways:
        occurrence_count.update(way.node_refs)
        for node_id in set(way.node_refs):
            way_ids_by_node.setdefault(node_id, set()).add(way.source_id)
    return frozenset(
        node_id
        for node_id, way_ids in way_ids_by_node.items()
        if len(way_ids) > 1 or occurrence_count[node_id] > 1
    )


def _unwrap_longitudes(nodes: tuple[_OSMNode, ...]) -> dict[int, float]:
    if not nodes:
        raise ValueError("longitude unwrapping requires at least one OSM node")
    anchor = nodes[0].lon_deg
    return {
        node.source_id: anchor
        + (((node.lon_deg - anchor + 180.0) % 360.0) - 180.0)
        for node in nodes
    }


def _project_equirectangular(
    node: _OSMNode,
    *,
    unwrapped_lon_deg: float,
    origin_lat_deg: float,
    origin_lon_deg: float,
) -> tuple[float, float]:
    origin_lat_rad = math.radians(origin_lat_deg)
    x = (
        _EARTH_RADIUS_M
        * math.cos(origin_lat_rad)
        * math.radians(unwrapped_lon_deg - origin_lon_deg)
    )
    y = _EARTH_RADIUS_M * math.radians(node.lat_deg - origin_lat_deg)
    return (_canonical_float(x), _canonical_float(y))


def _build_physical_segments(
    *,
    ways: tuple[_OSMWay, ...],
    projected_by_source_id: Mapping[int, tuple[float, float]],
    shared_node_ids: frozenset[int],
    config: OSMImportConfig,
    interpretations: MutableMapping[str, int] | None = None,
) -> tuple[_PhysicalSegment, ...]:
    out: list[_PhysicalSegment] = []
    for way in ways:
        road_class = _HIGHWAY_CLASS[way.tags["highway"]]
        oneway = _parse_oneway(way.tags)
        lanes_forward, lanes_backward = _parse_directional_lanes(
            way.tags,
            oneway=oneway,
            policy=config.lane_tagging_policy,
            interpretations=interpretations,
        )
        speed_mps = _parse_speed_mps(way.tags, road_class=road_class)
        layer = _parse_layer(way.tags)
        if way.node_refs[0] == way.node_refs[-1]:
            split_indices = list(range(len(way.node_refs)))
        else:
            split_indices = [0]
            split_indices.extend(
                idx
                for idx, node_id in enumerate(way.node_refs[1:-1], start=1)
                if node_id in shared_node_ids
            )
            split_indices.append(len(way.node_refs) - 1)
        for part_index, (start_idx, end_idx) in enumerate(
            zip(split_indices, split_indices[1:])
        ):
            points = tuple(
                projected_by_source_id[node_id]
                for node_id in way.node_refs[start_idx : end_idx + 1]
            )
            if any(
                _points_close(left, right)
                for left, right in zip(points, points[1:])
            ):
                raise ValueError(
                    f"OSM way {way.source_id} contains a zero-length source edge"
                )
            start_source_node_id = way.node_refs[start_idx]
            end_source_node_id = way.node_refs[end_idx]
            if oneway == "reverse":
                points = tuple(reversed(points))
                start_source_node_id, end_source_node_id = (
                    end_source_node_id,
                    start_source_node_id,
                )
            fragments = _clip_polyline(points, config.clip_bounds_m)
            for fragment_index, fragment in enumerate(fragments):
                simplified = _simplify_polyline(
                    fragment,
                    tolerance_m=config.simplify_tolerance_m,
                )
                if len(simplified) < 2 or _polyline_length(simplified) <= 0.0:
                    continue
                out.append(
                    _PhysicalSegment(
                        source_way_id=way.source_id,
                        part_index=part_index,
                        fragment_index=fragment_index,
                        points_m=simplified,
                        road_class=road_class,
                        lanes_forward=lanes_forward,
                        lanes_backward=lanes_backward,
                        speed_mps=speed_mps,
                        layer=layer,
                        start_node_identity=(
                            ("osm", start_source_node_id)
                            if _points_close(simplified[0], points[0])
                            else (
                                "clip",
                                way.source_id,
                                part_index,
                                fragment_index,
                                "start",
                            )
                        ),
                        end_node_identity=(
                            ("osm", end_source_node_id)
                            if _points_close(simplified[-1], points[-1])
                            else (
                                "clip",
                                way.source_id,
                                part_index,
                                fragment_index,
                                "end",
                            )
                        ),
                    )
                )
    return tuple(out)


def _compile_typed_topology(
    segments: tuple[_PhysicalSegment, ...],
    *,
    capacity_veh_per_lane_per_tick: float,
) -> tuple[tuple[Node, ...], tuple[RoadLink, ...], RoadGeometryCatalog]:
    nodes: list[Node] = []
    node_id_by_identity: dict[tuple[object, ...], int] = {}
    links: list[RoadLink] = []
    centerlines: list[RoadCenterline] = []
    assignments: list[LinkGeometryAssignment] = []

    def node_id_for(
        identity: tuple[object, ...],
        point: tuple[float, float],
    ) -> int:
        existing = node_id_by_identity.get(identity)
        if existing is not None:
            existing_node = nodes[existing]
            if not _points_close((existing_node.x, existing_node.y), point):
                raise ValueError("one OSM node identity resolved to multiple coordinates")
            return existing
        node_id = len(nodes)
        nodes.append(Node(node_id=node_id, x=point[0], y=point[1]))
        node_id_by_identity[identity] = node_id
        return node_id

    for geometry_id, segment in enumerate(segments):
        src_node_id = node_id_for(
            segment.start_node_identity,
            segment.points_m[0],
        )
        dst_node_id = node_id_for(
            segment.end_node_identity,
            segment.points_m[-1],
        )
        if src_node_id == dst_node_id:
            continue
        centerline = RoadCenterline(
            geometry_id=geometry_id,
            points_m=segment.points_m,
            source=CenterlineSource.OSM,
            source_ref=(
                f"way:{segment.source_way_id}:part:{segment.part_index}:"
                f"fragment:{segment.fragment_index}"
            ),
            layer=segment.layer,
            corridor_id=(segment.source_way_id if segment.source_way_id >= 0 else None),
        )
        centerlines.append(centerline)
        length_m = centerline.length_m
        if segment.lanes_forward > 0:
            link_id = len(links)
            links.append(
                RoadLink(
                    link_id=link_id,
                    src_node_id=src_node_id,
                    dst_node_id=dst_node_id,
                    road_class=segment.road_class,
                    length_m=length_m,
                    free_flow_speed_mps=segment.speed_mps,
                    capacity_veh_per_tick=(
                        segment.lanes_forward * capacity_veh_per_lane_per_tick
                    ),
                    lanes=segment.lanes_forward,
                    physical_road_id=geometry_id,
                )
            )
            assignments.append(LinkGeometryAssignment(link_id, geometry_id, False))
        if segment.lanes_backward > 0:
            link_id = len(links)
            links.append(
                RoadLink(
                    link_id=link_id,
                    src_node_id=dst_node_id,
                    dst_node_id=src_node_id,
                    road_class=segment.road_class,
                    length_m=length_m,
                    free_flow_speed_mps=segment.speed_mps,
                    capacity_veh_per_tick=(
                        segment.lanes_backward * capacity_veh_per_lane_per_tick
                    ),
                    lanes=segment.lanes_backward,
                    physical_road_id=geometry_id,
                )
            )
            assignments.append(LinkGeometryAssignment(link_id, geometry_id, True))
    if len(centerlines) != len(segments):
        raise ValueError("OSM clipping produced a closed physical centerline")
    geometry = RoadGeometryCatalog(tuple(centerlines), tuple(assignments))
    return tuple(nodes), tuple(links), geometry


def _parse_oneway(tags: Mapping[str, str]) -> str:
    value = tags.get("oneway")
    if value is None:
        if tags.get("junction") == "roundabout" or tags.get("highway") in {
            "motorway",
            "motorway_link",
        }:
            return "forward"
        return "both"
    normalized = value.strip().lower()
    if normalized in {"yes", "true", "1"}:
        return "forward"
    if normalized in {"-1", "reverse"}:
        return "reverse"
    if normalized in {"no", "false", "0"}:
        return "both"
    raise UnsupportedOSMTagError(
        "UNSUPPORTED_ONEWAY_VALUE",
        f"unsupported oneway value {value!r}",
    )


def _parse_directional_lanes(
    tags: Mapping[str, str],
    *,
    oneway: str,
    policy: str = "strict",
    interpretations: MutableMapping[str, int] | None = None,
) -> tuple[int, int]:
    lenient = policy == "osm_wiki"

    def _record(kind: str) -> None:
        if interpretations is not None:
            interpretations[kind] = interpretations.get(kind, 0) + 1

    total = _parse_present_positive_int_tag(tags, "lanes")
    forward = _parse_present_positive_int_tag(tags, "lanes:forward")
    backward = _parse_present_positive_int_tag(tags, "lanes:backward")
    if oneway in {"forward", "reverse"}:
        directional = forward if oneway == "forward" else backward
        opposite = backward if oneway == "forward" else forward
        if opposite is not None:
            if not lenient:
                raise ValueError("oneway road declares lanes in the opposing direction")
            # A contraflow bus or cycle lane. It carries no general motor
            # traffic, so the drive network drops it and keeps the way.
            _record("oneway_contraflow_ignored")
            if directional is None and total is not None:
                directional = max(1, total - opposite)
        lane_count = directional if directional is not None else total
        if lane_count is None:
            lane_count = 1
        if total is not None and directional is not None and total != directional:
            if not (lenient and opposite is not None):
                raise ValueError("oneway directional lane count must equal total lanes")
        return lane_count, 0
    if total is None and forward is None and backward is None:
        return 1, 1
    if total is None:
        if forward is None or backward is None:
            if not lenient:
                raise ValueError(
                    "bidirectional lane tags require both directions or total lanes"
                )
            # Only one side is tagged; the other is implied, not invalid.
            _record("partial_directional")
            return (forward if forward is not None else 1), (
                backward if backward is not None else 1
            )
        return forward, backward
    if total < 2:
        if not lenient:
            raise ValueError("bidirectional total lanes must be >= 2")
        # A single-track two-way street: one lane shared by both directions.
        _record("single_track_two_way")
        return 1, 1
    if forward is not None and backward is not None:
        if forward + backward != total:
            raise ValueError("directional lane counts must sum to total lanes")
        return forward, backward
    if forward is not None:
        derived_backward = total - forward
        if derived_backward < 1:
            raise UnsupportedOSMTagError(
                "UNSUPPORTED_DIRECTIONAL_LANE_ALLOCATION",
                "lanes:forward leaves no backward traffic lane",
            )
        return forward, derived_backward
    if backward is not None:
        derived_forward = total - backward
        if derived_forward < 1:
            raise UnsupportedOSMTagError(
                "UNSUPPORTED_DIRECTIONAL_LANE_ALLOCATION",
                "lanes:backward leaves no forward traffic lane",
            )
        return derived_forward, backward
    return max(1, (total + 1) // 2), max(1, total // 2)


def _parse_speed_mps(tags: Mapping[str, str], *, road_class: RoadClass) -> float:
    raw = tags.get("maxspeed")
    if raw is None:
        return _DEFAULT_SPEED_MPS[road_class]
    normalized = raw.strip().lower()
    multiplier = 1.0 / 3.6
    if normalized.endswith("mph"):
        normalized = normalized[:-3].strip()
        multiplier = 0.44704
    elif normalized.endswith("km/h"):
        normalized = normalized[:-4].strip()
    try:
        numeric = float(normalized)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"maxspeed must be numeric, got {raw!r}") from exc
    speed_mps = numeric * multiplier
    if not math.isfinite(speed_mps) or speed_mps <= 0.0:
        raise ValueError("maxspeed must resolve to a finite positive speed")
    return speed_mps


def _parse_layer(tags: Mapping[str, str]) -> int:
    raw = tags.get("layer")
    if raw is not None:
        try:
            layer = int(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"layer must be an integer, got {raw!r}") from exc
        if str(layer) != raw.strip():
            raise ValueError(f"layer must be an integer, got {raw!r}")
        return layer
    if tags.get("bridge", "").strip().lower() in {"yes", "true", "1"}:
        return 1
    if tags.get("tunnel", "").strip().lower() in {"yes", "true", "1"}:
        return -1
    return 0


def _parse_present_positive_int_tag(
    tags: Mapping[str, str],
    key: str,
) -> int | None:
    raw = tags.get(key)
    if raw is None:
        return None
    stripped = raw.strip()
    try:
        value = int(stripped)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be a positive integer, got {raw!r}") from exc
    if str(value) != stripped or value < 1:
        raise ValueError(f"{key} must be a positive integer, got {raw!r}")
    return value


def _clip_polyline(
    points: tuple[tuple[float, float], ...],
    bounds: tuple[float, float, float, float] | None,
) -> tuple[tuple[tuple[float, float], ...], ...]:
    if bounds is None:
        return (points,)
    fragments: list[tuple[tuple[float, float], ...]] = []
    current: list[tuple[float, float]] = []
    for start, end in zip(points, points[1:]):
        clipped = _clip_segment(start, end, bounds)
        if clipped is None:
            if len(current) >= 2:
                fragments.append(tuple(current))
            current = []
            continue
        clipped_start, clipped_end = clipped
        if current and _points_close(current[-1], clipped_start):
            if not _points_close(current[-1], clipped_end):
                current.append(clipped_end)
        else:
            if len(current) >= 2:
                fragments.append(tuple(current))
            current = [clipped_start, clipped_end]
    if len(current) >= 2:
        fragments.append(tuple(current))
    return tuple(_remove_consecutive_duplicate_points(item) for item in fragments)


def _clip_segment(
    start: tuple[float, float],
    end: tuple[float, float],
    bounds: tuple[float, float, float, float],
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    min_x, min_y, max_x, max_y = bounds
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    lower = 0.0
    upper = 1.0
    for p, q in (
        (-dx, start[0] - min_x),
        (dx, max_x - start[0]),
        (-dy, start[1] - min_y),
        (dy, max_y - start[1]),
    ):
        if p == 0.0:
            if q < 0.0:
                return None
            continue
        ratio = q / p
        if p < 0.0:
            lower = max(lower, ratio)
        else:
            upper = min(upper, ratio)
        if lower > upper:
            return None
    return (
        (
            _canonical_float(start[0] + lower * dx),
            _canonical_float(start[1] + lower * dy),
        ),
        (
            _canonical_float(start[0] + upper * dx),
            _canonical_float(start[1] + upper * dy),
        ),
    )


def _simplify_polyline(
    points: tuple[tuple[float, float], ...],
    *,
    tolerance_m: float,
) -> tuple[tuple[float, float], ...]:
    if tolerance_m <= 0.0 or len(points) <= 2:
        return points
    start = points[0]
    end = points[-1]
    max_distance = -1.0
    max_index = -1
    for idx, point in enumerate(points[1:-1], start=1):
        distance = _point_to_segment_distance(point, start, end)
        if distance > max_distance:
            max_distance = distance
            max_index = idx
    if max_distance <= tolerance_m:
        return (start, end)
    left = _simplify_polyline(points[: max_index + 1], tolerance_m=tolerance_m)
    right = _simplify_polyline(points[max_index:], tolerance_m=tolerance_m)
    return (*left[:-1], *right)


def _point_to_segment_distance(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    denominator = dx * dx + dy * dy
    if denominator <= 0.0:
        return math.hypot(point[0] - start[0], point[1] - start[1])
    ratio = (
        (point[0] - start[0]) * dx + (point[1] - start[1]) * dy
    ) / denominator
    ratio = max(0.0, min(1.0, ratio))
    nearest_x = start[0] + ratio * dx
    nearest_y = start[1] + ratio * dy
    return math.hypot(point[0] - nearest_x, point[1] - nearest_y)


def _polyline_length(points: tuple[tuple[float, float], ...]) -> float:
    return sum(
        math.hypot(right[0] - left[0], right[1] - left[1])
        for left, right in zip(points, points[1:])
    )


def _remove_consecutive_duplicate_points(
    points: tuple[tuple[float, float], ...],
) -> tuple[tuple[float, float], ...]:
    out: list[tuple[float, float]] = []
    for point in points:
        if not out or not _points_close(out[-1], point):
            out.append(point)
    return tuple(out)


def _points_close(
    left: tuple[float, float],
    right: tuple[float, float],
) -> bool:
    return math.isclose(left[0], right[0], abs_tol=1e-9) and math.isclose(
        left[1], right[1], abs_tol=1e-9
    )


def _normalize_clip_bounds(
    value: object,
) -> tuple[float, float, float, float] | None:
    if value is None:
        return None
    try:
        raw = tuple(value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise ValueError("clip_bounds_m must contain four real values") from exc
    if len(raw) != 4:
        raise ValueError("clip_bounds_m must contain four real values")
    min_x, min_y, max_x, max_y = (
        _strict_real(item, "clip_bounds_m") for item in raw
    )
    if not all(math.isfinite(item) for item in (min_x, min_y, max_x, max_y)):
        raise ValueError("clip_bounds_m values must be finite")
    if min_x >= max_x or min_y >= max_y:
        raise ValueError("clip_bounds_m must satisfy min < max")
    return (min_x, min_y, max_x, max_y)


def _parse_source_id(value: str | None, field_name: str) -> int:
    if value is None:
        raise ValueError(f"OSM {field_name} is required")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"OSM {field_name} must be an integer") from exc


def _parse_coordinate(value: str | None, field_name: str) -> float:
    if value is None:
        raise ValueError(f"OSM {field_name} is required")
    try:
        coordinate = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"OSM {field_name} must be numeric") from exc
    if not math.isfinite(coordinate):
        raise ValueError(f"OSM {field_name} must be finite")
    return coordinate


def _strict_real(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{field_name} must be a real number")
    return float(value)


def _canonical_float(value: float) -> float:
    resolved = float(value)
    return 0.0 if resolved == 0.0 else resolved


def _local_name(tag: str) -> str:
    return str(tag).rsplit("}", 1)[-1]


def _sha256_json(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()
