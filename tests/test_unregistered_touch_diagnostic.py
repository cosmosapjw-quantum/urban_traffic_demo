"""Count places where two streets meet on the ground but not in the graph.

`count_interior_centerline_intersections` already catches streets that cross.
It does not catch the defect that actually dominates the grown fabric: a street
that *starts* on another street's interior. Nothing crosses there — one polyline
simply begins partway along another — so a crossing counter sees nothing, and a
junction detector keyed on shared vertices sees nothing either. The two streets
are drawn touching and are not connected.

That is the `growth_fabric.py:653` defect. This diagnostic is what makes it
countable, so PR-B has a number to move rather than an assertion to argue with.

Diagnostic only. Nothing gates on it in this change.
"""

from __future__ import annotations

import pytest


def _catalog(*centerlines):
    from metroflow.map.road_geometry import (
        CenterlineSource,
        RoadCenterline,
        RoadGeometryCatalog,
    )

    return RoadGeometryCatalog(
        centerlines=tuple(
            RoadCenterline(
                geometry_id=index,
                points_m=tuple(points),
                source=CenterlineSource.SYNTHETIC,
            )
            for index, points in enumerate(centerlines)
        ),
        assignments=(),
    )


def test_a_street_starting_on_another_streets_interior_is_counted() -> None:
    """The exact shape `_branch_pass` produces: child begins mid-parent."""

    from metroflow.map.road_geometry import count_unregistered_centerline_touches

    catalog = _catalog(
        [(0.0, 0.0), (100.0, 0.0)],  # parent, no vertex at x=50
        [(50.0, 0.0), (50.0, 50.0)],  # child starts on the parent's interior
    )

    assert count_unregistered_centerline_touches(catalog) == 1


def test_the_same_junction_is_not_counted_once_the_parent_carries_the_vertex() -> None:
    """This is precisely what PR-B changes, so the counter must go to zero."""

    from metroflow.map.road_geometry import count_unregistered_centerline_touches

    catalog = _catalog(
        [(0.0, 0.0), (50.0, 0.0), (100.0, 0.0)],  # parent split at the anchor
        [(50.0, 0.0), (50.0, 50.0)],
    )

    assert count_unregistered_centerline_touches(catalog) == 0


def test_streets_that_merely_pass_nearby_are_not_counted() -> None:
    """A tolerance this loose would report every parallel street as a junction."""

    from metroflow.map.road_geometry import count_unregistered_centerline_touches

    catalog = _catalog(
        [(0.0, 0.0), (100.0, 0.0)],
        [(50.0, 5.0), (50.0, 50.0)],  # 5 m clear of the parent
    )

    assert count_unregistered_centerline_touches(catalog, tolerance_m=0.25) == 0


def test_endpoint_to_endpoint_meetings_are_not_touches() -> None:
    """Two streets meeting end to end share a node; that is a real junction."""

    from metroflow.map.road_geometry import count_unregistered_centerline_touches

    catalog = _catalog(
        [(0.0, 0.0), (100.0, 0.0)],
        [(100.0, 0.0), (100.0, 50.0)],
    )

    assert count_unregistered_centerline_touches(catalog) == 0


def test_different_layers_do_not_touch() -> None:
    """A bridge over a road is not a junction, and the crossing counter agrees."""

    from metroflow.map.road_geometry import (
        CenterlineSource,
        RoadCenterline,
        RoadGeometryCatalog,
        count_unregistered_centerline_touches,
    )

    catalog = RoadGeometryCatalog(
        centerlines=(
            RoadCenterline(
                geometry_id=0,
                points_m=((0.0, 0.0), (100.0, 0.0)),
                source=CenterlineSource.SYNTHETIC,
                layer=0,
            ),
            RoadCenterline(
                geometry_id=1,
                points_m=((50.0, 0.0), (50.0, 50.0)),
                source=CenterlineSource.SYNTHETIC,
                layer=1,
            ),
        ),
        assignments=(),
    )

    assert count_unregistered_centerline_touches(catalog) == 0


def test_tolerance_must_be_finite_and_positive() -> None:
    from metroflow.map.road_geometry import count_unregistered_centerline_touches

    catalog = _catalog([(0.0, 0.0), (100.0, 0.0)])

    with pytest.raises(ValueError):
        count_unregistered_centerline_touches(catalog, tolerance_m=0.0)
    with pytest.raises(ValueError):
        count_unregistered_centerline_touches(catalog, tolerance_m=float("inf"))
