#!/usr/bin/env python3
"""Reconstructed micro-to-macro network with physically explicit turning pockets.

This is a separate KCMB model and NOT an old V03 full-day substitute. Its fixed
six-moment per-link/route state cannot preserve arbitrary original strict FIFO
or source-birth timestamps. Physical constants are previously established test
fixtures, not calibrated/optimized coefficients, and original city input was
NOT reused to score the new model.
"""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/"src")]
from metroflow.v1.kcmb import KCMBClass
from metroflow.v1.kcmb_network import (
    KCMBLink,KCMBRoute,KCMBNetworkConfig,KCMBBoundedNetwork
)
from metroflow.v1.kcmb_turn_pockets import (
    PocketGroup,TurnPocketLayout,compile_turn_pockets
)
from metroflow.v1.native_engine import native_binary_provenance


def config():
    # Same dimensional fixture as earlier public KCMB turn-pocket tests, not
    # inferred from any GPS or calibrated against this experiment's output.
    cls=KCMBClass(
        "driver",10.,5.,.2,0.,1.,source_p=1.,source_speed_fraction=1.
    )
    links=(
        KCMBLink("approach","O","J",100.,1,2.,5.),
        KCMBLink("left","J","L",100.,1,2.,5.),
        KCMBLink("right","J","R",100.,1,2.,5.),
    )
    routes=(
        KCMBRoute("A",cls,("approach","left")),
        KCMBRoute("B",cls,("approach","right")),
    )
    original=KCMBNetworkConfig(links,routes,.5,lane_policy="shared_head")
    # A genuine physical widening: one 30m pocket per movement (2 lanes in
    # the pocket region rather than the original 1). Never invent capacity by
    # merely setting lane_policy=independent_turn on a one-lane approach.
    split=TurnPocketLayout(
        approach="approach",
        pocket_length_m=30.,
        groups=(
            PocketGroup("A_turn",("A",),1,1.),
            PocketGroup("B_turn",("B",),1,1.),
        ),
    )
    compiled=compile_turn_pockets(original,split)
    return original,compiled


def mass_check(m,st,total):
    for k in range(len(total)):
        active=sum(m.cell_class_mass(st,ln.name,k) for ln in m.config.links)
        residual=total[k]-st.pending[k]-st.completed[k]-active
        if abs(residual)>2e-8*max(1.,abs(total[k])):
            raise AssertionError(("mass-ledger",k,residual,total[k]))
    for l in m.config.links:
        metres=m.occupied_metres(st,l.name)
        if metres< -1e-8 or metres>l.length_m*l.lanes+1e-8:
            raise AssertionError(("invalid physical storage",l.name,metres))


