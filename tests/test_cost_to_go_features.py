from __future__ import annotations

from dataclasses import replace
import subprocess
import sys

import numpy as np
import pytest

from metroflow.flow.state import create_link_state


def _feature_fixture():
    from metroflow.city.graph import Node, RoadClass, RoadLink, build_road_network_csr

    network = build_road_network_csr(
        nodes=(
            Node(1, x=0.0, y=0.0),
            Node(2, x=100.0, y=0.0),
            Node(3, x=0.0, y=100.0),
            Node(4, x=100.0, y=100.0),
        ),
        links=(
            RoadLink(10, 1, 2, RoadClass.ARTERIAL, 100.0, 10.0, 5.0),
            RoadLink(11, 2, 4, RoadClass.ARTERIAL, 100.0, 10.0, 5.0),
            RoadLink(12, 1, 3, RoadClass.COLLECTOR, 100.0, 10.0, 4.0),
            RoadLink(13, 3, 4, RoadClass.COLLECTOR, 100.0, 10.0, 4.0),
            RoadLink(14, 4, 1, RoadClass.ARTERIAL, 141.4, 10.0, 3.0),
        ),
    )
    state = create_link_state(
        network.link_count,
        travel_time_cost=(5.0, 1.0, 2.0, 1.0, 8.0),
        capacity_veh_per_tick=(5.0, 5.0, 4.0, 4.0, 3.0),
    )
    return network, state


def _records(*, destinations=(2, 3, 4), scenario_id="feature-fixture"):
    from metroflow.learning.labels import export_cost_to_go_label_records

    network, state = _feature_fixture()
    return export_cost_to_go_label_records(
        road_csr=network,
        link_state=state,
        destination_node_ids=destinations,
        scenario_id=scenario_id,
        tick_index=7,
    )


def test_cost_to_go_rows_expose_versioned_non_identifier_model_inputs() -> None:
    from metroflow.learning.cost_to_go_features import (
        COST_TO_GO_FEATURE_NAMES,
        COST_TO_GO_FEATURE_SCHEMA_VERSION,
        build_cost_to_go_feature_dataset,
    )

    records = _records(destinations=(4,))
    assert records
    record = next(row for row in records if row.features["node_id"] == 1)
    model_inputs = record.features["model_inputs"]

    assert tuple(model_inputs) == COST_TO_GO_FEATURE_NAMES
    assert not any(
        name.endswith("_id") or name.endswith("_index") for name in model_inputs
    )
    assert all(np.isfinite(float(value)) for value in model_inputs.values())
    contract = record.metadata["cost_to_go_feature_contract"]
    assert contract["schema_version"] == COST_TO_GO_FEATURE_SCHEMA_VERSION
    assert tuple(contract["feature_names"]) == COST_TO_GO_FEATURE_NAMES
    assert set(contract["feature_units"].values()) == {"dimensionless"}
    assert contract["identifier_fields_excluded"] == (
        "node_id",
        "node_index",
        "destination_node_id",
        "destination_node_index",
    )
    assert record.source_authority == "baseline_dynamic_potential"
    assert record.routing_backend == "baseline"
    assert record.metadata["cost_to_go_diagnostics"][
        "node_destination_euclidean_distance_m"
    ] == pytest.approx(np.sqrt(20_000.0))
    assert "unseen-destination" in record.metadata["split_claim_scope"]

    dataset = build_cost_to_go_feature_dataset(records)
    assert dataset.features.dtype == np.float32
    assert dataset.targets.dtype == np.float32
    assert dataset.features.flags.c_contiguous
    assert dataset.targets.flags.c_contiguous
    assert not dataset.features.flags.writeable
    assert not dataset.targets.flags.writeable
    assert dataset.features.shape == (4, len(COST_TO_GO_FEATURE_NAMES))
    assert np.isfinite(dataset.features).all()
    assert np.isfinite(dataset.targets).all()


def test_cost_to_go_destination_geometry_features_are_semantic() -> None:
    from metroflow.learning.labels import export_cost_to_go_label_records

    network, state = _feature_fixture()
    baseline = export_cost_to_go_label_records(
        road_csr=network,
        link_state=state,
        destination_node_ids=(4,),
        scenario_id="semantic",
    )
    destination = next(row for row in baseline if row.features["node_id"] == 4)
    assert destination.features["model_inputs"]["relative_x_by_spatial_diagonal"] == 0.0
    assert destination.features["model_inputs"]["relative_y_by_spatial_diagonal"] == 0.0
    assert destination.features["model_inputs"]["euclidean_distance_by_spatial_diagonal"] == 0.0
    assert destination.features["model_inputs"]["is_destination"] == 1.0

    assert "unseen-destination" in destination.metadata["split_claim_scope"]


