"""Public-boundary tests for explicit physical turning-pocket geometry.

The presence of separate receiving lanes, not only turn labels, must justify
one turn flowing around a blocked turn. All input geometry is synthetic.
"""
from __future__ import annotations
import math
import random
import pytest

from metroflow.v1.kcmb import KCMBClass
from metroflow.v1.kcmb_network import KCMBLink, KCMBRoute, KCMBNetworkConfig
from metroflow.v1.kcmb_adaptive_fifo import CertifiedAdaptiveFIFO
from metroflow.v1.kcmb_turn_pockets import (
    PocketGroup, TurnPocketLayout, compile_turn_pockets,
)


def original(lanes=1):
    c=KCMBClass("driver",10.,5.,.2,0.,1.,source_p=1.,
                source_speed_fraction=1.)
    links=(
        KCMBLink("approach","O","J",100.,lanes,2.,5.),
        KCMBLink("left","J","L",100.,1,2.,5.),
        KCMBLink("right","J","R",100.,1,2.,5.),
    )
    routes=(
        KCMBRoute("A",c,("approach","left")),
        KCMBRoute("B",c,("approach","right")),
    )
    return KCMBNetworkConfig(links,routes,.5)


def partition(pocket_length=30.,left_lanes=1,right_lanes=1):
    return TurnPocketLayout(
        approach="approach",
        pocket_length_m=pocket_length,
        groups=(
            PocketGroup("A_turn",("A",),left_lanes,1.),
            PocketGroup("B_turn",("B",),right_lanes,1.),
        ),
    )


def setup(backend="python",layout=None):
    compiled=compile_turn_pockets(original(),layout or partition())
    return compiled,CertifiedAdaptiveFIFO(compiled.config,backend=backend,
                                           max_runs=1000)


def names(compiled):
    return dict(compiled.pocket_link_by_group)


def test_explicit_road_widening_geometry_and_no_phantom_lane_metres():
    base=original()
    compiled=compile_turn_pockets(base,partition())
    pocket=names(compiled)
    assert len(compiled.config.links)==len(base.links)+2
    assert compiled.config.links[0].name=="approach"
    assert compiled.config.links[0].length_m==70.
    assert compiled.config.links[0].lanes==1
    assert pocket.keys()=={"A_turn","B_turn"}
    links={l.name:l for l in compiled.config.links}
    assert all(links[pocket[g]].length_m==30 for g in pocket)
    assert all(links[pocket[g]].lanes==1 for g in pocket)
    assert links[pocket["A_turn"]].tail==links["approach"].head
    assert links[pocket["A_turn"]].head=="J"
    assert compiled.geometry.original_lane_metres==pytest.approx(100.)
    assert compiled.geometry.compiled_lane_metres==pytest.approx(130.)
    assert compiled.geometry.added_lane_metres==pytest.approx(30.)
    assert compiled.geometry.pocket_region_lanes==2
    assert compiled.config.routes[0].path==("approach",pocket["A_turn"],"left")
    assert compiled.config.routes[1].path==("approach",pocket["B_turn"],"right")
    assert compiled.config.routes[0].name=="A"
    assert compiled.config.routes[0].vehicle==base.routes[0].vehicle


def test_no_widening_shared_turn_group_is_explicit_and_stays_fifo():
    layout=TurnPocketLayout("approach",30.,
                            (PocketGroup("mixed",("A","B"),1,1.),))
    compiled=compile_turn_pockets(original(),layout)
    assert compiled.geometry.added_lane_metres==0.
    group=dict(compiled.pocket_link_by_group)["mixed"]
    assert all(r.path[1]==group for r in compiled.config.routes)
    m=CertifiedAdaptiveFIFO(compiled.config,max_runs=100)
    s=m.initial_profile({group:(1.,1.)},
                        order_by_link={group:(("A",1.),("B",1.))})
    # A is at the front and its destination is red.
    s,receipt=m.step(s,(0.,0.),gates={(group,"left"):0.,
                                     (group,"right"):1.})
    assert receipt["turn_flows"].get((group,"right","B"),0.)==0.


@pytest.mark.parametrize("backend",["python","rust"])
def test_dedicated_pockets_allow_green_B_when_A_pocket_red(backend):
    compiled,m=setup(backend)
    pocket=names(compiled)
    pA,pB=pocket["A_turn"],pocket["B_turn"]
    s=m.initial_profile({pA:(1.,0.),pB:(0.,1.)})
    s,r=m.step(s,(0.,0.),gates={(pA,"left"):0.,(pB,"right"):1.})
    assert r["turn_flows"].get((pA,"left","A"),0.)==0.
    assert r["turn_flows"].get((pB,"right","B"),0.)>0.
    assert r["mass_error_max_veh"]<=1e-9
    assert m.occupied_metres(s,pA)<=30+1e-9
    assert m.occupied_metres(s,pB)<=30+1e-9


def test_shared_approach_blocks_late_B_when_front_A_pocket_full():
    compiled,m=setup()
    pA,pB=names(compiled)["A_turn"],names(compiled)["B_turn"]
    state=m.initial_profile({"approach":(1.,1.),pA:(6.,0.)},
            order_by_link={"approach":(("A",1.),("B",1.))})
    # A pocket is already jam-stored (6 veh×5 m=30 lane-metres).
    assert m.occupied_metres(state,pA)==pytest.approx(30.)
    state,r=m.step(state,(0.,0.),gates={(pA,"left"):0.,
                                       (pB,"right"):1.})
    assert r["turn_flows"].get(("approach",pB,"B"),0.)==0.
    assert m.cell_class_mass(state,pB,1)==0.
    assert r["mass_error_max_veh"]<=1e-9


