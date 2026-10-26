from types import SimpleNamespace
from metroflow.restored_city import Junction, Section, RoadMap
from metroflow.environment.terrain import Terrain
from metroflow.terrain_city.audit import geometry_audit
import math


def sample(a, b, c):
    nodes = (Junction("a", a), Junction("b", b), Junction("c", c))
    sections = (
        Section("ab", "a", "b", (a, b), "local", "surface", 1, 1, math.dist(a, b), 0.0),
        Section("cb", "c", "b", (c, b), "local", "surface", 1, 1, math.dist(c, b), 0.0),
    )
    road = RoadMap("audit", Terrain(1, 8000.0, (0.0,) * 4), nodes, sections)
    return SimpleNamespace(
        roadmap=road, blocks=(), summary={"requested_population": 0, "unplaced_residents": 0}
    )


def test_adjacent_straight_radial_segments_are_not_spurious_crossings():
    a = (2727.825913693228, 3085.2126492076554, 0.0)
    b = (2578.8041529048814, 2970.8642303586125, 0.0)
    c = (2429.7823921165354, 2856.515811509569, 0.0)
    assert not geometry_audit(sample(a, b, c))["illegal_projected_contacts"]


def test_same_ray_shared_endpoint_overlap_remains_illegal():
    s = sample((100.0, 0.0, 0.0), (0.0, 0.0, 0.0), (50.0, 0.0, 0.0))
    assert geometry_audit(s)["illegal_projected_contacts"]
