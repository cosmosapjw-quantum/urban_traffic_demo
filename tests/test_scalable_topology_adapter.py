from __future__ import annotations

import hashlib
import inspect
import subprocess
import sys

import pytest


def _node(
    node_id: int,
    x_mm: int,
    y_mm: int,
    *,
    layer: int = 0,
    semantic_role: str = "test_node",
):
    from metroflow.city.scalable_topology import PhysicalNodeRecord

    semantic_id = hashlib.sha256(
        f"node:{node_id}:{x_mm}:{y_mm}:{layer}:{semantic_role}".encode()
    ).hexdigest()
    return PhysicalNodeRecord(
        node_id=node_id,
        semantic_id=semantic_id,
        x_mm=x_mm,
        y_mm=y_mm,
        layer=layer,
        semantic_role=semantic_role,
    )


def _road(
    road_id: int,
    start_node_id: int,
    end_node_id: int,
    points_mm: tuple[tuple[int, int], ...],
    *,
    hierarchy: str = "local",
    facility: str = "surface",
    layer: int = 0,
    access_directions: frozenset[str] = frozenset({"forward", "reverse"}),
    layer_transition: tuple[int, int] | None = None,
    structure_group: str | None = None,
    failure_group: str | None = None,
    provenance: str = "synthetic:test",
    semantic_role: str = "test_road",
    ramp_purpose: object | None = None,
):
    from metroflow.city.scalable_topology import (
        FacilityKind,
        PhysicalRoadRecord,
        RoadHierarchy,
    )

    facility_kind = FacilityKind(facility)
    hierarchy_kind = RoadHierarchy(hierarchy)
    profile_id = (
        "v2:ramp"
        if facility_kind is FacilityKind.RAMP
        else f"v2:{facility_kind.value}:{hierarchy_kind.value}"
    )
    semantic_id = hashlib.sha256(
        repr(
            (
                "road",
                road_id,
                start_node_id,
                end_node_id,
                points_mm,
                hierarchy,
                facility,
                layer,
                tuple(sorted(access_directions)),
                layer_transition,
                structure_group,
                failure_group,
                provenance,
                semantic_role,
                None if ramp_purpose is None else str(ramp_purpose),
            )
        ).encode()
    ).hexdigest()
    return PhysicalRoadRecord(
        road_id=road_id,
        semantic_id=semantic_id,
        start_node_id=start_node_id,
        end_node_id=end_node_id,
        points_mm=points_mm,
        hierarchy=hierarchy_kind,
        facility=facility_kind,
        layer=layer,
        access_directions=access_directions,
        layer_transition=layer_transition,
        structure_group=structure_group,
        failure_group=failure_group,
        profile_id=profile_id,
        provenance=provenance,
        semantic_role=semantic_role,
        ramp_purpose=ramp_purpose,
    )


def _build_block_authority_from_records(*, network, roads):
    from metroflow.city.scalable_blocks import (
        _build_block_authority_from_records as build_from_records,
    )

    return build_from_records(
        nodes=network.nodes,
        roads=tuple(roads),
        source_network_fingerprint=network.fingerprint,
        extent_mm=network.extent_mm,
        tile_coordinates=network.tile_coordinates,
    )


@pytest.fixture(scope="module")
def public_sources():
    from metroflow.city.scale import CityScaleSpec
    from metroflow.city.scalable_blocks import build_scalable_block_authority
    from metroflow.city.scalable_topology import build_scalable_street_network

    network = build_scalable_street_network(
        CityScaleSpec(100_000, 40.0),
        "grid_core",
        17,
    )
    return network, build_scalable_block_authority(network)


@pytest.fixture(scope="module")
def public_compiled(public_sources):
    from metroflow.city.scalable_topology_adapter import compile_scalable_topology

    network, blocks = public_sources
    return (
        network,
        blocks,
        compile_scalable_topology(network, block_authority=blocks),
    )


@pytest.fixture(scope="module")
def river_compiled():
    from metroflow.city.scale import CityScaleSpec
    from metroflow.city.scalable_blocks import build_scalable_block_authority
    from metroflow.city.scalable_topology import build_scalable_street_network
    from metroflow.city.scalable_topology_adapter import compile_scalable_topology

    network = build_scalable_street_network(
        CityScaleSpec(100_000, 40.0),
        "river_constrained",
        17,
    )
    blocks = build_scalable_block_authority(network)
    return compile_scalable_topology(network, block_authority=blocks)


