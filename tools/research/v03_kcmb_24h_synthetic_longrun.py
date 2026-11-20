#!/usr/bin/env python3
"""Independent synthetic 24h, fixed-state KCMB physical alternatives.

NOT the original V03 100k-resident city / acceptance: uses exactly three or
five directed links, two named physical routes, previously fixed microkinetic
coefficients and a deterministic synthetic source/signal. Tests fixed-state
numerical conservation over a full 86400 simulated seconds, not predictive
fidelity against traffic measurements.
"""
from datetime import datetime,timezone
from pathlib import Path
from time import perf_counter
import json
import math
import resource
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/"src")]
from tools.research.v03_kcmb_physical_alternatives import config, mass_check
from metroflow.v1.kcmb_network import KCMBBoundedNetwork
from metroflow.v1.native_engine import native_binary_provenance

ROUNDS=172800
DT=0.5
OFFER=(0.02,0.02)


def do_one(name,config_obj,pocket):
    model=KCMBBoundedNetwork(config_obj,backend="rust")
    state=model.initial()
    total=[0.,0.]
    max_residual=0.
    mass_verify_count=0
    redB=0
    start=perf_counter()
    for tick in range(ROUNDS):
        total[0]+=OFFER[0]
        total[1]+=OFFER[1]
        green_A=float(tick%32>=16)
        if pocket is None:
            gates={("approach","left"):green_A,
                   ("approach","right"):1.}
        else:
            gates={(pocket["A_turn"],"left"):green_A,
                   (pocket["B_turn"],"right"):1.}
        state,receipt=model.step(state,OFFER,gates=gates)
        max_residual=max(max_residual,receipt["mass_error_max_veh"])
        if tick%1000==0 or tick==ROUNDS-1:
            mass_check(model,state,total)
            assert receipt["state_scalar_capacity"]==model.state_scalars
            mass_verify_count+=1
    elapsed=perf_counter()-start
    assert state.tick==ROUNDS
    assert abs(sum(total)-ROUNDS*sum(OFFER))<1e-6
    payload=model.to_bytes(state)
    replay=model.from_bytes(payload)
    assert replay==state
    assert 0<model.state_scalars<200
    assert 0<len(payload)<4096
    assert max_residual<1e-6
    return {
      "native_backend":"Rust KCMB node and kinetic network",
      "geometry":name,
      "physical_link_count":len(model.config.links),
      "route_count":len(model.config.routes),
      "state_scalars":model.state_scalars,
      "scalar_state_capacity_has_constant_size":True,
      "simulated_ticks":ROUNDS,
      "dt_s":DT,
      "simulated_duration_s":ROUNDS*DT,
      "source_offered_veh_per_route":total,
      "final_released":list(state.released),
      "final_completed":list(state.completed),
      "final_pending":list(state.pending),
      "max_reported_step_mass_ledger_error_veh":max_residual,
      "independent_mass_and_lane_storage_checks":mass_verify_count,
      "checkpoint_bytes":len(payload),
      "checkpoint_same_model_exact_reload":True,
      "elapsed_wall_s":elapsed,
      "microphysics_parameter_fit":False,
      "models_compared_have_different_physical_lane_geometry":True,
    }


def main():
    original,compiled=config()
    pockets=dict(compiled.pocket_link_by_group)
    rows={}
    rows["shared_single_lane"]=do_one("shared_single_lane",original,None)
    print("KCMB_FULL_SYNTH_24H_ONE",rows["shared_single_lane"],flush=True)
    rows["dedicated_physical_turn_pockets"]=do_one(
        "dedicated_physical_turn_pockets",compiled.config,pockets)
    print("KCMB_FULL_SYNTH_24H_TWO",rows["dedicated_physical_turn_pockets"],flush=True)
    assert rows["shared_single_lane"]["state_scalars"]==42
    assert rows["dedicated_physical_turn_pockets"]["state_scalars"]==66
    assert rows["shared_single_lane"]["simulated_duration_s"]==86400.
    assert rows["dedicated_physical_turn_pockets"]["simulated_duration_s"]==86400.
    data={
      "schema":"V03_KCMB_RADICAL_SYNTHETIC_24H_FIXED_STATE_20261120_V1",
      "research_model":"6 kinetic moments per route/link, conservative node, geometric partial FIFO",
      "original_V03_100000_resident_city_simulated":False,
      "original_V03_full_day_release_accepted":False,
      "physical_model_not_exact_original_FIFO_checkpoint":True,
      "simulated_one_day_in_a_synthetic_three_or_five_link_network":True,
      "input_coefficients":"Reused unchanged source-fixed unit-test values, no fit",
      "physical_traffic_sources":"constant 0.02 veh per route each 0.5s, synthetic and not urban observational demand",
      "signal_policy":"red A for first 16 of each 32 half-second ticks, right B always green",
      "number_of_simulated_seconds":86400.,
      "original_source_model_matrix_untouched":True,
      "current_compiled_native_sha256":native_binary_provenance()["sha256"],
      "cases":rows,
      "claim_scope":"numerically checked 86400s for a tiny synthetic network; no city-scale prediction or true vehicle-level FIFO",
      "created_utc":datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    p=ROOT/"artifacts/v03_composed_events_20261120/C10_KCMB_SYNTHETIC_24H.json"
    p.write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")
    print("KCMB_FULL_DAY_SYNTHETIC_FIXED_SCALARS",
          json.dumps({k:(v["state_scalars"],v["checkpoint_bytes"],v["elapsed_wall_s"])
                      for k,v in rows.items()},sort_keys=True),flush=True)


if __name__=="__main__":
    main()
