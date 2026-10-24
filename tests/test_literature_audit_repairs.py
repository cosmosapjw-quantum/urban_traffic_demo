"""Audit counterexamples against existing public model boundaries."""
import math
import pytest
from metroflow.environment.terrain import Terrain, Rect, compile_network
from metroflow.environment.landuse import zone_city
from metroflow.restored_city import Junction, Section, RoadMap
from metroflow.restored_geometry import ground_profile
from metroflow.frontage_growth import grow_access, Site
from metroflow.foundation_kinetics import VehicleClass
from metroflow.gap_transport import PairBin, PairState, LeaderReport, step, control


def test_no_industrial_buffer_when_every_planned_factory_is_excluded():
    n=8; L=800.
    t=Terrain(n,100.,(0.,)*((n+1)**2),protected=(Rect(.7*L,0.,L,.21*L),))
    c=zone_city(t,compile_network(t),0,0)
    assert not any(z.use=='industrial' for z in c.zones)
    assert not any(z.use=='buffer' for z in c.zones), 'Buffer around factories that were never built'


def test_zero_age_exact_report_cannot_contradict_current_leader_speed():
    s=PairState(0.,(PairBin(VehicleClass(),1.,100.,5.,10.),))
    with pytest.raises(ValueError,match='report') as err:
        step(s,(LeaderReport(0.,0.),),(0.,),.1,20.,8.)
    assert err.value.checkpoint==s


def test_near_frontage_is_not_serviceable_across_a_steep_slope():
    t=Terrain(1,100.,(0.,0.,50.,50.))
    pts,length,grade=ground_profile(t,((0.,0.),(100.,0.)))
    s=Section('ab','a','b',pts,'local','surface',1,1,length,grade)
    c=RoadMap('slope',t,(Junction('a',pts[0]),Junction('b',pts[-1])),(s,))
    r=grow_access(c,(Site('home',(50.,5.)),),budget_m=100.)
    assert ('home','already_fronting') not in r.rejected, 'Flat-distance proximity hid 50% cross-slope'
    assert not r.admitted


def test_controller_remains_nonanticipating_under_stale_reports():
    a=PairBin(VehicleClass(),1.,40.,10.,9.)
    b=PairBin(VehicleClass(),1.,40.,10.,20.)
    r=LeaderReport(0.,12.)
    assert control(a,r,1.,.5,20.,6.)==control(b,r,1.,.5,20.,6.)
