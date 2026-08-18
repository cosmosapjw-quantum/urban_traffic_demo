"""PR103 gallery provenance test."""

from __future__ import annotations

import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_GALLERY_DIR = _REPO_ROOT / "artifacts" / "sample_city_maps"
_MANIFEST_PATH = _GALLERY_DIR / "gallery_manifest.json"


def test_gallery_manifest_provenance() -> None:
    """Verify gallery manifest records scalable_synthetic_v2 provenance."""
    assert _MANIFEST_PATH.exists(), "gallery manifest must exist"
    data = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    assert len(data) == 6, "all 6 morphology styles must be present"

    styles = set()
    for entry in data:
        assert entry["topology_mode"] == "scalable_synthetic_v2"
        assert len(entry["network_fingerprint"]) == 64
        assert len(entry["blocks_fingerprint"]) == 64
        assert len(entry["compiled_fingerprint"]) == 64
        assert len(entry["static_authority_fingerprint"]) == 64
        assert int(entry["node_count"]) > 1000
        assert int(entry["link_count"]) > 4000
        styles.add(entry["style_id"])

    expected = {
        "grid_core",
        "ring_radial",
        "river_constrained",
        "polycentric_tod",
        "superblock_mixed",
        "organic",
    }
    assert styles == expected
