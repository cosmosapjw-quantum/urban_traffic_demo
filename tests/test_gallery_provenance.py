"""PR103/PR110 gallery provenance and manifest binding tests."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest

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


def _render_module():
    module_path = _REPO_ROOT / "tools" / "render_morphology_gallery.py"
    spec = importlib.util.spec_from_file_location("render_morphology_gallery_test", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


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
        assert hashlib.sha256(png_file.read_bytes()).hexdigest() == entry["png_sha256"]

        styles.add(entry["style_id"])

    assert styles == EXPECTED_STYLES


def test_gallery_renderer_uses_absolute_svg_uri_and_binds_png(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """A relative output path must not produce Chrome's ERR_INVALID_URL page."""
    module = _render_module()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        module,
        "MORPHOLOGY_GALLERY_SET",
        (("grid_core", 17),),
    )
    chrome_commands: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> None:
        chrome_commands.append(command)
        screenshot_arg = next(item for item in command if item.startswith("--screenshot="))
        Path(screenshot_arg.removeprefix("--screenshot=")).write_bytes(b"bound-png")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    module.render_all_sample_maps(Path("gallery"), generate_png=True)

    expected_svg = (tmp_path / "gallery" / "map_grid_core.svg").as_uri()
    expected_png = tmp_path / "gallery" / "map_grid_core.png"
    assert chrome_commands[0][-1] == expected_svg
    assert f"--screenshot={expected_png}" in chrome_commands[0]
    manifest = json.loads((tmp_path / "gallery" / "gallery_manifest.json").read_text())
    assert manifest[0]["png_sha256"] == hashlib.sha256(b"bound-png").hexdigest()


def test_svg_only_render_does_not_rebind_a_stale_png(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Skipping Chrome must not make an old screenshot current provenance."""
    module = _render_module()
    monkeypatch.setattr(
        module,
        "MORPHOLOGY_GALLERY_SET",
        (("grid_core", 17),),
    )
    gallery = tmp_path / "gallery"
    gallery.mkdir()
    (gallery / "map_grid_core.png").write_bytes(b"stale-png")

    module.render_all_sample_maps(gallery, generate_png=False)

    manifest = json.loads((gallery / "gallery_manifest.json").read_text())
    assert "png_sha256" not in manifest[0]
    assert manifest[0]["png_provenance"] == "not_rendered_svg_only"


def test_png_render_rejects_a_stale_file_when_chrome_writes_nothing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """A successful Chrome exit without a fresh non-empty file is not a render."""
    module = _render_module()
    monkeypatch.setattr(
        module,
        "MORPHOLOGY_GALLERY_SET",
        (("grid_core", 17),),
    )
    gallery = tmp_path / "gallery"
    gallery.mkdir()
    png_path = gallery / "map_grid_core.png"
    png_path.write_bytes(b"stale-png")
    monkeypatch.setattr(module.subprocess, "run", lambda *_args, **_kwargs: None)

    with pytest.raises(RuntimeError, match="fresh non-empty PNG"):
        module.render_all_sample_maps(gallery, generate_png=True)

    assert not png_path.exists()