def test_new_boundary_birth_cannot_teleport_across_split_approach():
    compiled,m=setup()
    state=m.initial()
    state,r=m.step(state,(0.,.2))
    assert r["finished_by_route"]==(0.,0.)
    for _ in range(5):
        state,r=m.step(state,(0.,0.))
        assert r["finished_by_route"]==(0.,0.)
    assert state.released[1]==pytest.approx(.2)
    assert state.pending[1]+sum(m.cell_class_mass(state,l.name,1)
                 for l in compiled.config.links)==pytest.approx(.2)


def test_rejects_unphysical_ambiguous_road_geometry():
    bad=[
        TurnPocketLayout("approach",0.,partition().groups),
        TurnPocketLayout("approach",100.,partition().groups),
        TurnPocketLayout("missing",30.,partition().groups),
        TurnPocketLayout("approach",30.,(PocketGroup("onlyA",("A",),1,1.),)),
        TurnPocketLayout("approach",30.,(
            PocketGroup("L",("A","B"),1,1.),PocketGroup("R",("B",),1,1.))),
        TurnPocketLayout("approach",30.,(
            PocketGroup("L",("A",),1,1.),PocketGroup("L",("B",),1,1.))),
        TurnPocketLayout("approach",30.,(
            PocketGroup("L",("A",),0,1.),PocketGroup("R",("B",),1,1.))),
        TurnPocketLayout("approach",30.,(
            PocketGroup("L",("A",),1,-1.),PocketGroup("R",("B",),1,1.))),
    ]
    for layout in bad:
        with pytest.raises(ValueError):
            compile_turn_pockets(original(),layout)
    with pytest.raises(ValueError,match="one-lane|shared"):
        compile_turn_pockets(original(lanes=2),partition())


def test_cfl_split_violations_are_not_hidden_or_autorescaled():
    with pytest.raises(ValueError,match="CFL"):
        compile_turn_pockets(original(),partition(pocket_length=2.))


def test_route_names_and_geometry_yield_checkpoint_distinct_identity():
    small,m1=setup()
    large,m2=setup(layout=partition(pocket_length=40.))
    assert m1.model_id!=m2.model_id
    s=m1.initial()
    wire=m1.to_bytes(s)
    assert m1.from_bytes(wire)==s
    with pytest.raises(ValueError,match="identity"):
        m2.from_bytes(wire)
    assert small.geometry.added_lane_metres!=large.geometry.added_lane_metres


def test_random_signals_and_vehicle_metre_ledgers_are_conservative():
    rng=random.Random(20261119)
    compiled,m=setup()
    name=names(compiled)
    state=m.initial()
    offered=[0.,0.]
    for i in range(130):
        request=(rng.random()*.19,rng.random()*.14)
        offered=[a+b for a,b in zip(offered,request)]
        signals={(name["A_turn"],"left"):float(i%23>=9),
                 (name["B_turn"],"right"):float(i%17>=7)}
        state,rc=m.step(state,request,gates=signals)
        assert rc["mass_error_max_veh"]<2e-8
        for k in range(2):
            mass=sum(m.cell_class_mass(state,l.name,k)
                     for l in compiled.config.links)
            assert offered[k]==pytest.approx(
                mass+state.pending[k]+state.completed[k],abs=2e-8)
        for link in compiled.config.links:
            assert m.occupied_metres(state,link.name)<=link.length_m*link.lanes+1e-9


def test_python_rust_node_parity_under_identical_pocket_geometry():
    compiled,py=setup("python")
    _,rust=setup("rust")
    a,b=py.initial(),rust.initial()
    pocket=names(compiled)
    for i in range(80):
        inp=(.1+.03*(i%3),.09+.02*(i%4))
        gates={(pocket["A_turn"],"left"):float(i%21>=7),
               (pocket["B_turn"],"right"):float(i%17>=6)}
        a,ra=py.step(a,inp,gates=gates)
        b,rb=rust.step(b,inp,gates=gates)
        assert a.moments==pytest.approx(b.moments,abs=3e-8)
        assert a.completed==pytest.approx(b.completed,abs=1e-8)
        assert a.pending==pytest.approx(b.pending,abs=1e-8)
        assert ra["mass_error_max_veh"]<2e-8
        assert rb["mass_error_max_veh"]<2e-8


def test_does_not_silently_reinterpret_independent_turn_as_shared_head_fifo():
    base=original()
    separate=KCMBNetworkConfig(base.links,base.routes,base.dt_s,
                               lane_policy="independent_turn")
    with pytest.raises(ValueError,match="shared_head|FIFO"):
        compile_turn_pockets(separate,partition())


def test_compiler_preserves_input_config_immutability_and_link_geometry():
    base=original()
    original_geometry=tuple((l.name,l.tail,l.head,l.length_m,l.lanes)
                            for l in base.links)
    compiler_result=compile_turn_pockets(base,partition())
    assert tuple((l.name,l.tail,l.head,l.length_m,l.lanes)
                 for l in base.links)==original_geometry
    assert compiler_result.config!=base


def test_integer_tick_eligibility_splitting_adds_at_most_one_timestep():
    # This follows from ceil(x)+ceil(y)-ceil(x+y) in {0,1}; discretization
    # effect, NOT proof of equal congested travel time after lane widening.
    for pocket_length in (30.,33.,39.,40.,50.,61.):
        compiled=compile_turn_pockets(original(),partition(pocket_length=pocket_length))
        total=compiled.geometry.original_length_m
        upstream=compiled.geometry.shared_length_m
        pocket=compiled.geometry.pocket_length_m
        dt=compiled.config.dt_s
        U=original().routes[0].vehicle.vmax_mps
        old=math.ceil(total/(U*dt))
        split=math.ceil(upstream/(U*dt))+math.ceil(pocket/(U*dt))
        assert split-old in (0,1)