def test_cost_to_go_absolute_travel_scale_is_not_lost_by_normalization() -> None:
    from metroflow.learning.cost_to_go_features import build_cost_to_go_feature_dataset
    from metroflow.learning.labels import export_cost_to_go_label_records

    network, state = _feature_fixture()
    baseline = export_cost_to_go_label_records(
        road_csr=network,
        link_state=state,
        destination_node_ids=(4,),
        scenario_id="travel-scale",
    )
    scaled_state = create_link_state(
        network.link_count,
        travel_time_cost=np.asarray(state.travel_time_cost) * 2.0,
        capacity_veh_per_tick=state.capacity_veh_per_tick,
    )
    scaled = export_cost_to_go_label_records(
        road_csr=network,
        link_state=scaled_state,
        destination_node_ids=(4,),
        scenario_id="travel-scale",
    )
    baseline_dataset = build_cost_to_go_feature_dataset(baseline)
    scaled_dataset = build_cost_to_go_feature_dataset(scaled)
    scale_index = baseline_dataset.feature_names.index(
        "global_max_travel_time_by_one_tick"
    )

    np.testing.assert_allclose(
        scaled_dataset.features[:, scale_index],
        baseline_dataset.features[:, scale_index] * 2.0,
    )
    np.testing.assert_allclose(scaled_dataset.targets, baseline_dataset.targets * 2.0)
    assert baseline_dataset.dynamic_state_fingerprints != scaled_dataset.dynamic_state_fingerprints
    assert set(baseline_dataset.split_group_keys) == set(scaled_dataset.split_group_keys)


def test_cost_to_go_positive_capacity_change_updates_capacity_features_only() -> None:
    from metroflow.learning.cost_to_go_features import build_cost_to_go_feature_dataset
    from metroflow.learning.labels import export_cost_to_go_label_records

    network, state = _feature_fixture()
    baseline = export_cost_to_go_label_records(
        road_csr=network,
        link_state=state,
        destination_node_ids=(4,),
        scenario_id="capacity",
    )
    capacity = np.asarray(state.capacity_veh_per_tick).copy()
    capacity[0] = 2.5
    changed_state = create_link_state(
        network.link_count,
        travel_time_cost=state.travel_time_cost,
        capacity_veh_per_tick=capacity,
    )
    changed = export_cost_to_go_label_records(
        road_csr=network,
        link_state=changed_state,
        destination_node_ids=(4,),
        scenario_id="capacity",
    )
    baseline_dataset = build_cost_to_go_feature_dataset(baseline)
    changed_dataset = build_cost_to_go_feature_dataset(changed)
    capacity_indices = [
        baseline_dataset.feature_names.index("outgoing_effective_capacity_sum_by_max"),
        baseline_dataset.feature_names.index("incoming_effective_capacity_sum_by_max"),
    ]

    assert not np.array_equal(
        baseline_dataset.features[:, capacity_indices],
        changed_dataset.features[:, capacity_indices],
    )
    np.testing.assert_array_equal(baseline_dataset.targets, changed_dataset.targets)
    assert baseline_dataset.dynamic_state_fingerprints != changed_dataset.dynamic_state_fingerprints


def test_cost_to_go_incident_closure_updates_blocked_features() -> None:
    from metroflow.flow.state import LinkState
    from metroflow.learning.cost_to_go_features import build_cost_to_go_feature_dataset
    from metroflow.learning.labels import export_cost_to_go_label_records

    network, state = _feature_fixture()
    baseline = export_cost_to_go_label_records(
        road_csr=network,
        link_state=state,
        destination_node_ids=(4,),
        scenario_id="closure",
    )
    incident = np.ones((network.link_count,), dtype=np.float32)
    incident[0] = 0.0
    closed_state = LinkState.from_internal_arrays(
        queue_vehicles=state.queue_vehicles,
        inflow_vehicles=state.inflow_vehicles,
        outflow_vehicles=state.outflow_vehicles,
        travel_time_cost=state.travel_time_cost,
        capacity_veh_per_tick=state.capacity_veh_per_tick,
        incident_capacity_multiplier=incident,
        capacity_violation_flags=state.capacity_violation_flags,
    )
    closed = export_cost_to_go_label_records(
        road_csr=network,
        link_state=closed_state,
        destination_node_ids=(4,),
        scenario_id="closure",
    )
    baseline_node = next(row for row in baseline if row.features["node_id"] == 1)
    closed_node = next(row for row in closed if row.features["node_id"] == 1)

    assert baseline_node.features["model_inputs"]["outgoing_blocked_link_fraction"] == 0.0
    assert closed_node.features["model_inputs"]["outgoing_blocked_link_fraction"] == 0.5
    baseline_dataset = build_cost_to_go_feature_dataset(baseline)
    closed_dataset = build_cost_to_go_feature_dataset(closed)
    assert baseline_dataset.dynamic_state_fingerprints != closed_dataset.dynamic_state_fingerprints


