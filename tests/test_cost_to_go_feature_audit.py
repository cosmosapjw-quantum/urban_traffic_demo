from __future__ import annotations

from dataclasses import replace
import json
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest


def _tiny_network(*, offset: float = 0.0):
    from metroflow.city.graph import Node, RoadClass, RoadLink, build_road_network_csr

    return build_road_network_csr(
        nodes=(
            Node(1, x=0.0 + offset, y=0.0),
            Node(2, x=100.0 + offset, y=0.0),
            Node(3, x=0.0 + offset, y=100.0),
            Node(4, x=100.0 + offset, y=100.0),
            Node(5, x=50.0 + offset, y=50.0),
        ),
        links=(
            RoadLink(10, 1, 2, RoadClass.ARTERIAL, 100.0, 10.0, 5.0),
            RoadLink(11, 2, 1, RoadClass.ARTERIAL, 100.0, 10.0, 5.0),
            RoadLink(12, 2, 4, RoadClass.ARTERIAL, 100.0, 10.0, 4.0),
            RoadLink(13, 4, 2, RoadClass.ARTERIAL, 100.0, 10.0, 4.0),
            RoadLink(14, 4, 3, RoadClass.COLLECTOR, 100.0, 8.0, 3.0),
            RoadLink(15, 3, 4, RoadClass.COLLECTOR, 100.0, 8.0, 3.0),
            RoadLink(16, 3, 1, RoadClass.COLLECTOR, 100.0, 8.0, 3.0),
            RoadLink(17, 1, 3, RoadClass.COLLECTOR, 100.0, 8.0, 3.0),
            RoadLink(18, 1, 5, RoadClass.LOCAL, 70.7, 6.0, 2.0),
            RoadLink(19, 5, 4, RoadClass.LOCAL, 70.7, 6.0, 2.0),
            RoadLink(20, 4, 5, RoadClass.LOCAL, 70.7, 6.0, 2.0),
            RoadLink(21, 5, 1, RoadClass.LOCAL, 70.7, 6.0, 2.0),
        ),
    )


def test_feature_audit_config_requires_unique_three_by_three_matrix() -> None:
    from metroflow.learning.cost_to_go_audit import CostToGoFeatureAuditConfig

    with pytest.raises(ValueError, match="at least three styles"):
        CostToGoFeatureAuditConfig(style_ids=("a", "b"), seeds=(1, 2, 3))
    with pytest.raises(ValueError, match="unique"):
        CostToGoFeatureAuditConfig(style_ids=("a", "b", "c"), seeds=(1, 1, 2))
    with pytest.raises(ValueError, match="destination_count"):
        CostToGoFeatureAuditConfig(
            style_ids=("a", "b", "c"),
            seeds=(1, 2, 3),
            destination_count=1,
        )


def test_spatial_destination_selection_is_deterministic_and_dispersed() -> None:
    from metroflow.learning.cost_to_go_audit import select_spatial_destination_node_ids

    network = _tiny_network()
    first = select_spatial_destination_node_ids(network, destination_count=4)
    second = select_spatial_destination_node_ids(network, destination_count=4)

    assert first == second
    assert len(first) == len(set(first)) == 4
    assert set(first) <= set(int(value) for value in network.node_ids)
    assert 1 in first
    assert 4 in first
    coordinates = {
        int(node.node_id): np.asarray((node.x, node.y), dtype=np.float64)
        for node in network.nodes
    }
    minimum_pair_distance = min(
        float(np.linalg.norm(coordinates[left] - coordinates[right]))
        for index, left in enumerate(first)
        for right in first[index + 1 :]
    )
    assert minimum_pair_distance >= 100.0

    from metroflow.city.graph import build_road_network_csr

    node_id_map = {node.node_id: node.node_id + 100 for node in network.nodes}
    relabeled = build_road_network_csr(
        nodes=tuple(replace(node, node_id=node_id_map[node.node_id]) for node in network.nodes),
        links=tuple(
            replace(
                link,
                src_node_id=node_id_map[link.src_node_id],
                dst_node_id=node_id_map[link.dst_node_id],
            )
            for link in network.links
        ),
    )
    relabeled_ids = select_spatial_destination_node_ids(relabeled, destination_count=4)
    relabeled_coordinates = {
        int(node.node_id): (float(node.x), float(node.y)) for node in relabeled.nodes
    }
    assert tuple(relabeled_coordinates[node_id] for node_id in relabeled_ids) == tuple(
        tuple(coordinates[node_id]) for node_id in first
    )


