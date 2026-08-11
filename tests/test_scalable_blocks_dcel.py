from __future__ import annotations

import hashlib
import json
import subprocess
import sys


def test_scalable_blocks_module_import_exists() -> None:
    import metroflow.city as city

    assert city.__name__ == "metroflow.city"

    import metroflow.city.scalable_blocks as blocks

    assert blocks.__name__ == "metroflow.city.scalable_blocks"


def test_fresh_scalable_blocks_import_does_not_load_legacy_compilers() -> None:
    legacy_modules = (
        "metroflow.city.block_land_use",
        "metroflow.city.planar_blocks",
        "metroflow.city.planarization",
        "metroflow.city.topology_finalizer",
        "metroflow.city.generator_v2",
    )
    script = f"""
import json
import sys
import metroflow.city.scalable_blocks
print(json.dumps([name for name in {list(legacy_modules)!r} if name in sys.modules]))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == []


def test_lazy_city_exports_preserve_identity_all_and_unknown_attribute() -> None:
    legacy_modules = (
        "metroflow.city.block_land_use",
        "metroflow.city.planar_blocks",
        "metroflow.city.planarization",
        "metroflow.city.topology_finalizer",
        "metroflow.city.generator_v2",
    )
    lazy_exports = {
        "BlockLandUse": ".block_land_use",
        "BlockLandUseType": ".block_land_use",
        "BlockPOI": ".block_land_use",
        "BlockPOIType": ".block_land_use",
        "LandUseCatalog": ".block_land_use",
        "build_block_land_use_catalog": ".block_land_use",
        "CityBlock": ".planar_blocks",
        "CityBlockCatalog": ".planar_blocks",
        "compile_planar_city_blocks": ".planar_blocks",
        "GenerationPipeline": ".generator_v2",
        "GeneratorV2": ".generator_v2",
    }
    script = f"""
import hashlib
import importlib
import json
import sys

import metroflow.city.scalable_blocks as blocks
import metroflow.city as city

legacy_modules = {list(legacy_modules)!r}
expected_map = {lazy_exports!r}
payload = {{
    "loaded_before": [name for name in legacy_modules if name in sys.modules],
    "lazy_map": city.__dict__.get("_LAZY_EXPORT_MODULE"),
}}
if not payload["loaded_before"] and payload["lazy_map"] == expected_map:
    identities = {{}}
    from_identities = {{}}
    for name, module_name in expected_map.items():
        direct = getattr(importlib.import_module(module_name, city.__name__), name)
        identities[name] = getattr(city, name) is direct
        namespace = {{}}
        exec(f"from metroflow.city import {{name}}", namespace)
        from_identities[name] = namespace[name] is direct
    from metroflow.city.blueprint import (
        CityBlueprint,
        GeneratedCityMap,
        RealisticCityQualityResult,
    )
    from metroflow.city.realistic_city import generate_city_map
    payload.update(
        identities=identities,
        from_identities=from_identities,
        existing_lazy={{
            "CityBlueprint": city.CityBlueprint is CityBlueprint,
            "GeneratedCityMap": city.GeneratedCityMap is GeneratedCityMap,
            "RealisticCityQualityResult": (
                city.RealisticCityQualityResult is RealisticCityQualityResult
            ),
            "generate_city_map": city.generate_city_map is generate_city_map,
        }},
        unknown=(
            "no error"
            if hasattr(city, "definitely_not_a_city_export")
            else "definitely_not_a_city_export"
        ),
        task3b_exported=any(
            name in city.__all__
            for name in blocks.__dict__.get("__all__", ())
        ),
    )
payload["all_sha256"] = hashlib.sha256(
    json.dumps(city.__all__, separators=(",", ":")).encode()
).hexdigest()
print(json.dumps(payload, sort_keys=True))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)

    assert payload["lazy_map"] == lazy_exports
    assert payload["loaded_before"] == []
    assert all(payload["identities"].values())
    assert all(payload["from_identities"].values())
    assert all(payload["existing_lazy"].values())
    assert payload["unknown"] == "definitely_not_a_city_export"
    assert not payload["task3b_exported"]
    assert payload["all_sha256"] == hashlib.sha256(
        json.dumps(
            [
                "BlockLandUse",
                "BlockLandUseType",
                "BlockPOI",
                "BlockPOIType",
                "BridgeCrossing",
                "CityBlock",
                "CityBlockCatalog",
                "CityBlueprint",
                "GateDecision",
                "GateThresholds",
                "GateVersions",
                "GenerationPipeline",
                "GeneratedCityMap",
                "GeneratorV2",
                "LandUseCatalog",
                "MORPHOLOGY_ARCHETYPES",
                "MorphologyArchetype",
                "MorphologyQualityMetrics",
                "MorphologyQualityGate",
                "Node",
                "NodeKind",
                "PhysicalStreet",
                "PhysicalStreetPlan",
                "PreviewCityTopology",
                "RoadClass",
                "RoadLink",
                "RoadNetworkCSR",
                "RealisticStreetNetwork",
                "RealisticCityQualityResult",
                "StreetNetworkMorphometrics",
                "TerrainField",
                "TopologyValidationIssue",
                "TopologyValidationReport",
                "TurnAuthorityCatalog",
                "TurnMovement",
                "TurnType",
                "UrbanCenter",
                "UrbanFormField",
                "WeakConnectivityRepairResult",
                "WeakConnectivityReport",
                "analyze_weak_connectivity",
                "build_block_land_use_catalog",
                "build_road_network_csr",
                "build_hierarchical_street_skeleton",
                "build_continuous_local_fabric",
                "build_terrain_field",
                "build_urban_form_field",
                "compute_street_network_morphometrics",
                "compute_morphology_quality_metrics",
                "compile_turn_authority",
                "compile_planar_city_blocks",
                "empirical_street_network_references",
                "evaluate_morphology_quality_gate",
                "generate_city_map",
                "get_morphology_archetype",
                "repair_weak_connectivity",
                "validate_road_network_topology",
            ],
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
