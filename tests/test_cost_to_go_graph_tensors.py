from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from metroflow.flow.state import LinkState, create_link_state


def _graph_fixture(*, geometry_offset: float = 0.0):
    from metroflow.city.graph import Node, RoadClass, RoadLink, build_road_network_csr

    network = build_road_network_csr(
        nodes=(
            Node(1, x=0.0 + geometry_offset, y=0.0),
            Node(2, x=100.0, y=0.0),
            Node(3, x=0.0, y=100.0),
            Node(4, x=100.0, y=100.0),
        ),
        links=(
            RoadLink(10, 1, 2, RoadClass.ARTERIAL, 100.0, 10.0, 5.0, lanes=2),
            RoadLink(11, 2, 4, RoadClass.ARTERIAL, 100.0, 10.0, 5.0, lanes=2),
            RoadLink(12, 1, 3, RoadClass.COLLECTOR, 100.0, 8.0, 4.0),
            RoadLink(13, 3, 4, RoadClass.COLLECTOR, 100.0, 8.0, 4.0),
            RoadLink(14, 4, 1, RoadClass.LOCAL, 141.4, 6.0, 3.0),
        ),
    )
    state = create_link_state(
        network.link_count,
        travel_time_cost=(5.0, 1.0, 2.0, 1.0, 8.0),
        capacity_veh_per_tick=(5.0, 5.0, 4.0, 4.0, 3.0),
    )
    return network, state


def _small_graph_fixture():
    from metroflow.city.graph import Node, RoadClass, RoadLink, build_road_network_csr

    network = build_road_network_csr(
        nodes=(
            Node(21, x=0.0, y=0.0),
            Node(22, x=50.0, y=0.0),
            Node(23, x=100.0, y=0.0),
        ),
        links=(
            RoadLink(31, 21, 22, RoadClass.LOCAL, 50.0, 5.0, 2.0),
            RoadLink(32, 22, 23, RoadClass.LOCAL, 50.0, 5.0, 2.0),
            RoadLink(33, 23, 22, RoadClass.LOCAL, 50.0, 5.0, 2.0),
            RoadLink(34, 22, 21, RoadClass.LOCAL, 50.0, 5.0, 2.0),
        ),
    )
    state = create_link_state(
        network.link_count,
        travel_time_cost=(2.0, 3.0, 3.0, 2.0),
        capacity_veh_per_tick=(2.0, 2.0, 2.0, 2.0),
    )
    return network, state


def _sample(*, destination_node_id: int = 4):
    from metroflow.learning.cost_to_go_graph_tensors import (
        build_cost_to_go_graph_sample,
    )

    network, state = _graph_fixture()
    return build_cost_to_go_graph_sample(
        network,
        state,
        destination_node_id=destination_node_id,
    )


def test_graph_sample_preserves_directed_schema_and_immutable_arrays() -> None:
    from metroflow.learning.cost_to_go_features import COST_TO_GO_FEATURE_NAMES
    from metroflow.learning.cost_to_go_graph_tensors import (
        COST_TO_GO_EDGE_FEATURE_NAMES,
        COST_TO_GO_GRAPH_CONTRACT_FINGERPRINT,
        COST_TO_GO_GRAPH_SCHEMA_VERSION,
        build_cost_to_go_graph_sample,
    )

    network, state = _graph_fixture()
    sample = build_cost_to_go_graph_sample(network, state, destination_node_id=4)

    assert COST_TO_GO_GRAPH_SCHEMA_VERSION == 1
    assert sample.graph_contract_fingerprint == COST_TO_GO_GRAPH_CONTRACT_FINGERPRINT
    assert sample.node_feature_names == COST_TO_GO_FEATURE_NAMES
    assert sample.edge_feature_names == COST_TO_GO_EDGE_FEATURE_NAMES
    assert sample.node_features.shape == (network.node_count, len(COST_TO_GO_FEATURE_NAMES))
    assert sample.edge_index.shape == (2, network.link_count)
    assert sample.edge_features.shape == (
        network.link_count,
        len(COST_TO_GO_EDGE_FEATURE_NAMES),
    )
    np.testing.assert_array_equal(
        sample.edge_index,
        np.stack(
            (
                network.link_src_node_index,
                network.link_dst_node_index,
            ),
            axis=0,
        ),
    )
    assert sample.node_features.dtype == np.float32
    assert sample.edge_features.dtype == np.float32
    assert sample.edge_index.dtype == np.int32
    assert sample.blocked_link_mask.dtype == np.bool_
    assert sample.node_targets.dtype == np.float32
    assert sample.target_mask.dtype == np.bool_
    for array in (
        sample.node_features,
        sample.edge_index,
        sample.edge_features,
        sample.blocked_link_mask,
        sample.node_targets,
        sample.target_mask,
    ):
        assert array.flags.c_contiguous
        assert not array.flags.writeable
        with pytest.raises(ValueError):
            array.setflags(write=True)
    assert not any(
        name.endswith("_id") or name.endswith("_index")
        for name in sample.node_feature_names + sample.edge_feature_names
    )
    road_class_indices = [
        index
        for index, name in enumerate(sample.edge_feature_names)
        if name.startswith("road_class_")
    ]
    np.testing.assert_array_equal(
        np.sum(sample.edge_features[:, road_class_indices], axis=1),
        np.ones((network.link_count,), dtype=np.float32),
    )