def test_feature_audit_dynamic_states_are_deterministic_and_include_closure() -> None:
    from metroflow.learning.cost_to_go_audit import build_feature_audit_link_states

    network = _tiny_network()
    first = build_feature_audit_link_states(network, seed=17, closure_fraction=0.1)
    second = build_feature_audit_link_states(network, seed=17, closure_fraction=0.1)

    assert tuple(first) == ("free_flow", "stressed_closure")
    for name in first:
        np.testing.assert_array_equal(
            first[name].travel_time_cost,
            second[name].travel_time_cost,
        )
        np.testing.assert_array_equal(
            first[name].incident_capacity_multiplier,
            second[name].incident_capacity_multiplier,
        )
    assert np.all(first["free_flow"].incident_capacity_multiplier == 1.0)
    assert np.count_nonzero(
        first["stressed_closure"].incident_capacity_multiplier == 0.0
    ) >= 1
    stress_metadata = first["stressed_closure"].metadata
    assert stress_metadata["closure_link_count"] == stress_metadata[
        "requested_closure_link_count"
    ]
    assert stress_metadata["eligible_closure_link_count"] >= stress_metadata[
        "closure_link_count"
    ]
    assert not np.array_equal(
        first["free_flow"].travel_time_cost,
        first["stressed_closure"].travel_time_cost,
    )
    mutable_arrays = (
        "queue_vehicles",
        "inflow_vehicles",
        "outflow_vehicles",
        "travel_time_cost",
        "capacity_veh_per_tick",
        "incident_capacity_multiplier",
        "capacity_violation_flags",
    )
    for index, left_name in enumerate(mutable_arrays):
        left = getattr(first["free_flow"], left_name)
        for right_name in mutable_arrays[index + 1 :]:
            assert not np.shares_memory(
                left,
                getattr(first["free_flow"], right_name),
            )
        assert not np.shares_memory(
            left,
            getattr(first["stressed_closure"], left_name),
        )


def test_feature_audit_closure_rejects_zero_capacity_or_missing_alternate_paths() -> None:
    from metroflow.city.graph import Node, RoadClass, RoadLink, build_road_network_csr
    from metroflow.learning.cost_to_go_audit import build_feature_audit_link_states

    network = build_road_network_csr(
        nodes=(Node(1), Node(2)),
        links=(
            RoadLink(10, 1, 2, RoadClass.LOCAL, 10.0, 5.0, 1.0),
            RoadLink(11, 2, 1, RoadClass.LOCAL, 10.0, 5.0, 1.0),
        ),
    )
    with pytest.raises(ValueError, match="closure quota"):
        build_feature_audit_link_states(network, seed=1, closure_fraction=0.1)


def test_feature_audit_closure_rejects_zero_capacity_alternate_path() -> None:
    from metroflow.city.graph import Node, RoadClass, RoadLink, build_road_network_csr
    from metroflow.learning.cost_to_go_audit import (
        _select_reachability_preserving_closures,
        build_feature_audit_link_states,
    )

    network = build_road_network_csr(
        nodes=(Node(1), Node(2), Node(3)),
        links=(
            RoadLink(10, 1, 2, RoadClass.LOCAL, 10.0, 5.0, 1.0),
            RoadLink(11, 1, 3, RoadClass.LOCAL, 10.0, 5.0, 0.0, is_blockable=False),
            RoadLink(12, 3, 2, RoadClass.LOCAL, 10.0, 5.0, 1.0, is_blockable=False),
            RoadLink(13, 2, 1, RoadClass.LOCAL, 10.0, 5.0, 1.0, is_blockable=False),
        ),
    )
    usable = np.asarray(
        [link.capacity_veh_per_tick > 0.0 for link in network.links],
        dtype=np.bool_,
    )

    selected = _select_reachability_preserving_closures(
        network,
        ranked_candidates=(network.link_id_to_index[10],),
        requested_count=1,
        usable_link_mask=usable,
    )

    assert selected == ()
    with pytest.raises(ValueError, match="closure quota"):
        build_feature_audit_link_states(network, seed=1, closure_fraction=0.1)


