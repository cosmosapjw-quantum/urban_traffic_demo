"""Typed, bounded public capabilities for project-owned morphology styles.

This module owns public labels, compatibility identifiers, structural claim
ceilings, and generator-arm availability.  It is deliberately a fixed catalog:
it is not a plugin registry and it does not make empirical or traffic claims.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping

__all__ = [
    "GENERATOR_ARMS",
    "STYLE_CAPABILITIES",
    "STYLE_IDS",
    "SkipReason",
    "StyleCapability",
    "get_style_capability",
    "style_ids_for_arm",
    "style_supports_arm",
]


GENERATOR_ARMS = (
    "standard",
    "sidecar_morphology",
    "sidecar_district_cells",
    "sidecar_local_fabric",
    "sidecar_local_fabric_planar",
    "realistic_synthetic_v1",
    "growth_fabric_v1",
    "scalable_synthetic_v2",
)


class SkipReason(str, Enum):
    """Closed reason set for control-table attempts that produce no score."""

    UNSUPPORTED_ARM_STYLE = "UNSUPPORTED_ARM_STYLE"
    UNSUPPORTED_DIRECTIONAL_LANE_ALLOCATION = "UNSUPPORTED_DIRECTIONAL_LANE_ALLOCATION"
    UNSUPPORTED_ONEWAY_VALUE = "UNSUPPORTED_ONEWAY_VALUE"


@dataclass(frozen=True, slots=True)
class StyleCapability:
    """Bounded public contract for one morphology compatibility identifier."""

    style_id: str
    public_label: str
    compatibility_id: str
    implemented_structural_claims: tuple[str, ...]
    explicitly_unclaimed_functions: tuple[str, ...]
    supported_generator_arms: frozenset[str]
    legacy_center_pattern: str
    legacy_street_pattern: str
    empirical_reference_cities: tuple[str, ...]
    literature_basis: str

    def __post_init__(self) -> None:
        if not self.style_id:
            raise ValueError("style_id must not be empty")
        if not self.public_label:
            raise ValueError("public_label must not be empty")
        if not self.compatibility_id:
            raise ValueError("compatibility_id must not be empty")
        if not self.implemented_structural_claims:
            raise ValueError("implemented_structural_claims must not be empty")
        if not self.explicitly_unclaimed_functions:
            raise ValueError("explicitly_unclaimed_functions must not be empty")
        if not self.supported_generator_arms:
            raise ValueError("supported_generator_arms must not be empty")
        if not self.legacy_center_pattern or not self.legacy_street_pattern:
            raise ValueError("legacy morphology patterns must not be empty")
        if not self.literature_basis:
            raise ValueError("literature_basis must not be empty")
        unknown_arms = self.supported_generator_arms - set(GENERATOR_ARMS)
        if unknown_arms:
            raise ValueError(f"unsupported generator arms: {sorted(unknown_arms)!r}")


_NONSTANDARD_ARMS = frozenset(
    arm for arm in GENERATOR_ARMS if arm != "standard"
)
_STANDARD_AND_NONSTANDARD_ARMS = frozenset(GENERATOR_ARMS)
_UNCLAIMED_FUNCTIONS = (
    "empirical urban-morphology validity",
    "traffic-functional validity",
    "runtime-default promotion",
)

STYLE_CAPABILITIES = (
    StyleCapability(
        style_id="ring_radial",
        public_label="Ring Radial (Concentric Rings & Radial Spines)",
        compatibility_id="ring_radial",
        implemented_structural_claims=(
            "nested orbital cycles with radial spokes and a peripheral mainline",
        ),
        explicitly_unclaimed_functions=_UNCLAIMED_FUNCTIONS,
        supported_generator_arms=_STANDARD_AND_NONSTANDARD_ARMS,
        legacy_center_pattern="monocentric",
        legacy_street_pattern="radial_ring",
        empirical_reference_cities=(),
        literature_basis="Legacy compatibility grammar; retained as a control, not a universal city model.",
    ),
    StyleCapability(
        style_id="grid_core",
        public_label="Grid Core (Standard Uniform Lattice)",
        compatibility_id="grid_core",
        implemented_structural_claims=(
            "shared-axis orthogonal surface lattice in scalable_synthetic_v2",
        ),
        explicitly_unclaimed_functions=_UNCLAIMED_FUNCTIONS,
        supported_generator_arms=_NONSTANDARD_ARMS,
        legacy_center_pattern="distributed_grid",
        legacy_street_pattern="orthogonal_grid",
        empirical_reference_cities=("Chicago", "Buenos Aires"),
        literature_basis="Single-orientation grid with high four-way connectivity.",
    ),
    StyleCapability(
        style_id="polycentric_tod",
        public_label="Polycentric TOD (Multi-Hub Centers)",
        compatibility_id="polycentric_tod",
        implemented_structural_claims=(
            "non-collinear centre anchors with catchments and hierarchy paths",
        ),
        explicitly_unclaimed_functions=_UNCLAIMED_FUNCTIONS,
        supported_generator_arms=_STANDARD_AND_NONSTANDARD_ARMS,
        legacy_center_pattern="polycentric",
        legacy_street_pattern="polycentric_mesh",
        empirical_reference_cities=("Boston",),
        literature_basis="Multiple comparable centers connected without mandatory downtown traversal.",
    ),
    StyleCapability(
        style_id="river_constrained",
        public_label="River Constrained (Bifurcated Corridor & Bridges)",
        compatibility_id="river_constrained",
        implemented_structural_claims=(
            "barrier-constrained banks with registered bridge crossings",
        ),
        explicitly_unclaimed_functions=_UNCLAIMED_FUNCTIONS,
        supported_generator_arms=_NONSTANDARD_ARMS,
        legacy_center_pattern="linear_banks",
        legacy_street_pattern="corridor_constrained",
        empirical_reference_cities=("Hong Kong",),
        literature_basis="Longitudinal corridors and limited transverse crossings model a barrier-constrained city.",
    ),
    StyleCapability(
        style_id="superblock_mixed",
        public_label="Superblock Mixed (Hierarchical Macroblock Perimeters)",
        compatibility_id="superblock_mixed",
        implemented_structural_claims=(
            "two-axis macroblocks bounded by hierarchy-qualified perimeters",
        ),
        explicitly_unclaimed_functions=_UNCLAIMED_FUNCTIONS,
        supported_generator_arms=_NONSTANDARD_ARMS,
        legacy_center_pattern="district_clusters",
        legacy_street_pattern="multi_grid",
        empirical_reference_cities=("Detroit", "Seattle"),
        literature_basis="Several locally ordered grids use different orientations and sparse connectors.",
    ),
    StyleCapability(
        style_id="organic",
        public_label="Curvilinear Warped Grid (organic compatibility ID)",
        compatibility_id="organic",
        implemented_structural_claims=(
            "deterministic curvilinear warped-grid embedding in scalable_synthetic_v2",
            "legacy organic-mesh compatibility grammar in nonstandard generator arms",
        ),
        explicitly_unclaimed_functions=_UNCLAIMED_FUNCTIONS,
        supported_generator_arms=_NONSTANDARD_ARMS,
        legacy_center_pattern="accreted",
        legacy_street_pattern="organic_mesh",
        empirical_reference_cities=("Charlotte", "Seoul"),
        literature_basis="Legacy organic-mesh compatibility grammar; scalable_synthetic_v2 is a curvilinear warped grid, not organic topology.",
    ),
)

STYLE_IDS = tuple(capability.style_id for capability in STYLE_CAPABILITIES)
_CAPABILITY_BY_STYLE_ID: Mapping[str, StyleCapability] = MappingProxyType(
    {capability.style_id: capability for capability in STYLE_CAPABILITIES}
)
if len(_CAPABILITY_BY_STYLE_ID) != len(STYLE_CAPABILITIES):
    raise RuntimeError("style capability identifiers must be unique")


def get_style_capability(style_id: str) -> StyleCapability:
    """Return one known capability or reject unknown public identifiers."""
    try:
        return _CAPABILITY_BY_STYLE_ID[str(style_id)]
    except KeyError as exc:
        allowed = ", ".join(STYLE_IDS)
        raise ValueError(f"morphology style_id must be one of: {allowed}") from exc


def style_ids_for_arm(arm: str) -> tuple[str, ...]:
    """Return styles supported by one known generator arm in canonical order."""
    arm = str(arm)
    if arm not in GENERATOR_ARMS:
        allowed = ", ".join(GENERATOR_ARMS)
        raise ValueError(f"generator arm must be one of: {allowed}")
    return tuple(
        capability.style_id
        for capability in STYLE_CAPABILITIES
        if arm in capability.supported_generator_arms
    )


def style_supports_arm(style_id: str, arm: str) -> bool:
    """Return the fixed arm capability after validating both identifiers."""
    capability = get_style_capability(style_id)
    return capability.style_id in style_ids_for_arm(arm)
