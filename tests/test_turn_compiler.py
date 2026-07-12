from __future__ import annotations


def _cross_fixture(*, north_is_ramp: bool = False):
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
    north_class = RoadClass.RAMP if north_is_ramp else RoadClass.ARTERIAL
    links = (
        RoadLink(10, 2, 1, RoadClass.ARTERIAL, 10.0, 12.0, 7.0),
        RoadLink(11, 1, 2, RoadClass.ARTERIAL, 10.0, 12.0, 7.0),
        RoadLink(12, 1, 3, RoadClass.ARTERIAL, 10.0, 12.0, 7.0),
        RoadLink(13, 3, 1, RoadClass.ARTERIAL, 10.0, 12.0, 7.0),
        RoadLink(14, 4, 1, RoadClass.ARTERIAL, 10.0, 12.0, 7.0),
        RoadLink(15, 1, 4, RoadClass.ARTERIAL, 10.0, 12.0, 7.0),
        RoadLink(16, 1, 5, north_class, 10.0, 12.0, 7.0),
        RoadLink(17, 5, 1, north_class, 10.0, 12.0, 7.0),
    )
    geometry = build_endpoint_geometry_catalog(nodes=nodes, links=links)
    interfaces = compile_node_interfaces(
        nodes=nodes,
        links=links,
        road_geometry=geometry,
    )
    return nodes, links, geometry, interfaces


def test_turn_compiler_is_exhaustive_sorted_and_geometry_classified() -> None:
    from metroflow.city.graph import TurnType
    from metroflow.city.turn_compiler import compile_turn_authority

    _nodes, links, geometry, interfaces = _cross_fixture()
    authority = compile_turn_authority(
        links=links,
        road_geometry=geometry,
        node_interfaces=interfaces,
    )

    expected_pairs = {
        (incoming_id, outgoing_id)
        for interface in interfaces.interfaces
        for incoming_id in interface.incoming_link_ids
        for outgoing_id in interface.outgoing_link_ids
    }
    actual_pairs = {
        (movement.from_link_id, movement.to_link_id)
        for movement in authority.movements
    }
    ordered_pairs = tuple(
        (movement.from_link_id, movement.to_link_id)
        for movement in authority.movements
    )

    assert actual_pairs == expected_pairs
    assert len(authority.movements) == len(expected_pairs) == 20
    assert ordered_pairs == tuple(sorted(expected_pairs))
    assert dict(authority.pair_to_index) == {
        pair: index for index, pair in enumerate(ordered_pairs)
    }
    assert authority.movement_for_pair(10, 12).turn_type is TurnType.THROUGH
    assert authority.movement_for_pair(10, 16).turn_type is TurnType.LEFT
    assert authority.movement_for_pair(10, 15).turn_type is TurnType.RIGHT
    assert authority.movement_for_pair(10, 11).turn_type is TurnType.U_TURN_FORBIDDEN


def test_turn_compiler_marks_ramp_transitions_and_immediate_returns_fail_closed() -> None:
    from metroflow.city.graph import TurnType
    from metroflow.city.turn_compiler import compile_turn_authority

    _nodes, links, geometry, interfaces = _cross_fixture(north_is_ramp=True)
    authority = compile_turn_authority(
        links=links,
        road_geometry=geometry,
        node_interfaces=interfaces,
    )

    assert authority.movement_for_pair(10, 16).turn_type is TurnType.RAMP_ON
    assert authority.movement_for_pair(17, 12).turn_type is TurnType.RAMP_OFF
    assert authority.movement_for_pair(17, 16).turn_type is TurnType.U_TURN_FORBIDDEN

    link_by_id = {link.link_id: link for link in links}
    explicit_forbidden = {
        (movement.from_link_id, movement.to_link_id)
        for movement in authority.movements
        if movement.turn_type is TurnType.U_TURN_FORBIDDEN
    }
    expected_immediate_returns = {
        (movement.from_link_id, movement.to_link_id)
        for movement in authority.movements
        if link_by_id[movement.from_link_id].src_node_id
        == link_by_id[movement.to_link_id].dst_node_id
    }
    assert explicit_forbidden == expected_immediate_returns


