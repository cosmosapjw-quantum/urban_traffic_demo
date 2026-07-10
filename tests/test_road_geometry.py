from __future__ import annotations

import math

import pytest


def test_road_centerline_validates_meter_geometry_and_fingerprint() -> None:
    from metroflow.map.road_geometry import CenterlineSource, RoadCenterline

    centerline = RoadCenterline(
        geometry_id=7,
        points_m=((0.0, 0.0), (3.0, 4.0), (9.0, 4.0)),
        source=CenterlineSource.SYNTHETIC,
        source_ref="corridor-7",
        layer=1,
        corridor_id=12,
    )

    assert centerline.length_m == pytest.approx(11.0)
    assert len(centerline.fingerprint) == 64
    assert centerline.fingerprint == RoadCenterline(
        geometry_id=7,
        points_m=((0.0, 0.0), (3.0, 4.0), (9.0, 4.0)),
        source="synthetic",
        source_ref="corridor-7",
        layer=1,
        corridor_id=12,
    ).fingerprint
    assert RoadCenterline(
        geometry_id=8,
        points_m=((-0.0, 0.0), (1.0, -0.0)),
    ).fingerprint == RoadCenterline(
        geometry_id=8,
        points_m=((0.0, -0.0), (1.0, 0.0)),
    ).fingerprint


@pytest.mark.parametrize(
    ("points", "message"),
    [
        (((0.0, 0.0),), "at least two"),
        (((0.0, 0.0), (0.0, 0.0)), "consecutive"),
        (((0.0, 0.0), (math.inf, 1.0)), "finite"),
        (((0.0,), (1.0, 1.0)), "exactly two"),
        (((0.0, "north"), (1.0, 1.0)), "exactly two"),
    ],
)
def test_road_centerline_rejects_invalid_geometry(points, message) -> None:
    from metroflow.map.road_geometry import RoadCenterline

    with pytest.raises(ValueError, match=message):
        RoadCenterline(geometry_id=1, points_m=points)


def test_geometry_catalog_orients_shared_bidirectional_centerline() -> None:
    from metroflow.city.graph import Node, RoadClass, RoadLink
    from metroflow.map.road_geometry import build_endpoint_geometry_catalog

    nodes = (
        Node(10, x=0.0, y=0.0),
        Node(20, x=100.0, y=0.0),
        Node(30, x=150.0, y=50.0),
    )
    links = (
        RoadLink(101, 10, 20, RoadClass.ARTERIAL, 100.0, 15.0, 10.0, lanes=2),
        RoadLink(102, 20, 10, RoadClass.ARTERIAL, 100.0, 15.0, 10.0, lanes=2),
        RoadLink(103, 20, 30, RoadClass.RAMP, 70.71, 12.0, 5.0),
    )

    catalog = build_endpoint_geometry_catalog(nodes=nodes, links=links)

    assert len(catalog.centerlines) == 2
    assert len(catalog.assignments) == 3
    assert catalog.assignment_for_link(101).geometry_id == catalog.assignment_for_link(
        102
    ).geometry_id
    assert catalog.points_for_link(101) == ((0.0, 0.0), (100.0, 0.0))
    assert catalog.points_for_link(102) == ((100.0, 0.0), (0.0, 0.0))
    assert catalog.points_for_link(103) == ((100.0, 0.0), (150.0, 50.0))
    assert len(catalog.fingerprint) == 64


def test_geometry_catalog_rejects_duplicate_and_missing_references() -> None:
    from metroflow.map.road_geometry import (
        LinkGeometryAssignment,
        RoadCenterline,
        RoadGeometryCatalog,
    )

    centerline = RoadCenterline(geometry_id=1, points_m=((0.0, 0.0), (1.0, 0.0)))
    with pytest.raises(ValueError, match="duplicate geometry_id"):
        RoadGeometryCatalog(centerlines=(centerline, centerline), assignments=())
    with pytest.raises(ValueError, match="missing geometry_id"):
        RoadGeometryCatalog(
            centerlines=(centerline,),
            assignments=(LinkGeometryAssignment(link_id=3, geometry_id=99),),
        )
    with pytest.raises(ValueError, match="duplicate link_id"):
        RoadGeometryCatalog(
            centerlines=(centerline,),
            assignments=(
                LinkGeometryAssignment(link_id=3, geometry_id=1),
                LinkGeometryAssignment(link_id=3, geometry_id=1),
            ),
        )
    with pytest.raises(TypeError):
        catalog = RoadGeometryCatalog(centerlines=(centerline,), assignments=())
        catalog._geometry_by_id[2] = centerline
    with pytest.raises(TypeError):
        catalog._assignment_by_link_id[3] = LinkGeometryAssignment(
            link_id=3,
            geometry_id=1,
        )


def test_endpoint_geometry_catalog_rejects_ambiguous_parallel_links() -> None:
    from metroflow.city.graph import Node, RoadClass, RoadLink
    from metroflow.map.road_geometry import build_endpoint_geometry_catalog

    nodes = (Node(1, x=0.0, y=0.0), Node(2, x=10.0, y=0.0))
    links = (
        RoadLink(10, 1, 2, RoadClass.LOCAL, 10.0, 9.0, 4.0),
        RoadLink(11, 1, 2, RoadClass.LOCAL, 10.0, 9.0, 4.0),
    )

    with pytest.raises(ValueError, match="ambiguous parallel link pairing"):
        build_endpoint_geometry_catalog(nodes=nodes, links=links)


def test_endpoint_geometry_catalog_is_deterministic_for_input_order() -> None:
    from metroflow.city.graph import Node, RoadClass, RoadLink
    from metroflow.map.road_geometry import build_endpoint_geometry_catalog

    nodes = (Node(5, x=10.0, y=20.0), Node(2, x=-5.0, y=7.0))
    links = (
        RoadLink(9, 5, 2, RoadClass.LOCAL, 20.0, 9.0, 4.0),
        RoadLink(3, 2, 5, RoadClass.LOCAL, 20.0, 9.0, 4.0),
    )

    first = build_endpoint_geometry_catalog(nodes=nodes, links=links)
    second = build_endpoint_geometry_catalog(
        nodes=tuple(reversed(nodes)),
        links=tuple(reversed(links)),
    )

    assert first == second
    assert first.fingerprint == second.fingerprint
