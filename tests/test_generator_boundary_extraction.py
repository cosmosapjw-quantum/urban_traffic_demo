from __future__ import annotations

import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    (
        "preview_mode",
        "node_count",
        "link_count",
        "geometry_fingerprint",
        "turn_fingerprint",
    ),
    (
        (
            "standard",
            1_141,
            5_646,
            "9f83754500e450d0da9eef71276efb067aac0519992b0e2078816f5a77df6cbd",
            "96c75b891dbcd36f5dbacb76ff38f168c6fd8cbb67399393aef85e4df229ed5d",
        ),
        (
            "sidecar_local_fabric",
            447,
            1_244,
            "7d0a7f2bc88dc8d0c52f86175624285145fc07ca0b38bfbe05cd1dccd20c5384",
            "9a29d3c1e976b9b377a337e52f0becc69a48cc19d3d6f72124ccc16ae5ab8613",
        ),
        (
            "sidecar_local_fabric_planar",
            970,
            3_336,
            "0615ccd6db38d581d880e83c85675a9b30fdbb46a245f8c3838afd9797ee0456",
            "81abbacead8566a4d95cafedcffc098d2e66864c9b062f7d4fefea4a2f38c022",
        ),
    ),
)
def test_generator_boundary_extraction_preserves_legacy_fingerprints(
    preview_mode: str,
    node_count: int,
    link_count: int,
    geometry_fingerprint: str,
    turn_fingerprint: str,
) -> None:
    from metroflow.city.generator_v2 import GeneratorV2

    topology = GeneratorV2().generate_preview_topology(
        {
            "scenario_id": "synthetic_smoke",
            "seed": 17,
            "preview_mode": preview_mode,
            "style_id": "polycentric_tod",
        }
    )

    assert len(topology.nodes) == node_count
    assert len(topology.links) == link_count
    assert topology.road_geometry is not None
    assert topology.road_geometry.fingerprint == geometry_fingerprint
    assert topology.metadata["turn_authority_fingerprint"] == turn_fingerprint


def test_preview_topology_compatibility_alias_is_preserved() -> None:
    from metroflow.city import PreviewCityTopology as PublicTopology
    from metroflow.city.generated_map import PreviewCityTopology
    from metroflow.city.generator_v2 import PreviewCityTopology as LegacyImport

    assert PublicTopology is PreviewCityTopology
    assert LegacyImport is PreviewCityTopology


def test_generation_boundary_imports_do_not_load_optional_accelerators() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "import metroflow.city.generated_map; "
                "import metroflow.city.topology_finalizer; "
                "assert 'jax' not in sys.modules; "
                "assert 'torch' not in sys.modules; "
                "assert '_metroflow_rust' not in sys.modules"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
