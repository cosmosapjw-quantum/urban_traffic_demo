"""Two structural gaps visible in the diagnostic plot.

1. Redundant roads. Growth seeds a new street without checking whether one of
   the same class already occupies that ground. The snap radius is a fraction
   of a step (~13 m), far too tight to merge near-parallel streets, so they run
   alongside each other instead. Measured on `polycentric_tod`/17: 11,615
   redundant local streets across 19,650 sampled 25 m cells, a ratio of 0.59.
   This inflates street length without adding intersections, which is exactly
   why length density sits ~2.5x above the OSM-measured band while
   intersection density is inside it.

2. No bypass. Every expressway is seeded at a boundary gateway and grown toward
   the nearest centre, so through traffic has no route that avoids the core.
   Real cities carry a ring or bypass corridor.
"""

from __future__ import annotations

import math
from collections import defaultdict

import pytest


def _network(style_id="polycentric_tod", seed=17):
    from metroflow.city.growth_fabric import grow_street_network
    from metroflow.city.terrain_field import build_terrain_field
    from metroflow.city.urban_form import build_urban_form_field

    terrain = build_terrain_field(width=6000, height=6000, seed=seed, style_id=style_id)
    urban_form = build_urban_form_field(terrain=terrain, style_id=style_id, seed=seed)
    return grow_street_network(terrain=terrain, urban_form=urban_form, seed=seed), urban_form


def _redundancy_ratio(streets, road_class, *, cell_m=25.0, parallel_deg=30.0):
    """Share of occupied cells holding a near-PARALLEL duplicate of this class.

    Rasterised: every cell a segment crosses is credited, not just the one
    containing its left endpoint. The endpoint version was not
    segmentation-invariant -- reversing every polyline, a geometric no-op, moved
    it 0.2270 -> 0.1299 and flipped this file's own assertion. 69.2% of each
    segment's ground went unsampled.

    Direction is essential either way. Counting any two same-class streets in a
    cell also counts a street and the cross-street it legitimately meets, so a
    plain co-occupancy count reports junctions as duplication.
    """

    buckets = defaultdict(list)
    for street in streets:
        if street.road_class.value != road_class:
            continue
        for left, right in zip(street.points_m, street.points_m[1:]):
            heading = math.atan2(right[1] - left[1], right[0] - left[0])
            samples = max(int(math.dist(left, right) / (cell_m / 4.0)) + 1, 2)
            for index in range(samples + 1):
                t = index / samples
                point = (left[0] + t * (right[0] - left[0]), left[1] + t * (right[1] - left[1]))
                key = (int(point[0] // cell_m), int(point[1] // cell_m))
                buckets[key].append((street.street_id, heading))
    if not buckets:
        return 0.0

    tolerance = math.radians(parallel_deg)
    redundant = 0
    for entries in buckets.values():
        if len({street_id for street_id, _ in entries}) < 2:
            continue
        parallel_pair = False
        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                if entries[i][0] == entries[j][0]:
                    continue
                delta = abs(math.atan2(
                    math.sin(entries[i][1] - entries[j][1]),
                    math.cos(entries[i][1] - entries[j][1]),
                ))
                if min(delta, math.pi - delta) <= tolerance:
                    parallel_pair = True
                    break
            if parallel_pair:
                break
        redundant += parallel_pair
    return redundant / len(buckets)


def test_the_duplication_metric_is_invariant_to_polyline_reversal() -> None:
    """Reversing point order is a geometric no-op and must not move the number.

    The endpoint-bucketed version failed this: 0.2270 as generated, 0.1299
    reversed, which was enough to flip the assertion below.
    """

    from dataclasses import replace

    network, _ = _network()
    reversed_streets = tuple(
        replace(street, points_m=tuple(reversed(street.points_m)))
        for street in network.streets
    )

    assert _redundancy_ratio(network.streets, "local") == pytest.approx(
        _redundancy_ratio(reversed_streets, "local"), abs=0.005
    )


def test_local_streets_do_not_pile_up_on_the_same_ground() -> None:
    """The trade-off this file recorded as unreachable is now reached.

    The strict xfail here claimed: "No setting reaches density 5.3-13.9, dead
    ends < 0.3456 and dup < 0.15 together, because rejecting a seed leaves the
    street that did grow dangling at its far end." That is refuted, and by the
    mechanism it named. Measured over 6 styles x 3 seeds after branch anchors
    became junctions, crossings became junctions, the branch-spacing units were
    made consistent, and dangling tips were extended to cross:

        density        8.06 - 11.24 km/km2   (real 7.44 - 17.77, 18/18 inside)
        dead-end share 0.152 - 0.258         (real max 0.288, 18/18 under)
        mean degree    2.830 - 3.097         (real 2.55 - 3.55)
        duplication    0.068 - 0.082         (threshold 0.15)

    Note the xfail was also measuring with the reversal-dependent metric, so its
    own numbers were not stable.
    """

    network, _ = _network()

    ratio = _redundancy_ratio(network.streets, "local")

    assert ratio < 0.15, f"local streets are duplicated on the same ground: ratio {ratio:.2f}"


def test_arterials_and_collectors_do_not_pile_up_either() -> None:
    """Only local fabric duplicates; the upper tiers are already clean."""

    network, _ = _network()

    assert _redundancy_ratio(network.streets, "arterial") < 0.12
    assert _redundancy_ratio(network.streets, "collector") < 0.12


def test_expressways_are_not_seeded_three_deep_from_one_gateway() -> None:
    """Fanned seeds from a single point overlap for most of their length."""

    network, _ = _network()
    expressways = [s for s in network.streets if s.road_class.value == "expressway"]
    starts = defaultdict(int)
    for street in expressways:
        starts[(round(street.points_m[0][0] / 50.0), round(street.points_m[0][1] / 50.0))] += 1

    assert max(starts.values()) <= 1, f"overlapping expressway seeds: {dict(starts)}"


def test_a_bypass_lets_through_traffic_avoid_the_core() -> None:
    """At least one expressway must stay clear of the primary centre."""

    network, urban_form = _network()
    primary = min(urban_form.centers, key=lambda c: c.center_id)
    core = (float(primary.x_m), float(primary.y_m))

    expressways = [s for s in network.streets if s.road_class.value == "expressway"]
    assert expressways, "no expressways at all"

    # A bypass keeps its whole length well outside the core.
    clearances = [
        min(math.dist(point, core) for point in street.points_m) for street in expressways
    ]
    assert max(clearances) > 1200.0, (
        f"every expressway runs through the core; max clearance {max(clearances):.0f} m"
    )