def test_feature_audit_closure_returns_partial_selection_when_quota_is_unsafe() -> None:
    from metroflow.city.graph import Node, RoadClass, RoadLink, build_road_network_csr
    from metroflow.learning.cost_to_go_audit import (
        _select_reachability_preserving_closures,
        build_feature_audit_link_states,
    )

    network = _tiny_network()
    requested_count = network.link_count
    selected = _select_reachability_preserving_closures(
        network,
        ranked_candidates=tuple(range(network.link_count)),
        requested_count=requested_count,
        usable_link_mask=np.ones((network.link_count,), dtype=np.bool_),
    )

    assert 0 < len(selected) < requested_count

    partial_network = build_road_network_csr(
        nodes=(Node(1), Node(2), Node(3), Node(4), Node(5)),
        links=(
            RoadLink(10, 1, 2, RoadClass.LOCAL, 10.0, 5.0, 1.0),
            RoadLink(11, 1, 2, RoadClass.LOCAL, 10.0, 5.0, 1.0),
            RoadLink(12, 2, 3, RoadClass.LOCAL, 10.0, 5.0, 1.0),
            RoadLink(13, 3, 4, RoadClass.LOCAL, 10.0, 5.0, 1.0),
            RoadLink(14, 4, 5, RoadClass.LOCAL, 10.0, 5.0, 1.0),
            RoadLink(15, 5, 1, RoadClass.LOCAL, 10.0, 5.0, 1.0),
        ),
    )
    partial = _select_reachability_preserving_closures(
        partial_network,
        ranked_candidates=tuple(range(partial_network.link_count)),
        requested_count=2,
        usable_link_mask=np.ones((partial_network.link_count,), dtype=np.bool_),
    )
    assert len(partial) == 1
    with pytest.raises(ValueError, match="closure quota"):
        build_feature_audit_link_states(
            partial_network,
            seed=1,
            closure_fraction=0.2,
        )


