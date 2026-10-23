"""Deterministic pure-Python urban street morphogenesis research lane.

The generator models city formation as alternating exploration and densification.
It intentionally remains an opt-in research lane and does not replace the
repository's authoritative runtime map generators.  The scientific kernel uses
only Python's standard library; rendering remains an optional research-tool concern.
"""

from __future__ import annotations

import math
import random

from metroflow.city.formative_growth_analysis import (
    audit_formation_map,
    compute_formation_metrics,
    extract_planar_blocks,
)
from metroflow.city.formative_growth_hierarchy import classify_edges
from metroflow.city.formative_growth_model import (
    FormationBlock,
    FormationCentre,
    FormationConfig,
    FormationEdge,
    FormationMap,
    FormationNode,
)
from metroflow.city.formative_growth_network import (
    build_causal_growth_network,
    close_dangling_stubs,
    repair_local_connectivity,
)
from metroflow.city.formative_growth_sampling import build_centres, generate_nodes

__all__ = [
    "FormationConfig",
    "FormationMap",
    "FormationNode",
    "FormationEdge",
    "FormationBlock",
    "FormationCentre",
    "generate_formative_city",
    "extract_planar_blocks",
    "compute_formation_metrics",
    "audit_formation_map",
]


def generate_formative_city(config: FormationConfig | None = None) -> FormationMap:
    """Generate a replay-stable city through exploration, densification and loops."""

    cfg = config or FormationConfig()
    rng = random.Random(cfg.seed)
    width_m = math.sqrt(cfg.urbanized_area_km2 * 1_000_000.0 * cfg.aspect_ratio)
    height_m = width_m / cfg.aspect_ratio

    centres = build_centres(cfg, width_m, height_m, rng)
    nodes = generate_nodes(cfg, width_m, height_m, centres, rng)
    mutable_edges = build_causal_growth_network(cfg, nodes, centres)
    repair_local_connectivity(cfg, nodes, centres, mutable_edges)
    close_dangling_stubs(cfg, nodes, centres, mutable_edges)
    edges = classify_edges(nodes, centres, mutable_edges)
    blocks = extract_planar_blocks(cfg, nodes, edges, centres)
    metrics = compute_formation_metrics(cfg, width_m, height_m, centres, nodes, edges, blocks)
    audit = audit_formation_map(cfg, width_m, height_m, centres, nodes, edges, blocks, metrics)
    return FormationMap(
        config=cfg,
        width_m=width_m,
        height_m=height_m,
        centres=tuple(centres),
        nodes=tuple(nodes),
        edges=tuple(edges),
        blocks=tuple(blocks),
        metrics=metrics,
        audit=audit,
    )