def test_graph_sample_targets_match_baseline_dynamic_potential() -> None:
    from metroflow.learning.cost_to_go_graph_tensors import (
        build_cost_to_go_graph_sample,
    )
    from metroflow.routing.dynamic_potential import compute_dynamic_potential_state

    network, state = _graph_fixture()
    sample = build_cost_to_go_graph_sample(network, state, destination_node_id=4)
    baseline = compute_dynamic_potential_state(
        network,
        destination_node_id=4,
        link_state=state,
        routing_backend="baseline",
    )
    baseline_cost = np.asarray(baseline.node_cost_to_go, dtype=np.float32)
    expected_mask = np.isfinite(baseline_cost) & (baseline_cost < np.float32(5.0e11))

    np.testing.assert_array_equal(sample.target_mask, expected_mask)
    np.testing.assert_allclose(
        sample.node_targets[sample.target_mask],
        baseline_cost[expected_mask],
    )
    assert sample.destination_node_index == network.node_id_to_index[4]
    assert sample.target_mask[sample.destination_node_index]
    assert sample.node_targets[sample.destination_node_index] == 0.0
    assert sample.metadata["label_authority"] == "baseline_dynamic_potential"
    assert sample.metadata["route_legality_authority"] == "baseline_routing"
    assert sample.metadata["runtime_authority"] == "baseline_fallback_only"


def test_graph_sample_masks_unreachable_nodes_without_nonfinite_tensor_values() -> None:
    from metroflow.city.graph import Node, RoadClass, RoadLink, build_road_network_csr
    from metroflow.learning.cost_to_go_graph_tensors import (
        build_cost_to_go_graph_sample,
    )

    network = build_road_network_csr(
        nodes=(Node(1), Node(2), Node(3)),
        links=(
            RoadLink(10, 1, 2, RoadClass.LOCAL, 10.0, 5.0, 1.0),
            RoadLink(11, 2, 1, RoadClass.LOCAL, 10.0, 5.0, 1.0),
            RoadLink(12, 3, 1, RoadClass.LOCAL, 10.0, 5.0, 1.0),
        ),
    )
    state = create_link_state(network.link_count)
    sample = build_cost_to_go_graph_sample(network, state, destination_node_id=3)

    np.testing.assert_array_equal(sample.target_mask, (False, False, True))
    np.testing.assert_array_equal(sample.node_targets, (0.0, 0.0, 0.0))
    assert np.isfinite(sample.node_features).all()
    assert np.isfinite(sample.edge_features).all()
    assert np.isfinite(sample.node_targets).all()