def test_feature_audit_runner_and_bundle_remain_diagnostic(monkeypatch, tmp_path) -> None:
    from metroflow.learning import cost_to_go_audit
    from metroflow.learning.cost_to_go_audit import (
        CostToGoFeatureAuditConfig,
        run_cost_to_go_feature_audit,
        write_cost_to_go_feature_audit_bundle,
    )

    def fake_network(*, style_id: str, seed: int, topology_mode: str):
        del topology_mode
        style_offset = {"style-a": 0.0, "style-b": 250.0, "style-c": 500.0}[
            style_id
        ]
        return _tiny_network(offset=style_offset + float(seed))

    monkeypatch.setattr(cost_to_go_audit, "_generate_audit_network", fake_network)
    config = CostToGoFeatureAuditConfig(
        style_ids=("style-a", "style-b", "style-c"),
        seeds=(3, 5, 7),
        destination_count=4,
    )
    result = run_cost_to_go_feature_audit(config)
    repeated = run_cost_to_go_feature_audit(config)

    assert result.map_count == 9
    assert result.dynamic_state_count == 18
    assert result.row_count > 0
    assert len(result.feature_columns) == 20
    assert result.cross_map_holdout_feasible is True
    assert result.runtime_nn_backend_authorized is False
    assert result.route_legality_changed is False
    assert result.raw_label_rows_persisted is False
    assert result.row_local_mlp_probe_authorized is True
    assert result.decision_state == "admissible"
    assert result.adjacency_required_before_mlp is False
    assert result.config.canonical_gate_profile is True
    assert result.all_state_rows_retained is True
    assert result.feature_target_relation.passed is True
    assert result.map_holdout.feasible is True
    assert all(run.all_state_rows_retained for run in result.runs)
    assert all(
        run.dynamic_matched_row_count == run.expected_record_count_per_state
        for run in result.runs
    )
    assert result.dynamic_matched_row_count == sum(
        run.dynamic_matched_row_count for run in result.runs
    )
    assert result.dynamic_joint_changed_count == sum(
        run.dynamic_joint_changed_count for run in result.runs
    )
    assert cost_to_go_audit._build_map_holdout(config, result.runs[:-1]).feasible is False
    assert result.corpus_fingerprint == repeated.corpus_fingerprint
    assert result.map_holdout.split_fingerprint == repeated.map_holdout.split_fingerprint

    paths = write_cost_to_go_feature_audit_bundle(result, tmp_path / "first")
    repeated_paths = write_cost_to_go_feature_audit_bundle(
        repeated,
        tmp_path / "second",
    )
    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert payload["artifact_format_version"] == "cost_to_go_feature_audit_v1"
    assert payload["evidence_status"] == "diagnostic_not_validation"
    assert payload["threshold_provenance"] == (
        "fixed_in_pr_before_canonical_run_not_prior_preregistered"
    )
    assert payload["decision"]["runtime_nn_backend_authorized"] is False
    assert payload["decision"]["row_local_mlp_probe_authorized"] is True
    assert payload["decision"]["decision_state"] == "admissible"
    assert payload["decision"]["next_pr"] == "row_local_jax_probe_authorized"
    assert payload["map_holdout"]["split_fingerprint"]
    assert payload["feature_target_relation"]["passed"] is True
    assert payload["feature_target_relation"]["maximum_normalized_target_range"] == 0.1
    assert "global_max_travel_time" in payload["feature_target_relation"][
        "target_normalization"
    ]
    assert manifest["raw_label_rows_persisted"] is False
    assert manifest["threshold_provenance"] == (
        "fixed_in_pr_before_canonical_run_not_prior_preregistered"
    )
    assert manifest["decision_state"] == "admissible"
    review_markdown = paths["markdown"].read_text(encoding="utf-8")
    assert "experiment-only JAX MLP bakeoff" in review_markdown
    assert "does not validate an NN" in review_markdown
    for key in ("json", "markdown", "manifest"):
        assert paths[key].read_bytes() == repeated_paths[key].read_bytes()
    with pytest.raises(ValueError, match="output_dir must be empty"):
        write_cost_to_go_feature_audit_bundle(result, tmp_path / "first")

    for forbidden_field in (
        "runtime_nn_backend_authorized",
        "route_legality_changed",
        "raw_label_rows_persisted",
    ):
        with pytest.raises(ValueError, match=f"{forbidden_field} must remain False"):
            replace(result, **{forbidden_field: True})
    with pytest.raises(ValueError, match="must match the canonical audit gate"):
        replace(result, all_state_rows_retained=False)

    relation_rejected = replace(
        result,
        row_local_mlp_probe_authorized=False,
        feature_target_relation=replace(
            result.feature_target_relation,
            coverage_share=0.2,
            conflict_share=0.7,
            passed=False,
        ),
    )
    assert relation_rejected.decision_state == "relation_rejected"
    assert relation_rejected.adjacency_required_before_mlp is True
    assert relation_rejected.as_dict()["decision"]["next_pr"] == (
        "PR50_adjacency_edge_tensor_contract"
    )

    inconclusive = replace(relation_rejected, all_state_rows_retained=False)
    assert inconclusive.decision_state == "inconclusive"
    assert inconclusive.adjacency_required_before_mlp is False
    assert inconclusive.as_dict()["decision"]["next_pr"] == (
        "stop_and_repair_audit_evidence"
    )


def test_feature_target_relation_detects_permuted_target_conflicts() -> None:
    from metroflow.learning.cost_to_go_audit import audit_feature_target_relation
    from metroflow.learning.cost_to_go_features import COST_TO_GO_FEATURE_NAMES

    features = np.zeros((4, len(COST_TO_GO_FEATURE_NAMES)), dtype=np.float32)
    scale_index = COST_TO_GO_FEATURE_NAMES.index("global_max_travel_time_by_one_tick")
    features[:, scale_index] = 1.0
    features[2:, 0] = 0.5
    map_keys = np.asarray(("map-a", "map-b", "map-a", "map-b"), dtype=object)
    consistent = audit_feature_target_relation(
        features,
        np.asarray((1.0, 1.02, 2.0, 2.03), dtype=np.float32),
        map_keys,
    )
    conflicting = audit_feature_target_relation(
        features,
        np.asarray((1.0, 2.0, 1.02, 2.03), dtype=np.float32),
        map_keys,
    )

    assert consistent.coverage_share == 1.0
    assert consistent.conflict_share == 0.0
    assert consistent.passed is True
    assert conflicting.conflict_share == 1.0
    assert conflicting.passed is False


