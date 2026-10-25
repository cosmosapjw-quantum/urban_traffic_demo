import math
from collections import Counter
import pytest
from metroflow.restored_city import generate, STYLES


@pytest.mark.parametrize("style", STYLES)
def test_restored_styles_have_physical_hierarchy_and_cross_bank_bridges(style):
    city = generate(style, n=12, seed=17, interchanges=False)
    assert len(city.sections) > 60, "Requested original road grammar has no usable network"
    assert {"arterial", "collector", "local"} <= {s.hierarchy for s in city.sections}
    assert len({s.failure_group for s in city.sections if s.facility == "bridge"}) >= 2
    by = {n.id: n for n in city.nodes}
    for s in city.sections:
        assert s.points[0] == by[s.start].xyz and s.points[-1] == by[s.end].xyz
        assert s.length_m >= math.dist(s.points[0], s.points[-1]) - 1e-8
        assert s.max_grade <= 0.12 + 1e-10


def test_directed_interchange_has_no_surface_to_mainline_endpoint_merge():
    city = generate("grid_core", n=12, seed=17, interchanges=True)
    roles = Counter(s.facility for s in city.sections)
    assert roles["mainline"] > 0 and roles["ramp"] >= 4
    by = {n.id: n for n in city.nodes}
    for s in city.sections:
        if s.facility == "mainline":
            assert by[s.start].layer == by[s.end].layer == 1
            assert s.backward_lanes == 0
        elif s.facility == "ramp":
            assert s.backward_lanes == 0
            expected = (0, 1) if s.ramp_purpose == "on_ramp" else (1, 0)
            assert (by[s.start].layer, by[s.end].layer) == expected


def test_ring_ramps_do_not_cross_opposing_carriageway_without_clearance():
    from metroflow.restored_geometry import crossing_audit

    audit = crossing_audit(generate("ring_radial", n=12, seed=17))
    assert not audit["illegal"], audit["illegal"]


def test_no_ramp_passes_below_the_continuous_hillside():
    from metroflow.restored_geometry import elevation

    c = generate("ring_radial", n=12, seed=17)
    for s in c.sections:
        if s.facility == "surface":
            continue
        for a, b in zip(s.points, s.points[1:]):
            for k in range(33):
                u = k / 32
                p = tuple(x + (y - x) * u for x, y in zip(a, b))
                assert p[2] >= elevation(c.terrain, *p[:2]) - 1e-8, (s.id, p)


def test_ramp_tangents_match_directed_mainline_not_a_right_angle():
    c = generate("organic", n=12, seed=17)
    for s in c.sections:
        if s.facility != "ramp":
            continue
        p, q = s.points[-2:] if s.ramp_purpose == "on_ramp" else s.points[:2]
        sign = 1 if ":0:" in s.id else -1
        assert sign * (q[0] - p[0]) / math.dist(p[:2], q[:2]) >= 0.9, (s.id, p, q)


def test_raster_midsegment_grade_not_endpoint_secant_and_length_checked():
    from metroflow.environment.terrain import Terrain
    from metroflow.restored_geometry import ground_profile, minimum_ground_gap

    t = Terrain(1, 100.0, (0.0, 0.0, 0.0, 100.0))
    _, length, grade = ground_profile(t, ((0.0, 0.0), (100.0, 100.0)))
    assert grade == pytest.approx(math.sqrt(2))
    exact = 0.5 * (math.sqrt(60000.0) + 100.0 * math.asinh(math.sqrt(2)))
    assert length == pytest.approx(exact, abs=0.002)
    hill = Terrain(1, 100.0, (0.0, 100.0, 100.0, 0.0))
    assert minimum_ground_gap(hill, ((0.0, 0.0, 0.0), (100.0, 100.0, 0.0))) == pytest.approx(-50.0)


@pytest.mark.parametrize("style", STYLES)
def test_real_frontage_never_attaches_population_to_a_viaduct(style):
    from metroflow.restored_zoning import attach_zones

    r = generate(style)
    city, distances = attach_zones(r, 30000, 12000)
    by = {n.id: n for n in r.nodes}
    assert sum(z.residents for z in city.zones) == 30000
    assert sum(z.jobs for z in city.zones) == 12000
    assert all(by[z.access_node].layer == 0 for z in city.zones if z.residents or z.jobs)
    assert max(distances.values()) <= 500
    assert any(z.use == "industrial" for z in city.zones)


def test_unknown_style_not_silently_substituted():
    with pytest.raises(ValueError):
        generate("polycentric_tod_not_yet_ported")


def test_collinear_road_overlap_is_not_misclassified_as_grade_separation():
    from metroflow.restored_geometry import crossing

    result = crossing((0.0, 0.0), (100.0, 0.0), (50.0, 0.0), (150.0, 0.0))
    assert result is not None and result[2] == (75.0, 0.0)
    assert crossing((0.0, 0.0), (100.0, 0.0), (50.0, 10.0), (150.0, 10.0)) is None
