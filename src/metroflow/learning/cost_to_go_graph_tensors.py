"""Immutable NumPy graph tensors for cost-to-go experiments.

This module defines experiment substrate only. Baseline dynamic-potential
routing remains the label and route-legality authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from types import MappingProxyType
from typing import Any, Mapping, Sequence

import numpy as np

from metroflow.city.graph import RoadClass, RoadNetworkCSR
from metroflow.flow.state import LinkState
from metroflow.learning.cost_to_go_features import (
    COST_TO_GO_FEATURE_CONTRACT_FINGERPRINT,
    COST_TO_GO_FEATURE_NAMES,
    _build_cost_to_go_feature_context,
)
from metroflow.routing.dynamic_potential import compute_dynamic_potential_state

__all__ = [
    "COST_TO_GO_EDGE_FEATURE_NAMES",
    "COST_TO_GO_GRAPH_CONTRACT_FINGERPRINT",
    "COST_TO_GO_GRAPH_SCHEMA_VERSION",
    "CostToGoGraphBatch",
    "CostToGoGraphSample",
    "CostToGoGraphSplit",
    "build_cost_to_go_graph_batch",
    "build_cost_to_go_graph_sample",
    "compute_cost_to_go_map_holdout_fingerprint",
    "split_cost_to_go_graph_samples",
]

COST_TO_GO_GRAPH_SCHEMA_VERSION = 1
_ROAD_CLASS_VALUES = tuple(road_class.value for road_class in RoadClass)
COST_TO_GO_EDGE_FEATURE_NAMES = (
    "length_by_spatial_diagonal",
    "free_flow_speed_by_max",
    "lanes_by_max",
    "travel_time_cost_by_max",
    "effective_capacity_by_max",
    "incident_capacity_multiplier",
    "is_blockable",
    *(f"road_class_{value}" for value in _ROAD_CLASS_VALUES),
)
_EDGE_FEATURE_UNITS = {
    name: "dimensionless" for name in COST_TO_GO_EDGE_FEATURE_NAMES
}
_GRAPH_ALGORITHM = "directed_dynamic_cost_to_go_graph_v1"
_BATCH_ALGORITHM = "prefix_padded_graph_batch_v1"
_SPLIT_ALGORITHM = "explicit_static_network_holdout_v1"
_DEFAULT_MAXIMUM_PADDED_BYTES = 256 * 1024 * 1024
_BATCH_PEAK_ALLOCATION_MULTIPLIER = 2
_UNREACHABLE_COST_THRESHOLD = np.float32(5.0e11)
_AUTHORITY_METADATA = MappingProxyType(
    {
        "claim_scope": "experiment_substrate_not_validation",
        "label_authority": "baseline_dynamic_potential",
        "route_legality_authority": "baseline_routing",
        "runtime_authority": "baseline_fallback_only",
    }
)
_GRAPH_SCHEMA_DESCRIPTOR = {
    "algorithm": _GRAPH_ALGORITHM,
    "authority_metadata": dict(_AUTHORITY_METADATA),
    "batch": {
        "algorithm": _BATCH_ALGORITHM,
        "edge_index_padding": -1,
        "mask_padding": False,
        "numeric_padding": 0,
        "padding_layout": "contiguous_prefix",
        "preallocation_byte_budget_required": True,
        "projected_peak_allocation_multiplier": _BATCH_PEAK_ALLOCATION_MULTIPLIER,
    },
    "sample_tensors": {
        "blocked_link_mask": {
            "dtype": "bool",
            "semantics": "effective_capacity_zero_and_static_blockable",
            "shape": "(edge_count,)",
        },
        "edge_features": {
            "dtype": "float32",
            "names": COST_TO_GO_EDGE_FEATURE_NAMES,
            "shape": "(edge_count, edge_feature_count)",
            "units": _EDGE_FEATURE_UNITS,
        },
        "edge_index": {
            "dtype": "int32",
            "semantics": "directed_local_source_destination_indices",
            "shape": "(2, edge_count)",
        },
        "node_features": {
            "contract_fingerprint": COST_TO_GO_FEATURE_CONTRACT_FINGERPRINT,
            "dtype": "float32",
            "names": COST_TO_GO_FEATURE_NAMES,
            "shape": "(node_count, node_feature_count)",
        },
        "node_targets": {
            "authority": "baseline_dynamic_potential",
            "dtype": "float32",
            "masked_value": 0.0,
            "shape": "(node_count,)",
        },
        "target_mask": {
            "dtype": "bool",
            "semantics": "finite_reachable_baseline_target",
            "shape": "(node_count,)",
            "unreachable_threshold": float(_UNREACHABLE_COST_THRESHOLD),
        },
    },
    "schema_version": COST_TO_GO_GRAPH_SCHEMA_VERSION,
    "split": {
        "algorithm": _SPLIT_ALGORITHM,
        "group_unit": "static_network_fingerprint",
        "source_holdout_fingerprint": "recomputed_pr49_map_holdout_payload",
    },
}
COST_TO_GO_GRAPH_CONTRACT_FINGERPRINT = hashlib.sha256(
    json.dumps(
        _GRAPH_SCHEMA_DESCRIPTOR,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()


@dataclass(frozen=True, init=False)
class CostToGoGraphSample:
    """One directed graph, dynamic state, and destination label field."""

    node_features: np.ndarray
    edge_index: np.ndarray
    edge_features: np.ndarray
    blocked_link_mask: np.ndarray
    node_targets: np.ndarray
    target_mask: np.ndarray
    destination_node_index: int
    node_feature_names: tuple[str, ...]
    edge_feature_names: tuple[str, ...]
    static_network_fingerprint: str
    dynamic_state_fingerprint: str
    graph_contract_fingerprint: str
    sample_fingerprint: str = ""
    metadata: Mapping[str, Any] = field(default_factory=lambda: _AUTHORITY_METADATA)

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise TypeError("use build_cost_to_go_graph_sample for verified construction")

    def _validate_and_freeze(self) -> None:
        node_features = _copy_array(self.node_features, np.float32)
        edge_index = _copy_array(self.edge_index, np.int32)
        edge_features = _copy_array(self.edge_features, np.float32)
        blocked = _copy_array(self.blocked_link_mask, np.bool_)
        targets = _copy_array(self.node_targets, np.float32)
        target_mask = _copy_array(self.target_mask, np.bool_)
        node_names = tuple(str(value) for value in self.node_feature_names)
        edge_names = tuple(str(value) for value in self.edge_feature_names)
        if node_names != COST_TO_GO_FEATURE_NAMES:
            raise ValueError("node_feature_names must match the cost-to-go feature contract")
        if edge_names != COST_TO_GO_EDGE_FEATURE_NAMES:
            raise ValueError("edge_feature_names must match the graph edge contract")
        if node_features.ndim != 2 or node_features.shape[1] != len(node_names):
            raise ValueError("node_features must have shape (node_count, node_feature_count)")
        node_count = int(node_features.shape[0])
        if node_count < 1:
            raise ValueError("graph sample must contain at least one node")
        if edge_index.ndim != 2 or edge_index.shape[0] != 2:
            raise ValueError("edge_index must have shape (2, edge_count)")
        edge_count = int(edge_index.shape[1])
        if edge_features.shape != (edge_count, len(edge_names)):
            raise ValueError("edge_features must match edge count and schema width")
        if blocked.shape != (edge_count,):
            raise ValueError("blocked_link_mask must match edge count")
        if targets.shape != (node_count,) or target_mask.shape != (node_count,):
            raise ValueError("node_targets and target_mask must match node count")
        if edge_count and bool(np.any((edge_index < 0) | (edge_index >= node_count))):
            raise ValueError("edge_index values must be valid local node indices")
        if not np.isfinite(node_features).all() or not np.isfinite(edge_features).all():
            raise ValueError("graph feature arrays must be finite")
        if not np.isfinite(targets).all() or bool(np.any(targets < 0.0)):
            raise ValueError("node_targets must be finite and >= 0")
        if bool(np.any(targets[np.logical_not(target_mask)] != 0.0)):
            raise ValueError("masked node_targets must use zero padding")
        destination = int(self.destination_node_index)
        if not 0 <= destination < node_count:
            raise ValueError("destination_node_index must be in range")
        if not bool(target_mask[destination]) or float(targets[destination]) != 0.0:
            raise ValueError("destination target must be valid and zero")
        _validate_destination_feature(node_features, destination)
        _validate_edge_feature_domains(edge_features, edge_names)
        _validate_blocked_link_mask(edge_features, blocked)
        static_fingerprint = _require_sha256(
            self.static_network_fingerprint,
            name="static_network_fingerprint",
        )
        dynamic_fingerprint = _require_sha256(
            self.dynamic_state_fingerprint,
            name="dynamic_state_fingerprint",
        )
        contract_fingerprint = str(self.graph_contract_fingerprint)
        if contract_fingerprint != COST_TO_GO_GRAPH_CONTRACT_FINGERPRINT:
            raise ValueError("unexpected graph_contract_fingerprint")
        metadata = _freeze_authority_metadata(self.metadata)
        expected_fingerprint = _sample_fingerprint_from_arrays(
            node_features=node_features,
            edge_index=edge_index,
            edge_features=edge_features,
            blocked_link_mask=blocked,
            node_targets=targets,
            target_mask=target_mask,
            destination_node_index=destination,
            static_network_fingerprint=static_fingerprint,
            dynamic_state_fingerprint=dynamic_fingerprint,
            graph_contract_fingerprint=contract_fingerprint,
            metadata=metadata,
        )
        supplied_fingerprint = str(self.sample_fingerprint).strip()
        if supplied_fingerprint and supplied_fingerprint != expected_fingerprint:
            raise ValueError("sample_fingerprint does not match graph sample contents")
        for array in (
            node_features,
            edge_index,
            edge_features,
            blocked,
            targets,
            target_mask,
        ):
            array.setflags(write=False)
        object.__setattr__(self, "node_features", node_features)
        object.__setattr__(self, "edge_index", edge_index)
        object.__setattr__(self, "edge_features", edge_features)
        object.__setattr__(self, "blocked_link_mask", blocked)
        object.__setattr__(self, "node_targets", targets)
        object.__setattr__(self, "target_mask", target_mask)
        object.__setattr__(self, "destination_node_index", destination)
        object.__setattr__(self, "node_feature_names", node_names)
        object.__setattr__(self, "edge_feature_names", edge_names)
        object.__setattr__(self, "static_network_fingerprint", static_fingerprint)
        object.__setattr__(self, "dynamic_state_fingerprint", dynamic_fingerprint)
        object.__setattr__(self, "graph_contract_fingerprint", contract_fingerprint)
        object.__setattr__(self, "sample_fingerprint", expected_fingerprint)
        object.__setattr__(self, "metadata", metadata)

    @property
    def node_count(self) -> int:
        return int(self.node_features.shape[0])

    @property
    def edge_count(self) -> int:
        return int(self.edge_index.shape[1])


@dataclass(frozen=True)
class CostToGoGraphBatch:
    """Prefix-padded graph batch with explicit validity masks."""

    node_features: np.ndarray
    edge_index: np.ndarray
    edge_features: np.ndarray
    blocked_link_mask: np.ndarray
    node_targets: np.ndarray
    node_mask: np.ndarray
    edge_mask: np.ndarray
    target_mask: np.ndarray
    destination_node_indices: np.ndarray
    node_counts: np.ndarray
    edge_counts: np.ndarray
    sample_fingerprints: tuple[str, ...]
    static_network_fingerprints: tuple[str, ...]
    dynamic_state_fingerprints: tuple[str, ...]
    graph_contract_fingerprint: str
    maximum_padded_bytes: int
    padded_byte_count: int = 0
    estimated_peak_byte_count: int = 0
    batch_fingerprint: str = ""
    metadata: Mapping[str, Any] = field(default_factory=lambda: _AUTHORITY_METADATA)

    def __post_init__(self) -> None:
        node_features = _copy_array(self.node_features, np.float32)
        edge_index = _copy_array(self.edge_index, np.int32)
        edge_features = _copy_array(self.edge_features, np.float32)
        blocked = _copy_array(self.blocked_link_mask, np.bool_)
        targets = _copy_array(self.node_targets, np.float32)
        node_mask = _copy_array(self.node_mask, np.bool_)
        edge_mask = _copy_array(self.edge_mask, np.bool_)
        target_mask = _copy_array(self.target_mask, np.bool_)
        destinations = _copy_array(self.destination_node_indices, np.int32)
        node_counts = _copy_array(self.node_counts, np.int32)
        edge_counts = _copy_array(self.edge_counts, np.int32)
        sample_fingerprints = tuple(str(value) for value in self.sample_fingerprints)
        static_fingerprints = tuple(
            str(value) for value in self.static_network_fingerprints
        )
        dynamic_fingerprints = tuple(
            str(value) for value in self.dynamic_state_fingerprints
        )
        batch_size = len(sample_fingerprints)
        if batch_size < 1 or len(set(sample_fingerprints)) != batch_size:
            raise ValueError("graph batch requires unique non-empty sample fingerprints")
        if len(static_fingerprints) != batch_size or len(dynamic_fingerprints) != batch_size:
            raise ValueError("batch provenance fingerprints must match batch size")
        for name, values in (
            ("sample_fingerprints", sample_fingerprints),
            ("static_network_fingerprints", static_fingerprints),
            ("dynamic_state_fingerprints", dynamic_fingerprints),
        ):
            for value in values:
                _require_sha256(value, name=name)
        if node_features.ndim != 3 or node_features.shape[0] != batch_size:
            raise ValueError("node_features must have shape (batch, nodes, features)")
        if node_features.shape[2] != len(COST_TO_GO_FEATURE_NAMES):
            raise ValueError("node_features width must match the node feature contract")
        maximum_node_count = int(node_features.shape[1])
        if maximum_node_count < 1:
            raise ValueError("graph batch must contain at least one node per padded row")
        if edge_index.ndim != 3 or edge_index.shape[:2] != (batch_size, 2):
            raise ValueError("edge_index must have shape (batch, 2, edges)")
        maximum_edge_count = int(edge_index.shape[2])
        if edge_features.shape != (
            batch_size,
            maximum_edge_count,
            len(COST_TO_GO_EDGE_FEATURE_NAMES),
        ):
            raise ValueError("edge_features must match padded edge shape")
        expected_node_shape = (batch_size, maximum_node_count)
        expected_edge_shape = (batch_size, maximum_edge_count)
        if targets.shape != expected_node_shape:
            raise ValueError("node_targets must match padded node shape")
        if node_mask.shape != expected_node_shape or target_mask.shape != expected_node_shape:
            raise ValueError("node_mask and target_mask must match padded node shape")
        if blocked.shape != expected_edge_shape or edge_mask.shape != expected_edge_shape:
            raise ValueError("blocked_link_mask and edge_mask must match padded edge shape")
        if destinations.shape != (batch_size,):
            raise ValueError("destination_node_indices must match batch size")
        if node_counts.shape != (batch_size,) or edge_counts.shape != (batch_size,):
            raise ValueError("node_counts and edge_counts must match batch size")
        if bool(np.any((node_counts < 1) | (node_counts > maximum_node_count))):
            raise ValueError("node_counts must be within padded node bounds")
        if bool(np.any((edge_counts < 0) | (edge_counts > maximum_edge_count))):
            raise ValueError("edge_counts must be within padded edge bounds")
        expected_node_mask = (
            np.arange(maximum_node_count, dtype=np.int32)[None, :]
            < node_counts[:, None]
        )
        expected_edge_mask = (
            np.arange(maximum_edge_count, dtype=np.int32)[None, :]
            < edge_counts[:, None]
        )
        if not np.array_equal(node_mask, expected_node_mask):
            raise ValueError("node_mask must use contiguous prefix padding")
        if not np.array_equal(edge_mask, expected_edge_mask):
            raise ValueError("edge_mask must use contiguous prefix padding")
        if bool(np.any(target_mask & np.logical_not(node_mask))):
            raise ValueError("target_mask must be a subset of node_mask")
        if bool(np.any(blocked & np.logical_not(edge_mask))):
            raise ValueError("blocked_link_mask must be a subset of edge_mask")
        _validate_batch_padding(
            node_features=node_features,
            edge_index=edge_index,
            edge_features=edge_features,
            node_targets=targets,
            node_mask=node_mask,
            edge_mask=edge_mask,
            target_mask=target_mask,
        )
        if not np.isfinite(node_features).all() or not np.isfinite(edge_features).all():
            raise ValueError("batch feature arrays must be finite")
        if not np.isfinite(targets).all() or bool(np.any(targets < 0.0)):
            raise ValueError("batch node_targets must be finite and >= 0")
        if bool(np.any(targets[np.logical_not(target_mask)] != 0.0)):
            raise ValueError("masked batch node_targets must use zero padding")
        for batch_index in range(batch_size):
            node_count = int(node_counts[batch_index])
            edge_count = int(edge_counts[batch_index])
            destination = int(destinations[batch_index])
            if not 0 <= destination < node_count:
                raise ValueError("batch destination index must be within real nodes")
            if not bool(target_mask[batch_index, destination]):
                raise ValueError("batch destination must have a valid target")
            if float(targets[batch_index, destination]) != 0.0:
                raise ValueError("batch destination target must be zero")
            real_indices = edge_index[batch_index, :, :edge_count]
            if edge_count and bool(np.any((real_indices < 0) | (real_indices >= node_count))):
                raise ValueError("real batch edge indices must reference real nodes")
            real_node_features = node_features[batch_index, :node_count]
            real_edge_features = edge_features[batch_index, :edge_count]
            real_blocked = blocked[batch_index, :edge_count]
            _validate_destination_feature(real_node_features, destination)
            _validate_edge_feature_domains(
                real_edge_features,
                COST_TO_GO_EDGE_FEATURE_NAMES,
            )
            _validate_blocked_link_mask(real_edge_features, real_blocked)
            expected_sample_fingerprint = _sample_fingerprint_from_arrays(
                node_features=real_node_features,
                edge_index=real_indices,
                edge_features=real_edge_features,
                blocked_link_mask=real_blocked,
                node_targets=targets[batch_index, :node_count],
                target_mask=target_mask[batch_index, :node_count],
                destination_node_index=destination,
                static_network_fingerprint=static_fingerprints[batch_index],
                dynamic_state_fingerprint=dynamic_fingerprints[batch_index],
                graph_contract_fingerprint=COST_TO_GO_GRAPH_CONTRACT_FINGERPRINT,
                metadata=_AUTHORITY_METADATA,
            )
            if expected_sample_fingerprint != sample_fingerprints[batch_index]:
                raise ValueError("batch sample fingerprint does not match padded contents")
        contract_fingerprint = str(self.graph_contract_fingerprint)
        if contract_fingerprint != COST_TO_GO_GRAPH_CONTRACT_FINGERPRINT:
            raise ValueError("unexpected graph_contract_fingerprint")
        metadata = _freeze_authority_metadata(self.metadata)
        maximum_bytes = int(self.maximum_padded_bytes)
        if maximum_bytes < 1:
            raise ValueError("maximum_padded_bytes must be >= 1")
        arrays = (
            node_features,
            edge_index,
            edge_features,
            blocked,
            targets,
            node_mask,
            edge_mask,
            target_mask,
            destinations,
            node_counts,
            edge_counts,
        )
        actual_bytes = sum(int(array.nbytes) for array in arrays)
        estimated_peak_bytes = actual_bytes * _BATCH_PEAK_ALLOCATION_MULTIPLIER
        if estimated_peak_bytes > maximum_bytes:
            raise ValueError("padded graph batch exceeds maximum_padded_bytes")
        supplied_bytes = int(self.padded_byte_count)
        if supplied_bytes not in (0, actual_bytes):
            raise ValueError("padded_byte_count does not match batch arrays")
        supplied_peak_bytes = int(self.estimated_peak_byte_count)
        if supplied_peak_bytes not in (0, estimated_peak_bytes):
            raise ValueError("estimated_peak_byte_count does not match batch arrays")
        expected_fingerprint = _fingerprint_json(
            {
                "algorithm": _BATCH_ALGORITHM,
                "arrays": tuple(_array_digest(array) for array in arrays),
                "dynamic_state_fingerprints": dynamic_fingerprints,
                "graph_contract_fingerprint": contract_fingerprint,
                "maximum_padded_bytes": maximum_bytes,
                "estimated_peak_byte_count": estimated_peak_bytes,
                "metadata": _json_ready(metadata),
                "sample_fingerprints": sample_fingerprints,
                "static_network_fingerprints": static_fingerprints,
            }
        )
        supplied_fingerprint = str(self.batch_fingerprint).strip()
        if supplied_fingerprint and supplied_fingerprint != expected_fingerprint:
            raise ValueError("batch_fingerprint does not match graph batch contents")
        for array in arrays:
            array.setflags(write=False)
        for name, value in (
            ("node_features", node_features),
            ("edge_index", edge_index),
            ("edge_features", edge_features),
            ("blocked_link_mask", blocked),
            ("node_targets", targets),
            ("node_mask", node_mask),
            ("edge_mask", edge_mask),
            ("target_mask", target_mask),
            ("destination_node_indices", destinations),
            ("node_counts", node_counts),
            ("edge_counts", edge_counts),
        ):
            object.__setattr__(self, name, value)
        object.__setattr__(self, "sample_fingerprints", sample_fingerprints)
        object.__setattr__(self, "static_network_fingerprints", static_fingerprints)
        object.__setattr__(self, "dynamic_state_fingerprints", dynamic_fingerprints)
        object.__setattr__(self, "graph_contract_fingerprint", contract_fingerprint)
        object.__setattr__(self, "maximum_padded_bytes", maximum_bytes)
        object.__setattr__(self, "padded_byte_count", actual_bytes)
        object.__setattr__(self, "estimated_peak_byte_count", estimated_peak_bytes)
        object.__setattr__(self, "batch_fingerprint", expected_fingerprint)
        object.__setattr__(self, "metadata", metadata)

    @property
    def batch_size(self) -> int:
        return int(self.node_features.shape[0])

    @property
    def maximum_node_count(self) -> int:
        return int(self.node_features.shape[1])

    @property
    def maximum_edge_count(self) -> int:
        return int(self.edge_features.shape[1])


@dataclass(frozen=True)
class CostToGoGraphSplit:
    """Canonical sample ordering and static-network holdout indices."""

    sample_fingerprints: tuple[str, ...]
    sample_static_network_fingerprints: tuple[str, ...]
    train_indices: np.ndarray
    validation_indices: np.ndarray
    train_static_network_fingerprints: tuple[str, ...]
    validation_static_network_fingerprints: tuple[str, ...]
    map_holdout_split_fingerprint: str
    map_holdout_held_out_seed: int
    map_holdout_selection_seed: int
    split_algorithm: str = _SPLIT_ALGORITHM
    split_fingerprint: str = ""

    def __post_init__(self) -> None:
        samples = tuple(str(value) for value in self.sample_fingerprints)
        sample_static = tuple(
            str(value) for value in self.sample_static_network_fingerprints
        )
        train = _copy_array(self.train_indices, np.int32)
        validation = _copy_array(self.validation_indices, np.int32)
        train_static = tuple(
            sorted(str(value) for value in self.train_static_network_fingerprints)
        )
        validation_static = tuple(
            sorted(str(value) for value in self.validation_static_network_fingerprints)
        )
        row_count = len(samples)
        if row_count < 2 or len(set(samples)) != row_count:
            raise ValueError("graph split requires at least two unique samples")
        if len(sample_static) != row_count:
            raise ValueError("sample static fingerprints must match sample count")
        for name, values in (
            ("sample_fingerprints", samples),
            ("sample_static_network_fingerprints", sample_static),
            ("train_static_network_fingerprints", train_static),
            ("validation_static_network_fingerprints", validation_static),
        ):
            for value in values:
                _require_sha256(value, name=name)
        if train.ndim != 1 or validation.ndim != 1:
            raise ValueError("graph split indices must be 1-D")
        if train.size < 1 or validation.size < 1:
            raise ValueError("graph split requires both train and validation samples")
        train_set = set(int(value) for value in train)
        validation_set = set(int(value) for value in validation)
        if len(train_set) != int(train.size) or len(validation_set) != int(
            validation.size
        ):
            raise ValueError("graph split indices must be unique")
        if train_set & validation_set:
            raise ValueError("graph split indices must not overlap")
        if train_set | validation_set != set(range(row_count)):
            raise ValueError("graph split indices must cover every sample exactly once")
        actual_train_static = tuple(sorted({sample_static[index] for index in train_set}))
        actual_validation_static = tuple(
            sorted({sample_static[index] for index in validation_set})
        )
        if actual_train_static != train_static or actual_validation_static != validation_static:
            raise ValueError("graph split static fingerprints do not match indices")
        if set(train_static) & set(validation_static):
            raise ValueError("graph split static networks must not overlap")
        holdout_fingerprint = _require_sha256(
            self.map_holdout_split_fingerprint,
            name="map_holdout_split_fingerprint",
        )
        held_out_seed = int(self.map_holdout_held_out_seed)
        selection_seed = int(self.map_holdout_selection_seed)
        expected_holdout_fingerprint = compute_cost_to_go_map_holdout_fingerprint(
            train_static_network_fingerprints=train_static,
            validation_static_network_fingerprints=validation_static,
            held_out_seed=held_out_seed,
            split_seed=selection_seed,
        )
        if holdout_fingerprint != expected_holdout_fingerprint:
            raise ValueError(
                "map_holdout_split_fingerprint does not match split network provenance"
            )
        algorithm = str(self.split_algorithm)
        if algorithm != _SPLIT_ALGORITHM:
            raise ValueError("unexpected graph split algorithm")
        expected_fingerprint = _fingerprint_json(
            {
                "algorithm": algorithm,
                "map_holdout_split_fingerprint": holdout_fingerprint,
                "map_holdout_held_out_seed": held_out_seed,
                "map_holdout_selection_seed": selection_seed,
                "sample_fingerprints": samples,
                "sample_static_network_fingerprints": sample_static,
                "train_indices": tuple(sorted(train_set)),
                "train_static_network_fingerprints": train_static,
                "validation_indices": tuple(sorted(validation_set)),
                "validation_static_network_fingerprints": validation_static,
            }
        )
        supplied_fingerprint = str(self.split_fingerprint).strip()
        if supplied_fingerprint and supplied_fingerprint != expected_fingerprint:
            raise ValueError("split_fingerprint does not match graph split contents")
        train = _immutable_copy_array(np.sort(train), np.int32)
        validation = _immutable_copy_array(np.sort(validation), np.int32)
        object.__setattr__(self, "sample_fingerprints", samples)
        object.__setattr__(self, "sample_static_network_fingerprints", sample_static)
        object.__setattr__(self, "train_indices", train)
        object.__setattr__(self, "validation_indices", validation)
        object.__setattr__(self, "train_static_network_fingerprints", train_static)
        object.__setattr__(
            self,
            "validation_static_network_fingerprints",
            validation_static,
        )
        object.__setattr__(self, "map_holdout_split_fingerprint", holdout_fingerprint)
        object.__setattr__(self, "map_holdout_held_out_seed", held_out_seed)
        object.__setattr__(self, "map_holdout_selection_seed", selection_seed)
        object.__setattr__(self, "split_algorithm", algorithm)
        object.__setattr__(self, "split_fingerprint", expected_fingerprint)


def build_cost_to_go_graph_sample(
    road_csr: RoadNetworkCSR,
    link_state: LinkState,
    *,
    destination_node_id: int,
) -> CostToGoGraphSample:
    """Build one baseline-authoritative graph sample."""

    if not isinstance(road_csr, RoadNetworkCSR):
        raise TypeError("road_csr must be a RoadNetworkCSR")
    if not isinstance(link_state, LinkState):
        raise TypeError("link_state must be a LinkState")
    if link_state.link_count != road_csr.link_count:
        raise ValueError("link_state.link_count must match road_csr.link_count")
    destination_id = int(destination_node_id)
    if destination_id not in road_csr.node_id_to_index:
        raise ValueError("destination_node_id must exist in road_csr")
    destination_index = int(road_csr.node_id_to_index[destination_id])
    feature_context = _build_cost_to_go_feature_context(road_csr, link_state)
    node_features = np.asarray(
        [
            [
                feature_context.model_inputs(
                    node_index=node_index,
                    destination_node_index=destination_index,
                )[name]
                for name in COST_TO_GO_FEATURE_NAMES
            ]
            for node_index in range(road_csr.node_count)
        ],
        dtype=np.float32,
    )
    potential = compute_dynamic_potential_state(
        road_csr,
        destination_node_id=destination_id,
        link_state=link_state,
        routing_backend="baseline",
    )
    raw_targets = np.asarray(potential.node_cost_to_go, dtype=np.float32)
    target_mask = np.asarray(
        np.isfinite(raw_targets) & (raw_targets < _UNREACHABLE_COST_THRESHOLD),
        dtype=np.bool_,
    )
    node_targets = np.zeros((road_csr.node_count,), dtype=np.float32)
    node_targets[target_mask] = raw_targets[target_mask]
    edge_features = _build_edge_features(
        road_csr,
        link_state,
        spatial_diagonal_m=feature_context.spatial_diagonal_m,
        maximum_travel_time_cost=feature_context.maximum_travel_time_cost,
    )
    sample = object.__new__(CostToGoGraphSample)
    raw_values = {
        "node_features": node_features,
        "edge_index": np.stack(
            (
                np.asarray(road_csr.link_src_node_index, dtype=np.int32),
                np.asarray(road_csr.link_dst_node_index, dtype=np.int32),
            ),
            axis=0,
        ),
        "edge_features": edge_features,
        "blocked_link_mask": np.asarray(potential.blocked_link_mask, dtype=np.bool_),
        "node_targets": node_targets,
        "target_mask": target_mask,
        "destination_node_index": destination_index,
        "node_feature_names": COST_TO_GO_FEATURE_NAMES,
        "edge_feature_names": COST_TO_GO_EDGE_FEATURE_NAMES,
        "static_network_fingerprint": feature_context.static_network_fingerprint,
        "dynamic_state_fingerprint": feature_context.dynamic_state_fingerprint,
        "graph_contract_fingerprint": COST_TO_GO_GRAPH_CONTRACT_FINGERPRINT,
        "sample_fingerprint": "",
        "metadata": _AUTHORITY_METADATA,
    }
    for name, value in raw_values.items():
        object.__setattr__(sample, name, value)
    sample._validate_and_freeze()
    return sample


def build_cost_to_go_graph_batch(
    samples: Sequence[CostToGoGraphSample],
    *,
    maximum_padded_bytes: int = _DEFAULT_MAXIMUM_PADDED_BYTES,
) -> CostToGoGraphBatch:
    """Pad graph samples after a deterministic pre-allocation byte check."""

    resolved = tuple(samples)
    if not resolved:
        raise ValueError("graph batch requires at least one graph sample")
    if not all(isinstance(sample, CostToGoGraphSample) for sample in resolved):
        raise TypeError("samples must contain only CostToGoGraphSample values")
    if len({sample.sample_fingerprint for sample in resolved}) != len(resolved):
        raise ValueError("graph batch sample fingerprints must be unique")
    maximum_bytes = int(maximum_padded_bytes)
    if maximum_bytes < 1:
        raise ValueError("maximum_padded_bytes must be >= 1")
    batch_size = len(resolved)
    maximum_node_count = max(sample.node_count for sample in resolved)
    maximum_edge_count = max(sample.edge_count for sample in resolved)
    projected_bytes = _projected_batch_bytes(
        batch_size=batch_size,
        maximum_node_count=maximum_node_count,
        maximum_edge_count=maximum_edge_count,
    )
    projected_peak_bytes = projected_bytes * _BATCH_PEAK_ALLOCATION_MULTIPLIER
    if projected_peak_bytes > maximum_bytes:
        raise ValueError("padded graph batch exceeds maximum_padded_bytes")
    node_features = np.zeros(
        (batch_size, maximum_node_count, len(COST_TO_GO_FEATURE_NAMES)),
        dtype=np.float32,
    )
    edge_index = np.full(
        (batch_size, 2, maximum_edge_count),
        -1,
        dtype=np.int32,
    )
    edge_features = np.zeros(
        (batch_size, maximum_edge_count, len(COST_TO_GO_EDGE_FEATURE_NAMES)),
        dtype=np.float32,
    )
    blocked = np.zeros((batch_size, maximum_edge_count), dtype=np.bool_)
    targets = np.zeros((batch_size, maximum_node_count), dtype=np.float32)
    node_mask = np.zeros((batch_size, maximum_node_count), dtype=np.bool_)
    edge_mask = np.zeros((batch_size, maximum_edge_count), dtype=np.bool_)
    target_mask = np.zeros((batch_size, maximum_node_count), dtype=np.bool_)
    destinations = np.zeros((batch_size,), dtype=np.int32)
    node_counts = np.zeros((batch_size,), dtype=np.int32)
    edge_counts = np.zeros((batch_size,), dtype=np.int32)
    for batch_index, sample in enumerate(resolved):
        node_count = sample.node_count
        edge_count = sample.edge_count
        node_features[batch_index, :node_count] = sample.node_features
        edge_index[batch_index, :, :edge_count] = sample.edge_index
        edge_features[batch_index, :edge_count] = sample.edge_features
        blocked[batch_index, :edge_count] = sample.blocked_link_mask
        targets[batch_index, :node_count] = sample.node_targets
        node_mask[batch_index, :node_count] = True
        edge_mask[batch_index, :edge_count] = True
        target_mask[batch_index, :node_count] = sample.target_mask
        destinations[batch_index] = sample.destination_node_index
        node_counts[batch_index] = node_count
        edge_counts[batch_index] = edge_count
    return CostToGoGraphBatch(
        node_features=node_features,
        edge_index=edge_index,
        edge_features=edge_features,
        blocked_link_mask=blocked,
        node_targets=targets,
        node_mask=node_mask,
        edge_mask=edge_mask,
        target_mask=target_mask,
        destination_node_indices=destinations,
        node_counts=node_counts,
        edge_counts=edge_counts,
        sample_fingerprints=tuple(sample.sample_fingerprint for sample in resolved),
        static_network_fingerprints=tuple(
            sample.static_network_fingerprint for sample in resolved
        ),
        dynamic_state_fingerprints=tuple(
            sample.dynamic_state_fingerprint for sample in resolved
        ),
        graph_contract_fingerprint=COST_TO_GO_GRAPH_CONTRACT_FINGERPRINT,
        maximum_padded_bytes=maximum_bytes,
        padded_byte_count=projected_bytes,
        estimated_peak_byte_count=projected_peak_bytes,
        metadata=_AUTHORITY_METADATA,
    )


def compute_cost_to_go_map_holdout_fingerprint(
    *,
    train_static_network_fingerprints: Sequence[str],
    validation_static_network_fingerprints: Sequence[str],
    held_out_seed: int,
    split_seed: int,
) -> str:
    """Recompute the PR49 map-holdout fingerprint from its full payload."""

    raw_train = tuple(str(value).strip().lower() for value in train_static_network_fingerprints)
    raw_validation = tuple(
        str(value).strip().lower()
        for value in validation_static_network_fingerprints
    )
    if len(set(raw_train)) != len(raw_train) or len(set(raw_validation)) != len(
        raw_validation
    ):
        raise ValueError("map holdout static network fingerprints must be unique")
    train = tuple(
        sorted(_require_sha256(value, name="train_static_network_fingerprints") for value in raw_train)
    )
    validation = tuple(
        sorted(
            _require_sha256(
                value,
                name="validation_static_network_fingerprints",
            )
            for value in raw_validation
        )
    )
    if not train or not validation:
        raise ValueError("map holdout requires both train and validation networks")
    if set(train) & set(validation):
        raise ValueError("map holdout train and validation networks must not overlap")
    return _fingerprint_json(
        {
            "held_out_seed": int(held_out_seed),
            "split_seed": int(split_seed),
            "train_static_network_fingerprints": train,
            "validation_static_network_fingerprints": validation,
        }
    )


def split_cost_to_go_graph_samples(
    samples: Sequence[CostToGoGraphSample],
    *,
    validation_static_network_fingerprints: Sequence[str],
    map_holdout_split_fingerprint: str,
    map_holdout_held_out_seed: int,
    map_holdout_selection_seed: int,
) -> CostToGoGraphSplit:
    """Create a deterministic explicit static-network holdout split."""

    resolved = tuple(samples)
    if len(resolved) < 2:
        raise ValueError("graph split requires at least two graph samples")
    if not all(isinstance(sample, CostToGoGraphSample) for sample in resolved):
        raise TypeError("samples must contain only CostToGoGraphSample values")
    ordered = tuple(sorted(resolved, key=lambda sample: sample.sample_fingerprint))
    if len({sample.sample_fingerprint for sample in ordered}) != len(ordered):
        raise ValueError("graph split sample fingerprints must be unique")
    observed_static = {
        sample.static_network_fingerprint for sample in ordered
    }
    validation_static = tuple(
        sorted(
            {
                _require_sha256(value, name="validation_static_network_fingerprints")
                for value in validation_static_network_fingerprints
            }
        )
    )
    if not validation_static:
        raise ValueError("validation_static_network_fingerprints must be non-empty")
    unknown = set(validation_static) - observed_static
    if unknown:
        raise ValueError("graph split contains unknown validation static fingerprints")
    train_static = tuple(sorted(observed_static - set(validation_static)))
    if not train_static:
        raise ValueError("graph split requires both train and validation static networks")
    train_indices = np.asarray(
        [
            index
            for index, sample in enumerate(ordered)
            if sample.static_network_fingerprint in set(train_static)
        ],
        dtype=np.int32,
    )
    validation_indices = np.asarray(
        [
            index
            for index, sample in enumerate(ordered)
            if sample.static_network_fingerprint in set(validation_static)
        ],
        dtype=np.int32,
    )
    return CostToGoGraphSplit(
        sample_fingerprints=tuple(sample.sample_fingerprint for sample in ordered),
        sample_static_network_fingerprints=tuple(
            sample.static_network_fingerprint for sample in ordered
        ),
        train_indices=train_indices,
        validation_indices=validation_indices,
        train_static_network_fingerprints=train_static,
        validation_static_network_fingerprints=validation_static,
        map_holdout_split_fingerprint=map_holdout_split_fingerprint,
        map_holdout_held_out_seed=map_holdout_held_out_seed,
        map_holdout_selection_seed=map_holdout_selection_seed,
    )


def _build_edge_features(
    road_csr: RoadNetworkCSR,
    link_state: LinkState,
    *,
    spatial_diagonal_m: float,
    maximum_travel_time_cost: float,
) -> np.ndarray:
    length = np.asarray([link.length_m for link in road_csr.links], dtype=np.float32)
    speed = np.asarray(
        [link.free_flow_speed_mps for link in road_csr.links],
        dtype=np.float32,
    )
    lanes = np.asarray([link.lanes for link in road_csr.links], dtype=np.float32)
    travel = np.asarray(link_state.travel_time_cost, dtype=np.float32)
    capacity = np.asarray(link_state.capacity_veh_per_tick, dtype=np.float32)
    incident = np.asarray(
        link_state.incident_capacity_multiplier,
        dtype=np.float32,
    )
    effective_capacity = np.asarray(capacity * incident, dtype=np.float32)
    maximum_speed = max(float(np.max(speed, initial=np.float32(0.0))), 1.0e-6)
    maximum_lanes = max(float(np.max(lanes, initial=np.float32(0.0))), 1.0)
    maximum_capacity = max(
        float(np.max(effective_capacity, initial=np.float32(0.0))),
        1.0e-6,
    )
    road_class = np.zeros((road_csr.link_count, len(_ROAD_CLASS_VALUES)), dtype=np.float32)
    road_class_lookup = {value: index for index, value in enumerate(_ROAD_CLASS_VALUES)}
    for link_index, link in enumerate(road_csr.links):
        road_class[link_index, road_class_lookup[link.road_class.value]] = 1.0
    return np.ascontiguousarray(
        np.column_stack(
            (
                length / float(spatial_diagonal_m),
                speed / maximum_speed,
                lanes / maximum_lanes,
                travel / float(maximum_travel_time_cost),
                effective_capacity / maximum_capacity,
                incident,
                np.asarray(
                    [float(link.is_blockable) for link in road_csr.links],
                    dtype=np.float32,
                ),
                road_class,
            )
        ),
        dtype=np.float32,
    )


def _validate_edge_feature_domains(
    values: np.ndarray,
    names: tuple[str, ...],
) -> None:
    positive_names = (
        "length_by_spatial_diagonal",
        "free_flow_speed_by_max",
        "lanes_by_max",
        "travel_time_cost_by_max",
    )
    for name in positive_names:
        if bool(np.any(values[:, names.index(name)] <= 0.0)):
            raise ValueError(f"{name} must be > 0")
    nonnegative = values[:, names.index("effective_capacity_by_max")]
    if bool(np.any(nonnegative < 0.0)):
        raise ValueError("effective_capacity_by_max must be >= 0")
    incident = values[:, names.index("incident_capacity_multiplier")]
    if bool(np.any((incident < 0.0) | (incident > 1.0))):
        raise ValueError("incident_capacity_multiplier must be in [0, 1]")
    binary_indices = [names.index("is_blockable")] + [
        index for index, name in enumerate(names) if name.startswith("road_class_")
    ]
    binary = values[:, binary_indices]
    if bool(np.any((binary != 0.0) & (binary != 1.0))):
        raise ValueError("edge categorical features must be binary")
    road_class_indices = [
        index for index, name in enumerate(names) if name.startswith("road_class_")
    ]
    if values.shape[0] and not np.all(
        np.sum(values[:, road_class_indices], axis=1) == 1.0
    ):
        raise ValueError("every edge must have exactly one road class")


def _validate_destination_feature(
    node_features: np.ndarray,
    destination_node_index: int,
) -> None:
    destination_feature_index = COST_TO_GO_FEATURE_NAMES.index("is_destination")
    destination_values = node_features[:, destination_feature_index]
    if (
        bool(np.any((destination_values != 0.0) & (destination_values != 1.0)))
        or int(np.count_nonzero(destination_values == 1.0)) != 1
        or float(destination_values[int(destination_node_index)]) != 1.0
    ):
        raise ValueError("is_destination must identify exactly the destination node")


def _validate_blocked_link_mask(
    edge_features: np.ndarray,
    blocked_link_mask: np.ndarray,
) -> None:
    capacity_index = COST_TO_GO_EDGE_FEATURE_NAMES.index(
        "effective_capacity_by_max"
    )
    blockable_index = COST_TO_GO_EDGE_FEATURE_NAMES.index("is_blockable")
    expected = np.asarray(
        (edge_features[:, capacity_index] <= 0.0)
        & (edge_features[:, blockable_index] == 1.0),
        dtype=np.bool_,
    )
    if not np.array_equal(blocked_link_mask, expected):
        raise ValueError("blocked_link_mask must match effective capacity and blockability")


def _sample_fingerprint_from_arrays(
    *,
    node_features: np.ndarray,
    edge_index: np.ndarray,
    edge_features: np.ndarray,
    blocked_link_mask: np.ndarray,
    node_targets: np.ndarray,
    target_mask: np.ndarray,
    destination_node_index: int,
    static_network_fingerprint: str,
    dynamic_state_fingerprint: str,
    graph_contract_fingerprint: str,
    metadata: Mapping[str, Any],
) -> str:
    return _fingerprint_json(
        {
            "blocked_link_mask": _array_digest(blocked_link_mask),
            "destination_node_index": int(destination_node_index),
            "dynamic_state_fingerprint": str(dynamic_state_fingerprint),
            "edge_features": _array_digest(edge_features),
            "edge_index": _array_digest(edge_index),
            "graph_contract_fingerprint": str(graph_contract_fingerprint),
            "metadata": _json_ready(metadata),
            "node_features": _array_digest(node_features),
            "node_targets": _array_digest(node_targets),
            "static_network_fingerprint": str(static_network_fingerprint),
            "target_mask": _array_digest(target_mask),
        }
    )


def _validate_batch_padding(
    *,
    node_features: np.ndarray,
    edge_index: np.ndarray,
    edge_features: np.ndarray,
    node_targets: np.ndarray,
    node_mask: np.ndarray,
    edge_mask: np.ndarray,
    target_mask: np.ndarray,
) -> None:
    if bool(np.any(node_features[np.logical_not(node_mask)] != 0.0)):
        raise ValueError("padded node features must be zero")
    padded_edge_index_mask = np.broadcast_to(
        np.logical_not(edge_mask)[:, None, :],
        edge_index.shape,
    )
    if bool(np.any(edge_index[padded_edge_index_mask] != -1)):
        raise ValueError("padded edge indices must be -1")
    if bool(np.any(edge_features[np.logical_not(edge_mask)] != 0.0)):
        raise ValueError("padded edge features must be zero")
    if bool(np.any(node_targets[np.logical_not(node_mask)] != 0.0)):
        raise ValueError("padded node targets must be zero")
    if bool(np.any(target_mask[np.logical_not(node_mask)])):
        raise ValueError("padded target mask values must be false")


def _projected_batch_bytes(
    *,
    batch_size: int,
    maximum_node_count: int,
    maximum_edge_count: int,
) -> int:
    float_bytes = np.dtype(np.float32).itemsize
    int_bytes = np.dtype(np.int32).itemsize
    bool_bytes = np.dtype(np.bool_).itemsize
    return int(
        batch_size * maximum_node_count * len(COST_TO_GO_FEATURE_NAMES) * float_bytes
        + batch_size * 2 * maximum_edge_count * int_bytes
        + batch_size
        * maximum_edge_count
        * len(COST_TO_GO_EDGE_FEATURE_NAMES)
        * float_bytes
        + batch_size * maximum_edge_count * bool_bytes
        + batch_size * maximum_node_count * float_bytes
        + batch_size * maximum_node_count * bool_bytes
        + batch_size * maximum_edge_count * bool_bytes
        + batch_size * maximum_node_count * bool_bytes
        + batch_size * int_bytes
        + batch_size * int_bytes
        + batch_size * int_bytes
    )


def _copy_array(values: Any, dtype: Any) -> np.ndarray:
    return _immutable_copy_array(values, dtype)


def _immutable_copy_array(values: Any, dtype: Any) -> np.ndarray:
    contiguous = np.ascontiguousarray(values, dtype=dtype)
    immutable_buffer = contiguous.tobytes(order="C")
    return np.frombuffer(immutable_buffer, dtype=dtype).reshape(contiguous.shape)


def _array_digest(values: np.ndarray) -> str:
    array = np.ascontiguousarray(values)
    hasher = hashlib.sha256()
    hasher.update(str(array.dtype).encode("ascii"))
    hasher.update(str(tuple(array.shape)).encode("ascii"))
    hasher.update(memoryview(array).cast("B"))
    return hasher.hexdigest()


def _require_sha256(value: Any, *, name: str) -> str:
    resolved = str(value).strip().lower()
    if len(resolved) != 64 or any(character not in "0123456789abcdef" for character in resolved):
        raise ValueError(f"{name} must be a 64-character hexadecimal fingerprint")
    return resolved


def _freeze_authority_metadata(values: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(values, Mapping):
        raise TypeError("metadata must be a mapping")
    resolved = {str(key): value for key, value in values.items()}
    if resolved != _AUTHORITY_METADATA:
        raise ValueError("metadata does not match the graph experiment authority contract")
    return MappingProxyType(dict(resolved))


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, (np.integer, np.floating, np.bool_)):
        return value.item()
    return value


def _fingerprint_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            _json_ready(value),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
