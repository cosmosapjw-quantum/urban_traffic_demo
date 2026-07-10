from __future__ import annotations


def test_generated_topology_compiles_section_assignments_without_runtime_drift() -> None:
    from metroflow.city.generator_v2 import GeneratorV2

    topology = GeneratorV2().generate_preview_topology(
        {"scenario_id": "synthetic_smoke", "seed": 13}
    )

    assert topology.road_sections is not None
    assert len(topology.road_sections.assignments) == len(topology.links)
    for link in topology.links:
        assignment = topology.road_sections.assignment_for_link(link.link_id)
        assert assignment.lane_count == link.lanes
        assert assignment.capacity_veh_per_tick == link.capacity_veh_per_tick
        assert assignment.total_width_m > (link.lanes * 3.0)
    assert topology.metadata["road_section_fingerprint"] == (
        topology.road_sections.fingerprint
    )


def test_bidirectional_physical_road_shares_profile_with_opposite_directions() -> None:
    from metroflow.city.generator_v2 import GeneratorV2
    from metroflow.map.lane_grammar import TravelDirection

    topology = GeneratorV2().generate_preview_topology(
        {"scenario_id": "synthetic_smoke", "seed": 2}
    )
    first_road_id = topology.links[0].physical_road_id
    pair = [link for link in topology.links if link.physical_road_id == first_road_id]
    assignments = [
        topology.road_sections.assignment_for_link(link.link_id) for link in pair
    ]

    assert len(pair) == 2
    assert len({assignment.profile_id for assignment in assignments}) == 1
    assert {assignment.direction for assignment in assignments} == {
        TravelDirection.FORWARD,
        TravelDirection.BACKWARD,
    }


def test_node_compiler_detects_through_pairs_and_signal_eligibility() -> None:
    from metroflow.city.graph import Node, RoadClass, RoadLink
    from metroflow.map.node_compiler import compile_node_interfaces
    from metroflow.map.road_geometry import build_endpoint_geometry_catalog

    nodes = (
        Node(1, x=0.0, y=0.0),
        Node(2, x=-10.0, y=0.0),
        Node(3, x=10.0, y=0.0),
        Node(4, x=0.0, y=-10.0),
        Node(5, x=0.0, y=10.0),
    )
    links = (
        RoadLink(10, 2, 1, RoadClass.ARTERIAL, 10.0, 12.0, 7.0, lanes=2),
        RoadLink(11, 1, 2, RoadClass.ARTERIAL, 10.0, 12.0, 7.0, lanes=2),
        RoadLink(12, 1, 3, RoadClass.ARTERIAL, 10.0, 12.0, 7.0, lanes=2),
        RoadLink(13, 3, 1, RoadClass.ARTERIAL, 10.0, 12.0, 7.0, lanes=2),
        RoadLink(14, 4, 1, RoadClass.ARTERIAL, 10.0, 12.0, 7.0, lanes=2),
        RoadLink(15, 1, 4, RoadClass.ARTERIAL, 10.0, 12.0, 7.0, lanes=2),
        RoadLink(16, 1, 5, RoadClass.ARTERIAL, 10.0, 12.0, 7.0, lanes=2),
        RoadLink(17, 5, 1, RoadClass.ARTERIAL, 10.0, 12.0, 7.0, lanes=2),
    )
    geometry = build_endpoint_geometry_catalog(nodes=nodes, links=links)

    catalog = compile_node_interfaces(nodes=nodes, links=links, road_geometry=geometry)
    center = catalog.interface_for_node(1)

    assert (10, 12) in center.through_link_pairs
    assert (14, 16) in center.through_link_pairs
    assert (10, 11) not in center.through_link_pairs
    assert center.signal_eligible
    assert set(center.turn_pocket_incoming_link_ids) == {10, 13, 14, 17}
    assert center.non_through_movement_count == 8


