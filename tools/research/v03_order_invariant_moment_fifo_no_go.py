#!/usr/bin/env python3
"""Constructive obstruction: order-invariant kinetic moments cannot determine strict FIFO.

Two physically admissible ordered traffic streams have identical six-moment
per-route link state but different red-A/green-B FIFO exits. This does NOT
refute route-position-resolved kinetic fields or finite modes that encode
sufficient ordering. The model and numbers reuse prior documented test fixtures.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import json
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/"src")]

from metroflow.v1.kcmb import KCMBClass
from metroflow.v1.kcmb_network import KCMBLink,KCMBRoute,KCMBNetworkConfig
from metroflow.v1.kcmb_adaptive_fifo import CertifiedAdaptiveFIFO
from metroflow.v1.native_engine import native_binary_provenance


def example(backend:str):
    car=KCMBClass("driver",10.,5.,.2,0.,1.,
                  source_p=1.,source_speed_fraction=1.)
    cfg=KCMBNetworkConfig(
        (KCMBLink("entry","O","J",100.,1,2.,5.),
         KCMBLink("left","J","L",100.,1,2.,5.),
         KCMBLink("right","J","R",100.,1,2.,5.)),
        (KCMBRoute("A",car,("entry","left")),
         KCMBRoute("B",car,("entry","right"))),
        .5,lane_policy="shared_head",
    )
    model=CertifiedAdaptiveFIFO(cfg,backend=backend,max_runs=100)
    ab=model.initial_profile({"entry":(1.,1.)},
                             order_by_link={"entry":(("A",1.),("B",1.))})
    ba=model.initial_profile({"entry":(1.,1.)},
                             order_by_link={"entry":(("B",1.),("A",1.))})
    assert ab.model_id==ba.model_id
    assert ab.moments==ba.moments
    assert ab.pending==ba.pending
    assert ab.released==ba.released
    assert ab.completed==ba.completed
    assert ab.tick==ba.tick
    assert ab.runs!=ba.runs
    signal={("entry","left"):0.,("entry","right"):1.}
    ab2,recAB=model.step(ab,(0.,0.),gates=signal)
    ba2,recBA=model.step(ba,(0.,0.),gates=signal)
    bAB=recAB["turn_flows"].get(("entry","right","B"),0.)
    bBA=recBA["turn_flows"].get(("entry","right","B"),0.)
    assert bAB==0. and bBA>0.
    assert recAB["mass_error_max_veh"]<1e-11
    assert recBA["mass_error_max_veh"]<1e-11
    return {
        "backend":backend,
        "same_initial_six_moment_vector":True,
        "same_initial_route_mass":True,
        "same_initial_model_identifier":True,
        "FIFO_route_order_AB":[repr(v) for v in ab.runs],
        "FIFO_route_order_BA":[repr(v) for v in ba.runs],
        "red_A_green_B_exit_B_AB":bAB,
        "red_A_green_B_exit_B_BA":bBA,
        "mass_error_AB_veh":recAB["mass_error_max_veh"],
        "mass_error_BA_veh":recBA["mass_error_max_veh"],
        "fixed_scalar_state_capacity":model.state_scalars,
    }


def main():
    cases=[example("python"),example("rust")]
    assert cases[0]["red_A_green_B_exit_B_AB"]==cases[1]["red_A_green_B_exit_B_AB"]
    assert abs(cases[0]["red_A_green_B_exit_B_BA"]-
               cases[1]["red_A_green_B_exit_B_BA"])<1e-12
    output={
        "schema":"V03_FINITE_ORDER_INVARIANT_KINETIC_MOMENT_STRICT_FIFO_NO_GO_V1",
        "source":"metroflow.v1.kcmb_adaptive_fifo original network fixture, new research comparator",
        "claim":"two exactly equal order-invariant class/velocity moment vectors but distinct route order produce distinct strict FIFO outputs under one red turn",
        "claim_status":"CONSTRUCTIVE_FINITE_COUNTEREXAMPLE",
        "universal_no_go_scope":"ANY state reconstruction using only these order-insensitive instantaneous route moments, without additional route ordering state",
        "nonclaims":[
            "No proof against kinetic distribution functions resolving longitudinal position",
            "No proof against a finite state machine encoding all allowed orderings",
            "Not original V03 100k traffic physical acceptance or calibrated field validation",
        ],
        "same_physical_geometry":True,
        "same_initial_route_mass_and_six_moments":True,
        "class_source":"unchanged prior KCMB unit-test fixture, not calibrated",
        "results":cases,
        "current_Rust_KCMB_binary_sha256":native_binary_provenance()["sha256"],
        "created_utc":datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    f=ROOT/"artifacts/v03_composed_events_20261120/C10_MOMENT_FIFO_NONIDENTIFIABILITY.json"
    f.parent.mkdir(parents=True,exist_ok=True)
    f.write_text(json.dumps(output,indent=2,sort_keys=True,ensure_ascii=False)+"\n")
    print(json.dumps({
        "same_moments":True,
        "B_exit_if_A_front":cases[0]["red_A_green_B_exit_B_AB"],
        "B_exit_if_B_front":cases[0]["red_A_green_B_exit_B_BA"],
        "backends_agree":True,
    },sort_keys=True))


if __name__=="__main__":
    main()
