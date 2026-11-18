#!/usr/bin/env python3
"""Isolated KCMB Python-vs-Rust equivalent-model timing and resource receipt.

No unmeasured V03 projections. Run each backend as its own process for RSS.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import math
import platform
import resource
import statistics
import sys
from pathlib import Path
from time import perf_counter_ns

from metroflow.v1.kcmb import KCMBClass, KCMBConfig, KCMBCorridor


def scenario(cells, backend):
    classes=(
        KCMBClass("car", vmax_mps=10., footprint_m=5.5,
                  alpha_per_s=.2, nu_per_s=.3, tau_s=2., source_p=1.,
                  source_speed_fraction=0.),
        KCMBClass("bus", vmax_mps=8., footprint_m=12.5,
                  alpha_per_s=.12, nu_per_s=.08, tau_s=3.5, source_p=.5,
                  source_speed_fraction=.3),
    )
    return KCMBCorridor(KCMBConfig(cells=cells,cell_length_m=20.,
        lanes=1,dt_s=1.,capacity_veh_per_s=.9,backward_wave_mps=5.,
        classes=classes),backend=backend)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--backend", choices=("python","rust"),required=True)
    parser.add_argument("--cells", type=int, default=64)
    parser.add_argument("--steps", type=int, default=500)
    parser.add_argument("--demand-scale", type=float, default=1.)
    parser.add_argument("--output", required=True)
    args=parser.parse_args()
    if args.cells<1 or args.steps<1 or not math.isfinite(args.demand_scale) or args.demand_scale<=0:
        parser.error("positive bounded workload")
    obj=scenario(args.cells,args.backend)
    state=obj.initial()
    total_nano=0
    elapsed=[]
    high_occupancy=0.
    max_residual=0.
    for tick in range(args.steps):
        arrival=(args.demand_scale*(.40+.07*(tick%4)),
                 args.demand_scale*(.12+.03*(tick%7)))
        green = 0. if (tick%120)<55 else 1.
        start=perf_counter_ns()
        state,receipt=obj.step(state,arrival,green=green)
        nanoseconds=perf_counter_ns()-start
        elapsed.append(nanoseconds)
        total_nano+=nanoseconds
        max_residual=max(max_residual,receipt["mass_error_max_veh"])
        if tick%25==0:
            high_occupancy=max(high_occupancy,
                               max(obj.cell_occupied_metres(state,i)
                                   for i in range(args.cells)))
    state_bytes=obj.to_bytes(state)
    timed=sorted(elapsed)
    out={
        "experiment":"KCMB 6 conditional moments fixed spatial cells; not original packet V03",
        "model_id":obj.model_id,
        "backend":args.backend,"cells":args.cells,"classes":obj.classes,
        "steps":args.steps,"demand_scale":args.demand_scale,
        "simulated_seconds":args.steps*obj.config.dt_s,
        "state_scalar_capacity":obj.state_scalars,
        "timed_step_total_s":total_nano/1e9,
        "median_step_us":statistics.median(timed)/1e3,
        "p95_step_us":timed[math.ceil(.95*len(timed))-1]/1e3,
        "peak_rss_kib_including_python":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "max_mass_residual_veh":max_residual,
        "max_sampled_occupied_lane_metres":high_occupancy,
        "source_veh_by_class":state.released,
        "completed_veh_by_class":state.completed,
        "pending_veh_by_class":state.pending,
        "remaining_active_veh_by_class":[sum(obj.cell_class_mass(state,i,a)
                                             for i in range(args.cells))
                                         for a in range(obj.classes)],
        "checkpoint_bytes":len(state_bytes),
        "checkpoint_sha256":sha256(state_bytes).hexdigest(),
        "first_12_moments":state.moments[:12],
        "python":platform.python_version(),
        "host":platform.node(),
        "physical_range":"1D multi-class; no strict FIFO, actual field calibration or V03 equality",
    }
    path=Path(args.output)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
    print(json.dumps({k:out[k] for k in
         ("backend","cells","steps","demand_scale","timed_step_total_s",
          "peak_rss_kib_including_python","state_scalar_capacity",
          "max_mass_residual_veh","checkpoint_sha256")}))


if __name__=="__main__":
    main()
