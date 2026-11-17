#!/usr/bin/env python3
"""Paired finite-response merge/diverge experiment; not full-city acceptance."""
import argparse
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from metroflow.active_suffix.common import Signal  # noqa: E402
from metroflow.foundation_kinetics import VehicleClass  # noqa: E402
from metroflow.ordered_lane import Lane  # noqa: E402
from metroflow.ordered_network import Group, Route  # noqa: E402
from metroflow.packet_network import PacketNetwork  # noqa: E402
from metroflow.v1.kinetics import ClassMass  # noqa: E402
from metroflow.v1.transport import FiniteResponseMotion  # noqa: E402


def fixture(dt, width):
    car = VehicleClass("car", preferred_mps=12., response_s=1.5)
    bus = VehicleClass("bus", preferred_mps=9., response_s=3., length_m=9.)
    groups = (
        Group("a", "home-a", "merge", Lane(length_m=5., speed_mps=12., entry_rate=2., exit_rate=.8)),
        Group("b", "home-b", "merge", Lane(length_m=7., speed_mps=12., entry_rate=2., exit_rate=.7)),
        Group("c", "merge", "fork", Lane(length_m=8., speed_mps=12., entry_rate=1.5, exit_rate=.24),
              signal=Signal(10., 6.)),
        Group("d", "fork", "dest-d", Lane(length_m=5., speed_mps=12., entry_rate=1., exit_rate=.8)),
        Group("e", "fork", "dest-e", Lane(length_m=5., speed_mps=12., entry_rate=1., exit_rate=.8)),
    )
    routes = (Route("car-a", ("a", "c", "d")), Route("car-b", ("b", "c", "e")),
              Route("bus", ("b", "c", "d")))
    motion = FiniteResponseMotion((ClassMass(car, 1., latent=.8, gap_scale_m=4.),
                                   ClassMass(bus, 1., latent=.7, gap_scale_m=4.)),
                                  (("car", 8.), ("bus", 6.)))
    return PacketNetwork(groups, routes, dt_s=dt, windows=(("e", 10., 15., 0.),),
        record_budget=100000, event_budget=100000,
        vehicle_classes={"car-a": car, "car-b": car, "bus": bus},
        space_capacities_m={g.id: 200. for g in groups}, standing_gap_m=2.,
        motion=motion, preserve_entry_intervals=True, entry_projection_width_s=width)


def offers(t, dt):
    result = []
    for tag, start, end, rate in (("car-a", 0., 12., .19),
                                   ("car-b", 1., 14., .15), ("bus", 2., 12., .025)):
        lo, hi = max(t, start), min(t+dt, end)
        if hi > lo:
            # Same integrated physical supply for each dt. Availability is
            # released at the next boundary, as in the existing T04 contract.
            result.append((tag, rate*(hi-lo), rate*(hi-lo)*(lo+hi)/2))
    return result