def test_graph_sample_fingerprints_separate_static_and_dynamic_changes() -> None:
    from metroflow.city.graph import build_road_network_csr
    from metroflow.learning.cost_to_go_graph_tensors import (
        build_cost_to_go_graph_sample,
    )

    network, state = _graph_fixture()
    baseline = build_cost_to_go_graph_sample(network, state, destination_node_id=4)
    incident = np.ones((network.link_count,), dtype=np.float32)
    incident[0] = 0.0
    changed_state = LinkState.from_internal_arrays(
        queue_vehicles=np.zeros((network.link_count,), dtype=np.float32),
        inflow_vehicles=np.zeros((network.link_count,), dtype=np.float32),
        outflow_vehicles=np.zeros((network.link_count,), dtype=np.float32),
        travel_time_cost=np.asarray(state.travel_time_cost) * 1.5,
        capacity_veh_per_tick=state.capacity_veh_per_tick,
        incident_capacity_multiplier=incident,
        capacity_violation_flags=np.zeros((network.link_count,), dtype=np.bool_),
    )
    dynamic = build_cost_to_go_graph_sample(
        network,
        changed_state,
        destination_node_id=4,
    )
    moved_network, moved_state = _graph_fixture(geometry_offset=25.0)
    moved = build_cost_to_go_graph_sample(
        moved_network,
        moved_state,
        destination_node_id=4,
    )

    assert baseline.static_network_fingerprint == dynamic.static_network_fingerprint
    assert baseline.dynamic_state_fingerprint != dynamic.dynamic_state_fingerprint
    assert baseline.sample_fingerprint != dynamic.sample_fingerprint
    assert not np.array_equal(baseline.edge_features, dynamic.edge_features)
    assert dynamic.blocked_link_mask[0]
    assert baseline.static_network_fingerprint != moved.static_network_fingerprint
    assert baseline.sample_fingerprint != moved.sample_fingerprint
    assert not np.array_equal(baseline.node_features, moved.node_features)

    redirected_links = (
        replace(network.links[0], src_node_id=2, dst_node_id=1),
        *network.links[1:],
    )
    redirected_network = build_road_network_csr(
        nodes=network.nodes,
        links=redirected_links,
        turns=network.turns,
    )
    redirected = build_cost_to_go_graph_sample(
        redirected_network,
        state,
        destination_node_id=4,
    )
    assert baseline.static_network_fingerprint != redirected.static_network_fingerprint
    assert not np.array_equal(baseline.edge_index, redirected.edge_index)


def test_graph_edge_features_and_dynamic_fingerprints_cover_each_input() -> None:
    from metroflow.learning.cost_to_go_graph_tensors import (
        build_cost_to_go_graph_sample,
    )

    network, state = _graph_fixture()
    baseline = build_cost_to_go_graph_sample(network, state, destination_node_id=4)
    names = baseline.edge_feature_names
    spatial_diagonal = np.sqrt(20_000.0)
    expected_link_zero = {
        "length_by_spatial_diagonal": 100.0 / spatial_diagonal,
        "free_flow_speed_by_max": 1.0,
        "lanes_by_max": 1.0,
        "travel_time_cost_by_max": 5.0 / 8.0,
        "effective_capacity_by_max": 1.0,
        "incident_capacity_multiplier": 1.0,
        "is_blockable": 1.0,
        "road_class_arterial": 1.0,
    }
    for name, expected in expected_link_zero.items():
        assert baseline.edge_features[0, names.index(name)] == pytest.approx(expected)

    travel = np.asarray(state.travel_time_cost).copy()
    travel[3] *= 1.5
    travel_state = create_link_state(
        network.link_count,
        travel_time_cost=travel,
        capacity_veh_per_tick=state.capacity_veh_per_tick,
    )
    capacity = np.asarray(state.capacity_veh_per_tick).copy()
    capacity[0] = 2.5
    capacity_state = create_link_state(
        network.link_count,
        travel_time_cost=state.travel_time_cost,
        capacity_veh_per_tick=capacity,
    )
    incident = np.ones((network.link_count,), dtype=np.float32)
    incident[0] = 0.0
    closure_state = LinkState.from_internal_arrays(
        queue_vehicles=np.zeros((network.link_count,), dtype=np.float32),
        inflow_vehicles=np.zeros((network.link_count,), dtype=np.float32),
        outflow_vehicles=np.zeros((network.link_count,), dtype=np.float32),
        travel_time_cost=state.travel_time_cost,
        capacity_veh_per_tick=state.capacity_veh_per_tick,
        incident_capacity_multiplier=incident,
        capacity_violation_flags=np.zeros((network.link_count,), dtype=np.bool_),
    )
    travel_sample = build_cost_to_go_graph_sample(
        network,
        travel_state,
        destination_node_id=4,
    )
    capacity_sample = build_cost_to_go_graph_sample(
        network,
        capacity_state,
        destination_node_id=4,
    )
    closure_sample = build_cost_to_go_graph_sample(
        network,
        closure_state,
        destination_node_id=4,
    )

    assert baseline.dynamic_state_fingerprint != travel_sample.dynamic_state_fingerprint
    assert baseline.dynamic_state_fingerprint != capacity_sample.dynamic_state_fingerprint
    assert baseline.dynamic_state_fingerprint != closure_sample.dynamic_state_fingerprint
    assert not np.array_equal(baseline.edge_features, travel_sample.edge_features)
    assert not np.array_equal(baseline.edge_features, capacity_sample.edge_features)
    assert not np.array_equal(baseline.edge_features, closure_sample.edge_features)
    np.testing.assert_array_equal(baseline.node_targets, capacity_sample.node_targets)
    assert closure_sample.blocked_link_mask[0]


