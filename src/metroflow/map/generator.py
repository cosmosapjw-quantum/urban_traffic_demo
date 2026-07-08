from __future__ import annotations

from dataclasses import dataclass, replace

from metroflow.core.state import GraphState, TrafficState, WorldState, make_empty_world_state

__all__ = [
    "SyntheticCityConfig",
    "build_synthetic_city_graph",
    "build_synthetic_city_world",
]


@dataclass(frozen=True)
class SyntheticCityConfig:
    num_zones: int = 64
    include_bridge_bottleneck: bool = True
    include_ring_radial: bool = True

    def __post_init__(self) -> None:
        if self.num_zones <= 0:
            raise ValueError("num_zones must be positive.")
        if self.include_ring_radial and self.num_zones < 3:
            raise ValueError("num_zones must be at least 3 for ring-radial generation.")
        if self.include_bridge_bottleneck and self.num_zones < 2:
            raise ValueError("num_zones must be at least 2 for bridge bottleneck generation.")


def build_synthetic_city_graph(config: SyntheticCityConfig | None = None) -> GraphState:
    """Build a deterministic zone-level city graph.

    Nodes are abstract zone nodes. Edges are directed movements with class labels
    only; lengths, capacities, and travel times are assigned by downstream
    modules in their own explicit units.
    """

    resolved = config or SyntheticCityConfig()
    edge_src: list[int] = []
    edge_dst: list[int] = []
    edge_class: list[str] = []

    if resolved.include_ring_radial:
        hub_node = 0
        zone_nodes = tuple(range(1, resolved.num_zones + 1))
        num_nodes = resolved.num_zones + 1
        for zone_node in zone_nodes:
            _add_bidirectional_edge(edge_src, edge_dst, edge_class, hub_node, zone_node, "radial")
        for index, zone_node in enumerate(zone_nodes):
            next_zone = zone_nodes[(index + 1) % len(zone_nodes)]
            _add_bidirectional_edge(edge_src, edge_dst, edge_class, zone_node, next_zone, "ring")
    else:
        zone_nodes = tuple(range(resolved.num_zones))
        num_nodes = resolved.num_zones
        for zone_node, next_zone in zip(zone_nodes, zone_nodes[1:]):
            _add_bidirectional_edge(edge_src, edge_dst, edge_class, zone_node, next_zone, "local")

    if resolved.include_bridge_bottleneck:
        start_node, end_node = _bridge_endpoint_nodes(resolved)
        if start_node != end_node:
            _add_bidirectional_edge(
                edge_src,
                edge_dst,
                edge_class,
                start_node,
                end_node,
                "bridge_bottleneck",
            )

    return GraphState(
        num_nodes=num_nodes,
        num_edges=len(edge_src),
        edge_src=tuple(edge_src),
        edge_dst=tuple(edge_dst),
        edge_class=tuple(edge_class),
    )


def build_synthetic_city_world(
    config: SyntheticCityConfig | None = None,
    *,
    seed: int = 0,
    free_flow_time_ticks: float = 1.0,
) -> WorldState:
    """Create a baseline world with a materialized graph and empty traffic state."""

    if free_flow_time_ticks <= 0.0:
        raise ValueError("free_flow_time_ticks must be positive.")
    graph = build_synthetic_city_graph(config)
    edge_count = graph.num_edges
    return replace(
        make_empty_world_state(seed=seed),
        graph=graph,
        traffic=TrafficState(
            edge_queue=(0.0,) * edge_count,
            edge_stock=(0.0,) * edge_count,
            edge_travel_time=(float(free_flow_time_ticks),) * edge_count,
        ),
    )


def _add_bidirectional_edge(
    edge_src: list[int],
    edge_dst: list[int],
    edge_class: list[str],
    node_a: int,
    node_b: int,
    class_name: str,
) -> None:
    edge_src.extend((node_a, node_b))
    edge_dst.extend((node_b, node_a))
    edge_class.extend((class_name, class_name))


def _bridge_endpoint_nodes(config: SyntheticCityConfig) -> tuple[int, int]:
    if config.include_ring_radial:
        return 1, (config.num_zones // 2) + 1
    return 0, config.num_zones - 1
