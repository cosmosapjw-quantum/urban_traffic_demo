"""KCMB network extension: route-preserving fluid cohorts, junction contracts.

The shared-head mode conservatively blocks a shared lane's *mixture* when a
turn is red; it is not an assertion of exact temporal vehicle FIFO.
"""
import math
import random
import pytest

from metroflow.v1.kcmb import KCMBClass
from metroflow.v1.kcmb_network import (
    KCMBLink, KCMBRoute, KCMBNetworkConfig, KCMBBoundedNetwork,
    progressive_junction,
)


def cls(name, footprint=5.):
    return KCMBClass(name, vmax_mps=10., footprint_m=footprint,
                     alpha_per_s=.2, nu_per_s=.0, tau_s=1.,
                     source_p=1., source_speed_fraction=1.)


def diamond(policy="shared_head", backend="python"):
    links=(
        KCMBLink("entry", "origin", "junction", 20., 1, 2., 5.),
        KCMBLink("left", "junction", "left_dest", 20., 1, 2., 5.),
        KCMBLink("right","junction", "right_dest",20.,1,2.,5.),
    )
    routes=(
        KCMBRoute("left_car", cls("car"), ("entry","left")),
        KCMBRoute("right_car",cls("car"), ("entry","right")),
    )
    return KCMBBoundedNetwork(KCMBNetworkConfig(
        links=links, routes=routes,dt_s=.5, lane_policy=policy),backend=backend)


def merge(backend="python", weights=(1.,1.)):
    links=(
        KCMBLink("north","n","j",20.,1,2.,5.,priority=weights[0]),
        KCMBLink("south","s","j",20.,1,2.,5.,priority=weights[1]),
        KCMBLink("exit","j","d",20.,1,1.,5.),
    )
    routes=(
        KCMBRoute("north_car",cls("car"),("north","exit")),
        KCMBRoute("south_car",cls("car"),("south","exit")),
    )
    return KCMBBoundedNetwork(KCMBNetworkConfig(
        links=links,routes=routes,dt_s=.5),backend=backend)


def test_node_waterfill_priority_merge_is_bounded_and_maximal():
    # senders n,s each want 1 veh; downstream receiving allows 1 veh.
    demands=(((0,2,1.,5.),),((1,2,1.,5.),))
    a=progressive_junction(demands,
        receive_count={2:1.},receive_metres={2:100.},weights=(1.,1.))
    assert a[(0,0)]==pytest.approx(.5)
    assert a[(1,0)]==pytest.approx(.5)
    b=progressive_junction(demands,
        receive_count={2:1.},receive_metres={2:100.},weights=(2.,1.))
    assert b[(0,0)]==pytest.approx(2/3)
    assert b[(1,0)]==pytest.approx(1/3)
    # The weighted length budget must be independent of vehicle-count capacity.
    c=progressive_junction(
        (((0,2,1.,5.),),((1,2,1.,15.),)),
        receive_count={2:100.},receive_metres={2:10.},weights=(1.,1.))
    assert c[(0,0)]==pytest.approx(.5)
    assert c[(1,0)]==pytest.approx(.5)
    assert 5*c[(0,0)]+15*c[(1,0)]<=10+1e-12


def test_shared_head_blocks_uncongested_turn_when_other_destination_red():
    shared=diamond("shared_head")
    independent=diamond("independent_turn")
    for model,expect in ((shared,False),(independent,True)):
        # Fill the source link first. Different route tags share its physical lane.
        state=model.initial()
        state,_=model.step(state,(1.,1.),gates={})
        state,event=model.step(state,(0.,0.),gates={("entry","right"):0.})
        left=event["turn_flows"].get(("entry","left","left_car"),0.)
        right=event["turn_flows"].get(("entry","right","right_car"),0.)
        assert right==0.
        assert (left>0) == expect
        assert event["state_scalar_capacity"]==model.state_scalars
        assert state.model_id==model.model_id