@pytest.mark.parametrize("invalid_scale", (0.0, -1.0))
def test_feature_target_relation_rejects_nonpositive_normalization_scale(
    invalid_scale: float,
) -> None:
    from metroflow.learning.cost_to_go_audit import audit_feature_target_relation
    from metroflow.learning.cost_to_go_features import COST_TO_GO_FEATURE_NAMES

    features = np.zeros((2, len(COST_TO_GO_FEATURE_NAMES)), dtype=np.float32)
    scale_index = COST_TO_GO_FEATURE_NAMES.index("global_max_travel_time_by_one_tick")
    features[:, scale_index] = invalid_scale

    with pytest.raises(ValueError, match="normalization scale must be > 0"):
        audit_feature_target_relation(
            features,
            np.asarray((1.0, 1.0), dtype=np.float32),
            np.asarray(("map-a", "map-b"), dtype=object),
        )


@pytest.mark.parametrize(
    ("field", "rejected_value"),
    (
        ("nonconstant_feature_share", 0.69),
        ("target_standard_deviation", 0.0),
        ("all_maps_have_closure_support", False),
        ("all_state_rows_retained", False),
        ("all_maps_have_v1_split", False),
        ("map_holdout_feasible", False),
        ("feature_target_relation_passed", False),
        ("dynamic_feature_changed_share", 0.0),
        ("dynamic_target_changed_share", 0.0),
        ("dynamic_joint_changed_share", 0.0),
    ),
)
def test_feature_audit_gate_fails_closed_for_each_term(field, rejected_value) -> None:
    from metroflow.learning.cost_to_go_audit import (
        CostToGoFeatureAuditConfig,
        evaluate_cost_to_go_feature_audit_gate,
    )

    values = {
        "config": CostToGoFeatureAuditConfig(),
        "nonconstant_feature_share": 0.95,
        "target_standard_deviation": 1.0,
        "all_maps_have_closure_support": True,
        "all_state_rows_retained": True,
        "all_maps_have_v1_split": True,
        "map_holdout_feasible": True,
        "feature_target_relation_passed": True,
        "dynamic_feature_changed_share": 0.5,
        "dynamic_target_changed_share": 0.5,
        "dynamic_joint_changed_share": 0.5,
    }
    assert evaluate_cost_to_go_feature_audit_gate(**values) is True
    values[field] = rejected_value
    assert evaluate_cost_to_go_feature_audit_gate(**values) is False


def test_feature_audit_gate_rejects_nonfinite_and_nonboolean_inputs() -> None:
    from metroflow.learning.cost_to_go_audit import (
        CostToGoFeatureAuditConfig,
        evaluate_cost_to_go_feature_audit_gate,
    )

    values = {
        "config": CostToGoFeatureAuditConfig(),
        "nonconstant_feature_share": 0.95,
        "target_standard_deviation": 1.0,
        "all_maps_have_closure_support": True,
        "all_state_rows_retained": True,
        "all_maps_have_v1_split": True,
        "map_holdout_feasible": True,
        "feature_target_relation_passed": True,
        "dynamic_feature_changed_share": 0.5,
        "dynamic_target_changed_share": 0.5,
        "dynamic_joint_changed_share": 0.5,
    }
    with pytest.raises(ValueError, match="boolean inputs"):
        evaluate_cost_to_go_feature_audit_gate(
            **{**values, "all_state_rows_retained": "false"}
        )
    with pytest.raises(ValueError, match="nonconstant_feature_share"):
        evaluate_cost_to_go_feature_audit_gate(
            **{**values, "nonconstant_feature_share": float("inf")}
        )


