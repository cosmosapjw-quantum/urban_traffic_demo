from __future__ import annotations

import json
import sys
import subprocess

import numpy as np
import pytest

from metroflow.flow.state import create_link_state


def make_label_fixture():
    from metroflow.city.graph import Node, RoadClass, RoadLink, build_road_network_csr

    road_csr = build_road_network_csr(
        nodes=(Node(1), Node(2), Node(3), Node(4)),
        links=(
            RoadLink(10, 1, 2, RoadClass.ARTERIAL, 100.0, 10.0, 5.0),
            RoadLink(11, 2, 4, RoadClass.ARTERIAL, 100.0, 10.0, 5.0),
            RoadLink(12, 1, 3, RoadClass.ARTERIAL, 100.0, 10.0, 5.0),
            RoadLink(13, 3, 4, RoadClass.ARTERIAL, 100.0, 10.0, 5.0),
        ),
    )
    link_state = create_link_state(
        road_csr.link_count,
        travel_time_cost=(5.0, 1.0, 2.0, 1.0),
        capacity_veh_per_tick=(5.0, 5.0, 5.0, 5.0),
    )
    return road_csr, link_state


def test_cost_to_go_label_export_is_deterministic_and_baseline_authoritative():
    from metroflow.learning.labels import export_cost_to_go_label_records

    road_csr, link_state = make_label_fixture()

    first = export_cost_to_go_label_records(
        road_csr=road_csr,
        link_state=link_state,
        destination_node_ids=(4,),
        scenario_id="label-fixture",
        tick_index=3,
    )
    second = export_cost_to_go_label_records(
        road_csr=road_csr,
        link_state=link_state,
        destination_node_ids=(4,),
        scenario_id="label-fixture",
        tick_index=3,
    )

    assert tuple(record.fingerprint for record in first) == tuple(
        record.fingerprint for record in second
    )
    assert [record.label_kind for record in first] == ["cost_to_go"] * len(first)
    assert first[0].schema_version == 1
    assert first[0].source_authority == "baseline_dynamic_potential"
    assert first[0].routing_backend == "baseline"
    assert first[0].scenario_id == "label-fixture"
    assert first[0].tick_index == 3
    node_costs = {
        record.features["node_id"]: record.labels["label_cost_to_go"]
        for record in first
    }
    assert node_costs == {1: 3.0, 2: 1.0, 3: 1.0, 4: 0.0}
    assert first[0].metadata["destination_node_id"] == 4
    assert first[0].metadata["label_units"]["label_cost_to_go"] == (
        "generalized_travel_time_cost_ticks"
    )


def test_label_fingerprint_changes_when_authoritative_cost_changes():
    from metroflow.learning.labels import export_cost_to_go_label_records

    road_csr, link_state = make_label_fixture()
    baseline = export_cost_to_go_label_records(
        road_csr=road_csr,
        link_state=link_state,
        destination_node_ids=(4,),
    )
    changed_link_state = create_link_state(
        road_csr.link_count,
        travel_time_cost=(5.0, 10.0, 2.0, 1.0),
        capacity_veh_per_tick=(5.0, 5.0, 5.0, 5.0),
    )
    changed = export_cost_to_go_label_records(
        road_csr=road_csr,
        link_state=changed_link_state,
        destination_node_ids=(4,),
    )

    assert [record.fingerprint for record in baseline] != [
        record.fingerprint for record in changed
    ]


def test_route_scoring_label_export_records_selected_baseline_candidate():
    from metroflow.learning.labels import export_route_scoring_label_records

    road_csr, link_state = make_label_fixture()

    records = export_route_scoring_label_records(
        road_csr=road_csr,
        link_state=link_state,
        od_pairs=((1, 4),),
        scenario_id="route-labels",
        tick_index=5,
        max_candidates=2,
        path_size_gamma=0.0,
    )

    assert len(records) == 1
    record = records[0]
    assert record.label_kind == "route_scoring"
    assert record.source_authority == "baseline_route_candidate_scoring"
    assert record.routing_backend == "baseline"
    assert record.features["origin_node_id"] == 1
    assert record.features["destination_node_id"] == 4
    assert record.features["candidate_paths"] == ((12, 13), (10, 11))
    assert record.features["candidate_path_costs"] == (3.0, 6.0)
    assert record.features["candidate_path_size_factors"] == (1.0, 1.0)
    assert record.metadata["feature_units"]["candidate_path_costs"] == (
        "generalized_travel_time_cost_ticks"
    )
    assert record.metadata["feature_units"]["candidate_path_size_factors"] == (
        "dimensionless"
    )
    assert record.metadata["label_units"]["selected_candidate_utility"] == (
        "path_size_corrected_utility"
    )
    assert record.metadata["route_score_formula"] == (
        "-candidate_path_cost + path_size_gamma * log(candidate_path_size_factor)"
    )
    assert record.labels["selected_candidate_index"] == 0
    assert record.labels["selected_candidate_id"] == 0
    assert record.labels["selected_candidate_utility"] == pytest.approx(-3.0)
    assert record.labels["route_score_values"] == (-3.0, -6.0)
    assert record.metadata["candidate_generation_mode"] == "baseline_ranked_k"


def test_label_jsonl_writer_is_stable_and_sorted(tmp_path):
    from metroflow.learning.labels import (
        export_cost_to_go_label_records,
        write_label_records_jsonl,
    )

    road_csr, link_state = make_label_fixture()
    records = export_cost_to_go_label_records(
        road_csr=road_csr,
        link_state=link_state,
        destination_node_ids=(4,),
        scenario_id="jsonl-labels",
    )
    output = tmp_path / "labels.jsonl"
    write_label_records_jsonl(records, output)

    lines = output.read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(records)
    parsed = [json.loads(line) for line in lines]
    assert [row["fingerprint"] for row in parsed] == sorted(
        record.fingerprint for record in records
    )
    assert parsed[0]["schema_version"] == 1
    assert parsed[0]["source_authority"] == "baseline_dynamic_potential"


def test_label_records_reject_non_finite_json_values():
    from metroflow.learning.labels import SimulatorLabelRecord

    with pytest.raises(ValueError, match="finite"):
        SimulatorLabelRecord(
            label_kind="cost_to_go",
            source_authority="baseline_dynamic_potential",
            scenario_id="bad-json",
            tick_index=0,
            routing_backend="baseline",
            features={"node_id": 1},
            labels={"label_cost_to_go": float("nan")},
        )
    with pytest.raises(ValueError, match="finite"):
        SimulatorLabelRecord(
            label_kind="cost_to_go",
            source_authority="baseline_dynamic_potential",
            scenario_id="bad-json",
            tick_index=0,
            routing_backend="baseline",
            features={"node_id": 1},
            labels={"label_cost_to_go": np.float32("nan")},
            fingerprint="manual-fingerprint-must-not-bypass-validation",
        )


def test_learning_label_imports_do_not_load_accelerators():
    script = """
import sys
import metroflow.learning.labels  # noqa: F401
print('jax', 'jax' in sys.modules)
print('jax.numpy', 'jax.numpy' in sys.modules)
print('torch', 'torch' in sys.modules)
print('_metroflow_rust', '_metroflow_rust' in sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.splitlines() == [
        "jax False",
        "jax.numpy False",
        "torch False",
        "_metroflow_rust False",
    ]


def test_learning_label_exports_are_public_package_api():
    import metroflow.learning as learning

    assert hasattr(learning, "SimulatorLabelRecord")
    assert hasattr(learning, "export_cost_to_go_label_records")
    assert hasattr(learning, "export_route_scoring_label_records")