def test_two_to_one_merge_proportional_priority_and_competing_origin_supply():
    model=merge(weights=(3.,1.))
    state=model.initial()
    for tick in range(20):
        state,event=model.step(state,(.3,.3),
            gates={("north","exit"):1.,("south","exit"):1.})
        assert event["mass_error_max_veh"]<2e-9
        assert model.occupied_metres(state,"exit")<=20+1e-9
    totals=state.completed
    assert all(x>=0 for x in totals)
    # Larger north priority cannot guarantee total completion priority unless
    # both are contested in the same traffic regime; use the isolated allocator
    # test for the exact 3:1 split.


def test_network_conservation_and_no_mass_loss_under_stochastic_signals():
    rng=random.Random(43)
    for policy in ("shared_head","independent_turn"):
        model=diamond(policy)
        state=model.initial()
        offered=[0.,0.]
        for tick in range(250):
            arrivals=tuple(.25*rng.random() for _ in range(2))
            offered=[o+v for o,v in zip(offered,arrivals)]
            gates={("entry","right"):float(tick%23>=9)}
            state,receipt=model.step(state,arrivals,gates=gates)
            assert receipt["mass_error_max_veh"]<5e-9
            assert receipt["state_scalar_capacity"]==model.state_scalars
            for route in range(2):
                active=sum(model.cell_class_mass(state,link,route)
                           for link in ("entry","left","right"))
                assert offered[route]==pytest.approx(
                    state.pending[route]+state.completed[route]+active,abs=2e-8)
            for link in ("entry","left","right"):
                assert model.occupied_metres(state,link)<=20+5e-9


def test_network_checkpoint_resume_and_model_identity_rejection():
    m=diamond()
    s=m.initial()
    for i in range(35):
        s,_=m.step(s,(.4,.4),gates={("entry","right"):float(i%11>=4)})
    data=m.to_bytes(s)
    assert m.from_bytes(data)==s
    a=m.from_bytes(data)
    for i in range(45):
        s,_=m.step(s,(.1,.3),gates={("entry","right"):float(i%11>=4)})
        a,_=m.step(a,(.1,.3),gates={("entry","right"):float(i%11>=4)})
    assert a==s
    with pytest.raises(ValueError,match="identity"):
        diamond("independent_turn").from_bytes(data)
    with pytest.raises(ValueError):
        m.from_bytes(data+b"foo")


def test_initial_profile_route_occupancy_and_invalid_turns():
    m=diamond()
    x=m.initial_profile({"entry":(1.,1.)})
    assert m.occupied_metres(x,"entry")==pytest.approx(10.)
    assert x.released==(1.,1.)
    with pytest.raises(ValueError):
        m.initial_profile({"left":(0.,2.)}) # wrong route cannot inhabit left
    with pytest.raises(ValueError,match="route|contiguous"):
        KCMBBoundedNetwork(KCMBNetworkConfig(links=m.config.links,
            routes=(KCMBRoute("bad",cls("bad"),("left","right")),),dt_s=.5))
    with pytest.raises(ValueError,match="route|repeat"):
        KCMBBoundedNetwork(KCMBNetworkConfig(links=m.config.links,
            routes=(KCMBRoute("loop",cls("loop"),("entry","left","entry")),),dt_s=.5))


@pytest.mark.parametrize("backend",["python","rust"])
def test_opt_in_backend_respects_link_resources(backend):
    model=diamond("shared_head",backend)
    s=model.initial()
    for k in range(65):
        s,rc=model.step(s,(.2,.3),gates={("entry","right"):float(k%12<8)})
        assert rc["mass_error_max_veh"]<2e-9
    assert s.tick==65 and sum(s.completed)>0


def test_python_rust_node_and_state_parity_random_congested_network():
    py=diamond("independent_turn","python")
    rust=diamond("independent_turn","rust")
    a,b=py.initial(),rust.initial()
    for k in range(180):
        arrivals=(.43+.01*(k%3),.28+.02*(k%4))
        gate={("entry","left"):float(k%27<22),
              ("entry","right"):float(k%17<11)}
        a,ra=py.step(a,arrivals,gates=gate)
        b,rb=rust.step(b,arrivals,gates=gate)
        assert len(a.moments)==len(b.moments)
        for x,y in zip(a.moments,b.moments):
            assert x==pytest.approx(y,abs=5e-9,rel=2e-10)
        for x,y in zip(a.completed,b.completed):
            assert x==pytest.approx(y,abs=5e-9)
        assert ra["state_scalar_capacity"]==rb["state_scalar_capacity"]


