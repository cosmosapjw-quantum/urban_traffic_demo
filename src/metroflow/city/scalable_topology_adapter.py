from __future__ import annotations

import math
from dataclasses import dataclass

from metroflow.city.generated_map import PreviewCityTopology
from metroflow.city.graph import (
    BridgeCrossing,
    Node,
    NodeKind,
    RoadClass,
    RoadLink,
    RoadNetworkCSR,
)
from metroflow.city.scalable_blocks import ScalableBlockAuthority
from metroflow.city.scalable_topology import (
    FacilityKind,
    PhysicalNodeRecord,
    PhysicalRoadRecord,
    RoadHierarchy,
    ScalableStreetNetwork,
)
from metroflow.map.road_geometry import (
    CenterlineSource,
    LinkGeometryAssignment,
    RoadCenterline,
)

__all__ = (
    "ScalableCompiledTopology",
    "ScalableGroupCrosswalk",
    "ScalableNumericProfile",
    "ScalableRoadCrosswalk",
    "compile_scalable_topology",
    "require_valid_scalable_compiled_topology",
)


@dataclass(frozen=True, slots=True)
class ScalableNumericProfile:
    profile_id: str
    lanes_per_direction: int
    free_flow_speed_mps: float
    capacity_veh_per_second: float
    operational_road_class: RoadClass
    section_roadside_profile: str
    median_when_bidirectional: bool


@dataclass(frozen=True, slots=True)
class ScalableGroupCrosswalk:
    semantic_group: str
    dense_group_id: int
    member_physical_road_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ScalableRoadCrosswalk:
    physical_road_id: int
    road_semantic_id: str
    hierarchy: RoadHierarchy
    facility: FacilityKind
    profile_id: str
    layer: int
    layer_transition: tuple[int, int] | None
    access_directions: tuple[str, ...]
    provenance: str
    geometry_id: int
    centerline_source_ref: str
    forward_link_id: int | None
    reverse_link_id: int | None
    structure_group: str | None
    structure_group_id: int | None
    failure_group: str | None
    bridge_group_id: int | None


@dataclass(frozen=True, slots=True)
class ScalableCompiledTopology:
    schema_version: str
    numeric_profile_policy_version: str
    topology: PreviewCityTopology
    road_csr: RoadNetworkCSR
    numeric_profiles: tuple[ScalableNumericProfile, ...]
    road_crosswalk: tuple[ScalableRoadCrosswalk, ...]
    structure_group_crosswalk: tuple[ScalableGroupCrosswalk, ...]
    failure_group_crosswalk: tuple[ScalableGroupCrosswalk, ...]
    metadata_items: tuple[tuple[str, object], ...]
    source_network_fingerprint: str
    source_block_authority_fingerprint: str
    terrain_fingerprint: str
    scale_fingerprint: str
    style_fingerprint: str
    road_geometry_fingerprint: str
    road_section_fingerprint: str
    node_interface_fingerprint: str
    turn_authority_fingerprint: str
    source_node_count: int
    source_physical_road_count: int
    source_block_count: int
    compiled_node_count: int
    compiled_link_count: int
    compiled_turn_count: int
    permitted_turn_count: int
    forbidden_u_turn_count: int
    bridge_crossing_count: int
    fingerprint: str


@dataclass(frozen=True, slots=True)
class _LoweredScalableRecords:
    nodes: tuple[Node, ...]
    links: tuple[RoadLink, ...]
    centerlines: tuple[RoadCenterline, ...]
    assignments: tuple[LinkGeometryAssignment, ...]
    numeric_profiles: tuple[ScalableNumericProfile, ...]
    road_crosswalk: tuple[ScalableRoadCrosswalk, ...]
    structure_group_crosswalk: tuple[ScalableGroupCrosswalk, ...]
    failure_group_crosswalk: tuple[ScalableGroupCrosswalk, ...]
    bridge_crossings: tuple[BridgeCrossing, ...]


