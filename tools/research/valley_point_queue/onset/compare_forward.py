"""Compare the frozen car prediction to validated physical rows of native diagnostic runs."""
import argparse
import hashlib
import json
from pathlib import Path

p=argparse.ArgumentParser(description=__doc__)
p.add_argument("prediction",type=Path)
p.add_argument("output",type=Path)
p.add_argument("native_jsonl",type=Path,nargs="+")
args=p.parse_args()
frozen=args.prediction.read_bytes()
sha=hashlib.sha256(frozen).hexdigest()
assert sha=="7ff4d01b8dcd596723a56efa00cba5a9def0c8557fc636e93fc6900c2cd4625d"
forecast=json.loads(frozen)
out={}
for file in args.native_jsonl:
    for line in file.read_bytes().splitlines(keepends=True):
        row=json.loads(line)
        if row.get("phase")!="validated" or "physical" not in row: continue
        t=str(int(row["time_s"]))
        if t not in forecast["predictions"]:continue
        physical=row["physical"]
        assert (physical["city_identity"],physical["schedule_identity"])==(forecast["city"],forecast["schedule"])
        s=physical["service"]
        assert s["bus_road_vehicles"]==s["freight_completed_vehicles"]==0 and int(t)<32400
        buses=s["completed_bus_vehicles"]
        obs=dict(car_admitted_veh=s["road_released_veh"]-buses,car_exited_veh=s["road_completed_veh"]-buses,
                 car_subsystem_stock_veh=s["road_released_veh"]-s["road_completed_veh"])
        metrics={k:dict(predicted=forecast["predictions"][t][k],observed=v,delta=forecast["predictions"][t][k]-v,
                         relative_error=forecast["predictions"][t][k]/v-1) for k,v in obs.items()}
        if t not in out:
            out[t]=dict(metrics=metrics,receipts=[])
        assert out[t]["metrics"]==metrics
        out[t]["receipts"].append(dict(file=file.name,native_phase=row["phase"],completed_single_segment_buses=buses,
            physical_row_sha256=hashlib.sha256(line).hexdigest(),native_wall_s=row["wall_s"]))
answer=dict(frozen_sha256=sha,scope="native diagnostic internal-policy arm, not original release acceptance",
            scored=out,prediction_only=sorted(set(forecast["predictions"])-set(out)))
args.output.write_text(json.dumps(answer,indent=2,allow_nan=False)+"\n")
