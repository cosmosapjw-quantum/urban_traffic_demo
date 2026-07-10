"""NumPy-only cost-to-go feature and leakage-safe dataset contracts.

The feature surface is experiment substrate. Baseline dynamic-potential routing
continues to own labels, route legality, and runtime fallback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
from types import MappingProxyType
from typing import Any, Mapping, Sequence

import numpy as np

from metroflow.city.graph import RoadNetworkCSR
from metroflow.flow.state import LinkState

__all__ = [
    "COST_TO_GO_FEATURE_CONTRACT_FINGERPRINT",
    "COST_TO_GO_FEATURE_NAMES",
    "COST_TO_GO_FEATURE_SCHEMA_VERSION",
    "CostToGoDatasetSplit",
    "CostToGoFeatureDataset",
    "build_cost_to_go_feature_dataset",
    "split_cost_to_go_feature_dataset",
]

COST_TO_GO_FEATURE_SCHEMA_VERSION = 1
COST_TO_GO_FEATURE_NAMES = (
    "relative_x_by_spatial_diagonal",
    "relative_y_by_spatial_diagonal",
    "euclidean_distance_by_spatial_diagonal",
    "node_in_degree_by_max",
    "node_out_degree_by_max",
    "destination_in_degree_by_max",
    "destination_out_degree_by_max",
    "usable_outgoing_travel_time_min_by_max",
    "usable_outgoing_travel_time_mean_by_max",
    "usable_incoming_travel_time_mean_by_max",
    "outgoing_effective_capacity_sum_by_max",
    "incoming_effective_capacity_sum_by_max",
    "outgoing_blocked_link_fraction",
    "incoming_blocked_link_fraction",
    "global_max_travel_time_by_one_tick",
    "global_mean_travel_time_by_max",
    "global_blocked_link_fraction",
    "has_usable_outgoing",
    "has_usable_incoming",
    "is_destination",
)
COST_TO_GO_FEATURE_UNITS = {
    name: "dimensionless" for name in COST_TO_GO_FEATURE_NAMES
}
COST_TO_GO_IDENTIFIER_FIELDS = (
    "node_id",
    "node_index",
    "destination_node_id",
    "destination_node_index",
)
_SIGNED_UNIT_FEATURES = {
    "relative_x_by_spatial_diagonal",
    "relative_y_by_spatial_diagonal",
}
_BINARY_FEATURES = {
    "has_usable_outgoing",
    "has_usable_incoming",
    "is_destination",
}
_FEATURE_ALGORITHM = "row_local_geometry_topology_dynamic_v1"
_SPLIT_ALGORITHM = "static_network_destination_group_v2"
COST_TO_GO_FEATURE_CONTRACT_FINGERPRINT = hashlib.sha256(
    json.dumps(
        {
            "algorithm": _FEATURE_ALGORITHM,
            "feature_names": COST_TO_GO_FEATURE_NAMES,
            "feature_units": COST_TO_GO_FEATURE_UNITS,
            "identifier_fields_excluded": COST_TO_GO_IDENTIFIER_FIELDS,
            "schema_version": COST_TO_GO_FEATURE_SCHEMA_VERSION,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()


@dataclass(frozen=True)
class CostToGoFeatureDataset:
    """Contiguous experiment matrix built from authoritative label records."""

    features: np.ndarray
    targets: np.ndarray
    feature_names: tuple[str, ...]
    record_fingerprints: tuple[str, ...]
    split_group_keys: tuple[str, ...]
    static_network_fingerprints: tuple[str, ...]
    dynamic_state_fingerprints: tuple[str, ...]
    feature_contract_fingerprint: str
    dataset_fingerprint: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        features = np.array(self.features, dtype=np.float32, order="C", copy=True)
        targets = np.array(self.targets, dtype=np.float32, order="C", copy=True)
        names = tuple(str(name) for name in self.feature_names)
        record_fingerprints = tuple(str(value) for value in self.record_fingerprints)
        split_group_keys = tuple(str(value) for value in self.split_group_keys)
        static_fingerprints = tuple(str(value) for value in self.static_network_fingerprints)
        dynamic_fingerprints = tuple(str(value) for value in self.dynamic_state_fingerprints)
        if features.ndim != 2:
            raise ValueError("features must be a 2-D matrix")
        if targets.ndim != 1:
            raise ValueError("targets must be a 1-D vector")
        row_count = int(features.shape[0])
        if int(features.shape[1]) != len(names):
            raise ValueError("feature_names must match the feature matrix width")
        if names != COST_TO_GO_FEATURE_NAMES:
            raise ValueError("feature_names must match the canonical cost-to-go schema")
        if len(targets) != row_count:
            raise ValueError("targets must match the feature matrix row count")
        if len(record_fingerprints) != row_count or len(split_group_keys) != row_count:
            raise ValueError("record fingerprints and split groups must match row count")
        if not np.isfinite(features).all() or not np.isfinite(targets).all():
            raise ValueError("cost-to-go dataset arrays must be finite")
        if not all(record_fingerprints) or not all(split_group_keys):
            raise ValueError("record fingerprints and split groups must be non-empty")
        if len(set(record_fingerprints)) != len(record_fingerprints):
            raise ValueError("record fingerprints must be unique")
        if (
            not static_fingerprints
            or not dynamic_fingerprints
            or not all(static_fingerprints)
            or not all(dynamic_fingerprints)
        ):
            raise ValueError("dataset provenance fingerprints must be non-empty")
        metadata = _freeze_mapping(self.metadata)
        contract_fingerprint = str(self.feature_contract_fingerprint)
        if contract_fingerprint != COST_TO_GO_FEATURE_CONTRACT_FINGERPRINT:
            raise ValueError("unexpected cost-to-go feature contract fingerprint")
        expected_metadata = {
            "label_authority": "baseline_dynamic_potential",
            "route_legality_authority": "baseline_routing",
            "runtime_authority": "baseline_fallback_only",
            "split_claim_scope": (
                "same-static-network unseen-destination holdout"
                if len(static_fingerprints) == 1
                else "multi-network corpus; v1 split unavailable until explicit map strategy"
            ),
        }
        if _json_ready(metadata) != expected_metadata:
            raise ValueError("dataset metadata does not match the experiment authority contract")
        expected_dataset_fingerprint = _fingerprint_json(
            {
                "dynamic_state_fingerprints": dynamic_fingerprints,
                "feature_contract_fingerprint": contract_fingerprint,
                "feature_matrix_digest": _array_digest(features),
                "metadata": _json_ready(metadata),
                "record_fingerprints": record_fingerprints,
                "split_group_keys": split_group_keys,
                "static_network_fingerprints": static_fingerprints,
                "target_vector_digest": _array_digest(targets),
            }
        )
        dataset_fingerprint = str(self.dataset_fingerprint).strip()
        if dataset_fingerprint and dataset_fingerprint != expected_dataset_fingerprint:
            raise ValueError("dataset_fingerprint does not match dataset contents")
        dataset_fingerprint = expected_dataset_fingerprint
        features.setflags(write=False)
        targets.setflags(write=False)
        object.__setattr__(self, "features", features)
        object.__setattr__(self, "targets", targets)
        object.__setattr__(self, "feature_names", names)
        object.__setattr__(self, "record_fingerprints", record_fingerprints)
        object.__setattr__(self, "split_group_keys", split_group_keys)
        object.__setattr__(self, "static_network_fingerprints", static_fingerprints)
        object.__setattr__(self, "dynamic_state_fingerprints", dynamic_fingerprints)
        object.__setattr__(self, "feature_contract_fingerprint", contract_fingerprint)
        object.__setattr__(self, "dataset_fingerprint", dataset_fingerprint)
        object.__setattr__(self, "metadata", metadata)


@dataclass(frozen=True)
class CostToGoDatasetSplit:
    """Deterministic group split that prevents destination-row leakage."""

    dataset_fingerprint: str
    dataset_row_count: int
    train_indices: np.ndarray
    validation_indices: np.ndarray
    row_group_keys: tuple[str, ...]
    train_group_keys: tuple[str, ...]
    validation_group_keys: tuple[str, ...]
    split_seed: int
    validation_group_fraction: float
    split_algorithm: str = _SPLIT_ALGORITHM
    split_fingerprint: str = ""

    def __post_init__(self) -> None:
        train = np.array(self.train_indices, dtype=np.int32, order="C", copy=True)
        validation = np.array(self.validation_indices, dtype=np.int32, order="C", copy=True)
        train_groups = tuple(str(value) for value in self.train_group_keys)
        validation_groups = tuple(str(value) for value in self.validation_group_keys)
        row_groups = tuple(str(value) for value in self.row_group_keys)
        if train.ndim != 1 or validation.ndim != 1:
            raise ValueError("split indices must be 1-D")
        if train.size < 1 or validation.size < 1:
            raise ValueError("train and validation partitions must be non-empty")
        row_count = int(self.dataset_row_count)
        if row_count < 2:
            raise ValueError("dataset_row_count must be >= 2")
        if bool(np.any(train < 0)) or bool(np.any(validation < 0)):
            raise ValueError("split indices must be non-negative")
        train_index_set = set(int(value) for value in train)
        validation_index_set = set(int(value) for value in validation)
        if len(train_index_set) != int(train.size) or len(validation_index_set) != int(
            validation.size
        ):
            raise ValueError("split indices must be unique within each partition")
        if train_index_set & validation_index_set:
            raise ValueError("train and validation indices must not overlap")
        if train_index_set | validation_index_set != set(range(row_count)):
            raise ValueError("split indices must cover every dataset row exactly once")
        if len(row_groups) != row_count or not all(row_groups):
            raise ValueError("row_group_keys must provide one non-empty key per dataset row")
        if set(train_groups) & set(validation_groups):
            raise ValueError("train and validation split groups must not overlap")
        if not train_groups or not validation_groups or not all(train_groups + validation_groups):
            raise ValueError("train and validation split groups must be non-empty")
        if {row_groups[index] for index in train_index_set} != set(train_groups):
            raise ValueError("train group keys must match the indexed dataset rows")
        if {row_groups[index] for index in validation_index_set} != set(validation_groups):
            raise ValueError("validation group keys must match the indexed dataset rows")
        fraction = float(self.validation_group_fraction)
        if not math.isfinite(fraction) or not 0.0 < fraction < 1.0:
            raise ValueError("validation_group_fraction must be finite and in (0, 1)")
        seed = int(self.split_seed)
        dataset_fingerprint = str(self.dataset_fingerprint).strip()
        if not dataset_fingerprint:
            raise ValueError("dataset_fingerprint must be non-empty")
        split_algorithm = str(self.split_algorithm)
        if split_algorithm != _SPLIT_ALGORITHM:
            raise ValueError("unexpected cost-to-go split algorithm")
        expected_split_fingerprint = _fingerprint_json(
            {
                "dataset_fingerprint": dataset_fingerprint,
                "row_group_keys": row_groups,
                "split_algorithm": split_algorithm,
                "split_seed": seed,
                "train_group_keys": train_groups,
                "train_indices": tuple(int(value) for value in train),
                "validation_group_fraction": fraction,
                "validation_group_keys": validation_groups,
                "validation_indices": tuple(int(value) for value in validation),
            }
        )
        split_fingerprint = str(self.split_fingerprint).strip()
        if split_fingerprint and split_fingerprint != expected_split_fingerprint:
            raise ValueError("split_fingerprint does not match split contents")
        split_fingerprint = expected_split_fingerprint
        train.setflags(write=False)
        validation.setflags(write=False)
        object.__setattr__(self, "dataset_fingerprint", dataset_fingerprint)
        object.__setattr__(self, "dataset_row_count", row_count)
        object.__setattr__(self, "train_indices", train)
        object.__setattr__(self, "validation_indices", validation)
        object.__setattr__(self, "row_group_keys", row_groups)
        object.__setattr__(self, "train_group_keys", train_groups)
        object.__setattr__(self, "validation_group_keys", validation_groups)
        object.__setattr__(self, "split_seed", seed)
        object.__setattr__(self, "validation_group_fraction", fraction)
        object.__setattr__(self, "split_algorithm", split_algorithm)
        object.__setattr__(self, "split_fingerprint", split_fingerprint)


@dataclass(frozen=True)
class _CostToGoFeatureContext:
    node_xy_m: np.ndarray
    node_in_degree: np.ndarray
    node_out_degree: np.ndarray
    usable_outgoing_cost_min: np.ndarray
    usable_outgoing_cost_mean: np.ndarray
    usable_incoming_cost_mean: np.ndarray
    outgoing_effective_capacity_sum: np.ndarray
    incoming_effective_capacity_sum: np.ndarray
    outgoing_blocked_fraction: np.ndarray
    incoming_blocked_fraction: np.ndarray
    has_usable_outgoing: np.ndarray
    has_usable_incoming: np.ndarray
    spatial_diagonal_m: float
    maximum_degree: float
    maximum_travel_time_cost: float
    maximum_node_effective_capacity: float
    global_mean_travel_time_by_max: float
    global_blocked_link_fraction: float
    static_network_fingerprint: str
    dynamic_state_fingerprint: str

    def model_inputs(self, *, node_index: int, destination_node_index: int) -> dict[str, float]:
        node_index = int(node_index)
        destination_node_index = int(destination_node_index)
        node_count = int(self.node_xy_m.shape[0])
        if not 0 <= node_index < node_count or not 0 <= destination_node_index < node_count:
            raise ValueError("node and destination indices must be in range")
        delta = self.node_xy_m[node_index] - self.node_xy_m[destination_node_index]
        distance = float(np.hypot(delta[0], delta[1]))
        values = (
            float(delta[0] / self.spatial_diagonal_m),
            float(delta[1] / self.spatial_diagonal_m),
            float(distance / self.spatial_diagonal_m),
            float(self.node_in_degree[node_index] / self.maximum_degree),
            float(self.node_out_degree[node_index] / self.maximum_degree),
            float(self.node_in_degree[destination_node_index] / self.maximum_degree),
            float(self.node_out_degree[destination_node_index] / self.maximum_degree),
            float(self.usable_outgoing_cost_min[node_index] / self.maximum_travel_time_cost),
            float(self.usable_outgoing_cost_mean[node_index] / self.maximum_travel_time_cost),
            float(self.usable_incoming_cost_mean[node_index] / self.maximum_travel_time_cost),
            float(
                self.outgoing_effective_capacity_sum[node_index]
                / self.maximum_node_effective_capacity
            ),
            float(
                self.incoming_effective_capacity_sum[node_index]
                / self.maximum_node_effective_capacity
            ),
            float(self.outgoing_blocked_fraction[node_index]),
            float(self.incoming_blocked_fraction[node_index]),
            float(self.maximum_travel_time_cost),
            float(self.global_mean_travel_time_by_max),
            float(self.global_blocked_link_fraction),
            float(self.has_usable_outgoing[node_index]),
            float(self.has_usable_incoming[node_index]),
            float(node_index == destination_node_index),
        )
        if not np.isfinite(np.asarray(values, dtype=np.float64)).all():
            raise ValueError("cost-to-go model inputs must be finite")
        return dict(zip(COST_TO_GO_FEATURE_NAMES, values, strict=True))

    def record_metadata(
        self,
        *,
        node_index: int,
        destination_node_index: int,
        destination_node_id: int,
    ) -> dict[str, Any]:
        delta = self.node_xy_m[int(node_index)] - self.node_xy_m[
            int(destination_node_index)
        ]
        split_group_key = _cost_to_go_split_group_key(
            static_network_fingerprint=self.static_network_fingerprint,
            destination_node_id=int(destination_node_id),
        )
        return {
            "cost_to_go_feature_contract": {
                "algorithm": _FEATURE_ALGORITHM,
                "contract_fingerprint": COST_TO_GO_FEATURE_CONTRACT_FINGERPRINT,
                "feature_names": COST_TO_GO_FEATURE_NAMES,
                "feature_units": COST_TO_GO_FEATURE_UNITS,
                "identifier_fields_excluded": COST_TO_GO_IDENTIFIER_FIELDS,
                "normalization_scope": (
                    "per_network_and_dynamic_state_input; no dataset-fit statistics"
                ),
                "normalization": {
                    "spatial_diagonal_m": float(self.spatial_diagonal_m),
                    "maximum_degree_count": float(self.maximum_degree),
                    "one_tick_cost_reference_ticks": 1.0,
                    "maximum_travel_time_cost_ticks": float(
                        self.maximum_travel_time_cost
                    ),
                    "maximum_node_effective_capacity_veh_per_tick": float(
                        self.maximum_node_effective_capacity
                    ),
                },
                "schema_version": COST_TO_GO_FEATURE_SCHEMA_VERSION,
            },
            "dynamic_state_fingerprint": self.dynamic_state_fingerprint,
            "cost_to_go_diagnostics": {
                "node_destination_euclidean_distance_m": float(
                    np.hypot(delta[0], delta[1])
                ),
            },
            "split_group_algorithm": _SPLIT_ALGORITHM,
            "split_group_key": split_group_key,
            "split_claim_scope": (
                "same-static-network unseen-destination holdout; destination rows "
                "remain grouped across scenarios, ticks, and dynamic states"
            ),
            "static_network_fingerprint": self.static_network_fingerprint,
        }


def _build_cost_to_go_feature_context(
    road_csr: RoadNetworkCSR,
    link_state: LinkState,
) -> _CostToGoFeatureContext:
    if link_state.link_count != road_csr.link_count:
        raise ValueError("link_state.link_count must match road_csr.link_count")
    node_xy = np.ascontiguousarray(
        [(float(node.x), float(node.y)) for node in road_csr.nodes],
        dtype=np.float64,
    ).reshape((road_csr.node_count, 2))
    if not np.isfinite(node_xy).all():
        raise ValueError("road network node coordinates must be finite")
    travel_time = np.ascontiguousarray(link_state.travel_time_cost, dtype=np.float32)
    capacity = np.ascontiguousarray(link_state.capacity_veh_per_tick, dtype=np.float32)
    incident = np.ascontiguousarray(link_state.incident_capacity_multiplier, dtype=np.float32)
    if not np.isfinite(travel_time).all() or bool(np.any(travel_time <= 0.0)):
        raise ValueError("travel_time_cost must be finite and > 0")
    if not np.isfinite(capacity).all() or bool(np.any(capacity < 0.0)):
        raise ValueError("capacity_veh_per_tick must be finite and >= 0")
    if not np.isfinite(incident).all() or bool(np.any((incident < 0.0) | (incident > 1.0))):
        raise ValueError("incident_capacity_multiplier must be finite and in [0, 1]")

    static_blockable = np.asarray(
        [bool(link.is_blockable) for link in road_csr.links],
        dtype=np.bool_,
    )
    effective_capacity = np.asarray(capacity * incident, dtype=np.float32)
    blocked = np.asarray((effective_capacity <= 0.0) & static_blockable, dtype=np.bool_)
    in_degree = np.diff(np.asarray(road_csr.incoming_indptr, dtype=np.int32)).astype(
        np.float32
    )
    out_degree = np.diff(np.asarray(road_csr.outgoing_indptr, dtype=np.int32)).astype(
        np.float32
    )
    maximum_degree = max(float(np.max(in_degree, initial=0.0)), float(np.max(out_degree, initial=0.0)), 1.0)
    maximum_travel_time = max(float(np.max(travel_time, initial=np.float32(0.0))), 1.0e-6)

    node_count = road_csr.node_count
    outgoing_cost_min = np.zeros((node_count,), dtype=np.float32)
    outgoing_cost_mean = np.zeros((node_count,), dtype=np.float32)
    incoming_cost_mean = np.zeros((node_count,), dtype=np.float32)
    outgoing_capacity_sum = np.zeros((node_count,), dtype=np.float32)
    incoming_capacity_sum = np.zeros((node_count,), dtype=np.float32)
    outgoing_blocked_fraction = np.zeros((node_count,), dtype=np.float32)
    incoming_blocked_fraction = np.zeros((node_count,), dtype=np.float32)
    has_usable_outgoing = np.zeros((node_count,), dtype=np.float32)
    has_usable_incoming = np.zeros((node_count,), dtype=np.float32)
    for node_index in range(node_count):
        outgoing = _csr_slice(
            road_csr.outgoing_indptr,
            road_csr.outgoing_link_indices,
            node_index,
        )
        incoming = _csr_slice(
            road_csr.incoming_indptr,
            road_csr.incoming_link_indices,
            node_index,
        )
        outgoing_capacity_sum[node_index] = float(np.sum(effective_capacity[outgoing]))
        incoming_capacity_sum[node_index] = float(np.sum(effective_capacity[incoming]))
        outgoing_blocked_fraction[node_index] = _blocked_fraction(blocked[outgoing])
        incoming_blocked_fraction[node_index] = _blocked_fraction(blocked[incoming])
        usable_outgoing = outgoing[np.logical_not(blocked[outgoing])]
        usable_incoming = incoming[np.logical_not(blocked[incoming])]
        if usable_outgoing.size:
            usable_costs = travel_time[usable_outgoing]
            outgoing_cost_min[node_index] = float(np.min(usable_costs))
            outgoing_cost_mean[node_index] = float(np.mean(usable_costs, dtype=np.float64))
            has_usable_outgoing[node_index] = 1.0
        if usable_incoming.size:
            incoming_cost_mean[node_index] = float(
                np.mean(travel_time[usable_incoming], dtype=np.float64)
            )
            has_usable_incoming[node_index] = 1.0

    if node_count:
        extent = np.max(node_xy, axis=0) - np.min(node_xy, axis=0)
        spatial_diagonal = max(float(np.hypot(extent[0], extent[1])), 1.0)
    else:
        spatial_diagonal = 1.0
    maximum_node_capacity = max(
        float(np.max(outgoing_capacity_sum, initial=np.float32(0.0))),
        float(np.max(incoming_capacity_sum, initial=np.float32(0.0))),
        1.0e-6,
    )
    global_mean_travel = (
        float(np.mean(travel_time, dtype=np.float64) / maximum_travel_time)
        if travel_time.size
        else 0.0
    )
    global_blocked_fraction = float(np.mean(blocked, dtype=np.float64)) if blocked.size else 0.0
    return _CostToGoFeatureContext(
        node_xy_m=node_xy,
        node_in_degree=in_degree,
        node_out_degree=out_degree,
        usable_outgoing_cost_min=outgoing_cost_min,
        usable_outgoing_cost_mean=outgoing_cost_mean,
        usable_incoming_cost_mean=incoming_cost_mean,
        outgoing_effective_capacity_sum=outgoing_capacity_sum,
        incoming_effective_capacity_sum=incoming_capacity_sum,
        outgoing_blocked_fraction=outgoing_blocked_fraction,
        incoming_blocked_fraction=incoming_blocked_fraction,
        has_usable_outgoing=has_usable_outgoing,
        has_usable_incoming=has_usable_incoming,
        spatial_diagonal_m=spatial_diagonal,
        maximum_degree=maximum_degree,
        maximum_travel_time_cost=maximum_travel_time,
        maximum_node_effective_capacity=maximum_node_capacity,
        global_mean_travel_time_by_max=global_mean_travel,
        global_blocked_link_fraction=global_blocked_fraction,
        static_network_fingerprint=_static_network_fingerprint(road_csr),
        dynamic_state_fingerprint=_dynamic_state_fingerprint(link_state),
    )


def build_cost_to_go_feature_dataset(
    records: Sequence[Any],
) -> CostToGoFeatureDataset:
    """Build a deterministic matrix; malformed or non-authoritative rows fail closed."""

    from metroflow.learning.labels import SimulatorLabelRecord

    raw_records = tuple(records)
    if not raw_records:
        raise ValueError("records must contain at least one cost_to_go label")
    if not all(isinstance(record, SimulatorLabelRecord) for record in raw_records):
        raise ValueError("records must contain only SimulatorLabelRecord values")
    ordered = tuple(sorted(raw_records, key=_record_sort_key))
    rows: list[list[float]] = []
    targets: list[float] = []
    record_fingerprints: list[str] = []
    split_group_keys: list[str] = []
    static_fingerprints: set[str] = set()
    dynamic_fingerprints: set[str] = set()
    provenance_keys: set[tuple[Any, ...]] = set()
    for record in ordered:
        if record.label_kind != "cost_to_go":
            raise ValueError("all records must be cost_to_go labels")
        if record.source_authority != "baseline_dynamic_potential" or record.routing_backend != "baseline":
            raise ValueError("cost-to-go dataset requires baseline dynamic-potential authority")
        model_inputs = record.features.get("model_inputs")
        if not isinstance(model_inputs, Mapping):
            raise ValueError("cost-to-go record features must contain model_inputs")
        contract = record.metadata.get("cost_to_go_feature_contract")
        if not isinstance(contract, Mapping):
            raise ValueError("cost-to-go record metadata must contain feature contract")
        if int(contract.get("schema_version", -1)) != COST_TO_GO_FEATURE_SCHEMA_VERSION:
            raise ValueError("unexpected cost-to-go feature schema version")
        if tuple(contract.get("feature_names", ())) != COST_TO_GO_FEATURE_NAMES:
            raise ValueError("unexpected cost-to-go feature names")
        if str(contract.get("algorithm", "")) != _FEATURE_ALGORITHM:
            raise ValueError("unexpected cost-to-go feature algorithm")
        if dict(contract.get("feature_units", {})) != COST_TO_GO_FEATURE_UNITS:
            raise ValueError("unexpected cost-to-go feature units")
        if tuple(contract.get("identifier_fields_excluded", ())) != COST_TO_GO_IDENTIFIER_FIELDS:
            raise ValueError("unexpected cost-to-go identifier exclusion contract")
        if str(contract.get("contract_fingerprint", "")) != COST_TO_GO_FEATURE_CONTRACT_FINGERPRINT:
            raise ValueError("unexpected cost-to-go feature contract fingerprint")
        if len(model_inputs) != len(COST_TO_GO_FEATURE_NAMES) or set(model_inputs) != set(
            COST_TO_GO_FEATURE_NAMES
        ):
            raise ValueError("model_inputs must contain exactly the canonical feature names")
        try:
            row = [float(model_inputs[name]) for name in COST_TO_GO_FEATURE_NAMES]
            target = float(record.labels["label_cost_to_go"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("cost-to-go model inputs and label must be numeric and complete") from exc
        if not np.isfinite(np.asarray(row, dtype=np.float64)).all() or not math.isfinite(target):
            raise ValueError("cost-to-go model inputs and labels must be finite")
        _validate_cost_to_go_feature_domains(model_inputs, target=target)
        split_group_key = str(record.metadata.get("split_group_key", ""))
        static_fingerprint = str(record.metadata.get("static_network_fingerprint", ""))
        dynamic_fingerprint = str(record.metadata.get("dynamic_state_fingerprint", ""))
        if not split_group_key or not static_fingerprint or not dynamic_fingerprint:
            raise ValueError("cost-to-go record provenance fingerprints must be non-empty")
        if str(record.metadata.get("split_group_algorithm", "")) != _SPLIT_ALGORITHM:
            raise ValueError("unexpected cost-to-go split group algorithm")
        expected_split_group_key = _cost_to_go_split_group_key(
            static_network_fingerprint=static_fingerprint,
            destination_node_id=int(record.features.get("destination_node_id", -1)),
        )
        if split_group_key != expected_split_group_key:
            raise ValueError("cost-to-go split group key does not match input provenance")
        provenance_key = (
            static_fingerprint,
            str(record.scenario_id),
            int(record.tick_index),
            dynamic_fingerprint,
            int(record.features.get("destination_node_id", -1)),
            int(record.features.get("node_id", -1)),
        )
        if provenance_key in provenance_keys:
            raise ValueError("cost-to-go dataset contains duplicate row provenance")
        provenance_keys.add(provenance_key)
        rows.append(row)
        targets.append(target)
        record_fingerprints.append(str(record.fingerprint))
        split_group_keys.append(split_group_key)
        static_fingerprints.add(static_fingerprint)
        dynamic_fingerprints.add(dynamic_fingerprint)
    return CostToGoFeatureDataset(
        features=np.asarray(rows, dtype=np.float32),
        targets=np.asarray(targets, dtype=np.float32),
        feature_names=COST_TO_GO_FEATURE_NAMES,
        record_fingerprints=tuple(record_fingerprints),
        split_group_keys=tuple(split_group_keys),
        static_network_fingerprints=tuple(sorted(static_fingerprints)),
        dynamic_state_fingerprints=tuple(sorted(dynamic_fingerprints)),
        feature_contract_fingerprint=COST_TO_GO_FEATURE_CONTRACT_FINGERPRINT,
        metadata={
            "label_authority": "baseline_dynamic_potential",
            "route_legality_authority": "baseline_routing",
            "runtime_authority": "baseline_fallback_only",
            "split_claim_scope": (
                "same-static-network unseen-destination holdout"
                if len(static_fingerprints) == 1
                else "multi-network corpus; v1 split unavailable until explicit map strategy"
            ),
        },
    )


def split_cost_to_go_feature_dataset(
    dataset: CostToGoFeatureDataset,
    *,
    validation_group_fraction: float = 0.2,
    split_seed: int = 0,
) -> CostToGoDatasetSplit:
    """Split static-network/destination groups across scenarios and states."""

    fraction = float(validation_group_fraction)
    if not math.isfinite(fraction) or not 0.0 < fraction < 1.0:
        raise ValueError("validation_group_fraction must be finite and in (0, 1)")
    if len(dataset.static_network_fingerprints) != 1:
        raise ValueError("v1 cost-to-go split requires exactly one static network")
    groups = tuple(sorted(set(dataset.split_group_keys)))
    if len(groups) < 2:
        raise ValueError("at least two split groups are required")
    seed = int(split_seed)
    ranked_groups = tuple(
        sorted(
            groups,
            key=lambda group: (
                hashlib.sha256(f"{seed}:{group}".encode("utf-8")).hexdigest(),
                group,
            ),
        )
    )
    validation_count = min(
        max(1, int(math.ceil(len(ranked_groups) * fraction))),
        len(ranked_groups) - 1,
    )
    validation_groups = tuple(sorted(ranked_groups[:validation_count]))
    train_groups = tuple(sorted(ranked_groups[validation_count:]))
    validation_set = set(validation_groups)
    train_indices = np.asarray(
        [idx for idx, group in enumerate(dataset.split_group_keys) if group not in validation_set],
        dtype=np.int32,
    )
    validation_indices = np.asarray(
        [idx for idx, group in enumerate(dataset.split_group_keys) if group in validation_set],
        dtype=np.int32,
    )
    return CostToGoDatasetSplit(
        dataset_fingerprint=dataset.dataset_fingerprint,
        dataset_row_count=int(dataset.features.shape[0]),
        train_indices=train_indices,
        validation_indices=validation_indices,
        row_group_keys=dataset.split_group_keys,
        train_group_keys=train_groups,
        validation_group_keys=validation_groups,
        split_seed=seed,
        validation_group_fraction=fraction,
    )


def _csr_slice(indptr: np.ndarray, indices: np.ndarray, node_index: int) -> np.ndarray:
    pointer = np.asarray(indptr, dtype=np.int32)
    values = np.asarray(indices, dtype=np.int32)
    return values[int(pointer[node_index]) : int(pointer[node_index + 1])]


def _record_sort_key(record: Any) -> tuple[Any, ...]:
    """Order rows from input provenance, never from labels or their fingerprint."""

    features = record.features if isinstance(record.features, Mapping) else {}
    metadata = record.metadata if isinstance(record.metadata, Mapping) else {}
    return (
        str(metadata.get("static_network_fingerprint", "")),
        str(record.scenario_id),
        int(features.get("destination_node_id", -1)),
        int(record.tick_index),
        str(metadata.get("dynamic_state_fingerprint", "")),
        int(features.get("node_id", -1)),
    )


def _validate_cost_to_go_feature_domains(
    model_inputs: Mapping[str, Any],
    *,
    target: float,
) -> None:
    if target < 0.0:
        raise ValueError("label_cost_to_go must be >= 0")
    tolerance = 1.0e-6
    for name in COST_TO_GO_FEATURE_NAMES:
        value = float(model_inputs[name])
        if name == "global_max_travel_time_by_one_tick":
            if value <= 0.0:
                raise ValueError(f"{name} must be > 0")
            continue
        if name in _SIGNED_UNIT_FEATURES:
            if value < -1.0 - tolerance or value > 1.0 + tolerance:
                raise ValueError(f"{name} must be in [-1, 1]")
            continue
        if value < -tolerance or value > 1.0 + tolerance:
            raise ValueError(f"{name} must be in [0, 1]")
        if name in _BINARY_FEATURES and value not in {0.0, 1.0}:
            raise ValueError(f"{name} must be binary")


def _blocked_fraction(values: np.ndarray) -> float:
    return float(np.mean(values, dtype=np.float64)) if values.size else 0.0


def _array_digest(values: np.ndarray) -> str:
    array = np.ascontiguousarray(values)
    hasher = hashlib.sha256()
    hasher.update(str(array.dtype).encode("ascii"))
    hasher.update(str(tuple(array.shape)).encode("ascii"))
    hasher.update(array.tobytes())
    return hasher.hexdigest()


def _freeze_mapping(values: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(
        {str(key): _freeze_value(value) for key, value in dict(values).items()}
    )


def _freeze_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _freeze_mapping(value)
    if isinstance(value, (tuple, list)):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, np.generic):
        return value.item()
    return value


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(raw) for key, raw in sorted(value.items())}
    if isinstance(value, (tuple, list)):
        return [_json_ready(item) for item in value]
    return value


def _cost_to_go_split_group_key(
    *,
    static_network_fingerprint: str,
    destination_node_id: int,
) -> str:
    static_fingerprint = str(static_network_fingerprint)
    if not static_fingerprint:
        raise ValueError("static_network_fingerprint must be non-empty")
    return _fingerprint_json(
        {
            "algorithm": _SPLIT_ALGORITHM,
            "destination_node_id": int(destination_node_id),
            "static_network_fingerprint": static_fingerprint,
        }
    )


def _static_network_fingerprint(network: RoadNetworkCSR) -> str:
    return _fingerprint_json(
        {
            "nodes": tuple(
                (int(node.node_id), str(node.kind.value), float(node.x), float(node.y))
                for node in network.nodes
            ),
            "links": tuple(
                (
                    int(link.link_id),
                    int(link.src_node_id),
                    int(link.dst_node_id),
                    str(link.road_class.value),
                    float(link.length_m),
                    float(link.free_flow_speed_mps),
                    float(link.capacity_veh_per_tick),
                    int(link.lanes),
                    bool(link.is_blockable),
                )
                for link in network.links
            ),
        }
    )


def _dynamic_state_fingerprint(link_state: LinkState) -> str:
    hasher = hashlib.sha256()
    for name, values, dtype in (
        ("travel_time_cost", link_state.travel_time_cost, np.float32),
        ("capacity_veh_per_tick", link_state.capacity_veh_per_tick, np.float32),
        (
            "incident_capacity_multiplier",
            link_state.incident_capacity_multiplier,
            np.float32,
        ),
    ):
        array = np.ascontiguousarray(values, dtype=dtype)
        hasher.update(name.encode("ascii"))
        hasher.update(str(tuple(array.shape)).encode("ascii"))
        hasher.update(array.tobytes())
    return hasher.hexdigest()


def _fingerprint_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