def test_noncanonical_threshold_profile_cannot_authorize_pr50() -> None:
    from metroflow.learning.cost_to_go_audit import (
        CostToGoFeatureAuditConfig,
        evaluate_cost_to_go_feature_audit_gate,
    )

    config = CostToGoFeatureAuditConfig(minimum_nonconstant_feature_share=0.2)
    assert config.canonical_gate_profile is False
    assert (
        evaluate_cost_to_go_feature_audit_gate(
            config=config,
            nonconstant_feature_share=1.0,
            target_standard_deviation=1.0,
            all_maps_have_closure_support=True,
            all_state_rows_retained=True,
            all_maps_have_v1_split=True,
            map_holdout_feasible=True,
            feature_target_relation_passed=True,
            dynamic_feature_changed_share=1.0,
            dynamic_target_changed_share=1.0,
            dynamic_joint_changed_share=1.0,
        )
        is False
    )


def test_dynamic_response_requires_feature_and_target_change_on_same_row() -> None:
    from metroflow.learning.cost_to_go_audit import audit_dynamic_response
    from metroflow.learning.cost_to_go_features import COST_TO_GO_FEATURE_NAMES

    base_inputs = {name: 0.0 for name in COST_TO_GO_FEATURE_NAMES}
    base_inputs["global_max_travel_time_by_one_tick"] = 1.0

    def record(node_id: int, inputs, target: float):
        return SimpleNamespace(
            features={
                "destination_node_id": 9,
                "node_id": node_id,
                "model_inputs": inputs,
            },
            labels={"label_cost_to_go": target},
        )

    changed_inputs = {**base_inputs, "global_mean_travel_time_by_max": 0.5}
    free = (
        record(1, base_inputs, 1.0),
        record(2, base_inputs, 2.0),
    )
    stressed = (
        record(1, changed_inputs, 1.0),
        record(2, base_inputs, 3.0),
    )
    audit = audit_dynamic_response(
        free,
        stressed,
        expected_record_count=2,
        expected_keys=frozenset(((9, 1), (9, 2))),
    )

    assert audit.feature_changed_share == 0.5
    assert audit.target_changed_share == 0.5
    assert audit.joint_changed_share == 0.0
    assert audit.row_identity_aligned is True

    duplicate = (free[0], free[0])
    with pytest.raises(ValueError, match="duplicate row keys"):
        audit_dynamic_response(
            duplicate,
            stressed,
            expected_record_count=2,
            expected_keys=frozenset(((9, 1), (9, 2))),
        )
    missing = audit_dynamic_response(
        free[:1],
        stressed[:1],
        expected_record_count=2,
        expected_keys=frozenset(((9, 1), (9, 2))),
    )
    assert missing.row_identity_aligned is False
    assert missing.matched_row_count == 1


def test_dynamic_response_aggregate_weights_unequal_map_sizes_by_rows() -> None:
    from metroflow.learning.cost_to_go_audit import (
        _aggregate_dynamic_response_runs,
    )

    runs = (
        SimpleNamespace(
            expected_record_count_per_state=100,
            dynamic_matched_row_count=100,
            dynamic_feature_changed_count=1,
            dynamic_target_changed_count=1,
            dynamic_joint_changed_count=1,
            all_state_rows_retained=True,
        ),
        SimpleNamespace(
            expected_record_count_per_state=1,
            dynamic_matched_row_count=1,
            dynamic_feature_changed_count=1,
            dynamic_target_changed_count=1,
            dynamic_joint_changed_count=1,
            all_state_rows_retained=True,
        ),
    )

    aggregate = _aggregate_dynamic_response_runs(runs)

    assert aggregate.matched_row_count == 101
    assert aggregate.joint_changed_count == 2
    assert aggregate.feature_changed_share == pytest.approx(2.0 / 101.0)
    assert aggregate.target_changed_share == pytest.approx(2.0 / 101.0)
    assert aggregate.joint_changed_share == pytest.approx(2.0 / 101.0)


def test_feature_audit_import_does_not_load_accelerators() -> None:
    script = """
import sys
import metroflow.learning.cost_to_go_audit  # noqa: F401
print('jax', 'jax' in sys.modules)
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
        "torch False",
        "_metroflow_rust False",
    ]
