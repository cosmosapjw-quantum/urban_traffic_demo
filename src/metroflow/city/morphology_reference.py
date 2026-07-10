"""Literature-backed street-network references and synthetic archetype contracts."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

__all__ = [
    "EmpiricalStreetNetworkReference",
    "MorphologyArchetype",
    "MORPHOLOGY_ARCHETYPES",
    "empirical_street_network_references",
    "get_morphology_archetype",
]

BOEING_2019_DOI = "https://doi.org/10.1007/s41109-019-0189-1"


@dataclass(frozen=True, slots=True)
class EmpiricalStreetNetworkReference:
    """Observed city metrics retained for comparison, never runtime calibration."""

    city: str
    orientation_order: float
    orientation_entropy: float
    median_segment_length_m: float
    circuity: float
    mean_node_degree: float
    dead_end_share: float
    four_way_share: float
    source_url: str = BOEING_2019_DOI
    evidence_status: str = "reference_only"

    def __post_init__(self) -> None:
        if not self.city:
            raise ValueError("city must not be empty")
        if not 0.0 <= self.orientation_order <= 1.0:
            raise ValueError("orientation_order must be in [0, 1]")
        if self.orientation_entropy < 0.0:
            raise ValueError("orientation_entropy must be >= 0")
        if self.median_segment_length_m <= 0.0:
            raise ValueError("median_segment_length_m must be > 0")
        if self.circuity < 1.0:
            raise ValueError("circuity must be >= 1")
        if self.mean_node_degree < 0.0:
            raise ValueError("mean_node_degree must be >= 0")
        if not 0.0 <= self.dead_end_share <= 1.0:
            raise ValueError("dead_end_share must be in [0, 1]")
        if not 0.0 <= self.four_way_share <= 1.0:
            raise ValueError("four_way_share must be in [0, 1]")


@dataclass(frozen=True, slots=True)
class MorphologyArchetype:
    """Project-owned generation grammar informed by, but not copying, real cities."""

    style_id: str
    center_pattern: str
    street_pattern: str
    empirical_reference_cities: tuple[str, ...]
    literature_basis: str
    evidence_status: str = "specified_project_archetype"


_EMPIRICAL_REFERENCES = (
    EmpiricalStreetNetworkReference("Chicago", 0.899, 2.083, 105.3, 1.016, 3.343, 0.074, 0.507),
    EmpiricalStreetNetworkReference("Detroit", 0.582, 2.807, 101.2, 1.012, 3.352, 0.053, 0.482),
    EmpiricalStreetNetworkReference("Seattle", 0.723, 2.542, 97.2, 1.028, 3.107, 0.136, 0.369),
    EmpiricalStreetNetworkReference("Boston", 0.026, 3.554, 77.0, 1.039, 2.945, 0.135, 0.211),
    EmpiricalStreetNetworkReference("Charlotte", 0.002, 3.582, 117.2, 1.067, 2.546, 0.288, 0.139),
    EmpiricalStreetNetworkReference("Seoul", 0.009, 3.573, 53.5, 1.048, 3.011, 0.101, 0.205),
    EmpiricalStreetNetworkReference("Hong Kong", 0.012, 3.571, 61.0, 1.137, 2.932, 0.114, 0.174),
    EmpiricalStreetNetworkReference("Buenos Aires", 0.151, 3.411, 104.8, 1.011, 3.548, 0.027, 0.576),
)


_ARCHETYPES: Mapping[str, MorphologyArchetype] = MappingProxyType(
    {
        "ring_radial": MorphologyArchetype(
            "ring_radial",
            "monocentric",
            "radial_ring",
            (),
            "Legacy compatibility grammar; retained as a control, not a universal city model.",
        ),
        "grid_core": MorphologyArchetype(
            "grid_core",
            "distributed_grid",
            "orthogonal_grid",
            ("Chicago", "Buenos Aires"),
            "Single-orientation grid with high four-way connectivity.",
        ),
        "polycentric_tod": MorphologyArchetype(
            "polycentric_tod",
            "polycentric",
            "polycentric_mesh",
            ("Boston",),
            "Multiple comparable centers connected without mandatory downtown traversal.",
        ),
        "river_constrained": MorphologyArchetype(
            "river_constrained",
            "linear_banks",
            "corridor_constrained",
            ("Hong Kong",),
            "Longitudinal corridors and limited transverse crossings model a barrier-constrained city.",
        ),
        "superblock_mixed": MorphologyArchetype(
            "superblock_mixed",
            "district_clusters",
            "multi_grid",
            ("Detroit", "Seattle"),
            "Several locally ordered grids use different orientations and sparse connectors.",
        ),
        "organic": MorphologyArchetype(
            "organic",
            "accreted",
            "organic_mesh",
            ("Charlotte", "Seoul"),
            "Irregular nearest-neighbor accretion with loops and cul-de-sacs.",
        ),
    }
)

MORPHOLOGY_ARCHETYPES = tuple(_ARCHETYPES)


def empirical_street_network_references() -> tuple[EmpiricalStreetNetworkReference, ...]:
    return _EMPIRICAL_REFERENCES


def get_morphology_archetype(style_id: str) -> MorphologyArchetype:
    try:
        return _ARCHETYPES[str(style_id)]
    except KeyError as exc:
        allowed = ", ".join(MORPHOLOGY_ARCHETYPES)
        raise ValueError(f"morphology style_id must be one of: {allowed}") from exc
