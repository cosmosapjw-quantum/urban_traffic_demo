"""PR103/PR110 gallery provenance and manifest binding tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_GALLERY_DIR = _REPO_ROOT / "artifacts" / "sample_city_maps"
_MANIFEST_PATH = _GALLERY_DIR / "gallery_manifest.json"

EXPECTED_STYLES = {
    "grid_core",
    "ring_radial",
    "river_constrained",
    "polycentric_tod",
    "superblock_mixed",
    "organic",
}


def test_gallery_manifest_provenance() -> None:
    """Verify gallery manifest records full scalable_synthetic_v2 provenance and SVG bindings."""
    assert _MANIFEST_PATH.exists(), "gallery manifest must exist"
    data = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    assert len(data) == 6, "all 6 morphology styles must be present"

    styles = set()
    for entry in data:
        assert entry["topology_mode"] == "scalable_synthetic_v2"
        assert entry["target_population"] == "100000"
        assert entry["urbanized_area_km2"] == "25.0"
        assert len(entry["network_fingerprint"]) == 64
        assert len(entry["blocks_fingerprint"]) == 64
        assert len(entry["compiled_fingerprint"]) == 64
        assert len(entry["static_authority_fingerprint"]) == 64
        assert len(entry["zoning_placement_fingerprint"]) == 64
        assert len(entry["city_map_fingerprint"]) == 64
        assert len(entry["svg_sha256"]) == 64
        assert int(entry["node_count"]) > 0
        assert int(entry["link_count"]) > 0

        # Verify SVG and PNG file integrity and digest match
        svg_file = _GALLERY_DIR / f"map_{entry['style_id']}.svg"
        assert svg_file.exists(), f"SVG file must exist for {entry['style_id']}"
        actual_svg = svg_file.read_text(encoding="utf-8")
        actual_sha = hashlib.sha256(actual_svg.encode("utf-8")).hexdigest()
        assert actual_sha == entry["svg_sha256"], f"SVG digest mismatch for {entry['style_id']}"

        png_file = _GALLERY_DIR / f"map_{entry['style_id']}.png"
        assert png_file.exists(), f"PNG file must exist for {entry['style_id']}"
        assert png_file.stat().st_size > 0

        styles.add(entry["style_id"])

    assert styles == EXPECTED_STYLES
