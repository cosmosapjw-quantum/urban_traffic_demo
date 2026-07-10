from __future__ import annotations

import json
from dataclasses import replace


def test_directed_reachability_reports_ordered_pairs() -> None:
    from metroflow.city.connectivity import analyze_directed_reachability
    from metroflow.city.graph import Node, RoadClass, RoadLink

    nodes = tuple(Node(node_id, x=float(node_id), y=0.0) for node_id in (1, 2, 3))
    links = (
        RoadLink(1, 1, 2, RoadClass.LOCAL, 1.0, 1.0, 1.0),
        RoadLink(2, 2, 1, RoadClass.LOCAL, 1.0, 1.0, 1.0),
    )
    report = analyze_directed_reachability(
        nodes=nodes,
        links=links,
        pairs=((1, 2), (2, 1), (1, 3), (3, 1)),
    )

    assert report.pair_count == 4
    assert report.reachable_pair_count == 2
    assert report.reachability_share == 0.5
    assert report.unreachable_pairs == ((1, 3), (3, 1))


def test_landuse_audit_fails_closed_for_invalid_poi_access() -> None:
    from metroflow.city.graph import Node, RoadClass, RoadLink
    from metroflow.city.landuse_accessibility import audit_landuse_accessibility
    from metroflow.city.zones import POI, POIType, Zone
    from metroflow.sim.config import ZoneType

    nodes = (Node(1, x=0.0, y=0.0), Node(2, x=100.0, y=0.0))
    links = (
        RoadLink(1, 1, 2, RoadClass.LOCAL, 100.0, 10.0, 1.0),
        RoadLink(2, 2, 1, RoadClass.LOCAL, 100.0, 10.0, 1.0),
    )
    zones = (
        Zone(1, ZoneType.RESIDENTIAL, 0.0, 0.0),
        Zone(2, ZoneType.CBD_COMMERCIAL, 100.0, 0.0),
    )
    pois = (
        POI(1, 1, POIType.HOME, 1),
        POI(2, 2, POIType.WORKPLACE, 99),
    )
    audit = audit_landuse_accessibility(
        nodes=nodes,
        links=links,
        zones=zones,
        pois=pois,
        node_zone_by_id={1: 1, 2: 2},
        zone_node_ids={1: (1,), 2: (2,)},
        coupling_mode="test",
        zoning_fingerprint="fixture",
    )

    assert audit.poi_access_valid_count == 1
    assert audit.poi_access_valid_share == 0.5
    assert audit.zone_access_coverage_share == 1.0
    assert audit.directed_zone_pair_reachability_share == 1.0


def test_landuse_comparison_rejects_duplicate_ids_and_bounds_zero_baseline() -> None:
    import pytest

    from metroflow.city.graph import Node, RoadClass, RoadLink
    from metroflow.city.landuse_accessibility import (
        audit_landuse_accessibility,
        compare_landuse_placements,
    )
    from metroflow.city.zones import POI, POIType, Zone, ZoningPlacementResult
    from metroflow.sim.config import ZoneType

    nodes = (Node(1, x=0.0, y=0.0), Node(2, x=1.0, y=0.0))
    links = (
        RoadLink(1, 1, 2, RoadClass.LOCAL, 1.0, 1.0, 1.0),
        RoadLink(2, 2, 1, RoadClass.LOCAL, 1.0, 1.0, 1.0),
    )
    zones = (
        Zone(1, ZoneType.RESIDENTIAL, 0.0, 0.0),
        Zone(2, ZoneType.CBD_COMMERCIAL, 1.0, 0.0),
    )
    legacy_poi = POI(1, 1, POIType.HOME, 99)
    morphology_poi = POI(1, 1, POIType.HOME, 1)
    mapping = {1: 1, 2: 2}
    zone_nodes = {1: (1,), 2: (2,)}
    legacy = ZoningPlacementResult(zones, (legacy_poi,), mapping, zone_nodes)
    morphology = ZoningPlacementResult(zones, (morphology_poi,), mapping, zone_nodes)
    legacy_audit = audit_landuse_accessibility(
        nodes=nodes,
        links=links,
        zones=zones,
        pois=legacy.pois,
        node_zone_by_id=mapping,
        zone_node_ids=zone_nodes,
        coupling_mode="legacy",
        zoning_fingerprint="legacy",
    )
    morphology_audit = audit_landuse_accessibility(
        nodes=nodes,
        links=links,
        zones=zones,
        pois=morphology.pois,
        node_zone_by_id=mapping,
        zone_node_ids=zone_nodes,
        coupling_mode="morphology_gated",
        zoning_fingerprint="morphology",
    )
    comparison = compare_landuse_placements(
        legacy=legacy,
        morphology=morphology,
        legacy_audit=legacy_audit,
        morphology_audit=morphology_audit,
    )
    assert comparison.accessibility_retention_ratio == 1.0
    duplicate = ZoningPlacementResult(
        zones,
        (morphology_poi, replace(morphology_poi)),
        mapping,
        zone_nodes,
    )
    with pytest.raises(ValueError, match="unique POI ids"):
        compare_landuse_placements(
            legacy=legacy,
            morphology=duplicate,
            legacy_audit=legacy_audit,
            morphology_audit=morphology_audit,
        )


