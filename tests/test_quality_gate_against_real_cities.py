"""The quality gate rejects every one of its own real-city controls.

`morphology_quality` is a second, independent instrument from the Boeing
envelope, and it has never been run against real data. Doing so rejects all five
importable OSM extracts. A gate that fails Chicago, Barcelona, Seoul, Tokyo and
Charlotte is not measuring "is this a plausible city".

Only one threshold is changed here: the density floor, because PR-C depends on
density and because a real city sits below it. The other three refuted
thresholds are recorded as still-failing rather than tuned. Adjusting thresholds
until the generator passes is precisely the failure this remediation exists to
undo, and the same restraint applies when the thing that fails is real data.

The genuinely missing check is the opposite one: there is a floor and no
ceiling, which is why generated fabric at 32 km/km2 -- roughly twice the densest
real extract -- was invisible to the entire suite.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_OSM_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "osm_control"
IMPORTABLE = ("barcelona", "charlotte", "chicago", "seoul", "tokyo")


def _metrics(city: str):
    from metroflow.benchmarks.morphology_control_table import build_osm_topology
    from metroflow.city.morphology_quality import compute_morphology_quality_metrics

    return compute_morphology_quality_metrics(build_osm_topology(_OSM_DIR / f"{city}.osm"))


def _failures(city: str) -> list[str]:
    from metroflow.benchmarks.morphology_control_table import build_osm_topology
    from metroflow.city.morphology_quality import (
        compute_morphology_quality_metrics,
        evaluate_morphology_quality_gate,
    )

    topology = build_osm_topology(_OSM_DIR / f"{city}.osm")
    gate = evaluate_morphology_quality_gate(
        style_id="organic",
        geometry_fingerprint=topology.road_geometry.fingerprint,
        metrics=compute_morphology_quality_metrics(topology),
    )
    return list(gate.failures)


def test_the_area_convention_is_pinned_in_code() -> None:
    """Hull and bounding box differ by ~25%, so an unnamed convention is a trap.

    The band quoted in `growth_fabric` as "5.3-13.9 km/km2" is a bounding-box
    figure; these same extracts measure 7.4-17.8 over the convex hull, which is
    what this instrument actually uses. Every overshoot factor depends on which
    one is meant.
    """

    from metroflow.city.morphology_quality import DENSITY_AREA_CONVENTION

    assert DENSITY_AREA_CONVENTION == "node_convex_hull"


def test_the_density_floor_admits_the_least_dense_real_city() -> None:
    """Charlotte measures 7.439 km/km2 against a floor of 10."""

    charlotte = _metrics("charlotte").street_density_km_per_km2

    assert charlotte == pytest.approx(7.439, abs=0.01)
    assert "street_density_km_per_km2 must be >= 10" not in _failures("charlotte")


def test_a_density_ceiling_exists_and_would_catch_the_generated_fabric() -> None:
    """The missing half of the check.

    With a floor and no ceiling, a generator can emit unlimited street length and
    the gate stays silent. That is how the runtime default reached 28.9-35.7
    km/km2 -- twice the densest real extract -- without anything noticing.
    """

    from metroflow.city.morphology_quality import MORPHOLOGY_QUALITY_GATE_THRESHOLDS

    ceiling = MORPHOLOGY_QUALITY_GATE_THRESHOLDS["maximum_street_density_km_per_km2"]

    densest_real = max(
        _metrics(city).street_density_km_per_km2 for city in IMPORTABLE
    )
    assert densest_real == pytest.approx(17.769, abs=0.01)
    assert ceiling >= densest_real, "the ceiling must admit every real control"
    assert ceiling < 23.0, "a ceiling above the generated fabric would not bite"


def test_the_ceiling_is_advisory_so_the_runtime_default_is_not_silently_changed() -> None:
    """Reporting an overshoot must not re-route zone-POI coupling.

    `zones.py` consults this gate to choose between current and legacy coupling.
    The runtime default `standard` measures 28.9-35.7 km/km2 and would fail a
    blocking ceiling, which would change zone assignment, demand, and therefore
    simulation output -- a runtime change smuggled in as an instrument fix.

    So the overshoot is reported and admission is unchanged. It becomes blocking
    once the density work lands.
    """

    from metroflow.benchmarks.morphology_control_table import build_arm_topology
    from metroflow.city.morphology_quality import (
        compute_morphology_quality_metrics,
        evaluate_morphology_quality_gate,
    )

    topology = build_arm_topology(arm="standard", style_id="ring_radial", seed=17)
    metrics = compute_morphology_quality_metrics(topology)
    gate = evaluate_morphology_quality_gate(
        style_id="ring_radial",
        geometry_fingerprint=topology.road_geometry.fingerprint,
        metrics=metrics,
    )

    assert metrics.street_density_km_per_km2 > 21.323
    assert any("exceeds the real-city ceiling" in item for item in gate.advisories)
    assert not any("street_density" in item for item in gate.failures)
    # And the advisory must not reach the payload bound into replay fingerprints.
    assert "advisories" not in gate.as_dict()


def test_the_density_bounds_are_derived_from_the_extracts_not_authored() -> None:
    """Same [0.8*min, 1.2*max] construction the Boeing envelope already uses.

    Pinning the numbers keeps the gate fast; re-deriving them here keeps the pin
    falsifiable, so the bounds cannot drift away from the data they claim to come
    from.
    """

    from metroflow.city.morphology_quality import MORPHOLOGY_QUALITY_GATE_THRESHOLDS

    measured = [_metrics(city).street_density_km_per_km2 for city in IMPORTABLE]

    assert MORPHOLOGY_QUALITY_GATE_THRESHOLDS[
        "minimum_street_density_km_per_km2"
    ] == pytest.approx(0.8 * min(measured), abs=0.01)
    assert MORPHOLOGY_QUALITY_GATE_THRESHOLDS[
        "maximum_street_density_km_per_km2"
    ] == pytest.approx(1.2 * max(measured), abs=0.01)


def test_every_real_city_still_fails_the_component_check() -> None:
    """Recorded, not tuned away. A clipped bbox is not one component.

    This is an artifact of cutting a 5-12 km2 window out of a city, not a
    property of the city. It is left failing because the honest fix is to
    measure connectivity on the largest component or the 2-core, which is
    PR-D's G2 work, not a threshold edit.
    """

    for city in IMPORTABLE:
        assert "weak_component_count must equal 1" in _failures(city)


def test_four_of_five_real_cities_still_fail_block_continuity() -> None:
    """Also recorded rather than tuned."""

    failing = [
        city for city in IMPORTABLE if any("block_continuity" in f for f in _failures(city))
    ]

    assert sorted(failing) == ["charlotte", "chicago", "seoul", "tokyo"]
