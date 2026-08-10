"""Regression fixtures for final geometry repair in ``growth_fabric_v1``.

Each fixture uses the production fabric and builder, with literal geometry that
would otherwise be obscured by a full stochastic growth run.
"""

from __future__ import annotations

from contextlib import contextmanager
import signal

import pytest


def _street(
    fabric,
    start: tuple[float, float],
    *points: tuple[float, float],
    layer: int = 0,
) -> int:
    from metroflow.city.graph import RoadClass

    street_id = fabric.open_street(RoadClass.LOCAL, start, layer=layer)
    for point in points:
        fabric.extend(street_id, point)
    return street_id


@contextmanager
def _wall_clock_limit(seconds: float):
    """Turn an accidental repair loop into a deterministic test failure."""

    previous = signal.getsignal(signal.SIGALRM)

    def expire(_signum, _frame):
        raise TimeoutError("crossing repair did not terminate")

    signal.signal(signal.SIGALRM, expire)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0.0)
        signal.signal(signal.SIGALRM, previous)


def test_crossing_search_indexes_every_cell_in_a_long_segment_bbox() -> None:
    """Endpoint/midpoint-only buckets miss the real cell containing (100, 100)."""

    from metroflow.city.growth_fabric import _Fabric, _find_crossings

    fabric = _Fabric(cell_m=40.0)
    diagonal = _street(fabric, (0.0, 0.0), (240.0, 240.0))
    vertical = _street(fabric, (100.0, -40.0), (100.0, 300.0))

    assert _find_crossings(fabric) == [(diagonal, vertical, (100.0, 100.0))]


def test_crossing_repair_reaches_a_fixed_point_for_seven_street_pair_crossings() -> None:
    """A six-round cap leaves the seventh proper crossing unregistered."""

    from metroflow.city.growth_fabric import (
        _Fabric,
        _find_crossings,
        _register_remaining_crossings,
    )

    fabric = _Fabric(cell_m=40.0)
    horizontal = _street(fabric, (0.0, 0.0), (800.0, 0.0))
    zigzag = _street(
        fabric,
        (50.0, -10.0),
        (100.0, 10.0),
        (150.0, -10.0),
        (200.0, 10.0),
        (250.0, -10.0),
        (300.0, 10.0),
        (350.0, -10.0),
        (400.0, 10.0),
    )

    assert _register_remaining_crossings(fabric) == 7
    assert _find_crossings(fabric) == []
    shared = set(fabric.builder.node_ids_of(horizontal)) & set(fabric.builder.node_ids_of(zigzag))
    assert len(shared) == 7


def test_crossing_repair_fails_closed_when_a_welded_shared_node_cannot_resolve_a_crossing() -> None:
    """A truthy no-op bind must not restart repair forever."""

    from metroflow.city.growth_fabric import _Fabric, _register_remaining_crossings
    from metroflow.city.graph import RoadClass

    fabric = _Fabric(cell_m=40.0)
    horizontal = _street(fabric, (0.0, 0.0), (50.0, 0.0), (100.0, 0.0))
    shared_node = fabric.builder.node_ids_of(horizontal)[1]
    bent_vertical = fabric.open_street(RoadClass.LOCAL, (50.0, 0.0), start_node_id=shared_node)
    fabric.extend(bent_vertical, (50.1, -10.0))
    fabric.extend(bent_vertical, (50.1, 10.0))

    with _wall_clock_limit(0.25), pytest.raises(RuntimeError, match="no progress"):
        _register_remaining_crossings(fabric)


def test_incidence_compilation_preserves_the_authoritative_street_layer() -> None:
    """A nonzero builder grade must survive into the physical centerline."""

    from metroflow.city.growth_fabric import (
        GrownNetwork,
        GrownStreet,
        _Fabric,
        compile_grown_network,
    )
    from metroflow.city.graph import RoadClass

    fabric = _Fabric(cell_m=40.0)
    elevated = _street(fabric, (0.0, 0.0), (100.0, 0.0), layer=3)
    network = GrownNetwork(
        streets=(
            GrownStreet(
                street_id=elevated,
                road_class=RoadClass.LOCAL,
                points_m=fabric.points_of(elevated),
            ),
        ),
        dead_end_count=0,
        junction_count=0,
        topology=fabric.builder,
    )

    topology = compile_grown_network(network)

    assert len(topology.road_geometry.centerlines) == 1
    assert topology.road_geometry.centerlines[0].layer == 3


def test_segment_supercover_is_linear_for_a_forty_kilometre_diagonal() -> None:
    """A 40 km diagonal must not materialize the million-cell bbox rectangle."""

    from metroflow.city.growth_fabric import _segment_supercover_cells

    cells = tuple(_segment_supercover_cells((0.0, 0.0), (40_000.0, 40_000.0), 40.0))

    assert cells[0] == (0, 0)
    assert cells[-1] == (1000, 1000)
    assert len(cells) <= 3_005


def test_finalization_registers_an_exact_endpoint_to_foreign_segment_touch() -> None:
    """A vertical tip at a horizontal interior must become one shared node."""

    from metroflow.city.growth_fabric import _Fabric, _finalize_geometry_repairs

    fabric = _Fabric(cell_m=40.0)
    target = _street(fabric, (0.0, 0.0), (100.0, 0.0))
    tip = _street(fabric, (50.0, -40.0), (50.0, 0.0))

    assert _finalize_geometry_repairs(fabric) == 1
    shared = set(fabric.builder.node_ids_of(target)) & set(fabric.builder.node_ids_of(tip))
    assert len(shared) == 1
    junction = shared.pop()
    assert fabric.builder.point_of(junction) == (50.0, 0.0)


def test_finalization_does_not_snap_near_parallel_or_grade_separated_tips() -> None:
    """Only same-layer T contacts, not nearby parallels or bridges, are junctions."""

    from metroflow.city.growth_fabric import _Fabric, _finalize_geometry_repairs

    fabric = _Fabric(cell_m=40.0)
    target = _street(fabric, (0.0, 0.0), (100.0, 0.0))
    parallel = _street(fabric, (30.0, 0.10), (50.0, 0.10))
    bridge = _street(fabric, (75.0, -40.0), (75.0, 0.0), layer=1)

    assert _finalize_geometry_repairs(fabric) == 0
    target_nodes = set(fabric.builder.node_ids_of(target))
    assert not target_nodes & set(fabric.builder.node_ids_of(parallel))
    assert not target_nodes & set(fabric.builder.node_ids_of(bridge))
