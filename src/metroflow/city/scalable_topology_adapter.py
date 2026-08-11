from __future__ import annotations

import math
from collections import defaultdict
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
from metroflow.city.scalable_blocks import (
    ScalableBlockAuthority,
    validate_scalable_block_authority,
)
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
    structure_members: dict[str, list[int]] = defaultdict(list)
    failure_members: dict[str, list[int]] = defaultdict(list)
    for road in source_roads:
        if road.structure_group is not None:
            structure_members[road.structure_group].append(road.road_id)
        if road.failure_group is not None:
            failure_members[road.failure_group].append(road.road_id)
    structure_group_crosswalk = tuple(
        ScalableGroupCrosswalk(
            semantic_group=semantic_group,
            dense_group_id=dense_group_id,
            member_physical_road_ids=tuple(structure_members[semantic_group]),
        )
        for dense_group_id, semantic_group in enumerate(sorted(structure_members))
    )
    failure_group_crosswalk = tuple(
        ScalableGroupCrosswalk(
            semantic_group=semantic_group,
            dense_group_id=dense_group_id,
            member_physical_road_ids=tuple(failure_members[semantic_group]),
        )
        for dense_group_id, semantic_group in enumerate(sorted(failure_members))
    )
    structure_group_id = {
        row.semantic_group: row.dense_group_id
        for row in structure_group_crosswalk
    }
    failure_group_id = {
        row.semantic_group: row.dense_group_id for row in failure_group_crosswalk
    }
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
    bridge_link_ids: dict[int, list[int]] = defaultdict(list)
    for road in source_roads:
        resolved_profile_id = (
            "v2:mainline"
            if road.facility is FacilityKind.MAINLINE
            else road.profile_id
        )
        try:
            profile = profile_by_id[resolved_profile_id]
        except KeyError as error:
            raise ValueError(
                f"unsupported numeric profile {resolved_profile_id!r}"
            ) from error
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
            if road.facility is FacilityKind.BRIDGE:
                if road.structure_group is None or road.failure_group is None:
                    raise ValueError(
                        "bridge roads require structure and failure groups"
                    )
                bridge_group_id = failure_group_id[road.failure_group]
            else:
                bridge_group_id = None
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
                bridge_link_ids[bridge_group_id].append(link_id)
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
                profile_id=resolved_profile_id,
                layer=road.layer,
                layer_transition=road.layer_transition,
                access_directions=tuple(sorted(road.access_directions)),
                provenance=road.provenance,
                geometry_id=geometry_id,
                centerline_source_ref=source_ref,
                forward_link_id=forward_link_id,
                reverse_link_id=reverse_link_id,
                structure_group=road.structure_group,
                structure_group_id=(
                    None
                    if road.structure_group is None
                    else structure_group_id[road.structure_group]
                ),
                failure_group=road.failure_group,
                bridge_group_id=(
                    None
                    if road.failure_group is None
                    else failure_group_id[road.failure_group]
                ),
            )
        )

    failure_semantic_by_id = {
        row.dense_group_id: row.semantic_group for row in failure_group_crosswalk
    }
    bridge_crossings = tuple(
        BridgeCrossing(
            bridge_group_id=dense_group_id,
            link_ids=tuple(bridge_link_ids[dense_group_id]),
            barrier_id=dense_group_id,
            crossing_name=failure_semantic_by_id[dense_group_id],
        )
        for dense_group_id in sorted(bridge_link_ids)
    )
    return _LoweredScalableRecords(
        nodes=lowered_nodes,
        links=tuple(links),
        centerlines=tuple(centerlines),
        assignments=tuple(assignments),
        numeric_profiles=numeric_profiles,
        road_crosswalk=tuple(road_crosswalk),
        structure_group_crosswalk=structure_group_crosswalk,
        failure_group_crosswalk=failure_group_crosswalk,
        bridge_crossings=bridge_crossings,
    )


