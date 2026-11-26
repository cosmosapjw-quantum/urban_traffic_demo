"""Extract original routed Valley car cohorts and link parameters from the V03 entry points."""
import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
import sys
import time


def main():
    p = argparse.ArgumentParser()
    p.add_argument("repo", type=Path)
    p.add_argument("out", type=Path)
    args = p.parse_args()
    repo, out = args.repo.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    sys.path[:0] = [str(repo / "native_binding"), str(repo / "src"), str(repo)]
    from _metroflow_rust import V1RoutingGraph
    from tools.run_v1_local_acceptance import load_release_city, compile_activity, compile_factorized_demand
    from metroflow.v1.release_inventory import build_inventory, InventoryPolicy
    from metroflow.v1.native_static import prepare_native_static
    from metroflow.v1.demand import calendar_profiles

    start = time.monotonic()
    matrix_file = repo / "scenarios/v1/release_matrix.json"
    matrix = json.loads(matrix_file.read_text())
    case = next(x for x in matrix["cases"] if x["id"] == "valley_weekday_s7")
    city, _ = load_release_city(case)
    blocks = city.face_graph.blocks
    schedule = compile_factorized_demand(
        tuple(compile_activity(city,b.id) for b in blocks if b.residents),
        tuple(compile_activity(city,b.id,"job") for b in blocks if b.jobs),
        tuple(compile_activity(city,b.id,"service",service_stock=b.jobs) for b in blocks if b.jobs),
        day=case["day"], freight_kg=1000, worker_shortfall=matrix["worker_shortfall"])
    inv_policy = dict(matrix["inventory_policy"])
    inv_policy["departures_s"] = tuple(inv_policy["departures_s"])
    inventory = build_inventory(city,InventoryPolicy(**inv_policy))
    data = prepare_native_static(city,schedule,inventory,step_s=10.0,record_budget=20000,event_budget=20000)
    router = V1RoutingGraph(data["route_arcs"],[x[1] for x in data["route_costs"]],data["allowed_turns"],8)
    endpoints, access_laws = {}, {}
    for label, block, node, _, atoms, _, _ in data["activities"]:
        key = (block,json.loads(label)["kind"])
        access_laws[key] = atoms
        endpoints[key] = (node, math.fsum(a*w for a,w in atoms))
    mode_vehicles = Counter()
    mode_persons = Counter()
    skip_vehicles = Counter()
    cohorts, queries = [], set()
    total_legs = 0
    for cohort, legs in schedule.iter_records():
        total_legs += len(legs)
        if not legs:
            continue
        leg = legs[0]
        mode_vehicles[leg.mode] += 2*leg.amounts.vehicles
        mode_persons[leg.mode] += 2*leg.amounts.persons
        if leg.mode != "car":
            continue
        if leg.endpoint_kind != "interzonal" or leg.destination is None:
            skip_vehicles[leg.endpoint_kind] += 2*leg.amounts.vehicles
            continue
        a, tau_a = endpoints[leg.origin.block_id,leg.origin.kind]
        b, tau_b = endpoints[leg.destination.block_id,leg.destination.kind]
        if not a or not b or a == b:
            skip_vehicles["missing_or_colocated_gate"] += 2*leg.amounts.vehicles
            continue
        queries.update(((a,b),(b,a)))
        cohorts.append((a,b,leg.purpose,leg.amounts.vehicles,tau_a,tau_b,(leg.origin.block_id,leg.origin.kind)))
    for leg in schedule.iter_freight_legs():
        total_legs += 1
        mode_vehicles[leg.mode] += leg.amounts.vehicles
        mode_persons[leg.mode] += leg.amounts.persons
    paths, route_ids = {}, {}
    idx = {link:i for i,link in enumerate(data["link_ids"])}
    for a,b in sorted(queries, key=lambda pair:(pair[1],pair[0])):
        found,_,_ = router.search(a,b,1,2000)
        if not found or not found[0]:
            route_ids[a,b] = -1
            continue
        path = tuple(idx[link] for link in found[0])
        route_ids[a,b] = paths.setdefault(path,len(paths))
    purposes = ("work","school","service")
    profile_windows = []
    for purpose in purposes:
        op,ret = calendar_profiles(schedule.day,purpose)
        assert len(op.windows) == len(ret.windows) == 1
        profile_windows.append((op.windows[0].start_s,op.windows[0].end_s,ret.windows[0].start_s,ret.windows[0].end_s))
    routed, included = [], []
    gate_mass = Counter()
    for a,b,purpose,mass,tau_a,tau_b,origin_key in cohorts:
        forward,backward = route_ids[a,b],route_ids[b,a]
        if min(forward,backward) < 0:
            skip_vehicles["missing_paired_route"] += 2*mass
            continue
        routed.append((forward,backward,purposes.index(purpose),mass,tau_a,tau_b))
        included.append(2*mass)
        gate_mass[origin_key,purposes.index(purpose)] += mass
    # Original origin-law convolution at onset, before any native road receiving delay.
    # Group only by identical support and outward profile; weights retain physical vehicles.
    onset = {}
    for t in (25700,25710,25720):
        mean_atoms, all_atoms = [], []
        for (key,source_purpose),mass in gate_mass.items():
            start,end,*_ = profile_windows[source_purpose]
            def cdf(access_s):
                return min(1.,max(0.,(t-access_s-start)/(end-start)))
            mean_atoms.append(mass*cdf(endpoints[key][1]))
            all_atoms.append(mass*math.fsum(w*cdf(a) for a,w in access_laws[key]))
        onset[str(t)] = {"mean_access_veh":math.fsum(mean_atoms),"source_access_veh":math.fsum(all_atoms)}
    (out/"onset_access.json").write_text(json.dumps(onset,indent=2)+"\n")
    payload = out/"network.txt"
    with payload.open("w") as f:
        print(len(data["groups"]),len(paths),len(routed),len(purposes),schedule.minimum_dwell_s,file=f)
        for row in data["groups"]:
            length,v,_,capacity,*_ = row
            print(length/min(v,10.),capacity,file=f)
        for path in paths:
            print(len(path),*path,file=f)
        for windows in profile_windows:
            print(*windows,file=f)
        for row in routed:
            print(*row,file=f)
    (out/"link_ids.json").write_text(json.dumps(data["link_ids"]))
    info = dict(case=case,city_identity=city.identity,schedule_identity=schedule.identity,
                input_matrix_sha256=hashlib.sha256(matrix_file.read_bytes()).hexdigest(),
                source_static_identity=data["identity"],extracted_input_sha256=hashlib.sha256(payload.read_bytes()).hexdigest(),
                resident_stock=schedule.resident_stock,total_calendar_legs=total_legs,
                original_mode_vehicles=dict(mode_vehicles),original_mode_persons=dict(mode_persons),original_cargo_kg=schedule.freight_kg,
                projected_vehicle_legs=2*len(routed),projected_vehicles=math.fsum(included),
                car_vehicles_excluded=dict(skip_vehicles),links=len(idx),distinct_legal_paths=len(paths),
                windows=len(data["windows"]),declared_nonempty_signals=sum(x is not None for x in data["signals"]),
                purpose_order=purposes,wall_s=time.monotonic()-start)
    (out/"input_summary.json").write_text(json.dumps(info,indent=2)+"\n")
    print(json.dumps(info),flush=True)


if __name__ == "__main__":
    main()
