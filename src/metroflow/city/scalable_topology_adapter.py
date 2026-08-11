from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from dataclasses import dataclass, replace

import numpy as np

from metroflow.city.generated_map import PreviewCityTopology
from metroflow.city.graph import (
    BridgeCrossing,
    Node,
    NodeKind,
    RoadClass,
    RoadLink,
    RoadNetworkCSR,
    TurnMovement,
    TurnType,
)
from metroflow.city.map_validation import require_valid_city_map_contract
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
from metroflow.city.turn_compiler import TurnAuthorityCatalog, compile_turn_authority
from metroflow.map.lane_grammar import RoadSectionProfile
from metroflow.map.node_compiler import (
    CompiledNodeInterface,
    NodeInterfaceCatalog,
    compile_node_interfaces,
)
from metroflow.map.road_geometry import (
    CenterlineSource,
    LinkGeometryAssignment,
    RoadCenterline,
    RoadGeometryCatalog,
)
from metroflow.map.section_compiler import (
    LinkSectionAssignment,
    RoadSectionCatalog,
    compile_road_sections,
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

    def __post_init__(self) -> None:
        if type(self.profile_id) is not str:
            raise TypeError("profile_id must be an exact string")
        if type(self.lanes_per_direction) is not int:
            raise TypeError("lanes_per_direction must be an exact integer")
        if type(self.free_flow_speed_mps) is not float:
            raise TypeError("free_flow_speed_mps must be an exact float")
        if type(self.capacity_veh_per_second) is not float:
            raise TypeError("capacity_veh_per_second must be an exact float")
        if type(self.operational_road_class) is not RoadClass:
            raise TypeError("operational_road_class must be an exact RoadClass")
        if type(self.section_roadside_profile) is not str:
            raise TypeError("section_roadside_profile must be an exact string")
        if type(self.median_when_bidirectional) is not bool:
            raise TypeError("median_when_bidirectional must be an exact bool")
        if (
            not self.profile_id
            or self.lanes_per_direction < 1
            or self.free_flow_speed_mps <= 0.0
            or self.capacity_veh_per_second < 0.0
            or not self.section_roadside_profile
        ):
            raise ValueError("numeric profile values must be non-empty and non-negative")


@dataclass(frozen=True, slots=True)
class ScalableGroupCrosswalk:
    semantic_group: str
    dense_group_id: int
    member_physical_road_ids: tuple[int, ...]

    def __post_init__(self) -> None:
        if type(self.semantic_group) is not str:
            raise TypeError("semantic_group must be an exact string")
        if type(self.dense_group_id) is not int:
            raise TypeError("dense_group_id must be an exact integer")
        if type(self.member_physical_road_ids) is not tuple or any(
            type(road_id) is not int for road_id in self.member_physical_road_ids
        ):
            raise TypeError("member_physical_road_ids must be an exact integer tuple")
        if (
            not self.semantic_group
            or self.dense_group_id < 0
            or not self.member_physical_road_ids
            or tuple(sorted(set(self.member_physical_road_ids))) != self.member_physical_road_ids
        ):
            raise ValueError("group crosswalk values must be unique and canonical")


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

    def __post_init__(self) -> None:
        exact_int_names = ("physical_road_id", "layer", "geometry_id")
        if any(type(getattr(self, name)) is not int for name in exact_int_names):
            raise TypeError("road crosswalk IDs and layer must be exact integers")
        if type(self.road_semantic_id) is not str or type(self.profile_id) is not str:
            raise TypeError("road crosswalk semantic and profile IDs must be strings")
        if type(self.hierarchy) is not RoadHierarchy:
            raise TypeError("road crosswalk hierarchy must be exact")
        if type(self.facility) is not FacilityKind:
            raise TypeError("road crosswalk facility must be exact")
        if self.layer_transition is not None and (
            type(self.layer_transition) is not tuple
            or len(self.layer_transition) != 2
            or any(type(layer) is not int for layer in self.layer_transition)
        ):
            raise TypeError("layer_transition must be an exact integer pair")
        if type(self.access_directions) is not tuple or any(
            type(direction) is not str for direction in self.access_directions
        ):
            raise TypeError("access_directions must be an exact string tuple")
        if self.access_directions not in {
            ("forward",),
            ("reverse",),
            ("forward", "reverse"),
        }:
            raise ValueError("access_directions must be canonical")
        for name in (
            "provenance",
            "centerline_source_ref",
            "structure_group",
            "failure_group",
        ):
            value = getattr(self, name)
            if value is not None and type(value) is not str:
                raise TypeError(f"{name} must be an exact string when present")
        for name in (
            "forward_link_id",
            "reverse_link_id",
            "structure_group_id",
            "bridge_group_id",
        ):
            value = getattr(self, name)
            if value is not None and type(value) is not int:
                raise TypeError(f"{name} must be an exact integer when present")


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

    def __post_init__(self) -> None:
        if type(self.topology) is not PreviewCityTopology:
            raise TypeError("topology must be an exact PreviewCityTopology")
        if type(self.road_csr) is not RoadNetworkCSR:
            raise TypeError("road_csr must be an exact RoadNetworkCSR")
        tuple_fields = (
            "numeric_profiles",
            "road_crosswalk",
            "structure_group_crosswalk",
            "failure_group_crosswalk",
            "metadata_items",
        )
        for name in tuple_fields:
            if type(getattr(self, name)) is not tuple:
                raise TypeError(f"{name} must be an exact tuple")
        if any(type(row) is not ScalableNumericProfile for row in self.numeric_profiles):
            raise TypeError("numeric_profiles must contain exact rows")
        if any(type(row) is not ScalableRoadCrosswalk for row in self.road_crosswalk):
            raise TypeError("road_crosswalk must contain exact rows")
        for name in ("structure_group_crosswalk", "failure_group_crosswalk"):
            if any(type(row) is not ScalableGroupCrosswalk for row in getattr(self, name)):
                raise TypeError(f"{name} must contain exact rows")
        if any(
            type(item) is not tuple or len(item) != 2 or type(item[0]) is not str
            for item in self.metadata_items
        ):
            raise TypeError("metadata_items must contain exact string-key pairs")

        topology = self.topology
        csr = self.road_csr
        topology_rows = (
            ("nodes", Node),
            ("links", RoadLink),
            ("turns", TurnMovement),
            ("bridge_crossings", BridgeCrossing),
        )
        for name, row_type in topology_rows:
            rows = getattr(topology, name)
            if type(rows) is not tuple or any(type(row) is not row_type for row in rows):
                raise TypeError(f"topology {name} must contain exact rows")
            csr_rows = getattr(csr, name)
            if type(csr_rows) is not tuple or any(type(row) is not row_type for row in csr_rows):
                raise TypeError(f"road_csr CSR {name} must contain exact rows")
            if csr_rows != rows:
                raise ValueError(f"road_csr CSR {name} differ from topology")

        geometry = topology.road_geometry
        sections = topology.road_sections
        interfaces = topology.node_interfaces
        if type(geometry) is not RoadGeometryCatalog:
            raise TypeError("road geometry catalog must be exact")
        if type(sections) is not RoadSectionCatalog:
            raise TypeError("road section catalog must be exact")
        if type(interfaces) is not NodeInterfaceCatalog:
            raise TypeError("node interface catalog must be exact")
        catalog_rows = (
            (geometry.centerlines, RoadCenterline, "centerline"),
            (geometry.assignments, LinkGeometryAssignment, "geometry assignment"),
            (sections.profiles, RoadSectionProfile, "section profile"),
            (sections.assignments, LinkSectionAssignment, "section assignment"),
            (interfaces.interfaces, CompiledNodeInterface, "node interface"),
        )
        for rows, row_type, name in catalog_rows:
            if type(rows) is not tuple or any(type(row) is not row_type for row in rows):
                raise TypeError(f"{name} catalog must contain exact rows")

        string_fields = (
            "schema_version",
            "numeric_profile_policy_version",
            "source_network_fingerprint",
            "source_block_authority_fingerprint",
            "terrain_fingerprint",
            "scale_fingerprint",
            "style_fingerprint",
            "road_geometry_fingerprint",
            "road_section_fingerprint",
            "node_interface_fingerprint",
            "turn_authority_fingerprint",
            "fingerprint",
        )
        if any(type(getattr(self, name)) is not str for name in string_fields):
            raise TypeError("wrapper identity fields must be exact strings")
        count_fields = (
            "source_node_count",
            "source_physical_road_count",
            "source_block_count",
            "compiled_node_count",
            "compiled_link_count",
            "compiled_turn_count",
            "permitted_turn_count",
            "forbidden_u_turn_count",
            "bridge_crossing_count",
        )
        if any(type(getattr(self, name)) is not int for name in count_fields):
            raise TypeError("wrapper counts must be exact integers")
        if any(getattr(self, name) < 0 for name in count_fields):
            raise ValueError("wrapper counts must be non-negative")

        physical_ids = tuple(row.physical_road_id for row in self.road_crosswalk)
        if physical_ids != tuple(range(len(physical_ids))):
            raise ValueError("road crosswalk physical IDs must be dense and ordered")
        profile_ids = tuple(row.profile_id for row in self.numeric_profiles)
        if len(profile_ids) != len(set(profile_ids)) or profile_ids != tuple(sorted(profile_ids)):
            raise ValueError("numeric profile IDs must be unique and ordered")

        for crosswalk_name, semantic_name, dense_name in (
            (
                "structure_group_crosswalk",
                "structure_group",
                "structure_group_id",
            ),
            (
                "failure_group_crosswalk",
                "failure_group",
                "bridge_group_id",
            ),
        ):
            group_rows = getattr(self, crosswalk_name)
            semantics = tuple(row.semantic_group for row in group_rows)
            dense_ids = tuple(row.dense_group_id for row in group_rows)
            if len(semantics) != len(set(semantics)):
                raise ValueError(f"{crosswalk_name} has duplicate group semantics")
            if dense_ids != tuple(range(len(group_rows))):
                raise ValueError(f"{crosswalk_name} dense group IDs are not canonical")
            group_by_semantic = {row.semantic_group: row.dense_group_id for row in group_rows}
            for group_row in group_rows:
                expected_members = tuple(
                    row.physical_road_id
                    for row in self.road_crosswalk
                    if getattr(row, semantic_name) == group_row.semantic_group
                )
                if group_row.member_physical_road_ids != expected_members:
                    raise ValueError(f"{crosswalk_name} member rows differ")
            for road_row in self.road_crosswalk:
                semantic = getattr(road_row, semantic_name)
                dense_id = getattr(road_row, dense_name)
                expected_dense_id = None if semantic is None else group_by_semantic.get(semantic)
                if dense_id != expected_dense_id:
                    raise ValueError(f"{crosswalk_name} road mapping differs")

        node_ids = {node.node_id for node in topology.nodes}
        link_ids = {link.link_id for link in topology.links}
        geometry_ids = {row.geometry_id for row in self.road_crosswalk}
        if {row.geometry_id for row in geometry.centerlines} != geometry_ids:
            raise ValueError("centerline catalog coverage count differs")
        if {row.link_id for row in geometry.assignments} != link_ids:
            raise ValueError("geometry assignment catalog coverage count differs")
        if {row.link_id for row in sections.assignments} != link_ids:
            raise ValueError("section assignment catalog coverage count differs")
        if {row.node_id for row in interfaces.interfaces} != node_ids:
            raise ValueError("node interface catalog coverage count differs")

        permitted_turn_count = sum(
            movement.turn_type is not TurnType.U_TURN_FORBIDDEN for movement in topology.turns
        )
        expected_counts = {
            "source_node_count": len(topology.nodes),
            "source_physical_road_count": len(self.road_crosswalk),
            "compiled_node_count": len(topology.nodes),
            "compiled_link_count": len(topology.links),
            "compiled_turn_count": len(topology.turns),
            "permitted_turn_count": permitted_turn_count,
            "forbidden_u_turn_count": len(topology.turns) - permitted_turn_count,
            "bridge_crossing_count": len(topology.bridge_crossings),
        }
        for name, expected in expected_counts.items():
            if getattr(self, name) != expected:
                raise ValueError(f"{name} differs from current row count")

        if type(topology.metadata) is not dict:
            raise TypeError("topology metadata must be an exact dict")
        metadata = dict(self.metadata_items)
        if len(metadata) != len(self.metadata_items):
            raise ValueError("metadata_items keys must be unique")
        if tuple(topology.metadata.items()) != self.metadata_items:
            raise ValueError("topology and wrapper metadata items differ")
        expected_metadata_counts = {
            "source_node_count": self.source_node_count,
            "source_physical_road_count": self.source_physical_road_count,
            "source_block_count": self.source_block_count,
            "compiled_node_count": self.compiled_node_count,
            "compiled_link_count": self.compiled_link_count,
            "physical_centerline_count": len(geometry.centerlines),
            "geometry_assignment_count": len(geometry.assignments),
            "road_section_assignment_count": len(sections.assignments),
            "node_interface_count": len(interfaces.interfaces),
            "turn_authority_pair_count": len(topology.turns),
            "permitted_turn_movement_count": permitted_turn_count,
            "forbidden_u_turn_count": len(topology.turns) - permitted_turn_count,
            "bridge_crossing_count": len(topology.bridge_crossings),
        }
        for name, expected in expected_metadata_counts.items():
            if metadata.get(name) != expected:
                raise ValueError(f"metadata {name} differs from current row count")
        expected_fingerprints = {
            "road_geometry_fingerprint": self.road_geometry_fingerprint,
            "road_section_fingerprint": self.road_section_fingerprint,
            "node_interface_fingerprint": self.node_interface_fingerprint,
            "turn_authority_fingerprint": self.turn_authority_fingerprint,
        }
        for name, expected in expected_fingerprints.items():
            if metadata.get(name) != expected:
                raise ValueError(f"metadata {name} differs from wrapper identity")


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

    node_by_id = {node.node_id: node for node in source_nodes}
    for road in source_roads:
        try:
            endpoint_layers = (
                node_by_id[road.start_node_id].layer,
                node_by_id[road.end_node_id].layer,
            )
        except KeyError as error:
            raise ValueError("road endpoint is absent from physical nodes") from error
        if road.facility is FacilityKind.SURFACE:
            if road.layer != 0 or endpoint_layers != (0, 0):
                raise ValueError("surface roads require layer-0 endpoints")
        elif road.facility is FacilityKind.MAINLINE:
            if (
                road.hierarchy is not RoadHierarchy.EXPRESSWAY
                or road.layer != 1
                or endpoint_layers != (1, 1)
            ):
                raise ValueError(
                    "mainline roads require expressway hierarchy and layer-1 endpoints"
                )
        elif road.facility is FacilityKind.RAMP:
            if (
                road.hierarchy is not RoadHierarchy.ARTERIAL
                or road.layer != 1
                or road.layer_transition != (0, 1)
                or endpoint_layers != (0, 1)
            ):
                raise ValueError(
                    "ramp roads require arterial hierarchy and a layer-0-to-1 transition"
                )
        elif road.facility is FacilityKind.BRIDGE:
            if road.layer != 0 or endpoint_layers != (0, 0):
                raise ValueError("bridge roads require layer-0 endpoints")
        else:
            raise ValueError("tunnel facility is not admitted by this adapter schema")

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
        row.semantic_group: row.dense_group_id for row in structure_group_crosswalk
    }
    failure_group_id = {row.semantic_group: row.dense_group_id for row in failure_group_crosswalk}
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
            "v2:mainline" if road.facility is FacilityKind.MAINLINE else road.profile_id
        )
        try:
            profile = profile_by_id[resolved_profile_id]
        except KeyError as error:
            raise ValueError(f"unsupported numeric profile {resolved_profile_id!r}") from error
        geometry_id = road.road_id
        source_ref = f"scalable:{road.semantic_id}"
        points_m = tuple((x_mm / 1_000.0, y_mm / 1_000.0) for x_mm, y_mm in road.points_mm)
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
                    raise ValueError("bridge roads require structure and failure groups")
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
                    None if road.failure_group is None else failure_group_id[road.failure_group]
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
        expected_source_record = (
            road.semantic_id,
            road.start_node_id,
            road.end_node_id,
            start.semantic_id,
            end.semantic_id,
            road.points_mm,
            road.layer,
            road.facility.value,
            admitted_network.fingerprint,
        )
        observed_source_record = (
            edge.source_road_semantic_id,
            edge.start_node_id,
            edge.end_node_id,
            edge.start_node_semantic_id,
            edge.end_node_semantic_id,
            edge.points_mm,
            edge.layer,
            edge.facility,
            edge.source_fingerprint,
        )
        if observed_source_record != expected_source_record:
            raise ValueError("embedding source record mismatch")

    expected_ramp_road_ids = {
        road.road_id for road in admitted_network.roads if road.facility is FacilityKind.RAMP
    }
    if {ramp.source_road_id for ramp in block_authority.ramp_incidence} != (expected_ramp_road_ids):
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
        start = node_by_id[road.start_node_id]
        end = node_by_id[road.end_node_id]
        if (
            ramp.source_road_semantic_id,
            ramp.start_node_id,
            ramp.end_node_id,
            ramp.start_node_semantic_id,
            ramp.end_node_semantic_id,
            ramp.source_fingerprint,
        ) != (
            road.semantic_id,
            road.start_node_id,
            road.end_node_id,
            start.semantic_id,
            end.semantic_id,
            admitted_network.fingerprint,
        ):
            raise ValueError("ramp source record mismatch")

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


