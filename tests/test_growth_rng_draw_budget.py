"""Pin the growth path's stochastic surface before PR-B rewrites it.

PR-B changes how streets are seeded, split and contacted, which changes how many
random values the walk consumes. That is expected. What is not acceptable is the
number changing without anyone noticing, because the draw budget is what binds a
seed to a map: any change to it silently re-rolls every generated city, and the
replay fingerprint contract depends on that binding.

So the count is pinned here, on the CURRENT tree. When PR-B moves it, this test
goes red and the diff has to carry a written justification for the new number.
Pinning it after the rewrite would prove nothing — it would simply record
whatever PR-B happened to do.

This passes on arrival by construction. It is a characterization lock, not a
red-green cycle.
"""

from __future__ import annotations

from collections import Counter

import pytest

# Measured on the current tree at 367f25d. Not a target, not a threshold — a
# record of what the walk consumes today.
PINNED_DRAWS: dict[str, dict[str, int]] = {
    "grid_core/17": {"normal": 22141, "random": 5604, "uniform": 2392},
}


class _CountingGenerator:
    """Delegates every draw to the real generator and tallies the method used.

    Wrapping rather than reimplementing matters: the values handed to the
    generator must be bit-identical to an unwrapped run, or the pin would
    describe a map nobody generates.
    """

    def __init__(self, inner, counts: Counter) -> None:
        self._inner = inner
        self._counts = counts

    def __getattr__(self, name: str):
        attribute = getattr(self._inner, name)
        if not callable(attribute):
            return attribute

        def _counted(*args, **kwargs):
            self._counts[name] += 1
            return attribute(*args, **kwargs)

        return _counted


def _draw_counts(*, style_id: str, seed: int) -> tuple[Counter, object]:
    import numpy as np

    from metroflow.city import growth_fabric
    from metroflow.city.terrain_field import build_terrain_field
    from metroflow.city.urban_form import build_urban_form_field

    counts: Counter = Counter()
    real_default_rng = np.random.default_rng

    def _patched(*args, **kwargs):
        return _CountingGenerator(real_default_rng(*args, **kwargs), counts)

    terrain = build_terrain_field(width=6000, height=6000, seed=seed, style_id=style_id)
    urban_form = build_urban_form_field(terrain=terrain, style_id=style_id, seed=seed)

    # Patch only for the growth call: terrain and urban form draw their own
    # randomness and are not what this test is pinning.
    original = growth_fabric.np.random.default_rng
    growth_fabric.np.random.default_rng = _patched  # type: ignore[assignment]
    try:
        network = growth_fabric.grow_street_network(
            terrain=terrain, urban_form=urban_form, seed=seed
        )
    finally:
        growth_fabric.np.random.default_rng = original  # type: ignore[assignment]

    return counts, network


@pytest.mark.parametrize("case", sorted(PINNED_DRAWS))
def test_growth_consumes_a_pinned_number_of_random_draws(case: str) -> None:
    style_id, seed = case.split("/")

    counts, _ = _draw_counts(style_id=style_id, seed=int(seed))

    assert dict(counts) == PINNED_DRAWS[case], (
        f"{case}: growth's random-draw budget changed. Every seeded map moves "
        f"with it. Update PINNED_DRAWS only alongside a written justification."
    )


def test_counting_wrapper_does_not_perturb_the_generated_map() -> None:
    """If wrapping changed the map, the pin above would describe a fiction."""

    from metroflow.city.growth_fabric import compile_grown_network

    _, wrapped = _draw_counts(style_id="grid_core", seed=17)

    from metroflow.benchmarks.morphology_control_table import build_arm_topology

    unwrapped = build_arm_topology(arm="growth_fabric_v1", style_id="grid_core", seed=17)

    assert (
        compile_grown_network(wrapped.streets).road_geometry.fingerprint
        == unwrapped.road_geometry.fingerprint
    )
