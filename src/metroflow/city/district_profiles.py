"""Per-district road character, keyed on the project's existing taxonomy.

`zones._district_archetype_for_type` already classifies every zone into one of
four district archetypes, and `CityGenerationConfig.zone_mix_targets` already
declares how much of the city each should occupy. Those definitions survived the
topology failure and are reused verbatim here rather than replaced.

What is new is only the road-morphology side: how finely each archetype is
subdivided, how much of its fabric terminates in cul-de-sacs, and how far apart
its collectors run. Real cities differ across districts far more than they
differ from each other on a city-wide average, and a single global spacing
cannot express that - which is why the current fabric looks the same downtown
and in the suburbs.

Values are authored design targets, not empirical calibration. They set block
size and dead-end structure, both of which the morphology gate measures.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

__all__ = [
    "DistrictRoadProfile",
    "DISTRICT_ROAD_PROFILES",
    "assign_district_archetypes",
    "profile_for",
]


@dataclass(frozen=True, slots=True)
class DistrictRoadProfile:
    """Road-growth character for one district archetype. Distances in meters."""

    archetype: str
    density_tier: str
    local_spacing_m: float
    collector_spacing_m: float
    local_step_m: float
    local_max_steps: int
    local_turn_deg: float
    cul_de_sac_share: float

    def __post_init__(self) -> None:
        if self.local_spacing_m <= 0.0 or self.collector_spacing_m <= 0.0:
            raise ValueError("district spacings must be > 0")
        if not 0.0 <= self.cul_de_sac_share <= 1.0:
            raise ValueError("cul_de_sac_share must be a share in [0, 1]")
        if self.collector_spacing_m <= self.local_spacing_m:
            raise ValueError("collectors must be spaced wider than local streets")


# Ordering is the load-bearing part: block size grows from the core outward, and
# cul-de-sacs are a suburban trait that a downtown grid does not have.
DISTRICT_ROAD_PROFILES: Mapping[str, DistrictRoadProfile] = MappingProxyType(
    {
        "central_business_core": DistrictRoadProfile(
            archetype="central_business_core",
            density_tier="high",
            local_spacing_m=105.0,
            collector_spacing_m=330.0,
            local_step_m=34.0,
            local_max_steps=6,
            local_turn_deg=9.0,
            cul_de_sac_share=0.04,
        ),
        "mixed_activity_hub": DistrictRoadProfile(
            archetype="mixed_activity_hub",
            density_tier="medium",
            local_spacing_m=150.0,
            collector_spacing_m=430.0,
            local_step_m=44.0,
            local_max_steps=6,
            local_turn_deg=16.0,
            cul_de_sac_share=0.22,
        ),
        "residential_neighborhood": DistrictRoadProfile(
            archetype="residential_neighborhood",
            density_tier="medium",
            local_spacing_m=200.0,
            collector_spacing_m=540.0,
            local_step_m=52.0,
            local_max_steps=6,
            local_turn_deg=24.0,
            cul_de_sac_share=0.46,
        ),
        "industrial_belt": DistrictRoadProfile(
            archetype="industrial_belt",
            density_tier="low",
            local_spacing_m=330.0,
            collector_spacing_m=680.0,
            local_step_m=78.0,
            local_max_steps=5,
            local_turn_deg=7.0,
            cul_de_sac_share=0.12,
        ),
    }
)


def profile_for(archetype: str) -> DistrictRoadProfile:
    try:
        return DISTRICT_ROAD_PROFILES[str(archetype)]
    except KeyError as exc:
        raise KeyError(f"unknown district archetype {archetype!r}") from exc


def assign_district_archetypes(
    *,
    center_count: int,
    seed: int,
    zone_mix_targets: Mapping[object, float] | None = None,
) -> tuple[str, ...]:
    """Allocate an archetype to each urban centre, following the zone mix.

    The primary centre is always the central business core; the rest are dealt
    out in proportion to `CityGenerationConfig.zone_mix_targets` so the district
    composition matches the zoning the runtime already expects. Deterministic
    for a given (center_count, seed).
    """

    count = int(center_count)
    if count <= 0:
        raise ValueError("center_count must be > 0")

    from metroflow.sim.config import CityGenerationConfig, ZoneType

    from .zones import _district_archetype_for_type

    targets = zone_mix_targets or CityGenerationConfig().zone_mix_targets
    # Map zone shares onto archetype shares through the existing classifier.
    share_by_archetype: dict[str, float] = {}
    for zone_type in ZoneType:
        archetype = _district_archetype_for_type(zone_type)
        share_by_archetype[archetype] = share_by_archetype.get(archetype, 0.0) + float(
            targets.get(zone_type, 0.0)
        )
    total = sum(share_by_archetype.values()) or 1.0

    remaining = count - 1  # the primary centre is spoken for
    ordered = sorted(share_by_archetype.items(), key=lambda item: (-item[1], item[0]))
    quotas: dict[str, int] = {}
    for archetype, share in ordered:
        quotas[archetype] = int(remaining * share / total)
    # Hand out the rounding remainder to the largest shares first, so the result
    # is exact and reproducible rather than dependent on float ordering.
    leftover = remaining - sum(quotas.values())
    for archetype, _share in ordered:
        if leftover <= 0:
            break
        quotas[archetype] += 1
        leftover -= 1

    pool: list[str] = []
    for archetype, quota in quotas.items():
        pool.extend([archetype] * quota)

    # Deterministic interleave: rotate by seed so different seeds place the same
    # composition differently without changing the mix.
    if pool:
        offset = int(seed) % len(pool)
        pool = pool[offset:] + pool[:offset]
    return ("central_business_core",) + tuple(pool[:remaining])