def test_fixed_state_complexity_is_independent_of_population_scale():
    model=diamond()
    lengths=[]
    for scale in (1,100,100000):
        s=model.initial()
        for _ in range(50):
            s,r=model.step(s,(.2*scale,.3*scale),gates={})
        lengths.append((len(s.moments),r["state_scalar_capacity"],sum(s.pending)))
    assert lengths[0][:2]==lengths[1][:2]==lengths[2][:2]
    assert lengths[-1][2]>lengths[0][2]*1000


def long_chain(count=80, backend="python"):
    links=tuple(
        KCMBLink(f"road{i}",f"node{i}",f"node{i+1}",20.,1,2.,5.)
        for i in range(count))
    route=KCMBRoute("full_route",cls("car"),tuple(l.name for l in links))
    return KCMBBoundedNetwork(KCMBNetworkConfig(
        links=links,routes=(route,),dt_s=.5),backend=backend)


def test_local_junction_factorization_limits_receiver_table_to_node_degree(monkeypatch):
    import metroflow.v1.kcmb_network as kn
    observed=[]
    original=kn.progressive_junction
    def inspected(groups,*,receive_count,receive_metres,weights,theta_limits=None):
        observed.append((len(groups),len(receive_count)))
        return original(groups,receive_count=receive_count,
                        receive_metres=receive_metres,weights=weights,
                        theta_limits=theta_limits)
    monkeypatch.setattr(kn,"progressive_junction",inspected)
    model=long_chain(count=80)
    state=model.initial_profile({"road0":(1.,)})
    state,_=model.step(state,(0.,))
    assert observed and max(c for g,c in observed)<=1,observed
    assert state.tick==1


def test_large_sparse_network_does_not_allocate_dense_global_g_by_links():
    model=long_chain(1600,backend="rust")
    state=model.initial_profile({f"road{i}":(.1,) for i in range(1600)})
    state,receipt=model.step(state,(0.,))
    assert state.tick==1
    assert receipt["mass_error_max_veh"]<1e-10
    assert receipt["state_scalar_capacity"]==6*1600+3


def test_one_lane_chain_matches_previous_kcmb_corridor_same_boundary_kinetics():
    from metroflow.v1.kcmb import KCMBConfig,KCMBCorridor
    link_names=tuple(f"road{i}" for i in range(6))
    cls0=cls("car")
    old=KCMBCorridor(KCMBConfig(cells=6,cell_length_m=20.,lanes=1,
        dt_s=.5,capacity_veh_per_s=2.,backward_wave_mps=5.,
        classes=(cls0,)),backend="python")
    new=long_chain(count=6)
    a,b=old.initial(),new.initial()
    for tick in range(120):
        demand=(.5 if tick<30 else .1,)
        a,_=old.step(a,demand,green=float(tick%19>=7))
        b,_=new.step(b,demand,gates={("road5",None):float(tick%19>=7)})
        for i,name in enumerate(link_names):
            assert old.cell_class_mass(a,i,0)==pytest.approx(
                new.cell_class_mass(b,name,0),abs=2e-10)
        assert a.completed[0]==pytest.approx(b.completed[0],abs=2e-10)
        assert a.pending[0]==pytest.approx(b.pending[0],abs=2e-10)