def execute(dt, width, horizon, backend):
    reference = fixture(dt, width)
    model = reference
    if backend == "rust":
        from metroflow.v1.native_road import NativeRoadNetwork
        model = NativeRoadNetwork(reference)
    s = model.initial()
    curve = []
    pending = ()
    peak_parts = peak_packets = 0
    conservation = 0.
    local_cost = 0.
    started = time.perf_counter()
    bytag = {key: 0. for key in reference.routes}
    status = "EXECUTED"
    reason = None
    saved = None
    intervals = []
    for i in range(round(horizon/dt)):
        t = i*dt
        intervals.append(pending)
        try:
            s, events = model.advance_interval(s, dt, pending)
        except (MemoryError, ArithmeticError, RuntimeError, ValueError) as exc:
            status, reason = "FAILED", type(exc).__name__ + ": " + str(exc)
            break
        pending = offers(t, dt)
        counts = reference.counts(s)
        peak_parts = max(peak_parts, counts["parts"])
        peak_packets = max(peak_packets, counts["packets"])
        stored = math.fsum(c.occupancy for c in s.cells) + math.fsum(p.mass for q in s.pending for p in q)
        conservation = max(conservation, abs(s.released - s.completed - stored))
        local_cost += model.projection_diagnostics()["local_w1_bound_veh_s"]
        for e in events:
            if e.destination is None:
                bytag[e.tag] += e.mass
        curve.append(dict(time_s=s.time_s, completed_veh=s.completed,
                          occupancy_veh=[c.occupancy for c in s.cells],
                          parts=counts["parts"], packets=counts["packets"]))
        if i == round(horizon/dt)//2-1:
            saved = s
    replay = None
    if status == "EXECUTED" and saved is not None:
        resumed = saved
        for i in range(round(saved.time_s/dt), round(horizon/dt)):
            resumed, _ = model.advance_interval(resumed, dt, intervals[i])
        replay = asdict(resumed) == asdict(s)
    return dict(status=status, reason=reason, backend=backend, dt_s=dt, width_s=width,
                identity=reference.identity, simulated_s=s.time_s,
                released_veh=s.released, completed_veh=s.completed,
                completed_by_tag=bytag, system_vehicle_seconds=s.system_vehicle_seconds,
                exit_moment_veh_s=s.exit_moment, peak_parts=peak_parts, peak_packets=peak_packets,
                max_mass_residual_veh=conservation,
                summed_local_projection_cost_veh_s=local_cost,
                projection_cost_scope="sum of local proposal costs, not network error bound; replay excluded",
                replay_equal=replay, wall_s=time.perf_counter()-started, curve=curve)


def comparison(a, b):
    ac = {round(x["time_s"], 9): x for x in a["curve"]}
    common = [(ac[round(x["time_s"], 9)], x) for x in b["curve"]
              if round(x["time_s"], 9) in ac]
    return dict(reference_dt_s=a["dt_s"], reference_width_s=a["width_s"],
                candidate_dt_s=b["dt_s"], candidate_width_s=b["width_s"],
                sampled_common_times=len(common),
                max_completed_curve_difference_veh=max(
                    (abs(x["completed_veh"]-y["completed_veh"]) for x,y in common), default=None),
                max_cell_occupancy_difference_veh=max(
                    (abs(p-q) for x,y in common for p,q in zip(x["occupancy_veh"],y["occupancy_veh"])),
                    default=None),
                final_exit_moment_difference_veh_s=abs(a["exit_moment_veh_s"]-b["exit_moment_veh_s"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("python", "rust"), default="python")
    parser.add_argument("--horizon-s", type=float, default=60.)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if not math.isfinite(args.horizon_s) or args.horizon_s <= 0 or args.horizon_s % 1:
        parser.error("horizon must be a positive whole second")
    cases = [(1., 0.), (1., 1.), (1., .5), (1., .25), (.5, 0.), (.5, .5), (.5, .25)]
    runs = [execute(dt,h,args.horizon_s,args.backend) for dt,h in cases]
    references = {r["dt_s"]: r for r in runs if r["width_s"] == 0}
    comparisons = [comparison(references[r["dt_s"]], r) for r in runs if r["width_s"]]
    comparisons.append(comparison(references[.5], references[1.]))
    paths = ["src/metroflow/packet_network.py", "src/metroflow/entry_projection.py",
             "src/metroflow/v1/transport.py", "crates/metroflow-rust/src/v1_road.rs"]
    output = dict(scenario="synthetic_finite_response_merge_diverge_signal_closure_v1",
                  scope="bounded numerical comparison; full-city calibration/acceptance not established",
                  python=platform.python_version(), platform=platform.platform(),
                  base_commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
                  source_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths},
                  runs=runs, comparisons=comparisons)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(output,ensure_ascii=False,indent=2,allow_nan=False)+"\n")
    print(json.dumps([{k:r[k] for k in ("dt_s","width_s","status","completed_veh","peak_parts",
                     "max_mass_residual_veh","replay_equal","wall_s")} for r in runs],indent=2))
    return 0 if all(r["status"]=="EXECUTED" and r["replay_equal"] for r in runs) else 2


if __name__ == "__main__":
    raise SystemExit(main())
