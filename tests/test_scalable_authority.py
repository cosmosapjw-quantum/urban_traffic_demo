from __future__ import annotations

import importlib


def test_scalable_authority_public_api_is_exact() -> None:
    authority = importlib.import_module("metroflow.city.scalable_authority")

    assert authority.__all__ == (
        "BlockLandUseV2",
        "ImmutableBridgeCrossing",
        "ImmutableNode",
        "ImmutableRoadLink",
        "ImmutableRoadNetworkCSR",
        "ImmutableTurnMovement",
        "MapFingerprintSetV3",
        "PopulationCapacityCertificate",
        "RoutingStaticDependencyKey",
        "ScalableStaticAuthority",
        "V2LandUseType",
        "V2Poi",
        "V2PoiCatalog",
        "V2PoiKind",
        "V2Taz",
        "V2TazCatalog",
        "build_scalable_static_authority",
        "require_valid_scalable_static_authority",
    )
