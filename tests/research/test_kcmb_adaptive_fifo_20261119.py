"""Certified adaptive FIFO coalescence: same physical flux, lower run state.

Only mature + adjacent + same route are equivalent. All other route/clock
information remains, with an explicit budget failure instead of silent mixing.
"""
from dataclasses import replace
import math
import random
import pytest

from metroflow.v1.kcmb import KCMBClass
from metroflow.v1.kcmb_network import KCMBLink, KCMBRoute, KCMBNetworkConfig
from metroflow.v1.kcmb_ordered_fifo import (
    OrderedKCMBBoundedNetwork, OrderedRun, FIFOQueueBudgetError
)
from metroflow.v1.kcmb_adaptive_fifo import CertifiedAdaptiveFIFO


def single(backend="python",max_runs=110):
    c=KCMBClass("car",10.,5.,.2,0.,1.,source_p=1.,
                source_speed_fraction=1.)
    cfg=KCMBNetworkConfig((
       KCMBLink("road","O","D",1000.,1,5.,5.),),
       (KCMBRoute("A",c,("road",)),),1.)
    return CertifiedAdaptiveFIFO(cfg,backend=backend,max_runs=max_runs)


def base_single(backend="python",max_runs=2000):
    c=KCMBClass("car",10.,5.,.2,0.,1.,source_p=1.,
                source_speed_fraction=1.)
    cfg=KCMBNetworkConfig((
       KCMBLink("road","O","D",1000.,1,5.,5.),),
       (KCMBRoute("A",c,("road",)),),1.)
    return OrderedKCMBBoundedNetwork(cfg,backend=backend,max_runs=max_runs)


@pytest.mark.parametrize("backend",("python","rust"))
def test_mature_same_route_long_queue_compresses_with_exact_mass_and_events(backend):
    base=base_single(backend)
    adapt=single(backend,max_runs=110)
    a,b=base.initial(),adapt.initial()
    for n in range(250):
        offer=(.10,)
        a,ra=base.step(a,offer,gates={("road",None):0.})
        b,rb=adapt.step(b,offer,gates={("road",None):0.})
        assert a.completed==b.completed==(0.,)
        assert a.pending==pytest.approx(b.pending,abs=2e-9)
        assert a.moments==pytest.approx(b.moments,abs=2e-9)
        assert ra["mass_error_max_veh"]<2e-9
        assert rb["mass_error_max_veh"]<2e-9
        assert rb["run_count"]<=adapt.strict_max_runs
    assert len(a.runs[0])>=240
    assert len(b.runs[0])<=105
    assert len(b.runs[0])<len(a.runs[0])/2
    for n in range(30):
        a,ra=base.step(a,(0.,),gates={("road",None):1.})
        b,rb=adapt.step(b,(0.,),gates={("road",None):1.})
        assert ra["finished_by_route"]==pytest.approx(
            rb["finished_by_route"],abs=2e-10)
        assert a.moments==pytest.approx(b.moments,abs=2e-8)
    assert a.completed[0]==pytest.approx(b.completed[0],abs=2e-8)


def two_routes(max_runs=25,backend="python"):
    c=KCMBClass("car",10.,5.,.2,0.,1.,
                source_p=1.,source_speed_fraction=1.)
    links=(KCMBLink("entry","O","J",40.,1,3.,5.),
           KCMBLink("left","J","L",40.,1,3.,5.),
           KCMBLink("right","J","R",40.,1,3.,5.))
    routes=(KCMBRoute("A",c,("entry","left")),
            KCMBRoute("B",c,("entry","right")))
    return CertifiedAdaptiveFIFO(KCMBNetworkConfig(links,routes,1.),
                                 backend=backend,max_runs=max_runs)


def test_future_not_ready_runs_do_not_collapse_even_when_same_route():
    m=two_routes()
    s=m.initial_profile({"entry":(1.,0.)})
    s=replace(s,runs=((OrderedRun(0,.5,3),OrderedRun(0,.5,4)),(),()))
    s,r=m.step(s,(0.,0.),gates={("entry","left"):0.})
    assert len(s.runs[0])==2
    assert s.runs[0][0].ready_tick==3
    assert s.runs[0][1].ready_tick==4
    for _ in range(4):
        s,r=m.step(s,(0.,0.),gates={("entry","left"):0.})
    assert len(s.runs[0])==1
    assert s.runs[0][0].mass==pytest.approx(1.)


def test_alternating_routes_stay_ordered_under_blocking_signal():
    m=two_routes(max_runs=15)
    order=tuple(("A" if i%2==0 else "B",.1) for i in range(10))
    s=m.initial_profile({"entry":(.5,.5)},order_by_link={"entry":order})
    for _ in range(6):
        s,r=m.step(s,(0.,0.),gates={("entry","left"):0.,
                                  ("entry","right"):0.})
    assert len(s.runs[0])==10
    assert tuple(run.route for run in s.runs[0])==(0,1)*5


