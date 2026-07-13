from __future__ import annotations

import subprocess
import sys

import numpy as np
import pytest


def test_terrain_field_is_bounded_read_only_and_deterministic() -> None:
    from metroflow.city.terrain_field import build_terrain_field

    first = build_terrain_field(
        width=5_400,
        height=4_600,
        seed=17,
        style_id="river_constrained",
    )
    second = build_terrain_field(
        width=5_400,
        height=4_600,
        seed=17,
        style_id="river_constrained",
    )

    assert first.shape == second.shape
    assert max(first.shape) == 256
    assert first.elevation_m.dtype == np.float32
    assert first.slope_rise_per_m.dtype == np.float32
    assert first.water_mask.dtype == np.bool_
    assert first.buildable_mask.dtype == np.bool_
    assert not first.elevation_m.flags.writeable
    assert not first.water_mask.flags.writeable
    assert first.fingerprint == second.fingerprint
    assert np.array_equal(first.elevation_m, second.elevation_m)
    assert np.count_nonzero(first.water_mask) > 0
    assert not np.any(first.water_mask & first.buildable_mask)


def test_terrain_field_changes_with_seed_and_style() -> None:
    from metroflow.city.terrain_field import build_terrain_field

    baseline = build_terrain_field(width=4_400, height=4_000, seed=17)
    changed_seed = build_terrain_field(width=4_400, height=4_000, seed=18)
    changed_style = build_terrain_field(
        width=4_400,
        height=4_000,
        seed=17,
        style_id="river_constrained",
    )

    assert baseline.fingerprint != changed_seed.fingerprint
    assert baseline.fingerprint != changed_style.fingerprint

    with pytest.raises(ValueError, match="style_id"):
        build_terrain_field(
            width=4_400,
            height=4_000,
            seed=17,
            style_id="imaginary_city",
        )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    (
        ({"width": 0, "height": 100, "seed": 1}, "width"),
        ({"width": 100, "height": -1, "seed": 1}, "height"),
        ({"width": 100, "height": 100, "seed": 1, "max_grid_size": 15}, "max_grid_size"),
        ({"width": 100, "height": 100, "seed": 1, "max_grid_size": 257}, "max_grid_size"),
    ),
)
def test_terrain_field_rejects_invalid_bounds(
    kwargs: dict[str, int],
    message: str,
) -> None:
    from metroflow.city.terrain_field import build_terrain_field

    with pytest.raises(ValueError, match=message):
        build_terrain_field(**kwargs)


@pytest.mark.parametrize(
    "style_id",
    (
        "ring_radial",
        "grid_core",
        "polycentric_tod",
        "river_constrained",
        "superblock_mixed",
        "organic",
    ),
)
def test_urban_form_centers_and_fields_respect_terrain(style_id: str) -> None:
    from metroflow.city.terrain_field import build_terrain_field
    from metroflow.city.urban_form import build_urban_form_field

    terrain = build_terrain_field(
        width=4_400,
        height=4_000,
        seed=29,
        style_id=style_id,
        max_grid_size=96,
    )
    urban_form = build_urban_form_field(
        terrain=terrain,
        style_id=style_id,
        seed=29,
    )

    assert urban_form.development_intensity.shape == terrain.shape
    assert np.min(urban_form.development_intensity) >= 0.0
    assert np.max(urban_form.development_intensity) <= 1.0
    assert np.all(urban_form.development_intensity[terrain.water_mask] == 0.0)
    norm = np.hypot(urban_form.orientation_x, urban_form.orientation_y)
    assert np.allclose(norm, 1.0, atol=1e-6)
    assert not urban_form.development_intensity.flags.writeable
    assert not urban_form.orientation_x.flags.writeable
    assert urban_form.fingerprint == build_urban_form_field(
        terrain=terrain,
        style_id=style_id,
        seed=29,
    ).fingerprint
    for center in urban_form.centers:
        assert -terrain.width_m * 0.5 <= center.x_m <= terrain.width_m * 0.5
        assert -terrain.height_m * 0.5 <= center.y_m <= terrain.height_m * 0.5


def test_realistic_field_imports_do_not_load_optional_accelerators() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "import metroflow.city.terrain_field; "
                "import metroflow.city.urban_form; "
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