def test_cost_to_go_static_fingerprint_and_features_bind_node_geometry() -> None:
    from metroflow.city.graph import build_road_network_csr
    from metroflow.learning.cost_to_go_features import build_cost_to_go_feature_dataset
    from metroflow.learning.labels import export_cost_to_go_label_records

    network, state = _feature_fixture()
    moved_nodes = tuple(
        replace(node, x=node.x + (35.0 if node.node_id == 1 else 0.0))
        for node in network.nodes
    )
    moved = build_road_network_csr(nodes=moved_nodes, links=network.links, turns=network.turns)
    original_records = export_cost_to_go_label_records(
        road_csr=network,
        link_state=state,
        destination_node_ids=(4,),
        scenario_id="geometry",
    )
    moved_records = export_cost_to_go_label_records(
        road_csr=moved,
        link_state=state,
        destination_node_ids=(4,),
        scenario_id="geometry",
    )
    original = build_cost_to_go_feature_dataset(original_records)
    changed = build_cost_to_go_feature_dataset(moved_records)

    assert original.static_network_fingerprints != changed.static_network_fingerprints
    assert not np.array_equal(original.features, changed.features)
    original_targets = {
        int(row.features["node_id"]): float(row.labels["label_cost_to_go"])
        for row in original_records
    }
    moved_targets = {
        int(row.features["node_id"]): float(row.labels["label_cost_to_go"])
        for row in moved_records
    }
    assert original_targets == moved_targets


def test_cost_to_go_group_split_is_order_independent_and_leakage_safe() -> None:
    from metroflow.learning.cost_to_go_features import (
        build_cost_to_go_feature_dataset,
        split_cost_to_go_feature_dataset,
    )

    records = _records(scenario_id="scenario-a") + _records(scenario_id="scenario-b")
    forward = build_cost_to_go_feature_dataset(records)
    reverse = build_cost_to_go_feature_dataset(tuple(reversed(records)))
    first = split_cost_to_go_feature_dataset(
        forward,
        validation_group_fraction=0.34,
        split_seed=73,
    )
    second = split_cost_to_go_feature_dataset(
        reverse,
        validation_group_fraction=0.34,
        split_seed=73,
    )

    assert forward.dataset_fingerprint == reverse.dataset_fingerprint
    assert first.split_fingerprint == second.split_fingerprint
    assert set(first.train_group_keys).isdisjoint(first.validation_group_keys)
    assert first.train_indices.size > 0
    assert first.validation_indices.size > 0
    assert set(forward.split_group_keys[index] for index in first.train_indices) == set(
        first.train_group_keys
    )
    assert set(
        forward.split_group_keys[index] for index in first.validation_indices
    ) == set(first.validation_group_keys)
    destination_groups: dict[int, set[str]] = {}
    for record in records:
        destination_groups.setdefault(
            int(record.features["destination_node_id"]), set()
        ).add(str(record.metadata["split_group_key"]))
    assert all(len(group_keys) == 1 for group_keys in destination_groups.values())


def test_cost_to_go_dataset_and_split_fail_closed_on_legacy_or_single_group_rows() -> None:
    from metroflow.learning.cost_to_go_features import (
        build_cost_to_go_feature_dataset,
        split_cost_to_go_feature_dataset,
    )
    from metroflow.learning.labels import SimulatorLabelRecord

    legacy = SimulatorLabelRecord(
        label_kind="cost_to_go",
        source_authority="baseline_dynamic_potential",
        scenario_id="legacy",
        tick_index=0,
        routing_backend="baseline",
        features={
            "node_id": 1,
            "node_index": 0,
            "destination_node_id": 2,
            "destination_node_index": 1,
        },
        labels={"label_cost_to_go": 1.0},
    )
    with pytest.raises(ValueError, match="model_inputs"):
        build_cost_to_go_feature_dataset((legacy,))

    one_group = build_cost_to_go_feature_dataset(_records(destinations=(4,)))
    with pytest.raises(ValueError, match="at least two split groups"):
        split_cost_to_go_feature_dataset(one_group)