def _compiled_fingerprint(compiled: ScalableCompiledTopology) -> str:
    topology = compiled.topology
    csr = compiled.road_csr

    def csr_array(name: str) -> tuple[str, tuple[int, ...], tuple, bool]:
        array = getattr(csr, name)
        return (
            array.dtype.str,
            tuple(array.shape),
            tuple(array.reshape(-1).tolist()),
            bool(array.flags.writeable),
        )

    payload = {
        "schema_version": compiled.schema_version,
        "numeric_profile_policy_version": compiled.numeric_profile_policy_version,
        "numeric_profiles": tuple(
            (
                profile.profile_id,
                profile.lanes_per_direction,
                profile.free_flow_speed_mps,
                profile.capacity_veh_per_second,
                profile.operational_road_class.value,
                profile.section_roadside_profile,
                profile.median_when_bidirectional,
            )
            for profile in compiled.numeric_profiles
        ),
        "road_crosswalk": tuple(
            (
                row.physical_road_id,
                row.road_semantic_id,
                row.hierarchy.value,
                row.facility.value,
                row.profile_id,
                row.layer,
                row.layer_transition,
                row.access_directions,
                row.provenance,
                row.geometry_id,
                row.centerline_source_ref,
                row.forward_link_id,
                row.reverse_link_id,
                row.structure_group,
                row.structure_group_id,
                row.failure_group,
                row.bridge_group_id,
            )
            for row in compiled.road_crosswalk
        ),
        "structure_group_crosswalk": tuple(
            (
                row.semantic_group,
                row.dense_group_id,
                row.member_physical_road_ids,
            )
            for row in compiled.structure_group_crosswalk
        ),
        "failure_group_crosswalk": tuple(
            (
                row.semantic_group,
                row.dense_group_id,
                row.member_physical_road_ids,
            )
            for row in compiled.failure_group_crosswalk
        ),
        "nodes": tuple(
            (
                node.node_id,
                node.kind.value,
                node.x,
                node.y,
                node.zone_id,
                node.signal_group_id,
            )
            for node in topology.nodes
        ),
        "links": tuple(
            (
                link.link_id,
                link.src_node_id,
                link.dst_node_id,
                link.road_class.value,
                link.length_m,
                link.free_flow_speed_mps,
                link.capacity_veh_per_tick,
                link.lanes,
                link.bridge_group_id,
                link.is_blockable,
                link.physical_road_id,
            )
            for link in topology.links
        ),
        "turns": tuple(
            (
                movement.from_link_id,
                movement.to_link_id,
                movement.turn_type.value,
                movement.base_priority,
                movement.signal_phase_id,
            )
            for movement in topology.turns
        ),
        "bridge_crossings": tuple(
            (
                crossing.bridge_group_id,
                crossing.link_ids,
                crossing.barrier_id,
                crossing.crossing_name,
                crossing.bottleneck_rank_hint,
            )
            for crossing in topology.bridge_crossings
        ),
        "catalog_fingerprints": (
            topology.road_geometry.fingerprint,
            topology.road_sections.fingerprint,
            topology.node_interfaces.fingerprint,
            compiled.road_geometry_fingerprint,
            compiled.road_section_fingerprint,
            compiled.node_interface_fingerprint,
            compiled.turn_authority_fingerprint,
        ),
        "csr": {
            "node_id_to_index": tuple(sorted(csr.node_id_to_index.items())),
            "link_id_to_index": tuple(sorted(csr.link_id_to_index.items())),
            "arrays": tuple(
                (name, csr_array(name))
                for name in (
                    "node_ids",
                    "link_ids",
                    "link_src_node_index",
                    "link_dst_node_index",
                    "outgoing_indptr",
                    "outgoing_link_indices",
                    "incoming_indptr",
                    "incoming_link_indices",
                    "turn_from_link_index",
                    "turn_to_link_index",
                    "turn_base_priority",
                    "turn_is_forbidden",
                )
            ),
            "turn_pair_to_index": tuple(sorted(csr.turn_pair_to_index.items())),
            "topology_cache_key": csr.topology_cache_key,
        },
        "topology_metadata_items": tuple(topology.metadata.items()),
        "metadata_items": compiled.metadata_items,
        "source_identity": (
            compiled.source_network_fingerprint,
            compiled.source_block_authority_fingerprint,
            compiled.terrain_fingerprint,
            compiled.scale_fingerprint,
            compiled.style_fingerprint,
        ),
        "counts": (
            compiled.source_node_count,
            compiled.source_physical_road_count,
            compiled.source_block_count,
            compiled.compiled_node_count,
            compiled.compiled_link_count,
            compiled.compiled_turn_count,
            compiled.permitted_turn_count,
            compiled.forbidden_u_turn_count,
            compiled.bridge_crossing_count,
        ),
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _new_compiled_wrapper(**values) -> ScalableCompiledTopology:
    compiled = ScalableCompiledTopology(fingerprint="", **values)
    return replace(compiled, fingerprint=_compiled_fingerprint(compiled))


def _metadata_items_for(
    *,
    network: ScalableStreetNetwork,
    block_authority: ScalableBlockAuthority,
    numeric_profiles: tuple[ScalableNumericProfile, ...],
    topology: PreviewCityTopology,
    turn_fingerprint: str,
) -> tuple[tuple[str, object], ...]:
    road_geometry = topology.road_geometry
    road_sections = topology.road_sections
    node_interfaces = topology.node_interfaces
    if type(road_geometry) is not RoadGeometryCatalog:
        raise TypeError("topology road_geometry must be an exact catalog")
    if type(road_sections) is not RoadSectionCatalog:
        raise TypeError("topology road_sections must be an exact catalog")
    if type(node_interfaces) is not NodeInterfaceCatalog:
        raise TypeError("topology node_interfaces must be an exact catalog")
    permitted_turn_count = sum(
        movement.turn_type is not TurnType.U_TURN_FORBIDDEN for movement in topology.turns
    )
    forbidden_u_turn_count = len(topology.turns) - permitted_turn_count
    numeric_profile_payload = tuple(
        (
            profile.profile_id,
            profile.lanes_per_direction,
            profile.free_flow_speed_mps,
            profile.capacity_veh_per_second,
            profile.operational_road_class.value,
            profile.section_roadside_profile,
            profile.median_when_bidirectional,
        )
        for profile in numeric_profiles
    )
    return (
        ("engine", "metroflow"),
        ("topology_mode", "scalable_static"),
        ("adapter_schema_version", "scalable_topology_adapter_v1"),
        ("numeric_profile_policy_version", "scalable_v2_numeric_profiles_v1"),
        (
            "turn_authority_policy",
            "all_adjacent_pairs_explicit_immediate_return_forbidden_v1",
        ),
        ("seed", network.seed),
        ("style_id", network.style_id),
        ("source_network_fingerprint", network.fingerprint),
        ("source_block_authority_fingerprint", block_authority.fingerprint),
        ("block_authority_schema_version", block_authority.schema_version),
        ("terrain_fingerprint", network.terrain.fingerprint),
        ("scale_fingerprint", network.scale_fingerprint),
        ("style_fingerprint", network.style_fingerprint),
        ("road_geometry_fingerprint", road_geometry.fingerprint),
        ("road_section_fingerprint", road_sections.fingerprint),
        ("node_interface_fingerprint", node_interfaces.fingerprint),
        ("turn_authority_fingerprint", turn_fingerprint),
        ("numeric_profile_payload", numeric_profile_payload),
        ("source_node_count", len(network.nodes)),
        ("source_physical_road_count", len(network.roads)),
        ("source_block_count", len(block_authority.blocks)),
        ("compiled_node_count", len(topology.nodes)),
        ("compiled_link_count", len(topology.links)),
        ("physical_centerline_count", len(road_geometry.centerlines)),
        ("geometry_assignment_count", len(road_geometry.assignments)),
        ("road_section_assignment_count", len(road_sections.assignments)),
        ("node_interface_count", len(node_interfaces.interfaces)),
        ("turn_authority_pair_count", len(topology.turns)),
        ("permitted_turn_movement_count", permitted_turn_count),
        ("forbidden_u_turn_count", forbidden_u_turn_count),
        ("bridge_crossing_count", len(topology.bridge_crossings)),
        ("weak_component_count", 1),
        ("hidden_repair_count", network.hidden_repair_count),
        ("dropped_physical_road_count", 0),
        ("dropped_chain_count", 0),
        ("connectivity_repair_link_count", 0),
        ("connectivity_repair_link_ids", ()),
        ("planarization_status", "not_requested"),
        ("capacity_reference_tick_seconds", 1.0),
        ("capacity_source_unit", "vehicles_per_second"),
    )


def compile_scalable_topology(
    network: ScalableStreetNetwork,
    *,
    block_authority: ScalableBlockAuthority,
) -> ScalableCompiledTopology:
    admitted_network, admitted_blocks = _admit_scalable_sources(
        network,
        block_authority,
    )
    lowered = _lower_scalable_records(
        nodes=admitted_network.nodes,
        roads=admitted_network.roads,
    )
    road_geometry = RoadGeometryCatalog(
        centerlines=lowered.centerlines,
        assignments=lowered.assignments,
    )
    road_sections = compile_road_sections(
        links=lowered.links,
        road_geometry=road_geometry,
    )
    node_interfaces = compile_node_interfaces(
        nodes=lowered.nodes,
        links=lowered.links,
        road_geometry=road_geometry,
    )
    turn_authority = compile_turn_authority(
        links=lowered.links,
        road_geometry=road_geometry,
        node_interfaces=node_interfaces,
    )
    permitted_turn_count = sum(
        movement.turn_type is not TurnType.U_TURN_FORBIDDEN for movement in turn_authority.movements
    )
    forbidden_u_turn_count = len(turn_authority.movements) - permitted_turn_count
    topology = PreviewCityTopology(
        nodes=lowered.nodes,
        links=lowered.links,
        turns=turn_authority.movements,
        bridge_crossings=lowered.bridge_crossings,
        road_geometry=road_geometry,
        road_sections=road_sections,
        node_interfaces=node_interfaces,
        metadata={},
    )
    metadata_items = _metadata_items_for(
        network=admitted_network,
        block_authority=admitted_blocks,
        numeric_profiles=lowered.numeric_profiles,
        topology=topology,
        turn_fingerprint=turn_authority.fingerprint,
    )
    topology.metadata = dict(metadata_items)
    validation_report = require_valid_city_map_contract(
        topology,
        seed=admitted_network.seed,
    )
    if validation_report.metrics["weak_component_count"] != 1:
        raise ValueError("compiled topology must have one weak component")
    road_csr = topology.build_csr(validate=False)
    for array_name in (
        "node_ids",
        "link_ids",
        "link_src_node_index",
        "link_dst_node_index",
        "outgoing_indptr",
        "outgoing_link_indices",
        "incoming_indptr",
        "incoming_link_indices",
        "turn_from_link_index",
        "turn_to_link_index",
        "turn_base_priority",
        "turn_is_forbidden",
    ):
        array = getattr(road_csr, array_name)
        if type(array) is not np.ndarray:
            raise TypeError(f"CSR {array_name} must be an exact NumPy array")
        array.setflags(write=False)
    return _new_compiled_wrapper(
        schema_version="scalable_topology_adapter_v1",
        numeric_profile_policy_version="scalable_v2_numeric_profiles_v1",
        topology=topology,
        road_csr=road_csr,
        numeric_profiles=lowered.numeric_profiles,
        road_crosswalk=lowered.road_crosswalk,
        structure_group_crosswalk=lowered.structure_group_crosswalk,
        failure_group_crosswalk=lowered.failure_group_crosswalk,
        metadata_items=metadata_items,
        source_network_fingerprint=admitted_network.fingerprint,
        source_block_authority_fingerprint=admitted_blocks.fingerprint,
        terrain_fingerprint=admitted_network.terrain.fingerprint,
        scale_fingerprint=admitted_network.scale_fingerprint,
        style_fingerprint=admitted_network.style_fingerprint,
        road_geometry_fingerprint=road_geometry.fingerprint,
        road_section_fingerprint=road_sections.fingerprint,
        node_interface_fingerprint=node_interfaces.fingerprint,
        turn_authority_fingerprint=turn_authority.fingerprint,
        source_node_count=len(admitted_network.nodes),
        source_physical_road_count=len(admitted_network.roads),
        source_block_count=len(admitted_blocks.blocks),
        compiled_node_count=len(lowered.nodes),
        compiled_link_count=len(lowered.links),
        compiled_turn_count=len(turn_authority.movements),
        permitted_turn_count=permitted_turn_count,
        forbidden_u_turn_count=forbidden_u_turn_count,
        bridge_crossing_count=len(lowered.bridge_crossings),
    )


def _require_canonical_csr(
    road_csr: RoadNetworkCSR,
    *,
    topology: PreviewCityTopology,
) -> None:
    if type(road_csr) is not RoadNetworkCSR:
        raise TypeError("road_csr must be an exact RoadNetworkCSR")
    if road_csr.nodes != topology.nodes:
        raise ValueError("CSR node rows differ from current topology")
    if road_csr.links != topology.links:
        raise ValueError("CSR link rows differ from current topology")
    if road_csr.turns != topology.turns:
        raise ValueError("CSR turn rows differ from current topology")
    if road_csr.bridge_crossings != topology.bridge_crossings:
        raise ValueError("CSR bridge rows differ from current topology")

    node_id_to_index = {node.node_id: index for index, node in enumerate(topology.nodes)}
    link_id_to_index = {link.link_id: index for index, link in enumerate(topology.links)}
    if road_csr.node_id_to_index != node_id_to_index:
        raise ValueError("CSR node index mapping is not canonical")
    if road_csr.link_id_to_index != link_id_to_index:
        raise ValueError("CSR link index mapping is not canonical")

    def adjacency_arrays(
        endpoint_indices: tuple[int, ...],
    ) -> tuple[np.ndarray, np.ndarray]:
        buckets: list[list[int]] = [[] for _ in topology.nodes]
        for link_index, node_index in enumerate(endpoint_indices):
            buckets[node_index].append(link_index)
        indptr = [0]
        indices: list[int] = []
        for bucket in buckets:
            indices.extend(bucket)
            indptr.append(len(indices))
        return (
            np.asarray(indptr, dtype=np.int32),
            np.asarray(indices, dtype=np.int32),
        )

    src_indices = tuple(node_id_to_index[link.src_node_id] for link in topology.links)
    dst_indices = tuple(node_id_to_index[link.dst_node_id] for link in topology.links)
    outgoing_indptr, outgoing_indices = adjacency_arrays(src_indices)
    incoming_indptr, incoming_indices = adjacency_arrays(dst_indices)
    expected_arrays = {
        "node_ids": np.asarray(
            [node.node_id for node in topology.nodes],
            dtype=np.int32,
        ),
        "link_ids": np.asarray(
            [link.link_id for link in topology.links],
            dtype=np.int32,
        ),
        "link_src_node_index": np.asarray(src_indices, dtype=np.int32),
        "link_dst_node_index": np.asarray(dst_indices, dtype=np.int32),
        "outgoing_indptr": outgoing_indptr,
        "outgoing_link_indices": outgoing_indices,
        "incoming_indptr": incoming_indptr,
        "incoming_link_indices": incoming_indices,
        "turn_from_link_index": np.asarray(
            [link_id_to_index[movement.from_link_id] for movement in topology.turns],
            dtype=np.int32,
        ),
        "turn_to_link_index": np.asarray(
            [link_id_to_index[movement.to_link_id] for movement in topology.turns],
            dtype=np.int32,
        ),
        "turn_base_priority": np.asarray(
            [movement.base_priority for movement in topology.turns],
            dtype=np.float32,
        ),
        "turn_is_forbidden": np.asarray(
            [movement.turn_type is TurnType.U_TURN_FORBIDDEN for movement in topology.turns],
            dtype=np.bool_,
        ),
    }
    for name, expected in expected_arrays.items():
        observed = getattr(road_csr, name)
        if type(observed) is not np.ndarray:
            raise ValueError(f"CSR array {name} must be an exact NumPy array")
        if observed.dtype != expected.dtype or not np.array_equal(observed, expected):
            raise ValueError(f"CSR array {name} differs from current rows")
        if observed.flags.writeable:
            raise ValueError(f"CSR array {name} must be read-only")

    expected_legal_pairs = {
        (movement.from_link_id, movement.to_link_id): row_index
        for row_index, movement in enumerate(topology.turns)
        if movement.turn_type is not TurnType.U_TURN_FORBIDDEN
    }
    if dict(road_csr.turn_pair_to_index) != expected_legal_pairs:
        raise ValueError("CSR legal turn-row indices are not canonical")


def require_valid_scalable_compiled_topology(
    compiled: ScalableCompiledTopology,
    *,
    network: ScalableStreetNetwork,
    block_authority: ScalableBlockAuthority,
) -> None:
    if type(compiled) is not ScalableCompiledTopology:
        raise TypeError("compiled must be an exact ScalableCompiledTopology")
    admitted_network, admitted_blocks = _admit_scalable_sources(
        network,
        block_authority,
    )
    topology = compiled.topology
    if type(topology) is not PreviewCityTopology:
        raise TypeError("compiled topology must be an exact PreviewCityTopology")
    road_geometry = topology.road_geometry
    road_sections = topology.road_sections
    node_interfaces = topology.node_interfaces
    if type(road_geometry) is not RoadGeometryCatalog:
        raise TypeError("compiled road geometry catalog is not exact")
    if type(road_sections) is not RoadSectionCatalog:
        raise TypeError("compiled road section catalog is not exact")
    if type(node_interfaces) is not NodeInterfaceCatalog:
        raise TypeError("compiled node interface catalog is not exact")

    admitted_lowered = _lower_scalable_records(
        nodes=admitted_network.nodes,
        roads=admitted_network.roads,
    )
    if road_geometry.centerlines != admitted_lowered.centerlines:
        raise ValueError("road geometry centerlines differ from admitted source rows")
    if road_geometry.assignments != admitted_lowered.assignments:
        raise ValueError("road geometry assignments differ from admitted source rows")
    current_geometry = road_geometry
    if current_geometry.fingerprint != compiled.road_geometry_fingerprint:
        raise ValueError("road geometry fingerprint mismatch")
    current_sections = RoadSectionCatalog(
        profiles=tuple(road_sections.profiles),
        assignments=tuple(road_sections.assignments),
    )
    if current_sections != road_sections:
        raise ValueError("road section current rows are not canonical")
    if current_sections.fingerprint != compiled.road_section_fingerprint:
        raise ValueError("road section fingerprint mismatch")
    current_interfaces = NodeInterfaceCatalog(
        interfaces=tuple(node_interfaces.interfaces),
    )
    if current_interfaces != node_interfaces:
        raise ValueError("node interface current rows are not canonical")
    if current_interfaces.fingerprint != compiled.node_interface_fingerprint:
        raise ValueError("node interface fingerprint mismatch")
    current_turns = TurnAuthorityCatalog(tuple(topology.turns))
    if current_turns.movements != topology.turns:
        raise ValueError("turn authority current rows are not canonical")
    if current_turns.fingerprint != compiled.turn_authority_fingerprint:
        raise ValueError("turn authority fingerprint mismatch")

    expected_metadata_items = _metadata_items_for(
        network=admitted_network,
        block_authority=admitted_blocks,
        numeric_profiles=compiled.numeric_profiles,
        topology=topology,
        turn_fingerprint=current_turns.fingerprint,
    )
    if tuple(topology.metadata.items()) != expected_metadata_items:
        raise ValueError("topology metadata differs from source-derived metadata")
    if compiled.metadata_items != expected_metadata_items:
        raise ValueError("wrapper metadata_items differ from source-derived metadata")

    expected_scalar_values = {
        "schema_version": "scalable_topology_adapter_v1",
        "numeric_profile_policy_version": "scalable_v2_numeric_profiles_v1",
        "source_network_fingerprint": admitted_network.fingerprint,
        "source_block_authority_fingerprint": admitted_blocks.fingerprint,
        "terrain_fingerprint": admitted_network.terrain.fingerprint,
        "scale_fingerprint": admitted_network.scale_fingerprint,
        "style_fingerprint": admitted_network.style_fingerprint,
        "road_geometry_fingerprint": current_geometry.fingerprint,
        "road_section_fingerprint": current_sections.fingerprint,
        "node_interface_fingerprint": current_interfaces.fingerprint,
        "turn_authority_fingerprint": current_turns.fingerprint,
        "source_node_count": len(admitted_network.nodes),
        "source_physical_road_count": len(admitted_network.roads),
        "source_block_count": len(admitted_blocks.blocks),
        "compiled_node_count": len(topology.nodes),
        "compiled_link_count": len(topology.links),
        "compiled_turn_count": len(topology.turns),
        "permitted_turn_count": sum(
            movement.turn_type is not TurnType.U_TURN_FORBIDDEN for movement in topology.turns
        ),
        "forbidden_u_turn_count": sum(
            movement.turn_type is TurnType.U_TURN_FORBIDDEN for movement in topology.turns
        ),
        "bridge_crossing_count": len(topology.bridge_crossings),
    }
    for name, expected in expected_scalar_values.items():
        if getattr(compiled, name) != expected:
            raise ValueError(f"compiled {name} differs from current authority")

    require_valid_city_map_contract(
        topology,
        seed=admitted_network.seed,
    )
    _require_canonical_csr(compiled.road_csr, topology=topology)
    if compiled.fingerprint != _compiled_fingerprint(compiled):
        raise ValueError("compiled wrapper fingerprint mismatch")
