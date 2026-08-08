"""The first branch anchor must use the same spacing as every later one.

`_branch_pass` draws the first anchor's offset from RAW class spacing while
every subsequent increment uses the SCALED, district-resolved spacing. Local raw
spacing is 82 m; scaled it is 246-990 m. Almost every local street is shorter
than the scaled increment, so each source receives exactly one anchor placed
25-82 m from its start and the increment never fires again -- the arc-spacing
discipline the configuration describes is not in effect at all.

That also decouples `spacing_scale` from what it claims to control, which
matters because its docstring calls it the OSM calibration knob.
"""

from __future__ import annotations

import numpy as np
import pytest


def _seeded_anchor_share(source_length_m: float, trials: int = 400) -> float:
    """Share of sources of this length that receive at least one anchor."""

    from metroflow.city.growth_fabric import GrowthConfig, _branch_pass, _Fabric
    from metroflow.city.graph import RoadClass

    cfg = GrowthConfig()
    seeded = 0
    for trial in range(trials):
        fabric = _Fabric(cell_m=max(cfg.local_step_m, 40.0))
        street = fabric.open_street(RoadClass.COLLECTOR, (0.0, 0.0))
        fabric.extend(street, (source_length_m, 0.0))

        anchors: list[tuple[float, float]] = []

        def grow(start, heading, road_class, step_m, turn_deg, max_steps, floor,
                 *, may_dead_end, occupancy_radius_m=0.0, terminate_on_contact=True,
                 start_node_id=None):
            anchors.append(start)
            return None

        _branch_pass(
            fabric,
            np.random.default_rng(trial),
            cfg,
            grow,
            source_classes=(RoadClass.COLLECTOR,),
            road_class=RoadClass.LOCAL,
            spacing_m=cfg.local_spacing_m,
            step_m=cfg.local_step_m,
            turn_deg=cfg.local_turn_deg,
            max_steps=cfg.local_max_steps,
            floor=0.0,
            cul_de_sac_share=0.0,
            profile_at=None,
            tier="local",
        )
        seeded += bool(anchors)
    return seeded / trials


def test_the_first_anchor_uses_the_scaled_spacing_like_every_other() -> None:
    """A source shorter than one scaled interval must often get NO anchor.

    With the phase drawn uniformly from [0.3, 1.0] x scaled spacing, a source of
    length L receives an anchor with probability (L/spacing - 0.3) / 0.7,
    clamped to [0, 1]. Drawing the phase from RAW spacing instead makes the
    maximum offset 82 m, so every source longer than that is seeded every time.
    """

    from metroflow.city.growth_fabric import GrowthConfig

    cfg = GrowthConfig()
    scaled = cfg.local_spacing_m * cfg.spacing_scale  # 246 m
    length = 150.0

    expected = (length / scaled - 0.3) / 0.7
    measured = _seeded_anchor_share(length)

    assert measured == pytest.approx(expected, abs=0.08), (
        f"a {length:.0f} m source is seeded {measured:.2%} of the time; the "
        f"scaled spacing of {scaled:.0f} m implies {expected:.2%}"
    )


def test_spacing_scale_actually_scales_the_spacing() -> None:
    """Doubling the knob must roughly halve how often a short source is seeded.

    The docstring calls `spacing_scale` the OSM calibration constant. If the
    first anchor ignores it, a source shorter than one interval is seeded
    regardless of what the knob says.
    """

    from metroflow.city.growth_fabric import GrowthConfig, _branch_pass, _Fabric
    from metroflow.city.graph import RoadClass

    def share(scale: float) -> float:
        cfg = GrowthConfig(spacing_scale=scale)
        seeded = 0
        trials = 300
        for trial in range(trials):
            fabric = _Fabric(cell_m=max(cfg.local_step_m, 40.0))
            street = fabric.open_street(RoadClass.COLLECTOR, (0.0, 0.0))
            fabric.extend(street, (300.0, 0.0))
            anchors: list = []

            def grow(start, *args, **kwargs):
                anchors.append(start)
                return None

            _branch_pass(
                fabric, np.random.default_rng(trial), cfg, grow,
                source_classes=(RoadClass.COLLECTOR,), road_class=RoadClass.LOCAL,
                spacing_m=cfg.local_spacing_m, step_m=cfg.local_step_m,
                turn_deg=cfg.local_turn_deg, max_steps=cfg.local_max_steps,
                floor=0.0, cul_de_sac_share=0.0, profile_at=None, tier="local",
            )
            seeded += bool(anchors)
        return seeded / trials

    tight = share(2.0)
    loose = share(6.0)

    assert tight > loose * 1.5, (
        f"spacing_scale barely moves seeding: 2.0 -> {tight:.2%}, 6.0 -> {loose:.2%}"
    )
