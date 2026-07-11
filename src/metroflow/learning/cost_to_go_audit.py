"""Diagnostic multi-city audit for the cost-to-go feature contract."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from metroflow.city.generator_v2 import GeneratorV2
from metroflow.city.graph import RoadNetworkCSR
from metroflow.flow.state import LinkState
from metroflow.learning.cost_to_go_features import (
    COST_TO_GO_FEATURE_CONTRACT_FINGERPRINT,
    COST_TO_GO_FEATURE_NAMES,
    build_cost_to_go_feature_dataset,
    split_cost_to_go_feature_dataset,
)
from metroflow.learning.labels import export_cost_to_go_label_records

__all__ = [
    "CostToGoFeatureAuditConfig",
    "CostToGoFeatureAuditResult",
    "DynamicResponseAudit",
    "FeatureTargetRelationAudit",
    "audit_dynamic_response",
    "audit_feature_target_relation",
    "build_feature_audit_link_states",
    "evaluate_cost_to_go_feature_audit_gate",
    "run_cost_to_go_feature_audit",
    "select_spatial_destination_node_ids",
    "write_cost_to_go_feature_audit_bundle",
]

_DYNAMIC_STATE_NAMES = ("free_flow", "stressed_closure")
_DISTANCE_BINS = (0.0, 0.25, 0.5, 0.75, 1.000001)
_CANONICAL_DESTINATION_COUNT = 4
_CANONICAL_CLOSURE_FRACTION = 0.03
_CANONICAL_NEAR_CONSTANT_STD = 1.0e-6
_CANONICAL_MINIMUM_NONCONSTANT_SHARE = 0.70
_RELATION_QUANTIZATION_WIDTH = 0.05
_RELATION_MINIMUM_COVERAGE_SHARE = 0.05
_RELATION_MAXIMUM_CONFLICT_SHARE = 0.25
_RELATION_MAXIMUM_NORMALIZED_TARGET_RANGE = 0.10
_DYNAMIC_MINIMUM_TARGET_CHANGED_SHARE = 0.01
_MAP_HOLDOUT_SEED = 49
_THRESHOLD_PROVENANCE = "fixed_in_pr_before_canonical_run_not_prior_preregistered"


@dataclass(frozen=True)
class CostToGoFeatureAuditConfig:
    """Predeclared diagnostic workload and decision thresholds."""

    style_ids: tuple[str, ...] = ("grid_core", "polycentric_tod", "organic")
    seeds: tuple[int, ...] = (17, 29, 41)
    destination_count: int = 4
    topology_mode: str = "sidecar_local_fabric_planar"
    closure_fraction: float = 0.03
    near_constant_std_threshold: float = 1.0e-6
    minimum_nonconstant_feature_share: float = 0.70

    def __post_init__(self) -> None:
        styles = tuple(str(value).strip() for value in self.style_ids)
        seeds = tuple(int(value) for value in self.seeds)
        if len(styles) < 3:
            raise ValueError("feature audit requires at least three styles")
        if not all(styles) or len(set(styles)) != len(styles):
            raise ValueError("feature audit style_ids must be non-empty and unique")
        if len(seeds) < 3:
            raise ValueError("feature audit requires at least three seeds")
        if len(set(seeds)) != len(seeds):
            raise ValueError("feature audit seeds must be unique")
        destination_count = int(self.destination_count)
        if destination_count < _CANONICAL_DESTINATION_COUNT:
            raise ValueError("destination_count must be >= 4")
        topology_mode = str(self.topology_mode).strip()
        if not topology_mode:
            raise ValueError("topology_mode must be non-empty")
        closure_fraction = float(self.closure_fraction)
        if not math.isfinite(closure_fraction) or not 0.0 < closure_fraction <= 0.2:
            raise ValueError("closure_fraction must be finite and in (0, 0.2]")
        threshold = float(self.near_constant_std_threshold)
        if not math.isfinite(threshold) or threshold <= 0.0:
            raise ValueError("near_constant_std_threshold must be finite and > 0")
        share = float(self.minimum_nonconstant_feature_share)
        if not math.isfinite(share) or not 0.0 < share <= 1.0:
            raise ValueError(
                "minimum_nonconstant_feature_share must be finite and in (0, 1]"
            )
        object.__setattr__(self, "style_ids", styles)
        object.__setattr__(self, "seeds", seeds)
        object.__setattr__(self, "destination_count", destination_count)
        object.__setattr__(self, "topology_mode", topology_mode)
        object.__setattr__(self, "closure_fraction", closure_fraction)
        object.__setattr__(self, "near_constant_std_threshold", threshold)
        object.__setattr__(self, "minimum_nonconstant_feature_share", share)

    @property
    def canonical_gate_profile(self) -> bool:
        return (
            self.destination_count == _CANONICAL_DESTINATION_COUNT
            and self.closure_fraction == _CANONICAL_CLOSURE_FRACTION
            and self.near_constant_std_threshold == _CANONICAL_NEAR_CONSTANT_STD
            and self.minimum_nonconstant_feature_share
            == _CANONICAL_MINIMUM_NONCONSTANT_SHARE
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "style_ids": list(self.style_ids),
            "seeds": list(self.seeds),
            "destination_count": self.destination_count,
            "topology_mode": self.topology_mode,
            "closure_fraction": self.closure_fraction,
            "near_constant_std_threshold": self.near_constant_std_threshold,
            "minimum_nonconstant_feature_share": self.minimum_nonconstant_feature_share,
            "canonical_gate_profile": self.canonical_gate_profile,
        }


@dataclass(frozen=True)
class FeatureTargetRelationAudit:
    quantization_width: float
    comparison_group_count: int
    covered_row_count: int
    coverage_share: float
    conflicting_row_count: int
    conflict_share: float
    passed: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "quantization_width": self.quantization_width,
            "comparison_group_count": self.comparison_group_count,
            "covered_row_count": self.covered_row_count,
            "coverage_share": self.coverage_share,
            "conflicting_row_count": self.conflicting_row_count,
            "conflict_share": self.conflict_share,
            "minimum_coverage_share": _RELATION_MINIMUM_COVERAGE_SHARE,
            "maximum_conflict_share": _RELATION_MAXIMUM_CONFLICT_SHARE,
            "maximum_normalized_target_range": (
                _RELATION_MAXIMUM_NORMALIZED_TARGET_RANGE
            ),
            "target_normalization": (
                "label_cost_to_go / global_max_travel_time_by_one_tick"
            ),
            "passed": self.passed,
        }


@dataclass(frozen=True)
class DynamicResponseAudit:
    expected_row_count: int
    matched_row_count: int
    feature_changed_count: int
    target_changed_count: int
    joint_changed_count: int
    feature_changed_share: float
    target_changed_share: float
    joint_changed_share: float
    row_identity_aligned: bool


@dataclass(frozen=True)
class MapHoldoutAudit:
    split_seed: int
    held_out_seed: int
    train_static_network_fingerprints: tuple[str, ...]
    validation_static_network_fingerprints: tuple[str, ...]
    train_style_ids: tuple[str, ...]
    validation_style_ids: tuple[str, ...]
    split_fingerprint: str
    feasible: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "split_unit": "scenario_seed_across_all_styles",
            "split_seed": self.split_seed,
            "held_out_seed": self.held_out_seed,
            "train_static_network_fingerprints": list(
                self.train_static_network_fingerprints
            ),
            "validation_static_network_fingerprints": list(
                self.validation_static_network_fingerprints
            ),
            "train_style_ids": list(self.train_style_ids),
            "validation_style_ids": list(self.validation_style_ids),
            "split_fingerprint": self.split_fingerprint,
            "feasible": self.feasible,
        }


@dataclass(frozen=True)
class FeatureColumnAudit:
    feature_name: str
    minimum: float
    maximum: float
    mean: float
    standard_deviation: float
    nonzero_share: float
    near_constant: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "feature_name": self.feature_name,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "mean": self.mean,
            "standard_deviation": self.standard_deviation,
            "nonzero_share": self.nonzero_share,
            "near_constant": self.near_constant,
        }


@dataclass(frozen=True)
class DistanceBinAudit:
    lower_inclusive: float
    upper_exclusive: float
    row_count: int
    target_mean: float | None
    target_standard_deviation: float | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "lower_inclusive": self.lower_inclusive,
            "upper_exclusive": self.upper_exclusive,
            "row_count": self.row_count,
            "target_mean": self.target_mean,
            "target_standard_deviation": self.target_standard_deviation,
        }


@dataclass(frozen=True)
class CostToGoFeatureAuditRun:
    style_id: str
    seed: int
    node_count: int
    link_count: int
    destination_node_ids: tuple[int, ...]
    static_network_fingerprint: str
    dynamic_state_fingerprints: tuple[str, ...]
    state_record_counts: Mapping[str, int]
    expected_record_count_per_state: int
    all_state_rows_retained: bool
    closure_eligible_link_count: int
    closure_requested_link_count: int
    closure_link_count: int
    closure_link_share: float
    dataset_fingerprint: str
    split_fingerprint: str
    destination_group_count: int
    per_map_split_feasible: bool
    dynamic_feature_changed_share: float
    dynamic_target_changed_share: float
    dynamic_joint_changed_share: float
    dynamic_matched_row_count: int
    dynamic_feature_changed_count: int
    dynamic_target_changed_count: int
    dynamic_joint_changed_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "style_id": self.style_id,
            "seed": self.seed,
            "node_count": self.node_count,
            "link_count": self.link_count,
            "destination_node_ids": list(self.destination_node_ids),
            "static_network_fingerprint": self.static_network_fingerprint,
            "dynamic_state_fingerprints": list(self.dynamic_state_fingerprints),
            "state_record_counts": dict(self.state_record_counts),
            "expected_record_count_per_state": self.expected_record_count_per_state,
            "all_state_rows_retained": self.all_state_rows_retained,
            "closure_eligible_link_count": self.closure_eligible_link_count,
            "closure_requested_link_count": self.closure_requested_link_count,
            "closure_link_count": self.closure_link_count,
            "closure_link_share": self.closure_link_share,
            "dataset_fingerprint": self.dataset_fingerprint,
            "split_fingerprint": self.split_fingerprint,
            "destination_group_count": self.destination_group_count,
            "per_map_split_feasible": self.per_map_split_feasible,
            "dynamic_feature_changed_share": self.dynamic_feature_changed_share,
            "dynamic_target_changed_share": self.dynamic_target_changed_share,
            "dynamic_joint_changed_share": self.dynamic_joint_changed_share,
            "dynamic_matched_row_count": self.dynamic_matched_row_count,
            "dynamic_feature_changed_count": self.dynamic_feature_changed_count,
            "dynamic_target_changed_count": self.dynamic_target_changed_count,
            "dynamic_joint_changed_count": self.dynamic_joint_changed_count,
        }


@dataclass(frozen=True)
class CostToGoFeatureAuditResult:
    config: CostToGoFeatureAuditConfig
    runs: tuple[CostToGoFeatureAuditRun, ...]
    feature_columns: tuple[FeatureColumnAudit, ...]
    distance_bins: tuple[DistanceBinAudit, ...]
    feature_target_relation: FeatureTargetRelationAudit
    map_holdout: MapHoldoutAudit
    row_count: int
    map_count: int
    dynamic_state_count: int
    destination_group_count: int
    target_minimum: float
    target_maximum: float
    target_standard_deviation: float
    raw_distance_minimum_m: float
    raw_distance_maximum_m: float
    nonconstant_feature_share: float
    all_maps_have_closure_support: bool
    all_state_rows_retained: bool
    all_maps_have_v1_split: bool
    cross_map_holdout_feasible: bool
    row_local_mlp_probe_authorized: bool
    dynamic_feature_changed_share: float
    dynamic_target_changed_share: float
    dynamic_joint_changed_share: float
    dynamic_matched_row_count: int
    dynamic_feature_changed_count: int
    dynamic_target_changed_count: int
    dynamic_joint_changed_count: int
    corpus_fingerprint: str
    runtime_nn_backend_authorized: bool = False
    route_legality_changed: bool = False
    raw_label_rows_persisted: bool = False

    def __post_init__(self) -> None:
        forbidden_authority = {
            "runtime_nn_backend_authorized": self.runtime_nn_backend_authorized,
            "route_legality_changed": self.route_legality_changed,
            "raw_label_rows_persisted": self.raw_label_rows_persisted,
        }
        for name, value in forbidden_authority.items():
            if type(value) is not bool or value:
                raise ValueError(f"{name} must remain False for a diagnostic audit")
        if type(self.row_local_mlp_probe_authorized) is not bool:
            raise ValueError("row_local_mlp_probe_authorized must be a bool")
        expected_authorization = evaluate_cost_to_go_feature_audit_gate(
            config=self.config,
            nonconstant_feature_share=self.nonconstant_feature_share,
            target_standard_deviation=self.target_standard_deviation,
            all_maps_have_closure_support=self.all_maps_have_closure_support,
            all_state_rows_retained=self.all_state_rows_retained,
            all_maps_have_v1_split=self.all_maps_have_v1_split,
            map_holdout_feasible=self.cross_map_holdout_feasible,
            feature_target_relation_passed=self.feature_target_relation.passed,
            dynamic_feature_changed_share=self.dynamic_feature_changed_share,
            dynamic_target_changed_share=self.dynamic_target_changed_share,
            dynamic_joint_changed_share=self.dynamic_joint_changed_share,
        )
        if self.row_local_mlp_probe_authorized != expected_authorization:
            raise ValueError(
                "row_local_mlp_probe_authorized must match the canonical audit gate"
            )

    @property
    def decision_state(self) -> str:
        if self.row_local_mlp_probe_authorized:
            return "admissible"
        non_relation_evidence_complete = bool(
            self.config.canonical_gate_profile
            and self.nonconstant_feature_share
            >= self.config.minimum_nonconstant_feature_share
            and self.target_standard_deviation
            > self.config.near_constant_std_threshold
            and self.all_maps_have_closure_support
            and self.all_state_rows_retained
            and self.all_maps_have_v1_split
            and self.cross_map_holdout_feasible
            and self.dynamic_feature_changed_share
            >= _DYNAMIC_MINIMUM_TARGET_CHANGED_SHARE
            and self.dynamic_target_changed_share
            >= _DYNAMIC_MINIMUM_TARGET_CHANGED_SHARE
            and self.dynamic_joint_changed_share
            >= _DYNAMIC_MINIMUM_TARGET_CHANGED_SHARE
        )
        relation_rejected = bool(
            self.feature_target_relation.coverage_share
            >= _RELATION_MINIMUM_COVERAGE_SHARE
            and self.feature_target_relation.conflict_share
            > _RELATION_MAXIMUM_CONFLICT_SHARE
        )
        if non_relation_evidence_complete and relation_rejected:
            return "relation_rejected"
        return "inconclusive"

    @property
    def adjacency_required_before_mlp(self) -> bool:
        return self.decision_state == "relation_rejected"

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifact_format_version": "cost_to_go_feature_audit_v1",
            "evidence_status": "diagnostic_not_validation",
            "threshold_provenance": _THRESHOLD_PROVENANCE,
            "config": self.config.as_dict(),
            "feature_contract_fingerprint": COST_TO_GO_FEATURE_CONTRACT_FINGERPRINT,
            "feature_names": list(COST_TO_GO_FEATURE_NAMES),
            "runs": [run.as_dict() for run in self.runs],
            "aggregate": {
                "row_count": self.row_count,
                "map_count": self.map_count,
                "dynamic_state_count": self.dynamic_state_count,
                "destination_group_count": self.destination_group_count,
                "target_minimum": self.target_minimum,
                "target_maximum": self.target_maximum,
                "target_standard_deviation": self.target_standard_deviation,
                "raw_distance_minimum_m": self.raw_distance_minimum_m,
                "raw_distance_maximum_m": self.raw_distance_maximum_m,
                "nonconstant_feature_share": self.nonconstant_feature_share,
                "all_maps_have_closure_support": self.all_maps_have_closure_support,
                "all_state_rows_retained": self.all_state_rows_retained,
                "all_maps_have_v1_split": self.all_maps_have_v1_split,
                "cross_map_holdout_feasible": self.cross_map_holdout_feasible,
                "dynamic_feature_changed_share": self.dynamic_feature_changed_share,
                "dynamic_target_changed_share": self.dynamic_target_changed_share,
                "dynamic_joint_changed_share": self.dynamic_joint_changed_share,
                "dynamic_matched_row_count": self.dynamic_matched_row_count,
                "dynamic_feature_changed_count": self.dynamic_feature_changed_count,
                "dynamic_target_changed_count": self.dynamic_target_changed_count,
                "dynamic_joint_changed_count": self.dynamic_joint_changed_count,
                "corpus_fingerprint": self.corpus_fingerprint,
            },
            "feature_columns": [column.as_dict() for column in self.feature_columns],
            "distance_bins": [item.as_dict() for item in self.distance_bins],
            "feature_target_relation": self.feature_target_relation.as_dict(),
            "map_holdout": self.map_holdout.as_dict(),
            "decision": {
                "decision_state": self.decision_state,
                "row_local_mlp_probe_authorized": self.row_local_mlp_probe_authorized,
                "adjacency_required_before_mlp": self.adjacency_required_before_mlp,
                "runtime_nn_backend_authorized": self.runtime_nn_backend_authorized,
                "route_legality_changed": self.route_legality_changed,
                "raw_label_rows_persisted": self.raw_label_rows_persisted,
                "next_pr": {
                    "admissible": "row_local_jax_probe_authorized",
                    "relation_rejected": "PR50_adjacency_edge_tensor_contract",
                    "inconclusive": "stop_and_repair_audit_evidence",
                }[self.decision_state],
            },
        }


def select_spatial_destination_node_ids(
    network: RoadNetworkCSR,
    *,
    destination_count: int,
) -> tuple[int, ...]:
    """Select dispersed destination nodes using geometry-only tie breaks."""

    count = int(destination_count)
    if count < _CANONICAL_DESTINATION_COUNT:
        raise ValueError("destination_count must be >= 4")
    if count > network.node_count:
        raise ValueError("destination_count must not exceed network.node_count")
    coordinates = np.asarray(
        [(float(node.x), float(node.y)) for node in network.nodes],
        dtype=np.float64,
    )
    if not np.isfinite(coordinates).all():
        raise ValueError("network node coordinates must be finite")
    minimum = np.min(coordinates, axis=0)
    maximum = np.max(coordinates, axis=0)
    center = (minimum + maximum) * 0.5
    anchors = (
        minimum,
        maximum,
        np.asarray((maximum[0], minimum[1])),
        np.asarray((minimum[0], maximum[1])),
        center,
    )
    selected_indices: list[int] = []
    for anchor in anchors:
        if len(selected_indices) >= count:
            break
        candidates = sorted(
            (
                (
                    float(np.sum((coordinates[index] - anchor) ** 2)),
                    float(coordinates[index, 0]),
                    float(coordinates[index, 1]),
                    index,
                )
                for index in range(network.node_count)
                if index not in selected_indices
            ),
            key=lambda item: (item[0], item[1], item[2], item[3]),
        )
        selected_indices.append(int(candidates[0][3]))
    while len(selected_indices) < count:
        candidates = []
        for index in range(network.node_count):
            if index in selected_indices:
                continue
            minimum_distance = min(
                float(np.sum((coordinates[index] - coordinates[selected]) ** 2))
                for selected in selected_indices
            )
            candidates.append(
                (
                    -minimum_distance,
                    float(coordinates[index, 0]),
                    float(coordinates[index, 1]),
                    index,
                )
            )
        candidates.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
        selected_indices.append(int(candidates[0][3]))
    return tuple(int(network.node_ids[index]) for index in selected_indices)


def build_feature_audit_link_states(
    network: RoadNetworkCSR,
    *,
    seed: int,
    closure_fraction: float,
) -> dict[str, LinkState]:
    """Build free-flow and deterministic stressed/closure label states."""

    fraction = float(closure_fraction)
    if not math.isfinite(fraction) or not 0.0 < fraction <= 0.2:
        raise ValueError("closure_fraction must be finite and in (0, 0.2]")
    travel = np.asarray(
        [
            max(1.0e-3, float(link.length_m) / max(1.0e-3, float(link.free_flow_speed_mps)))
            for link in network.links
        ],
        dtype=np.float32,
    )
    capacity = np.asarray(
        [max(0.0, float(link.capacity_veh_per_tick)) for link in network.links],
        dtype=np.float32,
    )
    incident_free = np.ones((network.link_count,), dtype=np.float32)
    free_flow = LinkState.from_internal_arrays(
        queue_vehicles=np.zeros((network.link_count,), dtype=np.float32),
        inflow_vehicles=np.zeros((network.link_count,), dtype=np.float32),
        outflow_vehicles=np.zeros((network.link_count,), dtype=np.float32),
        travel_time_cost=travel,
        capacity_veh_per_tick=capacity.copy(),
        incident_capacity_multiplier=incident_free,
        capacity_violation_flags=np.zeros((network.link_count,), dtype=np.bool_),
        metadata={"feature_audit_state": "free_flow"},
    )
    stress_factor = np.asarray(
        [
            1.25
            + 0.75
            * _stable_unit_interval(seed=int(seed), value=int(link.link_id))
            for link in network.links
        ],
        dtype=np.float32,
    )
    stressed_travel = np.asarray(travel * stress_factor, dtype=np.float32)
    candidates = [
        index
        for index, link in enumerate(network.links)
        if bool(link.is_blockable) and float(capacity[index]) > 0.0
    ]
    if not candidates:
        raise ValueError("feature audit requires at least one positive-capacity blockable link")
    candidates.sort(
        key=lambda index: (
            hashlib.sha256(f"{int(seed)}:{int(network.link_ids[index])}".encode()).hexdigest(),
            int(network.link_ids[index]),
        )
    )
    requested_closure_count = min(
        len(candidates),
        max(1, int(math.ceil(len(candidates) * fraction))),
    )
    selected_closures = _select_reachability_preserving_closures(
        network,
        ranked_candidates=tuple(candidates),
        requested_count=requested_closure_count,
        usable_link_mask=np.asarray(capacity > 0.0, dtype=np.bool_),
    )
    if len(selected_closures) != requested_closure_count:
        raise ValueError(
            "feature audit could not satisfy the reachability-preserving closure quota"
        )
    closure_count = len(selected_closures)
    incident_stressed = np.ones((network.link_count,), dtype=np.float32)
    incident_stressed[np.asarray(selected_closures, dtype=np.int32)] = 0.0
    stressed = LinkState.from_internal_arrays(
        queue_vehicles=np.zeros((network.link_count,), dtype=np.float32),
        inflow_vehicles=np.zeros((network.link_count,), dtype=np.float32),
        outflow_vehicles=np.zeros((network.link_count,), dtype=np.float32),
        travel_time_cost=stressed_travel,
        capacity_veh_per_tick=capacity.copy(),
        incident_capacity_multiplier=incident_stressed,
        capacity_violation_flags=np.zeros((network.link_count,), dtype=np.bool_),
        metadata={
            "feature_audit_state": "stressed_closure",
            "eligible_closure_link_count": len(candidates),
            "closure_link_count": closure_count,
            "requested_closure_link_count": requested_closure_count,
        },
    )
    return {"free_flow": free_flow, "stressed_closure": stressed}


def run_cost_to_go_feature_audit(
    config: CostToGoFeatureAuditConfig | None = None,
) -> CostToGoFeatureAuditResult:
    """Run the deterministic diagnostic matrix and return compact summaries."""

    cfg = config or CostToGoFeatureAuditConfig()
    run_summaries: list[CostToGoFeatureAuditRun] = []
    feature_chunks: list[np.ndarray] = []
    target_chunks: list[np.ndarray] = []
    distance_chunks: list[np.ndarray] = []
    map_key_chunks: list[np.ndarray] = []
    corpus_parts: list[str] = []
    for style_id in cfg.style_ids:
        for seed in cfg.seeds:
            network = _generate_audit_network(
                style_id=style_id,
                seed=seed,
                topology_mode=cfg.topology_mode,
            )
            destinations = select_spatial_destination_node_ids(
                network,
                destination_count=cfg.destination_count,
            )
            states = build_feature_audit_link_states(
                network,
                seed=seed,
                closure_fraction=cfg.closure_fraction,
            )
            records = []
            records_by_state: dict[str, tuple[Any, ...]] = {}
            state_record_counts: dict[str, int] = {}
            for state_index, state_name in enumerate(_DYNAMIC_STATE_NAMES):
                state_records = export_cost_to_go_label_records(
                    road_csr=network,
                    link_state=states[state_name],
                    destination_node_ids=destinations,
                    scenario_id=f"feature-audit:{style_id}:{seed}:{state_name}",
                    tick_index=state_index,
                )
                if not state_records:
                    raise ValueError("feature audit state produced no reachable labels")
                state_record_counts[state_name] = len(state_records)
                records_by_state[state_name] = state_records
                records.extend(state_records)
            dataset = build_cost_to_go_feature_dataset(tuple(records))
            split = split_cost_to_go_feature_dataset(
                dataset,
                validation_group_fraction=0.25,
                split_seed=seed,
            )
            distances = np.asarray(
                [
                    float(
                        record.metadata["cost_to_go_diagnostics"][
                            "node_destination_euclidean_distance_m"
                        ]
                    )
                    for record in records
                ],
                dtype=np.float64,
            )
            normalized_distances = np.asarray(
                [
                    float(
                        record.features["model_inputs"][
                            "euclidean_distance_by_spatial_diagonal"
                        ]
                    )
                    for record in records
                ],
                dtype=np.float64,
            )
            distance_chunks.append(np.column_stack((distances, normalized_distances)))
            direct_features = np.asarray(
                [
                    [
                        float(record.features["model_inputs"][name])
                        for name in COST_TO_GO_FEATURE_NAMES
                    ]
                    for record in records
                ],
                dtype=np.float32,
            )
            feature_chunks.append(direct_features)
            target_chunks.append(
                np.asarray(
                    [float(record.labels["label_cost_to_go"]) for record in records],
                    dtype=np.float32,
                )
            )
            stressed_incident = np.asarray(
                states["stressed_closure"].incident_capacity_multiplier,
                dtype=np.float32,
            )
            closure_count = int(np.count_nonzero(stressed_incident == 0.0))
            static_fingerprint = dataset.static_network_fingerprints[0]
            destination_group_count = len(set(dataset.split_group_keys))
            map_key_chunks.append(
                np.full((len(records),), static_fingerprint, dtype=object)
            )
            expected_record_count = network.node_count * len(destinations)
            expected_keys = frozenset(
                (int(destination), int(node_id))
                for destination in destinations
                for node_id in network.node_ids
            )
            dynamic_response = audit_dynamic_response(
                records_by_state["free_flow"],
                records_by_state["stressed_closure"],
                expected_record_count=expected_record_count,
                expected_keys=expected_keys,
            )
            all_rows_retained = bool(
                dynamic_response.row_identity_aligned
                and all(
                    state_record_counts[state_name] == expected_record_count
                    for state_name in _DYNAMIC_STATE_NAMES
                )
            )
            stress_metadata = states["stressed_closure"].metadata
            run_summary = CostToGoFeatureAuditRun(
                style_id=style_id,
                seed=seed,
                node_count=network.node_count,
                link_count=network.link_count,
                destination_node_ids=destinations,
                static_network_fingerprint=static_fingerprint,
                dynamic_state_fingerprints=dataset.dynamic_state_fingerprints,
                state_record_counts=state_record_counts,
                expected_record_count_per_state=expected_record_count,
                all_state_rows_retained=all_rows_retained,
                closure_eligible_link_count=int(
                    stress_metadata["eligible_closure_link_count"]
                ),
                closure_requested_link_count=int(
                    stress_metadata["requested_closure_link_count"]
                ),
                closure_link_count=closure_count,
                closure_link_share=(closure_count / max(network.link_count, 1)),
                dataset_fingerprint=dataset.dataset_fingerprint,
                split_fingerprint=split.split_fingerprint,
                destination_group_count=destination_group_count,
                per_map_split_feasible=(
                    destination_group_count >= _CANONICAL_DESTINATION_COUNT
                    and bool(split.train_group_keys)
                    and bool(split.validation_group_keys)
                ),
                dynamic_feature_changed_share=dynamic_response.feature_changed_share,
                dynamic_target_changed_share=dynamic_response.target_changed_share,
                dynamic_joint_changed_share=dynamic_response.joint_changed_share,
                dynamic_matched_row_count=dynamic_response.matched_row_count,
                dynamic_feature_changed_count=dynamic_response.feature_changed_count,
                dynamic_target_changed_count=dynamic_response.target_changed_count,
                dynamic_joint_changed_count=dynamic_response.joint_changed_count,
            )
            run_summaries.append(run_summary)
            corpus_parts.extend((dataset.dataset_fingerprint, split.split_fingerprint))
    return _summarize_audit(
        config=cfg,
        runs=tuple(run_summaries),
        feature_matrix=np.concatenate(feature_chunks, axis=0),
        targets=np.concatenate(target_chunks, axis=0),
        distances=np.concatenate(distance_chunks, axis=0),
        map_keys=np.concatenate(map_key_chunks, axis=0),
        corpus_parts=tuple(corpus_parts),
    )


def write_cost_to_go_feature_audit_bundle(
    result: CostToGoFeatureAuditResult,
    output_dir: str | Path,
) -> dict[str, Path]:
    """Write compact diagnostic JSON, Markdown, and manifest files."""

    target = Path(output_dir)
    if target.exists() and any(target.iterdir()):
        raise ValueError("feature audit output_dir must be empty")
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / "cost-to-go-feature-audit.json"
    markdown_path = target / "cost-to-go-feature-audit.md"
    manifest_path = target / "manifest.json"
    json_path.write_text(
        json.dumps(result.as_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(_render_markdown(result), encoding="utf-8")
    manifest = {
        "artifact_format_version": "cost_to_go_feature_audit_bundle_v1",
        "evidence_status": "diagnostic_not_validation",
        "threshold_provenance": _THRESHOLD_PROVENANCE,
        "data_json": json_path.name,
        "review_markdown": markdown_path.name,
        "artifact_files": [json_path.name, markdown_path.name],
        "corpus_fingerprint": result.corpus_fingerprint,
        "map_holdout_split_fingerprint": result.map_holdout.split_fingerprint,
        "feature_target_relation_passed": result.feature_target_relation.passed,
        "decision_state": result.decision_state,
        "adjacency_required_before_mlp": result.adjacency_required_before_mlp,
        "row_local_mlp_probe_authorized": result.row_local_mlp_probe_authorized,
        "runtime_nn_backend_authorized": result.runtime_nn_backend_authorized,
        "raw_label_rows_persisted": result.raw_label_rows_persisted,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"json": json_path, "markdown": markdown_path, "manifest": manifest_path}


def _generate_audit_network(
    *,
    style_id: str,
    seed: int,
    topology_mode: str,
) -> RoadNetworkCSR:
    topology = GeneratorV2().generate_preview_topology(
        {
            "scenario_id": "synthetic_smoke",
            "seed": int(seed),
            "preview_mode": str(topology_mode),
            "style_id": str(style_id),
        }
    )
    return topology.build_csr(validate=None, require_weak_connectivity=True)


def audit_feature_target_relation(
    feature_matrix: np.ndarray,
    targets: np.ndarray,
    map_keys: np.ndarray,
) -> FeatureTargetRelationAudit:
    """Measure target conflicts among quantized near-duplicate rows across maps."""

    features = np.asarray(feature_matrix, dtype=np.float64)
    target_values = np.asarray(targets, dtype=np.float64)
    keys = np.asarray(map_keys, dtype=object)
    if features.ndim != 2 or features.shape[1] != len(COST_TO_GO_FEATURE_NAMES):
        raise ValueError("relation feature matrix has unexpected shape")
    if target_values.shape != (features.shape[0],) or keys.shape != (
        features.shape[0],
    ):
        raise ValueError("relation targets and map keys must match feature rows")
    if not np.isfinite(features).all() or not np.isfinite(target_values).all():
        raise ValueError("relation audit values must be finite")
    minimum = np.min(features, axis=0)
    span = np.max(features, axis=0) - minimum
    safe_span = np.where(span > 1.0e-12, span, 1.0)
    scaled = (features - minimum) / safe_span
    quantized = np.rint(scaled / _RELATION_QUANTIZATION_WIDTH).astype(np.int16)
    scale_index = COST_TO_GO_FEATURE_NAMES.index(
        "global_max_travel_time_by_one_tick"
    )
    target_scales = features[:, scale_index]
    if np.any(target_scales <= 0.0):
        raise ValueError("relation target normalization scale must be > 0")
    normalized_targets = target_values / target_scales
    groups: dict[tuple[int, ...], list[int]] = {}
    for index, row in enumerate(quantized):
        groups.setdefault(tuple(int(value) for value in row), []).append(index)
    covered: set[int] = set()
    conflicting: set[int] = set()
    comparison_group_count = 0
    for indices in groups.values():
        if len(indices) < 2 or len({str(keys[index]) for index in indices}) < 2:
            continue
        comparison_group_count += 1
        covered.update(indices)
        selected_targets = normalized_targets[np.asarray(indices, dtype=np.int32)]
        if float(np.max(selected_targets) - np.min(selected_targets)) > (
            _RELATION_MAXIMUM_NORMALIZED_TARGET_RANGE
        ):
            conflicting.update(indices)
    coverage_share = len(covered) / max(features.shape[0], 1)
    conflict_share = len(conflicting) / max(len(covered), 1)
    return FeatureTargetRelationAudit(
        quantization_width=_RELATION_QUANTIZATION_WIDTH,
        comparison_group_count=comparison_group_count,
        covered_row_count=len(covered),
        coverage_share=float(coverage_share),
        conflicting_row_count=len(conflicting),
        conflict_share=float(conflict_share),
        passed=(
            coverage_share >= _RELATION_MINIMUM_COVERAGE_SHARE
            and conflict_share <= _RELATION_MAXIMUM_CONFLICT_SHARE
        ),
    )


def evaluate_cost_to_go_feature_audit_gate(
    *,
    config: CostToGoFeatureAuditConfig,
    nonconstant_feature_share: float,
    target_standard_deviation: float,
    all_maps_have_closure_support: bool,
    all_state_rows_retained: bool,
    all_maps_have_v1_split: bool,
    map_holdout_feasible: bool,
    feature_target_relation_passed: bool,
    dynamic_feature_changed_share: float,
    dynamic_target_changed_share: float,
    dynamic_joint_changed_share: float,
) -> bool:
    """Apply the fixed canonical PR50 admission gate."""

    if not isinstance(config, CostToGoFeatureAuditConfig):
        raise TypeError("config must be a CostToGoFeatureAuditConfig")
    boolean_values = {
        "all_maps_have_closure_support": all_maps_have_closure_support,
        "all_state_rows_retained": all_state_rows_retained,
        "all_maps_have_v1_split": all_maps_have_v1_split,
        "map_holdout_feasible": map_holdout_feasible,
        "feature_target_relation_passed": feature_target_relation_passed,
    }
    if any(type(value) is not bool for value in boolean_values.values()):
        raise ValueError("feature audit gate boolean inputs must be bool values")
    share_values = {
        "nonconstant_feature_share": nonconstant_feature_share,
        "dynamic_feature_changed_share": dynamic_feature_changed_share,
        "dynamic_target_changed_share": dynamic_target_changed_share,
        "dynamic_joint_changed_share": dynamic_joint_changed_share,
    }
    for name, raw_value in share_values.items():
        value = float(raw_value)
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} must be finite and in [0, 1]")
    target_std = float(target_standard_deviation)
    if not math.isfinite(target_std) or target_std < 0.0:
        raise ValueError("target_standard_deviation must be finite and >= 0")
    return bool(
        config.canonical_gate_profile
        and float(nonconstant_feature_share)
        >= config.minimum_nonconstant_feature_share
        and target_std > config.near_constant_std_threshold
        and all_maps_have_closure_support
        and all_state_rows_retained
        and all_maps_have_v1_split
        and map_holdout_feasible
        and feature_target_relation_passed
        and float(dynamic_feature_changed_share)
        >= _DYNAMIC_MINIMUM_TARGET_CHANGED_SHARE
        and float(dynamic_target_changed_share)
        >= _DYNAMIC_MINIMUM_TARGET_CHANGED_SHARE
        and float(dynamic_joint_changed_share)
        >= _DYNAMIC_MINIMUM_TARGET_CHANGED_SHARE
    )


def _build_map_holdout(
    config: CostToGoFeatureAuditConfig,
    runs: tuple[CostToGoFeatureAuditRun, ...],
) -> MapHoldoutAudit:
    expected_pairs = {
        (style_id, seed) for style_id in config.style_ids for seed in config.seeds
    }
    observed_pairs = [(run.style_id, run.seed) for run in runs]
    complete_matrix = bool(
        len(observed_pairs) == len(expected_pairs)
        and len(set(observed_pairs)) == len(observed_pairs)
        and set(observed_pairs) == expected_pairs
    )
    ranked_seeds = sorted(
        config.seeds,
        key=lambda seed: (
            hashlib.sha256(f"{_MAP_HOLDOUT_SEED}:{seed}".encode()).hexdigest(),
            seed,
        ),
    )
    held_out_seed = int(ranked_seeds[0])
    train_runs = tuple(run for run in runs if run.seed != held_out_seed)
    validation_runs = tuple(run for run in runs if run.seed == held_out_seed)
    train_fingerprints = tuple(
        sorted(run.static_network_fingerprint for run in train_runs)
    )
    validation_fingerprints = tuple(
        sorted(run.static_network_fingerprint for run in validation_runs)
    )
    train_styles = tuple(sorted({run.style_id for run in train_runs}))
    validation_styles = tuple(sorted({run.style_id for run in validation_runs}))
    feasible = bool(
        complete_matrix
        and train_fingerprints
        and validation_fingerprints
        and len(set(train_fingerprints + validation_fingerprints)) == len(runs)
        and not (set(train_fingerprints) & set(validation_fingerprints))
        and train_styles == tuple(sorted(config.style_ids))
        and validation_styles == tuple(sorted(config.style_ids))
    )
    fingerprint = _fingerprint_json(
        {
            "held_out_seed": held_out_seed,
            "split_seed": _MAP_HOLDOUT_SEED,
            "train_static_network_fingerprints": train_fingerprints,
            "validation_static_network_fingerprints": validation_fingerprints,
        }
    )
    return MapHoldoutAudit(
        split_seed=_MAP_HOLDOUT_SEED,
        held_out_seed=held_out_seed,
        train_static_network_fingerprints=train_fingerprints,
        validation_static_network_fingerprints=validation_fingerprints,
        train_style_ids=train_styles,
        validation_style_ids=validation_styles,
        split_fingerprint=fingerprint,
        feasible=feasible,
    )


def audit_dynamic_response(
    free_flow_records: tuple[Any, ...],
    stressed_records: tuple[Any, ...],
    *,
    expected_record_count: int,
    expected_keys: frozenset[tuple[int, int]],
) -> DynamicResponseAudit:
    def keyed(records: tuple[Any, ...]) -> dict[tuple[int, int], Any]:
        output: dict[tuple[int, int], Any] = {}
        for record in records:
            key = (
                int(record.features["destination_node_id"]),
                int(record.features["node_id"]),
            )
            if key in output:
                raise ValueError("dynamic response records contain duplicate row keys")
            output[key] = record
        return output

    free_by_key = keyed(free_flow_records)
    stressed_by_key = keyed(stressed_records)
    common = tuple(sorted(set(free_by_key) & set(stressed_by_key)))
    expected = frozenset((int(left), int(right)) for left, right in expected_keys)
    if len(expected) != int(expected_record_count):
        raise ValueError("expected_keys must match expected_record_count")
    row_identity_aligned = bool(
        set(free_by_key) == set(stressed_by_key) == set(expected)
    )
    feature_changed = 0
    target_changed = 0
    joint_changed = 0
    for key in common:
        free = free_by_key[key]
        stressed = stressed_by_key[key]
        free_features = np.asarray(
            [float(free.features["model_inputs"][name]) for name in COST_TO_GO_FEATURE_NAMES]
        )
        stressed_features = np.asarray(
            [
                float(stressed.features["model_inputs"][name])
                for name in COST_TO_GO_FEATURE_NAMES
            ]
        )
        feature_did_change = bool(
            np.any(np.abs(free_features - stressed_features) > 1.0e-7)
        )
        target_did_change = abs(
            float(free.labels["label_cost_to_go"])
            - float(stressed.labels["label_cost_to_go"])
        ) > 1.0e-6
        if feature_did_change:
            feature_changed += 1
        if target_did_change:
            target_changed += 1
        if feature_did_change and target_did_change:
            joint_changed += 1
    denominator = max(len(common), 1)
    return DynamicResponseAudit(
        expected_row_count=int(expected_record_count),
        matched_row_count=len(common),
        feature_changed_count=feature_changed,
        target_changed_count=target_changed,
        joint_changed_count=joint_changed,
        feature_changed_share=feature_changed / denominator,
        target_changed_share=target_changed / denominator,
        joint_changed_share=joint_changed / denominator,
        row_identity_aligned=row_identity_aligned,
    )


def _aggregate_dynamic_response_runs(
    runs: tuple[CostToGoFeatureAuditRun, ...],
) -> DynamicResponseAudit:
    expected_row_count = sum(run.expected_record_count_per_state for run in runs)
    matched_row_count = sum(run.dynamic_matched_row_count for run in runs)
    feature_changed_count = sum(run.dynamic_feature_changed_count for run in runs)
    target_changed_count = sum(run.dynamic_target_changed_count for run in runs)
    joint_changed_count = sum(run.dynamic_joint_changed_count for run in runs)
    denominator = max(matched_row_count, 1)
    return DynamicResponseAudit(
        expected_row_count=expected_row_count,
        matched_row_count=matched_row_count,
        feature_changed_count=feature_changed_count,
        target_changed_count=target_changed_count,
        joint_changed_count=joint_changed_count,
        feature_changed_share=feature_changed_count / denominator,
        target_changed_share=target_changed_count / denominator,
        joint_changed_share=joint_changed_count / denominator,
        row_identity_aligned=all(run.all_state_rows_retained for run in runs),
    )


def _summarize_audit(
    *,
    config: CostToGoFeatureAuditConfig,
    runs: tuple[CostToGoFeatureAuditRun, ...],
    feature_matrix: np.ndarray,
    targets: np.ndarray,
    distances: np.ndarray,
    map_keys: np.ndarray,
    corpus_parts: tuple[str, ...],
) -> CostToGoFeatureAuditResult:
    features = np.asarray(feature_matrix, dtype=np.float64)
    target_values = np.asarray(targets, dtype=np.float64)
    distance_values = np.asarray(distances, dtype=np.float64)
    resolved_map_keys = np.asarray(map_keys, dtype=object)
    if features.ndim != 2 or features.shape[1] != len(COST_TO_GO_FEATURE_NAMES):
        raise ValueError("feature audit matrix has unexpected shape")
    if target_values.shape != (features.shape[0],):
        raise ValueError("feature audit targets must match matrix rows")
    if distance_values.shape != (features.shape[0], 2):
        raise ValueError("feature audit distances must match matrix rows")
    if resolved_map_keys.shape != (features.shape[0],):
        raise ValueError("feature audit map keys must match matrix rows")
    if not np.isfinite(features).all() or not np.isfinite(target_values).all():
        raise ValueError("feature audit values must be finite")
    columns = tuple(
        FeatureColumnAudit(
            feature_name=name,
            minimum=float(np.min(features[:, index])),
            maximum=float(np.max(features[:, index])),
            mean=float(np.mean(features[:, index], dtype=np.float64)),
            standard_deviation=float(np.std(features[:, index], dtype=np.float64)),
            nonzero_share=float(np.mean(np.abs(features[:, index]) > 1.0e-12)),
            near_constant=(
                float(np.std(features[:, index], dtype=np.float64))
                <= config.near_constant_std_threshold
            ),
        )
        for index, name in enumerate(COST_TO_GO_FEATURE_NAMES)
    )
    distance_bins = []
    normalized_distance = distance_values[:, 1]
    for lower, upper in zip(_DISTANCE_BINS[:-1], _DISTANCE_BINS[1:], strict=True):
        mask = (normalized_distance >= lower) & (normalized_distance < upper)
        selected = target_values[mask]
        distance_bins.append(
            DistanceBinAudit(
                lower_inclusive=lower,
                upper_exclusive=min(upper, 1.0),
                row_count=int(selected.size),
                target_mean=(float(np.mean(selected)) if selected.size else None),
                target_standard_deviation=(
                    float(np.std(selected, dtype=np.float64)) if selected.size else None
                ),
            )
        )
    nonconstant_share = sum(not column.near_constant for column in columns) / len(columns)
    all_closure = all(
        run.closure_link_count == run.closure_requested_link_count > 0
        and run.closure_eligible_link_count >= run.closure_requested_link_count
        for run in runs
    )
    all_rows_retained = all(run.all_state_rows_retained for run in runs)
    all_split = all(run.per_map_split_feasible for run in runs)
    map_holdout = _build_map_holdout(config, runs)
    relation = audit_feature_target_relation(features, target_values, resolved_map_keys)
    target_std = float(np.std(target_values, dtype=np.float64))
    dynamic_response = _aggregate_dynamic_response_runs(runs)
    authorized = evaluate_cost_to_go_feature_audit_gate(
        config=config,
        nonconstant_feature_share=nonconstant_share,
        target_standard_deviation=target_std,
        all_maps_have_closure_support=all_closure,
        all_state_rows_retained=all_rows_retained,
        all_maps_have_v1_split=all_split,
        map_holdout_feasible=map_holdout.feasible,
        feature_target_relation_passed=relation.passed,
        dynamic_feature_changed_share=dynamic_response.feature_changed_share,
        dynamic_target_changed_share=dynamic_response.target_changed_share,
        dynamic_joint_changed_share=dynamic_response.joint_changed_share,
    )
    return CostToGoFeatureAuditResult(
        config=config,
        runs=runs,
        feature_columns=columns,
        distance_bins=tuple(distance_bins),
        feature_target_relation=relation,
        map_holdout=map_holdout,
        row_count=int(features.shape[0]),
        map_count=len(runs),
        dynamic_state_count=len(runs) * len(_DYNAMIC_STATE_NAMES),
        destination_group_count=sum(run.destination_group_count for run in runs),
        target_minimum=float(np.min(target_values)),
        target_maximum=float(np.max(target_values)),
        target_standard_deviation=target_std,
        raw_distance_minimum_m=float(np.min(distance_values[:, 0])),
        raw_distance_maximum_m=float(np.max(distance_values[:, 0])),
        nonconstant_feature_share=float(nonconstant_share),
        all_maps_have_closure_support=all_closure,
        all_state_rows_retained=all_rows_retained,
        all_maps_have_v1_split=all_split,
        cross_map_holdout_feasible=map_holdout.feasible,
        row_local_mlp_probe_authorized=authorized,
        dynamic_feature_changed_share=dynamic_response.feature_changed_share,
        dynamic_target_changed_share=dynamic_response.target_changed_share,
        dynamic_joint_changed_share=dynamic_response.joint_changed_share,
        dynamic_matched_row_count=dynamic_response.matched_row_count,
        dynamic_feature_changed_count=dynamic_response.feature_changed_count,
        dynamic_target_changed_count=dynamic_response.target_changed_count,
        dynamic_joint_changed_count=dynamic_response.joint_changed_count,
        corpus_fingerprint=_fingerprint_json(
            {
                "config": config.as_dict(),
                "corpus_parts": corpus_parts,
                "feature_contract_fingerprint": COST_TO_GO_FEATURE_CONTRACT_FINGERPRINT,
                "map_holdout_split_fingerprint": map_holdout.split_fingerprint,
                "feature_target_relation": relation.as_dict(),
            }
        ),
    )


def _render_markdown(result: CostToGoFeatureAuditResult) -> str:
    decision_text = {
        "admissible": "Authorize a subsequent experiment-only JAX MLP bakeoff.",
        "relation_rejected": (
            "Require PR50 adjacency/edge tensors before any model probe."
        ),
        "inconclusive": "Stop and repair the audit evidence before selecting a model.",
    }[result.decision_state]
    falsifier_text = {
        "admissible": (
            "A subsequent bakeoff fails cross-map error, determinism, timing, or fallback gates."
        ),
        "relation_rejected": (
            "A leakage-safe graph contract cannot preserve directed topology and dynamic "
            "edge state within deterministic memory-bounded batches."
        ),
        "inconclusive": (
            "A canonical rerun closes every missing evidence term and reaches an admissible "
            "or relation-rejected state without threshold changes."
        ),
    }[result.decision_state]
    next_action_text = {
        "admissible": (
            "Open a bounded row-local probe; baseline Dijkstra remains authoritative."
        ),
        "relation_rejected": (
            "PR50 freezes the graph data contract; baseline Dijkstra remains authoritative."
        ),
        "inconclusive": (
            "Do not open PR50 or a model probe until the audit evidence is complete."
        ),
    }[result.decision_state]
    lines = [
        "# Cost-To-Go Feature Audit",
        "",
        "Diagnostic only. This does not validate an NN or authorize a runtime backend.",
        "",
        f"- Maps: {result.map_count}",
        f"- Rows: {result.row_count}",
        f"- Dynamic states: {result.dynamic_state_count}",
        f"- Canonical gate profile: {str(result.config.canonical_gate_profile).lower()}",
        "- Threshold provenance: fixed in PR49 before the canonical run; not prior preregistration",
        f"- Nonconstant feature share: {result.nonconstant_feature_share:.3f}",
        f"- All state rows retained: {str(result.all_state_rows_retained).lower()}",
        f"- Near-duplicate relation coverage: {result.feature_target_relation.coverage_share:.3f}",
        f"- Near-duplicate target conflict share: {result.feature_target_relation.conflict_share:.3f}",
        f"- Cross-map holdout feasible: {str(result.cross_map_holdout_feasible).lower()}",
        f"- Decision state: {result.decision_state}",
        f"- Row-local MLP probe authorized: {str(result.row_local_mlp_probe_authorized).lower()}",
        f"- Runtime NN backend authorized: {str(result.runtime_nn_backend_authorized).lower()}",
        "",
        "| Feature | Min | Max | Std | Nonzero share | Near constant |",
        "|---|---:|---:|---:|---:|:---:|",
    ]
    for column in result.feature_columns:
        lines.append(
            f"| {column.feature_name} | {column.minimum:.6g} | {column.maximum:.6g} | "
            f"{column.standard_deviation:.6g} | {column.nonzero_share:.3f} | "
            f"{'yes' if column.near_constant else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Compact CCoT",
            "",
            "Question: Is row-local cost-to-go v1 ready for a bounded GPU model probe?",
            "Evidence: Multi-style, multi-seed, two-state feature support, target relation conflicts, row retention, and a deterministic seed holdout.",
            "Inference: Relation-sensitive support can authorize an experiment, not model adequacy.",
            "Counterevidence checked: No fit, accuracy, replay, or runtime inference was measured.",
            f"Decision: {decision_text}",
            f"Falsifier: {falsifier_text}",
            f"Next action: {next_action_text}",
            "",
        ]
    )
    return "\n".join(lines)


def _select_reachability_preserving_closures(
    network: RoadNetworkCSR,
    *,
    ranked_candidates: tuple[int, ...],
    requested_count: int,
    usable_link_mask: np.ndarray,
) -> tuple[int, ...]:
    usable = np.asarray(usable_link_mask, dtype=np.bool_)
    if usable.shape != (network.link_count,):
        raise ValueError("usable_link_mask must match network.link_count")
    selected: set[int] = set()
    for link_index in ranked_candidates:
        proposed = selected | {int(link_index)}
        source = int(network.link_src_node_index[link_index])
        destination = int(network.link_dst_node_index[link_index])
        if _directed_path_exists(
            network,
            source_node_index=source,
            destination_node_index=destination,
            blocked_link_indices=proposed,
            usable_link_mask=usable,
        ):
            selected.add(int(link_index))
            if len(selected) >= int(requested_count):
                break
    return tuple(sorted(selected))


def _directed_path_exists(
    network: RoadNetworkCSR,
    *,
    source_node_index: int,
    destination_node_index: int,
    blocked_link_indices: set[int],
    usable_link_mask: np.ndarray,
) -> bool:
    if source_node_index == destination_node_index:
        return True
    visited = {int(source_node_index)}
    queue = [int(source_node_index)]
    cursor = 0
    while cursor < len(queue):
        node_index = queue[cursor]
        cursor += 1
        start = int(network.outgoing_indptr[node_index])
        end = int(network.outgoing_indptr[node_index + 1])
        for raw_link_index in network.outgoing_link_indices[start:end]:
            link_index = int(raw_link_index)
            if link_index in blocked_link_indices or not bool(
                usable_link_mask[link_index]
            ):
                continue
            next_node = int(network.link_dst_node_index[link_index])
            if next_node == destination_node_index:
                return True
            if next_node not in visited:
                visited.add(next_node)
                queue.append(next_node)
    return False


def _stable_unit_interval(*, seed: int, value: int) -> float:
    digest = hashlib.sha256(f"{seed}:{value}:stress".encode()).digest()
    return int.from_bytes(digest[:8], "little") / float((1 << 64) - 1)


def _fingerprint_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--style-ids", default="grid_core,polycentric_tod,organic")
    parser.add_argument("--seeds", default="17,29,41")
    parser.add_argument("--destination-count", type=int, default=4)
    parser.add_argument("--closure-fraction", type=float, default=0.03)
    args = parser.parse_args()
    config = CostToGoFeatureAuditConfig(
        style_ids=tuple(value.strip() for value in args.style_ids.split(",") if value.strip()),
        seeds=tuple(int(value.strip()) for value in args.seeds.split(",") if value.strip()),
        destination_count=args.destination_count,
        closure_fraction=args.closure_fraction,
    )
    result = run_cost_to_go_feature_audit(config)
    paths = write_cost_to_go_feature_audit_bundle(result, args.output_dir)
    print(json.dumps({key: str(value) for key, value in paths.items()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
