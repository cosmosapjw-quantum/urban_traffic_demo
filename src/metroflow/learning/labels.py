"""Simulator-only supervised label export helpers.

These records are experiment substrate for future surrogate work. They do not
change route legality, routing authority, or runtime fallback behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from metroflow.city.graph import RoadNetworkCSR
from metroflow.flow.state import LinkState
from metroflow.routing.candidates import create_route_candidate_set
from metroflow.routing.dynamic_potential import compute_dynamic_potential_state
from metroflow.sim.routing_runtime import _select_candidate_route

__all__ = [
    "SimulatorLabelRecord",
    "export_cost_to_go_label_records",
    "export_route_scoring_label_records",
    "write_label_records_jsonl",
]

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class SimulatorLabelRecord:
    """One deterministic simulator-derived supervised label row."""

    label_kind: str
    source_authority: str
    scenario_id: str
    tick_index: int
    routing_backend: str
    features: dict[str, Any]
    labels: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION
    fingerprint: str = ""

    def __post_init__(self) -> None:
        label_kind = str(self.label_kind).strip()
        if not label_kind:
            raise ValueError("label_kind must be non-empty")
        source_authority = str(self.source_authority).strip()
        if not source_authority:
            raise ValueError("source_authority must be non-empty")
        scenario_id = str(self.scenario_id).strip()
        if not scenario_id:
            raise ValueError("scenario_id must be non-empty")
        tick_index = int(self.tick_index)
        if tick_index < 0:
            raise ValueError("tick_index must be >= 0")
        schema_version = int(self.schema_version)
        if schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        features = _canonical_mapping(self.features)
        labels = _canonical_mapping(self.labels)
        metadata = _canonical_mapping(self.metadata)
        object.__setattr__(self, "label_kind", label_kind)
        object.__setattr__(self, "source_authority", source_authority)
        object.__setattr__(self, "scenario_id", scenario_id)
        object.__setattr__(self, "tick_index", tick_index)
        object.__setattr__(self, "routing_backend", str(self.routing_backend))
        object.__setattr__(self, "features", features)
        object.__setattr__(self, "labels", labels)
        object.__setattr__(self, "metadata", metadata)
        object.__setattr__(self, "schema_version", schema_version)
        fingerprint = str(self.fingerprint).strip()
        if not fingerprint:
            fingerprint = _fingerprint_payload(
                {
                    "schema_version": schema_version,
                    "label_kind": label_kind,
                    "source_authority": source_authority,
                    "scenario_id": scenario_id,
                    "tick_index": tick_index,
                    "routing_backend": str(self.routing_backend),
                    "features": features,
                    "labels": labels,
                    "metadata": metadata,
                }
            )
        object.__setattr__(self, "fingerprint", fingerprint)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": int(self.schema_version),
            "label_kind": self.label_kind,
            "source_authority": self.source_authority,
            "scenario_id": self.scenario_id,
            "tick_index": int(self.tick_index),
            "routing_backend": self.routing_backend,
            "features": self.features,
            "labels": self.labels,
            "metadata": self.metadata,
            "fingerprint": self.fingerprint,
        }


def export_cost_to_go_label_records(
    *,
    road_csr: RoadNetworkCSR,
    link_state: LinkState,
    destination_node_ids: Sequence[int],
    scenario_id: str = "simulator",
    tick_index: int = 0,
    routing_backend: str = "baseline",
) -> tuple[SimulatorLabelRecord, ...]:
    """Export baseline-authoritative destination cost-to-go labels."""

    if str(routing_backend) != "baseline":
        raise ValueError("cost-to-go label export requires routing_backend='baseline'")
    if link_state.link_count != road_csr.link_count:
        raise ValueError("link_state.link_count must match road_csr.link_count")
    records: list[SimulatorLabelRecord] = []
    for destination_node_id in tuple(int(node_id) for node_id in destination_node_ids):
        potential = compute_dynamic_potential_state(
            road_csr,
            destination_node_id=destination_node_id,
            link_state=link_state,
            routing_backend="baseline",
        )
        node_cost = np.asarray(potential.node_cost_to_go, dtype=np.float32)
        for node_index, cost in enumerate(node_cost):
            cost_f = float(cost)
            if not np.isfinite(cost_f) or cost_f >= 1e12 * 0.5:
                continue
            node_id = int(road_csr.node_ids[int(node_index)])
            records.append(
                SimulatorLabelRecord(
                    label_kind="cost_to_go",
                    source_authority="baseline_dynamic_potential",
                    scenario_id=scenario_id,
                    tick_index=tick_index,
                    routing_backend="baseline",
                    features={
                        "node_id": node_id,
                        "node_index": int(node_index),
                        "destination_node_id": int(destination_node_id),
                        "destination_node_index": int(
                            potential.destination_node_index
                        ),
                    },
                    labels={"label_cost_to_go": cost_f},
                    metadata={
                        "destination_node_id": int(destination_node_id),
                        "link_count": int(road_csr.link_count),
                        "node_count": int(road_csr.node_count),
                        "source_backend": str(
                            potential.metadata.get("routing_backend", "baseline")
                        ),
                        "label_units": {
                            "label_cost_to_go": "generalized_travel_time_cost_ticks",
                        },
                    },
                )
            )
    return tuple(sorted(records, key=lambda record: record.fingerprint))


def export_route_scoring_label_records(
    *,
    road_csr: RoadNetworkCSR,
    link_state: LinkState,
    od_pairs: Sequence[tuple[int, int]],
    scenario_id: str = "simulator",
    tick_index: int = 0,
    max_candidates: int = 2,
    max_hops: int = 64,
    path_size_gamma: float = 0.0,
    routing_backend: str = "baseline",
) -> tuple[SimulatorLabelRecord, ...]:
    """Export baseline-authoritative route scoring labels for OD pairs."""

    if str(routing_backend) != "baseline":
        raise ValueError("route-scoring label export requires routing_backend='baseline'")
    if int(max_candidates) < 1:
        raise ValueError("max_candidates must be >= 1")
    if link_state.link_count != road_csr.link_count:
        raise ValueError("link_state.link_count must match road_csr.link_count")
    records: list[SimulatorLabelRecord] = []
    for origin_node_id, destination_node_id in tuple(od_pairs):
        candidate_set = create_route_candidate_set(
            road_csr=road_csr,
            link_state=link_state,
            od_key=(int(origin_node_id), int(destination_node_id)),
            origin_node_id=int(origin_node_id),
            destination_node_id=int(destination_node_id),
            current_tick=int(tick_index),
            max_candidates=int(max_candidates),
            max_hops=int(max_hops),
            routing_backend="baseline",
        )
        if not candidate_set.candidate_paths:
            continue
        metadata = candidate_set.metadata
        costs = tuple(
            float(item) for item in tuple(metadata.get("candidate_path_costs", ()) or ())
        )
        path_sizes = tuple(
            float(item)
            for item in tuple(metadata.get("candidate_path_size_factors", ()) or ())
        )
        route_scores = _route_score_values(
            costs,
            path_sizes,
            path_size_gamma=float(path_size_gamma),
        )
        selected = _select_candidate_route(
            candidate_set,
            path_size_gamma=float(path_size_gamma),
            routing_backend="baseline",
        )
        if selected is None:
            continue
        records.append(
            SimulatorLabelRecord(
                label_kind="route_scoring",
                source_authority="baseline_route_candidate_scoring",
                scenario_id=scenario_id,
                tick_index=tick_index,
                routing_backend="baseline",
                features={
                    "origin_node_id": int(origin_node_id),
                    "destination_node_id": int(destination_node_id),
                    "candidate_ids": tuple(int(item) for item in candidate_set.candidate_ids),
                    "candidate_paths": candidate_set.candidate_paths,
                    "candidate_path_costs": costs,
                    "candidate_path_size_factors": path_sizes,
                    "path_size_gamma": float(path_size_gamma),
                    "max_candidates": int(max_candidates),
                    "max_hops": int(max_hops),
                },
                labels={
                    "selected_candidate_index": int(selected.candidate_index),
                    "selected_candidate_id": int(selected.candidate_id),
                    "selected_candidate_utility": float(selected.utility),
                    "route_score_values": tuple(float(value) for value in route_scores),
                },
                metadata={
                    "candidate_generation_mode": str(
                        metadata.get("candidate_generation_mode", "")
                    ),
                    "candidate_enumeration_backend": str(
                        metadata.get("candidate_enumeration_backend", "")
                    ),
                    "candidate_metadata_backend": str(
                        metadata.get("candidate_metadata_backend", "")
                    ),
                    "source_backend": str(metadata.get("routing_backend", "baseline")),
                    "feature_units": {
                        "candidate_path_costs": "generalized_travel_time_cost_ticks",
                        "candidate_path_size_factors": "dimensionless",
                    },
                    "label_units": {
                        "selected_candidate_index": "index",
                        "selected_candidate_id": "identifier",
                        "selected_candidate_utility": "path_size_corrected_utility",
                        "route_score_values": "path_size_corrected_utility",
                    },
                    "route_score_formula": (
                        "-candidate_path_cost + path_size_gamma * "
                        "log(candidate_path_size_factor)"
                    ),
                },
            )
        )
    return tuple(sorted(records, key=lambda record: record.fingerprint))


def write_label_records_jsonl(
    records: Sequence[SimulatorLabelRecord],
    output_path: str | Path,
) -> None:
    """Write label records as stable JSONL sorted by fingerprint."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sorted_records = sorted(tuple(records), key=lambda record: record.fingerprint)
    with path.open("w", encoding="utf-8") as handle:
        for record in sorted_records:
            handle.write(
                json.dumps(
                    record.to_json_dict(),
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
            )
            handle.write("\n")


def _route_score_values(
    candidate_path_costs: tuple[float, ...],
    candidate_path_size_factors: tuple[float, ...],
    *,
    path_size_gamma: float,
) -> np.ndarray:
    costs = np.asarray(candidate_path_costs, dtype=np.float32)
    path_sizes = np.ones_like(costs, dtype=np.float32)
    raw_path_sizes = np.asarray(candidate_path_size_factors, dtype=np.float32)
    if raw_path_sizes.ndim == 1 and int(raw_path_sizes.shape[0]) >= int(costs.shape[0]):
        path_sizes = raw_path_sizes[: int(costs.shape[0])]
    safe_path_sizes = np.where(
        np.logical_and(np.isfinite(path_sizes), path_sizes > 0.0),
        path_sizes,
        np.asarray(1.0e-12, dtype=np.float32),
    )
    return np.asarray(
        -costs + max(0.0, float(path_size_gamma)) * np.log(safe_path_sizes),
        dtype=np.float32,
    )


def _canonical_mapping(value: Mapping[str, Any] | dict[str, Any]) -> dict[str, Any]:
    return {str(key): _canonical_value(raw) for key, raw in dict(value).items()}


def _canonical_value(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return _canonical_value(value.tolist())
    if isinstance(value, np.generic):
        return _canonical_value(value.item())
    if isinstance(value, Mapping):
        return _canonical_mapping(value)
    if isinstance(value, tuple):
        return tuple(_canonical_value(item) for item in value)
    if isinstance(value, list):
        return tuple(_canonical_value(item) for item in value)
    if isinstance(value, float):
        if not np.isfinite(value):
            raise ValueError("label record numeric values must be finite")
        return float(value)
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, int):
        return int(value)
    return value


def _json_ready(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _json_ready(raw) for key, raw in sorted(value.items())}
    return value


def _fingerprint_payload(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        _json_ready(payload),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
