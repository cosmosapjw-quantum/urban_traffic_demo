"""Independent closed-form car admission audit at the first native Valley peak."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sys


def original_laws(repo):
    sys.path[:0] = [str(repo/"native_binding"),str(repo/"src"),str(repo)]
    from tools.run_v1_local_acceptance import load_release_city,compile_activity,compile_factorized_demand
    from metroflow.v1.release_inventory import build_inventory,InventoryPolicy
    from metroflow.v1.native_static import prepare_native_static
    matrix=json.loads((repo/"scenarios/v1/release_matrix.json").read_text())
    case=next(r for r in matrix["cases"] if r["id"]=="valley_weekday_s7")
    city,_=load_release_city(case)
    blocks=city.face_graph.blocks
    calendar=compile_factorized_demand(
        tuple(compile_activity(city,b.id) for b in blocks if b.residents),
        tuple(compile_activity(city,b.id,"job") for b in blocks if b.jobs),
        tuple(compile_activity(city,b.id,"service",service_stock=b.jobs) for b in blocks if b.jobs),
        day=case["day"],freight_kg=1000,worker_shortfall=matrix["worker_shortfall"])
    inv=dict(matrix["inventory_policy"])
    inv["departures_s"]=tuple(inv["departures_s"])
    static=prepare_native_static(city,calendar,build_inventory(city,InventoryPolicy(**inv)),step_s=10.,record_budget=20000,event_budget=20000)
    laws={}
    for label,block,node,_,atoms,_,_ in static["activities"]:
        laws[block,json.loads(label)["kind"]]=(node,tuple(atoms))
    return city.identity,calendar,laws,static


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo",type=Path)
    parser.add_argument("prepared",type=Path)
    args=parser.parse_args()
    repo,prepared=args.repo.resolve(),args.prepared.resolve()
    city,calendar,laws,_=original_laws(repo)
    meta=json.loads((prepared/"input_summary.json").read_text())
    assert (city,calendar.identity)==(meta["city_identity"],meta["schedule_identity"])
    path=prepared/"network.txt"
    assert hashlib.sha256(path.read_bytes()).hexdigest()==meta["extracted_input_sha256"]
    weights=Counter()
    with path.open() as stream:
        links,paths,groups,purposes,_=map(float,next(stream).split())
        for _ in range(int(links+paths)):
            next(stream)
        windows=[tuple(map(float,next(stream).split())) for _ in range(int(purposes))]
        matched=0
        for cohort,legs in calendar.iter_records():
            if not legs: continue
            leg=legs[0]
            if leg.mode!="car" or leg.endpoint_kind!="interzonal" or leg.destination is None: continue
            origin=(leg.origin.block_id,leg.origin.kind)
            n1,atoms=laws[origin]; n2,other=laws[leg.destination.block_id,leg.destination.kind]
            if not n1 or not n2 or n1==n2: continue
            _,_,purpose,mass,am,bm=next(stream).split()
            assert ("work","school","service")[int(purpose)]==leg.purpose
            assert float(mass)==leg.amounts.vehicles
            assert float(am)==math.fsum(a*p for a,p in atoms) and float(bm)==math.fsum(a*p for a,p in other)
            weights[origin,int(purpose)]+=float(mass)
            matched+=1
        assert not stream.read().strip() and matched==groups
    assert math.isclose(math.fsum(weights.values())*2,meta["projected_vehicles"],abs_tol=1e-7,rel_tol=0)
    h,t=10.,25710.
    quantized=[]; continuous=[]
    for (key,purpose),mass in weights.items():
        _,atoms=laws[key]
        start,end,*_=windows[purpose]
        assert (end-start)%h==0 and start%h==0 and end%h==0
        steps=(end-start)/h
        eligible=max(0,min(steps,(t-start)/h))
        for access,prob in atoms:
            rank_bins=max(0,min(eligible,math.floor((t+1e-10-start-access)/h+0.5)))
            quantized.append(mass*prob*rank_bins/steps)
            continuous.append(mass*prob*max(0.,min(1.,(t-access-start)/(end-start))))
    native=json.loads((repo/"artifacts/v03_measure_lift_20261123/S06_fresh0.json").read_text())["final_execution_report"]["service"]
    assert native["time_s"]==t+h and native["bus_road_vehicles"]==native["freight_completed_vehicles"]==0
    actual=native["road_released_veh"]-native["completed_bus_vehicles"]
    predicted=math.fsum(quantized)
    r=dict(native_end_s=t+h,last_prepare_s=t,step_s=h,native_routed_car_admitted_veh=actual,
           source_phase_prediction_veh=predicted,difference_veh=predicted-actual,
           continuous_at_last_prepare_veh=math.fsum(continuous),unique_origin_law_purpose_pairs=len(weights),
           network_sha256=meta["extracted_input_sha256"])
    print(json.dumps(r,indent=2))
    assert math.isclose(predicted,actual,rel_tol=0,abs_tol=1e-8)


if __name__=="__main__":
    main()
