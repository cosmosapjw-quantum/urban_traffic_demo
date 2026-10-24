import math
from dataclasses import replace
import pytest
from metroflow.environment.terrain import Rect, Terrain, synthetic_terrain, compile_network


def test_river_has_explicit_bridges_and_two_components_without_them():
    terrain = synthetic_terrain(n=8, seed=17)
    # Isolate river connectivity from the independent steep-hill barrier.
    terrain = replace(terrain, heights_m=(20.,)*len(terrain.heights_m))
    graph = compile_network(terrain)
    assert graph.links, 'No terrain-conditioned physical road network was generated'
    assert terrain.water
    assert any(e.kind == 'bridge' for e in graph.links)
    assert len(set(dict(graph.components).values())) == 1
    cut = compile_network(replace(terrain, bridge_rows=()))
    assert len(set(dict(cut.components).values())) >= 2


def test_grade_limit_rejects_steep_edges_instead_of_connectivity_fallback():
    t=Terrain(2,100.,(0.,100.,200.,0.,100.,200.,0.,100.,200.))
    graph=compile_network(t,max_grade=.1)
    assert graph.links, 'Flat north-south edges must survive'
    assert all(e.grade <= .1 for e in graph.links)
    assert dict(graph.rejected)['grade'] == 6
    assert len(set(dict(graph.components).values())) == 3


def test_surface_road_cannot_cross_a_narrow_river_between_dry_endpoints():
    t=Terrain(1,100.,(10.,)*4,water=(Rect(45.,-1.,55.,101.),))
    graph=compile_network(t)
    assert len(graph.links)==2, 'Only dry vertical edges are admissible'
    assert all(e.kind=='surface' for e in graph.links)


def test_replay_and_budget_geometry():
    t=synthetic_terrain(n=6,seed=33)
    a=compile_network(t); b=compile_network(t)
    assert a.links, 'No generated links'
    assert a==b
    by={n.id:n for n in a.nodes}
    for e in a.links:
        u,v=by[e.u],by[e.v]
        assert e.length_m >= math.hypot(u.x_m-v.x_m,u.y_m-v.y_m)
        assert e.construction_index_m >= e.length_m


def test_bad_raster_inputs_rejected():
    with pytest.raises(ValueError):compile_network(Terrain(2,0.,(0.,)*9))
    with pytest.raises(ValueError):compile_network(Terrain(2,10.,(0.,)*8))
    with pytest.raises(ValueError):compile_network(Terrain(1,10.,(math.nan,)*4))
