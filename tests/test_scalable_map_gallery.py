"""Public gallery claims must stay below the implemented morphology evidence."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import pytest


def _gallery_module():
    path = Path(__file__).parents[1] / "tools" / "render_morphology_gallery.py"
    spec = importlib.util.spec_from_file_location("scalable_gallery_under_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _render_cached_single_style_gallery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Any, Path]:
    """Exercise the public renderer/checker without rebuilding the city per mutation."""
    module = _gallery_module()
    selected_entry = next(
        entry for entry in module.MORPHOLOGY_GALLERY_SET if entry[0] == "grid_core"
    )
    monkeypatch.setattr(module, "MORPHOLOGY_GALLERY_SET", (selected_entry,))

    real_builder = module.build_scalable_city_map
    cached_cities: dict[tuple[str, str, int], Any] = {}

    def cached_builder(config, *, scenario_id: str, seed: int):
        key = (config.morphology_style_id, scenario_id, seed)
        if key not in cached_cities:
            cached_cities[key] = real_builder(
                config,
                scenario_id=scenario_id,
                seed=seed,
            )
        return cached_cities[key]

    monkeypatch.setattr(module, "build_scalable_city_map", cached_builder)
    module.render_all_sample_maps(tmp_path, generate_png=False)
    return module, tmp_path / "gallery_manifest.json"


@pytest.mark.parametrize(
    ("style_id", "expected_label"),
    (
        ("organic", "Curvilinear Warped Grid (organic compatibility ID)"),
        ("superblock_mixed", "Superblock Mixed (Hierarchical Macroblock Perimeters)"),
    ),
)
def test_gallery_display_label_stays_below_the_implemented_structure(
    tmp_path: Path,
    monkeypatch,
    style_id: str,
    expected_label: str,
) -> None:
    """The public label cannot claim a stronger mechanism than the geometry."""
    module = _gallery_module()
    selected_entry = next(
        entry for entry in module.MORPHOLOGY_GALLERY_SET if entry[0] == style_id
    )
    monkeypatch.setattr(
        module,
        "MORPHOLOGY_GALLERY_SET",
        (selected_entry,),
    )

    module.render_all_sample_maps(tmp_path, generate_png=False)

    manifest = json.loads((tmp_path / "gallery_manifest.json").read_text(encoding="utf-8"))
    assert module.gallery_display_label(style_id) == expected_label
    assert manifest[0]["display_label"] == expected_label


def test_gallery_check_rejects_drift_in_every_recorded_provenance_class(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every claimed pipeline identity must be re-derived, not merely recorded."""
    module, manifest_path = _render_cached_single_style_gallery(tmp_path, monkeypatch)
    original = json.loads(manifest_path.read_text(encoding="utf-8"))
    previously_unchecked_fields = (
        "seed",
        "topology_mode",
        "target_population",
        "urbanized_area_km2",
        "network_schema_version",
        "network_fingerprint",
        "blocks_schema_version",
        "blocks_fingerprint",
        "compiled_schema_version",
        "compiled_fingerprint",
        "static_authority_schema_version",
        "static_authority_fingerprint",
        "zoning_placement_fingerprint",
        "node_count",
        "link_count",
    )

    for field_name in previously_unchecked_fields:
        mutated = json.loads(json.dumps(original))
        mutated[0][field_name] = f"tampered-{mutated[0][field_name]}"
        manifest_path.write_text(json.dumps(mutated), encoding="utf-8")
        assert module.check_gallery_artifacts(tmp_path) is False, field_name


def test_gallery_check_rejects_duplicate_and_extra_manifest_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dictionary collapse must not hide duplicate or undeclared style records."""
    module, manifest_path = _render_cached_single_style_gallery(tmp_path, monkeypatch)
    original = json.loads(manifest_path.read_text(encoding="utf-8"))
    extra = dict(original[0], style_id="undeclared_style")

    for mutated in (original + [dict(original[0])], original + [extra]):
        manifest_path.write_text(json.dumps(mutated), encoding="utf-8")
        assert module.check_gallery_artifacts(tmp_path) is False
