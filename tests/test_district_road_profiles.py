"""District-specific road character, keyed on the project's own taxonomy.

`GrowthConfig` applies one local spacing, one collector spacing and one
cul-de-sac share to the whole city, so a downtown core and a suburb come out
with identical fabric. The district taxonomy that distinguishes them already
exists in `zones._district_archetype_for_type`; this binds road morphology to
it rather than inventing a parallel classification.
"""

from __future__ import annotations

import math



def test_profiles_are_keyed_on_the_existing_district_archetypes() -> None:
    """Reuse `zones._district_archetype_for_type`, do not invent a taxonomy."""

    from metroflow.city.district_profiles import DISTRICT_ROAD_PROFILES
    from metroflow.city.zones import _district_archetype_for_type
    from metroflow.sim.config import ZoneType

    expected = {_district_archetype_for_type(zone_type) for zone_type in ZoneType}

    assert set(DISTRICT_ROAD_PROFILES) == expected


def test_downtown_is_finer_grained_than_suburb_and_industry() -> None:
    """Block size ordering is the whole point: CBD < residential < industrial."""

    from metroflow.city.district_profiles import DISTRICT_ROAD_PROFILES

    cbd = DISTRICT_ROAD_PROFILES["central_business_core"]
    residential = DISTRICT_ROAD_PROFILES["residential_neighborhood"]
    industrial = DISTRICT_ROAD_PROFILES["industrial_belt"]

    assert cbd.local_spacing_m < residential.local_spacing_m < industrial.local_spacing_m
    assert cbd.collector_spacing_m < industrial.collector_spacing_m


def test_cul_de_sacs_are_a_suburban_trait_not_a_downtown_one() -> None:
    """Dead ends belong to residential fabric; a CBD grid has almost none."""

    from metroflow.city.district_profiles import DISTRICT_ROAD_PROFILES

    cbd = DISTRICT_ROAD_PROFILES["central_business_core"]
    residential = DISTRICT_ROAD_PROFILES["residential_neighborhood"]

    assert residential.cul_de_sac_share > cbd.cul_de_sac_share
    assert cbd.cul_de_sac_share < 0.10


def test_archetype_assignment_follows_zone_mix_targets() -> None:
    """Districts are allocated by the configured zone mix, deterministically."""

    from metroflow.city.district_profiles import assign_district_archetypes

    first = assign_district_archetypes(center_count=12, seed=17)
    second = assign_district_archetypes(center_count=12, seed=17)

    assert first == second
    assert len(first) == 12
    # The primary center is always the core, whatever the mix says.
    assert first[0] == "central_business_core"
    # Residential is the plurality target (0.4), so it must dominate.
    assert first.count("residential_neighborhood") >= 4


def test_growth_produces_measurably_different_fabric_per_district() -> None:
    """The end-to-end claim: local street density must vary across districts."""

    from metroflow.city.growth_fabric import compile_grown_network, grow_street_network
    from metroflow.city.terrain_field import build_terrain_field
    from metroflow.city.urban_form import build_urban_form_field

    terrain = build_terrain_field(width=6000, height=6000, seed=17, style_id="polycentric_tod")
    urban_form = build_urban_form_field(terrain=terrain, style_id="polycentric_tod", seed=17)
    network = grow_street_network(terrain=terrain, urban_form=urban_form, seed=17)
    topology = compile_grown_network(network.streets)

    from metroflow.city.district_profiles import assign_district_archetypes

    archetypes = assign_district_archetypes(center_count=len(urban_form.centers), seed=17)
    centers = [(float(c.x_m), float(c.y_m)) for c in urban_form.centers]

    # Profiles set local SPACING, which controls how many streets a district
    # gets and how long each one is. Total length is deliberately not the
    # differentiating quantity: a fine-grained core has many short streets and a
    # suburb has fewer long ones, so the two totals can coincide.
    geometry = topology.road_geometry
    link_by_id = {int(link.link_id): link for link in topology.links}
    counts: dict[str, int] = {}
    lengths: dict[str, float] = {}
    seen: set[int] = set()
    for assignment in geometry.assignments:
        if int(assignment.geometry_id) in seen:
            continue
        seen.add(int(assignment.geometry_id))
        if link_by_id[int(assignment.link_id)].road_class.value != "local":
            continue
        centerline = geometry.centerline(int(assignment.geometry_id))
        midpoint = centerline.points_m[len(centerline.points_m) // 2]
        index = min(range(len(centers)), key=lambda i: math.dist(midpoint, centers[i]))
        if math.dist(midpoint, centers[index]) > 600.0:
            continue
        key = archetypes[index]
        counts[key] = counts.get(key, 0) + 1
        lengths[key] = lengths.get(key, 0.0) + centerline.length_m

    assert len(counts) >= 2, "no district differentiation at all"
    core = "central_business_core"
    other = next(key for key in counts if key != core)

    # The core is subdivided more finely: more streets, each shorter.
    assert counts[core] > counts[other] * 1.15, f"street counts barely differ: {counts}"
    core_mean = lengths[core] / counts[core]
    other_mean = lengths[other] / counts[other]
    assert other_mean > core_mean * 1.15, (
        f"mean street length barely differs: core {core_mean:.0f} m, {other} {other_mean:.0f} m"
    )