def test_overbudget_mixed_route_sequence_still_fails_closed():
    m=two_routes(max_runs=2)
    s=m.initial()
    s,_=m.step(s,(.1,0.))
    s,_=m.step(s,(0.,.1))
    frozen=m.to_bytes(s)
    with pytest.raises(FIFOQueueBudgetError,match="budget") as exc:
        m.step(s,(.1,0.))
    assert exc.value.checkpoint==s
    assert m.to_bytes(s)==frozen


def test_adaptive_checkpoint_roundtrip_and_distinct_physics_identity():
    adaptive=single()
    ordered=base_single()
    assert adaptive.model_id != ordered.model_id
    assert "kcmb_adaptive" in adaptive.model_id
    assert ordered.model_id.startswith("kcmb_ordered_route_runs_v2")
    s=adaptive.initial()
    for _ in range(130):
        s,_=adaptive.step(s,(.1,),gates={("road",None):0.})
    wire=adaptive.to_bytes(s)
    assert adaptive.from_bytes(wire)==s
    assert adaptive.to_bytes(adaptive.from_bytes(wire))==wire
    with pytest.raises(ValueError,match="identity"):
        ordered.from_bytes(wire)
    with pytest.raises(ValueError,match="identity"):
        adaptive.from_bytes(ordered.to_bytes(ordered.initial()))
    with pytest.raises(ValueError):
        adaptive.from_bytes(wire+b"bad")


def test_existing_strict_turn_order_counterexample_remains_adaptive():
    m=two_routes()
    a=m.initial_profile({"entry":(1.,1.)},
        order_by_link={"entry":(("A",1.),("B",1.))})
    b=m.initial_profile({"entry":(1.,1.)},
        order_by_link={"entry":(("B",1.),("A",1.))})
    assert a.moments==b.moments
    g={("entry","left"):0.,("entry","right"):1.}
    aa,ra=m.step(a,(0.,0.),gates=g)
    bb,rb=m.step(b,(0.,0.),gates=g)
    assert ra["turn_flows"].get(("entry","right","B"),0.)==0.
    assert rb["turn_flows"].get(("entry","right","B"),0.)>0.

def test_random_signal_adaptive_matches_exact_ordered_reference():
    from metroflow.v1.kcmb_ordered_fifo import OrderedKCMBBoundedNetwork
    rng=random.Random(1119)
    cfg=two_routes().config
    exact=OrderedKCMBBoundedNetwork(cfg,max_runs=5000)
    adapt=CertifiedAdaptiveFIFO(cfg,max_runs=5000)
    a,b=exact.initial(),adapt.initial()
    reductions=0
    for i in range(240):
        offered=(rng.random()*.17,rng.random()*.15)
        gates={("entry","left"):float(i%19>=5),
               ("entry","right"):float(i%17>=6)}
        a,ra=exact.step(a,offered,gates=gates)
        b,rb=adapt.step(b,offered,gates=gates)
        assert a.moments==pytest.approx(b.moments,abs=2e-9,rel=2e-10)
        assert a.pending==pytest.approx(b.pending,abs=2e-9)
        assert a.completed==pytest.approx(b.completed,abs=2e-9)
        assert ra["turn_flows"]==pytest.approx(rb["turn_flows"],abs=2e-9)
        assert rb["run_count"]<=ra["run_count"]
        reductions+=rb["runs_certifiably_merged"]
    assert a.tick==b.tick==240
    assert reductions>=0


@pytest.mark.parametrize("backend",("python","rust"))
def test_random_partition_of_eligible_same_route_merge_is_invariant(backend):
    from dataclasses import replace
    from metroflow.v1.kcmb_ordered_fifo import OrderedRun
    from test_kcmb_partition_invariance_20261119 import merge_case
    rng=random.Random(442)
    engine,full,_=merge_case(backend,out_cap=.6)
    a,ra=engine.step(full,(0.,0.))
    for trial in range(20):
        weights=[rng.random() for _ in range(3)]
        weights=[v/sum(weights)*2. for v in weights]
        # Use varying but already eligible clocks for the SAME physical route.
        runs=(OrderedRun(0,weights[0],0),
              OrderedRun(0,weights[1],1),
              OrderedRun(0,weights[2],0))
        altered=replace(full,runs=(runs,full.runs[1],full.runs[2]))
        b,rb=engine.step(altered,(0.,0.))
        assert ra["turn_flows"]==pytest.approx(rb["turn_flows"],abs=1e-10)
        assert a.completed==pytest.approx(b.completed,abs=1e-10)
