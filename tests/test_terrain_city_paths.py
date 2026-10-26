from collections import defaultdict
import math
from metroflow.terrain_city.network import generate, route_path


def test_positive_turn_cost_selects_less_fragmented_equal_length_arterial():
    xy = {
        "o": (0.0, 0.0),
        "a": (1.0, 0.0),
        "b": (1.0, 1.0),
        "c": (2.0, 1.0),
        "z": (2.0, 2.0),
        "d": (0.0, 2.0),
    }
    adj = defaultdict(list)
    for u, v in [("o", "a"), ("a", "b"), ("b", "c"), ("c", "z"), ("o", "d"), ("d", "z")]:
        e = u + v
        length = math.dist(xy[u], xy[v]) + (0.01 if e in ("od", "dz") else 0.0)
        adj[u].append((v, e, length))
        adj[v].append((u, e, length))
    assert route_path(adj, xy, "o", "z", 1.0) == ("od", "dz")


def test_radial_arterials_include_an_orbital_not_only_center_spokes():
    city = generate("radial", "flat", 4000.0, 20, population=20000)
    roads = [s for s in city.roadmap.sections if s.hierarchy == "arterial"]
    nodes = {v for s in roads for v in (s.start, s.end)}
    assert len(roads) - len(nodes) + 1 >= 1, "No primary orbital route around the center"
