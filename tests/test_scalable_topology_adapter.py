from __future__ import annotations

import hashlib
import inspect

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

    validator_signature = inspect.signature(
        adapter.require_valid_scalable_compiled_topology
    )
    assert tuple(validator_signature.parameters) == (
        "compiled",
        "network",
        "block_authority",
    )
    assert validator_signature.parameters["compiled"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
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
    )
    assert tuple(
        profile.profile_id for profile in lowered.numeric_profiles
    ) == (
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
        alternate_road if road.road_id == source_road.road_id else road
        for road in network.roads
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

    nodes = tuple(
        _node(node_id, node_id * 2_000, (node_id % 2) * 1_000)
        for node_id in range(8)
    )
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
    bridge_group_by_link = {
        link.link_id: link.bridge_group_id for link in lowered.links
    }
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