def test_turn_compiler_is_input_order_independent_and_rejects_stale_interfaces() -> None:
    import pytest

    from metroflow.city.graph import RoadClass, RoadLink
    from metroflow.city.turn_compiler import compile_turn_authority

    _nodes, links, geometry, interfaces = _cross_fixture()
    first = compile_turn_authority(
        links=links,
        road_geometry=geometry,
        node_interfaces=interfaces,
    )
    repeated = compile_turn_authority(
        links=tuple(reversed(links)),
        road_geometry=geometry,
        node_interfaces=interfaces,
    )

    assert first == repeated
    assert first.fingerprint == repeated.fingerprint

    changed_links = tuple(links) + (
        RoadLink(99, 2, 3, RoadClass.LOCAL, 20.0, 6.0, 2.0),
    )
    with pytest.raises(ValueError, match="stale or incomplete"):
        compile_turn_authority(
            links=changed_links,
            road_geometry=geometry,
            node_interfaces=interfaces,
        )


def test_turn_authority_rows_are_immutable_and_cannot_desynchronize_lookup() -> None:
    from dataclasses import FrozenInstanceError

    import pytest

    from metroflow.city.turn_compiler import compile_turn_authority

    _nodes, links, geometry, interfaces = _cross_fixture()
    authority = compile_turn_authority(
        links=links,
        road_geometry=geometry,
        node_interfaces=interfaces,
    )
    movement = authority.movement_for_pair(10, 12)
    original_fingerprint = authority.fingerprint

    with pytest.raises(FrozenInstanceError):
        movement.from_link_id = 99  # type: ignore[misc]

    assert authority.movement_for_pair(10, 12) is movement
    assert authority.fingerprint == original_fingerprint


def test_generated_seed_41_has_complete_static_turn_authority() -> None:
    import numpy as np

    from metroflow.city.generator_v2 import GeneratorV2
    from metroflow.city.graph import TurnType
    from metroflow.city.turn_compiler import TurnAuthorityCatalog
    from metroflow.routing.dynamic_potential import (
        build_greedy_route_candidate,
        compute_dynamic_potential_state,
    )

    topology = GeneratorV2().generate_preview_topology(
        {"scenario_id": "synthetic_smoke", "seed": 41}
    )
    assert topology.node_interfaces is not None
    assert topology.turns

    authority = TurnAuthorityCatalog(topology.turns)
    link_by_id = {link.link_id: link for link in topology.links}
    expected_pairs = {
        (incoming_id, outgoing_id)
        for interface in topology.node_interfaces.interfaces
        for incoming_id in interface.incoming_link_ids
        for outgoing_id in interface.outgoing_link_ids
    }
    legal_pairs = {
        pair
        for pair in expected_pairs
        if link_by_id[pair[0]].src_node_id != link_by_id[pair[1]].dst_node_id
    }
    permitted_pairs = {
        (movement.from_link_id, movement.to_link_id)
        for movement in topology.turns
        if movement.turn_type is not TurnType.U_TURN_FORBIDDEN
    }

    assert set(authority.pair_to_index) == expected_pairs
    assert permitted_pairs == legal_pairs
    assert len(permitted_pairs) == 45_544
    assert topology.metadata["turn_authority_pair_count"] == len(expected_pairs)
    assert topology.metadata["permitted_turn_movement_count"] == len(legal_pairs)
    assert topology.metadata["turn_authority_fingerprint"] == authority.fingerprint
    road_csr = topology.build_csr()
    assert road_csr.turn_count == len(expected_pairs)

    link_costs = np.asarray(
        [
            link.length_m / link.free_flow_speed_mps
            for link in road_csr.links
        ],
        dtype=np.float32,
    )
    potential = compute_dynamic_potential_state(
        road_csr,
        destination_node_id=8,
        link_travel_time_cost=link_costs,
    )
    selected_path = build_greedy_route_candidate(
        road_csr,
        potential,
        origin_node_id=422,
        max_hops=64,
    )
    assert selected_path
    for selected_pair in zip(selected_path, selected_path[1:]):
        assert selected_pair in permitted_pairs
        selected_type = authority.movement_for_pair(*selected_pair).turn_type
        assert selected_type is not TurnType.U_TURN_FORBIDDEN