def test_cost_to_go_public_value_objects_reject_schema_and_index_leakage() -> None:
    from metroflow.learning.cost_to_go_features import (
        build_cost_to_go_feature_dataset,
        split_cost_to_go_feature_dataset,
    )

    dataset = build_cost_to_go_feature_dataset(_records())
    with pytest.raises(ValueError, match="canonical"):
        replace(
            dataset,
            feature_names=tuple(f"wrong_{index}" for index in range(dataset.features.shape[1])),
        )
    with pytest.raises(ValueError, match="provenance"):
        replace(dataset, static_network_fingerprints=("",))
    with pytest.raises(ValueError, match="dataset_fingerprint"):
        replace(dataset, dataset_fingerprint="forged-dataset")
    with pytest.raises(TypeError):
        dataset.metadata["runtime_authority"] = "nn"
    with pytest.raises(ValueError, match="authority contract"):
        replace(
            dataset,
            metadata={**dataset.metadata, "runtime_authority": "nn"},
            dataset_fingerprint="",
        )
    split = split_cost_to_go_feature_dataset(dataset, validation_group_fraction=0.34)
    with pytest.raises(ValueError, match="overlap"):
        replace(
            split,
            validation_indices=np.append(
                split.validation_indices,
                split.train_indices[0],
            ),
        )
    with pytest.raises(ValueError, match="groups must be non-empty"):
        replace(split, train_group_keys=())
    with pytest.raises(ValueError, match="split_fingerprint"):
        replace(split, split_fingerprint="forged-split")
    with pytest.raises(ValueError, match="split algorithm"):
        replace(split, split_algorithm="", split_fingerprint="")
    assert not split.train_indices.flags.writeable
    assert not split.validation_indices.flags.writeable


def test_cost_to_go_dataset_recomputes_split_key_from_input_provenance() -> None:
    from metroflow.learning.cost_to_go_features import build_cost_to_go_feature_dataset

    record = _records(destinations=(4,))[0]
    forged = replace(
        record,
        metadata={**record.metadata, "split_group_key": "forged-destination-group"},
        fingerprint="",
    )
    with pytest.raises(ValueError, match="does not match input provenance"):
        build_cost_to_go_feature_dataset((forged,))


def test_cost_to_go_dataset_rejects_extra_invalid_or_conflicting_rows() -> None:
    from metroflow.learning.cost_to_go_features import build_cost_to_go_feature_dataset

    record = _records(destinations=(4,))[0]
    with_extra = replace(
        record,
        features={
            **record.features,
            "model_inputs": {
                **record.features["model_inputs"],
                "target_derived_extra": 1.0,
            },
        },
        fingerprint="",
    )
    with pytest.raises(ValueError, match="exactly the canonical"):
        build_cost_to_go_feature_dataset((with_extra,))

    invalid_binary = replace(
        record,
        features={
            **record.features,
            "model_inputs": {
                **record.features["model_inputs"],
                "is_destination": 0.5,
            },
        },
        fingerprint="",
    )
    with pytest.raises(ValueError, match="is_destination must be binary"):
        build_cost_to_go_feature_dataset((invalid_binary,))

    negative_target = replace(
        record,
        labels={"label_cost_to_go": -1.0},
        fingerprint="",
    )
    with pytest.raises(ValueError, match="label_cost_to_go must be >= 0"):
        build_cost_to_go_feature_dataset((negative_target,))

    conflicting = replace(
        record,
        labels={"label_cost_to_go": float(record.labels["label_cost_to_go"]) + 1.0},
        fingerprint="",
    )
    with pytest.raises(ValueError, match="duplicate row provenance"):
        build_cost_to_go_feature_dataset((record, conflicting))
    with pytest.raises(ValueError, match="SimulatorLabelRecord"):
        build_cost_to_go_feature_dataset((object(),))


def test_cost_to_go_v1_split_rejects_mixed_static_networks() -> None:
    from metroflow.city.graph import build_road_network_csr
    from metroflow.learning.cost_to_go_features import (
        build_cost_to_go_feature_dataset,
        split_cost_to_go_feature_dataset,
    )
    from metroflow.learning.labels import export_cost_to_go_label_records

    network, state = _feature_fixture()
    moved = build_road_network_csr(
        nodes=tuple(
            replace(node, x=node.x + (25.0 if node.node_id == 1 else 0.0))
            for node in network.nodes
        ),
        links=network.links,
        turns=network.turns,
    )
    records = export_cost_to_go_label_records(
        road_csr=network,
        link_state=state,
        destination_node_ids=(2, 3),
        scenario_id="network-a",
    ) + export_cost_to_go_label_records(
        road_csr=moved,
        link_state=state,
        destination_node_ids=(2, 3),
        scenario_id="network-b",
    )
    dataset = build_cost_to_go_feature_dataset(records)

    assert len(dataset.static_network_fingerprints) == 2
    with pytest.raises(ValueError, match="exactly one static network"):
        split_cost_to_go_feature_dataset(dataset)


def test_cost_to_go_feature_imports_do_not_load_accelerators() -> None:
    script = """
import sys
import metroflow.learning.cost_to_go_features  # noqa: F401
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


def test_cost_to_go_feature_contract_is_public_experiment_api() -> None:
    import metroflow.learning as learning

    assert hasattr(learning, "COST_TO_GO_FEATURE_NAMES")
    assert hasattr(learning, "CostToGoFeatureDataset")
    assert hasattr(learning, "build_cost_to_go_feature_dataset")
    assert hasattr(learning, "split_cost_to_go_feature_dataset")