def test_compiler_value_objects_reject_coercive_or_mutable_inputs() -> None:
    import pytest

    from metroflow.map.lane_grammar import TravelDirection
    from metroflow.map.node_compiler import CompiledNodeInterface, NodeRuleSet
    from metroflow.map.section_compiler import LinkSectionAssignment

    with pytest.raises(ValueError, match="lane_count must be an integer"):
        LinkSectionAssignment(1, "p", TravelDirection.FORWARD, 1.5, 3.0, 8.0)
    with pytest.raises(ValueError, match="link_id must be an integer"):
        LinkSectionAssignment(1.0, "p", TravelDirection.FORWARD, 1, 3.0, 8.0)
    with pytest.raises(ValueError, match="must be a bool"):
        NodeRuleSet(signal_eligible=1)

    incoming = [10]
    interface = CompiledNodeInterface(
        node_id=1,
        incoming_link_ids=incoming,
        outgoing_link_ids=[11],
        through_link_pairs=[[10, 11]],
        turn_pocket_incoming_link_ids=[],
        non_through_movement_count=0,
        signal_eligible=False,
    )
    incoming.append(12)
    assert interface.incoming_link_ids == (10,)
    assert interface.through_link_pairs == ((10, 11),)

    with pytest.raises(ValueError, match="declared incoming/outgoing"):
        CompiledNodeInterface(
            node_id=1,
            incoming_link_ids=(10,),
            outgoing_link_ids=(11,),
            through_link_pairs=((12, 11),),
            turn_pocket_incoming_link_ids=(),
            non_through_movement_count=0,
            signal_eligible=False,
        )


def test_non_through_count_is_independent_of_interface_output_options() -> None:
    from metroflow.city.graph import Node, RoadClass, RoadLink
    from metroflow.map.node_compiler import NodeRuleSet, compile_node_interfaces
    from metroflow.map.road_geometry import build_endpoint_geometry_catalog

    nodes = (
        Node(1, x=0.0, y=0.0),
        Node(2, x=-10.0, y=0.0),
        Node(3, x=10.0, y=0.0),
    )
    links = (
        RoadLink(10, 2, 1, RoadClass.LOCAL, 10.0, 6.0, 4.0),
        RoadLink(11, 1, 2, RoadClass.LOCAL, 10.0, 6.0, 4.0),
        RoadLink(12, 1, 3, RoadClass.LOCAL, 10.0, 6.0, 4.0),
        RoadLink(13, 3, 1, RoadClass.LOCAL, 10.0, 6.0, 4.0),
    )
    geometry = build_endpoint_geometry_catalog(nodes=nodes, links=links)
    interface = compile_node_interfaces(
        nodes=nodes,
        links=links,
        road_geometry=geometry,
        rule_set=NodeRuleSet(through_continuity=False),
    ).interface_for_node(1)

    assert interface.through_link_pairs == ()
    assert interface.non_through_movement_count == 0


def test_node_and_section_catalogs_are_deterministic() -> None:
    from metroflow.city.generator_v2 import GeneratorV2

    first = GeneratorV2().generate_preview_topology(
        {"scenario_id": "synthetic_smoke", "seed": 17}
    )
    second = GeneratorV2().generate_preview_topology(
        {"scenario_id": "synthetic_smoke", "seed": 17}
    )

    assert first.road_sections == second.road_sections
    assert first.road_sections.fingerprint == second.road_sections.fingerprint
    assert first.node_interfaces == second.node_interfaces
    assert first.node_interfaces.fingerprint == second.node_interfaces.fingerprint


def test_section_compiler_rejects_incomplete_geometry_assignments() -> None:
    import pytest

    from metroflow.city.graph import RoadClass, RoadLink
    from metroflow.map.road_geometry import RoadCenterline, RoadGeometryCatalog
    from metroflow.map.section_compiler import compile_road_sections

    links = (RoadLink(1, 1, 2, RoadClass.LOCAL, 10.0, 9.0, 4.0),)
    geometry = RoadGeometryCatalog(
        centerlines=(RoadCenterline(1, ((0.0, 0.0), (10.0, 0.0))),),
        assignments=(),
    )

    with pytest.raises(KeyError, match="no geometry assignment"):
        compile_road_sections(links=links, road_geometry=geometry)
