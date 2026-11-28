"""Independent exact-rational verification of archived scalar claims, not simulation."""
from fractions import Fraction as F
from pathlib import Path
import json
import re
import hashlib

root = Path(__file__).resolve().parents[2]
def load(rel):
    return json.loads((root / rel).read_text(), parse_float=F)
def approx(x,y):
    assert abs(x-y) <= F(1,10**8) * max(1,abs(x)), (x,y)
def main():
    base="artifacts/akm_d05_final_20261128/"
    dbase="artifacts/akm_d09_final_cohort_20261128/"
    r=load("artifacts/akm_d11_decision_20261128/S06_decision.json")
    a=load(base+"S05_A_results.json")["results"]
    assert sum(x["status"]=="HORIZON_REACHED" for x in a)==22
    for p in r["a"]["policies"]:
        day=sorted((x for x in a if x["scenario"]["policy"]==p["policy"] and x["scenario"]["day_profile"]),key=lambda x:x["scenario"]["cells"])
        assert len(day)==3
        if day[-1]["status"]!="HORIZON_REACHED":
            assert p["finest_adjacent_relative_gap"] is None
        else:
            c,f=[x["completed_conditional_mean_s"] for x in day[-2:]]
            approx(abs(f-c)/c,p["finest_adjacent_relative_gap"])
    b0,b1=(load(base+f"S06_B_mesh{m}.json") for m in (300,150))
    p0,p1=[v["result"]["snapshots"] for v in (b0,b1)]
    for key,out in (("max_receiving_ratio","max_receiving_ratio_abs_gap"),("max_storage_ratio","max_storage_ratio_abs_gap")):
        approx(max(abs(a[key]-b[key]) for a,b in zip(p0,p1)),r["b"][out])
    means=[p[-1]["classes"][0]["trip_seconds"]/p[-1]["classes"][0]["completed"] for p in (p0,p1)]
    approx(abs(means[1]-means[0])/means[0],r["b"]["mean_relative_gap"])
    support=load(dbase+"S08_support.json")
    approx(support["bus_person_intent"]-support["sum_single_run_seat_capacity"],r["d"]["bus_deficit_lower_bound"])
    bound=support["parent_profile_bound"]
    approx((bound["requested"][0]-bound["optimistic_completion_ceiling"][0])/bound["requested"][0],r["d"]["parent_profile_uncompleted_fraction"])
    log=(root/(dbase+"S09_batch_bias.log")).read_text()
    rows=re.findall(r"D09_BATCH_BIAS h=([\d.]+) pair_first=([\d.]+) pair_second=([\d.]+) independent_second=([\d.]+) extra=([\d.]+)",log)
    assert len(rows)==3
    for h,first,second,independent,extra in map(lambda row:map(F,row),rows):
        assert second-independent==extra==F(100,10)-3
        assert h in (F(1),F(1,2),F(1,4))
    # All gate failures must survive; unknowns cannot count as passes.
    assert all(not all(g=="PASS" for g in c["gates"].values()) and not c["eligible"] for c in r["candidate_matrix"])
    assert r["candidate_selected"] is None and r["new_simulation_runs"]==0
    manifest=(root/"artifacts/akm_d11_decision_20261128/S01_baseline.txt").read_text()
    for line in manifest.splitlines():
        if "  artifacts/" in line or "  docs/v1/PLAN.json" in line:
            digest,path=line.split("  ",1)
            assert hashlib.sha256((root/path).read_bytes()).hexdigest()==digest
    print(json.dumps({"status":"VERIFIED_SCOPED","method":"exact rational recomputation of decimal archive and recorded native timing log","a_cases":len(a),"b_matched_observations":len(p0),"d_refinement_rows":len(rows),"new_simulation_runs":0,"nonclaim":"not independent generation of traffic trajectories"}))
if __name__=="__main__":
    main()
