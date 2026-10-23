"""Immutable public data model for the pure-Python formative-growth lane."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
from typing import Mapping

__all__ = [
    "FormationConfig",
    "FormationCentre",
    "FormationNode",
    "FormationEdge",
    "FormationBlock",
    "FormationMap",
]

_EPS = 1.0e-9

@dataclass(frozen=True, slots=True)
class FormationConfig:
    """Controls one deterministic morphogenetic city realization.

    Units are explicit: area is km² and all generated coordinates/lengths are m.
    The default node count keeps the research run light enough for a CPU-only
    pure-Python implementation while still producing multi-scale urban form.
    """

    seed: int = 20261023
    urbanized_area_km2: float = 25.0
    aspect_ratio: float = 9.0 / 7.0
    node_count: int = 320
    epochs: int = 7
    secondary_centre_count: int = 2
    target_mean_degree: float = 3.02
    max_local_edge_m: float = 620.0
    max_node_degree: int = 5
    min_block_area_m2: float = 4_000.0
    max_block_area_fraction: float = 0.10
    orientation_alignment_floor: float = 0.60
    old_core_fraction: float = 0.38
    exploration_start: float = 0.40
    exploration_end: float = 0.21
    infill_budget: int = 0
    infill_area_threshold_m2: float = 120_000.0
    infill_min_child_area_m2: float = 18_000.0

    def __post_init__(self) -> None:
        if not isinstance(self.infill_budget,int) or isinstance(self.infill_budget,bool) or self.infill_budget < 0:
            raise ValueError("infill_budget must be a non-negative integer")
        for name in ("infill_area_threshold_m2","infill_min_child_area_m2"):
            if not math.isfinite(getattr(self,name)) or getattr(self,name) <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if not isinstance(self.seed, int) or isinstance(self.seed, bool):
            raise TypeError("seed must be an integer")
        if not math.isfinite(self.urbanized_area_km2) or self.urbanized_area_km2 <= 0.0:
            raise ValueError("urbanized_area_km2 must be finite and positive")
        if not math.isfinite(self.aspect_ratio) or self.aspect_ratio <= 0.0:
            raise ValueError("aspect_ratio must be finite and positive")
        if self.node_count < 24:
            raise ValueError("node_count must be at least 24")
        if not 3 <= self.epochs <= 12:
            raise ValueError("epochs must be between 3 and 12")
        if not 0 <= self.secondary_centre_count <= 4:
            raise ValueError("secondary_centre_count must be between 0 and 4")
        if not 2.0 <= self.target_mean_degree < 4.5:
            raise ValueError("target_mean_degree must be in [2.0, 4.5)")
        if self.max_local_edge_m <= 0.0:
            raise ValueError("max_local_edge_m must be positive")
        if self.max_node_degree < 3:
            raise ValueError("max_node_degree must be at least 3")
        if not 0.0 < self.old_core_fraction < 1.0:
            raise ValueError("old_core_fraction must be in (0, 1)")
        if not 0.0 <= self.exploration_end <= self.exploration_start <= 1.0:
            raise ValueError("exploration probabilities must satisfy 0 <= end <= start <= 1")

@dataclass(frozen=True, slots=True)
class FormationCentre:
    centre_id: int
    x_m: float
    y_m: float
    birth_epoch: int
    attraction: float
    local_grid_angle_rad: float

@dataclass(frozen=True, slots=True)
class FormationNode:
    node_id: int
    x_m: float
    y_m: float
    birth_epoch: int
    centre_id: int
    mode: str

@dataclass(frozen=True, slots=True)
class FormationEdge:
    edge_id: int
    u: int
    v: int
    birth_epoch: int
    length_m: float
    hierarchy: str
    role: str
    score: float = 0.0

    @property
    def key(self) -> tuple[int, int]:
        return (min(self.u, self.v), max(self.u, self.v))

@dataclass(frozen=True, slots=True)
class FormationBlock:
    block_id: int
    node_ids: tuple[int, ...]
    area_m2: float
    centroid_x_m: float
    centroid_y_m: float
    land_use: str
    mean_birth_epoch: float

@dataclass(frozen=True, slots=True)
class FormationMap:
    config: FormationConfig
    width_m: float
    height_m: float
    centres: tuple[FormationCentre, ...]
    nodes: tuple[FormationNode, ...]
    edges: tuple[FormationEdge, ...]
    blocks: tuple[FormationBlock, ...]
    metrics: Mapping[str, float | int | str]
    audit: Mapping[str, object]
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        payload = {
            "config": {name: getattr(self.config, name) for name in self.config.__dataclass_fields__},
            "width_m": round(self.width_m, 6),
            "height_m": round(self.height_m, 6),
            "centres": [
                [c.centre_id, round(c.x_m, 6), round(c.y_m, 6), c.birth_epoch,
                 round(c.attraction, 6), round(c.local_grid_angle_rad, 9)]
                for c in self.centres
            ],
            "nodes": [
                [n.node_id, round(n.x_m, 6), round(n.y_m, 6), n.birth_epoch,
                 n.centre_id, n.mode]
                for n in self.nodes
            ],
            "edges": [
                [e.edge_id, e.u, e.v, e.birth_epoch, round(e.length_m, 6),
                 e.hierarchy, e.role, round(e.score, 9)]
                for e in self.edges
            ],
            "blocks": [
                [b.block_id, list(b.node_ids), round(b.area_m2, 6), b.land_use]
                for b in self.blocks
            ],
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        object.__setattr__(self, "fingerprint", digest)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "formative_growth_v1",
            "fingerprint": self.fingerprint,
            "config": {name: getattr(self.config, name) for name in self.config.__dataclass_fields__},
            "width_m": self.width_m,
            "height_m": self.height_m,
            "centres": [c.__dict__ if hasattr(c, "__dict__") else {
                "centre_id": c.centre_id,
                "x_m": c.x_m,
                "y_m": c.y_m,
                "birth_epoch": c.birth_epoch,
                "attraction": c.attraction,
                "local_grid_angle_rad": c.local_grid_angle_rad,
            } for c in self.centres],
            "nodes": [{
                "node_id": n.node_id,
                "x_m": n.x_m,
                "y_m": n.y_m,
                "birth_epoch": n.birth_epoch,
                "centre_id": n.centre_id,
                "mode": n.mode,
            } for n in self.nodes],
            "edges": [{
                "edge_id": e.edge_id,
                "u": e.u,
                "v": e.v,
                "birth_epoch": e.birth_epoch,
                "length_m": e.length_m,
                "hierarchy": e.hierarchy,
                "role": e.role,
                "score": e.score,
            } for e in self.edges],
            "blocks": [{
                "block_id": b.block_id,
                "node_ids": list(b.node_ids),
                "area_m2": b.area_m2,
                "centroid_x_m": b.centroid_x_m,
                "centroid_y_m": b.centroid_y_m,
                "land_use": b.land_use,
                "mean_birth_epoch": b.mean_birth_epoch,
            } for b in self.blocks],
            "metrics": dict(self.metrics),
            "audit": dict(self.audit),
        }
