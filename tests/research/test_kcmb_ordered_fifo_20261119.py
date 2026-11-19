"""Ordered KCMB FIFO research lane: observable tests, no V1 production override."""
from __future__ import annotations
import json
import math
import random
from dataclasses import replace
import pytest

from metroflow.v1.kcmb import KCMBClass
from metroflow.v1.kcmb_network import KCMBLink, KCMBRoute, KCMBNetworkConfig, KCMBBoundedNetwork
from metroflow.v1.kcmb_ordered_fifo import OrderedKCMBBoundedNetwork, FIFOQueueBudgetError


def toy(backend="python", *, max_runs=120, length=20.):
    car=KCMBClass("car",vmax_mps=10.,footprint_m=5.,
        alpha_per_s=.2,nu_per_s=0.,tau_s=1.,
        source_p=1.,source_speed_fraction=1.)
    links=(KCMBLink("entry","O","J",length,1,2.,5.),
           KCMBLink("left","J","L",length,1,2.,5.),
           KCMBLink("right","J","R",length,1,2.,5.))
    routes=(KCMBRoute("A",car,("entry","left")),
            KCMBRoute("B",car,("entry","right")))
    cfg=KCMBNetworkConfig(links=links,routes=routes,dt_s=.5)
    return OrderedKCMBBoundedNetwork(cfg,backend=backend,max_runs=max_runs)


def immediately_ready(model, order):
    return model.initial_profile({"entry":(1.,1.)},
                                 order_by_link={"entry":tuple((s,1.) for s in order)})


@pytest.mark.parametrize("backend",["python","rust"])
def test_same_six_moments_opposite_order_produce_opposite_red_turn_behavior(backend):
    model=toy(backend)
    first=immediately_ready(model,("A","B"))
    second=immediately_ready(model,("B","A"))
    # Crucial: the pre-step six moments, traffic inventory and all bulk state
    # are identical. Only the route run sequence differs.
    assert first.moments==second.moments
    assert first.released==second.released
    gates={("entry","left"):0.,("entry","right"):1.}
    a,ra=model.step(first,(0.,0.),gates=gates)
    b,rb=model.step(second,(0.,0.),gates=gates)
    assert ra["turn_flows"].get(("entry","right","B"),0.)==0.
    assert rb["turn_flows"].get(("entry","right","B"),0.)>0.
    assert ra["turn_flows"].get(("entry","left","A"),0.)==0.
    assert a.moments!=b.moments
    assert ra["mass_error_max_veh"]<1e-9
    assert rb["mass_error_max_veh"]<1e-9


def test_ineligible_front_cannot_be_overtaken_even_if_back_wants_green():
    m=toy(length=20.)
    s=m.initial()
    # Below the physical source admission bound; otherwise an earlier
    # A backlog would legitimately be admitted together with B.
    s,r=m.step(s,(.1,0.))
    s,r=m.step(s,(0.,.1))
    assert m.queue_route_names(s,"entry")==("A","B")
    assert all(v==0. for v in r["finished_by_route"])
    # A has free-flow minimum 20/10 = 2s, and arrived first.
    for _ in range(4):
        s,r=m.step(s,(0.,0.),gates={("entry","left"):0.,("entry","right"):1.})
        assert r["turn_flows"].get(("entry","right","B"),0.)==0.
    assert m.queue_route_names(s,"entry")==("A","B")


def test_same_route_different_birth_ticks_remain_distinct_until_eligible():
    m=toy(max_runs=12)
    s=m.initial()
    for _ in range(3):
        s,_=m.step(s,(.2,0.))
    runs=m.queue_runs(s,"entry")
    assert len(runs)==3
    assert [r.route for r in runs]==[0,0,0]
    assert len(set(r.ready_tick for r in runs))==3
    # Same-tick compatible same-route arrivals can be collapsed exactly.
    assert sum(r.mass for r in runs)==pytest.approx(.6)


def test_budget_overflow_fails_without_discarding_physical_state():
    m=toy(max_runs=2)
    s=m.initial()
    s,_=m.step(s,(.1,0.))
    s,_=m.step(s,(0.,.1))
    frozen=m.to_bytes(s)
    with pytest.raises(FIFOQueueBudgetError,match="budget") as info:
        m.step(s,(.1,0.))
    assert info.value.checkpoint==s
    assert m.to_bytes(s)==frozen


