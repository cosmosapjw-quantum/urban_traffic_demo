from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from metroflow.city.formative_growth import FormationConfig, generate_formative_city


def test_formative_growth_is_deterministic_connected_and_planar() -> None:
    cfg = FormationConfig(seed=41, node_count=90, urbanized_area_km2=25.0, epochs=6)
    first = generate_formative_city(cfg)
    second = generate_formative_city(cfg)
    assert first.fingerprint == second.fingerprint
    assert first.metrics["node_count"] == 90
    assert first.metrics["connected_components"] == 1
    assert first.metrics["crossing_count"] == 0
    assert first.metrics["cycle_rank"] > 0


def test_formative_growth_seed_changes_semantic_identity() -> None:
    a = generate_formative_city(FormationConfig(seed=7, node_count=75, urbanized_area_km2=20.0, epochs=5))
    b = generate_formative_city(FormationConfig(seed=8, node_count=75, urbanized_area_km2=20.0, epochs=5))
    assert a.fingerprint != b.fingerprint
    assert a.metrics["node_count"] == b.metrics["node_count"] == 75


def test_formative_growth_payload_is_strict_json() -> None:
    city = generate_formative_city(FormationConfig(seed=3, node_count=60, urbanized_area_km2=16.0, epochs=5))
    encoded = json.dumps(city.to_dict(), allow_nan=False, sort_keys=True)
    decoded = json.loads(encoded)
    assert decoded["schema_version"] == "formative_growth_v1"
    assert decoded["fingerprint"] == city.fingerprint


def test_each_late_node_has_causal_growth_connection() -> None:
    city = generate_formative_city(
        FormationConfig(seed=19, node_count=85, urbanized_area_km2=18.0, epochs=6)
    )
    by_id = {node.node_id: node for node in city.nodes}
    for node in city.nodes:
        if node.birth_epoch == 0 or node.mode == "nucleus":
            continue
        parents = [
            edge
            for edge in city.edges
            if edge.role == "growth_connection"
            and edge.u == node.node_id
            and edge.birth_epoch == node.birth_epoch
            and by_id[edge.v].birth_epoch <= node.birth_epoch
            and edge.v < edge.u
        ]
        assert len(parents) == 1, (
            f"node {node.node_id} has {len(parents)} causal growth connections"
        )


def test_primary_hierarchy_is_one_connected_backbone() -> None:
    city = generate_formative_city(
        FormationConfig(seed=23, node_count=120, urbanized_area_km2=12.0, epochs=6)
    )
    assert city.metrics["primary_components"] == 1
