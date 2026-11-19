#!/usr/bin/env python3
"""Actual KCMB numerical time integration under explicitly hypothetical bus-probe laws.

The two Chicago days are REAL City source records; the model's lane number,
offered vehicle-equivalents, source composition, free-flow target U and GPS
selection weights are SCENARIO INPUTS, not inferred from these records.

The run demonstrates conditional observability and kinetic six-moment support,
NOT validation of CTA aggregation or city-scale V1. It is fully offline.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
import platform
import resource
import statistics
from time import perf_counter

from metroflow.v1.chicago_observations import (
    parse_observation_days, evaluate_speed_only,
)
from metroflow.v1.kcmb import KCMBClass, KCMBConfig, KCMBCorridor
from metroflow.v1.kcmb_probe_observation import (
    AffineProbeWeights, pooled_probe_mean_speed,
    selected_probe_mean_speed, stationary_six_moments,
)


_WARMUP_STEPS=240
_SAMPLES_PER_SLOT=60
_SLOTS=12
_DT_SECONDS=10.
_U_MPS=30.*.44704
_RATE_K=0.5
_TAU_SECONDS=3.
_BUS_FOOTPRINT_M=8.
_SOURCE_VEH_PER_SECOND=.3
_INITIAL_MASS_VEH=20.


def _load_field(root: Path):
    manifest=json.loads((root/"artifacts/kcmb_field_20261119/SOURCE_MANIFEST.json").read_bytes())
    if manifest.get("dataset_id")!="4g9f-3jbs" or str(manifest.get("segment_id"))!="1221":
        raise ValueError("City speed-source identity mismatch")
    records={}
    hashes={}
    for item in manifest["source_requests"]:
        part=item["split"]
        if part not in ("calibration","holdout") or part in records:
            raise ValueError("invalid or duplicate observation split")
        relative=Path(item["file"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("source file outside repository")
        file=(root/relative).resolve()
        if not file.is_relative_to(root.resolve()):
            raise ValueError("source file escapes project root")
        raw=file.read_bytes()
        digest=sha256(raw).hexdigest()
        if digest!=item["sha256"]:
            raise ValueError("Chicago raw source SHA-256 mismatch")
        records[part]=(item["date_local"],json.loads(raw))
        hashes[part]=digest
    if set(records)!={"calibration","holdout"}:
        raise ValueError("both dates required")
    cal_day,cal_rows=records["calibration"]
    hold_day,hold_rows=records["holdout"]
    obs=parse_observation_days(
        cal_rows,hold_rows,
        calibration_day=cal_day,
        holdout_day=hold_day,
        segment_id=str(manifest["segment_id"]),
    )
    if obs.segment.street!=manifest["street"] or obs.segment.direction!=manifest["direction"]:
        raise ValueError("Chicago spatial identity mismatch")
    return obs,evaluate_speed_only(obs),hashes


def _mae(expected,observed):
    return math.fsum(abs(x-y) for x,y in zip(expected,observed))/len(expected)


def _rmse(expected,observed):
    return math.sqrt(math.fsum((x-y)**2 for x,y in zip(expected,observed))/len(expected))


def _backend_run(obs,mu_cal:float,backend:str)->dict:
    p=mu_cal/_U_MPS
    if not 0<p<1:
        raise ValueError("physical source mean must lie strictly inside assumed bus U")
    bus=KCMBClass(
        "hypothetical_CTA_bus_class",
        vmax_mps=_U_MPS,footprint_m=_BUS_FOOTPRINT_M,
        alpha_per_s=_RATE_K*p,nu_per_s=_RATE_K*(1-p),
        tau_s=_TAU_SECONDS,source_p=p,source_speed_fraction=p,
    )
    cfg=KCMBConfig(
        cells=1,cell_length_m=obs.segment.length_m,
        lanes=1,dt_s=_DT_SECONDS,
        capacity_veh_per_s=_SOURCE_VEH_PER_SECOND,
        backward_wave_mps=5.,
        classes=(bus,),
    )
    model=KCMBCorridor(cfg,backend=backend)
    start=perf_counter()
    state=model.initial_profile(((_INITIAL_MASS_VEH,),),
                                latent=(p,),speed_fraction=(p,))
    maximum_mass_error=0.
    for i in range(_WARMUP_STEPS):
        state,receipt=model.step(
            state,(_SOURCE_VEH_PER_SECOND*_DT_SECONDS,),green=1.)
        maximum_mass_error=max(maximum_mass_error,receipt["mass_error_max_veh"])
    initial_stage=tuple(state.moments)
    mass=initial_stage[0]+initial_stage[1]
    mean_u=(initial_stage[2]+initial_stage[3])/mass
    sample_var=(initial_stage[4]+initial_stage[5])/mass-mean_u*mean_u
    local_stationary=stationary_six_moments(p,_RATE_K,_TAU_SECONDS)
    local_stationary_var=(local_stationary[4]+local_stationary[5])-p*p

    selection_hypotheses={
        "unweighted":AffineProbeWeights(),
        "speed_upweighted":AffineProbeWeights(1.,1.,1.,1.),
        "speed_downweighted":AffineProbeWeights(1.,-.8,1.,-.8),
    }
    selected_by_slot={name:[] for name in selection_hypotheses}
    snapshots_at_10min=[]
    for bin_index in range(_SLOTS):
        samples=[]
        for within_bin in range(_SAMPLES_PER_SLOT):
            state,receipt=model.step(
                state,(_SOURCE_VEH_PER_SECOND*_DT_SECONDS,),green=1.)
            maximum_mass_error=max(maximum_mass_error,receipt["mass_error_max_veh"])
            samples.append(tuple(state.moments))
        snapshots_at_10min.append(tuple(state.moments))
        for name,weights in selection_hypotheses.items():
            # A declared support-weighted Riemann-sum time pooling of this
            # model's microscopic vehicle-equivalent opportunities. The City
            # dataset does not confirm this sampling or aggregation protocol.
            selected_by_slot[name].append(pooled_probe_mean_speed(
                ((s,_U_MPS,weights) for s in samples)
            ))
    by_real={row.slot:row.speed_mps for row in obs.holdout}
    indices=tuple(range(42,54))
    matching=[k for k in indices if k in by_real]
    if not matching:
        raise ValueError("no real holdout comparable ten-minute speed slots")
    real=[by_real[k] for k in matching]
    predictions={}
    for name,values in selected_by_slot.items():
        aligned=[values[k-42] for k in matching]
        predictions[name]={
            "weights":{
                "a0":selection_hypotheses[name].a0,
                "b0":selection_hypotheses[name].b0,
                "a1":selection_hypotheses[name].a1,
                "b1":selection_hypotheses[name].b1,
            },
            "predicted_speed_mps_by_clock_slot":values,
            "holdout_rmse_mps":_rmse(aligned,real),
            "holdout_mae_mps":_mae(aligned,real),
            "clock_slots_used":matching,
            "observation_law_status":"HYPOTHETICAL_AFFINE_MICRO_PROBE_SELECTION",
        }
    checkpoint=model.to_bytes(state)
    return {
        "backend":backend,
        "actual_physical_kernel":"KCMBCorridor six-moment local Markov + finite-volume transport",
        "bus_population_assumed_not_observed":True,
        "model_id":model.model_id,
        "steps_executed":state.tick,
        "warmup_steps":_WARMUP_STEPS,
        "forecast_steps":_SLOTS*_SAMPLES_PER_SLOT,
        "conditional_scenario_parameters":{
            "vmax_mps":_U_MPS,
            "vmax_assumed_mph":30.,
            "p_calibration":p,
            "switch_sum_per_s":_RATE_K,
            "alpha_per_s":_RATE_K*p,
            "nu_per_s":_RATE_K*(1-p),
            "tau_s":_TAU_SECONDS,
            "cell_length_m":obs.segment.length_m,
            "footprint_m":_BUS_FOOTPRINT_M,
            "cell_count":1,
            "lanes_assumed":1,
            "dt_s":_DT_SECONDS,
            "source_vehicle_equivalents_per_s":_SOURCE_VEH_PER_SECOND,
            "signal_at_sink":"assumed_always_green",
            "start_mass_veh":_INITIAL_MASS_VEH,
            "observation_window_seconds":_SAMPLES_PER_SLOT*_DT_SECONDS,
            "declared_source_speed_fraction":p,
            "declared_source_latent_probability":p,
        },
        "kinetic_bulk_speed_after_warmup_mps":_U_MPS*mean_u,
        "transport_variance_u_after_warmup":sample_var,
        "local_stationary_variance_u":local_stationary_var,
        "end_observed_mass_moment":tuple(state.moments),
        "mass_active_end_veh":state.moments[0]+state.moments[1],
        "source_veh_by_class":state.released,
        "completed_veh_by_class":state.completed,
        "pending_veh_by_class":state.pending,
        "all_class_mass_ledger_max_error_veh":maximum_mass_error,
        "selection_hypotheses":predictions,
        "end_checkpoint_sha256":sha256(checkpoint).hexdigest(),
        "end_checkpoint_bytes":len(checkpoint),
        "elapsed_compute_s":perf_counter()-start,
        "peak_rss_kib_whole_python_process":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }


def run_probe_scenarios(root:Path,*,backends=("python","rust")) -> dict:
    root=Path(root).resolve()
    if (isinstance(backends,str) or not isinstance(backends,(tuple,list)) or not backends
        or any(b not in ("python","rust") for b in backends) or
        len(set(backends))!=len(backends)):
        raise ValueError("backend selection must be unique python and/or rust")
    observations,field_metrics,digests=_load_field(root)
    mean=field_metrics["calibration_speed_mean_mps"]
    if field_metrics["holdout_count"]!=12 or field_metrics["calibration_count"]!=12:
        raise ValueError("this fixture must have full 12+12 speed rows")
    models={backend:_backend_run(observations,mean,backend) for backend in backends}
    return {
        "schema":"KCMB_PROBE_SCENARIO_HOLDOUT_20261119",
        "project":"cosmosapjw-quantum/urban_traffic_demo",
        "actual_chicago_source_input":True,
        "actual_chicago_raw_dataset":"4g9f-3jbs",
        "field_source_sha256":digests,
        "field_segment_id":observations.segment.segment_id,
        "field_calibration_day":observations.calibration_day,
        "field_holdout_day":observations.holdout_day,
        "valid_calibration_speed_rows":len(observations.calibration),
        "valid_holdout_speed_rows":len(observations.holdout),
        "field_calibration_mean_mps":mean,
        "field_holdout_mean_mps":field_metrics["holdout_speed_mean_mps"],
        "field_reference_baseline_holdout_rmse_mps":
            field_metrics["equilibrium_baseline_holdout_rmse_mps"],
        "actual_field_observable":"CTA_BUS_GPS_ESTIMATED_SEGMENT_SPEED_ONLY",
        "real_KCMB_runtime_executed":True,
        "physical_parameter_identifiability":"NOT_IDENTIFIED_FROM_CTA_SPEED_ONLY",
        "city_observation_mechanism":"UNKNOWN_NOT_CLAIMED_AFFINE",
        "scenario_boundary_status":"ASSUMED_SOURCE_FLOW_FOOTPRINT_LANES_U_RATE_TAU_AND_SINK",
        "empirical_validity":"CONDITIONAL_SCENARIO_SCORED_NOT_CALIBRATED_REAL_TRAFFIC",
        "backend_results":models,
        "not_measured":[
            "true road vehicle counts",
            "road density or individual queue lengths",
            "actual CTA inclusion weights or GPS reporting algorithm",
            "actual speed limit, bus target U, micro Markov rates or relaxation time",
            "true lane turning-pocket and signal geometry",
            "individual bus GPS trajectories and travel-time distribution",
        ],
        "population_uncertainty":"single CTA estimated-speed holdout Monday and within-day correlation",
        "claim_limit":"Matched speed-only numerical scenario, not physical V03 acceptance",
        "python":platform.python_version(),
    }


def main() -> None:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--backend",choices=("python","rust","both"),default="both")
    ap.add_argument("--output",required=True)
    args=ap.parse_args()
    root=Path(__file__).resolve().parents[2]
    backends=("python","rust") if args.backend=="both" else (args.backend,)
    result=run_probe_scenarios(root,backends=backends)
    target=Path(args.output)
    if not target.is_absolute():
        target=root/target
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print(json.dumps({
        "runtime_executed":result["real_KCMB_runtime_executed"],
        "real_observed_holdout_rows":result["valid_holdout_speed_rows"],
        "backend_used":list(result["backend_results"]),
        "scenario_rmse_mps":{
            name:{selection:round(v["holdout_rmse_mps"],6)
                   for selection,v in data["selection_hypotheses"].items()}
            for name,data in result["backend_results"].items()
        },
        "field_validation_scope":result["empirical_validity"],
    },sort_keys=True))


if __name__=="__main__":
    main()