_NUMERIC_PROFILE_POLICY = (
    ("v2:surface:local", 1, 8.3, 0.45, RoadClass.LOCAL, "urban", False),
    (
        "v2:surface:collector",
        1,
        11.1,
        0.70,
        RoadClass.COLLECTOR,
        "urban",
        False,
    ),
    (
        "v2:surface:arterial",
        2,
        16.7,
        1.10,
        RoadClass.ARTERIAL,
        "urban",
        True,
    ),
    (
        "v2:surface:expressway",
        3,
        27.8,
        1.80,
        RoadClass.EXPRESSWAY,
        "limited_access",
        True,
    ),
    (
        "v2:mainline",
        3,
        27.8,
        1.80,
        RoadClass.EXPRESSWAY,
        "limited_access",
        True,
    ),
    ("v2:ramp", 1, 13.9, 0.70, RoadClass.RAMP, "rural", False),
    (
        "v2:bridge:local",
        1,
        8.3,
        0.45,
        RoadClass.BRIDGE,
        "limited_access",
        True,
    ),
    (
        "v2:bridge:collector",
        1,
        11.1,
        0.70,
        RoadClass.BRIDGE,
        "limited_access",
        True,
    ),
    (
        "v2:bridge:arterial",
        2,
        16.7,
        1.10,
        RoadClass.BRIDGE,
        "limited_access",
        True,
    ),
    (
        "v2:bridge:expressway",
        3,
        27.8,
        1.80,
        RoadClass.BRIDGE,
        "limited_access",
        True,
    ),
    ("v2:tunnel:local", 1, 8.3, 0.45, RoadClass.LOCAL, "urban", False),
    (
        "v2:tunnel:collector",
        1,
        11.1,
        0.70,
        RoadClass.COLLECTOR,
        "urban",
        False,
    ),
    (
        "v2:tunnel:arterial",
        2,
        16.7,
        1.10,
        RoadClass.ARTERIAL,
        "urban",
        True,
    ),
    (
        "v2:tunnel:expressway",
        3,
        27.8,
        1.80,
        RoadClass.EXPRESSWAY,
        "limited_access",
        True,
    ),
)