def test_scalable_topology_adapter_public_api_is_exact() -> None:
    import metroflow.city.scalable_topology_adapter as adapter
    from metroflow.city.scalable_blocks import ScalableBlockAuthority
    from metroflow.city.scalable_topology import ScalableStreetNetwork

    assert adapter.__all__ == (
        "ScalableCompiledTopology",
        "ScalableGroupCrosswalk",
        "ScalableNumericProfile",
        "ScalableRoadCrosswalk",
        "compile_scalable_topology",
        "require_valid_scalable_compiled_topology",
    )

    for name in adapter.__all__[:4]:
        value = getattr(adapter, name)
        assert inspect.isclass(value)
        assert value.__module__ == adapter.__name__

    compile_signature = inspect.signature(adapter.compile_scalable_topology)
    assert tuple(compile_signature.parameters) == ("network", "block_authority")
    assert compile_signature.parameters["network"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert compile_signature.parameters["block_authority"].kind is inspect.Parameter.KEYWORD_ONLY
    assert compile_signature.parameters["block_authority"].default is inspect.Parameter.empty
    assert inspect.get_annotations(
        adapter.compile_scalable_topology,
        eval_str=True,
    ) == {
        "network": ScalableStreetNetwork,
        "block_authority": ScalableBlockAuthority,
        "return": adapter.ScalableCompiledTopology,
    }

    validator_signature = inspect.signature(adapter.require_valid_scalable_compiled_topology)
    assert tuple(validator_signature.parameters) == (
        "compiled",
        "network",
        "block_authority",
    )
    assert (
        validator_signature.parameters["compiled"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    )
    assert validator_signature.parameters["network"].kind is inspect.Parameter.KEYWORD_ONLY
    assert validator_signature.parameters["block_authority"].kind is inspect.Parameter.KEYWORD_ONLY
    assert inspect.get_annotations(
        adapter.require_valid_scalable_compiled_topology,
        eval_str=True,
    ) == {
        "compiled": adapter.ScalableCompiledTopology,
        "network": ScalableStreetNetwork,
        "block_authority": ScalableBlockAuthority,
        "return": None,
    }


def test_pure_lowering_preserves_curved_geometry_and_expands_directions() -> None:
    from dataclasses import fields, is_dataclass

    import metroflow.city.scalable_topology_adapter as adapter
    from metroflow.city.graph import RoadClass

    nodes = (
        _node(0, 0, 0),
        _node(1, 3_000, 0),
    )
    road = _road(
        0,
        0,
        1,
        ((0, 0), (1_000, 1_500), (3_000, 0)),
        hierarchy="arterial",
    )

    lowered = adapter._lower_scalable_records(
        nodes=nodes,
        roads=(road,),
    )

    assert is_dataclass(lowered)
    assert tuple(field.name for field in fields(lowered)) == (
        "nodes",
        "links",
        "centerlines",
        "assignments",
        "numeric_profiles",
        "road_crosswalk",
        "structure_group_crosswalk",
        "failure_group_crosswalk",
        "bridge_crossings",
    )
    assert tuple(field.name for field in fields(adapter.ScalableNumericProfile)) == (
        "profile_id",
        "lanes_per_direction",
        "free_flow_speed_mps",
        "capacity_veh_per_second",
        "operational_road_class",
        "section_roadside_profile",
        "median_when_bidirectional",
    )
    assert tuple(field.name for field in fields(adapter.ScalableGroupCrosswalk)) == (
        "semantic_group",
        "dense_group_id",
        "member_physical_road_ids",
    )
    assert tuple(field.name for field in fields(adapter.ScalableRoadCrosswalk)) == (
        "physical_road_id",
        "road_semantic_id",
        "hierarchy",
        "facility",
        "profile_id",
        "layer",
        "layer_transition",
        "access_directions",
        "provenance",
        "geometry_id",
        "centerline_source_ref",
        "forward_link_id",
        "reverse_link_id",
        "structure_group",
            "structure_group_id",
            "failure_group",
            "bridge_group_id",
            "ramp_purpose",
        )
    assert tuple(profile.profile_id for profile in lowered.numeric_profiles) == (
        "v2:bridge:arterial",
        "v2:bridge:collector",
        "v2:bridge:expressway",
        "v2:bridge:local",
        "v2:mainline",
        "v2:ramp",
        "v2:surface:arterial",
        "v2:surface:collector",
        "v2:surface:expressway",
        "v2:surface:local",
        "v2:tunnel:arterial",
        "v2:tunnel:collector",
        "v2:tunnel:expressway",
        "v2:tunnel:local",
    )
    arterial = next(
        profile
        for profile in lowered.numeric_profiles
        if profile.profile_id == "v2:surface:arterial"
    )
    assert (
        arterial.lanes_per_direction,
        arterial.free_flow_speed_mps,
        arterial.capacity_veh_per_second,
        arterial.operational_road_class,
        arterial.section_roadside_profile,
        arterial.median_when_bidirectional,
    ) == (2, 16.7, 1.10, RoadClass.ARTERIAL, "urban", True)

    assert tuple((node.node_id, node.x, node.y) for node in lowered.nodes) == (
        (0, 0.0, 0.0),
        (1, 3.0, 0.0),
    )
    assert len(lowered.centerlines) == 1
    assert lowered.centerlines[0].points_m == (
        (0.0, 0.0),
        (1.0, 1.5),
        (3.0, 0.0),
    )
    assert tuple(
        (link.link_id, link.src_node_id, link.dst_node_id, link.physical_road_id)
        for link in lowered.links
    ) == ((0, 0, 1, 0), (1, 1, 0, 0))
    assert tuple(
        (assignment.link_id, assignment.geometry_id, assignment.reversed)
        for assignment in lowered.assignments
    ) == ((0, 0, False), (1, 0, True))
    assert len(lowered.road_crosswalk) == 1
    crosswalk = lowered.road_crosswalk[0]
    assert crosswalk.physical_road_id == 0
    assert crosswalk.road_semantic_id == road.semantic_id
    assert crosswalk.access_directions == ("forward", "reverse")
    assert (crosswalk.forward_link_id, crosswalk.reverse_link_id) == (0, 1)
    assert lowered.structure_group_crosswalk == ()
    assert lowered.failure_group_crosswalk == ()
    assert lowered.bridge_crossings == ()

    mainline_nodes = (
        _node(0, 0, 0, layer=1),
        _node(1, 2_000, 0, layer=1),
    )
    mainline_road = _road(
        0,
        0,
        1,
        ((0, 0), (2_000, 0)),
        hierarchy="expressway",
        facility="mainline",
        layer=1,
    )
    mainline_lowered = adapter._lower_scalable_records(
        nodes=mainline_nodes,
        roads=(mainline_road,),
    )
    assert mainline_road.profile_id == "v2:mainline:expressway"
    assert mainline_lowered.road_crosswalk[0].profile_id == "v2:mainline"
    assert mainline_lowered.links[0].road_class is RoadClass.EXPRESSWAY


def test_source_embedding_is_cross_bound_before_lowering(
    public_sources,
    monkeypatch,
) -> None:
    from dataclasses import replace

    import metroflow.city.scalable_topology_adapter as adapter
    from metroflow.city.scalable_blocks import validate_scalable_block_authority
    from metroflow.city.scalable_topology import FacilityKind

    network, blocks = public_sources
    source_edge = next(
        edge
        for edge in blocks.embedding_edges
        if network.roads[edge.source_road_id].facility is FacilityKind.SURFACE
    )
    source_road = network.roads[source_edge.source_road_id]
    alternate_road = replace(
        source_road,
        facility=FacilityKind.BRIDGE,
        profile_id=f"v2:bridge:{source_road.hierarchy.value}",
        structure_group="alternate-structure",
        failure_group="alternate-failure",
    )
    alternate_roads = tuple(
        alternate_road if road.road_id == source_road.road_id else road for road in network.roads
    )
    alternate = _build_block_authority_from_records(
        network=network,
        roads=alternate_roads,
    )
    validate_scalable_block_authority(alternate)

    def fail_if_lowered(*, nodes, roads):
        raise AssertionError("lowering was reached before source admission")

    monkeypatch.setattr(adapter, "_lower_scalable_records", fail_if_lowered)
    with pytest.raises(ValueError, match="embedding"):
        adapter.compile_scalable_topology(network, block_authority=alternate)


def test_structure_and_failure_crosswalks_are_independent_at_equal_counts() -> None:
    from metroflow.city.scalable_topology_adapter import _lower_scalable_records

    nodes = tuple(_node(node_id, node_id * 2_000, (node_id % 2) * 1_000) for node_id in range(8))
    group_rows = (
        ("deck-shared", "pier-shared"),
        ("deck-shared", "pier-other"),
        ("deck-other", "pier-shared"),
        ("deck-other", "pier-other"),
    )
    roads = tuple(
        _road(
            road_id,
            road_id * 2,
            road_id * 2 + 1,
            (
                nodes[road_id * 2].point_mm,
                nodes[road_id * 2 + 1].point_mm,
            ),
            hierarchy="arterial",
            facility="bridge",
            structure_group=structure_group,
            failure_group=failure_group,
        )
        for road_id, (structure_group, failure_group) in enumerate(group_rows)
    )

    lowered = _lower_scalable_records(nodes=nodes, roads=roads)

    assert tuple(
        (
            row.semantic_group,
            row.dense_group_id,
            row.member_physical_road_ids,
        )
        for row in lowered.structure_group_crosswalk
    ) == (
        ("deck-other", 0, (2, 3)),
        ("deck-shared", 1, (0, 1)),
    )
    assert tuple(
        (
            row.semantic_group,
            row.dense_group_id,
            row.member_physical_road_ids,
        )
        for row in lowered.failure_group_crosswalk
    ) == (
        ("pier-other", 0, (1, 3)),
        ("pier-shared", 1, (0, 2)),
    )
    assert tuple(
        (
            row.physical_road_id,
            row.structure_group_id,
            row.bridge_group_id,
        )
        for row in lowered.road_crosswalk
    ) == ((0, 1, 1), (1, 1, 0), (2, 0, 1), (3, 0, 0))
    assert tuple(
        (
            crossing.bridge_group_id,
            crossing.link_ids,
            crossing.crossing_name,
        )
        for crossing in lowered.bridge_crossings
    ) == (
        (0, (2, 3, 6, 7), "pier-other"),
        (1, (0, 1, 4, 5), "pier-shared"),
    )
    bridge_group_by_link = {link.link_id: link.bridge_group_id for link in lowered.links}
    assert bridge_group_by_link == {
        0: 1,
        1: 1,
        2: 0,
        3: 0,
        4: 1,
        5: 1,
        6: 0,
        7: 0,
    }


def test_public_compile_keeps_full_turn_row_indices_in_legal_csr(
    public_sources,
) -> None:
    from metroflow.city.graph import TurnType
    from metroflow.city.scalable_topology_adapter import compile_scalable_topology

    network, blocks = public_sources
    compiled = compile_scalable_topology(network, block_authority=blocks)

    assert compiled.topology.turns == compiled.road_csr.turns
    assert compiled.compiled_turn_count == len(compiled.topology.turns)
    assert compiled.forbidden_u_turn_count > 0
    assert compiled.permitted_turn_count > 0
    assert (
        compiled.permitted_turn_count + compiled.forbidden_u_turn_count
        == compiled.compiled_turn_count
    )
    for row_index, movement in enumerate(compiled.topology.turns):
        pair = (movement.from_link_id, movement.to_link_id)
        if movement.turn_type is TurnType.U_TURN_FORBIDDEN:
            assert pair not in compiled.road_csr.turn_pair_to_index
        else:
            assert compiled.road_csr.turn_pair_to_index[pair] == row_index


@pytest.mark.parametrize(
    "projection_kind",
    ("reverse_embedding", "foreign_ramp_semantic"),
)
def test_fully_resealed_source_projection_is_rejected_before_lowering(
    public_sources,
    monkeypatch,
    projection_kind: str,
) -> None:
    from dataclasses import replace

    import metroflow.city.scalable_topology_adapter as adapter
    from metroflow.city.scalable_blocks import validate_scalable_block_authority
    from metroflow.city.scalable_topology import FacilityKind

    network, blocks = public_sources
    roads = network.roads
    if projection_kind == "reverse_embedding":
        edge = blocks.embedding_edges[0]
        road = network.roads[edge.source_road_id]
        swapped_directions = frozenset(
            "reverse" if direction == "forward" else "forward"
            for direction in road.access_directions
        )
        forged_road = replace(
            road,
            start_node_id=road.end_node_id,
            end_node_id=road.start_node_id,
            points_mm=tuple(reversed(road.points_mm)),
            access_directions=swapped_directions,
        )
        expected_message = "embedding source record"
    else:
        road = next(road for road in network.roads if road.facility is FacilityKind.RAMP)
        forged_road = replace(
            road,
            semantic_id=hashlib.sha256(f"foreign-ramp:{road.semantic_id}".encode()).hexdigest(),
        )
        expected_message = "ramp source record"
    forged_roads = tuple(
        forged_road if candidate.road_id == road.road_id else candidate for candidate in roads
    )
    forged = _build_block_authority_from_records(
        network=network,
        roads=forged_roads,
    )
    validate_scalable_block_authority(forged)

    def fail_if_lowered(*, nodes, roads):
        raise AssertionError("hostile projection reached lowering")

    monkeypatch.setattr(adapter, "_lower_scalable_records", fail_if_lowered)
    with pytest.raises(ValueError, match=expected_message):
        adapter.compile_scalable_topology(network, block_authority=forged)


def test_public_validator_rejects_mutable_metadata_and_raw_csr_array(
    public_compiled,
) -> None:
    import numpy as np

    import metroflow.city.scalable_topology_adapter as adapter

    network, blocks, compiled = public_compiled
    metadata = compiled.topology.metadata
    original_capacity_unit = metadata["capacity_source_unit"]
    metadata["capacity_source_unit"] = "vehicles_per_tick"
    try:
        with pytest.raises(ValueError):
            adapter.require_valid_scalable_compiled_topology(
                compiled,
                network=network,
                block_authority=blocks,
            )
    finally:
        metadata["capacity_source_unit"] = original_capacity_unit

    original_node_ids = compiled.road_csr.node_ids
    compiled.road_csr.node_ids = np.asarray(original_node_ids).copy()
    try:
        with pytest.raises(ValueError, match="CSR|array"):
            adapter.require_valid_scalable_compiled_topology(
                compiled,
                network=network,
                block_authority=blocks,
            )
    finally:
        compiled.road_csr.node_ids = original_node_ids


def test_public_validator_recomputes_turn_fingerprint_from_current_rows(
    public_compiled,
) -> None:
    from dataclasses import replace

    import metroflow.city.scalable_topology_adapter as adapter

    network, blocks, compiled = public_compiled
    original_turns = compiled.topology.turns
    compiled.topology.turns = (
        replace(
            original_turns[0],
            base_priority=original_turns[0].base_priority + 0.25,
        ),
        *original_turns[1:],
    )
    try:
        with pytest.raises(ValueError, match="turn"):
            adapter.require_valid_scalable_compiled_topology(
                compiled,
                network=network,
                block_authority=blocks,
            )
    finally:
        compiled.topology.turns = original_turns


def test_public_validator_rejects_self_consistently_resealed_metadata_lie(
    public_compiled,
) -> None:
    import metroflow.city.scalable_topology_adapter as adapter

    network, blocks, compiled = public_compiled
    metadata = compiled.topology.metadata
    original_count = metadata["source_node_count"]
    try:
        metadata["source_node_count"] = original_count + 1
        lying = object.__new__(type(compiled))
        for name in compiled.__slots__:
            object.__setattr__(lying, name, getattr(compiled, name))
        object.__setattr__(lying, "metadata_items", tuple(metadata.items()))
        object.__setattr__(lying, "fingerprint", adapter._compiled_fingerprint(lying))
        with pytest.raises(ValueError, match="metadata|source_node_count"):
            adapter.require_valid_scalable_compiled_topology(
                lying,
                network=network,
                block_authority=blocks,
            )
    finally:
        metadata["source_node_count"] = original_count


def test_private_lowering_covers_all_profiles_layers_and_section_policy() -> None:
    from metroflow.city.graph import RoadClass
    from metroflow.city.scalable_topology_adapter import _lower_scalable_records

    nodes = tuple(
        _node(
            node_id,
            node_id * 1_000,
            (node_id % 3) * 500,
            layer=1 if node_id in {8, 9, 11} else 0,
        )
        for node_id in range(20)
    )
    road_specs = (
        ("surface", "local", 0, None, None, None),
        ("surface", "collector", 0, None, None, None),
        ("surface", "arterial", 0, None, None, None),
        ("surface", "expressway", 0, None, None, None),
        ("mainline", "expressway", 1, None, None, None),
        ("ramp", "arterial", 1, (0, 1), None, None),
        ("bridge", "local", 0, None, "deck-local", "pier-local"),
        (
            "bridge",
            "collector",
            0,
            None,
            "deck-collector",
            "pier-collector",
        ),
        (
            "bridge",
            "arterial",
            0,
            None,
            "deck-arterial",
            "pier-arterial",
        ),
        (
            "bridge",
            "expressway",
            0,
            None,
            "deck-expressway",
            "pier-expressway",
        ),
    )
    roads = tuple(
        _road(
            road_id,
            road_id * 2,
            road_id * 2 + 1,
            (
                nodes[road_id * 2].point_mm,
                nodes[road_id * 2 + 1].point_mm,
            ),
            facility=facility,
            hierarchy=hierarchy,
            layer=layer,
            layer_transition=transition,
            structure_group=structure_group,
            failure_group=failure_group,
        )
        for road_id, (
            facility,
            hierarchy,
            layer,
            transition,
            structure_group,
            failure_group,
        ) in enumerate(road_specs)
    )
    lowered = _lower_scalable_records(nodes=nodes, roads=roads)

    assert tuple(profile.profile_id for profile in lowered.numeric_profiles) == (
        "v2:bridge:arterial",
        "v2:bridge:collector",
        "v2:bridge:expressway",
        "v2:bridge:local",
        "v2:mainline",
        "v2:ramp",
        "v2:surface:arterial",
        "v2:surface:collector",
        "v2:surface:expressway",
        "v2:surface:local",
        "v2:tunnel:arterial",
        "v2:tunnel:collector",
        "v2:tunnel:expressway",
        "v2:tunnel:local",
    )
    assert tuple(row.profile_id for row in lowered.road_crosswalk) == (
        "v2:surface:local",
        "v2:surface:collector",
        "v2:surface:arterial",
        "v2:surface:expressway",
        "v2:mainline",
        "v2:ramp",
        "v2:bridge:local",
        "v2:bridge:collector",
        "v2:bridge:arterial",
        "v2:bridge:expressway",
    )
    assert tuple(centerline.layer for centerline in lowered.centerlines) == tuple(
        spec[2] for spec in road_specs
    )
    policy = {profile.profile_id: profile for profile in lowered.numeric_profiles}
    assert (
        policy["v2:ramp"].operational_road_class,
        policy["v2:ramp"].section_roadside_profile,
        policy["v2:ramp"].median_when_bidirectional,
    ) == (RoadClass.RAMP, "rural", False)
    assert (
        policy["v2:bridge:arterial"].operational_road_class,
        policy["v2:bridge:arterial"].section_roadside_profile,
        policy["v2:bridge:arterial"].median_when_bidirectional,
    ) == (RoadClass.BRIDGE, "limited_access", True)


def test_reverse_only_and_ramp_turns_remain_explicit() -> None:
    from metroflow.city.graph import TurnType
    from metroflow.city.scalable_topology_adapter import _lower_scalable_records
    from metroflow.city.turn_compiler import compile_turn_authority
    from metroflow.map.node_compiler import compile_node_interfaces
    from metroflow.map.road_geometry import RoadGeometryCatalog

    nodes = (
        _node(0, 0, 0),
        _node(1, 1_000, 0),
        _node(2, 1_000, 1_000, layer=1),
        _node(3, 2_000, 1_000, layer=1),
    )
    roads = (
        _road(
            0,
            1,
            0,
            (nodes[1].point_mm, nodes[0].point_mm),
            access_directions=frozenset({"reverse"}),
        ),
        _road(
            1,
            1,
            2,
            (nodes[1].point_mm, nodes[2].point_mm),
            hierarchy="arterial",
            facility="ramp",
            layer=1,
            layer_transition=(0, 1),
        ),
        _road(
            2,
            2,
            3,
            (nodes[2].point_mm, nodes[3].point_mm),
            hierarchy="expressway",
            facility="mainline",
            layer=1,
        ),
    )
    lowered = _lower_scalable_records(nodes=nodes, roads=roads)
    geometry = RoadGeometryCatalog(lowered.centerlines, lowered.assignments)
    interfaces = compile_node_interfaces(
        nodes=lowered.nodes,
        links=lowered.links,
        road_geometry=geometry,
    )
    turns = compile_turn_authority(
        links=lowered.links,
        road_geometry=geometry,
        node_interfaces=interfaces,
    ).movements

    assert lowered.road_crosswalk[0].forward_link_id is None
    assert lowered.road_crosswalk[0].reverse_link_id == 0
    assert lowered.links[0].src_node_id == 0
    assert lowered.links[0].dst_node_id == 1
    assert {movement.turn_type for movement in turns} >= {
        TurnType.RAMP_ON,
        TurnType.RAMP_OFF,
        TurnType.U_TURN_FORBIDDEN,
    }


def test_lowering_admits_a_typed_forward_only_off_ramp() -> None:
    from metroflow.city.scalable_topology import RampPurpose
    from metroflow.city.scalable_topology_adapter import _lower_scalable_records

    nodes = (
        _node(0, 0, 0),
        _node(1, 1_000, 0, layer=1),
    )
    off_ramp = _road(
        0,
        1,
        0,
        (nodes[1].point_mm, nodes[0].point_mm),
        hierarchy="arterial",
        facility="ramp",
        layer=1,
        access_directions=frozenset({"forward"}),
        layer_transition=(0, 1),
        ramp_purpose=RampPurpose.OFF_RAMP,
    )

    lowered = _lower_scalable_records(nodes=nodes, roads=(off_ramp,))

    assert lowered.road_crosswalk[0].ramp_purpose is RampPurpose.OFF_RAMP
    assert lowered.road_crosswalk[0].forward_link_id == 0
    assert lowered.road_crosswalk[0].reverse_link_id is None
    assert (lowered.links[0].src_node_id, lowered.links[0].dst_node_id) == (1, 0)
    assert lowered.links[0].ramp_purpose == RampPurpose.OFF_RAMP.value


@pytest.mark.parametrize(
    (
        "facility",
        "hierarchy",
        "road_layer",
        "start_layer",
        "end_layer",
        "layer_transition",
        "structure_group",
        "failure_group",
    ),
    (
        pytest.param(
            "mainline",
            "local",
            1,
            1,
            1,
            None,
            None,
            None,
            id="mainline-local-1-1-1-None-None-None",
        ),
        pytest.param(
            "surface",
            "local",
            1,
            1,
            1,
            None,
            None,
            None,
            id="surface-local-1-1-1-None-None-None",
        ),
        pytest.param(
            "bridge",
            "arterial",
            0,
            0,
            0,
            None,
            None,
            "failure",
            id="bridge-arterial-0-0-0-None-None-failure",
        ),
        pytest.param(
            "ramp",
            "collector",
            1,
            1,
            0,
            (1, 0),
            None,
            None,
            id="ramp-collector-1-1-0-transition3-None-None",
        ),
        pytest.param(
            "tunnel",
            "local",
            -1,
            -1,
            -1,
            None,
            None,
            None,
            id="tunnel-local--1--1--1-None-None-None",
        ),
    ),
)
def test_private_lowering_rejects_closed_facility_layer_contracts(
    facility: str,
    hierarchy: str,
    road_layer: int,
    start_layer: int,
    end_layer: int,
    layer_transition: tuple[int, int] | None,
    structure_group: str | None,
    failure_group: str | None,
) -> None:
    from metroflow.city.scalable_topology_adapter import _lower_scalable_records

    nodes = (
        _node(0, 0, 0, layer=start_layer),
        _node(1, 1_000, 0, layer=end_layer),
    )
    road = _road(
        0,
        0,
        1,
        (nodes[0].point_mm, nodes[1].point_mm),
        facility=facility,
        hierarchy=hierarchy,
        layer=road_layer,
        layer_transition=layer_transition,
        structure_group=structure_group,
        failure_group=failure_group,
    )
    with pytest.raises(ValueError, match="facility|layer|bridge|ramp|tunnel"):
        _lower_scalable_records(nodes=nodes, roads=(road,))


def test_public_compiler_call_budget_metadata_and_complete_catalogs(
    public_sources,
    monkeypatch,
) -> None:
    import metroflow.city.map_validation as map_validation
    import metroflow.city.scalable_topology_adapter as adapter
    from metroflow.city.generated_map import PreviewCityTopology

    calls = {
        "section": 0,
        "validator_section": 0,
        "node": 0,
        "turn": 0,
        "csr": 0,
    }

    def counted(name, function):
        def wrapper(*args, **kwargs):
            calls[name] += 1
            return function(*args, **kwargs)

        return wrapper

    monkeypatch.setattr(
        adapter,
        "compile_road_sections",
        counted("section", adapter.compile_road_sections),
    )
    monkeypatch.setattr(
        map_validation,
        "compile_road_sections",
        counted("validator_section", map_validation.compile_road_sections),
    )
    monkeypatch.setattr(
        adapter,
        "compile_node_interfaces",
        counted("node", adapter.compile_node_interfaces),
    )
    monkeypatch.setattr(
        adapter,
        "compile_turn_authority",
        counted("turn", adapter.compile_turn_authority),
    )
    monkeypatch.setattr(
        PreviewCityTopology,
        "build_csr",
        counted("csr", PreviewCityTopology.build_csr),
    )
    network, blocks = public_sources
    compiled = adapter.compile_scalable_topology(network, block_authority=blocks)

    assert calls == {
        "section": 1,
        "validator_section": 1,
        "node": 1,
        "turn": 1,
        "csr": 1,
    }
    assert tuple(dict(compiled.metadata_items)) == (
        "engine",
        "topology_mode",
        "adapter_schema_version",
        "numeric_profile_policy_version",
        "turn_authority_policy",
        "seed",
        "style_id",
        "source_network_fingerprint",
        "source_block_authority_fingerprint",
        "block_authority_schema_version",
        "terrain_fingerprint",
        "scale_fingerprint",
        "style_fingerprint",
        "road_geometry_fingerprint",
        "road_section_fingerprint",
        "node_interface_fingerprint",
        "turn_authority_fingerprint",
        "numeric_profile_payload",
        "source_node_count",
        "source_physical_road_count",
        "source_block_count",
        "compiled_node_count",
        "compiled_link_count",
        "physical_centerline_count",
        "geometry_assignment_count",
        "road_section_assignment_count",
        "node_interface_count",
        "turn_authority_pair_count",
        "permitted_turn_movement_count",
        "forbidden_u_turn_count",
        "bridge_crossing_count",
        "weak_component_count",
        "hidden_repair_count",
        "dropped_physical_road_count",
        "dropped_chain_count",
        "connectivity_repair_link_count",
        "connectivity_repair_link_ids",
        "planarization_status",
        "capacity_reference_tick_seconds",
        "capacity_source_unit",
    )
    link_ids = {link.link_id for link in compiled.topology.links}
    assert {
        assignment.link_id for assignment in compiled.topology.road_geometry.assignments
    } == link_ids
    assert {
        assignment.link_id for assignment in compiled.topology.road_sections.assignments
    } == link_ids
    assert len(compiled.topology.node_interfaces.interfaces) == len(compiled.topology.nodes)


def test_public_validator_does_not_reconstruct_road_geometry_catalog(
    public_compiled,
    monkeypatch,
) -> None:
    import metroflow.city.scalable_topology_adapter as adapter
    from metroflow.map.road_geometry import RoadGeometryCatalog

    network, blocks, compiled = public_compiled
    calls = 0
    original_init = RoadGeometryCatalog.__init__

    def counted_init(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(RoadGeometryCatalog, "__init__", counted_init)
    adapter.require_valid_scalable_compiled_topology(
        compiled,
        network=network,
        block_authority=blocks,
    )

    assert calls == 0


def test_public_compile_constructs_road_geometry_catalog_exactly_once(
    public_sources,
    monkeypatch,
) -> None:
    import metroflow.city.scalable_topology_adapter as adapter
    from metroflow.map.road_geometry import RoadGeometryCatalog

    calls = 0
    original_init = RoadGeometryCatalog.__init__

    def counted_init(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(RoadGeometryCatalog, "__init__", counted_init)
    network, blocks = public_sources
    adapter.compile_scalable_topology(network, block_authority=blocks)

    assert calls == 1


def test_wrapper_constructor_rejects_nonexact_csr_nested_rows(
    public_compiled,
) -> None:
    from dataclasses import replace

    from metroflow.city.graph import Node, RoadNetworkCSR

    class DerivedNode(Node):
        pass

    _, _, compiled = public_compiled
    csr = compiled.road_csr
    derived_nodes = tuple(
        DerivedNode(
            node.node_id,
            node.kind,
            node.x,
            node.y,
            node.zone_id,
            node.signal_group_id,
        )
        for node in csr.nodes
    )
    derived_csr = RoadNetworkCSR(
        nodes=derived_nodes,
        links=csr.links,
        turns=csr.turns,
        bridge_crossings=csr.bridge_crossings,
    )
    assert type(derived_csr.nodes[0]) is DerivedNode

    with pytest.raises(TypeError, match="CSR|road_csr"):
        replace(compiled, road_csr=derived_csr)


def test_public_validator_constructs_one_turn_catalog_validation_view(
    public_compiled,
    monkeypatch,
) -> None:
    import metroflow.city.scalable_topology_adapter as adapter
    from metroflow.city.turn_compiler import TurnAuthorityCatalog

    network, blocks, compiled = public_compiled
    calls = 0
    original_init = TurnAuthorityCatalog.__init__

    def counted_init(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(TurnAuthorityCatalog, "__init__", counted_init)
    adapter.require_valid_scalable_compiled_topology(
        compiled,
        network=network,
        block_authority=blocks,
    )

    assert calls == 1


@pytest.mark.parametrize(
    ("crosswalk_name", "road_group_name", "road_group_id_name"),
    (
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
    ),
)
def test_wrapper_constructor_rejects_duplicate_group_semantics(
    river_compiled,
    crosswalk_name: str,
    road_group_name: str,
    road_group_id_name: str,
) -> None:
    from dataclasses import replace

    import metroflow.city.scalable_topology_adapter as adapter

    rows = getattr(river_compiled, crosswalk_name)
    assert len(rows) >= 2
    assert {
        getattr(row, road_group_name)
        for row in river_compiled.road_crosswalk
        if getattr(row, road_group_id_name) is not None
    } == {row.semantic_group for row in rows}
    duplicate = replace(rows[1], semantic_group=rows[0].semantic_group)
    values = {name: getattr(river_compiled, name) for name in river_compiled.__slots__[:-1]}
    values[crosswalk_name] = (rows[0], duplicate, *rows[2:])

    with pytest.raises(ValueError, match="duplicate|unique|group"):
        adapter._new_compiled_wrapper(**values)


def test_wrapper_constructor_rejects_resealed_turn_distribution_counts(
    public_compiled,
) -> None:
    from dataclasses import replace

    import metroflow.city.scalable_topology_adapter as adapter

    _, _, compiled = public_compiled
    metadata = dict(compiled.metadata_items)
    metadata["permitted_turn_movement_count"] += 1
    metadata["forbidden_u_turn_count"] -= 1
    topology = replace(compiled.topology, metadata=metadata)
    values = {name: getattr(compiled, name) for name in compiled.__slots__[:-1]}
    values.update(
        topology=topology,
        metadata_items=tuple(metadata.items()),
        permitted_turn_count=compiled.permitted_turn_count + 1,
        forbidden_u_turn_count=compiled.forbidden_u_turn_count - 1,
    )

    with pytest.raises(ValueError, match="turn|count"):
        adapter._new_compiled_wrapper(**values)


def test_wrapper_constructor_rejects_resealed_source_node_count_mismatch(
    public_compiled,
) -> None:
    from dataclasses import replace

    import metroflow.city.scalable_topology_adapter as adapter

    _, _, compiled = public_compiled
    metadata = dict(compiled.metadata_items)
    metadata["source_node_count"] += 1
    values = {name: getattr(compiled, name) for name in compiled.__slots__[:-1]}
    values.update(
        topology=replace(compiled.topology, metadata=metadata),
        metadata_items=tuple(metadata.items()),
        source_node_count=compiled.source_node_count + 1,
    )

    with pytest.raises(ValueError, match="source|node|count"):
        adapter._new_compiled_wrapper(**values)


@pytest.mark.parametrize(
    "metadata_name",
    (
        "physical_centerline_count",
        "geometry_assignment_count",
        "road_section_assignment_count",
        "node_interface_count",
        "turn_authority_pair_count",
        "bridge_crossing_count",
    ),
)
def test_wrapper_constructor_rejects_resealed_derived_metadata_count(
    public_compiled,
    metadata_name: str,
) -> None:
    from dataclasses import replace

    import metroflow.city.scalable_topology_adapter as adapter

    _, _, compiled = public_compiled
    metadata = dict(compiled.metadata_items)
    metadata[metadata_name] += 1
    values = {name: getattr(compiled, name) for name in compiled.__slots__[:-1]}
    values.update(
        topology=replace(compiled.topology, metadata=metadata),
        metadata_items=tuple(metadata.items()),
    )
    scalar_name = {
        "turn_authority_pair_count": "compiled_turn_count",
        "bridge_crossing_count": "bridge_crossing_count",
    }.get(metadata_name)
    if scalar_name is not None:
        values[scalar_name] += 1

    with pytest.raises(ValueError, match="metadata|count"):
        adapter._new_compiled_wrapper(**values)


@pytest.mark.parametrize(
    "catalog_row",
    ("centerline", "geometry_assignment", "section_assignment", "node_interface"),
)
def test_wrapper_constructor_rejects_resealed_catalog_coverage_count(
    public_compiled,
    catalog_row: str,
) -> None:
    from dataclasses import replace

    import metroflow.city.scalable_topology_adapter as adapter
    from metroflow.map.node_compiler import NodeInterfaceCatalog
    from metroflow.map.road_geometry import RoadGeometryCatalog
    from metroflow.map.section_compiler import RoadSectionCatalog

    _, _, compiled = public_compiled
    topology = compiled.topology
    geometry = topology.road_geometry
    sections = topology.road_sections
    interfaces = topology.node_interfaces
    metadata = dict(compiled.metadata_items)
    replacements = {}
    if catalog_row == "centerline":
        last = geometry.centerlines[-1]
        extra = replace(
            last,
            geometry_id=last.geometry_id + 1,
            source_ref=f"{last.source_ref}:extra",
            corridor_id=last.corridor_id + 1,
        )
        geometry = RoadGeometryCatalog(geometry.centerlines + (extra,), geometry.assignments)
        metadata["physical_centerline_count"] += 1
    elif catalog_row == "geometry_assignment":
        geometry = RoadGeometryCatalog(geometry.centerlines, geometry.assignments[:-1])
        metadata["geometry_assignment_count"] -= 1
    elif catalog_row == "section_assignment":
        sections = RoadSectionCatalog(sections.profiles, sections.assignments[:-1])
        metadata["road_section_assignment_count"] -= 1
    else:
        interfaces = NodeInterfaceCatalog(interfaces.interfaces[:-1])
        metadata["node_interface_count"] -= 1
    metadata["road_geometry_fingerprint"] = geometry.fingerprint
    metadata["road_section_fingerprint"] = sections.fingerprint
    metadata["node_interface_fingerprint"] = interfaces.fingerprint
    replacements.update(
        road_geometry=geometry,
        road_sections=sections,
        node_interfaces=interfaces,
        metadata=metadata,
    )
    values = {name: getattr(compiled, name) for name in compiled.__slots__[:-1]}
    values.update(
        topology=replace(topology, **replacements),
        metadata_items=tuple(metadata.items()),
        road_geometry_fingerprint=geometry.fingerprint,
        road_section_fingerprint=sections.fingerprint,
        node_interface_fingerprint=interfaces.fingerprint,
    )

    with pytest.raises(ValueError, match="coverage|catalog|count"):
        adapter._new_compiled_wrapper(**values)


@pytest.mark.parametrize(
    "catalog_row",
    (
        "centerline",
        "geometry_assignment",
        "section_profile",
        "section_assignment",
        "node_interface",
    ),
)
def test_wrapper_constructor_rejects_nonexact_catalog_nested_rows(
    public_compiled,
    catalog_row: str,
) -> None:
    from dataclasses import fields, replace

    import metroflow.city.scalable_topology_adapter as adapter
    from metroflow.map.node_compiler import NodeInterfaceCatalog
    from metroflow.map.road_geometry import RoadGeometryCatalog
    from metroflow.map.section_compiler import RoadSectionCatalog

    def derived(row):
        derived_type = type(f"Derived{type(row).__name__}", (type(row),), {})
        return derived_type(
            **{field.name: getattr(row, field.name) for field in fields(row) if field.init}
        )

    _, _, compiled = public_compiled
    topology = compiled.topology
    geometry = topology.road_geometry
    sections = topology.road_sections
    interfaces = topology.node_interfaces
    if catalog_row == "centerline":
        geometry = RoadGeometryCatalog(
            (derived(geometry.centerlines[0]), *geometry.centerlines[1:]),
            geometry.assignments,
        )
    elif catalog_row == "geometry_assignment":
        geometry = RoadGeometryCatalog(
            geometry.centerlines,
            (derived(geometry.assignments[0]), *geometry.assignments[1:]),
        )
    elif catalog_row == "section_profile":
        sections = RoadSectionCatalog(
            (derived(sections.profiles[0]), *sections.profiles[1:]),
            sections.assignments,
        )
    elif catalog_row == "section_assignment":
        sections = RoadSectionCatalog(
            sections.profiles,
            (derived(sections.assignments[0]), *sections.assignments[1:]),
        )
    else:
        interfaces = NodeInterfaceCatalog(
            (derived(interfaces.interfaces[0]), *interfaces.interfaces[1:])
        )
    values = {name: getattr(compiled, name) for name in compiled.__slots__[:-1]}
    values["topology"] = replace(
        topology,
        road_geometry=geometry,
        road_sections=sections,
        node_interfaces=interfaces,
    )

    with pytest.raises(TypeError, match="exact|catalog|row"):
        adapter._new_compiled_wrapper(**values)


def test_isolated_import_never_calls_generation_repair_or_runtime() -> None:
    code = r"""
import importlib, sys
import metroflow.city as city
import metroflow.city.connectivity as connectivity
import metroflow.city.scalable_blocks as blocks
import metroflow.map.road_geometry as geometry
def forbidden(*args, **kwargs):
    raise AssertionError("forbidden generation or repair call")
for name in ("repair_weak_connectivity", "build_hierarchical_street_skeleton", "build_continuous_local_fabric", "build_terrain_field", "build_urban_form_field"):
    setattr(city, name, forbidden)
connectivity.repair_weak_connectivity = forbidden
blocks.build_scalable_block_authority = forbidden
geometry.build_endpoint_geometry_catalog = forbidden
importlib.import_module("metroflow.city.scalable_topology_adapter")
exact = ("metroflow.city.topology_finalizer", "metroflow.city.planarization", "metroflow.city.planar_blocks", "metroflow.city.block_land_use", "metroflow.city.generator_v2", "metroflow.city.realistic_city", "metroflow.sim" + ".config", "jax", "torch", "_metroflow_rust")
prefixes = ("metroflow.sim", "metroflow.demand", "metroflow.landuse", "metroflow.routing", "metroflow.backends")
assert not set(exact) & set(sys.modules)
assert not any(name == prefix or name.startswith(prefix + ".")
               for name in sys.modules for prefix in prefixes)
"""
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "style_id",
    (
        "ring_radial",
        "grid_core",
        "polycentric_tod",
        "river_constrained",
        "superblock_mixed",
        "organic",
    ),
)
def test_all_generated_styles_compile_without_repair_or_nondeterminism(
    style_id: str,
    monkeypatch,
) -> None:
    from metroflow.city.scale import CityScaleSpec
    from metroflow.city.scalable_blocks import build_scalable_block_authority
    from metroflow.city.scalable_topology import build_scalable_street_network
    from metroflow.city.scalable_topology_adapter import compile_scalable_topology
    from metroflow.city import connectivity
    from metroflow.map import road_geometry

    def forbidden(*args, **kwargs):
        raise AssertionError("repair or endpoint reconstruction called")

    monkeypatch.setattr(connectivity, "repair_weak_connectivity", forbidden)
    monkeypatch.setattr(road_geometry, "build_endpoint_geometry_catalog", forbidden)
    network = build_scalable_street_network(CityScaleSpec(100_000, 40.0), style_id, 17)
    blocks = build_scalable_block_authority(network)
    first = compile_scalable_topology(network, block_authority=blocks)
    second = compile_scalable_topology(network, block_authority=blocks)
    assert first.fingerprint == second.fingerprint
    assert dict(first.metadata_items)["connectivity_repair_link_count"] == 0


def test_wrapper_identity_binds_numeric_link_bridge_metadata_and_block_seal(
    public_compiled,
    river_compiled,
) -> None:
    import metroflow.city.scalable_topology_adapter as adapter
    from metroflow.city.scale import CityScaleSpec
    from metroflow.city.scalable_blocks import build_scalable_block_authority
    from metroflow.city.scalable_topology import build_scalable_street_network

    network, blocks, compiled = public_compiled
    river_network = build_scalable_street_network(
        CityScaleSpec(100_000, 40.0), "river_constrained", 17
    )
    river_blocks = build_scalable_block_authority(river_network)
    public = (network, blocks, compiled)
    river = (river_network, river_blocks, river_compiled)
    for source_network, source_blocks, current in (public, river):
        adapter.require_valid_scalable_compiled_topology(
            current, network=source_network, block_authority=source_blocks
        )

    topology = compiled.topology
    csr = compiled.road_csr
    roads = river_compiled.road_crosswalk
    link = topology.links[0]
    profile = compiled.numeric_profiles[0]
    road = compiled.road_crosswalk[0]
    structure = river_compiled.structure_group_crosswalk[0]
    failure = river_compiled.failure_group_crosswalk[0]
    bridge = river_compiled.topology.bridge_crossings[0]
    centerline = topology.road_geometry.centerlines[0]
    profile_metadata = dict(compiled.metadata_items)
    profile_payload = list(profile_metadata["numeric_profile_payload"])
    profile_payload[0] = (
        *profile_payload[0][:2],
        profile.free_flow_speed_mps + 1.0,
        *profile_payload[0][3:],
    )
    profile_metadata["numeric_profile_payload"] = tuple(profile_payload)
    capacity_metadata = dict(compiled.metadata_items)
    capacity_metadata["capacity_source_unit"] = "changed"
    structure_name = f"{structure.semantic_group}:changed"
    failure_name = f"{failure.semantic_group}:changed"

    def group_changes(group, field, changed):
        semantic = group.semantic_group
        members = ((row, field, changed) for row in roads if getattr(row, field) == semantic)
        return ((group, "semantic_group", changed), *members)

    structure_changes = group_changes(structure, "structure_group", structure_name)
    failure_changes = group_changes(failure, "failure_group", failure_name)
    profile_changes = (
        (profile, "free_flow_speed_mps", profile.free_flow_speed_mps + 1.0),
        (topology, "metadata", profile_metadata),
        (compiled, "metadata_items", tuple(profile_metadata.items())),
    )
    cases = (
        ("link", public, ((link, "free_flow_speed_mps", link.free_flow_speed_mps + 1.0),)),
        ("numeric_profile", public, profile_changes),
        ("road_crosswalk", public, ((road, "provenance", "synthetic:changed"),)),
        ("structure_group_crosswalk", river, structure_changes),
        ("failure_group_crosswalk", river, failure_changes),
        ("bridge", river, ((bridge, "crossing_name", f"{bridge.crossing_name}:changed"),)),
        (
            "topology_cache_key",
            public,
            (
                (compiled, "terrain_fingerprint", "f" * 64),
                (csr, "topology_cache_key", ("forged",)),
            ),
        ),
        (
            "source_block_fingerprint",
            public,
            ((compiled, "source_block_authority_fingerprint", "f" * 64),),
        ),
        (
            "capacity_metadata",
            public,
            (
                (topology, "metadata", capacity_metadata),
                (compiled, "metadata_items", tuple(capacity_metadata.items())),
            ),
        ),
        (
            "road_geometry",
            public,
            (
                (compiled, "road_geometry_fingerprint", "f" * 64),
                (centerline, "source_ref", "scalable:changed"),
            ),
        ),
    )
    outcomes = {}
    for name, (source_network, source_blocks, current), changes in cases:
        originals = tuple((target, field, getattr(target, field)) for target, field, _ in changes)
        original_fingerprint = current.fingerprint
        validator_reached = False
        try:
            for target, field, changed in changes:
                object.__setattr__(target, field, changed)
            object.__setattr__(current, "fingerprint", adapter._compiled_fingerprint(current))
            assert current.fingerprint != original_fingerprint
            validator_reached = True
            adapter.require_valid_scalable_compiled_topology(
                current, network=source_network, block_authority=source_blocks
            )
        except (TypeError, ValueError) as error:
            status = "REJECTED" if validator_reached else "ERROR"
            outcomes[name] = f"{status}:{type(error).__name__}:{error}"
        except Exception as error:
            outcomes[name] = f"ERROR:{type(error).__name__}:{error}"
        else:
            outcomes[name] = "ACCEPTED"
        finally:
            for target, field, original in reversed(originals):
                object.__setattr__(target, field, original)
            object.__setattr__(current, "fingerprint", original_fingerprint)
    non_rejected = {k: v for k, v in outcomes.items() if not v.startswith("REJECTED:")}
    assert not non_rejected, non_rejected


def test_public_rows_are_frozen_and_reject_coercive_nested_values(
    public_compiled,
    river_compiled,
) -> None:
    from dataclasses import FrozenInstanceError, replace

    _, _, compiled = public_compiled
    rows = (
        (compiled.numeric_profiles[0], "profile_id"),
        (compiled.road_crosswalk[0], "provenance"),
        (river_compiled.structure_group_crosswalk[0], "semantic_group"),
        (compiled, "fingerprint"),
    )
    for row, name in rows:
        with pytest.raises(FrozenInstanceError):
            setattr(row, name, "changed")
    with pytest.raises(TypeError):
        replace(compiled.numeric_profiles[0], lanes_per_direction=True)
    with pytest.raises(TypeError):
        replace(river_compiled.structure_group_crosswalk[0], member_physical_road_ids=[])
    with pytest.raises(TypeError):
        replace(compiled.road_crosswalk[0], access_directions=["forward"])
    with pytest.raises(TypeError):
        replace(compiled, metadata_items=list(compiled.metadata_items))