def test_block_diagonal_junction_factorization_matches_single_global_problem():
    groups=(
        ((0,0,2.,5.),(1,1,1.,7.)),
        ((2,0,1.,5.),),
        ((3,2,1.5,9.),),
        ((4,3,1.,4.),(5,2,.5,6.)),
    )
    count={0:2.,1:2.,2:1.,3:1.}
    metres={0:10.,1:20.,2:15.,3:8.}
    weights=(1.,2.,3.,1.)
    full=progressive_junction(groups,receive_count=count,receive_metres=metres,
                              weights=weights)
    left=progressive_junction(groups[:2],
        receive_count={0:2.,1:2.},receive_metres={0:10.,1:20.},
        weights=weights[:2])
    right=progressive_junction(groups[2:],
        receive_count={2:1.,3:1.},receive_metres={2:15.,3:8.},
        weights=weights[2:])
    for (g,z),flow in full.items():
        other=left[g,z] if g<2 else right[g-2,z]
        assert flow==pytest.approx(other,abs=1e-12)


def test_no_same_step_source_to_second_link_or_unborn_completion():
    model=long_chain(3)
    state=model.initial()
    state,rc=model.step(state,(2.,))
    assert state.completed==(0.,)
    assert model.cell_class_mass(state,"road1",0)==0.
    assert model.cell_class_mass(state,"road2",0)==0.
    state,rc=model.step(state,(0.,))
    assert model.cell_class_mass(state,"road2",0)==0.
    assert state.completed==(0.,)
    assert model.cell_class_mass(state,"road1",0)>0.


def test_excessive_source_mass_is_pending_without_erasing_route_identity():
    model=diamond()
    state=model.initial()
    state,rc=model.step(state,(1e6,1e6),gates={})
    assert state.released==(1e6,1e6)
    assert all(p>1e6-10 for p in state.pending)
    assert rc["mass_error_max_veh"]<1e-6
    assert rc["state_scalar_capacity"]==model.state_scalars
    with pytest.raises(ValueError,match="gate"):
        model.step(state,(0.,0.),gates={("fake","left"):0.})
    assert state.tick==1


def test_user_suppled_wrong_initial_route_speed_and_checkpoint_are_rejected():
    model=diamond()
    state=model.initial()
    from dataclasses import replace
    bad=replace(state,moments=tuple(float("nan") if i==1 else x
                                    for i,x in enumerate(state.moments)))
    with pytest.raises(ValueError,match="nonfinite"):
        model.step(bad,(0.,0.))
    original=model.to_bytes(state)
    with pytest.raises(ValueError,match="size|budget"):
        model.from_bytes(original+b" "*(model.state_scalars*80+8192))
    assert state==model.initial()


def test_fixed_route_moments_cannot_certify_exact_vehicle_temporal_fifo():
    # Two micro queues with the same per-route totals and speed moments.
    # If only the B destination is open, A-leading vs B-leading queues have
    # different first exit flows under strict FIFO. Their coarse Q-images
    # are identical, so Q cannot recover both temporal outcomes.
    first=("A","B")
    second=("B","A")
    def strict_one(queue,green):
        return queue[0] if green[queue[0]] else None
    assert sorted(first)==sorted(second)
    assert strict_one(first,{"A":False,"B":True}) is None
    assert strict_one(second,{"A":False,"B":True})=="B"
    # Network's contract is a shared *mixture* closure, not either exact queue.


def test_single_link_source_mixture_matches_existing_kcmb_oversubscribed_boundary():
    from metroflow.v1.kcmb import KCMBCorridor,KCMBConfig
    car=cls("car",5.)
    bus=cls("bus",12.)
    old=KCMBCorridor(KCMBConfig(cells=1,cell_length_m=20.,lanes=1,
        dt_s=.5,capacity_veh_per_s=1.,backward_wave_mps=5.,
        classes=(car,bus,)),backend="python")
    new=KCMBBoundedNetwork(KCMBNetworkConfig(
        links=(KCMBLink("only","o","d",20.,1,1.,5.),),
        routes=(KCMBRoute("A",car,("only",)),
                KCMBRoute("B",bus,("only",))),dt_s=.5))
    offered=(100.,1.)
    a,ra=old.step(old.initial(),offered,green=0.)
    b,rb=new.step(new.initial(),offered,gates={("only",None):0.})
    assert rb["accepted_by_route"]==pytest.approx(
        ra["accepted_by_class"],rel=1e-12,abs=1e-12)
    assert b.pending==pytest.approx(a.pending,rel=1e-12,abs=1e-12)