def _lower_scalable_records(*, nodes, roads):
    source_nodes = tuple(nodes)
    source_roads = tuple(roads)
    if any(type(node) is not PhysicalNodeRecord for node in source_nodes):
        raise TypeError("nodes must contain exact PhysicalNodeRecord values")
    if any(type(road) is not PhysicalRoadRecord for road in source_roads):
        raise TypeError("roads must contain exact PhysicalRoadRecord values")
    if tuple(node.node_id for node in source_nodes) != tuple(range(len(source_nodes))):
        raise ValueError("physical node IDs must be dense and ordered")
    if tuple(road.road_id for road in source_roads) != tuple(range(len(source_roads))):
        raise ValueError("physical road IDs must be dense and ordered")

    numeric_profiles = tuple(
        sorted(
            (ScalableNumericProfile(*row) for row in _NUMERIC_PROFILE_POLICY),
            key=lambda profile: profile.profile_id,
        )
    )
    profile_by_id = {profile.profile_id: profile for profile in numeric_profiles}
    lowered_nodes = tuple(
        Node(
            node_id=node.node_id,
            kind=NodeKind.INTERSECTION,
            x=node.x_mm / 1_000.0,
            y=node.y_mm / 1_000.0,
        )
        for node in source_nodes
    )

    links: list[RoadLink] = []
    centerlines: list[RoadCenterline] = []
    assignments: list[LinkGeometryAssignment] = []
    road_crosswalk: list[ScalableRoadCrosswalk] = []
    bridge_link_ids: list[int] = []
    for road in source_roads:
        try:
            profile = profile_by_id[road.profile_id]
        except KeyError as error:
            raise ValueError(f"unsupported numeric profile {road.profile_id!r}") from error
        geometry_id = road.road_id
        source_ref = f"scalable:{road.semantic_id}"
        points_m = tuple(
            (x_mm / 1_000.0, y_mm / 1_000.0)
            for x_mm, y_mm in road.points_mm
        )
        centerlines.append(
            RoadCenterline(
                geometry_id=geometry_id,
                points_m=points_m,
                source=CenterlineSource.SYNTHETIC,
                source_ref=source_ref,
                layer=road.layer,
                corridor_id=road.road_id,
            )
        )
        length_m = float(
            sum(
                math.hypot(right[0] - left[0], right[1] - left[1])
                for left, right in zip(points_m, points_m[1:])
            )
        )
        forward_link_id: int | None = None
        reverse_link_id: int | None = None
        for direction in ("forward", "reverse"):
            if direction not in road.access_directions:
                continue
            link_id = len(links)
            is_reverse = direction == "reverse"
            src_node_id = road.end_node_id if is_reverse else road.start_node_id
            dst_node_id = road.start_node_id if is_reverse else road.end_node_id
            bridge_group_id = 0 if road.facility is FacilityKind.BRIDGE else None
            links.append(
                RoadLink(
                    link_id=link_id,
                    src_node_id=src_node_id,
                    dst_node_id=dst_node_id,
                    road_class=profile.operational_road_class,
                    length_m=length_m,
                    free_flow_speed_mps=profile.free_flow_speed_mps,
                    capacity_veh_per_tick=profile.capacity_veh_per_second,
                    lanes=profile.lanes_per_direction,
                    bridge_group_id=bridge_group_id,
                    physical_road_id=road.road_id,
                )
            )
            assignments.append(
                LinkGeometryAssignment(
                    link_id=link_id,
                    geometry_id=geometry_id,
                    reversed=is_reverse,
                )
            )
            if bridge_group_id is not None:
                bridge_link_ids.append(link_id)
            if is_reverse:
                reverse_link_id = link_id
            else:
                forward_link_id = link_id
        road_crosswalk.append(
            ScalableRoadCrosswalk(
                physical_road_id=road.road_id,
                road_semantic_id=road.semantic_id,
                hierarchy=road.hierarchy,
                facility=road.facility,
                profile_id=road.profile_id,
                layer=road.layer,
                layer_transition=road.layer_transition,
                access_directions=tuple(sorted(road.access_directions)),
                provenance=road.provenance,
                geometry_id=geometry_id,
                centerline_source_ref=source_ref,
                forward_link_id=forward_link_id,
                reverse_link_id=reverse_link_id,
                structure_group=road.structure_group,
                structure_group_id=0 if road.structure_group is not None else None,
                failure_group=road.failure_group,
                bridge_group_id=0 if road.failure_group is not None else None,
            )
        )

    bridge_crossings = (
        (
            BridgeCrossing(
                bridge_group_id=0,
                link_ids=tuple(bridge_link_ids),
                barrier_id=0,
                crossing_name="unbound_bridge_failure_authority",
            ),
        )
        if bridge_link_ids
        else ()
    )
    return _LoweredScalableRecords(
        nodes=lowered_nodes,
        links=tuple(links),
        centerlines=tuple(centerlines),
        assignments=tuple(assignments),
        numeric_profiles=numeric_profiles,
        road_crosswalk=tuple(road_crosswalk),
        structure_group_crosswalk=(),
        failure_group_crosswalk=(),
        bridge_crossings=bridge_crossings,
    )


def compile_scalable_topology(
    network: ScalableStreetNetwork,
    *,
    block_authority: ScalableBlockAuthority,
) -> ScalableCompiledTopology:
    raise NotImplementedError


def require_valid_scalable_compiled_topology(
    compiled: ScalableCompiledTopology,
    *,
    network: ScalableStreetNetwork,
    block_authority: ScalableBlockAuthority,
) -> None:
    raise NotImplementedError(
        "S6_OWNER_RED: current-content validation is not implemented"
    )