def test_graph_blocked_mask_keeps_nonblockable_zero_capacity_link_usable() -> None:
    from metroflow.city.graph import Node, RoadClass, RoadLink, build_road_network_csr
    from metroflow.learning.cost_to_go_graph_tensors import (
        build_cost_to_go_graph_sample,
    )

    network = build_road_network_csr(
        nodes=(Node(1), Node(2)),
        links=(
            RoadLink(
                10,
                1,
                2,
                RoadClass.LOCAL,
                10.0,
                5.0,
                0.0,
                is_blockable=False,
            ),
            RoadLink(11, 2, 1, RoadClass.LOCAL, 10.0, 5.0, 1.0),
        ),
    )
    state = create_link_state(
        network.link_count,
        travel_time_cost=(2.0, 2.0),
        capacity_veh_per_tick=(0.0, 1.0),
    )
    sample = build_cost_to_go_graph_sample(network, state, destination_node_id=2)

    assert not sample.blocked_link_mask[0]
    assert sample.target_mask[network.node_id_to_index[1]]
    capacity_index = sample.edge_feature_names.index("effective_capacity_by_max")
    assert sample.edge_features[0, capacity_index] == 0.0


def test_graph_sample_public_contract_rejects_forgery_and_authority_changes() -> None:
    from metroflow.learning import cost_to_go_graph_tensors as graph_module
    from metroflow.learning.cost_to_go_graph_tensors import CostToGoGraphSample

    sample = _sample()

    assert not hasattr(graph_module, "_SAMPLE_SOURCE_TOKEN")
    with pytest.raises(TypeError, match="use build_cost_to_go_graph_sample"):
        CostToGoGraphSample(
            node_features=sample.node_features,
            edge_index=sample.edge_index,
            edge_features=sample.edge_features,
            blocked_link_mask=sample.blocked_link_mask,
            node_targets=sample.node_targets,
            target_mask=sample.target_mask,
            destination_node_index=sample.destination_node_index,
            node_feature_names=sample.node_feature_names,
            edge_feature_names=sample.edge_feature_names,
            static_network_fingerprint="f" * 64,
            dynamic_state_fingerprint=sample.dynamic_state_fingerprint,
            graph_contract_fingerprint=sample.graph_contract_fingerprint,
        )
    with pytest.raises(TypeError, match="use build_cost_to_go_graph_sample"):
        replace(sample, static_network_fingerprint="f" * 64)
    with pytest.raises(TypeError):
        sample.metadata["runtime_authority"] = "graph_nn"


