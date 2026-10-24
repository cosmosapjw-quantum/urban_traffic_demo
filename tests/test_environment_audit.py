"""One post-implementation adversarial regression pass (not labeled TDD)."""
import math
import pytest
from metroflow.environment.terrain import Terrain, Rect, synthetic_terrain, compile_network, intersects
from metroflow.environment.landuse import zone_city
from metroflow.environment.demand import plan_commute
from metroflow.environment.coupling import road_physics,run_commute
from metroflow.active_suffix import Config


def test_road_width_not_only_centerline_respects_protected_land():
    # Edge y=0 misses the rectangle by 4m; a 12m road footprint does not.
    t=Terrain(1,100.,(10.,)*4,protected=(Rect(40.,4.,60.,20.),))
    g=compile_network(t,road_width_m=12.)
    coords={n.id:(n.x_m,n.y_m) for n in g.nodes}
    assert len(g.links)==3
    assert all(not intersects(coords[e.u],coords[e.v],t.protected[0],6.) for e in g.links)


def test_short_memory_limit_returns_last_valid_unmoved_state():
    t=synthetic_terrain(n=6);c=zone_city(t,compile_network(t),3000,1200)
    roads,_=road_physics(c);p=plan_commute(c,roads,divisions=2,profile=((0.,300.,1.),))
    result,state=run_commute(c,p,30.,Config(dt_s=5.,paths_per_od=1,event_budget=1))
    assert result['status']=='BLOCKED_RESOURCE'
    assert result['blocker']=='arrival-calendar bound'
    assert state.tick==0 and state.released==0
    assert result['not_yet_released']==pytest.approx(result['planned_network_vehicles'])
    assert result['mean_network_journey_s'] is None


def test_district_resolution_does_not_change_total_person_car_ledger():
    t=synthetic_terrain(n=12);c=zone_city(t,compile_network(t),100000,40000)
    r,_=road_physics(c)
    plans=[plan_commute(c,r,divisions=d,profile=((0.,3600.,1.),)) for d in (2,3,4)]
    for p in plans:
        ledger=dict(p.ledger)
        assert ledger['car_vehicle_trips']==7040
        assert ledger['network_vehicle_trips']+ledger['unresolved_local_vehicle_trips']==pytest.approx(7040)
    assert len({round(dict(p.ledger)['unresolved_local_vehicle_trips'],4) for p in plans})>1


def test_no_bridge_support_never_invents_cross_river_trips():
    from dataclasses import replace
    from metroflow.environment.demand import District,travel_skims
    t=synthetic_terrain(n=8,bridges=False);t=replace(t,heights_m=(20.,)*len(t.heights_m))
    c=zone_city(t,compile_network(t),20000,8000);roads,_=road_physics(c)
    a=District('west','n1:1',1,1,0,());b=District('east','n7:1',1,1,0,())
    costs=travel_skims(roads,(a,b))
    assert math.isinf(costs[0][1]) and math.isinf(costs[1][0])
