from collections import Counter

import pytest

from metroflow.core.contracts import validate_state_contract
from metroflow.map import generator


def test_synthetic_city_graph_is_deterministic_for_fixed_config():
    config = generator.SyntheticCityConfig(num_zones=8)

    graph_a = generator.build_synthetic_city_graph(config)
    graph_b = generator.build_synthetic_city_graph(config)

    assert graph_a == graph_b


def test_synthetic_city_graph_has_ring_radial_and_bridge_backbone():
    graph = generator.build_synthetic_city_graph(generator.SyntheticCityConfig(num_zones=8))

    edge_classes = Counter(graph.edge_class)
    assert graph.num_nodes == 9
    assert edge_classes["radial"] == 16
    assert edge_classes["ring"] == 16
    assert edge_classes["bridge_bottleneck"] == 2
    assert (0, 1, "radial") in zip(graph.edge_src, graph.edge_dst, graph.edge_class)
    assert (1, 2, "ring") in zip(graph.edge_src, graph.edge_dst, graph.edge_class)


def test_synthetic_city_world_preserves_state_contract():
    world = generator.build_synthetic_city_world(generator.SyntheticCityConfig(num_zones=6))

    validate_state_contract(world)
    assert world.graph.num_edges == len(world.traffic.edge_travel_time)
    assert set(world.traffic.edge_travel_time) == {1.0}


def test_synthetic_city_config_rejects_invalid_zone_count():
    with pytest.raises(ValueError, match="num_zones must be positive"):
        generator.SyntheticCityConfig(num_zones=0)