def test_graph_batch_padding_masks_and_memory_budget_are_exact() -> None:
    from metroflow.learning.cost_to_go_graph_tensors import (
        build_cost_to_go_graph_batch,
        build_cost_to_go_graph_sample,
    )

    large = _sample(destination_node_id=4)
    small_network, small_state = _small_graph_fixture()
    small = build_cost_to_go_graph_sample(
        small_network,
        small_state,
        destination_node_id=23,
    )
    batch = build_cost_to_go_graph_batch(
        (large, small),
        maximum_padded_bytes=1_000_000,
    )

    assert batch.batch_size == 2
    assert batch.maximum_node_count == large.node_count
    assert batch.maximum_edge_count == large.edge_count
    assert batch.node_features.shape[:2] == (2, large.node_count)
    assert batch.edge_features.shape[:2] == (2, large.edge_count)
    assert batch.edge_index.shape == (2, 2, large.edge_count)
    np.testing.assert_array_equal(
        batch.node_features[1, : small.node_count],
        small.node_features,
    )
    np.testing.assert_array_equal(
        batch.edge_index[1, :, : small.edge_count],
        small.edge_index,
    )
    np.testing.assert_array_equal(batch.node_mask[1], (True, True, True, False))
    np.testing.assert_array_equal(
        batch.edge_mask[1],
        (True, True, True, True, False),
    )
    assert np.all(batch.node_features[1, small.node_count :] == 0.0)
    assert np.all(batch.edge_features[1, small.edge_count :] == 0.0)
    assert np.all(batch.edge_index[1, :, small.edge_count :] == -1)
    assert not np.any(batch.blocked_link_mask[1, small.edge_count :])
    assert not np.any(batch.target_mask[1, small.node_count :])
    assert batch.padded_byte_count <= batch.maximum_padded_bytes
    assert batch.estimated_peak_byte_count == batch.padded_byte_count * 2
    assert batch.estimated_peak_byte_count <= batch.maximum_padded_bytes
    for array in (
        batch.node_features,
        batch.edge_index,
        batch.edge_features,
        batch.blocked_link_mask,
        batch.node_targets,
        batch.node_mask,
        batch.edge_mask,
        batch.target_mask,
        batch.destination_node_indices,
        batch.node_counts,
        batch.edge_counts,
    ):
        assert array.flags.c_contiguous
        assert not array.flags.writeable
        with pytest.raises(ValueError):
            array.setflags(write=True)
    with pytest.raises(ValueError, match="at least one graph sample"):
        build_cost_to_go_graph_batch(())
    with pytest.raises(ValueError, match="maximum_padded_bytes"):
        build_cost_to_go_graph_batch((large, small), maximum_padded_bytes=1)


def test_graph_batch_rejects_forged_padding_or_fingerprint() -> None:
    from metroflow.learning.cost_to_go_graph_tensors import (
        build_cost_to_go_graph_batch,
        build_cost_to_go_graph_sample,
    )

    large = _sample()
    network, state = _small_graph_fixture()
    small = build_cost_to_go_graph_sample(network, state, destination_node_id=23)
    batch = build_cost_to_go_graph_batch((large, small))
    forged_index = np.asarray(batch.edge_index).copy()
    forged_index[1, 0, -1] = 0

    with pytest.raises(ValueError, match="padded edge indices"):
        replace(batch, edge_index=forged_index, batch_fingerprint="")
    with pytest.raises(ValueError, match="batch_fingerprint"):
        replace(batch, batch_fingerprint="forged")
    forged_features = np.asarray(batch.node_features).copy()
    forged_features[0, 0, 0] += 0.25
    with pytest.raises(ValueError, match="batch sample fingerprint"):
        replace(
            batch,
            node_features=forged_features,
            batch_fingerprint="",
        )