def test_network_physical_mass_and_queue_mass_remain_consistent():
    rng=random.Random(20261119)
    m=toy(max_runs=900)
    s=m.initial()
    offered=[0.,0.]
    for i in range(140):
        arrivals=(rng.random()*.18,rng.random()*.16)
        offered=[a+b for a,b in zip(offered,arrivals)]
        gates={("entry","left"):float(i%19>=5),
               ("entry","right"):float(i%17>=7)}
        s,receipt=m.step(s,arrivals,gates=gates)
        assert receipt["mass_error_max_veh"]<2e-8
        assert len(s.runs)==3
        assert receipt["run_count"]<=receipt["run_budget"]
        for k in range(2):
            active=sum(m.cell_class_mass(s,link,k) for link in
                       ("entry","left","right"))
            assert offered[k]==pytest.approx(
                s.pending[k]+s.completed[k]+active,abs=2e-8)
        for link in ("entry","left","right"):
            assert m.occupied_metres(s,link)<=20.+3e-9
            for k in range(2):
                assert sum(r.mass for r in m.queue_runs(s,link)
                           if r.route==k)==pytest.approx(
                    m.cell_class_mass(s,link,k),abs=2e-9)


def test_time_of_entry_and_minimum_link_travel_lag():
    car=KCMBClass("car",vmax_mps=10.,footprint_m=5.,
                  alpha_per_s=0.,nu_per_s=0.,tau_s=1.,
                  source_p=1.,source_speed_fraction=1.)
    cfg=KCMBNetworkConfig(links=(KCMBLink("only","O","D",30.,1,5.,5.),),
        routes=(KCMBRoute("A",car,("only",)),),dt_s=1.)
    m=OrderedKCMBBoundedNetwork(cfg,max_runs=20)
    s,_=m.step(m.initial(),(1.,))
    assert s.tick==1
    assert s.runs[0][0].ready_tick==4
    for tick in (2,3):
        s,r=m.step(s,(0.,))
        assert r["finished_by_route"]==(0.,)
        assert s.tick==tick
    s,r=m.step(s,(0.,))
    assert r["finished_by_route"][0]>0.
    assert s.tick==4


def test_atomic_checkpoint_roundtrip_and_model_id_separation():
    m=toy()
    s=m.initial()
    for t in range(12):
        s,_=m.step(s,((t%2)*.1,(t%3)*.1))
    wire=m.to_bytes(s)
    assert m.from_bytes(wire)==s
    assert m.to_bytes(m.from_bytes(wire))==wire
    a,b=s,m.from_bytes(wire)
    for t in range(14):
        a,_=m.step(a,(.1,.0))
        b,_=m.step(b,(.1,.0))
    assert a==b
    assert m.model_id!=KCMBBoundedNetwork(m.config).model_id
    with pytest.raises(ValueError,match="identity"):
        toy(max_runs=200).from_bytes(wire)
    with pytest.raises(ValueError):
        m.from_bytes(wire+b"junk")


def test_nonready_and_budget_can_block_without_fake_completion():
    m=toy(max_runs=20)
    s=m.initial()
    for i in range(8):
        s,_=m.step(s,(.2 if i<4 else 0.,0.))
    assert s.released[0]==pytest.approx(.8)
    assert s.released[0]==pytest.approx(
        s.pending[0]+s.completed[0]+sum(m.cell_class_mass(s,link,0)
                                       for link in ("entry","left","right")))


def test_invalid_initial_route_order_and_snapshot_are_rejected():
    m=toy()
    with pytest.raises(ValueError,match="order"):
        m.initial_profile({"entry":(1.,1.)})
    with pytest.raises(ValueError):
        m.initial_profile({"entry":(1.,1.)},
                          order_by_link={"entry":(("A",1.),("A",1.))})
    with pytest.raises(ValueError):
        m.initial_profile({"entry":(1.,0.)},
                          order_by_link={"entry":(("X",1.),)})
    with pytest.raises(ValueError):
        m.step(m.initial(),(math.nan,0.))
    s=immediately_ready(m,("A","B"))
    corrupted=replace(s,runs=((replace(s.runs[0][0],mass=99.),),(),()))
    with pytest.raises(ValueError,match="queue|inventory"):
        m.step(corrupted,(0.,0.))