def run():
    original,compiled=config()
    pocket=dict(compiled.pocket_link_by_group)
    pA,pB=pocket["A_turn"],pocket["B_turn"]
    assert compiled.geometry.added_lane_metres==30.
    assert compiled.geometry.pocket_region_lanes==2
    assert original.links[0].lanes==1
    assert len(compiled.config.links)==5
    # Both models: same 2 vehicles and same two source routes, but a
    # DIFFERENT PHYSICAL POSITION/GEOMETRY. It is not a fixed-V03 benchmark.
    old=KCMBBoundedNetwork(original,backend="rust")
    new=KCMBBoundedNetwork(compiled.config,backend="rust")
    a=old.initial_profile({"approach":(1.,1.)})
    b=new.initial_profile({pA:(1.,0.),pB:(0.,1.)})
    a,r_old=old.step(a,(0.,0.),gates={("approach","left"):0.,("approach","right"):1.})
    b,r_new=new.step(b,(0.,0.),gates={(pA,"left"):0.,(pB,"right"):1.})
    left_red_old=r_old["turn_flows"].get(("approach","left","A"),0.)
    right_old=r_old["turn_flows"].get(("approach","right","B"),0.)
    left_red_new=r_new["turn_flows"].get((pA,"left","A"),0.)
    right_new=r_new["turn_flows"].get((pB,"right","B"),0.)
    assert left_red_old==left_red_new==right_old==0.
    assert right_new>0.
    assert r_old["mass_error_max_veh"]<1e-8 and r_new["mass_error_max_veh"]<1e-8

    # An independent finite-state benchmark from empty storage, identical
    # deterministic source offers and signal schedule in the physical
    # right-of-way (not a fitted model or observed real-city demand).
    rounds=1200
    results={}
    for label,model in (("one_shared_lane",old),("two_physical_turn_pockets",new)):
        st=model.initial()
        offered=[0.,0.]
        start=perf_counter()
        max_mass_error=0.
        blocked_right_during_A_red=0
        for i in range(rounds):
            amount=(0.02,0.02)
            offered[0]+=amount[0]
            offered[1]+=amount[1]
            green_A=float(i%32>=16)
            if label=="one_shared_lane":
                gates={("approach","left"):green_A,
                       ("approach","right"):1.}
            else:
                gates={(pA,"left"):green_A,
                       (pB,"right"):1.}
            st,rc=model.step(st,amount,gates=gates)
            max_mass_error=max(max_mass_error,rc["mass_error_max_veh"])
            if green_A==0.:
                if label=="one_shared_lane":
                    val=rc["turn_flows"].get(("approach","right","B"),0.)
                else:
                    val=rc["turn_flows"].get((pB,"right","B"),0.)
                if val>0:
                    blocked_right_during_A_red+=1
            mass_check(model,st,offered)
            assert rc["state_scalar_capacity"]==model.state_scalars
        elapsed=perf_counter()-start
        state_wire=model.to_bytes(st)
        # No packet split counter or individual birth-time/route queue grows
        # in this fixed-dimensional 6-moment representation.
        results[label]={
            "physical_link_count":len(model.config.links),
            "route_count":len(model.config.routes),
            "total_offered_by_route":offered,
            "completed_by_route":list(st.completed),
            "pending_by_route":list(st.pending),
            "state_scalars":model.state_scalars,
            "state_serialized_bytes":len(state_wire),
            "model_id":model.model_id,
            "max_step_mass_error_veh":max_mass_error,
            "elapsed_s":elapsed,
            "right_turn_positive_steps_while_A_red":blocked_right_during_A_red,
            "source_and_signal_test_is_synthetic":True,
        }
    assert results["one_shared_lane"]["state_scalars"]==42
    assert results["two_physical_turn_pockets"]["state_scalars"]==66
    assert results["one_shared_lane"]["total_offered_by_route"]==results["two_physical_turn_pockets"]["total_offered_by_route"]
    assert results["one_shared_lane"]["state_scalars"]<results["two_physical_turn_pockets"]["state_scalars"]
    data={
        "schema":"V03_KCMB_PHYSICAL_NON_FIFO_ALTERNATIVE_COMPARATOR_20261120_V1",
        "physical_model":"KCMB six kinetic Markov moments + conservative network node / explicit turning lanes",
        "strict_original_V03_FIFOnetwork_legacy_checkpoint_equivalent":False,
        "original_V03_full_day_acceptance_credit":0,
        "sample_parameters":"unchanged previous KCMB unit fixture; not fitted from observations",
        "original_100k_resident_city_simulated":False,
        "link_lengths_m":[100.,100.,100.],
        "pocket_length_m":30.,
        "added_physical_lane_metres":30.,
        "simulation_dt_s":.5,
        "simulated_ticks":rounds,
        "simulated_duration_s":rounds*.5,
        "total_source_offers_each_route":rounds*.02,
        "same_route_labels_and_signals":True,
        "one_step_red_A_green_B":{
           "shared_B_out":right_old,
           "pocket_B_out":right_new,
           "shared_A_out":left_red_old,
           "pocket_A_out":left_red_new,
        },
        "results":results,
        "Rust_KCMB_backend_binary_sha256":native_binary_provenance()["sha256"],
        "created_utc":datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "claims_not_made":[
            "No calibrated urban-driver alpha/nu/tau or observed validation",
            "No equivalence to original packet birth-time and perfect network FIFO",
            "No identical geometry (physical turn pockets add road lane metres)",
            "No V03 full 86400s x9 acceptance from synthetic 600s",
        ],
    }
    out=ROOT/"artifacts/v03_composed_events_20261120/C4_KCMB_PHYSICAL_ALTERNATIVES.json"
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(data,indent=2,sort_keys=True,ensure_ascii=False)+"\n")
    print(json.dumps({
       "shared_scalar_count":results["one_shared_lane"]["state_scalars"],
       "pocket_scalar_count":results["two_physical_turn_pockets"]["state_scalars"],
       "shared_red_B":right_old,"physical_pocket_red_B":right_new,
       "mass_error_max":max(v["max_step_mass_error_veh"] for v in results.values()),
       "elapsed_s_by_model":{k:round(v["elapsed_s"],3) for k,v in results.items()},
       "state_wire_bytes":{k:v["state_serialized_bytes"] for k,v in results.items()},
    },sort_keys=True))


if __name__=="__main__":
    run()
