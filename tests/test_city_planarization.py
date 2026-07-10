from __future__ import annotations


def _crossing_fixture(*, bridge_second: bool = False):
    from metroflow.city.graph import Node, RoadClass, RoadLink
    from metroflow.map.road_geometry import build_endpoint_geometry_catalog

    nodes = (
        Node(0, x=-10.0, y=0.0),
        Node(1, x=10.0, y=0.0),
        Node(2, x=0.0, y=-10.0),
        Node(3, x=0.0, y=10.0),
    )
    second_class = RoadClass.BRIDGE if bridge_second else RoadClass.COLLECTOR
    bridge_group = 7 if bridge_second else None
    links = (
        RoadLink(
            0,
            0,
            1,
            RoadClass.ARTERIAL,
            30.0,
            15.0,
            6.0,
            lanes=2,
            is_blockable=False,
            physical_road_id=0,
        ),
        RoadLink(1, 1, 0, RoadClass.ARTERIAL, 30.0, 15.0, 6.0, lanes=2, physical_road_id=0),
        RoadLink(
            2,
            2,
            3,
            second_class,
            40.0,
            11.0,
            4.0,
            lanes=1,
            bridge_group_id=bridge_group,
            physical_road_id=1,
        ),
        RoadLink(
            3,
            3,
            2,
            second_class,
            40.0,
            11.0,
            4.0,
            lanes=1,
            bridge_group_id=bridge_group,
            physical_road_id=1,
        ),
    )
    return nodes, links, build_endpoint_geometry_catalog(nodes=nodes, links=links)


def test_planarization_splits_proper_crossing_and_preserves_link_authority() -> None:
    import pytest

    from metroflow.city.planarization import planarize_endpoint_topology
    from metroflow.map.road_geometry import (
        build_endpoint_geometry_catalog,
        count_interior_centerline_intersections,
    )

    nodes, links, geometry = _crossing_fixture()
    result = planarize_endpoint_topology(
        nodes=nodes,
        links=links,
        road_geometry=geometry,
    )
    output_geometry = build_endpoint_geometry_catalog(
        nodes=result.nodes,
        links=result.links,
    )

    assert result.proper_intersection_count_before == 1
    assert result.proper_intersection_count_after == 0
    assert result.added_intersection_node_count == 1
    assert len(result.nodes) == 5
    assert len(result.links) == 8
    assert all(len(result.old_link_to_new_link_ids[link.link_id]) == 2 for link in links)
    assert count_interior_centerline_intersections(output_geometry) == 0
    for source_link in links:
        split_links = [
            result.links[link_id]
            for link_id in result.old_link_to_new_link_ids[source_link.link_id]
        ]
        assert sum(link.length_m for link in split_links) == pytest.approx(
            source_link.length_m
        )
        assert all(link.road_class is source_link.road_class for link in split_links)
        assert all(
            link.free_flow_speed_mps == source_link.free_flow_speed_mps
            for link in split_links
        )
        assert all(link.lanes == source_link.lanes for link in split_links)
        assert all(link.is_blockable is source_link.is_blockable for link in split_links)
        assert all(
            link.capacity_veh_per_tick == source_link.capacity_veh_per_tick
            for link in split_links
        )


def test_planarization_does_not_split_different_layer_bridge_crossing() -> None:
    from metroflow.city.planarization import planarize_endpoint_topology

    nodes, links, geometry = _crossing_fixture(bridge_second=True)
    result = planarize_endpoint_topology(
        nodes=nodes,
        links=links,
        road_geometry=geometry,
    )

    assert result.proper_intersection_count_before == 0
    assert result.nodes == nodes
    assert result.links == links
    assert result.old_link_to_new_link_ids == {
        0: (0,),
        1: (1,),
        2: (2,),
        3: (3,),
    }