def test_morphology_landuse_audit_bundle_is_diagnostic_and_reachable(tmp_path) -> None:
    from metroflow.ui.morphology_landuse_audit import (
        write_morphology_landuse_accessibility_audit,
    )

    paths = write_morphology_landuse_accessibility_audit(
        tmp_path,
        seeds=(3, 5, 7),
        style_ids=("polycentric_tod",),
        population_target=2_000,
    )
    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    runs = payload["styles"][0]["runs"]

    assert payload["artifact_format_version"] == "morphology_landuse_accessibility_v1"
    assert payload["evidence_status"] == "diagnostic_not_validation"
    assert payload["seeds"] == [3, 5, 7]
    assert all(run["morphology"]["poi_access_valid_share"] == 1.0 for run in runs)
    assert all(
        run["morphology"]["directed_zone_pair_reachability_share"] == 1.0
        for run in runs
    )
    assert all(run["comparison"]["placement_changed"] is True for run in runs)
    assert manifest["demand_policy_changed"] is False
    assert manifest["pr46_authorized"] is False
    assert manifest["runtime_backend_changed"] is False
    assert "PR46" in paths["markdown"].read_text(encoding="utf-8")
    assert set(manifest["artifact_files"]) == {
        "index.html",
        "morphology-landuse-accessibility.json",
        "morphology-landuse-accessibility.md",
        "polycentric_tod-legacy.html",
        "polycentric_tod-morphology.html",
    }
    assert "data-static-city-map" in paths["legacy_map"].read_text(encoding="utf-8")
    morphology_html = paths["morphology_map"].read_text(encoding="utf-8")
    assert "morphology_gated" in morphology_html
    assert "zoning_placement_fingerprint" in morphology_html


def test_morphology_landuse_audit_requires_three_unique_seeds(tmp_path) -> None:
    import pytest

    from metroflow.ui.morphology_landuse_audit import (
        write_morphology_landuse_accessibility_audit,
    )

    with pytest.raises(ValueError, match="at least three"):
        write_morphology_landuse_accessibility_audit(tmp_path, seeds=(1, 2))
    with pytest.raises(ValueError, match="unique"):
        write_morphology_landuse_accessibility_audit(tmp_path, seeds=(1, 1, 2))
    with pytest.raises(ValueError, match="style_ids must be unique"):
        write_morphology_landuse_accessibility_audit(
            tmp_path,
            seeds=(1, 2, 3),
            style_ids=("organic", "organic"),
        )
    with pytest.raises(ValueError, match="registered safe style ids"):
        write_morphology_landuse_accessibility_audit(
            tmp_path,
            seeds=(1, 2, 3),
            style_ids=("../escape",),
        )


def test_static_map_rejects_stale_zoning_fingerprint() -> None:
    import pytest

    from metroflow.sim.config import SimulationConfig
    from metroflow.sim.init import build_initial_simulation_state
    from metroflow.ui.static_map import build_static_city_map_artifact

    state = build_initial_simulation_state(
        config=SimulationConfig(population_target=500, active_agent_capacity=4),
        scenario_seed=9,
    ).state
    stale = replace(
        state,
        static=replace(
            state.static,
            metadata={
                **state.static.metadata,
                "zoning_placement_fingerprint": "0" * 64,
            },
        ),
    )
    with pytest.raises(ValueError, match="zoning_placement_fingerprint"):
        build_static_city_map_artifact(stale)
    unsealed_metadata = dict(state.static.metadata)
    unsealed_metadata.pop("zoning_placement_fingerprint")
    unsealed = replace(
        state,
        static=replace(state.static, metadata=unsealed_metadata),
    )
    artifact = build_static_city_map_artifact(unsealed)
    assert "zone_poi_coupling_resolved_mode" not in artifact.metadata
