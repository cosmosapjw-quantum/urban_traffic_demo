"""Reproduce the projected Valley experiment. The default runs one solver process at a time."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
H = 25720
NATIVE = Path("artifacts/v03_measure_lift_20261123/S06_fresh0.json")
SNAP_FIELDS = ("time_s", "released_veh", "road_admitted_veh", "road_exited_veh",
               "completed_veh", "active_veh", "on_road_veh", "max_ledger_error_veh")
END_FIELDS = ("outward_veh", "planned_outward_packets", "processed_events",
              "queue_wait_veh_s", "bottleneck_id", "bottleneck_wait_veh_s",
              "bottleneck_max_wait_s", "trip_time_veh_s")
CASES = {"base_1200": (1200,-1,1,86400), "base_600": (600,-1,1,86400),
         "base_300": (300,-1,1,86400), "shock_300": (300,None,.5,86400),
         "prefix_60": (60,-1,1,H), "prefix_20": (20,-1,1,H), "prefix_10": (10,-1,1,H),
         "base_150": (150,-1,1,86400), "stress_300": (300,None,.1,86400),
         "stress_150": (150,None,.1,86400)}
TOY = "1 1 2 1 50000\n10 0.5\n1 0\n0 100 200 300\n0 0 0 1 0 0\n0 0 0 1 0 0\n"


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse(path):
    snapshots, purposes, end = {}, {}, {}
    for line in path.read_text().splitlines():
        tag, *data = line.split()
        numbers = list(map(float, data))
        if tag == "snap":
            snapshots[str(int(numbers[0]))] = dict(zip(SNAP_FIELDS, numbers, strict=True))
        elif tag == "purpose":
            purposes[("work","school","service")[int(numbers[0])]] = dict(outward=numbers[1], inbound=numbers[2])
        elif tag == "end":
            end = dict(zip(END_FIELDS, numbers, strict=True))
            for key in ("planned_outward_packets","processed_events","bottleneck_id"):
                end[key] = int(end[key])
        else:
            raise ValueError(tag)
    if not end or not snapshots:
        raise ValueError(f"Incomplete run {path}")
    return dict(snapshots=snapshots, purpose_completions_veh=purposes, summary=end)


def collect(repo, out, *, partial):
    a = json.loads((out/"input_summary.json").read_text())
    ids = json.loads((out/"link_ids.json").read_text())
    reference = json.loads((repo/NATIVE).read_text())
    native = reference["final_execution_report"]
    service = native["service"]
    assert service["time_s"] == H and service["bus_road_vehicles"] == 0
    assert service["completed_bus_vehicles"] == 4 and service["freight_completed_vehicles"] == 0
    assert native["city_identity"] == a["city_identity"] and native["schedule_identity"] == a["schedule_identity"]
    assert native["construction"]["road_legs"] == a["projected_vehicle_legs"]
    assert native["construction"]["unique_paths"] == a["distinct_legal_paths"]
    assert file_sha(out/"network.txt") == a["extracted_input_sha256"]
    toy = parse(out/"toy.out")
    assert [toy["summary"][k] for k in ("processed_events","queue_wait_veh_s","trip_time_veh_s")] == [16,2,50]
    assert toy["snapshots"]["25720"]["completed_veh"] == 2 and toy["snapshots"]["86400"]["completed_veh"] == 4
    bs = service["completed_bus_vehicles"]
    expected = dict(road_admitted_veh=service["road_released_veh"]-bs,road_exited_veh=service["road_completed_veh"]-bs,
                    on_road_veh=service["road_released_veh"]-service["road_completed_veh"])
    cases = {}
    for name, (width, target, fraction, stop) in CASES.items():
        raw, times = out/(name+".out"), out/(name+".time")
        if partial and (not raw.exists() or not raw.stat().st_size or not times.exists() or not times.stat().st_size):
            continue
        runs = parse(raw)
        elapsed, rss = times.read_text().split()
        s = runs["summary"]
        s["bottleneck_link"] = ids[s["bottleneck_id"]]
        s["wall_s"],s["peak_rss_kib"] = float(elapsed),int(rss)
        end = runs["snapshots"][str(stop)]
        s["mean_completed_trip_s"] = s["trip_time_veh_s"]/end["completed_veh"] if end["completed_veh"] else None
        s["max_snapshot_error_veh"] = max(r["max_ledger_error_veh"] for r in runs["snapshots"].values())
        if stop==86400:
            assert math.isclose(end["completed_veh"], a["projected_vehicles"], abs_tol=1e-7,rel_tol=0)
            assert end["active_veh"] == end["on_road_veh"] == 0
        s["raw_sha256"] = file_sha(raw)
        runs["scenario"] = dict(max_bin_s=width,capacity_factor=fraction,stop_s=stop,
                            shocked_link=ids[cases["base_300"]["summary"]["bottleneck_id"]] if target is None else None)
        snap = runs["snapshots"][str(H)]
        runs["native_car_comparison"] = {
          k: dict(native=v,projected=snap[k],delta=snap[k]-v,relative_delta=snap[k]/v-1)
          for k,v in expected.items()}
        cases[name] = runs
    gate_access = json.loads((out/"onset_access.json").read_text())
    for row in gate_access.values():
        row["source_minus_native_admitted_veh"] = row["source_access_veh"] - expected["road_admitted_veh"]
    evidence = dict(analytic_onset_access_cdf=gate_access,schema="valley-routed-car-point-queues-v1",input=a,
        extraction_router_basis_git="5c8486cc7d8ba090b7883bff5c0f1fb3ed1448c3",
        prepared_input_fraction_of_car_veh=a["projected_vehicles"]/a["original_mode_vehicles"]["car"],
        native_reference=dict(file=str(NATIVE),sha256=file_sha(repo/NATIVE),git=reference["source_commit"],
                              physical_total_admitted_veh=service["road_released_veh"],
                              physical_total_exited_veh=service["road_completed_veh"],
                              completed_single_segment_buses=bs,bus_active_veh=service["bus_road_vehicles"],
                              first_freight_window_s=32400,car_reference=expected),
        analytic_fixture=toy,sources_sha256={p:file_sha(HERE/p) for p in
            ("point_queue.cpp","prepare_point_queue.py","run_point_queue.py")},cases=cases)
    if (out/"lazy_300.time").exists() and (out/"lazy_300.out").stat().st_size:
        t,r=(out/"lazy_300.time").read_text().split()
        evidence["lazy_300_validation"]=dict(eager_raw_sha=file_sha(out/"base_300.out"),
             lazy_raw_sha=file_sha(out/"lazy_300.out"),wall_s=float(t),peak_rss_kib=int(r))
        assert file_sha(out/"base_300.out")==file_sha(out/"lazy_300.out")
    (out/"RESULTS.json").write_text(json.dumps(evidence,indent=2,allow_nan=False)+"\n")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("repo",type=Path)
    p.add_argument("output_directory",type=Path)
    p.add_argument("--collect-only",action="store_true")
    p.add_argument("--partial",action="store_true",help="Collect only already completed cases")
    args=p.parse_args()
    repo,out=args.repo.resolve(),args.output_directory.resolve()
    if not args.collect_only:
        out.mkdir(parents=True,exist_ok=True)
        if any(out.iterdir()):
            p.error("Use a fresh output directory to preserve existing evidence.")
        subprocess.run([sys.executable,HERE/"prepare_point_queue.py",repo,out],check=True,cwd=repo)
        binary=out/"point_queue"
        subprocess.run(["g++","-std=c++17","-O3","-Wall","-Wextra","-pedantic",HERE/"point_queue.cpp","-o",binary],check=True)
        (out/"toy.txt").write_text(TOY)
        with (out/"toy.out").open("w") as stream:
            subprocess.run([binary,out/"toy.txt","100","-1","1"],stdout=stream,check=True)
        for name,(width,target,factor,stop) in CASES.items():
            if target is None:
                target=parse(out/"base_300.out")["summary"]["bottleneck_id"]
            cmd=["/usr/bin/time","-f","%e %M","-o",str(out/(name+".time")),
                 str(binary),str(out/"network.txt"),str(width),str(target),str(factor),str(stop)]
            with (out/(name+".out")).open("w") as stream:
                subprocess.run(cmd,stdout=stream,check=True)
    collect(repo,out,partial=args.partial)


if __name__=="__main__":
    main()
