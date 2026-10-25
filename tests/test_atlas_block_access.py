from dataclasses import replace
import math
import pytest
from metroflow.terrain_city.block_access import build_access, segment_inside, Growth
from metroflow.terrain_city.network import Atlas, Block
from metroflow.terrain_city.landscape import Landscape, Polygon
from metroflow.environment.terrain import Terrain
from metroflow.restored_city import RoadMap, Junction, Section


def fixture():
    pts = ((0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0), (200.0, 0.0), (200.0, 100.0))
    nodes = tuple(Junction(str(i), (*p, 0.0)) for i, p in enumerate(pts))
    pairs = ((0, 1), (1, 2), (2, 3), (3, 0), (1, 4), (4, 5), (5, 2))
    sections = tuple(
        Section(
            f"s{i}",
            str(a),
            str(b),
            (nodes[a].xyz, nodes[b].xyz),
            "local",
            "surface",
            1,
            1,
            math.dist(pts[a], pts[b]),
            0.0,
        )
        for i, (a, b) in enumerate(pairs)
    )
    t = Terrain(2, 100.0, (0.0,) * 9)
    city = RoadMap("test", t, nodes, sections)
    blocks = (
        Block(
            "home", ("0", "1", "2", "3"), (50.0, 50.0), 10000.0, 400.0, "residential", 20, 0, 5, 0
        ),
        Block(
            "job", ("1", "4", "5", "2"), (150.0, 50.0), 10000.0, 400.0, "commercial", 0, 30, 0, 30
        ),
    )
    return Atlas(Landscape("flat", 17, t, (), ()), city, ("1",), (), blocks, {})


def test_private_access_has_real_length_and_uses_block_boundary():
    a = fixture()
    access, _ = build_access(a)
    assert len(access) == 2
    by = {x.block: x for x in access}
    assert by["home"].length_m == pytest.approx(math.sqrt(5000))
    assert by["home"].road_node in a.blocks[0].boundary
    assert by["home"].points[0][:2] == (50.0, 50.0)


def test_polygon_masks_not_empty_legacy_rectangles_control_access():
    a = fixture()
    water = Polygon("hidden water", ((40.0, 40.0), (60.0, 40.0), (60.0, 60.0), (40.0, 60.0)))
    a = replace(a, landscape=replace(a.landscape, water=(water,)))
    access, reasons = build_access(a)
    assert "home" not in {x.block for x in access}
    assert dict(reasons)["home"] == "polygon_exclusion"
    assert not a.roadmap.terrain.water


def test_concave_boundary_does_not_allow_shortcut_outside_block():
    shape = Polygon("L", ((0.0, 0.0), (3.0, 0.0), (3.0, 1.0), (1.0, 1.0), (1.0, 3.0), (0.0, 3.0)))
    assert segment_inside((0.5, 0.5), (3.0, 1.0), shape)
    assert not segment_inside((2.5, 0.5), (0.5, 2.5), shape)


def test_existing_residents_preserved_newcomers_need_built_access_and_capacity():
    model = Growth(fixture(), ("job",))
    s = model.initial()
    a, receipt = model.step(s, 10, budget_m=0.0)
    assert a.residents == s.residents and a.pending == 10 and a.offered == 10
    b, receipt = model.step(a, 20, budget_m=100.0)
    assert b.residents == (20, 0) and b.pending == 15 and b.offered == 30
    assert b.built_m == pytest.approx(math.sqrt(5000))
    assert s.residents == (5, 0) and s.epoch == 0
    c, r = model.step(b, 0, budget_m=100.0)
    assert c.built_m == b.built_m and not r["new_access"]


def test_state_is_bound_to_geometry_and_polygon_identity():
    a = fixture()
    m = Growth(a, ("job",))
    s = m.initial()
    b = replace(
        a,
        landscape=replace(
            a.landscape,
            protected=(
                Polygon("reserve", ((10.0, 10.0), (20.0, 10.0), (20.0, 20.0), (10.0, 20.0))),
            ),
        ),
    )
    with pytest.raises(ValueError, match="identity"):
        Growth(b, ("job",)).step(s, 0)
