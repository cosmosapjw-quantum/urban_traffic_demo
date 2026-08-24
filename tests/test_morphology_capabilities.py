"""Behavioral contract for the public morphology capability authority."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

from metroflow.benchmarks.morphology_control_table import SkippedCase
from metroflow.city.generator_v2 import GeneratorV2
from metroflow.city.morphology_capabilities import (
    SkipReason,
    STYLE_IDS,
    get_style_capability,
    style_supports_arm,
    style_ids_for_arm,
)


def _gallery_module():
    path = Path(__file__).parents[1] / "tools" / "render_morphology_gallery.py"
    spec = importlib.util.spec_from_file_location("capability_gallery_under_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_gallery_labels_and_generator_style_ids_share_the_capability_authority() -> None:
    """The gallery may choose seeds, but it may not own labels or style support."""
    module = _gallery_module()

    assert {style_id for style_id, _seed in module.MORPHOLOGY_GALLERY_SET} == set(
        style_ids_for_arm("scalable_synthetic_v2")
    )
    for style_id, _seed in module.MORPHOLOGY_GALLERY_SET:
        assert module.gallery_display_label(style_id) == get_style_capability(style_id).public_label


def test_unknown_style_id_and_skip_reason_code_fail_closed() -> None:
    """Unsupported labels cannot silently become a new map or skipped datum."""
    with pytest.raises(ValueError, match="morphology style_id"):
        get_style_capability("unknown_style")
    with pytest.raises(ValueError):
        style_ids_for_arm("unknown_arm")
    with pytest.raises(ValueError, match="morphology style_id"):
        style_supports_arm("unknown_style", "standard")
    with pytest.raises(ValueError):
        SkipReason("UNKNOWN_SKIP_REASON")
    with pytest.raises(TypeError, match="SkipReason"):
        SkippedCase(
            arm="standard",
            case="grid_core/17",
            reason_code="UNSUPPORTED_ARM_STYLE",  # type: ignore[arg-type]
        )


def test_standard_support_is_exported_by_the_generator_capability_authority() -> None:
    """The benchmark preclassification cannot drift from the standard generator."""
    assert GeneratorV2.supported_standard_styles() == frozenset(
        style_ids_for_arm("standard")
    )


def test_legacy_archetypes_are_derived_from_the_capability_authority() -> None:
    """Legacy consumers retain their grammar without becoming a second style SSOT."""
    from metroflow.city.morphology_reference import (
        MORPHOLOGY_ARCHETYPES,
        get_morphology_archetype,
    )

    assert MORPHOLOGY_ARCHETYPES == STYLE_IDS
    organic = get_style_capability("organic")
    legacy_organic = get_morphology_archetype("organic")
    assert legacy_organic.center_pattern == organic.legacy_center_pattern
    assert legacy_organic.street_pattern == organic.legacy_street_pattern


def test_every_generator_preview_arm_has_a_declared_style_capability() -> None:
    """Supported preview modes cannot be omitted from the fixed registry."""
    assert set(style_ids_for_arm("sidecar_morphology")) == set(STYLE_IDS)
    assert set(style_ids_for_arm("sidecar_district_cells")) == set(STYLE_IDS)
