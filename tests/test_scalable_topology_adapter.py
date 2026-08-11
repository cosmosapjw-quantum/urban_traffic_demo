from __future__ import annotations

import hashlib
import inspect


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