def test_floating_point_head_residue_does_not_freeze_an_open_fifo_lane():
    car=KCMBClass("car",vmax_mps=10.,footprint_m=5.,
        alpha_per_s=.2,nu_per_s=0.,tau_s=1.,
        source_p=1.,source_speed_fraction=1.)
    links=(KCMBLink("entry","O","J",100.,1,20.,5.),
           KCMBLink("left","J","L",100.,1,20.,5.),
           KCMBLink("right","J","R",100.,1,20.,5.))
    routes=(KCMBRoute("A",car,("entry","left")),
            KCMBRoute("B",car,("entry","right")))
    model=OrderedKCMBBoundedNetwork(KCMBNetworkConfig(links,routes,1.),
                                    max_runs=2000)
    order=tuple(("A" if i%2==0 else "B",.02) for i in range(500))
    s=model.initial_profile({"entry":(5.,5.)},order_by_link={"entry":order})
    s,r0=model.step(s,(0.,0.))
    s,r1=model.step(s,(0.,0.))
    # The first step may truncate a front at the floating-point level.
    # The second step must not treat that machine residue as a permanently
    # blocked physical vehicle. Conservation still requires exact ledger.
    assert sum(r0["turn_flows"].values())>.9
    assert sum(r1["turn_flows"].values())>.1
    assert r1["mass_error_max_veh"]<1e-8



def test_rust_python_ordered_fifo_stochastic_parity_and_checkpoint():
    rng=random.Random(1119)
    python=toy("python",max_runs=1100)
    native=toy("rust",max_runs=1100)
    a,b=python.initial(),native.initial()
    for tick in range(200):
        offers=(rng.random()*.17,rng.random()*.19)
        gate={("entry","left"):float(tick%19>=6),
              ("entry","right"):float(tick%13>=5)}
        a,ra=python.step(a,offers,gates=gate)
        b,rb=native.step(b,offers,gates=gate)
        assert a.tick==b.tick
        assert len(a.runs)==len(b.runs)
        for raq,rbq in zip(a.runs,b.runs):
            assert len(raq)==len(rbq)
            for x,y in zip(raq,rbq):
                assert x.route==y.route and x.ready_tick==y.ready_tick
                assert x.mass==pytest.approx(y.mass,abs=5e-10,rel=5e-10)
        for x,y in zip(a.moments,b.moments):
            assert x==pytest.approx(y,abs=5e-9,rel=2e-10)
        for x,y in zip(a.completed,b.completed):
            assert x==pytest.approx(y,abs=2e-9)
        assert ra["run_count"]<=ra["run_budget"]
        assert rb["run_count"]<=rb["run_budget"]
    assert python.from_bytes(python.to_bytes(a))==a
    assert native.from_bytes(native.to_bytes(b))==b


def test_roundoff_completion_is_charged_and_numerically_bounded():
    car=KCMBClass("car",10.,5.,.2,0.,1.,source_p=1.,source_speed_fraction=1.)
    links=(KCMBLink("in","O","J",100.,1,20.,5.),
           KCMBLink("left","J","L",100.,1,20.,5.),
           KCMBLink("right","J","R",100.,1,20.,5.))
    routes=(KCMBRoute("A",car,("in","left")),
            KCMBRoute("B",car,("in","right")))
    model=OrderedKCMBBoundedNetwork(KCMBNetworkConfig(links,routes,1.),
                                    max_runs=2000)
    order=tuple(("A" if i%2==0 else "B",.02) for i in range(500))
    state=model.initial_profile({"in":(5.,5.)},order_by_link={"in":order})
    total_charge=0.
    for tick in range(4):
        state,r=model.step(state,(0.,0.))
        assert 0 <= r["numerical_completion_charge_veh"] <=500*1e-12
        assert r["mass_error_max_veh"]<5e-8
        total_charge+=r["numerical_completion_charge_veh"]
    assert total_charge>0.


def test_source_pending_has_no_external_subtick_fifo_contract():
    m=toy()
    s=m.initial()
    # Any permutations of arrivals *within a tick* that have the same
    # per-route totals give the same source input. External pending queues
    # are class totals; no exact FIFO order before road admission is claimed.
    a,_=m.step(s,(1.,1.))
    b,_=m.step(s,(1.,1.))
    assert a==b
    assert a.pending==b.pending



def test_subresolution_preloaded_vehicle_mass_is_rejected_not_frozen():
    model=toy()
    with pytest.raises(ValueError,match="resolution"):
        model.initial_profile({"entry":(5e-13,0.)},
                              order_by_link={"entry":(("A",5e-13),)})
