"""Proof witness: strict FIFO transfer is not a function of unordered moments.

The two admissible inputs have exactly equal kinetic class/route moments and
link geometry, but different head-of-line order. Red A / green B distinguishes.
"""
import json
from pathlib import Path

from metroflow.v1.kcmb import KCMBClass
from metroflow.v1.kcmb_network import KCMBLink,KCMBRoute,KCMBNetworkConfig
from metroflow.v1.kcmb_adaptive_fifo import CertifiedAdaptiveFIFO
from metroflow.v1.native_engine import native_binary_provenance

ROOT=Path(__file__).resolve().parents[2]
ART=ROOT/"artifacts/v03_composed_events_20261120"


def test_source_bound_order_invariance_counterexample_two_independent_backends():
    row=json.loads((ART/"C10_MOMENT_FIFO_NONIDENTIFIABILITY.json").read_bytes())
    assert row["claim_status"]=="CONSTRUCTIVE_FINITE_COUNTEREXAMPLE"
    assert row["same_physical_geometry"] is True
    assert row["same_initial_route_mass_and_six_moments"] is True
    assert row["current_Rust_KCMB_binary_sha256"]==native_binary_provenance()["sha256"]
    assert len(row["results"])==2
    assert {x["backend"] for x in row["results"]}=={"python","rust"}
    for x in row["results"]:
        assert x["same_initial_six_moment_vector"]
        assert x["same_initial_route_mass"]
        assert x["same_initial_model_identifier"]
        assert x["fixed_scalar_state_capacity"]==42
        assert x["FIFO_route_order_AB"]!=x["FIFO_route_order_BA"]
        assert x["red_A_green_B_exit_B_AB"]==0
        assert x["red_A_green_B_exit_B_BA"]==0.05
        assert x["mass_error_AB_veh"]==x["mass_error_BA_veh"]==0


def test_independent_direct_construction_of_finite_FIFO_order_no_go():
    cls=KCMBClass("driver",10.,5.,.2,0.,1.,
                  source_p=1.,source_speed_fraction=1.)
    config=KCMBNetworkConfig(
        (KCMBLink("entry","O","J",100.,1,2.,5.),
         KCMBLink("left","J","L",100.,1,2.,5.),
         KCMBLink("right","J","R",100.,1,2.,5.)),
        (KCMBRoute("A",cls,("entry","left")),
         KCMBRoute("B",cls,("entry","right"))),
        .5,
    )
    for backend in ("python","rust"):
        model=CertifiedAdaptiveFIFO(config,backend=backend,max_runs=100)
        ab=model.initial_profile({"entry":(1.,1.)},
             order_by_link={"entry":(("A",1.),("B",1.))})
        ba=model.initial_profile({"entry":(1.,1.)},
             order_by_link={"entry":(("B",1.),("A",1.))})
        assert ab.moments==ba.moments
        assert (ab.pending,ab.released,ab.completed)==(ba.pending,ba.released,ba.completed)
        assert ab.runs!=ba.runs
        signal={("entry","left"):0.,("entry","right"):1.}
        _,rAB=model.step(ab,(0.,0.),gates=signal)
        _,rBA=model.step(ba,(0.,0.),gates=signal)
        assert rAB["turn_flows"].get(("entry","right","B"),0.)==0.
        assert rBA["turn_flows"].get(("entry","right","B"),0.)==0.05
        assert rAB["mass_error_max_veh"]<1e-12
        assert rBA["mass_error_max_veh"]<1e-12