def _admit_scalable_sources(
    network: ScalableStreetNetwork,
    block_authority: ScalableBlockAuthority,
) -> tuple[ScalableStreetNetwork, ScalableBlockAuthority]:
    if type(network) is not ScalableStreetNetwork:
        raise TypeError("network must be an exact ScalableStreetNetwork")
    if type(block_authority) is not ScalableBlockAuthority:
        raise TypeError("block_authority must be an exact ScalableBlockAuthority")
    admitted_network = ScalableStreetNetwork(
        scale_spec=network.scale_spec,
        style_id=network.style_id,
        seed=network.seed,
        schema_version=network.schema_version,
        scale_fingerprint=network.scale_fingerprint,
        style_fingerprint=network.style_fingerprint,
        extent_mm=network.extent_mm,
        width_m=network.width_m,
        height_m=network.height_m,
        centers=network.centers,
        gateway_node_ids=network.gateway_node_ids,
        nodes=network.nodes,
        roads=network.roads,
        endpoint_incidence=network.endpoint_incidence,
        terrain=network.terrain,
        tile_coordinates=network.tile_coordinates,
        seam_diagnostics=network.seam_diagnostics,
        hidden_repair_count=network.hidden_repair_count,
        fingerprint=network.fingerprint,
    )
    validate_scalable_block_authority(block_authority)
    if block_authority.source_network_fingerprint != admitted_network.fingerprint:
        raise ValueError("block authority source network fingerprint mismatch")
    if block_authority.extent_mm != admitted_network.extent_mm:
        raise ValueError("block authority extent mismatch")
    if block_authority.tile_coordinates != admitted_network.tile_coordinates:
        raise ValueError("block authority tile coordinates mismatch")

    node_by_id = {node.node_id: node for node in admitted_network.nodes}
    road_by_id = {road.road_id: road for road in admitted_network.roads}
    expected_embedding_road_ids = {
        road.road_id
        for road in admitted_network.roads
        if road.layer == 0
        and road.layer_transition is None
        and road.facility in {FacilityKind.SURFACE, FacilityKind.BRIDGE}
    }
    if {edge.source_road_id for edge in block_authority.embedding_edges} != (
        expected_embedding_road_ids
    ):
        raise ValueError("embedding edge coverage differs from the source network")
    for edge in block_authority.embedding_edges:
        road = road_by_id[edge.source_road_id]
        if edge.source_fingerprint != admitted_network.fingerprint:
            raise ValueError("embedding edge source fingerprint mismatch")
        if edge.facility != road.facility.value or edge.layer != road.layer:
            raise ValueError("embedding edge facility or layer mismatch")
        start = node_by_id[road.start_node_id]
        end = node_by_id[road.end_node_id]
        forward = (
            road.start_node_id,
            road.end_node_id,
            start.semantic_id,
            end.semantic_id,
            road.points_mm,
        )
        reverse = (
            road.end_node_id,
            road.start_node_id,
            end.semantic_id,
            start.semantic_id,
            tuple(reversed(road.points_mm)),
        )
        observed = (
            edge.start_node_id,
            edge.end_node_id,
            edge.start_node_semantic_id,
            edge.end_node_semantic_id,
            edge.points_mm,
        )
        if observed not in {forward, reverse}:
            raise ValueError("embedding edge geometry mismatch")

    expected_ramp_road_ids = {
        road.road_id
        for road in admitted_network.roads
        if road.facility is FacilityKind.RAMP
    }
    if {ramp.source_road_id for ramp in block_authority.ramp_incidence} != (
        expected_ramp_road_ids
    ):
        raise ValueError("ramp incidence coverage differs from the source network")
    for ramp in block_authority.ramp_incidence:
        road = road_by_id[ramp.source_road_id]
        if ramp.source_fingerprint != admitted_network.fingerprint:
            raise ValueError("ramp incidence source fingerprint mismatch")
        if (ramp.start_node_id, ramp.end_node_id) not in {
            (road.start_node_id, road.end_node_id),
            (road.end_node_id, road.start_node_id),
        }:
            raise ValueError("ramp incidence endpoint mismatch")

    road_ids = set(road_by_id)
    node_ids = set(node_by_id)
    for block in block_authority.blocks:
        if not set(block.frontage_road_ids) <= road_ids:
            raise ValueError("block frontage references a foreign road")
        if not set(block.access_node_ids) <= node_ids:
            raise ValueError("block access references a foreign node")
        if block.primary_access_node_id not in block.access_node_ids:
            raise ValueError("block primary access is not in its access set")
    return admitted_network, block_authority


def compile_scalable_topology(
    network: ScalableStreetNetwork,
    *,
    block_authority: ScalableBlockAuthority,
) -> ScalableCompiledTopology:
    admitted_network, _admitted_blocks = _admit_scalable_sources(
        network,
        block_authority,
    )
    _lower_scalable_records(
        nodes=admitted_network.nodes,
        roads=admitted_network.roads,
    )
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