def test_graph_map_split_is_reorder_independent_and_leakage_safe() -> None:
    from metroflow.learning.cost_to_go_graph_tensors import (
        build_cost_to_go_graph_sample,
        compute_cost_to_go_map_holdout_fingerprint,
        split_cost_to_go_graph_samples,
    )

    train_network, train_state = _graph_fixture()
    validation_network, validation_state = _graph_fixture(geometry_offset=25.0)
    samples = (
        build_cost_to_go_graph_sample(train_network, train_state, destination_node_id=4),
        build_cost_to_go_graph_sample(train_network, train_state, destination_node_id=3),
        build_cost_to_go_graph_sample(
            validation_network,
            validation_state,
            destination_node_id=4,
        ),
        build_cost_to_go_graph_sample(
            validation_network,
            validation_state,
            destination_node_id=3,
        ),
    )
    validation_fingerprint = samples[2].static_network_fingerprint
    train_fingerprint = samples[0].static_network_fingerprint
    holdout_fingerprint = compute_cost_to_go_map_holdout_fingerprint(
        train_static_network_fingerprints=(train_fingerprint,),
        validation_static_network_fingerprints=(validation_fingerprint,),
        held_out_seed=29,
        split_seed=49,
    )
    first = split_cost_to_go_graph_samples(
        samples,
        validation_static_network_fingerprints=(validation_fingerprint,),
        map_holdout_split_fingerprint=holdout_fingerprint,
        map_holdout_held_out_seed=29,
        map_holdout_selection_seed=49,
    )
    second = split_cost_to_go_graph_samples(
        tuple(reversed(samples)),
        validation_static_network_fingerprints=(validation_fingerprint,),
        map_holdout_split_fingerprint=holdout_fingerprint,
        map_holdout_held_out_seed=29,
        map_holdout_selection_seed=49,
    )

    assert first.split_fingerprint == second.split_fingerprint
    assert first.sample_fingerprints == second.sample_fingerprints
    assert set(first.train_static_network_fingerprints).isdisjoint(
        first.validation_static_network_fingerprints
    )
    assert first.train_indices.size == 2
    assert first.validation_indices.size == 2
    assert set(first.train_indices) | set(first.validation_indices) == set(range(4))
    assert not first.train_indices.flags.writeable
    assert not first.validation_indices.flags.writeable
    with pytest.raises(ValueError):
        first.train_indices.setflags(write=True)
    with pytest.raises(ValueError, match="unknown validation"):
        split_cost_to_go_graph_samples(
            samples,
            validation_static_network_fingerprints=("b" * 64,),
            map_holdout_split_fingerprint=holdout_fingerprint,
            map_holdout_held_out_seed=29,
            map_holdout_selection_seed=49,
        )
    with pytest.raises(ValueError, match="both train and validation"):
        split_cost_to_go_graph_samples(
            samples,
            validation_static_network_fingerprints=tuple(
                sorted({sample.static_network_fingerprint for sample in samples})
            ),
            map_holdout_split_fingerprint=holdout_fingerprint,
            map_holdout_held_out_seed=29,
            map_holdout_selection_seed=49,
        )
    with pytest.raises(ValueError, match="does not match split network provenance"):
        split_cost_to_go_graph_samples(
            samples,
            validation_static_network_fingerprints=(validation_fingerprint,),
            map_holdout_split_fingerprint="a" * 64,
            map_holdout_held_out_seed=29,
            map_holdout_selection_seed=49,
        )


def test_graph_holdout_fingerprint_matches_pr49_canonical_artifact() -> None:
    from metroflow.learning.cost_to_go_graph_tensors import (
        compute_cost_to_go_map_holdout_fingerprint,
    )

    artifact_path = (
        Path(__file__).resolve().parents[1]
        / "artifacts"
        / "cost_to_go_feature_audit_20260711"
        / "cost-to-go-feature-audit.json"
    )
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    holdout = payload["map_holdout"]

    assert compute_cost_to_go_map_holdout_fingerprint(
        train_static_network_fingerprints=holdout[
            "train_static_network_fingerprints"
        ],
        validation_static_network_fingerprints=holdout[
            "validation_static_network_fingerprints"
        ],
        held_out_seed=holdout["held_out_seed"],
        split_seed=holdout["split_seed"],
    ) == holdout["split_fingerprint"]


def test_graph_tensor_import_does_not_load_accelerators() -> None:
    script = """
import sys
import metroflow.learning.cost_to_go_graph_tensors  # noqa: F401
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


def test_graph_tensor_contract_is_available_from_learning_facade() -> None:
    from metroflow import learning

    assert learning.COST_TO_GO_GRAPH_SCHEMA_VERSION == 1
    assert learning.CostToGoGraphSample.__name__ == "CostToGoGraphSample"
    assert callable(learning.build_cost_to_go_graph_sample)
    assert callable(learning.build_cost_to_go_graph_batch)
    assert callable(learning.compute_cost_to_go_map_holdout_fingerprint)
    assert callable(learning.split_cost_to_go_graph_samples)
