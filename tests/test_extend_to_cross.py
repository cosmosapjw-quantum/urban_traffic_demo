"""Dangling tips that stop just short of a street must reach it.

Fixing the branch-spacing units took density into the real band (7.75-10.91
against 7.44-17.77) and pushed dead-end share the other way, to 0.284-0.434
against an envelope ceiling of 0.3456 and a real-city maximum of 0.288. That is
the trade-off the strict xfail in `test_growth_redundancy_and_bypass.py`
recorded: seeding fewer streets leaves the ones that did grow dangling.

Extend-to-cross is what breaks it. A tip that terminated free and has a legal
target within a bounded reach is extended to meet it, converting a cul-de-sac
into a junction without seeding more street.

It is CONNECTIVITY REPAIR, not density control: it adds length, so it can only
ever push density up. That is why it runs after the spacing is right rather
than instead of fixing it.
"""

from __future__ import annotations

import pytest


def test_a_tip_stopping_short_of_a_street_is_extended_to_meet_it() -> None:
    from metroflow.city.growth_fabric import _extend_dangling_tips, _Fabric
    from metroflow.city.graph import RoadClass

    fabric = _Fabric(cell_m=40.0)
    target = fabric.open_street(RoadClass.COLLECTOR, (0.0, 0.0))
    fabric.extend(target, (200.0, 0.0))

    stub = fabric.open_street(RoadClass.LOCAL, (100.0, 80.0))
    fabric.extend(stub, (100.0, 20.0))  # stops 20 m short, pointing at the target

    extended = _extend_dangling_tips(fabric, max_reach_m=40.0)

    assert extended == 1
    tip_node = fabric.builder.node_ids_of(stub)[-1]
    assert len(fabric.builder.incident_street_ids(tip_node)) == 2
    assert fabric.point_of(tip_node) == pytest.approx((100.0, 0.0), abs=1e-6)


def test_a_tip_pointing_away_is_left_alone() -> None:
    """Extending backwards would invent a road nobody was building."""

    from metroflow.city.growth_fabric import _extend_dangling_tips, _Fabric
    from metroflow.city.graph import RoadClass

    fabric = _Fabric(cell_m=40.0)
    target = fabric.open_street(RoadClass.COLLECTOR, (0.0, 0.0))
    fabric.extend(target, (200.0, 0.0))

    stub = fabric.open_street(RoadClass.LOCAL, (100.0, 60.0))
    fabric.extend(stub, (100.0, 120.0))  # heading away from the target

    assert _extend_dangling_tips(fabric, max_reach_m=40.0) == 0


def test_a_target_beyond_the_reach_is_left_alone() -> None:
    from metroflow.city.growth_fabric import _extend_dangling_tips, _Fabric
    from metroflow.city.graph import RoadClass

    fabric = _Fabric(cell_m=40.0)
    target = fabric.open_street(RoadClass.COLLECTOR, (0.0, 0.0))
    fabric.extend(target, (200.0, 0.0))

    stub = fabric.open_street(RoadClass.LOCAL, (100.0, 200.0))
    fabric.extend(stub, (100.0, 120.0))  # 120 m short

    assert _extend_dangling_tips(fabric, max_reach_m=40.0) == 0


def test_a_grazing_target_is_rejected() -> None:
    """A near-parallel meeting is a duplicate road, not a junction.

    Without an angle window, a tip running alongside a street welds to it and
    the two become one corridor -- which is the duplication defect, arrived at
    from the repair side.
    """

    from metroflow.city.growth_fabric import _extend_dangling_tips, _Fabric
    from metroflow.city.graph import RoadClass

    fabric = _Fabric(cell_m=40.0)
    target = fabric.open_street(RoadClass.COLLECTOR, (0.0, 0.0))
    fabric.extend(target, (200.0, 0.0))

    stub = fabric.open_street(RoadClass.LOCAL, (40.0, 10.0))
    fabric.extend(stub, (120.0, 6.0))  # ~3 degrees off parallel

    assert _extend_dangling_tips(fabric, max_reach_m=40.0) == 0


def test_extension_is_deterministic_regardless_of_discovery_order() -> None:
    """Shortest first, ties broken by id, so the result cannot depend on chance."""

    from metroflow.city.growth_fabric import _extend_dangling_tips, _Fabric
    from metroflow.city.graph import RoadClass

    def build():
        fabric = _Fabric(cell_m=40.0)
        spine = fabric.open_street(RoadClass.COLLECTOR, (0.0, 0.0))
        fabric.extend(spine, (400.0, 0.0))
        for x in (80.0, 160.0, 240.0):
            stub = fabric.open_street(RoadClass.LOCAL, (x, 90.0))
            fabric.extend(stub, (x, 25.0))
        return fabric

    first = build()
    second = build()
    assert _extend_dangling_tips(first, max_reach_m=40.0) == 3
    assert _extend_dangling_tips(second, max_reach_m=40.0) == 3

    assert [first.point_of(n) for n in first.builder.node_ids_of(0)] == [
        second.point_of(n) for n in second.builder.node_ids_of(0)
    ]


def test_the_pass_reduces_dead_ends_on_a_real_map() -> None:
    """The point of the exercise, measured end to end."""

    from metroflow.benchmarks.morphology_control_table import build_arm_topology

    topology = build_arm_topology(
        arm="growth_fabric_v1", style_id="grid_core", seed=17
    )
    neighbours: dict[int, set[int]] = {}
    for link in topology.links:
        neighbours.setdefault(int(link.src_node_id), set()).add(int(link.dst_node_id))
    share = sum(1 for v in neighbours.values() if len(v) == 1) / len(topology.nodes)

    # Real cities reach 0.288 at most (Charlotte, the most sprawling extract).
    assert share <= 0.288, f"dead-end share {share:.3f} exceeds every real extract"
